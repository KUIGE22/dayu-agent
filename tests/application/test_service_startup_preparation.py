"""Service 启动准备公共 API 测试。

本文件覆盖 Slice 0.2 的平台设置 / 组合注入点行为：

1. 平台设置加载与组合构建是 startup admission：必须先于任何 Host /
   Fins 副作用（``HostStore`` schema 初始化、Host 构造、startup
   recovery）fail-fast；缺配置 / 缺提供者 / 提供者抛错三类场景下
   上述副作用计数必须为零；
2. 组合注入点只接收满足 ``PlatformServiceProtocol`` 的 Service 协议
   实例，非法提供者与非法注册一律 fail closed；
3. 本文件自身遵守根 ``AGENTS.md`` 约束，不使用 ``object`` / ``Any`` /
   ``cast`` / ``type: ignore`` / ``getattr`` / ``hasattr``，并由文件内
   AST guard 守护，防止新增逃逸。
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, TypeVar
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from dayu.execution.options import ExecutionOptions, ResolvedExecutionOptions
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet
from dayu.fins.storage.s3_file_store import S3FileStore
from dayu.host import Host
from dayu.host.protocols import HostAdminOperationsProtocol
from dayu.host.worker import (
    RedisWakeupRead,
    RedisWakeupReadAction,
    RedisWakeupSubscriberProtocol,
)
from dayu.investment.composition import (
    PlatformCompositionProviderProtocol,
    PlatformServiceProtocol,
)
from dayu.investment.config import (
    DAYU_PLATFORM_AUTH_KEY_ENV,
    DAYU_PLATFORM_ENABLED_ENV,
    DAYU_PLATFORM_OBJECT_STORAGE_ENV,
    DAYU_PLATFORM_POSTGRES_DSN_ENV,
    DAYU_PLATFORM_PROFILE_ENV,
    DAYU_PLATFORM_REDIS_ENV,
    PlatformDeploymentProfile,
    PlatformQueueAdmissionKind,
    PlatformQueueMode,
    PlatformQueueSettings,
    PlatformSettings,
    PlatformSettingsError,
)
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.domain.workspace_import import (
    WORKSPACE_IMPORT_MIGRATION_ID,
    WorkspaceImportDriftError,
    WorkspaceImportError,
    WorkspaceImportReceipt,
    WorkspaceImportRequest,
    WorkspaceImportUsageError,
    build_workspace_import_request,
)
from dayu.investment.storage.db import DEFAULT_ORGANIZATION_ID
from dayu.services.investment_identity import InvestmentIdentityService
from dayu.services.scene_execution_acceptance import SceneExecutionAcceptancePreparer
from dayu.services.startup_preparation import (
    PreparedHostRuntimeDependencies,
    PreparedPlatformQueueRuntime,
    _HostRuntimePreparationRequest,
    _prepare_queue_admission,
    _PreparedQueueAdmission,
    prepare_host_runtime_dependencies,
    prepare_platform_queue_runtime_dependencies,
    prepare_workspace_import_dependencies,
)
from dayu.services.workspace_import import WorkspaceImportService
from dayu.startup.config_file_resolver import ConfigFileResolver
from dayu.startup.model_catalog import ConfigLoaderModelCatalog
from dayu.startup.platform import PlatformCompositionError, build_platform_composition
from dayu.startup.prompt_assets import FilePromptAssetStore
from dayu.startup.workspace import WorkspaceResources

_T = TypeVar("_T")

_ESCAPE_CALL_NAMES: frozenset[str] = frozenset({"cast", "getattr", "hasattr"})
_ESCAPE_NAME_IDS: frozenset[str] = frozenset({"Any", "object"})


def _bare(cls: type[_T]) -> _T:
    """创建不调用构造器的类实例，用于只做身份断言的测试桩。

    Args:
        cls: 目标类型。

    Returns:
        未初始化字段的该类实例；本文件只对其做身份断言，不访问字段。

    Raises:
        无。
    """

    return cls.__new__(cls)


def _enabled_production_settings() -> PlatformSettings:
    """构造一份启用的合法 production 平台设置。

    Args:
        无。

    Returns:
        携带全部四个基础设施环境变量名称的 production 启用设置。

    Raises:
        无。
    """

    return PlatformSettings(
        enabled=True,
        profile=PlatformDeploymentProfile.PRODUCTION,
        postgres_dsn_env="DAYU_PLATFORM_POSTGRES_DSN",
        object_storage_env="DAYU_PLATFORM_OBJECT_STORAGE",
        redis_env="DAYU_PLATFORM_REDIS_URL",
        auth_key_env="DAYU_PLATFORM_AUTH_KEY",
    )


@dataclass(frozen=True)
class _FakePlatformService:
    """平台组合测试用的 Service 协议实现。

    结构满足 ``PlatformServiceProtocol``（只读 ``platform_service_name``）。
    """

    platform_service_name: str


class _FakePlatformCompositionProvider:
    """平台组合测试用的提供者桩。"""

    def __init__(self, services: Mapping[str, PlatformServiceProtocol]) -> None:
        """初始化提供者桩。

        Args:
            services: 提供者对外暴露的 Service 协议映射。
        """

        self._services = services

    def provide_services(self) -> Mapping[str, PlatformServiceProtocol]:
        """返回固定的 Service 协议映射。

        Args:
            无。

        Returns:
            构造时给定的 Service 协议映射。

        Raises:
            无。
        """

        return self._services


class _FailingPlatformCompositionProvider:
    """调用即失败的提供者桩，用于验证禁用平台不触碰提供者。"""

    def provide_services(self) -> Mapping[str, PlatformServiceProtocol]:
        """断言禁用平台不应调用本方法。

        Args:
            无。

        Returns:
            永不返回，直接断言失败。

        Raises:
            AssertionError: 方法被调用时抛出。
        """

        raise AssertionError("禁用平台不应调用组合提供者")


class _RaisingPlatformCompositionProvider:
    """调用即抛错的提供者桩，用于验证 provider 异常原样传播。"""

    def provide_services(self) -> Mapping[str, PlatformServiceProtocol]:
        """抛出固定错误。

        Args:
            无。

        Returns:
            永不返回，直接抛错。

        Raises:
            RuntimeError: 恒抛出，模拟提供者装配失败。
        """

        raise RuntimeError("provider boom")


class _InvalidRegistryProvider:
    """产出违反组合契约注册的提供者桩（注册键与名称不匹配）。"""

    def provide_services(self) -> Mapping[str, PlatformServiceProtocol]:
        """返回键名不匹配的注册。

        Args:
            无。

        Returns:
            注册键 ``chat`` 与值名称 ``fins`` 不一致的映射。

        Raises:
            无。
        """

        return {"chat": _FakePlatformService(platform_service_name="fins")}


class _FakeWriterLease:
    """测试用 writer lease 桩。"""

    def __init__(self, close_order: list[str] | None = None) -> None:
        """初始化可选 close 顺序记录。

        Args:
            close_order: 可选共享 close 顺序记录。

        Returns:
            无。

        Raises:
            无。
        """

        self._close_order = close_order
        self._released = False

    def release(self) -> None:
        """幂等释放 lease。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if self._released:
            return
        self._released = True
        if self._close_order is not None:
            self._close_order.append("lease")


class _CloseSafeS3Store(S3FileStore):
    """close() 不触碰 ``_client`` 的 S3 store 测试桩。

    只覆盖 ``PreparedHostRuntimeDependencies.close()`` 的幂等 close
    语义断言；不构造真实 boto3 client。
    """

    def __init__(self, close_order: list[str] | None = None) -> None:
        """初始化 close 计数。

        Args:
            close_order: 可选共享 close 顺序记录。

        Returns:
            无。

        Raises:
            无。
        """

        self.close_calls = 0
        self._close_order = close_order
        self._closed = False

    def close(self) -> None:
        """记录一次 close。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if self._closed:
            return
        self._closed = True
        self.close_calls += 1
        if self._close_order is not None:
            self._close_order.append("s3")


class _FakeRedisSubscriber:
    """startup composition 测试用 Redis subscriber 窄桩。"""

    def resubscribe(self) -> bool:
        """返回订阅成功。

        Args:
            无。

        Returns:
            恒为 ``True``。

        Raises:
            无。
        """

        return True

    def get_message(self, *, timeout_seconds: float) -> RedisWakeupRead:
        """返回无消息结果。

        Args:
            timeout_seconds: bounded timeout（本桩只验证为正）。

        Returns:
            ``NO_MESSAGE`` closed read。

        Raises:
            ValueError: timeout 非正时抛出。
        """

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须为正")
        return RedisWakeupRead(
            action=RedisWakeupReadAction.NO_MESSAGE,
            hint=None,
        )

    def close(self) -> None:
        """关闭 subscriber（本桩无资源）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """


class _FakeRedisPubSub:
    """concrete Redis adapter admission 测试用 raw PubSub 窄桩。"""

    def subscribe(self, *channels: str) -> None:
        """接受固定 channel 订阅。

        Args:
            channels: channel 名称。

        Returns:
            无。

        Raises:
            无。
        """

        del channels

    def get_message(
        self,
        *,
        ignore_subscribe_messages: bool,
        timeout: float,
    ) -> dict[str, bytes | str | int | bool | None] | None:
        """返回无消息。

        Args:
            ignore_subscribe_messages: 是否忽略订阅确认。
            timeout: bounded timeout。

        Returns:
            恒为 ``None``。

        Raises:
            无。
        """

        del ignore_subscribe_messages, timeout
        return None

    def close(self) -> None:
        """关闭 raw PubSub（无资源）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """


class _FakeQueueAdapter:
    """同时满足 publisher/factory/client 的无 Redis 测试桩。"""

    def __init__(
        self,
        close_order: list[str] | None = None,
        operation_order: list[str] | None = None,
    ) -> None:
        """初始化调用记录。

        Args:
            close_order: 可选共享 close 顺序记录。
            operation_order: 可选共享运行操作顺序记录。

        Returns:
            无。

        Raises:
            无。
        """

        self.publish_calls: list[tuple[TenantScope, UUID]] = []
        self.wire_publish_calls: list[tuple[str, bytes]] = []
        self.ping_calls = 0
        self.close_calls = 0
        self._closed = False
        self._close_order = close_order
        self._operation_order = operation_order

    def ping(self) -> bool:
        """记录并返回健康。

        Args:
            无。

        Returns:
            未关闭时为 ``True``。

        Raises:
            无。
        """

        self.ping_calls += 1
        if self._operation_order is not None:
            self._operation_order.append("redis")
        return not self._closed

    def publish_hint(self, scope: TenantScope, job_id: UUID) -> bool:
        """记录 best-effort hint。

        Args:
            scope: tenant scope。
            job_id: job UUID。

        Returns:
            未关闭时为 ``True``。

        Raises:
            无。
        """

        self.publish_calls.append((scope, job_id))
        return not self._closed

    def create_subscriber(self, scope: TenantScope) -> RedisWakeupSubscriberProtocol:
        """创建 subscriber 桩。

        Args:
            scope: tenant scope（本桩不使用）。

        Returns:
            新 subscriber 桩。

        Raises:
            无。
        """

        del scope
        return _FakeRedisSubscriber()

    def publish(self, channel: str, message: bytes) -> int:
        """记录 raw redis-py publish。

        Args:
            channel: Redis channel。
            message: canonical bytes。

        Returns:
            固定 subscriber 数量 1。

        Raises:
            无。
        """

        self.wire_publish_calls.append((channel, message))
        return 1

    def pubsub(self, *, ignore_subscribe_messages: bool) -> _FakeRedisPubSub:
        """创建 raw PubSub 桩。

        Args:
            ignore_subscribe_messages: 是否忽略订阅确认。

        Returns:
            新 raw PubSub 桩。

        Raises:
            无。
        """

        del ignore_subscribe_messages
        return _FakeRedisPubSub()

    def close(self) -> None:
        """幂等记录 client close。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if self._closed:
            return
        self._closed = True
        self.close_calls += 1
        if self._close_order is not None:
            self._close_order.append("redis")


def _fake_redis_admission(
    adapter: _FakeQueueAdapter | None = None,
) -> _PreparedQueueAdmission:
    """构造不连接 Redis 的合法 production admission。

    Args:
        adapter: 可选共享 adapter 桩。

    Returns:
        typed REDIS admission。

    Raises:
        无。
    """

    resolved_adapter = adapter if adapter is not None else _FakeQueueAdapter()
    return _PreparedQueueAdmission(
        kind=PlatformQueueAdmissionKind.REDIS,
        queue_settings=PlatformQueueSettings(mode=PlatformQueueMode.EVENT_ASSISTED),
        publisher=resolved_adapter,
        subscriber_factory=resolved_adapter,
        redis_client=resolved_adapter,
    )


class _SideEffectSentinels:
    """Host / Fins 装配副作用调用记录器。"""

    def __init__(self) -> None:
        """初始化副作用记录器。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.initialize_schema_calls: list[str] = []
        self.host_construct_calls: list[str] = []
        self.recovery_calls: list[tuple[HostAdminOperationsProtocol, str, str]] = []
        self.bare_host = Host.__new__(Host)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """把 Host / Fins 副作用调用替换为记录器。

        Args:
            monkeypatch: pytest 打桩器。

        Returns:
            无。

        Raises:
            无。
        """

        monkeypatch.setattr(
            "dayu.services.startup_preparation.HostStore.initialize_schema",
            lambda _self: self.initialize_schema_calls.append("initialize_schema"),
        )
        monkeypatch.setattr(
            "dayu.services.startup_preparation.Host",
            lambda **_kwargs: self._record_host_construct(),
        )
        monkeypatch.setattr(
            "dayu.services.startup_preparation.recover_host_startup_state",
            lambda host_admin_service, *, runtime_label, log_module: self.recovery_calls.append(
                (host_admin_service.host, runtime_label, log_module)
            ),
        )

    def _record_host_construct(self) -> Host:
        """记录 Host 构造副作用并返回测试桩实例。

        Args:
            无。

        Returns:
            用于身份断言的未初始化 Host 实例。

        Raises:
            无。
        """

        self.host_construct_calls.append("host")
        return self.bare_host

    def all_empty(self) -> bool:
        """三类副作用调用是否均为零。

        Args:
            无。

        Returns:
            schema 初始化 / Host 构造 / recovery 均未被调用时返回 True。

        Raises:
            无。
        """

        return not (
            self.initialize_schema_calls
            or self.host_construct_calls
            or self.recovery_calls
        )


def _patch_host_runtime_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    platform_settings: PlatformSettings,
) -> tuple[
    WorkspaceResources,
    ResolvedExecutionOptions,
    SceneExecutionAcceptancePreparer,
    DefaultFinsRuntime,
    Host,
    _SideEffectSentinels,
]:
    """对共享 Host 装配函数施加全部测试桩并返回关键假对象与副作用记录器。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时工作区目录。
        platform_settings: 注入到平台设置加载函数的固定设置。

    Returns:
        ``(fake_workspace, fake_default_execution_options, fake_scene_preparer,
        fake_fins_runtime, fake_host, sentinels)`` 六元组；前五个是只做
        身份断言的测试桩，最后一个是副作用调用记录器。

    Raises:
        无。
    """

    fake_paths = SimpleNamespace(
        workspace_root=tmp_path,
        config_root=tmp_path / "config",
        output_dir=tmp_path / "output",
    )
    fake_workspace = _bare(WorkspaceResources)
    fake_model_catalog = _bare(ConfigLoaderModelCatalog)
    fake_default_execution_options = _bare(ResolvedExecutionOptions)
    fake_scene_preparer = _bare(SceneExecutionAcceptancePreparer)
    fake_fins_runtime = _bare(DefaultFinsRuntime)
    sentinels = _SideEffectSentinels()
    sentinels.install(monkeypatch)

    monkeypatch.setattr(
        "dayu.services.startup_preparation._build_s3_store_from_settings",
        lambda *_args, **_kwargs: _CloseSafeS3Store(),
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.acquire_writer_lease",
        lambda _workspace_root: _FakeWriterLease(),
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.build_fs_repository_set",
        lambda **_kwargs: _bare(_FsRepositorySet),
    )

    monkeypatch.setattr(
        "dayu.services.startup_preparation.resolve_startup_paths",
        lambda **_kwargs: fake_paths,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.ConfigFileResolver",
        lambda _config_root: _bare(ConfigFileResolver),
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.ConfigLoader",
        lambda _resolver: SimpleNamespace(load_run_config=lambda: SimpleNamespace()),
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.FilePromptAssetStore",
        lambda _resolver: _bare(FilePromptAssetStore),
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.WorkspaceResources",
        lambda **_kwargs: fake_workspace,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.ConfigLoaderModelCatalog",
        lambda _config_loader: fake_model_catalog,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.build_base_execution_options",
        lambda **_kwargs: _bare(ResolvedExecutionOptions),
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.merge_execution_options",
        lambda **_kwargs: fake_default_execution_options,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.prepare_scene_execution_acceptance_preparer",
        lambda **_kwargs: fake_scene_preparer,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.DefaultFinsRuntime.create",
        lambda **_kwargs: fake_fins_runtime,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.resolve_host_config",
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
        "dayu.services.startup_preparation.load_platform_settings",
        lambda _env: platform_settings,
    )
    if (
        platform_settings.enabled
        and platform_settings.profile is PlatformDeploymentProfile.PRODUCTION
    ):
        fake_queue_adapter = _FakeQueueAdapter()

        def _fake_prepare_queue_admission(
            settings: PlatformSettings,
            queue_settings: PlatformQueueSettings | None,
        ) -> _PreparedQueueAdmission:
            """返回合法 REDIS admission，避免基线测试连接 Redis。

            Args:
                settings: public wrapper 读取的同一 settings。
                queue_settings: production strict queue settings。

            Returns:
                使用调用方 settings identity 的 typed admission。

            Raises:
                AssertionError: profile/settings identity 非预期时抛出。
            """

            assert settings is platform_settings
            assert queue_settings is not None
            assert queue_settings.mode is PlatformQueueMode.EVENT_ASSISTED
            return _PreparedQueueAdmission(
                kind=PlatformQueueAdmissionKind.REDIS,
                queue_settings=queue_settings,
                publisher=fake_queue_adapter,
                subscriber_factory=fake_queue_adapter,
                redis_client=fake_queue_adapter,
            )

        monkeypatch.setattr(
            "dayu.services.startup_preparation._prepare_queue_admission",
            _fake_prepare_queue_admission,
        )
    return (
        fake_workspace,
        fake_default_execution_options,
        fake_scene_preparer,
        fake_fins_runtime,
        sentinels.bare_host,
        sentinels,
    )


def _call_prepare_host_runtime(
    tmp_path: Path,
    *,
    platform_provider: PlatformCompositionProviderProtocol | None = None,
) -> PreparedHostRuntimeDependencies:
    """以统一参数调用共享 Host 装配函数。

    Args:
        tmp_path: 临时工作区目录。
        platform_provider: 传递给装配函数的平台组合提供者。

    Returns:
        装配函数返回的依赖集合。

    Raises:
        由装配函数传播的异常。
    """

    return prepare_host_runtime_dependencies(
        workspace_root=tmp_path,
        config_root=tmp_path / "config",
        execution_options=ExecutionOptions(),
        runtime_label="Shared Host runtime",
        log_module="APP.TEST",
        platform_provider=platform_provider,
    )


@pytest.mark.unit
def test_prepare_host_runtime_dependencies_runs_unified_startup_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """共享 Host 启动准备应在装配完成后执行统一 startup recovery。"""

    (
        fake_workspace,
        fake_default_execution_options,
        fake_scene_preparer,
        fake_fins_runtime,
        fake_host,
        sentinels,
    ) = _patch_host_runtime_dependencies(
        monkeypatch,
        tmp_path,
        platform_settings=PlatformSettings(
            enabled=False,
            profile=PlatformDeploymentProfile.DEVELOPMENT,
        ),
    )

    prepared = _call_prepare_host_runtime(tmp_path)

    assert prepared.workspace is fake_workspace
    assert prepared.default_execution_options is fake_default_execution_options
    assert prepared.scene_execution_acceptance_preparer is fake_scene_preparer
    assert prepared.host is fake_host
    assert prepared.fins_runtime is fake_fins_runtime
    assert sentinels.recovery_calls == [(fake_host, "Shared Host runtime", "APP.TEST")]


@pytest.mark.unit
def test_prepare_host_runtime_dependencies_loads_run_config_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """共享 Host 启动准备应复用同一次加载得到的 run_config。"""

    fake_paths = SimpleNamespace(
        workspace_root=tmp_path,
        config_root=tmp_path / "config",
        output_dir=tmp_path / "output",
    )
    fake_workspace = _bare(WorkspaceResources)
    fake_model_catalog = _bare(ConfigLoaderModelCatalog)
    fake_default_execution_options = _bare(ResolvedExecutionOptions)
    fake_scene_preparer = _bare(SceneExecutionAcceptancePreparer)
    fake_fins_runtime = _bare(DefaultFinsRuntime)
    fake_host = _bare(Host)
    fake_run_config = SimpleNamespace(name="shared-run-config")
    load_run_config_calls: list[SimpleNamespace] = []
    build_base_run_configs: list[SimpleNamespace] = []
    resolve_host_run_configs: list[SimpleNamespace] = []

    monkeypatch.setattr(
        "dayu.services.startup_preparation.resolve_startup_paths",
        lambda **_kwargs: fake_paths,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.ConfigFileResolver",
        lambda _config_root: _bare(ConfigFileResolver),
    )

    class _FakeConfigLoader:
        """记录 `load_run_config()` 调用次数的测试桩。"""

        def load_run_config(self) -> SimpleNamespace:
            """返回共享的测试 run_config。"""

            load_run_config_calls.append(fake_run_config)
            return fake_run_config

    monkeypatch.setattr(
        "dayu.services.startup_preparation.ConfigLoader",
        lambda _resolver: _FakeConfigLoader(),
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.FilePromptAssetStore",
        lambda _resolver: _bare(FilePromptAssetStore),
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.WorkspaceResources",
        lambda **_kwargs: fake_workspace,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.ConfigLoaderModelCatalog",
        lambda _config_loader: fake_model_catalog,
    )

    def _record_build_base(*, workspace_dir: Path, run_config: SimpleNamespace) -> ResolvedExecutionOptions:
        """记录 run_config 并返回默认执行选项桩。

        Args:
            workspace_dir: 工作区目录（本桩不使用）。
            run_config: 本次传入的 run_config。

        Returns:
            未初始化的默认执行选项桩。

        Raises:
            无。
        """

        del workspace_dir
        build_base_run_configs.append(run_config)
        return _bare(ResolvedExecutionOptions)

    monkeypatch.setattr(
        "dayu.services.startup_preparation.build_base_execution_options",
        _record_build_base,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.merge_execution_options",
        lambda **_kwargs: fake_default_execution_options,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.prepare_scene_execution_acceptance_preparer",
        lambda **_kwargs: fake_scene_preparer,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.DefaultFinsRuntime.create",
        lambda **_kwargs: fake_fins_runtime,
    )

    def _record_resolve_host(
        *,
        workspace_root: Path,
        run_config: SimpleNamespace,
        service_lane_defaults: dict[str, int] | None = None,
        explicit_lane_config: dict[str, int] | None = None,
    ) -> SimpleNamespace:
        """记录 run_config 并返回宿主配置桩。

        Args:
            workspace_root: 工作区根目录（本桩不使用）。
            run_config: 本次传入的 run_config。
            service_lane_defaults: Service 业务 lane 默认配置（本桩不使用）。
            explicit_lane_config: lane 覆盖配置（本桩不使用）。

        Returns:
            携带启动期所需字段的宿主配置桩。

        Raises:
            无。
        """

        del workspace_root, service_lane_defaults, explicit_lane_config
        resolve_host_run_configs.append(run_config)
        return SimpleNamespace(
            store_path=tmp_path / "host.sqlite3",
            lane_config={"llm_api": 1},
            pending_turn_resume_max_attempts=3,
            pending_turn_retention_hours=168,
            cancellation_bridge_poll_interval_seconds=0.5,
            cancellation_bridge_failure_grace_period_seconds=5.0,
        )

    monkeypatch.setattr(
        "dayu.services.startup_preparation.resolve_host_config",
        _record_resolve_host,
    )
    monkeypatch.setattr("dayu.services.startup_preparation.Host", lambda **_kwargs: fake_host)
    monkeypatch.setattr(
        "dayu.services.startup_preparation.recover_host_startup_state",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.load_platform_settings",
        lambda _env: PlatformSettings(
            enabled=False,
            profile=PlatformDeploymentProfile.DEVELOPMENT,
        ),
    )

    prepared = _call_prepare_host_runtime(tmp_path)

    assert prepared.host is fake_host
    assert len(load_run_config_calls) == 1
    assert build_base_run_configs == [fake_run_config]
    assert resolve_host_run_configs == [fake_run_config]


class TestBuildPlatformComposition:
    """平台组合注入点行为。"""

    @pytest.mark.unit
    def test_disabled_settings_yield_disabled_composition(self) -> None:
        """禁用设置得到禁用组合根，且不触碰提供者。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = PlatformSettings(
            enabled=False,
            profile=PlatformDeploymentProfile.DEVELOPMENT,
        )
        composition = build_platform_composition(
            settings=settings,
            provider=_FailingPlatformCompositionProvider(),
        )
        assert composition.enabled is False
        assert composition.services == {}

    @pytest.mark.unit
    def test_enabled_without_provider_fails_fast(self) -> None:
        """平台启用但未注入提供者时 fail-fast。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformCompositionError):
            build_platform_composition(settings=_enabled_production_settings())

    @pytest.mark.unit
    def test_enabled_with_provider_exposes_service_protocols(self) -> None:
        """平台启用且注入提供者时暴露提供者产出的 Service 协议。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        provider = _FakePlatformCompositionProvider(
            {"platform": _FakePlatformService(platform_service_name="platform")}
        )
        composition = build_platform_composition(
            settings=_enabled_production_settings(),
            provider=provider,
        )
        assert composition.enabled is True
        assert list(composition.services) == ["platform"]
        assert isinstance(composition.services["platform"], _FakePlatformService)

    @pytest.mark.unit
    def test_provider_invalid_registry_raises_composition_error(self) -> None:
        """提供者产出的注册违反组合契约时转换为稳定错误且不回显候选值。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformCompositionError) as excinfo:
            build_platform_composition(
                settings=_enabled_production_settings(),
                provider=_InvalidRegistryProvider(),
            )
        assert "chat" not in str(excinfo.value)

    @pytest.mark.unit
    def test_provider_error_propagates_original_exception(self) -> None:
        """提供者自身抛出的异常原样传播，不被包装。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(RuntimeError, match="provider boom"):
            build_platform_composition(
                settings=_enabled_production_settings(),
                provider=_RaisingPlatformCompositionProvider(),
            )


class TestPlatformAdmissionBeforeHostSideEffects:
    """平台 admission 必须早于任何 Host / Fins 副作用。"""

    @pytest.mark.unit
    def test_production_queue_missing_redis_package_config_or_ping_fails_before_pg_host_workspace_side_effect(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Redis 配置缺失时在 path/PG/Host/workspace 前 fail-fast。

        Args:
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        sentinels = _SideEffectSentinels()
        sentinels.install(monkeypatch)
        monkeypatch.setenv(DAYU_PLATFORM_ENABLED_ENV, "1")
        monkeypatch.setenv(DAYU_PLATFORM_PROFILE_ENV, "production")
        monkeypatch.setenv(DAYU_PLATFORM_POSTGRES_DSN_ENV, "postgresql://test")
        monkeypatch.setenv(DAYU_PLATFORM_OBJECT_STORAGE_ENV, "object-storage")
        monkeypatch.setenv(DAYU_PLATFORM_AUTH_KEY_ENV, "auth-key")
        monkeypatch.delenv(DAYU_PLATFORM_REDIS_ENV, raising=False)

        with pytest.raises(PlatformSettingsError):
            _call_prepare_host_runtime(tmp_path)
        assert sentinels.all_empty()

    @pytest.mark.unit
    def test_missing_provider_fails_before_host_side_effects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """production 缺 provider 且 DSN env 缺失时，Host / Fins 副作用为零。

        S12-CTRL-06：production 未显式注入 provider 时自动读取 DSN env
        构造默认 provider；DSN env 缺失由 ``PlatformSettingsError`` 在
        engine 创建前拒绝。

        Args:
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        (_, _, _, _, _, sentinels) = _patch_host_runtime_dependencies(
            monkeypatch,
            tmp_path,
            platform_settings=_enabled_production_settings(),
        )
        with pytest.raises(PlatformSettingsError):
            _call_prepare_host_runtime(tmp_path)
        assert sentinels.all_empty()

    @pytest.mark.unit
    def test_production_explicit_provider_cannot_bypass_redis_admission(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """组合提供者抛错时，原异常传播且 Host / Fins 副作用计数为零。

        Args:
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        (_, _, _, _, _, sentinels) = _patch_host_runtime_dependencies(
            monkeypatch,
            tmp_path,
            platform_settings=_enabled_production_settings(),
        )
        admission_calls: list[PlatformQueueSettings] = []

        def _record_admission(
            _settings: PlatformSettings,
            queue_settings: PlatformQueueSettings | None,
        ) -> _PreparedQueueAdmission:
            """记录显式 provider 前的 Redis admission。

            Args:
                _settings: production settings。
                queue_settings: strict queue settings。

            Returns:
                typed REDIS admission。

            Raises:
                AssertionError: queue settings 缺失时抛出。
            """

            assert queue_settings is not None
            admission_calls.append(queue_settings)
            adapter = _FakeQueueAdapter()
            return _PreparedQueueAdmission(
                kind=PlatformQueueAdmissionKind.REDIS,
                queue_settings=queue_settings,
                publisher=adapter,
                subscriber_factory=adapter,
                redis_client=adapter,
            )

        monkeypatch.setattr(
            "dayu.services.startup_preparation._prepare_queue_admission",
            _record_admission,
        )
        with pytest.raises(RuntimeError, match="provider boom"):
            _call_prepare_host_runtime(
                tmp_path,
                platform_provider=_RaisingPlatformCompositionProvider(),
            )
        assert len(admission_calls) == 1
        assert sentinels.all_empty()


class TestPrepareHostRuntimePlatformComposition:
    """共享 Host 装配中的平台组合注入。"""

    @pytest.mark.unit
    def test_platform_composition_disabled_by_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """未配置平台开关时装配出禁用组合根，现有行为不变。

        Args:
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        (_, _, _, _, _, sentinels) = _patch_host_runtime_dependencies(
            monkeypatch,
            tmp_path,
            platform_settings=PlatformSettings(
                enabled=False,
                profile=PlatformDeploymentProfile.DEVELOPMENT,
            ),
        )
        prepared = _call_prepare_host_runtime(tmp_path)
        assert prepared.platform_composition.enabled is False
        assert prepared.platform_composition.services == {}
        assert len(sentinels.initialize_schema_calls) == 1
        assert len(sentinels.host_construct_calls) == 1
        assert len(sentinels.recovery_calls) == 1

    @pytest.mark.unit
    def test_platform_enabled_without_provider_fails_fast(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """development 平台启用且未注入提供者时装配期 fail-fast。

        S12-CTRL-06：development 缺显式 provider 继续 fail-fast，
        禁止用 PostgreSQL 冒充 in-memory。

        Args:
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        (_, _, _, _, _, sentinels) = _patch_host_runtime_dependencies(
            monkeypatch,
            tmp_path,
            platform_settings=PlatformSettings(
                enabled=True,
                profile=PlatformDeploymentProfile.DEVELOPMENT,
                use_in_memory_adapters=True,
            ),
        )
        with pytest.raises(PlatformCompositionError):
            _call_prepare_host_runtime(tmp_path)
        assert sentinels.all_empty()

    @pytest.mark.unit
    def test_production_explicit_provider_keeps_custom_composition_after_redis_admission(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """平台启用且注入提供者时组合根暴露提供者产出的 Service。

        Args:
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        provider = _FakePlatformCompositionProvider(
            {"platform": _FakePlatformService(platform_service_name="platform")}
        )
        (_, _, _, _, _, sentinels) = _patch_host_runtime_dependencies(
            monkeypatch,
            tmp_path,
            platform_settings=_enabled_production_settings(),
        )
        prepared = _call_prepare_host_runtime(tmp_path, platform_provider=provider)
        assert prepared.platform_composition.enabled is True
        assert list(prepared.platform_composition.services) == ["platform"]
        assert isinstance(prepared.platform_composition.services["platform"], _FakePlatformService)
        assert prepared._queue_admission.kind is PlatformQueueAdmissionKind.REDIS
        assert prepared.job_service is None
        assert prepared.schedule_service is None
        assert len(sentinels.initialize_schema_calls) == 1
        assert len(sentinels.host_construct_calls) == 1
        assert len(sentinels.recovery_calls) == 1


class TestProductionProviderAdmissionProbe:
    """production 默认 provider 返回前的连接与角色 admission probe。"""

    @pytest.mark.unit
    def test_unreachable_dsn_fails_safely(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """不可达 DSN 在返回前被拒绝，Host / Fins 副作用为零且 engine dispose。

        Args:
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        from sqlalchemy.engine import Engine

        import dayu.services.startup_preparation as sp

        (_, _, _, _, _, sentinels) = _patch_host_runtime_dependencies(
            monkeypatch,
            tmp_path,
            platform_settings=_enabled_production_settings(),
        )
        dispose_calls: list[int] = []
        original_dispose = Engine.dispose
        registered_calls: list[str] = []
        original_atexit_register = sp.atexit.register

        def _counted_dispose(engine: Engine) -> None:
            """记录 dispose 调用并委托原实现。

            Args:
                engine: 被 dispose 的 engine。

            Returns:
                无。

            Raises:
                无。
            """

            dispose_calls.append(id(engine))
            original_dispose(engine)

        def _counted_atexit_register(func: Callable[[], None]) -> Callable[[], None]:
            """记录 atexit 注册并委托原实现。

            Args:
                func: 待注册回调。

            Returns:
                委托原实现返回的注册结果。

            Raises:
                无。
            """

            registered_calls.append(func.__name__)
            return original_atexit_register(func)

        monkeypatch.setenv(
            DAYU_PLATFORM_POSTGRES_DSN_ENV,
            "postgresql+psycopg://user:pass@127.0.0.1:1/platform",
        )
        monkeypatch.setattr(Engine, "dispose", _counted_dispose)
        monkeypatch.setattr(sp.atexit, "register", _counted_atexit_register)
        with pytest.raises(PlatformCompositionError):
            _call_prepare_host_runtime(tmp_path)
        assert sentinels.all_empty()
        assert len(dispose_calls) == 1
        assert registered_calls == []

    @pytest.mark.unit
    def test_malformed_dsn_fails_safely(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """畸形 DSN 在返回前被拒绝，Host / Fins 副作用为零。

        Args:
            monkeypatch: pytest 打桩器。
            tmp_path: 临时工作区目录。

        Returns:
            无。

        Raises:
            无。
        """

        (_, _, _, _, _, sentinels) = _patch_host_runtime_dependencies(
            monkeypatch,
            tmp_path,
            platform_settings=_enabled_production_settings(),
        )
        monkeypatch.setenv(DAYU_PLATFORM_POSTGRES_DSN_ENV, "not-a-dsn")
        with pytest.raises(PlatformCompositionError):
            _call_prepare_host_runtime(tmp_path)
        assert sentinels.all_empty()


class _CountingLifecycle:
    """记录 close 调用次数的生命周期桩。"""

    def __init__(self) -> None:
        """初始化计数。"""
        self.close_count = 0

    def close(self) -> None:
        """累加 close 计数。"""
        self.close_count += 1


class TestOwnedLifecycleRegistration:
    """_OwnedLifecycleRegistration 的 atexit callback 语义。"""

    @pytest.mark.unit
    def test_manual_close_then_callback_is_noop(self) -> None:
        """手动 close 后 atexit callback 不再调用 lifecycle.close。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        from dayu.services.startup_preparation import _OwnedLifecycleRegistration

        lifecycle = _CountingLifecycle()
        registration = _OwnedLifecycleRegistration(lifecycle)
        registration.register()
        registration.close()
        registration.close()
        assert lifecycle.close_count == 1
        registration._close_at_exit()
        assert lifecycle.close_count == 1

    @pytest.mark.unit
    def test_callback_without_manual_close_calls_once(self) -> None:
        """未手动 close 时 atexit callback 调用一次 lifecycle.close。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        from dayu.services.startup_preparation import _OwnedLifecycleRegistration

        lifecycle = _CountingLifecycle()
        registration = _OwnedLifecycleRegistration(lifecycle)
        registration.register()
        registration._close_at_exit()
        assert lifecycle.close_count == 1
        registration._close_at_exit()
        assert lifecycle.close_count == 1

    @pytest.mark.unit
    def test_prepared_close_then_callback_is_noop(self) -> None:
        """Prepared.close() 委托 registration 后 callback 不再调用 lifecycle。

        TERRA-004：public ``PreparedHostRuntimeDependencies.close()``
        必须与 ``_OwnedLifecycleRegistration`` 协调——manual close 先
        赢得 close 权并解除 atexit 意图，进程退出回调为 no-op。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        from dayu.services.startup_preparation import (
            PreparedHostRuntimeDependencies,
            _OwnedLifecycleRegistration,
        )

        lifecycle = _CountingLifecycle()
        registration = _OwnedLifecycleRegistration(lifecycle)
        prepared = PreparedHostRuntimeDependencies(
            workspace=_bare(WorkspaceResources),
            default_execution_options=_bare(ResolvedExecutionOptions),
            scene_execution_acceptance_preparer=_bare(SceneExecutionAcceptancePreparer),
            host=_bare(Host),
            fins_runtime=_bare(DefaultFinsRuntime),
            _owned_platform_lifecycle=registration,
        )
        registration.register()
        prepared.close()
        prepared.close()
        assert lifecycle.close_count == 1
        registration._close_at_exit()
        assert lifecycle.close_count == 1

    @pytest.mark.unit
    def test_register_before_callback_is_noop(self) -> None:
        """register() 前 callback 不触发任何 close。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        from dayu.services.startup_preparation import _OwnedLifecycleRegistration

        lifecycle = _CountingLifecycle()
        registration = _OwnedLifecycleRegistration(lifecycle)
        registration._close_at_exit()
        assert lifecycle.close_count == 0

    @pytest.mark.unit
    def test_register_is_exact_once(self) -> None:
        """register() 重复调用只注册一次回调。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        from dayu.services.startup_preparation import _OwnedLifecycleRegistration

        lifecycle = _CountingLifecycle()
        registration = _OwnedLifecycleRegistration(lifecycle)
        registration.register()
        registration.register()
        registration._close_at_exit()
        assert lifecycle.close_count == 1
        registration._close_at_exit()
        assert lifecycle.close_count == 1

    @pytest.mark.unit
    def test_register_after_close_is_noop(self) -> None:
        """已手动 close 后 register() 不再挂回调。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        from dayu.services.startup_preparation import _OwnedLifecycleRegistration

        lifecycle = _CountingLifecycle()
        registration = _OwnedLifecycleRegistration(lifecycle)
        registration.close()
        registration.register()
        registration._close_at_exit()
        assert lifecycle.close_count == 1


@pytest.mark.unit
def test_startup_preparation_test_avoids_escape_patterns() -> None:
    """本文件不得出现 Any/object/cast/type-ignore/getattr/hasattr 逃逸。

    与 ``tests/investment/test_architecture_boundaries.py`` 的逃逸守护
    一致，保证新增的 startup 测试路径始终用强类型 fake / 协议表达
    依赖。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    ignore_marker = "# type" + ": ignore"
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _ESCAPE_NAME_IDS:
            hits.append(f"禁止使用 {node.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ESCAPE_CALL_NAMES:
            hits.append(f"禁止调用 {node.func.id}()")
    for line_number, line in enumerate(source.splitlines(), start=1):
        if ignore_marker in line:
            hits.append(f"第 {line_number} 行禁止 type: ignore")
    assert hits == []


class _RecordingEngine(Engine):
    """测试用 engine 桩：记录 dispose 调用（结构满足 ``Engine``）。"""

    def __init__(self) -> None:
        """初始化桩（不调用父类构造器）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.disposed = False

    def dispose(self, close: bool = True) -> None:
        """记录 dispose 调用。

        Args:
            close: 是否同时关闭连接（本桩不使用）。

        Returns:
            无。

        Raises:
            无。
        """

        del close
        self.disposed = True


class _RecordingWorkspaceImportService:
    """测试用 workspace import Service 桩（记录 close）。"""

    def __init__(self, engine: _RecordingEngine) -> None:
        """初始化桩。

        Args:
            engine: 关联 engine 桩。

        Returns:
            无。

        Raises:
            无。
        """

        self.engine = engine
        self.closed = False

    @property
    def platform_service_name(self) -> str:
        """返回稳定注册名。

        Args:
            无。

        Returns:
            ``workspace_import``。

        Raises:
            无。
        """

        return "workspace_import"

    def import_workspace(
        self,
        scope: TenantScope,
        request: WorkspaceImportRequest,
    ) -> WorkspaceImportReceipt:
        """占位实现（本文件不调用）。

        Args:
            scope: 租户范围。
            request: import 请求。

        Returns:
            恒不返回（本文件不调用本方法）。

        Raises:
            AssertionError: 恒抛，说明测试误用了本占位方法。
        """

        del scope, request
        raise AssertionError("import_workspace 不应在本测试中被调用")

    def close(self) -> None:
        """记录 close 并释放 engine。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.closed = True
        self.engine.dispose()


def _patch_workspace_import_build(monkeypatch: pytest.MonkeyPatch) -> _RecordingEngine:
    """打桩 workspace import 依赖构造链并返回 engine 桩。

    Args:
        monkeypatch: pytest 属性替换夹具。

    Returns:
        recording engine 桩。

    Raises:
        无。
    """

    engine = _RecordingEngine()

    def _fake_read_dsn(settings: PlatformSettings) -> str:
        del settings
        return "postgresql+psycopg://u:p@127.0.0.1:1/db"

    def _fake_create_engine(dsn: str) -> _RecordingEngine:
        del dsn
        return engine

    def _fake_probe(probe_engine: _RecordingEngine) -> None:
        del probe_engine

    def _fake_session_factory(probe_engine: _RecordingEngine) -> str:
        del probe_engine
        return "session-factory"

    def _fake_repository(session_factory: str) -> str:
        del session_factory
        return "repository"

    def _fake_service(import_repository: str, owned_engine: _RecordingEngine) -> _RecordingWorkspaceImportService:
        del import_repository
        return _RecordingWorkspaceImportService(owned_engine)

    monkeypatch.setattr("dayu.services.startup_preparation._read_postgres_dsn", _fake_read_dsn)
    monkeypatch.setattr("dayu.services.startup_preparation.create_platform_engine", _fake_create_engine)
    monkeypatch.setattr("dayu.services.startup_preparation._probe_production_engine", _fake_probe)
    monkeypatch.setattr("dayu.services.startup_preparation.create_platform_session_factory", _fake_session_factory)
    monkeypatch.setattr("dayu.services.startup_preparation.PostgresWorkspaceImportRepository", _fake_repository)
    monkeypatch.setattr("dayu.services.startup_preparation.WorkspaceImportService", _fake_service)
    return engine


class TestPrepareWorkspaceImportDependencies:
    """one-shot workspace import 依赖装配。"""

    @pytest.mark.unit
    def test_requires_enabled_production_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """平台未启用或非 production 时抛 repository_failure。"""

        from dayu.investment.domain.workspace_import import WorkspaceImportRepositoryFailureError

        disabled_settings = PlatformSettings(
            enabled=False,
            profile=PlatformDeploymentProfile.PRODUCTION,
        )
        monkeypatch.setattr(
            "dayu.services.startup_preparation.load_platform_settings",
            lambda env: disabled_settings,
        )
        with pytest.raises(WorkspaceImportRepositoryFailureError):
            prepare_workspace_import_dependencies()

    @pytest.mark.unit
    def test_constructs_service_and_close_disposes_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """构造成功后 service close 幂等释放 engine。"""

        monkeypatch.setattr(
            "dayu.services.startup_preparation.load_platform_settings",
            lambda env: _enabled_production_settings(),
        )
        engine = _patch_workspace_import_build(monkeypatch)
        dependencies = prepare_workspace_import_dependencies()
        assert dependencies.service.platform_service_name == "workspace_import"
        dependencies.close()
        dependencies.close()
        assert engine.disposed

    @pytest.mark.unit
    def test_disposes_engine_on_probe_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """probe 失败时 dispose engine 并映射 repository_failure。"""

        from dayu.investment.domain.workspace_import import WorkspaceImportRepositoryFailureError

        monkeypatch.setattr(
            "dayu.services.startup_preparation.load_platform_settings",
            lambda env: _enabled_production_settings(),
        )
        engine = _patch_workspace_import_build(monkeypatch)

        def _failing_probe(probe_engine: _RecordingEngine) -> None:
            del probe_engine
            raise RuntimeError("admission failed")

        monkeypatch.setattr("dayu.services.startup_preparation._probe_production_engine", _failing_probe)
        with pytest.raises(WorkspaceImportRepositoryFailureError):
            prepare_workspace_import_dependencies()
        assert engine.disposed


class _FakeImportRepository:
    """测试用 workspace import repository 桩（强类型）。"""

    def __init__(self) -> None:
        """初始化桩。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.calls: list[tuple[TenantScope, WorkspaceImportRequest]] = []
        self.receipt: WorkspaceImportReceipt | None = None
        self.error: WorkspaceImportError | None = None

    def publish_import(
        self,
        scope: TenantScope,
        request: WorkspaceImportRequest,
    ) -> WorkspaceImportReceipt:
        """记录调用并返回配置的 receipt 或抛出配置的错误。

        Args:
            scope: 租户范围。
            request: import 请求。

        Returns:
            配置的 receipt。

        Raises:
            WorkspaceImportError: 配置了 error 时抛出。
            AssertionError: 未配置 receipt 时抛出。
        """

        self.calls.append((scope, request))
        if self.error is not None:
            raise self.error
        if self.receipt is None:
            raise AssertionError("fake repository 未配置 receipt")
        return self.receipt


def _sample_import_request() -> WorkspaceImportRequest:
    """构造空 import 请求（service 测试用）。

    Args:
        无。

    Returns:
        空 import 请求。

    Raises:
        无。
    """

    return build_workspace_import_request(
        migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
        companies=(),
        source_definitions=(),
        locators=(),
        company_projections=(),
        source_root_presence=(),
        bundle_closures=(),
    )


def _default_workspace_import_scope() -> TenantScope:
    """构造 default bootstrap scope。

    Args:
        无。

    Returns:
        default tenant scope。

    Raises:
        无。
    """

    return Principal(TenantId(DEFAULT_ORGANIZATION_ID), "workspace-import-bootstrap").to_scope()


class TestWorkspaceImportService:
    """真实 workspace import Service 契约。"""

    @pytest.mark.unit
    def test_cross_tenant_rejected_before_repository_call(self) -> None:
        """非 default tenant 在 repository 调用前拒绝。"""

        repository = _FakeImportRepository()
        service = WorkspaceImportService(import_repository=repository)
        cross_scope = Principal(
            TenantId("00000000-0000-0000-0000-000000000002"),
            "workspace-import-bootstrap",
        ).to_scope()
        with pytest.raises(WorkspaceImportUsageError):
            service.import_workspace(cross_scope, _sample_import_request())
        assert repository.calls == []

    @pytest.mark.unit
    def test_default_tenant_delegates_and_passes_receipt(self) -> None:
        """default tenant 透传 repository 的 receipt。"""

        repository = _FakeImportRepository()
        receipt = WorkspaceImportReceipt(
            marker_id="55555555-5555-4555-8555-555555555555",
            migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
            status="committed",
            company_count=0,
            security_count=0,
            source_definition_count=0,
            bundle_count=0,
            source_root_fingerprint="a" * 64,
            staged_payload_sha256="b" * 64,
        )
        repository.receipt = receipt
        service = WorkspaceImportService(import_repository=repository)
        request = _sample_import_request()
        result = service.import_workspace(_default_workspace_import_scope(), request)
        assert result is receipt
        assert len(repository.calls) == 1

    @pytest.mark.unit
    def test_repository_error_propagates_unchanged(self) -> None:
        """repository 稳定错误原样透传。"""

        repository = _FakeImportRepository()
        repository.error = WorkspaceImportDriftError()
        service = WorkspaceImportService(import_repository=repository)
        with pytest.raises(WorkspaceImportDriftError):
            service.import_workspace(_default_workspace_import_scope(), _sample_import_request())

    @pytest.mark.unit
    def test_close_disposes_owned_engine_once(self) -> None:
        """close 幂等释放自持 engine（只 dispose 一次）。"""

        engine = _RecordingEngine()
        repository = _FakeImportRepository()
        service = WorkspaceImportService(import_repository=repository, owned_engine=engine)
        service.close()
        service.close()
        assert engine.disposed

    @pytest.mark.unit
    def test_close_without_owned_engine_is_noop(self) -> None:
        """无自持 engine 时 close 为 no-op。"""

        repository = _FakeImportRepository()
        service = WorkspaceImportService(import_repository=repository)
        service.close()
        service.close()

    @pytest.mark.unit
    def test_platform_service_name_is_workspace_import(self) -> None:
        """稳定注册名精确为 workspace_import。"""

        service = WorkspaceImportService(import_repository=_FakeImportRepository())
        assert service.platform_service_name == "workspace_import"


class _FakeIdentityService(InvestmentIdentityService):
    """同时满足 identity Service 与 lifecycle close 契约的测试桩。

    不调用父类构造器（零 PG 连接）；以 ``close_calls`` 记录 close 次数。
    """

    def __init__(self, close_order: list[str] | None = None) -> None:
        """初始化 close 计数。

        Args:
            close_order: 可选共享 close 顺序记录。

        Returns:
            无。

        Raises:
            无。
        """

        self.close_calls = 0
        self._close_order = close_order

    @property
    def platform_service_name(self) -> str:
        """返回稳定注册名。

        Args:
            无。

        Returns:
            精确为 ``investment_identity``。

        Raises:
            无。
        """

        return "investment_identity"

    def close(self) -> None:
        """记录一次 close。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.close_calls += 1
        if self._close_order is not None:
            self._close_order.append("pg")


class _FakeSessionFactory(sessionmaker[Session]):
    """PostgresJobStore 只保存 session factory 的哨兵类型。

    不调用父类构造器（零连接/零绑定）。
    """

    def __init__(self) -> None:
        """初始化空哨兵。"""


def _install_fake_production_preparation(
    monkeypatch: pytest.MonkeyPatch,
    identity_service: _FakeIdentityService,
    session_factory: _FakeSessionFactory,
) -> None:
    """把阶段 1 平台依赖替换为 fake preparation（零 PG 连接）。

    Args:
        monkeypatch: pytest 打桩器。
        identity_service: 测试 identity service。
        session_factory: 断言 ``PostgresJobStore`` 持有的同一
            session factory 哨兵实例。

    Returns:
        无。

    Raises:
        无。
    """

    from sqlalchemy.engine import Engine

    from dayu.investment.storage.postgres_identity import PostgresIdentityRepository
    from dayu.services.startup_preparation import _PlatformPreparation

    def _fake_prepare(_settings) -> _PlatformPreparation:
        return _PlatformPreparation(
            engine=_bare(Engine),
            session_factory=session_factory,
            identity_repository=_bare(PostgresIdentityRepository),
            identity_service=identity_service,
        )

    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_production_platform_dependencies",
        _fake_prepare,
    )


def _run_production_prepare(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    identity_service: _FakeIdentityService,
) -> tuple[PreparedHostRuntimeDependencies, _FakeSessionFactory, _SideEffectSentinels]:
    """以 production 设置与 fake 阶段 1 跑完整装配并返回结果。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时工作区目录。
        identity_service: 测试 identity service。

    Returns:
        ``(prepared, session_factory, sentinels)`` 三元组。

    Raises:
        由装配函数传播的异常。
    """

    from dayu.investment.config import PlatformSettings

    fake_workspace, _, _, _, fake_host, sentinels = _patch_host_runtime_dependencies(
        monkeypatch,
        tmp_path,
        platform_settings=PlatformSettings(
            enabled=True,
            profile=PlatformDeploymentProfile.PRODUCTION,
            postgres_dsn_env="DAYU_TEST_POSTGRES_DSN",
            object_storage_env="DAYU_TEST_OBJECT_STORAGE",
            redis_env="DAYU_TEST_REDIS",
            auth_key_env="DAYU_TEST_AUTH",
        ),
    )
    del fake_workspace
    session_factory = _FakeSessionFactory()
    _install_fake_production_preparation(
        monkeypatch, identity_service, session_factory
    )
    prepared = _call_prepare_host_runtime(tmp_path)
    assert prepared.host is fake_host
    return prepared, session_factory, sentinels


@pytest.mark.unit
def test_production_provider_exposes_exact_slice22_service_mapping_with_empty_execution_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """auto-provider 精确暴露三项并共享空 registry、store 与 Host。"""

    from dayu.investment.storage.postgres_jobs import PostgresJobStore
    from dayu.investment.storage.postgres_schedules import PostgresScheduleStore
    from dayu.services.job_service import JobExecutionRegistry, JobService
    from dayu.services.schedule_service import ScheduleService

    identity_service = _FakeIdentityService()
    prepared, session_factory, sentinels = _run_production_prepare(
        monkeypatch, tmp_path, identity_service
    )
    services = prepared.platform_composition.services
    assert set(services) == {
        "investment_identity",
        "durable_jobs",
        "durable_schedules",
    }
    assert services["investment_identity"] is identity_service
    job_service = services["durable_jobs"]
    schedule_service = services["durable_schedules"]
    assert isinstance(job_service, JobService)
    assert isinstance(schedule_service, ScheduleService)
    assert job_service.platform_service_name == "durable_jobs"
    assert schedule_service.platform_service_name == "durable_schedules"
    job_store = job_service._job_store
    schedule_store = schedule_service._schedule_store
    assert isinstance(job_store, PostgresJobStore)
    assert isinstance(schedule_store, PostgresScheduleStore)
    assert job_store._session_factory is session_factory
    assert schedule_store._session_factory is session_factory
    assert job_service._host_run_reader is sentinels.bare_host
    assert job_service._host_run_canceller is sentinels.bare_host
    assert isinstance(job_service._execution_registry, JobExecutionRegistry)
    assert job_service._execution_registry._handlers == {}
    assert schedule_service._job_gateway is job_service
    assert prepared.job_service is job_service
    assert prepared.schedule_service is schedule_service


@pytest.mark.unit
def test_production_provider_preserves_pre_host_pg_admission_and_injects_host_after_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """阶段 1 PG admission 先于 Host side effect；阶段 2 才注入 Host reader。"""

    from dayu.services.startup_preparation import _PlatformPreparation

    identity_service = _FakeIdentityService()
    prepared = None
    order: list[str] = []
    fake_workspace, _, _, _, fake_host, sentinels = _patch_host_runtime_dependencies(
        monkeypatch,
        tmp_path,
        platform_settings=PlatformSettings(
            enabled=True,
            profile=PlatformDeploymentProfile.PRODUCTION,
            postgres_dsn_env="DAYU_TEST_POSTGRES_DSN",
            object_storage_env="DAYU_TEST_OBJECT_STORAGE",
            redis_env="DAYU_TEST_REDIS",
            auth_key_env="DAYU_TEST_AUTH",
        ),
    )
    del fake_workspace

    def _fake_prepare(_settings) -> _PlatformPreparation:
        # 阶段 1 运行在 Host 构造之前：此刻 Host 副作用必须为零。
        assert sentinels.host_construct_calls == []
        order.append("phase1")
        from sqlalchemy.engine import Engine

        from dayu.investment.storage.postgres_identity import PostgresIdentityRepository

        return _PlatformPreparation(
            engine=_bare(Engine),
            session_factory=_FakeSessionFactory(),
            identity_repository=_bare(PostgresIdentityRepository),
            identity_service=identity_service,
        )

    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_production_platform_dependencies",
        _fake_prepare,
    )
    prepared = _call_prepare_host_runtime(tmp_path)
    assert prepared.host is fake_host
    assert order[0] == "phase1"
    # 阶段 2 的 host_run_reader 是真实 Host。
    from dayu.services.job_service import JobService

    job_service = prepared.platform_composition.services["durable_jobs"]
    assert isinstance(job_service, JobService)
    assert job_service._host_run_reader is fake_host


@pytest.mark.unit
def test_production_provider_failure_disposes_one_engine_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """阶段 2 或 composition 失败时 identity service 恰好 close 一次。"""

    identity_service = _FakeIdentityService()
    fake_workspace, _, _, _, _, sentinels = _patch_host_runtime_dependencies(
        monkeypatch,
        tmp_path,
        platform_settings=PlatformSettings(
            enabled=True,
            profile=PlatformDeploymentProfile.PRODUCTION,
            postgres_dsn_env="DAYU_TEST_POSTGRES_DSN",
            object_storage_env="DAYU_TEST_OBJECT_STORAGE",
            redis_env="DAYU_TEST_REDIS",
            auth_key_env="DAYU_TEST_AUTH",
        ),
    )
    del fake_workspace
    _install_fake_production_preparation(
        monkeypatch, identity_service, _FakeSessionFactory()
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation._build_production_services_provider",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stage2 boom")),
    )
    with pytest.raises(RuntimeError):
        _call_prepare_host_runtime(tmp_path)
    assert identity_service.close_calls == 1
    assert sentinels.all_empty() is False


@pytest.mark.unit
def test_prepared_runtime_close_retry_disposes_shared_engine_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """成功装配后重复 close() 只 dispose identity service 一次。"""

    identity_service = _FakeIdentityService()
    prepared, _, _ = _run_production_prepare(
        monkeypatch, tmp_path, identity_service
    )
    prepared.close()
    prepared.close()
    assert identity_service.close_calls == 1


def _minimal_prepared_runtime(
    admission: _PreparedQueueAdmission,
    *,
    include_services: bool,
) -> PreparedHostRuntimeDependencies:
    """构造只用于 wrapper call-count 的最小 prepared runtime。

    Args:
        admission: wrapper 传入 private root 的同一 admission。
        include_services: 是否放入 concrete Job/Schedule Service identity 桩。

    Returns:
        不访问内部资源的 prepared runtime。

    Raises:
        无。
    """

    from dayu.services.job_service import JobService
    from dayu.services.schedule_service import ScheduleService

    return PreparedHostRuntimeDependencies(
        workspace=_bare(WorkspaceResources),
        default_execution_options=_bare(ResolvedExecutionOptions),
        scene_execution_acceptance_preparer=_bare(
            SceneExecutionAcceptancePreparer
        ),
        host=_bare(Host),
        fins_runtime=_bare(DefaultFinsRuntime),
        job_service=_bare(JobService) if include_services else None,
        schedule_service=_bare(ScheduleService) if include_services else None,
        _queue_admission=admission,
    )


@pytest.mark.unit
def test_ordinary_startup_rejects_integration_before_any_side_effect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """ordinary wrapper 在 path/Host 副作用前拒绝 integration。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        无。
    """

    path_calls: list[Path] = []
    monkeypatch.setenv(DAYU_PLATFORM_ENABLED_ENV, "1")
    monkeypatch.setenv(DAYU_PLATFORM_PROFILE_ENV, "integration")
    monkeypatch.setenv(DAYU_PLATFORM_POSTGRES_DSN_ENV, "postgresql://integration")
    monkeypatch.delenv(DAYU_PLATFORM_OBJECT_STORAGE_ENV, raising=False)
    monkeypatch.delenv(DAYU_PLATFORM_REDIS_ENV, raising=False)
    monkeypatch.delenv(DAYU_PLATFORM_AUTH_KEY_ENV, raising=False)
    monkeypatch.setattr(
        "dayu.services.startup_preparation.resolve_startup_paths",
        lambda **_kwargs: path_calls.append(tmp_path),
    )

    with pytest.raises(PlatformSettingsError, match="ordinary startup"):
        _call_prepare_host_runtime(tmp_path)
    assert path_calls == []


@pytest.mark.unit
def test_queue_preparation_admits_redis_before_existing_runtime_preparation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """public wrapper 必须先 admission，后进入唯一 private root。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        无。
    """

    settings = _enabled_production_settings()
    queue_settings = PlatformQueueSettings(mode=PlatformQueueMode.EVENT_ASSISTED)
    order: list[str] = []

    def _record_admission(
        actual_settings: PlatformSettings,
        actual_queue_settings: PlatformQueueSettings | None,
    ) -> _PreparedQueueAdmission:
        """记录 admission 并返回 typed REDIS shape。"""

        assert actual_settings is settings
        assert actual_queue_settings is queue_settings
        order.append("admission")
        return _PreparedQueueAdmission(
            kind=PlatformQueueAdmissionKind.REDIS,
            queue_settings=queue_settings,
            publisher=_FakeQueueAdapter(),
            subscriber_factory=_FakeQueueAdapter(),
            redis_client=_FakeQueueAdapter(),
        )

    def _record_root(
        *,
        platform_settings: PlatformSettings,
        queue_admission: _PreparedQueueAdmission,
        request: _HostRuntimePreparationRequest,
    ) -> PreparedHostRuntimeDependencies:
        """记录 private root 调用并返回最小 runtime。"""

        assert platform_settings is settings
        assert request.workspace_root == tmp_path
        assert request.config_root == tmp_path / "config"
        assert isinstance(request.execution_options, ExecutionOptions)
        assert request.runtime_label == "Shared Host runtime"
        assert request.log_module == "APP.TEST"
        assert request.platform_provider is None
        order.append("root")
        return _minimal_prepared_runtime(queue_admission, include_services=False)

    monkeypatch.setattr(
        "dayu.services.startup_preparation.load_platform_settings",
        lambda _env: settings,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.load_platform_queue_settings",
        lambda _env, _profile: queue_settings,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_queue_admission",
        _record_admission,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_host_runtime_after_queue_admission",
        _record_root,
    )

    prepared = _call_prepare_host_runtime(tmp_path)
    assert order == ["admission", "root"]
    prepared.close()


@pytest.mark.unit
def test_queue_preparation_uses_one_admission_and_one_private_composition_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """platform wrapper 不得调用 ordinary wrapper或重复 admission/root。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        无。
    """

    settings = _enabled_production_settings()
    queue_settings = PlatformQueueSettings(mode=PlatformQueueMode.EVENT_ASSISTED)
    admission_calls: list[PlatformQueueSettings] = []
    root_calls: list[_PreparedQueueAdmission] = []

    def _count_admission(
        actual_settings: PlatformSettings,
        actual_queue_settings: PlatformQueueSettings | None,
    ) -> _PreparedQueueAdmission:
        """记录并返回同 settings identity 的 REDIS admission。"""

        assert actual_settings is settings
        assert actual_queue_settings is queue_settings
        admission_calls.append(queue_settings)
        adapter = _FakeQueueAdapter()
        return _PreparedQueueAdmission(
            kind=PlatformQueueAdmissionKind.REDIS,
            queue_settings=queue_settings,
            publisher=adapter,
            subscriber_factory=adapter,
            redis_client=adapter,
        )

    def _count_root(
        *,
        platform_settings: PlatformSettings,
        queue_admission: _PreparedQueueAdmission,
        request: _HostRuntimePreparationRequest,
    ) -> PreparedHostRuntimeDependencies:
        """记录 private root exact-once 调用。"""

        assert platform_settings is settings
        assert request.workspace_root == tmp_path
        assert request.config_root is None
        assert request.execution_options is None
        assert request.runtime_label == "platform worker"
        assert request.log_module == "TEST"
        assert request.platform_provider is None
        root_calls.append(queue_admission)
        return _minimal_prepared_runtime(queue_admission, include_services=True)

    monkeypatch.setattr(
        "dayu.services.startup_preparation.load_platform_settings",
        lambda _env: settings,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.load_platform_queue_settings",
        lambda _env, _profile: queue_settings,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_queue_admission",
        _count_admission,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_host_runtime_after_queue_admission",
        _count_root,
    )

    prepared = prepare_platform_queue_runtime_dependencies(
        workspace_root=tmp_path,
        config_root=None,
        execution_options=None,
        runtime_label="platform worker",
        log_module="TEST",
    )
    assert isinstance(prepared, PreparedPlatformQueueRuntime)
    assert len(admission_calls) == 1
    assert len(root_calls) == 1
    assert root_calls[0] is prepared.queue_admission
    prepared.close()


@pytest.mark.unit
def test_queue_preparation_exposes_typed_job_and_schedule_services_without_mapping_cast(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """special wrapper 直接持有 concrete services 与 POSTGRES_ONLY shape。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        无。
    """

    from dayu.services.job_service import JobService
    from dayu.services.schedule_service import ScheduleService

    settings = PlatformSettings(
        enabled=True,
        profile=PlatformDeploymentProfile.INTEGRATION,
        postgres_dsn_env="DAYU_TEST_POSTGRES_DSN",
    )
    _patch_host_runtime_dependencies(
        monkeypatch,
        tmp_path,
        platform_settings=settings,
    )
    identity_service = _FakeIdentityService()
    _install_fake_production_preparation(
        monkeypatch,
        identity_service,
        _FakeSessionFactory(),
    )

    prepared = prepare_platform_queue_runtime_dependencies(
        workspace_root=tmp_path,
        config_root=None,
        execution_options=None,
        runtime_label="platform scheduler",
        log_module="TEST",
    )

    assert isinstance(prepared.job_service, JobService)
    assert isinstance(prepared.schedule_service, ScheduleService)
    assert prepared.existing_runtime.job_service is prepared.job_service
    assert prepared.existing_runtime.schedule_service is prepared.schedule_service
    assert prepared.queue_admission.kind is PlatformQueueAdmissionKind.POSTGRES_ONLY
    assert prepared.queue_admission.publisher is None
    assert prepared.queue_admission.subscriber_factory is None
    assert prepared.queue_admission.redis_client is None
    prepared.close()


@pytest.mark.unit
def test_source_handler_registration_remains_absent_until_slice_2_3() -> None:
    """Slice 2.2 production execution registry 保持空且无替换入口。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    from dayu.services.job_service import JobExecutionRegistry, JobHandlerRegistry

    registry = JobExecutionRegistry(JobHandlerRegistry())
    assert registry._handlers == {}
    assert "remove" not in JobExecutionRegistry.__dict__
    assert "replace" not in JobExecutionRegistry.__dict__


@pytest.mark.unit
def test_schedule_service_structurally_satisfies_scheduler_gateway_without_importing_host() -> None:
    """ScheduleService 以结构类型满足 Host-local scheduler gateway。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    from dayu.host.scheduler import SchedulerGatewayProtocol
    from dayu.services.schedule_service import ScheduleService

    gateway: SchedulerGatewayProtocol = _bare(ScheduleService)
    assert isinstance(gateway, SchedulerGatewayProtocol)


@pytest.mark.unit
def test_queue_preparation_failure_closes_resources_in_reverse_dependency_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Redis-first 构造失败按 PG/lease/S3/Redis 逆序 exact-once close。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        无。
    """

    settings = _enabled_production_settings()
    _patch_host_runtime_dependencies(
        monkeypatch,
        tmp_path,
        platform_settings=settings,
    )
    close_order: list[str] = []
    adapter = _FakeQueueAdapter(close_order)
    s3_store = _CloseSafeS3Store(close_order)
    writer_lease = _FakeWriterLease(close_order)
    identity_service = _FakeIdentityService(close_order)
    _install_fake_production_preparation(
        monkeypatch,
        identity_service,
        _FakeSessionFactory(),
    )

    def _record_admission(
        _settings: PlatformSettings,
        queue_settings: PlatformQueueSettings | None,
    ) -> _PreparedQueueAdmission:
        """返回共享 close-order adapter 的 REDIS admission。"""

        assert queue_settings is not None
        return _PreparedQueueAdmission(
            kind=PlatformQueueAdmissionKind.REDIS,
            queue_settings=queue_settings,
            publisher=adapter,
            subscriber_factory=adapter,
            redis_client=adapter,
        )

    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_queue_admission",
        _record_admission,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation._build_s3_store_from_settings",
        lambda *_args, **_kwargs: s3_store,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.acquire_writer_lease",
        lambda _workspace_root: writer_lease,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.Host",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("host boom")),
    )

    with pytest.raises(RuntimeError, match="host boom"):
        _call_prepare_host_runtime(tmp_path)
    assert close_order == ["pg", "lease", "s3", "redis"]


@pytest.mark.unit
def test_invalid_platform_settings_never_import_concrete_redis_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """settings fail-fast 不得触达唯一 concrete Redis local-import owner。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        无。
    """

    admission_calls: list[str] = []

    def _forbidden_admission(
        _settings: PlatformSettings,
        _queue_settings: PlatformQueueSettings | None,
    ) -> _PreparedQueueAdmission:
        """记录非法 settings 是否错误触达 admission。

        Args:
            _settings: 非法 settings（不应收到）。
            _queue_settings: queue settings（不应收到）。

        Returns:
            本函数不返回。

        Raises:
            AssertionError: 一旦被调用即抛出。
        """

        admission_calls.append("called")
        raise AssertionError("invalid settings 不得触达 Redis admission")

    monkeypatch.setenv(DAYU_PLATFORM_ENABLED_ENV, "1")
    monkeypatch.setenv(DAYU_PLATFORM_PROFILE_ENV, "production")
    for env_var in (
        DAYU_PLATFORM_POSTGRES_DSN_ENV,
        DAYU_PLATFORM_OBJECT_STORAGE_ENV,
        DAYU_PLATFORM_REDIS_ENV,
        DAYU_PLATFORM_AUTH_KEY_ENV,
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_queue_admission",
        _forbidden_admission,
    )

    with pytest.raises(PlatformSettingsError):
        _call_prepare_host_runtime(tmp_path)
    assert admission_calls == []


@pytest.mark.unit
def test_production_queue_admission_constructs_and_pings_one_typed_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """production admission local adapter 构造/ping 各一次且不泄漏 URL。

    Args:
        monkeypatch: pytest 打桩器。

    Returns:
        无。

    Raises:
        无。
    """

    from dayu.host.redis_wakeup import RedisWakeupAdapter

    settings = _enabled_production_settings()
    queue_settings = PlatformQueueSettings(mode=PlatformQueueMode.EVENT_ASSISTED)
    adapter = _FakeQueueAdapter()
    from_url_calls: list[tuple[str, float]] = []
    redis_url = "redis://127.0.0.1:6379/0"
    monkeypatch.setenv(DAYU_PLATFORM_REDIS_ENV, redis_url)

    def _from_url(
        actual_url: str,
        *,
        timeout_seconds: float,
    ) -> _FakeQueueAdapter:
        """记录 adapter construction 参数。

        Args:
            actual_url: Redis URL。
            timeout_seconds: bounded timeout。

        Returns:
            共享 adapter 桩。

        Raises:
            无。
        """

        from_url_calls.append((actual_url, timeout_seconds))
        return adapter

    monkeypatch.setattr(RedisWakeupAdapter, "from_url", _from_url)
    admission = _prepare_queue_admission(settings, queue_settings)

    assert admission.kind is PlatformQueueAdmissionKind.REDIS
    assert admission.publisher is adapter
    assert admission.subscriber_factory is adapter
    assert admission.redis_client is adapter
    assert from_url_calls == [(redis_url, 1.0)]
    assert adapter.ping_calls == 1
    assert redis_url not in repr(admission)
    admission.close()
    admission.close()
    assert adapter.close_calls == 1


@pytest.mark.unit
def test_production_queue_real_redis_admission_precedes_postgres_s3_host_and_workspace_initialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """concrete Redis adapter admission 严格早于其余 production 装配。

    本测试运行真实 ``_prepare_queue_admission`` 与 concrete
    ``RedisWakeupAdapter.from_url`` 逻辑，只把最底层 redis-py client 和
    S3/PG/Host/workspace 替换为受控 typed doubles，避免外部网络副作用。

    Args:
        monkeypatch: pytest 打桩器。
        tmp_path: 临时工作区。

    Returns:
        无。

    Raises:
        无。
    """

    import redis
    from sqlalchemy.engine import Engine

    from dayu.investment.storage.postgres_identity import PostgresIdentityRepository
    from dayu.services.startup_preparation import _PlatformPreparation

    settings = _enabled_production_settings()
    (_, _, _, _, _, sentinels) = _patch_host_runtime_dependencies(
        monkeypatch,
        tmp_path,
        platform_settings=settings,
    )
    order: list[str] = []
    raw_client = _FakeQueueAdapter(operation_order=order)
    identity_service = _FakeIdentityService()
    session_factory = _FakeSessionFactory()
    fake_paths = SimpleNamespace(
        workspace_root=tmp_path,
        config_root=tmp_path / "config",
        output_dir=tmp_path / "output",
    )
    fake_workspace = _bare(WorkspaceResources)
    wire_kwargs: list[tuple[int, bool, float, float]] = []

    def _redis_from_url(
        redis_url: str,
        *,
        protocol: int,
        decode_responses: bool,
        socket_connect_timeout: float,
        socket_timeout: float,
    ) -> _FakeQueueAdapter:
        """记录 concrete adapter 传给 redis-py 的 fixed wire 参数。

        Args:
            redis_url: 受控 Redis URL。
            protocol: RESP protocol version。
            decode_responses: 是否解码 response。
            socket_connect_timeout: connect timeout。
            socket_timeout: socket timeout。

        Returns:
            满足 redis-py client 窄协议的受控桩。

        Raises:
            AssertionError: URL 非预期时抛出。
        """

        assert redis_url == "redis://127.0.0.1:6379/0"
        wire_kwargs.append(
            (
                protocol,
                decode_responses,
                socket_connect_timeout,
                socket_timeout,
            )
        )
        return raw_client

    def _resolve_paths(**_kwargs) -> SimpleNamespace:
        """记录 queue admission 后的首次 path resolution。"""

        order.append("path")
        return fake_paths

    def _build_s3(
        _env: Mapping[str, str],
        _settings: PlatformSettings,
    ) -> S3FileStore:
        """记录 S3 admission 并返回受控 store。"""

        order.append("s3")
        return _CloseSafeS3Store()

    def _prepare_pg(_settings: PlatformSettings) -> _PlatformPreparation:
        """记录 PG admission 并返回受控 preparation。"""

        order.append("pg")
        return _PlatformPreparation(
            engine=_bare(Engine),
            session_factory=session_factory,
            identity_repository=_bare(PostgresIdentityRepository),
            identity_service=identity_service,
        )

    def _build_workspace(**_kwargs) -> WorkspaceResources:
        """记录 workspace 资源构造。"""

        order.append("workspace")
        return fake_workspace

    def _build_host(**_kwargs) -> Host:
        """记录 Host 构造并返回结构化 Host 桩。"""

        order.append("host")
        return sentinels.bare_host

    monkeypatch.setenv(DAYU_PLATFORM_REDIS_ENV, "redis://127.0.0.1:6379/0")
    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(_redis_from_url))
    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_queue_admission",
        _prepare_queue_admission,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.resolve_startup_paths",
        _resolve_paths,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation._build_s3_store_from_settings",
        _build_s3,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation._prepare_production_platform_dependencies",
        _prepare_pg,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.WorkspaceResources",
        _build_workspace,
    )
    monkeypatch.setattr(
        "dayu.services.startup_preparation.Host",
        _build_host,
    )

    prepared = _call_prepare_host_runtime(tmp_path)
    assert order == ["redis", "path", "s3", "pg", "workspace", "host"]
    assert wire_kwargs == [(2, False, 1.0, 1.0)]
    prepared.close()
