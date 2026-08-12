"""投资平台 identity/source repository 真实 PostgreSQL 16 integration lane。

本文件复用 Slice 1.1 owner-labeled PG16 fixture（S12-CTRL-03），在真实
PostgreSQL 16 上验证：

- unique ticker/security 冲突与 atomic registration 回滚（第二个 insert
  唯一冲突后 company 行也不存在）；
- stale ``expected_version`` CAS 不修改 row；
- scope A 无法读写 scope B subscription；public reference 可投影但
  private subscription 仍按 tenant；
- 每次事务结束后 tenant setting 不泄漏；
- production startup 组合精确承载三个真实 Service：
  ``investment_identity``（``InvestmentIdentityService``）与
  ``durable_jobs``（``JobService``，``platform_service_name ==
  "durable_jobs"``）、``durable_schedules``（``ScheduleService``），且
  导入图不含 evidence/portfolio future module；
- 结束 owner resource 为零。

禁止 SQLite/fake 代替 PG 行为。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from dayu.fins.storage.s3_file_store import S3FileStore
from dayu.host.worker import RedisWakeupSubscriberProtocol
from dayu.investment.composition import (
    PlatformIdentityServiceProtocol,
    PlatformServiceProtocol,
)
from dayu.investment.config import PlatformSettings
from dayu.investment.domain.identifiers import (
    CompanyId,
    Principal,
    SecurityId,
    TenantId,
    TenantScope,
)
from dayu.investment.domain.source import (
    CompanyCreateRequest,
    CompanyProjection,
    CompanySecurityRegistration,
    JsonValue,
    SecurityCreateRequest,
    SecurityProjection,
    SecurityType,
    SourceDefinitionCreateRequest,
    SourceDefinitionId,
    SourceDefinitionProjection,
    SourceKind,
    SourceSubscriptionCreateRequest,
    SourceSubscriptionId,
    SourceSubscriptionProjection,
    SourceSubscriptionUpdateRequest,
    SubscriptionStatus,
)
from dayu.investment.storage.db import create_platform_engine, create_platform_session_factory
from dayu.investment.storage.postgres_identity import PostgresIdentityRepository
from dayu.investment.storage.protocols import (
    RepositoryConflictError,
    RepositoryError,
    RepositoryInputError,
    RepositoryNotFoundError,
    RepositoryOptimisticConflictError,
)
from dayu.services.startup_preparation import PreparedHostRuntimeDependencies
from dayu.startup.platform import PlatformCompositionError
from tests.integration.investment.conftest import (
    PlatformCluster,
    TemporaryLogin,
    create_temporary_login,
    drop_temporary_login,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration

DatabaseFactory = Callable[[], str]
_S3_DUMMY_ACCESS_KEY_ENV = "DAYU_PLATFORM_S3_ACCESS_KEY"
_S3_DUMMY_SECRET_KEY_ENV = "DAYU_PLATFORM_S3_SECRET_KEY"
_S3_DUMMY_ACCESS_KEY_VALUE = "placeholder-access"
_S3_DUMMY_SECRET_KEY_VALUE = "placeholder-secret"

_TENANT_A = TenantId("00000000-0000-0000-0000-000000000001")
_TENANT_B = TenantId("00000000-0000-0000-0000-000000000002")


def _scope(tenant_id: TenantId) -> TenantScope:
    """构造指定租户的测试范围。

    Args:
        tenant_id: 租户标识。

    Returns:
        租户范围。

    Raises:
        无。
    """

    return Principal(tenant_id=tenant_id, user_id="u-1").to_scope()


def _company_id() -> CompanyId:
    """构造随机公司标识。

    Args:
        无。

    Returns:
        公司标识。

    Raises:
        无。
    """

    return CompanyId(str(uuid.uuid4()))


def _security_id() -> SecurityId:
    """构造随机证券标识。

    Args:
        无。

    Returns:
        证券标识。

    Raises:
        无。
    """

    return SecurityId(str(uuid.uuid4()))


def _source_definition_id() -> SourceDefinitionId:
    """构造随机数据源定义标识。

    Args:
        无。

    Returns:
        数据源定义标识。

    Raises:
        无。
    """

    return SourceDefinitionId(str(uuid.uuid4()))


def _subscription_id() -> SourceSubscriptionId:
    """构造随机订阅标识。

    Args:
        无。

    Returns:
        订阅标识。

    Raises:
        无。
    """

    return SourceSubscriptionId(str(uuid.uuid4()))


def _registration(company_id: CompanyId, security_id: SecurityId) -> CompanySecurityRegistration:
    """构造公司+证券注册请求。

    Args:
        company_id: 公司标识。
        security_id: 证券标识。

    Returns:
        注册请求。

    Raises:
        无。
    """

    return CompanySecurityRegistration(
        company=CompanyCreateRequest(
            company_id=company_id,
            legal_name="Acme Corp",
            lei=None,
            country_code="US",
        ),
        security=SecurityCreateRequest(
            security_id=security_id,
            company_id=company_id,
            ticker="ACME",
            exchange_mic="XNYS",
            security_type=SecurityType.EQUITY,
            currency="USD",
            isin=None,
            is_active=True,
        ),
    )


def _source_definition_request(
    source_definition_id: SourceDefinitionId,
    source_key: str,
) -> SourceDefinitionCreateRequest:
    """构造数据源定义创建请求。

    Args:
        source_definition_id: 数据源定义标识。
        source_key: 数据源唯一键。

    Returns:
        数据源定义创建请求。

    Raises:
        无。
    """

    return SourceDefinitionCreateRequest(
        source_definition_id=source_definition_id,
        source_key=source_key,
        source_kind=SourceKind.FILING,
        display_name="SEC 财报",
        enabled_by_default=True,
    )


def _subscription_request(
    subscription_id: SourceSubscriptionId,
    source_definition_id: SourceDefinitionId,
    company_id: CompanyId,
) -> SourceSubscriptionCreateRequest:
    """构造订阅创建请求。

    Args:
        subscription_id: 订阅标识。
        source_definition_id: 数据源定义标识。
        company_id: 公司目标。

    Returns:
        订阅创建请求。

    Raises:
        无。
    """

    return SourceSubscriptionCreateRequest(
        subscription_id=subscription_id,
        source_definition_id=source_definition_id,
        company_id=company_id,
        security_id=None,
        status=SubscriptionStatus.ENABLED,
        config={"interval_minutes": 60},
    )


def _build_strict_s3_object_storage_payload() -> str:
    """构造 production 严格契约所需的 6-key 对象存储配置 JSON。

    Args:
        无。

    Returns:
        严格 JSON 字符串。

    Raises:
        无。
    """

    payload: dict[str, str] = {
        "backend": "s3",
        "endpoint_url": "http://127.0.0.1:9000",
        "region": "us-east-1",
        "bucket": "dayu-platform-test-bucket",
        "access_key_env": _S3_DUMMY_ACCESS_KEY_ENV,
        "secret_key_env": _S3_DUMMY_SECRET_KEY_ENV,
    }
    return json.dumps(payload, ensure_ascii=False)


def _setup_production_startup_env(monkeypatch: pytest.MonkeyPatch, *, dsn: str) -> None:
    """为 production startup black-box 测试设置严格合法的环境变量。

    Args:
        monkeypatch: pytest 打桩器，用于临时注入环境变量。
        dsn: 真实 startup 所需的数据库连接串。

    Returns:
        无。

    Raises:
        无。
    """

    monkeypatch.setenv("DAYU_PLATFORM_ENABLED", "1")
    monkeypatch.setenv("DAYU_PLATFORM_PROFILE", "production")
    monkeypatch.setenv("DAYU_PLATFORM_POSTGRES_DSN", dsn)
    monkeypatch.setenv("DAYU_PLATFORM_OBJECT_STORAGE", _build_strict_s3_object_storage_payload())
    monkeypatch.setenv("DAYU_PLATFORM_REDIS_URL", "redis://placeholder")
    monkeypatch.setenv("DAYU_PLATFORM_AUTH_KEY", "placeholder")
    monkeypatch.setenv(_S3_DUMMY_ACCESS_KEY_ENV, _S3_DUMMY_ACCESS_KEY_VALUE)
    monkeypatch.setenv(_S3_DUMMY_SECRET_KEY_ENV, _S3_DUMMY_SECRET_KEY_VALUE)


def _cleanup_production_startup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清理 production startup black-box 测试设置的环境变量。

    Args:
        monkeypatch: pytest 打桩器，用于删除临时环境变量。

    Returns:
        无。

    Raises:
        无。
    """

    for env_name in (
        "DAYU_PLATFORM_ENABLED",
        "DAYU_PLATFORM_PROFILE",
        "DAYU_PLATFORM_POSTGRES_DSN",
        "DAYU_PLATFORM_OBJECT_STORAGE",
        "DAYU_PLATFORM_REDIS_URL",
        "DAYU_PLATFORM_AUTH_KEY",
        _S3_DUMMY_ACCESS_KEY_ENV,
        _S3_DUMMY_SECRET_KEY_ENV,
    ):
        monkeypatch.delenv(env_name, raising=False)


class _FakeRepositorySet:
    """黑盒测试专用最小 repository set 替身。"""

    def __init__(self) -> None:
        """仅保留实例身份，不承载任何初始化副作用。"""

        self.core = None


class _PlatformProviderSentinel:
    """用于确认 placeholder 阶段不会触达 platform provider 的计数替身。"""

    def __init__(self, counter: list[int]) -> None:
        """初始化并绑定计数容器。

        Args:
            counter: 计数共享容器。

        Returns:
            无。

        Raises:
            无。
        """

        self._counter = counter

    def provide_services(self) -> Mapping[str, PlatformServiceProtocol]:
        """提高 provider 计数并返回空服务映射。

        Returns:
            空服务映射。

        Raises:
            无。
        """

        self._counter[0] += 1
        return {}


def _head_bucket_noop(self: S3FileStore) -> None:
    """签名兼容 `S3FileStore.head_bucket` 的 noop 探活桩。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """


def _cleanup_production_startup_resources(
    *,
    prepared: PreparedHostRuntimeDependencies | None,
    monkeypatch: pytest.MonkeyPatch,
    cluster: PlatformCluster,
    database: str,
    login: TemporaryLogin | None,
) -> list[Exception]:
    """清理 production startup 黑盒测试期间的运行时资源。

    Args:
        prepared: 可选已构建的 `PreparedHostRuntimeDependencies`。
        monkeypatch: 用于回滚 monkeypatch 环境变量。
        cluster: PG 集群句柄。
        database: 当前数据库名。
        login: 可选的临时 LOGIN。

    Returns:
        清理阶段产生的异常列表。

    Raises:
        无。
    """

    cleanup_errors: list[Exception] = []
    if prepared is not None:
        try:
            prepared.close()
        except Exception as exc:
            cleanup_errors.append(exc)
    try:
        _cleanup_production_startup_env(monkeypatch)
    except Exception as exc:
        cleanup_errors.append(exc)
    if login is not None:
        try:
            drop_temporary_login(cluster, login)
        except Exception as exc:
            cleanup_errors.append(exc)
    try:
        _migrate_down_and_assert(cluster, database)
    except Exception as exc:
        cleanup_errors.append(exc)
    return cleanup_errors


def _report_cleanup_errors(
    *,
    primary_exception: Exception | None,
    cleanup_errors: list[Exception],
    context: str,
) -> None:
    """汇总并上报清理异常，保留主异常语义。

    Args:
        primary_exception: try/finally 主路径异常。
        cleanup_errors: 清理阶段累计异常。
        context: 主异常不存在时暴露的错误上下文。

    Returns:
        无。

    Raises:
        无。
    """

    if not cleanup_errors:
        return
    if primary_exception is None:
        raise ExceptionGroup(context, cleanup_errors)
    for cleanup_error in cleanup_errors:
        primary_exception.add_note(f"cleanup error: {type(cleanup_error).__name__}: {cleanup_error}")


class _FakeWriterLease:
    """启动桩所需的 writer lease 替身。"""

    def release(self) -> None:
        """关闭替身（黑盒测试无实际副作用）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """


class _BlackBoxRedisAdmission:
    """production mapping 黑盒测试的 typed Redis admission fake。"""

    def __init__(self) -> None:
        """初始化关闭计数。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.close_calls = 0

    def ping(self) -> bool:
        """返回 admission 成功。

        Args:
            无。

        Returns:
            恒为 ``True``。

        Raises:
            无。
        """

        return True

    def publish_hint(self, scope: TenantScope, job_id: uuid.UUID) -> bool:
        """接受 PG commit 后的测试提示。

        Args:
            scope: 显式 tenant scope。
            job_id: 已提交 job UUID。

        Returns:
            恒为 ``True``。

        Raises:
            无。
        """

        del scope, job_id
        return True

    def create_subscriber(
        self,
        scope: TenantScope,
    ) -> RedisWakeupSubscriberProtocol:
        """阻止 mapping 测试意外启动 Worker subscriber。

        Args:
            scope: 显式 tenant scope。

        Returns:
            本 fake 不返回。

        Raises:
            AssertionError: mapping 测试意外启动 subscriber 时抛出。
        """

        del scope
        raise AssertionError("mapping test must not create Redis subscriber")

    def close(self) -> None:
        """记录 admission lifecycle 关闭。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.close_calls += 1


def _install_redis_admission_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 production Redis client 边界替换为 typed、无网络 fake。

    Args:
        monkeypatch: pytest 打桩器。

    Returns:
        无。

    Raises:
        无。
    """

    from dayu.host.redis_wakeup import RedisWakeupAdapter

    admission = _BlackBoxRedisAdmission()

    def _from_url(
        _adapter_type: type[RedisWakeupAdapter],
        redis_url: str,
        *,
        timeout_seconds: float,
    ) -> _BlackBoxRedisAdmission:
        """验证受控参数后返回唯一 fake admission。

        Args:
            _adapter_type: 被替换的 adapter class。
            redis_url: production settings 读取的占位 URL。
            timeout_seconds: startup 计算的有限 timeout。

        Returns:
            唯一 typed admission fake。

        Raises:
            无。
        """

        del _adapter_type
        assert redis_url == "redis://placeholder"
        assert 0 < timeout_seconds <= 1
        return admission

    monkeypatch.setattr(
        RedisWakeupAdapter,
        "from_url",
        classmethod(_from_url),
    )


def _install_black_box_startup_stubs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """安装 production startup black-box 的最小外部边界替身。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时路径。

    Returns:
        无。

    Raises:
        无。
    """

    from dayu.services import startup_preparation as sp

    _install_redis_admission_stub(monkeypatch)
    monkeypatch.setattr(sp.S3FileStore, "head_bucket", _head_bucket_noop)
    monkeypatch.setattr(
        sp,
        "resolve_startup_paths",
        lambda **_kwargs: SimpleNamespace(
            workspace_root=tmp_path,
            config_root=tmp_path / "config",
            output_dir=tmp_path / "output",
        ),
    )
    monkeypatch.setattr(
        sp,
        "acquire_writer_lease",
        lambda _workspace_root: _FakeWriterLease(),
    )
    monkeypatch.setattr(
        sp,
        "build_fs_repository_set",
        lambda **_kwargs: _FakeRepositorySet(),
    )
    monkeypatch.setattr(
        sp.DefaultFinsRuntime,
        "create",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(sp, "recover_host_startup_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sp,
        "resolve_host_config",
        lambda **_kwargs: SimpleNamespace(
            store_path=tmp_path / "host.sqlite3",
            lane_config={"llm_api": 1},
            pending_turn_resume_max_attempts=3,
            pending_turn_retention_hours=168,
            cancellation_bridge_poll_interval_seconds=0.5,
            cancellation_bridge_failure_grace_period_seconds=5.0,
        ),
    )
    monkeypatch.setattr(
        sp,
        "Host",
        lambda **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        sp,
        "HostStore",
        lambda *args, **_kwargs: SimpleNamespace(initialize_schema=lambda: None),
    )


def _migrate(cluster: PlatformCluster, database: str) -> None:
    """对该数据库运行 empty upgrade。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库名。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: admission 失败时抛出。
    """

    run_alembic_upgrade(cluster.dsn_for_database(database, "postgres"))


def _bootstrap_conn(cluster: PlatformCluster, database: str) -> Connection:
    """建立 bootstrap 管理连接。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        打开的连接。

    Raises:
        无。
    """

    engine = create_engine(cluster.dsn_for_database(database, "postgres"), echo=False)
    return engine.connect().execution_options(isolation_level="AUTOCOMMIT")


class TestIdentityRepositoryPostgres:
    """identity repository 真实 PG16 契约。"""

    @pytest.mark.integration
    def test_atomic_registration_rollback_on_unique_conflict(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """second insert 唯一冲突后 company 行也不存在。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope = _scope(_TENANT_A)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            session_factory = create_platform_session_factory(engine)
            repository = PostgresIdentityRepository(session_factory)
            company_id = _company_id()
            security_id = _security_id()
            registration = _registration(company_id, security_id)
            result = repository.register_company_security(scope, registration)
            assert result.company.company_id == company_id
            assert result.security.security_id == security_id
            # 同 (exchange_mic, ticker) 再次注册触发 securities unique 冲突，
            # 整个事务回滚：新 company 行也不应存在。
            new_company_id = _company_id()
            duplicate = _registration(new_company_id, security_id)
            with pytest.raises(RepositoryConflictError):
                repository.register_company_security(scope, duplicate)
            assert repository.get_company(scope, new_company_id) is None
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)

    @pytest.mark.integration
    def test_find_security_by_mic_and_ticker(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """按 (exchange_mic, ticker) 查找证券。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope = _scope(_TENANT_A)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            repository = PostgresIdentityRepository(create_platform_session_factory(engine))
            company_id = _company_id()
            security_id = _security_id()
            repository.register_company_security(scope, _registration(company_id, security_id))
            found = repository.find_security(scope, "XNYS", "ACME")
            assert found is not None
            assert found.security_id == security_id
            assert found.company_id == company_id
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)


class TestSourceRepositoryPostgres:
    """source repository 真实 PG16 契约。"""

    @pytest.mark.integration
    def test_subscription_cas_optimistic_conflict(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """stale expected_version CAS 不修改 row。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope = _scope(_TENANT_A)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            repository = PostgresIdentityRepository(create_platform_session_factory(engine))
            company_id = _company_id()
            security_id = _security_id()
            repository.register_company_security(scope, _registration(company_id, security_id))
            source_definition_id = _source_definition_id()
            repository.register_source_definition(
                scope,
                _source_definition_request(source_definition_id, f"sec-{uuid.uuid4().hex[:8]}"),
            )
            subscription_id = _subscription_id()
            created = repository.create_source_subscription(
                scope,
                _subscription_request(subscription_id, source_definition_id, company_id),
            )
            assert created.version == 1
            stale_request = SourceSubscriptionUpdateRequest(
                status=SubscriptionStatus.DISABLED,
                config={},
            )
            with pytest.raises(RepositoryOptimisticConflictError):
                repository.update_source_subscription(
                    scope,
                    subscription_id,
                    expected_version=99,
                    request=stale_request,
                )
            fresh = repository.get_source_subscription(scope, subscription_id)
            assert fresh is not None
            assert fresh.version == 1
            assert fresh.status is SubscriptionStatus.ENABLED
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)

    @pytest.mark.integration
    def test_cross_tenant_subscription_isolated(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """scope A 无法读写 scope B subscription；public reference 可投影。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope_a = _scope(_TENANT_A)
        scope_b = _scope(_TENANT_B)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            repository = PostgresIdentityRepository(create_platform_session_factory(engine))
            # tenant A 注册公司+证券（public reference 可投影）。
            company_id = _company_id()
            security_id = _security_id()
            repository.register_company_security(scope_a, _registration(company_id, security_id))
            # public reference 可从 tenant B 读取（无 RLS）。
            assert repository.get_company(scope_b, company_id) is not None
            # tenant A 建订阅。
            source_definition_id = _source_definition_id()
            repository.register_source_definition(
                scope_a,
                _source_definition_request(source_definition_id, f"sec-{uuid.uuid4().hex[:8]}"),
            )
            subscription_id = _subscription_id()
            repository.create_source_subscription(
                scope_a,
                _subscription_request(subscription_id, source_definition_id, company_id),
            )
            # tenant B 读 tenant A 的订阅：not-found（不泄漏存在性）。
            assert repository.get_source_subscription(scope_b, subscription_id) is None
            # tenant B 更新 tenant A 的订阅：not-found。
            with pytest.raises(RepositoryNotFoundError):
                repository.update_source_subscription(
                    scope_b,
                    subscription_id,
                    expected_version=1,
                    request=SourceSubscriptionUpdateRequest(
                        status=SubscriptionStatus.DISABLED,
                        config={},
                    ),
                )
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)

    @pytest.mark.integration
    def test_tenant_setting_does_not_leak_after_transaction(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """每次事务结束后 tenant setting 不泄漏。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope = _scope(_TENANT_A)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            repository = PostgresIdentityRepository(create_platform_session_factory(engine))
            company_id = _company_id()
            security_id = _security_id()
            repository.register_company_security(scope, _registration(company_id, security_id))
            # 新连接（非 repository 会话）不应看到 tenant A 的 private row。
            probe_conn = engine.connect()
            try:
                count = probe_conn.execute(
                    text("SELECT count(*) FROM dayu_platform.source_subscriptions")
                ).scalar()
                assert count == 0
            finally:
                probe_conn.close()
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)

    @pytest.mark.integration
    def test_identity_read_paths_and_input_errors(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """identity 读取路径与 RepositoryInputError 分支。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope = _scope(_TENANT_A)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            repository = PostgresIdentityRepository(create_platform_session_factory(engine))
            company_id = _company_id()
            security_id = _security_id()
            repository.register_company_security(scope, _registration(company_id, security_id))
            # get_security / get_company 命中。
            fetched = repository.get_security(scope, security_id)
            assert fetched is not None
            assert fetched.company_id == company_id
            fetched_company = repository.get_company(scope, company_id)
            assert fetched_company is not None
            assert fetched_company.legal_name == "Acme Corp"
            # 未存在 id -> None。
            assert repository.get_company(scope, _company_id()) is None
            assert repository.get_security(scope, _security_id()) is None
            # find_security 未命中 -> None。
            assert repository.find_security(scope, "XNYS", "NOSUCH") is None
            # RepositoryInputError：非法 MIC 由 repository 校验。
            with pytest.raises(RepositoryInputError):
                repository.find_security(scope, "xny", "ACME")
            # source definition 读取路径。
            source_definition_id = _source_definition_id()
            repository.register_source_definition(
                scope,
                _source_definition_request(source_definition_id, f"sec-{uuid.uuid4().hex[:8]}"),
            )
            found_def = repository.get_source_definition(scope, source_definition_id)
            assert found_def is not None
            assert repository.get_source_definition(scope, _source_definition_id()) is None
            # update not-found。
            with pytest.raises(RepositoryNotFoundError):
                repository.update_source_subscription(
                    scope,
                    _subscription_id(),
                    expected_version=1,
                    request=SourceSubscriptionUpdateRequest(
                        status=SubscriptionStatus.DISABLED,
                        config={},
                    ),
                )
            # 非法 expected_version。
            subscription_id = _subscription_id()
            repository.create_source_subscription(
                scope,
                _subscription_request(subscription_id, source_definition_id, company_id),
            )
            with pytest.raises(RepositoryInputError):
                repository.update_source_subscription(
                    scope,
                    subscription_id,
                    expected_version=0,
                    request=SourceSubscriptionUpdateRequest(
                        status=SubscriptionStatus.DISABLED,
                        config={},
                    ),
                )
            # get_source_subscription 命中与未命中。
            got = repository.get_source_subscription(scope, subscription_id)
            assert got is not None
            assert got.status is SubscriptionStatus.ENABLED
            assert repository.get_source_subscription(scope, _subscription_id()) is None
            # find_source_definition 命中与未命中。
            found_by_key = repository.find_source_definition(scope, "sec-filings")
            assert found_by_key is None
            found_by_key = repository.find_source_definition(scope, found_def.source_key)
            assert found_by_key is not None
            assert found_by_key.source_definition_id == source_definition_id
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)

    @pytest.mark.integration
    def test_subscription_company_and_security_targets_not_misaligned(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """company-target 与 security-target 订阅 projection 不串位。

        分别创建 company-target（company_id 非空、security_id 为空）与
        security-target（security_id 非空、company_id 为空）订阅，读回并
        断言各自字段精确，验证 ``_row_subscription_full`` 列序正确。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope = _scope(_TENANT_A)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            repository = PostgresIdentityRepository(create_platform_session_factory(engine))
            company_id = _company_id()
            security_id = _security_id()
            repository.register_company_security(scope, _registration(company_id, security_id))
            source_definition_id = _source_definition_id()
            repository.register_source_definition(
                scope,
                _source_definition_request(source_definition_id, f"sec-{uuid.uuid4().hex[:8]}"),
            )
            # company-target 订阅。
            company_sub_id = _subscription_id()
            company_sub = repository.create_source_subscription(
                scope,
                _subscription_request(company_sub_id, source_definition_id, company_id),
            )
            assert company_sub.company_id == company_id
            assert company_sub.security_id is None
            # security-target 订阅。
            security_sub_id = _subscription_id()
            security_sub = repository.create_source_subscription(
                scope,
                SourceSubscriptionCreateRequest(
                    subscription_id=security_sub_id,
                    source_definition_id=source_definition_id,
                    company_id=None,
                    security_id=security_id,
                    status=SubscriptionStatus.ENABLED,
                    config={"interval_minutes": 30},
                ),
            )
            assert security_sub.security_id == security_id
            assert security_sub.company_id is None
            # 读回验证不串位。
            fetched_company = repository.get_source_subscription(scope, company_sub_id)
            assert fetched_company is not None
            assert fetched_company.company_id == company_id
            assert fetched_company.security_id is None
            assert fetched_company.status is SubscriptionStatus.ENABLED
            fetched_security = repository.get_source_subscription(scope, security_sub_id)
            assert fetched_security is not None
            assert fetched_security.security_id == security_id
            assert fetched_security.company_id is None
            assert fetched_security.status is SubscriptionStatus.ENABLED
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)

    @pytest.mark.integration
    def test_subscription_fk_violation_maps_to_repository_error(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """订阅引用不存在 source_definition 时映射 RepositoryError 并回滚。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope = _scope(_TENANT_A)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            repository = PostgresIdentityRepository(create_platform_session_factory(engine))
            missing_source_definition = _source_definition_id()
            with pytest.raises(RepositoryError):
                repository.create_source_subscription(
                    scope,
                    SourceSubscriptionCreateRequest(
                        subscription_id=_subscription_id(),
                        source_definition_id=missing_source_definition,
                        company_id=None,
                        security_id=None,
                        status=SubscriptionStatus.ENABLED,
                        config={},
                    ),
                )
            # 回滚后订阅不存在。
            probe_conn = engine.connect()
            try:
                count = probe_conn.execute(
                    text("SELECT count(*) FROM dayu_platform.source_subscriptions")
                ).scalar()
                assert count == 0
            finally:
                probe_conn.close()
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)

    @pytest.mark.integration
    def test_subscription_nested_config_round_trip(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """嵌套 Mapping/tuple-of-mapping config 经 JSONB 读写 round-trip。

        create 时传入嵌套 dict 与 tuple-of-mapping，get/CAS 读回后断言
        canonical 深冻结等价、输入修改不影响、更新后读回一致。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope = _scope(_TENANT_A)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            repository = PostgresIdentityRepository(create_platform_session_factory(engine))
            company_id = _company_id()
            security_id = _security_id()
            repository.register_company_security(scope, _registration(company_id, security_id))
            source_definition_id = _source_definition_id()
            repository.register_source_definition(
                scope,
                _source_definition_request(source_definition_id, f"sec-{uuid.uuid4().hex[:8]}"),
            )
            # 嵌套 dict + tuple-of-mapping 的深结构 config。
            nested_mapping: dict[str, str] = {"threshold": "0.5"}
            source_config: Mapping[str, JsonValue] = {
                "interval_minutes": 60,
                "nested": nested_mapping,
                "tags": ("a", {"b": 1}),
                "pairs": (("x", "y"),),
            }
            subscription_id = _subscription_id()
            created = repository.create_source_subscription(
                scope,
                SourceSubscriptionCreateRequest(
                    subscription_id=subscription_id,
                    source_definition_id=source_definition_id,
                    company_id=company_id,
                    security_id=None,
                    status=SubscriptionStatus.ENABLED,
                    config=source_config,
                ),
            )
            # 输入修改不影响已冻结投影。
            nested_mapping["threshold"] = "0.9"
            # get 读回：canonical 深冻结等价。
            got = repository.get_source_subscription(scope, subscription_id)
            assert got is not None
            assert got.config["interval_minutes"] == 60
            assert got.config["nested"] == {"threshold": "0.5"}
            assert got.config["tags"] == ("a", {"b": 1})
            assert got.config["pairs"] == (("x", "y"),)
            # CAS 更新后读回一致。
            updated = repository.update_source_subscription(
                scope,
                subscription_id,
                expected_version=created.version,
                request=SourceSubscriptionUpdateRequest(
                    status=SubscriptionStatus.DISABLED,
                    config={"interval_minutes": 120, "tags": ("z", {"c": 3})},
                ),
            )
            assert updated.version == created.version + 1
            assert updated.status is SubscriptionStatus.DISABLED
            assert updated.config["interval_minutes"] == 120
            assert updated.config["tags"] == ("z", {"c": 3})
            refetched = repository.get_source_subscription(scope, subscription_id)
            assert refetched is not None
            assert refetched.config["interval_minutes"] == 120
            assert refetched.config["tags"] == ("z", {"c": 3})
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)


class TestReadPathFaultInjection:
    """read-path 公共仓储故障语义：schema fault 映射 stable RepositoryError。

    用 bootstrap owner 临时 RENAME 目标表制造可恢复的 schema fault，
    调用对应 public get/find 方法，断言稳定 ``RepositoryError`` 且无
    DSN/SQL/候选值泄漏，随后 ``finally`` 恢复表名并证明后续调用正常。
    """

    @pytest.mark.integration
    def test_read_paths_map_schema_fault_to_repository_error(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """get/find 各方法在表被 RENAME 时抛 stable RepositoryError 且可恢复。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        scope = _scope(_TENANT_A)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        engine = create_platform_engine(app_login.dsn)
        try:
            repository = PostgresIdentityRepository(create_platform_session_factory(engine))
            company_id = _company_id()
            security_id = _security_id()
            repository.register_company_security(scope, _registration(company_id, security_id))
            source_definition_id = _source_definition_id()
            repository.register_source_definition(
                scope,
                _source_definition_request(source_definition_id, f"sec-{uuid.uuid4().hex[:8]}"),
            )
            subscription_id = _subscription_id()
            repository.create_source_subscription(
                scope,
                _subscription_request(subscription_id, source_definition_id, company_id),
            )
            # (目标表, fault 名, 调用闭包)
            faults: list[tuple[str, str, Callable[[], CompanyProjection | SecurityProjection | SourceDefinitionProjection | SourceSubscriptionProjection | None]]] = [
                (
                    "companies",
                    "companies_fault",
                    lambda: repository.get_company(scope, company_id),
                ),
                (
                    "securities",
                    "securities_fault",
                    lambda: repository.find_security(scope, "XNYS", "ACME"),
                ),
                (
                    "source_definitions",
                    "source_definitions_fault",
                    lambda: repository.find_source_definition(scope, "sec-probe"),
                ),
                (
                    "source_subscriptions",
                    "source_subscriptions_fault",
                    lambda: repository.get_source_subscription(scope, subscription_id),
                ),
            ]
            for table_name, fault_name, callable_target in faults:
                conn = _bootstrap_conn(platform_cluster, database)
                try:
                    conn.execute(
                        text(f"ALTER TABLE dayu_platform.{table_name} RENAME TO {fault_name}")
                    )
                finally:
                    conn.close()
                try:
                    with pytest.raises(RepositoryError) as excinfo:
                        callable_target()
                    message = str(excinfo.value)
                    assert "database operation failed" == message
                    assert "postgres" not in message.lower()
                    assert "password" not in message.lower()
                    assert "DSN" not in message
                finally:
                    conn = _bootstrap_conn(platform_cluster, database)
                    try:
                        conn.execute(
                            text(f"ALTER TABLE dayu_platform.{fault_name} RENAME TO {table_name}")
                        )
                    finally:
                        conn.close()
            # fault 恢复后正常调用。
            assert repository.get_company(scope, company_id) is not None
            assert repository.find_security(scope, "XNYS", "ACME") is not None
        finally:
            engine.dispose()
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down_and_assert(platform_cluster, database)


def _migrate_down_and_assert(cluster: PlatformCluster, database: str) -> None:
    """对数据库执行 downgrade 并断言 schema/roles 消失。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        无。
    """

    from tests.integration.investment.conftest import run_alembic_downgrade

    run_alembic_downgrade(cluster.dsn_for_database(database, "postgres"))
    conn = _bootstrap_conn(cluster, database)
    try:
        schema = conn.execute(
            text("SELECT 1 FROM pg_namespace WHERE nspname = 'dayu_platform'")
        ).fetchone()
        assert schema is None
        role_count = conn.execute(
            text(
                "SELECT count(*) FROM pg_roles WHERE rolname IN "
                "('dayu_platform_app', 'dayu_platform_audit')"
            )
        ).scalar()
        assert role_count == 0
    finally:
        conn.close()


class TestProductionStartupBlackBox:
    """production startup black-box：真实 PG16 全链路。"""

    @pytest.mark.integration
    def test_production_provider_wires_exact_three_service_mapping(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """production 未注入 provider 时装配 exact three-service mapping。

        default-production provider 的 key set 精确为
        ``{"investment_identity", "durable_jobs", "durable_schedules"}``；
        三者分别是真实 Identity、Job 与 Schedule Service，identity 的
        company/security 注册与重复 ``prepared.close()`` 行为保持不变。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        from dayu.services.job_service import JobService
        from dayu.services.schedule_service import ScheduleService
        from dayu.services.startup_preparation import prepare_host_runtime_dependencies

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        prepared = None
        primary_exception: Exception | None = None
        cleanup_errors: list[Exception]
        try:
            _setup_production_startup_env(monkeypatch, dsn=app_login.dsn)
            _install_black_box_startup_stubs(monkeypatch, tmp_path)
            prepared = prepare_host_runtime_dependencies(
                workspace_root=tmp_path,
                config_root=tmp_path / "config",
                execution_options=None,
                runtime_label="black-box",
                log_module="TEST",
                platform_provider=None,
            )
            services = prepared.platform_composition.services
            assert set(services) == {
                "investment_identity",
                "durable_jobs",
                "durable_schedules",
            }
            service = services["investment_identity"]
            assert isinstance(service, PlatformIdentityServiceProtocol)
            job_service = services["durable_jobs"]
            assert isinstance(job_service, JobService)
            assert job_service.platform_service_name == "durable_jobs"
            schedule_service = services["durable_schedules"]
            assert isinstance(schedule_service, ScheduleService)
            assert schedule_service.platform_service_name == "durable_schedules"
            scope = _scope(_TENANT_A)
            company_id = _company_id()
            security_id = _security_id()
            result = service.register_company_security(scope, _registration(company_id, security_id))
            assert result.company.company_id == company_id
            prepared.close()
            prepared.close()
        except Exception as exc:
            primary_exception = exc
            raise
        finally:
            cleanup_errors = _cleanup_production_startup_resources(
                prepared=prepared,
                monkeypatch=monkeypatch,
                cluster=platform_cluster,
                database=database,
                login=app_login,
            )
            _report_cleanup_errors(
                primary_exception=primary_exception,
                cleanup_errors=cleanup_errors,
                context="production startup wiring cleanup failed",
            )

    @pytest.mark.integration
    def test_production_provider_s3_placeholder_still_rejected(self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """旧 `s3://placeholder` 仍应在 provider/PG service 动作前被拒绝。"""

        from dayu.fins.storage.s3_settings import S3SettingsError
        from dayu.services import startup_preparation as sp
        from dayu.services.startup_preparation import prepare_host_runtime_dependencies

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        prepared = None
        reported_exception: Exception | None = None
        placeholder_read_calls: list[int] = [0]
        provider_calls: list[int] = [0]
        original_read_postgres = sp._read_postgres_dsn

        def _counted_read_postgres_dsn(settings: PlatformSettings) -> str:
            """计数并转发 PostgreSQL DSN 读取。

            Args:
                settings: 平台设置。

            Returns:
                原读取函数返回的 PostgreSQL DSN。

            Raises:
                透传原读取函数抛出的异常。
            """

            placeholder_read_calls[0] += 1
            return original_read_postgres(settings)

        try:
            _setup_production_startup_env(monkeypatch, dsn=app_login.dsn)
            monkeypatch.setenv("DAYU_PLATFORM_OBJECT_STORAGE", "s3://placeholder")
            _install_black_box_startup_stubs(monkeypatch, tmp_path)
            monkeypatch.setattr(sp, "_read_postgres_dsn", _counted_read_postgres_dsn)

            with pytest.raises(S3SettingsError) as excinfo:
                prepared = prepare_host_runtime_dependencies(
                    workspace_root=tmp_path,
                    config_root=tmp_path / "config",
                    execution_options=None,
                    runtime_label="black-box",
                    log_module="TEST",
                    platform_provider=_PlatformProviderSentinel(provider_calls),
                )
            assert placeholder_read_calls[0] == 0
            assert provider_calls[0] == 0
            assert "s3://placeholder" not in str(excinfo.value)
            reported_exception = excinfo.value
        except Exception as exc:
            reported_exception = exc
            raise
        finally:
            cleanup_errors = _cleanup_production_startup_resources(
                prepared=prepared,
                monkeypatch=monkeypatch,
                cluster=platform_cluster,
                database=database,
                login=app_login,
            )
            _report_cleanup_errors(
                primary_exception=reported_exception,
                cleanup_errors=cleanup_errors,
                context="production startup placeholder cleanup failed",
            )

    @pytest.mark.integration
    def test_production_provider_wrong_role_rejected(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """非 application member 的登录在 admission probe 被拒绝。

        probe 必须拒绝既非 ``dayu_platform_app`` member 又非
        superuser/BYPASSRLS 之外的 wrong-role 连接，统一抛
        ``PlatformCompositionError`` 且不回显 DSN。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        from dayu.services.startup_preparation import prepare_host_runtime_dependencies

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        wrong_login: TemporaryLogin | None = None
        prepared = None
        reported_exception: Exception | None = None
        try:
            wrong_login = create_temporary_login(
                platform_cluster,
                database,
                member_of="",
            )
            _setup_production_startup_env(monkeypatch, dsn=wrong_login.dsn)
            _install_black_box_startup_stubs(monkeypatch, tmp_path)
            with pytest.raises(PlatformCompositionError) as excinfo:
                prepared = prepare_host_runtime_dependencies(
                    workspace_root=tmp_path,
                    config_root=tmp_path / "config",
                    execution_options=None,
                    runtime_label="black-box",
                    log_module="TEST",
                    platform_provider=None,
                )
            assert wrong_login.role not in str(excinfo.value)
            assert str(platform_cluster.host_port) not in str(excinfo.value)
            reported_exception = excinfo.value
        except Exception as exc:
            reported_exception = exc
            raise
        finally:
            cleanup_errors = _cleanup_production_startup_resources(
                prepared=prepared,
                monkeypatch=monkeypatch,
                cluster=platform_cluster,
                database=database,
                login=wrong_login,
            )
            _report_cleanup_errors(
                primary_exception=reported_exception,
                cleanup_errors=cleanup_errors,
                context="production startup wrong-role cleanup failed",
            )

    @pytest.mark.integration
    def test_production_provider_missing_dsn_safe_failure(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """production 缺 provider 且 DSN env 缺失时安全失败。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        from types import SimpleNamespace

        from dayu.investment.config import PlatformSettingsError
        from dayu.services import startup_preparation as sp
        from dayu.services.startup_preparation import prepare_host_runtime_dependencies

        lifecycle_database()
        monkeypatch.setenv("DAYU_PLATFORM_ENABLED", "1")
        monkeypatch.setenv("DAYU_PLATFORM_PROFILE", "production")
        monkeypatch.delenv("DAYU_PLATFORM_POSTGRES_DSN", raising=False)
        monkeypatch.setenv("DAYU_PLATFORM_OBJECT_STORAGE", "s3://placeholder")
        monkeypatch.setenv("DAYU_PLATFORM_REDIS_URL", "redis://placeholder")
        monkeypatch.setenv("DAYU_PLATFORM_AUTH_KEY", "placeholder")
        monkeypatch.setattr(
            sp,
            "resolve_startup_paths",
            lambda **_kwargs: SimpleNamespace(
                workspace_root=tmp_path,
                config_root=tmp_path / "config",
                output_dir=tmp_path / "output",
            ),
        )
        with pytest.raises(PlatformSettingsError):
            prepare_host_runtime_dependencies(
                workspace_root=tmp_path,
                config_root=tmp_path / "config",
                execution_options=None,
                runtime_label="black-box",
                log_module="TEST",
                platform_provider=None,
            )
        monkeypatch.delenv("DAYU_PLATFORM_ENABLED", raising=False)
        monkeypatch.delenv("DAYU_PLATFORM_PROFILE", raising=False)
        monkeypatch.delenv("DAYU_PLATFORM_OBJECT_STORAGE", raising=False)
        monkeypatch.delenv("DAYU_PLATFORM_REDIS_URL", raising=False)
        monkeypatch.delenv("DAYU_PLATFORM_AUTH_KEY", raising=False)

    @pytest.mark.integration
    def test_production_provider_close_disposes_engine_once(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """prepared.close() 幂等：dispose 恰一次。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        from sqlalchemy.engine import Engine

        from dayu.services.startup_preparation import prepare_host_runtime_dependencies

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        dispose_calls: list[int] = []

        original_dispose = Engine.dispose

        def _counted_dispose(engine: Engine) -> None:
            """记录 dispose 调用次数并委托原实现。

            Args:
                engine: 被 dispose 的 engine。

            Returns:
                无。

            Raises:
                无。
            """

            dispose_calls.append(id(engine))
            return original_dispose(engine)
        prepared = None
        reported_exception: Exception | None = None
        try:
            monkeypatch.setattr(Engine, "dispose", _counted_dispose)
            _setup_production_startup_env(monkeypatch, dsn=app_login.dsn)
            _install_black_box_startup_stubs(monkeypatch, tmp_path)
            prepared = prepare_host_runtime_dependencies(
                workspace_root=tmp_path,
                config_root=tmp_path / "config",
                execution_options=None,
                runtime_label="black-box",
                log_module="TEST",
                platform_provider=None,
            )
            prepared.close()
            prepared.close()
            assert len(dispose_calls) == 1
            prepared.close()
            assert len(dispose_calls) == 1
        except Exception as exc:
            reported_exception = exc
            raise
        finally:
            monkeypatch.setattr(Engine, "dispose", original_dispose)
            cleanup_errors = _cleanup_production_startup_resources(
                prepared=prepared,
                monkeypatch=monkeypatch,
                cluster=platform_cluster,
                database=database,
                login=app_login,
            )
            _report_cleanup_errors(
                primary_exception=reported_exception,
                cleanup_errors=cleanup_errors,
                context="production startup close idempotent cleanup failed",
            )

    @pytest.mark.integration
    def test_production_provider_close_propagates_failure_and_still_cleans(self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """prepared.close() 抛错时仍保证 login/roles/schema 清理。"""

        from dayu.services import startup_preparation as sp
        from dayu.services.startup_preparation import prepare_host_runtime_dependencies

        database = lifecycle_database()
        _migrate(platform_cluster, database)
        app_login = create_temporary_login(
            platform_cluster,
            database,
            member_of="dayu_platform_app",
        )
        close_calls = 0
        close_error: RuntimeError | None = None
        prepared = None
        primary_exception: Exception | None = None

        original_s3_close = sp.S3FileStore.close

        def _failing_s3_close(store: S3FileStore) -> None:
            """首次调用抛错，二次重试委托原实现，验证错误传播后仍收口。

            计数器语义为「S3 close 调用次数」：第一次调用抛错证明
            ``prepared.close()`` 传播失败；cleanup 第二次重试走原实现并
            继续 platform lifecycle 收口。
            """

            nonlocal close_calls
            close_calls += 1
            if close_calls == 1:
                raise RuntimeError("simulated prepared close failure")
            original_s3_close(store)

        try:
            monkeypatch.setattr(sp.S3FileStore, "close", _failing_s3_close)
            _setup_production_startup_env(monkeypatch, dsn=app_login.dsn)
            _install_black_box_startup_stubs(monkeypatch, tmp_path)
            prepared = prepare_host_runtime_dependencies(
                workspace_root=tmp_path,
                config_root=tmp_path / "config",
                execution_options=None,
                runtime_label="black-box",
                log_module="TEST",
                platform_provider=None,
            )
            try:
                prepared.close()
            except RuntimeError as exc:
                close_error = exc
            else:
                raise AssertionError("expected prepared.close() runtime failure")
        except Exception as exc:
            primary_exception = exc
            raise
        finally:
            cleanup_errors: list[Exception] = []
            try:
                cleanup_errors = _cleanup_production_startup_resources(
                    prepared=prepared,
                    monkeypatch=monkeypatch,
                    cluster=platform_cluster,
                    database=database,
                    login=app_login,
                )
                if close_error is not None:
                    _report_cleanup_errors(
                        primary_exception=close_error,
                        cleanup_errors=cleanup_errors,
                        context="close failure path cleanup",
                    )
                    if cleanup_errors:
                        raise ExceptionGroup("close failure path cleanup must not fail", cleanup_errors)
                    if close_calls != 2:
                        raise AssertionError("close should be retried once after simulated failure")
                else:
                    _report_cleanup_errors(
                        primary_exception=primary_exception,
                        cleanup_errors=cleanup_errors,
                        context="production startup close-failure cleanup failed",
                    )
            finally:
                monkeypatch.setattr(sp.S3FileStore, "close", original_s3_close)
