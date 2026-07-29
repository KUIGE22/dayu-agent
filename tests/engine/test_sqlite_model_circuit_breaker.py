from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier

import pytest

from dayu.engine.model_circuit_breaker import (
    ModelCircuitAdmission,
    ModelCircuitBreakerPolicy,
    ModelCircuitBreakerRegistry,
    ModelCircuitState,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _persistent_registry(
    state_path: Path,
    *,
    clock: _FakeClock,
) -> ModelCircuitBreakerRegistry:
    return ModelCircuitBreakerRegistry(
        clock=clock,
        state_path=state_path,
    )


@pytest.mark.unit
def test_sqlite_registries_share_open_state_across_instances(tmp_path: Path) -> None:
    clock = _FakeClock()
    state_path = tmp_path / "model-circuit.db"
    first = _persistent_registry(state_path, clock=clock)
    second = _persistent_registry(state_path, clock=clock)
    policy = ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=30)

    admitted = first.before_call("deepseek", policy)
    first.record_failure(admitted.permit, error_type="server_error")

    blocked = second.before_call("deepseek", policy)
    assert blocked.allowed is False
    assert blocked.state is ModelCircuitState.OPEN
    assert blocked.retry_after_seconds == pytest.approx(30.0)


@pytest.mark.unit
def test_sqlite_registries_allow_only_one_half_open_probe(tmp_path: Path) -> None:
    clock = _FakeClock()
    state_path = tmp_path / "model-circuit.db"
    first = _persistent_registry(state_path, clock=clock)
    second = _persistent_registry(state_path, clock=clock)
    policy = ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=5)
    initial = first.before_call("mimo", policy)
    first.record_failure(initial.permit, error_type="network_error")
    clock.advance(5)
    barrier = Barrier(2)

    def _admit(registry: ModelCircuitBreakerRegistry) -> ModelCircuitAdmission:
        barrier.wait(timeout=5)
        return registry.before_call("mimo", policy)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_admit, (first, second)))

    allowed = [result for result in results if result.allowed]
    blocked = [result for result in results if not result.allowed]
    assert len(allowed) == 1
    assert allowed[0].permit is not None
    assert allowed[0].permit.half_open_probe is True
    assert len(blocked) == 1
    assert blocked[0].state is ModelCircuitState.HALF_OPEN
    assert blocked[0].reason == "half_open_probe_in_flight"

    first.record_success(allowed[0].permit)
    assert second.snapshot("mimo").state is ModelCircuitState.CLOSED


@pytest.mark.unit
def test_sqlite_registry_recovers_an_abandoned_half_open_probe_after_lease(
    tmp_path: Path,
) -> None:
    clock = _FakeClock()
    state_path = tmp_path / "model-circuit.db"
    first = _persistent_registry(state_path, clock=clock)
    second = _persistent_registry(state_path, clock=clock)
    policy = ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=5)
    initial = first.before_call("mimo", policy)
    first.record_failure(initial.permit, error_type="network_error")
    clock.advance(5)

    abandoned_probe = first.before_call("mimo", policy)
    assert abandoned_probe.allowed is True
    assert abandoned_probe.permit is not None
    blocked = second.before_call("mimo", policy)
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == pytest.approx(5.0)
    clock.advance(5)

    replacement_probe = second.before_call("mimo", policy)
    assert replacement_probe.allowed is True
    assert replacement_probe.reason == "half_open_probe_recovered"
    assert replacement_probe.permit is not None
    assert (
        replacement_probe.permit.generation
        == abandoned_probe.permit.generation + 1
    )

    first.record_success(abandoned_probe.permit)
    assert second.snapshot("mimo").state is ModelCircuitState.HALF_OPEN
    second.record_success(replacement_probe.permit)
    assert first.snapshot("mimo").state is ModelCircuitState.CLOSED


@pytest.mark.unit
def test_sqlite_registry_persists_state_across_recreation(tmp_path: Path) -> None:
    clock = _FakeClock()
    state_path = tmp_path / "model-circuit.db"
    policy = ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=60)
    first = _persistent_registry(state_path, clock=clock)
    admitted = first.before_call("deepseek", policy)
    first.record_failure(admitted.permit, error_type="timeout")

    recreated = _persistent_registry(state_path, clock=clock)
    snapshot = recreated.snapshot("deepseek")

    assert snapshot.state is ModelCircuitState.OPEN
    assert snapshot.generation == 1
    assert snapshot.last_error_type == "timeout"
    assert snapshot.retry_after_seconds == pytest.approx(60.0)


@pytest.mark.unit
def test_sqlite_registry_reset_is_shared_and_scoped(tmp_path: Path) -> None:
    clock = _FakeClock()
    state_path = tmp_path / "model-circuit.db"
    first = _persistent_registry(state_path, clock=clock)
    second = _persistent_registry(state_path, clock=clock)
    policy = ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=60)
    for model_name in ("deepseek", "mimo"):
        admitted = first.before_call(model_name, policy)
        first.record_failure(admitted.permit, error_type="server_error")

    second.reset("deepseek")
    assert first.snapshot("deepseek").state is ModelCircuitState.CLOSED
    assert first.snapshot("mimo").state is ModelCircuitState.OPEN

    second.reset()
    assert first.snapshot("mimo").state is ModelCircuitState.CLOSED


@pytest.mark.unit
def test_sqlite_registry_state_is_visible_to_an_independent_process(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "model-circuit.db"
    registry = ModelCircuitBreakerRegistry(state_path=state_path)
    policy = ModelCircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=3_600)
    admitted = registry.before_call("deepseek", policy)
    registry.record_failure(admitted.permit, error_type="server_error")
    script = (
        "from dayu.engine.model_circuit_breaker import ModelCircuitBreakerRegistry; "
        f"registry = ModelCircuitBreakerRegistry(state_path={str(state_path)!r}); "
        "print(registry.snapshot('deepseek').state.value)"
    )
    environment = dict(os.environ)
    python_path = [str(_PROJECT_ROOT)]
    if environment.get("PYTHONPATH"):
        python_path.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(python_path)

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
        cwd=_PROJECT_ROOT,
    )

    assert completed.stdout.strip() == ModelCircuitState.OPEN.value
