"""Create tamper-evident operator approval for Challenger common preflight."""

from __future__ import annotations

import hmac
import json
import os
import tempfile
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dayu.contracts.model_config import ModelConfigJsonValue
from dayu.services._write_artifact_utils import (
    canonical_json_str,
    fingerprint_str,
    validated_fingerprint,
)
from dayu.services.write_model_challenger_proposal import (
    validate_write_model_challenger_proposal,
)
from dayu.services.write_model_challenger_verification import (
    verify_write_model_challenger_proposal,
)

_REQUEST_SCHEMA_VERSION = "write_model_challenger_preflight_approval_request_v1"
_APPROVAL_SCHEMA_VERSION = "write_model_challenger_preflight_approval_v1"
_VERIFICATION_SCHEMA_VERSION = (
    "write_model_challenger_preflight_approval_verification_v1"
)
_APPROVAL_TYPE = "write_model_challenger_common_preflight"
_APPROVAL_SCOPE = "champion_challenger_common_preflight_only"
_APPROVAL_STATUS = "approved_for_common_preflight"
_MAX_APPROVAL_VALIDITY = timedelta(hours=24)
_REQUIRED_ACKNOWLEDGEMENTS = [
    "common_preflight_only",
    "no_model_execution",
    "no_configuration_change",
    "no_challenger_run_authorization",
    "no_challenger_promotion_authorization",
]
_SAFETY_BOUNDARIES = [
    "preflight_does_not_call_models",
    "approval_does_not_modify_configuration",
    "approval_does_not_authorize_challenger_execution",
    "approval_does_not_authorize_challenger_promotion",
]
_REQUEST_FIELDS = {
    "schema_version",
    "approval_type",
    "scope",
    "approved_by",
    "approval_reference",
    "approved_at",
    "expires_at",
    "proposal_fingerprint",
    "history_fingerprint",
    "acknowledgements",
}
_APPROVAL_FIELDS = {
    "schema_version",
    "approval_type",
    "scope",
    "status",
    "approved_by",
    "approval_reference",
    "approved_at",
    "expires_at",
    "proposal_fingerprint",
    "history_fingerprint",
    "request_fingerprint",
    "approved_cli_args",
    "acknowledgements",
    "safety_boundaries",
    "approval_fingerprint",
}
_ROLE_ARGUMENTS = {
    "--challenger-model-name",
    "--challenger-audit-model-name",
}


class WriteModelPreflightApprovalBlockedError(ValueError):
    """Raised when a valid request is not currently safe to approve."""


def _validate_exact_fields(
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
    details: list[str] = []
    if missing:
        details.append(f"missing={missing}")
    if unexpected:
        details.append(f"unexpected={unexpected}")
    raise ValueError(f"{name} fields are invalid: {', '.join(details)}")


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
        raise ValueError(f"{name} is required")
    if normalized != value:
        raise ValueError(f"{name} cannot have leading or trailing whitespace")
    if len(normalized) > maximum_length:
        raise ValueError(f"{name} must be at most {maximum_length} characters")
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise ValueError(f"{name} cannot contain control characters")
    return normalized


def _parse_utc_timestamp(value: object, *, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include UTC timezone information")
    return parsed.astimezone(UTC)


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_acknowledgements(value: object) -> None:
    if value != _REQUIRED_ACKNOWLEDGEMENTS:
        raise ValueError("acknowledgements must exactly match the required safety list")


def _validate_approval_window(
    *,
    approved_at: datetime,
    expires_at: datetime,
) -> None:
    if expires_at <= approved_at:
        raise ValueError("expires_at must be later than approved_at")
    if expires_at - approved_at > _MAX_APPROVAL_VALIDITY:
        raise ValueError("approval validity cannot exceed 24 hours")


def _validated_preflight_args(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("approved_cli_args must be a string array")
    if not value or value[0] != "--preflight-only":
        raise ValueError("approved_cli_args must start with --preflight-only")
    role_args = value[1:]
    if not role_args or len(role_args) % 2:
        raise ValueError("approved_cli_args must contain Challenger flag/value pairs")
    seen: set[str] = set()
    for index in range(0, len(role_args), 2):
        flag = role_args[index]
        raw_model_name = role_args[index + 1]
        model_name = raw_model_name.strip()
        if flag not in _ROLE_ARGUMENTS:
            raise ValueError("unsupported preflight approval argument")
        if flag in seen:
            raise ValueError("duplicate preflight approval argument")
        if (
            not model_name
            or model_name != raw_model_name
            or model_name.startswith("-")
            or len(model_name) > 200
            or any(character.isspace() for character in model_name)
            or any(unicodedata.category(character).startswith("C") for character in model_name)
        ):
            raise ValueError("invalid preflight approval model name")
        seen.add(flag)
    return list(value)


def validate_write_model_challenger_preflight_approval_request(
    payload: Mapping[str, Any],
) -> None:
    """Validate one explicit, non-cryptographic operator approval request."""

    _validate_exact_fields(
        payload,
        expected=_REQUEST_FIELDS,
        name="preflight approval request",
    )
    if payload.get("schema_version") != _REQUEST_SCHEMA_VERSION:
        raise ValueError("unsupported preflight approval request schema")
    if payload.get("approval_type") != _APPROVAL_TYPE:
        raise ValueError("unsupported preflight approval type")
    if payload.get("scope") != _APPROVAL_SCOPE:
        raise ValueError("preflight approval scope is invalid")
    _required_text(
        payload.get("approved_by"),
        name="approved_by",
        maximum_length=200,
    )
    _required_text(
        payload.get("approval_reference"),
        name="approval_reference",
        maximum_length=500,
    )
    approved_at = _parse_utc_timestamp(
        payload.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc_timestamp(
        payload.get("expires_at"),
        name="expires_at",
    )
    _validate_approval_window(
        approved_at=approved_at,
        expires_at=expires_at,
    )
    validated_fingerprint(
        payload.get("proposal_fingerprint"),
        name="proposal_fingerprint",
    )
    validated_fingerprint(
        payload.get("history_fingerprint"),
        name="history_fingerprint",
    )
    _validate_acknowledgements(payload.get("acknowledgements"))


def build_write_model_challenger_preflight_approval(
    *,
    request: Mapping[str, Any],
    proposal_receipt: Mapping[str, Any],
    current_proposal: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Build approval only for a current, ready Challenger proposal."""

    validate_write_model_challenger_preflight_approval_request(request)
    validate_write_model_challenger_proposal(proposal_receipt)
    validate_write_model_challenger_proposal(current_proposal)
    verification = verify_write_model_challenger_proposal(
        proposal_receipt,
        current_proposal,
    )
    if verification.get("status") != "current":
        raise WriteModelPreflightApprovalBlockedError("Challenger proposal is not current")
    if (
        current_proposal.get("status") != "ready"
        or verification.get("preflight_preview", {}).get("available") is not True
    ):
        raise WriteModelPreflightApprovalBlockedError("Challenger proposal is not ready for common preflight")

    approved_at = _parse_utc_timestamp(
        request.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc_timestamp(
        request.get("expires_at"),
        name="expires_at",
    )
    current_time = _normalize_now(now)
    if current_time < approved_at:
        raise WriteModelPreflightApprovalBlockedError("preflight approval is not effective yet")
    if current_time >= expires_at:
        raise WriteModelPreflightApprovalBlockedError("preflight approval has expired")

    proposal_fingerprint = validated_fingerprint(
        current_proposal.get("proposal_fingerprint"),
        name="proposal_fingerprint",
    )
    evidence_window = current_proposal.get("evidence_window")
    if not isinstance(evidence_window, Mapping):
        raise ValueError("proposal evidence_window must be an object")
    history_fingerprint = validated_fingerprint(
        evidence_window.get("history_fingerprint"),
        name="history_fingerprint",
    )
    requested_proposal_fingerprint = validated_fingerprint(
        request.get("proposal_fingerprint"),
        name="proposal_fingerprint",
    )
    requested_history_fingerprint = validated_fingerprint(
        request.get("history_fingerprint"),
        name="history_fingerprint",
    )
    if not hmac.compare_digest(
        requested_proposal_fingerprint,
        proposal_fingerprint,
    ):
        raise WriteModelPreflightApprovalBlockedError("approval request proposal fingerprint does not match")
    if not hmac.compare_digest(
        requested_history_fingerprint,
        history_fingerprint,
    ):
        raise WriteModelPreflightApprovalBlockedError("approval request history fingerprint does not match")

    proposal_args = current_proposal.get("challenger_cli_args")
    approved_cli_args = _validated_preflight_args(["--preflight-only", *(proposal_args or [])])
    payload: dict[str, Any] = {
        "schema_version": _APPROVAL_SCHEMA_VERSION,
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
        "status": _APPROVAL_STATUS,
        "approved_by": request["approved_by"],
        "approval_reference": request["approval_reference"],
        "approved_at": _format_utc(approved_at),
        "expires_at": _format_utc(expires_at),
        "proposal_fingerprint": proposal_fingerprint,
        "history_fingerprint": history_fingerprint,
        "request_fingerprint": fingerprint_str(dict(request)),
        "approved_cli_args": approved_cli_args,
        "acknowledgements": list(_REQUIRED_ACKNOWLEDGEMENTS),
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
    }
    payload["approval_fingerprint"] = fingerprint_str(payload)
    validate_write_model_challenger_preflight_approval(payload)
    return payload


def validate_write_model_challenger_preflight_approval(
    payload: Mapping[str, Any],
) -> None:
    """Validate approval schema, safe argv, and tamper-evident fingerprint."""

    _validate_exact_fields(
        payload,
        expected=_APPROVAL_FIELDS,
        name="preflight approval",
    )
    if payload.get("schema_version") != _APPROVAL_SCHEMA_VERSION:
        raise ValueError("unsupported preflight approval schema")
    if payload.get("approval_type") != _APPROVAL_TYPE:
        raise ValueError("unsupported preflight approval type")
    if payload.get("scope") != _APPROVAL_SCOPE:
        raise ValueError("preflight approval scope is invalid")
    if payload.get("status") != _APPROVAL_STATUS:
        raise ValueError("preflight approval status is invalid")
    _required_text(
        payload.get("approved_by"),
        name="approved_by",
        maximum_length=200,
    )
    _required_text(
        payload.get("approval_reference"),
        name="approval_reference",
        maximum_length=500,
    )
    approved_at = _parse_utc_timestamp(
        payload.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc_timestamp(
        payload.get("expires_at"),
        name="expires_at",
    )
    _validate_approval_window(
        approved_at=approved_at,
        expires_at=expires_at,
    )
    validated_fingerprint(
        payload.get("proposal_fingerprint"),
        name="proposal_fingerprint",
    )
    validated_fingerprint(
        payload.get("history_fingerprint"),
        name="history_fingerprint",
    )
    validated_fingerprint(
        payload.get("request_fingerprint"),
        name="request_fingerprint",
    )
    _validated_preflight_args(payload.get("approved_cli_args"))
    _validate_acknowledgements(payload.get("acknowledgements"))
    if payload.get("safety_boundaries") != _SAFETY_BOUNDARIES:
        raise ValueError("safety_boundaries must exactly match the approval boundary")
    expected = validated_fingerprint(
        payload.get("approval_fingerprint"),
        name="approval_fingerprint",
    )
    unsigned_payload = dict(payload)
    unsigned_payload.pop("approval_fingerprint", None)
    actual = fingerprint_str(unsigned_payload)
    if not hmac.compare_digest(expected, actual):
        raise ValueError("preflight approval fingerprint mismatch")


def verify_write_model_challenger_preflight_approval(
    *,
    approval: Mapping[str, Any],
    proposal_receipt: Mapping[str, Any],
    current_proposal: Mapping[str, Any],
    actual_cli_args: list[str],
    actual_current_models: Mapping[str, str],
    now: datetime,
) -> dict[str, Any]:
    """Verify approval identity, time, and the exact preflight model plan."""

    validate_write_model_challenger_preflight_approval(approval)
    validate_write_model_challenger_proposal(proposal_receipt)
    validate_write_model_challenger_proposal(current_proposal)
    proposal_verification = verify_write_model_challenger_proposal(
        proposal_receipt,
        current_proposal,
    )
    current_window = current_proposal.get("evidence_window")
    if not isinstance(current_window, Mapping):
        raise ValueError("proposal evidence_window must be an object")

    current_history_fingerprint = validated_fingerprint(
        current_window.get("history_fingerprint"),
        name="history_fingerprint",
    )
    current_proposal_fingerprint = validated_fingerprint(
        current_proposal.get("proposal_fingerprint"),
        name="proposal_fingerprint",
    )
    approval_history_fingerprint = validated_fingerprint(
        approval.get("history_fingerprint"),
        name="history_fingerprint",
    )
    approval_proposal_fingerprint = validated_fingerprint(
        approval.get("proposal_fingerprint"),
        name="proposal_fingerprint",
    )
    history_matches = hmac.compare_digest(
        approval_history_fingerprint,
        current_history_fingerprint,
    )
    proposal_matches = hmac.compare_digest(
        approval_proposal_fingerprint,
        current_proposal_fingerprint,
    )

    expected_cli_args = _validated_preflight_args(
        [
            "--preflight-only",
            *(current_proposal.get("challenger_cli_args") or []),
        ]
    )
    approved_cli_args = _validated_preflight_args(
        approval.get("approved_cli_args")
    )
    normalized_actual_cli_args = _validated_preflight_args(actual_cli_args)
    approved_cli_args_json: list[ModelConfigJsonValue] = list(
        approved_cli_args
    )
    expected_cli_args_json: list[ModelConfigJsonValue] = list(
        expected_cli_args
    )
    actual_cli_args_json: list[ModelConfigJsonValue] = list(
        normalized_actual_cli_args
    )
    approved_arguments_match = hmac.compare_digest(
        canonical_json_str(approved_cli_args_json),
        canonical_json_str(expected_cli_args_json),
    )
    command_arguments_match = hmac.compare_digest(
        canonical_json_str(actual_cli_args_json),
        canonical_json_str(approved_cli_args_json),
    )

    expected_current_models: dict[str, str] = {}
    raw_role_overrides = current_proposal.get("role_overrides")
    if not isinstance(raw_role_overrides, list):
        raise ValueError("proposal role_overrides must be an array")
    for raw_override in raw_role_overrides:
        if not isinstance(raw_override, Mapping):
            raise ValueError("proposal role override must be an object")
        role = str(raw_override.get("model_role") or "").strip()
        current_model = str(
            raw_override.get("current_model_name") or ""
        ).strip()
        if role not in {"primary", "audit"} or not current_model:
            raise ValueError("proposal role override identity is invalid")
        if role in expected_current_models:
            raise ValueError("proposal contains duplicate role overrides")
        expected_current_models[role] = current_model
    normalized_actual_models: dict[str, str] = {}
    for raw_role, raw_model_name in actual_current_models.items():
        role = str(raw_role).strip()
        model_name = str(raw_model_name or "").strip()
        if role not in {"primary", "audit"} or not model_name:
            raise ValueError("actual current model identity is invalid")
        normalized_actual_models[role] = model_name
    current_models_match = normalized_actual_models == (
        expected_current_models
    )

    approved_at = _parse_utc_timestamp(
        approval.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc_timestamp(
        approval.get("expires_at"),
        name="expires_at",
    )
    current_time = _normalize_now(now)
    proposal_status = str(proposal_verification.get("status") or "")
    if proposal_status != "current":
        status = proposal_status
        reason_codes = list(
            proposal_verification.get("reason_codes") or []
        )
    elif current_proposal.get("status") != "ready":
        status = "proposal_not_ready"
        reason_codes = ["current_proposal_not_ready"]
    elif not history_matches:
        status = "stale_history"
        reason_codes = ["approval_history_fingerprint_changed"]
    elif not proposal_matches:
        status = "policy_changed"
        reason_codes = ["approval_proposal_fingerprint_changed"]
    elif not approved_arguments_match:
        status = "approved_arguments_changed"
        reason_codes = ["approval_arguments_do_not_match_current_proposal"]
    elif current_time < approved_at:
        status = "not_effective"
        reason_codes = ["approval_not_effective_yet"]
    elif current_time >= expires_at:
        status = "expired"
        reason_codes = ["approval_expired"]
    elif not command_arguments_match:
        status = "command_mismatch"
        reason_codes = ["command_arguments_do_not_match_approval"]
    elif not current_models_match:
        status = "command_mismatch"
        reason_codes = ["current_models_do_not_match_proposal"]
    else:
        status = "approved"
        reason_codes = ["common_preflight_approved"]

    authorized = status == "approved"
    return {
        "schema_version": _VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "preflight_authorized": authorized,
        "action": "run_common_preflight" if authorized else "stop",
        "reason_codes": reason_codes,
        "identity": {
            "proposal_verification_status": proposal_status,
            "history_matches": history_matches,
            "proposal_matches": proposal_matches,
            "approved_arguments_match": approved_arguments_match,
            "command_arguments_match": command_arguments_match,
            "current_models_match": current_models_match,
        },
        "effective_window": {
            "approved_at": _format_utc(approved_at),
            "expires_at": _format_utc(expires_at),
            "checked_at": _format_utc(current_time),
        },
        "expected_current_models": expected_current_models,
        "actual_current_models": normalized_actual_models,
        "approved_cli_args": approved_cli_args,
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
    }


def format_write_model_challenger_preflight_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format the final Host-before-start approval gate result."""

    identity = payload.get("identity")
    identity_view = identity if isinstance(identity, Mapping) else {}
    effective_window = payload.get("effective_window")
    window_view = (
        effective_window
        if isinstance(effective_window, Mapping)
        else {}
    )
    return (
        "",
        "=" * 60,
        "Challenger 共同 preflight 审批验证",
        "=" * 60,
        f"  状态       : {payload.get('status', 'invalid')}",
        (
            "  历史一致   : "
            f"{'是' if identity_view.get('history_matches') is True else '否'}"
        ),
        (
            "  提案一致   : "
            f"{'是' if identity_view.get('proposal_matches') is True else '否'}"
        ),
        (
            "  参数一致   : "
            f"{'是' if identity_view.get('command_arguments_match') is True else '否'}"
        ),
        (
            "  Champion   : "
            f"{'一致' if identity_view.get('current_models_match') is True else '不一致'}"
        ),
        f"  失效时间   : {window_view.get('expires_at', 'unknown')}",
        (
            "  下一步     : 执行共同 preflight"
            if payload.get("preflight_authorized") is True
            else "  下一步     : 停止，不初始化 Host"
        ),
        "=" * 60,
        "",
    )


def _load_json_object(path: str | Path, *, name: str) -> tuple[Path, dict[str, Any]]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"{name} does not exist: {target}")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {name} JSON: {target}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be an object: {target}")
    return target, raw


def load_write_model_challenger_preflight_approval_request(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one explicit operator approval request."""

    target, payload = _load_json_object(
        path,
        name="preflight approval request",
    )
    validate_write_model_challenger_preflight_approval_request(payload)
    return target, payload


def load_write_model_challenger_preflight_approval(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one persisted common-preflight approval receipt."""

    target, payload = _load_json_object(
        path,
        name="preflight approval",
    )
    validate_write_model_challenger_preflight_approval(payload)
    return target, payload


def persist_write_model_challenger_preflight_approval(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist immutable approval atomically; identical content is idempotent."""

    validate_write_model_challenger_preflight_approval(payload)
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )

    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if existing == dict(payload):
            return target
        raise FileExistsError(f"preflight approval already exists with different content: {target}")

    file_descriptor, temp_path_value = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temp_path = Path(temp_path_value)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
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
                raise FileExistsError(f"preflight approval already exists with different content: {target}") from None
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return target


def format_write_model_challenger_preflight_approval_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact approval receipt report without executing preflight."""

    return (
        "",
        "=" * 60,
        "Challenger 共同 preflight 审批凭据",
        "=" * 60,
        f"  状态       : {payload.get('status', 'invalid')}",
        f"  审批人     : {payload.get('approved_by', 'unknown')}",
        f"  审批引用   : {payload.get('approval_reference', 'unknown')}",
        f"  失效时间   : {payload.get('expires_at', 'unknown')}",
        "  批准参数   : "
        + json.dumps(
            payload.get("approved_cli_args", []),
            ensure_ascii=False,
        ),
        "  安全边界   : 仅共同 preflight；未运行模型、未改配置、未批准双跑或晋升",
        "=" * 60,
        "",
    )


__all__ = [
    "WriteModelPreflightApprovalBlockedError",
    "build_write_model_challenger_preflight_approval",
    "format_write_model_challenger_preflight_approval_report",
    "format_write_model_challenger_preflight_verification_report",
    "load_write_model_challenger_preflight_approval",
    "load_write_model_challenger_preflight_approval_request",
    "persist_write_model_challenger_preflight_approval",
    "validate_write_model_challenger_preflight_approval",
    "validate_write_model_challenger_preflight_approval_request",
    "verify_write_model_challenger_preflight_approval",
]
