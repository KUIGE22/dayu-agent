"""Resolved routing snapshot and pre-application plan tests."""

from __future__ import annotations

from argparse import Namespace
import base64
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from dayu.services import (
    write_model_configuration_application as configuration_application_module,
)
from dayu.services import (
    write_model_configuration_rollback_application as rollback_application_module,
)
from dayu.services import (
    write_model_configuration_manual_recovery_application as manual_recovery_application_module,
)
from dayu.services import (
    write_model_configuration_manual_recovery_clearance as manual_recovery_clearance_module,
)
from dayu.cli.commands.write import (
    _run_write_model_configuration_manual_recovery_evidence,
    _run_write_preflight,
)
from dayu.services.contracts import (
    WriteModelRole,
    WritePreflightResult,
    WritePreflightScene,
    WriteRunConfig,
)
from dayu.services.internal.write_pipeline.enums import (
    AUDIT_WRITE_SCENES,
    PRIMARY_MODEL_WRITE_SCENES,
)
from dayu.services.write_model_challenger_promotion import (
    build_write_model_challenger_promotion_proposal,
    persist_write_model_challenger_promotion_proposal,
)
from dayu.services.write_model_configuration_change import (
    build_write_model_configuration_change_approval,
    build_write_model_configuration_change_request,
    persist_write_model_configuration_change_approval,
    persist_write_model_configuration_change_request,
)
from dayu.services.write_model_configuration_application import (
    WriteModelConfigurationApplicationBlockedError,
    apply_write_model_configuration_preapplication_plan,
    create_write_model_configuration_transaction_lock,
    load_write_model_configuration_application_receipt,
    validate_write_model_configuration_application_receipt,
    verify_write_model_configuration_application_receipt,
)
from dayu.services.write_model_configuration_preapplication import (
    WriteModelConfigurationPreapplicationBlockedError,
    build_write_model_configuration_preapplication_plan,
    build_write_scene_model_routing_snapshot,
    load_write_model_configuration_preapplication_plan,
    load_write_scene_model_routing_snapshot,
    persist_write_model_configuration_preapplication_plan,
    persist_write_scene_model_routing_snapshot,
    validate_write_model_configuration_preapplication_plan,
    validate_write_scene_model_routing_snapshot,
    verify_write_model_configuration_preapplication_plan,
    verify_write_scene_model_routing_snapshot,
)
from dayu.services.write_model_configuration_rollback import (
    WriteModelConfigurationRollbackBlockedError,
    build_write_model_configuration_operator_rollback_approval,
    build_write_model_configuration_operator_rollback_plan,
    load_write_model_configuration_operator_rollback_approval,
    load_write_model_configuration_operator_rollback_plan,
    persist_write_model_configuration_operator_rollback_approval,
    persist_write_model_configuration_operator_rollback_plan,
    validate_write_model_configuration_operator_rollback_plan,
    verify_write_model_configuration_operator_rollback_approval,
    verify_write_model_configuration_operator_rollback_plan,
)
from dayu.services.write_model_configuration_rollback_application import (
    WriteModelConfigurationRollbackApplicationBlockedError,
    WriteModelConfigurationRollbackApplicationBusyError,
    apply_write_model_configuration_operator_rollback,
    build_write_model_configuration_manual_recovery_evidence,
    build_write_model_configuration_operator_rollback_retry_plan,
    format_write_model_configuration_manual_recovery_evidence_report,
    load_write_model_configuration_manual_recovery_evidence,
    load_write_model_configuration_operator_rollback_receipt,
    persist_write_model_configuration_manual_recovery_evidence,
    validate_write_model_configuration_manual_recovery_evidence,
    validate_write_model_configuration_operator_rollback_receipt,
    validate_write_model_configuration_operator_rollback_verification,
    verify_write_model_configuration_operator_rollback_receipt,
)
from dayu.services.write_model_configuration_manual_recovery import (
    assert_write_model_configuration_manual_recovery_approval_current,
    assert_write_model_configuration_manual_recovery_plan_current,
    build_write_model_configuration_manual_recovery_approval,
    build_write_model_configuration_manual_recovery_plan,
    format_write_model_configuration_manual_recovery_approval_report,
    format_write_model_configuration_manual_recovery_plan_report,
    persist_write_model_configuration_manual_recovery_approval,
    persist_write_model_configuration_manual_recovery_plan,
    validate_write_model_configuration_manual_recovery_approval,
    validate_write_model_configuration_manual_recovery_approval_request,
    validate_write_model_configuration_manual_recovery_plan,
    validate_write_model_configuration_manual_recovery_selection_request,
)
from dayu.services.write_model_configuration_manual_recovery_application import (
    WriteModelConfigurationManualRecoveryApplicationBlockedError,
    apply_write_model_configuration_manual_recovery,
    format_write_model_configuration_manual_recovery_receipt_report,
    load_write_model_configuration_manual_recovery_consumption,
    load_write_model_configuration_manual_recovery_intent,
    load_write_model_configuration_manual_recovery_receipt,
    validate_write_model_configuration_manual_recovery_consumption,
    validate_write_model_configuration_manual_recovery_intent,
    validate_write_model_configuration_manual_recovery_receipt,
)
from dayu.services.write_model_configuration_manual_recovery_clearance import (
    WriteModelConfigurationManualRecoveryAuditTimelineChangedError,
    WriteModelConfigurationManualRecoveryClearanceBlockedError,
    WriteModelConfigurationManualRecoveryClearanceBusyError,
    WriteModelConfigurationManualRecoveryClearanceReceiptError,
    WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError,
    WriteModelConfigurationManualRecoveryClearanceRevocationReceiptError,
    WriteModelConfigurationManualRecoveryGateVerificationChangedError,
    WriteModelConfigurationManualRecoveryRestartBlockedError,
    WriteModelConfigurationManualRecoveryRestartBusyError,
    assess_write_model_configuration_manual_recovery_gate,
    build_write_model_configuration_manual_recovery_audit_timeline,
    format_write_model_configuration_manual_recovery_audit_timeline_report,
    format_write_model_configuration_manual_recovery_clearance_report,
    format_write_model_configuration_manual_recovery_gate_report,
    format_write_model_configuration_manual_recovery_gate_verification_report,
    issue_write_model_configuration_manual_recovery_clearance,
    load_write_model_configuration_manual_recovery_clearance_revocation,
    persist_write_model_configuration_manual_recovery_audit_timeline,
    persist_write_model_configuration_manual_recovery_gate,
    persist_write_model_configuration_manual_recovery_gate_verification,
    restart_write_model_configuration_manual_recovery_after_clearance_revocation,
    revoke_write_model_configuration_manual_recovery_clearance,
    validate_write_model_configuration_manual_recovery_clearance,
    validate_write_model_configuration_manual_recovery_clearance_request,
    validate_write_model_configuration_manual_recovery_clearance_revocation,
    validate_write_model_configuration_manual_recovery_audit_timeline,
    validate_write_model_configuration_manual_recovery_gate,
    validate_write_model_configuration_manual_recovery_gate_verification,
    verify_write_model_configuration_manual_recovery_gate_snapshot,
    write_model_configuration_manual_recovery_clearance_root,
    write_model_configuration_manual_recovery_clearance_revocation_root,
)
from dayu.services.write_model_configuration_manual_recovery_verification import (
    WriteModelConfigurationManualRecoveryVerificationBlockedError,
    WriteModelConfigurationManualRecoveryVerificationBusyError,
    format_write_model_configuration_manual_recovery_verification_report,
    validate_write_model_configuration_manual_recovery_verification,
    verify_write_model_configuration_manual_recovery_receipt,
)
from dayu.services.write_run_comparison import (
    compare_write_run_paths,
    persist_write_run_comparison,
)


_PRIMARY_SCENES = tuple(str(scene) for scene in PRIMARY_MODEL_WRITE_SCENES)
_AUDIT_SCENES = tuple(str(scene) for scene in AUDIT_WRITE_SCENES)


def _summary(
    *,
    primary_model: str,
    audit_model: str,
    cost: float,
) -> dict[str, Any]:
    return {
        "schema_version": "write_run_summary_v3",
        "ticker": "AAPL",
        "gate_status": "passed",
        "model_roles": {
            "primary": {
                "model_names": [primary_model],
                "scenes": [
                    {
                        "scene_name": scene_name,
                        "model_name": primary_model,
                        "temperature": 0.2,
                    }
                    for scene_name in _PRIMARY_SCENES
                ],
            },
            "audit": {
                "model_names": [audit_model],
                "scenes": [
                    {
                        "scene_name": scene_name,
                        "model_name": audit_model,
                        "temperature": 0.0,
                    }
                    for scene_name in _AUDIT_SCENES
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


def _write_config_root(
    tmp_path: Path,
    *,
    primary_model: str = "deepseek-primary",
    audit_model: str = "deepseek-audit",
) -> Path:
    config_root = tmp_path / "config"
    manifest_root = config_root / "prompts" / "manifests"
    manifest_root.mkdir(parents=True)
    (config_root / "run.json").write_text("{}\n", encoding="utf-8")
    (config_root / "llm_models.json").write_text(
        json.dumps(
            {
                "deepseek-primary": {"name": "deepseek-primary"},
                "deepseek-audit": {"name": "deepseek-audit"},
                "mimo-primary": {"name": "mimo-primary"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for scene_name in _PRIMARY_SCENES + _AUDIT_SCENES:
        role_primary = scene_name in _PRIMARY_SCENES
        current_model = primary_model if role_primary else audit_model
        allowed_names = ["deepseek-primary", "mimo-primary"] if role_primary else ["deepseek-audit"]
        (manifest_root / f"{scene_name}.json").write_text(
            json.dumps(
                {
                    "scene": scene_name,
                    "model": {
                        "default_name": current_model,
                        "allowed_names": allowed_names,
                        "temperature_profile": scene_name,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return config_root


def _write_run_config(
    tmp_path: Path,
    *,
    write_override: str = "",
) -> WriteRunConfig:
    return WriteRunConfig(
        ticker="AAPL",
        company="Apple",
        template_path=str(tmp_path / "template.md"),
        output_dir=str(tmp_path / "output"),
        write_max_retries=2,
        web_provider="auto",
        resume=True,
        write_model_override_name=write_override,
    )


def _preflight(
    *,
    primary_model: str = "deepseek-primary",
    audit_model: str = "deepseek-audit",
) -> WritePreflightResult:
    signature_scenes = tuple(
        [
            WritePreflightScene(
                scene_name=scene_name,
                model_role=WriteModelRole.PRIMARY,
                model_name=primary_model,
                temperature=0.2,
            )
            for scene_name in _PRIMARY_SCENES
        ]
        + [
            WritePreflightScene(
                scene_name=scene_name,
                model_role=WriteModelRole.AUDIT,
                model_name=audit_model,
                temperature=0.0,
            )
            for scene_name in _AUDIT_SCENES
        ]
    )
    return WritePreflightResult(
        ready=True,
        scenes=signature_scenes,
        signature_scenes=signature_scenes,
        required_environment_variables=(),
        issues=(),
    )


def test_cli_preflight_snapshot_export_is_configuration_read_only(
    tmp_path: Path,
) -> None:
    config_root = _write_config_root(tmp_path)
    watched_paths = [
        config_root / "run.json",
        config_root / "llm_models.json",
        *sorted((config_root / "prompts" / "manifests").glob("*.json")),
    ]
    original_bytes = {path: path.read_bytes() for path in watched_paths}

    class _PreflightOnlyService:
        def __init__(self) -> None:
            self.requests: list[Any] = []

        def preflight(self, request: Any) -> WritePreflightResult:
            self.requests.append(request)
            return _preflight()

    service = _PreflightOnlyService()
    snapshot_output = tmp_path / "routing-snapshot.json"

    exit_code = _run_write_preflight(
        write_config=_write_run_config(tmp_path),
        write_service=cast(Any, service),
        config_root=config_root,
        routing_snapshot_output=snapshot_output,
    )

    assert exit_code == 0
    assert len(service.requests) == 1
    _, snapshot = load_write_scene_model_routing_snapshot(snapshot_output)
    assert snapshot["status"] == "resolved"
    assert {path: path.read_bytes() for path in watched_paths} == original_bytes


def _approval(
    tmp_path: Path,
) -> tuple[Path, dict[str, Any]]:
    champion_dir = tmp_path / "champion"
    challenger_dir = tmp_path / "challenger"
    champion_dir.mkdir()
    challenger_dir.mkdir()
    champion_summary = champion_dir / "run_summary.json"
    challenger_summary = challenger_dir / "run_summary.json"
    champion_summary.write_text(
        json.dumps(
            _summary(
                primary_model="deepseek-primary",
                audit_model="deepseek-audit",
                cost=1.0,
            )
        ),
        encoding="utf-8",
    )
    challenger_summary.write_text(
        json.dumps(
            _summary(
                primary_model="mimo-primary",
                audit_model="deepseek-audit",
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
    promotion = build_write_model_challenger_promotion_proposal(comparison_path)
    promotion_path = persist_write_model_challenger_promotion_proposal(
        promotion,
        tmp_path / "promotion.json",
    )
    change_request = build_write_model_configuration_change_request(promotion_path)
    change_request_path = persist_write_model_configuration_change_request(
        change_request,
        tmp_path / "change-request.json",
    )
    approval_request = {
        "schema_version": ("write_model_challenger_configuration_change_approval_request_v1"),
        "approval_type": ("write_model_challenger_configuration_change"),
        "scope": ("one_future_write_scene_routing_change_subject_to_runtime_match"),
        "approved_by": "operator@example.com",
        "approval_reference": "OPS-2026-0726-01",
        "rollback_reference": "ROLLBACK-2026-0726-01",
        "approved_at": "2026-07-26T08:00:00Z",
        "expires_at": "2026-07-26T10:00:00Z",
        "configuration_change_request_fingerprint": change_request["request_fingerprint"],
        "promotion_proposal_fingerprint": change_request["source_promotion_proposal"]["proposal_fingerprint"],
        "acknowledgements": [
            "reviewed_exact_scene_model_transitions",
            ("promotion_proposal_and_change_request_must_remain_current"),
            ("runtime_configuration_must_match_observed_champion_before_application"),
            "rollback_plan_is_ready",
            "approval_is_single_use",
            ("issuance_and_verification_do_not_apply_configuration"),
            "issuance_and_verification_do_not_execute_models",
            "separate_application_command_required",
        ],
    }
    approval = build_write_model_configuration_change_approval(
        approval_request=approval_request,
        configuration_change_request_path=change_request_path,
        configuration_change_request=change_request,
        now=datetime(2026, 7, 26, 9, 0, tzinfo=UTC),
    )
    approval_path = persist_write_model_configuration_change_approval(
        approval,
        tmp_path / "approval.json",
    )
    return approval_path, approval


def _live_snapshot_builder(
    *,
    config_root: Path,
    tmp_path: Path,
) -> Any:
    def _build() -> dict[str, Any]:
        signature_scenes: list[WritePreflightScene] = []
        for scene_name in _PRIMARY_SCENES + _AUDIT_SCENES:
            manifest = json.loads(
                (config_root / "prompts" / "manifests" / f"{scene_name}.json").read_text(encoding="utf-8")
            )
            role = WriteModelRole.PRIMARY if scene_name in _PRIMARY_SCENES else WriteModelRole.AUDIT
            signature_scenes.append(
                WritePreflightScene(
                    scene_name=scene_name,
                    model_role=role,
                    model_name=manifest["model"]["default_name"],
                    temperature=(0.2 if role == WriteModelRole.PRIMARY else 0.0),
                )
            )
        preflight = WritePreflightResult(
            ready=True,
            scenes=tuple(signature_scenes),
            signature_scenes=tuple(signature_scenes),
            required_environment_variables=(),
            issues=(),
        )
        return build_write_scene_model_routing_snapshot(
            config_root=config_root,
            write_config=_write_run_config(tmp_path),
            preflight_result=preflight,
        )

    return _build


def _application_setup(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Any, dict[str, Any]]:
    config_root = _write_config_root(tmp_path)
    approval_path, _approval_payload = _approval(tmp_path)
    builder = _live_snapshot_builder(
        config_root=config_root,
        tmp_path=tmp_path,
    )
    snapshot = builder()
    snapshot_path = persist_write_scene_model_routing_snapshot(
        snapshot,
        tmp_path / "routing-snapshot.json",
    )
    plan = build_write_model_configuration_preapplication_plan(
        approval_path=approval_path,
        routing_snapshot_path=snapshot_path,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )
    plan_path = persist_write_model_configuration_preapplication_plan(
        plan,
        tmp_path / "preapplication-plan.json",
    )
    return (
        config_root,
        approval_path,
        plan_path,
        builder,
        snapshot,
    )


@pytest.mark.unit
def test_build_routing_snapshot_binds_resolved_scenes_and_sources(
    tmp_path: Path,
) -> None:
    config_root = _write_config_root(tmp_path)

    snapshot = build_write_scene_model_routing_snapshot(
        config_root=config_root,
        write_config=_write_run_config(tmp_path),
        preflight_result=_preflight(),
    )

    assert snapshot["schema_version"] == ("write_scene_model_routing_snapshot_v1")
    assert [scene["scene_name"] for scene in snapshot["scenes"]] == (list(_PRIMARY_SCENES + _AUDIT_SCENES))
    assert all(scene["route_source"] == "scene_manifest_default" for scene in snapshot["scenes"])
    assert [source["source_code"] for source in snapshot["configuration_sources"]] == ["model_catalog", "run_config"]
    assert snapshot["fallback_scenes"] == []
    validate_write_scene_model_routing_snapshot(snapshot)
    verification = verify_write_scene_model_routing_snapshot(snapshot)
    assert verification["status"] == "current"
    assert verification["configuration_change_applied"] is False
    assert verification["approval_consumed"] is False
    assert verification["model_execution_performed"] is False

    target = tmp_path / "routing-snapshot.json"
    persisted = persist_write_scene_model_routing_snapshot(
        snapshot,
        target,
    )
    original = persisted.read_bytes()
    assert (
        persist_write_scene_model_routing_snapshot(
            snapshot,
            target,
        )
        == target.resolve()
    )
    assert target.read_bytes() == original
    assert load_write_scene_model_routing_snapshot(target)[1] == (snapshot)


@pytest.mark.unit
def test_routing_snapshot_records_request_override_but_plan_blocks_it(
    tmp_path: Path,
) -> None:
    config_root = _write_config_root(tmp_path)
    approval_path, _approval_payload = _approval(tmp_path)
    snapshot = build_write_scene_model_routing_snapshot(
        config_root=config_root,
        write_config=_write_run_config(
            tmp_path,
            write_override="deepseek-primary",
        ),
        preflight_result=_preflight(),
    )
    snapshot_path = persist_write_scene_model_routing_snapshot(
        snapshot,
        tmp_path / "override-snapshot.json",
    )

    assert all(
        scene["route_source"] == "request_role_override" for scene in snapshot["scenes"] if scene["role"] == "primary"
    )
    with pytest.raises(
        WriteModelConfigurationPreapplicationBlockedError,
        match="request override",
    ):
        build_write_model_configuration_preapplication_plan(
            approval_path=approval_path,
            routing_snapshot_path=snapshot_path,
            now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
        )


@pytest.mark.unit
def test_preapplication_plan_preserves_exact_rollback_bytes_without_apply(
    tmp_path: Path,
) -> None:
    config_root = _write_config_root(tmp_path)
    approval_path, approval = _approval(tmp_path)
    snapshot = build_write_scene_model_routing_snapshot(
        config_root=config_root,
        write_config=_write_run_config(tmp_path),
        preflight_result=_preflight(),
    )
    snapshot_path = persist_write_scene_model_routing_snapshot(
        snapshot,
        tmp_path / "routing-snapshot.json",
    )
    manifest_paths = [
        Path(scene["manifest_source"]["path"]) for scene in snapshot["scenes"] if scene["role"] == "primary"
    ]
    before = {path: path.read_bytes() for path in manifest_paths}

    plan = build_write_model_configuration_preapplication_plan(
        approval_path=approval_path,
        routing_snapshot_path=snapshot_path,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )

    assert plan["status"] == ("ready_for_future_atomic_application_gate")
    assert len(plan["transitions"]) == len(_PRIMARY_SCENES)
    assert all(
        item["expected_current_model_name"] == "deepseek-primary"
        and item["proposed_model_name"] == "mimo-primary"
        and item["json_pointer"] == "/model/default_name"
        for item in plan["transitions"]
    )
    assert plan["rollback"]["rollback_reference"] == approval["rollback_reference"]
    assert plan["rollback"]["strategy"] == ("restore_exact_preapplication_manifest_bytes")
    assert {path: path.read_bytes() for path in manifest_paths} == before
    assert approval_path.is_file()
    assert not (tmp_path / "approval.json.consumed").exists()
    validate_write_model_configuration_preapplication_plan(plan)

    target = persist_write_model_configuration_preapplication_plan(
        plan,
        tmp_path / "preapplication-plan.json",
    )
    assert load_write_model_configuration_preapplication_plan(target)[1] == plan


@pytest.mark.unit
def test_preapplication_plan_blocks_when_current_champion_changed(
    tmp_path: Path,
) -> None:
    config_root = _write_config_root(
        tmp_path,
        primary_model="mimo-primary",
    )
    approval_path, _approval_payload = _approval(tmp_path)
    snapshot = build_write_scene_model_routing_snapshot(
        config_root=config_root,
        write_config=_write_run_config(tmp_path),
        preflight_result=_preflight(primary_model="mimo-primary"),
    )
    snapshot_path = persist_write_scene_model_routing_snapshot(
        snapshot,
        tmp_path / "routing-snapshot.json",
    )

    with pytest.raises(
        WriteModelConfigurationPreapplicationBlockedError,
        match="does not match observed Champion",
    ):
        build_write_model_configuration_preapplication_plan(
            approval_path=approval_path,
            routing_snapshot_path=snapshot_path,
            now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
        )


@pytest.mark.unit
def test_preapplication_plan_verification_uses_fresh_runtime_snapshot(
    tmp_path: Path,
) -> None:
    config_root = _write_config_root(tmp_path)
    approval_path, _approval_payload = _approval(tmp_path)
    snapshot = build_write_scene_model_routing_snapshot(
        config_root=config_root,
        write_config=_write_run_config(tmp_path),
        preflight_result=_preflight(),
    )
    snapshot_path = persist_write_scene_model_routing_snapshot(
        snapshot,
        tmp_path / "routing-snapshot.json",
    )
    plan = build_write_model_configuration_preapplication_plan(
        approval_path=approval_path,
        routing_snapshot_path=snapshot_path,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )

    verification = verify_write_model_configuration_preapplication_plan(
        plan,
        current_routing_snapshot=snapshot,
        expected_approval_path=approval_path,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )

    assert verification["status"] == "current"
    assert verification["action"] == ("separate_atomic_application_command_required")
    assert verification["eligible_for_future_single_use_application_attempt"] is True
    assert verification["configuration_change_applied"] is False
    assert verification["approval_consumed"] is False
    assert verification["model_execution_performed"] is False

    fresh_with_override = build_write_scene_model_routing_snapshot(
        config_root=config_root,
        write_config=_write_run_config(
            tmp_path,
            write_override="deepseek-primary",
        ),
        preflight_result=_preflight(),
    )
    changed = verify_write_model_configuration_preapplication_plan(
        plan,
        current_routing_snapshot=fresh_with_override,
        expected_approval_path=approval_path,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )
    assert changed["status"] == "current_runtime_routing_changed"
    assert changed["eligible_for_future_single_use_application_attempt"] is False


@pytest.mark.unit
def test_preapplication_plan_verification_detects_source_change(
    tmp_path: Path,
) -> None:
    config_root = _write_config_root(tmp_path)
    approval_path, _approval_payload = _approval(tmp_path)
    snapshot = build_write_scene_model_routing_snapshot(
        config_root=config_root,
        write_config=_write_run_config(tmp_path),
        preflight_result=_preflight(),
    )
    snapshot_path = persist_write_scene_model_routing_snapshot(
        snapshot,
        tmp_path / "routing-snapshot.json",
    )
    plan = build_write_model_configuration_preapplication_plan(
        approval_path=approval_path,
        routing_snapshot_path=snapshot_path,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )
    run_config_path = config_root / "run.json"
    run_config_path.write_text('{"changed": true}\n', encoding="utf-8")

    snapshot_verification = verify_write_scene_model_routing_snapshot(snapshot)
    verification = verify_write_model_configuration_preapplication_plan(
        plan,
        current_routing_snapshot=snapshot,
        expected_approval_path=approval_path,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )

    assert snapshot_verification["status"] == ("configuration_sources_changed")
    assert verification["status"] == "current_configuration_changed"
    assert verification["configuration_change_applied"] is False


@pytest.mark.unit
def test_preapplication_artifacts_are_strict_and_tamper_evident(
    tmp_path: Path,
) -> None:
    config_root = _write_config_root(tmp_path)
    approval_path, _approval_payload = _approval(tmp_path)
    snapshot = build_write_scene_model_routing_snapshot(
        config_root=config_root,
        write_config=_write_run_config(tmp_path),
        preflight_result=_preflight(),
    )
    snapshot_path = persist_write_scene_model_routing_snapshot(
        snapshot,
        tmp_path / "routing-snapshot.json",
    )
    plan = build_write_model_configuration_preapplication_plan(
        approval_path=approval_path,
        routing_snapshot_path=snapshot_path,
        now=datetime(2026, 7, 26, 9, 30, tzinfo=UTC),
    )

    tampered_snapshot = deepcopy(snapshot)
    tampered_snapshot["ticker"] = "MSFT"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_write_scene_model_routing_snapshot(tampered_snapshot)

    tampered_plan = deepcopy(plan)
    tampered_plan["transitions"][0]["proposed_model_name"] = "other-model"
    with pytest.raises(ValueError):
        validate_write_model_configuration_preapplication_plan(tampered_plan)


@pytest.mark.unit
def test_preapplication_plan_requires_unexpired_approval(
    tmp_path: Path,
) -> None:
    config_root = _write_config_root(tmp_path)
    approval_path, _approval_payload = _approval(tmp_path)
    snapshot = build_write_scene_model_routing_snapshot(
        config_root=config_root,
        write_config=_write_run_config(tmp_path),
        preflight_result=_preflight(),
    )
    snapshot_path = persist_write_scene_model_routing_snapshot(
        snapshot,
        tmp_path / "routing-snapshot.json",
    )

    with pytest.raises(
        WriteModelConfigurationPreapplicationBlockedError,
        match="approval is not current",
    ):
        build_write_model_configuration_preapplication_plan(
            approval_path=approval_path,
            routing_snapshot_path=snapshot_path,
            now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
        )


@pytest.mark.unit
def test_configuration_application_consumes_once_and_applies_exact_plan(
    tmp_path: Path,
) -> None:
    (
        config_root,
        approval_path,
        plan_path,
        snapshot_builder,
        _source_snapshot,
    ) = _application_setup(tmp_path)
    run_bytes = (config_root / "run.json").read_bytes()
    catalog_bytes = (config_root / "llm_models.json").read_bytes()
    audit_bytes = {
        scene_name: (config_root / "prompts" / "manifests" / f"{scene_name}.json").read_bytes()
        for scene_name in _AUDIT_SCENES
    }
    receipt_path = tmp_path / "application-receipt.json"

    receipt = apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
    )

    assert receipt["status"] == "applied"
    assert receipt["approval_consumed"] is True
    assert receipt["model_execution_performed"] is False
    assert len(receipt["operations"]) == len(_PRIMARY_SCENES)
    assert Path(receipt["approval_consumption"]["path"]).is_file()
    assert load_write_model_configuration_application_receipt(receipt_path)[1] == receipt
    for scene_name in _PRIMARY_SCENES:
        manifest = json.loads(
            (config_root / "prompts" / "manifests" / f"{scene_name}.json").read_text(encoding="utf-8")
        )
        assert manifest["model"]["default_name"] == "mimo-primary"
    assert (config_root / "run.json").read_bytes() == run_bytes
    assert (config_root / "llm_models.json").read_bytes() == catalog_bytes
    assert {
        scene_name: (config_root / "prompts" / "manifests" / f"{scene_name}.json").read_bytes()
        for scene_name in _AUDIT_SCENES
    } == audit_bytes
    verification = verify_write_model_configuration_application_receipt(
        receipt,
        current_routing_snapshot=snapshot_builder(),
    )
    assert verification["status"] == "current"
    assert verification["full_snapshot_match"] is True
    assert verification["changed_operation_routes_match"] is True
    assert verification["current_routing_matches_receipt"] is True
    assert verification["eligible_for_operator_rollback_plan"] is True
    assert verification["configuration_application_performed"] is False

    retry_path = tmp_path / "application-receipt-retry.json"
    retry = apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "other-workspace",
        receipt_output_path=retry_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
    )
    assert retry["receipt_fingerprint"] == receipt["receipt_fingerprint"]
    assert retry_path.is_file()


@pytest.mark.unit
def test_application_receipt_verification_detects_unapproved_scene_drift(
    tmp_path: Path,
) -> None:
    (
        config_root,
        approval_path,
        plan_path,
        snapshot_builder,
        _source_snapshot,
    ) = _application_setup(tmp_path)
    receipt = apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "application-receipt.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
    )
    audit_manifest_path = config_root / "prompts" / "manifests" / f"{_AUDIT_SCENES[0]}.json"
    audit_manifest = json.loads(audit_manifest_path.read_text(encoding="utf-8"))
    audit_manifest["model"]["allowed_names"].append("mimo-primary")
    audit_manifest_path.write_text(
        json.dumps(audit_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    verification = verify_write_model_configuration_application_receipt(
        receipt,
        current_routing_snapshot=snapshot_builder(),
    )

    assert verification["status"] == "routing_changed"
    assert verification["full_snapshot_match"] is False
    assert verification["changed_operation_routes_match"] is True
    assert verification["current_routing_matches_receipt"] is False
    assert verification["eligible_for_operator_rollback_plan"] is False
    assert verification["reason_codes"] == ["full_runtime_routing_snapshot_changed"]


@pytest.mark.unit
def test_cli_application_receipt_verification_is_configuration_read_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (
        config_root,
        approval_path,
        plan_path,
        snapshot_builder,
        _source_snapshot,
    ) = _application_setup(tmp_path)
    receipt_path = tmp_path / "application-receipt.json"
    apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
    )
    watched_paths = [
        config_root / "run.json",
        config_root / "llm_models.json",
        *sorted((config_root / "prompts" / "manifests").glob("*.json")),
    ]
    original_bytes = {path: path.read_bytes() for path in watched_paths}

    class _PreflightOnlyService:
        def preflight(self, _request: Any) -> WritePreflightResult:
            return _preflight(primary_model="mimo-primary")

    exit_code = _run_write_preflight(
        write_config=_write_run_config(tmp_path),
        write_service=cast(Any, _PreflightOnlyService()),
        config_root=config_root,
        application_receipt_input=receipt_path,
    )

    assert exit_code == 0
    assert "Status       : current" in capsys.readouterr().out
    assert {path: path.read_bytes() for path in watched_paths} == original_bytes


@pytest.mark.unit
def test_configuration_application_blocks_drift_before_consumption(
    tmp_path: Path,
) -> None:
    (
        config_root,
        approval_path,
        plan_path,
        snapshot_builder,
        _source_snapshot,
    ) = _application_setup(tmp_path)
    manifest_path = config_root / "prompts" / "manifests" / f"{_PRIMARY_SCENES[0]}.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    receipt_path = tmp_path / "application-receipt.json"

    with pytest.raises(
        WriteModelConfigurationApplicationBlockedError,
        match="not current",
    ):
        apply_write_model_configuration_preapplication_plan(
            plan_path=plan_path,
            approval_path=approval_path,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=receipt_path,
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
        )

    assert not receipt_path.exists()
    assert not list((approval_path.parent / ".dayu").rglob("*.consumed.json"))


@pytest.mark.unit
def test_configuration_application_failure_restores_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        approval_path,
        plan_path,
        snapshot_builder,
        source_snapshot,
    ) = _application_setup(tmp_path)
    manifest_paths = sorted((config_root / "prompts" / "manifests").glob("*.json"))
    original_bytes = {path: path.read_bytes() for path in manifest_paths}
    original_replace = configuration_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected replace failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        configuration_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )

    receipt = apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "rollback-receipt.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
    )

    assert receipt["status"] == "rolled_back"
    assert receipt["rollback_exact"] is True
    assert {path: path.read_bytes() for path in manifest_paths} == original_bytes
    assert snapshot_builder()["snapshot_fingerprint"] == (source_snapshot["snapshot_fingerprint"])
    verification = verify_write_model_configuration_application_receipt(
        receipt,
        current_routing_snapshot=snapshot_builder(),
    )
    assert verification["status"] == "current"
    assert verification["receipt_status"] == "rolled_back"
    assert verification["full_snapshot_match"] is True
    assert verification["eligible_for_operator_rollback_plan"] is False
    retry = apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "other-workspace",
        receipt_output_path=tmp_path / "rollback-retry.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
    )
    assert retry["receipt_fingerprint"] == receipt["receipt_fingerprint"]


@pytest.mark.unit
def test_configuration_application_preflight_failure_rolls_back(
    tmp_path: Path,
) -> None:
    (
        config_root,
        approval_path,
        plan_path,
        live_snapshot_builder,
        source_snapshot,
    ) = _application_setup(tmp_path)
    manifest_paths = sorted((config_root / "prompts" / "manifests").glob("*.json"))
    original_bytes = {path: path.read_bytes() for path in manifest_paths}
    snapshot_calls = 0

    def _fail_post_application_preflight() -> dict[str, Any]:
        nonlocal snapshot_calls
        snapshot_calls += 1
        if snapshot_calls == 2:
            raise RuntimeError("injected post-application preflight failure")
        return live_snapshot_builder()

    receipt = apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "rollback-receipt.json",
        snapshot_builder=_fail_post_application_preflight,
        now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
    )

    assert snapshot_calls == 3
    assert receipt["status"] == "rolled_back"
    assert receipt["failure"] == {
        "stage": "post_application_preflight",
        "error_type": "RuntimeError",
    }
    assert receipt["rollback_exact"] is True
    assert {path: path.read_bytes() for path in manifest_paths} == original_bytes
    assert live_snapshot_builder()["snapshot_fingerprint"] == (source_snapshot["snapshot_fingerprint"])


@pytest.mark.unit
def test_interrupted_configuration_application_recovers_before_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        approval_path,
        plan_path,
        snapshot_builder,
        source_snapshot,
    ) = _application_setup(tmp_path)
    manifest_paths = sorted((config_root / "prompts" / "manifests").glob("*.json"))
    original_bytes = {path: path.read_bytes() for path in manifest_paths}
    original_persist_receipts = configuration_application_module._persist_receipts

    def _interrupt_receipt_persistence(**_kwargs: Any) -> None:
        raise OSError("injected receipt interruption")

    monkeypatch.setattr(
        configuration_application_module,
        "_persist_receipts",
        _interrupt_receipt_persistence,
    )
    with pytest.raises(OSError, match="receipt interruption"):
        apply_write_model_configuration_preapplication_plan(
            plan_path=plan_path,
            approval_path=approval_path,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=tmp_path / "lost-receipt.json",
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
        )
    assert any(
        json.loads(path.read_text(encoding="utf-8"))["model"]["default_name"] == "mimo-primary"
        for path in manifest_paths
        if path.stem in _PRIMARY_SCENES
    )

    monkeypatch.setattr(
        configuration_application_module,
        "_persist_receipts",
        original_persist_receipts,
    )
    receipt = apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "other-workspace",
        receipt_output_path=tmp_path / "recovered-receipt.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
    )

    assert receipt["status"] == "rolled_back"
    assert receipt["failure"]["stage"] == ("interrupted_transaction_recovery")
    assert {path: path.read_bytes() for path in manifest_paths} == original_bytes
    assert snapshot_builder()["snapshot_fingerprint"] == (source_snapshot["snapshot_fingerprint"])


@pytest.mark.unit
def test_configuration_application_receipt_is_tamper_evident(
    tmp_path: Path,
) -> None:
    (
        _config_root,
        approval_path,
        plan_path,
        snapshot_builder,
        _source_snapshot,
    ) = _application_setup(tmp_path)
    receipt = apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "application-receipt.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
    )
    tampered = deepcopy(receipt)
    tampered["operations"][0]["applied_model_name"] = "other-model"

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_write_model_configuration_application_receipt(tampered)


@pytest.mark.unit
def test_configuration_receipt_semantics_fail_closed(
    tmp_path: Path,
) -> None:
    (
        _config_root,
        approval_path,
        plan_path,
        snapshot_builder,
        _source_snapshot,
    ) = _application_setup(tmp_path)
    receipt = apply_write_model_configuration_preapplication_plan(
        plan_path=plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "application-receipt.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
    )
    missing_post_snapshot = deepcopy(receipt)
    missing_post_snapshot["post_operation_routing_snapshot_fingerprint"] = None
    missing_post_snapshot.pop("receipt_fingerprint")
    missing_post_snapshot["receipt_fingerprint"] = configuration_application_module._fingerprint(missing_post_snapshot)

    with pytest.raises(
        ValueError,
        match="must contain post snapshot",
    ):
        validate_write_model_configuration_application_receipt(missing_post_snapshot)

    rollback_failed = deepcopy(receipt)
    rollback_failed["status"] = "rollback_failed"
    rollback_failed["action"] = "manual_recovery_required"
    rollback_failed["failure"] = {
        "stage": "manifest_application",
        "error_type": "OSError",
    }
    rollback_failed["rollback_exact"] = False
    rollback_failed["post_operation_routing_snapshot_fingerprint"] = None
    rollback_failed.pop("receipt_fingerprint")
    rollback_failed["receipt_fingerprint"] = configuration_application_module._fingerprint(rollback_failed)

    verification = verify_write_model_configuration_application_receipt(
        rollback_failed,
        current_routing_snapshot=snapshot_builder(),
    )

    assert verification["status"] == "manual_recovery_required"
    assert verification["current_routing_matches_receipt"] is False
    assert verification["eligible_for_operator_rollback_plan"] is False


def _operator_rollback_setup(
    tmp_path: Path,
) -> tuple[
    Path,
    Path,
    Path,
    Any,
    dict[str, Any],
    Path,
    dict[str, Any],
]:
    (
        config_root,
        approval_path,
        preapplication_plan_path,
        snapshot_builder,
        _source_snapshot,
    ) = _application_setup(tmp_path)
    receipt_path = tmp_path / "application-receipt.json"
    receipt = apply_write_model_configuration_preapplication_plan(
        plan_path=preapplication_plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
    )
    return (
        config_root,
        approval_path,
        preapplication_plan_path,
        snapshot_builder,
        receipt,
        receipt_path,
        snapshot_builder(),
    )


def _operator_rollback_approval_request(
    *,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    receipt_source = cast(
        Mapping[str, Any],
        plan["source_application_receipt"],
    )
    return {
        "schema_version": ("write_model_configuration_operator_rollback_approval_request_v1"),
        "approval_type": ("write_scene_model_routing_operator_rollback"),
        "scope": ("one_future_exact_operator_rollback_subject_to_runtime_match"),
        "approved_by": "rollback-operator@example.com",
        "approval_reference": "ROLLBACK-APPROVAL-2026-0726-01",
        "rollback_reason": ("Restore the verified preapplication routing after operator review."),
        "approved_at": "2026-07-26T09:40:00Z",
        "expires_at": "2026-07-26T11:40:00Z",
        "rollback_plan_fingerprint": plan["plan_fingerprint"],
        "application_receipt_fingerprint": receipt_source["content_fingerprint"],
        "acknowledgements": [
            "reviewed_exact_restore_operations",
            "current_runtime_matches_applied_receipt",
            "restore_exact_preapplication_bytes",
            "rollback_requires_separate_single_use_command",
            "approval_is_single_use",
            ("issuance_and_verification_do_not_modify_configuration"),
            "issuance_and_verification_do_not_execute_models",
        ],
    }


@pytest.mark.unit
def test_operator_rollback_plan_preserves_exact_preapplication_bytes(
    tmp_path: Path,
) -> None:
    (
        config_root,
        _approval_path,
        preapplication_plan_path,
        _snapshot_builder,
        receipt,
        receipt_path,
        current_snapshot,
    ) = _operator_rollback_setup(tmp_path)
    watched_paths = [
        config_root / "run.json",
        config_root / "llm_models.json",
        *sorted((config_root / "prompts" / "manifests").glob("*.json")),
    ]
    before = {path: path.read_bytes() for path in watched_paths}

    plan = build_write_model_configuration_operator_rollback_plan(
        application_receipt_path=receipt_path,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
    )

    assert plan["status"] == "ready_for_human_rollback_approval"
    assert plan["configuration_rollback_authorized"] is False
    assert plan["configuration_rollback_performed"] is False
    assert plan["approval_consumed"] is False
    assert plan["model_execution_performed"] is False
    assert (
        plan["expected_current_routing_snapshot_fingerprint"] == receipt["post_operation_routing_snapshot_fingerprint"]
    )
    assert plan["expected_restored_routing_snapshot_fingerprint"] == receipt["source_routing_snapshot_fingerprint"]
    _resolved, preapplication = load_write_model_configuration_preapplication_plan(preapplication_plan_path)
    rollback_entries = {(entry["role"], entry["scene_name"]): entry for entry in preapplication["rollback"]["entries"]}
    for operation in plan["operations"]:
        source = rollback_entries[(operation["role"], operation["scene_name"])]
        assert base64.b64decode(
            operation["restore_file_content_base64"],
            validate=True,
        ) == base64.b64decode(
            source["original_file_content_base64"],
            validate=True,
        )
        assert operation["restore_file_fingerprint"] == source["original_file_fingerprint"]
    validate_write_model_configuration_operator_rollback_plan(plan)
    plan_path = persist_write_model_configuration_operator_rollback_plan(
        plan,
        tmp_path / "operator-rollback-plan.json",
    )
    assert load_write_model_configuration_operator_rollback_plan(plan_path)[1] == plan
    verification = verify_write_model_configuration_operator_rollback_plan(
        plan,
        expected_application_receipt_path=receipt_path,
        current_routing_snapshot=current_snapshot,
    )
    assert verification["status"] == "current"
    assert verification["eligible_for_human_rollback_approval"] is True
    assert all(verification["identity"].values())
    assert {path: path.read_bytes() for path in watched_paths} == before


@pytest.mark.unit
def test_operator_rollback_plan_blocks_non_applied_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _config_root,
        approval_path,
        preapplication_plan_path,
        snapshot_builder,
        _source_snapshot,
    ) = _application_setup(tmp_path)
    original_replace = configuration_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected rollback-plan test failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        configuration_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )
    receipt_path = tmp_path / "rolled-back-receipt.json"
    receipt = apply_write_model_configuration_preapplication_plan(
        plan_path=preapplication_plan_path,
        approval_path=approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 9, 35, tzinfo=UTC),
    )
    assert receipt["status"] == "rolled_back"

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="not eligible",
    ):
        build_write_model_configuration_operator_rollback_plan(
            application_receipt_path=receipt_path,
            current_routing_snapshot=snapshot_builder(),
            now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
        )


@pytest.mark.unit
def test_operator_rollback_plan_verification_detects_full_snapshot_drift(
    tmp_path: Path,
) -> None:
    (
        config_root,
        _approval_path,
        _preapplication_plan_path,
        snapshot_builder,
        _receipt,
        receipt_path,
        current_snapshot,
    ) = _operator_rollback_setup(tmp_path)
    plan = build_write_model_configuration_operator_rollback_plan(
        application_receipt_path=receipt_path,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
    )
    audit_path = config_root / "prompts" / "manifests" / f"{_AUDIT_SCENES[0]}.json"
    audit_manifest = json.loads(audit_path.read_text(encoding="utf-8"))
    audit_manifest["model"]["allowed_names"].append("mimo-primary")
    audit_path.write_text(
        json.dumps(audit_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    verification = verify_write_model_configuration_operator_rollback_plan(
        plan,
        expected_application_receipt_path=receipt_path,
        current_routing_snapshot=snapshot_builder(),
    )

    assert verification["status"] == "routing_changed"
    assert verification["eligible_for_human_rollback_approval"] is False
    assert verification["identity"]["current_runtime_snapshot_match"] is False


@pytest.mark.unit
def test_operator_rollback_plan_is_tamper_evident(
    tmp_path: Path,
) -> None:
    (
        _config_root,
        _approval_path,
        _preapplication_plan_path,
        _snapshot_builder,
        _receipt,
        receipt_path,
        current_snapshot,
    ) = _operator_rollback_setup(tmp_path)
    plan = build_write_model_configuration_operator_rollback_plan(
        application_receipt_path=receipt_path,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
    )
    tampered = deepcopy(plan)
    tampered["operations"][0]["restore_model_name"] = "other-model"

    with pytest.raises(ValueError):
        validate_write_model_configuration_operator_rollback_plan(tampered)


@pytest.mark.unit
def test_operator_rollback_approval_is_short_lived_and_read_only(
    tmp_path: Path,
) -> None:
    (
        config_root,
        _approval_path,
        _preapplication_plan_path,
        _snapshot_builder,
        _receipt,
        receipt_path,
        current_snapshot,
    ) = _operator_rollback_setup(tmp_path)
    plan = build_write_model_configuration_operator_rollback_plan(
        application_receipt_path=receipt_path,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
    )
    plan_path = persist_write_model_configuration_operator_rollback_plan(
        plan,
        tmp_path / "operator-rollback-plan.json",
    )
    watched_paths = [
        config_root / "run.json",
        config_root / "llm_models.json",
        *sorted((config_root / "prompts" / "manifests").glob("*.json")),
    ]
    before = {path: path.read_bytes() for path in watched_paths}
    approval_request = _operator_rollback_approval_request(plan=plan)

    approval = build_write_model_configuration_operator_rollback_approval(
        approval_request=approval_request,
        rollback_plan_path=plan_path,
        rollback_plan=plan,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 9, 45, tzinfo=UTC),
    )

    assert approval["configuration_rollback_authorized"] is True
    assert approval["configuration_rollback_performed"] is False
    assert approval["approval_consumed"] is False
    assert approval["maximum_uses"] == 1
    approval_path = persist_write_model_configuration_operator_rollback_approval(
        approval,
        tmp_path / "operator-rollback-approval.json",
    )
    assert load_write_model_configuration_operator_rollback_approval(approval_path)[1] == approval
    verification = verify_write_model_configuration_operator_rollback_approval(
        approval,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    assert verification["status"] == "approved"
    assert verification["eligible_for_future_single_use_operator_rollback"] is True
    assert verification["configuration_rollback_performed"] is False
    assert verification["approval_consumed"] is False
    assert {path: path.read_bytes() for path in watched_paths} == before

    expired = verify_write_model_configuration_operator_rollback_approval(
        approval,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 11, 40, tzinfo=UTC),
    )
    assert expired["status"] == "expired"
    assert expired["eligible_for_future_single_use_operator_rollback"] is False


@pytest.mark.unit
def test_operator_rollback_approval_rejects_wrong_receipt_fingerprint(
    tmp_path: Path,
) -> None:
    (
        _config_root,
        _approval_path,
        _preapplication_plan_path,
        _snapshot_builder,
        _receipt,
        receipt_path,
        current_snapshot,
    ) = _operator_rollback_setup(tmp_path)
    plan = build_write_model_configuration_operator_rollback_plan(
        application_receipt_path=receipt_path,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
    )
    plan_path = persist_write_model_configuration_operator_rollback_plan(
        plan,
        tmp_path / "operator-rollback-plan.json",
    )
    approval_request = _operator_rollback_approval_request(plan=plan)
    approval_request["application_receipt_fingerprint"] = "sha256:" + ("0" * 64)

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="does not match",
    ):
        build_write_model_configuration_operator_rollback_approval(
            approval_request=approval_request,
            rollback_plan_path=plan_path,
            rollback_plan=plan,
            current_routing_snapshot=current_snapshot,
            now=datetime(2026, 7, 26, 9, 45, tzinfo=UTC),
        )


@pytest.mark.unit
def test_cli_operator_rollback_plan_and_approval_flow_is_read_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (
        config_root,
        _approval_path,
        _preapplication_plan_path,
        _snapshot_builder,
        _receipt,
        receipt_path,
        _current_snapshot,
    ) = _operator_rollback_setup(tmp_path)
    watched_paths = [
        config_root / "run.json",
        config_root / "llm_models.json",
        *sorted((config_root / "prompts" / "manifests").glob("*.json")),
    ]
    before = {path: path.read_bytes() for path in watched_paths}

    class _PreflightOnlyService:
        def preflight(self, _request: Any) -> WritePreflightResult:
            return _preflight(primary_model="mimo-primary")

    service = cast(Any, _PreflightOnlyService())
    rollback_plan_path = tmp_path / "operator-rollback-plan.json"
    assert (
        _run_write_preflight(
            write_config=_write_run_config(tmp_path),
            write_service=service,
            config_root=config_root,
            application_receipt_input=receipt_path,
            rollback_plan_output=rollback_plan_path,
        )
        == 0
    )
    _resolved, rollback_plan = load_write_model_configuration_operator_rollback_plan(rollback_plan_path)
    approval_request = _operator_rollback_approval_request(plan=rollback_plan)
    current_time = datetime.now(UTC)
    approval_request["approved_at"] = (current_time - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    approval_request["expires_at"] = (current_time + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    request_path = tmp_path / "rollback-approval-request.json"
    request_path.write_text(
        json.dumps(approval_request, indent=2) + "\n",
        encoding="utf-8",
    )
    rollback_approval_path = tmp_path / "operator-rollback-approval.json"
    assert (
        _run_write_preflight(
            write_config=_write_run_config(tmp_path),
            write_service=service,
            config_root=config_root,
            application_receipt_input=receipt_path,
            rollback_plan_input=rollback_plan_path,
            rollback_approval_request=request_path,
            rollback_approval_output=rollback_approval_path,
        )
        == 0
    )
    assert (
        _run_write_preflight(
            write_config=_write_run_config(tmp_path),
            write_service=service,
            config_root=config_root,
            application_receipt_input=receipt_path,
            rollback_plan_input=rollback_plan_path,
            rollback_approval_input=rollback_approval_path,
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "Status      : ready_for_human_rollback_approval" in output
    assert "Status      : approved_for_one_future_operator_rollback" in (output)
    assert "Status      : approved" in output
    assert {path: path.read_bytes() for path in watched_paths} == before


def _operator_rollback_application_setup(
    tmp_path: Path,
) -> tuple[
    Path,
    Path,
    Path,
    Any,
    dict[str, Any],
    dict[str, bytes],
    dict[str, bytes],
]:
    (
        config_root,
        _change_approval_path,
        _preapplication_plan_path,
        snapshot_builder,
        _application_receipt,
        application_receipt_path,
        current_snapshot,
    ) = _operator_rollback_setup(tmp_path)
    rollback_plan = build_write_model_configuration_operator_rollback_plan(
        application_receipt_path=application_receipt_path,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 9, 40, tzinfo=UTC),
    )
    rollback_plan_path = persist_write_model_configuration_operator_rollback_plan(
        rollback_plan,
        tmp_path / "operator-rollback-plan.json",
    )
    rollback_approval = build_write_model_configuration_operator_rollback_approval(
        approval_request=_operator_rollback_approval_request(plan=rollback_plan),
        rollback_plan_path=rollback_plan_path,
        rollback_plan=rollback_plan,
        current_routing_snapshot=current_snapshot,
        now=datetime(2026, 7, 26, 9, 45, tzinfo=UTC),
    )
    rollback_approval_path = persist_write_model_configuration_operator_rollback_approval(
        rollback_approval,
        tmp_path / "operator-rollback-approval.json",
    )
    applied_bytes = {
        str(operation["target_manifest_path"]): Path(str(operation["target_manifest_path"])).read_bytes()
        for operation in rollback_plan["operations"]
    }
    restore_bytes = {
        str(operation["target_manifest_path"]): base64.b64decode(
            operation["restore_file_content_base64"],
            validate=True,
        )
        for operation in rollback_plan["operations"]
    }
    return (
        config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        rollback_plan,
        applied_bytes,
        restore_bytes,
    )


def _recovery_failed_rollback_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    Path,
    Path,
    dict[str, Any],
    dict[str, Any],
    dict[str, bytes],
    dict[str, bytes],
]:
    (
        config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        rollback_plan,
        applied_bytes,
        restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    original_replace = rollback_application_module._replace_staged_file
    first_target = Path(str(rollback_plan["operations"][0]["target_manifest_path"]))
    replace_calls = 0

    def _corrupt_then_fail(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            first_target.write_bytes(b"unexpected external bytes")
            raise OSError("injected unrecoverable rollback failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        rollback_application_module,
        "_replace_staged_file",
        _corrupt_then_fail,
    )
    receipt_path = tmp_path / "recovery-failed.json"
    receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    assert receipt["status"] == "recovery_failed"
    return (
        config_root,
        receipt_path,
        receipt,
        rollback_plan,
        applied_bytes,
        restore_bytes,
    )


def _persist_manual_recovery_selection_request(
    *,
    path: Path,
    evidence: Mapping[str, Any],
    selected_state: str,
    selected_by: str = "selector@example.com",
    selected_at: str = "2026-07-26T10:10:00Z",
) -> Path:
    lineage = evidence.get("clearance_revocation_lineage")
    payload = {
        "schema_version": (
            "write_model_configuration_manual_recovery_selection_request_v2"
            if lineage is not None
            else "write_model_configuration_manual_recovery_selection_request_v1"
        ),
        "selection_type": ("write_scene_model_routing_manual_recovery_selection"),
        "scope": ("human_choice_of_one_exact_state_for_future_manual_recovery"),
        "selected_state": selected_state,
        "selected_by": selected_by,
        "selection_reference": "INC-2026-0726",
        "selection_reason": "Restore the explicitly reviewed state.",
        "selected_at": selected_at,
        "manual_recovery_evidence_fingerprint": evidence["evidence_fingerprint"],
        "source_transaction_id": evidence["transaction_id"],
        "acknowledgements": [
            "reviewed_recovery_failed_receipt_and_manual_recovery_evidence",
            "selected_state_is_an_explicit_human_decision",
            "selection_binds_one_exact_complete_configuration_state",
            "selection_does_not_authorize_or_modify_configuration",
            "separate_independent_short_lived_approval_required",
            "separate_single_use_recovery_command_required",
            "no_recovery_command_generated",
            "no_model_execution",
        ],
    }
    if lineage is not None:
        payload["clearance_revocation_lineage"] = deepcopy(lineage)
        payload["acknowledgements"].append("reviewed_exact_clearance_revocation_lineage")
    path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _persist_manual_recovery_approval_request(
    *,
    path: Path,
    plan: Mapping[str, Any],
    evidence: Mapping[str, Any],
    approved_by: str = "approver@example.com",
    approved_at: str = "2026-07-26T10:20:00Z",
    expires_at: str = "2026-07-26T11:20:00Z",
) -> Path:
    lineage = plan.get("clearance_revocation_lineage")
    payload = {
        "schema_version": (
            "write_model_configuration_manual_recovery_approval_request_v2"
            if lineage is not None
            else "write_model_configuration_manual_recovery_approval_request_v1"
        ),
        "approval_type": "write_scene_model_routing_manual_recovery",
        "scope": ("one_future_exact_manual_recovery_subject_to_byte_match"),
        "approved_by": approved_by,
        "approval_reference": "CAB-2026-0726",
        "approval_reason": "Independently approved exact recovery.",
        "approved_at": approved_at,
        "expires_at": expires_at,
        "manual_recovery_plan_fingerprint": plan["plan_fingerprint"],
        "manual_recovery_evidence_fingerprint": evidence["evidence_fingerprint"],
        "selected_state": plan["selected_state"],
        "acknowledgements": [
            "reviewed_manual_recovery_plan_and_exact_selected_bytes",
            "reviewed_current_observed_target_fingerprints",
            "approved_selected_state_matches_manual_selection",
            "approver_is_independent_from_state_selector",
            "approval_is_short_lived_and_single_use",
            "execution_requires_exact_current_byte_match",
            "failure_must_restore_exact_observed_starting_bytes",
            "issuance_does_not_modify_configuration",
            "issuance_does_not_execute_models",
        ],
    }
    if lineage is not None:
        payload["clearance_revocation_lineage"] = deepcopy(lineage)
        payload["acknowledgements"].append("approved_exact_clearance_revocation_lineage")
    path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _manual_recovery_application_setup(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selected_state: str = "applied",
) -> tuple[
    Path,
    Path,
    Path,
    Any,
    dict[str, Any],
    dict[str, bytes],
    dict[str, bytes],
    dict[Path, bytes],
]:
    (
        config_root,
        receipt_path,
        _receipt,
        _rollback_plan,
        applied_bytes,
        restore_bytes,
    ) = _recovery_failed_rollback_setup(tmp_path, monkeypatch)
    target_paths = [Path(path) for path in applied_bytes]
    starting_bytes = {target: target.read_bytes() for target in target_paths}
    evidence = build_write_model_configuration_manual_recovery_evidence(
        rollback_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
    )
    evidence_path = persist_write_model_configuration_manual_recovery_evidence(
        evidence,
        tmp_path / "manual-recovery-evidence.json",
    )
    selection_path = _persist_manual_recovery_selection_request(
        path=tmp_path / "manual-recovery-selection.json",
        evidence=evidence,
        selected_state=selected_state,
    )
    plan = build_write_model_configuration_manual_recovery_plan(
        manual_recovery_evidence_path=evidence_path,
        selection_request_path=selection_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 15, tzinfo=UTC),
    )
    plan_path = persist_write_model_configuration_manual_recovery_plan(
        plan,
        tmp_path / "manual-recovery-plan.json",
    )
    approval_request_path = _persist_manual_recovery_approval_request(
        path=tmp_path / "manual-recovery-approval-request.json",
        plan=plan,
        evidence=evidence,
    )
    approval = build_write_model_configuration_manual_recovery_approval(
        approval_request_path=approval_request_path,
        manual_recovery_plan_path=plan_path,
        config_root=config_root,
        now=datetime(2026, 7, 26, 10, 20, tzinfo=UTC),
    )
    approval_path = persist_write_model_configuration_manual_recovery_approval(
        approval,
        tmp_path / "manual-recovery-approval.json",
    )
    return (
        config_root,
        plan_path,
        approval_path,
        _live_snapshot_builder(
            config_root=config_root,
            tmp_path=tmp_path,
        ),
        plan,
        applied_bytes,
        restore_bytes,
        starting_bytes,
    )


def _recovered_manual_recovery_receipt(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Any, dict[str, Any], dict[str, bytes]]:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        plan,
        applied_bytes,
        _restore_bytes,
        _starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        selected_state="applied",
    )
    receipt_path = tmp_path / "manual-recovery-result.json"
    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
    )
    assert receipt["status"] == "recovered"
    return (
        config_root,
        receipt_path,
        snapshot_builder,
        plan,
        applied_bytes,
    )


def _persist_manual_recovery_clearance_request(
    *,
    path: Path,
    receipt: Mapping[str, Any],
    cleared_by: str = "clearer@example.com",
    cleared_at: str = "2026-07-26T10:30:00Z",
) -> Path:
    lineage = receipt.get("clearance_revocation_lineage")
    payload = {
        "schema_version": (
            "write_model_configuration_manual_recovery_clearance_request_v2"
            if lineage is not None
            else "write_model_configuration_manual_recovery_clearance_request_v1"
        ),
        "clearance_type": ("write_scene_model_routing_manual_recovery"),
        "scope": "close_one_verified_manual_recovery_incident",
        "ticker": receipt["ticker"],
        "transaction_id": receipt["transaction_id"],
        "manual_recovery_receipt_fingerprint": receipt["receipt_fingerprint"],
        "cleared_by": cleared_by,
        "clearance_reference": "CAB-CLOSE-2026-0726",
        "clearance_reason": ("Current routing and exact recovered bytes were reviewed."),
        "cleared_at": cleared_at,
        "acknowledgements": [
            "reviewed_manual_recovery_receipt_and_current_verification",
            "recovery_receipt_is_latest_internal_transaction",
            "current_verification_status_is_current",
            "clearance_closes_only_this_recovery_incident",
            "clearance_does_not_modify_configuration",
            "clearance_does_not_consume_approval",
            "clearance_does_not_execute_models",
            "normal_writes_still_require_normal_preflight",
        ],
    }
    if lineage is not None:
        payload["clearance_revocation_lineage"] = deepcopy(lineage)
        payload["acknowledgements"].append("reviewed_exact_clearance_revocation_lineage")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _persist_manual_recovery_clearance_revocation_request(
    *,
    path: Path,
    receipt: Mapping[str, Any],
    clearance: Mapping[str, Any],
    revoked_by: str = "incident-commander@example.com",
    revoked_at: str = "2026-07-26T10:40:00Z",
) -> Path:
    payload = {
        "schema_version": ("write_model_configuration_manual_recovery_clearance_revocation_request_v1"),
        "revocation_type": ("write_scene_model_routing_manual_recovery_clearance_revocation"),
        "scope": ("revoke_one_manual_recovery_clearance_and_block_normal_writes"),
        "ticker": receipt["ticker"],
        "transaction_id": receipt["transaction_id"],
        "manual_recovery_receipt_fingerprint": receipt["receipt_fingerprint"],
        "manual_recovery_clearance_fingerprint": clearance["clearance_fingerprint"],
        "revoked_by": revoked_by,
        "revocation_reference": "INC-REVOKE-2026-0726",
        "revocation_reason": ("The prior clearance requires immediate operator review."),
        "revoked_at": revoked_at,
        "acknowledgements": [
            "reviewed_latest_manual_recovery_receipt_and_clearance",
            "revocation_binds_the_exact_latest_clearance",
            "revocation_immediately_blocks_normal_writes",
            "revocation_cannot_be_removed_for_this_transaction",
            ("newer_manual_recovery_transaction_required_for_future_clearance"),
            "revocation_does_not_modify_configuration",
            "revocation_does_not_consume_approval",
            "revocation_does_not_execute_models",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _cleared_manual_recovery(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    Path,
    Path,
    Path,
    Any,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)[1]
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
    )
    clearance_path = tmp_path / "manual-recovery-clearance.json"
    clearance = issue_write_model_configuration_manual_recovery_clearance(
        clearance_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        clearance_output_path=clearance_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
    )
    return (
        config_root,
        receipt_path,
        clearance_path,
        snapshot_builder,
        plan,
        receipt,
        clearance,
    )


def _revoked_manual_recovery(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    Path,
    Path,
    Path,
    Path,
    Any,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    (
        config_root,
        receipt_path,
        clearance_path,
        snapshot_builder,
        plan,
        receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=receipt,
        clearance=clearance,
    )
    revocation_path = tmp_path / "clearance-revocation.json"
    revocation = revoke_write_model_configuration_manual_recovery_clearance(
        revocation_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        manual_recovery_clearance_path=clearance_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        revocation_output_path=revocation_path,
        now=datetime(2026, 7, 26, 10, 45, tzinfo=UTC),
    )
    return (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        snapshot_builder,
        plan,
        receipt,
        clearance,
        revocation,
    )


def _replace_payload_fingerprint(
    payload: dict[str, Any],
    *,
    fingerprint_field: str,
) -> None:
    unsigned = dict(payload)
    unsigned.pop(fingerprint_field, None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    payload[fingerprint_field] = "sha256:" + hashlib.sha256(canonical).hexdigest()


@pytest.mark.unit
def test_operator_rollback_application_restores_exact_bytes_once(
    tmp_path: Path,
) -> None:
    (
        config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        rollback_plan,
        _applied_bytes,
        restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    protected = [
        config_root / "run.json",
        config_root / "llm_models.json",
    ]
    protected_before = {path: path.read_bytes() for path in protected}
    receipt_path = tmp_path / "operator-rollback-receipt.json"

    receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )

    assert receipt["status"] == "rolled_back"
    assert receipt["configuration_rollback_completed"] is True
    assert receipt["approval_consumed"] is True
    assert receipt["model_execution_performed"] is False
    assert Path(receipt["approval_consumption"]["path"]).is_file()
    assert load_write_model_configuration_operator_rollback_receipt(receipt_path)[1] == receipt
    assert {path: Path(path).read_bytes() for path in restore_bytes} == restore_bytes
    assert snapshot_builder()["snapshot_fingerprint"] == rollback_plan["expected_restored_routing_snapshot_fingerprint"]
    assert {path: path.read_bytes() for path in protected} == protected_before
    verification = verify_write_model_configuration_operator_rollback_receipt(
        receipt,
        current_routing_snapshot=snapshot_builder(),
    )
    validate_write_model_configuration_operator_rollback_verification(verification)
    assert verification["status"] == "current"
    assert verification["receipt_status"] == "rolled_back"
    assert verification["full_snapshot_match"] is True
    assert verification["changed_operation_routes_match"] is True
    assert verification["current_routing_matches_receipt"] is True
    assert verification["eligible_for_new_operator_rollback_cycle"] is False
    assert verification["configuration_rollback_performed"] is False
    assert verification["approval_consumed"] is True
    assert verification["approval_consumed_by_verification"] is False

    copied_approval_path = tmp_path / "copied-evidence" / "operator-rollback-approval.json"
    copied_approval_path.parent.mkdir(parents=True)
    copied_approval_path.write_bytes(rollback_approval_path.read_bytes())
    retry = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=copied_approval_path,
        workspace_dir=tmp_path / "different-workspace",
        receipt_output_path=tmp_path / "rollback-retry.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
    )

    assert retry["receipt_fingerprint"] == receipt["receipt_fingerprint"]
    assert {path: Path(path).read_bytes() for path in restore_bytes} == restore_bytes


@pytest.mark.unit
def test_operator_rollback_receipt_verification_detects_unapproved_drift(
    tmp_path: Path,
) -> None:
    (
        config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        _rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "rollback-receipt.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    audit_manifest_path = config_root / "prompts" / "manifests" / f"{_AUDIT_SCENES[0]}.json"
    audit_manifest = json.loads(audit_manifest_path.read_text(encoding="utf-8"))
    audit_manifest["model"]["allowed_names"].append("mimo-primary")
    audit_manifest_path.write_text(
        json.dumps(audit_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    verification = verify_write_model_configuration_operator_rollback_receipt(
        receipt,
        current_routing_snapshot=snapshot_builder(),
    )

    assert verification["status"] == "routing_changed"
    assert verification["full_snapshot_match"] is False
    assert verification["changed_operation_routes_match"] is True
    assert verification["current_routing_matches_receipt"] is False
    assert verification["eligible_for_new_operator_rollback_cycle"] is False
    assert verification["reason_codes"] == ["full_runtime_routing_snapshot_changed"]


@pytest.mark.unit
def test_cli_operator_rollback_receipt_verification_is_read_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (
        config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        _rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    receipt_path = tmp_path / "rollback-receipt.json"
    apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    watched_paths = [
        config_root / "run.json",
        config_root / "llm_models.json",
        *sorted((config_root / "prompts" / "manifests").glob("*.json")),
    ]
    before = {path: path.read_bytes() for path in watched_paths}

    class _PreflightOnlyService:
        def preflight(self, _request: Any) -> WritePreflightResult:
            return _preflight()

    exit_code = _run_write_preflight(
        write_config=_write_run_config(tmp_path),
        write_service=cast(Any, _PreflightOnlyService()),
        config_root=config_root,
        rollback_receipt_input=receipt_path,
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "operator rollback verification" in output
    assert "Status        : current" in output
    assert "Configuration : unchanged by verification" in output
    assert {path: path.read_bytes() for path in watched_paths} == before


@pytest.mark.unit
def test_rolled_back_receipt_cannot_create_retry_plan(
    tmp_path: Path,
) -> None:
    (
        _config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        _rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    receipt_path = tmp_path / "rolled-back.json"
    apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="not eligible for a new rollback cycle",
    ):
        build_write_model_configuration_operator_rollback_retry_plan(
            rollback_receipt_path=receipt_path,
            current_routing_snapshot=snapshot_builder(),
            now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
        )


@pytest.mark.unit
def test_cli_exports_new_plan_from_current_rolled_forward_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (
        config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        first_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    original_replace = rollback_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected rollback failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        rollback_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )
    receipt_path = tmp_path / "rolled-forward.json"
    apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(
        rollback_application_module,
        "_replace_staged_file",
        original_replace,
    )
    watched_paths = [
        config_root / "run.json",
        config_root / "llm_models.json",
        *sorted((config_root / "prompts" / "manifests").glob("*.json")),
    ]
    before = {path: path.read_bytes() for path in watched_paths}
    retry_plan_path = tmp_path / "retry-plan.json"
    applied_models = {
        str(operation["role"]): str(operation["expected_current_model_name"]) for operation in first_plan["operations"]
    }

    class _PreflightOnlyService:
        def preflight(self, _request: Any) -> WritePreflightResult:
            return _preflight(
                primary_model=applied_models.get(
                    "primary",
                    "deepseek-primary",
                ),
                audit_model=applied_models.get(
                    "audit",
                    "deepseek-audit",
                ),
            )

    exit_code = _run_write_preflight(
        write_config=_write_run_config(tmp_path),
        write_service=cast(Any, _PreflightOnlyService()),
        config_root=config_root,
        rollback_receipt_input=receipt_path,
        rollback_plan_output=retry_plan_path,
    )

    assert exit_code == 0
    _resolved_path, retry_plan = load_write_model_configuration_operator_rollback_plan(retry_plan_path)
    assert retry_plan["plan_fingerprint"] != first_plan["plan_fingerprint"]
    assert retry_plan["operations"] == first_plan["operations"]
    output = capsys.readouterr().out
    assert "Status        : current" in output
    assert "operator rollback retry plan" in output
    assert {path: path.read_bytes() for path in watched_paths} == before


@pytest.mark.unit
def test_operator_rollback_application_blocks_drift_before_consumption(
    tmp_path: Path,
) -> None:
    (
        _config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    target = Path(str(rollback_plan["operations"][0]["target_manifest_path"]))
    target.write_bytes(target.read_bytes() + b"\n")

    with pytest.raises(
        WriteModelConfigurationRollbackApplicationBlockedError,
        match="not current",
    ):
        apply_write_model_configuration_operator_rollback(
            rollback_plan_path=rollback_plan_path,
            rollback_approval_path=rollback_approval_path,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=tmp_path / "receipt.json",
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
        )

    rollback_consumption_dir = (
        rollback_plan_path.parent / ".dayu" / "consumed-write-model-configuration-rollback-approvals"
    )
    assert not list(rollback_consumption_dir.glob("*.consumed.json"))


@pytest.mark.unit
def test_operator_rollback_rejects_artifacts_inside_configuration_root(
    tmp_path: Path,
) -> None:
    (
        config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        _rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)

    with pytest.raises(
        WriteModelConfigurationRollbackApplicationBlockedError,
        match="external receipt must be outside",
    ):
        apply_write_model_configuration_operator_rollback(
            rollback_plan_path=rollback_plan_path,
            rollback_approval_path=rollback_approval_path,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=config_root / "rollback-receipt.json",
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
        )

    rollback_consumption_dir = (
        rollback_plan_path.parent / ".dayu" / "consumed-write-model-configuration-rollback-approvals"
    )
    assert not list(rollback_consumption_dir.glob("*.consumed.json"))


@pytest.mark.unit
def test_operator_rollback_shares_configuration_transaction_lock(
    tmp_path: Path,
) -> None:
    (
        config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        _rollback_plan,
        applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    application_lock = create_write_model_configuration_transaction_lock(config_root)
    application_lock.acquire()
    try:
        with pytest.raises(
            WriteModelConfigurationRollbackApplicationBusyError,
            match="transaction holds the lock",
        ):
            apply_write_model_configuration_operator_rollback(
                rollback_plan_path=rollback_plan_path,
                rollback_approval_path=rollback_approval_path,
                workspace_dir=tmp_path / "workspace",
                receipt_output_path=tmp_path / "receipt.json",
                snapshot_builder=snapshot_builder,
                now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
            )
    finally:
        application_lock.release()

    assert {path: Path(path).read_bytes() for path in applied_bytes} == applied_bytes


@pytest.mark.unit
def test_operator_rollback_failure_restores_applied_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        rollback_plan,
        applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    original_replace = rollback_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected operator rollback failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        rollback_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )

    receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "rolled-forward.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )

    assert receipt["status"] == "rolled_forward"
    assert receipt["configuration_rollback_completed"] is False
    assert receipt["applied_state_recovery_exact"] is True
    assert receipt["failure"] == {
        "stage": "manifest_rollback",
        "error_type": "OSError",
    }
    assert {path: Path(path).read_bytes() for path in applied_bytes} == applied_bytes
    assert snapshot_builder()["snapshot_fingerprint"] == rollback_plan["expected_current_routing_snapshot_fingerprint"]
    verification = verify_write_model_configuration_operator_rollback_receipt(
        receipt,
        current_routing_snapshot=snapshot_builder(),
    )
    assert verification["status"] == "current"
    assert verification["receipt_status"] == "rolled_forward"
    assert verification["full_snapshot_match"] is True
    assert verification["changed_operation_routes_match"] is True
    assert verification["eligible_for_new_operator_rollback_cycle"] is True


@pytest.mark.unit
def test_rolled_forward_receipt_starts_new_approved_rollback_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _config_root,
        first_plan_path,
        first_approval_path,
        snapshot_builder,
        first_plan,
        applied_bytes,
        restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    original_replace = rollback_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected first-cycle rollback failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        rollback_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )
    first_receipt_path = tmp_path / "rolled-forward.json"
    first_receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=first_plan_path,
        rollback_approval_path=first_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=first_receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(
        rollback_application_module,
        "_replace_staged_file",
        original_replace,
    )

    retry_plan = build_write_model_configuration_operator_rollback_retry_plan(
        rollback_receipt_path=first_receipt_path,
        current_routing_snapshot=snapshot_builder(),
        now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
    )
    retry_plan_path = persist_write_model_configuration_operator_rollback_plan(
        retry_plan,
        tmp_path / "retry-plan.json",
    )

    assert first_receipt["status"] == "rolled_forward"
    assert retry_plan["plan_fingerprint"] != first_plan["plan_fingerprint"]
    assert retry_plan["operations"] == first_plan["operations"]
    assert {path: Path(path).read_bytes() for path in applied_bytes} == applied_bytes

    blocked_receipt_path = tmp_path / "old-approval-retry.json"
    with pytest.raises(
        WriteModelConfigurationRollbackApplicationBlockedError,
        match="different plan path",
    ):
        apply_write_model_configuration_operator_rollback(
            rollback_plan_path=retry_plan_path,
            rollback_approval_path=first_approval_path,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=blocked_receipt_path,
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 6, tzinfo=UTC),
        )
    assert not blocked_receipt_path.exists()
    assert {path: Path(path).read_bytes() for path in applied_bytes} == applied_bytes

    retry_approval_request = _operator_rollback_approval_request(plan=retry_plan)
    retry_approval_request.update(
        {
            "approval_reference": ("ROLLBACK-APPROVAL-2026-0726-RETRY-02"),
            "approved_at": "2026-07-26T10:06:30Z",
            "expires_at": "2026-07-26T12:00:00Z",
        }
    )
    retry_approval = build_write_model_configuration_operator_rollback_approval(
        approval_request=retry_approval_request,
        rollback_plan_path=retry_plan_path,
        rollback_plan=retry_plan,
        current_routing_snapshot=snapshot_builder(),
        now=datetime(2026, 7, 26, 10, 7, tzinfo=UTC),
    )
    retry_approval_path = persist_write_model_configuration_operator_rollback_approval(
        retry_approval,
        tmp_path / "retry-approval.json",
    )
    second_receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=retry_plan_path,
        rollback_approval_path=retry_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "rolled-back-retry.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 8, tzinfo=UTC),
    )

    assert second_receipt["status"] == "rolled_back"
    assert retry_approval["approval_fingerprint"] != first_receipt["source_rollback_approval"]["content_fingerprint"]
    assert second_receipt["approval_consumption"] != first_receipt["approval_consumption"]
    assert {path: Path(path).read_bytes() for path in restore_bytes} == restore_bytes
    second_verification = verify_write_model_configuration_operator_rollback_receipt(
        second_receipt,
        current_routing_snapshot=snapshot_builder(),
    )
    assert second_verification["status"] == "current"
    assert second_verification["eligible_for_new_operator_rollback_cycle"] is False
    first_verification = verify_write_model_configuration_operator_rollback_receipt(
        first_receipt,
        current_routing_snapshot=snapshot_builder(),
    )
    assert first_verification["status"] == "routing_changed"
    assert first_verification["eligible_for_new_operator_rollback_cycle"] is False


@pytest.mark.unit
def test_rollback_retry_plan_blocks_changed_source_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        _rollback_plan,
        applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    original_replace = rollback_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected rollback failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        rollback_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )
    receipt_path = tmp_path / "rolled-forward.json"
    receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    application_receipt_path = Path(str(receipt["source_application_receipt"]["path"]))
    application_receipt_path.write_bytes(application_receipt_path.read_bytes() + b"\n")

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="source application receipt file changed",
    ):
        build_write_model_configuration_operator_rollback_retry_plan(
            rollback_receipt_path=receipt_path,
            current_routing_snapshot=snapshot_builder(),
            now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
        )

    assert {path: Path(path).read_bytes() for path in applied_bytes} == applied_bytes


@pytest.mark.unit
def test_operator_rollback_preflight_failure_restores_applied_bytes(
    tmp_path: Path,
) -> None:
    (
        _config_root,
        rollback_plan_path,
        rollback_approval_path,
        live_snapshot_builder,
        rollback_plan,
        applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    calls = 0

    def _fail_post_rollback_preflight() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected post-rollback preflight failure")
        return live_snapshot_builder()

    receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "rolled-forward.json",
        snapshot_builder=_fail_post_rollback_preflight,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )

    assert receipt["status"] == "rolled_forward"
    assert receipt["failure"] == {
        "stage": "post_rollback_preflight",
        "error_type": "RuntimeError",
    }
    assert {path: Path(path).read_bytes() for path in applied_bytes} == applied_bytes
    assert (
        live_snapshot_builder()["snapshot_fingerprint"]
        == (rollback_plan["expected_current_routing_snapshot_fingerprint"])
    )


@pytest.mark.unit
def test_interrupted_operator_rollback_recovers_applied_state_on_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        rollback_plan,
        applied_bytes,
        restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    original_persist = rollback_application_module._persist_receipts

    def _interrupt_before_receipt(**_kwargs: Any) -> None:
        raise RuntimeError("injected receipt interruption")

    monkeypatch.setattr(
        rollback_application_module,
        "_persist_receipts",
        _interrupt_before_receipt,
    )
    with pytest.raises(RuntimeError, match="receipt interruption"):
        apply_write_model_configuration_operator_rollback(
            rollback_plan_path=rollback_plan_path,
            rollback_approval_path=rollback_approval_path,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=tmp_path / "missing-receipt.json",
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
        )
    assert {path: Path(path).read_bytes() for path in restore_bytes} == restore_bytes
    monkeypatch.setattr(
        rollback_application_module,
        "_persist_receipts",
        original_persist,
    )

    receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "other-workspace",
        receipt_output_path=tmp_path / "recovered-receipt.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
    )

    assert receipt["status"] == "rolled_forward"
    assert receipt["failure"] == {
        "stage": "interrupted_transaction_recovery",
        "error_type": "InterruptedOperatorRollback",
    }
    assert {path: Path(path).read_bytes() for path in applied_bytes} == applied_bytes
    assert snapshot_builder()["snapshot_fingerprint"] == rollback_plan["expected_current_routing_snapshot_fingerprint"]


@pytest.mark.unit
def test_operator_rollback_records_manual_recovery_when_bytes_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    last_valid_snapshot = snapshot_builder()
    original_replace = rollback_application_module._replace_staged_file
    first_target = Path(str(rollback_plan["operations"][0]["target_manifest_path"]))
    replace_calls = 0

    def _corrupt_then_fail(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            first_target.write_bytes(b"unexpected external bytes")
            raise OSError("injected unrecoverable rollback failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        rollback_application_module,
        "_replace_staged_file",
        _corrupt_then_fail,
    )

    receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "recovery-failed.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )

    assert receipt["status"] == "recovery_failed"
    assert receipt["action"] == "manual_recovery_required"
    assert receipt["post_operation_routing_snapshot_fingerprint"] is None
    assert receipt["applied_state_recovery_exact"] is False
    verification = verify_write_model_configuration_operator_rollback_receipt(
        receipt,
        current_routing_snapshot=last_valid_snapshot,
    )
    assert verification["status"] == "manual_recovery_required"
    assert verification["expected_routing_snapshot_fingerprint"] is None
    assert verification["full_snapshot_match"] is False
    assert verification["changed_operation_routes_match"] is False
    assert verification["current_routing_matches_receipt"] is False
    assert verification["eligible_for_new_operator_rollback_cycle"] is False
    assert verification["reason_codes"] == ["receipt_records_unrecovered_configuration_state"]


@pytest.mark.unit
def test_manual_recovery_evidence_preserves_both_exact_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        receipt,
        _rollback_plan,
        applied_bytes,
        restore_bytes,
    ) = _recovery_failed_rollback_setup(tmp_path, monkeypatch)
    target_paths = [Path(path) for path in applied_bytes]
    before = {path: path.read_bytes() for path in target_paths}

    evidence = build_write_model_configuration_manual_recovery_evidence(
        rollback_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
    )

    assert evidence["status"] == "manual_recovery_required"
    assert evidence["action"] == ("human_review_choose_one_exact_configuration_state")
    assert evidence["transaction_id"] == receipt["transaction_id"]
    assert evidence["write_ahead_intent"]["status"] == "valid"
    assert evidence["evidence_completeness"] == "complete"
    assert evidence["observed_configuration_state"] == "indeterminate"
    assert {operation["observed_state"] for operation in evidence["operations"]} == {"applied", "unexpected"}
    for operation in evidence["operations"]:
        target = str(operation["target_manifest_path"])
        assert operation["applied_candidate_available"] is True
        assert (
            base64.b64decode(
                operation["applied_file_content_base64"],
                validate=True,
            )
            == applied_bytes[target]
        )
        assert operation["preapplication_candidate_available"] is True
        assert (
            base64.b64decode(
                operation["preapplication_file_content_base64"],
                validate=True,
            )
            == restore_bytes[target]
        )
    assert evidence["configuration_mutation_performed"] is False
    assert evidence["approval_consumed"] is True
    assert evidence["approval_consumed_by_evidence_export"] is False
    assert evidence["model_execution_performed"] is False
    validate_write_model_configuration_manual_recovery_evidence(evidence)
    evidence_path = persist_write_model_configuration_manual_recovery_evidence(
        evidence,
        tmp_path / "manual-recovery-evidence.json",
    )
    assert json.loads(evidence_path.read_text(encoding="utf-8")) == (evidence)
    assert (
        persist_write_model_configuration_manual_recovery_evidence(
            evidence,
            evidence_path,
        )
        == evidence_path
    )
    assert {path: path.read_bytes() for path in target_paths} == before


@pytest.mark.unit
def test_manual_recovery_plan_and_independent_approval_bind_exact_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        _receipt,
        _rollback_plan,
        applied_bytes,
        _restore_bytes,
    ) = _recovery_failed_rollback_setup(tmp_path, monkeypatch)
    target_paths = [Path(path) for path in applied_bytes]
    before = {path: path.read_bytes() for path in target_paths}
    evidence = build_write_model_configuration_manual_recovery_evidence(
        rollback_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
    )
    evidence_path = persist_write_model_configuration_manual_recovery_evidence(
        evidence,
        tmp_path / "manual-recovery-evidence.json",
    )
    selection_path = _persist_manual_recovery_selection_request(
        path=tmp_path / "manual-recovery-selection.json",
        evidence=evidence,
        selected_state="applied",
    )

    plan = build_write_model_configuration_manual_recovery_plan(
        manual_recovery_evidence_path=evidence_path,
        selection_request_path=selection_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 15, tzinfo=UTC),
    )

    assert plan["selected_state"] == "applied"
    assert plan["selected_by"] == "selector@example.com"
    assert plan["source_evidence_completeness"] == "complete"
    for operation in plan["operations"]:
        target = str(operation["target_manifest_path"])
        assert (
            base64.b64decode(
                operation["selected_file_content_base64"],
                validate=True,
            )
            == applied_bytes[target]
        )
    validate_write_model_configuration_manual_recovery_plan(plan)
    plan_path = persist_write_model_configuration_manual_recovery_plan(
        plan,
        tmp_path / "manual-recovery-plan.json",
    )
    assert_write_model_configuration_manual_recovery_plan_current(
        plan=plan,
        config_root=config_root,
        now=datetime(2026, 7, 26, 10, 16, tzinfo=UTC),
    )
    approval_request_path = _persist_manual_recovery_approval_request(
        path=tmp_path / "manual-recovery-approval-request.json",
        plan=plan,
        evidence=evidence,
    )

    approval = build_write_model_configuration_manual_recovery_approval(
        approval_request_path=approval_request_path,
        manual_recovery_plan_path=plan_path,
        config_root=config_root,
        now=datetime(2026, 7, 26, 10, 20, tzinfo=UTC),
    )

    assert approval["approved_by"] == "approver@example.com"
    assert approval["maximum_uses"] == 1
    assert approval["configuration_recovery_authorized"] is True
    validate_write_model_configuration_manual_recovery_approval(approval)
    approval_path = persist_write_model_configuration_manual_recovery_approval(
        approval,
        tmp_path / "manual-recovery-approval.json",
    )
    assert approval_path.is_file()
    assert_write_model_configuration_manual_recovery_approval_current(
        approval=approval,
        manual_recovery_plan_path=plan_path,
        config_root=config_root,
        now=datetime(2026, 7, 26, 10, 21, tzinfo=UTC),
    )
    assert {path: path.read_bytes() for path in target_paths} == before


@pytest.mark.unit
def test_manual_recovery_applied_plan_requires_complete_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        receipt,
        _rollback_plan,
        _applied_bytes,
        restore_bytes,
    ) = _recovery_failed_rollback_setup(tmp_path, monkeypatch)
    consumption_path = Path(str(receipt["approval_consumption"]["path"]))
    consumption = json.loads(consumption_path.read_text(encoding="utf-8"))
    intent_path = Path(str(consumption["transaction_dir"])) / "intent.json"
    intent_path.unlink()
    evidence = build_write_model_configuration_manual_recovery_evidence(
        rollback_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
    )
    evidence_path = persist_write_model_configuration_manual_recovery_evidence(
        evidence,
        tmp_path / "partial-manual-recovery-evidence.json",
    )
    applied_selection_path = _persist_manual_recovery_selection_request(
        path=tmp_path / "applied-selection.json",
        evidence=evidence,
        selected_state="applied",
    )

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="applied recovery requires complete evidence",
    ):
        build_write_model_configuration_manual_recovery_plan(
            manual_recovery_evidence_path=evidence_path,
            selection_request_path=applied_selection_path,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 26, 10, 15, tzinfo=UTC),
        )

    preapplication_selection_path = _persist_manual_recovery_selection_request(
        path=tmp_path / "preapplication-selection.json",
        evidence=evidence,
        selected_state="preapplication",
    )
    plan = build_write_model_configuration_manual_recovery_plan(
        manual_recovery_evidence_path=evidence_path,
        selection_request_path=preapplication_selection_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 15, tzinfo=UTC),
    )
    assert plan["selected_state"] == "preapplication"
    for operation in plan["operations"]:
        target = str(operation["target_manifest_path"])
        assert (
            base64.b64decode(
                operation["selected_file_content_base64"],
                validate=True,
            )
            == restore_bytes[target]
        )


@pytest.mark.unit
def test_manual_recovery_approval_requires_independence_and_current_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        _receipt,
        _rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _recovery_failed_rollback_setup(tmp_path, monkeypatch)
    evidence = build_write_model_configuration_manual_recovery_evidence(
        rollback_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
    )
    evidence_path = persist_write_model_configuration_manual_recovery_evidence(
        evidence,
        tmp_path / "manual-recovery-evidence.json",
    )
    selection_path = _persist_manual_recovery_selection_request(
        path=tmp_path / "manual-recovery-selection.json",
        evidence=evidence,
        selected_state="preapplication",
    )
    plan = build_write_model_configuration_manual_recovery_plan(
        manual_recovery_evidence_path=evidence_path,
        selection_request_path=selection_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 15, tzinfo=UTC),
    )
    plan_path = persist_write_model_configuration_manual_recovery_plan(
        plan,
        tmp_path / "manual-recovery-plan.json",
    )
    same_person_request = _persist_manual_recovery_approval_request(
        path=tmp_path / "same-person-approval-request.json",
        plan=plan,
        evidence=evidence,
        approved_by="SELECTOR@example.com",
    )

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="approver must differ",
    ):
        build_write_model_configuration_manual_recovery_approval(
            approval_request_path=same_person_request,
            manual_recovery_plan_path=plan_path,
            config_root=config_root,
            now=datetime(2026, 7, 26, 10, 20, tzinfo=UTC),
        )

    target = Path(str(plan["operations"][0]["target_manifest_path"]))
    target.write_bytes(b"drift after plan")
    independent_request = _persist_manual_recovery_approval_request(
        path=tmp_path / "independent-approval-request.json",
        plan=plan,
        evidence=evidence,
    )
    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="no longer current",
    ):
        build_write_model_configuration_manual_recovery_approval(
            approval_request_path=independent_request,
            manual_recovery_plan_path=plan_path,
            config_root=config_root,
            now=datetime(2026, 7, 26, 10, 20, tzinfo=UTC),
        )


@pytest.mark.unit
def test_manual_recovery_application_restores_selected_bytes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        plan,
        applied_bytes,
        _restore_bytes,
        _starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        selected_state="applied",
    )
    receipt_path = tmp_path / "manual-recovery-result.json"

    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
    )

    assert receipt["status"] == "recovered"
    assert receipt["selected_state"] == "applied"
    assert receipt["approval_consumed"] is True
    assert receipt["configuration_recovery_completed"] is True
    assert receipt["model_execution_performed"] is False
    assert (
        receipt["post_operation_routing_snapshot_fingerprint"] == plan["expected_selected_routing_snapshot_fingerprint"]
    )
    for target, expected in applied_bytes.items():
        assert Path(target).read_bytes() == expected
    validate_write_model_configuration_manual_recovery_receipt(receipt)
    _loaded_path, loaded = load_write_model_configuration_manual_recovery_receipt(receipt_path)
    assert loaded == receipt

    second_receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "manual-recovery-reexport.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
    )
    assert second_receipt == receipt
    for target, expected in applied_bytes.items():
        assert Path(target).read_bytes() == expected


@pytest.mark.unit
def test_manual_recovery_application_failure_restores_starting_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
        _restore_bytes,
        starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_replace = manual_recovery_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected manual recovery failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )
    receipt_path = tmp_path / "manual-recovery-failed.json"

    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
    )

    assert receipt["status"] == "starting_state_restored"
    assert receipt["starting_state_recovery_performed"] is True
    assert receipt["starting_state_recovery_exact"] is True
    assert receipt["configuration_recovery_completed"] is False
    assert receipt["failure"]["stage"] == "manifest_manual_recovery"
    assert receipt["failure"]["recovery_failure_codes"] == []
    assert {path: path.read_bytes() for path in starting_bytes} == starting_bytes
    validate_write_model_configuration_manual_recovery_receipt(receipt)

    second = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "manual-recovery-reexport.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
    )
    assert second == receipt
    assert {path: path.read_bytes() for path in starting_bytes} == starting_bytes


@pytest.mark.unit
def test_manual_recovery_application_records_unrecoverable_byte_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        plan,
        _applied_bytes,
        _restore_bytes,
        _starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_replace = manual_recovery_application_module._replace_staged_file
    first_target = Path(str(plan["operations"][0]["target_manifest_path"]))
    replace_calls = 0

    def _corrupt_then_fail(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            first_target.write_bytes(b"external bytes after consumption")
            raise OSError("injected unrecoverable recovery failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_replace_staged_file",
        _corrupt_then_fail,
    )

    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "recovery-failed-again.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
    )

    assert receipt["status"] == "recovery_failed"
    assert receipt["starting_state_recovery_exact"] is False
    assert receipt["failure"]["recovery_failure_codes"]
    assert any(operation["final_state"] == "unexpected" for operation in receipt["operations"])
    validate_write_model_configuration_manual_recovery_receipt(receipt)


@pytest.mark.unit
def test_manual_recovery_verification_accepts_current_recovered_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    verification = verify_write_model_configuration_manual_recovery_receipt(
        manual_recovery_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        snapshot_builder=snapshot_builder,
    )

    assert verification["status"] == "current"
    assert verification["source_chain_valid"] is True
    assert verification["write_ahead_intent_valid"] is True
    assert verification["target_bytes_match_receipt"] is True
    assert verification["full_snapshot_checked"] is True
    assert verification["full_snapshot_match"] is True
    assert verification["eligible_for_normal_write_preflight"] is True
    assert verification["configuration_recovery_performed"] is False
    assert verification["approval_consumed_by_verification"] is False
    assert verification["model_execution_performed"] is False
    validate_write_model_configuration_manual_recovery_verification(verification)


@pytest.mark.unit
def test_manual_recovery_verification_detects_full_routing_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    (config_root / "run.json").write_text(
        '{"verification_drift": true}\n',
        encoding="utf-8",
    )

    verification = verify_write_model_configuration_manual_recovery_receipt(
        manual_recovery_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        snapshot_builder=snapshot_builder,
    )

    assert verification["status"] == "routing_changed"
    assert verification["target_bytes_match_receipt"] is True
    assert verification["full_snapshot_checked"] is True
    assert verification["full_snapshot_match"] is False
    assert verification["eligible_for_normal_write_preflight"] is False
    assert "full_runtime_routing_snapshot_changed" in verification["reason_codes"]


@pytest.mark.unit
def test_manual_recovery_verification_detects_target_drift_without_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        _snapshot_builder,
        plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    target = Path(str(plan["operations"][0]["target_manifest_path"]))
    target.write_bytes(b"external drift after manual recovery")
    snapshot_called = False

    def _unexpected_snapshot() -> Mapping[str, Any]:
        nonlocal snapshot_called
        snapshot_called = True
        raise AssertionError("target drift must stop before preflight")

    verification = verify_write_model_configuration_manual_recovery_receipt(
        manual_recovery_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        snapshot_builder=_unexpected_snapshot,
    )

    assert snapshot_called is False
    assert verification["status"] == "routing_changed"
    assert verification["target_bytes_match_receipt"] is False
    assert verification["full_snapshot_checked"] is False
    assert verification["full_snapshot_match"] is None


@pytest.mark.unit
def test_manual_recovery_verification_requires_new_evidence_after_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
        _restore_bytes,
        starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_replace = manual_recovery_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected manual recovery failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )
    receipt_path = tmp_path / "manual-recovery-restored.json"
    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
    )
    assert receipt["status"] == "starting_state_restored"

    def _unexpected_snapshot() -> Mapping[str, Any]:
        raise AssertionError("restored state must not run preflight")

    verification = verify_write_model_configuration_manual_recovery_receipt(
        manual_recovery_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        snapshot_builder=_unexpected_snapshot,
    )

    assert verification["status"] == "starting_state_current"
    assert verification["target_bytes_match_receipt"] is True
    assert verification["full_snapshot_checked"] is False
    assert verification["new_manual_recovery_evidence_required"] is True
    assert verification["manual_intervention_required"] is False
    assert {path: path.read_bytes() for path in starting_bytes} == starting_bytes


@pytest.mark.unit
def test_manual_recovery_verification_detects_restored_state_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        plan,
        _applied_bytes,
        _restore_bytes,
        _starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_replace = manual_recovery_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected manual recovery failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )
    receipt_path = tmp_path / "manual-recovery-restored.json"
    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
    )
    assert receipt["status"] == "starting_state_restored"
    target = Path(str(plan["operations"][0]["target_manifest_path"]))
    target.write_bytes(b"drift after starting-state restoration")

    verification = verify_write_model_configuration_manual_recovery_receipt(
        manual_recovery_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        snapshot_builder=None,
    )

    assert verification["status"] == "starting_state_changed"
    assert verification["target_bytes_match_receipt"] is False
    assert verification["manual_intervention_required"] is True


@pytest.mark.unit
def test_manual_recovery_verification_preserves_recovery_failed_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        plan,
        _applied_bytes,
        _restore_bytes,
        _starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_replace = manual_recovery_application_module._replace_staged_file
    first_target = Path(str(plan["operations"][0]["target_manifest_path"]))
    replace_calls = 0

    def _corrupt_then_fail(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            first_target.write_bytes(b"external bytes after consumption")
            raise OSError("injected unrecoverable recovery failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_replace_staged_file",
        _corrupt_then_fail,
    )
    receipt_path = tmp_path / "manual-recovery-failed-again.json"
    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
    )
    assert receipt["status"] == "recovery_failed"

    verification = verify_write_model_configuration_manual_recovery_receipt(
        manual_recovery_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        snapshot_builder=None,
    )

    assert verification["status"] == "manual_recovery_required"
    assert verification["full_snapshot_checked"] is False
    assert verification["eligible_for_normal_write_preflight"] is False
    assert verification["manual_intervention_required"] is True
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert gate["status"] == "manual_recovery_required"
    assert gate["latest_receipt_status"] == "recovery_failed"
    assert gate["normal_write_allowed"] is False
    assert gate["reason_codes"] == ["manual_intervention_required"]


@pytest.mark.unit
def test_manual_recovery_verification_rejects_source_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    selection_path = Path(str(plan["source_selection_request"]["path"]))
    selection_path.write_text(
        "{}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryVerificationBlockedError,
        match="file changed",
    ):
        verify_write_model_configuration_manual_recovery_receipt(
            manual_recovery_receipt_path=receipt_path,
            config_root=config_root,
            expected_ticker="AAPL",
            snapshot_builder=snapshot_builder,
        )


@pytest.mark.unit
def test_manual_recovery_verification_respects_transaction_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    transaction_lock = create_write_model_configuration_transaction_lock(config_root)
    transaction_lock.acquire()
    try:
        with pytest.raises(
            WriteModelConfigurationManualRecoveryVerificationBusyError,
            match="holds the lock",
        ):
            verify_write_model_configuration_manual_recovery_receipt(
                manual_recovery_receipt_path=receipt_path,
                config_root=config_root,
                expected_ticker="AAPL",
                snapshot_builder=snapshot_builder,
            )
    finally:
        transaction_lock.release()


@pytest.mark.unit
def test_manual_recovery_gate_allows_when_no_incident_exists(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()

    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
    )

    assert gate["schema_version"] == ("write_model_configuration_manual_recovery_gate_v4")
    assert gate["assessed_at"] == "2026-07-29T09:00:00Z"
    assert gate["ticker"] == "AAPL"
    assert gate["status"] == "not_required"
    assert gate["normal_write_allowed"] is True
    assert gate["clearance_present"] is False
    assert gate["clearance_revoked"] is False
    assert gate["configuration_mutation_performed"] is False
    assert gate["approval_consumed"] is False
    assert gate["model_execution_performed"] is False
    assert gate["clearance_revocation_lineage"] is None
    assert gate["clearance_revocation_lineage_status"] == "not_applicable"
    assert gate["gate_fingerprint"].startswith("sha256:")
    validate_write_model_configuration_manual_recovery_gate(gate)
    report = format_write_model_configuration_manual_recovery_gate_report(gate)
    assert any(gate["gate_fingerprint"] in line for line in report)

    tampered = deepcopy(gate)
    tampered["assessed_at"] = "2026-07-29T09:00:01Z"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_write_model_configuration_manual_recovery_gate(tampered)


@pytest.mark.unit
def test_manual_recovery_gate_exports_immutably_outside_configuration(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 5, tzinfo=UTC),
    )
    output_path = tmp_path / "audit" / "manual-recovery-gate.json"

    persisted_path = persist_write_model_configuration_manual_recovery_gate(
        gate,
        output_path,
        config_root=config_root,
    )

    assert persisted_path == output_path.resolve()
    assert json.loads(output_path.read_text(encoding="utf-8")) == gate
    assert (
        persist_write_model_configuration_manual_recovery_gate(
            gate,
            output_path,
            config_root=config_root,
        )
        == persisted_path
    )
    changed_gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 6, tzinfo=UTC),
    )
    with pytest.raises(FileExistsError, match="different content"):
        persist_write_model_configuration_manual_recovery_gate(
            changed_gate,
            output_path,
            config_root=config_root,
        )
    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="outside the configuration root",
    ):
        persist_write_model_configuration_manual_recovery_gate(
            gate,
            config_root / "manual-recovery-gate.json",
            config_root=config_root,
        )


@pytest.mark.unit
def test_manual_recovery_audit_timeline_reports_empty_history(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"

    timeline = (
        build_write_model_configuration_manual_recovery_audit_timeline(
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 10, tzinfo=UTC),
        )
    )

    assert timeline["schema_version"] == (
        "write_model_configuration_manual_recovery_audit_timeline_v1"
    )
    assert timeline["generated_at"] == "2026-07-29T09:10:00Z"
    assert timeline["ticker"] == "AAPL"
    assert timeline["current_gate"]["status"] == "not_required"
    assert timeline["events"] == []
    assert timeline["receipt_count"] == 0
    assert timeline["clearance_count"] == 0
    assert timeline["revocation_count"] == 0
    assert timeline["incomplete_transaction_ids"] == []
    assert timeline["history_complete"] is True
    assert timeline["normal_write_authorization_granted"] is False
    assert timeline["configuration_mutation_performed"] is False
    assert timeline["approval_consumed"] is False
    assert timeline["model_execution_performed"] is False
    validate_write_model_configuration_manual_recovery_audit_timeline(
        timeline
    )
    report = (
        format_write_model_configuration_manual_recovery_audit_timeline_report(
            timeline
        )
    )
    assert any(timeline["timeline_fingerprint"] in line for line in report)


@pytest.mark.unit
def test_manual_recovery_audit_timeline_binds_revoked_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        _receipt_path,
        _clearance_path,
        _revocation_path,
        _snapshot_builder,
        _plan,
        receipt,
        clearance,
        revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    timeline = (
        build_write_model_configuration_manual_recovery_audit_timeline(
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 20, tzinfo=UTC),
        )
    )

    assert timeline["current_gate"]["status"] == "clearance_revoked"
    assert [
        event["event_type"] for event in timeline["events"]
    ] == [
        "manual_recovery_receipt",
        "manual_recovery_clearance",
        "manual_recovery_clearance_revocation",
    ]
    assert [event["sequence"] for event in timeline["events"]] == [
        1,
        2,
        3,
    ]
    assert timeline["receipt_count"] == 1
    assert timeline["clearance_count"] == 1
    assert timeline["revocation_count"] == 1
    assert timeline["events"][0]["artifact"] == receipt
    assert timeline["events"][1]["artifact"] == clearance
    assert timeline["events"][2]["artifact"] == revocation
    validate_write_model_configuration_manual_recovery_audit_timeline(
        timeline
    )

    tampered = deepcopy(timeline)
    tampered["events"][0]["artifact_file_fingerprint"] = (
        "sha256:" + ("0" * 64)
    )
    _replace_payload_fingerprint(
        tampered,
        fingerprint_field="timeline_fingerprint",
    )
    with pytest.raises(
        ValueError,
        match="clearance receipt link is invalid",
    ):
        validate_write_model_configuration_manual_recovery_audit_timeline(
            tampered
        )


@pytest.mark.unit
def test_manual_recovery_audit_timeline_exports_immutably(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"
    timeline = (
        build_write_model_configuration_manual_recovery_audit_timeline(
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 25, tzinfo=UTC),
        )
    )
    output_path = tmp_path / "audit" / "manual-recovery-timeline.json"

    persisted_path = (
        persist_write_model_configuration_manual_recovery_audit_timeline(
            timeline,
            output_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
        )
    )

    assert persisted_path == output_path.resolve()
    assert json.loads(output_path.read_text(encoding="utf-8")) == timeline
    assert (
        persist_write_model_configuration_manual_recovery_audit_timeline(
            timeline,
            output_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
        )
        == persisted_path
    )
    for unsafe_path in (
        config_root / "timeline.json",
        workspace_dir / ".dayu" / "timeline.json",
    ):
        with pytest.raises(
            WriteModelConfigurationManualRecoveryClearanceBlockedError,
            match="outside configuration and authoritative evidence roots",
        ):
            persist_write_model_configuration_manual_recovery_audit_timeline(
                timeline,
                unsafe_path,
                workspace_dir=workspace_dir,
                config_root=config_root,
            )


@pytest.mark.unit
def test_manual_recovery_audit_timeline_reports_incomplete_transaction(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"
    transaction_root = (
        manual_recovery_clearance_module.write_model_configuration_manual_recovery_transaction_root(
            workspace_dir=workspace_dir
        )
    )
    (transaction_root / "tx-incomplete").mkdir(parents=True)

    timeline = (
        build_write_model_configuration_manual_recovery_audit_timeline(
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 30, tzinfo=UTC),
        )
    )

    assert timeline["current_gate"]["status"] == (
        "manual_recovery_required"
    )
    assert timeline["current_gate"]["latest_receipt_status"] == "incomplete"
    assert timeline["incomplete_transaction_ids"] == ["tx-incomplete"]
    assert timeline["history_complete"] is False
    assert timeline["events"] == []
    validate_write_model_configuration_manual_recovery_audit_timeline(
        timeline
    )


@pytest.mark.unit
def test_manual_recovery_audit_timeline_rejects_orphan_clearance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        _receipt_path,
        _clearance_path,
        _snapshot_builder,
        _plan,
        _receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    internal_receipt_path = Path(
        clearance["source_manual_recovery_receipt"]["path"]
    )
    internal_receipt_path.unlink()

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="orphan clearance",
    ):
        build_write_model_configuration_manual_recovery_audit_timeline(
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 35, tzinfo=UTC),
        )


@pytest.mark.unit
def test_manual_recovery_audit_timeline_detects_internal_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"
    original_scan = (
        manual_recovery_clearance_module._internal_manual_recovery_audit_state
    )
    call_count = 0

    def _changing_scan(
        *,
        workspace_dir: str | Path,
    ) -> dict[str, Any]:
        nonlocal call_count
        state = original_scan(workspace_dir=workspace_dir)
        call_count += 1
        if call_count == 1:
            transaction_root = (
                manual_recovery_clearance_module.write_model_configuration_manual_recovery_transaction_root(
                    workspace_dir=workspace_dir
                )
            )
            (transaction_root / "tx-racing").mkdir(parents=True)
        return state

    monkeypatch.setattr(
        manual_recovery_clearance_module,
        "_internal_manual_recovery_audit_state",
        _changing_scan,
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryAuditTimelineChangedError,
        match="changed during audit",
    ):
        build_write_model_configuration_manual_recovery_audit_timeline(
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 40, tzinfo=UTC),
        )


@pytest.mark.unit
def test_manual_recovery_gate_verification_accepts_current_snapshot_and_exports_receipt(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"
    source_gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
    )
    source_path = tmp_path / "audit" / "manual-recovery-gate.json"
    persist_write_model_configuration_manual_recovery_gate(
        source_gate,
        source_path,
        config_root=config_root,
    )

    verification = (
        verify_write_model_configuration_manual_recovery_gate_snapshot(
            gate_snapshot_path=source_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 5, tzinfo=UTC),
        )
    )

    assert verification["schema_version"] == (
        "write_model_configuration_manual_recovery_gate_verification_v1"
    )
    assert verification["verified_at"] == "2026-07-29T09:05:00Z"
    assert verification["status"] == "current"
    assert verification["action"] == (
        "historical_gate_matches_current_state"
    )
    assert verification["source_gate"] == source_gate
    assert verification["current_gate"]["assessed_at"] == (
        "2026-07-29T09:05:00Z"
    )
    assert verification["source_state_fingerprint"] == (
        verification["current_state_fingerprint"]
    )
    assert verification["state_matches"] is True
    assert verification["changed_fields"] == []
    assert verification["reason_codes"] == [
        "source_gate_state_matches_current_assessment"
    ]
    assert verification["normal_write_authorization_granted"] is False
    assert verification["configuration_mutation_performed"] is False
    assert verification["approval_consumed"] is False
    assert verification["model_execution_performed"] is False
    expected_file_fingerprint = (
        "sha256:"
        + hashlib.sha256(source_path.read_bytes()).hexdigest()
    )
    assert verification["source_gate_file_fingerprint"] == (
        expected_file_fingerprint
    )
    validate_write_model_configuration_manual_recovery_gate_verification(
        verification
    )
    report = (
        format_write_model_configuration_manual_recovery_gate_verification_report(
            verification
        )
    )
    assert any("State matches : True" in line for line in report)
    assert any("not granted by verification" in line for line in report)

    tampered = deepcopy(verification)
    tampered["current_gate"]["assessed_at"] = "2026-07-29T09:05:01Z"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_write_model_configuration_manual_recovery_gate_verification(
            tampered
        )

    output_path = (
        tmp_path / "audit" / "manual-recovery-gate-verification.json"
    )
    persisted_path = (
        persist_write_model_configuration_manual_recovery_gate_verification(
            verification,
            output_path,
            config_root=config_root,
        )
    )
    assert persisted_path == output_path.resolve()
    assert json.loads(output_path.read_text(encoding="utf-8")) == verification
    assert (
        persist_write_model_configuration_manual_recovery_gate_verification(
            verification,
            output_path,
            config_root=config_root,
        )
        == persisted_path
    )
    changed_verification = (
        verify_write_model_configuration_manual_recovery_gate_snapshot(
            gate_snapshot_path=source_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 6, tzinfo=UTC),
        )
    )
    with pytest.raises(FileExistsError, match="different content"):
        persist_write_model_configuration_manual_recovery_gate_verification(
            changed_verification,
            output_path,
            config_root=config_root,
        )
    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="outside the configuration root",
    ):
        persist_write_model_configuration_manual_recovery_gate_verification(
            verification,
            config_root / "gate-verification.json",
            config_root=config_root,
        )


@pytest.mark.unit
def test_manual_recovery_gate_verification_reports_stale_semantic_state(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"
    source_gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
    )
    source_path = tmp_path / "audit" / "manual-recovery-gate.json"
    persist_write_model_configuration_manual_recovery_gate(
        source_gate,
        source_path,
        config_root=config_root,
    )
    transaction_dir = (
        workspace_dir
        / ".dayu"
        / "write-model-configuration-manual-recoveries"
        / "transactions"
        / "interrupted-transaction"
    )
    transaction_dir.mkdir(parents=True)
    (transaction_dir / "intent.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    verification = (
        verify_write_model_configuration_manual_recovery_gate_snapshot(
            gate_snapshot_path=source_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 5, tzinfo=UTC),
        )
    )

    assert verification["status"] == "stale"
    assert verification["action"] == "use_current_gate_assessment"
    assert verification["state_matches"] is False
    assert verification["changed_fields"] == [
        "action",
        "latest_receipt_status",
        "latest_transaction_id",
        "normal_write_allowed",
        "reason_codes",
        "status",
    ]
    assert verification["source_gate"]["normal_write_allowed"] is True
    assert verification["current_gate"]["normal_write_allowed"] is False
    assert verification["current_gate"]["status"] == (
        "manual_recovery_required"
    )
    assert verification["reason_codes"] == [
        "source_gate_state_changed"
    ]
    assert verification["source_state_fingerprint"] != (
        verification["current_state_fingerprint"]
    )
    validate_write_model_configuration_manual_recovery_gate_verification(
        verification
    )


@pytest.mark.unit
def test_manual_recovery_gate_verification_rejects_tampered_or_internal_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
    )
    source_path = tmp_path / "audit" / "manual-recovery-gate.json"
    persist_write_model_configuration_manual_recovery_gate(
        gate,
        source_path,
        config_root=config_root,
    )
    tampered = deepcopy(gate)
    tampered["assessed_at"] = "2026-07-29T09:00:01Z"
    source_path.write_text(
        json.dumps(tampered),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        verify_write_model_configuration_manual_recovery_gate_snapshot(
            gate_snapshot_path=source_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 5, tzinfo=UTC),
        )

    internal_path = config_root / "manual-recovery-gate.json"
    internal_path.write_text(
        json.dumps(gate),
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="outside the configuration root",
    ):
        verify_write_model_configuration_manual_recovery_gate_snapshot(
            gate_snapshot_path=internal_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
        )

    source_path.write_text(
        json.dumps(gate),
        encoding="utf-8",
    )
    original_is_symlink = Path.is_symlink

    def _is_symlink(path: Path) -> bool:
        if path.absolute() == source_path.absolute():
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", _is_symlink)
    with pytest.raises(FileNotFoundError, match="must not be a symlink"):
        verify_write_model_configuration_manual_recovery_gate_snapshot(
            gate_snapshot_path=source_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
        )


@pytest.mark.unit
def test_manual_recovery_gate_verification_detects_source_change_during_assessment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"
    source_gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
    )
    source_path = tmp_path / "audit" / "manual-recovery-gate.json"
    persist_write_model_configuration_manual_recovery_gate(
        source_gate,
        source_path,
        config_root=config_root,
    )
    original_assess = (
        manual_recovery_clearance_module
        .assess_write_model_configuration_manual_recovery_gate
    )

    def _assess_and_change_source(**kwargs: Any) -> dict[str, Any]:
        current_gate = original_assess(**kwargs)
        source_path.write_bytes(source_path.read_bytes() + b" ")
        return current_gate

    monkeypatch.setattr(
        manual_recovery_clearance_module,
        "assess_write_model_configuration_manual_recovery_gate",
        _assess_and_change_source,
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryGateVerificationChangedError,
        match="changed during verification",
    ):
        verify_write_model_configuration_manual_recovery_gate_snapshot(
            gate_snapshot_path=source_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 5, tzinfo=UTC),
        )


@pytest.mark.unit
def test_manual_recovery_clearance_opens_normal_write_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    _receipt_path, receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)
    workspace_dir = tmp_path / "workspace"
    before = {
        path: path.read_bytes()
        for path in (
            config_root / "run.json",
            config_root / "llm_models.json",
            *(Path(str(operation["target_manifest_path"])) for operation in plan["operations"]),
        )
    }
    blocked = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert blocked["status"] == "clearance_required"
    assert blocked["normal_write_allowed"] is False
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
    )
    output_path = tmp_path / "manual-recovery-clearance.json"

    clearance = issue_write_model_configuration_manual_recovery_clearance(
        clearance_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        clearance_output_path=output_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
    )

    assert (
        json.loads(request_path.read_text(encoding="utf-8"))["schema_version"]
        == "write_model_configuration_manual_recovery_clearance_request_v1"
    )
    assert clearance["schema_version"] == ("write_model_configuration_manual_recovery_clearance_v1")
    assert "clearance_revocation_lineage" not in clearance
    assert clearance["status"] == "cleared"
    assert clearance["verification_status"] == "current"
    assert clearance["normal_write_clearance_granted"] is True
    assert clearance["configuration_mutation_performed"] is False
    assert clearance["approval_consumed"] is False
    assert clearance["model_execution_performed"] is False
    validate_write_model_configuration_manual_recovery_clearance(clearance)
    internal_path = (
        write_model_configuration_manual_recovery_clearance_root(workspace_dir=workspace_dir)
        / f"{receipt['transaction_id']}.json"
    )
    assert json.loads(output_path.read_text(encoding="utf-8")) == (clearance)
    assert json.loads(internal_path.read_text(encoding="utf-8")) == (clearance)
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert gate["status"] == "cleared"
    assert gate["normal_write_allowed"] is True
    assert gate["clearance_present"] is True
    assert gate["clearance_fingerprint"] == clearance["clearance_fingerprint"]
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.unit
def test_manual_recovery_clearance_revocation_blocks_gate_without_side_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        snapshot_builder,
        plan,
        receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    protected_paths = (
        config_root / "run.json",
        config_root / "llm_models.json",
        *(Path(str(operation["target_manifest_path"])) for operation in plan["operations"]),
    )
    before = {path: path.read_bytes() for path in protected_paths}
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=receipt,
        clearance=clearance,
    )
    output_path = tmp_path / "clearance-revocation.json"

    revocation = revoke_write_model_configuration_manual_recovery_clearance(
        revocation_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        manual_recovery_clearance_path=clearance_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        revocation_output_path=output_path,
        now=datetime(2026, 7, 26, 10, 45, tzinfo=UTC),
    )

    assert revocation["status"] == "revoked"
    assert revocation["normal_write_clearance_revoked"] is True
    assert revocation["normal_write_allowed"] is False
    assert revocation["configuration_mutation_performed"] is False
    assert revocation["approval_consumed"] is False
    assert revocation["model_execution_performed"] is False
    validate_write_model_configuration_manual_recovery_clearance_revocation(revocation)
    internal_path = (
        write_model_configuration_manual_recovery_clearance_revocation_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    )
    assert load_write_model_configuration_manual_recovery_clearance_revocation(internal_path)[1] == revocation
    assert json.loads(output_path.read_text(encoding="utf-8")) == (revocation)
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert gate["schema_version"] == ("write_model_configuration_manual_recovery_gate_v4")
    assert gate["status"] == "clearance_revoked"
    assert gate["clearance_present"] is True
    assert gate["clearance_revoked"] is True
    assert gate["normal_write_allowed"] is False
    assert gate["clearance_fingerprint"] == clearance["clearance_fingerprint"]
    assert gate["revocation_fingerprint"] == revocation["revocation_fingerprint"]
    assert {path: path.read_bytes() for path in protected_paths} == before

    def _unexpected_snapshot() -> Mapping[str, Any]:
        raise AssertionError("re-exporting clearance must not run models")

    issue_write_model_configuration_manual_recovery_clearance(
        clearance_request_path=(tmp_path / "manual-recovery-clearance-request.json"),
        manual_recovery_receipt_path=receipt_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        clearance_output_path=tmp_path / "reexported-clearance.json",
        snapshot_builder=_unexpected_snapshot,
        now=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
    )
    still_revoked = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert still_revoked["status"] == "clearance_revoked"
    assert still_revoked["normal_write_allowed"] is False


@pytest.mark.unit
def test_manual_recovery_clearance_revocation_reexports_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        _snapshot_builder,
        _plan,
        receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=receipt,
        clearance=clearance,
    )
    original = revoke_write_model_configuration_manual_recovery_clearance(
        revocation_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        manual_recovery_clearance_path=clearance_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        revocation_output_path=(tmp_path / "clearance-revocation.json"),
        now=datetime(2026, 7, 26, 10, 45, tzinfo=UTC),
    )
    reexport_path = tmp_path / "clearance-revocation-copy.json"

    reexported = revoke_write_model_configuration_manual_recovery_clearance(
        revocation_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        manual_recovery_clearance_path=clearance_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        revocation_output_path=reexport_path,
        now=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
    )

    assert reexported == original
    assert json.loads(reexport_path.read_text(encoding="utf-8")) == (original)


@pytest.mark.unit
def test_manual_recovery_clearance_revocation_rejects_stale_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        _snapshot_builder,
        _plan,
        receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=receipt,
        clearance=clearance,
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError,
        match="older than four hours",
    ):
        revoke_write_model_configuration_manual_recovery_clearance(
            revocation_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            revocation_output_path=(tmp_path / "clearance-revocation.json"),
            now=datetime(2026, 7, 26, 14, 41, tzinfo=UTC),
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field_name", "replacement", "expected_message"),
    [
        ("ticker", "MSFT", "request identity changed"),
        ("transaction_id", "other-transaction", "request identity changed"),
        (
            "manual_recovery_receipt_fingerprint",
            "sha256:" + ("0" * 64),
            "request identity changed",
        ),
        (
            "manual_recovery_clearance_fingerprint",
            "sha256:" + ("1" * 64),
            "request identity changed",
        ),
        (
            "revoked_at",
            "2026-07-26T10:35:00Z",
            "must follow clearance issuance",
        ),
        (
            "revoked_at",
            "2026-07-26T10:50:00Z",
            "not effective yet",
        ),
    ],
)
def test_manual_recovery_clearance_revocation_rejects_wrong_identity_or_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    replacement: str,
    expected_message: str,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        _snapshot_builder,
        _plan,
        receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=receipt,
        clearance=clearance,
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request[field_name] = replacement
    request_path.write_text(
        json.dumps(request, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError,
        match=expected_message,
    ):
        revoke_write_model_configuration_manual_recovery_clearance(
            revocation_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            revocation_output_path=(tmp_path / "clearance-revocation.json"),
            now=datetime(2026, 7, 26, 10, 45, tzinfo=UTC),
        )


@pytest.mark.unit
def test_manual_recovery_clearance_revocation_rejects_forged_clearance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        _snapshot_builder,
        _plan,
        receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    forged = deepcopy(clearance)
    forged["clearance_reason"] = "Forged but internally consistent."
    _replace_payload_fingerprint(
        forged,
        fingerprint_field="clearance_fingerprint",
    )
    clearance_path.write_text(
        json.dumps(forged, indent=2) + "\n",
        encoding="utf-8",
    )
    validate_write_model_configuration_manual_recovery_clearance(forged)
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=receipt,
        clearance=forged,
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError,
        match="exact authoritative clearance",
    ):
        revoke_write_model_configuration_manual_recovery_clearance(
            revocation_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            revocation_output_path=(tmp_path / "clearance-revocation.json"),
            now=datetime(2026, 7, 26, 10, 45, tzinfo=UTC),
        )


@pytest.mark.unit
def test_manual_recovery_clearance_revocation_records_before_export_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        _snapshot_builder,
        _plan,
        receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=receipt,
        clearance=clearance,
    )
    occupied_path = tmp_path / "occupied-revocation.json"
    occupied_path.write_text('{"occupied": true}\n', encoding="utf-8")

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceRevocationReceiptError,
        match="recorded internally",
    ):
        revoke_write_model_configuration_manual_recovery_clearance(
            revocation_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            revocation_output_path=occupied_path,
            now=datetime(2026, 7, 26, 10, 45, tzinfo=UTC),
        )

    internal_path = (
        write_model_configuration_manual_recovery_clearance_revocation_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    )
    validate_write_model_configuration_manual_recovery_clearance_revocation(
        json.loads(internal_path.read_text(encoding="utf-8"))
    )
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert gate["status"] == "clearance_revoked"
    assert gate["normal_write_allowed"] is False
    assert json.loads(occupied_path.read_text(encoding="utf-8")) == {"occupied": True}


@pytest.mark.unit
def test_manual_recovery_gate_rejects_semantically_forged_revocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        _snapshot_builder,
        _plan,
        receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=receipt,
        clearance=clearance,
    )
    revoke_write_model_configuration_manual_recovery_clearance(
        revocation_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        manual_recovery_clearance_path=clearance_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        revocation_output_path=tmp_path / "clearance-revocation.json",
        now=datetime(2026, 7, 26, 10, 45, tzinfo=UTC),
    )
    internal_path = (
        write_model_configuration_manual_recovery_clearance_revocation_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    )
    forged = json.loads(internal_path.read_text(encoding="utf-8"))
    forged["revoked_by"] = "forged@example.com"
    _replace_payload_fingerprint(
        forged,
        fingerprint_field="revocation_fingerprint",
    )
    internal_path.write_text(
        json.dumps(forged, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="another identity",
    ):
        assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
        )


@pytest.mark.unit
def test_manual_recovery_clearance_revocation_rejects_internal_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        _snapshot_builder,
        _plan,
        receipt,
        clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=receipt,
        clearance=clearance,
    )
    internal_path = (
        write_model_configuration_manual_recovery_clearance_revocation_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    )
    original_is_symlink = Path.is_symlink

    def _is_symlink(path: Path) -> bool:
        if path == internal_path:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", _is_symlink)

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="contains a symlink",
    ):
        revoke_write_model_configuration_manual_recovery_clearance(
            revocation_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            revocation_output_path=(tmp_path / "clearance-revocation.json"),
            now=datetime(2026, 7, 26, 10, 45, tzinfo=UTC),
        )


@pytest.mark.unit
def test_revoked_clearance_restart_exports_consumable_recovery_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        _snapshot_builder,
        prior_plan,
        receipt,
        clearance,
        revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    protected_paths = (
        config_root / "run.json",
        config_root / "llm_models.json",
        *(Path(str(operation["target_manifest_path"])) for operation in prior_plan["operations"]),
    )
    before = {path: path.read_bytes() for path in protected_paths}
    evidence_output_path = tmp_path / "restart-evidence.json"

    evidence = restart_write_model_configuration_manual_recovery_after_clearance_revocation(
        manual_recovery_receipt_path=receipt_path,
        manual_recovery_clearance_path=clearance_path,
        manual_recovery_clearance_revocation_path=revocation_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        evidence_output_path=evidence_output_path,
        now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
    )

    validate_write_model_configuration_manual_recovery_evidence(evidence)
    assert evidence["schema_version"] == ("write_model_configuration_manual_recovery_evidence_v2")
    lineage = evidence["clearance_revocation_lineage"]
    assert lineage["revoked_transaction_id"] == receipt["transaction_id"]
    assert lineage["revoked_manual_recovery_receipt_fingerprint"] == (receipt["receipt_fingerprint"])
    assert lineage["manual_recovery_clearance_fingerprint"] == (clearance["clearance_fingerprint"])
    assert lineage["manual_recovery_clearance_revocation_fingerprint"] == revocation["revocation_fingerprint"]
    assert evidence["status"] == "manual_recovery_required"
    assert evidence["configuration_mutation_performed"] is False
    assert evidence["approval_consumed_by_evidence_export"] is False
    assert evidence["model_execution_performed"] is False
    assert load_write_model_configuration_manual_recovery_evidence(evidence_output_path)[1] == evidence
    original_evidence = load_write_model_configuration_manual_recovery_evidence(
        receipt["source_manual_recovery_evidence"]["path"]
    )[1]
    assert evidence["source_rollback_receipt"] == original_evidence["source_rollback_receipt"]
    assert {path: path.read_bytes() for path in protected_paths} == before

    selection_path = _persist_manual_recovery_selection_request(
        path=tmp_path / "restart-selection.json",
        evidence=evidence,
        selected_state="applied",
        selected_at="2026-07-26T10:55:00Z",
    )
    next_plan = build_write_model_configuration_manual_recovery_plan(
        manual_recovery_evidence_path=evidence_output_path,
        selection_request_path=selection_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 11, 0, tzinfo=UTC),
    )
    validate_write_model_configuration_manual_recovery_plan(next_plan)
    assert next_plan["schema_version"] == ("write_model_configuration_manual_recovery_plan_v2")
    assert next_plan["clearance_revocation_lineage"] == lineage
    assert next_plan["source_manual_recovery_evidence"]["path"] == str(evidence_output_path.resolve())
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert gate["status"] == "clearance_revoked"
    assert gate["normal_write_allowed"] is False


@pytest.mark.unit
def test_revoked_clearance_restart_lineage_survives_full_recovery_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        snapshot_builder,
        _prior_plan,
        _prior_receipt,
        _clearance,
        _revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    workspace_dir = tmp_path / "workspace"
    evidence_path = tmp_path / "restart-v2-evidence.json"
    evidence = restart_write_model_configuration_manual_recovery_after_clearance_revocation(
        manual_recovery_receipt_path=receipt_path,
        manual_recovery_clearance_path=clearance_path,
        manual_recovery_clearance_revocation_path=revocation_path,
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        evidence_output_path=evidence_path,
        now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
    )
    lineage = evidence["clearance_revocation_lineage"]
    selection_path = _persist_manual_recovery_selection_request(
        path=tmp_path / "restart-v2-selection.json",
        evidence=evidence,
        selected_state="preapplication",
        selected_at="2026-07-26T10:55:00Z",
    )
    plan = build_write_model_configuration_manual_recovery_plan(
        manual_recovery_evidence_path=evidence_path,
        selection_request_path=selection_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 11, 0, tzinfo=UTC),
    )
    plan_path = persist_write_model_configuration_manual_recovery_plan(
        plan,
        tmp_path / "restart-v2-plan.json",
    )
    approval_request_path = _persist_manual_recovery_approval_request(
        path=tmp_path / "restart-v2-approval-request.json",
        plan=plan,
        evidence=evidence,
        approved_at="2026-07-26T11:10:00Z",
        expires_at="2026-07-26T12:10:00Z",
    )
    approval = build_write_model_configuration_manual_recovery_approval(
        approval_request_path=approval_request_path,
        manual_recovery_plan_path=plan_path,
        config_root=config_root,
        now=datetime(2026, 7, 26, 11, 10, tzinfo=UTC),
    )
    approval_path = persist_write_model_configuration_manual_recovery_approval(
        approval,
        tmp_path / "restart-v2-approval.json",
    )
    recovered_receipt_path = tmp_path / "restart-v2-receipt.json"
    recovered_receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=workspace_dir,
        receipt_output_path=recovered_receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 11, 15, tzinfo=UTC),
    )
    verification = verify_write_model_configuration_manual_recovery_receipt(
        manual_recovery_receipt_path=recovered_receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        snapshot_builder=snapshot_builder,
    )
    intent = load_write_model_configuration_manual_recovery_intent(recovered_receipt["write_ahead_intent"]["path"])[1]
    consumption = load_write_model_configuration_manual_recovery_consumption(
        recovered_receipt["approval_consumption"]["path"]
    )[1]
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    approval_request = json.loads(approval_request_path.read_text(encoding="utf-8"))
    clearance_request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "restart-v2-clearance-request.json",
        receipt=recovered_receipt,
        cleared_at="2026-07-26T11:20:00Z",
    )
    clearance_request = json.loads(clearance_request_path.read_text(encoding="utf-8"))
    legacy_clearance_request = deepcopy(clearance_request)
    legacy_clearance_request["schema_version"] = "write_model_configuration_manual_recovery_clearance_request_v1"
    legacy_clearance_request.pop("clearance_revocation_lineage")
    legacy_clearance_request["acknowledgements"].remove("reviewed_exact_clearance_revocation_lineage")
    validate_write_model_configuration_manual_recovery_clearance_request(legacy_clearance_request)
    legacy_clearance_request_path = tmp_path / "restart-v1-clearance-request.json"
    legacy_clearance_request_path.write_text(
        json.dumps(legacy_clearance_request, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="request lineage does not match the receipt",
    ):
        issue_write_model_configuration_manual_recovery_clearance(
            clearance_request_path=legacy_clearance_request_path,
            manual_recovery_receipt_path=recovered_receipt_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            clearance_output_path=tmp_path / "must-not-create-v1-clearance.json",
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 11, 25, tzinfo=UTC),
        )
    substituted_clearance_request = deepcopy(clearance_request)
    substituted_lineage = substituted_clearance_request["clearance_revocation_lineage"]
    substituted_lineage["manual_recovery_clearance_revocation_fingerprint"] = "sha256:" + ("0" * 64)
    _replace_payload_fingerprint(
        substituted_lineage,
        fingerprint_field="lineage_fingerprint",
    )
    validate_write_model_configuration_manual_recovery_clearance_request(substituted_clearance_request)
    substituted_clearance_request_path = tmp_path / "restart-substituted-clearance-request.json"
    substituted_clearance_request_path.write_text(
        json.dumps(substituted_clearance_request, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="request lineage does not match the receipt",
    ):
        issue_write_model_configuration_manual_recovery_clearance(
            clearance_request_path=substituted_clearance_request_path,
            manual_recovery_receipt_path=recovered_receipt_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            clearance_output_path=(tmp_path / "must-not-create-substituted-clearance.json"),
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 11, 25, tzinfo=UTC),
        )
    pre_clearance_gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 11, 24, tzinfo=UTC),
    )
    assert pre_clearance_gate["status"] == "clearance_required"
    assert pre_clearance_gate["normal_write_allowed"] is False
    assert pre_clearance_gate["clearance_revocation_lineage"] == lineage
    assert pre_clearance_gate["clearance_revocation_lineage_status"] == "current"
    validate_write_model_configuration_manual_recovery_gate(pre_clearance_gate)
    prior_revocation_path = Path(lineage["source_manual_recovery_clearance_revocation"]["path"])
    prior_revocation_bytes = prior_revocation_path.read_bytes()
    prior_revocation = json.loads(prior_revocation_bytes)
    prior_revocation["revocation_reason"] = "tampered before new clearance"
    prior_revocation_path.write_text(
        json.dumps(prior_revocation, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="clearance revocation lineage is not current",
    ):
        assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 26, 11, 24, 30, tzinfo=UTC),
        )
    prior_revocation_path.write_bytes(prior_revocation_bytes)
    new_clearance = issue_write_model_configuration_manual_recovery_clearance(
        clearance_request_path=clearance_request_path,
        manual_recovery_receipt_path=recovered_receipt_path,
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        clearance_output_path=tmp_path / "restart-v2-clearance.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 11, 25, tzinfo=UTC),
    )

    artifacts = (
        evidence,
        selection,
        plan,
        approval_request,
        approval,
        intent,
        consumption,
        recovered_receipt,
        verification,
        clearance_request,
        new_clearance,
    )
    assert [artifact["schema_version"] for artifact in artifacts] == [
        "write_model_configuration_manual_recovery_evidence_v2",
        "write_model_configuration_manual_recovery_selection_request_v2",
        "write_model_configuration_manual_recovery_plan_v2",
        "write_model_configuration_manual_recovery_approval_request_v2",
        "write_model_configuration_manual_recovery_approval_v2",
        "write_model_configuration_manual_recovery_intent_v2",
        "write_model_configuration_manual_recovery_consumption_v2",
        "write_model_configuration_manual_recovery_receipt_v2",
        "write_model_configuration_manual_recovery_verification_v2",
        "write_model_configuration_manual_recovery_clearance_request_v2",
        "write_model_configuration_manual_recovery_clearance_v2",
    ]
    assert all(artifact["clearance_revocation_lineage"] == lineage for artifact in artifacts)
    validators = (
        (
            evidence,
            validate_write_model_configuration_manual_recovery_evidence,
        ),
        (
            selection,
            validate_write_model_configuration_manual_recovery_selection_request,
        ),
        (
            plan,
            validate_write_model_configuration_manual_recovery_plan,
        ),
        (
            approval_request,
            validate_write_model_configuration_manual_recovery_approval_request,
        ),
        (
            approval,
            validate_write_model_configuration_manual_recovery_approval,
        ),
        (
            intent,
            validate_write_model_configuration_manual_recovery_intent,
        ),
        (
            consumption,
            validate_write_model_configuration_manual_recovery_consumption,
        ),
        (
            recovered_receipt,
            validate_write_model_configuration_manual_recovery_receipt,
        ),
        (
            verification,
            validate_write_model_configuration_manual_recovery_verification,
        ),
        (
            clearance_request,
            validate_write_model_configuration_manual_recovery_clearance_request,
        ),
        (
            new_clearance,
            validate_write_model_configuration_manual_recovery_clearance,
        ),
    )
    for artifact, validator in validators:
        missing_lineage = deepcopy(artifact)
        missing_lineage.pop("clearance_revocation_lineage")
        with pytest.raises(ValueError, match="fields"):
            validator(missing_lineage)
    reports = (
        format_write_model_configuration_manual_recovery_evidence_report(evidence),
        format_write_model_configuration_manual_recovery_plan_report(plan),
        format_write_model_configuration_manual_recovery_approval_report(approval),
        format_write_model_configuration_manual_recovery_receipt_report(recovered_receipt),
        format_write_model_configuration_manual_recovery_verification_report(verification),
        format_write_model_configuration_manual_recovery_clearance_report(new_clearance),
    )
    revocation_fingerprint = lineage["manual_recovery_clearance_revocation_fingerprint"]
    assert all(any(revocation_fingerprint in line for line in report) for report in reports)
    assert recovered_receipt["status"] == "recovered"
    assert verification["status"] == "current"
    assert verification["source_chain_valid"] is True
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert gate["status"] == "cleared"
    assert gate["normal_write_allowed"] is True
    assert gate["latest_transaction_id"] == recovered_receipt["transaction_id"]
    assert gate["clearance_revocation_lineage"] == lineage
    assert gate["clearance_revocation_lineage_status"] == "current"
    gate_report = format_write_model_configuration_manual_recovery_gate_report(gate)
    assert any(lineage["lineage_fingerprint"] in line for line in gate_report)
    assert any(lineage["manual_recovery_clearance_revocation_fingerprint"] in line for line in gate_report)
    new_revocation_request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "restart-v2-clearance-revocation-request.json",
        receipt=recovered_receipt,
        clearance=new_clearance,
        revoked_at="2026-07-26T11:30:00Z",
    )
    new_revocation = revoke_write_model_configuration_manual_recovery_clearance(
        revocation_request_path=new_revocation_request_path,
        manual_recovery_receipt_path=recovered_receipt_path,
        manual_recovery_clearance_path=(tmp_path / "restart-v2-clearance.json"),
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        revocation_output_path=(tmp_path / "restart-v2-clearance-revocation.json"),
        now=datetime(2026, 7, 26, 11, 35, tzinfo=UTC),
    )
    assert new_revocation["status"] == "revoked"
    revoked_gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert revoked_gate["status"] == "clearance_revoked"
    assert revoked_gate["normal_write_allowed"] is False
    lineage_revocation_path = Path(lineage["source_manual_recovery_clearance_revocation"]["path"])
    lineage_revocation = json.loads(lineage_revocation_path.read_text(encoding="utf-8"))
    lineage_revocation["revocation_reason"] = "tampered after recovery"
    lineage_revocation_path.write_text(
        json.dumps(lineage_revocation, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="clearance revocation lineage is not current",
    ):
        assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
        )
    with pytest.raises(
        WriteModelConfigurationManualRecoveryVerificationBlockedError,
        match="clearance revocation lineage is not current",
    ):
        verify_write_model_configuration_manual_recovery_receipt(
            manual_recovery_receipt_path=recovered_receipt_path,
            config_root=config_root,
            expected_ticker="AAPL",
            snapshot_builder=snapshot_builder,
        )


@pytest.mark.unit
def test_revoked_clearance_restart_rejects_cross_layer_lineage_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        _snapshot_builder,
        _prior_plan,
        _prior_receipt,
        _clearance,
        _revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    evidence_path = tmp_path / "restart-lineage-evidence.json"
    evidence = restart_write_model_configuration_manual_recovery_after_clearance_revocation(
        manual_recovery_receipt_path=receipt_path,
        manual_recovery_clearance_path=clearance_path,
        manual_recovery_clearance_revocation_path=revocation_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        evidence_output_path=evidence_path,
        now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
    )
    substituted_lineage = deepcopy(evidence["clearance_revocation_lineage"])
    substituted_lineage["manual_recovery_clearance_revocation_fingerprint"] = "sha256:" + ("0" * 64)
    _replace_payload_fingerprint(
        substituted_lineage,
        fingerprint_field="lineage_fingerprint",
    )
    mismatched_selection_path = _persist_manual_recovery_selection_request(
        path=tmp_path / "restart-mismatched-selection.json",
        evidence=evidence,
        selected_state="applied",
        selected_at="2026-07-26T10:55:00Z",
    )
    mismatched_selection = json.loads(mismatched_selection_path.read_text(encoding="utf-8"))
    mismatched_selection["clearance_revocation_lineage"] = substituted_lineage
    mismatched_selection_path.write_text(
        json.dumps(mismatched_selection, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="lineage does not match the evidence",
    ):
        build_write_model_configuration_manual_recovery_plan(
            manual_recovery_evidence_path=evidence_path,
            selection_request_path=mismatched_selection_path,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 26, 11, 0, tzinfo=UTC),
        )

    selection_path = _persist_manual_recovery_selection_request(
        path=tmp_path / "restart-current-selection.json",
        evidence=evidence,
        selected_state="applied",
        selected_at="2026-07-26T10:55:00Z",
    )
    plan = build_write_model_configuration_manual_recovery_plan(
        manual_recovery_evidence_path=evidence_path,
        selection_request_path=selection_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 11, 0, tzinfo=UTC),
    )
    plan_path = persist_write_model_configuration_manual_recovery_plan(
        plan,
        tmp_path / "restart-current-plan.json",
    )
    approval_request_path = _persist_manual_recovery_approval_request(
        path=tmp_path / "restart-mismatched-approval-request.json",
        plan=plan,
        evidence=evidence,
        approved_at="2026-07-26T11:10:00Z",
        expires_at="2026-07-26T12:10:00Z",
    )
    approval_request = json.loads(approval_request_path.read_text(encoding="utf-8"))
    approval_request["clearance_revocation_lineage"] = substituted_lineage
    approval_request_path.write_text(
        json.dumps(approval_request, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="lineage does not match the plan",
    ):
        build_write_model_configuration_manual_recovery_approval(
            approval_request_path=approval_request_path,
            manual_recovery_plan_path=plan_path,
            config_root=config_root,
            now=datetime(2026, 7, 26, 11, 10, tzinfo=UTC),
        )


@pytest.mark.unit
def test_revoked_clearance_restart_requires_current_revoked_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        _snapshot_builder,
        _plan,
        receipt,
        _clearance,
        _revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    internal_revocation_path = (
        write_model_configuration_manual_recovery_clearance_revocation_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    )
    internal_revocation_path.unlink()

    with pytest.raises(
        WriteModelConfigurationManualRecoveryRestartBlockedError,
        match="clearance_revoked",
    ):
        restart_write_model_configuration_manual_recovery_after_clearance_revocation(
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            manual_recovery_clearance_revocation_path=revocation_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            evidence_output_path=tmp_path / "restart-evidence.json",
            now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "changed_artifact",
    ["receipt", "clearance", "revocation"],
)
def test_revoked_clearance_restart_requires_exact_supplied_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_artifact: str,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        _snapshot_builder,
        _plan,
        _receipt,
        _clearance,
        _revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    paths = {
        "receipt": receipt_path,
        "clearance": clearance_path,
        "revocation": revocation_path,
    }
    changed_path = tmp_path / f"reformatted-{changed_artifact}.json"
    changed_payload = json.loads(paths[changed_artifact].read_text(encoding="utf-8"))
    changed_path.write_text(
        json.dumps(
            changed_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    paths[changed_artifact] = changed_path

    with pytest.raises(
        WriteModelConfigurationManualRecoveryRestartBlockedError,
        match="exact",
    ):
        restart_write_model_configuration_manual_recovery_after_clearance_revocation(
            manual_recovery_receipt_path=paths["receipt"],
            manual_recovery_clearance_path=paths["clearance"],
            manual_recovery_clearance_revocation_path=paths["revocation"],
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            evidence_output_path=tmp_path / "restart-evidence.json",
            now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "changed_source",
    ["manual_recovery_evidence", "rollback_receipt"],
)
def test_revoked_clearance_restart_rejects_changed_source_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_source: str,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        _snapshot_builder,
        _plan,
        receipt,
        _clearance,
        _revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    source_evidence_path = Path(str(receipt["source_manual_recovery_evidence"]["path"]))
    source_evidence = load_write_model_configuration_manual_recovery_evidence(source_evidence_path)[1]
    source_path = (
        source_evidence_path
        if changed_source == "manual_recovery_evidence"
        else Path(str(source_evidence["source_rollback_receipt"]["path"]))
    )
    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    source_path.write_text(
        json.dumps(
            source_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryRestartBlockedError,
        match="source identity changed",
    ):
        restart_write_model_configuration_manual_recovery_after_clearance_revocation(
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            manual_recovery_clearance_revocation_path=revocation_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            evidence_output_path=tmp_path / "restart-evidence.json",
            now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
        )


@pytest.mark.unit
def test_revoked_clearance_restart_blocks_configuration_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        _snapshot_builder,
        plan,
        _receipt,
        _clearance,
        _revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_observe = rollback_application_module._observe_manual_recovery_target
    first_target = Path(str(plan["operations"][0]["target_manifest_path"]))
    observation_count = 0

    def _observe_then_change(**kwargs: Any) -> tuple[str, str | None]:
        nonlocal observation_count
        observation = original_observe(**kwargs)
        observation_count += 1
        if observation_count == len(plan["operations"]):
            first_target.write_bytes(b"changed during restart evidence")
        return observation

    monkeypatch.setattr(
        rollback_application_module,
        "_observe_manual_recovery_target",
        _observe_then_change,
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryRestartBlockedError,
        match="configuration changed during",
    ):
        restart_write_model_configuration_manual_recovery_after_clearance_revocation(
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            manual_recovery_clearance_revocation_path=revocation_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            evidence_output_path=tmp_path / "restart-evidence.json",
            now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
        )
    assert not (tmp_path / "restart-evidence.json").exists()


@pytest.mark.unit
def test_revoked_clearance_restart_respects_transaction_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        _snapshot_builder,
        _plan,
        _receipt,
        _clearance,
        _revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    transaction_lock = create_write_model_configuration_transaction_lock(config_root)
    transaction_lock.acquire()
    try:
        with pytest.raises(
            WriteModelConfigurationManualRecoveryRestartBusyError,
            match="holds the lock",
        ):
            restart_write_model_configuration_manual_recovery_after_clearance_revocation(
                manual_recovery_receipt_path=receipt_path,
                manual_recovery_clearance_path=clearance_path,
                manual_recovery_clearance_revocation_path=(revocation_path),
                workspace_dir=tmp_path / "workspace",
                config_root=config_root,
                expected_ticker="AAPL",
                evidence_output_path=tmp_path / "restart-evidence.json",
                now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
            )
    finally:
        transaction_lock.release()


@pytest.mark.unit
def test_revoked_clearance_restart_rejects_output_inside_config_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        clearance_path,
        revocation_path,
        _snapshot_builder,
        _plan,
        _receipt,
        _clearance,
        _revocation,
    ) = _revoked_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryRestartBlockedError,
        match="outside the configuration root",
    ):
        restart_write_model_configuration_manual_recovery_after_clearance_revocation(
            manual_recovery_receipt_path=receipt_path,
            manual_recovery_clearance_path=clearance_path,
            manual_recovery_clearance_revocation_path=revocation_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            evidence_output_path=config_root / "restart-evidence.json",
            now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
        )


@pytest.mark.unit
def test_newer_manual_recovery_transaction_supersedes_old_revocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        first_config_root,
        first_receipt_path,
        first_clearance_path,
        _first_snapshot_builder,
        _first_plan,
        first_receipt,
        first_clearance,
    ) = _cleared_manual_recovery(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    shared_workspace = tmp_path / "workspace"
    request_path = _persist_manual_recovery_clearance_revocation_request(
        path=tmp_path / "clearance-revocation-request.json",
        receipt=first_receipt,
        clearance=first_clearance,
    )
    revoke_write_model_configuration_manual_recovery_clearance(
        revocation_request_path=request_path,
        manual_recovery_receipt_path=first_receipt_path,
        manual_recovery_clearance_path=first_clearance_path,
        workspace_dir=shared_workspace,
        config_root=first_config_root,
        expected_ticker="AAPL",
        revocation_output_path=tmp_path / "clearance-revocation.json",
        now=datetime(2026, 7, 26, 10, 45, tzinfo=UTC),
    )
    second_root = tmp_path / "second-incident"
    (
        second_config_root,
        second_plan_path,
        second_approval_path,
        second_snapshot_builder,
        _second_plan,
        _applied_bytes,
        _restore_bytes,
        _starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=second_root,
        monkeypatch=monkeypatch,
        selected_state="applied",
    )
    second_receipt_path = second_root / "manual-recovery-result.json"
    second_receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=second_plan_path,
        manual_recovery_approval_path=second_approval_path,
        config_root=second_config_root,
        workspace_dir=shared_workspace,
        receipt_output_path=second_receipt_path,
        snapshot_builder=second_snapshot_builder,
        now=datetime(2026, 7, 26, 10, 50, tzinfo=UTC),
    )

    assert second_receipt["status"] == "recovered"
    assert second_receipt["transaction_id"] != first_receipt["transaction_id"]
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=shared_workspace,
        config_root=second_config_root,
        expected_ticker="AAPL",
    )
    assert gate["latest_transaction_id"] == second_receipt["transaction_id"]
    assert gate["status"] == "clearance_required"
    assert gate["clearance_revoked"] is False
    assert gate["normal_write_allowed"] is False


@pytest.mark.unit
def test_manual_recovery_clearance_blocks_current_routing_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)[1]
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
    )
    (config_root / "run.json").write_text(
        '{"clearance_drift": true}\n',
        encoding="utf-8",
    )
    output_path = tmp_path / "manual-recovery-clearance.json"

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="current verification",
    ):
        issue_write_model_configuration_manual_recovery_clearance(
            clearance_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            clearance_output_path=output_path,
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
        )

    assert not output_path.exists()
    assert not (
        write_model_configuration_manual_recovery_clearance_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    ).exists()


@pytest.mark.unit
def test_manual_recovery_clearance_can_be_reexported_after_request_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)[1]
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
    )
    first_output_path = tmp_path / "manual-recovery-clearance.json"
    original = issue_write_model_configuration_manual_recovery_clearance(
        clearance_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        clearance_output_path=first_output_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
    )

    def _unexpected_snapshot() -> Mapping[str, Any]:
        raise AssertionError("an immutable re-export must not re-run models")

    reexport_path = tmp_path / "reexported-clearance.json"
    reexported = issue_write_model_configuration_manual_recovery_clearance(
        clearance_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        clearance_output_path=reexport_path,
        snapshot_builder=_unexpected_snapshot,
        now=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
    )

    assert reexported == original
    assert json.loads(reexport_path.read_text(encoding="utf-8")) == original


@pytest.mark.unit
def test_manual_recovery_clearance_records_internal_before_export_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)[1]
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
    )
    blocked_output_path = tmp_path / "occupied-clearance-output.json"
    blocked_output_path.write_text('{"occupied": true}\n', encoding="utf-8")

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceReceiptError,
        match="recorded internally",
    ):
        issue_write_model_configuration_manual_recovery_clearance(
            clearance_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            clearance_output_path=blocked_output_path,
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
        )

    internal_path = (
        write_model_configuration_manual_recovery_clearance_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    )
    internal_clearance = json.loads(internal_path.read_text(encoding="utf-8"))
    validate_write_model_configuration_manual_recovery_clearance(internal_clearance)
    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
    )
    assert gate["status"] == "cleared"
    assert gate["normal_write_allowed"] is True
    assert json.loads(blocked_output_path.read_text(encoding="utf-8")) == {"occupied": True}


@pytest.mark.unit
def test_manual_recovery_clearance_requires_independent_operator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)[1]
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
        cleared_by="SELECTOR@example.com",
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="must differ",
    ):
        issue_write_model_configuration_manual_recovery_clearance(
            clearance_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            clearance_output_path=(tmp_path / "manual-recovery-clearance.json"),
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
        )


@pytest.mark.unit
def test_manual_recovery_clearance_rejects_internal_symlink_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)[1]
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
    )
    internal_path = (
        write_model_configuration_manual_recovery_clearance_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    )
    original_is_symlink = Path.is_symlink

    def _is_symlink(path: Path) -> bool:
        if path == internal_path:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", _is_symlink)

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="contains a symlink",
    ):
        issue_write_model_configuration_manual_recovery_clearance(
            clearance_request_path=request_path,
            manual_recovery_receipt_path=receipt_path,
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
            clearance_output_path=(tmp_path / "manual-recovery-clearance.json"),
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
        )


@pytest.mark.unit
def test_manual_recovery_gate_blocks_starting_state_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
        _restore_bytes,
        _starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_replace = manual_recovery_application_module._replace_staged_file
    replace_calls = 0

    def _fail_second_replace(*, staged: Path, target: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected manual recovery failure")
        original_replace(staged=staged, target=target)

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_replace_staged_file",
        _fail_second_replace,
    )
    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "manual-recovery-restored.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
    )
    assert receipt["status"] == "starting_state_restored"

    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
    )

    assert gate["status"] == "manual_recovery_required"
    assert gate["latest_receipt_status"] == "starting_state_restored"
    assert gate["normal_write_allowed"] is False
    assert gate["reason_codes"] == ["new_manual_recovery_evidence_required"]


@pytest.mark.unit
def test_manual_recovery_gate_blocks_incomplete_transaction(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    transaction_dir = (
        tmp_path
        / "workspace"
        / ".dayu"
        / "write-model-configuration-manual-recoveries"
        / "transactions"
        / "interrupted-transaction"
    )
    transaction_dir.mkdir(parents=True)
    (transaction_dir / "intent.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
    )

    assert gate["status"] == "manual_recovery_required"
    assert gate["latest_receipt_status"] == "incomplete"
    assert gate["normal_write_allowed"] is False
    assert gate["reason_codes"] == ["incomplete_manual_recovery_transaction"]


@pytest.mark.unit
def test_manual_recovery_gate_rejects_internal_symlink_ancestor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"
    unsafe_component = workspace_dir.resolve() / ".dayu"
    original_is_symlink = Path.is_symlink

    def _is_symlink(path: Path) -> bool:
        if path == unsafe_component:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", _is_symlink)

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="contains a symlink",
    ):
        assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
        )


@pytest.mark.unit
def test_manual_recovery_gate_rejects_tampered_clearance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)[1]
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
    )
    issue_write_model_configuration_manual_recovery_clearance(
        clearance_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        clearance_output_path=(tmp_path / "manual-recovery-clearance.json"),
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
    )
    internal_path = (
        write_model_configuration_manual_recovery_clearance_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    )
    tampered = json.loads(internal_path.read_text(encoding="utf-8"))
    tampered["clearance_reference"] = "tampered"
    internal_path.write_text(
        json.dumps(tampered, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="clearance fingerprint mismatch",
    ):
        assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
        )


@pytest.mark.unit
def test_manual_recovery_gate_rejects_wrong_command_ticker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        _receipt_path,
        _snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="ticker does not match",
    ):
        assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="MSFT",
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tamper_case", "expected_message"),
    [
        ("routing", "routing identity changed"),
        ("time", "predates recovery completion"),
        ("operator", "must differ"),
    ],
)
def test_manual_recovery_gate_rejects_semantically_forged_clearance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_case: str,
    expected_message: str,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)[1]
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
    )
    issue_write_model_configuration_manual_recovery_clearance(
        clearance_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        clearance_output_path=(tmp_path / "manual-recovery-clearance.json"),
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
    )
    internal_path = (
        write_model_configuration_manual_recovery_clearance_root(workspace_dir=tmp_path / "workspace")
        / f"{receipt['transaction_id']}.json"
    )
    forged = json.loads(internal_path.read_text(encoding="utf-8"))
    if tamper_case == "routing":
        forged["verified_routing_snapshot_fingerprint"] = "sha256:" + ("0" * 64)
    elif tamper_case == "time":
        forged["cleared_at"] = "2026-07-26T10:20:00Z"
    else:
        forged["cleared_by"] = plan["selected_by"]
    _replace_payload_fingerprint(
        forged,
        fingerprint_field="clearance_fingerprint",
    )
    internal_path.write_text(
        json.dumps(forged, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match=expected_message,
    ):
        assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
        )


@pytest.mark.unit
def test_manual_recovery_gate_rejects_changed_operator_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        snapshot_builder,
        _plan,
        _applied_bytes,
    ) = _recovered_manual_recovery_receipt(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)[1]
    request_path = _persist_manual_recovery_clearance_request(
        path=tmp_path / "manual-recovery-clearance-request.json",
        receipt=receipt,
    )
    issue_write_model_configuration_manual_recovery_clearance(
        clearance_request_path=request_path,
        manual_recovery_receipt_path=receipt_path,
        workspace_dir=tmp_path / "workspace",
        config_root=config_root,
        expected_ticker="AAPL",
        clearance_output_path=(tmp_path / "manual-recovery-clearance.json"),
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 35, tzinfo=UTC),
    )
    plan_path = Path(str(receipt["source_manual_recovery_plan"]["path"]))
    changed_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    changed_plan["selected_by"] = "changed-selector@example.com"
    _replace_payload_fingerprint(
        changed_plan,
        fingerprint_field="plan_fingerprint",
    )
    plan_path.write_text(
        json.dumps(changed_plan, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryClearanceBlockedError,
        match="source identity changed",
    ):
        assess_write_model_configuration_manual_recovery_gate(
            workspace_dir=tmp_path / "workspace",
            config_root=config_root,
            expected_ticker="AAPL",
        )


@pytest.mark.unit
def test_manual_recovery_gate_respects_transaction_lock(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    transaction_lock = create_write_model_configuration_transaction_lock(config_root)
    transaction_lock.acquire()
    try:
        with pytest.raises(
            WriteModelConfigurationManualRecoveryClearanceBusyError,
            match="holds the lock",
        ):
            assess_write_model_configuration_manual_recovery_gate(
                workspace_dir=tmp_path / "workspace",
                config_root=config_root,
                expected_ticker="AAPL",
            )
    finally:
        transaction_lock.release()


@pytest.mark.unit
def test_manual_recovery_application_blocks_drift_before_consumption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        plan,
        _applied_bytes,
        _restore_bytes,
        _starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    target = Path(str(plan["operations"][0]["target_manifest_path"]))
    target.write_bytes(b"drift before approval consumption")
    receipt_path = tmp_path / "must-not-exist.json"

    with pytest.raises(
        WriteModelConfigurationManualRecoveryApplicationBlockedError,
        match="approval verification failed",
    ):
        apply_write_model_configuration_manual_recovery(
            manual_recovery_plan_path=plan_path,
            manual_recovery_approval_path=approval_path,
            config_root=config_root,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=receipt_path,
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
        )

    assert not receipt_path.exists()
    consumption_root = plan_path.parent / ".dayu" / ("consumed-write-model-configuration-manual-recovery-approvals")
    assert not consumption_root.exists()


@pytest.mark.unit
def test_interrupted_consumed_manual_recovery_restores_on_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        _plan,
        applied_bytes,
        _restore_bytes,
        starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_persist_receipts = manual_recovery_application_module._persist_receipts
    persist_calls = 0

    def _interrupt_receipt_persistence(**kwargs: Any) -> None:
        nonlocal persist_calls
        persist_calls += 1
        if persist_calls == 1:
            raise OSError("simulated process interruption")
        original_persist_receipts(**kwargs)

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_persist_receipts",
        _interrupt_receipt_persistence,
    )
    with pytest.raises(OSError, match="simulated process interruption"):
        apply_write_model_configuration_manual_recovery(
            manual_recovery_plan_path=plan_path,
            manual_recovery_approval_path=approval_path,
            config_root=config_root,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=tmp_path / "interrupted.json",
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
        )
    for target, expected in applied_bytes.items():
        assert Path(target).read_bytes() == expected

    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "recovered-interruption.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
    )

    assert receipt["status"] == "starting_state_restored"
    assert receipt["failure"]["stage"] == ("interrupted_transaction_recovery")
    assert {path: path.read_bytes() for path in starting_bytes} == starting_bytes
    validate_write_model_configuration_manual_recovery_receipt(receipt)


@pytest.mark.unit
def test_unconsumed_manual_recovery_reuses_existing_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        _plan,
        applied_bytes,
        _restore_bytes,
        starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_persist_exclusive = manual_recovery_application_module._persist_exclusive

    def _interrupt_before_consumption(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("interrupted before approval consumption")

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_persist_exclusive",
        _interrupt_before_consumption,
    )
    with pytest.raises(
        OSError,
        match="interrupted before approval consumption",
    ):
        apply_write_model_configuration_manual_recovery(
            manual_recovery_plan_path=plan_path,
            manual_recovery_approval_path=approval_path,
            config_root=config_root,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=tmp_path / "first-attempt.json",
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
        )
    assert {path: path.read_bytes() for path in starting_bytes} == starting_bytes
    intent_paths = list(
        (tmp_path / "workspace" / ".dayu" / "write-model-configuration-manual-recoveries").rglob("intent.json")
    )
    assert len(intent_paths) == 1

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_persist_exclusive",
        original_persist_exclusive,
    )
    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "second-attempt.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 30, tzinfo=UTC),
    )

    assert receipt["status"] == "recovered"
    for target, expected in applied_bytes.items():
        assert Path(target).read_bytes() == expected


@pytest.mark.unit
def test_consumed_manual_recovery_missing_intent_records_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        plan_path,
        approval_path,
        snapshot_builder,
        _plan,
        applied_bytes,
        _restore_bytes,
        _starting_bytes,
    ) = _manual_recovery_application_setup(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    original_persist_receipts = manual_recovery_application_module._persist_receipts

    def _interrupt_receipt_persistence(**_kwargs: Any) -> None:
        raise OSError("simulated receipt interruption")

    monkeypatch.setattr(
        manual_recovery_application_module,
        "_persist_receipts",
        _interrupt_receipt_persistence,
    )
    with pytest.raises(OSError, match="simulated receipt interruption"):
        apply_write_model_configuration_manual_recovery(
            manual_recovery_plan_path=plan_path,
            manual_recovery_approval_path=approval_path,
            config_root=config_root,
            workspace_dir=tmp_path / "workspace",
            receipt_output_path=tmp_path / "interrupted.json",
            snapshot_builder=snapshot_builder,
            now=datetime(2026, 7, 26, 10, 25, tzinfo=UTC),
        )
    intent_paths = list(
        (tmp_path / "workspace" / ".dayu" / "write-model-configuration-manual-recoveries").rglob("intent.json")
    )
    assert len(intent_paths) == 1
    intent_paths[0].unlink()
    monkeypatch.setattr(
        manual_recovery_application_module,
        "_persist_receipts",
        original_persist_receipts,
    )

    receipt = apply_write_model_configuration_manual_recovery(
        manual_recovery_plan_path=plan_path,
        manual_recovery_approval_path=approval_path,
        config_root=config_root,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "missing-intent-result.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
    )

    assert receipt["status"] == "recovery_failed"
    assert receipt["write_ahead_intent"] is None
    assert receipt["failure"]["recovery_failure_codes"] == ["write_ahead_intent:unavailable_or_invalid"]
    for target, expected in applied_bytes.items():
        assert Path(target).read_bytes() == expected
    validate_write_model_configuration_manual_recovery_receipt(receipt)


@pytest.mark.unit
def test_cli_exports_manual_recovery_evidence_without_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (
        config_root,
        receipt_path,
        _receipt,
        _rollback_plan,
        applied_bytes,
        _restore_bytes,
    ) = _recovery_failed_rollback_setup(tmp_path, monkeypatch)
    target_paths = [Path(path) for path in applied_bytes]
    before = {path: path.read_bytes() for path in target_paths}
    evidence_path = tmp_path / "manual-recovery-evidence.json"

    exit_code = _run_write_model_configuration_manual_recovery_evidence(
        args=Namespace(
            challenger_config_manual_recovery_receipt_input=str(receipt_path),
            challenger_config_manual_recovery_evidence_output=str(evidence_path),
        ),
        paths_config=cast(
            Any,
            Namespace(
                ticker="AAPL",
                config_root=config_root,
            ),
        ),
    )

    assert exit_code == 0
    persisted = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "manual_recovery_required"
    output = capsys.readouterr().out
    assert "manual recovery evidence" in output
    assert "Configuration : unchanged by evidence export" in output
    assert "Model calls   : none" in output
    assert "recovery command" not in output.lower()
    assert {path: path.read_bytes() for path in target_paths} == before


@pytest.mark.unit
def test_manual_recovery_evidence_is_partial_without_valid_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        receipt,
        _rollback_plan,
        applied_bytes,
        restore_bytes,
    ) = _recovery_failed_rollback_setup(tmp_path, monkeypatch)
    consumption_path = Path(str(receipt["approval_consumption"]["path"]))
    consumption = json.loads(consumption_path.read_text(encoding="utf-8"))
    intent_path = Path(str(consumption["transaction_dir"])) / "intent.json"
    intent_path.unlink()
    target_paths = [Path(path) for path in applied_bytes]
    before = {path: path.read_bytes() for path in target_paths}

    evidence = build_write_model_configuration_manual_recovery_evidence(
        rollback_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
    )

    assert evidence["write_ahead_intent"]["status"] == "missing"
    assert evidence["evidence_completeness"] == "partial"
    for operation in evidence["operations"]:
        target = str(operation["target_manifest_path"])
        assert operation["applied_candidate_available"] is False
        assert operation["applied_file_content_base64"] is None
        assert (
            base64.b64decode(
                operation["preapplication_file_content_base64"],
                validate=True,
            )
            == restore_bytes[target]
        )
    validate_write_model_configuration_manual_recovery_evidence(evidence)
    assert {path: path.read_bytes() for path in target_paths} == before


@pytest.mark.unit
def test_manual_recovery_evidence_blocks_target_drift_during_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        _receipt,
        rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _recovery_failed_rollback_setup(tmp_path, monkeypatch)
    original_observe = rollback_application_module._observe_manual_recovery_target
    first_target = Path(str(rollback_plan["operations"][0]["target_manifest_path"]))
    observation_count = 0

    def _drift_before_second_observation(**kwargs: Any) -> Any:
        nonlocal observation_count
        observation_count += 1
        if observation_count == len(rollback_plan["operations"]) + 1:
            first_target.write_bytes(b"changed during evidence export")
        return original_observe(**kwargs)

    monkeypatch.setattr(
        rollback_application_module,
        "_observe_manual_recovery_target",
        _drift_before_second_observation,
    )

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="configuration changed during",
    ):
        build_write_model_configuration_manual_recovery_evidence(
            rollback_receipt_path=receipt_path,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
        )


@pytest.mark.unit
def test_manual_recovery_evidence_rejects_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        receipt_path,
        _receipt,
        _rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _recovery_failed_rollback_setup(tmp_path, monkeypatch)
    evidence = build_write_model_configuration_manual_recovery_evidence(
        rollback_receipt_path=receipt_path,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
    )
    tampered = deepcopy(evidence)
    tampered["reason_codes"][1] = "applied_candidate_unavailable"
    tampered["evidence_fingerprint"] = rollback_application_module._fingerprint(
        {key: value for key, value in tampered.items() if key != "evidence_fingerprint"}
    )

    with pytest.raises(ValueError, match="reason_codes"):
        validate_write_model_configuration_manual_recovery_evidence(tampered)


@pytest.mark.unit
def test_manual_recovery_evidence_requires_recovery_failed_receipt(
    tmp_path: Path,
) -> None:
    (
        config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        _rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    receipt_path = tmp_path / "rolled-back.json"
    apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=receipt_path,
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )

    with pytest.raises(
        WriteModelConfigurationRollbackBlockedError,
        match="requires a recovery_failed receipt",
    ):
        build_write_model_configuration_manual_recovery_evidence(
            rollback_receipt_path=receipt_path,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
        )


@pytest.mark.unit
def test_operator_rollback_receipt_is_tamper_evident(
    tmp_path: Path,
) -> None:
    (
        _config_root,
        rollback_plan_path,
        rollback_approval_path,
        snapshot_builder,
        _rollback_plan,
        _applied_bytes,
        _restore_bytes,
    ) = _operator_rollback_application_setup(tmp_path)
    receipt = apply_write_model_configuration_operator_rollback(
        rollback_plan_path=rollback_plan_path,
        rollback_approval_path=rollback_approval_path,
        workspace_dir=tmp_path / "workspace",
        receipt_output_path=tmp_path / "receipt.json",
        snapshot_builder=snapshot_builder,
        now=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    )
    tampered = deepcopy(receipt)
    tampered["operations"][0]["restored_model_name"] = "other-model"

    with pytest.raises(ValueError, match="fingerprint"):
        validate_write_model_configuration_operator_rollback_receipt(tampered)
