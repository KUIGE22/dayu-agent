from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from dayu.engine.async_openai_runner import AsyncOpenAIRunner
from dayu.engine.events import EventType, StreamEvent, done_event, error_event
from dayu.engine.model_circuit_breaker import (
    ModelCircuitBreakerPolicy,
    ModelCircuitBreakerRegistry,
    ModelCircuitState,
)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _runner(
    *,
    registry: ModelCircuitBreakerRegistry,
    policy: ModelCircuitBreakerPolicy,
) -> AsyncOpenAIRunner:
    return AsyncOpenAIRunner(
        endpoint_url="https://provider.example/v1/chat/completions",
        model="provider-model",
        headers={},
        name="catalog-model",
        model_circuit_breaker_registry=registry,
        model_circuit_breaker_policy=policy,
        model_circuit_breaker_resource_id="catalog-model",
    )


async def _collect(runner: AsyncOpenAIRunner) -> list[StreamEvent]:
    return [event async for event in runner.call([], stream=False)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_blocks_provider_call_after_circuit_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelCircuitBreakerRegistry()
    runner = _runner(
        registry=registry,
        policy=ModelCircuitBreakerPolicy(failure_threshold=2, cooldown_seconds=60),
    )
    provider_calls = 0

    async def _provider_failure(*_args: object, **_kwargs: object) -> AsyncIterator[StreamEvent]:
        nonlocal provider_calls
        provider_calls += 1
        yield error_event("down", error_type="network_error")

    monkeypatch.setattr(runner, "_call_without_circuit_breaker", _provider_failure)

    await _collect(runner)
    await _collect(runner)
    blocked = await _collect(runner)

    assert provider_calls == 2
    assert len(blocked) == 1
    assert blocked[0].type is EventType.ERROR
    assert blocked[0].metadata["error_type"] == "model_circuit_open"
    assert blocked[0].metadata["circuit_state"] == "open"
    assert registry.snapshot("catalog-model").state is ModelCircuitState.OPEN


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_successful_half_open_probe_closes_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    registry = ModelCircuitBreakerRegistry(clock=clock)
    runner = _runner(
        registry=registry,
        policy=ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=5),
    )
    outcomes = ["failure", "success", "success"]
    provider_calls = 0

    async def _provider(*_args: object, **_kwargs: object) -> AsyncIterator[StreamEvent]:
        nonlocal provider_calls
        provider_calls += 1
        outcome = outcomes.pop(0)
        if outcome == "failure":
            yield error_event("busy", error_type="server_error")
        else:
            yield done_event({"finish_reason": "stop"})

    monkeypatch.setattr(runner, "_call_without_circuit_breaker", _provider)

    await _collect(runner)
    assert registry.snapshot("catalog-model").state is ModelCircuitState.OPEN
    clock.advance(5)
    probe = await _collect(runner)
    normal = await _collect(runner)

    assert probe[-1].type is EventType.DONE
    assert normal[-1].type is EventType.DONE
    assert provider_calls == 3
    assert registry.snapshot("catalog-model").state is ModelCircuitState.CLOSED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_does_not_trip_circuit_for_non_health_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelCircuitBreakerRegistry()
    runner = _runner(
        registry=registry,
        policy=ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=30),
    )
    provider_calls = 0

    async def _auth_failure(*_args: object, **_kwargs: object) -> AsyncIterator[StreamEvent]:
        nonlocal provider_calls
        provider_calls += 1
        yield error_event("bad key", error_type="auth_error")

    monkeypatch.setattr(runner, "_call_without_circuit_breaker", _auth_failure)

    await _collect(runner)
    await _collect(runner)

    assert provider_calls == 2
    assert registry.snapshot("catalog-model").state is ModelCircuitState.CLOSED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_non_health_error_breaks_provider_failure_streak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelCircuitBreakerRegistry()
    runner = _runner(
        registry=registry,
        policy=ModelCircuitBreakerPolicy(failure_threshold=2, cooldown_seconds=30),
    )
    outcomes = ["network_error", "auth_error", "network_error"]

    async def _provider(*_args: object, **_kwargs: object) -> AsyncIterator[StreamEvent]:
        yield error_event("failed", error_type=outcomes.pop(0))

    monkeypatch.setattr(runner, "_call_without_circuit_breaker", _provider)

    await _collect(runner)
    await _collect(runner)
    await _collect(runner)

    snapshot = registry.snapshot("catalog-model")
    assert snapshot.state is ModelCircuitState.CLOSED
    assert snapshot.consecutive_failures == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_non_health_half_open_probe_closes_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    registry = ModelCircuitBreakerRegistry(clock=clock)
    runner = _runner(
        registry=registry,
        policy=ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=5),
    )
    outcomes = ["network_error", "auth_error"]

    async def _provider(*_args: object, **_kwargs: object) -> AsyncIterator[StreamEvent]:
        yield error_event("failed", error_type=outcomes.pop(0))

    monkeypatch.setattr(runner, "_call_without_circuit_breaker", _provider)

    await _collect(runner)
    clock.advance(5)
    await _collect(runner)

    snapshot = registry.snapshot("catalog-model")
    assert snapshot.state is ModelCircuitState.CLOSED
    assert snapshot.consecutive_failures == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_cancellation_does_not_count_as_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelCircuitBreakerRegistry()
    runner = _runner(
        registry=registry,
        policy=ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=30),
    )

    async def _cancelled(*_args: object, **_kwargs: object) -> AsyncIterator[StreamEvent]:
        raise asyncio.CancelledError
        yield done_event()  # pragma: no cover

    monkeypatch.setattr(runner, "_call_without_circuit_breaker", _cancelled)

    with pytest.raises(asyncio.CancelledError):
        await _collect(runner)

    snapshot = registry.snapshot("catalog-model")
    assert snapshot.state is ModelCircuitState.CLOSED
    assert snapshot.consecutive_failures == 0
