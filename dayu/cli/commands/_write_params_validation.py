"""写作 CLI 参数组合与 Challenger 请求校验函数。"""

from __future__ import annotations

import argparse

from dayu.services.write_model_live_smoke_plan import (
    validate_live_smoke_budget_limits,
    validate_live_smoke_chapter_name,
)


def _challenger_requested(args: argparse.Namespace) -> bool:
    """判断是否显式设置了任一 Challenger 模型覆盖参数。

    Args:
        args: 解析后的命令行参数。

    Returns:
        任一 Challenger 模型覆盖参数非空时返回 True，否则返回 False。

    Raises:
        本函数不显式抛出异常。
    """

    return bool(
        str(getattr(args, "challenger_model_name", "") or "").strip()
        or str(getattr(args, "challenger_audit_model_name", "") or "").strip()
    )


def _validate_challenger_run_plan_args(
    args: argparse.Namespace,
) -> str | None:
    """校验完整双跑计划是否显式、有界且可复现。

    Args:
        args: 解析后的命令行参数。

    Returns:
        校验通过时返回 None，否则返回稳定错误消息。

    Raises:
        本函数不显式抛出异常。
    """

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


def _validate_live_smoke_plan_args(args: argparse.Namespace) -> str | None:
    """校验 Champion 单章节冒烟计划是否有界。

    Args:
        args: 解析后的命令行参数。

    Returns:
        校验通过时返回 None，否则返回稳定错误消息。

    Raises:
        本函数不显式抛出异常。
    """

    required_options = (
        ("chapter", "--chapter"),
        ("output", "--output"),
        ("template", "--template"),
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
            return f"live smoke plan requires explicit {option_name}"
    chapter_error = validate_live_smoke_chapter_name(getattr(args, "chapter", None))
    if chapter_error is not None:
        return chapter_error
    budget_error = validate_live_smoke_budget_limits(
        maximum_model_requests=getattr(args, "write_max_model_requests", None),
        maximum_total_tokens=getattr(args, "write_max_total_tokens", None),
    )
    if budget_error is not None:
        return budget_error
    if bool(getattr(args, "resume", True)):
        return "live smoke plan requires --no-resume"
    if bool(getattr(args, "fast", False)):
        return "live smoke plan cannot use --fast; it must exercise review routing"
    if bool(getattr(args, "force", False)):
        return "live smoke plan cannot use --force"
    if bool(getattr(args, "infer", False)):
        return "live smoke plan cannot use --infer"
    if bool(getattr(args, "materialize_research", False)):
        return "live smoke plan cannot materialize research artifacts"
    if bool(getattr(args, "research_base", None)) or bool(getattr(args, "overwrite_research", False)):
        return "live smoke plan cannot use research materialization parameters"
    return None


def _validate_research_materialization_args(args: argparse.Namespace) -> str | None:
    """校验研究物化、配置操作与 Challenger 模式的参数组合。

    Args:
        args: 解析后的命令行参数。

    Returns:
        校验通过时返回 None，否则返回稳定错误消息。

    Raises:
        本函数不显式抛出异常。
    """

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
    write_live_smoke_plan_output = bool(
        str(
            getattr(
                args,
                "write_live_smoke_plan_output",
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
                ("challenger_config_manual_recovery_gate_verification_output"),
                "",
            )
            or ""
        ).strip()
    )
    revalidate_write_model_configuration_manual_recovery_gate_verification = bool(
        getattr(
            args,
            ("revalidate_write_model_configuration_manual_recovery_gate_verification"),
            False,
        )
    )
    manual_recovery_gate_verification_input = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_gate_verification_input"),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_gate_verification_revalidation_output = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_gate_verification_revalidation_output"),
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
                ("challenger_config_manual_recovery_audit_timeline_output"),
                "",
            )
            or ""
        ).strip()
    )
    inspect_write_model_configuration_manual_recovery_incident = bool(
        getattr(
            args,
            ("inspect_write_model_configuration_manual_recovery_incident"),
            False,
        )
    )
    manual_recovery_incident_transaction_id = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_incident_transaction_id"),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_incident_dossier_output = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_incident_dossier_output"),
                "",
            )
            or ""
        ).strip()
    )
    revalidate_write_model_configuration_manual_recovery_incident_dossier = bool(
        getattr(
            args,
            ("revalidate_write_model_configuration_manual_recovery_incident_dossier"),
            False,
        )
    )
    manual_recovery_incident_dossier_input = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_incident_dossier_input"),
                "",
            )
            or ""
        ).strip()
    )
    manual_recovery_incident_dossier_revalidation_output = bool(
        str(
            getattr(
                args,
                ("challenger_config_manual_recovery_incident_dossier_revalidation_output"),
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
        audit_write_model_configuration_manual_recovery_history or manual_recovery_audit_timeline_output
    )
    manual_recovery_incident_dossier_mode_requested = any(
        (
            inspect_write_model_configuration_manual_recovery_incident,
            manual_recovery_incident_transaction_id,
            manual_recovery_incident_dossier_output,
        )
    )
    manual_recovery_incident_dossier_revalidation_mode_requested = any(
        (
            revalidate_write_model_configuration_manual_recovery_incident_dossier,
            manual_recovery_incident_dossier_input,
            manual_recovery_incident_dossier_revalidation_output,
        )
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
            manual_recovery_incident_dossier_mode_requested,
            manual_recovery_incident_dossier_revalidation_mode_requested,
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
    if write_live_smoke_plan_output:
        if not preflight_only:
            return "--write-live-smoke-plan-output requires --preflight-only"
        if any(
            (
                summary,
                reprice_costs,
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
                challenger_config_preapplication_requested,
                challenger_config_application_requested,
                challenger_config_application_receipt_input,
                challenger_config_rollback_requested,
                challenger_config_rollback_receipt_input,
                challenger_config_manual_recovery_requested,
                manual_recovery_control_requested,
                challenger_config_change_summary_requested,
                routing_preflight_approval_requested,
                routing_preflight_approval_input,
                routing_challenger_run_approval_issuance,
                routing_challenger_run_approval_input,
                challenger_requested,
                challenger_output,
            )
        ):
            return (
                "live smoke plan export cannot be combined with "
                "summary, routing approvals, configuration operations, "
                "manual recovery, or Challenger operations"
            )
        live_smoke_error = _validate_live_smoke_plan_args(args)
        if live_smoke_error is not None:
            return live_smoke_error
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
                manual_recovery_incident_dossier_mode_requested,
                manual_recovery_incident_dossier_revalidation_mode_requested,
            )
        )
        if active_mode_count != 1:
            return (
                "manual recovery requires exactly one of planning, "
                "approval issuance, execution, verification, or "
                "clearance, clearance revocation, restart, or "
                "gate-check, gate-verification, or gate-verification "
                "revalidation, history-audit, incident-dossier, or "
                "incident-dossier-revalidation mode"
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
        if manual_recovery_gate_verification_mode_requested and not all(
            (
                verify_write_model_configuration_manual_recovery_gate,
                manual_recovery_gate_input,
            )
        ):
            return (
                "manual recovery gate verification requires "
                "--verify-write-model-configuration-manual-recovery-gate "
                "and --challenger-config-manual-recovery-gate-input"
            )
        if manual_recovery_gate_revalidation_mode_requested and not all(
            (
                revalidate_write_model_configuration_manual_recovery_gate_verification,
                manual_recovery_gate_verification_input,
            )
        ):
            return (
                "manual recovery gate verification revalidation "
                "requires --revalidate-write-model-configuration-"
                "manual-recovery-gate-verification and --challenger-"
                "config-manual-recovery-gate-verification-input"
            )
        if manual_recovery_history_audit_mode_requested and not audit_write_model_configuration_manual_recovery_history:
            return (
                "--challenger-config-manual-recovery-audit-timeline-"
                "output requires --audit-write-model-configuration-"
                "manual-recovery-history"
            )
        if manual_recovery_incident_dossier_mode_requested and not all(
            (
                inspect_write_model_configuration_manual_recovery_incident,
                manual_recovery_incident_transaction_id,
            )
        ):
            return (
                "manual recovery incident inspection requires "
                "--inspect-write-model-configuration-manual-recovery-"
                "incident and --challenger-config-manual-recovery-"
                "incident-transaction-id"
            )
        if manual_recovery_incident_dossier_revalidation_mode_requested and not all(
            (
                revalidate_write_model_configuration_manual_recovery_incident_dossier,
                manual_recovery_incident_dossier_input,
            )
        ):
            return (
                "manual recovery incident dossier revalidation requires "
                "--revalidate-write-model-configuration-manual-recovery-"
                "incident-dossier and --challenger-config-manual-"
                "recovery-incident-dossier-input"
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
        if manual_recovery_gate_verification_mode_requested and challenger_config_manual_recovery_plan_input:
            return (
                "manual recovery gate verification cannot be combined "
                "with manual recovery planning, approval, execution, "
                "verification, clearance, revocation, restart, or "
                "gate-check inputs"
            )
        if manual_recovery_gate_revalidation_mode_requested and challenger_config_manual_recovery_plan_input:
            return (
                "manual recovery gate verification revalidation cannot "
                "be combined with manual recovery planning, approval, "
                "execution, verification, clearance, revocation, "
                "restart, gate-check, or gate-verification inputs"
            )
        if manual_recovery_history_audit_mode_requested and challenger_config_manual_recovery_plan_input:
            return (
                "manual recovery history audit cannot be combined "
                "with manual recovery planning, approval, execution, "
                "verification, clearance, revocation, restart, "
                "gate-check, gate-verification, or revalidation inputs"
            )
        if manual_recovery_incident_dossier_mode_requested and challenger_config_manual_recovery_plan_input:
            return (
                "manual recovery incident inspection cannot be combined "
                "with manual recovery planning, approval, execution, "
                "verification, clearance, revocation, restart, "
                "gate-check, gate-verification, revalidation, or "
                "history-audit inputs"
            )
        if (
            manual_recovery_incident_dossier_revalidation_mode_requested
            and challenger_config_manual_recovery_plan_input
        ):
            return (
                "manual recovery incident dossier revalidation cannot "
                "be combined with manual recovery planning, approval, "
                "execution, verification, clearance, revocation, "
                "restart, gate-check, gate-verification, revalidation, "
                "history-audit, or incident-dossier inputs"
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
