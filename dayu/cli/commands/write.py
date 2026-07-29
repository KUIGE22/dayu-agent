"""`dayu-cli write` 命令实现。"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from dayu.cli.dependency_setup import (
    RunningConfig,
    WorkspaceConfig,
    WriteCliConfig,
    _build_execution_options,
    _build_write_service,
    _prepare_cli_host_dependencies,
    _resolve_write_output_dir,
    run_write_pipeline,
    setup_loglevel,
    setup_model_name,
    setup_paths,
    setup_write_config,
)
from dayu.contracts.cancellation import CancelledError
from dayu.log import Log
from dayu.services.contracts import WritePreflightResult, WriteRequest, WriteRunConfig
from dayu.services.write_model_challenger_preflight_approval import (
    format_write_model_challenger_preflight_verification_report,
    load_write_model_challenger_preflight_approval,
    verify_write_model_challenger_preflight_approval,
)
from dayu.services.write_model_challenger_proposal import (
    load_write_model_challenger_proposal,
)
from dayu.services.write_model_health import build_write_model_health_trend
from dayu.services.write_model_challenger_run_approval import (
    WriteModelChallengerRunApprovalBlockedError,
    WriteModelChallengerRunApprovalConsumedError,
    build_write_model_challenger_run_approval,
    build_write_model_challenger_run_plan,
    consume_write_model_challenger_run_approval,
    format_write_model_challenger_run_approval_report,
    format_write_model_challenger_run_verification_report,
    load_write_model_challenger_run_approval,
    load_write_model_challenger_run_approval_request,
    persist_write_model_challenger_run_approval,
    persist_write_model_challenger_run_plan,
    verify_write_model_challenger_run_approval,
)
from dayu.services.write_model_configuration_application import (
    WriteModelConfigurationApplicationBlockedError,
    WriteModelConfigurationApplicationBusyError,
    WriteModelConfigurationApplicationReceiptError,
    apply_write_model_configuration_preapplication_plan,
    format_write_model_configuration_application_receipt_report,
    format_write_model_configuration_application_verification_report,
    load_write_model_configuration_application_receipt,
    verify_write_model_configuration_application_receipt,
)
from dayu.services.write_model_configuration_preapplication import (
    WriteModelConfigurationPreapplicationBlockedError,
    build_write_model_configuration_preapplication_plan,
    build_write_scene_model_routing_snapshot,
    format_write_model_configuration_preapplication_plan_report,
    format_write_model_configuration_preapplication_verification_report,
    format_write_scene_model_routing_snapshot_report,
    load_write_model_configuration_preapplication_plan,
    persist_write_model_configuration_preapplication_plan,
    persist_write_scene_model_routing_snapshot,
    verify_write_model_configuration_preapplication_plan,
)
from dayu.services.write_model_configuration_rollback import (
    WriteModelConfigurationRollbackBlockedError,
    build_write_model_configuration_operator_rollback_approval,
    build_write_model_configuration_operator_rollback_plan,
    format_write_model_configuration_operator_rollback_approval_report,
    format_write_model_configuration_operator_rollback_approval_verification_report,
    format_write_model_configuration_operator_rollback_plan_report,
    format_write_model_configuration_operator_rollback_plan_verification_report,
    load_write_model_configuration_operator_rollback_approval,
    load_write_model_configuration_operator_rollback_approval_request,
    load_write_model_configuration_operator_rollback_plan,
    persist_write_model_configuration_operator_rollback_approval,
    persist_write_model_configuration_operator_rollback_plan,
    verify_write_model_configuration_operator_rollback_approval,
    verify_write_model_configuration_operator_rollback_plan,
)
from dayu.services.write_model_configuration_rollback_application import (
    WriteModelConfigurationRollbackApplicationBlockedError,
    WriteModelConfigurationRollbackApplicationBusyError,
    WriteModelConfigurationRollbackReceiptError,
    apply_write_model_configuration_operator_rollback,
    build_write_model_configuration_manual_recovery_evidence,
    build_write_model_configuration_operator_rollback_retry_plan,
    format_write_model_configuration_manual_recovery_evidence_report,
    format_write_model_configuration_operator_rollback_receipt_report,
    format_write_model_configuration_operator_rollback_verification_report,
    load_write_model_configuration_operator_rollback_receipt,
    persist_write_model_configuration_manual_recovery_evidence,
    verify_write_model_configuration_operator_rollback_receipt,
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
from dayu.services.write_model_configuration_manual_recovery_verification import (
    WriteModelConfigurationManualRecoveryVerificationBlockedError,
    WriteModelConfigurationManualRecoveryVerificationBusyError,
    format_write_model_configuration_manual_recovery_verification_report,
    verify_write_model_configuration_manual_recovery_receipt,
)
from dayu.services.write_run_comparison import (
    compare_write_run_paths,
    persist_write_run_comparison,
)
from dayu.services.write_service import WRITE_CANCELLED_EXIT_CODE, WriteService
from dayu.startup.config_file_resolver import ConfigFileResolver
from dayu.startup.config_loader import ConfigLoader

MODULE = "APP.WRITE"
_CHALLENGER_COMPARISON_FILE = "challenger_comparison.json"


def _resolve_write_model_override_name(args: argparse.Namespace) -> str:
    """解析主写作模型覆盖名。

    Args:
        args: 解析后的命令行参数。

    Returns:
        归一化后的主写作模型覆盖名；未显式配置时返回空字符串。

    Raises:
        无。
    """

    return setup_model_name(args).model_name


def _resolve_write_company_name(
    *,
    ticker: str,
    company_name_resolver: Callable[[str], str],
) -> str:
    """解析写作配置中的公司名称。

    Args:
        ticker: 公司股票代码。
        company_name_resolver: 公司名称解析函数。

    Returns:
        解析后的公司名称；缺失或解析失败时返回空字符串。

    Raises:
        无。
    """

    try:
        return str(company_name_resolver(ticker) or "").strip()
    except Exception:
        return ""


def _build_write_run_config(
    *,
    ticker: str,
    company_name: str,
    write_cli_config: WriteCliConfig,
    write_model_override_name: str,
) -> WriteRunConfig:
    """Build the service contract for one write-pipeline stage."""

    return WriteRunConfig(
        ticker=ticker,
        company=company_name,
        template_path=str(write_cli_config.template_path),
        output_dir=str(write_cli_config.output_dir),
        write_max_retries=write_cli_config.write_max_retries,
        web_provider=write_cli_config.web_provider,
        resume=write_cli_config.resume,
        write_model_override_name=write_model_override_name,
        audit_model_override_name=write_cli_config.audit_model_override_name,
        write_fallback_model_name=getattr(
            write_cli_config,
            "write_fallback_model_name",
            "",
        ),
        audit_fallback_model_name=getattr(
            write_cli_config,
            "audit_fallback_model_name",
            "",
        ),
        chapter_filter=write_cli_config.chapter_filter,
        fast=write_cli_config.fast,
        force=write_cli_config.force,
        infer=write_cli_config.infer,
        research_template_requested_name=write_cli_config.research_template_requested_name,
        research_template_resolved_name=write_cli_config.research_template_resolved_name,
        research_template_selection_mode=write_cli_config.research_template_selection_mode,
        write_max_model_requests=getattr(write_cli_config, "write_max_model_requests", None),
        write_max_total_tokens=getattr(write_cli_config, "write_max_total_tokens", None),
        write_max_estimated_cost=getattr(write_cli_config, "write_max_estimated_cost", None),
        write_budget_currency=getattr(write_cli_config, "write_budget_currency", ""),
    )


def _run_write_stage(*, write_config: WriteRunConfig, write_service: WriteService) -> int:
    """Run one infer or writing stage with stable CLI logging and exit codes."""

    infer_mode = write_config.infer
    Log.info("公司级 Facet 归因启动..." if infer_mode else "写作流水线启动...", module=MODULE)
    start_time = perf_counter()
    try:
        exit_code = run_write_pipeline(write_config=write_config, write_service=write_service)
        elapsed = perf_counter() - start_time
        if exit_code == 0:
            Log.info(
                ("公司级 Facet 归因完成" if infer_mode else "写作流水线完成")
                + f": exit_code={exit_code}, elapsed={elapsed:.2f}s",
                module=MODULE,
            )
        elif exit_code == WRITE_CANCELLED_EXIT_CODE:
            Log.warn(
                ("公司级 Facet 归因已取消" if infer_mode else "写作模式已取消")
                + f": exit_code={exit_code}, elapsed={elapsed:.2f}s",
                module=MODULE,
            )
        else:
            Log.warn(
                ("公司级 Facet 归因结束但返回非零" if infer_mode else "写作流水线结束但返回非零")
                + f": exit_code={exit_code}, elapsed={elapsed:.2f}s",
                module=MODULE,
            )
        return exit_code
    except CancelledError as exc:
        elapsed = perf_counter() - start_time
        Log.warn(
            ("公司级 Facet 归因已取消" if infer_mode else "写作模式已取消") + f": elapsed={elapsed:.2f}s, reason={exc}",
            module=MODULE,
        )
        return WRITE_CANCELLED_EXIT_CODE
    except Exception as exc:
        elapsed = perf_counter() - start_time
        Log.error(
            ("公司级 Facet 归因执行失败" if infer_mode else "写作模式执行失败")
            + f": elapsed={elapsed:.2f}s, error={exc}",
            module=MODULE,
        )
        return 2


def _run_write_preflight(
    *,
    write_config: WriteRunConfig,
    write_service: WriteService,
    run_label: str = "",
    config_root: str | Path | None = None,
    routing_snapshot_output: str | Path | None = None,
    configuration_change_approval_input: str | Path | None = None,
    preapplication_plan_output: str | Path | None = None,
    preapplication_plan_input: str | Path | None = None,
    application_receipt_input: str | Path | None = None,
    rollback_plan_output: str | Path | None = None,
    rollback_plan_input: str | Path | None = None,
    rollback_approval_request: str | Path | None = None,
    rollback_approval_output: str | Path | None = None,
    rollback_approval_input: str | Path | None = None,
    rollback_receipt_input: str | Path | None = None,
) -> int:
    """Run model-free preflight and optional immutable config gates."""

    try:
        result = write_service.preflight(WriteRequest(write_config=write_config))
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        Log.error(f"写作运行前体检失败: {exc}", module=MODULE)
        return 2
    _log_write_preflight_result(result, run_label=run_label)
    if not result.ready:
        return 2
    artifact_requested = any(
        value is not None
        for value in (
            routing_snapshot_output,
            preapplication_plan_output,
            preapplication_plan_input,
            application_receipt_input,
            rollback_plan_output,
            rollback_plan_input,
            rollback_approval_request,
            rollback_approval_output,
            rollback_approval_input,
            rollback_receipt_input,
        )
    )
    if not artifact_requested:
        return 0
    try:
        current_snapshot = build_write_scene_model_routing_snapshot(
            config_root=config_root,
            write_config=write_config,
            preflight_result=result,
        )
        snapshot_path: Path | None = None
        if routing_snapshot_output is not None:
            snapshot_path = persist_write_scene_model_routing_snapshot(
                current_snapshot,
                routing_snapshot_output,
            )
            print(f"  Write routing snapshot: {snapshot_path}")
            for line in format_write_scene_model_routing_snapshot_report(current_snapshot):
                print(line)
        if preapplication_plan_output is not None:
            if snapshot_path is None or configuration_change_approval_input is None:
                raise ValueError("pre-application plan export requires a persisted snapshot and approval input")
            plan = build_write_model_configuration_preapplication_plan(
                approval_path=configuration_change_approval_input,
                routing_snapshot_path=snapshot_path,
                now=datetime.now(UTC),
            )
            plan_path = persist_write_model_configuration_preapplication_plan(
                plan,
                preapplication_plan_output,
            )
            print(f"  Configuration pre-application plan: {plan_path}")
            for line in format_write_model_configuration_preapplication_plan_report(plan):
                print(line)
        if preapplication_plan_input is not None:
            if configuration_change_approval_input is None:
                raise ValueError("pre-application plan verification requires approval input")
            plan_path, plan = load_write_model_configuration_preapplication_plan(preapplication_plan_input)
            verification = verify_write_model_configuration_preapplication_plan(
                plan,
                current_routing_snapshot=current_snapshot,
                expected_approval_path=(configuration_change_approval_input),
                now=datetime.now(UTC),
            )
            print(f"  Configuration pre-application plan: {plan_path}")
            for line in format_write_model_configuration_preapplication_verification_report(verification):
                print(line)
            if verification.get("status") != "current":
                return 4
        if application_receipt_input is not None:
            receipt_path, receipt = load_write_model_configuration_application_receipt(application_receipt_input)
            verification = verify_write_model_configuration_application_receipt(
                receipt,
                current_routing_snapshot=current_snapshot,
            )
            print(f"  Configuration application receipt: {receipt_path}")
            for line in format_write_model_configuration_application_verification_report(verification):
                print(line)
            if verification.get("status") != "current":
                return 4
            if rollback_plan_output is not None:
                rollback_plan = build_write_model_configuration_operator_rollback_plan(
                    application_receipt_path=receipt_path,
                    current_routing_snapshot=current_snapshot,
                    now=datetime.now(UTC),
                )
                persisted_rollback_plan_path = persist_write_model_configuration_operator_rollback_plan(
                    rollback_plan,
                    rollback_plan_output,
                )
                print(f"  Configuration operator rollback plan: {persisted_rollback_plan_path}")
                for line in format_write_model_configuration_operator_rollback_plan_report(rollback_plan):
                    print(line)
            if rollback_plan_input is not None:
                rollback_plan_path, rollback_plan = load_write_model_configuration_operator_rollback_plan(
                    rollback_plan_input
                )
                rollback_plan_verification = verify_write_model_configuration_operator_rollback_plan(
                    rollback_plan,
                    expected_application_receipt_path=receipt_path,
                    current_routing_snapshot=current_snapshot,
                )
                print(f"  Configuration operator rollback plan: {rollback_plan_path}")
                for line in format_write_model_configuration_operator_rollback_plan_verification_report(
                    rollback_plan_verification
                ):
                    print(line)
                if rollback_plan_verification.get("status") != "current":
                    return 4
                if rollback_approval_request is not None:
                    _request_path, approval_request = load_write_model_configuration_operator_rollback_approval_request(
                        rollback_approval_request
                    )
                    rollback_approval = build_write_model_configuration_operator_rollback_approval(
                        approval_request=approval_request,
                        rollback_plan_path=rollback_plan_path,
                        rollback_plan=rollback_plan,
                        current_routing_snapshot=current_snapshot,
                        now=datetime.now(UTC),
                    )
                    assert rollback_approval_output is not None
                    persisted_approval_path = persist_write_model_configuration_operator_rollback_approval(
                        rollback_approval,
                        rollback_approval_output,
                    )
                    print(f"  Configuration rollback approval: {persisted_approval_path}")
                    for line in format_write_model_configuration_operator_rollback_approval_report(rollback_approval):
                        print(line)
                if rollback_approval_input is not None:
                    rollback_approval_path, rollback_approval = (
                        load_write_model_configuration_operator_rollback_approval(rollback_approval_input)
                    )
                    approval_verification = verify_write_model_configuration_operator_rollback_approval(
                        rollback_approval,
                        current_routing_snapshot=current_snapshot,
                        now=datetime.now(UTC),
                    )
                    print(f"  Configuration rollback approval: {rollback_approval_path}")
                    for line in format_write_model_configuration_operator_rollback_approval_verification_report(
                        approval_verification
                    ):
                        print(line)
                    if approval_verification.get("status") != "approved":
                        return 4
        if rollback_receipt_input is not None:
            rollback_receipt_path, rollback_receipt = load_write_model_configuration_operator_rollback_receipt(
                rollback_receipt_input
            )
            rollback_receipt_verification = verify_write_model_configuration_operator_rollback_receipt(
                rollback_receipt,
                current_routing_snapshot=current_snapshot,
            )
            print(f"  Configuration operator rollback receipt: {rollback_receipt_path}")
            for line in format_write_model_configuration_operator_rollback_verification_report(
                rollback_receipt_verification
            ):
                print(line)
            if rollback_receipt_verification.get("status") != "current":
                return 4
            if rollback_plan_output is not None:
                retry_plan = build_write_model_configuration_operator_rollback_retry_plan(
                    rollback_receipt_path=rollback_receipt_path,
                    current_routing_snapshot=current_snapshot,
                    now=datetime.now(UTC),
                )
                persisted_retry_plan_path = persist_write_model_configuration_operator_rollback_plan(
                    retry_plan,
                    rollback_plan_output,
                )
                print(f"  Configuration operator rollback retry plan: {persisted_retry_plan_path}")
                for line in format_write_model_configuration_operator_rollback_plan_report(retry_plan):
                    print(line)
    except WriteModelConfigurationRollbackBlockedError as exc:
        Log.error(
            f"Configuration operator rollback gate blocked: {exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationPreapplicationBlockedError as exc:
        Log.error(
            f"Configuration pre-application gate blocked: {exc}",
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
            f"Configuration pre-application gate failed: {exc}",
            module=MODULE,
        )
        return 2
    return 0


def _build_fresh_application_routing_snapshot(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_options: Any,
    run_label: str = "configuration-application",
) -> dict[str, Any]:
    """Resolve one uncached write-routing snapshot without model calls."""

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
        scene_execution_acceptance_preparer=(scene_execution_acceptance_preparer),
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
        raise WriteModelConfigurationApplicationBlockedError("fresh write preflight failed")
    return build_write_scene_model_routing_snapshot(
        config_root=paths_config.config_root,
        write_config=write_config,
        preflight_result=result,
    )


def _run_write_model_configuration_application(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_options: Any,
) -> int:
    """Run only the single-use model-routing configuration transaction."""

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

    def _snapshot_builder() -> Mapping[str, Any]:
        return _build_fresh_application_routing_snapshot(
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
            snapshot_builder=_snapshot_builder,
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


def _run_write_model_configuration_rollback(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_options: Any,
) -> int:
    """Run only the single-use exact-byte operator rollback."""

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

    def _snapshot_builder() -> Mapping[str, Any]:
        return _build_fresh_application_routing_snapshot(
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
            snapshot_builder=_snapshot_builder,
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


def _run_write_model_configuration_manual_recovery_evidence(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """Export only immutable evidence for a recovery-failed rollback."""

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
    """Build only the exact plan for one explicit human selection."""

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
    """Issue only one independent short-lived recovery approval."""

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
    execution_options: Any,
) -> int:
    """Consume one approval and recover only its selected exact state."""

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

    def _snapshot_builder() -> Mapping[str, Any]:
        return _build_fresh_application_routing_snapshot(
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
            snapshot_builder=_snapshot_builder,
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
    execution_options: Any,
) -> int:
    """Independently verify a manual recovery receipt and current state."""

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

    def _snapshot_builder() -> Mapping[str, Any]:
        return _build_fresh_application_routing_snapshot(
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
            snapshot_builder=_snapshot_builder,
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
    execution_options: Any,
) -> int:
    """Verify and durably clear the latest recovered incident."""

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

    def _snapshot_builder() -> Mapping[str, Any]:
        return _build_fresh_application_routing_snapshot(
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
            snapshot_builder=_snapshot_builder,
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
    """Immutably revoke the latest recovery clearance."""

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
    """Export standard recovery evidence from a revoked clearance."""

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
    """Report the durable normal-write gate without starting a write."""

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
    """Verify one exported gate without authorizing or starting a write."""

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
            (
                "challenger_config_manual_recovery_gate_"
                "verification_output"
            ),
            "",
        )
        or ""
    ).strip()
    try:
        verification = (
            verify_write_model_configuration_manual_recovery_gate_snapshot(
                gate_snapshot_path=input_path,
                workspace_dir=paths_config.workspace_dir,
                config_root=config_root,
                expected_ticker=str(paths_config.ticker),
            )
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
    for line in (
        format_write_model_configuration_manual_recovery_gate_verification_report(
            verification
        )
    ):
        print(line)
    if persisted_path is not None:
        print(f"  Verification file : {persisted_path}")
    return 0 if verification.get("status") == "current" else 4


def _run_write_model_configuration_manual_recovery_gate_revalidation(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """Revalidate one saved gate verification without starting a write."""

    config_root = paths_config.config_root
    if config_root is None:
        Log.error(
            "Manual recovery gate verification revalidation requires "
            "a config root",
            module=MODULE,
        )
        return 2
    input_path = str(
        getattr(
            args,
            (
                "challenger_config_manual_recovery_gate_"
                "verification_input"
            ),
            "",
        )
        or ""
    ).strip()
    output_path = str(
        getattr(
            args,
            (
                "challenger_config_manual_recovery_gate_verification_"
                "revalidation_output"
            ),
            "",
        )
        or ""
    ).strip()
    try:
        revalidation = (
            revalidate_write_model_configuration_manual_recovery_gate_verification(
                gate_verification_path=input_path,
                workspace_dir=paths_config.workspace_dir,
                config_root=config_root,
                expected_ticker=str(paths_config.ticker),
            )
        )
    except WriteModelConfigurationManualRecoveryClearanceBusyError as exc:
        Log.error(
            "Manual recovery gate verification revalidation is busy: "
            f"{exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryGateVerificationChangedError as exc:
        Log.error(
            "Manual recovery gate verification evidence changed: "
            f"{exc}",
            module=MODULE,
        )
        return 4
    except WriteModelConfigurationManualRecoveryGateVerificationEvidenceError as exc:
        Log.error(
            "Manual recovery gate verification revalidation requires "
            f"intervention: {exc}",
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
            "Manual recovery gate verification revalidation input is "
            f"invalid: {exc}",
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
            "Manual recovery gate verification revalidation export "
            f"failed: {exc}",
            module=MODULE,
        )
        return 2
    for line in (
        format_write_model_configuration_manual_recovery_gate_revalidation_report(
            revalidation
        )
    ):
        print(line)
    if persisted_path is not None:
        print(f"  Revalidation file : {persisted_path}")
    return 0 if revalidation.get("status") == "current" else 4


def _run_write_model_configuration_manual_recovery_audit_timeline(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
) -> int:
    """Build and optionally export the strict recovery history."""

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
            (
                "challenger_config_manual_recovery_audit_"
                "timeline_output"
            ),
            "",
        )
        or ""
    ).strip()
    try:
        timeline = (
            build_write_model_configuration_manual_recovery_audit_timeline(
                workspace_dir=paths_config.workspace_dir,
                config_root=config_root,
                expected_ticker=str(paths_config.ticker),
            )
        )
    except WriteModelConfigurationManualRecoveryClearanceBusyError as exc:
        Log.error(
            f"Manual recovery history audit is busy: {exc}",
            module=MODULE,
        )
        return 4
    except (
        WriteModelConfigurationManualRecoveryAuditTimelineChangedError
    ) as exc:
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
    for line in (
        format_write_model_configuration_manual_recovery_audit_timeline_report(
            timeline
        )
    ):
        print(line)
    if persisted_path is not None:
        print(f"  Timeline file : {persisted_path}")
    return 0


def _check_write_model_configuration_manual_recovery_gate(
    *,
    paths_config: WorkspaceConfig,
) -> int:
    """Fail closed before normal preflight, approval use, or model work."""

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


def _log_write_preflight_result(result: WritePreflightResult, *, run_label: str = "") -> None:
    """输出写作体检结果，日志中只显示环境变量名称。"""

    label_prefix = f"[{run_label}] " if run_label else ""
    Log.info(f"{label_prefix}写作运行前体检:", module=MODULE)
    for scene in result.scenes:
        Log.info(
            f"- scene={scene.scene_name}, role={scene.model_role.value}, "
            f"model={scene.model_name}, temperature={scene.temperature}",
            module=MODULE,
        )
    for scene in result.fallback_scenes:
        Log.info(
            f"- scene={scene.scene_name}, role={scene.model_role.value}, route=fallback, "
            f"model={scene.model_name}, temperature={scene.temperature}",
            module=MODULE,
        )
    environment_names = ", ".join(result.required_environment_variables) or "无"
    Log.info(f"- required_environment_variables={environment_names}", module=MODULE)
    Log.info(f"- signature_scene_count={len(result.signature_scenes)}", module=MODULE)
    Log.info(
        f"- signature_fallback_scene_count={len(result.signature_fallback_scenes)}",
        module=MODULE,
    )
    if result.ready:
        Log.info(f"{label_prefix}写作运行前体检通过", module=MODULE)
        return
    for issue in result.issues:
        Log.error(f"- [{issue.code.value}] {issue.message}", module=MODULE)


def _challenger_requested(args: argparse.Namespace) -> bool:
    """Return whether either Challenger model override was explicitly set."""

    return bool(
        str(getattr(args, "challenger_model_name", "") or "").strip()
        or str(getattr(args, "challenger_audit_model_name", "") or "").strip()
    )


def _challenger_preflight_cli_args(
    args: argparse.Namespace,
) -> list[str]:
    """Build the canonical approval-bound Challenger preflight argv."""

    result = ["--preflight-only"]
    for flag, attribute in (
        ("--challenger-model-name", "challenger_model_name"),
        (
            "--challenger-audit-model-name",
            "challenger_audit_model_name",
        ),
    ):
        model_name = str(getattr(args, attribute, "") or "").strip()
        if model_name:
            result.extend((flag, model_name))
    return result


def _verify_challenger_preflight_approval_before_host(
    *,
    args: argparse.Namespace,
    write_model_override_name: str,
) -> int:
    """Consume a common-preflight approval before Host initialization."""

    try:
        history_root = Path(str(getattr(args, "routing_history_root"))).expanduser().resolve()
        proposal_path, proposal_receipt = load_write_model_challenger_proposal(
            str(getattr(args, "routing_proposal_input"))
        )
        approval_path, approval = load_write_model_challenger_preflight_approval(
            str(
                getattr(
                    args,
                    "routing_preflight_approval_input",
                )
            )
        )
        health_trend = build_write_model_health_trend(history_root)
        raw_current_proposal = health_trend.get("challenger_proposal")
        if not isinstance(raw_current_proposal, Mapping):
            raise ValueError("current routing history did not produce a Challenger proposal")
        actual_current_models: dict[str, str] = {}
        if write_model_override_name:
            actual_current_models["primary"] = write_model_override_name
        audit_model_name = str(getattr(args, "audit_model_name", "") or "").strip()
        if audit_model_name:
            actual_current_models["audit"] = audit_model_name
        verification = verify_write_model_challenger_preflight_approval(
            approval=approval,
            proposal_receipt=proposal_receipt,
            current_proposal=raw_current_proposal,
            actual_cli_args=_challenger_preflight_cli_args(args),
            actual_current_models=actual_current_models,
            now=datetime.now(UTC),
        )
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Challenger 共同 preflight 审批验证失败: {exc}",
            module=MODULE,
        )
        return 2

    Log.info(f"Challenger 提案凭据: {proposal_path}", module=MODULE)
    Log.info(f"Challenger preflight 审批凭据: {approval_path}", module=MODULE)
    for line in format_write_model_challenger_preflight_verification_report(verification):
        Log.info(line, module=MODULE)
    if verification.get("preflight_authorized") is not True:
        return 4
    return 0


def _build_challenger_run_plan_from_args(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    write_model_override_name: str,
) -> dict[str, Any]:
    """Build an exact full-run plan without initializing Host."""

    ticker = paths_config.ticker
    if not ticker:
        raise ValueError("Challenger run plan requires a ticker")
    raw_template = str(getattr(args, "template", "") or "").strip()
    template_path = Path(raw_template).expanduser()
    if not template_path.is_absolute():
        template_path = (Path.cwd() / template_path).resolve()
    champion_output = _resolve_write_output_dir(
        workspace_dir=paths_config.workspace_dir,
        ticker=paths_config.ticker,
        raw_output=getattr(args, "output", None),
    )
    challenger_output = Path(str(getattr(args, "challenger_output"))).expanduser().resolve()
    current_models: dict[str, str] = {}
    if write_model_override_name:
        current_models["primary"] = write_model_override_name
    audit_model_name = str(getattr(args, "audit_model_name", "") or "").strip()
    if audit_model_name:
        current_models["audit"] = audit_model_name
    fallback_models: dict[str, str] = {}
    write_fallback = str(getattr(args, "fallback_model_name", "") or "").strip()
    if write_fallback:
        fallback_models["primary"] = write_fallback
    audit_fallback = str(getattr(args, "audit_fallback_model_name", "") or "").strip()
    if audit_fallback:
        fallback_models["audit"] = audit_fallback

    return build_write_model_challenger_run_plan(
        ticker=ticker,
        template_path=template_path,
        champion_output_dir=champion_output,
        challenger_output_dir=challenger_output,
        current_models=current_models,
        challenger_cli_args=(_challenger_preflight_cli_args(args)[1:]),
        fallback_models=fallback_models,
        write_max_retries=int(getattr(args, "write_max_retries", 2)),
        web_provider=str(getattr(args, "web_provider", "") or "").strip(),
        temperature=getattr(args, "temperature", None),
        maximum_model_requests_per_run=int(getattr(args, "write_max_model_requests")),
        maximum_total_tokens_per_run=int(getattr(args, "write_max_total_tokens")),
        maximum_estimated_cost_per_run=float(getattr(args, "write_max_estimated_cost")),
        budget_currency=str(getattr(args, "write_budget_currency")),
    )


def _assert_challenger_run_output_boundaries(
    *,
    plan: Mapping[str, Any],
    workspace_dir: Path,
) -> None:
    """Require both approved outputs to be new workspace descendants."""

    outputs = plan.get("outputs")
    if not isinstance(outputs, Mapping):
        raise ValueError("Challenger run plan outputs are invalid")
    resolved_workspace = workspace_dir.expanduser().resolve()
    for label in ("champion", "challenger"):
        output = Path(str(outputs.get(label) or "")).resolve()
        if not output.is_relative_to(resolved_workspace):
            raise ValueError(f"{label} output must be inside the workspace")
        if output.exists():
            raise FileExistsError(f"{label} output must not already exist: {output}")


def _load_current_challenger_proposal(
    *,
    history_root: str | Path,
    proposal_input: str | Path,
) -> tuple[Path, dict[str, Any], Mapping[str, Any]]:
    """Load the exported proposal and rebuild it from current history."""

    proposal_path, proposal_receipt = load_write_model_challenger_proposal(proposal_input)
    health_trend = build_write_model_health_trend(history_root)
    current_proposal = health_trend.get("challenger_proposal")
    if not isinstance(current_proposal, Mapping):
        raise ValueError("current routing history did not produce a Challenger proposal")
    return proposal_path, proposal_receipt, current_proposal


def _persist_challenger_run_authorization_after_preflight(
    *,
    args: argparse.Namespace,
    execution_plan: Mapping[str, Any],
) -> int:
    """Export a plan and optionally issue one run approval after preflight."""

    raw_plan_output = str(
        getattr(
            args,
            "routing_challenger_run_plan_output",
            "",
        )
        or ""
    ).strip()
    raw_request = str(
        getattr(
            args,
            "routing_challenger_run_approval_request",
            "",
        )
        or ""
    ).strip()
    raw_approval_output = str(
        getattr(
            args,
            "routing_challenger_run_approval_output",
            "",
        )
        or ""
    ).strip()
    try:
        if raw_plan_output:
            plan_path = persist_write_model_challenger_run_plan(
                execution_plan,
                raw_plan_output,
            )
            Log.info(
                f"Challenger 双跑计划: {plan_path}",
                module=MODULE,
            )
        if not raw_request:
            return 0

        proposal_path, proposal_receipt, current_proposal = _load_current_challenger_proposal(
            history_root=str(getattr(args, "routing_history_root")),
            proposal_input=str(getattr(args, "routing_proposal_input")),
        )
        preflight_path, preflight_approval = load_write_model_challenger_preflight_approval(
            str(
                getattr(
                    args,
                    "routing_preflight_approval_input",
                )
            )
        )
        request_path, request = load_write_model_challenger_run_approval_request(raw_request)
        approval = build_write_model_challenger_run_approval(
            request=request,
            preflight_approval=preflight_approval,
            proposal_receipt=proposal_receipt,
            current_proposal=current_proposal,
            actual_execution_plan=execution_plan,
            preflight_passed=True,
            now=datetime.now(UTC),
        )
        approval_path = persist_write_model_challenger_run_approval(
            approval,
            raw_approval_output,
        )
    except WriteModelChallengerRunApprovalBlockedError as exc:
        Log.error(
            f"Challenger 双跑授权被阻止: {exc}",
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
            f"Challenger 双跑授权签发失败: {exc}",
            module=MODULE,
        )
        return 2

    Log.info(f"Challenger 提案凭据: {proposal_path}", module=MODULE)
    Log.info(
        f"Challenger preflight 审批凭据: {preflight_path}",
        module=MODULE,
    )
    Log.info(
        f"Challenger 双跑授权请求: {request_path}",
        module=MODULE,
    )
    Log.info(
        f"Challenger 双跑授权凭据: {approval_path}",
        module=MODULE,
    )
    for line in format_write_model_challenger_run_approval_report(approval):
        Log.info(line, module=MODULE)
    return 0


def _verify_and_consume_challenger_run_approval_before_host(
    *,
    args: argparse.Namespace,
    paths_config: WorkspaceConfig,
    execution_plan: Mapping[str, Any],
) -> int:
    """Verify and atomically consume one full-run approval before Host."""

    try:
        _assert_challenger_run_output_boundaries(
            plan=execution_plan,
            workspace_dir=paths_config.workspace_dir,
        )
        proposal_path, proposal_receipt, current_proposal = _load_current_challenger_proposal(
            history_root=str(getattr(args, "routing_history_root")),
            proposal_input=str(getattr(args, "routing_proposal_input")),
        )
        approval_path, approval = load_write_model_challenger_run_approval(
            str(
                getattr(
                    args,
                    "routing_challenger_run_approval_input",
                )
            )
        )
        checked_at = datetime.now(UTC)
        verification = verify_write_model_challenger_run_approval(
            approval=approval,
            proposal_receipt=proposal_receipt,
            current_proposal=current_proposal,
            actual_execution_plan=execution_plan,
            now=checked_at,
        )
        if verification.get("run_authorized") is not True:
            Log.info(
                f"Challenger 提案凭据: {proposal_path}",
                module=MODULE,
            )
            Log.info(
                f"Challenger 双跑授权凭据: {approval_path}",
                module=MODULE,
            )
            for line in format_write_model_challenger_run_verification_report(verification):
                Log.info(line, module=MODULE)
            return 4
        consumption_path = consume_write_model_challenger_run_approval(
            approval=approval,
            workspace_dir=paths_config.workspace_dir,
            now=checked_at,
        )
    except WriteModelChallengerRunApprovalConsumedError as exc:
        Log.error(str(exc), module=MODULE)
        return 4
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        Log.error(
            f"Challenger 双跑授权验证失败: {exc}",
            module=MODULE,
        )
        return 2

    Log.info(f"Challenger 提案凭据: {proposal_path}", module=MODULE)
    Log.info(
        f"Challenger 双跑授权凭据: {approval_path}",
        module=MODULE,
    )
    for line in format_write_model_challenger_run_verification_report(verification):
        Log.info(line, module=MODULE)
    Log.info(
        f"Challenger 双跑授权已消费: {consumption_path}",
        module=MODULE,
    )
    return 0


def _build_challenger_write_config(
    *,
    args: argparse.Namespace,
    champion_config: WriteRunConfig,
) -> WriteRunConfig:
    """Build an isolated Challenger config from the resolved Champion config."""

    champion_output = Path(champion_config.output_dir).expanduser().resolve()
    raw_output = str(getattr(args, "challenger_output", "") or "").strip()
    challenger_output = (
        Path(raw_output).expanduser().resolve()
        if raw_output
        else champion_output.with_name(f"{champion_output.name}-challenger")
    )
    if challenger_output == champion_output:
        raise ValueError("--challenger-output 必须与 Champion 输出目录不同")

    write_override = str(getattr(args, "challenger_model_name", "") or "").strip()
    audit_override = str(getattr(args, "challenger_audit_model_name", "") or "").strip()
    return replace(
        champion_config,
        output_dir=str(challenger_output),
        write_model_override_name=write_override or champion_config.write_model_override_name,
        audit_model_override_name=audit_override or champion_config.audit_model_override_name,
        scene_models={},
        scene_fallback_models={},
    )


def _preflight_champion_and_challenger(
    *,
    champion_config: WriteRunConfig,
    challenger_config: WriteRunConfig,
    write_service: WriteService,
) -> int:
    """Preflight both plans before either write run creates artifacts."""

    champion_code = _run_write_preflight(
        write_config=champion_config,
        write_service=write_service,
        run_label="Champion",
    )
    challenger_code = _run_write_preflight(
        write_config=challenger_config,
        write_service=write_service,
        run_label="Challenger",
    )
    return 0 if champion_code == 0 and challenger_code == 0 else 2


def _run_champion_challenger_experiment(
    *,
    champion_config: WriteRunConfig,
    challenger_config: WriteRunConfig,
    write_service: WriteService,
) -> int:
    """Run both isolated plans and persist a deterministic comparison artifact."""

    champion_exit_code = _run_write_stage(
        write_config=champion_config,
        write_service=write_service,
    )
    champion_summary = Path(champion_config.output_dir) / "run_summary.json"
    if champion_exit_code not in {0, 4} or not champion_summary.is_file():
        Log.error("Champion 本次运行未生成可比较摘要，停止 Challenger 实验", module=MODULE)
        return champion_exit_code if champion_exit_code != 0 else 2

    challenger_exit_code = _run_write_stage(
        write_config=challenger_config,
        write_service=write_service,
    )
    challenger_summary = Path(challenger_config.output_dir) / "run_summary.json"
    if challenger_exit_code not in {0, 4} or not challenger_summary.is_file():
        Log.error("Challenger 本次运行未生成可比较摘要，无法完成对比", module=MODULE)
        return challenger_exit_code if challenger_exit_code != 0 else 2

    try:
        comparison = compare_write_run_paths(champion_summary, challenger_summary)
        comparison_path = persist_write_run_comparison(
            comparison,
            Path(champion_config.output_dir) / _CHALLENGER_COMPARISON_FILE,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        Log.error(f"Champion/Challenger 对比失败: {exc}", module=MODULE)
        return 2

    Log.info(
        f"Champion/Challenger 对比完成: verdict={comparison['verdict']}, artifact={comparison_path}",
        module=MODULE,
    )
    if champion_exit_code != 0:
        return champion_exit_code
    return 0


def _manifest_has_usable_company_facets(manifest_path: Path) -> bool:
    """Return True only when the manifest carries a loadable company facet object.

    A prior write whose facet inference hit a transient error persists
    ``company_facets: null``. Treating that file as "already inferred" would make
    ``--research-template auto`` fail hard at template resolution instead of
    re-inferring, so the auto bootstrap must key off facet presence, not mere
    file existence.
    """

    from dayu.cli.research_template_routing import load_company_facets_from_manifest

    if not manifest_path.is_file():
        return False
    try:
        load_company_facets_from_manifest(manifest_path)
    except (OSError, ValueError):
        return False
    return True


def _needs_auto_research_bootstrap(args: argparse.Namespace, *, output_dir: Path) -> bool:
    requested = str(getattr(args, "research_template", "") or "").strip().lower()
    if requested != "auto":
        return False
    return not _manifest_has_usable_company_facets(output_dir / "manifest.json")


def _build_auto_bootstrap_args(args: argparse.Namespace) -> argparse.Namespace:
    values = dict(vars(args))
    values.update({"template": None, "research_template": None, "infer": True})
    return argparse.Namespace(**values)


def _validate_challenger_run_plan_args(
    args: argparse.Namespace,
) -> str | None:
    """Require an explicit, bounded and reproducible full-run CLI plan."""

    required_options = (
        ("template", "--template"),
        ("output", "--output"),
        ("challenger_output", "--challenger-output"),
        ("web_provider", "--web-provider"),
        (
            "write_max_model_requests",
            "--write-max-model-requests",
        ),
        (
            "write_max_total_tokens",
            "--write-max-total-tokens",
        ),
        (
            "write_max_estimated_cost",
            "--write-max-estimated-cost",
        ),
        (
            "write_budget_currency",
            "--write-budget-currency",
        ),
    )
    for attribute, option_name in required_options:
        value = getattr(args, attribute, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"Challenger 双跑授权需要显式提供 {option_name}"
    if not str(getattr(args, "model_name", "") or "").strip() and (
        not str(getattr(args, "audit_model_name", "") or "").strip()
    ):
        return "Challenger 双跑授权需要显式提供相关 Champion 模型参数"
    if bool(getattr(args, "resume", True)):
        return "Challenger 双跑授权需要使用 --no-resume"
    if bool(getattr(args, "fast", False)):
        return "Challenger 双跑授权不允许使用 --fast"
    if bool(getattr(args, "force", False)):
        return "Challenger 双跑授权不允许使用 --force"
    if str(getattr(args, "chapter", "") or "").strip():
        return "Challenger 双跑授权不允许使用 --chapter"
    if str(getattr(args, "research_template", "") or "").strip():
        return "Challenger 双跑授权不允许使用 --research-template"
    if bool(getattr(args, "materialize_research", False)):
        return "Challenger 双跑授权不允许使用 --materialize-research"
    if bool(getattr(args, "research_base", None)) or bool(getattr(args, "overwrite_research", False)):
        return "Challenger 双跑授权不允许使用 research 物化参数"
    return None


def _validate_research_materialization_args(args: argparse.Namespace) -> str | None:
    materialize = bool(getattr(args, "materialize_research", False))
    preflight_only = bool(getattr(args, "preflight_only", False))
    summary = bool(getattr(args, "summary", False))
    reprice_costs = bool(getattr(args, "reprice_costs", False))
    routing_history_root = bool(str(getattr(args, "routing_history_root", "") or "").strip())
    routing_proposal_input = bool(str(getattr(args, "routing_proposal_input", "") or "").strip())
    routing_proposal_output = bool(str(getattr(args, "routing_proposal_output", "") or "").strip())
    overwrite_routing_proposal = bool(getattr(args, "overwrite_routing_proposal", False))
    challenger_promotion_proposal_input = bool(
        str(
            getattr(
                args,
                "challenger_promotion_proposal_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_promotion_proposal_output = bool(
        str(
            getattr(
                args,
                "challenger_promotion_proposal_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_change_request_input = bool(
        str(
            getattr(
                args,
                "challenger_config_change_request_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_change_request_output = bool(
        str(
            getattr(
                args,
                "challenger_config_change_request_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_change_approval_request = bool(
        str(
            getattr(
                args,
                "challenger_config_change_approval_request",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_change_approval_output = bool(
        str(
            getattr(
                args,
                "challenger_config_change_approval_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_change_approval_input = bool(
        str(
            getattr(
                args,
                "challenger_config_change_approval_input",
                "",
            )
            or ""
        ).strip()
    )
    write_routing_snapshot_output = bool(
        str(
            getattr(
                args,
                "write_routing_snapshot_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_preapplication_plan_output = bool(
        str(
            getattr(
                args,
                "challenger_config_preapplication_plan_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_preapplication_plan_input = bool(
        str(
            getattr(
                args,
                "challenger_config_preapplication_plan_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_preapplication_requested = (
        challenger_config_preapplication_plan_output or challenger_config_preapplication_plan_input
    )
    apply_write_model_configuration = bool(getattr(args, "apply_write_model_configuration", False))
    challenger_config_application_plan_input = bool(
        str(
            getattr(
                args,
                "challenger_config_application_plan_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_application_receipt_output = bool(
        str(
            getattr(
                args,
                "challenger_config_application_receipt_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_application_receipt_input = bool(
        str(
            getattr(
                args,
                "challenger_config_application_receipt_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_rollback_plan_output = bool(
        str(
            getattr(
                args,
                "challenger_config_rollback_plan_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_rollback_plan_input = bool(
        str(
            getattr(
                args,
                "challenger_config_rollback_plan_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_rollback_approval_request = bool(
        str(
            getattr(
                args,
                "challenger_config_rollback_approval_request",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_rollback_approval_output = bool(
        str(
            getattr(
                args,
                "challenger_config_rollback_approval_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_rollback_approval_input = bool(
        str(
            getattr(
                args,
                "challenger_config_rollback_approval_input",
                "",
            )
            or ""
        ).strip()
    )
    rollback_write_model_configuration = bool(getattr(args, "rollback_write_model_configuration", False))
    challenger_config_rollback_receipt_output = bool(
        str(
            getattr(
                args,
                "challenger_config_rollback_receipt_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_rollback_receipt_input = bool(
        str(
            getattr(
                args,
                "challenger_config_rollback_receipt_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_manual_recovery_receipt_input = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_receipt_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_manual_recovery_evidence_output = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_evidence_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_manual_recovery_requested = (
        challenger_config_manual_recovery_receipt_input or challenger_config_manual_recovery_evidence_output
    )
    challenger_config_manual_recovery_evidence_input = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_evidence_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_manual_recovery_selection_request = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_selection_request",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_manual_recovery_plan_output = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_plan_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_manual_recovery_plan_input = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_plan_input",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_manual_recovery_approval_request = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_approval_request",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_manual_recovery_approval_output = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_approval_output",
                "",
            )
            or ""
        ).strip()
    )
    challenger_config_manual_recovery_approval_input = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_approval_input",
                "",
            )
            or ""
        ).strip()
    )
    recover_write_model_configuration = bool(getattr(args, "recover_write_model_configuration", False))
    challenger_config_manual_recovery_receipt_output = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_receipt_output",
                "",
            )
            or ""
        ).strip()
    )
    verify_write_model_configuration_manual_recovery = bool(
        getattr(
            args,
            "verify_write_model_configuration_manual_recovery",
            False,
        )
    )
    manual_recovery_verification_receipt_input = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_verification_receipt_input",
                "",
            )
            or ""
        ).strip()
    )
    clear_write_model_configuration_manual_recovery = bool(
        getattr(
            args,
            "clear_write_model_configuration_manual_recovery",
            False,
        )
    )
    manual_recovery_clearance_receipt_input = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_clearance_receipt_input",
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_clearance_request = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_clearance_request",
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_clearance_output = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_clearance_output",
                "",
            )
            or ""
        ).strip()
    )
    revoke_write_model_configuration_manual_recovery_clearance = bool(
        getattr(
            args,
            ("revoke_write_model_configuration_manual_recovery_clearance"),
            False,
        )
    )
    manual_recovery_clearance_revocation_receipt_input = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_clearance_revocation_receipt_input"),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_clearance_revocation_clearance_input = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_clearance_revocation_clearance_input"),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_clearance_revocation_request = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_clearance_revocation_request"),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_clearance_revocation_output = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_clearance_revocation_output"),
                "",
            )
            or ""
        ).strip()
    )
    restart_write_model_configuration_manual_recovery = bool(
        getattr(
            args,
            ("restart_write_model_configuration_manual_recovery_after_clearance_revocation"),
            False,
        )
    )
    manual_recovery_restart_receipt_input = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_restart_receipt_input",
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_restart_clearance_input = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_restart_clearance_input"),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_restart_revocation_input = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_restart_revocation_input"),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_restart_evidence_output = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_restart_evidence_output"),
                "",
            )
            or ""
        ).strip()
    )
    check_write_model_configuration_manual_recovery_gate = bool(
        getattr(
            args,
            "check_write_model_configuration_manual_recovery_gate",
            False,
        )
    )
    manual_recovery_gate_output = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_gate_output",
                "",
            )
            or ""
        ).strip()
    )
    verify_write_model_configuration_manual_recovery_gate = bool(
        getattr(
            args,
            "verify_write_model_configuration_manual_recovery_gate",
            False,
        )
    )
    manual_recovery_gate_input = bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_gate_input",
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_gate_verification_output = bool(
        str(
            getattr(
                args,
                (
                    "challenger_config_manual_recovery_gate_"
                    "verification_output"
                ),
                "",
            )
            or ""
        ).strip()
    )
    revalidate_write_model_configuration_manual_recovery_gate_verification = bool(
        getattr(
            args,
            (
                "revalidate_write_model_configuration_manual_recovery_"
                "gate_verification"
            ),
            False,
        )
    )
    manual_recovery_gate_verification_input = bool(
        str(
            getattr(
                args,
                (
                    "challenger_config_manual_recovery_gate_"
                    "verification_input"
                ),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_gate_verification_revalidation_output = bool(
        str(
            getattr(
                args,
                (
                    "challenger_config_manual_recovery_gate_"
                    "verification_revalidation_output"
                ),
                "",
            )
            or ""
        ).strip()
    )
    audit_write_model_configuration_manual_recovery_history = bool(
        getattr(
            args,
            "audit_write_model_configuration_manual_recovery_history",
            False,
        )
    )
    manual_recovery_audit_timeline_output = bool(
        str(
            getattr(
                args,
                (
                    "challenger_config_manual_recovery_audit_"
                    "timeline_output"
                ),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_plan_mode_requested = any(
        (
            challenger_config_manual_recovery_evidence_input,
            challenger_config_manual_recovery_selection_request,
            challenger_config_manual_recovery_plan_output,
        )
    )
    manual_recovery_approval_mode_requested = any(
        (
            challenger_config_manual_recovery_approval_request,
            challenger_config_manual_recovery_approval_output,
        )
    )
    manual_recovery_application_mode_requested = any(
        (
            recover_write_model_configuration,
            challenger_config_manual_recovery_approval_input,
            challenger_config_manual_recovery_receipt_output,
        )
    )
    manual_recovery_verification_mode_requested = any(
        (
            verify_write_model_configuration_manual_recovery,
            manual_recovery_verification_receipt_input,
        )
    )
    manual_recovery_clearance_mode_requested = any(
        (
            clear_write_model_configuration_manual_recovery,
            manual_recovery_clearance_receipt_input,
            manual_recovery_clearance_request,
            manual_recovery_clearance_output,
        )
    )
    manual_recovery_clearance_revocation_mode_requested = any(
        (
            revoke_write_model_configuration_manual_recovery_clearance,
            manual_recovery_clearance_revocation_receipt_input,
            manual_recovery_clearance_revocation_clearance_input,
            manual_recovery_clearance_revocation_request,
            manual_recovery_clearance_revocation_output,
        )
    )
    manual_recovery_restart_mode_requested = any(
        (
            restart_write_model_configuration_manual_recovery,
            manual_recovery_restart_receipt_input,
            manual_recovery_restart_clearance_input,
            manual_recovery_restart_revocation_input,
            manual_recovery_restart_evidence_output,
        )
    )
    manual_recovery_gate_check_mode_requested = (
        check_write_model_configuration_manual_recovery_gate or manual_recovery_gate_output
    )
    manual_recovery_gate_verification_mode_requested = any(
        (
            verify_write_model_configuration_manual_recovery_gate,
            manual_recovery_gate_input,
            manual_recovery_gate_verification_output,
        )
    )
    manual_recovery_gate_revalidation_mode_requested = any(
        (
            revalidate_write_model_configuration_manual_recovery_gate_verification,
            manual_recovery_gate_verification_input,
            manual_recovery_gate_verification_revalidation_output,
        )
    )
    manual_recovery_history_audit_mode_requested = (
        audit_write_model_configuration_manual_recovery_history
        or manual_recovery_audit_timeline_output
    )
    manual_recovery_control_requested = any(
        (
            manual_recovery_plan_mode_requested,
            manual_recovery_approval_mode_requested,
            manual_recovery_application_mode_requested,
            manual_recovery_verification_mode_requested,
            manual_recovery_clearance_mode_requested,
            manual_recovery_clearance_revocation_mode_requested,
            manual_recovery_restart_mode_requested,
            manual_recovery_gate_check_mode_requested,
            manual_recovery_gate_verification_mode_requested,
            manual_recovery_gate_revalidation_mode_requested,
            manual_recovery_history_audit_mode_requested,
            challenger_config_manual_recovery_plan_input,
        )
    )
    challenger_config_rollback_application_requested = (
        rollback_write_model_configuration or challenger_config_rollback_receipt_output
    )
    challenger_config_rollback_requested = any(
        (
            challenger_config_rollback_plan_output,
            challenger_config_rollback_plan_input,
            challenger_config_rollback_approval_request,
            challenger_config_rollback_approval_output,
            challenger_config_rollback_approval_input,
            challenger_config_rollback_application_requested,
        )
    )
    challenger_config_rollback_read_only_requested = (
        challenger_config_rollback_requested and not challenger_config_rollback_application_requested
    )
    challenger_config_rollback_approval_issuance = (
        challenger_config_rollback_approval_request or challenger_config_rollback_approval_output
    )
    challenger_config_application_requested = (
        apply_write_model_configuration
        or challenger_config_application_plan_input
        or challenger_config_application_receipt_output
    )
    challenger_config_change_approval_issuance = (
        challenger_config_change_approval_request or challenger_config_change_approval_output
    )
    challenger_config_change_summary_requested = (
        challenger_config_change_request_input
        or challenger_config_change_request_output
        or challenger_config_change_approval_issuance
    )
    routing_preflight_approval_request = bool(
        str(
            getattr(
                args,
                "routing_preflight_approval_request",
                "",
            )
            or ""
        ).strip()
    )
    routing_preflight_approval_output = bool(
        str(
            getattr(
                args,
                "routing_preflight_approval_output",
                "",
            )
            or ""
        ).strip()
    )
    routing_preflight_approval_input = bool(
        str(
            getattr(
                args,
                "routing_preflight_approval_input",
                "",
            )
            or ""
        ).strip()
    )
    routing_challenger_run_plan_output = bool(
        str(
            getattr(
                args,
                "routing_challenger_run_plan_output",
                "",
            )
            or ""
        ).strip()
    )
    routing_challenger_run_approval_request = bool(
        str(
            getattr(
                args,
                "routing_challenger_run_approval_request",
                "",
            )
            or ""
        ).strip()
    )
    routing_challenger_run_approval_output = bool(
        str(
            getattr(
                args,
                "routing_challenger_run_approval_output",
                "",
            )
            or ""
        ).strip()
    )
    routing_challenger_run_approval_input = bool(
        str(
            getattr(
                args,
                "routing_challenger_run_approval_input",
                "",
            )
            or ""
        ).strip()
    )
    routing_challenger_run_approval_issuance = (
        routing_challenger_run_plan_output
        or routing_challenger_run_approval_request
        or routing_challenger_run_approval_output
    )
    routing_preflight_approval_requested = routing_preflight_approval_request or routing_preflight_approval_output
    challenger_requested = _challenger_requested(args)
    challenger_output = bool(str(getattr(args, "challenger_output", "") or "").strip())
    if challenger_config_manual_recovery_receipt_input != challenger_config_manual_recovery_evidence_output:
        return (
            "--challenger-config-manual-recovery-receipt-input and "
            "--challenger-config-manual-recovery-evidence-output must "
            "be provided together"
        )
    if challenger_config_manual_recovery_requested and manual_recovery_control_requested:
        return "manual recovery evidence export, planning, approval, and execution are separate dedicated modes"
    if manual_recovery_control_requested:
        active_mode_count = sum(
            (
                manual_recovery_plan_mode_requested,
                manual_recovery_approval_mode_requested,
                manual_recovery_application_mode_requested,
                manual_recovery_verification_mode_requested,
                manual_recovery_clearance_mode_requested,
                manual_recovery_clearance_revocation_mode_requested,
                manual_recovery_restart_mode_requested,
                manual_recovery_gate_check_mode_requested,
                manual_recovery_gate_verification_mode_requested,
                manual_recovery_gate_revalidation_mode_requested,
                manual_recovery_history_audit_mode_requested,
            )
        )
        if active_mode_count != 1:
            return (
                "manual recovery requires exactly one of planning, "
                "approval issuance, execution, verification, or "
                "clearance, clearance revocation, restart, or "
                "gate-check, gate-verification, or gate-verification "
                "revalidation, or history-audit mode"
            )
        if manual_recovery_plan_mode_requested and not all(
            (
                challenger_config_manual_recovery_evidence_input,
                challenger_config_manual_recovery_selection_request,
                challenger_config_manual_recovery_plan_output,
            )
        ):
            return (
                "manual recovery planning requires "
                "--challenger-config-manual-recovery-evidence-input, "
                "--challenger-config-manual-recovery-selection-request, "
                "and --challenger-config-manual-recovery-plan-output"
            )
        if manual_recovery_plan_mode_requested and challenger_config_manual_recovery_plan_input:
            return "manual recovery plan input cannot be combined with manual recovery plan export"
        if manual_recovery_approval_mode_requested and not all(
            (
                challenger_config_manual_recovery_plan_input,
                challenger_config_manual_recovery_approval_request,
                challenger_config_manual_recovery_approval_output,
            )
        ):
            return (
                "manual recovery approval issuance requires "
                "--challenger-config-manual-recovery-plan-input, "
                "--challenger-config-manual-recovery-approval-request, "
                "and --challenger-config-manual-recovery-approval-output"
            )
        if manual_recovery_application_mode_requested and not all(
            (
                recover_write_model_configuration,
                challenger_config_manual_recovery_plan_input,
                challenger_config_manual_recovery_approval_input,
                challenger_config_manual_recovery_receipt_output,
            )
        ):
            return (
                "manual recovery execution requires "
                "--recover-write-model-configuration, "
                "--challenger-config-manual-recovery-plan-input, "
                "--challenger-config-manual-recovery-approval-input, "
                "and --challenger-config-manual-recovery-receipt-output"
            )
        if manual_recovery_verification_mode_requested and not all(
            (
                verify_write_model_configuration_manual_recovery,
                manual_recovery_verification_receipt_input,
            )
        ):
            return (
                "manual recovery verification requires "
                "--verify-write-model-configuration-manual-recovery and "
                "--challenger-config-manual-recovery-verification-"
                "receipt-input"
            )
        if manual_recovery_clearance_mode_requested and not all(
            (
                clear_write_model_configuration_manual_recovery,
                manual_recovery_clearance_receipt_input,
                manual_recovery_clearance_request,
                manual_recovery_clearance_output,
            )
        ):
            return (
                "manual recovery clearance requires "
                "--clear-write-model-configuration-manual-recovery, "
                "--challenger-config-manual-recovery-clearance-"
                "receipt-input, "
                "--challenger-config-manual-recovery-clearance-request, "
                "and --challenger-config-manual-recovery-clearance-output"
            )
        if manual_recovery_clearance_revocation_mode_requested and not all(
            (
                revoke_write_model_configuration_manual_recovery_clearance,
                manual_recovery_clearance_revocation_receipt_input,
                manual_recovery_clearance_revocation_clearance_input,
                manual_recovery_clearance_revocation_request,
                manual_recovery_clearance_revocation_output,
            )
        ):
            return (
                "manual recovery clearance revocation requires "
                "--revoke-write-model-configuration-manual-recovery-"
                "clearance, --challenger-config-manual-recovery-"
                "clearance-revocation-receipt-input, "
                "--challenger-config-manual-recovery-clearance-"
                "revocation-clearance-input, --challenger-config-"
                "manual-recovery-clearance-revocation-request, and "
                "--challenger-config-manual-recovery-clearance-"
                "revocation-output"
            )
        if manual_recovery_restart_mode_requested and not all(
            (
                restart_write_model_configuration_manual_recovery,
                manual_recovery_restart_receipt_input,
                manual_recovery_restart_clearance_input,
                manual_recovery_restart_revocation_input,
                manual_recovery_restart_evidence_output,
            )
        ):
            return (
                "manual recovery restart requires "
                "--restart-write-model-configuration-manual-recovery-"
                "after-clearance-revocation, --challenger-config-"
                "manual-recovery-restart-receipt-input, "
                "--challenger-config-manual-recovery-restart-"
                "clearance-input, --challenger-config-manual-recovery-"
                "restart-revocation-input, and --challenger-config-"
                "manual-recovery-restart-evidence-output"
            )
        if manual_recovery_gate_check_mode_requested and not check_write_model_configuration_manual_recovery_gate:
            return (
                "--challenger-config-manual-recovery-gate-output requires "
                "--check-write-model-configuration-manual-recovery-gate"
            )
        if (
            manual_recovery_gate_verification_mode_requested
            and not all(
                (
                    verify_write_model_configuration_manual_recovery_gate,
                    manual_recovery_gate_input,
                )
            )
        ):
            return (
                "manual recovery gate verification requires "
                "--verify-write-model-configuration-manual-recovery-gate "
                "and --challenger-config-manual-recovery-gate-input"
            )
        if (
            manual_recovery_gate_revalidation_mode_requested
            and not all(
                (
                    revalidate_write_model_configuration_manual_recovery_gate_verification,
                    manual_recovery_gate_verification_input,
                )
            )
        ):
            return (
                "manual recovery gate verification revalidation "
                "requires --revalidate-write-model-configuration-"
                "manual-recovery-gate-verification and --challenger-"
                "config-manual-recovery-gate-verification-input"
            )
        if (
            manual_recovery_history_audit_mode_requested
            and not audit_write_model_configuration_manual_recovery_history
        ):
            return (
                "--challenger-config-manual-recovery-audit-timeline-"
                "output requires --audit-write-model-configuration-"
                "manual-recovery-history"
            )
        if manual_recovery_verification_mode_requested and any(
            (
                challenger_config_manual_recovery_evidence_input,
                challenger_config_manual_recovery_selection_request,
                challenger_config_manual_recovery_plan_output,
                challenger_config_manual_recovery_plan_input,
                challenger_config_manual_recovery_approval_request,
                challenger_config_manual_recovery_approval_output,
                challenger_config_manual_recovery_approval_input,
                recover_write_model_configuration,
                challenger_config_manual_recovery_receipt_output,
            )
        ):
            return (
                "manual recovery verification cannot be combined with "
                "manual recovery planning, approval, or execution inputs"
            )
        if manual_recovery_clearance_mode_requested and any(
            (
                challenger_config_manual_recovery_evidence_input,
                challenger_config_manual_recovery_selection_request,
                challenger_config_manual_recovery_plan_output,
                challenger_config_manual_recovery_plan_input,
                challenger_config_manual_recovery_approval_request,
                challenger_config_manual_recovery_approval_output,
                challenger_config_manual_recovery_approval_input,
                recover_write_model_configuration,
                challenger_config_manual_recovery_receipt_output,
                verify_write_model_configuration_manual_recovery,
                manual_recovery_verification_receipt_input,
            )
        ):
            return (
                "manual recovery clearance cannot be combined with "
                "manual recovery planning, approval, execution, or "
                "verification inputs"
            )
        if manual_recovery_clearance_revocation_mode_requested and any(
            (
                challenger_config_manual_recovery_evidence_input,
                challenger_config_manual_recovery_selection_request,
                challenger_config_manual_recovery_plan_output,
                challenger_config_manual_recovery_plan_input,
                challenger_config_manual_recovery_approval_request,
                challenger_config_manual_recovery_approval_output,
                challenger_config_manual_recovery_approval_input,
                recover_write_model_configuration,
                challenger_config_manual_recovery_receipt_output,
                verify_write_model_configuration_manual_recovery,
                manual_recovery_verification_receipt_input,
                clear_write_model_configuration_manual_recovery,
                manual_recovery_clearance_receipt_input,
                manual_recovery_clearance_request,
                manual_recovery_clearance_output,
            )
        ):
            return (
                "manual recovery clearance revocation cannot be "
                "combined with manual recovery planning, approval, "
                "execution, verification, or clearance inputs"
            )
        if manual_recovery_restart_mode_requested and any(
            (
                challenger_config_manual_recovery_evidence_input,
                challenger_config_manual_recovery_selection_request,
                challenger_config_manual_recovery_plan_output,
                challenger_config_manual_recovery_plan_input,
                challenger_config_manual_recovery_approval_request,
                challenger_config_manual_recovery_approval_output,
                challenger_config_manual_recovery_approval_input,
                recover_write_model_configuration,
                challenger_config_manual_recovery_receipt_output,
                verify_write_model_configuration_manual_recovery,
                manual_recovery_verification_receipt_input,
                clear_write_model_configuration_manual_recovery,
                manual_recovery_clearance_receipt_input,
                manual_recovery_clearance_request,
                manual_recovery_clearance_output,
                revoke_write_model_configuration_manual_recovery_clearance,
                manual_recovery_clearance_revocation_receipt_input,
                manual_recovery_clearance_revocation_clearance_input,
                manual_recovery_clearance_revocation_request,
                manual_recovery_clearance_revocation_output,
            )
        ):
            return (
                "manual recovery restart cannot be combined with "
                "manual recovery planning, approval, execution, "
                "verification, clearance, or revocation inputs"
            )
        if manual_recovery_gate_check_mode_requested and any(
            (
                challenger_config_manual_recovery_evidence_input,
                challenger_config_manual_recovery_selection_request,
                challenger_config_manual_recovery_plan_output,
                challenger_config_manual_recovery_plan_input,
                challenger_config_manual_recovery_approval_request,
                challenger_config_manual_recovery_approval_output,
                challenger_config_manual_recovery_approval_input,
                recover_write_model_configuration,
                challenger_config_manual_recovery_receipt_output,
                verify_write_model_configuration_manual_recovery,
                manual_recovery_verification_receipt_input,
                clear_write_model_configuration_manual_recovery,
                manual_recovery_clearance_receipt_input,
                manual_recovery_clearance_request,
                manual_recovery_clearance_output,
                revoke_write_model_configuration_manual_recovery_clearance,
                manual_recovery_clearance_revocation_receipt_input,
                manual_recovery_clearance_revocation_clearance_input,
                manual_recovery_clearance_revocation_request,
                manual_recovery_clearance_revocation_output,
                restart_write_model_configuration_manual_recovery,
                manual_recovery_restart_receipt_input,
                manual_recovery_restart_clearance_input,
                manual_recovery_restart_revocation_input,
                manual_recovery_restart_evidence_output,
            )
        ):
            return (
                "manual recovery gate check cannot be combined with "
                "manual recovery planning, approval, execution, "
                "verification, or clearance inputs"
            )
        if (
            manual_recovery_gate_verification_mode_requested
            and challenger_config_manual_recovery_plan_input
        ):
            return (
                "manual recovery gate verification cannot be combined "
                "with manual recovery planning, approval, execution, "
                "verification, clearance, revocation, restart, or "
                "gate-check inputs"
            )
        if (
            manual_recovery_gate_revalidation_mode_requested
            and challenger_config_manual_recovery_plan_input
        ):
            return (
                "manual recovery gate verification revalidation cannot "
                "be combined with manual recovery planning, approval, "
                "execution, verification, clearance, revocation, "
                "restart, gate-check, or gate-verification inputs"
            )
        if (
            manual_recovery_history_audit_mode_requested
            and challenger_config_manual_recovery_plan_input
        ):
            return (
                "manual recovery history audit cannot be combined "
                "with manual recovery planning, approval, execution, "
                "verification, clearance, revocation, restart, "
                "gate-check, gate-verification, or revalidation inputs"
            )
        if any(
            (
                summary,
                preflight_only,
                reprice_costs,
                materialize,
                routing_history_root,
                routing_proposal_input,
                routing_proposal_output,
                overwrite_routing_proposal,
                challenger_promotion_proposal_input,
                challenger_promotion_proposal_output,
                challenger_config_change_request_input,
                challenger_config_change_request_output,
                challenger_config_change_approval_request,
                challenger_config_change_approval_output,
                challenger_config_change_approval_input,
                write_routing_snapshot_output,
                challenger_config_preapplication_requested,
                challenger_config_application_requested,
                challenger_config_application_receipt_input,
                challenger_config_rollback_requested,
                challenger_config_rollback_receipt_input,
                routing_preflight_approval_requested,
                routing_preflight_approval_input,
                routing_challenger_run_approval_issuance,
                routing_challenger_run_approval_input,
                challenger_requested,
                challenger_output,
            )
        ):
            return (
                "manual recovery control is a dedicated mode and cannot "
                "be combined with write, preflight, application, "
                "rollback, routing, proposal, or Challenger operations"
            )
        if any(
            (
                bool(str(getattr(args, "model_name", "") or "").strip()),
                bool(str(getattr(args, "audit_model_name", "") or "").strip()),
                bool(str(getattr(args, "fallback_model_name", "") or "").strip()),
                bool(
                    str(
                        getattr(
                            args,
                            "audit_fallback_model_name",
                            "",
                        )
                        or ""
                    ).strip()
                ),
                getattr(args, "temperature", None) is not None,
                bool(getattr(args, "fast", False)),
                bool(getattr(args, "force", False)),
                bool(getattr(args, "infer", False)),
                bool(str(getattr(args, "chapter", "") or "").strip()),
                bool(getattr(args, "research_base", None)),
                bool(getattr(args, "overwrite_research", False)),
            )
        ):
            return (
                "manual recovery control forbids model overrides, "
                "fallbacks, temperature overrides, partial write modes, "
                "and research materialization"
            )
        return None
    if challenger_config_manual_recovery_requested and any(
        (
            summary,
            preflight_only,
            reprice_costs,
            materialize,
            routing_history_root,
            routing_proposal_input,
            routing_proposal_output,
            overwrite_routing_proposal,
            challenger_promotion_proposal_input,
            challenger_promotion_proposal_output,
            challenger_config_change_request_input,
            challenger_config_change_request_output,
            challenger_config_change_approval_request,
            challenger_config_change_approval_output,
            challenger_config_change_approval_input,
            write_routing_snapshot_output,
            challenger_config_preapplication_requested,
            challenger_config_application_requested,
            challenger_config_application_receipt_input,
            challenger_config_rollback_requested,
            challenger_config_rollback_receipt_input,
            routing_preflight_approval_requested,
            routing_preflight_approval_input,
            routing_challenger_run_approval_issuance,
            routing_challenger_run_approval_input,
            challenger_requested,
            challenger_output,
        )
    ):
        return (
            "manual recovery evidence export is a dedicated read-only "
            "mode and cannot be combined with write, preflight, "
            "application, rollback, routing, proposal, approval, or "
            "Challenger operations"
        )
    if challenger_config_manual_recovery_requested and any(
        (
            bool(str(getattr(args, "model_name", "") or "").strip()),
            bool(str(getattr(args, "audit_model_name", "") or "").strip()),
            bool(str(getattr(args, "fallback_model_name", "") or "").strip()),
            bool(
                str(
                    getattr(
                        args,
                        "audit_fallback_model_name",
                        "",
                    )
                    or ""
                ).strip()
            ),
            getattr(args, "temperature", None) is not None,
            bool(getattr(args, "fast", False)),
            bool(getattr(args, "force", False)),
            bool(getattr(args, "infer", False)),
            bool(str(getattr(args, "chapter", "") or "").strip()),
            bool(getattr(args, "research_base", None)),
            bool(getattr(args, "overwrite_research", False)),
        )
    ):
        return (
            "manual recovery evidence export forbids model overrides, "
            "fallbacks, temperature overrides, partial write modes, "
            "and research materialization"
        )
    if challenger_config_manual_recovery_requested:
        return None
    if challenger_output and not challenger_requested:
        return "--challenger-output 需要同时提供至少一个 Challenger 模型覆盖参数"
    if challenger_requested and summary:
        return "Challenger 运行不能与 --summary 同时使用"
    if challenger_requested and bool(getattr(args, "infer", False)):
        return "Challenger 运行暂不支持 infer-only 的 --infer"
    if preflight_only and summary:
        return "--preflight-only 不能与 --summary 同时使用"
    if reprice_costs and not summary:
        return "--reprice-costs 需要与 --summary 同时使用"
    if challenger_config_application_requested and not all(
        (
            apply_write_model_configuration,
            challenger_config_application_plan_input,
            challenger_config_change_approval_input,
            challenger_config_application_receipt_output,
        )
    ):
        return (
            "configuration application requires "
            "--apply-write-model-configuration, "
            "--challenger-config-application-plan-input, "
            "--challenger-config-change-approval-input, and "
            "--challenger-config-application-receipt-output"
        )
    if challenger_config_application_requested and (summary or preflight_only):
        return "configuration application is a dedicated mode and cannot be combined with --summary or --preflight-only"
    if challenger_config_application_requested and (
        challenger_requested
        or challenger_config_rollback_receipt_input
        or write_routing_snapshot_output
        or challenger_config_preapplication_requested
        or challenger_config_change_summary_requested
        or routing_preflight_approval_requested
        or routing_preflight_approval_input
        or routing_challenger_run_approval_issuance
        or routing_challenger_run_approval_input
        or routing_history_root
        or routing_proposal_input
        or routing_proposal_output
    ):
        return (
            "configuration application cannot be combined with routing, "
            "proposal, approval issuance, or Challenger run operations"
        )
    if challenger_config_application_requested and any(
        (
            bool(str(getattr(args, "model_name", "") or "").strip()),
            bool(str(getattr(args, "audit_model_name", "") or "").strip()),
            bool(str(getattr(args, "fallback_model_name", "") or "").strip()),
            bool(
                str(
                    getattr(
                        args,
                        "audit_fallback_model_name",
                        "",
                    )
                    or ""
                ).strip()
            ),
            getattr(args, "temperature", None) is not None,
            bool(getattr(args, "fast", False)),
            bool(getattr(args, "force", False)),
            bool(getattr(args, "infer", False)),
            bool(str(getattr(args, "chapter", "") or "").strip()),
            bool(getattr(args, "materialize_research", False)),
            bool(getattr(args, "research_base", None)),
            bool(getattr(args, "overwrite_research", False)),
        )
    ):
        return (
            "configuration application forbids model overrides, "
            "fallbacks, temperature overrides, partial write modes, "
            "and research materialization"
        )
    if challenger_config_rollback_application_requested and not all(
        (
            rollback_write_model_configuration,
            challenger_config_rollback_plan_input,
            challenger_config_rollback_approval_input,
            challenger_config_rollback_receipt_output,
        )
    ):
        return (
            "configuration operator rollback requires "
            "--rollback-write-model-configuration, "
            "--challenger-config-rollback-plan-input, "
            "--challenger-config-rollback-approval-input, and "
            "--challenger-config-rollback-receipt-output"
        )
    if challenger_config_rollback_application_requested and (summary or preflight_only):
        return (
            "configuration operator rollback is a dedicated mode and "
            "cannot be combined with --summary or --preflight-only"
        )
    if challenger_config_rollback_application_requested and (
        challenger_config_application_requested
        or challenger_config_application_receipt_input
        or challenger_config_rollback_receipt_input
        or challenger_config_rollback_plan_output
        or challenger_config_rollback_approval_issuance
        or challenger_requested
        or write_routing_snapshot_output
        or challenger_config_preapplication_requested
        or challenger_config_change_summary_requested
        or challenger_config_change_approval_input
        or routing_preflight_approval_requested
        or routing_preflight_approval_input
        or routing_challenger_run_approval_issuance
        or routing_challenger_run_approval_input
        or routing_history_root
        or routing_proposal_input
        or routing_proposal_output
    ):
        return (
            "configuration operator rollback cannot be combined with "
            "application, routing, proposal, approval issuance, or "
            "Challenger run operations"
        )
    if challenger_config_rollback_application_requested and any(
        (
            bool(str(getattr(args, "model_name", "") or "").strip()),
            bool(str(getattr(args, "audit_model_name", "") or "").strip()),
            bool(str(getattr(args, "fallback_model_name", "") or "").strip()),
            bool(
                str(
                    getattr(
                        args,
                        "audit_fallback_model_name",
                        "",
                    )
                    or ""
                ).strip()
            ),
            getattr(args, "temperature", None) is not None,
            bool(getattr(args, "fast", False)),
            bool(getattr(args, "force", False)),
            bool(getattr(args, "infer", False)),
            bool(str(getattr(args, "chapter", "") or "").strip()),
            bool(getattr(args, "materialize_research", False)),
            bool(getattr(args, "research_base", None)),
            bool(getattr(args, "overwrite_research", False)),
        )
    ):
        return (
            "configuration operator rollback forbids model overrides, "
            "fallbacks, temperature overrides, partial write modes, "
            "and research materialization"
        )
    if challenger_config_application_receipt_input and not preflight_only:
        return "--challenger-config-application-receipt-input requires --preflight-only"
    if challenger_config_rollback_receipt_input and not preflight_only:
        return "--challenger-config-rollback-receipt-input requires --preflight-only"
    if (
        challenger_config_rollback_read_only_requested
        and not challenger_config_application_receipt_input
        and not challenger_config_rollback_receipt_input
    ):
        return "operator rollback plan and approval operations require --challenger-config-application-receipt-input"
    if challenger_config_rollback_plan_input and challenger_config_rollback_plan_output:
        return (
            "--challenger-config-rollback-plan-input cannot be combined with --challenger-config-rollback-plan-output"
        )
    if challenger_config_rollback_approval_request != challenger_config_rollback_approval_output:
        return (
            "--challenger-config-rollback-approval-request and "
            "--challenger-config-rollback-approval-output must be "
            "provided together"
        )
    if challenger_config_rollback_plan_output and (
        challenger_config_rollback_approval_issuance or challenger_config_rollback_approval_input
    ):
        return "rollback plan export cannot be combined with rollback approval issuance or verification"
    if (
        challenger_config_rollback_approval_issuance or challenger_config_rollback_approval_input
    ) and not challenger_config_rollback_plan_input:
        return "rollback approval issuance and verification require --challenger-config-rollback-plan-input"
    if challenger_config_rollback_approval_input and challenger_config_rollback_approval_issuance:
        return "--challenger-config-rollback-approval-input cannot be combined with rollback approval issuance"
    if challenger_config_application_receipt_input and (
        challenger_config_application_requested
        or challenger_config_rollback_receipt_input
        or write_routing_snapshot_output
        or challenger_config_preapplication_requested
        or challenger_config_change_approval_input
        or challenger_config_change_summary_requested
        or challenger_requested
        or routing_preflight_approval_requested
        or routing_preflight_approval_input
        or routing_challenger_run_approval_issuance
        or routing_challenger_run_approval_input
        or routing_history_root
        or routing_proposal_input
        or routing_proposal_output
    ):
        return "configuration application receipt verification is a dedicated read-only preflight mode"
    if challenger_config_application_receipt_input and any(
        (
            bool(str(getattr(args, "model_name", "") or "").strip()),
            bool(str(getattr(args, "audit_model_name", "") or "").strip()),
            bool(str(getattr(args, "fallback_model_name", "") or "").strip()),
            bool(
                str(
                    getattr(
                        args,
                        "audit_fallback_model_name",
                        "",
                    )
                    or ""
                ).strip()
            ),
            getattr(args, "temperature", None) is not None,
            bool(getattr(args, "fast", False)),
            bool(getattr(args, "force", False)),
            bool(getattr(args, "infer", False)),
            bool(str(getattr(args, "chapter", "") or "").strip()),
            bool(getattr(args, "materialize_research", False)),
            bool(getattr(args, "research_base", None)),
            bool(getattr(args, "overwrite_research", False)),
        )
    ):
        return (
            "configuration application receipt verification forbids "
            "routing overrides, partial write modes, and research "
            "materialization"
        )
    if challenger_config_rollback_receipt_input and (
        summary
        or challenger_config_application_requested
        or challenger_config_application_receipt_input
        or challenger_config_rollback_plan_input
        or challenger_config_rollback_approval_request
        or challenger_config_rollback_approval_output
        or challenger_config_rollback_approval_input
        or challenger_config_rollback_application_requested
        or write_routing_snapshot_output
        or challenger_config_preapplication_requested
        or challenger_config_change_summary_requested
        or challenger_config_change_approval_input
        or challenger_promotion_proposal_input
        or challenger_promotion_proposal_output
        or routing_preflight_approval_requested
        or routing_preflight_approval_input
        or routing_challenger_run_approval_issuance
        or routing_challenger_run_approval_input
        or routing_history_root
        or routing_proposal_input
        or routing_proposal_output
    ):
        return "configuration operator rollback receipt verification is a dedicated read-only preflight mode"
    if challenger_config_rollback_receipt_input and any(
        (
            bool(str(getattr(args, "model_name", "") or "").strip()),
            bool(str(getattr(args, "audit_model_name", "") or "").strip()),
            bool(str(getattr(args, "fallback_model_name", "") or "").strip()),
            bool(
                str(
                    getattr(
                        args,
                        "audit_fallback_model_name",
                        "",
                    )
                    or ""
                ).strip()
            ),
            getattr(args, "temperature", None) is not None,
            bool(getattr(args, "fast", False)),
            bool(getattr(args, "force", False)),
            bool(getattr(args, "infer", False)),
            bool(str(getattr(args, "chapter", "") or "").strip()),
            bool(getattr(args, "materialize_research", False)),
            bool(getattr(args, "research_base", None)),
            bool(getattr(args, "overwrite_research", False)),
        )
    ):
        return (
            "configuration operator rollback receipt verification "
            "forbids routing overrides, partial write modes, and "
            "research materialization"
        )
    if (write_routing_snapshot_output or challenger_config_preapplication_requested) and not preflight_only:
        return "write routing snapshots and configuration pre-application plans require --preflight-only"
    if challenger_config_preapplication_plan_input and challenger_config_preapplication_plan_output:
        return (
            "--challenger-config-preapplication-plan-input cannot be "
            "combined with --challenger-config-preapplication-plan-output"
        )
    if challenger_config_preapplication_plan_output and not write_routing_snapshot_output:
        return "--challenger-config-preapplication-plan-output requires --write-routing-snapshot-output"
    if challenger_config_preapplication_requested and not challenger_config_change_approval_input:
        return "configuration pre-application plan operations require --challenger-config-change-approval-input"
    if challenger_config_preapplication_requested and challenger_requested:
        return "configuration pre-application plan operations cannot be combined with Challenger run overrides"
    if routing_preflight_approval_input and routing_preflight_approval_requested:
        return "--routing-preflight-approval-input 不能与审批凭据签发参数同时使用"
    if routing_challenger_run_approval_request != routing_challenger_run_approval_output:
        return "--routing-challenger-run-approval-request 与 --routing-challenger-run-approval-output 必须同时提供"
    if routing_challenger_run_approval_input and routing_challenger_run_approval_issuance:
        return "--routing-challenger-run-approval-input 不能与双跑计划或授权签发参数同时使用"
    if routing_challenger_run_approval_input and routing_preflight_approval_input:
        return "完整双跑授权不能与共同 preflight 审批输入同时使用"
    if routing_preflight_approval_input and not preflight_only:
        return "--routing-preflight-approval-input 需要与 --preflight-only 同时使用"
    if routing_preflight_approval_input and not challenger_requested:
        return "--routing-preflight-approval-input 需要至少一个 Challenger 模型覆盖参数"
    if routing_challenger_run_approval_issuance and not preflight_only:
        return "双跑计划导出和授权签发需要与 --preflight-only 同时使用"
    if routing_challenger_run_approval_issuance and not routing_preflight_approval_input:
        return "双跑计划导出和授权签发需要已审批的共同 preflight"
    if routing_challenger_run_approval_input and preflight_only:
        return "--routing-challenger-run-approval-input 不能与 --preflight-only 同时使用"
    if routing_challenger_run_approval_input and not challenger_requested:
        return "--routing-challenger-run-approval-input 需要至少一个 Challenger 模型覆盖参数"
    if challenger_requested and preflight_only and not routing_preflight_approval_input:
        return "Champion/Challenger 共同 preflight 需要提供 --routing-preflight-approval-input"
    if challenger_requested and not preflight_only and not summary and not routing_challenger_run_approval_input:
        return "完整 Champion/Challenger 双跑需要提供 --routing-challenger-run-approval-input"
    routing_gate_input = routing_preflight_approval_input or routing_challenger_run_approval_input
    if routing_history_root and not summary and not routing_gate_input:
        return "--routing-history-root 需要与 --summary 或 Challenger 审批门禁同时使用"
    if routing_proposal_input and not summary and not routing_gate_input:
        return "--routing-proposal-input 需要与 --summary 或 Challenger 审批门禁同时使用"
    if routing_proposal_input and not routing_history_root:
        return "--routing-proposal-input 需要同时提供 --routing-history-root"
    if routing_proposal_output and not summary:
        return "--routing-proposal-output 需要与 --summary 同时使用"
    if routing_proposal_output and not routing_history_root:
        return "--routing-proposal-output 需要同时提供 --routing-history-root"
    if routing_proposal_input and routing_proposal_output:
        return "--routing-proposal-input 不能与 --routing-proposal-output 同时使用"
    if overwrite_routing_proposal and not routing_proposal_output:
        return "--overwrite-routing-proposal 需要同时提供 --routing-proposal-output"
    if challenger_promotion_proposal_input and not summary:
        return "--challenger-promotion-proposal-input 需要与 --summary 同时使用"
    if challenger_promotion_proposal_output and not summary:
        return "--challenger-promotion-proposal-output 需要与 --summary 同时使用"
    if challenger_promotion_proposal_input and challenger_promotion_proposal_output:
        return "--challenger-promotion-proposal-input 不能与 --challenger-promotion-proposal-output 同时使用"
    if challenger_config_change_summary_requested and not summary:
        return "Challenger configuration change request and approval options require --summary"
    if (
        challenger_config_change_approval_input
        and not summary
        and not (preflight_only and challenger_config_preapplication_requested)
        and not challenger_config_application_requested
    ):
        return (
            "--challenger-config-change-approval-input requires "
            "--summary, a --preflight-only pre-application plan "
            "operation, or the dedicated configuration application mode"
        )
    if challenger_config_change_request_input and challenger_config_change_request_output:
        return "--challenger-config-change-request-input cannot be used with --challenger-config-change-request-output"
    if challenger_config_change_request_output and not challenger_promotion_proposal_input:
        return "--challenger-config-change-request-output requires --challenger-promotion-proposal-input"
    if challenger_config_change_approval_request != challenger_config_change_approval_output:
        return (
            "--challenger-config-change-approval-request and "
            "--challenger-config-change-approval-output must be "
            "provided together"
        )
    if challenger_config_change_approval_issuance and not challenger_config_change_request_input:
        return "configuration change approval issuance requires --challenger-config-change-request-input"
    if challenger_config_change_approval_input and (
        challenger_config_change_request_input
        or challenger_config_change_request_output
        or challenger_config_change_approval_issuance
    ):
        return (
            "--challenger-config-change-approval-input cannot be "
            "combined with request export, request verification, or "
            "approval issuance"
        )
    if routing_preflight_approval_request != routing_preflight_approval_output:
        return "--routing-preflight-approval-request and --routing-preflight-approval-output must be provided together"
    if routing_preflight_approval_requested and not summary:
        return "--routing-preflight-approval-request requires --summary"
    if routing_preflight_approval_requested and not routing_history_root:
        return "--routing-preflight-approval-request requires --routing-history-root"
    if routing_preflight_approval_requested and not routing_proposal_input:
        return "--routing-preflight-approval-request requires --routing-proposal-input"
    if routing_preflight_approval_input and not routing_history_root:
        return "--routing-preflight-approval-input 需要同时提供 --routing-history-root"
    if routing_preflight_approval_input and not routing_proposal_input:
        return "--routing-preflight-approval-input 需要同时提供 --routing-proposal-input"
    if routing_challenger_run_approval_input and not routing_history_root:
        return "--routing-challenger-run-approval-input 需要同时提供 --routing-history-root"
    if routing_challenger_run_approval_input and not routing_proposal_input:
        return "--routing-challenger-run-approval-input 需要同时提供 --routing-proposal-input"
    if routing_preflight_approval_input and challenger_output and not routing_challenger_run_approval_issuance:
        return "审批后的共同 preflight 不允许自定义 --challenger-output"
    if routing_preflight_approval_input and bool(getattr(args, "fast", False)):
        return "审批后的共同 preflight 不允许使用 --fast"
    if routing_preflight_approval_input and bool(str(getattr(args, "chapter", "") or "").strip()):
        return "审批后的共同 preflight 不允许使用 --chapter"
    if routing_challenger_run_approval_issuance or routing_challenger_run_approval_input:
        run_plan_error = _validate_challenger_run_plan_args(args)
        if run_plan_error is not None:
            return run_plan_error
    has_related_option = bool(getattr(args, "research_base", None)) or bool(getattr(args, "overwrite_research", False))
    if preflight_only and (materialize or has_related_option):
        return "--preflight-only 不能与 research materialize 参数同时使用"
    if has_related_option and not materialize:
        return "--research-base/--overwrite-research 需要同时提供 --materialize-research"
    if not materialize:
        return None
    if not str(getattr(args, "research_template", "") or "").strip():
        return "--materialize-research 需要同时提供 --research-template"
    if bool(getattr(args, "infer", False)):
        return "--materialize-research 不能与 infer-only 的 --infer 同时使用"
    if summary:
        return "--materialize-research 不能与 --summary 同时使用"
    return None


def _materialize_research_after_write(
    args: argparse.Namespace,
    *,
    workspace_dir: Path,
    ticker: str,
    write_output_dir: Path,
) -> dict[str, object]:
    from dayu.cli.commands.research_template import materialize_research_bundle_from_write_manifest

    research_base_raw = getattr(args, "research_base", None)
    research_base = (
        Path(str(research_base_raw)).expanduser().resolve() if research_base_raw else (workspace_dir / ticker).resolve()
    )
    return materialize_research_bundle_from_write_manifest(
        write_output_dir / "manifest.json",
        workspace_root=research_base,
        overwrite=bool(getattr(args, "overwrite_research", False)),
    )


def run_write_command(args: argparse.Namespace) -> int:
    """执行写作 CLI 命令。

    Args:
        args: 解析后的命令行参数。

    Returns:
        写作命令退出码。

    Raises:
        无。
    """

    setup_loglevel(args)
    paths_config = setup_paths(args)
    Log.info(f"工作目录: {paths_config.workspace_dir}", module=MODULE)
    if paths_config.ticker:
        Log.info(f"公司股票代码: {paths_config.ticker}", module=MODULE)
        if paths_config.has_local_filings:
            Log.info("财报目录: 已检测到本地财报", module=MODULE)
        else:
            Log.info("财报目录: 无本地财报", module=MODULE)
    if not paths_config.ticker:
        error_message = (
            "write --summary 模式要求必须提供 --ticker"
            if getattr(args, "summary", False)
            else "write 模式要求必须提供 --ticker"
        )
        Log.error(error_message, module=MODULE)
        return 2
    research_materialization_error = _validate_research_materialization_args(args)
    if research_materialization_error is not None:
        Log.error(research_materialization_error, module=MODULE)
        return 2
    if bool(
        getattr(
            args,
            "audit_write_model_configuration_manual_recovery_history",
            False,
        )
    ):
        return _run_write_model_configuration_manual_recovery_audit_timeline(
            args=args,
            paths_config=paths_config,
        )
    if bool(
        getattr(
            args,
            (
                "revalidate_write_model_configuration_manual_recovery_"
                "gate_verification"
            ),
            False,
        )
    ):
        return _run_write_model_configuration_manual_recovery_gate_revalidation(
            args=args,
            paths_config=paths_config,
        )
    if bool(
        getattr(
            args,
            "verify_write_model_configuration_manual_recovery_gate",
            False,
        )
    ):
        return _run_write_model_configuration_manual_recovery_gate_verification(
            args=args,
            paths_config=paths_config,
        )
    if bool(
        getattr(
            args,
            "check_write_model_configuration_manual_recovery_gate",
            False,
        )
    ):
        return _run_write_model_configuration_manual_recovery_gate_check(
            args=args,
            paths_config=paths_config,
        )
    if bool(
        getattr(
            args,
            ("revoke_write_model_configuration_manual_recovery_clearance"),
            False,
        )
    ):
        return _run_write_model_configuration_manual_recovery_clearance_revocation(
            args=args,
            paths_config=paths_config,
        )
    if bool(
        getattr(
            args,
            ("restart_write_model_configuration_manual_recovery_after_clearance_revocation"),
            False,
        )
    ):
        return _run_write_model_configuration_manual_recovery_restart(
            args=args,
            paths_config=paths_config,
        )
    if bool(
        getattr(
            args,
            "clear_write_model_configuration_manual_recovery",
            False,
        )
    ):
        return _run_write_model_configuration_manual_recovery_clearance(
            args=args,
            paths_config=paths_config,
            execution_options=_build_execution_options(args),
        )
    if bool(
        getattr(
            args,
            "verify_write_model_configuration_manual_recovery",
            False,
        )
    ):
        return _run_write_model_configuration_manual_recovery_verification(
            args=args,
            paths_config=paths_config,
            execution_options=_build_execution_options(args),
        )
    if bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_receipt_input",
                "",
            )
            or ""
        ).strip()
    ):
        return _run_write_model_configuration_manual_recovery_evidence(
            args=args,
            paths_config=paths_config,
        )
    if bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_plan_output",
                "",
            )
            or ""
        ).strip()
    ):
        return _run_write_model_configuration_manual_recovery_plan(
            args=args,
            paths_config=paths_config,
        )
    if bool(
        str(
            getattr(
                args,
                "challenger_config_manual_recovery_approval_output",
                "",
            )
            or ""
        ).strip()
    ):
        return _run_write_model_configuration_manual_recovery_approval(
            args=args,
            paths_config=paths_config,
        )
    if bool(getattr(args, "recover_write_model_configuration", False)):
        return _run_write_model_configuration_manual_recovery_application(
            args=args,
            paths_config=paths_config,
            execution_options=_build_execution_options(args),
        )
    write_model_override_name = _resolve_write_model_override_name(args)
    execution_options = _build_execution_options(args)
    if bool(getattr(args, "apply_write_model_configuration", False)):
        return _run_write_model_configuration_application(
            args=args,
            paths_config=paths_config,
            execution_options=execution_options,
        )
    if bool(getattr(args, "rollback_write_model_configuration", False)):
        return _run_write_model_configuration_rollback(
            args=args,
            paths_config=paths_config,
            execution_options=execution_options,
        )
    if not bool(getattr(args, "summary", False)):
        recovery_gate_exit_code = _check_write_model_configuration_manual_recovery_gate(
            paths_config=paths_config,
        )
        if recovery_gate_exit_code != 0:
            return recovery_gate_exit_code
    if bool(getattr(args, "preflight_only", False)) and _challenger_requested(args):
        approval_exit_code = _verify_challenger_preflight_approval_before_host(
            args=args,
            write_model_override_name=write_model_override_name,
        )
        if approval_exit_code != 0:
            return approval_exit_code
    challenger_run_plan: dict[str, Any] | None = None
    challenger_run_plan_required = any(
        bool(str(getattr(args, attribute, "") or "").strip())
        for attribute in (
            "routing_challenger_run_plan_output",
            "routing_challenger_run_approval_request",
            "routing_challenger_run_approval_output",
            "routing_challenger_run_approval_input",
        )
    )
    if challenger_run_plan_required:
        try:
            challenger_run_plan = _build_challenger_run_plan_from_args(
                args=args,
                paths_config=paths_config,
                write_model_override_name=(write_model_override_name),
            )
            _assert_challenger_run_output_boundaries(
                plan=challenger_run_plan,
                workspace_dir=paths_config.workspace_dir,
            )
        except (
            FileExistsError,
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            Log.error(
                f"Challenger 双跑计划无效: {exc}",
                module=MODULE,
            )
            return 2
    if bool(
        str(
            getattr(
                args,
                "routing_challenger_run_approval_input",
                "",
            )
            or ""
        ).strip()
    ):
        assert challenger_run_plan is not None
        run_approval_exit_code = _verify_and_consume_challenger_run_approval_before_host(
            args=args,
            paths_config=paths_config,
            execution_plan=challenger_run_plan,
        )
        if run_approval_exit_code != 0:
            return run_approval_exit_code
    if getattr(args, "summary", False):
        output_dir = _resolve_write_output_dir(
            workspace_dir=paths_config.workspace_dir,
            ticker=paths_config.ticker,
            raw_output=getattr(args, "output", None),
        )
        raw_routing_history_root = getattr(args, "routing_history_root", None)
        routing_history_root = (
            Path(str(raw_routing_history_root)).expanduser().resolve() if raw_routing_history_root else None
        )
        raw_routing_proposal_input = getattr(
            args,
            "routing_proposal_input",
            None,
        )
        routing_proposal_input = (
            Path(str(raw_routing_proposal_input)).expanduser().resolve() if raw_routing_proposal_input else None
        )
        raw_routing_proposal_output = getattr(
            args,
            "routing_proposal_output",
            None,
        )
        routing_proposal_output = (
            Path(str(raw_routing_proposal_output)).expanduser().resolve() if raw_routing_proposal_output else None
        )
        overwrite_routing_proposal = bool(getattr(args, "overwrite_routing_proposal", False))
        raw_routing_preflight_approval_request = getattr(
            args,
            "routing_preflight_approval_request",
            None,
        )
        routing_preflight_approval_request = (
            Path(str(raw_routing_preflight_approval_request)).expanduser().resolve()
            if raw_routing_preflight_approval_request
            else None
        )
        raw_routing_preflight_approval_output = getattr(
            args,
            "routing_preflight_approval_output",
            None,
        )
        routing_preflight_approval_output = (
            Path(str(raw_routing_preflight_approval_output)).expanduser().resolve()
            if raw_routing_preflight_approval_output
            else None
        )
        raw_challenger_promotion_proposal_input = getattr(
            args,
            "challenger_promotion_proposal_input",
            None,
        )
        challenger_promotion_proposal_input = (
            Path(str(raw_challenger_promotion_proposal_input)).expanduser().resolve()
            if raw_challenger_promotion_proposal_input
            else None
        )
        raw_challenger_promotion_proposal_output = getattr(
            args,
            "challenger_promotion_proposal_output",
            None,
        )
        challenger_promotion_proposal_output = (
            Path(str(raw_challenger_promotion_proposal_output)).expanduser().resolve()
            if raw_challenger_promotion_proposal_output
            else None
        )
        raw_config_change_request_input = getattr(
            args,
            "challenger_config_change_request_input",
            None,
        )
        config_change_request_input = (
            Path(str(raw_config_change_request_input)).expanduser().resolve()
            if raw_config_change_request_input
            else None
        )
        raw_config_change_request_output = getattr(
            args,
            "challenger_config_change_request_output",
            None,
        )
        config_change_request_output = (
            Path(str(raw_config_change_request_output)).expanduser().resolve()
            if raw_config_change_request_output
            else None
        )
        raw_config_change_approval_request = getattr(
            args,
            "challenger_config_change_approval_request",
            None,
        )
        config_change_approval_request = (
            Path(str(raw_config_change_approval_request)).expanduser().resolve()
            if raw_config_change_approval_request
            else None
        )
        raw_config_change_approval_output = getattr(
            args,
            "challenger_config_change_approval_output",
            None,
        )
        config_change_approval_output = (
            Path(str(raw_config_change_approval_output)).expanduser().resolve()
            if raw_config_change_approval_output
            else None
        )
        raw_config_change_approval_input = getattr(
            args,
            "challenger_config_change_approval_input",
            None,
        )
        config_change_approval_input = (
            Path(str(raw_config_change_approval_input)).expanduser().resolve()
            if raw_config_change_approval_input
            else None
        )
        if bool(getattr(args, "reprice_costs", False)):
            try:
                config_loader = paths_config.config_loader or ConfigLoader(ConfigFileResolver(paths_config.config_root))
                model_catalog = config_loader.load_llm_models()
            except (OSError, TypeError, ValueError) as exc:
                Log.error(f"成本重估模型目录加载失败: {exc}", module=MODULE)
                return 2
            return WriteService.print_report(
                output_dir,
                model_catalog=model_catalog,
                routing_history_root=routing_history_root,
                routing_proposal_input=routing_proposal_input,
                routing_proposal_output=routing_proposal_output,
                overwrite_routing_proposal=overwrite_routing_proposal,
                routing_preflight_approval_request=(routing_preflight_approval_request),
                routing_preflight_approval_output=(routing_preflight_approval_output),
                challenger_promotion_proposal_input=(challenger_promotion_proposal_input),
                challenger_promotion_proposal_output=(challenger_promotion_proposal_output),
                challenger_config_change_request_input=(config_change_request_input),
                challenger_config_change_request_output=(config_change_request_output),
                challenger_config_change_approval_request=(config_change_approval_request),
                challenger_config_change_approval_output=(config_change_approval_output),
                challenger_config_change_approval_input=(config_change_approval_input),
            )
        return WriteService.print_report(
            output_dir,
            routing_history_root=routing_history_root,
            routing_proposal_input=routing_proposal_input,
            routing_proposal_output=routing_proposal_output,
            overwrite_routing_proposal=overwrite_routing_proposal,
            routing_preflight_approval_request=(routing_preflight_approval_request),
            routing_preflight_approval_output=(routing_preflight_approval_output),
            challenger_promotion_proposal_input=(challenger_promotion_proposal_input),
            challenger_promotion_proposal_output=(challenger_promotion_proposal_output),
            challenger_config_change_request_input=(config_change_request_input),
            challenger_config_change_request_output=(config_change_request_output),
            challenger_config_change_approval_request=(config_change_approval_request),
            challenger_config_change_approval_output=(config_change_approval_output),
            challenger_config_change_approval_input=(config_change_approval_input),
        )
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
    company_name = _resolve_write_company_name(
        ticker=paths_config.ticker,
        company_name_resolver=fins_runtime.get_company_name,
    )
    output_dir = _resolve_write_output_dir(
        workspace_dir=paths_config.workspace_dir,
        ticker=paths_config.ticker,
        raw_output=getattr(args, "output", None),
    )
    if bool(getattr(args, "preflight_only", False)):
        write_cli_config = setup_write_config(args, paths_config, running_config)
        preflight_config = _build_write_run_config(
            ticker=paths_config.ticker,
            company_name=company_name,
            write_cli_config=write_cli_config,
            write_model_override_name=write_model_override_name,
        )
        if _challenger_requested(args):
            try:
                challenger_config = _build_challenger_write_config(
                    args=args,
                    champion_config=preflight_config,
                )
            except ValueError as exc:
                Log.error(str(exc), module=MODULE)
                return 2
            preflight_exit_code = _preflight_champion_and_challenger(
                champion_config=preflight_config,
                challenger_config=challenger_config,
                write_service=service,
            )
            if preflight_exit_code != 0:
                return preflight_exit_code
            if challenger_run_plan is not None:
                return _persist_challenger_run_authorization_after_preflight(
                    args=args,
                    execution_plan=challenger_run_plan,
                )
            return 0
        return _run_write_preflight(
            write_config=preflight_config,
            write_service=service,
            config_root=paths_config.config_root,
            routing_snapshot_output=getattr(
                args,
                "write_routing_snapshot_output",
                None,
            ),
            configuration_change_approval_input=getattr(
                args,
                "challenger_config_change_approval_input",
                None,
            ),
            preapplication_plan_output=getattr(
                args,
                "challenger_config_preapplication_plan_output",
                None,
            ),
            preapplication_plan_input=getattr(
                args,
                "challenger_config_preapplication_plan_input",
                None,
            ),
            application_receipt_input=getattr(
                args,
                "challenger_config_application_receipt_input",
                None,
            ),
            rollback_plan_output=getattr(
                args,
                "challenger_config_rollback_plan_output",
                None,
            ),
            rollback_plan_input=getattr(
                args,
                "challenger_config_rollback_plan_input",
                None,
            ),
            rollback_approval_request=getattr(
                args,
                "challenger_config_rollback_approval_request",
                None,
            ),
            rollback_approval_output=getattr(
                args,
                "challenger_config_rollback_approval_output",
                None,
            ),
            rollback_approval_input=getattr(
                args,
                "challenger_config_rollback_approval_input",
                None,
            ),
            rollback_receipt_input=getattr(
                args,
                "challenger_config_rollback_receipt_input",
                None,
            ),
        )
    if _needs_auto_research_bootstrap(args, output_dir=output_dir):
        Log.info("auto 研究模板缺少本地 manifest，先执行公司级 Facet 归因", module=MODULE)
        bootstrap_cli_config = setup_write_config(
            _build_auto_bootstrap_args(args),
            paths_config,
            running_config,
        )
        bootstrap_config = _build_write_run_config(
            ticker=paths_config.ticker,
            company_name=company_name,
            write_cli_config=bootstrap_cli_config,
            write_model_override_name=write_model_override_name,
        )
        bootstrap_exit_code = _run_write_stage(write_config=bootstrap_config, write_service=service)
        if bootstrap_exit_code != 0 or bool(getattr(args, "infer", False)):
            return bootstrap_exit_code

    write_cli_config = setup_write_config(args, paths_config, running_config)
    write_config = _build_write_run_config(
        ticker=paths_config.ticker,
        company_name=company_name,
        write_cli_config=write_cli_config,
        write_model_override_name=write_model_override_name,
    )
    if _challenger_requested(args):
        if challenger_run_plan is not None:
            try:
                current_plan = _build_challenger_run_plan_from_args(
                    args=args,
                    paths_config=paths_config,
                    write_model_override_name=(write_model_override_name),
                )
            except (
                FileNotFoundError,
                OSError,
                TypeError,
                ValueError,
            ) as exc:
                Log.error(
                    f"Challenger 双跑计划复核失败: {exc}",
                    module=MODULE,
                )
                return 2
            if current_plan != challenger_run_plan:
                Log.error(
                    "Challenger 双跑计划在 Host 初始化后发生变化",
                    module=MODULE,
                )
                return 2
        try:
            challenger_config = _build_challenger_write_config(
                args=args,
                champion_config=write_config,
            )
        except ValueError as exc:
            Log.error(str(exc), module=MODULE)
            return 2
        preflight_exit_code = _preflight_champion_and_challenger(
            champion_config=write_config,
            challenger_config=challenger_config,
            write_service=service,
        )
        if preflight_exit_code != 0:
            return preflight_exit_code
        write_exit_code = _run_champion_challenger_experiment(
            champion_config=write_config,
            challenger_config=challenger_config,
            write_service=service,
        )
    else:
        write_exit_code = _run_write_stage(
            write_config=write_config,
            write_service=service,
        )
    if write_exit_code != 0 or not bool(getattr(args, "materialize_research", False)):
        return write_exit_code
    try:
        materialized = _materialize_research_after_write(
            args,
            workspace_dir=paths_config.workspace_dir,
            ticker=paths_config.ticker,
            write_output_dir=Path(write_config.output_dir),
        )
    except Exception as exc:  # noqa: BLE001 - report already written; surface materialize failure as partial success
        # materialize_research_workspace raises OSError/ValueError on normal
        # failures but RuntimeError (rollback-also-failed) / AssertionError on
        # degenerate paths. The write report is already on disk, so any
        # materialize failure is a documented partial success (exit 2), not an
        # uncaught traceback (exit 1).
        Log.error(f"研究工件 materialize 失败: {type(exc).__name__}: {exc}", module=MODULE)
        return 2
    Log.info(
        f"研究工件 materialize 完成: bundle={materialized['bundle_file']}, workbook={materialized['workbook_file']}",
        module=MODULE,
    )
    return 0
