"""PostgreSQL Source Sync repository 的唯一具体实现。

本模块独占 SQLAlchemy/psycopg、租户事务、NOWAIT 锁序与 Source
operation/run/health/outbox 的持久化重建。公开七方法只接收或返回纯领域
DTO；每个方法拥有一个完整事务，且不把 Session、Row、SQL 或 driver
异常泄漏到协议边界。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import NoReturn, TypeAlias
from uuid import UUID, uuid4

import psycopg
from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantId, TenantScope
from dayu.investment.domain.jobs import CanonicalJobDocument, JobHandlerDescriptor, JsonValue, build_canonical_document
from dayu.investment.domain.source import (
    SourceDefinitionId,
    SourceKind,
    SourceSubscriptionId,
    SubscriptionStatus,
)
from dayu.investment.domain.source_evidence import (
    SourceDocumentEvidence,
    SourceFinsTerminalCandidate,
    SourceNoProviderReason,
    SourceNoProviderTerminalCandidate,
    SourceSyncAttemptReceipt,
    SourceSyncResult,
    build_source_sync_attempt_receipt,
    build_source_sync_result,
    parse_source_sync_attempt_receipt,
    parse_source_sync_result,
    validate_evidence_against_snapshot,
)
from dayu.investment.domain.source_health import (
    SOURCE_HEALTH_ALERT_SCHEMA_NAME,
    SourceAlertKind,
    SourceAlertOutboxEvent,
    SourceHealthProjection,
    SourceHealthReenableRequest,
    SourceHealthSnapshotCursor,
    SourceHealthSnapshotPage,
    SourceHealthSnapshotProjection,
    SourceHealthStatus,
    build_source_alert_outbox_event,
    build_source_health_transition,
    is_source_observation_stale,
)
from dayu.investment.domain.source_operation import (
    SourceOperationAcquireAction,
    SourceOperationAcquireDecision,
    SourceOperationAcquireRequest,
    SourceOperationEffectiveState,
    SourceOperationState,
    SourceTerminalRecordAction,
    SourceTerminalRecordDecision,
    SourceTerminalRecordRequest,
)
from dayu.investment.domain.source_payload import (
    ManualSourceSyncPayload,
    ScheduledSourceSyncPayload,
    SourceExecutionBinding,
    SourceExecutionSnapshot,
    build_source_execution_snapshot,
    build_source_execution_snapshot_document,
    parse_source_execution_snapshot_document,
    parse_source_sync_payload,
)
from dayu.investment.domain.source_sync import (
    SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME,
    SOURCE_SYNC_JOB_DESCRIPTOR,
    SOURCE_SYNC_RECEIPT_SCHEMA_NAME,
    SOURCE_SYNC_RESULT_SCHEMA_NAME,
    FinsDisclosureSubscriptionConfig,
    SourceBindingDisposition,
    SourceConnectorKey,
    SourceSyncErrorCode,
    SourceSyncExecutionRejected,
    SourceSyncExecutionRejectionCode,
    SourceSyncOrigin,
    SourceSyncOutcome,
    SourceSyncRepositoryFailure,
    SourceSyncRepositoryFailureCode,
    SourceSyncRequestRejected,
    SourceSyncRequestRejectionCode,
    parse_fins_disclosure_subscription_config,
)
from dayu.investment.storage.db import PLATFORM_SCHEMA_NAME, TENANT_CONTEXT_SETTING
from dayu.investment.storage.source_sync_protocols import SourceSyncRepositoryProtocol

_SCHEMA = PLATFORM_SCHEMA_NAME
_MAX_HEALTH_PAGE_SIZE = 200
_SOURCE_RUN_CORE_COLUMNS = (
    "job_run_id",
    "job_attempt_id",
    "payload_sha256",
    "outcome",
    "retry_recommended",
    "records_downloaded",
    "records_reused",
    "records_ignored",
    "records_failed",
    "receipt_json",
    "receipt_sha256",
    "result_json",
    "result_sha256",
)

_DbJsonScalar: TypeAlias = str | int | float | bool | None
_DbJsonValue: TypeAlias = _DbJsonScalar | list["_DbJsonValue"] | dict[str, "_DbJsonValue"]
_DbValue: TypeAlias = (
    str | int | float | bool | datetime | date | bytes | memoryview | UUID | dict[str, _DbJsonValue] | list[_DbJsonValue] | None
)
_SqlRow: TypeAlias = Row[tuple[_DbValue, ...]]
_ClosedRepositoryError: TypeAlias = (
    SourceSyncRequestRejected | SourceSyncExecutionRejected | SourceSyncRepositoryFailure
)


@dataclass(frozen=True, slots=True)
class _LockedJobContext:
    """已按固定顺序锁定的 durable Job/attempt/lease 事实。"""

    job_row: _SqlRow
    definition_row: _SqlRow
    attempt_row: _SqlRow
    lease_row: _SqlRow
    operation_row: _SqlRow | None
    payload: ManualSourceSyncPayload | ScheduledSourceSyncPayload


@dataclass(frozen=True, slots=True)
class _LockedSourceContext:
    """已锁定的 subscription/source/security/health 事实。"""

    subscription_row: _SqlRow
    source_definition_row: _SqlRow
    security_row: _SqlRow
    health_row: _SqlRow | None


def _raise_request(code: SourceSyncRequestRejectionCode) -> NoReturn:
    """抛出 closed request rejection。

    Args:
        code: 精确拒绝码。

    Returns:
        永不返回。

    Raises:
        SourceSyncRequestRejected: 恒抛。
    """

    raise SourceSyncRequestRejected(code) from None


def _raise_execution(code: SourceSyncExecutionRejectionCode) -> NoReturn:
    """抛出 closed execution rejection。

    Args:
        code: 精确 execution 拒绝码。

    Returns:
        永不返回。

    Raises:
        SourceSyncExecutionRejected: 恒抛。
    """

    raise SourceSyncExecutionRejected(code) from None


def _raise_repository(code: SourceSyncRepositoryFailureCode) -> NoReturn:
    """抛出 closed repository failure。

    Args:
        code: 精确 repository failure 码。

    Returns:
        永不返回。

    Raises:
        SourceSyncRepositoryFailure: 恒抛。
    """

    raise SourceSyncRepositoryFailure(code) from None


def _canonical_uuid_text(value: str, label: str) -> str:
    """校验 canonical、非零 UUID 文本。

    Args:
        value: 待校验文本。
        label: 字段标签。

    Returns:
        原 canonical UUID 文本。

    Raises:
        SourceSyncRequestRejected: 文本非法时抛出 ``invalid_input``。
    """

    if type(value) is not str:
        _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
    try:
        parsed = UUID(value)
    except ValueError:
        _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
    if parsed.int == 0 or str(parsed) != value:
        _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
    return value


def _validate_scope(scope: TenantScope) -> TenantId:
    """校验可信租户范围并返回强租户标识。

    Args:
        scope: 待校验范围。

    Returns:
        范围内租户标识。

    Raises:
        SourceSyncRequestRejected: 类型或 UUID shape 非法时抛出。
    """

    if type(scope) is not TenantScope or type(scope.tenant_id) is not TenantId:
        _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
    _canonical_uuid_text(scope.tenant_id.value, "tenant_id")
    return scope.tenant_id


def _validate_subscription_id(subscription_id: SourceSubscriptionId) -> str:
    """校验 subscription 强标识并返回 UUID 文本。

    Args:
        subscription_id: 待校验标识。

    Returns:
        Canonical UUID 文本。

    Raises:
        SourceSyncRequestRejected: 类型或 UUID shape 非法时抛出。
    """

    if type(subscription_id) is not SourceSubscriptionId:
        _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
    return _canonical_uuid_text(subscription_id.value, "subscription_id")


def _validate_uuid(value: UUID, label: str) -> UUID:
    """校验精确、非零 UUID。

    Args:
        value: 待校验 UUID。
        label: 字段标签。

    Returns:
        原 UUID。

    Raises:
        SourceSyncRequestRejected: 类型或零值非法时抛出。
    """

    if type(value) is not UUID or value.int == 0:
        _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
    return value


def _is_lock_failure(error: SQLAlchemyError | psycopg.Error) -> bool:
    """判断错误是否为 exact PostgreSQL ``55P03`` typed lock failure。

    Args:
        error: SQLAlchemy 或 psycopg typed error。

    Returns:
        仅 exact ``55P03`` / ``LockNotAvailable`` 返回 ``True``。

    Raises:
        无。
    """

    if isinstance(error, psycopg.errors.LockNotAvailable):
        return True
    if isinstance(error, psycopg.Error):
        return error.sqlstate == "55P03"
    if isinstance(error, DBAPIError):
        original = error.orig
        if isinstance(original, psycopg.errors.LockNotAvailable):
            return True
        if isinstance(original, psycopg.Error):
            return original.sqlstate == "55P03"
    return False


def _close_after_settlement(session: Session) -> None:
    """在事务已收敛后关闭 Session。

    Args:
        session: 待关闭 Session。

    Returns:
        无。

    Raises:
        SourceSyncRepositoryFailure: close 仍触发数据库失败时抛出。
    """

    try:
        session.close()
    except (SQLAlchemyError, psycopg.Error):
        _raise_repository(SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)


def _rollback_database_failure(
    session: Session,
    original: SQLAlchemyError | psycopg.Error,
    *,
    post_admission: bool,
) -> NoReturn:
    """回滚数据库失败并按唯一优先级映射 closed code。

    Args:
        session: 当前 Session。
        original: Original operation 的 typed 数据库失败。
        post_admission: 第一条 repository SQL 是否已成功返回。

    Returns:
        永不返回。

    Raises:
        SourceSyncRepositoryFailure: rollback 或 original phase 对应的稳定失败。
    """

    try:
        session.rollback()
    except (SQLAlchemyError, psycopg.Error):
        _raise_repository(SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)
    _close_after_settlement(session)
    if _is_lock_failure(original):
        _raise_repository(SourceSyncRepositoryFailureCode.UNAVAILABLE)
    if post_admission:
        _raise_repository(SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)
    _raise_repository(SourceSyncRepositoryFailureCode.UNAVAILABLE)


def _rollback_closed_error(session: Session, error: _ClosedRepositoryError) -> NoReturn:
    """回滚 closed domain error，并让 rollback failure 覆盖原错误。

    Args:
        session: 当前 Session。
        error: 原 closed error。

    Returns:
        永不返回。

    Raises:
        SourceSyncRepositoryFailure: rollback 失败时抛出 ``transaction_aborted``。
        SourceSyncRequestRejected: rollback 成功后保留原 request code。
        SourceSyncExecutionRejected: rollback 成功后保留原 execution code。
    """

    try:
        session.rollback()
    except (SQLAlchemyError, psycopg.Error):
        _raise_repository(SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)
    _close_after_settlement(session)
    raise error from None


def _open_session(session_factory: sessionmaker[Session]) -> Session:
    """创建 Session 并进入事务；尚未发生成功 repository SQL。

    Args:
        session_factory: 平台 Session factory。

    Returns:
        已 begin 的 Session。

    Raises:
        SourceSyncRepositoryFailure: factory/begin 数据库失败时按 admission 映射。
    """

    try:
        session = session_factory()
    except (SQLAlchemyError, psycopg.Error) as error:
        if _is_lock_failure(error):
            _raise_repository(SourceSyncRepositoryFailureCode.UNAVAILABLE)
        _raise_repository(SourceSyncRepositoryFailureCode.UNAVAILABLE)
    try:
        session.begin()
    except (SQLAlchemyError, psycopg.Error) as error:
        _rollback_database_failure(session, error, post_admission=False)
    return session


def _set_tenant_local(session: Session, tenant_id: TenantId) -> None:
    """以第一条 repository SQL 设置并核验 transaction-local tenant。

    Args:
        session: 当前 Session。
        tenant_id: 已校验租户标识。

    Returns:
        无。

    Raises:
        SourceSyncRepositoryFailure: SQL failure 或读回漂移时抛出。
    """

    try:
        value = session.execute(
            text(f"SELECT set_config('{TENANT_CONTEXT_SETTING}', :tenant_id, true)"),
            {"tenant_id": tenant_id.value},
        ).scalar_one()
    except (SQLAlchemyError, psycopg.Error) as error:
        _rollback_database_failure(session, error, post_admission=False)
    if value != tenant_id.value:
        _rollback_closed_error(
            session,
            SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT),
        )


def _commit_and_close(session: Session) -> None:
    """提交 post-admission 事务并关闭 Session。

    Args:
        session: 当前 Session。

    Returns:
        无。

    Raises:
        SourceSyncRepositoryFailure: commit/rollback/close 失败时按全序映射。
    """

    try:
        session.commit()
    except (SQLAlchemyError, psycopg.Error) as error:
        _rollback_database_failure(session, error, post_admission=True)
    _close_after_settlement(session)


def _rv(row: _SqlRow, key: str) -> _DbValue:
    """按列名读取 SQLAlchemy Row 的 closed 值。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        Closed DB value。

    Raises:
        KeyError: 列缺失时向上交给 persisted reconstruction 边界。
    """

    return row._mapping[key]


def _rv_text(row: _SqlRow, key: str) -> str:
    """读取文本或 UUID 列为 canonical 文本。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        文本值。

    Raises:
        ValueError: 类型非法时抛出。
    """

    value = _rv(row, key)
    if type(value) is str:
        return value
    if type(value) is UUID:
        return str(value)
    raise ValueError("persisted text shape")


def _rv_int(row: _SqlRow, key: str) -> int:
    """读取精确整数列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        整数值。

    Raises:
        ValueError: 类型非法时抛出。
    """

    value = _rv(row, key)
    if type(value) is not int:
        raise ValueError("persisted int shape")
    return value


def _rv_bool(row: _SqlRow, key: str) -> bool:
    """读取精确 bool 列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        Bool 值。

    Raises:
        ValueError: 类型非法时抛出。
    """

    value = _rv(row, key)
    if type(value) is not bool:
        raise ValueError("persisted bool shape")
    return value


def _rv_uuid(row: _SqlRow, key: str) -> UUID:
    """读取非零 UUID 列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        UUID 值。

    Raises:
        ValueError: 类型或零值非法时抛出。
    """

    value = _rv(row, key)
    if type(value) is UUID and value.int != 0:
        return value
    if type(value) is str:
        parsed = UUID(value)
        if parsed.int != 0 and str(parsed) == value:
            return parsed
    raise ValueError("persisted UUID shape")


def _rv_datetime(row: _SqlRow, key: str) -> datetime:
    """读取并归一化 aware UTC 时间列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        Aware UTC datetime。

    Raises:
        ValueError: 类型非法时抛出。
    """

    value = _rv(row, key)
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("persisted datetime shape")
    return value.astimezone(timezone.utc)


def _rv_date(row: _SqlRow, key: str) -> date:
    """读取精确 calendar date 列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        Calendar date。

    Raises:
        ValueError: 类型非法时抛出。
    """

    value = _rv(row, key)
    if type(value) is not date:
        raise ValueError("persisted date shape")
    return value


def _narrow_json(value: _DbJsonValue) -> JsonValue:
    """把 driver JSONB 值递归收窄为 canonical Job JSON union。

    Args:
        value: Driver JSON 值。

    Returns:
        Closed ``JsonValue`` 副本。

    Raises:
        ValueError: float、非法 key 或容器形态出现时抛出。
    """

    if value is None:
        return None
    if type(value) is str:
        return value
    if type(value) is int:
        return value
    if type(value) is bool:
        return value
    if type(value) is list:
        return [_narrow_json(item) for item in value]
    if type(value) is dict:
        result: dict[str, JsonValue] = {}
        for key, nested in value.items():
            if type(key) is not str:
                raise ValueError("persisted JSON key shape")
            result[key] = _narrow_json(nested)
        return result
    raise ValueError("persisted JSON value shape")


def _rv_json_object(row: _SqlRow, key: str) -> dict[str, JsonValue]:
    """读取 JSONB object 并递归收窄。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        Closed JSON object。

    Raises:
        ValueError: 列不是 strict object 时抛出。
    """

    value = _rv(row, key)
    if type(value) is not dict:
        raise ValueError("persisted JSON object shape")
    narrowed = _narrow_json(value)
    if type(narrowed) is not dict:
        raise ValueError("persisted JSON object shape")
    return narrowed


def _canonical_document_from_json(
    row: _SqlRow,
    *,
    json_key: str,
    sha_key: str,
    schema_name: str,
) -> CanonicalJobDocument:
    """从 JSONB 与 stored SHA 重建 canonical document。

    Args:
        row: 查询行。
        json_key: JSONB 列名。
        sha_key: Stored SHA 列名。
        schema_name: Canonical schema 名。

    Returns:
        重建并核验的 canonical document。

    Raises:
        ValueError: JSON、SHA 或 canonical bytes 漂移时抛出。
    """

    document = build_canonical_document(
        _rv_json_object(row, json_key),
        schema_name=schema_name,
        schema_version=1,
    )
    if document.sha256 != _rv_text(row, sha_key):
        raise ValueError("persisted canonical SHA drift")
    return document


def _parse_binding_rows(
    subscription_row: _SqlRow,
    definition_row: _SqlRow,
    security_row: _SqlRow,
) -> SourceExecutionBinding:
    """从三张持久化行严格构造 executable binding。

    Args:
        subscription_row: Subscription 行。
        definition_row: Source definition 行。
        security_row: Security 行。

    Returns:
        Strict execution binding。

    Raises:
        ValueError: 任一 identity/config/executable shape 非法时抛出。
    """

    if _rv(subscription_row, "company_id") is not None:
        raise ValueError("subscription must be security-target")
    subscription_security_id = _rv_uuid(subscription_row, "security_id")
    security_id = _rv_uuid(security_row, "id")
    if subscription_security_id != security_id:
        raise ValueError("security lineage drift")
    source_definition_id = _rv_uuid(subscription_row, "source_definition_id")
    if source_definition_id != _rv_uuid(definition_row, "id"):
        raise ValueError("source definition lineage drift")
    try:
        config_value = _rv_json_object(subscription_row, "config_json")
        config: FinsDisclosureSubscriptionConfig = parse_fins_disclosure_subscription_config(config_value)
        return SourceExecutionBinding(
            tenant_id=TenantId(_rv_text(subscription_row, "tenant_id")),
            source_definition_id=SourceDefinitionId(str(source_definition_id)),
            source_definition_version=_rv_int(definition_row, "version"),
            source_key=_rv_text(definition_row, "source_key"),
            source_kind=SourceKind(_rv_text(definition_row, "source_kind")),
            subscription_id=SourceSubscriptionId(str(_rv_uuid(subscription_row, "id"))),
            subscription_version=_rv_int(subscription_row, "version"),
            subscription_status=SubscriptionStatus(_rv_text(subscription_row, "status")),
            security_company_id=CompanyId(str(_rv_uuid(security_row, "company_id"))),
            security_id=SecurityId(str(security_id)),
            security_version=_rv_int(security_row, "version"),
            security_ticker=_rv_text(security_row, "ticker"),
            exchange_mic=_rv_text(security_row, "exchange_mic"),
            security_is_active=_rv_bool(security_row, "is_active"),
            connector_key=SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1,
            config=config,
        )
    except (TypeError, ValueError, KeyError):
        raise ValueError("persisted binding shape") from None


def _health_from_row(
    row: _SqlRow,
    *,
    tenant_id: TenantId,
    subscription_id: SourceSubscriptionId,
) -> SourceHealthProjection:
    """从 health head 行严格重建 projection。

    Args:
        row: Health head 行。
        tenant_id: Outer tenant identity。
        subscription_id: Outer subscription identity。

    Returns:
        Strict persisted health projection。

    Raises:
        ValueError: outer/row lineage 或 closed shape 漂移时抛出。
    """

    if _rv_text(row, "tenant_id") != tenant_id.value or _rv_text(row, "subscription_id") != subscription_id.value:
        raise ValueError("health lineage drift")
    error_value = _rv(row, "safe_error_code")
    if error_value is not None and type(error_value) is not str:
        raise ValueError("health error shape")
    return SourceHealthProjection(
        tenant_id=tenant_id,
        subscription_id=subscription_id,
        status=SourceHealthStatus(_rv_text(row, "status")),
        consecutive_failures=_rv_int(row, "consecutive_failures"),
        safe_error_code=SourceSyncErrorCode(error_value) if type(error_value) is str else None,
        version=_rv_int(row, "version"),
        last_source_sync_run_id=_rv_uuid(row, "last_source_sync_run_id"),
        observed_at=_rv_datetime(row, "observed_at"),
    )


def _virtual_health(tenant_id: TenantId, subscription_id: SourceSubscriptionId) -> SourceHealthProjection:
    """构造无 head 时的 virtual healthy projection。

    Args:
        tenant_id: Outer tenant identity。
        subscription_id: Subscription identity。

    Returns:
        Version-zero virtual projection。

    Raises:
        无。
    """

    return SourceHealthProjection(
        tenant_id=tenant_id,
        subscription_id=subscription_id,
        status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
        safe_error_code=None,
        version=0,
        last_source_sync_run_id=None,
        observed_at=None,
    )


def _execute_first(session: Session, statement: str, parameters: Mapping[str, _DbValue]) -> _SqlRow | None:
    """执行一条 raw SQL 并返回首行。

    Args:
        session: 当前 Session。
        statement: Schema-qualified SQL。
        parameters: Closed bind parameters。

    Returns:
        首行，或没有结果时返回 ``None``。

    Raises:
        SQLAlchemyError: Driver/SQL 失败时向事务边界传播。
    """

    return session.execute(text(statement), dict(parameters)).first()


def _execute_all(session: Session, statement: str, parameters: Mapping[str, _DbValue]) -> list[_SqlRow]:
    """执行一条 raw SQL 并返回全部行。

    Args:
        session: 当前 Session。
        statement: Schema-qualified SQL。
        parameters: Closed bind parameters。

    Returns:
        结果行列表。

    Raises:
        SQLAlchemyError: Driver/SQL 失败时向事务边界传播。
    """

    return list(session.execute(text(statement), dict(parameters)).all())


def _descriptor_from_row(row: _SqlRow) -> JobHandlerDescriptor:
    """从 locked job definition 行重建 immutable descriptor。

    Args:
        row: Job definition 行。

    Returns:
        Durable descriptor。

    Raises:
        ValueError: 字段类型或 descriptor shape 漂移时抛出。
    """

    return JobHandlerDescriptor(
        job_type=_rv_text(row, "job_type"),
        payload_schema_name=_rv_text(row, "payload_schema_name"),
        payload_schema_version=_rv_int(row, "payload_schema_version"),
        max_attempts=_rv_int(row, "max_attempts"),
        retry_base_seconds=_rv_int(row, "retry_base_seconds"),
        retry_max_seconds=_rv_int(row, "retry_max_seconds"),
        lease_duration_seconds=_rv_int(row, "lease_duration_seconds"),
    )


def _payload_from_job_row(row: _SqlRow) -> ManualSourceSyncPayload | ScheduledSourceSyncPayload:
    """从 locked job payload bytes/hash strict parse Source payload。

    Args:
        row: Job run 行。

    Returns:
        Strict manual 或 scheduled payload。

    Raises:
        ValueError: bytes、hash、schema 或 payload shape 漂移时抛出。
    """

    raw_bytes = _rv(row, "payload_bytes")
    if isinstance(raw_bytes, memoryview):
        payload_bytes = raw_bytes.tobytes()
    elif type(raw_bytes) is bytes:
        payload_bytes = raw_bytes
    else:
        raise ValueError("persisted payload bytes shape")
    document = CanonicalJobDocument(
        schema_name=_rv_text(row, "request_payload_schema_name"),
        schema_version=_rv_int(row, "request_payload_schema_version"),
        canonical_bytes=payload_bytes,
        sha256=_rv_text(row, "payload_sha256"),
    )
    return parse_source_sync_payload(document)


def _lock_job_context(
    session: Session,
    tenant_id: TenantId,
    *,
    job_id: UUID,
    attempt_id: UUID,
) -> _LockedJobContext:
    """按前五步固定 NOWAIT 顺序锁 Job/definition/attempt/lease/operation。

    Args:
        session: 已设置 tenant 的事务 Session。
        tenant_id: Trusted tenant identity。
        job_id: Caller Job UUID。
        attempt_id: Caller attempt UUID。

    Returns:
        五锁 durable Job context。

    Raises:
        SourceSyncRequestRejected: Job/definition lineage 不匹配时抛出。
        SourceSyncExecutionRejected: Attempt/lease identity 丢失时抛出。
        SourceSyncRepositoryFailure: Persisted impossible shape 时抛出。
        SQLAlchemyError: NOWAIT 或 statement 失败时向事务边界传播。
    """

    common = {"tenant_id": tenant_id.value, "job_id": job_id}
    job_row = _execute_first(
        session,
        f"SELECT * FROM {_SCHEMA}.job_runs WHERE tenant_id = :tenant_id AND id = :job_id FOR UPDATE NOWAIT",
        common,
    )
    if job_row is None:
        _raise_request(SourceSyncRequestRejectionCode.JOB_LINEAGE_MISMATCH)
    definition_id = _rv_uuid(job_row, "definition_id")
    definition_row = _execute_first(
        session,
        f"SELECT * FROM {_SCHEMA}.job_definitions "
        "WHERE tenant_id = :tenant_id AND id = :definition_id FOR UPDATE NOWAIT",
        {"tenant_id": tenant_id.value, "definition_id": definition_id},
    )
    if definition_row is None:
        _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    current_attempt_number = _rv_int(job_row, "current_attempt_number")
    attempt_row = _execute_first(
        session,
        f"SELECT * FROM {_SCHEMA}.job_attempts WHERE tenant_id = :tenant_id "
        "AND job_run_id = :job_id AND attempt_number = :attempt_number FOR UPDATE NOWAIT",
        {"tenant_id": tenant_id.value, "job_id": job_id, "attempt_number": current_attempt_number},
    )
    if attempt_row is None:
        _raise_execution(SourceSyncExecutionRejectionCode.LEASE_LOST)
    locked_attempt_id = _rv_uuid(attempt_row, "id")
    lease_row = _execute_first(
        session,
        f"SELECT * FROM {_SCHEMA}.job_leases WHERE tenant_id = :tenant_id "
        "AND attempt_id = :attempt_id AND fence = :fence FOR UPDATE NOWAIT",
        {
            "tenant_id": tenant_id.value,
            "attempt_id": locked_attempt_id,
            "fence": _rv_int(attempt_row, "fence"),
        },
    )
    if lease_row is None:
        _raise_execution(SourceSyncExecutionRejectionCode.LEASE_LOST)
    operation_row = _execute_first(
        session,
        f"SELECT * FROM {_SCHEMA}.source_sync_operations WHERE tenant_id = :tenant_id "
        "AND job_run_id = :job_id FOR UPDATE NOWAIT",
        common,
    )
    try:
        descriptor = _descriptor_from_row(definition_row)
        payload = _payload_from_job_row(job_row)
    except (TypeError, ValueError, KeyError):
        _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    if descriptor != SOURCE_SYNC_JOB_DESCRIPTOR:
        _raise_request(SourceSyncRequestRejectionCode.JOB_LINEAGE_MISMATCH)
    return _LockedJobContext(
        job_row=job_row,
        definition_row=definition_row,
        attempt_row=attempt_row,
        lease_row=lease_row,
        operation_row=operation_row,
        payload=payload,
    )


def _lock_source_context(
    session: Session,
    tenant_id: TenantId,
    subscription_id: SourceSubscriptionId,
) -> _LockedSourceContext:
    """按后四步固定 NOWAIT 顺序锁 subscription/definition/security/health。

    Args:
        session: 当前 transaction Session。
        tenant_id: Trusted tenant identity。
        subscription_id: Subscription identity。

    Returns:
        四锁 Source context。

    Raises:
        SourceSyncRequestRejected: Subscription missing 或 binding 不可执行时抛出。
        SourceSyncRepositoryFailure: Persisted lineage 不可能时抛出。
        SQLAlchemyError: NOWAIT 或 statement 失败时向事务边界传播。
    """

    subscription_row = _execute_first(
        session,
        f"SELECT * FROM {_SCHEMA}.source_subscriptions WHERE tenant_id = :tenant_id "
        "AND id = :subscription_id FOR UPDATE NOWAIT",
        {"tenant_id": tenant_id.value, "subscription_id": subscription_id.value},
    )
    if subscription_row is None:
        _raise_request(SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND)
    definition_row = _execute_first(
        session,
        f"SELECT * FROM {_SCHEMA}.source_definitions WHERE id = :definition_id FOR UPDATE NOWAIT",
        {"definition_id": _rv_uuid(subscription_row, "source_definition_id")},
    )
    if definition_row is None:
        _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    security_value = _rv(subscription_row, "security_id")
    if security_value is None:
        _raise_request(SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE)
    security_id = _rv_uuid(subscription_row, "security_id")
    security_row = _execute_first(
        session,
        f"SELECT * FROM {_SCHEMA}.securities WHERE id = :security_id FOR UPDATE NOWAIT",
        {"security_id": security_id},
    )
    if security_row is None:
        _raise_request(SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE)
    health_row = _execute_first(
        session,
        f"SELECT * FROM {_SCHEMA}.source_health_states WHERE tenant_id = :tenant_id "
        "AND subscription_id = :subscription_id FOR UPDATE NOWAIT",
        {"tenant_id": tenant_id.value, "subscription_id": subscription_id.value},
    )
    return _LockedSourceContext(
        subscription_row=subscription_row,
        source_definition_row=definition_row,
        security_row=security_row,
        health_row=health_row,
    )


def _clock_after_all_locks(session: Session) -> datetime:
    """在全部潜在锁成功后读取唯一 raw PG clock。

    Args:
        session: 当前 Session。

    Returns:
        Aware UTC raw clock。

    Raises:
        ValueError: Driver 返回非时间值时抛出。
        SQLAlchemyError: Clock SQL 失败时向事务边界传播。
    """

    value = session.execute(text("SELECT clock_timestamp()")).scalar_one()
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("persisted clock shape")
    return value.astimezone(timezone.utc)


def _validate_locked_job_live(
    context: _LockedJobContext,
    *,
    job_id: UUID,
    attempt_id: UUID,
    attempt_number: int,
    raw_clock: datetime,
) -> None:
    """按 locked Job/attempt/lease 与 raw clock 验证唯一 live truth。

    Args:
        context: 五锁 durable context。
        job_id: Caller Job UUID。
        attempt_id: Caller attempt UUID。
        attempt_number: Caller attempt number。
        raw_clock: 全锁后的 raw PG clock。

    Returns:
        无。

    Raises:
        SourceSyncRequestRejected: Caller job lineage 不一致时抛出。
        SourceSyncExecutionRejected: Job 或 lease 不再 live 时抛出。
        SourceSyncRepositoryFailure: Persisted lease pairing 不可能时抛出。
    """

    job_row = context.job_row
    attempt_row = context.attempt_row
    lease_row = context.lease_row
    if _rv_uuid(job_row, "id") != job_id or _rv_uuid(attempt_row, "job_run_id") != job_id:
        _raise_request(SourceSyncRequestRejectionCode.JOB_LINEAGE_MISMATCH)
    if _rv_text(job_row, "state") != "leased" or _rv(job_row, "cancel_requested_at") is not None:
        _raise_execution(SourceSyncExecutionRejectionCode.JOB_NOT_LIVE)
    if _rv_datetime(job_row, "deadline_at") <= raw_clock:
        _raise_execution(SourceSyncExecutionRejectionCode.JOB_NOT_LIVE)
    if _rv_int(job_row, "current_attempt_number") != attempt_number:
        _raise_execution(SourceSyncExecutionRejectionCode.LEASE_LOST)
    if (
        _rv_uuid(attempt_row, "id") != attempt_id
        or _rv_int(attempt_row, "attempt_number") != attempt_number
        or _rv_text(attempt_row, "state") != "leased"
        or _rv_datetime(attempt_row, "lease_expires_at") <= raw_clock
    ):
        _raise_execution(SourceSyncExecutionRejectionCode.LEASE_LOST)
    if _rv_uuid(lease_row, "job_run_id") != job_id or _rv_uuid(lease_row, "attempt_id") != attempt_id:
        _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    if (
        _rv_int(lease_row, "fence") != _rv_int(attempt_row, "fence")
        or _rv_text(lease_row, "token_sha256") != _rv_text(attempt_row, "lease_token_sha256")
    ):
        _raise_execution(SourceSyncExecutionRejectionCode.LEASE_LOST)
    if _rv(lease_row, "released_at") is not None:
        _raise_execution(SourceSyncExecutionRejectionCode.LEASE_LOST)


def _locked_subscription_id(payload: ManualSourceSyncPayload | ScheduledSourceSyncPayload) -> SourceSubscriptionId:
    """读取 closed payload 的 subscription identity。

    Args:
        payload: Strict Source payload。

    Returns:
        Subscription 强标识。

    Raises:
        无。
    """

    return payload.subscription_id


def _binding_disposition(
    binding: SourceExecutionBinding,
    snapshot: SourceExecutionSnapshot,
    health: SourceHealthProjection,
) -> SourceBindingDisposition:
    """比较 frozen snapshot、current binding 与 health 得到 acquire disposition。

    Args:
        binding: Current locked executable binding。
        snapshot: Frozen operation snapshot。
        health: Locked/virtual health projection。

    Returns:
        Ready、disabled 或 stale。

    Raises:
        无。
    """

    frozen = snapshot.binding
    if frozen != binding:
        return SourceBindingDisposition.STALE
    if binding.subscription_status is SubscriptionStatus.DISABLED or health.status is SourceHealthStatus.DISABLED:
        return SourceBindingDisposition.DISABLED
    return SourceBindingDisposition.READY


def _snapshot_document_from_operation(row: _SqlRow) -> CanonicalJobDocument:
    """从 operation JSONB/SHA 重建 frozen snapshot document。

    Args:
        row: Operation 行。

    Returns:
        Canonical snapshot document。

    Raises:
        ValueError: JSONB/canonical/SHA 漂移时抛出。
    """

    return _canonical_document_from_json(
        row,
        json_key="execution_snapshot_json",
        sha_key="execution_snapshot_sha256",
        schema_name=SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME,
    )


def _parse_operation_snapshot(row: _SqlRow) -> SourceExecutionSnapshot:
    """从 operation 行 strict parse execution snapshot。

    Args:
        row: Operation 行。

    Returns:
        Strict snapshot DTO。

    Raises:
        ValueError: Canonical 或 typed parse 漂移时抛出。
    """

    return parse_source_execution_snapshot_document(_snapshot_document_from_operation(row))


def _rv_optional_uuid(row: _SqlRow, key: str) -> UUID | None:
    """读取可空 UUID 列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        UUID 值，或数据库值为空时返回 ``None``。

    Raises:
        ValueError: 非空值不是 canonical UUID 时抛出。
    """

    if _rv(row, key) is None:
        return None
    return _rv_uuid(row, key)


def _rv_optional_int(row: _SqlRow, key: str) -> int | None:
    """读取可空精确整数列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        整数值，或数据库值为空时返回 ``None``。

    Raises:
        ValueError: 非空值不是精确整数时抛出。
    """

    if _rv(row, key) is None:
        return None
    return _rv_int(row, key)


def _rv_optional_datetime(row: _SqlRow, key: str) -> datetime | None:
    """读取可空 aware UTC 时间列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        Aware UTC 时间，或数据库值为空时返回 ``None``。

    Raises:
        ValueError: 非空值不是时间时抛出。
    """

    if _rv(row, key) is None:
        return None
    return _rv_datetime(row, key)


def _rv_optional_date(row: _SqlRow, key: str) -> date | None:
    """读取可空 calendar date 列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        Calendar date，或数据库值为空时返回 ``None``。

    Raises:
        ValueError: 非空值不是精确 date 时抛出。
    """

    if _rv(row, key) is None:
        return None
    return _rv_date(row, key)


def _rv_optional_error(row: _SqlRow, key: str) -> SourceSyncErrorCode | None:
    """读取可空 closed Source error 列。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        Closed error，或数据库值为空时返回 ``None``。

    Raises:
        ValueError: 非空值不是 closed error 时抛出。
    """

    if _rv(row, key) is None:
        return None
    return SourceSyncErrorCode(_rv_text(row, key))


def _canonical_json_text(document: CanonicalJobDocument) -> str:
    """把已验证 canonical document 转为 UTF-8 JSON 文本供 JSONB bind 使用。

    Args:
        document: Canonical document。

    Returns:
        Canonical UTF-8 JSON 文本。

    Raises:
        ValueError: Canonical bytes 不是 UTF-8 时抛出。
    """

    try:
        return document.canonical_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("canonical document 必须是 UTF-8") from None


def _current_health(
    context: _LockedSourceContext,
    *,
    tenant_id: TenantId,
    subscription_id: SourceSubscriptionId,
) -> SourceHealthProjection:
    """从 locked source context 读取持久化或 virtual health。

    Args:
        context: Locked source context。
        tenant_id: Trusted tenant identity。
        subscription_id: Subscription identity。

    Returns:
        Current persisted 或 virtual health projection。

    Raises:
        ValueError: Persisted health shape 漂移时抛出。
    """

    if context.health_row is None:
        return _virtual_health(tenant_id, subscription_id)
    return _health_from_row(
        context.health_row,
        tenant_id=tenant_id,
        subscription_id=subscription_id,
    )


def _snapshot_from_row(
    row: _SqlRow,
    *,
    tenant_id: TenantId,
    subscription_id: SourceSubscriptionId,
) -> SourceHealthSnapshotProjection:
    """从持久化行严格重建 health snapshot。

    Args:
        row: Snapshot 查询行。
        tenant_id: Outer tenant identity。
        subscription_id: Outer subscription identity。

    Returns:
        Strict snapshot projection。

    Raises:
        ValueError: Lineage 或 closed shape 漂移时抛出。
    """

    if _rv_text(row, "tenant_id") != tenant_id.value:
        raise ValueError("snapshot tenant lineage drift")
    if _rv_text(row, "subscription_id") != subscription_id.value:
        raise ValueError("snapshot subscription lineage drift")
    return SourceHealthSnapshotProjection(
        snapshot_id=_rv_uuid(row, "id"),
        tenant_id=tenant_id,
        subscription_id=subscription_id,
        source_sync_run_id=_rv_optional_uuid(row, "sync_run_id"),
        health_state_version=_rv_optional_int(row, "health_state_version"),
        status=SourceHealthStatus(_rv_text(row, "status")),
        consecutive_failures=_rv_int(row, "consecutive_failures"),
        latency_ms=_rv_optional_int(row, "latency_ms"),
        safe_error_code=_rv_optional_error(row, "safe_error_code"),
        observed_at=_rv_datetime(row, "observed_at"),
        created_at=_rv_datetime(row, "created_at"),
    )


def _alert_from_row(row: _SqlRow) -> SourceAlertOutboxEvent:
    """从 conflict reread 行严格重建 semantic alert。

    Args:
        row: Alert outbox 查询行。

    Returns:
        Strict alert event。

    Raises:
        ValueError: Canonical、hash、lineage 或 closed shape 漂移时抛出。
    """

    return SourceAlertOutboxEvent(
        event_id=_rv_uuid(row, "id"),
        tenant_id=TenantId(_rv_text(row, "tenant_id")),
        subscription_id=SourceSubscriptionId(_rv_text(row, "subscription_id")),
        source_sync_run_id=_rv_uuid(row, "source_sync_run_id"),
        health_snapshot_id=_rv_uuid(row, "health_snapshot_id"),
        health_state_version=_rv_int(row, "health_state_version"),
        alert_kind=SourceAlertKind(_rv_text(row, "alert_kind")),
        target_status=SourceHealthStatus(_rv_text(row, "target_status")),
        safe_error_code=SourceSyncErrorCode(_rv_text(row, "safe_error_code")),
        dedupe_key=_rv_text(row, "dedupe_key"),
        created_at=_rv_datetime(row, "created_at"),
        event=_canonical_document_from_json(
            row,
            json_key="event_json",
            sha_key="event_sha256",
            schema_name=SOURCE_HEALTH_ALERT_SCHEMA_NAME,
        ),
    )


def _expected_run_status(outcome: SourceSyncOutcome) -> str:
    """把 Source outcome 映射为既有 source run status。

    Args:
        outcome: Closed Source outcome。

    Returns:
        ``succeeded`` 或 ``failed``。

    Raises:
        无。
    """

    if outcome in {
        SourceSyncOutcome.SUCCEEDED,
        SourceSyncOutcome.NO_CHANGE,
        SourceSyncOutcome.PARTIAL,
        SourceSyncOutcome.SKIPPED_DISABLED,
    }:
        return "succeeded"
    return "failed"


def _rebuild_run_artifacts(
    row: _SqlRow,
    *,
    tenant_id: TenantId,
) -> tuple[SourceSyncAttemptReceipt, SourceSyncResult]:
    """从 v1 source run 重建并交叉核验 receipt/result 与 outer columns。

    Args:
        row: V1 source run 行。
        tenant_id: Outer tenant identity。

    Returns:
        ``(receipt, result)``。

    Raises:
        ValueError: Canonical、SHA、outcome、count、time 或 lineage 漂移时抛出。
    """

    receipt_document = _canonical_document_from_json(
        row,
        json_key="receipt_json",
        sha_key="receipt_sha256",
        schema_name=SOURCE_SYNC_RECEIPT_SCHEMA_NAME,
    )
    result_document = _canonical_document_from_json(
        row,
        json_key="result_json",
        sha_key="result_sha256",
        schema_name=SOURCE_SYNC_RESULT_SCHEMA_NAME,
    )
    receipt = parse_source_sync_attempt_receipt(tenant_id=tenant_id, receipt=receipt_document)
    result = parse_source_sync_result(result_document)
    run_id = _rv_uuid(row, "id")
    subscription_id = SourceSubscriptionId(str(_rv_uuid(row, "subscription_id")))
    job_id = _rv_uuid(row, "job_run_id")
    attempt_id = _rv_uuid(row, "job_attempt_id")
    outcome = SourceSyncOutcome(_rv_text(row, "outcome"))
    if (
        _rv_text(row, "tenant_id") != tenant_id.value
        or receipt.source_sync_run_id != run_id
        or receipt.subscription_id != subscription_id
        or receipt.job_id != job_id
        or receipt.producer_attempt_id != attempt_id
        or receipt.payload_sha256 != _rv_text(row, "payload_sha256")
        or receipt.outcome is not outcome
        or receipt.retry_recommended != _rv_bool(row, "retry_recommended")
        or receipt.records_discovered != _rv_int(row, "records_discovered")
        or receipt.records_ingested != _rv_int(row, "records_ingested")
        or receipt.records_downloaded != _rv_int(row, "records_downloaded")
        or receipt.records_reused != _rv_int(row, "records_reused")
        or receipt.records_ignored != _rv_int(row, "records_ignored")
        or receipt.records_failed != _rv_int(row, "records_failed")
        or receipt.latest_source_observed_date != _rv_optional_date(row, "latest_source_observed_date")
        or receipt.safe_error_code is not _rv_optional_error(row, "safe_error_code")
        or receipt.started_at != _rv_datetime(row, "started_at")
        or receipt.finished_at != _rv_datetime(row, "finished_at")
        or _rv_text(row, "status") != _expected_run_status(outcome)
        or _rv_text(row, "idempotency_key") != f"source-sync-attempt:v1:{job_id}:{attempt_id}"
    ):
        raise ValueError("source run outer lineage drift")
    if (
        result.outcome is not receipt.outcome
        or result.source_sync_run_id != receipt.source_sync_run_id
        or result.producer_attempt_id != receipt.producer_attempt_id
        or result.source_receipt_sha256 != receipt.receipt.sha256
        or result.retry_recommended != receipt.retry_recommended
    ):
        raise ValueError("source result/receipt lineage drift")
    return receipt, result


def _core_presence(row: _SqlRow) -> tuple[bool, bool]:
    """判断 source run 13-core 是否全空或全满。

    Args:
        row: Source run 行。

    Returns:
        ``(all_null, all_present)``。

    Raises:
        无。
    """

    presence = tuple(_rv(row, column) is not None for column in _SOURCE_RUN_CORE_COLUMNS)
    return not any(presence), all(presence)


def _validate_acquire_input(request: SourceOperationAcquireRequest) -> None:
    """在零 SQL 边界校验 acquire request exact runtime 类型。

    Args:
        request: Caller request。

    Returns:
        无。

    Raises:
        SourceSyncRequestRejected: Runtime 类型非法时抛出 ``invalid_input``。
    """

    if type(request) is not SourceOperationAcquireRequest:
        _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)


def _validate_terminal_input(request: SourceTerminalRecordRequest) -> None:
    """在零 SQL 边界校验 terminal request exact runtime 类型。

    Args:
        request: Caller request。

    Returns:
        无。

    Raises:
        SourceSyncRequestRejected: Runtime 类型非法时抛出 ``invalid_input``。
    """

    if type(request) is not SourceTerminalRecordRequest:
        _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)


def _validate_acquire_job_lineage(
    context: _LockedJobContext,
    request: SourceOperationAcquireRequest,
    tenant_id: TenantId,
) -> None:
    """校验 caller acquire 与 locked durable Job/payload 的 exact lineage。

    Args:
        context: Locked Job context。
        request: Caller acquire request。
        tenant_id: Trusted tenant identity。

    Returns:
        无。

    Raises:
        SourceSyncRequestRejected: Job、payload 或 snapshot lineage 漂移时抛出。
    """

    if (
        _rv_text(context.job_row, "tenant_id") != tenant_id.value
        or _rv_uuid(context.job_row, "definition_id") != request.definition_id
        or _descriptor_from_row(context.definition_row) != request.descriptor
    ):
        _raise_request(SourceSyncRequestRejectionCode.JOB_LINEAGE_MISMATCH)
    if _rv_text(context.job_row, "payload_sha256") != request.payload_sha256:
        _raise_request(SourceSyncRequestRejectionCode.PAYLOAD_HASH_MISMATCH)
    payload = context.payload
    if request.origin is SourceSyncOrigin.MANUAL:
        if not isinstance(payload, ManualSourceSyncPayload):
            _raise_request(SourceSyncRequestRejectionCode.PAYLOAD_HASH_MISMATCH)
        candidate = request.candidate_execution_snapshot
        if candidate != payload.execution_snapshot:
            _raise_request(SourceSyncRequestRejectionCode.SNAPSHOT_MISMATCH)
        expected = build_source_execution_snapshot(
            payload.execution_snapshot.binding,
            _rv_datetime(context.job_row, "original_available_at"),
        )
        if expected != payload.execution_snapshot or payload.execution_snapshot.binding.tenant_id != tenant_id:
            _raise_request(SourceSyncRequestRejectionCode.SNAPSHOT_MISMATCH)
    elif not isinstance(payload, ScheduledSourceSyncPayload):
        _raise_request(SourceSyncRequestRejectionCode.PAYLOAD_HASH_MISMATCH)


def _validate_operation_lineage(
    row: _SqlRow,
    *,
    tenant_id: TenantId,
    job_id: UUID,
    subscription_id: SourceSubscriptionId,
    payload_sha256: str,
) -> None:
    """校验 operation 与 locked Job/subscription 的 persisted lineage。

    Args:
        row: Locked operation 行。
        tenant_id: Trusted tenant identity。
        job_id: Locked Job identity。
        subscription_id: Payload subscription identity。
        payload_sha256: Locked payload SHA。

    Returns:
        无。

    Raises:
        SourceSyncRepositoryFailure: Persisted cross-lineage 漂移时抛出。
    """

    if (
        _rv_text(row, "tenant_id") != tenant_id.value
        or _rv_uuid(row, "job_run_id") != job_id
        or _rv_text(row, "subscription_id") != subscription_id.value
        or _rv_text(row, "payload_sha256") != payload_sha256
    ):
        _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)


def _validate_operation_snapshot_provenance(
    context: _LockedJobContext,
    *,
    tenant_id: TenantId,
    snapshot: SourceExecutionSnapshot,
    snapshot_sha256: str,
) -> None:
    """把 persisted operation snapshot 锚定到 locked payload 与 Job clock。

    Args:
        context: Locked durable Job context。
        tenant_id: Trusted tenant identity。
        snapshot: Persisted operation snapshot。
        snapshot_sha256: Persisted operation canonical SHA。

    Returns:
        无。

    Raises:
        SourceSyncRepositoryFailure: Snapshot provenance 不闭合时抛出。
    """

    payload = context.payload
    if (
        snapshot.binding.tenant_id != tenant_id
        or snapshot.binding.subscription_id != payload.subscription_id
    ):
        _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    available_at = _rv_datetime(context.job_row, "original_available_at")
    if isinstance(payload, ManualSourceSyncPayload):
        expected = payload.execution_snapshot
        if build_source_execution_snapshot(expected.binding, available_at) != expected:
            _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    else:
        if snapshot.binding.source_definition_id != payload.source_definition_id:
            _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
        expected = build_source_execution_snapshot(snapshot.binding, available_at)
    expected_document = build_source_execution_snapshot_document(expected)
    if snapshot != expected or snapshot_sha256 != expected_document.sha256:
        _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)


def _terminal_execution_decision(
    code: SourceSyncExecutionRejectionCode,
) -> SourceTerminalRecordDecision:
    """把 pre-DML execution rejection 收敛为 terminal closed decision。

    Args:
        code: Locked live validation 的精确 rejection code。

    Returns:
        全空 terminal decision。

    Raises:
        SourceSyncRepositoryFailure: 未知 execution code 时 fail closed。
    """

    if code is SourceSyncExecutionRejectionCode.JOB_NOT_LIVE:
        action = SourceTerminalRecordAction.JOB_NOT_LIVE
    elif code is SourceSyncExecutionRejectionCode.LEASE_LOST:
        action = SourceTerminalRecordAction.LEASE_LOST
    else:
        _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    return SourceTerminalRecordDecision(
        action=action,
        result=None,
        receipt=None,
        health_after=None,
        health_snapshot=None,
        alert_event=None,
    )


def _disposition_for_snapshot(
    context: _LockedSourceContext,
    snapshot: SourceExecutionSnapshot,
    health: SourceHealthProjection,
) -> SourceBindingDisposition:
    """比较 current locked rows 与 frozen snapshot 派生 acquire disposition。

    Args:
        context: Locked source context。
        snapshot: Frozen execution snapshot。
        health: Current persisted 或 virtual health。

    Returns:
        Ready、disabled 或 stale。

    Raises:
        无。
    """

    try:
        binding = _parse_binding_rows(
            context.subscription_row,
            context.source_definition_row,
            context.security_row,
        )
    except (TypeError, ValueError, KeyError):
        return SourceBindingDisposition.STALE
    return _binding_disposition(binding, snapshot, health)


@dataclass(frozen=True, slots=True)
class _FinalObservation:
    """Repository authoritative terminal observation 的闭合中间值。"""

    outcome: SourceSyncOutcome
    safe_error_code: SourceSyncErrorCode | None
    retry_recommended: bool
    documents: tuple[SourceDocumentEvidence, ...]
    records_discovered: int
    records_downloaded: int
    records_reused: int
    records_ignored: int
    records_failed: int
    latest_source_observed_date: date | None


def _final_observation(
    *,
    candidate: SourceFinsTerminalCandidate | SourceNoProviderTerminalCandidate,
    stored_disposition: SourceBindingDisposition,
    current_disposition: SourceBindingDisposition,
    snapshot: SourceExecutionSnapshot,
    authoritative_utc_date: date,
) -> _FinalObservation:
    """验证 candidate/disposition 并派生 freshness/drift 后的 authoritative observation。

    Args:
        candidate: Caller closed terminal candidate。
        stored_disposition: Acquire generation 持久化 disposition。
        current_disposition: Terminal revalidation disposition。
        snapshot: Frozen execution snapshot。
        authoritative_utc_date: PG authoritative UTC date。

    Returns:
        Authoritative terminal observation。

    Raises:
        ValueError: Candidate 与 stored disposition 或 evidence identity 不闭合时抛出。
    """

    if stored_disposition is SourceBindingDisposition.READY:
        if not isinstance(candidate, SourceFinsTerminalCandidate):
            raise ValueError("ready operation 必须提交 Fins candidate")
        for evidence in candidate.documents:
            validate_evidence_against_snapshot(evidence, snapshot)
    elif stored_disposition is SourceBindingDisposition.DISABLED:
        if not isinstance(candidate, SourceNoProviderTerminalCandidate):
            raise ValueError("disabled operation 必须提交 no-provider candidate")
        if candidate.reason is not SourceNoProviderReason.DISABLED:
            raise ValueError("disabled operation reason 漂移")
    else:
        if not isinstance(candidate, SourceNoProviderTerminalCandidate):
            raise ValueError("stale operation 必须提交 no-provider candidate")
        if candidate.reason is not SourceNoProviderReason.BINDING_DRIFT:
            raise ValueError("stale operation reason 漂移")
    if stored_disposition is SourceBindingDisposition.STALE or current_disposition is SourceBindingDisposition.STALE:
        return _FinalObservation(
            outcome=SourceSyncOutcome.STALE_SUBSCRIPTION,
            safe_error_code=SourceSyncErrorCode.STALE_SUBSCRIPTION,
            retry_recommended=False,
            documents=(),
            records_discovered=0,
            records_downloaded=0,
            records_reused=0,
            records_ignored=0,
            records_failed=0,
            latest_source_observed_date=None,
        )
    if stored_disposition is SourceBindingDisposition.DISABLED:
        return _FinalObservation(
            outcome=SourceSyncOutcome.SKIPPED_DISABLED,
            safe_error_code=None,
            retry_recommended=False,
            documents=(),
            records_discovered=0,
            records_downloaded=0,
            records_reused=0,
            records_ignored=0,
            records_failed=0,
            latest_source_observed_date=None,
        )
    if not isinstance(candidate, SourceFinsTerminalCandidate):
        raise ValueError("ready operation candidate 类型漂移")
    outcome = candidate.proposed_outcome
    error = candidate.proposed_safe_error_code
    retry = outcome is SourceSyncOutcome.PARTIAL or error in {
        SourceSyncErrorCode.PROVIDER_RATE_LIMITED,
        SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
    }
    if candidate.documents and is_source_observation_stale(
        outcome=outcome,
        latest_source_observed_date=candidate.latest_source_observed_date,
        authoritative_utc_date=authoritative_utc_date,
        freshness_max_age_days=snapshot.binding.config.freshness_max_age_days,
    ):
        outcome = SourceSyncOutcome.FAILED
        error = SourceSyncErrorCode.STALE_DATA
        retry = False
    return _FinalObservation(
        outcome=outcome,
        safe_error_code=error,
        retry_recommended=retry,
        documents=candidate.documents,
        records_discovered=candidate.records_discovered,
        records_downloaded=candidate.records_downloaded,
        records_reused=candidate.records_reused,
        records_ignored=candidate.records_ignored,
        records_failed=candidate.records_failed,
        latest_source_observed_date=candidate.latest_source_observed_date,
    )


class PostgresSourceSyncRepository(SourceSyncRepositoryProtocol):
    """PostgreSQL Source Sync 的唯一 concrete repository。

    Args:
        session_factory: 平台共用的 SQLAlchemy Session factory。
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """保存唯一 transaction factory，构造期不创建 Session 或执行 SQL。

        Args:
            session_factory: 平台共用的 SQLAlchemy Session factory。

        Returns:
            无。

        Raises:
            无。
        """

        self._session_factory = session_factory

    def get_executable_binding(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceExecutionBinding:
        """读取租户内 strict executable Source binding。

        Args:
            scope: Trusted tenant scope。
            subscription_id: Source subscription identity。

        Returns:
            Strict executable binding；subscription 可以 enabled 或 disabled。

        Raises:
            SourceSyncRequestRejected: 输入、missing 或 binding 不可执行时抛出。
            SourceSyncRepositoryFailure: 事务或持久化不变量失败时抛出。
        """

        tenant_id = _validate_scope(scope)
        subscription_value = _validate_subscription_id(subscription_id)
        session = _open_session(self._session_factory)
        _set_tenant_local(session, tenant_id)
        try:
            subscription_row = _execute_first(
                session,
                f"SELECT * FROM {_SCHEMA}.source_subscriptions "
                "WHERE tenant_id = :tenant_id AND id = :subscription_id",
                {"tenant_id": tenant_id.value, "subscription_id": subscription_value},
            )
            if subscription_row is None:
                _raise_request(SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND)
            definition_row = _execute_first(
                session,
                f"SELECT * FROM {_SCHEMA}.source_definitions WHERE id = :definition_id",
                {"definition_id": _rv_uuid(subscription_row, "source_definition_id")},
            )
            if definition_row is None:
                _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
            if _rv(subscription_row, "security_id") is None:
                _raise_request(SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE)
            security_row = _execute_first(
                session,
                f"SELECT * FROM {_SCHEMA}.securities WHERE id = :security_id",
                {"security_id": _rv_uuid(subscription_row, "security_id")},
            )
            if security_row is None:
                _raise_request(SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE)
            try:
                binding = _parse_binding_rows(subscription_row, definition_row, security_row)
            except (TypeError, ValueError, KeyError):
                _raise_request(SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE)
            if binding.tenant_id != tenant_id or binding.subscription_id != subscription_id:
                _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
        except (SourceSyncRequestRejected, SourceSyncExecutionRejected, SourceSyncRepositoryFailure) as error:
            _rollback_closed_error(session, error)
        except (SQLAlchemyError, psycopg.Error) as error:
            _rollback_database_failure(session, error, post_admission=True)
        except (TypeError, ValueError, KeyError):
            _rollback_closed_error(
                session,
                SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT),
            )
        _commit_and_close(session)
        return binding

    def acquire_operation(
        self,
        scope: TenantScope,
        request: SourceOperationAcquireRequest,
    ) -> SourceOperationAcquireDecision:
        """按固定 NOWAIT 锁序 acquire、busy 或 terminal replay operation。

        Args:
            scope: Trusted tenant scope。
            request: Strict acquire request。

        Returns:
            Acquired、busy 或 terminal replay decision。

        Raises:
            SourceSyncRequestRejected: 输入或 durable request lineage 不匹配时抛出。
            SourceSyncExecutionRejected: Job 或 lease 不再 live 时抛出。
            SourceSyncRepositoryFailure: Lock、transaction 或 persisted invariant 失败时抛出。
        """

        tenant_id = _validate_scope(scope)
        _validate_acquire_input(request)
        session = _open_session(self._session_factory)
        _set_tenant_local(session, tenant_id)
        try:
            job_context = _lock_job_context(
                session,
                tenant_id,
                job_id=request.job_id,
                attempt_id=request.attempt_id,
            )
            _validate_acquire_job_lineage(job_context, request, tenant_id)
            subscription_id = _locked_subscription_id(job_context.payload)
            source_context = _lock_source_context(session, tenant_id, subscription_id)
            raw_clock = _clock_after_all_locks(session)
            _validate_locked_job_live(
                job_context,
                job_id=request.job_id,
                attempt_id=request.attempt_id,
                attempt_number=request.attempt_number,
                raw_clock=raw_clock,
            )
            health = _current_health(
                source_context,
                tenant_id=tenant_id,
                subscription_id=subscription_id,
            )
            operation_row = job_context.operation_row
            if operation_row is None:
                decision = self._insert_first_operation(
                    session,
                    tenant_id=tenant_id,
                    request=request,
                    job_context=job_context,
                    source_context=source_context,
                    health=health,
                    raw_clock=raw_clock,
                )
            else:
                decision = self._decide_existing_operation(
                    session,
                    tenant_id=tenant_id,
                    request=request,
                    job_context=job_context,
                    source_context=source_context,
                    health=health,
                    raw_clock=raw_clock,
                )
        except (SourceSyncRequestRejected, SourceSyncExecutionRejected, SourceSyncRepositoryFailure) as error:
            _rollback_closed_error(session, error)
        except (SQLAlchemyError, psycopg.Error) as error:
            _rollback_database_failure(session, error, post_admission=True)
        except (TypeError, ValueError, KeyError):
            _rollback_closed_error(
                session,
                SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT),
            )
        _commit_and_close(session)
        return decision

    def _insert_first_operation(
        self,
        session: Session,
        *,
        tenant_id: TenantId,
        request: SourceOperationAcquireRequest,
        job_context: _LockedJobContext,
        source_context: _LockedSourceContext,
        health: SourceHealthProjection,
        raw_clock: datetime,
    ) -> SourceOperationAcquireDecision:
        """在全部锁和 live check 后插入 generation 1 operation。

        Args:
            session: 当前 transaction Session。
            tenant_id: Trusted tenant identity。
            request: Strict acquire request。
            job_context: Locked Job context。
            source_context: Locked Source context。
            health: Current health projection。
            raw_clock: 全锁后的唯一 PG clock。

        Returns:
            Generation 1 acquired decision。

        Raises:
            SourceSyncRequestRejected: Scheduled binding 或 payload lineage 不可执行时抛出。
            SQLAlchemyError: Insert 失败时向 transaction boundary 传播。
        """

        payload = job_context.payload
        if isinstance(payload, ManualSourceSyncPayload):
            snapshot = payload.execution_snapshot
            disposition = _disposition_for_snapshot(source_context, snapshot, health)
        else:
            try:
                binding = _parse_binding_rows(
                    source_context.subscription_row,
                    source_context.source_definition_row,
                    source_context.security_row,
                )
            except (TypeError, ValueError, KeyError):
                _raise_request(SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE)
            if binding.source_definition_id != payload.source_definition_id:
                _raise_request(SourceSyncRequestRejectionCode.PAYLOAD_HASH_MISMATCH)
            snapshot = build_source_execution_snapshot(
                binding,
                _rv_datetime(job_context.job_row, "original_available_at"),
            )
            disposition = _binding_disposition(binding, snapshot, health)
        snapshot_document = build_source_execution_snapshot_document(snapshot)
        operation_id = uuid4()
        session.execute(
            text(
                f"INSERT INTO {_SCHEMA}.source_sync_operations "
                "(id, tenant_id, job_run_id, subscription_id, owner_attempt_id, state, generation, "
                "owner_binding_disposition, payload_sha256, execution_snapshot_sha256, "
                "execution_snapshot_json, acquired_at) VALUES "
                "(:id, :tenant_id, :job_id, :subscription_id, :attempt_id, :state, :generation, "
                ":disposition, :payload_sha256, :snapshot_sha256, CAST(:snapshot_json AS jsonb), :acquired_at)"
            ),
            {
                "id": operation_id,
                "tenant_id": tenant_id.value,
                "job_id": request.job_id,
                "subscription_id": snapshot.binding.subscription_id.value,
                "attempt_id": request.attempt_id,
                "state": SourceOperationState.ACTIVE.value,
                "generation": 1,
                "disposition": disposition.value,
                "payload_sha256": request.payload_sha256,
                "snapshot_sha256": snapshot_document.sha256,
                "snapshot_json": _canonical_json_text(snapshot_document),
                "acquired_at": raw_clock,
            },
        )
        return SourceOperationAcquireDecision(
            action=SourceOperationAcquireAction.ACQUIRED,
            effective_state=SourceOperationEffectiveState.LIVE,
            operation_id=operation_id,
            generation=1,
            execution_snapshot=snapshot,
            execution_snapshot_sha256=snapshot_document.sha256,
            binding_disposition=disposition,
            terminal_result=None,
            terminal_receipt=None,
        )

    def _decide_existing_operation(
        self,
        session: Session,
        *,
        tenant_id: TenantId,
        request: SourceOperationAcquireRequest,
        job_context: _LockedJobContext,
        source_context: _LockedSourceContext,
        health: SourceHealthProjection,
        raw_clock: datetime,
    ) -> SourceOperationAcquireDecision:
        """验证 existing operation 后返回 replay、busy 或 generation takeover。

        Args:
            session: 当前 transaction Session。
            tenant_id: Trusted tenant identity。
            request: Strict acquire request。
            job_context: Locked Job context。
            source_context: Locked Source context。
            health: Current health projection。
            raw_clock: 全锁后的唯一 PG clock。

        Returns:
            Terminal replay、busy 或 takeover acquired decision。

        Raises:
            SourceSyncRepositoryFailure: Persisted operation/run 不变量漂移时抛出。
            SQLAlchemyError: Update/read 失败时向 transaction boundary 传播。
        """

        operation_row = job_context.operation_row
        if operation_row is None:
            _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
        subscription_id = _locked_subscription_id(job_context.payload)
        _validate_operation_lineage(
            operation_row,
            tenant_id=tenant_id,
            job_id=request.job_id,
            subscription_id=subscription_id,
            payload_sha256=request.payload_sha256,
        )
        operation_id = _rv_uuid(operation_row, "id")
        snapshot = _parse_operation_snapshot(operation_row)
        snapshot_sha256 = _rv_text(operation_row, "execution_snapshot_sha256")
        if (
            snapshot.binding.tenant_id != tenant_id
            or snapshot.binding.subscription_id != subscription_id
            or build_source_execution_snapshot_document(snapshot).sha256 != snapshot_sha256
        ):
            _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
        _validate_operation_snapshot_provenance(
            job_context,
            tenant_id=tenant_id,
            snapshot=snapshot,
            snapshot_sha256=snapshot_sha256,
        )
        state = SourceOperationState(_rv_text(operation_row, "state"))
        if state is SourceOperationState.TERMINAL:
            terminal_run_id = _rv_optional_uuid(operation_row, "terminal_source_sync_run_id")
            if terminal_run_id is None:
                _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
            run_row = _execute_first(
                session,
                f"SELECT * FROM {_SCHEMA}.source_sync_runs "
                "WHERE tenant_id = :tenant_id AND id = :run_id",
                {"tenant_id": tenant_id.value, "run_id": terminal_run_id},
            )
            if run_row is None:
                _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
            receipt, result = _rebuild_run_artifacts(run_row, tenant_id=tenant_id)
            if (
                receipt.execution_snapshot_sha256 != snapshot_sha256
                or receipt.job_id != request.job_id
                or receipt.producer_attempt_id != _rv_uuid(operation_row, "owner_attempt_id")
            ):
                _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
            return SourceOperationAcquireDecision(
                action=SourceOperationAcquireAction.TERMINAL_REPLAY,
                effective_state=SourceOperationEffectiveState.TERMINAL,
                operation_id=operation_id,
                generation=None,
                execution_snapshot=None,
                execution_snapshot_sha256=None,
                binding_disposition=None,
                terminal_result=result,
                terminal_receipt=receipt,
            )
        generation = _rv_int(operation_row, "generation")
        owner_attempt_id = _rv_uuid(operation_row, "owner_attempt_id")
        SourceBindingDisposition(_rv_text(operation_row, "owner_binding_disposition"))
        if owner_attempt_id == request.attempt_id:
            return SourceOperationAcquireDecision(
                action=SourceOperationAcquireAction.BUSY,
                effective_state=SourceOperationEffectiveState.LIVE,
                operation_id=operation_id,
                generation=None,
                execution_snapshot=None,
                execution_snapshot_sha256=None,
                binding_disposition=None,
                terminal_result=None,
                terminal_receipt=None,
            )
        next_generation = generation + 1
        disposition = _disposition_for_snapshot(source_context, snapshot, health)
        acquired_at = max(raw_clock, _rv_datetime(operation_row, "acquired_at") + timedelta(microseconds=1))
        session.execute(
            text(
                f"UPDATE {_SCHEMA}.source_sync_operations SET owner_attempt_id = :attempt_id, "
                "generation = :generation, owner_binding_disposition = :disposition, "
                "acquired_at = :acquired_at, updated_at = :acquired_at "
                "WHERE tenant_id = :tenant_id AND id = :operation_id"
            ),
            {
                "attempt_id": request.attempt_id,
                "generation": next_generation,
                "disposition": disposition.value,
                "acquired_at": acquired_at,
                "tenant_id": tenant_id.value,
                "operation_id": operation_id,
            },
        )
        return SourceOperationAcquireDecision(
            action=SourceOperationAcquireAction.ACQUIRED,
            effective_state=SourceOperationEffectiveState.LIVE,
            operation_id=operation_id,
            generation=next_generation,
            execution_snapshot=snapshot,
            execution_snapshot_sha256=snapshot_sha256,
            binding_disposition=disposition,
            terminal_result=None,
            terminal_receipt=None,
        )

    def record_terminal(
        self,
        scope: TenantScope,
        request: SourceTerminalRecordRequest,
    ) -> SourceTerminalRecordDecision:
        """按固定 NOWAIT 锁序原子记录 run、health、snapshot、alert 与 terminal。

        Args:
            scope: Trusted tenant scope。
            request: Closed terminal candidate request。

        Returns:
            Recorded、stale_subscription、lease_lost 或 job_not_live decision。

        Raises:
            SourceSyncRequestRejected: 输入、lineage 或 snapshot 不匹配时抛出。
            SourceSyncRepositoryFailure: Lock、transaction 或 persisted invariant 失败时抛出。
        """

        tenant_id = _validate_scope(scope)
        _validate_terminal_input(request)
        session = _open_session(self._session_factory)
        _set_tenant_local(session, tenant_id)
        try:
            try:
                job_context = _lock_job_context(
                    session,
                    tenant_id,
                    job_id=request.job_id,
                    attempt_id=request.attempt_id,
                )
            except SourceSyncExecutionRejected as error:
                decision = _terminal_execution_decision(error.code)
            else:
                subscription_id = _locked_subscription_id(job_context.payload)
                source_context = _lock_source_context(session, tenant_id, subscription_id)
                raw_clock = _clock_after_all_locks(session)
                operation_row = job_context.operation_row
                if operation_row is None or _rv_uuid(operation_row, "id") != request.operation_id:
                    _raise_request(SourceSyncRequestRejectionCode.JOB_LINEAGE_MISMATCH)
                _validate_operation_lineage(
                    operation_row,
                    tenant_id=tenant_id,
                    job_id=request.job_id,
                    subscription_id=subscription_id,
                    payload_sha256=_rv_text(job_context.job_row, "payload_sha256"),
                )
                if SourceOperationState(_rv_text(operation_row, "state")) is SourceOperationState.TERMINAL:
                    _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
                snapshot = _parse_operation_snapshot(operation_row)
                snapshot_sha256 = _rv_text(operation_row, "execution_snapshot_sha256")
                if request.expected_execution_snapshot_sha256 != snapshot_sha256:
                    _raise_request(SourceSyncRequestRejectionCode.SNAPSHOT_MISMATCH)
                if build_source_execution_snapshot_document(snapshot).sha256 != snapshot_sha256:
                    _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
                _validate_operation_snapshot_provenance(
                    job_context,
                    tenant_id=tenant_id,
                    snapshot=snapshot,
                    snapshot_sha256=snapshot_sha256,
                )
                try:
                    _validate_locked_job_live(
                        job_context,
                        job_id=request.job_id,
                        attempt_id=request.attempt_id,
                        attempt_number=request.attempt_number,
                        raw_clock=raw_clock,
                    )
                except SourceSyncExecutionRejected as error:
                    decision = _terminal_execution_decision(error.code)
                else:
                    if (
                        _rv_uuid(operation_row, "owner_attempt_id") != request.attempt_id
                        or _rv_int(operation_row, "generation") != request.expected_generation
                    ):
                        decision = _terminal_execution_decision(SourceSyncExecutionRejectionCode.LEASE_LOST)
                    else:
                        decision = self._record_live_terminal(
                            session,
                            tenant_id=tenant_id,
                            request=request,
                            job_context=job_context,
                            source_context=source_context,
                            operation_row=operation_row,
                            snapshot=snapshot,
                            raw_clock=raw_clock,
                        )
        except (SourceSyncRequestRejected, SourceSyncExecutionRejected, SourceSyncRepositoryFailure) as error:
            _rollback_closed_error(session, error)
        except (SQLAlchemyError, psycopg.Error) as error:
            _rollback_database_failure(session, error, post_admission=True)
        except (TypeError, ValueError, KeyError):
            _rollback_closed_error(
                session,
                SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT),
            )
        _commit_and_close(session)
        return decision

    def _record_live_terminal(
        self,
        session: Session,
        *,
        tenant_id: TenantId,
        request: SourceTerminalRecordRequest,
        job_context: _LockedJobContext,
        source_context: _LockedSourceContext,
        operation_row: _SqlRow,
        snapshot: SourceExecutionSnapshot,
        raw_clock: datetime,
    ) -> SourceTerminalRecordDecision:
        """在 live owner/generation 已闭合后构建并写入 authoritative terminal。

        Args:
            session: 当前 transaction Session。
            tenant_id: Trusted tenant identity。
            request: Closed terminal request。
            job_context: Locked durable Job context。
            source_context: Locked source context。
            operation_row: Locked ACTIVE operation row。
            snapshot: Persisted frozen execution snapshot。
            raw_clock: 全锁后的唯一 PG clock。

        Returns:
            Recorded 或 stale_subscription decision。

        Raises:
            SourceSyncRequestRejected: Candidate 与 snapshot 不匹配时抛出。
            SourceSyncRepositoryFailure: Persisted operation shape 漂移时抛出。
            SQLAlchemyError: 任一 DML 失败时向 transaction boundary 传播。
        """

        subscription_id = snapshot.binding.subscription_id
        health = _current_health(
            source_context,
            tenant_id=tenant_id,
            subscription_id=subscription_id,
        )
        try:
            stored_disposition = SourceBindingDisposition(_rv_text(operation_row, "owner_binding_disposition"))
            operation_acquired_at = _rv_datetime(operation_row, "acquired_at")
        except (TypeError, ValueError):
            _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
        current_disposition = _disposition_for_snapshot(source_context, snapshot, health)
        authoritative_at = max(
            raw_clock,
            operation_acquired_at,
            health.observed_at if health.observed_at is not None else raw_clock,
        )
        try:
            observation = _final_observation(
                candidate=request.candidate,
                stored_disposition=stored_disposition,
                current_disposition=current_disposition,
                snapshot=snapshot,
                authoritative_utc_date=authoritative_at.date(),
            )
        except (TypeError, ValueError):
            _raise_request(SourceSyncRequestRejectionCode.SNAPSHOT_MISMATCH)
        source_sync_run_id = uuid4()
        started_at = _rv_datetime(operation_row, "acquired_at")
        latency_ms = int((authoritative_at - started_at) / timedelta(milliseconds=1))
        receipt = build_source_sync_attempt_receipt(
            tenant_id=tenant_id,
            source_sync_run_id=source_sync_run_id,
            subscription_id=subscription_id,
            job_id=request.job_id,
            producer_attempt_id=request.attempt_id,
            payload_sha256=_rv_text(job_context.job_row, "payload_sha256"),
            execution_snapshot_sha256=request.expected_execution_snapshot_sha256,
            outcome=observation.outcome,
            retry_recommended=observation.retry_recommended,
            documents=observation.documents,
            records_discovered=observation.records_discovered,
            records_ingested=observation.records_downloaded + observation.records_reused,
            records_downloaded=observation.records_downloaded,
            records_reused=observation.records_reused,
            records_ignored=observation.records_ignored,
            records_failed=observation.records_failed,
            latest_source_observed_date=observation.latest_source_observed_date,
            safe_error_code=observation.safe_error_code,
            started_at=started_at,
            finished_at=authoritative_at,
            latency_ms=latency_ms,
        )
        result = build_source_sync_result(receipt)
        session.execute(
            text(
                f"INSERT INTO {_SCHEMA}.source_sync_runs "
                "(id, tenant_id, subscription_id, idempotency_key, status, started_at, finished_at, "
                "records_discovered, records_ingested, safe_error_code, job_run_id, job_attempt_id, "
                "payload_sha256, outcome, retry_recommended, records_downloaded, records_reused, "
                "records_ignored, records_failed, latest_source_observed_date, receipt_json, receipt_sha256, "
                "result_json, result_sha256) VALUES "
                "(:id, :tenant_id, :subscription_id, :idempotency_key, :status, :started_at, :finished_at, "
                ":records_discovered, :records_ingested, :safe_error_code, :job_id, :attempt_id, "
                ":payload_sha256, :outcome, :retry_recommended, :records_downloaded, :records_reused, "
                ":records_ignored, :records_failed, :latest_source_observed_date, "
                "CAST(:receipt_json AS jsonb), :receipt_sha256, CAST(:result_json AS jsonb), :result_sha256)"
            ),
            {
                "id": source_sync_run_id,
                "tenant_id": tenant_id.value,
                "subscription_id": subscription_id.value,
                "idempotency_key": f"source-sync-attempt:v1:{request.job_id}:{request.attempt_id}",
                "status": _expected_run_status(observation.outcome),
                "started_at": started_at,
                "finished_at": authoritative_at,
                "records_discovered": observation.records_discovered,
                "records_ingested": observation.records_downloaded + observation.records_reused,
                "safe_error_code": (
                    observation.safe_error_code.value if observation.safe_error_code is not None else None
                ),
                "job_id": request.job_id,
                "attempt_id": request.attempt_id,
                "payload_sha256": receipt.payload_sha256,
                "outcome": observation.outcome.value,
                "retry_recommended": observation.retry_recommended,
                "records_downloaded": observation.records_downloaded,
                "records_reused": observation.records_reused,
                "records_ignored": observation.records_ignored,
                "records_failed": observation.records_failed,
                "latest_source_observed_date": observation.latest_source_observed_date,
                "receipt_json": _canonical_json_text(receipt.receipt),
                "receipt_sha256": receipt.receipt.sha256,
                "result_json": _canonical_json_text(result.result),
                "result_sha256": result.result.sha256,
            },
        )
        health_after, health_snapshot, alert_event = self._persist_health_for_terminal(
            session,
            current=health,
            receipt=receipt,
            config=snapshot.binding.config,
        )
        session.execute(
            text(
                f"UPDATE {_SCHEMA}.source_sync_operations SET state = :state, "
                "terminal_source_sync_run_id = :run_id, updated_at = :updated_at "
                "WHERE tenant_id = :tenant_id AND id = :operation_id"
            ),
            {
                "state": SourceOperationState.TERMINAL.value,
                "run_id": source_sync_run_id,
                "updated_at": authoritative_at,
                "tenant_id": tenant_id.value,
                "operation_id": request.operation_id,
            },
        )
        action = (
            SourceTerminalRecordAction.STALE_SUBSCRIPTION
            if observation.outcome is SourceSyncOutcome.STALE_SUBSCRIPTION
            else SourceTerminalRecordAction.RECORDED
        )
        return SourceTerminalRecordDecision(
            action=action,
            result=result,
            receipt=receipt,
            health_after=health_after,
            health_snapshot=health_snapshot,
            alert_event=alert_event,
        )

    def _persist_health_for_terminal(
        self,
        session: Session,
        *,
        current: SourceHealthProjection,
        receipt: SourceSyncAttemptReceipt,
        config: FinsDisclosureSubscriptionConfig,
    ) -> tuple[
        SourceHealthProjection,
        SourceHealthSnapshotProjection | None,
        SourceAlertOutboxEvent | None,
    ]:
        """在 source run 已插入后原子推进 health、snapshot 与可选 alert。

        Args:
            session: 当前 transaction Session。
            current: Locked current 或 virtual health。
            receipt: 本次 authoritative receipt。
            config: Frozen health thresholds。

        Returns:
            ``(health_after, optional_snapshot, optional_alert)``。

        Raises:
            SQLAlchemyError: 任一 DML 失败时向 transaction boundary 传播。
            ValueError: Alert conflict reread 与 candidate 漂移时抛出。
        """

        health_after, alert_kind = build_source_health_transition(
            current=current,
            outcome=receipt.outcome,
            safe_error_code=receipt.safe_error_code,
            config=config,
            source_sync_run_id=receipt.source_sync_run_id,
            observed_at=receipt.finished_at,
        )
        if health_after == current:
            return health_after, None, None
        if current.version == 0:
            session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.source_health_states "
                    "(id, tenant_id, subscription_id, last_source_sync_run_id, status, consecutive_failures, "
                    "safe_error_code, version, observed_at, updated_at) VALUES "
                    "(:id, :tenant_id, :subscription_id, :run_id, :status, :failures, :error, "
                    ":version, :observed_at, :observed_at)"
                ),
                {
                    "id": uuid4(),
                    "tenant_id": health_after.tenant_id.value,
                    "subscription_id": health_after.subscription_id.value,
                    "run_id": receipt.source_sync_run_id,
                    "status": health_after.status.value,
                    "failures": health_after.consecutive_failures,
                    "error": health_after.safe_error_code.value if health_after.safe_error_code is not None else None,
                    "version": health_after.version,
                    "observed_at": receipt.finished_at,
                },
            )
        else:
            session.execute(
                text(
                    f"UPDATE {_SCHEMA}.source_health_states SET last_source_sync_run_id = :run_id, "
                    "status = :status, consecutive_failures = :failures, safe_error_code = :error, "
                    "version = :version, observed_at = :observed_at, updated_at = :observed_at "
                    "WHERE tenant_id = :tenant_id AND subscription_id = :subscription_id"
                ),
                {
                    "run_id": receipt.source_sync_run_id,
                    "status": health_after.status.value,
                    "failures": health_after.consecutive_failures,
                    "error": health_after.safe_error_code.value if health_after.safe_error_code is not None else None,
                    "version": health_after.version,
                    "observed_at": receipt.finished_at,
                    "tenant_id": health_after.tenant_id.value,
                    "subscription_id": health_after.subscription_id.value,
                },
            )
        snapshot = SourceHealthSnapshotProjection(
            snapshot_id=uuid4(),
            tenant_id=health_after.tenant_id,
            subscription_id=health_after.subscription_id,
            source_sync_run_id=receipt.source_sync_run_id,
            health_state_version=health_after.version,
            status=health_after.status,
            consecutive_failures=health_after.consecutive_failures,
            latency_ms=receipt.latency_ms,
            safe_error_code=health_after.safe_error_code,
            observed_at=receipt.finished_at,
            created_at=receipt.finished_at,
        )
        session.execute(
            text(
                f"INSERT INTO {_SCHEMA}.source_health_snapshots "
                "(id, tenant_id, subscription_id, sync_run_id, health_state_version, observed_at, status, "
                "consecutive_failures, latency_ms, safe_error_code, created_at) VALUES "
                "(:id, :tenant_id, :subscription_id, :run_id, :version, :observed_at, :status, "
                ":failures, :latency_ms, :error, :created_at)"
            ),
            {
                "id": snapshot.snapshot_id,
                "tenant_id": snapshot.tenant_id.value,
                "subscription_id": snapshot.subscription_id.value,
                "run_id": snapshot.source_sync_run_id,
                "version": snapshot.health_state_version,
                "observed_at": snapshot.observed_at,
                "status": snapshot.status.value,
                "failures": snapshot.consecutive_failures,
                "latency_ms": snapshot.latency_ms,
                "error": snapshot.safe_error_code.value if snapshot.safe_error_code is not None else None,
                "created_at": snapshot.created_at,
            },
        )
        if alert_kind is None:
            return health_after, snapshot, None
        alert = build_source_alert_outbox_event(health_snapshot=snapshot, alert_kind=alert_kind)
        session.execute(
            text(
                f"INSERT INTO {_SCHEMA}.source_health_alert_outbox "
                "(id, tenant_id, subscription_id, source_sync_run_id, health_snapshot_id, "
                "health_state_version, alert_kind, target_status, safe_error_code, dedupe_key, "
                "event_json, event_sha256, created_at) VALUES "
                "(:id, :tenant_id, :subscription_id, :run_id, :snapshot_id, :version, :alert_kind, "
                ":target_status, :error, :dedupe_key, CAST(:event_json AS jsonb), :event_sha256, :created_at) "
                "ON CONFLICT (tenant_id, dedupe_key) DO NOTHING"
            ),
            {
                "id": alert.event_id,
                "tenant_id": alert.tenant_id.value,
                "subscription_id": alert.subscription_id.value,
                "run_id": alert.source_sync_run_id,
                "snapshot_id": alert.health_snapshot_id,
                "version": alert.health_state_version,
                "alert_kind": alert.alert_kind.value,
                "target_status": alert.target_status.value,
                "error": alert.safe_error_code.value,
                "dedupe_key": alert.dedupe_key,
                "event_json": _canonical_json_text(alert.event),
                "event_sha256": alert.event.sha256,
                "created_at": alert.created_at,
            },
        )
        persisted_row = _execute_first(
            session,
            f"SELECT * FROM {_SCHEMA}.source_health_alert_outbox "
            "WHERE tenant_id = :tenant_id AND dedupe_key = :dedupe_key",
            {"tenant_id": alert.tenant_id.value, "dedupe_key": alert.dedupe_key},
        )
        if persisted_row is None or _alert_from_row(persisted_row) != alert:
            raise ValueError("alert conflict reread drift")
        return health_after, snapshot, alert

    def get_source_receipt(
        self,
        scope: TenantScope,
        source_sync_run_id: UUID,
    ) -> SourceSyncAttemptReceipt | None:
        """读取 strict v1 receipt，missing 与合法 legacy row 返回空。

        Args:
            scope: Trusted tenant scope。
            source_sync_run_id: Source run UUID。

        Returns:
            Strict v1 receipt；scoped missing 或 13-core-all-null legacy row 返回 ``None``。

        Raises:
            SourceSyncRequestRejected: 输入非法时抛出。
            SourceSyncRepositoryFailure: 事务或持久化不变量失败时抛出。
        """

        tenant_id = _validate_scope(scope)
        _validate_uuid(source_sync_run_id, "source_sync_run_id")
        session = _open_session(self._session_factory)
        _set_tenant_local(session, tenant_id)
        try:
            run_row = _execute_first(
                session,
                f"SELECT * FROM {_SCHEMA}.source_sync_runs "
                "WHERE tenant_id = :tenant_id AND id = :run_id",
                {"tenant_id": tenant_id.value, "run_id": source_sync_run_id},
            )
            receipt: SourceSyncAttemptReceipt | None
            if run_row is None:
                receipt = None
            else:
                all_null, all_present = _core_presence(run_row)
                if all_null:
                    receipt = None
                elif not all_present:
                    _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
                else:
                    rebuilt_receipt, _result = _rebuild_run_artifacts(run_row, tenant_id=tenant_id)
                    if rebuilt_receipt.source_sync_run_id != source_sync_run_id:
                        _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
                    receipt = rebuilt_receipt
        except (SourceSyncRequestRejected, SourceSyncExecutionRejected, SourceSyncRepositoryFailure) as error:
            _rollback_closed_error(session, error)
        except (SQLAlchemyError, psycopg.Error) as error:
            _rollback_database_failure(session, error, post_admission=True)
        except (TypeError, ValueError, KeyError):
            _rollback_closed_error(
                session,
                SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT),
            )
        _commit_and_close(session)
        return receipt

    def get_health(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceHealthProjection:
        """读取 persisted health head 或 virtual healthy projection。

        Args:
            scope: Trusted tenant scope。
            subscription_id: Source subscription identity。

        Returns:
            Persisted head，或无 head 时的 version-zero virtual projection。

        Raises:
            SourceSyncRequestRejected: 输入非法或 subscription 不存在时抛出。
            SourceSyncRepositoryFailure: 事务或持久化不变量失败时抛出。
        """

        tenant_id = _validate_scope(scope)
        subscription_value = _validate_subscription_id(subscription_id)
        session = _open_session(self._session_factory)
        _set_tenant_local(session, tenant_id)
        try:
            subscription_row = _execute_first(
                session,
                f"SELECT tenant_id, id FROM {_SCHEMA}.source_subscriptions "
                "WHERE tenant_id = :tenant_id AND id = :subscription_id",
                {"tenant_id": tenant_id.value, "subscription_id": subscription_value},
            )
            if subscription_row is None:
                _raise_request(SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND)
            if (
                _rv_uuid(subscription_row, "tenant_id") != UUID(tenant_id.value)
                or _rv_uuid(subscription_row, "id") != UUID(subscription_value)
            ):
                _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
            health_row = _execute_first(
                session,
                f"SELECT * FROM {_SCHEMA}.source_health_states "
                "WHERE tenant_id = :tenant_id AND subscription_id = :subscription_id",
                {"tenant_id": tenant_id.value, "subscription_id": subscription_value},
            )
            health = (
                _virtual_health(tenant_id, subscription_id)
                if health_row is None
                else _health_from_row(
                    health_row,
                    tenant_id=tenant_id,
                    subscription_id=subscription_id,
                )
            )
        except (SourceSyncRequestRejected, SourceSyncExecutionRejected, SourceSyncRepositoryFailure) as error:
            _rollback_closed_error(session, error)
        except (SQLAlchemyError, psycopg.Error) as error:
            _rollback_database_failure(session, error, post_admission=True)
        except (TypeError, ValueError, KeyError):
            _rollback_closed_error(
                session,
                SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT),
            )
        _commit_and_close(session)
        return health

    def list_health_snapshots(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
        cursor: SourceHealthSnapshotCursor | None,
        *,
        limit: int,
    ) -> SourceHealthSnapshotPage:
        """按 ``observed_at DESC, id DESC`` 的稳定 keyset 分页读取 snapshots。

        Args:
            scope: Trusted tenant scope。
            subscription_id: Source subscription identity。
            cursor: 可空 keyset cursor。
            limit: 页大小，精确范围 1..200。

        Returns:
            Strict snapshot page。

        Raises:
            SourceSyncRequestRejected: 输入非法或 subscription 不存在时抛出。
            SourceSyncRepositoryFailure: 事务或持久化不变量失败时抛出。
        """

        tenant_id = _validate_scope(scope)
        subscription_value = _validate_subscription_id(subscription_id)
        if type(limit) is not int or not 1 <= limit <= _MAX_HEALTH_PAGE_SIZE:
            _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
        if cursor is not None:
            if type(cursor) is not SourceHealthSnapshotCursor:
                _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
            if (
                type(cursor.observed_at) is not datetime
                or cursor.observed_at.tzinfo is None
                or cursor.observed_at.utcoffset() != timedelta(0)
                or type(cursor.snapshot_id) is not UUID
                or cursor.snapshot_id.int == 0
            ):
                _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
        session = _open_session(self._session_factory)
        _set_tenant_local(session, tenant_id)
        try:
            subscription_row = _execute_first(
                session,
                f"SELECT tenant_id, id FROM {_SCHEMA}.source_subscriptions "
                "WHERE tenant_id = :tenant_id AND id = :subscription_id",
                {"tenant_id": tenant_id.value, "subscription_id": subscription_value},
            )
            if subscription_row is None:
                _raise_request(SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND)
            if (
                _rv_uuid(subscription_row, "tenant_id") != UUID(tenant_id.value)
                or _rv_uuid(subscription_row, "id") != UUID(subscription_value)
            ):
                _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
            parameters: dict[str, _DbValue] = {
                "tenant_id": tenant_id.value,
                "subscription_id": subscription_value,
                "row_limit": limit + 1,
            }
            cursor_clause = ""
            if cursor is not None:
                cursor_clause = "AND (observed_at, id) < (:cursor_observed_at, :cursor_id) "
                parameters["cursor_observed_at"] = cursor.observed_at
                parameters["cursor_id"] = cursor.snapshot_id
            rows = _execute_all(
                session,
                f"SELECT * FROM {_SCHEMA}.source_health_snapshots "
                "WHERE tenant_id = :tenant_id AND subscription_id = :subscription_id "
                f"{cursor_clause}ORDER BY observed_at DESC, id DESC LIMIT :row_limit",
                parameters,
            )
            page_rows = rows[:limit]
            snapshots = tuple(
                _snapshot_from_row(
                    row,
                    tenant_id=tenant_id,
                    subscription_id=subscription_id,
                )
                for row in page_rows
            )
            next_cursor = (
                SourceHealthSnapshotCursor(
                    observed_at=snapshots[-1].observed_at,
                    snapshot_id=snapshots[-1].snapshot_id,
                )
                if len(rows) > limit
                else None
            )
            page = SourceHealthSnapshotPage(snapshots=snapshots, next_cursor=next_cursor)
        except (SourceSyncRequestRejected, SourceSyncExecutionRejected, SourceSyncRepositoryFailure) as error:
            _rollback_closed_error(session, error)
        except (SQLAlchemyError, psycopg.Error) as error:
            _rollback_database_failure(session, error, post_admission=True)
        except (TypeError, ValueError, KeyError):
            _rollback_closed_error(
                session,
                SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT),
            )
        _commit_and_close(session)
        return page

    def reenable_health(
        self,
        scope: TenantScope,
        request: SourceHealthReenableRequest,
    ) -> SourceHealthProjection:
        """以 subscription/head NOWAIT 锁与 exact version CAS 恢复 health。

        Args:
            scope: Trusted tenant scope。
            request: Operator re-enable request。

        Returns:
            Version 前进一的 healthy projection。

        Raises:
            SourceSyncRequestRejected: 输入、subscription、状态或版本冲突时抛出。
            SourceSyncRepositoryFailure: Lock、事务或持久化不变量失败时抛出。
        """

        tenant_id = _validate_scope(scope)
        if type(request) is not SourceHealthReenableRequest:
            _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
        subscription_value = _validate_subscription_id(request.subscription_id)
        if type(request.expected_health_version) is not int or request.expected_health_version <= 0:
            _raise_request(SourceSyncRequestRejectionCode.INVALID_INPUT)
        session = _open_session(self._session_factory)
        _set_tenant_local(session, tenant_id)
        try:
            subscription_row = _execute_first(
                session,
                f"SELECT tenant_id, id, status FROM {_SCHEMA}.source_subscriptions "
                "WHERE tenant_id = :tenant_id AND id = :subscription_id FOR UPDATE NOWAIT",
                {"tenant_id": tenant_id.value, "subscription_id": subscription_value},
            )
            if subscription_row is None:
                _raise_request(SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND)
            if (
                _rv_uuid(subscription_row, "tenant_id") != UUID(tenant_id.value)
                or _rv_uuid(subscription_row, "id") != UUID(subscription_value)
            ):
                _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
            health_row = _execute_first(
                session,
                f"SELECT * FROM {_SCHEMA}.source_health_states "
                "WHERE tenant_id = :tenant_id AND subscription_id = :subscription_id "
                "FOR UPDATE NOWAIT",
                {"tenant_id": tenant_id.value, "subscription_id": subscription_value},
            )
            raw_clock = _clock_after_all_locks(session)
            subscription_status = SubscriptionStatus(_rv_text(subscription_row, "status"))
            if subscription_status is not SubscriptionStatus.ENABLED or health_row is None:
                _raise_request(SourceSyncRequestRejectionCode.HEALTH_STATE_CONFLICT)
            current = _health_from_row(
                health_row,
                tenant_id=tenant_id,
                subscription_id=request.subscription_id,
            )
            if current.status is not SourceHealthStatus.DISABLED:
                _raise_request(SourceSyncRequestRejectionCode.HEALTH_STATE_CONFLICT)
            if current.version != request.expected_health_version:
                _raise_request(SourceSyncRequestRejectionCode.HEALTH_VERSION_CONFLICT)
            if current.observed_at is None or current.last_source_sync_run_id is None:
                _raise_repository(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
            authoritative_at = max(raw_clock, current.observed_at + timedelta(microseconds=1))
            updated = SourceHealthProjection(
                tenant_id=tenant_id,
                subscription_id=request.subscription_id,
                status=SourceHealthStatus.HEALTHY,
                consecutive_failures=0,
                safe_error_code=None,
                version=current.version + 1,
                last_source_sync_run_id=current.last_source_sync_run_id,
                observed_at=authoritative_at,
            )
            session.execute(
                text(
                    f"UPDATE {_SCHEMA}.source_health_states SET status = :status, "
                    "consecutive_failures = 0, safe_error_code = NULL, version = :version, "
                    "observed_at = :observed_at, updated_at = :observed_at "
                    "WHERE tenant_id = :tenant_id AND subscription_id = :subscription_id"
                ),
                {
                    "status": updated.status.value,
                    "version": updated.version,
                    "observed_at": authoritative_at,
                    "tenant_id": tenant_id.value,
                    "subscription_id": subscription_value,
                },
            )
            snapshot = SourceHealthSnapshotProjection(
                snapshot_id=uuid4(),
                tenant_id=tenant_id,
                subscription_id=request.subscription_id,
                source_sync_run_id=None,
                health_state_version=updated.version,
                status=SourceHealthStatus.HEALTHY,
                consecutive_failures=0,
                latency_ms=None,
                safe_error_code=None,
                observed_at=authoritative_at,
                created_at=authoritative_at,
            )
            session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.source_health_snapshots "
                    "(id, tenant_id, subscription_id, sync_run_id, health_state_version, observed_at, "
                    "status, consecutive_failures, latency_ms, safe_error_code, created_at) VALUES "
                    "(:id, :tenant_id, :subscription_id, NULL, :version, :observed_at, "
                    ":status, 0, NULL, NULL, :created_at)"
                ),
                {
                    "id": snapshot.snapshot_id,
                    "tenant_id": tenant_id.value,
                    "subscription_id": subscription_value,
                    "version": snapshot.health_state_version,
                    "observed_at": snapshot.observed_at,
                    "status": snapshot.status.value,
                    "created_at": snapshot.created_at,
                },
            )
        except (SourceSyncRequestRejected, SourceSyncExecutionRejected, SourceSyncRepositoryFailure) as error:
            _rollback_closed_error(session, error)
        except (SQLAlchemyError, psycopg.Error) as error:
            _rollback_database_failure(session, error, post_admission=True)
        except (TypeError, ValueError, KeyError):
            _rollback_closed_error(
                session,
                SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT),
            )
        _commit_and_close(session)
        return updated
