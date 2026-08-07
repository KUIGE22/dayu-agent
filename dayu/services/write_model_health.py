"""Read-only historical health trends for write-model routing."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from dayu.services.internal.write_pipeline.model_usage_ledger import (
    model_role_for_scene,
    reprice_model_usage_summary,
)
from dayu.services.write_model_challenger_proposal import (
    build_write_model_challenger_proposal,
)
from dayu.services.write_run_comparison import build_write_run_routing_view

_TREND_SCHEMA_VERSION = "write_model_health_trend_v1"
_SUMMARY_FILE_NAME = "run_summary.json"
_MIN_TREND_WINDOW_RUNS = 3
_MIN_MODEL_SCENE_CALLS = 5
_MIN_FALLBACK_CALLS = 2
_DEGRADED_PRIMARY_SWITCH_SHARE = 0.20
_DEGRADED_FALLBACK_ERROR_RATE = 0.25
_DEGRADED_FALLBACK_SHARE_DELTA = 0.10
_WATCH_FALLBACK_SHARE_DELTA = 0.05
_WATCH_COST_PER_SCENE_RATIO = 0.25
_WATCH_GATE_PASS_RATE_DELTA = -0.10


@dataclass(frozen=True)
class _RunObservation:
    path: Path
    completed_at: datetime
    timestamp_source: str
    summary_fingerprint: str
    summary: dict[str, Any]
    routing: dict[str, Any]


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _finite_non_negative_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    resolved = float(value)
    if not math.isfinite(resolved) or resolved < 0:
        return None
    return resolved


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _fingerprint(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _positive_int(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _parse_completed_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _discover_summary_paths(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.name == _SUMMARY_FILE_NAME else []
    if not root.is_dir():
        raise FileNotFoundError(f"routing history root does not exist: {root}")
    return sorted(
        {
            candidate.resolve()
            for candidate in root.rglob(_SUMMARY_FILE_NAME)
            if candidate.is_file()
        },
        key=str,
    )


def _load_observation(
    path: Path,
    *,
    model_catalog: Mapping[str, Mapping[str, object]] | None,
) -> tuple[_RunObservation | None, str | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, f"{path}: unreadable_run_summary"
    if not isinstance(raw, dict):
        return None, f"{path}: invalid_run_summary_object"
    try:
        summary_fingerprint = _fingerprint(raw)
    except (TypeError, ValueError):
        return None, f"{path}: invalid_run_summary_value"
    schema_version = str(raw.get("schema_version") or "")
    if not schema_version.startswith("write_run_summary_v"):
        return None, f"{path}: unsupported_run_summary_schema"

    raw_completed_at = raw.get("completed_at")
    if raw_completed_at is None:
        try:
            completed_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            return None, f"{path}: unavailable_summary_timestamp"
        timestamp_source = "file_mtime"
    else:
        completed_at = _parse_completed_at(raw_completed_at)
        if completed_at is None:
            return None, f"{path}: invalid_completed_at"
        timestamp_source = "summary"

    summary = dict(raw)
    if model_catalog is not None:
        raw_usage = summary.get("model_usage")
        if isinstance(raw_usage, Mapping):
            try:
                summary["model_usage"] = reprice_model_usage_summary(
                    raw_usage,
                    model_catalog,
                )
            except ValueError:
                usage = dict(raw_usage)
                usage["cost"] = {
                    "status": "unavailable",
                    "currency": None,
                    "known_estimated_cost": None,
                }
                summary["model_usage"] = usage

    return (
        _RunObservation(
            path=path,
            completed_at=completed_at,
            timestamp_source=timestamp_source,
            summary_fingerprint=summary_fingerprint,
            summary=summary,
            routing=build_write_run_routing_view(summary),
        ),
        None,
    )


def _cost_summary(records: list[_RunObservation], *, scene_call_count: int) -> dict[str, Any]:
    observations: list[tuple[str, float]] = []
    for record in records:
        cost = _mapping(_mapping(record.summary.get("model_usage")).get("cost"))
        currency = str(cost.get("currency") or "").strip().upper()
        value = _finite_non_negative_float(cost.get("known_estimated_cost"))
        if cost.get("status") == "complete" and currency and value is not None:
            observations.append((currency, value))

    currencies = {currency for currency, _value in observations}
    priced_run_count = len(observations)
    unpriced_run_count = len(records) - priced_run_count
    if not observations:
        status = "unavailable"
        currency: str | None = None
        total_cost: float | None = None
    elif len(currencies) != 1:
        status = "mixed_currency"
        currency = "MIXED"
        total_cost = None
    else:
        status = "complete" if not unpriced_run_count else "partial"
        currency = next(iter(currencies))
        total_cost = sum(value for _currency, value in observations)
    return {
        "status": status,
        "currency": currency,
        "known_estimated_cost": total_cost,
        "cost_per_scene": (
            total_cost / scene_call_count
            if total_cost is not None and scene_call_count > 0
            else None
        ),
        "priced_run_count": priced_run_count,
        "unpriced_run_count": unpriced_run_count,
    }


def _history_fingerprint(records: Sequence[_RunObservation]) -> str:
    return _fingerprint(
        [record.summary_fingerprint for record in records]
    )


def _aggregate_runs(records: list[_RunObservation]) -> dict[str, Any]:
    scene_call_count = sum(
        _non_negative_int(_mapping(record.summary.get("model_usage")).get("scene_call_count"))
        for record in records
    )
    total_tokens = sum(
        _non_negative_int(_mapping(record.summary.get("model_usage")).get("total_tokens"))
        for record in records
    )
    gate_observations = [
        str(record.summary.get("gate_status"))
        for record in records
        if record.summary.get("gate_status") in {"passed", "blocked"}
    ]
    routing_records = [
        record for record in records if record.routing.get("status") == "complete"
    ]
    routing_scene_call_count = sum(
        _non_negative_int(record.routing.get("scene_call_count"))
        for record in routing_records
    )
    fallback_switch_count = sum(
        _non_negative_int(record.routing.get("fallback_switch_count"))
        for record in routing_records
    )
    fallback_completed_count = sum(
        _non_negative_int(record.routing.get("fallback_call_completed_count"))
        for record in routing_records
    )
    fallback_error_count = sum(
        _non_negative_int(record.routing.get("fallback_call_error_count"))
        for record in routing_records
    )
    return {
        "run_count": len(records),
        "gate_observed_run_count": len(gate_observations),
        "gate_passed_run_count": gate_observations.count("passed"),
        "gate_pass_rate": (
            gate_observations.count("passed") / len(gate_observations)
            if gate_observations
            else None
        ),
        "scene_call_count": scene_call_count,
        "total_tokens": total_tokens,
        "routing_observed_run_count": len(routing_records),
        "routing_scene_call_count": routing_scene_call_count,
        "fallback_switch_count": fallback_switch_count,
        "fallback_call_completed_count": fallback_completed_count,
        "fallback_call_error_count": fallback_error_count,
        "fallback_switch_share": (
            fallback_switch_count / routing_scene_call_count
            if routing_scene_call_count > 0
            else None
        ),
        "fallback_completion_rate": (
            fallback_completed_count / fallback_switch_count
            if fallback_switch_count > 0
            else None
        ),
        "fallback_error_rate": (
            fallback_error_count / fallback_switch_count
            if fallback_switch_count > 0
            else None
        ),
        "cost": _cost_summary(records, scene_call_count=scene_call_count),
    }


def _numeric_delta(recent: object, baseline: object) -> float | None:
    if not isinstance(recent, (int, float)) or isinstance(recent, bool):
        return None
    if not isinstance(baseline, (int, float)) or isinstance(baseline, bool):
        return None
    return float(recent) - float(baseline)


def _cost_delta(recent: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    recent_cost = _mapping(recent.get("cost"))
    baseline_cost = _mapping(baseline.get("cost"))
    recent_value = _finite_non_negative_float(recent_cost.get("cost_per_scene"))
    baseline_value = _finite_non_negative_float(baseline_cost.get("cost_per_scene"))
    comparable = bool(
        recent_cost.get("status") == "complete"
        and baseline_cost.get("status") == "complete"
        and recent_cost.get("currency") == baseline_cost.get("currency")
        and recent_value is not None
        and baseline_value is not None
    )
    ratio: float | None = None
    delta: float | None = None
    if comparable and recent_value is not None and baseline_value is not None:
        delta = recent_value - baseline_value
        if baseline_value > 0:
            ratio = recent_value / baseline_value - 1
        elif recent_value == 0:
            ratio = 0.0
    return {
        "cost_comparable": comparable,
        "cost_currency": (
            str(recent_cost.get("currency")) if comparable else None
        ),
        "cost_per_scene_delta": delta,
        "cost_per_scene_ratio": ratio,
    }


def _aggregate_models(
    records: list[_RunObservation],
) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "run_paths": set(),
            "observed_scene_call_count": 0,
            "primary_fallback_switch_count": 0,
            "fallback_call_count": 0,
            "fallback_completed_count": 0,
            "fallback_error_count": 0,
        }
    )
    for record in records:
        usage = _mapping(record.summary.get("model_usage"))
        raw_scenes = usage.get("by_scene")
        if isinstance(raw_scenes, list):
            for raw_scene in raw_scenes:
                if not isinstance(raw_scene, Mapping):
                    continue
                model_name = str(raw_scene.get("model_name") or "").strip()
                if not model_name:
                    continue
                values[model_name]["run_paths"].add(str(record.path))
                values[model_name]["observed_scene_call_count"] += _non_negative_int(
                    raw_scene.get("scene_call_count")
                )
        if record.routing.get("status") != "complete":
            continue
        raw_routes = _mapping(record.summary.get("model_routing")).get("routes")
        if not isinstance(raw_routes, list):
            continue
        for raw_route in raw_routes:
            if not isinstance(raw_route, Mapping):
                continue
            switch_count = _non_negative_int(raw_route.get("switch_count"))
            if switch_count <= 0:
                continue
            primary_model = str(
                raw_route.get("primary_model_name") or ""
            ).strip()
            fallback_model = str(
                raw_route.get("fallback_model_name") or ""
            ).strip()
            status = str(raw_route.get("fallback_call_status") or "").strip()
            if primary_model:
                values[primary_model]["primary_fallback_switch_count"] += (
                    switch_count
                )
            if fallback_model:
                values[fallback_model]["fallback_call_count"] += switch_count
                if status == "completed":
                    values[fallback_model]["fallback_completed_count"] += (
                        switch_count
                    )
                elif status == "error":
                    values[fallback_model]["fallback_error_count"] += switch_count

    result: dict[str, dict[str, Any]] = {}
    for model_name, value in values.items():
        observed_calls = int(value["observed_scene_call_count"])
        primary_switches = int(value["primary_fallback_switch_count"])
        fallback_calls = int(value["fallback_call_count"])
        fallback_completed = int(value["fallback_completed_count"])
        fallback_errors = int(value["fallback_error_count"])
        result[model_name] = {
            "run_count": len(value["run_paths"]),
            "observed_scene_call_count": observed_calls,
            "primary_fallback_switch_count": primary_switches,
            "primary_switch_share": (
                primary_switches / observed_calls if observed_calls > 0 else None
            ),
            "fallback_call_count": fallback_calls,
            "fallback_completed_count": fallback_completed,
            "fallback_error_count": fallback_errors,
            "fallback_completion_rate": (
                fallback_completed / fallback_calls
                if fallback_calls > 0
                else None
            ),
            "fallback_error_rate": (
                fallback_errors / fallback_calls if fallback_calls > 0 else None
            ),
        }
    return result


def _aggregate_route_pairs(
    records: list[_RunObservation],
) -> list[dict[str, Any]]:
    model_role_calls: dict[tuple[str, str], int] = defaultdict(int)
    route_values: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "run_paths": set(),
            "scene_names": set(),
            "trigger_error_types": set(),
            "fallback_usage_keys": set(),
            "fallback_observed_scene_call_count": 0,
            "fallback_switch_count": 0,
            "fallback_completed_count": 0,
            "fallback_error_count": 0,
        }
    )
    for record in records:
        usage = _mapping(record.summary.get("model_usage"))
        raw_scenes = usage.get("by_scene")
        scene_model_calls: dict[tuple[str, str], int] = defaultdict(int)
        if isinstance(raw_scenes, list):
            for raw_scene in raw_scenes:
                if not isinstance(raw_scene, Mapping):
                    continue
                scene_name = str(raw_scene.get("scene_name") or "").strip()
                model_name = str(raw_scene.get("model_name") or "").strip()
                model_role = model_role_for_scene(scene_name)
                if model_role not in {"primary", "audit"} or not model_name:
                    continue
                scene_call_count = _non_negative_int(
                    raw_scene.get("scene_call_count")
                )
                model_role_calls[(model_role, model_name)] += scene_call_count
                scene_model_calls[(scene_name, model_name)] += scene_call_count

        if record.routing.get("status") != "complete":
            continue
        raw_routes = _mapping(record.summary.get("model_routing")).get("routes")
        if not isinstance(raw_routes, list):
            continue
        for raw_route in raw_routes:
            if not isinstance(raw_route, Mapping):
                continue
            scene_name = str(raw_route.get("scene_name") or "").strip()
            model_role = model_role_for_scene(scene_name)
            primary_model = str(
                raw_route.get("primary_model_name") or ""
            ).strip()
            fallback_model = str(
                raw_route.get("fallback_model_name") or ""
            ).strip()
            switch_count = _non_negative_int(raw_route.get("switch_count"))
            status = str(raw_route.get("fallback_call_status") or "").strip()
            if (
                model_role not in {"primary", "audit"}
                or not primary_model
                or not fallback_model
                or switch_count <= 0
                or status not in {"completed", "error"}
            ):
                continue
            key = (model_role, primary_model, fallback_model)
            values = route_values[key]
            values["run_paths"].add(str(record.path))
            values["scene_names"].add(scene_name)
            fallback_usage_key = (str(record.path), scene_name)
            if fallback_usage_key not in values["fallback_usage_keys"]:
                values["fallback_usage_keys"].add(fallback_usage_key)
                values["fallback_observed_scene_call_count"] += (
                    scene_model_calls[(scene_name, fallback_model)]
                )
            values["fallback_switch_count"] += switch_count
            if status == "completed":
                values["fallback_completed_count"] += switch_count
            else:
                values["fallback_error_count"] += switch_count
            trigger_error_types = raw_route.get("trigger_error_types")
            if isinstance(trigger_error_types, list):
                values["trigger_error_types"].update(
                    str(error_type).strip()
                    for error_type in trigger_error_types
                    if str(error_type).strip()
                )

    result: list[dict[str, Any]] = []
    for model_role, primary_model, fallback_model in sorted(route_values):
        values = route_values[(model_role, primary_model, fallback_model)]
        switch_count = int(values["fallback_switch_count"])
        completed_count = int(values["fallback_completed_count"])
        error_count = int(values["fallback_error_count"])
        primary_calls = model_role_calls[(model_role, primary_model)]
        fallback_calls = int(values["fallback_observed_scene_call_count"])
        result.append(
            {
                "model_role": model_role,
                "primary_model_name": primary_model,
                "fallback_model_name": fallback_model,
                "run_count": len(values["run_paths"]),
                "scene_names": sorted(values["scene_names"]),
                "trigger_error_types": sorted(values["trigger_error_types"]),
                "primary_scene_call_count": primary_calls,
                "fallback_observed_scene_call_count": fallback_calls,
                "fallback_switch_count": switch_count,
                "fallback_completed_count": completed_count,
                "fallback_error_count": error_count,
                "primary_switch_share": (
                    switch_count / primary_calls if primary_calls > 0 else None
                ),
                "fallback_completion_rate": (
                    completed_count / switch_count
                    if switch_count > 0
                    else None
                ),
                "fallback_error_rate": (
                    error_count / switch_count if switch_count > 0 else None
                ),
            }
        )
    return result


def _model_status(value: Mapping[str, Any]) -> str:
    observed_calls = _non_negative_int(value.get("observed_scene_call_count"))
    fallback_calls = _non_negative_int(value.get("fallback_call_count"))
    primary_share = value.get("primary_switch_share")
    fallback_error_rate = value.get("fallback_error_rate")
    if observed_calls < _MIN_MODEL_SCENE_CALLS and fallback_calls < _MIN_FALLBACK_CALLS:
        return "insufficient_data"
    if (
        isinstance(primary_share, (int, float))
        and float(primary_share) >= _DEGRADED_PRIMARY_SWITCH_SHARE
    ) or (
        fallback_calls >= _MIN_FALLBACK_CALLS
        and isinstance(fallback_error_rate, (int, float))
        and float(fallback_error_rate) >= _DEGRADED_FALLBACK_ERROR_RATE
    ):
        return "degraded"
    if (
        _non_negative_int(value.get("primary_fallback_switch_count")) > 0
        or _non_negative_int(value.get("fallback_error_count")) > 0
    ):
        return "watch"
    return "healthy"


def _model_trend(
    recent_status: str,
    baseline_status: str,
) -> str:
    ranks = {
        "insufficient_data": -1,
        "healthy": 0,
        "watch": 1,
        "degraded": 2,
    }
    if "insufficient_data" in {recent_status, baseline_status}:
        return "insufficient_data"
    if ranks[recent_status] > ranks[baseline_status]:
        return "regressed"
    if ranks[recent_status] < ranks[baseline_status]:
        return "improved"
    return "stable"


def _build_model_summaries(
    recent_records: list[_RunObservation],
    baseline_records: list[_RunObservation],
) -> list[dict[str, Any]]:
    recent_models = _aggregate_models(recent_records)
    baseline_models = _aggregate_models(baseline_records)
    models: list[dict[str, Any]] = []
    for model_name in sorted(set(recent_models) | set(baseline_models)):
        recent = recent_models.get(model_name, {})
        baseline = baseline_models.get(model_name, {})
        recent_status = _model_status(recent)
        baseline_status = _model_status(baseline)
        models.append(
            {
                "model_name": model_name,
                "status": recent_status,
                "trend": _model_trend(recent_status, baseline_status),
                "recent": recent,
                "baseline": baseline,
                "deltas": {
                    "primary_switch_share": _numeric_delta(
                        recent.get("primary_switch_share"),
                        baseline.get("primary_switch_share"),
                    ),
                    "fallback_error_rate": _numeric_delta(
                        recent.get("fallback_error_rate"),
                        baseline.get("fallback_error_rate"),
                    ),
                },
            }
        )
    return models


def _trend_status(
    recent: Mapping[str, Any],
    baseline: Mapping[str, Any],
    deltas: Mapping[str, Any],
) -> str:
    if (
        _non_negative_int(recent.get("run_count")) < _MIN_TREND_WINDOW_RUNS
        or _non_negative_int(baseline.get("run_count")) < _MIN_TREND_WINDOW_RUNS
    ):
        return "insufficient_data"
    adverse_signals = (
        (
            isinstance(deltas.get("fallback_switch_share"), (int, float))
            and float(deltas["fallback_switch_share"])
            >= _WATCH_FALLBACK_SHARE_DELTA
        ),
        (
            isinstance(deltas.get("gate_pass_rate"), (int, float))
            and float(deltas["gate_pass_rate"]) <= _WATCH_GATE_PASS_RATE_DELTA
        ),
        (
            isinstance(deltas.get("cost_per_scene_ratio"), (int, float))
            and float(deltas["cost_per_scene_ratio"])
            >= _WATCH_COST_PER_SCENE_RATIO
        ),
    )
    improved_signals = (
        (
            isinstance(deltas.get("fallback_switch_share"), (int, float))
            and float(deltas["fallback_switch_share"])
            <= -_WATCH_FALLBACK_SHARE_DELTA
        ),
        (
            isinstance(deltas.get("gate_pass_rate"), (int, float))
            and float(deltas["gate_pass_rate"]) >= abs(_WATCH_GATE_PASS_RATE_DELTA)
        ),
        (
            isinstance(deltas.get("cost_per_scene_ratio"), (int, float))
            and float(deltas["cost_per_scene_ratio"])
            <= -_WATCH_COST_PER_SCENE_RATIO
        ),
    )
    adverse = any(adverse_signals)
    improved = any(improved_signals)
    if adverse and improved:
        return "mixed"
    if adverse:
        return "regressed"
    if improved:
        return "improved"
    return "stable"


def _overall_status(
    *,
    recent: Mapping[str, Any],
    deltas: Mapping[str, Any],
    models: Sequence[Mapping[str, Any]],
    invalid_routing_count: int,
    trend: str,
) -> str:
    fallback_share_delta = deltas.get("fallback_switch_share")
    fallback_error_rate = recent.get("fallback_error_rate")
    fallback_switch_count = _non_negative_int(recent.get("fallback_switch_count"))
    if (
        isinstance(fallback_share_delta, (int, float))
        and float(fallback_share_delta) >= _DEGRADED_FALLBACK_SHARE_DELTA
    ) or (
        fallback_switch_count >= _MIN_FALLBACK_CALLS
        and isinstance(fallback_error_rate, (int, float))
        and float(fallback_error_rate) >= _DEGRADED_FALLBACK_ERROR_RATE
    ) or any(model.get("status") == "degraded" for model in models):
        return "degraded"
    if invalid_routing_count > 0 or trend in {"regressed", "mixed"}:
        return "watch"
    if trend == "insufficient_data":
        return "insufficient_data"
    return "healthy"


def _recommendations(
    *,
    overall: Mapping[str, Any],
    models: Sequence[Mapping[str, Any]],
    invalid_routing_count: int,
) -> list[dict[str, Any]]:
    deltas = _mapping(overall.get("deltas"))
    recommendations: list[dict[str, Any]] = []

    def add(reason_code: str, *, model_name: str | None = None) -> None:
        item: dict[str, Any] = {
            "action": "manual_review",
            "reason_code": reason_code,
        }
        if model_name:
            item["model_name"] = model_name
        recommendations.append(item)

    if invalid_routing_count > 0:
        add("invalid_routing_receipt")
    fallback_share_delta = deltas.get("fallback_switch_share")
    if (
        isinstance(fallback_share_delta, (int, float))
        and float(fallback_share_delta) >= _WATCH_FALLBACK_SHARE_DELTA
    ):
        add("fallback_switch_share_increased")
    gate_pass_delta = deltas.get("gate_pass_rate")
    if (
        isinstance(gate_pass_delta, (int, float))
        and float(gate_pass_delta) <= _WATCH_GATE_PASS_RATE_DELTA
    ):
        add("gate_pass_rate_declined")
    cost_ratio = deltas.get("cost_per_scene_ratio")
    if (
        isinstance(cost_ratio, (int, float))
        and float(cost_ratio) >= _WATCH_COST_PER_SCENE_RATIO
    ):
        add("cost_per_scene_increased")
    for model in models:
        if model.get("status") != "degraded":
            continue
        model_name = str(model.get("model_name") or "").strip()
        recent = _mapping(model.get("recent"))
        primary_share = recent.get("primary_switch_share")
        if (
            isinstance(primary_share, (int, float))
            and float(primary_share) >= _DEGRADED_PRIMARY_SWITCH_SHARE
        ):
            add("primary_model_fallback_rate_high", model_name=model_name)
        fallback_calls = _non_negative_int(recent.get("fallback_call_count"))
        fallback_error_rate = recent.get("fallback_error_rate")
        if (
            fallback_calls >= _MIN_FALLBACK_CALLS
            and isinstance(fallback_error_rate, (int, float))
            and float(fallback_error_rate) >= _DEGRADED_FALLBACK_ERROR_RATE
        ):
            add("fallback_model_error_rate_high", model_name=model_name)
    return recommendations


def build_write_model_health_trend(
    root: str | Path,
    *,
    max_runs: int = 20,
    recent_run_count: int = 5,
    model_catalog: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """Aggregate recent write receipts into a bounded, advisory health trend."""

    max_runs = _positive_int(max_runs, name="max_runs")
    recent_run_count = _positive_int(
        recent_run_count,
        name="recent_run_count",
    )
    if recent_run_count > max_runs:
        raise ValueError("recent_run_count must not exceed max_runs")

    resolved_root = Path(root).expanduser().resolve()
    summary_paths = _discover_summary_paths(resolved_root)
    warnings: list[str] = []
    observations: list[_RunObservation] = []
    for path in summary_paths:
        observation, warning = _load_observation(
            path,
            model_catalog=model_catalog,
        )
        if warning is not None:
            warnings.append(warning)
        if observation is not None:
            observations.append(observation)
    observations.sort(
        key=lambda item: (item.completed_at, str(item.path)),
        reverse=True,
    )
    selected = observations[:max_runs]
    recent_records = selected[:recent_run_count]
    baseline_records = selected[recent_run_count:]

    recent = _aggregate_runs(recent_records)
    baseline = _aggregate_runs(baseline_records)
    deltas = {
        "gate_pass_rate": _numeric_delta(
            recent.get("gate_pass_rate"),
            baseline.get("gate_pass_rate"),
        ),
        "fallback_switch_share": _numeric_delta(
            recent.get("fallback_switch_share"),
            baseline.get("fallback_switch_share"),
        ),
        "fallback_error_rate": _numeric_delta(
            recent.get("fallback_error_rate"),
            baseline.get("fallback_error_rate"),
        ),
        **_cost_delta(recent, baseline),
    }
    models = _build_model_summaries(recent_records, baseline_records)
    recent_route_pairs = _aggregate_route_pairs(recent_records)
    baseline_route_pairs = _aggregate_route_pairs(baseline_records)
    routing_complete_count = sum(
        1 for record in selected if record.routing.get("status") == "complete"
    )
    routing_missing_count = sum(
        1 for record in selected if record.routing.get("status") == "missing"
    )
    routing_invalid_count = sum(
        1 for record in selected if record.routing.get("status") == "invalid"
    )
    history_fingerprint = _history_fingerprint(selected)
    trend_status = _trend_status(recent, baseline, deltas)
    overall: dict[str, Any] = {
        "status": _overall_status(
            recent=recent,
            deltas=deltas,
            models=models,
            invalid_routing_count=routing_invalid_count,
            trend=trend_status,
        ),
        "trend": trend_status,
        "recent": recent,
        "baseline": baseline,
        "deltas": deltas,
    }
    payload = {
        "schema_version": _TREND_SCHEMA_VERSION,
        "cost_basis": (
            "current_model_catalog"
            if model_catalog is not None
            else "persisted_run_summary"
        ),
        "window": {
            "discovered_summary_count": len(summary_paths),
            "selected_run_count": len(selected),
            "max_runs": max_runs,
            "recent_run_count": len(recent_records),
            "baseline_run_count": len(baseline_records),
            "summary_timestamp_count": sum(
                1 for record in selected if record.timestamp_source == "summary"
            ),
            "file_mtime_timestamp_count": sum(
                1 for record in selected if record.timestamp_source == "file_mtime"
            ),
            "invalid_summary_count": len(summary_paths) - len(observations),
        },
        "source_integrity": {
            "routing_complete_run_count": routing_complete_count,
            "routing_missing_run_count": routing_missing_count,
            "routing_invalid_run_count": routing_invalid_count,
            "selected_history_fingerprint": history_fingerprint,
        },
        "overall": overall,
        "models": models,
        "route_pairs": {
            "recent": recent_route_pairs,
            "baseline": baseline_route_pairs,
        },
        "challenger_proposal": {},
        "recommendations": [],
        "warnings": warnings,
    }
    payload["challenger_proposal"] = build_write_model_challenger_proposal(
        recent=recent,
        route_pairs=recent_route_pairs,
        models=models,
        history_fingerprint=history_fingerprint,
        selected_run_count=len(selected),
        baseline_run_count=len(baseline_records),
    )
    payload["recommendations"] = _recommendations(
        overall=overall,
        models=models,
        invalid_routing_count=routing_invalid_count,
    )
    return payload


def _format_rate(value: object, *, signed: bool = False) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "unavailable"
    prefix = "+" if signed and float(value) > 0 else ""
    return f"{prefix}{float(value) * 100:.1f}%"


def _format_cost(value: Mapping[str, Any]) -> str:
    cost = _mapping(value.get("cost"))
    cost_per_scene = _finite_non_negative_float(cost.get("cost_per_scene"))
    currency = str(cost.get("currency") or "").strip()
    if cost.get("status") != "complete" or cost_per_scene is None:
        return f"unavailable ({str(cost.get('status') or 'unavailable')})"
    return f"{currency} {cost_per_scene:.6f}"


def format_write_model_health_report(
    payload: Mapping[str, Any],
) -> list[str]:
    """Format a compact operator receipt without exposing source paths."""

    window = _mapping(payload.get("window"))
    integrity = _mapping(payload.get("source_integrity"))
    overall = _mapping(payload.get("overall"))
    recent = _mapping(overall.get("recent"))
    baseline = _mapping(overall.get("baseline"))
    deltas = _mapping(overall.get("deltas"))
    lines = [
        "",
        "模型健康趋势（只读）：",
        (
            "  运行窗口   : "
            f"recent={_non_negative_int(window.get('recent_run_count'))}, "
            f"baseline={_non_negative_int(window.get('baseline_run_count'))}, "
            f"selected={_non_negative_int(window.get('selected_run_count'))}"
        ),
        f"  健康状态   : {str(overall.get('status') or 'unknown')}",
        f"  趋势判断   : {str(overall.get('trend') or 'unknown')}",
        (
            "  后备占比   : "
            f"recent={_format_rate(recent.get('fallback_switch_share'))}, "
            f"baseline={_format_rate(baseline.get('fallback_switch_share'))}, "
            f"delta={_format_rate(deltas.get('fallback_switch_share'), signed=True)}"
        ),
        (
            "  后备错误率 : "
            f"recent={_format_rate(recent.get('fallback_error_rate'))}, "
            f"baseline={_format_rate(baseline.get('fallback_error_rate'))}"
        ),
        (
            "  发布通过率 : "
            f"recent={_format_rate(recent.get('gate_pass_rate'))}, "
            f"baseline={_format_rate(baseline.get('gate_pass_rate'))}"
        ),
        (
            "  单Scene成本: "
            f"recent={_format_cost(recent)}, baseline={_format_cost(baseline)}"
        ),
        (
            "  路由凭证   : "
            f"complete={_non_negative_int(integrity.get('routing_complete_run_count'))}, "
            f"missing={_non_negative_int(integrity.get('routing_missing_run_count'))}, "
            f"invalid={_non_negative_int(integrity.get('routing_invalid_run_count'))}"
        ),
    ]
    raw_models = payload.get("models")
    if isinstance(raw_models, list):
        for raw_model in raw_models:
            if not isinstance(raw_model, Mapping):
                continue
            recent_model = _mapping(raw_model.get("recent"))
            lines.append(
                "  模型状态   : "
                f"{str(raw_model.get('model_name') or 'unknown')} "
                f"{str(raw_model.get('status') or 'unknown')} "
                f"(calls={_non_negative_int(recent_model.get('observed_scene_call_count'))}, "
                f"primary_fallback={_format_rate(recent_model.get('primary_switch_share'))}, "
                f"fallback_errors={_format_rate(recent_model.get('fallback_error_rate'))})"
            )
    proposal = _mapping(payload.get("challenger_proposal"))
    lines.append(
        "  Challenger提案: "
        f"{str(proposal.get('status') or 'unknown')} "
        f"({str(proposal.get('action') or 'unknown')})"
    )
    raw_overrides = proposal.get("role_overrides")
    if isinstance(raw_overrides, list):
        for raw_override in raw_overrides:
            if not isinstance(raw_override, Mapping):
                continue
            lines.append(
                "  候选角色覆盖 : "
                f"{str(raw_override.get('model_role') or 'unknown')} "
                f"{str(raw_override.get('current_model_name') or 'unknown')} -> "
                f"{str(raw_override.get('challenger_model_name') or 'unknown')}"
            )
    raw_cli_args = proposal.get("challenger_cli_args")
    if isinstance(raw_cli_args, list) and raw_cli_args:
        lines.append(
            "  候选CLI参数  : "
            f"{json.dumps(raw_cli_args, ensure_ascii=False)}"
        )
    proposal_reasons = proposal.get("reason_codes")
    if isinstance(proposal_reasons, list) and proposal_reasons:
        lines.append(
            "  提案依据     : "
            + ", ".join(str(reason) for reason in proposal_reasons)
        )
    recommendations = payload.get("recommendations")
    if isinstance(recommendations, list) and recommendations:
        for raw_item in recommendations:
            if not isinstance(raw_item, Mapping):
                continue
            model_suffix = (
                f" model={str(raw_item.get('model_name'))}"
                if raw_item.get("model_name")
                else ""
            )
            lines.append(
                "  路由建议   : "
                f"{str(raw_item.get('action') or 'manual_review')} "
                f"{str(raw_item.get('reason_code') or 'unknown')}"
                f"{model_suffix}"
            )
    else:
        lines.append("  路由建议   : none")
    lines.append("  安全边界   : 只提供审计建议，不会自动修改主备模型配置")
    return lines


__all__ = [
    "build_write_model_health_trend",
    "format_write_model_health_report",
]
