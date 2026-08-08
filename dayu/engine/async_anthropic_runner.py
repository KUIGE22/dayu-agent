"""Anthropic Messages API adapter for the shared async HTTP runner."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List

from dayu.contracts.agent_types import AgentMessage

from .async_openai_runner import AsyncOpenAIRunner
from .events import StreamEvent, reasoning_delta
from .sse_parser import SSEStreamParser


_STOP_REASON_MAP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "refusal": "content_filter",
}

_PAUSE_TURN_STOP_REASON = "pause_turn"
_PAUSE_TURN_ERROR_TYPE = "anthropic_pause_turn_unsupported"
_PAUSE_TURN_ERROR_MESSAGE = (
    "Anthropic pause_turn continuation is unsupported by the current message contract"
)


def resolve_anthropic_endpoint_url(
    configured_endpoint_url: str,
    *,
    base_url: str | None,
) -> str:
    """Resolve an optional Anthropic-compatible base URL to ``/v1/messages``."""

    normalized_base = str(base_url or "").strip().rstrip("/")
    if not normalized_base:
        return configured_endpoint_url
    if normalized_base.endswith("/v1/messages"):
        return normalized_base
    if normalized_base.endswith("/v1"):
        return f"{normalized_base}/messages"
    return f"{normalized_base}/v1/messages"


def _parse_tool_arguments(raw_arguments: object) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return {str(key): value for key, value in raw_arguments.items()}
    if not isinstance(raw_arguments, str):
        raise ValueError("Anthropic tool_use input must be a JSON object")
    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("Anthropic tool_use arguments must contain valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Anthropic tool_use arguments must decode to a JSON object")
    return {str(key): value for key, value in parsed.items()}


def _tool_result_is_error(content: str) -> bool:
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("ok") is False


def _append_native_message(
    messages: list[dict[str, Any]],
    *,
    role: str,
    blocks: list[dict[str, Any]],
) -> None:
    if not blocks:
        blocks = [{"type": "text", "text": ""}]
    if messages and messages[-1].get("role") == role:
        existing_content = messages[-1].get("content")
        if isinstance(existing_content, list):
            existing_content.extend(blocks)
            return
    messages.append({"role": role, "content": blocks})


def _to_anthropic_messages(
    messages: List[AgentMessage],
) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    native_messages: list[dict[str, Any]] = []

    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "system":
            text = str(content or "").strip()
            if text:
                system_parts.append(text)
            continue
        if role == "user":
            _append_native_message(
                native_messages,
                role="user",
                blocks=[{"type": "text", "text": str(content or "")}],
            )
            continue
        if role == "tool":
            tool_call_id = str(message.get("tool_call_id") or "").strip()
            if not tool_call_id:
                raise ValueError("Anthropic tool_result message requires tool_call_id")
            result_content = str(content or "")
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": result_content,
            }
            if _tool_result_is_error(result_content):
                block["is_error"] = True
            _append_native_message(native_messages, role="user", blocks=[block])
            continue
        if role != "assistant":
            raise ValueError(f"Unsupported Anthropic message role: {role}")

        assistant_blocks: list[dict[str, Any]] = []
        if content:
            assistant_blocks.append({"type": "text", "text": str(content)})
        tool_calls = message.get("tool_calls") or []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                raise ValueError("Anthropic assistant tool_calls entries must be objects")
            function = tool_call.get("function")
            if not isinstance(function, dict):
                raise ValueError("Anthropic assistant tool_call requires function")
            tool_call_id = str(tool_call.get("id") or "").strip()
            tool_name = str(function.get("name") or "").strip()
            if not tool_call_id or not tool_name:
                raise ValueError("Anthropic assistant tool_call requires id and name")
            assistant_blocks.append(
                {
                    "type": "tool_use",
                    "id": tool_call_id,
                    "name": tool_name,
                    "input": _parse_tool_arguments(function.get("arguments", "{}")),
                }
            )
        _append_native_message(
            native_messages,
            role="assistant",
            blocks=assistant_blocks,
        )

    return "\n\n".join(system_parts), native_messages


def _normalize_tool_choice(value: object) -> object:
    if value == "auto":
        return {"type": "auto"}
    if value == "required":
        return {"type": "any"}
    if value == "none":
        return {"type": "none"}
    if not isinstance(value, dict):
        return value
    function = value.get("function")
    if value.get("type") == "function" and isinstance(function, dict):
        name = str(function.get("name") or "").strip()
        if name:
            return {"type": "tool", "name": name}
    return value


def _normalize_anthropic_response(result: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(result.get("choices"), list):
        return result

    raw_blocks = result.get("content")
    if not isinstance(raw_blocks, list):
        return {"choices": [], "usage": result.get("usage")}

    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(str(block.get("text") or ""))
        elif block_type == "thinking":
            reasoning_parts.append(str(block.get("thinking") or ""))
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": str(block.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": str(block.get("name") or ""),
                        "arguments": json.dumps(
                            block.get("input", {}),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                }
            )

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(text_parts),
    }
    reasoning_content = "".join(reasoning_parts)
    if reasoning_content:
        message["reasoning_content"] = reasoning_content
    if tool_calls:
        message["tool_calls"] = tool_calls

    normalized: Dict[str, Any] = {
        "id": result.get("id"),
        "model": result.get("model"),
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": _STOP_REASON_MAP.get(
                    str(result.get("stop_reason") or ""),
                    result.get("stop_reason"),
                ),
            }
        ],
    }
    usage = result.get("usage")
    if isinstance(usage, dict):
        normalized["usage"] = usage
    return normalized


class AnthropicSSEStreamParser(SSEStreamParser):
    """Map Anthropic Messages API SSE payloads into Dayu's stream contract."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._anthropic_tool_initial_inputs: dict[int, dict[str, Any]] = {}

    def _merge_usage(self, usage: object) -> None:
        if not isinstance(usage, dict):
            return
        if self._usage is None:
            self._usage = {}
        self._usage.update(
            {str(key): value for key, value in usage.items()}
        )

    def _event_index(self, data: dict[str, Any], event_type: str) -> int | None:
        index = data.get("index")
        if isinstance(index, int) and not isinstance(index, bool) and index >= 0:
            return index
        self._record_protocol_error(
            "response_error",
            f"Anthropic {event_type} requires a non-negative integer index",
            body=json.dumps(data, ensure_ascii=False, default=str)[:500],
        )
        return None

    async def _handle_payload(self, payload: str) -> AsyncIterator[StreamEvent]:
        """解析 Anthropic SSE payload 并产出共享流事件。

        参数:
            payload: 单个 Anthropic SSE data 行的 JSON 文本。

        返回值:
            异步迭代生成内容、推理或工具调用增量事件。

        异常:
            无；畸形 payload 与当前不支持的 ``pause_turn`` 会记录为协议错误，
            由 Runner 统一转换成失败事件。
        """

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            self._record_protocol_error(
                "response_error",
                "Invalid JSON SSE payload",
                body=payload[:500],
            )
            return
        if not isinstance(data, dict):
            self._record_protocol_error(
                "response_error",
                "Anthropic SSE payload must be an object",
                body=payload[:500],
            )
            return

        event_type = str(data.get("type") or "")
        if event_type == "message_start":
            message = data.get("message")
            if not isinstance(message, dict):
                self._record_protocol_error(
                    "response_error",
                    "Anthropic message_start requires a message object",
                    body=payload[:500],
                )
                return
            self._stream_state["saw_choice"] = True
            self._merge_usage(message.get("usage"))
            return

        if event_type == "content_block_start":
            index = self._event_index(data, event_type)
            if index is None:
                return
            block = data.get("content_block")
            if not isinstance(block, dict):
                self._record_protocol_error(
                    "response_error",
                    "Anthropic content_block_start requires a content_block object",
                    body=payload[:500],
                )
                return
            block_type = block.get("type")
            if block_type == "text" and block.get("text"):
                async for event in self._yield_content_chunks(str(block["text"])):
                    yield event
            elif block_type == "thinking" and block.get("thinking"):
                text = str(block["thinking"])
                self._reasoning_content_buffer.append(text)
                yield reasoning_delta(text)
            elif block_type == "tool_use":
                tool_id = str(block.get("id") or "").strip()
                tool_name = str(block.get("name") or "").strip()
                initial_input = block.get("input")
                if not isinstance(initial_input, dict):
                    initial_input = {}
                self._anthropic_tool_initial_inputs[index] = {
                    str(key): value for key, value in initial_input.items()
                }
                async for event in self._handle_tool_call_delta(
                    {
                        "index": index,
                        "id": tool_id,
                        "function": {"name": tool_name, "arguments": None},
                    }
                ):
                    yield event
            return

        if event_type == "content_block_delta":
            index = self._event_index(data, event_type)
            if index is None:
                return
            delta = data.get("delta")
            if not isinstance(delta, dict):
                self._record_protocol_error(
                    "response_error",
                    "Anthropic content_block_delta requires a delta object",
                    body=payload[:500],
                )
                return
            delta_type = delta.get("type")
            if delta_type == "text_delta":
                text = str(delta.get("text") or "")
                if text:
                    async for event in self._yield_content_chunks(text):
                        yield event
            elif delta_type == "thinking_delta":
                text = str(delta.get("thinking") or "")
                if text:
                    self._reasoning_content_buffer.append(text)
                    yield reasoning_delta(text)
            elif delta_type == "input_json_delta":
                partial_json = delta.get("partial_json")
                if partial_json is not None and not isinstance(partial_json, str):
                    self._record_protocol_error(
                        "tool_call_incomplete",
                        "Anthropic input_json_delta partial_json must be a string",
                        body=payload[:500],
                    )
                    return
                if partial_json:
                    async for event in self._handle_tool_call_delta(
                        {
                            "index": index,
                            "function": {"arguments": partial_json},
                        }
                    ):
                        yield event
            return

        if event_type == "content_block_stop":
            index = self._event_index(data, event_type)
            if index is None:
                return
            tool_entry = self._tool_calls_buffer.get(index)
            if tool_entry is not None and not tool_entry.get("arguments_buf"):
                initial_input = self._anthropic_tool_initial_inputs.get(index, {})
                arguments = json.dumps(
                    initial_input,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                async for event in self._handle_tool_call_delta(
                    {
                        "index": index,
                        "function": {"arguments": arguments},
                    }
                ):
                    yield event
            return

        if event_type == "message_delta":
            delta = data.get("delta")
            if isinstance(delta, dict):
                raw_stop_reason = delta.get("stop_reason")
                if raw_stop_reason is not None:
                    if raw_stop_reason == _PAUSE_TURN_STOP_REASON:
                        self._record_protocol_error(
                            _PAUSE_TURN_ERROR_TYPE,
                            _PAUSE_TURN_ERROR_MESSAGE,
                        )
                        self._merge_usage(data.get("usage"))
                        return
                    finish_reason = _STOP_REASON_MAP.get(
                        str(raw_stop_reason),
                        raw_stop_reason,
                    )
                    self._stream_state["finish_reason"] = finish_reason
                    if finish_reason == "tool_calls":
                        self._stream_state["tool_calls_finished"] = True
                    elif finish_reason == "length":
                        self._stream_state["truncated"] = True
                    elif finish_reason == "content_filter":
                        self._stream_state["content_filtered"] = True
            self._merge_usage(data.get("usage"))
            return

        if event_type == "message_stop":
            self._done_received = True
            return

        if event_type == "error":
            error = data.get("error")
            if not isinstance(error, dict):
                error = {}
            self._record_protocol_error(
                str(error.get("type") or "response_error"),
                str(error.get("message") or "Anthropic streaming error"),
                body=payload[:500],
            )
            return

        # Ping and future event/delta types are intentionally ignored.


class AsyncAnthropicRunner(AsyncOpenAIRunner):
    """Run Anthropic's native Messages API through Dayu's event contract."""

    def _build_request_payload(
        self,
        *,
        messages: List[AgentMessage],
        stream: bool,
        extra_payloads: Dict[str, Any],
    ) -> Dict[str, Any]:
        system_prompt, native_messages = _to_anthropic_messages(messages)
        payload = dict(extra_payloads)
        max_tokens = payload.pop(
            "max_tokens",
            payload.pop("max_completion_tokens", 8192),
        )
        try:
            normalized_max_tokens = int(max_tokens)
        except (TypeError, ValueError) as exc:
            raise ValueError("Anthropic max_tokens must be a positive integer") from exc
        if normalized_max_tokens <= 0:
            raise ValueError("Anthropic max_tokens must be a positive integer")

        payload.pop("stream_options", None)
        payload.pop("n", None)
        payload.pop("response_format", None)
        stop = payload.pop("stop", None)
        if stop is not None and "stop_sequences" not in payload:
            payload["stop_sequences"] = [stop] if isinstance(stop, str) else stop
        if "tool_choice" in payload:
            tool_choice = _normalize_tool_choice(payload["tool_choice"])
            payload["tool_choice"] = tool_choice

        thinking = payload.get("thinking")
        thinking_enabled = isinstance(thinking, dict) and thinking.get("type") == "enabled"
        payload.update(
            {
                "model": self.model,
                "messages": native_messages,
                "max_tokens": normalized_max_tokens,
                "stream": stream,
            }
        )
        if system_prompt:
            payload["system"] = system_prompt
        if thinking_enabled:
            payload.pop("temperature", None)
        else:
            payload["temperature"] = self.temperature
        return payload

    def _create_sse_parser(
        self,
        *,
        request_id: str,
        content_reasoning_tag: str | None,
    ) -> SSEStreamParser:
        return AnthropicSSEStreamParser(
            name=self.name,
            request_id=request_id,
            running_config=self.running_config,
            cancellation_token=self.cancellation_token,
            content_reasoning_tag=content_reasoning_tag,
        )

    def _tool_to_provider_spec(self, tool: Dict) -> Dict:
        openai_spec = self._tool_to_openai_spec(tool)
        function = openai_spec.get("function", {})
        if not isinstance(function, dict):
            function = {}
        input_schema = function.get("parameters", {})
        if not isinstance(input_schema, dict):
            input_schema = {}
        return {
            "name": str(function.get("name") or ""),
            "description": str(function.get("description") or ""),
            "input_schema": input_schema,
        }

    async def _process_non_stream(
        self,
        result: Dict,
        request_id: str,
        trace_meta: Dict[str, Any],
        content_reasoning_tag: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """处理 Anthropic 非流式响应并拒绝无法续传的暂停回合。

        参数:
            result: Anthropic Messages API 的完整 JSON 响应。
            request_id: 当前模型请求标识。
            trace_meta: 需要附加到共享事件的追踪元数据。
            content_reasoning_tag: 兼容父类签名的 reasoning 标签；Anthropic 原生
                thinking block 不使用该参数。

        返回值:
            异步迭代生成归一化共享事件；``pause_turn`` 仅生成稳定错误事件。

        异常:
            无；响应协议失败通过 ``StreamEvent`` 错误事件返回。
        """

        del content_reasoning_tag
        if result.get("stop_reason") == _PAUSE_TURN_STOP_REASON:
            yield self._build_non_stream_error_event(
                trace_meta=trace_meta,
                log_message=(
                    f"[{self.name}][{request_id}] {_PAUSE_TURN_ERROR_MESSAGE}"
                    f"（error_type={_PAUSE_TURN_ERROR_TYPE}）"
                ),
                message=_PAUSE_TURN_ERROR_MESSAGE,
                error_type=_PAUSE_TURN_ERROR_TYPE,
            )
            return
        normalized = _normalize_anthropic_response(result)
        async for event in super()._process_non_stream(
            normalized,
            request_id,
            trace_meta,
            content_reasoning_tag=None,
        ):
            yield event


__all__ = [
    "AnthropicSSEStreamParser",
    "AsyncAnthropicRunner",
    "resolve_anthropic_endpoint_url",
]
