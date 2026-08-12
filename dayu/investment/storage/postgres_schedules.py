"""PostgreSQL durable schedule repository 实现（Slice 2.2）。

本模块是 ``ScheduleStoreProtocol`` 的唯一合法实现 owner，把 schedule
definition 与 occurrence outbox 的持久化状态机收敛到真实的 PostgreSQL
16 transaction、RLS、列级 grant 与 trigger 上：

- 每个方法拥有自己的 tenant-scoped 单事务：先 ``SET LOCAL
  app.tenant_id``，所有 clock 决策只取同一事务内的
  ``transaction_timestamp()`` / ``clock_timestamp()``；
- ``job_schedules`` 是 immutable schedule definition/current cursor
  真源；``job_schedule_occurrences`` 是 cursor 与 job enqueue 之间的
  durable outbox；
- ``reserve_occurrences`` / ``set_state`` / ``begin_materialization``
  之间以 schedule 行锁线性化（``schedule -> occurrence`` 固定锁序）：
  disable 先赢则 PENDING->SKIPPED 且零 job，begin 先赢则
  MATERIALIZING 成为不可撤销的入队承诺；
- 稳定错误消息只含固定 safe code，绝不携带 cron/payload/DSN/SQL/
  raw exception。

本模块绝不 import ``dayu.host`` / ``dayu.services`` / Redis 或
croniter。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypeAlias
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, sessionmaker

from dayu.investment.domain.identifiers import TenantId, TenantScope
from dayu.investment.domain.jobs import (
    CanonicalJobDocument,
    JobHandlerDescriptor,
    JobInputError,
)
from dayu.investment.domain.schedules import (
    CanonicalScheduleEnqueueSnapshot,
    ScheduleActivationRequest,
    ScheduleDefinition,
    ScheduleDueCursor,
    ScheduleDueEntry,
    ScheduleDuePage,
    ScheduleInputError,
    ScheduleInvariantError,
    ScheduleMarkEnqueuedAction,
    ScheduleMarkEnqueuedResult,
    ScheduleMaterializationAction,
    ScheduleMaterializationAdmission,
    ScheduleMaterializationDecision,
    ScheduleMisfirePolicy,
    ScheduleObservation,
    ScheduleOccurrence,
    ScheduleOccurrenceState,
    ScheduleRegistrationRequest,
    ScheduleReplayCursor,
    ScheduleReplayPage,
    ScheduleRepositoryError,
    ScheduleReservationBatch,
    ScheduleReservationResult,
    ScheduleReserveAction,
    ScheduleSkipReason,
    ScheduleState,
    ScheduleStateTransitionAction,
    ScheduleStateTransitionResult,
    ScheduleVersionConflictError,
)
from dayu.investment.storage.db import PLATFORM_SCHEMA_NAME, TENANT_CONTEXT_SETTING
from dayu.investment.storage.protocols import ScheduleStoreProtocol

_SCHEMA = PLATFORM_SCHEMA_NAME
_SHA256_HEX_LENGTH = 64
"""SHA-256 小写十六进制文本的固定长度。"""

# 各查询统一列序常量（供 helper 索引，避免重组 tuple）。
_SCHEDULE_COLS = (
    "id, tenant_id, schedule_key, descriptor_job_type, "
    "descriptor_payload_schema_name, descriptor_payload_schema_version, "
    "descriptor_max_attempts, descriptor_retry_base_seconds, "
    "descriptor_retry_max_seconds, descriptor_lease_duration_seconds, "
    "payload_schema_name, payload_schema_version, payload_bytes, payload_sha256, "
    "cron_expression, timezone_name, misfire_policy, misfire_grace_seconds, "
    "job_deadline_seconds, state, next_fire_at, version, created_at, updated_at"
)
_OCCURRENCE_COLS = (
    "id, tenant_id, schedule_id, schedule_version, scheduled_for, state, "
    "snapshot_descriptor_job_type, snapshot_descriptor_payload_schema_name, "
    "snapshot_descriptor_payload_schema_version, snapshot_descriptor_max_attempts, "
    "snapshot_descriptor_retry_base_seconds, snapshot_descriptor_retry_max_seconds, "
    "snapshot_descriptor_lease_duration_seconds, snapshot_payload_schema_name, "
    "snapshot_payload_schema_version, snapshot_payload_bytes, snapshot_payload_sha256, "
    "snapshot_idempotency_key, snapshot_available_at, snapshot_deadline_at, "
    "snapshot_request_fingerprint, job_run_id, coalesced_count, skip_reason, "
    "created_at, updated_at"
)


def _qualified_columns(columns: str, alias: str) -> str:
    """为逗号分隔列清单增加固定 SQL alias。

    Args:
        columns: 模块内固定列清单。
        alias: 模块内固定 SQL alias。

    Returns:
        每列都带 alias 的逗号分隔清单。

    Raises:
        无。
    """

    return ", ".join(f"{alias}.{column.strip()}" for column in columns.split(","))


_SCHEDULE_S_COLS = _qualified_columns(_SCHEDULE_COLS, "s")
_SCHEDULE_D_COLS = _qualified_columns(_SCHEDULE_COLS, "d")
_SCHEDULE_C_COLS = _qualified_columns(_SCHEDULE_COLS, "c")
_OCCURRENCE_O_COLS = _qualified_columns(_OCCURRENCE_COLS, "o")
_OCCURRENCE_C_COLS = _qualified_columns(_OCCURRENCE_COLS, "c")

_RowValue: TypeAlias = str | int | float | bool | datetime | bytes | memoryview | UUID | None
"""原始 SQL 行的 closed 标量值联合（禁止 object/Any 逃逸）。"""

_SqlRow: TypeAlias = Row[tuple[_RowValue, ...]]
"""SQLAlchemy text query 的参数化 closed scalar row。"""

_RowLike: TypeAlias = _SqlRow
"""仓储内部唯一行类型；不会向 Service/Host 泄漏。"""

_SNAPSHOT_COLUMN_KEYS: tuple[str, ...] = (
    "snapshot_descriptor_job_type",
    "snapshot_descriptor_payload_schema_name",
    "snapshot_descriptor_payload_schema_version",
    "snapshot_descriptor_max_attempts",
    "snapshot_descriptor_retry_base_seconds",
    "snapshot_descriptor_retry_max_seconds",
    "snapshot_descriptor_lease_duration_seconds",
    "snapshot_payload_schema_name",
    "snapshot_payload_schema_version",
    "snapshot_payload_bytes",
    "snapshot_payload_sha256",
    "snapshot_idempotency_key",
    "snapshot_available_at",
    "snapshot_deadline_at",
    "snapshot_request_fingerprint",
)
"""occurrence 冻结 enqueue snapshot 的扁平列 key 集合（与 0004 一致）。"""


def _canonical_uuid(value: str, label: str) -> str:
    """校验并返回 canonical UUID 字符串。

    Args:
        value: 待校验的 UUID 字符串。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的小写连字符 UUID 字符串。

    Raises:
        ScheduleInputError: 值不是规范 UUID 时抛出。
    """

    if not isinstance(value, str):
        raise ScheduleInputError(f"{label} 必须是规范 UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ScheduleInputError(f"{label} 必须是规范 UUID") from None
    if parsed.int == 0:
        raise ScheduleInputError(f"{label} 必须是规范 UUID")
    canonical = str(parsed)
    if canonical != value:
        raise ScheduleInputError(f"{label} 必须是规范 UUID")
    return canonical


def _validate_scope(scope: TenantScope) -> TenantId:
    """校验租户范围并返回租户标识。

    Args:
        scope: 待校验的租户范围。

    Returns:
        租户标识。

    Raises:
        ScheduleInputError: scope 非法时抛出。
    """

    if not isinstance(scope, TenantScope):
        raise ScheduleInputError("scope 必须是 TenantScope")
    _canonical_uuid(scope.tenant_id.value, "租户标识")
    return scope.tenant_id


def _validate_uuid(value: UUID, label: str) -> UUID:
    """校验 UUID 参数并拒绝全零值。

    Args:
        value: 待校验 UUID。
        label: 安全错误字段名。

    Returns:
        原 UUID。

    Raises:
        ScheduleInputError: 值不是非零 UUID 时抛出。
    """

    if not isinstance(value, UUID) or value.int == 0:
        raise ScheduleInputError(f"{label} 必须是非零 UUID")
    return value


def _validate_limit(limit: int) -> int:
    """校验 keyword-only page limit 为 exact positive int。

    Args:
        limit: 待校验 page limit。

    Returns:
        原 limit。

    Raises:
        ScheduleInputError: bool、非 int 或非正值时抛出。
    """

    if type(limit) is not int or limit <= 0:
        raise ScheduleInputError("limit 必须是正整数")
    return limit


def _validate_fingerprint(value: str) -> str:
    """校验 expected snapshot fingerprint 为小写 SHA-256。

    Args:
        value: 待校验 fingerprint。

    Returns:
        原 fingerprint。

    Raises:
        ScheduleInputError: 值不是小写 64-hex 时抛出。
    """

    if (
        not isinstance(value, str)
        or len(value) != _SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ScheduleInputError("expected_snapshot_fingerprint 必须是小写 64 位 SHA-256")
    return value


def _set_tenant_local(session: Session, tenant_id: TenantId) -> None:
    """以 bind parameter 设置租户上下文并读回确认。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。

    Returns:
        无。

    Raises:
        ScheduleRepositoryError: 读回确认不一致时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    result = session.execute(
        text(f"SELECT set_config('{TENANT_CONTEXT_SETTING}', :tenant_id, true)"),
        {"tenant_id": tenant_value},
    )
    if result.scalar() != tenant_value:
        raise ScheduleRepositoryError("schedule_repository_tenant_context")


def _clock(session: Session) -> tuple[datetime, datetime]:
    """取同一事务的 PG clock（transaction/clock timestamp）。

    Args:
        session: 当前事务 Session。

    Returns:
        ``(transaction_timestamp, clock_timestamp)`` 二元组。

    Raises:
        ScheduleRepositoryError: 查询失败时抛出。
    """

    row = session.execute(text("SELECT transaction_timestamp(), clock_timestamp()")).one()
    return _as_aware_utc(row[0]), _as_aware_utc(row[1])


def _as_aware_utc(value: _RowValue) -> datetime:
    """把 PG 返回的时间值转换为 aware UTC datetime。

    Args:
        value: PG 时间标量。

    Returns:
        aware UTC datetime。

    Raises:
        ScheduleRepositoryError: 值不是时间时抛出。
    """

    if not isinstance(value, datetime):
        raise ScheduleRepositoryError("schedule_repository_datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ensure_row_tenant(row: _RowLike, tenant_id: TenantId) -> None:
    """校验查询行 tenant 与调用 scope 精确一致。

    Args:
        row: schedule 或 occurrence 查询行。
        tenant_id: 当前调用租户。

    Returns:
        无。

    Raises:
        ScheduleRepositoryError: tenant 列缺失、类型异常或不一致时抛出。
    """

    tenant_value = _rv(row, "tenant_id")
    if not isinstance(tenant_value, UUID) or str(tenant_value) != tenant_id.value:
        raise ScheduleRepositoryError("schedule_repository_tenant_mismatch")


def _rv(row: _RowLike, key: str) -> _RowValue:
    """从行按命名键读取值（类型安全列访问）。

    Args:
        row: SQLAlchemy 查询行或合成 dict 行。
        key: 列名。

    Returns:
        该列的 closed 标量值。

    Raises:
        KeyError: 列不存在时抛出。
    """

    return row._mapping[key]


def _rv_str(row: _RowLike, key: str) -> str:
    """读取命名列的字符串值。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        字符串值。

    Raises:
        ScheduleRepositoryError: 值不是字符串时抛出。
    """

    value = _rv(row, key)
    if not isinstance(value, str):
        raise ScheduleRepositoryError("schedule_repository_string")
    return value


def _rv_int(row: _RowLike, key: str) -> int:
    """读取命名列的整数值。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        整数值。

    Raises:
        ScheduleRepositoryError: 值不是整数时抛出。
    """

    value = _rv(row, key)
    if type(value) is not int:
        raise ScheduleRepositoryError("schedule_repository_integer")
    return value


def _rv_bool(row: _RowLike, key: str) -> bool:
    """读取命名列的 bool 值。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        bool 值。

    Raises:
        ScheduleRepositoryError: 值不是 exact bool 时抛出。
    """

    value = _rv(row, key)
    if type(value) is not bool:
        raise ScheduleRepositoryError("schedule_repository_boolean")
    return value


def _rv_bytes(row: _RowLike, key: str) -> bytes:
    """读取命名列的 bytes 值。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        bytes 值。

    Raises:
        ScheduleRepositoryError: 值不是 bytes 时抛出。
    """

    value = _rv(row, key)
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ScheduleRepositoryError("schedule_repository_bytes")
    return bytes(value)


def _rv_dt(row: _RowLike, key: str) -> datetime:
    """读取命名列的 aware UTC 时间值。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        aware UTC datetime。

    Raises:
        ScheduleRepositoryError: 值不是时间时抛出。
    """

    return _as_aware_utc(_rv(row, key))


def _rv_uuid(row: _RowLike, key: str) -> UUID:
    """读取命名列的 UUID 值。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        UUID 值。

    Raises:
        ScheduleRepositoryError: 值不是 UUID 时抛出。
    """

    value = _rv(row, key)
    if not isinstance(value, UUID):
        raise ScheduleRepositoryError("schedule_repository_uuid")
    return value


def _rv_obj(row: _RowLike, key: str) -> _RowValue:
    """读取命名列的原生值（用于空值判断/比较）。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        该列的 closed 标量值。

    Raises:
        KeyError: 列不存在时抛出。
    """

    return _rv(row, key)


def _row_descriptor(row: _RowLike) -> JobHandlerDescriptor:
    """从 schedule 行构造 descriptor。

    Args:
        row: schedule 查询行。

    Returns:
        ``JobHandlerDescriptor``。

    Raises:
        ScheduleRepositoryError: 行数据违反不变量时抛出。
    """

    try:
        return JobHandlerDescriptor(
            job_type=_rv_str(row, "descriptor_job_type"),
            payload_schema_name=_rv_str(row, "descriptor_payload_schema_name"),
            payload_schema_version=_rv_int(row, "descriptor_payload_schema_version"),
            max_attempts=_rv_int(row, "descriptor_max_attempts"),
            retry_base_seconds=_rv_int(row, "descriptor_retry_base_seconds"),
            retry_max_seconds=_rv_int(row, "descriptor_retry_max_seconds"),
            lease_duration_seconds=_rv_int(row, "descriptor_lease_duration_seconds"),
        )
    except (ScheduleInputError, JobInputError):
        raise ScheduleRepositoryError("schedule_repository_descriptor") from None


def _row_payload(row: _RowLike) -> CanonicalJobDocument:
    """从 schedule 行构造 canonical payload document。

    Args:
        row: schedule 查询行。

    Returns:
        ``CanonicalJobDocument``。

    Raises:
        ScheduleRepositoryError: 行数据违反不变量时抛出。
    """

    try:
        return CanonicalJobDocument(
            schema_name=_rv_str(row, "payload_schema_name"),
            schema_version=_rv_int(row, "payload_schema_version"),
            canonical_bytes=_rv_bytes(row, "payload_bytes"),
            sha256=_rv_str(row, "payload_sha256"),
        )
    except JobInputError:
        raise ScheduleRepositoryError("schedule_repository_payload") from None


def _row_definition(row: _RowLike, tenant_id: TenantId) -> ScheduleDefinition:
    """从 schedule 行构造 ``ScheduleDefinition``。

    Args:
        row: schedule 查询行。
        tenant_id: 租户标识。

    Returns:
        ``ScheduleDefinition``。

    Raises:
        ScheduleRepositoryError: 行数据违反不变量时抛出。
    """

    _ensure_row_tenant(row, tenant_id)
    next_fire_raw = _rv_obj(row, "next_fire_at")
    next_fire_at = _as_aware_utc(next_fire_raw) if next_fire_raw is not None else None
    try:
        return ScheduleDefinition(
            id=_rv_uuid(row, "id"),
            tenant_id=tenant_id,
            schedule_key=_rv_str(row, "schedule_key"),
            descriptor=_row_descriptor(row),
            payload=_row_payload(row),
            cron_expression=_rv_str(row, "cron_expression"),
            timezone_name=_rv_str(row, "timezone_name"),
            misfire_policy=ScheduleMisfirePolicy(_rv_str(row, "misfire_policy")),
            misfire_grace_seconds=_rv_int(row, "misfire_grace_seconds"),
            job_deadline_seconds=_rv_int(row, "job_deadline_seconds"),
            state=ScheduleState(_rv_str(row, "state")),
            next_fire_at=next_fire_at,
            version=_rv_int(row, "version"),
            created_at=_rv_dt(row, "created_at"),
            updated_at=_rv_dt(row, "updated_at"),
        )
    except (ScheduleInputError, ValueError):
        raise ScheduleRepositoryError("schedule_repository_definition") from None


def _snapshot_from_row(row: _RowLike) -> CanonicalScheduleEnqueueSnapshot | None:
    """从 occurrence 行的扁平 snapshot 列构造冻结 snapshot。

    Args:
        row: occurrence 查询行。

    Returns:
        完整 snapshot；snapshot 列全 NULL 时返回 ``None``。

    Raises:
        ScheduleRepositoryError: snapshot 列部分非空（违反 0004 CHECK）
            时抛出。
    """

    values = [_rv_obj(row, key) for key in _SNAPSHOT_COLUMN_KEYS]
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ScheduleRepositoryError("schedule_repository_partial_snapshot")
    try:
        descriptor = JobHandlerDescriptor(
            job_type=_rv_str(row, "snapshot_descriptor_job_type"),
            payload_schema_name=_rv_str(row, "snapshot_descriptor_payload_schema_name"),
            payload_schema_version=_rv_int(row, "snapshot_descriptor_payload_schema_version"),
            max_attempts=_rv_int(row, "snapshot_descriptor_max_attempts"),
            retry_base_seconds=_rv_int(row, "snapshot_descriptor_retry_base_seconds"),
            retry_max_seconds=_rv_int(row, "snapshot_descriptor_retry_max_seconds"),
            lease_duration_seconds=_rv_int(row, "snapshot_descriptor_lease_duration_seconds"),
        )
        payload = CanonicalJobDocument(
            schema_name=_rv_str(row, "snapshot_payload_schema_name"),
            schema_version=_rv_int(row, "snapshot_payload_schema_version"),
            canonical_bytes=_rv_bytes(row, "snapshot_payload_bytes"),
            sha256=_rv_str(row, "snapshot_payload_sha256"),
        )
        return CanonicalScheduleEnqueueSnapshot(
            descriptor=descriptor,
            payload=payload,
            idempotency_key=_rv_str(row, "snapshot_idempotency_key"),
            available_at=_rv_dt(row, "snapshot_available_at"),
            deadline_at=_rv_dt(row, "snapshot_deadline_at"),
            request_fingerprint=_rv_str(row, "snapshot_request_fingerprint"),
        )
    except (ScheduleInputError, JobInputError):
        raise ScheduleRepositoryError("schedule_repository_snapshot") from None


def _row_occurrence(row: _RowLike, tenant_id: TenantId) -> ScheduleOccurrence:
    """从 occurrence 行构造 ``ScheduleOccurrence``。

    Args:
        row: occurrence 查询行。
        tenant_id: 租户标识。

    Returns:
        ``ScheduleOccurrence``。

    Raises:
        ScheduleRepositoryError: 行数据违反不变量时抛出。
    """

    _ensure_row_tenant(row, tenant_id)
    job_raw = _rv_obj(row, "job_run_id")
    count_raw = _rv_obj(row, "coalesced_count")
    reason_raw = _rv_obj(row, "skip_reason")
    try:
        return ScheduleOccurrence(
            id=_rv_uuid(row, "id"),
            tenant_id=tenant_id,
            schedule_id=_rv_uuid(row, "schedule_id"),
            schedule_version=_rv_int(row, "schedule_version"),
            scheduled_for=_rv_dt(row, "scheduled_for"),
            state=ScheduleOccurrenceState(_rv_str(row, "state")),
            snapshot=_snapshot_from_row(row),
            job_id=_rv_uuid(row, "job_run_id") if job_raw is not None else None,
            coalesced_count=(_rv_int(row, "coalesced_count") if count_raw is not None else None),
            skip_reason=(ScheduleSkipReason(_rv_str(row, "skip_reason")) if reason_raw is not None else None),
            created_at=_rv_dt(row, "created_at"),
            updated_at=_rv_dt(row, "updated_at"),
        )
    except (ScheduleInputError, ValueError):
        raise ScheduleRepositoryError("schedule_repository_occurrence") from None


def _snapshot_bind_values(snapshot: CanonicalScheduleEnqueueSnapshot) -> dict[str, _RowValue]:
    """把冻结 snapshot 展开为扁平绑定参数。

    Args:
        snapshot: 冻结 enqueue snapshot。

    Returns:
        snapshot 列到值的绑定参数字典。

    Raises:
        无。
    """

    descriptor = snapshot.descriptor
    payload = snapshot.payload
    return {
        "snapshot_descriptor_job_type": descriptor.job_type,
        "snapshot_descriptor_payload_schema_name": descriptor.payload_schema_name,
        "snapshot_descriptor_payload_schema_version": descriptor.payload_schema_version,
        "snapshot_descriptor_max_attempts": descriptor.max_attempts,
        "snapshot_descriptor_retry_base_seconds": descriptor.retry_base_seconds,
        "snapshot_descriptor_retry_max_seconds": descriptor.retry_max_seconds,
        "snapshot_descriptor_lease_duration_seconds": descriptor.lease_duration_seconds,
        "snapshot_payload_schema_name": payload.schema_name,
        "snapshot_payload_schema_version": payload.schema_version,
        "snapshot_payload_bytes": payload.canonical_bytes,
        "snapshot_payload_sha256": payload.sha256,
        "snapshot_idempotency_key": snapshot.idempotency_key,
        "snapshot_available_at": snapshot.available_at,
        "snapshot_deadline_at": snapshot.deadline_at,
        "snapshot_request_fingerprint": snapshot.request_fingerprint,
    }


def _null_snapshot_bind_values() -> dict[str, _RowValue]:
    """构造全 NULL 的 snapshot 绑定参数（skipped audit）。

    Args:
        无。

    Returns:
        snapshot 列全部为 ``None`` 的绑定参数字典。

    Raises:
        无。
    """

    return {key: None for key in _SNAPSHOT_COLUMN_KEYS}


def _validate_activation_candidate(value: datetime | None) -> datetime:
    """校验 ACTIVE candidate 为 aware UTC。

    Args:
        value: Service 以 PG observation 计算出的 candidate。

    Returns:
        校验后的 candidate。

    Raises:
        ScheduleInvariantError: candidate 缺失、naive 或非 UTC 时抛出。
    """

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ScheduleInvariantError("schedule_activation_candidate")
    return value


def _clock_now(session: Session) -> datetime:
    """读取一次 fresh PostgreSQL ``clock_timestamp()``。

    Args:
        session: 当前租户事务 Session。

    Returns:
        aware UTC PG wall clock。

    Raises:
        ScheduleRepositoryError: PG 返回值非法时抛出。
    """

    row = session.execute(text("SELECT clock_timestamp() AS database_now")).one()
    return _rv_dt(row, "database_now")


def _lock_schedule(
    session: Session,
    tenant_id: TenantId,
    schedule_id: UUID,
) -> _SqlRow | None:
    """按固定 tenant/id 锁定 schedule 行。

    Args:
        session: 当前租户事务 Session。
        tenant_id: 当前租户。
        schedule_id: 目标 schedule UUID。

    Returns:
        锁定行；不存在或跨租户时返回 ``None``。

    Raises:
        无。
    """

    return session.execute(
        text(
            f"SELECT {_SCHEDULE_COLS} FROM {_SCHEMA}.job_schedules "
            "WHERE tenant_id = :tenant_id AND id = :schedule_id FOR UPDATE"
        ),
        {
            "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
            "schedule_id": str(schedule_id),
        },
    ).first()


def _lock_occurrence_after_parent(
    session: Session,
    tenant_id: TenantId,
    occurrence_id: UUID,
) -> tuple[_SqlRow, _SqlRow]:
    """经无锁 locator 后按 schedule->occurrence 顺序锁定两行。

    Args:
        session: 当前租户事务 Session。
        tenant_id: 当前租户。
        occurrence_id: 目标 occurrence UUID。

    Returns:
        ``(schedule_row, occurrence_row)`` 锁定行二元组。

    Raises:
        ScheduleInvariantError: occurrence/parent 在租户内不存在或 locator
            identity 漂移时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    locator = session.execute(
        text(
            f"SELECT schedule_id FROM {_SCHEMA}.job_schedule_occurrences "
            "WHERE tenant_id = :tenant_id AND id = :occurrence_id"
        ),
        {"tenant_id": tenant_value, "occurrence_id": str(occurrence_id)},
    ).first()
    if locator is None:
        raise ScheduleInvariantError("schedule_occurrence_missing")
    schedule_id = _rv_uuid(locator, "schedule_id")
    schedule_row = _lock_schedule(session, tenant_id, schedule_id)
    if schedule_row is None:
        raise ScheduleInvariantError("schedule_occurrence_parent_missing")
    occurrence_row = session.execute(
        text(
            f"SELECT {_OCCURRENCE_COLS} "
            f"FROM {_SCHEMA}.job_schedule_occurrences "
            "WHERE tenant_id = :tenant_id AND id = :occurrence_id "
            "AND schedule_id = :schedule_id FOR UPDATE"
        ),
        {
            "tenant_id": tenant_value,
            "occurrence_id": str(occurrence_id),
            "schedule_id": str(schedule_id),
        },
    ).first()
    if occurrence_row is None:
        raise ScheduleInvariantError("schedule_occurrence_locator_drift")
    return schedule_row, occurrence_row


def _activate_locked_schedule(
    session: Session,
    tenant_id: TenantId,
    request: ScheduleActivationRequest,
    previous: ScheduleDefinition,
    candidate: datetime,
) -> ScheduleStateTransitionResult:
    """在 schedule row lock 后执行单 statement conditional ACTIVE DML。

    one-row MATERIALIZED CTE 只调用一次 ``clock_timestamp()``；同一个
    ``database_now`` 同时用于 future guard 与 RETURNING observation。

    Args:
        session: 已持有目标 schedule row lock 的事务 Session。
        tenant_id: 当前租户。
        request: 原始 ACTIVE CAS 请求。
        previous: row lock 内重建的转换前 definition。
        candidate: aware UTC future candidate。

    Returns:
        ``applied`` 或 ``clock_stale`` 的闭合 transition result。

    Raises:
        ScheduleVersionConflictError: conditional CAS 的 identity/state/version
            在锁内不再匹配时抛出。
        ScheduleRepositoryError: locked row 意外消失或数据非法时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    row = session.execute(
        text(
            "WITH observed AS MATERIALIZED "
            "(SELECT clock_timestamp() AS database_now) "
            f"UPDATE {_SCHEMA}.job_schedules AS s "
            "SET state = :active, next_fire_at = :candidate, "
            "version = s.version + 1, updated_at = observed.database_now "
            "FROM observed "
            "WHERE s.tenant_id = :tenant_id AND s.id = :schedule_id "
            "AND s.version = :expected_version AND s.state = :disabled "
            "AND :candidate > observed.database_now "
            f"RETURNING {_SCHEDULE_S_COLS}, observed.database_now"
        ),
        {
            "active": ScheduleState.ACTIVE.value,
            "candidate": candidate,
            "tenant_id": tenant_value,
            "schedule_id": str(request.schedule_id),
            "expected_version": request.expected_version,
            "disabled": ScheduleState.DISABLED.value,
        },
    ).first()
    if row is not None:
        observation = ScheduleObservation(
            definition=_row_definition(row, tenant_id),
            database_now=_rv_dt(row, "database_now"),
        )
        return ScheduleStateTransitionResult(
            action=ScheduleStateTransitionAction.APPLIED,
            request=request,
            previous_definition=previous,
            observation=observation,
            activation_next_fire_at=candidate,
        )

    # future guard 为 false 时仍持有原 row lock；同事务重读 row，并用
    # fresh wall clock 构造唯一合法的 clock_stale 零修改结果。
    stale_row = session.execute(
        text(
            "WITH observed AS MATERIALIZED "
            "(SELECT clock_timestamp() AS database_now) "
            f"SELECT {_SCHEDULE_S_COLS}, observed.database_now "
            f"FROM {_SCHEMA}.job_schedules AS s CROSS JOIN observed "
            "WHERE s.tenant_id = :tenant_id AND s.id = :schedule_id"
        ),
        {"tenant_id": tenant_value, "schedule_id": str(request.schedule_id)},
    ).first()
    if stale_row is None:
        raise ScheduleRepositoryError("schedule_repository_locked_row_missing")
    stale_definition = _row_definition(stale_row, tenant_id)
    if stale_definition.version != request.expected_version or stale_definition.state is not ScheduleState.DISABLED:
        raise ScheduleVersionConflictError("schedule_version_conflict")
    return ScheduleStateTransitionResult(
        action=ScheduleStateTransitionAction.CLOCK_STALE,
        request=request,
        previous_definition=previous,
        observation=ScheduleObservation(
            definition=stale_definition,
            database_now=_rv_dt(stale_row, "database_now"),
        ),
        activation_next_fire_at=candidate,
    )


def _disable_locked_schedule(
    session: Session,
    tenant_id: TenantId,
    request: ScheduleActivationRequest,
    previous: ScheduleDefinition,
) -> ScheduleStateTransitionResult:
    """在 schedule row lock 后禁用并只收敛仍为 PENDING 的 occurrence。

    Args:
        session: 已持有 schedule row lock 的租户事务 Session。
        tenant_id: 当前租户。
        request: 原始 DISABLED CAS 请求。
        previous: 转换前 definition。

    Returns:
        ``applied`` transition；cursor 原值完整保留。

    Raises:
        ScheduleVersionConflictError: CAS 意外失配时抛出。
        ScheduleRepositoryError: PostgreSQL 返回数据非法时抛出。
    """

    database_now = _clock_now(session)
    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    session.execute(
        text(
            f"UPDATE {_SCHEMA}.job_schedule_occurrences "
            "SET state = :skipped, skip_reason = :reason, updated_at = :updated_at "
            "WHERE tenant_id = :tenant_id AND schedule_id = :schedule_id "
            "AND state = :pending"
        ),
        {
            "skipped": ScheduleOccurrenceState.SKIPPED.value,
            "reason": ScheduleSkipReason.SCHEDULE_DISABLED.value,
            "updated_at": database_now,
            "tenant_id": tenant_value,
            "schedule_id": str(request.schedule_id),
            "pending": ScheduleOccurrenceState.PENDING.value,
        },
    )
    row = session.execute(
        text(
            f"UPDATE {_SCHEMA}.job_schedules AS s "
            "SET state = :disabled, version = s.version + 1, "
            "updated_at = :updated_at "
            "WHERE s.tenant_id = :tenant_id AND s.id = :schedule_id "
            "AND s.version = :expected_version AND s.state = :active "
            f"RETURNING {_SCHEDULE_S_COLS}"
        ),
        {
            "disabled": ScheduleState.DISABLED.value,
            "updated_at": database_now,
            "tenant_id": tenant_value,
            "schedule_id": str(request.schedule_id),
            "expected_version": request.expected_version,
            "active": ScheduleState.ACTIVE.value,
        },
    ).first()
    if row is None:
        raise ScheduleVersionConflictError("schedule_version_conflict")
    return ScheduleStateTransitionResult(
        action=ScheduleStateTransitionAction.APPLIED,
        request=request,
        previous_definition=previous,
        observation=ScheduleObservation(
            definition=_row_definition(row, tenant_id),
            database_now=database_now,
        ),
        activation_next_fire_at=None,
    )


def _begin_pending_materialization(
    session: Session,
    tenant_id: TenantId,
    occurrence: ScheduleOccurrence,
    parent: ScheduleDefinition,
    admission: ScheduleMaterializationAdmission,
) -> ScheduleMaterializationDecision:
    """在线性化锁内处理 PENDING occurrence 的 admission。

    Args:
        session: 已持有 parent 与 occurrence 行锁的事务 Session。
        tenant_id: 当前租户。
        occurrence: 当前 PENDING occurrence。
        parent: 已锁定的父 schedule definition。
        admission: availability/replay 的闭合 admission。

    Returns:
        ENQUEUE 或 UNAVAILABLE materialization decision。

    Raises:
        ScheduleInvariantError: parent、admission 或 conditional DML 不变量非法时抛出。
        ScheduleInputError: 持久化 occurrence 数据不合法时抛出。
    """

    if parent.state is not ScheduleState.ACTIVE:
        raise ScheduleInvariantError("schedule_pending_parent_disabled")
    if admission is ScheduleMaterializationAdmission.COMMITTED_REPLAY:
        raise ScheduleInvariantError("schedule_pending_committed_replay")
    if admission is ScheduleMaterializationAdmission.PENDING_UNAVAILABLE:
        return ScheduleMaterializationDecision(
            action=ScheduleMaterializationAction.UNAVAILABLE,
            occurrence=occurrence,
        )
    updated_at = _clock_now(session)
    updated = session.execute(
        text(
            f"UPDATE {_SCHEMA}.job_schedule_occurrences AS o "
            "SET state = :materializing, updated_at = :updated_at "
            "WHERE o.tenant_id = :tenant_id "
            "AND o.id = :occurrence_id "
            "AND o.schedule_id = :schedule_id "
            "AND o.state = :pending "
            f"RETURNING {_OCCURRENCE_O_COLS}"
        ),
        {
            "materializing": ScheduleOccurrenceState.MATERIALIZING.value,
            "updated_at": updated_at,
            "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
            "occurrence_id": str(occurrence.id),
            "schedule_id": str(occurrence.schedule_id),
            "pending": ScheduleOccurrenceState.PENDING.value,
        },
    ).first()
    if updated is None:
        raise ScheduleInvariantError("schedule_materialization_linearization")
    return ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.ENQUEUE,
        occurrence=_row_occurrence(updated, tenant_id),
    )


def _materialization_decision(
    session: Session,
    tenant_id: TenantId,
    occurrence: ScheduleOccurrence,
    parent_row: _SqlRow,
    admission: ScheduleMaterializationAdmission,
) -> ScheduleMaterializationDecision:
    """按实际持久状态选择 materialization 的闭合 decision。

    Args:
        session: 已持有 parent 与 occurrence 行锁的事务 Session。
        tenant_id: 当前租户。
        occurrence: 锁内 occurrence 投影。
        parent_row: 锁内父 schedule SQL 行；只在 PENDING 路径解码。
        admission: availability/replay 的闭合 admission。

    Returns:
        enqueue/already-enqueued/unavailable/skipped decision。

    Raises:
        ScheduleInvariantError: PENDING 线性化不变量非法时抛出。
        ScheduleInputError: 持久化 occurrence 数据不合法时抛出。
    """

    if occurrence.state is ScheduleOccurrenceState.PENDING:
        return _begin_pending_materialization(
            session,
            tenant_id,
            occurrence,
            _row_definition(parent_row, tenant_id),
            admission,
        )
    if occurrence.state is ScheduleOccurrenceState.MATERIALIZING:
        return ScheduleMaterializationDecision(
            action=ScheduleMaterializationAction.ENQUEUE,
            occurrence=occurrence,
        )
    if occurrence.state is ScheduleOccurrenceState.ENQUEUED:
        return ScheduleMaterializationDecision(
            action=ScheduleMaterializationAction.ALREADY_ENQUEUED,
            occurrence=occurrence,
        )
    return ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.SKIPPED,
        occurrence=occurrence,
    )


def _list_due_statement(cursor: ScheduleDueCursor | None) -> str:
    """构造把 keyset segment 的排序与 limit 下推到索引扫描的 due SQL。

    Args:
        cursor: 可空 process-local due cursor；非空时生成 after/wrap 两段。

    Returns:
        每个 keyset segment 最多物化 ``:limit`` 行的固定 bind SQL。

    Raises:
        无。
    """

    observed = "WITH observed AS MATERIALIZED (SELECT clock_timestamp() AS database_now), "
    due_predicate = (
        "s.tenant_id = :tenant_id AND s.state = :active "
        "AND s.next_fire_at IS NOT NULL "
        "AND s.next_fire_at <= observed.database_now "
    )
    if cursor is None:
        return (
            observed
            + f"due_page AS MATERIALIZED (SELECT {_SCHEDULE_S_COLS}, observed.database_now "
            f"FROM {_SCHEMA}.job_schedules AS s CROSS JOIN observed "
            f"WHERE {due_predicate}"
            "ORDER BY s.next_fire_at, s.id LIMIT :limit) "
            f"SELECT {_SCHEDULE_D_COLS}, d.database_now FROM due_page AS d "
            "ORDER BY d.next_fire_at, d.id"
        )
    cursor_key = "(:cursor_next_fire_at, CAST(:cursor_schedule_id AS uuid))"
    return (
        observed
        + f"after_cursor AS MATERIALIZED (SELECT {_SCHEDULE_S_COLS}, "
        "observed.database_now, 0::integer AS segment "
        f"FROM {_SCHEMA}.job_schedules AS s CROSS JOIN observed "
        f"WHERE {due_predicate}AND (s.next_fire_at, s.id) > {cursor_key} "
        "ORDER BY s.next_fire_at, s.id LIMIT :limit), "
        f"wrapped AS MATERIALIZED (SELECT {_SCHEDULE_S_COLS}, "
        "observed.database_now, 1::integer AS segment "
        f"FROM {_SCHEMA}.job_schedules AS s CROSS JOIN observed "
        f"WHERE {due_predicate}AND (s.next_fire_at, s.id) <= {cursor_key} "
        "ORDER BY s.next_fire_at, s.id LIMIT :limit), "
        "candidates AS (SELECT * FROM after_cursor UNION ALL SELECT * FROM wrapped) "
        f"SELECT {_SCHEDULE_C_COLS}, c.database_now FROM candidates AS c "
        "ORDER BY c.segment, c.next_fire_at, c.id LIMIT :limit"
    )


def _replay_segment(
    *,
    state_parameter: str,
    segment: int,
    keyset_predicate: str,
) -> str:
    """构造一个按 replay index 顺序局部 bounded 的 occurrence segment。

    Args:
        state_parameter: ``materializing`` 或 ``pending`` bind 名称。
        segment: 最外层 priority segment 整数。
        keyset_predicate: 可空、以 ``AND`` 开头的固定 keyset predicate。

    Returns:
        最多物化 ``:limit`` 条宽 occurrence 行的 CTE 查询体。

    Raises:
        无。
    """

    return (
        f"SELECT {_OCCURRENCE_O_COLS}, {segment}::integer AS segment "
        f"FROM {_SCHEMA}.job_schedule_occurrences AS o "
        f"WHERE o.tenant_id = :tenant_id AND o.state = :{state_parameter} "
        f"{keyset_predicate}ORDER BY o.scheduled_for, o.id LIMIT :limit"
    )


def _list_replayable_statement(cursor: ScheduleReplayCursor | None) -> str:
    """构造 priority/keyset segment 均局部 bounded 的 replay SQL。

    Args:
        cursor: 可空 PENDING cursor；非空时生成 after/wrap 两段。

    Returns:
        MATERIALIZING-first 且每个 segment 最多物化 ``:limit`` 行的 SQL。

    Raises:
        无。
    """

    materializing = _replay_segment(
        state_parameter="materializing",
        segment=0,
        keyset_predicate="",
    )
    if cursor is None:
        pending_segments = (
            "pending_page AS MATERIALIZED ("
            + _replay_segment(
                state_parameter="pending",
                segment=1,
                keyset_predicate="",
            )
            + "), candidates AS (SELECT * FROM materializing "
            "UNION ALL SELECT * FROM pending_page)"
        )
    else:
        cursor_key = "(:cursor_scheduled_for, CAST(:cursor_occurrence_id AS uuid))"
        pending_segments = (
            "pending_after AS MATERIALIZED ("
            + _replay_segment(
                state_parameter="pending",
                segment=1,
                keyset_predicate=f"AND (o.scheduled_for, o.id) > {cursor_key} ",
            )
            + "), pending_wrapped AS MATERIALIZED ("
            + _replay_segment(
                state_parameter="pending",
                segment=2,
                keyset_predicate=f"AND (o.scheduled_for, o.id) <= {cursor_key} ",
            )
            + "), candidates AS (SELECT * FROM materializing "
            "UNION ALL SELECT * FROM pending_after "
            "UNION ALL SELECT * FROM pending_wrapped)"
        )
    return (
        "WITH materializing AS MATERIALIZED ("
        + materializing
        + "), "
        + pending_segments
        + ", selected AS MATERIALIZED (SELECT * FROM candidates "
        "ORDER BY segment, scheduled_for, id LIMIT :limit), "
        "summary AS MATERIALIZED (SELECT EXISTS ("
        f"SELECT 1 FROM {_SCHEMA}.job_schedule_occurrences AS p "
        "WHERE p.tenant_id = :tenant_id AND p.state = :pending"
        ") AS pending_exists) "
        f"SELECT {_OCCURRENCE_C_COLS}, summary.pending_exists "
        "FROM summary LEFT JOIN selected AS c ON TRUE "
        "ORDER BY c.segment NULLS LAST, c.scheduled_for, c.id"
    )


class PostgresScheduleStore(ScheduleStoreProtocol):
    """PostgreSQL durable schedule 仓储实现。

    Args:
        session_factory: 平台 SQLAlchemy ``sessionmaker`` 工厂。
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """初始化仓储。

        Args:
            session_factory: 平台 SQLAlchemy ``sessionmaker`` 工厂。

        Returns:
            无。

        Raises:
            无。
        """

        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # 基础事务设施
    # ------------------------------------------------------------------

    def _session(self, scope: TenantScope) -> tuple[Session, TenantId]:
        """开启一个租户隔离的会话事务。

        Args:
            scope: 租户范围。

        Returns:
            ``(session, tenant_id)`` 二元组。

        Raises:
            ScheduleInputError: scope 非法时抛出。
        """

        tenant_id = _validate_scope(scope)
        session = self._session_factory()
        try:
            session.begin()
            _set_tenant_local(session, tenant_id)
        except (ScheduleInputError, ScheduleRepositoryError):
            session.rollback()
            session.close()
            raise
        except Exception:
            session.rollback()
            session.close()
            raise ScheduleRepositoryError("schedule_repository_open") from None
        return session, tenant_id

    # ------------------------------------------------------------------
    # register / get / set_state / list_due
    # ------------------------------------------------------------------

    def register(
        self,
        scope: TenantScope,
        request: ScheduleRegistrationRequest,
    ) -> ScheduleDefinition:
        """注册一个新的 disabled draft schedule definition。

        Args:
            scope: 租户范围。
            request: 注册请求。

        Returns:
            已持久化的 ``ScheduleDefinition``（state=disabled）。

        Raises:
            ScheduleInputError: 请求类型非法时抛出。
            ScheduleVersionConflictError: ``schedule_key`` 已存在时抛出。
            ScheduleRepositoryError: PostgreSQL 操作失败时抛出。
        """

        if not isinstance(request, ScheduleRegistrationRequest):
            raise ScheduleInputError("request 必须是 ScheduleRegistrationRequest")
        session, tenant_id = self._session(scope)
        try:
            transaction_now, _ = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            schedule_id = uuid4()
            row = session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.job_schedules "
                    "(id, tenant_id, schedule_key, descriptor_job_type, "
                    "descriptor_payload_schema_name, descriptor_payload_schema_version, "
                    "descriptor_max_attempts, descriptor_retry_base_seconds, "
                    "descriptor_retry_max_seconds, descriptor_lease_duration_seconds, "
                    "payload_schema_name, payload_schema_version, payload_bytes, "
                    "payload_sha256, cron_expression, timezone_name, misfire_policy, "
                    "misfire_grace_seconds, job_deadline_seconds, state, next_fire_at, "
                    "version, created_at, updated_at) "
                    "VALUES (:id, :tenant_id, :schedule_key, :descriptor_job_type, "
                    ":descriptor_payload_schema_name, :descriptor_payload_schema_version, "
                    ":descriptor_max_attempts, :descriptor_retry_base_seconds, "
                    ":descriptor_retry_max_seconds, :descriptor_lease_duration_seconds, "
                    ":payload_schema_name, :payload_schema_version, :payload_bytes, "
                    ":payload_sha256, :cron_expression, :timezone_name, :misfire_policy, "
                    ":misfire_grace_seconds, :job_deadline_seconds, :state, NULL, "
                    ":version, :created_at, :updated_at) "
                    "ON CONFLICT (tenant_id, schedule_key) DO NOTHING "
                    f"RETURNING {_SCHEDULE_COLS}"
                ),
                {
                    "id": str(schedule_id),
                    "tenant_id": tenant_value,
                    "schedule_key": request.schedule_key,
                    "descriptor_job_type": request.descriptor.job_type,
                    "descriptor_payload_schema_name": request.descriptor.payload_schema_name,
                    "descriptor_payload_schema_version": request.descriptor.payload_schema_version,
                    "descriptor_max_attempts": request.descriptor.max_attempts,
                    "descriptor_retry_base_seconds": request.descriptor.retry_base_seconds,
                    "descriptor_retry_max_seconds": request.descriptor.retry_max_seconds,
                    "descriptor_lease_duration_seconds": request.descriptor.lease_duration_seconds,
                    "payload_schema_name": request.payload.schema_name,
                    "payload_schema_version": request.payload.schema_version,
                    "payload_bytes": request.payload.canonical_bytes,
                    "payload_sha256": request.payload.sha256,
                    "cron_expression": request.cron_expression,
                    "timezone_name": request.timezone_name,
                    "misfire_policy": request.misfire_policy.value,
                    "misfire_grace_seconds": request.misfire_grace_seconds,
                    "job_deadline_seconds": request.job_deadline_seconds,
                    "state": ScheduleState.DISABLED.value,
                    "version": 1,
                    "created_at": transaction_now,
                    "updated_at": transaction_now,
                },
            ).first()
            if row is None:
                raise ScheduleVersionConflictError("schedule_key_conflict")
            definition = _row_definition(row, tenant_id)
            session.commit()
        except (ScheduleVersionConflictError, ScheduleRepositoryError):
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise ScheduleRepositoryError("schedule_repository_register") from None
        finally:
            session.close()
        return definition

    def get(
        self,
        scope: TenantScope,
        schedule_id: UUID,
    ) -> ScheduleObservation | None:
        """按 ``(tenant_id, id)`` 读取 schedule 与同事务 PG 时钟。

        Args:
            scope: 租户范围。
            schedule_id: schedule UUID。

        Returns:
            ``ScheduleObservation``；本租户不存在或跨租户时返回
            ``None``。

        Raises:
            ScheduleInputError: schedule UUID 非法时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """

        _validate_uuid(schedule_id, "schedule_id")
        session, tenant_id = self._session(scope)
        try:
            row = session.execute(
                text(
                    "WITH observed AS MATERIALIZED "
                    "(SELECT clock_timestamp() AS database_now) "
                    f"SELECT {_SCHEDULE_S_COLS}, observed.database_now "
                    f"FROM {_SCHEMA}.job_schedules AS s CROSS JOIN observed "
                    "WHERE s.tenant_id = :tenant_id AND s.id = :schedule_id"
                ),
                {
                    "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                    "schedule_id": str(schedule_id),
                },
            ).first()
            observation = (
                ScheduleObservation(
                    definition=_row_definition(row, tenant_id),
                    database_now=_rv_dt(row, "database_now"),
                )
                if row is not None
                else None
            )
            session.commit()
        except ScheduleRepositoryError:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise ScheduleRepositoryError("schedule_repository_get") from None
        finally:
            session.close()
        return observation

    def get_occurrence(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
    ) -> ScheduleOccurrence | None:
        """按租户读取一条冻结 occurrence。

        Args:
            scope: 租户范围。
            occurrence_id: occurrence UUID。

        Returns:
            本租户完整 occurrence；不存在或跨租户时返回 ``None``。

        Raises:
            ScheduleInputError: occurrence UUID 非法时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """

        _validate_uuid(occurrence_id, "occurrence_id")
        session, tenant_id = self._session(scope)
        try:
            row = session.execute(
                text(
                    f"SELECT {_OCCURRENCE_COLS} "
                    f"FROM {_SCHEMA}.job_schedule_occurrences "
                    "WHERE tenant_id = :tenant_id AND id = :occurrence_id"
                ),
                {
                    "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                    "occurrence_id": str(occurrence_id),
                },
            ).first()
            occurrence = _row_occurrence(row, tenant_id) if row is not None else None
            session.commit()
        except ScheduleRepositoryError:
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise ScheduleRepositoryError("schedule_repository_get_occurrence") from None
        finally:
            session.close()
        return occurrence

    def set_state(
        self,
        scope: TenantScope,
        request: ScheduleActivationRequest,
        *,
        activation_next_fire_at: datetime | None,
    ) -> ScheduleStateTransitionResult:
        """CAS 切换 schedule state 并收敛 occurrence。

        Args:
            scope: 租户范围。
            request: 激活请求（含 expected_version CAS）。
            activation_next_fire_at: ACTIVE candidate；DISABLED/unchanged
                请求必须为 ``None``。

        Returns:
            携带 before/after/PG clock/candidate 的闭合结果。

        Raises:
            ScheduleVersionConflictError: 本租户不存在/跨租户或
                version/state/cursor 已变化时抛出（零 mutation）。
            ScheduleInvariantError: candidate 与 source/target state 矩阵
                不闭合时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """

        if not isinstance(request, ScheduleActivationRequest):
            raise ScheduleInputError("request 必须是 ScheduleActivationRequest")
        session, tenant_id = self._session(scope)
        try:
            schedule_row = _lock_schedule(
                session,
                tenant_id,
                request.schedule_id,
            )
            if schedule_row is None:
                raise ScheduleVersionConflictError("schedule_version_conflict")
            if _rv_int(schedule_row, "version") != request.expected_version:
                raise ScheduleVersionConflictError("schedule_version_conflict")
            previous = _row_definition(schedule_row, tenant_id)
            if previous.state is request.target_state:
                if activation_next_fire_at is not None:
                    raise ScheduleInvariantError("schedule_unchanged_candidate")
                result = ScheduleStateTransitionResult(
                    action=ScheduleStateTransitionAction.UNCHANGED,
                    request=request,
                    previous_definition=previous,
                    observation=ScheduleObservation(
                        definition=previous,
                        database_now=_clock_now(session),
                    ),
                    activation_next_fire_at=None,
                )
            elif request.target_state is ScheduleState.ACTIVE:
                result = _activate_locked_schedule(
                    session,
                    tenant_id,
                    request,
                    previous,
                    _validate_activation_candidate(activation_next_fire_at),
                )
            else:
                if activation_next_fire_at is not None:
                    raise ScheduleInvariantError("schedule_disable_candidate")
                result = _disable_locked_schedule(
                    session,
                    tenant_id,
                    request,
                    previous,
                )
            session.commit()
        except (
            ScheduleInputError,
            ScheduleInvariantError,
            ScheduleRepositoryError,
            ScheduleVersionConflictError,
        ):
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise ScheduleRepositoryError("schedule_repository_set_state") from None
        finally:
            session.close()
        return result

    def list_due(
        self,
        scope: TenantScope,
        cursor: ScheduleDueCursor | None,
        *,
        limit: int,
    ) -> ScheduleDuePage:
        """按 keyset + 无重复 wrap 列出 bounded active due page。

        Args:
            scope: 租户范围。
            cursor: 上一次 due cursor；``None`` 从队头读取。
            limit: keyword-only 行数上限。

        Returns:
            同一 PG clock observation 组成的 ``ScheduleDuePage``。

        Raises:
            ScheduleInputError: cursor/limit 非法时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """

        _validate_limit(limit)
        if cursor is not None and not isinstance(cursor, ScheduleDueCursor):
            raise ScheduleInputError("cursor 必须是 ScheduleDueCursor 或 None")
        session, tenant_id = self._session(scope)
        try:
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            parameters: dict[str, _RowValue] = {
                "tenant_id": tenant_value,
                "active": ScheduleState.ACTIVE.value,
                "limit": limit,
            }
            if cursor is not None:
                parameters["cursor_next_fire_at"] = cursor.next_fire_at
                parameters["cursor_schedule_id"] = str(cursor.schedule_id)
            rows = session.execute(
                text(_list_due_statement(cursor)),
                parameters,
            ).fetchall()
            entries = tuple(
                ScheduleDueEntry(
                    observation=ScheduleObservation(
                        definition=_row_definition(row, tenant_id),
                        database_now=_rv_dt(row, "database_now"),
                    ),
                    cursor_after=ScheduleDueCursor(
                        next_fire_at=_rv_dt(row, "next_fire_at"),
                        schedule_id=_rv_uuid(row, "id"),
                    ),
                )
                for row in rows
            )
            page = ScheduleDuePage(
                entries=entries,
                next_cursor=entries[-1].cursor_after if entries else None,
            )
            session.commit()
        except (ScheduleInputError, ScheduleRepositoryError):
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise ScheduleRepositoryError("schedule_repository_list_due") from None
        finally:
            session.close()
        return page

    def reserve_occurrences(
        self,
        scope: TenantScope,
        batch: ScheduleReservationBatch,
    ) -> ScheduleReservationResult:
        """锁定 schedule 后原子推进 cursor/state 并插入 occurrence batch。

        Args:
            scope: 租户范围。
            batch: Service 已闭合的 1 至 3 条 reservation batch。

        Returns:
            成功时返回持久化 occurrences；CAS 失配时返回
            ``lost_race`` 且事务零修改。

        Raises:
            ScheduleInputError: batch 类型非法时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """

        if not isinstance(batch, ScheduleReservationBatch):
            raise ScheduleInputError("batch 必须是 ScheduleReservationBatch")
        session, tenant_id = self._session(scope)
        try:
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            locked = _lock_schedule(session, tenant_id, batch.schedule_id)
            if (
                locked is None
                or _rv_int(locked, "version") != batch.expected_version
                or _rv_str(locked, "state") != ScheduleState.ACTIVE.value
                or _rv_obj(locked, "next_fire_at") is None
                or _rv_dt(locked, "next_fire_at") != batch.expected_next_fire_at
            ):
                result = ScheduleReservationResult(
                    action=ScheduleReserveAction.LOST_RACE,
                    occurrences=(),
                )
                session.commit()
                return result

            database_now = _clock_now(session)
            updated = session.execute(
                text(
                    f"UPDATE {_SCHEMA}.job_schedules AS s "
                    "SET state = :resulting_state, "
                    "next_fire_at = :resulting_next_fire_at, "
                    "version = s.version + 1, updated_at = :updated_at "
                    "WHERE s.tenant_id = :tenant_id AND s.id = :schedule_id "
                    "AND s.state = :active AND s.version = :expected_version "
                    "AND s.next_fire_at IS NOT DISTINCT FROM :expected_next_fire_at "
                    "RETURNING s.id"
                ),
                {
                    "resulting_state": batch.resulting_state.value,
                    "resulting_next_fire_at": batch.resulting_next_fire_at,
                    "updated_at": database_now,
                    "tenant_id": tenant_value,
                    "schedule_id": str(batch.schedule_id),
                    "active": ScheduleState.ACTIVE.value,
                    "expected_version": batch.expected_version,
                    "expected_next_fire_at": batch.expected_next_fire_at,
                },
            ).first()
            if updated is None:
                session.rollback()
                return ScheduleReservationResult(
                    action=ScheduleReserveAction.LOST_RACE,
                    occurrences=(),
                )

            persisted: list[ScheduleOccurrence] = []
            for reservation in batch.reservations:
                occurrence_id = uuid4()
                snapshot_values = (
                    _snapshot_bind_values(reservation.snapshot)
                    if reservation.snapshot is not None
                    else _null_snapshot_bind_values()
                )
                values: dict[str, _RowValue] = {
                    "id": str(occurrence_id),
                    "tenant_id": tenant_value,
                    "schedule_id": str(batch.schedule_id),
                    "schedule_version": batch.expected_version,
                    "scheduled_for": reservation.scheduled_for,
                    "state": reservation.state.value,
                    "job_run_id": None,
                    "coalesced_count": reservation.coalesced_count,
                    "skip_reason": (reservation.skip_reason.value if reservation.skip_reason is not None else None),
                    "created_at": database_now,
                    "updated_at": database_now,
                }
                values.update(snapshot_values)
                occurrence_row = session.execute(
                    text(
                        f"INSERT INTO {_SCHEMA}.job_schedule_occurrences "
                        "(id, tenant_id, schedule_id, schedule_version, scheduled_for, "
                        "state, snapshot_descriptor_job_type, "
                        "snapshot_descriptor_payload_schema_name, "
                        "snapshot_descriptor_payload_schema_version, "
                        "snapshot_descriptor_max_attempts, "
                        "snapshot_descriptor_retry_base_seconds, "
                        "snapshot_descriptor_retry_max_seconds, "
                        "snapshot_descriptor_lease_duration_seconds, "
                        "snapshot_payload_schema_name, snapshot_payload_schema_version, "
                        "snapshot_payload_bytes, snapshot_payload_sha256, "
                        "snapshot_idempotency_key, snapshot_available_at, "
                        "snapshot_deadline_at, snapshot_request_fingerprint, "
                        "job_run_id, coalesced_count, skip_reason, created_at, updated_at) "
                        "VALUES (:id, :tenant_id, :schedule_id, :schedule_version, "
                        ":scheduled_for, :state, :snapshot_descriptor_job_type, "
                        ":snapshot_descriptor_payload_schema_name, "
                        ":snapshot_descriptor_payload_schema_version, "
                        ":snapshot_descriptor_max_attempts, "
                        ":snapshot_descriptor_retry_base_seconds, "
                        ":snapshot_descriptor_retry_max_seconds, "
                        ":snapshot_descriptor_lease_duration_seconds, "
                        ":snapshot_payload_schema_name, :snapshot_payload_schema_version, "
                        ":snapshot_payload_bytes, :snapshot_payload_sha256, "
                        ":snapshot_idempotency_key, :snapshot_available_at, "
                        ":snapshot_deadline_at, :snapshot_request_fingerprint, "
                        ":job_run_id, :coalesced_count, :skip_reason, "
                        ":created_at, :updated_at) "
                        f"RETURNING {_OCCURRENCE_COLS}"
                    ),
                    values,
                ).one()
                persisted.append(_row_occurrence(occurrence_row, tenant_id))

            if batch.resulting_state is ScheduleState.DISABLED:
                session.execute(
                    text(
                        f"UPDATE {_SCHEMA}.job_schedule_occurrences "
                        "SET state = :skipped, skip_reason = :reason, "
                        "updated_at = :updated_at "
                        "WHERE tenant_id = :tenant_id AND schedule_id = :schedule_id "
                        "AND state = :pending"
                    ),
                    {
                        "skipped": ScheduleOccurrenceState.SKIPPED.value,
                        "reason": ScheduleSkipReason.SCHEDULE_DISABLED.value,
                        "updated_at": database_now,
                        "tenant_id": tenant_value,
                        "schedule_id": str(batch.schedule_id),
                        "pending": ScheduleOccurrenceState.PENDING.value,
                    },
                )
            result = ScheduleReservationResult(
                action=ScheduleReserveAction.RESERVED,
                occurrences=tuple(persisted),
            )
            session.commit()
        except (ScheduleInputError, ScheduleRepositoryError):
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise ScheduleRepositoryError("schedule_repository_reserve") from None
        finally:
            session.close()
        return result

    def list_replayable(
        self,
        scope: TenantScope,
        cursor: ScheduleReplayCursor | None,
        *,
        limit: int,
    ) -> ScheduleReplayPage:
        """列出 MATERIALIZING-first、PENDING-keyset 的 bounded page。

        Args:
            scope: 租户范围。
            cursor: 上一次 PENDING cursor；``None`` 从队头读取。
            limit: keyword-only page 上限。

        Returns:
            页内无重复且 MATERIALIZING 严格在前的 replay page。

        Raises:
            ScheduleInputError: cursor/limit 非法时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """

        _validate_limit(limit)
        if cursor is not None and not isinstance(cursor, ScheduleReplayCursor):
            raise ScheduleInputError("cursor 必须是 ScheduleReplayCursor 或 None")
        session, tenant_id = self._session(scope)
        try:
            parameters: dict[str, _RowValue] = {
                "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                "materializing": ScheduleOccurrenceState.MATERIALIZING.value,
                "pending": ScheduleOccurrenceState.PENDING.value,
                "limit": limit,
            }
            if cursor is not None:
                parameters["cursor_scheduled_for"] = cursor.scheduled_for
                parameters["cursor_occurrence_id"] = str(cursor.occurrence_id)
            rows = session.execute(
                text(_list_replayable_statement(cursor)),
                parameters,
            ).fetchall()
            pending_exists = _rv_bool(rows[0], "pending_exists")
            selected_rows = tuple(row for row in rows if _rv_obj(row, "id") is not None)
            occurrences = tuple(_row_occurrence(row, tenant_id) for row in selected_rows)
            last_pending: ScheduleOccurrence | None = None
            for occurrence in occurrences:
                if occurrence.state is ScheduleOccurrenceState.PENDING:
                    last_pending = occurrence
            if last_pending is not None:
                next_pending_cursor = ScheduleReplayCursor(
                    scheduled_for=last_pending.scheduled_for,
                    occurrence_id=last_pending.id,
                )
            elif pending_exists:
                next_pending_cursor = cursor
            else:
                next_pending_cursor = None
            page = ScheduleReplayPage(
                occurrences=occurrences,
                next_pending_cursor=next_pending_cursor,
            )
            session.commit()
        except (ScheduleInputError, ScheduleRepositoryError):
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise ScheduleRepositoryError("schedule_repository_list_replayable") from None
        finally:
            session.close()
        return page

    def begin_materialization(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
        *,
        admission: ScheduleMaterializationAdmission,
    ) -> ScheduleMaterializationDecision:
        """按实际持久状态线性化 PENDING materialization 或 replay。

        Args:
            scope: 租户范围。
            occurrence_id: 目标 occurrence UUID。
            admission: availability/replay 的闭合 admission。

        Returns:
            enqueue/already_enqueued/unavailable/skipped 闭合 decision。

        Raises:
            ScheduleInputError: UUID/admission 非法时抛出。
            ScheduleInvariantError: PENDING 收到 committed replay、parent
                状态异常或 locator 漂移时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """

        _validate_uuid(occurrence_id, "occurrence_id")
        if not isinstance(admission, ScheduleMaterializationAdmission):
            raise ScheduleInputError("admission 必须是 ScheduleMaterializationAdmission")
        session, tenant_id = self._session(scope)
        try:
            schedule_row, occurrence_row = _lock_occurrence_after_parent(
                session,
                tenant_id,
                occurrence_id,
            )
            occurrence = _row_occurrence(occurrence_row, tenant_id)
            decision = _materialization_decision(
                session,
                tenant_id,
                occurrence,
                schedule_row,
                admission,
            )
            session.commit()
        except (
            ScheduleInputError,
            ScheduleInvariantError,
            ScheduleRepositoryError,
        ):
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise ScheduleRepositoryError("schedule_repository_begin_materialization") from None
        finally:
            session.close()
        return decision

    def mark_enqueued(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
        expected_snapshot_fingerprint: str,
        job_id: UUID,
    ) -> ScheduleMarkEnqueuedResult:
        """只把 MATERIALIZING occurrence 首次绑定为 ENQUEUED。

        Args:
            scope: 租户范围。
            occurrence_id: 目标 occurrence UUID。
            expected_snapshot_fingerprint: begin decision 的冻结 fingerprint。
            job_id: 已由 JobStore 持久化的同租户 job UUID。

        Returns:
            marked/idempotent_replay/skipped_conflict 闭合结果。

        Raises:
            ScheduleInputError: UUID/fingerprint 非法时抛出。
            ScheduleInvariantError: snapshot 漂移、PENDING、或 ENQUEUED
                绑定不同 job 时抛出。
            ScheduleRepositoryError: PostgreSQL 操作或持久数据非法时抛出。
        """

        _validate_uuid(occurrence_id, "occurrence_id")
        _validate_uuid(job_id, "job_id")
        _validate_fingerprint(expected_snapshot_fingerprint)
        session, tenant_id = self._session(scope)
        try:
            _, occurrence_row = _lock_occurrence_after_parent(
                session,
                tenant_id,
                occurrence_id,
            )
            occurrence = _row_occurrence(occurrence_row, tenant_id)
            if occurrence.state is ScheduleOccurrenceState.MATERIALIZING:
                if (
                    occurrence.snapshot is None
                    or occurrence.snapshot.request_fingerprint != expected_snapshot_fingerprint
                ):
                    raise ScheduleInvariantError("schedule_snapshot_fingerprint_drift")
                updated = session.execute(
                    text(
                        f"UPDATE {_SCHEMA}.job_schedule_occurrences AS o "
                        "SET state = :enqueued, job_run_id = :job_id, "
                        "updated_at = :updated_at "
                        "WHERE o.tenant_id = :tenant_id "
                        "AND o.id = :occurrence_id "
                        "AND o.schedule_id = :schedule_id "
                        "AND o.state = :materializing "
                        "AND o.snapshot_request_fingerprint = :fingerprint "
                        f"RETURNING {_OCCURRENCE_O_COLS}"
                    ),
                    {
                        "enqueued": ScheduleOccurrenceState.ENQUEUED.value,
                        "job_id": str(job_id),
                        "updated_at": _clock_now(session),
                        "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                        "occurrence_id": str(occurrence_id),
                        "schedule_id": str(occurrence.schedule_id),
                        "materializing": ScheduleOccurrenceState.MATERIALIZING.value,
                        "fingerprint": expected_snapshot_fingerprint,
                    },
                ).first()
                if updated is None:
                    raise ScheduleInvariantError("schedule_mark_linearization")
                result = ScheduleMarkEnqueuedResult(
                    action=ScheduleMarkEnqueuedAction.MARKED,
                    occurrence=_row_occurrence(updated, tenant_id),
                )
            elif occurrence.state is ScheduleOccurrenceState.ENQUEUED:
                if (
                    occurrence.snapshot is None
                    or occurrence.snapshot.request_fingerprint != expected_snapshot_fingerprint
                    or occurrence.job_id != job_id
                ):
                    raise ScheduleInvariantError("schedule_enqueued_binding_conflict")
                result = ScheduleMarkEnqueuedResult(
                    action=ScheduleMarkEnqueuedAction.IDEMPOTENT_REPLAY,
                    occurrence=occurrence,
                )
            elif occurrence.state is ScheduleOccurrenceState.SKIPPED:
                result = ScheduleMarkEnqueuedResult(
                    action=ScheduleMarkEnqueuedAction.SKIPPED_CONFLICT,
                    occurrence=occurrence,
                )
            else:
                raise ScheduleInvariantError("schedule_mark_pending")
            session.commit()
        except (
            ScheduleInputError,
            ScheduleInvariantError,
            ScheduleRepositoryError,
        ):
            session.rollback()
            raise
        except Exception:
            session.rollback()
            raise ScheduleRepositoryError("schedule_repository_mark_enqueued") from None
        finally:
            session.close()
        return result
