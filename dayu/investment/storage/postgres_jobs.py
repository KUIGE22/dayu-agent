"""PostgreSQL durable job repository 实现（Slice 2.1）。

本模块是 ``JobStoreProtocol`` 的唯一合法实现 owner，把 job/attempt/
lease/receipt/event/correlation 的持久化状态机收敛到真实的 PostgreSQL
16 transaction、RLS、列级 grant 与 trigger 上：

- 每个方法拥有自己的 tenant-scoped 单事务：先 ``SET LOCAL
  app.tenant_id``，所有 clock 决策只取同一事务内的
  ``transaction_timestamp()`` / ``clock_timestamp()``，绝不接受或使用
  Python 本机时间与 caller 时间；
- 所有写入先锁定对应 ``job_runs`` 行（``FOR UPDATE``），再在该行锁期间
  用 job 的原子 ``next_event_sequence`` 生成 event sequence，禁止裸
  ``MAX(sequence_number)+1``；
- 私密租户边界双保险：显式 tenant predicate + RLS；
- 稳定错误消息只含固定 safe code，绝不携带 payload/result/token/DSN/
  SQL/raw exception。

本模块绝不 import ``dayu.host`` / ``dayu.contracts``，不接收 Host
reader / ``RunRecord``，也不接收 descriptor registry。
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import TypeAlias, TypeGuard
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, sessionmaker

from dayu.investment.domain.identifiers import TenantId, TenantScope
from dayu.investment.domain.jobs import (
    AgentRunCorrelation,
    AgentRunCorrelationObservation,
    AgentRunGovernanceCursor,
    AgentRunGovernanceProjection,
    AgentRunGovernanceProjectionPage,
    AgentRunStartAuthorizationAction,
    AgentRunStartAuthorizationDecision,
    AgentRunTerminalReconciliationAction,
    AgentRunTerminalReconciliationDecision,
    AttemptReceiptOutcome,
    AttemptState,
    CanonicalJobDocument,
    CorrelationState,
    GenericAttemptReceiptReason,
    HostRunObservationState,
    JobAttemptReceipt,
    JobCancellationRequest,
    JobClaim,
    JobCompletion,
    JobCorrelationInvariantError,
    JobDeadlineExceededError,
    JobDefinitionState,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobFailure,
    JobGovernanceRequiredError,
    JobHandlerDescriptor,
    JobHeartbeatAction,
    JobHeartbeatResult,
    JobIdempotencyConflictError,
    JobInputError,
    JobLeaseHandle,
    JobLeaseLostError,
    JobNotFoundError,
    JobRecoveryResult,
    JobRepositoryFailureError,
    JobState,
    JobStateConflictError,
    LeaseReleaseReason,
    SafeJobErrorCode,
    build_agent_run_terminal_receipt,
    build_generic_attempt_receipt,
    job_enqueue_request_fingerprint,
    parse_canonical_document,
)
from dayu.investment.storage.db import PLATFORM_SCHEMA_NAME, TENANT_CONTEXT_SETTING
from dayu.investment.storage.protocols import JobStoreProtocol

_SCHEMA = PLATFORM_SCHEMA_NAME

# 各查询统一列序常量（供 helper 索引，避免重组 tuple）。
_DEFINITION_COLS = (
    "id, tenant_id, job_type, payload_schema_name, payload_schema_version, "
    "max_attempts, retry_base_seconds, retry_max_seconds, lease_duration_seconds, "
    "status, created_at, updated_at, version"
)
_JOB_COLS = (
    "id, tenant_id, definition_id, idempotency_key, request_fingerprint, "
    "payload_bytes, payload_sha256, state, available_at, original_available_at, "
    "request_payload_schema_name, request_payload_schema_version, deadline_at, "
    "current_attempt_number, next_event_sequence, cancel_requested_at, cancel_reason, "
    "completed_at, safe_failure_code, created_at, updated_at, version"
)


def _validate_new_enqueue_payload(request: JobEnqueueRequest) -> CanonicalJobDocument:
    """在任何session/fingerprint/SQL前严格验证新入队payload。

    Args:
        request: caller提供的原始入队请求。

    Returns:
        由public canonical parser重新构造且与请求逐字节一致的document。

    Raises:
        JobInputError: request类型、UTF-8、canonical形状或bytes/SHA漂移时抛出。
    """

    if not isinstance(request, JobEnqueueRequest) or not isinstance(
        request.payload,
        CanonicalJobDocument,
    ):
        raise JobInputError("入队payload必须是canonical document")
    raw_bytes = request.payload.canonical_bytes
    try:
        payload_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise JobInputError("payload 必须是严格 canonical JSON") from None
    validated = parse_canonical_document(
        payload_text,
        schema_name=request.payload.schema_name,
        schema_version=request.payload.schema_version,
    )
    if (
        validated.canonical_bytes != raw_bytes
        or validated.sha256 != request.payload.sha256
    ):
        raise JobInputError("payload bytes/SHA identity 不一致")
    return validated
_ATTEMPT_COLS = (
    "id, tenant_id, job_run_id, attempt_number, worker_id, state, fence, "
    "lease_token_sha256, claimed_at, lease_expires_at, last_heartbeat_at, "
    "finished_at, safe_failure_code, created_at, updated_at, version"
)
_LEASE_COLS = (
    "id, tenant_id, job_run_id, attempt_id, fence, token_sha256, acquired_at, "
    "expires_at, released_at, release_reason, created_at, updated_at, version"
)
_RECEIPT_COLS = (
    "id, tenant_id, job_run_id, attempt_id, outcome, result_schema_name, "
    "result_schema_version, result_bytes, result_sha256, receipt_schema_name, "
    "receipt_schema_version, receipt_bytes, receipt_sha256, safe_error_code, "
    "finalized_at, created_at"
)
_CORRELATION_COLS = (
    "id, tenant_id, job_run_id, attempt_id, idempotency_key, reserved_host_run_id, "
    "state, observed_at, last_observation_sha256, created_at, updated_at, version"
)


def _canonical_uuid(value: str, label: str) -> str:
    """校验并返回 canonical UUID 字符串。

    Args:
        value: 待校验的 UUID 字符串。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的小写连字符 UUID 字符串。

    Raises:
        JobInputError: 值不是规范 UUID 时抛出。
    """

    if not isinstance(value, str):
        raise JobInputError(f"{label} 必须是规范 UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise JobInputError(f"{label} 必须是规范 UUID") from None
    if parsed.int == 0:
        raise JobInputError(f"{label} 必须是规范 UUID")
    canonical = str(parsed)
    if canonical != value:
        raise JobInputError(f"{label} 必须是规范 UUID")
    return canonical


def _validate_scope(scope: TenantScope) -> TenantId:
    """校验租户范围并返回租户标识。

    Args:
        scope: 待校验的租户范围。

    Returns:
        租户标识。

    Raises:
        JobInputError: scope 非法时抛出。
    """

    if not isinstance(scope, TenantScope):
        raise JobInputError("scope 必须是 TenantScope")
    _canonical_uuid(scope.tenant_id.value, "租户标识")
    return scope.tenant_id


def _set_tenant_local(session: Session, tenant_id: TenantId) -> None:
    """以 bind parameter 设置租户上下文并读回确认。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。

    Returns:
        无。

    Raises:
        JobRepositoryFailureError: 读回确认不一致时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    result = session.execute(
        text(f"SELECT set_config('{TENANT_CONTEXT_SETTING}', :tenant_id, true)"),
        {"tenant_id": tenant_value},
    )
    if result.scalar() != tenant_value:
        raise JobRepositoryFailureError()


def _clock(session: Session) -> tuple[datetime, datetime]:
    """取同一事务内的 PG 时钟。

    Args:
        session: 当前事务 Session。

    Returns:
        ``(transaction_timestamp, clock_timestamp)`` 二元组（均 aware
        UTC）。

    Raises:
        JobRepositoryFailureError: 查询失败时抛出。
    """

    row = session.execute(text("SELECT transaction_timestamp(), clock_timestamp()")).one()
    transaction_now, clock_now = row
    if not isinstance(transaction_now, datetime) or not isinstance(clock_now, datetime):
        raise JobRepositoryFailureError()
    return _as_aware_utc(transaction_now), _as_aware_utc(clock_now)


def _as_aware_utc(value: _RowValue) -> datetime:
    """把 PG 返回的时间归一化为 aware UTC。

    Args:
        value: PG 时间值。

    Returns:
        aware UTC datetime（naive 值按 UTC 补 tzinfo）。

    Raises:
        JobRepositoryFailureError: 值不是 datetime 时抛出。
    """

    if not isinstance(value, datetime):
        raise JobRepositoryFailureError()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_token(raw_token: str) -> str:
    """计算 raw lease token 的 SHA-256。

    Args:
        raw_token: raw token 字符串。

    Returns:
        小写 64-hex SHA-256。

    Raises:
        无。
    """

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    """生成 256-bit 随机 lease token。

    Args:
        无。

    Returns:
        256-bit 随机值的小写 64-hex。

    Raises:
        无。
    """

    return secrets.token_bytes(32).hex()


def _backoff_seconds(descriptor: JobHandlerDescriptor, attempt_number: int) -> int:
    """计算确定性无 jitter 退避秒数。

    Args:
        descriptor: job descriptor。
        attempt_number: 当前 attempt 序号（从 1 起）。

    Returns:
        ``min(retry_max, retry_base * 2 ** (attempt_number - 1))``。

    Raises:
        无。
    """

    return min(
        descriptor.retry_max_seconds,
        descriptor.retry_base_seconds * (2 ** (attempt_number - 1)),
    )


_RowValue: TypeAlias = str | int | float | bool | datetime | bytes | memoryview | UUID | None
"""原始 SQL 行的 closed 标量值联合（plan §3：禁止 object/Any 逃逸）。"""

_SqlRow: TypeAlias = Row[tuple[_RowValue, ...]]
"""SQLAlchemy raw SQL 行的精确参数化类型。"""

_RowLike: TypeAlias = _SqlRow | Mapping[str, _RowValue]
"""行访问联合类型：SQLAlchemy 行或合成 dict 行。"""


def _rv(row: _RowLike, key: str) -> _RowValue:
    """从行按命名键读取值（类型安全列访问）。

    Args:
        row: SQLAlchemy 查询行或合成 dict 行。
        key: 列名。

    Returns:
        该列的 closed 标量值（调用方以 ``str``/``int``/``bytes`` 等收窄）。

    Raises:
        KeyError: 列不存在时抛出。
    """

    if isinstance(row, Row):
        return row._mapping[key]
    return row[key]


def _rv_str(row: _RowLike, key: str) -> str:
    """读取命名列的字符串值（接受 str/UUID）。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        字符串值。

    Raises:
        JobRepositoryFailureError: 值不是 str/UUID 时抛出。
    """

    value = _rv(row, key)
    if isinstance(value, str):
        return value
    if isinstance(value, UUID):
        return str(value)
    raise JobRepositoryFailureError()


def _rv_int(row: _RowLike, key: str) -> int:
    """读取命名列的整数值。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        整数值。

    Raises:
        JobRepositoryFailureError: 值不是整数时抛出。
    """

    value = _rv(row, key)
    if type(value) is not int:
        raise JobRepositoryFailureError()
    return value


def _rv_bytes(row: _RowLike, key: str) -> bytes:
    """读取命名列的 bytes 值。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        bytes 值。

    Raises:
        JobRepositoryFailureError: 值不是 bytes 时抛出。
    """

    value = _rv(row, key)
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise JobRepositoryFailureError()
    return bytes(value)


def _rv_dt(row: _RowLike, key: str) -> datetime:
    """读取命名列的 aware UTC 时间值。

    Args:
        row: 查询行或合成行。
        key: 列名。

    Returns:
        aware UTC datetime。

    Raises:
        JobRepositoryFailureError: 值不是时间时抛出。
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
        JobRepositoryFailureError: 值不是 UUID 时抛出。
    """

    value = _rv(row, key)
    if not isinstance(value, UUID):
        raise JobRepositoryFailureError()
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


def _row_definition(row: _RowLike) -> JobHandlerDescriptor:
    """把 definition 行映射为 descriptor。

    Args:
        row: definition 查询行。

    Returns:
        ``JobHandlerDescriptor``。

    Raises:
        JobRepositoryFailureError: 值非法时抛出。
    """

    return JobHandlerDescriptor(
        job_type=_rv_str(row, "job_type"),
        payload_schema_name=_rv_str(row, "payload_schema_name"),
        payload_schema_version=_rv_int(row, "payload_schema_version"),
        max_attempts=_rv_int(row, "max_attempts"),
        retry_base_seconds=_rv_int(row, "retry_base_seconds"),
        retry_max_seconds=_rv_int(row, "retry_max_seconds"),
        lease_duration_seconds=_rv_int(row, "lease_duration_seconds"),
    )


def _row_receipt(row: _RowLike) -> JobAttemptReceipt:
    """把 receipt 行映射为 ``JobAttemptReceipt``。

    Args:
        row: receipt 查询行。

    Returns:
        ``JobAttemptReceipt``。

    Raises:
        JobRepositoryFailureError: 行值违反不变量时抛出。
    """

    result: CanonicalJobDocument | None = None
    if _rv_obj(row, "result_bytes") is not None:
        result = CanonicalJobDocument(
            schema_name=_rv_str(row, "result_schema_name"),
            schema_version=_rv_int(row, "result_schema_version"),
            canonical_bytes=_rv_bytes(row, "result_bytes"),
            sha256=_rv_str(row, "result_sha256"),
        )
    receipt_document = CanonicalJobDocument(
        schema_name=_rv_str(row, "receipt_schema_name"),
        schema_version=_rv_int(row, "receipt_schema_version"),
        canonical_bytes=_rv_bytes(row, "receipt_bytes"),
        sha256=_rv_str(row, "receipt_sha256"),
    )
    return JobAttemptReceipt(
        tenant_id=TenantId(_rv_str(row, "tenant_id")),
        job_id=_rv_uuid(row, "job_run_id"),
        attempt_id=_rv_uuid(row, "attempt_id"),
        outcome=AttemptReceiptOutcome(_rv_str(row, "outcome")),
        result=result,
        receipt=receipt_document,
        safe_error_code=(
            SafeJobErrorCode(_rv_str(row, "safe_error_code")) if _rv_obj(row, "safe_error_code") is not None else None
        ),
        finalized_at=_rv_dt(row, "finalized_at"),
    )


def _row_correlation(row: _RowLike) -> AgentRunCorrelation:
    """把 correlation 行映射为 ``AgentRunCorrelation``。

    Args:
        row: correlation 查询行。

    Returns:
        ``AgentRunCorrelation``。

    Raises:
        JobCorrelationInvariantError: 行值违反不变量时抛出。
        JobRepositoryFailureError: 值类型非法时抛出。
    """

    try:
        correlation = AgentRunCorrelation(
            id=_rv_uuid(row, "id"),
            tenant_id=TenantId(_rv_str(row, "tenant_id")),
            job_id=_rv_uuid(row, "job_run_id"),
            attempt_id=_rv_uuid(row, "attempt_id"),
            idempotency_key=_rv_str(row, "idempotency_key"),
            reserved_host_run_id=_rv_str(row, "reserved_host_run_id"),
            state=CorrelationState(_rv_str(row, "state")),
            observed_at=(_rv_dt(row, "observed_at") if _rv_obj(row, "observed_at") is not None else None),
            last_observation_sha256=(
                _rv_str(row, "last_observation_sha256") if _rv_obj(row, "last_observation_sha256") is not None else None
            ),
            created_at=_rv_dt(row, "created_at"),
            updated_at=_rv_dt(row, "updated_at"),
            version=_rv_int(row, "version"),
        )
    except (ValueError, TypeError) as exc:
        raise JobCorrelationInvariantError() from exc
    return correlation


class _LockedJobAttempt:
    """一个已锁定的 job+attempt+lease 组合的工作状态。

    Args:
        job_row: ``job_runs`` 行。
        attempt_row: ``job_attempts`` 行。
        lease_row: ``job_leases`` 行。
        definition: job 的 immutable descriptor。
        payload: job 的 canonical payload。
    """

    __slots__ = ("job_row", "attempt_row", "lease_row", "definition", "payload")

    def __init__(
        self,
        *,
        job_row: _RowLike,
        attempt_row: _RowLike,
        lease_row: _RowLike,
        definition: JobHandlerDescriptor,
        payload: CanonicalJobDocument,
    ) -> None:
        """初始化组合工作状态。

        Args:
            job_row: 已锁定的 ``job_runs`` 行。
            attempt_row: 已锁定的 ``job_attempts`` 行。
            lease_row: 已锁定的 ``job_leases`` 行。
            definition: job 的 immutable descriptor。
            payload: job 的 canonical payload。

        Returns:
            无。

        Raises:
            无。
        """

        self.job_row = job_row
        self.attempt_row = attempt_row
        self.lease_row = lease_row
        self.definition = definition
        self.payload = payload


class PostgresJobStore(JobStoreProtocol):
    """PostgreSQL durable job 仓储实现。

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
    # 基础事务与 event 基础设施
    # ------------------------------------------------------------------

    def _session(self, scope: TenantScope) -> tuple[Session, TenantId]:
        """开启一个租户隔离的会话事务。

        Args:
            scope: 租户范围。

        Returns:
            ``(session, tenant_id)`` 二元组。

        Raises:
            JobInputError: scope 非法时抛出。
        """

        tenant_id = _validate_scope(scope)
        session = self._session_factory()
        session.begin()
        _set_tenant_local(session, tenant_id)
        return session, tenant_id

    def _commit_and_close(self, session: Session) -> None:
        """提交并关闭事务会话。

        Args:
            session: 当前事务 Session。

        Returns:
            无。

        Raises:
            JobRepositoryFailureError: 提交失败时抛出（不泄漏 cause）。
        """

        try:
            session.commit()
        except Exception:
            session.rollback()
            raise JobRepositoryFailureError() from None
        finally:
            session.close()

    def _rollback_and_close(self, session: Session) -> None:
        """回滚并关闭事务会话。

        Args:
            session: 当前事务 Session。

        Returns:
            无。

        Raises:
            无。
        """

        try:
            session.rollback()
        finally:
            session.close()

    def _insert_event(
        self,
        session: Session,
        *,
        tenant_id: TenantId,
        job_id: UUID,
        attempt_id: UUID | None,
        event_type: str,
        transaction_now: datetime,
    ) -> None:
        """在已锁定 ``job_runs`` 行的前提下写入一个 job event。

        以锁定行上的原子 ``next_event_sequence`` 递增生成 sequence，
        禁止裸 ``MAX(sequence_number)+1``。

        Args:
            session: 当前事务 Session。
            tenant_id: 租户标识。
            job_id: 目标 job UUID。
            attempt_id: 可空关联 attempt UUID。
            event_type: 事件类型。
            transaction_now: 同一事务的 transaction_timestamp。

        Returns:
            无。

        Raises:
            JobRepositoryFailureError: 更新/插入失败时抛出。
        """

        tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
        job_value = str(job_id)
        attempt_value = str(attempt_id) if attempt_id is not None else None
        row = session.execute(
            text(
                f"UPDATE {_SCHEMA}.job_runs "
                "SET next_event_sequence = next_event_sequence + 1, "
                "updated_at = :updated_at, version = version + 1 "
                "WHERE tenant_id = :tenant_id AND id = :job_id "
                "RETURNING next_event_sequence"
            ),
            {
                "tenant_id": tenant_value,
                "job_id": job_value,
                "updated_at": transaction_now,
            },
        ).one()
        sequence = int(row[0]) - 1
        session.execute(
            text(
                f"INSERT INTO {_SCHEMA}.job_events "
                "(id, tenant_id, job_run_id, attempt_id, sequence_number, event_type, "
                "occurred_at, created_at) "
                "VALUES (:id, :tenant_id, :job_run_id, :attempt_id, :sequence_number, "
                ":event_type, :occurred_at, :created_at)"
            ),
            {
                "id": str(uuid4()),
                "tenant_id": tenant_value,
                "job_run_id": job_value,
                "attempt_id": attempt_value,
                "sequence_number": sequence,
                "event_type": event_type,
                "occurred_at": transaction_now,
                "created_at": transaction_now,
            },
        )

    def _lock_job_row(
        self,
        session: Session,
        *,
        tenant_id: TenantId,
        job_id: UUID,
    ) -> Mapping[str, _RowValue] | None:
        """以显式 tenant predicate 锁定单行 ``job_runs``。

        Args:
            session: 当前事务 Session。
            tenant_id: 租户标识。
            job_id: 目标 job UUID。

        Returns:
            ``job_runs`` 行的 mapping 投影；不存在时返回 ``None``。

        Raises:
            JobRepositoryFailureError: 查询失败时抛出。
        """

        row = session.execute(
            text(
                f"SELECT {_JOB_COLS} FROM {_SCHEMA}.job_runs WHERE tenant_id = :tenant_id AND id = :job_id FOR UPDATE"
            ),
            {
                "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                "job_id": str(job_id),
            },
        ).first()
        return dict(row._mapping) if row is not None else None

    def _correlation_exists_locked(
        self,
        session: Session,
        tenant_id: TenantId,
        job_id: UUID,
        attempt_id: UUID,
    ) -> bool:
        """在已锁定 job/attempt/lease 后，同事务 late lock/re-read 该
        attempt 是否已有已提交 correlation，并验证跨 job 身份闭合。

        锁定 correlation 后必须验证其 ``job_run_id`` 与当前锁定的
        ``job_id`` 一致；跨 job 同 tenant 的 identity 漂移一律 closed
        invariant（绝不静默按 governance/generic 处理）。

        Args:
            session: 当前事务 Session。
            tenant_id: 租户标识。
            job_id: 当前锁定的 job UUID。
            attempt_id: 目标 attempt UUID。

        Returns:
            存在且身份闭合的 correlation row 时返回 ``True``（该
            attempt 归 governance 所有，generic 终结入口必须零
            mutation 拒绝）。

        Raises:
            JobCorrelationInvariantError: correlation 的 job_run_id 与
                当前 job 不一致时抛出。
            JobRepositoryFailureError: 查询失败时抛出。
        """

        row = session.execute(
            text(
                f"SELECT {_CORRELATION_COLS} FROM {_SCHEMA}.agent_run_correlations "
                "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
                "FOR UPDATE"
            ),
            {
                "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                "attempt_id": str(attempt_id),
            },
        ).first()
        if row is None:
            return False
        if _rv_uuid(row, "job_run_id") != job_id:
            raise JobCorrelationInvariantError()
        return True

    # ------------------------------------------------------------------
    # enqueue
    # ------------------------------------------------------------------

    def enqueue(
        self,
        scope: TenantScope,
        request: JobEnqueueRequest,
    ) -> JobEnqueueReceipt:
        """入队一个已通过 Service registry gate 的 job。

        Args:
            scope: 租户范围。
            request: 已验证的入队请求。

        Returns:
            入队收据。

        Raises:
            JobIdempotencyConflictError: 同 key 不同 fingerprint 时抛出。
            JobStateConflictError: definition 为 disabled 时抛出。
            JobInputError: 输入非法时抛出。
        """

        validated_payload = _validate_new_enqueue_payload(request)
        session, tenant_id = self._session(scope)
        try:
            transaction_now, _ = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            descriptor = request.descriptor
            definition_row = session.execute(
                text(
                    f"SELECT {_DEFINITION_COLS} FROM {_SCHEMA}.job_definitions "
                    "WHERE tenant_id = :tenant_id AND job_type = :job_type"
                ),
                {
                    "tenant_id": tenant_value,
                    "job_type": descriptor.job_type,
                },
            ).first()
            if definition_row is None:
                definition_id = uuid4()
                session.execute(
                    text(
                        f"INSERT INTO {_SCHEMA}.job_definitions "
                        "(id, tenant_id, job_type, payload_schema_name, "
                        "payload_schema_version, max_attempts, retry_base_seconds, "
                        "retry_max_seconds, lease_duration_seconds, status, "
                        "created_at, updated_at, version) "
                        "VALUES (:id, :tenant_id, :job_type, :payload_schema_name, "
                        ":payload_schema_version, :max_attempts, :retry_base_seconds, "
                        ":retry_max_seconds, :lease_duration_seconds, :status, "
                        ":created_at, :updated_at, :version) "
                        "ON CONFLICT (tenant_id, job_type) DO NOTHING"
                    ),
                    {
                        "id": str(definition_id),
                        "tenant_id": tenant_value,
                        "job_type": descriptor.job_type,
                        "payload_schema_name": descriptor.payload_schema_name,
                        "payload_schema_version": descriptor.payload_schema_version,
                        "max_attempts": descriptor.max_attempts,
                        "retry_base_seconds": descriptor.retry_base_seconds,
                        "retry_max_seconds": descriptor.retry_max_seconds,
                        "lease_duration_seconds": descriptor.lease_duration_seconds,
                        "status": JobDefinitionState.ACTIVE.value,
                        "created_at": transaction_now,
                        "updated_at": transaction_now,
                        "version": 1,
                    },
                )
                # 竞态收敛：冲突（另一 writer 已提交同 job_type definition）时
                # DO NOTHING 后再读既有行，走与既有行一致的校验路径。
                definition_row = session.execute(
                    text(
                        f"SELECT {_DEFINITION_COLS} FROM {_SCHEMA}.job_definitions "
                        "WHERE tenant_id = :tenant_id AND job_type = :job_type"
                    ),
                    {
                        "tenant_id": tenant_value,
                        "job_type": descriptor.job_type,
                    },
                ).one()
            current_definition = _row_definition(definition_row)
            if current_definition != descriptor:
                raise JobStateConflictError("definition 与既存 immutable 配置不一致")
            if _rv_obj(definition_row, "status") == JobDefinitionState.DISABLED.value:
                raise JobStateConflictError("definition 已禁用")
            definition_id = _rv_uuid(definition_row, "id")

            fingerprint = job_enqueue_request_fingerprint(request)
            existing = session.execute(
                text(
                    f"SELECT {_JOB_COLS} FROM {_SCHEMA}.job_runs "
                    "WHERE tenant_id = :tenant_id AND definition_id = :definition_id "
                    "AND idempotency_key = :idempotency_key"
                ),
                {
                    "tenant_id": tenant_value,
                    "definition_id": str(definition_id),
                    "idempotency_key": request.idempotency_key,
                },
            ).first()
            if existing is not None:
                if _rv_str(existing, "request_fingerprint") != fingerprint:
                    raise JobIdempotencyConflictError()
                receipt = JobEnqueueReceipt(
                    tenant_id=tenant_id,
                    definition_id=definition_id,
                    job_id=_rv_uuid(existing, "id"),
                    state=JobState.READY,
                    idempotency_reused=True,
                )
                self._commit_and_close(session)
                return receipt

            job_id = uuid4()
            inserted = session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.job_runs "
                    "(id, tenant_id, definition_id, idempotency_key, request_fingerprint, "
                    "payload_bytes, payload_sha256, state, available_at, original_available_at, "
                    "request_payload_schema_name, request_payload_schema_version, deadline_at, "
                    "current_attempt_number, next_event_sequence, created_at, "
                    "updated_at, version) "
                    "VALUES (:id, :tenant_id, :definition_id, :idempotency_key, "
                    ":request_fingerprint, :payload_bytes, :payload_sha256, :state, "
                    ":available_at, :original_available_at, :request_payload_schema_name, "
                    ":request_payload_schema_version, :deadline_at, :current_attempt_number, "
                    ":next_event_sequence, :created_at, :updated_at, :version) "
                    "ON CONFLICT (tenant_id, definition_id, idempotency_key) "
                    "DO NOTHING RETURNING id"
                ),
                {
                    "id": str(job_id),
                    "tenant_id": tenant_value,
                    "definition_id": str(definition_id),
                    "idempotency_key": request.idempotency_key,
                    "request_fingerprint": fingerprint,
                    "payload_bytes": validated_payload.canonical_bytes,
                    "payload_sha256": validated_payload.sha256,
                    "state": JobState.READY.value,
                    "available_at": request.available_at,
                    "original_available_at": request.available_at,
                    "request_payload_schema_name": validated_payload.schema_name,
                    "request_payload_schema_version": validated_payload.schema_version,
                    "deadline_at": request.deadline_at,
                    "current_attempt_number": 0,
                    "next_event_sequence": 1,
                    "created_at": transaction_now,
                    "updated_at": transaction_now,
                    "version": 1,
                },
            ).first()
            if inserted is None:
                # 同 key 并发冲突：数据库原子 DO NOTHING 保证不泄漏
                # unique violation；在同一事务内重读既有行并比较完整
                # fingerprint，相同请求返回同一 job（idempotency_reused），
                # 不同请求抛 closed 冲突。
                conflicted = session.execute(
                    text(
                        f"SELECT {_JOB_COLS} FROM {_SCHEMA}.job_runs "
                        "WHERE tenant_id = :tenant_id AND definition_id = :definition_id "
                        "AND idempotency_key = :idempotency_key"
                    ),
                    {
                        "tenant_id": tenant_value,
                        "definition_id": str(definition_id),
                        "idempotency_key": request.idempotency_key,
                    },
                ).one()
                if _rv_str(conflicted, "request_fingerprint") != fingerprint:
                    raise JobIdempotencyConflictError()
                receipt = JobEnqueueReceipt(
                    tenant_id=tenant_id,
                    definition_id=definition_id,
                    job_id=_rv_uuid(conflicted, "id"),
                    state=JobState.READY,
                    idempotency_reused=True,
                )
                self._commit_and_close(session)
                return receipt
            locked = session.execute(
                text(
                    f"SELECT {_JOB_COLS} FROM {_SCHEMA}.job_runs "
                    "WHERE tenant_id = :tenant_id AND id = :job_id FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "job_id": str(job_id),
                },
            ).one()
            del locked
            self._insert_event(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=None,
                event_type="job_created",
                transaction_now=transaction_now,
            )
            self._commit_and_close(session)
        except (JobIdempotencyConflictError, JobStateConflictError):
            self._rollback_and_close(session)
            raise
        except Exception:
            self._rollback_and_close(session)
            raise
        return JobEnqueueReceipt(
            tenant_id=tenant_id,
            definition_id=definition_id,
            job_id=job_id,
            state=JobState.READY,
            idempotency_reused=False,
        )

    def _mark_expired_ready_jobs(
        self,
        session: Session,
        *,
        tenant_id: TenantId,
        tenant_value: str,
        clock_now: datetime,
        transaction_now: datetime,
    ) -> None:
        """把 deadline 已到的 ready job 标记为 failed（单 deadline event）。

        该路径不创建 attempt、lease 或 receipt；job 已非 ready 的重放
        不追加 event。每行先以 ``FOR UPDATE SKIP LOCKED`` 锁定，再在
        行锁期间以原子 ``next_event_sequence`` 写唯一 event。

        Args:
            session: 当前事务 Session。
            tenant_id: 租户标识。
            tenant_value: canonical tenant UUID 字符串。
            clock_now: PG clock_timestamp。
            transaction_now: PG transaction_timestamp。

        Returns:
            无。

        Raises:
            JobRepositoryFailureError: 更新失败时抛出。
        """

        rows = session.execute(
            text(
                f"SELECT {_JOB_COLS} FROM {_SCHEMA}.job_runs "
                "WHERE tenant_id = :tenant_id AND state = :state "
                "AND deadline_at <= :clock_now "
                "FOR UPDATE SKIP LOCKED"
            ),
            {
                "tenant_id": tenant_value,
                "state": JobState.READY.value,
                "clock_now": clock_now,
            },
        ).fetchall()
        for row in rows:
            job_id = _rv_uuid(row, "id")
            session.execute(
                text(
                    f"UPDATE {_SCHEMA}.job_runs "
                    "SET state = :state, safe_failure_code = :safe_failure_code, "
                    "completed_at = :completed_at, updated_at = :updated_at, "
                    "version = version + 1 "
                    "WHERE tenant_id = :tenant_id AND id = :job_id AND state = :ready_state"
                ),
                {
                    "state": JobState.FAILED.value,
                    "safe_failure_code": SafeJobErrorCode.DEADLINE_EXCEEDED.value,
                    "completed_at": clock_now,
                    "updated_at": transaction_now,
                    "tenant_id": tenant_value,
                    "job_id": str(job_id),
                    "ready_state": JobState.READY.value,
                },
            )
            self._insert_event(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=None,
                event_type="job_deadline_exceeded",
                transaction_now=transaction_now,
            )

    # ------------------------------------------------------------------
    # claim / heartbeat
    # ------------------------------------------------------------------

    def claim(
        self,
        scope: TenantScope,
        worker_id: str,
    ) -> JobClaim | None:
        """以 SKIP LOCKED 领取一个 ready job。

        Args:
            scope: 租户范围。
            worker_id: worker 标识。

        Returns:
            ``JobClaim``；无可用 job 时返回 ``None``。

        Raises:
            JobInputError: worker_id 非法时抛出。
        """

        _canonical_worker_id(worker_id)
        session, tenant_id = self._session(scope)
        try:
            transaction_now, clock_now = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            self._mark_expired_ready_jobs(
                session,
                tenant_id=tenant_id,
                tenant_value=tenant_value,
                clock_now=clock_now,
                transaction_now=transaction_now,
            )
            job_row = session.execute(
                text(
                    f"SELECT {_JOB_COLS} FROM {_SCHEMA}.job_runs "
                    "WHERE tenant_id = :tenant_id AND state = :state "
                    "AND available_at <= :clock_now AND deadline_at > :clock_now "
                    "ORDER BY available_at, id "
                    "FOR UPDATE SKIP LOCKED LIMIT 1"
                ),
                {
                    "tenant_id": tenant_value,
                    "state": JobState.READY.value,
                    "clock_now": clock_now,
                },
            ).first()
            if job_row is None:
                self._commit_and_close(session)
                return None

            job_id = _rv_uuid(job_row, "id")
            definition_row = session.execute(
                text(
                    f"SELECT {_DEFINITION_COLS} FROM {_SCHEMA}.job_definitions "
                    "WHERE tenant_id = :tenant_id AND id = :definition_id"
                ),
                {
                    "tenant_id": tenant_value,
                    "definition_id": _rv_str(job_row, "definition_id"),
                },
            ).one()
            descriptor = _row_definition(definition_row)
            attempt_number = _rv_int(job_row, "current_attempt_number") + 1
            fence = attempt_number
            attempt_id = uuid4()
            lease_id = uuid4()
            raw_token = _new_token()
            token_sha256 = _hash_token(raw_token)
            # claim 的 lease expiry 取完整 lease_duration（不钳到 deadline），
            # 使 deadline 分支可被有效 lease 的 holder 命中（§4.2.2/4.2.3）。
            lease_expires_at = clock_now + timedelta(seconds=descriptor.lease_duration_seconds)
            session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.job_attempts "
                    "(id, tenant_id, job_run_id, attempt_number, worker_id, state, fence, "
                    "lease_token_sha256, claimed_at, lease_expires_at, created_at, "
                    "updated_at, version) "
                    "VALUES (:id, :tenant_id, :job_run_id, :attempt_number, :worker_id, "
                    ":state, :fence, :lease_token_sha256, :claimed_at, "
                    ":lease_expires_at, :created_at, :updated_at, :version)"
                ),
                {
                    "id": str(attempt_id),
                    "tenant_id": tenant_value,
                    "job_run_id": str(job_id),
                    "attempt_number": attempt_number,
                    "worker_id": worker_id,
                    "state": AttemptState.LEASED.value,
                    "fence": fence,
                    "lease_token_sha256": token_sha256,
                    "claimed_at": clock_now,
                    "lease_expires_at": lease_expires_at,
                    "created_at": transaction_now,
                    "updated_at": transaction_now,
                    "version": 1,
                },
            )
            session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.job_leases "
                    "(id, tenant_id, job_run_id, attempt_id, fence, token_sha256, "
                    "acquired_at, expires_at, created_at, updated_at, version) "
                    "VALUES (:id, :tenant_id, :job_run_id, :attempt_id, :fence, "
                    ":token_sha256, :acquired_at, :expires_at, :created_at, "
                    ":updated_at, :version)"
                ),
                {
                    "id": str(lease_id),
                    "tenant_id": tenant_value,
                    "job_run_id": str(job_id),
                    "attempt_id": str(attempt_id),
                    "fence": fence,
                    "token_sha256": token_sha256,
                    "acquired_at": clock_now,
                    "expires_at": lease_expires_at,
                    "created_at": transaction_now,
                    "updated_at": transaction_now,
                    "version": 1,
                },
            )
            session.execute(
                text(
                    f"UPDATE {_SCHEMA}.job_runs "
                    "SET state = :state, current_attempt_number = :attempt_number, "
                    "updated_at = :updated_at, version = version + 1 "
                    "WHERE tenant_id = :tenant_id AND id = :job_id"
                ),
                {
                    "state": JobState.LEASED.value,
                    "attempt_number": attempt_number,
                    "updated_at": transaction_now,
                    "tenant_id": tenant_value,
                    "job_id": str(job_id),
                },
            )
            self._insert_event(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                event_type="job_claimed",
                transaction_now=transaction_now,
            )
            self._commit_and_close(session)
        except Exception:
            self._rollback_and_close(session)
            raise
        payload = _payload_document(
            schema_name=_rv_str(job_row, "request_payload_schema_name"),
            schema_version=_rv_int(job_row, "request_payload_schema_version"),
            canonical_bytes=_rv_bytes(job_row, "payload_bytes"),
            sha256=_rv_str(job_row, "payload_sha256"),
        )
        lease = JobLeaseHandle(
            tenant_id=tenant_id,
            job_id=job_id,
            attempt_id=attempt_id,
            fence=fence,
            raw_token=raw_token,
            acquired_at=clock_now,
            expires_at=lease_expires_at,
        )
        return JobClaim(
            tenant_id=tenant_id,
            definition_id=_rv_uuid(job_row, "definition_id"),
            job_id=job_id,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            worker_id=worker_id,
            descriptor=descriptor,
            payload=payload,
            lease=lease,
            deadline_at=_rv_dt(job_row, "deadline_at"),
        )

    def heartbeat(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
    ) -> JobHeartbeatResult:
        """续约有效 lease 并返回闭合 heartbeat 结果（Slice 2.2）。

        先按统一锁序锁定 job/attempt/lease，再做同事务 late correlation
        re-read（不能用锁前“未发现”缓存）。发现未终结 correlation 时：
        固定 ``new_expiry = database_clock_now + lease_duration_seconds``，
        cancel/deadline 未到返回 ``renewed``、已到返回
        ``governance_required``，两者都只续约同一 lease/fence；generic
        job 保持 Slice 2.1 的 cancel/deadline 异常语义并返回 ``renewed``。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。

        Returns:
            续约后的 ``JobHeartbeatResult``（action + claim）。

        Raises:
            JobLeaseLostError: lease 失效或 fence/token 不匹配时抛出。
            JobStateConflictError: generic job 已有 cancel intent 时抛出。
            JobDeadlineExceededError: generic job 已到 deadline 且已
                收敛 failed 时抛出。
        """

        session, tenant_id = self._session(scope)
        try:
            transaction_now, clock_now = _clock(session)
            locked = _lock_job_attempt_lease(session, tenant_id, lease, clock_now)
            if locked is None:
                raise JobLeaseLostError()
            job_id = _rv_uuid(locked.job_row, "id")
            correlation_row = session.execute(
                text(
                    f"SELECT {_CORRELATION_COLS} FROM {_SCHEMA}.agent_run_correlations "
                    "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
                    "FOR UPDATE"
                ),
                {
                    "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                    "attempt_id": str(lease.attempt_id),
                },
            ).first()
            if correlation_row is not None:
                if _rv_uuid(correlation_row, "job_run_id") != job_id:
                    raise JobCorrelationInvariantError()
                # 未终结 correlation：续满 lease_duration，cancel/deadline
                # 由 Worker 经 governance/reobserve 收敛，绝不在 heartbeat
                # generic terminalize。
                cancel_requested = _rv_obj(locked.job_row, "cancel_requested_at") is not None
                deadline_reached = clock_now >= _rv_dt(locked.job_row, "deadline_at")
                new_expiry = clock_now + timedelta(seconds=locked.definition.lease_duration_seconds)
                session.execute(
                    text(
                        f"UPDATE {_SCHEMA}.job_attempts "
                        "SET lease_expires_at = :lease_expires_at, "
                        "last_heartbeat_at = :last_heartbeat_at, "
                        "updated_at = :updated_at, version = version + 1 "
                        "WHERE tenant_id = :tenant_id AND id = :attempt_id "
                        "AND fence = :fence"
                    ),
                    {
                        "lease_expires_at": new_expiry,
                        "last_heartbeat_at": clock_now,
                        "updated_at": transaction_now,
                        "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                        "attempt_id": str(lease.attempt_id),
                        "fence": lease.fence,
                    },
                )
                self._insert_event(
                    session,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    attempt_id=lease.attempt_id,
                    event_type="job_heartbeat",
                    transaction_now=transaction_now,
                )
                self._commit_and_close(session)
                action = (
                    JobHeartbeatAction.GOVERNANCE_REQUIRED
                    if cancel_requested or deadline_reached
                    else JobHeartbeatAction.RENEWED
                )
                return JobHeartbeatResult(
                    action=action,
                    claim=_build_claim(
                        tenant_id=tenant_id,
                        job_row=locked.job_row,
                        attempt_row=locked.attempt_row,
                        definition=locked.definition,
                        payload=locked.payload,
                        raw_token=lease.raw_token,
                        new_expires_at=new_expiry,
                    ),
                )
            if _rv_obj(locked.job_row, "cancel_requested_at") is not None:
                raise JobStateConflictError()
            deadline = _rv_dt(locked.job_row, "deadline_at")
            if clock_now >= deadline:
                _terminalize_deadline(
                    session,
                    tenant_id=tenant_id,
                    locked=locked,
                    transaction_now=transaction_now,
                    clock_now=clock_now,
                )
                self._commit_and_close(session)
                raise JobDeadlineExceededError()
            new_expiry = min(
                clock_now + timedelta(seconds=locked.definition.lease_duration_seconds),
                deadline,
            )
            if not new_expiry > clock_now:
                _terminalize_deadline(
                    session,
                    tenant_id=tenant_id,
                    locked=locked,
                    transaction_now=transaction_now,
                    clock_now=clock_now,
                )
                self._commit_and_close(session)
                raise JobDeadlineExceededError()
            session.execute(
                text(
                    f"UPDATE {_SCHEMA}.job_attempts "
                    "SET lease_expires_at = :lease_expires_at, "
                    "last_heartbeat_at = :last_heartbeat_at, "
                    "updated_at = :updated_at, version = version + 1 "
                    "WHERE tenant_id = :tenant_id AND id = :attempt_id "
                    "AND fence = :fence"
                ),
                {
                    "lease_expires_at": new_expiry,
                    "last_heartbeat_at": clock_now,
                    "updated_at": transaction_now,
                    "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                    "attempt_id": str(lease.attempt_id),
                    "fence": lease.fence,
                },
            )
            self._insert_event(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=lease.attempt_id,
                event_type="job_heartbeat",
                transaction_now=transaction_now,
            )
            self._commit_and_close(session)
        except (JobLeaseLostError, JobStateConflictError, JobDeadlineExceededError):
            self._rollback_and_close(session)
            raise
        except Exception:
            self._rollback_and_close(session)
            raise
        return JobHeartbeatResult(
            action=JobHeartbeatAction.RENEWED,
            claim=_build_claim(
                tenant_id=tenant_id,
                job_row=locked.job_row,
                attempt_row=locked.attempt_row,
                definition=locked.definition,
                payload=locked.payload,
                raw_token=lease.raw_token,
                new_expires_at=new_expiry,
            ),
        )

    def complete(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        completion: JobCompletion,
    ) -> JobAttemptReceipt:
        """以有效 lease 正常完成 job。

        固定判定顺序：cancel intent -> deadline -> success；存在未终结
        correlation 时零 mutation 拒绝并转 governance。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。
            completion: 完成结果。

        Returns:
            immutable attempt receipt。

        Raises:
            JobLeaseLostError: lease 失效时抛出。
            JobDeadlineExceededError: 无 cancel intent 但已到 deadline 时抛出。
            JobGovernanceRequiredError: 存在未终结 correlation 时零
                mutation 抛出（Worker 转 governance/reobserve）。
        """

        session, tenant_id = self._session(scope)
        try:
            transaction_now, clock_now = _clock(session)
            locked = _lock_job_attempt_lease(session, tenant_id, lease, clock_now)
            if locked is None:
                raise JobLeaseLostError()
            job_id = _rv_uuid(locked.job_row, "id")
            attempt_id = _rv_uuid(locked.attempt_row, "id")
            if self._correlation_exists_locked(session, tenant_id, job_id, attempt_id):
                # 未终结 correlation：零 mutation 拒绝 generic 终结，由
                # Worker 转 governance/reobserve，绝不写第二 receipt。
                raise JobGovernanceRequiredError()
            if _rv_obj(locked.job_row, "cancel_requested_at") is not None:
                receipt = _converge_cancel_intent(
                    session,
                    tenant_id=tenant_id,
                    locked=locked,
                    transaction_now=transaction_now,
                    clock_now=clock_now,
                )
                self._commit_and_close(session)
                return receipt
            if clock_now >= _rv_dt(locked.job_row, "deadline_at"):
                _terminalize_deadline(
                    session,
                    tenant_id=tenant_id,
                    locked=locked,
                    transaction_now=transaction_now,
                    clock_now=clock_now,
                )
                self._commit_and_close(session)
                raise JobDeadlineExceededError()
            receipt_document = build_generic_attempt_receipt(
                job_id=job_id,
                attempt_id=attempt_id,
                outcome=AttemptReceiptOutcome.SUCCEEDED,
                reason=GenericAttemptReceiptReason.COMPLETION,
                safe_error_code=None,
                result_ref=completion.result,
            )
            receipt = _build_attempt_receipt(
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                outcome=AttemptReceiptOutcome.SUCCEEDED,
                result=completion.result,
                safe_error_code=None,
                finalized_at=clock_now,
                receipt_document=receipt_document,
            )
            _persist_receipt(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                receipt=receipt,
                transaction_now=transaction_now,
            )
            _write_job_terminal_state(
                session,
                tenant_id=tenant_id,
                locked=locked,
                job_state=JobState.SUCCEEDED,
                attempt_state=AttemptState.SUCCEEDED,
                safe_failure_code=None,
                completed_at=clock_now,
                transaction_now=transaction_now,
                lease_reason=LeaseReleaseReason.COMPLETION,
            )
            self._insert_event(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                event_type="job_completed",
                transaction_now=transaction_now,
            )
            self._commit_and_close(session)
        except (JobLeaseLostError, JobDeadlineExceededError):
            self._rollback_and_close(session)
            raise
        except Exception:
            self._rollback_and_close(session)
            raise
        return receipt

    def fail(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        failure: JobFailure,
    ) -> JobRecoveryResult:
        """以有效 lease 声明安全失败。

        存在未终结 correlation 时零 mutation 拒绝并转 governance。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。
            failure: 安全失败声明。

        Returns:
            收敛后的 recovery 结果。

        Raises:
            JobLeaseLostError: lease 失效时抛出。
            JobGovernanceRequiredError: 存在未终结 correlation 时零
                mutation 抛出（Worker 转 governance/reobserve）。
        """

        session, tenant_id = self._session(scope)
        try:
            transaction_now, clock_now = _clock(session)
            locked = _lock_job_attempt_lease(session, tenant_id, lease, clock_now)
            if locked is None:
                raise JobLeaseLostError()
            job_id = _rv_uuid(locked.job_row, "id")
            attempt_id = _rv_uuid(locked.attempt_row, "id")
            if self._correlation_exists_locked(session, tenant_id, job_id, attempt_id):
                # 未终结 correlation：零 mutation 拒绝 generic 终结，由
                # Worker 转 governance/reobserve，绝不写第二 receipt。
                raise JobGovernanceRequiredError()
            if _rv_obj(locked.job_row, "cancel_requested_at") is not None:
                receipt = _converge_cancel_intent(
                    session,
                    tenant_id=tenant_id,
                    locked=locked,
                    transaction_now=transaction_now,
                    clock_now=clock_now,
                )
                self._commit_and_close(session)
                return JobRecoveryResult(
                    job_id=job_id,
                    attempt_id=attempt_id,
                    job_state=JobState.CANCELLED,
                    attempt_state=AttemptState.CANCELLED,
                    receipt=receipt,
                    next_available_at=None,
                    safe_error_code=SafeJobErrorCode.CANCELLED,
                )
            attempt_number = _rv_int(locked.attempt_row, "attempt_number")
            deadline = _rv_dt(locked.job_row, "deadline_at")
            if clock_now >= deadline:
                receipt = _terminalize_deadline(
                    session,
                    tenant_id=tenant_id,
                    locked=locked,
                    transaction_now=transaction_now,
                    clock_now=clock_now,
                )
                self._commit_and_close(session)
                return JobRecoveryResult(
                    job_id=job_id,
                    attempt_id=attempt_id,
                    job_state=JobState.FAILED,
                    attempt_state=AttemptState.FAILED,
                    receipt=receipt,
                    next_available_at=None,
                    safe_error_code=SafeJobErrorCode.DEADLINE_EXCEEDED,
                )
            next_available_at = clock_now + timedelta(seconds=_backoff_seconds(locked.definition, attempt_number))
            retryable = (
                failure.retryable and attempt_number < locked.definition.max_attempts and next_available_at < deadline
            )
            if retryable:
                receipt = _persist_receipt(
                    session,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    attempt_id=attempt_id,
                    receipt=_build_attempt_receipt(
                        tenant_id=tenant_id,
                        job_id=job_id,
                        attempt_id=attempt_id,
                        outcome=AttemptReceiptOutcome.FAILED,
                        result=None,
                        safe_error_code=failure.safe_error_code,
                        finalized_at=clock_now,
                        receipt_document=build_generic_attempt_receipt(
                            job_id=job_id,
                            attempt_id=attempt_id,
                            outcome=AttemptReceiptOutcome.FAILED,
                            reason=GenericAttemptReceiptReason.FAILURE,
                            safe_error_code=failure.safe_error_code,
                            result_ref=None,
                        ),
                    ),
                    transaction_now=transaction_now,
                )
                _mark_attempt_failed_retry(
                    session,
                    tenant_id=tenant_id,
                    locked=locked,
                    safe_failure_code=failure.safe_error_code,
                    next_available_at=next_available_at,
                    transaction_now=transaction_now,
                )
                self._insert_event(
                    session,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    attempt_id=attempt_id,
                    event_type="job_retry_scheduled",
                    transaction_now=transaction_now,
                )
                self._commit_and_close(session)
                return JobRecoveryResult(
                    job_id=job_id,
                    attempt_id=attempt_id,
                    job_state=JobState.READY,
                    attempt_state=AttemptState.FAILED,
                    receipt=receipt,
                    next_available_at=next_available_at,
                    safe_error_code=failure.safe_error_code,
                )
            terminal_code = (
                SafeJobErrorCode.RETRY_EXHAUSTED
                if attempt_number >= locked.definition.max_attempts
                else failure.safe_error_code
            )
            receipt = _persist_receipt(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                receipt=_build_attempt_receipt(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    attempt_id=attempt_id,
                    outcome=AttemptReceiptOutcome.FAILED,
                    result=None,
                    safe_error_code=terminal_code,
                    finalized_at=clock_now,
                    receipt_document=build_generic_attempt_receipt(
                        job_id=job_id,
                        attempt_id=attempt_id,
                        outcome=AttemptReceiptOutcome.FAILED,
                        reason=GenericAttemptReceiptReason.FAILURE,
                        safe_error_code=terminal_code,
                        result_ref=None,
                    ),
                ),
                transaction_now=transaction_now,
            )
            _write_job_terminal_state(
                session,
                tenant_id=tenant_id,
                locked=locked,
                job_state=JobState.FAILED,
                attempt_state=AttemptState.FAILED,
                safe_failure_code=terminal_code,
                completed_at=clock_now,
                transaction_now=transaction_now,
                lease_reason=LeaseReleaseReason.FAILURE,
            )
            self._insert_event(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                event_type="job_failed",
                transaction_now=transaction_now,
            )
            self._commit_and_close(session)
        except JobLeaseLostError:
            self._rollback_and_close(session)
            raise
        except Exception:
            self._rollback_and_close(session)
            raise
        return JobRecoveryResult(
            job_id=job_id,
            attempt_id=attempt_id,
            job_state=JobState.FAILED,
            attempt_state=AttemptState.FAILED,
            receipt=receipt,
            next_available_at=None,
            safe_error_code=terminal_code,
        )

    def cancel(
        self,
        scope: TenantScope,
        request: JobCancellationRequest,
    ) -> JobRecoveryResult:
        """请求取消一个 job。

        Args:
            scope: 租户范围。
            request: 取消请求。

        Returns:
            收敛后的 recovery 结果。
        """

        session, tenant_id = self._session(scope)
        try:
            transaction_now, clock_now = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            job_row = self._lock_job_row(session, tenant_id=tenant_id, job_id=request.job_id)
            if job_row is None:
                raise JobNotFoundError()
            job_id = _rv_uuid(job_row, "id")
            current_state = JobState(_rv_str(job_row, "state"))
            attempt_id = _existing_attempt_id(session, tenant_id=tenant_id, job_id=job_id)
            if current_state in (JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED):
                receipt = (
                    _existing_receipt(session, tenant_id=tenant_id, attempt_id=attempt_id)
                    if attempt_id is not None
                    else None
                )
                attempt_state = (
                    _existing_attempt_state(session, tenant_id=tenant_id, job_id=job_id)
                    if attempt_id is not None
                    else None
                )
                self._commit_and_close(session)
                return JobRecoveryResult(
                    job_id=job_id,
                    attempt_id=attempt_id,
                    job_state=current_state,
                    attempt_state=attempt_state,
                    receipt=receipt,
                    next_available_at=None,
                    safe_error_code=(
                        SafeJobErrorCode.CANCELLED
                        if current_state is JobState.CANCELLED
                        else SafeJobErrorCode(_rv_str(job_row, "safe_failure_code"))
                        if _rv_obj(job_row, "safe_failure_code") is not None
                        else None
                    ),
                )
            if current_state is JobState.READY:
                session.execute(
                    text(
                        f"UPDATE {_SCHEMA}.job_runs "
                        "SET state = :state, cancel_requested_at = :cancel_requested_at, "
                        "cancel_reason = :cancel_reason, completed_at = :completed_at, "
                        "updated_at = :updated_at, version = version + 1 "
                        "WHERE tenant_id = :tenant_id AND id = :job_id"
                    ),
                    {
                        "state": JobState.CANCELLED.value,
                        "cancel_requested_at": clock_now,
                        "cancel_reason": request.reason,
                        "completed_at": clock_now,
                        "updated_at": transaction_now,
                        "tenant_id": tenant_value,
                        "job_id": str(job_id),
                    },
                )
                self._insert_event(
                    session,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    attempt_id=None,
                    event_type="job_cancelled",
                    transaction_now=transaction_now,
                )
                self._commit_and_close(session)
                return JobRecoveryResult(
                    job_id=job_id,
                    attempt_id=None,
                    job_state=JobState.CANCELLED,
                    attempt_state=None,
                    receipt=None,
                    next_available_at=None,
                    safe_error_code=None,
                )
            if current_state is JobState.LEASED:
                session.execute(
                    text(
                        f"UPDATE {_SCHEMA}.job_runs "
                        "SET state = :state, cancel_requested_at = :cancel_requested_at, "
                        "cancel_reason = :cancel_reason, updated_at = :updated_at, "
                        "version = version + 1 "
                        "WHERE tenant_id = :tenant_id AND id = :job_id"
                    ),
                    {
                        "state": JobState.CANCEL_REQUESTED.value,
                        "cancel_requested_at": clock_now,
                        "cancel_reason": request.reason,
                        "updated_at": transaction_now,
                        "tenant_id": tenant_value,
                        "job_id": str(job_id),
                    },
                )
                self._insert_event(
                    session,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    attempt_id=None,
                    event_type="job_cancel_requested",
                    transaction_now=transaction_now,
                )
                self._commit_and_close(session)
                return JobRecoveryResult(
                    job_id=job_id,
                    attempt_id=attempt_id,
                    job_state=JobState.CANCEL_REQUESTED,
                    attempt_state=AttemptState.LEASED,
                    receipt=None,
                    next_available_at=None,
                    safe_error_code=None,
                )
            # 已 cancel_requested：重复 cancel 返回同一状态。
            self._commit_and_close(session)
            return JobRecoveryResult(
                job_id=job_id,
                attempt_id=attempt_id,
                job_state=JobState.CANCEL_REQUESTED,
                attempt_state=AttemptState.LEASED,
                receipt=None,
                next_available_at=None,
                safe_error_code=None,
            )
        except JobNotFoundError:
            self._rollback_and_close(session)
            raise
        except Exception:
            self._rollback_and_close(session)
            raise

    # ------------------------------------------------------------------
    # recover
    # ------------------------------------------------------------------

    def recover(
        self,
        scope: TenantScope,
    ) -> tuple[JobRecoveryResult, ...]:
        """收敛所有从未提交 correlation 的过期 leased/cancel_requested attempt。

        Args:
            scope: 租户范围。

        Returns:
            按 ``(job_id ASC, attempt_id ASC)`` 排序的 recovery 结果 tuple。
        """

        session, tenant_id = self._session(scope)
        results: list[JobRecoveryResult] = []
        try:
            transaction_now, clock_now = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            # 第一条 statement：无锁候选过滤（NOT EXISTS correlation 只当
            # 候选过滤，不是授权真源；READ COMMITTED 下它基于本条
            # statement 的快照）。父行锁在下一段按统一顺序显式获取。
            rows = session.execute(
                text(
                    f"SELECT {_alias_columns('a', _ATTEMPT_COLS)}, "
                    f"{_alias_columns('j', _JOB_COLS)}, "
                    f"{_alias_columns('d', _DEFINITION_COLS)} "
                    f"FROM {_SCHEMA}.job_attempts a "
                    f"JOIN {_SCHEMA}.job_runs j ON j.tenant_id = a.tenant_id "
                    "AND j.id = a.job_run_id "
                    f"JOIN {_SCHEMA}.job_definitions d ON d.tenant_id = j.tenant_id "
                    "AND d.id = j.definition_id "
                    f"JOIN {_SCHEMA}.job_leases l ON l.tenant_id = a.tenant_id "
                    "AND l.attempt_id = a.id AND l.fence = a.fence "
                    "WHERE a.tenant_id = :tenant_id AND a.state = :attempt_state "
                    "AND j.state IN (:job_leased, :job_cancel_requested) "
                    "AND a.lease_expires_at <= :clock_now "
                    "AND NOT EXISTS ("
                    f"  SELECT 1 FROM {_SCHEMA}.agent_run_correlations c "
                    "  WHERE c.tenant_id = a.tenant_id AND c.attempt_id = a.id"
                    ") "
                    "ORDER BY j.id, a.id"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_state": AttemptState.LEASED.value,
                    "job_leased": JobState.LEASED.value,
                    "job_cancel_requested": JobState.CANCEL_REQUESTED.value,
                    "clock_now": clock_now,
                },
            ).fetchall()
            for row in rows:
                job_id = _rv_uuid(row, "j_id")
                attempt_id = _rv_uuid(row, "a_id")
                # 统一锁序：job_runs -> job_attempts -> job_leases（显式
                # 逐行 SKIP LOCKED，保持既有“跳过其它事务持锁行”语义）。
                job_row = session.execute(
                    text(
                        f"SELECT {_JOB_COLS} FROM {_SCHEMA}.job_runs "
                        "WHERE tenant_id = :tenant_id AND id = :job_id "
                        "FOR UPDATE SKIP LOCKED"
                    ),
                    {
                        "tenant_id": tenant_value,
                        "job_id": str(job_id),
                    },
                ).first()
                if not _generic_recovery_job_is_eligible(job_row):
                    continue
                attempt_row = session.execute(
                    text(
                        f"SELECT {_ATTEMPT_COLS} FROM {_SCHEMA}.job_attempts "
                        "WHERE tenant_id = :tenant_id AND id = :attempt_id "
                        "AND job_run_id = :job_id "
                        "FOR UPDATE SKIP LOCKED"
                    ),
                    {
                        "tenant_id": tenant_value,
                        "attempt_id": str(attempt_id),
                        "job_id": str(job_id),
                    },
                ).first()
                if attempt_row is None or _rv_str(attempt_row, "state") != AttemptState.LEASED.value:
                    continue
                if _rv_dt(attempt_row, "lease_expires_at") > clock_now:
                    continue
                lease_row = session.execute(
                    text(
                        f"SELECT {_LEASE_COLS} FROM {_SCHEMA}.job_leases "
                        "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
                        "AND job_run_id = :job_id AND fence = :fence "
                        "FOR UPDATE SKIP LOCKED"
                    ),
                    {
                        "tenant_id": tenant_value,
                        "attempt_id": str(attempt_id),
                        "job_id": str(job_id),
                        "fence": _rv_int(attempt_row, "fence"),
                    },
                ).first()
                if lease_row is None or _rv_obj(lease_row, "released_at") is not None:
                    continue
                definition_row = session.execute(
                    text(
                        f"SELECT {_DEFINITION_COLS} FROM {_SCHEMA}.job_definitions "
                        "WHERE tenant_id = :tenant_id AND id = :definition_id"
                    ),
                    {
                        "tenant_id": tenant_value,
                        "definition_id": _rv_str(job_row, "definition_id"),
                    },
                ).first()
                if definition_row is None:
                    continue
                # 第二条独立 statement：取得刷新后的 statement snapshot 并
                # late lock/re-read correlation；任一已提交 correlation 即
                # 跳过该候选且零 mutation（reserve 先赢则 generic 转
                # governance-required/skip）。correlation 的 job_run_id
                # 必须与候选 job 身份闭合，漂移一律 closed invariant。
                correlation_row = session.execute(
                    text(
                        f"SELECT {_CORRELATION_COLS} FROM {_SCHEMA}.agent_run_correlations "
                        "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
                        "FOR UPDATE"
                    ),
                    {
                        "tenant_id": tenant_value,
                        "attempt_id": str(attempt_id),
                    },
                ).first()
                if _generic_recovery_is_blocked_by_correlation(
                    correlation_row,
                    job_id=job_id,
                ):
                    continue
                locked = _build_locked_from_rows(
                    tenant_id=tenant_id,
                    job_row=job_row,
                    attempt_row=attempt_row,
                    lease_row=lease_row,
                    definition=_row_definition(definition_row),
                    payload=_payload_document(
                        schema_name=_rv_str(job_row, "request_payload_schema_name"),
                        schema_version=_rv_int(job_row, "request_payload_schema_version"),
                        canonical_bytes=_rv_bytes(job_row, "payload_bytes"),
                        sha256=_rv_str(job_row, "payload_sha256"),
                    ),
                )
                result = _recover_one_attempt(
                    session,
                    tenant_id=tenant_id,
                    locked=locked,
                    transaction_now=transaction_now,
                    clock_now=clock_now,
                )
                if result is not None:
                    results.append(result)
            self._commit_and_close(session)
        except Exception:
            self._rollback_and_close(session)
            raise
        results.sort(key=lambda result: (str(result.job_id), str(result.attempt_id)))
        return tuple(results)

    def reserve_agent_run_correlation(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
    ) -> AgentRunCorrelation:
        """在独立 PG 事务中保留一个 agent run correlation（Transaction 2）。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。

        Returns:
            已持久化的 ``AgentRunCorrelation``。

        Raises:
            JobLeaseLostError: lease/attempt/job 状态不匹配时抛出。
            JobStateConflictError: job 已有 cancel intent 时抛出。
            JobDeadlineExceededError: 已到 deadline 时抛出。
            JobCorrelationInvariantError: 已存在 correlation 身份不一致时抛出。
        """

        session, tenant_id = self._session(scope)
        try:
            transaction_now, clock_now = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            if lease.tenant_id != tenant_id:
                raise JobLeaseLostError()
            job_id = lease.job_id
            attempt_id = lease.attempt_id
            job_row = self._lock_job_row(session, tenant_id=tenant_id, job_id=job_id)
            if job_row is None:
                raise JobLeaseLostError()
            if _rv_str(job_row, "state") not in (
                JobState.LEASED.value,
                JobState.CANCEL_REQUESTED.value,
            ):
                raise JobLeaseLostError()
            if _rv_obj(job_row, "cancel_requested_at") is not None:
                raise JobStateConflictError()
            if clock_now >= _rv_dt(job_row, "deadline_at"):
                raise JobDeadlineExceededError()
            attempt_row = session.execute(
                text(
                    f"SELECT {_ATTEMPT_COLS} FROM {_SCHEMA}.job_attempts "
                    "WHERE tenant_id = :tenant_id AND id = :attempt_id "
                    "AND job_run_id = :job_id "
                    "AND fence = :fence AND lease_token_sha256 = :token_sha256 "
                    "FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(attempt_id),
                    "job_id": str(job_id),
                    "fence": lease.fence,
                    "token_sha256": _hash_token(lease.raw_token),
                },
            ).first()
            if attempt_row is None or _rv_obj(attempt_row, "state") != AttemptState.LEASED.value:
                raise JobLeaseLostError()
            if _rv_int(job_row, "current_attempt_number") != _rv_int(attempt_row, "attempt_number"):
                raise JobLeaseLostError()
            lease_row = session.execute(
                text(
                    f"SELECT {_LEASE_COLS} FROM {_SCHEMA}.job_leases "
                    "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
                    "AND job_run_id = :job_id "
                    "AND fence = :fence AND token_sha256 = :token_sha256 "
                    "FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(attempt_id),
                    "job_id": str(job_id),
                    "fence": lease.fence,
                    "token_sha256": _hash_token(lease.raw_token),
                },
            ).first()
            if lease_row is None or _rv_obj(lease_row, "released_at") is not None:
                raise JobLeaseLostError()
            if _rv_dt(attempt_row, "lease_expires_at") <= clock_now:
                raise JobLeaseLostError()
            existing = session.execute(
                text(
                    f"SELECT {_CORRELATION_COLS} FROM {_SCHEMA}.agent_run_correlations "
                    "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
                    "FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(attempt_id),
                },
            ).first()
            if existing is not None:
                existing_correlation = _row_correlation(existing)
                expected_id = f"run_{attempt_id.hex}"
                if (
                    existing_correlation.job_id != job_id
                    or existing_correlation.idempotency_key != _rv_str(job_row, "idempotency_key")
                    or existing_correlation.reserved_host_run_id != expected_id
                ):
                    raise JobCorrelationInvariantError()
                self._commit_and_close(session)
                return existing_correlation
            correlation_id = uuid4()
            session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.agent_run_correlations "
                    "(id, tenant_id, job_run_id, attempt_id, idempotency_key, "
                    "reserved_host_run_id, state, created_at, updated_at, version) "
                    "VALUES (:id, :tenant_id, :job_run_id, :attempt_id, "
                    ":idempotency_key, :reserved_host_run_id, :state, :created_at, "
                    ":updated_at, :version)"
                ),
                {
                    "id": str(correlation_id),
                    "tenant_id": tenant_value,
                    "job_run_id": str(job_id),
                    "attempt_id": str(attempt_id),
                    "idempotency_key": _rv_str(job_row, "idempotency_key"),
                    "reserved_host_run_id": f"run_{attempt_id.hex}",
                    "state": CorrelationState.RESERVED.value,
                    "created_at": transaction_now,
                    "updated_at": transaction_now,
                    "version": 1,
                },
            )
            self._insert_event(
                session,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                event_type="correlation_reserved",
                transaction_now=transaction_now,
            )
            # 在 commit 前以已知 canonical 字段构造 DTO；绝不在此后复用
            # 已 close 的 session（否则 SQLAlchemy 会静默开第二事务泄漏）。
            correlation = AgentRunCorrelation(
                id=correlation_id,
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                idempotency_key=_rv_str(job_row, "idempotency_key"),
                reserved_host_run_id=f"run_{attempt_id.hex}",
                state=CorrelationState.RESERVED,
                observed_at=None,
                last_observation_sha256=None,
                created_at=transaction_now,
                updated_at=transaction_now,
                version=1,
            )
            self._commit_and_close(session)
        except (JobLeaseLostError, JobStateConflictError, JobDeadlineExceededError, JobCorrelationInvariantError):
            self._rollback_and_close(session)
            raise
        except Exception:
            self._rollback_and_close(session)
            raise
        return correlation

    def get_agent_run_correlation(
        self,
        scope: TenantScope,
        correlation_id: UUID,
    ) -> AgentRunCorrelation:
        """按 ``(tenant_id, id)`` 精确读取 correlation。

        Args:
            scope: 租户范围。
            correlation_id: correlation UUID。

        Returns:
            完整 immutable identity/state/version 投影。

        Raises:
            JobNotFoundError: 本租户不存在或跨租户时抛出。
            JobCorrelationInvariantError: 读到的 row 违反不变量时抛出。
        """

        session, tenant_id = self._session(scope)
        try:
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            row = session.execute(
                text(
                    f"SELECT {_CORRELATION_COLS} FROM {_SCHEMA}.agent_run_correlations "
                    "WHERE tenant_id = :tenant_id AND id = :correlation_id"
                ),
                {
                    "tenant_id": tenant_value,
                    "correlation_id": str(correlation_id),
                },
            ).first()
            if row is None:
                raise JobNotFoundError()
            correlation = _row_correlation(row)
            attempt_row = session.execute(
                text(
                    f"SELECT {_ATTEMPT_COLS} FROM {_SCHEMA}.job_attempts "
                    "WHERE tenant_id = :tenant_id AND id = :attempt_id"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(correlation.attempt_id),
                },
            ).first()
            if attempt_row is None:
                raise JobCorrelationInvariantError()
            if (
                _rv_str(attempt_row, "job_run_id") != str(correlation.job_id)
                or f"run_{correlation.attempt_id.hex}" != correlation.reserved_host_run_id
            ):
                raise JobCorrelationInvariantError()
            self._commit_and_close(session)
        except (JobNotFoundError, JobCorrelationInvariantError):
            self._rollback_and_close(session)
            raise
        except Exception:
            self._rollback_and_close(session)
            raise
        return correlation

    def list_expired_agent_run_correlations(
        self,
        scope: TenantScope,
    ) -> tuple[AgentRunCorrelation, ...]:
        """列出已提交 correlation 且绑定 attempt lease 已过期的 correlation。

        Args:
            scope: 租户范围。

        Returns:
            按 ``(created_at ASC, id ASC)`` 排序的 correlation tuple。
        """

        session, tenant_id = self._session(scope)
        try:
            rows = session.execute(
                text(
                    f"SELECT {_prefixed_columns('c', _CORRELATION_COLS)} "
                    f"FROM {_SCHEMA}.agent_run_correlations c "
                    f"JOIN {_SCHEMA}.job_attempts a "
                    "ON a.tenant_id = c.tenant_id AND a.id = c.attempt_id "
                    "WHERE c.tenant_id = :tenant_id AND a.state = :attempt_state "
                    "AND a.lease_expires_at <= clock_timestamp() "
                    "ORDER BY c.created_at, c.id"
                ),
                {
                    "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
                    "attempt_state": AttemptState.LEASED.value,
                },
            ).fetchall()
            self._commit_and_close(session)
        except Exception:
            self._rollback_and_close(session)
            raise
        return tuple(_row_correlation(row) for row in rows)

    def list_governable_agent_runs(
        self,
        scope: TenantScope,
        cursor: AgentRunGovernanceCursor | None,
        *,
        limit: int,
    ) -> AgentRunGovernanceProjectionPage:
        """列出全部未终结 correlation 的 governance join projection。

        覆盖 lease 有效/过期的全部未终结 correlation（RESERVED /
        HOST_CREATED / HOST_RUNNING），以 PG clock/tenant join 收窄；
        固定 ``ORDER BY deadline_at ASC, correlation_id ASC`` 与同 tuple
        keyset。deadline/cancel truth 全部来自 PG 持久化列与同一事务
        PG clock，绝不使用 worker wall clock、``correlation.updated_at``
        或进程启动时间。

        Args:
            scope: 租户范围。
            cursor: 上一页 keyset cursor；从头开始时为 ``None``。
            limit: 本页行数上限（精确来自 settings governance
                page_size，调用方必须显式传 keyword-only）。

        Returns:
            本页 projection 与下一页 cursor（已到尾部时为 ``None``）。

        Raises:
            JobInputError: limit 不是正整数时抛出。
        """

        if type(limit) is not int or limit <= 0:
            raise JobInputError("limit 必须是正整数")
        if cursor is not None and not isinstance(cursor, AgentRunGovernanceCursor):
            raise JobInputError("cursor 必须是 AgentRunGovernanceCursor 或 None")
        session, tenant_id = self._session(scope)
        try:
            _, clock_now = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            statement_params: dict[str, _RowValue] = {
                "tenant_id": tenant_value,
                "state_reserved": CorrelationState.RESERVED.value,
                "state_host_created": CorrelationState.HOST_CREATED.value,
                "state_host_running": CorrelationState.HOST_RUNNING.value,
                "limit": limit,
            }
            keyset_clause = ""
            if cursor is not None:
                keyset_clause = "AND (j.deadline_at, c.id) > (:cursor_deadline, :cursor_id)"
                statement_params["cursor_deadline"] = cursor.deadline_at
                statement_params["cursor_id"] = str(cursor.correlation_id)
            rows = session.execute(
                text(
                    f"SELECT {_alias_columns('c', _CORRELATION_COLS)}, "
                    f"{_alias_columns('j', _JOB_COLS)}, "
                    f"{_alias_columns('a', _ATTEMPT_COLS)} "
                    f"FROM {_SCHEMA}.agent_run_correlations c "
                    f"JOIN {_SCHEMA}.job_runs j ON j.tenant_id = c.tenant_id "
                    "AND j.id = c.job_run_id "
                    f"JOIN {_SCHEMA}.job_attempts a ON a.tenant_id = c.tenant_id "
                    "AND a.id = c.attempt_id AND a.job_run_id = c.job_run_id "
                    "WHERE c.tenant_id = :tenant_id "
                    "AND c.state IN (:state_reserved, :state_host_created, "
                    ":state_host_running) " + keyset_clause + " ORDER BY j.deadline_at ASC, c.id ASC LIMIT (:limit + 1)"
                ),
                statement_params,
            ).fetchall()
            # LIMIT limit+1：多取一行判断是否还有下一页；恰好 limit 行
            # 在真尾部时 next_cursor 必须为 None。
            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]
            projections: list[AgentRunGovernanceProjection] = []
            for row in rows:
                correlation = _row_correlation(_unprefix_row(row, "c"))
                job_row = _unprefix_row(row, "j")
                attempt_row = _unprefix_row(row, "a")
                if correlation.job_id != _rv_uuid(job_row, "id") or correlation.attempt_id != _rv_uuid(
                    attempt_row, "id"
                ):
                    raise JobCorrelationInvariantError()
                deadline_at = _rv_dt(job_row, "deadline_at")
                cancel_raw = _rv_obj(job_row, "cancel_requested_at")
                cancel_requested_at = _as_aware_utc(cancel_raw) if cancel_raw is not None else None
                projections.append(
                    AgentRunGovernanceProjection(
                        correlation=correlation,
                        job_state=JobState(_rv_str(job_row, "state")),
                        attempt_state=AttemptState(_rv_str(attempt_row, "state")),
                        deadline_at=deadline_at,
                        job_cancel_requested_at=cancel_requested_at,
                        deadline_reached=clock_now >= deadline_at,
                        lease_expires_at=_rv_dt(attempt_row, "lease_expires_at"),
                        database_now=clock_now,
                    )
                )
            next_cursor: AgentRunGovernanceCursor | None = None
            if has_more and projections:
                last = projections[-1]
                next_cursor = AgentRunGovernanceCursor(
                    deadline_at=last.deadline_at,
                    correlation_id=last.correlation.id,
                )
            self._commit_and_close(session)
        except Exception:
            self._rollback_and_close(session)
            raise
        return AgentRunGovernanceProjectionPage(
            projections=tuple(projections),
            next_cursor=next_cursor,
        )

    # ------------------------------------------------------------------
    # live start authorization
    # ------------------------------------------------------------------

    def authorize_agent_run_start(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        correlation_id: UUID,
    ) -> AgentRunStartAuthorizationDecision:
        """在单个 PG 事务内产生 live start authorization 决策。

        对任何无效 lease（缺失/过期/wrong tenant/job/attempt/fence/
        token、非 current attempt、cancel intent、deadline 或 correlation
        已 terminal）返回闭合 decision（``LEASE_LOST``/``CANCEL``/
        ``DEADLINE_EXCEEDED``/``INVARIANT_FAILURE``），零业务状态变更；
        绝不抛 ``JobLeaseLostError``。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。
            correlation_id: 目标 correlation UUID。

        Returns:
            闭合决策（含 correlation 快照）。

        Raises:
            无。
        """

        session, tenant_id = self._session(scope)
        try:
            transaction_now, clock_now = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            if lease.tenant_id != tenant_id:
                # wrong-tenant handle 在业务查询前 fail closed，零 mutation。
                self._commit_and_close(session)
                return _start_decision_synthesized(
                    tenant_id=tenant_id,
                    job_row=None,
                    attempt_id=lease.attempt_id,
                    fence=lease.fence,
                    action=AgentRunStartAuthorizationAction.LEASE_LOST,
                    safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
                    clock_now=clock_now,
                )
            job_id = lease.job_id
            attempt_id = lease.attempt_id
            fence = lease.fence
            job_row = self._lock_job_row(session, tenant_id=tenant_id, job_id=job_id)
            if job_row is None:
                self._commit_and_close(session)
                return _start_decision_synthesized(
                    tenant_id=tenant_id,
                    job_row=None,
                    attempt_id=attempt_id,
                    fence=fence,
                    action=AgentRunStartAuthorizationAction.LEASE_LOST,
                    safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
                    clock_now=clock_now,
                )
            token_hash = _hash_token(lease.raw_token)
            attempt_row = session.execute(
                text(
                    f"SELECT {_ATTEMPT_COLS} FROM {_SCHEMA}.job_attempts "
                    "WHERE tenant_id = :tenant_id AND id = :attempt_id "
                    "AND job_run_id = :job_id "
                    "AND fence = :fence AND lease_token_sha256 = :token_sha256 "
                    "FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(attempt_id),
                    "job_id": str(job_id),
                    "fence": fence,
                    "token_sha256": token_hash,
                },
            ).first()
            lease_row = session.execute(
                text(
                    f"SELECT {_LEASE_COLS} FROM {_SCHEMA}.job_leases "
                    "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
                    "AND job_run_id = :job_id "
                    "AND fence = :fence AND token_sha256 = :token_sha256 "
                    "FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(attempt_id),
                    "job_id": str(job_id),
                    "fence": fence,
                    "token_sha256": token_hash,
                },
            ).first()
            if attempt_row is None or lease_row is None:
                # 无 attempt/lease 行（含跨租户/跨 job 拼接）：lease 必然失效。
                self._commit_and_close(session)
                return _start_decision_synthesized(
                    tenant_id=tenant_id,
                    job_row=job_row,
                    attempt_id=attempt_id,
                    fence=fence,
                    action=AgentRunStartAuthorizationAction.LEASE_LOST,
                    safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
                    clock_now=clock_now,
                )
            if (
                _rv_obj(lease_row, "released_at") is not None
                or _rv_dt(attempt_row, "lease_expires_at") <= clock_now
                or _rv_obj(attempt_row, "state") != AttemptState.LEASED.value
                or _rv_str(attempt_row, "job_run_id") != str(job_id)
                or _rv_str(lease_row, "job_run_id") != str(job_id)
            ):
                self._commit_and_close(session)
                return _start_decision_synthesized(
                    tenant_id=tenant_id,
                    job_row=job_row,
                    attempt_id=attempt_id,
                    fence=fence,
                    action=AgentRunStartAuthorizationAction.LEASE_LOST,
                    safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
                    clock_now=clock_now,
                )
            if _rv_int(job_row, "current_attempt_number") != _rv_int(attempt_row, "attempt_number"):
                self._commit_and_close(session)
                return _start_decision_synthesized(
                    tenant_id=tenant_id,
                    job_row=job_row,
                    attempt_id=attempt_id,
                    fence=fence,
                    action=AgentRunStartAuthorizationAction.LEASE_LOST,
                    safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
                    clock_now=clock_now,
                )
            correlation_row = session.execute(
                text(
                    f"SELECT {_CORRELATION_COLS} FROM {_SCHEMA}.agent_run_correlations "
                    "WHERE tenant_id = :tenant_id AND id = :correlation_id "
                    "AND attempt_id = :attempt_id FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "correlation_id": str(correlation_id),
                    "attempt_id": str(attempt_id),
                },
            ).first()
            if correlation_row is None:
                if not _job_has_event(
                    session,
                    tenant_value=tenant_value,
                    job_id=job_id,
                    event_type="correlation_missing",
                ):
                    _insert_event_safe(
                        session,
                        tenant_id=tenant_id,
                        job_id=job_id,
                        attempt_id=attempt_id,
                        event_type="correlation_missing",
                        transaction_now=transaction_now,
                    )
                self._commit_and_close(session)
                return _start_decision_synthesized(
                    tenant_id=tenant_id,
                    job_row=job_row,
                    attempt_id=attempt_id,
                    fence=fence,
                    action=AgentRunStartAuthorizationAction.INVARIANT_FAILURE,
                    safe_error_code=SafeJobErrorCode.CORRELATION_MISSING,
                    clock_now=clock_now,
                )
            correlation = _row_correlation(correlation_row)
            if (
                correlation.tenant_id != tenant_id
                or correlation.job_id != job_id
                or correlation.attempt_id != attempt_id
            ):
                if not _job_has_event(
                    session,
                    tenant_value=tenant_value,
                    job_id=job_id,
                    event_type="correlation_invariant",
                ):
                    _insert_event_safe(
                        session,
                        tenant_id=tenant_id,
                        job_id=job_id,
                        attempt_id=attempt_id,
                        event_type="correlation_invariant",
                        transaction_now=transaction_now,
                    )
                decision = AgentRunStartAuthorizationDecision(
                    correlation=correlation,
                    attempt_id=attempt_id,
                    fence=fence,
                    action=AgentRunStartAuthorizationAction.INVARIANT_FAILURE,
                    safe_error_code=SafeJobErrorCode.CORRELATION_INVARIANT,
                )
                self._commit_and_close(session)
                return decision
            if _rv_obj(job_row, "cancel_requested_at") is not None:
                decision = AgentRunStartAuthorizationDecision(
                    correlation=correlation,
                    attempt_id=attempt_id,
                    fence=fence,
                    action=AgentRunStartAuthorizationAction.CANCEL,
                    safe_error_code=SafeJobErrorCode.CANCELLED,
                )
                self._commit_and_close(session)
                return decision
            if clock_now >= _rv_dt(job_row, "deadline_at"):
                # 已有 correlation 后，deadline 只触发 Host governance；
                # 此入口不得写第二个 PG terminal receipt。
                decision = AgentRunStartAuthorizationDecision(
                    correlation=correlation,
                    attempt_id=attempt_id,
                    fence=fence,
                    action=AgentRunStartAuthorizationAction.DEADLINE_EXCEEDED,
                    safe_error_code=SafeJobErrorCode.DEADLINE_EXCEEDED,
                )
                self._commit_and_close(session)
                return decision
            if correlation.state is CorrelationState.RESERVED:
                action = AgentRunStartAuthorizationAction.START_REQUIRED
                safe_error_code = None
            elif correlation.state in (
                CorrelationState.HOST_CREATED,
                CorrelationState.HOST_RUNNING,
            ):
                action = AgentRunStartAuthorizationAction.WAIT
                safe_error_code = None
            else:
                if not _job_has_event(
                    session,
                    tenant_value=tenant_value,
                    job_id=job_id,
                    event_type="correlation_invariant",
                ):
                    _insert_event_safe(
                        session,
                        tenant_id=tenant_id,
                        job_id=job_id,
                        attempt_id=attempt_id,
                        event_type="correlation_invariant",
                        transaction_now=transaction_now,
                    )
                action = AgentRunStartAuthorizationAction.INVARIANT_FAILURE
                safe_error_code = SafeJobErrorCode.CORRELATION_INVARIANT
            decision = AgentRunStartAuthorizationDecision(
                correlation=correlation,
                attempt_id=attempt_id,
                fence=fence,
                action=action,
                safe_error_code=safe_error_code,
            )
            self._commit_and_close(session)
        except Exception:
            self._rollback_and_close(session)
            raise
        return decision

    # ------------------------------------------------------------------
    # tokenless terminal-only reconciliation
    # ------------------------------------------------------------------

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation: AgentRunCorrelationObservation,
    ) -> AgentRunTerminalReconciliationDecision:
        """在单个 PG 事务内以 observation 收敛 correlation/attempt/job。

        Args:
            scope: 租户范围。
            correlation_id: 目标 correlation UUID。
            observation: Service strict mapping 出的 observation。

        Returns:
            闭合决策（含 immutable receipt 复用）。

        Raises:
            JobNotFoundError: correlation 不存在时抛出。
        """

        session, tenant_id = self._session(scope)
        try:
            transaction_now, clock_now = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            # 无锁 correlation locator 读取（非授权真源）：只取得
            # job/attempt identity；授权检查在统一锁序之后逐字段重读。
            locator_row = session.execute(
                text(
                    f"SELECT id, job_run_id, attempt_id FROM {_SCHEMA}.agent_run_correlations "
                    "WHERE tenant_id = :tenant_id AND id = :correlation_id"
                ),
                {
                    "tenant_id": tenant_value,
                    "correlation_id": str(correlation_id),
                },
            ).first()
            if locator_row is None:
                raise JobNotFoundError()
            locator_job_id = _rv_uuid(locator_row, "job_run_id")
            locator_attempt_id = _rv_uuid(locator_row, "attempt_id")
            # 统一锁序：job_runs -> job_attempts -> job_leases，最后才
            # 锁定 correlation；禁止先 FOR UPDATE correlation 再回锁父行。
            job_row = self._lock_job_row(session, tenant_id=tenant_id, job_id=locator_job_id)
            if job_row is None:
                raise JobCorrelationInvariantError()
            attempt_row = session.execute(
                text(
                    f"SELECT {_ATTEMPT_COLS} FROM {_SCHEMA}.job_attempts "
                    "WHERE tenant_id = :tenant_id AND id = :attempt_id "
                    "AND job_run_id = :job_id FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(locator_attempt_id),
                    "job_id": str(locator_job_id),
                },
            ).first()
            if attempt_row is None:
                raise JobCorrelationInvariantError()
            lease_row = session.execute(
                text(
                    f"SELECT {_LEASE_COLS} FROM {_SCHEMA}.job_leases "
                    "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
                    "AND job_run_id = :job_id AND fence = :fence FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(locator_attempt_id),
                    "job_id": str(locator_job_id),
                    "fence": _rv_int(attempt_row, "fence"),
                },
            ).first()
            if lease_row is None:
                raise JobCorrelationInvariantError()
            # 最后锁定并逐字段重读 correlation（授权真源）；缺失/漂移
            # 一律 closed invariant 且零 mutation。
            correlation_row = session.execute(
                text(
                    f"SELECT {_CORRELATION_COLS} FROM {_SCHEMA}.agent_run_correlations "
                    "WHERE tenant_id = :tenant_id AND id = :correlation_id FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "correlation_id": str(correlation_id),
                },
            ).first()
            if correlation_row is None:
                raise JobCorrelationInvariantError()
            correlation = _row_correlation(correlation_row)
            if correlation.job_id != locator_job_id or correlation.attempt_id != locator_attempt_id:
                raise JobCorrelationInvariantError()
            fence = _rv_int(attempt_row, "fence")
            is_current_attempt = (
                _rv_int(job_row, "current_attempt_number") == _rv_int(attempt_row, "attempt_number")
                and _rv_str(attempt_row, "state") == AttemptState.LEASED.value
                and _rv_str(job_row, "state")
                in (
                    JobState.LEASED.value,
                    JobState.CANCEL_REQUESTED.value,
                )
            )
            if not is_current_attempt:
                decision = _stale_or_terminal_replay_reconciliation(
                    session,
                    tenant_id=tenant_id,
                    tenant_value=tenant_value,
                    correlation=correlation,
                    observation=observation,
                    attempt_id=correlation.attempt_id,
                    fence=fence,
                    transaction_now=transaction_now,
                    clock_now=clock_now,
                )
            elif correlation.state in _TERMINAL_CORRELATION_STATES:
                decision = _terminal_replay_reconciliation(
                    session,
                    tenant_id=tenant_id,
                    tenant_value=tenant_value,
                    correlation=correlation,
                    observation=observation,
                    attempt_id=correlation.attempt_id,
                    fence=fence,
                    transaction_now=transaction_now,
                )
            else:
                decision = _active_or_terminalize_reconciliation(
                    session,
                    tenant_id=tenant_id,
                    tenant_value=tenant_value,
                    correlation=correlation,
                    observation=observation,
                    job_row=job_row,
                    attempt_row=attempt_row,
                    lease_row=lease_row,
                    attempt_id=correlation.attempt_id,
                    fence=fence,
                    transaction_now=transaction_now,
                    clock_now=clock_now,
                )
            self._commit_and_close(session)
        except Exception:
            self._rollback_and_close(session)
            raise
        return decision

    # ------------------------------------------------------------------
    # targeted NO_HOST_RUN recovery（仅供 JobService.recover 使用）
    # ------------------------------------------------------------------

    def recover_agent_run_after_no_host(
        self,
        scope: TenantScope,
        correlation_id: UUID,
        observation_sha256: str,
    ) -> JobRecoveryResult | None:
        """对刚得到 ``NO_HOST_RUN`` 的该一条 correlation 执行 targeted 恢复。

        Args:
            scope: 租户范围。
            correlation_id: 目标 correlation UUID。
            observation_sha256: 该 decision observation 的 sha256。

        Returns:
            ``JobRecoveryResult``；任一前提变化时返回 ``None``（零
            mutation）。

        Raises:
            无。
        """

        session, tenant_id = self._session(scope)
        try:
            transaction_now, clock_now = _clock(session)
            tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
            # 无锁 correlation locator 读取（非授权真源）：只取得
            # job/attempt identity；state/observation 校验在统一锁序后
            # 以锁定的重读 correlation 为唯一授权真源。
            locator_row = session.execute(
                text(
                    f"SELECT id, job_run_id, attempt_id FROM {_SCHEMA}.agent_run_correlations "
                    "WHERE tenant_id = :tenant_id AND id = :correlation_id"
                ),
                {
                    "tenant_id": tenant_value,
                    "correlation_id": str(correlation_id),
                },
            ).first()
            if locator_row is None:
                self._commit_and_close(session)
                return None
            locator_job_id = _rv_uuid(locator_row, "job_run_id")
            locator_attempt_id = _rv_uuid(locator_row, "attempt_id")
            # 统一锁序：job_runs -> job_attempts -> job_leases，最后才
            # 锁定 correlation；禁止先 FOR UPDATE correlation 再回锁父行。
            job_row = self._lock_job_row(session, tenant_id=tenant_id, job_id=locator_job_id)
            if job_row is None:
                self._commit_and_close(session)
                return None
            attempt_row = session.execute(
                text(
                    f"SELECT {_ATTEMPT_COLS} FROM {_SCHEMA}.job_attempts "
                    "WHERE tenant_id = :tenant_id AND id = :attempt_id "
                    "AND job_run_id = :job_id FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(locator_attempt_id),
                    "job_id": str(locator_job_id),
                },
            ).first()
            if attempt_row is None:
                self._commit_and_close(session)
                return None
            lease_row = session.execute(
                text(
                    f"SELECT {_LEASE_COLS} FROM {_SCHEMA}.job_leases "
                    "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
                    "AND job_run_id = :job_id AND fence = :fence FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "attempt_id": str(locator_attempt_id),
                    "job_id": str(locator_job_id),
                    "fence": _rv_int(attempt_row, "fence"),
                },
            ).first()
            if lease_row is None or _rv_obj(lease_row, "released_at") is not None:
                self._commit_and_close(session)
                return None
            # 最后锁定并逐字段重读 correlation；缺失/漂移/观测不匹配
            # 一律返回 ``None``（closed 且零 mutation）。
            correlation_row = session.execute(
                text(
                    f"SELECT {_CORRELATION_COLS} FROM {_SCHEMA}.agent_run_correlations "
                    "WHERE tenant_id = :tenant_id AND id = :correlation_id FOR UPDATE"
                ),
                {
                    "tenant_id": tenant_value,
                    "correlation_id": str(correlation_id),
                },
            ).first()
            if correlation_row is None:
                self._commit_and_close(session)
                return None
            correlation = _row_correlation(correlation_row)
            if (
                correlation.job_id != locator_job_id
                or correlation.attempt_id != locator_attempt_id
                or correlation.state is not CorrelationState.RESERVED
                or correlation.last_observation_sha256 != observation_sha256
                or correlation.last_observation_sha256 is None
            ):
                self._commit_and_close(session)
                return None
            current_match = (
                _rv_int(job_row, "current_attempt_number") == _rv_int(attempt_row, "attempt_number")
                and _rv_str(attempt_row, "state") == AttemptState.LEASED.value
                and _rv_str(job_row, "state")
                in (
                    JobState.LEASED.value,
                    JobState.CANCEL_REQUESTED.value,
                )
            )
            lease_expired = _rv_dt(attempt_row, "lease_expires_at") <= clock_now
            if not current_match or not lease_expired:
                self._commit_and_close(session)
                return None
            definition_row = session.execute(
                text(
                    f"SELECT {_DEFINITION_COLS} FROM {_SCHEMA}.job_definitions "
                    "WHERE tenant_id = :tenant_id AND id = :definition_id"
                ),
                {
                    "tenant_id": tenant_value,
                    "definition_id": _rv_str(job_row, "definition_id"),
                },
            ).first()
            if definition_row is None:
                self._commit_and_close(session)
                return None
            locked = _build_locked_from_rows(
                tenant_id=tenant_id,
                job_row=job_row,
                attempt_row=attempt_row,
                lease_row=lease_row,
                definition=_row_definition(definition_row),
                payload=_payload_document(
                    schema_name=_rv_str(job_row, "request_payload_schema_name"),
                    schema_version=_rv_int(job_row, "request_payload_schema_version"),
                    canonical_bytes=_rv_bytes(job_row, "payload_bytes"),
                    sha256=_rv_str(job_row, "payload_sha256"),
                ),
            )
            result = _recover_one_attempt(
                session,
                tenant_id=tenant_id,
                locked=locked,
                transaction_now=transaction_now,
                clock_now=clock_now,
            )
            self._commit_and_close(session)
        except Exception:
            self._rollback_and_close(session)
            raise
        return result


def _generic_recovery_job_is_eligible(
    job_row: _RowLike | None,
) -> TypeGuard[_RowLike]:
    """判断已尝试加锁的 job 行是否仍允许 generic recovery。

    Args:
        job_row: ``FOR UPDATE SKIP LOCKED`` 返回的可空 job 行。

    Returns:
        成功锁定且仍处于 leased/cancel-requested 状态时为 ``True``。

    Raises:
        JobRepositoryFailureError: 行内状态值不是字符串时抛出。
    """

    if job_row is None:
        return False
    return _rv_str(job_row, "state") in (
        JobState.LEASED.value,
        JobState.CANCEL_REQUESTED.value,
    )


def _generic_recovery_is_blocked_by_correlation(
    correlation_row: _RowLike | None,
    *,
    job_id: UUID,
) -> bool:
    """在 late-lock 重读后判断 generic recovery 是否必须让位。

    Args:
        correlation_row: 按 attempt late-lock 得到的可空 correlation 行。
        job_id: 当前已锁定的候选 job 标识。

    Returns:
        已有同一 job correlation 时为 ``True``；无 correlation 时为
        ``False``。

    Raises:
        JobCorrelationInvariantError: correlation 指向其它 job 时抛出。
        JobRepositoryFailureError: 行内 job 标识不是 UUID 时抛出。
    """

    if correlation_row is None:
        return False
    if _rv_uuid(correlation_row, "job_run_id") != job_id:
        raise JobCorrelationInvariantError()
    return True


_TERMINAL_CORRELATION_STATES: frozenset[CorrelationState] = frozenset(
    {
        CorrelationState.HOST_SUCCEEDED,
        CorrelationState.HOST_FAILED,
        CorrelationState.HOST_CANCELLED,
        CorrelationState.HOST_UNSETTLED,
    }
)
"""correlation 的 Host terminal 状态集合。"""


def _canonical_worker_id(worker_id: str) -> None:
    """校验 worker_id 非空且无首尾空白。

    Args:
        worker_id: worker 标识。

    Returns:
        无。

    Raises:
        JobInputError: worker_id 非法时抛出。
    """

    if not isinstance(worker_id, str) or not worker_id or worker_id != worker_id.strip():
        raise JobInputError("worker_id 必须是非空且无首尾空白的字符串")


def _payload_document(
    *,
    schema_name: str,
    schema_version: int,
    canonical_bytes: bytes,
    sha256: str,
) -> CanonicalJobDocument:
    """构造 canonical payload document。

    Args:
        schema_name: payload schema 名。
        schema_version: payload schema 版本。
        canonical_bytes: canonical bytes。
        sha256: 小写 64-hex。

    Returns:
        ``CanonicalJobDocument``。

    Raises:
        JobRepositoryFailureError: 值非法时抛出。
    """

    try:
        text_value = canonical_bytes.decode("utf-8")
        document = parse_canonical_document(
            text_value,
            schema_name=schema_name,
            schema_version=schema_version,
        )
    except (JobInputError, UnicodeDecodeError):
        raise JobRepositoryFailureError() from None
    if document.canonical_bytes != canonical_bytes or document.sha256 != sha256:
        raise JobRepositoryFailureError()
    return document


def _lock_job_attempt_lease(
    session: Session,
    tenant_id: TenantId,
    lease: JobLeaseHandle,
    clock_now: datetime,
) -> _LockedJobAttempt | None:
    """以 tenant/job/attempt/fence/token-hash 锁定 current job/attempt/lease。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        lease: 调用方持有的 lease。
        clock_now: PG clock_timestamp。

    Returns:
        已锁定的组合工作状态；任一 predicate 不匹配或 lease 已过期时
        返回 ``None``。

    Raises:
        JobRepositoryFailureError: 查询失败时抛出。
    """

    if lease.tenant_id != tenant_id:
        return None
    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    token_hash = _hash_token(lease.raw_token)
    job_row = session.execute(
        text(f"SELECT {_JOB_COLS} FROM {_SCHEMA}.job_runs WHERE tenant_id = :tenant_id AND id = :job_id FOR UPDATE"),
        {
            "tenant_id": tenant_value,
            "job_id": str(lease.job_id),
        },
    ).first()
    if job_row is None:
        return None
    attempt_row = session.execute(
        text(
            f"SELECT {_ATTEMPT_COLS} FROM {_SCHEMA}.job_attempts "
            "WHERE tenant_id = :tenant_id AND id = :attempt_id "
            "AND job_run_id = :job_id "
            "AND fence = :fence AND lease_token_sha256 = :token_sha256 "
            "FOR UPDATE"
        ),
        {
            "tenant_id": tenant_value,
            "attempt_id": str(lease.attempt_id),
            "job_id": str(lease.job_id),
            "fence": lease.fence,
            "token_sha256": token_hash,
        },
    ).first()
    if attempt_row is None:
        return None
    if _rv_int(job_row, "current_attempt_number") != _rv_int(attempt_row, "attempt_number"):
        return None
    lease_row = session.execute(
        text(
            f"SELECT {_LEASE_COLS} FROM {_SCHEMA}.job_leases "
            "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
            "AND job_run_id = :job_id "
            "AND fence = :fence AND token_sha256 = :token_sha256 "
            "FOR UPDATE"
        ),
        {
            "tenant_id": tenant_value,
            "attempt_id": str(lease.attempt_id),
            "job_id": str(lease.job_id),
            "fence": lease.fence,
            "token_sha256": token_hash,
        },
    ).first()
    if lease_row is None or _rv_obj(lease_row, "released_at") is not None:
        return None
    if _rv_dt(attempt_row, "lease_expires_at") <= clock_now:
        return None
    definition_row = session.execute(
        text(
            f"SELECT {_DEFINITION_COLS} FROM {_SCHEMA}.job_definitions "
            "WHERE tenant_id = :tenant_id AND id = :definition_id"
        ),
        {
            "tenant_id": tenant_value,
            "definition_id": _rv_str(job_row, "definition_id"),
        },
    ).first()
    if definition_row is None:
        return None
    descriptor = _row_definition(definition_row)
    payload = _payload_document(
        schema_name=_rv_str(job_row, "request_payload_schema_name"),
        schema_version=_rv_int(job_row, "request_payload_schema_version"),
        canonical_bytes=_rv_bytes(job_row, "payload_bytes"),
        sha256=_rv_str(job_row, "payload_sha256"),
    )
    return _LockedJobAttempt(
        job_row=job_row,
        attempt_row=attempt_row,
        lease_row=lease_row,
        definition=descriptor,
        payload=payload,
    )


def _build_claim(
    *,
    tenant_id: TenantId,
    job_row: _RowLike,
    attempt_row: _RowLike,
    definition: JobHandlerDescriptor,
    payload: CanonicalJobDocument,
    raw_token: str,
    new_expires_at: datetime,
) -> JobClaim:
    """由已锁定的行重建 ``JobClaim``。

    Args:
        tenant_id: 租户标识。
        job_row: ``job_runs`` 行。
        attempt_row: ``job_attempts`` 行。
        definition: job descriptor。
        payload: job payload。
        raw_token: raw lease token。
        new_expires_at: 当前 lease 到期时间。

    Returns:
        ``JobClaim``。

    Raises:
        JobRepositoryFailureError: 值非法时抛出。
    """

    try:
        return JobClaim(
            tenant_id=tenant_id,
            definition_id=_rv_uuid(job_row, "definition_id"),
            job_id=_rv_uuid(job_row, "id"),
            attempt_id=_rv_uuid(attempt_row, "id"),
            attempt_number=_rv_int(attempt_row, "attempt_number"),
            worker_id=_rv_str(attempt_row, "worker_id"),
            descriptor=definition,
            payload=payload,
            lease=JobLeaseHandle(
                tenant_id=tenant_id,
                job_id=_rv_uuid(job_row, "id"),
                attempt_id=_rv_uuid(attempt_row, "id"),
                fence=_rv_int(attempt_row, "fence"),
                raw_token=raw_token,
                acquired_at=_rv_dt(attempt_row, "claimed_at"),
                expires_at=new_expires_at,
            ),
            deadline_at=_rv_dt(job_row, "deadline_at"),
        )
    except (ValueError, TypeError, JobInputError):
        raise JobRepositoryFailureError() from None


def _release_lease_cas(
    session: Session,
    *,
    tenant_id: TenantId,
    locked: _LockedJobAttempt,
    reason: LeaseReleaseReason,
    released_at: datetime,
    transaction_now: datetime,
) -> None:
    """以 versioned CAS + single-release trigger 释放 lease。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        locked: 已锁定的 job/attempt/lease 组合。
        reason: 释放原因。
        released_at: 释放时间。
        transaction_now: PG transaction_timestamp。

    Returns:
        无。

    Raises:
        JobLeaseLostError: CAS 未命中时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    effective_released_at = max(
        released_at,
        _rv_dt(locked.lease_row, "acquired_at"),
    )
    updated = session.execute(
        text(
            f"UPDATE {_SCHEMA}.job_leases "
            "SET released_at = :released_at, release_reason = :release_reason, "
            "updated_at = :updated_at, version = version + 1 "
            "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id "
            "AND fence = :fence AND released_at IS NULL AND version = :expected_version "
            "RETURNING id"
        ),
        {
            "released_at": effective_released_at,
            "release_reason": reason.value,
            "updated_at": transaction_now,
            "tenant_id": tenant_value,
            "attempt_id": _rv_str(locked.attempt_row, "id"),
            "fence": _rv_int(locked.attempt_row, "fence"),
            "expected_version": _rv_int(locked.lease_row, "version"),
        },
    ).first()
    if updated is None:
        raise JobLeaseLostError()


def _persist_receipt(
    session: Session,
    *,
    tenant_id: TenantId,
    job_id: UUID,
    attempt_id: UUID,
    receipt: JobAttemptReceipt,
    transaction_now: datetime,
) -> JobAttemptReceipt:
    """写入一条 immutable attempt receipt（含 result 四元组）。

    同一 attempt 的重复收口路径必须读取既存 immutable row，绝不重写：
    调用方先查询 ``UNIQUE(tenant_id, attempt_id)``，已存在则直接复用。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        job_id: job UUID。
        attempt_id: attempt UUID。
        receipt: 待持久化的 receipt DTO。
        transaction_now: PG transaction_timestamp。

    Returns:
        已持久化的 ``JobAttemptReceipt``。

    Raises:
        JobRepositoryFailureError: 插入失败时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    result = receipt.result
    session.execute(
        text(
            f"INSERT INTO {_SCHEMA}.job_attempt_receipts "
            "(id, tenant_id, job_run_id, attempt_id, outcome, result_schema_name, "
            "result_schema_version, result_bytes, result_sha256, receipt_schema_name, "
            "receipt_schema_version, receipt_bytes, receipt_sha256, safe_error_code, "
            "finalized_at, created_at) "
            "VALUES (:id, :tenant_id, :job_run_id, :attempt_id, :outcome, "
            ":result_schema_name, :result_schema_version, :result_bytes, "
            ":result_sha256, :receipt_schema_name, :receipt_schema_version, "
            ":receipt_bytes, :receipt_sha256, :safe_error_code, :finalized_at, "
            ":created_at)"
        ),
        {
            "id": str(uuid4()),
            "tenant_id": tenant_value,
            "job_run_id": str(job_id),
            "attempt_id": str(attempt_id),
            "outcome": receipt.outcome.value,
            "result_schema_name": result.schema_name if result is not None else None,
            "result_schema_version": result.schema_version if result is not None else None,
            "result_bytes": result.canonical_bytes if result is not None else None,
            "result_sha256": result.sha256 if result is not None else None,
            "receipt_schema_name": receipt.receipt.schema_name,
            "receipt_schema_version": receipt.receipt.schema_version,
            "receipt_bytes": receipt.receipt.canonical_bytes,
            "receipt_sha256": receipt.receipt.sha256,
            "safe_error_code": (receipt.safe_error_code.value if receipt.safe_error_code is not None else None),
            "finalized_at": receipt.finalized_at,
            "created_at": transaction_now,
        },
    )
    return receipt


def _existing_receipt(
    session: Session,
    *,
    tenant_id: TenantId,
    attempt_id: UUID,
) -> JobAttemptReceipt | None:
    """读取 attempt 的既存 immutable receipt。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        attempt_id: attempt UUID。

    Returns:
        既存 ``JobAttemptReceipt``；不存在时返回 ``None``。

    Raises:
        JobRepositoryFailureError: 行值非法时抛出。
    """

    row = session.execute(
        text(
            f"SELECT {_RECEIPT_COLS} FROM {_SCHEMA}.job_attempt_receipts "
            "WHERE tenant_id = :tenant_id AND attempt_id = :attempt_id"
        ),
        {
            "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
            "attempt_id": str(attempt_id),
        },
    ).first()
    if row is None:
        return None
    return _row_receipt(row)


def _write_job_terminal_state(
    session: Session,
    *,
    tenant_id: TenantId,
    locked: _LockedJobAttempt,
    job_state: JobState,
    attempt_state: AttemptState,
    safe_failure_code: SafeJobErrorCode | None,
    completed_at: datetime,
    transaction_now: datetime,
    lease_reason: LeaseReleaseReason,
) -> None:
    """把 job/attempt 收敛到终态并释放 lease。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        locked: 已锁定的 job/attempt/lease 组合。
        job_state: job 终态。
        attempt_state: attempt 终态。
        safe_failure_code: 可空安全失败码。
        completed_at: 完成时间。
        transaction_now: PG transaction_timestamp。
        lease_reason: 显式 lease 释放原因。

    Returns:
        无。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    job_id = _rv_uuid(locked.job_row, "id")
    attempt_id = _rv_uuid(locked.attempt_row, "id")
    session.execute(
        text(
            f"UPDATE {_SCHEMA}.job_attempts "
            "SET state = :state, finished_at = :finished_at, "
            "safe_failure_code = :safe_failure_code, updated_at = :updated_at, "
            "version = version + 1 "
            "WHERE tenant_id = :tenant_id AND id = :attempt_id AND fence = :fence"
        ),
        {
            "state": attempt_state.value,
            "finished_at": completed_at,
            "safe_failure_code": (safe_failure_code.value if safe_failure_code is not None else None),
            "updated_at": transaction_now,
            "tenant_id": tenant_value,
            "attempt_id": str(attempt_id),
            "fence": _rv_int(locked.attempt_row, "fence"),
        },
    )
    session.execute(
        text(
            f"UPDATE {_SCHEMA}.job_runs "
            "SET state = :state, completed_at = :completed_at, "
            "safe_failure_code = :safe_failure_code, updated_at = :updated_at, "
            "version = version + 1 "
            "WHERE tenant_id = :tenant_id AND id = :job_id"
        ),
        {
            "state": job_state.value,
            "completed_at": completed_at,
            "safe_failure_code": (safe_failure_code.value if safe_failure_code is not None else None),
            "updated_at": transaction_now,
            "tenant_id": tenant_value,
            "job_id": str(job_id),
        },
    )
    _release_lease_cas(
        session,
        tenant_id=tenant_id,
        locked=locked,
        reason=lease_reason,
        released_at=completed_at,
        transaction_now=transaction_now,
    )
    # ------------------------------------------------------------------
    # complete / fail / cancel
    # ------------------------------------------------------------------


def _prefixed_columns(prefix: str, columns: str) -> str:
    """返回带前缀的列清单。

    Args:
        prefix: 列前缀（如 ``a``）。
        columns: 逗号分隔的列名串。

    Returns:
        以 ``prefix.col`` 形式拼接的列清单。

    Raises:
        无。
    """

    return ", ".join(f"{prefix}.{column}" for column in columns.split(", "))


def _alias_columns(prefix: str, columns: str) -> str:
    """返回带唯一别名的列清单（``a.id AS a_id`` 形式）。

    用于多表 JOIN 的 SELECT，避免 PG 剥掉限定符后列名冲突。

    Args:
        prefix: 表别名（如 ``a``）。
        columns: 逗号分隔的列名串。

    Returns:
        以 ``prefix.col AS prefix_col`` 形式拼接的列清单。

    Raises:
        无。
    """

    return ", ".join(f"{prefix}.{column} AS {prefix}_{column}" for column in columns.split(", "))


def _unprefix_row(row: _RowLike, prefix: str) -> dict[str, _RowValue]:
    """去掉行键的别名前缀并返回可按键名访问的合成行。

    Args:
        row: 带别名前缀的查询行。
        prefix: 列前缀（如 ``a`` 对应 ``a_id``）。

    Returns:
        去掉 ``prefix_`` 前缀后的合成行（closed 标量值）。

    Raises:
        无。
    """

    stripped_prefix = f"{prefix}_"
    if isinstance(row, Row):
        items = row._mapping.items()
    else:
        items = row.items()
    return {key[len(stripped_prefix) :]: value for key, value in items if key.startswith(stripped_prefix)}


def _existing_attempt_id(
    session: Session,
    *,
    tenant_id: TenantId,
    job_id: UUID,
) -> UUID | None:
    """读取 job 当前 attempt 的 ID。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        job_id: job UUID。

    Returns:
        current attempt UUID；无 attempt 时返回 ``None``。
    """

    row = session.execute(
        text(
            f"SELECT id FROM {_SCHEMA}.job_attempts "
            "WHERE tenant_id = :tenant_id AND job_run_id = :job_id "
            "ORDER BY attempt_number DESC LIMIT 1"
        ),
        {
            "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
            "job_id": str(job_id),
        },
    ).first()
    return UUID(str(row[0])) if row is not None else None


def _existing_attempt_state(
    session: Session,
    *,
    tenant_id: TenantId,
    job_id: UUID,
) -> AttemptState | None:
    """读取 job 当前 attempt 的状态。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        job_id: job UUID。

    Returns:
        current attempt 状态；无 attempt 时返回 ``None``。
    """

    row = session.execute(
        text(
            f"SELECT state FROM {_SCHEMA}.job_attempts "
            "WHERE tenant_id = :tenant_id AND job_run_id = :job_id "
            "ORDER BY attempt_number DESC LIMIT 1"
        ),
        {
            "tenant_id": _canonical_uuid(tenant_id.value, "租户标识"),
            "job_id": str(job_id),
        },
    ).first()
    return AttemptState(str(row[0])) if row is not None else None


def _recover_one_attempt(
    session: Session,
    *,
    tenant_id: TenantId,
    locked: _LockedJobAttempt,
    transaction_now: datetime,
    clock_now: datetime,
) -> JobRecoveryResult | None:
    """收敛单个从未提交 correlation 的过期 attempt。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        locked: 已锁定的 job/attempt/lease 组合。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        收敛后的 ``JobRecoveryResult``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    job_id = _rv_uuid(locked.job_row, "id")
    attempt_id = _rv_uuid(locked.attempt_row, "id")
    if _rv_obj(locked.job_row, "cancel_requested_at") is not None:
        receipt = _converge_cancel_intent(
            session,
            tenant_id=tenant_id,
            locked=locked,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
        return JobRecoveryResult(
            job_id=job_id,
            attempt_id=attempt_id,
            job_state=JobState.CANCELLED,
            attempt_state=AttemptState.CANCELLED,
            receipt=receipt,
            next_available_at=None,
            safe_error_code=SafeJobErrorCode.CANCELLED,
        )
    attempt_number = _rv_int(locked.attempt_row, "attempt_number")
    deadline = _rv_dt(locked.job_row, "deadline_at")
    if clock_now >= deadline:
        safe_code = SafeJobErrorCode.DEADLINE_EXCEEDED
        receipt = _persist_receipt(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            attempt_id=attempt_id,
            receipt=_build_attempt_receipt(
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                outcome=AttemptReceiptOutcome.FAILED,
                result=None,
                safe_error_code=safe_code,
                finalized_at=clock_now,
                receipt_document=build_generic_attempt_receipt(
                    job_id=job_id,
                    attempt_id=attempt_id,
                    outcome=AttemptReceiptOutcome.FAILED,
                    reason=GenericAttemptReceiptReason.LEASE_EXPIRED,
                    safe_error_code=safe_code,
                    result_ref=None,
                ),
            ),
            transaction_now=transaction_now,
        )
        _write_job_terminal_state(
            session,
            tenant_id=tenant_id,
            locked=locked,
            job_state=JobState.FAILED,
            attempt_state=AttemptState.ABANDONED,
            safe_failure_code=safe_code,
            completed_at=clock_now,
            transaction_now=transaction_now,
            lease_reason=LeaseReleaseReason.LEASE_EXPIRED,
        )
        _insert_event_safe(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            attempt_id=attempt_id,
            event_type="job_lease_expired",
            transaction_now=transaction_now,
        )
        return JobRecoveryResult(
            job_id=job_id,
            attempt_id=attempt_id,
            job_state=JobState.FAILED,
            attempt_state=AttemptState.ABANDONED,
            receipt=receipt,
            next_available_at=None,
            safe_error_code=safe_code,
        )
    attempts_exhausted = attempt_number >= locked.definition.max_attempts
    if attempts_exhausted:
        return _terminalize_recover_lease_expiry(
            session,
            tenant_id=tenant_id,
            locked=locked,
            safe_code=SafeJobErrorCode.RETRY_EXHAUSTED,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
    next_available_at = clock_now + timedelta(seconds=_backoff_seconds(locked.definition, attempt_number))
    if not next_available_at < deadline:
        return _terminalize_recover_lease_expiry(
            session,
            tenant_id=tenant_id,
            locked=locked,
            safe_code=SafeJobErrorCode.DEADLINE_EXCEEDED,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
    receipt = _persist_receipt(
        session,
        tenant_id=tenant_id,
        job_id=job_id,
        attempt_id=attempt_id,
        receipt=_build_attempt_receipt(
            tenant_id=tenant_id,
            job_id=job_id,
            attempt_id=attempt_id,
            outcome=AttemptReceiptOutcome.FAILED,
            result=None,
            safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
            finalized_at=clock_now,
            receipt_document=build_generic_attempt_receipt(
                job_id=job_id,
                attempt_id=attempt_id,
                outcome=AttemptReceiptOutcome.FAILED,
                reason=GenericAttemptReceiptReason.LEASE_EXPIRED,
                safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
                result_ref=None,
            ),
        ),
        transaction_now=transaction_now,
    )
    _mark_attempt_failed_retry(
        session,
        tenant_id=tenant_id,
        locked=locked,
        safe_failure_code=SafeJobErrorCode.LEASE_EXPIRED,
        next_available_at=next_available_at,
        transaction_now=transaction_now,
    )
    _insert_event_safe(
        session,
        tenant_id=tenant_id,
        job_id=job_id,
        attempt_id=attempt_id,
        event_type="job_lease_expired",
        transaction_now=transaction_now,
    )
    return JobRecoveryResult(
        job_id=job_id,
        attempt_id=attempt_id,
        job_state=JobState.READY,
        attempt_state=AttemptState.ABANDONED,
        receipt=receipt,
        next_available_at=next_available_at,
        safe_error_code=SafeJobErrorCode.LEASE_EXPIRED,
    )


def _terminalize_recover_lease_expiry(
    session: Session,
    *,
    tenant_id: TenantId,
    locked: _LockedJobAttempt,
    safe_code: SafeJobErrorCode,
    transaction_now: datetime,
    clock_now: datetime,
) -> JobRecoveryResult:
    """把 lease-expiry 恢复收敛为 terminal failed（attempt=abandoned）。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        locked: 已锁定的 job/attempt/lease 组合。
        safe_code: 终态安全错误码（deadline_exceeded/retry_exhausted）。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        ``JobRecoveryResult``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    job_id = _rv_uuid(locked.job_row, "id")
    attempt_id = _rv_uuid(locked.attempt_row, "id")
    receipt = _persist_receipt(
        session,
        tenant_id=tenant_id,
        job_id=job_id,
        attempt_id=attempt_id,
        receipt=_build_attempt_receipt(
            tenant_id=tenant_id,
            job_id=job_id,
            attempt_id=attempt_id,
            outcome=AttemptReceiptOutcome.FAILED,
            result=None,
            safe_error_code=safe_code,
            finalized_at=clock_now,
            receipt_document=build_generic_attempt_receipt(
                job_id=job_id,
                attempt_id=attempt_id,
                outcome=AttemptReceiptOutcome.FAILED,
                reason=GenericAttemptReceiptReason.LEASE_EXPIRED,
                safe_error_code=safe_code,
                result_ref=None,
            ),
        ),
        transaction_now=transaction_now,
    )
    _write_job_terminal_state(
        session,
        tenant_id=tenant_id,
        locked=locked,
        job_state=JobState.FAILED,
        attempt_state=AttemptState.ABANDONED,
        safe_failure_code=safe_code,
        completed_at=clock_now,
        transaction_now=transaction_now,
        lease_reason=LeaseReleaseReason.LEASE_EXPIRED,
    )
    _insert_event_safe(
        session,
        tenant_id=tenant_id,
        job_id=job_id,
        attempt_id=attempt_id,
        event_type="job_lease_expired",
        transaction_now=transaction_now,
    )
    return JobRecoveryResult(
        job_id=job_id,
        attempt_id=attempt_id,
        job_state=JobState.FAILED,
        attempt_state=AttemptState.ABANDONED,
        receipt=receipt,
        next_available_at=None,
        safe_error_code=safe_code,
    )


def _converge_cancel_intent(
    session: Session,
    *,
    tenant_id: TenantId,
    locked: _LockedJobAttempt,
    transaction_now: datetime,
    clock_now: datetime,
) -> JobAttemptReceipt:
    """把持有 cancel intent 的 job/attempt 收敛为 cancelled。

    写唯一 generic ``(cancelled, cancel_intent, cancelled, null)``
    receipt/event，release lease；绝不写 deadline 或 success receipt。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        locked: 已锁定的 job/attempt/lease 组合。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        immutable ``JobAttemptReceipt``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    job_id = _rv_uuid(locked.job_row, "id")
    attempt_id = _rv_uuid(locked.attempt_row, "id")
    receipt_document = build_generic_attempt_receipt(
        job_id=job_id,
        attempt_id=attempt_id,
        outcome=AttemptReceiptOutcome.CANCELLED,
        reason=GenericAttemptReceiptReason.CANCEL_INTENT,
        safe_error_code=SafeJobErrorCode.CANCELLED,
        result_ref=None,
    )
    receipt = _persist_receipt(
        session,
        tenant_id=tenant_id,
        job_id=job_id,
        attempt_id=attempt_id,
        receipt=_build_attempt_receipt(
            tenant_id=tenant_id,
            job_id=job_id,
            attempt_id=attempt_id,
            outcome=AttemptReceiptOutcome.CANCELLED,
            result=None,
            safe_error_code=SafeJobErrorCode.CANCELLED,
            finalized_at=clock_now,
            receipt_document=receipt_document,
        ),
        transaction_now=transaction_now,
    )
    _write_job_terminal_state(
        session,
        tenant_id=tenant_id,
        locked=locked,
        job_state=JobState.CANCELLED,
        attempt_state=AttemptState.CANCELLED,
        safe_failure_code=SafeJobErrorCode.CANCELLED,
        completed_at=clock_now,
        transaction_now=transaction_now,
        lease_reason=LeaseReleaseReason.CANCEL_INTENT,
    )
    _insert_event_safe(
        session,
        tenant_id=tenant_id,
        job_id=job_id,
        attempt_id=attempt_id,
        event_type="job_cancelled",
        transaction_now=transaction_now,
    )
    return receipt


def _terminalize_deadline(
    session: Session,
    *,
    tenant_id: TenantId,
    locked: _LockedJobAttempt,
    transaction_now: datetime,
    clock_now: datetime,
) -> JobAttemptReceipt:
    """在 deadline 已到时把 attempt/job 收敛为 failed。

    写唯一 generic ``(failed, deadline, deadline_exceeded, null)``
    receipt/event，release lease；已存在 receipt 时原样复用（同 attempt
    重放不重建）。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        locked: 已锁定的 job/attempt/lease 组合。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        该 attempt 的 immutable ``JobAttemptReceipt``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    job_id = _rv_uuid(locked.job_row, "id")
    attempt_id = _rv_uuid(locked.attempt_row, "id")
    existing = _existing_receipt(session, tenant_id=tenant_id, attempt_id=attempt_id)
    if existing is None:
        receipt_document = build_generic_attempt_receipt(
            job_id=job_id,
            attempt_id=attempt_id,
            outcome=AttemptReceiptOutcome.FAILED,
            reason=GenericAttemptReceiptReason.DEADLINE,
            safe_error_code=SafeJobErrorCode.DEADLINE_EXCEEDED,
            result_ref=None,
        )
        existing = _persist_receipt(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            attempt_id=attempt_id,
            receipt=_build_attempt_receipt(
                tenant_id=tenant_id,
                job_id=job_id,
                attempt_id=attempt_id,
                outcome=AttemptReceiptOutcome.FAILED,
                result=None,
                safe_error_code=SafeJobErrorCode.DEADLINE_EXCEEDED,
                finalized_at=clock_now,
                receipt_document=receipt_document,
            ),
            transaction_now=transaction_now,
        )
    _write_job_terminal_state(
        session,
        tenant_id=tenant_id,
        locked=locked,
        job_state=JobState.FAILED,
        attempt_state=AttemptState.FAILED,
        safe_failure_code=SafeJobErrorCode.DEADLINE_EXCEEDED,
        completed_at=clock_now,
        transaction_now=transaction_now,
        lease_reason=LeaseReleaseReason.DEADLINE,
    )
    _insert_event_safe(
        session,
        tenant_id=tenant_id,
        job_id=job_id,
        attempt_id=attempt_id,
        event_type="job_deadline_exceeded",
        transaction_now=transaction_now,
    )
    return existing


def _mark_attempt_failed_retry(
    session: Session,
    *,
    tenant_id: TenantId,
    locked: _LockedJobAttempt,
    safe_failure_code: SafeJobErrorCode,
    next_available_at: datetime,
    transaction_now: datetime,
) -> None:
    """把 attempt 标记为 failed、job 恢复为 ready 并安排 next_available_at。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        locked: 已锁定的 job/attempt/lease 组合。
        safe_failure_code: attempt 的安全失败码。
        next_available_at: 下次可用时间。
        transaction_now: PG transaction_timestamp。

    Returns:
        无。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    job_id = _rv_uuid(locked.job_row, "id")
    attempt_id = _rv_uuid(locked.attempt_row, "id")
    session.execute(
        text(
            f"UPDATE {_SCHEMA}.job_attempts "
            "SET state = :state, finished_at = :finished_at, "
            "safe_failure_code = :safe_failure_code, updated_at = :updated_at, "
            "version = version + 1 "
            "WHERE tenant_id = :tenant_id AND id = :attempt_id AND fence = :fence"
        ),
        {
            "state": AttemptState.FAILED.value,
            "finished_at": next_available_at,
            "safe_failure_code": safe_failure_code.value,
            "updated_at": transaction_now,
            "tenant_id": tenant_value,
            "attempt_id": str(attempt_id),
            "fence": _rv_int(locked.attempt_row, "fence"),
        },
    )
    session.execute(
        text(
            f"UPDATE {_SCHEMA}.job_runs "
            "SET state = :state, available_at = :available_at, "
            "updated_at = :updated_at, version = version + 1 "
            "WHERE tenant_id = :tenant_id AND id = :job_id"
        ),
        {
            "state": JobState.READY.value,
            "available_at": next_available_at,
            "updated_at": transaction_now,
            "tenant_id": tenant_value,
            "job_id": str(job_id),
        },
    )
    _release_lease_cas(
        session,
        tenant_id=tenant_id,
        locked=locked,
        reason=LeaseReleaseReason.FAILURE,
        released_at=next_available_at,
        transaction_now=transaction_now,
    )


def _insert_event_safe(
    session: Session,
    *,
    tenant_id: TenantId,
    job_id: UUID,
    attempt_id: UUID | None,
    event_type: str,
    transaction_now: datetime,
) -> None:
    """以已锁定 job 行写入 event（带 job 行锁与原子 sequence）。

    供模块级收敛 helper 使用；假定调用方已对该 job 行持有 ``FOR
    UPDATE`` 锁。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        job_id: job UUID。
        attempt_id: 可空 attempt UUID。
        event_type: 事件类型。
        transaction_now: PG transaction_timestamp。

    Returns:
        无。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    row = session.execute(
        text(
            f"UPDATE {_SCHEMA}.job_runs "
            "SET next_event_sequence = next_event_sequence + 1, "
            "updated_at = :updated_at, version = version + 1 "
            "WHERE tenant_id = :tenant_id AND id = :job_id "
            "RETURNING next_event_sequence"
        ),
        {
            "tenant_id": tenant_value,
            "job_id": str(job_id),
            "updated_at": transaction_now,
        },
    ).one()
    sequence = int(row[0]) - 1
    session.execute(
        text(
            f"INSERT INTO {_SCHEMA}.job_events "
            "(id, tenant_id, job_run_id, attempt_id, sequence_number, event_type, "
            "occurred_at, created_at) "
            "VALUES (:id, :tenant_id, :job_run_id, :attempt_id, :sequence_number, "
            ":event_type, :occurred_at, :created_at)"
        ),
        {
            "id": str(uuid4()),
            "tenant_id": tenant_value,
            "job_run_id": str(job_id),
            "attempt_id": str(attempt_id) if attempt_id is not None else None,
            "sequence_number": sequence,
            "event_type": event_type,
            "occurred_at": transaction_now,
            "created_at": transaction_now,
        },
    )


def _build_attempt_receipt(
    *,
    tenant_id: TenantId,
    job_id: UUID,
    attempt_id: UUID,
    outcome: AttemptReceiptOutcome,
    result: CanonicalJobDocument | None,
    safe_error_code: SafeJobErrorCode | None,
    finalized_at: datetime,
    receipt_document: CanonicalJobDocument,
) -> JobAttemptReceipt:
    """构造 ``JobAttemptReceipt`` DTO。

    Args:
        tenant_id: 租户标识。
        job_id: job UUID。
        attempt_id: attempt UUID。
        outcome: 唯一业务 outcome。
        result: 可空 result document。
        safe_error_code: 可空安全错误码。
        finalized_at: 收口时间。
        receipt_document: canonical receipt document。

    Returns:
        ``JobAttemptReceipt``。

    Raises:
        JobRepositoryFailureError: 构造失败时抛出。
    """

    try:
        return JobAttemptReceipt(
            tenant_id=tenant_id,
            job_id=job_id,
            attempt_id=attempt_id,
            outcome=outcome,
            result=result,
            receipt=receipt_document,
            safe_error_code=safe_error_code,
            finalized_at=finalized_at,
        )
    except JobInputError:
        raise JobRepositoryFailureError() from None
    # ------------------------------------------------------------------
    # agent run correlation（Transaction 2 / lookup / enumeration）
    # ------------------------------------------------------------------


def _build_locked_from_rows(
    *,
    tenant_id: TenantId,
    job_row: _RowLike,
    attempt_row: _RowLike,
    lease_row: _RowLike,
    definition: JobHandlerDescriptor,
    payload: CanonicalJobDocument,
) -> _LockedJobAttempt:
    """由已锁定的行构造组合工作状态。

    Args:
        tenant_id: 租户标识。
        job_row: ``job_runs`` 行。
        attempt_row: ``job_attempts`` 行。
        lease_row: ``job_leases`` 行。
        definition: job descriptor。
        payload: job payload。

    Returns:
        ``_LockedJobAttempt``。

    Raises:
        无。
    """

    return _LockedJobAttempt(
        job_row=job_row,
        attempt_row=attempt_row,
        lease_row=lease_row,
        definition=definition,
        payload=payload,
    )


_SYNTHESIZED_IDEMPOTENCY_KEY = "synthesized-correlation"
"""无 committed correlation 时合成决策快照的占位幂等键（safe、固定）。"""


def _synthesize_correlation(
    *,
    tenant_id: TenantId,
    job_row: _RowLike | None,
    attempt_id: UUID,
    state: CorrelationState,
    clock_now: datetime,
) -> AgentRunCorrelation:
    """由已锁定行合成 correlation 快照（无 committed row 时使用）。

    仅供 start authorization 的非 ``START_REQUIRED`` 决策填充 DTO；
    合成值来自 locked job/attempt 的 immutable identity，不写数据库。
    ``job_row`` 为 ``None``（job 也不存在）时使用固定 safe 占位身份；
    占位时间取自本事务的 PG ``clock_timestamp()``，绝不使用本机时钟。

    Args:
        tenant_id: 租户标识。
        job_row: 可空 ``job_runs`` 行。
        attempt_id: attempt UUID。
        state: 合成 state。
        clock_now: PG ``clock_timestamp()``。

    Returns:
        ``AgentRunCorrelation``。

    Raises:
        JobRepositoryFailureError: 无法合成时抛出。
    """

    if job_row is None:
        return AgentRunCorrelation(
            id=uuid4(),
            tenant_id=tenant_id,
            job_id=uuid4(),
            attempt_id=attempt_id,
            idempotency_key=_SYNTHESIZED_IDEMPOTENCY_KEY,
            reserved_host_run_id=f"run_{attempt_id.hex}",
            state=state,
            observed_at=None,
            last_observation_sha256=None,
            created_at=clock_now,
            updated_at=clock_now,
            version=1,
        )
    try:
        return AgentRunCorrelation(
            id=uuid4(),
            tenant_id=tenant_id,
            job_id=_rv_uuid(job_row, "id"),
            attempt_id=attempt_id,
            idempotency_key=_rv_str(job_row, "idempotency_key"),
            reserved_host_run_id=f"run_{attempt_id.hex}",
            state=state,
            observed_at=None,
            last_observation_sha256=None,
            created_at=_rv_dt(job_row, "created_at"),
            updated_at=_rv_dt(job_row, "updated_at"),
            version=1,
        )
    except (ValueError, TypeError, JobInputError):
        raise JobRepositoryFailureError() from None


def _start_decision_synthesized(
    *,
    tenant_id: TenantId,
    job_row: _RowLike | None,
    attempt_id: UUID,
    fence: int,
    action: AgentRunStartAuthorizationAction,
    safe_error_code: SafeJobErrorCode | None,
    clock_now: datetime,
) -> AgentRunStartAuthorizationDecision:
    """构造 start authorization 决策（correlation 为合成快照）。

    Args:
        tenant_id: 租户标识。
        job_row: 可空 ``job_runs`` 行。
        attempt_id: attempt UUID。
        fence: attempt fence。
        action: 决策 action。
        safe_error_code: 可空安全错误码。
        clock_now: PG ``clock_timestamp()``。

    Returns:
        ``AgentRunStartAuthorizationDecision``。

    Raises:
        无。
    """

    correlation = _synthesize_correlation(
        tenant_id=tenant_id,
        job_row=job_row,
        attempt_id=attempt_id,
        state=CorrelationState.RESERVED,
        clock_now=clock_now,
    )
    return AgentRunStartAuthorizationDecision(
        correlation=correlation,
        attempt_id=attempt_id,
        fence=fence,
        action=action,
        safe_error_code=safe_error_code,
    )


def _job_has_event(
    session: Session,
    *,
    tenant_value: str,
    job_id: UUID,
    event_type: str,
) -> bool:
    """判断 job 是否已写指定类型 event（dedup 用）。

    Args:
        session: 当前事务 Session。
        tenant_value: canonical tenant UUID 字符串。
        job_id: job UUID。
        event_type: 事件类型。

    Returns:
        已存在时返回 ``True``。

    Raises:
        无。
    """

    row = session.execute(
        text(
            f"SELECT 1 FROM {_SCHEMA}.job_events "
            "WHERE tenant_id = :tenant_id AND job_run_id = :job_id "
            "AND event_type = :event_type LIMIT 1"
        ),
        {
            "tenant_id": tenant_value,
            "job_id": str(job_id),
            "event_type": event_type,
        },
    ).first()
    return row is not None


def _persist_correlation_observation(
    session: Session,
    *,
    tenant_id: TenantId,
    tenant_value: str,
    correlation_id: UUID,
    state: CorrelationState,
    observation: AgentRunCorrelationObservation,
    transaction_now: datetime,
    clock_now: datetime,
) -> None:
    """持久化 correlation 的 state/fingerprint/observed_at。

    仅更新 mutable 列；identity 列由列级 GRANT 与 trigger 双重拒绝。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        tenant_value: canonical tenant UUID 字符串。
        correlation_id: correlation UUID。
        state: 目标 correlation state。
        observation: 本次 observation。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        无。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    session.execute(
        text(
            f"UPDATE {_SCHEMA}.agent_run_correlations "
            "SET state = :state, observed_at = :observed_at, "
            "last_observation_sha256 = :last_observation_sha256, "
            "updated_at = :updated_at, version = version + 1 "
            "WHERE tenant_id = :tenant_id AND id = :correlation_id"
        ),
        {
            "state": state.value,
            "observed_at": clock_now,
            "last_observation_sha256": observation.sha256,
            "updated_at": transaction_now,
            "tenant_id": tenant_value,
            "correlation_id": str(correlation_id),
        },
    )


def _stale_or_terminal_replay_reconciliation(
    session: Session,
    *,
    tenant_id: TenantId,
    tenant_value: str,
    correlation: AgentRunCorrelation,
    observation: AgentRunCorrelationObservation,
    attempt_id: UUID,
    fence: int,
    transaction_now: datetime,
    clock_now: datetime,
) -> AgentRunTerminalReconciliationDecision:
    """处理 attempt 已非 current 的 terminal-replay / stale 分支。

    优先复用已收口 correlation 的 immutable receipt（terminal replay），
    否则按 stale 语义记录/重放。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        tenant_value: canonical tenant UUID 字符串。
        correlation: 已锁定 correlation。
        observation: 本次 observation。
        attempt_id: attempt UUID。
        fence: attempt fence。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        ``AgentRunTerminalReconciliationDecision``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    if correlation.state in _TERMINAL_CORRELATION_STATES:
        try:
            expected_state = _host_state_to_correlation_state(observation.host_state)
        except JobCorrelationInvariantError:
            expected_state = None
        existing_receipt = _existing_receipt(session, tenant_id=tenant_id, attempt_id=attempt_id)
        if (
            expected_state is not None
            and existing_receipt is not None
            and correlation.state == expected_state
            and _receipt_matches_observation(existing_receipt, observation)
        ):
            replay_action = _replay_action_for_receipt(existing_receipt.outcome)
            return AgentRunTerminalReconciliationDecision(
                correlation=correlation,
                observation=observation,
                attempt_id=attempt_id,
                fence=fence,
                action=replay_action,
                receipt=existing_receipt,
                safe_error_code=None,
            )
        if correlation.last_observation_sha256 == observation.sha256:
            # 无 receipt 的 terminal state 来自 stale 记录：相同 observation
            # 重放是 ALREADY_STALE，不是 contradiction。
            return AgentRunTerminalReconciliationDecision(
                correlation=correlation,
                observation=observation,
                attempt_id=attempt_id,
                fence=fence,
                action=AgentRunTerminalReconciliationAction.ALREADY_STALE_ATTEMPT,
                receipt=None,
                safe_error_code=SafeJobErrorCode.CORRELATION_STALE_ATTEMPT,
            )
        # 已持久化 terminal state 与本次 terminal observation 矛盾：invariant。
        if not _job_has_event(
            session,
            tenant_value=tenant_value,
            job_id=correlation.job_id,
            event_type="correlation_invariant",
        ):
            _insert_event_safe(
                session,
                tenant_id=tenant_id,
                job_id=correlation.job_id,
                attempt_id=attempt_id,
                event_type="correlation_invariant",
                transaction_now=transaction_now,
            )
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.INVARIANT_FAILURE,
            receipt=None,
            safe_error_code=SafeJobErrorCode.CORRELATION_INVARIANT,
        )
    return _stale_reconciliation(
        session,
        tenant_id=tenant_id,
        tenant_value=tenant_value,
        correlation=correlation,
        observation=observation,
        attempt_id=attempt_id,
        fence=fence,
        transaction_now=transaction_now,
        clock_now=clock_now,
    )


def _stale_reconciliation(
    session: Session,
    *,
    tenant_id: TenantId,
    tenant_value: str,
    correlation: AgentRunCorrelation,
    observation: AgentRunCorrelationObservation,
    attempt_id: UUID,
    fence: int,
    transaction_now: datetime,
    clock_now: datetime,
) -> AgentRunTerminalReconciliationDecision:
    """处理 correlation 已不属于 job current attempt 的 stale 分支。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        tenant_value: canonical tenant UUID 字符串。
        correlation: 已锁定 correlation。
        observation: 本次 observation。
        attempt_id: attempt UUID。
        fence: attempt fence。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        ``AgentRunTerminalReconciliationDecision``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    if correlation.last_observation_sha256 == observation.sha256:
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.ALREADY_STALE_ATTEMPT,
            receipt=None,
            safe_error_code=SafeJobErrorCode.CORRELATION_STALE_ATTEMPT,
        )
    terminal_state = _host_state_to_correlation_state(observation.host_state)
    _persist_correlation_observation(
        session,
        tenant_id=tenant_id,
        tenant_value=tenant_value,
        correlation_id=correlation.id,
        state=terminal_state,
        observation=observation,
        transaction_now=transaction_now,
        clock_now=clock_now,
    )
    _insert_event_safe(
        session,
        tenant_id=tenant_id,
        job_id=correlation.job_id,
        attempt_id=attempt_id,
        event_type="correlation_stale_attempt",
        transaction_now=transaction_now,
    )
    return AgentRunTerminalReconciliationDecision(
        correlation=correlation,
        observation=observation,
        attempt_id=attempt_id,
        fence=fence,
        action=AgentRunTerminalReconciliationAction.STALE_ATTEMPT,
        receipt=None,
        safe_error_code=SafeJobErrorCode.CORRELATION_STALE_ATTEMPT,
    )


def _terminal_replay_reconciliation(
    session: Session,
    *,
    tenant_id: TenantId,
    tenant_value: str,
    correlation: AgentRunCorrelation,
    observation: AgentRunCorrelationObservation,
    attempt_id: UUID,
    fence: int,
    transaction_now: datetime,
) -> AgentRunTerminalReconciliationDecision:
    """处理 correlation 已在 Host terminal state 的重放/矛盾分支。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        tenant_value: canonical tenant UUID 字符串。
        correlation: 已锁定 correlation。
        observation: 本次 observation。
        attempt_id: attempt UUID。
        fence: attempt fence。
        transaction_now: PG transaction_timestamp。

    Returns:
        ``AgentRunTerminalReconciliationDecision``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    existing_receipt = _existing_receipt(session, tenant_id=tenant_id, attempt_id=attempt_id)
    expected_state = _host_state_to_correlation_state(observation.host_state)
    if (
        existing_receipt is not None
        and correlation.state == expected_state
        and _receipt_matches_observation(existing_receipt, observation)
    ):
        replay_action = _replay_action_for_receipt(existing_receipt.outcome)
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=replay_action,
            receipt=existing_receipt,
            safe_error_code=None,
        )
    if not _job_has_event(
        session,
        tenant_value=tenant_value,
        job_id=correlation.job_id,
        event_type="correlation_invariant",
    ):
        _insert_event_safe(
            session,
            tenant_id=tenant_id,
            job_id=correlation.job_id,
            attempt_id=attempt_id,
            event_type="correlation_invariant",
            transaction_now=transaction_now,
        )
    return AgentRunTerminalReconciliationDecision(
        correlation=correlation,
        observation=observation,
        attempt_id=attempt_id,
        fence=fence,
        action=AgentRunTerminalReconciliationAction.INVARIANT_FAILURE,
        receipt=None,
        safe_error_code=SafeJobErrorCode.CORRELATION_INVARIANT,
    )


def _receipt_matches_observation(
    receipt: JobAttemptReceipt,
    observation: AgentRunCorrelationObservation,
) -> bool:
    """判断既有 receipt outcome 是否与 terminal observation 一致。

    Args:
        receipt: 既有 receipt。
        observation: 本次 terminal observation。

    Returns:
        succeeded<->succeeded、failed<->failed/unsettled、
        cancelled<->cancelled 一致时返回 ``True``。

    Raises:
        无。
    """

    if observation.host_state is HostRunObservationState.SUCCEEDED:
        return receipt.outcome is AttemptReceiptOutcome.SUCCEEDED
    if observation.host_state is HostRunObservationState.CANCELLED:
        return receipt.outcome is AttemptReceiptOutcome.CANCELLED
    if observation.host_state in (
        HostRunObservationState.FAILED,
        HostRunObservationState.UNSETTLED,
    ):
        return receipt.outcome is AttemptReceiptOutcome.FAILED
    return False


def _replay_action_for_receipt(
    outcome: AttemptReceiptOutcome,
) -> AgentRunTerminalReconciliationAction:
    """按既有 receipt outcome 返回 replay action。

    Args:
        outcome: 既有 receipt outcome。

    Returns:
        对应 ``ALREADY_TERMINALIZED_*`` action。

    Raises:
        无。
    """

    if outcome is AttemptReceiptOutcome.SUCCEEDED:
        return AgentRunTerminalReconciliationAction.ALREADY_TERMINALIZED_SUCCESS
    if outcome is AttemptReceiptOutcome.CANCELLED:
        return AgentRunTerminalReconciliationAction.ALREADY_TERMINALIZED_CANCEL
    return AgentRunTerminalReconciliationAction.ALREADY_TERMINALIZED_FAILURE


def _host_state_to_correlation_state(
    host_state: HostRunObservationState,
) -> CorrelationState:
    """把 Host observation state 映射为 correlation state。

    Args:
        host_state: Host observation state。

    Returns:
        对应 ``CorrelationState``。

    Raises:
        JobCorrelationInvariantError: 无法映射（如 missing/created/
            queued/running 之外由调用方先行处理）时抛出。
    """

    mapping = {
        HostRunObservationState.SUCCEEDED: CorrelationState.HOST_SUCCEEDED,
        HostRunObservationState.FAILED: CorrelationState.HOST_FAILED,
        HostRunObservationState.CANCELLED: CorrelationState.HOST_CANCELLED,
        HostRunObservationState.UNSETTLED: CorrelationState.HOST_UNSETTLED,
        HostRunObservationState.CREATED: CorrelationState.HOST_CREATED,
        HostRunObservationState.QUEUED: CorrelationState.HOST_CREATED,
        HostRunObservationState.RUNNING: CorrelationState.HOST_RUNNING,
    }
    mapped = mapping.get(host_state)
    if mapped is None:
        raise JobCorrelationInvariantError()
    return mapped


def _active_or_terminalize_reconciliation(
    session: Session,
    *,
    tenant_id: TenantId,
    tenant_value: str,
    correlation: AgentRunCorrelation,
    observation: AgentRunCorrelationObservation,
    job_row: _RowLike,
    attempt_row: _RowLike,
    lease_row: _RowLike,
    attempt_id: UUID,
    fence: int,
    transaction_now: datetime,
    clock_now: datetime,
) -> AgentRunTerminalReconciliationDecision:
    """处理 correlation 非 terminal 的 missing/active/terminalize 分支。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        tenant_value: canonical tenant UUID 字符串。
        correlation: 已锁定 correlation。
        observation: 本次 observation。
        job_row: 已锁定 ``job_runs`` 行。
        attempt_row: 已锁定 ``job_attempts`` 行。
        lease_row: 已锁定 ``job_leases`` 行。
        attempt_id: attempt UUID。
        fence: attempt fence。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        ``AgentRunTerminalReconciliationDecision``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    if observation.host_state is HostRunObservationState.MISSING:
        if correlation.state is CorrelationState.RESERVED:
            return _no_host_run_reconciliation(
                session,
                tenant_id=tenant_id,
                tenant_value=tenant_value,
                correlation=correlation,
                observation=observation,
                attempt_id=attempt_id,
                fence=fence,
                transaction_now=transaction_now,
                clock_now=clock_now,
            )
        if not _job_has_event(
            session,
            tenant_value=tenant_value,
            job_id=correlation.job_id,
            event_type="correlation_invariant",
        ):
            _insert_event_safe(
                session,
                tenant_id=tenant_id,
                job_id=correlation.job_id,
                attempt_id=attempt_id,
                event_type="correlation_invariant",
                transaction_now=transaction_now,
            )
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.INVARIANT_FAILURE,
            receipt=None,
            safe_error_code=SafeJobErrorCode.CORRELATION_INVARIANT,
        )
    if observation.host_state in (
        HostRunObservationState.CREATED,
        HostRunObservationState.QUEUED,
        HostRunObservationState.RUNNING,
    ):
        target_state = _host_state_to_correlation_state(observation.host_state)
        if correlation.last_observation_sha256 == observation.sha256:
            return AgentRunTerminalReconciliationDecision(
                correlation=correlation,
                observation=observation,
                attempt_id=attempt_id,
                fence=fence,
                action=AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
                receipt=None,
                safe_error_code=None,
            )
        _persist_correlation_observation(
            session,
            tenant_id=tenant_id,
            tenant_value=tenant_value,
            correlation_id=correlation.id,
            state=target_state,
            observation=observation,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
        _insert_event_safe(
            session,
            tenant_id=tenant_id,
            job_id=correlation.job_id,
            attempt_id=attempt_id,
            event_type="correlation_host_active",
            transaction_now=transaction_now,
        )
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT,
            receipt=None,
            safe_error_code=None,
        )
    return _terminalize_reconciliation(
        session,
        tenant_id=tenant_id,
        tenant_value=tenant_value,
        correlation=correlation,
        observation=observation,
        job_row=job_row,
        attempt_row=attempt_row,
        lease_row=lease_row,
        attempt_id=attempt_id,
        fence=fence,
        transaction_now=transaction_now,
        clock_now=clock_now,
    )


def _no_host_run_reconciliation(
    session: Session,
    *,
    tenant_id: TenantId,
    tenant_value: str,
    correlation: AgentRunCorrelation,
    observation: AgentRunCorrelationObservation,
    attempt_id: UUID,
    fence: int,
    transaction_now: datetime,
    clock_now: datetime,
) -> AgentRunTerminalReconciliationDecision:
    """处理 correlation=reserved 且 Host missing 的 NO_HOST_RUN 分支。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        tenant_value: canonical tenant UUID 字符串。
        correlation: 已锁定 correlation。
        observation: 本次 observation。
        attempt_id: attempt UUID。
        fence: attempt fence。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        ``AgentRunTerminalReconciliationDecision``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    if correlation.last_observation_sha256 == observation.sha256:
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.NO_HOST_RUN,
            receipt=None,
            safe_error_code=None,
        )
    _persist_correlation_observation(
        session,
        tenant_id=tenant_id,
        tenant_value=tenant_value,
        correlation_id=correlation.id,
        state=CorrelationState.RESERVED,
        observation=observation,
        transaction_now=transaction_now,
        clock_now=clock_now,
    )
    _insert_event_safe(
        session,
        tenant_id=tenant_id,
        job_id=correlation.job_id,
        attempt_id=attempt_id,
        event_type="correlation_no_host_run",
        transaction_now=transaction_now,
    )
    return AgentRunTerminalReconciliationDecision(
        correlation=correlation,
        observation=observation,
        attempt_id=attempt_id,
        fence=fence,
        action=AgentRunTerminalReconciliationAction.NO_HOST_RUN,
        receipt=None,
        safe_error_code=None,
    )


def _terminalize_reconciliation(
    session: Session,
    *,
    tenant_id: TenantId,
    tenant_value: str,
    correlation: AgentRunCorrelation,
    observation: AgentRunCorrelationObservation,
    job_row: _RowLike,
    attempt_row: _RowLike,
    lease_row: _RowLike,
    attempt_id: UUID,
    fence: int,
    transaction_now: datetime,
    clock_now: datetime,
) -> AgentRunTerminalReconciliationDecision:
    """首次 terminalize：cancel intent -> deadline -> Host terminal outcome。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。
        tenant_value: canonical tenant UUID 字符串。
        correlation: 已锁定 correlation。
        observation: 本次 terminal observation。
        job_row: 已锁定 ``job_runs`` 行。
        attempt_row: 已锁定 ``job_attempts`` 行。
        lease_row: 已锁定 ``job_leases`` 行。
        attempt_id: attempt UUID。
        fence: attempt fence。
        transaction_now: PG transaction_timestamp。
        clock_now: PG clock_timestamp。

    Returns:
        ``AgentRunTerminalReconciliationDecision``。

    Raises:
        JobRepositoryFailureError: 更新失败时抛出。
    """

    definition_row = session.execute(
        text(
            f"SELECT {_DEFINITION_COLS} FROM {_SCHEMA}.job_definitions "
            "WHERE tenant_id = :tenant_id AND id = :definition_id"
        ),
        {
            "tenant_id": tenant_value,
            "definition_id": _rv_str(job_row, "definition_id"),
        },
    ).one()
    locked = _build_locked_from_rows(
        tenant_id=tenant_id,
        job_row=job_row,
        attempt_row=attempt_row,
        lease_row=lease_row,
        definition=_row_definition(definition_row),
        payload=_payload_document(
            schema_name=_rv_str(job_row, "request_payload_schema_name"),
            schema_version=_rv_int(job_row, "request_payload_schema_version"),
            canonical_bytes=_rv_bytes(job_row, "payload_bytes"),
            sha256=_rv_str(job_row, "payload_sha256"),
        ),
    )
    target_state = _host_state_to_correlation_state(observation.host_state)
    if _rv_obj(job_row, "cancel_requested_at") is not None:
        receipt = _converge_cancel_intent(
            session,
            tenant_id=tenant_id,
            locked=locked,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
        _persist_correlation_observation(
            session,
            tenant_id=tenant_id,
            tenant_value=tenant_value,
            correlation_id=correlation.id,
            state=target_state,
            observation=observation,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.TERMINALIZED_CANCEL,
            receipt=receipt,
            safe_error_code=None,
        )
    if clock_now >= _rv_dt(job_row, "deadline_at"):
        _terminalize_deadline(
            session,
            tenant_id=tenant_id,
            locked=locked,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
        _persist_correlation_observation(
            session,
            tenant_id=tenant_id,
            tenant_value=tenant_value,
            correlation_id=correlation.id,
            state=target_state,
            observation=observation,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.TERMINALIZED_FAILURE,
            receipt=_existing_receipt(session, tenant_id=tenant_id, attempt_id=attempt_id),
            safe_error_code=None,
        )
    if observation.host_state is HostRunObservationState.SUCCEEDED:
        receipt_document = build_agent_run_terminal_receipt(
            correlation_id=correlation.id,
            reserved_host_run_id=correlation.reserved_host_run_id,
            host_state=observation.host_state,
            host_completed_at=observation.host_completed_at,
            outcome=AttemptReceiptOutcome.SUCCEEDED,
            safe_error_code=None,
        )
        receipt = _persist_receipt(
            session,
            tenant_id=tenant_id,
            job_id=correlation.job_id,
            attempt_id=attempt_id,
            receipt=_build_attempt_receipt(
                tenant_id=tenant_id,
                job_id=correlation.job_id,
                attempt_id=attempt_id,
                outcome=AttemptReceiptOutcome.SUCCEEDED,
                result=None,
                safe_error_code=None,
                finalized_at=clock_now,
                receipt_document=receipt_document,
            ),
            transaction_now=transaction_now,
        )
        _write_job_terminal_state(
            session,
            tenant_id=tenant_id,
            locked=locked,
            job_state=JobState.SUCCEEDED,
            attempt_state=AttemptState.SUCCEEDED,
            safe_failure_code=None,
            completed_at=clock_now,
            transaction_now=transaction_now,
            lease_reason=LeaseReleaseReason.COMPLETION,
        )
        _persist_correlation_observation(
            session,
            tenant_id=tenant_id,
            tenant_value=tenant_value,
            correlation_id=correlation.id,
            state=target_state,
            observation=observation,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
        _insert_event_safe(
            session,
            tenant_id=tenant_id,
            job_id=correlation.job_id,
            attempt_id=attempt_id,
            event_type="correlation_host_terminal",
            transaction_now=transaction_now,
        )
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.TERMINALIZED_SUCCESS,
            receipt=receipt,
            safe_error_code=None,
        )
    if observation.host_state is HostRunObservationState.CANCELLED:
        receipt_document = build_agent_run_terminal_receipt(
            correlation_id=correlation.id,
            reserved_host_run_id=correlation.reserved_host_run_id,
            host_state=observation.host_state,
            host_completed_at=observation.host_completed_at,
            outcome=AttemptReceiptOutcome.CANCELLED,
            safe_error_code=SafeJobErrorCode.HOST_RUN_CANCELLED,
        )
        receipt = _persist_receipt(
            session,
            tenant_id=tenant_id,
            job_id=correlation.job_id,
            attempt_id=attempt_id,
            receipt=_build_attempt_receipt(
                tenant_id=tenant_id,
                job_id=correlation.job_id,
                attempt_id=attempt_id,
                outcome=AttemptReceiptOutcome.CANCELLED,
                result=None,
                safe_error_code=SafeJobErrorCode.HOST_RUN_CANCELLED,
                finalized_at=clock_now,
                receipt_document=receipt_document,
            ),
            transaction_now=transaction_now,
        )
        _write_job_terminal_state(
            session,
            tenant_id=tenant_id,
            locked=locked,
            job_state=JobState.CANCELLED,
            attempt_state=AttemptState.CANCELLED,
            safe_failure_code=SafeJobErrorCode.HOST_RUN_CANCELLED,
            completed_at=clock_now,
            transaction_now=transaction_now,
            lease_reason=LeaseReleaseReason.CANCEL_INTENT,
        )
        _persist_correlation_observation(
            session,
            tenant_id=tenant_id,
            tenant_value=tenant_value,
            correlation_id=correlation.id,
            state=target_state,
            observation=observation,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
        _insert_event_safe(
            session,
            tenant_id=tenant_id,
            job_id=correlation.job_id,
            attempt_id=attempt_id,
            event_type="correlation_host_terminal",
            transaction_now=transaction_now,
        )
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.TERMINALIZED_CANCEL,
            receipt=receipt,
            safe_error_code=None,
        )
    # Host FAILED / UNSETTLED：以 retry policy 收敛。
    unsettled = observation.host_state is HostRunObservationState.UNSETTLED
    safe_code = SafeJobErrorCode.HOST_RUN_UNSETTLED if unsettled else SafeJobErrorCode.HOST_RUN_FAILED
    attempt_number = _rv_int(attempt_row, "attempt_number")
    deadline = _rv_dt(job_row, "deadline_at")
    next_available_at = clock_now + timedelta(seconds=_backoff_seconds(locked.definition, attempt_number))
    if attempt_number < locked.definition.max_attempts and next_available_at < deadline:
        receipt_document = build_agent_run_terminal_receipt(
            correlation_id=correlation.id,
            reserved_host_run_id=correlation.reserved_host_run_id,
            host_state=observation.host_state,
            host_completed_at=observation.host_completed_at,
            outcome=AttemptReceiptOutcome.FAILED,
            safe_error_code=safe_code,
        )
        receipt = _persist_receipt(
            session,
            tenant_id=tenant_id,
            job_id=correlation.job_id,
            attempt_id=attempt_id,
            receipt=_build_attempt_receipt(
                tenant_id=tenant_id,
                job_id=correlation.job_id,
                attempt_id=attempt_id,
                outcome=AttemptReceiptOutcome.FAILED,
                result=None,
                safe_error_code=safe_code,
                finalized_at=clock_now,
                receipt_document=receipt_document,
            ),
            transaction_now=transaction_now,
        )
        _mark_attempt_failed_retry(
            session,
            tenant_id=tenant_id,
            locked=locked,
            safe_failure_code=safe_code,
            next_available_at=next_available_at,
            transaction_now=transaction_now,
        )
        _persist_correlation_observation(
            session,
            tenant_id=tenant_id,
            tenant_value=tenant_value,
            correlation_id=correlation.id,
            state=target_state,
            observation=observation,
            transaction_now=transaction_now,
            clock_now=clock_now,
        )
        _insert_event_safe(
            session,
            tenant_id=tenant_id,
            job_id=correlation.job_id,
            attempt_id=attempt_id,
            event_type="correlation_host_terminal",
            transaction_now=transaction_now,
        )
        return AgentRunTerminalReconciliationDecision(
            correlation=correlation,
            observation=observation,
            attempt_id=attempt_id,
            fence=fence,
            action=AgentRunTerminalReconciliationAction.TERMINALIZED_FAILURE,
            receipt=receipt,
            safe_error_code=None,
        )
    terminal_code = (
        SafeJobErrorCode.RETRY_EXHAUSTED
        if attempt_number >= locked.definition.max_attempts
        else SafeJobErrorCode.DEADLINE_EXCEEDED
        if not next_available_at < deadline
        else safe_code
    )
    receipt_document = build_agent_run_terminal_receipt(
        correlation_id=correlation.id,
        reserved_host_run_id=correlation.reserved_host_run_id,
        host_state=observation.host_state,
        host_completed_at=observation.host_completed_at,
        outcome=AttemptReceiptOutcome.FAILED,
        safe_error_code=safe_code,
    )
    receipt = _persist_receipt(
        session,
        tenant_id=tenant_id,
        job_id=correlation.job_id,
        attempt_id=attempt_id,
        receipt=_build_attempt_receipt(
            tenant_id=tenant_id,
            job_id=correlation.job_id,
            attempt_id=attempt_id,
            outcome=AttemptReceiptOutcome.FAILED,
            result=None,
            safe_error_code=safe_code,
            finalized_at=clock_now,
            receipt_document=receipt_document,
        ),
        transaction_now=transaction_now,
    )
    _write_job_terminal_state(
        session,
        tenant_id=tenant_id,
        locked=locked,
        job_state=JobState.FAILED,
        attempt_state=AttemptState.FAILED,
        safe_failure_code=terminal_code,
        completed_at=clock_now,
        transaction_now=transaction_now,
        lease_reason=LeaseReleaseReason.FAILURE,
    )
    _persist_correlation_observation(
        session,
        tenant_id=tenant_id,
        tenant_value=tenant_value,
        correlation_id=correlation.id,
        state=target_state,
        observation=observation,
        transaction_now=transaction_now,
        clock_now=clock_now,
    )
    _insert_event_safe(
        session,
        tenant_id=tenant_id,
        job_id=correlation.job_id,
        attempt_id=attempt_id,
        event_type="correlation_host_terminal",
        transaction_now=transaction_now,
    )
    return AgentRunTerminalReconciliationDecision(
        correlation=correlation,
        observation=observation,
        attempt_id=attempt_id,
        fence=fence,
        action=AgentRunTerminalReconciliationAction.TERMINALIZED_FAILURE,
        receipt=receipt,
        safe_error_code=None,
    )
