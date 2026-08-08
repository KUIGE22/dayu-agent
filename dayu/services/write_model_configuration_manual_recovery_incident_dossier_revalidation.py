"""Revalidate one saved manual-recovery incident dossier."""

from __future__ import annotations

import hmac
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dayu.services._write_artifact_utils import (
    bytes_fingerprint,
    canonical_json_str,
    fingerprint_str,
    is_subpath,
    require_mapping,
    serialize_pretty,
)
from dayu.services.write_model_configuration_manual_recovery_clearance import (
    WriteModelConfigurationManualRecoveryAuditTimelineChangedError,
    WriteModelConfigurationManualRecoveryClearanceBusyError,
    build_write_model_configuration_manual_recovery_audit_timeline,
)
from dayu.services.write_model_configuration_manual_recovery_incident_dossier import (
    build_write_model_configuration_manual_recovery_incident_dossier,
    validate_write_model_configuration_manual_recovery_incident_dossier,
)


class WriteModelConfigurationManualRecoveryIncidentDossierChangedError(
    RuntimeError
):
    """Raised when a saved dossier changes during revalidation."""


class WriteModelConfigurationManualRecoveryIncidentDossierEvidenceError(
    RuntimeError
):
    """Raised when fresh evidence cannot form a strict comparison."""


_SCHEMA_VERSION = (
    "write_model_configuration_manual_recovery_incident_dossier_"
    "revalidation_v1"
)
_FIELDS = frozenset(
    {
        "schema_version",
        "revalidated_at",
        "ticker",
        "transaction_id",
        "status",
        "action",
        "source_dossier_path",
        "source_dossier_file_fingerprint",
        "source_dossier",
        "fresh_dossier",
        "saved_incident_state_fingerprint",
        "fresh_incident_state_fingerprint",
        "state_matches",
        "changed_fields",
        "reason_codes",
        "normal_write_authorization_granted",
        "configuration_mutation_performed",
        "approval_consumed",
        "model_execution_performed",
        "revalidation_fingerprint",
    }
)
_ACTIONS = {
    "current": "saved_incident_dossier_matches_current_history",
    "stale": "repeat_incident_dossier_inspection",
}
_REASONS = {
    "current": ["saved_incident_dossier_matches_current_history"],
    "stale": ["current_incident_state_changed_since_saved_dossier"],
}
_STABLE_DOSSIER_FIELDS = (
    "ticker",
    "transaction_id",
    "incident_state",
    "gate_relation",
    "normal_write_impact",
    "selected_events",
    "event_count",
    "reason_codes",
    "normal_write_authorization_granted",
    "configuration_mutation_performed",
    "approval_consumed",
    "model_execution_performed",
)
_VOLATILE_GATE_FIELDS = frozenset(
    {
        "assessed_at",
        "gate_fingerprint",
    }
)
_VOLATILE_TIMELINE_FIELDS = frozenset(
    {
        "generated_at",
        "timeline_fingerprint",
    }
)
_FINGERPRINT_PREFIX = "sha256:"


def _exact_fields(
    value: Mapping[str, Any],
    *,
    expected: frozenset[str],
    name: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"{name} fields are invalid; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _required_text(
    value: object,
    *,
    name: str,
    maximum_length: int,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} is empty")
    if len(normalized) > maximum_length:
        raise ValueError(f"{name} is too long")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{name} contains control characters")
    return normalized


def _parse_utc(value: object, *, name: str) -> datetime:
    normalized = _required_text(
        value,
        name=name,
        maximum_length=64,
    )
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("revalidation time must include a timezone")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validated_fingerprint(value: object, *, name: str) -> str:
    normalized = _required_text(
        value,
        name=name,
        maximum_length=80,
    ).lower()
    digest = normalized.removeprefix(_FINGERPRINT_PREFIX)
    if (
        not normalized.startswith(_FINGERPRINT_PREFIX)
        or len(digest) != 64
        or any(
            character not in "0123456789abcdef"
            for character in digest
        )
    ):
        raise ValueError(f"{name} must be a SHA-256 fingerprint")
    return normalized


def _load_external_dossier(
    path: str | Path,
    *,
    workspace_dir: str | Path,
    config_root: str | Path,
) -> tuple[Path, dict[str, Any], str]:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise FileNotFoundError(
            "manual recovery incident dossier input must not be a "
            f"symlink: {candidate}"
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
            "manual recovery incident dossier input must be outside "
            "configuration and authoritative evidence roots"
        )
    if not target.is_file():
        raise FileNotFoundError(
            "manual recovery incident dossier input does not exist as "
            f"a regular file: {target}"
        )
    raw_payload = target.read_bytes()
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "manual recovery incident dossier input is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            "manual recovery incident dossier input must contain a JSON "
            "object"
        )
    validate_write_model_configuration_manual_recovery_incident_dossier(
        payload
    )
    return target, payload, bytes_fingerprint(raw_payload)


def _stable_dossier_state(dossier: Mapping[str, Any]) -> dict[str, Any]:
    state = {
        field_name: dossier[field_name]
        for field_name in _STABLE_DOSSIER_FIELDS
    }
    state["source_timeline"] = _stable_timeline_state(
        dict(
            require_mapping(
                dossier.get("source_timeline"),
                name="source_timeline",
            )
        )
    )
    return state


def _stable_gate_state(gate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field_name: field_value
        for field_name, field_value in sorted(gate.items())
        if field_name not in _VOLATILE_GATE_FIELDS
    }


def _stable_timeline_state(timeline: Mapping[str, Any]) -> dict[str, Any]:
    state = {
        field_name: field_value
        for field_name, field_value in sorted(timeline.items())
        if field_name
        not in (_VOLATILE_TIMELINE_FIELDS | {"current_gate"})
    }
    state["current_gate"] = _stable_gate_state(
        dict(
            require_mapping(
                timeline.get("current_gate"),
                name="current_gate",
            )
        )
    )
    return state


def _changed_dossier_fields(
    saved_dossier: Mapping[str, Any],
    fresh_dossier: Mapping[str, Any],
) -> list[str]:
    saved_state = _stable_dossier_state(saved_dossier)
    fresh_state = _stable_dossier_state(fresh_dossier)
    if frozenset(saved_state) != frozenset(fresh_state):
        raise ValueError("manual recovery incident dossier schemas differ")
    return sorted(
        field_name
        for field_name in saved_state
        if saved_state[field_name] != fresh_state[field_name]
    )


def _revalidation_payload(
    *,
    revalidated_at: datetime,
    ticker: str,
    source_dossier_path: Path,
    source_dossier_file_fingerprint: str,
    source_dossier: Mapping[str, Any],
    fresh_dossier: Mapping[str, Any],
) -> dict[str, Any]:
    changed_fields = _changed_dossier_fields(
        source_dossier,
        fresh_dossier,
    )
    state_matches = not changed_fields
    status = "current" if state_matches else "stale"
    transaction_id = str(source_dossier["transaction_id"])
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "revalidated_at": _format_utc(revalidated_at),
        "ticker": ticker,
        "transaction_id": transaction_id,
        "status": status,
        "action": _ACTIONS[status],
        "source_dossier_path": str(source_dossier_path.resolve()),
        "source_dossier_file_fingerprint": (
            source_dossier_file_fingerprint
        ),
        "source_dossier": dict(source_dossier),
        "fresh_dossier": dict(fresh_dossier),
        "saved_incident_state_fingerprint": fingerprint_str(
            dict(_stable_dossier_state(source_dossier))
        ),
        "fresh_incident_state_fingerprint": fingerprint_str(
            dict(_stable_dossier_state(fresh_dossier))
        ),
        "state_matches": state_matches,
        "changed_fields": changed_fields,
        "reason_codes": list(_REASONS[status]),
        "normal_write_authorization_granted": False,
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    payload["revalidation_fingerprint"] = fingerprint_str(
        dict(payload)
    )
    validate_write_model_configuration_manual_recovery_incident_dossier_revalidation(
        payload
    )
    return payload


def validate_write_model_configuration_manual_recovery_incident_dossier_revalidation(
    payload: Mapping[str, Any],
) -> None:
    """Validate one self-contained saved-dossier revalidation."""

    revalidation = dict(
        require_mapping(
            payload,
            name="manual recovery incident dossier revalidation",
        )
    )
    _exact_fields(
        revalidation,
        expected=_FIELDS,
        name="manual recovery incident dossier revalidation",
    )
    if revalidation.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(
            "manual recovery incident dossier revalidation schema is "
            "invalid"
        )
    revalidated_at = _parse_utc(
        revalidation.get("revalidated_at"),
        name="revalidated_at",
    )
    ticker = _required_text(
        revalidation.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    transaction_id = _required_text(
        revalidation.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    status = revalidation.get("status")
    if status not in _ACTIONS:
        raise ValueError(
            "manual recovery incident dossier revalidation status is "
            "invalid"
        )
    if revalidation.get("action") != _ACTIONS[str(status)]:
        raise ValueError(
            "manual recovery incident dossier revalidation action is "
            "invalid"
        )
    source_path = Path(
        _required_text(
            revalidation.get("source_dossier_path"),
            name="source_dossier_path",
            maximum_length=32_768,
        )
    )
    if not source_path.is_absolute():
        raise ValueError("source_dossier_path must be absolute")
    _validated_fingerprint(
        revalidation.get("source_dossier_file_fingerprint"),
        name="source_dossier_file_fingerprint",
    )
    source_dossier = dict(
        require_mapping(
            revalidation.get("source_dossier"),
            name="source_dossier",
        )
    )
    fresh_dossier = dict(
        require_mapping(
            revalidation.get("fresh_dossier"),
            name="fresh_dossier",
        )
    )
    validate_write_model_configuration_manual_recovery_incident_dossier(
        source_dossier
    )
    validate_write_model_configuration_manual_recovery_incident_dossier(
        fresh_dossier
    )
    if (
        source_dossier.get("ticker") != ticker
        or fresh_dossier.get("ticker") != ticker
    ):
        raise ValueError(
            "manual recovery incident dossier revalidation ticker is "
            "inconsistent"
        )
    if (
        source_dossier.get("transaction_id") != transaction_id
        or fresh_dossier.get("transaction_id") != transaction_id
    ):
        raise ValueError(
            "manual recovery incident dossier revalidation transaction "
            "identity is inconsistent"
        )
    source_generated_at = _parse_utc(
        source_dossier.get("generated_at"),
        name="source_dossier.generated_at",
    )
    fresh_generated_at = _parse_utc(
        fresh_dossier.get("generated_at"),
        name="fresh_dossier.generated_at",
    )
    if source_generated_at > revalidated_at:
        raise ValueError("source incident dossier was created in the future")
    if fresh_generated_at != revalidated_at:
        raise ValueError(
            "fresh incident dossier generation time is inconsistent"
        )
    expected_changed_fields = _changed_dossier_fields(
        source_dossier,
        fresh_dossier,
    )
    changed_fields = revalidation.get("changed_fields")
    if not isinstance(changed_fields, list):
        raise ValueError(
            "manual recovery incident dossier revalidation changed_fields "
            "must be a list"
        )
    normalized_changed_fields = [
        _required_text(
            value,
            name=f"changed_fields[{index}]",
            maximum_length=128,
        )
        for index, value in enumerate(changed_fields)
    ]
    if normalized_changed_fields != expected_changed_fields:
        raise ValueError(
            "manual recovery incident dossier revalidation changed_fields "
            "are invalid"
        )
    expected_state_matches = not expected_changed_fields
    if revalidation.get("state_matches") is not expected_state_matches:
        raise ValueError(
            "manual recovery incident dossier revalidation state match is "
            "invalid"
        )
    expected_status = "current" if expected_state_matches else "stale"
    if status != expected_status:
        raise ValueError(
            "manual recovery incident dossier revalidation status is "
            "inconsistent"
        )
    if revalidation.get("reason_codes") != _REASONS[expected_status]:
        raise ValueError(
            "manual recovery incident dossier revalidation reason_codes "
            "are invalid"
        )
    saved_state_fingerprint = _validated_fingerprint(
        revalidation.get("saved_incident_state_fingerprint"),
        name="saved_incident_state_fingerprint",
    )
    if not hmac.compare_digest(
        saved_state_fingerprint,
        fingerprint_str(
            dict(_stable_dossier_state(source_dossier))
        ),
    ):
        raise ValueError(
            "saved incident-state fingerprint is inconsistent"
        )
    fresh_state_fingerprint = _validated_fingerprint(
        revalidation.get("fresh_incident_state_fingerprint"),
        name="fresh_incident_state_fingerprint",
    )
    if not hmac.compare_digest(
        fresh_state_fingerprint,
        fingerprint_str(
            dict(_stable_dossier_state(fresh_dossier))
        ),
    ):
        raise ValueError(
            "fresh incident-state fingerprint is inconsistent"
        )
    safety_fields = (
        "normal_write_authorization_granted",
        "configuration_mutation_performed",
        "approval_consumed",
        "model_execution_performed",
    )
    if any(revalidation.get(field_name) is not False for field_name in safety_fields):
        raise ValueError(
            "manual recovery incident dossier revalidation safety evidence "
            "is invalid"
        )
    revalidation_fingerprint = _validated_fingerprint(
        revalidation.get("revalidation_fingerprint"),
        name="revalidation_fingerprint",
    )
    unsigned = dict(revalidation)
    unsigned.pop("revalidation_fingerprint")
    if not hmac.compare_digest(
        revalidation_fingerprint,
        fingerprint_str(dict(unsigned)),
    ):
        raise ValueError(
            "manual recovery incident dossier revalidation fingerprint "
            "mismatch"
        )


def revalidate_write_model_configuration_manual_recovery_incident_dossier(
    *,
    incident_dossier_path: str | Path,
    workspace_dir: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Recheck a saved incident dossier against current strict history."""

    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    current_time = _normalize_now(now if now is not None else datetime.now(UTC))
    (
        source_dossier_path,
        source_dossier,
        source_dossier_file_fingerprint,
    ) = _load_external_dossier(
        incident_dossier_path,
        workspace_dir=workspace_dir,
        config_root=config_root,
    )
    if source_dossier.get("ticker") != normalized_ticker:
        raise ValueError(
            "manual recovery incident dossier input ticker does not match "
            "the command"
        )
    if (
        _parse_utc(
            source_dossier.get("generated_at"),
            name="source_dossier.generated_at",
        )
        > current_time
    ):
        raise ValueError(
            "manual recovery incident dossier input was created in the "
            "future"
        )
    transaction_id = str(source_dossier["transaction_id"])
    try:
        timeline = build_write_model_configuration_manual_recovery_audit_timeline(
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker=normalized_ticker,
            now=current_time,
        )
        fresh_dossier = (
            build_write_model_configuration_manual_recovery_incident_dossier(
                timeline=timeline,
                transaction_id=transaction_id,
            )
        )
    except (
        WriteModelConfigurationManualRecoveryAuditTimelineChangedError,
        WriteModelConfigurationManualRecoveryClearanceBusyError,
    ):
        raise
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise WriteModelConfigurationManualRecoveryIncidentDossierEvidenceError(
            "fresh manual recovery incident evidence is invalid: "
            f"{exc}"
        ) from exc
    try:
        (
            refreshed_source_dossier_path,
            refreshed_source_dossier,
            refreshed_source_dossier_file_fingerprint,
        ) = _load_external_dossier(
            incident_dossier_path,
            workspace_dir=workspace_dir,
            config_root=config_root,
        )
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise WriteModelConfigurationManualRecoveryIncidentDossierChangedError(
            "manual recovery incident dossier input changed during "
            f"revalidation: {exc}"
        ) from exc
    source_changed = (
        refreshed_source_dossier_path != source_dossier_path
        or not hmac.compare_digest(
            refreshed_source_dossier_file_fingerprint,
            source_dossier_file_fingerprint,
        )
        or not hmac.compare_digest(
            canonical_json_str(refreshed_source_dossier),
            canonical_json_str(source_dossier),
        )
    )
    if source_changed:
        raise WriteModelConfigurationManualRecoveryIncidentDossierChangedError(
            "manual recovery incident dossier input changed during "
            "revalidation"
        )
    try:
        return _revalidation_payload(
            revalidated_at=current_time,
            ticker=normalized_ticker,
            source_dossier_path=source_dossier_path,
            source_dossier_file_fingerprint=(
                source_dossier_file_fingerprint
            ),
            source_dossier=source_dossier,
            fresh_dossier=fresh_dossier,
        )
    except (TypeError, ValueError) as exc:
        raise WriteModelConfigurationManualRecoveryIncidentDossierEvidenceError(
            "manual recovery incident dossier revalidation evidence is "
            f"invalid: {exc}"
        ) from exc


def _assert_immutable_target_not_symlink(target: Path) -> None:
    if target.is_symlink():
        raise FileExistsError(
            "artifact target must not be a symlink: "
            f"{target}"
        )


def _persist_immutable(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    target = Path(path).expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    _assert_immutable_target_not_symlink(target)
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            existing = None
        if existing == dict(payload):
            return target.resolve()
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
            except (OSError, UnicodeError, json.JSONDecodeError):
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
    return target.resolve()


def persist_write_model_configuration_manual_recovery_incident_dossier_revalidation(
    payload: Mapping[str, Any],
    path: str | Path,
    *,
    workspace_dir: str | Path,
    config_root: str | Path,
) -> Path:
    """Immutably export one validated incident-dossier revalidation."""

    validate_write_model_configuration_manual_recovery_incident_dossier_revalidation(
        payload
    )
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise ValueError(
            "manual recovery incident dossier revalidation output must "
            "not be a symlink"
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
            "manual recovery incident dossier revalidation output must be "
            "outside configuration and authoritative evidence roots"
        )
    return _persist_immutable(payload, target)


def format_write_model_configuration_manual_recovery_incident_dossier_revalidation_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Render one concise saved-dossier revalidation report."""

    validate_write_model_configuration_manual_recovery_incident_dossier_revalidation(
        payload
    )
    changed_fields = ", ".join(payload["changed_fields"]) or "none"
    source_dossier = dict(
        require_mapping(
            payload["source_dossier"],
            name="source_dossier",
        )
    )
    fresh_dossier = dict(
        require_mapping(
            payload["fresh_dossier"],
            name="fresh_dossier",
        )
    )
    return (
        "",
        "=" * 60,
        "Write-model manual recovery incident dossier revalidation",
        f"  Status        : {payload['status']}",
        f"  Revalidated at: {payload['revalidated_at']}",
        f"  Ticker        : {payload['ticker']}",
        f"  Transaction   : {payload['transaction_id']}",
        f"  Action        : {payload['action']}",
        f"  Saved incident: {source_dossier['incident_state']}",
        f"  Fresh incident: {fresh_dossier['incident_state']}",
        f"  Saved relation: {source_dossier['gate_relation']}",
        f"  Fresh relation: {fresh_dossier['gate_relation']}",
        f"  State matches : {payload['state_matches']}",
        f"  Changed       : {changed_fields}",
        "  Authorization : not granted by revalidation",
        "  Configuration : unchanged by revalidation",
        "  Approval      : not consumed by revalidation",
        "  Model calls   : none",
        f"  Source file fp: {payload['source_dossier_file_fingerprint']}",
        f"  Revalidation  : {payload['revalidation_fingerprint']}",
        "=" * 60,
    )


__all__ = [
    "WriteModelConfigurationManualRecoveryIncidentDossierChangedError",
    "WriteModelConfigurationManualRecoveryIncidentDossierEvidenceError",
    "format_write_model_configuration_manual_recovery_incident_dossier_revalidation_report",
    "persist_write_model_configuration_manual_recovery_incident_dossier_revalidation",
    "revalidate_write_model_configuration_manual_recovery_incident_dossier",
    "validate_write_model_configuration_manual_recovery_incident_dossier_revalidation",
]
