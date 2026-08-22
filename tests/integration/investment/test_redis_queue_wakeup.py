"""真实 Redis 8.4 wake-up hint 与 PostgreSQL durable queue 集成测试。

Redis 只负责可丢失、可重复、可乱序的提示；本文件用固定 digest 的
Redis 8.4 容器和真实 PostgreSQL 16 证明 queue、claim、attempt 与幂等
真源始终位于 PostgreSQL。fixture 不隐式拉取镜像，资源均使用随机名称、
owner label、loopback 随机端口和有界清理。
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from dayu.contracts.run import RunRecord
from dayu.host.redis_wakeup import RedisWakeupAdapter
from dayu.host.worker import RedisWakeupReadAction
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.domain.jobs import (
    CanonicalJobDocument,
    JobEnqueueRequest,
    JobHandlerDescriptor,
    build_canonical_document,
)
from dayu.investment.storage.db import (
    DEFAULT_ORGANIZATION_ID,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage.postgres_jobs import PostgresJobStore
from dayu.services.job_service import (
    JobHandlerRegistry,
    JobService,
    JobServiceRuntimeAdapters,
)
from tests.integration.investment.conftest import (
    PlatformCluster,
    create_temporary_login,
    drop_temporary_login,
    run_alembic_downgrade,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration

_REDIS_IMAGE = "redis:8.4.0-bookworm@sha256:c22af04bb576503bf16b3e34a1fd2fd82de0f765afd866d2e380145e0af30d78"
_OWNER_LABEL_KEY = "dayu-slice22.redis-owner"
_CONTAINER_PREFIX = "dayu-slice22-redis"
_NETWORK_PREFIX = "dayu-slice22-redis-net"
_READY_TIMEOUT_SECONDS = 30.0
_READY_POLL_INTERVAL_SECONDS = 0.2
_DOCKER_TIMEOUT_SECONDS = 30

_SCHEMA = "dayu_platform"
_JOB_TYPE = "test.redis.integration"
_MIGRATED_DATABASE_CLEANUP_CHILD_TABLES = (
    "job_events",
    "job_attempt_receipts",
    "job_leases",
    "job_attempts",
)

_TENANT_UUID = UUID(DEFAULT_ORGANIZATION_ID)


class _RedisIntegrationError(RuntimeError):
    """真实 Redis integration 基础设施失败。"""


@dataclass(frozen=True, slots=True)
class _RedisCluster:
    """本测试独占的 Redis 容器资源。

    Args:
        container_name: 随机 owned container 名。
        network_name: 随机 owned network 名。
        owner_label: 本次资源唯一 owner label 值。
        host_port: 绑定到 ``127.0.0.1`` 的随机端口。
    """

    container_name: str
    network_name: str
    owner_label: str
    host_port: int

    @property
    def url(self) -> str:
        """返回无凭据、无 query/fragment 的 loopback Redis URL。

        Args:
            无。

        Returns:
            当前容器映射的 Redis URL。

        Raises:
            无。
        """

        return f"redis://127.0.0.1:{self.host_port}/0"

    def stop(self) -> None:
        """有界停止当前 owned Redis 容器。

        Args:
            无。

        Returns:
            无。

        Raises:
            _RedisIntegrationError: owner 身份漂移或 Docker 停止失败。
        """

        _assert_owned_container(self)
        _run_docker(("stop", "--time=1", self.container_name))

    def start(self) -> None:
        """重新启动当前 owned Redis 容器并等待健康。

        Args:
            无。

        Returns:
            无。

        Raises:
            _RedisIntegrationError: owner 身份漂移、启动或 readiness 失败。
        """

        _assert_owned_container(self)
        _run_docker(("start", self.container_name))
        _wait_ready(self)


class _MissingHostReader:
    """不参与本 lane 的最小 Host reader。"""

    def get_run(self, run_id: str) -> RunRecord | None:
        """返回 Host row 不存在。

        Args:
            run_id: 未使用的 reserved run ID。

        Returns:
            恒为 ``None``。

        Raises:
            无。
        """

        del run_id
        return None


@dataclass(frozen=True, slots=True)
class _JobRuntime:
    """真实 JobService 与其 engine 生命周期句柄。

    Args:
        service: 使用真实 PostgreSQL Store 的 JobService。
        engine: 测试结束时需要 dispose 的 SQLAlchemy engine。
        descriptor: 已注册 enqueue descriptor。
    """

    service: JobService
    engine: Engine
    descriptor: JobHandlerDescriptor


def _run_docker(args: tuple[str, ...]) -> str:
    """有界执行 Docker CLI 并返回 stdout。

    Args:
        args: 不含 ``docker`` 的参数 tuple。

    Returns:
        去首尾空白的 stdout。

    Raises:
        _RedisIntegrationError: Docker 命令非零或超时。
    """

    try:
        completed = subprocess.run(
            ("docker", *args),
            capture_output=True,
            text=True,
            check=False,
            timeout=_DOCKER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise _RedisIntegrationError("Redis integration Docker command failed") from None
    if completed.returncode != 0:
        safe_tail = completed.stderr.strip()[-500:]
        raise _RedisIntegrationError(f"Redis integration Docker command failed: {safe_tail}")
    return completed.stdout.strip()


def _free_loopback_port() -> int:
    """取得一个暂时空闲的 loopback TCP 端口。

    Args:
        无。

    Returns:
        可用于 Docker publish 的端口。

    Raises:
        OSError: 本机无法绑定 loopback socket。
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _require_image() -> None:
    """镜像缺失时 hard fail，且只给出显式 pull 动作。

    Args:
        无。

    Returns:
        无。

    Raises:
        _RedisIntegrationError: 固定 digest 镜像不在本机。
    """

    try:
        _run_docker(("image", "inspect", _REDIS_IMAGE))
    except _RedisIntegrationError:
        raise _RedisIntegrationError(f"Redis 测试镜像缺失，请先显式执行:\ndocker pull {_REDIS_IMAGE}") from None


def _wait_ready(cluster: _RedisCluster) -> None:
    """以真实 RESP2 client 有界等待 Redis ready。

    Args:
        cluster: 本测试 owned Redis cluster。

    Returns:
        无。

    Raises:
        _RedisIntegrationError: readiness 超时。
    """

    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            adapter = RedisWakeupAdapter.from_url(
                cluster.url,
                timeout_seconds=0.5,
            )
            try:
                if adapter.ping():
                    return
            finally:
                adapter.close()
        except (ValueError, RuntimeError):
            pass
        time.sleep(_READY_POLL_INTERVAL_SECONDS)
    raise _RedisIntegrationError("Redis 8.4 readiness timeout")


def _assert_owned_container(cluster: _RedisCluster) -> None:
    """删除或重启前复核 container owner label。

    Args:
        cluster: 待复核 cluster。

    Returns:
        无。

    Raises:
        _RedisIntegrationError: container name/owner 不匹配。
    """

    label = _run_docker(
        (
            "inspect",
            cluster.container_name,
            "--format",
            f'{{{{index .Config.Labels "{_OWNER_LABEL_KEY}"}}}}',
        )
    )
    if label != cluster.owner_label:
        raise _RedisIntegrationError("Redis container owner identity mismatch")


def _cleanup_cluster(cluster: _RedisCluster) -> None:
    """只清理复核通过的本测试 container/network。

    Args:
        cluster: 本测试资源句柄。

    Returns:
        无。

    Raises:
        _RedisIntegrationError: owner 漂移或 Docker 清理失败。
    """

    container_inspect = subprocess.run(
        ("docker", "inspect", cluster.container_name),
        capture_output=True,
        text=True,
        check=False,
        timeout=_DOCKER_TIMEOUT_SECONDS,
    )
    if container_inspect.returncode == 0:
        _assert_owned_container(cluster)
        subprocess.run(
            ("docker", "logs", "--tail", "100", cluster.container_name),
            capture_output=True,
            text=True,
            check=False,
            timeout=_DOCKER_TIMEOUT_SECONDS,
        )
        _run_docker(("rm", "-f", cluster.container_name))

    network_inspect = subprocess.run(
        (
            "docker",
            "network",
            "inspect",
            cluster.network_name,
            "--format",
            f'{{{{index .Labels "{_OWNER_LABEL_KEY}"}}}}',
        ),
        capture_output=True,
        text=True,
        check=False,
        timeout=_DOCKER_TIMEOUT_SECONDS,
    )
    if network_inspect.returncode == 0:
        if network_inspect.stdout.strip() != cluster.owner_label:
            raise _RedisIntegrationError("Redis network owner identity mismatch")
        _run_docker(("network", "rm", cluster.network_name))


@pytest.fixture()
def redis_cluster() -> Iterator[_RedisCluster]:
    """启动并清理 function-scoped 固定 Redis 8.4 容器。

    Args:
        无。

    Returns:
        迭代产出独占 Redis cluster。

    Raises:
        _RedisIntegrationError: 镜像、Docker、readiness 或 cleanup 失败。
    """

    _require_image()
    suffix = f"{os.getpid()}-{uuid.uuid4().hex[:10]}"
    owner_label = str(uuid.uuid4())
    cluster = _RedisCluster(
        container_name=f"{_CONTAINER_PREFIX}-{suffix}",
        network_name=f"{_NETWORK_PREFIX}-{suffix}",
        owner_label=owner_label,
        host_port=_free_loopback_port(),
    )
    _run_docker(
        (
            "network",
            "create",
            "--label",
            f"{_OWNER_LABEL_KEY}={owner_label}",
            cluster.network_name,
        )
    )
    try:
        _run_docker(
            (
                "run",
                "-d",
                "--name",
                cluster.container_name,
                "--label",
                f"{_OWNER_LABEL_KEY}={owner_label}",
                "--network",
                cluster.network_name,
                "-p",
                f"127.0.0.1:{cluster.host_port}:6379",
                _REDIS_IMAGE,
                "redis-server",
                "--save",
                "",
                "--appendonly",
                "no",
            )
        )
        _wait_ready(cluster)
        yield cluster
    finally:
        _cleanup_cluster(cluster)


def _clear_migrated_jobs_database(bootstrap_dsn: str) -> None:
    """按 FK 顺序清理当前 Redis 测试拥有的 Job 业务行。

    Args:
        bootstrap_dsn: 当前独占数据库的 bootstrap superuser DSN。

    Returns:
        无。

    Raises:
        SQLAlchemyError: cleanup transaction 或数据库操作失败时传播。
    """

    cleanup_engine = create_platform_engine(bootstrap_dsn)
    try:
        with cleanup_engine.begin() as connection:
            for table_name in _MIGRATED_DATABASE_CLEANUP_CHILD_TABLES:
                connection.execute(
                    text(
                        f"""
                        DELETE FROM {_SCHEMA}.{table_name} AS child
                        USING {_SCHEMA}.job_runs AS owned_run,
                              {_SCHEMA}.job_definitions AS definition
                        WHERE child.tenant_id = owned_run.tenant_id
                          AND child.job_run_id = owned_run.id
                          AND owned_run.tenant_id = :tenant_id
                          AND owned_run.tenant_id = definition.tenant_id
                          AND owned_run.definition_id = definition.id
                          AND definition.job_type = :job_type
                        """
                    ),
                    {"tenant_id": _TENANT_UUID, "job_type": _JOB_TYPE},
                )
            connection.execute(
                text(
                    f"""
                    DELETE FROM {_SCHEMA}.job_runs AS owned_run
                    USING {_SCHEMA}.job_definitions AS definition
                    WHERE owned_run.tenant_id = :tenant_id
                      AND owned_run.tenant_id = definition.tenant_id
                      AND owned_run.definition_id = definition.id
                      AND definition.job_type = :job_type
                    """
                ),
                {"tenant_id": _TENANT_UUID, "job_type": _JOB_TYPE},
            )
    finally:
        cleanup_engine.dispose()


@pytest.fixture()
def migrated_jobs_database(
    platform_cluster: PlatformCluster,
    lifecycle_database: Callable[[], str],
) -> Iterator[tuple[PlatformCluster, str]]:
    """创建、迁移、清理并最终 downgrade 一个独立 PostgreSQL 数据库。

    Args:
        platform_cluster: 独占测试进程的 PG16 cluster。
        lifecycle_database: function-scoped database factory。

    Returns:
        迭代产出 ``(cluster, database_name)``。

    Raises:
        SQLAlchemyError: business-row cleanup 或数据库操作失败时传播。
        RuntimeError: migration downgrade admission 失败时传播。
    """

    database = lifecycle_database()
    bootstrap_dsn = platform_cluster.dsn_for_database(database, "postgres")
    run_alembic_upgrade(bootstrap_dsn)
    try:
        yield platform_cluster, database
    finally:
        _clear_migrated_jobs_database(bootstrap_dsn)
        run_alembic_downgrade(bootstrap_dsn)


def _scope() -> TenantScope:
    """构造固定 canonical tenant scope。

    Args:
        无。

    Returns:
        测试 tenant scope。

    Raises:
        无。
    """

    return Principal(
        tenant_id=TenantId(str(_TENANT_UUID)),
        user_id="redis-integration",
    ).to_scope()


def _descriptor() -> JobHandlerDescriptor:
    """构造本 lane 唯一 job descriptor。

    Args:
        无。

    Returns:
        完整 handler descriptor。

    Raises:
        无。
    """

    return JobHandlerDescriptor(
        job_type=_JOB_TYPE,
        payload_schema_name="test.redis.payload",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=60,
    )


def _payload(marker: str) -> CanonicalJobDocument:
    """构造稳定 canonical job payload。

    Args:
        marker: 业务无关的测试标记。

    Returns:
        canonical payload document。

    Raises:
        无。
    """

    return build_canonical_document(
        {"marker": marker},
        schema_name="test.redis.payload",
        schema_version=1,
    )


def _request(descriptor: JobHandlerDescriptor, marker: str) -> JobEnqueueRequest:
    """构造当前数据库时钟前已可领取的 enqueue request。

    Args:
        descriptor: 已注册 descriptor。
        marker: payload 与 idempotency 标记。

    Returns:
        完整 enqueue request。

    Raises:
        无。
    """

    available_at = datetime.now(tz=timezone.utc) - timedelta(seconds=5)
    return JobEnqueueRequest(
        descriptor=descriptor,
        idempotency_key=f"redis-integration:{marker}",
        payload=_payload(marker),
        available_at=available_at,
        deadline_at=available_at + timedelta(hours=1),
    )


@pytest.fixture()
def job_runtime(
    migrated_jobs_database: tuple[PlatformCluster, str],
    redis_cluster: _RedisCluster,
) -> Iterator[_JobRuntime]:
    """构造真实 PG Store + Redis publisher 的 JobService。

    Args:
        migrated_jobs_database: 已迁移独立数据库。
        redis_cluster: 当前真实 Redis cluster。

    Returns:
        迭代产出 JobService、engine 与 descriptor 句柄。

    Raises:
        无。
    """

    cluster, database = migrated_jobs_database
    login = create_temporary_login(
        cluster,
        database,
        member_of="dayu_platform_app",
    )
    engine = create_platform_engine(login.dsn)
    store = PostgresJobStore(session_factory=create_platform_session_factory(engine))
    descriptor = _descriptor()
    registry = JobHandlerRegistry()
    registry.register_descriptor(descriptor)
    adapter = RedisWakeupAdapter.from_url(redis_cluster.url, timeout_seconds=1.0)
    service = JobService(
        job_store=store,
        descriptor_registry=registry,
        host_run_reader=_MissingHostReader(),
        runtime_adapters=JobServiceRuntimeAdapters(wakeup_publisher=adapter),
    )
    try:
        yield _JobRuntime(service=service, engine=engine, descriptor=descriptor)
    finally:
        adapter.close()
        engine.dispose()
        drop_temporary_login(cluster, login)


def test_real_redis_81_client_resp2_interoperates_with_pinned_84_server(
    redis_cluster: _RedisCluster,
) -> None:
    """redis-py 8.1 以 RESP2 bytes 与固定 Redis 8.4 服务互通。

    Args:
        redis_cluster: 真实固定 Redis 8.4 cluster。

    Returns:
        无。

    Raises:
        无。
    """

    assert version("redis").split(".")[:2] == ["8", "1"]
    assert "v=8.4.0" in _run_docker(("exec", redis_cluster.container_name, "redis-server", "--version"))
    adapter = RedisWakeupAdapter.from_url(redis_cluster.url, timeout_seconds=1.0)
    subscriber = adapter.create_subscriber(_scope())
    try:
        assert adapter.ping() is True
        assert subscriber.resubscribe() is True
        job_id = uuid4()
        assert adapter.publish_hint(_scope(), job_id) is True
        read = subscriber.get_message(timeout_seconds=1.0)
        assert read.action is RedisWakeupReadAction.WAKEUP
        assert read.hint is not None
        assert read.hint.tenant_id == _TENANT_UUID
        assert read.hint.job_id == job_id
        client_rows = tuple(
            frozenset(line.split())
            for line in _run_docker(
                (
                    "exec",
                    redis_cluster.container_name,
                    "redis-cli",
                    "--raw",
                    "CLIENT",
                    "LIST",
                )
            ).splitlines()
        )
        assert any({"cmd=publish", "resp=2"} <= row for row in client_rows)
        assert any({"cmd=subscribe", "resp=2"} <= row for row in client_rows)
    finally:
        subscriber.close()
        adapter.close()


def test_real_redis_duplicate_and_reordered_hints_cannot_duplicate_job_or_attempt(
    job_runtime: _JobRuntime,
    redis_cluster: _RedisCluster,
) -> None:
    """重复乱序 hint 不改变 PG job/attempt 唯一性。

    Args:
        job_runtime: 真实 JobService runtime。
        redis_cluster: 真实 Redis cluster。

    Returns:
        无。

    Raises:
        无。
    """

    adapter = RedisWakeupAdapter.from_url(redis_cluster.url, timeout_seconds=1.0)
    subscriber = adapter.create_subscriber(_scope())
    try:
        assert subscriber.resubscribe() is True
        first = job_runtime.service.enqueue(
            _scope(),
            _request(job_runtime.descriptor, "first"),
        )
        second = job_runtime.service.enqueue(
            _scope(),
            _request(job_runtime.descriptor, "second"),
        )
        assert adapter.publish_hint(_scope(), second.job_id) is True
        assert adapter.publish_hint(_scope(), first.job_id) is True
        assert adapter.publish_hint(_scope(), first.job_id) is True

        hinted_jobs: list[UUID] = []
        for _index in range(5):
            read = subscriber.get_message(timeout_seconds=1.0)
            assert read.action is RedisWakeupReadAction.WAKEUP
            assert read.hint is not None
            hinted_jobs.append(read.hint.job_id)
        assert set(hinted_jobs) == {first.job_id, second.job_id}
        assert hinted_jobs.count(first.job_id) == 3
        assert hinted_jobs.count(second.job_id) == 2

        first_claim = job_runtime.service.claim(_scope(), "redis-worker-1")
        second_claim = job_runtime.service.claim(_scope(), "redis-worker-2")
        assert first_claim is not None
        assert second_claim is not None
        assert {first_claim.job_id, second_claim.job_id} == {
            first.job_id,
            second.job_id,
        }
        assert first_claim.attempt_id != second_claim.attempt_id
        assert job_runtime.service.claim(_scope(), "redis-worker-3") is None
    finally:
        subscriber.close()
        adapter.close()


def test_real_redis_disconnect_lost_hint_and_restart_still_claims_from_postgres(
    job_runtime: _JobRuntime,
    redis_cluster: _RedisCluster,
) -> None:
    """publish 断线丢失后重启 Redis，job 仍只从 PG 成功 claim。

    Args:
        job_runtime: 真实 JobService runtime。
        redis_cluster: 可 stop/start 的 owned Redis cluster。

    Returns:
        无。

    Raises:
        无。
    """

    disconnected_adapter = RedisWakeupAdapter.from_url(
        redis_cluster.url,
        timeout_seconds=0.5,
    )
    try:
        assert disconnected_adapter.ping() is True
        redis_cluster.stop()
        started_at = time.monotonic()
        assert disconnected_adapter.publish_hint(_scope(), uuid4()) is False
        assert time.monotonic() - started_at < 2.0
    finally:
        disconnected_adapter.close()
    receipt = job_runtime.service.enqueue(
        _scope(),
        _request(job_runtime.descriptor, "lost-hint"),
    )
    redis_cluster.start()
    fresh_adapter = RedisWakeupAdapter.from_url(
        redis_cluster.url,
        timeout_seconds=1.0,
    )
    try:
        assert fresh_adapter.ping() is True
        claim = job_runtime.service.claim(_scope(), "redis-restart-worker")
        assert claim is not None
        assert claim.job_id == receipt.job_id
        assert job_runtime.service.claim(_scope(), "redis-restart-worker-2") is None
    finally:
        fresh_adapter.close()
