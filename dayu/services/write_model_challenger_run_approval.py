"""Authorize one bounded, isolated Champion/Challenger write experiment."""

from __future__ import annotations

import hmac
import json
import math
import os
import re
import tempfile
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from dayu.services._write_artifact_utils import (
    canonical_json_str,
    file_fingerprint,
    fingerprint_str,
    require_mapping,
    serialize_pretty,
    validated_fingerprint,
)
from dayu.services.write_model_challenger_preflight_approval import (
    validate_write_model_challenger_preflight_approval,
    verify_write_model_challenger_preflight_approval,
)
from dayu.services.write_model_challenger_proposal import (
    validate_write_model_challenger_proposal,
)
from dayu.services.write_model_challenger_verification import (
    verify_write_model_challenger_proposal,
)

_PLAN_SCHEMA_VERSION = "write_model_challenger_run_plan_v1"
_REQUEST_SCHEMA_VERSION = (
    "write_model_challenger_run_approval_request_v1"
)
_APPROVAL_SCHEMA_VERSION = "write_model_challenger_run_approval_v1"
_VERIFICATION_SCHEMA_VERSION = (
    "write_model_challenger_run_approval_verification_v1"
)
_CONSUMPTION_SCHEMA_VERSION = (
    "write_model_challenger_run_approval_consumption_v1"
)
_APPROVAL_TYPE = "write_model_challenger_isolated_run"
_APPROVAL_SCOPE = "one_bounded_isolated_champion_challenger_run"
_APPROVAL_STATUS = "approved_for_one_isolated_run"
_MAX_APPROVAL_VALIDITY = timedelta(hours=4)
_MAX_COST_DECIMAL_PLACES = 8
_MODEL_ROLES = {"primary", "audit"}
_ROLE_ARGUMENTS = {
    "--challenger-model-name",
    "--challenger-audit-model-name",
}
_REQUIRED_ACKNOWLEDGEMENTS = [
    "authorizes_champion_and_challenger_model_execution",
    "preflight_must_pass_before_execution",
    "isolated_outputs_are_new_and_distinct",
    "per_run_budget_applies_to_each_run_separately",
    "authorization_is_single_use",
    "no_configuration_change_authorization",
    "no_challenger_promotion_authorization",
]
_SAFETY_BOUNDARIES = [
    "one_champion_run_and_one_challenger_run_only",
    "automatic_preflight_must_pass_before_model_execution",
    "outputs_must_be_new_isolated_directories",
    "budget_is_enforced_per_run",
    "approval_is_consumed_before_host_initialization",
    "approval_does_not_authorize_configuration_change",
    "approval_does_not_authorize_challenger_promotion",
]
_PLAN_FIELDS = {
    "schema_version",
    "ticker",
    "template",
    "outputs",
    "models",
    "execution",
    "budget",
    "plan_fingerprint",
}
_TEMPLATE_FIELDS = {"path", "fingerprint"}
_OUTPUT_FIELDS = {"champion", "challenger"}
_MODEL_FIELDS = {
    "current",
    "challenger_cli_args",
    "fallback",
}
_EXECUTION_FIELDS = {
    "write_max_retries",
    "web_provider",
    "temperature",
    "resume",
}
_BUDGET_FIELDS = {
    "maximum_model_requests_per_run",
    "maximum_total_tokens_per_run",
    "maximum_estimated_cost_per_run",
    "maximum_estimated_experiment_cost",
    "currency",
}
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
    "preflight_approval_fingerprint",
    "execution_plan",
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
    "preflight_approval_fingerprint",
    "request_fingerprint",
    "execution_plan",
    "maximum_uses",
    "acknowledgements",
    "safety_boundaries",
    "approval_fingerprint",
}


class WriteModelChallengerRunApprovalBlockedError(ValueError):
    """Raised when a valid request is not safe to approve."""


class WriteModelChallengerRunApprovalConsumedError(RuntimeError):
    """Raised when a single-use run approval was already consumed."""


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
    maximum_length: int,
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
        raise ValueError("run approval validity cannot exceed 4 hours")


def _positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _non_negative_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def _normalized_cost(value: object, *, name: str) -> str:
    if not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{name} must be numeric")
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{name} must be greater than zero")
    exponent = amount.normalize().as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError(f"{name} must be finite")
    if exponent < -_MAX_COST_DECIMAL_PLACES:
        raise ValueError(
            f"{name} supports at most "
            f"{_MAX_COST_DECIMAL_PLACES} decimal places"
        )
    return format(amount.normalize(), "f")


def _validated_currency(value: object) -> str:
    currency = _required_text(
        value,
        name="currency",
        maximum_length=12,
    ).upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_-]{1,11}", currency):
        raise ValueError("currency is invalid")
    return currency


def _validated_model_mapping(
    value: object,
    *,
    name: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    result: dict[str, str] = {}
    for raw_role, raw_model_name in value.items():
        role = str(raw_role).strip()
        if role not in _MODEL_ROLES or role in result:
            raise ValueError(f"{name} contains an invalid model role")
        model_name = _required_text(
            raw_model_name,
            name=f"{name}.{role}",
            maximum_length=200,
        )
        if (
            model_name.startswith("-")
            or any(character.isspace() for character in model_name)
        ):
            raise ValueError(f"{name}.{role} is invalid")
        result[role] = model_name
    return result


def _validated_challenger_args(value: object) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError("challenger_cli_args must be a string array")
    if not value or len(value) % 2:
        raise ValueError(
            "challenger_cli_args must contain flag/value pairs"
        )
    seen: set[str] = set()
    for index in range(0, len(value), 2):
        flag = value[index]
        model_name = _required_text(
            value[index + 1],
            name="challenger model name",
            maximum_length=200,
        )
        if flag not in _ROLE_ARGUMENTS:
            raise ValueError("unsupported Challenger run argument")
        if flag in seen:
            raise ValueError("duplicate Challenger run argument")
        if (
            model_name.startswith("-")
            or any(character.isspace() for character in model_name)
        ):
            raise ValueError("invalid Challenger model name")
        seen.add(flag)
    return list(value)


def _validated_absolute_path(
    value: object,
    *,
    name: str,
) -> Path:
    text = _required_text(
        value,
        name=name,
        maximum_length=4096,
    )
    path = Path(text)
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path")
    return path.resolve()


def build_write_model_challenger_run_plan(
    *,
    ticker: str,
    template_path: str | Path,
    champion_output_dir: str | Path,
    challenger_output_dir: str | Path,
    current_models: Mapping[str, str],
    challenger_cli_args: list[str],
    fallback_models: Mapping[str, str],
    write_max_retries: int,
    web_provider: str,
    temperature: float | None,
    maximum_model_requests_per_run: int,
    maximum_total_tokens_per_run: int,
    maximum_estimated_cost_per_run: float,
    budget_currency: str,
) -> dict[str, Any]:
    """Build the exact, immutable plan later bound by human approval."""

    normalized_ticker = _required_text(
        ticker,
        name="ticker",
        maximum_length=64,
    ).upper()
    resolved_template = Path(template_path).expanduser().resolve()
    if not resolved_template.is_file():
        raise FileNotFoundError(
            f"write template does not exist: {resolved_template}"
        )
    champion_output = Path(
        champion_output_dir
    ).expanduser().resolve()
    challenger_output = Path(
        challenger_output_dir
    ).expanduser().resolve()
    if champion_output == challenger_output:
        raise ValueError(
            "Champion and Challenger outputs must be different"
        )
    normalized_current_models = _validated_model_mapping(
        current_models,
        name="current_models",
    )
    if not normalized_current_models:
        raise ValueError("current_models must not be empty")
    normalized_fallback_models = _validated_model_mapping(
        fallback_models,
        name="fallback_models",
    )
    normalized_challenger_args = _validated_challenger_args(
        challenger_cli_args
    )
    normalized_retries = _non_negative_integer(
        write_max_retries,
        name="write_max_retries",
    )
    normalized_web_provider = _required_text(
        web_provider,
        name="web_provider",
        maximum_length=100,
    )
    if temperature is not None:
        if isinstance(temperature, bool) or not isinstance(
            temperature,
            (int, float),
        ):
            raise ValueError("temperature must be numeric or null")
        if not math.isfinite(float(temperature)):
            raise ValueError("temperature must be finite")
        normalized_temperature: float | None = float(temperature)
    else:
        normalized_temperature = None
    maximum_requests = _positive_integer(
        maximum_model_requests_per_run,
        name="maximum_model_requests_per_run",
    )
    maximum_tokens = _positive_integer(
        maximum_total_tokens_per_run,
        name="maximum_total_tokens_per_run",
    )
    maximum_cost = _normalized_cost(
        maximum_estimated_cost_per_run,
        name="maximum_estimated_cost_per_run",
    )
    experiment_cost = _normalized_cost(
        Decimal(maximum_cost) * 2,
        name="maximum_estimated_experiment_cost",
    )
    currency = _validated_currency(budget_currency)

    payload: dict[str, Any] = {
        "schema_version": _PLAN_SCHEMA_VERSION,
        "ticker": normalized_ticker,
        "template": {
            "path": str(resolved_template),
            "fingerprint": file_fingerprint(resolved_template),
        },
        "outputs": {
            "champion": str(champion_output),
            "challenger": str(challenger_output),
        },
        "models": {
            "current": normalized_current_models,
            "challenger_cli_args": normalized_challenger_args,
            "fallback": normalized_fallback_models,
        },
        "execution": {
            "write_max_retries": normalized_retries,
            "web_provider": normalized_web_provider,
            "temperature": normalized_temperature,
            "resume": False,
        },
        "budget": {
            "maximum_model_requests_per_run": maximum_requests,
            "maximum_total_tokens_per_run": maximum_tokens,
            "maximum_estimated_cost_per_run": maximum_cost,
            "maximum_estimated_experiment_cost": experiment_cost,
            "currency": currency,
        },
    }
    payload["plan_fingerprint"] = fingerprint_str(payload)
    validate_write_model_challenger_run_plan(payload)
    return payload


def validate_write_model_challenger_run_plan(
    payload: Mapping[str, Any],
) -> None:
    """Validate a run plan and its content fingerprint."""

    _validate_exact_fields(
        payload,
        expected=_PLAN_FIELDS,
        name="Challenger run plan",
    )
    if payload.get("schema_version") != _PLAN_SCHEMA_VERSION:
        raise ValueError("unsupported Challenger run plan schema")
    _required_text(
        payload.get("ticker"),
        name="ticker",
        maximum_length=64,
    )
    template = require_mapping(payload.get("template"), name="template")
    _validate_exact_fields(
        template,
        expected=_TEMPLATE_FIELDS,
        name="template",
    )
    _validated_absolute_path(template.get("path"), name="template.path")
    validated_fingerprint(
        template.get("fingerprint"),
        name="template.fingerprint",
    )
    outputs = require_mapping(payload.get("outputs"), name="outputs")
    _validate_exact_fields(
        outputs,
        expected=_OUTPUT_FIELDS,
        name="outputs",
    )
    champion_output = _validated_absolute_path(
        outputs.get("champion"),
        name="outputs.champion",
    )
    challenger_output = _validated_absolute_path(
        outputs.get("challenger"),
        name="outputs.challenger",
    )
    if champion_output == challenger_output:
        raise ValueError(
            "Champion and Challenger outputs must be different"
        )
    models = require_mapping(payload.get("models"), name="models")
    _validate_exact_fields(
        models,
        expected=_MODEL_FIELDS,
        name="models",
    )
    current_models = _validated_model_mapping(
        models.get("current"),
        name="models.current",
    )
    if not current_models:
        raise ValueError("models.current must not be empty")
    _validated_model_mapping(
        models.get("fallback"),
        name="models.fallback",
    )
    _validated_challenger_args(models.get("challenger_cli_args"))
    execution = require_mapping(payload.get("execution"), name="execution")
    _validate_exact_fields(
        execution,
        expected=_EXECUTION_FIELDS,
        name="execution",
    )
    _non_negative_integer(
        execution.get("write_max_retries"),
        name="execution.write_max_retries",
    )
    _required_text(
        execution.get("web_provider"),
        name="execution.web_provider",
        maximum_length=100,
    )
    temperature = execution.get("temperature")
    if temperature is not None and (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not math.isfinite(float(temperature))
    ):
        raise ValueError("execution.temperature must be finite or null")
    if execution.get("resume") is not False:
        raise ValueError("execution.resume must be false")
    budget = require_mapping(payload.get("budget"), name="budget")
    _validate_exact_fields(
        budget,
        expected=_BUDGET_FIELDS,
        name="budget",
    )
    _positive_integer(
        budget.get("maximum_model_requests_per_run"),
        name="budget.maximum_model_requests_per_run",
    )
    _positive_integer(
        budget.get("maximum_total_tokens_per_run"),
        name="budget.maximum_total_tokens_per_run",
    )
    per_run_cost = _normalized_cost(
        budget.get("maximum_estimated_cost_per_run"),
        name="budget.maximum_estimated_cost_per_run",
    )
    experiment_cost = _normalized_cost(
        budget.get("maximum_estimated_experiment_cost"),
        name="budget.maximum_estimated_experiment_cost",
    )
    if Decimal(experiment_cost) != Decimal(per_run_cost) * 2:
        raise ValueError(
            "maximum_estimated_experiment_cost must equal "
            "twice the per-run cost"
        )
    _validated_currency(budget.get("currency"))
    expected = validated_fingerprint(
        payload.get("plan_fingerprint"),
        name="plan_fingerprint",
    )
    unsigned = dict(payload)
    unsigned.pop("plan_fingerprint", None)
    if not hmac.compare_digest(expected, fingerprint_str(unsigned)):
        raise ValueError("Challenger run plan fingerprint mismatch")


def validate_write_model_challenger_run_approval_request(
    payload: Mapping[str, Any],
) -> None:
    """Validate one explicit human request for a single isolated run."""

    _validate_exact_fields(
        payload,
        expected=_REQUEST_FIELDS,
        name="Challenger run approval request",
    )
    if payload.get("schema_version") != _REQUEST_SCHEMA_VERSION:
        raise ValueError(
            "unsupported Challenger run approval request schema"
        )
    if payload.get("approval_type") != _APPROVAL_TYPE:
        raise ValueError("unsupported Challenger run approval type")
    if payload.get("scope") != _APPROVAL_SCOPE:
        raise ValueError("Challenger run approval scope is invalid")
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
        payload.get("preflight_approval_fingerprint"),
        name="preflight_approval_fingerprint",
    )
    execution_plan = require_mapping(
        payload.get("execution_plan"),
        name="execution_plan",
    )
    validate_write_model_challenger_run_plan(execution_plan)
    if payload.get("acknowledgements") != _REQUIRED_ACKNOWLEDGEMENTS:
        raise ValueError(
            "acknowledgements must exactly match the run safety list"
        )


def build_write_model_challenger_run_approval(
    *,
    request: Mapping[str, Any],
    preflight_approval: Mapping[str, Any],
    proposal_receipt: Mapping[str, Any],
    current_proposal: Mapping[str, Any],
    actual_execution_plan: Mapping[str, Any],
    preflight_passed: bool,
    now: datetime,
) -> dict[str, Any]:
    """Build a single-use approval after an approved preflight passes."""

    validate_write_model_challenger_run_approval_request(request)
    validate_write_model_challenger_preflight_approval(
        preflight_approval
    )
    validate_write_model_challenger_proposal(proposal_receipt)
    validate_write_model_challenger_proposal(current_proposal)
    validate_write_model_challenger_run_plan(actual_execution_plan)
    if not preflight_passed:
        raise WriteModelChallengerRunApprovalBlockedError(
            "common preflight did not pass"
        )

    proposal_verification = verify_write_model_challenger_proposal(
        proposal_receipt,
        current_proposal,
    )
    if proposal_verification.get("status") != "current":
        raise WriteModelChallengerRunApprovalBlockedError(
            "Challenger proposal is not current"
        )
    if current_proposal.get("status") != "ready":
        raise WriteModelChallengerRunApprovalBlockedError(
            "Challenger proposal is not ready"
        )
    models = require_mapping(
        actual_execution_plan.get("models"),
        name="actual_execution_plan.models",
    )
    current_models = _validated_model_mapping(
        models.get("current"),
        name="actual_execution_plan.models.current",
    )
    challenger_args = _validated_challenger_args(
        models.get("challenger_cli_args")
    )
    preflight_verification = (
        verify_write_model_challenger_preflight_approval(
            approval=preflight_approval,
            proposal_receipt=proposal_receipt,
            current_proposal=current_proposal,
            actual_cli_args=[
                "--preflight-only",
                *challenger_args,
            ],
            actual_current_models=current_models,
            now=now,
        )
    )
    if (
        preflight_verification.get("preflight_authorized")
        is not True
    ):
        raise WriteModelChallengerRunApprovalBlockedError(
            "common preflight approval is not current"
        )

    current_time = _normalize_now(now)
    approved_at = _parse_utc_timestamp(
        request.get("approved_at"),
        name="approved_at",
    )
    expires_at = _parse_utc_timestamp(
        request.get("expires_at"),
        name="expires_at",
    )
    if current_time < approved_at:
        raise WriteModelChallengerRunApprovalBlockedError(
            "run approval is not effective yet"
        )
    if current_time >= expires_at:
        raise WriteModelChallengerRunApprovalBlockedError(
            "run approval has expired"
        )

    evidence_window = require_mapping(
        current_proposal.get("evidence_window"),
        name="proposal evidence_window",
    )
    identities = {
        "proposal_fingerprint": validated_fingerprint(
            current_proposal.get("proposal_fingerprint"),
            name="proposal_fingerprint",
        ),
        "history_fingerprint": validated_fingerprint(
            evidence_window.get("history_fingerprint"),
            name="history_fingerprint",
        ),
        "preflight_approval_fingerprint": validated_fingerprint(
            preflight_approval.get("approval_fingerprint"),
            name="preflight_approval_fingerprint",
        ),
    }
    for name, actual in identities.items():
        requested = validated_fingerprint(
            request.get(name),
            name=name,
        )
        if not hmac.compare_digest(requested, actual):
            raise WriteModelChallengerRunApprovalBlockedError(
                f"run approval request {name} does not match"
            )
    requested_plan = require_mapping(
        request.get("execution_plan"),
        name="execution_plan",
    )
    if not hmac.compare_digest(
        canonical_json_str(dict(requested_plan)),
        canonical_json_str(dict(actual_execution_plan)),
    ):
        raise WriteModelChallengerRunApprovalBlockedError(
            "run approval request execution plan does not match"
        )

    payload: dict[str, Any] = {
        "schema_version": _APPROVAL_SCHEMA_VERSION,
        "approval_type": _APPROVAL_TYPE,
        "scope": _APPROVAL_SCOPE,
        "status": _APPROVAL_STATUS,
        "approved_by": request["approved_by"],
        "approval_reference": request["approval_reference"],
        "approved_at": _format_utc(approved_at),
        "expires_at": _format_utc(expires_at),
        **identities,
        "request_fingerprint": fingerprint_str(dict(request)),
        "execution_plan": dict(actual_execution_plan),
        "maximum_uses": 1,
        "acknowledgements": list(_REQUIRED_ACKNOWLEDGEMENTS),
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
    }
    payload["approval_fingerprint"] = fingerprint_str(payload)
    validate_write_model_challenger_run_approval(payload)
    return payload


def validate_write_model_challenger_run_approval(
    payload: Mapping[str, Any],
) -> None:
    """Validate one tamper-evident, single-use run approval."""

    _validate_exact_fields(
        payload,
        expected=_APPROVAL_FIELDS,
        name="Challenger run approval",
    )
    if payload.get("schema_version") != _APPROVAL_SCHEMA_VERSION:
        raise ValueError("unsupported Challenger run approval schema")
    if payload.get("approval_type") != _APPROVAL_TYPE:
        raise ValueError("unsupported Challenger run approval type")
    if payload.get("scope") != _APPROVAL_SCOPE:
        raise ValueError("Challenger run approval scope is invalid")
    if payload.get("status") != _APPROVAL_STATUS:
        raise ValueError("Challenger run approval status is invalid")
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
    for name in (
        "proposal_fingerprint",
        "history_fingerprint",
        "preflight_approval_fingerprint",
        "request_fingerprint",
    ):
        validated_fingerprint(payload.get(name), name=name)
    execution_plan = require_mapping(
        payload.get("execution_plan"),
        name="execution_plan",
    )
    validate_write_model_challenger_run_plan(execution_plan)
    if payload.get("maximum_uses") != 1:
        raise ValueError("maximum_uses must be 1")
    if payload.get("acknowledgements") != _REQUIRED_ACKNOWLEDGEMENTS:
        raise ValueError(
            "acknowledgements must exactly match the run safety list"
        )
    if payload.get("safety_boundaries") != _SAFETY_BOUNDARIES:
        raise ValueError(
            "safety_boundaries must exactly match the run boundary"
        )
    expected = validated_fingerprint(
        payload.get("approval_fingerprint"),
        name="approval_fingerprint",
    )
    unsigned = dict(payload)
    unsigned.pop("approval_fingerprint", None)
    if not hmac.compare_digest(expected, fingerprint_str(unsigned)):
        raise ValueError("Challenger run approval fingerprint mismatch")


def verify_write_model_challenger_run_approval(
    *,
    approval: Mapping[str, Any],
    proposal_receipt: Mapping[str, Any],
    current_proposal: Mapping[str, Any],
    actual_execution_plan: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Verify one approval against current evidence and exact CLI plan."""

    validate_write_model_challenger_run_approval(approval)
    validate_write_model_challenger_proposal(proposal_receipt)
    validate_write_model_challenger_proposal(current_proposal)
    validate_write_model_challenger_run_plan(actual_execution_plan)
    proposal_verification = verify_write_model_challenger_proposal(
        proposal_receipt,
        current_proposal,
    )
    current_window = require_mapping(
        current_proposal.get("evidence_window"),
        name="proposal evidence_window",
    )
    current_identities = {
        "history_fingerprint": validated_fingerprint(
            current_window.get("history_fingerprint"),
            name="history_fingerprint",
        ),
        "proposal_fingerprint": validated_fingerprint(
            current_proposal.get("proposal_fingerprint"),
            name="proposal_fingerprint",
        ),
    }
    identity_matches = {
        name: hmac.compare_digest(
            validated_fingerprint(approval.get(name), name=name),
            value,
        )
        for name, value in current_identities.items()
    }
    approved_plan = require_mapping(
        approval.get("execution_plan"),
        name="execution_plan",
    )
    plan_matches = hmac.compare_digest(
        canonical_json_str(dict(approved_plan)),
        canonical_json_str(dict(actual_execution_plan)),
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
    elif not identity_matches["history_fingerprint"]:
        status = "stale_history"
        reason_codes = ["approval_history_fingerprint_changed"]
    elif not identity_matches["proposal_fingerprint"]:
        status = "policy_changed"
        reason_codes = ["approval_proposal_fingerprint_changed"]
    elif current_time < approved_at:
        status = "not_effective"
        reason_codes = ["run_approval_not_effective_yet"]
    elif current_time >= expires_at:
        status = "expired"
        reason_codes = ["run_approval_expired"]
    elif not plan_matches:
        status = "command_mismatch"
        reason_codes = ["execution_plan_does_not_match_approval"]
    else:
        status = "approved"
        reason_codes = ["one_isolated_run_approved"]

    authorized = status == "approved"
    return {
        "schema_version": _VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "run_authorized": authorized,
        "action": (
            "consume_and_run_once" if authorized else "stop"
        ),
        "reason_codes": reason_codes,
        "identity": {
            "proposal_verification_status": proposal_status,
            **identity_matches,
            "execution_plan_matches": plan_matches,
        },
        "effective_window": {
            "approved_at": _format_utc(approved_at),
            "expires_at": _format_utc(expires_at),
            "checked_at": _format_utc(current_time),
        },
        "execution_plan_fingerprint": approved_plan.get(
            "plan_fingerprint"
        ),
        "maximum_uses": 1,
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
    }


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
        raise ValueError(f"invalid {name} JSON: {target}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be an object: {target}")
    return target, raw


def load_write_model_challenger_run_plan(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate an exported run plan."""

    target, payload = _load_json_object(
        path,
        name="Challenger run plan",
    )
    validate_write_model_challenger_run_plan(payload)
    return target, payload


def load_write_model_challenger_run_approval_request(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one human run approval request."""

    target, payload = _load_json_object(
        path,
        name="Challenger run approval request",
    )
    validate_write_model_challenger_run_approval_request(payload)
    return target, payload


def load_write_model_challenger_run_approval(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one single-use run approval."""

    target, payload = _load_json_object(
        path,
        name="Challenger run approval",
    )
    validate_write_model_challenger_run_approval(payload)
    return target, payload


def _persist_immutable(
    payload: Mapping[str, Any],
    target: Path,
) -> Path:
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


def persist_write_model_challenger_run_plan(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist an immutable run plan; identical content is idempotent."""

    validate_write_model_challenger_run_plan(payload)
    return _persist_immutable(
        payload,
        Path(path).expanduser().resolve(),
    )


def persist_write_model_challenger_run_approval(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist an immutable single-use run approval."""

    validate_write_model_challenger_run_approval(payload)
    return _persist_immutable(
        payload,
        Path(path).expanduser().resolve(),
    )


def consume_write_model_challenger_run_approval(
    *,
    approval: Mapping[str, Any],
    workspace_dir: str | Path,
    now: datetime,
) -> Path:
    """Atomically consume one approval by fingerprint before Host starts."""

    validate_write_model_challenger_run_approval(approval)
    current_time = _normalize_now(now)
    approval_fingerprint = validated_fingerprint(
        approval.get("approval_fingerprint"),
        name="approval_fingerprint",
    )
    digest = approval_fingerprint.removeprefix("sha256:")
    target = (
        Path(workspace_dir).expanduser().resolve()
        / ".dayu"
        / "approvals"
        / "challenger-runs"
        / f"{digest}.consumed.json"
    )
    payload = {
        "schema_version": _CONSUMPTION_SCHEMA_VERSION,
        "approval_fingerprint": approval_fingerprint,
        "execution_plan_fingerprint": require_mapping(
            approval.get("execution_plan"),
            name="execution_plan",
        ).get("plan_fingerprint"),
        "consumed_at": _format_utc(current_time),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = serialize_pretty(payload)
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
        except FileExistsError as exc:
            raise WriteModelChallengerRunApprovalConsumedError(
                "Challenger run approval was already consumed"
            ) from exc
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    return target


def format_write_model_challenger_run_approval_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact approval issuance report."""

    plan = payload.get("execution_plan")
    plan_view = plan if isinstance(plan, Mapping) else {}
    budget = plan_view.get("budget")
    budget_view = budget if isinstance(budget, Mapping) else {}
    return (
        "",
        "=" * 60,
        "Challenger 隔离双跑授权凭据",
        "=" * 60,
        f"  状态       : {payload.get('status', 'invalid')}",
        f"  审批人     : {payload.get('approved_by', 'unknown')}",
        f"  审批引用   : {payload.get('approval_reference', 'unknown')}",
        f"  失效时间   : {payload.get('expires_at', 'unknown')}",
        f"  计划指纹   : {plan_view.get('plan_fingerprint', 'unknown')}",
        (
            "  单次成本上限: "
            f"{budget_view.get('currency', '')} "
            f"{budget_view.get('maximum_estimated_cost_per_run', 'unknown')}"
        ),
        "  使用次数   : 1（Host 初始化前原子消费）",
        "  安全边界   : 仅隔离双跑；不改配置，不批准晋升",
        "=" * 60,
        "",
    )


def format_write_model_challenger_run_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format the Host-before-start run authorization decision."""

    identity = payload.get("identity")
    identity_view = identity if isinstance(identity, Mapping) else {}
    window = payload.get("effective_window")
    window_view = window if isinstance(window, Mapping) else {}
    return (
        "",
        "=" * 60,
        "Challenger 隔离双跑授权验证",
        "=" * 60,
        f"  状态       : {payload.get('status', 'invalid')}",
        (
            "  历史一致   : "
            f"{'是' if identity_view.get('history_fingerprint') is True else '否'}"
        ),
        (
            "  提案一致   : "
            f"{'是' if identity_view.get('proposal_fingerprint') is True else '否'}"
        ),
        (
            "  运行计划   : "
            f"{'一致' if identity_view.get('execution_plan_matches') is True else '不一致'}"
        ),
        f"  失效时间   : {window_view.get('expires_at', 'unknown')}",
        (
            "  下一步     : 原子消费授权并初始化 Host"
            if payload.get("run_authorized") is True
            else "  下一步     : 停止，不初始化 Host"
        ),
        "=" * 60,
        "",
    )


__all__ = [
    "WriteModelChallengerRunApprovalBlockedError",
    "WriteModelChallengerRunApprovalConsumedError",
    "build_write_model_challenger_run_approval",
    "build_write_model_challenger_run_plan",
    "consume_write_model_challenger_run_approval",
    "format_write_model_challenger_run_approval_report",
    "format_write_model_challenger_run_verification_report",
    "load_write_model_challenger_run_approval",
    "load_write_model_challenger_run_approval_request",
    "load_write_model_challenger_run_plan",
    "persist_write_model_challenger_run_approval",
    "persist_write_model_challenger_run_plan",
    "validate_write_model_challenger_run_approval",
    "validate_write_model_challenger_run_approval_request",
    "validate_write_model_challenger_run_plan",
    "verify_write_model_challenger_run_approval",
]
