"""Read-only Challenger proposal verification tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.services.write_model_challenger_proposal import (
    build_write_model_challenger_proposal,
    load_write_model_challenger_proposal,
    persist_write_model_challenger_proposal,
)
from dayu.services.write_model_challenger_verification import (
    format_write_model_challenger_verification_report,
    verify_write_model_challenger_proposal,
)


def _ready_proposal(
    history_fingerprint: str,
    *,
    fallback_model: str = "mimo-fallback",
) -> dict[str, object]:
    return build_write_model_challenger_proposal(
        recent={
            "run_count": 5,
            "routing_observed_run_count": 5,
            "gate_observed_run_count": 5,
            "gate_pass_rate": 1.0,
            "fallback_switch_count": 4,
        },
        route_pairs=[
            {
                "model_role": "primary",
                "primary_model_name": "deepseek-primary",
                "fallback_model_name": fallback_model,
                "run_count": 5,
                "scene_names": ["write"],
                "primary_scene_call_count": 20,
                "fallback_observed_scene_call_count": 4,
                "fallback_switch_count": 4,
                "fallback_completed_count": 4,
                "fallback_error_count": 0,
                "primary_switch_share": 0.2,
                "fallback_completion_rate": 1.0,
                "fallback_error_rate": 0.0,
            }
        ],
        models=[
            {
                "model_name": "deepseek-primary",
                "status": "degraded",
            },
            {
                "model_name": fallback_model,
                "status": "healthy",
            },
        ],
        history_fingerprint=history_fingerprint,
        selected_run_count=5,
        baseline_run_count=0,
    )


def _not_needed_proposal(
    history_fingerprint: str,
) -> dict[str, object]:
    return build_write_model_challenger_proposal(
        recent={
            "run_count": 5,
            "routing_observed_run_count": 5,
            "gate_observed_run_count": 5,
            "gate_pass_rate": 1.0,
            "fallback_switch_count": 0,
        },
        route_pairs=[],
        models=[],
        history_fingerprint=history_fingerprint,
        selected_run_count=5,
        baseline_run_count=0,
    )


@pytest.mark.unit
def test_verification_exposes_preflight_args_only_for_current_ready_receipt() -> None:
    proposal = _ready_proposal(f"sha256:{'1' * 64}")

    verification = verify_write_model_challenger_proposal(
        proposal,
        proposal,
    )

    assert verification["status"] == "current"
    assert verification["is_current"] is True
    assert verification["action"] == "manual_preflight_required"
    assert verification["preflight_preview"] == {
        "available": True,
        "challenger_cli_args": [
            "--challenger-model-name",
            "mimo-fallback",
        ],
    }
    report = "\n".join(
        format_write_model_challenger_verification_report(verification)
    )
    assert "验证状态   : current" in report
    assert "--challenger-model-name" in report
    assert "未调用模型，未修改配置" in report


@pytest.mark.unit
def test_verification_blocks_preview_when_history_changed() -> None:
    receipt = _ready_proposal(f"sha256:{'1' * 64}")
    current = _ready_proposal(f"sha256:{'2' * 64}")

    verification = verify_write_model_challenger_proposal(
        receipt,
        current,
    )

    assert verification["status"] == "stale_history"
    assert verification["is_current"] is False
    assert verification["reason_codes"] == [
        "history_fingerprint_changed"
    ]
    assert verification["preflight_preview"] == {
        "available": False,
        "challenger_cli_args": [],
    }
    report = "\n".join(
        format_write_model_challenger_verification_report(verification)
    )
    assert "预检参数   : 不可用" in report
    assert "mimo-fallback" not in report


@pytest.mark.unit
def test_verification_detects_policy_or_content_change_on_same_history() -> None:
    history_fingerprint = f"sha256:{'1' * 64}"
    receipt = _ready_proposal(history_fingerprint)
    current = _not_needed_proposal(history_fingerprint)

    verification = verify_write_model_challenger_proposal(
        receipt,
        current,
    )

    assert verification["status"] == "policy_changed"
    assert verification["identity"]["history_matches"] is True
    assert verification["identity"]["proposal_matches"] is False
    assert verification["action"] == "regenerate_proposal"
    assert verification["preflight_preview"]["available"] is False


@pytest.mark.unit
def test_exported_receipt_round_trips_into_current_verification(
    tmp_path: Path,
) -> None:
    proposal = _ready_proposal(f"sha256:{'1' * 64}")
    target = persist_write_model_challenger_proposal(
        proposal,
        tmp_path / "proposal.json",
    )

    loaded_path, receipt = load_write_model_challenger_proposal(target)
    verification = verify_write_model_challenger_proposal(
        receipt,
        proposal,
    )

    assert loaded_path == target
    assert verification["status"] == "current"
    assert verification["preflight_preview"]["available"] is True
