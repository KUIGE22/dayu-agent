"""Plan and approve an exact manual write-routing recovery."""

from __future__ import annotations

import hmac
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dayu.contracts.model_config import ModelConfigJsonValue
from dayu.services._write_artifact_utils import (
    absolute_path,
    bytes_fingerprint,
    canonical_json_bytes,
    decode_base64_strict,
    file_fingerprint,
    fingerprint_bytes,
    format_utc,
    require_mapping,
    require_text,
    serialize_pretty,
)
from dayu.services.write_model_configuration_rollback import (
    WriteModelConfigurationRollbackBlockedError,
)
from dayu.services.write_model_configuration_rollback_application import (
    assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current,
    build_write_model_configuration_manual_recovery_evidence,
    load_write_model_configuration_manual_recovery_evidence,
    validate_write_model_configuration_manual_recovery_clearance_revocation_lineage,
)

_SELECTION_REQUEST_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_selection_request_v1"
_SELECTION_REQUEST_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_selection_request_v2"
_PLAN_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_plan_v1"
_PLAN_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_plan_v2"
_APPROVAL_REQUEST_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_approval_request_v1"
_APPROVAL_REQUEST_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_approval_request_v2"
_APPROVAL_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_approval_v1"
_APPROVAL_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_approval_v2"
_SELECTION_TYPE = "write_scene_model_routing_manual_recovery_selection"
_PLAN_TYPE = "write_scene_model_routing_manual_recovery_plan"
_APPROVAL_TYPE = "write_scene_model_routing_manual_recovery"
_SELECTION_SCOPE = "human_choice_of_one_exact_state_for_future_manual_recovery"
_PLAN_SCOPE = "exact_selected_state_plan_no_configuration_change"
_APPROVAL_SCOPE = "one_future_exact_manual_recovery_subject_to_byte_match"
_PLAN_STATUS = "ready_for_independent_manual_recovery_approval"
_APPROVAL_STATUS = "approved_for_one_future_manual_recovery"
_CONFIGURATION_DOMAIN = "write_scene_model_routing"
_MODEL_POINTER = "/model/default_name"
_SELECTED_STATES = {"applied", "preapplication"}
_READABLE_OBSERVED_STATES = {
    "applied",
    "preapplication",
    "unexpected",
}
_ROLE_ORDER = {"primary": 0, "audit": 1}
_MAX_APPROVAL_VALIDITY = timedelta(hours=4)
_SOURCE_FIELDS = {
    "path",
    "file_fingerprint",
    "content_fingerprint",
}
_SELECTION_REQUEST_FIELDS_V1 = {
    "schema_version",
    "selection_type",
    "scope",
    "selected_state",
    "selected_by",
    "selection_reference",
    "selection_reason",
    "selected_at",
    "manual_recovery_evidence_fingerprint",
    "source_transaction_id",
    "acknowledgements",
}
_SELECTION_REQUEST_FIELDS_V2 = _SELECTION_REQUEST_FIELDS_V1 | {"clearance_revocation_lineage"}
_PLAN_OPERATION_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "json_pointer",
    "observed_state",
    "expected_current_file_fingerprint",
    "selected_model_name",
    "selected_file_fingerprint",
    "selected_file_content_base64",
}
_PLAN_FIELDS_V1 = {
    "schema_version",
    "plan_type",
    "scope",
    "status",
    "ticker",
    "configuration_domain",
    "selected_state",
    "selected_by",
    "selection_reference",
    "selection_reason",
    "selected_at",
    "source_manual_recovery_evidence",
    "source_selection_request",
    "source_recovery_failed_transaction_id",
    "source_observed_configuration_state",
    "source_evidence_completeness",
    "expected_selected_routing_snapshot_fingerprint",
    "created_at",
    "operations",
    "safety_boundaries",
    "configuration_recovery_authorized",
    "configuration_recovery_performed",
    "approval_consumed",
    "model_execution_performed",
    "plan_fingerprint",
}
_PLAN_FIELDS_V2 = _PLAN_FIELDS_V1 | {"clearance_revocation_lineage"}
_APPROVAL_REQUEST_FIELDS_V1 = {
    "schema_version",
    "approval_type",
    "scope",
    "approved_by",
    "approval_reference",
    "approval_reason",
    "approved_at",
    "expires_at",
    "manual_recovery_plan_fingerprint",
    "manual_recovery_evidence_fingerprint",
    "selected_state",
    "acknowledgements",
}
_APPROVAL_REQUEST_FIELDS_V2 = _APPROVAL_REQUEST_FIELDS_V1 | {"clearance_revocation_lineage"}
_APPROVAL_FIELDS_V1 = {
    "schema_version",
    "approval_type",
    "scope",
    "status",
    "approved_by",
    "approval_reference",
    "approval_reason",
    "approved_at",
    "expires_at",
    "manual_recovery_plan_source",
    "approval_request_source",
    "manual_recovery_plan_fingerprint",
    "manual_recovery_evidence_fingerprint",
    "selected_state",
    "approval_request_fingerprint",
    "manual_recovery_plan",
    "maximum_uses",
    "acknowledgements",
    "safety_boundaries",
    "configuration_recovery_authorized",
    "configuration_recovery_performed",
    "approval_consumed",
    "model_execution_performed",
    "approval_fingerprint",
}
_APPROVAL_FIELDS_V2 = _APPROVAL_FIELDS_V1 | {"clearance_revocation_lineage"}
_SELECTION_ACKNOWLEDGEMENTS = [
    "reviewed_recovery_failed_receipt_and_manual_recovery_evidence",
    "selected_state_is_an_explicit_human_decision",
    "selection_binds_one_exact_complete_configuration_state",
    "selection_does_not_authorize_or_modify_configuration",
    "separate_independent_short_lived_approval_required",
    "separate_single_use_recovery_command_required",
    "no_recovery_command_generated",
    "no_model_execution",
]
_SELECTION_V2_ACKNOWLEDGEMENTS = [
    *_SELECTION_ACKNOWLEDGEMENTS,
    "reviewed_exact_clearance_revocation_lineage",
]
_PLAN_SAFETY_BOUNDARIES = [
    "human_selected_exact_state_only",
    "source_manual_recovery_evidence_must_remain_current",
    "applied_state_requires_complete_write_ahead_intent_evidence",
    "all_current_target_bytes_are_bound_to_the_plan",
    "all_selected_target_bytes_are_embedded_exactly",
    "independent_short_lived_approval_required",
    "separate_single_use_recovery_command_required",
    "no_configuration_mutation",
    "no_approval_consumption",
    "no_model_execution",
    "no_secret_or_model_catalog_mutation",
    "no_recovery_command_generated",
]
_PLAN_V2_SAFETY_BOUNDARIES = [
    *_PLAN_SAFETY_BOUNDARIES,
    "clearance_revocation_lineage_must_remain_current",
]
_APPROVAL_ACKNOWLEDGEMENTS = [
    "reviewed_manual_recovery_plan_and_exact_selected_bytes",
    "reviewed_current_observed_target_fingerprints",
    "approved_selected_state_matches_manual_selection",
    "approver_is_independent_from_state_selector",
    "approval_is_short_lived_and_single_use",
    "execution_requires_exact_current_byte_match",
    "failure_must_restore_exact_observed_starting_bytes",
    "issuance_does_not_modify_configuration",
    "issuance_does_not_execute_models",
]
_APPROVAL_V2_ACKNOWLEDGEMENTS = [
    *_APPROVAL_ACKNOWLEDGEMENTS,
    "approved_exact_clearance_revocation_lineage",
]
_APPROVAL_SAFETY_BOUNDARIES = [
    "one_future_exact_manual_recovery_only",
    "approver_must_differ_from_state_selector",
    "source_evidence_plan_and_selection_must_remain_current",
    "all_current_target_bytes_must_match_plan",
    "selected_manifest_bytes_only",
    "single_use_consumption_required_before_first_replace",
    "failure_restores_exact_observed_starting_bytes",
    "issuance_does_not_modify_configuration",
    "no_model_execution",
    "no_secret_or_model_catalog_mutation",
]
_APPROVAL_V2_SAFETY_BOUNDARIES = [
    *_APPROVAL_SAFETY_BOUNDARIES,
    "clearance_revocation_lineage_must_remain_current",
]


def _exact_fields(
    payload: Mapping[str, Any],
    *,
    expected: set[str],
    name: str,
) -> None:
    actual = set(payload)
    if actual == expected:
        return
    raise ValueError(
        f"{name} fields are invalid: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
    )


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
        raise ValueError(f"{name} schema_version is invalid")
    _exact_fields(payload, expected=fields_v2, name=name)
    lineage = require_mapping(
        payload.get("clearance_revocation_lineage"),
        name=f"{name} clearance_revocation_lineage",
    )
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
            canonical_json_bytes(left),
            canonical_json_bytes(right),
        )
    ):
        raise WriteModelConfigurationRollbackBlockedError(message)


def _target_path(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> Path:
    text = require_text(
        value,
        name=name,
        maximum_length=32_768,
    )
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return Path(os.path.abspath(str(path)))


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _parse_utc(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> datetime:
    text = require_text(value, name=name, maximum_length=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _validated_fingerprint(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> str:
    text = require_text(value, name=name, maximum_length=128)
    prefix = "sha256:"
    digest = text.removeprefix(prefix)
    if not text.startswith(prefix) or len(digest) != 64:
        raise ValueError(f"{name} must be a SHA-256 fingerprint")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a SHA-256 fingerprint") from exc
    return text


def _validate_source(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> dict[str, str]:
    source = require_mapping(value, name=name)
    _exact_fields(source, expected=_SOURCE_FIELDS, name=name)
    return {
        "path": str(
            absolute_path(
                require_text(
                    source.get("path"),
                    name=f"{name}.path",
                    maximum_length=32_768,
                ),
                name=f"{name}.path",
            )
        ),
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
        "path": str(path),
        "file_fingerprint": file_fingerprint(path),
        "content_fingerprint": content_fingerprint,
    }


def _assert_source_file(
    source: Mapping[str, str],
    *,
    name: str,
) -> Path:
    path = absolute_path(
        require_text(
            source.get("path"),
            name=f"{name}.path",
            maximum_length=32_768,
        ),
        name=f"{name}.path",
    )
    try:
        current_fingerprint = file_fingerprint(path)
    except (FileNotFoundError, OSError) as exc:
        raise WriteModelConfigurationRollbackBlockedError(f"{name} is unavailable") from exc
    if not hmac.compare_digest(
        source["file_fingerprint"],
        current_fingerprint,
    ):
        raise WriteModelConfigurationRollbackBlockedError(f"{name} file changed")
    return path


def _load_json_object(
    path: str | Path,
    *,
    name: str,
) -> tuple[Path, dict[str, Any]]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"{name} does not exist: {target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return target, payload


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
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = serialize_pretty(payload)
    _assert_immutable_target_not_symlink(target)
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
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_path, target)
        except FileExistsError:
            _assert_immutable_target_not_symlink(target)
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = None
            if existing != dict(payload):
                raise FileExistsError(f"artifact already exists with different content: {target}") from None
        _assert_immutable_target_not_symlink(target)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return target


def _operation_key(value: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(value.get("role") or ""),
        str(value.get("scene_name") or ""),
    )


def _operation_sort_key(value: Mapping[str, Any]) -> tuple[int, str]:
    return (
        _ROLE_ORDER.get(str(value.get("role") or ""), 99),
        str(value.get("scene_name") or ""),
    )


def _validate_manifest_candidate(
    *,
    content: bytes,
    expected_model_name: str,
    name: str,
) -> None:
    try:
        manifest = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} is not a UTF-8 JSON manifest") from exc
    manifest_view = require_mapping(manifest, name=f"{name} manifest")
    model = require_mapping(
        manifest_view.get("model"),
        name=f"{name} manifest.model",
    )
    if model.get("default_name") != expected_model_name:
        raise ValueError(f"{name} does not contain the selected model")


def _stable_evidence_view(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    stable = dict(evidence)
    stable.pop("created_at", None)
    stable.pop("evidence_fingerprint", None)
    return stable


def _stable_plan_view(plan: Mapping[str, Any]) -> dict[str, Any]:
    stable = dict(plan)
    stable.pop("created_at", None)
    stable.pop("plan_fingerprint", None)
    return stable


def _clearance_revocation_lineage(
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    value = payload.get("clearance_revocation_lineage")
    if value is None:
        return None
    lineage = require_mapping(
        value,
        name="clearance_revocation_lineage",
    )
    validate_write_model_configuration_manual_recovery_clearance_revocation_lineage(lineage)
    return dict(lineage)


def _refresh_manual_recovery_evidence(
    *,
    evidence: Mapping[str, Any],
    config_root: str | Path,
    now: datetime,
) -> dict[str, Any]:
    receipt_source = _validate_source(
        evidence.get("source_rollback_receipt"),
        name="source_rollback_receipt",
    )
    refreshed = build_write_model_configuration_manual_recovery_evidence(
        rollback_receipt_path=receipt_source["path"],
        config_root=config_root,
        expected_ticker=str(evidence["ticker"]),
        now=now,
        clearance_revocation_lineage=(_clearance_revocation_lineage(evidence)),
    )
    if _stable_evidence_view(refreshed) != _stable_evidence_view(evidence):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery evidence is no longer current")
    return refreshed


def validate_write_model_configuration_manual_recovery_selection_request(
    payload: Mapping[str, Any],
) -> None:
    """Validate one explicit human state selection."""

    request = require_mapping(payload, name="manual recovery selection request")
    lineage = _validate_versioned_clearance_revocation_lineage(
        request,
        schema_version_v1=_SELECTION_REQUEST_SCHEMA_VERSION_V1,
        schema_version_v2=_SELECTION_REQUEST_SCHEMA_VERSION_V2,
        fields_v1=_SELECTION_REQUEST_FIELDS_V1,
        fields_v2=_SELECTION_REQUEST_FIELDS_V2,
        name="manual recovery selection request",
    )
    constants = {
        "selection_type": _SELECTION_TYPE,
        "scope": _SELECTION_SCOPE,
    }
    for field_name, expected_value in constants.items():
        if request.get(field_name) != expected_value:
            raise ValueError(f"manual recovery selection {field_name} is invalid")
    if request.get("selected_state") not in _SELECTED_STATES:
        raise ValueError("manual recovery selected_state is invalid")
    require_text(
        request.get("selected_by"),
        name="selected_by",
        maximum_length=200,
    )
    require_text(
        request.get("selection_reference"),
        name="selection_reference",
        maximum_length=500,
    )
    require_text(
        request.get("selection_reason"),
        name="selection_reason",
        maximum_length=2_000,
    )
    _parse_utc(request.get("selected_at"), name="selected_at")
    _validated_fingerprint(
        request.get("manual_recovery_evidence_fingerprint"),
        name="manual_recovery_evidence_fingerprint",
    )
    require_text(
        request.get("source_transaction_id"),
        name="source_transaction_id",
        maximum_length=64,
    )
    expected_acknowledgements = _SELECTION_V2_ACKNOWLEDGEMENTS if lineage is not None else _SELECTION_ACKNOWLEDGEMENTS
    if request.get("acknowledgements") != expected_acknowledgements:
        raise ValueError("manual recovery selection acknowledgements are invalid")


def load_write_model_configuration_manual_recovery_selection_request(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one persisted human state selection."""

    target, payload = _load_json_object(
        path,
        name="manual recovery selection request",
    )
    validate_write_model_configuration_manual_recovery_selection_request(payload)
    return target, payload


def _build_plan_operations(
    *,
    evidence: Mapping[str, Any],
    selected_state: str,
) -> list[dict[str, Any]]:
    raw_operations = evidence.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("manual recovery evidence operations are empty")
    operations: list[dict[str, Any]] = []
    for index, raw_operation in enumerate(raw_operations):
        source = require_mapping(
            raw_operation,
            name=f"evidence.operations[{index}]",
        )
        observed_state = str(source["observed_state"])
        observed_fingerprint = source.get("observed_file_fingerprint")
        if observed_state not in _READABLE_OBSERVED_STATES or observed_fingerprint is None:
            raise WriteModelConfigurationRollbackBlockedError("manual recovery target state is not safely readable")
        target = _target_path(
            source.get("target_manifest_path"),
            name=f"evidence.operations[{index}].target_manifest_path",
        )
        if target.is_symlink() or not target.is_file():
            raise WriteModelConfigurationRollbackBlockedError(
                f"manual recovery target for {source['scene_name']!r} is unavailable"
            )
        current_fingerprint = file_fingerprint(target)
        expected_current_fingerprint = _validated_fingerprint(
            observed_fingerprint,
            name=(f"evidence.operations[{index}].observed_file_fingerprint"),
        )
        if not hmac.compare_digest(
            current_fingerprint,
            expected_current_fingerprint,
        ):
            raise WriteModelConfigurationRollbackBlockedError(
                f"manual recovery target for {source['scene_name']!r} changed"
            )
        if selected_state == "applied":
            if source.get("applied_candidate_available") is not True:
                raise WriteModelConfigurationRollbackBlockedError("exact applied candidate bytes are unavailable")
            selected_model_name = str(source["expected_applied_model_name"])
            selected_fingerprint = str(source["expected_applied_file_fingerprint"])
            selected_content = source["applied_file_content_base64"]
        else:
            if source.get("preapplication_candidate_available") is not True:
                raise WriteModelConfigurationRollbackBlockedError(
                    "exact preapplication candidate bytes are unavailable"
                )
            selected_model_name = str(source["expected_preapplication_model_name"])
            selected_fingerprint = str(source["expected_preapplication_file_fingerprint"])
            selected_content = source["preapplication_file_content_base64"]
        selected_bytes = decode_base64_strict(
            require_text(
                selected_content,
                name=f"selected bytes for {source['scene_name']}",
                maximum_length=1_000_000,
            ),
            name=f"selected bytes for {source['scene_name']}",
        )
        if not hmac.compare_digest(
            bytes_fingerprint(selected_bytes),
            selected_fingerprint,
        ):
            raise ValueError(f"selected bytes for {source['scene_name']!r} changed")
        _validate_manifest_candidate(
            content=selected_bytes,
            expected_model_name=selected_model_name,
            name=f"selected bytes for {source['scene_name']}",
        )
        operations.append(
            {
                "role": source["role"],
                "scene_name": source["scene_name"],
                "target_manifest_path": str(target),
                "json_pointer": _MODEL_POINTER,
                "observed_state": observed_state,
                "expected_current_file_fingerprint": (expected_current_fingerprint),
                "selected_model_name": selected_model_name,
                "selected_file_fingerprint": selected_fingerprint,
                "selected_file_content_base64": selected_content,
            }
        )
    operations.sort(key=_operation_sort_key)
    return operations


def build_write_model_configuration_manual_recovery_plan(
    *,
    manual_recovery_evidence_path: str | Path,
    selection_request_path: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    now: datetime,
) -> dict[str, Any]:
    """Build a read-only exact-state plan from a human selection."""

    current_time = _normalize_now(now)
    normalized_ticker = require_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    evidence_path, evidence = load_write_model_configuration_manual_recovery_evidence(manual_recovery_evidence_path)
    selection_path, selection = load_write_model_configuration_manual_recovery_selection_request(selection_request_path)
    evidence_lineage = _clearance_revocation_lineage(evidence)
    selection_lineage = _clearance_revocation_lineage(selection)
    _assert_same_clearance_revocation_lineage(
        evidence_lineage,
        selection_lineage,
        message=("manual recovery selection clearance revocation lineage does not match the evidence"),
    )
    if evidence.get("ticker") != normalized_ticker:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery evidence ticker does not match the command")
    evidence_created_at = _parse_utc(
        evidence.get("created_at"),
        name="evidence.created_at",
    )
    selected_at = _parse_utc(
        selection.get("selected_at"),
        name="selection.selected_at",
    )
    if selected_at <= evidence_created_at:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery selection must follow the evidence")
    if current_time < selected_at:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery selection is not effective yet")
    expected_selection_identity = {
        "manual_recovery_evidence_fingerprint": evidence["evidence_fingerprint"],
        "source_transaction_id": evidence["transaction_id"],
    }
    if any(
        selection.get(field_name) != expected_value
        for field_name, expected_value in (expected_selection_identity.items())
    ):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery selection does not match the evidence")
    selected_state = str(selection["selected_state"])
    if selected_state == "applied" and evidence.get("evidence_completeness") != "complete":
        raise WriteModelConfigurationRollbackBlockedError("applied recovery requires complete evidence")
    _refresh_manual_recovery_evidence(
        evidence=evidence,
        config_root=config_root,
        now=current_time,
    )
    operations = _build_plan_operations(
        evidence=evidence,
        selected_state=selected_state,
    )
    selected_routing_fingerprint = (
        evidence["source_applied_routing_snapshot_fingerprint"]
        if selected_state == "applied"
        else evidence["expected_preapplication_routing_snapshot_fingerprint"]
    )
    payload: dict[str, Any] = {
        "schema_version": (_PLAN_SCHEMA_VERSION_V2 if evidence_lineage is not None else _PLAN_SCHEMA_VERSION_V1),
        "plan_type": _PLAN_TYPE,
        "scope": _PLAN_SCOPE,
        "status": _PLAN_STATUS,
        "ticker": evidence["ticker"],
        "configuration_domain": _CONFIGURATION_DOMAIN,
        "selected_state": selected_state,
        "selected_by": selection["selected_by"],
        "selection_reference": selection["selection_reference"],
        "selection_reason": selection["selection_reason"],
        "selected_at": format_utc(selected_at),
        "source_manual_recovery_evidence": _source_reference(
            path=evidence_path,
            content_fingerprint=str(evidence["evidence_fingerprint"]),
        ),
        "source_selection_request": _source_reference(
            path=selection_path,
            content_fingerprint=fingerprint_bytes(selection),
        ),
        "source_recovery_failed_transaction_id": evidence["transaction_id"],
        "source_observed_configuration_state": evidence["observed_configuration_state"],
        "source_evidence_completeness": evidence["evidence_completeness"],
        "expected_selected_routing_snapshot_fingerprint": (selected_routing_fingerprint),
        "created_at": format_utc(current_time),
        "operations": operations,
        "safety_boundaries": list(
            _PLAN_V2_SAFETY_BOUNDARIES if evidence_lineage is not None else _PLAN_SAFETY_BOUNDARIES
        ),
        "configuration_recovery_authorized": False,
        "configuration_recovery_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    if evidence_lineage is not None:
        payload["clearance_revocation_lineage"] = dict(evidence_lineage)
    payload["plan_fingerprint"] = fingerprint_bytes(payload)
    validate_write_model_configuration_manual_recovery_plan(payload)
    return payload


def _validate_plan_operation(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> dict[str, Any]:
    operation = require_mapping(value, name=name)
    _exact_fields(
        operation,
        expected=_PLAN_OPERATION_FIELDS,
        name=name,
    )
    normalized: dict[str, Any] = {
        "role": require_text(
            operation.get("role"),
            name=f"{name}.role",
            maximum_length=32,
        ),
        "scene_name": require_text(
            operation.get("scene_name"),
            name=f"{name}.scene_name",
            maximum_length=128,
        ),
        "target_manifest_path": str(
            _target_path(
                operation.get("target_manifest_path"),
                name=f"{name}.target_manifest_path",
            )
        ),
        "json_pointer": operation.get("json_pointer"),
        "observed_state": operation.get("observed_state"),
        "expected_current_file_fingerprint": (
            _validated_fingerprint(
                operation.get("expected_current_file_fingerprint"),
                name=f"{name}.expected_current_file_fingerprint",
            )
        ),
        "selected_model_name": require_text(
            operation.get("selected_model_name"),
            name=f"{name}.selected_model_name",
            maximum_length=256,
        ),
        "selected_file_fingerprint": _validated_fingerprint(
            operation.get("selected_file_fingerprint"),
            name=f"{name}.selected_file_fingerprint",
        ),
        "selected_file_content_base64": operation.get("selected_file_content_base64"),
    }
    if normalized["role"] not in _ROLE_ORDER:
        raise ValueError(f"{name}.role is invalid")
    if normalized["json_pointer"] != _MODEL_POINTER:
        raise ValueError(f"{name}.json_pointer is invalid")
    if normalized["observed_state"] not in (_READABLE_OBSERVED_STATES):
        raise ValueError(f"{name}.observed_state is invalid")
    selected_bytes = decode_base64_strict(
        require_text(
            normalized["selected_file_content_base64"],
            name=f"{name}.selected_file_content_base64",
            maximum_length=1_000_000,
        ),
        name=f"{name}.selected_file_content_base64",
    )
    if not hmac.compare_digest(
        bytes_fingerprint(selected_bytes),
        normalized["selected_file_fingerprint"],
    ):
        raise ValueError(f"{name} selected bytes fingerprint mismatch")
    _validate_manifest_candidate(
        content=selected_bytes,
        expected_model_name=normalized["selected_model_name"],
        name=f"{name}.selected_file_content_base64",
    )
    return normalized


def validate_write_model_configuration_manual_recovery_plan(
    payload: Mapping[str, Any],
) -> None:
    """Validate one immutable exact-state manual recovery plan."""

    plan = require_mapping(payload, name="manual recovery plan")
    lineage = _validate_versioned_clearance_revocation_lineage(
        plan,
        schema_version_v1=_PLAN_SCHEMA_VERSION_V1,
        schema_version_v2=_PLAN_SCHEMA_VERSION_V2,
        fields_v1=_PLAN_FIELDS_V1,
        fields_v2=_PLAN_FIELDS_V2,
        name="manual recovery plan",
    )
    constants = {
        "plan_type": _PLAN_TYPE,
        "scope": _PLAN_SCOPE,
        "status": _PLAN_STATUS,
        "configuration_domain": _CONFIGURATION_DOMAIN,
    }
    for field_name, expected_value in constants.items():
        if plan.get(field_name) != expected_value:
            raise ValueError(f"manual recovery plan {field_name} is invalid")
    require_text(plan.get("ticker"), name="ticker", maximum_length=64)
    if plan.get("selected_state") not in _SELECTED_STATES:
        raise ValueError("manual recovery plan selected_state is invalid")
    require_text(
        plan.get("selected_by"),
        name="selected_by",
        maximum_length=200,
    )
    require_text(
        plan.get("selection_reference"),
        name="selection_reference",
        maximum_length=500,
    )
    require_text(
        plan.get("selection_reason"),
        name="selection_reason",
        maximum_length=2_000,
    )
    selected_at = _parse_utc(
        plan.get("selected_at"),
        name="selected_at",
    )
    created_at = _parse_utc(
        plan.get("created_at"),
        name="created_at",
    )
    if created_at < selected_at:
        raise ValueError("manual recovery plan predates its selection")
    _validate_source(
        plan.get("source_manual_recovery_evidence"),
        name="source_manual_recovery_evidence",
    )
    _validate_source(
        plan.get("source_selection_request"),
        name="source_selection_request",
    )
    require_text(
        plan.get("source_recovery_failed_transaction_id"),
        name="source_recovery_failed_transaction_id",
        maximum_length=64,
    )
    require_text(
        plan.get("source_observed_configuration_state"),
        name="source_observed_configuration_state",
        maximum_length=64,
    )
    completeness = plan.get("source_evidence_completeness")
    if completeness not in {"complete", "partial"}:
        raise ValueError("manual recovery plan evidence completeness is invalid")
    if plan.get("selected_state") == "applied" and (completeness != "complete"):
        raise ValueError("applied manual recovery plan requires complete evidence")
    _validated_fingerprint(
        plan.get("expected_selected_routing_snapshot_fingerprint"),
        name="expected_selected_routing_snapshot_fingerprint",
    )
    raw_operations = plan.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("manual recovery plan operations must be non-empty")
    operations = [
        _validate_plan_operation(
            operation,
            name=f"operations[{index}]",
        )
        for index, operation in enumerate(raw_operations)
    ]
    if operations != sorted(operations, key=_operation_sort_key):
        raise ValueError("manual recovery plan operations are not ordered")
    identities = [_operation_key(operation) for operation in operations]
    paths = [operation["target_manifest_path"] for operation in operations]
    if len(identities) != len(set(identities)) or len(paths) != len(set(paths)):
        raise ValueError("manual recovery plan operations contain duplicates")
    expected_safety_boundaries = _PLAN_V2_SAFETY_BOUNDARIES if lineage is not None else _PLAN_SAFETY_BOUNDARIES
    if plan.get("safety_boundaries") != expected_safety_boundaries:
        raise ValueError("manual recovery plan safety boundaries are invalid")
    expected_flags: dict[str, bool] = {
        "configuration_recovery_authorized": False,
        "configuration_recovery_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    for field_name, expected_flag in expected_flags.items():
        if plan.get(field_name) is not expected_flag:
            raise ValueError(f"manual recovery plan {field_name} is invalid")
    fingerprint = _validated_fingerprint(
        plan.get("plan_fingerprint"),
        name="plan_fingerprint",
    )
    unsigned = dict(plan)
    unsigned.pop("plan_fingerprint", None)
    if not hmac.compare_digest(fingerprint, fingerprint_bytes(unsigned)):
        raise ValueError("manual recovery plan fingerprint mismatch")


def load_write_model_configuration_manual_recovery_plan(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable manual recovery plan."""

    target, payload = _load_json_object(
        path,
        name="manual recovery plan",
    )
    validate_write_model_configuration_manual_recovery_plan(payload)
    return target, payload


def assert_write_model_configuration_manual_recovery_plan_current(
    *,
    plan: Mapping[str, Any],
    config_root: str | Path,
    now: datetime,
) -> None:
    """Block unless every source and target still matches the plan."""

    validate_write_model_configuration_manual_recovery_plan(plan)
    current_time = _normalize_now(now)
    if current_time < _parse_utc(
        plan.get("created_at"),
        name="plan.created_at",
    ):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery plan is not effective yet")
    evidence_source = _validate_source(
        plan.get("source_manual_recovery_evidence"),
        name="source_manual_recovery_evidence",
    )
    evidence_path = _assert_source_file(
        evidence_source,
        name="source manual recovery evidence",
    )
    _resolved_evidence_path, evidence = load_write_model_configuration_manual_recovery_evidence(evidence_path)
    if not hmac.compare_digest(
        evidence_source["content_fingerprint"],
        str(evidence["evidence_fingerprint"]),
    ):
        raise WriteModelConfigurationRollbackBlockedError("source manual recovery evidence content changed")
    selection_source = _validate_source(
        plan.get("source_selection_request"),
        name="source_selection_request",
    )
    selection_path = _assert_source_file(
        selection_source,
        name="source manual recovery selection",
    )
    _resolved_selection_path, selection = load_write_model_configuration_manual_recovery_selection_request(
        selection_path
    )
    if not hmac.compare_digest(
        selection_source["content_fingerprint"],
        fingerprint_bytes(selection),
    ):
        raise WriteModelConfigurationRollbackBlockedError("source manual recovery selection content changed")
    plan_lineage = _clearance_revocation_lineage(plan)
    evidence_lineage = _clearance_revocation_lineage(evidence)
    selection_lineage = _clearance_revocation_lineage(selection)
    _assert_same_clearance_revocation_lineage(
        plan_lineage,
        evidence_lineage,
        message=("manual recovery plan clearance revocation lineage differs from the evidence"),
    )
    _assert_same_clearance_revocation_lineage(
        plan_lineage,
        selection_lineage,
        message=("manual recovery plan clearance revocation lineage differs from the selection"),
    )
    if plan_lineage is not None:
        try:
            assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current(plan_lineage)
        except (
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise WriteModelConfigurationRollbackBlockedError(
                "manual recovery clearance revocation lineage is no longer current"
            ) from exc
    refreshed_plan = build_write_model_configuration_manual_recovery_plan(
        manual_recovery_evidence_path=evidence_path,
        selection_request_path=selection_path,
        config_root=config_root,
        expected_ticker=str(plan["ticker"]),
        now=current_time,
    )
    if _stable_plan_view(refreshed_plan) != _stable_plan_view(plan):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery plan is no longer current")


def persist_write_model_configuration_manual_recovery_plan(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist one immutable exact-state recovery plan."""

    validate_write_model_configuration_manual_recovery_plan(payload)
    return _persist_immutable(payload, path)


def validate_write_model_configuration_manual_recovery_approval_request(
    payload: Mapping[str, Any],
) -> None:
    """Validate one independent manual recovery approval request."""

    request = require_mapping(payload, name="manual recovery approval request")
    lineage = _validate_versioned_clearance_revocation_lineage(
        request,
        schema_version_v1=_APPROVAL_REQUEST_SCHEMA_VERSION_V1,
        schema_version_v2=_APPROVAL_REQUEST_SCHEMA_VERSION_V2,
        fields_v1=_APPROVAL_REQUEST_FIELDS_V1,
        fields_v2=_APPROVAL_REQUEST_FIELDS_V2,
        name="manual recovery approval request",
    )
    constants = {
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
    }
    for field_name, expected_value in constants.items():
        if request.get(field_name) != expected_value:
            raise ValueError(f"manual recovery approval request {field_name} is invalid")
    require_text(
        request.get("approved_by"),
        name="approved_by",
        maximum_length=200,
    )
    require_text(
        request.get("approval_reference"),
        name="approval_reference",
        maximum_length=500,
    )
    require_text(
        request.get("approval_reason"),
        name="approval_reason",
        maximum_length=2_000,
    )
    approved_at = _parse_utc(
        request.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc(
        request.get("expires_at"),
        name="expires_at",
    )
    if expires_at <= approved_at:
        raise ValueError("manual recovery approval must expire later")
    if expires_at - approved_at > _MAX_APPROVAL_VALIDITY:
        raise ValueError("manual recovery approval validity exceeds four hours")
    _validated_fingerprint(
        request.get("manual_recovery_plan_fingerprint"),
        name="manual_recovery_plan_fingerprint",
    )
    _validated_fingerprint(
        request.get("manual_recovery_evidence_fingerprint"),
        name="manual_recovery_evidence_fingerprint",
    )
    if request.get("selected_state") not in _SELECTED_STATES:
        raise ValueError("manual recovery approval selected_state is invalid")
    expected_acknowledgements = _APPROVAL_V2_ACKNOWLEDGEMENTS if lineage is not None else _APPROVAL_ACKNOWLEDGEMENTS
    if request.get("acknowledgements") != expected_acknowledgements:
        raise ValueError("manual recovery approval acknowledgements are invalid")


def load_write_model_configuration_manual_recovery_approval_request(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one independent approval request."""

    target, payload = _load_json_object(
        path,
        name="manual recovery approval request",
    )
    validate_write_model_configuration_manual_recovery_approval_request(payload)
    return target, payload


def build_write_model_configuration_manual_recovery_approval(
    *,
    approval_request_path: str | Path,
    manual_recovery_plan_path: str | Path,
    config_root: str | Path,
    now: datetime,
) -> dict[str, Any]:
    """Issue a short-lived single-use credential without mutation."""

    current_time = _normalize_now(now)
    request_path, request = load_write_model_configuration_manual_recovery_approval_request(approval_request_path)
    plan_path, plan = load_write_model_configuration_manual_recovery_plan(manual_recovery_plan_path)
    plan_lineage = _clearance_revocation_lineage(plan)
    request_lineage = _clearance_revocation_lineage(request)
    _assert_same_clearance_revocation_lineage(
        plan_lineage,
        request_lineage,
        message=("manual recovery approval request clearance revocation lineage does not match the plan"),
    )
    assert_write_model_configuration_manual_recovery_plan_current(
        plan=plan,
        config_root=config_root,
        now=current_time,
    )
    approved_at = _parse_utc(
        request.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc(
        request.get("expires_at"),
        name="expires_at",
    )
    if approved_at <= _parse_utc(
        plan.get("created_at"),
        name="plan.created_at",
    ):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval must follow the plan")
    if current_time < approved_at:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval is not effective yet")
    if current_time >= expires_at:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval has expired")
    selected_by = require_text(
        plan.get("selected_by"),
        name="selected_by",
        maximum_length=200,
    )
    approved_by = require_text(
        request.get("approved_by"),
        name="approved_by",
        maximum_length=200,
    )
    if selected_by.casefold() == approved_by.casefold():
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approver must differ from state selector")
    evidence_source = _validate_source(
        plan.get("source_manual_recovery_evidence"),
        name="source_manual_recovery_evidence",
    )
    expected_identity = {
        "manual_recovery_plan_fingerprint": plan["plan_fingerprint"],
        "manual_recovery_evidence_fingerprint": evidence_source["content_fingerprint"],
        "selected_state": plan["selected_state"],
    }
    if any(request.get(field_name) != expected_value for field_name, expected_value in expected_identity.items()):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval request does not match the plan")
    payload: dict[str, Any] = {
        "schema_version": (_APPROVAL_SCHEMA_VERSION_V2 if plan_lineage is not None else _APPROVAL_SCHEMA_VERSION_V1),
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
        "status": _APPROVAL_STATUS,
        "approved_by": approved_by,
        "approval_reference": request["approval_reference"],
        "approval_reason": request["approval_reason"],
        "approved_at": format_utc(approved_at),
        "expires_at": format_utc(expires_at),
        "manual_recovery_plan_source": _source_reference(
            path=plan_path,
            content_fingerprint=str(plan["plan_fingerprint"]),
        ),
        "approval_request_source": _source_reference(
            path=request_path,
            content_fingerprint=fingerprint_bytes(request),
        ),
        **expected_identity,
        "approval_request_fingerprint": fingerprint_bytes(request),
        "manual_recovery_plan": dict(plan),
        "maximum_uses": 1,
        "acknowledgements": list(
            _APPROVAL_V2_ACKNOWLEDGEMENTS if plan_lineage is not None else _APPROVAL_ACKNOWLEDGEMENTS
        ),
        "safety_boundaries": list(
            _APPROVAL_V2_SAFETY_BOUNDARIES if plan_lineage is not None else _APPROVAL_SAFETY_BOUNDARIES
        ),
        "configuration_recovery_authorized": True,
        "configuration_recovery_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    if plan_lineage is not None:
        payload["clearance_revocation_lineage"] = dict(plan_lineage)
    payload["approval_fingerprint"] = fingerprint_bytes(payload)
    validate_write_model_configuration_manual_recovery_approval(payload)
    return payload


def validate_write_model_configuration_manual_recovery_approval(
    payload: Mapping[str, Any],
) -> None:
    """Validate one strict single-use manual recovery approval."""

    approval = require_mapping(payload, name="manual recovery approval")
    lineage = _validate_versioned_clearance_revocation_lineage(
        approval,
        schema_version_v1=_APPROVAL_SCHEMA_VERSION_V1,
        schema_version_v2=_APPROVAL_SCHEMA_VERSION_V2,
        fields_v1=_APPROVAL_FIELDS_V1,
        fields_v2=_APPROVAL_FIELDS_V2,
        name="manual recovery approval",
    )
    constants = {
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
        "status": _APPROVAL_STATUS,
    }
    for field_name, expected_value in constants.items():
        if approval.get(field_name) != expected_value:
            raise ValueError(f"manual recovery approval {field_name} is invalid")
    approved_by = require_text(
        approval.get("approved_by"),
        name="approved_by",
        maximum_length=200,
    )
    require_text(
        approval.get("approval_reference"),
        name="approval_reference",
        maximum_length=500,
    )
    require_text(
        approval.get("approval_reason"),
        name="approval_reason",
        maximum_length=2_000,
    )
    approved_at = _parse_utc(
        approval.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc(
        approval.get("expires_at"),
        name="expires_at",
    )
    if expires_at <= approved_at or expires_at - approved_at > _MAX_APPROVAL_VALIDITY:
        raise ValueError("manual recovery approval window is invalid")
    plan_source = _validate_source(
        approval.get("manual_recovery_plan_source"),
        name="manual_recovery_plan_source",
    )
    request_source = _validate_source(
        approval.get("approval_request_source"),
        name="approval_request_source",
    )
    plan_fingerprint = _validated_fingerprint(
        approval.get("manual_recovery_plan_fingerprint"),
        name="manual_recovery_plan_fingerprint",
    )
    evidence_fingerprint = _validated_fingerprint(
        approval.get("manual_recovery_evidence_fingerprint"),
        name="manual_recovery_evidence_fingerprint",
    )
    if approval.get("selected_state") not in _SELECTED_STATES:
        raise ValueError("manual recovery approval selected_state is invalid")
    request_fingerprint = _validated_fingerprint(
        approval.get("approval_request_fingerprint"),
        name="approval_request_fingerprint",
    )
    if not hmac.compare_digest(
        request_source["content_fingerprint"],
        request_fingerprint,
    ):
        raise ValueError("manual recovery approval request identities differ")
    embedded_plan = require_mapping(
        approval.get("manual_recovery_plan"),
        name="manual_recovery_plan",
    )
    validate_write_model_configuration_manual_recovery_plan(embedded_plan)
    embedded_plan_lineage = _clearance_revocation_lineage(embedded_plan)
    if (lineage is None) != (embedded_plan_lineage is None) or (
        lineage is not None
        and embedded_plan_lineage is not None
        and not hmac.compare_digest(
            canonical_json_bytes(lineage),
            canonical_json_bytes(embedded_plan_lineage),
        )
    ):
        raise ValueError("manual recovery approval clearance revocation lineage is inconsistent")
    embedded_evidence_source = _validate_source(
        embedded_plan.get("source_manual_recovery_evidence"),
        name="embedded source_manual_recovery_evidence",
    )
    if not (
        hmac.compare_digest(
            plan_source["content_fingerprint"],
            plan_fingerprint,
        )
        and hmac.compare_digest(
            str(embedded_plan["plan_fingerprint"]),
            plan_fingerprint,
        )
        and hmac.compare_digest(
            embedded_evidence_source["content_fingerprint"],
            evidence_fingerprint,
        )
        and approval.get("selected_state") == embedded_plan.get("selected_state")
    ):
        raise ValueError("manual recovery approval identities are inconsistent")
    selected_by = require_text(
        embedded_plan.get("selected_by"),
        name="embedded selected_by",
        maximum_length=200,
    )
    if selected_by.casefold() == approved_by.casefold():
        raise ValueError("manual recovery approval is not independently approved")
    if approval.get("maximum_uses") != 1:
        raise ValueError("manual recovery approval maximum_uses is invalid")
    expected_acknowledgements = _APPROVAL_V2_ACKNOWLEDGEMENTS if lineage is not None else _APPROVAL_ACKNOWLEDGEMENTS
    if approval.get("acknowledgements") != expected_acknowledgements:
        raise ValueError("manual recovery approval acknowledgements are invalid")
    expected_safety_boundaries = _APPROVAL_V2_SAFETY_BOUNDARIES if lineage is not None else _APPROVAL_SAFETY_BOUNDARIES
    if approval.get("safety_boundaries") != (expected_safety_boundaries):
        raise ValueError("manual recovery approval safety boundaries are invalid")
    expected_flags: dict[str, bool] = {
        "configuration_recovery_authorized": True,
        "configuration_recovery_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    for field_name, expected_flag in expected_flags.items():
        if approval.get(field_name) is not expected_flag:
            raise ValueError(f"manual recovery approval {field_name} is invalid")
    fingerprint = _validated_fingerprint(
        approval.get("approval_fingerprint"),
        name="approval_fingerprint",
    )
    unsigned = dict(approval)
    unsigned.pop("approval_fingerprint", None)
    if not hmac.compare_digest(fingerprint, fingerprint_bytes(unsigned)):
        raise ValueError("manual recovery approval fingerprint mismatch")


def load_write_model_configuration_manual_recovery_approval(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable manual recovery approval."""

    target, payload = _load_json_object(
        path,
        name="manual recovery approval",
    )
    validate_write_model_configuration_manual_recovery_approval(payload)
    return target, payload


def assert_write_model_configuration_manual_recovery_approval_current(
    *,
    approval: Mapping[str, Any],
    manual_recovery_plan_path: str | Path,
    config_root: str | Path,
    now: datetime,
) -> dict[str, Any]:
    """Return the persisted plan only while approval remains executable."""

    validate_write_model_configuration_manual_recovery_approval(approval)
    current_time = _normalize_now(now)
    approved_at = _parse_utc(
        approval.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc(
        approval.get("expires_at"),
        name="expires_at",
    )
    if current_time < approved_at:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval is not effective yet")
    if current_time >= expires_at:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval has expired")
    resolved_plan_path, plan = load_write_model_configuration_manual_recovery_plan(manual_recovery_plan_path)
    plan_source = _validate_source(
        approval.get("manual_recovery_plan_source"),
        name="manual_recovery_plan_source",
    )
    if str(resolved_plan_path) != plan_source["path"]:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval is bound to another plan path")
    _assert_source_file(
        plan_source,
        name="approved manual recovery plan",
    )
    if not hmac.compare_digest(
        str(plan["plan_fingerprint"]),
        str(approval["manual_recovery_plan_fingerprint"]),
    ):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval plan fingerprint changed")
    embedded_plan = require_mapping(
        approval.get("manual_recovery_plan"),
        name="embedded manual recovery plan",
    )
    if not hmac.compare_digest(
        canonical_json_bytes(plan),
        canonical_json_bytes(embedded_plan),
    ):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval embedded plan changed")
    request_source = _validate_source(
        approval.get("approval_request_source"),
        name="approval_request_source",
    )
    request_path = _assert_source_file(
        request_source,
        name="manual recovery approval request",
    )
    _resolved_request_path, request = load_write_model_configuration_manual_recovery_approval_request(request_path)
    if not hmac.compare_digest(
        fingerprint_bytes(request),
        str(approval["approval_request_fingerprint"]),
    ):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery approval request content changed")
    approval_lineage = _clearance_revocation_lineage(approval)
    plan_lineage = _clearance_revocation_lineage(plan)
    request_lineage = _clearance_revocation_lineage(request)
    _assert_same_clearance_revocation_lineage(
        approval_lineage,
        plan_lineage,
        message=("manual recovery approval clearance revocation lineage differs from the plan"),
    )
    _assert_same_clearance_revocation_lineage(
        approval_lineage,
        request_lineage,
        message=("manual recovery approval clearance revocation lineage differs from the request"),
    )
    assert_write_model_configuration_manual_recovery_plan_current(
        plan=plan,
        config_root=config_root,
        now=current_time,
    )
    return plan


def persist_write_model_configuration_manual_recovery_approval(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist one immutable short-lived manual recovery approval."""

    validate_write_model_configuration_manual_recovery_approval(payload)
    return _persist_immutable(payload, path)


def format_write_model_configuration_manual_recovery_plan_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact manual recovery plan report."""

    validate_write_model_configuration_manual_recovery_plan(payload)
    lineage = _clearance_revocation_lineage(payload)
    return (
        "",
        "=" * 60,
        "Write model configuration manual recovery plan",
        f"  Status       : {payload['status']}",
        f"  Selected     : {payload['selected_state']}",
        f"  Selected by  : {payload['selected_by']}",
        *(
            (f"  Revocation fp: {lineage['manual_recovery_clearance_revocation_fingerprint']}",)
            if lineage is not None
            else ()
        ),
        f"  Operations   : {len(payload['operations'])}",
        "  Authorized   : no",
        "  Configuration: unchanged",
        "  Model calls  : none",
        "=" * 60,
    )


def format_write_model_configuration_manual_recovery_approval_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact manual recovery approval report."""

    validate_write_model_configuration_manual_recovery_approval(payload)
    lineage = _clearance_revocation_lineage(payload)
    return (
        "",
        "=" * 60,
        "Write model configuration manual recovery approval",
        f"  Status       : {payload['status']}",
        f"  Selected     : {payload['selected_state']}",
        f"  Approved by  : {payload['approved_by']}",
        f"  Reference    : {payload['approval_reference']}",
        f"  Expires at   : {payload['expires_at']}",
        *(
            (f"  Revocation fp: {lineage['manual_recovery_clearance_revocation_fingerprint']}",)
            if lineage is not None
            else ()
        ),
        "  Consumed     : no",
        "  Configuration: unchanged",
        "  Model calls  : none",
        "=" * 60,
    )


__all__ = [
    "assert_write_model_configuration_manual_recovery_approval_current",
    "assert_write_model_configuration_manual_recovery_plan_current",
    "build_write_model_configuration_manual_recovery_approval",
    "build_write_model_configuration_manual_recovery_plan",
    "format_write_model_configuration_manual_recovery_approval_report",
    "format_write_model_configuration_manual_recovery_plan_report",
    "load_write_model_configuration_manual_recovery_approval",
    "load_write_model_configuration_manual_recovery_approval_request",
    "load_write_model_configuration_manual_recovery_plan",
    "load_write_model_configuration_manual_recovery_selection_request",
    "persist_write_model_configuration_manual_recovery_approval",
    "persist_write_model_configuration_manual_recovery_plan",
    "validate_write_model_configuration_manual_recovery_approval",
    "validate_write_model_configuration_manual_recovery_approval_request",
    "validate_write_model_configuration_manual_recovery_plan",
    "validate_write_model_configuration_manual_recovery_selection_request",
]
