"""Anthropic native Messages API runner tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, AsyncIterator, cast

import pytest

from dayu.engine.async_anthropic_runner import (
    AnthropicSSEStreamParser,
    AsyncAnthropicRunner,
    _normalize_anthropic_response,
    resolve_anthropic_endpoint_url,
)
from dayu.engine.async_openai_runner import AsyncOpenAIRunnerRunningConfig
from dayu.engine.context_budget import ContextBudgetState
from dayu.engine.events import EventType, StreamEvent

if TYPE_CHECKING:
    from aiohttp import ClientResponse


class _ChunkedContentStub:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def iter_chunked(self, _: int) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


class _ResponseStub:
    def __init__(self, chunks: list[bytes]) -> None:
        self.content = _ChunkedContentStub(chunks)


def _sse_response(*payloads: dict[str, Any]) -> "ClientResponse":
    body = "".join(
        f"event: {payload.get('type', 'unknown')}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        for payload in payloads
    ).encode("utf-8")
    split_at = max(1, len(body) // 3)
    response = _ResponseStub(
        [body[:split_at], body[split_at : split_at * 2], body[split_at * 2 :]]
    )
    return cast("ClientResponse", cast(object, response))


async def _collect(events: AsyncIterator[StreamEvent]) -> list[StreamEvent]:
    return [event async for event in events]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://proxy.example", "https://proxy.example/v1/messages"),
        ("https://proxy.example/v1", "https://proxy.example/v1/messages"),
        (
            "https://proxy.example/v1/messages/",
            "https://proxy.example/v1/messages",
        ),
        (None, "https://api.anthropic.com/v1/messages"),
    ],
)
def test_resolve_anthropic_endpoint_url(
    base_url: str | None,
    expected: str,
) -> None:
    assert (
        resolve_anthropic_endpoint_url(
            "https://api.anthropic.com/v1/messages",
            base_url=base_url,
        )
        == expected
    )


@pytest.mark.unit
def test_build_request_payload_translates_system_and_tool_loop() -> None:
    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        temperature=0.2,
        supports_stream=False,
    )

    payload = runner._build_request_payload(
        messages=[
            {"role": "system", "content": "Follow the evidence."},
            {"role": "user", "content": "Look up the filing."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "tool_1",
                        "type": "function",
                        "function": {
                            "name": "read_filing",
                            "arguments": '{"ticker":"ABC"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tool_1",
                "name": "read_filing",
                "content": '{"ok":true,"value":"revenue up"}',
            },
        ],
        stream=False,
        extra_payloads={"max_tokens": 1024},
    )

    assert payload["system"] == "Follow the evidence."
    assert payload["model"] == "claude-sonnet-4-6"
    assert payload["max_tokens"] == 1024
    assert payload["temperature"] == 0.2
    assert payload["stream"] is False
    native_messages = payload["messages"]
    assert isinstance(native_messages, list)
    assert [message["role"] for message in native_messages] == [
        "user",
        "assistant",
        "user",
    ]
    assert native_messages[1]["content"][0] == {
        "type": "tool_use",
        "id": "tool_1",
        "name": "read_filing",
        "input": {"ticker": "ABC"},
    }
    assert native_messages[2]["content"][0]["type"] == "tool_result"


@pytest.mark.unit
def test_build_request_payload_omits_temperature_for_extended_thinking() -> None:
    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        temperature=0.2,
        supports_stream=False,
    )

    payload = runner._build_request_payload(
        messages=[{"role": "user", "content": "Think carefully."}],
        stream=False,
        extra_payloads={
            "max_tokens": 16000,
            "thinking": {"type": "enabled", "budget_tokens": 8000},
        },
    )

    assert "temperature" not in payload
    assert payload["thinking"] == {
        "type": "enabled",
        "budget_tokens": 8000,
    }


@pytest.mark.unit
def test_build_request_payload_enables_native_streaming() -> None:
    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        supports_stream=True,
    )

    payload = runner._build_request_payload(
        messages=[{"role": "user", "content": "Stream this."}],
        stream=True,
        extra_payloads={"max_tokens": 128},
    )

    assert payload["stream"] is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("auto", {"type": "auto"}),
        ("required", {"type": "any"}),
        ("none", {"type": "none"}),
        (
            {"type": "function", "function": {"name": "calculator"}},
            {"type": "tool", "name": "calculator"},
        ),
    ],
)
def test_build_request_payload_translates_tool_choice(
    configured: object,
    expected: object,
) -> None:
    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        supports_stream=False,
    )

    payload = runner._build_request_payload(
        messages=[{"role": "user", "content": "Use tools only when allowed."}],
        stream=False,
        extra_payloads={"tool_choice": configured},
    )

    assert payload["tool_choice"] == expected


@pytest.mark.unit
def test_tool_schema_uses_anthropic_input_schema() -> None:
    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        supports_stream=False,
    )

    assert runner._tool_to_provider_spec(
        {
            "name": "calculator",
            "description": "Calculate a value",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
            },
        }
    ) == {
        "name": "calculator",
        "description": "Calculate a value",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
        },
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_native_response_emits_shared_events_and_preserves_usage() -> None:
    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        supports_stream=False,
    )
    response: dict[str, Any] = {
        "id": "msg_1",
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "content": [
            {"type": "thinking", "thinking": "Check the evidence."},
            {"type": "text", "text": "Supported answer."},
        ],
        "usage": {
            "input_tokens": 12,
            "cache_read_input_tokens": 3,
            "cache_creation_input_tokens": 2,
            "output_tokens": 5,
        },
    }

    events = [
        event
        async for event in runner._process_non_stream(
            response,
            "req_test",
            {"run_id": "run_1"},
        )
    ]

    assert [event.type for event in events] == [
        EventType.REASONING_DELTA,
        EventType.CONTENT_DELTA,
        EventType.CONTENT_COMPLETE,
        EventType.DONE,
        EventType.METADATA,
    ]
    assert events[0].data == "Check the evidence."
    assert events[2].data == "Supported answer."
    assert events[2].metadata["reasoning_content"] == "Check the evidence."
    assert events[3].data["usage"] == response["usage"]
    assert events[4].data["token_usage_summary"] == {
        "prompt_tokens": 17,
        "completion_tokens": 5,
        "total_tokens": 22,
        "cached_tokens": 3,
        "cache_creation_tokens": 2,
        "reasoning_tokens": 0,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_native_response_fails_loud_on_pause_turn_without_done() -> None:
    """验证非流式 ``pause_turn`` 只产出稳定错误而不报告成功完成。

    参数:
        无。

    返回值:
        无。

    异常:
        AssertionError: 事件类型、错误分类或完成事件不符合契约时抛出。
    """

    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        supports_stream=False,
    )
    response: dict[str, Any] = {
        "id": "msg_pause",
        "model": "claude-sonnet-4-6",
        "stop_reason": "pause_turn",
        "content": [{"type": "text", "text": "Partial response."}],
        "usage": {"input_tokens": 4, "output_tokens": 2},
    }

    events = await _collect(
        runner._process_non_stream(
            response,
            "req_pause_non_stream",
            {"run_id": "run_pause_non_stream"},
        )
    )

    assert [event.type for event in events] == [EventType.ERROR]
    assert events[0].metadata["error_type"] == "anthropic_pause_turn_unsupported"
    assert not any(event.type is EventType.DONE for event in events)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_native_stream_emits_text_reasoning_and_usage() -> None:
    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        supports_stream=True,
    )
    response = _sse_response(
        {
            "type": "message_start",
            "message": {
                "content": [],
                "usage": {
                    "input_tokens": 12,
                    "cache_read_input_tokens": 3,
                    "output_tokens": 1,
                },
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "Check. "},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "ignored"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "text", "text": ""},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": "Hello"},
        },
        {"type": "future_event", "value": "ignored"},
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": " Claude"},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 7},
        },
        {"type": "message_stop"},
    )

    events = await _collect(
        runner._process_sse_stream(
            response,
            "req_stream",
            {"run_id": "run_stream"},
        )
    )

    assert [event.type for event in events] == [
        EventType.REASONING_DELTA,
        EventType.CONTENT_DELTA,
        EventType.CONTENT_DELTA,
        EventType.CONTENT_COMPLETE,
        EventType.DONE,
        EventType.METADATA,
    ]
    assert events[0].data == "Check. "
    assert events[3].data == "Hello Claude"
    assert events[3].metadata["reasoning_content"] == "Check. "
    assert events[4].data["finish_reason"] == "stop"
    assert events[4].data["usage"] == {
        "input_tokens": 12,
        "cache_read_input_tokens": 3,
        "output_tokens": 7,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_native_stream_fails_loud_on_pause_turn_without_done() -> None:
    """验证流式 ``pause_turn`` 以稳定协议错误收口且不产出成功完成。

    参数:
        无。

    返回值:
        无。

    异常:
        AssertionError: 事件序列、错误分类或完成事件不符合契约时抛出。
    """

    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        supports_stream=True,
    )
    response = _sse_response(
        {
            "type": "message_start",
            "message": {"content": [], "usage": {"input_tokens": 4}},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": "Partial response."},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "pause_turn"},
            "usage": {"output_tokens": 2},
        },
        {"type": "message_stop"},
    )

    events = await _collect(
        runner._process_sse_stream(
            response,
            "req_pause_stream",
            {"run_id": "run_pause_stream"},
        )
    )

    assert [event.type for event in events] == [
        EventType.CONTENT_DELTA,
        EventType.CONTENT_COMPLETE,
        EventType.ERROR,
    ]
    assert events[-1].metadata["error_type"] == "anthropic_pause_turn_unsupported"
    assert not any(event.type is EventType.DONE for event in events)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_native_stream_reassembles_tool_input_json() -> None:
    parser = AnthropicSSEStreamParser(
        name="claude",
        request_id="req_tool",
        running_config=AsyncOpenAIRunnerRunningConfig(),
    )
    response = _sse_response(
        {
            "type": "message_start",
            "message": {"content": [], "usage": {"input_tokens": 8}},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "tool_1",
                "name": "calculator",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {
                "type": "input_json_delta",
                "partial_json": '{"expression"',
            },
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": ':"2+2"}'},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 10},
        },
        {"type": "message_stop"},
    )

    events = await _collect(parser.parse_stream(response))
    result = parser.get_result()

    assert [event.type for event in events] == [
        EventType.TOOL_CALL_START,
        EventType.TOOL_CALL_DELTA,
        EventType.TOOL_CALL_DELTA,
    ]
    assert result.tool_calls == [
        {
            "id": "tool_1",
            "name": "calculator",
            "arguments": {"expression": "2+2"},
            "index_in_iteration": 0,
        }
    ]
    assert result.stream_state["finish_reason"] == "tool_calls"
    assert result.stream_state["tool_calls_finished"] is True
    assert result.usage == {"input_tokens": 8, "output_tokens": 10}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_native_stream_completes_no_argument_tool_with_empty_object() -> None:
    parser = AnthropicSSEStreamParser(
        name="claude",
        request_id="req_no_args",
        running_config=AsyncOpenAIRunnerRunningConfig(),
    )
    response = _sse_response(
        {
            "type": "message_start",
            "message": {"content": [], "usage": {"input_tokens": 5}},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "tool_no_args",
                "name": "current_time",
                "input": {},
            },
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 3},
        },
        {"type": "message_stop"},
    )

    events = await _collect(parser.parse_stream(response))
    result = parser.get_result()

    assert [event.type for event in events] == [
        EventType.TOOL_CALL_START,
        EventType.TOOL_CALL_DELTA,
    ]
    assert result.tool_calls == [
        {
            "id": "tool_no_args",
            "name": "current_time",
            "arguments": {},
            "index_in_iteration": 0,
        }
    ]
    assert result.stream_state["tool_calls_finished"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_native_stream_reports_in_band_error() -> None:
    runner = AsyncAnthropicRunner(
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        headers={},
        supports_stream=True,
    )
    response = _sse_response(
        {
            "type": "message_start",
            "message": {"content": [], "usage": {"input_tokens": 4}},
        },
        {
            "type": "error",
            "error": {"type": "overloaded_error", "message": "Overloaded"},
        },
    )

    events = await _collect(
        runner._process_sse_stream(
            response,
            "req_error",
            {"run_id": "run_error"},
        )
    )

    assert [event.type for event in events] == [
        EventType.CONTENT_COMPLETE,
        EventType.ERROR,
    ]
    assert events[1].metadata["error_type"] == "overloaded_error"
    assert events[1].data["message"] == "Overloaded"


@pytest.mark.unit
def test_native_tool_use_normalizes_to_openai_internal_shape() -> None:
    normalized = _normalize_anthropic_response(
        {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool_9",
                    "name": "calculator",
                    "input": {"expression": "2+2"},
                }
            ],
        }
    )

    choice = normalized["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"] == [
        {
            "id": "tool_9",
            "type": "function",
            "function": {
                "name": "calculator",
                "arguments": '{"expression":"2+2"}',
            },
        }
    ]


@pytest.mark.unit
def test_context_budget_accepts_anthropic_native_usage() -> None:
    state = ContextBudgetState(max_context_tokens=131072)
    state.record_usage(
        {
            "input_tokens": 5000,
            "cache_read_input_tokens": 1200,
            "cache_creation_input_tokens": 300,
            "output_tokens": 1000,
        }
    )

    assert state.current_prompt_tokens == 6500
    assert state.latest_completion_tokens == 1000
    assert state.total_prompt_tokens == 6500
    assert state.total_completion_tokens == 1000
    assert state.iteration_count == 1
