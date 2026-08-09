"""刻画投资 Agent AAPL 固定验收语料与现有生产 owner 契约。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypeAlias
from unittest.mock import create_autospec

import pytest

from dayu.cli.commands._research_template_materialize import (
    _materialization_artifact_paths,
    materialize_research_template_bundle,
    materialize_research_workspace,
)
from dayu.cli.commands._research_template_monitoring import (
    build_monitoring_execution_plan,
    validate_monitoring_execution_plan,
)
from dayu.cli.commands.research_workbook import build_research_workbook_payload
from dayu.contracts.model_usage import ModelUsage
from dayu.fins.domain.document_models import FileObjectMeta, SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import (
    DocumentBlobRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.services.contracts import SceneModelConfig, WriteRunConfig
from dayu.services.internal.write_pipeline.execution_summary_builder import ExecutionSummaryBuilder
from dayu.services.internal.write_pipeline.model_usage_ledger import WriteModelUsageLedger
from dayu.services.internal.write_pipeline.models import ChapterResult, RunManifest
from dayu.startup.config_file_resolver import resolve_package_assets_path, resolve_package_config_path
from utils import investment_agent_acceptance_contracts as acceptance_contracts_module
from utils import investment_agent_acceptance_evaluator as acceptance_evaluator_module
from utils.investment_agent_acceptance_contracts import (
    REQUIRED_RESEARCH_ARTIFACTS,
    AcceptancePlan,
    BudgetLimits,
    ContractError,
    FingerprintDriftError,
    PhaseReceipt,
    ProcessedState,
    SourceWindow,
    assert_package_input_fingerprints,
    build_package_input_fingerprints,
    canonical_json_sha256,
    parse_acceptance_contract,
    parse_acceptance_plan,
    parse_acceptance_receipt,
    parse_json_bytes,
    parse_owner_run_summary,
    parse_phase_receipt,
)
from utils.investment_agent_acceptance_evaluator import (
    AcceptanceInputs,
    FixtureInputRequest,
    RepositoryInventoryRequest,
    build_source_inventory_from_repositories,
    evaluate_acceptance,
    inspect_research_artifacts,
    load_fixture_inputs,
)

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
_RESEARCH_ARTIFACT_NAMES = list(REQUIRED_RESEARCH_ARTIFACTS)
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
_APPROVED_BUDGET = BudgetLimits(
    max_model_requests=20,
    max_total_tokens=200_000,
    max_estimated_cost=Decimal("5.0"),
    budget_currency="CNY",
)
_FIXED_EVALUATED_AT = datetime(2025, 2, 1, 1, 0, tzinfo=UTC)
_MAX_WALL_SECONDS = 3_600
_ACTUAL_WALL_SECONDS = 120.0
_ACCEPTANCE_ARTIFACT_PREFIX = "research/assets/research_templates"


def _materialize_acceptance_artifacts(tmp_path: Path) -> Path:
    """在临时目录物化真实 technology 13 产物。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        ``assets/research_templates`` 产物目录。

    Raises:
        OSError: owner 写入产物失败时抛出。
        ValueError: owner validator 拒绝物化结果时抛出。
    """

    materialize_research_workspace(
        "technology",
        workspace_root=tmp_path,
        ticker="AAPL",
        company="Apple Inc.",
    )
    return tmp_path / "assets" / "research_templates"


def _load_acceptance_inputs(
    tmp_path: Path,
    *,
    acceptance_owned_outputs: tuple[JsonValue, ...] = (),
) -> AcceptanceInputs:
    """构造一个真实 13 产物支持的 happy evaluator 输入。

    Args:
        tmp_path: pytest 隔离目录。
        acceptance_owned_outputs: 仅供 sanitizer 检查的验收自有 JSON。

    Returns:
        完整严格 evaluator 输入。

    Raises:
        OSError: fixture 或临时研究产物读取失败时抛出。
        ContractError: fixture 或产物 contract 非法时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    return _load_acceptance_inputs_from_artifacts(
        artifact_root,
        acceptance_owned_outputs=acceptance_owned_outputs,
    )


def _load_acceptance_inputs_from_artifacts(
    artifact_root: Path,
    *,
    acceptance_owned_outputs: tuple[JsonValue, ...] = (),
    expected_artifact_sha256: tuple[tuple[str, str], ...] = (),
) -> AcceptanceInputs:
    """从一个已物化产物目录加载 evaluator 输入。

    Args:
        artifact_root: 精确研究产物目录。
        acceptance_owned_outputs: 仅供 sanitizer 检查的验收自有 JSON。
        expected_artifact_sha256: 可选的 artifact 绑定摘要。

    Returns:
        完整严格 evaluator 输入。

    Raises:
        OSError: fixture 或产物读取失败时抛出。
        ContractError: fixture 或产物 contract 非法时抛出。
    """

    return load_fixture_inputs(
        FixtureInputRequest(
            fixture_root=_FIXTURE_ROOT,
            artifact_root=artifact_root,
            approved_budget=_APPROVED_BUDGET,
            max_wall_seconds=_MAX_WALL_SECONDS,
            actual_wall_seconds=_ACTUAL_WALL_SECONDS,
            acceptance_owned_outputs=acceptance_owned_outputs,
            expected_artifact_sha256=expected_artifact_sha256,
        )
    )


def _finding_codes(inputs: AcceptanceInputs) -> set[str]:
    """执行固定时钟 evaluator 并返回 finding code 集合。

    Args:
        inputs: 严格 evaluator 输入。

    Returns:
        finding code 集合。

    Raises:
        ContractError: evaluator receipt 生成失败时抛出。
    """

    return {item.code for item in evaluate_acceptance(inputs, evaluated_at=_FIXED_EVALUATED_AT).findings}


def _drop_markdown_section(report: str, heading: str) -> str:
    """从测试报告删除一个二级 Markdown 章节。

    Args:
        report: 原报告文本。
        heading: 不含 ``##`` 的精确标题。

    Returns:
        删除目标章节后的文本。

    Raises:
        AssertionError: 目标章节不存在时抛出。
    """

    marker = f"## {heading}"
    before, separator, after = report.partition(marker)
    assert separator
    _section, next_separator, remainder = after.partition("\n## ")
    return before + (f"\n## {remainder}" if next_separator else "")


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
    assert (
        _require_mapping(
            score_contract["dimension_minimums"],
            label="contract.score_contract.dimension_minimums",
        )
        == _EXPECTED_DIMENSION_MINIMUMS
    )
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
    assert (
        _require_list(
            contract["required_research_artifacts"],
            label="contract.required_research_artifacts",
        )
        == _RESEARCH_ARTIFACT_NAMES
    )

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
    assert all(len(line.removeprefix("- ").split(" | ")) == len(required_evidence_parts) for line in citations)
    evidence_document_ids = {line.removeprefix("- ").split(" | ", maxsplit=1)[0] for line in body_citations}
    source_list_document_ids = {line.removeprefix("- ").split(" | ", maxsplit=1)[0] for line in source_entries}
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


@pytest.mark.unit
def test_slice1_evaluator_happy_fixture_passes_and_receipt_is_byte_stable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 happy fixture 精确 PASS、85 分且固定时钟 receipt 字节稳定。

    Args:
        tmp_path: pytest 隔离目录。
        capsys: pytest 标准输出捕获器。

    Returns:
        无。

    Raises:
        AssertionError: verdict、分数、门禁、序列化或 stdout 行为漂移时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)

    first = evaluate_acceptance(inputs, evaluated_at=_FIXED_EVALUATED_AT)
    second = evaluate_acceptance(inputs, evaluated_at=_FIXED_EVALUATED_AT)

    assert first.verdict == "PASS"
    assert first.total_score == 85
    assert first.findings == ()
    assert len(first.artifacts) == 13
    assert all(status == "passed" for _gate, status in first.hard_gates)
    assert first.canonical_bytes() == second.canonical_bytes()
    parsed_receipt = parse_acceptance_receipt(parse_json_bytes(first.canonical_bytes(), label="acceptance receipt"))
    assert parsed_receipt.verdict == "PASS"
    assert parsed_receipt.total_score == 85
    assert len(parsed_receipt.artifacts) == 13
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.unit
def test_slice1_strict_schemas_reject_unknown_nan_bool_and_round_trip_plan_phase(
    tmp_path: Path,
) -> None:
    """验证 plan/phase/contract/receipt 严格 schema 与 JSON 数值规则。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 未知字段、NaN 或 bool-as-int 被接受时抛出。
    """

    contract_payload = _load_json_fixture("contract-v1.json")
    contract_with_unknown = dict(contract_payload)
    contract_with_unknown["unexpected"] = True
    with pytest.raises(ContractError, match="unknown"):
        parse_acceptance_contract(contract_with_unknown)
    contract_missing_required = dict(contract_payload)
    contract_missing_required.pop("model_roles")
    with pytest.raises(
        ContractError,
        match=r"contract schema 不闭合: missing=\['model_roles'\], unknown=\[\]",
    ):
        parse_acceptance_contract(contract_missing_required)

    contract_with_bool = json.loads((_FIXTURE_ROOT / "contract-v1.json").read_text(encoding="utf-8"))
    contract_with_bool["score_contract"]["total_points"] = True
    with pytest.raises(ContractError, match="bool"):
        parse_acceptance_contract(contract_with_bool)
    with pytest.raises(ContractError, match="NaN"):
        parse_json_bytes(b'{"value":NaN}', label="nan fixture")

    package_inputs = build_package_input_fingerprints()
    plan = AcceptancePlan(
        ticker="AAPL",
        company="Apple Inc.",
        research_template="technology",
        as_of=datetime(2025, 2, 1, tzinfo=UTC),
        git_sha="a" * 64,
        dirty=False,
        python_version="3.11.15",
        platform="darwin",
        timezone="Asia/Shanghai",
        package_inputs=package_inputs,
        price_snapshot_sha256="b" * 64,
        price_material_sha256="c" * 64,
        budget=_APPROVED_BUDGET,
        max_wall_seconds=_MAX_WALL_SECONDS,
        termination_grace_seconds=10,
        required_research_artifacts=tuple(_RESEARCH_ARTIFACT_NAMES),
    )
    assert parse_acceptance_plan(plan.to_json()) == plan
    plan_unknown = dict(plan.to_json())
    plan_unknown["unexpected"] = "rejected"
    with pytest.raises(ContractError, match="unknown"):
        parse_acceptance_plan(plan_unknown)

    phase = PhaseReceipt(
        plan_fingerprint=plan.fingerprint,
        phase_name="download",
        status="passed",
        started_at=datetime(2025, 2, 1, tzinfo=UTC),
        ended_at=datetime(2025, 2, 1, 0, 1, tzinfo=UTC),
        duration_seconds=60.0,
        remaining_wall_seconds=3_540.0,
        argv=(("python", "-m", "dayu.cli", "download"),),
        exit_code=0,
        stop_reason=None,
        termination_action=None,
        partial_by_timeout=False,
    )
    assert parse_phase_receipt(phase.to_json()) == phase
    phase_unknown = dict(phase.to_json())
    phase_unknown["unexpected"] = 1
    with pytest.raises(ContractError, match="unknown"):
        parse_phase_receipt(phase_unknown)

    result = evaluate_acceptance(_load_acceptance_inputs(tmp_path), evaluated_at=_FIXED_EVALUATED_AT)
    receipt_unknown = dict(result.to_json())
    receipt_unknown["unexpected"] = 1
    with pytest.raises(ContractError, match="unknown"):
        parse_acceptance_receipt(receipt_unknown)


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["missing", "renamed"])
def test_slice1_required_research_artifact_set_is_fixed_before_semantic_lookup(
    tmp_path: Path,
    mutation: str,
) -> None:
    """验证 contract 与 inspection 在语义下标前拒绝非固定 13 文件集合。

    Args:
        tmp_path: pytest 隔离目录。
        mutation: 删除或重命名一个语义 artifact 的变异类型。

    Returns:
        无。

    Raises:
        AssertionError: 非固定集合未以 ContractError fail closed 时抛出。
    """

    contract_payload = _load_json_fixture("contract-v1.json")
    artifact_values = _require_list(
        contract_payload["required_research_artifacts"],
        label="contract.required_research_artifacts",
    )
    mutated_values: list[JsonValue] = list(artifact_values)
    if mutation == "missing":
        mutated_values.remove("technology.monitoring-plan.json")
    else:
        index = mutated_values.index("technology.monitoring-plan.json")
        mutated_values[index] = "technology.monitoring-plan-renamed.json"
    contract_payload["required_research_artifacts"] = mutated_values
    expected_message = "必须精确等于固定 AAPL/technology 13 文件集合"
    with pytest.raises(ContractError, match=expected_message):
        parse_acceptance_contract(contract_payload)

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    mutated_names = tuple(value for value in mutated_values if isinstance(value, str))
    with pytest.raises(ContractError, match=expected_message):
        inspect_research_artifacts(
            artifact_root,
            required_artifacts=mutated_names,
        )


@pytest.mark.unit
def test_slice1_manual_review_skeleton_and_partial_are_pending_but_low_complete_review_fails(
    tmp_path: Path,
) -> None:
    """验证人工 rubric 骨架、部分填写与完整低分的严格三态。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: pending/FAIL 状态聚合错误时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    skeleton_dimensions = tuple(
        replace(
            dimension,
            score=None,
            items=tuple(replace(item, score=None, evidence_paths=(), notes=None) for item in dimension.items),
        )
        for dimension in inputs.quality_review.dimensions
    )
    skeleton = replace(
        inputs.quality_review,
        reviewer_role=None,
        reviewer_id_label=None,
        status="PENDING_MANUAL_REVIEW",
        dimensions=skeleton_dimensions,
        total_score=None,
        completed_at=None,
    )
    skeleton_result = evaluate_acceptance(
        replace(inputs, quality_review=skeleton),
        evaluated_at=_FIXED_EVALUATED_AT,
    )
    assert skeleton_result.verdict == "PENDING_MANUAL_REVIEW"
    assert skeleton_result.findings == ()
    assert dict(skeleton_result.hard_gates)["manual_review_passed"] == "pending"

    first_dimension = skeleton_dimensions[0]
    partial_first_item = replace(
        first_dimension.items[0],
        score=0,
        evidence_paths=("report-v1.md",),
        notes="部分复核。",
    )
    partial = replace(
        skeleton,
        reviewer_role="investment-reviewer",
        reviewer_id_label="reviewer-1",
        dimensions=(
            replace(first_dimension, items=(partial_first_item, *first_dimension.items[1:])),
            *skeleton_dimensions[1:],
        ),
    )
    partial_result = evaluate_acceptance(
        replace(inputs, quality_review=partial),
        evaluated_at=_FIXED_EVALUATED_AT,
    )
    assert partial_result.verdict == "PENDING_MANUAL_REVIEW"

    source_dimension = inputs.quality_review.dimensions[0]
    lowered_first_item = replace(source_dimension.items[0], score=6)
    lowered_source = replace(
        source_dimension,
        score=19,
        items=(lowered_first_item, *source_dimension.items[1:]),
    )
    low_review = replace(
        inputs.quality_review,
        status="FAIL",
        dimensions=(lowered_source, *inputs.quality_review.dimensions[1:]),
        total_score=83,
    )
    low_result = evaluate_acceptance(
        replace(inputs, quality_review=low_review),
        evaluated_at=_FIXED_EVALUATED_AT,
    )
    assert low_result.verdict == "FAIL"
    assert "rubric.dimension_threshold" in {item.code for item in low_result.findings}


@pytest.mark.unit
def test_slice1_report_topics_citations_and_acceptance_quality_fail_closed(tmp_path: Path) -> None:
    """验证缺 bear、断 citation 与三段 evidence 均按确定性门禁失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 报告质量缺口未被拒绝时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    without_bear = replace(
        inputs,
        report_text=_drop_markdown_section(inputs.report_text, "Bear case 与反证"),
    )
    assert "report.topic.bear_case" in _finding_codes(without_bear)

    disconnected = replace(
        inputs,
        report_text=inputs.report_text.replace(
            "filing-aapl-10q-2025q1 | 10-Q / 0000320193-25-000008",
            "filing-not-in-inventory | 10-Q / 0000320193-25-000008",
            1,
        ),
    )
    disconnected_codes = _finding_codes(disconnected)
    assert "report.citation_closure" in disconnected_codes
    assert "report.inventory_closure" in disconnected_codes

    three_part = replace(
        inputs,
        report_text=inputs.report_text.replace(
            (
                "- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | "
                "2024-11-01 | Item 1 与 Item 8，业务分部及现金流量表"
            ),
            "- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | 2024-11-01",
            1,
        ),
    )
    assert "report.acceptance_quality.thesis" in _finding_codes(three_part)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('"price":"236.85"', '"price":"236.86"'),
        ('"currency":"USD"', '"currency":"EUR"'),
        ('"market_date":"2025-01-15"', '"market_date":"2025-01-14"'),
    ],
)
def test_slice1_report_price_currency_and_date_must_exactly_match_snapshot(
    tmp_path: Path,
    old: str,
    new: str,
) -> None:
    """验证报告估值基准的价格、币种与 market date 均需精确一致。

    Args:
        tmp_path: pytest 隔离目录。
        old: baseline reference 片段。
        new: 制造漂移的替换片段。

    Returns:
        无。

    Raises:
        AssertionError: 任一 reference 漂移未触发 FAIL 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    mutated = replace(inputs, report_text=inputs.report_text.replace(old, new, 1))

    assert "report.valuation_reference_mismatch" in _finding_codes(mutated)


@pytest.mark.unit
def test_slice1_indented_valuation_reference_uses_one_normalized_line(tmp_path: Path) -> None:
    """验证缩进 reference 的合法与 mismatch 分支不被 schema 偏移掩盖。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 合法缩进误报或 mismatch 未命中特定 code 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    reference_line = next(
        line for line in inputs.report_text.splitlines() if line.startswith("valuation_reference_price:")
    )
    indented_valid = replace(
        inputs,
        report_text=inputs.report_text.replace(reference_line, f"  {reference_line}", 1),
    )
    assert evaluate_acceptance(indented_valid, evaluated_at=_FIXED_EVALUATED_AT).verdict == "PASS"

    mismatch_line = reference_line.replace('"price":"236.85"', '"price":"236.86"', 1)
    indented_mismatch = replace(
        inputs,
        report_text=inputs.report_text.replace(reference_line, f"  {mismatch_line}", 1),
    )
    codes = _finding_codes(indented_mismatch)
    assert "report.valuation_reference_mismatch" in codes
    assert "report.valuation_reference_schema" not in codes


@pytest.mark.unit
def test_slice1_exact_headings_ignore_decoys_and_reject_combined_topics(tmp_path: Path) -> None:
    """验证 source-list/topic 只接受唯一精确标题且合并标题不能复用。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 诱饵遮蔽真实章节或合并标题满足多个 topic 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    decoy_block = "## 来源清单说明\n\n诱饵内容\n\n## 风险说明\n\n诱饵内容\n\n"
    decoy_report = inputs.report_text.replace("## 来源清单", f"{decoy_block}## 来源清单", 1)
    decoy_result = evaluate_acceptance(
        replace(inputs, report_text=decoy_report),
        evaluated_at=_FIXED_EVALUATED_AT,
    )
    assert decoy_result.verdict == "PASS"

    without_catalyst = _drop_markdown_section(inputs.report_text, "催化剂（catalyst）")
    without_risk = _drop_markdown_section(without_catalyst, "风险（risk）")
    combined = (
        "## 风险与催化剂\n\n合并章节不得复用。\n\n### 证据与出处\n\n"
        "- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | "
        "2024-11-01 | Item 1\n\n"
    )
    combined_report = without_risk.replace("## 来源清单", f"{combined}## 来源清单", 1)
    codes = _finding_codes(replace(inputs, report_text=combined_report))
    assert "report.topic.catalyst" in codes
    assert "report.topic.risk" in codes


@pytest.mark.unit
def test_slice1_inventory_future_processed_and_reprocess_cases_fail_closed(tmp_path: Path) -> None:
    """验证未来源、processed 缺失和 reprocess_required 均硬失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一 inventory 失败条件未被拒绝时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    document = inputs.inventory.documents[0]
    future_document = replace(document, filing_date=date(2025, 2, 2), report_date=date(2025, 2, 2))
    future_inventory = replace(
        inputs.inventory,
        documents=(future_document, *inputs.inventory.documents[1:]),
    )
    assert "inventory.future_source" in _finding_codes(replace(inputs, inventory=future_inventory))

    missing_processed = ProcessedState(
        exists=False,
        parser_version="",
        quality="",
        reprocess_required=False,
        schema_version="",
        source_fingerprint="",
    )
    missing_document = replace(
        document,
        processed=missing_processed,
        processed_state_fingerprint=canonical_json_sha256(missing_processed.to_json()),
    )
    missing_inventory = replace(
        inputs.inventory,
        documents=(missing_document, *inputs.inventory.documents[1:]),
    )
    assert "inventory.processed_missing" in _finding_codes(replace(inputs, inventory=missing_inventory))

    reprocess_state = replace(document.processed, reprocess_required=True)
    reprocess_document = replace(
        document,
        processed=reprocess_state,
        processed_state_fingerprint=canonical_json_sha256(reprocess_state.to_json()),
    )
    reprocess_inventory = replace(
        inputs.inventory,
        documents=(reprocess_document, *inputs.inventory.documents[1:]),
    )
    assert "inventory.reprocess_required" in _finding_codes(replace(inputs, inventory=reprocess_inventory))


@pytest.mark.unit
def test_slice1_price_max_age_is_a_hard_gate(tmp_path: Path) -> None:
    """验证显式 price snapshot 超过 max_age_days 时硬失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 超龄价格未触发 FAIL 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    stale_price = replace(inputs.price_snapshot, max_age_days=1)

    assert "price.stale" in _finding_codes(replace(inputs, price_snapshot=stale_price))


@pytest.mark.unit
def test_slice1_budget_audit_cost_and_wall_clock_failures_are_distinct(tmp_path: Path) -> None:
    """验证 blocked budget、audit skip、超成本与 wall-clock 各自失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一治理失败未触发对应 code 时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    blocked_budget = replace(inputs.run_summary.budget, status="blocked", block_present=True)
    blocked_summary = replace(inputs.run_summary, budget=blocked_budget)
    assert "budget.blocked" in _finding_codes(replace(inputs, run_summary=blocked_summary))

    skipped_summary = replace(inputs.run_summary, audit_skipped_count=1)
    assert "audit.incomplete" in _finding_codes(replace(inputs, run_summary=skipped_summary))

    expensive_budget = replace(inputs.run_summary.budget, estimated_cost=Decimal("5.01"))
    expensive_summary = replace(
        inputs.run_summary,
        known_estimated_cost=Decimal("5.01"),
        budget=expensive_budget,
    )
    assert "budget.exceeded" in _finding_codes(replace(inputs, run_summary=expensive_summary))

    slow_runtime = replace(inputs.runtime, actual_wall_seconds=3_600.01)
    assert "wall_clock.exceeded" in _finding_codes(replace(inputs, runtime=slow_runtime))


@pytest.mark.unit
def test_slice1_ledger_owner_builders_bind_fixture_nested_summary_shape() -> None:
    """把真实 WriteModelUsageLedger 两个 builder 的嵌套形状绑定到 fixture parser。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: ledger usage/budget 嵌套字段与验收 fixture 漂移时抛出。
    """

    ledger = WriteModelUsageLedger(
        max_model_requests=20,
        max_total_tokens=200_000,
        max_estimated_cost=5.0,
        budget_currency="CNY",
    )
    pricing = {
        "currency": "CNY",
        "input_per_million": 1.0,
        "cached_input_per_million": 0.1,
        "output_per_million": 2.0,
    }
    ledger.record(
        scene_name="write",
        model_name="deepseek-v4-pro",
        model_role="primary",
        model_config={"pricing": pricing},
        usage=ModelUsage(
            request_count=1,
            usage_report_count=1,
            input_tokens=70_000,
            uncached_input_tokens=70_000,
            output_tokens=10_000,
            total_tokens=80_000,
        ),
        replay=False,
    )
    ledger.record(
        scene_name="audit",
        model_name="mimo-v2.5-pro-thinking",
        model_role="audit",
        model_config={"pricing": pricing},
        usage=ModelUsage(
            request_count=1,
            usage_report_count=1,
            input_tokens=30_000,
            uncached_input_tokens=30_000,
            output_tokens=10_000,
            total_tokens=40_000,
        ),
        replay=False,
    )
    payload = json.loads((_FIXTURE_ROOT / "run-summary-v1.json").read_text(encoding="utf-8"))
    payload["model_usage"] = ledger.build_summary()
    payload["budget"] = ledger.build_budget_summary()

    parsed = parse_owner_run_summary(payload)

    assert parsed.request_count == 2
    assert parsed.total_tokens == 120_000
    assert parsed.budget.model_requests == 2
    assert parsed.budget.total_tokens == 120_000
    assert parsed.budget.status == "within_budget"
    assert parsed.budget.block_present is False


@pytest.mark.unit
@pytest.mark.parametrize("mutation", ["stale", "tampered"])
def test_slice1_owner_report_validator_detects_stale_and_tampered_artifacts(
    tmp_path: Path,
    mutation: str,
) -> None:
    """验证真实 owner report validator 能区分 stale 与 body tamper。

    Args:
        tmp_path: pytest 隔离目录。
        mutation: ``stale`` 或 ``tampered`` 注入方式。

    Returns:
        无。

    Raises:
        AssertionError: 真实 owner validator 未触发对应门禁时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    if mutation == "stale":
        workbook_path = artifact_root / "technology.research-workbook.json"
        workbook = json.loads(workbook_path.read_text(encoding="utf-8"))
        workbook["company"] = "Apple Inc. fixture drift"
        workbook_path.write_text(json.dumps(workbook, ensure_ascii=False), encoding="utf-8")
    else:
        report_path = artifact_root / "technology.research-progress.md"
        report_path.write_text(report_path.read_text(encoding="utf-8") + "\nmanual tamper\n", encoding="utf-8")
    inputs = _load_acceptance_inputs_from_artifacts(artifact_root)

    codes = _finding_codes(inputs)

    assert ("workbook.stale" if mutation == "stale" else "workbook.tampered") in codes


@pytest.mark.unit
def test_slice1_monitoring_fingerprint_and_forged_bound_source_fail_closed(tmp_path: Path) -> None:
    """验证 monitoring 输入指纹漂移与伪造 bound source 均被 owner 拒绝。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 指纹或绑定伪造未触发 monitoring hard gate 时抛出。
    """

    fingerprint_root = _materialize_acceptance_artifacts(tmp_path / "fingerprint")
    source_map = fingerprint_root / "technology.source-map.json"
    source_map.write_text(source_map.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    fingerprint_inputs = _load_acceptance_inputs_from_artifacts(fingerprint_root)
    assert "monitoring.unsafe" in _finding_codes(fingerprint_inputs)

    forged_root = _materialize_acceptance_artifacts(tmp_path / "forged")
    plan_path = forged_root / "technology.monitoring-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    task = plan["tasks"][0]
    task["status"] = "ready_for_review"
    task["bound_data_sources"] = [task["data_source_candidates"][0]]
    plan["readiness"]["status"] = "blocked_unbound_sources"
    plan["readiness"]["ready_task_count"] = 1
    plan["readiness"]["blocked_task_count"] -= 1
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    forged_inputs = _load_acceptance_inputs_from_artifacts(forged_root)
    assert "monitoring.unsafe" in _finding_codes(forged_inputs)


@pytest.mark.unit
def test_slice1_artifact_symlink_and_bound_sha_tamper_fail_containment(tmp_path: Path) -> None:
    """验证研究 artifact symlink 越界与已绑定 SHA 漂移均失败。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: containment 或 tamper 未被拒绝时抛出。
    """

    tamper_root = _materialize_acceptance_artifacts(tmp_path / "tamper")
    target_name = "technology.checklist.md"
    original_sha = hashlib.sha256((tamper_root / target_name).read_bytes()).hexdigest()
    (tamper_root / target_name).write_text("tampered", encoding="utf-8")
    tampered_inputs = _load_acceptance_inputs_from_artifacts(
        tamper_root,
        expected_artifact_sha256=((target_name, original_sha),),
    )
    assert "artifacts.inventory" in _finding_codes(tampered_inputs)

    symlink_root = _materialize_acceptance_artifacts(tmp_path / "symlink")
    external = tmp_path / "external.md"
    external.write_text("outside", encoding="utf-8")
    symlink_target = symlink_root / target_name
    symlink_target.unlink()
    symlink_target.symlink_to(external)
    symlink_inputs = _load_acceptance_inputs_from_artifacts(symlink_root)
    assert "artifacts.inventory" in _finding_codes(symlink_inputs)


@pytest.mark.unit
def test_slice1_production_artifact_json_rejects_nan_before_owner_validation(tmp_path: Path) -> None:
    """验证全部生产 JSON 先经 strict ingress，NaN 不进入 owner validator。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: NaN 未以 ContractError fail closed 时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    workbook_path = artifact_root / "technology.research-workbook.json"
    original = workbook_path.read_text(encoding="utf-8")
    mutated = original.replace('"schema_version": 1', '"schema_version": NaN', 1)
    assert mutated != original
    workbook_path.write_text(mutated, encoding="utf-8")

    with pytest.raises(ContractError, match="不得包含 NaN/Infinity"):
        _load_acceptance_inputs_from_artifacts(artifact_root)


@pytest.mark.unit
def test_slice1_non_json_owner_result_is_normalized_to_contract_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 owner validator 的非 JSON 返回在既有 ingress 归一化。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: TypeError 未归一化为 ContractError 时抛出。
    """

    def non_json_workbook_result(_payload: dict[str, JsonValue]) -> dict[str, set[str]]:
        """返回一个故意包含 set 的 owner 宽结果。

        Args:
            _payload: owner workbook 输入；本替身不读取。

        Returns:
            不能 JSON 序列化的测试结果。

        Raises:
            本函数不显式抛出异常。
        """

        return {"errors": {"not-json"}}

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    monkeypatch.setattr(
        acceptance_evaluator_module,
        "validate_research_workbook_payload",
        non_json_workbook_result,
    )
    with pytest.raises(ContractError, match="workbook validation owner result 不是严格 JSON"):
        _load_acceptance_inputs_from_artifacts(artifact_root)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tree", "relative_path"),
    [
        ("assets", "定性分析模板.md"),
        ("assets", "research_templates/technology.definition.json"),
        ("assets", "research_templates/common.md"),
        ("assets", "research_templates/technology.md"),
        ("assets", "research_templates/consumer.md"),
        ("config", "prompts/manifests/write.json"),
    ],
)
def test_slice1_package_input_tree_drift_covers_all_materialization_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tree: str,
    relative_path: str,
) -> None:
    """验证 config/tree、base、definition 与 manifest-enumerated 资产漂移。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。
        tree: 要修改的复制树名称。
        relative_path: 树内相对文件路径。

    Returns:
        无。

    Raises:
        AssertionError: 目标未纳入闭包或 drift 未在执行前失败时抛出。
    """

    config_root = tmp_path / "config"
    assets_root = tmp_path / "assets"
    shutil.copytree(resolve_package_config_path(), config_root)
    shutil.copytree(resolve_package_assets_path(), assets_root)
    monkeypatch.setattr(acceptance_contracts_module, "resolve_package_config_path", lambda: config_root)
    monkeypatch.setattr(acceptance_contracts_module, "resolve_package_assets_path", lambda: assets_root)
    expected = build_package_input_fingerprints()
    research_locators = {item.locator for item in expected.research_tree.files}
    assert "dayu/assets/research_templates/common.md" in research_locators
    assert "dayu/assets/research_templates/technology.md" in research_locators
    assert "dayu/assets/research_templates/technology.definition.json" in research_locators
    assert "dayu/assets/research_templates/consumer.md" in research_locators
    assert "dayu/config/prompts/manifests/write.json" in {item.locator for item in expected.config_tree.files}
    target_root = assets_root if tree == "assets" else config_root
    target = target_root / relative_path
    target.write_bytes(target.read_bytes() + b"\nfixture drift\n")

    with pytest.raises(FingerprintDriftError, match="drift"):
        assert_package_input_fingerprints(expected)


@pytest.mark.unit
def test_slice1_package_tree_rejects_symlink_nonregular_and_duplicate_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 package canonical tree 对 symlink、FIFO 与重复 locator fail closed。

    Args:
        tmp_path: pytest 隔离目录。
        monkeypatch: pytest 属性替换器。

    Returns:
        无。

    Raises:
        AssertionError: 非普通输入或重复 canonical locator 被接受时抛出。
    """

    config_root = tmp_path / "config"
    assets_root = tmp_path / "assets"
    shutil.copytree(resolve_package_config_path(), config_root)
    shutil.copytree(resolve_package_assets_path(), assets_root)
    monkeypatch.setattr(acceptance_contracts_module, "resolve_package_config_path", lambda: config_root)
    monkeypatch.setattr(acceptance_contracts_module, "resolve_package_assets_path", lambda: assets_root)
    external = tmp_path / "external.md"
    external.write_text("external", encoding="utf-8")
    (assets_root / "research_templates" / "linked.md").symlink_to(external)
    with pytest.raises(ContractError, match="symlink"):
        build_package_input_fingerprints()
    (assets_root / "research_templates" / "linked.md").unlink()
    fifo = config_root / "nonregular.fifo"
    os.mkfifo(fifo)
    with pytest.raises(ContractError, match="普通文件"):
        build_package_input_fingerprints()
    fifo.unlink()

    package_inputs = build_package_input_fingerprints()
    plan = AcceptancePlan(
        ticker="AAPL",
        company="Apple Inc.",
        research_template="technology",
        as_of=datetime(2025, 2, 1, tzinfo=UTC),
        git_sha="a" * 64,
        dirty=False,
        python_version="3.11.15",
        platform="darwin",
        timezone="UTC",
        package_inputs=package_inputs,
        price_snapshot_sha256="b" * 64,
        price_material_sha256="c" * 64,
        budget=_APPROVED_BUDGET,
        max_wall_seconds=3_600,
        termination_grace_seconds=10,
        required_research_artifacts=tuple(_RESEARCH_ARTIFACT_NAMES),
    )
    plan_payload = plan.to_json()
    package_payload = _require_mapping(plan_payload["package_inputs"], label="plan.package_inputs")
    research_payload = _require_mapping(package_payload["research_tree"], label="plan.research_tree")
    files = _require_list(research_payload["files"], label="plan.research_tree.files")
    research_payload["files"] = [*files, files[0]]
    with pytest.raises(ContractError, match="排序且唯一"):
        parse_acceptance_plan(plan_payload)


@pytest.mark.unit
@pytest.mark.parametrize(
    "sensitive_value",
    [
        "Authorization: Bearer secret-token-value",
        "Cookie: session=secret-token-value",
        "sk-abcdefghijklmnopqrstuvwx",
        "/Users/alice/private/result.json",
        "/home/alice/private/result.json",
        r"C:\Users\alice\private\result.json",
    ],
)
def test_slice1_sanitizer_rejects_secret_and_posix_windows_home_shapes(
    tmp_path: Path,
    sensitive_value: str,
) -> None:
    """验证 sanitizer 只对验收自有输出拒绝秘密与绝对 home 路径。

    Args:
        tmp_path: pytest 隔离目录。
        sensitive_value: 待注入 acceptance-owned JSON 的敏感文本。

    Returns:
        无。

    Raises:
        AssertionError: 敏感形状未触发 hard gate 时抛出。
    """

    inputs = _load_acceptance_inputs(
        tmp_path,
        acceptance_owned_outputs=({"value": sensitive_value},),
    )

    assert "sanitizer.sensitive_shape" in _finding_codes(inputs)


@pytest.mark.unit
def test_slice1_phase_receipt_and_reviewer_labels_share_bounded_sanitizer(tmp_path: Path) -> None:
    """验证 phase receipt 与 reviewer 标签也进入验收自有敏感信息边界。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: phase argv home 路径或 reviewer PII 未被拒绝时抛出。
    """

    inputs = _load_acceptance_inputs(tmp_path)
    phase = PhaseReceipt(
        plan_fingerprint="a" * 64,
        phase_name="write",
        status="passed",
        started_at=datetime(2025, 2, 1, tzinfo=UTC),
        ended_at=datetime(2025, 2, 1, 0, 1, tzinfo=UTC),
        duration_seconds=60.0,
        remaining_wall_seconds=3_540.0,
        argv=(("python", "--config", "/Users/alice/private/config"),),
        exit_code=0,
        stop_reason=None,
        termination_action=None,
        partial_by_timeout=False,
    )
    phase_inputs = replace(inputs, runtime=replace(inputs.runtime, phase_receipts=(phase,)))
    assert "sanitizer.sensitive_shape" in _finding_codes(phase_inputs)

    pii_review = replace(inputs.quality_review, reviewer_id_label="alice@example.com")
    reviewer_inputs = replace(inputs, quality_review=pii_review)
    assert "rubric.reviewer_pii" in _finding_codes(reviewer_inputs)


@pytest.mark.unit
def test_slice1_status_snapshot_tamper_fails_research_artifact_validator(tmp_path: Path) -> None:
    """验证三个 13 产物状态快照不是仅存在即通过。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: unhealthy snapshot 未触发 artifact validator finding 时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    status_path = artifact_root / "research-workbook-report-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["overall_status"] = "unhealthy"
    status["summary"]["invalid_report_count"] = 1
    status_path.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    inputs = _load_acceptance_inputs_from_artifacts(artifact_root)

    assert "artifacts.validators" in _finding_codes(inputs)


@pytest.mark.unit
def test_slice1_inventory_and_quality_review_unknown_fields_are_rejected() -> None:
    """验证 inventory 与 rubric 顶层未知字段同样 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: inventory/rubric 未知字段被接受时抛出。
    """

    inventory = _load_json_fixture("source-inventory-v1.json")
    inventory["unexpected"] = True
    with pytest.raises(ContractError, match="unknown"):
        acceptance_contracts_module.parse_source_inventory(inventory)
    review = _load_json_fixture("quality-review-v1.json")
    review["unexpected"] = True
    with pytest.raises(ContractError, match="unknown"):
        acceptance_contracts_module.parse_quality_review(review)


@pytest.mark.unit
def test_slice1_production_absolute_paths_are_not_rewritten_or_copied_to_receipt(tmp_path: Path) -> None:
    """验证生产 artifact 原生绝对 package 路径不被扫描、改写或复制。

    Args:
        tmp_path: pytest 隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 生产字节变化、误判 FAIL 或 receipt 泄漏绝对路径时抛出。
    """

    artifact_root = _materialize_acceptance_artifacts(tmp_path)
    manifest_path = artifact_root / "research-template.manifest.json"
    rules_path = artifact_root / "technology.monitoring-rules.json"
    before_manifest = manifest_path.read_bytes()
    before_rules = rules_path.read_bytes()
    manifest_value: JsonValue = json.loads(before_manifest)
    rules_value: JsonValue = json.loads(before_rules)
    manifest_payload = _require_mapping(manifest_value, label="research template manifest")
    rules_payload = _require_mapping(rules_value, label="monitoring rules")
    template_entries = _require_list(manifest_payload["templates"], label="research template manifest.templates")
    technology_entry = next(
        _require_mapping(value, label="research template manifest.template")
        for value in template_entries
        if isinstance(value, dict) and value.get("name") == "technology"
    )
    template_file = technology_entry["template_file"]
    source_template_file = rules_payload["source_template_file"]
    assert isinstance(template_file, str) and Path(template_file).is_absolute()
    assert isinstance(source_template_file, str) and Path(source_template_file).is_absolute()
    inputs = _load_acceptance_inputs_from_artifacts(artifact_root)

    result = evaluate_acceptance(inputs, evaluated_at=_FIXED_EVALUATED_AT)

    assert result.verdict == "PASS"
    assert manifest_path.read_bytes() == before_manifest
    assert rules_path.read_bytes() == before_rules
    receipt = result.canonical_bytes()
    assert template_file.encode("utf-8") not in receipt
    assert source_template_file.encode("utf-8") not in receipt
    assert b"template_file" not in receipt
    assert b"source_template_file" not in receipt
    assert all(reference.locator.startswith(f"{_ACCEPTANCE_ARTIFACT_PREFIX}/") for reference in result.artifacts)


@pytest.mark.unit
def test_slice1_repository_inventory_uses_only_protocol_methods_and_strict_ingress() -> None:
    """验证 source inventory 只通过三个仓储 Protocol 读取并立即严格收窄。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 协议调用、排序或 primary/processed 指纹闭包错误时抛出。
    """

    source_repository = create_autospec(SourceDocumentRepositoryProtocol, instance=True)
    processed_repository = create_autospec(ProcessedDocumentRepositoryProtocol, instance=True)
    blob_repository = create_autospec(DocumentBlobRepositoryProtocol, instance=True)
    source_repository.list_source_document_ids.side_effect = lambda _ticker, kind: (
        ["filing-aapl-10k-2024"] if kind == SourceKind.FILING else ["material-price"]
    )
    source_payloads = {
        "filing-aapl-10k-2024": {
            "document_id": "filing-aapl-10k-2024",
            "internal_document_id": "0000320193-24-000123",
            "form_type": "10-K",
            "filing_date": "2024-11-01",
            "report_date": "2024-09-28",
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "ingest_complete": True,
        },
        "material-price": {
            "document_id": "material-price",
            "internal_document_id": "material-price",
            "form_type": "MATERIAL_OTHER",
            "filing_date": "2025-01-15",
            "report_date": "2025-01-15",
            "fiscal_year": None,
            "fiscal_period": None,
            "ingest_complete": True,
        },
    }
    source_repository.get_source_meta.side_effect = lambda _ticker, document_id, _kind: source_payloads[document_id]
    processed_repository.get_processed_meta.side_effect = lambda _ticker, document_id: {
        "document_id": document_id,
        "parser_version": "fixture-parser-v1",
        "quality": "accepted_fixture",
        "reprocess_required": False,
        "schema_version": "processed_document_v1",
        "source_fingerprint": hashlib.sha256(document_id.encode("utf-8")).hexdigest(),
    }
    source_repository.get_primary_file.side_effect = lambda _ticker, document_id, _kind: FileObjectMeta(
        uri=f"storage://{document_id}/primary.md",
        sha256=hashlib.sha256(document_id.encode("utf-8")).hexdigest(),
    )
    source_repository.get_source_handle.side_effect = lambda ticker, document_id, kind: SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=kind.value,
    )
    blob_repository.read_file_bytes.side_effect = lambda handle, _name: handle.document_id.encode("utf-8")
    as_of = datetime(2025, 2, 1, tzinfo=UTC)

    inventory = build_source_inventory_from_repositories(
        RepositoryInventoryRequest(
            fixture_id="repository-fixture",
            ticker="AAPL",
            company="Apple Inc.",
            as_of=as_of,
            live_freshness_claimed=True,
            source_windows=(
                SourceWindow(("10-K",), date(2020, 2, 1), date(2025, 2, 1)),
                SourceWindow(("10-Q",), date(2023, 2, 1), date(2025, 2, 1)),
                SourceWindow(("8-K", "DEF 14A"), date(2023, 2, 1), date(2025, 2, 1)),
            ),
            latest_discovery=(("10-K", "0000320193-24-000123"),),
            source_repository=source_repository,
            processed_repository=processed_repository,
            blob_repository=blob_repository,
        )
    )

    assert [item.document_id for item in inventory.documents] == [
        "filing-aapl-10k-2024",
        "material-price",
    ]
    assert all(item.processed.exists for item in inventory.documents)
    assert all(
        item.primary_file_sha256 == hashlib.sha256(item.document_id.encode()).hexdigest()
        for item in inventory.documents
    )
    assert source_repository.list_source_document_ids.call_count == 2
    assert source_repository.get_source_meta.call_count == 2
    assert processed_repository.get_processed_meta.call_count == 2
    assert blob_repository.read_file_bytes.call_count == 2
