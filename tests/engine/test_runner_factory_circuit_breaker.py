from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.agent_execution import AgentCreateArgs
from dayu.contracts.model_config import (
    AnthropicRunnerParams,
    OpenAICompatibleRunnerParams,
    RunnerType,
)
from dayu.engine.async_anthropic_runner import AsyncAnthropicRunner
from dayu.engine.async_openai_runner import AsyncOpenAIRunner
from dayu.engine.model_circuit_breaker import (
    GLOBAL_MODEL_CIRCUIT_BREAKERS,
    ModelCircuitState,
)
from dayu.engine.runner_factory import create_runner


@pytest.mark.unit
@pytest.mark.parametrize(
    ("runner_type", "runner_params", "expected_type"),
    [
        (
            RunnerType.OPENAI_COMPATIBLE,
            cast(
                OpenAICompatibleRunnerParams,
                {
                    "endpoint_url": "https://openai-compatible.example/v1/chat/completions",
                    "model": "provider-model",
                    "headers": {},
                },
            ),
            AsyncOpenAIRunner,
        ),
        (
            RunnerType.ANTHROPIC,
            cast(
                AnthropicRunnerParams,
                {
                    "endpoint_url": "https://anthropic.example/v1/messages",
                    "model": "provider-model",
                    "headers": {},
                },
            ),
            AsyncAnthropicRunner,
        ),
    ],
)
def test_runner_factory_wires_shared_model_circuit_breaker(
    runner_type: RunnerType,
    runner_params: AnthropicRunnerParams | OpenAICompatibleRunnerParams,
    expected_type: type[AsyncOpenAIRunner],
) -> None:
    runner = create_runner(
        AgentCreateArgs(
            runner_type=runner_type,
            model_name="catalog-model",
            runner_params=runner_params,
            runner_running_config={
                "model_circuit_breaker_enabled": True,
                "model_circuit_breaker_failure_threshold": 4,
                "model_circuit_breaker_cooldown_seconds": 25.0,
            },
        )
    )

    assert isinstance(runner, expected_type)
    assert runner.model_circuit_breaker_registry is GLOBAL_MODEL_CIRCUIT_BREAKERS
    assert runner.model_circuit_breaker_policy is not None
    assert runner.model_circuit_breaker_policy.failure_threshold == 4
    assert runner.model_circuit_breaker_policy.cooldown_seconds == pytest.approx(25.0)
    assert runner.model_circuit_breaker_resource_id == "catalog-model"


@pytest.mark.unit
def test_runner_factory_can_disable_model_circuit_breaker() -> None:
    runner = create_runner(
        AgentCreateArgs(
            runner_type=RunnerType.OPENAI_COMPATIBLE,
            model_name="catalog-model",
            runner_params=cast(
                OpenAICompatibleRunnerParams,
                {
                    "endpoint_url": "https://provider.example/v1/chat/completions",
                    "model": "provider-model",
                    "headers": {},
                },
            ),
            runner_running_config={
                "model_circuit_breaker_enabled": False,
            },
        )
    )

    assert isinstance(runner, AsyncOpenAIRunner)
    assert runner.model_circuit_breaker_registry is None
    assert runner.model_circuit_breaker_policy is None


@pytest.mark.unit
def test_runner_factory_uses_configured_sqlite_circuit_state(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "shared-model-circuit.db"

    def _create() -> AsyncOpenAIRunner:
        runner = create_runner(
            AgentCreateArgs(
                runner_type=RunnerType.OPENAI_COMPATIBLE,
                model_name="catalog-model",
                runner_params=cast(
                    OpenAICompatibleRunnerParams,
                    {
                        "endpoint_url": "https://provider.example/v1/chat/completions",
                        "model": "provider-model",
                        "headers": {},
                    },
                ),
                runner_running_config={
                    "model_circuit_breaker_enabled": True,
                    "model_circuit_breaker_failure_threshold": 1,
                    "model_circuit_breaker_cooldown_seconds": 60.0,
                    "model_circuit_breaker_state_path": str(state_path),
                },
            )
        )
        assert isinstance(runner, AsyncOpenAIRunner)
        return runner

    first = _create()
    second = _create()
    first_registry = first.model_circuit_breaker_registry
    second_registry = second.model_circuit_breaker_registry
    assert first_registry is not None
    assert second_registry is not None
    assert second_registry is first_registry
    assert first_registry is not GLOBAL_MODEL_CIRCUIT_BREAKERS
    assert first_registry.state_path == state_path.resolve()
    assert first.model_circuit_breaker_policy is not None
    admitted = first_registry.before_call(
        first.model_circuit_breaker_resource_id,
        first.model_circuit_breaker_policy,
    )
    first_registry.record_failure(admitted.permit, error_type="server_error")

    assert second.model_circuit_breaker_policy is not None
    blocked = second_registry.before_call(
        second.model_circuit_breaker_resource_id,
        second.model_circuit_breaker_policy,
    )
    assert blocked.allowed is False
    assert blocked.state is ModelCircuitState.OPEN
