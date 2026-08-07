"""Engine Runner 工厂。

Host 通过本模块的 ``create_runner`` 获取 ``AsyncRunner`` 实例，
无需直接依赖具体 Runner 实现类。
"""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import cast

from dayu.contracts.agent_execution import AgentCreateArgs
from dayu.contracts.model_config import (
    AnthropicRunnerParams,
    OpenAICompatibleRunnerParams,
    RunnerType,
    ensure_runner_type_enabled,
)
from dayu.engine.async_anthropic_runner import (
    AsyncAnthropicRunner,
    resolve_anthropic_endpoint_url,
)
from dayu.engine.async_openai_runner import AsyncOpenAIRunner, AsyncOpenAIRunnerRunningConfig
from dayu.contracts.cancellation import CancellationToken
from dayu.engine.model_circuit_breaker import (
    GLOBAL_MODEL_CIRCUIT_BREAKERS,
    ModelCircuitBreakerPolicy,
    ModelCircuitBreakerRegistry,
)
from dayu.engine.protocols import AsyncRunner


def create_runner(
    agent_create_args: AgentCreateArgs,
    *,
    cancellation_token: CancellationToken | None = None,
) -> AsyncRunner:
    """根据 ``AgentCreateArgs`` 构造底层 Runner。

    Args:
        agent_create_args: 已解析完成的 Agent 创建参数。
        cancellation_token: 可选取消令牌。

    Returns:
        底层异步 Runner。

    Raises:
        ValueError: ``runner_type`` 不支持时抛出。
    """

    runner_type = ensure_runner_type_enabled(agent_create_args.runner_type)
    running_config = _build_openai_runner_running_config(agent_create_args)
    circuit_registry, circuit_policy = _build_model_circuit_breaker(running_config)
    circuit_resource_id = str(agent_create_args.model_name or "").strip()
    if runner_type == RunnerType.OPENAI_COMPATIBLE:
        runner_params = cast(OpenAICompatibleRunnerParams, agent_create_args.runner_params)
        endpoint_url = runner_params.get("endpoint_url")
        model = runner_params.get("model")
        headers = runner_params.get("headers")
        if endpoint_url is None:
            raise ValueError("openai_compatible runner_params 缺少 endpoint_url")
        if model is None:
            raise ValueError("openai_compatible runner_params 缺少 model")
        if headers is None:
            raise ValueError("openai_compatible runner_params 缺少 headers")
        temperature = runner_params.get("temperature")
        return AsyncOpenAIRunner(
            endpoint_url=str(endpoint_url),
            model=str(model),
            headers=dict(headers),
            name=runner_params.get("name"),
            temperature=float(agent_create_args.temperature or 0.0) if temperature is None else float(temperature),
            default_extra_payloads=dict(runner_params.get("default_extra_payloads") or {}),
            timeout=int(runner_params.get("timeout", 3600)),
            max_retries=int(runner_params.get("max_retries", 3)),
            supports_stream=bool(runner_params.get("supports_stream", True)),
            supports_tool_calling=bool(runner_params.get("supports_tool_calling", True)),
            supports_stream_usage=bool(runner_params.get("supports_stream_usage", False)),
            running_config=running_config,
            cancellation_token=cancellation_token,
            model_circuit_breaker_registry=circuit_registry,
            model_circuit_breaker_policy=circuit_policy,
            model_circuit_breaker_resource_id=circuit_resource_id or str(model),
        )
    if runner_type == RunnerType.ANTHROPIC:
        runner_params = cast(AnthropicRunnerParams, agent_create_args.runner_params)
        configured_endpoint_url = runner_params.get("endpoint_url")
        model = runner_params.get("model")
        headers = runner_params.get("headers")
        if configured_endpoint_url is None:
            raise ValueError("anthropic runner_params 缺少 endpoint_url")
        if model is None:
            raise ValueError("anthropic runner_params 缺少 model")
        if headers is None:
            raise ValueError("anthropic runner_params 缺少 headers")
        base_url_env = str(
            runner_params.get("base_url_env") or "ANTHROPIC_BASE_URL"
        ).strip()
        endpoint_url = resolve_anthropic_endpoint_url(
            str(configured_endpoint_url),
            base_url=os.environ.get(base_url_env) if base_url_env else None,
        )
        temperature = runner_params.get("temperature")
        return AsyncAnthropicRunner(
            endpoint_url=endpoint_url,
            model=str(model),
            headers=dict(headers),
            name=runner_params.get("name"),
            temperature=float(agent_create_args.temperature or 0.0)
            if temperature is None
            else float(temperature),
            default_extra_payloads=dict(
                runner_params.get("default_extra_payloads") or {}
            ),
            timeout=int(runner_params.get("timeout", 3600)),
            max_retries=int(runner_params.get("max_retries", 3)),
            supports_stream=bool(runner_params.get("supports_stream", True)),
            supports_tool_calling=bool(
                runner_params.get("supports_tool_calling", True)
            ),
            supports_stream_usage=False,
            running_config=running_config,
            cancellation_token=cancellation_token,
            model_circuit_breaker_registry=circuit_registry,
            model_circuit_breaker_policy=circuit_policy,
            model_circuit_breaker_resource_id=circuit_resource_id or str(model),
        )
    raise ValueError(f"不支持的 runner_type: {runner_type}")


def _build_openai_runner_running_config(
    agent_create_args: AgentCreateArgs,
) -> AsyncOpenAIRunnerRunningConfig:
    """从快照构造 OpenAI Runner 运行时配置。"""

    snapshot = agent_create_args.runner_running_config
    raw_circuit_state_path = snapshot.get("model_circuit_breaker_state_path")
    return AsyncOpenAIRunnerRunningConfig(
        debug_sse=snapshot.get("debug_sse", False),
        debug_tool_delta=snapshot.get("debug_tool_delta", False),
        debug_sse_sample_rate=snapshot.get("debug_sse_sample_rate", 1.0),
        debug_sse_throttle_sec=snapshot.get("debug_sse_throttle_sec", 0.0),
        tool_timeout_seconds=snapshot.get("tool_timeout_seconds"),
        stream_idle_timeout=snapshot.get("stream_idle_timeout"),
        stream_idle_heartbeat_sec=snapshot.get("stream_idle_heartbeat_sec"),
        model_circuit_breaker_enabled=bool(
            snapshot.get("model_circuit_breaker_enabled", True)
        ),
        model_circuit_breaker_failure_threshold=int(
            snapshot.get("model_circuit_breaker_failure_threshold", 3)
        ),
        model_circuit_breaker_cooldown_seconds=float(
            snapshot.get("model_circuit_breaker_cooldown_seconds", 60.0)
        ),
        model_circuit_breaker_state_path=(
            str(raw_circuit_state_path).strip() or None
            if raw_circuit_state_path is not None
            else None
        ),
    )


@lru_cache(maxsize=32)
def _get_persistent_model_circuit_breaker_registry(
    state_path: str,
) -> ModelCircuitBreakerRegistry:
    return ModelCircuitBreakerRegistry(state_path=state_path)


def _build_model_circuit_breaker(
    running_config: AsyncOpenAIRunnerRunningConfig,
) -> tuple[ModelCircuitBreakerRegistry | None, ModelCircuitBreakerPolicy | None]:
    if not running_config.model_circuit_breaker_enabled:
        return None, None

    policy = ModelCircuitBreakerPolicy(
        enabled=True,
        failure_threshold=running_config.model_circuit_breaker_failure_threshold,
        cooldown_seconds=running_config.model_circuit_breaker_cooldown_seconds,
    )
    configured_state_path = str(
        running_config.model_circuit_breaker_state_path or ""
    ).strip()
    if not configured_state_path:
        return GLOBAL_MODEL_CIRCUIT_BREAKERS, policy
    resolved_state_path = str(Path(configured_state_path).expanduser().resolve())
    return _get_persistent_model_circuit_breaker_registry(resolved_state_path), policy


__all__ = ["create_runner"]
