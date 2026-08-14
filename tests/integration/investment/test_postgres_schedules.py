"""PostgresScheduleStore 的真实 PostgreSQL 16 集成测试。

本文件只验证 Slice 2.2 storage 边界：tenant/CAS、PG clock activation、
schedule->occurrence 锁序、durable occurrence outbox、bounded due/replay
cursor，以及 MATERIALIZING committed semantics。Service cron/availability
编排与 Host drain 由各自测试 owner 覆盖。
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from dayu.investment.domain.identifiers import Principal, TenantId
from dayu.investment.domain.jobs import (
    CanonicalJobDocument,
    JobEnqueueRequest,
    JobHandlerDescriptor,
    build_canonical_document,
    job_enqueue_request_fingerprint,
)
from dayu.investment.domain.schedules import (
    CanonicalScheduleEnqueueSnapshot,
    ScheduleActivationRequest,
    ScheduleDefinition,
    ScheduleDueCursor,
    ScheduleInputError,
    ScheduleInvariantError,
    ScheduleMarkEnqueuedAction,
    ScheduleMaterializationAction,
    ScheduleMaterializationAdmission,
    ScheduleMisfirePolicy,
    ScheduleOccurrence,
    ScheduleOccurrenceReservation,
    ScheduleOccurrenceState,
    ScheduleRegistrationRequest,
    ScheduleReplayCursor,
    ScheduleRepositoryError,
    ScheduleReservationBatch,
    ScheduleReservationResult,
    ScheduleReserveAction,
    ScheduleSkipReason,
    ScheduleState,
    ScheduleStateTransitionAction,
    ScheduleVersionConflictError,
)
from dayu.investment.storage import postgres_schedules as postgres_schedules_storage
from dayu.investment.storage.db import (
    PLATFORM_SCHEMA_NAME,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage.postgres_jobs import PostgresJobStore
from dayu.investment.storage.postgres_schedules import PostgresScheduleStore
from tests.integration.investment.conftest import (
    PlatformCluster,
    create_temporary_login,
    drop_temporary_login,
    run_alembic_downgrade,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration

_SCHEMA = PLATFORM_SCHEMA_NAME
_TENANT_A = TenantId("00000000-0000-0000-0000-000000000001")
_TENANT_B = TenantId("00000000-0000-0000-0000-000000000002")
_SCOPE_A = Principal(tenant_id=_TENANT_A, user_id="schedule-a").to_scope()
_SCOPE_B = Principal(tenant_id=_TENANT_B, user_id="schedule-b").to_scope()

_LARGE_BACKLOG_SIZE = 512
"""bounded-query 真实 PG 回归使用的宽行 backlog 数量。"""

_QUERY_PAGE_LIMIT = 5
"""bounded-query 回归使用的小 page limit。"""

_DbParam = str | int | datetime | UUID | bytes | None


@dataclass(frozen=True, slots=True)
class ScheduleHarness:
    """两个独立 schedule engine 与各自同租户 JobStore。

    Args:
        primary: 主要 schedule store。
        secondary: 独立 engine 的并发 schedule store。
        jobs: 用于验证 occurrence->job FK/mark 的 JobStore。
        secondary_jobs: 第二独立 engine 的并发 JobStore。
    """

    primary: PostgresScheduleStore
    secondary: PostgresScheduleStore
    jobs: PostgresJobStore
    secondary_jobs: PostgresJobStore


@dataclass(frozen=True, slots=True)
class _MaterializationRaceOutcome:
    """一个 scheduler writer 完整 materialization 的闭合结果。

    Args:
        begin_action: occurrence begin 的持久化决策。
        job_id: 幂等 enqueue 收敛后的 job UUID。
        idempotency_reused: 当前 writer 是否复用了既有 job。
        mark_action: occurrence mark 的持久化决策。
    """

    begin_action: ScheduleMaterializationAction
    job_id: UUID
    idempotency_reused: bool
    mark_action: ScheduleMarkEnqueuedAction


@pytest.fixture()
def schedule_db(
    platform_cluster: PlatformCluster,
    lifecycle_database: Callable[[], str],
) -> Iterator[tuple[PlatformCluster, str]]:
    """创建 head schema 的独立数据库并在结束时安全降级。

    Args:
        platform_cluster: session 级真实 PostgreSQL 16 cluster。
        lifecycle_database: 独立数据库工厂。

    Yields:
        ``(cluster, database)``。

    Raises:
        无。
    """

    database = lifecycle_database()
    dsn = platform_cluster.dsn_for_database(database, "postgres")
    run_alembic_upgrade(dsn)
    try:
        yield platform_cluster, database
    finally:
        # 0004/0006 downgrade 按设计拒绝业务行；只在本测试独立数据库
        # 内按 FK 顺序清理 schedule、source 与 job descendants，再执行
        # 正式 downgrade。
        engine = create_platform_engine(dsn)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(f"DELETE FROM {_SCHEMA}.source_health_alert_outbox")
                )
                connection.execute(text(f"DELETE FROM {_SCHEMA}.source_health_states"))
                connection.execute(text(f"DELETE FROM {_SCHEMA}.source_sync_operations"))
                connection.execute(
                    text(f"DELETE FROM {_SCHEMA}.source_health_snapshots")
                )
                connection.execute(text(f"DELETE FROM {_SCHEMA}.source_sync_runs"))
                connection.execute(
                    text(f"DELETE FROM {_SCHEMA}.job_schedule_occurrences")
                )
                connection.execute(
                    text(f"DELETE FROM {_SCHEMA}.agent_run_correlations")
                )
                connection.execute(text(f"DELETE FROM {_SCHEMA}.job_events"))
                connection.execute(
                    text(f"DELETE FROM {_SCHEMA}.job_attempt_receipts")
                )
                connection.execute(text(f"DELETE FROM {_SCHEMA}.job_leases"))
                connection.execute(text(f"DELETE FROM {_SCHEMA}.job_attempts"))
                connection.execute(text(f"DELETE FROM {_SCHEMA}.job_runs"))
                connection.execute(text(f"DELETE FROM {_SCHEMA}.job_schedules"))
        finally:
            engine.dispose()
        run_alembic_downgrade(dsn)


@pytest.fixture()
def harness(
    schedule_db: tuple[PlatformCluster, str],
) -> Iterator[ScheduleHarness]:
    """构造两个独立 app engine 与 store 集合。

    Args:
        schedule_db: 已迁移独立数据库。

    Yields:
        ``ScheduleHarness``。

    Raises:
        无。
    """

    cluster, database = schedule_db
    primary_login = create_temporary_login(
        cluster,
        database,
        member_of="dayu_platform_app",
    )
    secondary_login = create_temporary_login(
        cluster,
        database,
        member_of="dayu_platform_app",
    )
    primary_engine = create_platform_engine(primary_login.dsn)
    secondary_engine = create_platform_engine(secondary_login.dsn)
    primary_factory: sessionmaker[Session] = create_platform_session_factory(
        primary_engine
    )
    secondary_factory: sessionmaker[Session] = create_platform_session_factory(
        secondary_engine
    )
    try:
        yield ScheduleHarness(
            primary=PostgresScheduleStore(primary_factory),
            secondary=PostgresScheduleStore(secondary_factory),
            jobs=PostgresJobStore(primary_factory),
            secondary_jobs=PostgresJobStore(secondary_factory),
        )
    finally:
        primary_engine.dispose()
        secondary_engine.dispose()
        drop_temporary_login(cluster, secondary_login)
        drop_temporary_login(cluster, primary_login)


def _descriptor(*, job_type: str = "test.schedule") -> JobHandlerDescriptor:
    """构造固定测试 descriptor。

    Args:
        job_type: job type 标识。

    Returns:
        合法 ``JobHandlerDescriptor``。

    Raises:
        无。
    """

    return JobHandlerDescriptor(
        job_type=job_type,
        payload_schema_name="test.schedule.payload",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=60,
    )


def _payload(*, marker: str = "p") -> CanonicalJobDocument:
    """构造 canonical schedule payload。

    Args:
        marker: payload 区分标记。

    Returns:
        canonical document。

    Raises:
        无。
    """

    return build_canonical_document(
        {"marker": marker},
        schema_name="test.schedule.payload",
        schema_version=1,
    )


def _registration(*, key: str, marker: str = "p") -> ScheduleRegistrationRequest:
    """构造 schedule 注册请求。

    Args:
        key: tenant 内 schedule key。
        marker: payload 区分标记。

    Returns:
        disabled draft 注册请求。

    Raises:
        无。
    """

    return ScheduleRegistrationRequest(
        schedule_key=key,
        descriptor=_descriptor(),
        payload=_payload(marker=marker),
        cron_expression="* * * * *",
        timezone_name="Asia/Shanghai",
        misfire_policy=ScheduleMisfirePolicy.COALESCE_ONE,
        misfire_grace_seconds=60,
        job_deadline_seconds=600,
    )


def _register(
    store: PostgresScheduleStore,
    *,
    key: str,
    marker: str = "p",
) -> ScheduleDefinition:
    """注册一条 tenant A disabled draft。

    Args:
        store: schedule store。
        key: schedule key。
        marker: payload 标记。

    Returns:
        已持久化 definition。

    Raises:
        无。
    """

    return store.register(_SCOPE_A, _registration(key=key, marker=marker))


def _activate(
    store: PostgresScheduleStore,
    definition: ScheduleDefinition,
    *,
    delay: timedelta = timedelta(minutes=5),
) -> ScheduleDefinition:
    """以 Store PG observation 激活 schedule。

    Args:
        store: schedule store。
        definition: 当前 disabled definition。
        delay: candidate 相对 PG observation 的未来偏移。

    Returns:
        激活后的 definition。

    Raises:
        AssertionError: observation/transition 不符合预期时抛出。
    """

    observation = store.get(_SCOPE_A, definition.id)
    assert observation is not None
    candidate = observation.database_now + delay
    result = store.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=definition.id,
            expected_version=definition.version,
            target_state=ScheduleState.ACTIVE,
        ),
        activation_next_fire_at=candidate,
    )
    assert result.action is ScheduleStateTransitionAction.APPLIED
    return result.observation.definition


def _snapshot(
    definition: ScheduleDefinition,
    scheduled_for: datetime,
    *,
    key_suffix: str,
) -> CanonicalScheduleEnqueueSnapshot:
    """从 frozen schedule content 构造合法 enqueue snapshot。

    Args:
        definition: 当前 schedule definition。
        scheduled_for: occurrence fire 时间。
        key_suffix: 幂等键后缀。

    Returns:
        byte-identical replay snapshot。

    Raises:
        无。
    """

    request = JobEnqueueRequest(
        descriptor=definition.descriptor,
        idempotency_key=f"schedule:{definition.id}:{key_suffix}",
        payload=definition.payload,
        available_at=scheduled_for,
        deadline_at=scheduled_for + timedelta(seconds=definition.job_deadline_seconds),
    )
    return CanonicalScheduleEnqueueSnapshot(
        descriptor=request.descriptor,
        payload=request.payload,
        idempotency_key=request.idempotency_key,
        available_at=request.available_at,
        deadline_at=request.deadline_at,
        request_fingerprint=job_enqueue_request_fingerprint(request),
    )


def _job_request(
    snapshot: CanonicalScheduleEnqueueSnapshot,
) -> JobEnqueueRequest:
    """从冻结 occurrence snapshot 重建唯一合法 job request。

    Args:
        snapshot: PostgreSQL occurrence 中持久化的完整 enqueue snapshot。

    Returns:
        与原 reservation byte-identical 的 ``JobEnqueueRequest``。

    Raises:
        无。
    """

    return JobEnqueueRequest(
        descriptor=snapshot.descriptor,
        idempotency_key=snapshot.idempotency_key,
        payload=snapshot.payload,
        available_at=snapshot.available_at,
        deadline_at=snapshot.deadline_at,
    )


def _reserve_pending(
    store: PostgresScheduleStore,
    definition: ScheduleDefinition,
    *,
    key_suffix: str,
) -> tuple[ScheduleOccurrence, ScheduleDefinition]:
    """为 active schedule reserve 一条 PENDING 并推进一分钟 cursor。

    Args:
        store: schedule store。
        definition: active definition。
        key_suffix: snapshot 幂等键后缀。

    Returns:
        ``(pending occurrence, advanced definition)``。

    Raises:
        AssertionError: definition/cursor 或 reserve 结果异常时抛出。
    """

    assert definition.state is ScheduleState.ACTIVE
    assert definition.next_fire_at is not None
    scheduled_for = definition.next_fire_at
    result = store.reserve_occurrences(
        _SCOPE_A,
        ScheduleReservationBatch(
            schedule_id=definition.id,
            expected_version=definition.version,
            expected_next_fire_at=scheduled_for,
            resulting_state=ScheduleState.ACTIVE,
            resulting_next_fire_at=scheduled_for + timedelta(minutes=1),
            reservations=(
                ScheduleOccurrenceReservation(
                    scheduled_for=scheduled_for,
                    state=ScheduleOccurrenceState.PENDING,
                    snapshot=_snapshot(
                        definition,
                        scheduled_for,
                        key_suffix=key_suffix,
                    ),
                    coalesced_count=0,
                    skip_reason=None,
                ),
            ),
        ),
    )
    assert result.action is ScheduleReserveAction.RESERVED
    assert len(result.occurrences) == 1
    observation = store.get(_SCOPE_A, definition.id)
    assert observation is not None
    return result.occurrences[0], observation.definition


def _admin_execute(
    schedule_db: tuple[PlatformCluster, str],
    statement: str,
    parameters: dict[str, _DbParam],
) -> None:
    """在独立测试数据库以 bootstrap 身份执行一条 DML。

    Args:
        schedule_db: 独立数据库信息。
        statement: 固定测试 SQL。
        parameters: bind 参数。

    Returns:
        无。

    Raises:
        DBAPIError: PostgreSQL 约束拒绝时抛出。
    """

    cluster, database = schedule_db
    engine = create_platform_engine(cluster.dsn_for_database(database, "postgres"))
    try:
        with engine.begin() as connection:
            connection.execute(text(statement), parameters)
    finally:
        engine.dispose()


def _admin_count(
    schedule_db: tuple[PlatformCluster, str],
    statement: str,
    parameters: dict[str, _DbParam],
) -> int:
    """以 bootstrap 身份执行固定 count 查询。

    Args:
        schedule_db: 独立数据库信息。
        statement: 返回单个 ``count`` 列的固定测试 SQL。
        parameters: bind 参数。

    Returns:
        查询得到的非负整数 count。

    Raises:
        AssertionError: 查询没有返回 exact int 时抛出。
    """

    cluster, database = schedule_db
    engine = create_platform_engine(cluster.dsn_for_database(database, "postgres"))
    try:
        with engine.connect() as connection:
            value = connection.execute(text(statement), parameters).scalar_one()
            connection.rollback()
    finally:
        engine.dispose()
    assert type(value) is int
    assert value >= 0
    return value


def _bulk_schedule_id(index: int) -> UUID:
    """构造按整数顺序递增的确定性 bulk schedule UUID。

    Args:
        index: 从 1 开始的 bulk 行序号。

    Returns:
        可按 PostgreSQL UUID 顺序比较的确定性 UUID。

    Raises:
        ValueError: index 超出 UUID 文本可表示范围时抛出。
    """

    return UUID(f"10000000-0000-0000-0000-{index:012d}")


def _bulk_occurrence_id(index: int) -> UUID:
    """构造按整数顺序递增的确定性 bulk occurrence UUID。

    Args:
        index: 从 1 开始的 bulk 行序号。

    Returns:
        可按 PostgreSQL UUID 顺序比较的确定性 UUID。

    Raises:
        ValueError: index 超出 UUID 文本可表示范围时抛出。
    """

    return UUID(f"20000000-0000-0000-0000-{index:012d}")


def _insert_due_backlog(
    schedule_db: tuple[PlatformCluster, str],
    template: ScheduleDefinition,
) -> None:
    """以一条合法 ACTIVE definition 克隆大量有序 due 宽行。

    Args:
        schedule_db: 独立真实 PostgreSQL 测试数据库。
        template: 已激活且即将 due 的模板 definition。

    Returns:
        无。

    Raises:
        DBAPIError: bulk insert 或 ANALYZE 失败时抛出。
    """

    _admin_execute(
        schedule_db,
        f"""
        INSERT INTO {_SCHEMA}.job_schedules (
            id, tenant_id, schedule_key, descriptor_job_type,
            descriptor_payload_schema_name, descriptor_payload_schema_version,
            descriptor_max_attempts, descriptor_retry_base_seconds,
            descriptor_retry_max_seconds, descriptor_lease_duration_seconds,
            payload_schema_name, payload_schema_version, payload_bytes,
            payload_sha256, cron_expression, timezone_name, misfire_policy,
            misfire_grace_seconds, job_deadline_seconds, state, next_fire_at,
            version, created_at, updated_at
        )
        SELECT
            ('10000000-0000-0000-0000-' || lpad(series.value::text, 12, '0'))::uuid,
            source.tenant_id,
            source.schedule_key || '-bulk-' || series.value::text,
            source.descriptor_job_type,
            source.descriptor_payload_schema_name,
            source.descriptor_payload_schema_version,
            source.descriptor_max_attempts,
            source.descriptor_retry_base_seconds,
            source.descriptor_retry_max_seconds,
            source.descriptor_lease_duration_seconds,
            source.payload_schema_name,
            source.payload_schema_version,
            source.payload_bytes,
            source.payload_sha256,
            source.cron_expression,
            source.timezone_name,
            source.misfire_policy,
            source.misfire_grace_seconds,
            source.job_deadline_seconds,
            source.state,
            source.next_fire_at + series.value * interval '1 microsecond',
            source.version,
            source.created_at,
            source.updated_at
        FROM {_SCHEMA}.job_schedules AS source
        CROSS JOIN generate_series(1, :backlog_size) AS series(value)
        WHERE source.id = :template_id
        """,
        {
            "backlog_size": _LARGE_BACKLOG_SIZE,
            "template_id": template.id,
        },
    )
    _admin_execute(
        schedule_db,
        f"ANALYZE {_SCHEMA}.job_schedules",
        {},
    )


def _insert_replay_backlog(
    schedule_db: tuple[PlatformCluster, str],
    template: ScheduleOccurrence,
) -> None:
    """克隆大量 fingerprint 合法且 identity 唯一的 PENDING 宽行。

    Args:
        schedule_db: 独立真实 PostgreSQL 测试数据库。
        template: 已持久化的合法 PENDING occurrence。

    Returns:
        无。

    Raises:
        AssertionError: 模板缺少冻结 snapshot 时抛出。
        DBAPIError: bulk insert、模板删除或 ANALYZE 失败时抛出。
    """

    snapshot = template.snapshot
    assert snapshot is not None
    parameters: dict[str, _DbParam] = {"template_id": template.id}
    values: list[str] = []
    for index in range(1, _LARGE_BACKLOG_SIZE + 1):
        occurrence_id = _bulk_occurrence_id(index)
        idempotency_key = f"schedule:{template.schedule_id}:bulk-{index}"
        scheduled_for = template.scheduled_for + timedelta(microseconds=index)
        deadline_at = snapshot.deadline_at + timedelta(microseconds=index)
        request = JobEnqueueRequest(
            descriptor=snapshot.descriptor,
            idempotency_key=idempotency_key,
            payload=snapshot.payload,
            available_at=scheduled_for,
            deadline_at=deadline_at,
        )
        parameters[f"occurrence_id_{index}"] = occurrence_id
        parameters[f"scheduled_for_{index}"] = scheduled_for
        parameters[f"deadline_at_{index}"] = deadline_at
        parameters[f"idempotency_key_{index}"] = idempotency_key
        parameters[f"fingerprint_{index}"] = job_enqueue_request_fingerprint(request)
        values.append(
            "(CAST(:occurrence_id_{0} AS uuid), :scheduled_for_{0}, "
            ":deadline_at_{0}, :idempotency_key_{0}, :fingerprint_{0})".format(
                index
            )
        )
    _admin_execute(
        schedule_db,
        f"""
        WITH source AS MATERIALIZED (
            SELECT * FROM {_SCHEMA}.job_schedule_occurrences
            WHERE id = :template_id
        ), bulk(
            occurrence_id, scheduled_for, deadline_at,
            idempotency_key, request_fingerprint
        ) AS (
            VALUES {", ".join(values)}
        )
        INSERT INTO {_SCHEMA}.job_schedule_occurrences (
            id, tenant_id, schedule_id, schedule_version, scheduled_for, state,
            snapshot_descriptor_job_type,
            snapshot_descriptor_payload_schema_name,
            snapshot_descriptor_payload_schema_version,
            snapshot_descriptor_max_attempts,
            snapshot_descriptor_retry_base_seconds,
            snapshot_descriptor_retry_max_seconds,
            snapshot_descriptor_lease_duration_seconds,
            snapshot_payload_schema_name,
            snapshot_payload_schema_version,
            snapshot_payload_bytes,
            snapshot_payload_sha256,
            snapshot_idempotency_key,
            snapshot_available_at,
            snapshot_deadline_at,
            snapshot_request_fingerprint,
            job_run_id, coalesced_count, skip_reason, created_at, updated_at
        )
        SELECT
            bulk.occurrence_id,
            source.tenant_id,
            source.schedule_id,
            source.schedule_version,
            bulk.scheduled_for,
            source.state,
            source.snapshot_descriptor_job_type,
            source.snapshot_descriptor_payload_schema_name,
            source.snapshot_descriptor_payload_schema_version,
            source.snapshot_descriptor_max_attempts,
            source.snapshot_descriptor_retry_base_seconds,
            source.snapshot_descriptor_retry_max_seconds,
            source.snapshot_descriptor_lease_duration_seconds,
            source.snapshot_payload_schema_name,
            source.snapshot_payload_schema_version,
            source.snapshot_payload_bytes,
            source.snapshot_payload_sha256,
            bulk.idempotency_key,
            bulk.scheduled_for,
            bulk.deadline_at,
            bulk.request_fingerprint,
            source.job_run_id,
            source.coalesced_count,
            source.skip_reason,
            source.created_at,
            source.updated_at
        FROM source CROSS JOIN bulk
        """,
        parameters,
    )
    _admin_execute(
        schedule_db,
        f"DELETE FROM {_SCHEMA}.job_schedule_occurrences WHERE id = :template_id",
        {"template_id": template.id},
    )
    _admin_execute(
        schedule_db,
        f"ANALYZE {_SCHEMA}.job_schedule_occurrences",
        {},
    )


def _explain_bounded_statement(
    schedule_db: tuple[PlatformCluster, str],
    statement: str,
    parameters: dict[str, _DbParam],
    *,
    expected_local_limits: int,
    expected_index: str,
    expected_relation: str,
    expected_segment_alias: str,
) -> str:
    """执行生产 SQL 的真实 EXPLAIN ANALYZE 并验证局部 limit/index 证据。

    Args:
        schedule_db: 独立真实 PostgreSQL 测试数据库。
        statement: 生产 query builder 返回的固定 bind SQL。
        parameters: 与生产调用相同的 bind 参数。
        expected_local_limits: SQL 中应存在的局部/最终 limit 数量。
        expected_index: 计划必须使用的既有复合索引名称。
        expected_relation: 计划不得顺序扫描的 backlog relation 名称。
        expected_segment_alias: production segment 使用的 SQL relation alias。

    Returns:
        可重复审计的 PostgreSQL text query plan。

    Raises:
        AssertionError: limit 数量、实际输出行数或索引计划不满足 bounded
            合同时抛出。
    """

    assert statement.count("LIMIT :limit") == expected_local_limits
    cluster, database = schedule_db
    engine = create_platform_engine(cluster.dsn_for_database(database, "postgres"))
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT, COSTS OFF, "
                    "TIMING OFF, SUMMARY OFF) " + statement
                ),
                parameters,
            ).fetchall()
            connection.rollback()
    finally:
        engine.dispose()
    plan_lines: list[str] = []
    for row in rows:
        value = row[0]
        assert isinstance(value, str)
        plan_lines.append(value)
    plan = "\n".join(plan_lines)
    assert (
        f"Index Scan using {expected_index}" in plan
        or f"Index Only Scan using {expected_index}" in plan
    )
    assert f"Seq Scan on {expected_relation} {expected_segment_alias}" not in plan
    limited_row_counts = tuple(
        int(match.group(1))
        for match in re.finditer(r"Limit \(actual rows=(\d+) loops=\d+\)", plan)
    )
    assert limited_row_counts
    query_limit = parameters["limit"]
    assert type(query_limit) is int
    assert max(limited_row_counts) <= query_limit
    return plan


def _race_activate(
    store: PostgresScheduleStore,
    barrier: Barrier,
    request: ScheduleActivationRequest,
    candidate: datetime,
) -> str:
    """等待双 writer barrier 后发起一次 ACTIVE CAS。

    Args:
        store: 独立 engine 的 schedule store。
        barrier: 两个 writer 共用的启动 barrier。
        request: 相同 expected-version ACTIVE 请求。
        candidate: 相同 future candidate。

    Returns:
        成功 action 值或 ``conflict`` 闭合标签。

    Raises:
        无；version loser 被收敛为 ``conflict``。
    """

    barrier.wait(timeout=10)
    try:
        result = store.set_state(
            _SCOPE_A,
            request,
            activation_next_fire_at=candidate,
        )
    except ScheduleVersionConflictError:
        return "conflict"
    return result.action.value


def _race_ensure_registered(
    store: PostgresScheduleStore,
    barrier: Barrier,
    request: ScheduleRegistrationRequest,
) -> ScheduleDefinition:
    """等待双 writer barrier 后提交同一 ensure registration。

    Args:
        store: 当前 writer 的独立 schedule store。
        barrier: 两个 writer 共用的启动 barrier。
        request: 两个 writer 完全相同的 immutable request。

    Returns:
        唯一 schedule identity 的当前 definition projection。

    Raises:
        threading.BrokenBarrierError: 另一个 writer 未有界抵达时抛出。
        ScheduleRepositoryError: PostgreSQL 边界失败时由 Store 抛出。
    """

    barrier.wait(timeout=10)
    return store.ensure_registered(_SCOPE_A, request)


def _race_reserve(
    store: PostgresScheduleStore,
    barrier: Barrier,
    batch: ScheduleReservationBatch,
) -> ScheduleReservationResult:
    """在双 writer barrier 后提交同一 reservation batch。

    Args:
        store: 当前 writer 的独立 schedule store。
        barrier: 两个 writer 共用的启动 barrier。
        batch: 两个 writer 完全相同的 reservation batch。

    Returns:
        ``reserved`` 或 ``lost_race`` 的闭合 PG 结果。

    Raises:
        threading.BrokenBarrierError: 另一个 writer 未有界抵达时抛出。
        ScheduleRepositoryError: PostgreSQL 边界失败时由 Store 抛出。
    """

    barrier.wait(timeout=10)
    return store.reserve_occurrences(_SCOPE_A, batch)


def _race_disable(
    store: PostgresScheduleStore,
    barrier: Barrier,
    request: ScheduleActivationRequest,
) -> ScheduleStateTransitionAction:
    """在双 writer barrier 后提交 manual disable。

    Args:
        store: 当前 writer 的独立 schedule store。
        barrier: disable/begin 共用的启动 barrier。
        request: exact-version DISABLED 请求。

    Returns:
        Store 返回的 state transition action。

    Raises:
        threading.BrokenBarrierError: begin writer 未有界抵达时抛出。
        ScheduleVersionConflictError: schedule version 已被其它操作推进时抛出。
    """

    barrier.wait(timeout=10)
    return store.set_state(
        _SCOPE_A,
        request,
        activation_next_fire_at=None,
    ).action


def _race_begin(
    store: PostgresScheduleStore,
    barrier: Barrier,
    occurrence_id: UUID,
) -> ScheduleMaterializationAction:
    """在双 writer barrier 后尝试线性化 PENDING occurrence。

    Args:
        store: 当前 writer 的独立 schedule store。
        barrier: disable/begin 共用的启动 barrier。
        occurrence_id: 目标 occurrence UUID。

    Returns:
        enqueue 或 skipped 的闭合 begin action。

    Raises:
        threading.BrokenBarrierError: disable writer 未有界抵达时抛出。
        ScheduleInvariantError: 持久状态不闭合时由 Store 抛出。
    """

    barrier.wait(timeout=10)
    return store.begin_materialization(
        _SCOPE_A,
        occurrence_id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    ).action


def _race_materialize(
    schedule_store: PostgresScheduleStore,
    job_store: PostgresJobStore,
    barrier: Barrier,
    occurrence_id: UUID,
) -> _MaterializationRaceOutcome:
    """以独立 engine 完成一次 committed materialization replay。

    Args:
        schedule_store: 当前 scheduler 的独立 schedule store。
        job_store: 与该 scheduler 同 engine/session factory 的 job store。
        barrier: 两个 scheduler 共用的启动 barrier。
        occurrence_id: 目标 PENDING occurrence UUID。

    Returns:
        begin/enqueue/mark 三阶段闭合结果。

    Raises:
        threading.BrokenBarrierError: 另一个 scheduler 未有界抵达时抛出。
        AssertionError: persisted snapshot 缺失时抛出。
        ScheduleInvariantError: occurrence 状态不闭合时由 Store 抛出。
    """

    barrier.wait(timeout=10)
    decision = schedule_store.begin_materialization(
        _SCOPE_A,
        occurrence_id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    assert decision.action is ScheduleMaterializationAction.ENQUEUE
    snapshot = decision.occurrence.snapshot
    assert snapshot is not None
    receipt = job_store.enqueue(_SCOPE_A, _job_request(snapshot))
    marked = schedule_store.mark_enqueued(
        _SCOPE_A,
        occurrence_id,
        snapshot.request_fingerprint,
        receipt.job_id,
    )
    return _MaterializationRaceOutcome(
        begin_action=decision.action,
        job_id=receipt.job_id,
        idempotency_reused=receipt.idempotency_reused,
        mark_action=marked.action,
    )


def test_schedule_ensure_registered_replays_lost_response_to_same_exact_draft(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """丢失首次响应后按 key 重读并复用已推进的同一 schedule。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    request = _registration(key="ensure-replay")
    created = harness.primary.ensure_registered(_SCOPE_A, request)
    assert created.state is ScheduleState.DISABLED
    assert created.next_fire_at is None
    assert created.version == 1
    assert (
        harness.primary.get_by_key(
            _SCOPE_A,
            schedule_key=request.schedule_key,
        )
        == created
    )
    assert (
        harness.primary.get_by_key(
            _SCOPE_A,
            schedule_key="ensure-replay-missing",
        )
        is None
    )
    assert (
        harness.primary.get_by_key(
            _SCOPE_B,
            schedule_key=request.schedule_key,
        )
        is None
    )
    for invalid_schedule_key in ("", " ensure-replay", "ensure-replay "):
        with pytest.raises(ScheduleInputError):
            harness.primary.get_by_key(
                _SCOPE_A,
                schedule_key=invalid_schedule_key,
            )

    active = _activate(harness.primary, created)
    replayed = harness.secondary.ensure_registered(_SCOPE_A, request)
    assert replayed == active
    assert replayed.id == created.id
    assert replayed.state is ScheduleState.ACTIVE
    assert replayed.version == created.version + 1
    assert replayed.next_fire_at is not None
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_schedules "
            "WHERE tenant_id=:tenant_id AND schedule_key=:schedule_key",
            {
                "tenant_id": _TENANT_A.value,
                "schedule_key": request.schedule_key,
            },
        )
        == 1
    )


def test_schedule_lookup_miss_converges_concurrently_through_ensure_registered_unique_identity(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """两个独立 engine 的同 intent miss 由唯一约束收敛为同一 identity。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    request = _registration(key="ensure-race")
    assert (
        harness.primary.get_by_key(
            _SCOPE_A,
            schedule_key=request.schedule_key,
        )
        is None
    )
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            _race_ensure_registered,
            harness.primary,
            barrier,
            request,
        )
        second_future = executor.submit(
            _race_ensure_registered,
            harness.secondary,
            barrier,
            request,
        )
        first = first_future.result(timeout=20)
        second = second_future.result(timeout=20)

    assert first == second
    assert first.id == second.id
    assert first.state is ScheduleState.DISABLED
    assert first.version == 1
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_schedules "
            "WHERE tenant_id=:tenant_id AND schedule_key=:schedule_key",
            {
                "tenant_id": _TENANT_A.value,
                "schedule_key": request.schedule_key,
            },
        )
        == 1
    )


def test_schedule_ensure_registered_rejects_same_key_with_each_schema_valid_immutable_drift(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """每个当前可构造 immutable 替代值均 typed conflict 且零修改。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    request = _registration(key="ensure-drift")
    created = harness.primary.ensure_registered(_SCOPE_A, request)
    descriptor = request.descriptor
    cases = (
        ("descriptor_job_type", replace(request, descriptor=replace(descriptor, job_type="test.schedule.other"))),
        (
            "descriptor_payload_schema_name",
            replace(
                request,
                descriptor=replace(
                    descriptor,
                    payload_schema_name="test.schedule.payload.other",
                ),
            ),
        ),
        (
            "descriptor_payload_schema_version",
            replace(request, descriptor=replace(descriptor, payload_schema_version=2)),
        ),
        (
            "descriptor_max_attempts",
            replace(request, descriptor=replace(descriptor, max_attempts=4)),
        ),
        (
            "descriptor_retry_base_seconds",
            replace(request, descriptor=replace(descriptor, retry_base_seconds=2)),
        ),
        (
            "descriptor_retry_max_seconds",
            replace(request, descriptor=replace(descriptor, retry_max_seconds=11)),
        ),
        (
            "descriptor_lease_duration_seconds",
            replace(request, descriptor=replace(descriptor, lease_duration_seconds=61)),
        ),
        (
            "payload_schema_name",
            replace(
                request,
                payload=build_canonical_document(
                    {"marker": "p"},
                    schema_name="test.schedule.payload.other",
                    schema_version=request.payload.schema_version,
                ),
            ),
        ),
        (
            "payload_schema_version",
            replace(
                request,
                payload=build_canonical_document(
                    {"marker": "p"},
                    schema_name=request.payload.schema_name,
                    schema_version=2,
                ),
            ),
        ),
        ("payload_content", replace(request, payload=_payload(marker="other"))),
        ("cron_expression", replace(request, cron_expression="0 * * * *")),
        ("timezone_name", replace(request, timezone_name="UTC")),
        (
            "misfire_grace_seconds",
            replace(request, misfire_grace_seconds=61),
        ),
        ("job_deadline_seconds", replace(request, job_deadline_seconds=601)),
    )
    assert len(cases) == 14

    for label, drifted_request in cases:
        with pytest.raises(ScheduleVersionConflictError):
            harness.secondary.ensure_registered(_SCOPE_A, drifted_request)
        persisted = harness.primary.get_by_key(
            _SCOPE_A,
            schedule_key=request.schedule_key,
        )
        assert persisted == created, label
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_schedules "
            "WHERE tenant_id=:tenant_id AND schedule_key=:schedule_key",
            {
                "tenant_id": _TENANT_A.value,
                "schedule_key": request.schedule_key,
            },
        )
        == 1
    )


def test_schedule_schema_valid_immutable_conflict_is_distinct_from_malformed_persisted_row(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """合法 immutable drift 与无法构造的 persisted enum 精确分流。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    request = _registration(key="ensure-malformed")
    created = harness.primary.ensure_registered(_SCOPE_A, request)
    with pytest.raises(ScheduleVersionConflictError):
        harness.secondary.ensure_registered(
            _SCOPE_A,
            replace(request, cron_expression="0 * * * *"),
        )
    assert (
        harness.primary.get_by_key(
            _SCOPE_A,
            schedule_key=request.schedule_key,
        )
        == created
    )

    trigger_name = "guard_job_schedules_immutable_columns_trigger"
    constraint_name = "ck_job_schedules_misfire_policy_closed"
    _admin_execute(
        schedule_db,
        f"ALTER TABLE {_SCHEMA}.job_schedules DISABLE TRIGGER {trigger_name}",
        {},
    )
    try:
        _admin_execute(
            schedule_db,
            f"ALTER TABLE {_SCHEMA}.job_schedules DROP CONSTRAINT {constraint_name}",
            {},
        )
        try:
            _admin_execute(
                schedule_db,
                f"UPDATE {_SCHEMA}.job_schedules SET misfire_policy='unknown' "
                "WHERE id=:schedule_id",
                {"schedule_id": created.id},
            )
            with pytest.raises(ScheduleRepositoryError):
                harness.secondary.ensure_registered(_SCOPE_A, request)
            assert (
                _admin_count(
                    schedule_db,
                    f"SELECT count(*) FROM {_SCHEMA}.job_schedules "
                    "WHERE id=:schedule_id AND misfire_policy='unknown' "
                    "AND state=:state AND version=:version",
                    {
                        "schedule_id": created.id,
                        "state": created.state.value,
                        "version": created.version,
                    },
                )
                == 1
            )
        finally:
            try:
                _admin_execute(
                    schedule_db,
                    f"UPDATE {_SCHEMA}.job_schedules "
                    "SET misfire_policy='coalesce_one' WHERE id=:schedule_id",
                    {"schedule_id": created.id},
                )
            finally:
                _admin_execute(
                    schedule_db,
                    f"ALTER TABLE {_SCHEMA}.job_schedules ADD CONSTRAINT "
                    f"{constraint_name} CHECK (misfire_policy IN ('coalesce_one'))",
                    {},
                )
    finally:
        _admin_execute(
            schedule_db,
            f"ALTER TABLE {_SCHEMA}.job_schedules ENABLE TRIGGER {trigger_name}",
            {},
        )

    assert (
        harness.primary.get_by_key(
            _SCOPE_A,
            schedule_key=request.schedule_key,
        )
        == created
    )
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_schedules "
            "WHERE tenant_id=:tenant_id AND schedule_key=:schedule_key",
            {
                "tenant_id": _TENANT_A.value,
                "schedule_key": request.schedule_key,
            },
        )
        == 1
    )


def test_schedule_content_is_immutable_and_activation_requires_exact_version(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """immutable trigger 与 exact-version activation 均由真实 PG 拒绝。"""

    definition = _register(harness.primary, key="immutable")
    with pytest.raises(DBAPIError):
        _admin_execute(
            schedule_db,
            f"UPDATE {_SCHEMA}.job_schedules SET cron_expression = '0 * * * *' WHERE id = :schedule_id",
            {"schedule_id": str(definition.id)},
        )
    observation = harness.primary.get(_SCOPE_A, definition.id)
    assert observation is not None
    assert observation.definition == definition
    with pytest.raises(ScheduleVersionConflictError):
        harness.primary.set_state(
            _SCOPE_A,
            ScheduleActivationRequest(
                schedule_id=definition.id,
                expected_version=definition.version + 1,
                target_state=ScheduleState.ACTIVE,
            ),
            activation_next_fire_at=observation.database_now + timedelta(minutes=1),
        )


def test_activate_uses_pg_observation_and_persists_first_strictly_future_cursor(
    harness: ScheduleHarness,
) -> None:
    """ACTIVE DML 返回同 statement PG clock 且 cursor 严格在其未来。"""

    definition = _register(harness.primary, key="activate")
    before = harness.primary.get(_SCOPE_A, definition.id)
    assert before is not None
    candidate = before.database_now + timedelta(minutes=2)
    result = harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=definition.id,
            expected_version=definition.version,
            target_state=ScheduleState.ACTIVE,
        ),
        activation_next_fire_at=candidate,
    )
    assert result.action is ScheduleStateTransitionAction.APPLIED
    assert result.observation.definition.next_fire_at == candidate
    assert candidate > result.observation.database_now
    assert result.observation.definition.version == definition.version + 1
    persisted = harness.primary.get(_SCOPE_A, definition.id)
    assert persisted is not None
    assert persisted.definition == result.observation.definition


def test_activate_conditional_pg_clock_guard_rejects_candidate_expiring_at_update_boundary(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """row-lock 等待期间过期的 candidate 返回 clock_stale 且零修改。"""

    definition = _register(harness.primary, key="clock-boundary")
    observation = harness.primary.get(_SCOPE_A, definition.id)
    assert observation is not None
    candidate = observation.database_now + timedelta(milliseconds=150)
    cluster, database = schedule_db
    engine = create_platform_engine(cluster.dsn_for_database(database, "postgres"))
    try:
        connection = engine.connect()
        transaction = connection.begin()
        connection.execute(
            text(
                f"SELECT id FROM {_SCHEMA}.job_schedules WHERE id = :schedule_id FOR UPDATE"
            ),
            {"schedule_id": str(definition.id)},
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                harness.secondary.set_state,
                _SCOPE_A,
                ScheduleActivationRequest(
                    schedule_id=definition.id,
                    expected_version=definition.version,
                    target_state=ScheduleState.ACTIVE,
                ),
                activation_next_fire_at=candidate,
            )
            time.sleep(0.25)
            transaction.commit()
            result = future.result(timeout=10)
        connection.close()
    finally:
        engine.dispose()
    assert result.action is ScheduleStateTransitionAction.CLOCK_STALE
    assert result.observation.definition == definition
    assert candidate <= result.observation.database_now
    persisted = harness.primary.get(_SCOPE_A, definition.id)
    assert persisted is not None
    assert persisted.definition == definition


def test_two_activate_or_activate_disable_same_version_have_one_linearized_winner(
    harness: ScheduleHarness,
) -> None:
    """两个相同 version 的 activate 只有一个 applied winner。"""

    definition = _register(harness.primary, key="activate-race")
    observation = harness.primary.get(_SCOPE_A, definition.id)
    assert observation is not None
    candidate = observation.database_now + timedelta(minutes=5)
    request = ScheduleActivationRequest(
        schedule_id=definition.id,
        expected_version=definition.version,
        target_state=ScheduleState.ACTIVE,
    )
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            _race_activate,
            harness.primary,
            barrier,
            request,
            candidate,
        )
        second = executor.submit(
            _race_activate,
            harness.secondary,
            barrier,
            request,
            candidate,
        )
        outcomes = sorted((first.result(timeout=10), second.result(timeout=10)))
    assert outcomes == ["applied", "conflict"]


def test_disabled_schedule_never_becomes_due_and_skips_existing_pending_occurrence(
    harness: ScheduleHarness,
) -> None:
    """manual disable 保留 cursor、skip PENDING，且不再出现在 due page。"""

    active = _activate(harness.primary, _register(harness.primary, key="disable"))
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="pending",
    )
    assert advanced.next_fire_at is not None
    disabled = harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=advanced.id,
            expected_version=advanced.version,
            target_state=ScheduleState.DISABLED,
        ),
        activation_next_fire_at=None,
    )
    assert disabled.action is ScheduleStateTransitionAction.APPLIED
    assert disabled.observation.definition.next_fire_at == advanced.next_fire_at
    stored_occurrence = harness.primary.get_occurrence(_SCOPE_A, pending.id)
    assert stored_occurrence is not None
    assert stored_occurrence.state is ScheduleOccurrenceState.SKIPPED
    assert stored_occurrence.skip_reason is ScheduleSkipReason.SCHEDULE_DISABLED
    assert stored_occurrence.snapshot == pending.snapshot
    assert harness.primary.list_due(_SCOPE_A, None, limit=10).entries == ()


def test_scan_limit_batch_explicitly_disables_and_preserves_expected_cursor_without_skip_reason_inference(
    harness: ScheduleHarness,
) -> None:
    """scan-limit batch 由 resulting_state 显式禁用并保留审计 cursor。"""

    active = _activate(harness.primary, _register(harness.primary, key="scan-limit"))
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="old-pending",
    )
    assert advanced.next_fire_at is not None
    cursor = advanced.next_fire_at
    result = harness.primary.reserve_occurrences(
        _SCOPE_A,
        ScheduleReservationBatch(
            schedule_id=advanced.id,
            expected_version=advanced.version,
            expected_next_fire_at=cursor,
            resulting_state=ScheduleState.DISABLED,
            resulting_next_fire_at=cursor,
            reservations=(
                ScheduleOccurrenceReservation(
                    scheduled_for=cursor,
                    state=ScheduleOccurrenceState.SKIPPED,
                    snapshot=None,
                    coalesced_count=None,
                    skip_reason=ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED,
                ),
            ),
        ),
    )
    assert result.action is ScheduleReserveAction.RESERVED
    assert (
        result.occurrences[0].skip_reason
        is ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED
    )
    persisted = harness.primary.get(_SCOPE_A, advanced.id)
    assert persisted is not None
    assert persisted.definition.state is ScheduleState.DISABLED
    assert persisted.definition.next_fire_at == cursor
    old_pending = harness.primary.get_occurrence(_SCOPE_A, pending.id)
    assert old_pending is not None
    assert old_pending.skip_reason is ScheduleSkipReason.SCHEDULE_DISABLED


def test_pending_unavailable_admission_returns_no_work_without_schedule_or_occurrence_mutation(
    harness: ScheduleHarness,
) -> None:
    """PENDING unavailable 只返回 typed no-work，PG 两行保持逐字段不变。"""

    active = _activate(harness.primary, _register(harness.primary, key="unavailable"))
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="unavailable",
    )
    decision = harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_UNAVAILABLE,
    )
    assert decision.action is ScheduleMaterializationAction.UNAVAILABLE
    assert decision.occurrence == pending
    after_occurrence = harness.primary.get_occurrence(_SCOPE_A, pending.id)
    after_schedule = harness.primary.get(_SCOPE_A, advanced.id)
    assert after_occurrence == pending
    assert after_schedule is not None
    assert after_schedule.definition == advanced


def test_stale_unavailable_admission_losing_to_begin_keeps_materializing_commitment(
    harness: ScheduleHarness,
) -> None:
    """已 MATERIALIZING 后的 stale unavailable admission 仍返回 enqueue。"""

    active = _activate(harness.primary, _register(harness.primary, key="stale-proof"))
    pending, _ = _reserve_pending(
        harness.primary,
        active,
        key_suffix="stale-proof",
    )
    winner = harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    assert winner.action is ScheduleMaterializationAction.ENQUEUE
    stale = harness.secondary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_UNAVAILABLE,
    )
    assert stale.action is ScheduleMaterializationAction.ENQUEUE
    assert stale.occurrence.state is ScheduleOccurrenceState.MATERIALIZING


def test_materializing_is_always_selected_before_pending_regardless_of_pending_cursor(
    harness: ScheduleHarness,
) -> None:
    """replay page 无条件把较新的 MATERIALIZING 放在较老 PENDING 前。"""

    active = _activate(harness.primary, _register(harness.primary, key="replay-order"))
    oldest, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="oldest",
    )
    newer, _ = _reserve_pending(
        harness.primary,
        advanced,
        key_suffix="newer",
    )
    harness.primary.begin_materialization(
        _SCOPE_A,
        newer.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    page = harness.primary.list_replayable(
        _SCOPE_A,
        ScheduleReplayCursor(
            scheduled_for=oldest.scheduled_for,
            occurrence_id=oldest.id,
        ),
        limit=2,
    )
    assert [item.id for item in page.occurrences] == [newer.id, oldest.id]
    assert page.next_pending_cursor == ScheduleReplayCursor(
        scheduled_for=oldest.scheduled_for,
        occurrence_id=oldest.id,
    )
    committed_only = harness.primary.list_replayable(
        _SCOPE_A,
        page.next_pending_cursor,
        limit=1,
    )
    assert [item.id for item in committed_only.occurrences] == [newer.id]
    assert committed_only.next_pending_cursor == page.next_pending_cursor


def test_unavailable_oldest_pending_does_not_starve_later_materializing_commitment(
    harness: ScheduleHarness,
) -> None:
    """最老 PENDING unavailable 时，后续 MATERIALIZING 仍固定排在页首。

    Args:
        harness: 两条独立 app engine/store 集合。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(
        harness.primary,
        _register(harness.primary, key="unavailable-before-commitment"),
    )
    oldest, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="unavailable-oldest",
    )
    later, _ = _reserve_pending(
        harness.primary,
        advanced,
        key_suffix="later-commitment",
    )
    unavailable = harness.primary.begin_materialization(
        _SCOPE_A,
        oldest.id,
        admission=ScheduleMaterializationAdmission.PENDING_UNAVAILABLE,
    )
    assert unavailable.action is ScheduleMaterializationAction.UNAVAILABLE
    committed = harness.secondary.begin_materialization(
        _SCOPE_A,
        later.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    assert committed.action is ScheduleMaterializationAction.ENQUEUE

    page = harness.primary.list_replayable(_SCOPE_A, None, limit=2)
    assert [occurrence.id for occurrence in page.occurrences] == [
        later.id,
        oldest.id,
    ]
    assert page.occurrences[0].state is ScheduleOccurrenceState.MATERIALIZING
    assert page.occurrences[1].state is ScheduleOccurrenceState.PENDING
    assert page.next_pending_cursor == ScheduleReplayCursor(
        scheduled_for=oldest.scheduled_for,
        occurrence_id=oldest.id,
    )


def test_pending_keyset_cursor_rotates_past_unavailable_without_starving_later_available_pending(
    harness: ScheduleHarness,
) -> None:
    """PENDING cursor 越过 unavailable 首项后可线性化后续 available 项。

    Args:
        harness: 两条独立 app engine/store 集合。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(
        harness.primary,
        _register(harness.primary, key="pending-capability-rotation"),
    )
    unavailable_pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="unavailable-prefix",
    )
    available_pending, _ = _reserve_pending(
        harness.primary,
        advanced,
        key_suffix="available-later",
    )
    first_page = harness.primary.list_replayable(_SCOPE_A, None, limit=1)
    assert first_page.occurrences == (unavailable_pending,)
    assert first_page.next_pending_cursor is not None
    unavailable = harness.primary.begin_materialization(
        _SCOPE_A,
        unavailable_pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_UNAVAILABLE,
    )
    assert unavailable.action is ScheduleMaterializationAction.UNAVAILABLE

    second_page = harness.secondary.list_replayable(
        _SCOPE_A,
        first_page.next_pending_cursor,
        limit=1,
    )
    assert second_page.occurrences == (available_pending,)
    assert second_page.next_pending_cursor == ScheduleReplayCursor(
        scheduled_for=available_pending.scheduled_for,
        occurrence_id=available_pending.id,
    )
    capable = harness.secondary.begin_materialization(
        _SCOPE_A,
        available_pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    assert capable.action is ScheduleMaterializationAction.ENQUEUE
    assert capable.occurrence.state is ScheduleOccurrenceState.MATERIALIZING
    oldest_after = harness.primary.get_occurrence(
        _SCOPE_A,
        unavailable_pending.id,
    )
    assert oldest_after == unavailable_pending


def test_replay_page_limit_and_cursor_prevent_same_tick_busy_loop_or_duplicate_occurrence(
    harness: ScheduleHarness,
) -> None:
    """PENDING keyset wrap 受 limit 限制且单页不重复 occurrence。"""

    active = _activate(harness.primary, _register(harness.primary, key="replay-page"))
    first, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="first",
    )
    second, advanced = _reserve_pending(
        harness.primary,
        advanced,
        key_suffix="second",
    )
    third, _ = _reserve_pending(
        harness.primary,
        advanced,
        key_suffix="third",
    )
    first_page = harness.primary.list_replayable(_SCOPE_A, None, limit=2)
    assert [item.id for item in first_page.occurrences] == [first.id, second.id]
    assert first_page.next_pending_cursor is not None
    second_page = harness.primary.list_replayable(
        _SCOPE_A,
        first_page.next_pending_cursor,
        limit=2,
    )
    second_ids = [item.id for item in second_page.occurrences]
    assert second_ids == [third.id, first.id]
    assert len(second_ids) == len(set(second_ids)) == 2


def test_due_page_wrap_has_no_duplicates_and_unavailable_rows_remain_byte_exact(
    harness: ScheduleHarness,
) -> None:
    """due keyset 到尾后无重复 wrap，纯读取不改变任一 schedule。"""

    definitions: list[ScheduleDefinition] = []
    for index in range(3):
        draft = _register(harness.primary, key=f"due-{index}")
        definitions.append(
            _activate(
                harness.primary,
                draft,
                delay=timedelta(milliseconds=100),
            )
        )
    time.sleep(0.2)
    before = {
        definition.id: harness.primary.get(_SCOPE_A, definition.id)
        for definition in definitions
    }
    first_page = harness.primary.list_due(_SCOPE_A, None, limit=2)
    assert len(first_page.entries) == 2
    assert first_page.next_cursor is not None
    second_page = harness.primary.list_due(
        _SCOPE_A,
        first_page.next_cursor,
        limit=2,
    )
    second_ids = [entry.observation.definition.id for entry in second_page.entries]
    assert len(second_ids) == len(set(second_ids)) == 2
    all_ids = {
        entry.observation.definition.id
        for entry in (*first_page.entries, *second_page.entries)
    }
    assert all_ids == {definition.id for definition in definitions}
    after = {
        definition.id: harness.primary.get(_SCOPE_A, definition.id)
        for definition in definitions
    }
    assert {
        key: value.definition if value is not None else None
        for key, value in before.items()
    } == {
        key: value.definition if value is not None else None
        for key, value in after.items()
    }


def test_large_backlog_queries_bound_each_keyset_segment_and_preserve_wrap_priority(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """大 backlog 下每段走索引局部 limit，且 due/replay wrap/priority 不变。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 同一独立真实 PostgreSQL 测试数据库。

    Returns:
        无。

    Raises:
        AssertionError: 结果顺序、cursor、局部 limit 或 EXPLAIN 索引证据
            不符合 bounded contract 时抛出。
    """

    due_template = _activate(
        harness.primary,
        _register(harness.primary, key="bounded-due-template"),
        delay=timedelta(milliseconds=100),
    )
    assert due_template.next_fire_at is not None
    _insert_due_backlog(schedule_db, due_template)
    time.sleep(0.2)
    due_cursor_index = _LARGE_BACKLOG_SIZE - 2
    due_cursor = ScheduleDueCursor(
        next_fire_at=due_template.next_fire_at
        + timedelta(microseconds=due_cursor_index),
        schedule_id=_bulk_schedule_id(due_cursor_index),
    )
    due_page = harness.primary.list_due(
        _SCOPE_A,
        due_cursor,
        limit=_QUERY_PAGE_LIMIT,
    )
    assert [entry.observation.definition.id for entry in due_page.entries] == [
        _bulk_schedule_id(_LARGE_BACKLOG_SIZE - 1),
        _bulk_schedule_id(_LARGE_BACKLOG_SIZE),
        due_template.id,
        _bulk_schedule_id(1),
        _bulk_schedule_id(2),
    ]
    assert due_page.next_cursor == due_page.entries[-1].cursor_after
    due_statement = postgres_schedules_storage._list_due_statement(due_cursor)
    due_plan = _explain_bounded_statement(
        schedule_db,
        due_statement,
        {
            "tenant_id": _TENANT_A.value,
            "active": ScheduleState.ACTIVE.value,
            "limit": _QUERY_PAGE_LIMIT,
            "cursor_next_fire_at": due_cursor.next_fire_at,
            "cursor_schedule_id": str(due_cursor.schedule_id),
        },
        expected_local_limits=3,
        expected_index="ix_job_schedules_due",
        expected_relation="job_schedules",
        expected_segment_alias="s",
    )
    assert f"actual rows={_LARGE_BACKLOG_SIZE}" not in due_plan

    replay_definition = _activate(
        harness.primary,
        _register(harness.primary, key="bounded-replay-template"),
    )
    replay_template, _ = _reserve_pending(
        harness.primary,
        replay_definition,
        key_suffix="template",
    )
    _insert_replay_backlog(schedule_db, replay_template)
    replay_cursor_index = _LARGE_BACKLOG_SIZE - 2
    replay_cursor = ScheduleReplayCursor(
        scheduled_for=replay_template.scheduled_for
        + timedelta(microseconds=replay_cursor_index),
        occurrence_id=_bulk_occurrence_id(replay_cursor_index),
    )
    replay_page = harness.primary.list_replayable(
        _SCOPE_A,
        replay_cursor,
        limit=_QUERY_PAGE_LIMIT,
    )
    assert [occurrence.id for occurrence in replay_page.occurrences] == [
        _bulk_occurrence_id(_LARGE_BACKLOG_SIZE - 1),
        _bulk_occurrence_id(_LARGE_BACKLOG_SIZE),
        _bulk_occurrence_id(1),
        _bulk_occurrence_id(2),
        _bulk_occurrence_id(3),
    ]
    assert replay_page.next_pending_cursor == ScheduleReplayCursor(
        scheduled_for=replay_template.scheduled_for + timedelta(microseconds=3),
        occurrence_id=_bulk_occurrence_id(3),
    )

    for index in range(1, _QUERY_PAGE_LIMIT + 4):
        decision = harness.primary.begin_materialization(
            _SCOPE_A,
            _bulk_occurrence_id(index),
            admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
        )
        assert decision.action is ScheduleMaterializationAction.ENQUEUE
    priority_page = harness.primary.list_replayable(
        _SCOPE_A,
        replay_cursor,
        limit=_QUERY_PAGE_LIMIT,
    )
    assert [occurrence.id for occurrence in priority_page.occurrences] == [
        _bulk_occurrence_id(index)
        for index in range(1, _QUERY_PAGE_LIMIT + 1)
    ]
    assert all(
        occurrence.state is ScheduleOccurrenceState.MATERIALIZING
        for occurrence in priority_page.occurrences
    )
    assert priority_page.next_pending_cursor == replay_cursor
    replay_statement = postgres_schedules_storage._list_replayable_statement(
        replay_cursor
    )
    replay_plan = _explain_bounded_statement(
        schedule_db,
        replay_statement,
        {
            "tenant_id": _TENANT_A.value,
            "materializing": ScheduleOccurrenceState.MATERIALIZING.value,
            "pending": ScheduleOccurrenceState.PENDING.value,
            "limit": _QUERY_PAGE_LIMIT,
            "cursor_scheduled_for": replay_cursor.scheduled_for,
            "cursor_occurrence_id": str(replay_cursor.occurrence_id),
        },
        expected_local_limits=4,
        expected_index="ix_job_schedule_occurrences_replayable",
        expected_relation="job_schedule_occurrences",
        expected_segment_alias="o",
    )
    assert f"actual rows={_LARGE_BACKLOG_SIZE}" not in replay_plan


def test_get_occurrence_is_tenant_scoped_and_returns_frozen_descriptor_snapshot(
    harness: ScheduleHarness,
) -> None:
    """point-read 返回冻结 snapshot，跨租户表现为 not-found。"""

    active = _activate(harness.primary, _register(harness.primary, key="point-read"))
    pending, _ = _reserve_pending(
        harness.primary,
        active,
        key_suffix="point-read",
    )
    own = harness.primary.get_occurrence(_SCOPE_A, pending.id)
    assert own == pending
    assert own is not None
    assert own.snapshot is not None
    assert own.snapshot.descriptor == active.descriptor
    assert harness.primary.get_occurrence(_SCOPE_B, pending.id) is None


def test_crash_after_cursor_commit_before_enqueue_replays_pending_without_losing_fire(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """cursor+PENDING 提交后新 engine 必须从 durable outbox 找回 fire。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(harness.primary, _register(harness.primary, key="crash-cursor"))
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="crash-cursor",
    )

    replay = harness.secondary.list_replayable(_SCOPE_A, None, limit=10)
    assert replay.occurrences == (pending,)
    assert replay.next_pending_cursor == ScheduleReplayCursor(
        scheduled_for=pending.scheduled_for,
        occurrence_id=pending.id,
    )
    persisted = harness.secondary.get(_SCOPE_A, active.id)
    assert persisted is not None
    assert persisted.definition == advanced
    assert persisted.definition.next_fire_at != pending.scheduled_for
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_runs WHERE tenant_id = :tenant_id",
            {"tenant_id": _TENANT_A.value},
        )
        == 0
    )


def test_crash_after_begin_materialization_before_enqueue_replays_frozen_request(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """MATERIALIZING 提交后新 engine 重放同一 snapshot 且没有虚构 job。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(harness.primary, _register(harness.primary, key="crash-begin"))
    pending, _ = _reserve_pending(
        harness.primary,
        active,
        key_suffix="crash-begin",
    )
    begun = harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    assert begun.action is ScheduleMaterializationAction.ENQUEUE
    assert begun.occurrence.state is ScheduleOccurrenceState.MATERIALIZING

    replay_page = harness.secondary.list_replayable(_SCOPE_A, None, limit=10)
    assert replay_page.occurrences == (begun.occurrence,)
    assert replay_page.next_pending_cursor is None
    replay = harness.secondary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.COMMITTED_REPLAY,
    )
    assert replay.action is ScheduleMaterializationAction.ENQUEUE
    assert replay.occurrence == begun.occurrence
    assert replay.occurrence.snapshot == pending.snapshot
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_runs WHERE tenant_id = :tenant_id",
            {"tenant_id": _TENANT_A.value},
        )
        == 0
    )


def test_crash_after_enqueue_before_mark_replays_frozen_request_and_reuses_one_job(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """job commit 后 occurrence 未 mark 的重启重放复用同一 PG job。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(harness.primary, _register(harness.primary, key="crash-enqueue"))
    pending, _ = _reserve_pending(
        harness.primary,
        active,
        key_suffix="crash-enqueue",
    )
    begun = harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    snapshot = begun.occurrence.snapshot
    assert snapshot is not None
    first_receipt = harness.jobs.enqueue(_SCOPE_A, _job_request(snapshot))
    still_open = harness.primary.get_occurrence(_SCOPE_A, pending.id)
    assert still_open is not None
    assert still_open.state is ScheduleOccurrenceState.MATERIALIZING
    assert still_open.job_id is None

    replay_page = harness.secondary.list_replayable(_SCOPE_A, None, limit=10)
    assert replay_page.occurrences == (still_open,)
    replay = harness.secondary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.COMMITTED_REPLAY,
    )
    assert replay.occurrence.snapshot == snapshot
    second_receipt = harness.secondary_jobs.enqueue(
        _SCOPE_A,
        _job_request(snapshot),
    )
    assert second_receipt.job_id == first_receipt.job_id
    assert second_receipt.idempotency_reused is True
    marked = harness.secondary.mark_enqueued(
        _SCOPE_A,
        pending.id,
        snapshot.request_fingerprint,
        second_receipt.job_id,
    )
    assert marked.action is ScheduleMarkEnqueuedAction.MARKED
    assert marked.occurrence.state is ScheduleOccurrenceState.ENQUEUED
    assert marked.occurrence.job_id == first_receipt.job_id
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_runs "
            "WHERE tenant_id = :tenant_id AND idempotency_key = :idempotency_key",
            {
                "tenant_id": _TENANT_A.value,
                "idempotency_key": snapshot.idempotency_key,
            },
        )
        == 1
    )
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_events "
            "WHERE tenant_id = :tenant_id AND job_run_id = :job_id "
            "AND event_type = 'job_created'",
            {"tenant_id": _TENANT_A.value, "job_id": first_receipt.job_id},
        )
        == 1
    )


def test_materialization_replay_builds_byte_identical_enqueue_request(
    harness: ScheduleHarness,
) -> None:
    """独立 engine 重读 MATERIALIZING 后重建逐字段相同 job request。

    Args:
        harness: 两条独立 app engine/store 集合。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(
        harness.primary, _register(harness.primary, key="byte-identical")
    )
    pending, _ = _reserve_pending(
        harness.primary,
        active,
        key_suffix="byte-identical",
    )
    assert pending.snapshot is not None
    original_request = _job_request(pending.snapshot)
    original_fingerprint = job_enqueue_request_fingerprint(original_request)
    harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )

    replay = harness.secondary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.COMMITTED_REPLAY,
    )
    assert replay.occurrence.snapshot is not None
    replay_request = _job_request(replay.occurrence.snapshot)
    assert replay_request == original_request
    assert (
        replay_request.payload.canonical_bytes
        == original_request.payload.canonical_bytes
    )
    assert replay_request.payload.sha256 == original_request.payload.sha256
    assert job_enqueue_request_fingerprint(replay_request) == original_fingerprint
    assert replay.occurrence.snapshot.request_fingerprint == original_fingerprint


def test_disable_before_materialization_linearization_skips_without_job(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """manual disable 先锁定时 PENDING 只转 SKIPPED 且绝不产生 job。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(harness.primary, _register(harness.primary, key="disable-first"))
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="disable-first",
    )
    disabled = harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=advanced.id,
            expected_version=advanced.version,
            target_state=ScheduleState.DISABLED,
        ),
        activation_next_fire_at=None,
    )
    assert disabled.action is ScheduleStateTransitionAction.APPLIED
    decision = harness.secondary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    assert decision.action is ScheduleMaterializationAction.SKIPPED
    assert decision.occurrence.state is ScheduleOccurrenceState.SKIPPED
    assert decision.occurrence.skip_reason is ScheduleSkipReason.SCHEDULE_DISABLED
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_runs WHERE tenant_id = :tenant_id",
            {"tenant_id": _TENANT_A.value},
        )
        == 0
    )


def test_disable_after_enqueue_commit_before_mark_reconciles_without_orphan_job(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """enqueue commit 后 disable 不撤销 MATERIALIZING，mark 绑定原 job。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(
        harness.primary, _register(harness.primary, key="disable-after-enqueue")
    )
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="disable-after-enqueue",
    )
    begun = harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    snapshot = begun.occurrence.snapshot
    assert snapshot is not None
    receipt = harness.jobs.enqueue(_SCOPE_A, _job_request(snapshot))
    disabled = harness.secondary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=advanced.id,
            expected_version=advanced.version,
            target_state=ScheduleState.DISABLED,
        ),
        activation_next_fire_at=None,
    )
    assert disabled.observation.definition.state is ScheduleState.DISABLED
    committed = harness.secondary.get_occurrence(_SCOPE_A, pending.id)
    assert committed is not None
    assert committed.state is ScheduleOccurrenceState.MATERIALIZING
    assert committed.job_id is None
    marked = harness.secondary.mark_enqueued(
        _SCOPE_A,
        pending.id,
        snapshot.request_fingerprint,
        receipt.job_id,
    )
    assert marked.action is ScheduleMarkEnqueuedAction.MARKED
    assert marked.occurrence.state is ScheduleOccurrenceState.ENQUEUED
    assert marked.occurrence.job_id == receipt.job_id
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_runs WHERE tenant_id = :tenant_id AND id = :job_id",
            {"tenant_id": _TENANT_A.value, "job_id": receipt.job_id},
        )
        == 1
    )


def test_disable_racing_pending_materialization_has_one_linearized_outcome(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """manual disable 与 PENDING begin 双 engine 只产生一个锁序结果。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(
        harness.primary, _register(harness.primary, key="disable-begin-race")
    )
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="disable-begin-race",
    )
    request = ScheduleActivationRequest(
        schedule_id=advanced.id,
        expected_version=advanced.version,
        target_state=ScheduleState.DISABLED,
    )
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        disable_future = executor.submit(
            _race_disable,
            harness.primary,
            barrier,
            request,
        )
        begin_future = executor.submit(
            _race_begin,
            harness.secondary,
            barrier,
            pending.id,
        )
        disable_action = disable_future.result(timeout=15)
        begin_action = begin_future.result(timeout=15)

    assert disable_action is ScheduleStateTransitionAction.APPLIED
    persisted_schedule = harness.primary.get(_SCOPE_A, advanced.id)
    persisted_occurrence = harness.primary.get_occurrence(_SCOPE_A, pending.id)
    assert persisted_schedule is not None
    assert persisted_schedule.definition.state is ScheduleState.DISABLED
    assert persisted_occurrence is not None
    if begin_action is ScheduleMaterializationAction.SKIPPED:
        assert persisted_occurrence.state is ScheduleOccurrenceState.SKIPPED
        assert persisted_occurrence.skip_reason is ScheduleSkipReason.SCHEDULE_DISABLED
        assert (
            _admin_count(
                schedule_db,
                f"SELECT count(*) FROM {_SCHEMA}.job_runs WHERE tenant_id = :tenant_id",
                {"tenant_id": _TENANT_A.value},
            )
            == 0
        )
    else:
        assert begin_action is ScheduleMaterializationAction.ENQUEUE
        assert persisted_occurrence.state is ScheduleOccurrenceState.MATERIALIZING
        assert persisted_occurrence.snapshot is not None
        receipt = harness.jobs.enqueue(
            _SCOPE_A,
            _job_request(persisted_occurrence.snapshot),
        )
        marked = harness.primary.mark_enqueued(
            _SCOPE_A,
            pending.id,
            persisted_occurrence.snapshot.request_fingerprint,
            receipt.job_id,
        )
        assert marked.action is ScheduleMarkEnqueuedAction.MARKED
        assert marked.occurrence.job_id == receipt.job_id


def test_concurrent_pending_replay_reuses_one_job_and_marks_one_occurrence(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """两个 scheduler 并发重放同一 PENDING 收敛为一 job/occurrence。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(
        harness.primary, _register(harness.primary, key="pending-replay-race")
    )
    pending, _ = _reserve_pending(
        harness.primary,
        active,
        key_suffix="pending-replay-race",
    )
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            _race_materialize,
            harness.primary,
            harness.jobs,
            barrier,
            pending.id,
        )
        second_future = executor.submit(
            _race_materialize,
            harness.secondary,
            harness.secondary_jobs,
            barrier,
            pending.id,
        )
        outcomes = (
            first_future.result(timeout=20),
            second_future.result(timeout=20),
        )

    assert all(
        outcome.begin_action is ScheduleMaterializationAction.ENQUEUE
        for outcome in outcomes
    )
    assert outcomes[0].job_id == outcomes[1].job_id
    assert sorted(outcome.idempotency_reused for outcome in outcomes) == [False, True]
    assert sorted(outcome.mark_action.value for outcome in outcomes) == [
        ScheduleMarkEnqueuedAction.IDEMPOTENT_REPLAY.value,
        ScheduleMarkEnqueuedAction.MARKED.value,
    ]
    persisted = harness.primary.get_occurrence(_SCOPE_A, pending.id)
    assert persisted is not None
    assert persisted.state is ScheduleOccurrenceState.ENQUEUED
    assert persisted.job_id == outcomes[0].job_id
    assert pending.snapshot is not None
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_runs "
            "WHERE tenant_id = :tenant_id AND idempotency_key = :idempotency_key",
            {
                "tenant_id": _TENANT_A.value,
                "idempotency_key": pending.snapshot.idempotency_key,
            },
        )
        == 1
    )
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_events "
            "WHERE tenant_id = :tenant_id AND job_run_id = :job_id "
            "AND event_type = 'job_created'",
            {"tenant_id": _TENANT_A.value, "job_id": outcomes[0].job_id},
        )
        == 1
    )


def test_two_schedulers_do_not_duplicate_or_skip_same_due_fire(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """两个 due reader 对同一 fire 并发 CAS 时一胜一负且只留一行。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(
        harness.primary, _register(harness.primary, key="two-schedulers")
    )
    _admin_execute(
        schedule_db,
        f"UPDATE {_SCHEMA}.job_schedules "
        "SET next_fire_at = clock_timestamp() - interval '1 minute' "
        "WHERE tenant_id = :tenant_id AND id = :schedule_id",
        {"tenant_id": _TENANT_A.value, "schedule_id": active.id},
    )
    first_page = harness.primary.list_due(_SCOPE_A, None, limit=1)
    second_page = harness.secondary.list_due(_SCOPE_A, None, limit=1)
    assert len(first_page.entries) == len(second_page.entries) == 1
    first_due = first_page.entries[0].observation.definition
    second_due = second_page.entries[0].observation.definition
    assert first_due == second_due
    assert first_due.next_fire_at is not None
    scheduled_for = first_due.next_fire_at
    batch = ScheduleReservationBatch(
        schedule_id=first_due.id,
        expected_version=first_due.version,
        expected_next_fire_at=scheduled_for,
        resulting_state=ScheduleState.ACTIVE,
        resulting_next_fire_at=scheduled_for + timedelta(minutes=1),
        reservations=(
            ScheduleOccurrenceReservation(
                scheduled_for=scheduled_for,
                state=ScheduleOccurrenceState.PENDING,
                snapshot=_snapshot(
                    first_due,
                    scheduled_for,
                    key_suffix="two-schedulers",
                ),
                coalesced_count=0,
                skip_reason=None,
            ),
        ),
    )
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            _race_reserve,
            harness.primary,
            barrier,
            batch,
        )
        second_future = executor.submit(
            _race_reserve,
            harness.secondary,
            barrier,
            batch,
        )
        results = (
            first_future.result(timeout=15),
            second_future.result(timeout=15),
        )

    assert sorted(result.action.value for result in results) == [
        ScheduleReserveAction.LOST_RACE.value,
        ScheduleReserveAction.RESERVED.value,
    ]
    assert sorted(len(result.occurrences) for result in results) == [0, 1]
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_schedule_occurrences "
            "WHERE tenant_id = :tenant_id AND schedule_id = :schedule_id "
            "AND schedule_version = :schedule_version AND scheduled_for = :scheduled_for",
            {
                "tenant_id": _TENANT_A.value,
                "schedule_id": first_due.id,
                "schedule_version": first_due.version,
                "scheduled_for": scheduled_for,
            },
        )
        == 1
    )
    replay = harness.primary.list_replayable(_SCOPE_A, None, limit=10)
    assert len(replay.occurrences) == 1
    assert replay.occurrences[0].scheduled_for == scheduled_for


def test_manual_and_scan_limit_disable_preserve_audit_cursor(
    harness: ScheduleHarness,
) -> None:
    """manual 与 scan-limit 两种 disable 都保留各自持久审计 cursor。

    Args:
        harness: 两条独立 app engine/store 集合。

    Returns:
        无。

    Raises:
        无。
    """

    manual_active = _activate(
        harness.primary,
        _register(harness.primary, key="manual-cursor"),
    )
    assert manual_active.next_fire_at is not None
    manual_cursor = manual_active.next_fire_at
    manual = harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=manual_active.id,
            expected_version=manual_active.version,
            target_state=ScheduleState.DISABLED,
        ),
        activation_next_fire_at=None,
    )
    assert manual.observation.definition.next_fire_at == manual_cursor

    scan_active = _activate(
        harness.primary,
        _register(harness.primary, key="scan-cursor"),
    )
    assert scan_active.next_fire_at is not None
    scan_cursor = scan_active.next_fire_at
    scan = harness.primary.reserve_occurrences(
        _SCOPE_A,
        ScheduleReservationBatch(
            schedule_id=scan_active.id,
            expected_version=scan_active.version,
            expected_next_fire_at=scan_cursor,
            resulting_state=ScheduleState.DISABLED,
            resulting_next_fire_at=scan_cursor,
            reservations=(
                ScheduleOccurrenceReservation(
                    scheduled_for=scan_cursor,
                    state=ScheduleOccurrenceState.SKIPPED,
                    snapshot=None,
                    coalesced_count=None,
                    skip_reason=ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED,
                ),
            ),
        ),
    )
    assert scan.action is ScheduleReserveAction.RESERVED
    scan_persisted = harness.secondary.get(_SCOPE_A, scan_active.id)
    assert scan_persisted is not None
    assert scan_persisted.definition.state is ScheduleState.DISABLED
    assert scan_persisted.definition.next_fire_at == scan_cursor
    assert scan.occurrences[0].scheduled_for == scan_cursor
    assert (
        scan.occurrences[0].skip_reason
        is ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED
    )


def test_mixed_capability_scheduler_cannot_skip_fire_available_to_another_process(
    harness: ScheduleHarness,
    schedule_db: tuple[PlatformCluster, str],
) -> None:
    """negative admission 保留 PENDING，另一个 capable process 可提交同 fire。

    Args:
        harness: 两条独立 app engine/store 集合。
        schedule_db: 独立真实 PostgreSQL 16 数据库。

    Returns:
        无。

    Raises:
        无。
    """

    active = _activate(
        harness.primary, _register(harness.primary, key="mixed-capability")
    )
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="mixed-capability",
    )
    unavailable = harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_UNAVAILABLE,
    )
    assert unavailable.action is ScheduleMaterializationAction.UNAVAILABLE
    after_negative = harness.secondary.get_occurrence(_SCOPE_A, pending.id)
    assert after_negative == pending
    schedule_after_negative = harness.secondary.get(_SCOPE_A, advanced.id)
    assert schedule_after_negative is not None
    assert schedule_after_negative.definition == advanced

    capable = harness.secondary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    assert capable.action is ScheduleMaterializationAction.ENQUEUE
    snapshot = capable.occurrence.snapshot
    assert snapshot is not None
    receipt = harness.secondary_jobs.enqueue(_SCOPE_A, _job_request(snapshot))
    marked = harness.secondary.mark_enqueued(
        _SCOPE_A,
        pending.id,
        snapshot.request_fingerprint,
        receipt.job_id,
    )
    assert marked.action is ScheduleMarkEnqueuedAction.MARKED
    assert marked.occurrence.state is ScheduleOccurrenceState.ENQUEUED
    assert marked.occurrence.skip_reason is None
    assert (
        _admin_count(
            schedule_db,
            f"SELECT count(*) FROM {_SCHEMA}.job_runs WHERE tenant_id = :tenant_id AND id = :job_id",
            {"tenant_id": _TENANT_A.value, "job_id": receipt.job_id},
        )
        == 1
    )


def test_materialization_linearization_before_disable_finishes_same_job(
    harness: ScheduleHarness,
) -> None:
    """begin 先赢后 disable 不撤销 commitment，mark 仍绑定同一 job。"""

    active = _activate(
        harness.primary, _register(harness.primary, key="mark-after-disable")
    )
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="mark-after-disable",
    )
    begun = harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    assert begun.occurrence.snapshot is not None
    harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=advanced.id,
            expected_version=advanced.version,
            target_state=ScheduleState.DISABLED,
        ),
        activation_next_fire_at=None,
    )
    snapshot = begun.occurrence.snapshot
    receipt = harness.jobs.enqueue(
        _SCOPE_A,
        JobEnqueueRequest(
            descriptor=snapshot.descriptor,
            idempotency_key=snapshot.idempotency_key,
            payload=snapshot.payload,
            available_at=snapshot.available_at,
            deadline_at=snapshot.deadline_at,
        ),
    )
    marked = harness.primary.mark_enqueued(
        _SCOPE_A,
        pending.id,
        snapshot.request_fingerprint,
        receipt.job_id,
    )
    assert marked.action is ScheduleMarkEnqueuedAction.MARKED
    assert marked.occurrence.job_id == receipt.job_id
    replay = harness.primary.mark_enqueued(
        _SCOPE_A,
        pending.id,
        snapshot.request_fingerprint,
        receipt.job_id,
    )
    assert replay.action is ScheduleMarkEnqueuedAction.IDEMPOTENT_REPLAY
    terminal = harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.COMMITTED_REPLAY,
    )
    assert terminal.action is ScheduleMaterializationAction.ALREADY_ENQUEUED
    with pytest.raises(ScheduleInvariantError):
        harness.primary.mark_enqueued(
            _SCOPE_A,
            pending.id,
            snapshot.request_fingerprint,
            uuid4(),
        )


def test_store_closed_noop_lost_race_and_input_matrix(
    harness: ScheduleHarness,
) -> None:
    """valid closed edge inputs cover no-op、lost-race 与 fail-fast 分支。"""

    zero_uuid = UUID(int=0)
    zero_scope = Principal(
        tenant_id=TenantId(str(zero_uuid)),
        user_id="zero-tenant",
    ).to_scope()
    with pytest.raises(ScheduleInputError):
        harness.primary.get(zero_scope, uuid4())
    with pytest.raises(ScheduleInputError):
        harness.primary.get(_SCOPE_A, zero_uuid)
    with pytest.raises(ScheduleInputError):
        harness.primary.get_occurrence(_SCOPE_A, zero_uuid)
    with pytest.raises(ScheduleInputError):
        harness.primary.list_due(_SCOPE_A, None, limit=0)
    with pytest.raises(ScheduleInputError):
        harness.primary.list_replayable(_SCOPE_A, None, limit=False)
    with pytest.raises(ScheduleInputError):
        harness.primary.begin_materialization(
            _SCOPE_A,
            zero_uuid,
            admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
        )
    with pytest.raises(ScheduleInputError):
        harness.primary.mark_enqueued(
            _SCOPE_A,
            uuid4(),
            "not-a-fingerprint",
            uuid4(),
        )

    draft = _register(harness.primary, key="closed-matrix")
    with pytest.raises(ScheduleVersionConflictError):
        harness.primary.register(_SCOPE_A, _registration(key="closed-matrix"))
    active = _activate(harness.primary, draft)
    unchanged = harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=active.id,
            expected_version=active.version,
            target_state=ScheduleState.ACTIVE,
        ),
        activation_next_fire_at=None,
    )
    assert unchanged.action is ScheduleStateTransitionAction.UNCHANGED
    assert unchanged.observation.definition == active
    assert active.next_fire_at is not None
    stale_result = harness.primary.reserve_occurrences(
        _SCOPE_A,
        ScheduleReservationBatch(
            schedule_id=active.id,
            expected_version=active.version + 1,
            expected_next_fire_at=active.next_fire_at,
            resulting_state=ScheduleState.ACTIVE,
            resulting_next_fire_at=active.next_fire_at + timedelta(minutes=1),
            reservations=(
                ScheduleOccurrenceReservation(
                    scheduled_for=active.next_fire_at,
                    state=ScheduleOccurrenceState.PENDING,
                    snapshot=_snapshot(
                        active,
                        active.next_fire_at,
                        key_suffix="lost-race",
                    ),
                    coalesced_count=0,
                    skip_reason=None,
                ),
            ),
        ),
    )
    assert stale_result.action is ScheduleReserveAction.LOST_RACE
    assert stale_result.occurrences == ()
    assert harness.primary.list_replayable(_SCOPE_A, None, limit=10).occurrences == ()
    assert harness.primary.get(_SCOPE_A, uuid4()) is None
    assert harness.primary.get_occurrence(_SCOPE_A, uuid4()) is None


def test_reenable_overwrites_preserved_cursor_from_fresh_pg_clock_without_reviving_occurrences(
    harness: ScheduleHarness,
) -> None:
    """re-enable 覆盖审计 cursor，disabled occurrence 保持终态。"""

    active = _activate(harness.primary, _register(harness.primary, key="reenable"))
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="reenable",
    )
    disabled = harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=advanced.id,
            expected_version=advanced.version,
            target_state=ScheduleState.DISABLED,
        ),
        activation_next_fire_at=None,
    )
    old_cursor = disabled.observation.definition.next_fire_at
    same_disabled = harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=advanced.id,
            expected_version=disabled.observation.definition.version,
            target_state=ScheduleState.DISABLED,
        ),
        activation_next_fire_at=None,
    )
    assert same_disabled.action is ScheduleStateTransitionAction.UNCHANGED
    fresh = harness.primary.get(_SCOPE_A, advanced.id)
    assert fresh is not None
    new_cursor = fresh.database_now + timedelta(minutes=10)
    reenabled = harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=advanced.id,
            expected_version=fresh.definition.version,
            target_state=ScheduleState.ACTIVE,
        ),
        activation_next_fire_at=new_cursor,
    )
    assert reenabled.action is ScheduleStateTransitionAction.APPLIED
    assert reenabled.observation.definition.next_fire_at == new_cursor
    assert new_cursor != old_cursor
    old_occurrence = harness.primary.get_occurrence(_SCOPE_A, pending.id)
    assert old_occurrence is not None
    assert old_occurrence.state is ScheduleOccurrenceState.SKIPPED
    assert old_occurrence.skip_reason is ScheduleSkipReason.SCHEDULE_DISABLED


def test_pending_committed_replay_and_skipped_mark_conflicts_are_closed(
    harness: ScheduleHarness,
) -> None:
    """PENDING replay/mark fail closed，SKIPPED 返回 closed no-work/conflict。"""

    active = _activate(
        harness.primary, _register(harness.primary, key="terminal-matrix")
    )
    pending, advanced = _reserve_pending(
        harness.primary,
        active,
        key_suffix="terminal-matrix",
    )
    assert pending.snapshot is not None
    with pytest.raises(ScheduleInvariantError):
        harness.primary.begin_materialization(
            _SCOPE_A,
            pending.id,
            admission=ScheduleMaterializationAdmission.COMMITTED_REPLAY,
        )
    with pytest.raises(ScheduleInvariantError):
        harness.primary.mark_enqueued(
            _SCOPE_A,
            pending.id,
            pending.snapshot.request_fingerprint,
            uuid4(),
        )
    harness.primary.set_state(
        _SCOPE_A,
        ScheduleActivationRequest(
            schedule_id=advanced.id,
            expected_version=advanced.version,
            target_state=ScheduleState.DISABLED,
        ),
        activation_next_fire_at=None,
    )
    skipped = harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    assert skipped.action is ScheduleMaterializationAction.SKIPPED
    conflict = harness.primary.mark_enqueued(
        _SCOPE_A,
        pending.id,
        pending.snapshot.request_fingerprint,
        uuid4(),
    )
    assert conflict.action is ScheduleMarkEnqueuedAction.SKIPPED_CONFLICT
    assert harness.primary.list_replayable(_SCOPE_A, None, limit=10).occurrences == ()


def test_mark_rejects_materializing_snapshot_fingerprint_drift(
    harness: ScheduleHarness,
) -> None:
    """MATERIALIZING mark 必须逐字段重验 frozen fingerprint。"""

    active = _activate(harness.primary, _register(harness.primary, key="mark-drift"))
    pending, _ = _reserve_pending(
        harness.primary,
        active,
        key_suffix="mark-drift",
    )
    harness.primary.begin_materialization(
        _SCOPE_A,
        pending.id,
        admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
    )
    with pytest.raises(ScheduleInvariantError):
        harness.primary.mark_enqueued(
            _SCOPE_A,
            pending.id,
            "0" * 64,
            uuid4(),
        )
    persisted = harness.primary.get_occurrence(_SCOPE_A, pending.id)
    assert persisted is not None
    assert persisted.state is ScheduleOccurrenceState.MATERIALIZING


def test_transition_candidate_and_missing_identity_fail_closed(
    harness: ScheduleHarness,
) -> None:
    """candidate/source matrix 与缺失 identity 均 fail closed 且零修改。"""

    draft = _register(harness.primary, key="invalid-transition")
    active_request = ScheduleActivationRequest(
        schedule_id=draft.id,
        expected_version=draft.version,
        target_state=ScheduleState.ACTIVE,
    )
    with pytest.raises(ScheduleInvariantError):
        harness.primary.set_state(
            _SCOPE_A,
            active_request,
            activation_next_fire_at=None,
        )
    active = _activate(harness.primary, draft)
    assert active.next_fire_at is not None
    with pytest.raises(ScheduleInvariantError):
        harness.primary.set_state(
            _SCOPE_A,
            ScheduleActivationRequest(
                schedule_id=active.id,
                expected_version=active.version,
                target_state=ScheduleState.ACTIVE,
            ),
            activation_next_fire_at=active.next_fire_at + timedelta(minutes=1),
        )
    with pytest.raises(ScheduleInvariantError):
        harness.primary.set_state(
            _SCOPE_A,
            ScheduleActivationRequest(
                schedule_id=active.id,
                expected_version=active.version,
                target_state=ScheduleState.DISABLED,
            ),
            activation_next_fire_at=active.next_fire_at,
        )
    with pytest.raises(ScheduleVersionConflictError):
        harness.primary.set_state(
            _SCOPE_A,
            ScheduleActivationRequest(
                schedule_id=uuid4(),
                expected_version=1,
                target_state=ScheduleState.DISABLED,
            ),
            activation_next_fire_at=None,
        )
    missing_occurrence = uuid4()
    with pytest.raises(ScheduleInvariantError):
        harness.primary.begin_materialization(
            _SCOPE_A,
            missing_occurrence,
            admission=ScheduleMaterializationAdmission.PENDING_AVAILABLE,
        )
    with pytest.raises(ScheduleInvariantError):
        harness.primary.mark_enqueued(
            _SCOPE_A,
            missing_occurrence,
            "0" * 64,
            uuid4(),
        )
    persisted = harness.primary.get(_SCOPE_A, active.id)
    assert persisted is not None
    assert persisted.definition == active
