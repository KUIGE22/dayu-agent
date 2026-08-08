"""写作 CLI 的 Challenger 运行编排。"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dayu.cli.commands._write_config_helpers import MODULE
from dayu.cli.commands._write_execution import _run_write_preflight, _run_write_stage
from dayu.cli.dependency_setup import WorkspaceConfig, _resolve_write_output_dir
from dayu.log import Log
from dayu.services.contracts import WriteRunConfig
from dayu.services.write_model_challenger_preflight_approval import (
    format_write_model_challenger_preflight_verification_report,
    load_write_model_challenger_preflight_approval,
    verify_write_model_challenger_preflight_approval,
)
from dayu.services.write_model_challenger_proposal import (
    load_write_model_challenger_proposal,
)
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
from dayu.services.write_model_health import build_write_model_health_trend
from dayu.services.write_run_comparison import (
    compare_write_run_paths,
    persist_write_run_comparison,
)
from dayu.services.write_service import WriteService

_CHALLENGER_COMPARISON_FILE = "challenger_comparison.json"


def _challenger_preflight_cli_args(
    args: argparse.Namespace,
) -> list[str]:
    """构造与审批凭据绑定的 Challenger preflight 参数列表。

    Args:
        args: 解析后的写作命令参数。

    Returns:
        以 ``--preflight-only`` 开头并包含有效模型覆盖项的规范参数列表。

    Raises:
        本函数不显式抛出异常。
    """

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
    """在 Host 初始化前验证共同 preflight 审批。

    Args:
        args: 解析后的写作命令参数。
        write_model_override_name: 当前主写作模型覆盖名称。

    Returns:
        审批允许时返回 0，审批拒绝时返回 4，凭据或输入无效时返回 2。

    Raises:
        Exception: 日志或报告格式化等未纳入退出码映射的异常会原样传播。
    """

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
    """在不初始化 Host 的情况下构造精确 Challenger 双跑计划。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        write_model_override_name: 当前主写作模型覆盖名称。

    Returns:
        可用于审批校验的完整 Challenger 双跑计划。

    Raises:
        ValueError: 未提供股票代码或参数值无法满足计划约束时抛出。
        TypeError: 参数值类型无法转换或下游计划构造器拒绝输入时抛出。
        OSError: 模板或输出路径规范化失败时抛出。
    """

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
    """要求 Champion 与 Challenger 输出均为工作区内的新路径。

    Args:
        plan: 已审批的 Challenger 双跑计划。
        workspace_dir: 允许承载输出的工作区目录。

    Returns:
        无。

    Raises:
        ValueError: 输出映射无效或任一输出位于工作区之外时抛出。
        FileExistsError: 任一批准输出路径已经存在时抛出。
        OSError: 路径规范化或存在性检查失败时抛出。
    """

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
    """加载导出的 Challenger 提案并从当前历史重建提案状态。

    Args:
        history_root: 当前路由历史根目录。
        proposal_input: 已导出的 Challenger 提案凭据路径。

    Returns:
        提案路径、提案回执与当前历史重建的提案映射。

    Raises:
        FileNotFoundError: 提案或历史输入不存在时抛出。
        OSError: 提案或历史读取失败时抛出。
        TypeError: 提案或历史载荷类型无效时抛出。
        ValueError: 当前历史无法生成有效 Challenger 提案时抛出。
    """

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
    """导出双跑计划并按需在 preflight 后签发一次运行审批。

    Args:
        args: 解析后的写作命令参数。
        execution_plan: 已通过 preflight 的 Challenger 双跑计划。

    Returns:
        导出或签发成功时返回 0，审批门禁阻断时返回 4，输入或文件错误返回 2。

    Raises:
        Exception: 日志或报告格式化等未纳入退出码映射的异常会原样传播。
    """

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
    """在 Host 初始化前验证并原子消费一次完整双跑审批。

    Args:
        args: 解析后的写作命令参数。
        paths_config: 写作工作区与配置路径。
        execution_plan: 本次实际 Challenger 双跑计划。

    Returns:
        审批验证并消费成功时返回 0，拒绝或已消费时返回 4，输入或文件错误返回 2。

    Raises:
        Exception: 日志或报告格式化等未纳入退出码映射的异常会原样传播。
    """

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
    """从已解析的 Champion 配置构造隔离的 Challenger 配置。

    Args:
        args: 解析后的写作命令参数。
        champion_config: 已解析的 Champion 写作运行配置。

    Returns:
        使用独立输出与模型覆盖的 Challenger 写作运行配置。

    Raises:
        ValueError: Challenger 与 Champion 输出目录相同时抛出。
        OSError: 输出路径规范化失败时抛出。
    """

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
    """在任一写作运行创建产物前预检 Champion 与 Challenger。

    Args:
        champion_config: Champion 写作运行配置。
        challenger_config: Challenger 写作运行配置。
        write_service: 执行两次预检的写作服务。

    Returns:
        两次预检均通过时返回 0，否则返回 2。

    Raises:
        Exception: 写作服务或预检日志未处理的异常会原样传播。
    """

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
    """运行两份隔离计划并持久化确定性的对比产物。

    Args:
        champion_config: Champion 写作运行配置。
        challenger_config: Challenger 写作运行配置。
        write_service: 执行两次写作运行的写作服务。

    Returns:
        对比成功时返回 0；运行失败时返回对应退出码；摘要或对比失败时返回 2。

    Raises:
        Exception: 写作执行或日志未纳入本函数错误映射的异常会原样传播。
    """

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
    """判断清单是否包含可加载的公司画像对象。

    画像推断遇到瞬时错误时，既有写作可能持久化
    ``company_facets: null``。自动研究模板必须依据画像内容是否可用决定是否
    重新引导，不能只依据清单文件是否存在。

    Args:
        manifest_path: 待检查的写作清单路径。

    Returns:
        清单存在且公司画像可加载时返回 ``True``，否则返回 ``False``。

    Raises:
        ImportError: 公司画像加载依赖不可用时抛出。
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
    """判断自动研究模板是否需要先执行画像引导写作。

    Args:
        args: 解析后的写作命令参数。
        output_dir: 当前 Champion 输出目录。

    Returns:
        请求自动模板且现有清单没有可用公司画像时返回 ``True``。

    Raises:
        ImportError: 公司画像加载依赖不可用时抛出。
    """

    requested = str(getattr(args, "research_template", "") or "").strip().lower()
    if requested != "auto":
        return False
    return not _manifest_has_usable_company_facets(output_dir / "manifest.json")


def _build_auto_bootstrap_args(args: argparse.Namespace) -> argparse.Namespace:
    """构造自动研究模板画像引导阶段使用的命令参数。

    Args:
        args: 原始写作命令参数。

    Returns:
        关闭模板物化并启用画像推断的新参数命名空间。

    Raises:
        TypeError: 输入不是可由 ``vars`` 读取的参数命名空间时抛出。
    """

    values = dict(vars(args))
    values.update({"template": None, "research_template": None, "infer": True})
    return argparse.Namespace(**values)
