"""Build tamper-evident, review-only Challenger promotion proposals."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dayu.services.write_run_comparison import (
    compare_write_run_paths,
    load_write_run_comparison,
    load_write_run_summary,
)

_PROPOSAL_SCHEMA_VERSION = (
    "write_model_challenger_promotion_proposal_v1"
)
_VERIFICATION_SCHEMA_VERSION = (
    "write_model_challenger_promotion_verification_v1"
)
_PROPOSAL_TYPE = "write_model_challenger_promotion_review"
_PROPOSAL_SCOPE = "review_only_no_configuration_change"
_PROPOSAL_STATUS = "ready_for_human_review"
_SOURCE_SEMANTICS = (
    "configured_scene_models_recorded_by_completed_runs"
)
_SAFETY_BOUNDARIES = [
    "review_only",
    "no_model_execution",
    "no_configuration_change",
    "no_promotion_authorization",
    "source_artifacts_must_remain_current",
]
_BASE_REVIEW_REQUIREMENTS = [
    "verify_current_runtime_configuration",
    "separate_change_approval_required",
]
_PROPOSAL_FIELDS = {
    "schema_version",
    "proposal_type",
    "scope",
    "status",
    "ticker",
    "sources",
    "comparison",
    "model_plan_review",
    "safety_boundaries",
    "proposal_fingerprint",
}
_SOURCE_NAMES = (
    "champion_summary",
    "challenger_summary",
    "comparison",
)
_SOURCE_FIELDS = {"path", "fingerprint"}
_COMPARISON_FIELDS = {
    "schema_version",
    "verdict",
    "reason_codes",
}
_MODEL_PLAN_REVIEW_FIELDS = {
    "source_semantics",
    "changed_roles",
    "all_changed_roles_unambiguous",
    "roles",
    "review_requirements",
}
_ROLE_FIELDS = {
    "role",
    "changed",
    "transition_unambiguous",
    "champion_model_names",
    "challenger_model_names",
    "champion_scenes",
    "challenger_scenes",
}
_SCENE_FIELDS = {"scene_name", "model_name"}
_ROLE_NAMES = ("primary", "audit")


class WriteModelChallengerPromotionBlockedError(ValueError):
    """Raised when completed evidence does not support a promotion review."""


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


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


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
    return normalized


def _string_list(
    value: object,
    *,
    name: str,
    require_sorted_unique: bool = False,
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
    if require_sorted_unique and result != sorted(set(result)):
        raise ValueError(f"{name} must be sorted and unique")
    return result


def _extract_model_names(
    summary: Mapping[str, Any],
    *,
    role_name: str,
) -> list[str]:
    roles = _mapping(
        summary.get("model_roles"),
        name="run summary model_roles",
    )
    role = _mapping(
        roles.get(role_name),
        name=f"run summary model_roles.{role_name}",
    )
    raw_names = role.get("model_names")
    if not isinstance(raw_names, list):
        raise ValueError(
            f"run summary model_roles.{role_name}.model_names "
            "must be a list"
        )
    names = [
        _required_text(
            item,
            name=(
                "run summary "
                f"model_roles.{role_name}.model_names[{index}]"
            ),
            maximum_length=256,
        )
        for index, item in enumerate(raw_names)
    ]
    return sorted(set(names))


def _extract_scenes(
    summary: Mapping[str, Any],
    *,
    role_name: str,
) -> list[dict[str, str]]:
    roles = _mapping(
        summary.get("model_roles"),
        name="run summary model_roles",
    )
    role = _mapping(
        roles.get(role_name),
        name=f"run summary model_roles.{role_name}",
    )
    raw_scenes = role.get("scenes")
    if not isinstance(raw_scenes, list):
        raise ValueError(
            f"run summary model_roles.{role_name}.scenes "
            "must be a list"
        )
    scenes: list[dict[str, str]] = []
    for index, raw_scene in enumerate(raw_scenes):
        scene = _mapping(
            raw_scene,
            name=(
                "run summary "
                f"model_roles.{role_name}.scenes[{index}]"
            ),
        )
        scenes.append(
            {
                "scene_name": _required_text(
                    scene.get("scene_name"),
                    name=(
                        "run summary "
                        f"model_roles.{role_name}.scenes"
                        f"[{index}].scene_name"
                    ),
                    maximum_length=128,
                ),
                "model_name": _required_text(
                    scene.get("model_name"),
                    name=(
                        "run summary "
                        f"model_roles.{role_name}.scenes"
                        f"[{index}].model_name"
                    ),
                    maximum_length=256,
                ),
            }
        )
    return sorted(
        scenes,
        key=lambda item: (
            item["scene_name"],
            item["model_name"],
        ),
    )


def _transition_is_unambiguous(
    *,
    changed: bool,
    champion_model_names: list[str],
    challenger_model_names: list[str],
    champion_scenes: list[dict[str, str]],
    challenger_scenes: list[dict[str, str]],
) -> bool:
    if not changed:
        return True
    if (
        len(champion_model_names) != 1
        or len(challenger_model_names) != 1
        or not champion_scenes
        or not challenger_scenes
    ):
        return False
    champion_scene_names = [
        scene["scene_name"] for scene in champion_scenes
    ]
    challenger_scene_names = [
        scene["scene_name"] for scene in challenger_scenes
    ]
    if (
        len(champion_scene_names)
        != len(set(champion_scene_names))
        or len(challenger_scene_names)
        != len(set(challenger_scene_names))
        or champion_scene_names != challenger_scene_names
    ):
        return False
    return all(
        scene["model_name"] == champion_model_names[0]
        for scene in champion_scenes
    ) and all(
        scene["model_name"] == challenger_model_names[0]
        for scene in challenger_scenes
    )


def _build_role_review(
    *,
    role_name: str,
    champion: Mapping[str, Any],
    challenger: Mapping[str, Any],
) -> dict[str, Any]:
    champion_model_names = _extract_model_names(
        champion,
        role_name=role_name,
    )
    challenger_model_names = _extract_model_names(
        challenger,
        role_name=role_name,
    )
    champion_scenes = _extract_scenes(
        champion,
        role_name=role_name,
    )
    challenger_scenes = _extract_scenes(
        challenger,
        role_name=role_name,
    )
    changed = champion_model_names != challenger_model_names
    return {
        "role": role_name,
        "changed": changed,
        "transition_unambiguous": _transition_is_unambiguous(
            changed=changed,
            champion_model_names=champion_model_names,
            challenger_model_names=challenger_model_names,
            champion_scenes=champion_scenes,
            challenger_scenes=challenger_scenes,
        ),
        "champion_model_names": champion_model_names,
        "challenger_model_names": challenger_model_names,
        "champion_scenes": champion_scenes,
        "challenger_scenes": challenger_scenes,
    }


def _source_entry(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "fingerprint": _file_fingerprint(path),
    }


def build_write_model_challenger_promotion_proposal(
    comparison_path: str | Path,
) -> dict[str, Any]:
    """Build a deterministic review proposal from persisted run evidence."""

    resolved_comparison_path, comparison = (
        load_write_run_comparison(comparison_path)
    )
    if comparison.get("schema_version") != "write_run_comparison_v2":
        raise ValueError(
            "promotion proposals require write_run_comparison_v2"
        )
    sources = _mapping(
        comparison.get("sources"),
        name="comparison sources",
    )
    champion_source = _required_text(
        sources.get("champion"),
        name="comparison sources.champion",
    )
    challenger_source = _required_text(
        sources.get("challenger"),
        name="comparison sources.challenger",
    )
    champion_path, champion = load_write_run_summary(
        champion_source
    )
    challenger_path, challenger = load_write_run_summary(
        challenger_source
    )
    recomputed = compare_write_run_paths(
        champion_path,
        challenger_path,
    )
    if _canonical_json(comparison) != _canonical_json(recomputed):
        raise ValueError(
            "persisted comparison does not match its source summaries"
        )
    if comparison.get("verdict") != "promote_challenger":
        raise WriteModelChallengerPromotionBlockedError(
            "persisted comparison does not recommend promotion"
        )
    ticker = _required_text(
        comparison.get("ticker"),
        name="comparison ticker",
        maximum_length=64,
    )
    if champion.get("ticker") != ticker or challenger.get(
        "ticker"
    ) != ticker:
        raise ValueError(
            "comparison ticker does not match both source summaries"
        )
    roles = [
        _build_role_review(
            role_name=role_name,
            champion=champion,
            challenger=challenger,
        )
        for role_name in _ROLE_NAMES
    ]
    changed_roles = [
        str(role["role"])
        for role in roles
        if role["changed"] is True
    ]
    if not changed_roles:
        raise ValueError(
            "promotion comparison does not contain a changed model role"
        )
    all_unambiguous = all(
        role["transition_unambiguous"] is True
        for role in roles
        if role["changed"] is True
    )
    review_requirements = list(_BASE_REVIEW_REQUIREMENTS)
    if not all_unambiguous:
        review_requirements.append(
            "resolve_ambiguous_model_roles"
        )
    reason_codes = _string_list(
        comparison.get("reason_codes"),
        name="comparison reason_codes",
    )
    payload: dict[str, Any] = {
        "schema_version": _PROPOSAL_SCHEMA_VERSION,
        "proposal_type": _PROPOSAL_TYPE,
        "scope": _PROPOSAL_SCOPE,
        "status": _PROPOSAL_STATUS,
        "ticker": ticker,
        "sources": {
            "champion_summary": _source_entry(champion_path),
            "challenger_summary": _source_entry(
                challenger_path
            ),
            "comparison": _source_entry(
                resolved_comparison_path
            ),
        },
        "comparison": {
            "schema_version": comparison["schema_version"],
            "verdict": comparison["verdict"],
            "reason_codes": reason_codes,
        },
        "model_plan_review": {
            "source_semantics": _SOURCE_SEMANTICS,
            "changed_roles": changed_roles,
            "all_changed_roles_unambiguous": all_unambiguous,
            "roles": roles,
            "review_requirements": review_requirements,
        },
        "safety_boundaries": list(_SAFETY_BOUNDARIES),
    }
    payload["proposal_fingerprint"] = _fingerprint(payload)
    validate_write_model_challenger_promotion_proposal(payload)
    return payload


def _validate_source(
    value: object,
    *,
    name: str,
) -> None:
    source = _mapping(value, name=name)
    _validate_exact_fields(
        source,
        expected=_SOURCE_FIELDS,
        name=name,
    )
    path_text = _required_text(
        source.get("path"),
        name=f"{name}.path",
    )
    if not Path(path_text).is_absolute():
        raise ValueError(f"{name}.path must be absolute")
    _validated_fingerprint(
        source.get("fingerprint"),
        name=f"{name}.fingerprint",
    )


def _validate_scene_list(
    value: object,
    *,
    name: str,
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    scenes: list[dict[str, str]] = []
    for index, raw_scene in enumerate(value):
        scene = _mapping(
            raw_scene,
            name=f"{name}[{index}]",
        )
        _validate_exact_fields(
            scene,
            expected=_SCENE_FIELDS,
            name=f"{name}[{index}]",
        )
        scenes.append(
            {
                "scene_name": _required_text(
                    scene.get("scene_name"),
                    name=f"{name}[{index}].scene_name",
                    maximum_length=128,
                ),
                "model_name": _required_text(
                    scene.get("model_name"),
                    name=f"{name}[{index}].model_name",
                    maximum_length=256,
                ),
            }
        )
    expected = sorted(
        scenes,
        key=lambda item: (
            item["scene_name"],
            item["model_name"],
        ),
    )
    if scenes != expected:
        raise ValueError(f"{name} must be sorted")
    return scenes


def _validate_role(
    value: object,
    *,
    expected_role: str,
    name: str,
) -> dict[str, Any]:
    role = _mapping(value, name=name)
    _validate_exact_fields(
        role,
        expected=_ROLE_FIELDS,
        name=name,
    )
    if role.get("role") != expected_role:
        raise ValueError(
            f"{name}.role must be {expected_role!r}"
        )
    changed = role.get("changed")
    unambiguous = role.get("transition_unambiguous")
    if not isinstance(changed, bool):
        raise ValueError(f"{name}.changed must be a boolean")
    if not isinstance(unambiguous, bool):
        raise ValueError(
            f"{name}.transition_unambiguous must be a boolean"
        )
    champion_names = _string_list(
        role.get("champion_model_names"),
        name=f"{name}.champion_model_names",
        require_sorted_unique=True,
    )
    challenger_names = _string_list(
        role.get("challenger_model_names"),
        name=f"{name}.challenger_model_names",
        require_sorted_unique=True,
    )
    champion_scenes = _validate_scene_list(
        role.get("champion_scenes"),
        name=f"{name}.champion_scenes",
    )
    challenger_scenes = _validate_scene_list(
        role.get("challenger_scenes"),
        name=f"{name}.challenger_scenes",
    )
    expected_changed = champion_names != challenger_names
    if changed is not expected_changed:
        raise ValueError(f"{name}.changed is inconsistent")
    expected_unambiguous = _transition_is_unambiguous(
        changed=changed,
        champion_model_names=champion_names,
        challenger_model_names=challenger_names,
        champion_scenes=champion_scenes,
        challenger_scenes=challenger_scenes,
    )
    if unambiguous is not expected_unambiguous:
        raise ValueError(
            f"{name}.transition_unambiguous is inconsistent"
        )
    return {
        "role": expected_role,
        "changed": changed,
        "transition_unambiguous": unambiguous,
    }


def validate_write_model_challenger_promotion_proposal(
    payload: Mapping[str, Any],
) -> None:
    """Validate the strict proposal schema and content fingerprint."""

    _validate_exact_fields(
        payload,
        expected=_PROPOSAL_FIELDS,
        name="promotion proposal",
    )
    constants = {
        "schema_version": _PROPOSAL_SCHEMA_VERSION,
        "proposal_type": _PROPOSAL_TYPE,
        "scope": _PROPOSAL_SCOPE,
        "status": _PROPOSAL_STATUS,
    }
    for field_name, expected in constants.items():
        if payload.get(field_name) != expected:
            raise ValueError(
                f"promotion proposal {field_name} must be "
                f"{expected!r}"
            )
    _required_text(
        payload.get("ticker"),
        name="promotion proposal ticker",
        maximum_length=64,
    )
    sources = _mapping(
        payload.get("sources"),
        name="promotion proposal sources",
    )
    if set(sources) != set(_SOURCE_NAMES):
        raise ValueError(
            "promotion proposal sources must contain champion_summary, "
            "challenger_summary, and comparison"
        )
    for source_name in _SOURCE_NAMES:
        _validate_source(
            sources.get(source_name),
            name=f"promotion proposal sources.{source_name}",
        )

    comparison = _mapping(
        payload.get("comparison"),
        name="promotion proposal comparison",
    )
    _validate_exact_fields(
        comparison,
        expected=_COMPARISON_FIELDS,
        name="promotion proposal comparison",
    )
    if comparison.get("schema_version") != (
        "write_run_comparison_v2"
    ):
        raise ValueError(
            "promotion proposal comparison schema_version is invalid"
        )
    if comparison.get("verdict") != "promote_challenger":
        raise ValueError(
            "promotion proposal comparison verdict is invalid"
        )
    _string_list(
        comparison.get("reason_codes"),
        name="promotion proposal comparison.reason_codes",
    )

    review = _mapping(
        payload.get("model_plan_review"),
        name="promotion proposal model_plan_review",
    )
    _validate_exact_fields(
        review,
        expected=_MODEL_PLAN_REVIEW_FIELDS,
        name="promotion proposal model_plan_review",
    )
    if review.get("source_semantics") != _SOURCE_SEMANTICS:
        raise ValueError(
            "promotion proposal source semantics are invalid"
        )
    raw_roles = review.get("roles")
    if not isinstance(raw_roles, list) or len(raw_roles) != len(
        _ROLE_NAMES
    ):
        raise ValueError(
            "promotion proposal roles must contain primary and audit"
        )
    validated_roles = [
        _validate_role(
            raw_roles[index],
            expected_role=role_name,
            name=f"promotion proposal roles[{index}]",
        )
        for index, role_name in enumerate(_ROLE_NAMES)
    ]
    expected_changed_roles = [
        str(role["role"])
        for role in validated_roles
        if role["changed"] is True
    ]
    changed_roles = _string_list(
        review.get("changed_roles"),
        name="promotion proposal changed_roles",
    )
    if changed_roles != expected_changed_roles or not changed_roles:
        raise ValueError(
            "promotion proposal changed_roles are inconsistent"
        )
    expected_all_unambiguous = all(
        role["transition_unambiguous"] is True
        for role in validated_roles
        if role["changed"] is True
    )
    if review.get("all_changed_roles_unambiguous") is not (
        expected_all_unambiguous
    ):
        raise ValueError(
            "promotion proposal ambiguity summary is inconsistent"
        )
    expected_requirements = list(_BASE_REVIEW_REQUIREMENTS)
    if not expected_all_unambiguous:
        expected_requirements.append(
            "resolve_ambiguous_model_roles"
        )
    requirements = _string_list(
        review.get("review_requirements"),
        name="promotion proposal review_requirements",
    )
    if requirements != expected_requirements:
        raise ValueError(
            "promotion proposal review_requirements are invalid"
        )
    if payload.get("safety_boundaries") != _SAFETY_BOUNDARIES:
        raise ValueError(
            "promotion proposal safety_boundaries are invalid"
        )
    expected_fingerprint = _validated_fingerprint(
        payload.get("proposal_fingerprint"),
        name="promotion proposal proposal_fingerprint",
    )
    unsigned = dict(payload)
    unsigned.pop("proposal_fingerprint", None)
    actual_fingerprint = _fingerprint(unsigned)
    if not hmac.compare_digest(
        expected_fingerprint,
        actual_fingerprint,
    ):
        raise ValueError(
            "write model Challenger promotion proposal "
            "fingerprint mismatch"
        )


def load_write_model_challenger_promotion_proposal(
    path: str | Path,
) -> tuple[Path, dict[str, Any]]:
    """Load and validate one exported promotion proposal."""

    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"promotion proposal does not exist: {resolved}"
        )
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid promotion proposal JSON: {resolved}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError(
            f"promotion proposal must be a JSON object: {resolved}"
        )
    validate_write_model_challenger_promotion_proposal(raw)
    return resolved, raw


def _serialize(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def persist_write_model_challenger_promotion_proposal(
    payload: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Persist an immutable proposal; identical content is idempotent."""

    validate_write_model_challenger_promotion_proposal(payload)
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = _serialize(payload)
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


def _verification_payload(
    *,
    status: str,
    action: str,
    reason_codes: list[str],
    identity: Mapping[str, bool],
) -> dict[str, Any]:
    return {
        "schema_version": _VERIFICATION_SCHEMA_VERSION,
        "status": status,
        "action": action,
        "reason_codes": reason_codes,
        "identity": dict(identity),
        "authorizes_configuration_change": False,
        "authorizes_promotion": False,
    }


def verify_write_model_challenger_promotion_proposal(
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify that a proposal still binds current, reproducible evidence."""

    validate_write_model_challenger_promotion_proposal(receipt)
    sources = _mapping(
        receipt.get("sources"),
        name="promotion proposal sources",
    )
    identity = {
        "champion_summary_fingerprint": False,
        "challenger_summary_fingerprint": False,
        "comparison_fingerprint": False,
        "comparison_recomputed": False,
        "proposal_fingerprint": False,
    }
    reason_codes: list[str] = []
    source_identity_names = {
        "champion_summary": "champion_summary_fingerprint",
        "challenger_summary": "challenger_summary_fingerprint",
        "comparison": "comparison_fingerprint",
    }
    for source_name in _SOURCE_NAMES:
        source = _mapping(
            sources.get(source_name),
            name=f"promotion proposal sources.{source_name}",
        )
        source_path = Path(
            str(source["path"])
        ).expanduser().resolve()
        expected = str(source["fingerprint"])
        matched = source_path.is_file() and hmac.compare_digest(
            expected,
            _file_fingerprint(source_path),
        )
        identity[source_identity_names[source_name]] = matched
        if not matched:
            reason_codes.append(
                f"{source_name}_fingerprint_changed"
            )
    if reason_codes:
        return _verification_payload(
            status="stale_sources",
            action="stop",
            reason_codes=reason_codes,
            identity=identity,
        )

    comparison_source = _mapping(
        sources.get("comparison"),
        name="promotion proposal sources.comparison",
    )
    comparison_path, persisted_comparison = (
        load_write_run_comparison(str(comparison_source["path"]))
    )
    champion_source = _mapping(
        sources.get("champion_summary"),
        name="promotion proposal sources.champion_summary",
    )
    challenger_source = _mapping(
        sources.get("challenger_summary"),
        name="promotion proposal sources.challenger_summary",
    )
    recomputed = compare_write_run_paths(
        str(champion_source["path"]),
        str(challenger_source["path"]),
    )
    identity["comparison_recomputed"] = hmac.compare_digest(
        _canonical_json(persisted_comparison),
        _canonical_json(recomputed),
    )
    if not identity["comparison_recomputed"]:
        return _verification_payload(
            status="comparison_changed",
            action="stop",
            reason_codes=[
                "comparison_no_longer_matches_source_summaries"
            ],
            identity=identity,
        )
    try:
        current = build_write_model_challenger_promotion_proposal(
            comparison_path
        )
    except WriteModelChallengerPromotionBlockedError:
        return _verification_payload(
            status="comparison_not_promotable",
            action="stop",
            reason_codes=[
                "comparison_no_longer_recommends_promotion"
            ],
            identity=identity,
        )
    receipt_fingerprint = _validated_fingerprint(
        receipt.get("proposal_fingerprint"),
        name="promotion proposal proposal_fingerprint",
    )
    current_fingerprint = _validated_fingerprint(
        current.get("proposal_fingerprint"),
        name="current promotion proposal proposal_fingerprint",
    )
    identity["proposal_fingerprint"] = hmac.compare_digest(
        receipt_fingerprint,
        current_fingerprint,
    )
    if not identity["proposal_fingerprint"]:
        return _verification_payload(
            status="proposal_changed",
            action="stop",
            reason_codes=["proposal_fingerprint_changed"],
            identity=identity,
        )
    return _verification_payload(
        status="current",
        action="human_review_only",
        reason_codes=[],
        identity=identity,
    )


def format_write_model_challenger_promotion_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact operator-facing review proposal report."""

    review = _mapping(
        payload.get("model_plan_review"),
        name="promotion proposal model_plan_review",
    )
    return (
        "",
        "=" * 60,
        "Challenger promotion review proposal",
        "-" * 60,
        f"  Status       : {payload.get('status', 'unknown')}",
        f"  Ticker       : {payload.get('ticker', 'unknown')}",
        "  Changed roles: "
        + ", ".join(
            str(value)
            for value in review.get("changed_roles", [])
        ),
        "  Unambiguous  : "
        + (
            "yes"
            if review.get(
                "all_changed_roles_unambiguous"
            )
            is True
            else "no"
        ),
        "  Boundary     : review only; no configuration change",
        "=" * 60,
        "",
    )


def format_write_model_challenger_promotion_verification_report(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    """Format a compact proposal-currentness verification report."""

    reason_codes = payload.get("reason_codes")
    reasons = (
        ", ".join(str(value) for value in reason_codes)
        if isinstance(reason_codes, list) and reason_codes
        else "none"
    )
    return (
        "",
        "=" * 60,
        "Challenger promotion proposal verification",
        "-" * 60,
        f"  Status   : {payload.get('status', 'unknown')}",
        f"  Action   : {payload.get('action', 'unknown')}",
        f"  Reasons  : {reasons}",
        "  Boundary : no configuration change; no promotion authorization",
        "=" * 60,
        "",
    )
