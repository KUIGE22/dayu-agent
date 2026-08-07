"""Model usage normalization contract tests."""

from __future__ import annotations

import pytest

from dayu.contracts.model_usage import ModelUsage


@pytest.mark.unit
def test_model_usage_normalizes_deepseek_usage() -> None:
    usage = ModelUsage.from_mapping(
        {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 40,
            "completion_tokens_details": {"reasoning_tokens": 12},
        }
    )

    assert usage.to_dict() == {
        "request_count": 1,
        "usage_report_count": 1,
        "input_tokens": 120,
        "uncached_input_tokens": 40,
        "cached_input_tokens": 80,
        "cache_creation_input_tokens": 0,
        "output_tokens": 30,
        "reasoning_tokens": 12,
        "total_tokens": 150,
    }


@pytest.mark.unit
def test_model_usage_normalizes_anthropic_usage() -> None:
    usage = ModelUsage.from_mapping(
        {
            "input_tokens": 20,
            "output_tokens": 7,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 10,
        }
    )

    assert usage.to_dict() == {
        "request_count": 1,
        "usage_report_count": 1,
        "input_tokens": 80,
        "uncached_input_tokens": 20,
        "cached_input_tokens": 50,
        "cache_creation_input_tokens": 10,
        "output_tokens": 7,
        "reasoning_tokens": 0,
        "total_tokens": 87,
    }


@pytest.mark.unit
def test_model_usage_aggregates_and_ignores_invalid_counters() -> None:
    first = ModelUsage.from_mapping(
        {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}
    )
    second = ModelUsage.from_mapping(
        {"input_tokens": -9, "output_tokens": True, "cache_read_input_tokens": 4}
    )

    assert (first + second).to_dict() == {
        "request_count": 2,
        "usage_report_count": 2,
        "input_tokens": 14,
        "uncached_input_tokens": 10,
        "cached_input_tokens": 4,
        "cache_creation_input_tokens": 0,
        "output_tokens": 3,
        "reasoning_tokens": 0,
        "total_tokens": 17,
    }
    assert ModelUsage.from_mapping(None) == ModelUsage()


@pytest.mark.unit
def test_model_usage_counts_done_without_usage_as_an_unreported_request() -> None:
    usage = ModelUsage.from_done_usage(None)

    assert usage.request_count == 1
    assert usage.usage_report_count == 0
    assert usage.total_tokens == 0
