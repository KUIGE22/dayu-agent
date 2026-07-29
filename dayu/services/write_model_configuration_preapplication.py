"""Build immutable write-routing snapshots and pre-application plans."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import tempfile
import unicodedata
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from dayu.services.contracts import (
    WriteModelRole,
    WritePreflightResult,
    WritePreflightScene,
    WriteRunConfig,
)
from dayu.services.internal.write_pipeline.enums import (
    AUDIT_WRITE_SCENES,
    PRIMARY_MODEL_WRITE_SCENES,
)
from dayu.services.write_model_configuration_change import (
    load_write_model_configuration_change_approval,
    validate_write_model_configuration_change_approval,
    verify_write_model_configuration_change_approval,
)
from dayu.startup.config_file_resolver import ConfigFileResolver


_SNAPSHOT_SCHEMA_VERSION = "write_scene_model_routing_snapshot_v1"
_SNAPSHOT_VERIFICATION_SCHEMA_VERSION = (
    "write_scene_model_routing_snapshot_verification_v1"
)
_SNAPSHOT_TYPE = "resolved_write_scene_model_routing"
_SNAPSHOT_SCOPE = "preflight_only_no_configuration_application"
_SNAPSHOT_STATUS = "resolved"
_SNAPSHOT_SOURCE_SEMANTICS = (
    "resolved_by_current_write_preflight_signature_scenes"
)
_PLAN_SCHEMA_VERSION = (
    "write_model_challenger_configuration_preapplication_plan_v1"
)
_PLAN_VERIFICATION_SCHEMA_VERSION = (
    "write_model_challenger_configuration_preapplication_"
    "plan_verification_v1"
)
_PLAN_TYPE = "write_scene_model_routing_preapplication"
_PLAN_SCOPE = (
    "rollback_validated_no_configuration_application_or_approval_consumption"
)
_PLAN_STATUS = "ready_for_future_atomic_application_gate"
_CONFIGURATION_DOMAIN = "write_scene_model_routing"
_MANIFEST_ROUTE_SOURCE = "scene_manifest_default"
_REQUEST_ROUTE_SOURCE = "request_role_override"
_FALLBACK_ROUTE_SOURCE = "request_fallback_override"
_MODEL_POINTER = "/model/default_name"
_ROLLBACK_STRATEGY = "restore_exact_preapplication_manifest_bytes"
_ROLE_NAMES = ("primary", "audit")
_ROLE_ORDER = {name: index for index, name in enumerate(_ROLE_NAMES)}
_PRIMARY_SCENES = tuple(str(scene) for scene in PRIMARY_MODEL_WRITE_SCENES)
_AUDIT_SCENES = tuple(str(scene) for scene in AUDIT_WRITE_SCENES)
_EXPECTED_SCENES = _PRIMARY_SCENES + _AUDIT_SCENES
_SCENE_ORDER = {
    scene_name: index for index, scene_name in enumerate(_EXPECTED_SCENES)
}
_SNAPSHOT_SAFETY_BOUNDARIES = [
    "preflight_observation_only",
    "no_configuration_application",
    "no_approval_consumption",
    "no_model_execution",
    "no_model_catalog_or_secret_mutation",
]
_PLAN_SAFETY_BOUNDARIES = [
    "preapplication_plan_only",
    "current_runtime_must_match_observed_champion",
    "manifest_backed_routes_only",
    "exact_original_manifest_bytes_preserved_for_rollback",
    "source_files_must_remain_current",
    "separate_atomic_application_command_required",
    "no_configuration_application",
    "no_approval_consumption",
    "no_model_execution",
    "no_model_catalog_or_secret_mutation",
]
_SNAPSHOT_FIELDS = {
    "schema_version",
    "snapshot_type",
    "scope",
    "status",
    "ticker",
    "resolution_context",
    "configuration_sources",
    "scenes",
    "fallback_scenes",
    "safety_boundaries",
    "snapshot_fingerprint",
}
_RESOLUTION_CONTEXT_FIELDS = {
    "config_root",
    "source_semantics",
    "write_model_override_name",
    "audit_model_override_name",
    "write_fallback_model_name",
    "audit_fallback_model_name",
}
_CONFIG_SOURCE_FIELDS = {"source_code", "path", "fingerprint"}
_SCENE_FIELDS = {
    "role",
    "scene_name",
    "model_name",
    "temperature",
    "route_source",
    "manifest_source",
}
_MANIFEST_SOURCE_FIELDS = {
    "path",
    "fingerprint",
    "default_model_name",
    "allowed_model_names",
}
_PLAN_FIELDS = {
    "schema_version",
    "plan_type",
    "scope",
    "status",
    "ticker",
    "configuration_domain",
    "source_approval",
    "source_routing_snapshot",
    "transitions",
    "rollback",
    "safety_boundaries",
    "plan_fingerprint",
}
_ARTIFACT_SOURCE_FIELDS = {
    "path",
    "fingerprint",
    "content_fingerprint",
}
_PLAN_TRANSITION_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "target_manifest_fingerprint",
    "json_pointer",
    "expected_current_model_name",
    "proposed_model_name",
}
_ROLLBACK_FIELDS = {"rollback_reference", "strategy", "entries"}
_ROLLBACK_ENTRY_FIELDS = {
    "role",
    "scene_name",
    "target_manifest_path",
    "original_file_fingerprint",
    "original_file_content_base64",
    "restore_model_name",
    "expected_applied_model_name",
}


class WriteModelConfigurationPreapplicationBlockedError(ValueError):
    """Raised when current routing cannot safely enter application."""


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


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


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


def _optional_text(
    value: object,
    *,
    name: str,
    maximum_length: int = 4096,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if not value:
        return ""
    return _required_text(
        value,
        name=name,
        maximum_length=maximum_length,
    )


def _absolute_path(value: object, *, name: str) -> Path:
    path = Path(_required_text(value, name=name)).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return path.resolve()


def _string_list(
    value: object,
    *,
    name: str,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    result = [
        _required_text(
            item,
            name=f"{name}[{index}]",
            maximum_length=256,
        )
        for index, item in enumerate(value)
    ]
    if not allow_empty and not result:
        raise ValueError(f"{name} must be non-empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must contain unique values")
    return result


def _temperature(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _scene_role(scene_name: str) -> str:
    if scene_name in _PRIMARY_SCENES:
        return WriteModelRole.PRIMARY.value
    if scene_name in _AUDIT_SCENES:
        return WriteModelRole.AUDIT.value
    raise ValueError(f"unsupported write scene: {scene_name}")


def _scene_sort_key(value: Mapping[str, Any]) -> tuple[int, int]:
    role = str(value.get("role") or "")
    scene_name = str(value.get("scene_name") or "")
    return (
        _ROLE_ORDER.get(role, len(_ROLE_ORDER)),
        _SCENE_ORDER.get(scene_name, len(_SCENE_ORDER)),
    )


def _resolve_active_config_path(
    resolver: ConfigFileResolver,
    relative_path: str,
) -> Path:
    normalized = relative_path.strip().lstrip("/")
    for root in resolver.config_dirs:
        candidate = (root / normalized).resolve()
        if candidate.is_file():
            return candidate
    searched = ", ".join(
        str((root / normalized).resolve())
        for root in resolver.config_dirs
    )
    raise FileNotFoundError(
        f"configuration source does not exist: {normalized}; "
        f"searched={searched}"
    )


def _load_json_bytes(
    path: Path,
    *,
    name: str,
) -> tuple[bytes, dict[str, Any]]:
    raw_bytes = path.read_bytes()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {name} JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be an object: {path}")
    return raw_bytes, payload


def _manifest_source(
    resolver: ConfigFileResolver,
    *,
    scene_name: str,
) -> dict[str, Any]:
    path = _resolve_active_config_path(
        resolver,
        f"prompts/manifests/{scene_name}.json",
    )
    _raw_bytes, manifest = _load_json_bytes(
        path,
        name=f"scene manifest {scene_name}",
    )
    if manifest.get("scene") != scene_name:
        raise ValueError(
            f"scene manifest {scene_name!r} has mismatched scene"
        )
    model = _mapping(
        manifest.get("model"),
        name=f"scene manifest {scene_name}.model",
    )
    default_model_name = _required_text(
        model.get("default_name"),
        name=f"scene manifest {scene_name}.model.default_name",
        maximum_length=256,
    )
    allowed_model_names = _string_list(
        model.get("allowed_names"),
        name=f"scene manifest {scene_name}.model.allowed_names",
    )
    if default_model_name not in allowed_model_names:
        raise ValueError(
            f"scene manifest {scene_name!r} default model is not allowed"
        )
    return {
        "path": str(path),
        "fingerprint": _file_fingerprint(path),
        "default_model_name": default_model_name,
        "allowed_model_names": allowed_model_names,
    }


def _configuration_source(
    resolver: ConfigFileResolver,
    *,
    source_code: str,
    relative_path: str,
) -> dict[str, str]:
    path = _resolve_active_config_path(resolver, relative_path)
    return {
        "source_code": source_code,
        "path": str(path),
        "fingerprint": _file_fingerprint(path),
    }


def _preflight_scene_map(
    scenes: tuple[WritePreflightScene, ...],
    *,
    name: str,
) -> dict[str, WritePreflightScene]:
    result: dict[str, WritePreflightScene] = {}
    for scene in scenes:
        scene_name = str(scene.scene_name)
        if scene_name in result:
            raise ValueError(f"{name} contains duplicate scene {scene_name}")
        result[scene_name] = scene
    return result


def build_write_scene_model_routing_snapshot(
    *,
    config_root: str | Path | None,
    write_config: WriteRunConfig,
    preflight_result: WritePreflightResult,
) -> dict[str, Any]:
    """Build a deterministic snapshot from the resolved write preflight."""

    if not preflight_result.ready:
        raise WriteModelConfigurationPreapplicationBlockedError(
            "write preflight must pass before routing can be snapshotted"
        )
    signature_scenes = _preflight_scene_map(
        preflight_result.signature_scenes,
        name="signature_scenes",
    )
    if set(signature_scenes) != set(_EXPECTED_SCENES):
        raise WriteModelConfigurationPreapplicationBlockedError(
            "write preflight signature scenes are incomplete"
        )
    fallback_scenes = _preflight_scene_map(
        preflight_result.signature_fallback_scenes,
        name="signature_fallback_scenes",
    )
    if not set(fallback_scenes).issubset(_EXPECTED_SCENES):
        raise ValueError(
            "write preflight fallback scenes contain unsupported scenes"
        )

    resolver = ConfigFileResolver(
        Path(config_root).expanduser().resolve()
        if config_root is not None
        else None
    )
    resolved_config_root = resolver.config_dirs[0].resolve()
    context = {
        "config_root": str(resolved_config_root),
        "source_semantics": _SNAPSHOT_SOURCE_SEMANTICS,
        "write_model_override_name": str(
            write_config.write_model_override_name or ""
        ).strip(),
        "audit_model_override_name": str(
            write_config.audit_model_override_name or ""
        ).strip(),
        "write_fallback_model_name": str(
            write_config.write_fallback_model_name or ""
        ).strip(),
        "audit_fallback_model_name": str(
            write_config.audit_fallback_model_name or ""
        ).strip(),
    }
    configuration_sources = [
        _configuration_source(
            resolver,
            source_code="model_catalog",
            relative_path="llm_models.json",
        ),
        _configuration_source(
            resolver,
            source_code="run_config",
            relative_path="run.json",
        ),
    ]
    scenes: list[dict[str, Any]] = []
    for scene_name in _EXPECTED_SCENES:
        preflight_scene = signature_scenes[scene_name]
        role = _scene_role(scene_name)
        if preflight_scene.model_role.value != role:
            raise ValueError(
                f"preflight scene {scene_name!r} has the wrong role"
            )
        manifest_source = _manifest_source(
            resolver,
            scene_name=scene_name,
        )
        role_override = (
            context["audit_model_override_name"]
            if role == WriteModelRole.AUDIT.value
            else context["write_model_override_name"]
        )
        route_source = (
            _REQUEST_ROUTE_SOURCE
            if role_override
            else _MANIFEST_ROUTE_SOURCE
        )
        expected_model = (
            role_override
            if role_override
            else manifest_source["default_model_name"]
        )
        if preflight_scene.model_name != expected_model:
            raise WriteModelConfigurationPreapplicationBlockedError(
                f"resolved scene {scene_name!r} does not match its "
                "declared routing source"
            )
        scenes.append(
            {
                "role": role,
                "scene_name": scene_name,
                "model_name": preflight_scene.model_name,
                "temperature": preflight_scene.temperature,
                "route_source": route_source,
                "manifest_source": manifest_source,
            }
        )

    fallback_entries: list[dict[str, Any]] = []
    for scene_name in _EXPECTED_SCENES:
        preflight_scene = fallback_scenes.get(scene_name)
        if preflight_scene is None:
            continue
        role = _scene_role(scene_name)
        configured_name = (
            context["audit_fallback_model_name"]
            if role == WriteModelRole.AUDIT.value
            else context["write_fallback_model_name"]
        )
        if (
            not configured_name
            or preflight_scene.model_name != configured_name
            or preflight_scene.model_role.value != role
        ):
            raise WriteModelConfigurationPreapplicationBlockedError(
                f"resolved fallback scene {scene_name!r} does not "
                "match its request override"
            )
        fallback_entries.append(
            {
                "role": role,
                "scene_name": scene_name,
                "model_name": preflight_scene.model_name,
                "temperature": preflight_scene.temperature,
                "route_source": _FALLBACK_ROUTE_SOURCE,
                "manifest_source": _manifest_source(
                    resolver,
                    scene_name=scene_name,
                ),
            }
        )

    payload: dict[str, Any] = {
        "schema_version": _SNAPSHOT_SCHEMA_VERSION,
        "snapshot_type": _SNAPSHOT_TYPE,
        "scope": _SNAPSHOT_SCOPE,
        "status": _SNAPSHOT_STATUS,
        "ticker": _required_text(
            write_config.ticker,
            name="write_config.ticker",
            maximum_length=64,
        ),
        "resolution_context": context,
        "configuration_sources": configuration_sources,
        "scenes": scenes,
        "fallback_scenes": fallback_entries,
        "safety_boundaries": list(_SNAPSHOT_SAFETY_BOUNDARIES),
    }
    payload["snapshot_fingerprint"] = _fingerprint(payload)
    validate_write_scene_model_routing_snapshot(payload)
    return payload


def _validate_configuration_source(
    value: object,
    *,
    name: str,
) -> dict[str, str]:
    source = _mapping(value, name=name)
    _validate_exact_fields(
        source,
        expected=_CONFIG_SOURCE_FIELDS,
        name=name,
    )
    source_code = _required_text(
        source.get("source_code"),
        name=f"{name}.source_code",
        maximum_length=64,
    )
    if source_code not in {"model_catalog", "run_config"}:
        raise ValueError(f"{name}.source_code is invalid")
    return {
        "source_code": source_code,
        "path": str(
            _absolute_path(source.get("path"), name=f"{name}.path")
        ),
        "fingerprint": _validated_fingerprint(
            source.get("fingerprint"),
            name=f"{name}.fingerprint",
        ),
    }


def _validate_manifest_source(
    value: object,
    *,
    name: str,
) -> dict[str, Any]:
    source = _mapping(value, name=name)
    _validate_exact_fields(
        source,
        expected=_MANIFEST_SOURCE_FIELDS,
        name=name,
    )
    default_model_name = _required_text(
        source.get("default_model_name"),
        name=f"{name}.default_model_name",
        maximum_length=256,
    )
    allowed_model_names = _string_list(
        source.get("allowed_model_names"),
        name=f"{name}.allowed_model_names",
    )
    if default_model_name not in allowed_model_names:
        raise ValueError(f"{name}.default_model_name is not allowed")
    return {
        "path": str(
            _absolute_path(source.get("path"), name=f"{name}.path")
        ),
        "fingerprint": _validated_fingerprint(
            source.get("fingerprint"),
            name=f"{name}.fingerprint",
        ),
        "default_model_name": default_model_name,
        "allowed_model_names": allowed_model_names,
    }


def _validate_scene_entry(
    value: object,
    *,
    name: str,
    fallback: bool,
) -> dict[str, Any]:
    scene = _mapping(value, name=name)
    _validate_exact_fields(scene, expected=_SCENE_FIELDS, name=name)
    role = _required_text(
        scene.get("role"),
        name=f"{name}.role",
        maximum_length=32,
    )
    scene_name = _required_text(
        scene.get("scene_name"),
        name=f"{name}.scene_name",
        maximum_length=128,
    )
    if role not in _ROLE_NAMES or role != _scene_role(scene_name):
        raise ValueError(f"{name} role/scene identity is invalid")
    route_source = _required_text(
        scene.get("route_source"),
        name=f"{name}.route_source",
        maximum_length=64,
    )
    expected_sources = (
        {_FALLBACK_ROUTE_SOURCE}
        if fallback
        else {_MANIFEST_ROUTE_SOURCE, _REQUEST_ROUTE_SOURCE}
    )
    if route_source not in expected_sources:
        raise ValueError(f"{name}.route_source is invalid")
    return {
        "role": role,
        "scene_name": scene_name,
        "model_name": _required_text(
            scene.get("model_name"),
            name=f"{name}.model_name",
            maximum_length=256,
        ),
        "temperature": _temperature(
            scene.get("temperature"),
            name=f"{name}.temperature",
        ),
        "route_source": route_source,
        "manifest_source": _validate_manifest_source(
            scene.get("manifest_source"),
            name=f"{name}.manifest_source",
        ),
    }


def validate_write_scene_model_routing_snapshot(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict resolved-routing snapshot."""

    _validate_exact_fields(
        payload,
        expected=_SNAPSHOT_FIELDS,
        name="routing snapshot",
    )
    constants = {
        "schema_version": _SNAPSHOT_SCHEMA_VERSION,
        "snapshot_type": _SNAPSHOT_TYPE,
        "scope": _SNAPSHOT_SCOPE,
        "status": _SNAPSHOT_STATUS,
    }
    for field_name, expected in constants.items():
        if payload.get(field_name) != expected:
            raise ValueError(
                f"routing snapshot {field_name} must be {expected!r}"
            )
    _required_text(
        payload.get("ticker"),
        name="routing snapshot ticker",
        maximum_length=64,
    )
    context = _mapping(
        payload.get("resolution_context"),
        name="routing snapshot resolution_context",
    )
    _validate_exact_fields(
        context,
        expected=_RESOLUTION_CONTEXT_FIELDS,
        name="routing snapshot resolution_context",
    )
    _absolute_path(
        context.get("config_root"),
        name="resolution_context.config_root",
    )
    if context.get("source_semantics") != _SNAPSHOT_SOURCE_SEMANTICS:
        raise ValueError("routing snapshot source_semantics is invalid")
    normalized_context = {
        field_name: _optional_text(
            context.get(field_name),
            name=f"resolution_context.{field_name}",
            maximum_length=256,
        )
        for field_name in (
            "write_model_override_name",
            "audit_model_override_name",
            "write_fallback_model_name",
            "audit_fallback_model_name",
        )
    }
    raw_sources = payload.get("configuration_sources")
    if not isinstance(raw_sources, list):
        raise ValueError(
            "routing snapshot configuration_sources must be a list"
        )
    sources = [
        _validate_configuration_source(
            value,
            name=f"configuration_sources[{index}]",
        )
        for index, value in enumerate(raw_sources)
    ]
    if [source["source_code"] for source in sources] != [
        "model_catalog",
        "run_config",
    ]:
        raise ValueError(
            "routing snapshot configuration_sources are incomplete"
        )
    raw_scenes = payload.get("scenes")
    if not isinstance(raw_scenes, list):
        raise ValueError("routing snapshot scenes must be a list")
    scenes = [
        _validate_scene_entry(
            value,
            name=f"scenes[{index}]",
            fallback=False,
        )
        for index, value in enumerate(raw_scenes)
    ]
    if [scene["scene_name"] for scene in scenes] != list(
        _EXPECTED_SCENES
    ):
        raise ValueError(
            "routing snapshot scenes must contain every signature scene "
            "in canonical order"
        )
    for scene in scenes:
        role = scene["role"]
        role_override = (
            normalized_context["audit_model_override_name"]
            if role == WriteModelRole.AUDIT.value
            else normalized_context["write_model_override_name"]
        )
        expected_source = (
            _REQUEST_ROUTE_SOURCE
            if role_override
            else _MANIFEST_ROUTE_SOURCE
        )
        expected_model = (
            role_override
            or scene["manifest_source"]["default_model_name"]
        )
        if (
            scene["route_source"] != expected_source
            or scene["model_name"] != expected_model
        ):
            raise ValueError(
                f"routing snapshot scene {scene['scene_name']!r} "
                "does not match its resolution context"
            )

    raw_fallbacks = payload.get("fallback_scenes")
    if not isinstance(raw_fallbacks, list):
        raise ValueError(
            "routing snapshot fallback_scenes must be a list"
        )
    fallbacks = [
        _validate_scene_entry(
            value,
            name=f"fallback_scenes[{index}]",
            fallback=True,
        )
        for index, value in enumerate(raw_fallbacks)
    ]
    if fallbacks != sorted(fallbacks, key=_scene_sort_key):
        raise ValueError(
            "routing snapshot fallback_scenes are not ordered"
        )
    fallback_names = [
        scene["scene_name"] for scene in fallbacks
    ]
    if len(fallback_names) != len(set(fallback_names)):
        raise ValueError(
            "routing snapshot fallback_scenes contain duplicates"
        )
    scenes_by_name = {
        scene["scene_name"]: scene for scene in scenes
    }
    expected_fallback_names: list[str] = []
    for scene_name in _EXPECTED_SCENES:
        role = _scene_role(scene_name)
        fallback_name = (
            normalized_context["audit_fallback_model_name"]
            if role == WriteModelRole.AUDIT.value
            else normalized_context["write_fallback_model_name"]
        )
        if fallback_name and (
            fallback_name != scenes_by_name[scene_name]["model_name"]
        ):
            expected_fallback_names.append(scene_name)
    if fallback_names != expected_fallback_names:
        raise ValueError(
            "routing snapshot fallback_scenes do not match context"
        )
    for fallback in fallbacks:
        configured_name = (
            normalized_context["audit_fallback_model_name"]
            if fallback["role"] == WriteModelRole.AUDIT.value
            else normalized_context["write_fallback_model_name"]
        )
        if fallback["model_name"] != configured_name:
            raise ValueError(
                f"routing snapshot fallback {fallback['scene_name']!r} "
                "does not match context"
            )
    if payload.get("safety_boundaries") != _SNAPSHOT_SAFETY_BOUNDARIES:
        raise ValueError(
            "routing snapshot safety_boundaries are invalid"
        )
    expected_fingerprint = _validated_fingerprint(
        payload.get("snapshot_fingerprint"),
        name="routing snapshot fingerprint",
    )
    unsigned = dict(payload)
    unsigned.pop("snapshot_fingerprint", None)
    if not hmac.compare_digest(
        expected_fingerprint,
        _fingerprint(unsigned),
    ):
        raise ValueError("routing snapshot fingerprint mismatch")


def _snapshot_verification_payload(
    *,
    status: str,
    action: str,
    reason_codes: list[str],
    identity: Mapping[str, bool],
) -> dict[str, Any]:
    return {
        "schema_version": _SNAPSHOT_VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "action": action,
        "reason_codes": reason_codes,
        "identity": dict(identity),
        "configuration_change_applied": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }


def verify_write_scene_model_routing_snapshot(
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify that every file bound by a snapshot remains current."""

    validate_write_scene_model_routing_snapshot(receipt)
    identity = {
        "snapshot_fingerprint": True,
        "configuration_source_files": True,
        "scene_manifest_files": True,
    }
    raw_sources = receipt["configuration_sources"]
    assert isinstance(raw_sources, list)
    for index, raw_source in enumerate(raw_sources):
        source = _mapping(
            raw_source,
            name=f"configuration_sources[{index}]",
        )
        path = _absolute_path(
            source.get("path"),
            name=f"configuration_sources[{index}].path",
        )
        if not path.is_file() or not hmac.compare_digest(
            _validated_fingerprint(
                source.get("fingerprint"),
                name=f"configuration_sources[{index}].fingerprint",
            ),
            _file_fingerprint(path),
        ):
            identity["configuration_source_files"] = False
            return _snapshot_verification_payload(
                status="configuration_sources_changed",
                action="stop",
                reason_codes=[
                    f"configuration_source_changed:{source.get('source_code')}"
                ],
                identity=identity,
            )
    checked_manifests: set[str] = set()
    for collection_name in ("scenes", "fallback_scenes"):
        raw_scenes = receipt[collection_name]
        assert isinstance(raw_scenes, list)
        for index, raw_scene in enumerate(raw_scenes):
            scene = _mapping(
                raw_scene,
                name=f"{collection_name}[{index}]",
            )
            manifest = _mapping(
                scene.get("manifest_source"),
                name=f"{collection_name}[{index}].manifest_source",
            )
            path = _absolute_path(
                manifest.get("path"),
                name=(
                    f"{collection_name}[{index}]."
                    "manifest_source.path"
                ),
            )
            path_key = str(path)
            if path_key in checked_manifests:
                continue
            checked_manifests.add(path_key)
            if not path.is_file() or not hmac.compare_digest(
                _validated_fingerprint(
                    manifest.get("fingerprint"),
                    name=(
                        f"{collection_name}[{index}]."
                        "manifest_source.fingerprint"
                    ),
                ),
                _file_fingerprint(path),
            ):
                identity["scene_manifest_files"] = False
                return _snapshot_verification_payload(
                    status="scene_manifests_changed",
                    action="stop",
                    reason_codes=[
                        f"scene_manifest_changed:{scene.get('scene_name')}"
                    ],
                    identity=identity,
                )
    return _snapshot_verification_payload(
        status="current",
        action="preapplication_plan_may_be_built",
        reason_codes=[],
        identity=identity,
    )


def _approval_change_request(
    approval: Mapping[str, Any],
) -> Mapping[str, Any]:
    validate_write_model_configuration_change_approval(approval)
    return _mapping(
        approval.get("configuration_change_request"),
        name="configuration change approval request",
    )


def _source_reference(
    *,
    path: Path,
    content_fingerprint: str,
) -> dict[str, str]:
    return {
        "path": str(path),
        "fingerprint": _file_fingerprint(path),
        "content_fingerprint": _validated_fingerprint(
            content_fingerprint,
            name="artifact content_fingerprint",
        ),
    }


def _load_model_catalog_from_snapshot(
    snapshot: Mapping[str, Any],
) -> Mapping[str, Any]:
    raw_sources = snapshot.get("configuration_sources")
    if not isinstance(raw_sources, list):
        raise ValueError(
            "routing snapshot configuration_sources must be a list"
        )
    for index, raw_source in enumerate(raw_sources):
        source = _mapping(
            raw_source,
            name=f"configuration_sources[{index}]",
        )
        if source.get("source_code") != "model_catalog":
            continue
        path = _absolute_path(
            source.get("path"),
            name="model_catalog source path",
        )
        _raw_bytes, payload = _load_json_bytes(
            path,
            name="model catalog",
        )
        return payload
    raise ValueError("routing snapshot is missing model catalog source")


def build_write_model_configuration_preapplication_plan(
    *,
    approval_path: str | Path,
    routing_snapshot_path: str | Path,
    now: datetime,
) -> dict[str, Any]:
    """Build a rollback-complete plan without consuming or applying."""

    resolved_approval_path, approval = (
        load_write_model_configuration_change_approval(approval_path)
    )
    approval_verification = (
        verify_write_model_configuration_change_approval(
            approval,
            now=now,
        )
    )
    if approval_verification.get("status") != "approved":
        raise WriteModelConfigurationPreapplicationBlockedError(
            "configuration change approval is not current"
        )
    resolved_snapshot_path, snapshot = (
        load_write_scene_model_routing_snapshot(
            routing_snapshot_path
        )
    )
    snapshot_verification = (
        verify_write_scene_model_routing_snapshot(snapshot)
    )
    if snapshot_verification.get("status") != "current":
        raise WriteModelConfigurationPreapplicationBlockedError(
            "routing snapshot sources are not current"
        )
    change_request = _approval_change_request(approval)
    if change_request.get("ticker") != snapshot.get("ticker"):
        raise WriteModelConfigurationPreapplicationBlockedError(
            "routing snapshot ticker does not match approval"
        )
    raw_scenes = snapshot.get("scenes")
    assert isinstance(raw_scenes, list)
    scenes_by_identity = {
        (str(scene["role"]), str(scene["scene_name"])): scene
        for scene in raw_scenes
        if isinstance(scene, Mapping)
    }
    model_catalog = _load_model_catalog_from_snapshot(snapshot)
    raw_transitions = change_request.get("transitions")
    if not isinstance(raw_transitions, list) or not raw_transitions:
        raise ValueError(
            "configuration change request transitions must be non-empty"
        )
    transitions: list[dict[str, str]] = []
    rollback_entries: list[dict[str, str]] = []
    seen_manifest_paths: set[str] = set()
    for index, raw_transition in enumerate(raw_transitions):
        transition = _mapping(
            raw_transition,
            name=f"configuration change transitions[{index}]",
        )
        role = _required_text(
            transition.get("role"),
            name=f"configuration change transitions[{index}].role",
            maximum_length=32,
        )
        scene_name = _required_text(
            transition.get("scene_name"),
            name=(
                f"configuration change transitions[{index}].scene_name"
            ),
            maximum_length=128,
        )
        current_model = _required_text(
            transition.get("observed_champion_model_name"),
            name=(
                "configuration change transitions"
                f"[{index}].observed_champion_model_name"
            ),
            maximum_length=256,
        )
        proposed_model = _required_text(
            transition.get("proposed_challenger_model_name"),
            name=(
                "configuration change transitions"
                f"[{index}].proposed_challenger_model_name"
            ),
            maximum_length=256,
        )
        scene = scenes_by_identity.get((role, scene_name))
        if scene is None:
            raise WriteModelConfigurationPreapplicationBlockedError(
                f"current routing is missing approved scene {scene_name!r}"
            )
        if scene.get("model_name") != current_model:
            raise WriteModelConfigurationPreapplicationBlockedError(
                f"current scene {scene_name!r} does not match observed "
                "Champion"
            )
        if scene.get("route_source") != _MANIFEST_ROUTE_SOURCE:
            raise WriteModelConfigurationPreapplicationBlockedError(
                f"current scene {scene_name!r} depends on a request "
                "override and cannot enter persistent application"
            )
        manifest = _mapping(
            scene.get("manifest_source"),
            name=f"snapshot scene {scene_name}.manifest_source",
        )
        if manifest.get("default_model_name") != current_model:
            raise WriteModelConfigurationPreapplicationBlockedError(
                f"current manifest for {scene_name!r} does not contain "
                "the observed Champion"
            )
        allowed_names = manifest.get("allowed_model_names")
        if (
            not isinstance(allowed_names, list)
            or proposed_model not in allowed_names
        ):
            raise WriteModelConfigurationPreapplicationBlockedError(
                f"proposed model is not allowed for scene {scene_name!r}"
            )
        if proposed_model not in model_catalog:
            raise WriteModelConfigurationPreapplicationBlockedError(
                f"proposed model is absent from the current catalog: "
                f"{proposed_model}"
            )
        manifest_path = _absolute_path(
            manifest.get("path"),
            name=f"snapshot scene {scene_name}.manifest_source.path",
        )
        manifest_path_text = str(manifest_path)
        if manifest_path_text in seen_manifest_paths:
            raise ValueError(
                "configuration transitions target the same manifest twice"
            )
        seen_manifest_paths.add(manifest_path_text)
        original_bytes = manifest_path.read_bytes()
        original_fingerprint = _bytes_fingerprint(original_bytes)
        expected_fingerprint = _validated_fingerprint(
            manifest.get("fingerprint"),
            name=f"snapshot scene {scene_name}.manifest fingerprint",
        )
        if not hmac.compare_digest(
            original_fingerprint,
            expected_fingerprint,
        ):
            raise WriteModelConfigurationPreapplicationBlockedError(
                f"manifest changed while building scene {scene_name!r}"
            )
        transitions.append(
            {
                "role": role,
                "scene_name": scene_name,
                "target_manifest_path": manifest_path_text,
                "target_manifest_fingerprint": original_fingerprint,
                "json_pointer": _MODEL_POINTER,
                "expected_current_model_name": current_model,
                "proposed_model_name": proposed_model,
            }
        )
        rollback_entries.append(
            {
                "role": role,
                "scene_name": scene_name,
                "target_manifest_path": manifest_path_text,
                "original_file_fingerprint": original_fingerprint,
                "original_file_content_base64": base64.b64encode(
                    original_bytes
                ).decode("ascii"),
                "restore_model_name": current_model,
                "expected_applied_model_name": proposed_model,
            }
        )
    transitions.sort(key=_scene_sort_key)
    rollback_entries.sort(key=_scene_sort_key)
    payload: dict[str, Any] = {
        "schema_version": _PLAN_SCHEMA_VERSION,
        "plan_type": _PLAN_TYPE,
        "scope": _PLAN_SCOPE,
        "status": _PLAN_STATUS,
        "ticker": snapshot["ticker"],
        "configuration_domain": _CONFIGURATION_DOMAIN,
        "source_approval": _source_reference(
            path=resolved_approval_path,
            content_fingerprint=str(
                approval.get("approval_fingerprint") or ""
            ),
        ),
        "source_routing_snapshot": _source_reference(
            path=resolved_snapshot_path,
            content_fingerprint=str(
                snapshot.get("snapshot_fingerprint") or ""
            ),
        ),
        "transitions": transitions,
        "rollback": {
            "rollback_reference": approval["rollback_reference"],
            "strategy": _ROLLBACK_STRATEGY,
            "entries": rollback_entries,
        },
        "safety_boundaries": list(_PLAN_SAFETY_BOUNDARIES),
    }
    payload["plan_fingerprint"] = _fingerprint(payload)
    validate_write_model_configuration_preapplication_plan(payload)
    return payload


def _validate_artifact_source(
    value: object,
    *,
    name: str,
) -> dict[str, str]:
    source = _mapping(value, name=name)
    _validate_exact_fields(
        source,
        expected=_ARTIFACT_SOURCE_FIELDS,
        name=name,
    )
    return {
        "path": str(
            _absolute_path(source.get("path"), name=f"{name}.path")
        ),
        "fingerprint": _validated_fingerprint(
            source.get("fingerprint"),
            name=f"{name}.fingerprint",
        ),
        "content_fingerprint": _validated_fingerprint(
            source.get("content_fingerprint"),
            name=f"{name}.content_fingerprint",
        ),
    }


def _validate_plan_transition(
    value: object,
    *,
    name: str,
) -> dict[str, str]:
    transition = _mapping(value, name=name)
    _validate_exact_fields(
        transition,
        expected=_PLAN_TRANSITION_FIELDS,
        name=name,
    )
    role = _required_text(
        transition.get("role"),
        name=f"{name}.role",
        maximum_length=32,
    )
    scene_name = _required_text(
        transition.get("scene_name"),
        name=f"{name}.scene_name",
        maximum_length=128,
    )
    if role not in _ROLE_NAMES or role != _scene_role(scene_name):
        raise ValueError(f"{name} role/scene identity is invalid")
    current_model = _required_text(
        transition.get("expected_current_model_name"),
        name=f"{name}.expected_current_model_name",
        maximum_length=256,
    )
    proposed_model = _required_text(
        transition.get("proposed_model_name"),
        name=f"{name}.proposed_model_name",
        maximum_length=256,
    )
    if current_model == proposed_model:
        raise ValueError(f"{name} does not change the model")
    if transition.get("json_pointer") != _MODEL_POINTER:
        raise ValueError(f"{name}.json_pointer is invalid")
    return {
        "role": role,
        "scene_name": scene_name,
        "target_manifest_path": str(
            _absolute_path(
                transition.get("target_manifest_path"),
                name=f"{name}.target_manifest_path",
            )
        ),
        "target_manifest_fingerprint": _validated_fingerprint(
            transition.get("target_manifest_fingerprint"),
            name=f"{name}.target_manifest_fingerprint",
        ),
        "json_pointer": _MODEL_POINTER,
        "expected_current_model_name": current_model,
        "proposed_model_name": proposed_model,
    }


def _validate_rollback_entry(
    value: object,
    *,
    name: str,
) -> tuple[dict[str, str], bytes]:
    entry = _mapping(value, name=name)
    _validate_exact_fields(
        entry,
        expected=_ROLLBACK_ENTRY_FIELDS,
        name=name,
    )
    role = _required_text(
        entry.get("role"),
        name=f"{name}.role",
        maximum_length=32,
    )
    scene_name = _required_text(
        entry.get("scene_name"),
        name=f"{name}.scene_name",
        maximum_length=128,
    )
    if role not in _ROLE_NAMES or role != _scene_role(scene_name):
        raise ValueError(f"{name} role/scene identity is invalid")
    encoded = _required_text(
        entry.get("original_file_content_base64"),
        name=f"{name}.original_file_content_base64",
        maximum_length=1_000_000,
    )
    try:
        original_bytes = base64.b64decode(
            encoded,
            validate=True,
        )
    except (binascii.Error, ValueError, TypeError) as exc:
        raise ValueError(
            f"{name}.original_file_content_base64 is invalid"
        ) from exc
    fingerprint = _validated_fingerprint(
        entry.get("original_file_fingerprint"),
        name=f"{name}.original_file_fingerprint",
    )
    if not hmac.compare_digest(
        fingerprint,
        _bytes_fingerprint(original_bytes),
    ):
        raise ValueError(f"{name} original file fingerprint mismatch")
    return (
        {
            "role": role,
            "scene_name": scene_name,
            "target_manifest_path": str(
                _absolute_path(
                    entry.get("target_manifest_path"),
                    name=f"{name}.target_manifest_path",
                )
            ),
            "original_file_fingerprint": fingerprint,
            "original_file_content_base64": encoded,
            "restore_model_name": _required_text(
                entry.get("restore_model_name"),
                name=f"{name}.restore_model_name",
                maximum_length=256,
            ),
            "expected_applied_model_name": _required_text(
                entry.get("expected_applied_model_name"),
                name=f"{name}.expected_applied_model_name",
                maximum_length=256,
            ),
        },
        original_bytes,
    )


def validate_write_model_configuration_preapplication_plan(
    payload: Mapping[str, Any],
) -> None:
    """Validate a strict, rollback-complete pre-application plan."""

    _validate_exact_fields(
        payload,
        expected=_PLAN_FIELDS,
        name="configuration preapplication plan",
    )
    constants = {
        "schema_version": _PLAN_SCHEMA_VERSION,
        "plan_type": _PLAN_TYPE,
        "scope": _PLAN_SCOPE,
        "status": _PLAN_STATUS,
        "configuration_domain": _CONFIGURATION_DOMAIN,
    }
    for field_name, expected in constants.items():
        if payload.get(field_name) != expected:
            raise ValueError(
                f"configuration preapplication plan {field_name} "
                f"must be {expected!r}"
            )
    _required_text(
        payload.get("ticker"),
        name="configuration preapplication plan ticker",
        maximum_length=64,
    )
    _validate_artifact_source(
        payload.get("source_approval"),
        name="source_approval",
    )
    _validate_artifact_source(
        payload.get("source_routing_snapshot"),
        name="source_routing_snapshot",
    )
    raw_transitions = payload.get("transitions")
    if not isinstance(raw_transitions, list) or not raw_transitions:
        raise ValueError(
            "configuration preapplication transitions must be non-empty"
        )
    transitions = [
        _validate_plan_transition(
            value,
            name=f"transitions[{index}]",
        )
        for index, value in enumerate(raw_transitions)
    ]
    if transitions != sorted(transitions, key=_scene_sort_key):
        raise ValueError(
            "configuration preapplication transitions are not ordered"
        )
    identities = [
        (item["role"], item["scene_name"]) for item in transitions
    ]
    paths = [
        item["target_manifest_path"] for item in transitions
    ]
    if (
        len(identities) != len(set(identities))
        or len(paths) != len(set(paths))
    ):
        raise ValueError(
            "configuration preapplication transitions contain duplicates"
        )
    rollback = _mapping(
        payload.get("rollback"),
        name="configuration preapplication rollback",
    )
    _validate_exact_fields(
        rollback,
        expected=_ROLLBACK_FIELDS,
        name="configuration preapplication rollback",
    )
    _required_text(
        rollback.get("rollback_reference"),
        name="rollback.rollback_reference",
        maximum_length=500,
    )
    if rollback.get("strategy") != _ROLLBACK_STRATEGY:
        raise ValueError("rollback strategy is invalid")
    raw_entries = rollback.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("rollback entries must be a list")
    validated_entries = [
        _validate_rollback_entry(
            value,
            name=f"rollback.entries[{index}]",
        )
        for index, value in enumerate(raw_entries)
    ]
    entries = [item[0] for item in validated_entries]
    original_bytes = [item[1] for item in validated_entries]
    if entries != sorted(entries, key=_scene_sort_key):
        raise ValueError("rollback entries are not ordered")
    if len(entries) != len(transitions):
        raise ValueError("rollback entries do not match transitions")
    for transition, entry, source_bytes in zip(
        transitions,
        entries,
        original_bytes,
        strict=True,
    ):
        comparable = {
            "role": transition["role"],
            "scene_name": transition["scene_name"],
            "target_manifest_path": transition[
                "target_manifest_path"
            ],
            "fingerprint": transition[
                "target_manifest_fingerprint"
            ],
            "current": transition["expected_current_model_name"],
            "proposed": transition["proposed_model_name"],
        }
        rollback_comparable = {
            "role": entry["role"],
            "scene_name": entry["scene_name"],
            "target_manifest_path": entry["target_manifest_path"],
            "fingerprint": entry["original_file_fingerprint"],
            "current": entry["restore_model_name"],
            "proposed": entry["expected_applied_model_name"],
        }
        if comparable != rollback_comparable:
            raise ValueError(
                "rollback entry does not match its transition"
            )
        try:
            source_manifest = json.loads(source_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "rollback source bytes are not a JSON manifest"
            ) from exc
        if not isinstance(source_manifest, dict):
            raise ValueError(
                "rollback source bytes are not a JSON object"
            )
        source_model = _mapping(
            source_manifest.get("model"),
            name="rollback source manifest model",
        )
        if source_model.get("default_name") != comparable["current"]:
            raise ValueError(
                "rollback source manifest does not restore current model"
            )
        allowed_names = source_model.get("allowed_names")
        if (
            not isinstance(allowed_names, list)
            or comparable["proposed"] not in allowed_names
        ):
            raise ValueError(
                "rollback source manifest does not allow proposed model"
            )
    if payload.get("safety_boundaries") != _PLAN_SAFETY_BOUNDARIES:
        raise ValueError(
            "configuration preapplication safety_boundaries are invalid"
        )
    expected_fingerprint = _validated_fingerprint(
        payload.get("plan_fingerprint"),
        name="configuration preapplication plan fingerprint",
    )
    unsigned = dict(payload)
    unsigned.pop("plan_fingerprint", None)
    if not hmac.compare_digest(
        expected_fingerprint,
        _fingerprint(unsigned),
    ):
        raise ValueError(
            "configuration preapplication plan fingerprint mismatch"
        )


def _plan_verification_payload(
    *,
    status: str,
    action: str,
    reason_codes: list[str],
    identity: Mapping[str, bool],
) -> dict[str, Any]:
    return {
        "schema_version": _PLAN_VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "action": action,
        "reason_codes": reason_codes,
        "identity": dict(identity),
        "eligible_for_future_single_use_application_attempt": (
            status == "current"
        ),
        "configuration_change_applied": False,
        "approval_consumed": False,
        "model_execution_performed": False,
    }


def verify_write_model_configuration_preapplication_plan(
    receipt: Mapping[str, Any],
    *,
    current_routing_snapshot: Mapping[str, Any],
    expected_approval_path: str | Path,
    now: datetime,
) -> dict[str, Any]:
    """Verify a plan against fresh runtime resolution and source files."""

    validate_write_model_configuration_preapplication_plan(receipt)
    validate_write_scene_model_routing_snapshot(
        current_routing_snapshot
    )
    identity = {
        "approval_path": False,
        "approval_file_fingerprint": False,
        "approval_content_fingerprint": False,
        "approval_current": False,
        "routing_snapshot_file_fingerprint": False,
        "routing_snapshot_content_fingerprint": False,
        "routing_snapshot_sources_current": False,
        "fresh_runtime_snapshot_match": False,
        "plan_fingerprint": False,
    }
    approval_source = _mapping(
        receipt.get("source_approval"),
        name="source_approval",
    )
    source_approval_path = _absolute_path(
        approval_source.get("path"),
        name="source_approval.path",
    )
    explicit_approval_path = Path(
        expected_approval_path
    ).expanduser().resolve()
    identity["approval_path"] = (
        source_approval_path == explicit_approval_path
    )
    if not identity["approval_path"]:
        return _plan_verification_payload(
            status="approval_mismatch",
            action="stop",
            reason_codes=["explicit_approval_path_does_not_match_plan"],
            identity=identity,
        )
    if (
        not source_approval_path.is_file()
        or not hmac.compare_digest(
            _validated_fingerprint(
                approval_source.get("fingerprint"),
                name="source_approval.fingerprint",
            ),
            _file_fingerprint(source_approval_path),
        )
    ):
        return _plan_verification_payload(
            status="approval_changed",
            action="stop",
            reason_codes=["approval_file_fingerprint_changed"],
            identity=identity,
        )
    identity["approval_file_fingerprint"] = True
    _approval_path, approval = (
        load_write_model_configuration_change_approval(
            source_approval_path
        )
    )
    identity["approval_content_fingerprint"] = hmac.compare_digest(
        _validated_fingerprint(
            approval_source.get("content_fingerprint"),
            name="source_approval.content_fingerprint",
        ),
        _validated_fingerprint(
            approval.get("approval_fingerprint"),
            name="approval fingerprint",
        ),
    )
    if not identity["approval_content_fingerprint"]:
        return _plan_verification_payload(
            status="approval_changed",
            action="stop",
            reason_codes=["approval_content_fingerprint_changed"],
            identity=identity,
        )
    approval_verification = (
        verify_write_model_configuration_change_approval(
            approval,
            now=now,
        )
    )
    identity["approval_current"] = (
        approval_verification.get("status") == "approved"
    )
    if not identity["approval_current"]:
        return _plan_verification_payload(
            status="approval_not_current",
            action="stop",
            reason_codes=[
                f"approval_{approval_verification.get('status', 'invalid')}"
            ],
            identity=identity,
        )
    snapshot_source = _mapping(
        receipt.get("source_routing_snapshot"),
        name="source_routing_snapshot",
    )
    snapshot_path = _absolute_path(
        snapshot_source.get("path"),
        name="source_routing_snapshot.path",
    )
    if not snapshot_path.is_file() or not hmac.compare_digest(
        _validated_fingerprint(
            snapshot_source.get("fingerprint"),
            name="source_routing_snapshot.fingerprint",
        ),
        _file_fingerprint(snapshot_path),
    ):
        return _plan_verification_payload(
            status="routing_snapshot_changed",
            action="stop",
            reason_codes=["routing_snapshot_file_fingerprint_changed"],
            identity=identity,
        )
    identity["routing_snapshot_file_fingerprint"] = True
    _resolved_snapshot_path, source_snapshot = (
        load_write_scene_model_routing_snapshot(snapshot_path)
    )
    identity["routing_snapshot_content_fingerprint"] = (
        hmac.compare_digest(
            _validated_fingerprint(
                snapshot_source.get("content_fingerprint"),
                name="source_routing_snapshot.content_fingerprint",
            ),
            _validated_fingerprint(
                source_snapshot.get("snapshot_fingerprint"),
                name="source routing snapshot fingerprint",
            ),
        )
    )
    if not identity["routing_snapshot_content_fingerprint"]:
        return _plan_verification_payload(
            status="routing_snapshot_changed",
            action="stop",
            reason_codes=["routing_snapshot_content_fingerprint_changed"],
            identity=identity,
        )
    source_snapshot_verification = (
        verify_write_scene_model_routing_snapshot(source_snapshot)
    )
    identity["routing_snapshot_sources_current"] = (
        source_snapshot_verification.get("status") == "current"
    )
    if not identity["routing_snapshot_sources_current"]:
        return _plan_verification_payload(
            status="current_configuration_changed",
            action="stop",
            reason_codes=[
                "routing_snapshot_configuration_sources_changed"
            ],
            identity=identity,
        )
    identity["fresh_runtime_snapshot_match"] = hmac.compare_digest(
        _validated_fingerprint(
            source_snapshot.get("snapshot_fingerprint"),
            name="source routing snapshot fingerprint",
        ),
        _validated_fingerprint(
            current_routing_snapshot.get("snapshot_fingerprint"),
            name="current routing snapshot fingerprint",
        ),
    )
    if not identity["fresh_runtime_snapshot_match"]:
        return _plan_verification_payload(
            status="current_runtime_routing_changed",
            action="stop",
            reason_codes=[
                "fresh_runtime_snapshot_does_not_match_plan_source"
            ],
            identity=identity,
        )
    try:
        current_plan = (
            build_write_model_configuration_preapplication_plan(
                approval_path=source_approval_path,
                routing_snapshot_path=snapshot_path,
                now=now,
            )
        )
    except WriteModelConfigurationPreapplicationBlockedError:
        return _plan_verification_payload(
            status="plan_no_longer_eligible",
            action="stop",
            reason_codes=["preapplication_plan_cannot_be_rebuilt"],
            identity=identity,
        )
    identity["plan_fingerprint"] = hmac.compare_digest(
        _validated_fingerprint(
            receipt.get("plan_fingerprint"),
            name="configuration preapplication plan fingerprint",
        ),
        _validated_fingerprint(
            current_plan.get("plan_fingerprint"),
            name="current configuration preapplication plan fingerprint",
        ),
    )
    if not identity["plan_fingerprint"]:
        return _plan_verification_payload(
            status="plan_changed",
            action="stop",
            reason_codes=["preapplication_plan_fingerprint_changed"],
            identity=identity,
        )
    return _plan_verification_payload(
        status="current",
        action="separate_atomic_application_command_required",
        reason_codes=[
            "eligible_for_future_single_use_application_attempt"
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
        raise ValueError(f"invalid {name} JSON: {target}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be an object: {target}")
    return target, raw


def load_write_scene_model_routing_snapshot(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one resolved-routing snapshot."""

    target, payload = _load_json_object(
        path,
        name="write scene model routing snapshot",
    )
    validate_write_scene_model_routing_snapshot(payload)
    return target, payload


def load_write_model_configuration_preapplication_plan(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one configuration pre-application plan."""

    target, payload = _load_json_object(
        path,
        name="configuration preapplication plan",
    )
    validate_write_model_configuration_preapplication_plan(payload)
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


def persist_write_scene_model_routing_snapshot(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist an immutable resolved-routing snapshot."""

    validate_write_scene_model_routing_snapshot(payload)
    return _persist_immutable(payload, path)


def persist_write_model_configuration_preapplication_plan(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist an immutable configuration pre-application plan."""

    validate_write_model_configuration_preapplication_plan(payload)
    return _persist_immutable(payload, path)


def format_write_scene_model_routing_snapshot_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact operator-facing routing snapshot report."""

    scenes = payload.get("scenes")
    scene_count = len(scenes) if isinstance(scenes, list) else 0
    context = _mapping(
        payload.get("resolution_context"),
        name="routing snapshot resolution_context",
    )
    has_overrides = bool(
        context.get("write_model_override_name")
        or context.get("audit_model_override_name")
    )
    return (
        "",
        "=" * 60,
        "Write scene model routing snapshot",
        "-" * 60,
        f"  Status      : {payload.get('status', 'unknown')}",
        f"  Ticker      : {payload.get('ticker', 'unknown')}",
        f"  Scene count : {scene_count}",
        f"  Overrides   : {'present' if has_overrides else 'none'}",
        "  Boundary    : preflight snapshot; configuration unchanged",
        "=" * 60,
        "",
    )


def format_write_model_configuration_preapplication_plan_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact operator-facing pre-application plan report."""

    transitions = payload.get("transitions")
    transition_count = (
        len(transitions) if isinstance(transitions, list) else 0
    )
    rollback = _mapping(
        payload.get("rollback"),
        name="configuration preapplication rollback",
    )
    return (
        "",
        "=" * 60,
        "Configuration pre-application plan",
        "-" * 60,
        f"  Status      : {payload.get('status', 'unknown')}",
        f"  Ticker      : {payload.get('ticker', 'unknown')}",
        f"  Transitions : {transition_count}",
        "  Rollback ref: "
        f"{rollback.get('rollback_reference', 'unknown')}",
        "  Boundary    : plan only; approval unconsumed; config unchanged",
        "=" * 60,
        "",
    )


def format_write_model_configuration_preapplication_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format one plan verification result."""

    reasons = payload.get("reason_codes")
    reason_text = (
        ", ".join(str(value) for value in reasons)
        if isinstance(reasons, list) and reasons
        else "none"
    )
    return (
        "",
        "=" * 60,
        "Configuration pre-application verification",
        "-" * 60,
        f"  Status      : {payload.get('status', 'unknown')}",
        f"  Action      : {payload.get('action', 'unknown')}",
        f"  Reasons     : {reason_text}",
        "  Applied     : no",
        "  Approval used: no",
        "  Model calls : no",
        "=" * 60,
        "",
    )


__all__ = [
    "WriteModelConfigurationPreapplicationBlockedError",
    "build_write_model_configuration_preapplication_plan",
    "build_write_scene_model_routing_snapshot",
    "format_write_model_configuration_preapplication_plan_report",
    "format_write_model_configuration_preapplication_verification_report",
    "format_write_scene_model_routing_snapshot_report",
    "load_write_model_configuration_preapplication_plan",
    "load_write_scene_model_routing_snapshot",
    "persist_write_model_configuration_preapplication_plan",
    "persist_write_scene_model_routing_snapshot",
    "validate_write_model_configuration_preapplication_plan",
    "validate_write_scene_model_routing_snapshot",
    "verify_write_model_configuration_preapplication_plan",
    "verify_write_scene_model_routing_snapshot",
]
