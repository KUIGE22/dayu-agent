"""Source Sync binding、snapshot 与 payload canonical 契约。

本模块从冻结的 Slice 2.3 WIP 机械拆出 payload 责任闭包，唯一拥有
execution binding/snapshot、manual/scheduled payload、query window、caller
intent fingerprint 以及对应 canonical parser/builder。它只依赖纯领域 owner，
不接触 Fins、Service 或存储实现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TypeAlias
from uuid import UUID

from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantId
from dayu.investment.domain.jobs import CanonicalJobDocument, JsonValue, build_canonical_document
from dayu.investment.domain.source import (
    SourceDefinitionId,
    SourceKind,
    SourceSubscriptionId,
    SubscriptionStatus,
)
from dayu.investment.domain.source_sync import (
    _CANONICAL_TICKER,
    FINS_SOURCE_DEFINITION_KEY,
    MAX_SOURCE_DOCUMENT_BYTES,
    SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME,
    SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
    FinsDisclosureSubscriptionConfig,
    SourceConnectorKey,
    SourcePollingScheduleRequest,
    SourceSyncEnqueueRequest,
    SourceSyncOrigin,
    _decode_source_document,
    _parse_date_text,
    _parse_uuid_text,
    _require_aware_utc,
    _require_canonical_document_size,
    _require_exact_keys,
    _require_exact_type,
    _require_json_object,
    _require_json_positive_int,
    _require_json_schema_version,
    _require_json_text,
    _require_nonblank,
    _require_positive_int,
    _require_sha256,
    parse_fins_disclosure_subscription_config,
)

_MIC = re.compile(r"^[A-Z]{4}$")


@dataclass(frozen=True, slots=True)
class SourceExecutionBinding:
    """锁定的、可执行 Fins security subscription binding。"""

    tenant_id: TenantId
    source_definition_id: SourceDefinitionId
    source_definition_version: int
    source_key: str
    source_kind: SourceKind
    subscription_id: SourceSubscriptionId
    subscription_version: int
    subscription_status: SubscriptionStatus
    security_company_id: CompanyId
    security_id: SecurityId
    security_version: int
    security_ticker: str
    exchange_mic: str
    security_is_active: bool
    connector_key: SourceConnectorKey
    config: FinsDisclosureSubscriptionConfig

    def __post_init__(self) -> None:
        """闭合 executable binding 的全部 identity 与状态。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: binding 不可执行时抛出。
        """

        if not isinstance(self.tenant_id, TenantId):
            raise TypeError("tenant_id 必须是 TenantId")
        if not isinstance(self.source_definition_id, SourceDefinitionId):
            raise TypeError("source_definition_id 必须是 SourceDefinitionId")
        _require_positive_int(self.source_definition_version, "source_definition_version")
        if self.source_key != FINS_SOURCE_DEFINITION_KEY:
            raise ValueError("source_key 不是可执行 Fins key")
        if self.source_kind is not SourceKind.FILING:
            raise ValueError("source_kind 必须是 filing")
        if not isinstance(self.subscription_id, SourceSubscriptionId):
            raise TypeError("subscription_id 必须是 SourceSubscriptionId")
        _require_positive_int(self.subscription_version, "subscription_version")
        if not isinstance(self.subscription_status, SubscriptionStatus):
            raise TypeError("subscription_status 必须是 SubscriptionStatus")
        if not isinstance(self.security_company_id, CompanyId):
            raise TypeError("security_company_id 必须是 CompanyId")
        if not isinstance(self.security_id, SecurityId):
            raise TypeError("security_id 必须是 SecurityId")
        _require_positive_int(self.security_version, "security_version")
        if not isinstance(self.security_ticker, str) or _CANONICAL_TICKER.fullmatch(self.security_ticker) is None:
            raise ValueError("security_ticker 必须是 canonical ticker")
        if not isinstance(self.exchange_mic, str) or _MIC.fullmatch(self.exchange_mic) is None:
            raise ValueError("exchange_mic 必须是四位大写 MIC")
        if type(self.security_is_active) is not bool or not self.security_is_active:
            raise ValueError("security 必须 active")
        if self.connector_key is not SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1:
            raise ValueError("connector_key 不是可执行 Fins connector")
        if not isinstance(self.config, FinsDisclosureSubscriptionConfig):
            raise TypeError("config 必须是 FinsDisclosureSubscriptionConfig")


@dataclass(frozen=True, slots=True)
class SourceExecutionSnapshot:
    """一次 source operation 的不可变执行快照。"""

    binding: SourceExecutionBinding
    canonical_ticker: str
    query_start_date: date
    query_end_date: date

    def __post_init__(self) -> None:
        """校验 ticker identity 与 inclusive query window。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: 窗口或 ticker identity 漂移时抛出。
        """

        if not isinstance(self.binding, SourceExecutionBinding):
            raise TypeError("binding 必须是 SourceExecutionBinding")
        if self.canonical_ticker != self.binding.security_ticker:
            raise ValueError("canonical_ticker 必须等于 binding ticker")
        if type(self.query_start_date) is not date or type(self.query_end_date) is not date:
            raise TypeError("query window 必须使用精确 date")
        expected_days = (self.query_end_date - self.query_start_date).days + 1
        if expected_days != self.binding.config.lookback_days:
            raise ValueError("query window 必须精确覆盖 lookback_days")


@dataclass(frozen=True, slots=True)
class ManualSourceSyncPayload:
    """手工 Source Sync 的 strict parsed payload。"""

    subscription_id: SourceSubscriptionId
    expected_subscription_version: int
    trigger_id: UUID
    execution_snapshot: SourceExecutionSnapshot
    request_fingerprint: str

    def __post_init__(self) -> None:
        """校验 payload identity、version、snapshot 与 fingerprint。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: identity 或 hash 漂移时抛出。
        """

        if not isinstance(self.subscription_id, SourceSubscriptionId):
            raise TypeError("subscription_id 必须是 SourceSubscriptionId")
        _require_positive_int(self.expected_subscription_version, "expected_subscription_version")
        _require_exact_type(self.trigger_id, UUID, "trigger_id")
        if not isinstance(self.execution_snapshot, SourceExecutionSnapshot):
            raise TypeError("execution_snapshot 必须是 SourceExecutionSnapshot")
        if self.subscription_id != self.execution_snapshot.binding.subscription_id:
            raise ValueError("payload subscription 与 snapshot 不一致")
        if self.expected_subscription_version != self.execution_snapshot.binding.subscription_version:
            raise ValueError("payload expected version 与 snapshot 不一致")
        _require_sha256(self.request_fingerprint, "request_fingerprint")


@dataclass(frozen=True, slots=True)
class ScheduledSourceSyncPayload:
    """周期 Source Sync 的 strict static payload。"""

    subscription_id: SourceSubscriptionId
    source_definition_id: SourceDefinitionId
    expected_subscription_version: int
    schedule_key: str
    source_request_fingerprint: str

    def __post_init__(self) -> None:
        """校验 static schedule payload。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: 文本、version 或 hash 非法时抛出。
        """

        if not isinstance(self.subscription_id, SourceSubscriptionId):
            raise TypeError("subscription_id 必须是 SourceSubscriptionId")
        if not isinstance(self.source_definition_id, SourceDefinitionId):
            raise TypeError("source_definition_id 必须是 SourceDefinitionId")
        _require_positive_int(self.expected_subscription_version, "expected_subscription_version")
        _require_nonblank(self.schedule_key, "schedule_key")
        _require_sha256(self.source_request_fingerprint, "source_request_fingerprint")


SourceSyncPayload: TypeAlias = ManualSourceSyncPayload | ScheduledSourceSyncPayload
"""Source Sync payload 的 closed discriminated union。"""


def build_source_query_window(available_at: datetime, lookback_days: int) -> tuple[date, date]:
    """从 durable available_at 生成 inclusive calendar window。

    Args:
        available_at: Job 业务可用时刻。
        lookback_days: Inclusive 天数。

    Returns:
        ``(start_date, end_date)``。

    Raises:
        TypeError: 参数类型非法时抛出。
        ValueError: 时间或范围非法时抛出。
    """

    _require_aware_utc(available_at, "available_at")
    _require_positive_int(lookback_days, "lookback_days")
    if lookback_days > 3660:
        raise ValueError("lookback_days 不得超过 3660")
    end_date = available_at.date()
    return end_date - timedelta(days=lookback_days - 1), end_date


def build_source_execution_snapshot(
    binding: SourceExecutionBinding,
    available_at: datetime,
) -> SourceExecutionSnapshot:
    """从 binding 与 available_at 冻结 execution snapshot。

    Args:
        binding: 锁定的 executable binding。
        available_at: Durable Job 可用时刻。

    Returns:
        不可变 execution snapshot。

    Raises:
        TypeError: 参数类型非法时抛出。
        ValueError: 时间或 binding 非法时抛出。
    """

    if not isinstance(binding, SourceExecutionBinding):
        raise TypeError("binding 必须是 SourceExecutionBinding")
    start_date, end_date = build_source_query_window(available_at, binding.config.lookback_days)
    return SourceExecutionSnapshot(
        binding=binding,
        canonical_ticker=binding.security_ticker,
        query_start_date=start_date,
        query_end_date=end_date,
    )


def build_manual_source_request_fingerprint(request: SourceSyncEnqueueRequest) -> str:
    """按固定 caller-intent 字段生成 manual fingerprint。

    Args:
        request: 手工入队调用意图。

    Returns:
        小写 SHA-256。

    Raises:
        TypeError: request 类型非法时抛出。
    """

    if not isinstance(request, SourceSyncEnqueueRequest):
        raise TypeError("request 必须是 SourceSyncEnqueueRequest")
    document = build_canonical_document(
        {
            "available_at": request.available_at.isoformat(),
            "deadline_at": request.deadline_at.isoformat(),
            "expected_subscription_version": request.expected_subscription_version,
            "schema_version": 1,
            "subscription_id": str(request.subscription_id),
            "trigger_id": str(request.trigger_id),
        },
        schema_name="investment.source-sync-manual-intent",
        schema_version=1,
    )
    return document.sha256


def build_scheduled_source_request_fingerprint(request: SourcePollingScheduleRequest, schedule_key: str) -> str:
    """按固定 caller-intent 字段生成 scheduled fingerprint。

    Args:
        request: Schedule draft 调用意图。
        schedule_key: 已派生或调用方给定的稳定 key。

    Returns:
        小写 SHA-256。

    Raises:
        TypeError: request 类型非法时抛出。
        ValueError: schedule key 非法时抛出。
    """

    if not isinstance(request, SourcePollingScheduleRequest):
        raise TypeError("request 必须是 SourcePollingScheduleRequest")
    _require_nonblank(schedule_key, "schedule_key")
    document = build_canonical_document(
        {
            "cron_expression": request.cron_expression,
            "expected_subscription_version": request.expected_subscription_version,
            "job_deadline_seconds": request.job_deadline_seconds,
            "misfire_grace_seconds": request.misfire_grace_seconds,
            "misfire_policy": request.misfire_policy.value,
            "schedule_key": schedule_key,
            "schema_version": 1,
            "subscription_id": str(request.subscription_id),
            "timezone_name": request.timezone_name,
        },
        schema_name="investment.source-sync-scheduled-intent",
        schema_version=1,
    )
    return document.sha256


def _config_value(config: FinsDisclosureSubscriptionConfig) -> dict[str, JsonValue]:
    """把 strict config 投影为 closed JSON 对象。

    Args:
        config: Fins 配置。

    Returns:
        Closed JSON 对象。

    Raises:
        TypeError: config 类型非法时抛出。
    """

    if not isinstance(config, FinsDisclosureSubscriptionConfig):
        raise TypeError("config 必须是 FinsDisclosureSubscriptionConfig")
    return {
        "disable_after": config.disable_after,
        "failing_after": config.failing_after,
        "forms": list(config.forms),
        "freshness_max_age_days": config.freshness_max_age_days,
        "lookback_days": config.lookback_days,
        "max_documents_per_sync": config.max_documents_per_sync,
    }


def _binding_value(binding: SourceExecutionBinding) -> dict[str, JsonValue]:
    """把 execution binding 投影为 closed JSON 对象。

    Args:
        binding: Strict execution binding。

    Returns:
        Closed JSON 对象。

    Raises:
        TypeError: binding 类型非法时抛出。
    """

    if not isinstance(binding, SourceExecutionBinding):
        raise TypeError("binding 必须是 SourceExecutionBinding")
    return {
        "config": _config_value(binding.config),
        "connector_key": binding.connector_key.value,
        "exchange_mic": binding.exchange_mic,
        "security_company_id": str(binding.security_company_id),
        "security_id": str(binding.security_id),
        "security_is_active": binding.security_is_active,
        "security_ticker": binding.security_ticker,
        "security_version": binding.security_version,
        "source_definition_id": str(binding.source_definition_id),
        "source_definition_version": binding.source_definition_version,
        "source_key": binding.source_key,
        "source_kind": binding.source_kind.value,
        "subscription_id": str(binding.subscription_id),
        "subscription_status": binding.subscription_status.value,
        "subscription_version": binding.subscription_version,
        "tenant_id": str(binding.tenant_id),
    }


def _parse_source_execution_binding(value: JsonValue) -> SourceExecutionBinding:
    """从 closed JSON 解析 execution binding。

    Args:
        value: JSON binding 对象。

    Returns:
        Strict binding DTO。

    Raises:
        ValueError: key、枚举或 identity 非法时抛出。
    """

    raw = _require_json_object(value, "binding")
    _require_exact_keys(
        raw,
        frozenset(
            {
                "tenant_id",
                "source_definition_id",
                "source_definition_version",
                "source_key",
                "source_kind",
                "subscription_id",
                "subscription_version",
                "subscription_status",
                "security_company_id",
                "security_id",
                "security_version",
                "security_ticker",
                "exchange_mic",
                "security_is_active",
                "connector_key",
                "config",
            }
        ),
        "binding",
    )
    security_active = raw["security_is_active"]
    if type(security_active) is not bool:
        raise ValueError("security_is_active 必须是 bool")
    try:
        source_kind = SourceKind(_require_json_text(raw["source_kind"], "source_kind"))
        subscription_status = SubscriptionStatus(_require_json_text(raw["subscription_status"], "subscription_status"))
        connector_key = SourceConnectorKey(_require_json_text(raw["connector_key"], "connector_key"))
    except ValueError:
        raise ValueError("binding closed enum 非法") from None
    return SourceExecutionBinding(
        tenant_id=TenantId(_require_json_text(raw["tenant_id"], "tenant_id")),
        source_definition_id=SourceDefinitionId(
            _require_json_text(raw["source_definition_id"], "source_definition_id")
        ),
        source_definition_version=_require_json_positive_int(
            raw["source_definition_version"],
            "source_definition_version",
        ),
        source_key=_require_json_text(raw["source_key"], "source_key"),
        source_kind=source_kind,
        subscription_id=SourceSubscriptionId(_require_json_text(raw["subscription_id"], "subscription_id")),
        subscription_version=_require_json_positive_int(
            raw["subscription_version"],
            "subscription_version",
        ),
        subscription_status=subscription_status,
        security_company_id=CompanyId(_require_json_text(raw["security_company_id"], "security_company_id")),
        security_id=SecurityId(_require_json_text(raw["security_id"], "security_id")),
        security_version=_require_json_positive_int(raw["security_version"], "security_version"),
        security_ticker=_require_json_text(raw["security_ticker"], "security_ticker"),
        exchange_mic=_require_json_text(raw["exchange_mic"], "exchange_mic"),
        security_is_active=security_active,
        connector_key=connector_key,
        config=parse_fins_disclosure_subscription_config(raw["config"]),
    )


def _snapshot_value(snapshot: SourceExecutionSnapshot) -> dict[str, JsonValue]:
    """把 execution snapshot 投影为 closed JSON 对象。

    Args:
        snapshot: Strict execution snapshot。

    Returns:
        Closed JSON 对象。

    Raises:
        TypeError: snapshot 类型非法时抛出。
    """

    if not isinstance(snapshot, SourceExecutionSnapshot):
        raise TypeError("snapshot 必须是 SourceExecutionSnapshot")
    return {
        "binding": _binding_value(snapshot.binding),
        "canonical_ticker": snapshot.canonical_ticker,
        "query_end_date": snapshot.query_end_date.isoformat(),
        "query_start_date": snapshot.query_start_date.isoformat(),
        "schema_version": 1,
    }


def build_source_execution_snapshot_document(snapshot: SourceExecutionSnapshot) -> CanonicalJobDocument:
    """构建 execution snapshot 的唯一 canonical document。

    Args:
        snapshot: Strict execution snapshot。

    Returns:
        Canonical snapshot document。

    Raises:
        TypeError: snapshot 类型非法时抛出。
    """

    document = build_canonical_document(
        _snapshot_value(snapshot),
        schema_name=SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME,
        schema_version=1,
    )
    _require_canonical_document_size(document, max_bytes=MAX_SOURCE_DOCUMENT_BYTES)
    return document


def parse_source_execution_snapshot_document(document: CanonicalJobDocument) -> SourceExecutionSnapshot:
    """严格解析 execution snapshot canonical document。

    Args:
        document: 待解析 snapshot document。

    Returns:
        Strict execution snapshot。

    Raises:
        ValueError: schema、hash、keys 或字段非法时抛出。
    """

    raw = _decode_source_document(
        document,
        schema_name=SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME,
        schema_version=1,
        max_bytes=MAX_SOURCE_DOCUMENT_BYTES,
    )
    return _parse_source_execution_snapshot_value(raw)


def _parse_source_execution_snapshot_value(value: JsonValue) -> SourceExecutionSnapshot:
    """严格解析 nested execution snapshot JSON 值。

    Args:
        value: Snapshot JSON 对象。

    Returns:
        Strict execution snapshot。

    Raises:
        ValueError: keys 或字段非法时抛出。
    """

    raw = _require_json_object(value, "execution_snapshot")
    _require_exact_keys(
        raw,
        frozenset(
            {
                "schema_version",
                "binding",
                "canonical_ticker",
                "query_start_date",
                "query_end_date",
            }
        ),
        "execution_snapshot",
    )
    _require_json_schema_version(raw["schema_version"], "execution snapshot schema_version")
    return SourceExecutionSnapshot(
        binding=_parse_source_execution_binding(raw["binding"]),
        canonical_ticker=_require_json_text(raw["canonical_ticker"], "canonical_ticker"),
        query_start_date=_parse_date_text(raw["query_start_date"], "query_start_date"),
        query_end_date=_parse_date_text(raw["query_end_date"], "query_end_date"),
    )


def build_manual_source_sync_payload_document(payload: ManualSourceSyncPayload) -> CanonicalJobDocument:
    """构建手工 Source Sync canonical payload。

    Args:
        payload: Strict manual payload。

    Returns:
        Canonical Job payload document。

    Raises:
        TypeError: payload 类型非法时抛出。
    """

    if not isinstance(payload, ManualSourceSyncPayload):
        raise TypeError("payload 必须是 ManualSourceSyncPayload")
    document = build_canonical_document(
        {
            "execution_snapshot": _snapshot_value(payload.execution_snapshot),
            "expected_subscription_version": payload.expected_subscription_version,
            "origin": SourceSyncOrigin.MANUAL.value,
            "request_fingerprint": payload.request_fingerprint,
            "schema_version": 1,
            "subscription_id": str(payload.subscription_id),
            "trigger_id": str(payload.trigger_id),
        },
        schema_name=SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
        schema_version=1,
    )
    _require_canonical_document_size(document, max_bytes=MAX_SOURCE_DOCUMENT_BYTES)
    return document


def build_scheduled_source_sync_payload_document(payload: ScheduledSourceSyncPayload) -> CanonicalJobDocument:
    """构建 scheduled Source Sync canonical payload。

    Args:
        payload: Strict scheduled payload。

    Returns:
        Canonical Job payload document。

    Raises:
        TypeError: payload 类型非法时抛出。
    """

    if not isinstance(payload, ScheduledSourceSyncPayload):
        raise TypeError("payload 必须是 ScheduledSourceSyncPayload")
    document = build_canonical_document(
        {
            "expected_subscription_version": payload.expected_subscription_version,
            "origin": SourceSyncOrigin.SCHEDULED.value,
            "schedule_key": payload.schedule_key,
            "schema_version": 1,
            "source_definition_id": str(payload.source_definition_id),
            "source_request_fingerprint": payload.source_request_fingerprint,
            "subscription_id": str(payload.subscription_id),
        },
        schema_name=SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
        schema_version=1,
    )
    _require_canonical_document_size(document, max_bytes=MAX_SOURCE_DOCUMENT_BYTES)
    return document


def parse_source_sync_payload(document: CanonicalJobDocument) -> SourceSyncPayload:
    """严格解析 Source Sync closed discriminated payload。

    Args:
        document: Durable Job payload document。

    Returns:
        Manual 或 scheduled typed payload。

    Raises:
        ValueError: schema、hash、origin 或字段集非法时抛出。
    """

    raw = _decode_source_document(
        document,
        schema_name=SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
        schema_version=1,
        max_bytes=MAX_SOURCE_DOCUMENT_BYTES,
    )
    _require_json_schema_version(raw.get("schema_version"), "payload schema_version")
    origin = raw.get("origin")
    if origin == SourceSyncOrigin.MANUAL.value:
        _require_exact_keys(
            raw,
            frozenset(
                {
                    "schema_version",
                    "origin",
                    "subscription_id",
                    "expected_subscription_version",
                    "trigger_id",
                    "execution_snapshot",
                    "request_fingerprint",
                }
            ),
            "manual payload",
        )
        return ManualSourceSyncPayload(
            subscription_id=SourceSubscriptionId(_require_json_text(raw["subscription_id"], "subscription_id")),
            expected_subscription_version=_require_json_positive_int(
                raw["expected_subscription_version"],
                "expected_subscription_version",
            ),
            trigger_id=_parse_uuid_text(raw["trigger_id"], "trigger_id"),
            execution_snapshot=_parse_source_execution_snapshot_value(raw["execution_snapshot"]),
            request_fingerprint=_require_json_text(raw["request_fingerprint"], "request_fingerprint"),
        )
    if origin == SourceSyncOrigin.SCHEDULED.value:
        _require_exact_keys(
            raw,
            frozenset(
                {
                    "schema_version",
                    "origin",
                    "subscription_id",
                    "source_definition_id",
                    "expected_subscription_version",
                    "schedule_key",
                    "source_request_fingerprint",
                }
            ),
            "scheduled payload",
        )
        return ScheduledSourceSyncPayload(
            subscription_id=SourceSubscriptionId(_require_json_text(raw["subscription_id"], "subscription_id")),
            source_definition_id=SourceDefinitionId(
                _require_json_text(raw["source_definition_id"], "source_definition_id")
            ),
            expected_subscription_version=_require_json_positive_int(
                raw["expected_subscription_version"],
                "expected_subscription_version",
            ),
            schedule_key=_require_json_text(raw["schedule_key"], "schedule_key"),
            source_request_fingerprint=_require_json_text(
                raw["source_request_fingerprint"],
                "source_request_fingerprint",
            ),
        )
    raise ValueError("payload origin 不在 closed union")


__all__ = [
    "ManualSourceSyncPayload",
    "ScheduledSourceSyncPayload",
    "SourceExecutionBinding",
    "SourceExecutionSnapshot",
    "SourceSyncPayload",
    "build_manual_source_request_fingerprint",
    "build_manual_source_sync_payload_document",
    "build_scheduled_source_request_fingerprint",
    "build_scheduled_source_sync_payload_document",
    "build_source_execution_snapshot",
    "build_source_execution_snapshot_document",
    "build_source_query_window",
    "parse_source_execution_snapshot_document",
    "parse_source_sync_payload",
]
