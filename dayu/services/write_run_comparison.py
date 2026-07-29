"""Deterministic Champion/Challenger comparison for write-run summaries."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from dayu.services.internal.write_pipeline.model_usage_ledger import (
    reprice_model_usage_summary,
)

_COMPARISON_SCHEMA_VERSION = "write_run_comparison_v2"
_COMPARISON_FILE_NAME = "challenger_comparison.json"
_SUMMARY_FILE_NAME = "run_summary.json"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _optional_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _routing_route_totals(value: object) -> tuple[int, int] | None:
    if not isinstance(value, list):
        return None
    completed_count = 0
    error_count = 0
    for raw_route in value:
        if not isinstance(raw_route, Mapping):
            return None
        switch_count = _optional_non_negative_int(raw_route.get("switch_count"))
        status = str(raw_route.get("fallback_call_status") or "")
        if switch_count is None or switch_count <= 0:
            return None
        if status == "completed":
            completed_count += switch_count
        elif status == "error":
            error_count += switch_count
        else:
            return None
    return completed_count, error_count


def _summary_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_dir():
        candidate = candidate / _SUMMARY_FILE_NAME
    return candidate


def _comparison_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_dir():
        candidate = candidate / _COMPARISON_FILE_NAME
    return candidate


def load_write_run_summary(path: str | Path) -> tuple[Path, dict[str, Any]]:
    """Load one write summary from either its file or output directory."""

    summary_path = _summary_path(path)
    if not summary_path.is_file():
        raise FileNotFoundError(f"write run summary does not exist: {summary_path}")
    try:
        raw = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid write run summary JSON: {summary_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"write run summary must be a JSON object: {summary_path}")
    schema_version = str(raw.get("schema_version") or "")
    if not schema_version.startswith("write_run_summary_v"):
        raise ValueError(
            f"unsupported write run summary schema {schema_version!r}: {summary_path}"
        )
    return summary_path, raw


def load_write_run_comparison(path: str | Path) -> tuple[Path, dict[str, Any]]:
    """Load one versioned comparison artifact from a file or Champion directory."""

    comparison_path = _comparison_path(path)
    if not comparison_path.is_file():
        raise FileNotFoundError(
            f"write run comparison does not exist: {comparison_path}"
        )
    try:
        raw = json.loads(comparison_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid write run comparison JSON: {comparison_path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError(
            f"write run comparison must be a JSON object: {comparison_path}"
        )
    schema_version = str(raw.get("schema_version") or "")
    if not schema_version.startswith("write_run_comparison_v"):
        raise ValueError(
            f"unsupported write run comparison schema {schema_version!r}: "
            f"{comparison_path}"
        )
    return comparison_path, raw


def _quality_values(summary: Mapping[str, Any]) -> dict[str, int]:
    audit = _mapping(summary.get("audit"))
    return {
        "gate_passed": 1 if summary.get("gate_status") == "passed" else 0,
        "failed_count": _non_negative_int(summary.get("failed_count")),
        "audit_failed_count": _non_negative_int(audit.get("failed_count")),
        "gate_blocked_count": _non_negative_int(audit.get("gate_blocked_count")),
        "first_pass_count": _non_negative_int(audit.get("first_pass_count")),
        "total_retries": _non_negative_int(audit.get("total_retries")),
    }


def _compare_quality_metrics(
    champion: Mapping[str, Any],
    challenger: Mapping[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    champion_values = _quality_values(champion)
    challenger_values = _quality_values(challenger)
    higher_is_better = {"gate_passed", "first_pass_count"}
    comparisons: list[dict[str, Any]] = []
    oriented_deltas: list[int] = []
    for name, champion_value in champion_values.items():
        challenger_value = challenger_values[name]
        raw_delta = challenger_value - champion_value
        oriented_delta = raw_delta if name in higher_is_better else -raw_delta
        oriented_deltas.append(oriented_delta)
        comparisons.append(
            {
                "metric": name,
                "preference": "higher" if name in higher_is_better else "lower",
                "champion": champion_value,
                "challenger": challenger_value,
                "delta": raw_delta,
                "assessment": (
                    "improved"
                    if oriented_delta > 0
                    else "regressed"
                    if oriented_delta < 0
                    else "equivalent"
                ),
            }
        )
    if all(delta == 0 for delta in oriented_deltas):
        return "equivalent", comparisons
    if all(delta >= 0 for delta in oriented_deltas):
        return "improved", comparisons
    if all(delta <= 0 for delta in oriented_deltas):
        return "regressed", comparisons
    return "mixed", comparisons


def _chapter_map(summary: Mapping[str, Any]) -> dict[tuple[int, str], Mapping[str, Any]]:
    chapters = summary.get("chapters")
    if not isinstance(chapters, list):
        return {}
    result: dict[tuple[int, str], Mapping[str, Any]] = {}
    for raw in chapters:
        chapter = _mapping(raw)
        index = chapter.get("index")
        title = chapter.get("title")
        if isinstance(index, bool) or not isinstance(index, int) or not isinstance(title, str):
            continue
        result[(index, title)] = chapter
    return result


def _compare_chapters(
    champion: Mapping[str, Any],
    challenger: Mapping[str, Any],
) -> dict[str, Any]:
    champion_chapters = _chapter_map(champion)
    challenger_chapters = _chapter_map(challenger)
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    for key in sorted(champion_chapters.keys() & challenger_chapters.keys()):
        champion_chapter = champion_chapters[key]
        challenger_chapter = challenger_chapters[key]
        champion_gate = champion_chapter.get("gate_passed") is True
        challenger_gate = challenger_chapter.get("gate_passed") is True
        champion_audit = champion_chapter.get("audit_passed") is True
        challenger_audit = challenger_chapter.get("audit_passed") is True
        record = {"index": key[0], "title": key[1]}
        if champion_gate and not challenger_gate:
            regressions.append({**record, "reason": "gate_passed_to_blocked"})
        elif not champion_gate and challenger_gate:
            improvements.append({**record, "reason": "gate_blocked_to_passed"})
        if champion_audit and not challenger_audit:
            regressions.append({**record, "reason": "audit_passed_to_failed"})
        elif not champion_audit and challenger_audit:
            improvements.append({**record, "reason": "audit_failed_to_passed"})
    return {
        "champion_chapter_count": len(champion_chapters),
        "challenger_chapter_count": len(challenger_chapters),
        "regressions": regressions,
        "improvements": improvements,
    }


def _cost_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    model_usage = _mapping(summary.get("model_usage"))
    cost = _mapping(model_usage.get("cost"))
    raw_value = cost.get("known_estimated_cost")
    value = (
        float(raw_value)
        if isinstance(raw_value, (int, float))
        and not isinstance(raw_value, bool)
        and math.isfinite(float(raw_value))
        and raw_value >= 0
        else None
    )
    currency_value = cost.get("currency")
    passed_chapter_count = sum(
        1 for chapter in _chapter_map(summary).values() if chapter.get("gate_passed") is True
    )
    cost_per_passed_chapter = (
        value / passed_chapter_count
        if value is not None
        and str(cost.get("status") or "unavailable") == "complete"
        and passed_chapter_count > 0
        else None
    )
    return {
        "status": str(cost.get("status") or "unavailable"),
        "currency": str(currency_value) if currency_value else None,
        "known_estimated_cost": value,
        "total_tokens": _non_negative_int(model_usage.get("total_tokens")),
        "request_count": _non_negative_int(model_usage.get("request_count")),
        "scene_call_count": _non_negative_int(model_usage.get("scene_call_count")),
        "usage_status": str(model_usage.get("usage_status") or "unavailable"),
        "passed_chapter_count": passed_chapter_count,
        "cost_per_passed_chapter": cost_per_passed_chapter,
    }


def _cost_repricing_view(summary: Mapping[str, Any]) -> dict[str, Any] | None:
    model_usage = _mapping(summary.get("model_usage"))
    repricing = model_usage.get("cost_repricing")
    if not isinstance(repricing, Mapping):
        return None
    return dict(repricing)


def _compare_cost(
    champion: Mapping[str, Any],
    challenger: Mapping[str, Any],
    *,
    basis: str,
) -> dict[str, Any]:
    champion_cost = _cost_view(champion)
    challenger_cost = _cost_view(challenger)
    comparable = (
        champion_cost["status"] == "complete"
        and challenger_cost["status"] == "complete"
        and champion_cost["currency"] is not None
        and champion_cost["currency"] == challenger_cost["currency"]
        and champion_cost["known_estimated_cost"] is not None
        and challenger_cost["known_estimated_cost"] is not None
    )
    cost_delta: float | None = None
    cost_ratio: float | None = None
    unit_cost_delta: float | None = None
    champion_raw_value = champion_cost["known_estimated_cost"]
    challenger_raw_value = challenger_cost["known_estimated_cost"]
    if (
        comparable
        and isinstance(champion_raw_value, (int, float))
        and not isinstance(champion_raw_value, bool)
        and isinstance(challenger_raw_value, (int, float))
        and not isinstance(challenger_raw_value, bool)
    ):
        champion_value = float(champion_raw_value)
        challenger_value = float(challenger_raw_value)
        cost_delta = challenger_value - champion_value
        if champion_value > 0:
            cost_ratio = challenger_value / champion_value
        champion_unit_cost = champion_cost["cost_per_passed_chapter"]
        challenger_unit_cost = challenger_cost["cost_per_passed_chapter"]
        if isinstance(champion_unit_cost, (int, float)) and isinstance(
            challenger_unit_cost, (int, float)
        ):
            unit_cost_delta = float(challenger_unit_cost) - float(champion_unit_cost)
    return {
        "basis": basis,
        "comparable": comparable,
        "champion": champion_cost,
        "challenger": challenger_cost,
        "cost_delta": cost_delta,
        "challenger_to_champion_ratio": cost_ratio,
        "cost_per_passed_chapter_delta": unit_cost_delta,
        "token_delta": challenger_cost["total_tokens"] - champion_cost["total_tokens"],
        "request_delta": challenger_cost["request_count"] - champion_cost["request_count"],
        "scene_call_delta": challenger_cost["scene_call_count"]
        - champion_cost["scene_call_count"],
        "repricing": {
            "champion": _cost_repricing_view(champion),
            "challenger": _cost_repricing_view(challenger),
        },
    }


def build_write_run_routing_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize and validate the additive fallback-routing receipt."""

    model_usage = _mapping(summary.get("model_usage"))
    scene_call_count = _optional_non_negative_int(
        model_usage.get("scene_call_count")
    )
    raw_routing = summary.get("model_routing")
    if not isinstance(raw_routing, Mapping):
        return {
            "status": "missing",
            "fallback_switch_count": None,
            "fallback_call_completed_count": None,
            "fallback_call_error_count": None,
            "fallback_call_completion_rate": None,
            "scene_call_count": scene_call_count,
            "fallback_scene_call_share": None,
        }

    switch_count = _optional_non_negative_int(
        raw_routing.get("fallback_switch_count")
    )
    completed_count = _optional_non_negative_int(
        raw_routing.get("fallback_call_completed_count")
    )
    error_count = _optional_non_negative_int(
        raw_routing.get("fallback_call_error_count")
    )
    if (
        switch_count is None
        or completed_count is None
        or error_count is None
    ):
        return {
            "status": "invalid",
            "fallback_switch_count": switch_count,
            "fallback_call_completed_count": completed_count,
            "fallback_call_error_count": error_count,
            "fallback_call_completion_rate": None,
            "scene_call_count": scene_call_count,
            "fallback_scene_call_share": None,
        }
    if (
        completed_count + error_count != switch_count
        or (
            scene_call_count is not None
            and switch_count > scene_call_count
        )
        or _routing_route_totals(raw_routing.get("routes"))
        != (completed_count, error_count)
    ):
        return {
            "status": "invalid",
            "fallback_switch_count": switch_count,
            "fallback_call_completed_count": completed_count,
            "fallback_call_error_count": error_count,
            "fallback_call_completion_rate": None,
            "scene_call_count": scene_call_count,
            "fallback_scene_call_share": None,
        }
    return {
        "status": "complete",
        "fallback_switch_count": switch_count,
        "fallback_call_completed_count": completed_count,
        "fallback_call_error_count": error_count,
        "fallback_call_completion_rate": (
            completed_count / switch_count if switch_count > 0 else None
        ),
        "scene_call_count": scene_call_count,
        "fallback_scene_call_share": (
            switch_count / scene_call_count
            if scene_call_count is not None and scene_call_count > 0
            else None
        ),
    }


def _compare_routing(
    champion: Mapping[str, Any],
    challenger: Mapping[str, Any],
) -> dict[str, Any]:
    champion_routing = build_write_run_routing_view(champion)
    challenger_routing = build_write_run_routing_view(challenger)
    comparable = (
        champion_routing["status"] == "complete"
        and challenger_routing["status"] == "complete"
    )
    integrity_issue = (
        champion_routing["status"] == "invalid"
        or challenger_routing["status"] == "invalid"
    )
    if not comparable:
        return {
            "comparable": False,
            "integrity_issue": integrity_issue,
            "status": "invalid" if integrity_issue else "unavailable",
            "champion": champion_routing,
            "challenger": challenger_routing,
            "fallback_switch_delta": None,
            "fallback_call_error_delta": None,
            "fallback_call_completion_rate_delta": None,
            "fallback_scene_call_share_delta": None,
        }

    champion_switches = int(champion_routing["fallback_switch_count"])
    challenger_switches = int(challenger_routing["fallback_switch_count"])
    champion_errors = int(champion_routing["fallback_call_error_count"])
    challenger_errors = int(challenger_routing["fallback_call_error_count"])
    switch_delta = challenger_switches - champion_switches
    error_delta = challenger_errors - champion_errors
    oriented_deltas = (-switch_delta, -error_delta)
    if all(delta == 0 for delta in oriented_deltas):
        status = "equivalent"
    elif all(delta >= 0 for delta in oriented_deltas):
        status = "improved"
    elif all(delta <= 0 for delta in oriented_deltas):
        status = "regressed"
    else:
        status = "mixed"

    champion_completion_rate = champion_routing[
        "fallback_call_completion_rate"
    ]
    challenger_completion_rate = challenger_routing[
        "fallback_call_completion_rate"
    ]
    completion_rate_delta = (
        float(challenger_completion_rate) - float(champion_completion_rate)
        if isinstance(champion_completion_rate, (int, float))
        and isinstance(challenger_completion_rate, (int, float))
        else None
    )
    champion_scene_share = champion_routing["fallback_scene_call_share"]
    challenger_scene_share = challenger_routing["fallback_scene_call_share"]
    scene_share_delta = (
        float(challenger_scene_share) - float(champion_scene_share)
        if isinstance(champion_scene_share, (int, float))
        and isinstance(challenger_scene_share, (int, float))
        else None
    )
    return {
        "comparable": True,
        "integrity_issue": False,
        "status": status,
        "champion": champion_routing,
        "challenger": challenger_routing,
        "fallback_switch_delta": switch_delta,
        "fallback_call_error_delta": error_delta,
        "fallback_call_completion_rate_delta": completion_rate_delta,
        "fallback_scene_call_share_delta": scene_share_delta,
    }


def _model_role_names(summary: Mapping[str, Any]) -> dict[str, list[str]]:
    roles = _mapping(summary.get("model_roles"))
    result: dict[str, list[str]] = {}
    for role_name in ("primary", "audit"):
        role = _mapping(roles.get(role_name))
        names = role.get("model_names")
        if isinstance(names, list):
            result[role_name] = sorted(str(name) for name in names if str(name).strip())
        else:
            result[role_name] = []
    return result


def compare_write_run_summaries(
    champion_summary: Mapping[str, Any],
    challenger_summary: Mapping[str, Any],
    *,
    champion_path: str | Path | None = None,
    challenger_path: str | Path | None = None,
    model_catalog: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """Compare two completed write runs without invoking a model."""

    cost_basis = "persisted_run_summary"
    effective_champion: Mapping[str, Any] = champion_summary
    effective_challenger: Mapping[str, Any] = challenger_summary
    if model_catalog is not None:
        champion_usage = champion_summary.get("model_usage")
        challenger_usage = challenger_summary.get("model_usage")
        if not isinstance(champion_usage, Mapping):
            raise ValueError("Champion run summary lacks model_usage for repricing")
        if not isinstance(challenger_usage, Mapping):
            raise ValueError("Challenger run summary lacks model_usage for repricing")
        repriced_champion = dict(champion_summary)
        repriced_challenger = dict(challenger_summary)
        repriced_champion["model_usage"] = reprice_model_usage_summary(
            champion_usage,
            model_catalog,
        )
        repriced_challenger["model_usage"] = reprice_model_usage_summary(
            challenger_usage,
            model_catalog,
        )
        effective_champion = repriced_champion
        effective_challenger = repriced_challenger
        cost_basis = "current_model_catalog"

    compatibility_issues: list[str] = []
    if effective_champion.get("ticker") != effective_challenger.get("ticker"):
        compatibility_issues.append("ticker_mismatch")
    champion_chapters = _chapter_map(effective_champion)
    challenger_chapters = _chapter_map(effective_challenger)
    if not champion_chapters or not challenger_chapters:
        compatibility_issues.append("missing_chapter_results")
    if set(champion_chapters) != set(challenger_chapters):
        compatibility_issues.append("chapter_set_mismatch")

    champion_audit = _mapping(effective_champion.get("audit"))
    challenger_audit = _mapping(effective_challenger.get("audit"))
    champion_audit_required = champion_audit.get("required") is True
    challenger_audit_required = challenger_audit.get("required") is True
    if champion_audit_required != challenger_audit_required:
        compatibility_issues.append("audit_requirement_mismatch")

    quality_status, metric_comparisons = _compare_quality_metrics(
        effective_champion,
        effective_challenger,
    )
    chapter_comparison = _compare_chapters(effective_champion, effective_challenger)
    cost_comparison = _compare_cost(
        effective_champion,
        effective_challenger,
        basis=cost_basis,
    )
    routing_comparison = _compare_routing(
        effective_champion,
        effective_challenger,
    )
    champion_models = _model_role_names(effective_champion)
    challenger_models = _model_role_names(effective_challenger)
    model_plan_changed = champion_models != challenger_models

    hard_quality_regression = bool(chapter_comparison["regressions"])
    hard_quality_regression = hard_quality_regression or any(
        item["assessment"] == "regressed"
        for item in metric_comparisons
        if item["metric"]
        in {"gate_passed", "failed_count", "audit_failed_count", "gate_blocked_count"}
    )
    reasons: list[str] = []
    if compatibility_issues:
        verdict = "keep_champion"
        reasons.extend(compatibility_issues)
    elif hard_quality_regression or quality_status == "regressed":
        verdict = "keep_champion"
        reasons.append("challenger_quality_regressed")
    elif quality_status == "mixed":
        verdict = "manual_review"
        reasons.append("mixed_quality_changes")
    elif not model_plan_changed:
        verdict = "manual_review"
        reasons.append("model_plan_unchanged")
    elif not champion_audit_required or not challenger_audit_required:
        verdict = "manual_review"
        reasons.append("audited_comparison_required_for_promotion")
    elif not cost_comparison["comparable"]:
        verdict = "manual_review"
        reasons.append("complete_same_currency_cost_required")
    else:
        verdict = "manual_review"
        cost_delta = float(cost_comparison["cost_delta"])
        promotion_reason: str | None = None
        if quality_status == "improved" and cost_delta <= 0:
            promotion_reason = "quality_improved_without_cost_increase"
        elif quality_status == "equivalent" and cost_delta < 0:
            promotion_reason = "equivalent_quality_at_lower_cost"
        elif quality_status == "equivalent" and cost_delta > 0:
            verdict = "keep_champion"
            reasons.append("equivalent_quality_at_higher_cost")
        else:
            verdict = "manual_review"
            reasons.append("quality_cost_tradeoff_requires_review")
        if promotion_reason is not None:
            routing_status = routing_comparison["status"]
            if routing_comparison["integrity_issue"]:
                verdict = "manual_review"
                reasons.append("invalid_fallback_routing_receipt")
            elif (
                routing_comparison["comparable"]
                and routing_status == "regressed"
            ):
                verdict = "manual_review"
                reasons.append("challenger_fallback_routing_regressed")
            elif (
                routing_comparison["comparable"]
                and routing_status == "mixed"
            ):
                verdict = "manual_review"
                reasons.append("mixed_fallback_routing_changes")
            else:
                verdict = "promote_challenger"
                reasons.append(promotion_reason)

    warnings: list[str] = []
    if not model_plan_changed:
        warnings.append("Champion and Challenger resolved to the same model-role plan.")
    if not cost_comparison["comparable"]:
        warnings.append("Configured cost is incomplete or uses different currencies.")
    if routing_comparison["integrity_issue"]:
        warnings.append(
            "Fallback routing receipt is internally inconsistent."
        )
    elif not routing_comparison["comparable"]:
        warnings.append(
            "Fallback routing is missing or invalid in one or both run summaries."
        )
    elif routing_comparison["status"] in {"regressed", "mixed"}:
        warnings.append(
            "Challenger fallback routing needs operator review before promotion."
        )

    return {
        "schema_version": _COMPARISON_SCHEMA_VERSION,
        "ticker": effective_champion.get("ticker"),
        "verdict": verdict,
        "reason_codes": reasons,
        "compatible": not compatibility_issues,
        "compatibility_issues": compatibility_issues,
        "sources": {
            "champion": str(champion_path) if champion_path is not None else None,
            "challenger": str(challenger_path) if challenger_path is not None else None,
        },
        "model_plans": {
            "changed": model_plan_changed,
            "champion": champion_models,
            "challenger": challenger_models,
        },
        "quality": {
            "status": quality_status,
            "metrics": metric_comparisons,
            "chapters": chapter_comparison,
        },
        "routing": routing_comparison,
        "cost": cost_comparison,
        "warnings": warnings,
    }


def compare_write_run_paths(
    champion_path: str | Path,
    challenger_path: str | Path,
    *,
    model_catalog: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """Load and compare two write-run summary paths."""

    resolved_champion_path, champion = load_write_run_summary(champion_path)
    resolved_challenger_path, challenger = load_write_run_summary(challenger_path)
    return compare_write_run_summaries(
        champion,
        challenger,
        champion_path=resolved_champion_path,
        challenger_path=resolved_challenger_path,
        model_catalog=model_catalog,
    )


def resolve_write_run_comparison_for_report(
    champion_output_dir: str | Path,
    *,
    model_catalog: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[dict[str, Any], bool] | None:
    """Load a comparison and optionally rebuild its costs from current rates."""

    comparison_path = _comparison_path(champion_output_dir)
    if not comparison_path.is_file():
        return None
    _resolved_path, comparison = load_write_run_comparison(comparison_path)
    if model_catalog is None:
        return comparison, False
    sources = _mapping(comparison.get("sources"))
    champion_source = sources.get("champion")
    challenger_source = sources.get("challenger")
    if not isinstance(champion_source, str) or not champion_source.strip():
        raise ValueError("comparison artifact lacks Champion run-summary source")
    if not isinstance(challenger_source, str) or not challenger_source.strip():
        raise ValueError("comparison artifact lacks Challenger run-summary source")
    return (
        compare_write_run_paths(
            champion_source,
            challenger_source,
            model_catalog=model_catalog,
        ),
        True,
    )


def _format_comparison_cost(value: object) -> str:
    view = _mapping(value)
    raw_cost = view.get("known_estimated_cost")
    status = str(view.get("status") or "unavailable")
    currency = str(view.get("currency") or "").strip().upper()
    if (
        isinstance(raw_cost, (int, float))
        and not isinstance(raw_cost, bool)
        and math.isfinite(float(raw_cost))
        and float(raw_cost) >= 0
    ):
        return f"{currency or 'UNKNOWN'} {float(raw_cost):.6f} ({status})"
    return f"不可用 ({status})"


def _format_comparison_delta(value: object, *, currency: str | None = None) -> str:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        return "不可比"
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{float(value):+.6f}"


def _format_comparison_unit_cost(value: object) -> str:
    view = _mapping(value)
    raw_cost = view.get("cost_per_passed_chapter")
    currency = str(view.get("currency") or "").strip().upper()
    if (
        isinstance(raw_cost, (int, float))
        and not isinstance(raw_cost, bool)
        and math.isfinite(float(raw_cost))
        and float(raw_cost) >= 0
    ):
        return f"{currency or 'UNKNOWN'} {float(raw_cost):.6f}"
    return "不可用"


def _format_count_delta(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        return "不可用"
    return f"{value:+,}"


def _format_percentage(value: object) -> str:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        return "不适用"
    return f"{float(value):.1%}"


def _format_routing_view(value: object) -> str:
    view = _mapping(value)
    status = str(view.get("status") or "missing")
    if status == "missing":
        return "未记录"
    if status != "complete":
        return "无效"
    switch_count = _optional_non_negative_int(
        view.get("fallback_switch_count")
    )
    if switch_count is None:
        return "无效"
    return (
        f"{switch_count:,} "
        f"(完成率 {_format_percentage(view.get('fallback_call_completion_rate'))} / "
        f"Scene占比 {_format_percentage(view.get('fallback_scene_call_share'))})"
    )


def format_write_run_comparison_report(
    comparison: Mapping[str, Any],
    *,
    repriced: bool,
) -> tuple[str, ...]:
    """Format a compact operator-facing comparison receipt."""

    quality = _mapping(comparison.get("quality"))
    cost = _mapping(comparison.get("cost"))
    raw_routing = comparison.get("routing")
    routing = _mapping(raw_routing)
    champion_cost = _mapping(cost.get("champion"))
    challenger_cost = _mapping(cost.get("challenger"))
    currency_value = champion_cost.get("currency")
    currency = str(currency_value).strip().upper() if currency_value else None
    reason_codes = comparison.get("reason_codes")
    reasons = (
        ", ".join(str(item) for item in reason_codes)
        if isinstance(reason_codes, list)
        else "未记录"
    )
    lines = [
        "",
        "=" * 60,
        "  Champion/Challenger 对比",
        "=" * 60,
        f"  推荐结论   : {str(comparison.get('verdict') or 'unknown')}",
        f"  质量状态   : {str(quality.get('status') or 'unknown')}",
        f"  成本口径   : {str(cost.get('basis') or 'unknown')}",
        f"  Champion   : {_format_comparison_cost(champion_cost)}",
        f"  Challenger : {_format_comparison_cost(challenger_cost)}",
        f"  成本差额   : {_format_comparison_delta(cost.get('cost_delta'), currency=currency)}",
        f"  Champion/章: {_format_comparison_unit_cost(champion_cost)}",
        f"  挑战者/章  : {_format_comparison_unit_cost(challenger_cost)}",
        "  单位章节差 : "
        + _format_comparison_delta(
            cost.get("cost_per_passed_chapter_delta"),
            currency=currency,
        ),
        f"  Token 差额 : {_format_count_delta(cost.get('token_delta'))}",
        f"  请求差额   : {_format_count_delta(cost.get('request_delta'))}",
        f"  Scene 差额 : {_format_count_delta(cost.get('scene_call_delta'))}",
        f"  原因代码   : {reasons or '未记录'}",
    ]
    if isinstance(raw_routing, Mapping):
        lines.extend(
            [
                f"  路由状态   : {str(routing.get('status') or 'unavailable')}",
                f"  Champion备 : {_format_routing_view(routing.get('champion'))}",
                f"  挑战者备   : {_format_routing_view(routing.get('challenger'))}",
                "  后备切换差 : "
                + _format_count_delta(routing.get("fallback_switch_delta")),
                "  后备错误差 : "
                + _format_count_delta(routing.get("fallback_call_error_delta")),
            ]
        )
    else:
        lines.append("  路由状态   : 未记录")
    if repriced:
        lines.append("  计价说明   : 当前模型目录只读重估，未改写历史产物")
    lines.extend(["=" * 60, ""])
    return tuple(lines)


def persist_write_run_comparison(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    """Persist a comparison artifact and return its resolved path."""

    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return target
