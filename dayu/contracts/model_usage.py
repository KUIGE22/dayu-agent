"""Provider-neutral token usage contracts.

The runtime accepts both OpenAI-compatible usage payloads (including
DeepSeek extensions) and Anthropic usage payloads.  Provider fields are
normalized once at the Host boundary so upper layers never need vendor
specific accounting logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


def _counter(value: object) -> int:
    """Return a non-negative integer counter without accepting booleans."""

    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    if value < 0:
        return 0
    return int(value)


def _nested_counter(value: object, key: str) -> int:
    if not isinstance(value, Mapping):
        return 0
    return _counter(value.get(key))


@dataclass(frozen=True)
class ModelUsage:
    """Normalized token usage for one or more provider requests."""

    request_count: int = 0
    usage_report_count: int = 0
    input_tokens: int = 0
    uncached_input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_mapping(cls, raw_usage: Mapping[str, object] | None) -> "ModelUsage":
        """Normalize an OpenAI-compatible, DeepSeek, or Anthropic payload."""

        if not isinstance(raw_usage, Mapping) or not raw_usage:
            return cls()

        if "prompt_tokens" in raw_usage or "completion_tokens" in raw_usage:
            input_tokens = _counter(raw_usage.get("prompt_tokens"))
            output_tokens = _counter(raw_usage.get("completion_tokens"))
            details_cached = _nested_counter(
                raw_usage.get("prompt_tokens_details"), "cached_tokens"
            )
            cached_input_tokens = _counter(
                raw_usage.get("prompt_cache_hit_tokens")
            ) or details_cached
            explicit_uncached = _counter(raw_usage.get("prompt_cache_miss_tokens"))
            uncached_input_tokens = (
                explicit_uncached
                if "prompt_cache_miss_tokens" in raw_usage
                else max(input_tokens - cached_input_tokens, 0)
            )
            reasoning_tokens = _counter(raw_usage.get("reasoning_tokens")) or _nested_counter(
                raw_usage.get("completion_tokens_details"), "reasoning_tokens"
            )
            return cls(
                request_count=1,
                usage_report_count=1,
                input_tokens=input_tokens,
                uncached_input_tokens=uncached_input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                total_tokens=input_tokens + output_tokens,
            )

        uncached_input_tokens = _counter(raw_usage.get("input_tokens"))
        cached_input_tokens = _counter(raw_usage.get("cache_read_input_tokens"))
        cache_creation_input_tokens = _counter(
            raw_usage.get("cache_creation_input_tokens")
        )
        input_tokens = (
            uncached_input_tokens
            + cached_input_tokens
            + cache_creation_input_tokens
        )
        output_tokens = _counter(raw_usage.get("output_tokens"))
        return cls(
            request_count=1,
            usage_report_count=1,
            input_tokens=input_tokens,
            uncached_input_tokens=uncached_input_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=_counter(raw_usage.get("reasoning_tokens")),
            total_tokens=input_tokens + output_tokens,
        )

    @classmethod
    def from_done_usage(cls, raw_usage: Mapping[str, object] | None) -> "ModelUsage":
        """Normalize one DONE event while counting absent provider usage honestly."""

        normalized = cls.from_mapping(raw_usage)
        if normalized.request_count > 0:
            return normalized
        return cls(request_count=1)

    def __add__(self, other: object) -> "ModelUsage":
        if not isinstance(other, ModelUsage):
            return NotImplemented
        return ModelUsage(
            request_count=self.request_count + other.request_count,
            usage_report_count=self.usage_report_count + other.usage_report_count,
            input_tokens=self.input_tokens + other.input_tokens,
            uncached_input_tokens=(
                self.uncached_input_tokens + other.uncached_input_tokens
            ),
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            cache_creation_input_tokens=(
                self.cache_creation_input_tokens + other.cache_creation_input_tokens
            ),
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        """Return the stable JSON representation used by run summaries."""

        return {
            "request_count": self.request_count,
            "usage_report_count": self.usage_report_count,
            "input_tokens": self.input_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
        }


__all__ = ["ModelUsage"]
