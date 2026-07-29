"""Write model usage ledger tests."""

from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest

from dayu.contracts.model_usage import ModelUsage
from dayu.services.internal.write_pipeline.model_usage_ledger import (
    WriteBudgetExceededError,
    WriteModelUsageLedger,
    reprice_model_usage_summary,
)
from dayu.startup.config_file_resolver import ConfigFileResolver
from dayu.startup.config_loader import ConfigLoader


def _deepseek_usage() -> ModelUsage:
    return ModelUsage.from_mapping(
        {
            "prompt_tokens": 1_000_000,
            "completion_tokens": 100_000,
            "prompt_cache_hit_tokens": 600_000,
            "prompt_cache_miss_tokens": 400_000,
        }
    )


@pytest.mark.unit
def test_builtin_deepseek_and_mimo_payg_models_use_verified_cny_pricing() -> None:
    models = ConfigLoader(ConfigFileResolver()).load_llm_models()
    expected_pricing = {
        "currency": "CNY",
        "input_per_million": 3.0,
        "cached_input_per_million": 0.025,
        "output_per_million": 6.0,
    }

    for model_name in (
        "deepseek-v4-pro",
        "deepseek-v4-pro-thinking",
        "mimo-v2.5-pro",
        "mimo-v2.5-pro-thinking",
    ):
        assert models[model_name].get("pricing") == expected_pricing

    for plan_model_name in (
        "mimo-v2.5-pro-plan",
        "mimo-v2.5-pro-thinking-plan",
        "mimo-v2.5-pro-plan-sg",
        "mimo-v2.5-pro-thinking-plan-sg",
    ):
        assert "pricing" not in models[plan_model_name]


@pytest.mark.unit
def test_ledger_aggregates_roles_scenes_replays_and_configured_cost() -> None:
    ledger = WriteModelUsageLedger()
    pricing = {
        "currency": "USD",
        "input_per_million": 1.0,
        "cached_input_per_million": 0.1,
        "output_per_million": 2.0,
    }

    ledger.record(
        scene_name="write",
        model_name="deepseek-v4-pro",
        model_role="primary",
        model_config={"pricing": pricing},
        usage=_deepseek_usage(),
        replay=False,
    )
    ledger.record(
        scene_name="audit",
        model_name="claude-sonnet",
        model_role="audit",
        model_config={"pricing": pricing},
        usage=ModelUsage.from_mapping({"input_tokens": 200, "output_tokens": 50}),
        replay=True,
    )

    summary = ledger.build_summary()

    assert summary["usage_status"] == "complete"
    assert summary["scene_call_count"] == 2
    assert summary["request_count"] == 2
    assert summary["usage_report_count"] == 2
    assert summary["unreported_request_count"] == 0
    assert summary["replay_call_count"] == 1
    assert summary["input_tokens"] == 1_000_200
    assert summary["output_tokens"] == 100_050
    assert summary["cost"] == {
        "currency": "USD",
        "status": "complete",
        "known_estimated_cost": 0.6603,
        "priced_scene_call_count": 2,
        "unpriced_scene_call_count": 0,
    }
    assert summary["by_role"]["primary"]["scene_call_count"] == 1
    assert summary["by_role"]["audit"]["scene_call_count"] == 1
    assert [entry["scene_name"] for entry in summary["by_scene"]] == ["audit", "write"]


@pytest.mark.unit
def test_ledger_reports_partial_usage_and_unavailable_cost_honestly() -> None:
    ledger = WriteModelUsageLedger()
    ledger.record(
        scene_name="write",
        model_name="deepseek-v4-pro",
        model_role="primary",
        model_config={},
        usage=_deepseek_usage(),
        replay=False,
    )
    ledger.record(
        scene_name="audit",
        model_name="claude-sonnet",
        model_role="audit",
        model_config={},
        usage=ModelUsage.from_done_usage(None),
        replay=False,
    )

    summary = ledger.build_summary()

    assert summary["usage_status"] == "partial"
    assert summary["metered_scene_call_count"] == 1
    assert summary["unmetered_scene_call_count"] == 1
    assert summary["request_count"] == 2
    assert summary["usage_report_count"] == 1
    assert summary["unreported_request_count"] == 1
    assert summary["cost"] == {
        "currency": None,
        "status": "unavailable",
        "known_estimated_cost": None,
        "priced_scene_call_count": 0,
        "unpriced_scene_call_count": 2,
    }


@pytest.mark.unit
def test_ledger_aggregates_model_fallback_routes_without_error_messages() -> None:
    ledger = WriteModelUsageLedger()

    ledger.record_fallback_switch(
        scene_name="write",
        primary_model_name="deepseek-v4-pro",
        fallback_model_name="mimo-v2.5-pro",
        trigger_error_types=("model_circuit_open",),
        fallback_call_status="completed",
    )
    for _ in range(2):
        ledger.record_fallback_switch(
            scene_name="audit",
            primary_model_name="mimo-v2.5-pro-thinking",
            fallback_model_name="deepseek-v4-pro-thinking",
            trigger_error_types=("provider_timeout", "provider_network_error"),
            fallback_call_status="error",
            fallback_error_types=("auth_error",),
        )

    summary = ledger.build_model_routing_summary()

    assert summary == {
        "fallback_switch_count": 3,
        "fallback_call_completed_count": 1,
        "fallback_call_error_count": 2,
        "routes": [
            {
                "scene_name": "audit",
                "primary_model_name": "mimo-v2.5-pro-thinking",
                "fallback_model_name": "deepseek-v4-pro-thinking",
                "trigger_error_types": [
                    "provider_network_error",
                    "provider_timeout",
                ],
                "fallback_call_status": "error",
                "fallback_error_types": ["auth_error"],
                "switch_count": 2,
            },
            {
                "scene_name": "write",
                "primary_model_name": "deepseek-v4-pro",
                "fallback_model_name": "mimo-v2.5-pro",
                "trigger_error_types": ["model_circuit_open"],
                "fallback_call_status": "completed",
                "fallback_error_types": [],
                "switch_count": 1,
            },
        ],
    }


@pytest.mark.unit
def test_ledger_marks_configured_cost_partial_when_one_request_lacks_usage() -> None:
    ledger = WriteModelUsageLedger()
    partial_usage = ModelUsage.from_mapping(
        {"prompt_tokens": 1_000_000, "completion_tokens": 0}
    ) + ModelUsage.from_done_usage(None)
    ledger.record(
        scene_name="write",
        model_name="deepseek-v4-pro",
        model_role="primary",
        model_config={
            "pricing": {
                "currency": "USD",
                "input_per_million": 1.0,
                "output_per_million": 2.0,
            }
        },
        usage=partial_usage,
        replay=False,
    )

    summary = ledger.build_summary()

    assert summary["usage_status"] == "partial"
    assert summary["request_count"] == 2
    assert summary["usage_report_count"] == 1
    assert summary["partially_metered_scene_call_count"] == 1
    assert summary["cost"] == {
        "currency": "USD",
        "status": "partial",
        "known_estimated_cost": 1.0,
        "priced_scene_call_count": 1,
        "unpriced_scene_call_count": 0,
    }


@pytest.mark.unit
def test_reprice_model_usage_summary_uses_current_catalog_without_mutating_receipt() -> None:
    ledger = WriteModelUsageLedger()
    ledger.record(
        scene_name="write",
        model_name="deepseek-v4-pro",
        model_role="primary",
        model_config={},
        usage=_deepseek_usage(),
        replay=False,
    )
    ledger.record(
        scene_name="audit",
        model_name="mimo-v2.5-pro-thinking",
        model_role="audit",
        model_config={},
        usage=ModelUsage.from_mapping({"input_tokens": 200, "output_tokens": 50}),
        replay=False,
    )
    original = ledger.build_summary()
    original_snapshot = deepcopy(original)
    pricing = {
        "currency": "CNY",
        "input_per_million": 3.0,
        "cached_input_per_million": 0.025,
        "output_per_million": 6.0,
    }

    repriced = reprice_model_usage_summary(
        original,
        {
            "deepseek-v4-pro": {"pricing": pricing},
            "mimo-v2.5-pro-thinking": {"pricing": pricing},
        },
    )

    assert original == original_snapshot
    assert original["cost"]["status"] == "unavailable"
    assert repriced["cost"] == {
        "currency": "CNY",
        "status": "complete",
        "known_estimated_cost": 1.8159,
        "priced_scene_call_count": 2,
        "unpriced_scene_call_count": 0,
    }
    assert repriced["by_role"]["primary"]["cost"]["known_estimated_cost"] == 1.815
    assert repriced["by_role"]["audit"]["cost"]["known_estimated_cost"] == 0.0009
    assert repriced["cost_repricing"] == {
        "mode": "current_model_catalog",
        "model_names": ["deepseek-v4-pro", "mimo-v2.5-pro-thinking"],
        "unpriced_model_names": [],
    }


@pytest.mark.unit
def test_reprice_model_usage_summary_reports_missing_model_pricing_as_partial() -> None:
    ledger = WriteModelUsageLedger()
    for scene_name, model_name, model_role in (
        ("write", "deepseek-v4-pro", "primary"),
        ("audit", "missing-audit-model", "audit"),
    ):
        ledger.record(
            scene_name=scene_name,
            model_name=model_name,
            model_role=model_role,
            model_config={},
            usage=_deepseek_usage(),
            replay=False,
        )

    repriced = reprice_model_usage_summary(
        ledger.build_summary(),
        {
            "deepseek-v4-pro": {
                "pricing": {
                    "currency": "CNY",
                    "input_per_million": 3.0,
                    "cached_input_per_million": 0.025,
                    "output_per_million": 6.0,
                }
            }
        },
    )

    assert repriced["cost"] == {
        "currency": "CNY",
        "status": "partial",
        "known_estimated_cost": 1.815,
        "priced_scene_call_count": 1,
        "unpriced_scene_call_count": 1,
    }
    assert repriced["cost_repricing"]["unpriced_model_names"] == [
        "missing-audit-model"
    ]


@pytest.mark.unit
def test_reprice_model_usage_summary_rejects_missing_scene_breakdown() -> None:
    with pytest.raises(ValueError, match="model_usage.by_scene must be a list"):
        reprice_model_usage_summary({"cost": {}}, {})


@pytest.mark.unit
def test_ledger_is_thread_safe() -> None:
    ledger = WriteModelUsageLedger()

    def _record(index: int) -> None:
        ledger.record(
            scene_name="write" if index % 2 == 0 else "audit",
            model_name="model",
            model_role="primary" if index % 2 == 0 else "audit",
            model_config={},
            usage=ModelUsage.from_mapping({"input_tokens": 1, "output_tokens": 1}),
            replay=False,
        )
        ledger.record_fallback_switch(
            scene_name="write",
            primary_model_name="primary-model",
            fallback_model_name="fallback-model",
            trigger_error_types=("model_circuit_open",),
            fallback_call_status="completed" if index % 2 == 0 else "error",
            fallback_error_types=() if index % 2 == 0 else ("provider_timeout",),
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(_record, range(100)))

    summary = ledger.build_summary()
    assert summary["scene_call_count"] == 100
    assert summary["request_count"] == 100
    assert summary["usage_report_count"] == 100
    assert summary["total_tokens"] == 200
    assert summary["by_role"]["primary"]["scene_call_count"] == 50
    assert summary["by_role"]["audit"]["scene_call_count"] == 50
    routing = ledger.build_model_routing_summary()
    assert routing["fallback_switch_count"] == 100
    assert routing["fallback_call_completed_count"] == 50
    assert routing["fallback_call_error_count"] == 50
    assert len(routing["routes"]) == 2


@pytest.mark.unit
def test_ledger_budget_reservation_blocks_concurrent_scene_admission() -> None:
    ledger = WriteModelUsageLedger(max_model_requests=2)

    first = ledger.reserve_scene_call(
        scene_name="write",
        model_name="primary-model",
        model_config={},
        prompt_text="first",
    )
    second = ledger.reserve_scene_call(
        scene_name="audit",
        model_name="audit-model",
        model_config={},
        prompt_text="second",
    )

    with pytest.raises(WriteBudgetExceededError, match="模型请求数预算"):
        ledger.reserve_scene_call(
            scene_name="write",
            model_name="primary-model",
            model_config={},
            prompt_text="third",
        )

    ledger.release_scene_call(first)
    ledger.release_scene_call(second)
    budget = ledger.build_budget_summary()
    assert budget["status"] == "blocked"
    assert budget["block"]["dimension"] == "model_requests"
    assert budget["limits"]["max_model_requests"] == 2


@pytest.mark.unit
def test_ledger_budget_blocks_after_actual_tokens_exceed_projection() -> None:
    ledger = WriteModelUsageLedger(max_total_tokens=20_000)
    reservation = ledger.reserve_scene_call(
        scene_name="write",
        model_name="primary-model",
        model_config={},
        prompt_text="short prompt",
    )

    with pytest.raises(WriteBudgetExceededError, match="总 Token 预算"):
        ledger.record(
            scene_name="write",
            model_name="primary-model",
            model_role="primary",
            model_config={},
            usage=ModelUsage.from_mapping(
                {"prompt_tokens": 15_000, "completion_tokens": 10_000}
            ),
            replay=False,
            reservation=reservation,
        )

    budget = ledger.build_budget_summary()
    assert budget["status"] == "blocked"
    assert budget["usage"]["total_tokens"] == 25_000
    assert budget["block"]["dimension"] == "total_tokens"
    assert budget["block"]["phase"] == "settlement"


@pytest.mark.unit
def test_ledger_cost_budget_requires_complete_matching_pricing_before_call() -> None:
    ledger = WriteModelUsageLedger(
        max_estimated_cost=1.0,
        budget_currency="CNY",
    )

    with pytest.raises(WriteBudgetExceededError, match="缺少可审计价格"):
        ledger.reserve_scene_call(
            scene_name="audit",
            model_name="unpriced-model",
            model_config={},
            prompt_text="audit",
        )

    budget = ledger.build_budget_summary()
    assert budget["status"] == "blocked"
    assert budget["block"]["dimension"] == "estimated_cost"
    assert budget["block"]["phase"] == "admission"
    assert budget["limits"]["budget_currency"] == "CNY"
