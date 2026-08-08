"""写作模型配置应用与即时路由快照构建。"""

from __future__ import annotations

import argparse
import functools
from collections.abc import Mapping
from datetime import UTC, datetime

from dayu.cli.arguments import DayuCliArguments
from dayu.cli.commands._write_config_helpers import (
    MODULE,
    _build_write_run_config,
    _log_write_preflight_result,
)
from dayu.cli.dependency_setup import (
    RunningConfig,
    WorkspaceConfig,
    _build_write_service,
    _prepare_cli_host_dependencies,
    setup_write_config,
)
from dayu.contracts.model_config import ModelConfigJsonValue
from dayu.execution.options import ExecutionOptions
from dayu.log import Log
from dayu.services.contracts import WriteRequest
from dayu.services.write_model_configuration_application import (
    WriteModelConfigurationApplicationBlockedError,
    WriteModelConfigurationApplicationBusyError,
    WriteModelConfigurationApplicationReceiptError,
    apply_write_model_configuration_preapplication_plan,
    format_write_model_configuration_application_receipt_report,
)
from dayu.services.write_model_configuration_preapplication import (
    build_write_scene_model_routing_snapshot,
)


def _build_fresh_application_routing_snapshot(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_options: ExecutionOptions,
    run_label: str = "configuration-application",
) -> Mapping[str, ModelConfigJsonValue]:
    """解析一次不复用缓存的写作路由快照且不执行模型调用。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        execution_options: 本次写作请求的执行选项。
        run_label: 写作体检日志标签。

    Returns:
        当前写作配置解析得到的路由快照。

    Raises:
        WriteModelConfigurationApplicationBlockedError: 写作体检未通过时抛出。
        Exception: 依赖装配、配置解析、体检或快照构建失败时原样传播。
    """

    (
        workspace,
        default_execution_options,
        scene_execution_acceptance_preparer,
        host,
        fins_runtime,
    ) = _prepare_cli_host_dependencies(
        workspace_config=paths_config,
        execution_options=execution_options,
        interactive=False,
    )
    running_config = RunningConfig.from_resolved(default_execution_options)
    service = _build_write_service(
        host=host,
        workspace=workspace,
        scene_execution_acceptance_preparer=scene_execution_acceptance_preparer,
        fins_runtime=fins_runtime,
    )
    write_cli_config = setup_write_config(
        args,
        paths_config,
        running_config,
    )
    ticker = str(paths_config.ticker or "").strip()
    write_config = _build_write_run_config(
        ticker=ticker,
        company_name=ticker,
        write_cli_config=write_cli_config,
        write_model_override_name="",
    )
    result = service.preflight(WriteRequest(write_config=write_config))
    _log_write_preflight_result(
        result,
        run_label=run_label,
    )
    if not result.ready:
        raise WriteModelConfigurationApplicationBlockedError(
            "fresh write preflight failed"
        )
    return build_write_scene_model_routing_snapshot(
        config_root=paths_config.config_root,
        write_config=write_config,
        preflight_result=result,
    )


def _run_write_model_configuration_application(
    *,
    args: DayuCliArguments,
    paths_config: WorkspaceConfig,
    execution_options: ExecutionOptions,
) -> int:
    """执行一次单次使用的模型路由配置应用事务。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        execution_options: 本次写作请求的执行选项。

    Returns:
        应用成功返回 0，门禁阻断或回滚返回 4，回执失败返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    plan_path = str(
        getattr(
            args,
            "challenger_config_application_plan_input",
            "",
        )
        or ""
    ).strip()
    approval_path = str(
        getattr(
            args,
            "challenger_config_change_approval_input",
            "",
        )
        or ""
    ).strip()
    receipt_path = str(
        getattr(
            args,
            "challenger_config_application_receipt_output",
            "",
        )
        or ""
    ).strip()

    snapshot_builder = functools.partial(
        _build_fresh_application_routing_snapshot,
        args=args,
        paths_config=paths_config,
        execution_options=execution_options,
    )

    try:
        receipt = apply_write_model_configuration_preapplication_plan(
            plan_path=plan_path,
            approval_path=approval_path,
            workspace_dir=paths_config.workspace_dir,
            receipt_output_path=receipt_path,
            snapshot_builder=snapshot_builder,
            now=datetime.now(UTC),
        )
    except (
        WriteModelConfigurationApplicationBlockedError,
        WriteModelConfigurationApplicationBusyError,
    ) as exc:
        Log.error(
            f"Configuration application gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationApplicationReceiptError as exc:
        Log.error(
            f"Configuration application receipt export failed: {exc}",
            module=MODULE,
        )
        return 6
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Configuration application failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_application_receipt_report(receipt):
        print(line)
    status = receipt.get("status")
    if status == "applied":
        return 0
    if status == "rolled_back":
        return 4
    return 6
