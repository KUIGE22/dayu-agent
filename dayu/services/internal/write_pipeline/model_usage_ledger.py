"""Thread-safe model usage and configured-cost ledger for write runs."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from threading import Lock
from typing import Any, Mapping

from dayu.contracts.model_usage import ModelUsage
from dayu.services.internal.write_pipeline.enums import (
    AUDIT_WRITE_SCENES,
    PRIMARY_MODEL_WRITE_SCENES,
)

_ONE_MILLION = Decimal(1_000_000)
_DEFAULT_PROJECTED_OUTPUT_TOKENS = 8_192


class WriteBudgetExceededError(RuntimeError):
    """A write-run budget gate rejected or stopped a model scene."""

    def __init__(self, block: Mapping[str, object]) -> None:
        self.block = dict(block)
        super().__init__(str(block.get("reason") or "写作运行预算已耗尽"))


@dataclass(frozen=True)
class WriteSceneBudgetReservation:
    """Atomic admission reservation for one model scene call."""

    reservation_id: int
    model_requests: int
    total_tokens: int
    estimated_cost: Decimal | None
    currency: str | None


def model_role_for_scene(scene_name: str) -> str:
    """Map a write scene to its stable dual-model responsibility."""

    if scene_name in PRIMARY_MODEL_WRITE_SCENES:
        return "primary"
    if scene_name in AUDIT_WRITE_SCENES:
        return "audit"
    return "other"


def _decimal_rate(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not rate.is_finite() or rate < 0:
        return None
    return rate


@dataclass(frozen=True)
class _UsageRecord:
    scene_name: str
    model_name: str
    model_role: str
    usage: ModelUsage
    replay: bool
    currency: str | None
    estimated_cost: Decimal | None


@dataclass(frozen=True)
class _ModelFallbackRouteRecord:
    scene_name: str
    primary_model_name: str
    fallback_model_name: str
    trigger_error_types: tuple[str, ...]
    fallback_call_status: str
    fallback_error_types: tuple[str, ...]


@dataclass(frozen=True)
class _CostObservation:
    scene_call_count: int
    request_count: int
    usage_report_count: int
    currency: str | None
    estimated_cost: Decimal | None


def _estimate_cost(
    *,
    usage: ModelUsage,
    model_config: Mapping[str, object],
) -> tuple[str | None, Decimal | None]:
    if usage.usage_report_count <= 0:
        return None, None
    pricing = model_config.get("pricing")
    if not isinstance(pricing, Mapping):
        return None, None
    currency_value = pricing.get("currency")
    currency = str(currency_value).strip().upper() if currency_value else ""
    if not currency:
        return None, None

    token_rates = (
        (usage.uncached_input_tokens, "input_per_million"),
        (usage.cached_input_tokens, "cached_input_per_million"),
        (usage.cache_creation_input_tokens, "cache_creation_input_per_million"),
        (usage.output_tokens, "output_per_million"),
    )
    cost = Decimal(0)
    for tokens, rate_name in token_rates:
        if tokens <= 0:
            continue
        rate = _decimal_rate(pricing.get(rate_name))
        if rate is None:
            return currency, None
        cost += Decimal(tokens) * rate / _ONE_MILLION
    return currency, cost


def validate_model_pricing_for_budget(
    *,
    model_name: str,
    model_config: Mapping[str, object],
    budget_currency: str,
) -> str | None:
    """Return a safe validation message when a cost-budget model is unpriceable."""

    probe_usage = ModelUsage(
        request_count=1,
        usage_report_count=1,
        input_tokens=1,
        uncached_input_tokens=1,
        output_tokens=1,
        total_tokens=2,
    )
    currency, estimated_cost = _estimate_cost(
        usage=probe_usage,
        model_config=model_config,
    )
    if currency is None or estimated_cost is None:
        return f"模型 {model_name} 缺少可审计价格，无法启用写作成本预算"
    normalized_currency = str(budget_currency or "").strip().upper()
    if currency != normalized_currency:
        return (
            f"模型 {model_name} 的价格币种为 {currency}，"
            f"与写作预算币种 {normalized_currency or 'missing'} 不一致"
        )
    return None


def _cost_summary_from_observations(
    observations: list[_CostObservation],
) -> dict[str, Any]:
    priced = [item for item in observations if item.estimated_cost is not None]
    priced_count = sum(item.scene_call_count for item in priced)
    unpriced_count = sum(
        item.scene_call_count
        for item in observations
        if item.estimated_cost is None
    )
    currencies = {item.currency for item in priced if item.currency}
    if not priced:
        return {
            "currency": None,
            "status": "unavailable",
            "known_estimated_cost": None,
            "priced_scene_call_count": 0,
            "unpriced_scene_call_count": unpriced_count,
        }
    if len(currencies) != 1:
        return {
            "currency": "MIXED",
            "status": "partial",
            "known_estimated_cost": None,
            "priced_scene_call_count": priced_count,
            "unpriced_scene_call_count": unpriced_count,
        }
    known_cost = sum(
        (item.estimated_cost or Decimal(0) for item in priced), Decimal(0)
    )
    usage_coverage_complete = all(
        item.request_count > 0
        and item.usage_report_count == item.request_count
        for item in observations
    )
    return {
        "currency": next(iter(currencies)),
        "status": (
            "complete"
            if not unpriced_count and usage_coverage_complete
            else "partial"
        ),
        "known_estimated_cost": float(known_cost),
        "priced_scene_call_count": priced_count,
        "unpriced_scene_call_count": unpriced_count,
    }


def _cost_summary(records: list[_UsageRecord]) -> dict[str, Any]:
    return _cost_summary_from_observations(
        [
            _CostObservation(
                scene_call_count=1,
                request_count=record.usage.request_count,
                usage_report_count=record.usage.usage_report_count,
                currency=record.currency,
                estimated_cost=record.estimated_cost,
            )
            for record in records
        ]
    )


def _summary_counter(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _usage_from_summary(value: Mapping[str, object]) -> ModelUsage:
    return ModelUsage(
        request_count=_summary_counter(value.get("request_count")),
        usage_report_count=_summary_counter(value.get("usage_report_count")),
        input_tokens=_summary_counter(value.get("input_tokens")),
        uncached_input_tokens=_summary_counter(value.get("uncached_input_tokens")),
        cached_input_tokens=_summary_counter(value.get("cached_input_tokens")),
        cache_creation_input_tokens=_summary_counter(
            value.get("cache_creation_input_tokens")
        ),
        output_tokens=_summary_counter(value.get("output_tokens")),
        reasoning_tokens=_summary_counter(value.get("reasoning_tokens")),
        total_tokens=_summary_counter(value.get("total_tokens")),
    )


def reprice_model_usage_summary(
    model_usage_summary: Mapping[str, Any],
    model_catalog: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    """Recalculate aggregate cost from persisted usage and current catalog rates.

    The returned object is a deep copy. Persisted run summaries remain untouched,
    so callers cannot accidentally rewrite the original run-time receipt.
    """

    result = deepcopy(dict(model_usage_summary))
    raw_by_scene = model_usage_summary.get("by_scene")
    if not isinstance(raw_by_scene, list):
        raise ValueError("model_usage.by_scene must be a list for cost repricing")

    observations: list[tuple[str, str, _CostObservation]] = []
    repriced_scenes: list[dict[str, Any]] = []
    for index, raw_scene in enumerate(raw_by_scene):
        if not isinstance(raw_scene, Mapping):
            raise ValueError(f"model_usage.by_scene[{index}] must be an object")
        model_name = str(raw_scene.get("model_name") or "").strip()
        model_role = str(raw_scene.get("model_role") or "other").strip() or "other"
        scene_call_count = _summary_counter(raw_scene.get("scene_call_count"))
        if not model_name or scene_call_count <= 0:
            raise ValueError(
                f"model_usage.by_scene[{index}] requires model_name and positive scene_call_count"
            )

        usage = _usage_from_summary(raw_scene)
        raw_model_config = model_catalog.get(model_name)
        model_config: Mapping[str, object] = (
            raw_model_config if isinstance(raw_model_config, Mapping) else {}
        )
        currency, estimated_cost = _estimate_cost(
            usage=usage,
            model_config=model_config,
        )
        observation = _CostObservation(
            scene_call_count=scene_call_count,
            request_count=usage.request_count,
            usage_report_count=usage.usage_report_count,
            currency=currency,
            estimated_cost=estimated_cost,
        )
        observations.append((model_role, model_name, observation))
        repriced_scene = deepcopy(dict(raw_scene))
        repriced_scene["cost"] = _cost_summary_from_observations([observation])
        repriced_scenes.append(repriced_scene)

    result["by_scene"] = repriced_scenes
    raw_by_role = model_usage_summary.get("by_role")
    if isinstance(raw_by_role, Mapping):
        repriced_roles: dict[str, Any] = {}
        for raw_role_name, raw_role_summary in raw_by_role.items():
            role_name = str(raw_role_name)
            if not isinstance(raw_role_summary, Mapping):
                raise ValueError(f"model_usage.by_role.{role_name} must be an object")
            role_summary = deepcopy(dict(raw_role_summary))
            role_summary["cost"] = _cost_summary_from_observations(
                [
                    observation
                    for candidate_role, _model_name, observation in observations
                    if candidate_role == role_name
                ]
            )
            repriced_roles[role_name] = role_summary
        result["by_role"] = repriced_roles

    all_cost_observations = [observation for _role, _model, observation in observations]
    result["cost"] = _cost_summary_from_observations(all_cost_observations)
    result["cost_repricing"] = {
        "mode": "current_model_catalog",
        "model_names": sorted({model_name for _role, model_name, _item in observations}),
        "unpriced_model_names": sorted(
            {
                model_name
                for _role, model_name, item in observations
                if item.estimated_cost is None
            }
        ),
    }
    return result


def _summarize_records(records: list[_UsageRecord]) -> dict[str, Any]:
    total_usage = ModelUsage()
    for record in records:
        total_usage += record.usage
    metered_count = sum(1 for record in records if record.usage.usage_report_count > 0)
    fully_metered_count = sum(
        1
        for record in records
        if record.usage.request_count > 0
        and record.usage.usage_report_count == record.usage.request_count
    )
    partially_metered_count = sum(
        1
        for record in records
        if 0 < record.usage.usage_report_count < record.usage.request_count
    )
    unknown_scene_call_count = sum(
        1 for record in records if record.usage.request_count <= 0
    )
    if not records:
        usage_status = "no_usage"
    elif (
        total_usage.request_count > 0
        and total_usage.usage_report_count == total_usage.request_count
        and unknown_scene_call_count == 0
    ):
        usage_status = "complete"
    elif total_usage.usage_report_count > 0:
        usage_status = "partial"
    else:
        usage_status = "unavailable"
    return {
        "usage_status": usage_status,
        "scene_call_count": len(records),
        "metered_scene_call_count": metered_count,
        "fully_metered_scene_call_count": fully_metered_count,
        "partially_metered_scene_call_count": partially_metered_count,
        "unmetered_scene_call_count": len(records) - metered_count,
        "replay_call_count": sum(1 for record in records if record.replay),
        **total_usage.to_dict(),
        "unreported_request_count": (
            total_usage.request_count - total_usage.usage_report_count
        ),
        "cost": _cost_summary(records),
    }


def _positive_optional_int(value: int | None, *, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_optional_decimal(
    value: float | Decimal | None,
    *,
    name: str,
) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive finite number")
    try:
        normalized = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a positive finite number") from exc
    if not normalized.is_finite() or normalized <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return normalized


def _ceil_div(value: int, divisor: int) -> int:
    if divisor <= 0:
        return 0
    return (max(value, 0) + divisor - 1) // divisor


def _estimate_prompt_tokens(prompt_text: str) -> int:
    encoded_length = len(str(prompt_text or "").encode("utf-8"))
    return max(_ceil_div(encoded_length, 3), 1)


def _json_number(value: int | Decimal | None) -> int | float | None:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _required_route_name(value: str, *, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _normalized_error_types(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


class WriteModelUsageLedger:
    """Collect write usage, budgets, and fallback routes across concurrent workers."""

    def __init__(
        self,
        *,
        max_model_requests: int | None = None,
        max_total_tokens: int | None = None,
        max_estimated_cost: float | Decimal | None = None,
        budget_currency: str = "",
    ) -> None:
        self._records: list[_UsageRecord] = []
        self._model_fallback_routes: list[_ModelFallbackRouteRecord] = []
        self._lock = Lock()
        self._max_model_requests = _positive_optional_int(
            max_model_requests,
            name="max_model_requests",
        )
        self._max_total_tokens = _positive_optional_int(
            max_total_tokens,
            name="max_total_tokens",
        )
        self._max_estimated_cost = _positive_optional_decimal(
            max_estimated_cost,
            name="max_estimated_cost",
        )
        self._budget_currency = str(budget_currency or "").strip().upper()
        if self._max_estimated_cost is not None and not self._budget_currency:
            raise ValueError("max_estimated_cost requires budget_currency")
        if self._max_estimated_cost is None and self._budget_currency:
            raise ValueError("budget_currency requires max_estimated_cost")
        self._budget_enabled = any(
            value is not None
            for value in (
                self._max_model_requests,
                self._max_total_tokens,
                self._max_estimated_cost,
            )
        )
        self._budget_model_requests = 0
        self._reservations: dict[int, WriteSceneBudgetReservation] = {}
        self._next_reservation_id = 1
        self._budget_block: dict[str, Any] | None = None

    def reserve_scene_call(
        self,
        *,
        scene_name: str,
        model_name: str,
        model_config: Mapping[str, object],
        prompt_text: str,
    ) -> WriteSceneBudgetReservation | None:
        """Atomically reserve projected budget before dispatching a scene."""

        if not self._budget_enabled:
            return None
        with self._lock:
            if self._budget_block is not None:
                raise WriteBudgetExceededError(self._budget_block)

            reservation_or_block = self._build_reservation_or_block_locked(
                scene_name=scene_name,
                model_name=model_name,
                model_config=model_config,
                prompt_text=prompt_text,
            )
            if isinstance(reservation_or_block, dict):
                self._budget_block = reservation_or_block
                raise WriteBudgetExceededError(reservation_or_block)
            reservation = reservation_or_block
            block = self._check_projected_limits_locked(
                phase="admission",
                scene_name=scene_name,
                model_name=model_name,
                candidate=reservation,
            )
            if block is not None:
                self._budget_block = block
                raise WriteBudgetExceededError(block)
            self._reservations[reservation.reservation_id] = reservation
            self._next_reservation_id += 1
            return reservation

    def release_scene_call(
        self,
        reservation: WriteSceneBudgetReservation | None,
    ) -> None:
        """Release an admission reservation when dispatch failed before usage settled."""

        if reservation is None:
            return
        with self._lock:
            self._reservations.pop(reservation.reservation_id, None)

    def record(
        self,
        *,
        scene_name: str,
        model_name: str,
        model_role: str,
        model_config: Mapping[str, object],
        usage: ModelUsage,
        replay: bool,
        reservation: WriteSceneBudgetReservation | None = None,
    ) -> None:
        currency, estimated_cost = _estimate_cost(
            usage=usage,
            model_config=model_config,
        )
        record = _UsageRecord(
            scene_name=scene_name,
            model_name=model_name,
            model_role=model_role,
            usage=usage,
            replay=replay,
            currency=currency,
            estimated_cost=estimated_cost,
        )
        raised_block: dict[str, Any] | None = None
        with self._lock:
            if reservation is not None:
                self._reservations.pop(reservation.reservation_id, None)
            self._records.append(record)
            self._budget_model_requests += max(
                usage.request_count,
                reservation.model_requests if reservation is not None else 1,
            )
            if self._budget_enabled and self._budget_block is None:
                raised_block = self._check_settled_usage_locked(
                    scene_name=scene_name,
                    model_name=model_name,
                    usage=usage,
                )
                if raised_block is not None:
                    self._budget_block = raised_block
        if raised_block is not None:
            raise WriteBudgetExceededError(raised_block)

    def build_summary(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)
        summary = _summarize_records(records)
        roles = sorted({record.model_role for record in records})
        summary["by_role"] = {
            role: _summarize_records(
                [record for record in records if record.model_role == role]
            )
            for role in roles
        }
        scene_keys = sorted(
            {(record.scene_name, record.model_name, record.model_role) for record in records}
        )
        by_scene: list[dict[str, Any]] = []
        for scene_name, model_name, model_role in scene_keys:
            scene_records = [
                record
                for record in records
                if (
                    record.scene_name,
                    record.model_name,
                    record.model_role,
                )
                == (scene_name, model_name, model_role)
            ]
            by_scene.append(
                {
                    "scene_name": scene_name,
                    "model_name": model_name,
                    "model_role": model_role,
                    **_summarize_records(scene_records),
                }
            )
        summary["by_scene"] = by_scene
        return summary

    def record_fallback_switch(
        self,
        *,
        scene_name: str,
        primary_model_name: str,
        fallback_model_name: str,
        trigger_error_types: tuple[str, ...],
        fallback_call_status: str,
        fallback_error_types: tuple[str, ...] = (),
    ) -> None:
        """Record one dispatched fallback call without persisting error text."""

        normalized_trigger_types = _normalized_error_types(trigger_error_types)
        if not normalized_trigger_types:
            raise ValueError("trigger_error_types must not be empty")
        normalized_status = str(fallback_call_status or "").strip()
        if normalized_status not in {"completed", "error"}:
            raise ValueError("fallback_call_status must be completed or error")
        record = _ModelFallbackRouteRecord(
            scene_name=_required_route_name(scene_name, name="scene_name"),
            primary_model_name=_required_route_name(
                primary_model_name,
                name="primary_model_name",
            ),
            fallback_model_name=_required_route_name(
                fallback_model_name,
                name="fallback_model_name",
            ),
            trigger_error_types=normalized_trigger_types,
            fallback_call_status=normalized_status,
            fallback_error_types=_normalized_error_types(fallback_error_types),
        )
        with self._lock:
            self._model_fallback_routes.append(record)

    def build_model_routing_summary(self) -> dict[str, Any]:
        """Return a deterministic, credential-free fallback routing receipt."""

        with self._lock:
            records = list(self._model_fallback_routes)
        route_counts = Counter(records)
        ordered_routes = sorted(
            route_counts,
            key=lambda record: (
                record.scene_name,
                record.primary_model_name,
                record.fallback_model_name,
                record.trigger_error_types,
                record.fallback_call_status,
                record.fallback_error_types,
            ),
        )
        return {
            "fallback_switch_count": len(records),
            "fallback_call_completed_count": sum(
                1 for record in records if record.fallback_call_status == "completed"
            ),
            "fallback_call_error_count": sum(
                1 for record in records if record.fallback_call_status == "error"
            ),
            "routes": [
                {
                    "scene_name": record.scene_name,
                    "primary_model_name": record.primary_model_name,
                    "fallback_model_name": record.fallback_model_name,
                    "trigger_error_types": list(record.trigger_error_types),
                    "fallback_call_status": record.fallback_call_status,
                    "fallback_error_types": list(record.fallback_error_types),
                    "switch_count": route_counts[record],
                }
                for record in ordered_routes
            ],
        }

    def build_budget_summary(self) -> dict[str, Any]:
        """Return a credential-free snapshot of limits, usage, and any block."""

        with self._lock:
            records = list(self._records)
            block = deepcopy(self._budget_block)
            active_reservation_count = len(self._reservations)
            model_requests = self._budget_model_requests
        usage = _summarize_records(records)
        raw_cost = usage.get("cost")
        cost: Mapping[str, Any] = raw_cost if isinstance(raw_cost, Mapping) else {}
        return {
            "enabled": self._budget_enabled,
            "status": (
                "disabled"
                if not self._budget_enabled
                else "blocked"
                if block is not None
                else "within_budget"
            ),
            "enforcement": "scene_admission_with_actual_usage_settlement",
            "limits": {
                "max_model_requests": self._max_model_requests,
                "max_total_tokens": self._max_total_tokens,
                "max_estimated_cost": (
                    float(self._max_estimated_cost)
                    if self._max_estimated_cost is not None
                    else None
                ),
                "budget_currency": self._budget_currency or None,
            },
            "usage": {
                "scene_call_count": len(records),
                "model_requests": model_requests,
                "total_tokens": usage["total_tokens"],
                "usage_status": usage["usage_status"],
                "estimated_cost": cost.get("known_estimated_cost"),
                "cost_status": cost.get("status"),
                "currency": cost.get("currency"),
            },
            "active_reservation_count": active_reservation_count,
            "projection": {
                "method": "prompt_estimate_plus_output_reserve_and_observed_average",
                "default_output_tokens_per_scene": _DEFAULT_PROJECTED_OUTPUT_TOKENS,
            },
            "block": block,
        }

    def is_budget_blocked(self) -> bool:
        """Return whether any admission or settlement permanently blocked this run."""

        with self._lock:
            return self._budget_block is not None

    def _build_reservation_or_block_locked(
        self,
        *,
        scene_name: str,
        model_name: str,
        model_config: Mapping[str, object],
        prompt_text: str,
    ) -> WriteSceneBudgetReservation | dict[str, Any]:
        prompt_tokens = _estimate_prompt_tokens(prompt_text)
        observed_scene_count = len(self._records)
        observed_tokens = sum(record.usage.total_tokens for record in self._records)
        observed_request_projection = (
            _ceil_div(self._budget_model_requests, observed_scene_count)
            if observed_scene_count > 0
            else 1
        )
        token_projection = max(
            prompt_tokens + _DEFAULT_PROJECTED_OUTPUT_TOKENS,
            _ceil_div(observed_tokens, observed_scene_count)
            if observed_scene_count > 0
            else 0,
        )

        currency: str | None = None
        estimated_cost: Decimal | None = None
        if self._max_estimated_cost is not None:
            projection_usage = ModelUsage(
                request_count=1,
                usage_report_count=1,
                input_tokens=prompt_tokens,
                uncached_input_tokens=prompt_tokens,
                output_tokens=_DEFAULT_PROJECTED_OUTPUT_TOKENS,
                total_tokens=prompt_tokens + _DEFAULT_PROJECTED_OUTPUT_TOKENS,
            )
            currency, estimated_cost = _estimate_cost(
                usage=projection_usage,
                model_config=model_config,
            )
            if estimated_cost is None or currency is None:
                return self._build_block(
                    dimension="estimated_cost",
                    phase="admission",
                    scene_name=scene_name,
                    model_name=model_name,
                    reason=(
                        f"写作估算成本预算无法执行：模型 {model_name} 缺少可审计价格"
                    ),
                    limit=self._max_estimated_cost,
                )
            if currency != self._budget_currency:
                return self._build_block(
                    dimension="estimated_cost",
                    phase="admission",
                    scene_name=scene_name,
                    model_name=model_name,
                    reason=(
                        "写作估算成本预算币种不匹配："
                        f"model={model_name}, pricing={currency}, budget={self._budget_currency}"
                    ),
                    limit=self._max_estimated_cost,
                )
            observed_costs = [
                record.estimated_cost
                for record in self._records
                if record.estimated_cost is not None
            ]
            if observed_costs:
                estimated_cost = max(
                    estimated_cost,
                    sum(observed_costs, Decimal(0)) / Decimal(len(observed_costs)),
                )

        return WriteSceneBudgetReservation(
            reservation_id=self._next_reservation_id,
            model_requests=max(observed_request_projection, 1),
            total_tokens=max(token_projection, 1),
            estimated_cost=estimated_cost,
            currency=currency,
        )

    def _check_settled_usage_locked(
        self,
        *,
        scene_name: str,
        model_name: str,
        usage: ModelUsage,
    ) -> dict[str, Any] | None:
        if self._max_total_tokens is not None or self._max_estimated_cost is not None:
            if usage.request_count <= 0 or usage.usage_report_count != usage.request_count:
                dimension = (
                    "estimated_cost"
                    if self._max_estimated_cost is not None
                    else "total_tokens"
                )
                return self._build_block(
                    dimension=dimension,
                    phase="settlement",
                    scene_name=scene_name,
                    model_name=model_name,
                    reason=(
                        "写作预算无法继续审计：模型调用未返回完整 usage，"
                        f"scene={scene_name}, model={model_name}"
                    ),
                )
        if self._max_estimated_cost is not None:
            current_record = self._records[-1]
            if (
                current_record.estimated_cost is None
                or current_record.currency != self._budget_currency
            ):
                return self._build_block(
                    dimension="estimated_cost",
                    phase="settlement",
                    scene_name=scene_name,
                    model_name=model_name,
                    reason=(
                        "写作估算成本预算无法结算："
                        f"scene={scene_name}, model={model_name}"
                    ),
                    limit=self._max_estimated_cost,
                )
        return self._check_projected_limits_locked(
            phase="settlement",
            scene_name=scene_name,
            model_name=model_name,
            candidate=None,
        )

    def _check_projected_limits_locked(
        self,
        *,
        phase: str,
        scene_name: str,
        model_name: str,
        candidate: WriteSceneBudgetReservation | None,
    ) -> dict[str, Any] | None:
        reservations = list(self._reservations.values())
        if candidate is not None:
            reservations.append(candidate)

        projected_requests = self._budget_model_requests + sum(
            reservation.model_requests for reservation in reservations
        )
        if (
            self._max_model_requests is not None
            and projected_requests > self._max_model_requests
        ):
            return self._build_block(
                dimension="model_requests",
                phase=phase,
                scene_name=scene_name,
                model_name=model_name,
                reason=(
                    "写作模型请求数预算已耗尽："
                    f"projected={projected_requests}, limit={self._max_model_requests}"
                ),
                limit=self._max_model_requests,
                observed=self._budget_model_requests,
                projected=projected_requests,
            )

        actual_tokens = sum(record.usage.total_tokens for record in self._records)
        projected_tokens = actual_tokens + sum(
            reservation.total_tokens for reservation in reservations
        )
        if (
            self._max_total_tokens is not None
            and projected_tokens > self._max_total_tokens
        ):
            return self._build_block(
                dimension="total_tokens",
                phase=phase,
                scene_name=scene_name,
                model_name=model_name,
                reason=(
                    "写作总 Token 预算已耗尽："
                    f"projected={projected_tokens}, limit={self._max_total_tokens}"
                ),
                limit=self._max_total_tokens,
                observed=actual_tokens,
                projected=projected_tokens,
            )

        if self._max_estimated_cost is not None:
            actual_cost = sum(
                (
                    record.estimated_cost
                    for record in self._records
                    if record.estimated_cost is not None
                ),
                Decimal(0),
            )
            reservation_cost = sum(
                (
                    reservation.estimated_cost
                    for reservation in reservations
                    if reservation.estimated_cost is not None
                ),
                Decimal(0),
            )
            projected_cost = actual_cost + reservation_cost
            if projected_cost > self._max_estimated_cost:
                return self._build_block(
                    dimension="estimated_cost",
                    phase=phase,
                    scene_name=scene_name,
                    model_name=model_name,
                    reason=(
                        "写作估算成本预算已耗尽："
                        f"projected={projected_cost}, "
                        f"limit={self._max_estimated_cost} {self._budget_currency}"
                    ),
                    limit=self._max_estimated_cost,
                    observed=actual_cost,
                    projected=projected_cost,
                )
        return None

    def _build_block(
        self,
        *,
        dimension: str,
        phase: str,
        scene_name: str,
        model_name: str,
        reason: str,
        limit: int | Decimal | None = None,
        observed: int | Decimal | None = None,
        projected: int | Decimal | None = None,
    ) -> dict[str, Any]:
        return {
            "dimension": dimension,
            "phase": phase,
            "scene_name": scene_name,
            "model_name": model_name,
            "reason": reason,
            "limit": _json_number(limit),
            "observed": _json_number(observed),
            "projected": _json_number(projected),
        }


__all__ = [
    "WriteBudgetExceededError",
    "WriteModelUsageLedger",
    "WriteSceneBudgetReservation",
    "model_role_for_scene",
    "reprice_model_usage_summary",
    "validate_model_pricing_for_budget",
]
