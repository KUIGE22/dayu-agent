"""Service 层对启动期暴露的 preparation API。

本模块是 Service 层的 public surface，供 UI 启动期装配调用。
它负责把稳定输入收敛成 Service 请求期需要的公开依赖，
但不把内部 reader / preparer 的实现细节泄漏给 `startup/` 或 UI。

本模块同时是投资平台 production/durable queue provider 的唯一装配真源：

- ordinary 与 platform queue 两个 public wrapper 都先解析严格 settings，
  再完成 typed queue admission，并且只调用同一 private composition root；
  production Redis package/client/ping 必须早于路径、S3、PG、Host 与
  workspace 副作用，integration special runtime 固定为 PG-only；
- platform enabled + production/integration 且使用 auto-provider 时，
  共享唯一 engine/session factory、descriptor/execution registries 与
  wakeup publisher，精确装配 ``investment_identity``、``durable_jobs``、
  ``durable_schedules`` 三项 Service；
- 显式 provider 注入仍优先用于 tests/dev；development in-memory
  profile 不假造 production repository；ordinary production 显式
  provider 仍不得绕过 Redis admission，也不自动向 custom provider
  注入 publisher；错误不得回显 Redis URL/DSN；
- auto-created provider 在成功态由
  ``PreparedHostRuntimeDependencies`` 持有
  ``_owned_platform_lifecycle``（atexit 协调器），公开幂等 ``close()``，
  并在完整构造成功后注册一次 ``atexit`` 兜底；queue admission 由
  prepared runtime 幂等关闭，启动失败时所有自持资源逆序释放。
"""

from __future__ import annotations

import atexit
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from dayu.contracts.infrastructure import ModelCatalogProtocol, PromptAssetStoreProtocol
from dayu.execution.options import (
    ExecutionOptions,
    ResolvedExecutionOptions,
    build_base_execution_options,
    merge_execution_options,
)
from dayu.fins.service_runtime import DefaultFinsRuntime, FinsRuntimeProtocol
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage.s3_file_store import S3FileStore
from dayu.fins.storage.s3_settings import (
    S3SettingsError,
    parse_object_storage_settings,
    read_credentials,
)
from dayu.fins.storage.writer_lease import WriterLease, acquire_writer_lease
from dayu.fins.toolset_registrars import build_fins_toolset_registrars
from dayu.host import Host, resolve_host_config
from dayu.host.concurrency import SQLiteConcurrencyGovernor
from dayu.host.host_store import HostStore
from dayu.host.worker import (
    RedisWakeupClientProtocol,
    RedisWakeupSubscriberFactoryProtocol,
)
from dayu.investment.composition import (
    PlatformComposition,
    PlatformCompositionProviderProtocol,
    PlatformOwnedLifecycleProtocol,
    PlatformServiceProtocol,
    PlatformWorkspaceImportServiceProtocol,
)
from dayu.investment.config import (
    PlatformDeploymentProfile,
    PlatformQueueAdmissionKind,
    PlatformQueueMode,
    PlatformQueueSettings,
    PlatformSettings,
    PlatformSettingsError,
    load_platform_queue_settings,
    load_platform_settings,
)
from dayu.investment.domain.workspace_import import WorkspaceImportRepositoryFailureError
from dayu.investment.storage.db import (
    PLATFORM_APP_ROLE,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage.postgres_identity import PostgresIdentityRepository
from dayu.investment.storage.postgres_jobs import PostgresJobStore
from dayu.investment.storage.postgres_schedules import PostgresScheduleStore
from dayu.investment.storage.postgres_workspace_import import PostgresWorkspaceImportRepository
from dayu.services.concurrency_lanes import SERVICE_DEFAULT_LANE_CONFIG
from dayu.services.conversation_policy_reader import ConversationPolicyReader
from dayu.services.fins_download_lane_gate import GovernorCnDownloadPdfGate
from dayu.services.host_admin_service import HostAdminService
from dayu.services.investment_identity import InvestmentIdentityService
from dayu.services.job_service import (
    DURABLE_JOBS_SERVICE_NAME,
    HostRunCancellationProtocol,
    HostRunReaderProtocol,
    JobExecutionRegistry,
    JobHandlerRegistry,
    JobService,
    JobServiceRuntimeAdapters,
    JobWakeupPublisherProtocol,
)
from dayu.services.scene_definition_reader import SceneDefinitionReader
from dayu.services.scene_execution_acceptance import SceneExecutionAcceptancePreparer
from dayu.services.schedule_service import (
    DURABLE_SCHEDULES_SERVICE_NAME,
    ScheduleService,
)
from dayu.services.startup_recovery import recover_host_startup_state
from dayu.services.workspace_import import WorkspaceImportService
from dayu.startup.config_file_resolver import ConfigFileResolver
from dayu.startup.config_loader import ConfigLoader
from dayu.startup.model_catalog import ConfigLoaderModelCatalog
from dayu.startup.paths import StartupPaths, resolve_startup_paths
from dayu.startup.platform import PlatformCompositionError, build_platform_composition
from dayu.startup.prompt_assets import FilePromptAssetStore
from dayu.startup.workspace import WorkspaceResources

_INVESTMENT_IDENTITY_SERVICE_NAME = "investment_identity"
"""production provider 注册的 identity/source Service 稳定名。"""

_REDIS_ADMISSION_TIMEOUT_MAX_SECONDS = 1.0
"""Redis connect/socket admission timeout 的固定最大秒数。"""


@dataclass(slots=True)
class _PreparedQueueAdmission:
    """durable queue 的 typed admission 与唯一 Redis lifecycle owner。

    Args:
        kind: profile 唯一派生的 admission 类型。
        queue_settings: durable runtime 数值设置；``NOT_REQUIRED`` 时为空。
        publisher: Redis admission 成功后的 Job hint publisher。
        subscriber_factory: Redis subscriber factory。
        redis_client: Redis health/lifecycle client。

    Raises:
        PlatformCompositionError: 字段组合不满足 closed admission 矩阵时抛出。
    """

    kind: PlatformQueueAdmissionKind
    queue_settings: PlatformQueueSettings | None
    publisher: JobWakeupPublisherProtocol | None = field(repr=False)
    subscriber_factory: RedisWakeupSubscriberFactoryProtocol | None = field(
        repr=False,
    )
    redis_client: RedisWakeupClientProtocol | None = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        """校验 admission closed shape。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformCompositionError: kind、settings 或 Redis 引用矩阵非法时
                抛出。
        """

        if not isinstance(self.kind, PlatformQueueAdmissionKind):
            raise PlatformCompositionError("queue admission kind 非法")
        if self.kind is PlatformQueueAdmissionKind.NOT_REQUIRED:
            if any(
                value is not None
                for value in (
                    self.queue_settings,
                    self.publisher,
                    self.subscriber_factory,
                    self.redis_client,
                )
            ):
                raise PlatformCompositionError("NOT_REQUIRED queue admission shape 非法")
            return
        if not isinstance(self.queue_settings, PlatformQueueSettings):
            raise PlatformCompositionError("durable queue admission 缺少严格 settings")
        if self.kind is PlatformQueueAdmissionKind.POSTGRES_ONLY:
            if self.queue_settings.mode is not PlatformQueueMode.POSTGRES_POLLING:
                raise PlatformCompositionError("POSTGRES_ONLY queue mode 非法")
            if any(
                value is not None
                for value in (
                    self.publisher,
                    self.subscriber_factory,
                    self.redis_client,
                )
            ):
                raise PlatformCompositionError("POSTGRES_ONLY 不得持有 Redis 引用")
            return
        if self.queue_settings.mode is not PlatformQueueMode.EVENT_ASSISTED:
            raise PlatformCompositionError("REDIS queue mode 非法")
        if (
            self.publisher is None
            or not isinstance(self.publisher, JobWakeupPublisherProtocol)
            or self.subscriber_factory is None
            or not isinstance(
                self.subscriber_factory,
                RedisWakeupSubscriberFactoryProtocol,
            )
            or self.redis_client is None
            or not isinstance(self.redis_client, RedisWakeupClientProtocol)
        ):
            raise PlatformCompositionError("REDIS queue admission 缺少 typed adapter")

    def close(self) -> None:
        """幂等关闭 admission 唯一持有的 Redis client。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: concrete adapter 报告程序类型错误时传播。
            ValueError: concrete adapter 报告程序值错误时传播。
        """

        if self._closed:
            return
        self._closed = True
        if self.redis_client is not None:
            self.redis_client.close()


def _not_required_queue_admission() -> _PreparedQueueAdmission:
    """构造 ordinary disabled/development 的 typed admission。

    Args:
        无。

    Returns:
        所有可选资源均为空的 ``NOT_REQUIRED`` admission。

    Raises:
        无。
    """

    return _PreparedQueueAdmission(
        kind=PlatformQueueAdmissionKind.NOT_REQUIRED,
        queue_settings=None,
        publisher=None,
        subscriber_factory=None,
        redis_client=None,
    )


class PreparedWorkspaceImportServiceProtocol(
    PlatformWorkspaceImportServiceProtocol,
    PlatformOwnedLifecycleProtocol,
    Protocol,
):
    """one-shot workspace import Service 契约（窄 + 幂等 close）。"""


@dataclass(frozen=True)
class PreparedHostAdminDependencies:
    """Host 管理子命令使用的轻量依赖集合。

    Args:
        paths: 启动期解析出的路径信息（供 CLI 展示）。
        host_admin_service: 已装配的宿主管理服务。
    """

    paths: StartupPaths
    host_admin_service: HostAdminService


@dataclass(frozen=True)
class PreparedWorkspaceImportDependencies:
    """one-shot workspace import 依赖集合（S15-CTRL-10）。

    Args:
        service: 窄 ``workspace_import`` Service（自持 one-shot engine）；
            ``close()`` 幂等释放。
    """

    service: PreparedWorkspaceImportServiceProtocol

    def close(self) -> None:
        """释放 one-shot 自持 engine（幂等）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.service.close()


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
        job_service: auto-provider 直接装配的 concrete ``JobService``；
            disabled/development 与 production 显式 provider 时为空。
        schedule_service: auto-provider 直接装配的 concrete
            ``ScheduleService``；与 ``job_service`` 同为空或同为非空。
        _queue_admission: 本次启动唯一 queue admission owner。
        _owned_platform_lifecycle: 成功态 auto-created provider 的
            atexit 协调器（private wrapper）；``close()`` 委托它协调
            manual close 与进程退出回调。无自持资源时为 ``None``。
        _owned_s3_store: 成功态 S3 模式独占持有的 S3 store（runtime 不
            重复 close）。
        _owned_writer_lease: 成功态 S3 模式独占持有的 writer lease。
    """

    workspace: WorkspaceResources
    default_execution_options: ResolvedExecutionOptions
    scene_execution_acceptance_preparer: SceneExecutionAcceptancePreparer
    host: Host
    fins_runtime: FinsRuntimeProtocol
    platform_composition: PlatformComposition[PlatformServiceProtocol] = field(
        default_factory=_default_platform_composition,
    )
    job_service: JobService | None = None
    schedule_service: ScheduleService | None = None
    _queue_admission: _PreparedQueueAdmission = field(
        default_factory=_not_required_queue_admission,
        repr=False,
        compare=False,
    )
    _owned_platform_lifecycle: _OwnedLifecycleRegistration | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _owned_s3_store: S3FileStore | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _owned_writer_lease: _OwnedS3LeaseRegistration | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def close(self) -> None:
        """释放成功态 auto-created 自持资源（幂等）。

        先关闭 Redis admission，再依次释放 writer lease、S3 store、
        platform lifecycle；manual close 先赢得 close 权并解除 atexit
        回调意图，之后进程退出时回调为 no-op。显式注入 provider、平台
        禁用与 development 路径仍由 typed NOT_REQUIRED admission 保持
        no-op。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._queue_admission.close()
        if self._owned_writer_lease is not None:
            self._owned_writer_lease.close()
        if self._owned_s3_store is not None:
            self._owned_s3_store.close()
        if self._owned_platform_lifecycle is not None:
            self._owned_platform_lifecycle.close()


@dataclass(frozen=True, slots=True)
class PreparedPlatformQueueRuntime:
    """Worker/Scheduler CLI 使用的 durable queue prepared runtime。

    Args:
        existing_runtime: 同一 private composition root 产出的 Host runtime。
        job_service: 直接持有的 concrete JobService gateway。
        schedule_service: 直接持有的 concrete ScheduleService gateway。
        queue_admission: ``POSTGRES_ONLY`` 或 ``REDIS`` typed admission。
        queue_settings: 与 admission 同一份 strict queue settings。

    Raises:
        PlatformCompositionError: service identity 或 admission/settings
            不闭合时抛出。
    """

    existing_runtime: PreparedHostRuntimeDependencies
    job_service: JobService
    schedule_service: ScheduleService
    queue_admission: _PreparedQueueAdmission = field(repr=False)
    queue_settings: PlatformQueueSettings

    def __post_init__(self) -> None:
        """验证 direct refs 与 existing runtime 逐字段闭合。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformCompositionError: 任一引用类型、identity 或 admission
                shape 不闭合时抛出。
        """

        if not isinstance(self.existing_runtime, PreparedHostRuntimeDependencies):
            raise PlatformCompositionError("platform queue runtime 缺少 existing runtime")
        if not isinstance(self.job_service, JobService):
            raise PlatformCompositionError("platform queue runtime 缺少 JobService")
        if not isinstance(self.schedule_service, ScheduleService):
            raise PlatformCompositionError("platform queue runtime 缺少 ScheduleService")
        if self.existing_runtime.job_service is not self.job_service:
            raise PlatformCompositionError("platform queue JobService identity 漂移")
        if self.existing_runtime.schedule_service is not self.schedule_service:
            raise PlatformCompositionError("platform queue ScheduleService identity 漂移")
        if self.existing_runtime._queue_admission is not self.queue_admission:
            raise PlatformCompositionError("platform queue admission identity 漂移")
        if self.queue_admission.kind is PlatformQueueAdmissionKind.NOT_REQUIRED:
            raise PlatformCompositionError("platform queue runtime 拒绝 NOT_REQUIRED")
        if self.queue_admission.queue_settings is not self.queue_settings:
            raise PlatformCompositionError("platform queue settings identity 漂移")

    def close(self) -> None:
        """幂等关闭 Redis admission 后释放 existing runtime。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: concrete Redis adapter 报告程序类型错误时传播。
            ValueError: concrete Redis adapter 报告程序值错误时传播。
        """

        self.queue_admission.close()
        self.existing_runtime.close()


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


@dataclass(frozen=True)
class _PlatformPreparation:
    """production 平台依赖的私有 preparation（阶段 1 产物）。

    Args:
        engine: 唯一 production engine。
        session_factory: 绑定该 engine 的 session factory。
        identity_repository: PostgreSQL identity/source repository。
        identity_service: 已装配的 ``InvestmentIdentityService``（同时是
            engine lifecycle owner）。
    """

    engine: Engine
    session_factory: sessionmaker[Session]
    identity_repository: PostgresIdentityRepository
    identity_service: InvestmentIdentityService


def _prepare_production_platform_dependencies(
    settings: PlatformSettings,
) -> _PlatformPreparation:
    """阶段 1：在 provider admission 位点准备 production 平台依赖。

    读取 DSN、创建并 probe 唯一 engine/session factory、构造
    ``PostgresIdentityRepository`` 与 ``InvestmentIdentityService``。
    本阶段任一失败时 Host/Fins 未构造且恰好 dispose engine 一次。

    Args:
        settings: 已解析的平台严格设置。

    Returns:
        只含 engine/session factory/repository/service 的私有 preparation。

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
    return _PlatformPreparation(
        engine=engine,
        session_factory=session_factory,
        identity_repository=repository,
        identity_service=service,
    )


def _build_production_services_provider(
    preparation: _PlatformPreparation,
    *,
    host_run_reader: HostRunReaderProtocol,
    host_run_canceller: HostRunCancellationProtocol,
    queue_settings: PlatformQueueSettings,
    wakeup_publisher: JobWakeupPublisherProtocol | None,
) -> _ProductionServicesProvider:
    """阶段 2：在 Host 构造成功后做内存装配并返回 production provider。

    只做内存装配：Job/Schedule Store 共享 session factory；Job/Schedule
    Service 共享唯一空 descriptor/execution registries 与 wakeup publisher；
    同一真实 Host 分别以 reader/canceller 窄协议注入 JobService。本阶段
    不连接 PG、不启动 thread/timer/connection/atexit，因而不会引入第二
    lifecycle owner。provider mapping 精确为 identity/jobs/schedules 三项。

    Args:
        preparation: 阶段 1 的私有 preparation。
        host_run_reader: 刚构造的真实 ``Host``（以其既有 ``get_run``
            结构满足 services-layer 协议）。
        host_run_canceller: 同一真实 ``Host`` 的 ``cancel_run`` 窄入口。
        queue_settings: 已通过 queue admission 的严格数值设置。
        wakeup_publisher: REDIS admission 的 best-effort publisher；
            POSTGRES_ONLY 时为空。

    Returns:
        精确注册 identity/jobs/schedules 的 concrete provider。

    Raises:
        无。
    """

    job_store = PostgresJobStore(session_factory=preparation.session_factory)
    schedule_store = PostgresScheduleStore(preparation.session_factory)
    descriptor_registry = JobHandlerRegistry()
    execution_registry = JobExecutionRegistry(descriptor_registry)
    job_service = JobService(
        job_store=job_store,
        descriptor_registry=descriptor_registry,
        host_run_reader=host_run_reader,
        execution_registry=execution_registry,
        runtime_adapters=JobServiceRuntimeAdapters(
            host_run_canceller=host_run_canceller,
            wakeup_publisher=wakeup_publisher,
        ),
    )
    schedule_service = ScheduleService(
        schedule_store=schedule_store,
        job_gateway=job_service,
        schedule_max_lookback_seconds=(
            queue_settings.schedule_max_lookback_seconds
        ),
        schedule_candidate_scan_limit=(
            queue_settings.schedule_candidate_scan_limit
        ),
    )
    return _ProductionServicesProvider(
        identity_service=preparation.identity_service,
        job_service=job_service,
        schedule_service=schedule_service,
    )


class _ProductionServicesProvider:
    """production services provider（精确注册 identity/jobs/schedules）。

    Args:
        identity_service: 阶段 1 装配的 identity Service。
        job_service: 阶段 2 装配的 ``JobService``。
        schedule_service: 阶段 2 装配的 ``ScheduleService``。
    """

    def __init__(
        self,
        *,
        identity_service: InvestmentIdentityService,
        job_service: JobService,
        schedule_service: ScheduleService,
    ) -> None:
        """初始化 provider。

        Args:
            identity_service: identity Service。
            job_service: durable job Service。
            schedule_service: durable schedule Service。

        Returns:
            无。

        Raises:
            无。
        """

        self._identity_service = identity_service
        self.job_service = job_service
        self.schedule_service = schedule_service

    def provide_services(self) -> Mapping[str, PlatformServiceProtocol]:
        """返回 production Service 映射。

        Args:
            无。

        Returns:
            identity/jobs/schedules 精确三项映射。

        Raises:
            无。
        """

        return {
            _INVESTMENT_IDENTITY_SERVICE_NAME: self._identity_service,
            DURABLE_JOBS_SERVICE_NAME: self.job_service,
            DURABLE_SCHEDULES_SERVICE_NAME: self.schedule_service,
        }


def _default_provider_or_fail(
    settings: PlatformSettings,
    queue_admission: _PreparedQueueAdmission,
    explicit_provider: PlatformCompositionProviderProtocol | None,
) -> tuple[
    PlatformCompositionProviderProtocol | None,
    PlatformOwnedLifecycleProtocol | None,
    _PlatformPreparation | None,
]:
    """解析组合提供者与自持生命周期。

    显式 provider 优先；未显式注入时 production 构造阶段 1 preparation
    （provider 延迟到 Host 构造后装配），development 保持 fail-fast（不
    假造 in-memory）。

    Args:
        settings: 已解析的平台严格设置。
        queue_admission: settings/profile 派生且已完成的 typed admission。
        explicit_provider: 显式注入的组合提供者（可空）。

    Returns:
        ``(provider, lifecycle, preparation)`` 三元组；provider 非
        ``None`` 表示可立即用于 composition；preparation 非 ``None``
        表示 production 阶段 1 已完成、provider 需在 Host 构造后经
        ``_build_production_services_provider`` 装配；lifecycle 为
        ``None`` 表示无自持资源。

    Raises:
        PlatformCompositionError: enabled + development 且未注入
            provider，或 production 阶段 1 初始化失败时抛出。
    """

    if explicit_provider is not None:
        return explicit_provider, None, None
    if not settings.enabled:
        return None, None, None
    if settings.profile in (
        PlatformDeploymentProfile.PRODUCTION,
        PlatformDeploymentProfile.INTEGRATION,
    ):
        if queue_admission.queue_settings is None:
            raise PlatformCompositionError("durable platform 缺少 queue admission")
        preparation = _prepare_production_platform_dependencies(settings)
        return None, preparation.identity_service, preparation
    raise PlatformCompositionError(
        "development 平台启用必须显式注入组合提供者，禁止用 PostgreSQL 冒充 in-memory"
    )


def _prepare_queue_admission(
    settings: PlatformSettings,
    queue_settings: PlatformQueueSettings | None,
) -> _PreparedQueueAdmission:
    """按已验证 profile/settings 完成唯一 queue admission。

    production REDIS 分支委托唯一 private helper local-import concrete
    adapter；import、client 构造与 ping 均发生在路径解析、S3、PG、Host 与
    workspace 副作用之前。integration 仅构造 typed
    ``POSTGRES_ONLY`` shape。

    Args:
        settings: 已通过严格 loader 的平台设置。
        queue_settings: 同一 profile 派生的 queue settings；ordinary
            disabled/development 路径为空。

    Returns:
        closed typed queue admission。

    Raises:
        PlatformCompositionError: profile/mode 不闭合、Redis package/client/
            ping admission 失败时抛出固定安全错误。
        PlatformSettingsError: Redis 环境变量名称或值缺失时抛出。
        TypeError: 已构造 Redis client 的程序类型错误传播。
        ValueError: 已构造 Redis client 的程序值错误传播。
    """

    if queue_settings is None:
        return _not_required_queue_admission()
    if not settings.enabled:
        raise PlatformCompositionError("durable queue runtime 要求平台启用")
    if settings.profile is PlatformDeploymentProfile.INTEGRATION:
        return _prepare_postgres_only_queue_admission(queue_settings)
    if (
        settings.profile is not PlatformDeploymentProfile.PRODUCTION
        or queue_settings.mode is not PlatformQueueMode.EVENT_ASSISTED
    ):
        raise PlatformCompositionError("queue profile/mode admission 非法")
    return _prepare_redis_queue_admission(settings, queue_settings)


def _prepare_postgres_only_queue_admission(
    queue_settings: PlatformQueueSettings,
) -> _PreparedQueueAdmission:
    """构造 integration profile 的 PostgreSQL-only admission。

    Args:
        queue_settings: 已按 integration profile 解析的严格队列设置。

    Returns:
        不持有 Redis 资源的 ``POSTGRES_ONLY`` admission。

    Raises:
        PlatformCompositionError: integration queue mode 非 PostgreSQL polling
            时抛出。
    """

    if queue_settings.mode is not PlatformQueueMode.POSTGRES_POLLING:
        raise PlatformCompositionError("integration queue mode 非法")
    return _PreparedQueueAdmission(
        kind=PlatformQueueAdmissionKind.POSTGRES_ONLY,
        queue_settings=queue_settings,
        publisher=None,
        subscriber_factory=None,
        redis_client=None,
    )


def _prepare_redis_queue_admission(
    settings: PlatformSettings,
    queue_settings: PlatformQueueSettings,
) -> _PreparedQueueAdmission:
    """完成 production Redis adapter 的唯一 admission。

    concrete adapter 仍只在本函数内延迟导入；环境变量读取、adapter
    构造与 ping 的先后顺序保持不变，失败消息不携带 Redis URL。

    Args:
        settings: 已验证为 production 的平台设置。
        queue_settings: 已验证为 event-assisted 的严格队列设置。

    Returns:
        唯一持有 Redis adapter 的 ``REDIS`` admission。

    Raises:
        PlatformCompositionError: Redis package、client 构造或 ping admission
            失败时抛出固定安全错误。
        PlatformSettingsError: Redis 环境变量名称或值缺失时抛出。
        TypeError: 已构造 Redis client 的程序类型错误传播。
        ValueError: 已构造 Redis client 的程序值错误传播。
    """

    redis_env_name = settings.redis_env
    if redis_env_name is None:
        raise PlatformSettingsError("production Redis 环境变量名称缺失")
    redis_url = os.environ.get(redis_env_name, "")
    if not redis_url or not redis_url.strip():
        raise PlatformSettingsError(f"环境变量 {redis_env_name} 缺失或为空")

    try:
        from dayu.host.redis_wakeup import (
            RedisWakeupAdapter,
            RedisWakeupUnavailableError,
        )
    except ModuleNotFoundError as error:
        if error.name is None or not error.name.startswith("redis"):
            raise
        raise PlatformCompositionError("production Redis queue admission failed") from None

    try:
        adapter = RedisWakeupAdapter.from_url(
            redis_url,
            timeout_seconds=min(
                queue_settings.poll_interval_seconds,
                _REDIS_ADMISSION_TIMEOUT_MAX_SECONDS,
            ),
        )
    except (RedisWakeupUnavailableError, ValueError):
        raise PlatformCompositionError("production Redis queue admission failed") from None
    if not adapter.ping():
        adapter.close()
        raise PlatformCompositionError("production Redis queue admission failed")
    publisher: JobWakeupPublisherProtocol = adapter
    subscriber_factory: RedisWakeupSubscriberFactoryProtocol = adapter
    redis_client: RedisWakeupClientProtocol = adapter
    try:
        return _PreparedQueueAdmission(
            kind=PlatformQueueAdmissionKind.REDIS,
            queue_settings=queue_settings,
            publisher=publisher,
            subscriber_factory=subscriber_factory,
            redis_client=redis_client,
        )
    except Exception:
        adapter.close()
        raise


@dataclass(frozen=True, slots=True)
class _HostRuntimePreparationRequest:
    """private composition root 的稳定启动输入。

    Args:
        workspace_root: 工作区根目录。
        config_root: 可选配置根目录。
        execution_options: 请求级执行选项。
        runtime_label: startup recovery 的运行时标签。
        log_module: recovery 日志模块名。
        platform_provider: 可选平台组合提供者。
    """

    workspace_root: Path
    config_root: Path | None
    execution_options: ExecutionOptions | None
    runtime_label: str
    log_module: str
    platform_provider: PlatformCompositionProviderProtocol | None


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


class _OwnedS3LeaseRegistration:
    """成功态 writer lease 的 atexit 协调器（S14-CTRL-05/09）。

    与 ``_OwnedLifecycleRegistration`` 同语义：初始化仅持有 lease，不注册
    atexit；由装配方在完整构造成功后显式 ``register()``（exact-once）。
    ``close()``（manual）无条件释放并解除注册意图；``_close_at_exit()``
    仅在已注册且未被手动 close 时执行一次。
    """

    def __init__(self, lease: WriterLease) -> None:
        """持有 lease 并初始化为未注册、未关闭状态。

        Args:
            lease: 已获取的 writer lease。

        Returns:
            无。

        Raises:
            无。
        """

        self._lease = lease
        self._registered = False
        self._closed = False

    def register(self) -> None:
        """注册 atexit 回调（exact-once）。

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
        """atexit 回调：仅当已注册且未被手动 close 时执行一次。

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
        self._lease.release()

    def close(self) -> None:
        """手动 close 并解除 atexit 注册意图（幂等）。

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
        self._lease.release()


def _should_build_s3_store(settings: PlatformSettings) -> bool:
    """判断是否应构建 S3 store（production + enabled + 配置了对象存储）。

    Args:
        settings: 已解析的平台严格设置。

    Returns:
        production 且平台 enabled 且配置了 ``object_storage_env`` 时返回
        ``True``；否则返回 ``False``（development/in-memory 与
        platform-disabled 路径继续使用 FS）。

    Raises:
        无。
    """

    if not settings.enabled:
        return False
    if settings.profile is not PlatformDeploymentProfile.PRODUCTION:
        return False
    return settings.object_storage_env is not None


def _build_s3_store_from_settings(env: Mapping[str, str], settings: PlatformSettings) -> S3FileStore:
    """按平台严格设置构建唯一 S3FileStore（S14-CTRL-02/05）。

    Args:
        env: 进程环境变量映射。
        settings: 已解析的平台严格设置。

    Returns:
        已构造并完成 head_bucket 探活的 S3 store。

    Raises:
        S3SettingsError: 配置解析或凭证读取失败时抛出。
        FileNotFoundError: bucket 不存在时抛出。
        OSError: head_bucket 无权限/不可达时抛出。
    """

    object_storage_env = settings.object_storage_env
    if object_storage_env is None:
        raise S3SettingsError("对象存储环境变量未配置")
    parsed = parse_object_storage_settings(env, object_storage_env)
    credentials = read_credentials(env, parsed)
    store = S3FileStore(
        endpoint_url=parsed.endpoint_url,
        region=parsed.region,
        bucket=parsed.bucket,
        access_key=credentials.access_key,
        secret_key=credentials.secret_key,
    )
    store.head_bucket()
    return store


def prepare_host_runtime_dependencies(
    *,
    workspace_root: Path,
    config_root: Path | None,
    execution_options: ExecutionOptions | None,
    runtime_label: str,
    log_module: str,
    platform_provider: PlatformCompositionProviderProtocol | None = None,
) -> PreparedHostRuntimeDependencies:
    """准备 CLI / WeChat 共用的 ordinary Host 运行时依赖。

    本 wrapper 只负责一次 settings/profile 解析与 queue admission，然后
    精确调用唯一 private composition root 一次。ordinary startup 拒绝
    integration；production 即使显式注入 provider 也必须先完成 Redis
    admission，不能绕过。

    Args:
        workspace_root: 工作区根目录。
        config_root: 可选配置根目录。
        execution_options: 请求级执行选项。
        runtime_label: startup recovery 的运行时标签。
        log_module: recovery 日志模块名。
        platform_provider: 可选平台组合提供者。

    Returns:
        已完成 Host、Fins 与可选平台组合装配的共享依赖集合。

    Raises:
        PlatformSettingsError: settings/profile/queue 数值非法，或 ordinary
            startup 收到 integration profile 时抛出。
        PlatformCompositionError: Redis admission 或平台组合失败时抛出。
        组合提供者自身异常原样传播。
    """

    platform_settings = load_platform_settings(os.environ)
    if platform_settings.profile is PlatformDeploymentProfile.INTEGRATION:
        raise PlatformSettingsError("ordinary startup 不接受 integration profile")
    queue_settings = (
        load_platform_queue_settings(os.environ, platform_settings.profile)
        if platform_settings.enabled
        and platform_settings.profile is PlatformDeploymentProfile.PRODUCTION
        else None
    )
    queue_admission = _prepare_queue_admission(
        platform_settings,
        queue_settings,
    )
    return _prepare_host_runtime_after_queue_admission(
        platform_settings=platform_settings,
        queue_admission=queue_admission,
        request=_HostRuntimePreparationRequest(
            workspace_root=workspace_root,
            config_root=config_root,
            execution_options=execution_options,
            runtime_label=runtime_label,
            log_module=log_module,
            platform_provider=platform_provider,
        ),
    )


def prepare_platform_queue_runtime_dependencies(
    *,
    workspace_root: Path,
    config_root: Path | None,
    execution_options: ExecutionOptions | None,
    runtime_label: str,
    log_module: str,
) -> PreparedPlatformQueueRuntime:
    """准备 Worker/Scheduler 共用的 durable platform queue runtime。

    本 wrapper 只接受启用的 production/integration profile，完成一次
    REDIS/POSTGRES_ONLY admission 后精确调用与 ordinary startup 相同的
    private composition root；绝不二次调用 ordinary wrapper。

    Args:
        workspace_root: 工作区根目录。
        config_root: 可选配置根目录。
        execution_options: Host runtime 的请求级执行选项。
        runtime_label: startup recovery 的运行时标签。
        log_module: recovery 日志模块名。

    Returns:
        直接持有 concrete Job/Schedule Service、typed admission/settings
        与 existing Host runtime 的 durable prepared runtime。

    Raises:
        PlatformSettingsError: 平台未启用、profile 非 production/
            integration，或 queue settings 非法时抛出。
        PlatformCompositionError: queue admission、auto-provider 或 direct
            service refs 不闭合时抛出。
    """

    platform_settings = load_platform_settings(os.environ)
    if not platform_settings.enabled:
        raise PlatformSettingsError("platform queue runtime 要求平台启用")
    if platform_settings.profile not in (
        PlatformDeploymentProfile.PRODUCTION,
        PlatformDeploymentProfile.INTEGRATION,
    ):
        raise PlatformSettingsError(
            "platform queue runtime 只接受 production / integration profile"
        )
    queue_settings = load_platform_queue_settings(
        os.environ,
        platform_settings.profile,
    )
    if queue_settings is None:
        raise PlatformSettingsError("platform queue runtime 缺少 queue settings")
    queue_admission = _prepare_queue_admission(
        platform_settings,
        queue_settings,
    )
    existing_runtime = _prepare_host_runtime_after_queue_admission(
        platform_settings=platform_settings,
        queue_admission=queue_admission,
        request=_HostRuntimePreparationRequest(
            workspace_root=workspace_root,
            config_root=config_root,
            execution_options=execution_options,
            runtime_label=runtime_label,
            log_module=log_module,
            platform_provider=None,
        ),
    )
    job_service = existing_runtime.job_service
    schedule_service = existing_runtime.schedule_service
    if job_service is None or schedule_service is None:
        existing_runtime.close()
        raise PlatformCompositionError("platform queue runtime direct services 缺失")
    try:
        return PreparedPlatformQueueRuntime(
            existing_runtime=existing_runtime,
            job_service=job_service,
            schedule_service=schedule_service,
            queue_admission=queue_admission,
            queue_settings=queue_settings,
        )
    except Exception:
        existing_runtime.close()
        raise


def _prepare_host_runtime_after_queue_admission(
    *,
    platform_settings: PlatformSettings,
    queue_admission: _PreparedQueueAdmission,
    request: _HostRuntimePreparationRequest,
) -> PreparedHostRuntimeDependencies:
    """唯一 private composition root：在 queue admission 后装配 Host。

    Args:
        platform_settings: public wrapper 已读取并验证的平台设置。
        queue_admission: public wrapper 已完成的 typed queue admission。
        request: 工作区、配置、执行选项、recovery 标签与可选 provider 的
            稳定启动输入。

    Returns:
        已完成 Host、scene preparation、fins runtime 与平台组合装配的
        共享依赖集合。

    Raises:
        PlatformCompositionError: 平台启用但未注入组合提供者、提供者
            不满足协议，或提供者产出的 service 注册违反组合契约时
            抛出。
        组合提供者自身抛出的异常原样传播，且必发生在任何 Host / Fins
        副作用之前。
    """

    if not isinstance(platform_settings, PlatformSettings):
        queue_admission.close()
        raise PlatformCompositionError("private composition root settings 非法")
    if not isinstance(queue_admission, _PreparedQueueAdmission):
        raise PlatformCompositionError("private composition root admission 非法")
    lifecycle_registration: _OwnedLifecycleRegistration | None = None
    s3_store: S3FileStore | None = None
    lease_registration: _OwnedS3LeaseRegistration | None = None
    owned_lifecycle: PlatformOwnedLifecycleProtocol | None = None
    platform_preparation: _PlatformPreparation | None = None
    job_service: JobService | None = None
    schedule_service: ScheduleService | None = None
    try:
        # queue admission 已先完成；此后才允许 read-only path resolution。
        # path resolution 也属于构造期，因此必须在 failure-close 边界内。
        paths = resolve_startup_paths(
            workspace_root=request.workspace_root,
            config_root=request.config_root,
        )
        # S14-CTRL-05 固定顺序：load settings -> resolve paths -> S3 admission/head ->
        # lease + build_fs_repository_set(recovery) -> provider preparation -> Host ->
        # 阶段 2 services provider -> composition -> startup recovery。
        # S3 admission 在任何 provider/workspace/HostStore side effect 之前完成。
        s3_active = _should_build_s3_store(platform_settings)
        if s3_active:
            s3_store = _build_s3_store_from_settings(os.environ, platform_settings)
            lease = acquire_writer_lease(paths.workspace_root)
            lease_registration = _OwnedS3LeaseRegistration(lease)
            repository_set = build_fs_repository_set(
                workspace_root=paths.workspace_root,
                file_store=s3_store,
            )
        else:
            repository_set = None
        resolved_provider, owned_lifecycle, platform_preparation = _default_provider_or_fail(
            platform_settings,
            queue_admission,
            request.platform_provider,
        )
        platform_composition: PlatformComposition[PlatformServiceProtocol]
        if resolved_provider is not None:
            # 显式注入 / 平台禁用路径：composition 可在任何 Host 副作用前构建。
            platform_composition = build_platform_composition(
                settings=platform_settings,
                provider=resolved_provider,
            )
        else:
            platform_composition = _default_platform_composition()
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
            execution_options=request.execution_options,
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
            repository_set=repository_set,
            cn_download_pdf_gate=GovernorCnDownloadPdfGate(
                governor=SQLiteConcurrencyGovernor(
                    pdf_gate_host_store,
                    lane_config=host_config.lane_config,
                )
            ),
        )
        fins_toolset_overrides = build_fins_toolset_registrars(fins_runtime)
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
            toolset_registrar_overrides=fins_toolset_overrides,
        )
        if platform_preparation is not None:
            # 阶段 2：Host 构造成功后、startup recovery 前装配 production
            # services provider 并构建最终 composition。
            queue_settings = queue_admission.queue_settings
            if queue_settings is None:
                raise PlatformCompositionError("auto-provider 缺少 queue settings")
            services_provider = _build_production_services_provider(
                platform_preparation,
                host_run_reader=host,
                host_run_canceller=host,
                queue_settings=queue_settings,
                wakeup_publisher=queue_admission.publisher,
            )
            job_service = services_provider.job_service
            schedule_service = services_provider.schedule_service
            platform_composition = build_platform_composition(
                settings=platform_settings,
                provider=services_provider,
            )
        recover_host_startup_state(
            HostAdminService(host=host),
            runtime_label=request.runtime_label,
            log_module=request.log_module,
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
            job_service=job_service,
            schedule_service=schedule_service,
            _queue_admission=queue_admission,
            _owned_platform_lifecycle=lifecycle_registration,
            _owned_s3_store=s3_store,
            _owned_writer_lease=lease_registration,
        )
        if lifecycle_registration is not None:
            lifecycle_registration.register()
        if lease_registration is not None:
            lease_registration.register()
        return prepared
    except Exception:
        if lifecycle_registration is not None:
            lifecycle_registration.close()
        elif owned_lifecycle is not None:
            owned_lifecycle.close()
        if lease_registration is not None:
            lease_registration.close()
        if s3_store is not None:
            s3_store.close()
        queue_admission.close()
        raise


def prepare_workspace_import_dependencies() -> PreparedWorkspaceImportDependencies:
    """为 one-shot workspace import mode 装配单例 PostgreSQL 依赖。

    只做：读取既有 strict production platform settings/DSN、probe app
    role admission、构造一个 engine/session/repository/service 与幂等
    close owner。失败即 dispose 且消息不含 DSN。

    本入口不启动 Host/Fins runtime、S3、Redis、auth、model，也不把
    migration service 注册进普通 Host runtime composition。

    Args:
        无。

    Returns:
        携带窄 ``workspace_import`` Service 的 one-shot 依赖集合。

    Raises:
        WorkspaceImportRepositoryFailureError: 平台未启用/非 production、
            DSN 缺失、app role admission 失败或 engine/repository/
            service 构造失败时抛出（不泄漏 DSN）。
    """

    settings = load_platform_settings(os.environ)
    if not settings.enabled or settings.profile is not PlatformDeploymentProfile.PRODUCTION:
        raise WorkspaceImportRepositoryFailureError()
    engine: Engine | None = None
    try:
        dsn = _read_postgres_dsn(settings)
        engine = create_platform_engine(dsn)
        _probe_production_engine(engine)
        session_factory = create_platform_session_factory(engine)
        repository = PostgresWorkspaceImportRepository(session_factory)
        service = WorkspaceImportService(
            import_repository=repository,
            owned_engine=engine,
        )
    except WorkspaceImportRepositoryFailureError:
        if engine is not None:
            engine.dispose()
        raise
    except Exception:
        if engine is not None:
            engine.dispose()
        raise WorkspaceImportRepositoryFailureError() from None
    return PreparedWorkspaceImportDependencies(service=service)


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
    "PreparedPlatformQueueRuntime",
    "PreparedWorkspaceImportDependencies",
    "prepare_host_admin_dependencies",
    "prepare_host_runtime_dependencies",
    "prepare_platform_queue_runtime_dependencies",
    "prepare_scene_execution_acceptance_preparer",
    "prepare_workspace_import_dependencies",
]
