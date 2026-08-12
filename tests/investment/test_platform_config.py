"""投资平台严格配置与组合契约测试。

本文件覆盖 Slice 0.2 的两类契约：

1. ``PlatformSettings`` 严格校验：配置只记录环境变量名称、不回显
   secret；production 启用缺少 DSN / 对象存储 / Redis / auth key 任一
   环境变量即 fail-fast，且禁止 in-memory adapters；development 启用
   必须显式选择 in-memory adapters，禁止混用 production 基础设施。
2. ``PlatformComposition`` 空 / 禁用状态与泛型组合根的只读语义。

本测试文件遵守根 ``AGENTS.md`` 约束，不使用 ``object`` / ``Any`` /
``cast`` / ``type: ignore`` / ``getattr`` / ``hasattr``。
"""

from __future__ import annotations

import math
import traceback
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Callable

import pytest

from dayu.investment.composition import (
    PlatformComposition,
    PlatformCompositionContractError,
    PlatformCompositionProviderProtocol,
    PlatformServiceProtocol,
)
from dayu.investment.config import (
    DAYU_PLATFORM_AUTH_KEY_ENV,
    DAYU_PLATFORM_ENABLED_ENV,
    DAYU_PLATFORM_OBJECT_STORAGE_ENV,
    DAYU_PLATFORM_POSTGRES_DSN_ENV,
    DAYU_PLATFORM_PROFILE_ENV,
    DAYU_PLATFORM_QUEUE_GOVERNANCE_FAILURE_THRESHOLD,
    DAYU_PLATFORM_QUEUE_POLL_INTERVAL_SECONDS,
    DAYU_PLATFORM_QUEUE_REDIS_FAILURE_THRESHOLD,
    DAYU_PLATFORM_QUEUE_REDIS_HEALTH_INTERVAL_SECONDS,
    DAYU_PLATFORM_REDIS_ENV,
    DAYU_PLATFORM_USE_IN_MEMORY_ENV,
    PlatformDeploymentProfile,
    PlatformQueueMode,
    PlatformQueueSettings,
    PlatformSettings,
    PlatformSettingsError,
    build_queue_startup_snapshot,
    load_platform_queue_settings,
    load_platform_settings,
)

_SECRET_DSN = "postgres://user:super-secret-dsn@localhost:5432/dayu"
_SECRET_OBJECT_STORAGE = "minio://localhost:9000"
_SECRET_REDIS = "redis://localhost:6379"
_SECRET_AUTH_KEY = "super-secret-signing-key"

_QueueSettingTestValue = PlatformQueueMode | str | bool | int | float
"""queue setting 负例使用的闭合标量联合。"""


class _TenantText(str):
    """用于证明 startup tenant 只接受 exact ``str`` 的测试子类。"""

_PRODUCTION_ENV: dict[str, str] = {
    DAYU_PLATFORM_ENABLED_ENV: "1",
    DAYU_PLATFORM_PROFILE_ENV: "production",
    DAYU_PLATFORM_POSTGRES_DSN_ENV: _SECRET_DSN,
    DAYU_PLATFORM_OBJECT_STORAGE_ENV: _SECRET_OBJECT_STORAGE,
    DAYU_PLATFORM_REDIS_ENV: _SECRET_REDIS,
    DAYU_PLATFORM_AUTH_KEY_ENV: _SECRET_AUTH_KEY,
}

def _production_settings() -> PlatformSettings:
    """构造一份合法的 production 平台设置。

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
        postgres_dsn_env=DAYU_PLATFORM_POSTGRES_DSN_ENV,
        object_storage_env=DAYU_PLATFORM_OBJECT_STORAGE_ENV,
        redis_env=DAYU_PLATFORM_REDIS_ENV,
        auth_key_env=DAYU_PLATFORM_AUTH_KEY_ENV,
    )


@dataclass(frozen=True)
class _FakePlatformService:
    """测试用平台 Service 协议实现。

    结构满足 ``PlatformServiceProtocol``（携带只读
    ``platform_service_name``），用于验证组合根只接收/暴露协议实例。
    """

    platform_service_name: str


class TestPlatformSettingsValidation:
    """平台设置构造期严格校验。"""

    @pytest.mark.unit
    def test_disabled_settings_accept_missing_infrastructure(self) -> None:
        """平台未启用时不要求任何基础设施环境变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = PlatformSettings(enabled=False, profile=PlatformDeploymentProfile.PRODUCTION)
        assert settings.enabled is False
        assert settings.postgres_dsn_env is None

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "build_incomplete_settings",
        [
            pytest.param(
                lambda: PlatformSettings(
                    enabled=True,
                    profile=PlatformDeploymentProfile.PRODUCTION,
                    object_storage_env=DAYU_PLATFORM_OBJECT_STORAGE_ENV,
                    redis_env=DAYU_PLATFORM_REDIS_ENV,
                    auth_key_env=DAYU_PLATFORM_AUTH_KEY_ENV,
                ),
                id="missing-postgres-dsn",
            ),
            pytest.param(
                lambda: PlatformSettings(
                    enabled=True,
                    profile=PlatformDeploymentProfile.PRODUCTION,
                    postgres_dsn_env=DAYU_PLATFORM_POSTGRES_DSN_ENV,
                    redis_env=DAYU_PLATFORM_REDIS_ENV,
                    auth_key_env=DAYU_PLATFORM_AUTH_KEY_ENV,
                ),
                id="missing-object-storage",
            ),
            pytest.param(
                lambda: PlatformSettings(
                    enabled=True,
                    profile=PlatformDeploymentProfile.PRODUCTION,
                    postgres_dsn_env=DAYU_PLATFORM_POSTGRES_DSN_ENV,
                    object_storage_env=DAYU_PLATFORM_OBJECT_STORAGE_ENV,
                    auth_key_env=DAYU_PLATFORM_AUTH_KEY_ENV,
                ),
                id="missing-redis",
            ),
            pytest.param(
                lambda: PlatformSettings(
                    enabled=True,
                    profile=PlatformDeploymentProfile.PRODUCTION,
                    postgres_dsn_env=DAYU_PLATFORM_POSTGRES_DSN_ENV,
                    object_storage_env=DAYU_PLATFORM_OBJECT_STORAGE_ENV,
                    redis_env=DAYU_PLATFORM_REDIS_ENV,
                ),
                id="missing-auth-key",
            ),
        ],
    )
    def test_production_missing_any_infrastructure_env_fails_fast(
        self,
        build_incomplete_settings: Callable[[], PlatformSettings],
    ) -> None:
        """production 启用缺少任一基础设施环境变量即 fail-fast。

        Args:
            build_incomplete_settings: 构造缺少一个基础设施字段设置的工厂。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            build_incomplete_settings()

    @pytest.mark.unit
    def test_production_forbids_in_memory_adapters(self) -> None:
        """production 启用禁止 in-memory adapters。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            PlatformSettings(
                enabled=True,
                profile=PlatformDeploymentProfile.PRODUCTION,
                use_in_memory_adapters=True,
                postgres_dsn_env=DAYU_PLATFORM_POSTGRES_DSN_ENV,
                object_storage_env=DAYU_PLATFORM_OBJECT_STORAGE_ENV,
                redis_env=DAYU_PLATFORM_REDIS_ENV,
                auth_key_env=DAYU_PLATFORM_AUTH_KEY_ENV,
            )

    @pytest.mark.unit
    def test_production_with_all_infrastructure_is_valid(self) -> None:
        """production 启用且四个环境变量齐全时构造成功。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = _production_settings()
        assert settings.enabled is True
        assert settings.profile is PlatformDeploymentProfile.PRODUCTION

    @pytest.mark.unit
    def test_development_requires_explicit_in_memory(self) -> None:
        """development 启用必须显式选择 in-memory adapters。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            PlatformSettings(
                enabled=True,
                profile=PlatformDeploymentProfile.DEVELOPMENT,
            )

    @pytest.mark.unit
    def test_development_in_memory_rejects_production_env_names(self) -> None:
        """development in-memory 平台禁止配置 production 基础设施环境变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            PlatformSettings(
                enabled=True,
                profile=PlatformDeploymentProfile.DEVELOPMENT,
                use_in_memory_adapters=True,
                postgres_dsn_env=DAYU_PLATFORM_POSTGRES_DSN_ENV,
            )

    @pytest.mark.unit
    def test_development_in_memory_is_valid(self) -> None:
        """development 启用且显式选择 in-memory 时构造成功。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = PlatformSettings(
            enabled=True,
            profile=PlatformDeploymentProfile.DEVELOPMENT,
            use_in_memory_adapters=True,
        )
        assert settings.use_in_memory_adapters is True

    @pytest.mark.unit
    def test_invalid_env_name_format_rejected_even_when_disabled(self) -> None:
        """即使平台禁用，非法环境变量名称格式也 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            PlatformSettings(
                enabled=False,
                profile=PlatformDeploymentProfile.DEVELOPMENT,
                postgres_dsn_env="bad env name",
            )

    @pytest.mark.unit
    def test_settings_are_frozen(self) -> None:
        """平台设置构造后禁止属性改写。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = _production_settings()
        with pytest.raises(AttributeError):
            setattr(settings, "enabled", False)


class TestLoadPlatformSettings:
    """从环境变量映射加载平台设置。"""

    @pytest.mark.unit
    def test_empty_env_yields_disabled_development_defaults(self) -> None:
        """空环境映射得到禁用的 development 默认设置。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = load_platform_settings({})
        assert settings.enabled is False
        assert settings.profile is PlatformDeploymentProfile.DEVELOPMENT
        assert settings.use_in_memory_adapters is False
        assert settings.postgres_dsn_env is None
        assert settings.object_storage_env is None
        assert settings.redis_env is None
        assert settings.auth_key_env is None

    @pytest.mark.unit
    def test_disabled_load_records_env_names_without_fail(self) -> None:
        """平台禁用时仍记录已配置的环境变量名称，不触发校验失败。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        env = dict(_PRODUCTION_ENV)
        del env[DAYU_PLATFORM_ENABLED_ENV]
        del env[DAYU_PLATFORM_PROFILE_ENV]
        settings = load_platform_settings(env)
        assert settings.enabled is False
        assert settings.postgres_dsn_env == DAYU_PLATFORM_POSTGRES_DSN_ENV
        assert settings.auth_key_env == DAYU_PLATFORM_AUTH_KEY_ENV

    @pytest.mark.unit
    def test_production_env_records_names_never_values(self) -> None:
        """production 环境加载后只记录环境变量名称，不回显 secret 值。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = load_platform_settings(_PRODUCTION_ENV)
        assert settings.enabled is True
        assert settings.profile is PlatformDeploymentProfile.PRODUCTION
        assert settings.postgres_dsn_env == DAYU_PLATFORM_POSTGRES_DSN_ENV
        assert settings.object_storage_env == DAYU_PLATFORM_OBJECT_STORAGE_ENV
        assert settings.redis_env == DAYU_PLATFORM_REDIS_ENV
        assert settings.auth_key_env == DAYU_PLATFORM_AUTH_KEY_ENV
        serialized = str(settings)
        assert _SECRET_DSN not in serialized
        assert _SECRET_AUTH_KEY not in serialized

    @pytest.mark.unit
    def test_enabled_without_profile_defaults_to_development(self) -> None:
        """未指定 profile 时默认 development，并按 development 规则校验。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            load_platform_settings({DAYU_PLATFORM_ENABLED_ENV: "1"})

    @pytest.mark.unit
    def test_development_in_memory_env_loads(self) -> None:
        """development 显式选择 in-memory 时加载成功。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = load_platform_settings(
            {
                DAYU_PLATFORM_ENABLED_ENV: "1",
                DAYU_PLATFORM_PROFILE_ENV: "development",
                DAYU_PLATFORM_USE_IN_MEMORY_ENV: "1",
            }
        )
        assert settings.enabled is True
        assert settings.use_in_memory_adapters is True

    @pytest.mark.unit
    @pytest.mark.parametrize("raw_value", ["1", "true", "TRUE", "yes", "on"])
    def test_true_tokens_accepted(self, raw_value: str) -> None:
        """布尔开关接受 1/true/yes/on 多种写法。

        Args:
            raw_value: 布尔开关原始取值。

        Returns:
            无。

        Raises:
            无。
        """

        settings = load_platform_settings(
            {
                DAYU_PLATFORM_ENABLED_ENV: raw_value,
                DAYU_PLATFORM_PROFILE_ENV: "development",
                DAYU_PLATFORM_USE_IN_MEMORY_ENV: raw_value,
            }
        )
        assert settings.enabled is True
        assert settings.use_in_memory_adapters is True

    @pytest.mark.unit
    def test_invalid_profile_rejected(self) -> None:
        """未知部署环境一律 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            load_platform_settings({DAYU_PLATFORM_PROFILE_ENV: "staging"})

    @pytest.mark.unit
    def test_invalid_boolean_rejected(self) -> None:
        """非空但无法识别的布尔开关一律 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            load_platform_settings({DAYU_PLATFORM_ENABLED_ENV: "garbage"})


class TestPlatformComposition:
    """平台组合根的空 / 禁用状态、协议边界与防御性快照。"""

    @pytest.mark.unit
    def test_disabled_composition_state(self) -> None:
        """禁用状态组合根不启用且不暴露任何 Service。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        composition: PlatformComposition[PlatformServiceProtocol] = PlatformComposition.disabled()
        assert composition.enabled is False
        assert composition.services == {}

    @pytest.mark.unit
    def test_empty_composition_state(self) -> None:
        """空状态组合根已启用但尚无可暴露的 Service。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        composition: PlatformComposition[PlatformServiceProtocol] = PlatformComposition.empty()
        assert composition.enabled is True
        assert composition.services == {}

    @pytest.mark.unit
    def test_composition_holds_platform_service_protocols(self) -> None:
        """组合根按协议边界承载真实 ``PlatformServiceProtocol`` 实例。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        service = _FakePlatformService(platform_service_name="platform")
        composition = PlatformComposition[PlatformServiceProtocol](
            enabled=True,
            services={"platform": service},
        )
        assert composition.enabled is True
        assert composition.services == {"platform": service}
        assert isinstance(composition.services["platform"], PlatformServiceProtocol)

    @pytest.mark.unit
    def test_composition_equality(self) -> None:
        """同状态同内容组合根相等。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        left = PlatformComposition[PlatformServiceProtocol](
            enabled=True,
            services={"a": _FakePlatformService(platform_service_name="a")},
        )
        right = PlatformComposition[PlatformServiceProtocol](
            enabled=True,
            services={"a": _FakePlatformService(platform_service_name="a")},
        )
        assert left == right
        assert left != PlatformComposition.disabled()

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "bad_services",
        [
            {"platform": "not-a-service"},
            {"platform": {"name": "platform"}},
            {"platform": 1},
            {"platform": None},
        ],
    )
    def test_composition_rejects_non_protocol_values(
        self,
        bad_services: dict[str, str] | dict[str, int] | dict[str, None] | dict[str, dict[str, str]],
    ) -> None:
        """str / dict / 数字 / None 等非协议值一律 fail closed。

        通过 ``dataclasses.replace`` 注入静态类型不允许的候选值，
        验证组合根在运行时的协议守卫（与 Money / Quantity 反例测试
        同款注入模式，不使用 Any / cast / object 逃逸）。

        Args:
            bad_services: 携带非协议值的 service 注册。

        Returns:
            无。

        Raises:
            无。
        """

        valid = PlatformComposition[PlatformServiceProtocol](enabled=True, services={})
        with pytest.raises(PlatformCompositionContractError):
            replace(valid, services=bad_services)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("key", "service_name"),
        [
            ("", "platform"),
            ("   ", "platform"),
            ("\tplatform", "platform"),
            (" chat", " chat"),
            ("chat ", "chat "),
        ],
    )
    def test_composition_rejects_invalid_registry_keys(
        self,
        key: str,
        service_name: str,
    ) -> None:
        """空 / 仅空白 / 首尾空白注册键一律 fail closed。

        ``(" chat", " chat")`` 与 ``("chat ", "chat ")`` 是键名一致的
        带首尾空白 case：若规则只检查 ``strip()`` 非空而不检查无首尾
        空白，将错误放行，因此本 case 独立锁定空白规则。

        Args:
            key: 非法注册键。
            service_name: 与键一致的非法 Service 名称。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformCompositionContractError):
            PlatformComposition[PlatformServiceProtocol](
                enabled=True,
                services={key: _FakePlatformService(platform_service_name=service_name)},
            )

    @pytest.mark.unit
    @pytest.mark.parametrize("service_name", ["", "   ", " chat"])
    def test_composition_rejects_invalid_service_names(self, service_name: str) -> None:
        """空 / 仅空白 / 首尾空白的 Service 名称一律 fail closed。

        Args:
            service_name: 非法 Service 名称。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformCompositionContractError):
            PlatformComposition[PlatformServiceProtocol](
                enabled=True,
                services={"chat": _FakePlatformService(platform_service_name=service_name)},
            )

    @pytest.mark.unit
    def test_composition_rejects_mismatched_registry_name(self) -> None:
        """注册键与 Service 名称不一致时 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformCompositionContractError):
            PlatformComposition[PlatformServiceProtocol](
                enabled=True,
                services={"chat": _FakePlatformService(platform_service_name="fins")},
            )

    @pytest.mark.unit
    def test_composition_rejects_non_mapping_services(self) -> None:
        """services 不是 Mapping（如裸字符串）时 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        valid = PlatformComposition[PlatformServiceProtocol](enabled=True, services={})
        with pytest.raises(PlatformCompositionContractError):
            replace(valid, services="not-a-mapping")

    @pytest.mark.unit
    def test_composition_rejects_non_bool_enabled(self) -> None:
        """enabled 不是布尔值（如字符串）时 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        valid = PlatformComposition[PlatformServiceProtocol](enabled=True, services={})
        with pytest.raises(PlatformCompositionContractError):
            replace(valid, enabled="yes")

    @pytest.mark.unit
    def test_composition_rejects_disabled_with_services(self) -> None:
        """禁用状态组合根携带任何 Service 注册时 fail closed。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformCompositionContractError):
            PlatformComposition[PlatformServiceProtocol](
                enabled=False,
                services={"chat": _FakePlatformService(platform_service_name="chat")},
            )

    @pytest.mark.unit
    def test_composition_snapshot_isolates_external_mutation(self) -> None:
        """构造后的组合根不受外部原映射后续修改影响。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        registry: dict[str, _FakePlatformService] = {
            "chat": _FakePlatformService(platform_service_name="chat"),
        }
        composition = PlatformComposition[PlatformServiceProtocol](
            enabled=True,
            services=registry,
        )
        registry["fins"] = _FakePlatformService(platform_service_name="fins")
        assert list(composition.services) == ["chat"]

    @pytest.mark.unit
    def test_composition_services_mapping_is_read_only(self) -> None:
        """组合根暴露的 service 注册是只读 ``MappingProxyType``。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        composition = PlatformComposition[PlatformServiceProtocol](
            enabled=True,
            services={"chat": _FakePlatformService(platform_service_name="chat")},
        )
        assert isinstance(composition.services, MappingProxyType)

    @pytest.mark.unit
    def test_composition_contract_error_does_not_echo_candidate_value(self) -> None:
        """组合契约异常只报告违反的规则，不格式化候选值。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        secret_shaped = "postgres://user:super-secret@db/dayu"
        valid = PlatformComposition[PlatformServiceProtocol](enabled=True, services={})
        with pytest.raises(PlatformCompositionContractError) as excinfo:
            replace(valid, services={"platform": secret_shaped})
        assert secret_shaped not in str(excinfo.value)
        assert "PlatformServiceProtocol" in str(excinfo.value)


class TestProviderContract:
    """组合提供者协议与注入点行为。"""

    @pytest.mark.unit
    def test_provider_protocol_is_runtime_checkable(self) -> None:
        """组合提供者协议支持运行时结构检查。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        assert isinstance(
            _FakePlatformCompositionProvider(services={}),
            PlatformCompositionProviderProtocol,
        )
        assert not isinstance("not-a-provider", PlatformCompositionProviderProtocol)

    @pytest.mark.unit
    def test_service_protocol_is_runtime_checkable(self) -> None:
        """平台 Service 协议支持运行时结构检查，裸值不通过。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        assert isinstance(_FakePlatformService(platform_service_name="chat"), PlatformServiceProtocol)
        assert not isinstance("chat", PlatformServiceProtocol)
        assert not isinstance({"name": "chat"}, PlatformServiceProtocol)


class _FakePlatformCompositionProvider:
    """测试用平台组合提供者实现。"""

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


class TestPlatformSettingsRedaction:
    """非法 env-name 异常与 secret 形状输入的红action。"""

    @pytest.mark.unit
    def test_invalid_env_name_error_does_not_echo_candidate(self) -> None:
        """非法 env-name 异常只报告字段与固定规则，不格式化候选值。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        bad_value = "postgres_dsn_env with spaces"
        with pytest.raises(PlatformSettingsError) as excinfo:
            PlatformSettings(
                enabled=False,
                profile=PlatformDeploymentProfile.DEVELOPMENT,
                postgres_dsn_env=bad_value,
            )
        message = str(excinfo.value)
        assert bad_value not in message
        assert "postgres_dsn_env" in message

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("build_settings_with_secret", "secret_value"),
        [
            pytest.param(
                lambda value: PlatformSettings(
                    enabled=False,
                    profile=PlatformDeploymentProfile.DEVELOPMENT,
                    postgres_dsn_env=value,
                ),
                _SECRET_DSN,
                id="postgres-dsn",
            ),
            pytest.param(
                lambda value: PlatformSettings(
                    enabled=False,
                    profile=PlatformDeploymentProfile.DEVELOPMENT,
                    object_storage_env=value,
                ),
                _SECRET_OBJECT_STORAGE,
                id="object-storage",
            ),
            pytest.param(
                lambda value: PlatformSettings(
                    enabled=False,
                    profile=PlatformDeploymentProfile.DEVELOPMENT,
                    redis_env=value,
                ),
                _SECRET_REDIS,
                id="redis",
            ),
            pytest.param(
                lambda value: PlatformSettings(
                    enabled=False,
                    profile=PlatformDeploymentProfile.DEVELOPMENT,
                    auth_key_env=value,
                ),
                _SECRET_AUTH_KEY,
                id="auth-key",
            ),
        ],
    )
    def test_secret_shaped_env_name_error_is_redacted(
        self,
        build_settings_with_secret: Callable[[str], PlatformSettings],
        secret_value: str,
    ) -> None:
        """DSN / 对象存储 / Redis / auth key 形状输入在异常中不回显。

        Args:
            build_settings_with_secret: 把 secret 形状值误传为 env-name
                字段的构造工厂。
            secret_value: 形状类似 secret 的候选值。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError) as excinfo:
            build_settings_with_secret(secret_value)
        assert secret_value not in str(excinfo.value)


class TestProfileSettingsRedaction:
    """未知部署环境异常对 secret 形状候选值的 redaction。"""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "secret_profile",
        [
            _SECRET_DSN,
            "auth-token-super-secret-abcdef",
            "sk-provider-super-secret-abcdef",
        ],
    )
    def test_secret_shaped_profile_error_is_redacted(self, secret_profile: str) -> None:
        """DSN / auth token / provider key 形状的 profile 候选值不回显。

        校验三层泄露面：顶层 ``str(error)``、``error.__cause__`` 与完整
        ``traceback.format_exception`` 文本均不得包含候选值；稳定消息
        只报告环境变量名与固定允许值。

        Args:
            secret_profile: 被误配到 ``DAYU_PLATFORM_PROFILE`` 的候选值。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError) as excinfo:
            load_platform_settings({DAYU_PLATFORM_PROFILE_ENV: secret_profile})
        error = excinfo.value
        message = str(error)
        assert secret_profile not in message
        assert DAYU_PLATFORM_PROFILE_ENV in message
        assert "development" in message and "production" in message
        assert error.__cause__ is None
        assert secret_profile not in "".join(traceback.format_exception(error))


class TestPlatformSettingsStrictTypes:
    """公开构造器的运行时类型边界反例。"""

    @pytest.mark.unit
    def test_non_bool_enabled_rejected(self) -> None:
        """``enabled=1`` 这类非布尔值一律 fail closed。

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
        with pytest.raises(PlatformSettingsError):
            replace(settings, enabled=1)

    @pytest.mark.unit
    def test_non_bool_in_memory_rejected(self) -> None:
        """``use_in_memory_adapters="yes"`` 这类非布尔值一律 fail closed。

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
        with pytest.raises(PlatformSettingsError):
            replace(settings, use_in_memory_adapters="yes")

    @pytest.mark.unit
    def test_unknown_string_profile_rejected(self) -> None:
        """未知字符串 profile 无法绕过严格契约。

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
        with pytest.raises(PlatformSettingsError):
            replace(settings, profile="unsupported-profile")

    @pytest.mark.unit
    @pytest.mark.parametrize("env_value", [123, True, b"bytes"])
    def test_non_string_env_name_rejected(self, env_value: int | bool | bytes) -> None:
        """非 ``str | None`` 的基础设施字段值一律 fail closed。

        Args:
            env_value: 非法基础设施字段值。

        Returns:
            无。

        Raises:
            无。
        """

        settings = PlatformSettings(
            enabled=False,
            profile=PlatformDeploymentProfile.DEVELOPMENT,
        )
        with pytest.raises(PlatformSettingsError):
            replace(settings, postgres_dsn_env=env_value)


class TestPlatformQueueSettings:
    """``PlatformQueueSettings`` 严格数值契约与 profile 派生测试。"""

    def _settings(
        self,
        **overrides: _QueueSettingTestValue,
    ) -> PlatformQueueSettings:
        """以默认值构造 queue settings 并允许字段覆盖。

        Args:
            overrides: 需要覆盖的字段名到值的映射。

        Returns:
            构造出的 ``PlatformQueueSettings``。

        Raises:
            PlatformSettingsError: 覆盖值非法时抛出。
        """

        defaults = PlatformQueueSettings(mode=PlatformQueueMode.EVENT_ASSISTED)
        return replace(defaults, **overrides)

    @pytest.mark.unit
    def test_queue_settings_defaults_are_exact_and_enter_safe_startup_snapshot(self) -> None:
        """默认值与 safe startup snapshot 数值必须精确一致。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = PlatformQueueSettings(mode=PlatformQueueMode.EVENT_ASSISTED)
        assert settings.poll_interval_seconds == 5.0
        assert settings.redis_health_interval_seconds == 30.0
        assert settings.redis_failure_threshold == 3
        assert settings.shutdown_grace_seconds == 30.0
        assert settings.empty_poll_jitter_max_seconds == 1.0
        assert settings.schedule_max_lookback_seconds == 604800
        assert settings.schedule_candidate_scan_limit == 20000
        assert settings.schedule_tick_batch_size == 100
        assert settings.governance_page_size == 100
        assert settings.governance_failure_threshold == 3
        snapshot = build_queue_startup_snapshot(
            profile=PlatformDeploymentProfile.PRODUCTION,
            queue_settings=settings,
            tenant_id="00000000-0000-0000-0000-000000000001",
            process_label="worker_abcd1234ef56",
        )
        assert snapshot["profile"] == "production"
        assert snapshot["mode"] == "event_assisted"
        assert snapshot["redis_env_names"] == (DAYU_PLATFORM_REDIS_ENV,)
        assert snapshot["tenant_id"] == "00000000-0000-0000-0000-000000000001"
        assert snapshot["process_label"] == "worker_abcd1234ef56"
        assert snapshot["schedule_candidate_scan_limit"] == 20000
        assert snapshot["governance_failure_threshold"] == 3

    @pytest.mark.unit
    def test_nondefault_governance_failure_threshold_is_strict_and_enters_safe_startup_snapshot(
        self,
    ) -> None:
        """非默认 governance failure threshold 严格解析并进入安全快照。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = load_platform_queue_settings(
            {DAYU_PLATFORM_QUEUE_GOVERNANCE_FAILURE_THRESHOLD: "5"},
            PlatformDeploymentProfile.PRODUCTION,
        )
        assert settings is not None
        assert settings.governance_failure_threshold == 5
        snapshot = build_queue_startup_snapshot(
            profile=PlatformDeploymentProfile.PRODUCTION,
            queue_settings=settings,
            tenant_id="00000000-0000-0000-0000-000000000001",
            process_label="worker_governance",
        )
        assert snapshot["governance_failure_threshold"] == 5
        for invalid_value in ("true", "3.0", "0", "-1"):
            with pytest.raises(PlatformSettingsError):
                load_platform_queue_settings(
                    {
                        DAYU_PLATFORM_QUEUE_GOVERNANCE_FAILURE_THRESHOLD: invalid_value
                    },
                    PlatformDeploymentProfile.PRODUCTION,
                )

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("mode", "event_assisted"),
            ("poll_interval_seconds", True),
            ("redis_health_interval_seconds", float("nan")),
            ("redis_failure_threshold", 0),
            ("shutdown_grace_seconds", -1.0),
            ("empty_poll_jitter_max_seconds", float("inf")),
            ("schedule_max_lookback_seconds", -604800),
            ("schedule_tick_batch_size", 0),
            ("governance_page_size", -1),
            ("governance_failure_threshold", 0),
        ],
    )
    def test_queue_settings_reject_bool_nan_infinity_zero_negative_and_unknown_profile(
        self,
        field: str,
        value: _QueueSettingTestValue,
    ) -> None:
        """bool/NaN/Infinity/零/负值与未知 profile 一律 fail-fast。

        Args:
            field: 待覆盖字段名。
            value: 非法字段值。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            self._settings(**{field: value})
        with pytest.raises(ValueError):
            PlatformDeploymentProfile("unsupported-profile")

    @pytest.mark.unit
    def test_queue_settings_scan_limit_lower_bound_includes_timezone_offset_margin(self) -> None:
        """scan limit 下限必须包含 timezone offset 边界余量。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = PlatformQueueSettings(mode=PlatformQueueMode.EVENT_ASSISTED)
        minimum = math.ceil(settings.schedule_max_lookback_seconds / 60) + 2882
        assert settings.schedule_candidate_scan_limit >= minimum
        with pytest.raises(PlatformSettingsError):
            self._settings(schedule_candidate_scan_limit=minimum - 1)

    @pytest.mark.unit
    def test_queue_settings_numeric_fields_reject_bool_and_non_exact_types(self) -> None:
        """float/int 字段必须 exact 类型（bool 冒充一律拒绝）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(PlatformSettingsError):
            self._settings(poll_interval_seconds=True)
        with pytest.raises(PlatformSettingsError):
            self._settings(redis_failure_threshold=True)
        with pytest.raises(PlatformSettingsError):
            self._settings(governance_page_size=3.5)
        with pytest.raises(PlatformSettingsError):
            self._settings(governance_failure_threshold=True)

    @pytest.mark.unit
    def test_load_queue_settings_derives_mode_from_profile_and_nondefault_values_change(self) -> None:
        """loader 唯一派生 mode，非默认合法值真实生效。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        production = load_platform_queue_settings(
            {
                DAYU_PLATFORM_QUEUE_POLL_INTERVAL_SECONDS: "2.5",
                DAYU_PLATFORM_QUEUE_REDIS_FAILURE_THRESHOLD: "5",
                DAYU_PLATFORM_QUEUE_REDIS_HEALTH_INTERVAL_SECONDS: "45",
            },
            PlatformDeploymentProfile.PRODUCTION,
        )
        assert production is not None
        assert production.mode is PlatformQueueMode.EVENT_ASSISTED
        assert production.poll_interval_seconds == 2.5
        assert production.redis_failure_threshold == 5
        assert production.redis_health_interval_seconds == 45.0
        integration = load_platform_queue_settings(
            {},
            PlatformDeploymentProfile.INTEGRATION,
        )
        assert integration is not None
        assert integration.mode is PlatformQueueMode.POSTGRES_POLLING
        assert load_platform_queue_settings(
            {}, PlatformDeploymentProfile.DEVELOPMENT
        ) is None
        with pytest.raises(PlatformSettingsError):
            load_platform_queue_settings(
                {DAYU_PLATFORM_QUEUE_POLL_INTERVAL_SECONDS: "abc"},
                PlatformDeploymentProfile.PRODUCTION,
            )
        with pytest.raises(PlatformSettingsError):
            load_platform_queue_settings(
                {DAYU_PLATFORM_QUEUE_POLL_INTERVAL_SECONDS: "-1"},
                PlatformDeploymentProfile.PRODUCTION,
            )

    @pytest.mark.unit
    def test_queue_startup_snapshot_derives_mode_and_env_names_from_profile(self) -> None:
        """snapshot 的 mode 与 Redis env tuple 必须从 closed profile 派生。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        integration_settings = PlatformQueueSettings(
            mode=PlatformQueueMode.POSTGRES_POLLING
        )
        integration_snapshot = build_queue_startup_snapshot(
            profile=PlatformDeploymentProfile.INTEGRATION,
            queue_settings=integration_settings,
            tenant_id="00000000-0000-0000-0000-000000000001",
            process_label="scheduler_abcd1234ef56",
        )
        assert integration_snapshot["mode"] == "postgres_polling"
        assert integration_snapshot["redis_env_names"] == ()
        with pytest.raises(PlatformSettingsError):
            build_queue_startup_snapshot(
                profile=PlatformDeploymentProfile.PRODUCTION,
                queue_settings=integration_settings,
                tenant_id="00000000-0000-0000-0000-000000000001",
                process_label="worker_abcd1234ef56",
            )
        with pytest.raises(PlatformSettingsError):
            build_queue_startup_snapshot(
                profile=PlatformDeploymentProfile.DEVELOPMENT,
                queue_settings=PlatformQueueSettings(
                    mode=PlatformQueueMode.EVENT_ASSISTED
                ),
                tenant_id="00000000-0000-0000-0000-000000000001",
                process_label="worker_abcd1234ef56",
            )

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "label",
        [
            "redis://user:secret@localhost:6379",
            "worker_abcd\n1234",
            "worker_abcd\t1234",
            "  worker_abcd",
            "worker_abcd  ",
            "worker_token_abcd",
            "abcd" * 17,
            "worker/path",
        ],
    )
    def test_queue_startup_snapshot_rejects_unsafe_process_labels(self, label: str) -> None:
        """URL/换行/空白/敏感标记/非法字符/超长 label 一律拒绝。

        Args:
            label: 不安全进程标签。

        Returns:
            无。

        Raises:
            无。
        """

        settings = PlatformQueueSettings(mode=PlatformQueueMode.EVENT_ASSISTED)
        with pytest.raises(PlatformSettingsError):
            build_queue_startup_snapshot(
                profile=PlatformDeploymentProfile.PRODUCTION,
                queue_settings=settings,
                tenant_id="00000000-0000-0000-0000-000000000001",
                process_label=label,
            )

    @pytest.mark.unit
    def test_queue_startup_snapshot_rejects_invalid_tenant_uuid(self) -> None:
        """非 canonical UUID 的 tenant 值必须拒绝。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        settings = PlatformQueueSettings(mode=PlatformQueueMode.EVENT_ASSISTED)
        with pytest.raises(ValueError):
            build_queue_startup_snapshot(
                profile=PlatformDeploymentProfile.PRODUCTION,
                queue_settings=settings,
                tenant_id="not-a-uuid",
                process_label="worker_abcd1234ef56",
            )
        with pytest.raises(ValueError):
            build_queue_startup_snapshot(
                profile=PlatformDeploymentProfile.PRODUCTION,
                queue_settings=settings,
                tenant_id=_TenantText(
                    "00000000-0000-0000-0000-000000000001"
                ),
                process_label="worker_abcd1234ef56",
            )

    @pytest.mark.unit
    def test_integration_profile_requires_only_postgres_and_rejects_redis_object_and_auth_env(self) -> None:
        """integration profile 必须且只允许 PostgreSQL DSN 环境变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        integration_env: dict[str, str] = {
            DAYU_PLATFORM_ENABLED_ENV: "true",
            DAYU_PLATFORM_PROFILE_ENV: "integration",
            DAYU_PLATFORM_POSTGRES_DSN_ENV: "postgres://user@localhost/dayu",
        }
        settings = load_platform_settings(integration_env)
        assert settings.profile is PlatformDeploymentProfile.INTEGRATION
        assert settings.use_in_memory_adapters is False
        for env_var in (
            DAYU_PLATFORM_REDIS_ENV,
            DAYU_PLATFORM_OBJECT_STORAGE_ENV,
            DAYU_PLATFORM_AUTH_KEY_ENV,
        ):
            with pytest.raises(PlatformSettingsError):
                load_platform_settings({**integration_env, env_var: "configured"})
        missing_dsn = {
            DAYU_PLATFORM_ENABLED_ENV: "true",
            DAYU_PLATFORM_PROFILE_ENV: "integration",
        }
        with pytest.raises(PlatformSettingsError):
            load_platform_settings(missing_dsn)
        in_memory_env = {
            **integration_env,
            DAYU_PLATFORM_USE_IN_MEMORY_ENV: "true",
        }
        with pytest.raises(PlatformSettingsError):
            load_platform_settings(in_memory_env)
