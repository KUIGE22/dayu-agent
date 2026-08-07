"""Anthropic model catalog to Runner wiring tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from dayu.contracts.agent_execution import AgentCreateArgs
from dayu.contracts.model_config import AnthropicRunnerParams, RunnerType
from dayu.engine.async_anthropic_runner import AsyncAnthropicRunner
from dayu.execution.options import (
    ConversationMemorySettings,
    ResolvedExecutionOptions,
    TraceSettings,
)
from dayu.execution.runtime_config import AgentRuntimeConfig, OpenAIRunnerRuntimeConfig
from dayu.host.agent_builder import build_agent_create_args, build_async_runner
from dayu.startup.config_file_resolver import (
    ConfigFileResolver,
    resolve_package_config_path,
)
from dayu.startup.config_loader import ConfigLoader


def _resolved_options() -> ResolvedExecutionOptions:
    return ResolvedExecutionOptions(
        model_name="claude-sonnet-4-6",
        runner_running_config=OpenAIRunnerRuntimeConfig(),
        agent_running_config=AgentRuntimeConfig(),
        trace_settings=TraceSettings(
            enabled=False,
            output_dir=Path("/tmp/trace"),
        ),
        temperature=0.2,
        conversation_memory_settings=ConversationMemorySettings(),
    )


@pytest.mark.unit
def test_package_claude_config_uses_native_messages_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    loader = ConfigLoader(ConfigFileResolver(resolve_package_config_path()))

    config = loader.load_llm_model("claude-sonnet-4-6")

    assert config.get("runner_type") == RunnerType.ANTHROPIC
    assert config.get("endpoint_url") == "https://api.anthropic.com/v1/messages"
    assert config.get("base_url_env") == "ANTHROPIC_BASE_URL"
    assert config.get("supports_stream") is True
    assert config.get("headers") == {
        "x-api-key": "test-key",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


@pytest.mark.unit
def test_build_agent_create_args_maps_anthropic_config() -> None:
    created = build_agent_create_args(
        resolved_execution_options=_resolved_options(),
        model_config=cast(
            Any,
            {
                "runner_type": "anthropic",
                "endpoint_url": "https://api.anthropic.com/v1/messages",
                "base_url_env": "CUSTOM_ANTHROPIC_BASE_URL",
                "model": "claude-sonnet-4-6",
                "headers": {"x-api-key": "secret"},
                "name": "claude-audit",
                "extra_payloads": {"max_tokens": 2048},
                "supports_tool_calling": True,
            },
        ),
    )

    assert created.runner_type == RunnerType.ANTHROPIC.value
    params = cast(dict[str, object], created.runner_params)
    assert params["base_url_env"] == "CUSTOM_ANTHROPIC_BASE_URL"
    assert params["default_extra_payloads"] == {"max_tokens": 2048}
    assert params["temperature"] == 0.2


@pytest.mark.unit
def test_runner_factory_uses_anthropic_base_url_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example/v1")
    runner = build_async_runner(
        AgentCreateArgs(
            runner_type=RunnerType.ANTHROPIC,
            model_name="claude-sonnet-4-6",
            temperature=0.2,
            runner_params=cast(
                AnthropicRunnerParams,
                {
                    "endpoint_url": "https://api.anthropic.com/v1/messages",
                    "base_url_env": "ANTHROPIC_BASE_URL",
                    "model": "claude-sonnet-4-6",
                    "headers": {"x-api-key": "secret"},
                    "default_extra_payloads": {"max_tokens": 2048},
                },
            ),
        )
    )

    assert isinstance(runner, AsyncAnthropicRunner)
    assert runner.endpoint_url == "https://proxy.example/v1/messages"
    assert runner.supports_stream is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("runner_params", "expected_message"),
    [
        ({"model": "demo", "headers": {}}, "endpoint_url"),
        ({"endpoint_url": "https://example.com/v1/messages", "headers": {}}, "model"),
        (
            {
                "endpoint_url": "https://example.com/v1/messages",
                "model": "demo",
            },
            "headers",
        ),
    ],
)
def test_runner_factory_validates_anthropic_required_params(
    runner_params: AnthropicRunnerParams,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        build_async_runner(
            AgentCreateArgs(
                runner_type=RunnerType.ANTHROPIC,
                model_name="demo",
                runner_params=runner_params,
            )
        )
