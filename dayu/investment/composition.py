"""投资平台组合契约定义。

本模块定义平台组合根的纯契约，保持标准库依赖、不依赖任何上层包：

- ``PlatformServiceProtocol`` 是平台可对外暴露 Service 的非空稳定契约，
  携带只读 ``platform_service_name``；任意无该属性的值都无法通过
  运行时结构检查，杜绝把裸字符串 / dict / 任意对象当作 Service 注入；
- ``PlatformCompositionProviderProtocol`` 是组合提供者契约；
- ``PlatformComposition`` 是只承载 ``PlatformServiceProtocol`` 实例的
  组合根：构造期对注册键 / Service 名称 / 值做严格校验，并把内部映射
  防御性快照为只读 ``MappingProxyType``，外部后续修改原映射不影响
  组合根；任意 str / dict / 无协议值、空 / 仅空白 / 键名不匹配一律
  fail closed；
- ``disabled()`` 表达"平台禁用"状态，``empty()`` 表达"已启用但尚无
  Service 可暴露"的空状态。

协议契约与组合根的绑定都在本纯层完成；上层（``dayu.startup.platform``
与 ``dayu.services.startup_preparation``）只消费本模块导出的稳定契约，
因此不构成对上层包的反向依赖。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, Protocol, TypeVar, runtime_checkable


@runtime_checkable
class PlatformServiceProtocol(Protocol):
    """平台可对外暴露的 Service 稳定契约。

    任何暴露给平台组合根的 Service 都必须携带只读
    ``platform_service_name``，供注册键与名称的一致性校验使用。
    以只读 property 声明，保证 frozen dataclass / property 等
    不可变实现可直接满足该契约。
    """

    @property
    def platform_service_name(self) -> str:
        """返回该 Service 对外注册的稳定名称。"""
        ...


@runtime_checkable
class PlatformCompositionProviderProtocol(Protocol):
    """平台组合提供者契约。

    提供者负责把平台配置与持久化基础设施装配成对外可见的
    ``PlatformServiceProtocol`` 实例集合；组合根只接收/暴露本协议产出的
    Service 协议实例，不暴露 repository / ORM / adapter。本 slice 只
    定义契约，不提供任何真实实现。
    """

    def provide_services(self) -> Mapping[str, PlatformServiceProtocol]:
        """返回平台对外暴露的 Service 协议实例集合。

        Args:
            无。

        Returns:
            service 注册名到 ``PlatformServiceProtocol`` 实例的映射；
            当前 slice 尚无真实 Service，真实实现恒返回空映射。

        Raises:
            无。
        """
        ...


class PlatformCompositionContractError(ValueError):
    """平台组合根构造违反严格契约时抛出的错误。"""


ServiceProtocolT = TypeVar("ServiceProtocolT", bound=PlatformServiceProtocol, covariant=True)


@dataclass(frozen=True)
class PlatformComposition(Generic[ServiceProtocolT]):
    """平台组合根：只接收/暴露 Service 协议实例。

    Args:
        enabled: 平台是否启用；禁用组合不得暴露任何 Service。
        services: 对外暴露的 Service 协议实例映射，键必须是合法
            service 注册名且与对应实例的 ``platform_service_name``
            一致；构造后内部映射被防御性快照为只读。
    """

    enabled: bool
    services: Mapping[str, ServiceProtocolT]

    def __post_init__(self) -> None:
        """构造后执行严格校验并防御性快照 service 注册。

        Args:
            无。

        Returns:
            无。

        Raises:
            PlatformCompositionContractError: 注册键或 Service 值违反
                严格契约时抛出。
        """

        if not isinstance(self.enabled, bool):
            raise PlatformCompositionContractError("enabled 必须是布尔值")
        if not isinstance(self.services, Mapping):
            raise PlatformCompositionContractError("services 必须是 Mapping")
        registry = dict(self.services)
        if self.enabled:
            for key, value in registry.items():
                _validate_registry_entry(key, value)
        elif registry:
            raise PlatformCompositionContractError(
                "平台禁用状态不得暴露任何 Service 注册"
            )
        super(PlatformComposition, self).__setattr__(
            "services", MappingProxyType(registry)
        )

    @classmethod
    def disabled(cls: type[PlatformComposition[ServiceProtocolT]]) -> PlatformComposition[ServiceProtocolT]:
        """构造平台禁用状态的组合根。

        Args:
            无。

        Returns:
            携带 ``enabled=False`` 与空 service 注册的组合根。

        Raises:
            无。
        """

        return cls(enabled=False, services={})

    @classmethod
    def empty(cls: type[PlatformComposition[ServiceProtocolT]]) -> PlatformComposition[ServiceProtocolT]:
        """构造已启用但尚无 Service 可暴露的空组合根。

        Args:
            无。

        Returns:
            携带 ``enabled=True`` 与空 service 注册的组合根。

        Raises:
            无。
        """

        return cls(enabled=True, services={})


def _validate_registry_entry(key: str, value: PlatformServiceProtocol) -> None:
    """校验单个 service 注册条目的键、名称与值。

    规则：

    - 注册键必须是非空且无首尾空白的字符串；
    - 值必须结构满足 ``PlatformServiceProtocol``；
    - 值的 ``platform_service_name`` 必须是非空且无首尾空白的字符串；
    - 注册键必须与 ``platform_service_name`` 一致。

    异常消息只报告违反的规则，不格式化任何候选值，避免把不可信输入
    回显到日志或错误上报。

    Args:
        key: service 注册键。
        value: 待校验的 Service 协议实例。

    Returns:
        无。

    Raises:
        PlatformCompositionContractError: 键、名称或值违反严格契约时抛出。
    """

    if not isinstance(key, str) or not key.strip() or key != key.strip():
        raise PlatformCompositionContractError(
            "service 注册键必须是非空且无首尾空白的字符串"
        )
    if not isinstance(value, PlatformServiceProtocol):
        raise PlatformCompositionContractError(
            "service 注册值必须是 PlatformServiceProtocol 实例"
        )
    service_name = value.platform_service_name
    if (
        not isinstance(service_name, str)
        or not service_name.strip()
        or service_name != service_name.strip()
    ):
        raise PlatformCompositionContractError(
            "service 注册值的 platform_service_name 必须是非空且无首尾空白的字符串"
        )
    if key != service_name:
        raise PlatformCompositionContractError(
            "service 注册键必须与 platform_service_name 一致"
        )


__all__ = [
    "PlatformComposition",
    "PlatformCompositionContractError",
    "PlatformCompositionProviderProtocol",
    "PlatformServiceProtocol",
]
