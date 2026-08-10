"""Fins toolset adapter（runtime-bound 装配函数）。

本模块不再从 workspace 路径自造缓存 runtime（S14-CTRL-11），改为
``build_fins_toolset_registrars(runtime)`` 返回只读映射：

- 键为 ``fins`` 与 ``ingestion``，值是持有已装配 runtime 的 typed frozen
  callable（模块级私有函数 + ``functools.partial`` 绑定 runtime）；
- ``fins`` 闭包执行 ``build_fins_tool_limits`` + ``register_fins_read_tools``；
- ``ingestion`` 闭包执行 ``build_ingestion_service_factory`` +
  ``get_ingestion_manager_key``；
- 无任何模块级可变状态、无 runtime 缓存；startup 是构造 toolset override 的
  唯一位置。
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from types import MappingProxyType

from dayu.contracts.tool_configs import build_fins_tool_limits
from dayu.contracts.toolset_registrar import (
    ToolsetRegistrarProtocol,
    ToolsetRegistrationContext,
)
from dayu.engine.tool_registry import ToolRegistry
from dayu.fins.service_runtime import FinsRuntimeProtocol
from dayu.fins.tools.fins_tools import register_fins_ingestion_tools, register_fins_read_tools

_FINS_TOOLSET_NAME = "fins"
_INGESTION_TOOLSET_NAME = "ingestion"


def _register_fins_read_toolset(
    runtime: FinsRuntimeProtocol,
    context: ToolsetRegistrationContext,
) -> int:
    """注册 fins 读取 toolset（绑定指定 runtime）。

    Args:
        runtime: 已装配的 Fins runtime。
        context: toolset 注册上下文。

    Returns:
        实际注册的工具数量。

    Raises:
        无。
    """

    registry = context.registry
    if not isinstance(registry, ToolRegistry):
        raise RuntimeError("fins toolset 注册需要 ToolRegistry 实现")
    fins_tool_limits = build_fins_tool_limits(context.toolset_config)
    before_count = len(registry.tools)
    register_fins_read_tools(
        registry,
        service=runtime.get_tool_service(
            processor_cache_max_entries=fins_tool_limits.processor_cache_max_entries
        ),
        limits=fins_tool_limits,
        timeout_budget=context.tool_timeout_seconds,
    )
    return len(registry.tools) - before_count


def _register_fins_ingestion_toolset(
    runtime: FinsRuntimeProtocol,
    context: ToolsetRegistrationContext,
) -> int:
    """注册 fins ingestion toolset（绑定指定 runtime）。

    Args:
        runtime: 已装配的 Fins runtime。
        context: toolset 注册上下文。

    Returns:
        实际注册的工具数量。

    Raises:
        无。
    """

    registry = context.registry
    if not isinstance(registry, ToolRegistry):
        raise RuntimeError("fins toolset 注册需要 ToolRegistry 实现")
    before_count = len(registry.tools)
    register_fins_ingestion_tools(
        registry,
        service_factory=runtime.build_ingestion_service_factory(),
        manager_key=runtime.get_ingestion_manager_key(),
        timeout_budget=context.tool_timeout_seconds,
    )
    return len(registry.tools) - before_count


def build_fins_toolset_registrars(
    runtime: FinsRuntimeProtocol,
) -> Mapping[str, ToolsetRegistrarProtocol]:
    """按已装配 runtime 构造只读 toolset override 映射。

    Args:
        runtime: 已装配的 Fins runtime（S3 模式下即 S3-backed 唯一 runtime）。

    Returns:
        只读映射：``{"fins": callable, "ingestion": callable}``。

    Raises:
        无。
    """

    return MappingProxyType(
        {
            _FINS_TOOLSET_NAME: partial(_register_fins_read_toolset, runtime),
            _INGESTION_TOOLSET_NAME: partial(_register_fins_ingestion_toolset, runtime),
        }
    )


__all__ = ["build_fins_toolset_registrars"]
