"""提供研究模板的基础读取、路由、监控源与清单操作。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from dayu.cli.commands._research_template_helpers import (
    _COMMON_DATA_SOURCE_CANDIDATES,
    _DATA_SOURCE_BINDING_CANDIDATES,
    _FALLBACK_TEMPLATE_NAME,
    _TEMPLATE_DATA_SOURCE_CANDIDATES,
    _TEMPLATE_DIR_NAME,
    _TEMPLATE_SUFFIX,
    ResearchTemplate,
    ResearchTemplateRecommendation,
    _as_str_list,
    _dedupe,
    _inspect_source_binding_snapshot,
    _load_company_facets_from_manifest,
    _load_json_object,
    _normalize_research_target,
    _normalize_template_name,
    _read_template_title,
    _recommendation_payload,
    _resolve_template_dir,
    _sha256_file,
    _sha256_json_object,
    _source_map_sources_by_name,
)
from dayu.cli.research_template_assets import build_composed_research_template_text
from dayu.cli.research_template_checklist import render_research_checklist_markdown
from dayu.cli.research_template_definitions import load_research_template_definition
from dayu.cli.research_template_routing import TEMPLATE_FACET_RULES, TEMPLATE_PRIORITY
from dayu.services.internal.write_pipeline.models import CompanyFacetProfile


def list_research_templates() -> tuple[ResearchTemplate, ...]:
    """枚举打包目录中的 Markdown 研究模板，并排除目录 README。

    Args:
        无。

    Returns:
        按文件名排序的稳定模板视图元组。

    Raises:
        FileNotFoundError: 当打包研究模板目录不存在时，由 ``_resolve_template_dir`` 传播。
        OSError: 当模板目录无法遍历或模板标题文件无法读取时。
    """

    template_dir = _resolve_template_dir()
    templates = []
    for path in sorted(template_dir.glob(f"*{_TEMPLATE_SUFFIX}")):
        name = path.stem
        if name.lower() == "readme":
            continue
        templates.append(ResearchTemplate(name=name, title=_read_template_title(path), path=path))
    return tuple(templates)


def load_research_template(name: str) -> str:
    """按稳定模板名读取打包 Markdown 模板正文。

    Args:
        name: 研究模板的稳定名称。

    Returns:
        UTF-8 解码后的模板全文。

    Raises:
        ValueError: 当模板名为空或含非法路径字符时。
        FileNotFoundError: 当模板目录或指定模板文件不存在时。
        OSError: 当模板文件无法读取时。
    """

    return _resolve_template_path(name).read_text(encoding="utf-8")


def copy_research_template(
    name: str,
    *,
    workspace_root: Path,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """把一个打包模板复制到工作区标准 assets 目录或指定路径。

    Args:
        name: 研究模板的稳定名称。
        workspace_root: 研究工作区根目录。
        output_path: 可选自定义输出路径；为空时使用标准 assets 路径。
        overwrite: 目标存在时是否允许覆盖。

    Returns:
        实际写入的目标文件绝对路径。

    Raises:
        ValueError: 当模板名无效时。
        FileNotFoundError: 当指定打包模板不存在时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当源模板读取、目标目录创建或文件写入失败时。
    """

    source_path = _resolve_template_path(name)
    target_path = output_path or workspace_root / "assets" / _TEMPLATE_DIR_NAME / source_path.name
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return target_path


def compose_research_template(
    name: str,
    *,
    workspace_root: Path,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """组合 common 与指定行业模板，并写入工作区模板资产文件。

    Args:
        name: 研究模板的稳定名称。
        workspace_root: 研究工作区根目录。
        output_path: 可选自定义输出路径；为空时使用标准 assets 路径。
        overwrite: 目标存在时是否允许覆盖。

    Returns:
        组合模板的目标文件绝对路径。

    Raises:
        ValueError: 当模板名无效或组合资产不满足要求时。
        FileNotFoundError: 当组合所需的打包模板不存在时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当目标目录创建或组合文件写入失败时。
    """

    normalized = _normalize_template_name(name)
    composed_text = build_composed_research_template_text(normalized)
    default_name = "common.write.md" if normalized == _FALLBACK_TEMPLATE_NAME else f"common-plus-{normalized}.md"
    target_path = output_path or workspace_root / "assets" / _TEMPLATE_DIR_NAME / default_name
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(composed_text, encoding="utf-8", newline="\n")
    return target_path


def materialize_research_checklist(
    name: str,
    *,
    workspace_root: Path,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """把模板定义渲染为研究检查单 Markdown 并写入工作区。

    Args:
        name: 研究模板的稳定名称。
        workspace_root: 研究工作区根目录。
        output_path: 可选自定义输出路径；为空时使用标准 assets 路径。
        overwrite: 目标存在时是否允许覆盖。

    Returns:
        实际写入的检查单文件绝对路径。

    Raises:
        FileNotFoundError: 当模板定义资产不存在时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        ValueError: 当模板定义结构或完整性校验失败时。
        OSError: 当目标目录创建或检查单写入失败时。
    """

    definition = load_research_template_definition(name)
    markdown = render_research_checklist_markdown(definition)
    target_path = output_path or workspace_root / "assets" / _TEMPLATE_DIR_NAME / f"{definition.name}.checklist.md"
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(markdown, encoding="utf-8", newline="\n")
    return target_path


def recommend_research_templates(
    company_facets: CompanyFacetProfile | None,
    *,
    limit: int | None = None,
) -> tuple[ResearchTemplateRecommendation, ...]:
    """根据公司主特征与约束特征为打包模板评分并稳定排序。

    Args:
        company_facets: 用于模板路由的公司主特征与约束特征；可为空。
        limit: 可选最大推荐数量；负数按零处理。

    Returns:
        按分数、模板优先级和名称排序的推荐元组。

    Raises:
        FileNotFoundError: 当模板资产目录或 common 回退模板不存在时。
        OSError: 当模板资产无法枚举或读取时。
        KeyError: 当打包模板集合缺少 common 回退模板时。
    """

    templates_by_name = {template.name: template for template in list_research_templates()}
    primary_facets = tuple(company_facets.primary_facets) if company_facets is not None else ()
    constraint_facets = tuple(company_facets.cross_cutting_facets) if company_facets is not None else ()
    recommendations: list[ResearchTemplateRecommendation] = []
    for name, rule_facets in TEMPLATE_FACET_RULES.items():
        template = templates_by_name.get(name)
        if template is None:
            continue
        primary_matches = tuple(facet for facet in primary_facets if facet in rule_facets)
        constraint_matches = tuple(facet for facet in constraint_facets if facet in rule_facets)
        score = len(primary_matches) * 3 + len(constraint_matches)
        matched = _dedupe([*primary_matches, *constraint_matches])
        if score <= 0:
            continue
        recommendations.append(
            ResearchTemplateRecommendation(
                name=name,
                title=template.title,
                score=score,
                matched_facets=matched,
                reason=f"matched facets: {', '.join(matched)}",
            )
        )
    if not recommendations:
        fallback = templates_by_name[_FALLBACK_TEMPLATE_NAME]
        recommendations.append(
            ResearchTemplateRecommendation(
                name=fallback.name,
                title=fallback.title,
                score=0,
                matched_facets=(),
                reason="no industry-specific facet matched; using common template",
            )
        )
    recommendations.sort(key=lambda item: (-item.score, TEMPLATE_PRIORITY.get(item.name, 99), item.name))
    if limit is not None:
        return tuple(recommendations[: max(limit, 0)])
    return tuple(recommendations)


def extract_monitoring_variables(name: str) -> tuple[str, ...]:
    """从模板的“监控变量”章节提取项目符号并稳定去重。

    Args:
        name: 研究模板的稳定名称。

    Returns:
        按模板出现顺序排列的监控变量元组。

    Raises:
        ValueError: 当模板名无效时。
        FileNotFoundError: 当指定模板不存在时。
        OSError: 当模板文件无法读取时。
    """

    content = load_research_template(name)
    variables: list[str] = []
    in_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and "监控变量" in stripped:
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section or not stripped.startswith("- "):
            continue
        variables.append(stripped.removeprefix("- ").strip())
    return _dedupe(variables)


def build_monitoring_rules_payload(name: str) -> dict[str, object]:
    """根据模板监控变量构建人工复核模式的监控规则草案。

    Args:
        name: 研究模板的稳定名称。

    Returns:
        包含模板、变量、节奏与自动化禁用标记的规则载荷。

    Raises:
        ValueError: 当模板名无效时。
        FileNotFoundError: 当模板资产不存在时。
        OSError: 当模板文件无法读取时。
    """

    normalized = _normalize_template_name(name)
    template = _resolve_template_path(normalized)
    variables = extract_monitoring_variables(normalized)
    data_source_candidates = list(get_monitoring_data_source_candidates(normalized))
    return {
        "schema_version": 1,
        "template": normalized,
        "source_template_file": str(template),
        "rule_type": "manual_review",
        "cadence": "quarterly",
        "data_source_candidates": data_source_candidates,
        "variables": [
            {
                "name": variable,
                "source_section": "监控变量",
                "evidence_required": True,
                "data_source_candidates": data_source_candidates,
                "binding_status": "unbound",
                "notes": "Draft rule extracted from research template; bind to concrete data source before automation.",
            }
            for variable in variables
        ],
    }


def build_monitoring_source_map_payload(name: str) -> dict[str, object]:
    """为模板候选数据源构建默认未绑定的 source-map 草案。

    Args:
        name: 研究模板的稳定名称。

    Returns:
        包含 source 候选、provider 元数据和 binding 状态的载荷。

    Raises:
        ValueError: 当模板名无效时。
    """

    normalized = _normalize_template_name(name)
    candidates = get_monitoring_data_source_candidates(normalized)
    return {
        "schema_version": 1,
        "template": normalized,
        "source_map_type": "monitoring_data_binding_draft",
        "binding_status": "unbound",
        "data_sources": [
            {
                "source": source,
                "binding_status": "unbound",
                **_DATA_SOURCE_BINDING_CANDIDATES.get(
                    source,
                    {
                        "provider_type": "unknown_placeholder",
                        "candidate_tools": [],
                        "candidate_fields": [],
                    },
                ),
                "notes": "Draft source binding only; verify concrete provider fields before automation.",
            }
            for source in candidates
        ],
    }


def validate_monitoring_source_map_payload(
    rules_payload: dict[str, object],
    source_map_payload: dict[str, object],
) -> dict[str, object]:
    """校验监控规则与 source-map 的模板、变量和候选数据源一致性。

    Args:
        rules_payload: 待校验的监控规则草案。
        source_map_payload: 待校验、预览或绑定的数据源映射载荷。

    Returns:
        包含 ``ok``、错误、警告、模板和计数的验证结果。

    Raises:
        本函数把结构和一致性问题收集到结果中，不显式抛出业务异常。
    """

    errors: list[str] = []
    warnings: list[str] = []
    rules_template = str(rules_payload.get("template", "") or "")
    source_map_template = str(source_map_payload.get("template", "") or "")
    if rules_template != source_map_template:
        errors.append(f"template mismatch: rules={rules_template!r} source_map={source_map_template!r}")

    rules_sources = set(_as_str_list(rules_payload.get("data_source_candidates")))
    variable_sources: set[str] = set()
    variables = rules_payload.get("variables", [])
    if isinstance(variables, list):
        for index, variable in enumerate(variables):
            if not isinstance(variable, dict):
                errors.append(f"variables[{index}] must be an object")
                continue
            variable_sources.update(_as_str_list(variable.get("data_source_candidates")))
            binding_status = str(variable.get("binding_status", "") or "")
            if binding_status not in {"unbound", "bound"}:
                errors.append(f"variables[{index}].binding_status must be unbound or bound")
    else:
        errors.append("variables must be a list")

    data_sources = source_map_payload.get("data_sources", [])
    mapped_sources: set[str] = set()
    if isinstance(data_sources, list):
        for index, source in enumerate(data_sources):
            if not isinstance(source, dict):
                errors.append(f"data_sources[{index}] must be an object")
                continue
            source_name = str(source.get("source", "") or "")
            if source_name:
                mapped_sources.add(source_name)
            binding_status = str(source.get("binding_status", "") or "")
            if binding_status not in {"unbound", "bound"}:
                errors.append(f"data_sources[{index}].binding_status must be unbound or bound")
    else:
        errors.append("data_sources must be a list")

    required_sources = rules_sources | variable_sources
    missing_sources = sorted(required_sources - mapped_sources)
    extra_sources = sorted(mapped_sources - required_sources)
    if missing_sources:
        errors.append(f"missing source-map entries: {', '.join(missing_sources)}")
    if extra_sources:
        warnings.append(f"unused source-map entries: {', '.join(extra_sources)}")
    return {
        "ok": not errors,
        "template": rules_template or source_map_template,
        "errors": errors,
        "warnings": warnings,
        "rules_source_count": len(required_sources),
        "source_map_entry_count": len(mapped_sources),
    }


def build_monitoring_source_binding_preview(
    source_map_payload: dict[str, object],
    approval_payload: dict[str, object],
) -> dict[str, object]:
    """校验批准载荷，并生成支持的 Dayu 数据源绑定预览。

    Args:
        source_map_payload: 待校验、预览或绑定的数据源映射载荷。
        approval_payload: 声明批准人、引用与具体 source 绑定的批准载荷。

    Returns:
        包含绑定后 source-map、变更项和是否可应用标志的预览。

    Raises:
        ValueError: 当 source-map、批准记录、provider/tool/field 或绑定集合无效时。
    """

    if approval_payload.get("schema_version") != 1:
        raise ValueError("binding approval schema_version must be 1")
    if approval_payload.get("approval_type") != "research_monitoring_source_binding":
        raise ValueError("approval_type must be research_monitoring_source_binding")
    source_template = str(source_map_payload.get("template", "") or "")
    approval_template = str(approval_payload.get("template", "") or "")
    if not approval_template or approval_template != source_template:
        raise ValueError(
            f"binding approval template mismatch: source_map={source_template!r} approval={approval_template!r}"
        )
    approved_by = str(approval_payload.get("approved_by", "") or "").strip()
    approval_reference = str(approval_payload.get("approval_reference", "") or "").strip()
    if not approved_by:
        raise ValueError("binding approval approved_by is required")
    if not approval_reference:
        raise ValueError("binding approval approval_reference is required")
    bindings = approval_payload.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("binding approval bindings must be a non-empty list")

    updated = deepcopy(source_map_payload)
    data_sources = updated.get("data_sources")
    if not isinstance(data_sources, list):
        raise ValueError("source-map data_sources must be a list")
    sources_by_name = {
        str(source.get("source", "") or ""): source
        for source in data_sources
        if isinstance(source, dict) and str(source.get("source", "") or "")
    }
    changed_sources: list[str] = []
    seen_sources: set[str] = set()
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise ValueError(f"binding approval bindings[{index}] must be an object")
        source_name = str(binding.get("source", "") or "").strip()
        if not source_name or source_name not in sources_by_name:
            raise ValueError(f"binding approval bindings[{index}].source is unknown: {source_name!r}")
        if source_name in seen_sources:
            raise ValueError(f"duplicate binding approval source: {source_name}")
        seen_sources.add(source_name)
        source = sources_by_name[source_name]
        if source.get("provider_type") != "dayu_fins_tool":
            raise ValueError(f"source {source_name!r} is not an implemented dayu_fins_tool provider")
        selected_tool = str(binding.get("selected_tool", "") or "").strip()
        candidate_tools = _as_str_list(source.get("candidate_tools"))
        if selected_tool not in candidate_tools:
            raise ValueError(f"source {source_name!r} selected_tool is not a declared candidate: {selected_tool!r}")
        selected_fields = _dedupe(_as_str_list(binding.get("selected_fields")))
        if not selected_fields:
            raise ValueError(f"source {source_name!r} selected_fields must be non-empty")
        candidate_fields = set(_as_str_list(source.get("candidate_fields")))
        unknown_fields = [field for field in selected_fields if field not in candidate_fields]
        if unknown_fields:
            raise ValueError(f"source {source_name!r} selected_fields are not declared candidates: {unknown_fields}")
        source["binding_status"] = "bound"
        source["selected_tool"] = selected_tool
        source["selected_fields"] = list(selected_fields)
        source["binding_approval"] = {
            "approved_by": approved_by,
            "approval_reference": approval_reference,
        }
        changed_sources.append(source_name)

    bound_count = sum(isinstance(source, dict) and source.get("binding_status") == "bound" for source in data_sources)
    if bound_count == len(data_sources):
        overall_status = "bound"
    elif bound_count:
        overall_status = "partially_bound"
    else:
        overall_status = "unbound"
    updated["binding_status"] = overall_status
    return {
        "schema_version": 1,
        "preview_type": "research_monitoring_source_binding",
        "template": source_template,
        "approved_by": approved_by,
        "approval_reference": approval_reference,
        "changed_source_count": len(changed_sources),
        "changed_sources": changed_sources,
        "resulting_binding_status": overall_status,
        "source_map": updated,
    }


def write_monitoring_source_binding_approval(
    source_map_path: Path,
    approval_path: Path,
) -> dict[str, object]:
    """应用已批准的数据源绑定，并在原位写入前创建内容寻址备份。

    Args:
        source_map_path: 当前监控 source-map 文件路径。
        approval_path: 绑定批准 JSON 文件路径。

    Returns:
        包含更新后 source-map、备份路径和绑定摘要的结果。

    Raises:
        OSError: 当 source-map、批准文件或备份/目标文件无法读写时。
        ValueError: 当 JSON、批准内容或绑定预览无效时。
        FileExistsError: 当内容寻址备份已存在但字节与当前 source-map 不一致时。
    """

    resolved_source_map = source_map_path.resolve()
    resolved_approval = approval_path.resolve()
    source_map_payload = _load_json_object(resolved_source_map)
    approval_payload = _load_json_object(resolved_approval)
    preview = build_monitoring_source_binding_preview(source_map_payload, approval_payload)
    original_fingerprint = _sha256_file(resolved_source_map)
    backup_path = resolved_source_map.with_name(
        f"{resolved_source_map.stem}.before-bindings.{original_fingerprint[:12]}.json"
    )
    if backup_path.exists():
        if not backup_path.is_file() or _sha256_file(backup_path) != original_fingerprint:
            raise FileExistsError(f"binding backup path is occupied by different content: {backup_path}")
    else:
        backup_path.write_bytes(resolved_source_map.read_bytes())
    updated_source_map = preview.get("source_map")
    if not isinstance(updated_source_map, dict):
        raise ValueError("binding preview did not produce a source-map object")
    resolved_source_map.write_text(
        json.dumps(updated_source_map, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "source_map_file": str(resolved_source_map),
        "backup_file": str(backup_path),
        "approval_file": str(resolved_approval),
        "source_map_fingerprint_before": original_fingerprint,
        "source_map_fingerprint_after": _sha256_file(resolved_source_map),
        "preview": preview,
    }


def build_monitoring_source_binding_rollback_preview(
    source_map_path: Path,
    backup_path: Path,
) -> dict[str, object]:
    """验证内容寻址备份并预览 source-map 绑定回滚，不执行写入。

    Args:
        source_map_path: 当前监控 source-map 文件路径。
        backup_path: 待验证或恢复的内容寻址备份路径。

    Returns:
        包含当前/备份指纹、绑定变化和 ``can_rollback`` 的预览。

    Raises:
        OSError: 当 source-map 或备份文件无法读取时。
        ValueError: 当备份命名、指纹、模板或 source 集合不匹配时。
    """

    resolved_source_map = source_map_path.resolve()
    resolved_backup = backup_path.resolve()
    if resolved_source_map == resolved_backup:
        raise ValueError("source-map and binding backup must be different files")
    if resolved_source_map.parent != resolved_backup.parent:
        raise ValueError("binding backup must be in the same directory as source-map")

    current_payload = _load_json_object(resolved_source_map)
    backup_payload = _load_json_object(resolved_backup)
    current_template = str(current_payload.get("template", "") or "").strip()
    backup_template = str(backup_payload.get("template", "") or "").strip()
    if not current_template or current_template != backup_template:
        raise ValueError(
            f"binding rollback template mismatch: source_map={current_template!r} backup={backup_template!r}"
        )

    backup_fingerprint = _sha256_file(resolved_backup)
    trusted_snapshot_names = {
        "before_bindings": f"{resolved_source_map.stem}.before-bindings.{backup_fingerprint[:12]}.json",
        "before_rollback": f"{resolved_source_map.stem}.before-rollback.{backup_fingerprint[:12]}.json",
    }
    matching_snapshot_types = [
        snapshot_type
        for snapshot_type, expected_name in trusted_snapshot_names.items()
        if resolved_backup.name == expected_name
    ]
    if not matching_snapshot_types:
        raise ValueError(
            "binding backup filename does not match a trusted source-map snapshot and content fingerprint: "
            f"expected one of {sorted(trusted_snapshot_names.values())!r}"
        )
    snapshot_type = matching_snapshot_types[0]

    current_sources = _source_map_sources_by_name(current_payload, label="source-map")
    backup_sources = _source_map_sources_by_name(backup_payload, label="binding backup")
    current_source_names = set(current_sources)
    backup_source_names = set(backup_sources)
    if current_source_names != backup_source_names:
        missing = sorted(current_source_names - backup_source_names)
        extra = sorted(backup_source_names - current_source_names)
        raise ValueError(f"binding rollback source set mismatch: missing={missing} extra={extra}")

    changed_sources = sorted(
        source_name
        for source_name in current_source_names
        if current_sources[source_name] != backup_sources[source_name]
    )
    return {
        "schema_version": 1,
        "preview_type": "research_monitoring_source_binding_rollback",
        "template": current_template,
        "source_map_file": str(resolved_source_map),
        "binding_backup_file": str(resolved_backup),
        "snapshot_type": snapshot_type,
        "source_map_fingerprint_before": _sha256_file(resolved_source_map),
        "source_map_fingerprint_after": backup_fingerprint,
        "binding_status_before": str(current_payload.get("binding_status", "") or ""),
        "binding_status_after": str(backup_payload.get("binding_status", "") or ""),
        "changed_source_count": len(changed_sources),
        "changed_sources": changed_sources,
        "write_required": True,
    }


def write_monitoring_source_binding_rollback(
    source_map_path: Path,
    backup_path: Path,
) -> dict[str, object]:
    """保存当前 source-map 的可重做快照后，恢复指定绑定备份。

    Args:
        source_map_path: 当前监控 source-map 文件路径。
        backup_path: 待验证或恢复的内容寻址备份路径。

    Returns:
        包含恢复路径、重做备份、指纹和恢复后绑定摘要的结果。

    Raises:
        OSError: 当当前文件、备份、重做快照或目标文件无法读写时。
        ValueError: 当回滚预览不允许执行或恢复后内容无效时。
        FileExistsError: 当内容寻址重做快照已存在但字节不一致时。
    """

    preview = build_monitoring_source_binding_rollback_preview(source_map_path, backup_path)
    resolved_source_map = Path(str(preview["source_map_file"]))
    resolved_backup = Path(str(preview["binding_backup_file"]))
    current_fingerprint = str(preview["source_map_fingerprint_before"])
    rollback_backup_path = resolved_source_map.with_name(
        f"{resolved_source_map.stem}.before-rollback.{current_fingerprint[:12]}.json"
    )
    if rollback_backup_path.exists():
        if not rollback_backup_path.is_file() or _sha256_file(rollback_backup_path) != current_fingerprint:
            raise FileExistsError(f"rollback backup path is occupied by different content: {rollback_backup_path}")
    else:
        rollback_backup_path.write_bytes(resolved_source_map.read_bytes())

    resolved_source_map.write_bytes(resolved_backup.read_bytes())
    restored_fingerprint = _sha256_file(resolved_source_map)
    expected_fingerprint = str(preview["source_map_fingerprint_after"])
    if restored_fingerprint != expected_fingerprint:
        raise ValueError("restored source-map fingerprint does not match binding backup")
    return {
        "source_map_file": str(resolved_source_map),
        "binding_backup_file": str(resolved_backup),
        "rollback_backup_file": str(rollback_backup_path),
        "source_map_fingerprint_before": current_fingerprint,
        "source_map_fingerprint_after": restored_fingerprint,
        "preview": preview,
    }


def inspect_monitoring_source_binding_history(source_map_path: Path) -> dict[str, object]:
    """检查 source-map 旁的批准备份与回滚快照，并汇总有效性。

    Args:
        source_map_path: 当前监控 source-map 文件路径。

    Returns:
        包含当前绑定、备份检查结果、回滚检查结果和验证状态的历史报告。

    Raises:
        OSError: 当当前 source-map 无法读取或计算指纹时。
        ValueError: 当当前 source-map 的模板或 source 集合无效时。
    """

    resolved_source_map = source_map_path.resolve()
    current_payload = _load_json_object(resolved_source_map)
    template = str(current_payload.get("template", "") or "").strip()
    if not template:
        raise ValueError("source-map template is required")
    current_sources = _source_map_sources_by_name(current_payload, label="source-map")
    snapshot_specs = (
        ("before_bindings", "before-bindings"),
        ("before_rollback", "before-rollback"),
    )
    snapshots: list[dict[str, object]] = []
    for snapshot_type, filename_marker in snapshot_specs:
        pattern = f"{resolved_source_map.stem}.{filename_marker}.*.json"
        for snapshot_path in sorted(resolved_source_map.parent.glob(pattern), key=str):
            snapshots.append(
                _inspect_source_binding_snapshot(
                    snapshot_path.resolve(),
                    source_map_path=resolved_source_map,
                    current_template=template,
                    current_source_names=set(current_sources),
                    snapshot_type=snapshot_type,
                    filename_marker=filename_marker,
                )
            )

    invalid_snapshots = [snapshot for snapshot in snapshots if snapshot.get("ok") is not True]
    before_bindings_count = sum(snapshot.get("snapshot_type") == "before_bindings" for snapshot in snapshots)
    before_rollback_count = sum(snapshot.get("snapshot_type") == "before_rollback" for snapshot in snapshots)
    bound_sources = sorted(
        source_name for source_name, source in current_sources.items() if source.get("binding_status") == "bound"
    )
    return {
        "schema_version": 1,
        "inspection_type": "research_monitoring_source_binding_history",
        "source_map_file": str(resolved_source_map),
        "template": template,
        "current": {
            "fingerprint": _sha256_file(resolved_source_map),
            "binding_status": str(current_payload.get("binding_status", "") or ""),
            "bound_sources": bound_sources,
        },
        "summary": {
            "snapshot_count": len(snapshots),
            "valid_snapshot_count": len(snapshots) - len(invalid_snapshots),
            "invalid_snapshot_count": len(invalid_snapshots),
            "before_bindings_count": before_bindings_count,
            "before_rollback_count": before_rollback_count,
        },
        "snapshots": snapshots,
        "validation": {
            "ok": not invalid_snapshots,
            "errors": [f"invalid binding snapshot: {snapshot.get('snapshot_file')}" for snapshot in invalid_snapshots],
        },
    }


def build_research_template_package_manifest() -> dict[str, object]:
    """为全部打包研究模板生成标题、路径与 SHA-256 清单。

    Args:
        无。

    Returns:
        包含 schema、模板目录和模板条目的 package manifest。

    Raises:
        FileNotFoundError: 当打包模板目录不存在时。
        OSError: 当模板目录、标题或模板字节无法读取时。
    """

    templates = []
    for template in list_research_templates():
        rules_payload = build_monitoring_rules_payload(template.name)
        source_map_payload = build_monitoring_source_map_payload(template.name)
        validation = validate_monitoring_source_map_payload(rules_payload, source_map_payload)
        variables = rules_payload.get("variables", [])
        data_sources = source_map_payload.get("data_sources", [])
        templates.append(
            {
                "name": template.name,
                "title": template.title,
                "template_file": str(template.path),
                "monitoring_variable_count": len(variables) if isinstance(variables, list) else 0,
                "data_source_count": len(data_sources) if isinstance(data_sources, list) else 0,
                "validation": validation,
            }
        )
    return {
        "schema_version": 1,
        "manifest_type": "research_template_package",
        "templates": templates,
    }


def get_monitoring_data_source_candidates(name: str) -> tuple[str, ...]:
    """返回模板专属候选数据源；未配置时回退到 common 候选。

    Args:
        name: 研究模板的稳定名称。

    Returns:
        按配置顺序排列的数据源名称元组。

    Raises:
        ValueError: 当模板名无效时。
    """

    normalized = _normalize_template_name(name)
    return _TEMPLATE_DATA_SOURCE_CANDIDATES.get(normalized, _COMMON_DATA_SOURCE_CANDIDATES)


def write_monitoring_rules_payload(
    name: str,
    *,
    workspace_root: Path,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """构建并写入单个模板的监控规则 JSON 草案。

    Args:
        name: 研究模板的稳定名称。
        workspace_root: 研究工作区根目录。
        output_path: 可选自定义输出路径；为空时使用标准 assets 路径。
        overwrite: 目标存在时是否允许覆盖。

    Returns:
        实际写入的规则文件绝对路径。

    Raises:
        ValueError: 当模板名无效时。
        FileNotFoundError: 当模板资产不存在时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当模板读取、目录创建或 JSON 文件写入失败时。
    """

    normalized = _normalize_template_name(name)
    payload = build_monitoring_rules_payload(normalized)
    target_path = output_path or workspace_root / "assets" / _TEMPLATE_DIR_NAME / f"{normalized}.monitoring-rules.json"
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target_path


def write_monitoring_source_map_payload(
    name: str,
    *,
    workspace_root: Path,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """构建并写入单个模板的监控 source-map JSON 草案。

    Args:
        name: 研究模板的稳定名称。
        workspace_root: 研究工作区根目录。
        output_path: 可选自定义输出路径；为空时使用标准 assets 路径。
        overwrite: 目标存在时是否允许覆盖。

    Returns:
        实际写入的 source-map 文件绝对路径。

    Raises:
        ValueError: 当模板名无效时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当目录创建或 JSON 文件写入失败时。
    """

    normalized = _normalize_template_name(name)
    payload = build_monitoring_source_map_payload(normalized)
    target_path = output_path or workspace_root / "assets" / _TEMPLATE_DIR_NAME / f"{normalized}.source-map.json"
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target_path


def write_research_template_package_manifest(
    *,
    workspace_root: Path,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """构建并写入工作区级研究模板 package manifest JSON。

    Args:
        workspace_root: 研究工作区根目录。
        output_path: 可选自定义输出路径；为空时使用标准 assets 路径。
        overwrite: 目标存在时是否允许覆盖。

    Returns:
        实际写入的 manifest 文件绝对路径。

    Raises:
        FileNotFoundError: 当打包模板目录不存在时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当模板读取、目录创建或 manifest 写入失败时。
    """

    payload = build_research_template_package_manifest()
    target_path = output_path or workspace_root / "assets" / _TEMPLATE_DIR_NAME / "research-template.manifest.json"
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target_path


def build_research_template_usage_guide(
    name: str,
    *,
    template_file: Path | None = None,
    workbook_file: Path | None = None,
    progress_report_file: Path | None = None,
    rules_file: Path | None = None,
    source_map_file: Path | None = None,
    manifest_file: Path | None = None,
    monitoring_plan_file: Path | None = None,
    monitoring_status_file: Path | None = None,
    workbook_status_file: Path | None = None,
    report_status_file: Path | None = None,
    ticker: str = "",
    company: str = "",
) -> str:
    """根据模板及其物化产物路径构建本地研究工作流使用指南。

    Args:
        name: 研究模板的稳定名称。
        template_file: 物化后的研究模板文件路径。
        workbook_file: 物化后的研究工作簿文件路径。
        progress_report_file: 可选研究进度报告路径。
        rules_file: 物化后的监控规则文件路径。
        source_map_file: 物化后的监控 source-map 文件路径。
        manifest_file: 物化后的 package manifest 文件路径。
        monitoring_plan_file: 可选监控执行计划文件路径。
        monitoring_status_file: 可选监控状态快照路径。
        workbook_status_file: 可选工作簿状态快照路径。
        report_status_file: 可选报告状态快照路径。
        ticker: 研究目标股票代码。
        company: 研究目标公司名称。

    Returns:
        包含目标公司、产物索引和建议命令的 Markdown 文本。

    Raises:
        ValueError: 当模板名无效时。
        FileNotFoundError: 当模板目录或指定模板文件不存在时，由路径解析传播。
        OSError: 当模板标题文件无法读取时，由底层文件操作传播。
    """

    normalized = _normalize_template_name(name)
    template = _resolve_template_path(normalized)
    variables = extract_monitoring_variables(normalized)
    data_sources = get_monitoring_data_source_candidates(normalized)
    artifact_lines = []
    for label, path in (
        ("template", template_file),
        ("research_workbook", workbook_file),
        ("research_progress_report", progress_report_file),
        ("monitoring_rules", rules_file),
        ("source_map", source_map_file),
        ("package_manifest", manifest_file),
        ("monitoring_plan", monitoring_plan_file),
        ("monitoring_status", monitoring_status_file),
        ("research_workbook_status", workbook_status_file),
        ("research_progress_report_status", report_status_file),
    ):
        if path is not None:
            artifact_lines.append(f"- `{label}`: `{path}`")
    if not artifact_lines:
        artifact_lines.append(
            "- Run `dayu-cli research-template materialize <name> --base ./workspace` to create local files."
        )

    variable_lines = [f"- {variable}" for variable in variables] or ["- No monitoring variables found."]
    source_lines = [f"- `{source}`" for source in data_sources] or ["- No data source candidates found."]
    template_arg = (
        str(template_file)
        if template_file is not None
        else f"./workspace/assets/research_templates/common-plus-{normalized}.md"
    )
    if normalized == _FALLBACK_TEMPLATE_NAME and template_file is None:
        template_arg = "./workspace/assets/research_templates/common.md"
    research_target = _normalize_research_target(ticker=ticker, company=company)
    ticker_arg = research_target["ticker"] or "<TICKER>"
    target_lines = [
        f"- Ticker: `{research_target['ticker'] or '(not set)'}`",
        f"- Company: `{research_target['company'] or '(not set)'}`",
    ]

    return "\n".join(
        [
            f"# Research Template Usage Guide: {normalized}",
            "",
            f"- Packaged template: `{template}`",
            f"- Template title: {_read_template_title(template)}",
            "",
            "## Research Target",
            "",
            *target_lines,
            "",
            "## Local Artifacts",
            "",
            *artifact_lines,
            "",
            "## Next Write Command",
            "",
            "```bash",
            f'dayu-cli write --ticker {ticker_arg} --template "{template_arg}"',
            "```",
            "",
            "## Monitoring Variables",
            "",
            *variable_lines,
            "",
            "## Data Source Candidates",
            "",
            *source_lines,
            "",
            "## Notes",
            "",
            "- Generated monitoring rules are draft/manual-review rules until their source-map bindings are reviewed.",
            "- Keep this guide with the materialized template files so a future UI, scheduler, or report workflow can discover the bundle.",
            "",
        ]
    )


def write_research_template_usage_guide(
    name: str,
    *,
    workspace_root: Path,
    template_file: Path | None = None,
    workbook_file: Path | None = None,
    progress_report_file: Path | None = None,
    rules_file: Path | None = None,
    source_map_file: Path | None = None,
    manifest_file: Path | None = None,
    monitoring_plan_file: Path | None = None,
    monitoring_status_file: Path | None = None,
    workbook_status_file: Path | None = None,
    report_status_file: Path | None = None,
    ticker: str = "",
    company: str = "",
    output_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """构建并写入单个物化模板的 Markdown 使用指南。

    Args:
        name: 研究模板的稳定名称。
        workspace_root: 研究工作区根目录。
        template_file: 物化后的研究模板文件路径。
        workbook_file: 物化后的研究工作簿文件路径。
        progress_report_file: 可选研究进度报告路径。
        rules_file: 物化后的监控规则文件路径。
        source_map_file: 物化后的监控 source-map 文件路径。
        manifest_file: 物化后的 package manifest 文件路径。
        monitoring_plan_file: 可选监控执行计划文件路径。
        monitoring_status_file: 可选监控状态快照路径。
        workbook_status_file: 可选工作簿状态快照路径。
        report_status_file: 可选报告状态快照路径。
        ticker: 研究目标股票代码。
        company: 研究目标公司名称。
        output_path: 可选自定义输出路径；为空时使用标准 assets 路径。
        overwrite: 目标存在时是否允许覆盖。

    Returns:
        实际写入的使用指南绝对路径。

    Raises:
        ValueError: 当模板名无效时。
        FileNotFoundError: 当模板资产不存在时。
        FileExistsError: 当目标已存在且 ``overwrite`` 为 false 时。
        OSError: 当模板读取、目录创建或指南写入失败时。
    """

    normalized = _normalize_template_name(name)
    guide = build_research_template_usage_guide(
        normalized,
        template_file=template_file,
        workbook_file=workbook_file,
        progress_report_file=progress_report_file,
        rules_file=rules_file,
        source_map_file=source_map_file,
        manifest_file=manifest_file,
        monitoring_plan_file=monitoring_plan_file,
        monitoring_status_file=monitoring_status_file,
        workbook_status_file=workbook_status_file,
        report_status_file=report_status_file,
        ticker=ticker,
        company=company,
    )
    target_path = output_path or workspace_root / "assets" / _TEMPLATE_DIR_NAME / f"{normalized}.research-guide.md"
    target_path = target_path.resolve()
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"{target_path} already exists; pass --overwrite to replace it")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(guide, encoding="utf-8", newline="\n")
    return target_path


def _resolve_template_selection_from_write_manifest(manifest_path: Path) -> tuple[str, dict[str, object]]:
    """从完成的 write manifest 校验并解析最终研究模板选择及其依据。

    Args:
        manifest_path: 完成的 write manifest 文件路径。

    Returns:
        规范模板名与包含选择模式、请求值、公司特征和推荐信息的载荷。

    Raises:
        OSError: 当 write manifest 或模板资产无法读取时。
        ValueError: 当 manifest 缺少完成状态、模板选择或选择语义不一致时。
        FileNotFoundError: 当 manifest 选择的模板资产不存在时。
    """
    payload = _load_json_object(manifest_path)
    config = payload.get("config")
    config_payload = config if isinstance(config, dict) else {}
    requested_name = str(config_payload.get("research_template_requested_name", "") or "").strip().lower()
    resolved_name = str(config_payload.get("research_template_resolved_name", "") or "").strip().lower()
    selection_mode = str(config_payload.get("research_template_selection_mode", "") or "").strip().lower()
    provenance_values = (requested_name, resolved_name, selection_mode)
    if any(provenance_values):
        if not all(provenance_values):
            raise ValueError(f"write manifest contains incomplete research-template provenance: {manifest_path}")
        resolved_name = _normalize_template_name(resolved_name)
        _resolve_template_path(resolved_name)
        if selection_mode == "named" and requested_name != resolved_name:
            raise ValueError(f"write manifest named research-template provenance is inconsistent: {manifest_path}")
        if selection_mode == "auto" and requested_name != "auto":
            raise ValueError(f"write manifest auto research-template provenance is inconsistent: {manifest_path}")
        if selection_mode not in {"named", "auto"}:
            raise ValueError(f"write manifest research-template selection mode is unsupported: {selection_mode!r}")
        return resolved_name, {
            "selection_mode": "manifest_provenance",
            "selected_template": resolved_name,
            "manifest_file": str(manifest_path),
            "write_selection": {
                "requested_name": requested_name,
                "resolved_name": resolved_name,
                "selection_mode": selection_mode,
            },
        }

    company_facets = _load_company_facets_from_manifest(manifest_path)
    recommendation = recommend_research_templates(company_facets, limit=1)[0]
    return recommendation.name, {
        "selection_mode": "manifest_recommendation",
        "selected_template": recommendation.name,
        "manifest_file": str(manifest_path),
        "recommendation": _recommendation_payload(recommendation),
    }


def _build_source_write_manifest_binding(
    manifest_path: Path,
    *,
    expected_template: str,
) -> dict[str, object]:
    """构建绑定到 write manifest 文件与选择语义指纹的来源记录。

    Args:
        manifest_path: 完成的 write manifest 文件路径。
        expected_template: 调用方要求 manifest 必须选择的规范模板名。

    Returns:
        包含 manifest 路径、文件/语义指纹、最终模板和研究目标的绑定对象。

    Raises:
        OSError: 当 manifest 或模板资产无法读取并计算指纹时。
        ValueError: 当 manifest 选择无效或与期望模板不一致时。
        FileNotFoundError: 当选择的模板资产不存在时。
    """
    selected_template, selection = _resolve_template_selection_from_write_manifest(manifest_path)
    if selected_template != expected_template:
        raise ValueError(
            "write manifest selected template does not match materialized bundle: "
            f"source={selected_template!r} bundle={expected_template!r}"
        )
    source_payload = _load_json_object(manifest_path)
    source_config = source_payload.get("config")
    source_target = {"ticker": "", "company": ""}
    if isinstance(source_config, dict):
        source_target = _normalize_research_target(
            ticker=str(source_config.get("ticker", "") or ""),
            company=str(source_config.get("company", "") or ""),
        )
    return {
        "path": str(manifest_path),
        "file_fingerprint": _sha256_file(manifest_path),
        "semantic_fingerprint": _sha256_json_object(_build_write_manifest_binding_semantics(manifest_path)),
        "selected_template": selected_template,
        "selection": selection,
        "research_target": source_target,
    }


def _build_write_manifest_binding_semantics(manifest_path: Path) -> dict[str, object]:
    """提取 write manifest 中影响模板选择和研究目标的稳定语义字段。

    Args:
        manifest_path: 完成的 write manifest 文件路径。

    Returns:
        用于计算语义指纹的规范化字典。

    Raises:
        OSError: 当 manifest 或模板资产无法读取时。
        ValueError: 当 manifest 的模板选择语义无效时。
        FileNotFoundError: 当选择的模板资产不存在时。
    """
    selected_template, selection = _resolve_template_selection_from_write_manifest(manifest_path)
    source_payload = _load_json_object(manifest_path)
    source_config = source_payload.get("config")
    source_target = {"ticker": "", "company": ""}
    if isinstance(source_config, dict):
        source_target = _normalize_research_target(
            ticker=str(source_config.get("ticker", "") or ""),
            company=str(source_config.get("company", "") or ""),
        )
    company_facets = _load_company_facets_from_manifest(manifest_path)
    return {
        "schema_version": 1,
        "selected_template": selected_template,
        "selection_mode": str(selection.get("selection_mode", "") or ""),
        "research_target": source_target,
        "company_facets": company_facets.to_dict(),
    }


def _resolve_template_path(name: str) -> Path:
    """规范模板名并解析对应打包 Markdown 文件，要求文件存在。

    Args:
        name: 研究模板的稳定名称。

    Returns:
        指定研究模板的资产文件路径。

    Raises:
        ValueError: 当模板名为空或包含非法路径字符时。
        FileNotFoundError: 当模板目录或指定模板文件不存在时。
        OSError: 当底层路径状态检查失败时。
    """
    normalized = _normalize_template_name(name)
    template_path = _resolve_template_dir() / f"{normalized}{_TEMPLATE_SUFFIX}"
    if not template_path.is_file():
        available = ", ".join(template.name for template in list_research_templates()) or "(none)"
        raise FileNotFoundError(f"unknown research template {name!r}; available: {available}")
    return template_path
