"""写作 CLI 的配置回滚编排。"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from dayu.cli.commands._write_config_helpers import MODULE
from dayu.cli.commands._write_snapshot_builder import build_snapshot_builder
from dayu.cli.dependency_setup import WorkspaceConfig
from dayu.execution.options import ExecutionOptions
from dayu.log import Log
from dayu.services.write_model_configuration_application import (
    WriteModelConfigurationApplicationBlockedError,
)
from dayu.services.write_model_configuration_rollback_application import (
    WriteModelConfigurationRollbackApplicationBlockedError,
    WriteModelConfigurationRollbackApplicationBusyError,
    WriteModelConfigurationRollbackReceiptError,
    apply_write_model_configuration_operator_rollback,
    format_write_model_configuration_operator_rollback_receipt_report,
)


def _run_write_model_configuration_rollback(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_options: ExecutionOptions,
) -> int:
    """执行一次单次使用的精确字节配置回滚。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        execution_options: 本次写作请求的执行选项。

    Returns:
        回滚成功返回 0，门禁阻断或前滚返回 4，回执失败返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    plan_path = str(
        getattr(
            args,
            "challenger_config_rollback_plan_input",
            "",
        )
        or ""
    ).strip()
    approval_path = str(
        getattr(
            args,
            "challenger_config_rollback_approval_input",
            "",
        )
        or ""
    ).strip()
    receipt_path = str(
        getattr(
            args,
            "challenger_config_rollback_receipt_output",
            "",
        )
        or ""
    ).strip()

    snapshot_builder = build_snapshot_builder(
        args=args,
        paths_config=paths_config,
        execution_options=execution_options,
    )

    try:
        receipt = apply_write_model_configuration_operator_rollback(
            rollback_plan_path=plan_path,
            rollback_approval_path=approval_path,
            workspace_dir=paths_config.workspace_dir,
            receipt_output_path=receipt_path,
            snapshot_builder=snapshot_builder,
            now=datetime.now(UTC),
        )
    except (
        WriteModelConfigurationApplicationBlockedError,
        WriteModelConfigurationRollbackApplicationBlockedError,
        WriteModelConfigurationRollbackApplicationBusyError,
    ) as exc:
        Log.error(
            f"Configuration operator rollback gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationRollbackReceiptError as exc:
        Log.error(
            f"Configuration rollback receipt export failed: {exc}",
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
            f"Configuration operator rollback failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_operator_rollback_receipt_report(receipt):
        print(line)
    status = receipt.get("status")
    if status == "rolled_back":
        return 0
    if status == "rolled_forward":
        return 4
    return 6
