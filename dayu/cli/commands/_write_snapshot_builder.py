"""为写作配置事务构造延迟执行的路由快照回调。"""

from __future__ import annotations

import argparse
import functools
from collections.abc import Callable, Mapping

from dayu.cli.commands._write_config_application import (
    _build_fresh_application_routing_snapshot,
)
from dayu.cli.dependency_setup import WorkspaceConfig
from dayu.contracts.model_config import ModelConfigJsonValue
from dayu.execution.options import ExecutionOptions


def _build_snapshot_for_args(
    args: argparse.Namespace,
    *,
    paths_config: WorkspaceConfig,
    execution_options: ExecutionOptions,
    run_label: str = "configuration-application",
) -> Mapping[str, ModelConfigJsonValue]:
    """使用已绑定的 CLI 参数构建一次最新路由快照。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        execution_options: 本次写作请求的执行选项。
        run_label: 写作体检日志标签。

    Returns:
        当前写作配置解析得到的路由快照。

    Raises:
        Exception: 即时路由快照构建失败时原样传播。
    """

    return _build_fresh_application_routing_snapshot(
        args=args,
        paths_config=paths_config,
        execution_options=execution_options,
        run_label=run_label,
    )


def build_snapshot_builder(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_options: ExecutionOptions,
    run_label: str = "configuration-application",
) -> Callable[[], Mapping[str, ModelConfigJsonValue]]:
    """绑定一次路由快照构建所需参数并返回零参数回调。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        execution_options: 本次写作请求的执行选项。
        run_label: 写作体检日志标签。

    Returns:
        调用时构建最新路由快照的零参数回调。

    Raises:
        本函数不显式抛出异常。
    """

    return functools.partial(
        _build_snapshot_for_args,
        args,
        paths_config=paths_config,
        execution_options=execution_options,
        run_label=run_label,
    )
