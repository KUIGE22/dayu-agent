"""Historical write-model health trend tests."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.services.write_model_health import (
    build_write_model_health_trend,
    format_write_model_health_report,
)


def _write_summary(
    root: Path,
    *,
    name: str,
    completed_at: str | None,
    primary_model: str = "deepseek-primary",
    fallback_model: str = "mimo-fallback",
    primary_call_count: int = 10,
    fallback_completed_count: int = 0,
    fallback_error_count: int = 0,
    gate_status: str = "passed",
    estimated_cost: float = 10.0,
    currency: str = "CNY",
    include_routing: bool = True,
    corrupt_routing: bool = False,
    scene_name: str = "write",
    model_role: str = "primary",
) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    fallback_switch_count = fallback_completed_count + fallback_error_count
    scene_call_count = primary_call_count + fallback_switch_count
    by_scene = [
        {
            "scene_name": scene_name,
            "model_name": primary_model,
            "model_role": model_role,
            "scene_call_count": primary_call_count,
        }
    ]
    if fallback_switch_count:
        by_scene.append(
            {
                "scene_name": scene_name,
                "model_name": fallback_model,
                "model_role": model_role,
                "scene_call_count": fallback_switch_count,
            }
        )
    payload: dict[str, object] = {
        "schema_version": "write_run_summary_v3",
        "ticker": name,
        "gate_status": gate_status,
        "model_usage": {
            "scene_call_count": scene_call_count,
            "request_count": scene_call_count,
            "total_tokens": scene_call_count * 100,
            "by_scene": by_scene,
            "cost": {
                "status": "complete",
                "currency": currency,
                "known_estimated_cost": estimated_cost,
            },
        },
    }
    if completed_at is not None:
        payload["completed_at"] = completed_at
    if include_routing:
        routes: list[dict[str, object]] = []
        if fallback_completed_count:
            routes.append(
                {
                    "scene_name": scene_name,
                    "primary_model_name": primary_model,
                    "fallback_model_name": fallback_model,
                    "trigger_error_types": ["network_error"],
                    "fallback_call_status": "completed",
                    "fallback_error_types": [],
                    "switch_count": fallback_completed_count,
                }
            )
        if fallback_error_count:
            routes.append(
                {
                    "scene_name": scene_name,
                    "primary_model_name": primary_model,
                    "fallback_model_name": fallback_model,
                    "trigger_error_types": ["server_error"],
                    "fallback_call_status": "error",
                    "fallback_error_types": ["timeout_error"],
                    "switch_count": fallback_error_count,
                }
            )
        payload["model_routing"] = {
            "fallback_switch_count": (
                fallback_switch_count + 1
                if corrupt_routing
                else fallback_switch_count
            ),
            "fallback_call_completed_count": fallback_completed_count,
            "fallback_call_error_count": fallback_error_count,
            "routes": routes,
        }
    summary_path = run_dir / "run_summary.json"
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary_path


@pytest.mark.unit
def test_build_write_model_health_trend_detects_route_and_cost_regression(
    tmp_path: Path,
) -> None:
    for index in range(3):
        _write_summary(
            tmp_path,
            name=f"baseline-{index}",
            completed_at=f"2026-07-{index + 1:02d}T00:00:00Z",
        )
    for index in range(3):
        _write_summary(
            tmp_path,
            name=f"recent-{index}",
            completed_at=f"2026-07-{index + 11:02d}T00:00:00Z",
            fallback_completed_count=2,
            estimated_cost=18.0,
        )

    trend = build_write_model_health_trend(
        tmp_path,
        max_runs=6,
        recent_run_count=3,
    )

    assert trend["schema_version"] == "write_model_health_trend_v1"
    assert trend["window"] == {
        "discovered_summary_count": 6,
        "selected_run_count": 6,
        "max_runs": 6,
        "recent_run_count": 3,
        "baseline_run_count": 3,
        "summary_timestamp_count": 6,
        "file_mtime_timestamp_count": 0,
        "invalid_summary_count": 0,
    }
    source_integrity = trend["source_integrity"]
    assert {
        key: source_integrity[key]
        for key in (
            "routing_complete_run_count",
            "routing_missing_run_count",
            "routing_invalid_run_count",
        )
    } == {
        "routing_complete_run_count": 6,
        "routing_missing_run_count": 0,
        "routing_invalid_run_count": 0,
    }
    assert str(source_integrity["selected_history_fingerprint"]).startswith(
        "sha256:"
    )
    assert trend["overall"]["status"] == "degraded"
    assert trend["overall"]["trend"] == "regressed"
    assert trend["overall"]["recent"]["fallback_switch_share"] == pytest.approx(
        1 / 6
    )
    assert trend["overall"]["baseline"]["fallback_switch_share"] == 0.0
    assert trend["overall"]["deltas"]["fallback_switch_share"] == pytest.approx(
        1 / 6
    )
    assert trend["overall"]["deltas"]["cost_per_scene_ratio"] == pytest.approx(
        0.5
    )

    models = {item["model_name"]: item for item in trend["models"]}
    assert models["deepseek-primary"]["recent"]["observed_scene_call_count"] == 30
    assert models["deepseek-primary"]["recent"]["primary_fallback_switch_count"] == 6
    assert models["deepseek-primary"]["recent"]["primary_switch_share"] == 0.2
    assert models["deepseek-primary"]["status"] == "degraded"
    assert models["mimo-fallback"]["recent"]["fallback_call_count"] == 6
    assert models["mimo-fallback"]["recent"]["fallback_completion_rate"] == 1.0
    assert {
        item["reason_code"] for item in trend["recommendations"]
    } >= {
        "fallback_switch_share_increased",
        "cost_per_scene_increased",
        "primary_model_fallback_rate_high",
    }
    assert {
        item["action"] for item in trend["recommendations"]
    } == {"manual_review"}
    assert trend["route_pairs"]["recent"] == [
        {
            "model_role": "primary",
            "primary_model_name": "deepseek-primary",
            "fallback_model_name": "mimo-fallback",
            "run_count": 3,
            "scene_names": ["write"],
            "trigger_error_types": ["network_error"],
            "primary_scene_call_count": 30,
            "fallback_observed_scene_call_count": 6,
            "fallback_switch_count": 6,
            "fallback_completed_count": 6,
            "fallback_error_count": 0,
            "primary_switch_share": 0.2,
            "fallback_completion_rate": 1.0,
            "fallback_error_rate": 0.0,
        }
    ]
    assert trend["challenger_proposal"]["status"] == "ready"
    assert trend["challenger_proposal"]["action"] == "run_isolated_challenger"
    assert trend["challenger_proposal"]["challenger_cli_args"] == [
        "--challenger-model-name",
        "mimo-fallback",
    ]
    assert (
        trend["challenger_proposal"]["evidence_window"][
            "history_fingerprint"
        ]
        == source_integrity["selected_history_fingerprint"]
    )


@pytest.mark.unit
def test_build_write_model_health_trend_preserves_legacy_and_flags_corruption(
    tmp_path: Path,
) -> None:
    legacy_path = _write_summary(
        tmp_path,
        name="legacy",
        completed_at=None,
        include_routing=False,
    )
    legacy_timestamp = datetime(2026, 7, 10, tzinfo=UTC).timestamp()
    os.utime(legacy_path, (legacy_timestamp, legacy_timestamp))
    _write_summary(
        tmp_path,
        name="corrupt-routing",
        completed_at="2026-07-11T00:00:00Z",
        fallback_completed_count=1,
        corrupt_routing=True,
    )
    invalid_time_path = _write_summary(
        tmp_path,
        name="invalid-time",
        completed_at="not-a-time",
    )
    invalid_json_path = tmp_path / "invalid-json" / "run_summary.json"
    invalid_json_path.parent.mkdir()
    invalid_json_path.write_text("{bad json", encoding="utf-8")

    trend = build_write_model_health_trend(
        tmp_path,
        max_runs=10,
        recent_run_count=1,
    )

    assert trend["window"]["discovered_summary_count"] == 4
    assert trend["window"]["selected_run_count"] == 2
    assert trend["window"]["summary_timestamp_count"] == 1
    assert trend["window"]["file_mtime_timestamp_count"] == 1
    assert trend["window"]["invalid_summary_count"] == 2
    source_integrity = trend["source_integrity"]
    assert {
        key: source_integrity[key]
        for key in (
            "routing_complete_run_count",
            "routing_missing_run_count",
            "routing_invalid_run_count",
        )
    } == {
        "routing_complete_run_count": 0,
        "routing_missing_run_count": 1,
        "routing_invalid_run_count": 1,
    }
    assert str(source_integrity["selected_history_fingerprint"]).startswith(
        "sha256:"
    )
    assert trend["overall"]["status"] == "watch"
    assert trend["overall"]["trend"] == "insufficient_data"
    assert any(
        item["reason_code"] == "invalid_routing_receipt"
        for item in trend["recommendations"]
    )
    assert any("invalid-time" in warning for warning in trend["warnings"])
    assert any("invalid-json" in warning for warning in trend["warnings"])
    assert all("not-a-time" not in warning for warning in trend["warnings"])
    assert invalid_time_path.is_file()


@pytest.mark.unit
def test_build_write_model_health_trend_keeps_mixed_currency_costs_incomparable(
    tmp_path: Path,
) -> None:
    _write_summary(
        tmp_path,
        name="baseline",
        completed_at="2026-07-01T00:00:00Z",
        currency="USD",
    )
    _write_summary(
        tmp_path,
        name="recent",
        completed_at="2026-07-11T00:00:00Z",
        currency="CNY",
    )

    trend = build_write_model_health_trend(
        tmp_path,
        max_runs=2,
        recent_run_count=1,
    )

    assert trend["overall"]["recent"]["cost"]["status"] == "complete"
    assert trend["overall"]["baseline"]["cost"]["status"] == "complete"
    assert trend["overall"]["deltas"]["cost_comparable"] is False
    assert trend["overall"]["deltas"]["cost_per_scene_ratio"] is None
    assert all(
        item["reason_code"] != "cost_per_scene_increased"
        for item in trend["recommendations"]
    )


@pytest.mark.unit
def test_current_catalog_repricing_preserves_history_and_proposal_fingerprints(
    tmp_path: Path,
) -> None:
    """Current prices may change cost views, never source or proposal identity."""

    for index in range(3):
        _write_summary(
            tmp_path,
            name=f"run-{index}",
            completed_at=f"2026-07-{index + 11:02d}T00:00:00Z",
            fallback_completed_count=1,
        )

    persisted_basis = build_write_model_health_trend(
        tmp_path,
        max_runs=3,
        recent_run_count=3,
    )
    current_catalog_basis = build_write_model_health_trend(
        tmp_path,
        max_runs=3,
        recent_run_count=3,
        model_catalog={
            "deepseek-primary": {
                "pricing": {
                    "currency": "CNY",
                    "input_per_million": 99.0,
                    "output_per_million": 199.0,
                }
            },
            "mimo-fallback": {
                "pricing": {
                    "currency": "CNY",
                    "input_per_million": 88.0,
                    "output_per_million": 188.0,
                }
            },
        },
    )

    assert (
        persisted_basis["source_integrity"]["selected_history_fingerprint"]
        == current_catalog_basis["source_integrity"][
            "selected_history_fingerprint"
        ]
    )
    assert (
        persisted_basis["challenger_proposal"]["proposal_fingerprint"]
        == current_catalog_basis["challenger_proposal"][
            "proposal_fingerprint"
        ]
    )


@pytest.mark.unit
def test_format_write_model_health_report_is_compact_and_advisory(
    tmp_path: Path,
) -> None:
    _write_summary(
        tmp_path,
        name="run",
        completed_at="2026-07-11T00:00:00Z",
    )
    trend = build_write_model_health_trend(
        tmp_path,
        max_runs=1,
        recent_run_count=1,
    )

    output = "\n".join(format_write_model_health_report(trend))

    assert "模型健康趋势（只读）" in output
    assert "健康状态   : insufficient_data" in output
    assert "趋势判断   : insufficient_data" in output
    assert "不会自动修改主备模型配置" in output
    assert str(tmp_path.resolve()) not in output


@pytest.mark.unit
def test_build_write_model_health_trend_proposes_audit_challenger_argument(
    tmp_path: Path,
) -> None:
    for index in range(3):
        _write_summary(
            tmp_path,
            name=f"audit-{index}",
            completed_at=f"2026-07-{index + 11:02d}T00:00:00Z",
            primary_model="deepseek-audit",
            fallback_model="mimo-audit",
            primary_call_count=5,
            fallback_completed_count=1,
            scene_name="audit",
            model_role="audit",
        )

    trend = build_write_model_health_trend(
        tmp_path,
        max_runs=3,
        recent_run_count=3,
    )

    proposal = trend["challenger_proposal"]
    assert proposal["status"] == "ready"
    assert proposal["challenger_cli_args"] == [
        "--challenger-audit-model-name",
        "mimo-audit",
    ]
    assert proposal["role_overrides"][0]["model_role"] == "audit"
