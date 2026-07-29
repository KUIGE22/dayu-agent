"""Single-use authorization tests for isolated Challenger write runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dayu.services.write_model_challenger_preflight_approval import (
    build_write_model_challenger_preflight_approval,
)
from dayu.services.write_model_challenger_proposal import (
    build_write_model_challenger_proposal,
)
from dayu.services.write_model_challenger_run_approval import (
    WriteModelChallengerRunApprovalBlockedError,
    WriteModelChallengerRunApprovalConsumedError,
    build_write_model_challenger_run_approval,
    build_write_model_challenger_run_plan,
    consume_write_model_challenger_run_approval,
    load_write_model_challenger_run_approval,
    load_write_model_challenger_run_plan,
    persist_write_model_challenger_run_approval,
    persist_write_model_challenger_run_plan,
    validate_write_model_challenger_run_approval,
    validate_write_model_challenger_run_approval_request,
    validate_write_model_challenger_run_plan,
    verify_write_model_challenger_run_approval,
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


def _preflight_request(
    proposal: dict[str, object],
    *,
    approved_at: datetime,
) -> dict[str, object]:
    evidence_window = proposal["evidence_window"]
    assert isinstance(evidence_window, dict)
    return {
        "schema_version": (
            "write_model_challenger_preflight_approval_request_v1"
        ),
        "approval_type": "write_model_challenger_common_preflight",
        "scope": "champion_challenger_common_preflight_only",
        "approved_by": "operator@example.test",
        "approval_reference": "OPS-PREFLIGHT-42",
        "approved_at": approved_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
        "expires_at": (
            approved_at + timedelta(hours=1)
        ).isoformat().replace("+00:00", "Z"),
        "proposal_fingerprint": proposal["proposal_fingerprint"],
        "history_fingerprint": evidence_window[
            "history_fingerprint"
        ],
        "acknowledgements": [
            "common_preflight_only",
            "no_model_execution",
            "no_configuration_change",
            "no_challenger_run_authorization",
            "no_challenger_promotion_authorization",
        ],
    }


def _preflight_approval(
    proposal: dict[str, object],
    *,
    now: datetime,
) -> dict[str, object]:
    return build_write_model_challenger_preflight_approval(
        request=_preflight_request(proposal, approved_at=now),
        proposal_receipt=proposal,
        current_proposal=proposal,
        now=now,
    )


def _plan(
    tmp_path: Path,
    *,
    write_max_retries: int = 2,
) -> dict[str, object]:
    template = tmp_path / "template.md"
    template.write_text("# Research\n", encoding="utf-8")
    return build_write_model_challenger_run_plan(
        ticker="AAPL",
        template_path=template,
        champion_output_dir=tmp_path / "champion",
        challenger_output_dir=tmp_path / "challenger",
        current_models={"primary": "deepseek-primary"},
        challenger_cli_args=[
            "--challenger-model-name",
            "mimo-fallback",
        ],
        fallback_models={},
        write_max_retries=write_max_retries,
        web_provider="auto",
        temperature=None,
        maximum_model_requests_per_run=60,
        maximum_total_tokens_per_run=1_500_000,
        maximum_estimated_cost_per_run=12.5,
        budget_currency="cny",
    )


def _run_request(
    *,
    proposal: dict[str, object],
    preflight_approval: dict[str, object],
    plan: dict[str, object],
    approved_at: datetime,
    expires_at: datetime | None = None,
) -> dict[str, object]:
    evidence_window = proposal["evidence_window"]
    assert isinstance(evidence_window, dict)
    return {
        "schema_version": (
            "write_model_challenger_run_approval_request_v1"
        ),
        "approval_type": "write_model_challenger_isolated_run",
        "scope": "one_bounded_isolated_champion_challenger_run",
        "approved_by": "operator@example.test",
        "approval_reference": "OPS-RUN-42",
        "approved_at": approved_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
        "expires_at": (
            expires_at or approved_at + timedelta(hours=2)
        ).isoformat().replace("+00:00", "Z"),
        "proposal_fingerprint": proposal["proposal_fingerprint"],
        "history_fingerprint": evidence_window[
            "history_fingerprint"
        ],
        "preflight_approval_fingerprint": preflight_approval[
            "approval_fingerprint"
        ],
        "execution_plan": plan,
        "acknowledgements": [
            "authorizes_champion_and_challenger_model_execution",
            "preflight_must_pass_before_execution",
            "isolated_outputs_are_new_and_distinct",
            "per_run_budget_applies_to_each_run_separately",
            "authorization_is_single_use",
            "no_configuration_change_authorization",
            "no_challenger_promotion_authorization",
        ],
    }


def _approval(
    tmp_path: Path,
    *,
    now: datetime,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    proposal = _ready_proposal()
    preflight = _preflight_approval(proposal, now=now)
    plan = _plan(tmp_path)
    approval = build_write_model_challenger_run_approval(
        request=_run_request(
            proposal=proposal,
            preflight_approval=preflight,
            plan=plan,
            approved_at=now,
        ),
        preflight_approval=preflight,
        proposal_receipt=proposal,
        current_proposal=proposal,
        actual_execution_plan=plan,
        preflight_passed=True,
        now=now,
    )
    return approval, proposal, plan


@pytest.mark.unit
def test_run_plan_binds_template_outputs_models_and_budget(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)

    assert plan["schema_version"] == (
        "write_model_challenger_run_plan_v1"
    )
    template = plan["template"]
    assert isinstance(template, dict)
    assert str(template["fingerprint"]).startswith("sha256:")
    budget = plan["budget"]
    assert isinstance(budget, dict)
    assert budget["maximum_estimated_cost_per_run"] == "12.5"
    assert budget["maximum_estimated_experiment_cost"] == "25"
    assert budget["currency"] == "CNY"
    assert str(plan["plan_fingerprint"]).startswith("sha256:")
    validate_write_model_challenger_run_plan(plan)


@pytest.mark.unit
def test_run_plan_rejects_tampering(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    execution = plan["execution"]
    assert isinstance(execution, dict)
    execution["resume"] = True

    with pytest.raises(ValueError, match="resume must be false"):
        validate_write_model_challenger_run_plan(plan)


@pytest.mark.unit
def test_build_run_approval_binds_passed_preflight_and_exact_plan(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval, proposal, plan = _approval(tmp_path, now=now)

    assert approval["schema_version"] == (
        "write_model_challenger_run_approval_v1"
    )
    assert approval["status"] == "approved_for_one_isolated_run"
    assert approval["maximum_uses"] == 1
    assert approval["proposal_fingerprint"] == (
        proposal["proposal_fingerprint"]
    )
    assert approval["execution_plan"] == plan
    safety_boundaries = approval["safety_boundaries"]
    assert isinstance(safety_boundaries, list)
    assert "approval_is_consumed_before_host_initialization" in (
        safety_boundaries
    )
    validate_write_model_challenger_run_approval(approval)


@pytest.mark.unit
def test_build_run_approval_requires_successful_preflight(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    preflight = _preflight_approval(proposal, now=now)
    plan = _plan(tmp_path)

    with pytest.raises(
        WriteModelChallengerRunApprovalBlockedError,
        match="did not pass",
    ):
        build_write_model_challenger_run_approval(
            request=_run_request(
                proposal=proposal,
                preflight_approval=preflight,
                plan=plan,
                approved_at=now,
            ),
            preflight_approval=preflight,
            proposal_receipt=proposal,
            current_proposal=proposal,
            actual_execution_plan=plan,
            preflight_passed=False,
            now=now,
        )


@pytest.mark.unit
def test_build_run_approval_rejects_request_plan_mismatch(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    preflight = _preflight_approval(proposal, now=now)
    plan = _plan(tmp_path)
    different_plan = _plan(tmp_path, write_max_retries=3)

    with pytest.raises(
        WriteModelChallengerRunApprovalBlockedError,
        match="execution plan does not match",
    ):
        build_write_model_challenger_run_approval(
            request=_run_request(
                proposal=proposal,
                preflight_approval=preflight,
                plan=different_plan,
                approved_at=now,
            ),
            preflight_approval=preflight,
            proposal_receipt=proposal,
            current_proposal=proposal,
            actual_execution_plan=plan,
            preflight_passed=True,
            now=now,
        )


@pytest.mark.unit
def test_run_approval_request_rejects_long_window(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    proposal = _ready_proposal()
    preflight = _preflight_approval(proposal, now=now)
    request = _run_request(
        proposal=proposal,
        preflight_approval=preflight,
        plan=_plan(tmp_path),
        approved_at=now,
        expires_at=now + timedelta(hours=5),
    )

    with pytest.raises(ValueError, match="4 hours"):
        validate_write_model_challenger_run_approval_request(
            request
        )


@pytest.mark.unit
def test_verify_run_approval_authorizes_current_exact_plan(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval, proposal, plan = _approval(tmp_path, now=now)

    verification = verify_write_model_challenger_run_approval(
        approval=approval,
        proposal_receipt=proposal,
        current_proposal=proposal,
        actual_execution_plan=plan,
        now=now + timedelta(minutes=5),
    )

    assert verification["status"] == "approved"
    assert verification["run_authorized"] is True
    assert verification["action"] == "consume_and_run_once"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("change", "expected_status"),
    [
        ("plan", "command_mismatch"),
        ("history", "stale_history"),
        ("expired", "expired"),
    ],
)
def test_verify_run_approval_fails_closed(
    tmp_path: Path,
    change: str,
    expected_status: str,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval, proposal, plan = _approval(tmp_path, now=now)
    current_proposal = proposal
    actual_plan = plan
    checked_at = now
    if change == "plan":
        actual_plan = _plan(tmp_path, write_max_retries=3)
    elif change == "history":
        current_proposal = _ready_proposal(f"sha256:{'2' * 64}")
    else:
        checked_at = now + timedelta(hours=2)

    verification = verify_write_model_challenger_run_approval(
        approval=approval,
        proposal_receipt=proposal,
        current_proposal=current_proposal,
        actual_execution_plan=actual_plan,
        now=checked_at,
    )

    assert verification["status"] == expected_status
    assert verification["run_authorized"] is False
    assert verification["action"] == "stop"


@pytest.mark.unit
def test_run_plan_and_approval_persistence_are_immutable(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval, _proposal, plan = _approval(tmp_path, now=now)
    plan_path = tmp_path / "receipts" / "run-plan.json"
    approval_path = tmp_path / "receipts" / "run-approval.json"

    assert (
        persist_write_model_challenger_run_plan(plan, plan_path)
        == plan_path.resolve()
    )
    assert (
        persist_write_model_challenger_run_plan(plan, plan_path)
        == plan_path.resolve()
    )
    assert (
        persist_write_model_challenger_run_approval(
            approval,
            approval_path,
        )
        == approval_path.resolve()
    )
    loaded_plan_path, loaded_plan = (
        load_write_model_challenger_run_plan(plan_path)
    )
    loaded_approval_path, loaded_approval = (
        load_write_model_challenger_run_approval(approval_path)
    )
    assert loaded_plan_path == plan_path.resolve()
    assert loaded_plan == plan
    assert loaded_approval_path == approval_path.resolve()
    assert loaded_approval == approval

    changed_plan = _plan(tmp_path, write_max_retries=3)
    with pytest.raises(FileExistsError, match="different content"):
        persist_write_model_challenger_run_plan(
            changed_plan,
            plan_path,
        )


@pytest.mark.unit
def test_run_approval_consumption_is_atomic_and_single_use(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    approval, _proposal, _plan_value = _approval(
        tmp_path,
        now=now,
    )
    workspace = tmp_path / "workspace"

    consumption_path = consume_write_model_challenger_run_approval(
        approval=approval,
        workspace_dir=workspace,
        now=now,
    )

    payload = json.loads(
        consumption_path.read_text(encoding="utf-8")
    )
    assert payload["approval_fingerprint"] == (
        approval["approval_fingerprint"]
    )
    assert consumption_path.is_file()
    with pytest.raises(
        WriteModelChallengerRunApprovalConsumedError,
        match="already consumed",
    ):
        consume_write_model_challenger_run_approval(
            approval=approval,
            workspace_dir=workspace,
            now=now + timedelta(seconds=1),
        )
    assert not list(consumption_path.parent.glob("*.tmp"))
