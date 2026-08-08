"""研究模板拆分后的叶子类型、常量与通用辅助函数。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dayu.cli.research_template_definitions import ResearchTemplateDefinition
from dayu.cli.research_template_routing import load_company_facets_from_manifest
from dayu.services.internal.write_pipeline.models import CompanyFacetProfile
from dayu.startup.config_file_resolver import resolve_package_assets_path

_TEMPLATE_DIR_NAME = "research_templates"


_TEMPLATE_SUFFIX = ".md"


_FALLBACK_TEMPLATE_NAME = "common"


_BUNDLE_ARTIFACT_KEYS = (
    "write_template",
    "research_workbook",
    "research_progress_report",
    "research_checklist",
    "monitoring_rules",
    "source_map",
    "package_manifest",
    "usage_guide",
)


_COMMON_DATA_SOURCE_CANDIDATES = (
    "financial_statements",
    "company_filings",
    "market_data",
)


_TEMPLATE_DATA_SOURCE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "common": _COMMON_DATA_SOURCE_CANDIDATES,
    "consumer": (
        "financial_statements",
        "company_filings",
        "channel_checks",
        "market_data",
    ),
    "cyclical": (
        "financial_statements",
        "industry_price_data",
        "inventory_supply_data",
        "market_data",
    ),
    "technology": (
        "financial_statements",
        "operating_metrics",
        "product_release_notes",
        "market_data",
    ),
    "financial": (
        "financial_statements",
        "regulatory_filings",
        "capital_adequacy_data",
        "market_data",
    ),
}


_DATA_SOURCE_BINDING_CANDIDATES: dict[str, dict[str, object]] = {
    "financial_statements": {
        "provider_type": "dayu_fins_tool",
        "candidate_tools": ["get_financial_statement", "query_xbrl_facts", "get_table"],
        "candidate_fields": [
            "revenue",
            "gross_profit",
            "operating_profit",
            "net_income",
            "operating_cash_flow",
        ],
    },
    "company_filings": {
        "provider_type": "dayu_fins_tool",
        "candidate_tools": ["list_documents", "search_document", "read_section"],
        "candidate_fields": ["document_type", "section_title", "filing_date", "matched_text"],
    },
    "market_data": {
        "provider_type": "external_market_data_placeholder",
        "candidate_tools": [],
        "candidate_fields": ["price", "market_cap", "pe_ttm", "pb", "dividend_yield", "turnover"],
    },
    "channel_checks": {
        "provider_type": "manual_or_external_placeholder",
        "candidate_tools": [],
        "candidate_fields": ["same_store_sales", "channel_inventory", "store_count", "customer_frequency"],
    },
    "industry_price_data": {
        "provider_type": "external_industry_data_placeholder",
        "candidate_tools": [],
        "candidate_fields": ["spot_price", "spread", "freight_rate", "utilization_rate"],
    },
    "inventory_supply_data": {
        "provider_type": "external_industry_data_placeholder",
        "candidate_tools": [],
        "candidate_fields": ["inventory_days", "orderbook", "capacity_additions", "operating_rate"],
    },
    "operating_metrics": {
        "provider_type": "company_filings_or_manual_placeholder",
        "candidate_tools": ["search_document", "read_section"],
        "candidate_fields": ["mau", "dau", "arr", "nrr", "churn", "gross_margin"],
    },
    "product_release_notes": {
        "provider_type": "company_filings_or_web_placeholder",
        "candidate_tools": ["search_document", "read_section"],
        "candidate_fields": ["product_launch", "customer_case", "release_date", "management_commentary"],
    },
    "regulatory_filings": {
        "provider_type": "dayu_fins_tool",
        "candidate_tools": ["list_documents", "search_document", "read_section"],
        "candidate_fields": ["capital_ratio", "npl_ratio", "solvency_ratio", "regulatory_disclosure"],
    },
    "capital_adequacy_data": {
        "provider_type": "dayu_fins_tool",
        "candidate_tools": ["get_financial_statement", "search_document", "read_section"],
        "candidate_fields": ["cet1_ratio", "capital_adequacy_ratio", "leverage_ratio", "provision_coverage"],
    },
}


@dataclass(frozen=True)
class ResearchTemplate:
    """稳定表示一个打包研究模板。"""

    name: str
    title: str
    path: Path


@dataclass(frozen=True)
class ResearchTemplateRecommendation:
    """表示确定性的研究模板路由结果。"""

    name: str
    title: str
    score: int
    matched_facets: tuple[str, ...]
    reason: str


def _print_definition_header(definition: ResearchTemplateDefinition) -> None:
    """向标准输出打印模板定义的稳定名称与标题表头。

    Args:
        definition: 待打印表头的模板定义。

    Returns:
        无；模板名称与标题直接写入标准输出。

    Raises:
        OSError: 当标准输出流写入失败时由底层 ``print`` 调用传播。
    """

    print(f"# {definition.name}\t{definition.title}")


def _resolve_materialize_research_target(
    *,
    ticker_raw: object,
    company_raw: object,
    manifest_raw: object,
) -> dict[str, str]:
    """合并显式股票代码、公司名与可选写作清单中的研究目标。

    Args:
        ticker_raw: 显式股票代码原始值。
        company_raw: 显式公司名称原始值。
        manifest_raw: 可选写作清单路径原始值。

    Returns:
        包含规范化 ``ticker`` 与 ``company`` 的研究目标字典。

    Raises:
        OSError: 当写作清单无法读取时由底层文件操作传播。
        ValueError: 当写作清单不是合法 JSON 对象时。
    """
    manifest_target = {"ticker": "", "company": ""}
    if manifest_raw is not None and str(manifest_raw).strip():
        manifest_payload = _load_json_object(Path(str(manifest_raw)).resolve())
        config = manifest_payload.get("config")
        if isinstance(config, dict):
            manifest_target = _normalize_research_target(
                ticker=str(config.get("ticker", "") or ""),
                company=str(config.get("company", "") or ""),
            )
    explicit_ticker = str(ticker_raw).strip() if ticker_raw is not None else ""
    explicit_company = str(company_raw).strip() if company_raw is not None else ""
    return _normalize_research_target(
        ticker=explicit_ticker or manifest_target["ticker"],
        company=explicit_company or manifest_target["company"],
    )


def _build_research_portfolio_preview(
    portfolio_path: Path,
    workspace_root: Path,
    targets: list[dict[str, object]],
    *,
    overwrite: bool,
) -> dict[str, object]:
    """汇总 Portfolio 各目标的预期产物、冲突状态与已有文件指纹，不执行写入。

    Args:
        portfolio_path: Portfolio 配置文件的绝对路径。
        workspace_root: 研究工作区根目录。
        targets: 已完成模板与研究目标规范化的 Portfolio 目标列表。
        overwrite: 是否允许后续物化覆盖已有产物。

    Returns:
        包含目标预览、冲突计数、可执行状态及 Portfolio 指纹的预览载荷。

    Raises:
        OSError: 当 Portfolio 或已有产物无法读取并计算指纹时。
    """
    target_previews: list[dict[str, object]] = []
    blocked_count = 0
    overwrite_count = 0
    for target in targets:
        template = str(target["template"])
        target_workspace = workspace_root / str(target["workspace_key"])
        artifacts = _portfolio_target_artifact_paths(target_workspace, template)
        existing_files = [str(path) for path in artifacts.values() if path.exists()]
        if existing_files and not overwrite:
            action = "blocked_existing_files"
            blocked_count += 1
        elif existing_files:
            action = "overwrite"
            overwrite_count += 1
        else:
            action = "create"
        target_previews.append(
            {
                "ticker": target["ticker"],
                "company": target["company"],
                "template": template,
                "workspace_root": str(target_workspace),
                "selection": target["selection"],
                "write_manifest": target["write_manifest"],
                "action": action,
                "existing_files": existing_files,
                "artifacts": {key: str(path) for key, path in artifacts.items()},
                "regenerated_files": [
                    str(target_workspace / "assets" / _TEMPLATE_DIR_NAME / "research-template.manifest.json")
                ],
            }
        )
    return {
        "schema_version": 1,
        "preview_type": "research_portfolio_materialization",
        "portfolio_file": str(portfolio_path),
        "portfolio_fingerprint": _sha256_file(portfolio_path),
        "workspace_root": str(workspace_root),
        "overwrite": overwrite,
        "can_materialize": blocked_count == 0,
        "summary": {
            "target_count": len(target_previews),
            "create_count": len(target_previews) - blocked_count - overwrite_count,
            "overwrite_count": overwrite_count,
            "blocked_count": blocked_count,
        },
        "derived_outputs": {
            "materialization_report": str(workspace_root / "research-portfolio.materialization.json"),
            "monitoring_status": str(workspace_root / "assets" / _TEMPLATE_DIR_NAME / "monitoring-status.json"),
            "workbook_status": str(workspace_root / "assets" / _TEMPLATE_DIR_NAME / "research-workbook-status.json"),
            "report_status": str(
                workspace_root / "assets" / _TEMPLATE_DIR_NAME / "research-workbook-report-status.json"
            ),
        },
        "targets": target_previews,
    }


def _portfolio_target_artifact_paths(workspace_root: Path, template: str) -> dict[str, Path]:
    """计算单个模板工作区内全部标准物化产物的绝对路径。

    Args:
        workspace_root: 研究工作区根目录。
        template: 已规范化的研究模板名。

    Returns:
        产物键到预期绝对路径的映射。

    Raises:
        本函数只进行路径组合，不显式抛出异常。
    """
    artifact_dir = workspace_root / "assets" / _TEMPLATE_DIR_NAME
    template_file_name = "common.md" if template == _FALLBACK_TEMPLATE_NAME else f"common-plus-{template}.md"
    return {
        "write_template": artifact_dir / template_file_name,
        "research_workbook": artifact_dir / f"{template}.research-workbook.json",
        "research_progress_report": artifact_dir / f"{template}.research-progress.md",
        "monitoring_rules": artifact_dir / f"{template}.monitoring-rules.json",
        "source_map": artifact_dir / f"{template}.source-map.json",
        "usage_guide": artifact_dir / f"{template}.research-guide.md",
        "bundle": artifact_dir / f"{template}.bundle.json",
        "monitoring_plan": artifact_dir / f"{template}.monitoring-plan.json",
        "monitoring_status": artifact_dir / "monitoring-status.json",
        "workbook_status": artifact_dir / "research-workbook-status.json",
        "report_status": artifact_dir / "research-workbook-report-status.json",
    }


def _recommendation_payload(recommendation: ResearchTemplateRecommendation) -> dict[str, object]:
    """把模板推荐 dataclass 转换为可 JSON 序列化的字典。

    Args:
        recommendation: 待序列化的模板推荐结果。

    Returns:
        包含名称、标题、分数、命中特征与推荐原因的字典。

    Raises:
        本函数只读取已构造的推荐对象，不显式抛出异常。
    """
    return {
        "name": recommendation.name,
        "title": recommendation.title,
        "score": recommendation.score,
        "matched_facets": list(recommendation.matched_facets),
        "reason": recommendation.reason,
    }


def _company_facets_from_args(args: argparse.Namespace) -> CompanyFacetProfile:
    """合并命令行特征标签与可选清单中的公司特征，并保持稳定去重顺序。

    Args:
        args: 包含 manifest 与特征标签字段的命令行参数。

    Returns:
        用于模板路由的 ``CompanyFacetProfile``。

    Raises:
        OSError: 当命令行指定的清单文件无法读取时。
        ValueError: 当清单内容无法解析为公司特征时。
    """
    manifest_raw = getattr(args, "manifest", None)
    profile = _load_company_facets_from_manifest(Path(str(manifest_raw)).resolve()) if manifest_raw else None
    primary_facets = list(profile.primary_facets) if profile is not None else []
    constraint_facets = list(profile.cross_cutting_facets) if profile is not None else []
    primary_facets.extend(_as_str_list(getattr(args, "business_model_tags", ())))
    constraint_facets.extend(_as_str_list(getattr(args, "constraint_tags", ())))
    return CompanyFacetProfile(
        primary_facets=list(_dedupe(primary_facets)),
        cross_cutting_facets=list(_dedupe(constraint_facets)),
        confidence_notes=profile.confidence_notes if profile is not None else "",
    )


def _load_company_facets_from_manifest(path: Path) -> CompanyFacetProfile:
    """通过 research-template routing 真源加载指定清单的公司特征。

    Args:
        path: 待处理的文件路径。

    Returns:
        从清单解析得到的 ``CompanyFacetProfile``。

    Raises:
        OSError: 当清单文件无法读取时由 routing loader 传播。
        ValueError: 当清单结构或特征字段无效时由 routing loader 传播。
    """
    return load_company_facets_from_manifest(path)


def _load_json_object(path: Path) -> dict[str, object]:
    """以 UTF-8-SIG 读取 JSON 文件并要求顶层值为对象。

    Args:
        path: 待处理的文件路径。

    Returns:
        解析后的 JSON 对象字典。

    Raises:
        OSError: 当 JSON 文件无法读取时。
        json.JSONDecodeError: 当文件内容不是合法 JSON 时。
        ValueError: 当 JSON 顶层值不是对象时。
    """
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _load_workbook_evidence_records(path: Path) -> list[dict[str, object]]:
    """读取工作簿证据文件，并把单个对象或对象列表规范为非空记录列表。

    Args:
        path: 待处理的文件路径。

    Returns:
        一个或多个证据对象组成的列表。

    Raises:
        OSError: 当证据文件无法读取时。
        json.JSONDecodeError: 当证据文件不是合法 JSON 时。
        ValueError: 当顶层值不是对象/列表，或列表为空、含非对象元素时。
    """
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        records = [payload]
    elif isinstance(payload, list):
        records = payload
    else:
        raise ValueError(f"evidence file must contain an object or list: {path}")
    if not records or not all(isinstance(record, dict) for record in records):
        raise ValueError(f"evidence file must contain one or more objects: {path}")
    return records


def _resolve_template_dir() -> Path:
    """解析打包资产中的研究模板目录并确认目录存在。

    Args:
        无。

    Returns:
        研究模板资产目录的路径。

    Raises:
        FileNotFoundError: 当打包资产中不存在研究模板目录时。
        OSError: 当底层路径状态检查失败时。
    """
    template_dir = resolve_package_assets_path() / _TEMPLATE_DIR_NAME
    if not template_dir.is_dir():
        raise FileNotFoundError(f"research template directory not found: {template_dir}")
    return template_dir


def _normalize_template_name(name: str) -> str:
    """去除模板名两端空白、转换为小写并拒绝路径分隔符。

    Args:
        name: 用户提供的研究模板名。

    Returns:
        可安全用于模板资产查找的规范名称。

    Raises:
        ValueError: 当名称为空或包含反斜杠、斜杠、冒号、``..`` 时。
    """
    normalized = name.strip().lower()
    if not normalized:
        raise ValueError("template name is required")
    if any(char in normalized for char in ("\\", "/", ":", "..")):
        raise ValueError(f"invalid template name: {name!r}")
    return normalized


def _read_template_title(path: Path) -> str:
    """读取 Markdown 中首个一级标题；没有标题时回退到文件名。

    Args:
        path: 待处理的文件路径。

    Returns:
        模板标题或文件 stem。

    Raises:
        OSError: 当模板文件无法读取时。
    """
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return path.stem


def _as_str_list(value: object) -> list[str]:
    """把空值、字符串、可迭代值或标量规范为字符串列表。

    Args:
        value: 待转换为字符串列表或标识的输入值。

    Returns:
        保持输入迭代顺序的字符串列表。

    Raises:
        本函数不验证元素业务语义；元素字符串化异常由其 ``__str__`` 实现传播。
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    """去除空白字符串，并按首次出现顺序对字符串序列去重。

    Args:
        values: 待稳定去重的字符串序列。

    Returns:
        稳定去重后的非空字符串元组。

    Raises:
        本函数仅处理字符串迭代值，不显式抛出业务异常。
    """
    deduped: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in deduped:
            deduped.append(item)
    return tuple(deduped)


def _normalize_research_target(*, ticker: str, company: str) -> dict[str, str]:
    """规范化研究目标的股票代码大小写和公司名称空白。

    Args:
        ticker: 待规范化的股票代码。
        company: 待规范化的公司名称。

    Returns:
        含 ``ticker`` 与 ``company`` 两个键的研究目标字典。

    Raises:
        本函数仅处理字符串，不显式抛出异常。
    """
    return {
        "ticker": ticker.strip().upper(),
        "company": company.strip(),
    }


def _identifier_component(value: str) -> str:
    """把任意文本转换为小写、连字符分隔的标识组成部分。

    Args:
        value: 待转换为字符串列表或标识的输入值。

    Returns:
        移除空段后的稳定标识字符串。

    Raises:
        本函数仅处理字符串，不显式抛出异常。
    """
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    return "-".join(part for part in normalized.split("-") if part)


def _scheduler_state_from_plan_inspection(inspection: dict[str, object]) -> str:
    """根据计划检查的 validation 与 readiness 字段归纳调度状态。

    Args:
        inspection: 监控执行计划的检查结果。

    Returns:
        ``invalid_plan``、计划 readiness 状态或 ``blocked_unknown``。

    Raises:
        本函数对缺失或畸形字段使用安全回退，不显式抛出异常。
    """
    validation = inspection.get("validation")
    if not isinstance(validation, dict) or validation.get("ok") is not True:
        return "invalid_plan"
    readiness = inspection.get("readiness")
    if not isinstance(readiness, dict):
        return "blocked_unknown"
    return str(readiness.get("status", "") or "blocked_unknown")


def _discover_research_artifact_paths(
    workspace_root: Path,
    filename_glob: str,
    *,
    recursive: bool,
) -> tuple[Path, ...]:
    """在标准 assets 目录中发现匹配的研究产物，并可递归包含子工作区。

    Args:
        workspace_root: 研究工作区根目录。
        filename_glob: 相对于标准模板产物目录的 glob 模式。
        recursive: 是否递归搜索 ticker 等子工作区。

    Returns:
        按绝对路径字符串排序且去重的路径元组。

    Raises:
        OSError: 当目录状态检查或 glob 遍历失败时。
    """
    resolved_workspace = workspace_root.resolve()
    direct_dir = resolved_workspace / "assets" / _TEMPLATE_DIR_NAME
    paths = set(direct_dir.glob(filename_glob)) if direct_dir.is_dir() else set()
    if recursive and resolved_workspace.is_dir():
        paths.update(resolved_workspace.glob(f"**/assets/{_TEMPLATE_DIR_NAME}/{filename_glob}"))
    return tuple(sorted((path.resolve() for path in paths), key=str))


def _sha256_file(path: Path) -> str:
    """以 1 MiB 分块读取文件并计算 SHA-256 十六进制摘要。

    Args:
        path: 待处理的文件路径。

    Returns:
        64 字符的小写 SHA-256 十六进制摘要。

    Raises:
        OSError: 当目标文件无法打开或读取时。
    """
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json_object(payload: dict[str, object]) -> str:
    """对 JSON 对象按键排序、紧凑编码后计算语义 SHA-256。

    Args:
        payload: 待规范化哈希或解析 source 列表的 JSON 对象。

    Returns:
        规范 JSON 字节的 64 字符 SHA-256 摘要。

    Raises:
        TypeError: 当载荷包含 JSON 无法序列化的值时。
    """
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_map_sources_by_name(
    payload: dict[str, object],
    *,
    label: str,
) -> dict[str, dict[str, object]]:
    """校验 source-map 的 data_sources 列表，并按唯一 source 名建立索引。

    Args:
        payload: 待规范化哈希或解析 source 列表的 JSON 对象。
        label: 用于校验错误消息标识载荷来源的名称。

    Returns:
        source 名到原始 source 对象的映射。

    Raises:
        ValueError: 当 data_sources 非列表，元素非对象，source 为空/重复或 binding_status 非法时。
    """
    data_sources = payload.get("data_sources")
    if not isinstance(data_sources, list):
        raise ValueError(f"{label} data_sources must be a list")
    sources: dict[str, dict[str, object]] = {}
    for index, source in enumerate(data_sources):
        if not isinstance(source, dict):
            raise ValueError(f"{label} data_sources[{index}] must be an object")
        source_name = str(source.get("source", "") or "").strip()
        if not source_name:
            raise ValueError(f"{label} data_sources[{index}].source is required")
        if source_name in sources:
            raise ValueError(f"{label} contains duplicate source: {source_name}")
        binding_status = str(source.get("binding_status", "") or "")
        if binding_status not in {"unbound", "bound"}:
            raise ValueError(f"{label} data_sources[{index}].binding_status must be unbound or bound")
        sources[source_name] = source
    return sources


def _inspect_source_binding_snapshot(
    snapshot_path: Path,
    *,
    source_map_path: Path,
    current_template: str,
    current_source_names: set[str],
    snapshot_type: str,
    filename_marker: str,
) -> dict[str, object]:
    """检查源绑定快照的文件名指纹、模板、源集合与绑定状态。

    Args:
        snapshot_path: 待检查的内容寻址快照文件。
        source_map_path: 当前 source-map 文件，用于验证快照命名。
        current_template: 当前 source-map 声明的模板名。
        current_source_names: 当前 source-map 中的 source 名集合。
        snapshot_type: 写入检查结果的快照类型标签。
        filename_marker: 内容寻址文件名中应包含的用途标记。

    Returns:
        包含快照指纹、绑定摘要、错误列表和 ``ok`` 标志的检查结果。

    Raises:
        OSError: 当快照文件无法读取以计算初始指纹时。
    """
    fingerprint = _sha256_file(snapshot_path)
    expected_name = f"{source_map_path.stem}.{filename_marker}.{fingerprint[:12]}.json"
    errors: list[str] = []
    if snapshot_path.name != expected_name:
        errors.append(f"filename fingerprint mismatch: expected {expected_name!r}")
    binding_status = ""
    bound_sources: list[str] = []
    try:
        payload = _load_json_object(snapshot_path)
        snapshot_template = str(payload.get("template", "") or "").strip()
        if snapshot_template != current_template:
            errors.append(f"template mismatch: source_map={current_template!r} snapshot={snapshot_template!r}")
        snapshot_sources = _source_map_sources_by_name(payload, label="binding snapshot")
        snapshot_source_names = set(snapshot_sources)
        if snapshot_source_names != current_source_names:
            missing = sorted(current_source_names - snapshot_source_names)
            extra = sorted(snapshot_source_names - current_source_names)
            errors.append(f"source set mismatch: missing={missing} extra={extra}")
        binding_status = str(payload.get("binding_status", "") or "")
        bound_sources = sorted(
            source_name for source_name, source in snapshot_sources.items() if source.get("binding_status") == "bound"
        )
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "snapshot_file": str(snapshot_path),
        "snapshot_type": snapshot_type,
        "fingerprint": fingerprint,
        "binding_status": binding_status,
        "bound_sources": bound_sources,
        "ok": not errors,
        "errors": errors,
    }
