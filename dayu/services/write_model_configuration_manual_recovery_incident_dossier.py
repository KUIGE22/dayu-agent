"""Build one self-contained operator dossier from a recovery audit timeline."""

from __future__ import annotations

import hmac
import json
import os
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from dayu.contracts.model_config import ModelConfigJsonValue
from dayu.services._write_artifact_utils import (
    canonical_json_str,
    fingerprint_str,
    is_subpath,
    require_mapping,
    require_text,
    serialize_pretty,
)
from dayu.services.write_model_configuration_manual_recovery_clearance import (
    validate_write_model_configuration_manual_recovery_audit_timeline,
)

_SCHEMA_VERSION = (
    "write_model_configuration_manual_recovery_incident_dossier_v1"
)
_FIELDS = {
    "schema_version",
    "generated_at",
    "ticker",
    "transaction_id",
    "incident_state",
    "gate_relation",
    "normal_write_impact",
    "selected_events",
    "event_count",
    "source_timeline",
    "source_timeline_fingerprint",
    "reason_codes",
    "normal_write_authorization_granted",
    "configuration_mutation_performed",
    "approval_consumed",
    "model_execution_performed",
    "dossier_fingerprint",
}
_INCIDENT_STATE_REASONS = {
    "incomplete": "incomplete_manual_recovery_transaction",
    "recovery_failed": "manual_recovery_failed",
    "starting_state_restored": "manual_recovery_starting_state_restored",
    "recovered_clearance_required": "recovered_transaction_has_no_clearance",
    "recovered_cleared": "recovered_transaction_has_clearance",
    "recovered_clearance_revoked": (
        "recovered_transaction_clearance_revoked"
    ),
}
_GATE_RELATION_REASONS = {
    "current_incomplete_blocker": (
        "transaction_contributes_to_current_incomplete_gate"
    ),
    "current_complete_subject": "transaction_is_current_gate_subject",
    "historical": "transaction_is_historical_only",
}
_NORMAL_WRITE_IMPACTS = {
    "blocks_current_normal_writes",
    "current_gate_allows_normal_writes",
    "historical_only",
}
_TRANSACTION_ID_PREVIEW_LIMIT = 8


class WriteModelConfigurationManualRecoveryIncidentNotFoundError(
    LookupError
):
    """Raised when the requested transaction is absent from the timeline."""


def _exact_fields(
    payload: Mapping[str, Any],
    *,
    expected: set[str],
    name: str,
) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"{name} fields are invalid; missing={missing}, extra={extra}"
        )


def _transaction_id(value: ModelConfigJsonValue) -> str:
    transaction_id = require_text(
        value,
        name="transaction_id",
        maximum_length=64,
    )
    if (
        transaction_id in {".", ".."}
        or "/" in transaction_id
        or "\\" in transaction_id
    ):
        raise ValueError("transaction_id is unsafe")
    return transaction_id


def _validated_fingerprint(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> str:
    text = require_text(
        value,
        name=name,
        maximum_length=80,
    ).lower()
    digest = text.removeprefix("sha256:")
    if (
        not text.startswith("sha256:")
        or len(digest) != 64
        or any(
            character not in "0123456789abcdef"
            for character in digest
        )
    ):
        raise ValueError(f"{name} must be a sha256 fingerprint")
    return text


def _available_transaction_ids(
    timeline: Mapping[str, Any],
) -> list[str]:
    return sorted(
        {
            *timeline["incomplete_transaction_ids"],
            *(
                event["transaction_id"]
                for event in timeline["events"]
            ),
        }
    )


def _format_transaction_id_preview(
    transaction_ids: list[str],
) -> str:
    if not transaction_ids:
        return "none"
    visible = transaction_ids[:_TRANSACTION_ID_PREVIEW_LIMIT]
    preview = ", ".join(visible)
    remaining = len(transaction_ids) - len(visible)
    if remaining:
        return f"{preview} (+{remaining} more)"
    return preview


def _derive_incident(
    timeline: Mapping[str, Any],
    *,
    transaction_id: str,
) -> dict[str, Any]:
    incomplete_transaction_ids = timeline[
        "incomplete_transaction_ids"
    ]
    selected_events = [
        deepcopy(event)
        for event in timeline["events"]
        if event["transaction_id"] == transaction_id
    ]
    if transaction_id in incomplete_transaction_ids:
        if selected_events:
            raise ValueError(
                "incomplete transaction unexpectedly has audit events"
            )
        incident_state = "incomplete"
    else:
        receipt_events = [
            event
            for event in selected_events
            if event["event_type"] == "manual_recovery_receipt"
        ]
        if not receipt_events:
            available = _format_transaction_id_preview(
                _available_transaction_ids(timeline)
            )
            raise (
                WriteModelConfigurationManualRecoveryIncidentNotFoundError(
                    "manual recovery transaction is not present in "
                    "the audited history; available transaction IDs: "
                    f"{available}"
                )
            )
        if len(receipt_events) != 1:
            raise ValueError(
                "manual recovery transaction has invalid receipt events"
            )
        receipt = require_mapping(
            receipt_events[0]["artifact"],
            name="manual recovery receipt",
        )
        receipt_status = receipt["status"]
        clearance_present = any(
            event["event_type"] == "manual_recovery_clearance"
            for event in selected_events
        )
        revocation_present = any(
            event["event_type"]
            == "manual_recovery_clearance_revocation"
            for event in selected_events
        )
        if receipt_status == "recovery_failed":
            incident_state = "recovery_failed"
        elif receipt_status == "starting_state_restored":
            incident_state = "starting_state_restored"
        elif receipt_status != "recovered":
            raise ValueError(
                "manual recovery receipt status is unsupported"
            )
        elif revocation_present:
            incident_state = "recovered_clearance_revoked"
        elif clearance_present:
            incident_state = "recovered_cleared"
        else:
            incident_state = "recovered_clearance_required"

    current_gate = require_mapping(
        timeline["current_gate"],
        name="current_gate",
    )
    if transaction_id in incomplete_transaction_ids:
        gate_relation = "current_incomplete_blocker"
    elif current_gate.get("latest_transaction_id") == transaction_id:
        gate_relation = "current_complete_subject"
    else:
        gate_relation = "historical"

    if gate_relation == "historical":
        normal_write_impact = "historical_only"
    elif current_gate.get("normal_write_allowed") is True:
        normal_write_impact = "current_gate_allows_normal_writes"
    else:
        normal_write_impact = "blocks_current_normal_writes"

    return {
        "incident_state": incident_state,
        "gate_relation": gate_relation,
        "normal_write_impact": normal_write_impact,
        "selected_events": selected_events,
        "event_count": len(selected_events),
        "reason_codes": [
            _INCIDENT_STATE_REASONS[incident_state],
            _GATE_RELATION_REASONS[gate_relation],
        ],
    }


def validate_write_model_configuration_manual_recovery_incident_dossier(
    payload: Mapping[str, Any],
) -> None:
    """Validate one self-contained transaction dossier."""

    dossier = require_mapping(
        payload,
        name="manual recovery incident dossier",
    )
    _exact_fields(
        dossier,
        expected=_FIELDS,
        name="manual recovery incident dossier",
    )
    if dossier.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            "manual recovery incident dossier schema is invalid"
        )
    transaction_id = _transaction_id(dossier.get("transaction_id"))
    source_timeline = require_mapping(
        dossier.get("source_timeline"),
        name="source_timeline",
    )
    validate_write_model_configuration_manual_recovery_audit_timeline(
        source_timeline
    )
    ticker = require_text(
        dossier.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    generated_at = require_text(
        dossier.get("generated_at"),
        name="generated_at",
        maximum_length=64,
    )
    if (
        source_timeline.get("ticker") != ticker
        or source_timeline.get("generated_at") != generated_at
    ):
        raise ValueError(
            "manual recovery incident dossier timeline identity changed"
        )
    source_fingerprint = _validated_fingerprint(
        dossier.get("source_timeline_fingerprint"),
        name="source_timeline_fingerprint",
    )
    if not hmac.compare_digest(
        source_fingerprint,
        str(source_timeline.get("timeline_fingerprint")),
    ):
        raise ValueError(
            "manual recovery incident dossier timeline fingerprint changed"
        )
    derived = _derive_incident(
        source_timeline,
        transaction_id=transaction_id,
    )
    for field_name in (
        "incident_state",
        "gate_relation",
        "normal_write_impact",
        "event_count",
    ):
        if dossier.get(field_name) != derived[field_name]:
            raise ValueError(
                f"manual recovery incident dossier {field_name} is invalid"
            )
    if dossier.get("normal_write_impact") not in _NORMAL_WRITE_IMPACTS:
        raise ValueError(
            "manual recovery incident dossier normal-write impact is invalid"
        )
    for field_name in ("selected_events", "reason_codes"):
        if not hmac.compare_digest(
            canonical_json_str(dossier.get(field_name)),
            canonical_json_str(derived[field_name]),
        ):
            raise ValueError(
                f"manual recovery incident dossier {field_name} is invalid"
            )
    for field_name in (
        "normal_write_authorization_granted",
        "configuration_mutation_performed",
        "approval_consumed",
        "model_execution_performed",
    ):
        if dossier.get(field_name) is not False:
            raise ValueError(
                "manual recovery incident dossier safety evidence is invalid"
            )
    dossier_fingerprint = _validated_fingerprint(
        dossier.get("dossier_fingerprint"),
        name="dossier_fingerprint",
    )
    unsigned_dossier = dict(dossier)
    unsigned_dossier.pop("dossier_fingerprint")
    if not hmac.compare_digest(
        dossier_fingerprint,
        fingerprint_str(unsigned_dossier),
    ):
        raise ValueError(
            "manual recovery incident dossier fingerprint mismatch"
        )


def build_write_model_configuration_manual_recovery_incident_dossier(
    *,
    timeline: Mapping[str, Any],
    transaction_id: str,
) -> dict[str, Any]:
    """Select one transaction from a strict full-history timeline."""

    validate_write_model_configuration_manual_recovery_audit_timeline(
        timeline
    )
    normalized_transaction_id = _transaction_id(transaction_id)
    derived = _derive_incident(
        timeline,
        transaction_id=normalized_transaction_id,
    )
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": timeline["generated_at"],
        "ticker": timeline["ticker"],
        "transaction_id": normalized_transaction_id,
        **derived,
        "source_timeline": deepcopy(dict(timeline)),
        "source_timeline_fingerprint": timeline[
            "timeline_fingerprint"
        ],
        "normal_write_authorization_granted": False,
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    payload["dossier_fingerprint"] = fingerprint_str(payload)
    validate_write_model_configuration_manual_recovery_incident_dossier(
        payload
    )
    return payload


def _assert_immutable_target_not_symlink(target: Path) -> None:
    if target.is_symlink():
        raise FileExistsError(
            "artifact target must not be a symlink: "
            f"{target}"
        )


def _persist_immutable(
    payload: Mapping[str, Any],
    target: Path,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    _assert_immutable_target_not_symlink(target)
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if existing == dict(payload):
            return target
        raise FileExistsError(
            "artifact already exists with different content: "
            f"{target}"
        )
    file_descriptor, temp_path_value = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temp_path = Path(temp_path_value)
    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
        ) as stream:
            file_descriptor = -1
            stream.write(serialize_pretty(payload))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_path, target)
        except FileExistsError:
            _assert_immutable_target_not_symlink(target)
            try:
                existing = json.loads(
                    target.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                existing = None
            if existing != dict(payload):
                raise FileExistsError(
                    "artifact already exists with different content: "
                    f"{target}"
                ) from None
        _assert_immutable_target_not_symlink(target)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return target


def persist_write_model_configuration_manual_recovery_incident_dossier(
    payload: Mapping[str, Any],
    path: str | Path,
    *,
    workspace_dir: str | Path,
    config_root: str | Path,
) -> Path:
    """Immutably export a dossier outside authoritative evidence roots."""

    validate_write_model_configuration_manual_recovery_incident_dossier(
        payload
    )
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise ValueError(
            "manual recovery incident dossier output must not be a symlink"
        )
    lexical_target = candidate.absolute()
    target = candidate.resolve()
    protected_roots = (
        Path(config_root).expanduser().resolve(),
        Path(workspace_dir).expanduser().resolve() / ".dayu",
    )
    if any(
        is_subpath(lexical_target, root)
        or is_subpath(target, root)
        for root in protected_roots
    ):
        raise ValueError(
            "manual recovery incident dossier output must be outside "
            "configuration and authoritative evidence roots"
        )
    return _persist_immutable(payload, target)


def format_write_model_configuration_manual_recovery_incident_dossier_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Render one concise operator-facing incident summary."""

    validate_write_model_configuration_manual_recovery_incident_dossier(
        payload
    )
    source_timeline = require_mapping(
        payload["source_timeline"],
        name="source_timeline",
    )
    current_gate = require_mapping(
        source_timeline["current_gate"],
        name="current_gate",
    )
    event_types = ", ".join(
        str(event["event_type"])
        for event in payload["selected_events"]
    ) or "none"
    reason_codes = ", ".join(payload["reason_codes"])
    return (
        "",
        "=" * 60,
        "Write-model configuration manual recovery incident dossier",
        f"  Generated at  : {payload['generated_at']}",
        f"  Ticker        : {payload['ticker']}",
        f"  Transaction   : {payload['transaction_id']}",
        f"  Incident      : {payload['incident_state']}",
        f"  Gate relation : {payload['gate_relation']}",
        f"  Write impact  : {payload['normal_write_impact']}",
        f"  Current gate  : {current_gate['status']}",
        f"  Events        : {payload['event_count']} ({event_types})",
        f"  Reasons       : {reason_codes}",
        "  Authorization : not granted by dossier",
        "  Configuration : unchanged by dossier",
        "  Approval      : not consumed by dossier",
        "  Model calls   : none",
        f"  Timeline fp   : {payload['source_timeline_fingerprint']}",
        f"  Dossier fp    : {payload['dossier_fingerprint']}",
        "=" * 60,
    )


__all__ = [
    "WriteModelConfigurationManualRecoveryIncidentNotFoundError",
    "build_write_model_configuration_manual_recovery_incident_dossier",
    "format_write_model_configuration_manual_recovery_incident_dossier_report",
    "persist_write_model_configuration_manual_recovery_incident_dossier",
    "validate_write_model_configuration_manual_recovery_incident_dossier",
]
