"""Build reviewable write-model configuration change approval artifacts."""

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
    absolute_path,
    canonical_json_str,
    file_fingerprint,
    fingerprint_str,
    require_mapping,
    serialize_pretty,
    validated_fingerprint,
)
from dayu.services.write_model_challenger_promotion import (
    load_write_model_challenger_promotion_proposal,
    verify_write_model_challenger_promotion_proposal,
)

_CHANGE_REQUEST_SCHEMA_VERSION = (
    "write_model_challenger_configuration_change_request_v1"
)
_CHANGE_REQUEST_VERIFICATION_SCHEMA_VERSION = (
    "write_model_challenger_configuration_change_request_verification_v1"
)
_APPROVAL_REQUEST_SCHEMA_VERSION = (
    "write_model_challenger_configuration_change_approval_request_v1"
)
_APPROVAL_SCHEMA_VERSION = (
    "write_model_challenger_configuration_change_approval_v1"
)
_APPROVAL_VERIFICATION_SCHEMA_VERSION = (
    "write_model_challenger_configuration_change_approval_verification_v1"
)
_CHANGE_REQUEST_TYPE = "write_model_challenger_configuration_change_review"
_CHANGE_REQUEST_SCOPE = "review_only_no_configuration_application"
_CHANGE_REQUEST_STATUS = "ready_for_human_approval"
_APPROVAL_TYPE = "write_model_challenger_configuration_change"
_APPROVAL_SCOPE = (
    "one_future_write_scene_routing_change_subject_to_runtime_match"
)
_APPROVAL_STATUS = "approved_for_one_future_configuration_change"
_CONFIGURATION_DOMAIN = "write_scene_model_routing"
_SOURCE_SEMANTICS = (
    "completed_run_observation_not_current_runtime_configuration"
)
_MAX_APPROVAL_VALIDITY = timedelta(hours=4)
_ROLE_NAMES = ("primary", "audit")
_ROLE_ORDER = {
    role_name: index
    for index, role_name in enumerate(_ROLE_NAMES)
}
_CHANGE_REQUEST_REVIEW_REQUIREMENTS = [
    "verify_current_runtime_configuration_matches_observed_champion",
    "prepare_and_validate_rollback_plan",
    "consume_short_lived_approval_once_before_application",
    "separate_application_command_required",
]
_CHANGE_REQUEST_SAFETY_BOUNDARIES = [
    "review_only",
    "no_configuration_application",
    "no_model_execution",
    "no_model_catalog_or_secret_mutation",
    "completed_run_models_are_observations_not_runtime_assertions",
    "source_promotion_proposal_must_remain_current",
]
_REQUIRED_ACKNOWLEDGEMENTS = [
    "reviewed_exact_scene_model_transitions",
    "promotion_proposal_and_change_request_must_remain_current",
    "runtime_configuration_must_match_observed_champion_before_application",
    "rollback_plan_is_ready",
    "approval_is_single_use",
    "issuance_and_verification_do_not_apply_configuration",
    "issuance_and_verification_do_not_execute_models",
    "separate_application_command_required",
]
_APPROVAL_SAFETY_BOUNDARIES = [
    "one_future_write_scene_routing_change_only",
    "current_runtime_configuration_match_required",
    "rollback_reference_required",
    "single_use_consumption_required_before_application",
    "issuance_does_not_apply_configuration",
    "verification_does_not_apply_configuration",
    "no_model_execution",
    "no_model_catalog_or_secret_mutation",
]
_CHANGE_REQUEST_FIELDS = {
    "schema_version",
    "request_type",
    "scope",
    "status",
    "ticker",
    "source_promotion_proposal",
    "target",
    "transitions",
    "review_requirements",
    "safety_boundaries",
    "request_fingerprint",
}
_PROMOTION_SOURCE_FIELDS = {
    "path",
    "fingerprint",
    "proposal_fingerprint",
}
_TARGET_FIELDS = {
    "configuration_domain",
    "source_semantics",
    "changed_roles",
    "transition_count",
}
_TRANSITION_FIELDS = {
    "role",
    "scene_name",
    "observed_champion_model_name",
    "proposed_challenger_model_name",
}
_APPROVAL_REQUEST_FIELDS = {
    "schema_version",
    "approval_type",
    "scope",
    "approved_by",
    "approval_reference",
    "rollback_reference",
    "approved_at",
    "expires_at",
    "configuration_change_request_fingerprint",
    "promotion_proposal_fingerprint",
    "acknowledgements",
}
_APPROVAL_FIELDS = {
    "schema_version",
    "approval_type",
    "scope",
    "status",
    "approved_by",
    "approval_reference",
    "rollback_reference",
    "approved_at",
    "expires_at",
    "configuration_change_request_source",
    "configuration_change_request_fingerprint",
    "promotion_proposal_fingerprint",
    "approval_request_fingerprint",
    "configuration_change_request",
    "maximum_uses",
    "acknowledgements",
    "safety_boundaries",
    "approval_fingerprint",
}
_CHANGE_REQUEST_SOURCE_FIELDS = {
    "path",
    "fingerprint",
    "request_fingerprint",
}


class WriteModelConfigurationChangeBlockedError(ValueError):
    """Raised when current evidence cannot safely enter the next gate."""


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
    raise ValueError(
        f"{name} fields are invalid: {', '.join(details)}"
    )


def _required_text(
    value: object,
    *,
    name: str,
    maximum_length: int = 4096,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    if normalized != value:
        raise ValueError(
            f"{name} cannot have leading or trailing whitespace"
        )
    if len(normalized) > maximum_length:
        raise ValueError(
            f"{name} must be at most {maximum_length} characters"
        )
    if any(
        unicodedata.category(character).startswith("C")
        for character in normalized
    ):
        raise ValueError(f"{name} cannot contain control characters")
    return normalized


def _string_list(
    value: object,
    *,
    name: str,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return [
        _required_text(
            item,
            name=f"{name}[{index}]",
            maximum_length=256,
        )
        for index, item in enumerate(value)
    ]


def _parse_utc_timestamp(value: object, *, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(
            f"{name} must be an ISO-8601 UTC timestamp ending in Z"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(
            f"{name} must be a valid ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(
            f"{name} must include UTC timezone information"
        )
    return parsed.astimezone(UTC)


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_approval_window(
    *,
    approved_at: datetime,
    expires_at: datetime,
) -> None:
    if expires_at <= approved_at:
        raise ValueError("expires_at must be later than approved_at")
    if expires_at - approved_at > _MAX_APPROVAL_VALIDITY:
        raise ValueError(
            "configuration change approval validity cannot exceed 4 hours"
        )


def _role_scenes(
    role: Mapping[str, Any],
    *,
    side: str,
) -> dict[str, str]:
    raw_scenes = role.get(f"{side}_scenes")
    if not isinstance(raw_scenes, list):
        raise ValueError(f"{side}_scenes must be a list")
    scenes: dict[str, str] = {}
    for index, raw_scene in enumerate(raw_scenes):
        scene = require_mapping(
            raw_scene,
            name=f"{side}_scenes[{index}]",
        )
        scene_name = _required_text(
            scene.get("scene_name"),
            name=f"{side}_scenes[{index}].scene_name",
            maximum_length=128,
        )
        model_name = _required_text(
            scene.get("model_name"),
            name=f"{side}_scenes[{index}].model_name",
            maximum_length=256,
        )
        if scene_name in scenes:
            raise ValueError(f"{side}_scenes contains duplicate scenes")
        scenes[scene_name] = model_name
    return scenes


def _derive_transitions(
    proposal: Mapping[str, Any],
) -> tuple[list[str], list[dict[str, str]]]:
    review = require_mapping(
        proposal.get("model_plan_review"),
        name="promotion proposal model_plan_review",
    )
    if review.get("all_changed_roles_unambiguous") is not True:
        raise WriteModelConfigurationChangeBlockedError(
            "promotion proposal contains ambiguous model transitions"
        )
    changed_roles = _string_list(
        review.get("changed_roles"),
        name="promotion proposal changed_roles",
    )
    if changed_roles != [
        role_name
        for role_name in _ROLE_NAMES
        if role_name in changed_roles
    ]:
        raise ValueError(
            "promotion proposal changed_roles are not ordered"
        )
    raw_roles = review.get("roles")
    if not isinstance(raw_roles, list):
        raise ValueError("promotion proposal roles must be a list")
    roles_by_name: dict[str, Mapping[str, Any]] = {}
    for index, raw_role in enumerate(raw_roles):
        role = require_mapping(
            raw_role,
            name=f"promotion proposal roles[{index}]",
        )
        role_name = _required_text(
            role.get("role"),
            name=f"promotion proposal roles[{index}].role",
            maximum_length=32,
        )
        if role_name not in _ROLE_NAMES or role_name in roles_by_name:
            raise ValueError("promotion proposal contains invalid roles")
        roles_by_name[role_name] = role

    transitions: list[dict[str, str]] = []
    for role_name in changed_roles:
        role = roles_by_name.get(role_name)
        if role is None:
            raise ValueError(
                f"promotion proposal is missing role {role_name!r}"
            )
        if (
            role.get("changed") is not True
            or role.get("transition_unambiguous") is not True
        ):
            raise WriteModelConfigurationChangeBlockedError(
                f"promotion proposal role {role_name!r} is ambiguous"
            )
        champion_scenes = _role_scenes(role, side="champion")
        challenger_scenes = _role_scenes(role, side="challenger")
        if set(champion_scenes) != set(challenger_scenes):
            raise WriteModelConfigurationChangeBlockedError(
                f"promotion proposal role {role_name!r} has unequal scenes"
            )
        for scene_name in sorted(champion_scenes):
            champion_model = champion_scenes[scene_name]
            challenger_model = challenger_scenes[scene_name]
            if champion_model == challenger_model:
                raise WriteModelConfigurationChangeBlockedError(
                    "changed promotion role contains an unchanged scene"
                )
            transitions.append(
                {
                    "role": role_name,
                    "scene_name": scene_name,
                    "observed_champion_model_name": champion_model,
                    "proposed_challenger_model_name": challenger_model,
                }
            )
    if not transitions:
        raise WriteModelConfigurationChangeBlockedError(
            "promotion proposal contains no configuration transitions"
        )
    return changed_roles, transitions


def build_write_model_configuration_change_request(
    promotion_proposal_path: str | Path,
) -> dict[str, Any]:
    """Build a deterministic review request from one current proposal."""

    resolved_path, proposal = (
        load_write_model_challenger_promotion_proposal(
            promotion_proposal_path
        )
    )
    verification = (
        verify_write_model_challenger_promotion_proposal(proposal)
    )
    if verification.get("status") != "current":
        raise WriteModelConfigurationChangeBlockedError(
            "promotion proposal is not current"
        )
    changed_roles, transitions = _derive_transitions(proposal)
    payload: dict[str, Any] = {
        "schema_version": _CHANGE_REQUEST_SCHEMA_VERSION,
        "request_type": _CHANGE_REQUEST_TYPE,
        "scope": _CHANGE_REQUEST_SCOPE,
        "status": _CHANGE_REQUEST_STATUS,
        "ticker": _required_text(
            proposal.get("ticker"),
            name="promotion proposal ticker",
            maximum_length=64,
        ),
        "source_promotion_proposal": {
            "path": str(resolved_path),
            "fingerprint": file_fingerprint(resolved_path),
            "proposal_fingerprint": validated_fingerprint(
                proposal.get("proposal_fingerprint"),
                name="promotion proposal proposal_fingerprint",
            ),
        },
        "target": {
            "configuration_domain": _CONFIGURATION_DOMAIN,
            "source_semantics": _SOURCE_SEMANTICS,
            "changed_roles": changed_roles,
            "transition_count": len(transitions),
        },
        "transitions": transitions,
        "review_requirements": list(
            _CHANGE_REQUEST_REVIEW_REQUIREMENTS
        ),
        "safety_boundaries": list(
            _CHANGE_REQUEST_SAFETY_BOUNDARIES
        ),
    }
    payload["request_fingerprint"] = fingerprint_str(payload)
    validate_write_model_configuration_change_request(payload)
    return payload


def _validate_transition(
    value: ModelConfigJsonValue,
    *,
    name: str,
) -> dict[str, str]:
    """校验单个配置变更 transition。

    Args:
        value: 待校验的 JSON 值。
        name: 用于错误消息的字段路径。

    Returns:
        规范化后的 transition 字段字典。

    Raises:
        ValueError: 当结构、角色、场景、模型或路径字段不合法时抛出。
    """
    transition = require_mapping(value, name=name)
    _validate_exact_fields(
        transition,
        expected=_TRANSITION_FIELDS,
        name=name,
    )
    role = _required_text(
        transition.get("role"),
        name=f"{name}.role",
        maximum_length=32,
    )
    if role not in _ROLE_NAMES:
        raise ValueError(f"{name}.role is invalid")
    scene_name = _required_text(
        transition.get("scene_name"),
        name=f"{name}.scene_name",
        maximum_length=128,
    )
    champion_model = _required_text(
        transition.get("observed_champion_model_name"),
        name=f"{name}.observed_champion_model_name",
        maximum_length=256,
    )
    challenger_model = _required_text(
        transition.get("proposed_challenger_model_name"),
        name=f"{name}.proposed_challenger_model_name",
        maximum_length=256,
    )
    if champion_model == challenger_model:
        raise ValueError(f"{name} does not change the model")
    return {
        "role": role,
        "scene_name": scene_name,
        "observed_champion_model_name": champion_model,
        "proposed_challenger_model_name": challenger_model,
    }


def validate_write_model_configuration_change_request(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict, tamper-evident change review request."""

    _validate_exact_fields(
        payload,
        expected=_CHANGE_REQUEST_FIELDS,
        name="configuration change request",
    )
    constants = {
        "schema_version": _CHANGE_REQUEST_SCHEMA_VERSION,
        "request_type": _CHANGE_REQUEST_TYPE,
        "scope": _CHANGE_REQUEST_SCOPE,
        "status": _CHANGE_REQUEST_STATUS,
    }
    for field_name, expected in constants.items():
        if payload.get(field_name) != expected:
            raise ValueError(
                f"configuration change request {field_name} "
                f"must be {expected!r}"
            )
    _required_text(
        payload.get("ticker"),
        name="configuration change request ticker",
        maximum_length=64,
    )
    source = require_mapping(
        payload.get("source_promotion_proposal"),
        name="configuration change request source_promotion_proposal",
    )
    _validate_exact_fields(
        source,
        expected=_PROMOTION_SOURCE_FIELDS,
        name="configuration change request source_promotion_proposal",
    )
    absolute_path(
        _required_text(
            source.get("path"),
            name="source_promotion_proposal.path",
        ),
        name="source_promotion_proposal.path",
    )
    validated_fingerprint(
        source.get("fingerprint"),
        name="source_promotion_proposal.fingerprint",
    )
    validated_fingerprint(
        source.get("proposal_fingerprint"),
        name="source_promotion_proposal.proposal_fingerprint",
    )
    target = require_mapping(
        payload.get("target"),
        name="configuration change request target",
    )
    _validate_exact_fields(
        target,
        expected=_TARGET_FIELDS,
        name="configuration change request target",
    )
    if target.get("configuration_domain") != _CONFIGURATION_DOMAIN:
        raise ValueError("configuration change domain is invalid")
    if target.get("source_semantics") != _SOURCE_SEMANTICS:
        raise ValueError("configuration change source semantics are invalid")
    changed_roles = _string_list(
        target.get("changed_roles"),
        name="configuration change request changed_roles",
    )
    if (
        not changed_roles
        or changed_roles
        != [
            role_name
            for role_name in _ROLE_NAMES
            if role_name in changed_roles
        ]
        or len(changed_roles) != len(set(changed_roles))
    ):
        raise ValueError(
            "configuration change request changed_roles are invalid"
        )
    raw_transitions = payload.get("transitions")
    if not isinstance(raw_transitions, list) or not raw_transitions:
        raise ValueError(
            "configuration change request transitions must be non-empty"
        )
    transitions = [
        _validate_transition(
            raw_transition,
            name=f"configuration change request transitions[{index}]",
        )
        for index, raw_transition in enumerate(raw_transitions)
    ]
    expected_order = sorted(
        transitions,
        key=lambda item: (
            _ROLE_ORDER[item["role"]],
            item["scene_name"],
        ),
    )
    if transitions != expected_order:
        raise ValueError(
            "configuration change request transitions must be sorted"
        )
    identities = [
        (transition["role"], transition["scene_name"])
        for transition in transitions
    ]
    if len(identities) != len(set(identities)):
        raise ValueError(
            "configuration change request contains duplicate scenes"
        )
    transition_roles = [
        role_name
        for role_name in _ROLE_NAMES
        if any(
            transition["role"] == role_name
            for transition in transitions
        )
    ]
    if transition_roles != changed_roles:
        raise ValueError(
            "configuration change request changed_roles do not "
            "match transitions"
        )
    transition_count = target.get("transition_count")
    if (
        isinstance(transition_count, bool)
        or not isinstance(transition_count, int)
        or transition_count != len(transitions)
    ):
        raise ValueError(
            "configuration change request transition_count is invalid"
        )
    if (
        payload.get("review_requirements")
        != _CHANGE_REQUEST_REVIEW_REQUIREMENTS
    ):
        raise ValueError(
            "configuration change request review_requirements are invalid"
        )
    if (
        payload.get("safety_boundaries")
        != _CHANGE_REQUEST_SAFETY_BOUNDARIES
    ):
        raise ValueError(
            "configuration change request safety_boundaries are invalid"
        )
    expected_fingerprint = validated_fingerprint(
        payload.get("request_fingerprint"),
        name="configuration change request request_fingerprint",
    )
    unsigned = dict(payload)
    unsigned.pop("request_fingerprint", None)
    if not hmac.compare_digest(
        expected_fingerprint,
        fingerprint_str(unsigned),
    ):
        raise ValueError(
            "configuration change request fingerprint mismatch"
        )


def _request_verification_payload(
    *,
    status: str,
    action: str,
    reason_codes: list[str],
    identity: Mapping[str, bool],
) -> dict[str, Any]:
    return {
        "schema_version": (
            _CHANGE_REQUEST_VERIFICATION_SCHEMA_VERSION
        ),
        "status": status,
        "action": action,
        "reason_codes": reason_codes,
        "identity": dict(identity),
        "authorizes_configuration_change": False,
        "configuration_change_applied": False,
        "model_execution_performed": False,
    }


def verify_write_model_configuration_change_request(
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a request against its current promotion evidence."""

    validate_write_model_configuration_change_request(receipt)
    source = require_mapping(
        receipt.get("source_promotion_proposal"),
        name="configuration change request source_promotion_proposal",
    )
    source_path = absolute_path(
        _required_text(
            source.get("path"),
            name="source_promotion_proposal.path",
        ),
        name="source_promotion_proposal.path",
    )
    identity = {
        "promotion_proposal_file_fingerprint": False,
        "promotion_proposal_content_fingerprint": False,
        "promotion_proposal_current": False,
        "request_fingerprint": False,
    }
    if not source_path.is_file() or not hmac.compare_digest(
        validated_fingerprint(
            source.get("fingerprint"),
            name="source_promotion_proposal.fingerprint",
        ),
        file_fingerprint(source_path),
    ):
        return _request_verification_payload(
            status="stale_promotion_proposal",
            action="stop",
            reason_codes=["promotion_proposal_file_fingerprint_changed"],
            identity=identity,
        )
    identity["promotion_proposal_file_fingerprint"] = True
    _resolved, proposal = (
        load_write_model_challenger_promotion_proposal(source_path)
    )
    identity["promotion_proposal_content_fingerprint"] = (
        hmac.compare_digest(
            validated_fingerprint(
                source.get("proposal_fingerprint"),
                name="source_promotion_proposal.proposal_fingerprint",
            ),
            validated_fingerprint(
                proposal.get("proposal_fingerprint"),
                name="promotion proposal proposal_fingerprint",
            ),
        )
    )
    if not identity["promotion_proposal_content_fingerprint"]:
        return _request_verification_payload(
            status="stale_promotion_proposal",
            action="stop",
            reason_codes=["promotion_proposal_fingerprint_changed"],
            identity=identity,
        )
    promotion_verification = (
        verify_write_model_challenger_promotion_proposal(proposal)
    )
    identity["promotion_proposal_current"] = (
        promotion_verification.get("status") == "current"
    )
    if not identity["promotion_proposal_current"]:
        raw_reasons = promotion_verification.get("reason_codes")
        reasons = (
            [
                f"promotion_{str(reason)}"
                for reason in raw_reasons
            ]
            if isinstance(raw_reasons, list) and raw_reasons
            else ["promotion_proposal_not_current"]
        )
        return _request_verification_payload(
            status="promotion_proposal_not_current",
            action="stop",
            reason_codes=reasons,
            identity=identity,
        )
    try:
        current = build_write_model_configuration_change_request(
            source_path
        )
    except WriteModelConfigurationChangeBlockedError:
        return _request_verification_payload(
            status="request_no_longer_eligible",
            action="stop",
            reason_codes=[
                "promotion_proposal_no_longer_has_unambiguous_transitions"
            ],
            identity=identity,
        )
    identity["request_fingerprint"] = hmac.compare_digest(
        validated_fingerprint(
            receipt.get("request_fingerprint"),
            name="configuration change request request_fingerprint",
        ),
        validated_fingerprint(
            current.get("request_fingerprint"),
            name="current configuration change request fingerprint",
        ),
    )
    if not identity["request_fingerprint"]:
        return _request_verification_payload(
            status="request_changed",
            action="stop",
            reason_codes=["configuration_change_request_changed"],
            identity=identity,
        )
    return _request_verification_payload(
        status="current",
        action="human_approval_required",
        reason_codes=[],
        identity=identity,
    )


def validate_write_model_configuration_change_approval_request(
    payload: Mapping[str, Any],
) -> None:
    """Validate one explicit human confirmation for a future change."""

    _validate_exact_fields(
        payload,
        expected=_APPROVAL_REQUEST_FIELDS,
        name="configuration change approval request",
    )
    constants = {
        "schema_version": _APPROVAL_REQUEST_SCHEMA_VERSION,
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
    }
    for field_name, expected in constants.items():
        if payload.get(field_name) != expected:
            raise ValueError(
                f"configuration change approval request {field_name} "
                f"must be {expected!r}"
            )
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
    _required_text(
        payload.get("rollback_reference"),
        name="rollback_reference",
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
        payload.get("configuration_change_request_fingerprint"),
        name="configuration_change_request_fingerprint",
    )
    validated_fingerprint(
        payload.get("promotion_proposal_fingerprint"),
        name="promotion_proposal_fingerprint",
    )
    if payload.get("acknowledgements") != _REQUIRED_ACKNOWLEDGEMENTS:
        raise ValueError(
            "acknowledgements must exactly match the configuration "
            "change safety list"
        )


def build_write_model_configuration_change_approval(
    *,
    approval_request: Mapping[str, Any],
    configuration_change_request_path: str | Path,
    configuration_change_request: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Issue a short-lived credential without applying configuration."""

    validate_write_model_configuration_change_approval_request(
        approval_request
    )
    validate_write_model_configuration_change_request(
        configuration_change_request
    )
    resolved_path, persisted_request = (
        load_write_model_configuration_change_request(
            configuration_change_request_path
        )
    )
    if not hmac.compare_digest(
        canonical_json_str(dict(persisted_request)),
        canonical_json_str(dict(configuration_change_request)),
    ):
        raise WriteModelConfigurationChangeBlockedError(
            "configuration change request does not match its source file"
        )
    request_verification = (
        verify_write_model_configuration_change_request(
            configuration_change_request
        )
    )
    if request_verification.get("status") != "current":
        raise WriteModelConfigurationChangeBlockedError(
            "configuration change request is not current"
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
        raise WriteModelConfigurationChangeBlockedError(
            "configuration change approval is not effective yet"
        )
    if current_time >= expires_at:
        raise WriteModelConfigurationChangeBlockedError(
            "configuration change approval has expired"
        )
    request_fingerprint = validated_fingerprint(
        configuration_change_request.get("request_fingerprint"),
        name="configuration change request request_fingerprint",
    )
    promotion_source = require_mapping(
        configuration_change_request.get(
            "source_promotion_proposal"
        ),
        name="configuration change request source_promotion_proposal",
    )
    promotion_fingerprint = validated_fingerprint(
        promotion_source.get("proposal_fingerprint"),
        name="promotion_proposal_fingerprint",
    )
    requested_fingerprints = {
        "configuration_change_request_fingerprint": (
            request_fingerprint
        ),
        "promotion_proposal_fingerprint": promotion_fingerprint,
    }
    for field_name, actual in requested_fingerprints.items():
        requested = validated_fingerprint(
            approval_request.get(field_name),
            name=field_name,
        )
        if not hmac.compare_digest(requested, actual):
            raise WriteModelConfigurationChangeBlockedError(
                f"approval request {field_name} does not match"
            )
    payload: dict[str, Any] = {
        "schema_version": _APPROVAL_SCHEMA_VERSION,
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
        "status": _APPROVAL_STATUS,
        "approved_by": approval_request["approved_by"],
        "approval_reference": approval_request[
            "approval_reference"
        ],
        "rollback_reference": approval_request[
            "rollback_reference"
        ],
        "approved_at": _format_utc(approved_at),
        "expires_at": _format_utc(expires_at),
        "configuration_change_request_source": {
            "path": str(resolved_path),
            "fingerprint": file_fingerprint(resolved_path),
            "request_fingerprint": request_fingerprint,
        },
        **requested_fingerprints,
        "approval_request_fingerprint": fingerprint_str(
            dict(approval_request)
        ),
        "configuration_change_request": dict(
            configuration_change_request
        ),
        "maximum_uses": 1,
        "acknowledgements": list(_REQUIRED_ACKNOWLEDGEMENTS),
        "safety_boundaries": list(_APPROVAL_SAFETY_BOUNDARIES),
    }
    payload["approval_fingerprint"] = fingerprint_str(payload)
    validate_write_model_configuration_change_approval(payload)
    return payload


def validate_write_model_configuration_change_approval(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict, short-lived configuration change approval."""

    _validate_exact_fields(
        payload,
        expected=_APPROVAL_FIELDS,
        name="configuration change approval",
    )
    constants = {
        "schema_version": _APPROVAL_SCHEMA_VERSION,
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
        "status": _APPROVAL_STATUS,
    }
    for field_name, expected in constants.items():
        if payload.get(field_name) != expected:
            raise ValueError(
                f"configuration change approval {field_name} "
                f"must be {expected!r}"
            )
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
    _required_text(
        payload.get("rollback_reference"),
        name="rollback_reference",
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
    source = require_mapping(
        payload.get("configuration_change_request_source"),
        name="configuration_change_request_source",
    )
    _validate_exact_fields(
        source,
        expected=_CHANGE_REQUEST_SOURCE_FIELDS,
        name="configuration_change_request_source",
    )
    absolute_path(
        _required_text(
            source.get("path"),
            name="configuration_change_request_source.path",
        ),
        name="configuration_change_request_source.path",
    )
    validated_fingerprint(
        source.get("fingerprint"),
        name="configuration_change_request_source.fingerprint",
    )
    source_request_fingerprint = validated_fingerprint(
        source.get("request_fingerprint"),
        name="configuration_change_request_source.request_fingerprint",
    )
    request_fingerprint = validated_fingerprint(
        payload.get("configuration_change_request_fingerprint"),
        name="configuration_change_request_fingerprint",
    )
    promotion_fingerprint = validated_fingerprint(
        payload.get("promotion_proposal_fingerprint"),
        name="promotion_proposal_fingerprint",
    )
    validated_fingerprint(
        payload.get("approval_request_fingerprint"),
        name="approval_request_fingerprint",
    )
    embedded_request = require_mapping(
        payload.get("configuration_change_request"),
        name="configuration_change_request",
    )
    validate_write_model_configuration_change_request(
        embedded_request
    )
    embedded_request_fingerprint = validated_fingerprint(
        embedded_request.get("request_fingerprint"),
        name="embedded configuration change request fingerprint",
    )
    if not (
        hmac.compare_digest(
            source_request_fingerprint,
            request_fingerprint,
        )
        and hmac.compare_digest(
            request_fingerprint,
            embedded_request_fingerprint,
        )
    ):
        raise ValueError(
            "configuration change approval request fingerprints "
            "are inconsistent"
        )
    embedded_promotion_source = require_mapping(
        embedded_request.get("source_promotion_proposal"),
        name="embedded source_promotion_proposal",
    )
    embedded_promotion_fingerprint = validated_fingerprint(
        embedded_promotion_source.get("proposal_fingerprint"),
        name="embedded promotion proposal fingerprint",
    )
    if not hmac.compare_digest(
        promotion_fingerprint,
        embedded_promotion_fingerprint,
    ):
        raise ValueError(
            "configuration change approval promotion fingerprint "
            "is inconsistent"
        )
    if payload.get("maximum_uses") != 1:
        raise ValueError("maximum_uses must be 1")
    if payload.get("acknowledgements") != _REQUIRED_ACKNOWLEDGEMENTS:
        raise ValueError(
            "acknowledgements must exactly match the configuration "
            "change safety list"
        )
    if payload.get("safety_boundaries") != _APPROVAL_SAFETY_BOUNDARIES:
        raise ValueError(
            "configuration change approval safety_boundaries are invalid"
        )
    expected_fingerprint = validated_fingerprint(
        payload.get("approval_fingerprint"),
        name="approval_fingerprint",
    )
    unsigned = dict(payload)
    unsigned.pop("approval_fingerprint", None)
    if not hmac.compare_digest(
        expected_fingerprint,
        fingerprint_str(unsigned),
    ):
        raise ValueError(
            "configuration change approval fingerprint mismatch"
        )


def _approval_verification_payload(
    *,
    approval: Mapping[str, Any],
    checked_at: datetime,
    status: str,
    action: str,
    reason_codes: list[str],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": _APPROVAL_VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "action": action,
        "reason_codes": reason_codes,
        "identity": dict(identity),
        "effective_window": {
            "approved_at": approval["approved_at"],
            "expires_at": approval["expires_at"],
            "checked_at": _format_utc(checked_at),
        },
        "eligible_for_future_single_use_application": (
            status == "approved"
        ),
        "maximum_uses": 1,
        "configuration_change_applied": False,
        "approval_consumed": False,
        "model_execution_performed": False,
        "safety_boundaries": list(_APPROVAL_SAFETY_BOUNDARIES),
    }


def verify_write_model_configuration_change_approval(
    approval: Mapping[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    """Verify approval currentness without consuming or applying it."""

    validate_write_model_configuration_change_approval(approval)
    checked_at = _normalize_now(now)
    source = require_mapping(
        approval.get("configuration_change_request_source"),
        name="configuration_change_request_source",
    )
    source_path = absolute_path(
        _required_text(
            source.get("path"),
            name="configuration_change_request_source.path",
        ),
        name="configuration_change_request_source.path",
    )
    identity: dict[str, Any] = {
        "configuration_change_request_file_fingerprint": False,
        "embedded_request_matches_source": False,
        "configuration_change_request_fingerprint": False,
        "promotion_proposal_fingerprint": False,
        "configuration_change_request_status": "not_checked",
    }
    if not source_path.is_file() or not hmac.compare_digest(
        validated_fingerprint(
            source.get("fingerprint"),
            name="configuration_change_request_source.fingerprint",
        ),
        file_fingerprint(source_path),
    ):
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="stale_configuration_change_request",
            action="stop",
            reason_codes=[
                "configuration_change_request_file_fingerprint_changed"
            ],
            identity=identity,
        )
    identity["configuration_change_request_file_fingerprint"] = True
    _resolved, current_request = (
        load_write_model_configuration_change_request(source_path)
    )
    embedded_request = require_mapping(
        approval.get("configuration_change_request"),
        name="configuration_change_request",
    )
    identity["embedded_request_matches_source"] = hmac.compare_digest(
        canonical_json_str(dict(embedded_request)),
        canonical_json_str(current_request),
    )
    identity["configuration_change_request_fingerprint"] = (
        hmac.compare_digest(
            validated_fingerprint(
                approval.get(
                    "configuration_change_request_fingerprint"
                ),
                name="configuration_change_request_fingerprint",
            ),
            validated_fingerprint(
                current_request.get("request_fingerprint"),
                name="current request fingerprint",
            ),
        )
    )
    promotion_source = require_mapping(
        current_request.get("source_promotion_proposal"),
        name="source_promotion_proposal",
    )
    identity["promotion_proposal_fingerprint"] = hmac.compare_digest(
        validated_fingerprint(
            approval.get("promotion_proposal_fingerprint"),
            name="promotion_proposal_fingerprint",
        ),
        validated_fingerprint(
            promotion_source.get("proposal_fingerprint"),
            name="current promotion proposal fingerprint",
        ),
    )
    if not identity["embedded_request_matches_source"]:
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="stale_configuration_change_request",
            action="stop",
            reason_codes=[
                "embedded_configuration_change_request_changed"
            ],
            identity=identity,
        )
    if not identity["configuration_change_request_fingerprint"]:
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="stale_configuration_change_request",
            action="stop",
            reason_codes=[
                "configuration_change_request_fingerprint_changed"
            ],
            identity=identity,
        )
    if not identity["promotion_proposal_fingerprint"]:
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="stale_promotion_proposal",
            action="stop",
            reason_codes=["promotion_proposal_fingerprint_changed"],
            identity=identity,
        )
    request_verification = (
        verify_write_model_configuration_change_request(
            current_request
        )
    )
    request_status = str(
        request_verification.get("status") or "unknown"
    )
    identity["configuration_change_request_status"] = request_status
    if request_status != "current":
        raw_reasons = request_verification.get("reason_codes")
        reasons = (
            [str(reason) for reason in raw_reasons]
            if isinstance(raw_reasons, list) and raw_reasons
            else ["configuration_change_request_not_current"]
        )
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="configuration_change_request_not_current",
            action="stop",
            reason_codes=reasons,
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
            action="stop",
            reason_codes=["configuration_change_approval_not_effective_yet"],
            identity=identity,
        )
    if checked_at >= expires_at:
        return _approval_verification_payload(
            approval=approval,
            checked_at=checked_at,
            status="expired",
            action="stop",
            reason_codes=["configuration_change_approval_expired"],
            identity=identity,
        )
    return _approval_verification_payload(
        approval=approval,
        checked_at=checked_at,
        status="approved",
        action="separate_application_command_required",
        reason_codes=[
            "eligible_for_one_future_configuration_change"
        ],
        identity=identity,
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
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"invalid {name} JSON: {target}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be an object: {target}")
    return target, raw


def load_write_model_configuration_change_request(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one configuration change request."""

    target, payload = _load_json_object(
        path,
        name="configuration change request",
    )
    validate_write_model_configuration_change_request(payload)
    return target, payload


def load_write_model_configuration_change_approval_request(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one human configuration approval request."""

    target, payload = _load_json_object(
        path,
        name="configuration change approval request",
    )
    validate_write_model_configuration_change_approval_request(payload)
    return target, payload


def load_write_model_configuration_change_approval(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one configuration change approval."""

    target, payload = _load_json_object(
        path,
        name="configuration change approval",
    )
    validate_write_model_configuration_change_approval(payload)
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
            existing = json.loads(
                target.read_text(encoding="utf-8")
            )
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


def persist_write_model_configuration_change_request(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist an immutable configuration change request."""

    validate_write_model_configuration_change_request(payload)
    return _persist_immutable(payload, path)


def persist_write_model_configuration_change_approval(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist an immutable configuration change approval."""

    validate_write_model_configuration_change_approval(payload)
    return _persist_immutable(payload, path)


def format_write_model_configuration_change_request_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact operator-facing request report."""

    target = require_mapping(
        payload.get("target"),
        name="configuration change request target",
    )
    changed_roles = target.get("changed_roles", [])
    if not isinstance(changed_roles, list):
        raise TypeError(
            "configuration change request target changed_roles must be a list"
        )
    return (
        "",
        "=" * 60,
        "Challenger configuration change request",
        "-" * 60,
        f"  Status      : {payload.get('status', 'unknown')}",
        f"  Ticker      : {payload.get('ticker', 'unknown')}",
        "  Changed roles: "
        + ", ".join(
            str(value)
            for value in changed_roles
        ),
        f"  Scene changes: {target.get('transition_count', 0)}",
        "  Boundary    : review only; configuration unchanged",
        "=" * 60,
        "",
    )


def format_write_model_configuration_change_request_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact request-currentness report."""

    reason_codes = payload.get("reason_codes")
    reasons = (
        ", ".join(str(value) for value in reason_codes)
        if isinstance(reason_codes, list) and reason_codes
        else "none"
    )
    return (
        "",
        "=" * 60,
        "Configuration change request verification",
        "-" * 60,
        f"  Status   : {payload.get('status', 'unknown')}",
        f"  Action   : {payload.get('action', 'unknown')}",
        f"  Reasons  : {reasons}",
        "  Boundary : no configuration application; no model execution",
        "=" * 60,
        "",
    )


def format_write_model_configuration_change_approval_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact approval issuance report."""

    return (
        "",
        "=" * 60,
        "Configuration change approval credential",
        "-" * 60,
        f"  Status    : {payload.get('status', 'unknown')}",
        f"  Approved by: {payload.get('approved_by', 'unknown')}",
        f"  Reference : {payload.get('approval_reference', 'unknown')}",
        f"  Rollback  : {payload.get('rollback_reference', 'unknown')}",
        f"  Expires at: {payload.get('expires_at', 'unknown')}",
        "  Boundary  : issued only; not consumed or applied",
        "=" * 60,
        "",
    )


def format_write_model_configuration_change_approval_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact approval verification report."""

    reason_codes = payload.get("reason_codes")
    reasons = (
        ", ".join(str(value) for value in reason_codes)
        if isinstance(reason_codes, list) and reason_codes
        else "none"
    )
    return (
        "",
        "=" * 60,
        "Configuration change approval verification",
        "-" * 60,
        f"  Status   : {payload.get('status', 'unknown')}",
        f"  Action   : {payload.get('action', 'unknown')}",
        f"  Reasons  : {reasons}",
        "  Applied  : no",
        "  Consumed : no",
        "=" * 60,
        "",
    )


__all__ = [
    "WriteModelConfigurationChangeBlockedError",
    "build_write_model_configuration_change_approval",
    "build_write_model_configuration_change_request",
    "format_write_model_configuration_change_approval_report",
    "format_write_model_configuration_change_approval_verification_report",
    "format_write_model_configuration_change_request_report",
    "format_write_model_configuration_change_request_verification_report",
    "load_write_model_configuration_change_approval",
    "load_write_model_configuration_change_approval_request",
    "load_write_model_configuration_change_request",
    "persist_write_model_configuration_change_approval",
    "persist_write_model_configuration_change_request",
    "validate_write_model_configuration_change_approval",
    "validate_write_model_configuration_change_approval_request",
    "validate_write_model_configuration_change_request",
    "verify_write_model_configuration_change_approval",
    "verify_write_model_configuration_change_request",
]
