"""Apply one approved write-model routing plan transactionally."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dayu.contracts.model_config import ModelConfigJsonValue
from dayu.services._write_artifact_utils import (
    absolute_path,
    bytes_fingerprint,
    decode_base64,
    file_fingerprint,
    fingerprint_bytes,
    format_utc,
    is_subpath,
    require_mapping,
    require_text,
    serialize_pretty,
)
from dayu.services.write_model_configuration_change import (
    load_write_model_configuration_change_approval,
)
from dayu.services.write_model_configuration_preapplication import (
    load_write_model_configuration_preapplication_plan,
    load_write_scene_model_routing_snapshot,
    validate_write_scene_model_routing_snapshot,
    verify_write_model_configuration_preapplication_plan,
)
from dayu.state_dir_lock import StateDirSingleInstanceLock

_INTENT_SCHEMA_VERSION = (
    "write_model_challenger_configuration_application_intent_v1"
)
_CONSUMPTION_SCHEMA_VERSION = (
    "write_model_challenger_configuration_change_consumption_v1"
)
_RECEIPT_SCHEMA_VERSION = (
    "write_model_challenger_configuration_application_receipt_v1"
)
_VERIFICATION_SCHEMA_VERSION = (
    "write_model_challenger_configuration_application_verification_v1"
)
_RECEIPT_TYPE = "write_scene_model_routing_application"
_APPLICATION_SCOPE = (
    "single_use_transactional_manifest_application_with_exact_rollback"
)
_LOCK_FILE_NAME = ".write-model-configuration-application.lock"
_LOCK_NAME = "write model configuration application"
_MODEL_POINTER = "/model/default_name"
_RECEIPT_STATUSES = {
    "applied",
    "rolled_back",
    "rollback_failed",
}
_SAFETY_BOUNDARIES = [
    "single_use_approval_consumed_before_first_configuration_replace",
    "all_targets_verified_before_approval_consumption",
    "cross_process_configuration_lock_required",
    "write_ahead_intent_persisted_before_approval_consumption",
    "each_manifest_replace_is_atomic",
    "post_application_fresh_runtime_preflight_required",
    "failure_restores_exact_preapplication_bytes",
    "interrupted_transaction_is_recovered_before_any_new_attempt",
    "application_does_not_modify_run_config_or_model_catalog",
    "application_does_not_call_models",
    "application_does_not_modify_secrets",
    "application_does_not_start_a_write_run",
]
_INTENT_FIELDS = {
    "schema_version",
    "transaction_id",
    "ticker",
    "plan_fingerprint",
    "approval_fingerprint",
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
    "proposed_model_name",
    "original_file_fingerprint",
    "original_file_content_base64",
    "applied_file_fingerprint",
    "applied_file_content_base64",
}
_CONSUMPTION_FIELDS = {
    "schema_version",
    "approval_fingerprint",
    "plan_fingerprint",
    "transaction_id",
    "transaction_dir",
    "intent_fingerprint",
    "consumed_at",
    "consumption_fingerprint",
}
_SOURCE_FIELDS = {
    "path",
    "file_fingerprint",
    "content_fingerprint",
}
_RECEIPT_OPERATION_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "expected_current_model_name",
    "applied_model_name",
    "original_file_fingerprint",
    "applied_file_fingerprint",
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
    "source_plan",
    "source_approval",
    "source_routing_snapshot_fingerprint",
    "post_operation_routing_snapshot_fingerprint",
    "approval_consumption",
    "operations",
    "failure",
    "rollback_exact",
    "completed_at",
    "safety_boundaries",
    "configuration_application_performed",
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
    "eligible_for_operator_rollback_plan",
    "reason_codes",
    "configuration_verification_performed",
    "configuration_application_performed",
    "approval_consumed",
    "model_execution_performed",
}
_VERIFICATION_STATUSES = {
    "current",
    "routing_changed",
    "manual_recovery_required",
}
_EXPECTED_CONFIGURATION_STATES = {
    "applied": "approved_application",
    "rolled_back": "preapplication_restored",
    "rollback_failed": "manual_recovery",
}

RoutingSnapshotBuilder = Callable[[], Mapping[str, Any]]


class WriteModelConfigurationApplicationBlockedError(ValueError):
    """Raised when the application gate fails before approval consumption."""


class WriteModelConfigurationApplicationBusyError(RuntimeError):
    """Raised when another process currently owns the configuration lock."""


class WriteModelConfigurationApplicationReceiptError(RuntimeError):
    """Raised when a completed internal receipt cannot be exported."""


def create_write_model_configuration_transaction_lock(
    config_root: str | Path,
) -> StateDirSingleInstanceLock:
    """Create the shared lock used by configuration apply and rollback."""

    resolved_root = Path(config_root).expanduser().resolve()
    return StateDirSingleInstanceLock(
        state_dir=_lock_state_dir(resolved_root),
        lock_file_name=_LOCK_FILE_NAME,
        lock_name=_LOCK_NAME,
    )


def _exact_fields(
    payload: Mapping[str, Any],
    *,
    expected: set[str],
    name: str,
) -> None:
    fields = set(payload)
    if fields != expected:
        missing = sorted(expected - fields)
        extra = sorted(fields - expected)
        raise ValueError(
            f"{name} fields are invalid: missing={missing}, extra={extra}"
        )


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _parse_utc(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> datetime:
    text = require_text(
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


def _validated_fingerprint(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> str:
    text = require_text(
        value,
        name=name,
        maximum_length=80,
    )
    if not text.startswith("sha256:"):
        raise ValueError(f"{name} must use sha256")
    digest = text.removeprefix("sha256:")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef"
        for character in digest
    ):
        raise ValueError(f"{name} is invalid")
    return text


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
    serialized = serialize_pretty(payload)
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


def _persist_exclusive(
    payload: Mapping[str, Any],
    path: Path,
) -> Path:
    if path.exists():
        raise FileExistsError(f"single-use artifact already exists: {path}")
    return _persist_immutable(payload, path)


def _encode_base64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _load_source_snapshot(
    plan: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    source = require_mapping(
        plan.get("source_routing_snapshot"),
        name="source_routing_snapshot",
    )
    snapshot_path = absolute_path(
        require_text(
            source.get("path"),
            name="source_routing_snapshot.path",
            maximum_length=32_768,
        ),
        name="source_routing_snapshot.path",
    )
    return load_write_scene_model_routing_snapshot(snapshot_path)


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


def _configuration_root(
    snapshot: Mapping[str, Any],
) -> Path:
    context = require_mapping(
        snapshot.get("resolution_context"),
        name="routing snapshot resolution_context",
    )
    return absolute_path(
        require_text(
            context.get("config_root"),
            name="routing snapshot config_root",
            maximum_length=32_768,
        ),
        name="routing snapshot config_root",
    )


def _operation_key(value: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(value.get("role") or ""),
        str(value.get("scene_name") or ""),
    )


def _render_applied_manifest(
    *,
    original_bytes: bytes,
    expected_current_model_name: str,
    proposed_model_name: str,
    scene_name: str,
) -> bytes:
    try:
        decoded = original_bytes.decode("utf-8")
        payload = json.loads(decoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"manifest for scene {scene_name!r} is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"manifest for scene {scene_name!r} must be an object"
        )
    model = payload.get("model")
    if not isinstance(model, dict):
        raise ValueError(
            f"manifest for scene {scene_name!r} is missing model object"
        )
    if model.get("default_name") != expected_current_model_name:
        raise WriteModelConfigurationApplicationBlockedError(
            f"manifest for scene {scene_name!r} no longer contains "
            "the approved current model"
        )
    allowed_names = model.get("allowed_names")
    if (
        not isinstance(allowed_names, list)
        or proposed_model_name not in allowed_names
    ):
        raise WriteModelConfigurationApplicationBlockedError(
            f"manifest for scene {scene_name!r} no longer allows "
            "the proposed model"
        )
    model["default_name"] = proposed_model_name
    newline = "\r\n" if "\r\n" in decoded else "\n"
    had_final_newline = decoded.endswith(("\n", "\r"))
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    if newline != "\n":
        rendered = rendered.replace("\n", newline)
    if had_final_newline:
        rendered += newline
    return rendered.encode("utf-8")


def _build_operations(
    *,
    plan: Mapping[str, Any],
    config_root: Path,
) -> list[dict[str, str]]:
    raw_transitions = plan.get("transitions")
    raw_rollback = require_mapping(
        plan.get("rollback"),
        name="preapplication rollback",
    ).get("entries")
    if not isinstance(raw_transitions, list):
        raise ValueError("preapplication transitions must be a list")
    if not isinstance(raw_rollback, list):
        raise ValueError("preapplication rollback entries must be a list")
    rollback_by_key = {
        _operation_key(
            require_mapping(entry, name=f"rollback.entries[{index}]")
        ): require_mapping(entry, name=f"rollback.entries[{index}]")
        for index, entry in enumerate(raw_rollback)
    }
    operations: list[dict[str, str]] = []
    seen_paths: set[Path] = set()
    manifest_root = (
        config_root / "prompts" / "manifests"
    ).resolve()
    for index, raw_transition in enumerate(raw_transitions):
        transition = require_mapping(
            raw_transition,
            name=f"transitions[{index}]",
        )
        role = require_text(
            transition.get("role"),
            name=f"transitions[{index}].role",
            maximum_length=32,
        )
        scene_name = require_text(
            transition.get("scene_name"),
            name=f"transitions[{index}].scene_name",
            maximum_length=128,
        )
        expected_current_model_name = require_text(
            transition.get("expected_current_model_name"),
            name=(
                f"transitions[{index}].expected_current_model_name"
            ),
            maximum_length=256,
        )
        proposed_model_name = require_text(
            transition.get("proposed_model_name"),
            name=f"transitions[{index}].proposed_model_name",
            maximum_length=256,
        )
        if transition.get("json_pointer") != _MODEL_POINTER:
            raise ValueError(
                f"transition for scene {scene_name!r} has invalid pointer"
            )
        target = absolute_path(
            require_text(
                transition.get("target_manifest_path"),
                name=(
                    f"transitions[{index}].target_manifest_path"
                ),
                maximum_length=32_768,
            ),
            name=f"transitions[{index}].target_manifest_path",
        )
        if (
            not is_subpath(target, manifest_root)
            or target.parent != manifest_root
            or target.name != f"{scene_name}.json"
            or target in seen_paths
        ):
            raise WriteModelConfigurationApplicationBlockedError(
                f"manifest target for scene {scene_name!r} is unsafe"
            )
        seen_paths.add(target)
        rollback = rollback_by_key.get((role, scene_name))
        if rollback is None:
            raise ValueError(
                f"rollback entry is missing for scene {scene_name!r}"
            )
        if (
            absolute_path(
                require_text(
                    rollback.get("target_manifest_path"),
                    name=(
                        f"rollback {scene_name}.target_manifest_path"
                    ),
                    maximum_length=32_768,
                ),
                name=f"rollback {scene_name}.target_manifest_path",
            )
            != target
        ):
            raise ValueError(
                f"rollback target mismatch for scene {scene_name!r}"
            )
        original_bytes = decode_base64(
            require_text(
                rollback.get("original_file_content_base64"),
                name=(
                    f"rollback {scene_name}."
                    "original_file_content_base64"
                ),
                maximum_length=1_000_000,
            ),
            name=f"rollback {scene_name}.original_file_content_base64",
        )
        original_fingerprint = bytes_fingerprint(original_bytes)
        expected_original_fingerprint = _validated_fingerprint(
            transition.get("target_manifest_fingerprint"),
            name=f"transition {scene_name}.target fingerprint",
        )
        rollback_fingerprint = _validated_fingerprint(
            rollback.get("original_file_fingerprint"),
            name=f"rollback {scene_name}.original fingerprint",
        )
        if not (
            hmac.compare_digest(
                original_fingerprint,
                expected_original_fingerprint,
            )
            and hmac.compare_digest(
                original_fingerprint,
                rollback_fingerprint,
            )
        ):
            raise ValueError(
                f"original bytes mismatch for scene {scene_name!r}"
            )
        applied_bytes = _render_applied_manifest(
            original_bytes=original_bytes,
            expected_current_model_name=expected_current_model_name,
            proposed_model_name=proposed_model_name,
            scene_name=scene_name,
        )
        operations.append(
            {
                "role": role,
                "scene_name": scene_name,
                "target_manifest_path": str(target),
                "json_pointer": _MODEL_POINTER,
                "expected_current_model_name": (
                    expected_current_model_name
                ),
                "proposed_model_name": proposed_model_name,
                "original_file_fingerprint": original_fingerprint,
                "original_file_content_base64": _encode_base64(
                    original_bytes
                ),
                "applied_file_fingerprint": bytes_fingerprint(
                    applied_bytes
                ),
                "applied_file_content_base64": _encode_base64(
                    applied_bytes
                ),
            }
        )
    if len(rollback_by_key) != len(operations):
        raise ValueError("preapplication rollback entries do not match")
    return operations


def _validate_intent_operation(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> dict[str, str]:
    operation = require_mapping(value, name=name)
    _exact_fields(
        operation,
        expected=_INTENT_OPERATION_FIELDS,
        name=name,
    )
    normalized = {
        field_name: require_text(
            operation.get(field_name),
            name=f"{name}.{field_name}",
            maximum_length=(
                1_000_000
                if field_name.endswith("_content_base64")
                else 32_768
            ),
        )
        for field_name in _INTENT_OPERATION_FIELDS
    }
    if normalized["json_pointer"] != _MODEL_POINTER:
        raise ValueError(f"{name}.json_pointer is invalid")
    target = absolute_path(
        require_text(
            normalized["target_manifest_path"],
            name=f"{name}.target_manifest_path",
            maximum_length=32_768,
        ),
        name=f"{name}.target_manifest_path",
    )
    normalized["target_manifest_path"] = str(target)
    original_bytes = decode_base64(
        require_text(
            normalized["original_file_content_base64"],
            name=f"{name}.original_file_content_base64",
            maximum_length=1_000_000,
        ),
        name=f"{name}.original_file_content_base64",
    )
    applied_bytes = decode_base64(
        require_text(
            normalized["applied_file_content_base64"],
            name=f"{name}.applied_file_content_base64",
            maximum_length=1_000_000,
        ),
        name=f"{name}.applied_file_content_base64",
    )
    if not hmac.compare_digest(
        bytes_fingerprint(original_bytes),
        _validated_fingerprint(
            normalized["original_file_fingerprint"],
            name=f"{name}.original_file_fingerprint",
        ),
    ):
        raise ValueError(f"{name} original file fingerprint mismatch")
    if not hmac.compare_digest(
        bytes_fingerprint(applied_bytes),
        _validated_fingerprint(
            normalized["applied_file_fingerprint"],
            name=f"{name}.applied_file_fingerprint",
        ),
    ):
        raise ValueError(f"{name} applied file fingerprint mismatch")
    return normalized


def validate_write_model_configuration_application_intent(
    payload: Mapping[str, Any],
) -> None:
    """Validate one write-ahead application intent."""

    intent = require_mapping(payload, name="configuration application intent")
    _exact_fields(
        intent,
        expected=_INTENT_FIELDS,
        name="configuration application intent",
    )
    if intent.get("schema_version") != _INTENT_SCHEMA_VERSION:
        raise ValueError("unsupported configuration intent schema")
    require_text(
        intent.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    require_text(
        intent.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    _validated_fingerprint(
        intent.get("plan_fingerprint"),
        name="plan_fingerprint",
    )
    _validated_fingerprint(
        intent.get("approval_fingerprint"),
        name="approval_fingerprint",
    )
    _parse_utc(intent.get("created_at"), name="created_at")
    raw_operations = intent.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("configuration intent operations must be non-empty")
    operations = [
        _validate_intent_operation(
            operation,
            name=f"operations[{index}]",
        )
        for index, operation in enumerate(raw_operations)
    ]
    keys = [_operation_key(operation) for operation in operations]
    paths = [
        operation["target_manifest_path"]
        for operation in operations
    ]
    if len(keys) != len(set(keys)) or len(paths) != len(set(paths)):
        raise ValueError("configuration intent operations contain duplicates")
    fingerprint = _validated_fingerprint(
        intent.get("intent_fingerprint"),
        name="intent_fingerprint",
    )
    unsigned = dict(intent)
    unsigned.pop("intent_fingerprint", None)
    if not hmac.compare_digest(fingerprint, fingerprint_bytes(unsigned)):
        raise ValueError("configuration intent fingerprint mismatch")


def _build_intent(
    *,
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    operations: list[dict[str, str]],
    transaction_id: str,
    now: datetime,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": _INTENT_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "ticker": plan["ticker"],
        "plan_fingerprint": plan["plan_fingerprint"],
        "approval_fingerprint": approval["approval_fingerprint"],
        "created_at": format_utc(now),
        "operations": [dict(operation) for operation in operations],
    }
    payload["intent_fingerprint"] = fingerprint_bytes(payload)
    validate_write_model_configuration_application_intent(payload)
    return payload


def _validate_consumption(
    payload: Mapping[str, Any],
) -> None:
    consumption = require_mapping(
        payload,
        name="configuration approval consumption",
    )
    _exact_fields(
        consumption,
        expected=_CONSUMPTION_FIELDS,
        name="configuration approval consumption",
    )
    if consumption.get("schema_version") != _CONSUMPTION_SCHEMA_VERSION:
        raise ValueError("unsupported approval consumption schema")
    for field_name in (
        "approval_fingerprint",
        "plan_fingerprint",
        "intent_fingerprint",
    ):
        _validated_fingerprint(
            consumption.get(field_name),
            name=field_name,
        )
    require_text(
        consumption.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    absolute_path(
        require_text(
            consumption.get("transaction_dir"),
            name="transaction_dir",
            maximum_length=32_768,
        ),
        name="transaction_dir",
    )
    _parse_utc(consumption.get("consumed_at"), name="consumed_at")
    fingerprint = _validated_fingerprint(
        consumption.get("consumption_fingerprint"),
        name="consumption_fingerprint",
    )
    unsigned = dict(consumption)
    unsigned.pop("consumption_fingerprint", None)
    if not hmac.compare_digest(fingerprint, fingerprint_bytes(unsigned)):
        raise ValueError("approval consumption fingerprint mismatch")


def _transaction_id(
    *,
    approval_fingerprint: str,
    plan_fingerprint: str,
) -> str:
    material = (
        approval_fingerprint.encode("ascii")
        + b"\0"
        + plan_fingerprint.encode("ascii")
    )
    return hashlib.sha256(material).hexdigest()


def _lock_state_dir(config_root: Path) -> Path:
    digest = hashlib.sha256(
        str(config_root).encode("utf-8")
    ).hexdigest()
    return (
        Path(tempfile.gettempdir())
        / "dayu-write-model-configuration-locks"
        / digest
    ).resolve()


def _consumption_path(
    *,
    approval_path: Path,
    approval_fingerprint: str,
) -> Path:
    digest = approval_fingerprint.removeprefix("sha256:")
    return (
        approval_path.parent
        / ".dayu"
        / "consumed-write-model-configuration-approvals"
        / f"{digest}.consumed.json"
    ).resolve()


def _transaction_dir(
    *,
    workspace_dir: str | Path,
    transaction_id: str,
) -> Path:
    return (
        Path(workspace_dir).expanduser().resolve()
        / ".dayu"
        / "write-model-configuration-applications"
        / "transactions"
        / transaction_id
    ).resolve()


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


def _receipt_operations(
    operations: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": str(operation["role"]),
            "scene_name": str(operation["scene_name"]),
            "target_manifest_path": str(
                operation["target_manifest_path"]
            ),
            "expected_current_model_name": str(
                operation["expected_current_model_name"]
            ),
            "applied_model_name": str(
                operation["proposed_model_name"]
            ),
            "original_file_fingerprint": str(
                operation["original_file_fingerprint"]
            ),
            "applied_file_fingerprint": str(
                operation["applied_file_fingerprint"]
            ),
        }
        for operation in operations
    ]


def _build_receipt(
    *,
    status: str,
    plan_path: Path,
    plan: Mapping[str, Any],
    approval_path: Path,
    approval: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    post_snapshot: Mapping[str, Any] | None,
    consumption_path: Path,
    consumption: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
    failure_stage: str | None,
    error_type: str | None,
    rollback_exact: bool,
    completed_at: datetime,
) -> dict[str, Any]:
    action = {
        "applied": "configuration_applied_stop",
        "rolled_back": "rolled_back_new_approval_required",
        "rollback_failed": "manual_recovery_required",
    }[status]
    failure: dict[str, str] | None = None
    if failure_stage is not None or error_type is not None:
        failure = {
            "stage": require_text(
                failure_stage,
                name="failure_stage",
                maximum_length=128,
            ),
            "error_type": require_text(
                error_type,
                name="error_type",
                maximum_length=256,
            ),
        }
    payload: dict[str, Any] = {
        "schema_version": _RECEIPT_SCHEMA_VERSION,
        "receipt_type": _RECEIPT_TYPE,
        "scope": _APPLICATION_SCOPE,
        "status": status,
        "action": action,
        "ticker": plan["ticker"],
        "transaction_id": consumption["transaction_id"],
        "source_plan": _source_reference(
            path=plan_path,
            content_fingerprint=str(plan["plan_fingerprint"]),
        ),
        "source_approval": _source_reference(
            path=approval_path,
            content_fingerprint=str(
                approval["approval_fingerprint"]
            ),
        ),
        "source_routing_snapshot_fingerprint": (
            _snapshot_fingerprint(
                source_snapshot,
                name="source routing snapshot",
            )
        ),
        "post_operation_routing_snapshot_fingerprint": (
            _snapshot_fingerprint(
                post_snapshot,
                name="post-operation routing snapshot",
            )
            if post_snapshot is not None
            else None
        ),
        "approval_consumption": {
            "path": str(consumption_path),
            "file_fingerprint": file_fingerprint(consumption_path),
            "content_fingerprint": consumption[
                "consumption_fingerprint"
            ],
        },
        "operations": _receipt_operations(operations),
        "failure": failure,
        "rollback_exact": rollback_exact,
        "completed_at": format_utc(completed_at),
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
        "configuration_application_performed": True,
        "approval_consumed": True,
        "model_execution_performed": False,
    }
    payload["receipt_fingerprint"] = fingerprint_bytes(payload)
    validate_write_model_configuration_application_receipt(payload)
    return payload


def _validate_receipt_operation(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> dict[str, str]:
    operation = require_mapping(value, name=name)
    _exact_fields(
        operation,
        expected=_RECEIPT_OPERATION_FIELDS,
        name=name,
    )
    normalized = {
        field_name: require_text(
            operation.get(field_name),
            name=f"{name}.{field_name}",
            maximum_length=32_768,
        )
        for field_name in _RECEIPT_OPERATION_FIELDS
    }
    normalized["target_manifest_path"] = str(
        absolute_path(
            require_text(
                normalized["target_manifest_path"],
                name=f"{name}.target_manifest_path",
                maximum_length=32_768,
            ),
            name=f"{name}.target_manifest_path",
        )
    )
    for field_name in (
        "original_file_fingerprint",
        "applied_file_fingerprint",
    ):
        normalized[field_name] = _validated_fingerprint(
            normalized[field_name],
            name=f"{name}.{field_name}",
        )
    return normalized


def validate_write_model_configuration_application_receipt(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict application, rollback, or recovery receipt."""

    receipt = require_mapping(
        payload,
        name="configuration application receipt",
    )
    _exact_fields(
        receipt,
        expected=_RECEIPT_FIELDS,
        name="configuration application receipt",
    )
    if receipt.get("schema_version") != _RECEIPT_SCHEMA_VERSION:
        raise ValueError("unsupported configuration receipt schema")
    if receipt.get("receipt_type") != _RECEIPT_TYPE:
        raise ValueError("unsupported configuration receipt type")
    if receipt.get("scope") != _APPLICATION_SCOPE:
        raise ValueError("configuration receipt scope is invalid")
    status = receipt.get("status")
    if status not in _RECEIPT_STATUSES:
        raise ValueError("configuration receipt status is invalid")
    expected_action = {
        "applied": "configuration_applied_stop",
        "rolled_back": "rolled_back_new_approval_required",
        "rollback_failed": "manual_recovery_required",
    }[str(status)]
    if receipt.get("action") != expected_action:
        raise ValueError("configuration receipt action is invalid")
    require_text(
        receipt.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    require_text(
        receipt.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    _validate_source(receipt.get("source_plan"), name="source_plan")
    _validate_source(
        receipt.get("source_approval"),
        name="source_approval",
    )
    source_fingerprint = _validated_fingerprint(
        receipt.get("source_routing_snapshot_fingerprint"),
        name="source_routing_snapshot_fingerprint",
    )
    raw_post_fingerprint = receipt.get(
        "post_operation_routing_snapshot_fingerprint"
    )
    post_fingerprint = (
        _validated_fingerprint(
            raw_post_fingerprint,
            name="post_operation_routing_snapshot_fingerprint",
        )
        if raw_post_fingerprint is not None
        else None
    )
    consumption = _validate_source(
        receipt.get("approval_consumption"),
        name="approval_consumption",
    )
    if not Path(consumption["path"]).name.endswith(".consumed.json"):
        raise ValueError("approval consumption path is invalid")
    raw_operations = receipt.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("configuration receipt operations must be non-empty")
    operations = [
        _validate_receipt_operation(
            operation,
            name=f"operations[{index}]",
        )
        for index, operation in enumerate(raw_operations)
    ]
    if len({_operation_key(item) for item in operations}) != len(
        operations
    ):
        raise ValueError("configuration receipt operations contain duplicates")
    failure = receipt.get("failure")
    if failure is not None:
        failure_view = require_mapping(failure, name="failure")
        _exact_fields(
            failure_view,
            expected=_FAILURE_FIELDS,
            name="failure",
        )
        require_text(
            failure_view.get("stage"),
            name="failure.stage",
            maximum_length=128,
        )
        require_text(
            failure_view.get("error_type"),
            name="failure.error_type",
            maximum_length=256,
        )
    if status == "applied":
        if failure is not None or receipt.get("rollback_exact") is not False:
            raise ValueError("applied receipt failure state is invalid")
    elif failure is None:
        raise ValueError("non-applied receipt must contain failure")
    if not isinstance(receipt.get("rollback_exact"), bool):
        raise ValueError("rollback_exact must be boolean")
    if status == "rolled_back" and receipt.get("rollback_exact") is not True:
        raise ValueError("rolled-back receipt must record exact rollback")
    if status == "rollback_failed" and receipt.get("rollback_exact") is not False:
        raise ValueError("rollback-failed receipt state is invalid")
    if status in {"applied", "rolled_back"} and post_fingerprint is None:
        raise ValueError(
            "completed configuration receipt must contain post snapshot"
        )
    if (
        status == "rolled_back"
        and post_fingerprint is not None
        and not hmac.compare_digest(
            source_fingerprint,
            post_fingerprint,
        )
    ):
        raise ValueError(
            "rolled-back receipt must restore the source snapshot"
        )
    if status == "rollback_failed" and post_fingerprint is not None:
        raise ValueError(
            "rollback-failed receipt cannot claim a verified post snapshot"
        )
    _parse_utc(receipt.get("completed_at"), name="completed_at")
    if receipt.get("safety_boundaries") != _SAFETY_BOUNDARIES:
        raise ValueError("configuration receipt boundaries are invalid")
    if receipt.get("configuration_application_performed") is not True:
        raise ValueError("configuration application evidence is invalid")
    if receipt.get("approval_consumed") is not True:
        raise ValueError("approval consumption evidence is invalid")
    if receipt.get("model_execution_performed") is not False:
        raise ValueError("model execution evidence is invalid")
    fingerprint = _validated_fingerprint(
        receipt.get("receipt_fingerprint"),
        name="receipt_fingerprint",
    )
    unsigned = dict(receipt)
    unsigned.pop("receipt_fingerprint", None)
    if not hmac.compare_digest(fingerprint, fingerprint_bytes(unsigned)):
        raise ValueError("configuration receipt fingerprint mismatch")


def load_write_model_configuration_application_receipt(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one immutable configuration receipt."""

    target, payload = _load_json_object(
        path,
        name="configuration application receipt",
    )
    validate_write_model_configuration_application_receipt(payload)
    return target, payload


def persist_write_model_configuration_application_receipt(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist one immutable configuration receipt."""

    validate_write_model_configuration_application_receipt(payload)
    return _persist_immutable(payload, path)


def _assert_target_bytes_current(
    operations: Sequence[Mapping[str, Any]],
) -> None:
    for operation in operations:
        scene_name = str(operation["scene_name"])
        target = Path(str(operation["target_manifest_path"]))
        if not target.is_file() or target.is_symlink():
            raise WriteModelConfigurationApplicationBlockedError(
                f"manifest target for scene {scene_name!r} is unavailable"
            )
        actual = file_fingerprint(target)
        expected = str(operation["original_file_fingerprint"])
        if not hmac.compare_digest(actual, expected):
            raise WriteModelConfigurationApplicationBlockedError(
                f"manifest target for scene {scene_name!r} changed"
            )


def _stage_content(
    *,
    target: Path,
    content: bytes,
) -> Path:
    file_descriptor, temp_path_value = tempfile.mkstemp(
        prefix=f".{target.name}.dayu-apply.",
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


def _replace_content_atomically(
    *,
    target: Path,
    content: bytes,
) -> None:
    staged = _stage_content(target=target, content=content)
    try:
        _replace_staged_file(staged=staged, target=target)
    finally:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass


def _scene_map(
    snapshot: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    raw_scenes = snapshot.get("scenes")
    if not isinstance(raw_scenes, list):
        raise ValueError("routing snapshot scenes must be a list")
    return {
        _operation_key(require_mapping(scene, name=f"scenes[{index}]")): (
            require_mapping(scene, name=f"scenes[{index}]")
        )
        for index, scene in enumerate(raw_scenes)
    }


def _verify_applied_snapshot(
    *,
    source_snapshot: Mapping[str, Any],
    applied_snapshot: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
) -> None:
    validate_write_scene_model_routing_snapshot(applied_snapshot)
    if applied_snapshot.get("ticker") != source_snapshot.get("ticker"):
        raise RuntimeError("post-application ticker changed")
    if (
        applied_snapshot.get("resolution_context")
        != source_snapshot.get("resolution_context")
    ):
        raise RuntimeError("post-application routing context changed")
    if (
        applied_snapshot.get("configuration_sources")
        != source_snapshot.get("configuration_sources")
    ):
        raise RuntimeError(
            "run configuration or model catalog changed during application"
        )
    if (
        applied_snapshot.get("fallback_scenes")
        != source_snapshot.get("fallback_scenes")
    ):
        raise RuntimeError("fallback routing changed during application")
    source_scenes = _scene_map(source_snapshot)
    applied_scenes = _scene_map(applied_snapshot)
    if set(source_scenes) != set(applied_scenes):
        raise RuntimeError("post-application scene set changed")
    operations_by_key = {
        _operation_key(operation): operation
        for operation in operations
    }
    for key, source_scene in source_scenes.items():
        applied_scene = applied_scenes[key]
        operation = operations_by_key.get(key)
        if operation is None:
            if applied_scene != source_scene:
                raise RuntimeError(
                    f"unapproved scene {key[1]!r} changed"
                )
            continue
        if (
            applied_scene.get("model_name")
            != operation["proposed_model_name"]
            or applied_scene.get("route_source")
            != "scene_manifest_default"
        ):
            raise RuntimeError(
                f"scene {key[1]!r} did not resolve to proposed model"
            )
        source_manifest = require_mapping(
            source_scene.get("manifest_source"),
            name=f"source scene {key[1]} manifest",
        )
        applied_manifest = require_mapping(
            applied_scene.get("manifest_source"),
            name=f"applied scene {key[1]} manifest",
        )
        expected_manifest = dict(source_manifest)
        expected_manifest["fingerprint"] = operation[
            "applied_file_fingerprint"
        ]
        expected_manifest["default_model_name"] = operation[
            "proposed_model_name"
        ]
        if applied_manifest != expected_manifest:
            raise RuntimeError(
                f"scene {key[1]!r} manifest evidence is unexpected"
            )


def _verify_rolled_back_snapshot(
    *,
    source_snapshot: Mapping[str, Any],
    rolled_back_snapshot: Mapping[str, Any],
) -> None:
    source_fingerprint = _snapshot_fingerprint(
        source_snapshot,
        name="source routing snapshot",
    )
    current_fingerprint = _snapshot_fingerprint(
        rolled_back_snapshot,
        name="rolled-back routing snapshot",
    )
    if not hmac.compare_digest(
        source_fingerprint,
        current_fingerprint,
    ):
        raise RuntimeError(
            "runtime routing did not return to preapplication snapshot"
        )


def _restore_operations(
    operations: Sequence[Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for operation in reversed(operations):
        scene_name = str(operation["scene_name"])
        target = Path(str(operation["target_manifest_path"]))
        original_fingerprint = str(
            operation["original_file_fingerprint"]
        )
        applied_fingerprint = str(
            operation["applied_file_fingerprint"]
        )
        try:
            current_fingerprint = file_fingerprint(target)
        except OSError:
            failures.append(f"{scene_name}:target_unreadable")
            continue
        if hmac.compare_digest(
            current_fingerprint,
            original_fingerprint,
        ):
            continue
        if not hmac.compare_digest(
            current_fingerprint,
            applied_fingerprint,
        ):
            failures.append(f"{scene_name}:unexpected_target_content")
            continue
        original_bytes = decode_base64(
            require_text(
                operation["original_file_content_base64"],
                name=f"rollback {scene_name} original bytes",
                maximum_length=1_000_000,
            ),
            name=f"rollback {scene_name} original bytes",
        )
        try:
            _replace_content_atomically(
                target=target,
                content=original_bytes,
            )
            if not hmac.compare_digest(
                file_fingerprint(target),
                original_fingerprint,
            ):
                failures.append(f"{scene_name}:restore_mismatch")
        except OSError:
            failures.append(f"{scene_name}:restore_failed")
    return not failures, failures


def _consumption_payload(
    *,
    approval: Mapping[str, Any],
    plan: Mapping[str, Any],
    transaction_id: str,
    transaction_dir: Path,
    intent: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": _CONSUMPTION_SCHEMA_VERSION,
        "approval_fingerprint": approval["approval_fingerprint"],
        "plan_fingerprint": plan["plan_fingerprint"],
        "transaction_id": transaction_id,
        "transaction_dir": str(transaction_dir),
        "intent_fingerprint": intent["intent_fingerprint"],
        "consumed_at": format_utc(now),
    }
    payload["consumption_fingerprint"] = fingerprint_bytes(payload)
    _validate_consumption(payload)
    return payload


def _load_consumption(path: Path) -> dict[str, Any]:
    _target, payload = _load_json_object(
        path,
        name="configuration approval consumption",
    )
    _validate_consumption(payload)
    return payload


def _assert_consumption_identity(
    *,
    consumption: Mapping[str, Any],
    approval: Mapping[str, Any],
    plan: Mapping[str, Any],
    transaction_id: str,
) -> None:
    expected = {
        "approval_fingerprint": approval["approval_fingerprint"],
        "plan_fingerprint": plan["plan_fingerprint"],
        "transaction_id": transaction_id,
    }
    for field_name, expected_value in expected.items():
        if consumption.get(field_name) != expected_value:
            raise WriteModelConfigurationApplicationBlockedError(
                "existing approval consumption identity does not match"
            )


def _probe_receipt_parent(path: Path) -> None:
    if path.exists():
        raise FileExistsError(
            f"application receipt already exists: {path}"
        )
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
        raise WriteModelConfigurationApplicationReceiptError(
            "configuration result is recorded internally but the "
            "requested receipt could not be exported"
        ) from exc


def _recover_interrupted_transaction(
    *,
    plan_path: Path,
    plan: Mapping[str, Any],
    approval_path: Path,
    approval: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    consumption_path: Path,
    consumption: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
    snapshot_builder: RoutingSnapshotBuilder,
    internal_receipt_path: Path,
    external_receipt_path: Path,
    now: datetime,
) -> dict[str, Any]:
    restored, _failures = _restore_operations(operations)
    post_snapshot: Mapping[str, Any] | None = None
    if restored:
        try:
            post_snapshot = snapshot_builder()
            _verify_rolled_back_snapshot(
                source_snapshot=source_snapshot,
                rolled_back_snapshot=post_snapshot,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            restored = False
            post_snapshot = None
    receipt = _build_receipt(
        status="rolled_back" if restored else "rollback_failed",
        plan_path=plan_path,
        plan=plan,
        approval_path=approval_path,
        approval=approval,
        source_snapshot=source_snapshot,
        post_snapshot=post_snapshot,
        consumption_path=consumption_path,
        consumption=consumption,
        operations=operations,
        failure_stage="interrupted_transaction_recovery",
        error_type="InterruptedConfigurationApplication",
        rollback_exact=restored,
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
    plan_path: Path,
    plan: Mapping[str, Any],
    approval_path: Path,
    approval: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    config_root: Path,
    consumption_path: Path,
    consumption: Mapping[str, Any],
    snapshot_builder: RoutingSnapshotBuilder,
    external_receipt_path: Path,
    now: datetime,
) -> dict[str, Any]:
    transaction_dir = absolute_path(
        require_text(
            consumption.get("transaction_dir"),
            name="consumption.transaction_dir",
            maximum_length=32_768,
        ),
        name="consumption.transaction_dir",
    )
    internal_receipt_path = transaction_dir / "receipt.json"
    if internal_receipt_path.is_file():
        _path, receipt = (
            load_write_model_configuration_application_receipt(
                internal_receipt_path
            )
        )
        if (
            receipt.get("transaction_id")
            != consumption.get("transaction_id")
        ):
            raise ValueError("internal receipt transaction mismatch")
        _persist_immutable(receipt, external_receipt_path)
        return receipt
    intent_path = transaction_dir / "intent.json"
    if intent_path.is_file():
        _intent_path, intent = _load_json_object(
            intent_path,
            name="configuration application intent",
        )
        validate_write_model_configuration_application_intent(intent)
        if (
            intent.get("intent_fingerprint")
            != consumption.get("intent_fingerprint")
        ):
            raise ValueError("transaction intent identity mismatch")
        raw_operations = intent.get("operations")
        assert isinstance(raw_operations, list)
        operations = [
            _validate_intent_operation(
                operation,
                name=f"intent.operations[{index}]",
            )
            for index, operation in enumerate(raw_operations)
        ]
    else:
        operations = _build_operations(
            plan=plan,
            config_root=config_root,
        )
    return _recover_interrupted_transaction(
        plan_path=plan_path,
        plan=plan,
        approval_path=approval_path,
        approval=approval,
        source_snapshot=source_snapshot,
        consumption_path=consumption_path,
        consumption=consumption,
        operations=operations,
        snapshot_builder=snapshot_builder,
        internal_receipt_path=internal_receipt_path,
        external_receipt_path=external_receipt_path,
        now=now,
    )


def apply_write_model_configuration_preapplication_plan(
    *,
    plan_path: str | Path,
    approval_path: str | Path,
    workspace_dir: str | Path,
    receipt_output_path: str | Path,
    snapshot_builder: RoutingSnapshotBuilder,
    now: datetime,
) -> dict[str, Any]:
    """Consume one approval and transactionally apply its exact plan."""

    current_time = _normalize_now(now)
    resolved_plan_path, plan = (
        load_write_model_configuration_preapplication_plan(plan_path)
    )
    resolved_approval_path, approval = (
        load_write_model_configuration_change_approval(approval_path)
    )
    _source_snapshot_path, source_snapshot = _load_source_snapshot(plan)
    config_root = _configuration_root(source_snapshot)
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
    external_receipt_path = (
        Path(receipt_output_path).expanduser().resolve()
    )
    consumption_path = _consumption_path(
        approval_path=resolved_approval_path,
        approval_fingerprint=approval_fingerprint,
    )
    application_lock = (
        create_write_model_configuration_transaction_lock(config_root)
    )
    try:
        application_lock.acquire()
    except RuntimeError as exc:
        raise WriteModelConfigurationApplicationBusyError(
            "another configuration application currently holds the lock"
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
                plan_path=resolved_plan_path,
                plan=plan,
                approval_path=resolved_approval_path,
                approval=approval,
                source_snapshot=source_snapshot,
                config_root=config_root,
                consumption_path=consumption_path,
                consumption=consumption,
                snapshot_builder=snapshot_builder,
                external_receipt_path=external_receipt_path,
                now=current_time,
            )
        _probe_receipt_parent(external_receipt_path)
        current_snapshot = dict(snapshot_builder())
        verification = (
            verify_write_model_configuration_preapplication_plan(
                plan,
                current_routing_snapshot=current_snapshot,
                expected_approval_path=resolved_approval_path,
                now=current_time,
            )
        )
        if verification.get("status") != "current":
            raise WriteModelConfigurationApplicationBlockedError(
                "preapplication plan is not current at application time"
            )
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
        _persist_immutable(intent, intent_path)
        for operation in operations:
            staged_files.append(
                _stage_content(
                    target=Path(
                        str(operation["target_manifest_path"])
                    ),
                    content=decode_base64(
                        require_text(
                            operation[
                                "applied_file_content_base64"
                            ],
                            name=(
                                f"applied bytes for "
                                f"{operation['scene_name']}"
                            ),
                            maximum_length=1_000_000,
                        ),
                        name=(
                            f"applied bytes for "
                            f"{operation['scene_name']}"
                        ),
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
        failure_stage = "manifest_application"
        try:
            for operation, staged in zip(
                operations,
                staged_files,
                strict=True,
            ):
                target = Path(
                    str(operation["target_manifest_path"])
                )
                if not hmac.compare_digest(
                    file_fingerprint(target),
                    str(operation["original_file_fingerprint"]),
                ):
                    raise RuntimeError(
                        "manifest changed after approval consumption"
                    )
                _replace_staged_file(staged=staged, target=target)
                if not hmac.compare_digest(
                    file_fingerprint(target),
                    str(operation["applied_file_fingerprint"]),
                ):
                    raise RuntimeError(
                        "applied manifest fingerprint mismatch"
                    )
            failure_stage = "post_application_preflight"
            applied_snapshot = dict(snapshot_builder())
            _verify_applied_snapshot(
                source_snapshot=source_snapshot,
                applied_snapshot=applied_snapshot,
                operations=operations,
            )
        except BaseException as exc:
            restored, _failures = _restore_operations(operations)
            rolled_back_snapshot: Mapping[str, Any] | None = None
            if restored:
                try:
                    rolled_back_snapshot = dict(snapshot_builder())
                    _verify_rolled_back_snapshot(
                        source_snapshot=source_snapshot,
                        rolled_back_snapshot=rolled_back_snapshot,
                    )
                except (
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ):
                    restored = False
                    rolled_back_snapshot = None
            receipt = _build_receipt(
                status=(
                    "rolled_back" if restored else "rollback_failed"
                ),
                plan_path=resolved_plan_path,
                plan=plan,
                approval_path=resolved_approval_path,
                approval=approval,
                source_snapshot=source_snapshot,
                post_snapshot=rolled_back_snapshot,
                consumption_path=consumption_path,
                consumption=consumption,
                operations=operations,
                failure_stage=failure_stage,
                error_type=type(exc).__name__,
                rollback_exact=restored,
                completed_at=current_time,
            )
            _persist_receipts(
                receipt=receipt,
                internal_receipt_path=internal_receipt_path,
                external_receipt_path=external_receipt_path,
            )
            return receipt
        receipt = _build_receipt(
            status="applied",
            plan_path=resolved_plan_path,
            plan=plan,
            approval_path=resolved_approval_path,
            approval=approval,
            source_snapshot=source_snapshot,
            post_snapshot=applied_snapshot,
            consumption_path=consumption_path,
            consumption=consumption,
            operations=operations,
            failure_stage=None,
            error_type=None,
            rollback_exact=False,
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
        application_lock.release()


def _snapshot_matches_receipt_operations(
    *,
    receipt: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> bool:
    scenes = _scene_map(snapshot)
    raw_operations = receipt.get("operations")
    assert isinstance(raw_operations, list)
    for index, raw_operation in enumerate(raw_operations):
        operation = require_mapping(
            raw_operation,
            name=f"receipt.operations[{index}]",
        )
        key = _operation_key(operation)
        scene = scenes.get(key)
        if scene is None:
            return False
        expected_model = (
            operation["applied_model_name"]
            if receipt.get("status") == "applied"
            else operation["expected_current_model_name"]
        )
        expected_fingerprint = (
            operation["applied_file_fingerprint"]
            if receipt.get("status") == "applied"
            else operation["original_file_fingerprint"]
        )
        manifest = require_mapping(
            scene.get("manifest_source"),
            name=f"scene {key[1]} manifest",
        )
        if (
            scene.get("model_name") != expected_model
            or manifest.get("default_model_name") != expected_model
            or manifest.get("fingerprint") != expected_fingerprint
        ):
            return False
    return True


def verify_write_model_configuration_application_receipt(
    receipt: Mapping[str, Any],
    *,
    current_routing_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a historical receipt against current runtime routing."""

    validate_write_model_configuration_application_receipt(receipt)
    current_fingerprint = _snapshot_fingerprint(
        current_routing_snapshot,
        name="current routing snapshot",
    )
    receipt_status = str(receipt["status"])
    expected_fingerprint = receipt.get(
        "post_operation_routing_snapshot_fingerprint"
    )
    operation_routes_match = _snapshot_matches_receipt_operations(
        receipt=receipt,
        snapshot=current_routing_snapshot,
    )
    if receipt_status == "rollback_failed":
        verification_status = "manual_recovery_required"
        full_snapshot_match = False
        operation_routes_match = False
        reason_codes = ["receipt_records_incomplete_rollback"]
    else:
        assert isinstance(expected_fingerprint, str)
        full_snapshot_match = hmac.compare_digest(
            expected_fingerprint,
            current_fingerprint,
        )
        if full_snapshot_match and operation_routes_match:
            verification_status = "current"
            reason_codes = [
                "current_runtime_snapshot_matches_application_receipt"
            ]
        else:
            verification_status = "routing_changed"
            reason_codes = []
            if not full_snapshot_match:
                reason_codes.append(
                    "full_runtime_routing_snapshot_changed"
                )
            if not operation_routes_match:
                reason_codes.append(
                    "approved_scene_manifest_routing_changed"
                )
    matches = (
        verification_status == "current"
        and full_snapshot_match
        and operation_routes_match
    )
    payload = {
        "schema_version": _VERIFICATION_SCHEMA_VERSION,
        "status": verification_status,
        "action": "stop",
        "receipt_status": receipt_status,
        "expected_configuration_state": (
            _EXPECTED_CONFIGURATION_STATES[receipt_status]
        ),
        "expected_routing_snapshot_fingerprint": expected_fingerprint,
        "current_routing_snapshot_fingerprint": current_fingerprint,
        "full_snapshot_match": full_snapshot_match,
        "changed_operation_routes_match": operation_routes_match,
        "current_routing_matches_receipt": matches,
        "eligible_for_operator_rollback_plan": (
            matches and receipt_status == "applied"
        ),
        "reason_codes": reason_codes,
        "configuration_verification_performed": True,
        "configuration_application_performed": False,
        "approval_consumed": True,
        "model_execution_performed": False,
    }
    validate_write_model_configuration_application_verification(
        payload
    )
    return payload


def validate_write_model_configuration_application_verification(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict, read-only application verification result."""

    verification = require_mapping(
        payload,
        name="configuration application verification",
    )
    _exact_fields(
        verification,
        expected=_VERIFICATION_FIELDS,
        name="configuration application verification",
    )
    if verification.get("schema_version") != _VERIFICATION_SCHEMA_VERSION:
        raise ValueError("unsupported configuration verification schema")
    status = verification.get("status")
    if status not in _VERIFICATION_STATUSES:
        raise ValueError("configuration verification status is invalid")
    if verification.get("action") != "stop":
        raise ValueError("configuration verification action is invalid")
    receipt_status = verification.get("receipt_status")
    if receipt_status not in _RECEIPT_STATUSES:
        raise ValueError(
            "configuration verification receipt status is invalid"
        )
    if verification.get("expected_configuration_state") != (
        _EXPECTED_CONFIGURATION_STATES[str(receipt_status)]
    ):
        raise ValueError(
            "configuration verification expected state is invalid"
        )
    expected_fingerprint = verification.get(
        "expected_routing_snapshot_fingerprint"
    )
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
        "eligible_for_operator_rollback_plan",
        "configuration_verification_performed",
        "configuration_application_performed",
        "approval_consumed",
        "model_execution_performed",
    ):
        if not isinstance(verification.get(field_name), bool):
            raise ValueError(
                f"configuration verification {field_name} must be boolean"
            )
    reason_codes = verification.get("reason_codes")
    if not isinstance(reason_codes, list) or not reason_codes:
        raise ValueError(
            "configuration verification reason_codes must be non-empty"
        )
    normalized_reasons = [
        require_text(
            reason,
            name=f"reason_codes[{index}]",
            maximum_length=128,
        )
        for index, reason in enumerate(reason_codes)
    ]
    if len(normalized_reasons) != len(set(normalized_reasons)):
        raise ValueError(
            "configuration verification reason_codes contain duplicates"
        )
    full_match = verification["full_snapshot_match"]
    operation_match = verification[
        "changed_operation_routes_match"
    ]
    matches = verification["current_routing_matches_receipt"]
    expected_matches = bool(full_match and operation_match)
    if status == "current":
        if (
            expected_fingerprint is None
            or not expected_matches
            or matches is not True
        ):
            raise ValueError(
                "current configuration verification is inconsistent"
            )
    elif matches is not False:
        raise ValueError(
            "non-current configuration verification is inconsistent"
        )
    if status == "routing_changed" and expected_fingerprint is None:
        raise ValueError(
            "routing-changed verification needs an expected snapshot"
        )
    if status == "manual_recovery_required" and (
        receipt_status != "rollback_failed"
        or expected_fingerprint is not None
        or full_match is not False
        or operation_match is not False
    ):
        raise ValueError(
            "manual-recovery verification is inconsistent"
        )
    eligible = verification[
        "eligible_for_operator_rollback_plan"
    ]
    if eligible != (
        status == "current" and receipt_status == "applied"
    ):
        raise ValueError(
            "configuration rollback-plan eligibility is invalid"
        )
    if verification["configuration_verification_performed"] is not True:
        raise ValueError(
            "configuration verification evidence is invalid"
        )
    if verification["configuration_application_performed"] is not False:
        raise ValueError(
            "read-only verification cannot apply configuration"
        )
    if verification["approval_consumed"] is not True:
        raise ValueError("approval consumption evidence is invalid")
    if verification["model_execution_performed"] is not False:
        raise ValueError("model execution evidence is invalid")


def format_write_model_configuration_application_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format one read-only application verification result."""

    validate_write_model_configuration_application_verification(
        payload
    )
    return (
        "",
        "=" * 60,
        "Write model configuration application verification",
        f"  Status       : {payload['status']}",
        f"  Receipt      : {payload['receipt_status']}",
        f"  Full snapshot: {payload['full_snapshot_match']}",
        (
            "  Changed routes: "
            f"{payload['changed_operation_routes_match']}"
        ),
        (
            "  Rollback plan: "
            f"{payload['eligible_for_operator_rollback_plan']}"
        ),
        "  Configuration: unchanged by verification",
        "  Model calls  : none",
        "=" * 60,
    )


def format_write_model_configuration_application_receipt_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact operator-facing application receipt."""

    validate_write_model_configuration_application_receipt(payload)
    return (
        "",
        "=" * 60,
        "Write model configuration application",
        f"  Status      : {payload['status']}",
        f"  Action      : {payload['action']}",
        f"  Transaction : {payload['transaction_id']}",
        f"  Scenes      : {len(payload['operations'])}",
        f"  Rollback    : {payload['rollback_exact']}",
        "  Approval    : consumed exactly once",
        "  Model calls : none",
        "=" * 60,
    )


__all__ = [
    "RoutingSnapshotBuilder",
    "WriteModelConfigurationApplicationBlockedError",
    "WriteModelConfigurationApplicationBusyError",
    "WriteModelConfigurationApplicationReceiptError",
    "apply_write_model_configuration_preapplication_plan",
    "create_write_model_configuration_transaction_lock",
    "format_write_model_configuration_application_receipt_report",
    "format_write_model_configuration_application_verification_report",
    "load_write_model_configuration_application_receipt",
    "persist_write_model_configuration_application_receipt",
    "validate_write_model_configuration_application_intent",
    "validate_write_model_configuration_application_receipt",
    "validate_write_model_configuration_application_verification",
    "verify_write_model_configuration_application_receipt",
]
