from __future__ import annotations

import pytest

from dayu.engine.model_circuit_breaker import (
    ModelCircuitBreakerPolicy,
    ModelCircuitBreakerRegistry,
    ModelCircuitState,
    is_provider_health_failure,
)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.unit
def test_model_circuit_breaker_opens_then_allows_one_half_open_probe() -> None:
    clock = _FakeClock()
    registry = ModelCircuitBreakerRegistry(clock=clock)
    policy = ModelCircuitBreakerPolicy(
        failure_threshold=2,
        cooldown_seconds=10.0,
    )

    first = registry.before_call("mimo", policy)
    assert first.allowed is True
    registry.record_failure(first.permit, error_type="network_error")
    assert registry.snapshot("mimo").consecutive_failures == 1

    second = registry.before_call("mimo", policy)
    registry.record_failure(second.permit, error_type="timeout")
    opened = registry.snapshot("mimo")
    assert opened.state is ModelCircuitState.OPEN
    assert opened.consecutive_failures == 2
    assert opened.last_error_type == "timeout"

    blocked = registry.before_call("mimo", policy)
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == pytest.approx(10.0)

    clock.advance(10.0)
    probe = registry.before_call("mimo", policy)
    assert probe.allowed is True
    assert probe.permit is not None
    assert probe.permit.half_open_probe is True
    assert registry.snapshot("mimo").state is ModelCircuitState.HALF_OPEN

    concurrent_probe = registry.before_call("mimo", policy)
    assert concurrent_probe.allowed is False
    assert concurrent_probe.reason == "half_open_probe_in_flight"

    registry.record_success(probe.permit)
    recovered = registry.snapshot("mimo")
    assert recovered.state is ModelCircuitState.CLOSED
    assert recovered.consecutive_failures == 0
    assert recovered.last_error_type is None


@pytest.mark.unit
def test_stale_success_cannot_close_newly_opened_model_circuit() -> None:
    clock = _FakeClock()
    registry = ModelCircuitBreakerRegistry(clock=clock)
    policy = ModelCircuitBreakerPolicy(
        failure_threshold=1,
        cooldown_seconds=5.0,
    )
    failing = registry.before_call("deepseek", policy)
    stale_success = registry.before_call("deepseek", policy)

    registry.record_failure(failing.permit, error_type="server_error")
    registry.record_success(stale_success.permit)

    assert registry.snapshot("deepseek").state is ModelCircuitState.OPEN

    clock.advance(5.0)
    probe = registry.before_call("deepseek", policy)
    registry.record_failure(probe.permit, error_type="rate_limit_exceeded")
    reopened = registry.snapshot("deepseek")
    assert reopened.state is ModelCircuitState.OPEN
    assert reopened.generation == 2
    assert reopened.retry_after_seconds == pytest.approx(5.0)


@pytest.mark.unit
def test_abandoned_half_open_probe_reopens_model_circuit() -> None:
    clock = _FakeClock()
    registry = ModelCircuitBreakerRegistry(clock=clock)
    policy = ModelCircuitBreakerPolicy(
        failure_threshold=1,
        cooldown_seconds=3.0,
    )
    initial = registry.before_call("mimo", policy)
    registry.record_failure(initial.permit, error_type="network_error")
    clock.advance(3.0)

    probe = registry.before_call("mimo", policy)
    registry.record_abandoned(probe.permit)

    snapshot = registry.snapshot("mimo")
    assert snapshot.state is ModelCircuitState.OPEN
    assert snapshot.generation == 2
    assert snapshot.retry_after_seconds == pytest.approx(3.0)


@pytest.mark.unit
@pytest.mark.parametrize(
    "error_type",
    [
        "timeout",
        "network_error",
        "server_error",
        "rate_limit_exceeded",
        "unknown_http_status",
        "unknown_error",
        "response_error",
    ],
)
def test_provider_health_failures_are_classified(error_type: str) -> None:
    assert is_provider_health_failure(error_type) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "error_type",
    [
        "auth_error",
        "insufficient_quota",
        "invalid_request",
        "context_overflow",
        "content_blocked",
        "tool_call_incomplete",
        "tool_executor_missing",
        "model_circuit_open",
        "",
    ],
)
def test_non_provider_health_failures_do_not_trip_circuit(error_type: str) -> None:
    assert is_provider_health_failure(error_type) is False
