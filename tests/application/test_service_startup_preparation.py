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
from typing import TypeVar

import pytest

from dayu.execution.options import ExecutionOptions, ResolvedExecutionOptions
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.host import Host
from dayu.host.protocols import HostAdminOperationsProtocol
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
    PlatformSettings,
    PlatformSettingsError,
)
from dayu.services.scene_execution_acceptance import SceneExecutionAcceptancePreparer
from dayu.services.startup_preparation import (
    PreparedHostRuntimeDependencies,
    prepare_host_runtime_dependencies,
)
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
    def test_missing_production_config_fails_before_host_side_effects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """缺四类 production 配置时，Host / Fins 副作用计数为零。

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
        for env_var in (
            DAYU_PLATFORM_POSTGRES_DSN_ENV,
            DAYU_PLATFORM_OBJECT_STORAGE_ENV,
            DAYU_PLATFORM_REDIS_ENV,
            DAYU_PLATFORM_AUTH_KEY_ENV,
        ):
            monkeypatch.delenv(env_var, raising=False)

        with pytest.raises(PlatformSettingsError):
            _call_prepare_host_runtime(tmp_path)
        assert sentinels.all_empty()

    @pytest.mark.unit
    def test_missing_provider_fails_before_host_side_effects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """缺组合提供者时，Host / Fins 副作用计数为零。

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
        with pytest.raises(PlatformCompositionError):
            _call_prepare_host_runtime(tmp_path)
        assert sentinels.all_empty()

    @pytest.mark.unit
    def test_provider_error_fails_before_host_side_effects(
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
        with pytest.raises(RuntimeError, match="provider boom"):
            _call_prepare_host_runtime(
                tmp_path,
                platform_provider=_RaisingPlatformCompositionProvider(),
            )
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
        """平台启用且未注入提供者时装配期 fail-fast。

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
        with pytest.raises(PlatformCompositionError):
            _call_prepare_host_runtime(tmp_path)
        assert sentinels.all_empty()

    @pytest.mark.unit
    def test_platform_enabled_with_provider_wires_composition(
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
        assert len(sentinels.initialize_schema_calls) == 1
        assert len(sentinels.host_construct_calls) == 1
        assert len(sentinels.recovery_calls) == 1


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
