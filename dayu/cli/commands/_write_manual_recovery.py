"""模型配置手工恢复命令及正常写作恢复门禁。"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from dayu.cli.commands._write_config_helpers import MODULE
from dayu.cli.commands._write_snapshot_builder import build_snapshot_builder
from dayu.cli.dependency_setup import WorkspaceConfig
from dayu.execution.options import ExecutionOptions
from dayu.log import Log
from dayu.services.write_model_configuration_application import (
    WriteModelConfigurationApplicationBlockedError,
)
from dayu.services.write_model_configuration_manual_recovery import (
    build_write_model_configuration_manual_recovery_approval,
    build_write_model_configuration_manual_recovery_plan,
    format_write_model_configuration_manual_recovery_approval_report,
    format_write_model_configuration_manual_recovery_plan_report,
    persist_write_model_configuration_manual_recovery_approval,
    persist_write_model_configuration_manual_recovery_plan,
)
from dayu.services.write_model_configuration_manual_recovery_application import (
    WriteModelConfigurationManualRecoveryApplicationBlockedError,
    WriteModelConfigurationManualRecoveryApplicationBusyError,
    WriteModelConfigurationManualRecoveryReceiptError,
    apply_write_model_configuration_manual_recovery,
    format_write_model_configuration_manual_recovery_receipt_report,
    write_model_configuration_manual_recovery_transaction_root,
)
from dayu.services.write_model_configuration_manual_recovery_clearance import (
    WriteModelConfigurationManualRecoveryAuditTimelineChangedError,
    WriteModelConfigurationManualRecoveryClearanceBlockedError,
    WriteModelConfigurationManualRecoveryClearanceBusyError,
    WriteModelConfigurationManualRecoveryClearanceReceiptError,
    WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError,
    WriteModelConfigurationManualRecoveryClearanceRevocationBusyError,
    WriteModelConfigurationManualRecoveryClearanceRevocationReceiptError,
    WriteModelConfigurationManualRecoveryGateVerificationChangedError,
    WriteModelConfigurationManualRecoveryGateVerificationEvidenceError,
    WriteModelConfigurationManualRecoveryRestartBlockedError,
    WriteModelConfigurationManualRecoveryRestartBusyError,
    assess_write_model_configuration_manual_recovery_gate,
    build_write_model_configuration_manual_recovery_audit_timeline,
    format_write_model_configuration_manual_recovery_audit_timeline_report,
    format_write_model_configuration_manual_recovery_clearance_report,
    format_write_model_configuration_manual_recovery_clearance_revocation_report,
    format_write_model_configuration_manual_recovery_gate_report,
    format_write_model_configuration_manual_recovery_gate_verification_report,
    issue_write_model_configuration_manual_recovery_clearance,
    persist_write_model_configuration_manual_recovery_audit_timeline,
    persist_write_model_configuration_manual_recovery_gate,
    persist_write_model_configuration_manual_recovery_gate_verification,
    restart_write_model_configuration_manual_recovery_after_clearance_revocation,
    revoke_write_model_configuration_manual_recovery_clearance,
    verify_write_model_configuration_manual_recovery_gate_snapshot,
)
from dayu.services.write_model_configuration_manual_recovery_gate_revalidation import (
    format_write_model_configuration_manual_recovery_gate_revalidation_report,
    persist_write_model_configuration_manual_recovery_gate_revalidation,
    revalidate_write_model_configuration_manual_recovery_gate_verification,
)
from dayu.services.write_model_configuration_manual_recovery_incident_dossier import (
    WriteModelConfigurationManualRecoveryIncidentNotFoundError,
    build_write_model_configuration_manual_recovery_incident_dossier,
    format_write_model_configuration_manual_recovery_incident_dossier_report,
    persist_write_model_configuration_manual_recovery_incident_dossier,
)
from dayu.services.write_model_configuration_manual_recovery_incident_dossier_revalidation import (
    WriteModelConfigurationManualRecoveryIncidentDossierChangedError,
    WriteModelConfigurationManualRecoveryIncidentDossierEvidenceError,
    format_write_model_configuration_manual_recovery_incident_dossier_revalidation_report,
    persist_write_model_configuration_manual_recovery_incident_dossier_revalidation,
    revalidate_write_model_configuration_manual_recovery_incident_dossier,
)
from dayu.services.write_model_configuration_manual_recovery_verification import (
    WriteModelConfigurationManualRecoveryVerificationBlockedError,
    WriteModelConfigurationManualRecoveryVerificationBusyError,
    format_write_model_configuration_manual_recovery_verification_report,
    verify_write_model_configuration_manual_recovery_receipt,
)
from dayu.services.write_model_configuration_rollback import (
    WriteModelConfigurationRollbackBlockedError,
)
from dayu.services.write_model_configuration_rollback_application import (
    build_write_model_configuration_manual_recovery_evidence,
    format_write_model_configuration_manual_recovery_evidence_report,
    persist_write_model_configuration_manual_recovery_evidence,
)


def _run_write_model_configuration_manual_recovery_evidence(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """导出一次回滚恢复失败的不可变证据。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        导出成功返回 0，门禁阻断返回 4，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    receipt_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_receipt_input",
            "",
        )
        or ""
    ).strip()
    evidence_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_evidence_output",
            "",
        )
        or ""
    ).strip()
    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery evidence export requires a config root",
            module=MODULE,
        )
        return 2
    try:
        evidence = build_write_model_configuration_manual_recovery_evidence(
            rollback_receipt_path=receipt_path,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
            now=datetime.now(UTC),
        )
        persisted_path = persist_write_model_configuration_manual_recovery_evidence(
            evidence,
            evidence_path,
        )
    except WriteModelConfigurationRollbackBlockedError as exc:
        Log.error(
            f"Manual recovery evidence gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery evidence export failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_evidence_report(evidence):
        print(line)
    print(f"  Evidence file : {persisted_path}")
    return 0


def _run_write_model_configuration_manual_recovery_plan(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """为一次明确的人工选择构建精确恢复计划。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        计划持久化成功返回 0，门禁阻断返回 4，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    evidence_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_evidence_input",
            "",
        )
        or ""
    ).strip()
    selection_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_selection_request",
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_plan_output",
            "",
        )
        or ""
    ).strip()
    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery planning requires a config root",
            module=MODULE,
        )
        return 2
    try:
        plan = build_write_model_configuration_manual_recovery_plan(
            manual_recovery_evidence_path=evidence_path,
            selection_request_path=selection_path,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
            now=datetime.now(UTC),
        )
        persisted_path = persist_write_model_configuration_manual_recovery_plan(
            plan,
            output_path,
        )
    except WriteModelConfigurationRollbackBlockedError as exc:
        Log.error(
            f"Manual recovery planning gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery planning failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_plan_report(plan):
        print(line)
    print(f"  Plan file     : {persisted_path}")
    return 0


def _run_write_model_configuration_manual_recovery_approval(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """签发一份独立且短时效的手工恢复批准。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        批准持久化成功返回 0，门禁阻断返回 4，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    plan_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_plan_input",
            "",
        )
        or ""
    ).strip()
    request_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_approval_request",
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_approval_output",
            "",
        )
        or ""
    ).strip()
    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery approval requires a config root",
            module=MODULE,
        )
        return 2
    try:
        approval = build_write_model_configuration_manual_recovery_approval(
            approval_request_path=request_path,
            manual_recovery_plan_path=plan_path,
            config_root=config_root,
            now=datetime.now(UTC),
        )
        persisted_path = persist_write_model_configuration_manual_recovery_approval(
            approval,
            output_path,
        )
    except WriteModelConfigurationRollbackBlockedError as exc:
        Log.error(
            f"Manual recovery approval gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery approval failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_approval_report(approval):
        print(line)
    print(f"  Approval file : {persisted_path}")
    return 0


def _run_write_model_configuration_manual_recovery_application(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_options: ExecutionOptions,
) -> int:
    """消费一次批准并仅恢复批准选择的精确配置状态。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        execution_options: 本次写作请求的执行选项。

    Returns:
        恢复成功返回 0，门禁阻断或起始状态恢复返回 4，回执失败返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    plan_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_plan_input",
            "",
        )
        or ""
    ).strip()
    approval_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_approval_input",
            "",
        )
        or ""
    ).strip()
    receipt_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_receipt_output",
            "",
        )
        or ""
    ).strip()
    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery execution requires a config root",
            module=MODULE,
        )
        return 2

    snapshot_builder = build_snapshot_builder(
        args=args,
        paths_config=paths_config,
        execution_options=execution_options,
    )

    try:
        receipt = apply_write_model_configuration_manual_recovery(
            manual_recovery_plan_path=plan_path,
            manual_recovery_approval_path=approval_path,
            config_root=config_root,
            workspace_dir=paths_config.workspace_dir,
            receipt_output_path=receipt_path,
            snapshot_builder=snapshot_builder,
            now=datetime.now(UTC),
        )
    except (
        WriteModelConfigurationManualRecoveryApplicationBlockedError,
        WriteModelConfigurationManualRecoveryApplicationBusyError,
    ) as exc:
        Log.error(
            f"Manual recovery execution gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryReceiptError as exc:
        Log.error(
            f"Manual recovery receipt export failed: {exc}",
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
            f"Manual recovery execution failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_receipt_report(receipt):
        print(line)
    status = receipt.get("status")
    if status == "recovered":
        return 0
    if status == "starting_state_restored":
        return 4
    return 6


def _run_write_model_configuration_manual_recovery_verification(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_options: ExecutionOptions,
) -> int:
    """独立验证手工恢复回执与当前配置状态。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        execution_options: 本次写作请求的执行选项。

    Returns:
        当前状态匹配返回 0，路由变化或起始状态当前返回 4，其他验证状态返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    receipt_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_verification_receipt_input",
            "",
        )
        or ""
    ).strip()
    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery verification requires a config root",
            module=MODULE,
        )
        return 2

    snapshot_builder = build_snapshot_builder(
        args=args,
        paths_config=paths_config,
        execution_options=execution_options,
        run_label="configuration-manual-recovery-verification",
    )

    try:
        verification = verify_write_model_configuration_manual_recovery_receipt(
            manual_recovery_receipt_path=receipt_path,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
            snapshot_builder=snapshot_builder,
        )
    except (
        WriteModelConfigurationApplicationBlockedError,
        WriteModelConfigurationManualRecoveryVerificationBlockedError,
        WriteModelConfigurationManualRecoveryVerificationBusyError,
    ) as exc:
        Log.error(
            f"Manual recovery verification gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery verification failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_verification_report(verification):
        print(line)
    status = verification.get("status")
    if status == "current":
        return 0
    if status in {
        "routing_changed",
        "starting_state_current",
    }:
        return 4
    return 6


def _run_write_model_configuration_manual_recovery_clearance(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_options: ExecutionOptions,
) -> int:
    """验证并持久清除最新已恢复配置事件。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        execution_options: 本次写作请求的执行选项。

    Returns:
        清除成功返回 0，门禁阻断返回 4，回执失败返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    receipt_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_clearance_receipt_input",
            "",
        )
        or ""
    ).strip()
    request_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_clearance_request",
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_clearance_output",
            "",
        )
        or ""
    ).strip()
    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery clearance requires a config root",
            module=MODULE,
        )
        return 2

    snapshot_builder = build_snapshot_builder(
        args=args,
        paths_config=paths_config,
        execution_options=execution_options,
        run_label="configuration-manual-recovery-clearance",
    )

    try:
        clearance = issue_write_model_configuration_manual_recovery_clearance(
            clearance_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
            clearance_output_path=output_path,
            snapshot_builder=snapshot_builder,
            now=datetime.now(UTC),
        )
    except WriteModelConfigurationManualRecoveryClearanceReceiptError as exc:
        Log.error(
            f"Manual recovery clearance export failed: {exc}",
            module=MODULE,
        )
        return 6
    except (
        WriteModelConfigurationApplicationBlockedError,
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        WriteModelConfigurationManualRecoveryClearanceBusyError,
        WriteModelConfigurationManualRecoveryVerificationBlockedError,
        WriteModelConfigurationManualRecoveryVerificationBusyError,
    ) as exc:
        Log.error(
            f"Manual recovery clearance gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery clearance failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_clearance_report(clearance):
        print(line)
    return 0


def _run_write_model_configuration_manual_recovery_clearance_revocation(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """不可变地撤销最新手工恢复清除凭据。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        撤销成功返回 0，门禁阻断返回 4，回执失败返回 6，
        输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    receipt_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_clearance_revocation_receipt_input"),
            "",
        )
        or ""
    ).strip()
    clearance_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_clearance_revocation_clearance_input"),
            "",
        )
        or ""
    ).strip()
    request_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_clearance_revocation_request"),
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_clearance_revocation_output"),
            "",
        )
        or ""
    ).strip()
    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery clearance revocation requires a config root",
            module=MODULE,
        )
        return 2
    try:
        revocation = revoke_write_model_configuration_manual_recovery_clearance(
            revocation_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
            revocation_output_path=output_path,
            now=datetime.now(UTC),
        )
    except WriteModelConfigurationManualRecoveryClearanceRevocationReceiptError as exc:
        Log.error(
            f"Manual recovery clearance revocation export failed: {exc}",
            module=MODULE,
        )
        return 6
    except (
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        WriteModelConfigurationManualRecoveryClearanceBusyError,
        WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError,
        WriteModelConfigurationManualRecoveryClearanceRevocationBusyError,
    ) as exc:
        Log.error(
            f"Manual recovery clearance revocation blocked: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery clearance revocation failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_clearance_revocation_report(revocation):
        print(line)
    return 0


def _run_write_model_configuration_manual_recovery_restart(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """根据已撤销的清除凭据导出标准恢复证据。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        证据导出成功返回 0，门禁阻断返回 4，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    receipt_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_restart_receipt_input",
            "",
        )
        or ""
    ).strip()
    clearance_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_restart_clearance_input",
            "",
        )
        or ""
    ).strip()
    revocation_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_restart_revocation_input",
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_restart_evidence_output",
            "",
        )
        or ""
    ).strip()
    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery restart requires a config root",
            module=MODULE,
        )
        return 2
    try:
        evidence = restart_write_model_configuration_manual_recovery_after_clearance_revocation(
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            manual_recovery_clearance_revocation_path=(revocation_path),
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
            evidence_output_path=output_path,
            now=datetime.now(UTC),
        )
    except (
        WriteModelConfigurationManualRecoveryRestartBlockedError,
        WriteModelConfigurationManualRecoveryRestartBusyError,
    ) as exc:
        Log.error(
            f"Manual recovery restart blocked: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery restart failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_evidence_report(evidence):
        print(line)
    print(f"  Evidence file : {Path(output_path).expanduser().resolve()}")
    return 0


def _run_write_model_configuration_manual_recovery_gate_check(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """在不启动写作的情况下评估并报告持久正常写作门禁。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        门禁可通行返回 0，阻断返回 4，证据无效返回 6，
        输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery gate check requires a config root",
            module=MODULE,
        )
        return 2
    output_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_gate_output",
            "",
        )
        or ""
    ).strip()
    try:
        gate = assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
        )
    except WriteModelConfigurationManualRecoveryClearanceBusyError as exc:
        Log.error(
            f"Manual recovery gate check is busy: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery gate evidence requires intervention: {exc}",
            module=MODULE,
        )
        return 6
    try:
        persisted_path = (
            persist_write_model_configuration_manual_recovery_gate(
                gate,
                output_path,
                config_root=config_root,
            )
            if output_path
            else None
        )
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery gate export failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_gate_report(gate):
        print(line)
    if persisted_path is not None:
        print(f"  Gate file     : {persisted_path}")
    if gate.get("normal_write_allowed") is True:
        return 0
    return 4


def _run_write_model_configuration_manual_recovery_gate_verification(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """在不授权或启动写作的情况下验证一份已导出恢复门禁。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        门禁当前有效返回 0，状态已变或门禁阻断返回 4，
        证据错误返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery gate verification requires a config root",
            module=MODULE,
        )
        return 2
    input_path = str(
        getattr(
            args,
            "challenger_config_manual_recovery_gate_input",
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_gate_verification_output"),
            "",
        )
        or ""
    ).strip()
    try:
        verification = verify_write_model_configuration_manual_recovery_gate_snapshot(
            gate_snapshot_path=input_path,
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
        )
    except WriteModelConfigurationManualRecoveryClearanceBusyError as exc:
        Log.error(
            f"Manual recovery gate verification is busy: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryGateVerificationChangedError as exc:
        Log.error(
            f"Manual recovery gate input changed: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryGateVerificationEvidenceError as exc:
        Log.error(
            f"Manual recovery gate current evidence requires intervention: {exc}",
            module=MODULE,
        )
        return 6
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery gate verification input is invalid: {exc}",
            module=MODULE,
        )
        return 2
    try:
        persisted_path = (
            persist_write_model_configuration_manual_recovery_gate_verification(
                verification,
                output_path,
                config_root=config_root,
            )
            if output_path
            else None
        )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery gate verification export failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_gate_verification_report(verification):
        print(line)
    if persisted_path is not None:
        print(f"  Verification file : {persisted_path}")
    return 0 if verification.get("status") == "current" else 4


def _run_write_model_configuration_manual_recovery_gate_revalidation(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """在不启动写作的情况下重新验证一份已保存的门禁验证。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        重验状态当前有效返回 0，状态已变或门禁阻断返回 4，
        证据错误返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery gate verification revalidation requires a config root",
            module=MODULE,
        )
        return 2
    input_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_gate_verification_input"),
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_gate_verification_revalidation_output"),
            "",
        )
        or ""
    ).strip()
    try:
        revalidation = revalidate_write_model_configuration_manual_recovery_gate_verification(
            gate_verification_path=input_path,
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
        )
    except WriteModelConfigurationManualRecoveryClearanceBusyError as exc:
        Log.error(
            f"Manual recovery gate verification revalidation is busy: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryGateVerificationChangedError as exc:
        Log.error(
            f"Manual recovery gate verification evidence changed: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryGateVerificationEvidenceError as exc:
        Log.error(
            f"Manual recovery gate verification revalidation requires intervention: {exc}",
            module=MODULE,
        )
        return 6
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery gate verification revalidation input is invalid: {exc}",
            module=MODULE,
        )
        return 2
    try:
        persisted_path = (
            persist_write_model_configuration_manual_recovery_gate_revalidation(
                revalidation,
                output_path,
                config_root=config_root,
            )
            if output_path
            else None
        )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery gate verification revalidation export failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_gate_revalidation_report(revalidation):
        print(line)
    if persisted_path is not None:
        print(f"  Revalidation file : {persisted_path}")
    return 0 if revalidation.get("status") == "current" else 4


def _run_write_model_configuration_manual_recovery_audit_timeline(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """构建并可选导出严格的手工恢复审计时间线。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        时间线构建或导出成功返回 0，状态变更或门禁阻断返回 4，
        严格审计失败返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery history audit requires a config root",
            module=MODULE,
        )
        return 2
    output_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_audit_timeline_output"),
            "",
        )
        or ""
    ).strip()
    try:
        timeline = build_write_model_configuration_manual_recovery_audit_timeline(
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
        )
    except WriteModelConfigurationManualRecoveryClearanceBusyError as exc:
        Log.error(
            f"Manual recovery history audit is busy: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryAuditTimelineChangedError as exc:
        Log.error(
            f"Manual recovery history changed during audit: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery history evidence requires intervention: {exc}",
            module=MODULE,
        )
        return 6
    try:
        persisted_path = (
            persist_write_model_configuration_manual_recovery_audit_timeline(
                timeline,
                output_path,
                workspace_dir=paths_config.workspace_dir,
                config_root=config_root,
            )
            if output_path
            else None
        )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery audit timeline export failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_audit_timeline_report(timeline):
        print(line)
    if persisted_path is not None:
        print(f"  Timeline file : {persisted_path}")
    return 0


def _run_write_model_configuration_manual_recovery_incident_dossier(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """构建并可选导出一份经审计的手工恢复事件档案。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        档案构建或导出成功返回 0，状态变更或门禁阻断返回 4，
        事件缺失或审计失败返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery incident inspection requires a config root",
            module=MODULE,
        )
        return 2
    transaction_id = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_incident_transaction_id"),
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_incident_dossier_output"),
            "",
        )
        or ""
    ).strip()
    try:
        timeline = build_write_model_configuration_manual_recovery_audit_timeline(
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
        )
    except WriteModelConfigurationManualRecoveryClearanceBusyError as exc:
        Log.error(
            f"Manual recovery incident inspection is busy: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryAuditTimelineChangedError as exc:
        Log.error(
            f"Manual recovery history changed during incident inspection: {exc}",
            module=MODULE,
        )
        return 4
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery incident evidence requires intervention: {exc}",
            module=MODULE,
        )
        return 6
    try:
        dossier = build_write_model_configuration_manual_recovery_incident_dossier(
            timeline=timeline,
            transaction_id=transaction_id,
        )
    except WriteModelConfigurationManualRecoveryIncidentNotFoundError as exc:
        Log.error(
            f"Manual recovery incident was not found: {exc}",
            module=MODULE,
        )
        return 4
    except (TypeError, ValueError) as exc:
        Log.error(
            f"Manual recovery incident selection is invalid: {exc}",
            module=MODULE,
        )
        return 2
    try:
        persisted_path = (
            persist_write_model_configuration_manual_recovery_incident_dossier(
                dossier,
                output_path,
                workspace_dir=paths_config.workspace_dir,
                config_root=config_root,
            )
            if output_path
            else None
        )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery incident dossier export failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_incident_dossier_report(dossier):
        print(line)
    if persisted_path is not None:
        print(f"  Dossier file : {persisted_path}")
    return 0


def _run_write_model_configuration_manual_recovery_incident_dossier_revalidation(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """在不启动写作的情况下重新验证一份已保存的事件档案。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。

    Returns:
        重验状态当前有效返回 0，状态已变或门禁阻断返回 4，
        证据或审计失败返回 6，输入或文件错误返回 2。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery incident dossier revalidation requires a config root",
            module=MODULE,
        )
        return 2
    input_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_incident_dossier_input"),
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            ("challenger_config_manual_recovery_incident_dossier_revalidation_output"),
            "",
        )
        or ""
    ).strip()
    try:
        revalidation = revalidate_write_model_configuration_manual_recovery_incident_dossier(
            incident_dossier_path=input_path,
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
        )
    except WriteModelConfigurationManualRecoveryClearanceBusyError as exc:
        Log.error(
            f"Manual recovery incident dossier revalidation is busy: {exc}",
            module=MODULE,
        )
        return 4
    except (
        WriteModelConfigurationManualRecoveryAuditTimelineChangedError,
        WriteModelConfigurationManualRecoveryIncidentDossierChangedError,
    ) as exc:
        Log.error(
            f"Manual recovery incident dossier evidence changed: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryIncidentDossierEvidenceError as exc:
        Log.error(
            f"Manual recovery incident dossier revalidation requires intervention: {exc}",
            module=MODULE,
        )
        return 6
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery incident dossier revalidation input is invalid: {exc}",
            module=MODULE,
        )
        return 2
    try:
        persisted_path = (
            persist_write_model_configuration_manual_recovery_incident_dossier_revalidation(
                revalidation,
                output_path,
                workspace_dir=paths_config.workspace_dir,
                config_root=config_root,
            )
            if output_path
            else None
        )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery incident dossier revalidation export failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in format_write_model_configuration_manual_recovery_incident_dossier_revalidation_report(revalidation):
        print(line)
    if persisted_path is not None:
        print(f"  Revalidation file : {persisted_path}")
    return 0 if revalidation.get("status") == "current" else 4


def _check_write_model_configuration_manual_recovery_gate(
    *,
    paths_config: WorkspaceConfig,
) -> int:
    """在正常体检、批准消费或模型工作前执行 fail-closed 恢复门禁。

    Args:
        paths_config: 写作工作区与配置路径。

    Returns:
        允许继续正常写作返回 0；门禁阻断或门禁评估失败返回 4。

    Raises:
        Exception: 日志、报告格式化或标准输出等未纳入退出码映射的异常会原样传播。
    """

    config_root = getattr(paths_config, "config_root", None)
    if config_root is None:
        transaction_root = write_model_configuration_manual_recovery_transaction_root(
            workspace_dir=paths_config.workspace_dir
        )
        if not transaction_root.exists():
            return 0
        Log.error(
            "Manual recovery gate requires a config root",
            module=MODULE,
        )
        return 4
    try:
        gate = assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=paths_config.workspace_dir,
            config_root=config_root,
            expected_ticker=str(paths_config.ticker),
        )
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Manual recovery normal-write gate failed closed: {exc}",
            module=MODULE,
        )
        return 4
    if gate.get("normal_write_allowed") is True:
        return 0
    for line in format_write_model_configuration_manual_recovery_gate_report(gate):
        print(line)
    Log.error(
        "Normal write is blocked until the latest manual recovery incident is safely resolved and cleared",
        module=MODULE,
    )
    return 4
