"""启动期平台组合注入点。

本模块是投资平台的 startup 注入点：接收已解析的 ``PlatformSettings``
与组合提供者，构建只承载 ``PlatformServiceProtocol`` 实例的平台组合根。

组合根契约（``PlatformComposition`` / ``PlatformServiceProtocol`` /
``PlatformCompositionProviderProtocol``）全部定义在纯层
``dayu.investment.composition``，本模块只依赖纯层契约，不导入
``dayu.services`` 任何模块，因此 ``import dayu.startup.platform``
在全新解释器中可直接成功，不依赖调用方先导入 Service 包。

平台启用时：

- 未注入提供者或提供者不满足组合提供者协议，fail-fast 抛
  ``PlatformCompositionError``；
- 提供者产出的 service 注册违反组合契约时，契约异常被转换为稳定的
  ``PlatformCompositionError``，不把内部候选值回显到错误消息；
- 提供者自身抛出的异常原样传播（允许原始异常类型），由装配方保证
  发生在任何 Host / Fins 副作用之前。

本 slice 不导入或构造任何尚不存在的 PG / Fins / job repository。
"""

from __future__ import annotations

from dayu.investment.composition import (
    PlatformComposition,
    PlatformCompositionContractError,
    PlatformCompositionProviderProtocol,
    PlatformServiceProtocol,
)
from dayu.investment.config import PlatformSettings


class PlatformCompositionError(RuntimeError):
    """平台组合装配失败时抛出的错误。"""


def build_platform_composition(
    *,
    settings: PlatformSettings,
    provider: PlatformCompositionProviderProtocol | None = None,
) -> PlatformComposition[PlatformServiceProtocol]:
    """按平台设置与组合提供者构建平台组合根。

    Args:
        settings: 已解析的平台严格设置。
        provider: 平台组合提供者；平台启用时必须注入满足组合提供者
            协议的有效实例，禁用时可为 ``None``。

    Returns:
        只承载 ``PlatformServiceProtocol`` 实例的平台组合根；平台禁用
        时返回 ``enabled=False`` 的禁用组合根且不触碰提供者。

    Raises:
        PlatformCompositionError: 平台启用但未注入提供者、提供者不满
            足组合提供者协议，或提供者产出的 service 注册违反组合
            契约时抛出。
    """

    if not settings.enabled:
        return PlatformComposition.disabled()
    if provider is None or not isinstance(provider, PlatformCompositionProviderProtocol):
        raise PlatformCompositionError(
            "平台已启用但未注入有效的组合提供者（PlatformCompositionProviderProtocol）"
        )
    services = provider.provide_services()
    try:
        return PlatformComposition(enabled=True, services=services)
    except PlatformCompositionContractError as error:
        raise PlatformCompositionError(
            "平台组合契约非法：提供者产出的 service 注册不满足 PlatformServiceProtocol 契约"
        ) from error


__all__ = [
    "PlatformCompositionError",
    "build_platform_composition",
]
