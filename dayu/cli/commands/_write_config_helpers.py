"""写作 CLI 配置解析、运行契约构建与体检日志辅助函数。"""

from __future__ import annotations

import argparse
from collections.abc import Callable

from dayu.cli.dependency_setup import WriteCliConfig, setup_model_name
from dayu.log import Log
from dayu.services.contracts import WritePreflightResult, WriteRunConfig

MODULE = "APP.WRITE"


def _resolve_write_model_override_name(args: argparse.Namespace) -> str:
    """解析主写作模型覆盖名。

    Args:
        args: 解析后的命令行参数。

    Returns:
        归一化后的主写作模型覆盖名；未显式配置时返回空字符串。

    Raises:
        配置解析依赖抛出的异常会原样传播。
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
        本函数会吞掉公司名称解析依赖抛出的异常并返回空字符串。
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
    """构建单次写作流水线使用的服务配置。

    Args:
        ticker: 公司股票代码。
        company_name: 解析后的公司名称。
        write_cli_config: CLI 写作配置。
        write_model_override_name: 主写作模型覆盖名。

    Returns:
        完整的写作运行配置。

    Raises:
        配置字段不满足 WriteRunConfig 契约时传播其构造异常。
    """

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


def _log_write_preflight_result(result: WritePreflightResult, *, run_label: str = "") -> None:
    """输出写作体检结果，日志中只显示环境变量名称。

    Args:
        result: 写作运行前体检结果。
        run_label: 可选的运行标签前缀。

    Returns:
        无。

    Raises:
        日志后端抛出的异常会原样传播。
    """

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
