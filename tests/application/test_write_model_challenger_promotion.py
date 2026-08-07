"""Review-only promotion proposal tests for completed Challenger runs."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from dayu.services.write_model_challenger_promotion import (
    WriteModelChallengerPromotionBlockedError,
    build_write_model_challenger_promotion_proposal,
    load_write_model_challenger_promotion_proposal,
    persist_write_model_challenger_promotion_proposal,
    validate_write_model_challenger_promotion_proposal,
    verify_write_model_challenger_promotion_proposal,
)
from dayu.services.write_run_comparison import (
    compare_write_run_paths,
    persist_write_run_comparison,
)


def _summary(
    *,
    primary_model: str,
    cost: float,
    primary_scene_models: dict[str, str] | None = None,
    gate_status: str = "passed",
) -> dict[str, Any]:
    scene_models = primary_scene_models or {
        "infer": primary_model,
        "write": primary_model,
        "decision": primary_model,
        "overview": primary_model,
    }
    primary_names = sorted(set(scene_models.values()))
    failed_count = 0 if gate_status == "passed" else 1
    return {
        "schema_version": "write_run_summary_v3",
        "ticker": "AAPL",
        "gate_status": gate_status,
        "model_roles": {
            "primary": {
                "model_names": primary_names,
                "scenes": [
                    {
                        "scene_name": scene_name,
                        "model_name": model_name,
                        "temperature": 0.2,
                    }
                    for scene_name, model_name in sorted(
                        scene_models.items()
                    )
                ],
            },
            "audit": {
                "model_names": ["audit-model"],
                "scenes": [
                    {
                        "scene_name": "audit",
                        "model_name": "audit-model",
                        "temperature": 0.0,
                    },
                    {
                        "scene_name": "confirm",
                        "model_name": "audit-model",
                        "temperature": 0.0,
                    },
                ],
            },
        },
        "model_usage": {
            "usage_status": "complete",
            "scene_call_count": 10,
            "request_count": 10,
            "total_tokens": 1_000,
            "cost": {
                "status": "complete",
                "currency": "CNY",
                "known_estimated_cost": cost,
            },
        },
        "model_routing": {
            "fallback_switch_count": 0,
            "fallback_call_completed_count": 0,
            "fallback_call_error_count": 0,
            "routes": [],
        },
        "chapter_count": 1,
        "failed_count": failed_count,
        "audit": {
            "required": True,
            "failed_count": 0,
            "gate_blocked_count": 0,
            "first_pass_count": 1,
            "total_retries": 0,
        },
        "chapters": [
            {
                "index": 1,
                "title": "Business",
                "gate_passed": gate_status == "passed",
                "audit_passed": True,
            }
        ],
    }


def _write_comparison(
    tmp_path: Path,
    *,
    champion: dict[str, Any] | None = None,
    challenger: dict[str, Any] | None = None,
) -> Path:
    champion_dir = tmp_path / "champion"
    challenger_dir = tmp_path / "challenger"
    champion_dir.mkdir(parents=True)
    challenger_dir.mkdir(parents=True)
    (champion_dir / "run_summary.json").write_text(
        json.dumps(
            champion
            or _summary(
                primary_model="deepseek-primary",
                cost=1.0,
            )
        ),
        encoding="utf-8",
    )
    (challenger_dir / "run_summary.json").write_text(
        json.dumps(
            challenger
            or _summary(
                primary_model="mimo-challenger",
                cost=0.7,
            )
        ),
        encoding="utf-8",
    )
    comparison = compare_write_run_paths(
        champion_dir,
        challenger_dir,
    )
    return persist_write_run_comparison(
        comparison,
        champion_dir / "challenger_comparison.json",
    )


@pytest.mark.unit
def test_build_promotion_proposal_binds_completed_run_evidence(
    tmp_path: Path,
) -> None:
    comparison_path = _write_comparison(tmp_path)

    proposal = build_write_model_challenger_promotion_proposal(
        comparison_path
    )

    assert proposal["schema_version"] == (
        "write_model_challenger_promotion_proposal_v1"
    )
    assert proposal["proposal_type"] == (
        "write_model_challenger_promotion_review"
    )
    assert proposal["scope"] == "review_only_no_configuration_change"
    assert proposal["status"] == "ready_for_human_review"
    assert proposal["comparison"] == {
        "schema_version": "write_run_comparison_v2",
        "verdict": "promote_challenger",
        "reason_codes": ["equivalent_quality_at_lower_cost"],
    }
    assert set(proposal["sources"]) == {
        "champion_summary",
        "challenger_summary",
        "comparison",
    }
    for source in proposal["sources"].values():
        assert Path(source["path"]).is_absolute()
        assert source["fingerprint"].startswith("sha256:")
    review = proposal["model_plan_review"]
    assert review["source_semantics"] == (
        "configured_scene_models_recorded_by_completed_runs"
    )
    assert review["changed_roles"] == ["primary"]
    assert review["all_changed_roles_unambiguous"] is True
    assert review["roles"][0]["role"] == "primary"
    assert review["roles"][0]["changed"] is True
    assert review["roles"][0]["transition_unambiguous"] is True
    assert review["roles"][0]["champion_model_names"] == [
        "deepseek-primary"
    ]
    assert review["roles"][0]["challenger_model_names"] == [
        "mimo-challenger"
    ]
    assert proposal["safety_boundaries"] == [
        "review_only",
        "no_model_execution",
        "no_configuration_change",
        "no_promotion_authorization",
        "source_artifacts_must_remain_current",
    ]
    assert proposal["proposal_fingerprint"].startswith("sha256:")
    validate_write_model_challenger_promotion_proposal(proposal)


@pytest.mark.unit
def test_build_promotion_proposal_marks_multi_model_role_ambiguous(
    tmp_path: Path,
) -> None:
    comparison_path = _write_comparison(
        tmp_path,
        challenger=_summary(
            primary_model="unused",
            cost=0.7,
            primary_scene_models={
                "infer": "mimo-infer",
                "write": "mimo-write",
                "decision": "mimo-write",
                "overview": "mimo-write",
            },
        ),
    )

    proposal = build_write_model_challenger_promotion_proposal(
        comparison_path
    )

    review = proposal["model_plan_review"]
    assert review["all_changed_roles_unambiguous"] is False
    assert "resolve_ambiguous_model_roles" in review[
        "review_requirements"
    ]
    assert review["roles"][0]["challenger_model_names"] == [
        "mimo-infer",
        "mimo-write",
    ]
    assert review["roles"][0]["transition_unambiguous"] is False


@pytest.mark.unit
def test_promotion_proposal_requires_a_current_promotion_verdict(
    tmp_path: Path,
) -> None:
    comparison_path = _write_comparison(
        tmp_path,
        challenger=_summary(
            primary_model="mimo-challenger",
            cost=1.2,
        ),
    )

    with pytest.raises(
        WriteModelChallengerPromotionBlockedError,
        match="does not recommend promotion",
    ):
        build_write_model_challenger_promotion_proposal(
            comparison_path
        )


@pytest.mark.unit
def test_promotion_proposal_rejects_non_reproducible_comparison(
    tmp_path: Path,
) -> None:
    comparison_path = _write_comparison(tmp_path)
    comparison = json.loads(
        comparison_path.read_text(encoding="utf-8")
    )
    comparison["cost"]["cost_delta"] = -99.0
    comparison_path.write_text(
        json.dumps(comparison),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="does not match its source summaries",
    ):
        build_write_model_challenger_promotion_proposal(
            comparison_path
        )


@pytest.mark.unit
def test_promotion_proposal_validation_detects_tampering(
    tmp_path: Path,
) -> None:
    proposal = build_write_model_challenger_promotion_proposal(
        _write_comparison(tmp_path)
    )
    tampered = deepcopy(proposal)
    tampered["status"] = "approved"

    with pytest.raises(ValueError, match="status"):
        validate_write_model_challenger_promotion_proposal(tampered)

    tampered = deepcopy(proposal)
    tampered["ticker"] = "MSFT"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_write_model_challenger_promotion_proposal(tampered)


@pytest.mark.unit
def test_promotion_proposal_persistence_is_immutable(
    tmp_path: Path,
) -> None:
    proposal = build_write_model_challenger_promotion_proposal(
        _write_comparison(tmp_path)
    )
    target = tmp_path / "receipts" / "promotion.json"

    assert (
        persist_write_model_challenger_promotion_proposal(
            proposal,
            target,
        )
        == target.resolve()
    )
    original = target.read_bytes()
    assert (
        persist_write_model_challenger_promotion_proposal(
            proposal,
            target,
        )
        == target.resolve()
    )
    assert target.read_bytes() == original

    changed = deepcopy(proposal)
    changed["ticker"] = "MSFT"
    changed["proposal_fingerprint"] = proposal[
        "proposal_fingerprint"
    ]
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        persist_write_model_challenger_promotion_proposal(
            changed,
            target,
        )

    other_path = _write_comparison(
        tmp_path / "other",
        champion=_summary(
            primary_model="deepseek-primary",
            cost=1.1,
        ),
    )
    other = build_write_model_challenger_promotion_proposal(
        other_path
    )
    with pytest.raises(FileExistsError, match="different content"):
        persist_write_model_challenger_promotion_proposal(
            other,
            target,
        )


@pytest.mark.unit
def test_promotion_proposal_verification_detects_stale_sources(
    tmp_path: Path,
) -> None:
    comparison_path = _write_comparison(tmp_path)
    proposal = build_write_model_challenger_promotion_proposal(
        comparison_path
    )

    current = verify_write_model_challenger_promotion_proposal(
        proposal
    )
    assert current["status"] == "current"
    assert current["action"] == "human_review_only"
    assert current["authorizes_configuration_change"] is False
    assert current["authorizes_promotion"] is False

    champion_path = Path(
        proposal["sources"]["champion_summary"]["path"]
    )
    champion = json.loads(champion_path.read_text(encoding="utf-8"))
    champion["completed_at"] = "2026-07-24T09:00:00Z"
    champion_path.write_text(
        json.dumps(champion),
        encoding="utf-8",
    )

    stale = verify_write_model_challenger_promotion_proposal(
        proposal
    )
    assert stale["status"] == "stale_sources"
    assert stale["action"] == "stop"
    assert stale["reason_codes"] == [
        "champion_summary_fingerprint_changed"
    ]


@pytest.mark.unit
def test_promotion_proposal_loader_validates_fingerprint(
    tmp_path: Path,
) -> None:
    proposal = build_write_model_challenger_promotion_proposal(
        _write_comparison(tmp_path)
    )
    target = persist_write_model_challenger_promotion_proposal(
        proposal,
        tmp_path / "promotion.json",
    )

    resolved, loaded = load_write_model_challenger_promotion_proposal(
        target
    )
    assert resolved == target.resolve()
    assert loaded == proposal

    loaded["ticker"] = "MSFT"
    target.write_text(json.dumps(loaded), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_write_model_challenger_promotion_proposal(target)
