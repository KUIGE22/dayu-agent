"""Issue and enforce durable clearance after manual routing recovery."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import unicodedata
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dayu.services.write_model_configuration_application import (
    create_write_model_configuration_transaction_lock,
)
from dayu.services.write_model_configuration_manual_recovery import (
    load_write_model_configuration_manual_recovery_approval,
    load_write_model_configuration_manual_recovery_plan,
)
from dayu.services.write_model_configuration_manual_recovery_application import (
    load_write_model_configuration_manual_recovery_receipt,
    validate_write_model_configuration_manual_recovery_receipt,
    write_model_configuration_manual_recovery_transaction_root,
)
from dayu.services.write_model_configuration_manual_recovery_verification import (
    verify_write_model_configuration_manual_recovery_receipt,
)
from dayu.services.write_model_configuration_rollback import (
    WriteModelConfigurationRollbackBlockedError,
)
from dayu.services.write_model_configuration_rollback_application import (
    assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current,
    build_write_model_configuration_manual_recovery_evidence,
    load_write_model_configuration_manual_recovery_evidence,
    load_write_model_configuration_operator_rollback_receipt,
    persist_write_model_configuration_manual_recovery_evidence,
    validate_write_model_configuration_manual_recovery_clearance_revocation_lineage,
)


_REQUEST_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_clearance_request_v1"
_REQUEST_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_clearance_request_v2"
_CLEARANCE_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_clearance_v1"
_CLEARANCE_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_clearance_v2"
_REVOCATION_REQUEST_SCHEMA_VERSION = "write_model_configuration_manual_recovery_clearance_revocation_request_v1"
_REVOCATION_SCHEMA_VERSION = "write_model_configuration_manual_recovery_clearance_revocation_v1"
_GATE_SCHEMA_VERSION = "write_model_configuration_manual_recovery_gate_v4"
_GATE_VERIFICATION_SCHEMA_VERSION = (
    "write_model_configuration_manual_recovery_gate_verification_v1"
)
_AUDIT_TIMELINE_SCHEMA_VERSION = (
    "write_model_configuration_manual_recovery_audit_timeline_v1"
)
_CLEARANCE_TYPE = "write_scene_model_routing_manual_recovery"
_REVOCATION_TYPE = "write_scene_model_routing_manual_recovery_clearance_revocation"
_REQUEST_SCOPE = "close_one_verified_manual_recovery_incident"
_CLEARANCE_SCOPE = "one_verified_manual_recovery_incident_for_future_normal_writes"
_REVOCATION_REQUEST_SCOPE = "revoke_one_manual_recovery_clearance_and_block_normal_writes"
_REVOCATION_SCOPE = "immutable_revocation_of_one_manual_recovery_clearance"
_CLEARANCE_STATUS = "cleared"
_REVOCATION_STATUS = "revoked"
_CLEARANCE_ACTION = "allow_future_normal_write_preflight_subject_to_normal_controls"
_REVOCATION_ACTION = "block_future_normal_writes_until_newer_manual_recovery_transaction"
_MAX_REQUEST_AGE = timedelta(hours=4)
_SOURCE_FIELDS = {
    "path",
    "file_fingerprint",
    "content_fingerprint",
}
_REQUEST_FIELDS_V1 = {
    "schema_version",
    "clearance_type",
    "scope",
    "ticker",
    "transaction_id",
    "manual_recovery_receipt_fingerprint",
    "cleared_by",
    "clearance_reference",
    "clearance_reason",
    "cleared_at",
    "acknowledgements",
}
_REQUEST_FIELDS_V2 = _REQUEST_FIELDS_V1 | {"clearance_revocation_lineage"}
_CLEARANCE_FIELDS_V1 = {
    "schema_version",
    "clearance_type",
    "scope",
    "status",
    "action",
    "ticker",
    "transaction_id",
    "manual_recovery_receipt_fingerprint",
    "verified_routing_snapshot_fingerprint",
    "cleared_by",
    "clearance_reference",
    "clearance_reason",
    "cleared_at",
    "issued_at",
    "source_manual_recovery_receipt",
    "source_clearance_request",
    "verification_status",
    "acknowledgements",
    "safety_boundaries",
    "normal_write_clearance_granted",
    "configuration_mutation_performed",
    "approval_consumed",
    "model_execution_performed",
    "clearance_fingerprint",
}
_CLEARANCE_FIELDS_V2 = _CLEARANCE_FIELDS_V1 | {"clearance_revocation_lineage"}
_REVOCATION_REQUEST_FIELDS = {
    "schema_version",
    "revocation_type",
    "scope",
    "ticker",
    "transaction_id",
    "manual_recovery_receipt_fingerprint",
    "manual_recovery_clearance_fingerprint",
    "revoked_by",
    "revocation_reference",
    "revocation_reason",
    "revoked_at",
    "acknowledgements",
}
_REVOCATION_FIELDS = {
    "schema_version",
    "revocation_type",
    "scope",
    "status",
    "action",
    "ticker",
    "transaction_id",
    "manual_recovery_receipt_fingerprint",
    "manual_recovery_clearance_fingerprint",
    "revoked_by",
    "revocation_reference",
    "revocation_reason",
    "revoked_at",
    "issued_at",
    "source_manual_recovery_receipt",
    "source_manual_recovery_clearance",
    "source_revocation_request",
    "acknowledgements",
    "safety_boundaries",
    "normal_write_clearance_revoked",
    "normal_write_allowed",
    "configuration_mutation_performed",
    "approval_consumed",
    "model_execution_performed",
    "revocation_fingerprint",
}
_GATE_FIELDS = {
    "schema_version",
    "assessed_at",
    "ticker",
    "status",
    "action",
    "latest_transaction_id",
    "latest_receipt_status",
    "latest_receipt_fingerprint",
    "clearance_path",
    "clearance_fingerprint",
    "revocation_path",
    "revocation_fingerprint",
    "clearance_required",
    "clearance_present",
    "clearance_revoked",
    "normal_write_allowed",
    "clearance_revocation_lineage",
    "clearance_revocation_lineage_status",
    "reason_codes",
    "configuration_mutation_performed",
    "approval_consumed",
    "model_execution_performed",
    "gate_fingerprint",
}
_GATE_STATE_FIELDS = _GATE_FIELDS - {
    "assessed_at",
    "gate_fingerprint",
}
_GATE_VERIFICATION_FIELDS = {
    "schema_version",
    "verified_at",
    "ticker",
    "status",
    "action",
    "source_gate_path",
    "source_gate_file_fingerprint",
    "source_gate",
    "current_gate",
    "source_state_fingerprint",
    "current_state_fingerprint",
    "state_matches",
    "changed_fields",
    "reason_codes",
    "normal_write_authorization_granted",
    "configuration_mutation_performed",
    "approval_consumed",
    "model_execution_performed",
    "verification_fingerprint",
}
_AUDIT_TIMELINE_ROOT_FIELDS = {
    "transaction_root",
    "clearance_root",
    "revocation_root",
}
_AUDIT_TIMELINE_EVENT_FIELDS = {
    "sequence",
    "event_type",
    "event_at",
    "transaction_id",
    "artifact_path",
    "artifact_file_fingerprint",
    "artifact_content_fingerprint",
    "artifact",
}
_AUDIT_TIMELINE_FIELDS = {
    "schema_version",
    "generated_at",
    "ticker",
    "evidence_roots",
    "current_gate",
    "events",
    "receipt_count",
    "clearance_count",
    "revocation_count",
    "incomplete_transaction_ids",
    "history_complete",
    "normal_write_authorization_granted",
    "configuration_mutation_performed",
    "approval_consumed",
    "model_execution_performed",
    "timeline_fingerprint",
}
_REQUEST_ACKNOWLEDGEMENTS_V1 = [
    "reviewed_manual_recovery_receipt_and_current_verification",
    "recovery_receipt_is_latest_internal_transaction",
    "current_verification_status_is_current",
    "clearance_closes_only_this_recovery_incident",
    "clearance_does_not_modify_configuration",
    "clearance_does_not_consume_approval",
    "clearance_does_not_execute_models",
    "normal_writes_still_require_normal_preflight",
]
_REQUEST_ACKNOWLEDGEMENTS_V2 = [
    *_REQUEST_ACKNOWLEDGEMENTS_V1,
    "reviewed_exact_clearance_revocation_lineage",
]
_REVOCATION_REQUEST_ACKNOWLEDGEMENTS = [
    "reviewed_latest_manual_recovery_receipt_and_clearance",
    "revocation_binds_the_exact_latest_clearance",
    "revocation_immediately_blocks_normal_writes",
    "revocation_cannot_be_removed_for_this_transaction",
    "newer_manual_recovery_transaction_required_for_future_clearance",
    "revocation_does_not_modify_configuration",
    "revocation_does_not_consume_approval",
    "revocation_does_not_execute_models",
]
_SAFETY_BOUNDARIES_V1 = [
    "latest_internal_manual_recovery_receipt_required",
    "recovered_receipt_and_complete_source_chain_required",
    "exact_current_target_bytes_required",
    "fresh_full_runtime_routing_snapshot_required",
    "independent_clearance_operator_required",
    "configuration_transaction_lock_held_during_issuance",
    "clearance_is_immutable_and_bound_to_one_transaction",
    "newer_manual_recovery_transaction_invalidates_older_clearance",
    "normal_write_preflight_and_approvals_still_required",
    "no_configuration_mutation",
    "no_approval_consumption",
    "no_model_execution",
]
_SAFETY_BOUNDARIES_V2 = [
    *_SAFETY_BOUNDARIES_V1,
    "clearance_revocation_lineage_bound_and_current",
]
_REVOCATION_SAFETY_BOUNDARIES = [
    "latest_internal_manual_recovery_receipt_required",
    "latest_valid_internal_clearance_required",
    "exact_receipt_and_clearance_bytes_required",
    "configuration_transaction_lock_held_during_revocation",
    "revocation_is_immutable_and_bound_to_one_transaction",
    "revocation_cannot_be_reversed_for_the_same_transaction",
    "newer_manual_recovery_transaction_supersedes_old_revocation",
    "normal_writes_fail_closed_after_revocation",
    "no_configuration_mutation",
    "no_approval_consumption",
    "no_model_execution",
]
_GATE_STATUSES = {
    "not_required",
    "cleared",
    "clearance_required",
    "clearance_revoked",
    "manual_recovery_required",
}
_GATE_ACTIONS = {
    "not_required": "continue_normal_write_controls",
    "cleared": "continue_normal_write_controls",
    "clearance_required": "block_and_issue_manual_recovery_clearance",
    "clearance_revoked": ("block_and_complete_new_manual_recovery_transaction"),
    "manual_recovery_required": "block_and_resolve_manual_recovery",
}
_GATE_VERIFICATION_ACTIONS = {
    "current": "historical_gate_matches_current_state",
    "stale": "use_current_gate_assessment",
}
_GATE_VERIFICATION_REASONS = {
    "current": ["source_gate_state_matches_current_assessment"],
    "stale": ["source_gate_state_changed"],
}
_RECEIPT_STATUSES = {
    "recovered",
    "starting_state_restored",
    "recovery_failed",
    "incomplete",
}
_AUDIT_EVENT_TYPES: dict[str, dict[str, str | int]] = {
    "manual_recovery_receipt": {
        "timestamp_field": "completed_at",
        "fingerprint_field": "receipt_fingerprint",
        "order": 0,
        "root_field": "transaction_root",
    },
    "manual_recovery_clearance": {
        "timestamp_field": "issued_at",
        "fingerprint_field": "clearance_fingerprint",
        "order": 1,
        "root_field": "clearance_root",
    },
    "manual_recovery_clearance_revocation": {
        "timestamp_field": "issued_at",
        "fingerprint_field": "revocation_fingerprint",
        "order": 2,
        "root_field": "revocation_root",
    },
}

RoutingSnapshotBuilder = Callable[[], Mapping[str, Any]]


class WriteModelConfigurationManualRecoveryClearanceBlockedError(ValueError):
    """Raised when a recovery incident cannot be safely cleared."""


class WriteModelConfigurationManualRecoveryClearanceBusyError(RuntimeError):
    """Raised when another configuration transaction owns the lock."""


class WriteModelConfigurationManualRecoveryClearanceReceiptError(RuntimeError):
    """Raised when an internal clearance cannot be exported."""


class WriteModelConfigurationManualRecoveryGateVerificationChangedError(RuntimeError):
    """Raised when a gate snapshot changes during independent verification."""


class WriteModelConfigurationManualRecoveryGateVerificationEvidenceError(RuntimeError):
    """Raised when current internal gate evidence cannot be assessed."""


class WriteModelConfigurationManualRecoveryAuditTimelineChangedError(RuntimeError):
    """Raised when internal recovery evidence changes during one audit."""


class WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(ValueError):
    """Raised when a recovery clearance cannot be safely revoked."""


class WriteModelConfigurationManualRecoveryClearanceRevocationBusyError(RuntimeError):
    """Raised when another configuration transaction owns the lock."""


class WriteModelConfigurationManualRecoveryClearanceRevocationReceiptError(RuntimeError):
    """Raised when an internal revocation cannot be exported."""


class WriteModelConfigurationManualRecoveryRestartBlockedError(ValueError):
    """Raised when a revoked recovery cannot be safely restarted."""


class WriteModelConfigurationManualRecoveryRestartBusyError(RuntimeError):
    """Raised when another configuration transaction owns the lock."""


class _IncompleteManualRecoveryTransactionsError(WriteModelConfigurationManualRecoveryClearanceBlockedError):
    def __init__(self, transaction_ids: list[str]) -> None:
        self.transaction_ids = tuple(transaction_ids)
        super().__init__("incomplete manual recovery transaction requires resolution: " + ", ".join(transaction_ids))


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


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
        raise ValueError(f"{name} fields are invalid; missing={missing}, extra={extra}")


def _required_text(
    value: object,
    *,
    name: str,
    maximum_length: int,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > maximum_length:
        raise ValueError(f"{name} is too long")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{name} contains control characters")
    return normalized


def _validated_fingerprint(value: object, *, name: str) -> str:
    text = _required_text(value, name=name, maximum_length=80).lower()
    digest = text.removeprefix("sha256:")
    if (
        not text.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a sha256 fingerprint")
    return text


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must include a timezone")
    return value.astimezone(UTC)


def _parse_utc(value: object, *, name: str) -> datetime:
    text = _required_text(value, name=name, maximum_length=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return _normalize_now(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(payload)).hexdigest()}"


def _validate_versioned_clearance_revocation_lineage(
    payload: Mapping[str, Any],
    *,
    schema_version_v1: str,
    schema_version_v2: str,
    fields_v1: set[str],
    fields_v2: set[str],
    name: str,
) -> dict[str, Any] | None:
    schema_version = payload.get("schema_version")
    if schema_version == schema_version_v1:
        _exact_fields(payload, expected=fields_v1, name=name)
        return None
    if schema_version != schema_version_v2:
        raise ValueError(f"{name} schema is invalid")
    _exact_fields(payload, expected=fields_v2, name=name)
    lineage = _mapping(
        payload.get("clearance_revocation_lineage"),
        name=f"{name} clearance_revocation_lineage",
    )
    validate_write_model_configuration_manual_recovery_clearance_revocation_lineage(lineage)
    return dict(lineage)


def _clearance_revocation_lineage(
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    value = payload.get("clearance_revocation_lineage")
    if value is None:
        return None
    lineage = _mapping(value, name="clearance_revocation_lineage")
    validate_write_model_configuration_manual_recovery_clearance_revocation_lineage(lineage)
    return dict(lineage)


def _assert_same_clearance_revocation_lineage(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
    *,
    message: str,
) -> None:
    if left is None and right is None:
        return
    if (
        left is None
        or right is None
        or not hmac.compare_digest(
            _canonical_json(left),
            _canonical_json(right),
        )
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(message)


def _assert_clearance_revocation_lineage_current(
    lineage: Mapping[str, Any] | None,
) -> None:
    if lineage is None:
        return
    try:
        assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current(lineage)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            f"manual recovery clearance revocation lineage is not current: {exc}"
        ) from exc


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _bytes_fingerprint(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _serialize(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def _load_json_object(
    path: str | Path,
    *,
    name: str,
) -> tuple[Path, dict[str, Any]]:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise FileNotFoundError(f"{name} must not be a symlink: {candidate}")
    target = candidate.resolve()
    if not target.is_file():
        raise FileNotFoundError(f"{name} does not exist as a regular file: {target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return target, payload


def _persist_immutable(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    target = Path(path).expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if existing == dict(payload):
            return target
        raise FileExistsError(f"artifact already exists with different content: {target}")
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
            stream.write(_serialize(payload))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_path, target)
        except FileExistsError:
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = None
            if existing != dict(payload):
                raise FileExistsError(f"artifact already exists with different content: {target}") from None
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return target


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _load_external_gate_snapshot(
    path: str | Path,
    *,
    config_root: str | Path,
) -> tuple[Path, dict[str, Any], str]:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise FileNotFoundError(
            f"manual recovery gate input must not be a symlink: {candidate}"
        )
    lexical_target = candidate.absolute()
    target = candidate.resolve()
    resolved_config_root = Path(config_root).expanduser().resolve()
    if _is_relative_to(lexical_target, resolved_config_root) or _is_relative_to(
        target,
        resolved_config_root,
    ):
        raise ValueError(
            "manual recovery gate input must be outside the configuration root"
        )
    if not target.is_file():
        raise FileNotFoundError(
            "manual recovery gate input does not exist as a regular file: "
            f"{target}"
        )
    raw_payload = target.read_bytes()
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "manual recovery gate input is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            "manual recovery gate input must contain a JSON object"
        )
    validate_write_model_configuration_manual_recovery_gate(payload)
    return target, payload, _bytes_fingerprint(raw_payload)


def _gate_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field_name: payload[field_name]
        for field_name in sorted(_GATE_STATE_FIELDS)
    }


def _changed_gate_state_fields(
    source_gate: Mapping[str, Any],
    current_gate: Mapping[str, Any],
) -> list[str]:
    return sorted(
        field_name
        for field_name in _GATE_STATE_FIELDS
        if source_gate[field_name] != current_gate[field_name]
    )


def _assert_internal_path_components_safe(
    *,
    workspace_dir: str | Path,
    target: Path,
) -> None:
    workspace = Path(workspace_dir).expanduser().resolve()
    try:
        relative = target.relative_to(workspace)
    except ValueError as exc:
        raise (
            WriteModelConfigurationManualRecoveryClearanceBlockedError(
                "internal manual recovery artifact escaped the workspace"
            )
        ) from exc
    current = workspace
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError(
                    "internal manual recovery artifact path contains a symlink"
                )
            )


def _validate_source(value: object, *, name: str) -> dict[str, str]:
    source = _mapping(value, name=name)
    _exact_fields(source, expected=_SOURCE_FIELDS, name=name)
    path = Path(
        _required_text(
            source.get("path"),
            name=f"{name}.path",
            maximum_length=32_768,
        )
    ).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name}.path must be absolute")
    return {
        "path": str(path.resolve()),
        "file_fingerprint": _validated_fingerprint(
            source.get("file_fingerprint"),
            name=f"{name}.file_fingerprint",
        ),
        "content_fingerprint": _validated_fingerprint(
            source.get("content_fingerprint"),
            name=f"{name}.content_fingerprint",
        ),
    }


def _source_reference(
    *,
    path: Path,
    content_fingerprint: str,
) -> dict[str, str]:
    return {
        "path": str(path.resolve()),
        "file_fingerprint": _file_fingerprint(path),
        "content_fingerprint": content_fingerprint,
    }


def validate_write_model_configuration_manual_recovery_clearance_request(
    payload: Mapping[str, Any],
) -> None:
    """Validate an explicit human request to close one recovery incident."""

    request = _mapping(payload, name="manual recovery clearance request")
    lineage = _validate_versioned_clearance_revocation_lineage(
        request,
        schema_version_v1=_REQUEST_SCHEMA_VERSION_V1,
        schema_version_v2=_REQUEST_SCHEMA_VERSION_V2,
        fields_v1=_REQUEST_FIELDS_V1,
        fields_v2=_REQUEST_FIELDS_V2,
        name="manual recovery clearance request",
    )
    constants = {
        "clearance_type": _CLEARANCE_TYPE,
        "scope": _REQUEST_SCOPE,
    }
    for field_name, expected_value in constants.items():
        if request.get(field_name) != expected_value:
            raise ValueError(f"manual recovery clearance request {field_name} is invalid")
    _required_text(
        request.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    _required_text(
        request.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    _validated_fingerprint(
        request.get("manual_recovery_receipt_fingerprint"),
        name="manual_recovery_receipt_fingerprint",
    )
    _required_text(
        request.get("cleared_by"),
        name="cleared_by",
        maximum_length=200,
    )
    _required_text(
        request.get("clearance_reference"),
        name="clearance_reference",
        maximum_length=500,
    )
    _required_text(
        request.get("clearance_reason"),
        name="clearance_reason",
        maximum_length=2_000,
    )
    _parse_utc(request.get("cleared_at"), name="cleared_at")
    expected_acknowledgements = _REQUEST_ACKNOWLEDGEMENTS_V2 if lineage is not None else _REQUEST_ACKNOWLEDGEMENTS_V1
    if request.get("acknowledgements") != expected_acknowledgements:
        raise ValueError("manual recovery clearance acknowledgements are invalid")


def load_write_model_configuration_manual_recovery_clearance_request(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load one explicit manual-recovery clearance request."""

    target, payload = _load_json_object(
        path,
        name="manual recovery clearance request",
    )
    validate_write_model_configuration_manual_recovery_clearance_request(payload)
    return target, payload


def validate_write_model_configuration_manual_recovery_clearance(
    payload: Mapping[str, Any],
) -> None:
    """Validate one immutable recovery clearance."""

    clearance = _mapping(payload, name="manual recovery clearance")
    lineage = _validate_versioned_clearance_revocation_lineage(
        clearance,
        schema_version_v1=_CLEARANCE_SCHEMA_VERSION_V1,
        schema_version_v2=_CLEARANCE_SCHEMA_VERSION_V2,
        fields_v1=_CLEARANCE_FIELDS_V1,
        fields_v2=_CLEARANCE_FIELDS_V2,
        name="manual recovery clearance",
    )
    constants = {
        "clearance_type": _CLEARANCE_TYPE,
        "scope": _CLEARANCE_SCOPE,
        "status": _CLEARANCE_STATUS,
        "action": _CLEARANCE_ACTION,
        "verification_status": "current",
    }
    for field_name, expected_value in constants.items():
        if clearance.get(field_name) != expected_value:
            raise ValueError(f"manual recovery clearance {field_name} is invalid")
    for field_name, maximum_length in (
        ("ticker", 64),
        ("transaction_id", 64),
        ("cleared_by", 200),
        ("clearance_reference", 500),
        ("clearance_reason", 2_000),
    ):
        _required_text(
            clearance.get(field_name),
            name=field_name,
            maximum_length=maximum_length,
        )
    for field_name in (
        "manual_recovery_receipt_fingerprint",
        "verified_routing_snapshot_fingerprint",
    ):
        _validated_fingerprint(
            clearance.get(field_name),
            name=field_name,
        )
    cleared_at = _parse_utc(
        clearance.get("cleared_at"),
        name="cleared_at",
    )
    issued_at = _parse_utc(
        clearance.get("issued_at"),
        name="issued_at",
    )
    if issued_at < cleared_at:
        raise ValueError("manual recovery clearance cannot predate its request")
    receipt_source = _validate_source(
        clearance.get("source_manual_recovery_receipt"),
        name="source_manual_recovery_receipt",
    )
    if not hmac.compare_digest(
        receipt_source["content_fingerprint"],
        str(clearance["manual_recovery_receipt_fingerprint"]),
    ):
        raise ValueError("manual recovery clearance receipt identity changed")
    _validate_source(
        clearance.get("source_clearance_request"),
        name="source_clearance_request",
    )
    expected_acknowledgements = _REQUEST_ACKNOWLEDGEMENTS_V2 if lineage is not None else _REQUEST_ACKNOWLEDGEMENTS_V1
    if clearance.get("acknowledgements") != expected_acknowledgements:
        raise ValueError("manual recovery clearance acknowledgements are invalid")
    expected_safety_boundaries = _SAFETY_BOUNDARIES_V2 if lineage is not None else _SAFETY_BOUNDARIES_V1
    if clearance.get("safety_boundaries") != expected_safety_boundaries:
        raise ValueError("manual recovery clearance safety boundaries are invalid")
    expected_flags = {
        "normal_write_clearance_granted": True,
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    if any(clearance.get(field_name) is not expected_value for field_name, expected_value in expected_flags.items()):
        raise ValueError("manual recovery clearance safety evidence is invalid")
    fingerprint = _validated_fingerprint(
        clearance.get("clearance_fingerprint"),
        name="clearance_fingerprint",
    )
    unsigned = dict(clearance)
    unsigned.pop("clearance_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("manual recovery clearance fingerprint mismatch")


def load_write_model_configuration_manual_recovery_clearance(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load one immutable recovery clearance."""

    target, payload = _load_json_object(
        path,
        name="manual recovery clearance",
    )
    validate_write_model_configuration_manual_recovery_clearance(payload)
    return target, payload


def validate_write_model_configuration_manual_recovery_clearance_revocation_request(
    payload: Mapping[str, Any],
) -> None:
    """Validate an explicit request to revoke one recovery clearance."""

    request = _mapping(
        payload,
        name="manual recovery clearance revocation request",
    )
    _exact_fields(
        request,
        expected=_REVOCATION_REQUEST_FIELDS,
        name="manual recovery clearance revocation request",
    )
    constants = {
        "schema_version": _REVOCATION_REQUEST_SCHEMA_VERSION,
        "revocation_type": _REVOCATION_TYPE,
        "scope": _REVOCATION_REQUEST_SCOPE,
    }
    for field_name, expected_value in constants.items():
        if request.get(field_name) != expected_value:
            raise ValueError(f"manual recovery clearance revocation request {field_name} is invalid")
    for field_name, maximum_length in (
        ("ticker", 64),
        ("transaction_id", 64),
        ("revoked_by", 200),
        ("revocation_reference", 500),
        ("revocation_reason", 2_000),
    ):
        _required_text(
            request.get(field_name),
            name=field_name,
            maximum_length=maximum_length,
        )
    for field_name in (
        "manual_recovery_receipt_fingerprint",
        "manual_recovery_clearance_fingerprint",
    ):
        _validated_fingerprint(
            request.get(field_name),
            name=field_name,
        )
    _parse_utc(request.get("revoked_at"), name="revoked_at")
    if request.get("acknowledgements") != _REVOCATION_REQUEST_ACKNOWLEDGEMENTS:
        raise ValueError("manual recovery clearance revocation acknowledgements are invalid")


def load_write_model_configuration_manual_recovery_clearance_revocation_request(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load one explicit recovery-clearance revocation request."""

    target, payload = _load_json_object(
        path,
        name="manual recovery clearance revocation request",
    )
    validate_write_model_configuration_manual_recovery_clearance_revocation_request(payload)
    return target, payload


def validate_write_model_configuration_manual_recovery_clearance_revocation(
    payload: Mapping[str, Any],
) -> None:
    """Validate one immutable recovery-clearance revocation."""

    revocation = _mapping(
        payload,
        name="manual recovery clearance revocation",
    )
    _exact_fields(
        revocation,
        expected=_REVOCATION_FIELDS,
        name="manual recovery clearance revocation",
    )
    constants = {
        "schema_version": _REVOCATION_SCHEMA_VERSION,
        "revocation_type": _REVOCATION_TYPE,
        "scope": _REVOCATION_SCOPE,
        "status": _REVOCATION_STATUS,
        "action": _REVOCATION_ACTION,
    }
    for field_name, expected_value in constants.items():
        if revocation.get(field_name) != expected_value:
            raise ValueError(f"manual recovery clearance revocation {field_name} is invalid")
    for field_name, maximum_length in (
        ("ticker", 64),
        ("transaction_id", 64),
        ("revoked_by", 200),
        ("revocation_reference", 500),
        ("revocation_reason", 2_000),
    ):
        _required_text(
            revocation.get(field_name),
            name=field_name,
            maximum_length=maximum_length,
        )
    for field_name in (
        "manual_recovery_receipt_fingerprint",
        "manual_recovery_clearance_fingerprint",
    ):
        _validated_fingerprint(
            revocation.get(field_name),
            name=field_name,
        )
    revoked_at = _parse_utc(
        revocation.get("revoked_at"),
        name="revoked_at",
    )
    issued_at = _parse_utc(
        revocation.get("issued_at"),
        name="issued_at",
    )
    if issued_at < revoked_at:
        raise ValueError("manual recovery clearance revocation cannot predate its request")
    receipt_source = _validate_source(
        revocation.get("source_manual_recovery_receipt"),
        name="source_manual_recovery_receipt",
    )
    clearance_source = _validate_source(
        revocation.get("source_manual_recovery_clearance"),
        name="source_manual_recovery_clearance",
    )
    _validate_source(
        revocation.get("source_revocation_request"),
        name="source_revocation_request",
    )
    if not hmac.compare_digest(
        receipt_source["content_fingerprint"],
        str(revocation["manual_recovery_receipt_fingerprint"]),
    ):
        raise ValueError("manual recovery clearance revocation receipt identity changed")
    if not hmac.compare_digest(
        clearance_source["content_fingerprint"],
        str(revocation["manual_recovery_clearance_fingerprint"]),
    ):
        raise ValueError("manual recovery clearance revocation clearance identity changed")
    if revocation.get("acknowledgements") != _REVOCATION_REQUEST_ACKNOWLEDGEMENTS:
        raise ValueError("manual recovery clearance revocation acknowledgements are invalid")
    if revocation.get("safety_boundaries") != _REVOCATION_SAFETY_BOUNDARIES:
        raise ValueError("manual recovery clearance revocation safety boundaries are invalid")
    expected_flags = {
        "normal_write_clearance_revoked": True,
        "normal_write_allowed": False,
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    if any(revocation.get(field_name) is not expected_value for field_name, expected_value in expected_flags.items()):
        raise ValueError("manual recovery clearance revocation safety evidence is invalid")
    fingerprint = _validated_fingerprint(
        revocation.get("revocation_fingerprint"),
        name="revocation_fingerprint",
    )
    unsigned = dict(revocation)
    unsigned.pop("revocation_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("manual recovery clearance revocation fingerprint mismatch")


def load_write_model_configuration_manual_recovery_clearance_revocation(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load one immutable recovery-clearance revocation."""

    target, payload = _load_json_object(
        path,
        name="manual recovery clearance revocation",
    )
    validate_write_model_configuration_manual_recovery_clearance_revocation(payload)
    return target, payload


def write_model_configuration_manual_recovery_clearance_root(
    *,
    workspace_dir: str | Path,
) -> Path:
    """Return the authoritative internal recovery-clearance root."""

    return Path(workspace_dir).expanduser().resolve() / ".dayu" / "write-model-configuration-manual-recovery-clearances"


def write_model_configuration_manual_recovery_clearance_revocation_root(
    *,
    workspace_dir: str | Path,
) -> Path:
    """Return the authoritative internal clearance-revocation root."""

    return (
        Path(workspace_dir).expanduser().resolve()
        / ".dayu"
        / ("write-model-configuration-manual-recovery-clearance-revocations")
    )


def _internal_clearance_path(
    *,
    workspace_dir: str | Path,
    transaction_id: str,
) -> Path:
    return (
        write_model_configuration_manual_recovery_clearance_root(workspace_dir=workspace_dir) / f"{transaction_id}.json"
    )


def _internal_clearance_revocation_path(
    *,
    workspace_dir: str | Path,
    transaction_id: str,
) -> Path:
    return (
        write_model_configuration_manual_recovery_clearance_revocation_root(workspace_dir=workspace_dir)
        / f"{transaction_id}.json"
    )


def _load_internal_audit_artifact(
    path: Path,
    *,
    name: str,
    validator: Callable[[Mapping[str, Any]], None],
) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            f"{name} is unsafe"
        )
    try:
        raw_payload = path.read_bytes()
    except OSError as exc:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            f"{name} cannot be read"
        ) from exc
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            f"{name} is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            f"{name} must contain a JSON object"
        )
    try:
        validator(payload)
    except (TypeError, ValueError) as exc:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            f"{name} is invalid: {exc}"
        ) from exc
    return payload, _bytes_fingerprint(raw_payload)


def _audit_timeline_event(
    *,
    event_type: str,
    artifact_path: Path,
    artifact_file_fingerprint: str,
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    metadata = _AUDIT_EVENT_TYPES[event_type]
    timestamp_field = str(metadata["timestamp_field"])
    fingerprint_field = str(metadata["fingerprint_field"])
    return {
        "sequence": 0,
        "event_type": event_type,
        "event_at": artifact[timestamp_field],
        "transaction_id": artifact["transaction_id"],
        "artifact_path": str(artifact_path.resolve()),
        "artifact_file_fingerprint": artifact_file_fingerprint,
        "artifact_content_fingerprint": artifact[fingerprint_field],
        "artifact": dict(artifact),
    }


def _audit_internal_receipt_events(
    *,
    workspace_dir: str | Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    root = write_model_configuration_manual_recovery_transaction_root(
        workspace_dir=workspace_dir
    )
    _assert_internal_path_components_safe(
        workspace_dir=workspace_dir,
        target=root,
    )
    if not root.exists():
        return [], []
    if root.is_symlink() or not root.is_dir():
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery transaction root is unsafe"
        )
    events: list[dict[str, Any]] = []
    incomplete_transaction_ids: list[str] = []
    for transaction_dir in sorted(root.iterdir(), key=lambda item: item.name):
        if transaction_dir.is_symlink() or not transaction_dir.is_dir():
            raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
                "manual recovery transaction root contains an unsafe entry"
            )
        transaction_id = _required_text(
            transaction_dir.name,
            name="manual recovery transaction directory",
            maximum_length=64,
        )
        if transaction_id != transaction_dir.name:
            raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
                "manual recovery transaction directory identity is invalid"
            )
        receipt_path = transaction_dir / "receipt.json"
        if not receipt_path.exists():
            incomplete_transaction_ids.append(transaction_id)
            continue
        receipt, file_fingerprint = _load_internal_audit_artifact(
            receipt_path,
            name="manual recovery transaction receipt",
            validator=validate_write_model_configuration_manual_recovery_receipt,
        )
        if receipt.get("transaction_id") != transaction_id:
            raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
                "manual recovery transaction directory identity changed"
            )
        events.append(
            _audit_timeline_event(
                event_type="manual_recovery_receipt",
                artifact_path=receipt_path,
                artifact_file_fingerprint=file_fingerprint,
                artifact=receipt,
            )
        )
    return events, incomplete_transaction_ids


def _audit_internal_flat_artifact_events(
    *,
    workspace_dir: str | Path,
    root: Path,
    artifact_name: str,
    event_type: str,
    validator: Callable[[Mapping[str, Any]], None],
) -> list[dict[str, Any]]:
    _assert_internal_path_components_safe(
        workspace_dir=workspace_dir,
        target=root,
    )
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            f"{artifact_name} root is unsafe"
        )
    events: list[dict[str, Any]] = []
    for artifact_path in sorted(root.iterdir(), key=lambda item: item.name):
        if (
            artifact_path.is_symlink()
            or not artifact_path.is_file()
            or artifact_path.suffix != ".json"
        ):
            raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
                f"{artifact_name} root contains an unsafe entry"
            )
        artifact, file_fingerprint = _load_internal_audit_artifact(
            artifact_path,
            name=artifact_name,
            validator=validator,
        )
        transaction_id = _required_text(
            artifact.get("transaction_id"),
            name=f"{artifact_name}.transaction_id",
            maximum_length=64,
        )
        if artifact_path.name != f"{transaction_id}.json":
            raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
                f"{artifact_name} file identity changed"
            )
        events.append(
            _audit_timeline_event(
                event_type=event_type,
                artifact_path=artifact_path,
                artifact_file_fingerprint=file_fingerprint,
                artifact=artifact,
            )
        )
    return events


def _internal_manual_recovery_audit_state(
    *,
    workspace_dir: str | Path,
) -> dict[str, Any]:
    transaction_root = (
        write_model_configuration_manual_recovery_transaction_root(
            workspace_dir=workspace_dir
        )
    )
    clearance_root = write_model_configuration_manual_recovery_clearance_root(
        workspace_dir=workspace_dir
    )
    revocation_root = (
        write_model_configuration_manual_recovery_clearance_revocation_root(
            workspace_dir=workspace_dir
        )
    )
    receipt_events, incomplete_transaction_ids = (
        _audit_internal_receipt_events(workspace_dir=workspace_dir)
    )
    clearance_events = _audit_internal_flat_artifact_events(
        workspace_dir=workspace_dir,
        root=clearance_root,
        artifact_name="manual recovery clearance",
        event_type="manual_recovery_clearance",
        validator=validate_write_model_configuration_manual_recovery_clearance,
    )
    revocation_events = _audit_internal_flat_artifact_events(
        workspace_dir=workspace_dir,
        root=revocation_root,
        artifact_name="manual recovery clearance revocation",
        event_type="manual_recovery_clearance_revocation",
        validator=validate_write_model_configuration_manual_recovery_clearance_revocation,
    )
    events = sorted(
        [*receipt_events, *clearance_events, *revocation_events],
        key=lambda event: (
            _parse_utc(event["event_at"], name="event_at"),
            int(_AUDIT_EVENT_TYPES[str(event["event_type"])]["order"]),
            str(event["transaction_id"]),
        ),
    )
    for sequence, event in enumerate(events, start=1):
        event["sequence"] = sequence
    return {
        "evidence_roots": {
            "transaction_root": str(transaction_root.resolve()),
            "clearance_root": str(clearance_root.resolve()),
            "revocation_root": str(revocation_root.resolve()),
        },
        "events": events,
        "incomplete_transaction_ids": sorted(
            incomplete_transaction_ids
        ),
    }


def _internal_receipts(
    *,
    workspace_dir: str | Path,
) -> tuple[list[tuple[datetime, Path, dict[str, Any]]], list[str]]:
    root = write_model_configuration_manual_recovery_transaction_root(workspace_dir=workspace_dir)
    _assert_internal_path_components_safe(
        workspace_dir=workspace_dir,
        target=root,
    )
    if not root.exists():
        return [], []
    if root.is_symlink() or not root.is_dir():
        raise (WriteModelConfigurationManualRecoveryClearanceBlockedError("manual recovery transaction root is unsafe"))
    receipts: list[tuple[datetime, Path, dict[str, Any]]] = []
    incomplete: list[str] = []
    for transaction_dir in sorted(root.iterdir(), key=lambda item: item.name):
        if transaction_dir.is_symlink() or not transaction_dir.is_dir():
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError(
                    "manual recovery transaction root contains an unsafe entry"
                )
            )
        receipt_path = transaction_dir / "receipt.json"
        if not receipt_path.exists():
            incomplete.append(transaction_dir.name)
            continue
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError(
                    "manual recovery transaction receipt is unsafe"
                )
            )
        _resolved, receipt = load_write_model_configuration_manual_recovery_receipt(receipt_path)
        if receipt.get("transaction_id") != transaction_dir.name:
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError(
                    "manual recovery transaction directory identity changed"
                )
            )
        receipts.append(
            (
                _parse_utc(
                    receipt.get("completed_at"),
                    name="receipt.completed_at",
                ),
                receipt_path.resolve(),
                receipt,
            )
        )
    return receipts, incomplete


def _latest_internal_receipt(
    *,
    workspace_dir: str | Path,
) -> tuple[Path, dict[str, Any]] | None:
    receipts, incomplete = _internal_receipts(workspace_dir=workspace_dir)
    if incomplete:
        raise _IncompleteManualRecoveryTransactionsError(incomplete)
    if not receipts:
        return None
    _completed_at, path, receipt = max(
        receipts,
        key=lambda item: (item[0], str(item[2]["transaction_id"])),
    )
    return path, receipt


def _assert_receipt_is_latest(
    *,
    supplied_receipt_path: Path,
    supplied_receipt: Mapping[str, Any],
    latest_receipt_path: Path,
    latest_receipt: Mapping[str, Any],
) -> None:
    if (
        supplied_receipt.get("transaction_id") != latest_receipt.get("transaction_id")
        or not hmac.compare_digest(
            str(supplied_receipt.get("receipt_fingerprint")),
            str(latest_receipt.get("receipt_fingerprint")),
        )
        or not hmac.compare_digest(
            _file_fingerprint(supplied_receipt_path),
            _file_fingerprint(latest_receipt_path),
        )
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance requires the latest exact internal receipt"
        )


def _assert_request_identity(
    *,
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
    expected_ticker: str,
    now: datetime,
    require_current_request: bool,
) -> None:
    expected = {
        "ticker": expected_ticker,
        "transaction_id": receipt["transaction_id"],
        "manual_recovery_receipt_fingerprint": receipt["receipt_fingerprint"],
    }
    if any(request.get(field_name) != expected_value for field_name, expected_value in expected.items()):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance request identity changed"
        )
    receipt_lineage = _clearance_revocation_lineage(receipt)
    _assert_same_clearance_revocation_lineage(
        receipt_lineage,
        _clearance_revocation_lineage(request),
        message="manual recovery clearance request lineage does not match the receipt",
    )
    _assert_clearance_revocation_lineage_current(receipt_lineage)
    completed_at = _parse_utc(
        receipt.get("completed_at"),
        name="receipt.completed_at",
    )
    cleared_at = _parse_utc(
        request.get("cleared_at"),
        name="cleared_at",
    )
    if cleared_at <= completed_at:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance must follow the recovery receipt"
        )
    if require_current_request and cleared_at > now:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance is not effective yet"
        )
    if require_current_request and now - cleared_at > _MAX_REQUEST_AGE:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance request is older than four hours"
        )


def _load_bound_operator_source(
    *,
    receipt: Mapping[str, Any],
    field_name: str,
    fingerprint_field: str,
    loader: Callable[[str | Path], tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    source = _validate_source(receipt.get(field_name), name=field_name)
    source_path = Path(source["path"])
    loaded_path, payload = loader(source_path)
    try:
        file_fingerprint = _file_fingerprint(loaded_path)
    except OSError as exc:
        raise (
            WriteModelConfigurationManualRecoveryClearanceBlockedError(f"{field_name} source cannot be read")
        ) from exc
    if (
        loaded_path != source_path
        or not hmac.compare_digest(
            source["file_fingerprint"],
            file_fingerprint,
        )
        or not hmac.compare_digest(
            source["content_fingerprint"],
            _validated_fingerprint(
                payload.get(fingerprint_field),
                name=f"{field_name}.{fingerprint_field}",
            ),
        )
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(f"{field_name} source identity changed")
    return payload


def _assert_independent_operator(
    *,
    receipt: Mapping[str, Any],
    request: Mapping[str, Any],
) -> None:
    plan = _load_bound_operator_source(
        receipt=receipt,
        field_name="source_manual_recovery_plan",
        fingerprint_field="plan_fingerprint",
        loader=load_write_model_configuration_manual_recovery_plan,
    )
    approval = _load_bound_operator_source(
        receipt=receipt,
        field_name="source_manual_recovery_approval",
        fingerprint_field="approval_fingerprint",
        loader=load_write_model_configuration_manual_recovery_approval,
    )
    cleared_by = _required_text(
        request.get("cleared_by"),
        name="cleared_by",
        maximum_length=200,
    )
    prior_operators = {
        _required_text(
            plan.get("selected_by"),
            name="selected_by",
            maximum_length=200,
        ).casefold(),
        _required_text(
            approval.get("approved_by"),
            name="approved_by",
            maximum_length=200,
        ).casefold(),
    }
    if cleared_by.casefold() in prior_operators:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance operator must differ from the state selector and recovery approver"
        )


def _build_clearance(
    *,
    request_path: Path,
    request: Mapping[str, Any],
    receipt_path: Path,
    receipt: Mapping[str, Any],
    verification: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    lineage = _clearance_revocation_lineage(receipt)
    _assert_same_clearance_revocation_lineage(
        lineage,
        _clearance_revocation_lineage(request),
        message="manual recovery clearance request lineage does not match the receipt",
    )
    _assert_same_clearance_revocation_lineage(
        lineage,
        _clearance_revocation_lineage(verification),
        message="manual recovery clearance verification lineage does not match the receipt",
    )
    schema_version = _CLEARANCE_SCHEMA_VERSION_V2 if lineage is not None else _CLEARANCE_SCHEMA_VERSION_V1
    acknowledgements = _REQUEST_ACKNOWLEDGEMENTS_V2 if lineage is not None else _REQUEST_ACKNOWLEDGEMENTS_V1
    safety_boundaries = _SAFETY_BOUNDARIES_V2 if lineage is not None else _SAFETY_BOUNDARIES_V1
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "clearance_type": _CLEARANCE_TYPE,
        "scope": _CLEARANCE_SCOPE,
        "status": _CLEARANCE_STATUS,
        "action": _CLEARANCE_ACTION,
        "ticker": receipt["ticker"],
        "transaction_id": receipt["transaction_id"],
        "manual_recovery_receipt_fingerprint": receipt["receipt_fingerprint"],
        "verified_routing_snapshot_fingerprint": verification["current_routing_snapshot_fingerprint"],
        "cleared_by": request["cleared_by"],
        "clearance_reference": request["clearance_reference"],
        "clearance_reason": request["clearance_reason"],
        "cleared_at": request["cleared_at"],
        "issued_at": _format_utc(now),
        "source_manual_recovery_receipt": _source_reference(
            path=receipt_path,
            content_fingerprint=str(receipt["receipt_fingerprint"]),
        ),
        "source_clearance_request": _source_reference(
            path=request_path,
            content_fingerprint=_fingerprint(request),
        ),
        "verification_status": "current",
        "acknowledgements": list(acknowledgements),
        "safety_boundaries": list(safety_boundaries),
        "normal_write_clearance_granted": True,
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    if lineage is not None:
        payload["clearance_revocation_lineage"] = dict(lineage)
    payload["clearance_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_manual_recovery_clearance(payload)
    return payload


def _assert_existing_clearance_identity(
    *,
    clearance: Mapping[str, Any],
    request_path: Path,
    request: Mapping[str, Any],
    receipt_path: Path,
    receipt: Mapping[str, Any],
) -> None:
    receipt_lineage = _clearance_revocation_lineage(receipt)
    _assert_same_clearance_revocation_lineage(
        receipt_lineage,
        _clearance_revocation_lineage(request),
        message="existing manual recovery clearance request lineage changed",
    )
    _assert_same_clearance_revocation_lineage(
        receipt_lineage,
        _clearance_revocation_lineage(clearance),
        message="existing manual recovery clearance lineage changed",
    )
    _assert_clearance_revocation_lineage_current(receipt_lineage)
    request_source = _validate_source(
        clearance.get("source_clearance_request"),
        name="source_clearance_request",
    )
    receipt_source = _validate_source(
        clearance.get("source_manual_recovery_receipt"),
        name="source_manual_recovery_receipt",
    )
    expected = {
        "ticker": receipt["ticker"],
        "transaction_id": receipt["transaction_id"],
        "manual_recovery_receipt_fingerprint": receipt["receipt_fingerprint"],
        "cleared_by": request["cleared_by"],
        "clearance_reference": request["clearance_reference"],
        "clearance_reason": request["clearance_reason"],
        "cleared_at": request["cleared_at"],
    }
    if any(clearance.get(field_name) != expected_value for field_name, expected_value in expected.items()):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "existing manual recovery clearance has another identity"
        )
    if (
        Path(request_source["path"]) != request_path
        or not hmac.compare_digest(
            request_source["file_fingerprint"],
            _file_fingerprint(request_path),
        )
        or not hmac.compare_digest(
            request_source["content_fingerprint"],
            _fingerprint(request),
        )
        or Path(receipt_source["path"]) != receipt_path
        or not hmac.compare_digest(
            receipt_source["file_fingerprint"],
            _file_fingerprint(receipt_path),
        )
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "existing manual recovery clearance source changed"
        )


def issue_write_model_configuration_manual_recovery_clearance(
    *,
    clearance_request_path: str | Path,
    manual_recovery_receipt_path: str | Path,
    workspace_dir: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    clearance_output_path: str | Path,
    snapshot_builder: RoutingSnapshotBuilder,
    now: datetime,
) -> dict[str, Any]:
    """Verify and immutably clear the latest recovered incident."""

    current_time = _normalize_now(now)
    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    request_path, request = load_write_model_configuration_manual_recovery_clearance_request(clearance_request_path)
    supplied_receipt_path, supplied_receipt = load_write_model_configuration_manual_recovery_receipt(
        manual_recovery_receipt_path
    )
    resolved_config_root = Path(config_root).expanduser().resolve()
    external_clearance_path = Path(clearance_output_path).expanduser().resolve()
    internal_clearance_path = _internal_clearance_path(
        workspace_dir=workspace_dir,
        transaction_id=str(supplied_receipt["transaction_id"]),
    )
    _assert_internal_path_components_safe(
        workspace_dir=workspace_dir,
        target=internal_clearance_path,
    )
    for artifact_name, artifact_path in (
        ("clearance request", request_path),
        ("manual recovery receipt", supplied_receipt_path),
        ("internal clearance", internal_clearance_path),
        ("external clearance", external_clearance_path),
    ):
        if _is_relative_to(artifact_path, resolved_config_root):
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError(
                    f"{artifact_name} must be outside the configuration root"
                )
            )
    transaction_lock = create_write_model_configuration_transaction_lock(resolved_config_root)
    try:
        transaction_lock.acquire()
    except RuntimeError as exc:
        raise WriteModelConfigurationManualRecoveryClearanceBusyError(
            "another write-model configuration transaction holds the lock"
        ) from exc
    try:
        latest = _latest_internal_receipt(workspace_dir=workspace_dir)
        if latest is None:
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError(
                    "no internal manual recovery transaction requires clearance"
                )
            )
        latest_receipt_path, latest_receipt = latest
        _assert_receipt_is_latest(
            supplied_receipt_path=supplied_receipt_path,
            supplied_receipt=supplied_receipt,
            latest_receipt_path=latest_receipt_path,
            latest_receipt=latest_receipt,
        )
        if latest_receipt.get("status") != "recovered":
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError(
                    "only a recovered manual recovery receipt can be cleared"
                )
            )
        _assert_internal_path_components_safe(
            workspace_dir=workspace_dir,
            target=internal_clearance_path,
        )
        if internal_clearance_path.exists() and not internal_clearance_path.is_file():
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError("manual recovery clearance path is unsafe")
            )
        if internal_clearance_path.is_file():
            _assert_request_identity(
                request=request,
                receipt=latest_receipt,
                expected_ticker=normalized_ticker,
                now=current_time,
                require_current_request=False,
            )
            _path, existing = load_write_model_configuration_manual_recovery_clearance(internal_clearance_path)
            _assert_existing_clearance_identity(
                clearance=existing,
                request_path=request_path,
                request=request,
                receipt_path=latest_receipt_path,
                receipt=latest_receipt,
            )
            try:
                _persist_immutable(existing, external_clearance_path)
            except (FileExistsError, OSError) as exc:
                raise (
                    WriteModelConfigurationManualRecoveryClearanceReceiptError(
                        "manual recovery clearance is recorded internally "
                        "but the requested artifact could not be exported"
                    )
                ) from exc
            return existing
        _assert_request_identity(
            request=request,
            receipt=latest_receipt,
            expected_ticker=normalized_ticker,
            now=current_time,
            require_current_request=True,
        )
        verification = verify_write_model_configuration_manual_recovery_receipt(
            manual_recovery_receipt_path=latest_receipt_path,
            config_root=resolved_config_root,
            expected_ticker=normalized_ticker,
            snapshot_builder=snapshot_builder,
            configuration_transaction_lock_held=True,
        )
        if verification.get("status") != "current":
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError(
                    "manual recovery clearance requires a current verification result"
                )
            )
        _assert_independent_operator(
            receipt=latest_receipt,
            request=request,
        )
        clearance = _build_clearance(
            request_path=request_path,
            request=request,
            receipt_path=latest_receipt_path,
            receipt=latest_receipt,
            verification=verification,
            now=current_time,
        )
        _persist_immutable(clearance, internal_clearance_path)
        try:
            _persist_immutable(clearance, external_clearance_path)
        except (FileExistsError, OSError) as exc:
            raise (
                WriteModelConfigurationManualRecoveryClearanceReceiptError(
                    "manual recovery clearance is recorded internally but the requested artifact could not be exported"
                )
            ) from exc
        return clearance
    finally:
        transaction_lock.release()


def _assert_revocation_request_identity(
    *,
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
    clearance: Mapping[str, Any],
    expected_ticker: str,
    now: datetime,
    require_current_request: bool,
) -> None:
    expected = {
        "ticker": expected_ticker,
        "transaction_id": receipt["transaction_id"],
        "manual_recovery_receipt_fingerprint": receipt["receipt_fingerprint"],
        "manual_recovery_clearance_fingerprint": clearance["clearance_fingerprint"],
    }
    if any(request.get(field_name) != expected_value for field_name, expected_value in expected.items()):
        raise (
            WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                "manual recovery clearance revocation request identity changed"
            )
        )
    revoked_at = _parse_utc(
        request.get("revoked_at"),
        name="revoked_at",
    )
    clearance_issued_at = _parse_utc(
        clearance.get("issued_at"),
        name="clearance.issued_at",
    )
    if revoked_at <= clearance_issued_at:
        raise (
            WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                "manual recovery clearance revocation must follow clearance issuance"
            )
        )
    if require_current_request and revoked_at > now:
        raise (
            WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                "manual recovery clearance revocation is not effective yet"
            )
        )
    if require_current_request and now - revoked_at > _MAX_REQUEST_AGE:
        raise (
            WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                "manual recovery clearance revocation request is older than four hours"
            )
        )


def _assert_supplied_clearance_is_authoritative(
    *,
    supplied_clearance_path: Path,
    supplied_clearance: Mapping[str, Any],
    internal_clearance_path: Path,
    internal_clearance: Mapping[str, Any],
) -> None:
    if (
        supplied_clearance.get("transaction_id") != internal_clearance.get("transaction_id")
        or supplied_clearance.get("ticker") != internal_clearance.get("ticker")
        or not hmac.compare_digest(
            str(supplied_clearance.get("clearance_fingerprint")),
            str(internal_clearance.get("clearance_fingerprint")),
        )
        or not hmac.compare_digest(
            _file_fingerprint(supplied_clearance_path),
            _file_fingerprint(internal_clearance_path),
        )
    ):
        raise (
            WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                "manual recovery clearance revocation requires the exact authoritative clearance"
            )
        )


def _assert_supplied_revocation_is_authoritative(
    *,
    supplied_revocation_path: Path,
    supplied_revocation: Mapping[str, Any],
    internal_revocation_path: Path,
    internal_revocation: Mapping[str, Any],
) -> None:
    if (
        supplied_revocation.get("transaction_id") != internal_revocation.get("transaction_id")
        or supplied_revocation.get("ticker") != internal_revocation.get("ticker")
        or not hmac.compare_digest(
            str(supplied_revocation.get("manual_recovery_receipt_fingerprint")),
            str(internal_revocation.get("manual_recovery_receipt_fingerprint")),
        )
        or not hmac.compare_digest(
            str(supplied_revocation.get("manual_recovery_clearance_fingerprint")),
            str(internal_revocation.get("manual_recovery_clearance_fingerprint")),
        )
        or not hmac.compare_digest(
            str(supplied_revocation.get("revocation_fingerprint")),
            str(internal_revocation.get("revocation_fingerprint")),
        )
        or not hmac.compare_digest(
            _file_fingerprint(supplied_revocation_path),
            _file_fingerprint(internal_revocation_path),
        )
    ):
        raise WriteModelConfigurationManualRecoveryRestartBlockedError(
            "manual recovery restart requires the exact authoritative clearance revocation"
        )


def _load_exact_bound_restart_source(
    *,
    owner: Mapping[str, Any],
    field_name: str,
    fingerprint_field: str,
    loader: Callable[[str | Path], tuple[Path, dict[str, Any]]],
) -> tuple[Path, dict[str, Any]]:
    raw_source = _mapping(owner.get(field_name), name=field_name)
    raw_path = Path(
        _required_text(
            raw_source.get("path"),
            name=f"{field_name}.path",
            maximum_length=32_768,
        )
    ).expanduser()
    if raw_path.is_symlink():
        raise WriteModelConfigurationManualRecoveryRestartBlockedError(f"{field_name} source must not be a symlink")
    source = _validate_source(raw_source, name=field_name)
    source_path = Path(source["path"])
    loaded_path, payload = loader(source_path)
    try:
        current_file_fingerprint = _file_fingerprint(loaded_path)
    except OSError as exc:
        raise WriteModelConfigurationManualRecoveryRestartBlockedError(f"{field_name} source cannot be read") from exc
    if (
        loaded_path != source_path
        or not hmac.compare_digest(
            source["file_fingerprint"],
            current_file_fingerprint,
        )
        or not hmac.compare_digest(
            source["content_fingerprint"],
            _validated_fingerprint(
                payload.get(fingerprint_field),
                name=f"{field_name}.{fingerprint_field}",
            ),
        )
    ):
        raise WriteModelConfigurationManualRecoveryRestartBlockedError(f"{field_name} source identity changed")
    return loaded_path, payload


def _build_clearance_revocation(
    *,
    request_path: Path,
    request: Mapping[str, Any],
    receipt_path: Path,
    receipt: Mapping[str, Any],
    clearance_path: Path,
    clearance: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": _REVOCATION_SCHEMA_VERSION,
        "revocation_type": _REVOCATION_TYPE,
        "scope": _REVOCATION_SCOPE,
        "status": _REVOCATION_STATUS,
        "action": _REVOCATION_ACTION,
        "ticker": receipt["ticker"],
        "transaction_id": receipt["transaction_id"],
        "manual_recovery_receipt_fingerprint": receipt["receipt_fingerprint"],
        "manual_recovery_clearance_fingerprint": clearance["clearance_fingerprint"],
        "revoked_by": request["revoked_by"],
        "revocation_reference": request["revocation_reference"],
        "revocation_reason": request["revocation_reason"],
        "revoked_at": request["revoked_at"],
        "issued_at": _format_utc(now),
        "source_manual_recovery_receipt": _source_reference(
            path=receipt_path,
            content_fingerprint=str(receipt["receipt_fingerprint"]),
        ),
        "source_manual_recovery_clearance": _source_reference(
            path=clearance_path,
            content_fingerprint=str(clearance["clearance_fingerprint"]),
        ),
        "source_revocation_request": _source_reference(
            path=request_path,
            content_fingerprint=_fingerprint(request),
        ),
        "acknowledgements": list(_REVOCATION_REQUEST_ACKNOWLEDGEMENTS),
        "safety_boundaries": list(_REVOCATION_SAFETY_BOUNDARIES),
        "normal_write_clearance_revoked": True,
        "normal_write_allowed": False,
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    payload["revocation_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_manual_recovery_clearance_revocation(payload)
    return payload


def _assert_existing_revocation_identity(
    *,
    revocation: Mapping[str, Any],
    request_path: Path,
    request: Mapping[str, Any],
    receipt_path: Path,
    receipt: Mapping[str, Any],
    clearance_path: Path,
    clearance: Mapping[str, Any],
) -> None:
    request_source = _validate_source(
        revocation.get("source_revocation_request"),
        name="source_revocation_request",
    )
    receipt_source = _validate_source(
        revocation.get("source_manual_recovery_receipt"),
        name="source_manual_recovery_receipt",
    )
    clearance_source = _validate_source(
        revocation.get("source_manual_recovery_clearance"),
        name="source_manual_recovery_clearance",
    )
    expected = {
        "ticker": receipt["ticker"],
        "transaction_id": receipt["transaction_id"],
        "manual_recovery_receipt_fingerprint": receipt["receipt_fingerprint"],
        "manual_recovery_clearance_fingerprint": clearance["clearance_fingerprint"],
        "revoked_by": request["revoked_by"],
        "revocation_reference": request["revocation_reference"],
        "revocation_reason": request["revocation_reason"],
        "revoked_at": request["revoked_at"],
    }
    if any(revocation.get(field_name) != expected_value for field_name, expected_value in expected.items()):
        raise (
            WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                "existing manual recovery clearance revocation has another identity"
            )
        )
    if (
        Path(request_source["path"]) != request_path
        or not hmac.compare_digest(
            request_source["file_fingerprint"],
            _file_fingerprint(request_path),
        )
        or not hmac.compare_digest(
            request_source["content_fingerprint"],
            _fingerprint(request),
        )
        or Path(receipt_source["path"]) != receipt_path
        or not hmac.compare_digest(
            receipt_source["file_fingerprint"],
            _file_fingerprint(receipt_path),
        )
        or Path(clearance_source["path"]) != clearance_path
        or not hmac.compare_digest(
            clearance_source["file_fingerprint"],
            _file_fingerprint(clearance_path),
        )
    ):
        raise (
            WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                "existing manual recovery clearance revocation source changed"
            )
        )


def _assert_revocation_matches_current_clearance(
    *,
    revocation: Mapping[str, Any],
    receipt_path: Path,
    receipt: Mapping[str, Any],
    clearance_path: Path,
    clearance: Mapping[str, Any],
) -> None:
    request_source = _validate_source(
        revocation.get("source_revocation_request"),
        name="source_revocation_request",
    )
    request_path = Path(request_source["path"])
    loaded_request_path, request = load_write_model_configuration_manual_recovery_clearance_revocation_request(
        request_path
    )
    if (
        loaded_request_path != request_path
        or not hmac.compare_digest(
            request_source["file_fingerprint"],
            _file_fingerprint(loaded_request_path),
        )
        or not hmac.compare_digest(
            request_source["content_fingerprint"],
            _fingerprint(request),
        )
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance revocation request source changed"
        )
    try:
        _assert_existing_revocation_identity(
            revocation=revocation,
            request_path=loaded_request_path,
            request=request,
            receipt_path=receipt_path,
            receipt=receipt,
            clearance_path=clearance_path,
            clearance=clearance,
        )
        _assert_revocation_request_identity(
            request=request,
            receipt=receipt,
            clearance=clearance,
            expected_ticker=str(receipt["ticker"]),
            now=_parse_utc(
                revocation.get("issued_at"),
                name="revocation.issued_at",
            ),
            require_current_request=False,
        )
    except WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError as exc:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(str(exc)) from exc


def revoke_write_model_configuration_manual_recovery_clearance(
    *,
    revocation_request_path: str | Path,
    manual_recovery_receipt_path: str | Path,
    manual_recovery_clearance_path: str | Path,
    workspace_dir: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    revocation_output_path: str | Path,
    now: datetime,
) -> dict[str, Any]:
    """Immutably revoke the latest recovery clearance and fail closed."""

    current_time = _normalize_now(now)
    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    request_candidate = Path(revocation_request_path).expanduser()
    receipt_candidate = Path(manual_recovery_receipt_path).expanduser()
    clearance_candidate = Path(manual_recovery_clearance_path).expanduser()
    for artifact_name, candidate in (
        ("revocation request", request_candidate),
        ("manual recovery receipt", receipt_candidate),
        ("manual recovery clearance", clearance_candidate),
    ):
        if candidate.is_symlink():
            raise FileNotFoundError(f"{artifact_name} must not be a symlink: {candidate}")
    request_path = request_candidate.resolve()
    supplied_receipt_path = receipt_candidate.resolve()
    supplied_clearance_path = clearance_candidate.resolve()
    resolved_config_root = Path(config_root).expanduser().resolve()
    external_revocation_path = Path(revocation_output_path).expanduser().resolve()
    for artifact_name, artifact_path in (
        ("revocation request", request_path),
        ("manual recovery receipt", supplied_receipt_path),
        ("manual recovery clearance", supplied_clearance_path),
        ("external revocation", external_revocation_path),
    ):
        if _is_relative_to(artifact_path, resolved_config_root):
            raise (
                WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                    f"{artifact_name} must be outside the configuration root"
                )
            )
    transaction_lock = create_write_model_configuration_transaction_lock(resolved_config_root)
    try:
        transaction_lock.acquire()
    except RuntimeError as exc:
        raise (
            WriteModelConfigurationManualRecoveryClearanceRevocationBusyError(
                "another write-model configuration transaction holds the lock"
            )
        ) from exc
    try:
        request_path, request = load_write_model_configuration_manual_recovery_clearance_revocation_request(
            request_path
        )
        supplied_receipt_path, supplied_receipt = load_write_model_configuration_manual_recovery_receipt(
            supplied_receipt_path
        )
        supplied_clearance_path, supplied_clearance = load_write_model_configuration_manual_recovery_clearance(
            supplied_clearance_path
        )
        latest = _latest_internal_receipt(workspace_dir=workspace_dir)
        if latest is None:
            raise (
                WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                    "no internal manual recovery transaction has a clearance to revoke"
                )
            )
        latest_receipt_path, latest_receipt = latest
        try:
            _assert_receipt_is_latest(
                supplied_receipt_path=supplied_receipt_path,
                supplied_receipt=supplied_receipt,
                latest_receipt_path=latest_receipt_path,
                latest_receipt=latest_receipt,
            )
        except WriteModelConfigurationManualRecoveryClearanceBlockedError as exc:
            raise (WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(str(exc))) from exc
        if latest_receipt.get("status") != "recovered":
            raise (
                WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                    "only the latest recovered manual recovery transaction can have its clearance revoked"
                )
            )
        transaction_id = str(latest_receipt["transaction_id"])
        internal_clearance_path = _internal_clearance_path(
            workspace_dir=workspace_dir,
            transaction_id=transaction_id,
        )
        internal_revocation_path = _internal_clearance_revocation_path(
            workspace_dir=workspace_dir,
            transaction_id=transaction_id,
        )
        for internal_path in (
            internal_clearance_path,
            internal_revocation_path,
        ):
            _assert_internal_path_components_safe(
                workspace_dir=workspace_dir,
                target=internal_path,
            )
        if internal_clearance_path.is_symlink() or not internal_clearance_path.is_file():
            raise (
                WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                    "authoritative manual recovery clearance is missing or unsafe"
                )
            )
        _resolved, internal_clearance = load_write_model_configuration_manual_recovery_clearance(
            internal_clearance_path
        )
        _assert_supplied_clearance_is_authoritative(
            supplied_clearance_path=supplied_clearance_path,
            supplied_clearance=supplied_clearance,
            internal_clearance_path=internal_clearance_path,
            internal_clearance=internal_clearance,
        )
        _assert_revocation_request_identity(
            request=request,
            receipt=latest_receipt,
            clearance=internal_clearance,
            expected_ticker=normalized_ticker,
            now=current_time,
            require_current_request=not internal_revocation_path.exists(),
        )
        if internal_revocation_path.is_symlink():
            raise (
                WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                    "manual recovery clearance revocation path is unsafe"
                )
            )
        if internal_revocation_path.exists() and not internal_revocation_path.is_file():
            raise (
                WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                    "manual recovery clearance revocation path is unsafe"
                )
            )
        if internal_revocation_path.is_file():
            _path, existing = load_write_model_configuration_manual_recovery_clearance_revocation(
                internal_revocation_path
            )
            _assert_existing_revocation_identity(
                revocation=existing,
                request_path=request_path,
                request=request,
                receipt_path=latest_receipt_path,
                receipt=latest_receipt,
                clearance_path=internal_clearance_path,
                clearance=internal_clearance,
            )
            try:
                _persist_immutable(existing, external_revocation_path)
            except (FileExistsError, OSError) as exc:
                raise (
                    WriteModelConfigurationManualRecoveryClearanceRevocationReceiptError(
                        "manual recovery clearance revocation is "
                        "recorded internally but the requested artifact "
                        "could not be exported"
                    )
                ) from exc
            return existing
        gate = _assess_gate_locked(
            workspace_dir=workspace_dir,
            expected_ticker=normalized_ticker,
            now=current_time,
        )
        if gate.get("status") != "cleared" or not hmac.compare_digest(
            str(gate.get("clearance_fingerprint")),
            str(internal_clearance["clearance_fingerprint"]),
        ):
            raise (
                WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError(
                    "manual recovery clearance revocation requires the latest valid open clearance"
                )
            )
        revocation = _build_clearance_revocation(
            request_path=request_path,
            request=request,
            receipt_path=latest_receipt_path,
            receipt=latest_receipt,
            clearance_path=internal_clearance_path,
            clearance=internal_clearance,
            now=current_time,
        )
        _persist_immutable(revocation, internal_revocation_path)
        try:
            _persist_immutable(revocation, external_revocation_path)
        except (FileExistsError, OSError) as exc:
            raise (
                WriteModelConfigurationManualRecoveryClearanceRevocationReceiptError(
                    "manual recovery clearance revocation is recorded "
                    "internally but the requested artifact could not be "
                    "exported"
                )
            ) from exc
        return revocation
    finally:
        transaction_lock.release()


def restart_write_model_configuration_manual_recovery_after_clearance_revocation(
    *,
    manual_recovery_receipt_path: str | Path,
    manual_recovery_clearance_path: str | Path,
    manual_recovery_clearance_revocation_path: str | Path,
    workspace_dir: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    evidence_output_path: str | Path,
    now: datetime,
) -> dict[str, Any]:
    """Export standard recovery evidence from the latest revoked incident."""

    current_time = _normalize_now(now)
    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    receipt_candidate = Path(manual_recovery_receipt_path).expanduser()
    clearance_candidate = Path(manual_recovery_clearance_path).expanduser()
    revocation_candidate = Path(manual_recovery_clearance_revocation_path).expanduser()
    output_candidate = Path(evidence_output_path).expanduser()
    for artifact_name, candidate in (
        ("manual recovery receipt", receipt_candidate),
        ("manual recovery clearance", clearance_candidate),
        ("manual recovery clearance revocation", revocation_candidate),
        ("manual recovery restart evidence output", output_candidate),
    ):
        if candidate.is_symlink():
            raise FileNotFoundError(f"{artifact_name} must not be a symlink: {candidate}")
    supplied_receipt_path = receipt_candidate.resolve()
    supplied_clearance_path = clearance_candidate.resolve()
    supplied_revocation_path = revocation_candidate.resolve()
    external_evidence_path = output_candidate.resolve()
    resolved_config_root = Path(config_root).expanduser().resolve()
    for artifact_name, artifact_path in (
        ("manual recovery receipt", supplied_receipt_path),
        ("manual recovery clearance", supplied_clearance_path),
        (
            "manual recovery clearance revocation",
            supplied_revocation_path,
        ),
        ("manual recovery restart evidence", external_evidence_path),
    ):
        if _is_relative_to(artifact_path, resolved_config_root):
            raise WriteModelConfigurationManualRecoveryRestartBlockedError(
                f"{artifact_name} must be outside the configuration root"
            )

    transaction_lock = create_write_model_configuration_transaction_lock(resolved_config_root)
    try:
        transaction_lock.acquire()
    except RuntimeError as exc:
        raise WriteModelConfigurationManualRecoveryRestartBusyError(
            "another write-model configuration transaction holds the lock"
        ) from exc
    try:
        supplied_receipt_path, supplied_receipt = load_write_model_configuration_manual_recovery_receipt(
            supplied_receipt_path
        )
        supplied_clearance_path, supplied_clearance = load_write_model_configuration_manual_recovery_clearance(
            supplied_clearance_path
        )
        supplied_revocation_path, supplied_revocation = (
            load_write_model_configuration_manual_recovery_clearance_revocation(supplied_revocation_path)
        )
        try:
            gate = _assess_gate_locked(
                workspace_dir=workspace_dir,
                expected_ticker=normalized_ticker,
                now=current_time,
            )
            if gate.get("status") != "clearance_revoked":
                raise (
                    WriteModelConfigurationManualRecoveryRestartBlockedError(
                        "manual recovery restart requires the latest clearance_revoked gate"
                    )
                )
            latest = _latest_internal_receipt(workspace_dir=workspace_dir)
            if latest is None:
                raise (
                    WriteModelConfigurationManualRecoveryRestartBlockedError(
                        "manual recovery restart has no latest internal receipt"
                    )
                )
            latest_receipt_path, latest_receipt = latest
            _assert_receipt_is_latest(
                supplied_receipt_path=supplied_receipt_path,
                supplied_receipt=supplied_receipt,
                latest_receipt_path=latest_receipt_path,
                latest_receipt=latest_receipt,
            )
            transaction_id = str(latest_receipt["transaction_id"])
            internal_clearance_path = _internal_clearance_path(
                workspace_dir=workspace_dir,
                transaction_id=transaction_id,
            )
            internal_revocation_path = _internal_clearance_revocation_path(
                workspace_dir=workspace_dir,
                transaction_id=transaction_id,
            )
            for internal_path in (
                internal_clearance_path,
                internal_revocation_path,
            ):
                _assert_internal_path_components_safe(
                    workspace_dir=workspace_dir,
                    target=internal_path,
                )
                if internal_path.is_symlink() or not internal_path.is_file():
                    raise (
                        WriteModelConfigurationManualRecoveryRestartBlockedError(
                            "manual recovery restart authoritative artifact is missing or unsafe"
                        )
                    )
            if (
                Path(str(gate["clearance_path"])) != internal_clearance_path.resolve()
                or Path(str(gate["revocation_path"])) != internal_revocation_path.resolve()
            ):
                raise (
                    WriteModelConfigurationManualRecoveryRestartBlockedError(
                        "manual recovery restart gate paths changed"
                    )
                )
            _path, internal_clearance = load_write_model_configuration_manual_recovery_clearance(
                internal_clearance_path
            )
            _path, internal_revocation = load_write_model_configuration_manual_recovery_clearance_revocation(
                internal_revocation_path
            )
            _assert_supplied_clearance_is_authoritative(
                supplied_clearance_path=supplied_clearance_path,
                supplied_clearance=supplied_clearance,
                internal_clearance_path=internal_clearance_path,
                internal_clearance=internal_clearance,
            )
            _assert_supplied_revocation_is_authoritative(
                supplied_revocation_path=supplied_revocation_path,
                supplied_revocation=supplied_revocation,
                internal_revocation_path=internal_revocation_path,
                internal_revocation=internal_revocation,
            )
            source_evidence_path, source_evidence = _load_exact_bound_restart_source(
                owner=latest_receipt,
                field_name="source_manual_recovery_evidence",
                fingerprint_field="evidence_fingerprint",
                loader=(load_write_model_configuration_manual_recovery_evidence),
            )
            source_rollback_receipt_path, source_rollback_receipt = _load_exact_bound_restart_source(
                owner=source_evidence,
                field_name="source_rollback_receipt",
                fingerprint_field="receipt_fingerprint",
                loader=(load_write_model_configuration_operator_rollback_receipt),
            )
            clearance_revocation_lineage: dict[str, Any] = {
                "schema_version": ("write_model_configuration_manual_recovery_clearance_revocation_lineage_v1"),
                "ticker": normalized_ticker,
                "revoked_transaction_id": transaction_id,
                "revoked_manual_recovery_receipt_fingerprint": (latest_receipt["receipt_fingerprint"]),
                "manual_recovery_clearance_fingerprint": (internal_clearance["clearance_fingerprint"]),
                "manual_recovery_clearance_revocation_fingerprint": (internal_revocation["revocation_fingerprint"]),
                "source_revoked_manual_recovery_receipt": (
                    _source_reference(
                        path=latest_receipt_path,
                        content_fingerprint=str(latest_receipt["receipt_fingerprint"]),
                    )
                ),
                "source_manual_recovery_clearance": _source_reference(
                    path=internal_clearance_path,
                    content_fingerprint=str(internal_clearance["clearance_fingerprint"]),
                ),
                "source_manual_recovery_clearance_revocation": (
                    _source_reference(
                        path=internal_revocation_path,
                        content_fingerprint=str(internal_revocation["revocation_fingerprint"]),
                    )
                ),
            }
            clearance_revocation_lineage["lineage_fingerprint"] = _fingerprint(clearance_revocation_lineage)
            validate_write_model_configuration_manual_recovery_clearance_revocation_lineage(
                clearance_revocation_lineage
            )
            evidence = build_write_model_configuration_manual_recovery_evidence(
                rollback_receipt_path=source_rollback_receipt_path,
                config_root=resolved_config_root,
                expected_ticker=normalized_ticker,
                now=current_time,
                clearance_revocation_lineage=(clearance_revocation_lineage),
            )

            refreshed_gate = _assess_gate_locked(
                workspace_dir=workspace_dir,
                expected_ticker=normalized_ticker,
                now=current_time,
            )
            if refreshed_gate != gate:
                raise (
                    WriteModelConfigurationManualRecoveryRestartBlockedError(
                        "manual recovery clearance revocation changed during restart evidence export"
                    )
                )
            refreshed_receipt_path, refreshed_receipt = load_write_model_configuration_manual_recovery_receipt(
                supplied_receipt_path
            )
            _assert_receipt_is_latest(
                supplied_receipt_path=refreshed_receipt_path,
                supplied_receipt=refreshed_receipt,
                latest_receipt_path=latest_receipt_path,
                latest_receipt=latest_receipt,
            )
            (
                refreshed_clearance_path,
                refreshed_clearance,
            ) = load_write_model_configuration_manual_recovery_clearance(supplied_clearance_path)
            _assert_supplied_clearance_is_authoritative(
                supplied_clearance_path=refreshed_clearance_path,
                supplied_clearance=refreshed_clearance,
                internal_clearance_path=internal_clearance_path,
                internal_clearance=internal_clearance,
            )
            (
                refreshed_revocation_path,
                refreshed_revocation,
            ) = load_write_model_configuration_manual_recovery_clearance_revocation(supplied_revocation_path)
            _assert_supplied_revocation_is_authoritative(
                supplied_revocation_path=refreshed_revocation_path,
                supplied_revocation=refreshed_revocation,
                internal_revocation_path=internal_revocation_path,
                internal_revocation=internal_revocation,
            )
            (
                refreshed_source_evidence_path,
                refreshed_source_evidence,
            ) = _load_exact_bound_restart_source(
                owner=latest_receipt,
                field_name="source_manual_recovery_evidence",
                fingerprint_field="evidence_fingerprint",
                loader=(load_write_model_configuration_manual_recovery_evidence),
            )
            (
                refreshed_source_rollback_receipt_path,
                refreshed_source_rollback_receipt,
            ) = _load_exact_bound_restart_source(
                owner=refreshed_source_evidence,
                field_name="source_rollback_receipt",
                fingerprint_field="receipt_fingerprint",
                loader=(load_write_model_configuration_operator_rollback_receipt),
            )
            if (
                refreshed_source_evidence_path != source_evidence_path
                or refreshed_source_evidence != source_evidence
                or refreshed_source_rollback_receipt_path != source_rollback_receipt_path
                or refreshed_source_rollback_receipt != source_rollback_receipt
            ):
                raise (
                    WriteModelConfigurationManualRecoveryRestartBlockedError(
                        "manual recovery source evidence changed during restart export"
                    )
                )
        except WriteModelConfigurationManualRecoveryRestartBlockedError:
            raise
        except (
            WriteModelConfigurationManualRecoveryClearanceBlockedError,
            WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError,
            WriteModelConfigurationRollbackBlockedError,
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise (
                WriteModelConfigurationManualRecoveryRestartBlockedError(
                    f"manual recovery restart evidence is not current: {exc}"
                )
            ) from exc

        persist_write_model_configuration_manual_recovery_evidence(
            evidence,
            external_evidence_path,
        )
        return evidence
    finally:
        transaction_lock.release()


def _gate_payload(
    *,
    assessed_at: datetime,
    ticker: str,
    status: str,
    transaction_id: str | None,
    receipt_status: str | None,
    receipt_fingerprint: str | None,
    clearance_path: Path | None,
    clearance_fingerprint: str | None,
    revocation_path: Path | None,
    revocation_fingerprint: str | None,
    clearance_revocation_lineage: Mapping[str, Any] | None,
    reason_codes: list[str],
) -> dict[str, Any]:
    lineage: dict[str, Any] | None = None
    if clearance_revocation_lineage is not None:
        lineage = dict(clearance_revocation_lineage)
        validate_write_model_configuration_manual_recovery_clearance_revocation_lineage(lineage)
    payload: dict[str, Any] = {
        "schema_version": _GATE_SCHEMA_VERSION,
        "assessed_at": _format_utc(assessed_at),
        "ticker": ticker,
        "status": status,
        "action": _GATE_ACTIONS[status],
        "latest_transaction_id": transaction_id,
        "latest_receipt_status": receipt_status,
        "latest_receipt_fingerprint": receipt_fingerprint,
        "clearance_path": (str(clearance_path.resolve()) if clearance_path is not None else None),
        "clearance_fingerprint": clearance_fingerprint,
        "revocation_path": (str(revocation_path.resolve()) if revocation_path is not None else None),
        "revocation_fingerprint": revocation_fingerprint,
        "clearance_required": status == "clearance_required",
        "clearance_present": status in {"cleared", "clearance_revoked"},
        "clearance_revoked": status == "clearance_revoked",
        "normal_write_allowed": status in {"not_required", "cleared"},
        "clearance_revocation_lineage": lineage,
        "clearance_revocation_lineage_status": ("current" if lineage is not None else "not_applicable"),
        "reason_codes": reason_codes,
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    payload["gate_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_manual_recovery_gate(payload)
    return payload


def _assess_gate_locked(
    *,
    workspace_dir: str | Path,
    expected_ticker: str,
    now: datetime,
) -> dict[str, Any]:
    current_time = _normalize_now(now)
    try:
        latest = _latest_internal_receipt(workspace_dir=workspace_dir)
    except _IncompleteManualRecoveryTransactionsError as exc:
        transaction_id = ", ".join(exc.transaction_ids)
        return _gate_payload(
            assessed_at=current_time,
            ticker=expected_ticker,
            status="manual_recovery_required",
            transaction_id=transaction_id,
            receipt_status="incomplete",
            receipt_fingerprint=None,
            clearance_path=None,
            clearance_fingerprint=None,
            revocation_path=None,
            revocation_fingerprint=None,
            clearance_revocation_lineage=None,
            reason_codes=["incomplete_manual_recovery_transaction"],
        )
    if latest is None:
        return _gate_payload(
            assessed_at=current_time,
            ticker=expected_ticker,
            status="not_required",
            transaction_id=None,
            receipt_status=None,
            receipt_fingerprint=None,
            clearance_path=None,
            clearance_fingerprint=None,
            revocation_path=None,
            revocation_fingerprint=None,
            clearance_revocation_lineage=None,
            reason_codes=["no_manual_recovery_transaction"],
        )
    receipt_path, receipt = latest
    if receipt.get("ticker") != expected_ticker:
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "latest manual recovery transaction ticker does not match the command"
        )
    transaction_id = str(receipt["transaction_id"])
    receipt_status = str(receipt["status"])
    receipt_fingerprint = str(receipt["receipt_fingerprint"])
    receipt_lineage = _clearance_revocation_lineage(receipt)
    _assert_clearance_revocation_lineage_current(receipt_lineage)
    if receipt_status != "recovered":
        return _gate_payload(
            assessed_at=current_time,
            ticker=expected_ticker,
            status="manual_recovery_required",
            transaction_id=transaction_id,
            receipt_status=receipt_status,
            receipt_fingerprint=receipt_fingerprint,
            clearance_path=None,
            clearance_fingerprint=None,
            revocation_path=None,
            revocation_fingerprint=None,
            clearance_revocation_lineage=receipt_lineage,
            reason_codes=[
                (
                    "new_manual_recovery_evidence_required"
                    if receipt_status == "starting_state_restored"
                    else "manual_intervention_required"
                )
            ],
        )
    clearance_path = _internal_clearance_path(
        workspace_dir=workspace_dir,
        transaction_id=transaction_id,
    )
    _assert_internal_path_components_safe(
        workspace_dir=workspace_dir,
        target=clearance_path,
    )
    if clearance_path.is_symlink():
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError("manual recovery clearance path is unsafe")
    if not clearance_path.exists():
        return _gate_payload(
            assessed_at=current_time,
            ticker=expected_ticker,
            status="clearance_required",
            transaction_id=transaction_id,
            receipt_status=receipt_status,
            receipt_fingerprint=receipt_fingerprint,
            clearance_path=None,
            clearance_fingerprint=None,
            revocation_path=None,
            revocation_fingerprint=None,
            clearance_revocation_lineage=receipt_lineage,
            reason_codes=["latest_recovered_transaction_has_no_clearance"],
        )
    if not clearance_path.is_file():
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError("manual recovery clearance path is unsafe")
    _resolved, clearance = load_write_model_configuration_manual_recovery_clearance(clearance_path)
    _assert_same_clearance_revocation_lineage(
        receipt_lineage,
        _clearance_revocation_lineage(clearance),
        message="manual recovery clearance lineage no longer matches the latest internal receipt",
    )
    _assert_clearance_revocation_lineage_current(receipt_lineage)
    source = _validate_source(
        clearance.get("source_manual_recovery_receipt"),
        name="source_manual_recovery_receipt",
    )
    if (
        clearance.get("transaction_id") != transaction_id
        or clearance.get("ticker") != receipt.get("ticker")
        or not hmac.compare_digest(
            str(clearance.get("manual_recovery_receipt_fingerprint")),
            receipt_fingerprint,
        )
        or Path(source["path"]) != receipt_path
        or not hmac.compare_digest(
            source["file_fingerprint"],
            _file_fingerprint(receipt_path),
        )
        or not hmac.compare_digest(
            source["content_fingerprint"],
            receipt_fingerprint,
        )
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance no longer matches the latest internal receipt"
        )
    expected_snapshot_fingerprint = _validated_fingerprint(
        receipt.get("expected_selected_routing_snapshot_fingerprint"),
        name="expected_selected_routing_snapshot_fingerprint",
    )
    if not hmac.compare_digest(
        str(clearance.get("verified_routing_snapshot_fingerprint")),
        expected_snapshot_fingerprint,
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance routing identity changed"
        )
    if _parse_utc(
        clearance.get("cleared_at"),
        name="clearance.cleared_at",
    ) <= _parse_utc(
        receipt.get("completed_at"),
        name="receipt.completed_at",
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance predates recovery completion"
        )
    _assert_independent_operator(
        receipt=receipt,
        request={"cleared_by": clearance.get("cleared_by")},
    )
    revocation_path = _internal_clearance_revocation_path(
        workspace_dir=workspace_dir,
        transaction_id=transaction_id,
    )
    _assert_internal_path_components_safe(
        workspace_dir=workspace_dir,
        target=revocation_path,
    )
    if revocation_path.is_symlink():
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery clearance revocation path is unsafe"
        )
    if revocation_path.exists():
        if not revocation_path.is_file():
            raise (
                WriteModelConfigurationManualRecoveryClearanceBlockedError(
                    "manual recovery clearance revocation path is unsafe"
                )
            )
        _resolved, revocation = load_write_model_configuration_manual_recovery_clearance_revocation(revocation_path)
        _assert_revocation_matches_current_clearance(
            revocation=revocation,
            receipt_path=receipt_path,
            receipt=receipt,
            clearance_path=clearance_path,
            clearance=clearance,
        )
        return _gate_payload(
            assessed_at=current_time,
            ticker=expected_ticker,
            status="clearance_revoked",
            transaction_id=transaction_id,
            receipt_status=receipt_status,
            receipt_fingerprint=receipt_fingerprint,
            clearance_path=clearance_path,
            clearance_fingerprint=str(clearance["clearance_fingerprint"]),
            revocation_path=revocation_path,
            revocation_fingerprint=str(revocation["revocation_fingerprint"]),
            clearance_revocation_lineage=receipt_lineage,
            reason_codes=["latest_manual_recovery_clearance_revoked"],
        )
    return _gate_payload(
        assessed_at=current_time,
        ticker=expected_ticker,
        status="cleared",
        transaction_id=transaction_id,
        receipt_status=receipt_status,
        receipt_fingerprint=receipt_fingerprint,
        clearance_path=clearance_path,
        clearance_fingerprint=str(clearance["clearance_fingerprint"]),
        revocation_path=None,
        revocation_fingerprint=None,
        clearance_revocation_lineage=receipt_lineage,
        reason_codes=["latest_recovered_transaction_has_valid_clearance"],
    )


def assess_write_model_configuration_manual_recovery_gate(
    *,
    workspace_dir: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assess the durable gate before any normal write-side effects."""

    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    current_time = _normalize_now(now if now is not None else datetime.now(UTC))
    transaction_lock = create_write_model_configuration_transaction_lock(config_root)
    try:
        transaction_lock.acquire()
    except RuntimeError as exc:
        raise WriteModelConfigurationManualRecoveryClearanceBusyError(
            "another write-model configuration transaction holds the lock"
        ) from exc
    try:
        return _assess_gate_locked(
            workspace_dir=workspace_dir,
            expected_ticker=normalized_ticker,
            now=current_time,
        )
    finally:
        transaction_lock.release()


def validate_write_model_configuration_manual_recovery_gate(
    payload: Mapping[str, Any],
) -> None:
    """Validate one deterministic normal-write recovery gate result."""

    gate = _mapping(payload, name="manual recovery gate")
    _exact_fields(
        gate,
        expected=_GATE_FIELDS,
        name="manual recovery gate",
    )
    if gate.get("schema_version") != _GATE_SCHEMA_VERSION:
        raise ValueError("manual recovery gate schema is invalid")
    _parse_utc(
        gate.get("assessed_at"),
        name="assessed_at",
    )
    _required_text(
        gate.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    status = gate.get("status")
    if status not in _GATE_STATUSES:
        raise ValueError("manual recovery gate status is invalid")
    if gate.get("action") != _GATE_ACTIONS[str(status)]:
        raise ValueError("manual recovery gate action is invalid")
    transaction_id = gate.get("latest_transaction_id")
    receipt_status = gate.get("latest_receipt_status")
    receipt_fingerprint = gate.get("latest_receipt_fingerprint")
    clearance_path = gate.get("clearance_path")
    clearance_fingerprint = gate.get("clearance_fingerprint")
    revocation_path = gate.get("revocation_path")
    revocation_fingerprint = gate.get("revocation_fingerprint")
    lineage_value = gate.get("clearance_revocation_lineage")
    lineage_status = gate.get("clearance_revocation_lineage_status")
    if lineage_value is None:
        if lineage_status != "not_applicable":
            raise ValueError("manual recovery gate lineage status is invalid")
        lineage = None
    else:
        lineage = _mapping(
            lineage_value,
            name="clearance_revocation_lineage",
        )
        validate_write_model_configuration_manual_recovery_clearance_revocation_lineage(lineage)
        if lineage_status != "current":
            raise ValueError("manual recovery gate lineage status is invalid")
        if lineage.get("ticker") != gate.get("ticker"):
            raise ValueError("manual recovery gate lineage ticker is invalid")
    if status == "not_required":
        if any(
            value is not None
            for value in (
                transaction_id,
                receipt_status,
                receipt_fingerprint,
                clearance_path,
                clearance_fingerprint,
                revocation_path,
                revocation_fingerprint,
            )
        ):
            raise ValueError("unneeded manual recovery gate has incident evidence")
        if lineage is not None:
            raise ValueError("unneeded manual recovery gate has revocation lineage")
    else:
        _required_text(
            transaction_id,
            name="latest_transaction_id",
            maximum_length=256,
        )
        if receipt_status not in _RECEIPT_STATUSES:
            raise ValueError("manual recovery gate receipt status is invalid")
        if receipt_status == "incomplete":
            if receipt_fingerprint is not None:
                raise ValueError("incomplete recovery gate has a receipt fingerprint")
            if lineage is not None:
                raise ValueError("incomplete recovery gate has revocation lineage")
        else:
            _validated_fingerprint(
                receipt_fingerprint,
                name="latest_receipt_fingerprint",
            )
    if status in {"cleared", "clearance_revoked"}:
        path = Path(
            _required_text(
                clearance_path,
                name="clearance_path",
                maximum_length=32_768,
            )
        )
        if not path.is_absolute():
            raise ValueError("clearance_path must be absolute")
        _validated_fingerprint(
            clearance_fingerprint,
            name="clearance_fingerprint",
        )
    elif clearance_path is not None or clearance_fingerprint is not None:
        raise ValueError("blocked manual recovery gate cannot claim a clearance")
    if status == "clearance_revoked":
        path = Path(
            _required_text(
                revocation_path,
                name="revocation_path",
                maximum_length=32_768,
            )
        )
        if not path.is_absolute():
            raise ValueError("revocation_path must be absolute")
        _validated_fingerprint(
            revocation_fingerprint,
            name="revocation_fingerprint",
        )
    elif revocation_path is not None or revocation_fingerprint is not None:
        raise ValueError("non-revoked manual recovery gate has revocation evidence")
    expected_flags = {
        "clearance_required": status == "clearance_required",
        "clearance_present": status in {"cleared", "clearance_revoked"},
        "clearance_revoked": status == "clearance_revoked",
        "normal_write_allowed": status in {"not_required", "cleared"},
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    if any(gate.get(field_name) is not expected_value for field_name, expected_value in expected_flags.items()):
        raise ValueError("manual recovery gate safety evidence is invalid")
    reason_codes = gate.get("reason_codes")
    if not isinstance(reason_codes, list) or not reason_codes:
        raise ValueError("manual recovery gate reason_codes are empty")
    normalized_reasons = [
        _required_text(
            reason,
            name=f"reason_codes[{index}]",
            maximum_length=128,
        )
        for index, reason in enumerate(reason_codes)
    ]
    if len(normalized_reasons) != len(set(normalized_reasons)):
        raise ValueError("manual recovery gate reason codes duplicate")
    gate_fingerprint = _validated_fingerprint(
        gate.get("gate_fingerprint"),
        name="gate_fingerprint",
    )
    unsigned_gate = dict(gate)
    unsigned_gate.pop("gate_fingerprint")
    if not hmac.compare_digest(
        gate_fingerprint,
        _fingerprint(unsigned_gate),
    ):
        raise ValueError("manual recovery gate fingerprint mismatch")


def _validate_audit_timeline_roots(
    value: object,
) -> dict[str, Path]:
    roots = _mapping(value, name="manual recovery audit timeline roots")
    _exact_fields(
        roots,
        expected=_AUDIT_TIMELINE_ROOT_FIELDS,
        name="manual recovery audit timeline roots",
    )
    normalized: dict[str, Path] = {}
    for field_name in sorted(_AUDIT_TIMELINE_ROOT_FIELDS):
        path = Path(
            _required_text(
                roots.get(field_name),
                name=f"evidence_roots.{field_name}",
                maximum_length=32_768,
            )
        )
        if not path.is_absolute():
            raise ValueError(
                f"evidence_roots.{field_name} must be absolute"
            )
        normalized[field_name] = path
    transaction_root = normalized["transaction_root"]
    clearance_root = normalized["clearance_root"]
    revocation_root = normalized["revocation_root"]
    if (
        transaction_root.name != "transactions"
        or transaction_root.parent.name
        != "write-model-configuration-manual-recoveries"
        or clearance_root.name
        != "write-model-configuration-manual-recovery-clearances"
        or revocation_root.name
        != (
            "write-model-configuration-manual-recovery-"
            "clearance-revocations"
        )
    ):
        raise ValueError(
            "manual recovery audit timeline evidence roots are invalid"
        )
    dayu_root = transaction_root.parent.parent
    if (
        dayu_root.name != ".dayu"
        or clearance_root.parent != dayu_root
        or revocation_root.parent != dayu_root
    ):
        raise ValueError(
            "manual recovery audit timeline evidence roots disagree"
        )
    return normalized


def _expected_audit_artifact_path(
    *,
    roots: Mapping[str, Path],
    event_type: str,
    transaction_id: str,
) -> Path:
    metadata = _AUDIT_EVENT_TYPES[event_type]
    root = roots[str(metadata["root_field"])]
    if event_type == "manual_recovery_receipt":
        return root / transaction_id / "receipt.json"
    return root / f"{transaction_id}.json"


def _validate_audit_timeline_event(
    value: object,
    *,
    index: int,
    roots: Mapping[str, Path],
    ticker: str,
    generated_at: datetime,
) -> Mapping[str, Any]:
    event = _mapping(
        value,
        name=f"manual recovery audit timeline events[{index}]",
    )
    _exact_fields(
        event,
        expected=_AUDIT_TIMELINE_EVENT_FIELDS,
        name=f"manual recovery audit timeline events[{index}]",
    )
    if event.get("sequence") != index + 1:
        raise ValueError(
            "manual recovery audit timeline event sequence is invalid"
        )
    event_type = event.get("event_type")
    if event_type not in _AUDIT_EVENT_TYPES:
        raise ValueError(
            "manual recovery audit timeline event type is invalid"
        )
    normalized_event_type = str(event_type)
    metadata = _AUDIT_EVENT_TYPES[normalized_event_type]
    transaction_id = _required_text(
        event.get("transaction_id"),
        name=f"events[{index}].transaction_id",
        maximum_length=64,
    )
    event_at_text = _required_text(
        event.get("event_at"),
        name=f"events[{index}].event_at",
        maximum_length=64,
    )
    event_at = _parse_utc(
        event_at_text,
        name=f"events[{index}].event_at",
    )
    if event_at > generated_at:
        raise ValueError(
            "manual recovery audit timeline event occurs in the future"
        )
    artifact_path = Path(
        _required_text(
            event.get("artifact_path"),
            name=f"events[{index}].artifact_path",
            maximum_length=32_768,
        )
    )
    if not artifact_path.is_absolute():
        raise ValueError(
            "manual recovery audit timeline artifact path must be absolute"
        )
    expected_path = _expected_audit_artifact_path(
        roots=roots,
        event_type=normalized_event_type,
        transaction_id=transaction_id,
    )
    if artifact_path != expected_path:
        raise ValueError(
            "manual recovery audit timeline artifact path is invalid"
        )
    _validated_fingerprint(
        event.get("artifact_file_fingerprint"),
        name=f"events[{index}].artifact_file_fingerprint",
    )
    content_fingerprint = _validated_fingerprint(
        event.get("artifact_content_fingerprint"),
        name=f"events[{index}].artifact_content_fingerprint",
    )
    artifact = _mapping(
        event.get("artifact"),
        name=f"events[{index}].artifact",
    )
    validator: Callable[[Mapping[str, Any]], None]
    if normalized_event_type == "manual_recovery_receipt":
        validator = (
            validate_write_model_configuration_manual_recovery_receipt
        )
    elif normalized_event_type == "manual_recovery_clearance":
        validator = validate_write_model_configuration_manual_recovery_clearance
    else:
        validator = (
            validate_write_model_configuration_manual_recovery_clearance_revocation
        )
    validator(artifact)
    timestamp_field = str(metadata["timestamp_field"])
    fingerprint_field = str(metadata["fingerprint_field"])
    if artifact.get("transaction_id") != transaction_id:
        raise ValueError(
            "manual recovery audit timeline transaction identity changed"
        )
    if artifact.get("ticker") != ticker:
        raise ValueError(
            "manual recovery audit timeline artifact ticker is inconsistent"
        )
    if artifact.get(timestamp_field) != event_at_text:
        raise ValueError(
            "manual recovery audit timeline event timestamp is inconsistent"
        )
    if not hmac.compare_digest(
        content_fingerprint,
        str(artifact.get(fingerprint_field)),
    ):
        raise ValueError(
            "manual recovery audit timeline artifact identity changed"
        )
    return event


def _audit_source_matches_event(
    *,
    source_value: object,
    source_name: str,
    event: Mapping[str, Any],
) -> bool:
    source = _validate_source(source_value, name=source_name)
    return (
        Path(source["path"]) == Path(str(event["artifact_path"]))
        and hmac.compare_digest(
            source["file_fingerprint"],
            str(event["artifact_file_fingerprint"]),
        )
        and hmac.compare_digest(
            source["content_fingerprint"],
            str(event["artifact_content_fingerprint"]),
        )
    )


def _audit_lineages_match(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return hmac.compare_digest(
        _canonical_json(left),
        _canonical_json(right),
    )


def _validate_audit_clearance_link(
    *,
    receipt_event: Mapping[str, Any],
    clearance_event: Mapping[str, Any],
) -> None:
    receipt = _mapping(
        receipt_event["artifact"],
        name="receipt event artifact",
    )
    clearance = _mapping(
        clearance_event["artifact"],
        name="clearance event artifact",
    )
    if receipt.get("status") != "recovered":
        raise ValueError(
            "manual recovery audit timeline clearance has no recovered receipt"
        )
    if (
        clearance.get("ticker") != receipt.get("ticker")
        or clearance.get("transaction_id") != receipt.get("transaction_id")
        or not hmac.compare_digest(
            str(clearance.get("manual_recovery_receipt_fingerprint")),
            str(receipt.get("receipt_fingerprint")),
        )
        or not _audit_source_matches_event(
            source_value=clearance.get(
                "source_manual_recovery_receipt"
            ),
            source_name="source_manual_recovery_receipt",
            event=receipt_event,
        )
    ):
        raise ValueError(
            "manual recovery audit timeline clearance receipt link is invalid"
        )
    if not hmac.compare_digest(
        str(clearance.get("verified_routing_snapshot_fingerprint")),
        str(
            receipt.get(
                "expected_selected_routing_snapshot_fingerprint"
            )
        ),
    ):
        raise ValueError(
            "manual recovery audit timeline clearance routing link is invalid"
        )
    if _parse_utc(
        clearance.get("cleared_at"),
        name="clearance.cleared_at",
    ) <= _parse_utc(
        receipt.get("completed_at"),
        name="receipt.completed_at",
    ):
        raise ValueError(
            "manual recovery audit timeline clearance predates recovery"
        )
    if not _audit_lineages_match(
        _clearance_revocation_lineage(receipt),
        _clearance_revocation_lineage(clearance),
    ):
        raise ValueError(
            "manual recovery audit timeline clearance lineage changed"
        )


def _validate_audit_revocation_link(
    *,
    receipt_event: Mapping[str, Any],
    clearance_event: Mapping[str, Any],
    revocation_event: Mapping[str, Any],
) -> None:
    receipt = _mapping(
        receipt_event["artifact"],
        name="receipt event artifact",
    )
    clearance = _mapping(
        clearance_event["artifact"],
        name="clearance event artifact",
    )
    revocation = _mapping(
        revocation_event["artifact"],
        name="revocation event artifact",
    )
    if (
        revocation.get("ticker") != receipt.get("ticker")
        or revocation.get("transaction_id")
        != receipt.get("transaction_id")
        or not hmac.compare_digest(
            str(revocation.get("manual_recovery_receipt_fingerprint")),
            str(receipt.get("receipt_fingerprint")),
        )
        or not hmac.compare_digest(
            str(
                revocation.get(
                    "manual_recovery_clearance_fingerprint"
                )
            ),
            str(clearance.get("clearance_fingerprint")),
        )
        or not _audit_source_matches_event(
            source_value=revocation.get(
                "source_manual_recovery_receipt"
            ),
            source_name="source_manual_recovery_receipt",
            event=receipt_event,
        )
        or not _audit_source_matches_event(
            source_value=revocation.get(
                "source_manual_recovery_clearance"
            ),
            source_name="source_manual_recovery_clearance",
            event=clearance_event,
        )
    ):
        raise ValueError(
            "manual recovery audit timeline revocation link is invalid"
        )
    if _parse_utc(
        revocation.get("revoked_at"),
        name="revocation.revoked_at",
    ) <= _parse_utc(
        clearance.get("issued_at"),
        name="clearance.issued_at",
    ):
        raise ValueError(
            "manual recovery audit timeline revocation predates clearance"
        )


def _validate_audit_gate_history_link(
    *,
    gate: Mapping[str, Any],
    receipt_events: Mapping[str, Mapping[str, Any]],
    clearance_events: Mapping[str, Mapping[str, Any]],
    revocation_events: Mapping[str, Mapping[str, Any]],
    incomplete_transaction_ids: list[str],
) -> None:
    expected: dict[str, Any]
    expected_lineage: dict[str, Any] | None = None
    if incomplete_transaction_ids:
        expected = {
            "status": "manual_recovery_required",
            "latest_transaction_id": ", ".join(
                incomplete_transaction_ids
            ),
            "latest_receipt_status": "incomplete",
            "latest_receipt_fingerprint": None,
            "clearance_path": None,
            "clearance_fingerprint": None,
            "revocation_path": None,
            "revocation_fingerprint": None,
            "reason_codes": [
                "incomplete_manual_recovery_transaction"
            ],
        }
    elif not receipt_events:
        expected = {
            "status": "not_required",
            "latest_transaction_id": None,
            "latest_receipt_status": None,
            "latest_receipt_fingerprint": None,
            "clearance_path": None,
            "clearance_fingerprint": None,
            "revocation_path": None,
            "revocation_fingerprint": None,
            "reason_codes": ["no_manual_recovery_transaction"],
        }
    else:
        latest_receipt_event = max(
            receipt_events.values(),
            key=lambda event: (
                _parse_utc(
                    _mapping(
                        event["artifact"],
                        name="receipt event artifact",
                    ).get("completed_at"),
                    name="receipt.completed_at",
                ),
                str(event["transaction_id"]),
            ),
        )
        receipt = _mapping(
            latest_receipt_event["artifact"],
            name="latest receipt event artifact",
        )
        transaction_id = str(receipt["transaction_id"])
        receipt_status = str(receipt["status"])
        expected_lineage = _clearance_revocation_lineage(receipt)
        if receipt_status != "recovered":
            expected = {
                "status": "manual_recovery_required",
                "latest_transaction_id": transaction_id,
                "latest_receipt_status": receipt_status,
                "latest_receipt_fingerprint": receipt[
                    "receipt_fingerprint"
                ],
                "clearance_path": None,
                "clearance_fingerprint": None,
                "revocation_path": None,
                "revocation_fingerprint": None,
                "reason_codes": [
                    (
                        "new_manual_recovery_evidence_required"
                        if receipt_status == "starting_state_restored"
                        else "manual_intervention_required"
                    )
                ],
            }
        else:
            clearance_event = clearance_events.get(transaction_id)
            if clearance_event is None:
                expected = {
                    "status": "clearance_required",
                    "latest_transaction_id": transaction_id,
                    "latest_receipt_status": receipt_status,
                    "latest_receipt_fingerprint": receipt[
                        "receipt_fingerprint"
                    ],
                    "clearance_path": None,
                    "clearance_fingerprint": None,
                    "revocation_path": None,
                    "revocation_fingerprint": None,
                    "reason_codes": [
                        "latest_recovered_transaction_has_no_clearance"
                    ],
                }
            else:
                clearance = _mapping(
                    clearance_event["artifact"],
                    name="latest clearance event artifact",
                )
                revocation_event = revocation_events.get(transaction_id)
                revocation = (
                    _mapping(
                        revocation_event["artifact"],
                        name="latest revocation event artifact",
                    )
                    if revocation_event is not None
                    else None
                )
                expected = {
                    "status": (
                        "clearance_revoked"
                        if revocation is not None
                        else "cleared"
                    ),
                    "latest_transaction_id": transaction_id,
                    "latest_receipt_status": receipt_status,
                    "latest_receipt_fingerprint": receipt[
                        "receipt_fingerprint"
                    ],
                    "clearance_path": clearance_event[
                        "artifact_path"
                    ],
                    "clearance_fingerprint": clearance[
                        "clearance_fingerprint"
                    ],
                    "revocation_path": (
                        revocation_event["artifact_path"]
                        if revocation_event is not None
                        else None
                    ),
                    "revocation_fingerprint": (
                        revocation["revocation_fingerprint"]
                        if revocation is not None
                        else None
                    ),
                    "reason_codes": [
                        (
                            "latest_manual_recovery_clearance_revoked"
                            if revocation is not None
                            else (
                                "latest_recovered_transaction_has_"
                                "valid_clearance"
                            )
                        )
                    ],
                }
    if any(
        gate.get(field_name) != expected_value
        for field_name, expected_value in expected.items()
    ):
        raise ValueError(
            "manual recovery audit timeline gate disagrees with history"
        )
    actual_lineage = _clearance_revocation_lineage(gate)
    if not _audit_lineages_match(expected_lineage, actual_lineage):
        raise ValueError(
            "manual recovery audit timeline gate lineage disagrees with history"
        )


def validate_write_model_configuration_manual_recovery_audit_timeline(
    payload: Mapping[str, Any],
) -> None:
    """Validate one self-contained, read-only recovery history snapshot."""

    timeline = _mapping(
        payload,
        name="manual recovery audit timeline",
    )
    _exact_fields(
        timeline,
        expected=_AUDIT_TIMELINE_FIELDS,
        name="manual recovery audit timeline",
    )
    if timeline.get("schema_version") != _AUDIT_TIMELINE_SCHEMA_VERSION:
        raise ValueError(
            "manual recovery audit timeline schema is invalid"
        )
    generated_at = _parse_utc(
        timeline.get("generated_at"),
        name="generated_at",
    )
    ticker = _required_text(
        timeline.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    roots = _validate_audit_timeline_roots(
        timeline.get("evidence_roots")
    )
    gate = _mapping(
        timeline.get("current_gate"),
        name="current_gate",
    )
    validate_write_model_configuration_manual_recovery_gate(gate)
    if (
        gate.get("ticker") != ticker
        or gate.get("assessed_at") != timeline.get("generated_at")
    ):
        raise ValueError(
            "manual recovery audit timeline gate identity is inconsistent"
        )
    raw_events = timeline.get("events")
    if not isinstance(raw_events, list):
        raise ValueError(
            "manual recovery audit timeline events must be a list"
        )
    events = [
        _validate_audit_timeline_event(
            event,
            index=index,
            roots=roots,
            ticker=ticker,
            generated_at=generated_at,
        )
        for index, event in enumerate(raw_events)
    ]
    expected_order = sorted(
        events,
        key=lambda event: (
            _parse_utc(event["event_at"], name="event_at"),
            int(
                _AUDIT_EVENT_TYPES[str(event["event_type"])]["order"]
            ),
            str(event["transaction_id"]),
        ),
    )
    if events != expected_order:
        raise ValueError(
            "manual recovery audit timeline events are not ordered"
        )
    events_by_type: dict[str, dict[str, Mapping[str, Any]]] = {
        event_type: {} for event_type in _AUDIT_EVENT_TYPES
    }
    for event in events:
        event_type = str(event["event_type"])
        transaction_id = str(event["transaction_id"])
        if transaction_id in events_by_type[event_type]:
            raise ValueError(
                "manual recovery audit timeline artifact duplicates"
            )
        events_by_type[event_type][transaction_id] = event
    receipt_events = events_by_type["manual_recovery_receipt"]
    clearance_events = events_by_type["manual_recovery_clearance"]
    revocation_events = events_by_type[
        "manual_recovery_clearance_revocation"
    ]
    expected_counts = {
        "receipt_count": len(receipt_events),
        "clearance_count": len(clearance_events),
        "revocation_count": len(revocation_events),
    }
    for field_name, expected_count in expected_counts.items():
        value = timeline.get(field_name)
        if type(value) is not int or value != expected_count:
            raise ValueError(
                f"manual recovery audit timeline {field_name} is invalid"
            )
    incomplete_value = timeline.get("incomplete_transaction_ids")
    if not isinstance(incomplete_value, list):
        raise ValueError(
            "manual recovery audit timeline incomplete transactions "
            "must be a list"
        )
    incomplete_transaction_ids = [
        _required_text(
            value,
            name=f"incomplete_transaction_ids[{index}]",
            maximum_length=64,
        )
        for index, value in enumerate(incomplete_value)
    ]
    if (
        incomplete_transaction_ids
        != sorted(set(incomplete_transaction_ids))
        or set(incomplete_transaction_ids) & set(receipt_events)
    ):
        raise ValueError(
            "manual recovery audit timeline incomplete transactions "
            "are invalid"
        )
    if timeline.get("history_complete") is not (
        not incomplete_transaction_ids
    ):
        raise ValueError(
            "manual recovery audit timeline history status is invalid"
        )
    for transaction_id, clearance_event in clearance_events.items():
        receipt_event = receipt_events.get(transaction_id)
        if receipt_event is None:
            raise ValueError(
                "manual recovery audit timeline has an orphan clearance"
            )
        _validate_audit_clearance_link(
            receipt_event=receipt_event,
            clearance_event=clearance_event,
        )
    for transaction_id, revocation_event in revocation_events.items():
        revocation_receipt_event = receipt_events.get(transaction_id)
        revocation_clearance_event = clearance_events.get(transaction_id)
        if (
            revocation_receipt_event is None
            or revocation_clearance_event is None
        ):
            raise ValueError(
                "manual recovery audit timeline has an orphan revocation"
            )
        _validate_audit_revocation_link(
            receipt_event=revocation_receipt_event,
            clearance_event=revocation_clearance_event,
            revocation_event=revocation_event,
        )
    _validate_audit_gate_history_link(
        gate=gate,
        receipt_events=receipt_events,
        clearance_events=clearance_events,
        revocation_events=revocation_events,
        incomplete_transaction_ids=incomplete_transaction_ids,
    )
    safety_flags = (
        "normal_write_authorization_granted",
        "configuration_mutation_performed",
        "approval_consumed",
        "model_execution_performed",
    )
    if any(
        timeline.get(field_name) is not False
        for field_name in safety_flags
    ):
        raise ValueError(
            "manual recovery audit timeline safety evidence is invalid"
        )
    fingerprint = _validated_fingerprint(
        timeline.get("timeline_fingerprint"),
        name="timeline_fingerprint",
    )
    unsigned_timeline = dict(timeline)
    unsigned_timeline.pop("timeline_fingerprint")
    if not hmac.compare_digest(
        fingerprint,
        _fingerprint(unsigned_timeline),
    ):
        raise ValueError(
            "manual recovery audit timeline fingerprint mismatch"
        )


def build_write_model_configuration_manual_recovery_audit_timeline(
    *,
    workspace_dir: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build one strict audit timeline under the configuration lock."""

    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    current_time = _normalize_now(
        now if now is not None else datetime.now(UTC)
    )
    transaction_lock = create_write_model_configuration_transaction_lock(
        config_root
    )
    try:
        transaction_lock.acquire()
    except RuntimeError as exc:
        raise WriteModelConfigurationManualRecoveryClearanceBusyError(
            "another write-model configuration transaction holds the lock"
        ) from exc
    try:
        initial_state = _internal_manual_recovery_audit_state(
            workspace_dir=workspace_dir
        )
        gate = _assess_gate_locked(
            workspace_dir=workspace_dir,
            expected_ticker=normalized_ticker,
            now=current_time,
        )
        final_state = _internal_manual_recovery_audit_state(
            workspace_dir=workspace_dir
        )
        if not hmac.compare_digest(
            _canonical_json(initial_state),
            _canonical_json(final_state),
        ):
            raise (
                WriteModelConfigurationManualRecoveryAuditTimelineChangedError(
                    "internal manual recovery evidence changed during audit"
                )
            )
        events = list(final_state["events"])
        incomplete_transaction_ids = list(
            final_state["incomplete_transaction_ids"]
        )
        payload: dict[str, Any] = {
            "schema_version": _AUDIT_TIMELINE_SCHEMA_VERSION,
            "generated_at": _format_utc(current_time),
            "ticker": normalized_ticker,
            "evidence_roots": dict(final_state["evidence_roots"]),
            "current_gate": gate,
            "events": events,
            "receipt_count": sum(
                event["event_type"] == "manual_recovery_receipt"
                for event in events
            ),
            "clearance_count": sum(
                event["event_type"] == "manual_recovery_clearance"
                for event in events
            ),
            "revocation_count": sum(
                event["event_type"]
                == "manual_recovery_clearance_revocation"
                for event in events
            ),
            "incomplete_transaction_ids": incomplete_transaction_ids,
            "history_complete": not incomplete_transaction_ids,
            "normal_write_authorization_granted": False,
            "configuration_mutation_performed": False,
            "approval_consumed": False,
            "model_execution_performed": False,
        }
        payload["timeline_fingerprint"] = _fingerprint(payload)
        try:
            validate_write_model_configuration_manual_recovery_audit_timeline(
                payload
            )
        except (TypeError, ValueError) as exc:
            raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
                "manual recovery audit timeline evidence is invalid: "
                f"{exc}"
            ) from exc
        return payload
    finally:
        transaction_lock.release()


def _manual_recovery_gate_verification_payload(
    *,
    verified_at: datetime,
    ticker: str,
    source_gate_path: Path,
    source_gate_file_fingerprint: str,
    source_gate: Mapping[str, Any],
    current_gate: Mapping[str, Any],
) -> dict[str, Any]:
    changed_fields = _changed_gate_state_fields(
        source_gate,
        current_gate,
    )
    state_matches = not changed_fields
    status = "current" if state_matches else "stale"
    payload: dict[str, Any] = {
        "schema_version": _GATE_VERIFICATION_SCHEMA_VERSION,
        "verified_at": _format_utc(verified_at),
        "ticker": ticker,
        "status": status,
        "action": _GATE_VERIFICATION_ACTIONS[status],
        "source_gate_path": str(source_gate_path.resolve()),
        "source_gate_file_fingerprint": source_gate_file_fingerprint,
        "source_gate": dict(source_gate),
        "current_gate": dict(current_gate),
        "source_state_fingerprint": _fingerprint(
            _gate_state(source_gate)
        ),
        "current_state_fingerprint": _fingerprint(
            _gate_state(current_gate)
        ),
        "state_matches": state_matches,
        "changed_fields": changed_fields,
        "reason_codes": list(_GATE_VERIFICATION_REASONS[status]),
        "normal_write_authorization_granted": False,
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    payload["verification_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_manual_recovery_gate_verification(
        payload
    )
    return payload


def validate_write_model_configuration_manual_recovery_gate_verification(
    payload: Mapping[str, Any],
) -> None:
    """Validate one self-contained gate snapshot verification result."""

    verification = _mapping(
        payload,
        name="manual recovery gate verification",
    )
    _exact_fields(
        verification,
        expected=_GATE_VERIFICATION_FIELDS,
        name="manual recovery gate verification",
    )
    if (
        verification.get("schema_version")
        != _GATE_VERIFICATION_SCHEMA_VERSION
    ):
        raise ValueError(
            "manual recovery gate verification schema is invalid"
        )
    verified_at = _parse_utc(
        verification.get("verified_at"),
        name="verified_at",
    )
    ticker = _required_text(
        verification.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    status = verification.get("status")
    if status not in _GATE_VERIFICATION_ACTIONS:
        raise ValueError(
            "manual recovery gate verification status is invalid"
        )
    if verification.get("action") != _GATE_VERIFICATION_ACTIONS[str(status)]:
        raise ValueError(
            "manual recovery gate verification action is invalid"
        )
    source_gate_path = Path(
        _required_text(
            verification.get("source_gate_path"),
            name="source_gate_path",
            maximum_length=32_768,
        )
    )
    if not source_gate_path.is_absolute():
        raise ValueError("source_gate_path must be absolute")
    _validated_fingerprint(
        verification.get("source_gate_file_fingerprint"),
        name="source_gate_file_fingerprint",
    )
    source_gate = _mapping(
        verification.get("source_gate"),
        name="source_gate",
    )
    current_gate = _mapping(
        verification.get("current_gate"),
        name="current_gate",
    )
    validate_write_model_configuration_manual_recovery_gate(source_gate)
    validate_write_model_configuration_manual_recovery_gate(current_gate)
    if (
        source_gate.get("ticker") != ticker
        or current_gate.get("ticker") != ticker
    ):
        raise ValueError(
            "manual recovery gate verification ticker is inconsistent"
        )
    source_assessed_at = _parse_utc(
        source_gate.get("assessed_at"),
        name="source_gate.assessed_at",
    )
    current_assessed_at = _parse_utc(
        current_gate.get("assessed_at"),
        name="current_gate.assessed_at",
    )
    if source_assessed_at > verified_at:
        raise ValueError(
            "source manual recovery gate was assessed after verification"
        )
    if current_assessed_at != verified_at:
        raise ValueError(
            "current manual recovery gate assessment time is inconsistent"
        )
    source_state_fingerprint = _validated_fingerprint(
        verification.get("source_state_fingerprint"),
        name="source_state_fingerprint",
    )
    current_state_fingerprint = _validated_fingerprint(
        verification.get("current_state_fingerprint"),
        name="current_state_fingerprint",
    )
    expected_source_state_fingerprint = _fingerprint(
        _gate_state(source_gate)
    )
    expected_current_state_fingerprint = _fingerprint(
        _gate_state(current_gate)
    )
    if not hmac.compare_digest(
        source_state_fingerprint,
        expected_source_state_fingerprint,
    ):
        raise ValueError(
            "manual recovery gate source state fingerprint mismatch"
        )
    if not hmac.compare_digest(
        current_state_fingerprint,
        expected_current_state_fingerprint,
    ):
        raise ValueError(
            "manual recovery gate current state fingerprint mismatch"
        )
    expected_changed_fields = _changed_gate_state_fields(
        source_gate,
        current_gate,
    )
    changed_fields = verification.get("changed_fields")
    if not isinstance(changed_fields, list):
        raise ValueError(
            "manual recovery gate verification changed_fields must be a list"
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
            "manual recovery gate verification changed_fields are invalid"
        )
    expected_state_matches = not expected_changed_fields
    if (
        verification.get("state_matches")
        is not expected_state_matches
    ):
        raise ValueError(
            "manual recovery gate verification state match is invalid"
        )
    expected_status = (
        "current" if expected_state_matches else "stale"
    )
    if status != expected_status:
        raise ValueError(
            "manual recovery gate verification status is inconsistent"
        )
    if (
        verification.get("reason_codes")
        != _GATE_VERIFICATION_REASONS[expected_status]
    ):
        raise ValueError(
            "manual recovery gate verification reason_codes are invalid"
        )
    safety_flags = (
        "normal_write_authorization_granted",
        "configuration_mutation_performed",
        "approval_consumed",
        "model_execution_performed",
    )
    if any(
        verification.get(field_name) is not False
        for field_name in safety_flags
    ):
        raise ValueError(
            "manual recovery gate verification safety evidence is invalid"
        )
    verification_fingerprint = _validated_fingerprint(
        verification.get("verification_fingerprint"),
        name="verification_fingerprint",
    )
    unsigned_verification = dict(verification)
    unsigned_verification.pop("verification_fingerprint")
    if not hmac.compare_digest(
        verification_fingerprint,
        _fingerprint(unsigned_verification),
    ):
        raise ValueError(
            "manual recovery gate verification fingerprint mismatch"
        )


def verify_write_model_configuration_manual_recovery_gate_snapshot(
    *,
    gate_snapshot_path: str | Path,
    workspace_dir: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compare one exported gate snapshot with a fresh local assessment."""

    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    current_time = _normalize_now(
        now if now is not None else datetime.now(UTC)
    )
    (
        source_gate_path,
        source_gate,
        source_gate_file_fingerprint,
    ) = _load_external_gate_snapshot(
        gate_snapshot_path,
        config_root=config_root,
    )
    if source_gate.get("ticker") != normalized_ticker:
        raise ValueError(
            "manual recovery gate input ticker does not match the command"
        )
    if _parse_utc(
        source_gate.get("assessed_at"),
        name="source_gate.assessed_at",
    ) > current_time:
        raise ValueError(
            "manual recovery gate input was assessed in the future"
        )
    try:
        current_gate = (
            assess_write_model_configuration_manual_recovery_gate(
                workspace_dir=workspace_dir,
                config_root=config_root,
                expected_ticker=normalized_ticker,
                now=current_time,
            )
        )
        validate_write_model_configuration_manual_recovery_gate(
            current_gate
        )
    except WriteModelConfigurationManualRecoveryClearanceBusyError:
        raise
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise (
            WriteModelConfigurationManualRecoveryGateVerificationEvidenceError(
                "current manual recovery gate evidence is invalid: "
                f"{exc}"
            )
        ) from exc
    try:
        (
            refreshed_source_gate_path,
            refreshed_source_gate,
            refreshed_source_gate_file_fingerprint,
        ) = _load_external_gate_snapshot(
            gate_snapshot_path,
            config_root=config_root,
        )
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise (
            WriteModelConfigurationManualRecoveryGateVerificationChangedError(
                "manual recovery gate input changed during verification: "
                f"{exc}"
            )
        ) from exc
    source_changed = (
        refreshed_source_gate_path != source_gate_path
        or not hmac.compare_digest(
            refreshed_source_gate_file_fingerprint,
            source_gate_file_fingerprint,
        )
        or not hmac.compare_digest(
            _canonical_json(refreshed_source_gate),
            _canonical_json(source_gate),
        )
    )
    if source_changed:
        raise (
            WriteModelConfigurationManualRecoveryGateVerificationChangedError(
                "manual recovery gate input changed during verification"
            )
        )
    try:
        return _manual_recovery_gate_verification_payload(
            verified_at=current_time,
            ticker=normalized_ticker,
            source_gate_path=source_gate_path,
            source_gate_file_fingerprint=(
                source_gate_file_fingerprint
            ),
            source_gate=source_gate,
            current_gate=current_gate,
        )
    except (TypeError, ValueError) as exc:
        raise (
            WriteModelConfigurationManualRecoveryGateVerificationEvidenceError(
                "manual recovery gate verification evidence is invalid: "
                f"{exc}"
            )
        ) from exc


def persist_write_model_configuration_manual_recovery_gate(
    payload: Mapping[str, Any],
    path: str | Path,
    *,
    config_root: str | Path,
) -> Path:
    """Immutably export one validated gate snapshot outside configuration."""

    validate_write_model_configuration_manual_recovery_gate(payload)
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery gate output must not be a symlink"
        )
    lexical_target = candidate.absolute()
    target = candidate.resolve()
    resolved_config_root = Path(config_root).expanduser().resolve()
    if _is_relative_to(lexical_target, resolved_config_root) or _is_relative_to(
        target,
        resolved_config_root,
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery gate output must be outside the configuration root"
        )
    return _persist_immutable(payload, target)


def persist_write_model_configuration_manual_recovery_gate_verification(
    payload: Mapping[str, Any],
    path: str | Path,
    *,
    config_root: str | Path,
) -> Path:
    """Immutably export a gate verification outside configuration."""

    validate_write_model_configuration_manual_recovery_gate_verification(
        payload
    )
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery gate verification output must not be a symlink"
        )
    lexical_target = candidate.absolute()
    target = candidate.resolve()
    resolved_config_root = Path(config_root).expanduser().resolve()
    if _is_relative_to(lexical_target, resolved_config_root) or _is_relative_to(
        target,
        resolved_config_root,
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery gate verification output must be outside "
            "the configuration root"
        )
    return _persist_immutable(payload, target)


def persist_write_model_configuration_manual_recovery_audit_timeline(
    payload: Mapping[str, Any],
    path: str | Path,
    *,
    workspace_dir: str | Path,
    config_root: str | Path,
) -> Path:
    """Immutably export one audit timeline outside authoritative roots."""

    validate_write_model_configuration_manual_recovery_audit_timeline(
        payload
    )
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery audit timeline output must not be a symlink"
        )
    lexical_target = candidate.absolute()
    target = candidate.resolve()
    protected_roots = (
        Path(config_root).expanduser().resolve(),
        Path(workspace_dir).expanduser().resolve() / ".dayu",
    )
    if any(
        _is_relative_to(lexical_target, root)
        or _is_relative_to(target, root)
        for root in protected_roots
    ):
        raise WriteModelConfigurationManualRecoveryClearanceBlockedError(
            "manual recovery audit timeline output must be outside "
            "configuration and authoritative evidence roots"
        )
    return _persist_immutable(payload, target)


def format_write_model_configuration_manual_recovery_clearance_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Render one concise operator-facing clearance result."""

    validate_write_model_configuration_manual_recovery_clearance(payload)
    lines = [
        "",
        "=" * 60,
        "Write-model configuration manual recovery clearance",
        f"  Status        : {payload['status']}",
        f"  Ticker        : {payload['ticker']}",
        f"  Transaction   : {payload['transaction_id']}",
        f"  Cleared by    : {payload['cleared_by']}",
        f"  Verification  : {payload['verification_status']}",
        "  Configuration : unchanged by clearance",
        "  Approval      : not consumed by clearance",
        "  Model calls   : none",
    ]
    lineage = _clearance_revocation_lineage(payload)
    if lineage is not None:
        lines.append(f"  Revocation fp : {lineage['manual_recovery_clearance_revocation_fingerprint']}")
    lines.extend(
        (
            f"  Clearance fp  : {payload['clearance_fingerprint']}",
            "=" * 60,
        )
    )
    return tuple(lines)


def format_write_model_configuration_manual_recovery_clearance_revocation_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Render one concise operator-facing clearance revocation."""

    validate_write_model_configuration_manual_recovery_clearance_revocation(payload)
    return (
        "",
        "=" * 60,
        "Write-model configuration manual recovery clearance revocation",
        f"  Status        : {payload['status']}",
        f"  Ticker        : {payload['ticker']}",
        f"  Transaction   : {payload['transaction_id']}",
        f"  Revoked by    : {payload['revoked_by']}",
        "  Normal writes : blocked",
        "  Configuration : unchanged by revocation",
        "  Approval      : not consumed by revocation",
        "  Model calls   : none",
        f"  Revocation fp : {payload['revocation_fingerprint']}",
        "=" * 60,
    )


def format_write_model_configuration_manual_recovery_gate_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Render one concise normal-write recovery gate result."""

    validate_write_model_configuration_manual_recovery_gate(payload)
    lines = [
        "",
        "=" * 60,
        "Write-model configuration manual recovery gate",
        f"  Status        : {payload['status']}",
        f"  Assessed at   : {payload['assessed_at']}",
        f"  Ticker        : {payload['ticker']}",
        f"  Action        : {payload['action']}",
        f"  Transaction   : {payload['latest_transaction_id']}",
        f"  Receipt       : {payload['latest_receipt_status']}",
        f"  Clearance     : {payload['clearance_present']}",
        f"  Revoked       : {payload['clearance_revoked']}",
        f"  Lineage       : {payload['clearance_revocation_lineage_status']}",
        f"  Normal writes : {payload['normal_write_allowed']}",
        "  Configuration : unchanged by gate",
        "  Approval      : not consumed by gate",
        "  Model calls   : none",
    ]
    lineage = _clearance_revocation_lineage(payload)
    if lineage is not None:
        lines.extend(
            (
                f"  Lineage fp    : {lineage['lineage_fingerprint']}",
                f"  Prior revoke  : {lineage['manual_recovery_clearance_revocation_fingerprint']}",
            )
        )
    lines.extend(
        (
            f"  Gate fp       : {payload['gate_fingerprint']}",
            "=" * 60,
        )
    )
    return tuple(lines)


def format_write_model_configuration_manual_recovery_audit_timeline_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Render one concise operator-facing recovery history summary."""

    validate_write_model_configuration_manual_recovery_audit_timeline(
        payload
    )
    gate = _mapping(payload["current_gate"], name="current_gate")
    incomplete = ", ".join(payload["incomplete_transaction_ids"]) or "none"
    return (
        "",
        "=" * 60,
        "Write-model configuration manual recovery audit timeline",
        f"  Generated at  : {payload['generated_at']}",
        f"  Ticker        : {payload['ticker']}",
        f"  Gate status   : {gate['status']}",
        f"  Normal writes : {gate['normal_write_allowed']}",
        f"  Events        : {len(payload['events'])}",
        f"  Receipts      : {payload['receipt_count']}",
        f"  Clearances    : {payload['clearance_count']}",
        f"  Revocations   : {payload['revocation_count']}",
        f"  Incomplete    : {incomplete}",
        f"  Full history  : {payload['history_complete']}",
        "  Authorization : not granted by timeline",
        "  Configuration : unchanged by timeline",
        "  Approval      : not consumed by timeline",
        "  Model calls   : none",
        f"  Timeline fp   : {payload['timeline_fingerprint']}",
        "=" * 60,
    )


def format_write_model_configuration_manual_recovery_gate_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Render one concise gate snapshot verification result."""

    validate_write_model_configuration_manual_recovery_gate_verification(
        payload
    )
    changed_fields = ", ".join(payload["changed_fields"]) or "none"
    source_gate = _mapping(
        payload["source_gate"],
        name="source_gate",
    )
    current_gate = _mapping(
        payload["current_gate"],
        name="current_gate",
    )
    return (
        "",
        "=" * 60,
        "Write-model configuration manual recovery gate verification",
        f"  Status        : {payload['status']}",
        f"  Verified at   : {payload['verified_at']}",
        f"  Ticker        : {payload['ticker']}",
        f"  Action        : {payload['action']}",
        f"  Source gate   : {source_gate['status']}",
        f"  Current gate  : {current_gate['status']}",
        f"  State matches : {payload['state_matches']}",
        f"  Changed       : {changed_fields}",
        "  Authorization : not granted by verification",
        "  Configuration : unchanged by verification",
        "  Approval      : not consumed by verification",
        "  Model calls   : none",
        f"  Source file fp: {payload['source_gate_file_fingerprint']}",
        f"  Verification  : {payload['verification_fingerprint']}",
        "=" * 60,
    )


__all__ = [
    "WriteModelConfigurationManualRecoveryAuditTimelineChangedError",
    "WriteModelConfigurationManualRecoveryClearanceBlockedError",
    "WriteModelConfigurationManualRecoveryClearanceBusyError",
    "WriteModelConfigurationManualRecoveryClearanceReceiptError",
    "WriteModelConfigurationManualRecoveryGateVerificationChangedError",
    "WriteModelConfigurationManualRecoveryGateVerificationEvidenceError",
    "WriteModelConfigurationManualRecoveryClearanceRevocationBlockedError",
    "WriteModelConfigurationManualRecoveryClearanceRevocationBusyError",
    "WriteModelConfigurationManualRecoveryClearanceRevocationReceiptError",
    "WriteModelConfigurationManualRecoveryRestartBlockedError",
    "WriteModelConfigurationManualRecoveryRestartBusyError",
    "assess_write_model_configuration_manual_recovery_gate",
    "build_write_model_configuration_manual_recovery_audit_timeline",
    "format_write_model_configuration_manual_recovery_audit_timeline_report",
    "format_write_model_configuration_manual_recovery_clearance_report",
    "format_write_model_configuration_manual_recovery_clearance_revocation_report",
    "format_write_model_configuration_manual_recovery_gate_report",
    "format_write_model_configuration_manual_recovery_gate_verification_report",
    "issue_write_model_configuration_manual_recovery_clearance",
    "load_write_model_configuration_manual_recovery_clearance",
    "load_write_model_configuration_manual_recovery_clearance_revocation",
    "load_write_model_configuration_manual_recovery_clearance_revocation_request",
    "load_write_model_configuration_manual_recovery_clearance_request",
    "persist_write_model_configuration_manual_recovery_audit_timeline",
    "persist_write_model_configuration_manual_recovery_gate",
    "persist_write_model_configuration_manual_recovery_gate_verification",
    "restart_write_model_configuration_manual_recovery_after_clearance_revocation",
    "revoke_write_model_configuration_manual_recovery_clearance",
    "validate_write_model_configuration_manual_recovery_clearance",
    "validate_write_model_configuration_manual_recovery_clearance_revocation",
    "validate_write_model_configuration_manual_recovery_clearance_revocation_request",
    "validate_write_model_configuration_manual_recovery_clearance_request",
    "validate_write_model_configuration_manual_recovery_audit_timeline",
    "validate_write_model_configuration_manual_recovery_gate",
    "validate_write_model_configuration_manual_recovery_gate_verification",
    "verify_write_model_configuration_manual_recovery_gate_snapshot",
    "write_model_configuration_manual_recovery_clearance_root",
    "write_model_configuration_manual_recovery_clearance_revocation_root",
]
