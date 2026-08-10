"""Service 层对启动期暴露的 preparation API。

本模块是 Service 层的 public surface，供 UI 启动期装配调用。
它负责把稳定输入收敛成 Service 请求期需要的公开依赖，
但不把内部 reader / preparer 的实现细节泄漏给 `startup/` 或 UI。

本模块同时是投资平台 production provider 的装配真源（S12-CTRL-06/07）：

- platform enabled + production 且未显式注入 provider 时，只读取
  ``PlatformSettings.postgres_dsn_env`` 指向的环境变量值，构造关闭
  echo 的 engine/session factory、PostgreSQL repository、
  ``InvestmentIdentityService`` 与只含 ``investment_identity`` 的
  provider，然后交给 ``build_platform_composition()``；
- 显式 provider 注入仍优先用于 tests/dev；development in-memory
  profile 不假造 production repository，缺显式 provider 时继续
  fail-fast；错误不得回显 DSN；
- auto-created provider 在成功态由
  ``PreparedHostRuntimeDependencies`` 持有
  ``_owned_platform_lifecycle``（atexit 协调器），公开幂等 ``close()``，
  并在完整构造成功后注册一次 ``atexit`` 兜底；显式注入 provider 由
  caller own，启动失败时 auto-created engine 被同步 dispose。
"""

from __future__ import annotations

import atexit
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from dayu.contracts.infrastructure import ModelCatalogProtocol, PromptAssetStoreProtocol
from dayu.execution.options import (
    ExecutionOptions,
    ResolvedExecutionOptions,
    build_base_execution_options,
    merge_execution_options,
)
from dayu.fins.service_runtime import DefaultFinsRuntime, FinsRuntimeProtocol
from dayu.host import Host, resolve_host_config
from dayu.host.concurrency import SQLiteConcurrencyGovernor
from dayu.host.host_store import HostStore
from dayu.investment.composition import (
    PlatformComposition,
    PlatformCompositionProviderProtocol,
    PlatformOwnedLifecycleProtocol,
    PlatformServiceProtocol,
)
from dayu.investment.config import (
    PlatformDeploymentProfile,
    PlatformSettings,
    PlatformSettingsError,
    load_platform_settings,
)
from dayu.investment.storage.db import (
    PLATFORM_APP_ROLE,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage.postgres_identity import PostgresIdentityRepository
from dayu.services.concurrency_lanes import SERVICE_DEFAULT_LANE_CONFIG
from dayu.services.conversation_policy_reader import ConversationPolicyReader
from dayu.services.fins_download_lane_gate import GovernorCnDownloadPdfGate
from dayu.services.host_admin_service import HostAdminService
from dayu.services.investment_identity import InvestmentIdentityService
from dayu.services.scene_definition_reader import SceneDefinitionReader
from dayu.services.scene_execution_acceptance import SceneExecutionAcceptancePreparer
from dayu.services.startup_recovery import recover_host_startup_state
from dayu.startup.config_file_resolver import ConfigFileResolver
from dayu.startup.config_loader import ConfigLoader
from dayu.startup.model_catalog import ConfigLoaderModelCatalog
from dayu.startup.paths import StartupPaths, resolve_startup_paths
from dayu.startup.platform import PlatformCompositionError, build_platform_composition
from dayu.startup.prompt_assets import FilePromptAssetStore
from dayu.startup.workspace import WorkspaceResources

_INVESTMENT_IDENTITY_SERVICE_NAME = "investment_identity"
"""production provider 注册的 identity/source Service 稳定名。"""


@dataclass(frozen=True)
class PreparedHostAdminDependencies:
    """Host 管理子命令使用的轻量依赖集合。

    Args:
        paths: 启动期解析出的路径信息（供 CLI 展示）。
        host_admin_service: 已装配的宿主管理服务。
    """

    paths: StartupPaths
    host_admin_service: HostAdminService


def _default_platform_composition() -> PlatformComposition[PlatformServiceProtocol]:
    """返回未显式装配平台组合时的禁用默认组合根。

    Args:
        无。

    Returns:
        携带 ``enabled=False`` 与空 service 注册的平台组合根。

    Raises:
        无。
    """

    return PlatformComposition.disabled()


@dataclass(frozen=True)
class PreparedHostRuntimeDependencies:
    """共享 Host 运行时依赖集合。

    Args:
        workspace: 工作区稳定资源。
        default_execution_options: 启动期解析后的默认执行选项。
        scene_execution_acceptance_preparer: scene 执行接受准备器。
        host: Host 实例。
        fins_runtime: 财报领域运行时。
        platform_composition: 只承载 Service 协议实例的平台组合根；
            未显式装配时默认为平台禁用的组合根。
        _owned_platform_lifecycle: 成功态 auto-created provider 的
            atexit 协调器（private wrapper）；``close()`` 委托它协调
            manual close 与进程退出回调。无自持资源时为 ``None``。
    """

    workspace: WorkspaceResources
    default_execution_options: ResolvedExecutionOptions
    scene_execution_acceptance_preparer: SceneExecutionAcceptancePreparer
    host: Host
    fins_runtime: FinsRuntimeProtocol
    platform_composition: PlatformComposition[PlatformServiceProtocol] = field(
        default_factory=_default_platform_composition,
    )
    _owned_platform_lifecycle: _OwnedLifecycleRegistration | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def close(self) -> None:
        """释放成功态 auto-created platform 自持资源（幂等）。

        委托 ``_OwnedLifecycleRegistration.close()``：manual close 先
        赢得 close 权并解除 atexit 回调意图，之后进程退出时回调为
        no-op。显式注入 provider、平台禁用与 development 路径为
        no-op。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if self._owned_platform_lifecycle is not None:
            self._owned_platform_lifecycle.close()


def _read_postgres_dsn(settings: PlatformSettings) -> str:
    """读取 production PostgreSQL DSN 环境变量值。

    Args:
        settings: 已解析的平台严格设置。

    Returns:
        PostgreSQL DSN 字符串。

    Raises:
        PlatformSettingsError: DSN 环境变量缺失或为空时抛出（不回显
            候选值）。
        PlatformCompositionError: DSN 存在但无法读取时抛出（不泄漏
            DSN 内容）。
    """

    if settings.postgres_dsn_env is None:
        raise PlatformCompositionError(
            "production PostgreSQL identity provider 初始化失败"
        )
    dsn = os.environ.get(settings.postgres_dsn_env, "")
    if not dsn or not dsn.strip():
        raise PlatformSettingsError(
            f"环境变量 {settings.postgres_dsn_env} 缺失或为空"
        )
    return dsn


def _probe_production_engine(engine: Engine) -> None:
    """对 production engine 做最小连接与角色 admission probe。

    在返回 auto-created provider 前执行：

    - ``SELECT 1`` 确认数据库可连接（不可达/认证失败在此失败）；
    - ``pg_has_role(current_user, app_role, 'MEMBER')`` 确认当前用户是
      ``dayu_platform_app`` group role 的 member（支持 plan 的临时
      ``LOGIN IN ROLE dayu_platform_app``，而非要求用户名等于 group
      role 名）；
    - 拒绝 superuser 与 BYPASSRLS 连接（application 连接必须
      ``NOBYPASSRLS`` 且非 superuser，与 PG16 black-box contract
      一致）。

    任何连接/认证/角色失败原样抛出，由调用方 ``dispose()`` 并统一
    转换为不含 cause 的 ``PlatformCompositionError``。

    Args:
        engine: production engine。

    Returns:
        无。

    Raises:
        Exception: 连接、认证或角色校验失败时原样抛出（消息由调用方
            抑制，不泄漏 DSN/候选值）。
    """

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        admission = conn.execute(
            text(
                "SELECT pg_has_role(current_user, :app_role, 'MEMBER'), "
                "rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            ),
            {"app_role": PLATFORM_APP_ROLE},
        ).first()
        if admission is None:
            raise RuntimeError("application role admission failed")
        is_member, is_superuser, is_bypassrls = admission
        if not is_member or is_superuser or is_bypassrls:
            raise RuntimeError("application role admission failed")


def _build_production_identity_provider(
    settings: PlatformSettings,
) -> tuple[PlatformCompositionProviderProtocol, PlatformOwnedLifecycleProtocol]:
    """构造 production identity provider 与自持生命周期句柄。

    构造关闭 echo 的 engine/session factory、PostgreSQL repository、
    ``InvestmentIdentityService`` 与只含 ``investment_identity`` 的
    provider。DSN 读取失败或 engine 创建失败统一抛稳定错误，且在任何
    后续组合失败时由调用方 dispose engine。

    Args:
        settings: 已解析的平台严格设置。

    Returns:
        ``(provider, lifecycle)`` 二元组；lifecycle 是
        ``InvestmentIdentityService``（实现
        ``PlatformOwnedLifecycleProtocol``）。

    Raises:
        PlatformCompositionError: DSN/engine/repository/service 任一
            构造失败时抛出（不泄漏 DSN）。
        PlatformSettingsError: DSN 环境变量缺失或为空时抛出。
    """

    dsn = _read_postgres_dsn(settings)
    engine: Engine | None = None
    try:
        engine = create_platform_engine(dsn)
        _probe_production_engine(engine)
        session_factory = create_platform_session_factory(engine)
        repository = PostgresIdentityRepository(session_factory)
        service = InvestmentIdentityService(
            identity_repository=repository,
            source_repository=repository,
            owned_engine=engine,
        )
    except PlatformCompositionError:
        if engine is not None:
            engine.dispose()
        raise
    except Exception:
        if engine is not None:
            engine.dispose()
        raise PlatformCompositionError(
            "production PostgreSQL identity provider 初始化失败"
        ) from None

    class _ProductionIdentityProvider:
        """production identity provider（只注册 ``investment_identity``）。"""

        def provide_services(self) -> Mapping[str, PlatformServiceProtocol]:
            """返回只含 ``investment_identity`` 的 Service 映射。

            Args:
                无。

            Returns:
                ``{"investment_identity": service}`` 映射。

            Raises:
                无。
            """

            return {_INVESTMENT_IDENTITY_SERVICE_NAME: service}

    return _ProductionIdentityProvider(), service


def _default_provider_or_fail(
    settings: PlatformSettings,
    explicit_provider: PlatformCompositionProviderProtocol | None,
) -> tuple[PlatformCompositionProviderProtocol | None, PlatformOwnedLifecycleProtocol | None]:
    """解析组合提供者与自持生命周期。

    显式 provider 优先；未显式注入时 production 构造默认 provider，
    development 保持 fail-fast（不假造 in-memory）。

    Args:
        settings: 已解析的平台严格设置。
        explicit_provider: 显式注入的组合提供者（可空）。

    Returns:
        ``(provider, lifecycle)`` 二元组；provider 为 ``None`` 表示
        platform 禁用；lifecycle 为 ``None`` 表示无自持资源。

    Raises:
        PlatformCompositionError: enabled + development 且未注入
            provider，或 production provider 初始化失败时抛出。
    """

    if explicit_provider is not None:
        return explicit_provider, None
    if not settings.enabled:
        return None, None
    if settings.profile is PlatformDeploymentProfile.PRODUCTION:
        return _build_production_identity_provider(settings)
    raise PlatformCompositionError(
        "development 平台启用必须显式注入组合提供者，禁止用 PostgreSQL 冒充 in-memory"
    )


class _OwnedLifecycleRegistration:
    """成功态 auto-created lifecycle 的 atexit 协调器。

    初始化仅持有底层 lifecycle，不注册 atexit 回调；必须由装配方在
    auto-created provider 完整构造成功后显式调用 ``register()`` 挂载
    （exact-once）。``close()``（manual）无条件释放底层并解除注册
    意图；``_close_at_exit()``（callback）仅在已注册且未被手动 close
    时执行一次，先到者赢得 close 权，保证底层 ``close()`` 恰好一次。

    Args:
        lifecycle: 自持生命周期句柄。
    """

    def __init__(self, lifecycle: PlatformOwnedLifecycleProtocol) -> None:
        """持有句柄并初始化为未注册、未关闭状态。

        Args:
            lifecycle: 自持生命周期句柄。

        Returns:
            无。

        Raises:
            无。
        """

        self._lifecycle = lifecycle
        self._registered = False
        self._closed = False

    def register(self) -> None:
        """注册 atexit 回调（exact-once）。

        重复调用为 no-op；已手动 close 后也拒绝再次注册，避免退出时
        残留回调。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if self._registered or self._closed:
            return
        self._registered = True
        atexit.register(self._close_at_exit)

    def _close_at_exit(self) -> None:
        """atexit 回调：仅当已注册且未被手动 close 时才执行一次 close。

        手动 ``close()`` 后 ``_closed`` 为 True，进程退出时回调为
        no-op；未手动 close 时回调执行一次并立即标记，保证
        exact-once。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if not self._registered or self._closed:
            return
        self._closed = True
        self._registered = False
        self._lifecycle.close()

    def close(self) -> None:
        """手动 close 并解除 atexit 注册意图（幂等）。

        无论是否已注册都释放底层；已 close 过则为 no-op。

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
        self._registered = False
        self._lifecycle.close()


def prepare_scene_execution_acceptance_preparer(
    *,
    workspace_root: Path,
    default_execution_options: ResolvedExecutionOptions,
    model_catalog: ModelCatalogProtocol,
    prompt_asset_store: PromptAssetStoreProtocol,
) -> SceneExecutionAcceptancePreparer:
    """准备 Service 侧 scene 执行接受准备器。

    Args:
        workspace_root: 当前工作区根目录。
        default_execution_options: 启动期已解析的默认执行选项。
        model_catalog: 启动期模型目录对象。
        prompt_asset_store: prompt 资产仓储对象。

    Returns:
        已完成内部 reader 装配的 `SceneExecutionAcceptancePreparer`。

    Raises:
        无。
    """

    scene_definition_reader = SceneDefinitionReader(prompt_asset_store)
    conversation_policy_reader = ConversationPolicyReader()
    return SceneExecutionAcceptancePreparer(
        workspace_dir=workspace_root,
        base_execution_options=default_execution_options,
        model_catalog=model_catalog,
        scene_definition_reader=scene_definition_reader,
        conversation_policy_reader=conversation_policy_reader,
    )


def prepare_host_runtime_dependencies(
    *,
    workspace_root: Path,
    config_root: Path | None,
    execution_options: ExecutionOptions | None,
    runtime_label: str,
    log_module: str,
    platform_provider: PlatformCompositionProviderProtocol | None = None,
) -> PreparedHostRuntimeDependencies:
    """准备 CLI / WeChat 共用的 Host 运行时稳定依赖。

    Args:
        workspace_root: 工作区根目录。
        config_root: 可选配置根目录。
        execution_options: 请求级执行选项。
        runtime_label: startup recovery 的运行时标签。
        log_module: recovery 日志模块名。
        platform_provider: 可选平台组合提供者；平台启用时必须注入，
            否则启动期 fail-fast。

    Returns:
        已完成 Host、scene preparation、fins runtime 与平台组合装配的
        共享依赖集合。

    Raises:
        PlatformSettingsError: 平台环境变量设置违反严格规则时抛出；
            在函数最前部抛出，早于任何 Host / Fins 副作用。
        PlatformCompositionError: 平台启用但未注入组合提供者、提供者
            不满足协议，或提供者产出的 service 注册违反组合契约时
            抛出；同样早于任何 Host / Fins 副作用。
        组合提供者自身抛出的异常原样传播，且必发生在任何 Host / Fins
        副作用之前。
    """

    platform_settings = load_platform_settings(os.environ)
    resolved_provider, owned_lifecycle = _default_provider_or_fail(
        platform_settings,
        platform_provider,
    )
    lifecycle_registration: _OwnedLifecycleRegistration | None = None
    try:
        platform_composition = build_platform_composition(
            settings=platform_settings,
            provider=resolved_provider,
        )
        paths = resolve_startup_paths(
            workspace_root=workspace_root,
            config_root=config_root,
        )
        resolver = ConfigFileResolver(paths.config_root)
        config_loader = ConfigLoader(resolver)
        prompt_asset_store = FilePromptAssetStore(resolver)
        workspace = WorkspaceResources(
            workspace_dir=paths.workspace_root,
            config_root=paths.config_root,
            output_dir=paths.output_dir,
            config_loader=config_loader,
            prompt_asset_store=prompt_asset_store,
        )
        model_catalog = ConfigLoaderModelCatalog(config_loader)
        run_config = config_loader.load_run_config()
        base_execution_options = build_base_execution_options(
            workspace_dir=paths.workspace_root,
            run_config=run_config,
        )
        default_execution_options = merge_execution_options(
            base_options=base_execution_options,
            workspace_dir=paths.workspace_root,
            execution_options=execution_options,
        )
        scene_execution_acceptance_preparer = prepare_scene_execution_acceptance_preparer(
            workspace_root=paths.workspace_root,
            default_execution_options=default_execution_options,
            model_catalog=model_catalog,
            prompt_asset_store=prompt_asset_store,
        )
        host_config = resolve_host_config(
            workspace_root=paths.workspace_root,
            run_config=run_config,
            service_lane_defaults=dict(SERVICE_DEFAULT_LANE_CONFIG),
            explicit_lane_config=None,
        )
        pdf_gate_host_store = HostStore(host_config.store_path)
        pdf_gate_host_store.initialize_schema()
        fins_runtime = DefaultFinsRuntime.create(
            workspace_root=paths.workspace_root,
            cn_download_pdf_gate=GovernorCnDownloadPdfGate(
                governor=SQLiteConcurrencyGovernor(
                    pdf_gate_host_store,
                    lane_config=host_config.lane_config,
                )
            ),
        )
        host = Host(
            workspace=workspace,
            model_catalog=model_catalog,
            default_execution_options=default_execution_options,
            host_store_path=host_config.store_path,
            lane_config=host_config.lane_config,
            pending_turn_resume_max_attempts=host_config.pending_turn_resume_max_attempts,
            pending_turn_retention_hours=host_config.pending_turn_retention_hours,
            cancellation_bridge_poll_interval_seconds=(
                host_config.cancellation_bridge_poll_interval_seconds
            ),
            cancellation_bridge_failure_grace_period_seconds=(
                host_config.cancellation_bridge_failure_grace_period_seconds
            ),
            event_bus=None,
        )
        recover_host_startup_state(
            HostAdminService(host=host),
            runtime_label=runtime_label,
            log_module=log_module,
        )
        if owned_lifecycle is not None:
            lifecycle_registration = _OwnedLifecycleRegistration(owned_lifecycle)
        prepared = PreparedHostRuntimeDependencies(
            workspace=workspace,
            default_execution_options=default_execution_options,
            scene_execution_acceptance_preparer=scene_execution_acceptance_preparer,
            host=host,
            fins_runtime=fins_runtime,
            platform_composition=platform_composition,
            _owned_platform_lifecycle=lifecycle_registration,
        )
        if lifecycle_registration is not None:
            lifecycle_registration.register()
        return prepared
    except Exception:
        if lifecycle_registration is not None:
            lifecycle_registration.close()
        elif owned_lifecycle is not None:
            owned_lifecycle.close()
        raise


def prepare_host_admin_dependencies(
    *,
    workspace_root: Path,
    config_root: Path | None,
) -> PreparedHostAdminDependencies:
    """为 Host 管理子命令准备轻量依赖。

    本入口不构造执行期所需的 scene preparer 与 fins runtime，
    仅装配 Host 并封装出 `HostAdminService`，供 CLI 展示与运维命令使用。

    Args:
        workspace_root: 工作区根目录。
        config_root: 可选配置根目录。

    Returns:
        已装配的宿主管理服务以及配套路径信息。

    Raises:
        TypeError: `run.json` 配置结构非法时抛出。
        ValueError: `run.json` 配置值非法时抛出。
    """

    paths = resolve_startup_paths(
        workspace_root=workspace_root,
        config_root=config_root,
    )
    resolver = ConfigFileResolver(paths.config_root)
    config_loader = ConfigLoader(resolver)
    run_config = config_loader.load_run_config()
    host_config = resolve_host_config(
        workspace_root=paths.workspace_root,
        run_config=run_config,
        service_lane_defaults=dict(SERVICE_DEFAULT_LANE_CONFIG),
        explicit_lane_config=None,
    )
    host = Host(
        host_store_path=host_config.store_path,
        lane_config=host_config.lane_config,
        pending_turn_resume_max_attempts=host_config.pending_turn_resume_max_attempts,
        pending_turn_retention_hours=host_config.pending_turn_retention_hours,
        cancellation_bridge_poll_interval_seconds=(
            host_config.cancellation_bridge_poll_interval_seconds
        ),
        cancellation_bridge_failure_grace_period_seconds=(
            host_config.cancellation_bridge_failure_grace_period_seconds
        ),
        event_bus=None,
    )
    return PreparedHostAdminDependencies(
        paths=paths,
        host_admin_service=HostAdminService(host=host),
    )


__all__ = [
    "PreparedHostAdminDependencies",
    "PreparedHostRuntimeDependencies",
    "prepare_host_admin_dependencies",
    "prepare_host_runtime_dependencies",
    "prepare_scene_execution_acceptance_preparer",
]
