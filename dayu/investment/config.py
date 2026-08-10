"""投资平台严格配置定义。

本模块定义投资平台的部署配置契约，保持纯标准库依赖、不依赖任何上层包：

- 配置只记录环境变量名称（env name），绝不记录或回显 secret 值；
  即使对 ``PlatformSettings`` 做调试快照，也只能看到环境变量名。
- production 部署启用平台时，缺少 DSN / 对象存储 / Redis / auth key
  任一环境变量即构造期 fail-fast，且禁止使用 in-memory adapters。
- development 部署启用平台时必须显式选择 in-memory adapters，
  禁止混用 production 基础设施环境变量，防止误连真实持久化设施。

环境变量开关与名称是固定契约，由本模块常量声明；具体取值由后续
slice 的 provider 读取，本模块只记录"名称已配置"这一事实。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

DAYU_PLATFORM_ENABLED_ENV = "DAYU_PLATFORM_ENABLED"
DAYU_PLATFORM_PROFILE_ENV = "DAYU_PLATFORM_PROFILE"
DAYU_PLATFORM_USE_IN_MEMORY_ENV = "DAYU_PLATFORM_USE_IN_MEMORY"
DAYU_PLATFORM_POSTGRES_DSN_ENV = "DAYU_PLATFORM_POSTGRES_DSN"
DAYU_PLATFORM_OBJECT_STORAGE_ENV = "DAYU_PLATFORM_OBJECT_STORAGE"
DAYU_PLATFORM_REDIS_ENV = "DAYU_PLATFORM_REDIS_URL"
DAYU_PLATFORM_AUTH_KEY_ENV = "DAYU_PLATFORM_AUTH_KEY"

_TRUE_TOKENS: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class PlatformDeploymentProfile(Enum):
    """平台部署环境。"""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class PlatformSettingsError(ValueError):
    """平台设置非法时抛出的错误。"""


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

        missing_names = [
            field_name for field_name, env_name in self._infra_env_entries() if env_name is None
        ]
        if missing_names:
            raise PlatformSettingsError(
                "production 平台启用缺少基础设施环境变量名称: "
                + ", ".join(missing_names)
            )
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
            raise PlatformSettingsError(
                "development 平台启用必须显式选择 in-memory adapters"
            )
        configured_names = [
            field_name for field_name, env_name in self._infra_env_entries() if env_name is not None
        ]
        if configured_names:
            raise PlatformSettingsError(
                "development in-memory 平台禁止配置 production 基础设施环境变量: "
                + ", ".join(configured_names)
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
                f"{DAYU_PLATFORM_PROFILE_ENV} 必须是受支持的部署环境（development / production）"
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
    "DAYU_PLATFORM_REDIS_ENV",
    "DAYU_PLATFORM_USE_IN_MEMORY_ENV",
    "PlatformDeploymentProfile",
    "PlatformSettings",
    "PlatformSettingsError",
    "load_platform_settings",
]
