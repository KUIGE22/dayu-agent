"""Source Sync Job、Schedule 与 Source truth 的真实 PostgreSQL 16 契约。

本 owner 使用每个测试独立的 lifecycle database、两个 app login/engine，
并装配真实 Identity、Job、Schedule、Source repositories 与 application
services。只有 provider connector、领域取消信号和并发屏障是 pure fake；
所有 durable identity、lease、operation、run、health 与 outbox 事实都来自
PostgreSQL。文件不导入其它测试模块，cleanup 按 FK 顺序清空本 owner 行。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from typing import Protocol, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.engine.interfaces import ExecutionContext
from sqlalchemy.orm import Session, sessionmaker

from dayu.contracts.run import RunRecord
from dayu.investment.connectors.source import (
    SourceConnectorProtocol,
    SourceConnectorRegistry,
)
from dayu.investment.domain.identifiers import (
    CompanyId,
    Principal,
    SecurityId,
    TenantId,
    TenantScope,
)
from dayu.investment.domain.jobs import (
    AttemptState,
    JobCancellationRequest,
    JobCancellationSignalProtocol,
    JobClaim,
    JobCompletion,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobFailure,
    JobHandlerDescriptor,
    JobIdempotencyConflictError,
    JobIdempotencyRecord,
    JobRecoveryResult,
    JobState,
    SafeJobErrorCode,
)
from dayu.investment.domain.schedules import (
    ScheduleActivationRequest,
    ScheduleDefinition,
    ScheduleMaterializationResult,
    ScheduleMaterializationResultAction,
    ScheduleMisfirePolicy,
    ScheduleOccurrence,
    ScheduleReserveAction,
    ScheduleState,
    ScheduleStateTransitionAction,
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
    SourceSubscriptionProjection,
    SourceSubscriptionUpdateRequest,
    SubscriptionStatus,
)
from dayu.investment.domain.source_evidence import (
    SourceConnectorSyncAction,
    SourceConnectorSyncDecision,
    SourceConnectorSyncRequest,
    SourceFinsTerminalCandidate,
    SourceNoProviderReason,
    SourceNoProviderTerminalCandidate,
    SourceSyncResult,
    parse_source_sync_result,
)
from dayu.investment.domain.source_health import (
    SourceHealthProjection,
    SourceHealthReenableRequest,
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
    build_manual_source_request_fingerprint,
    build_manual_source_sync_payload_document,
    build_scheduled_source_request_fingerprint,
    build_scheduled_source_sync_payload_document,
    build_source_execution_snapshot,
    build_source_execution_snapshot_document,
)
from dayu.investment.domain.source_sync import (
    FINS_SOURCE_DEFINITION_KEY,
    SOURCE_SYNC_JOB_DESCRIPTOR,
    SourceBindingDisposition,
    SourceConnectorKey,
    SourcePollingScheduleRequest,
    SourceSyncEnqueueRequest,
    SourceSyncErrorCode,
    SourceSyncOrigin,
    SourceSyncOutcome,
)
from dayu.investment.storage.db import (
    PLATFORM_SCHEMA_NAME,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage.postgres_identity import PostgresIdentityRepository
from dayu.investment.storage.postgres_jobs import PostgresJobStore
from dayu.investment.storage.postgres_schedules import PostgresScheduleStore
from dayu.investment.storage.postgres_sources import PostgresSourceSyncRepository
from dayu.services.investment_sources import InvestmentSourcesService
from dayu.services.job_service import (
    JobExecutionRegistry,
    JobHandlerRegistry,
    JobService,
)
from dayu.services.schedule_service import ScheduleService
from dayu.services.source_sync_execution import (
    SourceSyncExecutionHandler,
    SourceSyncExecutionService,
)

pytestmark = pytest.mark.integration

DatabaseFactory = Callable[[], str]
_DbParam: TypeAlias = str | int | bool | datetime | UUID | bytes | None
_CursorParameters: TypeAlias = Mapping[str, _DbParam]
_CursorReplacement: TypeAlias = tuple[str, _CursorParameters]
_PostgresRow: TypeAlias = tuple[str | int | bool | datetime | UUID | None, ...]

_SCHEMA = PLATFORM_SCHEMA_NAME
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"
_MIGRATIONS_DIR = _REPO_ROOT / "dayu" / "investment" / "storage" / "migrations"
_TENANT_ID = TenantId("00000000-0000-0000-0000-000000000001")
_SCOPE = Principal(tenant_id=_TENANT_ID, user_id="source-job-owner").to_scope()
_CONFIG: dict[str, JsonValue] = {
    "forms": ("10-K", "10-Q"),
    "lookback_days": 3,
    "freshness_max_age_days": 1,
    "failing_after": 2,
    "disable_after": 3,
    "max_documents_per_sync": 50,
}


class _PlatformClusterProtocol(Protocol):
    """Fixture 注入的最窄 PostgreSQL cluster 结构。"""

    bootstrap_dsn: str
    admin_password: str

    def dsn_for_database(self, database: str, role: str) -> str:
        """构造目标 database/role 的 SQLAlchemy DSN。

        Args:
            database: Lifecycle database 名。
            role: 临时 LOGIN role 名。

        Returns:
            指向目标 database 的 SQLAlchemy DSN。

        Raises:
            无。
        """

        ...


@dataclass(frozen=True, slots=True)
class _TemporaryLogin:
    """本 owner 创建并负责删除的临时 app LOGIN。

    Args:
        role: PostgreSQL role 名。
        dsn: 该 role 指向 lifecycle database 的 DSN。
    """

    role: str
    dsn: str


def _alembic_config() -> Config:
    """构造不含 credential 的仓库 Alembic 配置。

    Args:
        无。

    Returns:
        指向受控 migrations 目录的 Config。

    Raises:
        无。
    """

    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return config


def _run_alembic(dsn: str, revision: str) -> None:
    """以显式 DSN 运行一次 upgrade 或 downgrade。

    Args:
        dsn: Lifecycle database bootstrap DSN。
        revision: 仅允许 ``head`` 或 ``base``。

    Returns:
        无。

    Raises:
        AssertionError: revision 不属于 closed allowlist 时抛出。
        RuntimeError: 迁移 admission 或 Alembic execution 失败时传播。
    """

    assert revision in {"head", "base"}
    previous = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = dsn
    try:
        if revision == "head":
            command.upgrade(_alembic_config(), revision)
        else:
            command.downgrade(_alembic_config(), revision)
    finally:
        if previous is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = previous


def _admin_execute(bootstrap_dsn: str, statement: str) -> None:
    """以 bootstrap AUTOCOMMIT 连接执行一条固定管理 SQL。

    Args:
        bootstrap_dsn: Session-owned cluster bootstrap DSN。
        statement: 本 owner 构造的 CREATE/GRANT/DROP ROLE SQL。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 连接、管理 SQL 或 dispose 失败时传播。
    """

    engine = create_engine(bootstrap_dsn, echo=False)
    try:
        with engine.connect() as connection:
            connection.execution_options(isolation_level="AUTOCOMMIT").execute(text(statement))
    finally:
        engine.dispose()


def _drop_temporary_login(
    cluster: _PlatformClusterProtocol,
    login: _TemporaryLogin,
) -> None:
    """删除一个由本 owner 创建的临时 LOGIN。

    Args:
        cluster: Session-owned cluster 窄结构。
        login: 已成功创建的临时 LOGIN。

    Returns:
        无。

    Raises:
        SQLAlchemyError: DROP ROLE 或连接失败时传播。
    """

    _admin_execute(cluster.bootstrap_dsn, f'DROP ROLE IF EXISTS "{login.role}"')


def _create_temporary_login(
    cluster: _PlatformClusterProtocol,
    database: str,
) -> _TemporaryLogin:
    """创建仅继承 platform app group 的临时 LOGIN。

    Args:
        cluster: Session-owned cluster 窄结构。
        database: 当前 lifecycle database 名。

    Returns:
        本 owner 的临时 LOGIN 句柄。

    Raises:
        SQLAlchemyError: CREATE/GRANT/DROP ROLE 或连接失败时传播。
    """

    role = f"dayu_item6_source_job_{uuid4().hex}"
    with ExitStack() as partial_cleanup:
        _admin_execute(
            cluster.bootstrap_dsn,
            f"CREATE ROLE \"{role}\" LOGIN NOBYPASSRLS PASSWORD '{cluster.admin_password}'",
        )
        login = _TemporaryLogin(
            role=role,
            dsn=cluster.dsn_for_database(database, role),
        )
        partial_cleanup.callback(_drop_temporary_login, cluster, login)
        _admin_execute(
            cluster.bootstrap_dsn,
            f'GRANT dayu_platform_app TO "{role}" WITH INHERIT TRUE, SET TRUE, ADMIN FALSE',
        )
        partial_cleanup.pop_all()
    return login


def _stable_uuid(label: str) -> UUID:
    """按测试标签生成稳定、非零 UUID。

    Args:
        label: 当前数据库内的语义标签。

    Returns:
        Item 6 source-job 命名空间内的 UUID5。

    Raises:
        无。
    """

    return uuid5(NAMESPACE_URL, f"dayu-source-job-item6:{label}")


class _HostReader:
    """JobService 使用的恒 missing Host run reader。"""

    def get_run(self, run_id: str) -> RunRecord | None:
        """返回不存在的 Host run。

        Args:
            run_id: 未被 Source Job 使用的 Host run ID。

        Returns:
            恒为 ``None``。

        Raises:
            无。
        """

        del run_id
        return None


class _CancellationSignal:
    """可置位或按序返回的领域取消信号。"""

    def __init__(self, responses: tuple[bool, ...] = ()) -> None:
        """初始化取消状态与可选读取序列。

        Args:
            responses: 每次同步读取优先消费的布尔结果。

        Returns:
            无。

        Raises:
            无。
        """

        self.requested = False
        self.responses = responses
        self.read_calls = 0
        self._event = asyncio.Event()
        if any(responses):
            self._event.set()

    def request(self) -> None:
        """置位取消并唤醒异步 waiter。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.requested = True
        self._event.set()

    def is_cancel_requested(self) -> bool:
        """返回当前序列位置或持久取消状态。

        Args:
            无。

        Returns:
            当前读取是否观察到取消。

        Raises:
            无。
        """

        index = self.read_calls
        self.read_calls += 1
        if index < len(self.responses):
            return self.responses[index]
        return self.requested

    async def wait_cancel_requested(self) -> None:
        """等待取消信号置位。

        Args:
            无。

        Returns:
            取消置位后返回。

        Raises:
            asyncio.CancelledError: 外层等待任务被取消时传播。
        """

        await self._event.wait()


class _MutableConnector(SourceConnectorProtocol):
    """返回可配置 closed candidate，并支持无 sleep 的 provider 屏障。"""

    def __init__(self) -> None:
        """初始化为立即返回 no-change 的连接器。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.decision = SourceConnectorSyncDecision(
            action=SourceConnectorSyncAction.COMPLETED,
            candidate=_no_change_candidate(),
        )
        self.calls: list[tuple[SourceConnectorSyncRequest, JobCancellationSignalProtocol]] = []
        self.entered: asyncio.Event | None = None
        self.release: asyncio.Event | None = None
        self.cancellation_to_request: _CancellationSignal | None = None

    @property
    def connector_key(self) -> SourceConnectorKey:
        """返回唯一 Fins connector key。

        Args:
            无。

        Returns:
            固定 Fins market-disclosure key。

        Raises:
            无。
        """

        return SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1

    def configure(
        self,
        *,
        decision: SourceConnectorSyncDecision | None = None,
        entered: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
        cancellation_to_request: _CancellationSignal | None = None,
    ) -> None:
        """配置下一组 provider 调用的结果与屏障。

        Args:
            decision: 可选替换 closed decision。
            entered: 调用开始时置位的事件。
            release: 返回前必须等待的事件。
            cancellation_to_request: 返回前置位的领域取消信号。

        Returns:
            无。

        Raises:
            无。
        """

        if decision is not None:
            self.decision = decision
        self.entered = entered
        self.release = release
        self.cancellation_to_request = cancellation_to_request

    def reset_observation(self) -> None:
        """清空调用记录并恢复无屏障配置。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.calls.clear()
        self.entered = None
        self.release = None
        self.cancellation_to_request = None

    async def sync(
        self,
        request: SourceConnectorSyncRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> SourceConnectorSyncDecision:
        """记录请求，在可选屏障后返回配置 decision。

        Args:
            request: Repository-authoritative execution snapshot 请求。
            cancellation: 同一领域取消信号。

        Returns:
            当前配置的 closed connector decision。

        Raises:
            asyncio.CancelledError: 外层 provider task 被取消时传播。
        """

        self.calls.append((request, cancellation))
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.cancellation_to_request is not None:
            self.cancellation_to_request.request()
        return self.decision


class _ClockOverride:
    """SQLAlchemy event 使用的固定 PostgreSQL clock 替换器。"""

    def __init__(self, clock: datetime) -> None:
        """保存 aware UTC 固定时钟。

        Args:
            clock: 替换 transaction/clock_timestamp 的时间。

        Returns:
            无。

        Raises:
            无。
        """

        self.clock = clock

    def __call__(
        self,
        _connection: Connection,
        _cursor: psycopg.Cursor[_PostgresRow],
        statement: str,
        parameters: _CursorParameters,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> _CursorReplacement:
        """把命中的 PG clock 查询替换为固定 timestamptz。

        Args:
            _connection: 当前 SQLAlchemy connection，本替换器不读取。
            _cursor: 当前 psycopg cursor，本替换器不读取。
            statement: 即将执行的 SQL。
            parameters: 原绑定参数。
            _context: 当前 execution context，本替换器不读取。
            _executemany: 是否批量执行，本替换器不读取。

        Returns:
            原 SQL，或保持同列数的固定时钟 SQL 与原参数。

        Raises:
            无。
        """

        return self.rewrite(statement, parameters)

    def rewrite(
        self,
        statement: str,
        parameters: _CursorParameters,
    ) -> _CursorReplacement:
        """保留原 SQL shape 地替换 PostgreSQL clock 函数。

        Args:
            statement: 即将执行的 SQL。
            parameters: 原绑定参数。

        Returns:
            Pair-clock standalone 的等列 SELECT，或仅把原 statement 内
            ``clock_timestamp()`` 原位替换成固定 timestamptz literal。

        Raises:
            无。
        """

        normalized = statement.strip().lower()
        fixed = self.clock.isoformat()
        if normalized == "select transaction_timestamp(), clock_timestamp()":
            return f"SELECT TIMESTAMPTZ '{fixed}', TIMESTAMPTZ '{fixed}'", parameters
        if "clock_timestamp()" in normalized:
            return (
                statement.replace(
                    "clock_timestamp()",
                    f"TIMESTAMPTZ '{fixed}'",
                ),
                parameters,
            )
        return statement, parameters


class _BarrierJobGateway:
    """让两个真实 JobService lookup miss 同步抵达 ordinary enqueue。"""

    def __init__(self, delegate: JobService, barrier: Barrier) -> None:
        """保存真实 JobService 与双 writer barrier。

        Args:
            delegate: 执行真实 lookup/enqueue 的 JobService。
            barrier: 两个 lookup miss 共享的有界屏障。

        Returns:
            无。

        Raises:
            无。
        """

        self._delegate = delegate
        self._barrier = barrier

    def get_by_idempotency_key(
        self,
        scope: TenantScope,
        *,
        descriptor: JobHandlerDescriptor,
        idempotency_key: str,
    ) -> JobIdempotencyRecord | None:
        """真实查询，并只在 miss 时等待另一个 writer。

        Args:
            scope: 可信租户范围。
            descriptor: Source Sync exact descriptor。
            idempotency_key: Manual stable key。

        Returns:
            真实 record 或 ``None``。

        Raises:
            threading.BrokenBarrierError: 另一 writer 未在十秒内抵达。
            JobInputError: 真实 JobService 输入拒绝时传播。
            JobRepositoryFailureError: 真实 JobStore 失败时传播。
        """

        record = self._delegate.get_by_idempotency_key(
            scope,
            descriptor=descriptor,
            idempotency_key=idempotency_key,
        )
        if record is None:
            self._barrier.wait(timeout=10)
        return record

    def enqueue(
        self,
        scope: TenantScope,
        request: JobEnqueueRequest,
    ) -> JobEnqueueReceipt:
        """把 ordinary enqueue 原样交给真实 JobService。

        Args:
            scope: 可信租户范围。
            request: Facade 构造的完整 enqueue request。

        Returns:
            真实 Job enqueue receipt。

        Raises:
            RuntimeError: 真实 JobService/Store typed failure 向调用者传播。
        """

        return self._delegate.enqueue(scope, request)


@dataclass(frozen=True, slots=True)
class _Harness:
    """一个隔离数据库内的双 writer 全链路句柄。

    Args:
        cluster: Session-owned PostgreSQL cluster。
        database: 当前独立数据库名。
        bootstrap_engine: Superuser 只用于精确 fixture/只读证据的 engine。
        primary_engine: Primary app engine。
        secondary_engine: Secondary app engine。
        primary_factory: Primary typed Session factory。
        secondary_factory: Secondary typed Session factory。
        identity: Primary identity repository。
        repository: Primary Source repository。
        second_repository: Secondary Source repository。
        jobs: Primary JobStore。
        second_jobs: Secondary JobStore。
        schedules: Primary ScheduleStore。
        second_schedules: Secondary ScheduleStore。
        job_service: Primary JobService。
        second_job_service: Secondary JobService。
        schedule_service: Primary ScheduleService。
        second_schedule_service: Secondary ScheduleService。
        facade: Primary public Source facade。
        second_facade: Secondary public Source facade。
        connector: 唯一可配置 pure provider connector。
        scope: 可信 tenant scope。
        source_definition_id: 已 seed Source definition ID。
        subscription_id: 已 seed subscription ID。
        company_id: 已 seed company ID。
        security_id: 已 seed security ID。
    """

    cluster: _PlatformClusterProtocol
    database: str
    bootstrap_engine: Engine
    primary_engine: Engine
    secondary_engine: Engine
    primary_factory: sessionmaker[Session]
    secondary_factory: sessionmaker[Session]
    identity: PostgresIdentityRepository
    repository: PostgresSourceSyncRepository
    second_repository: PostgresSourceSyncRepository
    jobs: PostgresJobStore
    second_jobs: PostgresJobStore
    schedules: PostgresScheduleStore
    second_schedules: PostgresScheduleStore
    job_service: JobService
    second_job_service: JobService
    schedule_service: ScheduleService
    second_schedule_service: ScheduleService
    facade: InvestmentSourcesService
    second_facade: InvestmentSourcesService
    connector: _MutableConnector
    scope: TenantScope
    source_definition_id: SourceDefinitionId
    subscription_id: SourceSubscriptionId
    company_id: CompanyId
    security_id: SecurityId


@dataclass(frozen=True, slots=True)
class _ClaimedSourceJob:
    """真实 claim 与预期 origin/snapshot 的组合。

    Args:
        claim: PostgresJobStore 返回的 live claim。
        origin: Manual 或 scheduled origin。
        snapshot: Manual candidate 或 scheduled 预期 authoritative snapshot。
    """

    claim: JobClaim
    origin: SourceSyncOrigin
    snapshot: SourceExecutionSnapshot


@dataclass(frozen=True, slots=True)
class _LiveSourceOperation:
    """已 acquired operation 与对应 claim/snapshot。

    Args:
        claimed: 产生 operation 的真实 claimed Job。
        acquire: Repository 返回的 ACQUIRED decision。
    """

    claimed: _ClaimedSourceJob
    acquire: SourceOperationAcquireDecision


def _no_change_candidate() -> SourceFinsTerminalCandidate:
    """构造合法零数据 no-change candidate。

    Args:
        无。

    Returns:
        Closed no-change candidate。

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


def _failure_candidate() -> SourceFinsTerminalCandidate:
    """构造合法零数据 provider failure candidate。

    Args:
        无。

    Returns:
        Fins invariant closed failure candidate。

    Raises:
        无。
    """

    return SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.FAILED,
        proposed_safe_error_code=SourceSyncErrorCode.FINS_INVARIANT,
        documents=(),
        records_discovered=0,
        records_downloaded=0,
        records_reused=0,
        records_ignored=0,
        records_failed=0,
        latest_source_observed_date=None,
    )


def _connector_decision(
    candidate: SourceFinsTerminalCandidate,
) -> SourceConnectorSyncDecision:
    """把合法 candidate 封装成 connector completed decision。

    Args:
        candidate: Closed Fins terminal candidate。

    Returns:
        ``COMPLETED`` connector decision。

    Raises:
        无。
    """

    return SourceConnectorSyncDecision(
        action=SourceConnectorSyncAction.COMPLETED,
        candidate=candidate,
    )


def _seed_identity(
    identity: PostgresIdentityRepository,
) -> tuple[SourceDefinitionId, SourceSubscriptionId, CompanyId, SecurityId]:
    """经真实 Identity repository 建立唯一 executable Fins binding。

    Args:
        identity: 当前 app role 的真实 Identity repository。

    Returns:
        Definition、subscription、company、security 四个稳定标识。

    Raises:
        RepositoryError: Identity repository typed failure 向调用者传播。
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
                legal_name="Item Six Corp",
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


def _build_job_service(
    store: PostgresJobStore,
    repository: PostgresSourceSyncRepository,
    connector: _MutableConnector,
) -> JobService:
    """装配真实 JobService 与唯一 Source execution handler。

    Args:
        store: 当前 engine 的真实 JobStore。
        repository: 同 engine 的真实 Source repository。
        connector: Fixture-owned pure connector。

    Returns:
        Descriptor/execution registries 已封存的 JobService。

    Raises:
        JobInputError: Registry exact registration 不闭合时传播。
    """

    descriptor_registry = JobHandlerRegistry()
    descriptor_registry.register_descriptor(SOURCE_SYNC_JOB_DESCRIPTOR)
    execution_registry = JobExecutionRegistry(descriptor_registry)
    handler = SourceSyncExecutionHandler(
        execution_service=SourceSyncExecutionService(
            repository=repository,
            connector_registry=SourceConnectorRegistry((connector,)),
        )
    )
    execution_registry.register_handler(SOURCE_SYNC_JOB_DESCRIPTOR, handler)
    execution_registry.seal()
    descriptor_registry.seal()
    return JobService(
        job_store=store,
        descriptor_registry=descriptor_registry,
        host_run_reader=_HostReader(),
        execution_registry=execution_registry,
    )


def _truncate_owned_rows(bootstrap_engine: Engine) -> None:
    """按 FK owner 顺序清空本文件可能创建的 durable rows。

    Args:
        bootstrap_engine: 当前 lifecycle database 的 bootstrap engine。

    Returns:
        无。

    Raises:
        SQLAlchemyError: TRUNCATE transaction 失败时传播。
    """

    with bootstrap_engine.begin() as connection:
        connection.execute(
            text(
                f"TRUNCATE TABLE {_SCHEMA}.source_health_alert_outbox, "
                f"{_SCHEMA}.source_health_snapshots, {_SCHEMA}.source_health_states, "
                f"{_SCHEMA}.source_sync_operations, {_SCHEMA}.source_sync_runs, "
                f"{_SCHEMA}.job_schedule_occurrences, {_SCHEMA}.job_schedules, "
                f"{_SCHEMA}.agent_run_correlations, {_SCHEMA}.job_events, "
                f"{_SCHEMA}.job_attempt_receipts, {_SCHEMA}.job_leases, "
                f"{_SCHEMA}.job_attempts, {_SCHEMA}.job_runs CASCADE"
            )
        )


@pytest.fixture()
def source_job_harness(
    platform_cluster: _PlatformClusterProtocol,
    lifecycle_database: DatabaseFactory,
) -> Iterator[_Harness]:
    """创建迁移后的双 app 全链路 fixture，并按 FK 顺序清理。

    Args:
        platform_cluster: Session-owned pinned PostgreSQL 16 cluster。
        lifecycle_database: 当前 test 的独立数据库 factory。

    Yields:
        已 seed identity、装配真实 service/repository 的双 writer harness。

    Raises:
        PlatformMigrationAdmissionError: Upgrade/downgrade admission 失败时传播。
        PlatformIntegrationError: 临时 app role 创建或删除失败时传播。
        RepositoryError: Identity seed 失败时传播。
        SQLAlchemyError: Engine transaction 或 cleanup 失败时传播。
    """

    with ExitStack() as cleanup:
        database = lifecycle_database()
        bootstrap_dsn = platform_cluster.dsn_for_database(database, "postgres")
        cleanup.callback(_run_alembic, bootstrap_dsn, "base")
        _run_alembic(bootstrap_dsn, "head")
        bootstrap_engine = create_platform_engine(bootstrap_dsn)
        cleanup.callback(bootstrap_engine.dispose)
        cleanup.callback(_truncate_owned_rows, bootstrap_engine)
        primary_login = _create_temporary_login(platform_cluster, database)
        cleanup.callback(_drop_temporary_login, platform_cluster, primary_login)
        secondary_login = _create_temporary_login(platform_cluster, database)
        cleanup.callback(_drop_temporary_login, platform_cluster, secondary_login)
        primary_engine = create_platform_engine(primary_login.dsn)
        cleanup.callback(primary_engine.dispose)
        secondary_engine = create_platform_engine(secondary_login.dsn)
        cleanup.callback(secondary_engine.dispose)
        primary_factory = create_platform_session_factory(primary_engine)
        secondary_factory = create_platform_session_factory(secondary_engine)
        identity = PostgresIdentityRepository(primary_factory)
        source_definition_id, subscription_id, company_id, security_id = _seed_identity(identity)
        connector = _MutableConnector()
        repository = PostgresSourceSyncRepository(primary_factory)
        second_repository = PostgresSourceSyncRepository(secondary_factory)
        jobs = PostgresJobStore(primary_factory)
        second_jobs = PostgresJobStore(secondary_factory)
        schedules = PostgresScheduleStore(primary_factory)
        second_schedules = PostgresScheduleStore(secondary_factory)
        job_service = _build_job_service(jobs, repository, connector)
        second_job_service = _build_job_service(second_jobs, second_repository, connector)
        schedule_service = ScheduleService(
            schedule_store=schedules,
            job_gateway=job_service,
            schedule_max_lookback_seconds=86_400,
            schedule_candidate_scan_limit=512,
        )
        second_schedule_service = ScheduleService(
            schedule_store=second_schedules,
            job_gateway=second_job_service,
            schedule_max_lookback_seconds=86_400,
            schedule_candidate_scan_limit=512,
        )
        facade = InvestmentSourcesService(
            job_gateway=job_service,
            schedule_gateway=schedule_service,
            source_repository=repository,
        )
        second_facade = InvestmentSourcesService(
            job_gateway=second_job_service,
            schedule_gateway=second_schedule_service,
            source_repository=second_repository,
        )
        harness = _Harness(
            cluster=platform_cluster,
            database=database,
            bootstrap_engine=bootstrap_engine,
            primary_engine=primary_engine,
            secondary_engine=secondary_engine,
            primary_factory=primary_factory,
            secondary_factory=secondary_factory,
            identity=identity,
            repository=repository,
            second_repository=second_repository,
            jobs=jobs,
            second_jobs=second_jobs,
            schedules=schedules,
            second_schedules=second_schedules,
            job_service=job_service,
            second_job_service=second_job_service,
            schedule_service=schedule_service,
            second_schedule_service=second_schedule_service,
            facade=facade,
            second_facade=second_facade,
            connector=connector,
            scope=_SCOPE,
            source_definition_id=source_definition_id,
            subscription_id=subscription_id,
            company_id=company_id,
            security_id=security_id,
        )
        yield harness


def _bootstrap_execute(
    harness: _Harness,
    statement: str,
    parameters: dict[str, _DbParam],
) -> None:
    """在 owned database 内执行精确 bootstrap DML。

    Args:
        harness: 提供 bootstrap engine 的隔离句柄。
        statement: 当前对抗场景的参数化 SQL。
        parameters: SQL 绑定参数。

    Returns:
        无；transaction 成功退出即提交。

    Raises:
        SQLAlchemyError: 连接、执行或提交失败时传播。
    """

    with harness.bootstrap_engine.begin() as connection:
        connection.execute(text(statement), parameters)


def _pg_clock(harness: _Harness) -> datetime:
    """读取当前数据库 aware UTC clock。

    Args:
        harness: 提供 bootstrap engine 的隔离句柄。

    Returns:
        规范到 UTC 的 PostgreSQL clock。

    Raises:
        AssertionError: PostgreSQL 未返回 datetime 时抛出。
        SQLAlchemyError: 只读查询或 rollback 失败时传播。
    """

    with harness.bootstrap_engine.connect() as connection:
        value = connection.execute(text("SELECT clock_timestamp()"), {}).scalar_one()
        connection.rollback()
    assert isinstance(value, datetime)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _count(
    harness: _Harness,
    table: str,
    *,
    predicate: str = "TRUE",
    parameters: dict[str, _DbParam] | None = None,
) -> int:
    """读取 owned schema 单表的精确行数。

    Args:
        harness: 提供 bootstrap engine 的隔离句柄。
        table: allowlisted platform table 名。
        predicate: 测试内固定的 SQL predicate。
        parameters: 可选绑定参数。

    Returns:
        匹配行数。

    Raises:
        AssertionError: PostgreSQL count 不是 exact int 时抛出。
        SQLAlchemyError: 查询或 rollback 失败时传播。
    """

    with harness.bootstrap_engine.connect() as connection:
        value = connection.execute(
            text(f"SELECT count(*) FROM {_SCHEMA}.{table} WHERE {predicate}"),
            parameters if parameters is not None else {},
        ).scalar_one()
        connection.rollback()
    assert type(value) is int
    return value


def _source_counts(harness: _Harness) -> tuple[int, int, int, int, int]:
    """返回 operation/run/health/snapshot/outbox 五表行数。

    Args:
        harness: 当前隔离数据库句柄。

    Returns:
        五个表按固定顺序的 count tuple。

    Raises:
        AssertionError: 任一 count 不是 exact int 时抛出。
        SQLAlchemyError: 任一查询失败时传播。
    """

    return (
        _count(harness, "source_sync_operations"),
        _count(harness, "source_sync_runs"),
        _count(harness, "source_health_states"),
        _count(harness, "source_health_snapshots"),
        _count(harness, "source_health_alert_outbox"),
    )


def _job_state(harness: _Harness, job_id: UUID) -> JobState:
    """读取一个 Job 的 current durable state。

    Args:
        harness: 当前隔离数据库句柄。
        job_id: 目标 Job UUID。

    Returns:
        Closed ``JobState``。

    Raises:
        AssertionError: Row missing 或 state 不是字符串时抛出。
        ValueError: Persisted state 不属于 closed enum 时抛出。
    """

    with harness.bootstrap_engine.connect() as connection:
        value = connection.execute(
            text(f"SELECT state FROM {_SCHEMA}.job_runs WHERE tenant_id=:tenant_id AND id=:job_id"),
            {"tenant_id": _TENANT_ID.value, "job_id": job_id},
        ).scalar_one()
        connection.rollback()
    assert isinstance(value, str)
    return JobState(value)


def _attempt_states(harness: _Harness, job_id: UUID) -> tuple[AttemptState, ...]:
    """按 attempt_number 读取一个 Job 的 attempt states。

    Args:
        harness: 当前隔离数据库句柄。
        job_id: 目标 Job UUID。

    Returns:
        Closed attempt state tuple。

    Raises:
        AssertionError: 任一 state 不是字符串时抛出。
        ValueError: Persisted state 不属于 closed enum 时抛出。
    """

    with harness.bootstrap_engine.connect() as connection:
        values = connection.execute(
            text(
                f"SELECT state FROM {_SCHEMA}.job_attempts "
                "WHERE tenant_id=:tenant_id AND job_run_id=:job_id "
                "ORDER BY attempt_number"
            ),
            {"tenant_id": _TENANT_ID.value, "job_id": job_id},
        ).scalars()
        states = tuple(values)
        connection.rollback()
    assert all(isinstance(value, str) for value in states)
    return tuple(AttemptState(value) for value in states)


def _operation_projection(
    harness: _Harness,
    job_id: UUID,
) -> tuple[str, int, UUID, str, str]:
    """读取 Source operation 的 owner/generation/snapshot 核心事实。

    Args:
        harness: 当前隔离数据库句柄。
        job_id: Operation 绑定的 Job UUID。

    Returns:
        State、generation、owner attempt、disposition、snapshot SHA-256。

    Raises:
        AssertionError: Row missing 或任一数据库类型漂移时抛出。
    """

    with harness.bootstrap_engine.connect() as connection:
        row = connection.execute(
            text(
                f"SELECT state, generation, owner_attempt_id, "
                "owner_binding_disposition, execution_snapshot_sha256 "
                f"FROM {_SCHEMA}.source_sync_operations "
                "WHERE tenant_id=:tenant_id AND job_run_id=:job_id"
            ),
            {"tenant_id": _TENANT_ID.value, "job_id": job_id},
        ).one()
        connection.rollback()
    state, generation, owner_attempt_id, disposition, snapshot_sha256 = tuple(row)
    assert isinstance(state, str)
    assert type(generation) is int
    assert isinstance(owner_attempt_id, UUID)
    assert isinstance(disposition, str)
    assert isinstance(snapshot_sha256, str)
    return state, generation, owner_attempt_id, disposition, snapshot_sha256


def _source_result_sha256(harness: _Harness, job_id: UUID) -> str:
    """读取一个 Job 唯一 Source run 的 canonical result SHA-256。

    Args:
        harness: 当前隔离数据库句柄。
        job_id: Source run 绑定的 Job UUID。

    Returns:
        持久化 canonical result SHA-256。

    Raises:
        AssertionError: Row 不唯一或 SHA 类型漂移时抛出。
    """

    with harness.bootstrap_engine.connect() as connection:
        value = connection.execute(
            text(
                f"SELECT result_sha256 FROM {_SCHEMA}.source_sync_runs "
                "WHERE tenant_id=:tenant_id AND job_run_id=:job_id"
            ),
            {"tenant_id": _TENANT_ID.value, "job_id": job_id},
        ).scalar_one()
        connection.rollback()
    assert isinstance(value, str)
    return value


def _manual_request(
    harness: _Harness,
    *,
    label: str,
    available_at: datetime | None = None,
) -> SourceSyncEnqueueRequest:
    """构造 facade 使用的合法 manual caller intent。

    Args:
        harness: 提供 subscription/version 的隔离句柄。
        label: 隔离 trigger identity 的语义标签。
        available_at: 可选首次 available time。

    Returns:
        Exact ``SourceSyncEnqueueRequest``。

    Raises:
        AssertionError: Subscription projection missing 时抛出。
    """

    subscription = harness.identity.get_source_subscription(
        harness.scope,
        harness.subscription_id,
    )
    assert subscription is not None
    first_available_at = available_at if available_at is not None else _pg_clock(harness) - timedelta(minutes=1)
    return SourceSyncEnqueueRequest(
        subscription_id=harness.subscription_id,
        expected_subscription_version=subscription.version,
        trigger_id=_stable_uuid(f"manual-trigger:{label}"),
        available_at=first_available_at,
        deadline_at=_pg_clock(harness) + timedelta(hours=4),
    )


def _polling_request(
    harness: _Harness,
    *,
    label: str,
) -> SourcePollingScheduleRequest:
    """构造 facade 使用的合法 static polling intent。

    Args:
        harness: 提供 subscription/version 的隔离句柄。
        label: 隔离 schedule key 的语义标签。

    Returns:
        Exact ``SourcePollingScheduleRequest``。

    Raises:
        AssertionError: Subscription projection missing 时抛出。
    """

    subscription = harness.identity.get_source_subscription(
        harness.scope,
        harness.subscription_id,
    )
    assert subscription is not None
    return SourcePollingScheduleRequest(
        subscription_id=harness.subscription_id,
        expected_subscription_version=subscription.version,
        cron_expression="* * * * *",
        timezone_name="UTC",
        misfire_policy=ScheduleMisfirePolicy.COALESCE_ONE,
        misfire_grace_seconds=60,
        job_deadline_seconds=600,
        schedule_key=f"source-job-item6:{label}",
    )


def _enqueue_manual_direct(
    harness: _Harness,
    *,
    label: str,
    available_at: datetime | None = None,
    jobs: PostgresJobStore | None = None,
    repository: PostgresSourceSyncRepository | None = None,
) -> tuple[JobEnqueueReceipt, SourceExecutionSnapshot, SourceSyncEnqueueRequest]:
    """以真实 binding 与 JobStore 直接创建合法 manual Job。

    Args:
        harness: 提供 Source/Job repositories 与 identity 的隔离句柄。
        label: 隔离 trigger/key identity 的语义标签。
        available_at: 可选 immutable original available time。
        jobs: 可选 JobStore；省略时使用 primary。
        repository: 可选 binding reader；省略时使用 primary。

    Returns:
        Enqueue receipt、frozen snapshot 与 caller intent。

    Raises:
        SourceSyncRequestRejected: Binding 当前不可执行时传播。
        RuntimeError: JobStore typed failure 向调用者传播。
    """

    active_jobs = jobs if jobs is not None else harness.jobs
    active_repository = repository if repository is not None else harness.repository
    request = _manual_request(harness, label=label, available_at=available_at)
    binding = active_repository.get_executable_binding(
        harness.scope,
        harness.subscription_id,
    )
    snapshot = build_source_execution_snapshot(binding, request.available_at)
    payload = build_manual_source_sync_payload_document(
        ManualSourceSyncPayload(
            subscription_id=request.subscription_id,
            expected_subscription_version=request.expected_subscription_version,
            trigger_id=request.trigger_id,
            execution_snapshot=snapshot,
            request_fingerprint=build_manual_source_request_fingerprint(request),
        )
    )
    receipt = active_jobs.enqueue(
        harness.scope,
        JobEnqueueRequest(
            descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
            idempotency_key=(f"source-sync-trigger:v1:{request.subscription_id.value}:{request.trigger_id}"),
            payload=payload,
            available_at=request.available_at,
            deadline_at=request.deadline_at,
        ),
    )
    return receipt, snapshot, request


def _enqueue_scheduled_direct(
    harness: _Harness,
    *,
    label: str,
    available_at: datetime | None = None,
) -> tuple[JobEnqueueReceipt, SourceExecutionSnapshot]:
    """以真实 current binding 创建合法 scheduled Job。

    Args:
        harness: 提供 binding 与 JobStore 的隔离句柄。
        label: 隔离 schedule/key identity 的语义标签。
        available_at: 可选 immutable original available time。

    Returns:
        Enqueue receipt 与按 current binding 预期的 snapshot。

    Raises:
        SourceSyncRequestRejected: Binding 当前不可执行时传播。
        RuntimeError: JobStore typed failure 向调用者传播。
    """

    binding = harness.repository.get_executable_binding(
        harness.scope,
        harness.subscription_id,
    )
    first_available_at = available_at if available_at is not None else _pg_clock(harness) - timedelta(minutes=1)
    schedule_request = _polling_request(harness, label=label)
    assert schedule_request.schedule_key is not None
    payload = build_scheduled_source_sync_payload_document(
        ScheduledSourceSyncPayload(
            subscription_id=harness.subscription_id,
            source_definition_id=harness.source_definition_id,
            expected_subscription_version=binding.subscription_version,
            schedule_key=schedule_request.schedule_key,
            source_request_fingerprint=build_scheduled_source_request_fingerprint(
                schedule_request,
                schedule_request.schedule_key,
            ),
        )
    )
    receipt = harness.jobs.enqueue(
        harness.scope,
        JobEnqueueRequest(
            descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
            idempotency_key=f"source-sync-scheduled:v1:{label}",
            payload=payload,
            available_at=first_available_at,
            deadline_at=_pg_clock(harness) + timedelta(hours=4),
        ),
    )
    return receipt, build_source_execution_snapshot(binding, first_available_at)


def _claim(
    harness: _Harness,
    receipt: JobEnqueueReceipt,
    *,
    worker: str,
    jobs: PostgresJobStore | None = None,
) -> JobClaim:
    """领取并核对指定新 Job。

    Args:
        harness: 提供 tenant 与默认 JobStore 的隔离句柄。
        receipt: 预期被领取的 enqueue receipt。
        worker: 当前 worker identity。
        jobs: 可选 JobStore；省略时使用 primary。

    Returns:
        与 receipt 同 Job 的真实 claim。

    Raises:
        AssertionError: 无 claim 或 claim 属于其它 Job 时抛出。
        RuntimeError: JobStore typed failure 向调用者传播。
    """

    active_jobs = jobs if jobs is not None else harness.jobs
    claim = active_jobs.claim(harness.scope, worker)
    assert claim is not None and claim.job_id == receipt.job_id
    return claim


def _claimed_manual(
    harness: _Harness,
    *,
    label: str,
    available_at: datetime | None = None,
) -> _ClaimedSourceJob:
    """经直接 enqueue/claim 创建 manual claimed Job。

    Args:
        harness: 当前隔离数据库句柄。
        label: 隔离 request/worker identity 的标签。
        available_at: 可选 immutable original available time。

    Returns:
        Manual claim 与 frozen snapshot。

    Raises:
        AssertionError: Claim 不属于 enqueue receipt 时抛出。
        RuntimeError: Repository/JobStore typed failure 向调用者传播。
    """

    receipt, snapshot, _request = _enqueue_manual_direct(
        harness,
        label=label,
        available_at=available_at,
    )
    return _ClaimedSourceJob(
        claim=_claim(harness, receipt, worker=f"manual-{label}"),
        origin=SourceSyncOrigin.MANUAL,
        snapshot=snapshot,
    )


def _claimed_scheduled(
    harness: _Harness,
    *,
    label: str,
    available_at: datetime | None = None,
) -> _ClaimedSourceJob:
    """经直接 enqueue/claim 创建 scheduled claimed Job。

    Args:
        harness: 当前隔离数据库句柄。
        label: 隔离 request/worker identity 的标签。
        available_at: 可选 immutable original available time。

    Returns:
        Scheduled claim 与预期 authoritative snapshot。

    Raises:
        AssertionError: Claim 不属于 enqueue receipt 时抛出。
        RuntimeError: Repository/JobStore typed failure 向调用者传播。
    """

    receipt, snapshot = _enqueue_scheduled_direct(
        harness,
        label=label,
        available_at=available_at,
    )
    return _ClaimedSourceJob(
        claim=_claim(harness, receipt, worker=f"scheduled-{label}"),
        origin=SourceSyncOrigin.SCHEDULED,
        snapshot=snapshot,
    )


def _acquire_request(claimed: _ClaimedSourceJob) -> SourceOperationAcquireRequest:
    """从真实 claim 构造 exact Source acquire request。

    Args:
        claimed: 提供 Job lineage、origin 与 candidate snapshot 的组合。

    Returns:
        Manual 携带 candidate、scheduled 不携带 candidate 的 request。

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
        candidate_execution_snapshot=(claimed.snapshot if claimed.origin is SourceSyncOrigin.MANUAL else None),
    )


def _acquire(
    harness: _Harness,
    claimed: _ClaimedSourceJob,
    *,
    repository: PostgresSourceSyncRepository | None = None,
) -> _LiveSourceOperation:
    """经真实 Source repository 创建或 takeover operation。

    Args:
        harness: 提供 tenant 与默认 Source repository 的隔离句柄。
        claimed: 当前 live Job attempt。
        repository: 可选 Source repository；省略时使用 primary。

    Returns:
        ``ACQUIRED`` decision 与 claimed facts。

    Raises:
        AssertionError: Repository 未返回 ACQUIRED 时抛出。
        SourceSyncRequestRejected: Acquire lineage 非法时传播。
        SourceSyncExecutionRejected: Job/lease 不再 live 时传播。
        SourceSyncRepositoryFailure: PostgreSQL failure 时传播。
    """

    active_repository = repository if repository is not None else harness.repository
    decision = active_repository.acquire_operation(
        harness.scope,
        _acquire_request(claimed),
    )
    assert decision.action is SourceOperationAcquireAction.ACQUIRED
    return _LiveSourceOperation(claimed=claimed, acquire=decision)


def _record_terminal(
    harness: _Harness,
    live: _LiveSourceOperation,
    candidate: SourceFinsTerminalCandidate | SourceNoProviderTerminalCandidate,
    *,
    repository: PostgresSourceSyncRepository | None = None,
) -> SourceTerminalRecordDecision:
    """按 acquired durable facts 提交 exact terminal request。

    Args:
        harness: 提供 tenant 与默认 Source repository 的隔离句柄。
        live: 当前 operation owner facts。
        candidate: Closed provider/no-provider candidate。
        repository: 可选 Source repository；省略时使用 primary。

    Returns:
        Repository authoritative terminal decision。

    Raises:
        AssertionError: Acquire decision 缺 generation/snapshot SHA 时抛出。
        SourceSyncRequestRejected: Terminal lineage 非法时传播。
        SourceSyncRepositoryFailure: PostgreSQL failure 时传播。
    """

    generation = live.acquire.generation
    snapshot_sha256 = live.acquire.execution_snapshot_sha256
    assert generation is not None and snapshot_sha256 is not None
    active_repository = repository if repository is not None else harness.repository
    return active_repository.record_terminal(
        harness.scope,
        SourceTerminalRecordRequest(
            operation_id=live.acquire.operation_id,
            job_id=live.claimed.claim.job_id,
            attempt_id=live.claimed.claim.attempt_id,
            attempt_number=live.claimed.claim.attempt_number,
            expected_generation=generation,
            expected_execution_snapshot_sha256=snapshot_sha256,
            candidate=candidate,
        ),
    )


def _retry_claim(
    harness: _Harness,
    claimed: _ClaimedSourceJob,
    *,
    worker: str,
    safe_error_code: SafeJobErrorCode = SafeJobErrorCode.REPOSITORY_FAILURE,
) -> _ClaimedSourceJob:
    """以真实 fail/retry 与固定 PG clock 形成下一 attempt。

    Args:
        harness: 提供 primary fail 与 secondary claim 的隔离句柄。
        claimed: 当前 leased attempt 与 origin/snapshot。
        worker: Retry worker identity。
        safe_error_code: 当前 retryable safe error code。

    Returns:
        同一 Job 的下一 live attempt，并保留 origin/snapshot。

    Raises:
        AssertionError: Fail 未安排 retry 或 claim 不属于同 Job 时抛出。
        RuntimeError: JobStore typed failure 向调用者传播。
    """

    recovery = harness.jobs.fail(
        harness.scope,
        claimed.claim.lease,
        JobFailure(safe_error_code=safe_error_code, retryable=True),
    )
    assert recovery.next_available_at is not None
    override = _ClockOverride(recovery.next_available_at + timedelta(seconds=1))
    event.listen(
        harness.secondary_engine,
        "before_cursor_execute",
        override,
        retval=True,
    )
    try:
        retry = harness.second_jobs.claim(harness.scope, worker)
    finally:
        event.remove(harness.secondary_engine, "before_cursor_execute", override)
    assert retry is not None and retry.job_id == claimed.claim.job_id
    return _ClaimedSourceJob(
        claim=retry,
        origin=claimed.origin,
        snapshot=claimed.snapshot,
    )


def _recover_expired_claim(
    harness: _Harness,
    claimed: _ClaimedSourceJob,
    *,
    worker: str,
) -> tuple[JobRecoveryResult, _ClaimedSourceJob | None]:
    """以真实 generic recover 收敛模拟 crash 的过期 attempt。

    Args:
        harness: 提供 primary recover 与 secondary claim 的隔离句柄。
        claimed: 模拟进程崩溃后遗留的 leased attempt。
        worker: 若仍可 retry，下一 worker identity。

    Returns:
        当前 Job recovery result 与可空下一 claim。

    Raises:
        AssertionError: Recovery 未包含目标 Job 或后续 claim identity 漂移时抛出。
        RuntimeError: JobStore typed failure 向调用者传播。
    """

    recover_clock = claimed.claim.lease.expires_at + timedelta(seconds=1)
    recover_override = _ClockOverride(recover_clock)
    event.listen(
        harness.primary_engine,
        "before_cursor_execute",
        recover_override,
        retval=True,
    )
    try:
        recoveries = harness.jobs.recover(harness.scope)
    finally:
        event.remove(harness.primary_engine, "before_cursor_execute", recover_override)
    recovery = next(result for result in recoveries if result.job_id == claimed.claim.job_id)
    if recovery.next_available_at is None:
        return recovery, None
    claim_override = _ClockOverride(recovery.next_available_at + timedelta(seconds=1))
    event.listen(
        harness.secondary_engine,
        "before_cursor_execute",
        claim_override,
        retval=True,
    )
    try:
        retry = harness.second_jobs.claim(harness.scope, worker)
    finally:
        event.remove(harness.secondary_engine, "before_cursor_execute", claim_override)
    assert retry is not None and retry.job_id == claimed.claim.job_id
    return recovery, _ClaimedSourceJob(
        claim=retry,
        origin=claimed.origin,
        snapshot=claimed.snapshot,
    )


async def _execute_claim(
    harness: _Harness,
    claimed: _ClaimedSourceJob,
    cancellation: _CancellationSignal | None = None,
    *,
    service: JobService | None = None,
) -> JobCompletion | JobFailure:
    """通过真实 JobService/handler 执行一个 claimed Source Job。

    Args:
        harness: 提供默认 JobService 的隔离句柄。
        claimed: 当前 live Job claim。
        cancellation: 可选领域取消信号；省略时使用未取消信号。
        service: 可选 JobService；省略时使用 primary。

    Returns:
        Handler 经 JobService 收窄后的 completion 或 failure。

    Raises:
        asyncio.CancelledError: Pre-PONR outer task cancellation 时传播。
    """

    active_service = service if service is not None else harness.job_service
    active_cancellation = cancellation if cancellation is not None else _CancellationSignal()
    return await active_service.execute_claim(
        harness.scope,
        claimed.claim,
        active_cancellation,
    )


def _complete_claim(
    harness: _Harness,
    claimed: _ClaimedSourceJob,
    completion: JobCompletion,
) -> None:
    """以真实 lease 把 Source completion 写入 Job envelope。

    Args:
        harness: 提供真实 JobService 的隔离句柄。
        claimed: 当前 live claim。
        completion: Handler 返回的 closed completion。

    Returns:
        无。

    Raises:
        RuntimeError: JobStore typed terminal failure 向调用者传播。
    """

    harness.job_service.complete(
        harness.scope,
        claimed.claim.lease,
        completion,
    )


def _set_subscription(
    harness: _Harness,
    *,
    status: SubscriptionStatus,
    config: Mapping[str, JsonValue] = _CONFIG,
) -> SourceSubscriptionProjection:
    """以真实 Identity CAS 更新 subscription status/config。

    Args:
        harness: 提供 Identity repository 的隔离句柄。
        status: 目标 closed subscription status。
        config: 目标 closed JSON config。

    Returns:
        更新后的 subscription projection。

    Raises:
        AssertionError: Subscription missing 时抛出。
        RepositoryError: Identity repository typed failure 时传播。
    """

    current = harness.identity.get_source_subscription(
        harness.scope,
        harness.subscription_id,
    )
    assert current is not None
    return harness.identity.update_source_subscription(
        harness.scope,
        harness.subscription_id,
        current.version,
        SourceSubscriptionUpdateRequest(status=status, config=config),
    )


def _seed_disabled_health(harness: _Harness) -> SourceHealthProjection:
    """以三次真实 failed observation 把 health 推进到 disabled。

    Args:
        harness: 提供真实 Job/Source repositories 的隔离句柄。

    Returns:
        Version 3 disabled health projection。

    Raises:
        AssertionError: 任次 terminal 未 recorded 或最终未 disabled 时抛出。
        RuntimeError: Repository/JobStore typed failure 向调用者传播。
    """

    for index in range(3):
        claimed = _claimed_manual(harness, label=f"health-disable-{index}")
        live = _acquire(harness, claimed)
        terminal = _record_terminal(harness, live, _failure_candidate())
        assert terminal.action is SourceTerminalRecordAction.RECORDED
    health = harness.repository.get_health(
        harness.scope,
        harness.subscription_id,
    )
    assert health.status is SourceHealthStatus.DISABLED
    assert health.version == 3
    return health


def _activate_schedule(
    harness: _Harness,
    definition: ScheduleDefinition,
) -> ScheduleDefinition:
    """经真实 ScheduleService 激活 disabled Source schedule。

    Args:
        harness: 提供真实 ScheduleService/Job availability 的隔离句柄。
        definition: Facade ensure 返回的 disabled definition。

    Returns:
        Active definition 与首个 PG-clock-derived candidate。

    Raises:
        AssertionError: Transition 未 APPLIED/ACTIVE 时抛出。
        RuntimeError: Schedule service/store typed failure 向调用者传播。
    """

    transition = harness.schedule_service.set_state(
        harness.scope,
        ScheduleActivationRequest(
            schedule_id=definition.id,
            expected_version=definition.version,
            target_state=ScheduleState.ACTIVE,
        ),
    )
    assert transition.action is ScheduleStateTransitionAction.APPLIED
    assert transition.observation.definition.state is ScheduleState.ACTIVE
    return transition.observation.definition


def _materialize(
    harness: _Harness,
    occurrence: ScheduleOccurrence,
) -> ScheduleMaterializationResult:
    """经真实 ScheduleService→JobService materialize occurrence。

    Args:
        harness: 提供真实 Schedule/Job services 的隔离句柄。
        occurrence: Pending occurrence。

    Returns:
        ENQUEUED materialization result。

    Raises:
        AssertionError: Result 未 ENQUEUED 或缺 receipt 时抛出。
        RuntimeError: Schedule/Job typed failure 向调用者传播。
    """

    result = harness.schedule_service.materialize_occurrence(
        harness.scope,
        occurrence.id,
    )
    assert result.action is ScheduleMaterializationResultAction.ENQUEUED
    assert result.enqueue_receipt is not None
    return result


def test_two_static_schedule_occurrences_create_distinct_jobs(
    source_job_harness: _Harness,
) -> None:
    """同一 static schedule 的两个 fire 必须 materialize 为不同 Job。

    Args:
        source_job_harness: 真实 ScheduleService→JobService/PostgreSQL 全链路。

    Returns:
        无。

    Raises:
        AssertionError: Occurrence、snapshot、Job identity 或行数不唯一时抛出。
    """

    request = _polling_request(source_job_harness, label="two-static-fires")
    draft = source_job_harness.facade.ensure_polling_schedule(
        source_job_harness.scope,
        request,
    )
    active = _activate_schedule(source_job_harness, draft)
    first_clock = active.next_fire_at
    assert first_clock is not None
    first_override = _ClockOverride(first_clock)
    clock_parameters: dict[str, _DbParam] = {"limit": 1}
    due_statement = (
        "WITH observed AS MATERIALIZED "
        "(SELECT clock_timestamp() AS database_now) "
        "SELECT schedule_id, database_now FROM observed LIMIT :limit"
    )
    rewritten_due, due_parameters = first_override.rewrite(
        due_statement,
        clock_parameters,
    )
    rewritten_alias, alias_parameters = first_override.rewrite(
        "SELECT clock_timestamp() AS database_now",
        clock_parameters,
    )
    rewritten_pair, pair_parameters = first_override.rewrite(
        "SELECT transaction_timestamp(), clock_timestamp()",
        clock_parameters,
    )
    assert rewritten_due.startswith("WITH observed AS MATERIALIZED")
    assert "AS database_now" in rewritten_due
    assert "SELECT schedule_id, database_now FROM observed" in rewritten_due
    assert rewritten_alias.endswith("AS database_now")
    assert rewritten_pair.count("TIMESTAMPTZ") == 2
    assert due_parameters is clock_parameters
    assert alias_parameters is clock_parameters
    assert pair_parameters is clock_parameters
    event.listen(
        source_job_harness.primary_engine,
        "before_cursor_execute",
        first_override,
        retval=True,
    )
    try:
        first_scan = source_job_harness.schedule_service.reserve_due_occurrences(
            source_job_harness.scope,
            None,
            limit=1,
        )
    finally:
        event.remove(
            source_job_harness.primary_engine,
            "before_cursor_execute",
            first_override,
        )
    assert first_scan.reservation is not None
    assert first_scan.reservation.action is ScheduleReserveAction.RESERVED
    assert len(first_scan.reservation.occurrences) == 1
    first_occurrence = first_scan.reservation.occurrences[0]

    first_observation = source_job_harness.schedules.get(
        source_job_harness.scope,
        active.id,
    )
    assert first_observation is not None
    advanced = first_observation.definition
    second_clock = advanced.next_fire_at
    assert second_clock is not None
    second_override = _ClockOverride(second_clock)
    event.listen(
        source_job_harness.primary_engine,
        "before_cursor_execute",
        second_override,
        retval=True,
    )
    try:
        second_scan = source_job_harness.schedule_service.reserve_due_occurrences(
            source_job_harness.scope,
            None,
            limit=1,
        )
    finally:
        event.remove(
            source_job_harness.primary_engine,
            "before_cursor_execute",
            second_override,
        )
    assert second_scan.reservation is not None
    assert second_scan.reservation.action is ScheduleReserveAction.RESERVED
    assert len(second_scan.reservation.occurrences) == 1
    second_occurrence = second_scan.reservation.occurrences[0]

    first = _materialize(source_job_harness, first_occurrence)
    second = _materialize(source_job_harness, second_occurrence)

    assert first_occurrence.id != second_occurrence.id
    assert first_occurrence.scheduled_for != second_occurrence.scheduled_for
    assert first_occurrence.snapshot is not None
    assert second_occurrence.snapshot is not None
    assert first_occurrence.snapshot.payload == second_occurrence.snapshot.payload
    assert first_occurrence.snapshot.idempotency_key == (
        f"schedule:{active.id}:{active.version}:{first_occurrence.scheduled_for.isoformat(timespec='microseconds')}"
    )
    assert second_occurrence.snapshot.idempotency_key == (
        f"schedule:{advanced.id}:{advanced.version}:"
        f"{second_occurrence.scheduled_for.isoformat(timespec='microseconds')}"
    )
    assert first_occurrence.snapshot.idempotency_key != second_occurrence.snapshot.idempotency_key
    assert first.enqueue_receipt is not None and second.enqueue_receipt is not None
    assert first.enqueue_receipt.job_id != second.enqueue_receipt.job_id
    assert first.enqueue_receipt.idempotency_reused is False
    assert second.enqueue_receipt.idempotency_reused is False
    assert _count(source_job_harness, "job_runs") == 2


def test_manual_trigger_reuses_same_job_only_for_same_subscription_trigger_and_payload(
    source_job_harness: _Harness,
) -> None:
    """Manual exact caller intent 重放复用，同 key 时间漂移冲突且新 trigger 新建。

    Args:
        source_job_harness: 真实 InvestmentSourcesService→JobService/Store 全链路。

    Returns:
        无。

    Raises:
        AssertionError: Reuse/conflict/distinct identity 或 row count 漂移时抛出。
    """

    request = _manual_request(source_job_harness, label="manual-reuse")
    first = source_job_harness.facade.enqueue_manual_sync(
        source_job_harness.scope,
        request,
    )
    replay = source_job_harness.facade.enqueue_manual_sync(
        source_job_harness.scope,
        request,
    )
    assert replay.job_id == first.job_id
    assert first.idempotency_reused is False
    assert replay.idempotency_reused is True

    drifted = SourceSyncEnqueueRequest(
        subscription_id=request.subscription_id,
        expected_subscription_version=request.expected_subscription_version,
        trigger_id=request.trigger_id,
        available_at=request.available_at,
        deadline_at=request.deadline_at + timedelta(seconds=1),
    )
    with pytest.raises(JobIdempotencyConflictError):
        source_job_harness.facade.enqueue_manual_sync(
            source_job_harness.scope,
            drifted,
        )
    distinct_request = SourceSyncEnqueueRequest(
        subscription_id=request.subscription_id,
        expected_subscription_version=request.expected_subscription_version,
        trigger_id=_stable_uuid("manual-reuse-distinct-trigger"),
        available_at=request.available_at,
        deadline_at=request.deadline_at,
    )
    distinct = source_job_harness.facade.enqueue_manual_sync(
        source_job_harness.scope,
        distinct_request,
    )
    assert distinct.job_id != first.job_id
    assert distinct.idempotency_reused is False

    second_company_id = CompanyId(str(_stable_uuid("manual-reuse-second-company")))
    second_security_id = SecurityId(str(_stable_uuid("manual-reuse-second-security")))
    second_subscription_id = SourceSubscriptionId(str(_stable_uuid("manual-reuse-second-subscription")))
    source_job_harness.identity.register_company_security(
        source_job_harness.scope,
        CompanySecurityRegistration(
            company=CompanyCreateRequest(
                company_id=second_company_id,
                legal_name="Item Six Second Corp",
                lei=None,
                country_code="US",
            ),
            security=SecurityCreateRequest(
                security_id=second_security_id,
                company_id=second_company_id,
                ticker="ITEM2",
                exchange_mic="XNYS",
                security_type=SecurityType.EQUITY,
                currency="USD",
                isin=None,
                is_active=True,
            ),
        ),
    )
    second_subscription = source_job_harness.identity.create_source_subscription(
        source_job_harness.scope,
        SourceSubscriptionCreateRequest(
            subscription_id=second_subscription_id,
            source_definition_id=source_job_harness.source_definition_id,
            company_id=None,
            security_id=second_security_id,
            status=SubscriptionStatus.ENABLED,
            config=_CONFIG,
        ),
    )
    second_request = SourceSyncEnqueueRequest(
        subscription_id=second_subscription_id,
        expected_subscription_version=second_subscription.version,
        trigger_id=request.trigger_id,
        available_at=request.available_at,
        deadline_at=request.deadline_at,
    )
    second_subscription_receipt = source_job_harness.facade.enqueue_manual_sync(
        source_job_harness.scope,
        second_request,
    )
    first_key = f"source-sync-trigger:v1:{request.subscription_id.value}:{request.trigger_id}"
    second_key = f"source-sync-trigger:v1:{second_request.subscription_id.value}:{second_request.trigger_id}"
    first_record = source_job_harness.jobs.get_by_idempotency_key(
        source_job_harness.scope,
        descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
        idempotency_key=first_key,
    )
    second_record = source_job_harness.jobs.get_by_idempotency_key(
        source_job_harness.scope,
        descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
        idempotency_key=second_key,
    )
    assert first_key != second_key
    assert second_subscription_receipt.job_id != first.job_id
    assert second_subscription_receipt.idempotency_reused is False
    assert first_record is not None and first_record.job_id == first.job_id
    assert second_record is not None
    assert second_record.job_id == second_subscription_receipt.job_id
    assert _count(source_job_harness, "job_runs") == 3


def test_manual_lookup_miss_converges_concurrently_through_ordinary_enqueue_unique_identity(
    source_job_harness: _Harness,
) -> None:
    """双 facade 同时 lookup miss 后只经 ordinary enqueue 唯一收敛。

    Args:
        source_job_harness: 两套独立 app engine/service/repository 全链路。

    Returns:
        无。

    Raises:
        AssertionError: 两个 writer 未收敛同 Job 或 reused matrix 漂移时抛出。
        threading.BrokenBarrierError: 任一 writer 未在有界时间抵达时传播。
    """

    barrier = Barrier(2)
    first_facade = InvestmentSourcesService(
        job_gateway=_BarrierJobGateway(source_job_harness.job_service, barrier),
        schedule_gateway=source_job_harness.schedule_service,
        source_repository=source_job_harness.repository,
    )
    second_facade = InvestmentSourcesService(
        job_gateway=_BarrierJobGateway(
            source_job_harness.second_job_service,
            barrier,
        ),
        schedule_gateway=source_job_harness.second_schedule_service,
        source_repository=source_job_harness.second_repository,
    )
    request = _manual_request(source_job_harness, label="manual-race")
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            first_facade.enqueue_manual_sync,
            source_job_harness.scope,
            request,
        )
        second_future = executor.submit(
            second_facade.enqueue_manual_sync,
            source_job_harness.scope,
            request,
        )
        receipts = (
            first_future.result(timeout=15),
            second_future.result(timeout=15),
        )
    assert receipts[0].job_id == receipts[1].job_id
    assert sorted(receipt.idempotency_reused for receipt in receipts) == [False, True]
    assert _count(source_job_harness, "job_runs") == 1
    assert (
        _count(
            source_job_harness,
            "job_events",
            predicate="event_type='job_created'",
        )
        == 1
    )


def test_cross_midnight_retry_never_moves_original_available_at_seeded_source_query_window(
    source_job_harness: _Harness,
) -> None:
    """跨 UTC 日界 retry 只移动 current available，不重写 Source query seed。

    Args:
        source_job_harness: 真实 Job fail/retry 与 Source takeover repositories。

    Returns:
        无。

    Raises:
        AssertionError: original/current、snapshot window 或 generation 漂移时抛出。
    """

    pg_now = _pg_clock(source_job_harness)
    original = pg_now.replace(hour=23, minute=59, second=59, microsecond=123456) - timedelta(days=1)
    first = _claimed_manual(
        source_job_harness,
        label="cross-midnight",
        available_at=original,
    )
    first_live = _acquire(source_job_harness, first)
    retry = _retry_claim(
        source_job_harness,
        first,
        worker="cross-midnight-retry",
        safe_error_code=SafeJobErrorCode.SOURCE_INTERRUPTED,
    )
    with source_job_harness.bootstrap_engine.connect() as connection:
        current_available, original_available = connection.execute(
            text(
                f"SELECT available_at, original_available_at FROM {_SCHEMA}.job_runs "
                "WHERE tenant_id=:tenant_id AND id=:job_id"
            ),
            {"tenant_id": _TENANT_ID.value, "job_id": first.claim.job_id},
        ).one()
        connection.rollback()
    assert isinstance(current_available, datetime)
    assert isinstance(original_available, datetime)
    current_utc = current_available.astimezone(timezone.utc)
    original_utc = original_available.astimezone(timezone.utc)
    assert original_utc == original
    assert current_utc != original_utc
    assert current_utc.date() > original_utc.date()

    takeover = _acquire(
        source_job_harness,
        retry,
        repository=source_job_harness.second_repository,
    )
    assert first_live.acquire.generation == 1
    assert takeover.acquire.generation == 2
    assert takeover.acquire.operation_id == first_live.acquire.operation_id
    assert takeover.acquire.execution_snapshot == first.snapshot
    assert takeover.acquire.execution_snapshot_sha256 == (
        build_source_execution_snapshot_document(first.snapshot).sha256
    )
    terminal = _record_terminal(
        source_job_harness,
        takeover,
        _no_change_candidate(),
        repository=source_job_harness.second_repository,
    )
    assert terminal.action is SourceTerminalRecordAction.RECORDED


@pytest.mark.asyncio
async def test_real_pg_middle_row_nowait_conflict_returns_bounded_retry_releases_job_lock_then_heartbeat_advances_and_takeover_commits_once(
    source_job_harness: _Harness,
) -> None:
    """Takeover 的中间 Source row NOWAIT 冲突回滚早期 Job locks 后可重试。

    Args:
        source_job_harness: 双 engine Job/Source repositories 与 bootstrap row lock。

    Returns:
        无。

    Raises:
        AssertionError: Failure、heartbeat、generation 或 exact-once terminal 漂移时抛出。
    """

    first = _claimed_manual(source_job_harness, label="middle-nowait")
    first_live = _acquire(source_job_harness, first)
    retry = _retry_claim(
        source_job_harness,
        first,
        worker="middle-nowait-takeover",
    )
    lock_connection = source_job_harness.bootstrap_engine.connect()
    lock_transaction = lock_connection.begin()
    blocker_released = False
    try:
        lock_connection.execute(
            text(
                f"SELECT id FROM {_SCHEMA}.source_definitions "
                "WHERE id=:definition_id FOR UPDATE"
            ),
            {
                "definition_id": UUID(source_job_harness.source_definition_id.value),
            },
        ).one()
        execution_task = asyncio.create_task(
            _execute_claim(
                source_job_harness,
                retry,
                service=source_job_harness.second_job_service,
            )
        )
        execution_done, execution_pending = await asyncio.wait(
            (execution_task,),
            timeout=10,
        )
        if execution_pending:
            lock_transaction.rollback()
            lock_connection.close()
            blocker_released = True
            await execution_task
            raise AssertionError("middle-row NOWAIT execution 未在有界时间返回")
        assert execution_done == {execution_task}
        failed = execution_task.result()
        assert isinstance(failed, JobFailure)
        assert failed.safe_error_code is SafeJobErrorCode.REPOSITORY_FAILURE
        assert failed.retryable is True
        heartbeat_override = _ClockOverride(
            retry.claim.lease.acquired_at + timedelta(microseconds=1)
        )
        event.listen(
            source_job_harness.secondary_engine,
            "before_cursor_execute",
            heartbeat_override,
            retval=True,
        )
        try:
            heartbeat_task = asyncio.create_task(
                asyncio.to_thread(
                    source_job_harness.second_jobs.heartbeat,
                    source_job_harness.scope,
                    retry.claim.lease,
                )
            )
            heartbeat_done, heartbeat_pending = await asyncio.wait(
                (heartbeat_task,),
                timeout=10,
            )
            if heartbeat_pending:
                lock_transaction.rollback()
                lock_connection.close()
                blocker_released = True
                await heartbeat_task
                raise AssertionError("middle-row NOWAIT 后 heartbeat 未在有界时间返回")
            assert heartbeat_done == {heartbeat_task}
            heartbeat = heartbeat_task.result()
        finally:
            event.remove(
                source_job_harness.secondary_engine,
                "before_cursor_execute",
                heartbeat_override,
            )
        assert heartbeat.claim.lease.expires_at > retry.claim.lease.expires_at
        assert (
            _operation_projection(
                source_job_harness,
                first.claim.job_id,
            )[1]
            == 1
        )
        assert _source_counts(source_job_harness) == (1, 0, 0, 0, 0)
    finally:
        if not blocker_released:
            lock_transaction.rollback()
            lock_connection.close()

    heartbeat_claimed = _ClaimedSourceJob(
        claim=heartbeat.claim,
        origin=retry.origin,
        snapshot=retry.snapshot,
    )
    completed = await _execute_claim(
        source_job_harness,
        heartbeat_claimed,
        service=source_job_harness.second_job_service,
    )
    assert isinstance(completed, JobCompletion)
    _complete_claim(source_job_harness, heartbeat_claimed, completed)
    operation = _operation_projection(source_job_harness, first.claim.job_id)
    assert operation[0] == "terminal"
    assert operation[1] == 2
    assert operation[2] == retry.claim.attempt_id
    assert first_live.acquire.operation_id is not None
    assert len(source_job_harness.connector.calls) == 1
    assert _source_counts(source_job_harness) == (1, 1, 1, 1, 0)


@pytest.mark.asyncio
async def test_terminal_nowait_conflict_after_point_of_no_return_rolls_back_all_terminal_rows_keeps_active_then_next_attempt_takes_over_once(
    source_job_harness: _Harness,
) -> None:
    """PONR 后中间锁冲突零 terminal DML，下一 attempt takeover exact-once。

    Args:
        source_job_harness: 双 engine、provider barrier 与 bootstrap row lock。

    Returns:
        无。

    Raises:
        AssertionError: PONR failure、ACTIVE audit 或 takeover terminal 漂移时抛出。
        asyncio.TimeoutError: Provider/task 未在有界时间收敛时传播。
    """

    claimed = _claimed_manual(source_job_harness, label="terminal-nowait")
    entered = asyncio.Event()
    release = asyncio.Event()
    source_job_harness.connector.configure(entered=entered, release=release)
    task = asyncio.create_task(_execute_claim(source_job_harness, claimed))
    lock_connection = source_job_harness.bootstrap_engine.connect()
    lock_transaction = lock_connection.begin()
    blocker_released = False
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        lock_connection.execute(
            text(
                f"SELECT id FROM {_SCHEMA}.source_definitions "
                "WHERE id=:definition_id FOR UPDATE"
            ),
            {
                "definition_id": UUID(source_job_harness.source_definition_id.value),
            },
        ).one()
        release.set()
        terminal_done, terminal_pending = await asyncio.wait(
            (task,),
            timeout=10,
        )
        if terminal_pending:
            lock_transaction.rollback()
            lock_connection.close()
            blocker_released = True
            await task
            raise AssertionError("terminal NOWAIT execution 未在有界时间返回")
        assert terminal_done == {task}
        failed = task.result()
        assert isinstance(failed, JobFailure)
        assert failed.safe_error_code is SafeJobErrorCode.REPOSITORY_FAILURE
        assert failed.retryable is True
        operation = _operation_projection(source_job_harness, claimed.claim.job_id)
        assert operation[0] == "active"
        assert operation[1] == 1
        assert _source_counts(source_job_harness) == (1, 0, 0, 0, 0)
    finally:
        release.set()
        if not blocker_released:
            lock_transaction.rollback()
            lock_connection.close()
        if not task.done():
            await task
        source_job_harness.connector.reset_observation()

    retry = _retry_claim(
        source_job_harness,
        claimed,
        worker="terminal-nowait-takeover",
    )
    completed = await _execute_claim(
        source_job_harness,
        retry,
        service=source_job_harness.second_job_service,
    )
    assert isinstance(completed, JobCompletion)
    _complete_claim(source_job_harness, retry, completed)
    operation = _operation_projection(source_job_harness, claimed.claim.job_id)
    assert operation[0] == "terminal"
    assert operation[1] == 2
    assert _source_counts(source_job_harness) == (1, 1, 1, 1, 0)


@pytest.mark.asyncio
async def test_same_attempt_duplicate_is_busy_and_never_enters_fins_twice(
    source_job_harness: _Harness,
) -> None:
    """同 attempt 并发 duplicate 只返回 busy，provider 仍恰好一次。

    Args:
        source_job_harness: 真实 execution service 与可控 provider barrier。

    Returns:
        无。

    Raises:
        AssertionError: Duplicate 未 busy、provider 重入或 terminal 漂移时抛出。
        asyncio.TimeoutError: Provider/task 未在有界时间收敛时传播。
    """

    claimed = _claimed_manual(source_job_harness, label="same-attempt-busy")
    entered = asyncio.Event()
    release = asyncio.Event()
    source_job_harness.connector.configure(entered=entered, release=release)
    owner_task = asyncio.create_task(_execute_claim(source_job_harness, claimed))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        duplicate = await _execute_claim(
            source_job_harness,
            claimed,
            service=source_job_harness.second_job_service,
        )
        assert isinstance(duplicate, JobFailure)
        assert duplicate.safe_error_code is SafeJobErrorCode.SOURCE_OPERATION_BUSY
        assert duplicate.retryable is True
        assert len(source_job_harness.connector.calls) == 1
        release.set()
        owner = await asyncio.wait_for(owner_task, timeout=10)
    finally:
        release.set()
        if not owner_task.done():
            await asyncio.wait_for(owner_task, timeout=10)
        source_job_harness.connector.reset_observation()
    assert isinstance(owner, JobCompletion)
    _complete_claim(source_job_harness, claimed, owner)
    assert _source_counts(source_job_harness) == (1, 1, 1, 1, 0)


def _completion_result(completion: JobCompletion) -> SourceSyncResult:
    """Strict parse 一个 Source Job completion result。

    Args:
        completion: Execution service 返回的 canonical completion。

    Returns:
        Parsed Source result DTO。

    Raises:
        TypeError: Canonical wrapper 类型非法时传播。
        ValueError: Result schema/bytes/hash 不闭合时传播。
    """

    return parse_source_sync_result(completion.result)


@pytest.mark.asyncio
async def test_terminal_replay_returns_byte_identical_job_result_without_new_run_health_or_outbox(
    source_job_harness: _Harness,
) -> None:
    """同一 attempt 的 terminal replay 返回相同 bytes 且零新 Source facts。

    Args:
        source_job_harness: 真实 execution/source repositories 与 Job lease。

    Returns:
        无。

    Raises:
        AssertionError: Replay bytes、provider calls 或 durable counts 漂移时抛出。
    """

    claimed = _claimed_manual(source_job_harness, label="terminal-replay")
    first = await _execute_claim(source_job_harness, claimed)
    assert isinstance(first, JobCompletion)
    first_counts = _source_counts(source_job_harness)
    persisted_sha256 = _source_result_sha256(
        source_job_harness,
        claimed.claim.job_id,
    )
    replay = await _execute_claim(
        source_job_harness,
        claimed,
        service=source_job_harness.second_job_service,
    )
    assert isinstance(replay, JobCompletion)
    assert replay.result == first.result
    assert replay.result.sha256 == persisted_sha256
    assert replay.result.sha256 == first.result.sha256
    assert _completion_result(replay) == _completion_result(first)
    assert len(source_job_harness.connector.calls) == 1
    assert _source_counts(source_job_harness) == first_counts
    _complete_claim(source_job_harness, claimed, replay)


@pytest.mark.asyncio
async def test_crash_after_source_terminal_before_job_complete_replays_when_next_attempt_exists(
    source_job_harness: _Harness,
) -> None:
    """Source commit 后模拟进程 crash，真实 lease recovery 的下一 attempt 只 replay。

    Args:
        source_job_harness: 真实 Source terminal、Job recovery 与第二 execution stack。

    Returns:
        无。

    Raises:
        AssertionError: Recovery、replay bytes、provider count 或 Source facts 漂移时抛出。
    """

    first_claim = _claimed_manual(source_job_harness, label="crash-replay")
    first = await _execute_claim(source_job_harness, first_claim)
    assert isinstance(first, JobCompletion)
    counts_after_commit = _source_counts(source_job_harness)
    recovery, retry = _recover_expired_claim(
        source_job_harness,
        first_claim,
        worker="crash-replay-next-attempt",
    )
    assert recovery.job_state is JobState.READY
    assert recovery.attempt_state is AttemptState.ABANDONED
    assert retry is not None
    replay = await _execute_claim(
        source_job_harness,
        retry,
        service=source_job_harness.second_job_service,
    )
    assert isinstance(replay, JobCompletion)
    assert replay.result == first.result
    assert replay.result.sha256 == _source_result_sha256(
        source_job_harness,
        first_claim.claim.job_id,
    )
    assert len(source_job_harness.connector.calls) == 1
    assert _source_counts(source_job_harness) == counts_after_commit
    _complete_claim(source_job_harness, retry, replay)
    assert _job_state(source_job_harness, retry.claim.job_id) is JobState.SUCCEEDED


@pytest.mark.asyncio
async def test_last_attempt_crash_preserves_source_truth_when_job_envelope_expires_without_replay(
    source_job_harness: _Harness,
) -> None:
    """最后 attempt 的 Source commit 后 crash 使 Job 终结但不删除 Source truth。

    Args:
        source_job_harness: 真实三 attempt lease recovery 与 Source terminal repositories。

    Returns:
        无。

    Raises:
        AssertionError: Attempt 数、final recovery、Job state 或 Source truth 漂移时抛出。
    """

    first = _claimed_manual(source_job_harness, label="last-attempt-crash")
    first_recovery, second = _recover_expired_claim(
        source_job_harness,
        first,
        worker="last-attempt-second",
    )
    assert first_recovery.job_state is JobState.READY
    assert second is not None
    second_recovery, third = _recover_expired_claim(
        source_job_harness,
        second,
        worker="last-attempt-third",
    )
    assert second_recovery.job_state is JobState.READY
    assert third is not None and third.claim.attempt_number == 3
    completion = await _execute_claim(
        source_job_harness,
        third,
        service=source_job_harness.second_job_service,
    )
    assert isinstance(completion, JobCompletion)
    source_truth = _source_result_sha256(source_job_harness, third.claim.job_id)
    source_counts = _source_counts(source_job_harness)
    final_recovery, no_fourth = _recover_expired_claim(
        source_job_harness,
        third,
        worker="forbidden-fourth",
    )
    assert no_fourth is None
    assert final_recovery.job_state is JobState.FAILED
    assert final_recovery.attempt_state is AttemptState.ABANDONED
    assert final_recovery.safe_error_code is SafeJobErrorCode.RETRY_EXHAUSTED
    assert _job_state(source_job_harness, third.claim.job_id) is JobState.FAILED
    assert _attempt_states(source_job_harness, third.claim.job_id) == (
        AttemptState.ABANDONED,
        AttemptState.ABANDONED,
        AttemptState.ABANDONED,
    )
    assert _source_result_sha256(source_job_harness, third.claim.job_id) == source_truth
    assert _source_counts(source_job_harness) == source_counts
    assert len(source_job_harness.connector.calls) == 1


def test_job_terminal_without_source_commit_keeps_physical_active_audit_without_public_projection_or_false_source_terminal(
    source_job_harness: _Harness,
) -> None:
    """Job 终结但 Source 未 commit 时保留 ACTIVE audit，且无 receipt/run 假象。

    Args:
        source_job_harness: 真实 Job cancel/fail 与 Source acquire repositories。

    Returns:
        无。

    Raises:
        AssertionError: Job terminal、ACTIVE operation 或零 Source projection 漂移时抛出。
    """

    claimed = _claimed_manual(source_job_harness, label="job-terminal-active-audit")
    live = _acquire(source_job_harness, claimed)
    cancel = source_job_harness.jobs.cancel(
        source_job_harness.scope,
        JobCancellationRequest(
            job_id=claimed.claim.job_id,
            reason="operator",
        ),
    )
    assert cancel.job_state is JobState.CANCEL_REQUESTED
    terminal = source_job_harness.jobs.fail(
        source_job_harness.scope,
        claimed.claim.lease,
        JobFailure(
            safe_error_code=SafeJobErrorCode.SOURCE_INTERRUPTED,
            retryable=True,
        ),
    )
    assert terminal.job_state is JobState.CANCELLED
    assert _job_state(source_job_harness, claimed.claim.job_id) is JobState.CANCELLED
    assert _operation_projection(source_job_harness, claimed.claim.job_id)[0] == "active"
    assert (
        source_job_harness.repository.get_source_receipt(
            source_job_harness.scope,
            live.acquire.operation_id,
        )
        is None
    )
    assert _source_counts(source_job_harness) == (1, 0, 0, 0, 0)


@pytest.mark.asyncio
async def test_disabled_subscription_or_health_records_skipped_completion_without_fins_or_health_change(
    source_job_harness: _Harness,
) -> None:
    """Scheduled subscription-disabled 与 health-disabled 均记录 skipped、零 provider/health 变化。

    Args:
        source_job_harness: 真实 scheduled/manual Jobs、identity、health 与 execution stack。

    Returns:
        无。

    Raises:
        AssertionError: Outcome、provider、health 或 Source counts 漂移时抛出。
    """

    scheduled = _claimed_scheduled(
        source_job_harness,
        label="subscription-disabled",
    )
    _set_subscription(
        source_job_harness,
        status=SubscriptionStatus.DISABLED,
    )
    subscription_disabled = await _execute_claim(source_job_harness, scheduled)
    assert isinstance(subscription_disabled, JobCompletion)
    assert _completion_result(subscription_disabled).outcome is SourceSyncOutcome.SKIPPED_DISABLED
    assert len(source_job_harness.connector.calls) == 0
    assert (
        source_job_harness.repository.get_health(
            source_job_harness.scope,
            source_job_harness.subscription_id,
        ).version
        == 0
    )

    _set_subscription(
        source_job_harness,
        status=SubscriptionStatus.ENABLED,
    )
    health_target = _claimed_manual(
        source_job_harness,
        label="health-disabled-target",
    )
    disabled_health = _seed_disabled_health(source_job_harness)
    before_target = _source_counts(source_job_harness)
    health_disabled = await _execute_claim(source_job_harness, health_target)
    assert isinstance(health_disabled, JobCompletion)
    assert _completion_result(health_disabled).outcome is SourceSyncOutcome.SKIPPED_DISABLED
    after_target = _source_counts(source_job_harness)
    assert after_target == (
        before_target[0] + 1,
        before_target[1] + 1,
        before_target[2],
        before_target[3],
        before_target[4],
    )
    health_after = source_job_harness.repository.get_health(
        source_job_harness.scope,
        source_job_harness.subscription_id,
    )
    assert health_after == disabled_health
    assert len(source_job_harness.connector.calls) == 0


def test_disabled_acquire_then_operator_reenable_still_records_stored_disabled_disposition_without_fins(
    source_job_harness: _Harness,
) -> None:
    """Acquire 冻结 DISABLED 后 operator re-enable 不改写 owner disposition。

    Args:
        source_job_harness: 真实 health transition、Source acquire/terminal repositories。

    Returns:
        无。

    Raises:
        AssertionError: Stored disposition、reenable、terminal outcome 或 provider 漂移时抛出。
    """

    target = _claimed_manual(
        source_job_harness,
        label="disabled-then-reenable-target",
    )
    disabled = _seed_disabled_health(source_job_harness)
    live = _acquire(source_job_harness, target)
    assert live.acquire.binding_disposition is SourceBindingDisposition.DISABLED
    operation_before = _operation_projection(
        source_job_harness,
        target.claim.job_id,
    )
    assert operation_before[3] == SourceBindingDisposition.DISABLED.value
    reenabled = source_job_harness.second_facade.reenable_source_health(
        source_job_harness.scope,
        SourceHealthReenableRequest(
            subscription_id=source_job_harness.subscription_id,
            expected_health_version=disabled.version,
        ),
    )
    assert reenabled.status is SourceHealthStatus.HEALTHY
    terminal = _record_terminal(
        source_job_harness,
        live,
        SourceNoProviderTerminalCandidate(reason=SourceNoProviderReason.DISABLED),
        repository=source_job_harness.second_repository,
    )
    assert terminal.action is SourceTerminalRecordAction.RECORDED
    assert terminal.receipt is not None
    assert terminal.receipt.outcome is SourceSyncOutcome.SKIPPED_DISABLED
    assert terminal.health_after == reenabled
    assert terminal.health_snapshot is None
    assert terminal.alert_event is None
    operation_after = _operation_projection(
        source_job_harness,
        target.claim.job_id,
    )
    assert operation_after[3] == SourceBindingDisposition.DISABLED.value
    assert len(source_job_harness.connector.calls) == 0


@pytest.mark.asyncio
async def test_binding_drift_before_acquire_records_typed_stale_without_fins_or_health_change(
    source_job_harness: _Harness,
) -> None:
    """Manual frozen binding 在 acquire 前漂移时记录 typed stale，零 provider/health 变化。

    Args:
        source_job_harness: 真实 manual Job、Identity CAS 与 execution stack。

    Returns:
        无。

    Raises:
        AssertionError: Disposition、outcome、provider 或 health facts 漂移时抛出。
    """

    claimed = _claimed_manual(source_job_harness, label="binding-drift-before-acquire")
    drifted_config = dict(_CONFIG)
    drifted_config["lookback_days"] = 4
    _set_subscription(
        source_job_harness,
        status=SubscriptionStatus.ENABLED,
        config=drifted_config,
    )
    before = _source_counts(source_job_harness)
    completion = await _execute_claim(source_job_harness, claimed)
    assert isinstance(completion, JobCompletion)
    result = _completion_result(completion)
    assert result.outcome is SourceSyncOutcome.STALE_SUBSCRIPTION
    operation = _operation_projection(source_job_harness, claimed.claim.job_id)
    assert operation[3] == SourceBindingDisposition.STALE.value
    assert len(source_job_harness.connector.calls) == 0
    after = _source_counts(source_job_harness)
    assert after == (before[0] + 1, before[1] + 1, 0, 0, 0)
    assert (
        source_job_harness.repository.get_health(
            source_job_harness.scope,
            source_job_harness.subscription_id,
        ).version
        == 0
    )


@pytest.mark.asyncio
async def test_scheduled_acquire_freezes_locked_current_binding_and_disabled_is_typed_no_provider(
    source_job_harness: _Harness,
) -> None:
    """Scheduled acquire 以 locked current binding/original seed 冻结 snapshot，health-disabled 零 provider。

    Args:
        source_job_harness: 真实 scheduled Job、health transitions 与 execution stack。

    Returns:
        无。

    Raises:
        AssertionError: Snapshot bytes/disposition/outcome/provider 或 health 变化时抛出。
    """

    original = _pg_clock(source_job_harness) - timedelta(minutes=2)
    target = _claimed_scheduled(
        source_job_harness,
        label="scheduled-disabled-current-binding",
        available_at=original,
    )
    disabled = _seed_disabled_health(source_job_harness)
    before = _source_counts(source_job_harness)
    completion = await _execute_claim(source_job_harness, target)
    assert isinstance(completion, JobCompletion)
    assert _completion_result(completion).outcome is SourceSyncOutcome.SKIPPED_DISABLED
    operation = _operation_projection(source_job_harness, target.claim.job_id)
    expected_document = build_source_execution_snapshot_document(target.snapshot)
    assert operation[3] == SourceBindingDisposition.DISABLED.value
    assert operation[4] == expected_document.sha256
    assert target.snapshot.query_end_date == original.date()
    assert len(source_job_harness.connector.calls) == 0
    after = _source_counts(source_job_harness)
    assert after == (
        before[0] + 1,
        before[1] + 1,
        before[2],
        before[3],
        before[4],
    )
    assert (
        source_job_harness.repository.get_health(
            source_job_harness.scope,
            source_job_harness.subscription_id,
        )
        == disabled
    )


@pytest.mark.asyncio
async def test_scheduled_takeover_binding_drift_is_typed_stale_without_overwriting_snapshot_or_calling_fins(
    source_job_harness: _Harness,
) -> None:
    """Scheduled generation 2 binding drift 只改 disposition，不覆盖 generation 1 snapshot。

    Args:
        source_job_harness: 真实 scheduled Job retry/takeover 与 Identity CAS。

    Returns:
        无。

    Raises:
        AssertionError: Generation、snapshot、stale outcome 或 provider count 漂移时抛出。
    """

    first = _claimed_scheduled(
        source_job_harness,
        label="scheduled-takeover-drift",
    )
    first_live = _acquire(source_job_harness, first)
    before = _operation_projection(source_job_harness, first.claim.job_id)
    retry = _retry_claim(
        source_job_harness,
        first,
        worker="scheduled-drift-takeover",
    )
    drifted_config = dict(_CONFIG)
    drifted_config["max_documents_per_sync"] = 49
    _set_subscription(
        source_job_harness,
        status=SubscriptionStatus.ENABLED,
        config=drifted_config,
    )
    completion = await _execute_claim(
        source_job_harness,
        retry,
        service=source_job_harness.second_job_service,
    )
    assert isinstance(completion, JobCompletion)
    assert _completion_result(completion).outcome is SourceSyncOutcome.STALE_SUBSCRIPTION
    after = _operation_projection(source_job_harness, first.claim.job_id)
    assert first_live.acquire.generation == 1
    assert after[0] == "terminal"
    assert after[1] == 2
    assert after[2] == retry.claim.attempt_id
    assert after[3] == SourceBindingDisposition.STALE.value
    assert after[4] == before[4]
    assert len(source_job_harness.connector.calls) == 0
    assert _source_counts(source_job_harness) == (1, 1, 0, 0, 0)


@pytest.mark.asyncio
async def test_disable_during_fins_discards_provider_result_as_stale_without_health_change(
    source_job_harness: _Harness,
) -> None:
    """Provider 执行期间 disable subscription 时丢弃结果并记录 stale。

    Args:
        source_job_harness: 真实 execution/terminal revalidation 与 provider barrier。

    Returns:
        无。

    Raises:
        AssertionError: Outcome、provider count、health 或 operation state 漂移时抛出。
        asyncio.TimeoutError: Provider/task 未在有界时间收敛时传播。
    """

    claimed = _claimed_manual(source_job_harness, label="disable-during-fins")
    entered = asyncio.Event()
    release = asyncio.Event()
    source_job_harness.connector.configure(entered=entered, release=release)
    task = asyncio.create_task(_execute_claim(source_job_harness, claimed))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        _set_subscription(
            source_job_harness,
            status=SubscriptionStatus.DISABLED,
        )
        release.set()
        completion = await asyncio.wait_for(task, timeout=10)
    finally:
        release.set()
        if not task.done():
            await asyncio.wait_for(task, timeout=10)
        source_job_harness.connector.entered = None
        source_job_harness.connector.release = None
    assert isinstance(completion, JobCompletion)
    assert _completion_result(completion).outcome is SourceSyncOutcome.STALE_SUBSCRIPTION
    assert len(source_job_harness.connector.calls) == 1
    assert _operation_projection(source_job_harness, claimed.claim.job_id)[0] == "terminal"
    assert _source_counts(source_job_harness) == (1, 1, 0, 0, 0)
    assert (
        source_job_harness.repository.get_health(
            source_job_harness.scope,
            source_job_harness.subscription_id,
        ).version
        == 0
    )


@pytest.mark.asyncio
async def test_job_cancel_or_deadline_after_fins_before_source_commit_writes_zero_source_observation(
    source_job_harness: _Harness,
) -> None:
    """Provider 后 Job cancel 或 authoritative deadline 均拒绝 Source observation。

    Args:
        source_job_harness: 真实 Job cancel/deadline、Source terminal 与 provider barriers。

    Returns:
        无。

    Raises:
        AssertionError: Failure code、ACTIVE audits 或零 run/health/outbox 漂移时抛出。
        asyncio.TimeoutError: Provider/task 未在有界时间收敛时传播。
    """

    cancel_claim = _claimed_manual(source_job_harness, label="cancel-after-fins")
    cancel_entered = asyncio.Event()
    cancel_release = asyncio.Event()
    source_job_harness.connector.configure(
        entered=cancel_entered,
        release=cancel_release,
    )
    cancel_task = asyncio.create_task(_execute_claim(source_job_harness, cancel_claim))
    try:
        await asyncio.wait_for(cancel_entered.wait(), timeout=10)
        cancel_result = source_job_harness.jobs.cancel(
            source_job_harness.scope,
            JobCancellationRequest(
                job_id=cancel_claim.claim.job_id,
                reason="operator",
            ),
        )
        assert cancel_result.job_state is JobState.CANCEL_REQUESTED
        cancel_release.set()
        cancelled = await asyncio.wait_for(cancel_task, timeout=10)
    finally:
        cancel_release.set()
        if not cancel_task.done():
            await asyncio.wait_for(cancel_task, timeout=10)
        source_job_harness.connector.reset_observation()
    assert isinstance(cancelled, JobFailure)
    assert cancelled.safe_error_code is SafeJobErrorCode.SOURCE_INTERRUPTED
    assert (
        _operation_projection(
            source_job_harness,
            cancel_claim.claim.job_id,
        )[0]
        == "active"
    )

    deadline_claim = _claimed_manual(source_job_harness, label="deadline-after-fins")
    deadline_entered = asyncio.Event()
    deadline_release = asyncio.Event()
    source_job_harness.connector.configure(
        entered=deadline_entered,
        release=deadline_release,
    )
    deadline_task = asyncio.create_task(_execute_claim(source_job_harness, deadline_claim))
    deadline_override = _ClockOverride(deadline_claim.claim.deadline_at + timedelta(seconds=1))
    listener_installed = False
    try:
        await asyncio.wait_for(deadline_entered.wait(), timeout=10)
        event.listen(
            source_job_harness.primary_engine,
            "before_cursor_execute",
            deadline_override,
            retval=True,
        )
        listener_installed = True
        deadline_release.set()
        deadline = await asyncio.wait_for(deadline_task, timeout=10)
    finally:
        deadline_release.set()
        if not deadline_task.done():
            await asyncio.wait_for(deadline_task, timeout=10)
        if listener_installed:
            event.remove(
                source_job_harness.primary_engine,
                "before_cursor_execute",
                deadline_override,
            )
        source_job_harness.connector.entered = None
        source_job_harness.connector.release = None
    assert isinstance(deadline, JobFailure)
    assert deadline.safe_error_code is SafeJobErrorCode.SOURCE_INTERRUPTED
    assert (
        _operation_projection(
            source_job_harness,
            deadline_claim.claim.job_id,
        )[0]
        == "active"
    )
    assert _source_counts(source_job_harness) == (2, 0, 0, 0, 0)
    assert len(source_job_harness.connector.calls) == 1


@pytest.mark.asyncio
async def test_completion_after_source_commit_cancel_gate_keeps_source_truth_and_rejects_job_handler_result(
    source_job_harness: _Harness,
) -> None:
    """Source commit 后 JobService cancellation 后置 gate 只拒绝 envelope result。

    Args:
        source_job_harness: 真实 execution/source commit 与 JobService post-handler gate。

    Returns:
        无。

    Raises:
        AssertionError: Handler rejection、Source truth 或 Job terminal 漂移时抛出。
    """

    claimed = _claimed_manual(source_job_harness, label="post-source-cancel-gate")
    cancellation = _CancellationSignal(responses=(False, True))
    rejected = await _execute_claim(
        source_job_harness,
        claimed,
        cancellation,
    )
    assert isinstance(rejected, JobFailure)
    assert rejected.safe_error_code is SafeJobErrorCode.HANDLER_REJECTED
    assert rejected.retryable is False
    assert cancellation.read_calls == 2
    assert len(source_job_harness.connector.calls) == 1
    source_truth = _source_result_sha256(source_job_harness, claimed.claim.job_id)
    source_counts = _source_counts(source_job_harness)
    assert source_counts == (1, 1, 1, 1, 0)
    terminal = source_job_harness.jobs.fail(
        source_job_harness.scope,
        claimed.claim.lease,
        rejected,
    )
    assert terminal.job_state is JobState.FAILED
    assert _job_state(source_job_harness, claimed.claim.job_id) is JobState.FAILED
    assert _source_result_sha256(source_job_harness, claimed.claim.job_id) == source_truth
    assert _source_counts(source_job_harness) == source_counts
