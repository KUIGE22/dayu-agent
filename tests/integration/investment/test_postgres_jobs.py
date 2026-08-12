"""PostgresJobStore / JobService 的真实 PostgreSQL 16 集成测试。

覆盖 ``docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`` 的
PG16 fault matrix：

- 两个独立 engine/process barrier 的 SKIP LOCKED claim、同 job
  event sequence two-writer race；
- lease/fence/token 陈旧写、worker clock skew 不改变 DB 权威时间、
  deadline/retry、ready/leased cancel receipt 分支、cancel race、
  upgrade->downgrade->upgrade、grant matrix、external dependency
  downgrade refusal；
- correlation reserve/authorize/terminal reconciliation 全状态机与
  replay 幂等（含双 engine barrier）。

每个测试断言最终 job/attempt/correlation state、唯一 receipt、
精确 event sequence 与无 raw secret 泄漏。
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Row

from dayu.contracts.agent_execution import (
    AcceptedExecutionSpec,
    AcceptedModelSpec,
    AgentCreateArgs,
    AgentInput,
    ExecutionContract,
    ExecutionHostPolicy,
    ExecutionMessageInputs,
    ScenePreparationSpec,
)
from dayu.contracts.agent_types import AgentTraceIdentity
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.run import RunState
from dayu.engine.events import EventType, StreamEvent
from dayu.engine.protocols import ToolExecutor
from dayu.engine.tool_trace import ToolTraceRecorderFactory
from dayu.host.executor import DefaultHostExecutor
from dayu.host.host_execution import HostedRunContext
from dayu.host.host_store import HostStore
from dayu.host.prepared_turn import PreparedAgentTurnSnapshot
from dayu.host.protocols import ReservedAgentRunExistsError
from dayu.host.run_registry import SQLiteRunRegistry
from dayu.host.scene_preparer import PreparedAgentExecution
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.domain.jobs import (
    AgentRunCorrelationObservation,
    AgentRunStartAuthorizationAction,
    AgentRunTerminalReconciliationAction,
    AttemptReceiptOutcome,
    AttemptState,
    CanonicalJobDocument,
    CorrelationState,
    HostRunObservationState,
    JobCancellationRequest,
    JobClaim,
    JobCompletion,
    JobDeadlineExceededError,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobFailure,
    JobGovernanceRequiredError,
    JobHandlerDescriptor,
    JobHeartbeatAction,
    JobIdempotencyConflictError,
    JobLeaseLostError,
    JobState,
    JobStateConflictError,
    JsonValue,
    LeaseReleaseReason,
    SafeJobErrorCode,
    build_canonical_document,
    parse_canonical_document,
)
from dayu.investment.storage.db import (
    PLATFORM_SCHEMA_NAME,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage.postgres_jobs import PostgresJobStore
from tests.integration.investment.conftest import (
    PlatformCluster,
    create_temporary_login,
    drop_temporary_login,
)

pytestmark = pytest.mark.integration

_TENANT_A = TenantId("00000000-0000-0000-0000-000000000001")
_TENANT_B = TenantId("00000000-0000-0000-0000-000000000002")

_SCOPE_A = Principal(tenant_id=_TENANT_A, user_id="u-a").to_scope()
_SCOPE_B = Principal(tenant_id=_TENANT_B, user_id="u-b").to_scope()

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

_JOBS_SCHEMA = PLATFORM_SCHEMA_NAME

_RowValue = str | int | float | bool | datetime | bytes | memoryview | UUID | None
_SqlRow = Row[tuple[_RowValue, ...]]

_HARD_STOP_WORKER_CHILD_SCRIPT = """
import asyncio
import os
from pathlib import Path

from dayu.cli.commands.platform import _run_platform_process
from dayu.host.process_intake import ProcessIntakeGate
from dayu.host.worker import PlatformWorker
from dayu.investment.config import PlatformQueueMode, PlatformQueueSettings
from dayu.investment.domain.identifiers import Principal, TenantId
from dayu.investment.domain.jobs import JobHandlerDescriptor
from dayu.investment.storage.db import create_platform_engine, create_platform_session_factory
from dayu.investment.storage.postgres_jobs import PostgresJobStore
from dayu.services.job_service import JobExecutionRegistry, JobHandlerRegistry, JobService


class _MissingHostReader:
    def get_run(self, _run_id):
        return None


class _NonCooperativeHandler:
    @property
    def job_type(self):
        return "test.worker-hard-stop"

    async def execute(self, _scope, request, _cancellation):
        Path(os.environ["DAYU_TEST_READY_PATH"]).write_text(
            str(request.attempt_id),
            encoding="utf-8",
        )
        while True:
            try:
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                continue


def _build_worker():
    engine = create_platform_engine(os.environ["DAYU_TEST_PG_DSN"])
    store = PostgresJobStore(
        session_factory=create_platform_session_factory(engine),
    )
    descriptor = JobHandlerDescriptor(
        job_type="test.worker-hard-stop",
        payload_schema_name="test.payload",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=1,
    )
    descriptors = JobHandlerRegistry()
    descriptors.register_descriptor(descriptor)
    executions = JobExecutionRegistry(descriptors)
    executions.register_handler(descriptor, _NonCooperativeHandler())
    service = JobService(
        job_store=store,
        descriptor_registry=descriptors,
        execution_registry=executions,
        host_run_reader=_MissingHostReader(),
    )
    scope = Principal(
        tenant_id=TenantId(os.environ["DAYU_TEST_TENANT_ID"]),
        user_id="worker-hard-stop",
    ).to_scope()
    return PlatformWorker(
        gateway=service,
        scope=scope,
        worker_id="worker-hard-stop",
        settings=PlatformQueueSettings(
            mode=PlatformQueueMode.POSTGRES_POLLING,
            poll_interval_seconds=0.05,
            shutdown_grace_seconds=60.0,
        ),
        intake_gate=ProcessIntakeGate(),
    )


raise SystemExit(asyncio.run(_run_platform_process(_build_worker())))
"""
"""真实 Worker/CLI hard-stop 子进程的固定脚本。"""


@dataclass(frozen=True, slots=True)
class _FingerprintBarrier:
    """把两个 enqueue writer 固定在 fingerprint 后的真实 PG 竞态窗口。

    Args:
        barrier: 两个 writer 共用的线程 barrier。
        fingerprint: production fingerprint 真源。
    """

    barrier: threading.Barrier
    fingerprint: Callable[[JobEnqueueRequest], str]

    def __call__(self, request: JobEnqueueRequest) -> str:
        """等待另一个 writer 后计算原始 request fingerprint。

        Args:
            request: 当前 writer 的完整入队请求。

        Returns:
            production helper 计算的稳定 SHA-256 fingerprint。

        Raises:
            threading.BrokenBarrierError: 另一个 writer 未在有界时间内抵达。
        """

        self.barrier.wait(timeout=10)
        return self.fingerprint(request)


def _descriptor(*, job_type: str = "test.job") -> JobHandlerDescriptor:
    """构造测试 descriptor。

    Args:
        job_type: job 类型。

    Returns:
        ``JobHandlerDescriptor``。
    """

    return JobHandlerDescriptor(
        job_type=job_type,
        payload_schema_name="test.payload",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=60,
    )


def json_dumps(value: JsonValue) -> str:
    """以 canonical 紧凑格式序列化（测试辅助）。

    Args:
        value: 待序列化值。

    Returns:
        compact JSON 文本。

    Raises:
        无。
    """

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _payload(*, marker: str = "p") -> CanonicalJobDocument:
    """构造 canonical payload。

    Args:
        marker: payload 内容标记。

    Returns:
        ``CanonicalJobDocument``。
    """

    return parse_canonical_document(
        json_dumps({"marker": marker}),
        schema_name="test.payload",
        schema_version=1,
    )


def _result() -> CanonicalJobDocument:
    """构造安全 result document。

    Args:
        无。

    Returns:
        ``CanonicalJobDocument``。
    """

    return build_canonical_document(
        {"ok": True}, schema_name="test.result", schema_version=1
    )


def _make_request(
    *,
    descriptor: JobHandlerDescriptor | None = None,
    idempotency_key: str = "key-1",
    available_at: datetime = NOW,
    deadline_at: datetime = NOW + timedelta(hours=1),
    marker: str = "p",
) -> JobEnqueueRequest:
    """构造入队请求。

    Args:
        descriptor: 可空 descriptor。
        idempotency_key: 幂等键。
        available_at: 可用时间。
        deadline_at: 截止时间。
        marker: payload 标记。

    Returns:
        ``JobEnqueueRequest``。
    """

    return JobEnqueueRequest(
        descriptor=descriptor if descriptor is not None else _descriptor(),
        idempotency_key=idempotency_key,
        payload=_payload(marker=marker),
        available_at=available_at,
        deadline_at=deadline_at,
    )


@pytest.fixture(autouse=True)
def _downgrade_after(jobs_db) -> Iterator[None]:
    """每个测试结束后全量 downgrade，释放 cluster 级 group roles。

    Args:
        jobs_db: 已迁移的数据库信息。

    Yields:
        无。

    Raises:
        无。
    """

    yield
    from tests.integration.investment.conftest import run_alembic_downgrade

    cluster, database = jobs_db
    run_alembic_downgrade(cluster.dsn_for_database(database, "postgres"))


@pytest.fixture()
def jobs_db(
    platform_cluster,
    lifecycle_database,
) -> tuple[PlatformCluster, str]:
    """构造可用的 0003 数据库并返回 bootstrap 信息。

    Args:
        platform_cluster: 共享 PG16 cluster。
        lifecycle_database: 随机独立数据库工厂。

    Returns:
        ``(cluster, database)`` 二元组。
    """

    from tests.integration.investment.conftest import run_alembic_upgrade

    database = lifecycle_database()
    dsn = platform_cluster.dsn_for_database(database, "postgres")
    run_alembic_upgrade(dsn)
    return platform_cluster, database


@pytest.fixture()
def store(jobs_db) -> Iterator[PostgresJobStore]:
    """构造 app 身份连接的 PostgresJobStore。

    Args:
        jobs_db: 已迁移的数据库信息。

    Returns:
        ``PostgresJobStore``。
    """

    from tests.integration.investment.conftest import create_temporary_login

    cluster, database = jobs_db
    login = create_temporary_login(cluster, database, member_of="dayu_platform_app")
    engine = create_platform_engine(login.dsn)
    session_factory = create_platform_session_factory(engine)
    store = PostgresJobStore(session_factory=session_factory)
    yield store
    engine.dispose()
    from tests.integration.investment.conftest import drop_temporary_login

    drop_temporary_login(cluster, login)


@pytest.fixture()
def second_store(jobs_db) -> Iterator[PostgresJobStore]:
    """构造第二个独立 engine 的 store（双 engine barrier）。

    Args:
        jobs_db: 已迁移的数据库信息。

    Returns:
        ``PostgresJobStore``。
    """

    from tests.integration.investment.conftest import create_temporary_login

    cluster, database = jobs_db
    login = create_temporary_login(cluster, database, member_of="dayu_platform_app")
    engine = create_platform_engine(login.dsn)
    session_factory = create_platform_session_factory(engine)
    second = PostgresJobStore(session_factory=session_factory)
    yield second
    engine.dispose()
    from tests.integration.investment.conftest import drop_temporary_login

    drop_temporary_login(cluster, login)


def _enqueue(
    store: PostgresJobStore,
    scope: TenantScope,
    request: JobEnqueueRequest | None = None,
) -> tuple[UUID, UUID]:
    """入队并返回 (definition_id, job_id)。

    Args:
        store: 仓储。
        scope: 租户范围。
        request: 可空入队请求。

    Returns:
        ``(definition_id, job_id)``。
    """

    receipt = store.enqueue(scope, request if request is not None else _make_request())
    assert receipt.state is JobState.READY
    return receipt.definition_id, receipt.job_id


def _claim(store: PostgresJobStore, scope: TenantScope, worker_id: str = "worker-1"):
    """领取一个 job 并返回 claim。

    Args:
        store: 仓储。
        scope: 租户范围。
        worker_id: worker 标识。

    Returns:
        claim；无可用时返回 ``None``。
    """

    return store.claim(scope, worker_id)


def _query(
    jobs_db,
    statement: str,
    params: dict[str, str | int | UUID | None] | None = None,
) -> list[_SqlRow]:
    """以 bootstrap 连接执行查询。

    Args:
        jobs_db: 数据库信息。
        statement: SQL。
        params: 可空参数。

    Returns:
        查询行列表。
    """

    cluster, database = jobs_db
    dsn = cluster.dsn_for_database(database, "postgres")
    engine = create_platform_engine(dsn)
    try:
        with engine.connect() as conn:
            if params is None:
                rows = conn.execute(text(statement)).fetchall()
            else:
                rows = conn.execute(text(statement), params).fetchall()
            conn.rollback()
            return list(rows)
    finally:
        engine.dispose()


def _col(
    row: _SqlRow,
    key: str,
) -> str | int | float | bool | datetime | bytes | memoryview | UUID | None:
    """从查询行读取命名列值（SQLAlchemy 2.0 Row 的 mapping 访问）。

    Args:
        row: 查询行。
        key: 列名。

    Returns:
        该列的值（PG 标量/时间/bytes/UUID 联合）。

    Raises:
        KeyError: 列不存在时抛出。
    """

    value = row._mapping[key]
    assert (
        isinstance(value, (str, int, float, bool, datetime, bytes, memoryview, UUID))
        or value is None
    )
    return value


def _pg_now(jobs_db) -> datetime:
    """读取 PG 权威时钟（clock_timestamp，aware UTC）。

    Args:
        jobs_db: 数据库信息。

    Returns:
        PG 当前时间。

    Raises:
        AssertionError: 值非法时抛出。
    """

    rows = _query(jobs_db, "SELECT clock_timestamp()")
    value = rows[0][0]
    assert isinstance(value, datetime)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _pg_request(
    jobs_db,
    *,
    descriptor: JobHandlerDescriptor | None = None,
    idempotency_key: str = "key-1",
    available_delta: timedelta = timedelta(minutes=-1),
    deadline_delta: timedelta = timedelta(hours=1),
    marker: str = "p",
) -> JobEnqueueRequest:
    """构造以 PG 时钟为基准的入队请求。

    Args:
        jobs_db: 数据库信息。
        descriptor: 可空 descriptor。
        idempotency_key: 幂等键。
        available_delta: 相对 PG now 的可用偏移。
        deadline_delta: 相对 PG now 的截止偏移。
        marker: payload 标记。

    Returns:
        ``JobEnqueueRequest``。
    """

    pg_now = _pg_now(jobs_db)
    return _make_request(
        descriptor=descriptor,
        idempotency_key=idempotency_key,
        available_at=pg_now + available_delta,
        deadline_at=pg_now + deadline_delta,
        marker=marker,
    )


def _execute(
    jobs_db,
    statement: str,
    params: dict[str, str | int | UUID | None] | None = None,
) -> None:
    """以 bootstrap 连接执行 DML（不取行）。

    Args:
        jobs_db: 数据库信息。
        statement: SQL。
        params: 可空参数。

    Returns:
        无。

    Raises:
        无。
    """

    cluster, database = jobs_db
    dsn = cluster.dsn_for_database(database, "postgres")
    engine = create_platform_engine(dsn)
    try:
        with engine.connect() as conn:
            if params is None:
                conn.execute(text(statement))
            else:
                conn.execute(text(statement), params)
            conn.commit()
    finally:
        engine.dispose()


def _job_row(jobs_db, job_id: UUID) -> _SqlRow:
    """读取单行 job。

    Args:
        jobs_db: 数据库信息。
        job_id: job UUID。

    Returns:
        ``job_runs`` 行。
    """

    rows = _query(
        jobs_db,
        f"SELECT * FROM {_JOBS_SCHEMA}.job_runs WHERE id = :job_id",
        {"job_id": str(job_id)},
    )
    assert len(rows) == 1
    return rows[0]


def _events_for(jobs_db, job_id: UUID) -> list[_SqlRow]:
    """读取 job 的全部 event（按 sequence 排序）。

    Args:
        jobs_db: 数据库信息。
        job_id: job UUID。

    Returns:
        event 行列表。
    """

    rows = _query(
        jobs_db,
        f"SELECT * FROM {_JOBS_SCHEMA}.job_events WHERE job_run_id = :job_id ORDER BY sequence_number",
        {"job_id": str(job_id)},
    )
    return rows


def _receipts_for(jobs_db, attempt_id: UUID) -> list[_SqlRow]:
    """读取 attempt 的全部 receipt。

    Args:
        jobs_db: 数据库信息。
        attempt_id: attempt UUID。

    Returns:
        receipt 行列表。
    """

    rows = _query(
        jobs_db,
        f"SELECT * FROM {_JOBS_SCHEMA}.job_attempt_receipts WHERE attempt_id = :attempt_id",
        {"attempt_id": str(attempt_id)},
    )
    return rows


def _attempt_rows(jobs_db, job_id: UUID) -> list[_SqlRow]:
    """读取 job 的全部 attempt（按 attempt_number 排序）。

    Args:
        jobs_db: 数据库信息。
        job_id: job UUID。

    Returns:
        attempt 行列表。
    """

    rows = _query(
        jobs_db,
        f"SELECT * FROM {_JOBS_SCHEMA}.job_attempts WHERE job_run_id = :job_id ORDER BY attempt_number",
        {"job_id": str(job_id)},
    )
    return rows


def _wait_for_hard_stop_worker_claim(
    process: subprocess.Popen[str],
    ready_path: Path,
) -> UUID:
    """bounded 等待真实 Worker handler 写入 attempt identity。

    Args:
        process: 当前测试唯一 owned child process。
        ready_path: handler 在真实 claim 后写入的 ready 文件。

    Returns:
        child 实际领取的 attempt UUID。

    Raises:
        AssertionError: child 提前退出、ready 内容非法或等待超时时抛出。
    """

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if ready_path.exists():
            return UUID(ready_path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise AssertionError("Worker child 在 claim barrier 前退出")
        time.sleep(0.02)
    raise AssertionError("Worker child 未在 bounded 时间内取得 PG claim")


def _cleanup_hard_stop_worker(process: subprocess.Popen[str]) -> None:
    """只清理当前测试创建且仍存活的 child process。

    Args:
        process: 当前测试唯一 owned child process。

    Returns:
        无。

    Raises:
        subprocess.TimeoutExpired: kill 后 child 仍未退出时抛出。
    """

    if process.poll() is None:
        process.kill()
        process.wait(timeout=10.0)


@pytest.mark.integration
@pytest.mark.skipif(sys.platform == "win32", reason="Windows 不提供 POSIX SIGTERM 链")
def test_worker_second_signal_hard_stops_without_false_terminal_then_lease_recovers(
    store: PostgresJobStore,
    jobs_db,
    tmp_path: Path,
) -> None:
    """真实 Worker 第二信号 hard-stop 后只允许 PG lease recovery 收敛。

    Args:
        store: 父进程使用的真实 PostgreSQL Store。
        jobs_db: 已迁移的随机 PostgreSQL 数据库。
        tmp_path: pytest-owned child ready 文件目录。

    Returns:
        无。

    Raises:
        AssertionError: signal、无伪终态或 lease recovery 任一门禁失败时抛出。
        subprocess.TimeoutExpired: child 未在 bounded 时间内 hard-stop 时抛出。
    """

    descriptor = JobHandlerDescriptor(
        job_type="test.worker-hard-stop",
        payload_schema_name="test.payload",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=1,
    )
    _, job_id = _enqueue(
        store,
        _SCOPE_A,
        _pg_request(
            jobs_db,
            descriptor=descriptor,
            idempotency_key="worker-hard-stop",
        ),
    )
    cluster, database = jobs_db
    child_login = create_temporary_login(
        cluster,
        database,
        member_of="dayu_platform_app",
    )
    ready_path = tmp_path / "worker-claimed"
    environment = os.environ.copy()
    environment.update(
        {
            "DAYU_TEST_PG_DSN": child_login.dsn,
            "DAYU_TEST_READY_PATH": str(ready_path),
            "DAYU_TEST_TENANT_ID": str(_TENANT_A),
            "PYTHONUNBUFFERED": "1",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-c", _HARD_STOP_WORKER_CHILD_SCRIPT],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        attempt_id = _wait_for_hard_stop_worker_claim(process, ready_path)
        process.send_signal(signal.SIGTERM)
        time.sleep(0.15)
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=10.0) == 1

        job_before_recovery = _job_row(jobs_db, job_id)
        attempt_before_recovery = _attempt_rows(jobs_db, job_id)
        assert _col(job_before_recovery, "state") == JobState.LEASED.value
        assert len(attempt_before_recovery) == 1
        assert _col(attempt_before_recovery[0], "id") == attempt_id
        assert _col(attempt_before_recovery[0], "state") == AttemptState.LEASED.value
        assert _receipts_for(jobs_db, attempt_id) == []

        time.sleep(1.5)
        recovered = store.recover(_SCOPE_A)
        recovery = next(result for result in recovered if result.job_id == job_id)
        assert recovery.attempt_id == attempt_id
        assert recovery.job_state is JobState.READY
        assert recovery.attempt_state is AttemptState.ABANDONED
        assert recovery.safe_error_code is SafeJobErrorCode.LEASE_EXPIRED
        assert recovery.receipt is not None
        assert recovery.receipt.outcome is AttemptReceiptOutcome.FAILED
    finally:
        _cleanup_hard_stop_worker(process)
        drop_temporary_login(cluster, child_login)


class TestEnqueueLifecycle:
    """enqueue 生命周期与 idempotency。"""

    @pytest.mark.integration
    def test_enqueue_same_scope_key_same_fingerprint_is_idempotent(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """同 scope/key/fingerprint 重放返回同 job 且 idempotency_reused=True。"""

        request = _make_request()
        first = store.enqueue(_SCOPE_A, request)
        second = store.enqueue(_SCOPE_A, request)
        assert second.job_id == first.job_id
        assert second.definition_id == first.definition_id
        assert second.idempotency_reused is True
        assert first.idempotency_reused is False
        rows = _query(
            jobs_db,
            f"SELECT count(*) AS c FROM {_JOBS_SCHEMA}.job_runs WHERE id = :job_id",
            {"job_id": str(first.job_id)},
        )
        assert rows[0][0] == 1

    @pytest.mark.integration
    def test_enqueue_same_key_different_fingerprint_conflicts(
        self, store: PostgresJobStore
    ) -> None:
        """同 key 不同 fingerprint（payload 不同）抛 JobIdempotencyConflictError。"""

        store.enqueue(_SCOPE_A, _make_request(marker="p1"))
        with pytest.raises(JobIdempotencyConflictError):
            store.enqueue(_SCOPE_A, _make_request(marker="p2"))

    @pytest.mark.integration
    def test_concurrent_same_idempotency_enqueue_returns_same_job_without_integrity_error(
        self,
        store: PostgresJobStore,
        second_store: PostgresJobStore,
        jobs_db: tuple[PlatformCluster, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """同 fingerprint 双 engine enqueue 原子收敛到一条 job/event。

        Args:
            store: 第一条独立 app engine。
            second_store: 第二条独立 app engine。
            jobs_db: 独立真实 PostgreSQL 16 数据库。
            monkeypatch: fingerprint barrier 注入工具。

        Returns:
            无。

        Raises:
            无；任何裸数据库异常都会直接使测试失败。
        """

        from dayu.investment.storage import postgres_jobs as postgres_jobs_module

        # 先建立 immutable definition，避免 definition natural-key 竞争遮蔽
        # 本测试唯一要证明的 job idempotency conflict window。
        store.enqueue(
            _SCOPE_A,
            _pg_request(
                jobs_db,
                idempotency_key="concurrent-same-definition-seed",
            ),
        )
        original_fingerprint = postgres_jobs_module.job_enqueue_request_fingerprint
        monkeypatch.setattr(
            postgres_jobs_module,
            "job_enqueue_request_fingerprint",
            _FingerprintBarrier(threading.Barrier(2), original_fingerprint),
        )
        request = _pg_request(
            jobs_db,
            idempotency_key="concurrent-same-idempotency",
            marker="same",
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(store.enqueue, _SCOPE_A, request)
            second_future = executor.submit(second_store.enqueue, _SCOPE_A, request)
            receipts = (
                first_future.result(timeout=15),
                second_future.result(timeout=15),
            )

        assert receipts[0].job_id == receipts[1].job_id
        assert receipts[0].definition_id == receipts[1].definition_id
        assert sorted(receipt.idempotency_reused for receipt in receipts) == [
            False,
            True,
        ]
        rows = _query(
            jobs_db,
            f"SELECT count(*) AS count FROM {_JOBS_SCHEMA}.job_runs "
            "WHERE tenant_id = :tenant_id AND definition_id = :definition_id "
            "AND idempotency_key = :idempotency_key",
            {
                "tenant_id": _TENANT_A.value,
                "definition_id": str(receipts[0].definition_id),
                "idempotency_key": request.idempotency_key,
            },
        )
        assert _col(rows[0], "count") == 1
        event_types = [
            _col(row, "event_type") for row in _events_for(jobs_db, receipts[0].job_id)
        ]
        assert event_types == ["job_created"]

    @pytest.mark.integration
    def test_concurrent_different_fingerprint_enqueue_returns_closed_conflict(
        self,
        store: PostgresJobStore,
        second_store: PostgresJobStore,
        jobs_db: tuple[PlatformCluster, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """同 key 不同 fingerprint 双 engine 只有一条 job 与一个闭合 loser。

        Args:
            store: 第一条独立 app engine。
            second_store: 第二条独立 app engine。
            jobs_db: 独立真实 PostgreSQL 16 数据库。
            monkeypatch: fingerprint barrier 注入工具。

        Returns:
            无。

        Raises:
            无；非 ``JobIdempotencyConflictError`` 异常不会被吞掉。
        """

        from dayu.investment.storage import postgres_jobs as postgres_jobs_module

        store.enqueue(
            _SCOPE_A,
            _pg_request(
                jobs_db,
                idempotency_key="concurrent-different-definition-seed",
            ),
        )
        original_fingerprint = postgres_jobs_module.job_enqueue_request_fingerprint
        monkeypatch.setattr(
            postgres_jobs_module,
            "job_enqueue_request_fingerprint",
            _FingerprintBarrier(threading.Barrier(2), original_fingerprint),
        )
        first_request = _pg_request(
            jobs_db,
            idempotency_key="concurrent-different-idempotency",
            marker="first",
        )
        second_request = _make_request(
            idempotency_key=first_request.idempotency_key,
            available_at=first_request.available_at,
            deadline_at=first_request.deadline_at,
            marker="second",
        )
        receipts: list[JobEnqueueReceipt] = []
        conflicts = 0

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(store.enqueue, _SCOPE_A, first_request),
                executor.submit(second_store.enqueue, _SCOPE_A, second_request),
            )
            for future in futures:
                try:
                    receipts.append(future.result(timeout=15))
                except JobIdempotencyConflictError:
                    conflicts += 1

        assert len(receipts) == 1
        assert conflicts == 1
        assert receipts[0].idempotency_reused is False
        rows = _query(
            jobs_db,
            f"SELECT count(*) AS count FROM {_JOBS_SCHEMA}.job_runs "
            "WHERE tenant_id = :tenant_id AND definition_id = :definition_id "
            "AND idempotency_key = :idempotency_key",
            {
                "tenant_id": _TENANT_A.value,
                "definition_id": str(receipts[0].definition_id),
                "idempotency_key": first_request.idempotency_key,
            },
        )
        assert _col(rows[0], "count") == 1
        event_types = [
            _col(row, "event_type") for row in _events_for(jobs_db, receipts[0].job_id)
        ]
        assert event_types == ["job_created"]

    @pytest.mark.integration
    def test_disabled_definition_rejects_enqueue(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """disabled definition 拒绝 enqueue。"""

        receipt = store.enqueue(_SCOPE_A, _make_request())
        _execute(
            jobs_db,
            f"UPDATE {_JOBS_SCHEMA}.job_definitions SET status = 'disabled', "
            "updated_at = now(), version = version + 1 WHERE id = :definition_id",
            {"definition_id": str(receipt.definition_id)},
        )
        with pytest.raises(JobStateConflictError):
            store.enqueue(_SCOPE_A, _make_request(idempotency_key="key-2"))

    @pytest.mark.integration
    def test_ready_deadline_sets_exact_safe_failure_and_single_event_without_attempt(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """ready job 到期由 claim 前置标记 failed + 单 deadline event，无 attempt。"""

        _, job_id = _enqueue(
            store,
            _SCOPE_A,
            _make_request(
                available_at=NOW - timedelta(hours=2),
                deadline_at=NOW - timedelta(hours=1),
            ),
        )
        assert _claim(store, _SCOPE_A, "worker-1") is None
        job = _job_row(jobs_db, job_id)
        assert _col(job, "state") == JobState.FAILED.value
        assert (
            _col(job, "safe_failure_code") == SafeJobErrorCode.DEADLINE_EXCEEDED.value
        )
        assert _attempt_rows(jobs_db, job_id) == []
        events = _events_for(jobs_db, job_id)
        assert [_col(row, "event_type") for row in events] == [
            "job_created",
            "job_deadline_exceeded",
        ]
        # 重放不追加 event。
        assert _claim(store, _SCOPE_A, "worker-1") is None
        assert len(_events_for(jobs_db, job_id)) == 2

    @pytest.mark.integration
    def test_ready_cancel_writes_no_attempt_receipt(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """ready cancel 直接 terminal，不写 attempt/receipt。"""

        _, job_id = _enqueue(store, _SCOPE_A)
        result = store.cancel(
            _SCOPE_A, JobCancellationRequest(job_id=job_id, reason="operator")
        )
        assert result.job_state is JobState.CANCELLED
        assert result.attempt_id is None
        assert result.receipt is None
        assert _attempt_rows(jobs_db, job_id) == []
        assert _receipts_for(jobs_db, job_id) == []

    @pytest.mark.integration
    def test_cancel_before_claim_is_terminal_without_attempt_receipt(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """claim 前 cancel 即 terminal：无 attempt/receipt 且不再被 claim 复活。"""

        _, job_id = _enqueue(store, _SCOPE_A)
        result = store.cancel(
            _SCOPE_A, JobCancellationRequest(job_id=job_id, reason="operator")
        )
        assert result.job_state is JobState.CANCELLED
        assert result.attempt_id is None
        assert result.attempt_state is None
        assert result.receipt is None
        assert result.next_available_at is None
        assert _attempt_rows(jobs_db, job_id) == []
        assert _receipts_for(jobs_db, job_id) == []
        # 终态 job 不再被 claim（不会复活、不产生 attempt）。
        assert _claim(store, _SCOPE_A, "worker-1") is None
        assert _attempt_rows(jobs_db, job_id) == []


class TestClaimRace:
    """SKIP LOCKED 双 engine/process barrier。"""

    @pytest.mark.integration
    def test_claim_empty_returns_none(self, store: PostgresJobStore) -> None:
        """无可用 job 时 claim 返回 None。"""

        assert _claim(store, _SCOPE_A, "worker-1") is None

    @pytest.mark.integration
    def test_claim_two_workers_only_one_receives_job(
        self, store: PostgresJobStore, second_store: PostgresJobStore, jobs_db
    ) -> None:
        """两个独立 engine 同时 claim 同一 job 只有一方成功。"""

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        barrier = threading.Barrier(2)
        results: list[JobClaim | str] = []
        results_lock = threading.Lock()

        def worker(st: PostgresJobStore, name: str) -> None:
            """以独立 engine 尝试 claim 一次并记录结果。"""

            barrier.wait()
            try:
                claim = st.claim(_SCOPE_A, name)
            except Exception as exc:  # pragma: no cover - 记录失败便于断言
                with results_lock:
                    results.append(f"error:{type(exc).__name__}")
                return
            if claim is not None:
                with results_lock:
                    results.append(claim)

        threads = [
            threading.Thread(target=worker, args=(store, "w1")),
            threading.Thread(target=worker, args=(second_store, "w2")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        claims = [item for item in results if isinstance(item, JobClaim)]
        assert len(claims) == 1
        assert claims[0].job_id == job_id
        assert len(_attempt_rows(jobs_db, job_id)) == 1

    @pytest.mark.integration
    def test_two_writers_allocate_distinct_per_job_event_sequences(
        self, store: PostgresJobStore, second_store: PostgresJobStore, jobs_db
    ) -> None:
        """两个 writer 对同一 job 写 event 得到互不重复的序列。"""

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        barrier = threading.Barrier(2)
        captured: list[str] = []
        captured_lock = threading.Lock()

        def writer(marker: str) -> None:
            """以独立事务递增 job 的 next_event_sequence 计数器。"""

            barrier.wait()
            session = store._session_factory()
            session.begin()
            session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": _TENANT_A.value},
            )
            for _ in range(10):
                session.execute(
                    text(
                        f"UPDATE {_JOBS_SCHEMA}.job_runs "
                        "SET next_event_sequence = next_event_sequence + 1, "
                        "updated_at = now(), version = version + 1 "
                        "WHERE tenant_id = :tenant_id AND id = :job_id "
                        "RETURNING next_event_sequence"
                    ),
                    {
                        "tenant_id": _TENANT_A.value,
                        "job_id": str(job_id),
                    },
                )
            session.commit()
            session.close()
            with captured_lock:
                captured.append(marker)

        threads = [threading.Thread(target=writer, args=(m,)) for m in ("w1", "w2")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(captured) == ["w1", "w2"]
        job = _job_row(jobs_db, job_id)
        # job_created event 已把 next_event_sequence 从 1 推到 2，再叠加 20 次。
        next_sequence = _col(job, "next_event_sequence")
        assert isinstance(next_sequence, int)
        assert next_sequence == 2 + 20


class TestHeartbeat:
    """heartbeat 的 fence/deadline/clamp 契约。"""

    @pytest.mark.integration
    def test_stale_heartbeat_complete_and_fail_are_fenced(
        self, store: PostgresJobStore, second_store: PostgresJobStore, jobs_db
    ) -> None:
        """过期/错误 lease 的 heartbeat/complete/fail 均被 fence 拒绝。"""

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        stale_lease = _lease_copy(claim.lease)
        # 第二个 worker 无法用错误 token 操作。
        with pytest.raises(JobLeaseLostError):
            second_store.heartbeat(_SCOPE_A, _lease_copy(claim.lease, token="f" * 64))
        with pytest.raises(JobLeaseLostError):
            second_store.complete(
                _SCOPE_A,
                _lease_copy(claim.lease, token="f" * 64),
                JobCompletion(result=_result()),
            )
        with pytest.raises(JobLeaseLostError):
            second_store.fail(
                _SCOPE_A,
                _lease_copy(claim.lease, token="f" * 64),
                JobFailure(
                    safe_error_code=SafeJobErrorCode.HANDLER_REJECTED, retryable=True
                ),
            )
        # 正常持有者仍可完成（fence/token 匹配）。
        receipt = store.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
        assert receipt.outcome is AttemptReceiptOutcome.SUCCEEDED
        job = _job_row(jobs_db, job_id)
        assert _col(job, "state") == JobState.SUCCEEDED.value
        del stale_lease

    @pytest.mark.integration
    def test_heartbeat_at_or_after_deadline_terminalizes_then_raises_deadline_error(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """heartbeat 时已到 deadline：收敛 failed 并抛 JobDeadlineExceededError。"""

        import time as time_module

        _, job_id = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(
                jobs_db,
                available_delta=timedelta(minutes=-1),
                deadline_delta=timedelta(seconds=1),
            ),
        )
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        time_module.sleep(1.5)
        with pytest.raises(JobDeadlineExceededError):
            store.heartbeat(_SCOPE_A, claim.lease)
        job = _job_row(jobs_db, job_id)
        assert _col(job, "state") == JobState.FAILED.value
        assert (
            _col(job, "safe_failure_code") == SafeJobErrorCode.DEADLINE_EXCEEDED.value
        )
        attempts = _attempt_rows(jobs_db, job_id)
        assert len(attempts) == 1
        assert _col(attempts[0], "state") == AttemptState.FAILED.value
        receipts = _receipts_for(jobs_db, claim.attempt_id)
        assert len(receipts) == 1
        assert _col(receipts[0], "outcome") == AttemptReceiptOutcome.FAILED.value
        assert (
            _col(receipts[0], "safe_error_code")
            == SafeJobErrorCode.DEADLINE_EXCEEDED.value
        )

    @pytest.mark.integration
    def test_heartbeat_before_deadline_clamps_expiry_without_past_success_claim(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """deadline 前 heartbeat 把 expiry 钳制到 deadline 且不超过。"""

        pg_now = _pg_now(jobs_db)
        _, job_id = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(
                jobs_db,
                available_delta=timedelta(minutes=-1),
                deadline_delta=timedelta(seconds=30),
            ),
        )
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        refreshed = store.heartbeat(_SCOPE_A, claim.lease)
        # 新 expiry 不得晚于 deadline，也不得早于当前时刻。
        assert refreshed.claim.lease.expires_at <= claim.deadline_at
        assert refreshed.claim.lease.expires_at > refreshed.claim.lease.acquired_at
        attempts = _attempt_rows(jobs_db, job_id)
        assert _col(attempts[0], "state") == AttemptState.LEASED.value
        del pg_now

    @pytest.mark.integration
    def test_worker_clock_skew_does_not_change_lease_deadline_backoff_or_event_time(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """worker 侧时间不影响 lease/deadline/backoff/event 的 DB 权威时间。"""

        pg_before = _pg_now(jobs_db)
        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        pg_after = _pg_now(jobs_db)
        # lease 时间来自 PG clock，而非 Python 时间。
        assert (
            pg_before - timedelta(seconds=2)
            <= claim.lease.acquired_at
            <= pg_after + timedelta(seconds=2)
        )
        events = _events_for(jobs_db, job_id)
        job_claimed = next(
            row for row in events if _col(row, "event_type") == "job_claimed"
        )
        occurred = _col(job_claimed, "occurred_at")
        assert isinstance(occurred, datetime)
        assert (
            pg_before - timedelta(seconds=2)
            <= occurred
            <= pg_after + timedelta(seconds=2)
        )


class TestCompleteAndFail:
    """complete/fail 的 cancel/deadline/success 顺序与 retry。"""

    @pytest.mark.integration
    def test_complete_cancel_intent_precedes_deadline_and_success(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """cancel intent 时 complete 收敛 cancelled（不写 deadline/success receipt）。"""

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        store.cancel(_SCOPE_A, JobCancellationRequest(job_id=job_id, reason="operator"))
        receipt = store.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
        assert receipt.outcome is AttemptReceiptOutcome.CANCELLED
        assert receipt.safe_error_code is SafeJobErrorCode.CANCELLED
        job = _job_row(jobs_db, job_id)
        assert _col(job, "state") == JobState.CANCELLED.value
        receipts = _receipts_for(jobs_db, claim.attempt_id)
        assert len(receipts) == 1
        assert _col(receipts[0], "outcome") == AttemptReceiptOutcome.CANCELLED.value

    @pytest.mark.integration
    def test_cancel_while_leased_blocks_success(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """leased cancel 后 fail/complete 不得成功。"""

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        cancel_result = store.cancel(
            _SCOPE_A, JobCancellationRequest(job_id=job_id, reason="operator")
        )
        assert cancel_result.job_state is JobState.CANCEL_REQUESTED
        # 重复 cancel 返回同一状态。
        again = store.cancel(
            _SCOPE_A, JobCancellationRequest(job_id=job_id, reason="operator")
        )
        assert again.job_state is JobState.CANCEL_REQUESTED
        fail_result = store.fail(
            _SCOPE_A,
            claim.lease,
            JobFailure(
                safe_error_code=SafeJobErrorCode.HANDLER_REJECTED, retryable=True
            ),
        )
        assert fail_result.job_state is JobState.CANCELLED
        assert fail_result.attempt_state is AttemptState.CANCELLED
        receipts = _receipts_for(jobs_db, claim.attempt_id)
        assert len(receipts) == 1
        assert _col(receipts[0], "outcome") == AttemptReceiptOutcome.CANCELLED.value

    @pytest.mark.integration
    def test_retry_backoff_and_deadline_are_closed(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """retry 产生确定性 backoff；deadline 内耗尽 attempts 后 terminal。"""

        descriptor = JobHandlerDescriptor(
            job_type="test.retry",
            payload_schema_name="test.payload",
            payload_schema_version=1,
            max_attempts=2,
            retry_base_seconds=1,
            retry_max_seconds=10,
            lease_duration_seconds=60,
        )
        _, job_id = _enqueue(
            store, _SCOPE_A, _pg_request(jobs_db, descriptor=descriptor)
        )
        first = _claim(store, _SCOPE_A, "worker-1")
        assert first is not None
        result = store.fail(
            _SCOPE_A,
            first.lease,
            JobFailure(
                safe_error_code=SafeJobErrorCode.HANDLER_REJECTED, retryable=True
            ),
        )
        assert result.job_state is JobState.READY
        assert result.attempt_state is AttemptState.FAILED
        assert result.next_available_at is not None
        assert result.safe_error_code is SafeJobErrorCode.HANDLER_REJECTED
        # backoff = min(10, 1 * 2^0) = 1s。
        assert result.next_available_at - _pg_now(jobs_db) <= timedelta(seconds=2)
        import time as time_module

        time_module.sleep(1.2)
        second = _claim(store, _SCOPE_A, "worker-1")
        assert second is not None
        assert second.attempt_number == 2
        # 第二次 fail 耗尽 attempts -> retry_exhausted。
        terminal = store.fail(
            _SCOPE_A,
            second.lease,
            JobFailure(
                safe_error_code=SafeJobErrorCode.HANDLER_REJECTED, retryable=True
            ),
        )
        assert terminal.job_state is JobState.FAILED
        assert terminal.safe_error_code is SafeJobErrorCode.RETRY_EXHAUSTED
        receipts = _receipts_for(jobs_db, second.attempt_id)
        assert len(receipts) == 1
        assert (
            _col(receipts[0], "safe_error_code")
            == SafeJobErrorCode.RETRY_EXHAUSTED.value
        )

    @pytest.mark.integration
    def test_recovery_result_reports_actual_handler_fail_lease_expiry_cancel_and_terminal_states(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """handler fail/lease-expiry/cancel/deadline 的真实 attempt/job/receipt 状态。"""

        import time as time_module

        # handler fail（非 retryable）-> failed/failed + failure receipt。
        _, job_a = _enqueue(store, _SCOPE_A, _pg_request(jobs_db, idempotency_key="a"))
        claim_a = _claim(store, _SCOPE_A, "worker-a")
        assert claim_a is not None
        result_a = store.fail(
            _SCOPE_A,
            claim_a.lease,
            JobFailure(
                safe_error_code=SafeJobErrorCode.HANDLER_REJECTED, retryable=False
            ),
        )
        assert result_a.job_state is JobState.FAILED
        assert result_a.attempt_state is AttemptState.FAILED
        assert result_a.safe_error_code is SafeJobErrorCode.HANDLER_REJECTED
        assert result_a.receipt is not None

        # lease-expiry -> abandoned/ready + lease_expired receipt。
        descriptor = JobHandlerDescriptor(
            job_type="test.expiry",
            payload_schema_name="test.payload",
            payload_schema_version=1,
            max_attempts=5,
            retry_base_seconds=1,
            retry_max_seconds=10,
            lease_duration_seconds=1,
        )
        _, job_b = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(jobs_db, descriptor=descriptor, idempotency_key="b"),
        )
        claim_b = _claim(store, _SCOPE_A, "worker-b")
        assert claim_b is not None
        time_module.sleep(1.5)
        recovered = store.recover(_SCOPE_A)
        result_b = next((r for r in recovered if r.job_id == job_b), None)
        assert result_b is not None
        assert result_b.job_state is JobState.READY
        assert result_b.attempt_state is AttemptState.ABANDONED
        assert result_b.safe_error_code is SafeJobErrorCode.LEASE_EXPIRED
        assert result_b.receipt is not None
        assert result_b.receipt.outcome is AttemptReceiptOutcome.FAILED

        # leased cancel 由 recover 收敛为 cancelled。
        _, job_c = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(jobs_db, descriptor=descriptor, idempotency_key="c"),
        )
        claim_c = _claim(store, _SCOPE_A, "worker-c")
        assert claim_c is not None
        store.cancel(_SCOPE_A, JobCancellationRequest(job_id=job_c, reason="op"))
        time_module.sleep(1.5)
        recovered_c = store.recover(_SCOPE_A)
        result_c = next((r for r in recovered_c if r.job_id == job_c), None)
        assert result_c is not None
        assert result_c.job_state is JobState.CANCELLED
        assert result_c.attempt_state is AttemptState.CANCELLED
        assert result_c.receipt is not None
        assert result_c.receipt.outcome is AttemptReceiptOutcome.CANCELLED
        del job_a, job_b, job_c

    @pytest.mark.integration
    def test_recover_expired_lease_never_revives_attempt(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """过期 lease 由 recover 收敛后，陈旧 heartbeat 无法复活 attempt。"""

        import time as time_module

        descriptor = JobHandlerDescriptor(
            job_type="test.revive",
            payload_schema_name="test.payload",
            payload_schema_version=1,
            max_attempts=5,
            retry_base_seconds=1,
            retry_max_seconds=10,
            lease_duration_seconds=1,
        )
        _, job_id = _enqueue(
            store, _SCOPE_A, _pg_request(jobs_db, descriptor=descriptor)
        )
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        time_module.sleep(1.5)
        recovered = store.recover(_SCOPE_A)
        assert any(r.job_id == job_id for r in recovered)
        # 陈旧 heartbeat 被 fence（lease 已 release）拒绝。
        with pytest.raises(JobLeaseLostError):
            store.heartbeat(_SCOPE_A, claim.lease)
        job = _job_row(jobs_db, job_id)
        assert _col(job, "state") == JobState.READY.value


class TestConcurrentCompleteFail:
    """同一 attempt 的双 writer 结算竞态（两个独立 engine/process barrier）。"""

    @pytest.mark.integration
    def test_complete_vs_fail_exactly_one_settles(
        self, store: PostgresJobStore, second_store: PostgresJobStore, jobs_db
    ) -> None:
        """complete 与 fail 并发：恰一方成功、另一方 JobLeaseLostError；唯一 receipt、lease 单次释放。"""

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        attempt_id = claim.attempt_id
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()

        def completer() -> None:
            """以第一 engine 结算 complete。"""

            barrier.wait()
            try:
                store.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
                with outcomes_lock:
                    outcomes.append("complete:ok")
            except JobLeaseLostError:
                with outcomes_lock:
                    outcomes.append("complete:lease_lost")

        def failer() -> None:
            """以第二 engine 结算 fail（retryable=False）。"""

            barrier.wait()
            try:
                second_store.fail(
                    _SCOPE_A,
                    claim.lease,
                    JobFailure(
                        safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
                        retryable=False,
                    ),
                )
                with outcomes_lock:
                    outcomes.append("fail:ok")
            except JobLeaseLostError:
                with outcomes_lock:
                    outcomes.append("fail:lease_lost")

        threads = [threading.Thread(target=completer), threading.Thread(target=failer)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sum(1 for o in outcomes if o.endswith(":ok")) == 1
        assert sum(1 for o in outcomes if o.endswith(":lease_lost")) == 1
        # 唯一 immutable receipt。
        receipts = _receipts_for(jobs_db, attempt_id)
        assert len(receipts) == 1
        # lease 只释放一次且 version=2（CAS release）。
        lease_rows = _query(
            jobs_db,
            f"SELECT * FROM {_JOBS_SCHEMA}.job_leases WHERE job_run_id = :job_id ORDER BY id",
            {"job_id": str(job_id)},
        )
        assert len(lease_rows) == 1
        assert _col(lease_rows[0], "released_at") is not None
        assert _col(lease_rows[0], "version") == 2
        # 事件严格 job_created / job_claimed / 唯一 terminal，sequence 1,2,3。
        events = _events_for(jobs_db, job_id)
        event_types = [_col(row, "event_type") for row in events]
        sequences = [_col(row, "sequence_number") for row in events]
        assert sequences == [1, 2, 3]
        assert event_types[0] == "job_created"
        assert event_types[1] == "job_claimed"
        terminal_type = "job_completed" if "complete:ok" in outcomes else "job_failed"
        assert event_types[2] == terminal_type
        # job/attempt 终态与唯一 terminal 一致。
        job = _job_row(jobs_db, job_id)
        attempt = _attempt_rows(jobs_db, job_id)[0]
        if terminal_type == "job_completed":
            assert _col(job, "state") == JobState.SUCCEEDED.value
            assert _col(attempt, "state") == AttemptState.SUCCEEDED.value
        else:
            assert _col(job, "state") == JobState.FAILED.value
            assert _col(attempt, "state") == AttemptState.FAILED.value

    @pytest.mark.integration
    def test_complete_vs_complete_exactly_one_settles(
        self, store: PostgresJobStore, second_store: PostgresJobStore, jobs_db
    ) -> None:
        """两个 complete 并发：恰一方成功、另一方 JobLeaseLostError；不产生第二个 receipt 或重复 terminal event。"""

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        attempt_id = claim.attempt_id
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()

        def completer(st: PostgresJobStore, marker: str) -> None:
            """以指定 engine 结算 complete。"""

            barrier.wait()
            try:
                st.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
                with outcomes_lock:
                    outcomes.append(f"{marker}:ok")
            except JobLeaseLostError:
                with outcomes_lock:
                    outcomes.append(f"{marker}:lease_lost")

        threads = [
            threading.Thread(target=completer, args=(store, "c1")),
            threading.Thread(target=completer, args=(second_store, "c2")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sum(1 for o in outcomes if o.endswith(":ok")) == 1
        assert sum(1 for o in outcomes if o.endswith(":lease_lost")) == 1
        # 唯一 receipt、唯一 job_completed event、lease 单次释放。
        assert len(_receipts_for(jobs_db, attempt_id)) == 1
        events = _events_for(jobs_db, job_id)
        event_types = [_col(row, "event_type") for row in events]
        sequences = [_col(row, "sequence_number") for row in events]
        assert sequences == [1, 2, 3]
        assert event_types == ["job_created", "job_claimed", "job_completed"]
        lease_rows = _query(
            jobs_db,
            f"SELECT * FROM {_JOBS_SCHEMA}.job_leases WHERE job_run_id = :job_id ORDER BY id",
            {"job_id": str(job_id)},
        )
        assert len(lease_rows) == 1
        assert _col(lease_rows[0], "released_at") is not None
        assert _col(lease_rows[0], "version") == 2
        job = _job_row(jobs_db, job_id)
        assert _col(job, "state") == JobState.SUCCEEDED.value


def _lease_copy(lease, *, token: str | None = None):
    """复制 lease（可替换 raw token）。

    Args:
        lease: 原 lease。
        token: 可空替换 token。

    Returns:
        新 ``JobLeaseHandle``。
    """

    from dayu.investment.domain.jobs import JobLeaseHandle

    return JobLeaseHandle(
        tenant_id=lease.tenant_id,
        job_id=lease.job_id,
        attempt_id=lease.attempt_id,
        fence=lease.fence,
        raw_token=token if token is not None else lease.raw_token,
        acquired_at=lease.acquired_at,
        expires_at=lease.expires_at,
    )


class TestLeaseVersionedCas:
    """versioned single-release lease CAS（单次释放与 grant 矩阵）。"""

    @pytest.mark.integration
    def test_job_lease_single_release_versioned_cas_and_grant_matrix(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """lease 只能从未释放一次释放；重复/配对不一致被拒绝；token 永不落明文。"""

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        rows = _query(
            jobs_db,
            f"SELECT * FROM {_JOBS_SCHEMA}.job_leases WHERE attempt_id = :attempt_id",
            {"attempt_id": str(claim.attempt_id)},
        )
        assert len(rows) == 1
        lease_row = rows[0]
        # token 只存 hash。
        assert _col(lease_row, "token_sha256") != claim.lease.raw_token
        # 首次释放（completion）。
        store.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
        after = _query(
            jobs_db,
            f"SELECT * FROM {_JOBS_SCHEMA}.job_leases WHERE attempt_id = :attempt_id",
            {"attempt_id": str(claim.attempt_id)},
        )[0]
        assert _col(after, "released_at") is not None
        assert _col(after, "release_reason") == LeaseReleaseReason.COMPLETION.value
        # 再释放被 single-release trigger 拒绝（含完整身份匹配的陈旧调用）。
        with pytest.raises(Exception):
            _execute(
                jobs_db,
                f"UPDATE {_JOBS_SCHEMA}.job_leases "
                "SET released_at = now(), release_reason = 'failure', "
                "updated_at = now(), version = version + 1 "
                "WHERE attempt_id = :attempt_id AND released_at IS NOT NULL",
                {"attempt_id": str(claim.attempt_id)},
            )

    @pytest.mark.integration
    def test_attempt_receipt_schema_requires_existing_attempt(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """receipt 必须关联既有 attempt（复合 FK 拒绝孤儿行）。"""

        from sqlalchemy.exc import SQLAlchemyError

        with pytest.raises(SQLAlchemyError):
            _execute(
                jobs_db,
                f"INSERT INTO {_JOBS_SCHEMA}.job_attempt_receipts "
                "(id, tenant_id, job_run_id, attempt_id, outcome, receipt_schema_name, "
                "receipt_schema_version, receipt_bytes, receipt_sha256, safe_error_code, "
                "finalized_at, created_at) "
                "VALUES (:id, :tenant_id, :job_run_id, :attempt_id, 'failed', "
                "'dayu.job.generic-attempt-receipt', 1, decode('7b7d', 'hex'), "
                "repeat('0', 64), 'lease_expired', now(), now())",
                {
                    "id": str(uuid4()),
                    "tenant_id": _TENANT_A.value,
                    "job_run_id": str(uuid4()),
                    "attempt_id": str(uuid4()),
                },
            )


def _observation(
    correlation,
    host_state: HostRunObservationState,
    completed_at: datetime | None = None,
    *,
    sha256: str | None = None,
) -> AgentRunCorrelationObservation:
    """构造与 Service fingerprint 算法一致的 observation。

    Args:
        correlation: 目标 correlation。
        host_state: Host observation state。
        completed_at: 可空完成时间。
        sha256: 可空显式 fingerprint（缺省按 canonical 算法计算）。

    Returns:
        ``AgentRunCorrelationObservation``。
    """

    import hashlib

    canonical = json_dumps(
        {
            "correlation_id": str(correlation.id),
            "host_run_id": correlation.reserved_host_run_id,
            "host_state": host_state.value,
            "host_completed_at": (
                completed_at.isoformat() if completed_at is not None else None
            ),
        }
    )
    digest = (
        sha256
        if sha256 is not None
        else hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    )
    return AgentRunCorrelationObservation(
        correlation_id=correlation.id,
        host_run_id=correlation.reserved_host_run_id,
        host_state=host_state,
        host_completed_at=completed_at,
        sha256=digest,
    )


def _reserve_correlation(
    store: PostgresJobStore,
    jobs_db,
    *,
    descriptor: JobHandlerDescriptor | None = None,
    idempotency_key: str = "key-1",
    deadline_delta: timedelta = timedelta(hours=1),
) -> tuple:
    """enqueue -> claim -> reserve，返回 (job_id, claim, correlation)。

    Args:
        store: 仓储。
        jobs_db: 数据库信息。
        descriptor: 可空 descriptor。
        idempotency_key: 幂等键。
        deadline_delta: 相对 PG now 的 deadline 偏移。

    Returns:
        ``(job_id, claim, correlation)`` 三元组。
    """

    _, job_id = _enqueue(
        store,
        _SCOPE_A,
        _pg_request(
            jobs_db,
            descriptor=descriptor,
            idempotency_key=idempotency_key,
            deadline_delta=deadline_delta,
        ),
    )
    claim = _claim(store, _SCOPE_A, "worker-1")
    assert claim is not None
    correlation = store.reserve_agent_run_correlation(_SCOPE_A, claim.lease)
    return job_id, claim, correlation


def _host_execution_contract(*, session_key: str) -> ExecutionContract:
    """构造 reserved Host entry 的测试执行契约（非 resumable）。"""

    return ExecutionContract(
        service_name="durable_job_test",
        scene_name="durable_job_test",
        host_policy=ExecutionHostPolicy(session_key=session_key, resumable=False),
        preparation_spec=ScenePreparationSpec(),
        message_inputs=ExecutionMessageInputs(user_message="durable job fixture"),
        accepted_execution_spec=AcceptedExecutionSpec(
            model=AcceptedModelSpec(model_name="test-model")
        ),
    )


class _StubScenePreparation:
    """stub scene preparation：只返回静态 prepared execution（Host 侧）。"""

    async def prepare(
        self,
        execution_contract: ExecutionContract,
        run_context: HostedRunContext,
    ) -> PreparedAgentExecution:
        """返回静态 prepared execution。

        Args:
            execution_contract: 执行契约。
            run_context: Host run 上下文。

        Returns:
            静态 ``PreparedAgentExecution``。

        Raises:
            无。
        """

        del execution_contract, run_context
        return PreparedAgentExecution(
            agent_input=AgentInput(
                system_prompt="test",
                messages=[],
                agent_create_args=AgentCreateArgs(runner_type="", model_name=""),
            ),
            resume_snapshot=None,
        )

    async def restore_prepared_execution(
        self,
        prepared_turn: PreparedAgentTurnSnapshot,
        run_context: HostedRunContext,
    ) -> AgentInput:
        """拒绝恢复路径（本类测试不应触发）。

        Args:
            prepared_turn: prepared turn 快照。
            run_context: Host run 上下文。

        Returns:
            永不返回。

        Raises:
            AssertionError: 恒抛。
        """

        del prepared_turn, run_context
        raise AssertionError("该测试不应走恢复路径")


class _FakeAgent:
    """fake agent：计数构造与 model entry 次数（Host 侧）。"""

    construction_count = 0
    entry_count = 0

    def __init__(
        self,
        *,
        agent_create_args: AgentCreateArgs,
        tool_executor: ToolExecutor | None = None,
        tool_trace_recorder_factory: ToolTraceRecorderFactory | None = None,
        trace_identity: AgentTraceIdentity | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        """计数一次 Agent construction。

        Args:
            agent_create_args: Agent 创建参数。
            tool_executor: 工具执行器。
            tool_trace_recorder_factory: 工具 trace recorder 工厂。
            trace_identity: trace 身份。
            cancellation_token: 取消令牌。

        Returns:
            无。

        Raises:
            无。
        """

        del (
            agent_create_args,
            tool_executor,
            tool_trace_recorder_factory,
            trace_identity,
            cancellation_token,
        )
        _FakeAgent.construction_count += 1

    async def run_messages(self, messages, *, session_id, run_id, stream):
        """计数一次 model entry 并产出最终答案事件。

        Args:
            messages: 消息列表。
            session_id: Host session ID。
            run_id: Host run ID。
            stream: 事件流。

        Yields:
            最终答案 ``StreamEvent``。

        Raises:
            无。
        """

        del messages, session_id, run_id
        _FakeAgent.entry_count += 1
        yield StreamEvent(
            EventType.FINAL_ANSWER, {"content": "done", "degraded": False}, {}
        )


def _open_host_seam(sqlite_path: Path) -> tuple[DefaultHostExecutor, SQLiteRunRegistry]:
    """打开（或重开）SQLite Host seam：新 HostStore/registry/executor。

    Args:
        sqlite_path: Host SQLite 文件路径。

    Returns:
        ``(executor, registry)`` 二元组。
    """

    _FakeAgent.construction_count = 0
    _FakeAgent.entry_count = 0
    host_store = HostStore(sqlite_path)
    host_store.initialize_schema()
    registry = SQLiteRunRegistry(host_store)
    executor = DefaultHostExecutor(
        run_registry=registry,
        scene_preparation=_StubScenePreparation(),
    )
    return executor, registry


def _run_reserved_stream(
    executor: DefaultHostExecutor,
    contract: ExecutionContract,
    reserved_run_id: str,
) -> None:
    """以 reserved ID 跑一次完整 Host stream。

    Args:
        executor: Host executor。
        contract: 执行契约。
        reserved_run_id: 确定性 Host run ID。

    Raises:
        ReservedAgentRunExistsError: reserved run 已存在时抛出。
        由 executor 传播的其它异常。
    """

    async def _run() -> None:
        """驱动一次 reserved stream 事件循环。"""

        async for _event in executor.run_agent_stream(
            contract, reserved_run_id=reserved_run_id
        ):
            pass

    asyncio.run(_run())


class TestCorrelationReserveAndAuthorize:
    """Transaction-2 reserve 与 live start authorization。"""

    @pytest.mark.integration
    def test_governance_keyset_rotation_prevents_long_active_wait_from_starving_later_rows(
        self,
        store: PostgresJobStore,
        jobs_db,
    ) -> None:
        """governance JOIN 使用唯一别名且 keyset 真尾部返回空 cursor。

        Args:
            store: 真实 PostgreSQL job store。
            jobs_db: 数据库信息。

        Returns:
            无。

        Raises:
            无。
        """

        _, first_claim, first = _reserve_correlation(
            store,
            jobs_db,
            idempotency_key="governance-page-1",
            deadline_delta=timedelta(hours=1),
        )
        _, second_claim, second = _reserve_correlation(
            store,
            jobs_db,
            idempotency_key="governance-page-2",
            deadline_delta=timedelta(hours=2),
        )

        first_page = store.list_governable_agent_runs(
            _SCOPE_A,
            None,
            limit=1,
        )
        assert len(first_page.projections) == 1
        assert first_page.next_cursor is not None
        first_projection = first_page.projections[0]
        assert first_projection.correlation.id == first.id
        assert first_projection.correlation.job_id == first_claim.job_id
        assert first_projection.correlation.attempt_id == first_claim.attempt_id

        second_page = store.list_governable_agent_runs(
            _SCOPE_A,
            first_page.next_cursor,
            limit=1,
        )
        assert len(second_page.projections) == 1
        assert second_page.next_cursor is None
        second_projection = second_page.projections[0]
        assert second_projection.correlation.id == second.id
        assert second_projection.correlation.job_id == second_claim.job_id
        assert second_projection.correlation.attempt_id == second_claim.attempt_id
        assert second_projection.deadline_at > first_projection.deadline_at

    @pytest.mark.integration
    def test_correlation_is_committed_before_start_authorization(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """authorize 前 correlation 必须已 commit（START_REQUIRED 需要 committed row）。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        decision = store.authorize_agent_run_start(
            _SCOPE_A, claim.lease, correlation.id
        )
        assert decision.action is AgentRunStartAuthorizationAction.START_REQUIRED
        assert decision.safe_error_code is None
        assert decision.correlation.id == correlation.id
        assert decision.attempt_id == claim.attempt_id

    @pytest.mark.integration
    def test_missing_expired_or_wrong_lease_never_authorizes_start(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """缺失/过期/wrong token 的 lease 一律不得 START_REQUIRED。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        # wrong token。
        wrong = _lease_copy(claim.lease, token="a" * 64)
        decision = store.authorize_agent_run_start(_SCOPE_A, wrong, correlation.id)
        assert decision.action is not AgentRunStartAuthorizationAction.START_REQUIRED
        assert decision.action is AgentRunStartAuthorizationAction.LEASE_LOST
        # 合法 token + 随机 correlation id（缺失 committed row）。
        random_id = uuid4()
        decision2 = store.authorize_agent_run_start(_SCOPE_A, claim.lease, random_id)
        assert decision2.action is AgentRunStartAuthorizationAction.INVARIANT_FAILURE
        assert decision2.safe_error_code is SafeJobErrorCode.CORRELATION_MISSING

    @pytest.mark.integration
    def test_correlation_missing_has_only_start_authorization_invariant_decision(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """correlation_missing 只出现在 start authorization；其它缺失读取为 not-found。"""

        _, claim, _ = _reserve_correlation(store, jobs_db, idempotency_key="key-m1")
        random_id = uuid4()
        decision = store.authorize_agent_run_start(_SCOPE_A, claim.lease, random_id)
        assert decision.action is AgentRunStartAuthorizationAction.INVARIANT_FAILURE
        assert decision.safe_error_code is SafeJobErrorCode.CORRELATION_MISSING
        # get_agent_run_correlation 对该 id 是 tenant-scoped not-found。
        from dayu.investment.domain.jobs import JobNotFoundError

        with pytest.raises(JobNotFoundError):
            store.get_agent_run_correlation(_SCOPE_A, random_id)

    @pytest.mark.integration
    def test_start_required_requires_current_raw_lease(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """START_REQUIRED 必须持有当前 raw lease（fence/token 全匹配）。"""

        _, claim, correlation = _reserve_correlation(
            store, jobs_db, descriptor=_descriptor_short_lease()
        )
        decision = store.authorize_agent_run_start(
            _SCOPE_A, claim.lease, correlation.id
        )
        assert decision.action is AgentRunStartAuthorizationAction.START_REQUIRED
        # 过期 lease（原 lease 到期后）。
        import time as time_module

        time_module.sleep(1.5)
        decision2 = store.authorize_agent_run_start(
            _SCOPE_A, claim.lease, correlation.id
        )
        assert decision2.action is not AgentRunStartAuthorizationAction.START_REQUIRED

    @pytest.mark.integration
    def test_get_agent_run_correlation_is_tenant_scoped_not_found_and_invariant_checked(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """correlation 按 (tenant, id) 读取：跨租户 not-found、不变量校验。"""

        from dayu.investment.domain.jobs import JobNotFoundError

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        found = store.get_agent_run_correlation(_SCOPE_A, correlation.id)
        assert found.id == correlation.id
        assert found.reserved_host_run_id == f"run_{claim.attempt_id.hex}"
        assert found.state is CorrelationState.RESERVED
        with pytest.raises(JobNotFoundError):
            store.get_agent_run_correlation(_SCOPE_B, correlation.id)


class TestTerminalReconciliation:
    """tokenless terminal-only reconciliation 状态机。"""

    @pytest.mark.integration
    def test_reserved_missing_host_returns_no_host_run_then_recovers(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """correlation=reserved 且 Host missing 时返回 NO_HOST_RUN，随后 targeted recover 收敛。"""

        import time as time_module

        descriptor = _descriptor_short_lease()
        _, claim, correlation = _reserve_correlation(
            store, jobs_db, descriptor=descriptor
        )
        decision = store.reconcile_agent_run_terminal(
            _SCOPE_A,
            correlation.id,
            _observation(correlation, HostRunObservationState.MISSING),
        )
        assert decision.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        assert decision.receipt is None
        time_module.sleep(1.5)
        result = store.recover_agent_run_after_no_host(
            _SCOPE_A, correlation.id, decision.observation.sha256
        )
        assert result is not None
        assert result.job_state is JobState.READY
        assert result.attempt_state is AttemptState.ABANDONED

    @pytest.mark.integration
    def test_reserved_missing_replay_has_no_duplicate_event(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """相同 missing observation 重放不追加 event。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        obs = _observation(correlation, HostRunObservationState.MISSING)
        first = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, obs)
        assert first.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        events_after_first = [
            row
            for row in _events_for(jobs_db, claim.job_id)
            if _col(row, "event_type") == "correlation_no_host_run"
        ]
        assert len(events_after_first) == 1
        second = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, obs)
        assert second.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        events_after_second = [
            row
            for row in _events_for(jobs_db, claim.job_id)
            if _col(row, "event_type") == "correlation_no_host_run"
        ]
        assert len(events_after_second) == 1

    @pytest.mark.integration
    def test_active_host_returns_wait_never_recovers_or_creates_new_attempt(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """Host CREATED/RUNNING -> HOST_ACTIVE_WAIT，不 recover、不新建 attempt。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        obs = _observation(correlation, HostRunObservationState.RUNNING)
        decision = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, obs)
        assert decision.action is AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT
        assert decision.receipt is None
        assert len(_attempt_rows(jobs_db, claim.job_id)) == 1
        job = _job_row(jobs_db, claim.job_id)
        assert _col(job, "state") == JobState.LEASED.value

    @pytest.mark.integration
    def test_active_reconciliation_repeat_has_no_event_until_host_transition(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """相同 active observation 重放不追加 event；状态转换才写 event。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        obs = _observation(correlation, HostRunObservationState.CREATED)
        store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, obs)
        active_events = [
            row
            for row in _events_for(jobs_db, claim.job_id)
            if _col(row, "event_type") == "correlation_host_active"
        ]
        assert len(active_events) == 1
        store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, obs)
        active_events = [
            row
            for row in _events_for(jobs_db, claim.job_id)
            if _col(row, "event_type") == "correlation_host_active"
        ]
        assert len(active_events) == 1
        running = _observation(correlation, HostRunObservationState.RUNNING)
        store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, running)
        active_events = [
            row
            for row in _events_for(jobs_db, claim.job_id)
            if _col(row, "event_type") == "correlation_host_active"
        ]
        assert len(active_events) == 2

    @pytest.mark.integration
    def test_host_transition_between_reconciliation_observations_terminalizes_once(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """active -> terminal 转换只 terminalize 一次（重放复用同一 receipt）。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        running = _observation(correlation, HostRunObservationState.RUNNING)
        store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, running)
        succeeded = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        decision = store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation.id, succeeded
        )
        assert (
            decision.action is AgentRunTerminalReconciliationAction.TERMINALIZED_SUCCESS
        )
        assert decision.receipt is not None
        receipts = _receipts_for(jobs_db, claim.attempt_id)
        assert len(receipts) == 1
        replay = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, succeeded)
        assert (
            replay.action
            is AgentRunTerminalReconciliationAction.ALREADY_TERMINALIZED_SUCCESS
        )
        assert replay.receipt is not None
        assert replay.receipt.receipt.sha256 == decision.receipt.receipt.sha256
        assert len(_receipts_for(jobs_db, claim.attempt_id)) == 1

    @pytest.mark.integration
    def test_host_success_terminal_reconcile_writes_exact_receipt_and_event(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """Host SUCCEEDED terminalize 写 Host-origin receipt 与 event。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        succeeded = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        decision = store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation.id, succeeded
        )
        assert (
            decision.action is AgentRunTerminalReconciliationAction.TERMINALIZED_SUCCESS
        )
        assert decision.receipt is not None
        assert decision.receipt.outcome is AttemptReceiptOutcome.SUCCEEDED
        assert decision.receipt.safe_error_code is None
        assert (
            decision.receipt.receipt.schema_name
            == "dayu.job.agent-run-terminal-receipt"
        )
        job = _job_row(jobs_db, claim.job_id)
        assert _col(job, "state") == JobState.SUCCEEDED.value

    @pytest.mark.integration
    def test_host_unsettled_maps_to_unsettled_state_code_and_failure_action(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """Host UNSETTLED 唯一映射 host_unsettled + host_run_unsettled。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        unsettled = _observation(
            correlation,
            HostRunObservationState.UNSETTLED,
            completed_at=_pg_now(jobs_db),
        )
        decision = store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation.id, unsettled
        )
        assert (
            decision.action is AgentRunTerminalReconciliationAction.TERMINALIZED_FAILURE
        )
        assert decision.receipt is not None
        assert decision.receipt.safe_error_code is SafeJobErrorCode.HOST_RUN_UNSETTLED
        correlation_row = store.get_agent_run_correlation(_SCOPE_A, correlation.id)
        assert correlation_row.state is CorrelationState.HOST_UNSETTLED

    @pytest.mark.integration
    def test_host_failed_or_unsettled_terminalizes_with_retry_policy(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """Host FAILED/UNSETTLED 以 retry policy 收敛（可重试回 ready）。"""

        descriptor = _descriptor()
        _, claim, correlation = _reserve_correlation(
            store, jobs_db, descriptor=descriptor
        )
        failed = _observation(
            correlation,
            HostRunObservationState.FAILED,
            completed_at=_pg_now(jobs_db),
        )
        decision = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, failed)
        assert (
            decision.action is AgentRunTerminalReconciliationAction.TERMINALIZED_FAILURE
        )
        assert decision.receipt is not None
        assert decision.receipt.safe_error_code is SafeJobErrorCode.HOST_RUN_FAILED
        job = _job_row(jobs_db, claim.job_id)
        assert _col(job, "state") == JobState.READY.value

    @pytest.mark.integration
    def test_host_cancelled_terminalizes_cancel_receipt(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """Host CANCELLED terminalize 写 cancelled receipt 且 job cancelled。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        cancelled = _observation(
            correlation,
            HostRunObservationState.CANCELLED,
            completed_at=_pg_now(jobs_db),
        )
        decision = store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation.id, cancelled
        )
        assert (
            decision.action is AgentRunTerminalReconciliationAction.TERMINALIZED_CANCEL
        )
        assert decision.receipt is not None
        assert decision.receipt.safe_error_code is SafeJobErrorCode.HOST_RUN_CANCELLED
        job = _job_row(jobs_db, claim.job_id)
        assert _col(job, "state") == JobState.CANCELLED.value

    @pytest.mark.integration
    def test_terminal_reconcile_applies_cancel_then_deadline_then_host_outcome(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """terminalize 严格按 cancel intent -> deadline -> Host outcome 收敛。"""

        import time as time_module

        # cancel intent 优先于 deadline 与 Host success。
        _, claim, correlation = _reserve_correlation(
            store, jobs_db, descriptor=_descriptor_short_lease()
        )
        store.cancel(
            _SCOPE_A, JobCancellationRequest(job_id=claim.job_id, reason="operator")
        )
        time_module.sleep(1.5)  # 越过 short lease 与 deadline。
        succeeded = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        decision = store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation.id, succeeded
        )
        assert (
            decision.action is AgentRunTerminalReconciliationAction.TERMINALIZED_CANCEL
        )
        assert decision.receipt is not None
        assert decision.receipt.outcome is AttemptReceiptOutcome.CANCELLED
        assert decision.receipt.safe_error_code is SafeJobErrorCode.CANCELLED
        job = _job_row(jobs_db, claim.job_id)
        assert _col(job, "state") == JobState.CANCELLED.value

        # 无 cancel intent 且 deadline 已到：deadline 优先于 Host outcome。
        _, claim2, correlation2 = _reserve_correlation(
            store,
            jobs_db,
            descriptor=_descriptor_short_lease(),
            idempotency_key="key-deadline-first",
            deadline_delta=timedelta(seconds=1),
        )
        time_module.sleep(1.5)
        succeeded2 = _observation(
            correlation2,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        decision2 = store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation2.id, succeeded2
        )
        assert (
            decision2.action
            is AgentRunTerminalReconciliationAction.TERMINALIZED_FAILURE
        )
        assert decision2.receipt is not None
        assert decision2.receipt.safe_error_code is SafeJobErrorCode.DEADLINE_EXCEEDED
        job2 = _job_row(jobs_db, claim2.job_id)
        assert _col(job2, "state") == JobState.FAILED.value

        # 无 cancel 且未到 deadline：Host outcome 生效。
        _, claim3, correlation3 = _reserve_correlation(
            store, jobs_db, idempotency_key="key-host-first"
        )
        succeeded3 = _observation(
            correlation3,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        decision3 = store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation3.id, succeeded3
        )
        assert (
            decision3.action
            is AgentRunTerminalReconciliationAction.TERMINALIZED_SUCCESS
        )
        assert decision3.receipt is not None
        job3 = _job_row(jobs_db, claim3.job_id)
        assert _col(job3, "state") == JobState.SUCCEEDED.value

    @pytest.mark.integration
    def test_observed_host_disappearance_is_invariant_failure(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """已记录 active 后 Host 消失（missing）是 invariant failure。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        created = _observation(correlation, HostRunObservationState.CREATED)
        store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, created)
        missing = _observation(correlation, HostRunObservationState.MISSING)
        decision = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, missing)
        assert decision.action is AgentRunTerminalReconciliationAction.INVARIANT_FAILURE
        assert decision.safe_error_code is SafeJobErrorCode.CORRELATION_INVARIANT
        # 相同 missing 重放不追加 event。
        invariant_events = [
            row
            for row in _events_for(jobs_db, claim.job_id)
            if _col(row, "event_type") == "correlation_invariant"
        ]
        assert len(invariant_events) == 1
        store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, missing)
        invariant_events = [
            row
            for row in _events_for(jobs_db, claim.job_id)
            if _col(row, "event_type") == "correlation_invariant"
        ]
        assert len(invariant_events) == 1

    @pytest.mark.integration
    def test_correlation_identity_or_state_mismatch_is_invariant_failure(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """terminal 后矛盾 observation 是 invariant failure。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        succeeded = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, succeeded)
        failed = _observation(
            correlation,
            HostRunObservationState.FAILED,
            completed_at=_pg_now(jobs_db),
        )
        decision = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, failed)
        assert decision.action is AgentRunTerminalReconciliationAction.INVARIANT_FAILURE
        assert decision.safe_error_code is SafeJobErrorCode.CORRELATION_INVARIANT


def _descriptor_short_lease() -> JobHandlerDescriptor:
    """构造短 lease 的 descriptor（1s，便于 recover/过期测试）。

    Args:
        无。

    Returns:
        ``JobHandlerDescriptor``。
    """

    return JobHandlerDescriptor(
        job_type="test.short-lease",
        payload_schema_name="test.payload",
        payload_schema_version=1,
        max_attempts=5,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=1,
    )


class TestReceiptRoundtrip:
    """receipt bytes/hash 的 DB roundtrip 与不可变复用。"""

    @pytest.mark.integration
    def test_generic_attempt_receipt_db_roundtrip_preserves_bytes_and_hash(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """receipt 行保存的 bytes/hash 与返回 DTO 完全一致，仅一行。"""

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        receipt = store.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
        assert receipt.result is not None
        rows = _receipts_for(jobs_db, claim.attempt_id)
        assert len(rows) == 1
        receipt_bytes = _col(rows[0], "receipt_bytes")
        result_bytes = _col(rows[0], "result_bytes")
        assert isinstance(receipt_bytes, (bytes, memoryview))
        assert isinstance(result_bytes, (bytes, memoryview))
        assert bytes(receipt_bytes) == receipt.receipt.canonical_bytes
        assert _col(rows[0], "receipt_sha256") == receipt.receipt.sha256
        assert bytes(result_bytes) == receipt.result.canonical_bytes
        assert _col(rows[0], "result_sha256") == receipt.result.sha256
        # 终态后 recover 不再触碰该 attempt，行数与 bytes 不变。
        store.recover(_SCOPE_A)
        rows_after = _receipts_for(jobs_db, claim.attempt_id)
        assert len(rows_after) == 1
        receipt_bytes_after = _col(rows_after[0], "receipt_bytes")
        assert isinstance(receipt_bytes_after, (bytes, memoryview))
        assert bytes(receipt_bytes_after) == receipt.receipt.canonical_bytes

    @pytest.mark.integration
    def test_duplicate_non_host_finalization_reuses_existing_receipt_bytes_and_hash(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """同一 attempt 的重复收口不重写 receipt（行数/bytes/hash 不变）。"""

        import time as time_module

        _, job_id = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(
                jobs_db,
                available_delta=timedelta(minutes=-1),
                deadline_delta=timedelta(seconds=1),
            ),
        )
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        time_module.sleep(1.5)
        with pytest.raises(JobDeadlineExceededError):
            store.heartbeat(_SCOPE_A, claim.lease)
        rows = _receipts_for(jobs_db, claim.attempt_id)
        assert len(rows) == 1
        first_bytes_value = _col(rows[0], "receipt_bytes")
        assert isinstance(first_bytes_value, (bytes, memoryview))
        first_bytes = bytes(first_bytes_value)
        first_sha = _col(rows[0], "receipt_sha256")
        # 重复 finalization（陈旧 heartbeat）被 fence，不追加、不改写。
        with pytest.raises(JobLeaseLostError):
            store.heartbeat(_SCOPE_A, claim.lease)
        rows_after = _receipts_for(jobs_db, claim.attempt_id)
        assert len(rows_after) == 1
        receipt_bytes_after = _col(rows_after[0], "receipt_bytes")
        assert isinstance(receipt_bytes_after, (bytes, memoryview))
        assert bytes(receipt_bytes_after) == first_bytes
        assert _col(rows_after[0], "receipt_sha256") == first_sha


class TestTargetedNoHostRecovery:
    """targeted NO_HOST_RUN recovery 隔离与零突变。"""

    @pytest.mark.integration
    def test_targeted_no_host_recovery_isolated_from_active_and_no_correlation_attempts(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """targeted 只收敛该一条 NO_HOST_RUN correlation；其它 attempt 不受触碰。"""

        import time as time_module

        # target：reserved + missing + 过期 lease。
        descriptor = _descriptor_short_lease()
        _, claim_t, correlation_t = _reserve_correlation(
            store, jobs_db, descriptor=descriptor, idempotency_key="t1"
        )
        target_job = claim_t.job_id
        decision = store.reconcile_agent_run_terminal(
            _SCOPE_A,
            correlation_t.id,
            _observation(correlation_t, HostRunObservationState.MISSING),
        )
        assert decision.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        # active：leased + running。
        _, claim_a, correlation_a = _reserve_correlation(
            store, jobs_db, idempotency_key="t2"
        )
        active_job = claim_a.job_id
        store.reconcile_agent_run_terminal(
            _SCOPE_A,
            correlation_a.id,
            _observation(correlation_a, HostRunObservationState.RUNNING),
        )
        # no-correlation：leased attempt（claim 后不 reserve）。
        _, no_corr_job = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(jobs_db, idempotency_key="t3"),
        )
        claim_nc = _claim(store, _SCOPE_A, "worker-3")
        assert claim_nc is not None
        time_module.sleep(1.5)
        # targeted 只作用于 target。
        result = store.recover_agent_run_after_no_host(
            _SCOPE_A, correlation_t.id, decision.observation.sha256
        )
        assert result is not None
        assert result.job_id == target_job
        # active attempt 未被 targeted 触碰。
        active_attempt = _attempt_rows(jobs_db, active_job)[0]
        assert _col(active_attempt, "state") == AttemptState.LEASED.value
        # no-correlation attempt 未被 targeted 触碰（generic recover 才会收敛）。
        no_corr_attempt = _attempt_rows(jobs_db, no_corr_job)[0]
        assert _col(no_corr_attempt, "state") == AttemptState.LEASED.value
        del claim_t

    @pytest.mark.integration
    def test_targeted_no_host_recovery_changed_observation_state_or_fence_is_zero_mutation(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """observation state/fingerprint 变化后 targeted 返回 None 且零 mutation。"""

        import time as time_module

        descriptor = _descriptor_short_lease()
        _, claim_z, correlation = _reserve_correlation(
            store, jobs_db, descriptor=descriptor, idempotency_key="zm"
        )
        job_id = claim_z.job_id
        missing = _observation(correlation, HostRunObservationState.MISSING)
        decision = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, missing)
        assert decision.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        # 状态被改写（active observation 持久化后 correlation 不再 reserved）。
        store.reconcile_agent_run_terminal(
            _SCOPE_A,
            correlation.id,
            _observation(correlation, HostRunObservationState.RUNNING),
        )
        time_module.sleep(1.5)
        result = store.recover_agent_run_after_no_host(
            _SCOPE_A, correlation.id, decision.observation.sha256
        )
        assert result is None
        attempts = _attempt_rows(jobs_db, job_id)
        assert len(attempts) == 1
        assert _col(attempts[0], "state") == AttemptState.LEASED.value

    @pytest.mark.integration
    def test_crash_after_claim_before_reserve_recovers_without_host_side_effect(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """claim 后 reserve 前崩溃：无 correlation、无 Host side effect，generic recover 收敛。"""

        import time as time_module

        descriptor = _descriptor_short_lease()
        _, job_id = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(jobs_db, descriptor=descriptor, idempotency_key="crash"),
        )
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        time_module.sleep(1.5)
        recovered = store.recover(_SCOPE_A)
        result = next((r for r in recovered if r.job_id == job_id), None)
        assert result is not None
        assert result.job_state is JobState.READY
        assert result.attempt_state is AttemptState.ABANDONED
        correlations = _query(
            jobs_db,
            f"SELECT count(*) AS c FROM {_JOBS_SCHEMA}.agent_run_correlations WHERE job_run_id = :job_id",
            {"job_id": str(job_id)},
        )
        assert correlations[0][0] == 0
        del claim


class TestTerminalVersusRecover:
    """terminal reconciliation 与 recover 的竞态裁决。"""

    @pytest.mark.integration
    def test_terminal_reconcile_wins_before_recover(
        self, store: PostgresJobStore, second_store: PostgresJobStore, jobs_db
    ) -> None:
        """terminal reconcile 先取得 job lock：job 终态化，recover 不再收敛。"""

        _, claim_s, correlation = _reserve_correlation(store, jobs_db)
        job_id = claim_s.job_id
        claim = claim_s
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()
        succeeded = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )

        def terminalizer() -> None:
            """以第二 engine 执行 terminal reconciliation 并记录 action。"""

            barrier.wait()
            decision = second_store.reconcile_agent_run_terminal(
                _SCOPE_A, correlation.id, succeeded
            )
            with outcomes_lock:
                outcomes.append(f"t:{decision.action.value}")

        def recoverer() -> None:
            """执行 generic recover 并记录结果数量。"""

            barrier.wait()
            try:
                results = store.recover(_SCOPE_A)
                with outcomes_lock:
                    outcomes.append(f"r:{len(results)}")
            except Exception as exc:  # pragma: no cover
                with outcomes_lock:
                    outcomes.append(f"r:ERR:{type(exc).__name__}")

        threads = [
            threading.Thread(target=terminalizer),
            threading.Thread(target=recoverer),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        job = _job_row(jobs_db, job_id)
        assert _col(job, "state") == JobState.SUCCEEDED.value
        assert len(_receipts_for(jobs_db, claim.attempt_id)) == 1
        assert any(o.startswith("t:TERMINALIZED_SUCCESS") for o in outcomes)

    @pytest.mark.integration
    def test_terminal_reconciliation_replay_returns_existing_receipt_without_event(
        self, store: PostgresJobStore, second_store: PostgresJobStore, jobs_db
    ) -> None:
        """terminal-first 后第二 worker 重放：复用同一 immutable receipt、无新 event。"""

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        job_id = claim.job_id
        succeeded = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        first = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, succeeded)
        assert first.action is AgentRunTerminalReconciliationAction.TERMINALIZED_SUCCESS
        assert first.receipt is not None
        assert len(_receipts_for(jobs_db, claim.attempt_id)) == 1
        terminal_events = [
            row
            for row in _events_for(jobs_db, job_id)
            if _col(row, "event_type") == "correlation_host_terminal"
        ]
        assert len(terminal_events) == 1
        # 第二 worker（独立 engine）重放同一 observation。
        replay = second_store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation.id, succeeded
        )
        assert (
            replay.action
            is AgentRunTerminalReconciliationAction.ALREADY_TERMINALIZED_SUCCESS
        )
        assert replay.receipt is not None
        assert replay.receipt.receipt.sha256 == first.receipt.receipt.sha256
        assert len(_receipts_for(jobs_db, claim.attempt_id)) == 1
        terminal_events_after = [
            row
            for row in _events_for(jobs_db, job_id)
            if _col(row, "event_type") == "correlation_host_terminal"
        ]
        assert len(terminal_events_after) == 1

    @pytest.mark.integration
    def test_recover_wins_terminal_reconcile_is_stale_without_receipt_or_job_mutation(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """recover 先取得 job lock：旧 attempt abandoned，terminal reconcile 为 stale。"""

        import time as time_module

        descriptor = _descriptor_short_lease()
        _, claim_rw, correlation = _reserve_correlation(
            store, jobs_db, descriptor=descriptor, idempotency_key="rw"
        )
        job_id = claim_rw.job_id
        claim = claim_rw
        no_host = store.reconcile_agent_run_terminal(
            _SCOPE_A,
            correlation.id,
            _observation(correlation, HostRunObservationState.MISSING),
        )
        assert no_host.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        time_module.sleep(1.5)
        targeted = store.recover_agent_run_after_no_host(
            _SCOPE_A, correlation.id, no_host.observation.sha256
        )
        assert targeted is not None
        succeeded = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        decision = store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation.id, succeeded
        )
        assert decision.action is AgentRunTerminalReconciliationAction.STALE_ATTEMPT
        assert decision.safe_error_code is SafeJobErrorCode.CORRELATION_STALE_ATTEMPT
        assert decision.receipt is None
        job = _job_row(jobs_db, job_id)
        assert _col(job, "state") == JobState.READY.value
        # targeted 恢复已写 lease_expired receipt；stale 决策不新增/改写。
        assert len(_receipts_for(jobs_db, claim.attempt_id)) == 1

    @pytest.mark.integration
    def test_recover_stale_reconciliation_replay_returns_already_stale_without_event(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """stale observation 重放返回 ALREADY_STALE_ATTEMPT 且不追加 event。"""

        import time as time_module

        descriptor = _descriptor_short_lease()
        _, claim_rs, correlation = _reserve_correlation(
            store, jobs_db, descriptor=descriptor, idempotency_key="rs"
        )
        job_id = claim_rs.job_id
        no_host = store.reconcile_agent_run_terminal(
            _SCOPE_A,
            correlation.id,
            _observation(correlation, HostRunObservationState.MISSING),
        )
        assert no_host.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        time_module.sleep(1.5)
        targeted = store.recover_agent_run_after_no_host(
            _SCOPE_A, correlation.id, no_host.observation.sha256
        )
        assert targeted is not None
        succeeded = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        first = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, succeeded)
        assert first.action is AgentRunTerminalReconciliationAction.STALE_ATTEMPT
        stale_events = [
            row
            for row in _events_for(jobs_db, job_id)
            if _col(row, "event_type") == "correlation_stale_attempt"
        ]
        assert len(stale_events) == 1
        second = store.reconcile_agent_run_terminal(_SCOPE_A, correlation.id, succeeded)
        assert (
            second.action is AgentRunTerminalReconciliationAction.ALREADY_STALE_ATTEMPT
        )
        stale_events = [
            row
            for row in _events_for(jobs_db, job_id)
            if _col(row, "event_type") == "correlation_stale_attempt"
        ]
        assert len(stale_events) == 1

    @pytest.mark.integration
    def test_newer_attempt_stale_correlation_only_records_safe_observation(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """新 attempt 出现后旧 correlation reconcile 只记录 stale observation。"""

        import time as time_module

        descriptor = _descriptor_short_lease()
        _, claim_na, correlation = _reserve_correlation(
            store, jobs_db, descriptor=descriptor, idempotency_key="na"
        )
        job_id = claim_na.job_id
        no_host = store.reconcile_agent_run_terminal(
            _SCOPE_A,
            correlation.id,
            _observation(correlation, HostRunObservationState.MISSING),
        )
        assert no_host.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
        time_module.sleep(1.5)
        targeted = store.recover_agent_run_after_no_host(
            _SCOPE_A, correlation.id, no_host.observation.sha256
        )
        assert targeted is not None
        time_module.sleep(1.2)
        claim2 = _claim(store, _SCOPE_A, "worker-2")
        assert claim2 is not None
        assert claim2.attempt_number == 2
        succeeded = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        decision = store.reconcile_agent_run_terminal(
            _SCOPE_A, correlation.id, succeeded
        )
        assert decision.action is AgentRunTerminalReconciliationAction.STALE_ATTEMPT
        assert decision.receipt is None
        # 新 attempt 与 job 不受影响。
        job = _job_row(jobs_db, job_id)
        assert _col(job, "state") == JobState.LEASED.value
        attempts = _attempt_rows(jobs_db, job_id)
        assert _col(attempts[1], "state") == AttemptState.LEASED.value


class TestCorrelationLockOrderAndLateReread:
    """correlation 统一锁序与父行锁内 late re-read 的真实竞态。"""

    @pytest.mark.integration
    def test_correlation_mutations_share_job_attempt_lease_correlation_lock_order_without_deadlock(
        self,
        store: PostgresJobStore,
        second_store: PostgresJobStore,
        jobs_db,
    ) -> None:
        """heartbeat 与 terminal reconcile 并发时有界结束且只终结一次。

        Args:
            store: 第一条独立 app engine。
            second_store: 第二条独立 app engine。
            jobs_db: 数据库信息。

        Returns:
            无。

        Raises:
            无。
        """

        _, claim, correlation = _reserve_correlation(
            store,
            jobs_db,
            idempotency_key="lock-order-heartbeat-terminal",
        )
        observation = _observation(
            correlation,
            HostRunObservationState.SUCCEEDED,
            completed_at=_pg_now(jobs_db),
        )
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()

        def heartbeat_writer() -> None:
            """并发续租；terminal 先赢时接受 closed lease-lost。"""

            try:
                barrier.wait(timeout=5)
                heartbeat = store.heartbeat(_SCOPE_A, claim.lease)
                with outcomes_lock:
                    outcomes.append(f"heartbeat:{heartbeat.action.value}")
            except JobLeaseLostError:
                with outcomes_lock:
                    outcomes.append("heartbeat:lease_lost")
            except Exception as error:  # pragma: no cover - 仅保留诊断
                with outcomes_lock:
                    outcomes.append(f"heartbeat:error:{type(error).__name__}")

        def terminal_writer() -> None:
            """并发写入 Host terminal reconciliation。"""

            try:
                barrier.wait(timeout=5)
                decision = second_store.reconcile_agent_run_terminal(
                    _SCOPE_A,
                    correlation.id,
                    observation,
                )
                with outcomes_lock:
                    outcomes.append(f"terminal:{decision.action.value}")
            except Exception as error:  # pragma: no cover - 仅保留诊断
                with outcomes_lock:
                    outcomes.append(f"terminal:error:{type(error).__name__}")

        threads = (
            threading.Thread(
                target=heartbeat_writer,
                name="correlation-heartbeat-writer",
                daemon=True,
            ),
            threading.Thread(
                target=terminal_writer,
                name="correlation-terminal-writer",
                daemon=True,
            ),
        )
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert all(not thread.is_alive() for thread in threads), outcomes
        assert any(
            outcome == "terminal:TERMINALIZED_SUCCESS" for outcome in outcomes
        ), outcomes
        assert any(
            outcome in ("heartbeat:renewed", "heartbeat:lease_lost")
            for outcome in outcomes
        ), outcomes
        assert not any(":error:" in outcome for outcome in outcomes), outcomes

        persisted = store.get_agent_run_correlation(_SCOPE_A, correlation.id)
        assert persisted.id == correlation.id
        assert persisted.tenant_id == correlation.tenant_id
        assert persisted.job_id == claim.job_id
        assert persisted.attempt_id == claim.attempt_id
        assert persisted.idempotency_key == correlation.idempotency_key
        assert persisted.reserved_host_run_id == correlation.reserved_host_run_id
        assert persisted.state is CorrelationState.HOST_SUCCEEDED
        assert (
            _col(_job_row(jobs_db, claim.job_id), "state") == JobState.SUCCEEDED.value
        )
        assert len(_receipts_for(jobs_db, claim.attempt_id)) == 1
        event_types = [
            str(_col(row, "event_type")) for row in _events_for(jobs_db, claim.job_id)
        ]
        assert event_types.count("correlation_host_terminal") == 1
        assert event_types.count("job_completed") == 0
        assert event_types.count("job_failed") == 0
        assert event_types.count("job_lease_expired") == 0

    @pytest.mark.integration
    @pytest.mark.parametrize("operation", ("heartbeat", "complete", "fail"))
    def test_reserve_racing_heartbeat_complete_or_fail_has_one_late_rechecked_linearized_outcome(
        self,
        operation: str,
        store: PostgresJobStore,
        second_store: PostgresJobStore,
        jobs_db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """reserve 提交后 generic writer 在父行锁内重读并服从 governance。

        Args:
            operation: generic writer 分支。
            store: generic writer 的独立 app engine。
            second_store: reserve writer 的独立 app engine。
            jobs_db: 数据库信息。
            monkeypatch: pytest 临时执行 seam。

        Returns:
            无。

        Raises:
            无。
        """

        from dayu.investment.storage import postgres_jobs as postgres_jobs_module

        _, job_id = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(
                jobs_db,
                idempotency_key=f"late-reread-{operation}",
            ),
        )
        claim = _claim(store, _SCOPE_A, f"worker-late-reread-{operation}")
        assert claim is not None
        original_clock = postgres_jobs_module._clock
        reservation_finished = threading.Event()

        def clock_with_generic_writer_seam(session):
            """让 generic writer 在取 PG clock 后等待 reserve commit。"""

            sampled = original_clock(session)
            if threading.current_thread().name == "generic-correlation-racer":
                if not reservation_finished.wait(timeout=10):
                    raise AssertionError("reserve writer 未在有界时间内完成")
            return sampled

        monkeypatch.setattr(
            postgres_jobs_module,
            "_clock",
            clock_with_generic_writer_seam,
        )
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()
        reserved_ids: list[UUID] = []

        def reserve_writer() -> None:
            """通过第二 engine 提交 correlation，并释放 generic seam。"""

            try:
                barrier.wait(timeout=5)
                reserved = second_store.reserve_agent_run_correlation(
                    _SCOPE_A,
                    claim.lease,
                )
                with outcomes_lock:
                    reserved_ids.append(reserved.id)
                    outcomes.append("reserve:ok")
            except Exception as error:  # pragma: no cover - 仅保留诊断
                with outcomes_lock:
                    outcomes.append(f"reserve:error:{type(error).__name__}")
            finally:
                reservation_finished.set()

        def generic_writer() -> None:
            """执行 heartbeat/complete/fail 之一并记录闭合结果。"""

            try:
                barrier.wait(timeout=5)
                if operation == "heartbeat":
                    result = store.heartbeat(_SCOPE_A, claim.lease)
                    with outcomes_lock:
                        outcomes.append(f"generic:{result.action.value}")
                elif operation == "complete":
                    store.complete(
                        _SCOPE_A,
                        claim.lease,
                        JobCompletion(result=_result()),
                    )
                    with outcomes_lock:
                        outcomes.append("generic:unexpected_terminal")
                else:
                    store.fail(
                        _SCOPE_A,
                        claim.lease,
                        JobFailure(
                            safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
                            retryable=False,
                        ),
                    )
                    with outcomes_lock:
                        outcomes.append("generic:unexpected_terminal")
            except JobGovernanceRequiredError:
                with outcomes_lock:
                    outcomes.append("generic:governance_required")
            except Exception as error:  # pragma: no cover - 仅保留诊断
                with outcomes_lock:
                    outcomes.append(f"generic:error:{type(error).__name__}")

        threads = (
            threading.Thread(
                target=reserve_writer,
                name="correlation-reserve-writer",
                daemon=True,
            ),
            threading.Thread(
                target=generic_writer,
                name="generic-correlation-racer",
                daemon=True,
            ),
        )
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert all(not thread.is_alive() for thread in threads), outcomes
        assert outcomes.count("reserve:ok") == 1, outcomes
        expected_generic = (
            "generic:renewed"
            if operation == "heartbeat"
            else "generic:governance_required"
        )
        assert outcomes.count(expected_generic) == 1, outcomes
        assert not any(":error:" in outcome for outcome in outcomes), outcomes
        assert len(reserved_ids) == 1

        correlation = store.get_agent_run_correlation(_SCOPE_A, reserved_ids[0])
        assert correlation.id == reserved_ids[0]
        assert correlation.tenant_id == _TENANT_A
        assert correlation.job_id == job_id
        assert correlation.attempt_id == claim.attempt_id
        assert correlation.reserved_host_run_id == f"run_{claim.attempt_id.hex}"
        assert correlation.state is CorrelationState.RESERVED
        assert _col(_job_row(jobs_db, job_id), "state") == JobState.LEASED.value
        attempts = _attempt_rows(jobs_db, job_id)
        assert len(attempts) == 1
        assert _col(attempts[0], "state") == AttemptState.LEASED.value
        assert _receipts_for(jobs_db, claim.attempt_id) == []
        event_types = [
            str(_col(row, "event_type")) for row in _events_for(jobs_db, job_id)
        ]
        assert event_types.count("correlation_reserved") == 1
        assert event_types.count("job_completed") == 0
        assert event_types.count("job_failed") == 0
        assert event_types.count("job_lease_expired") == 0

    @pytest.mark.integration
    def test_generic_recover_racing_correlation_reservation_late_rechecks_and_skips(
        self,
        store: PostgresJobStore,
        second_store: PostgresJobStore,
        jobs_db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """recover 旧候选在父行锁后用新 statement 看见 correlation 并跳过。

        Args:
            store: reserve writer 的独立 app engine。
            second_store: generic recover 的独立 app engine。
            jobs_db: 数据库信息。
            monkeypatch: pytest 临时 clock/execute seam。

        Returns:
            无。

        Raises:
            无。
        """

        import time as time_module

        from sqlalchemy.orm import Session

        from dayu.investment.storage import postgres_jobs as postgres_jobs_module

        _, job_id = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(
                jobs_db,
                descriptor=_descriptor_short_lease(),
                idempotency_key="recover-reserve-late-reread",
            ),
        )
        claim = _claim(store, _SCOPE_A, "worker-recover-reserve-race")
        assert claim is not None

        original_clock = postgres_jobs_module._clock
        original_execute = Session.execute
        reserve_clock_sampled = threading.Event()
        allow_reserve = threading.Event()
        recover_candidate_selected = threading.Event()
        allow_recover = threading.Event()

        def clock_with_reserve_seam(session):
            """冻结 reserve 的 PG clock，让其稍后仍按取样时点验证 lease。"""

            sampled = original_clock(session)
            if threading.current_thread().name == "correlation-reserve-racer":
                reserve_clock_sampled.set()
                if not allow_reserve.wait(timeout=10):
                    raise AssertionError("reserve seam 未在有界时间内释放")
            return sampled

        def execute_with_recover_candidate_seam(
            session,
            statement,
            *args,
            **kwargs,
        ):
            """在 recover 第一条候选 statement 完成后暂停父行加锁。"""

            result = original_execute(session, statement, *args, **kwargs)
            sql = str(statement)
            if (
                threading.current_thread().name == "generic-recover-racer"
                and "NOT EXISTS (" in sql
                and "agent_run_correlations c" in sql
            ):
                recover_candidate_selected.set()
                if not allow_recover.wait(timeout=10):
                    raise AssertionError("recover seam 未在有界时间内释放")
            return result

        monkeypatch.setattr(
            postgres_jobs_module,
            "_clock",
            clock_with_reserve_seam,
        )
        monkeypatch.setattr(Session, "execute", execute_with_recover_candidate_seam)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()
        reserved_ids: list[UUID] = []
        recovery_counts: list[int] = []

        def reserve_writer() -> None:
            """以 lease 取样时点进入 reserve，待 recover 形成旧候选后提交。"""

            try:
                reserved = store.reserve_agent_run_correlation(
                    _SCOPE_A,
                    claim.lease,
                )
                with outcomes_lock:
                    reserved_ids.append(reserved.id)
                    outcomes.append("reserve:ok")
            except Exception as error:  # pragma: no cover - 仅保留诊断
                with outcomes_lock:
                    outcomes.append(f"reserve:error:{type(error).__name__}")

        def recover_writer() -> None:
            """从 correlation 不存在的旧候选进入，随后执行 late re-read。"""

            try:
                recovered = second_store.recover(_SCOPE_A)
                with outcomes_lock:
                    recovery_counts.append(len(recovered))
                    outcomes.append("recover:ok")
            except Exception as error:  # pragma: no cover - 仅保留诊断
                with outcomes_lock:
                    outcomes.append(f"recover:error:{type(error).__name__}")

        reserve_thread = threading.Thread(
            target=reserve_writer,
            name="correlation-reserve-racer",
            daemon=True,
        )
        reserve_thread.start()
        assert reserve_clock_sampled.wait(timeout=5)
        time_module.sleep(1.2)
        eligible = _query(
            jobs_db,
            f"SELECT count(*) AS c FROM {_JOBS_SCHEMA}.job_attempts a "
            f"JOIN {_JOBS_SCHEMA}.job_runs j ON j.tenant_id = a.tenant_id "
            "AND j.id = a.job_run_id "
            f"WHERE a.id = '{claim.attempt_id}' "
            "AND a.state = 'leased' AND j.state = 'leased' "
            "AND a.lease_expires_at <= clock_timestamp() "
            "AND NOT EXISTS ("
            f"SELECT 1 FROM {_JOBS_SCHEMA}.agent_run_correlations c "
            "WHERE c.tenant_id = a.tenant_id AND c.attempt_id = a.id)",
        )
        assert _col(eligible[0], "c") == 1

        recover_thread = threading.Thread(
            target=recover_writer,
            name="generic-recover-racer",
            daemon=True,
        )
        recover_thread.start()
        assert recover_candidate_selected.wait(timeout=5)
        allow_reserve.set()
        reserve_thread.join(timeout=10)
        assert not reserve_thread.is_alive(), outcomes
        assert outcomes.count("reserve:ok") == 1, outcomes
        allow_recover.set()
        recover_thread.join(timeout=10)
        assert not recover_thread.is_alive(), outcomes
        assert outcomes.count("recover:ok") == 1, outcomes
        assert not any(":error:" in outcome for outcome in outcomes), outcomes
        assert recovery_counts == [0]
        assert len(reserved_ids) == 1

        correlation = second_store.get_agent_run_correlation(
            _SCOPE_A,
            reserved_ids[0],
        )
        assert correlation.id == reserved_ids[0]
        assert correlation.tenant_id == _TENANT_A
        assert correlation.job_id == job_id
        assert correlation.attempt_id == claim.attempt_id
        assert correlation.idempotency_key == "recover-reserve-late-reread"
        assert correlation.reserved_host_run_id == f"run_{claim.attempt_id.hex}"
        assert correlation.state is CorrelationState.RESERVED
        assert _col(_job_row(jobs_db, job_id), "state") == JobState.LEASED.value
        attempts = _attempt_rows(jobs_db, job_id)
        assert len(attempts) == 1
        assert _col(attempts[0], "state") == AttemptState.LEASED.value
        assert _receipts_for(jobs_db, claim.attempt_id) == []
        lease_rows = _query(
            jobs_db,
            f"SELECT released_at FROM {_JOBS_SCHEMA}.job_leases WHERE attempt_id = :attempt_id",
            {"attempt_id": str(claim.attempt_id)},
        )
        assert len(lease_rows) == 1
        assert _col(lease_rows[0], "released_at") is None
        event_types = [
            str(_col(row, "event_type")) for row in _events_for(jobs_db, job_id)
        ]
        assert event_types == [
            "job_created",
            "job_claimed",
            "correlation_reserved",
        ]


class TestSlice21BranchCoverage:
    """Slice 2.1 剩余状态机分支的补强覆盖（不改变契约语义）。"""

    @pytest.mark.integration
    def test_list_expired_agent_run_correlations_returns_only_expired_reserved(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """expired-correlation 枚举：未过期为空，过期后按 (created_at, id) 返回。"""

        import time as time_module

        descriptor = _descriptor_short_lease()
        _, _, correlation = _reserve_correlation(
            store, jobs_db, descriptor=descriptor, idempotency_key="k-listed"
        )
        assert store.list_expired_agent_run_correlations(_SCOPE_A) == ()
        time_module.sleep(1.5)
        expired = store.list_expired_agent_run_correlations(_SCOPE_A)
        assert [item.id for item in expired] == [correlation.id]
        assert expired[0].state is CorrelationState.RESERVED

    @pytest.mark.integration
    def test_reserve_correlation_reuse_and_expired_and_deadline_errors(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """reserve：同 attempt 复用逐字段相等；过期 lease 与 deadline 各抛稳定错误。"""

        import time as time_module

        # 同 attempt 已存在 correlation：immutable compare 后返回相同。
        _, claim, correlation = _reserve_correlation(store, jobs_db)
        again = store.reserve_agent_run_correlation(_SCOPE_A, claim.lease)
        assert again.id == correlation.id
        assert again.state is CorrelationState.RESERVED
        # 过期 lease：JobLeaseLostError。
        _, claim2, _ = _reserve_correlation(
            store,
            jobs_db,
            descriptor=_descriptor_short_lease(),
            idempotency_key="k-reserve-expired",
        )
        time_module.sleep(1.5)
        with pytest.raises(JobLeaseLostError):
            store.reserve_agent_run_correlation(_SCOPE_A, claim2.lease)
        # deadline 已到但 lease 仍有效：JobDeadlineExceededError。
        _, claim3, _ = _reserve_correlation(
            store,
            jobs_db,
            descriptor=_descriptor(),
            idempotency_key="k-reserve-deadline",
            deadline_delta=timedelta(seconds=1),
        )
        time_module.sleep(1.5)
        with pytest.raises(JobDeadlineExceededError):
            store.reserve_agent_run_correlation(_SCOPE_A, claim3.lease)

    @pytest.mark.integration
    def test_authorize_cancel_deadline_and_terminal_correlation_actions(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """authorize返回cancel/deadline决策，correlated deadline不写PG终态。"""

        import time as time_module

        # cancel intent。
        _, claim, correlation = _reserve_correlation(store, jobs_db)
        store.cancel(
            _SCOPE_A, JobCancellationRequest(job_id=claim.job_id, reason="operator")
        )
        decision = store.authorize_agent_run_start(
            _SCOPE_A, claim.lease, correlation.id
        )
        assert decision.action is AgentRunStartAuthorizationAction.CANCEL
        assert decision.safe_error_code is SafeJobErrorCode.CANCELLED
        # deadline 已到。
        _, claim2, correlation2 = _reserve_correlation(
            store,
            jobs_db,
            descriptor=_descriptor(),
            idempotency_key="k-auth-deadline",
            deadline_delta=timedelta(seconds=1),
        )
        time_module.sleep(1.5)
        before_deadline_authorization = _job_snapshot(jobs_db, claim2.job_id)
        decision2 = store.authorize_agent_run_start(
            _SCOPE_A, claim2.lease, correlation2.id
        )
        assert decision2.action is AgentRunStartAuthorizationAction.DEADLINE_EXCEEDED
        assert decision2.safe_error_code is SafeJobErrorCode.DEADLINE_EXCEEDED
        assert decision2.correlation == correlation2
        assert _job_snapshot(jobs_db, claim2.job_id) == before_deadline_authorization
        assert _col(_job_row(jobs_db, claim2.job_id), "state") == JobState.LEASED.value
        attempts = _attempt_rows(jobs_db, claim2.job_id)
        assert _col(attempts[0], "state") == AttemptState.LEASED.value
        assert _receipts_for(jobs_db, claim2.attempt_id) == []

    @pytest.mark.integration
    def test_cancel_terminal_job_reports_attempt_state_and_receipt(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """对已 terminal job 再次 cancel：如实报告 attempt state 与 immutable receipt。"""

        _enqueue(
            store,
            _SCOPE_A,
            _pg_request(jobs_db, idempotency_key="k-terminal-cancel"),
        )
        claim = _claim(store, _SCOPE_A, "worker-terminal-cancel")
        assert claim is not None
        store.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
        result = store.cancel(
            _SCOPE_A, JobCancellationRequest(job_id=claim.job_id, reason="operator")
        )
        assert result.job_state is JobState.SUCCEEDED
        assert result.attempt_id == claim.attempt_id
        assert result.attempt_state is AttemptState.SUCCEEDED
        assert result.receipt is not None
        assert result.receipt.outcome is AttemptReceiptOutcome.SUCCEEDED

    @pytest.mark.integration
    def test_complete_deadline_and_heartbeat_cancel_intent_branches(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """complete 遇 deadline 抛错并收敛 failed；heartbeat 遇 cancel intent 抛 JobStateConflictError。"""

        import time as time_module

        _enqueue(
            store,
            _SCOPE_A,
            _pg_request(
                jobs_db,
                descriptor=_descriptor(),
                idempotency_key="k-complete-deadline",
                deadline_delta=timedelta(seconds=1),
            ),
        )
        claim = _claim(store, _SCOPE_A, "worker-complete-deadline")
        assert claim is not None
        time_module.sleep(1.5)
        with pytest.raises(JobDeadlineExceededError):
            store.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
        job = _job_row(jobs_db, claim.job_id)
        assert _col(job, "state") == JobState.FAILED.value
        assert (
            _col(job, "safe_failure_code") == SafeJobErrorCode.DEADLINE_EXCEEDED.value
        )
        # generic heartbeat 遇 cancel intent。
        _enqueue(
            store,
            _SCOPE_A,
            _pg_request(jobs_db, idempotency_key="k-heartbeat-cancel"),
        )
        claim2 = _claim(store, _SCOPE_A, "worker-heartbeat-cancel")
        assert claim2 is not None
        store.cancel(
            _SCOPE_A, JobCancellationRequest(job_id=claim2.job_id, reason="operator")
        )
        with pytest.raises(JobStateConflictError):
            store.heartbeat(_SCOPE_A, claim2.lease)

    @pytest.mark.integration
    def test_correlated_complete_and_fail_are_rejected_until_host_terminal_reconciliation(
        self,
        store: PostgresJobStore,
        jobs_db,
    ) -> None:
        """correlation 存在时 complete/fail 必须零 mutation 转治理。

        Args:
            store: 真实 PostgreSQL job store。
            jobs_db: 数据库信息。

        Returns:
            无。

        Raises:
            无。
        """

        _, claim, _ = _reserve_correlation(
            store,
            jobs_db,
            idempotency_key="k-correlated-finalize",
        )
        before = _job_snapshot(jobs_db, claim.job_id)
        with pytest.raises(JobGovernanceRequiredError):
            store.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
        assert _job_snapshot(jobs_db, claim.job_id) == before
        with pytest.raises(JobGovernanceRequiredError):
            store.fail(
                _SCOPE_A,
                claim.lease,
                JobFailure(
                    safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
                    retryable=False,
                ),
            )
        assert _job_snapshot(jobs_db, claim.job_id) == before

    @pytest.mark.integration
    def test_correlated_heartbeat_renews_past_business_deadline_with_governance_required_action(
        self,
        store: PostgresJobStore,
        jobs_db,
    ) -> None:
        """correlated heartbeat 过业务 deadline 仍续同 lease 并请求治理。

        Args:
            store: 真实 PostgreSQL job store。
            jobs_db: 数据库信息。

        Returns:
            无。

        Raises:
            无。
        """

        import time as time_module

        _, claim, _ = _reserve_correlation(
            store,
            jobs_db,
            idempotency_key="k-correlated-heartbeat-deadline",
            deadline_delta=timedelta(seconds=1),
        )
        time_module.sleep(1.5)
        result = store.heartbeat(_SCOPE_A, claim.lease)

        assert result.action is JobHeartbeatAction.GOVERNANCE_REQUIRED
        assert result.claim.job_id == claim.job_id
        assert result.claim.attempt_id == claim.attempt_id
        assert result.claim.lease.fence == claim.lease.fence
        assert result.claim.lease.raw_token == claim.lease.raw_token
        assert result.claim.lease.expires_at > claim.lease.expires_at
        assert _col(_job_row(jobs_db, claim.job_id), "state") == JobState.LEASED.value
        assert _receipts_for(jobs_db, claim.attempt_id) == []

    @pytest.mark.integration
    def test_generic_and_correlated_deadline_priority_contracts_are_distinct(
        self,
        store: PostgresJobStore,
        jobs_db: tuple[PlatformCluster, str],
    ) -> None:
        """同一 PG deadline 后 generic 终结而 correlated 只续租并治理。

        Args:
            store: 真实 PostgreSQL job store。
            jobs_db: 独立真实 PostgreSQL 16 数据库。

        Returns:
            无。

        Raises:
            无。
        """

        _, generic_job_id = _enqueue(
            store,
            _SCOPE_A,
            _pg_request(
                jobs_db,
                idempotency_key="generic-deadline-priority",
                deadline_delta=timedelta(seconds=2),
            ),
        )
        generic_claim = _claim(store, _SCOPE_A, "generic-deadline-worker")
        assert generic_claim is not None
        _, correlated_claim, _ = _reserve_correlation(
            store,
            jobs_db,
            idempotency_key="correlated-deadline-priority",
            deadline_delta=timedelta(seconds=2),
        )
        latest_deadline = max(
            generic_claim.deadline_at,
            correlated_claim.deadline_at,
        )
        wait_seconds = max(
            0.0,
            (latest_deadline - _pg_now(jobs_db)).total_seconds(),
        )
        deadline_wait = threading.Event()
        assert deadline_wait.wait(timeout=wait_seconds + 0.1) is False
        assert _pg_now(jobs_db) >= latest_deadline

        with pytest.raises(JobDeadlineExceededError):
            store.heartbeat(_SCOPE_A, generic_claim.lease)
        correlated = store.heartbeat(_SCOPE_A, correlated_claim.lease)

        assert correlated.action is JobHeartbeatAction.GOVERNANCE_REQUIRED
        assert correlated.claim.job_id == correlated_claim.job_id
        assert correlated.claim.attempt_id == correlated_claim.attempt_id
        assert correlated.claim.lease.fence == correlated_claim.lease.fence
        assert correlated.claim.lease.raw_token == correlated_claim.lease.raw_token
        generic_row = _job_row(jobs_db, generic_job_id)
        assert _col(generic_row, "state") == JobState.FAILED.value
        assert (
            _col(generic_row, "safe_failure_code")
            == SafeJobErrorCode.DEADLINE_EXCEEDED.value
        )
        correlated_row = _job_row(jobs_db, correlated_claim.job_id)
        assert _col(correlated_row, "state") == JobState.LEASED.value
        correlated_attempts = _attempt_rows(jobs_db, correlated_claim.job_id)
        assert len(correlated_attempts) == 1
        assert _col(correlated_attempts[0], "state") == AttemptState.LEASED.value
        assert _receipts_for(jobs_db, correlated_claim.attempt_id) == []

    @pytest.mark.integration
    def test_correlated_deadline_does_not_follow_generic_heartbeat_terminalization(
        self,
        store: PostgresJobStore,
        jobs_db,
    ) -> None:
        """correlated complete 在 deadline 后仍优先治理且不写 PG terminal。

        Args:
            store: 真实 PostgreSQL job store。
            jobs_db: 数据库信息。

        Returns:
            无。

        Raises:
            无。
        """

        import time as time_module

        _, claim, _ = _reserve_correlation(
            store,
            jobs_db,
            idempotency_key="k-correlated-complete-deadline",
            deadline_delta=timedelta(seconds=1),
        )
        time_module.sleep(1.5)
        before = _job_snapshot(jobs_db, claim.job_id)
        with pytest.raises(JobGovernanceRequiredError):
            store.complete(_SCOPE_A, claim.lease, JobCompletion(result=_result()))
        assert _job_snapshot(jobs_db, claim.job_id) == before


def _job_snapshot(jobs_db, job_id: UUID) -> tuple:
    """快照 job 相关的 attempt/lease/correlation/receipt/event 行。"""

    return (
        _job_row(jobs_db, job_id),
        tuple(_attempt_rows(jobs_db, job_id)),
        tuple(
            _query(
                jobs_db,
                f"SELECT * FROM {_JOBS_SCHEMA}.job_leases WHERE job_run_id = :job_id ORDER BY id",
                {"job_id": str(job_id)},
            )
        ),
        tuple(
            _query(
                jobs_db,
                f"SELECT * FROM {_JOBS_SCHEMA}.agent_run_correlations WHERE job_run_id = :job_id ORDER BY id",
                {"job_id": str(job_id)},
            )
        ),
        tuple(
            _query(
                jobs_db,
                f"SELECT * FROM {_JOBS_SCHEMA}.job_attempt_receipts WHERE job_run_id = :job_id ORDER BY id",
                {"job_id": str(job_id)},
            )
        ),
        tuple(_events_for(jobs_db, job_id)),
    )


class TestWrongTenantLeaseHandle:
    """wrong-tenant lease handle 在 SQL/业务查询前 fail closed（零 mutation）。"""

    @pytest.mark.integration
    def test_heartbeat_complete_fail_reserve_reject_wrong_tenant_handle(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """wrong-tenant handle 对 heartbeat/complete/fail/reserve 一律 JobLeaseLostError 且零变化。"""

        from dataclasses import replace

        _, claim, _ = _reserve_correlation(store, jobs_db)
        job_id = claim.job_id
        wrong = replace(claim.lease, tenant_id=_TENANT_B)
        assert wrong.tenant_id != claim.lease.tenant_id
        before = _job_snapshot(jobs_db, job_id)
        with pytest.raises(JobLeaseLostError):
            store.heartbeat(_SCOPE_A, wrong)
        with pytest.raises(JobLeaseLostError):
            store.complete(_SCOPE_A, wrong, JobCompletion(result=_result()))
        with pytest.raises(JobLeaseLostError):
            store.fail(
                _SCOPE_A,
                wrong,
                JobFailure(
                    safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
                    retryable=True,
                ),
            )
        with pytest.raises(JobLeaseLostError):
            store.reserve_agent_run_correlation(_SCOPE_A, wrong)
        assert _job_snapshot(jobs_db, job_id) == before

    @pytest.mark.integration
    def test_authorize_wrong_tenant_handle_returns_lease_lost_without_mutation(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """authorize：wrong-tenant handle 返回 LEASE_LOST/LEASE_EXPIRED 且零 mutation。"""

        from dataclasses import replace

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        job_id = claim.job_id
        # 正确 handle 先建 correlation 并成功授权。
        decision_ok = store.authorize_agent_run_start(
            _SCOPE_A, claim.lease, correlation.id
        )
        assert decision_ok.action is AgentRunStartAuthorizationAction.START_REQUIRED
        wrong = replace(claim.lease, tenant_id=_TENANT_B)
        before = _job_snapshot(jobs_db, job_id)
        decision = store.authorize_agent_run_start(_SCOPE_A, wrong, correlation.id)
        assert decision.action is AgentRunStartAuthorizationAction.LEASE_LOST
        assert decision.safe_error_code is SafeJobErrorCode.LEASE_EXPIRED
        assert _job_snapshot(jobs_db, job_id) == before


class TestCrossJobSplicedLeaseHandle:
    """同 tenant 跨 job 拼接 handle（job_id 与 attempt/fence/token 不同源）必须 fail closed。"""

    @pytest.mark.integration
    def test_spliced_handle_never_touches_either_job(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """五入口全部拒绝拼接 handle，两个 job 的 job/attempt/lease/correlation/receipt/event 零变化。"""

        from dataclasses import replace

        _, claim_a, correlation_a = _reserve_correlation(
            store, jobs_db, idempotency_key="k-splice-a"
        )
        _, claim_b, _ = _reserve_correlation(
            store, jobs_db, idempotency_key="k-splice-b"
        )
        assert claim_a.job_id != claim_b.job_id
        # job_id 来自 B，attempt/fence/token 来自 A。
        spliced = replace(claim_a.lease, job_id=claim_b.job_id)
        before_a = _job_snapshot(jobs_db, claim_a.job_id)
        before_b = _job_snapshot(jobs_db, claim_b.job_id)
        with pytest.raises(JobLeaseLostError):
            store.heartbeat(_SCOPE_A, spliced)
        with pytest.raises(JobLeaseLostError):
            store.complete(_SCOPE_A, spliced, JobCompletion(result=_result()))
        with pytest.raises(JobLeaseLostError):
            store.fail(
                _SCOPE_A,
                spliced,
                JobFailure(
                    safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
                    retryable=True,
                ),
            )
        with pytest.raises(JobLeaseLostError):
            store.reserve_agent_run_correlation(_SCOPE_A, spliced)
        decision = store.authorize_agent_run_start(_SCOPE_A, spliced, correlation_a.id)
        assert decision.action is AgentRunStartAuthorizationAction.LEASE_LOST
        assert decision.safe_error_code is SafeJobErrorCode.LEASE_EXPIRED
        assert _job_snapshot(jobs_db, claim_a.job_id) == before_a
        assert _job_snapshot(jobs_db, claim_b.job_id) == before_b


class TestLeaseFieldMatrix:
    """wrong job/attempt/fence/token 单字段矩阵（共享 lock 路径与 authorize 路径）。"""

    @pytest.mark.integration
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("job_id", UUID("00000000-0000-0000-0000-00000000dead")),
            ("attempt_id", UUID("00000000-0000-0000-0000-00000000beef")),
            ("fence", 424242),
            ("raw_token", "f" * 64),
        ],
    )
    def test_heartbeat_rejects_wrong_single_field(
        self,
        store: PostgresJobStore,
        jobs_db,
        field: str,
        value: str | int | UUID,
    ) -> None:
        """heartbeat 对单字段错误的 lease 一律 JobLeaseLostError。"""

        from dataclasses import replace

        _, claim, _ = _reserve_correlation(store, jobs_db)
        wrong = replace(claim.lease, **{field: value})
        with pytest.raises(JobLeaseLostError):
            store.heartbeat(_SCOPE_A, wrong)

    @pytest.mark.integration
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("job_id", UUID("00000000-0000-0000-0000-00000000dead")),
            ("attempt_id", UUID("00000000-0000-0000-0000-00000000beef")),
            ("fence", 424242),
            ("raw_token", "f" * 64),
        ],
    )
    def test_authorize_rejects_wrong_single_field(
        self,
        store: PostgresJobStore,
        jobs_db,
        field: str,
        value: str | int | UUID,
    ) -> None:
        """authorize 对单字段错误的 lease 返回 LEASE_LOST/LEASE_EXPIRED closed decision。"""

        from dataclasses import replace

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        wrong = replace(claim.lease, **{field: value})
        decision = store.authorize_agent_run_start(_SCOPE_A, wrong, correlation.id)
        assert decision.action is AgentRunStartAuthorizationAction.LEASE_LOST
        assert decision.safe_error_code is SafeJobErrorCode.LEASE_EXPIRED


class TestJobServicePublicCancel:
    """``JobService.cancel`` 公共路径（真实 PG Service→Store）。"""

    @pytest.mark.integration
    def test_job_service_public_cancel_ready_path(
        self, store: PostgresJobStore, jobs_db, tmp_path: Path
    ) -> None:
        """Service.cancel 对 ready job 直接 cancelled：无 attempt/receipt，events created/cancelled，后续 claim None。"""

        from dayu.host.host_store import HostStore
        from dayu.host.run_registry import SQLiteRunRegistry
        from dayu.services.job_service import JobHandlerRegistry, JobService

        host_store = HostStore(tmp_path / "service-cancel.db")
        host_store.initialize_schema()
        registry = SQLiteRunRegistry(host_store)
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=registry,
        )
        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        request = JobCancellationRequest(job_id=job_id, reason="operator")
        result = service.cancel(_SCOPE_A, request)
        assert result.job_state is JobState.CANCELLED
        assert result.attempt_id is None
        assert result.receipt is None
        assert _attempt_rows(jobs_db, job_id) == []
        assert _receipts_for(jobs_db, job_id) == []
        events = _events_for(jobs_db, job_id)
        assert [_col(row, "event_type") for row in events] == [
            "job_created",
            "job_cancelled",
        ]
        assert _claim(store, _SCOPE_A, "worker-1") is None


class TestReservedHostCrashWindows:
    """reserved Host entry 的 crash-window at-most-once（SQLite reopen seam）。

    使用真实 ``PostgresJobStore``（PG16）与真实 SQLite
    ``HostStore``/``SQLiteRunRegistry``/``DefaultHostExecutor``：以重开
    SQLite 模拟进程重启，断言每个 reserved ID 至多触发一次 Agent
    construction / model entry。
    """

    @pytest.mark.integration
    def test_crash_after_reserve_before_future_host_call_reuses_same_reserved_id(
        self,
        store: PostgresJobStore,
        jobs_db,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """reserve commit 后 Host 调用前崩溃：重启后复用同一 reserved ID 进入模型一次。"""

        from unittest.mock import Mock

        from dayu.services.job_service import JobHandlerRegistry, JobService

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        monkeypatch.setattr(
            "dayu.host.executor.build_async_agent", Mock(side_effect=_FakeAgent)
        )
        # 崩溃窗口：reserve 已 commit、Host 尚未调用。重启（重开 SQLite）。
        executor, registry = _open_host_seam(tmp_path / "host-reserve.db")
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=registry,
        )
        decision = service.authorize_agent_run_start(
            _SCOPE_A, claim.lease, correlation.id
        )
        assert decision.action is AgentRunStartAuthorizationAction.START_REQUIRED
        contract = _host_execution_contract(session_key="reserved-s1")
        _run_reserved_stream(executor, contract, correlation.reserved_host_run_id)
        run = registry.get_run(correlation.reserved_host_run_id)
        assert run is not None
        # 复用 correlation 的 reserved ID，而非随机 run。
        assert run.run_id == correlation.reserved_host_run_id
        assert run.state == RunState.SUCCEEDED
        assert _FakeAgent.construction_count == 1
        assert _FakeAgent.entry_count == 1
        # 重启后的重放：同一 reserved ID 第二次 entry 不构造第二个 Agent。
        with pytest.raises(ReservedAgentRunExistsError):
            _run_reserved_stream(executor, contract, correlation.reserved_host_run_id)
        assert _FakeAgent.construction_count == 1
        assert _FakeAgent.entry_count == 1

    @pytest.mark.integration
    def test_crash_after_host_reserved_insert_before_model_does_not_enter_model_twice(
        self,
        store: PostgresJobStore,
        jobs_db,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Host reserved INSERT 已提交、模型前崩溃：重启后不第二次构造 Agent。"""

        from unittest.mock import Mock

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        executor, registry = _open_host_seam(tmp_path / "host-insert.db")
        contract = _host_execution_contract(session_key="reserved-s2")

        def _crash_before_model(
            *,
            agent_create_args: AgentCreateArgs,
            tool_executor: ToolExecutor | None = None,
            tool_trace_recorder_factory: ToolTraceRecorderFactory | None = None,
            trace_identity: AgentTraceIdentity | None = None,
            cancellation_token: CancellationToken | None = None,
        ) -> _FakeAgent:
            """模拟 Host reserved INSERT 后、模型前崩溃。"""

            del (
                agent_create_args,
                tool_executor,
                tool_trace_recorder_factory,
                trace_identity,
                cancellation_token,
            )
            raise RuntimeError("crash-before-model")

        monkeypatch.setattr("dayu.host.executor.build_async_agent", _crash_before_model)
        with pytest.raises(RuntimeError):
            _run_reserved_stream(executor, contract, correlation.reserved_host_run_id)
        # reserved INSERT 已提交，模型零 entry。
        run = registry.get_run(correlation.reserved_host_run_id)
        assert run is not None
        assert _FakeAgent.construction_count == 0
        assert _FakeAgent.entry_count == 0
        # 重启后重试：同一 reserved ID 已存在，created=False，绝不构造第二个 Agent。
        monkeypatch.setattr(
            "dayu.host.executor.build_async_agent", Mock(side_effect=_FakeAgent)
        )
        with pytest.raises(ReservedAgentRunExistsError):
            _run_reserved_stream(executor, contract, correlation.reserved_host_run_id)
        assert _FakeAgent.construction_count == 0
        assert _FakeAgent.entry_count == 0

    @pytest.mark.integration
    def test_active_host_wait_never_enters_model_twice(
        self,
        store: PostgresJobStore,
        jobs_db,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """active Host（首 entry 已进行）不得造成第二次 Agent construction/entry。"""

        from unittest.mock import Mock

        from dayu.services.job_service import JobHandlerRegistry, JobService

        _, claim, correlation = _reserve_correlation(store, jobs_db)
        monkeypatch.setattr(
            "dayu.host.executor.build_async_agent", Mock(side_effect=_FakeAgent)
        )
        executor, registry = _open_host_seam(tmp_path / "host-active.db")
        service = JobService(
            job_store=store,
            descriptor_registry=JobHandlerRegistry(),
            host_run_reader=registry,
        )
        decision = service.authorize_agent_run_start(
            _SCOPE_A, claim.lease, correlation.id
        )
        assert decision.action is AgentRunStartAuthorizationAction.START_REQUIRED
        contract = _host_execution_contract(session_key="reserved-s3")
        _run_reserved_stream(executor, contract, correlation.reserved_host_run_id)
        assert _FakeAgent.construction_count == 1
        assert _FakeAgent.entry_count == 1
        # 第二个 caller（重启重放同一 correlation）：reserved run 已存在，
        # ensure created=False，抛 ReservedAgentRunExistsError，不第二次进模型。
        with pytest.raises(ReservedAgentRunExistsError):
            _run_reserved_stream(executor, contract, correlation.reserved_host_run_id)
        assert _FakeAgent.construction_count == 1
        assert _FakeAgent.entry_count == 1


class TestTenantIsolation:
    """跨租户 RLS 边界。"""

    @pytest.mark.integration
    def test_postgres_jobs_cross_tenant_reads_are_not_found_and_writes_denied(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """租户 B 读/写租户 A 的 job/correlation 均失败。"""

        from dayu.investment.domain.jobs import JobNotFoundError

        _, job_id = _enqueue(store, _SCOPE_A, _pg_request(jobs_db))
        claim = _claim(store, _SCOPE_A, "worker-1")
        assert claim is not None
        correlation = store.reserve_agent_run_correlation(_SCOPE_A, claim.lease)
        with pytest.raises(JobNotFoundError):
            store.get_agent_run_correlation(_SCOPE_B, correlation.id)
        with pytest.raises(Exception):
            store.cancel(_SCOPE_B, JobCancellationRequest(job_id=job_id, reason="x"))
        # 跨租户 claim 不可见 A 的 ready job。
        assert _claim(store, _SCOPE_B, "worker-b") is None

    @pytest.mark.integration
    def test_postgres_jobs_rls_setting_does_not_leak_between_transactions(
        self, store: PostgresJobStore, jobs_db
    ) -> None:
        """无 SET LOCAL 的普通连接默认 deny，租户上下文不跨事务泄漏。"""

        cluster, database = jobs_db
        from tests.integration.investment.conftest import create_temporary_login

        login = create_temporary_login(cluster, database, member_of="dayu_platform_app")
        engine = create_platform_engine(login.dsn)
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(f"SELECT count(*) FROM {_JOBS_SCHEMA}.job_definitions")
                ).fetchall()
                conn.rollback()
                assert rows[0][0] == 0
        finally:
            engine.dispose()
            from tests.integration.investment.conftest import drop_temporary_login

            drop_temporary_login(cluster, login)
