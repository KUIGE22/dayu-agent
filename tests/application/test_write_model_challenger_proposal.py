"""Read-only write-model Challenger proposal policy tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dayu.services.write_model_challenger_proposal import (
    build_write_model_challenger_proposal,
    load_write_model_challenger_proposal,
    persist_write_model_challenger_proposal,
    validate_write_model_challenger_proposal,
)

_HISTORY_FINGERPRINT = f"sha256:{'1' * 64}"


def _resign(payload: dict[str, object]) -> dict[str, object]:
    unsigned = dict(payload)
    unsigned.pop("proposal_fingerprint", None)
    serialized = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    payload["proposal_fingerprint"] = (
        "sha256:"
        + hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    )
    return payload


def _recent(
    *,
    run_count: int = 5,
    routing_observed_run_count: int = 5,
    gate_observed_run_count: int = 5,
    gate_pass_rate: float = 1.0,
    fallback_switch_count: int = 4,
) -> dict[str, object]:
    return {
        "run_count": run_count,
        "routing_observed_run_count": routing_observed_run_count,
        "gate_observed_run_count": gate_observed_run_count,
        "gate_pass_rate": gate_pass_rate,
        "fallback_switch_count": fallback_switch_count,
    }


def _route(
    *,
    model_role: str = "primary",
    primary_model_name: str = "deepseek-primary",
    fallback_model_name: str = "mimo-fallback",
    primary_scene_call_count: int = 20,
    fallback_observed_scene_call_count: int = 4,
    fallback_switch_count: int = 4,
    fallback_completed_count: int = 4,
    fallback_error_count: int = 0,
) -> dict[str, object]:
    return {
        "model_role": model_role,
        "primary_model_name": primary_model_name,
        "fallback_model_name": fallback_model_name,
        "run_count": 4,
        "scene_names": ["write" if model_role == "primary" else "audit"],
        "primary_scene_call_count": primary_scene_call_count,
        "fallback_observed_scene_call_count": (
            fallback_observed_scene_call_count
        ),
        "fallback_switch_count": fallback_switch_count,
        "fallback_completed_count": fallback_completed_count,
        "fallback_error_count": fallback_error_count,
        "primary_switch_share": (
            fallback_switch_count / primary_scene_call_count
        ),
        "fallback_completion_rate": (
            fallback_completed_count / fallback_switch_count
        ),
        "fallback_error_rate": (
            fallback_error_count / fallback_switch_count
        ),
    }


def _models(*names: str) -> list[dict[str, object]]:
    return [
        {
            "model_name": name,
            "status": "healthy",
        }
        for name in names
    ]


@pytest.mark.unit
def test_challenger_proposal_is_ready_only_for_isolated_evaluation() -> None:
    proposal = build_write_model_challenger_proposal(
        recent=_recent(),
        route_pairs=[_route()],
        models=_models("deepseek-primary", "mimo-fallback"),
        history_fingerprint=_HISTORY_FINGERPRINT,
        selected_run_count=5,
        baseline_run_count=0,
    )

    assert proposal["schema_version"] == "write_model_challenger_proposal_v2"
    assert proposal["status"] == "ready"
    assert proposal["action"] == "run_isolated_challenger"
    assert proposal["challenger_cli_args"] == [
        "--challenger-model-name",
        "mimo-fallback",
    ]
    assert proposal["role_overrides"] == [
        {
            "model_role": "primary",
            "current_model_name": "deepseek-primary",
            "challenger_model_name": "mimo-fallback",
            "evidence": {
                "run_count": 4,
                "scene_names": ["write"],
                "primary_scene_call_count": 20,
                "fallback_observed_scene_call_count": 4,
                "fallback_switch_count": 4,
                "fallback_completed_count": 4,
                "fallback_error_count": 0,
                "primary_switch_share": 0.2,
                "fallback_completion_rate": 1.0,
                "fallback_error_rate": 0.0,
            },
        }
    ]
    assert "manual_promotion_only" in proposal["safety_requirements"]
    assert proposal["evidence_window"] == {
        "history_fingerprint": _HISTORY_FINGERPRINT,
        "selected_run_count": 5,
        "recent_run_count": 5,
        "baseline_run_count": 0,
    }
    assert str(proposal["proposal_fingerprint"]).startswith("sha256:")
    validate_write_model_challenger_proposal(proposal)


@pytest.mark.unit
def test_challenger_proposal_blocks_unstable_fallback() -> None:
    route = _route(
        fallback_observed_scene_call_count=5,
        fallback_switch_count=5,
        fallback_completed_count=4,
        fallback_error_count=1,
    )
    proposal = build_write_model_challenger_proposal(
        recent=_recent(fallback_switch_count=5),
        route_pairs=[route],
        models=_models("deepseek-primary", "mimo-fallback"),
        history_fingerprint=_HISTORY_FINGERPRINT,
        selected_run_count=5,
        baseline_run_count=0,
    )

    assert proposal["status"] == "blocked"
    assert proposal["action"] == "manual_review"
    assert proposal["role_overrides"] == []
    assert proposal["challenger_cli_args"] == []
    assert {
        "fallback_completion_rate_too_low",
        "fallback_error_rate_too_high",
    }.issubset(proposal["reason_codes"])


@pytest.mark.unit
def test_challenger_proposal_blocks_incomplete_recent_receipts() -> None:
    proposal = build_write_model_challenger_proposal(
        recent=_recent(routing_observed_run_count=4),
        route_pairs=[_route()],
        models=_models("deepseek-primary", "mimo-fallback"),
        history_fingerprint=_HISTORY_FINGERPRINT,
        selected_run_count=5,
        baseline_run_count=0,
    )

    assert proposal["status"] == "blocked"
    assert proposal["reason_codes"] == [
        "incomplete_recent_routing_receipts"
    ]


@pytest.mark.unit
def test_challenger_proposal_does_nothing_for_healthy_routes() -> None:
    proposal = build_write_model_challenger_proposal(
        recent=_recent(fallback_switch_count=0),
        route_pairs=[],
        models=[],
        history_fingerprint=_HISTORY_FINGERPRINT,
        selected_run_count=5,
        baseline_run_count=0,
    )

    assert proposal["status"] == "not_needed"
    assert proposal["action"] == "none"
    assert proposal["challenger_cli_args"] == []
    assert proposal["reason_codes"] == ["no_degraded_primary_route"]


@pytest.mark.unit
def test_challenger_proposal_rejects_ambiguous_role_candidates() -> None:
    route_a = _route(
        fallback_model_name="mimo-a",
        primary_scene_call_count=20,
        fallback_observed_scene_call_count=3,
        fallback_switch_count=3,
        fallback_completed_count=3,
    )
    route_b = _route(
        fallback_model_name="mimo-b",
        primary_scene_call_count=20,
        fallback_observed_scene_call_count=3,
        fallback_switch_count=3,
        fallback_completed_count=3,
    )
    proposal = build_write_model_challenger_proposal(
        recent=_recent(fallback_switch_count=6),
        route_pairs=[route_a, route_b],
        models=_models("deepseek-primary", "mimo-a", "mimo-b"),
        history_fingerprint=_HISTORY_FINGERPRINT,
        selected_run_count=5,
        baseline_run_count=0,
    )

    assert proposal["status"] == "ambiguous"
    assert proposal["action"] == "manual_review"
    assert proposal["challenger_cli_args"] == []
    assert proposal["reason_codes"] == ["ambiguous_degraded_role_routes"]


@pytest.mark.unit
def test_challenger_proposal_fingerprint_binds_history() -> None:
    first = build_write_model_challenger_proposal(
        recent=_recent(fallback_switch_count=0),
        route_pairs=[],
        models=[],
        history_fingerprint=_HISTORY_FINGERPRINT,
        selected_run_count=5,
        baseline_run_count=0,
    )
    second = build_write_model_challenger_proposal(
        recent=_recent(fallback_switch_count=0),
        route_pairs=[],
        models=[],
        history_fingerprint=f"sha256:{'2' * 64}",
        selected_run_count=5,
        baseline_run_count=0,
    )

    assert first["proposal_fingerprint"] != second["proposal_fingerprint"]
    tampered = dict(first)
    tampered["action"] = "run_isolated_challenger"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_write_model_challenger_proposal(tampered)


@pytest.mark.unit
def test_challenger_proposal_validation_rejects_unsafe_cli_arguments() -> None:
    proposal = build_write_model_challenger_proposal(
        recent=_recent(),
        route_pairs=[_route()],
        models=_models("deepseek-primary", "mimo-fallback"),
        history_fingerprint=_HISTORY_FINGERPRINT,
        selected_run_count=5,
        baseline_run_count=0,
    )
    proposal["challenger_cli_args"] = [
        "--output",
        "unexpected-path",
    ]
    _resign(proposal)

    with pytest.raises(ValueError, match="unsupported.*argument"):
        validate_write_model_challenger_proposal(proposal)


@pytest.mark.unit
def test_persist_challenger_proposal_is_atomic_idempotent_and_no_clobber(
    tmp_path: Path,
) -> None:
    target = tmp_path / "receipts" / "proposal.json"
    first = build_write_model_challenger_proposal(
        recent=_recent(fallback_switch_count=0),
        route_pairs=[],
        models=[],
        history_fingerprint=_HISTORY_FINGERPRINT,
        selected_run_count=5,
        baseline_run_count=0,
    )
    second = build_write_model_challenger_proposal(
        recent=_recent(fallback_switch_count=0),
        route_pairs=[],
        models=[],
        history_fingerprint=f"sha256:{'2' * 64}",
        selected_run_count=5,
        baseline_run_count=0,
    )

    assert persist_write_model_challenger_proposal(first, target) == target.resolve()
    original = target.read_text(encoding="utf-8")
    assert persist_write_model_challenger_proposal(first, target) == target.resolve()
    assert target.read_text(encoding="utf-8") == original
    with pytest.raises(FileExistsError, match="different content"):
        persist_write_model_challenger_proposal(second, target)

    persist_write_model_challenger_proposal(second, target, overwrite=True)
    persisted = json.loads(target.read_text(encoding="utf-8"))
    assert persisted["proposal_fingerprint"] == second["proposal_fingerprint"]
    assert not list(target.parent.glob("*.tmp"))

    loaded_path, loaded = load_write_model_challenger_proposal(target)
    assert loaded_path == target.resolve()
    assert loaded == second

    loaded["action"] = "run_isolated_challenger"
    target.write_text(
        json.dumps(loaded, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_write_model_challenger_proposal(target)
