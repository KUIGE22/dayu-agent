"""`dayu-cli write` 命令实现。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from dayu.cli.arguments import DayuCliArguments
from dayu.cli.commands._write_challenger import (
    _assert_challenger_run_output_boundaries,
    _build_auto_bootstrap_args,
    _build_challenger_run_plan_from_args,
    _build_challenger_write_config,
    _needs_auto_research_bootstrap,
    _persist_challenger_run_authorization_after_preflight,
    _preflight_champion_and_challenger,
    _run_champion_challenger_experiment,
    _verify_and_consume_challenger_run_approval_before_host,
    _verify_challenger_preflight_approval_before_host,
)
from dayu.cli.commands._write_config_application import (
    _run_write_model_configuration_application,
)
from dayu.cli.commands._write_config_helpers import (
    MODULE,
    _build_write_run_config,
    _resolve_write_company_name,
    _resolve_write_model_override_name,
)
from dayu.cli.commands._write_config_rollback import (
    _run_write_model_configuration_rollback,
)
from dayu.cli.commands._write_dispatch import (
    _ConfigurationWriteSubcommandEntry,
    _EarlyWriteSubcommandEntry,
    _WriteCommandContext,
    _WriteConfigurationContext,
)
from dayu.cli.commands._write_execution import (
    _run_write_preflight,
    _run_write_stage,
)
from dayu.cli.commands._write_manual_recovery import (
    _check_write_model_configuration_manual_recovery_gate,
    _run_write_model_configuration_manual_recovery_application,
    _run_write_model_configuration_manual_recovery_approval,
    _run_write_model_configuration_manual_recovery_audit_timeline,
    _run_write_model_configuration_manual_recovery_clearance,
    _run_write_model_configuration_manual_recovery_clearance_revocation,
    _run_write_model_configuration_manual_recovery_evidence,
    _run_write_model_configuration_manual_recovery_gate_check,
    _run_write_model_configuration_manual_recovery_gate_revalidation,
    _run_write_model_configuration_manual_recovery_gate_verification,
    _run_write_model_configuration_manual_recovery_incident_dossier,
    _run_write_model_configuration_manual_recovery_incident_dossier_revalidation,
    _run_write_model_configuration_manual_recovery_plan,
    _run_write_model_configuration_manual_recovery_restart,
    _run_write_model_configuration_manual_recovery_verification,
)
from dayu.cli.commands._write_params_validation import (
    _challenger_requested,
    _validate_research_materialization_args,
)
from dayu.cli.dependency_setup import (
    RunningConfig,
    _build_execution_options,
    _build_write_service,
    _prepare_cli_host_dependencies,
    _resolve_write_output_dir,
    setup_loglevel,
    setup_paths,
    setup_write_config,
)
from dayu.log import Log
from dayu.services.write_service import WriteService
from dayu.startup.config_file_resolver import ConfigFileResolver
from dayu.startup.config_loader import ConfigLoader


def _run_incident_dossier_revalidation_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复事故档案重验证分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        事故档案重验证 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_incident_dossier_revalidation(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_incident_dossier_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复事故档案检查分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        事故档案检查 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_incident_dossier(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_audit_timeline_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复历史审计分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        历史审计 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_audit_timeline(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_gate_revalidation_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复门禁重验证分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        门禁重验证 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_gate_revalidation(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_gate_verification_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复门禁验证分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        门禁验证 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_gate_verification(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_gate_check_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复门禁检查分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        门禁检查 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_gate_check(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_clearance_revocation_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复许可撤销分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        许可撤销 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_clearance_revocation(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_restart_after_revocation_adapter(ctx: _WriteCommandContext) -> int:
    """执行许可撤销后的人工恢复重启分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        人工恢复重启 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_restart(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_clearance_adapter(ctx: _WriteCommandContext) -> int:
    """惰性构造执行选项并执行人工恢复许可签发分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        许可签发 runner 的退出码。

    Raises:
        Exception: 执行选项构造或底层 runner 未转换的异常原样传播。
    """

    execution_options = _build_execution_options(ctx.args)
    return _run_write_model_configuration_manual_recovery_clearance(
        args=ctx.args,
        paths_config=ctx.paths_config,
        execution_options=execution_options,
    )


def _run_verification_adapter(ctx: _WriteCommandContext) -> int:
    """惰性构造执行选项并执行人工恢复验证分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        人工恢复验证 runner 的退出码。

    Raises:
        Exception: 执行选项构造或底层 runner 未转换的异常原样传播。
    """

    execution_options = _build_execution_options(ctx.args)
    return _run_write_model_configuration_manual_recovery_verification(
        args=ctx.args,
        paths_config=ctx.paths_config,
        execution_options=execution_options,
    )


def _run_evidence_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复证据收集分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        证据收集 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_evidence(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_plan_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复计划生成分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        计划生成 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_plan(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_approval_adapter(ctx: _WriteCommandContext) -> int:
    """执行人工恢复审批生成分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        审批生成 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_manual_recovery_approval(
        args=ctx.args,
        paths_config=ctx.paths_config,
    )


def _run_recover_adapter(ctx: _WriteCommandContext) -> int:
    """惰性构造执行选项并执行人工恢复应用分支。

    Args:
        ctx: Phase A 命令上下文。

    Returns:
        人工恢复应用 runner 的退出码。

    Raises:
        Exception: 执行选项构造或底层 runner 未转换的异常原样传播。
    """

    execution_options = _build_execution_options(ctx.args)
    return _run_write_model_configuration_manual_recovery_application(
        args=ctx.args,
        paths_config=ctx.paths_config,
        execution_options=execution_options,
    )


def _run_apply_adapter(ctx: _WriteConfigurationContext) -> int:
    """复用预计算执行选项并执行配置应用分支。

    Args:
        ctx: Phase B 配置上下文。

    Returns:
        配置应用 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_application(
        args=ctx.args,
        paths_config=ctx.paths_config,
        execution_options=ctx.execution_options,
    )


def _run_rollback_adapter(ctx: _WriteConfigurationContext) -> int:
    """复用预计算执行选项并执行配置回滚分支。

    Args:
        ctx: Phase B 配置上下文。

    Returns:
        配置回滚 runner 的退出码。

    Raises:
        Exception: 底层 runner 未转换的异常原样传播。
    """

    return _run_write_model_configuration_rollback(
        args=ctx.args,
        paths_config=ctx.paths_config,
        execution_options=ctx.execution_options,
    )


_WRITE_PHASE_EARLY_RECOVERY: Final[Sequence[_EarlyWriteSubcommandEntry]] = (
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.revalidate_write_model_configuration_manual_recovery_incident_dossier
        ),
        runner=_run_incident_dossier_revalidation_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.inspect_write_model_configuration_manual_recovery_incident
        ),
        runner=_run_incident_dossier_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.audit_write_model_configuration_manual_recovery_history
        ),
        runner=_run_audit_timeline_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.revalidate_write_model_configuration_manual_recovery_gate_verification
        ),
        runner=_run_gate_revalidation_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.verify_write_model_configuration_manual_recovery_gate
        ),
        runner=_run_gate_verification_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.check_write_model_configuration_manual_recovery_gate
        ),
        runner=_run_gate_check_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.revoke_write_model_configuration_manual_recovery_clearance
        ),
        runner=_run_clearance_revocation_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.restart_write_model_configuration_manual_recovery_after_clearance_revocation
        ),
        runner=_run_restart_after_revocation_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.clear_write_model_configuration_manual_recovery
        ),
        runner=_run_clearance_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            args.verify_write_model_configuration_manual_recovery
        ),
        runner=_run_verification_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            (args.challenger_config_manual_recovery_receipt_input or "").strip()
        ),
        runner=_run_evidence_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            (args.challenger_config_manual_recovery_plan_output or "").strip()
        ),
        runner=_run_plan_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(
            (args.challenger_config_manual_recovery_approval_output or "").strip()
        ),
        runner=_run_approval_adapter,
    ),
    _EarlyWriteSubcommandEntry(
        predicate=lambda args: bool(args.recover_write_model_configuration),
        runner=_run_recover_adapter,
    ),
)


_WRITE_PHASE_CONFIGURATION: Final[Sequence[_ConfigurationWriteSubcommandEntry]] = (
    _ConfigurationWriteSubcommandEntry(
        predicate=lambda args: bool(args.apply_write_model_configuration),
        runner=_run_apply_adapter,
    ),
    _ConfigurationWriteSubcommandEntry(
        predicate=lambda args: bool(args.rollback_write_model_configuration),
        runner=_run_rollback_adapter,
    ),
)


def _materialize_research_after_write(
    args: argparse.Namespace,
    *,
    workspace_dir: Path,
    ticker: str,
    write_output_dir: Path,
) -> dict[str, object]:
    """在写作完成后延迟物化研究模板产物。

    Args:
        args: 解析后的命令行参数。
        workspace_dir: 写作工作区目录。
        ticker: 股票代码。
        write_output_dir: 写作输出目录。

    Returns:
        研究模板物化结果。

    Raises:
        OSError: 当 write manifest、模板资产或物化产物无法读写时由底层物化流程传播。
        ValueError: 当 manifest 未完成、模板选择无效或物化验证失败时由底层物化流程传播。
        FileNotFoundError: 当 manifest 或选中的模板资产不存在时由底层物化流程传播。
        FileExistsError: 当目标产物已存在且未启用覆盖时由底层物化流程传播。
        RuntimeError: 当物化失败且快照回滚也失败时由底层物化流程传播。
    """

    from dayu.cli.commands._research_template_materialize import (
        materialize_research_bundle_from_write_manifest,
    )

    research_base_raw = getattr(args, "research_base", None)
    research_base = (
        Path(str(research_base_raw)).expanduser().resolve() if research_base_raw else (workspace_dir / ticker).resolve()
    )
    return materialize_research_bundle_from_write_manifest(
        write_output_dir / "manifest.json",
        workspace_root=research_base,
        overwrite=bool(getattr(args, "overwrite_research", False)),
    )


def run_write_command(args: DayuCliArguments) -> int:
    """执行写作 CLI 命令。

    Args:
        args: 解析后的命令行参数。

    Returns:
        写作命令退出码。

    Raises:
        Exception: 未被具体命令分支转换为退出码的装配、读写或执行异常会原样传播。
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
            if args.summary
            else "write 模式要求必须提供 --ticker"
        )
        Log.error(error_message, module=MODULE)
        return 2
    research_materialization_error = _validate_research_materialization_args(args)
    if research_materialization_error is not None:
        Log.error(research_materialization_error, module=MODULE)
        return 2
    phase_a_ctx = _WriteCommandContext(args=args, paths_config=paths_config)
    for entry in _WRITE_PHASE_EARLY_RECOVERY:
        if entry.predicate(args):
            return entry.runner(phase_a_ctx)

    write_model_override_name = _resolve_write_model_override_name(args)
    execution_options = _build_execution_options(args)
    phase_b_ctx = _WriteConfigurationContext(
        args=args,
        paths_config=paths_config,
        write_model_override_name=write_model_override_name,
        execution_options=execution_options,
    )
    for entry in _WRITE_PHASE_CONFIGURATION:
        if entry.predicate(args):
            return entry.runner(phase_b_ctx)

    if not args.summary:
        recovery_gate_exit_code = _check_write_model_configuration_manual_recovery_gate(
            paths_config=paths_config,
        )
        if recovery_gate_exit_code != 0:
            return recovery_gate_exit_code
    if args.preflight_only and _challenger_requested(args):
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
    if bool((args.routing_challenger_run_approval_input or "").strip()):
        assert challenger_run_plan is not None
        run_approval_exit_code = _verify_and_consume_challenger_run_approval_before_host(
            args=args,
            paths_config=paths_config,
            execution_plan=challenger_run_plan,
        )
        if run_approval_exit_code != 0:
            return run_approval_exit_code
    if args.summary:
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
        if args.reprice_costs:
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
    if args.preflight_only:
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
            workspace_dir=paths_config.workspace_dir,
            routing_snapshot_output=getattr(
                args,
                "write_routing_snapshot_output",
                None,
            ),
            live_smoke_plan_output=getattr(
                args,
                "write_live_smoke_plan_output",
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
