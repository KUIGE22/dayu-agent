"""定义 write 命令分阶段分派所需的不可变类型边界。

本模块只承载 Phase A/B 的上下文与条目数据结构，不依赖具体 runner，也不负责
执行分派或构造运行时依赖。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dayu.cli.arguments import DayuCliArguments, WriteDispatchArguments
from dayu.cli.dependency_setup import WorkspaceConfig
from dayu.execution.options import ExecutionOptions


@dataclass(frozen=True)
class _WriteCommandContext:
    """承载 Phase A runner 需要的参数与工作区配置。"""

    args: DayuCliArguments
    paths_config: WorkspaceConfig


@dataclass(frozen=True)
class _WriteConfigurationContext:
    """承载 Phase B runner 复用的模型覆盖与执行选项。"""

    args: DayuCliArguments
    paths_config: WorkspaceConfig
    write_model_override_name: str
    execution_options: ExecutionOptions


@dataclass(frozen=True)
class _EarlyWriteSubcommandEntry:
    """声明 Phase A predicate 与 runner 的稳定配对。"""

    predicate: Callable[[WriteDispatchArguments], bool]
    runner: Callable[[_WriteCommandContext], int]


@dataclass(frozen=True)
class _ConfigurationWriteSubcommandEntry:
    """声明 Phase B predicate 与 runner 的稳定配对。"""

    predicate: Callable[[WriteDispatchArguments], bool]
    runner: Callable[[_WriteConfigurationContext], int]
