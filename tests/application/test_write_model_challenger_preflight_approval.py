"""Operator approval tests for Challenger common preflight."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dayu.services.write_model_challenger_preflight_approval import (
    WriteModelPreflightApprovalBlockedError,
    build_write_model_challenger_preflight_approval,
    load_write_model_challenger_preflight_approval,
    load_write_model_challenger_preflight_approval_request,
    persist_write_model_challenger_preflight_approval,
    validate_write_model_challenger_preflight_approval,
    validate_write_model_challenger_preflight_approval_request,
    verify_write_model_challenger_preflight_approval,
)
from dayu.services.write_model_challenger_proposal import (
    build_write_model_challenger_proposal,
)


def _ready_proposal(
    history_fingerprint: str = f"sha256:{'1' * 64}",
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
                "fallback_model_name": "mimo-fallback",
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
                "model_name": "mimo-fallback",
                "status": "healthy",
            },
        ],
        history_fingerprint=history_fingerprint,
        selected_run_count=5,
        baseline_run_count=0,
    )


def _not_needed_proposal(
    history_fingerprint: str = f"sha256:{'1' * 64}",
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


def _approval_request(
    proposal: dict[str, object],
    *,
    approved_at: datetime,
    expires_at: datetime | None = None,
    approval_reference: str = "OPS-42",
) -> dict[str, object]:
    evidence_window = proposal["evidence_window"]
    assert isinstance(evidence_window, dict)
    resolved_expiry = expires_at or approved_at + timedelta(hours=1)
    return {
        "schema_version": ("write_model_challenger_preflight_approval_request_v1"),
        "approval_type": "write_model_challenger_common_preflight",
        "scope": "champion_challenger_common_preflight_only",
        "approved_by": "operator@example.test",
        "approval_reference": approval_reference,
        "approved_at": approved_at.isoformat().replace("+00:00", "Z"),
        "expires_at": resolved_expiry.isoformat().replace("+00:00", "Z"),
        "proposal_fingerprint": proposal["proposal_fingerprint"],
        "history_fingerprint": evidence_window["history_fingerprint"],
        "acknowledgements": [
            "common_preflight_only",
            "no_model_execution",
            "no_configuration_change",
            "no_challenger_run_authorization",
            "no_challenger_promotion_authorization",
        ],
    }


def _resign_approval(payload: dict[str, object]) -> None:
    unsigned = dict(payload)
    unsigned.pop("approval_fingerprint", None)
    serialized = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    payload["approval_fingerprint"] = "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_approval(
    proposal: dict[str, object],
    *,
    approved_at: datetime,
) -> dict[str, object]:
    return build_write_model_challenger_preflight_approval(
        request=_approval_request(
            proposal,
            approved_at=approved_at,
        ),
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=approved_at,
    )


def _verify_approval(
    *,
    approval: dict[str, object],
    proposal_receipt: dict[str, object],
    current_proposal: dict[str, object],
    now: datetime,
    actual_cli_args: list[str] | None = None,
    actual_current_models: dict[str, str] | None = None,
) -> dict[str, object]:
    return verify_write_model_challenger_preflight_approval(
        approval=approval,
        proposal_receipt=proposal_receipt,
        current_proposal=current_proposal,
        actual_cli_args=actual_cli_args
        or [
            "--preflight-only",
            "--challenger-model-name",
            "mimo-fallback",
        ],
        actual_current_models=actual_current_models
        or {"primary": "deepseek-primary"},
        now=now,
    )


@pytest.mark.unit
def test_build_preflight_approval_binds_current_ready_proposal() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    request = _approval_request(proposal, approved_at=now)

    approval = build_write_model_challenger_preflight_approval(
        request=request,
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now,
    )

    assert approval["schema_version"] == ("write_model_challenger_preflight_approval_v1")
    assert approval["status"] == "approved_for_common_preflight"
    assert approval["scope"] == ("champion_challenger_common_preflight_only")
    assert approval["proposal_fingerprint"] == (proposal["proposal_fingerprint"])
    evidence_window = proposal["evidence_window"]
    assert isinstance(evidence_window, dict)
    assert approval["history_fingerprint"] == (evidence_window["history_fingerprint"])
    assert approval["approved_cli_args"] == [
        "--preflight-only",
        "--challenger-model-name",
        "mimo-fallback",
    ]
    assert "approval_does_not_authorize_challenger_execution" in (approval["safety_boundaries"])
    assert str(approval["request_fingerprint"]).startswith("sha256:")
    assert str(approval["approval_fingerprint"]).startswith("sha256:")
    validate_write_model_challenger_preflight_approval(approval)


@pytest.mark.unit
def test_verify_preflight_approval_authorizes_exact_current_command() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    approval = _build_approval(proposal, approved_at=now)

    verification = _verify_approval(
        approval=approval,
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now + timedelta(minutes=1),
    )

    assert verification["schema_version"] == (
        "write_model_challenger_preflight_approval_verification_v1"
    )
    assert verification["status"] == "approved"
    assert verification["preflight_authorized"] is True
    assert verification["action"] == "run_common_preflight"
    assert verification["reason_codes"] == [
        "common_preflight_approved"
    ]
    assert verification["expected_current_models"] == {
        "primary": "deepseek-primary"
    }
    assert verification["actual_current_models"] == {
        "primary": "deepseek-primary"
    }
    safety_boundaries = verification["safety_boundaries"]
    assert isinstance(safety_boundaries, list)
    assert (
        "approval_does_not_authorize_challenger_execution"
        in safety_boundaries
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("checked_at", "expected_status"),
    [
        (
            datetime(2026, 7, 24, 7, 59, tzinfo=UTC),
            "not_effective",
        ),
        (
            datetime(2026, 7, 24, 9, 0, tzinfo=UTC),
            "expired",
        ),
    ],
)
def test_verify_preflight_approval_blocks_outside_effective_window(
    checked_at: datetime,
    expected_status: str,
) -> None:
    approved_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    approval = _build_approval(proposal, approved_at=approved_at)

    verification = _verify_approval(
        approval=approval,
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=checked_at,
    )

    assert verification["status"] == expected_status
    assert verification["preflight_authorized"] is False
    assert verification["action"] == "stop"


@pytest.mark.unit
def test_verify_preflight_approval_blocks_stale_history() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    receipt = _ready_proposal()
    approval = _build_approval(receipt, approved_at=now)

    verification = _verify_approval(
        approval=approval,
        proposal_receipt=receipt,
        current_proposal=_ready_proposal(f"sha256:{'2' * 64}"),
        now=now,
    )

    assert verification["status"] == "stale_history"
    assert verification["preflight_authorized"] is False
    assert verification["action"] == "stop"


@pytest.mark.unit
def test_verify_preflight_approval_blocks_changed_approved_arguments() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    approval = _build_approval(proposal, approved_at=now)
    approval["approved_cli_args"] = [
        "--preflight-only",
        "--challenger-model-name",
        "other-challenger",
    ]
    _resign_approval(approval)

    verification = _verify_approval(
        approval=approval,
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now,
    )

    assert verification["status"] == "approved_arguments_changed"
    assert verification["preflight_authorized"] is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("actual_cli_args", "actual_current_models", "expected_reason"),
    [
        (
            [
                "--preflight-only",
                "--challenger-model-name",
                "different-challenger",
            ],
            {"primary": "deepseek-primary"},
            "command_arguments_do_not_match_approval",
        ),
        (
            [
                "--preflight-only",
                "--challenger-model-name",
                "mimo-fallback",
            ],
            {"primary": "different-champion"},
            "current_models_do_not_match_proposal",
        ),
    ],
)
def test_verify_preflight_approval_blocks_changed_actual_command(
    actual_cli_args: list[str],
    actual_current_models: dict[str, str],
    expected_reason: str,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    approval = _build_approval(proposal, approved_at=now)

    verification = _verify_approval(
        approval=approval,
        proposal_receipt=proposal,
        current_proposal=proposal,
        actual_cli_args=actual_cli_args,
        actual_current_models=actual_current_models,
        now=now,
    )

    assert verification["status"] == "command_mismatch"
    assert verification["reason_codes"] == [expected_reason]
    assert verification["preflight_authorized"] is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("request_time_offset", "expiry_offset", "expected_message"),
    [
        (timedelta(minutes=1), timedelta(hours=1), "not effective"),
        (timedelta(hours=-2), timedelta(hours=-1), "expired"),
    ],
)
def test_preflight_approval_blocks_outside_effective_window(
    request_time_offset: timedelta,
    expiry_offset: timedelta,
    expected_message: str,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    request = _approval_request(
        proposal,
        approved_at=now + request_time_offset,
        expires_at=now + expiry_offset,
    )

    with pytest.raises(
        WriteModelPreflightApprovalBlockedError,
        match=expected_message,
    ):
        build_write_model_challenger_preflight_approval(
            request=request,
            proposal_receipt=proposal,
            current_proposal=proposal,
            now=now,
        )


@pytest.mark.unit
def test_preflight_approval_blocks_fingerprint_mismatch() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    request = _approval_request(proposal, approved_at=now)
    request["proposal_fingerprint"] = f"sha256:{'9' * 64}"

    with pytest.raises(
        WriteModelPreflightApprovalBlockedError,
        match="proposal fingerprint does not match",
    ):
        build_write_model_challenger_preflight_approval(
            request=request,
            proposal_receipt=proposal,
            current_proposal=proposal,
            now=now,
        )


@pytest.mark.unit
def test_preflight_approval_blocks_stale_or_non_ready_proposal() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    receipt = _ready_proposal()
    request = _approval_request(receipt, approved_at=now)

    with pytest.raises(
        WriteModelPreflightApprovalBlockedError,
        match="not current",
    ):
        build_write_model_challenger_preflight_approval(
            request=request,
            proposal_receipt=receipt,
            current_proposal=_ready_proposal(f"sha256:{'2' * 64}"),
            now=now,
        )

    not_needed = _not_needed_proposal()
    not_needed_request = _approval_request(
        not_needed,
        approved_at=now,
    )
    with pytest.raises(
        WriteModelPreflightApprovalBlockedError,
        match="not ready",
    ):
        build_write_model_challenger_preflight_approval(
            request=not_needed_request,
            proposal_receipt=not_needed,
            current_proposal=not_needed,
            now=now,
        )


@pytest.mark.unit
def test_approval_request_rejects_extra_fields_and_long_validity() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    request = _approval_request(proposal, approved_at=now)
    request["command"] = "dayu-cli write"

    with pytest.raises(ValueError, match="unexpected"):
        validate_write_model_challenger_preflight_approval_request(request)

    request = _approval_request(
        proposal,
        approved_at=now,
        expires_at=now + timedelta(hours=25),
    )
    with pytest.raises(ValueError, match="24 hours"):
        validate_write_model_challenger_preflight_approval_request(request)


@pytest.mark.unit
def test_approval_validation_rejects_tampering_and_unsafe_args() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    approval = build_write_model_challenger_preflight_approval(
        request=_approval_request(proposal, approved_at=now),
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now,
    )
    approval["approval_reference"] = "OPS-99"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_write_model_challenger_preflight_approval(approval)

    approval = build_write_model_challenger_preflight_approval(
        request=_approval_request(proposal, approved_at=now),
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now,
    )
    approval["approved_cli_args"] = [
        "--preflight-only",
        "--output",
        "unsafe",
    ]
    _resign_approval(approval)
    with pytest.raises(ValueError, match="unsupported.*argument"):
        validate_write_model_challenger_preflight_approval(approval)

    approval = build_write_model_challenger_preflight_approval(
        request=_approval_request(proposal, approved_at=now),
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now,
    )
    approval["approved_cli_args"] = [
        "--preflight-only",
        "--challenger-model-name",
        "mimo fallback",
    ]
    _resign_approval(approval)
    with pytest.raises(ValueError, match="invalid.*model name"):
        validate_write_model_challenger_preflight_approval(approval)


@pytest.mark.unit
def test_preflight_approval_persistence_is_immutable_and_idempotent(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    request = _approval_request(proposal, approved_at=now)
    request_path = tmp_path / "approval-request.json"
    request_path.write_text(
        json.dumps(request, ensure_ascii=False),
        encoding="utf-8",
    )
    loaded_request_path, loaded_request = load_write_model_challenger_preflight_approval_request(request_path)
    assert loaded_request_path == request_path.resolve()
    assert loaded_request == request

    approval = build_write_model_challenger_preflight_approval(
        request=request,
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now,
    )
    target = tmp_path / "receipts" / "approval.json"
    assert (
        persist_write_model_challenger_preflight_approval(
            approval,
            target,
        )
        == target.resolve()
    )
    original = target.read_text(encoding="utf-8")
    assert (
        persist_write_model_challenger_preflight_approval(
            approval,
            target,
        )
        == target.resolve()
    )
    assert target.read_text(encoding="utf-8") == original

    changed = build_write_model_challenger_preflight_approval(
        request=_approval_request(
            proposal,
            approved_at=now,
            approval_reference="OPS-43",
        ),
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now,
    )
    with pytest.raises(FileExistsError, match="different content"):
        persist_write_model_challenger_preflight_approval(changed, target)

    loaded_path, loaded = load_write_model_challenger_preflight_approval(target)
    assert loaded_path == target.resolve()
    assert loaded == approval
    assert not list(target.parent.glob("*.tmp"))
