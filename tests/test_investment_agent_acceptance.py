"""刻画投资 Agent AAPL 固定验收语料与现有生产 owner 契约。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypeAlias

import pytest

from dayu.cli.commands._research_template_materialize import (
    _materialization_artifact_paths,
    materialize_research_template_bundle,
)
from dayu.cli.commands._research_template_monitoring import (
    build_monitoring_execution_plan,
    validate_monitoring_execution_plan,
)
from dayu.cli.commands.research_workbook import build_research_workbook_payload
from dayu.services.contracts import SceneModelConfig, WriteRunConfig
from dayu.services.internal.write_pipeline.execution_summary_builder import ExecutionSummaryBuilder
from dayu.services.internal.write_pipeline.models import ChapterResult, RunManifest

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "investment_agent" / "aapl_acceptance"
_JSON_FIXTURE_SHA256 = {
    "contract-v1.json": "60a7e0dfdccd35120542b7018b46924c34a5fe97027cff8fb533d8d3e5a07cd4",
    "price-snapshot-v1.json": "6c8da51d65063576597534880986a4093568b70e3d69dce83c6909e2bb388a50",
    "quality-review-v1.json": "90ac48387253599e6d025ab287fa169e815cc1d0f4e5ec62cdc72d1bb1ca3bd8",
    "run-summary-v1.json": "d3fdfacc5df7c8519586e01c5c2c78770c4f39b1da42a7d3986602b4510e3fa4",
    "source-inventory-v1.json": "9a014eb569d9f0841c14bf84e6911b37ba802e96199303e8e0e229c0454478d5",
    "write-manifest-v1.json": "066d398d7c651b2b16ff230be6ee33f640f3ee160a6d6fb2e2dac20c5a1cb16f",
}
_REPORT_SHA256 = "4b256afc6fcae8d3ed543654c0a24f2ef0579a0b18ee70b7dad46bdd75914796"
_WORKBOOK_CATEGORIES = {
    "research_question",
    "business_analysis",
    "evidence_requirement",
    "monitoring_variable",
    "falsifier",
    "synthesis",
    "valuation",
    "catalyst",
    "management_governance",
    "portfolio_decision",
}
_RESEARCH_ARTIFACT_NAMES = [
    "common-plus-technology.md",
    "technology.research-workbook.json",
    "technology.research-progress.md",
    "technology.monitoring-rules.json",
    "technology.source-map.json",
    "research-template.manifest.json",
    "technology.research-guide.md",
    "technology.checklist.md",
    "technology.bundle.json",
    "technology.monitoring-plan.json",
    "monitoring-status.json",
    "research-workbook-status.json",
    "research-workbook-report-status.json",
]
_DOCUMENT_KEYS = {
    "document_id",
    "source_kind",
    "form",
    "filing_date",
    "report_date",
    "fiscal_year",
    "fiscal_period",
    "accession",
    "source_locator",
    "primary_file_sha256",
    "ingest_complete",
    "processed",
    "processed_state_fingerprint",
}
_PROCESSED_KEYS = {
    "exists",
    "parser_version",
    "quality",
    "reprocess_required",
    "schema_version",
    "source_fingerprint",
}
# 以下常量只锁定 Slice 0 fixture 的已接受语义；Slice 1 evaluator 必须解析
# contract fixture 本身，不能把这些测试期望复制成第二套生产枚举。
_EXPECTED_HARD_GATES = (
    "run_summary_passed",
    "audit_complete",
    "dual_model_roles_closed",
    "budget_within_limits",
    "research_artifacts_valid",
    "workbook_progress_valid",
    "monitoring_safe",
    "source_price_closed",
    "acceptance_outputs_sanitized",
    "manual_review_passed",
)
_EXPECTED_DIMENSION_MINIMUMS = {
    "source_traceability": 20,
    "investment_research_completeness": 24,
    "evidence_reasoning_quality": 20,
    # 后两维的 0 是有意表示“不设独立 hard minimum”，而不是待填占位。
    "reproducibility_recovery": 0,
    "run_governance": 0,
}
_EXPECTED_REQUIRED_TOPICS = (
    "thesis",
    "bear_case",
    "valuation",
    "catalyst",
    "risk",
)
_EXPECTED_EVIDENCE_PARTS = (
    "source",
    "type_or_identifier",
    "date",
    "locator",
)
_REPORT_HEADING_BY_TOPIC = {
    "thesis": "## 投资主线（thesis）",
    "bear_case": "## Bear case 与反证",
    "valuation": "## 估值（valuation）",
    "catalyst": "## 催化剂（catalyst）",
    "risk": "## 风险（risk）",
}


def _load_json_fixture(name: str) -> dict[str, JsonValue]:
    """读取一个固定 JSON fixture。

    Args:
        name: fixture 文件名。

    Returns:
        JSON 顶层对象。

    Raises:
        OSError: 文件读取失败时抛出。
        json.JSONDecodeError: fixture 不是合法 JSON 时抛出。
        AssertionError: JSON 顶层不是对象时抛出。
    """
    payload: JsonValue = json.loads((_FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{name} 顶层必须是对象"
    return payload


def _require_mapping(value: JsonValue, *, label: str) -> dict[str, JsonValue]:
    """把已解析 JSON 值收窄为对象。

    Args:
        value: 待收窄的 JSON 值。
        label: 断言失败时使用的字段标签。

    Returns:
        已验证的 JSON 对象。

    Raises:
        AssertionError: 值不是对象时抛出。
    """
    assert isinstance(value, dict), f"{label} 必须是对象"
    return value


def _require_list(value: JsonValue, *, label: str) -> list[JsonValue]:
    """把已解析 JSON 值收窄为数组。

    Args:
        value: 待收窄的 JSON 值。
        label: 断言失败时使用的字段标签。

    Returns:
        已验证的 JSON 数组。

    Raises:
        AssertionError: 值不是数组时抛出。
    """
    assert isinstance(value, list), f"{label} 必须是数组"
    return value


def _canonical_json_bytes(payload: dict[str, JsonValue]) -> bytes:
    """按验收 contract 的固定规则生成 canonical JSON 字节。

    Args:
        payload: 待序列化的 JSON 对象。

    Returns:
        UTF-8 编码、键排序且无多余空白的 JSON 字节。

    Raises:
        ValueError: 载荷包含 NaN 或其它非标准浮点数时抛出。
        TypeError: 载荷包含不可序列化值时抛出。
    """
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    """计算字节载荷的 SHA-256。

    Args:
        payload: 待计算的字节载荷。

    Returns:
        小写十六进制 SHA-256。

    Raises:
        本函数不显式抛出异常。
    """
    return hashlib.sha256(payload).hexdigest()


def _chapter_passed(result: ChapterResult | None) -> bool:
    """判断生产运行摘要测试中的章节是否通过门禁。

    Args:
        result: 可选章节结果。

    Returns:
        章节存在、状态通过且审计通过时返回 ``True``。

    Raises:
        本函数不显式抛出异常。
    """
    return bool(result is not None and result.status == "passed" and result.audit_passed)


@pytest.mark.unit
def test_fixture_files_have_strict_shapes_and_stable_canonical_serialization() -> None:
    """验证全部固定语料的字段闭包与 canonical 指纹稳定。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一 fixture 漂移、增删字段或失去 canonical 稳定性时抛出。
        OSError: fixture 无法读取时抛出。
        json.JSONDecodeError: fixture 不是合法 JSON 时抛出。
    """
    assert {path.name for path in _FIXTURE_ROOT.iterdir()} == {
        *_JSON_FIXTURE_SHA256,
        "report-v1.md",
    }
    for name, expected_sha256 in _JSON_FIXTURE_SHA256.items():
        payload = _load_json_fixture(name)
        canonical = _canonical_json_bytes(payload)
        assert _sha256_bytes(canonical) == expected_sha256
        reparsed: JsonValue = json.loads(canonical)
        assert isinstance(reparsed, dict)
        assert _canonical_json_bytes(reparsed) == canonical
    assert _sha256_bytes((_FIXTURE_ROOT / "report-v1.md").read_bytes()) == _REPORT_SHA256

    contract = _load_json_fixture("contract-v1.json")
    assert set(contract) == {
        "schema_version",
        "contract_type",
        "fixture_id",
        "target",
        "fixture_policy",
        "model_roles",
        "report_contract",
        "score_contract",
        "hard_gates",
        "required_research_artifacts",
    }
    assert set(_require_mapping(contract["target"], label="contract.target")) == {
        "ticker",
        "company",
        "research_template",
    }
    assert set(_require_mapping(contract["fixture_policy"], label="contract.fixture_policy")) == {
        "deterministic",
        "external_calls_allowed",
        "live_freshness_claimed",
    }
    assert set(_require_mapping(contract["model_roles"], label="contract.model_roles")) == {
        "primary",
        "audit",
    }
    report_contract = _require_mapping(contract["report_contract"], label="contract.report_contract")
    assert set(report_contract) == {
        "required_topics",
        "required_evidence_parts",
        "valuation_reference_price",
    }
    score_contract = _require_mapping(contract["score_contract"], label="contract.score_contract")
    assert set(score_contract) == {"total_points", "minimum_total_score", "dimension_minimums"}
    assert _require_mapping(
        score_contract["dimension_minimums"],
        label="contract.score_contract.dimension_minimums",
    ) == _EXPECTED_DIMENSION_MINIMUMS
    hard_gates = _require_list(contract["hard_gates"], label="contract.hard_gates")
    assert hard_gates == list(_EXPECTED_HARD_GATES)
    assert len(hard_gates) == len(set(hard_gates)) == len(_EXPECTED_HARD_GATES)
    assert _require_list(
        report_contract["required_topics"],
        label="contract.report_contract.required_topics",
    ) == list(_EXPECTED_REQUIRED_TOPICS)
    assert _require_list(
        report_contract["required_evidence_parts"],
        label="contract.report_contract.required_evidence_parts",
    ) == list(_EXPECTED_EVIDENCE_PARTS)
    assert _require_list(
        contract["required_research_artifacts"],
        label="contract.required_research_artifacts",
    ) == _RESEARCH_ARTIFACT_NAMES

    price = _load_json_fixture("price-snapshot-v1.json")
    assert set(price) == {"price", "currency", "market_date", "source_url", "captured_at", "max_age_days"}

    inventory = _load_json_fixture("source-inventory-v1.json")
    assert set(inventory) == {
        "schema_version",
        "inventory_type",
        "fixture_id",
        "ticker",
        "company",
        "as_of",
        "live_freshness_claimed",
        "source_windows",
        "latest_discovery",
        "documents",
    }
    source_windows = _require_list(inventory["source_windows"], label="inventory.source_windows")
    assert len(source_windows) == 3
    for index, window_value in enumerate(source_windows):
        window = _require_mapping(window_value, label=f"inventory.source_windows[{index}]")
        assert set(window) == {"forms", "start_date", "end_date"}
    documents = _require_list(inventory["documents"], label="inventory.documents")
    assert len(documents) == 4
    for index, document_value in enumerate(documents):
        document = _require_mapping(document_value, label=f"inventory.documents[{index}]")
        assert set(document) == _DOCUMENT_KEYS
        assert document["ingest_complete"] is True
        assert isinstance(document["primary_file_sha256"], str)
        assert len(document["primary_file_sha256"]) == 64
        processed = _require_mapping(document["processed"], label=f"inventory.documents[{index}].processed")
        assert set(processed) == _PROCESSED_KEYS
        assert processed["exists"] is True
        assert processed["reprocess_required"] is False
        assert isinstance(processed["source_fingerprint"], str)
        assert len(processed["source_fingerprint"]) == 64
        assert document["processed_state_fingerprint"] == _sha256_bytes(_canonical_json_bytes(processed))

    quality_review = _load_json_fixture("quality-review-v1.json")
    assert set(quality_review) == {
        "schema_version",
        "review_type",
        "fixture_id",
        "reviewer_role",
        "reviewer_id_label",
        "status",
        "dimensions",
        "total_score",
        "finding_counts",
        "findings",
        "completed_at",
    }
    dimensions = _require_mapping(quality_review["dimensions"], label="quality_review.dimensions")
    assert set(dimensions) == {
        "source_traceability",
        "investment_research_completeness",
        "evidence_reasoning_quality",
        "reproducibility_recovery",
        "run_governance",
    }
    for dimension_name, dimension_value in dimensions.items():
        dimension = _require_mapping(dimension_value, label=f"quality_review.dimensions.{dimension_name}")
        assert set(dimension) == {"score", "max_score", "items"}
        items = _require_list(dimension["items"], label=f"quality_review.dimensions.{dimension_name}.items")
        assert items
        for item_index, item_value in enumerate(items):
            item = _require_mapping(
                item_value,
                label=f"quality_review.dimensions.{dimension_name}.items[{item_index}]",
            )
            assert set(item) == {"item_id", "score", "max_score", "evidence_paths", "notes"}
            assert _require_list(item["evidence_paths"], label=f"{dimension_name}.evidence_paths")
            assert isinstance(item["notes"], str) and item["notes"]

    manifest = _load_json_fixture("write-manifest-v1.json")
    assert set(manifest) == {"version", "signature", "config", "chapter_results", "company_facets"}
    config = _require_mapping(manifest["config"], label="manifest.config")
    assert set(config) == {
        "ticker",
        "company",
        "template_path",
        "output_dir",
        "write_max_retries",
        "web_provider",
        "resume",
        "write_model_override_name",
        "audit_model_override_name",
        "write_fallback_model_name",
        "audit_fallback_model_name",
        "scene_models",
        "scene_fallback_models",
        "chapter_filter",
        "fast",
        "force",
        "infer",
        "research_template_requested_name",
        "research_template_resolved_name",
        "research_template_selection_mode",
        "write_max_model_requests",
        "write_max_total_tokens",
        "write_max_estimated_cost",
        "write_budget_currency",
    }
    chapter_results = _require_mapping(manifest["chapter_results"], label="manifest.chapter_results")
    assert len(chapter_results) == 5
    for chapter_title, chapter_value in chapter_results.items():
        chapter = _require_mapping(chapter_value, label=f"manifest.chapter_results.{chapter_title}")
        assert set(chapter) == {
            "index",
            "title",
            "status",
            "content",
            "audit_passed",
            "retry_count",
            "failure_reason",
            "evidence_items",
            "process_state",
        }
        process_state = _require_mapping(chapter["process_state"], label=f"{chapter_title}.process_state")
        assert set(process_state) == {
            "final_stage",
            "audit_history",
            "confirm_history",
            "anchor_rewrite_history",
        }

    run_summary = _load_json_fixture("run-summary-v1.json")
    assert set(run_summary) == {
        "schema_version",
        "completed_at",
        "ticker",
        "output_file",
        "gate_status",
        "publication_status",
        "model_roles",
        "model_usage",
        "model_routing",
        "budget",
        "chapter_count",
        "failed_count",
        "failed_chapters",
        "audit",
        "chapters",
    }
    assert set(_require_mapping(run_summary["model_roles"], label="run_summary.model_roles")) == {
        "primary",
        "audit",
    }
    assert "usage_status" in _require_mapping(run_summary["model_usage"], label="run_summary.model_usage")
    assert set(_require_mapping(run_summary["model_routing"], label="run_summary.model_routing")) == {
        "fallback_switch_count",
        "fallback_call_completed_count",
        "fallback_call_error_count",
        "routes",
    }
    assert set(_require_mapping(run_summary["budget"], label="run_summary.budget")) == {
        "enabled",
        "status",
        "enforcement",
        "limits",
        "usage",
        "active_reservation_count",
        "projection",
        "block",
    }
    assert set(_require_mapping(run_summary["audit"], label="run_summary.audit")) == {
        "required",
        "passed_count",
        "failed_count",
        "skipped_count",
        "gate_blocked_count",
        "first_pass_count",
        "repaired_pass_count",
        "total_retries",
        "audit_attempt_count",
        "confirmation_check_count",
        "anchor_rewrite_count",
    }


@pytest.mark.unit
def test_fixture_contract_is_aapl_technology_85_point_pass_with_closed_sources() -> None:
    """验证固定语料覆盖五类研究内容、四段引用和精确估值价格闭环。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: contract、评分、报告或来源闭环不一致时抛出。
        OSError: fixture 无法读取时抛出。
        json.JSONDecodeError: fixture 不是合法 JSON 时抛出。
    """
    contract = _load_json_fixture("contract-v1.json")
    target = _require_mapping(contract["target"], label="contract.target")
    policy = _require_mapping(contract["fixture_policy"], label="contract.fixture_policy")
    score_contract = _require_mapping(contract["score_contract"], label="contract.score_contract")
    assert target == {"ticker": "AAPL", "company": "Apple Inc.", "research_template": "technology"}
    assert policy == {
        "deterministic": True,
        "external_calls_allowed": False,
        "live_freshness_claimed": False,
    }
    assert score_contract["total_points"] == 100
    assert score_contract["minimum_total_score"] == 85
    dimension_minimums = _require_mapping(
        score_contract["dimension_minimums"],
        label="contract.score_contract.dimension_minimums",
    )
    assert dimension_minimums == _EXPECTED_DIMENSION_MINIMUMS

    quality_review = _load_json_fixture("quality-review-v1.json")
    dimensions = _require_mapping(quality_review["dimensions"], label="quality_review.dimensions")
    assert set(dimensions) == set(dimension_minimums)
    dimension_score_total = 0
    dimension_max_total = 0
    for dimension_name, dimension_value in dimensions.items():
        dimension = _require_mapping(dimension_value, label=f"quality_review.dimensions.{dimension_name}")
        dimension_score = dimension["score"]
        dimension_max_score = dimension["max_score"]
        dimension_minimum = dimension_minimums[dimension_name]
        assert isinstance(dimension_score, int) and not isinstance(dimension_score, bool)
        assert isinstance(dimension_max_score, int) and not isinstance(dimension_max_score, bool)
        assert isinstance(dimension_minimum, int) and not isinstance(dimension_minimum, bool)
        assert dimension_score >= dimension_minimum
        items = _require_list(dimension["items"], label=f"quality_review.dimensions.{dimension_name}.items")
        item_score_total = 0
        item_max_total = 0
        for item_index, item_value in enumerate(items):
            item = _require_mapping(
                item_value,
                label=f"quality_review.dimensions.{dimension_name}.items[{item_index}]",
            )
            item_score = item["score"]
            item_max_score = item["max_score"]
            assert isinstance(item_score, int) and not isinstance(item_score, bool)
            assert isinstance(item_max_score, int) and not isinstance(item_max_score, bool)
            item_score_total += item_score
            item_max_total += item_max_score
        assert item_score_total == dimension_score
        assert item_max_total == dimension_max_score
        dimension_score_total += dimension_score
        dimension_max_total += dimension_max_score
    assert dimension_score_total == quality_review["total_score"] == 85
    assert dimension_max_total == score_contract["total_points"] == 100
    assert quality_review["status"] == "PASS"
    finding_counts = _require_mapping(quality_review["finding_counts"], label="quality_review.finding_counts")
    assert finding_counts["high"] == finding_counts["medium"] == 0

    price = _load_json_fixture("price-snapshot-v1.json")
    report_contract = _require_mapping(contract["report_contract"], label="contract.report_contract")
    required_topics = _require_list(
        report_contract["required_topics"],
        label="contract.report_contract.required_topics",
    )
    required_evidence_parts = _require_list(
        report_contract["required_evidence_parts"],
        label="contract.report_contract.required_evidence_parts",
    )
    assert required_topics == list(_EXPECTED_REQUIRED_TOPICS)
    assert required_evidence_parts == list(_EXPECTED_EVIDENCE_PARTS)
    reference_price = _require_mapping(
        report_contract["valuation_reference_price"],
        label="contract.report_contract.valuation_reference_price",
    )
    assert {key: price[key] for key in ("price", "currency", "market_date")} == {
        key: reference_price[key] for key in ("price", "currency", "market_date")
    }

    report = (_FIXTURE_ROOT / "report-v1.md").read_text(encoding="utf-8")
    assert set(_REPORT_HEADING_BY_TOPIC) == set(required_topics)
    for topic_value in required_topics:
        assert isinstance(topic_value, str)
        assert _REPORT_HEADING_BY_TOPIC[topic_value] in report
    expected_reference_record = (
        'valuation_reference_price: {"price":"236.85","currency":"USD",'
        '"market_date":"2025-01-15",'
        '"material_document_id":"material-aapl-price-snapshot-2025-01-15"}'
    )
    assert report.count("valuation_reference_price:") == 1
    assert expected_reference_record in report
    assert "不声明实时性" in report

    report_body, source_list = report.split("## 来源清单", maxsplit=1)
    body_citations = [line for line in report_body.splitlines() if line.startswith("- ")]
    source_entries = [line for line in source_list.splitlines() if line.startswith("- ")]
    assert body_citations and source_entries
    citations = body_citations + source_entries
    assert all(
        len(line.removeprefix("- ").split(" | ")) == len(required_evidence_parts)
        for line in citations
    )
    evidence_document_ids = {
        line.removeprefix("- ").split(" | ", maxsplit=1)[0] for line in body_citations
    }
    source_list_document_ids = {
        line.removeprefix("- ").split(" | ", maxsplit=1)[0] for line in source_entries
    }
    inventory = _load_json_fixture("source-inventory-v1.json")
    inventory_documents = _require_list(inventory["documents"], label="inventory.documents")
    inventory_by_document_id: dict[str, dict[str, JsonValue]] = {}
    for document_value in inventory_documents:
        document = _require_mapping(document_value, label="inventory.document")
        document_id = document["document_id"]
        assert isinstance(document_id, str) and document_id
        inventory_by_document_id[document_id] = document
    inventory_document_ids = set(inventory_by_document_id)
    assert inventory["live_freshness_claimed"] is False
    assert evidence_document_ids <= source_list_document_ids == inventory_document_ids

    as_of_value = inventory["as_of"]
    assert isinstance(as_of_value, str)
    as_of_date = datetime.fromisoformat(as_of_value.replace("Z", "+00:00")).date()
    for citation in citations:
        document_id, type_or_identifier, citation_date_text, _locator = citation.removeprefix("- ").split(" | ")
        assert date.fromisoformat(citation_date_text) <= as_of_date
        document = inventory_by_document_id[document_id]
        if document["source_kind"] == "filing":
            form = document["form"]
            accession = document["accession"]
            assert isinstance(form, str) and form
            assert isinstance(accession, str) and accession
            assert type_or_identifier == f"{form} / {accession}"

    latest_discovery = _require_mapping(inventory["latest_discovery"], label="inventory.latest_discovery")
    for form, latest_accession in latest_discovery.items():
        matching_filings = [
            document
            for document in inventory_by_document_id.values()
            if document["source_kind"] == "filing" and document["form"] == form
        ]
        assert len(matching_filings) == 1
        assert matching_filings[0]["accession"] == latest_accession


@pytest.mark.unit
def test_write_manifest_fixture_is_accepted_by_current_production_owner() -> None:
    """验证固定 write manifest 可由现有生产模型无兼容分支地恢复。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 恢复后的 AAPL/technology/双模型契约不闭合时抛出。
        OSError: fixture 无法读取时抛出。
        json.JSONDecodeError: fixture 不是合法 JSON 时抛出。
        KeyError: manifest 缺少生产 owner 必填字段时抛出。
        TypeError: manifest 字段类型不符合生产 owner 契约时抛出。
    """
    raw_manifest = json.loads((_FIXTURE_ROOT / "write-manifest-v1.json").read_text(encoding="utf-8"))
    manifest = RunManifest.from_dict(raw_manifest)

    assert manifest.version == "write_manifest_v1"
    assert manifest.config.ticker == "AAPL"
    assert manifest.config.research_template_requested_name == "technology"
    assert manifest.config.research_template_resolved_name == "technology"
    assert manifest.config.research_template_selection_mode == "named"
    assert manifest.config.scene_models["write"].name == "deepseek-v4-pro"
    assert manifest.config.scene_models["audit"].name == "mimo-v2.5-pro-thinking"
    assert len(manifest.chapter_results) == 5
    assert all(chapter.status == "passed" and chapter.audit_passed for chapter in manifest.chapter_results.values())


@pytest.mark.unit
def test_technology_workbook_owner_has_ten_categories_and_37_items() -> None:
    """直接刻画 production owner 生成的 technology 工作簿规模。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: technology 工作簿不再是 10 类、37 项时抛出。
        FileNotFoundError: packaged technology 模板不存在时抛出。
        OSError: packaged technology 模板读取失败时抛出。
        ValueError: packaged technology 模板没有可执行章节时抛出。
    """
    workbook = build_research_workbook_payload("technology", ticker="AAPL", company="Apple Inc.")
    summary_value = workbook["summary"]
    assert isinstance(summary_value, dict)
    category_counts = summary_value["category_counts"]
    assert isinstance(category_counts, dict)

    assert set(category_counts) == _WORKBOOK_CATEGORIES
    assert len(category_counts) == 10
    assert sum(int(count) for count in category_counts.values()) == 37
    assert summary_value["item_count"] == 37
    assert summary_value["open_item_count"] == 37


@pytest.mark.unit
def test_materialization_owner_protects_exactly_thirteen_artifacts(tmp_path: Path) -> None:
    """直接刻画 production materializer 的 13 产物回滚边界。

    Args:
        tmp_path: pytest 提供的隔离临时目录。

    Returns:
        无。

    Raises:
        AssertionError: owner 的受保护路径数量、顺序或名称漂移时抛出。
    """
    artifact_paths = _materialization_artifact_paths(tmp_path, "technology")

    assert len(artifact_paths) == len(set(artifact_paths)) == 13
    assert [path.name for path in artifact_paths] == _RESEARCH_ARTIFACT_NAMES
    assert all(path.parent == (tmp_path / "assets" / "research_templates").resolve() for path in artifact_paths)


@pytest.mark.unit
def test_monitoring_owner_forces_dry_run_and_disables_automation(tmp_path: Path) -> None:
    """直接刻画 monitoring owner 的 dry-run 与禁止自动执行安全边界。

    Args:
        tmp_path: pytest 提供的隔离临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 生成器或 validator 不再强制安全开关时抛出。
        OSError: 本地物化产物无法读写时抛出。
        ValueError: 本地 bundle 或 monitoring plan 不健康时抛出。
    """
    materialized = materialize_research_template_bundle(
        "technology",
        workspace_root=tmp_path,
        ticker="AAPL",
        company="Apple Inc.",
    )
    plan = build_monitoring_execution_plan(Path(str(materialized["bundle_file"])))

    assert plan["execution_mode"] == "dry_run"
    assert plan["automated_execution_allowed"] is False
    valid_result = validate_monitoring_execution_plan(plan)
    assert valid_result["ok"] is True
    assert valid_result["errors"] == []

    unsafe_automation = dict(plan)
    unsafe_automation["automated_execution_allowed"] = True
    unsafe_automation_result = validate_monitoring_execution_plan(unsafe_automation)
    assert unsafe_automation_result["ok"] is False
    unsafe_automation_errors = unsafe_automation_result["errors"]
    assert isinstance(unsafe_automation_errors, list)
    assert "automated_execution_allowed must be false" in unsafe_automation_errors
    unsafe_mode = dict(plan)
    unsafe_mode["execution_mode"] = "live"
    unsafe_mode_result = validate_monitoring_execution_plan(unsafe_mode)
    assert unsafe_mode_result["ok"] is False
    unsafe_mode_errors = unsafe_mode_result["errors"]
    assert isinstance(unsafe_mode_errors, list)
    assert "execution_mode must be dry_run" in unsafe_mode_errors


@pytest.mark.unit
def test_run_summary_v3_owner_includes_budget_usage_and_audit() -> None:
    """直接刻画 production run summary v3 的预算、usage 与审计字段。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: v3 owner 不再保留预算、usage 或审计 receipt 时抛出。
        ValueError: 固定完成时间不带时区时抛出。
    """
    config = WriteRunConfig(
        ticker="AAPL",
        company="Apple Inc.",
        template_path="dayu/assets/定性分析模板.md",
        output_dir="write",
        write_max_retries=2,
        web_provider="auto",
        resume=False,
        scene_models={
            "write": SceneModelConfig(name="deepseek-v4-pro", temperature=1.0),
            "audit": SceneModelConfig(name="mimo-v2.5-pro-thinking", temperature=0.2),
        },
    )
    model_usage = {
        "usage_status": "complete",
        "scene_call_count": 2,
        "total_tokens": 120,
    }
    budget = {
        "enabled": True,
        "status": "within_budget",
        "block": None,
    }
    summary = ExecutionSummaryBuilder(write_config=config).build_summary(
        {
            "投资主线": ChapterResult(
                index=1,
                title="投资主线",
                status="passed",
                content="fixture",
                audit_passed=True,
                process_state={"audit_history": [{"phase": "initial"}], "final_stage": "complete"},
            )
        },
        output_file=Path("write/AAPL_qual_report.md"),
        success_predicate=_chapter_passed,
        model_usage=model_usage,
        budget=budget,
        completed_at=datetime(2025, 1, 16, tzinfo=UTC),
    )

    assert summary["schema_version"] == "write_run_summary_v3"
    assert summary["gate_status"] == "passed"
    assert summary["publication_status"] == "published"
    assert summary["model_usage"] == model_usage
    assert summary["budget"] == budget
    audit = summary["audit"]
    assert isinstance(audit, dict)
    assert audit["required"] is True
    assert audit["passed_count"] == 1
    assert audit["failed_count"] == 0
    assert audit["skipped_count"] == 0

    fixture_summary = _load_json_fixture("run-summary-v1.json")
    assert set(summary) == set(fixture_summary)
    fixture_audit = _require_mapping(fixture_summary["audit"], label="fixture_summary.audit")
    assert set(audit) == set(fixture_audit)

    owner_chapters = summary["chapters"]
    assert isinstance(owner_chapters, list) and owner_chapters
    owner_first_chapter = owner_chapters[0]
    assert isinstance(owner_first_chapter, dict)
    fixture_chapters = _require_list(fixture_summary["chapters"], label="fixture_summary.chapters")
    fixture_first_chapter = _require_mapping(fixture_chapters[0], label="fixture_summary.chapters[0]")
    assert set(owner_first_chapter) == set(fixture_first_chapter)

    owner_routing = summary["model_routing"]
    assert isinstance(owner_routing, dict)
    fixture_routing = _require_mapping(fixture_summary["model_routing"], label="fixture_summary.model_routing")
    assert set(owner_routing) == set(fixture_routing)

    owner_roles = summary["model_roles"]
    assert isinstance(owner_roles, dict)
    fixture_roles = _require_mapping(fixture_summary["model_roles"], label="fixture_summary.model_roles")
    assert set(owner_roles) == set(fixture_roles)
    for role_name in ("primary", "audit"):
        owner_role = owner_roles[role_name]
        assert isinstance(owner_role, dict)
        fixture_role = _require_mapping(fixture_roles[role_name], label=f"fixture_summary.model_roles.{role_name}")
        assert set(owner_role) == set(fixture_role)
        owner_scenes = owner_role["scenes"]
        fixture_scenes = _require_list(fixture_role["scenes"], label=f"fixture_summary.{role_name}.scenes")
        assert isinstance(owner_scenes, list) and owner_scenes
        assert fixture_scenes
        assert isinstance(owner_scenes[0], dict)
        assert set(owner_scenes[0]) == set(
            _require_mapping(fixture_scenes[0], label=f"fixture_summary.{role_name}.scenes[0]")
        )
