"""Revalidate one saved manual-recovery gate verification receipt."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dayu.services.write_model_configuration_manual_recovery_clearance import (
    WriteModelConfigurationManualRecoveryClearanceBusyError,
    WriteModelConfigurationManualRecoveryGateVerificationChangedError,
    WriteModelConfigurationManualRecoveryGateVerificationEvidenceError,
    validate_write_model_configuration_manual_recovery_gate_verification,
    verify_write_model_configuration_manual_recovery_gate_snapshot,
)

_SCHEMA_VERSION = "write_model_configuration_manual_recovery_gate_verification_revalidation_v1"
_FIELDS = frozenset(
    {
        "schema_version",
        "revalidated_at",
        "ticker",
        "status",
        "action",
        "source_verification_path",
        "source_verification_file_fingerprint",
        "source_verification",
        "fresh_verification",
        "saved_current_state_fingerprint",
        "fresh_current_state_fingerprint",
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
    "current": "saved_verification_matches_current_gate_state",
    "stale": "repeat_gate_snapshot_verification",
}
_REASONS = {
    "current": ["saved_verification_and_bound_gate_match_current_assessment"],
    "stale": ["current_gate_state_changed_since_saved_verification"],
}
_VOLATILE_GATE_FIELDS = frozenset(
    {
        "assessed_at",
        "gate_fingerprint",
    }
)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fingerprint(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _bytes_fingerprint(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _serialize(value: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def _mapping(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return dict(value)


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
        raise ValueError(f"{name} fields are invalid; missing={missing}, unexpected={unexpected}")


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


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("revalidation time must include a timezone")
    return value.astimezone(UTC)


def _validated_fingerprint(value: object, *, name: str) -> str:
    normalized = _required_text(
        value,
        name=name,
        maximum_length=71,
    )
    if _FINGERPRINT_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"{name} is not a SHA-256 fingerprint")
    return normalized


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _stable_gate_state(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field_name: field_value
        for field_name, field_value in sorted(value.items())
        if field_name not in _VOLATILE_GATE_FIELDS
    }


def _changed_gate_fields(
    saved_gate: Mapping[str, Any],
    fresh_gate: Mapping[str, Any],
) -> list[str]:
    saved_state = _stable_gate_state(saved_gate)
    fresh_state = _stable_gate_state(fresh_gate)
    if frozenset(saved_state) != frozenset(fresh_state):
        raise ValueError("manual recovery gate schemas are inconsistent")
    return sorted(field_name for field_name in saved_state if saved_state[field_name] != fresh_state[field_name])


def _load_external_verification(
    path: str | Path,
    *,
    config_root: str | Path,
) -> tuple[Path, dict[str, Any], str]:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise FileNotFoundError(f"manual recovery gate verification input must not be a symlink: {candidate}")
    lexical_target = candidate.absolute()
    target = candidate.resolve()
    resolved_config_root = Path(config_root).expanduser().resolve()
    if _is_relative_to(
        lexical_target,
        resolved_config_root,
    ) or _is_relative_to(target, resolved_config_root):
        raise ValueError("manual recovery gate verification input must be outside the configuration root")
    if not target.is_file():
        raise FileNotFoundError(f"manual recovery gate verification input does not exist as a regular file: {target}")
    raw_payload = target.read_bytes()
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("manual recovery gate verification input is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("manual recovery gate verification input must contain a JSON object")
    validate_write_model_configuration_manual_recovery_gate_verification(payload)
    return target, payload, _bytes_fingerprint(raw_payload)


def _revalidation_payload(
    *,
    revalidated_at: datetime,
    ticker: str,
    source_verification_path: Path,
    source_verification_file_fingerprint: str,
    source_verification: Mapping[str, Any],
    fresh_verification: Mapping[str, Any],
) -> dict[str, Any]:
    saved_current_gate = _mapping(
        source_verification.get("current_gate"),
        name="source_verification.current_gate",
    )
    fresh_current_gate = _mapping(
        fresh_verification.get("current_gate"),
        name="fresh_verification.current_gate",
    )
    changed_fields = _changed_gate_fields(
        saved_current_gate,
        fresh_current_gate,
    )
    state_matches = not changed_fields
    status = "current" if state_matches else "stale"
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "revalidated_at": _format_utc(revalidated_at),
        "ticker": ticker,
        "status": status,
        "action": _ACTIONS[status],
        "source_verification_path": str(source_verification_path.resolve()),
        "source_verification_file_fingerprint": (source_verification_file_fingerprint),
        "source_verification": dict(source_verification),
        "fresh_verification": dict(fresh_verification),
        "saved_current_state_fingerprint": source_verification["current_state_fingerprint"],
        "fresh_current_state_fingerprint": fresh_verification["current_state_fingerprint"],
        "state_matches": state_matches,
        "changed_fields": changed_fields,
        "reason_codes": list(_REASONS[status]),
        "normal_write_authorization_granted": False,
        "configuration_mutation_performed": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }
    payload["revalidation_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_manual_recovery_gate_revalidation(payload)
    return payload


def validate_write_model_configuration_manual_recovery_gate_revalidation(
    payload: Mapping[str, Any],
) -> None:
    """Validate one self-contained saved-verification revalidation."""

    revalidation = _mapping(
        payload,
        name="manual recovery gate verification revalidation",
    )
    _exact_fields(
        revalidation,
        expected=_FIELDS,
        name="manual recovery gate verification revalidation",
    )
    if revalidation.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("manual recovery gate verification revalidation schema is invalid")
    revalidated_at = _parse_utc(
        revalidation.get("revalidated_at"),
        name="revalidated_at",
    )
    ticker = _required_text(
        revalidation.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    status = revalidation.get("status")
    if status not in _ACTIONS:
        raise ValueError("manual recovery gate verification revalidation status is invalid")
    if revalidation.get("action") != _ACTIONS[str(status)]:
        raise ValueError("manual recovery gate verification revalidation action is invalid")
    source_verification_path = Path(
        _required_text(
            revalidation.get("source_verification_path"),
            name="source_verification_path",
            maximum_length=32_768,
        )
    )
    if not source_verification_path.is_absolute():
        raise ValueError("source_verification_path must be absolute")
    _validated_fingerprint(
        revalidation.get("source_verification_file_fingerprint"),
        name="source_verification_file_fingerprint",
    )
    source_verification = _mapping(
        revalidation.get("source_verification"),
        name="source_verification",
    )
    fresh_verification = _mapping(
        revalidation.get("fresh_verification"),
        name="fresh_verification",
    )
    validate_write_model_configuration_manual_recovery_gate_verification(source_verification)
    validate_write_model_configuration_manual_recovery_gate_verification(fresh_verification)
    if source_verification.get("ticker") != ticker or fresh_verification.get("ticker") != ticker:
        raise ValueError("manual recovery gate verification revalidation ticker is inconsistent")
    source_verified_at = _parse_utc(
        source_verification.get("verified_at"),
        name="source_verification.verified_at",
    )
    fresh_verified_at = _parse_utc(
        fresh_verification.get("verified_at"),
        name="fresh_verification.verified_at",
    )
    if source_verified_at > revalidated_at:
        raise ValueError("source gate verification was created after revalidation")
    if fresh_verified_at != revalidated_at:
        raise ValueError("fresh gate verification time is inconsistent")
    source_gate_path = source_verification.get("source_gate_path")
    if fresh_verification.get("source_gate_path") != source_gate_path:
        raise ValueError("fresh gate verification source path is inconsistent")
    source_gate_file_fingerprint = source_verification.get("source_gate_file_fingerprint")
    if fresh_verification.get("source_gate_file_fingerprint") != source_gate_file_fingerprint:
        raise ValueError("fresh gate verification source-file fingerprint is inconsistent")
    if not hmac.compare_digest(
        _canonical_json(
            _mapping(
                source_verification.get("source_gate"),
                name="source_verification.source_gate",
            )
        ),
        _canonical_json(
            _mapping(
                fresh_verification.get("source_gate"),
                name="fresh_verification.source_gate",
            )
        ),
    ):
        raise ValueError("fresh gate verification source gate is inconsistent")
    saved_current_state_fingerprint = _validated_fingerprint(
        revalidation.get("saved_current_state_fingerprint"),
        name="saved_current_state_fingerprint",
    )
    if not hmac.compare_digest(
        saved_current_state_fingerprint,
        str(source_verification["current_state_fingerprint"]),
    ):
        raise ValueError("saved current-state fingerprint is inconsistent")
    fresh_current_state_fingerprint = _validated_fingerprint(
        revalidation.get("fresh_current_state_fingerprint"),
        name="fresh_current_state_fingerprint",
    )
    if not hmac.compare_digest(
        fresh_current_state_fingerprint,
        str(fresh_verification["current_state_fingerprint"]),
    ):
        raise ValueError("fresh current-state fingerprint is inconsistent")
    expected_changed_fields = _changed_gate_fields(
        _mapping(
            source_verification.get("current_gate"),
            name="source_verification.current_gate",
        ),
        _mapping(
            fresh_verification.get("current_gate"),
            name="fresh_verification.current_gate",
        ),
    )
    changed_fields = revalidation.get("changed_fields")
    if not isinstance(changed_fields, list):
        raise ValueError("manual recovery gate verification revalidation changed_fields must be a list")
    normalized_changed_fields = [
        _required_text(
            value,
            name=f"changed_fields[{index}]",
            maximum_length=128,
        )
        for index, value in enumerate(changed_fields)
    ]
    if normalized_changed_fields != expected_changed_fields:
        raise ValueError("manual recovery gate verification revalidation changed_fields are invalid")
    expected_state_matches = not expected_changed_fields
    if revalidation.get("state_matches") is not expected_state_matches:
        raise ValueError("manual recovery gate verification revalidation state match is invalid")
    expected_status = "current" if expected_state_matches else "stale"
    if status != expected_status:
        raise ValueError("manual recovery gate verification revalidation status is inconsistent")
    if revalidation.get("reason_codes") != _REASONS[expected_status]:
        raise ValueError("manual recovery gate verification revalidation reason_codes are invalid")
    safety_fields = (
        "normal_write_authorization_granted",
        "configuration_mutation_performed",
        "approval_consumed",
        "model_execution_performed",
    )
    if any(revalidation.get(field_name) is not False for field_name in safety_fields):
        raise ValueError("manual recovery gate verification revalidation safety evidence is invalid")
    revalidation_fingerprint = _validated_fingerprint(
        revalidation.get("revalidation_fingerprint"),
        name="revalidation_fingerprint",
    )
    unsigned_revalidation = dict(revalidation)
    unsigned_revalidation.pop("revalidation_fingerprint")
    if not hmac.compare_digest(
        revalidation_fingerprint,
        _fingerprint(unsigned_revalidation),
    ):
        raise ValueError("manual recovery gate verification revalidation fingerprint mismatch")


def revalidate_write_model_configuration_manual_recovery_gate_verification(
    *,
    gate_verification_path: str | Path,
    workspace_dir: str | Path,
    config_root: str | Path,
    expected_ticker: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Recheck a saved verification receipt and its bound gate snapshot."""

    normalized_ticker = _required_text(
        expected_ticker,
        name="expected_ticker",
        maximum_length=64,
    )
    current_time = _normalize_now(now if now is not None else datetime.now(UTC))
    (
        source_verification_path,
        source_verification,
        source_verification_file_fingerprint,
    ) = _load_external_verification(
        gate_verification_path,
        config_root=config_root,
    )
    if source_verification.get("ticker") != normalized_ticker:
        raise ValueError("manual recovery gate verification input ticker does not match the command")
    if (
        _parse_utc(
            source_verification.get("verified_at"),
            name="source_verification.verified_at",
        )
        > current_time
    ):
        raise ValueError("manual recovery gate verification input was created in the future")
    try:
        fresh_verification = verify_write_model_configuration_manual_recovery_gate_snapshot(
            gate_snapshot_path=source_verification["source_gate_path"],
            workspace_dir=workspace_dir,
            config_root=config_root,
            expected_ticker=normalized_ticker,
            now=current_time,
        )
    except (
        WriteModelConfigurationManualRecoveryClearanceBusyError,
        WriteModelConfigurationManualRecoveryGateVerificationChangedError,
        WriteModelConfigurationManualRecoveryGateVerificationEvidenceError,
    ):
        raise
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise (
            WriteModelConfigurationManualRecoveryGateVerificationChangedError(
                f"the gate snapshot bound by the saved verification is not current: {exc}"
            )
        ) from exc
    try:
        (
            refreshed_source_verification_path,
            refreshed_source_verification,
            refreshed_source_verification_file_fingerprint,
        ) = _load_external_verification(
            gate_verification_path,
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
                f"manual recovery gate verification input changed during revalidation: {exc}"
            )
        ) from exc
    source_verification_changed = (
        refreshed_source_verification_path != source_verification_path
        or not hmac.compare_digest(
            refreshed_source_verification_file_fingerprint,
            source_verification_file_fingerprint,
        )
        or not hmac.compare_digest(
            _canonical_json(refreshed_source_verification),
            _canonical_json(source_verification),
        )
    )
    if source_verification_changed:
        raise (
            WriteModelConfigurationManualRecoveryGateVerificationChangedError(
                "manual recovery gate verification input changed during revalidation"
            )
        )
    bound_source_matches = (
        fresh_verification.get("source_gate_path") == source_verification.get("source_gate_path")
        and hmac.compare_digest(
            str(fresh_verification["source_gate_file_fingerprint"]),
            str(source_verification["source_gate_file_fingerprint"]),
        )
        and hmac.compare_digest(
            _canonical_json(
                _mapping(
                    fresh_verification.get("source_gate"),
                    name="fresh_verification.source_gate",
                )
            ),
            _canonical_json(
                _mapping(
                    source_verification.get("source_gate"),
                    name="source_verification.source_gate",
                )
            ),
        )
    )
    if not bound_source_matches:
        raise (
            WriteModelConfigurationManualRecoveryGateVerificationChangedError(
                "the gate snapshot bound by the saved verification has changed"
            )
        )
    try:
        return _revalidation_payload(
            revalidated_at=current_time,
            ticker=normalized_ticker,
            source_verification_path=source_verification_path,
            source_verification_file_fingerprint=(source_verification_file_fingerprint),
            source_verification=source_verification,
            fresh_verification=fresh_verification,
        )
    except (TypeError, ValueError) as exc:
        raise (
            WriteModelConfigurationManualRecoveryGateVerificationEvidenceError(
                f"manual recovery gate verification revalidation evidence is invalid: {exc}"
            )
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
            except (OSError, UnicodeError, json.JSONDecodeError):
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
    return target.resolve()


def persist_write_model_configuration_manual_recovery_gate_revalidation(
    payload: Mapping[str, Any],
    path: str | Path,
    *,
    config_root: str | Path,
) -> Path:
    """Immutably export one validated revalidation outside configuration."""

    validate_write_model_configuration_manual_recovery_gate_revalidation(payload)
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise ValueError("manual recovery gate verification revalidation output must not be a symlink")
    lexical_target = candidate.absolute()
    target = candidate.resolve()
    resolved_config_root = Path(config_root).expanduser().resolve()
    if _is_relative_to(
        lexical_target,
        resolved_config_root,
    ) or _is_relative_to(target, resolved_config_root):
        raise ValueError("manual recovery gate verification revalidation output must be outside the configuration root")
    return _persist_immutable(payload, target)


def format_write_model_configuration_manual_recovery_gate_revalidation_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Render one concise saved-verification revalidation report."""

    validate_write_model_configuration_manual_recovery_gate_revalidation(payload)
    changed_fields = ", ".join(payload["changed_fields"]) or "none"
    source_verification = _mapping(
        payload["source_verification"],
        name="source_verification",
    )
    fresh_verification = _mapping(
        payload["fresh_verification"],
        name="fresh_verification",
    )
    return (
        "",
        "=" * 60,
        "Write-model manual recovery gate verification revalidation",
        f"  Status        : {payload['status']}",
        f"  Revalidated at: {payload['revalidated_at']}",
        f"  Ticker        : {payload['ticker']}",
        f"  Action        : {payload['action']}",
        f"  Saved result  : {source_verification['status']}",
        f"  Fresh result  : {fresh_verification['status']}",
        f"  State matches : {payload['state_matches']}",
        f"  Changed       : {changed_fields}",
        "  Authorization : not granted by revalidation",
        "  Configuration : unchanged by revalidation",
        "  Approval      : not consumed by revalidation",
        "  Model calls   : none",
        (f"  Source file fp: {payload['source_verification_file_fingerprint']}"),
        f"  Revalidation  : {payload['revalidation_fingerprint']}",
        "=" * 60,
    )


__all__ = [
    "format_write_model_configuration_manual_recovery_gate_revalidation_report",
    "persist_write_model_configuration_manual_recovery_gate_revalidation",
    "revalidate_write_model_configuration_manual_recovery_gate_verification",
    "validate_write_model_configuration_manual_recovery_gate_revalidation",
]
