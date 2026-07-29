"""Stable model-provider availability error classification."""

from __future__ import annotations


PROVIDER_AVAILABILITY_ERROR_TYPES = frozenset(
    {
        "network_error",
        "rate_limit_exceeded",
        "response_error",
        "server_error",
        "timeout",
        "unknown_error",
        "unknown_http_status",
    }
)
MODEL_FAILOVER_ERROR_TYPES = frozenset(
    {
        *PROVIDER_AVAILABILITY_ERROR_TYPES,
        "model_circuit_open",
    }
)


def is_provider_availability_error(error_type: object) -> bool:
    """Return whether an error should affect provider availability state."""

    return str(error_type or "").strip() in PROVIDER_AVAILABILITY_ERROR_TYPES


def is_model_failover_error(error_type: object) -> bool:
    """Return whether a clean model attempt may use an explicit fallback."""

    return str(error_type or "").strip() in MODEL_FAILOVER_ERROR_TYPES


__all__ = [
    "MODEL_FAILOVER_ERROR_TYPES",
    "PROVIDER_AVAILABILITY_ERROR_TYPES",
    "is_model_failover_error",
    "is_provider_availability_error",
]
