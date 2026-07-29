from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import dayu.services.write_model_configuration_manual_recovery_gate_revalidation as revalidation_module
from dayu.services.write_model_configuration_manual_recovery_clearance import (
    WriteModelConfigurationManualRecoveryGateVerificationChangedError,
    assess_write_model_configuration_manual_recovery_gate,
    persist_write_model_configuration_manual_recovery_gate,
    persist_write_model_configuration_manual_recovery_gate_verification,
    verify_write_model_configuration_manual_recovery_gate_snapshot,
)
from dayu.services.write_model_configuration_manual_recovery_gate_revalidation import (
    format_write_model_configuration_manual_recovery_gate_revalidation_report,
    persist_write_model_configuration_manual_recovery_gate_revalidation,
    revalidate_write_model_configuration_manual_recovery_gate_verification,
    validate_write_model_configuration_manual_recovery_gate_revalidation,
)


def _saved_gate_verification(
    tmp_path: Path,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    config_root = tmp_path / "config"
    config_root.mkdir()
    workspace_dir = tmp_path / "workspace"
    source_gate = assess_write_model_configuration_manual_recovery_gate(
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
    )
    source_gate_path = tmp_path / "audit" / "manual-recovery-gate.json"
    persist_write_model_configuration_manual_recovery_gate(
        source_gate,
        source_gate_path,
        config_root=config_root,
    )
    source_verification = verify_write_model_configuration_manual_recovery_gate_snapshot(
        gate_snapshot_path=source_gate_path,
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 5, tzinfo=UTC),
    )
    source_verification_path = tmp_path / "audit" / "manual-recovery-gate-verification.json"
    persist_write_model_configuration_manual_recovery_gate_verification(
        source_verification,
        source_verification_path,
        config_root=config_root,
    )
    return (
        config_root,
        workspace_dir,
        source_verification_path,
        source_verification,
    )


@pytest.mark.unit
def test_gate_verification_revalidation_accepts_current_receipt_and_exports(
    tmp_path: Path,
) -> None:
    (
        config_root,
        workspace_dir,
        source_verification_path,
        source_verification,
    ) = _saved_gate_verification(tmp_path)

    revalidation = revalidate_write_model_configuration_manual_recovery_gate_verification(
        gate_verification_path=source_verification_path,
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 10, tzinfo=UTC),
    )

    assert revalidation["schema_version"] == (
        "write_model_configuration_manual_recovery_gate_verification_revalidation_v1"
    )
    assert revalidation["revalidated_at"] == "2026-07-29T09:10:00Z"
    assert revalidation["ticker"] == "AAPL"
    assert revalidation["status"] == "current"
    assert revalidation["action"] == ("saved_verification_matches_current_gate_state")
    assert revalidation["source_verification"] == source_verification
    assert revalidation["fresh_verification"]["verified_at"] == ("2026-07-29T09:10:00Z")
    assert revalidation["saved_current_state_fingerprint"] == revalidation["fresh_current_state_fingerprint"]
    assert revalidation["state_matches"] is True
    assert revalidation["changed_fields"] == []
    assert revalidation["reason_codes"] == ["saved_verification_and_bound_gate_match_current_assessment"]
    assert revalidation["normal_write_authorization_granted"] is False
    assert revalidation["configuration_mutation_performed"] is False
    assert revalidation["approval_consumed"] is False
    assert revalidation["model_execution_performed"] is False
    assert revalidation["source_verification_file_fingerprint"] == (
        "sha256:" + hashlib.sha256(source_verification_path.read_bytes()).hexdigest()
    )
    validate_write_model_configuration_manual_recovery_gate_revalidation(revalidation)
    report = format_write_model_configuration_manual_recovery_gate_revalidation_report(revalidation)
    assert any("State matches : True" in line for line in report)
    assert any("not granted by revalidation" in line for line in report)

    tampered = deepcopy(revalidation)
    tampered["fresh_verification"]["current_gate"]["assessed_at"] = "2026-07-29T09:10:01Z"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_write_model_configuration_manual_recovery_gate_revalidation(tampered)

    output_path = tmp_path / "audit" / "gate-verification-revalidation.json"
    persisted_path = persist_write_model_configuration_manual_recovery_gate_revalidation(
        revalidation,
        output_path,
        config_root=config_root,
    )
    assert persisted_path == output_path.resolve()
    assert json.loads(output_path.read_text(encoding="utf-8")) == (revalidation)
    assert (
        persist_write_model_configuration_manual_recovery_gate_revalidation(
            revalidation,
            output_path,
            config_root=config_root,
        )
        == persisted_path
    )
    changed = deepcopy(revalidation)
    changed["revalidated_at"] = "2026-07-29T09:10:01Z"
    with pytest.raises(ValueError, match="time is inconsistent"):
        persist_write_model_configuration_manual_recovery_gate_revalidation(
            changed,
            output_path,
            config_root=config_root,
        )
    with pytest.raises(ValueError, match="outside the configuration root"):
        persist_write_model_configuration_manual_recovery_gate_revalidation(
            revalidation,
            config_root / "revalidation.json",
            config_root=config_root,
        )


@pytest.mark.unit
def test_gate_verification_revalidation_reports_stale_current_gate(
    tmp_path: Path,
) -> None:
    (
        config_root,
        workspace_dir,
        source_verification_path,
        _source_verification,
    ) = _saved_gate_verification(tmp_path)
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

    revalidation = revalidate_write_model_configuration_manual_recovery_gate_verification(
        gate_verification_path=source_verification_path,
        workspace_dir=workspace_dir,
        config_root=config_root,
        expected_ticker="AAPL",
        now=datetime(2026, 7, 29, 9, 10, tzinfo=UTC),
    )

    assert revalidation["status"] == "stale"
    assert revalidation["action"] == "repeat_gate_snapshot_verification"
    assert revalidation["state_matches"] is False
    assert revalidation["changed_fields"] == [
        "action",
        "latest_receipt_status",
        "latest_transaction_id",
        "normal_write_allowed",
        "reason_codes",
        "status",
    ]
    assert revalidation["fresh_verification"]["status"] == "stale"
    assert revalidation["reason_codes"] == ["current_gate_state_changed_since_saved_verification"]
    validate_write_model_configuration_manual_recovery_gate_revalidation(revalidation)


@pytest.mark.unit
def test_gate_verification_revalidation_rejects_changed_bound_gate(
    tmp_path: Path,
) -> None:
    (
        config_root,
        workspace_dir,
        source_verification_path,
        source_verification,
    ) = _saved_gate_verification(tmp_path)
    source_gate_path = Path(source_verification["source_gate_path"])
    source_gate_path.write_bytes(source_gate_path.read_bytes() + b" ")

    with pytest.raises(
        WriteModelConfigurationManualRecoveryGateVerificationChangedError,
        match="bound by the saved verification has changed",
    ):
        revalidate_write_model_configuration_manual_recovery_gate_verification(
            gate_verification_path=source_verification_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 10, tzinfo=UTC),
        )


@pytest.mark.unit
def test_gate_verification_revalidation_rejects_invalid_or_internal_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        workspace_dir,
        source_verification_path,
        source_verification,
    ) = _saved_gate_verification(tmp_path)
    tampered = deepcopy(source_verification)
    tampered["verified_at"] = "2026-07-29T09:05:01Z"
    source_verification_path.write_text(
        json.dumps(tampered),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="inconsistent"):
        revalidate_write_model_configuration_manual_recovery_gate_verification(
            gate_verification_path=source_verification_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
        )

    internal_path = config_root / "gate-verification.json"
    internal_path.write_text(
        json.dumps(source_verification),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="outside the configuration root"):
        revalidate_write_model_configuration_manual_recovery_gate_verification(
            gate_verification_path=internal_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
        )

    source_verification_path.write_text(
        json.dumps(source_verification),
        encoding="utf-8",
    )
    original_is_symlink = Path.is_symlink

    def _is_symlink(path: Path) -> bool:
        if path.absolute() == source_verification_path.absolute():
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", _is_symlink)
    with pytest.raises(FileNotFoundError, match="must not be a symlink"):
        revalidate_write_model_configuration_manual_recovery_gate_verification(
            gate_verification_path=source_verification_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
        )


@pytest.mark.unit
def test_gate_verification_revalidation_detects_receipt_change_during_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        config_root,
        workspace_dir,
        source_verification_path,
        _source_verification,
    ) = _saved_gate_verification(tmp_path)
    original_verify = revalidation_module.verify_write_model_configuration_manual_recovery_gate_snapshot

    def _verify_and_change_receipt(**kwargs: Any) -> dict[str, Any]:
        fresh_verification = original_verify(**kwargs)
        source_verification_path.write_bytes(source_verification_path.read_bytes() + b" ")
        return fresh_verification

    monkeypatch.setattr(
        revalidation_module,
        "verify_write_model_configuration_manual_recovery_gate_snapshot",
        _verify_and_change_receipt,
    )

    with pytest.raises(
        WriteModelConfigurationManualRecoveryGateVerificationChangedError,
        match="changed during revalidation",
    ):
        revalidate_write_model_configuration_manual_recovery_gate_verification(
            gate_verification_path=source_verification_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker="AAPL",
            now=datetime(2026, 7, 29, 9, 10, tzinfo=UTC),
        )
