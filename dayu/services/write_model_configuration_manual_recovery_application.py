"""Apply one independently approved exact manual routing recovery."""

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
)
from dayu.services.write_model_configuration_manual_recovery import (
    assert_write_model_configuration_manual_recovery_approval_current,
    load_write_model_configuration_manual_recovery_approval,
    load_write_model_configuration_manual_recovery_plan,
)
from dayu.services.write_model_configuration_preapplication import (
    validate_write_scene_model_routing_snapshot,
)
from dayu.services.write_model_configuration_rollback_application import (
    validate_write_model_configuration_manual_recovery_clearance_revocation_lineage,
)


_INTENT_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_intent_v1"
_INTENT_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_intent_v2"
_CONSUMPTION_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_consumption_v1"
_CONSUMPTION_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_consumption_v2"
_RECEIPT_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_receipt_v1"
_RECEIPT_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_receipt_v2"
_RECEIPT_TYPE = "write_scene_model_routing_manual_recovery"
_SCOPE = "single_use_transactional_exact_selected_state_recovery"
_MODEL_POINTER = "/model/default_name"
_SELECTED_STATES = {"applied", "preapplication"}
_RECEIPT_STATUSES = {
    "recovered",
    "starting_state_restored",
    "recovery_failed",
}
_RECEIPT_ACTIONS = {
    "recovered": "exact_selected_configuration_recovered_stop",
    "starting_state_restored": ("recovery_not_completed_starting_state_restored_new_evidence_required"),
    "recovery_failed": "manual_intervention_required",
}
_SOURCE_FIELDS = {
    "path",
    "file_fingerprint",
    "content_fingerprint",
}
_INTENT_OPERATION_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "json_pointer",
    "observed_state",
    "selected_model_name",
    "starting_file_fingerprint",
    "starting_file_content_base64",
    "selected_file_fingerprint",
    "selected_file_content_base64",
}
_INTENT_FIELDS_V1 = {
    "schema_version",
    "transaction_id",
    "ticker",
    "selected_state",
    "manual_recovery_plan_fingerprint",
    "manual_recovery_approval_fingerprint",
    "manual_recovery_evidence_fingerprint",
    "expected_selected_routing_snapshot_fingerprint",
    "created_at",
    "operations",
    "intent_fingerprint",
}
_INTENT_FIELDS_V2 = _INTENT_FIELDS_V1 | {"clearance_revocation_lineage"}
_CONSUMPTION_FIELDS_V1 = {
    "schema_version",
    "manual_recovery_approval_fingerprint",
    "manual_recovery_plan_fingerprint",
    "manual_recovery_evidence_fingerprint",
    "transaction_id",
    "transaction_dir",
    "intent_fingerprint",
    "consumed_at",
    "consumption_fingerprint",
}
_CONSUMPTION_FIELDS_V2 = _CONSUMPTION_FIELDS_V1 | {"clearance_revocation_lineage"}
_RECEIPT_OPERATION_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "json_pointer",
    "observed_state",
    "selected_model_name",
    "starting_file_fingerprint",
    "selected_file_fingerprint",
    "final_state",
    "final_file_fingerprint",
}
_FAILURE_FIELDS = {
    "stage",
    "error_type",
    "recovery_failure_codes",
}
_RECEIPT_FIELDS_V1 = {
    "schema_version",
    "receipt_type",
    "scope",
    "status",
    "action",
    "ticker",
    "transaction_id",
    "selected_state",
    "source_manual_recovery_plan",
    "source_manual_recovery_approval",
    "source_manual_recovery_evidence",
    "write_ahead_intent",
    "expected_selected_routing_snapshot_fingerprint",
    "post_operation_routing_snapshot_fingerprint",
    "approval_consumption",
    "operations",
    "failure",
    "starting_state_recovery_performed",
    "starting_state_recovery_exact",
    "completed_at",
    "safety_boundaries",
    "configuration_recovery_attempted",
    "configuration_recovery_completed",
    "approval_consumed",
    "model_execution_performed",
    "receipt_fingerprint",
}
_RECEIPT_FIELDS_V2 = _RECEIPT_FIELDS_V1 | {"clearance_revocation_lineage"}
_SAFETY_BOUNDARIES = [
    "human_selected_exact_state_only",
    "independent_short_lived_single_use_approval_required",
    "configuration_apply_rollback_and_recovery_share_one_lock",
    "all_targets_verified_before_approval_consumption",
    "write_ahead_intent_contains_exact_starting_and_selected_bytes",
    "approval_consumed_before_first_manifest_replace",
    "each_manifest_replace_is_atomic",
    "fresh_runtime_preflight_runs_only_after_selected_state_restore",
    "failure_restores_exact_observed_starting_bytes",
    "interrupted_consumed_transaction_restores_starting_state",
    "recovery_does_not_modify_run_config_or_model_catalog",
    "recovery_does_not_call_models",
    "recovery_does_not_modify_secrets",
    "recovery_does_not_start_a_write_run",
]
_V2_SAFETY_BOUNDARIES = [
    *_SAFETY_BOUNDARIES,
    "clearance_revocation_lineage_bound_end_to_end",
]

RoutingSnapshotBuilder = Callable[[], Mapping[str, Any]]


class WriteModelConfigurationManualRecoveryApplicationBlockedError(ValueError):
    """Raised when recovery is blocked before approval consumption."""


class WriteModelConfigurationManualRecoveryApplicationBusyError(RuntimeError):
    """Raised when another configuration transaction owns the lock."""


class WriteModelConfigurationManualRecoveryReceiptError(RuntimeError):
    """Raised when an internal result cannot be exported."""


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
        raise ValueError(message)


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
    return normalized


def _absolute_path(value: object, *, name: str) -> Path:
    text = _required_text(value, name=name, maximum_length=32_768)
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return path.resolve()


def _target_path(value: object, *, name: str) -> Path:
    text = _required_text(value, name=name, maximum_length=32_768)
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


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


def _bytes_fingerprint(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


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
            stream.write(_serialize(payload))
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


def _persist_exclusive(
    payload: Mapping[str, Any],
    path: Path,
) -> Path:
    if path.exists():
        raise FileExistsError(f"single-use artifact exists: {path}")
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


def _validate_source(value: object, *, name: str) -> dict[str, str]:
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


def _manifest_payload(
    content: bytes,
    *,
    scene_name: str,
    expected_model: str,
) -> None:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"selected manifest for {scene_name!r} is not UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"selected manifest for {scene_name!r} must be an object")
    model = payload.get("model")
    if not isinstance(model, dict):
        raise ValueError(f"selected manifest for {scene_name!r} has no model object")
    if model.get("default_name") != expected_model:
        raise ValueError(f"selected manifest for {scene_name!r} has wrong model")
    allowed = model.get("allowed_names")
    if not isinstance(allowed, list) or expected_model not in allowed:
        raise ValueError(f"selected manifest for {scene_name!r} disallows its model")


def _assert_target_identity(
    *,
    target: Path,
    config_root: Path,
    scene_name: str,
) -> None:
    manifest_root = config_root / "prompts" / "manifests"
    if target.parent != manifest_root or target.name != f"{scene_name}.json":
        raise WriteModelConfigurationManualRecoveryApplicationBlockedError(
            f"manual recovery target for {scene_name!r} is unsafe"
        )


def _assert_safe_target(
    *,
    target: Path,
    config_root: Path,
    scene_name: str,
) -> None:
    _assert_target_identity(
        target=target,
        config_root=config_root,
        scene_name=scene_name,
    )
    if target.parent.is_symlink():
        raise WriteModelConfigurationManualRecoveryApplicationBlockedError(
            "manual recovery manifest root must not be a symlink"
        )
    if target.is_symlink() or not target.is_file():
        raise WriteModelConfigurationManualRecoveryApplicationBlockedError(
            f"manual recovery target for {scene_name!r} is unavailable"
        )


def _build_operations(
    *,
    plan: Mapping[str, Any],
    config_root: Path,
) -> list[dict[str, str]]:
    raw_operations = plan.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("manual recovery plan operations are empty")
    operations: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    seen_paths: set[Path] = set()
    for index, raw_operation in enumerate(raw_operations):
        source = _mapping(
            raw_operation,
            name=f"plan.operations[{index}]",
        )
        role = _required_text(
            source.get("role"),
            name=f"plan.operations[{index}].role",
            maximum_length=32,
        )
        scene_name = _required_text(
            source.get("scene_name"),
            name=f"plan.operations[{index}].scene_name",
            maximum_length=128,
        )
        target = _target_path(
            source.get("target_manifest_path"),
            name=f"plan.operations[{index}].target_manifest_path",
        )
        _assert_safe_target(
            target=target,
            config_root=config_root,
            scene_name=scene_name,
        )
        key = (role, scene_name)
        if key in seen_keys or target in seen_paths:
            raise ValueError("manual recovery plan operations contain duplicates")
        seen_keys.add(key)
        seen_paths.add(target)
        if source.get("json_pointer") != _MODEL_POINTER:
            raise ValueError(f"manual recovery pointer for {scene_name!r} is invalid")
        starting_bytes = target.read_bytes()
        starting_fingerprint = _bytes_fingerprint(starting_bytes)
        expected_starting = _validated_fingerprint(
            source.get("expected_current_file_fingerprint"),
            name=(f"plan.operations[{index}].expected_current_file_fingerprint"),
        )
        if not hmac.compare_digest(
            starting_fingerprint,
            expected_starting,
        ):
            raise (
                WriteModelConfigurationManualRecoveryApplicationBlockedError(
                    f"manual recovery target for {scene_name!r} changed"
                )
            )
        selected_bytes = _decode_base64(
            source.get("selected_file_content_base64"),
            name=f"selected bytes for {scene_name}",
        )
        selected_fingerprint = _validated_fingerprint(
            source.get("selected_file_fingerprint"),
            name=(f"plan.operations[{index}].selected_file_fingerprint"),
        )
        if not hmac.compare_digest(
            _bytes_fingerprint(selected_bytes),
            selected_fingerprint,
        ):
            raise ValueError(f"selected bytes for {scene_name!r} changed")
        selected_model = _required_text(
            source.get("selected_model_name"),
            name=f"plan.operations[{index}].selected_model_name",
            maximum_length=256,
        )
        _manifest_payload(
            selected_bytes,
            scene_name=scene_name,
            expected_model=selected_model,
        )
        operations.append(
            {
                "role": role,
                "scene_name": scene_name,
                "target_manifest_path": str(target),
                "json_pointer": _MODEL_POINTER,
                "observed_state": str(source["observed_state"]),
                "selected_model_name": selected_model,
                "starting_file_fingerprint": starting_fingerprint,
                "starting_file_content_base64": _encode_base64(starting_bytes),
                "selected_file_fingerprint": selected_fingerprint,
                "selected_file_content_base64": _encode_base64(selected_bytes),
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
    for state_name in ("starting", "selected"):
        content = _decode_base64(
            normalized[f"{state_name}_file_content_base64"],
            name=f"{name}.{state_name}_file_content_base64",
        )
        fingerprint = _validated_fingerprint(
            normalized[f"{state_name}_file_fingerprint"],
            name=f"{name}.{state_name}_file_fingerprint",
        )
        if not hmac.compare_digest(
            _bytes_fingerprint(content),
            fingerprint,
        ):
            raise ValueError(f"{name} {state_name} bytes changed")
    _manifest_payload(
        _decode_base64(
            normalized["selected_file_content_base64"],
            name=f"{name}.selected_file_content_base64",
        ),
        scene_name=normalized["scene_name"],
        expected_model=normalized["selected_model_name"],
    )
    return normalized


def validate_write_model_configuration_manual_recovery_intent(
    payload: Mapping[str, Any],
) -> None:
    """Validate an exact starting/selected write-ahead intent."""

    intent = _mapping(payload, name="manual recovery intent")
    _validate_versioned_clearance_revocation_lineage(
        intent,
        schema_version_v1=_INTENT_SCHEMA_VERSION_V1,
        schema_version_v2=_INTENT_SCHEMA_VERSION_V2,
        fields_v1=_INTENT_FIELDS_V1,
        fields_v2=_INTENT_FIELDS_V2,
        name="manual recovery intent",
    )
    _required_text(
        intent.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    _required_text(intent.get("ticker"), name="ticker", maximum_length=64)
    if intent.get("selected_state") not in _SELECTED_STATES:
        raise ValueError("manual recovery intent selected_state is invalid")
    for field_name in (
        "manual_recovery_plan_fingerprint",
        "manual_recovery_approval_fingerprint",
        "manual_recovery_evidence_fingerprint",
        "expected_selected_routing_snapshot_fingerprint",
    ):
        _validated_fingerprint(
            intent.get(field_name),
            name=field_name,
        )
    _parse_utc(intent.get("created_at"), name="created_at")
    raw_operations = intent.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("manual recovery intent operations are empty")
    operations = [
        _validate_intent_operation(
            operation,
            name=f"operations[{index}]",
        )
        for index, operation in enumerate(raw_operations)
    ]
    keys = {(operation["role"], operation["scene_name"]) for operation in operations}
    paths = {operation["target_manifest_path"] for operation in operations}
    if len(keys) != len(operations) or len(paths) != len(operations):
        raise ValueError("manual recovery intent operations duplicate")
    fingerprint = _validated_fingerprint(
        intent.get("intent_fingerprint"),
        name="intent_fingerprint",
    )
    unsigned = dict(intent)
    unsigned.pop("intent_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("manual recovery intent fingerprint mismatch")


def _build_intent(
    *,
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    operations: Sequence[Mapping[str, str]],
    transaction_id: str,
    now: datetime,
) -> dict[str, Any]:
    lineage = _clearance_revocation_lineage(plan)
    _assert_same_clearance_revocation_lineage(
        lineage,
        _clearance_revocation_lineage(approval),
        message=("manual recovery intent clearance revocation lineage does not match approval"),
    )
    payload: dict[str, Any] = {
        "schema_version": (_INTENT_SCHEMA_VERSION_V2 if lineage is not None else _INTENT_SCHEMA_VERSION_V1),
        "transaction_id": transaction_id,
        "ticker": plan["ticker"],
        "selected_state": plan["selected_state"],
        "manual_recovery_plan_fingerprint": plan["plan_fingerprint"],
        "manual_recovery_approval_fingerprint": approval["approval_fingerprint"],
        "manual_recovery_evidence_fingerprint": approval["manual_recovery_evidence_fingerprint"],
        "expected_selected_routing_snapshot_fingerprint": plan["expected_selected_routing_snapshot_fingerprint"],
        "created_at": _format_utc(now),
        "operations": [dict(operation) for operation in operations],
    }
    if lineage is not None:
        payload["clearance_revocation_lineage"] = dict(lineage)
    payload["intent_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_manual_recovery_intent(payload)
    return payload


def _load_intent(path: Path) -> dict[str, Any]:
    _resolved, payload = load_write_model_configuration_manual_recovery_intent(path)
    return payload


def load_write_model_configuration_manual_recovery_intent(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable manual recovery intent."""

    resolved, payload = _load_json_object(
        path,
        name="manual recovery intent",
    )
    validate_write_model_configuration_manual_recovery_intent(payload)
    return resolved, payload


def _persist_or_reuse_intent(
    *,
    intent: Mapping[str, Any],
    path: Path,
) -> dict[str, Any]:
    if path.is_file():
        existing = _load_intent(path)
        existing_stable = dict(existing)
        existing_stable.pop("created_at", None)
        existing_stable.pop("intent_fingerprint", None)
        candidate_stable = dict(intent)
        candidate_stable.pop("created_at", None)
        candidate_stable.pop("intent_fingerprint", None)
        if existing_stable != candidate_stable:
            raise (
                WriteModelConfigurationManualRecoveryApplicationBlockedError(
                    "manual recovery intent already exists with different content"
                )
            )
        return existing
    _persist_immutable(intent, path)
    return dict(intent)


def _validate_consumption(payload: Mapping[str, Any]) -> None:
    consumption = _mapping(
        payload,
        name="manual recovery approval consumption",
    )
    _validate_versioned_clearance_revocation_lineage(
        consumption,
        schema_version_v1=_CONSUMPTION_SCHEMA_VERSION_V1,
        schema_version_v2=_CONSUMPTION_SCHEMA_VERSION_V2,
        fields_v1=_CONSUMPTION_FIELDS_V1,
        fields_v2=_CONSUMPTION_FIELDS_V2,
        name="manual recovery approval consumption",
    )
    for field_name in (
        "manual_recovery_approval_fingerprint",
        "manual_recovery_plan_fingerprint",
        "manual_recovery_evidence_fingerprint",
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
        raise ValueError("manual recovery consumption fingerprint mismatch")


def validate_write_model_configuration_manual_recovery_consumption(
    payload: Mapping[str, Any],
) -> None:
    """Validate one immutable single-use approval consumption."""

    _validate_consumption(payload)


def _consumption_payload(
    *,
    approval: Mapping[str, Any],
    plan: Mapping[str, Any],
    transaction_id: str,
    transaction_dir: Path,
    intent: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    lineage = _clearance_revocation_lineage(plan)
    _assert_same_clearance_revocation_lineage(
        lineage,
        _clearance_revocation_lineage(approval),
        message=("manual recovery consumption clearance revocation lineage does not match approval"),
    )
    _assert_same_clearance_revocation_lineage(
        lineage,
        _clearance_revocation_lineage(intent),
        message=("manual recovery consumption clearance revocation lineage does not match intent"),
    )
    payload: dict[str, Any] = {
        "schema_version": (_CONSUMPTION_SCHEMA_VERSION_V2 if lineage is not None else _CONSUMPTION_SCHEMA_VERSION_V1),
        "manual_recovery_approval_fingerprint": approval["approval_fingerprint"],
        "manual_recovery_plan_fingerprint": plan["plan_fingerprint"],
        "manual_recovery_evidence_fingerprint": approval["manual_recovery_evidence_fingerprint"],
        "transaction_id": transaction_id,
        "transaction_dir": str(transaction_dir),
        "intent_fingerprint": intent["intent_fingerprint"],
        "consumed_at": _format_utc(now),
    }
    if lineage is not None:
        payload["clearance_revocation_lineage"] = dict(lineage)
    payload["consumption_fingerprint"] = _fingerprint(payload)
    _validate_consumption(payload)
    return payload


def _load_consumption(path: Path) -> dict[str, Any]:
    _resolved, payload = load_write_model_configuration_manual_recovery_consumption(path)
    return payload


def load_write_model_configuration_manual_recovery_consumption(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable approval consumption."""

    resolved, payload = _load_json_object(
        path,
        name="manual recovery approval consumption",
    )
    validate_write_model_configuration_manual_recovery_consumption(payload)
    return resolved, payload


def _transaction_id(
    *,
    approval_fingerprint: str,
    plan_fingerprint: str,
) -> str:
    material = (f"{approval_fingerprint}\n{plan_fingerprint}\nmanual-recovery-v1").encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def write_model_configuration_manual_recovery_transaction_root(
    *,
    workspace_dir: str | Path,
) -> Path:
    """Return the authoritative internal manual-recovery transaction root."""

    return (
        Path(workspace_dir).expanduser().resolve()
        / ".dayu"
        / "write-model-configuration-manual-recoveries"
        / "transactions"
    )


def _transaction_dir(
    *,
    workspace_dir: str | Path,
    transaction_id: str,
) -> Path:
    return write_model_configuration_manual_recovery_transaction_root(workspace_dir=workspace_dir) / transaction_id


def _consumption_path(
    *,
    manual_recovery_plan_path: Path,
    approval_fingerprint: str,
) -> Path:
    digest = approval_fingerprint.removeprefix("sha256:")
    return (
        manual_recovery_plan_path.parent
        / ".dayu"
        / "consumed-write-model-configuration-manual-recovery-approvals"
        / f"{digest}.consumed.json"
    )


def _assert_consumption_identity(
    *,
    consumption: Mapping[str, Any],
    approval: Mapping[str, Any],
    plan: Mapping[str, Any],
    transaction_id: str,
) -> None:
    expected = {
        "manual_recovery_approval_fingerprint": approval["approval_fingerprint"],
        "manual_recovery_plan_fingerprint": plan["plan_fingerprint"],
        "manual_recovery_evidence_fingerprint": approval["manual_recovery_evidence_fingerprint"],
        "transaction_id": transaction_id,
    }
    if any(consumption.get(field_name) != expected_value for field_name, expected_value in expected.items()):
        raise ValueError("manual recovery consumption identity mismatch")
    plan_lineage = _clearance_revocation_lineage(plan)
    _assert_same_clearance_revocation_lineage(
        plan_lineage,
        _clearance_revocation_lineage(approval),
        message=("manual recovery approval clearance revocation lineage changed"),
    )
    _assert_same_clearance_revocation_lineage(
        plan_lineage,
        _clearance_revocation_lineage(consumption),
        message=("manual recovery consumption clearance revocation lineage changed"),
    )


def _validate_receipt_operation(
    value: object,
    *,
    name: str,
) -> dict[str, Any]:
    operation = _mapping(value, name=name)
    _exact_fields(
        operation,
        expected=_RECEIPT_OPERATION_FIELDS,
        name=name,
    )
    normalized: dict[str, Any] = {
        field_name: _required_text(
            operation.get(field_name),
            name=f"{name}.{field_name}",
            maximum_length=32_768,
        )
        for field_name in _RECEIPT_OPERATION_FIELDS
        if field_name != "final_file_fingerprint"
    }
    if normalized["json_pointer"] != _MODEL_POINTER:
        raise ValueError(f"{name}.json_pointer is invalid")
    for field_name in (
        "starting_file_fingerprint",
        "selected_file_fingerprint",
    ):
        normalized[field_name] = _validated_fingerprint(
            normalized[field_name],
            name=f"{name}.{field_name}",
        )
    if normalized["final_state"] not in {
        "selected",
        "starting",
        "unexpected",
        "unreadable",
    }:
        raise ValueError(f"{name}.final_state is invalid")
    final_fingerprint = operation.get("final_file_fingerprint")
    if final_fingerprint is not None:
        final_fingerprint = _validated_fingerprint(
            final_fingerprint,
            name=f"{name}.final_file_fingerprint",
        )
    if normalized["final_state"] == "unreadable" and final_fingerprint is not None:
        raise ValueError(f"{name}.unreadable state cannot have a fingerprint")
    if normalized["final_state"] != "unreadable" and final_fingerprint is None:
        raise ValueError(f"{name}.final fingerprint is required")
    normalized["final_file_fingerprint"] = final_fingerprint
    return normalized


def validate_write_model_configuration_manual_recovery_receipt(
    payload: Mapping[str, Any],
) -> None:
    """Validate one immutable exact recovery result."""

    receipt = _mapping(payload, name="manual recovery receipt")
    lineage = _validate_versioned_clearance_revocation_lineage(
        receipt,
        schema_version_v1=_RECEIPT_SCHEMA_VERSION_V1,
        schema_version_v2=_RECEIPT_SCHEMA_VERSION_V2,
        fields_v1=_RECEIPT_FIELDS_V1,
        fields_v2=_RECEIPT_FIELDS_V2,
        name="manual recovery receipt",
    )
    constants = {
        "receipt_type": _RECEIPT_TYPE,
        "scope": _SCOPE,
    }
    for field_name, expected_value in constants.items():
        if receipt.get(field_name) != expected_value:
            raise ValueError(f"manual recovery receipt {field_name} is invalid")
    status = receipt.get("status")
    if status not in _RECEIPT_STATUSES:
        raise ValueError("manual recovery receipt status is invalid")
    if receipt.get("action") != _RECEIPT_ACTIONS[str(status)]:
        raise ValueError("manual recovery receipt action is invalid")
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
    if receipt.get("selected_state") not in _SELECTED_STATES:
        raise ValueError("manual recovery selected_state is invalid")
    for field_name in (
        "source_manual_recovery_plan",
        "source_manual_recovery_approval",
        "source_manual_recovery_evidence",
        "approval_consumption",
    ):
        _validate_source(receipt.get(field_name), name=field_name)
    intent_source = receipt.get("write_ahead_intent")
    if intent_source is None:
        if status != "recovery_failed":
            raise ValueError("completed manual recovery receipt requires an intent")
    else:
        _validate_source(intent_source, name="write_ahead_intent")
    expected_snapshot = _validated_fingerprint(
        receipt.get("expected_selected_routing_snapshot_fingerprint"),
        name="expected_selected_routing_snapshot_fingerprint",
    )
    post_snapshot = receipt.get("post_operation_routing_snapshot_fingerprint")
    if post_snapshot is not None:
        post_snapshot = _validated_fingerprint(
            post_snapshot,
            name="post_operation_routing_snapshot_fingerprint",
        )
    raw_operations = receipt.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("manual recovery receipt operations are empty")
    operations = [
        _validate_receipt_operation(
            operation,
            name=f"operations[{index}]",
        )
        for index, operation in enumerate(raw_operations)
    ]
    if len({(operation["role"], operation["scene_name"]) for operation in operations}) != len(operations):
        raise ValueError("manual recovery receipt operations duplicate")
    failure = receipt.get("failure")
    if failure is not None:
        failure_view = _mapping(failure, name="failure")
        _exact_fields(
            failure_view,
            expected=_FAILURE_FIELDS,
            name="failure",
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
        codes = failure_view.get("recovery_failure_codes")
        if not isinstance(codes, list) or any(not isinstance(item, str) or not item for item in codes):
            raise ValueError("failure recovery codes are invalid")
    if status == "recovered":
        if (
            failure is not None
            or post_snapshot is None
            or not hmac.compare_digest(
                expected_snapshot,
                post_snapshot,
            )
            or receipt.get("starting_state_recovery_performed") is True
            or receipt.get("starting_state_recovery_exact") is not False
            or receipt.get("configuration_recovery_completed") is not True
            or any(operation["final_state"] != "selected" for operation in operations)
        ):
            raise ValueError("recovered receipt state is invalid")
    elif failure is None or post_snapshot is not None:
        raise ValueError("failed recovery receipt state is invalid")
    elif status == "starting_state_restored":
        if (
            receipt.get("starting_state_recovery_performed") is not True
            or receipt.get("starting_state_recovery_exact") is not True
            or receipt.get("configuration_recovery_completed") is not False
            or any(operation["final_state"] != "starting" for operation in operations)
        ):
            raise ValueError("starting-state-restored receipt is invalid")
    elif (
        receipt.get("starting_state_recovery_performed") is not True
        or receipt.get("starting_state_recovery_exact") is not False
        or receipt.get("configuration_recovery_completed") is not False
    ):
        raise ValueError("recovery-failed receipt state is invalid")
    expected_safety_boundaries = _V2_SAFETY_BOUNDARIES if lineage is not None else _SAFETY_BOUNDARIES
    if receipt.get("safety_boundaries") != expected_safety_boundaries:
        raise ValueError("manual recovery safety boundaries are invalid")
    if receipt.get("configuration_recovery_attempted") is not True:
        raise ValueError("manual recovery attempt evidence is invalid")
    if receipt.get("approval_consumed") is not True:
        raise ValueError("manual recovery consumption evidence is invalid")
    if receipt.get("model_execution_performed") is not False:
        raise ValueError("manual recovery model evidence is invalid")
    _parse_utc(receipt.get("completed_at"), name="completed_at")
    fingerprint = _validated_fingerprint(
        receipt.get("receipt_fingerprint"),
        name="receipt_fingerprint",
    )
    unsigned = dict(receipt)
    unsigned.pop("receipt_fingerprint", None)
    if not hmac.compare_digest(fingerprint, _fingerprint(unsigned)):
        raise ValueError("manual recovery receipt fingerprint mismatch")


def load_write_model_configuration_manual_recovery_receipt(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable manual recovery receipt."""

    target, payload = _load_json_object(
        path,
        name="manual recovery receipt",
    )
    validate_write_model_configuration_manual_recovery_receipt(payload)
    return target, payload


def persist_write_model_configuration_manual_recovery_receipt(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist one immutable manual recovery receipt."""

    validate_write_model_configuration_manual_recovery_receipt(payload)
    return _persist_immutable(payload, path)


def _stage_content(*, target: Path, content: bytes) -> Path:
    file_descriptor, temp_path_value = tempfile.mkstemp(
        prefix=f".{target.name}.dayu-manual-recovery.",
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


def _assert_target_bytes(
    operations: Sequence[Mapping[str, Any]],
    *,
    state: str,
) -> None:
    field_name = f"{state}_file_fingerprint"
    for operation in operations:
        scene_name = str(operation["scene_name"])
        target = _target_path(
            operation["target_manifest_path"],
            name=f"target for {scene_name}",
        )
        if target.is_symlink() or not target.is_file():
            raise (
                WriteModelConfigurationManualRecoveryApplicationBlockedError(
                    f"manual recovery target for {scene_name!r} is unavailable"
                )
            )
        if not hmac.compare_digest(
            _file_fingerprint(target),
            str(operation[field_name]),
        ):
            raise (
                WriteModelConfigurationManualRecoveryApplicationBlockedError(
                    f"manual recovery target for {scene_name!r} changed"
                )
            )


def _restore_starting_state(
    operations: Sequence[Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for operation in reversed(operations):
        scene_name = str(operation["scene_name"])
        target = _target_path(
            operation["target_manifest_path"],
            name=f"recovery target for {scene_name}",
        )
        if target.parent.is_symlink() or target.is_symlink():
            failures.append(f"{scene_name}:target_unsafe")
            continue
        starting_fingerprint = str(operation["starting_file_fingerprint"])
        selected_fingerprint = str(operation["selected_file_fingerprint"])
        try:
            current_fingerprint = _file_fingerprint(target)
        except OSError:
            failures.append(f"{scene_name}:target_unreadable")
            continue
        if hmac.compare_digest(
            current_fingerprint,
            starting_fingerprint,
        ):
            continue
        if not hmac.compare_digest(
            current_fingerprint,
            selected_fingerprint,
        ):
            failures.append(f"{scene_name}:unexpected_target_content")
            continue
        try:
            _replace_content_atomically(
                target=target,
                content=_decode_base64(
                    operation["starting_file_content_base64"],
                    name=f"starting bytes for {scene_name}",
                ),
            )
            if not hmac.compare_digest(
                _file_fingerprint(target),
                starting_fingerprint,
            ):
                failures.append(f"{scene_name}:recovery_mismatch")
        except OSError:
            failures.append(f"{scene_name}:recovery_failed")
    for operation in operations:
        scene_name = str(operation["scene_name"])
        target = _target_path(
            operation["target_manifest_path"],
            name=f"recovery target for {scene_name}",
        )
        if target.parent.is_symlink() or target.is_symlink():
            exact = False
        else:
            try:
                exact = hmac.compare_digest(
                    _file_fingerprint(target),
                    str(operation["starting_file_fingerprint"]),
                )
            except OSError:
                exact = False
        code = f"{scene_name}:starting_state_not_exact"
        if not exact and code not in failures:
            failures.append(code)
    return not failures, failures


def _observe_final_operation(
    operation: Mapping[str, Any],
    *,
    preferred_state: str,
) -> dict[str, Any]:
    target = _target_path(
        operation["target_manifest_path"],
        name=f"target for {operation['scene_name']}",
    )
    if target.parent.is_symlink() or target.is_symlink():
        final_state = "unreadable"
        fingerprint = None
    else:
        try:
            fingerprint = _file_fingerprint(target)
        except OSError:
            final_state = "unreadable"
            fingerprint = None
        else:
            selected_match = hmac.compare_digest(
                fingerprint,
                str(operation["selected_file_fingerprint"]),
            )
            starting_match = hmac.compare_digest(
                fingerprint,
                str(operation["starting_file_fingerprint"]),
            )
            if preferred_state == "starting" and starting_match:
                final_state = "starting"
            elif selected_match:
                final_state = "selected"
            elif starting_match:
                final_state = "starting"
            else:
                final_state = "unexpected"
    return {
        "role": operation["role"],
        "scene_name": operation["scene_name"],
        "target_manifest_path": str(target),
        "json_pointer": _MODEL_POINTER,
        "observed_state": operation["observed_state"],
        "selected_model_name": operation["selected_model_name"],
        "starting_file_fingerprint": operation["starting_file_fingerprint"],
        "selected_file_fingerprint": operation["selected_file_fingerprint"],
        "final_state": final_state,
        "final_file_fingerprint": fingerprint,
    }


def _build_receipt(
    *,
    status: str,
    transaction_id: str,
    plan_path: Path,
    plan: Mapping[str, Any],
    approval_path: Path,
    approval: Mapping[str, Any],
    intent_path: Path | None,
    intent: Mapping[str, Any] | None,
    consumption_path: Path,
    consumption: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
    post_snapshot: Mapping[str, Any] | None,
    failure_stage: str | None,
    error_type: str | None,
    recovery_failure_codes: Sequence[str],
    completed_at: datetime,
) -> dict[str, Any]:
    evidence_source = _validate_source(
        plan.get("source_manual_recovery_evidence"),
        name="source_manual_recovery_evidence",
    )
    lineage = _clearance_revocation_lineage(plan)
    _assert_same_clearance_revocation_lineage(
        lineage,
        _clearance_revocation_lineage(approval),
        message=("manual recovery receipt clearance revocation lineage does not match approval"),
    )
    _assert_same_clearance_revocation_lineage(
        lineage,
        _clearance_revocation_lineage(consumption),
        message=("manual recovery receipt clearance revocation lineage does not match consumption"),
    )
    if intent is not None:
        _assert_same_clearance_revocation_lineage(
            lineage,
            _clearance_revocation_lineage(intent),
            message=("manual recovery receipt clearance revocation lineage does not match intent"),
        )
    failure = (
        None
        if failure_stage is None or error_type is None
        else {
            "stage": failure_stage,
            "error_type": error_type,
            "recovery_failure_codes": list(recovery_failure_codes),
        }
    )
    payload: dict[str, Any] = {
        "schema_version": (_RECEIPT_SCHEMA_VERSION_V2 if lineage is not None else _RECEIPT_SCHEMA_VERSION_V1),
        "receipt_type": _RECEIPT_TYPE,
        "scope": _SCOPE,
        "status": status,
        "action": _RECEIPT_ACTIONS[status],
        "ticker": plan["ticker"],
        "transaction_id": transaction_id,
        "selected_state": plan["selected_state"],
        "source_manual_recovery_plan": _source_reference(
            path=plan_path,
            content_fingerprint=str(plan["plan_fingerprint"]),
        ),
        "source_manual_recovery_approval": _source_reference(
            path=approval_path,
            content_fingerprint=str(approval["approval_fingerprint"]),
        ),
        "source_manual_recovery_evidence": dict(evidence_source),
        "write_ahead_intent": (
            None
            if intent_path is None or intent is None
            else _source_reference(
                path=intent_path,
                content_fingerprint=str(intent["intent_fingerprint"]),
            )
        ),
        "expected_selected_routing_snapshot_fingerprint": plan["expected_selected_routing_snapshot_fingerprint"],
        "post_operation_routing_snapshot_fingerprint": (
            None
            if post_snapshot is None
            else _snapshot_fingerprint(
                post_snapshot,
                name="post manual recovery snapshot",
            )
        ),
        "approval_consumption": _source_reference(
            path=consumption_path,
            content_fingerprint=str(consumption["consumption_fingerprint"]),
        ),
        "operations": [
            _observe_final_operation(
                operation,
                preferred_state=("selected" if status == "recovered" else "starting"),
            )
            for operation in operations
        ],
        "failure": failure,
        "starting_state_recovery_performed": (status != "recovered"),
        "starting_state_recovery_exact": (status == "starting_state_restored"),
        "completed_at": _format_utc(completed_at),
        "safety_boundaries": list(_V2_SAFETY_BOUNDARIES if lineage is not None else _SAFETY_BOUNDARIES),
        "configuration_recovery_attempted": True,
        "configuration_recovery_completed": status == "recovered",
        "approval_consumed": True,
        "model_execution_performed": False,
    }
    if lineage is not None:
        payload["clearance_revocation_lineage"] = dict(lineage)
    payload["receipt_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_manual_recovery_receipt(payload)
    return payload


def _probe_receipt_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, probe_value = tempfile.mkstemp(
        prefix=".dayu-manual-recovery-receipt-probe.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(file_descriptor)
    Path(probe_value).unlink()


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
        raise WriteModelConfigurationManualRecoveryReceiptError(
            "manual recovery result is recorded internally but the requested receipt could not be exported"
        ) from exc


def _assert_approval_plan_identity(
    *,
    plan_path: Path,
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> None:
    source = _validate_source(
        approval.get("manual_recovery_plan_source"),
        name="manual_recovery_plan_source",
    )
    if (
        _absolute_path(
            source["path"],
            name="manual_recovery_plan_source.path",
        )
        != plan_path
    ):
        raise (
            WriteModelConfigurationManualRecoveryApplicationBlockedError(
                "manual recovery approval is bound to another plan path"
            )
        )
    if not hmac.compare_digest(
        str(source["file_fingerprint"]),
        _file_fingerprint(plan_path),
    ):
        raise (WriteModelConfigurationManualRecoveryApplicationBlockedError("manual recovery plan file changed"))
    if not hmac.compare_digest(
        str(plan["plan_fingerprint"]),
        str(approval["manual_recovery_plan_fingerprint"]),
    ):
        raise (
            WriteModelConfigurationManualRecoveryApplicationBlockedError(
                "manual recovery approval plan identity changed"
            )
        )
    embedded = _mapping(
        approval.get("manual_recovery_plan"),
        name="embedded manual recovery plan",
    )
    if not hmac.compare_digest(
        _canonical_json(plan),
        _canonical_json(embedded),
    ):
        raise (WriteModelConfigurationManualRecoveryApplicationBlockedError("manual recovery embedded plan changed"))


def _intent_operations(
    intent: Mapping[str, Any],
    *,
    config_root: Path,
) -> list[dict[str, str]]:
    raw_operations = intent.get("operations")
    if not isinstance(raw_operations, list):
        raise ValueError("manual recovery intent operations are invalid")
    operations = [
        _validate_intent_operation(
            operation,
            name=f"intent.operations[{index}]",
        )
        for index, operation in enumerate(raw_operations)
    ]
    for operation in operations:
        _assert_safe_target(
            target=_target_path(
                operation["target_manifest_path"],
                name=f"target for {operation['scene_name']}",
            ),
            config_root=config_root,
            scene_name=operation["scene_name"],
        )
    return operations


def _receipt_operations_from_plan(
    plan: Mapping[str, Any],
    *,
    config_root: Path,
) -> list[dict[str, str]]:
    raw_operations = plan.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("manual recovery plan operations are invalid")
    operations: list[dict[str, str]] = []
    for index, raw_operation in enumerate(raw_operations):
        source = _mapping(
            raw_operation,
            name=f"plan.operations[{index}]",
        )
        scene_name = _required_text(
            source.get("scene_name"),
            name=f"plan.operations[{index}].scene_name",
            maximum_length=128,
        )
        target = _target_path(
            source.get("target_manifest_path"),
            name=f"plan.operations[{index}].target_manifest_path",
        )
        _assert_target_identity(
            target=target,
            config_root=config_root,
            scene_name=scene_name,
        )
        operations.append(
            {
                "role": _required_text(
                    source.get("role"),
                    name=f"plan.operations[{index}].role",
                    maximum_length=32,
                ),
                "scene_name": scene_name,
                "target_manifest_path": str(target),
                "json_pointer": _MODEL_POINTER,
                "observed_state": _required_text(
                    source.get("observed_state"),
                    name=f"plan.operations[{index}].observed_state",
                    maximum_length=32,
                ),
                "selected_model_name": _required_text(
                    source.get("selected_model_name"),
                    name=(f"plan.operations[{index}].selected_model_name"),
                    maximum_length=256,
                ),
                "starting_file_fingerprint": _validated_fingerprint(
                    source.get("expected_current_file_fingerprint"),
                    name=(f"plan.operations[{index}].expected_current_file_fingerprint"),
                ),
                "selected_file_fingerprint": _validated_fingerprint(
                    source.get("selected_file_fingerprint"),
                    name=(f"plan.operations[{index}].selected_file_fingerprint"),
                ),
            }
        )
    return operations


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
    internal_receipt_path: Path,
    external_receipt_path: Path,
    now: datetime,
) -> dict[str, Any]:
    intent_path = internal_receipt_path.parent / "intent.json"
    try:
        intent = _load_intent(intent_path)
        if (
            intent.get("intent_fingerprint") != consumption.get("intent_fingerprint")
            or intent.get("transaction_id") != transaction_id
        ):
            raise ValueError("manual recovery intent identity mismatch")
        plan_lineage = _clearance_revocation_lineage(plan)
        _assert_same_clearance_revocation_lineage(
            plan_lineage,
            _clearance_revocation_lineage(consumption),
            message=("manual recovery interrupted transaction clearance revocation lineage differs from consumption"),
        )
        _assert_same_clearance_revocation_lineage(
            plan_lineage,
            _clearance_revocation_lineage(intent),
            message=("manual recovery interrupted transaction clearance revocation lineage differs from intent"),
        )
        operations = _intent_operations(
            intent,
            config_root=config_root,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        operations = _receipt_operations_from_plan(
            plan,
            config_root=config_root,
        )
        receipt = _build_receipt(
            status="recovery_failed",
            transaction_id=transaction_id,
            plan_path=plan_path,
            plan=plan,
            approval_path=approval_path,
            approval=approval,
            intent_path=None,
            intent=None,
            consumption_path=consumption_path,
            consumption=consumption,
            operations=operations,
            post_snapshot=None,
            failure_stage="interrupted_transaction_recovery",
            error_type=type(exc).__name__,
            recovery_failure_codes=["write_ahead_intent:unavailable_or_invalid"],
            completed_at=now,
        )
        _persist_receipts(
            receipt=receipt,
            internal_receipt_path=internal_receipt_path,
            external_receipt_path=external_receipt_path,
        )
        return receipt
    restored, failures = _restore_starting_state(operations)
    receipt = _build_receipt(
        status=("starting_state_restored" if restored else "recovery_failed"),
        transaction_id=transaction_id,
        plan_path=plan_path,
        plan=plan,
        approval_path=approval_path,
        approval=approval,
        intent_path=intent_path,
        intent=intent,
        consumption_path=consumption_path,
        consumption=consumption,
        operations=operations,
        post_snapshot=None,
        failure_stage="interrupted_transaction_recovery",
        error_type="InterruptedManualRecovery",
        recovery_failure_codes=failures,
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
    external_receipt_path: Path,
    now: datetime,
) -> dict[str, Any]:
    transaction_dir = _absolute_path(
        consumption.get("transaction_dir"),
        name="consumption.transaction_dir",
    )
    internal_receipt_path = transaction_dir / "receipt.json"
    if internal_receipt_path.is_file():
        _resolved, receipt = load_write_model_configuration_manual_recovery_receipt(internal_receipt_path)
        if receipt.get("transaction_id") != transaction_id:
            raise ValueError("internal manual recovery receipt identity mismatch")
        try:
            _persist_immutable(receipt, external_receipt_path)
        except (FileExistsError, OSError) as exc:
            raise WriteModelConfigurationManualRecoveryReceiptError(
                "manual recovery result is recorded internally but the requested receipt could not be exported"
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
        internal_receipt_path=internal_receipt_path,
        external_receipt_path=external_receipt_path,
        now=now,
    )


def apply_write_model_configuration_manual_recovery(
    *,
    manual_recovery_plan_path: str | Path,
    manual_recovery_approval_path: str | Path,
    config_root: str | Path,
    workspace_dir: str | Path,
    receipt_output_path: str | Path,
    snapshot_builder: RoutingSnapshotBuilder,
    now: datetime,
) -> dict[str, Any]:
    """Consume one approval and recover the exact selected state."""

    current_time = _normalize_now(now)
    resolved_plan_path, plan = load_write_model_configuration_manual_recovery_plan(manual_recovery_plan_path)
    resolved_approval_path, approval = load_write_model_configuration_manual_recovery_approval(
        manual_recovery_approval_path
    )
    _assert_approval_plan_identity(
        plan_path=resolved_plan_path,
        plan=plan,
        approval=approval,
    )
    resolved_config_root = Path(config_root).expanduser().resolve()
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
    intent_path = transaction_dir / "intent.json"
    internal_receipt_path = transaction_dir / "receipt.json"
    external_receipt_path = Path(receipt_output_path).expanduser().resolve()
    consumption_path = _consumption_path(
        manual_recovery_plan_path=resolved_plan_path,
        approval_fingerprint=approval_fingerprint,
    )
    for artifact_name, artifact_path in (
        ("transaction directory", transaction_dir),
        ("approval consumption", consumption_path),
        ("external receipt", external_receipt_path),
    ):
        if _is_relative_to(artifact_path, resolved_config_root):
            raise (
                WriteModelConfigurationManualRecoveryApplicationBlockedError(
                    f"{artifact_name} must be outside the configuration root"
                )
            )
    transaction_lock = create_write_model_configuration_transaction_lock(resolved_config_root)
    try:
        transaction_lock.acquire()
    except RuntimeError as exc:
        raise WriteModelConfigurationManualRecoveryApplicationBusyError(
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
                config_root=resolved_config_root,
                external_receipt_path=external_receipt_path,
                now=current_time,
            )
        _probe_receipt_parent(external_receipt_path)
        try:
            current_plan = assert_write_model_configuration_manual_recovery_approval_current(
                approval=approval,
                manual_recovery_plan_path=resolved_plan_path,
                config_root=resolved_config_root,
                now=current_time,
            )
        except (
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise (
                WriteModelConfigurationManualRecoveryApplicationBlockedError(
                    "manual recovery approval verification failed"
                )
            ) from exc
        if not hmac.compare_digest(
            _canonical_json(plan),
            _canonical_json(current_plan),
        ):
            raise (
                WriteModelConfigurationManualRecoveryApplicationBlockedError(
                    "manual recovery plan changed during verification"
                )
            )
        operations = _build_operations(
            plan=plan,
            config_root=resolved_config_root,
        )
        _assert_target_bytes(operations, state="starting")
        intent = _persist_or_reuse_intent(
            intent=_build_intent(
                plan=plan,
                approval=approval,
                operations=operations,
                transaction_id=transaction_id,
                now=current_time,
            ),
            path=intent_path,
        )
        for operation in operations:
            staged_files.append(
                _stage_content(
                    target=_target_path(
                        operation["target_manifest_path"],
                        name=f"target for {operation['scene_name']}",
                    ),
                    content=_decode_base64(
                        operation["selected_file_content_base64"],
                        name=(f"selected bytes for {operation['scene_name']}"),
                    ),
                )
            )
        _assert_target_bytes(operations, state="starting")
        consumption = _consumption_payload(
            approval=approval,
            plan=plan,
            transaction_id=transaction_id,
            transaction_dir=transaction_dir,
            intent=intent,
            now=current_time,
        )
        _persist_exclusive(consumption, consumption_path)
        failure_stage = "manifest_manual_recovery"
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
                    str(operation["starting_file_fingerprint"]),
                ):
                    raise RuntimeError("manifest changed after manual recovery approval consumption")
                _replace_staged_file(staged=staged, target=target)
                if not hmac.compare_digest(
                    _file_fingerprint(target),
                    str(operation["selected_file_fingerprint"]),
                ):
                    raise RuntimeError("selected manifest fingerprint mismatch")
            failure_stage = "post_manual_recovery_preflight"
            selected_snapshot = dict(snapshot_builder())
            actual_snapshot_fingerprint = _snapshot_fingerprint(
                selected_snapshot,
                name="selected manual recovery snapshot",
            )
            if not hmac.compare_digest(
                actual_snapshot_fingerprint,
                str(plan["expected_selected_routing_snapshot_fingerprint"]),
            ):
                raise RuntimeError("selected routing snapshot does not match the plan")
        except BaseException as exc:
            restored, failures = _restore_starting_state(operations)
            receipt = _build_receipt(
                status=("starting_state_restored" if restored else "recovery_failed"),
                transaction_id=transaction_id,
                plan_path=resolved_plan_path,
                plan=plan,
                approval_path=resolved_approval_path,
                approval=approval,
                intent_path=intent_path,
                intent=intent,
                consumption_path=consumption_path,
                consumption=consumption,
                operations=operations,
                post_snapshot=None,
                failure_stage=failure_stage,
                error_type=type(exc).__name__,
                recovery_failure_codes=failures,
                completed_at=current_time,
            )
            _persist_receipts(
                receipt=receipt,
                internal_receipt_path=internal_receipt_path,
                external_receipt_path=external_receipt_path,
            )
            return receipt
        receipt = _build_receipt(
            status="recovered",
            transaction_id=transaction_id,
            plan_path=resolved_plan_path,
            plan=plan,
            approval_path=resolved_approval_path,
            approval=approval,
            intent_path=intent_path,
            intent=intent,
            consumption_path=consumption_path,
            consumption=consumption,
            operations=operations,
            post_snapshot=selected_snapshot,
            failure_stage=None,
            error_type=None,
            recovery_failure_codes=[],
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


def format_write_model_configuration_manual_recovery_receipt_report(
    receipt: Mapping[str, Any],
) -> tuple[str, ...]:
    """Render a concise operator-facing recovery result."""

    validate_write_model_configuration_manual_recovery_receipt(receipt)
    lineage = _clearance_revocation_lineage(receipt)
    return (
        "",
        "=" * 60,
        "Write-model configuration manual recovery",
        f"  Status       : {receipt['status']}",
        f"  Action       : {receipt['action']}",
        f"  Ticker       : {receipt['ticker']}",
        f"  State        : {receipt['selected_state']}",
        f"  Transaction  : {receipt['transaction_id']}",
        *(
            (f"  Revocation fp: {lineage['manual_recovery_clearance_revocation_fingerprint']}",)
            if lineage is not None
            else ()
        ),
        "  Approval     : consumed once before first manifest replace",
        (
            "  Configuration: exact selected state restored"
            if receipt["status"] == "recovered"
            else (
                "  Configuration: exact starting state restored"
                if receipt["status"] == "starting_state_restored"
                else "  Configuration: manual intervention required"
            )
        ),
        "  Model calls  : none",
        f"  Receipt fp   : {receipt['receipt_fingerprint']}",
        "=" * 60,
    )


__all__ = [
    "WriteModelConfigurationManualRecoveryApplicationBlockedError",
    "WriteModelConfigurationManualRecoveryApplicationBusyError",
    "WriteModelConfigurationManualRecoveryReceiptError",
    "apply_write_model_configuration_manual_recovery",
    "format_write_model_configuration_manual_recovery_receipt_report",
    "load_write_model_configuration_manual_recovery_consumption",
    "load_write_model_configuration_manual_recovery_intent",
    "load_write_model_configuration_manual_recovery_receipt",
    "persist_write_model_configuration_manual_recovery_receipt",
    "validate_write_model_configuration_manual_recovery_consumption",
    "validate_write_model_configuration_manual_recovery_intent",
    "validate_write_model_configuration_manual_recovery_receipt",
    "write_model_configuration_manual_recovery_transaction_root",
]
