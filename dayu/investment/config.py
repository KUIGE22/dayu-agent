"""投资平台严格配置定义。

本模块定义投资平台的部署配置契约，保持纯标准库依赖、不依赖任何上层包：

- 配置只记录环境变量名称（env name），绝不记录或回显 secret 值；
  即使对 ``PlatformSettings`` 做调试快照，也只能看到环境变量名。
- production 部署启用平台时，缺少 DSN / 对象存储 / Redis / auth key
  任一环境变量即构造期 fail-fast，且禁止使用 in-memory adapters。
- integration 部署（只供测试/本地 durable integration）启用平台时，
  必须且只允许配置 PostgreSQL DSN 环境变量，object storage / Redis /
  auth 任一非空即 fail-fast。
- development 部署启用平台时必须显式选择 in-memory adapters，
  禁止混用 production 基础设施环境变量，防止误连真实持久化设施。
- ``PlatformQueueSettings`` 只供 PRODUCTION/INTEGRATION durable queue
  runtime 构造：profile -> queue mode / admission kind 映射由 loader
  唯一决定，用户无自由 mode/admission 字符串；所有数值严格校验，
  candidate scan limit 下限由 lookback 与 timezone offset 边界推导。

环境变量开关与名称是固定契约，由本模块常量声明；具体取值由后续
slice 的 provider 读取，本模块只记录"名称已配置"这一事实。
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

DAYU_PLATFORM_ENABLED_ENV = "DAYU_PLATFORM_ENABLED"
DAYU_PLATFORM_PROFILE_ENV = "DAYU_PLATFORM_PROFILE"
DAYU_PLATFORM_USE_IN_MEMORY_ENV = "DAYU_PLATFORM_USE_IN_MEMORY"
DAYU_PLATFORM_POSTGRES_DSN_ENV = "DAYU_PLATFORM_POSTGRES_DSN"
DAYU_PLATFORM_OBJECT_STORAGE_ENV = "DAYU_PLATFORM_OBJECT_STORAGE"
DAYU_PLATFORM_REDIS_ENV = "DAYU_PLATFORM_REDIS_URL"
DAYU_PLATFORM_AUTH_KEY_ENV = "DAYU_PLATFORM_AUTH_KEY"

DAYU_PLATFORM_QUEUE_POLL_INTERVAL_SECONDS = "DAYU_PLATFORM_QUEUE_POLL_INTERVAL_SECONDS"
DAYU_PLATFORM_QUEUE_REDIS_HEALTH_INTERVAL_SECONDS = "DAYU_PLATFORM_QUEUE_REDIS_HEALTH_INTERVAL_SECONDS"
DAYU_PLATFORM_QUEUE_REDIS_FAILURE_THRESHOLD = "DAYU_PLATFORM_QUEUE_REDIS_FAILURE_THRESHOLD"
DAYU_PLATFORM_QUEUE_SHUTDOWN_GRACE_SECONDS = "DAYU_PLATFORM_QUEUE_SHUTDOWN_GRACE_SECONDS"
DAYU_PLATFORM_QUEUE_EMPTY_POLL_JITTER_MAX_SECONDS = "DAYU_PLATFORM_QUEUE_EMPTY_POLL_JITTER_MAX_SECONDS"
DAYU_PLATFORM_SCHEDULE_MAX_LOOKBACK_SECONDS = "DAYU_PLATFORM_SCHEDULE_MAX_LOOKBACK_SECONDS"
DAYU_PLATFORM_SCHEDULE_CANDIDATE_SCAN_LIMIT = "DAYU_PLATFORM_SCHEDULE_CANDIDATE_SCAN_LIMIT"
DAYU_PLATFORM_SCHEDULE_TICK_BATCH_SIZE = "DAYU_PLATFORM_SCHEDULE_TICK_BATCH_SIZE"
DAYU_PLATFORM_QUEUE_GOVERNANCE_PAGE_SIZE = "DAYU_PLATFORM_QUEUE_GOVERNANCE_PAGE_SIZE"
DAYU_PLATFORM_QUEUE_GOVERNANCE_FAILURE_THRESHOLD = "DAYU_PLATFORM_QUEUE_GOVERNANCE_FAILURE_THRESHOLD"

_TRUE_TOKENS: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")

_SCAN_LIMIT_TIMEZONE_OFFSET_MARGIN = 2880
"""Python timezone offset 两端严格小于 24 小时所允许的最坏 naive-local
跨度差（分钟），另 2 覆盖 boundary/future candidate。"""


class PlatformDeploymentProfile(Enum):
    """平台部署环境。"""

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    INTEGRATION = "integration"


class PlatformQueueMode(Enum):
    """durable queue 的部署级模式（由 profile 唯一派生）。

    ``EVENT_ASSISTED`` 只在 production 使用，Redis hint 只提前结束
    PG poll 等待；``POSTGRES_POLLING`` 只在 integration 使用，绝不
    构造/调用任何 Redis 对象。
    """

    EVENT_ASSISTED = "event_assisted"
    POSTGRES_POLLING = "postgres_polling"


class PlatformQueueAdmissionKind(Enum):
    """queue 启动 admission 的闭合类型。

    - ``NOT_REQUIRED``：disabled / development ordinary startup，不
      构造 queue settings，也不要求 Redis；
    - ``POSTGRES_ONLY``：integration platform runtime，只允许
      PostgreSQL DSN，Redis 引用全部为 ``None``；
    - ``REDIS``：production platform runtime，Redis package/client/
      ping admission 必须早于任何 PG/Host/workspace 副作用。
    """

    NOT_REQUIRED = "not_required"
    POSTGRES_ONLY = "postgres_only"
    REDIS = "redis"


class PlatformSettingsError(ValueError):
    """平台设置非法时抛出的错误。"""


@dataclass(frozen=True, slots=True)
class PlatformQueueSettings:
    """durable queue runtime 的严格数值设置。

    只供 PRODUCTION/INTEGRATION durable runtime 构造；``mode`` 由
    loader 依 profile 唯一派生，用户不得自由指定 mode 字符串。所有
    float 必须是 exact int/float（拒 bool）、``math.isfinite`` 且为正；
    threshold/lookback/candidate-scan-limit/tick-batch-size/page-size
    必须为 exact positive int。``schedule_candidate_scan_limit`` 的下限
    固定为 ``ceil(schedule_max_lookback_seconds / 60) + 2882``，其中
    2880 覆盖 Python timezone offset 两端的最坏 naive-local 跨度差，
    另 2 覆盖 boundary/future candidate；默认 7 日 lookback 的最小值
    为 12962，默认 20000 合法，改变 lookback 使下限不满足时 fail-fast。

    Args:
        mode: queue 部署模式（由 loader 依 profile 唯一派生）。
        poll_interval_seconds: 无 hint/无 due 时的 PG poll 间隔秒数。
        redis_health_interval_seconds: polling_degraded 状态下 Redis
            探活间隔秒数。
        redis_failure_threshold: 连续失败达到该阈值才从 event_assisted
            降级为 polling_degraded。
        shutdown_grace_seconds: 停止 intake 后的协作式 soft grace 秒数。
        empty_poll_jitter_max_seconds: 空 poll 本地等待 jitter 上界秒数。
        schedule_max_lookback_seconds: schedule 允许回看的最老秒数。
        schedule_candidate_scan_limit: croniter 每次产出的 raw
            naive-local candidate 计数上限（含 DST 分类前的 invalid
            candidate）。
        schedule_tick_batch_size: scheduler 每 tick 最多执行的 Service
            gateway work unit 数量。
        governance_page_size: Worker 每 poll 处理的 governance 页大小。
        governance_failure_threshold: 连续 governance repository failure
            达到该阈值时 runtime 必须安全停止。
    """

    mode: PlatformQueueMode
    poll_interval_seconds: float = 5.0
    redis_health_interval_seconds: float = 30.0
    redis_failure_threshold: int = 3
    shutdown_grace_seconds: float = 30.0
    empty_poll_jitter_max_seconds: float = 1.0
    schedule_max_lookback_seconds: int = 604800
    schedule_candidate_scan_limit: int = 20000
    schedule_tick_batch_size: int = 100
    governance_page_size: int = 100
    governance_failure_threshold: int = 3

    def __post_init__(self) -> None:
        """构造期执行严格数值校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformSettingsError: 任一数值/模式违反严格规则时抛出。
        """

        if not isinstance(self.mode, PlatformQueueMode):
            raise PlatformSettingsError("mode 必须是 PlatformQueueMode 枚举值")
        _require_positive_finite_number(self.poll_interval_seconds, "poll_interval_seconds")
        _require_positive_finite_number(self.redis_health_interval_seconds, "redis_health_interval_seconds")
        _require_positive_finite_number(self.shutdown_grace_seconds, "shutdown_grace_seconds")
        _require_positive_finite_number(self.empty_poll_jitter_max_seconds, "empty_poll_jitter_max_seconds")
        _require_positive_exact_int(self.redis_failure_threshold, "redis_failure_threshold")
        _require_positive_exact_int(self.schedule_max_lookback_seconds, "schedule_max_lookback_seconds")
        _require_positive_exact_int(self.schedule_candidate_scan_limit, "schedule_candidate_scan_limit")
        _require_positive_exact_int(self.schedule_tick_batch_size, "schedule_tick_batch_size")
        _require_positive_exact_int(self.governance_page_size, "governance_page_size")
        _require_positive_exact_int(self.governance_failure_threshold, "governance_failure_threshold")
        minimum_scan_limit = math.ceil(self.schedule_max_lookback_seconds / 60) + _SCAN_LIMIT_TIMEZONE_OFFSET_MARGIN + 2
        if self.schedule_candidate_scan_limit < minimum_scan_limit:
            raise PlatformSettingsError(
                "schedule_candidate_scan_limit 必须不小于 ceil(schedule_max_lookback_seconds / 60) + 2882"
            )


def _require_positive_finite_number(value: int | float, label: str) -> None:
    """校验值为 exact int/float（拒 bool）、有限且为正。

    Args:
        value: 待校验数值。
        label: 错误消息中的中文字段名。

    Returns:
        无。

    Raises:
        PlatformSettingsError: 值非 exact int/float、为 bool、非有限
            或不大于 0 时抛出。
    """

    if type(value) not in (int, float):
        raise PlatformSettingsError(f"{label} 必须是 exact int/float")
    if not math.isfinite(float(value)) or value <= 0:
        raise PlatformSettingsError(f"{label} 必须是有限正数")


def _require_positive_exact_int(value: int, label: str) -> None:
    """校验值为 exact positive int（拒 bool 与 float 冒充）。

    Args:
        value: 待校验整数。
        label: 错误消息中的中文字段名。

    Returns:
        无。

    Raises:
        PlatformSettingsError: 值不是 exact ``int`` 或不大于 0 时抛出。
    """

    if type(value) is not int or value <= 0:
        raise PlatformSettingsError(f"{label} 必须是正整数")


def _read_queue_positive_float(
    env: Mapping[str, str],
    env_var: str,
    default: float,
) -> float:
    """读取并严格解析一个正的有限 float 环境变量。

    Args:
        env: 环境变量映射。
        env_var: 环境变量名称。
        default: 未设置或空值时的默认值。

    Returns:
        解析后的正有限 float。

    Raises:
        PlatformSettingsError: 值非法（非数字、NaN/Infinity、非正）时
            抛出；消息不回显候选值。
    """

    raw_value = env.get(env_var, "").strip()
    if not raw_value:
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        raise PlatformSettingsError(f"环境变量 {env_var} 必须是正有限数字") from None
    _require_positive_finite_number(parsed, env_var)
    return parsed


def _read_queue_positive_int(env: Mapping[str, str], env_var: str, default: int) -> int:
    """读取并严格解析一个 positive int 环境变量。

    Args:
        env: 环境变量映射。
        env_var: 环境变量名称。
        default: 未设置或空值时的默认值。

    Returns:
        解析后的 positive int。

    Raises:
        PlatformSettingsError: 值非法（非整数、非正）时抛出；消息不
            回显候选值。
    """

    raw_value = env.get(env_var, "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        raise PlatformSettingsError(f"环境变量 {env_var} 必须是正整数") from None
    _require_positive_exact_int(parsed, env_var)
    return parsed


def load_platform_queue_settings(
    env: Mapping[str, str],
    profile: PlatformDeploymentProfile,
) -> PlatformQueueSettings | None:
    """按 profile 唯一派生并加载 durable queue settings。

    development 返回 ``None``（NOT_REQUIRED admission，不构造 durable
    CLI）；production 派生 ``EVENT_ASSISTED``、integration 派生
    ``POSTGRES_POLLING``。mode/admission 映射只在本函数决定。

    Args:
        env: 环境变量映射（通常是进程环境）。
        profile: 已校验的部署环境。

    Returns:
        非 development 时返回严格校验后的 ``PlatformQueueSettings``；
        development 时返回 ``None``。

    Raises:
        PlatformSettingsError: profile 非法或任一 queue 环境变量非法时
            抛出。
    """

    if not isinstance(profile, PlatformDeploymentProfile):
        raise PlatformSettingsError("profile 必须是 PlatformDeploymentProfile 枚举值")
    if profile is PlatformDeploymentProfile.DEVELOPMENT:
        return None
    mode = (
        PlatformQueueMode.EVENT_ASSISTED
        if profile is PlatformDeploymentProfile.PRODUCTION
        else PlatformQueueMode.POSTGRES_POLLING
    )
    return PlatformQueueSettings(
        mode=mode,
        poll_interval_seconds=_read_queue_positive_float(env, DAYU_PLATFORM_QUEUE_POLL_INTERVAL_SECONDS, 5.0),
        redis_health_interval_seconds=_read_queue_positive_float(
            env, DAYU_PLATFORM_QUEUE_REDIS_HEALTH_INTERVAL_SECONDS, 30.0
        ),
        redis_failure_threshold=_read_queue_positive_int(env, DAYU_PLATFORM_QUEUE_REDIS_FAILURE_THRESHOLD, 3),
        shutdown_grace_seconds=_read_queue_positive_float(env, DAYU_PLATFORM_QUEUE_SHUTDOWN_GRACE_SECONDS, 30.0),
        empty_poll_jitter_max_seconds=_read_queue_positive_float(
            env, DAYU_PLATFORM_QUEUE_EMPTY_POLL_JITTER_MAX_SECONDS, 1.0
        ),
        schedule_max_lookback_seconds=_read_queue_positive_int(
            env, DAYU_PLATFORM_SCHEDULE_MAX_LOOKBACK_SECONDS, 604800
        ),
        schedule_candidate_scan_limit=_read_queue_positive_int(env, DAYU_PLATFORM_SCHEDULE_CANDIDATE_SCAN_LIMIT, 20000),
        schedule_tick_batch_size=_read_queue_positive_int(env, DAYU_PLATFORM_SCHEDULE_TICK_BATCH_SIZE, 100),
        governance_page_size=_read_queue_positive_int(env, DAYU_PLATFORM_QUEUE_GOVERNANCE_PAGE_SIZE, 100),
        governance_failure_threshold=_read_queue_positive_int(env, DAYU_PLATFORM_QUEUE_GOVERNANCE_FAILURE_THRESHOLD, 3),
    )


def build_queue_startup_snapshot(
    *,
    profile: PlatformDeploymentProfile,
    queue_settings: PlatformQueueSettings,
    tenant_id: str,
    process_label: str,
) -> dict[str, str | int | float | bool | tuple[str, ...]]:
    """构建 durable queue 启动的安全 snapshot。

    snapshot 只记录 profile/mode、queue 数值、Redis 环境变量**名称**、
    tenant id 与 process id label；绝不记录 Redis URL/DSN/auth 值、
    payload/token、hostname 环境或原始异常。``mode`` 与 Redis 环境
    变量名称 tuple 都从 closed profile/admission 唯一派生：与
    ``queue_settings.mode`` 矛盾即 fail-fast；调用方无法传入 raw
    URL/secret/换行值。``process_label`` 必须是非空、无首尾空白、无
    换行、无 URL marker 且不含敏感标记的安全标签。

    Args:
        profile: 已校验的部署环境。
        queue_settings: 已校验的 queue settings。
        tenant_id: canonical tenant UUID 字符串。
        process_label: 进程身份标签（worker/scheduler + 生成 id）。

    Returns:
        可安全记录/输出的 snapshot 字典。

    Raises:
        PlatformSettingsError: profile/mode 矛盾、queue_settings 类型
            非法或 process_label 不安全时抛出。
        ValueError: tenant_id 不是 canonical UUID 时抛出。
    """

    if not isinstance(queue_settings, PlatformQueueSettings):
        raise PlatformSettingsError("queue_settings 必须是 PlatformQueueSettings 实例")
    if profile is PlatformDeploymentProfile.PRODUCTION:
        expected_mode = PlatformQueueMode.EVENT_ASSISTED
        redis_env_names = (DAYU_PLATFORM_REDIS_ENV,)
    elif profile is PlatformDeploymentProfile.INTEGRATION:
        expected_mode = PlatformQueueMode.POSTGRES_POLLING
        redis_env_names = ()
    else:
        raise PlatformSettingsError("queue startup snapshot 只接受 production / integration profile")
    if queue_settings.mode is not expected_mode:
        raise PlatformSettingsError("queue_settings.mode 与 profile 派生 mode 矛盾")
    if type(tenant_id) is not str:
        raise ValueError("tenant_id 必须是规范 UUID 字符串")
    parsed_tenant = UUID(tenant_id)
    if str(parsed_tenant) != tenant_id or parsed_tenant.int == 0:
        raise ValueError("tenant_id 必须是规范 UUID")
    _require_safe_process_label(process_label)
    return {
        "profile": profile.value,
        "mode": queue_settings.mode.value,
        "poll_interval_seconds": queue_settings.poll_interval_seconds,
        "redis_health_interval_seconds": queue_settings.redis_health_interval_seconds,
        "redis_failure_threshold": queue_settings.redis_failure_threshold,
        "shutdown_grace_seconds": queue_settings.shutdown_grace_seconds,
        "empty_poll_jitter_max_seconds": queue_settings.empty_poll_jitter_max_seconds,
        "schedule_max_lookback_seconds": queue_settings.schedule_max_lookback_seconds,
        "schedule_candidate_scan_limit": queue_settings.schedule_candidate_scan_limit,
        "schedule_tick_batch_size": queue_settings.schedule_tick_batch_size,
        "governance_page_size": queue_settings.governance_page_size,
        "governance_failure_threshold": queue_settings.governance_failure_threshold,
        "redis_env_names": redis_env_names,
        "tenant_id": tenant_id,
        "process_label": process_label,
    }


_SAFE_PROCESS_LABEL_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)
"""进程身份标签允许的安全字符集合（拒 URL/换行/空白/敏感形态）。"""

_SAFE_PROCESS_LABEL_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "://",
    "password",
    "secret",
    "token",
    "apikey",
    "api_key",
    "authorization",
)
"""进程身份标签拒绝的 URL marker 与敏感标记子串。"""

_MAX_PROCESS_LABEL_LENGTH = 64
"""进程身份标签允许的最大字符数。"""


def _require_safe_process_label(label: str) -> None:
    """校验进程身份标签为安全形态（非空、无空白/换行、无 URL/敏感标记）。

    Args:
        label: 待校验的进程身份标签。

    Returns:
        无。

    Raises:
        PlatformSettingsError: 标签为空、含首尾空白、含换行、含非法
            字符或含 URL/敏感标记时抛出。
    """

    if not isinstance(label, str) or not label or label != label.strip() or any(ch in label for ch in "\r\n\t"):
        raise PlatformSettingsError("process_label 必须是非空且无空白/换行的字符串")
    if len(label) > _MAX_PROCESS_LABEL_LENGTH:
        raise PlatformSettingsError("process_label 长度不得超过 64")
    if any(ch not in _SAFE_PROCESS_LABEL_CHARS for ch in label):
        raise PlatformSettingsError("process_label 只允许字母/数字/下划线/连字符")
    lowered = label.lower()
    if any(marker in lowered for marker in _SAFE_PROCESS_LABEL_FORBIDDEN_SUBSTRINGS):
        raise PlatformSettingsError("process_label 不得包含 URL 或敏感标记")


@dataclass(frozen=True)
class PlatformSettings:
    """投资平台严格设置（只记录环境变量名称）。

    Args:
        enabled: 平台是否启用。
        profile: 平台部署环境。
        use_in_memory_adapters: development 部署是否显式使用 in-memory
            adapters；production 部署必须为 ``False``。
        postgres_dsn_env: PostgreSQL DSN 所在环境变量名称；未配置时为
            ``None``。
        object_storage_env: 对象存储配置所在环境变量名称；未配置时为
            ``None``。
        redis_env: Redis 地址所在环境变量名称；未配置时为 ``None``。
        auth_key_env: auth 密钥所在环境变量名称；未配置时为 ``None``。
    """

    enabled: bool
    profile: PlatformDeploymentProfile
    use_in_memory_adapters: bool = False
    postgres_dsn_env: str | None = None
    object_storage_env: str | None = None
    redis_env: str | None = None
    auth_key_env: str | None = None

    def __post_init__(self) -> None:
        """构造后立即执行严格校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformSettingsError: 设置违反严格规则时抛出。
        """

        self.validate()

    def validate(self) -> None:
        """校验平台设置并返回。

        规则：

        - 标量字段必须是精确运行时类型：``enabled`` 与
          ``use_in_memory_adapters`` 必须为 ``bool``、``profile`` 必须为
          ``PlatformDeploymentProfile`` 枚举值；
        - 基础设施字段必须为 ``str | None``，非空时必须符合
          ``[A-Z][A-Z0-9_]*`` 形态；
        - 平台未启用时不要求任何基础设施环境变量；
        - production 部署启用时必须提供全部四个基础设施环境变量名称，
          且禁止 in-memory adapters；
        - development 部署启用时必须显式选择 in-memory adapters，
          且禁止配置任何 production 基础设施环境变量。

        所有失败消息只报告字段名与固定规则，不格式化任何候选值。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformSettingsError: 设置违反严格规则时抛出。
        """

        self._validate_field_types()
        for field_name, env_name in self._infra_env_entries():
            if env_name is None:
                continue
            if _ENV_NAME_PATTERN.fullmatch(env_name) is None:
                raise PlatformSettingsError(
                    f"{field_name} 必须是合法环境变量名称（仅允许大写字母、数字与下划线，且以字母开头）"
                )
        if not self.enabled:
            return
        if self.profile is PlatformDeploymentProfile.PRODUCTION:
            self._validate_production()
            return
        if self.profile is PlatformDeploymentProfile.INTEGRATION:
            self._validate_integration()
            return
        self._validate_development()

    def _validate_field_types(self) -> None:
        """校验标量与基础设施字段的精确运行时类型。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformSettingsError: 字段类型非法时抛出。
        """

        if not isinstance(self.enabled, bool):
            raise PlatformSettingsError("enabled 必须是布尔值")
        if not isinstance(self.use_in_memory_adapters, bool):
            raise PlatformSettingsError("use_in_memory_adapters 必须是布尔值")
        if not isinstance(self.profile, PlatformDeploymentProfile):
            raise PlatformSettingsError("profile 必须是 PlatformDeploymentProfile 枚举值")
        for field_name, env_name in self._infra_env_entries():
            if env_name is not None and not isinstance(env_name, str):
                raise PlatformSettingsError(f"{field_name} 必须是环境变量名称或 None")

    def _validate_production(self) -> None:
        """校验 production 部署启用时的严格规则。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformSettingsError: 缺少基础设施环境变量或误用 in-memory
                adapters 时抛出。
        """

        missing_names = [field_name for field_name, env_name in self._infra_env_entries() if env_name is None]
        if missing_names:
            raise PlatformSettingsError("production 平台启用缺少基础设施环境变量名称: " + ", ".join(missing_names))
        if self.use_in_memory_adapters:
            raise PlatformSettingsError("production 平台禁止使用 in-memory adapters")

    def _validate_development(self) -> None:
        """校验 development 部署启用时的严格规则。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformSettingsError: 未显式选择 in-memory adapters 或混用
                production 基础设施环境变量时抛出。
        """

        if not self.use_in_memory_adapters:
            raise PlatformSettingsError("development 平台启用必须显式选择 in-memory adapters")
        configured_names = [field_name for field_name, env_name in self._infra_env_entries() if env_name is not None]
        if configured_names:
            raise PlatformSettingsError(
                "development in-memory 平台禁止配置 production 基础设施环境变量: " + ", ".join(configured_names)
            )

    def _validate_integration(self) -> None:
        """校验 integration 部署启用时的严格规则。

        只供测试/本地 durable integration：必须且只允许配置
        ``postgres_dsn_env``，object storage / Redis / auth 任一非空
        即 fail-fast，绝不静默忽略。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformSettingsError: 缺少 DSN、误用 in-memory adapters 或
                配置了其它基础设施环境变量时抛出。
        """

        if self.use_in_memory_adapters:
            raise PlatformSettingsError("integration 平台禁止使用 in-memory adapters")
        if self.postgres_dsn_env is None:
            raise PlatformSettingsError("integration 平台启用必须配置 postgres_dsn 环境变量")
        forbidden_names = [
            field_name
            for field_name, env_name in self._infra_env_entries()
            if env_name is not None and field_name != "postgres_dsn_env"
        ]
        if forbidden_names:
            raise PlatformSettingsError(
                "integration 平台只允许配置 postgres_dsn 环境变量，禁止: " + ", ".join(forbidden_names)
            )

    def _infra_env_entries(self) -> tuple[tuple[str, str | None], ...]:
        """返回基础设施字段名到环境变量名称的对应关系。

        Args:
            无。

        Returns:
            依次为 postgres_dsn / object_storage / redis / auth_key
            的 ``(字段名, 环境变量名称或 None)`` 元组序列。

        Raises:
            无。
        """

        return (
            ("postgres_dsn_env", self.postgres_dsn_env),
            ("object_storage_env", self.object_storage_env),
            ("redis_env", self.redis_env),
            ("auth_key_env", self.auth_key_env),
        )


def _read_bool_env(env: Mapping[str, str], env_var: str) -> bool:
    """读取布尔开关环境变量。

    Args:
        env: 环境变量映射。
        env_var: 布尔开关环境变量名称。

    Returns:
        值为 ``1/true/yes/on``（不区分大小写）时返回 ``True``，
        未设置或为空时返回 ``False``。

    Raises:
        PlatformSettingsError: 值非空但无法识别为布尔开关时抛出。
    """

    raw_value = env.get(env_var, "").strip().lower()
    if not raw_value:
        return False
    if raw_value in _TRUE_TOKENS:
        return True
    raise PlatformSettingsError(f"环境变量 {env_var} 必须是 1/true/yes/on 或保持为空")


def _read_optional_env_name(env: Mapping[str, str], env_var: str) -> str | None:
    """检查基础设施环境变量是否已配置并返回其名称。

    本函数只做存在性检查，绝不读取或返回环境变量的取值，因此
    ``PlatformSettings`` 永远不会持有 secret 值。

    Args:
        env: 环境变量映射。
        env_var: 基础设施环境变量名称。

    Returns:
        环境变量已设置且值非空时返回其名称，否则返回 ``None``。

    Raises:
        无。
    """

    if env.get(env_var, "").strip():
        return env_var
    return None


def load_platform_settings(env: Mapping[str, str]) -> PlatformSettings:
    """从环境变量映射加载并校验平台设置。

    Args:
        env: 环境变量映射（通常是进程环境）。

    Returns:
        完成严格校验的 ``PlatformSettings``，其中基础设施字段只记录
        环境变量名称，不记录任何 secret 值。

    Raises:
        PlatformSettingsError: 部署环境未知、布尔开关非法或设置违反
            严格规则时抛出。
    """

    raw_profile = env.get(DAYU_PLATFORM_PROFILE_ENV, "").strip().lower()
    if not raw_profile:
        profile = PlatformDeploymentProfile.DEVELOPMENT
    else:
        try:
            profile = PlatformDeploymentProfile(raw_profile)
        except ValueError:
            raise PlatformSettingsError(
                f"{DAYU_PLATFORM_PROFILE_ENV} 必须是受支持的部署环境（development / production / integration）"
            ) from None
    settings = PlatformSettings(
        enabled=_read_bool_env(env, DAYU_PLATFORM_ENABLED_ENV),
        profile=profile,
        use_in_memory_adapters=_read_bool_env(env, DAYU_PLATFORM_USE_IN_MEMORY_ENV),
        postgres_dsn_env=_read_optional_env_name(env, DAYU_PLATFORM_POSTGRES_DSN_ENV),
        object_storage_env=_read_optional_env_name(env, DAYU_PLATFORM_OBJECT_STORAGE_ENV),
        redis_env=_read_optional_env_name(env, DAYU_PLATFORM_REDIS_ENV),
        auth_key_env=_read_optional_env_name(env, DAYU_PLATFORM_AUTH_KEY_ENV),
    )
    return settings


__all__ = [
    "DAYU_PLATFORM_AUTH_KEY_ENV",
    "DAYU_PLATFORM_ENABLED_ENV",
    "DAYU_PLATFORM_OBJECT_STORAGE_ENV",
    "DAYU_PLATFORM_POSTGRES_DSN_ENV",
    "DAYU_PLATFORM_PROFILE_ENV",
    "DAYU_PLATFORM_QUEUE_EMPTY_POLL_JITTER_MAX_SECONDS",
    "DAYU_PLATFORM_QUEUE_GOVERNANCE_FAILURE_THRESHOLD",
    "DAYU_PLATFORM_QUEUE_GOVERNANCE_PAGE_SIZE",
    "DAYU_PLATFORM_QUEUE_POLL_INTERVAL_SECONDS",
    "DAYU_PLATFORM_QUEUE_REDIS_FAILURE_THRESHOLD",
    "DAYU_PLATFORM_QUEUE_REDIS_HEALTH_INTERVAL_SECONDS",
    "DAYU_PLATFORM_QUEUE_SHUTDOWN_GRACE_SECONDS",
    "DAYU_PLATFORM_REDIS_ENV",
    "DAYU_PLATFORM_SCHEDULE_CANDIDATE_SCAN_LIMIT",
    "DAYU_PLATFORM_SCHEDULE_MAX_LOOKBACK_SECONDS",
    "DAYU_PLATFORM_SCHEDULE_TICK_BATCH_SIZE",
    "DAYU_PLATFORM_USE_IN_MEMORY_ENV",
    "PlatformDeploymentProfile",
    "PlatformQueueAdmissionKind",
    "PlatformQueueMode",
    "PlatformQueueSettings",
    "PlatformSettings",
    "PlatformSettingsError",
    "build_queue_startup_snapshot",
    "load_platform_queue_settings",
    "load_platform_settings",
]
