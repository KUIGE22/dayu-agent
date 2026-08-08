"""Independently verify one manual write-routing recovery receipt."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import unicodedata
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dayu.contracts.model_config import ModelConfigJsonValue
from dayu.services._write_artifact_utils import (
    bytes_fingerprint,
    canonical_json_bytes,
    require_mapping,
)
from dayu.services.write_model_configuration_application import (
    create_write_model_configuration_transaction_lock,
)
from dayu.services.write_model_configuration_manual_recovery import (
    validate_write_model_configuration_manual_recovery_approval,
    validate_write_model_configuration_manual_recovery_approval_request,
    validate_write_model_configuration_manual_recovery_plan,
    validate_write_model_configuration_manual_recovery_selection_request,
)
from dayu.services.write_model_configuration_manual_recovery_application import (
    validate_write_model_configuration_manual_recovery_consumption,
    validate_write_model_configuration_manual_recovery_intent,
    validate_write_model_configuration_manual_recovery_receipt,
)
from dayu.services.write_model_configuration_preapplication import (
    validate_write_scene_model_routing_snapshot,
)
from dayu.services.write_model_configuration_rollback_application import (
    assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current,
    validate_write_model_configuration_manual_recovery_clearance_revocation_lineage,
    validate_write_model_configuration_manual_recovery_evidence,
)

_VERIFICATION_SCHEMA_VERSION_V1 = "write_model_configuration_manual_recovery_verification_v1"
_VERIFICATION_SCHEMA_VERSION_V2 = "write_model_configuration_manual_recovery_verification_v2"
_VERIFICATION_STATUSES = {
    "current",
    "routing_changed",
    "starting_state_current",
    "starting_state_changed",
    "manual_recovery_required",
}
_RECEIPT_STATUSES = {
    "recovered",
    "starting_state_restored",
    "recovery_failed",
}
_EXPECTED_CONFIGURATION_STATES = {
    "recovered": "selected",
    "starting_state_restored": "starting",
    "recovery_failed": "unproven",
}
_SOURCE_FIELDS = {
    "path",
    "file_fingerprint",
    "content_fingerprint",
}
_VERIFICATION_FIELDS_V1 = {
    "schema_version",
    "status",
    "action",
    "receipt_status",
    "selected_state",
    "transaction_id",
    "source_chain_valid",
    "write_ahead_intent_valid",
    "expected_configuration_state",
    "expected_routing_snapshot_fingerprint",
    "current_routing_snapshot_fingerprint",
    "full_snapshot_checked",
    "full_snapshot_match",
    "target_bytes_stable",
    "target_bytes_match_receipt",
    "current_configuration_matches_receipt",
    "eligible_for_normal_write_preflight",
    "new_manual_recovery_evidence_required",
    "manual_intervention_required",
    "reason_codes",
    "configuration_verification_performed",
    "configuration_recovery_performed",
    "approval_consumed",
    "approval_consumed_by_verification",
    "model_execution_performed",
}
_VERIFICATION_FIELDS_V2 = _VERIFICATION_FIELDS_V1 | {"clearance_revocation_lineage"}
_MODEL_POINTER = "/model/default_name"

PayloadValidator = Callable[[Mapping[str, Any]], None]
ContentFingerprint = Callable[[Mapping[str, Any]], str]
RoutingSnapshotBuilder = Callable[[], Mapping[str, Any]]


class WriteModelConfigurationManualRecoveryVerificationBlockedError(ValueError):
    """Raised when immutable recovery evidence cannot be verified."""


class WriteModelConfigurationManualRecoveryVerificationBusyError(RuntimeError):
    """Raised when another configuration transaction owns the lock."""


def _exact_fields(
    payload: Mapping[str, Any],
    *,
    expected: set[str],
    name: str,
) -> None:
    actual = set(payload)
    if actual != expected:
        raise ValueError(
            f"{name} fields are invalid; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


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


def _assert_same_clearance_revocation_lineage(
    expected: Mapping[str, Any] | None,
    actual: Mapping[str, Any] | None,
    *,
    name: str,
) -> None:
    if expected is None and actual is None:
        return
    if (
        expected is None
        or actual is None
        or not hmac.compare_digest(
            canonical_json_bytes(expected),
            canonical_json_bytes(actual),
        )
    ):
        raise (
            WriteModelConfigurationManualRecoveryVerificationBlockedError(
                f"{name} clearance revocation lineage changed"
            )
        )


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


def _artifact_path(value: object, *, name: str) -> Path:
    raw_value: object = str(value) if isinstance(value, Path) else value
    text = _required_text(
        raw_value,
        name=name,
        maximum_length=32_768,
    )
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return Path(os.path.abspath(path))


def _payload_fingerprint(payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"sha256:{digest}"


def _validated_fingerprint(value: object, *, name: str) -> str:
    text = _required_text(value, name=name, maximum_length=80).lower()
    digest = text.removeprefix("sha256:")
    if (
        not text.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} is not a SHA-256 fingerprint")
    return text


def _parse_utc(value: object, *, name: str) -> datetime:
    text = _required_text(value, name=name, maximum_length=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _validate_source(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> dict[str, str]:
    source = require_mapping(value, name=name)
    _exact_fields(source, expected=_SOURCE_FIELDS, name=name)
    return {
        "path": str(_artifact_path(source.get("path"), name=f"{name}.path")),
        "file_fingerprint": _validated_fingerprint(
            source.get("file_fingerprint"),
            name=f"{name}.file_fingerprint",
        ),
        "content_fingerprint": _validated_fingerprint(
            source.get("content_fingerprint"),
            name=f"{name}.content_fingerprint",
        ),
    }


def _json_object_from_bytes(value: bytes, *, name: str) -> dict[str, Any]:
    try:
        payload = json.loads(value.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} is not UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must contain one JSON object")
    return payload


def _load_artifact(
    path: str | Path,
    *,
    name: str,
    validator: PayloadValidator,
) -> tuple[Path, dict[str, Any]]:
    target = _artifact_path(path, name=f"{name}.path")
    if target.is_symlink() or not target.is_file():
        raise ValueError(f"{name} is unavailable")
    first = target.read_bytes()
    payload = _json_object_from_bytes(first, name=name)
    validator(payload)
    if target.read_bytes() != first:
        raise ValueError(f"{name} changed while being read")
    return target, payload


def _load_source_artifact(
    value: ModelConfigJsonValue,
    *,
    name: str,
    validator: PayloadValidator,
    content_fingerprint: ContentFingerprint,
) -> tuple[dict[str, str], Path, dict[str, Any]]:
    source = _validate_source(value, name=name)
    path = _artifact_path(source["path"], name=f"{name}.path")
    if path.is_symlink() or not path.is_file():
        raise WriteModelConfigurationManualRecoveryVerificationBlockedError(f"{name} is unavailable")
    try:
        first = path.read_bytes()
        if not hmac.compare_digest(
            bytes_fingerprint(first),
            source["file_fingerprint"],
        ):
            raise (WriteModelConfigurationManualRecoveryVerificationBlockedError(f"{name} file changed"))
        payload = _json_object_from_bytes(first, name=name)
        validator(payload)
        actual_content_fingerprint = _validated_fingerprint(
            content_fingerprint(payload),
            name=f"{name}.content_fingerprint",
        )
        if not hmac.compare_digest(
            actual_content_fingerprint,
            source["content_fingerprint"],
        ):
            raise (WriteModelConfigurationManualRecoveryVerificationBlockedError(f"{name} content changed"))
        if path.read_bytes() != first:
            raise (
                WriteModelConfigurationManualRecoveryVerificationBlockedError(f"{name} changed while being verified")
            )
    except WriteModelConfigurationManualRecoveryVerificationBlockedError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise WriteModelConfigurationManualRecoveryVerificationBlockedError(f"{name} is invalid") from exc
    return source, path, payload


def _field_fingerprint(field_name: str) -> ContentFingerprint:
    def _read(payload: Mapping[str, Any]) -> str:
        return _required_text(
            payload.get(field_name),
            name=field_name,
            maximum_length=80,
        )

    return _read


def _request_fingerprint(payload: Mapping[str, Any]) -> str:
    return _payload_fingerprint(payload)


def _assert_equal(
    actual: object,
    expected: object,
    *,
    message: str,
) -> None:
    if actual != expected:
        raise WriteModelConfigurationManualRecoveryVerificationBlockedError(message)


def _operation_map(
    payload: Mapping[str, Any],
    *,
    name: str,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    raw_operations = payload.get("operations")
    if not isinstance(raw_operations, list) or not raw_operations:
        raise WriteModelConfigurationManualRecoveryVerificationBlockedError(f"{name} operations are unavailable")
    operations: dict[tuple[str, str], Mapping[str, Any]] = {}
    for index, raw_operation in enumerate(raw_operations):
        operation = require_mapping(
            raw_operation,
            name=f"{name}.operations[{index}]",
        )
        key = (
            _required_text(
                operation.get("role"),
                name=f"{name}.operations[{index}].role",
                maximum_length=32,
            ),
            _required_text(
                operation.get("scene_name"),
                name=f"{name}.operations[{index}].scene_name",
                maximum_length=128,
            ),
        )
        if key in operations:
            raise (
                WriteModelConfigurationManualRecoveryVerificationBlockedError(f"{name} operations contain duplicates")
            )
        operations[key] = operation
    return operations


def _assert_operation_chain(
    *,
    receipt: Mapping[str, Any],
    plan: Mapping[str, Any],
    evidence: Mapping[str, Any],
    intent: Mapping[str, Any] | None,
) -> None:
    receipt_operations = _operation_map(receipt, name="receipt")
    plan_operations = _operation_map(plan, name="plan")
    evidence_operations = _operation_map(evidence, name="evidence")
    intent_operations = None if intent is None else _operation_map(intent, name="intent")
    keys = set(plan_operations)
    if (
        set(receipt_operations) != keys
        or set(evidence_operations) != keys
        or (intent_operations is not None and set(intent_operations) != keys)
    ):
        raise WriteModelConfigurationManualRecoveryVerificationBlockedError(
            "manual recovery operation identities changed"
        )

    selected_state = str(plan["selected_state"])
    for key in keys:
        plan_operation = plan_operations[key]
        evidence_operation = evidence_operations[key]
        receipt_operation = receipt_operations[key]
        selected_prefix = "expected_applied" if selected_state == "applied" else "expected_preapplication"
        selected_content_field = (
            "applied_file_content_base64" if selected_state == "applied" else "preapplication_file_content_base64"
        )
        expected_selected_fingerprint = evidence_operation[f"{selected_prefix}_file_fingerprint"]
        expected_selected_model = evidence_operation[f"{selected_prefix}_model_name"]
        expected_starting_fingerprint = evidence_operation.get("observed_file_fingerprint")
        common_identity = {
            "role": key[0],
            "scene_name": key[1],
            "target_manifest_path": evidence_operation["target_manifest_path"],
            "json_pointer": _MODEL_POINTER,
            "observed_state": evidence_operation["observed_state"],
            "selected_model_name": expected_selected_model,
        }
        for field_name, expected_value in common_identity.items():
            _assert_equal(
                plan_operation.get(field_name),
                expected_value,
                message=(f"manual recovery plan operation {key} changed"),
            )
            _assert_equal(
                receipt_operation.get(field_name),
                expected_value,
                message=(f"manual recovery receipt operation {key} changed"),
            )
        _assert_equal(
            plan_operation.get("expected_current_file_fingerprint"),
            expected_starting_fingerprint,
            message=f"manual recovery starting identity {key} changed",
        )
        _assert_equal(
            plan_operation.get("selected_file_fingerprint"),
            expected_selected_fingerprint,
            message=f"manual recovery selected identity {key} changed",
        )
        _assert_equal(
            plan_operation.get("selected_file_content_base64"),
            evidence_operation[selected_content_field],
            message=f"manual recovery selected bytes {key} changed",
        )
        _assert_equal(
            receipt_operation.get("starting_file_fingerprint"),
            expected_starting_fingerprint,
            message=f"manual recovery receipt starting bytes {key} changed",
        )
        _assert_equal(
            receipt_operation.get("selected_file_fingerprint"),
            expected_selected_fingerprint,
            message=f"manual recovery receipt selected bytes {key} changed",
        )
        if intent_operations is None:
            continue
        intent_operation = intent_operations[key]
        for field_name, expected_value in common_identity.items():
            _assert_equal(
                intent_operation.get(field_name),
                expected_value,
                message=f"manual recovery intent operation {key} changed",
            )
        for field_name, expected_value in (
            (
                "starting_file_fingerprint",
                expected_starting_fingerprint,
            ),
            (
                "selected_file_fingerprint",
                expected_selected_fingerprint,
            ),
            (
                "selected_file_content_base64",
                evidence_operation[selected_content_field],
            ),
        ):
            _assert_equal(
                intent_operation.get(field_name),
                expected_value,
                message=f"manual recovery intent bytes {key} changed",
            )


def _transaction_id(
    *,
    approval_fingerprint: str,
    plan_fingerprint: str,
) -> str:
    material = (f"{approval_fingerprint}\n{plan_fingerprint}\nmanual-recovery-v1").encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _assert_source_chain(
    receipt: Mapping[str, Any],
) -> bool:
    plan_source, _plan_path, plan = _load_source_artifact(
        receipt.get("source_manual_recovery_plan"),
        name="source manual recovery plan",
        validator=validate_write_model_configuration_manual_recovery_plan,
        content_fingerprint=_field_fingerprint("plan_fingerprint"),
    )
    _approval_source, _approval_path, approval = _load_source_artifact(
        receipt.get("source_manual_recovery_approval"),
        name="source manual recovery approval",
        validator=(validate_write_model_configuration_manual_recovery_approval),
        content_fingerprint=_field_fingerprint("approval_fingerprint"),
    )
    evidence_source, _evidence_path, evidence = _load_source_artifact(
        receipt.get("source_manual_recovery_evidence"),
        name="source manual recovery evidence",
        validator=(validate_write_model_configuration_manual_recovery_evidence),
        content_fingerprint=_field_fingerprint("evidence_fingerprint"),
    )
    _selection_source, _selection_path, selection = _load_source_artifact(
        plan.get("source_selection_request"),
        name="source manual recovery selection",
        validator=(validate_write_model_configuration_manual_recovery_selection_request),
        content_fingerprint=_request_fingerprint,
    )
    (
        approval_request_source,
        _approval_request_path,
        approval_request,
    ) = _load_source_artifact(
        approval.get("approval_request_source"),
        name="source manual recovery approval request",
        validator=(validate_write_model_configuration_manual_recovery_approval_request),
        content_fingerprint=_request_fingerprint,
    )
    consumption_source, _consumption_path, consumption = _load_source_artifact(
        receipt.get("approval_consumption"),
        name="manual recovery approval consumption",
        validator=(validate_write_model_configuration_manual_recovery_consumption),
        content_fingerprint=_field_fingerprint("consumption_fingerprint"),
    )
    receipt_lineage = _clearance_revocation_lineage(receipt)
    for artifact_name, artifact in (
        ("manual recovery evidence", evidence),
        ("manual recovery selection", selection),
        ("manual recovery plan", plan),
        ("manual recovery approval request", approval_request),
        ("manual recovery approval", approval),
        ("manual recovery approval consumption", consumption),
    ):
        _assert_same_clearance_revocation_lineage(
            receipt_lineage,
            _clearance_revocation_lineage(artifact),
            name=artifact_name,
        )
    if receipt_lineage is not None:
        try:
            assert_write_model_configuration_manual_recovery_clearance_revocation_lineage_current(receipt_lineage)
        except (
            FileNotFoundError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise (
                WriteModelConfigurationManualRecoveryVerificationBlockedError(
                    "manual recovery clearance revocation lineage is not current"
                )
            ) from exc

    _assert_equal(
        _validate_source(
            approval.get("manual_recovery_plan_source"),
            name="approval manual recovery plan source",
        ),
        plan_source,
        message="manual recovery approval is bound to another plan",
    )
    _assert_equal(
        _validate_source(
            plan.get("source_manual_recovery_evidence"),
            name="plan manual recovery evidence source",
        ),
        evidence_source,
        message="manual recovery plan is bound to another evidence file",
    )
    _assert_equal(
        require_mapping(
            approval.get("manual_recovery_plan"),
            name="approval embedded manual recovery plan",
        ),
        plan,
        message="embedded manual recovery plan changed",
    )
    _assert_equal(
        _validate_source(
            approval.get("approval_request_source"),
            name="approval request source",
        ),
        approval_request_source,
        message="manual recovery approval request source changed",
    )
    _assert_equal(
        receipt.get("ticker"),
        plan.get("ticker"),
        message="manual recovery receipt ticker changed",
    )
    _assert_equal(
        receipt.get("selected_state"),
        plan.get("selected_state"),
        message="manual recovery selected state changed",
    )
    _assert_equal(
        receipt.get("expected_selected_routing_snapshot_fingerprint"),
        plan.get("expected_selected_routing_snapshot_fingerprint"),
        message="manual recovery expected routing identity changed",
    )
    _assert_equal(
        selection.get("selected_state"),
        plan.get("selected_state"),
        message="manual recovery selection state changed",
    )
    for field_name in (
        "selected_by",
        "selection_reference",
        "selection_reason",
    ):
        _assert_equal(
            selection.get(field_name),
            plan.get(field_name),
            message=f"manual recovery selection {field_name} changed",
        )
    _assert_equal(
        _parse_utc(
            selection.get("selected_at"),
            name="selection.selected_at",
        ),
        _parse_utc(
            plan.get("selected_at"),
            name="plan.selected_at",
        ),
        message="manual recovery selection selected_at changed",
    )
    _assert_equal(
        selection.get("manual_recovery_evidence_fingerprint"),
        evidence.get("evidence_fingerprint"),
        message="manual recovery selection evidence identity changed",
    )
    _assert_equal(
        selection.get("source_transaction_id"),
        evidence.get("transaction_id"),
        message="manual recovery selection transaction changed",
    )
    approval_request_fingerprint = _request_fingerprint(approval_request)
    _assert_equal(
        approval.get("approval_request_fingerprint"),
        approval_request_fingerprint,
        message="manual recovery approval request changed",
    )
    for field_name in (
        "approved_by",
        "approval_reference",
        "approval_reason",
        "manual_recovery_plan_fingerprint",
        "manual_recovery_evidence_fingerprint",
        "selected_state",
    ):
        _assert_equal(
            approval_request.get(field_name),
            approval.get(field_name),
            message=f"manual recovery approval {field_name} changed",
        )
    for field_name in ("approved_at", "expires_at"):
        _assert_equal(
            _parse_utc(
                approval_request.get(field_name),
                name=f"approval_request.{field_name}",
            ),
            _parse_utc(
                approval.get(field_name),
                name=f"approval.{field_name}",
            ),
            message=f"manual recovery approval {field_name} changed",
        )
    _assert_equal(
        approval.get("manual_recovery_plan_fingerprint"),
        plan.get("plan_fingerprint"),
        message="manual recovery approval plan identity changed",
    )
    _assert_equal(
        approval.get("manual_recovery_evidence_fingerprint"),
        evidence.get("evidence_fingerprint"),
        message="manual recovery approval evidence identity changed",
    )

    expected_transaction_id = _transaction_id(
        approval_fingerprint=str(approval["approval_fingerprint"]),
        plan_fingerprint=str(plan["plan_fingerprint"]),
    )
    _assert_equal(
        receipt.get("transaction_id"),
        expected_transaction_id,
        message="manual recovery transaction identity changed",
    )
    expected_consumption_identity = {
        "manual_recovery_approval_fingerprint": approval["approval_fingerprint"],
        "manual_recovery_plan_fingerprint": plan["plan_fingerprint"],
        "manual_recovery_evidence_fingerprint": evidence["evidence_fingerprint"],
        "transaction_id": expected_transaction_id,
    }
    for field_name, expected_value in expected_consumption_identity.items():
        _assert_equal(
            consumption.get(field_name),
            expected_value,
            message=f"manual recovery consumption {field_name} changed",
        )
    consumed_at = _parse_utc(
        consumption.get("consumed_at"),
        name="consumption.consumed_at",
    )
    approved_at = _parse_utc(
        approval.get("approved_at"),
        name="approval.approved_at",
    )
    expires_at = _parse_utc(
        approval.get("expires_at"),
        name="approval.expires_at",
    )
    completed_at = _parse_utc(
        receipt.get("completed_at"),
        name="receipt.completed_at",
    )
    if not (approved_at <= consumed_at < expires_at and completed_at >= consumed_at):
        raise WriteModelConfigurationManualRecoveryVerificationBlockedError(
            "manual recovery transaction timestamps are inconsistent"
        )

    intent: dict[str, Any] | None = None
    intent_source_value = receipt.get("write_ahead_intent")
    if intent_source_value is not None:
        intent_source, intent_path, intent = _load_source_artifact(
            intent_source_value,
            name="manual recovery write-ahead intent",
            validator=(validate_write_model_configuration_manual_recovery_intent),
            content_fingerprint=_field_fingerprint("intent_fingerprint"),
        )
        expected_intent_path = (
            _artifact_path(
                consumption.get("transaction_dir"),
                name="consumption.transaction_dir",
            )
            / "intent.json"
        )
        _assert_equal(
            intent_path,
            expected_intent_path,
            message="manual recovery intent path changed",
        )
        _assert_equal(
            _validate_source(
                intent_source_value,
                name="receipt intent source",
            ),
            intent_source,
            message="manual recovery intent source changed",
        )
        expected_intent_identity = {
            "transaction_id": expected_transaction_id,
            "ticker": plan["ticker"],
            "selected_state": plan["selected_state"],
            "manual_recovery_plan_fingerprint": plan["plan_fingerprint"],
            "manual_recovery_approval_fingerprint": approval["approval_fingerprint"],
            "manual_recovery_evidence_fingerprint": evidence["evidence_fingerprint"],
            "expected_selected_routing_snapshot_fingerprint": plan["expected_selected_routing_snapshot_fingerprint"],
            "intent_fingerprint": consumption["intent_fingerprint"],
        }
        for field_name, expected_value in expected_intent_identity.items():
            _assert_equal(
                intent.get(field_name),
                expected_value,
                message=f"manual recovery intent {field_name} changed",
            )
        _assert_same_clearance_revocation_lineage(
            receipt_lineage,
            _clearance_revocation_lineage(intent),
            name="manual recovery write-ahead intent",
        )
        if (
            _parse_utc(
                intent.get("created_at"),
                name="intent.created_at",
            )
            > consumed_at
        ):
            raise (
                WriteModelConfigurationManualRecoveryVerificationBlockedError(
                    "manual recovery intent postdates consumption"
                )
            )
    _assert_operation_chain(
        receipt=receipt,
        plan=plan,
        evidence=evidence,
        intent=intent,
    )
    _assert_equal(
        _validate_source(
            receipt.get("approval_consumption"),
            name="receipt approval consumption",
        ),
        consumption_source,
        message="manual recovery consumption source changed",
    )
    return intent is not None


def _observe_targets(
    *,
    receipt: Mapping[str, Any],
    config_root: Path,
) -> tuple[tuple[str, str, str | None], ...]:
    manifest_root = config_root / "prompts" / "manifests"
    if manifest_root.is_symlink():
        raise WriteModelConfigurationManualRecoveryVerificationBlockedError(
            "manual recovery manifest root must not be a symlink"
        )
    operations = _operation_map(receipt, name="receipt")
    observations: list[tuple[str, str, str | None]] = []
    for (role, scene_name), operation in sorted(operations.items()):
        target = _artifact_path(
            operation.get("target_manifest_path"),
            name=f"receipt target for {scene_name}",
        )
        if target.parent != manifest_root or target.name != f"{scene_name}.json":
            raise (
                WriteModelConfigurationManualRecoveryVerificationBlockedError(
                    f"manual recovery target for {scene_name!r} is unsafe"
                )
            )
        if target.is_symlink():
            observations.append((role, scene_name, None))
            continue
        try:
            content = target.read_bytes()
        except OSError:
            observations.append((role, scene_name, None))
            continue
        observations.append((role, scene_name, bytes_fingerprint(content)))
    return tuple(observations)


def _target_bytes_match_receipt(
    *,
    receipt: Mapping[str, Any],
    observations: tuple[tuple[str, str, str | None], ...],
) -> bool:
    operations = _operation_map(receipt, name="receipt")
    receipt_status = str(receipt["status"])
    for role, scene_name, current_fingerprint in observations:
        operation = operations[(role, scene_name)]
        if receipt_status == "recovered":
            expected = operation["selected_file_fingerprint"]
        elif receipt_status == "starting_state_restored":
            expected = operation["starting_file_fingerprint"]
        else:
            expected = operation.get("final_file_fingerprint")
        if (
            current_fingerprint is None
            or expected is None
            or not hmac.compare_digest(
                current_fingerprint,
                str(expected),
            )
        ):
            return False
    return True


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


def _verification_payload(
    *,
    receipt: Mapping[str, Any],
    write_ahead_intent_valid: bool,
    status: str,
    expected_routing_snapshot_fingerprint: str | None,
    current_routing_snapshot_fingerprint: str | None,
    full_snapshot_checked: bool,
    full_snapshot_match: bool | None,
    target_bytes_stable: bool,
    target_bytes_match_receipt: bool,
    reason_codes: list[str],
) -> dict[str, Any]:
    lineage = _clearance_revocation_lineage(receipt)
    current_matches = status in {
        "current",
        "starting_state_current",
    }
    payload = {
        "schema_version": (_VERIFICATION_SCHEMA_VERSION_V2 if lineage is not None else _VERIFICATION_SCHEMA_VERSION_V1),
        "status": status,
        "action": "stop",
        "receipt_status": receipt["status"],
        "selected_state": receipt["selected_state"],
        "transaction_id": receipt["transaction_id"],
        "source_chain_valid": True,
        "write_ahead_intent_valid": write_ahead_intent_valid,
        "expected_configuration_state": (_EXPECTED_CONFIGURATION_STATES[str(receipt["status"])]),
        "expected_routing_snapshot_fingerprint": (expected_routing_snapshot_fingerprint),
        "current_routing_snapshot_fingerprint": (current_routing_snapshot_fingerprint),
        "full_snapshot_checked": full_snapshot_checked,
        "full_snapshot_match": full_snapshot_match,
        "target_bytes_stable": target_bytes_stable,
        "target_bytes_match_receipt": target_bytes_match_receipt,
        "current_configuration_matches_receipt": current_matches,
        "eligible_for_normal_write_preflight": status == "current",
        "new_manual_recovery_evidence_required": (status == "starting_state_current"),
        "manual_intervention_required": status
        in {
            "routing_changed",
            "starting_state_changed",
            "manual_recovery_required",
        },
        "reason_codes": reason_codes,
        "configuration_verification_performed": True,
        "configuration_recovery_performed": False,
        "approval_consumed": True,
        "approval_consumed_by_verification": False,
        "model_execution_performed": False,
    }
    if lineage is not None:
        payload["clearance_revocation_lineage"] = dict(lineage)
    validate_write_model_configuration_manual_recovery_verification(payload)
    return payload


def verify_write_model_configuration_manual_recovery_receipt(
    *,
    manual_recovery_receipt_path: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    snapshot_builder: RoutingSnapshotBuilder | None,
    configuration_transaction_lock_held: bool = False,
) -> dict[str, Any]:
    """Verify immutable evidence and current bytes without mutation."""

    if not isinstance(configuration_transaction_lock_held, bool):
        raise TypeError("configuration_transaction_lock_held must be boolean")
    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    resolved_config_root = Path(config_root).expanduser().resolve()
    transaction_lock = None
    if not configuration_transaction_lock_held:
        transaction_lock = create_write_model_configuration_transaction_lock(resolved_config_root)
        try:
            transaction_lock.acquire()
        except RuntimeError as exc:
            raise (
                WriteModelConfigurationManualRecoveryVerificationBusyError(
                    "another write-model configuration transaction holds the lock"
                )
            ) from exc
    try:
        _receipt_path, receipt = _load_artifact(
            manual_recovery_receipt_path,
            name="manual recovery receipt",
            validator=(validate_write_model_configuration_manual_recovery_receipt),
        )
        if receipt.get("ticker") != normalized_ticker:
            raise (
                WriteModelConfigurationManualRecoveryVerificationBlockedError(
                    "manual recovery receipt ticker does not match the command"
                )
            )
        write_ahead_intent_valid = _assert_source_chain(receipt)
        first_observation = _observe_targets(
            receipt=receipt,
            config_root=resolved_config_root,
        )
        second_observation = _observe_targets(
            receipt=receipt,
            config_root=resolved_config_root,
        )
        target_bytes_stable = first_observation == second_observation
        target_bytes_match = target_bytes_stable and _target_bytes_match_receipt(
            receipt=receipt,
            observations=second_observation,
        )
        receipt_status = str(receipt["status"])
        expected_snapshot: str | None = None
        current_snapshot: str | None = None
        snapshot_checked = False
        snapshot_matches: bool | None = None

        if receipt_status == "recovered":
            expected_snapshot = _validated_fingerprint(
                receipt.get("expected_selected_routing_snapshot_fingerprint"),
                name="expected_selected_routing_snapshot_fingerprint",
            )
            if target_bytes_match:
                if snapshot_builder is None:
                    raise (
                        WriteModelConfigurationManualRecoveryVerificationBlockedError(
                            "recovered receipt verification requires a fresh routing snapshot"
                        )
                    )
                try:
                    current_snapshot_payload = dict(snapshot_builder())
                    current_snapshot = _snapshot_fingerprint(
                        current_snapshot_payload,
                        name="current routing snapshot",
                    )
                except (
                    FileNotFoundError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as exc:
                    raise (
                        WriteModelConfigurationManualRecoveryVerificationBlockedError(
                            "fresh manual recovery routing verification failed"
                        )
                    ) from exc
                snapshot_checked = True
                snapshot_matches = hmac.compare_digest(
                    current_snapshot,
                    expected_snapshot,
                )
                final_observation = _observe_targets(
                    receipt=receipt,
                    config_root=resolved_config_root,
                )
                target_bytes_stable = target_bytes_stable and final_observation == second_observation
                target_bytes_match = target_bytes_stable and _target_bytes_match_receipt(
                    receipt=receipt,
                    observations=final_observation,
                )
            if snapshot_checked and snapshot_matches is True and target_bytes_match:
                status = "current"
                reason_codes = ["source_chain_target_bytes_and_runtime_snapshot_match"]
            else:
                status = "routing_changed"
                reason_codes = []
                if not target_bytes_stable:
                    reason_codes.append("target_bytes_changed_during_verification")
                elif not target_bytes_match:
                    reason_codes.append("selected_target_bytes_changed")
                if snapshot_checked and snapshot_matches is not True:
                    reason_codes.append("full_runtime_routing_snapshot_changed")
                if not snapshot_checked and target_bytes_match:
                    reason_codes.append("full_runtime_routing_snapshot_unavailable")
        elif receipt_status == "starting_state_restored":
            if target_bytes_match:
                status = "starting_state_current"
                reason_codes = [
                    "exact_starting_bytes_remain_current",
                    "new_manual_recovery_evidence_required",
                ]
            else:
                status = "starting_state_changed"
                reason_codes = [
                    (
                        "target_bytes_changed_during_verification"
                        if not target_bytes_stable
                        else "starting_target_bytes_changed"
                    ),
                    "manual_intervention_required",
                ]
        else:
            status = "manual_recovery_required"
            reason_codes = [
                "receipt_records_unproven_configuration_state",
                (
                    "observed_target_bytes_unchanged_since_receipt"
                    if target_bytes_match
                    else "observed_target_bytes_changed_since_receipt"
                ),
                "manual_intervention_required",
            ]

        return _verification_payload(
            receipt=receipt,
            write_ahead_intent_valid=write_ahead_intent_valid,
            status=status,
            expected_routing_snapshot_fingerprint=expected_snapshot,
            current_routing_snapshot_fingerprint=current_snapshot,
            full_snapshot_checked=snapshot_checked,
            full_snapshot_match=snapshot_matches,
            target_bytes_stable=target_bytes_stable,
            target_bytes_match_receipt=target_bytes_match,
            reason_codes=reason_codes,
        )
    finally:
        if transaction_lock is not None:
            transaction_lock.release()


def validate_write_model_configuration_manual_recovery_verification(
    payload: Mapping[str, Any],
) -> None:
    """Validate one strict read-only recovery verification result."""

    verification = require_mapping(
        payload,
        name="manual recovery verification",
    )
    schema_version = verification.get("schema_version")
    if schema_version == _VERIFICATION_SCHEMA_VERSION_V1:
        expected_fields = _VERIFICATION_FIELDS_V1
    elif schema_version == _VERIFICATION_SCHEMA_VERSION_V2:
        expected_fields = _VERIFICATION_FIELDS_V2
    else:
        raise ValueError("manual recovery verification schema is invalid")
    _exact_fields(
        verification,
        expected=expected_fields,
        name="manual recovery verification",
    )
    if schema_version == _VERIFICATION_SCHEMA_VERSION_V2:
        lineage = require_mapping(
            verification.get("clearance_revocation_lineage"),
            name="verification clearance_revocation_lineage",
        )
        validate_write_model_configuration_manual_recovery_clearance_revocation_lineage(lineage)
    status = verification.get("status")
    if status not in _VERIFICATION_STATUSES:
        raise ValueError("manual recovery verification status is invalid")
    if verification.get("action") != "stop":
        raise ValueError("manual recovery verification action is invalid")
    receipt_status = verification.get("receipt_status")
    if receipt_status not in _RECEIPT_STATUSES:
        raise ValueError("manual recovery verification receipt status is invalid")
    if verification.get("selected_state") not in {
        "applied",
        "preapplication",
    }:
        raise ValueError("manual recovery verification selected state is invalid")
    _required_text(
        verification.get("transaction_id"),
        name="transaction_id",
        maximum_length=64,
    )
    if verification.get("expected_configuration_state") != (_EXPECTED_CONFIGURATION_STATES[str(receipt_status)]):
        raise ValueError("manual recovery verification expected state is invalid")
    expected_snapshot = verification.get("expected_routing_snapshot_fingerprint")
    current_snapshot = verification.get("current_routing_snapshot_fingerprint")
    if expected_snapshot is not None:
        _validated_fingerprint(
            expected_snapshot,
            name="expected_routing_snapshot_fingerprint",
        )
    if current_snapshot is not None:
        _validated_fingerprint(
            current_snapshot,
            name="current_routing_snapshot_fingerprint",
        )
    for field_name in (
        "source_chain_valid",
        "write_ahead_intent_valid",
        "full_snapshot_checked",
        "target_bytes_stable",
        "target_bytes_match_receipt",
        "current_configuration_matches_receipt",
        "eligible_for_normal_write_preflight",
        "new_manual_recovery_evidence_required",
        "manual_intervention_required",
        "configuration_verification_performed",
        "configuration_recovery_performed",
        "approval_consumed",
        "approval_consumed_by_verification",
        "model_execution_performed",
    ):
        if not isinstance(verification.get(field_name), bool):
            raise ValueError(f"manual recovery verification {field_name} must be boolean")
    full_snapshot_match = verification.get("full_snapshot_match")
    if full_snapshot_match is not None and not isinstance(
        full_snapshot_match,
        bool,
    ):
        raise ValueError("manual recovery verification full_snapshot_match is invalid")
    snapshot_checked = verification["full_snapshot_checked"]
    if snapshot_checked:
        if expected_snapshot is None or current_snapshot is None or full_snapshot_match is None:
            raise ValueError("checked manual recovery snapshot is incomplete")
    elif current_snapshot is not None or full_snapshot_match is not None:
        raise ValueError("unchecked manual recovery snapshot has observations")
    if receipt_status == "recovered":
        if expected_snapshot is None:
            raise ValueError("recovered verification lacks expected snapshot")
    elif expected_snapshot is not None or snapshot_checked or current_snapshot is not None:
        raise ValueError("non-recovered verification cannot claim a routing snapshot")
    reason_codes = verification.get("reason_codes")
    if not isinstance(reason_codes, list) or not reason_codes:
        raise ValueError("manual recovery verification reason_codes are empty")
    normalized_reasons = [
        _required_text(
            reason,
            name=f"reason_codes[{index}]",
            maximum_length=128,
        )
        for index, reason in enumerate(reason_codes)
    ]
    if len(normalized_reasons) != len(set(normalized_reasons)):
        raise ValueError("manual recovery verification reason codes duplicate")
    target_stable = verification["target_bytes_stable"]
    target_match = verification["target_bytes_match_receipt"]
    current_matches = verification["current_configuration_matches_receipt"]
    eligible = verification["eligible_for_normal_write_preflight"]
    new_evidence = verification["new_manual_recovery_evidence_required"]
    manual_intervention = verification["manual_intervention_required"]
    if target_match and not target_stable:
        raise ValueError("matching manual recovery target bytes are not stable")
    expected_status_receipt = {
        "current": "recovered",
        "routing_changed": "recovered",
        "starting_state_current": "starting_state_restored",
        "starting_state_changed": "starting_state_restored",
        "manual_recovery_required": "recovery_failed",
    }
    if receipt_status != expected_status_receipt[str(status)]:
        raise ValueError("manual recovery verification status and receipt differ")
    if status == "current":
        if not (
            snapshot_checked
            and full_snapshot_match is True
            and target_match
            and current_matches
            and eligible
            and not new_evidence
            and not manual_intervention
        ):
            raise ValueError("current manual recovery verification is inconsistent")
    elif status == "routing_changed":
        if (
            current_matches
            or eligible
            or new_evidence
            or not manual_intervention
            or (target_match and snapshot_checked and full_snapshot_match is True)
        ):
            raise ValueError("changed manual recovery verification is inconsistent")
    elif status == "starting_state_current":
        if not (target_match and current_matches and not eligible and new_evidence and not manual_intervention):
            raise ValueError("current starting-state verification is inconsistent")
    elif status == "starting_state_changed":
        if target_match or current_matches or eligible or new_evidence or not manual_intervention:
            raise ValueError("changed starting-state verification is inconsistent")
    elif current_matches or eligible or new_evidence or not manual_intervention:
        raise ValueError("manual-recovery-required verification is inconsistent")
    if verification["source_chain_valid"] is not True:
        raise ValueError("manual recovery verification source chain is invalid")
    if receipt_status != "recovery_failed" and verification["write_ahead_intent_valid"] is not True:
        raise ValueError("completed manual recovery verification lacks an intent")
    if verification["configuration_verification_performed"] is not True:
        raise ValueError("manual recovery verification evidence is invalid")
    if verification["configuration_recovery_performed"] is not False:
        raise ValueError("read-only verification cannot recover configuration")
    if verification["approval_consumed"] is not True:
        raise ValueError("manual recovery approval consumption evidence is invalid")
    if verification["approval_consumed_by_verification"] is not False:
        raise ValueError("read-only verification cannot consume an approval")
    if verification["model_execution_performed"] is not False:
        raise ValueError("manual recovery verification claims model execution")


def format_write_model_configuration_manual_recovery_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format one concise read-only recovery verification result."""

    validate_write_model_configuration_manual_recovery_verification(payload)
    lineage = _clearance_revocation_lineage(payload)
    return (
        "",
        "=" * 60,
        "Write-model configuration manual recovery verification",
        f"  Status        : {payload['status']}",
        f"  Receipt       : {payload['receipt_status']}",
        f"  Selected      : {payload['selected_state']}",
        *(
            (f"  Revocation fp : {lineage['manual_recovery_clearance_revocation_fingerprint']}",)
            if lineage is not None
            else ()
        ),
        f"  Source chain  : {payload['source_chain_valid']}",
        f"  Intent        : {payload['write_ahead_intent_valid']}",
        f"  Target bytes  : {payload['target_bytes_match_receipt']}",
        f"  Full snapshot : {payload['full_snapshot_match']}",
        (f"  Normal writes : {payload['eligible_for_normal_write_preflight']}"),
        (f"  New evidence  : {payload['new_manual_recovery_evidence_required']}"),
        (f"  Manual action : {payload['manual_intervention_required']}"),
        "  Configuration  : unchanged by verification",
        "  Approval       : not consumed by verification",
        "  Model calls    : none",
        "=" * 60,
    )


__all__ = [
    "WriteModelConfigurationManualRecoveryVerificationBlockedError",
    "WriteModelConfigurationManualRecoveryVerificationBusyError",
    "format_write_model_configuration_manual_recovery_verification_report",
    "validate_write_model_configuration_manual_recovery_verification",
    "verify_write_model_configuration_manual_recovery_receipt",
]
