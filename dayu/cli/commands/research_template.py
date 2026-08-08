"""提供 ``research-template`` CLI 入口与 39 个命令 runner。"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from dayu.cli.arguments import DayuCliArguments, ResearchTemplateDispatchArguments
from dayu.cli.commands._research_template_bundle import (
    build_research_template_bundle_rebind_preview,
    build_research_template_bundle_rebind_rollback_preview,
    discover_research_template_bundles,
    inspect_research_template_bundle,
    write_research_template_bundle_rebind,
    write_research_template_bundle_rebind_rollback,
)
from dayu.cli.commands._research_template_core import (
    build_monitoring_rules_payload,
    build_monitoring_source_binding_preview,
    build_monitoring_source_binding_rollback_preview,
    build_monitoring_source_map_payload,
    build_research_template_package_manifest,
    compose_research_template,
    copy_research_template,
    inspect_monitoring_source_binding_history,
    list_research_templates,
    load_research_template,
    materialize_research_checklist,
    recommend_research_templates,
    validate_monitoring_source_map_payload,
    write_monitoring_rules_payload,
    write_monitoring_source_binding_approval,
    write_monitoring_source_binding_rollback,
    write_monitoring_source_map_payload,
    write_research_template_package_manifest,
)
from dayu.cli.commands._research_template_helpers import (
    _company_facets_from_args,
    _load_json_object,
    _load_workbook_evidence_records,
    _print_definition_header,
    _recommendation_payload,
    _resolve_materialize_research_target,
)
from dayu.cli.commands._research_template_materialize import (
    _resolve_materialize_template_selection,
    build_research_portfolio_preview,
    build_research_workspace_refresh_preview,
    materialize_research_portfolio,
    materialize_research_workspace,
    write_research_workspace_refresh,
)
from dayu.cli.commands._research_template_monitoring import (
    build_monitoring_execution_plan,
    build_monitoring_scheduler_manifest,
    build_monitoring_status_snapshot,
    discover_monitoring_execution_plans,
    inspect_monitoring_execution_plan,
    inspect_monitoring_scheduler_manifest,
    write_monitoring_execution_plan,
    write_monitoring_scheduler_manifest,
    write_monitoring_status_snapshot,
)
from dayu.cli.commands.research_workbook import (
    build_research_workbook_payload,
    build_research_workbook_report,
    build_research_workbook_report_status_snapshot,
    build_research_workbook_rollback_preview,
    build_research_workbook_status_snapshot,
    build_research_workbook_update_preview,
    discover_research_workbook_reports,
    discover_research_workbooks,
    inspect_research_workbook,
    inspect_research_workbook_report,
    validate_research_workbook_payload,
    write_research_workbook_payload,
    write_research_workbook_report,
    write_research_workbook_report_status_snapshot,
    write_research_workbook_rollback,
    write_research_workbook_status_snapshot,
    write_research_workbook_update,
)
from dayu.cli.dependency_setup import setup_loglevel
from dayu.cli.research_template_checklist import (
    build_research_checklist_payload,
    render_research_checklist_markdown,
)
from dayu.cli.research_template_definitions import (
    definition_to_payload,
    evidence_to_payload,
    load_research_template_definition,
    scorecard_to_payload,
)


def _resolve_research_template_action(
    args: ResearchTemplateDispatchArguments,
) -> str:
    """规范化 research-template action 并保留入口的防御性语义。

    Args:
        args: 提供 research-template action 的类型化参数对象。

    Returns:
        去除首尾空白并转为小写的 action；缺字段或空值返回空字符串。

    Raises:
        本函数不显式抛出异常。
    """

    return str(getattr(args, "research_template_action", "") or "").strip().lower()


def run_research_template_command(args: DayuCliArguments) -> int:
    """分派 research-template 子命令并保持既有错误边界。

    Args:
        args: 已由 argparse 解析的 CLI 参数。

    Returns:
        runner 的退出码；未知 action 或已知输入、文件异常返回 1。

    Raises:
        Exception: runner 抛出的非文件存在性或输入校验异常会原样传播。
    """

    setup_loglevel(args)
    action = _resolve_research_template_action(args)
    try:
        runner = _RESEARCH_TEMPLATE_ACTION_DISPATCH.get(action)
        if runner is None:
            return 1
        return runner(args)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"research-template error: {exc}", file=sys.stderr)
        return 1


def _run_list(args: DayuCliArguments) -> int:
    """列出内置研究模板，并按参数选择文本或 JSON 输出。

    Args:
        args: 包含 JSON 输出开关的 CLI 参数。

    Returns:
        模板列表成功输出时返回 0。

    Raises:
        Exception: 模板发现或标准输出失败时由底层流程传播。
    """

    templates = list_research_templates()
    if bool(getattr(args, "json", False)):
        payload = [{"name": template.name, "title": template.title} for template in templates]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for template in templates:
        print(f"{template.name}\t{template.title}")
    return 0


def _run_show(args: DayuCliArguments) -> int:
    """读取并打印指定研究模板的原始内容。

    Args:
        args: 包含模板名称的 CLI 参数。

    Returns:
        模板内容成功输出时返回 0。

    Raises:
        FileNotFoundError: 指定模板不存在时由加载流程传播。
        ValueError: 模板名称无效时由加载流程传播。
    """

    print(load_research_template(str(getattr(args, "name"))))
    return 0


def _run_scorecard(args: DayuCliArguments) -> int:
    """打印指定研究模板的评分卡定义。

    Args:
        args: 包含模板名称与 JSON 输出开关的 CLI 参数。

    Returns:
        评分卡成功输出时返回 0。

    Raises:
        FileNotFoundError: 模板定义不存在时由加载流程传播。
        ValueError: 模板定义无效时由加载流程传播。
    """

    definition = load_research_template_definition(str(getattr(args, "name")))
    if bool(getattr(args, "json", False)):
        print(json.dumps(scorecard_to_payload(definition), ensure_ascii=False, indent=2))
        return 0
    _print_definition_header(definition)
    print("## 评分卡")
    for dimension in definition.scorecard:
        print(f"- [{dimension.weight}] {dimension.key}\t{dimension.title}: {dimension.description}")
    return 0


def _run_evidence(args: DayuCliArguments) -> int:
    """打印指定研究模板的证据要求定义。

    Args:
        args: 包含模板名称与 JSON 输出开关的 CLI 参数。

    Returns:
        证据要求成功输出时返回 0。

    Raises:
        FileNotFoundError: 模板定义不存在时由加载流程传播。
        ValueError: 模板定义无效时由加载流程传播。
    """

    definition = load_research_template_definition(str(getattr(args, "name")))
    if bool(getattr(args, "json", False)):
        print(json.dumps(evidence_to_payload(definition), ensure_ascii=False, indent=2))
        return 0
    _print_definition_header(definition)
    print("## 证据要求")
    for requirement in definition.evidence_requirements:
        sources = ", ".join(requirement.data_sources)
        print(f"- {requirement.key}: {requirement.description} (数据源: {sources})")
    return 0


def _run_schema(args: DayuCliArguments) -> int:
    """打印指定研究模板的完整定义模式。

    Args:
        args: 包含模板名称与 JSON 输出开关的 CLI 参数。

    Returns:
        完整定义成功输出时返回 0。

    Raises:
        FileNotFoundError: 模板定义不存在时由加载流程传播。
        ValueError: 模板定义无效时由加载流程传播。
    """

    definition = load_research_template_definition(str(getattr(args, "name")))
    if bool(getattr(args, "json", False)):
        print(json.dumps(definition_to_payload(definition), ensure_ascii=False, indent=2))
        return 0
    _print_definition_header(definition)
    print("## 评分卡")
    for dimension in definition.scorecard:
        print(f"- [{dimension.weight}] {dimension.key}\t{dimension.title}: {dimension.description}")
    print("## 证据要求")
    for requirement in definition.evidence_requirements:
        sources = ", ".join(requirement.data_sources)
        print(f"- {requirement.key}: {requirement.description} (数据源: {sources})")
    print("## 否决红旗")
    for flag in definition.red_flags:
        print(f"- {flag}")
    print("## 输出结构")
    for section in definition.output_sections:
        print(f"- {section.key}\t{section.title}: {section.guidance}")
    return 0


def _run_checklist(args: DayuCliArguments) -> int:
    """预览指定研究模板的分析师检查单而不写入工作区。

    Args:
        args: 包含模板名称与 JSON 输出开关的 CLI 参数。

    Returns:
        检查单成功输出时返回 0。

    Raises:
        FileNotFoundError: 模板定义不存在时由加载流程传播。
        ValueError: 模板定义无效时由加载流程传播。
    """

    definition = load_research_template_definition(str(getattr(args, "name")))
    if bool(getattr(args, "json", False)):
        print(json.dumps(build_research_checklist_payload(definition), ensure_ascii=False, indent=2))
        return 0
    print(render_research_checklist_markdown(definition), end="")
    return 0


def _run_materialize_checklist(args: DayuCliArguments) -> int:
    """把指定研究模板的检查单物化为工作区 Markdown 文件。

    Args:
        args: 包含模板、工作区、输出路径及覆盖策略的 CLI 参数。

    Returns:
        检查单成功物化并报告路径时返回 0。

    Raises:
        FileNotFoundError: 模板定义不存在时由物化流程传播。
        FileExistsError: 目标已存在且未允许覆盖时由物化流程传播。
        OSError: 检查单文件无法写入时由物化流程传播。
        ValueError: 模板或输出参数无效时由物化流程传播。
    """

    output_raw = getattr(args, "output", None)
    checklist_path = materialize_research_checklist(
        str(getattr(args, "name")),
        workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
        output_path=Path(str(output_raw)).resolve() if output_raw else None,
        overwrite=bool(getattr(args, "overwrite", False)),
    )
    if bool(getattr(args, "json", False)):
        print(json.dumps({"checklist_file": str(checklist_path)}, ensure_ascii=False, indent=2))
    else:
        print(f"checklist_file: {checklist_path}")
    return 0


def _run_copy(args: DayuCliArguments) -> int:
    """把指定研究模板复制到工作区并报告目标路径。

    Args:
        args: 包含模板、工作区、输出路径及覆盖策略的 CLI 参数。

    Returns:
        模板成功复制并报告路径时返回 0。

    Raises:
        FileNotFoundError: 源模板不存在时由复制流程传播。
        FileExistsError: 目标已存在且未允许覆盖时由复制流程传播。
        OSError: 模板文件无法读取或写入时由复制流程传播。
        ValueError: 模板或目标路径无效时由复制流程传播。
    """

    output_raw = getattr(args, "output", None)
    copied_path = copy_research_template(
        str(getattr(args, "name")),
        workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
        output_path=Path(str(output_raw)).resolve() if output_raw else None,
        overwrite=bool(getattr(args, "overwrite", False)),
    )
    if bool(getattr(args, "json", False)):
        print(json.dumps({"template_file": str(copied_path)}, ensure_ascii=False, indent=2))
    else:
        print(f"template_file: {copied_path}")
    return 0


def _run_recommend(args: DayuCliArguments) -> int:
    """依据公司特征推荐研究模板并输出排序结果。

    Args:
        args: 包含公司特征、数量限制与 JSON 输出开关的 CLI 参数。

    Returns:
        推荐结果成功输出时返回 0。

    Raises:
        ValueError: 公司特征或推荐数量参数无效时由推荐流程传播。
        Exception: 模板目录读取或标准输出失败时由底层流程传播。
    """

    company_facets = _company_facets_from_args(args)
    recommendations = recommend_research_templates(
        company_facets,
        limit=int(getattr(args, "limit", 3)),
    )
    if bool(getattr(args, "json", False)):
        payload = [_recommendation_payload(recommendation) for recommendation in recommendations]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for recommendation in recommendations:
        matched = ", ".join(recommendation.matched_facets) if recommendation.matched_facets else "-"
        print(f"{recommendation.name}\tscore={recommendation.score}\tmatched={matched}\t{recommendation.title}")
    return 0


def _run_compose(args: DayuCliArguments) -> int:
    """组合指定研究模板并把结果写入工作区。

    Args:
        args: 包含模板、工作区、输出路径及覆盖策略的 CLI 参数。

    Returns:
        组合模板成功写入并报告路径时返回 0。

    Raises:
        FileNotFoundError: 组成模板所需资产不存在时由组合流程传播。
        FileExistsError: 目标已存在且未允许覆盖时由组合流程传播。
        OSError: 模板资产无法读取或结果无法写入时由组合流程传播。
        ValueError: 模板定义或输出参数无效时由组合流程传播。
    """

    output_raw = getattr(args, "output", None)
    composed_path = compose_research_template(
        str(getattr(args, "name")),
        workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
        output_path=Path(str(output_raw)).resolve() if output_raw else None,
        overwrite=bool(getattr(args, "overwrite", False)),
    )
    if bool(getattr(args, "json", False)):
        print(json.dumps({"template_file": str(composed_path)}, ensure_ascii=False, indent=2))
    else:
        print(f"template_file: {composed_path}")
    return 0


def _run_monitoring_rules(args: DayuCliArguments) -> int:
    """预览或写入指定模板的监控规则 JSON。

    Args:
        args: 包含模板、工作区、输出路径、写入与覆盖选项的 CLI 参数。

    Returns:
        规则成功预览或写入时返回 0。

    Raises:
        FileNotFoundError: 模板定义不存在时由规则构建流程传播。
        FileExistsError: 规则文件已存在且未允许覆盖时由写入流程传播。
        OSError: 规则文件无法写入时由底层流程传播。
        ValueError: 模板定义或输出参数无效时由底层流程传播。
    """

    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        rules_path = write_monitoring_rules_payload(
            str(getattr(args, "name")),
            workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        print(json.dumps({"rules_file": str(rules_path)}, ensure_ascii=False, indent=2))
        return 0
    payload = build_monitoring_rules_payload(str(getattr(args, "name")))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_research_workbook(args: DayuCliArguments) -> int:
    """预览或写入指定研究目标的工作簿 JSON。

    Args:
        args: 包含模板、研究目标、工作区及写入选项的 CLI 参数。

    Returns:
        工作簿成功预览或写入时返回 0。

    Raises:
        FileNotFoundError: 模板定义不存在时由工作簿构建流程传播。
        FileExistsError: 目标已存在且未允许覆盖时由写入流程传播。
        OSError: 工作簿文件无法写入时由底层流程传播。
        ValueError: 模板或研究目标无效时由底层流程传播。
    """

    name = str(getattr(args, "name"))
    ticker = str(getattr(args, "ticker", "") or "")
    company = str(getattr(args, "company", "") or "")
    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        workbook_path = write_research_workbook_payload(
            name,
            workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
            ticker=ticker,
            company=company,
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        print(json.dumps({"workbook_file": str(workbook_path)}, ensure_ascii=False, indent=2))
        return 0
    payload = build_research_workbook_payload(name, ticker=ticker, company=company)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_validate_research_workbook(args: DayuCliArguments) -> int:
    """校验研究工作簿并输出结构化验证结果。

    Args:
        args: 包含工作簿路径的 CLI 参数。

    Returns:
        验证通过返回 0，否则返回 1。

    Raises:
        FileNotFoundError: 工作簿文件不存在时由加载流程传播。
        OSError: 工作簿文件无法读取时由加载流程传播。
        ValueError: JSON 或工作簿结构无效时由校验流程传播。
    """

    workbook_path = Path(str(getattr(args, "workbook"))).resolve()
    result = validate_research_workbook_payload(_load_json_object(workbook_path))
    print(json.dumps({"workbook_file": str(workbook_path), "validation": result}, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") is True else 1


def _run_update_research_workbook(args: DayuCliArguments) -> int:
    """预览或执行研究工作簿条目更新。

    Args:
        args: 包含工作簿、条目更新字段、证据文件及写入开关的 CLI 参数。

    Returns:
        更新预览或写入成功时返回 0。

    Raises:
        FileNotFoundError: 工作簿或证据文件不存在时由加载流程传播。
        OSError: 工作簿或证据文件无法读写时由底层流程传播。
        ValueError: JSON、条目标识或更新内容无效时由底层流程传播。
    """

    workbook_path = Path(str(getattr(args, "workbook"))).resolve()
    evidence_raw = getattr(args, "evidence_file", None)
    evidence_records = _load_workbook_evidence_records(Path(str(evidence_raw)).resolve()) if evidence_raw else None
    update_kwargs = {
        "item_id": str(getattr(args, "item_id")),
        "status": getattr(args, "status", None),
        "response": getattr(args, "response", None),
        "analyst_notes": getattr(args, "analyst_notes", None),
        "evidence_records": evidence_records,
    }
    if bool(getattr(args, "write", False)):
        result = write_research_workbook_update(workbook_path, **update_kwargs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    preview = build_research_workbook_update_preview(
        _load_json_object(workbook_path),
        **update_kwargs,
    )
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


def _run_rollback_research_workbook(args: DayuCliArguments) -> int:
    """预览或执行研究工作簿备份回滚。

    Args:
        args: 包含工作簿、备份路径与写入开关的 CLI 参数。

    Returns:
        回滚预览或执行成功时返回 0。

    Raises:
        FileNotFoundError: 工作簿或备份文件不存在时由回滚流程传播。
        OSError: 工作簿或备份文件无法读写时由底层流程传播。
        ValueError: 工作簿或备份内容无效时由回滚流程传播。
    """

    workbook_path = Path(str(getattr(args, "workbook"))).resolve()
    backup_path = Path(str(getattr(args, "backup"))).resolve()
    if bool(getattr(args, "write", False)):
        result = write_research_workbook_rollback(workbook_path, backup_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    preview = build_research_workbook_rollback_preview(workbook_path, backup_path)
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


def _run_source_map(args: DayuCliArguments) -> int:
    """预览或写入指定模板的监控数据源映射。

    Args:
        args: 包含模板、工作区、输出路径、写入与覆盖选项的 CLI 参数。

    Returns:
        数据源映射成功预览或写入时返回 0。

    Raises:
        FileNotFoundError: 模板定义不存在时由映射构建流程传播。
        FileExistsError: 目标已存在且未允许覆盖时由写入流程传播。
        OSError: 映射文件无法写入时由底层流程传播。
        ValueError: 模板定义或输出参数无效时由底层流程传播。
    """

    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        source_map_path = write_monitoring_source_map_payload(
            str(getattr(args, "name")),
            workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        print(json.dumps({"source_map_file": str(source_map_path)}, ensure_ascii=False, indent=2))
        return 0
    payload = build_monitoring_source_map_payload(str(getattr(args, "name")))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_validate_source_map(args: DayuCliArguments) -> int:
    """校验监控规则与数据源映射的绑定关系。

    Args:
        args: 包含监控规则和数据源映射路径的 CLI 参数。

    Returns:
        校验成功时返回 0，校验失败时返回 1。

    Raises:
        FileNotFoundError: 规则或映射文件不存在时由加载流程传播。
        OSError: 规则或映射文件无法读取时由加载流程传播。
        ValueError: JSON 或绑定关系无效时由校验流程传播。
    """

    rules_payload = _load_json_object(Path(str(getattr(args, "rules"))).resolve())
    source_map_payload = _load_json_object(Path(str(getattr(args, "source_map"))).resolve())
    result = validate_monitoring_source_map_payload(rules_payload, source_map_payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") is True else 1


def _run_package_manifest(args: DayuCliArguments) -> int:
    """预览或写入内置研究模板资产清单。

    Args:
        args: 包含工作区、输出路径、写入与覆盖选项的 CLI 参数。

    Returns:
        资产清单成功预览或写入时返回 0。

    Raises:
        FileExistsError: 目标已存在且未允许覆盖时由写入流程传播。
        OSError: 模板资产无法读取或清单无法写入时由底层流程传播。
        ValueError: 模板资产或输出参数无效时由底层流程传播。
    """

    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        manifest_path = write_research_template_package_manifest(
            workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        print(json.dumps({"manifest_file": str(manifest_path)}, ensure_ascii=False, indent=2))
        return 0
    payload = build_research_template_package_manifest()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_materialize(args: DayuCliArguments) -> int:
    """解析模板与研究目标并物化完整研究工作区。

    Args:
        args: 包含模板选择、manifest、研究目标、工作区与覆盖选项的 CLI 参数。

    Returns:
        工作区成功物化并输出结果时返回 0。

    Raises:
        FileNotFoundError: 模板或 manifest 不存在时由物化流程传播。
        FileExistsError: 目标产物已存在且未允许覆盖时由物化流程传播。
        OSError: 模板资产或工作区产物无法读写时由底层流程传播。
        ValueError: 模板选择、manifest 或研究目标无效时由物化流程传播。
    """

    template_name, selection_payload = _resolve_materialize_template_selection(
        getattr(args, "name", None),
        getattr(args, "manifest", None),
    )
    research_target = _resolve_materialize_research_target(
        ticker_raw=getattr(args, "ticker", None),
        company_raw=getattr(args, "company", None),
        manifest_raw=getattr(args, "manifest", None),
    )
    payload = materialize_research_workspace(
        template_name,
        workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
        ticker=research_target["ticker"],
        company=research_target["company"],
        write_manifest_path=(
            Path(str(getattr(args, "manifest"))).resolve()
            if getattr(args, "manifest", None) and selection_payload.get("selection_mode") != "explicit"
            else None
        ),
        overwrite=bool(getattr(args, "overwrite", False)),
    )
    payload["selection"] = selection_payload
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_refresh_workspace(args: DayuCliArguments) -> int:
    """预览或执行研究工作区刷新。

    Args:
        args: 包含 bundle 路径与写入开关的 CLI 参数。

    Returns:
        写入刷新成功返回 0；预览可刷新返回 0，否则返回 1。

    Raises:
        FileNotFoundError: bundle 或其资产不存在时由刷新流程传播。
        OSError: bundle 或工作区文件无法读写时由底层流程传播。
        ValueError: bundle 描述或刷新状态无效时由底层流程传播。
    """

    bundle_path = Path(str(getattr(args, "bundle"))).resolve()
    if bool(getattr(args, "write", False)):
        result = write_research_workspace_refresh(bundle_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    preview = build_research_workspace_refresh_preview(bundle_path)
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0 if preview.get("can_refresh") is True else 1


def _run_list_bundles(args: DayuCliArguments) -> int:
    """发现研究模板 bundle 并按文本或 JSON 输出。

    Args:
        args: 包含工作区、递归与 JSON 输出选项的 CLI 参数。

    Returns:
        bundle 列表成功输出时返回 0。

    Raises:
        OSError: 工作区目录无法扫描时由发现流程传播。
        ValueError: bundle 描述无法解析时由发现流程传播。
    """

    bundles = discover_research_template_bundles(
        Path(str(getattr(args, "base", "./workspace"))).resolve(),
        recursive=bool(getattr(args, "recursive", False)),
    )
    if bool(getattr(args, "json", False)):
        print(json.dumps(bundles, ensure_ascii=False, indent=2))
        return 0
    for bundle in bundles:
        validation = bundle.get("validation")
        is_valid = isinstance(validation, dict) and validation.get("ok") is True
        template = str(bundle.get("template", "") or "<invalid>")
        research_target = bundle.get("research_target")
        ticker = str(research_target.get("ticker", "") or "-") if isinstance(research_target, dict) else "-"
        print(f"{ticker}\t{template}\t{'valid' if is_valid else 'invalid'}\t{bundle['descriptor_file']}")
    return 0


def _run_validate_bundle(args: DayuCliArguments) -> int:
    """检查研究模板 bundle 并输出验证详情。

    Args:
        args: 包含 bundle 路径的 CLI 参数。

    Returns:
        bundle 验证通过返回 0，否则返回 1。

    Raises:
        FileNotFoundError: bundle 不存在时由检查流程传播。
        OSError: bundle 文件无法读取时由检查流程传播。
        ValueError: bundle 描述无效时由检查流程传播。
    """

    result = inspect_research_template_bundle(Path(str(getattr(args, "bundle"))).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    validation = result.get("validation")
    return 0 if isinstance(validation, dict) and validation.get("ok") is True else 1


def _run_rebind_bundle(args: DayuCliArguments) -> int:
    """预览或执行研究模板 bundle 数据源重绑定。

    Args:
        args: 包含 bundle 路径与写入开关的 CLI 参数。

    Returns:
        重绑定预览或执行成功时返回 0。

    Raises:
        FileNotFoundError: bundle 或绑定资产不存在时由重绑定流程传播。
        OSError: bundle 或绑定文件无法读写时由底层流程传播。
        ValueError: bundle 或绑定关系无效时由底层流程传播。
    """

    bundle_path = Path(str(getattr(args, "bundle"))).resolve()
    result = (
        write_research_template_bundle_rebind(bundle_path)
        if bool(getattr(args, "write", False))
        else build_research_template_bundle_rebind_preview(bundle_path)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _run_rollback_bundle_rebind(args: DayuCliArguments) -> int:
    """预览或执行研究模板 bundle 重绑定回滚。

    Args:
        args: 包含 bundle、备份路径与写入开关的 CLI 参数。

    Returns:
        重绑定回滚预览或执行成功时返回 0。

    Raises:
        FileNotFoundError: bundle 或备份不存在时由回滚流程传播。
        OSError: bundle 或备份文件无法读写时由底层流程传播。
        ValueError: bundle 或备份内容无效时由回滚流程传播。
    """

    bundle_path = Path(str(getattr(args, "bundle"))).resolve()
    backup_path = Path(str(getattr(args, "backup"))).resolve()
    result = (
        write_research_template_bundle_rebind_rollback(bundle_path, backup_path)
        if bool(getattr(args, "write", False))
        else build_research_template_bundle_rebind_rollback_preview(bundle_path, backup_path)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _run_monitoring_plan(args: DayuCliArguments) -> int:
    """预览或写入 bundle 对应的监控执行计划。

    Args:
        args: 包含 bundle、输出路径、写入与覆盖选项的 CLI 参数。

    Returns:
        监控计划成功预览或写入时返回 0。

    Raises:
        FileNotFoundError: bundle 不存在时由计划构建流程传播。
        FileExistsError: 目标已存在且未允许覆盖时由写入流程传播。
        OSError: bundle 或计划文件无法读写时由底层流程传播。
        ValueError: bundle 或监控计划无效时由底层流程传播。
    """

    bundle_path = Path(str(getattr(args, "bundle"))).resolve()
    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        plan_path = write_monitoring_execution_plan(
            bundle_path,
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        payload = _load_json_object(plan_path)
        print(json.dumps({"monitoring_plan_file": str(plan_path), "plan": payload}, ensure_ascii=False, indent=2))
        return 0
    payload = build_monitoring_execution_plan(bundle_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_validate_monitoring_plan(args: DayuCliArguments) -> int:
    """检查监控执行计划并输出验证详情。

    Args:
        args: 包含监控计划路径的 CLI 参数。

    Returns:
        计划验证通过返回 0，否则返回 1。

    Raises:
        FileNotFoundError: 监控计划不存在时由检查流程传播。
        OSError: 监控计划无法读取时由检查流程传播。
        ValueError: 监控计划内容无效时由检查流程传播。
    """

    result = inspect_monitoring_execution_plan(Path(str(getattr(args, "plan"))).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    validation = result.get("validation")
    return 0 if isinstance(validation, dict) and validation.get("ok") is True else 1


def _run_list_monitoring_plans(args: DayuCliArguments) -> int:
    """发现监控执行计划并按文本或 JSON 输出。

    Args:
        args: 包含工作区、递归与 JSON 输出选项的 CLI 参数。

    Returns:
        监控计划列表成功输出时返回 0。

    Raises:
        OSError: 工作区目录无法扫描时由发现流程传播。
        ValueError: 监控计划内容无法解析时由发现流程传播。
    """

    plans = discover_monitoring_execution_plans(
        Path(str(getattr(args, "base", "./workspace"))).resolve(),
        recursive=bool(getattr(args, "recursive", False)),
    )
    if bool(getattr(args, "json", False)):
        print(json.dumps(plans, ensure_ascii=False, indent=2))
        return 0
    for plan in plans:
        validation = plan.get("validation")
        is_valid = isinstance(validation, dict) and validation.get("ok") is True
        template = str(plan.get("template", "") or "<invalid>")
        research_target = plan.get("research_target")
        ticker = str(research_target.get("ticker", "") or "-") if isinstance(research_target, dict) else "-"
        readiness = plan.get("readiness")
        status = str(readiness.get("status", "") or "unknown") if isinstance(readiness, dict) else "unknown"
        print(f"{ticker}\t{template}\t{'valid' if is_valid else 'invalid'}\t{status}\t{plan['monitoring_plan_file']}")
    return 0


def _run_monitoring_status(args: DayuCliArguments) -> int:
    """构建监控状态快照，并按需写入指定路径。

    Args:
        args: 包含工作区、递归、输出路径、写入与覆盖选项的 CLI 参数。

    Returns:
        状态快照成功预览或写入时返回 0。

    Raises:
        FileExistsError: 目标已存在且未允许覆盖时由写入流程传播。
        OSError: 工作区无法扫描或状态文件无法写入时由底层流程传播。
        ValueError: 监控资产或状态快照无效时由底层流程传播。
    """

    workspace_root = Path(str(getattr(args, "base", "./workspace"))).resolve()
    recursive = bool(getattr(args, "recursive", False))
    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        status_path = write_monitoring_status_snapshot(
            workspace_root,
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            recursive=recursive,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        payload = _load_json_object(status_path)
        print(json.dumps({"monitoring_status_file": str(status_path), "status": payload}, ensure_ascii=False, indent=2))
        return 0
    print(
        json.dumps(build_monitoring_status_snapshot(workspace_root, recursive=recursive), ensure_ascii=False, indent=2)
    )
    return 0


def _run_workbook_status(args: DayuCliArguments) -> int:
    """构建研究工作簿状态快照，并按需写入指定路径。

    Args:
        args: 包含工作区、递归、输出路径、写入与覆盖选项的 CLI 参数。

    Returns:
        工作簿状态成功预览或写入时返回 0。

    Raises:
        FileExistsError: 目标已存在且未允许覆盖时由写入流程传播。
        OSError: 工作区无法扫描或状态文件无法写入时由底层流程传播。
        ValueError: 工作簿资产或状态快照无效时由底层流程传播。
    """

    workspace_root = Path(str(getattr(args, "base", "./workspace"))).resolve()
    recursive = bool(getattr(args, "recursive", False))
    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        status_path = write_research_workbook_status_snapshot(
            workspace_root,
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            recursive=recursive,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        payload = _load_json_object(status_path)
        print(json.dumps({"workbook_status_file": str(status_path), "status": payload}, ensure_ascii=False, indent=2))
        return 0
    print(
        json.dumps(
            build_research_workbook_status_snapshot(workspace_root, recursive=recursive),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _run_workbook_report(args: DayuCliArguments) -> int:
    """预览或写入指定工作簿的 Markdown 报告。

    Args:
        args: 包含工作簿、输出路径、写入与覆盖选项的 CLI 参数。

    Returns:
        工作簿报告成功预览或写入时返回 0。

    Raises:
        FileNotFoundError: 工作簿不存在时由报告流程传播。
        FileExistsError: 目标已存在且未允许覆盖时由写入流程传播。
        OSError: 工作簿或报告文件无法读写时由底层流程传播。
        ValueError: 工作簿 JSON 或报告内容无效时由底层流程传播。
    """

    workbook_path = Path(str(getattr(args, "workbook"))).resolve()
    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        report_path = write_research_workbook_report(
            workbook_path,
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        print(json.dumps({"workbook_report_file": str(report_path)}, ensure_ascii=False, indent=2))
        return 0
    print(build_research_workbook_report(_load_json_object(workbook_path)), end="")
    return 0


def _run_validate_workbook_report(args: DayuCliArguments) -> int:
    """核验工作簿报告与来源工作簿是否一致。

    Args:
        args: 包含报告与工作簿路径的 CLI 参数。

    Returns:
        报告验证通过返回 0，否则返回 1。

    Raises:
        FileNotFoundError: 报告或工作簿不存在时由检查流程传播。
        OSError: 报告或工作簿无法读取时由检查流程传播。
        ValueError: 报告或工作簿内容无效时由检查流程传播。
    """

    result = inspect_research_workbook_report(
        Path(str(getattr(args, "report"))).resolve(),
        Path(str(getattr(args, "workbook"))).resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    validation = result.get("validation")
    return 0 if isinstance(validation, dict) and validation.get("ok") is True else 1


def _run_workbook_report_status(args: DayuCliArguments) -> int:
    """构建工作簿报告状态快照，并按需写入指定路径。

    Args:
        args: 包含工作区、递归、输出路径、写入与覆盖选项的 CLI 参数。

    Returns:
        报告状态成功预览或写入时返回 0。

    Raises:
        FileExistsError: 目标已存在且未允许覆盖时由写入流程传播。
        OSError: 工作区无法扫描或状态文件无法写入时由底层流程传播。
        ValueError: 工作簿报告或状态快照无效时由底层流程传播。
    """

    workspace_root = Path(str(getattr(args, "base", "./workspace"))).resolve()
    recursive = bool(getattr(args, "recursive", False))
    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        status_path = write_research_workbook_report_status_snapshot(
            workspace_root,
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            recursive=recursive,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        payload = _load_json_object(status_path)
        print(
            json.dumps(
                {"workbook_report_status_file": str(status_path), "status": payload},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(
        json.dumps(
            build_research_workbook_report_status_snapshot(workspace_root, recursive=recursive),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _run_materialize_portfolio(args: DayuCliArguments) -> int:
    """按研究组合清单批量物化研究工作区。

    Args:
        args: 包含组合清单、工作区与覆盖选项的 CLI 参数。

    Returns:
        全部目标物化成功返回 0；存在失败目标时返回 1。

    Raises:
        FileNotFoundError: 组合清单或模板资产不存在时由物化流程传播。
        OSError: 清单或工作区产物无法读写时由底层流程传播。
        ValueError: 组合清单或研究目标无效时由物化流程传播。
    """

    report = materialize_research_portfolio(
        Path(str(getattr(args, "portfolio"))).resolve(),
        workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
        overwrite=bool(getattr(args, "overwrite", False)),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") is True else 1


def _run_preview_portfolio(args: DayuCliArguments) -> int:
    """预览研究组合清单的批量物化结果而不写入。

    Args:
        args: 包含组合清单、工作区与覆盖选项的 CLI 参数。

    Returns:
        所有目标均可物化返回 0；存在冲突或无效目标时返回 1。

    Raises:
        FileNotFoundError: 组合清单或模板资产不存在时由预览流程传播。
        OSError: 组合清单或模板资产无法读取时由底层流程传播。
        ValueError: 组合清单或研究目标无效时由预览流程传播。
    """

    preview = build_research_portfolio_preview(
        Path(str(getattr(args, "portfolio"))).resolve(),
        workspace_root=Path(str(getattr(args, "base", "./workspace"))).resolve(),
        overwrite=bool(getattr(args, "overwrite", False)),
    )
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0 if preview.get("can_materialize") is True else 1


def _run_scheduler_manifest(args: DayuCliArguments) -> int:
    """预览或写入监控调度清单。

    Args:
        args: 包含工作区、递归、时区、输出路径与写入选项的 CLI 参数。

    Returns:
        调度清单成功预览或写入时返回 0。

    Raises:
        FileExistsError: 目标已存在且未允许覆盖时由写入流程传播。
        OSError: 工作区无法扫描或清单无法写入时由底层流程传播。
        ValueError: 时区、监控计划或调度清单无效时由底层流程传播。
    """

    workspace_root = Path(str(getattr(args, "base", "./workspace"))).resolve()
    recursive = bool(getattr(args, "recursive", False))
    timezone = str(getattr(args, "timezone", "UTC"))
    output_raw = getattr(args, "output", None)
    should_write = bool(output_raw) or bool(getattr(args, "write", False))
    if should_write:
        schedule_path = write_monitoring_scheduler_manifest(
            workspace_root,
            recursive=recursive,
            timezone=timezone,
            output_path=Path(str(output_raw)).resolve() if output_raw else None,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        payload = _load_json_object(schedule_path)
        print(
            json.dumps(
                {"scheduler_manifest_file": str(schedule_path), "manifest": payload}, ensure_ascii=False, indent=2
            )
        )
        return 0
    print(
        json.dumps(
            build_monitoring_scheduler_manifest(workspace_root, recursive=recursive, timezone=timezone),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _run_validate_scheduler_manifest(args: DayuCliArguments) -> int:
    """检查监控调度清单并输出验证详情。

    Args:
        args: 包含调度清单路径的 CLI 参数。

    Returns:
        调度清单验证通过返回 0，否则返回 1。

    Raises:
        FileNotFoundError: 调度清单不存在时由检查流程传播。
        OSError: 调度清单无法读取时由检查流程传播。
        ValueError: 调度清单内容无效时由检查流程传播。
    """

    result = inspect_monitoring_scheduler_manifest(Path(str(getattr(args, "manifest"))).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    validation = result.get("validation")
    return 0 if isinstance(validation, dict) and validation.get("ok") is True else 1


def _run_source_bindings(args: DayuCliArguments) -> int:
    """预览或批准监控数据源绑定变更。

    Args:
        args: 包含数据源映射、批准文件与写入开关的 CLI 参数。

    Returns:
        绑定预览或批准写入成功时返回 0。

    Raises:
        FileNotFoundError: 数据源映射或批准文件不存在时由绑定流程传播。
        OSError: 映射或批准文件无法读写时由底层流程传播。
        ValueError: 映射、批准或绑定关系无效时由底层流程传播。
    """

    source_map_path = Path(str(getattr(args, "source_map"))).resolve()
    approval_path = Path(str(getattr(args, "approval"))).resolve()
    if bool(getattr(args, "write", False)):
        result = write_monitoring_source_binding_approval(source_map_path, approval_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    preview = build_monitoring_source_binding_preview(
        _load_json_object(source_map_path),
        _load_json_object(approval_path),
    )
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


def _run_rollback_source_bindings(args: DayuCliArguments) -> int:
    """预览或执行监控数据源绑定回滚。

    Args:
        args: 包含数据源映射、备份文件与写入开关的 CLI 参数。

    Returns:
        绑定回滚预览或执行成功时返回 0。

    Raises:
        FileNotFoundError: 数据源映射或备份不存在时由回滚流程传播。
        OSError: 映射或备份文件无法读写时由底层流程传播。
        ValueError: 映射、备份或回滚关系无效时由底层流程传播。
    """

    source_map_path = Path(str(getattr(args, "source_map"))).resolve()
    backup_path = Path(str(getattr(args, "backup"))).resolve()
    if bool(getattr(args, "write", False)):
        result = write_monitoring_source_binding_rollback(source_map_path, backup_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    preview = build_monitoring_source_binding_rollback_preview(source_map_path, backup_path)
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


def _run_source_binding_history(args: DayuCliArguments) -> int:
    """检查数据源绑定历史并输出验证结果。

    Args:
        args: 包含数据源映射路径的 CLI 参数。

    Returns:
        绑定历史验证通过返回 0，否则返回 1。

    Raises:
        FileNotFoundError: 数据源映射或历史快照不存在时由检查流程传播。
        OSError: 映射或历史文件无法读取时由检查流程传播。
        ValueError: 映射或历史记录无效时由检查流程传播。
    """

    result = inspect_monitoring_source_binding_history(Path(str(getattr(args, "source_map"))).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    validation = result.get("validation")
    return 0 if isinstance(validation, dict) and validation.get("ok") is True else 1


_RESEARCH_TEMPLATE_ACTION_DISPATCH: Final[
    Mapping[str, Callable[[DayuCliArguments], int]]
] = {
    "list": _run_list,
    "show": _run_show,
    "scorecard": _run_scorecard,
    "evidence": _run_evidence,
    "schema": _run_schema,
    "checklist": _run_checklist,
    "materialize-checklist": _run_materialize_checklist,
    "copy": _run_copy,
    "recommend": _run_recommend,
    "compose": _run_compose,
    "monitoring-rules": _run_monitoring_rules,
    "research-workbook": _run_research_workbook,
    "validate-research-workbook": _run_validate_research_workbook,
    "update-research-workbook": _run_update_research_workbook,
    "rollback-research-workbook": _run_rollback_research_workbook,
    "source-map": _run_source_map,
    "validate-source-map": _run_validate_source_map,
    "package-manifest": _run_package_manifest,
    "materialize": _run_materialize,
    "refresh-workspace": _run_refresh_workspace,
    "list-bundles": _run_list_bundles,
    "validate-bundle": _run_validate_bundle,
    "rebind-bundle": _run_rebind_bundle,
    "rollback-bundle-rebind": _run_rollback_bundle_rebind,
    "monitoring-plan": _run_monitoring_plan,
    "validate-monitoring-plan": _run_validate_monitoring_plan,
    "list-monitoring-plans": _run_list_monitoring_plans,
    "monitoring-status": _run_monitoring_status,
    "workbook-status": _run_workbook_status,
    "workbook-report": _run_workbook_report,
    "validate-workbook-report": _run_validate_workbook_report,
    "workbook-report-status": _run_workbook_report_status,
    "materialize-portfolio": _run_materialize_portfolio,
    "preview-portfolio": _run_preview_portfolio,
    "scheduler-manifest": _run_scheduler_manifest,
    "validate-scheduler-manifest": _run_validate_scheduler_manifest,
    "source-bindings": _run_source_bindings,
    "rollback-source-bindings": _run_rollback_source_bindings,
    "source-binding-history": _run_source_binding_history,
}


__all__ = [
    "build_monitoring_execution_plan",
    "build_monitoring_status_snapshot",
    "build_monitoring_scheduler_manifest",
    "build_research_portfolio_preview",
    "build_monitoring_rules_payload",
    "build_monitoring_source_map_payload",
    "build_monitoring_source_binding_preview",
    "build_monitoring_source_binding_rollback_preview",
    "build_research_workbook_payload",
    "build_research_workbook_report",
    "build_research_workbook_report_status_snapshot",
    "build_research_workbook_status_snapshot",
    "build_research_workbook_rollback_preview",
    "build_research_workbook_update_preview",
    "build_research_template_bundle_rebind_preview",
    "build_research_template_bundle_rebind_rollback_preview",
    "build_research_template_package_manifest",
    "build_research_workspace_refresh_preview",
    "compose_research_template",
    "copy_research_template",
    "discover_research_template_bundles",
    "discover_research_workbook_reports",
    "discover_research_workbooks",
    "discover_monitoring_execution_plans",
    "inspect_monitoring_execution_plan",
    "inspect_monitoring_scheduler_manifest",
    "inspect_monitoring_source_binding_history",
    "inspect_research_template_bundle",
    "inspect_research_workbook",
    "inspect_research_workbook_report",
    "list_research_templates",
    "load_research_template",
    "materialize_research_workspace",
    "materialize_research_portfolio",
    "recommend_research_templates",
    "run_research_template_command",
    "validate_monitoring_source_map_payload",
    "validate_research_workbook_payload",
    "write_monitoring_rules_payload",
    "write_monitoring_execution_plan",
    "write_monitoring_status_snapshot",
    "write_monitoring_scheduler_manifest",
    "write_monitoring_source_map_payload",
    "write_monitoring_source_binding_approval",
    "write_monitoring_source_binding_rollback",
    "write_research_workbook_payload",
    "write_research_workbook_rollback",
    "write_research_workbook_report",
    "write_research_workbook_report_status_snapshot",
    "write_research_workbook_status_snapshot",
    "write_research_workbook_update",
    "write_research_template_package_manifest",
    "write_research_template_bundle_rebind",
    "write_research_template_bundle_rebind_rollback",
    "write_research_workspace_refresh",
]
