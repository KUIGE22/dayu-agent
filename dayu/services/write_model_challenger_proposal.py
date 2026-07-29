"""Build a conservative, non-executing Challenger proposal from route history."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

_PROPOSAL_SCHEMA_VERSION = "write_model_challenger_proposal_v2"
_MIN_RECENT_RUNS = 3
_MIN_PRIMARY_SCENE_CALLS = 5
_MIN_FALLBACK_SWITCHES = 3
_MIN_PRIMARY_SWITCH_SHARE = 0.20
_MIN_FALLBACK_COMPLETION_RATE = 0.90
_MAX_FALLBACK_ERROR_RATE = 0.10
_MIN_GATE_PASS_RATE = 0.80
_ROLE_ARGUMENTS = {
    "primary": "--challenger-model-name",
    "audit": "--challenger-audit-model-name",
}
_ROLE_ORDER = {
    "primary": 0,
    "audit": 1,
}
_PROPOSAL_ACTIONS = {
    "run_isolated_challenger",
    "manual_review",
    "none",
}
_PROPOSAL_STATUSES = {
    "ready",
    "blocked",
    "ambiguous",
    "not_needed",
}
_SAFETY_REQUIREMENTS = [
    "preflight_champion_and_challenger_before_execution",
    "use_isolated_challenger_output",
    "compare_quality_routing_and_cost",
    "manual_promotion_only",
]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fingerprint(value: object) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _validated_fingerprint(value: str, *, name: str) -> str:
    normalized = str(value or "").strip().lower()
    prefix = "sha256:"
    digest = normalized[len(prefix) :] if normalized.startswith(prefix) else ""
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{name} must be a sha256 fingerprint")
    return normalized


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _required_non_negative_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _finite_rate(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    resolved = float(value)
    if not math.isfinite(resolved) or resolved < 0:
        return None
    return resolved


def _append_reason(reasons: list[str], reason_code: str) -> None:
    if reason_code not in reasons:
        reasons.append(reason_code)


def _model_statuses(
    models: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for model in models:
        model_name = str(model.get("model_name") or "").strip()
        if model_name:
            statuses[model_name] = str(model.get("status") or "").strip()
    return statuses


def _assess_route(
    route: Mapping[str, Any],
    *,
    model_statuses: Mapping[str, str],
) -> dict[str, Any]:
    role = str(route.get("model_role") or "").strip()
    primary_model = str(route.get("primary_model_name") or "").strip()
    fallback_model = str(route.get("fallback_model_name") or "").strip()
    primary_calls = _non_negative_int(route.get("primary_scene_call_count"))
    fallback_calls = _non_negative_int(
        route.get("fallback_observed_scene_call_count")
    )
    switch_count = _non_negative_int(route.get("fallback_switch_count"))
    completed_count = _non_negative_int(route.get("fallback_completed_count"))
    switch_share = _finite_rate(route.get("primary_switch_share"))
    completion_rate = _finite_rate(route.get("fallback_completion_rate"))
    error_rate = _finite_rate(route.get("fallback_error_rate"))
    reasons: list[str] = []

    if role not in _ROLE_ARGUMENTS:
        _append_reason(reasons, "unsupported_model_role")
    if not primary_model or not fallback_model:
        _append_reason(reasons, "missing_route_model_name")
    elif primary_model == fallback_model:
        _append_reason(reasons, "primary_and_fallback_are_identical")
    if primary_calls < _MIN_PRIMARY_SCENE_CALLS:
        _append_reason(reasons, "insufficient_primary_observations")
    if switch_count < _MIN_FALLBACK_SWITCHES:
        _append_reason(reasons, "insufficient_fallback_samples")
    if switch_count > primary_calls:
        _append_reason(reasons, "fallback_switches_exceed_primary_calls")
    if switch_share is None:
        _append_reason(reasons, "primary_switch_share_unavailable")
    elif switch_share < _MIN_PRIMARY_SWITCH_SHARE:
        _append_reason(reasons, "primary_route_not_degraded")
    if completion_rate is None:
        _append_reason(reasons, "fallback_completion_rate_unavailable")
    elif completion_rate < _MIN_FALLBACK_COMPLETION_RATE:
        _append_reason(reasons, "fallback_completion_rate_too_low")
    if error_rate is None:
        _append_reason(reasons, "fallback_error_rate_unavailable")
    elif error_rate > _MAX_FALLBACK_ERROR_RATE:
        _append_reason(reasons, "fallback_error_rate_too_high")
    if fallback_calls < completed_count:
        _append_reason(reasons, "fallback_usage_receipt_incomplete")

    fallback_status = model_statuses.get(fallback_model)
    if fallback_status is None:
        _append_reason(reasons, "fallback_model_health_missing")
    elif fallback_status == "degraded":
        _append_reason(reasons, "fallback_model_degraded")

    return {
        **dict(route),
        "eligible": not reasons,
        "reason_codes": reasons,
    }


def _base_payload() -> dict[str, Any]:
    return {
        "schema_version": _PROPOSAL_SCHEMA_VERSION,
        "status": "blocked",
        "action": "manual_review",
        "role_overrides": [],
        "challenger_cli_args": [],
        "role_decisions": [],
        "evaluated_routes": [],
        "reason_codes": [],
        "thresholds": {
            "minimum_recent_runs": _MIN_RECENT_RUNS,
            "minimum_primary_scene_calls": _MIN_PRIMARY_SCENE_CALLS,
            "minimum_fallback_switches": _MIN_FALLBACK_SWITCHES,
            "minimum_primary_switch_share": _MIN_PRIMARY_SWITCH_SHARE,
            "minimum_fallback_completion_rate": (
                _MIN_FALLBACK_COMPLETION_RATE
            ),
            "maximum_fallback_error_rate": _MAX_FALLBACK_ERROR_RATE,
            "minimum_gate_pass_rate": _MIN_GATE_PASS_RATE,
        },
        "safety_requirements": list(_SAFETY_REQUIREMENTS),
    }


def _finalize_payload(
    payload: dict[str, Any],
    *,
    history_fingerprint: str,
    selected_run_count: int,
    recent_run_count: int,
    baseline_run_count: int,
) -> dict[str, Any]:
    payload["evidence_window"] = {
        "history_fingerprint": history_fingerprint,
        "selected_run_count": selected_run_count,
        "recent_run_count": recent_run_count,
        "baseline_run_count": baseline_run_count,
    }
    unsigned_payload = dict(payload)
    unsigned_payload.pop("proposal_fingerprint", None)
    payload["proposal_fingerprint"] = _fingerprint(unsigned_payload)
    return payload


def _global_block_reasons(
    *,
    recent: Mapping[str, Any],
    route_pairs: Sequence[Mapping[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    run_count = _non_negative_int(recent.get("run_count"))
    if run_count < _MIN_RECENT_RUNS:
        _append_reason(reasons, "insufficient_recent_runs")
    if _non_negative_int(recent.get("routing_observed_run_count")) != run_count:
        _append_reason(reasons, "incomplete_recent_routing_receipts")
    if _non_negative_int(recent.get("gate_observed_run_count")) != run_count:
        _append_reason(reasons, "incomplete_recent_gate_receipts")

    gate_pass_rate = _finite_rate(recent.get("gate_pass_rate"))
    if gate_pass_rate is None:
        _append_reason(reasons, "recent_gate_pass_rate_unavailable")
    elif gate_pass_rate < _MIN_GATE_PASS_RATE:
        _append_reason(reasons, "recent_gate_pass_rate_too_low")

    route_switch_count = sum(
        _non_negative_int(route.get("fallback_switch_count"))
        for route in route_pairs
    )
    if route_switch_count != _non_negative_int(
        recent.get("fallback_switch_count")
    ):
        _append_reason(reasons, "incomplete_recent_route_details")
    return reasons


def _role_decisions(
    assessed_routes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    route_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for route in assessed_routes:
        role = str(route.get("model_role") or "").strip()
        primary_model = str(route.get("primary_model_name") or "").strip()
        if role in _ROLE_ARGUMENTS and primary_model:
            route_groups.setdefault((role, primary_model), []).append(route)

    degraded_by_role: dict[
        str,
        list[tuple[str, list[Mapping[str, Any]]]],
    ] = {}
    for (role, primary_model), routes in route_groups.items():
        primary_calls = max(
            _non_negative_int(route.get("primary_scene_call_count"))
            for route in routes
        )
        switch_count = sum(
            _non_negative_int(route.get("fallback_switch_count"))
            for route in routes
        )
        switch_share = (
            switch_count / primary_calls if primary_calls > 0 else None
        )
        if (
            switch_share is not None
            and switch_share >= _MIN_PRIMARY_SWITCH_SHARE
        ):
            degraded_by_role.setdefault(role, []).append(
                (primary_model, routes)
            )

    decisions: list[dict[str, Any]] = []
    for role in sorted(degraded_by_role, key=lambda item: _ROLE_ORDER[item]):
        route_groups_for_role = degraded_by_role[role]
        if len(route_groups_for_role) > 1:
            decisions.append(
                {
                    "model_role": role,
                    "status": "ambiguous",
                    "reason_codes": ["multiple_degraded_primaries_for_role"],
                    "candidate_count": 0,
                }
            )
            continue

        _primary_model, routes = route_groups_for_role[0]
        if len(routes) > 1:
            decisions.append(
                {
                    "model_role": role,
                    "status": "ambiguous",
                    "reason_codes": [
                        "multiple_fallback_candidates_for_degraded_route"
                    ],
                    "candidate_count": sum(
                        1 for route in routes if route.get("eligible") is True
                    ),
                }
            )
            continue

        route = routes[0]
        if route.get("eligible") is not True:
            decisions.append(
                {
                    "model_role": role,
                    "status": "blocked",
                    "reason_codes": list(route.get("reason_codes") or []),
                    "candidate_count": 0,
                }
            )
            continue
        decisions.append(
            {
                "model_role": role,
                "status": "ready",
                "reason_codes": [],
                "candidate_count": 1,
                "current_model_name": route.get("primary_model_name"),
                "challenger_model_name": route.get("fallback_model_name"),
                "evidence": {
                    key: route.get(key)
                    for key in (
                        "run_count",
                        "scene_names",
                        "primary_scene_call_count",
                        "fallback_observed_scene_call_count",
                        "fallback_switch_count",
                        "fallback_completed_count",
                        "fallback_error_count",
                        "primary_switch_share",
                        "fallback_completion_rate",
                        "fallback_error_rate",
                    )
                },
            }
        )
    return decisions


def build_write_model_challenger_proposal(
    *,
    recent: Mapping[str, Any],
    route_pairs: Sequence[Mapping[str, Any]],
    models: Sequence[Mapping[str, Any]],
    history_fingerprint: str,
    selected_run_count: int,
    baseline_run_count: int,
) -> dict[str, Any]:
    """Return a safe argv proposal for an isolated Challenger evaluation."""

    normalized_history_fingerprint = _validated_fingerprint(
        history_fingerprint,
        name="history_fingerprint",
    )
    selected_run_count = _required_non_negative_int(
        selected_run_count,
        name="selected_run_count",
    )
    baseline_run_count = _required_non_negative_int(
        baseline_run_count,
        name="baseline_run_count",
    )
    recent_run_count = _non_negative_int(recent.get("run_count"))
    if selected_run_count != recent_run_count + baseline_run_count:
        raise ValueError(
            "selected_run_count must equal recent and baseline run counts"
        )

    payload = _base_payload()

    def finish() -> dict[str, Any]:
        return _finalize_payload(
            payload,
            history_fingerprint=normalized_history_fingerprint,
            selected_run_count=selected_run_count,
            recent_run_count=recent_run_count,
            baseline_run_count=baseline_run_count,
        )

    global_reasons = _global_block_reasons(
        recent=recent,
        route_pairs=route_pairs,
    )
    model_statuses = _model_statuses(models)
    assessed_routes = [
        _assess_route(route, model_statuses=model_statuses)
        for route in route_pairs
    ]
    payload["evaluated_routes"] = assessed_routes
    if global_reasons:
        payload["reason_codes"] = global_reasons
        return finish()

    role_decisions = _role_decisions(assessed_routes)
    payload["role_decisions"] = role_decisions
    if not role_decisions:
        payload["status"] = "not_needed"
        payload["action"] = "none"
        payload["reason_codes"] = ["no_degraded_primary_route"]
        return finish()

    ambiguous = [
        decision
        for decision in role_decisions
        if decision.get("status") == "ambiguous"
    ]
    if ambiguous:
        payload["status"] = "ambiguous"
        payload["reason_codes"] = ["ambiguous_degraded_role_routes"]
        return finish()

    blocked = [
        decision
        for decision in role_decisions
        if decision.get("status") == "blocked"
    ]
    if blocked:
        reason_codes = ["degraded_role_has_no_stable_fallback_candidate"]
        for decision in blocked:
            for reason_code in decision.get("reason_codes") or []:
                _append_reason(reason_codes, str(reason_code))
        payload["reason_codes"] = reason_codes
        return finish()

    ready = [
        decision
        for decision in role_decisions
        if decision.get("status") == "ready"
    ]
    role_overrides: list[dict[str, Any]] = []
    cli_args: list[str] = []
    for decision in ready:
        role = str(decision["model_role"])
        challenger_model = str(decision["challenger_model_name"])
        role_overrides.append(
            {
                "model_role": role,
                "current_model_name": decision["current_model_name"],
                "challenger_model_name": challenger_model,
                "evidence": decision["evidence"],
            }
        )
        cli_args.extend([_ROLE_ARGUMENTS[role], challenger_model])

    payload["status"] = "ready"
    payload["action"] = "run_isolated_challenger"
    payload["role_overrides"] = role_overrides
    payload["challenger_cli_args"] = cli_args
    payload["reason_codes"] = [
        "stable_fallback_candidate_requires_challenger_evaluation"
    ]
    return finish()


def validate_write_model_challenger_proposal(
    payload: Mapping[str, Any],
) -> None:
    """Validate the schema and content fingerprint of an exportable proposal."""

    if payload.get("schema_version") != _PROPOSAL_SCHEMA_VERSION:
        raise ValueError("unsupported write model Challenger proposal schema")
    expected = _validated_fingerprint(
        str(payload.get("proposal_fingerprint") or ""),
        name="proposal_fingerprint",
    )
    unsigned_payload = dict(payload)
    unsigned_payload.pop("proposal_fingerprint", None)
    actual = _fingerprint(unsigned_payload)
    if not hmac.compare_digest(expected, actual):
        raise ValueError("write model Challenger proposal fingerprint mismatch")

    status = str(payload.get("status") or "")
    action = str(payload.get("action") or "")
    if status not in _PROPOSAL_STATUSES:
        raise ValueError("unsupported write model Challenger proposal status")
    if action not in _PROPOSAL_ACTIONS:
        raise ValueError("unsupported write model Challenger proposal action")

    evidence_window = payload.get("evidence_window")
    if not isinstance(evidence_window, Mapping):
        raise ValueError("proposal evidence_window must be an object")
    _validated_fingerprint(
        str(evidence_window.get("history_fingerprint") or ""),
        name="history_fingerprint",
    )
    selected_run_count = _required_non_negative_int(
        evidence_window.get("selected_run_count"),
        name="selected_run_count",
    )
    recent_run_count = _required_non_negative_int(
        evidence_window.get("recent_run_count"),
        name="recent_run_count",
    )
    baseline_run_count = _required_non_negative_int(
        evidence_window.get("baseline_run_count"),
        name="baseline_run_count",
    )
    if selected_run_count != recent_run_count + baseline_run_count:
        raise ValueError(
            "selected_run_count must equal recent and baseline run counts"
        )

    raw_cli_args = payload.get("challenger_cli_args")
    if not isinstance(raw_cli_args, list) or any(
        not isinstance(item, str) for item in raw_cli_args
    ):
        raise ValueError("challenger_cli_args must be a string array")
    if len(raw_cli_args) % 2:
        raise ValueError("challenger_cli_args must contain flag/value pairs")
    parsed_args: dict[str, str] = {}
    allowed_flags = set(_ROLE_ARGUMENTS.values())
    for index in range(0, len(raw_cli_args), 2):
        flag = raw_cli_args[index]
        model_name = raw_cli_args[index + 1].strip()
        if flag not in allowed_flags:
            raise ValueError("unsupported Challenger proposal argument")
        if flag in parsed_args:
            raise ValueError("duplicate Challenger proposal argument")
        if not model_name or model_name.startswith("-"):
            raise ValueError("invalid Challenger proposal model name")
        parsed_args[flag] = model_name

    raw_role_overrides = payload.get("role_overrides")
    if not isinstance(raw_role_overrides, list):
        raise ValueError("role_overrides must be an array")
    if status == "ready":
        if action != "run_isolated_challenger" or not parsed_args:
            raise ValueError(
                "ready proposal requires isolated Challenger arguments"
            )
        if len(raw_role_overrides) != len(parsed_args):
            raise ValueError(
                "role_overrides must match Challenger argument count"
            )
        for raw_override in raw_role_overrides:
            if not isinstance(raw_override, Mapping):
                raise ValueError("role_overrides entries must be objects")
            role = str(raw_override.get("model_role") or "")
            challenger_model = str(
                raw_override.get("challenger_model_name") or ""
            ).strip()
            expected_flag = _ROLE_ARGUMENTS.get(role)
            if (
                expected_flag is None
                or parsed_args.get(expected_flag) != challenger_model
            ):
                raise ValueError(
                    "role override does not match Challenger arguments"
                )
    elif raw_cli_args or raw_role_overrides:
        raise ValueError(
            "non-ready proposal cannot contain Challenger overrides"
        )
    elif status == "not_needed" and action != "none":
        raise ValueError("not_needed proposal action must be none")
    elif status != "not_needed" and action != "manual_review":
        raise ValueError("blocked proposal action must be manual_review")

def load_write_model_challenger_proposal(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one exported Challenger proposal receipt."""

    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(
            f"write model Challenger proposal does not exist: {target}"
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"invalid write model Challenger proposal JSON: {target}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError(
            f"write model Challenger proposal must be an object: {target}"
        )
    validate_write_model_challenger_proposal(raw)
    return target, raw


def persist_write_model_challenger_proposal(
    payload: Mapping[str, Any],
    path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Persist one validated proposal atomically without silent replacement."""

    validate_write_model_challenger_proposal(payload)
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"

    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if existing == dict(payload):
            return target
        if not overwrite:
            raise FileExistsError(
                f"routing proposal already exists with different content: {target}"
            )

    file_descriptor, temp_path_value = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temp_path = Path(temp_path_value)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            file_descriptor = -1
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return target


__all__ = [
    "build_write_model_challenger_proposal",
    "load_write_model_challenger_proposal",
    "persist_write_model_challenger_proposal",
    "validate_write_model_challenger_proposal",
]
