"""Build an immutable, model-free plan for one bounded live write smoke run."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dayu.services.contracts import WritePreflightResult, WriteRunConfig

_SCHEMA_VERSION = "write_model_live_smoke_plan_v1"
_STATUS = "ready_for_operator_model_execution"
_DEPENDENCY_CHAPTER_TITLES = frozenset(
    {
        "投资要点概览",
        "是否值得继续深研与待验证问题",
    }
)
_MINIMUM_MODEL_REQUESTS = 64
_MINIMUM_TOTAL_TOKENS = 800_000
_SAFETY_BOUNDARIES = [
    "preflight_passed_before_plan_export",
    "one_chapter_only",
    "resume_disabled_for_fresh_output",
    "budget_limits_required_on_execution_command",
    "operator_must_run_command_explicitly",
    "plan_export_does_not_call_models",
    "plan_export_does_not_record_secret_values",
    "plan_export_does_not_change_configuration",
]
_PLAN_FIELDS = {
    "schema_version",
    "status",
    "generated_at",
    "ticker",
    "company",
    "workspace",
    "template",
    "output",
    "execution",
    "budget",
    "routing",
    "operator_command",
    "safety_boundaries",
    "model_execution_performed",
    "configuration_mutation_performed",
    "secret_values_recorded",
    "plan_fingerprint",
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fingerprint(value: object) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _file_fingerprint_if_present(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _required_text(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def _positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a positive integer")
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_cost(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return normalized


def _operator_command(
    *,
    workspace_dir: Path,
    write_config: WriteRunConfig,
) -> list[str]:
    args = [
        "dayu-cli",
        "write",
        "--workspace",
        str(workspace_dir),
        "--ticker",
        write_config.ticker,
        "--template",
        write_config.template_path,
        "--output",
        write_config.output_dir,
        "--chapter",
        write_config.chapter_filter,
        "--no-resume",
        "--write-max-retries",
        str(write_config.write_max_retries),
        "--write-max-model-requests",
        str(write_config.write_max_model_requests),
        "--write-max-total-tokens",
        str(write_config.write_max_total_tokens),
        "--write-max-estimated-cost",
        str(write_config.write_max_estimated_cost),
        "--write-budget-currency",
        write_config.write_budget_currency,
    ]
    if write_config.web_provider:
        args.extend(["--web-provider", write_config.web_provider])
    if write_config.write_model_override_name:
        args.extend(["--model-name", write_config.write_model_override_name])
    if write_config.audit_model_override_name:
        args.extend(["--audit-model-name", write_config.audit_model_override_name])
    if write_config.write_fallback_model_name:
        args.extend(["--fallback-model-name", write_config.write_fallback_model_name])
    if write_config.audit_fallback_model_name:
        args.extend(
            [
                "--audit-fallback-model-name",
                write_config.audit_fallback_model_name,
            ]
        )
    return args


def validate_live_smoke_chapter_name(chapter: object) -> str | None:
    """Return an operator-facing error when a chapter is not smoke-safe."""

    try:
        normalized = _required_text(chapter, name="chapter")
    except ValueError as exc:
        return str(exc)
    if normalized in _DEPENDENCY_CHAPTER_TITLES:
        return (
            "live smoke plan requires a standalone base chapter; "
            f"{normalized} depends on prior chapter artifacts"
        )
    return None


def validate_live_smoke_budget_limits(
    *,
    maximum_model_requests: object,
    maximum_total_tokens: object,
) -> str | None:
    """Return an operator-facing error when smoke budgets are too small."""

    try:
        request_limit = _positive_integer(
            maximum_model_requests,
            name="write_max_model_requests",
        )
        token_limit = _positive_integer(
            maximum_total_tokens,
            name="write_max_total_tokens",
        )
    except ValueError as exc:
        return str(exc)
    if request_limit < _MINIMUM_MODEL_REQUESTS:
        return (
            "live smoke plan requires at least "
            f"{_MINIMUM_MODEL_REQUESTS} --write-max-model-requests "
            "to cover infer, write, audit, repair, and confirm routing"
        )
    if token_limit < _MINIMUM_TOTAL_TOKENS:
        return (
            "live smoke plan requires at least "
            f"{_MINIMUM_TOTAL_TOKENS} --write-max-total-tokens "
            "to cover infer, write, audit, repair, and confirm routing"
        )
    return None


def build_write_model_live_smoke_plan(
    *,
    workspace_dir: str | Path,
    write_config: WriteRunConfig,
    preflight_result: WritePreflightResult,
    routing_snapshot_fingerprint: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a bounded live-smoke execution plan without calling a model."""

    if not preflight_result.ready:
        raise ValueError("live smoke plan requires a successful preflight")
    if write_config.infer:
        raise ValueError("live smoke plan cannot use --infer")
    if write_config.fast:
        raise ValueError("live smoke plan cannot use --fast")
    if write_config.force:
        raise ValueError("live smoke plan cannot use --force")
    if write_config.resume:
        raise ValueError("live smoke plan requires --no-resume")
    chapter = _required_text(write_config.chapter_filter, name="chapter")
    chapter_error = validate_live_smoke_chapter_name(chapter)
    if chapter_error is not None:
        raise ValueError(chapter_error)
    ticker = _required_text(write_config.ticker, name="ticker")
    currency = _required_text(
        write_config.write_budget_currency,
        name="write_budget_currency",
    ).upper()
    maximum_model_requests = _positive_integer(
        write_config.write_max_model_requests,
        name="write_max_model_requests",
    )
    maximum_total_tokens = _positive_integer(
        write_config.write_max_total_tokens,
        name="write_max_total_tokens",
    )
    budget_error = validate_live_smoke_budget_limits(
        maximum_model_requests=maximum_model_requests,
        maximum_total_tokens=maximum_total_tokens,
    )
    if budget_error is not None:
        raise ValueError(budget_error)
    maximum_estimated_cost = _positive_cost(
        write_config.write_max_estimated_cost,
        name="write_max_estimated_cost",
    )
    template_path = Path(write_config.template_path).expanduser().resolve()
    output_dir = Path(write_config.output_dir).expanduser().resolve()
    resolved_workspace = Path(workspace_dir).expanduser().resolve()
    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")

    scenes = [
        {
            "scene_name": scene.scene_name,
            "model_role": scene.model_role.value,
            "model_name": scene.model_name,
            "temperature": scene.temperature,
        }
        for scene in preflight_result.scenes
    ]
    required_environment_variables = sorted(
        {
            str(name).strip()
            for name in preflight_result.required_environment_variables
            if str(name).strip()
        }
    )
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "status": _STATUS,
        "generated_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "ticker": ticker,
        "company": write_config.company,
        "workspace": str(resolved_workspace),
        "template": {
            "path": str(template_path),
            "fingerprint": _file_fingerprint_if_present(template_path),
        },
        "output": {
            "path": str(output_dir),
        },
        "execution": {
            "chapter": chapter,
            "fast": False,
            "force": False,
            "infer": False,
            "resume": False,
            "write_max_retries": write_config.write_max_retries,
            "web_provider": write_config.web_provider,
        },
        "budget": {
            "maximum_model_requests": maximum_model_requests,
            "maximum_total_tokens": maximum_total_tokens,
            "maximum_estimated_cost": maximum_estimated_cost,
            "currency": currency,
        },
        "routing": {
            "snapshot_fingerprint": routing_snapshot_fingerprint,
            "scene_count": len(scenes),
            "signature_scene_count": len(preflight_result.signature_scenes),
            "fallback_scene_count": len(preflight_result.fallback_scenes),
            "signature_fallback_scene_count": len(
                preflight_result.signature_fallback_scenes
            ),
            "scenes": scenes,
            "required_environment_variables": required_environment_variables,
        },
        "operator_command": _operator_command(
            workspace_dir=resolved_workspace,
            write_config=write_config,
        ),
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
        "model_execution_performed": False,
        "configuration_mutation_performed": False,
        "secret_values_recorded": False,
    }
    payload["plan_fingerprint"] = _fingerprint(payload)
    validate_write_model_live_smoke_plan(payload)
    return payload


def validate_write_model_live_smoke_plan(payload: Mapping[str, Any]) -> None:
    """Validate a live-smoke plan and its content fingerprint."""

    actual_fields = set(payload)
    if actual_fields != _PLAN_FIELDS:
        raise ValueError("live smoke plan fields are invalid")
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("unsupported live smoke plan schema")
    if payload.get("status") != _STATUS:
        raise ValueError("live smoke plan status is invalid")
    for field_name in (
        "ticker",
        "workspace",
        "safety_boundaries",
        "operator_command",
    ):
        if not payload.get(field_name):
            raise ValueError(f"{field_name} is required")
    if payload.get("model_execution_performed") is not False:
        raise ValueError("model execution flag is invalid")
    if payload.get("configuration_mutation_performed") is not False:
        raise ValueError("configuration mutation flag is invalid")
    if payload.get("secret_values_recorded") is not False:
        raise ValueError("secret recording flag is invalid")
    budget = payload.get("budget")
    if not isinstance(budget, Mapping):
        raise ValueError("budget is invalid")
    maximum_model_requests = _positive_integer(
        budget.get("maximum_model_requests"),
        name="budget.maximum_model_requests",
    )
    maximum_total_tokens = _positive_integer(
        budget.get("maximum_total_tokens"),
        name="budget.maximum_total_tokens",
    )
    _positive_cost(
        budget.get("maximum_estimated_cost"),
        name="budget.maximum_estimated_cost",
    )
    _required_text(budget.get("currency"), name="budget.currency")
    budget_error = validate_live_smoke_budget_limits(
        maximum_model_requests=maximum_model_requests,
        maximum_total_tokens=maximum_total_tokens,
    )
    if budget_error is not None:
        raise ValueError(budget_error)
    execution = payload.get("execution")
    if not isinstance(execution, Mapping):
        raise ValueError("execution is invalid")
    if execution.get("fast") is not False or execution.get("resume") is not False:
        raise ValueError("execution mode is invalid")
    chapter_error = validate_live_smoke_chapter_name(execution.get("chapter"))
    if chapter_error is not None:
        raise ValueError(chapter_error)
    routing = payload.get("routing")
    if not isinstance(routing, Mapping):
        raise ValueError("routing is invalid")
    scenes = routing.get("scenes")
    if not isinstance(scenes, Sequence) or isinstance(scenes, (str, bytes)):
        raise ValueError("routing scenes are invalid")
    if routing.get("scene_count") != len(scenes):
        raise ValueError("routing scene count is invalid")
    for field_name in (
        "signature_scene_count",
        "fallback_scene_count",
        "signature_fallback_scene_count",
    ):
        value = routing.get(field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"routing {field_name} is invalid")
    if routing["signature_scene_count"] < routing["scene_count"]:
        raise ValueError("routing signature scene count is invalid")
    plan_fingerprint = str(payload.get("plan_fingerprint") or "").strip()
    if not plan_fingerprint.startswith("sha256:"):
        raise ValueError("plan fingerprint is invalid")
    without_fingerprint = dict(payload)
    without_fingerprint.pop("plan_fingerprint", None)
    if _fingerprint(without_fingerprint) != plan_fingerprint:
        raise ValueError("plan fingerprint mismatch")


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


def _persist_immutable(payload: Mapping[str, Any], target: Path) -> Path:
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


def persist_write_model_live_smoke_plan(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist an immutable live-smoke plan; identical content is idempotent."""

    validate_write_model_live_smoke_plan(payload)
    return _persist_immutable(payload, Path(path).expanduser().resolve())
