"""Configuration change request and human approval gate tests."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dayu.services.write_model_challenger_promotion import (
    build_write_model_challenger_promotion_proposal,
    persist_write_model_challenger_promotion_proposal,
)
from dayu.services.write_model_configuration_change import (
    WriteModelConfigurationChangeBlockedError,
    build_write_model_configuration_change_approval,
    build_write_model_configuration_change_request,
    format_write_model_configuration_change_approval_report,
    format_write_model_configuration_change_approval_verification_report,
    format_write_model_configuration_change_request_report,
    format_write_model_configuration_change_request_verification_report,
    load_write_model_configuration_change_approval,
    load_write_model_configuration_change_request,
    persist_write_model_configuration_change_approval,
    persist_write_model_configuration_change_request,
    validate_write_model_configuration_change_approval,
    validate_write_model_configuration_change_approval_request,
    validate_write_model_configuration_change_request,
    verify_write_model_configuration_change_approval,
    verify_write_model_configuration_change_request,
)
from dayu.services.write_run_comparison import (
    compare_write_run_paths,
    persist_write_run_comparison,
)


def _summary(
    *,
    primary_model: str,
    cost: float,
    primary_scene_models: dict[str, str] | None = None,
) -> dict[str, Any]:
    scene_models = primary_scene_models or {
        "infer": primary_model,
        "write": primary_model,
        "decision": primary_model,
        "overview": primary_model,
    }
    return {
        "schema_version": "write_run_summary_v3",
        "ticker": "AAPL",
        "gate_status": "passed",
        "model_roles": {
            "primary": {
                "model_names": sorted(set(scene_models.values())),
                "scenes": [
                    {
                        "scene_name": scene_name,
                        "model_name": model_name,
                        "temperature": 0.2,
                    }
                    for scene_name, model_name in sorted(
                        scene_models.items()
                    )
                ],
            },
            "audit": {
                "model_names": ["audit-model"],
                "scenes": [
                    {
                        "scene_name": "audit",
                        "model_name": "audit-model",
                        "temperature": 0.0,
                    },
                    {
                        "scene_name": "confirm",
                        "model_name": "audit-model",
                        "temperature": 0.0,
                    },
                ],
            },
        },
        "model_usage": {
            "usage_status": "complete",
            "scene_call_count": 10,
            "request_count": 10,
            "total_tokens": 1_000,
            "cost": {
                "status": "complete",
                "currency": "CNY",
                "known_estimated_cost": cost,
            },
        },
        "model_routing": {
            "fallback_switch_count": 0,
            "fallback_call_completed_count": 0,
            "fallback_call_error_count": 0,
            "routes": [],
        },
        "chapter_count": 1,
        "failed_count": 0,
        "audit": {
            "required": True,
            "failed_count": 0,
            "gate_blocked_count": 0,
            "first_pass_count": 1,
            "total_retries": 0,
        },
        "chapters": [
            {
                "index": 1,
                "title": "Business",
                "gate_passed": True,
                "audit_passed": True,
            }
        ],
    }


def _promotion(
    tmp_path: Path,
    *,
    challenger: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    champion_dir = tmp_path / "champion"
    challenger_dir = tmp_path / "challenger"
    champion_dir.mkdir(parents=True)
    challenger_dir.mkdir(parents=True)
    champion_summary = champion_dir / "run_summary.json"
    challenger_summary = challenger_dir / "run_summary.json"
    champion_summary.write_text(
        json.dumps(
            _summary(
                primary_model="deepseek-primary",
                cost=1.0,
            )
        ),
        encoding="utf-8",
    )
    challenger_summary.write_text(
        json.dumps(
            challenger
            or _summary(
                primary_model="mimo-challenger",
                cost=0.7,
            )
        ),
        encoding="utf-8",
    )
    comparison = compare_write_run_paths(
        champion_summary,
        challenger_summary,
    )
    comparison_path = persist_write_run_comparison(
        comparison,
        champion_dir / "challenger_comparison.json",
    )
    proposal = build_write_model_challenger_promotion_proposal(
        comparison_path
    )
    proposal_path = persist_write_model_challenger_promotion_proposal(
        proposal,
        tmp_path / "promotion.json",
    )
    return proposal_path, proposal


def _approval_request(
    change_request: dict[str, Any],
    *,
    approved_at: str = "2026-07-26T08:00:00Z",
    expires_at: str = "2026-07-26T10:00:00Z",
) -> dict[str, Any]:
    source = change_request["source_promotion_proposal"]
    return {
        "schema_version": (
            "write_model_challenger_configuration_change_"
            "approval_request_v1"
        ),
        "approval_type": (
            "write_model_challenger_configuration_change"
        ),
        "scope": (
            "one_future_write_scene_routing_change_"
            "subject_to_runtime_match"
        ),
        "approved_by": "operator@example.com",
        "approval_reference": "OPS-2026-0726-01",
        "rollback_reference": "ROLLBACK-2026-0726-01",
        "approved_at": approved_at,
        "expires_at": expires_at,
        "configuration_change_request_fingerprint": change_request[
            "request_fingerprint"
        ],
        "promotion_proposal_fingerprint": source[
            "proposal_fingerprint"
        ],
        "acknowledgements": [
            "reviewed_exact_scene_model_transitions",
            (
                "promotion_proposal_and_change_request_"
                "must_remain_current"
            ),
            (
                "runtime_configuration_must_match_observed_"
                "champion_before_application"
            ),
            "rollback_plan_is_ready",
            "approval_is_single_use",
            (
                "issuance_and_verification_do_not_apply_"
                "configuration"
            ),
            (
                "issuance_and_verification_do_not_execute_models"
            ),
            "separate_application_command_required",
        ],
    }


@pytest.mark.unit
def test_build_configuration_change_request_is_scene_level_and_read_only(
    tmp_path: Path,
) -> None:
    proposal_path, proposal = _promotion(tmp_path)

    request = build_write_model_configuration_change_request(
        proposal_path
    )

    assert request["schema_version"] == (
        "write_model_challenger_configuration_change_request_v1"
    )
    assert request["scope"] == (
        "review_only_no_configuration_application"
    )
    assert request["status"] == "ready_for_human_approval"
    assert request["source_promotion_proposal"] == {
        "path": str(proposal_path.resolve()),
        "fingerprint": request["source_promotion_proposal"][
            "fingerprint"
        ],
        "proposal_fingerprint": proposal["proposal_fingerprint"],
    }
    assert request["target"] == {
        "configuration_domain": "write_scene_model_routing",
        "source_semantics": (
            "completed_run_observation_not_current_runtime_"
            "configuration"
        ),
        "changed_roles": ["primary"],
        "transition_count": 4,
    }
    assert [
        transition["scene_name"]
        for transition in request["transitions"]
    ] == ["decision", "infer", "overview", "write"]
    assert all(
        transition["observed_champion_model_name"]
        == "deepseek-primary"
        and transition["proposed_challenger_model_name"]
        == "mimo-challenger"
        for transition in request["transitions"]
    )
    assert "no_configuration_application" in request[
        "safety_boundaries"
    ]
    validate_write_model_configuration_change_request(request)

    verification = verify_write_model_configuration_change_request(
        request
    )
    assert verification["status"] == "current"
    assert verification["action"] == "human_approval_required"
    assert verification["authorizes_configuration_change"] is False
    assert verification["configuration_change_applied"] is False
    assert verification["model_execution_performed"] is False


@pytest.mark.unit
def test_configuration_change_request_rejects_ambiguous_transition(
    tmp_path: Path,
) -> None:
    proposal_path, _proposal = _promotion(
        tmp_path,
        challenger=_summary(
            primary_model="unused",
            cost=0.7,
            primary_scene_models={
                "infer": "mimo-infer",
                "write": "mimo-write",
                "decision": "mimo-write",
                "overview": "mimo-write",
            },
        ),
    )

    with pytest.raises(
        WriteModelConfigurationChangeBlockedError,
        match="ambiguous",
    ):
        build_write_model_configuration_change_request(
            proposal_path
        )


@pytest.mark.unit
def test_configuration_change_request_detects_stale_promotion_evidence(
    tmp_path: Path,
) -> None:
    proposal_path, _proposal = _promotion(tmp_path)
    request = build_write_model_configuration_change_request(
        proposal_path
    )
    champion_summary = tmp_path / "champion" / "run_summary.json"
    payload = json.loads(champion_summary.read_text(encoding="utf-8"))
    payload["completed_at"] = "2026-07-26T09:00:00Z"
    champion_summary.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    verification = verify_write_model_configuration_change_request(
        request
    )

    assert verification["status"] == (
        "promotion_proposal_not_current"
    )
    assert verification["action"] == "stop"
    assert verification["configuration_change_applied"] is False
    with pytest.raises(
        WriteModelConfigurationChangeBlockedError,
        match="not current",
    ):
        build_write_model_configuration_change_request(
            proposal_path
        )


@pytest.mark.unit
def test_configuration_change_request_is_strict_and_immutable(
    tmp_path: Path,
) -> None:
    proposal_path, _proposal = _promotion(tmp_path)
    request = build_write_model_configuration_change_request(
        proposal_path
    )
    target = tmp_path / "receipts" / "change-request.json"

    assert persist_write_model_configuration_change_request(
        request,
        target,
    ) == target.resolve()
    original = target.read_bytes()
    assert persist_write_model_configuration_change_request(
        request,
        target,
    ) == target.resolve()
    assert target.read_bytes() == original
    resolved, loaded = load_write_model_configuration_change_request(
        target
    )
    assert resolved == target.resolve()
    assert loaded == request

    tampered = deepcopy(request)
    tampered["ticker"] = "MSFT"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_write_model_configuration_change_request(tampered)

    other = deepcopy(request)
    other["request_fingerprint"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        persist_write_model_configuration_change_request(
            other,
            target,
        )


@pytest.mark.unit
def test_configuration_change_approval_request_is_strict_and_bounded(
    tmp_path: Path,
) -> None:
    proposal_path, _proposal = _promotion(tmp_path)
    change_request = build_write_model_configuration_change_request(
        proposal_path
    )
    request = _approval_request(change_request)

    validate_write_model_configuration_change_approval_request(
        request
    )

    too_long = _approval_request(
        change_request,
        expires_at="2026-07-26T12:00:01Z",
    )
    with pytest.raises(ValueError, match="cannot exceed 4 hours"):
        validate_write_model_configuration_change_approval_request(
            too_long
        )
    missing_ack = deepcopy(request)
    missing_ack["acknowledgements"].pop()
    with pytest.raises(ValueError, match="acknowledgements"):
        validate_write_model_configuration_change_approval_request(
            missing_ack
        )


@pytest.mark.unit
def test_issue_and_verify_configuration_change_approval_without_apply(
    tmp_path: Path,
) -> None:
    proposal_path, _proposal = _promotion(tmp_path)
    change_request = build_write_model_configuration_change_request(
        proposal_path
    )
    request_path = persist_write_model_configuration_change_request(
        change_request,
        tmp_path / "change-request.json",
    )

    approval = build_write_model_configuration_change_approval(
        approval_request=_approval_request(change_request),
        configuration_change_request_path=request_path,
        configuration_change_request=change_request,
        now=datetime(2026, 7, 26, 9, 0, tzinfo=UTC),
    )

    assert approval["schema_version"] == (
        "write_model_challenger_configuration_change_approval_v1"
    )
    assert approval["status"] == (
        "approved_for_one_future_configuration_change"
    )
    assert approval["maximum_uses"] == 1
    assert approval["configuration_change_request"] == change_request
    assert approval["configuration_change_request_source"]["path"] == (
        str(request_path.resolve())
    )
    validate_write_model_configuration_change_approval(approval)

    verification = verify_write_model_configuration_change_approval(
        approval,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )
    assert verification["status"] == "approved"
    assert verification["action"] == (
        "separate_application_command_required"
    )
    assert (
        verification[
            "eligible_for_future_single_use_application"
        ]
        is True
    )
    assert verification["configuration_change_applied"] is False
    assert verification["approval_consumed"] is False
    assert verification["model_execution_performed"] is False


@pytest.mark.unit
def test_configuration_change_approval_rejects_identity_mismatch(
    tmp_path: Path,
) -> None:
    proposal_path, _proposal = _promotion(tmp_path)
    change_request = build_write_model_configuration_change_request(
        proposal_path
    )
    request_path = persist_write_model_configuration_change_request(
        change_request,
        tmp_path / "change-request.json",
    )
    approval_request = _approval_request(change_request)
    approval_request[
        "configuration_change_request_fingerprint"
    ] = "sha256:" + "0" * 64

    with pytest.raises(
        WriteModelConfigurationChangeBlockedError,
        match="does not match",
    ):
        build_write_model_configuration_change_approval(
            approval_request=approval_request,
            configuration_change_request_path=request_path,
            configuration_change_request=change_request,
            now=datetime(2026, 7, 26, 9, 0, tzinfo=UTC),
        )


@pytest.mark.unit
def test_configuration_change_approval_expiry_and_stale_request_fail_closed(
    tmp_path: Path,
) -> None:
    proposal_path, _proposal = _promotion(tmp_path)
    change_request = build_write_model_configuration_change_request(
        proposal_path
    )
    request_path = persist_write_model_configuration_change_request(
        change_request,
        tmp_path / "change-request.json",
    )
    approval = build_write_model_configuration_change_approval(
        approval_request=_approval_request(change_request),
        configuration_change_request_path=request_path,
        configuration_change_request=change_request,
        now=datetime(2026, 7, 26, 9, 0, tzinfo=UTC),
    )

    expired = verify_write_model_configuration_change_approval(
        approval,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    assert expired["status"] == "expired"
    assert (
        expired["eligible_for_future_single_use_application"]
        is False
    )
    assert expired["configuration_change_applied"] is False

    request_path.write_text(
        request_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    stale = verify_write_model_configuration_change_approval(
        approval,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )
    assert stale["status"] == "stale_configuration_change_request"
    assert stale["action"] == "stop"
    assert stale["configuration_change_applied"] is False


@pytest.mark.unit
def test_configuration_change_approval_persistence_is_immutable(
    tmp_path: Path,
) -> None:
    proposal_path, _proposal = _promotion(tmp_path)
    change_request = build_write_model_configuration_change_request(
        proposal_path
    )
    request_path = persist_write_model_configuration_change_request(
        change_request,
        tmp_path / "change-request.json",
    )
    approval = build_write_model_configuration_change_approval(
        approval_request=_approval_request(change_request),
        configuration_change_request_path=request_path,
        configuration_change_request=change_request,
        now=datetime(2026, 7, 26, 9, 0, tzinfo=UTC),
    )
    approval_path = tmp_path / "approval.json"

    assert persist_write_model_configuration_change_approval(
        approval,
        approval_path,
    ) == approval_path.resolve()
    original = approval_path.read_bytes()
    assert persist_write_model_configuration_change_approval(
        approval,
        approval_path,
    ) == approval_path.resolve()
    assert approval_path.read_bytes() == original
    resolved, loaded = load_write_model_configuration_change_approval(
        approval_path
    )
    assert resolved == approval_path.resolve()
    assert loaded == approval

    changed = deepcopy(approval)
    changed["approval_reference"] = "OTHER"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        persist_write_model_configuration_change_approval(
            changed,
            approval_path,
        )


@pytest.mark.unit
def test_configuration_change_reports_format_all_gate_stages() -> None:
    """验证配置变更四个门禁阶段的报告摘要。

    Returns:
        无。

    Raises:
        AssertionError: 当任一报告缺少预期状态时抛出。
    """
    request_report = format_write_model_configuration_change_request_report(
        {
            "status": "ready_for_human_approval",
            "ticker": "AAPL",
            "target": {
                "changed_roles": ["primary"],
                "transition_count": 1,
            },
        }
    )
    request_verification_report = (
        format_write_model_configuration_change_request_verification_report(
            {
                "status": "current",
                "action": "human_approval_required",
                "reason_codes": [],
            }
        )
    )
    approval_report = format_write_model_configuration_change_approval_report(
        {
            "status": "approved",
            "approved_by": "operator@example.test",
            "approval_reference": "OPS-42",
            "rollback_reference": "ROLLBACK-42",
            "expires_at": "2026-07-26T10:00:00Z",
        }
    )
    approval_verification_report = (
        format_write_model_configuration_change_approval_verification_report(
            {
                "status": "approved",
                "action": "eligible_for_application",
                "reason_codes": [],
            }
        )
    )

    assert any("primary" in line for line in request_report)
    assert any("current" in line for line in request_verification_report)
    assert any("OPS-42" in line for line in approval_report)
    assert any("approved" in line for line in approval_verification_report)


@pytest.mark.unit
@pytest.mark.parametrize(
    "malformed_changed_roles",
    [
        {"primary": "mimo"},
        "primary",
    ],
)
def test_configuration_change_report_rejects_non_list_changed_roles(
    malformed_changed_roles: dict[str, str] | str,
) -> None:
    """验证配置变更报告拒绝字典和文本形式的畸形角色列表。

    Args:
        malformed_changed_roles: 非列表形式的角色值。

    Returns:
        无。

    Raises:
        AssertionError: 当畸形角色值未以精确 TypeError 拒绝时抛出。
    """
    with pytest.raises(TypeError) as exc_info:
        format_write_model_configuration_change_request_report(
            {
                "target": {
                    "changed_roles": malformed_changed_roles,
                },
            }
        )

    assert str(exc_info.value) == (
        "configuration change request target changed_roles must be a list"
    )
