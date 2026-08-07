"""Execute one approved operator write-routing rollback transactionally."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import tempfile
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dayu.services.write_model_configuration_application import (
    create_write_model_configuration_transaction_lock,
    load_write_model_configuration_application_receipt,
)
from dayu.services.write_model_configuration_preapplication import (
    validate_write_scene_model_routing_snapshot,
)
from dayu.services.write_model_configuration_rollback import (
    WriteModelConfigurationRollbackBlockedError,
    build_write_model_configuration_operator_rollback_plan,
    load_write_model_configuration_operator_rollback_approval,
    load_write_model_configuration_operator_rollback_plan,
    verify_write_model_configuration_operator_rollback_approval,
)


_INTENT_SCHEMA_VERSION = "write_model_configuration_operator_rollback_intent_v1"
_CONSUMPTION_SCHEMA_VERSION = "write_model_configuration_operator_rollback_consumption_v1"
_RECEIPT_SCHEMA_VERSION = "write_model_configuration_operator_rollback_receipt_v1"
_VERIFICATION_SCHEMA_VERSION = "write_model_configuration_operator_rollback_verification_v1"
_MANUAL_RECOVERY_EVIDENCE_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_evidence_v1"
_MANUAL_RECOVERY_EVIDENCE_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_evidence_v2"
_MANUAL_RECOVERY_CLEARANCE_REVOCATION_LINEAGE_SCHEMA_VERSION = (
    "write_model_configuration_manual_recovery_clearance_revocation_lineage_v1"
)
_MANUAL_RECOVERY_EVIDENCE_TYPE = "write_scene_model_routing_manual_recovery_evidence"
_MANUAL_RECOVERY_STATUS = "manual_recovery_required"
_MANUAL_RECOVERY_ACTION = "human_review_choose_one_exact_configuration_state"
_RECEIPT_TYPE = "write_scene_model_routing_operator_rollback"
_ROLLBACK_SCOPE = "single_use_transactional_exact_preapplication_byte_restore"
_MODEL_POINTER = "/model/default_name"
_RECEIPT_STATUSES = {
    "rolled_back",
    "rolled_forward",
    "recovery_failed",
}
_RECEIPT_ACTIONS = {
    "rolled_back": "configuration_rolled_back_stop",
    "rolled_forward": ("rollback_not_completed_applied_state_restored_new_approval_required"),
    "recovery_failed": "manual_recovery_required",
}
_SAFETY_BOUNDARIES = [
    "single_use_rollback_approval_consumed_before_first_manifest_replace",
    "all_targets_verified_before_approval_consumption",
    "configuration_apply_and_rollback_share_one_cross_process_lock",
    "write_ahead_intent_contains_exact_applied_and_restore_bytes",
    "each_manifest_replace_is_atomic",
    "post_rollback_fresh_runtime_preflight_required",
    "failure_restores_exact_applied_manifest_bytes",
    "interrupted_transaction_restores_applied_state_before_new_attempt",
    "rollback_does_not_modify_run_config_or_model_catalog",
    "rollback_does_not_call_models",
    "rollback_does_not_modify_secrets",
    "rollback_does_not_start_a_write_run",
]
_SOURCE_FIELDS = {
    "path",
    "file_fingerprint",
    "content_fingerprint",
}
_INTENT_FIELDS = {
    "schema_version",
    "transaction_id",
    "ticker",
    "rollback_plan_fingerprint",
    "rollback_approval_fingerprint",
    "application_receipt_fingerprint",
    "source_applied_routing_snapshot_fingerprint",
    "expected_restored_routing_snapshot_fingerprint",
    "created_at",
    "operations",
    "intent_fingerprint",
}
_INTENT_OPERATION_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "json_pointer",
    "expected_current_model_name",
    "restore_model_name",
    "applied_file_fingerprint",
    "applied_file_content_base64",
    "restore_file_fingerprint",
    "restore_file_content_base64",
}
_CONSUMPTION_FIELDS = {
    "schema_version",
    "rollback_approval_fingerprint",
    "rollback_plan_fingerprint",
    "application_receipt_fingerprint",
    "transaction_id",
    "transaction_dir",
    "intent_fingerprint",
    "consumed_at",
    "consumption_fingerprint",
}
_RECEIPT_OPERATION_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "json_pointer",
    "expected_current_model_name",
    "restored_model_name",
    "expected_current_file_fingerprint",
    "restored_file_fingerprint",
}
_FAILURE_FIELDS = {
    "stage",
    "error_type",
}
_RECEIPT_FIELDS = {
    "schema_version",
    "receipt_type",
    "scope",
    "status",
    "action",
    "ticker",
    "transaction_id",
    "source_rollback_plan",
    "source_rollback_approval",
    "source_application_receipt",
    "source_applied_routing_snapshot_fingerprint",
    "expected_restored_routing_snapshot_fingerprint",
    "post_operation_routing_snapshot_fingerprint",
    "approval_consumption",
    "operations",
    "failure",
    "applied_state_recovery_performed",
    "applied_state_recovery_exact",
    "completed_at",
    "safety_boundaries",
    "configuration_rollback_attempted",
    "configuration_rollback_completed",
    "approval_consumed",
    "model_execution_performed",
    "receipt_fingerprint",
}
_VERIFICATION_FIELDS = {
    "schema_version",
    "status",
    "action",
    "receipt_status",
    "expected_configuration_state",
    "expected_routing_snapshot_fingerprint",
    "current_routing_snapshot_fingerprint",
    "full_snapshot_match",
    "changed_operation_routes_match",
    "current_routing_matches_receipt",
    "eligible_for_new_operator_rollback_cycle",
    "reason_codes",
    "configuration_verification_performed",
    "configuration_rollback_performed",
    "approval_consumed",
    "approval_consumed_by_verification",
    "model_execution_performed",
}
_VERIFICATION_STATUSES = {
    "current",
    "routing_changed",
    "manual_recovery_required",
}
_EXPECTED_CONFIGURATION_STATES = {
    "rolled_back": "exact_preapplication_restored",
    "rolled_forward": "exact_applied_state_restored",
    "recovery_failed": "manual_recovery",
}
_MANUAL_RECOVERY_EVIDENCE_FIELDS_V1 = {
    "schema_version",
    "evidence_type",
    "status",
    "action",
    "ticker",
    "transaction_id",
    "source_rollback_receipt",
    "source_rollback_plan",
    "source_rollback_approval",
    "source_application_receipt",
    "approval_consumption",
    "source_applied_routing_snapshot_fingerprint",
    "expected_preapplication_routing_snapshot_fingerprint",
    "write_ahead_intent",
    "evidence_completeness",
    "observed_configuration_state",
    "operations",
    "reason_codes",
    "created_at",
    "safety_boundaries",
    "configuration_mutation_performed",
    "approval_consumed",
    "approval_consumed_by_evidence_export",
    "model_execution_performed",
    "evidence_fingerprint",
}
_MANUAL_RECOVERY_EVIDENCE_FIELDS_V2 = _MANUAL_RECOVERY_EVIDENCE_FIELDS_V1 | {"clearance_revocation_lineage"}
_MANUAL_RECOVERY_CLEARANCE_REVOCATION_LINEAGE_FIELDS = {
    "schema_version",
    "ticker",
    "revoked_transaction_id",
    "revoked_manual_recovery_receipt_fingerprint",
    "manual_recovery_clearance_fingerprint",
    "manual_recovery_clearance_revocation_fingerprint",
    "source_revoked_manual_recovery_receipt",
    "source_manual_recovery_clearance",
    "source_manual_recovery_clearance_revocation",
    "lineage_fingerprint",
}
_MANUAL_RECOVERY_INTENT_FIELDS = {
    "path",
    "status",
    "file_fingerprint",
    "content_fingerprint",
    "issue_codes",
}
_MANUAL_RECOVERY_OPERATION_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "json_pointer",
    "observed_state",
    "observed_file_fingerprint",
    "expected_applied_model_name",
    "expected_applied_file_fingerprint",
    "applied_candidate_available",
    "applied_file_content_base64",
    "expected_preapplication_model_name",
    "expected_preapplication_file_fingerprint",
    "preapplication_candidate_available",
    "preapplication_file_content_base64",
}
_MANUAL_RECOVERY_INTENT_STATUSES = {
    "valid",
    "missing",
    "invalid",
}
_MANUAL_RECOVERY_COMPLETENESS = {
    "complete",
    "partial",
}
_MANUAL_RECOVERY_OBSERVED_STATES = {
    "exact_applied",
    "exact_preapplication",
    "mixed_known",
    "indeterminate",
}
_MANUAL_RECOVERY_TARGET_STATES = {
    "applied",
    "preapplication",
    "unexpected",
    "missing",
    "unsafe_symlink",
    "unreadable",
}
_MANUAL_RECOVERY_SAFETY_BOUNDARIES = [
    "evidence_export_only",
    "recovery_failed_receipt_required",
    "source_plan_approval_consumption_and_application_receipt_verified",
    "write_ahead_intent_used_only_when_valid_and_transaction_bound",
    "current_target_files_observed_without_modification",
    "missing_or_invalid_applied_bytes_are_never_guessed",
    "exact_state_choice_requires_independent_human_review",
    "no_configuration_mutation",
    "no_new_approval_consumption",
    "no_model_execution",
    "no_secret_or_model_catalog_mutation",
    "no_recovery_command_generated",
]
_MANUAL_RECOVERY_V2_SAFETY_BOUNDARIES = [
    *_MANUAL_RECOVERY_SAFETY_BOUNDARIES,
    "clearance_revocation_lineage_bound_and_current",
]

RoutingSnapshotBuilder = Callable[[], Mapping[str, Any]]


class WriteModelConfigurationRollbackApplicationBlockedError(ValueError):
    """Raised when rollback is blocked before approval consumption."""


class WriteModelConfigurationRollbackApplicationBusyError(RuntimeError):
    """Raised when another configuration transaction owns the lock."""


class WriteModelConfigurationRollbackReceiptError(RuntimeError):
    """Raised when an internal result cannot be exported."""


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
    extra = sorted(actual - expected)
    raise ValueError(f"{name} fields are invalid: missing={missing}, extra={extra}")


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


def _target_path(value: object, *, name: str) -> Path:
    text = _required_text(
        value,
        name=name,
        maximum_length=32_768,
    )
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return Path(os.path.abspath(str(path)))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object, *, name: str) -> datetime:
    text = _required_text(
        value,
        name=name,
        maximum_length=64,
    )
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
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
    text = _required_text(
        value,
        name=name,
        maximum_length=80,
    ).lower()
    prefix = "sha256:"
    digest = text.removeprefix(prefix) if text.startswith(prefix) else ""
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{name} must be a sha256 fingerprint")
    return text


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


def _encode_base64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


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


def _persist_exclusive(
    payload: Mapping[str, Any],
    path: Path,
) -> Path:
    if path.exists():
        raise FileExistsError(f"single-use artifact already exists: {path}")
    return _persist_immutable(payload, path)


def _source_reference(
    *,
    path: Path,
    content_fingerprint: str,
) -> dict[str, str]:
    return {
        "path": str(path),
        "file_fingerprint": _file_fingerprint(path),
        "content_fingerprint": content_fingerprint,
    }


def _validate_source(
    value: object,
    *,
    name: str,
) -> dict[str, str]:
    source = _mapping(value, name=name)
    _exact_fields(source, expected=_SOURCE_FIELDS, name=name)
    return {
        "path": str(_absolute_path(source.get("path"), name=f"{name}.path")),
        "file_fingerprint": _validated_fingerprint(
            source.get("file_fingerprint"),
            name=f"{name}.file_fingerprint",
        ),
        "content_fingerprint": _validated_fingerprint(
            source.get("content_fingerprint"),
            name=f"{name}.content_fingerprint",
        ),
    }


def _validate_manual_recovery_clearance_revocation_lineage(
    value: object,
) -> dict[str, Any]:
    lineage = _mapping(
        value,
        name="manual recovery clearance revocation lineage",
    )
    _exact_fields(
        lineage,
        expected=(_MANUAL_RECOVERY_CLEARANCE_REVOCATION_LINEAGE_FIELDS),
        name="manual recovery clearance revocation lineage",
    )
    if lineage.get("schema_version") != (_MANUAL_RECOVERY_CLEARANCE_REVOCATION_LINEAGE_SCHEMA_VERSION):
        raise ValueError("manual recovery clearance revocation lineage schema is invalid")
    _required_text(
        lineage.get("ticker"),
        name="clearance_revocation_lineage.ticker",
        maximum_length=64,
    )
    _required_text(
        lineage.get("revoked_transaction_id"),
        name="clearance_revocation_lineage.revoked_transaction_id",
        maximum_length=64,
    )
    for field_name in (
        "revoked_manual_recovery_receipt_fingerprint",
        "manual_recovery_clearance_fingerprint",
        "manual_recovery_clearance_revocation_fingerprint",
    ):
        _validated_fingerprint(
            lineage.get(field_name),
            name=f"clearance_revocation_lineage.{field_name}",
        )
    for field_name in (
        "source_revoked_manual_recovery_receipt",
        "source_manual_recovery_clearance",
        "source_manual_recovery_clearance_revocation",
    ):
        _validate_source(
            lineage.get(field_name),
            name=f"clearance_revocation_lineage.{field_name}",
        )
    fingerprint = _validated_fingerprint(
        lineage.get("lineage_fingerprint"),
        name="clearance_revocation_lineage.lineage_fingerprint",
    )
    unsigned = dict(lineage)
    unsigned.pop("lineage_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("manual recovery clearance revocation lineage fingerprint mismatch")
    return dict(lineage)


def validate_write_model_configuration_manual_recovery_clearance_revocation_lineage(
    payload: Mapping[str, Any],
) -> None:
    """Validate one strict revoked-clearance restart lineage."""

    _validate_manual_recovery_clearance_revocation_lineage(payload)


def _load_manual_recovery_lineage_source(
    source: Mapping[str, Any],
    *,
    name: str,
    fingerprint_field: str,
) -> dict[str, Any]:
    source_view = _validate_source(source, name=name)
    raw_path = Path(source_view["path"]).expanduser()
    if raw_path.is_symlink():
        raise ValueError(f"{name} must not be a symlink")
    path = raw_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{name} does not exist: {path}")
    content = path.read_bytes()
    if not hmac.compare_digest(
        _bytes_fingerprint(content),
        source_view["file_fingerprint"],
    ):
        raise ValueError(f"{name} file fingerprint changed")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} is not valid UTF-8 JSON") from exc
    artifact = _mapping(payload, name=name)
    content_fingerprint = _validated_fingerprint(
        artifact.get(fingerprint_field),
        name=f"{name}.{fingerprint_field}",
    )
    if not hmac.compare_digest(
        content_fingerprint,
        source_view["content_fingerprint"],
    ):
        raise ValueError(f"{name} content fingerprint changed")
    return dict(artifact)


def assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current(
    payload: Mapping[str, Any],
) -> None:
    """Block unless every revoked-clearance lineage artifact is current."""

    lineage = _validate_manual_recovery_clearance_revocation_lineage(payload)
    receipt = _load_manual_recovery_lineage_source(
        lineage["source_revoked_manual_recovery_receipt"],
        name="revoked manual recovery receipt",
        fingerprint_field="receipt_fingerprint",
    )
    clearance = _load_manual_recovery_lineage_source(
        lineage["source_manual_recovery_clearance"],
        name="manual recovery clearance",
        fingerprint_field="clearance_fingerprint",
    )
    revocation = _load_manual_recovery_lineage_source(
        lineage["source_manual_recovery_clearance_revocation"],
        name="manual recovery clearance revocation",
        fingerprint_field="revocation_fingerprint",
    )
    expected_identity = {
        "ticker": lineage["ticker"],
        "transaction_id": lineage["revoked_transaction_id"],
    }
    for artifact_name, artifact in (
        ("revoked manual recovery receipt", receipt),
        ("manual recovery clearance", clearance),
        ("manual recovery clearance revocation", revocation),
    ):
        for field_name, expected_value in expected_identity.items():
            if artifact.get(field_name) != expected_value:
                raise ValueError(f"{artifact_name} {field_name} changed")
    fingerprint_checks = (
        (
            receipt.get("receipt_fingerprint"),
            lineage["revoked_manual_recovery_receipt_fingerprint"],
            "revoked manual recovery receipt",
        ),
        (
            clearance.get("clearance_fingerprint"),
            lineage["manual_recovery_clearance_fingerprint"],
            "manual recovery clearance",
        ),
        (
            revocation.get("revocation_fingerprint"),
            lineage["manual_recovery_clearance_revocation_fingerprint"],
            "manual recovery clearance revocation",
        ),
        (
            clearance.get("manual_recovery_receipt_fingerprint"),
            lineage["revoked_manual_recovery_receipt_fingerprint"],
            "manual recovery clearance receipt identity",
        ),
        (
            revocation.get("manual_recovery_receipt_fingerprint"),
            lineage["revoked_manual_recovery_receipt_fingerprint"],
            "manual recovery clearance revocation receipt identity",
        ),
        (
            revocation.get("manual_recovery_clearance_fingerprint"),
            lineage["manual_recovery_clearance_fingerprint"],
            "manual recovery clearance revocation clearance identity",
        ),
    )
    for actual, expected, name in fingerprint_checks:
        if not isinstance(actual, str) or not hmac.compare_digest(
            actual,
            str(expected),
        ):
            raise ValueError(f"{name} changed")
    if (
        receipt.get("status") != "recovered"
        or clearance.get("status") != "cleared"
        or revocation.get("status") != "revoked"
    ):
        raise ValueError("manual recovery clearance revocation lineage states changed")


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


def _operation_key(value: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(value.get("role") or ""),
        str(value.get("scene_name") or ""),
    )


def _scene_map(
    snapshot: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    raw_scenes = snapshot.get("scenes")
    if not isinstance(raw_scenes, list):
        raise ValueError("routing snapshot scenes must be a list")
    return {
        _operation_key(_mapping(scene, name=f"scenes[{index}]")): (_mapping(scene, name=f"scenes[{index}]"))
        for index, scene in enumerate(raw_scenes)
    }


def _configuration_root_from_plan(
    plan: Mapping[str, Any],
) -> Path:
    raw_operations = plan.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("rollback plan operations must be non-empty")
    first = _mapping(raw_operations[0], name="operations[0]")
    first_target = _target_path(
        first.get("target_manifest_path"),
        name="operations[0].target_manifest_path",
    )
    manifest_root = first_target.parent
    if manifest_root.name != "manifests" or manifest_root.parent.name != "prompts":
        raise WriteModelConfigurationRollbackApplicationBlockedError("rollback plan manifest root is unsafe")
    return manifest_root.parent.parent


def _assert_safe_target(
    *,
    target: Path,
    config_root: Path,
    scene_name: str,
) -> None:
    manifest_root = config_root / "prompts" / "manifests"
    if target.parent != manifest_root or target.name != f"{scene_name}.json":
        raise WriteModelConfigurationRollbackApplicationBlockedError(
            f"rollback target for scene {scene_name!r} is unsafe"
        )
    if target.is_symlink():
        raise WriteModelConfigurationRollbackApplicationBlockedError(
            f"rollback target for scene {scene_name!r} is a symlink"
        )


def _manifest_payload(
    content: bytes,
    *,
    scene_name: str,
    expected_default: str,
    name: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} for scene {scene_name!r} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} for scene {scene_name!r} must be an object")
    model = payload.get("model")
    if not isinstance(model, dict):
        raise ValueError(f"{name} for scene {scene_name!r} has no model object")
    if model.get("default_name") != expected_default:
        raise WriteModelConfigurationRollbackApplicationBlockedError(
            f"{name} for scene {scene_name!r} has an unexpected model"
        )
    allowed_names = model.get("allowed_names")
    if not isinstance(allowed_names, list) or expected_default not in allowed_names:
        raise WriteModelConfigurationRollbackApplicationBlockedError(
            f"{name} for scene {scene_name!r} does not allow its model"
        )
    return payload


def _build_operations(
    *,
    plan: Mapping[str, Any],
    config_root: Path,
) -> list[dict[str, str]]:
    raw_operations = plan.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("rollback plan operations must be non-empty")
    operations: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    seen_paths: set[Path] = set()
    for index, raw_operation in enumerate(raw_operations):
        source = _mapping(
            raw_operation,
            name=f"operations[{index}]",
        )
        role = _required_text(
            source.get("role"),
            name=f"operations[{index}].role",
            maximum_length=32,
        )
        scene_name = _required_text(
            source.get("scene_name"),
            name=f"operations[{index}].scene_name",
            maximum_length=128,
        )
        expected_current_model = _required_text(
            source.get("expected_current_model_name"),
            name=(f"operations[{index}].expected_current_model_name"),
            maximum_length=256,
        )
        restore_model = _required_text(
            source.get("restore_model_name"),
            name=f"operations[{index}].restore_model_name",
            maximum_length=256,
        )
        if source.get("json_pointer") != _MODEL_POINTER:
            raise ValueError(f"rollback operation for {scene_name!r} has bad pointer")
        target = _target_path(
            source.get("target_manifest_path"),
            name=f"operations[{index}].target_manifest_path",
        )
        _assert_safe_target(
            target=target,
            config_root=config_root,
            scene_name=scene_name,
        )
        key = (role, scene_name)
        if key in seen_keys or target in seen_paths:
            raise ValueError("rollback plan operations contain duplicates")
        seen_keys.add(key)
        seen_paths.add(target)
        if not target.is_file():
            raise WriteModelConfigurationRollbackApplicationBlockedError(
                f"rollback target for scene {scene_name!r} is unavailable"
            )
        applied_bytes = target.read_bytes()
        applied_fingerprint = _bytes_fingerprint(applied_bytes)
        expected_applied_fingerprint = _validated_fingerprint(
            source.get("expected_current_file_fingerprint"),
            name=(f"operations[{index}].expected_current_file_fingerprint"),
        )
        if not hmac.compare_digest(
            applied_fingerprint,
            expected_applied_fingerprint,
        ):
            raise WriteModelConfigurationRollbackApplicationBlockedError(
                f"rollback target for scene {scene_name!r} changed"
            )
        restore_bytes = _decode_base64(
            source.get("restore_file_content_base64"),
            name=(f"operations[{index}].restore_file_content_base64"),
        )
        restore_fingerprint = _bytes_fingerprint(restore_bytes)
        expected_restore_fingerprint = _validated_fingerprint(
            source.get("restore_file_fingerprint"),
            name=f"operations[{index}].restore_file_fingerprint",
        )
        if not hmac.compare_digest(
            restore_fingerprint,
            expected_restore_fingerprint,
        ):
            raise ValueError(f"restore bytes for scene {scene_name!r} changed")
        applied_payload = _manifest_payload(
            applied_bytes,
            scene_name=scene_name,
            expected_default=expected_current_model,
            name="current manifest",
        )
        restore_payload = _manifest_payload(
            restore_bytes,
            scene_name=scene_name,
            expected_default=restore_model,
            name="restore manifest",
        )
        applied_model = _mapping(
            applied_payload.get("model"),
            name=f"current manifest {scene_name}.model",
        )
        if restore_model not in applied_model.get("allowed_names", []):
            raise WriteModelConfigurationRollbackApplicationBlockedError(
                f"current manifest for scene {scene_name!r} no longer allows the restore model"
            )
        normalized_applied = json.loads(json.dumps(applied_payload))
        normalized_applied["model"]["default_name"] = restore_model
        if normalized_applied != restore_payload:
            raise WriteModelConfigurationRollbackApplicationBlockedError(
                f"restore manifest for scene {scene_name!r} changes more than the approved default model"
            )
        operations.append(
            {
                "role": role,
                "scene_name": scene_name,
                "target_manifest_path": str(target),
                "json_pointer": _MODEL_POINTER,
                "expected_current_model_name": expected_current_model,
                "restore_model_name": restore_model,
                "applied_file_fingerprint": applied_fingerprint,
                "applied_file_content_base64": _encode_base64(applied_bytes),
                "restore_file_fingerprint": restore_fingerprint,
                "restore_file_content_base64": _encode_base64(restore_bytes),
            }
        )
    return operations


def _validate_intent_operation(
    value: object,
    *,
    name: str,
) -> dict[str, str]:
    operation = _mapping(value, name=name)
    _exact_fields(
        operation,
        expected=_INTENT_OPERATION_FIELDS,
        name=name,
    )
    normalized = {
        field_name: _required_text(
            operation.get(field_name),
            name=f"{name}.{field_name}",
            maximum_length=(1_000_000 if field_name.endswith("_content_base64") else 32_768),
        )
        for field_name in _INTENT_OPERATION_FIELDS
    }
    if normalized["json_pointer"] != _MODEL_POINTER:
        raise ValueError(f"{name}.json_pointer is invalid")
    target = _target_path(
        normalized["target_manifest_path"],
        name=f"{name}.target_manifest_path",
    )
    normalized["target_manifest_path"] = str(target)
    for prefix in ("applied", "restore"):
        content = _decode_base64(
            normalized[f"{prefix}_file_content_base64"],
            name=f"{name}.{prefix}_file_content_base64",
        )
        expected = _validated_fingerprint(
            normalized[f"{prefix}_file_fingerprint"],
            name=f"{name}.{prefix}_file_fingerprint",
        )
        if not hmac.compare_digest(
            _bytes_fingerprint(content),
            expected,
        ):
            raise ValueError(f"{name} {prefix} file fingerprint mismatch")
    return normalized


def validate_write_model_configuration_operator_rollback_intent(
    payload: Mapping[str, Any],
) -> None:
    """Validate one write-ahead operator rollback intent."""

    intent = _mapping(payload, name="operator rollback intent")
    _exact_fields(
        intent,
        expected=_INTENT_FIELDS,
        name="operator rollback intent",
    )
    if intent.get("schema_version") != _INTENT_SCHEMA_VERSION:
        raise ValueError("unsupported operator rollback intent schema")
    _required_text(
        intent.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    _required_text(
        intent.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    for field_name in (
        "rollback_plan_fingerprint",
        "rollback_approval_fingerprint",
        "application_receipt_fingerprint",
        "source_applied_routing_snapshot_fingerprint",
        "expected_restored_routing_snapshot_fingerprint",
    ):
        _validated_fingerprint(
            intent.get(field_name),
            name=field_name,
        )
    _parse_utc(intent.get("created_at"), name="created_at")
    raw_operations = intent.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("operator rollback intent operations are empty")
    operations = [
        _validate_intent_operation(
            operation,
            name=f"operations[{index}]",
        )
        for index, operation in enumerate(raw_operations)
    ]
    keys = [_operation_key(operation) for operation in operations]
    paths = [operation["target_manifest_path"] for operation in operations]
    if len(keys) != len(set(keys)) or len(paths) != len(set(paths)):
        raise ValueError("operator rollback intent contains duplicates")
    fingerprint = _validated_fingerprint(
        intent.get("intent_fingerprint"),
        name="intent_fingerprint",
    )
    unsigned = dict(intent)
    unsigned.pop("intent_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("operator rollback intent fingerprint mismatch")


def _build_intent(
    *,
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
    transaction_id: str,
    now: datetime,
) -> dict[str, Any]:
    receipt_source = _mapping(
        plan.get("source_application_receipt"),
        name="source_application_receipt",
    )
    payload: dict[str, Any] = {
        "schema_version": _INTENT_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "ticker": plan["ticker"],
        "rollback_plan_fingerprint": plan["plan_fingerprint"],
        "rollback_approval_fingerprint": approval["approval_fingerprint"],
        "application_receipt_fingerprint": receipt_source["content_fingerprint"],
        "source_applied_routing_snapshot_fingerprint": plan["expected_current_routing_snapshot_fingerprint"],
        "expected_restored_routing_snapshot_fingerprint": plan["expected_restored_routing_snapshot_fingerprint"],
        "created_at": _format_utc(now),
        "operations": [dict(operation) for operation in operations],
    }
    payload["intent_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_operator_rollback_intent(payload)
    return payload


def _persist_or_reuse_intent(
    *,
    intent: Mapping[str, Any],
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        _persist_immutable(intent, path)
        return dict(intent)
    _resolved, existing = _load_json_object(
        path,
        name="operator rollback intent",
    )
    validate_write_model_configuration_operator_rollback_intent(existing)
    ignored = {"created_at", "intent_fingerprint"}
    expected_core = {key: value for key, value in intent.items() if key not in ignored}
    existing_core = {key: value for key, value in existing.items() if key not in ignored}
    if existing_core != expected_core:
        raise WriteModelConfigurationRollbackApplicationBlockedError(
            "existing unconsumed rollback intent does not match"
        )
    return existing


def _validate_consumption(payload: Mapping[str, Any]) -> None:
    consumption = _mapping(
        payload,
        name="operator rollback approval consumption",
    )
    _exact_fields(
        consumption,
        expected=_CONSUMPTION_FIELDS,
        name="operator rollback approval consumption",
    )
    if consumption.get("schema_version") != _CONSUMPTION_SCHEMA_VERSION:
        raise ValueError("unsupported operator rollback consumption schema")
    for field_name in (
        "rollback_approval_fingerprint",
        "rollback_plan_fingerprint",
        "application_receipt_fingerprint",
        "intent_fingerprint",
    ):
        _validated_fingerprint(
            consumption.get(field_name),
            name=field_name,
        )
    _required_text(
        consumption.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    _absolute_path(
        consumption.get("transaction_dir"),
        name="transaction_dir",
    )
    _parse_utc(consumption.get("consumed_at"), name="consumed_at")
    fingerprint = _validated_fingerprint(
        consumption.get("consumption_fingerprint"),
        name="consumption_fingerprint",
    )
    unsigned = dict(consumption)
    unsigned.pop("consumption_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("operator rollback consumption fingerprint mismatch")


def _consumption_payload(
    *,
    approval: Mapping[str, Any],
    plan: Mapping[str, Any],
    transaction_id: str,
    transaction_dir: Path,
    intent: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    receipt_source = _mapping(
        plan.get("source_application_receipt"),
        name="source_application_receipt",
    )
    payload: dict[str, Any] = {
        "schema_version": _CONSUMPTION_SCHEMA_VERSION,
        "rollback_approval_fingerprint": approval["approval_fingerprint"],
        "rollback_plan_fingerprint": plan["plan_fingerprint"],
        "application_receipt_fingerprint": receipt_source["content_fingerprint"],
        "transaction_id": transaction_id,
        "transaction_dir": str(transaction_dir),
        "intent_fingerprint": intent["intent_fingerprint"],
        "consumed_at": _format_utc(now),
    }
    payload["consumption_fingerprint"] = _fingerprint(payload)
    _validate_consumption(payload)
    return payload


def _load_consumption(path: Path) -> dict[str, Any]:
    _resolved, payload = _load_json_object(
        path,
        name="operator rollback approval consumption",
    )
    _validate_consumption(payload)
    return payload


def _transaction_id(
    *,
    approval_fingerprint: str,
    plan_fingerprint: str,
) -> str:
    material = (
        b"write-model-configuration-operator-rollback\0"
        + approval_fingerprint.encode("ascii")
        + b"\0"
        + plan_fingerprint.encode("ascii")
    )
    return hashlib.sha256(material).hexdigest()


def _transaction_dir(
    *,
    workspace_dir: str | Path,
    transaction_id: str,
) -> Path:
    return (
        Path(workspace_dir).expanduser().resolve()
        / ".dayu"
        / "write-model-configuration-rollbacks"
        / "transactions"
        / transaction_id
    ).resolve()


def _consumption_path(
    *,
    rollback_plan_path: Path,
    approval_fingerprint: str,
) -> Path:
    digest = approval_fingerprint.removeprefix("sha256:")
    return (
        rollback_plan_path.parent
        / ".dayu"
        / "consumed-write-model-configuration-rollback-approvals"
        / f"{digest}.consumed.json"
    ).resolve()


def _assert_consumption_identity(
    *,
    consumption: Mapping[str, Any],
    approval: Mapping[str, Any],
    plan: Mapping[str, Any],
    transaction_id: str,
) -> None:
    receipt_source = _mapping(
        plan.get("source_application_receipt"),
        name="source_application_receipt",
    )
    expected = {
        "rollback_approval_fingerprint": approval["approval_fingerprint"],
        "rollback_plan_fingerprint": plan["plan_fingerprint"],
        "application_receipt_fingerprint": receipt_source["content_fingerprint"],
        "transaction_id": transaction_id,
    }
    for field_name, expected_value in expected.items():
        if consumption.get(field_name) != expected_value:
            raise WriteModelConfigurationRollbackApplicationBlockedError(
                "existing rollback approval consumption identity does not match"
            )
    transaction_dir = _absolute_path(
        consumption.get("transaction_dir"),
        name="transaction_dir",
    )
    if (
        transaction_dir.name != transaction_id
        or transaction_dir.parent.name != "transactions"
        or transaction_dir.parent.parent.name != "write-model-configuration-rollbacks"
    ):
        raise WriteModelConfigurationRollbackApplicationBlockedError("existing rollback transaction path is invalid")


def _validate_receipt_operation(
    value: object,
    *,
    name: str,
) -> dict[str, str]:
    operation = _mapping(value, name=name)
    _exact_fields(
        operation,
        expected=_RECEIPT_OPERATION_FIELDS,
        name=name,
    )
    normalized = {
        field_name: _required_text(
            operation.get(field_name),
            name=f"{name}.{field_name}",
            maximum_length=32_768,
        )
        for field_name in _RECEIPT_OPERATION_FIELDS
    }
    normalized["target_manifest_path"] = str(
        _target_path(
            normalized["target_manifest_path"],
            name=f"{name}.target_manifest_path",
        )
    )
    if normalized["json_pointer"] != _MODEL_POINTER:
        raise ValueError(f"{name}.json_pointer is invalid")
    for field_name in (
        "expected_current_file_fingerprint",
        "restored_file_fingerprint",
    ):
        normalized[field_name] = _validated_fingerprint(
            normalized[field_name],
            name=f"{name}.{field_name}",
        )
    return normalized


def _receipt_operations(
    operations: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": str(operation["role"]),
            "scene_name": str(operation["scene_name"]),
            "target_manifest_path": str(operation["target_manifest_path"]),
            "json_pointer": _MODEL_POINTER,
            "expected_current_model_name": str(operation["expected_current_model_name"]),
            "restored_model_name": str(operation["restore_model_name"]),
            "expected_current_file_fingerprint": str(
                operation.get(
                    "applied_file_fingerprint",
                    operation.get("expected_current_file_fingerprint"),
                )
            ),
            "restored_file_fingerprint": str(operation["restore_file_fingerprint"]),
        }
        for operation in operations
    ]


def validate_write_model_configuration_operator_rollback_receipt(
    payload: Mapping[str, Any],
) -> None:
    """Validate one strict operator rollback transaction receipt."""

    receipt = _mapping(payload, name="operator rollback receipt")
    _exact_fields(
        receipt,
        expected=_RECEIPT_FIELDS,
        name="operator rollback receipt",
    )
    if receipt.get("schema_version") != _RECEIPT_SCHEMA_VERSION:
        raise ValueError("unsupported operator rollback receipt schema")
    if receipt.get("receipt_type") != _RECEIPT_TYPE:
        raise ValueError("unsupported operator rollback receipt type")
    if receipt.get("scope") != _ROLLBACK_SCOPE:
        raise ValueError("operator rollback receipt scope is invalid")
    status = receipt.get("status")
    if status not in _RECEIPT_STATUSES:
        raise ValueError("operator rollback receipt status is invalid")
    if receipt.get("action") != _RECEIPT_ACTIONS[str(status)]:
        raise ValueError("operator rollback receipt action is invalid")
    _required_text(
        receipt.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    _required_text(
        receipt.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    plan_source = _validate_source(
        receipt.get("source_rollback_plan"),
        name="source_rollback_plan",
    )
    approval_source = _validate_source(
        receipt.get("source_rollback_approval"),
        name="source_rollback_approval",
    )
    application_source = _validate_source(
        receipt.get("source_application_receipt"),
        name="source_application_receipt",
    )
    del plan_source, approval_source, application_source
    source_applied = _validated_fingerprint(
        receipt.get("source_applied_routing_snapshot_fingerprint"),
        name="source_applied_routing_snapshot_fingerprint",
    )
    expected_restored = _validated_fingerprint(
        receipt.get("expected_restored_routing_snapshot_fingerprint"),
        name="expected_restored_routing_snapshot_fingerprint",
    )
    post_value = receipt.get("post_operation_routing_snapshot_fingerprint")
    post_fingerprint = (
        None
        if post_value is None
        else _validated_fingerprint(
            post_value,
            name="post_operation_routing_snapshot_fingerprint",
        )
    )
    _validate_source(
        receipt.get("approval_consumption"),
        name="approval_consumption",
    )
    raw_operations = receipt.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("operator rollback receipt operations are empty")
    operations = [
        _validate_receipt_operation(
            operation,
            name=f"operations[{index}]",
        )
        for index, operation in enumerate(raw_operations)
    ]
    keys = [_operation_key(operation) for operation in operations]
    paths = [operation["target_manifest_path"] for operation in operations]
    if len(keys) != len(set(keys)) or len(paths) != len(set(paths)):
        raise ValueError("operator rollback receipt has duplicates")
    failure = receipt.get("failure")
    if status == "rolled_back":
        if failure is not None:
            raise ValueError("successful operator rollback cannot contain failure")
    else:
        failure_view = _mapping(
            failure,
            name="operator rollback failure",
        )
        _exact_fields(
            failure_view,
            expected=_FAILURE_FIELDS,
            name="operator rollback failure",
        )
        _required_text(
            failure_view.get("stage"),
            name="failure.stage",
            maximum_length=128,
        )
        _required_text(
            failure_view.get("error_type"),
            name="failure.error_type",
            maximum_length=256,
        )
    recovery_performed = receipt.get("applied_state_recovery_performed")
    recovery_exact = receipt.get("applied_state_recovery_exact")
    if not isinstance(recovery_performed, bool) or not isinstance(
        recovery_exact,
        bool,
    ):
        raise ValueError("operator rollback recovery flags are invalid")
    if status == "rolled_back":
        if post_fingerprint != expected_restored or recovery_performed or recovery_exact:
            raise ValueError("successful operator rollback state is inconsistent")
    elif status == "rolled_forward":
        if post_fingerprint != source_applied or not recovery_performed or not recovery_exact:
            raise ValueError("rolled-forward operator rollback state is inconsistent")
    elif post_fingerprint is not None or not recovery_performed or recovery_exact:
        raise ValueError("failed operator rollback recovery state is inconsistent")
    _parse_utc(receipt.get("completed_at"), name="completed_at")
    if receipt.get("safety_boundaries") != _SAFETY_BOUNDARIES:
        raise ValueError("operator rollback safety boundaries are invalid")
    if receipt.get("configuration_rollback_attempted") is not True:
        raise ValueError("operator rollback attempt evidence is invalid")
    if receipt.get("configuration_rollback_completed") is not (status == "rolled_back"):
        raise ValueError("operator rollback completion evidence is invalid")
    if receipt.get("approval_consumed") is not True:
        raise ValueError("operator rollback approval was not consumed")
    if receipt.get("model_execution_performed") is not False:
        raise ValueError("operator rollback receipt claims model execution")
    fingerprint = _validated_fingerprint(
        receipt.get("receipt_fingerprint"),
        name="receipt_fingerprint",
    )
    unsigned = dict(receipt)
    unsigned.pop("receipt_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("operator rollback receipt fingerprint mismatch")


def _build_receipt(
    *,
    status: str,
    transaction_id: str,
    plan_path: Path,
    plan: Mapping[str, Any],
    approval_path: Path,
    approval: Mapping[str, Any],
    consumption_path: Path,
    consumption: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
    post_snapshot: Mapping[str, Any] | None,
    failure_stage: str | None,
    error_type: str | None,
    completed_at: datetime,
) -> dict[str, Any]:
    if status not in _RECEIPT_STATUSES:
        raise ValueError("operator rollback receipt status is invalid")
    application_source = _validate_source(
        plan.get("source_application_receipt"),
        name="source_application_receipt",
    )
    failure: dict[str, str] | None = None
    if status != "rolled_back":
        failure = {
            "stage": _required_text(
                failure_stage,
                name="failure_stage",
                maximum_length=128,
            ),
            "error_type": _required_text(
                error_type,
                name="error_type",
                maximum_length=256,
            ),
        }
    payload: dict[str, Any] = {
        "schema_version": _RECEIPT_SCHEMA_VERSION,
        "receipt_type": _RECEIPT_TYPE,
        "scope": _ROLLBACK_SCOPE,
        "status": status,
        "action": _RECEIPT_ACTIONS[status],
        "ticker": plan["ticker"],
        "transaction_id": transaction_id,
        "source_rollback_plan": _source_reference(
            path=plan_path,
            content_fingerprint=str(plan["plan_fingerprint"]),
        ),
        "source_rollback_approval": _source_reference(
            path=approval_path,
            content_fingerprint=str(approval["approval_fingerprint"]),
        ),
        "source_application_receipt": application_source,
        "source_applied_routing_snapshot_fingerprint": plan["expected_current_routing_snapshot_fingerprint"],
        "expected_restored_routing_snapshot_fingerprint": plan["expected_restored_routing_snapshot_fingerprint"],
        "post_operation_routing_snapshot_fingerprint": (
            None
            if post_snapshot is None
            else _snapshot_fingerprint(
                post_snapshot,
                name="post-operation routing snapshot",
            )
        ),
        "approval_consumption": _source_reference(
            path=consumption_path,
            content_fingerprint=str(consumption["consumption_fingerprint"]),
        ),
        "operations": _receipt_operations(operations),
        "failure": failure,
        "applied_state_recovery_performed": status != "rolled_back",
        "applied_state_recovery_exact": status == "rolled_forward",
        "completed_at": _format_utc(completed_at),
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
        "configuration_rollback_attempted": True,
        "configuration_rollback_completed": status == "rolled_back",
        "approval_consumed": True,
        "model_execution_performed": False,
    }
    payload["receipt_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_operator_rollback_receipt(payload)
    return payload


def load_write_model_configuration_operator_rollback_receipt(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable operator rollback receipt."""

    target, payload = _load_json_object(
        path,
        name="operator rollback receipt",
    )
    validate_write_model_configuration_operator_rollback_receipt(payload)
    return target, payload


def persist_write_model_configuration_operator_rollback_receipt(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist one immutable operator rollback receipt."""

    validate_write_model_configuration_operator_rollback_receipt(payload)
    return _persist_immutable(payload, path)


def _probe_receipt_parent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"operator rollback receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_path_value = tempfile.mkstemp(
        prefix=f".{path.name}.probe.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_path_value)
    try:
        os.close(file_descriptor)
        file_descriptor = -1
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _persist_receipts(
    *,
    receipt: Mapping[str, Any],
    internal_receipt_path: Path,
    external_receipt_path: Path,
) -> None:
    _persist_immutable(receipt, internal_receipt_path)
    try:
        _persist_immutable(receipt, external_receipt_path)
    except (FileExistsError, OSError) as exc:
        raise WriteModelConfigurationRollbackReceiptError(
            "operator rollback result is recorded internally but the requested receipt could not be exported"
        ) from exc


def _stage_content(*, target: Path, content: bytes) -> Path:
    file_descriptor, temp_path_value = tempfile.mkstemp(
        prefix=f".{target.name}.dayu-rollback.",
        suffix=".tmp",
        dir=target.parent,
    )
    temp_path = Path(temp_path_value)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            file_descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temp_path, target.stat().st_mode)
        except OSError:
            pass
    except BaseException:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return temp_path


def _replace_staged_file(*, staged: Path, target: Path) -> None:
    os.replace(staged, target)


def _replace_content_atomically(*, target: Path, content: bytes) -> None:
    staged = _stage_content(target=target, content=content)
    try:
        _replace_staged_file(staged=staged, target=target)
    finally:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass


def _assert_target_bytes_current(
    operations: Sequence[Mapping[str, Any]],
) -> None:
    for operation in operations:
        scene_name = str(operation["scene_name"])
        target = _target_path(
            operation["target_manifest_path"],
            name=f"target for {scene_name}",
        )
        if not target.is_file() or target.is_symlink():
            raise WriteModelConfigurationRollbackApplicationBlockedError(
                f"rollback target for scene {scene_name!r} is unavailable"
            )
        actual = _file_fingerprint(target)
        expected = str(operation["applied_file_fingerprint"])
        if not hmac.compare_digest(actual, expected):
            raise WriteModelConfigurationRollbackApplicationBlockedError(
                f"rollback target for scene {scene_name!r} changed"
            )


def _assert_intent_targets_safe(
    *,
    operations: Sequence[Mapping[str, Any]],
    config_root: Path,
) -> None:
    seen_paths: set[Path] = set()
    for operation in operations:
        scene_name = str(operation["scene_name"])
        target = _target_path(
            operation["target_manifest_path"],
            name=f"intent target for {scene_name}",
        )
        _assert_safe_target(
            target=target,
            config_root=config_root,
            scene_name=scene_name,
        )
        if target in seen_paths:
            raise ValueError("operator rollback intent paths duplicate")
        seen_paths.add(target)


def _verify_snapshot_fingerprint(
    *,
    snapshot: Mapping[str, Any],
    expected_fingerprint: str,
    name: str,
) -> None:
    actual = _snapshot_fingerprint(snapshot, name=name)
    if not hmac.compare_digest(actual, expected_fingerprint):
        raise RuntimeError(f"{name} does not match the approved routing state")


def _restore_applied_state(
    operations: Sequence[Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for operation in reversed(operations):
        scene_name = str(operation["scene_name"])
        target = _target_path(
            operation["target_manifest_path"],
            name=f"recovery target for {scene_name}",
        )
        applied_fingerprint = str(operation["applied_file_fingerprint"])
        restore_fingerprint = str(operation["restore_file_fingerprint"])
        try:
            current_fingerprint = _file_fingerprint(target)
        except OSError:
            failures.append(f"{scene_name}:target_unreadable")
            continue
        if hmac.compare_digest(
            current_fingerprint,
            applied_fingerprint,
        ):
            continue
        if not hmac.compare_digest(
            current_fingerprint,
            restore_fingerprint,
        ):
            failures.append(f"{scene_name}:unexpected_target_content")
            continue
        applied_bytes = _decode_base64(
            operation["applied_file_content_base64"],
            name=f"recovery applied bytes for {scene_name}",
        )
        try:
            _replace_content_atomically(
                target=target,
                content=applied_bytes,
            )
            if not hmac.compare_digest(
                _file_fingerprint(target),
                applied_fingerprint,
            ):
                failures.append(f"{scene_name}:recovery_mismatch")
        except OSError:
            failures.append(f"{scene_name}:recovery_failed")
    return not failures, failures


def _recover_consumed_transaction(
    *,
    transaction_id: str,
    plan_path: Path,
    plan: Mapping[str, Any],
    approval_path: Path,
    approval: Mapping[str, Any],
    consumption_path: Path,
    consumption: Mapping[str, Any],
    config_root: Path,
    snapshot_builder: RoutingSnapshotBuilder,
    internal_receipt_path: Path,
    external_receipt_path: Path,
    now: datetime,
) -> dict[str, Any]:
    intent_path = internal_receipt_path.parent / "intent.json"
    operations: list[dict[str, str]] | None = None
    error_type = "InterruptedOperatorRollback"
    if intent_path.is_file():
        try:
            _resolved, intent = _load_json_object(
                intent_path,
                name="operator rollback intent",
            )
            validate_write_model_configuration_operator_rollback_intent(intent)
            if (
                intent.get("intent_fingerprint") != consumption.get("intent_fingerprint")
                or intent.get("transaction_id") != transaction_id
            ):
                raise ValueError("operator rollback intent identity mismatch")
            raw_operations = intent.get("operations")
            assert isinstance(raw_operations, list)
            operations = [
                _validate_intent_operation(
                    operation,
                    name=f"intent.operations[{index}]",
                )
                for index, operation in enumerate(raw_operations)
            ]
            _assert_intent_targets_safe(
                operations=operations,
                config_root=config_root,
            )
        except (OSError, TypeError, ValueError) as exc:
            operations = None
            error_type = type(exc).__name__
    if operations is None:
        receipt = _build_receipt(
            status="recovery_failed",
            transaction_id=transaction_id,
            plan_path=plan_path,
            plan=plan,
            approval_path=approval_path,
            approval=approval,
            consumption_path=consumption_path,
            consumption=consumption,
            operations=[
                _mapping(
                    operation,
                    name=f"plan.operations[{index}]",
                )
                for index, operation in enumerate(plan.get("operations", []))
            ],
            post_snapshot=None,
            failure_stage="interrupted_transaction_recovery",
            error_type=error_type,
            completed_at=now,
        )
        _persist_receipts(
            receipt=receipt,
            internal_receipt_path=internal_receipt_path,
            external_receipt_path=external_receipt_path,
        )
        return receipt
    restored, _failures = _restore_applied_state(operations)
    post_snapshot: Mapping[str, Any] | None = None
    if restored:
        try:
            post_snapshot = dict(snapshot_builder())
            _verify_snapshot_fingerprint(
                snapshot=post_snapshot,
                expected_fingerprint=str(plan["expected_current_routing_snapshot_fingerprint"]),
                name="recovered applied routing snapshot",
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            restored = False
            post_snapshot = None
    receipt = _build_receipt(
        status="rolled_forward" if restored else "recovery_failed",
        transaction_id=transaction_id,
        plan_path=plan_path,
        plan=plan,
        approval_path=approval_path,
        approval=approval,
        consumption_path=consumption_path,
        consumption=consumption,
        operations=operations,
        post_snapshot=post_snapshot,
        failure_stage="interrupted_transaction_recovery",
        error_type=error_type,
        completed_at=now,
    )
    _persist_receipts(
        receipt=receipt,
        internal_receipt_path=internal_receipt_path,
        external_receipt_path=external_receipt_path,
    )
    return receipt


def _existing_transaction_result(
    *,
    transaction_id: str,
    plan_path: Path,
    plan: Mapping[str, Any],
    approval_path: Path,
    approval: Mapping[str, Any],
    consumption_path: Path,
    consumption: Mapping[str, Any],
    config_root: Path,
    snapshot_builder: RoutingSnapshotBuilder,
    external_receipt_path: Path,
    now: datetime,
) -> dict[str, Any]:
    transaction_dir = _absolute_path(
        consumption.get("transaction_dir"),
        name="consumption.transaction_dir",
    )
    internal_receipt_path = transaction_dir / "receipt.json"
    if internal_receipt_path.is_file():
        _resolved, receipt = load_write_model_configuration_operator_rollback_receipt(internal_receipt_path)
        if receipt.get("transaction_id") != transaction_id:
            raise ValueError("internal rollback receipt identity mismatch")
        try:
            _persist_immutable(receipt, external_receipt_path)
        except (FileExistsError, OSError) as exc:
            raise WriteModelConfigurationRollbackReceiptError(
                "operator rollback result is recorded internally but the requested receipt could not be exported"
            ) from exc
        return receipt
    return _recover_consumed_transaction(
        transaction_id=transaction_id,
        plan_path=plan_path,
        plan=plan,
        approval_path=approval_path,
        approval=approval,
        consumption_path=consumption_path,
        consumption=consumption,
        config_root=config_root,
        snapshot_builder=snapshot_builder,
        internal_receipt_path=internal_receipt_path,
        external_receipt_path=external_receipt_path,
        now=now,
    )


def apply_write_model_configuration_operator_rollback(
    *,
    rollback_plan_path: str | Path,
    rollback_approval_path: str | Path,
    workspace_dir: str | Path,
    receipt_output_path: str | Path,
    snapshot_builder: RoutingSnapshotBuilder,
    now: datetime,
) -> dict[str, Any]:
    """Consume one approval and restore exact preapplication bytes."""

    current_time = _normalize_now(now)
    resolved_plan_path, plan = load_write_model_configuration_operator_rollback_plan(rollback_plan_path)
    resolved_approval_path, approval = load_write_model_configuration_operator_rollback_approval(rollback_approval_path)
    approval_plan_source = _validate_source(
        approval.get("rollback_plan_source"),
        name="rollback_plan_source",
    )
    if (
        _absolute_path(
            approval_plan_source["path"],
            name="rollback_plan_source.path",
        )
        != resolved_plan_path
    ):
        raise WriteModelConfigurationRollbackApplicationBlockedError(
            "rollback approval is bound to a different plan path"
        )
    config_root = _configuration_root_from_plan(plan)
    approval_fingerprint = _validated_fingerprint(
        approval.get("approval_fingerprint"),
        name="approval_fingerprint",
    )
    plan_fingerprint = _validated_fingerprint(
        plan.get("plan_fingerprint"),
        name="plan_fingerprint",
    )
    transaction_id = _transaction_id(
        approval_fingerprint=approval_fingerprint,
        plan_fingerprint=plan_fingerprint,
    )
    transaction_dir = _transaction_dir(
        workspace_dir=workspace_dir,
        transaction_id=transaction_id,
    )
    internal_receipt_path = transaction_dir / "receipt.json"
    intent_path = transaction_dir / "intent.json"
    external_receipt_path = Path(receipt_output_path).expanduser().resolve()
    consumption_path = _consumption_path(
        rollback_plan_path=resolved_plan_path,
        approval_fingerprint=approval_fingerprint,
    )
    for artifact_name, artifact_path in (
        ("transaction directory", transaction_dir),
        ("approval consumption", consumption_path),
        ("external receipt", external_receipt_path),
    ):
        if _is_relative_to(artifact_path, config_root):
            raise (
                WriteModelConfigurationRollbackApplicationBlockedError(
                    f"{artifact_name} must be outside the configuration root"
                )
            )
    transaction_lock = create_write_model_configuration_transaction_lock(config_root)
    try:
        transaction_lock.acquire()
    except RuntimeError as exc:
        raise WriteModelConfigurationRollbackApplicationBusyError(
            "another write-model configuration transaction holds the lock"
        ) from exc
    staged_files: list[Path] = []
    try:
        if consumption_path.is_file():
            consumption = _load_consumption(consumption_path)
            _assert_consumption_identity(
                consumption=consumption,
                approval=approval,
                plan=plan,
                transaction_id=transaction_id,
            )
            return _existing_transaction_result(
                transaction_id=transaction_id,
                plan_path=resolved_plan_path,
                plan=plan,
                approval_path=resolved_approval_path,
                approval=approval,
                consumption_path=consumption_path,
                consumption=consumption,
                config_root=config_root,
                snapshot_builder=snapshot_builder,
                external_receipt_path=external_receipt_path,
                now=current_time,
            )
        _probe_receipt_parent(external_receipt_path)
        current_snapshot = dict(snapshot_builder())
        try:
            verification = verify_write_model_configuration_operator_rollback_approval(
                approval,
                current_routing_snapshot=current_snapshot,
                now=current_time,
            )
        except (
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise (
                WriteModelConfigurationRollbackApplicationBlockedError("rollback approval verification failed")
            ) from exc
        if verification.get("status") != "approved":
            raise WriteModelConfigurationRollbackApplicationBlockedError("operator rollback approval is not current")
        operations = _build_operations(
            plan=plan,
            config_root=config_root,
        )
        _assert_target_bytes_current(operations)
        intent = _build_intent(
            plan=plan,
            approval=approval,
            operations=operations,
            transaction_id=transaction_id,
            now=current_time,
        )
        intent = _persist_or_reuse_intent(
            intent=intent,
            path=intent_path,
        )
        for operation in operations:
            staged_files.append(
                _stage_content(
                    target=_target_path(
                        operation["target_manifest_path"],
                        name=(f"target for {operation['scene_name']}"),
                    ),
                    content=_decode_base64(
                        operation["restore_file_content_base64"],
                        name=(f"restore bytes for {operation['scene_name']}"),
                    ),
                )
            )
        _assert_target_bytes_current(operations)
        consumption = _consumption_payload(
            approval=approval,
            plan=plan,
            transaction_id=transaction_id,
            transaction_dir=transaction_dir,
            intent=intent,
            now=current_time,
        )
        _persist_exclusive(consumption, consumption_path)
        failure_stage = "manifest_rollback"
        try:
            for operation, staged in zip(
                operations,
                staged_files,
                strict=True,
            ):
                target = _target_path(
                    operation["target_manifest_path"],
                    name=f"target for {operation['scene_name']}",
                )
                if not hmac.compare_digest(
                    _file_fingerprint(target),
                    str(operation["applied_file_fingerprint"]),
                ):
                    raise RuntimeError("manifest changed after rollback approval consumption")
                _replace_staged_file(staged=staged, target=target)
                if not hmac.compare_digest(
                    _file_fingerprint(target),
                    str(operation["restore_file_fingerprint"]),
                ):
                    raise RuntimeError("restored manifest fingerprint mismatch")
            failure_stage = "post_rollback_preflight"
            restored_snapshot = dict(snapshot_builder())
            _verify_snapshot_fingerprint(
                snapshot=restored_snapshot,
                expected_fingerprint=str(plan["expected_restored_routing_snapshot_fingerprint"]),
                name="restored routing snapshot",
            )
        except BaseException as exc:
            recovered, _failures = _restore_applied_state(operations)
            recovered_snapshot: Mapping[str, Any] | None = None
            if recovered:
                try:
                    recovered_snapshot = dict(snapshot_builder())
                    _verify_snapshot_fingerprint(
                        snapshot=recovered_snapshot,
                        expected_fingerprint=str(plan["expected_current_routing_snapshot_fingerprint"]),
                        name="recovered applied routing snapshot",
                    )
                except (
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ):
                    recovered = False
                    recovered_snapshot = None
            receipt = _build_receipt(
                status=("rolled_forward" if recovered else "recovery_failed"),
                transaction_id=transaction_id,
                plan_path=resolved_plan_path,
                plan=plan,
                approval_path=resolved_approval_path,
                approval=approval,
                consumption_path=consumption_path,
                consumption=consumption,
                operations=operations,
                post_snapshot=recovered_snapshot,
                failure_stage=failure_stage,
                error_type=type(exc).__name__,
                completed_at=current_time,
            )
            _persist_receipts(
                receipt=receipt,
                internal_receipt_path=internal_receipt_path,
                external_receipt_path=external_receipt_path,
            )
            return receipt
        receipt = _build_receipt(
            status="rolled_back",
            transaction_id=transaction_id,
            plan_path=resolved_plan_path,
            plan=plan,
            approval_path=resolved_approval_path,
            approval=approval,
            consumption_path=consumption_path,
            consumption=consumption,
            operations=operations,
            post_snapshot=restored_snapshot,
            failure_stage=None,
            error_type=None,
            completed_at=current_time,
        )
        _persist_receipts(
            receipt=receipt,
            internal_receipt_path=internal_receipt_path,
            external_receipt_path=external_receipt_path,
        )
        return receipt
    finally:
        for staged in staged_files:
            try:
                staged.unlink()
            except FileNotFoundError:
                pass
        transaction_lock.release()


def _snapshot_matches_rollback_receipt_operations(
    *,
    receipt: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> bool:
    scenes = _scene_map(snapshot)
    receipt_status = str(receipt["status"])
    raw_operations = receipt.get("operations")
    assert isinstance(raw_operations, list)
    for index, raw_operation in enumerate(raw_operations):
        operation = _mapping(
            raw_operation,
            name=f"receipt.operations[{index}]",
        )
        scene = scenes.get(_operation_key(operation))
        if scene is None:
            return False
        expected_model = (
            operation["restored_model_name"]
            if receipt_status == "rolled_back"
            else operation["expected_current_model_name"]
        )
        expected_fingerprint = (
            operation["restored_file_fingerprint"]
            if receipt_status == "rolled_back"
            else operation["expected_current_file_fingerprint"]
        )
        manifest = _mapping(
            scene.get("manifest_source"),
            name=(f"rollback receipt scene {operation['scene_name']} manifest"),
        )
        if (
            scene.get("model_name") != expected_model
            or manifest.get("default_model_name") != expected_model
            or manifest.get("fingerprint") != expected_fingerprint
        ):
            return False
    return True


def verify_write_model_configuration_operator_rollback_receipt(
    receipt: Mapping[str, Any],
    *,
    current_routing_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a rollback receipt against current runtime routing."""

    validate_write_model_configuration_operator_rollback_receipt(receipt)
    current_fingerprint = _snapshot_fingerprint(
        current_routing_snapshot,
        name="current routing snapshot",
    )
    receipt_status = str(receipt["status"])
    expected_fingerprint: object
    if receipt_status == "rolled_back":
        expected_fingerprint = receipt["expected_restored_routing_snapshot_fingerprint"]
    elif receipt_status == "rolled_forward":
        expected_fingerprint = receipt["source_applied_routing_snapshot_fingerprint"]
    else:
        expected_fingerprint = None

    if receipt_status == "recovery_failed":
        verification_status = "manual_recovery_required"
        full_snapshot_match = False
        operation_routes_match = False
        reason_codes = ["receipt_records_unrecovered_configuration_state"]
    else:
        assert isinstance(expected_fingerprint, str)
        full_snapshot_match = hmac.compare_digest(
            expected_fingerprint,
            current_fingerprint,
        )
        operation_routes_match = _snapshot_matches_rollback_receipt_operations(
            receipt=receipt,
            snapshot=current_routing_snapshot,
        )
        if full_snapshot_match and operation_routes_match:
            verification_status = "current"
            reason_codes = [(f"current_runtime_snapshot_matches_{receipt_status}_receipt")]
        else:
            verification_status = "routing_changed"
            reason_codes = []
            if not full_snapshot_match:
                reason_codes.append("full_runtime_routing_snapshot_changed")
            if not operation_routes_match:
                reason_codes.append("rollback_scene_manifest_routing_changed")

    matches = verification_status == "current" and full_snapshot_match and operation_routes_match
    payload = {
        "schema_version": _VERIFICATION_SCHEMA_VERSION,
        "status": verification_status,
        "action": "stop",
        "receipt_status": receipt_status,
        "expected_configuration_state": (_EXPECTED_CONFIGURATION_STATES[receipt_status]),
        "expected_routing_snapshot_fingerprint": expected_fingerprint,
        "current_routing_snapshot_fingerprint": current_fingerprint,
        "full_snapshot_match": full_snapshot_match,
        "changed_operation_routes_match": operation_routes_match,
        "current_routing_matches_receipt": matches,
        "eligible_for_new_operator_rollback_cycle": (matches and receipt_status == "rolled_forward"),
        "reason_codes": reason_codes,
        "configuration_verification_performed": True,
        "configuration_rollback_performed": False,
        "approval_consumed": True,
        "approval_consumed_by_verification": False,
        "model_execution_performed": False,
    }
    validate_write_model_configuration_operator_rollback_verification(payload)
    return payload


def _assert_rollback_receipt_source_file(
    source: Mapping[str, str],
    *,
    name: str,
) -> Path:
    path = _absolute_path(source.get("path"), name=f"{name}.path")
    try:
        current_fingerprint = _file_fingerprint(path)
    except (FileNotFoundError, OSError) as exc:
        raise WriteModelConfigurationRollbackBlockedError(f"{name} is unavailable") from exc
    if not hmac.compare_digest(
        source["file_fingerprint"],
        current_fingerprint,
    ):
        raise WriteModelConfigurationRollbackBlockedError(f"{name} file changed")
    return path


def _assert_rollback_receipt_evidence_chain(
    receipt: Mapping[str, Any],
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    plan_source = _validate_source(
        receipt.get("source_rollback_plan"),
        name="source_rollback_plan",
    )
    plan_path = _assert_rollback_receipt_source_file(
        plan_source,
        name="source rollback plan",
    )
    _resolved_plan_path, source_plan = load_write_model_configuration_operator_rollback_plan(plan_path)
    if not hmac.compare_digest(
        plan_source["content_fingerprint"],
        str(source_plan["plan_fingerprint"]),
    ):
        raise WriteModelConfigurationRollbackBlockedError("source rollback plan content changed")

    approval_source = _validate_source(
        receipt.get("source_rollback_approval"),
        name="source_rollback_approval",
    )
    approval_path = _assert_rollback_receipt_source_file(
        approval_source,
        name="source rollback approval",
    )
    _resolved_approval_path, source_approval = load_write_model_configuration_operator_rollback_approval(approval_path)
    if not hmac.compare_digest(
        approval_source["content_fingerprint"],
        str(source_approval["approval_fingerprint"]),
    ):
        raise WriteModelConfigurationRollbackBlockedError("source rollback approval content changed")
    approval_plan_source = _validate_source(
        source_approval.get("rollback_plan_source"),
        name="rollback approval plan source",
    )
    if approval_plan_source != plan_source:
        raise WriteModelConfigurationRollbackBlockedError("source rollback approval is not bound to the source plan")

    application_source = _validate_source(
        receipt.get("source_application_receipt"),
        name="source_application_receipt",
    )
    application_receipt_path = _assert_rollback_receipt_source_file(
        application_source,
        name="source application receipt",
    )
    (
        _resolved_application_receipt_path,
        source_application_receipt,
    ) = load_write_model_configuration_application_receipt(application_receipt_path)
    if not hmac.compare_digest(
        application_source["content_fingerprint"],
        str(source_application_receipt["receipt_fingerprint"]),
    ):
        raise WriteModelConfigurationRollbackBlockedError("source application receipt content changed")
    plan_application_source = _validate_source(
        source_plan.get("source_application_receipt"),
        name="source plan application receipt",
    )
    if plan_application_source != application_source:
        raise WriteModelConfigurationRollbackBlockedError(
            "source rollback plan is not bound to the source application receipt"
        )

    consumption_source = _validate_source(
        receipt.get("approval_consumption"),
        name="approval_consumption",
    )
    consumption_path = _assert_rollback_receipt_source_file(
        consumption_source,
        name="rollback approval consumption",
    )
    source_consumption = _load_consumption(consumption_path)
    if not hmac.compare_digest(
        consumption_source["content_fingerprint"],
        str(source_consumption["consumption_fingerprint"]),
    ):
        raise WriteModelConfigurationRollbackBlockedError("rollback approval consumption content changed")

    approval_fingerprint = str(source_approval["approval_fingerprint"])
    plan_fingerprint = str(source_plan["plan_fingerprint"])
    expected_transaction_id = _transaction_id(
        approval_fingerprint=approval_fingerprint,
        plan_fingerprint=plan_fingerprint,
    )
    expected_consumption = {
        "rollback_approval_fingerprint": approval_fingerprint,
        "rollback_plan_fingerprint": plan_fingerprint,
        "application_receipt_fingerprint": application_source["content_fingerprint"],
        "transaction_id": expected_transaction_id,
    }
    if any(
        source_consumption.get(field_name) != expected_value
        for field_name, expected_value in expected_consumption.items()
    ):
        raise WriteModelConfigurationRollbackBlockedError("rollback approval consumption identity is inconsistent")
    if receipt.get("transaction_id") != expected_transaction_id:
        raise WriteModelConfigurationRollbackBlockedError(
            "operator rollback receipt transaction identity is inconsistent"
        )
    if receipt.get("ticker") != source_plan.get("ticker"):
        raise WriteModelConfigurationRollbackBlockedError("operator rollback receipt ticker is inconsistent")
    if receipt.get("source_applied_routing_snapshot_fingerprint") != source_plan.get(
        "expected_current_routing_snapshot_fingerprint"
    ) or receipt.get("expected_restored_routing_snapshot_fingerprint") != source_plan.get(
        "expected_restored_routing_snapshot_fingerprint"
    ):
        raise WriteModelConfigurationRollbackBlockedError(
            "operator rollback receipt routing identities are inconsistent"
        )
    if receipt.get("operations") != _receipt_operations(source_plan["operations"]):
        raise WriteModelConfigurationRollbackBlockedError("operator rollback receipt operations are inconsistent")
    return application_receipt_path, source_plan, source_consumption


def build_write_model_configuration_operator_rollback_retry_plan(
    *,
    rollback_receipt_path: str | Path,
    current_routing_snapshot: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Build a new exact rollback plan after a rolled-forward result."""

    current_time = _normalize_now(now)
    _resolved_receipt_path, receipt = load_write_model_configuration_operator_rollback_receipt(rollback_receipt_path)
    verification = verify_write_model_configuration_operator_rollback_receipt(
        receipt,
        current_routing_snapshot=current_routing_snapshot,
    )
    if (
        receipt.get("status") != "rolled_forward"
        or verification.get("status") != "current"
        or verification.get("eligible_for_new_operator_rollback_cycle") is not True
    ):
        raise WriteModelConfigurationRollbackBlockedError("rollback receipt is not eligible for a new rollback cycle")
    if current_time <= _parse_utc(
        receipt.get("completed_at"),
        name="completed_at",
    ):
        raise WriteModelConfigurationRollbackBlockedError("retry plan must be created after the rolled-forward receipt")

    try:
        application_receipt_path, source_plan, _source_consumption = _assert_rollback_receipt_evidence_chain(receipt)
        retry_plan = build_write_model_configuration_operator_rollback_plan(
            application_receipt_path=application_receipt_path,
            current_routing_snapshot=current_routing_snapshot,
            now=current_time,
        )
    except WriteModelConfigurationRollbackBlockedError:
        raise
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise WriteModelConfigurationRollbackBlockedError("rolled-forward rollback evidence chain is invalid") from exc

    retry_application_source = _validate_source(
        retry_plan.get("source_application_receipt"),
        name="retry plan application receipt",
    )
    receipt_application_source = _validate_source(
        receipt.get("source_application_receipt"),
        name="receipt application receipt",
    )
    if retry_application_source != receipt_application_source:
        raise WriteModelConfigurationRollbackBlockedError("retry plan application receipt identity changed")
    if retry_plan.get("operations") != source_plan.get("operations"):
        raise WriteModelConfigurationRollbackBlockedError("retry plan operations changed")
    if hmac.compare_digest(
        str(retry_plan["plan_fingerprint"]),
        str(source_plan["plan_fingerprint"]),
    ):
        raise WriteModelConfigurationRollbackBlockedError("retry plan must have a new plan fingerprint")
    return retry_plan


def _manual_recovery_target_path(
    value: object,
    *,
    name: str,
) -> Path:
    text = _required_text(
        value,
        name=name,
        maximum_length=32_768,
    )
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return Path(os.path.abspath(path))


def _intent_operations_match_plan(
    *,
    intent_operations: Sequence[Mapping[str, Any]],
    plan_operations: Sequence[Mapping[str, Any]],
) -> bool:
    if len(intent_operations) != len(plan_operations):
        return False
    for intent_operation, plan_operation in zip(
        intent_operations,
        plan_operations,
        strict=True,
    ):
        expected = {
            "role": plan_operation.get("role"),
            "scene_name": plan_operation.get("scene_name"),
            "target_manifest_path": plan_operation.get("target_manifest_path"),
            "json_pointer": plan_operation.get("json_pointer"),
            "expected_current_model_name": plan_operation.get("expected_current_model_name"),
            "restore_model_name": plan_operation.get("restore_model_name"),
            "applied_file_fingerprint": plan_operation.get("expected_current_file_fingerprint"),
            "restore_file_fingerprint": plan_operation.get("restore_file_fingerprint"),
            "restore_file_content_base64": plan_operation.get("restore_file_content_base64"),
        }
        if any(intent_operation.get(field_name) != expected_value for field_name, expected_value in expected.items()):
            return False
    return True


def _load_manual_recovery_intent_evidence(
    *,
    receipt: Mapping[str, Any],
    plan: Mapping[str, Any],
    consumption: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]] | None]:
    transaction_dir = _absolute_path(
        consumption.get("transaction_dir"),
        name="approval consumption transaction_dir",
    )
    intent_path = transaction_dir / "intent.json"
    if intent_path.is_symlink():
        return (
            {
                "path": str(intent_path),
                "status": "invalid",
                "file_fingerprint": None,
                "content_fingerprint": None,
                "issue_codes": ["write_ahead_intent_invalid"],
            },
            None,
        )
    if not intent_path.is_file():
        return (
            {
                "path": str(intent_path),
                "status": "missing",
                "file_fingerprint": None,
                "content_fingerprint": None,
                "issue_codes": ["write_ahead_intent_missing"],
            },
            None,
        )
    file_fingerprint: str | None = None
    try:
        file_fingerprint = _file_fingerprint(intent_path)
        _resolved_intent_path, intent = _load_json_object(
            intent_path,
            name="operator rollback intent",
        )
        validate_write_model_configuration_operator_rollback_intent(intent)
        expected_identity = {
            "transaction_id": receipt["transaction_id"],
            "ticker": receipt["ticker"],
            "rollback_plan_fingerprint": plan["plan_fingerprint"],
            "rollback_approval_fingerprint": consumption["rollback_approval_fingerprint"],
            "application_receipt_fingerprint": consumption["application_receipt_fingerprint"],
            "source_applied_routing_snapshot_fingerprint": receipt["source_applied_routing_snapshot_fingerprint"],
            "expected_restored_routing_snapshot_fingerprint": receipt["expected_restored_routing_snapshot_fingerprint"],
            "intent_fingerprint": consumption["intent_fingerprint"],
        }
        if any(intent.get(field_name) != expected_value for field_name, expected_value in expected_identity.items()):
            raise ValueError("operator rollback intent identity mismatch")
        raw_intent_operations = intent.get("operations")
        raw_plan_operations = plan.get("operations")
        if not isinstance(raw_intent_operations, list) or not isinstance(
            raw_plan_operations,
            list,
        ):
            raise ValueError("operator rollback intent operations are unavailable")
        intent_operations = [
            _validate_intent_operation(
                operation,
                name=f"intent.operations[{index}]",
            )
            for index, operation in enumerate(raw_intent_operations)
        ]
        plan_operations = [
            _mapping(
                operation,
                name=f"plan.operations[{index}]",
            )
            for index, operation in enumerate(raw_plan_operations)
        ]
        if not _intent_operations_match_plan(
            intent_operations=intent_operations,
            plan_operations=plan_operations,
        ):
            raise ValueError("operator rollback intent operations do not match plan")
    except (OSError, TypeError, ValueError):
        return (
            {
                "path": str(intent_path),
                "status": "invalid",
                "file_fingerprint": file_fingerprint,
                "content_fingerprint": None,
                "issue_codes": ["write_ahead_intent_invalid"],
            },
            None,
        )
    return (
        {
            "path": str(intent_path),
            "status": "valid",
            "file_fingerprint": file_fingerprint,
            "content_fingerprint": intent["intent_fingerprint"],
            "issue_codes": [],
        },
        intent_operations,
    )


def _observe_manual_recovery_target(
    *,
    target: Path,
    applied_fingerprint: str,
    preapplication_fingerprint: str,
) -> tuple[str, str | None]:
    if target.is_symlink():
        return "unsafe_symlink", None
    if not target.exists():
        return "missing", None
    if not target.is_file():
        return "unreadable", None
    try:
        current_fingerprint = _file_fingerprint(target)
    except OSError:
        return "unreadable", None
    if hmac.compare_digest(
        current_fingerprint,
        applied_fingerprint,
    ):
        return "applied", current_fingerprint
    if hmac.compare_digest(
        current_fingerprint,
        preapplication_fingerprint,
    ):
        return "preapplication", current_fingerprint
    return "unexpected", current_fingerprint


def _manual_recovery_observed_state(
    operations: Sequence[Mapping[str, Any]],
) -> str:
    states = [str(operation["observed_state"]) for operation in operations]
    if all(state == "applied" for state in states):
        return "exact_applied"
    if all(state == "preapplication" for state in states):
        return "exact_preapplication"
    if all(state in {"applied", "preapplication"} for state in states):
        return "mixed_known"
    return "indeterminate"


def build_write_model_configuration_manual_recovery_evidence(
    *,
    rollback_receipt_path: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    now: datetime,
    clearance_revocation_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build read-only evidence for a recovery-failed rollback."""

    current_time = _normalize_now(now)
    resolved_config_root = Path(config_root).expanduser().resolve()
    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    lineage: dict[str, Any] | None = None
    if clearance_revocation_lineage is not None:
        lineage = _validate_manual_recovery_clearance_revocation_lineage(clearance_revocation_lineage)
        if lineage["ticker"] != normalized_ticker:
            raise WriteModelConfigurationRollbackBlockedError(
                "manual recovery clearance revocation lineage ticker does not match the command"
            )
        try:
            assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current(lineage)
        except (
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise WriteModelConfigurationRollbackBlockedError(
                "manual recovery clearance revocation lineage is not current"
            ) from exc
    resolved_receipt_path, receipt = load_write_model_configuration_operator_rollback_receipt(rollback_receipt_path)
    if receipt.get("status") != "recovery_failed":
        raise WriteModelConfigurationRollbackBlockedError("manual recovery evidence requires a recovery_failed receipt")
    if receipt.get("ticker") != normalized_ticker:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery receipt ticker does not match the command")
    if current_time <= _parse_utc(
        receipt.get("completed_at"),
        name="completed_at",
    ):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery evidence must be created after the receipt")
    try:
        (
            _application_receipt_path,
            source_plan,
            source_consumption,
        ) = _assert_rollback_receipt_evidence_chain(receipt)
    except WriteModelConfigurationRollbackBlockedError:
        raise
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery source evidence chain is invalid") from exc

    intent_evidence, intent_operations = _load_manual_recovery_intent_evidence(
        receipt=receipt,
        plan=source_plan,
        consumption=source_consumption,
    )
    raw_plan_operations = source_plan.get("operations")
    if not isinstance(raw_plan_operations, list):
        raise WriteModelConfigurationRollbackBlockedError("manual recovery source plan has no operations")
    intent_by_key = (
        {} if intent_operations is None else {_operation_key(operation): operation for operation in intent_operations}
    )
    manifest_root = resolved_config_root / "prompts" / "manifests"
    operations: list[dict[str, Any]] = []
    observations: dict[Path, tuple[str, str | None]] = {}
    seen_paths: set[Path] = set()
    for index, raw_plan_operation in enumerate(raw_plan_operations):
        plan_operation = _mapping(
            raw_plan_operation,
            name=f"plan.operations[{index}]",
        )
        scene_name = _required_text(
            plan_operation.get("scene_name"),
            name=f"plan.operations[{index}].scene_name",
            maximum_length=128,
        )
        target = _manual_recovery_target_path(
            plan_operation.get("target_manifest_path"),
            name=f"plan.operations[{index}].target_manifest_path",
        )
        if target.parent != manifest_root or target.name != f"{scene_name}.json" or target in seen_paths:
            raise WriteModelConfigurationRollbackBlockedError(f"manual recovery target for {scene_name!r} is unsafe")
        seen_paths.add(target)
        applied_fingerprint = _validated_fingerprint(
            plan_operation.get("expected_current_file_fingerprint"),
            name=(f"plan.operations[{index}].expected_current_file_fingerprint"),
        )
        preapplication_fingerprint = _validated_fingerprint(
            plan_operation.get("restore_file_fingerprint"),
            name=(f"plan.operations[{index}].restore_file_fingerprint"),
        )
        observed_state, observed_fingerprint = _observe_manual_recovery_target(
            target=target,
            applied_fingerprint=applied_fingerprint,
            preapplication_fingerprint=(preapplication_fingerprint),
        )
        observations[target] = (
            observed_state,
            observed_fingerprint,
        )
        intent_operation = intent_by_key.get(_operation_key(plan_operation))
        applied_content = None if intent_operation is None else intent_operation["applied_file_content_base64"]
        operations.append(
            {
                "role": plan_operation["role"],
                "scene_name": scene_name,
                "target_manifest_path": str(target),
                "json_pointer": _MODEL_POINTER,
                "observed_state": observed_state,
                "observed_file_fingerprint": observed_fingerprint,
                "expected_applied_model_name": plan_operation["expected_current_model_name"],
                "expected_applied_file_fingerprint": (applied_fingerprint),
                "applied_candidate_available": (applied_content is not None),
                "applied_file_content_base64": applied_content,
                "expected_preapplication_model_name": plan_operation["restore_model_name"],
                "expected_preapplication_file_fingerprint": (preapplication_fingerprint),
                "preapplication_candidate_available": True,
                "preapplication_file_content_base64": plan_operation["restore_file_content_base64"],
            }
        )

    for operation in operations:
        target = Path(str(operation["target_manifest_path"]))
        current_observation = _observe_manual_recovery_target(
            target=target,
            applied_fingerprint=str(operation["expected_applied_file_fingerprint"]),
            preapplication_fingerprint=str(operation["expected_preapplication_file_fingerprint"]),
        )
        if current_observation != observations[target]:
            raise WriteModelConfigurationRollbackBlockedError(
                "configuration changed during manual recovery evidence export"
            )

    try:
        (
            _refreshed_application_receipt_path,
            refreshed_plan,
            refreshed_consumption,
        ) = _assert_rollback_receipt_evidence_chain(receipt)
    except WriteModelConfigurationRollbackBlockedError:
        raise
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise WriteModelConfigurationRollbackBlockedError(
            "manual recovery source evidence changed during export"
        ) from exc
    if refreshed_plan != source_plan or refreshed_consumption != source_consumption:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery source evidence changed during export")
    refreshed_intent_evidence, refreshed_intent_operations = _load_manual_recovery_intent_evidence(
        receipt=receipt,
        plan=refreshed_plan,
        consumption=refreshed_consumption,
    )
    if refreshed_intent_evidence != intent_evidence or refreshed_intent_operations != intent_operations:
        raise WriteModelConfigurationRollbackBlockedError("manual recovery intent changed during export")
    if lineage is not None:
        try:
            assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current(lineage)
        except (
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise WriteModelConfigurationRollbackBlockedError(
                "manual recovery clearance revocation lineage changed during export"
            ) from exc

    completeness = "complete" if intent_evidence["status"] == "valid" else "partial"
    observed_configuration_state = _manual_recovery_observed_state(operations)
    reason_codes = [
        "rollback_receipt_records_recovery_failed",
        (
            "exact_applied_and_preapplication_candidates_available"
            if completeness == "complete"
            else "applied_candidate_unavailable"
        ),
        (f"current_configuration_state_{observed_configuration_state}"),
    ]
    payload: dict[str, Any] = {
        "schema_version": (
            _MANUAL_RECOVERY_EVIDENCE_SCHEMA_VERSION_V2
            if lineage is not None
            else _MANUAL_RECOVERY_EVIDENCE_SCHEMA_VERSION_V1
        ),
        "evidence_type": _MANUAL_RECOVERY_EVIDENCE_TYPE,
        "status": _MANUAL_RECOVERY_STATUS,
        "action": _MANUAL_RECOVERY_ACTION,
        "ticker": receipt["ticker"],
        "transaction_id": receipt["transaction_id"],
        "source_rollback_receipt": _source_reference(
            path=resolved_receipt_path,
            content_fingerprint=str(receipt["receipt_fingerprint"]),
        ),
        "source_rollback_plan": receipt["source_rollback_plan"],
        "source_rollback_approval": receipt["source_rollback_approval"],
        "source_application_receipt": receipt["source_application_receipt"],
        "approval_consumption": receipt["approval_consumption"],
        "source_applied_routing_snapshot_fingerprint": receipt["source_applied_routing_snapshot_fingerprint"],
        "expected_preapplication_routing_snapshot_fingerprint": (
            receipt["expected_restored_routing_snapshot_fingerprint"]
        ),
        "write_ahead_intent": intent_evidence,
        "evidence_completeness": completeness,
        "observed_configuration_state": (observed_configuration_state),
        "operations": operations,
        "reason_codes": reason_codes,
        "created_at": _format_utc(current_time),
        "safety_boundaries": list(
            _MANUAL_RECOVERY_V2_SAFETY_BOUNDARIES if lineage is not None else _MANUAL_RECOVERY_SAFETY_BOUNDARIES
        ),
        "configuration_mutation_performed": False,
        "approval_consumed": True,
        "approval_consumed_by_evidence_export": False,
        "model_execution_performed": False,
    }
    if lineage is not None:
        payload["clearance_revocation_lineage"] = dict(lineage)
    payload["evidence_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_manual_recovery_evidence(payload)
    return payload


def _validate_manual_recovery_intent_evidence(
    value: object,
) -> dict[str, Any]:
    intent = _mapping(
        value,
        name="manual recovery write-ahead intent",
    )
    _exact_fields(
        intent,
        expected=_MANUAL_RECOVERY_INTENT_FIELDS,
        name="manual recovery write-ahead intent",
    )
    _absolute_path(
        intent.get("path"),
        name="write_ahead_intent.path",
    )
    status = intent.get("status")
    if status not in _MANUAL_RECOVERY_INTENT_STATUSES:
        raise ValueError("manual recovery intent status is invalid")
    file_fingerprint = intent.get("file_fingerprint")
    content_fingerprint = intent.get("content_fingerprint")
    if file_fingerprint is not None:
        _validated_fingerprint(
            file_fingerprint,
            name="write_ahead_intent.file_fingerprint",
        )
    if content_fingerprint is not None:
        _validated_fingerprint(
            content_fingerprint,
            name="write_ahead_intent.content_fingerprint",
        )
    issue_codes = intent.get("issue_codes")
    if not isinstance(issue_codes, list):
        raise ValueError("manual recovery intent issue_codes must be a list")
    normalized_issues = [
        _required_text(
            issue,
            name=f"write_ahead_intent.issue_codes[{index}]",
            maximum_length=128,
        )
        for index, issue in enumerate(issue_codes)
    ]
    expected_issues = {
        "valid": [],
        "missing": ["write_ahead_intent_missing"],
        "invalid": ["write_ahead_intent_invalid"],
    }
    if normalized_issues != expected_issues[str(status)]:
        raise ValueError("manual recovery intent issue_codes are inconsistent")
    if status == "valid":
        if file_fingerprint is None or content_fingerprint is None:
            raise ValueError("valid manual recovery intent lacks fingerprints")
    elif content_fingerprint is not None:
        raise ValueError("unavailable manual recovery intent has content identity")
    if status == "missing" and file_fingerprint is not None:
        raise ValueError("missing manual recovery intent has a file identity")
    return dict(intent)


def _validate_manual_recovery_operation(
    value: object,
    *,
    name: str,
    applied_candidate_expected: bool,
) -> dict[str, Any]:
    operation = _mapping(value, name=name)
    _exact_fields(
        operation,
        expected=_MANUAL_RECOVERY_OPERATION_FIELDS,
        name=name,
    )
    normalized: dict[str, Any] = {
        "role": _required_text(
            operation.get("role"),
            name=f"{name}.role",
            maximum_length=32,
        ),
        "scene_name": _required_text(
            operation.get("scene_name"),
            name=f"{name}.scene_name",
            maximum_length=128,
        ),
        "target_manifest_path": str(
            _manual_recovery_target_path(
                operation.get("target_manifest_path"),
                name=f"{name}.target_manifest_path",
            )
        ),
        "json_pointer": operation.get("json_pointer"),
        "observed_state": operation.get("observed_state"),
        "observed_file_fingerprint": operation.get("observed_file_fingerprint"),
        "expected_applied_model_name": _required_text(
            operation.get("expected_applied_model_name"),
            name=f"{name}.expected_applied_model_name",
            maximum_length=256,
        ),
        "expected_applied_file_fingerprint": (
            _validated_fingerprint(
                operation.get("expected_applied_file_fingerprint"),
                name=(f"{name}.expected_applied_file_fingerprint"),
            )
        ),
        "applied_candidate_available": operation.get("applied_candidate_available"),
        "applied_file_content_base64": operation.get("applied_file_content_base64"),
        "expected_preapplication_model_name": _required_text(
            operation.get("expected_preapplication_model_name"),
            name=f"{name}.expected_preapplication_model_name",
            maximum_length=256,
        ),
        "expected_preapplication_file_fingerprint": (
            _validated_fingerprint(
                operation.get("expected_preapplication_file_fingerprint"),
                name=(f"{name}.expected_preapplication_file_fingerprint"),
            )
        ),
        "preapplication_candidate_available": operation.get("preapplication_candidate_available"),
        "preapplication_file_content_base64": operation.get("preapplication_file_content_base64"),
    }
    if normalized["role"] not in {"primary", "audit"}:
        raise ValueError(f"{name}.role is invalid")
    if normalized["json_pointer"] != _MODEL_POINTER:
        raise ValueError(f"{name}.json_pointer is invalid")
    observed_state = normalized["observed_state"]
    if observed_state not in _MANUAL_RECOVERY_TARGET_STATES:
        raise ValueError(f"{name}.observed_state is invalid")
    observed_fingerprint = normalized["observed_file_fingerprint"]
    if observed_fingerprint is not None:
        observed_fingerprint = _validated_fingerprint(
            observed_fingerprint,
            name=f"{name}.observed_file_fingerprint",
        )
        normalized["observed_file_fingerprint"] = observed_fingerprint
    if observed_state in {
        "missing",
        "unsafe_symlink",
        "unreadable",
    }:
        if observed_fingerprint is not None:
            raise ValueError(f"{name} unavailable target has a fingerprint")
    elif observed_fingerprint is None:
        raise ValueError(f"{name} observed target lacks a fingerprint")
    if observed_state == "applied" and not hmac.compare_digest(
        str(observed_fingerprint),
        normalized["expected_applied_file_fingerprint"],
    ):
        raise ValueError(f"{name} applied observation is inconsistent")
    if observed_state == "preapplication" and not hmac.compare_digest(
        str(observed_fingerprint),
        normalized["expected_preapplication_file_fingerprint"],
    ):
        raise ValueError(f"{name} preapplication observation is inconsistent")
    if observed_state == "unexpected" and (
        hmac.compare_digest(
            str(observed_fingerprint),
            normalized["expected_applied_file_fingerprint"],
        )
        or hmac.compare_digest(
            str(observed_fingerprint),
            normalized["expected_preapplication_file_fingerprint"],
        )
    ):
        raise ValueError(f"{name} unexpected observation is inconsistent")

    applied_available = normalized["applied_candidate_available"]
    if not isinstance(applied_available, bool) or applied_available is not applied_candidate_expected:
        raise ValueError(f"{name} applied candidate availability is invalid")
    applied_content = normalized["applied_file_content_base64"]
    if applied_available:
        applied_bytes = _decode_base64(
            applied_content,
            name=f"{name}.applied_file_content_base64",
        )
        if not hmac.compare_digest(
            _bytes_fingerprint(applied_bytes),
            normalized["expected_applied_file_fingerprint"],
        ):
            raise ValueError(f"{name} applied candidate fingerprint mismatch")
    elif applied_content is not None:
        raise ValueError(f"{name} unavailable applied candidate contains bytes")

    if normalized["preapplication_candidate_available"] is not True:
        raise ValueError(f"{name} preapplication candidate must be available")
    preapplication_bytes = _decode_base64(
        normalized["preapplication_file_content_base64"],
        name=f"{name}.preapplication_file_content_base64",
    )
    if not hmac.compare_digest(
        _bytes_fingerprint(preapplication_bytes),
        normalized["expected_preapplication_file_fingerprint"],
    ):
        raise ValueError(f"{name} preapplication candidate fingerprint mismatch")
    return normalized


def validate_write_model_configuration_manual_recovery_evidence(
    payload: Mapping[str, Any],
) -> None:
    """Validate one immutable manual recovery evidence bundle."""

    evidence = _mapping(payload, name="manual recovery evidence")
    schema_version = evidence.get("schema_version")
    if schema_version == _MANUAL_RECOVERY_EVIDENCE_SCHEMA_VERSION_V1:
        expected_fields = _MANUAL_RECOVERY_EVIDENCE_FIELDS_V1
    elif schema_version == _MANUAL_RECOVERY_EVIDENCE_SCHEMA_VERSION_V2:
        expected_fields = _MANUAL_RECOVERY_EVIDENCE_FIELDS_V2
    else:
        raise ValueError("manual recovery evidence schema_version is invalid")
    _exact_fields(
        evidence,
        expected=expected_fields,
        name="manual recovery evidence",
    )
    expected_constants = {
        "evidence_type": _MANUAL_RECOVERY_EVIDENCE_TYPE,
        "status": _MANUAL_RECOVERY_STATUS,
        "action": _MANUAL_RECOVERY_ACTION,
    }
    for field_name, expected_value in expected_constants.items():
        if evidence.get(field_name) != expected_value:
            raise ValueError(f"manual recovery evidence {field_name} is invalid")
    ticker = _required_text(
        evidence.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    _required_text(
        evidence.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    if schema_version == _MANUAL_RECOVERY_EVIDENCE_SCHEMA_VERSION_V2:
        lineage = _validate_manual_recovery_clearance_revocation_lineage(evidence.get("clearance_revocation_lineage"))
        if lineage["ticker"] != ticker:
            raise ValueError("manual recovery evidence clearance revocation lineage ticker differs")
    for field_name in (
        "source_rollback_receipt",
        "source_rollback_plan",
        "source_rollback_approval",
        "source_application_receipt",
        "approval_consumption",
    ):
        _validate_source(
            evidence.get(field_name),
            name=field_name,
        )
    _validated_fingerprint(
        evidence.get("source_applied_routing_snapshot_fingerprint"),
        name="source_applied_routing_snapshot_fingerprint",
    )
    _validated_fingerprint(
        evidence.get("expected_preapplication_routing_snapshot_fingerprint"),
        name=("expected_preapplication_routing_snapshot_fingerprint"),
    )
    intent = _validate_manual_recovery_intent_evidence(evidence.get("write_ahead_intent"))
    completeness = evidence.get("evidence_completeness")
    if completeness not in _MANUAL_RECOVERY_COMPLETENESS:
        raise ValueError("manual recovery evidence completeness is invalid")
    if completeness != ("complete" if intent["status"] == "valid" else "partial"):
        raise ValueError("manual recovery evidence completeness is inconsistent")
    observed_configuration_state = evidence.get("observed_configuration_state")
    if observed_configuration_state not in _MANUAL_RECOVERY_OBSERVED_STATES:
        raise ValueError("manual recovery observed state is invalid")
    raw_operations = evidence.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("manual recovery evidence operations must be non-empty")
    applied_candidate_expected = completeness == "complete"
    operations = [
        _validate_manual_recovery_operation(
            operation,
            name=f"operations[{index}]",
            applied_candidate_expected=applied_candidate_expected,
        )
        for index, operation in enumerate(raw_operations)
    ]
    identities = [_operation_key(operation) for operation in operations]
    paths = [operation["target_manifest_path"] for operation in operations]
    if len(identities) != len(set(identities)) or len(paths) != len(set(paths)):
        raise ValueError("manual recovery evidence operations contain duplicates")
    if _manual_recovery_observed_state(operations) != (observed_configuration_state):
        raise ValueError("manual recovery observed state is inconsistent")
    reason_codes = evidence.get("reason_codes")
    if not isinstance(reason_codes, list) or not reason_codes:
        raise ValueError("manual recovery reason_codes must be non-empty")
    normalized_reasons = [
        _required_text(
            reason,
            name=f"reason_codes[{index}]",
            maximum_length=128,
        )
        for index, reason in enumerate(reason_codes)
    ]
    if len(normalized_reasons) != len(set(normalized_reasons)):
        raise ValueError("manual recovery reason_codes contain duplicates")
    expected_reasons = [
        "rollback_receipt_records_recovery_failed",
        (
            "exact_applied_and_preapplication_candidates_available"
            if completeness == "complete"
            else "applied_candidate_unavailable"
        ),
        (f"current_configuration_state_{observed_configuration_state}"),
    ]
    if normalized_reasons != expected_reasons:
        raise ValueError("manual recovery reason_codes are inconsistent")
    _parse_utc(evidence.get("created_at"), name="created_at")
    expected_safety_boundaries = (
        _MANUAL_RECOVERY_V2_SAFETY_BOUNDARIES
        if schema_version == _MANUAL_RECOVERY_EVIDENCE_SCHEMA_VERSION_V2
        else _MANUAL_RECOVERY_SAFETY_BOUNDARIES
    )
    if evidence.get("safety_boundaries") != expected_safety_boundaries:
        raise ValueError("manual recovery safety boundaries are invalid")
    expected_flags = {
        "configuration_mutation_performed": False,
        "approval_consumed": True,
        "approval_consumed_by_evidence_export": False,
        "model_execution_performed": False,
    }
    for field_name, expected_value in expected_flags.items():
        if evidence.get(field_name) is not expected_value:
            raise ValueError(f"manual recovery evidence {field_name} is invalid")
    fingerprint = _validated_fingerprint(
        evidence.get("evidence_fingerprint"),
        name="evidence_fingerprint",
    )
    unsigned = dict(evidence)
    unsigned.pop("evidence_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("manual recovery evidence fingerprint mismatch")


def persist_write_model_configuration_manual_recovery_evidence(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist one immutable manual recovery evidence bundle."""

    validate_write_model_configuration_manual_recovery_evidence(payload)
    return _persist_immutable(payload, path)


def load_write_model_configuration_manual_recovery_evidence(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable manual recovery evidence bundle."""

    target, payload = _load_json_object(
        path,
        name="manual recovery evidence",
    )
    validate_write_model_configuration_manual_recovery_evidence(payload)
    return target, payload


def format_write_model_configuration_manual_recovery_evidence_report(
    payload: Mapping[str, Any],
) -> list[str]:
    """Format a compact manual recovery evidence report."""

    validate_write_model_configuration_manual_recovery_evidence(payload)
    raw_operations = payload["operations"]
    assert isinstance(raw_operations, list)
    state_counts = {
        state: sum(
            1
            for operation in raw_operations
            if isinstance(operation, Mapping) and operation.get("observed_state") == state
        )
        for state in sorted(_MANUAL_RECOVERY_TARGET_STATES)
    }
    nonzero_counts = ", ".join(f"{state}={count}" for state, count in state_counts.items() if count)
    lineage = (
        _validate_manual_recovery_clearance_revocation_lineage(payload["clearance_revocation_lineage"])
        if "clearance_revocation_lineage" in payload
        else None
    )
    return [
        "Write model configuration manual recovery evidence",
        f"  Status        : {payload['status']}",
        f"  Completeness  : {payload['evidence_completeness']}",
        *(
            [f"  Revocation fp : {lineage['manual_recovery_clearance_revocation_fingerprint']}"]
            if lineage is not None
            else []
        ),
        (f"  Current state : {payload['observed_configuration_state']}"),
        f"  Targets       : {nonzero_counts}",
        "  Configuration : unchanged by evidence export",
        "  Approval      : no new approval consumed",
        "  Model calls   : none",
        "  Next action   : independent human review required",
    ]


def validate_write_model_configuration_operator_rollback_verification(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict, read-only rollback verification result."""

    verification = _mapping(
        payload,
        name="operator rollback verification",
    )
    _exact_fields(
        verification,
        expected=_VERIFICATION_FIELDS,
        name="operator rollback verification",
    )
    if verification.get("schema_version") != _VERIFICATION_SCHEMA_VERSION:
        raise ValueError("unsupported operator rollback verification schema")
    status = verification.get("status")
    if status not in _VERIFICATION_STATUSES:
        raise ValueError("operator rollback verification status is invalid")
    if verification.get("action") != "stop":
        raise ValueError("operator rollback verification action is invalid")
    receipt_status = verification.get("receipt_status")
    if receipt_status not in _RECEIPT_STATUSES:
        raise ValueError("operator rollback verification receipt status is invalid")
    if verification.get("expected_configuration_state") != (_EXPECTED_CONFIGURATION_STATES[str(receipt_status)]):
        raise ValueError("operator rollback verification expected state is invalid")
    expected_fingerprint = verification.get("expected_routing_snapshot_fingerprint")
    if expected_fingerprint is not None:
        _validated_fingerprint(
            expected_fingerprint,
            name="expected_routing_snapshot_fingerprint",
        )
    _validated_fingerprint(
        verification.get("current_routing_snapshot_fingerprint"),
        name="current_routing_snapshot_fingerprint",
    )
    for field_name in (
        "full_snapshot_match",
        "changed_operation_routes_match",
        "current_routing_matches_receipt",
        "eligible_for_new_operator_rollback_cycle",
        "configuration_verification_performed",
        "configuration_rollback_performed",
        "approval_consumed",
        "approval_consumed_by_verification",
        "model_execution_performed",
    ):
        if not isinstance(verification.get(field_name), bool):
            raise ValueError(f"operator rollback verification {field_name} must be boolean")
    reason_codes = verification.get("reason_codes")
    if not isinstance(reason_codes, list) or not reason_codes:
        raise ValueError("operator rollback verification reason_codes must be non-empty")
    normalized_reasons = [
        _required_text(
            reason,
            name=f"reason_codes[{index}]",
            maximum_length=128,
        )
        for index, reason in enumerate(reason_codes)
    ]
    if len(normalized_reasons) != len(set(normalized_reasons)):
        raise ValueError("operator rollback verification reason_codes contain duplicates")
    full_match = verification["full_snapshot_match"]
    operation_match = verification["changed_operation_routes_match"]
    matches = verification["current_routing_matches_receipt"]
    expected_matches = bool(full_match and operation_match)
    if status == "current":
        if expected_fingerprint is None or not expected_matches or matches is not True:
            raise ValueError("current operator rollback verification is inconsistent")
    elif matches is not False:
        raise ValueError("non-current operator rollback verification is inconsistent")
    if status == "routing_changed" and (expected_fingerprint is None or expected_matches):
        raise ValueError("routing-changed operator rollback verification is inconsistent")
    if status == "manual_recovery_required" and (
        receipt_status != "recovery_failed"
        or expected_fingerprint is not None
        or full_match is not False
        or operation_match is not False
    ):
        raise ValueError("manual-recovery operator rollback verification is inconsistent")
    eligible = verification["eligible_for_new_operator_rollback_cycle"]
    if eligible != (status == "current" and receipt_status == "rolled_forward"):
        raise ValueError("new operator rollback cycle eligibility is invalid")
    if verification["configuration_verification_performed"] is not True:
        raise ValueError("operator rollback verification evidence is invalid")
    if verification["configuration_rollback_performed"] is not False:
        raise ValueError("read-only verification cannot roll back configuration")
    if verification["approval_consumed"] is not True:
        raise ValueError("operator rollback approval consumption evidence is invalid")
    if verification["approval_consumed_by_verification"] is not False:
        raise ValueError("read-only verification cannot consume rollback approval")
    if verification["model_execution_performed"] is not False:
        raise ValueError("operator rollback verification claims model execution")


def format_write_model_configuration_operator_rollback_verification_report(
    payload: Mapping[str, Any],
) -> list[str]:
    """Format one read-only rollback receipt verification result."""

    validate_write_model_configuration_operator_rollback_verification(payload)
    return [
        "",
        "=" * 60,
        "Write model configuration operator rollback verification",
        f"  Status        : {payload['status']}",
        f"  Receipt       : {payload['receipt_status']}",
        f"  Full snapshot : {payload['full_snapshot_match']}",
        (f"  Changed routes: {payload['changed_operation_routes_match']}"),
        (f"  New cycle     : {payload['eligible_for_new_operator_rollback_cycle']}"),
        "  Configuration : unchanged by verification",
        "  Approval      : not consumed by verification",
        "  Model calls   : none",
        "=" * 60,
    ]


def format_write_model_configuration_operator_rollback_receipt_report(
    payload: Mapping[str, Any],
) -> list[str]:
    """Format a compact operator-facing rollback receipt."""

    validate_write_model_configuration_operator_rollback_receipt(payload)
    failure = payload.get("failure")
    failure_text = "none"
    if isinstance(failure, Mapping):
        failure_text = f"{failure.get('stage')} ({failure.get('error_type')})"
    return [
        "Write model configuration operator rollback",
        f"  Status       : {payload['status']}",
        f"  Action       : {payload['action']}",
        f"  Transaction  : {payload['transaction_id']}",
        "  Approval     : consumed exactly once",
        f"  Recovery     : {payload['applied_state_recovery_exact']}",
        f"  Failure      : {failure_text}",
        "  Model calls  : none",
    ]


__all__ = [
    "WriteModelConfigurationRollbackApplicationBlockedError",
    "WriteModelConfigurationRollbackApplicationBusyError",
    "WriteModelConfigurationRollbackReceiptError",
    "apply_write_model_configuration_operator_rollback",
    "assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current",
    "build_write_model_configuration_manual_recovery_evidence",
    "build_write_model_configuration_operator_rollback_retry_plan",
    "format_write_model_configuration_manual_recovery_evidence_report",
    "format_write_model_configuration_operator_rollback_receipt_report",
    "format_write_model_configuration_operator_rollback_verification_report",
    "load_write_model_configuration_manual_recovery_evidence",
    "load_write_model_configuration_operator_rollback_receipt",
    "persist_write_model_configuration_manual_recovery_evidence",
    "persist_write_model_configuration_operator_rollback_receipt",
    "validate_write_model_configuration_manual_recovery_clearance_revocation_lineage",
    "validate_write_model_configuration_manual_recovery_evidence",
    "validate_write_model_configuration_operator_rollback_intent",
    "validate_write_model_configuration_operator_rollback_receipt",
    "validate_write_model_configuration_operator_rollback_verification",
    "verify_write_model_configuration_operator_rollback_receipt",
]
