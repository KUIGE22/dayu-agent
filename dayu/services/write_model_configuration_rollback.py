"""Plan and approve an operator-initiated write-routing rollback."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import tempfile
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dayu.services.write_model_configuration_application import (
    load_write_model_configuration_application_receipt,
    validate_write_model_configuration_application_receipt,
    verify_write_model_configuration_application_receipt,
)
from dayu.services.write_model_configuration_preapplication import (
    load_write_model_configuration_preapplication_plan,
    validate_write_model_configuration_preapplication_plan,
    validate_write_scene_model_routing_snapshot,
)


_PLAN_SCHEMA_VERSION = (
    "write_model_configuration_operator_rollback_plan_v1"
)
_PLAN_VERIFICATION_SCHEMA_VERSION = (
    "write_model_configuration_operator_rollback_plan_verification_v1"
)
_APPROVAL_REQUEST_SCHEMA_VERSION = (
    "write_model_configuration_operator_rollback_approval_request_v1"
)
_APPROVAL_SCHEMA_VERSION = (
    "write_model_configuration_operator_rollback_approval_v1"
)
_APPROVAL_VERIFICATION_SCHEMA_VERSION = (
    "write_model_configuration_operator_rollback_"
    "approval_verification_v1"
)
_PLAN_TYPE = "write_scene_model_routing_operator_rollback"
_PLAN_SCOPE = (
    "exact_preapplication_restore_plan_no_configuration_change"
)
_PLAN_STATUS = "ready_for_human_rollback_approval"
_APPROVAL_TYPE = "write_scene_model_routing_operator_rollback"
_APPROVAL_SCOPE = (
    "one_future_exact_operator_rollback_subject_to_runtime_match"
)
_APPROVAL_STATUS = "approved_for_one_future_operator_rollback"
_CONFIGURATION_DOMAIN = "write_scene_model_routing"
_MODEL_POINTER = "/model/default_name"
_MAX_APPROVAL_VALIDITY = timedelta(hours=4)
_ROLE_ORDER = {"primary": 0, "audit": 1}
_PLAN_SAFETY_BOUNDARIES = [
    "operator_rollback_plan_only",
    "source_application_receipt_must_be_applied_and_current",
    "complete_runtime_snapshot_must_match_application_receipt",
    "exact_preapplication_manifest_bytes_are_embedded",
    "all_target_manifests_must_match_applied_fingerprints",
    "separate_short_lived_human_approval_required",
    "separate_single_use_rollback_command_required",
    "no_configuration_rollback",
    "no_approval_consumption",
    "no_model_execution",
    "no_model_catalog_or_secret_mutation",
]
_REQUIRED_ACKNOWLEDGEMENTS = [
    "reviewed_exact_restore_operations",
    "current_runtime_matches_applied_receipt",
    "restore_exact_preapplication_bytes",
    "rollback_requires_separate_single_use_command",
    "approval_is_single_use",
    "issuance_and_verification_do_not_modify_configuration",
    "issuance_and_verification_do_not_execute_models",
]
_APPROVAL_SAFETY_BOUNDARIES = [
    "one_future_exact_operator_rollback_only",
    "current_runtime_and_manifest_fingerprints_must_match_plan",
    "source_application_receipt_must_remain_current",
    "restore_exact_preapplication_manifest_bytes_only",
    "single_use_consumption_required_before_rollback",
    "issuance_does_not_modify_configuration",
    "verification_does_not_modify_configuration",
    "no_model_execution",
    "no_model_catalog_or_secret_mutation",
]
_SOURCE_FIELDS = {
    "path",
    "file_fingerprint",
    "content_fingerprint",
}
_PLAN_OPERATION_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "json_pointer",
    "expected_current_model_name",
    "restore_model_name",
    "expected_current_file_fingerprint",
    "restore_file_fingerprint",
    "restore_file_content_base64",
}
_PLAN_FIELDS = {
    "schema_version",
    "plan_type",
    "scope",
    "status",
    "ticker",
    "configuration_domain",
    "source_application_receipt",
    "source_preapplication_plan",
    "expected_current_routing_snapshot_fingerprint",
    "expected_restored_routing_snapshot_fingerprint",
    "rollback_reference",
    "created_at",
    "operations",
    "safety_boundaries",
    "configuration_rollback_authorized",
    "configuration_rollback_performed",
    "approval_consumed",
    "model_execution_performed",
    "plan_fingerprint",
}
_PLAN_IDENTITY_FIELDS = {
    "application_receipt_path",
    "application_receipt_file_fingerprint",
    "application_receipt_content_fingerprint",
    "application_receipt_status",
    "preapplication_plan_file_fingerprint",
    "preapplication_plan_content_fingerprint",
    "receipt_plan_consistency",
    "current_runtime_snapshot_match",
    "current_manifest_files_match",
}
_PLAN_VERIFICATION_FIELDS = {
    "schema_version",
    "status",
    "action",
    "reason_codes",
    "identity",
    "expected_current_routing_snapshot_fingerprint",
    "current_routing_snapshot_fingerprint",
    "expected_restored_routing_snapshot_fingerprint",
    "eligible_for_human_rollback_approval",
    "configuration_verification_performed",
    "configuration_rollback_performed",
    "approval_consumed",
    "model_execution_performed",
}
_PLAN_VERIFICATION_STATUSES = {
    "current",
    "application_receipt_mismatch",
    "source_evidence_changed",
    "routing_changed",
    "manifest_files_changed",
}
_APPROVAL_REQUEST_FIELDS = {
    "schema_version",
    "approval_type",
    "scope",
    "approved_by",
    "approval_reference",
    "rollback_reason",
    "approved_at",
    "expires_at",
    "rollback_plan_fingerprint",
    "application_receipt_fingerprint",
    "acknowledgements",
}
_APPROVAL_FIELDS = {
    "schema_version",
    "approval_type",
    "scope",
    "status",
    "approved_by",
    "approval_reference",
    "rollback_reason",
    "approved_at",
    "expires_at",
    "rollback_plan_source",
    "rollback_plan_fingerprint",
    "application_receipt_fingerprint",
    "approval_request_fingerprint",
    "rollback_plan",
    "maximum_uses",
    "acknowledgements",
    "safety_boundaries",
    "configuration_rollback_authorized",
    "configuration_rollback_performed",
    "approval_consumed",
    "model_execution_performed",
    "approval_fingerprint",
}
_APPROVAL_IDENTITY_FIELDS = {
    "rollback_plan_file_fingerprint",
    "embedded_plan_matches_source",
    "rollback_plan_fingerprint",
    "application_receipt_fingerprint",
    "rollback_plan_current",
}
_APPROVAL_VERIFICATION_FIELDS = {
    "schema_version",
    "status",
    "action",
    "reason_codes",
    "identity",
    "effective_window",
    "eligible_for_future_single_use_operator_rollback",
    "maximum_uses",
    "configuration_rollback_authorized",
    "configuration_rollback_performed",
    "approval_consumed",
    "model_execution_performed",
    "safety_boundaries",
}
_APPROVAL_VERIFICATION_STATUSES = {
    "approved",
    "stale_rollback_plan",
    "rollback_plan_not_current",
    "not_effective",
    "expired",
}
_EFFECTIVE_WINDOW_FIELDS = {
    "approved_at",
    "expires_at",
    "checked_at",
}


class WriteModelConfigurationRollbackBlockedError(ValueError):
    """Raised when rollback evidence cannot enter the next gate."""


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


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


def _exact_fields(
    payload: Mapping[str, Any],
    *,
    expected: set[str],
    name: str,
) -> None:
    actual = set(payload)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    raise ValueError(
        f"{name} fields are invalid: "
        f"missing={missing}, extra={unexpected}"
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fingerprint(value: object) -> str:
    digest = hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _bytes_fingerprint(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _validated_fingerprint(value: object, *, name: str) -> str:
    normalized = str(value or "").strip().lower()
    prefix = "sha256:"
    digest = (
        normalized[len(prefix) :]
        if normalized.startswith(prefix)
        else ""
    )
    if len(digest) != 64 or any(
        character not in "0123456789abcdef"
        for character in digest
    ):
        raise ValueError(f"{name} must be a sha256 fingerprint")
    return normalized


def _absolute_path(value: object, *, name: str) -> Path:
    text = _required_text(
        value,
        name=name,
        maximum_length=32_768,
    )
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return path.resolve()


def _parse_utc_timestamp(value: object, *, name: str) -> datetime:
    text = _required_text(value, name=name, maximum_length=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must include a timezone")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_approval_window(
    *,
    approved_at: datetime,
    expires_at: datetime,
) -> None:
    if expires_at <= approved_at:
        raise ValueError("expires_at must be after approved_at")
    if expires_at - approved_at > _MAX_APPROVAL_VALIDITY:
        raise ValueError("approval validity cannot exceed four hours")


def _decode_base64(value: object, *, name: str) -> bytes:
    text = _required_text(
        value,
        name=name,
        maximum_length=1_000_000,
    )
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, TypeError, ValueError) as exc:
        raise ValueError(f"{name} is invalid") from exc


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _source_reference(
    *,
    path: Path,
    content_fingerprint: str,
) -> dict[str, str]:
    return {
        "path": str(path),
        "file_fingerprint": _file_fingerprint(path),
        "content_fingerprint": _validated_fingerprint(
            content_fingerprint,
            name="source content fingerprint",
        ),
    }


def _validate_source(
    value: object,
    *,
    name: str,
) -> dict[str, str]:
    source = _mapping(value, name=name)
    _exact_fields(source, expected=_SOURCE_FIELDS, name=name)
    return {
        "path": str(
            _absolute_path(source.get("path"), name=f"{name}.path")
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


def _snapshot_fingerprint(
    snapshot: Mapping[str, Any],
    *,
    name: str,
) -> str:
    validate_write_scene_model_routing_snapshot(snapshot)
    return _validated_fingerprint(
        snapshot.get("snapshot_fingerprint"),
        name=f"{name}.snapshot_fingerprint",
    )


def _configuration_root(snapshot: Mapping[str, Any]) -> Path:
    context = _mapping(
        snapshot.get("resolution_context"),
        name="routing snapshot resolution_context",
    )
    return _absolute_path(
        context.get("config_root"),
        name="routing snapshot config_root",
    )


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


def _validate_plan_operation(
    value: object,
    *,
    name: str,
) -> tuple[dict[str, str], bytes]:
    operation = _mapping(value, name=name)
    _exact_fields(
        operation,
        expected=_PLAN_OPERATION_FIELDS,
        name=name,
    )
    normalized = {
        field_name: _required_text(
            operation.get(field_name),
            name=f"{name}.{field_name}",
            maximum_length=(
                1_000_000
                if field_name == "restore_file_content_base64"
                else 32_768
            ),
        )
        for field_name in _PLAN_OPERATION_FIELDS
    }
    if normalized["role"] not in _ROLE_ORDER:
        raise ValueError(f"{name}.role is invalid")
    if normalized["json_pointer"] != _MODEL_POINTER:
        raise ValueError(f"{name}.json_pointer is invalid")
    normalized["target_manifest_path"] = str(
        _absolute_path(
            normalized["target_manifest_path"],
            name=f"{name}.target_manifest_path",
        )
    )
    for field_name in (
        "expected_current_file_fingerprint",
        "restore_file_fingerprint",
    ):
        normalized[field_name] = _validated_fingerprint(
            normalized[field_name],
            name=f"{name}.{field_name}",
        )
    restore_bytes = _decode_base64(
        normalized["restore_file_content_base64"],
        name=f"{name}.restore_file_content_base64",
    )
    if not hmac.compare_digest(
        _bytes_fingerprint(restore_bytes),
        normalized["restore_file_fingerprint"],
    ):
        raise ValueError(f"{name} restore bytes fingerprint mismatch")
    try:
        manifest = json.loads(restore_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"{name} restore bytes are not a UTF-8 JSON manifest"
        ) from exc
    manifest_view = _mapping(manifest, name=f"{name} restore manifest")
    model = _mapping(
        manifest_view.get("model"),
        name=f"{name} restore manifest model",
    )
    if model.get("default_name") != normalized["restore_model_name"]:
        raise ValueError(
            f"{name} restore bytes do not contain the restore model"
        )
    allowed_names = model.get("allowed_names")
    if (
        not isinstance(allowed_names, list)
        or normalized["expected_current_model_name"]
        not in allowed_names
    ):
        raise ValueError(
            f"{name} restore manifest does not allow the applied model"
        )
    if (
        normalized["restore_model_name"]
        == normalized["expected_current_model_name"]
    ):
        raise ValueError(f"{name} does not describe a model transition")
    return normalized, restore_bytes


def _preapplication_operation_maps(
    plan: Mapping[str, Any],
) -> tuple[
    dict[tuple[str, str], Mapping[str, Any]],
    dict[tuple[str, str], Mapping[str, Any]],
]:
    raw_transitions = plan.get("transitions")
    rollback = _mapping(
        plan.get("rollback"),
        name="preapplication rollback",
    )
    raw_entries = rollback.get("entries")
    if not isinstance(raw_transitions, list):
        raise ValueError("preapplication transitions must be a list")
    if not isinstance(raw_entries, list):
        raise ValueError("preapplication rollback entries must be a list")
    transitions = {
        _operation_key(
            _mapping(value, name=f"transitions[{index}]")
        ): _mapping(value, name=f"transitions[{index}]")
        for index, value in enumerate(raw_transitions)
    }
    entries = {
        _operation_key(
            _mapping(value, name=f"rollback.entries[{index}]")
        ): _mapping(value, name=f"rollback.entries[{index}]")
        for index, value in enumerate(raw_entries)
    }
    return transitions, entries


def _build_restore_operations(
    *,
    receipt: Mapping[str, Any],
    preapplication_plan: Mapping[str, Any],
    current_routing_snapshot: Mapping[str, Any],
) -> list[dict[str, str]]:
    validate_write_model_configuration_application_receipt(receipt)
    validate_write_model_configuration_preapplication_plan(
        preapplication_plan
    )
    transitions, rollback_entries = _preapplication_operation_maps(
        preapplication_plan
    )
    raw_receipt_operations = receipt.get("operations")
    assert isinstance(raw_receipt_operations, list)
    if not (
        len(raw_receipt_operations)
        == len(transitions)
        == len(rollback_entries)
    ):
        raise ValueError(
            "application receipt and preapplication operations differ"
        )
    manifest_root = (
        _configuration_root(current_routing_snapshot)
        / "prompts"
        / "manifests"
    ).resolve()
    operations: list[dict[str, str]] = []
    seen_paths: set[Path] = set()
    for index, raw_receipt_operation in enumerate(
        raw_receipt_operations
    ):
        receipt_operation = _mapping(
            raw_receipt_operation,
            name=f"application receipt operations[{index}]",
        )
        key = _operation_key(receipt_operation)
        transition = transitions.get(key)
        rollback = rollback_entries.get(key)
        if transition is None or rollback is None:
            raise ValueError(
                "application receipt operation is absent from source plan"
            )
        scene_name = str(receipt_operation["scene_name"])
        target = _absolute_path(
            receipt_operation.get("target_manifest_path"),
            name=f"receipt operation {scene_name}.target_manifest_path",
        )
        if (
            not _is_relative_to(target, manifest_root)
            or target.parent != manifest_root
            or target.name != f"{scene_name}.json"
            or target in seen_paths
            or target.is_symlink()
        ):
            raise WriteModelConfigurationRollbackBlockedError(
                f"rollback target for scene {scene_name!r} is unsafe"
            )
        seen_paths.add(target)
        expected = {
            "target_manifest_path": str(target),
            "expected_current_model_name": str(
                receipt_operation["applied_model_name"]
            ),
            "restore_model_name": str(
                receipt_operation["expected_current_model_name"]
            ),
            "expected_current_file_fingerprint": str(
                receipt_operation["applied_file_fingerprint"]
            ),
            "restore_file_fingerprint": str(
                receipt_operation["original_file_fingerprint"]
            ),
        }
        actual = {
            "target_manifest_path": str(
                _absolute_path(
                    transition.get("target_manifest_path"),
                    name=f"transition {scene_name}.target path",
                )
            ),
            "expected_current_model_name": str(
                transition.get("proposed_model_name")
            ),
            "restore_model_name": str(
                transition.get("expected_current_model_name")
            ),
            "expected_current_file_fingerprint": str(
                receipt_operation["applied_file_fingerprint"]
            ),
            "restore_file_fingerprint": str(
                transition.get("target_manifest_fingerprint")
            ),
        }
        if expected != actual:
            raise ValueError(
                f"receipt transition mismatch for scene {scene_name!r}"
            )
        if (
            str(rollback.get("target_manifest_path")) != str(target)
            or rollback.get("restore_model_name")
            != expected["restore_model_name"]
            or rollback.get("expected_applied_model_name")
            != expected["expected_current_model_name"]
            or rollback.get("original_file_fingerprint")
            != expected["restore_file_fingerprint"]
        ):
            raise ValueError(
                f"receipt rollback mismatch for scene {scene_name!r}"
            )
        restore_bytes = _decode_base64(
            rollback.get("original_file_content_base64"),
            name=f"rollback {scene_name}.original_file_content_base64",
        )
        if not hmac.compare_digest(
            _bytes_fingerprint(restore_bytes),
            expected["restore_file_fingerprint"],
        ):
            raise ValueError(
                f"rollback bytes mismatch for scene {scene_name!r}"
            )
        if not target.is_file() or not hmac.compare_digest(
            _file_fingerprint(target),
            expected["expected_current_file_fingerprint"],
        ):
            raise WriteModelConfigurationRollbackBlockedError(
                f"current manifest for scene {scene_name!r} changed"
            )
        operations.append(
            {
                "role": str(receipt_operation["role"]),
                "scene_name": scene_name,
                "target_manifest_path": str(target),
                "json_pointer": _MODEL_POINTER,
                **expected,
                "restore_file_content_base64": base64.b64encode(
                    restore_bytes
                ).decode("ascii"),
            }
        )
    if set(transitions) != {
        _operation_key(operation) for operation in operations
    }:
        raise ValueError(
            "source preapplication plan contains unmatched operations"
        )
    operations.sort(key=_operation_sort_key)
    return operations


def _receipt_source_plan(
    receipt: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    source = _mapping(
        receipt.get("source_plan"),
        name="application receipt source_plan",
    )
    plan_path = _absolute_path(
        source.get("path"),
        name="application receipt source_plan.path",
    )
    if not plan_path.is_file() or not hmac.compare_digest(
        _validated_fingerprint(
            source.get("file_fingerprint"),
            name="application receipt source_plan.file_fingerprint",
        ),
        _file_fingerprint(plan_path),
    ):
        raise WriteModelConfigurationRollbackBlockedError(
            "source preapplication plan file changed"
        )
    _resolved, plan = (
        load_write_model_configuration_preapplication_plan(plan_path)
    )
    if not hmac.compare_digest(
        _validated_fingerprint(
            source.get("content_fingerprint"),
            name="application receipt source_plan.content_fingerprint",
        ),
        _validated_fingerprint(
            plan.get("plan_fingerprint"),
            name="source preapplication plan fingerprint",
        ),
    ):
        raise WriteModelConfigurationRollbackBlockedError(
            "source preapplication plan content changed"
        )
    return plan_path, plan


def build_write_model_configuration_operator_rollback_plan(
    *,
    application_receipt_path: str | Path,
    current_routing_snapshot: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Build an exact read-only rollback plan from current evidence."""

    validate_write_scene_model_routing_snapshot(
        current_routing_snapshot
    )
    resolved_receipt_path, receipt = (
        load_write_model_configuration_application_receipt(
            application_receipt_path
        )
    )
    verification = (
        verify_write_model_configuration_application_receipt(
            receipt,
            current_routing_snapshot=current_routing_snapshot,
        )
    )
    if (
        verification.get("status") != "current"
        or verification.get("eligible_for_operator_rollback_plan")
        is not True
    ):
        raise WriteModelConfigurationRollbackBlockedError(
            "application receipt is not eligible for operator rollback"
        )
    plan_path, preapplication_plan = _receipt_source_plan(receipt)
    operations = _build_restore_operations(
        receipt=receipt,
        preapplication_plan=preapplication_plan,
        current_routing_snapshot=current_routing_snapshot,
    )
    rollback = _mapping(
        preapplication_plan.get("rollback"),
        name="preapplication rollback",
    )
    payload: dict[str, Any] = {
        "schema_version": _PLAN_SCHEMA_VERSION,
        "plan_type": _PLAN_TYPE,
        "scope": _PLAN_SCOPE,
        "status": _PLAN_STATUS,
        "ticker": receipt["ticker"],
        "configuration_domain": _CONFIGURATION_DOMAIN,
        "source_application_receipt": _source_reference(
            path=resolved_receipt_path,
            content_fingerprint=str(receipt["receipt_fingerprint"]),
        ),
        "source_preapplication_plan": _source_reference(
            path=plan_path,
            content_fingerprint=str(
                preapplication_plan["plan_fingerprint"]
            ),
        ),
        "expected_current_routing_snapshot_fingerprint": (
            receipt["post_operation_routing_snapshot_fingerprint"]
        ),
        "expected_restored_routing_snapshot_fingerprint": (
            receipt["source_routing_snapshot_fingerprint"]
        ),
        "rollback_reference": rollback["rollback_reference"],
        "created_at": _format_utc(_normalize_now(now)),
        "operations": operations,
        "safety_boundaries": list(_PLAN_SAFETY_BOUNDARIES),
        "configuration_rollback_authorized": False,
        "configuration_rollback_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    payload["plan_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_operator_rollback_plan(payload)
    return payload


def validate_write_model_configuration_operator_rollback_plan(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict exact-byte operator rollback plan."""

    plan = _mapping(payload, name="operator rollback plan")
    _exact_fields(
        plan,
        expected=_PLAN_FIELDS,
        name="operator rollback plan",
    )
    constants = {
        "schema_version": _PLAN_SCHEMA_VERSION,
        "plan_type": _PLAN_TYPE,
        "scope": _PLAN_SCOPE,
        "status": _PLAN_STATUS,
        "configuration_domain": _CONFIGURATION_DOMAIN,
    }
    for field_name, expected in constants.items():
        if plan.get(field_name) != expected:
            raise ValueError(
                f"operator rollback plan {field_name} "
                f"must be {expected!r}"
            )
    _required_text(plan.get("ticker"), name="ticker", maximum_length=64)
    _validate_source(
        plan.get("source_application_receipt"),
        name="source_application_receipt",
    )
    _validate_source(
        plan.get("source_preapplication_plan"),
        name="source_preapplication_plan",
    )
    current_fingerprint = _validated_fingerprint(
        plan.get("expected_current_routing_snapshot_fingerprint"),
        name="expected_current_routing_snapshot_fingerprint",
    )
    restored_fingerprint = _validated_fingerprint(
        plan.get("expected_restored_routing_snapshot_fingerprint"),
        name="expected_restored_routing_snapshot_fingerprint",
    )
    if hmac.compare_digest(current_fingerprint, restored_fingerprint):
        raise ValueError(
            "operator rollback plan snapshots must describe a change"
        )
    _required_text(
        plan.get("rollback_reference"),
        name="rollback_reference",
        maximum_length=500,
    )
    _parse_utc_timestamp(plan.get("created_at"), name="created_at")
    raw_operations = plan.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("operator rollback operations must be non-empty")
    validated = [
        _validate_plan_operation(
            operation,
            name=f"operations[{index}]",
        )[0]
        for index, operation in enumerate(raw_operations)
    ]
    if validated != sorted(validated, key=_operation_sort_key):
        raise ValueError("operator rollback operations are not ordered")
    identities = [_operation_key(operation) for operation in validated]
    paths = [
        operation["target_manifest_path"] for operation in validated
    ]
    if (
        len(identities) != len(set(identities))
        or len(paths) != len(set(paths))
    ):
        raise ValueError(
            "operator rollback operations contain duplicates"
        )
    if plan.get("safety_boundaries") != _PLAN_SAFETY_BOUNDARIES:
        raise ValueError("operator rollback plan boundaries are invalid")
    expected_flags = {
        "configuration_rollback_authorized": False,
        "configuration_rollback_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    for field_name, expected in expected_flags.items():
        if plan.get(field_name) is not expected:
            raise ValueError(
                f"operator rollback plan {field_name} is invalid"
            )
    fingerprint = _validated_fingerprint(
        plan.get("plan_fingerprint"),
        name="operator rollback plan fingerprint",
    )
    unsigned = dict(plan)
    unsigned.pop("plan_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("operator rollback plan fingerprint mismatch")


def _empty_plan_identity() -> dict[str, bool]:
    return {
        field_name: False for field_name in _PLAN_IDENTITY_FIELDS
    }


def _plan_verification_payload(
    *,
    plan: Mapping[str, Any],
    current_routing_snapshot: Mapping[str, Any],
    status: str,
    reason_codes: list[str],
    identity: Mapping[str, bool],
) -> dict[str, Any]:
    payload = {
        "schema_version": _PLAN_VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "action": (
            "human_rollback_approval_required"
            if status == "current"
            else "stop"
        ),
        "reason_codes": reason_codes,
        "identity": dict(identity),
        "expected_current_routing_snapshot_fingerprint": (
            plan["expected_current_routing_snapshot_fingerprint"]
        ),
        "current_routing_snapshot_fingerprint": _snapshot_fingerprint(
            current_routing_snapshot,
            name="current routing snapshot",
        ),
        "expected_restored_routing_snapshot_fingerprint": (
            plan["expected_restored_routing_snapshot_fingerprint"]
        ),
        "eligible_for_human_rollback_approval": status == "current",
        "configuration_verification_performed": True,
        "configuration_rollback_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    validate_write_model_configuration_operator_rollback_plan_verification(
        payload
    )
    return payload


def verify_write_model_configuration_operator_rollback_plan(
    plan: Mapping[str, Any],
    *,
    expected_application_receipt_path: str | Path,
    current_routing_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a rollback plan against fresh routing and source evidence."""

    validate_write_model_configuration_operator_rollback_plan(plan)
    validate_write_scene_model_routing_snapshot(
        current_routing_snapshot
    )
    identity = _empty_plan_identity()
    receipt_source = _mapping(
        plan.get("source_application_receipt"),
        name="source_application_receipt",
    )
    receipt_path = _absolute_path(
        receipt_source.get("path"),
        name="source_application_receipt.path",
    )
    expected_receipt_path = Path(
        expected_application_receipt_path
    ).expanduser().resolve()
    identity["application_receipt_path"] = (
        receipt_path == expected_receipt_path
    )
    if not identity["application_receipt_path"]:
        return _plan_verification_payload(
            plan=plan,
            current_routing_snapshot=current_routing_snapshot,
            status="application_receipt_mismatch",
            reason_codes=[
                "explicit_application_receipt_path_does_not_match_plan"
            ],
            identity=identity,
        )
    if not receipt_path.is_file() or not hmac.compare_digest(
        _validated_fingerprint(
            receipt_source.get("file_fingerprint"),
            name="source_application_receipt.file_fingerprint",
        ),
        _file_fingerprint(receipt_path),
    ):
        return _plan_verification_payload(
            plan=plan,
            current_routing_snapshot=current_routing_snapshot,
            status="source_evidence_changed",
            reason_codes=["application_receipt_file_fingerprint_changed"],
            identity=identity,
        )
    identity["application_receipt_file_fingerprint"] = True
    _resolved_receipt, receipt = (
        load_write_model_configuration_application_receipt(receipt_path)
    )
    identity["application_receipt_content_fingerprint"] = (
        hmac.compare_digest(
            _validated_fingerprint(
                receipt_source.get("content_fingerprint"),
                name=(
                    "source_application_receipt.content_fingerprint"
                ),
            ),
            _validated_fingerprint(
                receipt.get("receipt_fingerprint"),
                name="application receipt fingerprint",
            ),
        )
    )
    identity["application_receipt_status"] = (
        receipt.get("status") == "applied"
    )
    if not (
        identity["application_receipt_content_fingerprint"]
        and identity["application_receipt_status"]
    ):
        return _plan_verification_payload(
            plan=plan,
            current_routing_snapshot=current_routing_snapshot,
            status="source_evidence_changed",
            reason_codes=["application_receipt_content_or_status_changed"],
            identity=identity,
        )
    preapplication_source = _mapping(
        plan.get("source_preapplication_plan"),
        name="source_preapplication_plan",
    )
    preapplication_path = _absolute_path(
        preapplication_source.get("path"),
        name="source_preapplication_plan.path",
    )
    if not preapplication_path.is_file() or not hmac.compare_digest(
        _validated_fingerprint(
            preapplication_source.get("file_fingerprint"),
            name="source_preapplication_plan.file_fingerprint",
        ),
        _file_fingerprint(preapplication_path),
    ):
        return _plan_verification_payload(
            plan=plan,
            current_routing_snapshot=current_routing_snapshot,
            status="source_evidence_changed",
            reason_codes=["preapplication_plan_file_fingerprint_changed"],
            identity=identity,
        )
    identity["preapplication_plan_file_fingerprint"] = True
    _resolved_plan, preapplication_plan = (
        load_write_model_configuration_preapplication_plan(
            preapplication_path
        )
    )
    identity["preapplication_plan_content_fingerprint"] = (
        hmac.compare_digest(
            _validated_fingerprint(
                preapplication_source.get("content_fingerprint"),
                name="source_preapplication_plan.content_fingerprint",
            ),
            _validated_fingerprint(
                preapplication_plan.get("plan_fingerprint"),
                name="preapplication plan fingerprint",
            ),
        )
    )
    if not identity["preapplication_plan_content_fingerprint"]:
        return _plan_verification_payload(
            plan=plan,
            current_routing_snapshot=current_routing_snapshot,
            status="source_evidence_changed",
            reason_codes=[
                "preapplication_plan_content_fingerprint_changed"
            ],
            identity=identity,
        )
    receipt_plan_source = _mapping(
        receipt.get("source_plan"),
        name="application receipt source_plan",
    )
    identity["receipt_plan_consistency"] = (
        Path(str(receipt_plan_source.get("path"))).resolve()
        == preapplication_path
        and hmac.compare_digest(
            str(receipt_plan_source.get("file_fingerprint")),
            str(preapplication_source.get("file_fingerprint")),
        )
        and hmac.compare_digest(
            str(receipt_plan_source.get("content_fingerprint")),
            str(preapplication_source.get("content_fingerprint")),
        )
        and hmac.compare_digest(
            str(
                plan.get(
                    "expected_current_routing_snapshot_fingerprint"
                )
            ),
            str(
                receipt.get(
                    "post_operation_routing_snapshot_fingerprint"
                )
            ),
        )
        and hmac.compare_digest(
            str(
                plan.get(
                    "expected_restored_routing_snapshot_fingerprint"
                )
            ),
            str(receipt.get("source_routing_snapshot_fingerprint")),
        )
    )
    if not identity["receipt_plan_consistency"]:
        return _plan_verification_payload(
            plan=plan,
            current_routing_snapshot=current_routing_snapshot,
            status="source_evidence_changed",
            reason_codes=["application_receipt_plan_evidence_mismatch"],
            identity=identity,
        )
    receipt_verification = (
        verify_write_model_configuration_application_receipt(
            receipt,
            current_routing_snapshot=current_routing_snapshot,
        )
    )
    identity["current_runtime_snapshot_match"] = (
        receipt_verification.get("status") == "current"
        and receipt_verification.get(
            "eligible_for_operator_rollback_plan"
        )
        is True
    )
    if not identity["current_runtime_snapshot_match"]:
        return _plan_verification_payload(
            plan=plan,
            current_routing_snapshot=current_routing_snapshot,
            status="routing_changed",
            reason_codes=[
                "current_runtime_does_not_match_application_receipt"
            ],
            identity=identity,
        )
    try:
        rebuilt_operations = _build_restore_operations(
            receipt=receipt,
            preapplication_plan=preapplication_plan,
            current_routing_snapshot=current_routing_snapshot,
        )
    except WriteModelConfigurationRollbackBlockedError:
        return _plan_verification_payload(
            plan=plan,
            current_routing_snapshot=current_routing_snapshot,
            status="manifest_files_changed",
            reason_codes=["applied_manifest_file_fingerprint_changed"],
            identity=identity,
        )
    identity["current_manifest_files_match"] = True
    if rebuilt_operations != plan.get("operations"):
        identity["receipt_plan_consistency"] = False
        return _plan_verification_payload(
            plan=plan,
            current_routing_snapshot=current_routing_snapshot,
            status="source_evidence_changed",
            reason_codes=["rollback_operations_no_longer_match_evidence"],
            identity=identity,
        )
    return _plan_verification_payload(
        plan=plan,
        current_routing_snapshot=current_routing_snapshot,
        status="current",
        reason_codes=["eligible_for_human_rollback_approval"],
        identity=identity,
    )


def validate_write_model_configuration_operator_rollback_plan_verification(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict read-only rollback-plan verification."""

    verification = _mapping(
        payload,
        name="operator rollback plan verification",
    )
    _exact_fields(
        verification,
        expected=_PLAN_VERIFICATION_FIELDS,
        name="operator rollback plan verification",
    )
    if (
        verification.get("schema_version")
        != _PLAN_VERIFICATION_SCHEMA_VERSION
    ):
        raise ValueError("unsupported rollback plan verification schema")
    status = verification.get("status")
    if status not in _PLAN_VERIFICATION_STATUSES:
        raise ValueError("rollback plan verification status is invalid")
    expected_action = (
        "human_rollback_approval_required"
        if status == "current"
        else "stop"
    )
    if verification.get("action") != expected_action:
        raise ValueError("rollback plan verification action is invalid")
    reasons = verification.get("reason_codes")
    if not isinstance(reasons, list) or not reasons:
        raise ValueError(
            "rollback plan verification reasons must be non-empty"
        )
    normalized_reasons = [
        _required_text(
            reason,
            name=f"reason_codes[{index}]",
            maximum_length=128,
        )
        for index, reason in enumerate(reasons)
    ]
    if len(normalized_reasons) != len(set(normalized_reasons)):
        raise ValueError(
            "rollback plan verification reasons contain duplicates"
        )
    identity = _mapping(
        verification.get("identity"),
        name="rollback plan verification identity",
    )
    _exact_fields(
        identity,
        expected=_PLAN_IDENTITY_FIELDS,
        name="rollback plan verification identity",
    )
    if any(not isinstance(value, bool) for value in identity.values()):
        raise ValueError(
            "rollback plan verification identity must be boolean"
        )
    for field_name in (
        "expected_current_routing_snapshot_fingerprint",
        "current_routing_snapshot_fingerprint",
        "expected_restored_routing_snapshot_fingerprint",
    ):
        _validated_fingerprint(
            verification.get(field_name),
            name=field_name,
        )
    eligible = verification.get(
        "eligible_for_human_rollback_approval"
    )
    if eligible is not (status == "current"):
        raise ValueError(
            "rollback plan verification eligibility is invalid"
        )
    if status == "current" and not all(identity.values()):
        raise ValueError(
            "current rollback plan verification is inconsistent"
        )
    expected_flags = {
        "configuration_verification_performed": True,
        "configuration_rollback_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    for field_name, expected in expected_flags.items():
        if verification.get(field_name) is not expected:
            raise ValueError(
                f"rollback plan verification {field_name} is invalid"
            )


def validate_write_model_configuration_operator_rollback_approval_request(
    payload: Mapping[str, Any],
) -> None:
    """Validate one explicit human operator rollback confirmation."""

    request = _mapping(payload, name="operator rollback approval request")
    _exact_fields(
        request,
        expected=_APPROVAL_REQUEST_FIELDS,
        name="operator rollback approval request",
    )
    constants = {
        "schema_version": _APPROVAL_REQUEST_SCHEMA_VERSION,
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
    }
    for field_name, expected in constants.items():
        if request.get(field_name) != expected:
            raise ValueError(
                f"operator rollback approval request {field_name} "
                f"must be {expected!r}"
            )
    _required_text(
        request.get("approved_by"),
        name="approved_by",
        maximum_length=200,
    )
    _required_text(
        request.get("approval_reference"),
        name="approval_reference",
        maximum_length=500,
    )
    _required_text(
        request.get("rollback_reason"),
        name="rollback_reason",
        maximum_length=2_000,
    )
    approved_at = _parse_utc_timestamp(
        request.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc_timestamp(
        request.get("expires_at"),
        name="expires_at",
    )
    _validate_approval_window(
        approved_at=approved_at,
        expires_at=expires_at,
    )
    _validated_fingerprint(
        request.get("rollback_plan_fingerprint"),
        name="rollback_plan_fingerprint",
    )
    _validated_fingerprint(
        request.get("application_receipt_fingerprint"),
        name="application_receipt_fingerprint",
    )
    if request.get("acknowledgements") != _REQUIRED_ACKNOWLEDGEMENTS:
        raise ValueError(
            "acknowledgements must exactly match the operator "
            "rollback safety list"
        )


def build_write_model_configuration_operator_rollback_approval(
    *,
    approval_request: Mapping[str, Any],
    rollback_plan_path: str | Path,
    rollback_plan: Mapping[str, Any],
    current_routing_snapshot: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Issue a short-lived rollback credential without changing config."""

    validate_write_model_configuration_operator_rollback_approval_request(
        approval_request
    )
    validate_write_model_configuration_operator_rollback_plan(
        rollback_plan
    )
    resolved_plan_path, persisted_plan = (
        load_write_model_configuration_operator_rollback_plan(
            rollback_plan_path
        )
    )
    if not hmac.compare_digest(
        _canonical_json(persisted_plan),
        _canonical_json(rollback_plan),
    ):
        raise WriteModelConfigurationRollbackBlockedError(
            "operator rollback plan does not match its source file"
        )
    receipt_source = _mapping(
        rollback_plan.get("source_application_receipt"),
        name="source_application_receipt",
    )
    verification = (
        verify_write_model_configuration_operator_rollback_plan(
            rollback_plan,
            expected_application_receipt_path=receipt_source["path"],
            current_routing_snapshot=current_routing_snapshot,
        )
    )
    if verification.get("status") != "current":
        raise WriteModelConfigurationRollbackBlockedError(
            "operator rollback plan is not current"
        )
    current_time = _normalize_now(now)
    approved_at = _parse_utc_timestamp(
        approval_request.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc_timestamp(
        approval_request.get("expires_at"),
        name="expires_at",
    )
    if current_time < approved_at:
        raise WriteModelConfigurationRollbackBlockedError(
            "operator rollback approval is not effective yet"
        )
    if current_time >= expires_at:
        raise WriteModelConfigurationRollbackBlockedError(
            "operator rollback approval has expired"
        )
    plan_fingerprint = _validated_fingerprint(
        rollback_plan.get("plan_fingerprint"),
        name="rollback_plan_fingerprint",
    )
    receipt_fingerprint = _validated_fingerprint(
        receipt_source.get("content_fingerprint"),
        name="application_receipt_fingerprint",
    )
    requested = {
        "rollback_plan_fingerprint": plan_fingerprint,
        "application_receipt_fingerprint": receipt_fingerprint,
    }
    for field_name, expected in requested.items():
        actual = _validated_fingerprint(
            approval_request.get(field_name),
            name=field_name,
        )
        if not hmac.compare_digest(actual, expected):
            raise WriteModelConfigurationRollbackBlockedError(
                f"approval request {field_name} does not match"
            )
    payload: dict[str, Any] = {
        "schema_version": _APPROVAL_SCHEMA_VERSION,
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
        "status": _APPROVAL_STATUS,
        "approved_by": approval_request["approved_by"],
        "approval_reference": approval_request["approval_reference"],
        "rollback_reason": approval_request["rollback_reason"],
        "approved_at": _format_utc(approved_at),
        "expires_at": _format_utc(expires_at),
        "rollback_plan_source": _source_reference(
            path=resolved_plan_path,
            content_fingerprint=plan_fingerprint,
        ),
        **requested,
        "approval_request_fingerprint": _fingerprint(
            dict(approval_request)
        ),
        "rollback_plan": dict(rollback_plan),
        "maximum_uses": 1,
        "acknowledgements": list(_REQUIRED_ACKNOWLEDGEMENTS),
        "safety_boundaries": list(_APPROVAL_SAFETY_BOUNDARIES),
        "configuration_rollback_authorized": True,
        "configuration_rollback_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    payload["approval_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_operator_rollback_approval(
        payload
    )
    return payload


def validate_write_model_configuration_operator_rollback_approval(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict short-lived operator rollback approval."""

    approval = _mapping(payload, name="operator rollback approval")
    _exact_fields(
        approval,
        expected=_APPROVAL_FIELDS,
        name="operator rollback approval",
    )
    constants = {
        "schema_version": _APPROVAL_SCHEMA_VERSION,
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
        "status": _APPROVAL_STATUS,
    }
    for field_name, expected in constants.items():
        if approval.get(field_name) != expected:
            raise ValueError(
                f"operator rollback approval {field_name} "
                f"must be {expected!r}"
            )
    _required_text(
        approval.get("approved_by"),
        name="approved_by",
        maximum_length=200,
    )
    _required_text(
        approval.get("approval_reference"),
        name="approval_reference",
        maximum_length=500,
    )
    _required_text(
        approval.get("rollback_reason"),
        name="rollback_reason",
        maximum_length=2_000,
    )
    approved_at = _parse_utc_timestamp(
        approval.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc_timestamp(
        approval.get("expires_at"),
        name="expires_at",
    )
    _validate_approval_window(
        approved_at=approved_at,
        expires_at=expires_at,
    )
    source = _validate_source(
        approval.get("rollback_plan_source"),
        name="rollback_plan_source",
    )
    plan_fingerprint = _validated_fingerprint(
        approval.get("rollback_plan_fingerprint"),
        name="rollback_plan_fingerprint",
    )
    receipt_fingerprint = _validated_fingerprint(
        approval.get("application_receipt_fingerprint"),
        name="application_receipt_fingerprint",
    )
    _validated_fingerprint(
        approval.get("approval_request_fingerprint"),
        name="approval_request_fingerprint",
    )
    embedded_plan = _mapping(
        approval.get("rollback_plan"),
        name="rollback_plan",
    )
    validate_write_model_configuration_operator_rollback_plan(
        embedded_plan
    )
    embedded_fingerprint = _validated_fingerprint(
        embedded_plan.get("plan_fingerprint"),
        name="embedded rollback plan fingerprint",
    )
    embedded_receipt_source = _mapping(
        embedded_plan.get("source_application_receipt"),
        name="embedded source_application_receipt",
    )
    embedded_receipt_fingerprint = _validated_fingerprint(
        embedded_receipt_source.get("content_fingerprint"),
        name="embedded application receipt fingerprint",
    )
    if not (
        hmac.compare_digest(
            source["content_fingerprint"],
            plan_fingerprint,
        )
        and hmac.compare_digest(
            plan_fingerprint,
            embedded_fingerprint,
        )
        and hmac.compare_digest(
            receipt_fingerprint,
            embedded_receipt_fingerprint,
        )
    ):
        raise ValueError(
            "operator rollback approval fingerprints are inconsistent"
        )
    if approval.get("maximum_uses") != 1:
        raise ValueError("maximum_uses must be 1")
    if approval.get("acknowledgements") != _REQUIRED_ACKNOWLEDGEMENTS:
        raise ValueError(
            "operator rollback approval acknowledgements are invalid"
        )
    if approval.get("safety_boundaries") != (
        _APPROVAL_SAFETY_BOUNDARIES
    ):
        raise ValueError(
            "operator rollback approval safety boundaries are invalid"
        )
    expected_flags = {
        "configuration_rollback_authorized": True,
        "configuration_rollback_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    for field_name, expected in expected_flags.items():
        if approval.get(field_name) is not expected:
            raise ValueError(
                f"operator rollback approval {field_name} is invalid"
            )
    fingerprint = _validated_fingerprint(
        approval.get("approval_fingerprint"),
        name="approval_fingerprint",
    )
    unsigned = dict(approval)
    unsigned.pop("approval_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError(
            "operator rollback approval fingerprint mismatch"
        )


def _empty_approval_identity() -> dict[str, bool]:
    return {
        field_name: False for field_name in _APPROVAL_IDENTITY_FIELDS
    }


def _approval_verification_payload(
    *,
    approval: Mapping[str, Any],
    checked_at: datetime,
    status: str,
    reason_codes: list[str],
    identity: Mapping[str, bool],
) -> dict[str, Any]:
    payload = {
        "schema_version": _APPROVAL_VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "action": (
            "separate_single_use_rollback_command_required"
            if status == "approved"
            else "stop"
        ),
        "reason_codes": reason_codes,
        "identity": dict(identity),
        "effective_window": {
            "approved_at": approval["approved_at"],
            "expires_at": approval["expires_at"],
            "checked_at": _format_utc(checked_at),
        },
        "eligible_for_future_single_use_operator_rollback": (
            status == "approved"
        ),
        "maximum_uses": 1,
        "configuration_rollback_authorized": status == "approved",
        "configuration_rollback_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
        "safety_boundaries": list(_APPROVAL_SAFETY_BOUNDARIES),
    }
    validate_write_model_configuration_operator_rollback_approval_verification(
        payload
    )
    return payload


def verify_write_model_configuration_operator_rollback_approval(
    approval: Mapping[str, Any],
    *,
    current_routing_snapshot: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Verify rollback approval currentness without consuming it."""

    validate_write_model_configuration_operator_rollback_approval(
        approval
    )
    validate_write_scene_model_routing_snapshot(
        current_routing_snapshot
    )
    checked_at = _normalize_now(now)
    identity = _empty_approval_identity()
    source = _mapping(
        approval.get("rollback_plan_source"),
        name="rollback_plan_source",
    )
    plan_path = _absolute_path(
        source.get("path"),
        name="rollback_plan_source.path",
    )
    if not plan_path.is_file() or not hmac.compare_digest(
        _validated_fingerprint(
            source.get("file_fingerprint"),
            name="rollback_plan_source.file_fingerprint",
        ),
        _file_fingerprint(plan_path),
    ):
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="stale_rollback_plan",
            reason_codes=["rollback_plan_file_fingerprint_changed"],
            identity=identity,
        )
    identity["rollback_plan_file_fingerprint"] = True
    _resolved, current_plan = (
        load_write_model_configuration_operator_rollback_plan(plan_path)
    )
    embedded_plan = _mapping(
        approval.get("rollback_plan"),
        name="embedded rollback_plan",
    )
    identity["embedded_plan_matches_source"] = hmac.compare_digest(
        _canonical_json(embedded_plan),
        _canonical_json(current_plan),
    )
    identity["rollback_plan_fingerprint"] = hmac.compare_digest(
        _validated_fingerprint(
            approval.get("rollback_plan_fingerprint"),
            name="rollback_plan_fingerprint",
        ),
        _validated_fingerprint(
            current_plan.get("plan_fingerprint"),
            name="current rollback plan fingerprint",
        ),
    )
    receipt_source = _mapping(
        current_plan.get("source_application_receipt"),
        name="source_application_receipt",
    )
    identity["application_receipt_fingerprint"] = hmac.compare_digest(
        _validated_fingerprint(
            approval.get("application_receipt_fingerprint"),
            name="application_receipt_fingerprint",
        ),
        _validated_fingerprint(
            receipt_source.get("content_fingerprint"),
            name="current application receipt fingerprint",
        ),
    )
    if not all(
        (
            identity["embedded_plan_matches_source"],
            identity["rollback_plan_fingerprint"],
            identity["application_receipt_fingerprint"],
        )
    ):
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="stale_rollback_plan",
            reason_codes=["rollback_plan_or_receipt_fingerprint_changed"],
            identity=identity,
        )
    plan_verification = (
        verify_write_model_configuration_operator_rollback_plan(
            current_plan,
            expected_application_receipt_path=receipt_source["path"],
            current_routing_snapshot=current_routing_snapshot,
        )
    )
    identity["rollback_plan_current"] = (
        plan_verification.get("status") == "current"
    )
    if not identity["rollback_plan_current"]:
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="rollback_plan_not_current",
            reason_codes=[
                f"rollback_plan_{plan_verification.get('status', 'invalid')}"
            ],
            identity=identity,
        )
    approved_at = _parse_utc_timestamp(
        approval.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc_timestamp(
        approval.get("expires_at"),
        name="expires_at",
    )
    if checked_at < approved_at:
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="not_effective",
            reason_codes=["operator_rollback_approval_not_effective_yet"],
            identity=identity,
        )
    if checked_at >= expires_at:
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="expired",
            reason_codes=["operator_rollback_approval_expired"],
            identity=identity,
        )
    return _approval_verification_payload(
        approval=approval,
        checked_at=checked_at,
        status="approved",
        reason_codes=[
            "eligible_for_one_future_single_use_operator_rollback"
        ],
        identity=identity,
    )


def validate_write_model_configuration_operator_rollback_approval_verification(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict read-only rollback-approval verification."""

    verification = _mapping(
        payload,
        name="operator rollback approval verification",
    )
    _exact_fields(
        verification,
        expected=_APPROVAL_VERIFICATION_FIELDS,
        name="operator rollback approval verification",
    )
    if verification.get("schema_version") != (
        _APPROVAL_VERIFICATION_SCHEMA_VERSION
    ):
        raise ValueError(
            "unsupported rollback approval verification schema"
        )
    status = verification.get("status")
    if status not in _APPROVAL_VERIFICATION_STATUSES:
        raise ValueError(
            "operator rollback approval verification status is invalid"
        )
    expected_action = (
        "separate_single_use_rollback_command_required"
        if status == "approved"
        else "stop"
    )
    if verification.get("action") != expected_action:
        raise ValueError(
            "operator rollback approval verification action is invalid"
        )
    reasons = verification.get("reason_codes")
    if not isinstance(reasons, list) or not reasons:
        raise ValueError(
            "operator rollback approval verification reasons "
            "must be non-empty"
        )
    normalized_reasons = [
        _required_text(
            reason,
            name=f"reason_codes[{index}]",
            maximum_length=160,
        )
        for index, reason in enumerate(reasons)
    ]
    if len(normalized_reasons) != len(set(normalized_reasons)):
        raise ValueError(
            "operator rollback approval verification reasons "
            "contain duplicates"
        )
    identity = _mapping(
        verification.get("identity"),
        name="operator rollback approval verification identity",
    )
    _exact_fields(
        identity,
        expected=_APPROVAL_IDENTITY_FIELDS,
        name="operator rollback approval verification identity",
    )
    if any(not isinstance(value, bool) for value in identity.values()):
        raise ValueError(
            "rollback approval verification identity must be boolean"
        )
    window = _mapping(
        verification.get("effective_window"),
        name="effective_window",
    )
    _exact_fields(
        window,
        expected=_EFFECTIVE_WINDOW_FIELDS,
        name="effective_window",
    )
    approved_at = _parse_utc_timestamp(
        window.get("approved_at"),
        name="effective_window.approved_at",
    )
    expires_at = _parse_utc_timestamp(
        window.get("expires_at"),
        name="effective_window.expires_at",
    )
    _parse_utc_timestamp(
        window.get("checked_at"),
        name="effective_window.checked_at",
    )
    _validate_approval_window(
        approved_at=approved_at,
        expires_at=expires_at,
    )
    eligible = verification.get(
        "eligible_for_future_single_use_operator_rollback"
    )
    if eligible is not (status == "approved"):
        raise ValueError(
            "operator rollback approval eligibility is invalid"
        )
    if verification.get("maximum_uses") != 1:
        raise ValueError("maximum_uses must be 1")
    if verification.get("configuration_rollback_authorized") is not (
        status == "approved"
    ):
        raise ValueError(
            "operator rollback authorization evidence is invalid"
        )
    expected_flags = {
        "configuration_rollback_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    for field_name, expected in expected_flags.items():
        if verification.get(field_name) is not expected:
            raise ValueError(
                f"rollback approval verification {field_name} is invalid"
            )
    if verification.get("safety_boundaries") != (
        _APPROVAL_SAFETY_BOUNDARIES
    ):
        raise ValueError(
            "rollback approval verification boundaries are invalid"
        )
    if status == "approved" and not all(identity.values()):
        raise ValueError(
            "approved rollback verification is inconsistent"
        )


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
        raise ValueError(f"invalid {name} JSON: {target}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return target, payload


def load_write_model_configuration_operator_rollback_plan(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable operator rollback plan."""

    target, payload = _load_json_object(
        path,
        name="operator rollback plan",
    )
    validate_write_model_configuration_operator_rollback_plan(payload)
    return target, payload


def load_write_model_configuration_operator_rollback_approval_request(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one human rollback approval request."""

    target, payload = _load_json_object(
        path,
        name="operator rollback approval request",
    )
    validate_write_model_configuration_operator_rollback_approval_request(
        payload
    )
    return target, payload


def load_write_model_configuration_operator_rollback_approval(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable operator rollback approval."""

    target, payload = _load_json_object(
        path,
        name="operator rollback approval",
    )
    validate_write_model_configuration_operator_rollback_approval(
        payload
    )
    return target, payload


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


def _persist_immutable(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = _serialize(payload)
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if existing == dict(payload):
            return target
        raise FileExistsError(
            f"artifact already exists with different content: {target}"
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
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_path, target)
        except FileExistsError:
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
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return target


def persist_write_model_configuration_operator_rollback_plan(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist one immutable exact-byte rollback plan."""

    validate_write_model_configuration_operator_rollback_plan(payload)
    return _persist_immutable(payload, path)


def persist_write_model_configuration_operator_rollback_approval(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist one immutable short-lived rollback approval."""

    validate_write_model_configuration_operator_rollback_approval(
        payload
    )
    return _persist_immutable(payload, path)


def format_write_model_configuration_operator_rollback_plan_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format one compact operator rollback plan report."""

    validate_write_model_configuration_operator_rollback_plan(payload)
    return (
        "",
        "=" * 60,
        "Write model configuration operator rollback plan",
        f"  Status      : {payload['status']}",
        f"  Ticker      : {payload['ticker']}",
        f"  Operations  : {len(payload['operations'])}",
        f"  Reference   : {payload['rollback_reference']}",
        "  Authorized  : no",
        "  Configuration: unchanged",
        "  Model calls : none",
        "=" * 60,
    )


def format_write_model_configuration_operator_rollback_plan_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format one compact rollback-plan verification report."""

    validate_write_model_configuration_operator_rollback_plan_verification(
        payload
    )
    return (
        "",
        "=" * 60,
        "Write model configuration rollback plan verification",
        f"  Status      : {payload['status']}",
        (
            "  Runtime     : "
            f"{payload['identity']['current_runtime_snapshot_match']}"
        ),
        (
            "  Manifests   : "
            f"{payload['identity']['current_manifest_files_match']}"
        ),
        (
            "  Approval gate: "
            f"{payload['eligible_for_human_rollback_approval']}"
        ),
        "  Configuration: unchanged",
        "  Model calls : none",
        "=" * 60,
    )


def format_write_model_configuration_operator_rollback_approval_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format one compact rollback approval issuance report."""

    validate_write_model_configuration_operator_rollback_approval(
        payload
    )
    return (
        "",
        "=" * 60,
        "Write model configuration rollback approval",
        f"  Status      : {payload['status']}",
        f"  Approved by : {payload['approved_by']}",
        f"  Reference   : {payload['approval_reference']}",
        f"  Expires at  : {payload['expires_at']}",
        "  Consumed    : no",
        "  Rolled back : no",
        "  Model calls : none",
        "=" * 60,
    )


def format_write_model_configuration_operator_rollback_approval_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format one compact rollback-approval verification report."""

    validate_write_model_configuration_operator_rollback_approval_verification(
        payload
    )
    return (
        "",
        "=" * 60,
        "Write model configuration rollback approval verification",
        f"  Status      : {payload['status']}",
        f"  Action      : {payload['action']}",
        (
            "  Eligible    : "
            f"{payload['eligible_for_future_single_use_operator_rollback']}"
        ),
        "  Consumed    : no",
        "  Rolled back : no",
        "  Model calls : none",
        "=" * 60,
    )


__all__ = [
    "WriteModelConfigurationRollbackBlockedError",
    "build_write_model_configuration_operator_rollback_approval",
    "build_write_model_configuration_operator_rollback_plan",
    "format_write_model_configuration_operator_rollback_approval_report",
    "format_write_model_configuration_operator_rollback_approval_verification_report",
    "format_write_model_configuration_operator_rollback_plan_report",
    "format_write_model_configuration_operator_rollback_plan_verification_report",
    "load_write_model_configuration_operator_rollback_approval",
    "load_write_model_configuration_operator_rollback_approval_request",
    "load_write_model_configuration_operator_rollback_plan",
    "persist_write_model_configuration_operator_rollback_approval",
    "persist_write_model_configuration_operator_rollback_plan",
    "validate_write_model_configuration_operator_rollback_approval",
    "validate_write_model_configuration_operator_rollback_approval_request",
    "validate_write_model_configuration_operator_rollback_approval_verification",
    "validate_write_model_configuration_operator_rollback_plan",
    "validate_write_model_configuration_operator_rollback_plan_verification",
    "verify_write_model_configuration_operator_rollback_approval",
    "verify_write_model_configuration_operator_rollback_plan",
]
