"""PostgresSourceSyncRepository 的真实 PostgreSQL 16 integration 契约。

本文件是 Item 5 唯一 PostgreSQL owner。所有 fixture 都使用独立 lifecycle
database、真实 app role、真实 identity/job repositories，并让 production
repository 自己在每个 transaction 设置 tenant-local RLS context。
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from threading import Barrier
from typing import Protocol, TypeAlias, get_type_hints
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
import pytest
from sqlalchemy import Connection, Engine, Row, event, text
from sqlalchemy.engine.interfaces import ExecutionContext
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, PoolProxiedConnection

import dayu.investment.storage.postgres_sources as postgres_sources_module
from dayu.investment.domain.identifiers import CompanyId, Principal, SecurityId, TenantId, TenantScope
from dayu.investment.domain.jobs import (
    CanonicalJobDocument,
    JobCancellationRequest,
    JobClaim,
    JobEnqueueRequest,
    JobFailure,
    SafeJobErrorCode,
)
from dayu.investment.domain.source import (
    CompanyCreateRequest,
    CompanySecurityRegistration,
    JsonValue,
    SecurityCreateRequest,
    SecurityType,
    SourceDefinitionCreateRequest,
    SourceDefinitionId,
    SourceKind,
    SourceSubscriptionCreateRequest,
    SourceSubscriptionId,
    SubscriptionStatus,
)
from dayu.investment.domain.source_evidence import (
    SourceDocumentEvidence,
    SourceFinsTerminalCandidate,
    SourceNoProviderReason,
    SourceNoProviderTerminalCandidate,
    build_source_evidence_locator_document,
)
from dayu.investment.domain.source_health import (
    SourceHealthReenableRequest,
    SourceHealthSnapshotCursor,
    SourceHealthStatus,
)
from dayu.investment.domain.source_operation import (
    SourceOperationAcquireAction,
    SourceOperationAcquireDecision,
    SourceOperationAcquireRequest,
    SourceTerminalRecordAction,
    SourceTerminalRecordDecision,
    SourceTerminalRecordRequest,
)
from dayu.investment.domain.source_payload import (
    ManualSourceSyncPayload,
    ScheduledSourceSyncPayload,
    SourceExecutionSnapshot,
    build_manual_source_sync_payload_document,
    build_scheduled_source_sync_payload_document,
    build_source_execution_snapshot,
    build_source_execution_snapshot_document,
)
from dayu.investment.domain.source_sync import (
    FINS_SOURCE_DEFINITION_KEY,
    SOURCE_SYNC_JOB_DESCRIPTOR,
    SourceBindingDisposition,
    SourceSyncErrorCode,
    SourceSyncExecutionRejected,
    SourceSyncExecutionRejectionCode,
    SourceSyncOrigin,
    SourceSyncOutcome,
    SourceSyncRepositoryFailure,
    SourceSyncRepositoryFailureCode,
    SourceSyncRequestRejected,
    SourceSyncRequestRejectionCode,
)
from dayu.investment.storage.db import (
    PLATFORM_SCHEMA_NAME,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage.postgres_identity import PostgresIdentityRepository
from dayu.investment.storage.postgres_jobs import PostgresJobStore
from dayu.investment.storage.postgres_sources import PostgresSourceSyncRepository
from dayu.investment.storage.source_sync_protocols import SourceSyncRepositoryProtocol
from tests.integration.investment.conftest import (
    PlatformCluster,
    create_temporary_login,
    drop_temporary_login,
    run_alembic_downgrade,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration

DatabaseFactory = Callable[[], str]
DatabaseJsonScalar: TypeAlias = str | int | float | bool | None
DatabaseJsonValue: TypeAlias = (
    DatabaseJsonScalar | list["DatabaseJsonValue"] | dict[str, "DatabaseJsonValue"]
)
DatabaseValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | datetime
    | date
    | bytes
    | memoryview
    | UUID
    | dict[str, DatabaseJsonValue]
    | list[DatabaseJsonValue]
    | None
)
PostgresRow: TypeAlias = tuple[DatabaseValue, ...]
CursorParameters: TypeAlias = Mapping[str, DatabaseValue]
CursorReplacement: TypeAlias = tuple[str, CursorParameters]
DatabaseRow: TypeAlias = Row[PostgresRow]


class _StringExecuteCursor(Protocol):
    """SQLAlchemy event 回调实际使用的闭合 cursor execute 表面。"""

    execute: Callable[[str, CursorParameters], None]


_SCHEMA = PLATFORM_SCHEMA_NAME
_TENANT_ID = TenantId("00000000-0000-0000-0000-000000000001")
_SCOPE = Principal(tenant_id=_TENANT_ID, user_id="source-pg-owner").to_scope()
_CONFIG: dict[str, JsonValue] = {
    "forms": ("10-K", "10-Q"),
    "lookback_days": 3,
    "freshness_max_age_days": 1,
    "failing_after": 2,
    "disable_after": 3,
    "max_documents_per_sync": 50,
}
_CONSTRAINT_TRIGGER_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        (
            "source_subscriptions",
            "fk_source_subscriptions_security_id_securities",
        ),
    }
)
_NAMED_TRIGGER_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("job_leases", "guard_job_leases_immutable_columns_trigger"),
        ("source_sync_runs", "source_sync_runs_require_v1_insert_trigger"),
        ("source_sync_runs", "guard_source_sync_runs_append_only_trigger"),
        (
            "source_sync_operations",
            "guard_source_sync_operations_transition_trigger",
        ),
    }
)
_SOURCE_RUN_TAMPER_CHECKS: frozenset[str] = frozenset(
    {
        "ck_source_sync_runs_v1_core_presence",
        "ck_source_sync_runs_v1_outcome_shape",
    }
)


def _stable_uuid(label: str) -> UUID:
    """返回测试 fixture 的稳定、非零 UUID。

    Args:
        label: 区分测试实体的稳定语义标签，作为 UUID5 名称的一部分。

    Returns:
        Item 5 测试命名空间内由 ``label`` 唯一决定的非零 UUID。

    Raises:
        无。
    """

    return uuid5(NAMESPACE_URL, f"dayu-source-pg-item5:{label}")


@dataclass(frozen=True, slots=True)
class _Harness:
    """单个隔离数据库的 Source repository 测试句柄。"""

    cluster: PlatformCluster
    database: str
    bootstrap_engine: Engine
    primary_engine: Engine
    secondary_engine: Engine
    primary_factory: sessionmaker[Session]
    secondary_factory: sessionmaker[Session]
    repository: PostgresSourceSyncRepository
    second_repository: PostgresSourceSyncRepository
    jobs: PostgresJobStore
    second_jobs: PostgresJobStore
    identity: PostgresIdentityRepository
    scope: TenantScope
    source_definition_id: SourceDefinitionId
    subscription_id: SourceSubscriptionId
    company_id: CompanyId
    security_id: SecurityId


@dataclass(frozen=True, slots=True)
class _LiveOperation:
    """真实 Job claim 与 acquired Source operation 的组合。"""

    claim: JobClaim
    snapshot: SourceExecutionSnapshot
    acquire: SourceOperationAcquireDecision


@dataclass(frozen=True, slots=True)
class _ClaimedOperation:
    """真实 Job claim 与冻结 snapshot，尚未创建 Source operation。"""

    claim: JobClaim
    snapshot: SourceExecutionSnapshot
    origin: SourceSyncOrigin


def _bootstrap_execute(harness: _Harness, statement: str, parameters: dict[str, str | int | UUID | datetime]) -> None:
    """在 owned database 内用 bootstrap transaction 执行精确 DML。

    Args:
        harness: 提供 bootstrap engine 的隔离数据库句柄。
        statement: 仅供当前对抗 fixture 使用的精确参数化 SQL。
        parameters: 绑定到 ``statement`` 的强类型参数字典。

    Returns:
        无；transaction 成功退出时 DML 已提交。

    Raises:
        SQLAlchemyError: 建立 transaction、执行 SQL 或提交失败时向调用者传播。
    """

    with harness.bootstrap_engine.begin() as connection:
        connection.execute(text(statement), parameters)


def _bootstrap_scalar(
    harness: _Harness,
    statement: str,
    parameters: dict[str, str | UUID | datetime] | None = None,
) -> int:
    """读取 owned database 的单个整数标量。

    Args:
        harness: 提供 bootstrap engine 的隔离数据库句柄。
        statement: 必须只返回一个整数单元格的参数化查询。
        parameters: 可选查询绑定参数；省略时使用空字典。

    Returns:
        查询唯一行、唯一列中的严格 ``int`` 值。

    Raises:
        AssertionError: 数据库标量不是严格 ``int`` 时抛出。
        SQLAlchemyError: 查询失败或结果不是唯一标量时向调用者传播。
    """

    with harness.bootstrap_engine.connect() as connection:
        value = connection.execute(text(statement), parameters if parameters is not None else {}).scalar_one()
        connection.rollback()
    assert type(value) is int
    return value


def _set_constraint_triggers_enabled(
    harness: _Harness,
    *,
    table_name: str,
    constraint_name: str,
    enabled: bool,
) -> None:
    """只切换测试允许的 exact foreign-key constraint triggers。

    Args:
        harness: Owned database 测试句柄。
        table_name: Exact child table 名。
        constraint_name: Exact foreign-key constraint 名。
        enabled: ``True`` 表示恢复，``False`` 表示暂停。

    Returns:
        无。

    Raises:
        AssertionError: 请求不在闭合 allowlist，或 catalog identity 漂移时抛出。
        SQLAlchemyError: Catalog 查询或 DDL 失败时向外传播。
    """

    assert (table_name, constraint_name) in _CONSTRAINT_TRIGGER_ALLOWLIST
    action = "ENABLE" if enabled else "DISABLE"
    with harness.bootstrap_engine.begin() as connection:
        trigger_names = tuple(
            connection.execute(
                text(
                    "SELECT trigger.tgname FROM pg_catalog.pg_trigger AS trigger "
                    "JOIN pg_catalog.pg_constraint AS fk_constraint "
                    "ON fk_constraint.oid = trigger.tgconstraint "
                    "JOIN pg_catalog.pg_class AS relation ON relation.oid = trigger.tgrelid "
                    "JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
                    "WHERE namespace.nspname = :schema_name AND relation.relname = :table_name "
                    "AND fk_constraint.conname = :constraint_name ORDER BY trigger.tgname"
                ),
                {
                    "schema_name": _SCHEMA,
                    "table_name": table_name,
                    "constraint_name": constraint_name,
                },
            ).scalars()
        )
        assert len(trigger_names) == 2
        for trigger_name in trigger_names:
            assert type(trigger_name) is str
            quoted_trigger = trigger_name.replace('"', '""')
            connection.exec_driver_sql(
                f'ALTER TABLE "{_SCHEMA}"."{table_name}" {action} TRIGGER "{quoted_trigger}"'
            )


def _set_named_trigger_enabled(
    harness: _Harness,
    *,
    table_name: str,
    trigger_name: str,
    enabled: bool,
) -> None:
    """只切换测试允许的 exact named trigger。

    Args:
        harness: Owned database 测试句柄。
        table_name: Exact table 名。
        trigger_name: Exact trigger 名。
        enabled: ``True`` 表示恢复，``False`` 表示暂停。

    Returns:
        无。

    Raises:
        AssertionError: 请求不在闭合 allowlist 时抛出。
        SQLAlchemyError: DDL 失败时向外传播。
    """

    assert (table_name, trigger_name) in _NAMED_TRIGGER_ALLOWLIST
    action = "ENABLE" if enabled else "DISABLE"
    with harness.bootstrap_engine.begin() as connection:
        connection.exec_driver_sql(
            f'ALTER TABLE "{_SCHEMA}"."{table_name}" {action} TRIGGER "{trigger_name}"'
        )


def _drop_source_run_check(harness: _Harness, constraint_name: str) -> str:
    """暂时移除一个 exact source-run CHECK 并返回其 catalog 定义。

    Args:
        harness: Owned database 测试句柄。
        constraint_name: 闭合 allowlist 中的 CHECK 名。

    Returns:
        PostgreSQL ``pg_get_constraintdef`` 返回的完整定义。

    Raises:
        AssertionError: Constraint 不在 allowlist 或 catalog identity 漂移时抛出。
        SQLAlchemyError: Catalog 查询或 DDL 失败时向外传播。
    """

    assert constraint_name in _SOURCE_RUN_TAMPER_CHECKS
    with harness.bootstrap_engine.begin() as connection:
        definition = connection.execute(
            text(
                "SELECT pg_catalog.pg_get_constraintdef(check_constraint.oid, true) "
                "FROM pg_catalog.pg_constraint AS check_constraint "
                "JOIN pg_catalog.pg_class AS relation ON relation.oid = check_constraint.conrelid "
                "JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
                "WHERE namespace.nspname = :schema_name AND relation.relname = 'source_sync_runs' "
                "AND check_constraint.conname = :constraint_name"
            ),
            {"schema_name": _SCHEMA, "constraint_name": constraint_name},
        ).scalar_one()
        assert type(definition) is str and definition.startswith("CHECK (")
        connection.exec_driver_sql(
            f'ALTER TABLE "{_SCHEMA}"."source_sync_runs" '
            f'DROP CONSTRAINT "{constraint_name}"'
        )
    return definition


def _restore_source_run_check(
    harness: _Harness,
    *,
    constraint_name: str,
    definition: str,
) -> None:
    """用冻结 catalog 定义恢复一个 exact source-run CHECK。

    Args:
        harness: Owned database 测试句柄。
        constraint_name: 闭合 allowlist 中的 CHECK 名。
        definition: 移除前读取的完整 PostgreSQL 定义。

    Returns:
        无。

    Raises:
        AssertionError: Constraint 或 definition shape 非法时抛出。
        SQLAlchemyError: DDL 或 validation 失败时向外传播。
    """

    assert constraint_name in _SOURCE_RUN_TAMPER_CHECKS
    assert definition.startswith("CHECK (")
    with harness.bootstrap_engine.begin() as connection:
        connection.exec_driver_sql(
            f'ALTER TABLE "{_SCHEMA}"."source_sync_runs" '
            f'ADD CONSTRAINT "{constraint_name}" {definition}'
        )


def _operation_identity(
    harness: _Harness,
    operation_id: UUID,
) -> tuple[int, UUID, str, UUID]:
    """读取 operation 的 generation/owner/snapshot/subscription identity。

    Args:
        harness: Owned database 测试句柄。
        operation_id: Operation UUID。

    Returns:
        ``(generation, owner_attempt_id, snapshot_sha256, subscription_id)``。

    Raises:
        AssertionError: Persisted row shape 不符合预期时抛出。
        SQLAlchemyError: 查询失败时向外传播。
    """

    with harness.bootstrap_engine.connect() as connection:
        row = connection.execute(
            text(
                f"SELECT generation, owner_attempt_id, execution_snapshot_sha256, subscription_id "
                f"FROM {_SCHEMA}.source_sync_operations WHERE id = :operation_id"
            ),
            {"operation_id": operation_id},
        ).one()
        connection.rollback()
    generation, owner_attempt_id, snapshot_sha256, subscription_id = tuple(row)
    assert type(generation) is int
    assert type(owner_attempt_id) is UUID
    assert type(snapshot_sha256) is str
    assert type(subscription_id) is UUID
    return generation, owner_attempt_id, snapshot_sha256, subscription_id


def _source_run_result_fingerprint(
    harness: _Harness,
    source_sync_run_id: UUID,
) -> tuple[str, str]:
    """读取 source run 的 immutable result JSON/SHA 指纹。

    Args:
        harness: Owned database 测试句柄。
        source_sync_run_id: Source run UUID。

    Returns:
        ``(result_json_text, result_sha256)``。

    Raises:
        AssertionError: Persisted row shape 不符合预期时抛出。
        SQLAlchemyError: 查询失败时向外传播。
    """

    with harness.bootstrap_engine.connect() as connection:
        row = connection.execute(
            text(
                f"SELECT result_json::text, result_sha256 FROM {_SCHEMA}.source_sync_runs "
                "WHERE id = :source_sync_run_id"
            ),
            {"source_sync_run_id": source_sync_run_id},
        ).one()
        connection.rollback()
    result_json, result_sha256 = tuple(row)
    assert type(result_json) is str and type(result_sha256) is str
    return result_json, result_sha256


def _assert_receipt_invariant_is_read_only(
    harness: _Harness,
    *,
    source_sync_run_id: UUID,
    operation_id: UUID,
    expected_counts: tuple[int, int, int, int, int],
    expected_operation: tuple[int, UUID, str, UUID],
    expected_result: tuple[str, str],
) -> None:
    """断言 corrupt receipt 稳定失败且不改变任何 durable fact。

    Args:
        harness: Owned database 测试句柄。
        source_sync_run_id: 被读取的 Source run UUID。
        operation_id: 绑定该 run 的 operation UUID。
        expected_counts: 五张 Source 表的冻结行数。
        expected_operation: Operation generation/owner/snapshot/subscription identity。
        expected_result: Immutable result JSON/SHA 指纹。

    Returns:
        无。

    Raises:
        AssertionError: Failure code 或任一 durable fact 发生漂移时抛出。
    """

    with pytest.raises(SourceSyncRepositoryFailure) as error:
        harness.repository.get_source_receipt(harness.scope, source_sync_run_id)
    _assert_repository_error(error.value, SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    assert _source_counts(harness) == expected_counts
    assert _operation_identity(harness, operation_id) == expected_operation
    assert _source_run_result_fingerprint(harness, source_sync_run_id) == expected_result


def _pg_clock(harness: _Harness) -> datetime:
    """读取测试数据库的 aware UTC clock。

    Args:
        harness: 提供 authoritative PostgreSQL clock 的隔离数据库句柄。

    Returns:
        从数据库读取并规范化到 UTC 的 aware ``datetime``。

    Raises:
        AssertionError: PostgreSQL 返回值不是 ``datetime`` 时抛出。
        SQLAlchemyError: clock 查询或连接回滚失败时向调用者传播。
    """

    with harness.bootstrap_engine.connect() as connection:
        value = connection.execute(text("SELECT clock_timestamp()"), {}).scalar_one()
        connection.rollback()
    assert isinstance(value, datetime)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _seed_identity(identity: PostgresIdentityRepository) -> tuple[SourceDefinitionId, SourceSubscriptionId, CompanyId, SecurityId]:
    """经真实 identity repository 建立唯一 executable Fins security binding。

    Args:
        identity: 用于写入 company、security、definition 与 subscription 的真实仓储。

    Returns:
        按 definition、subscription、company、security 排列的四个稳定强标识。

    Raises:
        RepositoryError: 任一 identity 校验、冲突或持久化操作失败时由仓储传播。
    """

    company_id = CompanyId(str(_stable_uuid("company")))
    security_id = SecurityId(str(_stable_uuid("security")))
    source_definition_id = SourceDefinitionId(str(_stable_uuid("source-definition")))
    subscription_id = SourceSubscriptionId(str(_stable_uuid("subscription")))
    identity.register_company_security(
        _SCOPE,
        CompanySecurityRegistration(
            company=CompanyCreateRequest(
                company_id=company_id,
                legal_name="Item Five Corp",
                lei=None,
                country_code="US",
            ),
            security=SecurityCreateRequest(
                security_id=security_id,
                company_id=company_id,
                ticker="ITEM",
                exchange_mic="XNAS",
                security_type=SecurityType.EQUITY,
                currency="USD",
                isin=None,
                is_active=True,
            ),
        ),
    )
    identity.register_source_definition(
        _SCOPE,
        SourceDefinitionCreateRequest(
            source_definition_id=source_definition_id,
            source_key=FINS_SOURCE_DEFINITION_KEY,
            source_kind=SourceKind.FILING,
            display_name="Fins market disclosure",
            enabled_by_default=True,
        ),
    )
    identity.create_source_subscription(
        _SCOPE,
        SourceSubscriptionCreateRequest(
            subscription_id=subscription_id,
            source_definition_id=source_definition_id,
            company_id=None,
            security_id=security_id,
            status=SubscriptionStatus.ENABLED,
            config=_CONFIG,
        ),
    )
    return source_definition_id, subscription_id, company_id, security_id


@pytest.fixture()
def source_harness(
    platform_cluster: PlatformCluster,
    lifecycle_database: DatabaseFactory,
) -> Iterator[_Harness]:
    """创建迁移后的 owned database 与两个完全独立的 app repositories。

    Args:
        platform_cluster: 提供 pinned PostgreSQL 16 bootstrap DSN 与管理能力的 session fixture。
        lifecycle_database: 为当前 test 分配唯一 database 名称的 factory fixture。

    Yields:
        已迁移、已 seed identity，且含两个独立 app login/repository 的测试句柄。

    Raises:
        PlatformMigrationAdmissionError: upgrade 或 downgrade 的迁移 admission 失败时传播。
        PlatformIntegrationError: 临时 app login 创建或清理失败时传播。
        RepositoryError: 初始 identity seed 失败时由仓储传播。
        SQLAlchemyError: bootstrap 清理或 engine transaction 失败时传播。
    """

    database = lifecycle_database()
    bootstrap_dsn = platform_cluster.dsn_for_database(database, "postgres")
    run_alembic_upgrade(bootstrap_dsn)
    primary_login = create_temporary_login(platform_cluster, database, member_of="dayu_platform_app")
    secondary_login = create_temporary_login(platform_cluster, database, member_of="dayu_platform_app")
    bootstrap_engine = create_platform_engine(bootstrap_dsn)
    primary_engine = create_platform_engine(primary_login.dsn)
    secondary_engine = create_platform_engine(secondary_login.dsn)
    primary_factory = create_platform_session_factory(primary_engine)
    secondary_factory = create_platform_session_factory(secondary_engine)
    identity = PostgresIdentityRepository(primary_factory)
    source_definition_id, subscription_id, company_id, security_id = _seed_identity(identity)
    harness = _Harness(
        cluster=platform_cluster,
        database=database,
        bootstrap_engine=bootstrap_engine,
        primary_engine=primary_engine,
        secondary_engine=secondary_engine,
        primary_factory=primary_factory,
        secondary_factory=secondary_factory,
        repository=PostgresSourceSyncRepository(primary_factory),
        second_repository=PostgresSourceSyncRepository(secondary_factory),
        jobs=PostgresJobStore(primary_factory),
        second_jobs=PostgresJobStore(secondary_factory),
        identity=identity,
        scope=_SCOPE,
        source_definition_id=source_definition_id,
        subscription_id=subscription_id,
        company_id=company_id,
        security_id=security_id,
    )
    try:
        yield harness
    finally:
        primary_engine.dispose()
        secondary_engine.dispose()
        drop_temporary_login(platform_cluster, secondary_login)
        drop_temporary_login(platform_cluster, primary_login)
        with bootstrap_engine.begin() as connection:
            connection.execute(
                text(
                    f"TRUNCATE TABLE {_SCHEMA}.source_health_alert_outbox, "
                    f"{_SCHEMA}.source_health_snapshots, {_SCHEMA}.source_health_states, "
                    f"{_SCHEMA}.source_sync_operations, {_SCHEMA}.source_sync_runs, "
                    f"{_SCHEMA}.job_schedule_occurrences, {_SCHEMA}.agent_run_correlations, "
                    f"{_SCHEMA}.job_events, {_SCHEMA}.job_attempt_receipts, "
                    f"{_SCHEMA}.job_leases, {_SCHEMA}.job_attempts, {_SCHEMA}.job_runs CASCADE"
                )
            )
        bootstrap_engine.dispose()
        run_alembic_downgrade(bootstrap_dsn)


def _new_live_operation(
    harness: _Harness,
    *,
    key: str,
    repository: PostgresSourceSyncRepository | None = None,
    jobs: PostgresJobStore | None = None,
) -> _LiveOperation:
    """经真实 enqueue/claim/acquire 创建 manual Source operation。

    Args:
        harness: 提供 tenant、identity、JobStore 与默认 Source repository 的句柄。
        key: 隔离 enqueue idempotency、trigger UUID 与 worker 名的测试标签。
        repository: 可选 Source repository；省略时使用 primary repository。
        jobs: 可选 JobStore；省略时使用 primary JobStore。

    Returns:
        组合真实 Job claim、冻结 snapshot 与 ``ACQUIRED`` decision 的 live operation。

    Raises:
        AssertionError: acquire 未返回 ``ACQUIRED`` 时抛出。
        SourceSyncRequestRejected: acquire request 不满足 closed contract 时由仓储传播。
        SourceSyncExecutionRejected: 当前 binding 不可执行时由仓储传播。
        SourceSyncRepositoryFailure: Source 持久化失败时由仓储传播。
    """

    claimed = _new_claimed_manual_operation(harness, key=key, repository=repository, jobs=jobs)
    active_repository = repository if repository is not None else harness.repository
    acquire = active_repository.acquire_operation(
        harness.scope,
        _acquire_request(claimed),
    )
    assert acquire.action is SourceOperationAcquireAction.ACQUIRED
    return _LiveOperation(claim=claimed.claim, snapshot=claimed.snapshot, acquire=acquire)


def _new_claimed_manual_operation(
    harness: _Harness,
    *,
    key: str,
    repository: PostgresSourceSyncRepository | None = None,
    jobs: PostgresJobStore | None = None,
) -> _ClaimedOperation:
    """经真实 binding/enqueue/claim 创建尚未 acquire 的 manual Job。

    Args:
        harness: 提供 tenant、subscription 与默认 Source/Job repositories 的句柄。
        key: 隔离 manual payload、idempotency key 与 worker 的测试标签。
        repository: 可选 binding reader；省略时使用 primary Source repository。
        jobs: 可选 enqueue/claim store；省略时使用 primary JobStore。

    Returns:
        尚未 acquire、包含真实 manual Job claim 与 frozen snapshot 的组合。

    Raises:
        AssertionError: Job 未被 claim 或 claim 不属于刚 enqueue 的 Job 时抛出。
        SourceSyncRequestRejected: executable binding 请求非法时由仓储传播。
        SourceSyncExecutionRejected: subscription 当前不可执行时由仓储传播。
        SourceSyncRepositoryFailure: binding 查询失败时由 Source repository 传播。
        RuntimeError: enqueue/claim 的 typed JobStore failure 向调用者传播。
    """

    active_repository = repository if repository is not None else harness.repository
    active_jobs = jobs if jobs is not None else harness.jobs
    binding = active_repository.get_executable_binding(harness.scope, harness.subscription_id)
    available_at = _pg_clock(harness) - timedelta(minutes=1)
    deadline_at = available_at + timedelta(hours=2)
    snapshot = build_source_execution_snapshot(binding, available_at)
    payload = build_manual_source_sync_payload_document(
        ManualSourceSyncPayload(
            subscription_id=harness.subscription_id,
            expected_subscription_version=binding.subscription_version,
            trigger_id=_stable_uuid(f"trigger:{key}"),
            execution_snapshot=snapshot,
            request_fingerprint="a" * 64,
        )
    )
    enqueue = active_jobs.enqueue(
        harness.scope,
        JobEnqueueRequest(
            descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
            idempotency_key=f"source-pg-item5:{key}",
            payload=payload,
            available_at=available_at,
            deadline_at=deadline_at,
        ),
    )
    claim = active_jobs.claim(harness.scope, f"worker-{key}")
    assert claim is not None
    assert claim.job_id == enqueue.job_id
    return _ClaimedOperation(claim=claim, snapshot=snapshot, origin=SourceSyncOrigin.MANUAL)


def _new_scheduled_live_operation(
    harness: _Harness,
    *,
    key: str,
    available_at: datetime | None = None,
    deadline_at: datetime | None = None,
) -> _LiveOperation:
    """经真实 scheduled payload、enqueue、claim 与 acquire 创建 operation。

    Args:
        harness: 提供 scheduled Job 与 Source acquire 所需 repositories 的句柄。
        key: 隔离 schedule key、idempotency key 与 worker 的测试标签。
        available_at: 可选首次enqueue时间；省略时使用既有PG-clock默认。
        deadline_at: 可选未来deadline；与跨UTC日界seed配合使用。

    Returns:
        带 repository-authoritative scheduled snapshot 的 live operation。

    Raises:
        AssertionError: acquire decision 未携带 authoritative snapshot 时抛出。
        SourceSyncRequestRejected: scheduled acquire request 非法时由仓储传播。
        SourceSyncExecutionRejected: scheduled binding 不可执行时由仓储传播。
        SourceSyncRepositoryFailure: Source 持久化失败时由仓储传播。
    """

    claimed = _new_claimed_scheduled_operation(
        harness,
        key=key,
        available_at=available_at,
        deadline_at=deadline_at,
    )
    acquire = harness.repository.acquire_operation(harness.scope, _acquire_request(claimed))
    assert acquire.execution_snapshot is not None
    return _LiveOperation(claim=claimed.claim, snapshot=acquire.execution_snapshot, acquire=acquire)


def _new_claimed_scheduled_operation(
    harness: _Harness,
    *,
    key: str,
    available_at: datetime | None = None,
    deadline_at: datetime | None = None,
) -> _ClaimedOperation:
    """经真实 scheduled payload/enqueue/claim 创建尚未 acquire 的 Job。

    Args:
        harness: 提供 binding、subscription 与 primary JobStore 的测试句柄。
        key: 隔离 schedule payload、idempotency key 与 worker 的测试标签。
        available_at: 可选首次enqueue时间；省略时取PG clock前一分钟。
        deadline_at: 可选未来deadline；省略时为首次时间后二小时。

    Returns:
        尚未 acquire、包含真实 scheduled Job claim 与候选 snapshot 的组合。

    Raises:
        AssertionError: Job 未被 claim 或 claim 不属于刚 enqueue 的 Job 时抛出。
        SourceSyncRequestRejected: executable binding 请求非法时由仓储传播。
        SourceSyncExecutionRejected: subscription 当前不可执行时由仓储传播。
        SourceSyncRepositoryFailure: binding 查询失败时由 Source repository 传播。
        RuntimeError: enqueue/claim 的 typed JobStore failure 向调用者传播。
    """

    binding = harness.repository.get_executable_binding(harness.scope, harness.subscription_id)
    original_available_at = (
        available_at
        if available_at is not None
        else _pg_clock(harness) - timedelta(minutes=1)
    )
    request_deadline_at = (
        deadline_at
        if deadline_at is not None
        else original_available_at + timedelta(hours=2)
    )
    payload = build_scheduled_source_sync_payload_document(
        ScheduledSourceSyncPayload(
            subscription_id=harness.subscription_id,
            source_definition_id=harness.source_definition_id,
            expected_subscription_version=binding.subscription_version,
            schedule_key=f"source-pg-schedule:{key}",
            source_request_fingerprint="9" * 64,
        )
    )
    enqueue = harness.jobs.enqueue(
        harness.scope,
        JobEnqueueRequest(
            descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
            idempotency_key=f"source-pg-scheduled:{key}",
            payload=payload,
            available_at=original_available_at,
            deadline_at=request_deadline_at,
        ),
    )
    claim = harness.jobs.claim(harness.scope, f"scheduled-worker-{key}")
    assert claim is not None and claim.job_id == enqueue.job_id
    snapshot = build_source_execution_snapshot(binding, original_available_at)
    return _ClaimedOperation(claim=claim, snapshot=snapshot, origin=SourceSyncOrigin.SCHEDULED)


def _acquire_request(claimed: _ClaimedOperation) -> SourceOperationAcquireRequest:
    """从真实 claimed facts 构造 exact acquire request。

    Args:
        claimed: 提供真实 Job lineage、origin、payload SHA 与候选 snapshot 的 claim 组合。

    Returns:
        与 claim facts 精确一致、仅 manual origin 携带候选 snapshot 的 acquire request。

    Raises:
        无。
    """

    return SourceOperationAcquireRequest(
        origin=claimed.origin,
        definition_id=claimed.claim.definition_id,
        descriptor=claimed.claim.descriptor,
        job_id=claimed.claim.job_id,
        attempt_id=claimed.claim.attempt_id,
        attempt_number=claimed.claim.attempt_number,
        payload_sha256=claimed.claim.payload.sha256,
        candidate_execution_snapshot=(
            claimed.snapshot if claimed.origin is SourceSyncOrigin.MANUAL else None
        ),
    )


def _retry_claim(harness: _Harness, claimed: _ClaimedOperation, *, worker: str) -> _ClaimedOperation:
    """让真实 JobStore fail/retry 并由第二 store 形成新 live attempt。

    Args:
        harness: 提供 primary fail 与 secondary retry claim JobStores 的句柄。
        claimed: 当前 attempt 及其 frozen snapshot/origin。
        worker: 领取 retry attempt 的 worker 标识。

    Returns:
        同一 Job 的新 attempt claim，并保留原 snapshot 与 origin。

    Raises:
        AssertionError: fail 未安排 retry，或新 claim 缺失/属于其他 Job 时抛出。
        RuntimeError: fail 或 claim 的 typed JobStore failure 向调用者传播。
    """

    recovery = harness.jobs.fail(
        harness.scope,
        claimed.claim.lease,
        JobFailure(safe_error_code=SafeJobErrorCode.SOURCE_INTERRUPTED, retryable=True),
    )
    assert recovery.next_available_at is not None
    claim_clock = recovery.next_available_at + timedelta(seconds=1)

    def replace_claim_clock(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> CursorReplacement:
        """把 retry claim 的 PG transaction/clock 固定到 next_available 后。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；仅识别 claim 的双时钟查询。
            parameters: 原 SQL 的绑定参数映射，替换时保持不变。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            原 SQL 或固定双时钟 SQL，以及原绑定参数映射。

        Raises:
            无。
        """

        if "transaction_timestamp(), clock_timestamp()" in statement.lower():
            fixed = claim_clock.isoformat()
            return f"SELECT TIMESTAMPTZ '{fixed}', TIMESTAMPTZ '{fixed}'", parameters
        return statement, parameters

    event.listen(harness.secondary_engine, "before_cursor_execute", replace_claim_clock, retval=True)
    try:
        retry = harness.second_jobs.claim(harness.scope, worker)
    finally:
        event.remove(harness.secondary_engine, "before_cursor_execute", replace_claim_clock)
    assert retry is not None and retry.job_id == claimed.claim.job_id
    return _ClaimedOperation(claim=retry, snapshot=claimed.snapshot, origin=claimed.origin)


def test_manual_retry_across_utc_midnight_keeps_original_available_at_for_existing_operation_provenance(
    source_harness: _Harness,
) -> None:
    """跨UTC日界retry takeover仍以首次available构造manual provenance。

    Args:
        source_harness: 真实Job/Source repositories与隔离PostgreSQL 16数据库。

    Returns:
        无。

    Raises:
        AssertionError: current/original未分离或generation 2 provenance漂移时抛出。
    """

    binding = source_harness.repository.get_executable_binding(
        source_harness.scope,
        source_harness.subscription_id,
    )
    pg_now = _pg_clock(source_harness)
    original_available_at = (
        pg_now.replace(hour=23, minute=59, second=59, microsecond=123456)
        - timedelta(days=1)
    )
    snapshot = build_source_execution_snapshot(binding, original_available_at)
    payload = build_manual_source_sync_payload_document(
        ManualSourceSyncPayload(
            subscription_id=source_harness.subscription_id,
            expected_subscription_version=binding.subscription_version,
            trigger_id=_stable_uuid("manual-midnight-original-trigger"),
            execution_snapshot=snapshot,
            request_fingerprint="b" * 64,
        )
    )
    enqueue = source_harness.jobs.enqueue(
        source_harness.scope,
        JobEnqueueRequest(
            descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
            idempotency_key="source-pg-manual-midnight-original",
            payload=payload,
            available_at=original_available_at,
            deadline_at=pg_now + timedelta(hours=2),
        ),
    )
    claim = source_harness.jobs.claim(source_harness.scope, "manual-midnight-worker")
    assert claim is not None and claim.job_id == enqueue.job_id
    claimed = _ClaimedOperation(
        claim=claim,
        snapshot=snapshot,
        origin=SourceSyncOrigin.MANUAL,
    )
    first_acquire = source_harness.repository.acquire_operation(
        source_harness.scope,
        _acquire_request(claimed),
    )
    assert first_acquire.action is SourceOperationAcquireAction.ACQUIRED
    assert first_acquire.execution_snapshot == snapshot
    retry = _retry_claim(
        source_harness,
        claimed,
        worker="manual-midnight-retry-worker",
    )
    with source_harness.bootstrap_engine.connect() as connection:
        current_available_at, persisted_original_at = connection.execute(
            text(
                f"SELECT available_at, original_available_at FROM {_SCHEMA}.job_runs "
                "WHERE id=:job_id"
            ),
            {"job_id": enqueue.job_id},
        ).one()
        connection.rollback()
    assert isinstance(current_available_at, datetime)
    assert isinstance(persisted_original_at, datetime)
    current_available_at = current_available_at.astimezone(timezone.utc)
    persisted_original_at = persisted_original_at.astimezone(timezone.utc)
    assert persisted_original_at == original_available_at
    assert current_available_at != persisted_original_at
    assert current_available_at.date() > persisted_original_at.date()
    takeover = source_harness.second_repository.acquire_operation(
        source_harness.scope,
        _acquire_request(retry),
    )
    assert takeover.action is SourceOperationAcquireAction.ACQUIRED
    assert takeover.generation == 2
    assert takeover.execution_snapshot == snapshot
    assert takeover.execution_snapshot_sha256 == build_source_execution_snapshot_document(
        snapshot
    ).sha256


def test_scheduled_retry_before_first_acquire_and_existing_takeover_use_original_available_at_seed(
    source_harness: _Harness,
) -> None:
    """scheduled首次acquire前retry及generation 2均复用original seed。

    Args:
        source_harness: 真实Job/Source repositories与隔离PostgreSQL 16数据库。

    Returns:
        无。

    Raises:
        AssertionError: 任一路径用mutable available重建snapshot时抛出。
    """

    pg_now = _pg_clock(source_harness)
    original_available_at = (
        pg_now.replace(hour=23, minute=59, second=58, microsecond=654321)
        - timedelta(days=1)
    )
    deadline_at = pg_now + timedelta(hours=3)
    before_first = _new_claimed_scheduled_operation(
        source_harness,
        key="scheduled-retry-before-first-acquire",
        available_at=original_available_at,
        deadline_at=deadline_at,
    )
    retried_before_first = _retry_claim(
        source_harness,
        before_first,
        worker="scheduled-retry-before-first-worker",
    )
    with source_harness.bootstrap_engine.connect() as connection:
        first_current_at, first_original_at = connection.execute(
            text(
                f"SELECT available_at, original_available_at FROM {_SCHEMA}.job_runs "
                "WHERE id=:job_id"
            ),
            {"job_id": before_first.claim.job_id},
        ).one()
        connection.rollback()
    assert isinstance(first_current_at, datetime)
    assert isinstance(first_original_at, datetime)
    first_current_at = first_current_at.astimezone(timezone.utc)
    first_original_at = first_original_at.astimezone(timezone.utc)
    assert first_original_at == original_available_at
    assert first_current_at != first_original_at
    assert first_current_at.date() > first_original_at.date()
    first_after_retry = source_harness.second_repository.acquire_operation(
        source_harness.scope,
        _acquire_request(retried_before_first),
    )
    assert first_after_retry.action is SourceOperationAcquireAction.ACQUIRED
    assert first_after_retry.generation == 1
    assert first_after_retry.execution_snapshot == before_first.snapshot
    assert first_after_retry.execution_snapshot_sha256 == build_source_execution_snapshot_document(
        before_first.snapshot
    ).sha256

    existing = _new_scheduled_live_operation(
        source_harness,
        key="scheduled-existing-original-takeover",
        available_at=original_available_at + timedelta(seconds=1),
        deadline_at=deadline_at,
    )
    existing_claimed = _ClaimedOperation(
        claim=existing.claim,
        snapshot=existing.snapshot,
        origin=SourceSyncOrigin.SCHEDULED,
    )
    retried_existing = _retry_claim(
        source_harness,
        existing_claimed,
        worker="scheduled-existing-takeover-worker",
    )
    with source_harness.bootstrap_engine.connect() as connection:
        existing_current_at, existing_original_at = connection.execute(
            text(
                f"SELECT available_at, original_available_at FROM {_SCHEMA}.job_runs "
                "WHERE id=:job_id"
            ),
            {"job_id": existing.claim.job_id},
        ).one()
        connection.rollback()
    assert isinstance(existing_current_at, datetime)
    assert isinstance(existing_original_at, datetime)
    existing_current_at = existing_current_at.astimezone(timezone.utc)
    existing_original_at = existing_original_at.astimezone(timezone.utc)
    assert existing_original_at == original_available_at + timedelta(seconds=1)
    assert existing_current_at != existing_original_at
    assert existing_current_at.date() > existing_original_at.date()
    takeover = source_harness.second_repository.acquire_operation(
        source_harness.scope,
        _acquire_request(retried_existing),
    )
    assert takeover.action is SourceOperationAcquireAction.ACQUIRED
    assert takeover.generation == 2
    assert takeover.operation_id == existing.acquire.operation_id
    assert takeover.execution_snapshot == existing.snapshot
    assert takeover.execution_snapshot_sha256 == existing.acquire.execution_snapshot_sha256


def _take_over_operation(harness: _Harness, live: _LiveOperation) -> _LiveOperation:
    """让真实 JobStore retry 到新 attempt，并由第二 repository takeover。

    Args:
        harness: 提供两套 Job/Source repositories 的隔离数据库句柄。
        live: 将由 retry attempt takeover 的当前 manual live operation。

    Returns:
        由新 attempt 持有且 snapshot 不变的第二 generation live operation。

    Raises:
        AssertionError: takeover acquire 未返回 ``ACQUIRED`` 时抛出。
        SourceSyncRequestRejected: takeover request 非法时由仓储传播。
        SourceSyncExecutionRejected: takeover 当前不可执行时由仓储传播。
        SourceSyncRepositoryFailure: takeover 持久化失败时由仓储传播。
        RuntimeError: retry JobStore failure 向调用者传播。
    """

    claimed = _ClaimedOperation(
        claim=live.claim,
        snapshot=live.snapshot,
        origin=SourceSyncOrigin.MANUAL,
    )
    retry = _retry_claim(harness, claimed, worker="takeover-worker")
    acquire = harness.second_repository.acquire_operation(
        harness.scope,
        _acquire_request(retry),
    )
    assert acquire.action is SourceOperationAcquireAction.ACQUIRED
    return _LiveOperation(claim=retry.claim, snapshot=live.snapshot, acquire=acquire)


def _insert_drift_operation_as_app(
    harness: _Harness,
    claimed: _ClaimedOperation,
    *,
    label: str,
) -> tuple[UUID, SourceExecutionSnapshot, str]:
    """由真实 app role 插入 self-canonical 但窗口移位的 ACTIVE operation。

    Args:
        harness: 提供真实 app-role engine、tenant scope 与数据库 clock 的句柄。
        claimed: 为 drift operation 提供 Job/attempt/payload/binding lineage 的 claim。
        label: 隔离 drift operation UUID 的语义标签。

    Returns:
        Drift operation UUID、日期窗口平移后的 snapshot 及其 canonical SHA。

    Raises:
        SQLAlchemyError: tenant context 设置或 app-role INSERT 失败时向调用者传播。
        ValueError: 平移 snapshot 或 canonical document 违反 domain invariant 时传播。
    """

    shifted = SourceExecutionSnapshot(
        binding=claimed.snapshot.binding,
        canonical_ticker=claimed.snapshot.canonical_ticker,
        query_start_date=claimed.snapshot.query_start_date + timedelta(days=1),
        query_end_date=claimed.snapshot.query_end_date + timedelta(days=1),
    )
    document = build_source_execution_snapshot_document(shifted)
    operation_id = _stable_uuid(f"drift-operation:{label}")
    acquired_at = _pg_clock(harness)
    with harness.primary_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": harness.scope.tenant_id.value},
        ).scalar_one()
        connection.execute(
            text(
                f"INSERT INTO {_SCHEMA}.source_sync_operations "
                "(id, tenant_id, job_run_id, subscription_id, owner_attempt_id, state, generation, "
                "owner_binding_disposition, payload_sha256, execution_snapshot_sha256, "
                "execution_snapshot_json, acquired_at) VALUES "
                "(:id, :tenant_id, :job_id, :subscription_id, :attempt_id, 'active', 1, "
                "'ready', :payload_sha256, :snapshot_sha256, CAST(:snapshot_json AS jsonb), :acquired_at)"
            ),
            {
                "id": operation_id,
                "tenant_id": harness.scope.tenant_id.value,
                "job_id": claimed.claim.job_id,
                "subscription_id": claimed.snapshot.binding.subscription_id.value,
                "attempt_id": claimed.claim.attempt_id,
                "payload_sha256": claimed.claim.payload.sha256,
                "snapshot_sha256": document.sha256,
                "snapshot_json": document.canonical_bytes.decode("utf-8"),
                "acquired_at": acquired_at,
            },
        )
    return operation_id, shifted, document.sha256


def _exercise_closed_reconstruction_branches(harness: _Harness, snapshot: SourceExecutionSnapshot) -> None:
    """覆盖 concrete 的 closed row readers 与 terminal disposition 负面矩阵。

    Args:
        harness: 提供 bootstrap row fixture 与 production helper module 的测试句柄。
        snapshot: 用于 terminal disposition matrix 的合法 execution snapshot。

    Returns:
        无；全部 closed reader 与 terminal disposition 断言通过即完成。

    Raises:
        AssertionError: 任一 reconstruction 正例、负例或 disposition 事实不符合预期时抛出。
        SQLAlchemyError: 测试 row 查询或回滚失败时向调用者传播。
    """

    test_uuid = _stable_uuid("row-reader")
    with harness.bootstrap_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT CAST(:uuid_value AS uuid) AS uuid_value, CAST(NULL AS uuid) AS null_uuid, "
                "CAST('00000000-0000-0000-0000-000000000000' AS uuid) AS zero_uuid, "
                "7::integer AS int_value, true AS bool_value, 3.5::double precision AS float_value, "
                "TIMESTAMP '2026-01-01 00:00:00' AS naive_datetime, DATE '2026-01-01' AS date_value, "
                "CAST(NULL AS integer) AS null_int, CAST(NULL AS timestamptz) AS null_datetime, "
                "CAST(NULL AS date) AS null_date, CAST(NULL AS text) AS null_error, "
                "'fins_invariant'::text AS error_value, '[1]'::jsonb AS json_list, "
                "CAST(:json_object AS jsonb) AS json_object, CAST(:wrong_sha AS text) AS wrong_sha"
            ),
            {"uuid_value": test_uuid, "json_object": '{"schema_version":1}', "wrong_sha": "f" * 64},
        ).one()
        connection.rollback()
    assert postgres_sources_module._rv_text(row, "uuid_value") == str(test_uuid)
    assert postgres_sources_module._rv_optional_uuid(row, "null_uuid") is None
    assert postgres_sources_module._rv_optional_int(row, "null_int") is None
    assert postgres_sources_module._rv_optional_datetime(row, "null_datetime") is None
    assert postgres_sources_module._rv_optional_date(row, "null_date") is None
    assert postgres_sources_module._rv_optional_error(row, "null_error") is None
    assert postgres_sources_module._rv_optional_error(row, "error_value") is SourceSyncErrorCode.FINS_INVARIANT
    with pytest.raises(ValueError):
        postgres_sources_module._rv_datetime(row, "naive_datetime")
    assert postgres_sources_module._rv_date(row, "date_value") == date(2026, 1, 1)
    assert postgres_sources_module._narrow_json({"items": [None, "x", 1, True]}) == {
        "items": [None, "x", 1, True]
    }
    for reader, key in (
        (postgres_sources_module._rv_text, "float_value"),
        (postgres_sources_module._rv_int, "bool_value"),
        (postgres_sources_module._rv_bool, "int_value"),
        (postgres_sources_module._rv_uuid, "zero_uuid"),
        (postgres_sources_module._rv_datetime, "date_value"),
        (postgres_sources_module._rv_date, "naive_datetime"),
        (postgres_sources_module._rv_json_object, "json_list"),
    ):
        with pytest.raises(ValueError):
            reader(row, key)
    with pytest.raises(ValueError):
        postgres_sources_module._narrow_json(3.5)
    with pytest.raises(ValueError):
        postgres_sources_module._canonical_document_from_json(
            row,
            json_key="json_object",
            sha_key="wrong_sha",
            schema_name="test.source-row",
        )
    with pytest.raises(ValueError):
        postgres_sources_module._canonical_json_text(
            CanonicalJobDocument(
                schema_name="test.invalid-utf8",
                schema_version=1,
                canonical_bytes=b"\xff",
                sha256="e" * 64,
            )
        )
    no_provider_disabled = SourceNoProviderTerminalCandidate(reason=SourceNoProviderReason.DISABLED)
    no_provider_drift = SourceNoProviderTerminalCandidate(reason=SourceNoProviderReason.BINDING_DRIFT)
    fins = _no_change_candidate()
    invalid_cases = (
        (no_provider_disabled, SourceBindingDisposition.READY),
        (fins, SourceBindingDisposition.DISABLED),
        (no_provider_drift, SourceBindingDisposition.DISABLED),
        (fins, SourceBindingDisposition.STALE),
        (no_provider_disabled, SourceBindingDisposition.STALE),
    )
    for candidate, disposition in invalid_cases:
        with pytest.raises(ValueError):
            postgres_sources_module._final_observation(
                candidate=candidate,
                stored_disposition=disposition,
                current_disposition=disposition,
                snapshot=snapshot,
                authoritative_utc_date=snapshot.query_end_date,
            )
    stale = postgres_sources_module._final_observation(
        candidate=no_provider_drift,
        stored_disposition=SourceBindingDisposition.STALE,
        current_disposition=SourceBindingDisposition.STALE,
        snapshot=snapshot,
        authoritative_utc_date=snapshot.query_end_date,
    )
    disabled = postgres_sources_module._final_observation(
        candidate=no_provider_disabled,
        stored_disposition=SourceBindingDisposition.DISABLED,
        current_disposition=SourceBindingDisposition.DISABLED,
        snapshot=snapshot,
        authoritative_utc_date=snapshot.query_end_date,
    )
    assert stale.outcome is SourceSyncOutcome.STALE_SUBSCRIPTION
    assert disabled.outcome is SourceSyncOutcome.SKIPPED_DISABLED


def _no_change_candidate() -> SourceFinsTerminalCandidate:
    """构造合法空 observation。

    Args:
        无。

    Returns:
        零文档、零计数且 outcome 为 ``NO_CHANGE`` 的合法 terminal candidate。

    Raises:
        无。
    """

    return SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.NO_CHANGE,
        proposed_safe_error_code=None,
        documents=(),
        records_discovered=0,
        records_downloaded=0,
        records_reused=0,
        records_ignored=0,
        records_failed=0,
        latest_source_observed_date=None,
    )


def _failure_candidate(error: SourceSyncErrorCode = SourceSyncErrorCode.FINS_INVARIANT) -> SourceFinsTerminalCandidate:
    """构造零 provider 数据的合法 failed observation。

    Args:
        error: 合法 failed outcome 使用的 closed safe error code。

    Returns:
        零文档、零计数且携带 ``error`` 的合法 failed terminal candidate。

    Raises:
        TypeError: ``error`` 不是 ``SourceSyncErrorCode`` 时由 candidate 校验传播。
        ValueError: ``error`` 不允许用于零计数 failed candidate 时传播。
    """

    return SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.FAILED,
        proposed_safe_error_code=error,
        documents=(),
        records_discovered=0,
        records_downloaded=0,
        records_reused=0,
        records_ignored=0,
        records_failed=0,
        latest_source_observed_date=None,
    )


def _evidence(snapshot: SourceExecutionSnapshot, *, label: str, observed_date: date | None = None) -> SourceDocumentEvidence:
    """构造与 frozen snapshot 完全一致的单文档 evidence。

    Args:
        snapshot: 提供 canonical ticker 与默认 source observed date 的冻结 snapshot。
        label: 隔离 document identity 与 locator 的测试标签。
        observed_date: 可选 source date；省略时使用 snapshot query end date。

    Returns:
        Locator identity、hash 与 snapshot ticker 一致的单文档 evidence。

    Raises:
        TypeError: Evidence 或 locator 字段类型非法时由 domain 校验传播。
        ValueError: Locator canonical identity/hash 或 evidence 形态非法时传播。
    """

    document_id = f"doc-{label}"
    locator = build_source_evidence_locator_document(
        repository_id="dayu.fins.public.v1",
        ticker=snapshot.canonical_ticker,
        document_id=document_id,
        source_kind="filing",
        artifact_kind="source",
        document_version="v1",
        source_fingerprint="b" * 64,
        primary_content_sha256="c" * 64,
        locator_kind="document",
        locator_content_sha256="d" * 64,
    )
    return SourceDocumentEvidence(
        document_id=document_id,
        form_type="10-K",
        source_observed_date=observed_date if observed_date is not None else snapshot.query_end_date,
        locator=locator,
        locator_sha256=locator.document.sha256,
    )


def _partial_candidate(live: _LiveOperation, *, label: str) -> SourceFinsTerminalCandidate:
    """构造一个 verified document 加一个 failed record 的 partial observation。

    Args:
        live: 提供 evidence 必须匹配的 execution snapshot。
        label: 隔离 evidence document identity 的测试标签。

    Returns:
        一个 verified document 加一个 failed record 的合法 ``PARTIAL`` candidate。

    Raises:
        TypeError: Evidence 或 candidate 字段类型非法时由 domain 校验传播。
        ValueError: Evidence/candidate 的 canonical 或计数矩阵非法时传播。
    """

    evidence = _evidence(live.snapshot, label=label)
    return SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.PARTIAL,
        proposed_safe_error_code=SourceSyncErrorCode.PARTIAL_BATCH,
        documents=(evidence,),
        records_discovered=2,
        records_downloaded=1,
        records_reused=0,
        records_ignored=0,
        records_failed=1,
        latest_source_observed_date=evidence.source_observed_date,
    )


def _record_terminal(
    harness: _Harness,
    live: _LiveOperation,
    candidate: SourceFinsTerminalCandidate | SourceNoProviderTerminalCandidate,
    *,
    repository: PostgresSourceSyncRepository | None = None,
) -> SourceTerminalRecordDecision:
    """以 live acquired facts 构造并提交 terminal request。

    Args:
        harness: 提供 tenant scope 与默认 Source repository 的句柄。
        live: 提供 operation、Job lineage、generation 与 snapshot SHA 的 live facts。
        candidate: 待持久化的 closed Fins 或 no-provider terminal observation。
        repository: 可选提交 repository；省略时使用 primary repository。

    Returns:
        Repository 对 terminal commit、lease loss 或 replay boundary 的 closed decision。

    Raises:
        AssertionError: Live acquire decision 缺少 generation 或 snapshot SHA 时抛出。
        SourceSyncRequestRejected: Terminal request 不满足 closed lineage contract 时由仓储传播。
        SourceSyncRepositoryFailure: Terminal transaction、persisted invariant 或基础设施失败时传播。
    """

    active_repository = repository if repository is not None else harness.repository
    assert live.acquire.generation is not None
    assert live.acquire.execution_snapshot_sha256 is not None
    return active_repository.record_terminal(
        harness.scope,
        SourceTerminalRecordRequest(
            operation_id=live.acquire.operation_id,
            job_id=live.claim.job_id,
            attempt_id=live.claim.attempt_id,
            attempt_number=live.claim.attempt_number,
            expected_generation=live.acquire.generation,
            expected_execution_snapshot_sha256=live.acquire.execution_snapshot_sha256,
            candidate=candidate,
        ),
    )


def _source_counts(harness: _Harness) -> tuple[int, int, int, int, int]:
    """返回 operation/run/head/snapshot/alert 五表行数。

    Args:
        harness: 提供 bootstrap read connection 的隔离数据库句柄。

    Returns:
        按 operation、run、health head、snapshot、alert 排列的五表行数。

    Raises:
        AssertionError: 查询结果不是五个严格 ``int`` 时抛出。
        SQLAlchemyError: 聚合查询或回滚失败时向调用者传播。
    """

    with harness.bootstrap_engine.connect() as connection:
        row = connection.execute(
            text(
                f"SELECT (SELECT count(*) FROM {_SCHEMA}.source_sync_operations), "
                f"(SELECT count(*) FROM {_SCHEMA}.source_sync_runs), "
                f"(SELECT count(*) FROM {_SCHEMA}.source_health_states), "
                f"(SELECT count(*) FROM {_SCHEMA}.source_health_snapshots), "
                f"(SELECT count(*) FROM {_SCHEMA}.source_health_alert_outbox)"
            )
        ).one()
        connection.rollback()
    values = tuple(row)
    assert len(values) == 5 and all(type(value) is int for value in values)
    return values[0], values[1], values[2], values[3], values[4]


def _assert_empty_terminal_decision(
    decision: SourceTerminalRecordDecision,
    action: SourceTerminalRecordAction,
) -> None:
    """断言 live-loss decision 的 action 与所有 optional facts 精确为空。

    Args:
        decision: 待验证为不携带任何 durable fact 的 terminal decision。
        action: 期望的 closed terminal action，通常为 lease lost 或 stale generation。

    Returns:
        无。

    Raises:
        AssertionError: Action 不匹配或任一 optional durable fact 非空时抛出。
    """

    assert decision.action is action
    assert decision.result is None
    assert decision.receipt is None
    assert decision.health_after is None
    assert decision.health_snapshot is None
    assert decision.alert_event is None


def _assert_repository_error(
    error: SourceSyncRepositoryFailure,
    code: SourceSyncRepositoryFailureCode,
) -> None:
    """断言 repository error 的闭合 code、正文与 from-None 形态。

    Args:
        error: 待验证的 closed Source repository failure。
        code: 期望的精确 failure code。

    Returns:
        无。

    Raises:
        AssertionError: Code、正文、cause 或 exception chaining 形态不闭合时抛出。
    """

    assert error.code is code
    assert error.args == (code.value,)
    assert str(error) == code.value
    assert error.__cause__ is None
    assert error.__suppress_context__ is True


def test_postgres_source_sync_repository_class_and_session_factory_constructor_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concrete owner/protocol/七签名/constructor generic 与零 I/O 全部精确。

    Args:
        monkeypatch: 拦截 Session factory，证明 constructor 不执行数据库 I/O 的 pytest fixture。

    Returns:
        无。

    Raises:
        AssertionError: Owner、protocol、签名、类型提示或零 I/O 断言失败时由测试抛出。
    """

    assert PostgresSourceSyncRepository.__module__ == "dayu.investment.storage.postgres_sources"
    assert PostgresSourceSyncRepository.__qualname__ == "PostgresSourceSyncRepository"
    assert PostgresSourceSyncRepository.__bases__ == (SourceSyncRepositoryProtocol,)
    assert issubclass(PostgresSourceSyncRepository, SourceSyncRepositoryProtocol)
    constructor = inspect.signature(PostgresSourceSyncRepository.__init__)
    assert tuple(constructor.parameters) == ("self", "session_factory")
    assert get_type_hints(PostgresSourceSyncRepository.__init__) == {
        "session_factory": sessionmaker[Session],
        "return": type(None),
    }
    method_names = (
        "get_executable_binding",
        "acquire_operation",
        "record_terminal",
        "get_source_receipt",
        "get_health",
        "list_health_snapshots",
        "reenable_health",
    )
    assert tuple(
        name for name in PostgresSourceSyncRepository.__dict__ if name in method_names
    ) == method_names
    for name in method_names:
        concrete_method = PostgresSourceSyncRepository.__dict__[name]
        protocol_method = SourceSyncRepositoryProtocol.__dict__[name]
        assert inspect.signature(concrete_method) == inspect.signature(protocol_method)
        assert get_type_hints(concrete_method) == get_type_hints(protocol_method)
    factory = sessionmaker()
    factory_calls = 0

    def reject_factory_call(_factory: sessionmaker[Session]) -> Session:
        """若 constructor 试图创建 Session 则立即失败。

        Args:
            _factory: 被 constructor 调用的 Session factory；仅用于匹配替换后的调用签名。

        Returns:
            无正常返回；每次调用都立即失败。

        Raises:
            AssertionError: Constructor 误调用 Session factory 时无条件抛出。
        """

        nonlocal factory_calls
        factory_calls += 1
        raise AssertionError("constructor must not create a Session")

    monkeypatch.setattr(sessionmaker, "__call__", reject_factory_call)
    repository = PostgresSourceSyncRepository(factory)
    assert repository._session_factory is factory
    assert factory_calls == 0
    assert isinstance(repository, SourceSyncRepositoryProtocol)


def test_heartbeat_extended_attempt_lease_allows_terminal_after_job_lease_audit_expiry(
    source_harness: _Harness,
) -> None:
    """Source live truth 读取 attempt expiry，而 job lease expiry 只保留审计。

    Args:
        source_harness: 提供真实 heartbeat、audit lease 与 terminal repositories 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Extended attempt lease 未允许 terminal 或 durable facts 不符时由测试抛出。
    """

    live = _new_live_operation(source_harness, key="heartbeat")
    heartbeat_clock = live.claim.lease.expires_at - timedelta(seconds=1)

    def replace_heartbeat_clock(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> CursorReplacement:
        """把真实 heartbeat 的 transaction/clock 固定到 audit expiry 前一秒。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；仅识别 heartbeat 的双时钟查询。
            parameters: 原 SQL 的绑定参数映射，替换时保持不变。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            原 SQL 或固定 heartbeat 双时钟 SQL，以及原绑定参数映射。

        Raises:
            无。
        """

        if "transaction_timestamp(), clock_timestamp()" in statement.lower():
            fixed = heartbeat_clock.isoformat()
            return f"SELECT TIMESTAMPTZ '{fixed}', TIMESTAMPTZ '{fixed}'", parameters
        return statement, parameters

    event.listen(source_harness.primary_engine, "before_cursor_execute", replace_heartbeat_clock, retval=True)
    try:
        heartbeat = source_harness.jobs.heartbeat(source_harness.scope, live.claim.lease)
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", replace_heartbeat_clock)
    assert heartbeat.claim.lease.expires_at > live.claim.lease.expires_at
    terminal_clock = live.claim.lease.expires_at + timedelta(seconds=1)

    def replace_terminal_clock(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> CursorReplacement:
        """把 terminal clock 固定到 audit expiry 后、heartbeat expiry 前。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；仅识别 terminal 的单时钟查询。
            parameters: 原 SQL 的绑定参数映射，替换时保持不变。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            原 SQL 或固定 terminal 时钟 SQL，以及原绑定参数映射。

        Raises:
            无。
        """

        if "clock_timestamp()" in statement.lower():
            return f"SELECT TIMESTAMPTZ '{terminal_clock.isoformat()}'", parameters
        return statement, parameters

    event.listen(source_harness.primary_engine, "before_cursor_execute", replace_terminal_clock, retval=True)
    try:
        decision = _record_terminal(source_harness, live, _no_change_candidate())
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", replace_terminal_clock)
    assert decision.action is SourceTerminalRecordAction.RECORDED


def test_single_clock_after_all_nowait_locks_rejects_deadline_or_attempt_expiry_without_source_dml(
    source_harness: _Harness,
) -> None:
    """九锁后只有一个 clock，expired attempt 在任何 Source DML 前拒绝。

    Args:
        source_harness: 提供真实锁序、Job deadline 与 Source terminal transaction 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Clock 数量/位置、closed decision 或零 Source DML 事实不符时由测试抛出。
    """

    statements: list[str] = []
    live = _new_live_operation(source_harness, key="single-clock")
    fixed_clock = live.claim.lease.expires_at + timedelta(seconds=1)

    def recorder(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        _parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> CursorReplacement:
        """记录 SQL，并把唯一 terminal clock 固定到 attempt expiry 后。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；规范化记录并识别单时钟查询。
            _parameters: 原 SQL 的绑定参数映射，替换时保持不变。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            原 SQL 或固定 terminal 时钟 SQL，以及原绑定参数映射。

        Raises:
            无。
        """

        statements.append(" ".join(statement.lower().split()))
        if "clock_timestamp()" in statement.lower():
            return f"SELECT TIMESTAMPTZ '{fixed_clock.isoformat()}'", _parameters
        return statement, _parameters

    event.listen(source_harness.primary_engine, "before_cursor_execute", recorder, retval=True)
    try:
        decision = _record_terminal(source_harness, live, _no_change_candidate())
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", recorder)
    assert decision.action is SourceTerminalRecordAction.LEASE_LOST
    lock_positions = [index for index, sql in enumerate(statements) if "for update nowait" in sql]
    clock_positions = [index for index, sql in enumerate(statements) if "clock_timestamp()" in sql]
    assert len(lock_positions) == 9
    assert len(clock_positions) == 1 and clock_positions[0] > lock_positions[-1]
    assert _source_counts(source_harness)[1:] == (0, 0, 0, 0)

    deadline_live = _new_live_operation(source_harness, key="single-clock-deadline")
    deadline_clock = deadline_live.claim.deadline_at + timedelta(seconds=1)

    def replace_deadline_clock(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> CursorReplacement:
        """把唯一 terminal clock 固定到 durable deadline 后。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；仅识别 terminal 的单时钟查询。
            parameters: 原 SQL 的绑定参数映射，替换时保持不变。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            原 SQL 或 durable deadline 后的固定时钟 SQL，以及原绑定参数映射。

        Raises:
            无。
        """

        if "clock_timestamp()" in statement.lower():
            return f"SELECT TIMESTAMPTZ '{deadline_clock.isoformat()}'", parameters
        return statement, parameters

    before = _source_counts(source_harness)
    event.listen(source_harness.primary_engine, "before_cursor_execute", replace_deadline_clock, retval=True)
    try:
        deadline_decision = _record_terminal(source_harness, deadline_live, _no_change_candidate())
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", replace_deadline_clock)
    _assert_empty_terminal_decision(deadline_decision, SourceTerminalRecordAction.JOB_NOT_LIVE)
    assert _source_counts(source_harness) == before


def test_acquire_and_terminal_nowait_map_only_sqlstate_55p03_lock_not_available_to_retryable_repository_failure(
    source_harness: _Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acquire/terminal typed lock 与四种 rollback outcome 全序精确。

    Args:
        source_harness: 提供两套 app repositories 与可由 bootstrap connection 加锁的隔离 PG fixture。
        monkeypatch: 注入 rollback、factory 与 typed lock failure 的 pytest fixture。

    Returns:
        无。

    Raises:
        AssertionError: Lock/error mapping、rollback precedence 或零 mutation 断言失败时由测试抛出。
    """

    live = _new_live_operation(source_harness, key="nowait")
    claimed = _ClaimedOperation(claim=live.claim, snapshot=live.snapshot, origin=SourceSyncOrigin.MANUAL)
    before = _source_counts(source_harness)
    lock_connection = source_harness.bootstrap_engine.connect()
    transaction = lock_connection.begin()
    try:
        lock_connection.execute(
            text(f"SELECT id FROM {_SCHEMA}.source_sync_operations WHERE id = :id FOR UPDATE"),
            {"id": live.acquire.operation_id},
        ).one()
        with pytest.raises(SourceSyncRepositoryFailure) as excinfo:
            _record_terminal(source_harness, live, _no_change_candidate(), repository=source_harness.second_repository)
        _assert_repository_error(excinfo.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)
        with pytest.raises(SourceSyncRepositoryFailure) as acquire_error:
            source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(claimed))
        _assert_repository_error(acquire_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)

        original_rollback = Session.rollback

        def rollback_then_fail(session: Session) -> None:
            """先真实收敛事务，再注入 rollback SQLAlchemy failure。

            Args:
                session: 先调用原始 rollback、再关闭并注入失败的当前 Session。

            Returns:
                无。

            Raises:
                SQLAlchemyError: 原始 rollback 与 close 完成后无条件注入 cleanup 失败。
            """

            original_rollback(session)
            session.close()
            raise SQLAlchemyError("rollback failure")

        with monkeypatch.context() as patch:
            patch.setattr(Session, "rollback", rollback_then_fail)
            with pytest.raises(SourceSyncRepositoryFailure) as rollback_failure:
                source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(claimed))
        _assert_repository_error(rollback_failure.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)

        def rollback_then_typed_lock(session: Session) -> None:
            """先真实收敛事务，再让 rollback 自身抛 exact 55P03。

            Args:
                session: 先调用原始 rollback、再关闭并注入锁失败的当前 Session。

            Returns:
                无。

            Raises:
                psycopg.errors.LockNotAvailable: 原始 rollback 与 close 完成后无条件注入 55P03。
            """

            original_rollback(session)
            session.close()
            raise psycopg.errors.LockNotAvailable("rollback lock")

        with monkeypatch.context() as patch:
            patch.setattr(Session, "rollback", rollback_then_typed_lock)
            with pytest.raises(SourceSyncRepositoryFailure) as rollback_lock:
                source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(claimed))
        _assert_repository_error(rollback_lock.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)

        def factory_typed_lock(_factory: sessionmaker[Session]) -> Session:
            """在 Session 创建前注入无需 rollback 的 exact 55P03。

            Args:
                _factory: 被 repository 调用的 Session factory；本 failpoint 不读取。

            Returns:
                无正常返回；每次调用都抛出锁失败。

            Raises:
                psycopg.errors.LockNotAvailable: Session 创建前无条件注入 55P03。
            """

            raise psycopg.errors.LockNotAvailable("factory lock")

        with monkeypatch.context() as patch:
            patch.setattr(sessionmaker, "__call__", factory_typed_lock)
            with pytest.raises(SourceSyncRepositoryFailure) as no_rollback_lock:
                source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(claimed))
        _assert_repository_error(no_rollback_lock.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)
        assert _source_counts(source_harness) == before
    finally:
        transaction.rollback()
        lock_connection.close()


def test_pg_clock_backward_takeover_advances_acquired_at_one_microsecond_and_terminal_uses_later_health_head_for_all_times(
    source_harness: _Harness,
) -> None:
    """Backward takeover 与 terminal 全时间严格晚于 operation/head durable truth。

    Args:
        source_harness: 提供 takeover、health head 与可固定 PG clock 的隔离数据库 fixture。

    Returns:
        无。

    Raises:
        AssertionError: Monotonic timestamp、generation 或 terminal/health 时间不符时由测试抛出。
    """

    live = _new_live_operation(source_harness, key="clock-forward")
    with source_harness.bootstrap_engine.connect() as connection:
        acquired_at = connection.execute(
            text(f"SELECT acquired_at FROM {_SCHEMA}.source_sync_operations WHERE id = :id"),
            {"id": live.acquire.operation_id},
        ).scalar_one()
        connection.rollback()
    assert isinstance(acquired_at, datetime)
    acquired_at = acquired_at.astimezone(timezone.utc)
    fixed_clock = acquired_at - timedelta(minutes=5)

    def replace_clock(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> CursorReplacement:
        """把唯一 PG clock 替换为早于 operation audit truth 的固定时刻。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；仅识别 takeover 的单时钟查询。
            parameters: 原 SQL 的绑定参数映射，替换时保持不变。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            原 SQL 或早于 operation audit truth 的固定时钟 SQL，以及原绑定参数映射。

        Raises:
            无。
        """

        if "clock_timestamp()" in statement.lower():
            return f"SELECT TIMESTAMPTZ '{fixed_clock.isoformat()}'", parameters
        return statement, parameters

    claimed = _ClaimedOperation(claim=live.claim, snapshot=live.snapshot, origin=SourceSyncOrigin.MANUAL)
    retry = _retry_claim(source_harness, claimed, worker="clock-backward-takeover")
    event.listen(source_harness.secondary_engine, "before_cursor_execute", replace_clock, retval=True)
    try:
        takeover_acquire = source_harness.second_repository.acquire_operation(
            source_harness.scope,
            _acquire_request(retry),
        )
    finally:
        event.remove(source_harness.secondary_engine, "before_cursor_execute", replace_clock)
    assert takeover_acquire.generation == 2
    with source_harness.bootstrap_engine.connect() as connection:
        takeover_acquired_at = connection.execute(
            text(f"SELECT acquired_at FROM {_SCHEMA}.source_sync_operations WHERE id = :id"),
            {"id": live.acquire.operation_id},
        ).scalar_one()
        connection.rollback()
    assert isinstance(takeover_acquired_at, datetime)
    takeover_acquired_at = takeover_acquired_at.astimezone(timezone.utc)
    assert takeover_acquired_at == acquired_at + timedelta(microseconds=1)

    head_live = _new_live_operation(source_harness, key="clock-later-head")
    head = _record_terminal(source_harness, head_live, _failure_candidate())
    assert head.health_after is not None and head.health_after.observed_at is not None
    takeover = _LiveOperation(claim=retry.claim, snapshot=retry.snapshot, acquire=takeover_acquire)
    event.listen(source_harness.secondary_engine, "before_cursor_execute", replace_clock, retval=True)
    try:
        decision = _record_terminal(
            source_harness,
            takeover,
            _no_change_candidate(),
            repository=source_harness.second_repository,
        )
    finally:
        event.remove(source_harness.secondary_engine, "before_cursor_execute", replace_clock)
    assert decision.receipt is not None and decision.health_after is not None and decision.health_snapshot is not None
    expected_finished = head.health_after.observed_at
    assert decision.receipt.started_at == takeover_acquired_at
    assert decision.receipt.finished_at == expected_finished
    assert decision.health_after.observed_at == expected_finished
    assert decision.health_snapshot.observed_at == expected_finished
    assert decision.health_snapshot.created_at == expected_finished


def test_operator_reenable_clock_backward_advances_head_and_snapshot_one_microsecond(
    source_harness: _Harness,
) -> None:
    """Operator re-enable 在 future head 后精确前进一微秒。

    Args:
        source_harness: 提供 disabled health head、operator re-enable 与可固定 PG clock 的 fixture。

    Returns:
        无。

    Raises:
        AssertionError: Re-enable head/snapshot 未精确推进一微秒时由测试抛出。
    """

    first = _new_live_operation(source_harness, key="disable-1")
    second = _new_live_operation(source_harness, key="disable-2")
    third = _new_live_operation(source_harness, key="disable-3")
    _record_terminal(source_harness, first, _failure_candidate())
    _record_terminal(source_harness, second, _failure_candidate())
    disabled = _record_terminal(source_harness, third, _failure_candidate())
    assert disabled.health_after is not None and disabled.health_after.status is SourceHealthStatus.DISABLED
    assert disabled.health_after.observed_at is not None
    fixed_clock = disabled.health_after.observed_at - timedelta(minutes=5)

    def replace_clock(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> CursorReplacement:
        """把 re-enable 的唯一 PG clock 固定到 locked head 之前。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；仅识别 re-enable 的单时钟查询。
            parameters: 原 SQL 的绑定参数映射，替换时保持不变。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            原 SQL 或 locked head 之前的固定时钟 SQL，以及原绑定参数映射。

        Raises:
            无。
        """

        if "clock_timestamp()" in statement.lower():
            return f"SELECT TIMESTAMPTZ '{fixed_clock.isoformat()}'", parameters
        return statement, parameters

    event.listen(source_harness.primary_engine, "before_cursor_execute", replace_clock, retval=True)
    try:
        enabled = source_harness.repository.reenable_health(
            source_harness.scope,
            SourceHealthReenableRequest(
                subscription_id=source_harness.subscription_id,
                expected_health_version=disabled.health_after.version,
            ),
        )
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", replace_clock)
    assert enabled.observed_at == disabled.health_after.observed_at + timedelta(microseconds=1)
    page = source_harness.repository.list_health_snapshots(
        source_harness.scope,
        source_harness.subscription_id,
        None,
        limit=1,
    )
    assert len(page.snapshots) == 1
    assert page.snapshots[0].health_state_version == enabled.version
    assert page.snapshots[0].observed_at == enabled.observed_at
    assert page.snapshots[0].created_at == enabled.observed_at


def test_stale_attempt_cannot_commit_after_new_current_attempt_takes_over_generation(source_harness: _Harness) -> None:
    """Expected generation/attempt fence 阻止旧 producer terminalize。

    Args:
        source_harness: 提供旧/新 attempts 与 generation takeover 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Stale attempt 未被拒绝或 operation/source facts 发生漂移时由测试抛出。
    """

    live = _new_live_operation(source_harness, key="stale-attempt")
    busy = source_harness.repository.acquire_operation(
        source_harness.scope,
        SourceOperationAcquireRequest(
            origin=SourceSyncOrigin.MANUAL,
            definition_id=live.claim.definition_id,
            descriptor=live.claim.descriptor,
            job_id=live.claim.job_id,
            attempt_id=live.claim.attempt_id,
            attempt_number=live.claim.attempt_number,
            payload_sha256=live.claim.payload.sha256,
            candidate_execution_snapshot=live.snapshot,
        ),
    )
    assert busy.action is SourceOperationAcquireAction.BUSY
    takeover = _take_over_operation(source_harness, live)
    assert takeover.acquire.generation == 2
    assert takeover.acquire.operation_id == live.acquire.operation_id
    decision = _record_terminal(source_harness, live, _no_change_candidate())
    assert decision.action is SourceTerminalRecordAction.LEASE_LOST
    assert _source_counts(source_harness)[1:] == (0, 0, 0, 0)
    recorded = _record_terminal(
        source_harness,
        takeover,
        _no_change_candidate(),
        repository=source_harness.second_repository,
    )
    assert recorded.action is SourceTerminalRecordAction.RECORDED


def test_scheduled_binding_missing_or_non_executable_before_or_inside_acquire_is_typed_invalid_with_zero_operation(
    source_harness: _Harness,
) -> None:
    """Scheduled acquire 的三种 missing/non-executable binding 均零 operation。

    Args:
        source_harness: 提供 scheduled Job、binding tamper 与 Source acquire 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Typed rejection 或零 operation/source rows 矩阵不符时由测试抛出。
    """

    assert source_harness.repository.get_health(
        source_harness.scope,
        source_harness.subscription_id,
    ).version == 0
    missing = SourceSubscriptionId(str(_stable_uuid("missing-subscription")))
    with pytest.raises(SourceSyncRequestRejected) as excinfo:
        source_harness.repository.get_executable_binding(source_harness.scope, missing)
    assert excinfo.value.code is SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND
    with pytest.raises(SourceSyncRequestRejected) as health_error:
        source_harness.repository.get_health(source_harness.scope, missing)
    assert health_error.value.code is SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND
    with pytest.raises(SourceSyncRequestRejected) as page_error:
        source_harness.repository.list_health_snapshots(source_harness.scope, missing, None, limit=1)
    assert page_error.value.code is SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND
    with pytest.raises(SourceSyncRequestRejected) as reenable_error:
        source_harness.repository.reenable_health(
            source_harness.scope,
            SourceHealthReenableRequest(subscription_id=missing, expected_health_version=1),
    )
    assert reenable_error.value.code is SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND
    assert _source_counts(source_harness) == (0, 0, 0, 0, 0)

    binding = source_harness.repository.get_executable_binding(
        source_harness.scope,
        source_harness.subscription_id,
    )
    missing_available_at = _pg_clock(source_harness) - timedelta(minutes=1)
    missing_payload = build_scheduled_source_sync_payload_document(
        ScheduledSourceSyncPayload(
            subscription_id=missing,
            source_definition_id=source_harness.source_definition_id,
            expected_subscription_version=binding.subscription_version,
            schedule_key="source-pg-schedule:missing-before-acquire",
            source_request_fingerprint="8" * 64,
        )
    )
    missing_enqueue = source_harness.jobs.enqueue(
        source_harness.scope,
        JobEnqueueRequest(
            descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
            idempotency_key="source-pg-scheduled:missing-before-acquire",
            payload=missing_payload,
            available_at=missing_available_at,
            deadline_at=missing_available_at + timedelta(hours=2),
        ),
    )
    missing_claim = source_harness.jobs.claim(
        source_harness.scope,
        "scheduled-worker-missing-before-acquire",
    )
    assert missing_claim is not None and missing_claim.job_id == missing_enqueue.job_id
    with pytest.raises(SourceSyncRequestRejected) as missing_acquire:
        source_harness.repository.acquire_operation(
            source_harness.scope,
            SourceOperationAcquireRequest(
                origin=SourceSyncOrigin.SCHEDULED,
                definition_id=missing_claim.definition_id,
                descriptor=missing_claim.descriptor,
                job_id=missing_claim.job_id,
                attempt_id=missing_claim.attempt_id,
                attempt_number=missing_claim.attempt_number,
                payload_sha256=missing_claim.payload.sha256,
                candidate_execution_snapshot=None,
            ),
        )
    assert missing_acquire.value.code is SourceSyncRequestRejectionCode.SUBSCRIPTION_NOT_FOUND
    assert _source_counts(source_harness) == (0, 0, 0, 0, 0)

    target_missing = _new_claimed_scheduled_operation(
        source_harness,
        key="scheduled-target-missing",
    )
    _bootstrap_execute(
        source_harness,
        f"UPDATE {_SCHEMA}.source_subscriptions SET security_id = NULL "
        "WHERE id = :subscription_id",
        {"subscription_id": UUID(source_harness.subscription_id.value)},
    )
    try:
        with pytest.raises(SourceSyncRequestRejected) as target_missing_error:
            source_harness.repository.acquire_operation(
                source_harness.scope,
                _acquire_request(target_missing),
            )
    finally:
        _bootstrap_execute(
            source_harness,
            f"UPDATE {_SCHEMA}.source_subscriptions SET security_id = :security_id "
            "WHERE id = :subscription_id",
            {
                "security_id": UUID(source_harness.security_id.value),
                "subscription_id": UUID(source_harness.subscription_id.value),
            },
        )
    assert target_missing_error.value.code is SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE
    assert _source_counts(source_harness) == (0, 0, 0, 0, 0)

    security_missing = _new_claimed_scheduled_operation(
        source_harness,
        key="scheduled-security-missing",
    )
    missing_security_id = _stable_uuid("scheduled-missing-security-row")
    _set_constraint_triggers_enabled(
        source_harness,
        table_name="source_subscriptions",
        constraint_name="fk_source_subscriptions_security_id_securities",
        enabled=False,
    )
    try:
        _bootstrap_execute(
            source_harness,
            f"UPDATE {_SCHEMA}.source_subscriptions SET security_id = :security_id "
            "WHERE id = :subscription_id",
            {
                "security_id": missing_security_id,
                "subscription_id": UUID(source_harness.subscription_id.value),
            },
        )
        with pytest.raises(SourceSyncRequestRejected) as security_missing_error:
            source_harness.repository.acquire_operation(
                source_harness.scope,
                _acquire_request(security_missing),
            )
    finally:
        try:
            _bootstrap_execute(
                source_harness,
                f"UPDATE {_SCHEMA}.source_subscriptions SET security_id = :security_id "
                "WHERE id = :subscription_id",
                {
                    "security_id": UUID(source_harness.security_id.value),
                    "subscription_id": UUID(source_harness.subscription_id.value),
                },
            )
        finally:
            _set_constraint_triggers_enabled(
                source_harness,
                table_name="source_subscriptions",
                constraint_name="fk_source_subscriptions_security_id_securities",
                enabled=True,
            )
    assert security_missing_error.value.code is SourceSyncRequestRejectionCode.BINDING_NON_EXECUTABLE
    assert _source_counts(source_harness) == (0, 0, 0, 0, 0)

    scheduled = _new_scheduled_live_operation(source_harness, key="scheduled-positive")
    decision = _record_terminal(source_harness, scheduled, _no_change_candidate())
    assert decision.action is SourceTerminalRecordAction.RECORDED

    drift_claimed = _new_claimed_scheduled_operation(source_harness, key="scheduled-provenance")
    operation_id, _shifted, shifted_sha = _insert_drift_operation_as_app(
        source_harness,
        drift_claimed,
        label="scheduled",
    )
    retry = _retry_claim(source_harness, drift_claimed, worker="scheduled-provenance-retry")
    with pytest.raises(SourceSyncRepositoryFailure) as drift_error:
        source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(retry))
    assert drift_error.value.code is SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
    with source_harness.bootstrap_engine.connect() as connection:
        persisted = connection.execute(
            text(
                f"SELECT generation, owner_attempt_id, execution_snapshot_sha256 "
                f"FROM {_SCHEMA}.source_sync_operations WHERE id = :id"
            ),
            {"id": operation_id},
        ).one()
        connection.rollback()
    assert tuple(persisted) == (1, drift_claimed.claim.attempt_id, shifted_sha)
    assert _source_counts(source_harness) == (2, 1, 1, 1, 0)


def test_terminal_replay_never_mutates_result_receipt_or_adds_replay_marker(source_harness: _Harness) -> None:
    """Replay、legacy、v1 与所有 corrupt receipt shape 保持 immutable。

    Args:
        source_harness: 提供 receipt/run tamper、真实 replay 与第二 tenant 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Legacy/v1/lineage/cross-tenant 或零 mutation 断言失败时由测试抛出。
    """

    missing_run_id = _stable_uuid("missing-source-run")
    assert source_harness.repository.get_source_receipt(source_harness.scope, missing_run_id) is None
    with pytest.raises(SourceSyncRequestRejected) as invalid_run:
        source_harness.repository.get_source_receipt(source_harness.scope, UUID(int=0))
    assert invalid_run.value.code is SourceSyncRequestRejectionCode.INVALID_INPUT
    legacy_run_id = _stable_uuid("legacy-source-run")
    legacy_at = _pg_clock(source_harness)
    _set_named_trigger_enabled(
        source_harness,
        table_name="source_sync_runs",
        trigger_name="source_sync_runs_require_v1_insert_trigger",
        enabled=False,
    )
    try:
        _bootstrap_execute(
            source_harness,
            f"INSERT INTO {_SCHEMA}.source_sync_runs "
            "(id, tenant_id, subscription_id, idempotency_key, status, started_at, "
            "records_discovered, records_ingested) VALUES "
            "(:id, :tenant_id, :subscription_id, :key, 'planned', :started_at, 0, 0)",
            {
                "id": legacy_run_id,
                "tenant_id": UUID(_TENANT_ID.value),
                "subscription_id": UUID(source_harness.subscription_id.value),
                "key": "legacy-item5",
                "started_at": legacy_at,
            },
        )
    finally:
        _set_named_trigger_enabled(
            source_harness,
            table_name="source_sync_runs",
            trigger_name="source_sync_runs_require_v1_insert_trigger",
            enabled=True,
        )
    assert source_harness.repository.get_source_receipt(source_harness.scope, legacy_run_id) is None
    live = _new_live_operation(source_harness, key="replay")
    terminal = _record_terminal(source_harness, live, _no_change_candidate())
    assert terminal.receipt is not None and terminal.result is not None
    replay = source_harness.repository.acquire_operation(
        source_harness.scope,
        SourceOperationAcquireRequest(
            origin=SourceSyncOrigin.MANUAL,
            definition_id=live.claim.definition_id,
            descriptor=live.claim.descriptor,
            job_id=live.claim.job_id,
            attempt_id=live.claim.attempt_id,
            attempt_number=live.claim.attempt_number,
            payload_sha256=live.claim.payload.sha256,
            candidate_execution_snapshot=live.snapshot,
        ),
    )
    assert replay.action is SourceOperationAcquireAction.TERMINAL_REPLAY
    assert replay.terminal_receipt == terminal.receipt
    assert replay.terminal_result == terminal.result
    assert source_harness.repository.get_source_receipt(source_harness.scope, terminal.receipt.source_sync_run_id) == terminal.receipt
    assert _source_counts(source_harness) == (1, 2, 1, 1, 0)
    run_id = terminal.receipt.source_sync_run_id
    original_receipt_json = terminal.receipt.receipt.canonical_bytes.decode("utf-8")
    original_receipt_sha256 = terminal.receipt.receipt.sha256
    original_result_json = terminal.result.result.canonical_bytes.decode("utf-8")
    original_result_sha256 = terminal.result.result.sha256
    expected_counts = _source_counts(source_harness)
    expected_operation = _operation_identity(source_harness, live.acquire.operation_id)
    expected_result = _source_run_result_fingerprint(source_harness, run_id)
    assert "replay" not in expected_result[0].lower()

    core_presence_definition = _drop_source_run_check(
        source_harness,
        "ck_source_sync_runs_v1_core_presence",
    )
    try:
        _set_named_trigger_enabled(
            source_harness,
            table_name="source_sync_runs",
            trigger_name="guard_source_sync_runs_append_only_trigger",
            enabled=False,
        )
        _bootstrap_execute(
            source_harness,
            f"UPDATE {_SCHEMA}.source_sync_runs SET receipt_sha256 = NULL WHERE id = :id",
            {"id": run_id},
        )
        _assert_receipt_invariant_is_read_only(
            source_harness,
            source_sync_run_id=run_id,
            operation_id=live.acquire.operation_id,
            expected_counts=expected_counts,
            expected_operation=expected_operation,
            expected_result=expected_result,
        )
    finally:
        try:
            try:
                _bootstrap_execute(
                    source_harness,
                    f"UPDATE {_SCHEMA}.source_sync_runs SET receipt_sha256 = :sha WHERE id = :id",
                    {"sha": original_receipt_sha256, "id": run_id},
                )
            finally:
                _set_named_trigger_enabled(
                    source_harness,
                    table_name="source_sync_runs",
                    trigger_name="guard_source_sync_runs_append_only_trigger",
                    enabled=True,
                )
        finally:
            _restore_source_run_check(
                source_harness,
                constraint_name="ck_source_sync_runs_v1_core_presence",
                definition=core_presence_definition,
            )

    outcome_definition = _drop_source_run_check(
        source_harness,
        "ck_source_sync_runs_v1_outcome_shape",
    )
    try:
        _set_named_trigger_enabled(
            source_harness,
            table_name="source_sync_runs",
            trigger_name="guard_source_sync_runs_append_only_trigger",
            enabled=False,
        )
        _bootstrap_execute(
            source_harness,
            f"UPDATE {_SCHEMA}.source_sync_runs SET retry_recommended = true WHERE id = :id",
            {"id": run_id},
        )
        _assert_receipt_invariant_is_read_only(
            source_harness,
            source_sync_run_id=run_id,
            operation_id=live.acquire.operation_id,
            expected_counts=expected_counts,
            expected_operation=expected_operation,
            expected_result=expected_result,
        )
    finally:
        try:
            try:
                _bootstrap_execute(
                    source_harness,
                    f"UPDATE {_SCHEMA}.source_sync_runs SET retry_recommended = false WHERE id = :id",
                    {"id": run_id},
                )
            finally:
                _set_named_trigger_enabled(
                    source_harness,
                    table_name="source_sync_runs",
                    trigger_name="guard_source_sync_runs_append_only_trigger",
                    enabled=True,
                )
        finally:
            _restore_source_run_check(
                source_harness,
                constraint_name="ck_source_sync_runs_v1_outcome_shape",
                definition=outcome_definition,
            )

    assert original_receipt_json.endswith("}")
    canonical_drift_json = original_receipt_json[:-1] + ',"zz_unexpected":"drift"}'
    canonical_drift_sha256 = hashlib.sha256(canonical_drift_json.encode("utf-8")).hexdigest()
    corrupt_documents = (
        (canonical_drift_json, canonical_drift_sha256, original_result_json, original_result_sha256),
        (original_receipt_json, "f" * 64, original_result_json, original_result_sha256),
    )
    lineage_definitions = (
        (
            "source_sync_run_id",
            str(terminal.receipt.source_sync_run_id),
            str(_stable_uuid("receipt-cross-lineage-run")),
            "source_sync_run_id",
        ),
        (
            "subscription_id",
            terminal.receipt.subscription_id.value,
            str(_stable_uuid("receipt-cross-lineage-subscription")),
            None,
        ),
        (
            "job_id",
            str(terminal.receipt.job_id),
            str(_stable_uuid("receipt-cross-lineage-job")),
            None,
        ),
        (
            "producer_attempt_id",
            str(terminal.receipt.producer_attempt_id),
            str(_stable_uuid("receipt-cross-lineage-attempt")),
            "producer_attempt_id",
        ),
    )
    lineage_cases: list[tuple[str, str, str, str, str]] = []
    result_receipt_sha_fragment = f'"source_receipt_sha256":"{original_receipt_sha256}"'
    assert original_result_json.count(result_receipt_sha_fragment) == 1
    for receipt_field, original_value, drift_value, result_identity_field in lineage_definitions:
        receipt_fragment = f'"{receipt_field}":"{original_value}"'
        assert original_receipt_json.count(receipt_fragment) == 1
        drift_receipt_json = original_receipt_json.replace(
            receipt_fragment,
            f'"{receipt_field}":"{drift_value}"',
        )
        drift_receipt_sha256 = hashlib.sha256(drift_receipt_json.encode("utf-8")).hexdigest()
        drift_result_json = original_result_json.replace(
            result_receipt_sha_fragment,
            f'"source_receipt_sha256":"{drift_receipt_sha256}"',
        )
        if result_identity_field is not None:
            result_identity_fragment = f'"{result_identity_field}":"{original_value}"'
            assert drift_result_json.count(result_identity_fragment) == 1
            drift_result_json = drift_result_json.replace(
                result_identity_fragment,
                f'"{result_identity_field}":"{drift_value}"',
            )
        drift_result_sha256 = hashlib.sha256(drift_result_json.encode("utf-8")).hexdigest()
        lineage_cases.append(
            (
                receipt_field,
                drift_receipt_json,
                drift_receipt_sha256,
                drift_result_json,
                drift_result_sha256,
            )
        )
    _set_named_trigger_enabled(
        source_harness,
        table_name="source_sync_runs",
        trigger_name="guard_source_sync_runs_append_only_trigger",
        enabled=False,
    )
    try:
        for receipt_json, receipt_sha256, result_json, result_sha256 in corrupt_documents:
            _bootstrap_execute(
                source_harness,
                f"UPDATE {_SCHEMA}.source_sync_runs SET receipt_json = CAST(:receipt_json AS jsonb), "
                "receipt_sha256 = :receipt_sha256, result_json = CAST(:result_json AS jsonb), "
                "result_sha256 = :result_sha256 WHERE id = :id",
                {
                    "receipt_json": receipt_json,
                    "receipt_sha256": receipt_sha256,
                    "result_json": result_json,
                    "result_sha256": result_sha256,
                    "id": run_id,
                },
            )
            tampered_result = _source_run_result_fingerprint(source_harness, run_id)
            assert tampered_result[1] == result_sha256
            _assert_receipt_invariant_is_read_only(
                source_harness,
                source_sync_run_id=run_id,
                operation_id=live.acquire.operation_id,
                expected_counts=expected_counts,
                expected_operation=expected_operation,
                expected_result=tampered_result,
            )
        for receipt_field, receipt_json, receipt_sha256, result_json, result_sha256 in lineage_cases:
            _bootstrap_execute(
                source_harness,
                f"UPDATE {_SCHEMA}.source_sync_runs SET receipt_json = CAST(:receipt_json AS jsonb), "
                "receipt_sha256 = :receipt_sha256, result_json = CAST(:result_json AS jsonb), "
                "result_sha256 = :result_sha256 WHERE id = :id",
                {
                    "receipt_json": receipt_json,
                    "receipt_sha256": receipt_sha256,
                    "result_json": result_json,
                    "result_sha256": result_sha256,
                    "id": run_id,
                },
            )
            with source_harness.bootstrap_engine.connect() as connection:
                tampered_row: DatabaseRow = connection.execute(
                    text(f"SELECT * FROM {_SCHEMA}.source_sync_runs WHERE id = :id"),
                    {"id": run_id},
                ).one()
                connection.rollback()
            with pytest.raises(ValueError, match="^source run outer lineage drift$"):
                postgres_sources_module._rebuild_run_artifacts(
                    tampered_row,
                    tenant_id=_TENANT_ID,
                )
            tampered_result = _source_run_result_fingerprint(source_harness, run_id)
            assert tampered_result[1] == result_sha256, receipt_field
            assert (
                _bootstrap_scalar(
                    source_harness,
                    f"SELECT count(*) FROM {_SCHEMA}.source_sync_runs WHERE id = :id "
                    "AND receipt_json = CAST(:receipt_json AS jsonb) AND receipt_sha256 = :receipt_sha256",
                    {
                        "id": run_id,
                        "receipt_json": receipt_json,
                        "receipt_sha256": receipt_sha256,
                    },
                )
                == 1
            ), receipt_field
            _assert_receipt_invariant_is_read_only(
                source_harness,
                source_sync_run_id=run_id,
                operation_id=live.acquire.operation_id,
                expected_counts=expected_counts,
                expected_operation=expected_operation,
                expected_result=tampered_result,
            )
    finally:
        try:
            _bootstrap_execute(
                source_harness,
                f"UPDATE {_SCHEMA}.source_sync_runs SET receipt_json = CAST(:receipt_json AS jsonb), "
                "receipt_sha256 = :receipt_sha256, result_json = CAST(:result_json AS jsonb), "
                "result_sha256 = :result_sha256 WHERE id = :id",
                {
                    "receipt_json": original_receipt_json,
                    "receipt_sha256": original_receipt_sha256,
                    "result_json": original_result_json,
                    "result_sha256": original_result_sha256,
                    "id": run_id,
                },
            )
        finally:
            _set_named_trigger_enabled(
                source_harness,
                table_name="source_sync_runs",
                trigger_name="guard_source_sync_runs_append_only_trigger",
                enabled=True,
            )
    assert source_harness.repository.get_source_receipt(source_harness.scope, run_id) == terminal.receipt
    assert _source_counts(source_harness) == expected_counts
    assert _operation_identity(source_harness, live.acquire.operation_id) == expected_operation
    assert _source_run_result_fingerprint(source_harness, run_id) == expected_result

    other_tenant_id = TenantId(str(_stable_uuid("receipt-other-tenant")))
    other_scope = Principal(tenant_id=other_tenant_id, user_id="receipt-other-owner").to_scope()
    other_subscription_id = SourceSubscriptionId(str(_stable_uuid("receipt-other-subscription")))
    _bootstrap_execute(
        source_harness,
        f"INSERT INTO {_SCHEMA}.organizations (id, slug, display_name, status, version) "
        "VALUES (:id, :slug, :display_name, 'active', 1)",
        {
            "id": UUID(other_tenant_id.value),
            "slug": "receipt-other-tenant",
            "display_name": "Receipt other tenant",
        },
    )
    other_identity = PostgresIdentityRepository(source_harness.secondary_factory)
    other_identity.create_source_subscription(
        other_scope,
        SourceSubscriptionCreateRequest(
            subscription_id=other_subscription_id,
            source_definition_id=source_harness.source_definition_id,
            company_id=None,
            security_id=source_harness.security_id,
            status=SubscriptionStatus.ENABLED,
            config=_CONFIG,
        ),
    )
    other_harness = replace(
        source_harness,
        repository=source_harness.second_repository,
        jobs=source_harness.second_jobs,
        identity=other_identity,
        scope=other_scope,
        subscription_id=other_subscription_id,
    )
    other_live = _new_live_operation(other_harness, key="receipt-other-tenant")
    other_terminal = _record_terminal(other_harness, other_live, _no_change_candidate())
    assert other_terminal.receipt is not None
    other_run_id = other_terminal.receipt.source_sync_run_id
    assert (
        _bootstrap_scalar(
            source_harness,
            f"SELECT count(*) FROM {_SCHEMA}.source_sync_runs WHERE tenant_id = :tenant_id AND id = :id",
            {"tenant_id": UUID(other_tenant_id.value), "id": other_run_id},
        )
        == 1
    )
    assert other_harness.repository.get_source_receipt(other_scope, other_run_id) == other_terminal.receipt
    assert source_harness.repository.get_source_receipt(source_harness.scope, other_run_id) is None


def test_repository_failure_before_source_commit_writes_zero_source_health_or_alert_rows(
    source_harness: _Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admission/post-admission 与 rollback 覆盖矩阵均零 terminal observation。

    Args:
        source_harness: 提供 admission、terminal、health/outbox transactions 的隔离 PG fixture。
        monkeypatch: 注入 factory、transaction、driver、commit 与 rollback failures 的 pytest fixture。

    Returns:
        无。

    Raises:
        AssertionError: Failure precedence、closed code 或零 durable mutation 矩阵不符时由测试抛出。
    """

    live = _new_live_operation(source_harness, key="rollback")
    before = _source_counts(source_harness)

    def fail_factory(_factory: sessionmaker[Session]) -> Session:
        """在 Session factory admission 阶段注入 ordinary database failure。

        Args:
            _factory: 被 repository 调用的 Session factory；本 failpoint 不读取。

        Returns:
            无正常返回；每次调用都抛出数据库失败。

        Raises:
            SQLAlchemyError: Session factory 被调用时无条件注入数据库失败。
        """

        raise SQLAlchemyError("factory failpoint")

    with monkeypatch.context() as patch:
        patch.setattr(sessionmaker, "__call__", fail_factory)
        with pytest.raises(SourceSyncRepositoryFailure) as factory_error:
            source_harness.second_repository.get_health(source_harness.scope, source_harness.subscription_id)
    _assert_repository_error(factory_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)

    def fail_begin(_session: Session) -> None:
        """在 transaction begin admission 阶段注入 ordinary database failure。

        Args:
            _session: 即将开启事务的 Session；本 failpoint 不读取。

        Returns:
            无。

        Raises:
            SQLAlchemyError: Transaction begin 被调用时无条件注入数据库失败。
        """

        raise SQLAlchemyError("begin failpoint")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "begin", fail_begin)
        with pytest.raises(SourceSyncRepositoryFailure) as begin_error:
            source_harness.second_repository.get_health(source_harness.scope, source_harness.subscription_id)
    _assert_repository_error(begin_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)

    source_harness.secondary_engine.dispose()
    secondary_pool = source_harness.secondary_engine.pool

    def fail_checkout(
        _dbapi_connection: psycopg.Connection[PostgresRow],
        _connection_record: ConnectionPoolEntry,
        _connection_proxy: PoolProxiedConnection,
    ) -> None:
        """在 connection checkout admission 阶段注入 ordinary database failure。

        Args:
            _dbapi_connection: 刚从连接池取出的 psycopg 连接；本 failpoint 不读取。
            _connection_record: 该连接的池记录；本 failpoint 不读取。
            _connection_proxy: 连接池代理；本 failpoint 不读取。

        Returns:
            无。

        Raises:
            SQLAlchemyError: Connection checkout 时无条件注入数据库失败。
        """

        raise SQLAlchemyError("checkout failpoint")

    event.listen(secondary_pool, "checkout", fail_checkout)
    try:
        with pytest.raises(SourceSyncRepositoryFailure) as checkout_error:
            source_harness.second_repository.get_health(source_harness.scope, source_harness.subscription_id)
    finally:
        event.remove(secondary_pool, "checkout", fail_checkout)
    _assert_repository_error(checkout_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)

    def fail_first_sql(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        _parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        """在 tenant admission 第一条 SQL 尚未成功前注入失败。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；命中 tenant ``set_config`` 时注入失败。
            _parameters: SQL 绑定参数，本回调不读取。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            无。

        Raises:
            SQLAlchemyError: 命中 tenant ``set_config`` SQL 时注入 admission 失败。
        """

        if "set_config" in statement.lower():
            raise SQLAlchemyError("admission failpoint")

    event.listen(source_harness.secondary_engine, "before_cursor_execute", fail_first_sql)
    try:
        with pytest.raises(SourceSyncRepositoryFailure) as admission_error:
            source_harness.second_repository.get_health(source_harness.scope, source_harness.subscription_id)
    finally:
        event.remove(source_harness.secondary_engine, "before_cursor_execute", fail_first_sql)
    _assert_repository_error(admission_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)

    def fail_read(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        _parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        """在 tenant SQL 成功后的 subscription read 注入 ordinary failure。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；命中 subscription 查询时注入失败。
            _parameters: SQL 绑定参数，本回调不读取。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            无。

        Raises:
            SQLAlchemyError: 命中 source subscription 查询时注入 read 失败。
        """

        if "from dayu_platform.source_subscriptions" in statement.lower():
            raise SQLAlchemyError("read failpoint")

    event.listen(source_harness.secondary_engine, "before_cursor_execute", fail_read)
    try:
        with pytest.raises(SourceSyncRepositoryFailure) as read_error:
            source_harness.second_repository.get_health(source_harness.scope, source_harness.subscription_id)
    finally:
        event.remove(source_harness.secondary_engine, "before_cursor_execute", fail_read)
    _assert_repository_error(read_error.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)

    def fail_run_insert(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        _parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        """在 source run insert 前注入 typed SQLAlchemy failure。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；命中 source run INSERT 时注入失败。
            _parameters: SQL 绑定参数，本回调不读取。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            无。

        Raises:
            SQLAlchemyError: 命中 source sync run INSERT 时注入 terminal write 失败。
        """

        if "insert into dayu_platform.source_sync_runs" in statement.lower():
            raise SQLAlchemyError("test failpoint")

    event.listen(source_harness.primary_engine, "before_cursor_execute", fail_run_insert)
    try:
        with pytest.raises(SourceSyncRepositoryFailure) as terminal_error:
            _record_terminal(source_harness, live, _no_change_candidate())
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", fail_run_insert)
    _assert_repository_error(terminal_error.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)

    original_commit = Session.commit

    def fail_flush(_session: Session) -> None:
        """在 explicit commit wrapper 的 flush 阶段注入 ordinary failure。

        Args:
            _session: 即将 flush 的 Session；本 failpoint 不读取。

        Returns:
            无。

        Raises:
            SQLAlchemyError: Session flush 被调用时无条件注入数据库失败。
        """

        raise SQLAlchemyError("flush failpoint")

    def commit_via_flush(session: Session) -> None:
        """让 Core-only read transaction 明确经过 ORM flush phase。

        Args:
            session: 先 flush、再由原始 commit 提交的当前 Session。

        Returns:
            无。

        Raises:
            SQLAlchemyError: flush 或原始 commit 失败时向调用者传播。
        """

        session.flush()
        original_commit(session)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "flush", fail_flush)
        patch.setattr(Session, "commit", commit_via_flush)
        with pytest.raises(SourceSyncRepositoryFailure) as flush_error:
            source_harness.second_repository.get_health(source_harness.scope, source_harness.subscription_id)
    _assert_repository_error(flush_error.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)

    def fail_commit(_session: Session) -> None:
        """在 first-SQL 成功后的 commit 阶段注入 ordinary failure。

        Args:
            _session: 即将 commit 的 Session；本 failpoint 不读取。

        Returns:
            无。

        Raises:
            SQLAlchemyError: Session commit 被调用时无条件注入数据库失败。
        """

        raise SQLAlchemyError("commit failpoint")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(SourceSyncRepositoryFailure) as commit_error:
            source_harness.second_repository.get_health(source_harness.scope, source_harness.subscription_id)
    _assert_repository_error(commit_error.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)

    original_rollback = Session.rollback

    def rollback_then_fail(session: Session) -> None:
        """先真实 rollback/close，再注入最高优先级 cleanup failure。

        Args:
            session: 先调用原始 rollback、再关闭并注入 cleanup 失败的当前 Session。

        Returns:
            无。

        Raises:
            SQLAlchemyError: 原始 rollback 与 close 完成后无条件注入 cleanup 失败。
        """

        original_rollback(session)
        session.close()
        raise SQLAlchemyError("rollback override")

    lock_connection = source_harness.bootstrap_engine.connect()
    lock_transaction = lock_connection.begin()
    try:
        lock_connection.execute(
            text(f"SELECT id FROM {_SCHEMA}.source_sync_operations WHERE id = :id FOR UPDATE"),
            {"id": live.acquire.operation_id},
        ).one()
        with monkeypatch.context() as patch:
            patch.setattr(Session, "rollback", rollback_then_fail)
            with pytest.raises(SourceSyncRepositoryFailure) as lock_override:
                _record_terminal(
                    source_harness,
                    live,
                    _no_change_candidate(),
                    repository=source_harness.second_repository,
                )
        _assert_repository_error(lock_override.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)
    finally:
        lock_transaction.rollback()
        lock_connection.close()

    missing = SourceSubscriptionId(str(_stable_uuid("rollback-missing-subscription")))
    with monkeypatch.context() as patch:
        patch.setattr(Session, "rollback", rollback_then_fail)
        with pytest.raises(SourceSyncRepositoryFailure) as request_override:
            source_harness.second_repository.get_health(source_harness.scope, missing)
    _assert_repository_error(request_override.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)

    original_rv_uuid = postgres_sources_module._rv_uuid

    def fail_uuid_rebuild(_row: DatabaseRow, _key: str) -> UUID:
        """在 successful SQL 后注入 persisted UUID reconstruction failure。

        Args:
            _row: 已读取的 durable 数据库行；本 failpoint 不重建它。
            _key: 待重建的 UUID 列名；本 failpoint 不读取。

        Returns:
            无正常返回；每次重建都抛出值错误。

        Raises:
            ValueError: Durable UUID 重建被调用时无条件注入 persisted-value 失败。
        """

        raise ValueError("persisted rebuild failpoint")

    with monkeypatch.context() as patch:
        patch.setattr(postgres_sources_module, "_rv_uuid", fail_uuid_rebuild)
        with pytest.raises(SourceSyncRepositoryFailure) as persisted_original:
            source_harness.second_repository.get_health(
                source_harness.scope,
                source_harness.subscription_id,
            )
    _assert_repository_error(persisted_original.value, SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    with monkeypatch.context() as patch:
        patch.setattr(postgres_sources_module, "_rv_uuid", fail_uuid_rebuild)
        patch.setattr(Session, "rollback", rollback_then_fail)
        with pytest.raises(SourceSyncRepositoryFailure) as persisted_override:
            source_harness.second_repository.get_health(
                source_harness.scope,
                source_harness.subscription_id,
            )
    _assert_repository_error(persisted_override.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)
    assert postgres_sources_module._rv_uuid is original_rv_uuid

    source_harness.jobs.fail(
        source_harness.scope,
        live.claim.lease,
        JobFailure(safe_error_code=SafeJobErrorCode.SOURCE_INVALID, retryable=False),
    )
    claimed = _ClaimedOperation(claim=live.claim, snapshot=live.snapshot, origin=SourceSyncOrigin.MANUAL)
    with monkeypatch.context() as patch:
        patch.setattr(Session, "rollback", rollback_then_fail)
        with pytest.raises(SourceSyncRepositoryFailure) as execution_override:
            source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(claimed))
    _assert_repository_error(execution_override.value, SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)
    assert _source_counts(source_harness) == before


def test_forged_manual_tenant_version_window_payload_hash_or_security_company_lineage_is_invalid_with_zero_source_rows(
    source_harness: _Harness,
) -> None:
    """Caller payload hash 漂移在 Source mutation 前 closed reject。

    Args:
        source_harness: 提供 manual payload、identity tamper 与 Source acquire 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Typed rejection、lineage validation 或零 Source rows 断言失败时由测试抛出。
    """

    live = _new_live_operation(source_harness, key="forged")
    with pytest.raises(SourceSyncRequestRejected) as excinfo:
        source_harness.repository.acquire_operation(
            source_harness.scope,
            SourceOperationAcquireRequest(
                origin=SourceSyncOrigin.MANUAL,
                definition_id=live.claim.definition_id,
                descriptor=live.claim.descriptor,
                job_id=live.claim.job_id,
                attempt_id=live.claim.attempt_id,
                attempt_number=live.claim.attempt_number,
                payload_sha256="f" * 64,
                candidate_execution_snapshot=live.snapshot,
            ),
        )
    assert excinfo.value.code is SourceSyncRequestRejectionCode.PAYLOAD_HASH_MISMATCH
    assert _source_counts(source_harness)[1:] == (0, 0, 0, 0)

    drift_claimed = _new_claimed_manual_operation(source_harness, key="manual-provenance")
    operation_id, _shifted, shifted_sha = _insert_drift_operation_as_app(
        source_harness,
        drift_claimed,
        label="manual",
    )
    with pytest.raises(SourceSyncRepositoryFailure) as terminal_drift:
        source_harness.repository.record_terminal(
            source_harness.scope,
            SourceTerminalRecordRequest(
                operation_id=operation_id,
                job_id=drift_claimed.claim.job_id,
                attempt_id=drift_claimed.claim.attempt_id,
                attempt_number=drift_claimed.claim.attempt_number,
                expected_generation=1,
                expected_execution_snapshot_sha256=shifted_sha,
                candidate=_no_change_candidate(),
            ),
        )
    assert terminal_drift.value.code is SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
    retry = _retry_claim(source_harness, drift_claimed, worker="manual-provenance-retry")
    with pytest.raises(SourceSyncRepositoryFailure) as takeover_drift:
        source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(retry))
    assert takeover_drift.value.code is SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
    with source_harness.bootstrap_engine.connect() as connection:
        persisted = connection.execute(
            text(
                f"SELECT generation, owner_attempt_id, execution_snapshot_sha256 "
                f"FROM {_SCHEMA}.source_sync_operations WHERE id = :id"
            ),
            {"id": operation_id},
        ).one()
        connection.rollback()
    assert tuple(persisted) == (1, drift_claimed.claim.attempt_id, shifted_sha)
    assert _source_counts(source_harness) == (2, 0, 0, 0, 0)


def test_job_and_source_definition_uuid_values_are_never_cross_compared_and_cross_source_binding_is_rejected(
    source_harness: _Harness,
) -> None:
    """Acquire definition identity 只与 Job definition 比较。

    Args:
        source_harness: 提供 Job definition 与可构造 cross-source binding 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: UUID comparison 或 cross-source rejection 事实不符时由测试抛出。
    """

    live = _new_live_operation(source_harness, key="uuid-owner")
    assert live.claim.definition_id != UUID(source_harness.source_definition_id.value)
    assert live.acquire.action is SourceOperationAcquireAction.ACQUIRED
    _exercise_closed_reconstruction_branches(source_harness, live.snapshot)
    _bootstrap_execute(
        source_harness,
        f"UPDATE {_SCHEMA}.source_subscriptions SET version = version + 1 WHERE id = :subscription_id",
        {"subscription_id": UUID(source_harness.subscription_id.value)},
    )
    stale = _record_terminal(source_harness, live, _no_change_candidate())
    assert stale.action is SourceTerminalRecordAction.STALE_SUBSCRIPTION
    assert stale.receipt is not None and stale.receipt.outcome is SourceSyncOutcome.STALE_SUBSCRIPTION


def test_concurrent_source_definition_or_security_update_serializes_with_acquire_and_terminal_revalidation(
    source_harness: _Harness,
) -> None:
    """Definition/security/status 锁串行化两路径，disabled 不撤销既有 lease。

    Args:
        source_harness: 提供 definition/security 行锁与双 app repositories 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Serialization、reenable 或 terminal revalidation 断言失败时由测试抛出。
    """

    binding = source_harness.repository.get_executable_binding(source_harness.scope, source_harness.subscription_id)
    claimed = _new_claimed_manual_operation(source_harness, key="definition-acquire-lock")
    terminal_live = _new_live_operation(source_harness, key="definition-terminal-lock")
    assert claimed.claim.definition_id == terminal_live.claim.definition_id
    before = _source_counts(source_harness)

    lock_targets = (
        ("source_definitions", UUID(binding.source_definition_id.value)),
        ("securities", UUID(binding.security_id.value)),
    )
    for table_name, row_id in lock_targets:
        lock_connection = source_harness.bootstrap_engine.connect()
        transaction = lock_connection.begin()
        try:
            lock_connection.execute(
                text(f"SELECT id FROM {_SCHEMA}.{table_name} WHERE id = :id FOR UPDATE"),
                {"id": row_id},
            ).one()
            with pytest.raises(SourceSyncRepositoryFailure) as acquire_error:
                source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(claimed))
            _assert_repository_error(acquire_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)
            with pytest.raises(SourceSyncRepositoryFailure) as terminal_error:
                _record_terminal(
                    source_harness,
                    terminal_live,
                    _no_change_candidate(),
                    repository=source_harness.second_repository,
                )
            _assert_repository_error(terminal_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)
            assert _source_counts(source_harness) == before
        finally:
            transaction.rollback()
            lock_connection.close()

    status_connection = source_harness.bootstrap_engine.connect()
    status_transaction = status_connection.begin()
    status_connection.execute(
        text(
            f"UPDATE {_SCHEMA}.job_definitions SET status = 'disabled', "
            "updated_at = clock_timestamp(), version = version + 1 WHERE id = :id"
        ),
        {"id": claimed.claim.definition_id},
    )
    try:
        with pytest.raises(SourceSyncRepositoryFailure) as acquire_status_error:
            source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(claimed))
        _assert_repository_error(acquire_status_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)
        with pytest.raises(SourceSyncRepositoryFailure) as terminal_status_error:
            _record_terminal(
                source_harness,
                terminal_live,
                _no_change_candidate(),
                repository=source_harness.second_repository,
            )
        _assert_repository_error(terminal_status_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)
        assert _source_counts(source_harness) == before
        status_transaction.commit()
    finally:
        if status_transaction.is_active:
            status_transaction.rollback()
        status_connection.close()
    assert _bootstrap_scalar(
        source_harness,
        f"SELECT count(*) FROM {_SCHEMA}.job_definitions WHERE id = :id AND status = 'disabled'",
        {"id": claimed.claim.definition_id},
    ) == 1

    acquired = source_harness.second_repository.acquire_operation(source_harness.scope, _acquire_request(claimed))
    assert acquired.action is SourceOperationAcquireAction.ACQUIRED
    recorded = _record_terminal(
        source_harness,
        terminal_live,
        _no_change_candidate(),
        repository=source_harness.second_repository,
    )
    assert recorded.action is SourceTerminalRecordAction.RECORDED
    assert _source_counts(source_harness) == (2, 1, 1, 1, 0)


def test_repository_freshness_one_day_overrides_to_nonretryable_stale_data_preserves_verified_counts_and_advances_health(
    source_harness: _Harness,
) -> None:
    """超过一日 freshness 的 verified document 被 authoritative override。

    Args:
        source_harness: 提供 freshness config、verified evidence 与 health projection 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Stale override、verified counts 或 health advance 断言失败时由测试抛出。
    """

    live = _new_live_operation(source_harness, key="freshness")
    evidence = _evidence(live.snapshot, label="old", observed_date=live.snapshot.query_start_date)
    candidate = SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.SUCCEEDED,
        proposed_safe_error_code=None,
        documents=(evidence,),
        records_discovered=1,
        records_downloaded=1,
        records_reused=0,
        records_ignored=0,
        records_failed=0,
        latest_source_observed_date=evidence.source_observed_date,
    )
    decision = _record_terminal(source_harness, live, candidate)
    assert decision.receipt is not None
    assert decision.receipt.outcome is SourceSyncOutcome.FAILED
    assert decision.receipt.safe_error_code is SourceSyncErrorCode.STALE_DATA
    assert decision.receipt.records_ingested == 1
    assert decision.receipt.retry_recommended is False
    assert decision.health_after is not None and decision.health_after.version == 1
    assert decision.health_after.safe_error_code is SourceSyncErrorCode.STALE_DATA
    assert decision.health_snapshot is not None and decision.health_snapshot.health_state_version == 1
    assert _source_counts(source_harness) == (1, 1, 1, 1, 1)


def test_no_change_resets_health_to_healthy_without_alert(source_harness: _Harness) -> None:
    """真实 failure 后 no-change 恢复 healthy 且不写恢复 alert。

    Args:
        source_harness: 提供 failure 后 no-change observation 与 health/outbox tables 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Healthy reset、version advance 或零 recovery alert 断言失败时由测试抛出。
    """

    failed = _new_live_operation(source_harness, key="reset-failed")
    _record_terminal(source_harness, failed, _failure_candidate())
    healthy = _new_live_operation(source_harness, key="reset-healthy")
    decision = _record_terminal(source_harness, healthy, _no_change_candidate())
    assert decision.health_after is not None and decision.health_after.status is SourceHealthStatus.HEALTHY
    assert decision.alert_event is None
    assert decision.health_after.consecutive_failures == 0
    assert decision.health_after.safe_error_code is None
    assert _source_counts(source_harness) == (2, 2, 1, 2, 1)


def test_each_real_partial_or_failure_advances_health_exactly_once(source_harness: _Harness) -> None:
    """每个真实 observation 仅推进一个 version/snapshot。

    Args:
        source_harness: 提供 partial/failure observations 与 health version tables 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: 任一 observation 未精确推进一个 version/snapshot 时由测试抛出。
    """

    partial = _new_live_operation(source_harness, key="partial")
    first = _record_terminal(source_harness, partial, _partial_candidate(partial, label="partial"))
    failed = _new_live_operation(source_harness, key="failure")
    second = _record_terminal(source_harness, failed, _failure_candidate())
    assert first.health_after is not None and first.health_after.version == 1
    assert second.health_after is not None and second.health_after.version == 2
    assert _source_counts(source_harness) == (2, 2, 1, 2, 2)


def test_concurrent_observations_linearize_unique_health_versions_and_one_semantic_alert(source_harness: _Harness) -> None:
    """真实并发 terminal 由固定 NOWAIT 锁序线性化，重试形成唯一版本与一条语义 alert。

    Args:
        source_harness: 提供双 app transactions、NOWAIT locks 与 alert outbox 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: 并发重试、唯一 health versions 或单条 semantic alert 断言失败时抛出。
    """

    _bootstrap_execute(
        source_harness,
        f"UPDATE {_SCHEMA}.source_subscriptions SET "
        "config_json = jsonb_set(jsonb_set(config_json, '{failing_after}', '3'::jsonb), "
        "'{disable_after}', '4'::jsonb), version = version + 1 WHERE id = :subscription_id",
        {"subscription_id": UUID(source_harness.subscription_id.value)},
    )
    first_live = _new_live_operation(source_harness, key="linear-1")
    second_live = _new_live_operation(
        source_harness,
        key="linear-2",
        repository=source_harness.second_repository,
        jobs=source_harness.second_jobs,
    )
    locks_held = Barrier(2)
    release_locks = Barrier(2)

    def hold_after_locks(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        _parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        """第一 terminal 在九把锁后停住，让第二 terminal 观察真实 NOWAIT conflict。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；精确命中最终 clock 查询时同步两线程。
            _parameters: SQL 绑定参数，本回调不读取。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            无。

        Raises:
            BrokenBarrierError: 任一测试线程未在十秒内到达同步点时向调用者传播。
        """

        if statement.strip().lower() == "select clock_timestamp()":
            locks_held.wait(timeout=10)
            release_locks.wait(timeout=10)

    event.listen(source_harness.primary_engine, "before_cursor_execute", hold_after_locks)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            first_future = executor.submit(_record_terminal, source_harness, first_live, _failure_candidate())
            locks_held.wait(timeout=10)
            try:
                with pytest.raises(SourceSyncRepositoryFailure) as concurrent_error:
                    _record_terminal(
                        source_harness,
                        second_live,
                        _failure_candidate(),
                        repository=source_harness.second_repository,
                    )
                _assert_repository_error(concurrent_error.value, SourceSyncRepositoryFailureCode.UNAVAILABLE)
            finally:
                release_locks.wait(timeout=10)
            first = first_future.result(timeout=10)
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", hold_after_locks)
    second = _record_terminal(
        source_harness,
        second_live,
        _failure_candidate(),
        repository=source_harness.second_repository,
    )
    assert first.health_after is not None and second.health_after is not None
    assert (first.health_after.version, second.health_after.version) == (1, 2)
    assert _bootstrap_scalar(
        source_harness,
        f"SELECT count(DISTINCT health_state_version) FROM {_SCHEMA}.source_health_snapshots",
    ) == 2
    assert _source_counts(source_harness) == (2, 2, 1, 2, 1)


def test_alert_conflict_do_nothing_never_rolls_back_run_or_snapshot(source_harness: _Harness) -> None:
    """真实 same-dedupe conflict DO NOTHING 后 reread 收敛且保留 run/snapshot。

    Args:
        source_harness: 提供 alert conflict 注入与 terminal transaction 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Conflict reread、run/snapshot 保留或 durable counts 断言失败时抛出。
    """

    live = _new_live_operation(source_harness, key="alert")
    injected = [False]

    def inject_matching_alert(
        _connection: Connection,
        cursor: _StringExecuteCursor,
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        """在 production INSERT 前以同一 transaction 插入完全相同 outbox row。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            cursor: 在同一事务中执行抢先 INSERT 的 psycopg 游标。
            statement: 即将执行的 SQL；仅命中 alert outbox INSERT。
            parameters: production INSERT 的绑定参数，抢先写入时原样复用。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            无。

        Raises:
            psycopg.Error: 抢先执行 alert outbox INSERT 失败时向调用者传播。
        """

        if "insert into dayu_platform.source_health_alert_outbox" in statement.lower() and not injected[0]:
            injected[0] = True
            cursor.execute(statement, parameters)

    event.listen(source_harness.primary_engine, "before_cursor_execute", inject_matching_alert)
    try:
        decision = _record_terminal(source_harness, live, _failure_candidate())
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", inject_matching_alert)
    assert injected == [True]
    assert decision.alert_event is not None
    assert _source_counts(source_harness) == (1, 1, 1, 1, 1)


def test_operator_reenable_requires_enabled_subscription_and_exact_disabled_health_version(source_harness: _Harness) -> None:
    """Re-enable 先要求 disabled head，再要求 exact expected version。

    Args:
        source_harness: 提供 enabled subscription、disabled health head 与 operator re-enable 的 fixture。

    Returns:
        无。

    Raises:
        AssertionError: Status/version rejection 或合法 re-enable projection 断言失败时抛出。
    """

    class _ReenableSubclass(SourceHealthReenableRequest):
        """用于证明 re-enable request runtime type 必须精确。"""

    with pytest.raises(SourceSyncRequestRejected) as input_error:
        source_harness.repository.reenable_health(
            source_harness.scope,
            _ReenableSubclass(subscription_id=source_harness.subscription_id, expected_health_version=1),
        )
    assert input_error.value.code is SourceSyncRequestRejectionCode.INVALID_INPUT
    with pytest.raises(SourceSyncRequestRejected) as state_error:
        source_harness.repository.reenable_health(
            source_harness.scope,
            SourceHealthReenableRequest(subscription_id=source_harness.subscription_id, expected_health_version=1),
        )
    assert state_error.value.code is SourceSyncRequestRejectionCode.HEALTH_STATE_CONFLICT
    _bootstrap_execute(
        source_harness,
        f"UPDATE {_SCHEMA}.source_subscriptions SET status = 'disabled', version = version + 1 "
        "WHERE id = :subscription_id",
        {"subscription_id": UUID(source_harness.subscription_id.value)},
    )
    disabled_live = _new_live_operation(source_harness, key="stored-disabled")
    skipped = _record_terminal(
        source_harness,
        disabled_live,
        SourceNoProviderTerminalCandidate(reason=SourceNoProviderReason.DISABLED),
    )
    assert skipped.receipt is not None and skipped.receipt.outcome is SourceSyncOutcome.SKIPPED_DISABLED
    assert skipped.health_snapshot is None and skipped.health_after is not None and skipped.health_after.version == 0
    _bootstrap_execute(
        source_harness,
        f"UPDATE {_SCHEMA}.source_subscriptions SET status = 'enabled', version = version + 1 "
        "WHERE id = :subscription_id",
        {"subscription_id": UUID(source_harness.subscription_id.value)},
    )
    lives = [_new_live_operation(source_harness, key=f"reenable-{index}") for index in range(3)]
    decisions = [_record_terminal(source_harness, live, _failure_candidate()) for live in lives]
    disabled = decisions[-1].health_after
    assert disabled is not None and disabled.status is SourceHealthStatus.DISABLED
    _bootstrap_execute(
        source_harness,
        f"UPDATE {_SCHEMA}.source_subscriptions SET status = 'disabled', version = version + 1 "
        "WHERE id = :subscription_id",
        {"subscription_id": UUID(source_harness.subscription_id.value)},
    )
    with pytest.raises(SourceSyncRequestRejected) as disabled_subscription_error:
        source_harness.repository.reenable_health(
            source_harness.scope,
            SourceHealthReenableRequest(
                subscription_id=source_harness.subscription_id,
                expected_health_version=disabled.version,
            ),
        )
    assert disabled_subscription_error.value.code is SourceSyncRequestRejectionCode.HEALTH_STATE_CONFLICT
    _bootstrap_execute(
        source_harness,
        f"UPDATE {_SCHEMA}.source_subscriptions SET status = 'enabled', version = version + 1 "
        "WHERE id = :subscription_id",
        {"subscription_id": UUID(source_harness.subscription_id.value)},
    )
    with pytest.raises(SourceSyncRequestRejected) as version_error:
        source_harness.repository.reenable_health(
            source_harness.scope,
            SourceHealthReenableRequest(
                subscription_id=source_harness.subscription_id,
                expected_health_version=disabled.version + 1,
            ),
        )
    assert version_error.value.code is SourceSyncRequestRejectionCode.HEALTH_VERSION_CONFLICT


def test_operator_reenable_nowait_conflict_is_typed_unavailable_with_zero_mutation(source_harness: _Harness) -> None:
    """Re-enable subscription NOWAIT conflict 返回 unavailable。

    Args:
        source_harness: 提供可锁定 subscription 与 second repository re-enable 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: NOWAIT typed failure 或零 health mutation 断言失败时由测试抛出。
    """

    lock_connection = source_harness.bootstrap_engine.connect()
    transaction = lock_connection.begin()
    try:
        lock_connection.execute(
            text(f"SELECT id FROM {_SCHEMA}.source_subscriptions WHERE id = :id FOR UPDATE"),
            {"id": UUID(source_harness.subscription_id.value)},
        ).one()
        with pytest.raises(SourceSyncRepositoryFailure) as excinfo:
            source_harness.second_repository.reenable_health(
                source_harness.scope,
                SourceHealthReenableRequest(subscription_id=source_harness.subscription_id, expected_health_version=1),
            )
        assert excinfo.value.code is SourceSyncRepositoryFailureCode.UNAVAILABLE
        assert _source_counts(source_harness) == (0, 0, 0, 0, 0)
    finally:
        transaction.rollback()
        lock_connection.close()


def test_health_snapshot_list_limit_accepts_one_and_two_hundred_and_rejects_bool_zero_negative_or_over_max(
    source_harness: _Harness,
) -> None:
    """Health list 使用 exact 1..200 limit 与稳定 cursor。

    Args:
        source_harness: 提供 health snapshot history 与 tenant-scoped pagination 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Limit/cursor validation、page ordering 或 tenant isolation 断言失败时抛出。
    """

    live = _new_live_operation(source_harness, key="page")
    _record_terminal(source_harness, live, _no_change_candidate())
    second_live = _new_live_operation(source_harness, key="page-second")
    second_terminal = _record_terminal(source_harness, second_live, _no_change_candidate())
    page = source_harness.repository.list_health_snapshots(
        source_harness.scope,
        source_harness.subscription_id,
        None,
        limit=1,
    )
    assert len(page.snapshots) == 1 and page.snapshots[0] == second_terminal.health_snapshot
    assert page.next_cursor is not None
    next_page = source_harness.repository.list_health_snapshots(
        source_harness.scope,
        source_harness.subscription_id,
        page.next_cursor,
        limit=1,
    )
    assert len(next_page.snapshots) == 1 and next_page.next_cursor is None
    page_200 = source_harness.repository.list_health_snapshots(
        source_harness.scope,
        source_harness.subscription_id,
        SourceHealthSnapshotCursor(
            observed_at=page.snapshots[0].observed_at + timedelta(microseconds=1),
            snapshot_id=UUID(int=(1 << 128) - 1),
        ),
        limit=200,
    )
    assert len(page_200.snapshots) == 2
    for invalid in (True, 0, -1, 201):
        with pytest.raises(SourceSyncRequestRejected) as excinfo:
            source_harness.repository.list_health_snapshots(
                source_harness.scope,
                source_harness.subscription_id,
                None,
                limit=invalid,
            )
        assert excinfo.value.code is SourceSyncRequestRejectionCode.INVALID_INPUT

    class _CursorSubclass(SourceHealthSnapshotCursor):
        """用于证明 cursor runtime type 必须精确。"""

    invalid_cursor = _CursorSubclass(
        observed_at=page.snapshots[0].observed_at,
        snapshot_id=page.snapshots[0].snapshot_id,
    )
    with pytest.raises(SourceSyncRequestRejected) as cursor_error:
        source_harness.repository.list_health_snapshots(
            source_harness.scope,
            source_harness.subscription_id,
            invalid_cursor,
            limit=1,
        )
    assert cursor_error.value.code is SourceSyncRequestRejectionCode.INVALID_INPUT
    malformed_scope = Principal(tenant_id=TenantId("not-a-uuid"), user_id="malformed").to_scope()
    with pytest.raises(SourceSyncRequestRejected) as scope_error:
        source_harness.repository.get_health(malformed_scope, source_harness.subscription_id)
    assert scope_error.value.code is SourceSyncRequestRejectionCode.INVALID_INPUT

    class _SubscriptionIdSubclass(SourceSubscriptionId):
        """用于证明 subscription identity runtime type 必须精确。"""

    with pytest.raises(SourceSyncRequestRejected) as subscription_error:
        source_harness.repository.get_health(
            source_harness.scope,
            _SubscriptionIdSubclass(source_harness.subscription_id.value),
        )
    assert subscription_error.value.code is SourceSyncRequestRejectionCode.INVALID_INPUT


def test_source_operation_composite_identity_rejects_cross_job_attempt_or_subscription(source_harness: _Harness) -> None:
    """Live caller 真实读取 operation 后拒绝 cross-attempt/subscription drift。

    Args:
        source_harness: 提供 live Job、operation lineage tamper 与 alternate subscription 的 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Cross-attempt/subscription rejection 或恢复后 identity/counts 断言失败时抛出。
    """

    original = _new_live_operation(source_harness, key="operation-lineage")
    live = _take_over_operation(source_harness, original)
    assert live.acquire.generation == 2
    assert live.acquire.execution_snapshot_sha256 is not None
    before = _source_counts(source_harness)
    _set_named_trigger_enabled(
        source_harness,
        table_name="source_sync_operations",
        trigger_name="guard_source_sync_operations_transition_trigger",
        enabled=False,
    )
    try:
        _bootstrap_execute(
            source_harness,
            f"UPDATE {_SCHEMA}.source_sync_operations SET owner_attempt_id = :attempt_id "
            "WHERE id = :operation_id",
            {
                "attempt_id": original.claim.attempt_id,
                "operation_id": live.acquire.operation_id,
            },
        )
        cross_attempt_identity = _operation_identity(
            source_harness,
            live.acquire.operation_id,
        )
        cross_attempt = _record_terminal(
            source_harness,
            live,
            _no_change_candidate(),
            repository=source_harness.second_repository,
        )
        _assert_empty_terminal_decision(
            cross_attempt,
            SourceTerminalRecordAction.LEASE_LOST,
        )
        assert _operation_identity(
            source_harness,
            live.acquire.operation_id,
        ) == cross_attempt_identity
        assert _source_counts(source_harness) == before
    finally:
        try:
            _bootstrap_execute(
                source_harness,
                f"UPDATE {_SCHEMA}.source_sync_operations SET owner_attempt_id = :attempt_id "
                "WHERE id = :operation_id",
                {
                    "attempt_id": live.claim.attempt_id,
                    "operation_id": live.acquire.operation_id,
                },
            )
        finally:
            _set_named_trigger_enabled(
                source_harness,
                table_name="source_sync_operations",
                trigger_name="guard_source_sync_operations_transition_trigger",
                enabled=True,
            )

    alternate_definition = SourceDefinitionId(str(_stable_uuid("operation-alternate-definition")))
    alternate_subscription = SourceSubscriptionId(str(_stable_uuid("operation-alternate-subscription")))
    try:
        source_harness.identity.register_source_definition(
            source_harness.scope,
            SourceDefinitionCreateRequest(
                source_definition_id=alternate_definition,
                source_key="rss.v1",
                source_kind=SourceKind.ANNOUNCEMENT,
                display_name="Operation alternate source",
                enabled_by_default=True,
            ),
        )
        source_harness.identity.create_source_subscription(
            source_harness.scope,
            SourceSubscriptionCreateRequest(
                subscription_id=alternate_subscription,
                source_definition_id=alternate_definition,
                company_id=None,
                security_id=source_harness.security_id,
                status=SubscriptionStatus.ENABLED,
                config=_CONFIG,
            ),
        )
        _set_named_trigger_enabled(
            source_harness,
            table_name="source_sync_operations",
            trigger_name="guard_source_sync_operations_transition_trigger",
            enabled=False,
        )
        try:
            _bootstrap_execute(
                source_harness,
                f"UPDATE {_SCHEMA}.source_sync_operations SET subscription_id = :subscription_id "
                "WHERE id = :operation_id",
                {
                    "subscription_id": UUID(alternate_subscription.value),
                    "operation_id": live.acquire.operation_id,
                },
            )
            cross_subscription_identity = _operation_identity(
                source_harness,
                live.acquire.operation_id,
            )
            with pytest.raises(SourceSyncRepositoryFailure) as cross_subscription:
                _record_terminal(
                    source_harness,
                    live,
                    _no_change_candidate(),
                    repository=source_harness.second_repository,
                )
            _assert_repository_error(
                cross_subscription.value,
                SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT,
            )
            assert _operation_identity(
                source_harness,
                live.acquire.operation_id,
            ) == cross_subscription_identity
            assert _source_counts(source_harness) == before
        finally:
            try:
                _bootstrap_execute(
                    source_harness,
                    f"UPDATE {_SCHEMA}.source_sync_operations SET subscription_id = :subscription_id "
                    "WHERE id = :operation_id",
                    {
                        "subscription_id": UUID(source_harness.subscription_id.value),
                        "operation_id": live.acquire.operation_id,
                    },
                )
            finally:
                _set_named_trigger_enabled(
                    source_harness,
                    table_name="source_sync_operations",
                    trigger_name="guard_source_sync_operations_transition_trigger",
                    enabled=True,
                )
        assert _operation_identity(source_harness, live.acquire.operation_id) == (
            2,
            live.claim.attempt_id,
            live.acquire.execution_snapshot_sha256,
            UUID(source_harness.subscription_id.value),
        )
        assert _source_counts(source_harness) == before
    finally:
        try:
            _bootstrap_execute(
                source_harness,
                f"DELETE FROM {_SCHEMA}.source_subscriptions WHERE id = :subscription_id",
                {"subscription_id": UUID(alternate_subscription.value)},
            )
        finally:
            _bootstrap_execute(
                source_harness,
                f"DELETE FROM {_SCHEMA}.source_definitions WHERE id = :source_definition_id",
                {"source_definition_id": UUID(alternate_definition.value)},
            )


def test_operation_terminal_run_cannot_mix_different_job_or_same_job_different_attempt_lineage(
    source_harness: _Harness,
) -> None:
    """Composite FK 真实拒绝 different-job 与 same-job/different-attempt terminal 拼接。

    Args:
        source_harness: 提供 terminal run 与不同 Job/attempt rows 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Composite FK 未拒绝混合 lineage 或 persisted row 发生漂移时抛出。
    """

    first_live = _new_live_operation(source_harness, key="terminal-lineage-first")
    first = _record_terminal(source_harness, first_live, _no_change_candidate())
    second_live = _new_live_operation(source_harness, key="terminal-lineage-second")
    second = _record_terminal(source_harness, second_live, _no_change_candidate())
    assert first.receipt is not None and second.receipt is not None
    with source_harness.bootstrap_engine.begin() as connection:
        connection.execute(
            text(
                f"ALTER TABLE {_SCHEMA}.source_sync_operations DISABLE TRIGGER "
                "guard_source_sync_operations_transition_trigger"
            )
        )
        savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError) as different_job:
            connection.execute(
                text(
                    f"UPDATE {_SCHEMA}.source_sync_operations SET terminal_source_sync_run_id = :run_id "
                    "WHERE id = :operation_id"
                ),
                {"run_id": second.receipt.source_sync_run_id, "operation_id": first_live.acquire.operation_id},
            )
        assert isinstance(different_job.value.orig, psycopg.errors.ForeignKeyViolation)
        assert different_job.value.orig.diag.constraint_name == "fk_source_sync_operations_terminal_run"
        savepoint.rollback()
        connection.execute(
            text(
                f"ALTER TABLE {_SCHEMA}.source_sync_operations ENABLE TRIGGER "
                "guard_source_sync_operations_transition_trigger"
            )
        )

    takeover_source = _new_live_operation(source_harness, key="terminal-lineage-takeover")
    takeover = _take_over_operation(source_harness, takeover_source)
    takeover_terminal = _record_terminal(
        source_harness,
        takeover,
        _no_change_candidate(),
        repository=source_harness.second_repository,
    )
    assert takeover_terminal.receipt is not None
    with source_harness.bootstrap_engine.begin() as connection:
        connection.execute(
            text(
                f"ALTER TABLE {_SCHEMA}.source_sync_operations DISABLE TRIGGER "
                "guard_source_sync_operations_transition_trigger"
            )
        )
        savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError) as different_attempt:
            connection.execute(
                text(
                    f"UPDATE {_SCHEMA}.source_sync_operations SET owner_attempt_id = :attempt_id "
                    "WHERE id = :operation_id"
                ),
                {"attempt_id": takeover_source.claim.attempt_id, "operation_id": takeover.acquire.operation_id},
            )
        assert isinstance(different_attempt.value.orig, psycopg.errors.ForeignKeyViolation)
        assert different_attempt.value.orig.diag.constraint_name == "fk_source_sync_operations_terminal_run"
        savepoint.rollback()
        connection.execute(
            text(
                f"ALTER TABLE {_SCHEMA}.source_sync_operations ENABLE TRIGGER "
                "guard_source_sync_operations_transition_trigger"
            )
        )
    assert _bootstrap_scalar(
        source_harness,
        f"SELECT count(*) FROM {_SCHEMA}.source_sync_operations "
        "WHERE id = :id AND owner_attempt_id = :attempt_id AND terminal_source_sync_run_id = :run_id",
        {
            "id": takeover.acquire.operation_id,
            "attempt_id": takeover.claim.attempt_id,
            "run_id": takeover_terminal.receipt.source_sync_run_id,
        },
    ) == 1


def test_alert_snapshot_cannot_mix_same_subscription_different_source_run_lineage(source_harness: _Harness) -> None:
    """Alert composite FK 真实拒绝同 subscription 不同 run/snapshot 拼接。

    Args:
        source_harness: 提供同 subscription 的多个 runs、snapshots 与 alert outbox 的 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Alert/snapshot composite lineage 未 fail closed 或 counts 漂移时抛出。
    """

    first_live = _new_live_operation(source_harness, key="alert-lineage-first")
    first = _record_terminal(source_harness, first_live, _failure_candidate())
    second_live = _new_live_operation(source_harness, key="alert-lineage-second")
    second = _record_terminal(source_harness, second_live, _failure_candidate())
    assert first.alert_event is not None and first.health_snapshot is not None and first.receipt is not None
    assert second.health_snapshot is not None
    with source_harness.bootstrap_engine.begin() as connection:
        savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError) as mixed_alert:
            connection.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.source_health_alert_outbox "
                    "(id, tenant_id, subscription_id, source_sync_run_id, health_snapshot_id, "
                    "health_state_version, alert_kind, target_status, safe_error_code, dedupe_key, "
                    "event_json, event_sha256, created_at) SELECT :id, tenant_id, subscription_id, "
                    "source_sync_run_id, :snapshot_id, health_state_version, alert_kind, target_status, "
                    "safe_error_code, :dedupe_key, event_json, event_sha256, created_at "
                    f"FROM {_SCHEMA}.source_health_alert_outbox WHERE id = :source_id"
                ),
                {
                    "id": _stable_uuid("mixed-alert-lineage"),
                    "snapshot_id": second.health_snapshot.snapshot_id,
                    "dedupe_key": "e" * 64,
                    "source_id": first.alert_event.event_id,
                },
            )
        assert isinstance(mixed_alert.value.orig, psycopg.errors.ForeignKeyViolation)
        assert mixed_alert.value.orig.diag.constraint_name == "fk_source_health_alert_outbox_snapshot"
        savepoint.rollback()
    assert _source_counts(source_harness) == (2, 2, 1, 2, 2)


def test_live_attempt_join_uses_lease_attempt_id_current_attempt_number_fence_and_unreleased_lease_at_one_pg_clock_and_rejects_cross_job_malformed_lineage(
    source_harness: _Harness,
) -> None:
    """Attempt/lease loss 与 non-live Job 返回精确空 decision 且零 Source mutation。

    Args:
        source_harness: 提供 Job attempt/lease/fence tamper 与 terminal live checks 的 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: 任一 live-loss decision、cross-job invariant 或零 mutation 断言失败时抛出。
    """

    released = _new_live_operation(source_harness, key="lease-released")
    now = _pg_clock(source_harness)
    _bootstrap_execute(
        source_harness,
        f"UPDATE {_SCHEMA}.job_leases SET released_at = :now, release_reason = 'failure' "
        "WHERE attempt_id = :lease_id",
        {"now": now, "lease_id": released.claim.attempt_id},
    )
    before = _source_counts(source_harness)
    _assert_empty_terminal_decision(
        _record_terminal(source_harness, released, _no_change_candidate()),
        SourceTerminalRecordAction.LEASE_LOST,
    )
    assert _source_counts(source_harness) == before

    missing = _new_live_operation(source_harness, key="lease-missing")
    _bootstrap_execute(
        source_harness,
        f"DELETE FROM {_SCHEMA}.job_leases WHERE attempt_id = :lease_id",
        {"lease_id": missing.claim.attempt_id},
    )
    before = _source_counts(source_harness)
    _assert_empty_terminal_decision(
        _record_terminal(source_harness, missing, _no_change_candidate()),
        SourceTerminalRecordAction.LEASE_LOST,
    )
    with pytest.raises(SourceSyncExecutionRejected) as acquire_loss:
        source_harness.repository.acquire_operation(
            source_harness.scope,
            SourceOperationAcquireRequest(
                origin=SourceSyncOrigin.MANUAL,
                definition_id=missing.claim.definition_id,
                descriptor=missing.claim.descriptor,
                job_id=missing.claim.job_id,
                attempt_id=missing.claim.attempt_id,
                attempt_number=missing.claim.attempt_number,
                payload_sha256=missing.claim.payload.sha256,
                candidate_execution_snapshot=missing.snapshot,
            ),
        )
    assert acquire_loss.value.code is SourceSyncExecutionRejectionCode.LEASE_LOST
    assert _source_counts(source_harness) == before

    fenced = _new_live_operation(source_harness, key="lease-fence")
    _bootstrap_execute(
        source_harness,
        f"WITH original AS ("
        f"DELETE FROM {_SCHEMA}.job_leases WHERE attempt_id = :attempt_id "
        "RETURNING tenant_id, job_run_id, attempt_id, fence, token_sha256, acquired_at, expires_at"
        f") INSERT INTO {_SCHEMA}.job_leases "
        "(id, tenant_id, job_run_id, attempt_id, fence, token_sha256, acquired_at, expires_at) "
        "SELECT :lease_id, tenant_id, job_run_id, attempt_id, fence + 1, token_sha256, acquired_at, expires_at "
        "FROM original",
        {"attempt_id": fenced.claim.attempt_id, "lease_id": _stable_uuid("lease-fence-drift")},
    )
    before = _source_counts(source_harness)
    _assert_empty_terminal_decision(
        _record_terminal(source_harness, fenced, _no_change_candidate()),
        SourceTerminalRecordAction.LEASE_LOST,
    )
    assert _source_counts(source_harness) == before

    token_mismatch = _new_live_operation(source_harness, key="lease-token")
    before = _source_counts(source_harness)
    operation_before = _operation_identity(
        source_harness,
        token_mismatch.acquire.operation_id,
    )
    _set_named_trigger_enabled(
        source_harness,
        table_name="job_leases",
        trigger_name="guard_job_leases_immutable_columns_trigger",
        enabled=False,
    )
    try:
        _bootstrap_execute(
            source_harness,
            f"UPDATE {_SCHEMA}.job_leases SET token_sha256 = :token_sha256 "
            "WHERE attempt_id = :attempt_id",
            {
                "token_sha256": "e" * 64,
                "attempt_id": token_mismatch.claim.attempt_id,
            },
        )
        assert _bootstrap_scalar(
            source_harness,
            f"SELECT count(*) FROM {_SCHEMA}.job_leases AS lease "
            f"JOIN {_SCHEMA}.job_attempts AS attempt ON attempt.id = lease.attempt_id "
            "WHERE lease.attempt_id = :attempt_id "
            "AND lease.fence = attempt.fence AND lease.token_sha256 <> attempt.lease_token_sha256",
            {"attempt_id": token_mismatch.claim.attempt_id},
        ) == 1
        _assert_empty_terminal_decision(
            _record_terminal(source_harness, token_mismatch, _no_change_candidate()),
            SourceTerminalRecordAction.LEASE_LOST,
        )
        assert _source_counts(source_harness) == before
        assert _operation_identity(
            source_harness,
            token_mismatch.acquire.operation_id,
        ) == operation_before
    finally:
        try:
            _bootstrap_execute(
                source_harness,
                f"UPDATE {_SCHEMA}.job_leases AS lease SET token_sha256 = attempt.lease_token_sha256 "
                f"FROM {_SCHEMA}.job_attempts AS attempt "
                "WHERE lease.attempt_id = attempt.id AND lease.attempt_id = :attempt_id",
                {"attempt_id": token_mismatch.claim.attempt_id},
            )
        finally:
            _set_named_trigger_enabled(
                source_harness,
                table_name="job_leases",
                trigger_name="guard_job_leases_immutable_columns_trigger",
                enabled=True,
            )
    assert _bootstrap_scalar(
        source_harness,
        f"SELECT count(*) FROM {_SCHEMA}.job_leases AS lease "
        f"JOIN {_SCHEMA}.job_attempts AS attempt ON attempt.id = lease.attempt_id "
        "WHERE lease.attempt_id = :attempt_id "
        "AND lease.token_sha256 <> attempt.lease_token_sha256",
        {"attempt_id": token_mismatch.claim.attempt_id},
    ) == 0

    mismatched = _new_live_operation(source_harness, key="attempt-mismatch")
    assert mismatched.acquire.generation is not None
    assert mismatched.acquire.execution_snapshot_sha256 is not None
    mismatch_decision = source_harness.repository.record_terminal(
        source_harness.scope,
        SourceTerminalRecordRequest(
            operation_id=mismatched.acquire.operation_id,
            job_id=mismatched.claim.job_id,
            attempt_id=_stable_uuid("missing-attempt"),
            attempt_number=mismatched.claim.attempt_number,
            expected_generation=mismatched.acquire.generation,
            expected_execution_snapshot_sha256=mismatched.acquire.execution_snapshot_sha256,
            candidate=_no_change_candidate(),
        ),
    )
    _assert_empty_terminal_decision(mismatch_decision, SourceTerminalRecordAction.LEASE_LOST)

    missing_current = _new_live_operation(source_harness, key="current-attempt-missing")
    _bootstrap_execute(
        source_harness,
        f"UPDATE {_SCHEMA}.job_runs SET current_attempt_number = current_attempt_number + 1, "
        "updated_at = clock_timestamp(), version = version + 1 WHERE id = :job_id",
        {"job_id": missing_current.claim.job_id},
    )
    before = _source_counts(source_harness)
    _assert_empty_terminal_decision(
        _record_terminal(source_harness, missing_current, _no_change_candidate()),
        SourceTerminalRecordAction.LEASE_LOST,
    )
    assert _source_counts(source_harness) == before

    cancelled = _new_live_operation(source_harness, key="job-cancelled")
    source_harness.jobs.cancel(
        source_harness.scope,
        JobCancellationRequest(job_id=cancelled.claim.job_id, reason="item5-test-cancel"),
    )
    before = _source_counts(source_harness)
    _assert_empty_terminal_decision(
        _record_terminal(source_harness, cancelled, _no_change_candidate()),
        SourceTerminalRecordAction.JOB_NOT_LIVE,
    )
    assert _source_counts(source_harness) == before

    nonleased = _new_live_operation(source_harness, key="job-nonleased")
    source_harness.jobs.fail(
        source_harness.scope,
        nonleased.claim.lease,
        JobFailure(safe_error_code=SafeJobErrorCode.SOURCE_INVALID, retryable=False),
    )
    before = _source_counts(source_harness)
    _assert_empty_terminal_decision(
        _record_terminal(source_harness, nonleased, _no_change_candidate()),
        SourceTerminalRecordAction.JOB_NOT_LIVE,
    )
    assert _source_counts(source_harness) == before

    expired = _new_live_operation(source_harness, key="attempt-expired-direct")
    fixed_clock = expired.claim.lease.expires_at + timedelta(seconds=1)

    def replace_expired_clock(
        _connection: Connection,
        _cursor: psycopg.Cursor[PostgresRow],
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> CursorReplacement:
        """把唯一 Source clock 固定到 attempt lease expiry 后。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            _cursor: psycopg 执行游标，本回调不读取。
            statement: 即将执行的 SQL；仅识别 Source terminal 的单时钟查询。
            parameters: 原 SQL 的绑定参数映射，替换时保持不变。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            原 SQL 或 attempt lease expiry 后的固定时钟 SQL，以及原绑定参数映射。

        Raises:
            无。
        """

        if "clock_timestamp()" in statement.lower():
            return f"SELECT TIMESTAMPTZ '{fixed_clock.isoformat()}'", parameters
        return statement, parameters

    event.listen(source_harness.primary_engine, "before_cursor_execute", replace_expired_clock, retval=True)
    before = _source_counts(source_harness)
    try:
        expired_decision = _record_terminal(source_harness, expired, _no_change_candidate())
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", replace_expired_clock)
    _assert_empty_terminal_decision(expired_decision, SourceTerminalRecordAction.LEASE_LOST)
    assert _source_counts(source_harness) == before

    victim = _new_live_operation(source_harness, key="cross-job-victim")
    other = _new_live_operation(source_harness, key="cross-job-other")
    _bootstrap_execute(
        source_harness,
        f"WITH original AS ("
        f"DELETE FROM {_SCHEMA}.job_leases WHERE attempt_id = :attempt_id "
        "RETURNING id, tenant_id, attempt_id, fence, token_sha256, acquired_at, expires_at, "
        "released_at, release_reason, created_at, updated_at, version"
        f") INSERT INTO {_SCHEMA}.job_leases "
        "(id, tenant_id, job_run_id, attempt_id, fence, token_sha256, acquired_at, expires_at, "
        "released_at, release_reason, created_at, updated_at, version) "
        "SELECT id, tenant_id, :other_job_id, attempt_id, fence, token_sha256, acquired_at, expires_at, "
        "released_at, release_reason, created_at, updated_at, version FROM original",
        {"attempt_id": victim.claim.attempt_id, "other_job_id": other.claim.job_id},
    )
    before = _source_counts(source_harness)
    with pytest.raises(SourceSyncRepositoryFailure) as malformed_lineage:
        _record_terminal(source_harness, victim, _no_change_candidate())
    _assert_repository_error(malformed_lineage.value, SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    assert _source_counts(source_harness) == before


def test_record_terminal_on_terminal_operation_fails_closed_and_acquire_is_the_only_replay_path(
    source_harness: _Harness,
) -> None:
    """第二次 direct terminal 是 persisted invariant；replay 只由 acquire 返回。

    Args:
        source_harness: 提供已 terminal operation、direct record 与 acquire replay 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Direct terminal failure、immutable facts 或 acquire replay 断言失败时抛出。
    """

    live = _new_live_operation(source_harness, key="terminal-only")
    _record_terminal(source_harness, live, _no_change_candidate())
    with pytest.raises(SourceSyncRepositoryFailure) as excinfo:
        _record_terminal(source_harness, live, _no_change_candidate())
    assert excinfo.value.code is SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT
    replay = source_harness.repository.acquire_operation(
        source_harness.scope,
        SourceOperationAcquireRequest(
            origin=SourceSyncOrigin.MANUAL,
            definition_id=live.claim.definition_id,
            descriptor=live.claim.descriptor,
            job_id=live.claim.job_id,
            attempt_id=live.claim.attempt_id,
            attempt_number=live.claim.attempt_number,
            payload_sha256=live.claim.payload.sha256,
            candidate_execution_snapshot=live.snapshot,
        ),
    )
    assert replay.action is SourceOperationAcquireAction.TERMINAL_REPLAY
    assert replay.terminal_result is not None and replay.terminal_receipt is not None


def test_outbox_status_and_error_match_bound_snapshot_under_conflict_reread(source_harness: _Harness) -> None:
    """Persisted outbox status/error 与其 bound snapshot 一致。

    Args:
        source_harness: 提供 bound snapshot、alert conflict 注入与 reread 的隔离 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: Reread outbox status/error 未与 snapshot 一致时由测试抛出。
    """

    live = _new_live_operation(source_harness, key="outbox-bound")
    injected = [False]

    def inject_bound_conflict(
        _connection: Connection,
        cursor: _StringExecuteCursor,
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        """抢先写入 exact row，迫使 repository 从 conflict reread 重建 status/error。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            cursor: 在同一事务中执行抢先 INSERT 的 psycopg 游标。
            statement: 即将执行的 SQL；仅命中 alert outbox INSERT。
            parameters: production INSERT 的绑定参数，抢先写入时原样复用。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            无。

        Raises:
            psycopg.Error: 抢先执行 alert outbox INSERT 失败时向调用者传播。
        """

        if "insert into dayu_platform.source_health_alert_outbox" in statement.lower() and not injected[0]:
            injected[0] = True
            cursor.execute(statement, parameters)

    event.listen(source_harness.primary_engine, "before_cursor_execute", inject_bound_conflict)
    try:
        decision = _record_terminal(source_harness, live, _failure_candidate())
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", inject_bound_conflict)
    assert injected == [True]
    assert decision.alert_event is not None and decision.health_snapshot is not None
    assert decision.alert_event.target_status is decision.health_snapshot.status
    assert decision.alert_event.safe_error_code is decision.health_snapshot.safe_error_code


def test_alert_event_dedupe_then_uuid_then_snapshot_time_canonical_body_is_byte_identical_and_conflict_drift_fails_closed(
    source_harness: _Harness,
) -> None:
    """Alert dedupe、uuid5、snapshot time 与 canonical persisted body 闭合。

    Args:
        source_harness: 提供 alert event canonical row、dedupe conflict 与 drift 注入的 PG fixture。

    Returns:
        无。

    Raises:
        AssertionError: UUID/time/body identity、drift rejection 或零 rollback mutation 断言失败时抛出。
    """

    live = _new_live_operation(source_harness, key="alert-canonical")
    decision = _record_terminal(source_harness, live, _failure_candidate())
    assert decision.alert_event is not None and decision.health_snapshot is not None
    alert = decision.alert_event
    assert alert.event_id == uuid5(NAMESPACE_URL, f"investment-source-health-alert:v1:{alert.dedupe_key}")
    assert alert.created_at == decision.health_snapshot.observed_at
    persisted_sha = _bootstrap_scalar(
        source_harness,
        f"SELECT count(*) FROM {_SCHEMA}.source_health_alert_outbox "
        "WHERE id = :id AND event_sha256 = :sha AND event_json = CAST(:event_json AS jsonb)",
        {
            "id": alert.event_id,
            "sha": alert.event.sha256,
            "event_json": alert.event.canonical_bytes.decode("utf-8"),
        },
    )
    assert persisted_sha == 1

    drift_live = _new_live_operation(source_harness, key="alert-conflict-drift")
    before = _source_counts(source_harness)
    injected = [False]

    def inject_drift_alert(
        _connection: Connection,
        cursor: _StringExecuteCursor,
        statement: str,
        parameters: CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        """抢先插入 canonical 自洽、同 dedupe 但 created_at 漂移的 row。

        Args:
            _connection: SQLAlchemy 传入的当前连接，本回调不读取。
            cursor: 在同一事务中执行漂移 INSERT 的 psycopg 游标。
            statement: 即将执行的 SQL；仅命中 alert outbox INSERT。
            parameters: production INSERT 参数，用于构造 SHA 自洽的时间漂移副本。
            _context: 当前执行上下文，本回调不读取。
            _executemany: 是否批量执行，本回调不读取。

        Returns:
            无。

        Raises:
            KeyError: production 参数缺少 ``created_at`` 或 ``event_json`` 时抛出。
            AssertionError: 参数类型不符或 canonical 时间文本未被替换时抛出。
            psycopg.Error: 执行漂移 alert outbox INSERT 失败时向调用者传播。
        """

        if "insert into dayu_platform.source_health_alert_outbox" in statement.lower() and not injected[0]:
            injected[0] = True
            drift_parameters = dict(parameters)
            original_created_at = drift_parameters["created_at"]
            original_json = drift_parameters["event_json"]
            assert isinstance(original_created_at, datetime) and isinstance(original_json, str)
            drift_created_at = original_created_at + timedelta(microseconds=1)
            drift_json = original_json.replace(
                original_created_at.isoformat(),
                drift_created_at.isoformat(),
            )
            assert drift_json != original_json
            drift_parameters["created_at"] = drift_created_at
            drift_parameters["event_json"] = drift_json
            drift_parameters["event_sha256"] = hashlib.sha256(drift_json.encode("utf-8")).hexdigest()
            cursor.execute(statement, drift_parameters)

    event.listen(source_harness.primary_engine, "before_cursor_execute", inject_drift_alert)
    try:
        with pytest.raises(SourceSyncRepositoryFailure) as drift_error:
            _record_terminal(source_harness, drift_live, _failure_candidate())
    finally:
        event.remove(source_harness.primary_engine, "before_cursor_execute", inject_drift_alert)
    assert injected == [True]
    _assert_repository_error(drift_error.value, SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    assert _source_counts(source_harness) == before
