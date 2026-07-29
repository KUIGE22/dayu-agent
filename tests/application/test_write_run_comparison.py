"""Tests for deterministic Champion/Challenger write-run comparison."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from dayu.services.write_run_comparison import (
    compare_write_run_paths,
    compare_write_run_summaries,
    load_write_run_comparison,
    persist_write_run_comparison,
    resolve_write_run_comparison_for_report,
)


def _summary(
    *,
    primary_model: str,
    cost: float | None,
    cost_status: str = "complete",
    gate_status: str = "passed",
    audit_passed: bool = True,
    retries: int = 0,
    fallback_switch_count: int = 0,
    fallback_error_count: int = 0,
    routing_recorded: bool = True,
) -> dict[str, Any]:
    failed_count = 0 if gate_status == "passed" else 1
    audit_failed_count = 0 if audit_passed else 1
    summary = {
        "schema_version": "write_run_summary_v3",
        "ticker": "AAPL",
        "gate_status": gate_status,
        "model_roles": {
            "primary": {"model_names": [primary_model], "scenes": []},
            "audit": {"model_names": ["claude-audit"], "scenes": []},
        },
        "model_usage": {
            "usage_status": "complete",
            "scene_call_count": 10,
            "request_count": 10,
            "total_tokens": 1_000,
            "cost": {
                "status": cost_status,
                "currency": "USD",
                "known_estimated_cost": cost,
            },
        },
        "chapter_count": 1,
        "failed_count": failed_count,
        "audit": {
            "required": True,
            "failed_count": audit_failed_count,
            "gate_blocked_count": 0,
            "first_pass_count": 1 if retries == 0 and gate_status == "passed" else 0,
            "total_retries": retries,
        },
        "chapters": [
            {
                "index": 1,
                "title": "Business",
                "gate_passed": gate_status == "passed",
                "audit_passed": audit_passed,
            }
        ],
    }
    if routing_recorded:
        completed_count = fallback_switch_count - fallback_error_count
        routes = []
        if completed_count > 0:
            routes.append(
                {
                    "fallback_call_status": "completed",
                    "switch_count": completed_count,
                }
            )
        if fallback_error_count > 0:
            routes.append(
                {
                    "fallback_call_status": "error",
                    "switch_count": fallback_error_count,
                }
            )
        summary["model_routing"] = {
            "fallback_switch_count": fallback_switch_count,
            "fallback_call_completed_count": completed_count,
            "fallback_call_error_count": fallback_error_count,
            "routes": routes,
        }
    return summary


def _summary_with_scene_usage(
    *,
    primary_model: str,
    uncached_input_tokens: int,
) -> dict[str, Any]:
    """Build one v3 summary whose persisted cost is intentionally unavailable."""

    summary = _summary(
        primary_model=primary_model,
        cost=None,
        cost_status="unavailable",
    )
    unavailable_cost = {
        "currency": None,
        "status": "unavailable",
        "known_estimated_cost": None,
        "priced_scene_call_count": 0,
        "unpriced_scene_call_count": 1,
    }
    summary["model_usage"] = {
        "usage_status": "complete",
        "scene_call_count": 1,
        "request_count": 1,
        "usage_report_count": 1,
        "input_tokens": uncached_input_tokens,
        "uncached_input_tokens": uncached_input_tokens,
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": uncached_input_tokens,
        "cost": unavailable_cost,
        "by_role": {
            "primary": {
                "scene_call_count": 1,
                "request_count": 1,
                "usage_report_count": 1,
                "cost": unavailable_cost,
            }
        },
        "by_scene": [
            {
                "scene_name": "write",
                "model_name": primary_model,
                "model_role": "primary",
                "scene_call_count": 1,
                "request_count": 1,
                "usage_report_count": 1,
                "input_tokens": uncached_input_tokens,
                "uncached_input_tokens": uncached_input_tokens,
                "cached_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": uncached_input_tokens,
                "cost": unavailable_cost,
            }
        ],
    }
    return summary


@pytest.mark.unit
def test_equivalent_lower_cost_challenger_is_recommended() -> None:
    champion = _summary(primary_model="deepseek", cost=1.0)
    challenger = _summary(primary_model="claude", cost=0.7)

    result = compare_write_run_summaries(champion, challenger)

    assert result["verdict"] == "promote_challenger"
    assert result["reason_codes"] == ["equivalent_quality_at_lower_cost"]
    assert result["quality"]["status"] == "equivalent"
    assert result["cost"]["cost_delta"] == pytest.approx(-0.3)
    assert result["cost"]["basis"] == "persisted_run_summary"
    assert result["routing"]["status"] == "equivalent"


@pytest.mark.unit
def test_routing_comparison_reports_lower_fallback_usage_as_improved() -> None:
    champion = _summary(
        primary_model="deepseek",
        cost=1.0,
        fallback_switch_count=2,
    )
    challenger = _summary(
        primary_model="mimo",
        cost=0.7,
    )

    result = compare_write_run_summaries(champion, challenger)

    assert result["verdict"] == "promote_challenger"
    assert result["routing"] == {
        "comparable": True,
        "integrity_issue": False,
        "status": "improved",
        "champion": {
            "status": "complete",
            "fallback_switch_count": 2,
            "fallback_call_completed_count": 2,
            "fallback_call_error_count": 0,
            "fallback_call_completion_rate": 1.0,
            "scene_call_count": 10,
            "fallback_scene_call_share": 0.2,
        },
        "challenger": {
            "status": "complete",
            "fallback_switch_count": 0,
            "fallback_call_completed_count": 0,
            "fallback_call_error_count": 0,
            "fallback_call_completion_rate": None,
            "scene_call_count": 10,
            "fallback_scene_call_share": 0.0,
        },
        "fallback_switch_delta": -2,
        "fallback_call_error_delta": 0,
        "fallback_call_completion_rate_delta": None,
        "fallback_scene_call_share_delta": -0.2,
    }


@pytest.mark.unit
def test_routing_regression_requires_review_before_automatic_promotion() -> None:
    champion = _summary(primary_model="deepseek", cost=1.0)
    challenger = _summary(
        primary_model="mimo",
        cost=0.7,
        fallback_switch_count=1,
    )

    result = compare_write_run_summaries(champion, challenger)

    assert result["quality"]["status"] == "equivalent"
    assert result["routing"]["status"] == "regressed"
    assert result["verdict"] == "manual_review"
    assert result["reason_codes"] == ["challenger_fallback_routing_regressed"]


@pytest.mark.unit
def test_mixed_routing_changes_require_review_before_automatic_promotion() -> None:
    champion = _summary(
        primary_model="deepseek",
        cost=1.0,
        fallback_switch_count=2,
    )
    challenger = _summary(
        primary_model="mimo",
        cost=0.7,
        fallback_switch_count=1,
        fallback_error_count=1,
    )

    result = compare_write_run_summaries(champion, challenger)

    assert result["routing"]["status"] == "mixed"
    assert result["verdict"] == "manual_review"
    assert result["reason_codes"] == ["mixed_fallback_routing_changes"]


@pytest.mark.unit
def test_missing_legacy_routing_preserves_existing_verdict() -> None:
    champion = _summary(
        primary_model="deepseek",
        cost=1.0,
        routing_recorded=False,
    )
    challenger = _summary(primary_model="mimo", cost=0.7)

    result = compare_write_run_summaries(champion, challenger)

    assert result["verdict"] == "promote_challenger"
    assert result["routing"]["comparable"] is False
    assert result["routing"]["integrity_issue"] is False
    assert result["routing"]["status"] == "unavailable"
    assert result["routing"]["champion"]["status"] == "missing"
    assert (
        "Fallback routing is missing or invalid in one or both run summaries."
        in result["warnings"]
    )


@pytest.mark.unit
def test_invalid_routing_receipt_blocks_automatic_promotion() -> None:
    champion = _summary(primary_model="deepseek", cost=1.0)
    challenger = _summary(
        primary_model="mimo",
        cost=0.7,
        fallback_switch_count=1,
    )
    challenger["model_routing"]["routes"] = []

    result = compare_write_run_summaries(champion, challenger)

    assert result["routing"]["comparable"] is False
    assert result["routing"]["integrity_issue"] is True
    assert result["routing"]["status"] == "invalid"
    assert result["routing"]["challenger"]["status"] == "invalid"
    assert result["verdict"] == "manual_review"
    assert result["reason_codes"] == ["invalid_fallback_routing_receipt"]


@pytest.mark.unit
def test_quality_regression_keeps_champion_even_when_challenger_is_cheaper() -> None:
    champion = _summary(primary_model="deepseek", cost=1.0)
    challenger = _summary(
        primary_model="claude",
        cost=0.2,
        gate_status="blocked",
        audit_passed=False,
    )

    result = compare_write_run_summaries(champion, challenger)

    assert result["verdict"] == "keep_champion"
    assert "challenger_quality_regressed" in result["reason_codes"]
    assert result["quality"]["chapters"]["regressions"] == [
        {"index": 1, "title": "Business", "reason": "gate_passed_to_blocked"},
        {"index": 1, "title": "Business", "reason": "audit_passed_to_failed"},
    ]


@pytest.mark.unit
def test_incomplete_cost_requires_manual_review() -> None:
    champion = _summary(primary_model="deepseek", cost=1.0)
    challenger = _summary(
        primary_model="claude",
        cost=0.5,
        cost_status="partial",
    )

    result = compare_write_run_summaries(champion, challenger)

    assert result["verdict"] == "manual_review"
    assert result["reason_codes"] == ["complete_same_currency_cost_required"]
    assert result["cost"]["comparable"] is False


@pytest.mark.unit
@pytest.mark.parametrize("invalid_cost", [-1.0, float("nan"), float("inf")])
def test_invalid_cost_cannot_trigger_promotion(invalid_cost: float) -> None:
    champion = _summary(primary_model="deepseek", cost=1.0)
    challenger = _summary(primary_model="claude", cost=invalid_cost)

    result = compare_write_run_summaries(champion, challenger)

    assert result["verdict"] == "manual_review"
    assert result["cost"]["comparable"] is False


@pytest.mark.unit
def test_mismatched_chapter_set_is_not_comparable() -> None:
    champion = _summary(primary_model="deepseek", cost=1.0)
    challenger = _summary(primary_model="claude", cost=0.5)
    challenger["chapters"][0]["title"] = "Different"

    result = compare_write_run_summaries(champion, challenger)

    assert result["verdict"] == "keep_champion"
    assert result["compatible"] is False
    assert "chapter_set_mismatch" in result["compatibility_issues"]


@pytest.mark.unit
def test_comparison_can_load_directories_and_persist_artifact(tmp_path: Path) -> None:
    champion_dir = tmp_path / "champion"
    challenger_dir = tmp_path / "challenger"
    champion_dir.mkdir()
    challenger_dir.mkdir()
    (champion_dir / "run_summary.json").write_text(
        json.dumps(_summary(primary_model="deepseek", cost=1.0)),
        encoding="utf-8",
    )
    (challenger_dir / "run_summary.json").write_text(
        json.dumps(_summary(primary_model="claude", cost=0.8)),
        encoding="utf-8",
    )

    comparison = compare_write_run_paths(champion_dir, challenger_dir)
    output = persist_write_run_comparison(comparison, tmp_path / "comparison.json")

    assert comparison["sources"]["champion"].endswith("champion\\run_summary.json")
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "promote_challenger"


@pytest.mark.unit
def test_current_catalog_repricing_is_read_only_and_adds_unit_cost_metrics() -> None:
    champion = _summary_with_scene_usage(
        primary_model="deepseek-v4-pro",
        uncached_input_tokens=1_000_000,
    )
    challenger = _summary_with_scene_usage(
        primary_model="mimo-v2.5-pro",
        uncached_input_tokens=500_000,
    )
    champion_before = deepcopy(champion)
    challenger_before = deepcopy(challenger)
    pricing = {
        "currency": "CNY",
        "input_per_million": 3.0,
    }

    result = compare_write_run_summaries(
        champion,
        challenger,
        model_catalog={
            "deepseek-v4-pro": {"pricing": pricing},
            "mimo-v2.5-pro": {"pricing": pricing},
        },
    )

    assert champion == champion_before
    assert challenger == challenger_before
    assert result["schema_version"] == "write_run_comparison_v2"
    assert result["verdict"] == "promote_challenger"
    assert result["cost"]["basis"] == "current_model_catalog"
    assert result["cost"]["champion"]["known_estimated_cost"] == 3.0
    assert result["cost"]["challenger"]["known_estimated_cost"] == 1.5
    assert result["cost"]["champion"]["cost_per_passed_chapter"] == 3.0
    assert result["cost"]["challenger"]["cost_per_passed_chapter"] == 1.5
    assert result["cost"]["cost_per_passed_chapter_delta"] == -1.5
    assert result["cost"]["request_delta"] == 0
    assert result["cost"]["scene_call_delta"] == 0
    assert result["cost"]["repricing"]["champion"]["unpriced_model_names"] == []


@pytest.mark.unit
def test_current_catalog_repricing_requires_complete_pricing_for_promotion() -> None:
    champion = _summary_with_scene_usage(
        primary_model="deepseek-v4-pro",
        uncached_input_tokens=1_000_000,
    )
    challenger = _summary_with_scene_usage(
        primary_model="missing-challenger",
        uncached_input_tokens=500_000,
    )

    result = compare_write_run_summaries(
        champion,
        challenger,
        model_catalog={
            "deepseek-v4-pro": {
                "pricing": {
                    "currency": "CNY",
                    "input_per_million": 3.0,
                }
            }
        },
    )

    assert result["verdict"] == "manual_review"
    assert result["reason_codes"] == ["complete_same_currency_cost_required"]
    assert result["cost"]["comparable"] is False
    assert result["cost"]["repricing"]["challenger"]["unpriced_model_names"] == [
        "missing-challenger"
    ]


@pytest.mark.unit
def test_report_repricing_rebuilds_from_sources_without_mutating_artifact(
    tmp_path: Path,
) -> None:
    champion_dir = tmp_path / "champion"
    challenger_dir = tmp_path / "challenger"
    champion_dir.mkdir()
    challenger_dir.mkdir()
    (champion_dir / "run_summary.json").write_text(
        json.dumps(
            _summary_with_scene_usage(
                primary_model="deepseek-v4-pro",
                uncached_input_tokens=1_000_000,
            )
        ),
        encoding="utf-8",
    )
    (challenger_dir / "run_summary.json").write_text(
        json.dumps(
            _summary_with_scene_usage(
                primary_model="mimo-v2.5-pro",
                uncached_input_tokens=500_000,
            )
        ),
        encoding="utf-8",
    )
    persisted = compare_write_run_paths(champion_dir, challenger_dir)
    comparison_path = persist_write_run_comparison(
        persisted,
        champion_dir / "challenger_comparison.json",
    )
    artifact_before = comparison_path.read_bytes()

    report_comparison = resolve_write_run_comparison_for_report(
        champion_dir,
        model_catalog={
            "deepseek-v4-pro": {
                "pricing": {"currency": "CNY", "input_per_million": 3.0}
            },
            "mimo-v2.5-pro": {
                "pricing": {"currency": "CNY", "input_per_million": 3.0}
            },
        },
    )
    assert report_comparison is not None
    resolved, repriced = report_comparison

    assert repriced is True
    assert resolved["verdict"] == "promote_challenger"
    assert resolved["cost"]["basis"] == "current_model_catalog"
    assert comparison_path.read_bytes() == artifact_before


@pytest.mark.unit
def test_loader_accepts_legacy_v1_comparison_artifact(tmp_path: Path) -> None:
    payload = compare_write_run_summaries(
        _summary(primary_model="deepseek", cost=1.0),
        _summary(primary_model="mimo", cost=0.8),
    )
    payload["schema_version"] = "write_run_comparison_v1"
    path = tmp_path / "challenger_comparison.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    resolved_path, loaded = load_write_run_comparison(path)

    assert resolved_path == path.resolve()
    assert loaded["schema_version"] == "write_run_comparison_v1"
