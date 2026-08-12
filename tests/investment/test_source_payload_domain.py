"""Source Sync binding、snapshot 与 payload owner 的直接测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

import dayu.investment.domain.source_payload as source_payload_module
from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantId
from dayu.investment.domain.jobs import JsonValue, build_canonical_document
from dayu.investment.domain.schedules import ScheduleMisfirePolicy
from dayu.investment.domain.source import (
    SourceDefinitionId,
    SourceKind,
    SourceSubscriptionId,
    SubscriptionStatus,
)
from dayu.investment.domain.source_payload import (
    ManualSourceSyncPayload,
    ScheduledSourceSyncPayload,
    SourceExecutionBinding,
    SourceExecutionSnapshot,
    _binding_value,
    _snapshot_value,
    build_manual_source_request_fingerprint,
    build_manual_source_sync_payload_document,
    build_scheduled_source_request_fingerprint,
    build_scheduled_source_sync_payload_document,
    build_source_execution_snapshot,
    build_source_execution_snapshot_document,
    build_source_query_window,
    parse_source_execution_snapshot_document,
    parse_source_sync_payload,
)
from dayu.investment.domain.source_sync import (
    FINS_SOURCE_DEFINITION_KEY,
    MAX_SOURCE_DOCUMENT_BYTES,
    SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME,
    SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
    FinsDisclosureSubscriptionConfig,
    SourceConnectorKey,
    SourcePollingScheduleRequest,
    SourceSyncEnqueueRequest,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_AVAILABLE_AT = datetime(2026, 3, 1, 0, 5, tzinfo=_UTC)
_TENANT_ID = TenantId("tenant-source-payload")
_DEFINITION_ID = SourceDefinitionId("00000000-0000-4000-8000-000000000011")
_SUBSCRIPTION_ID = SourceSubscriptionId("00000000-0000-4000-8000-000000000012")
_COMPANY_ID = CompanyId("company-source-payload")
_SECURITY_ID = SecurityId("security-source-payload")


def _config() -> FinsDisclosureSubscriptionConfig:
    """返回可执行 binding 使用的 strict 配置。"""

    return FinsDisclosureSubscriptionConfig(
        forms=("10-K", "10-Q"),
        lookback_days=3,
        freshness_max_age_days=7,
        failing_after=2,
        disable_after=4,
        max_documents_per_sync=100,
    )


def _binding(*, status: SubscriptionStatus = SubscriptionStatus.ENABLED) -> SourceExecutionBinding:
    """返回稳定的可执行 Fins binding。"""

    return SourceExecutionBinding(
        tenant_id=_TENANT_ID,
        source_definition_id=_DEFINITION_ID,
        source_definition_version=4,
        source_key=FINS_SOURCE_DEFINITION_KEY,
        source_kind=SourceKind.FILING,
        subscription_id=_SUBSCRIPTION_ID,
        subscription_version=6,
        subscription_status=status,
        security_company_id=_COMPANY_ID,
        security_id=_SECURITY_ID,
        security_version=5,
        security_ticker="BRK.B",
        exchange_mic="XNYS",
        security_is_active=True,
        connector_key=SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1,
        config=_config(),
    )


def _snapshot() -> SourceExecutionSnapshot:
    """返回由 available_at 唯一冻结的 snapshot。"""

    return build_source_execution_snapshot(_binding(), _AVAILABLE_AT)


def _enqueue_request() -> SourceSyncEnqueueRequest:
    """返回 manual caller intent。"""

    return SourceSyncEnqueueRequest(
        subscription_id=_SUBSCRIPTION_ID,
        expected_subscription_version=6,
        trigger_id=UUID("00000000-0000-4000-8000-000000000013"),
        available_at=_AVAILABLE_AT,
        deadline_at=_AVAILABLE_AT + timedelta(hours=2),
    )


def _schedule_request() -> SourcePollingScheduleRequest:
    """返回 scheduled caller intent。"""

    return SourcePollingScheduleRequest(
        subscription_id=_SUBSCRIPTION_ID,
        expected_subscription_version=6,
        cron_expression="0 6 * * *",
        timezone_name="Asia/Shanghai",
        misfire_policy=ScheduleMisfirePolicy.COALESCE_ONE,
        misfire_grace_seconds=120,
        job_deadline_seconds=900,
    )


def _manual_payload() -> ManualSourceSyncPayload:
    """返回合法 manual payload。"""

    request = _enqueue_request()
    return ManualSourceSyncPayload(
        subscription_id=request.subscription_id,
        expected_subscription_version=request.expected_subscription_version,
        trigger_id=request.trigger_id,
        execution_snapshot=_snapshot(),
        request_fingerprint=build_manual_source_request_fingerprint(request),
    )


def _scheduled_payload() -> ScheduledSourceSyncPayload:
    """返回合法 scheduled payload。"""

    request = _schedule_request()
    return ScheduledSourceSyncPayload(
        subscription_id=request.subscription_id,
        source_definition_id=_DEFINITION_ID,
        expected_subscription_version=request.expected_subscription_version,
        schedule_key="source:daily:brk-b",
        source_request_fingerprint=build_scheduled_source_request_fingerprint(
            request,
            "source:daily:brk-b",
        ),
    )


def _payload_document(value: dict[str, JsonValue]):
    """构造可交给 payload parser 的 canonical 文档。"""

    return build_canonical_document(
        value,
        schema_name=SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
        schema_version=1,
    )


def test_binding_fields_frozen_slots_and_disabled_snapshot_are_exact() -> None:
    """Binding 精确持有计划字段，且 disabled subscription 仍可冻结。"""

    binding = _binding(status=SubscriptionStatus.DISABLED)
    assert tuple(field.name for field in fields(binding)) == (
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
    )
    assert binding.subscription_status is SubscriptionStatus.DISABLED
    with pytest.raises(FrozenInstanceError):
        setattr(binding, "security_ticker", "AAPL")


@pytest.mark.parametrize(
    "invalid",
    [
        {"source_definition_version": 0},
        {"source_key": "rss.v1"},
        {"source_kind": SourceKind.ANNOUNCEMENT},
        {"subscription_version": True},
        {"security_version": 0},
        {"security_ticker": "brk.b"},
        {"security_ticker": " BRK.B"},
        {"exchange_mic": "XNAS "},
        {"exchange_mic": "xnas"},
        {"security_is_active": False},
        {"security_is_active": 1},
        {"connector_key": SourceConnectorKey.RSS_V1},
    ],
)
def test_binding_rejects_non_executable_identity_and_shape(invalid: dict[str, JsonValue]) -> None:
    """Binding 对非 Fins identity、inactive security 与非 canonical ticker/MIC 关闭。"""

    with pytest.raises((TypeError, ValueError)):
        replace(_binding(), **invalid)


def test_query_window_is_inclusive_calendar_arithmetic_and_independent_of_deadline() -> None:
    """窗口只由 available_at 与 lookback 决定，跨月及闰日保持 inclusive。"""

    assert build_source_query_window(datetime(2024, 3, 1, tzinfo=_UTC), 1) == (
        date(2024, 3, 1),
        date(2024, 3, 1),
    )
    assert build_source_query_window(datetime(2024, 3, 1, tzinfo=_UTC), 3) == (
        date(2024, 2, 28),
        date(2024, 3, 1),
    )
    request = _enqueue_request()
    moved_deadline = replace(request, deadline_at=request.deadline_at + timedelta(days=5))
    assert build_source_execution_snapshot(_binding(), request.available_at) == build_source_execution_snapshot(
        _binding(),
        moved_deadline.available_at,
    )
    for available_at, lookback in (
        (_AVAILABLE_AT.replace(tzinfo=None), 3),
        (_AVAILABLE_AT, 0),
        (_AVAILABLE_AT, True),
        (_AVAILABLE_AT, 3661),
    ):
        with pytest.raises((TypeError, ValueError)):
            build_source_query_window(available_at, lookback)


def test_snapshot_requires_ticker_identity_and_exact_inclusive_days() -> None:
    """Snapshot 必须与 binding ticker 相等且精确覆盖 lookback 天数。"""

    snapshot = _snapshot()
    assert snapshot.canonical_ticker == "BRK.B"
    assert snapshot.query_start_date == date(2026, 2, 27)
    assert snapshot.query_end_date == date(2026, 3, 1)
    for invalid in (
        {"canonical_ticker": "AAPL"},
        {"query_start_date": date(2026, 2, 28)},
        {"query_end_date": date(2026, 2, 28)},
        {"query_start_date": _AVAILABLE_AT},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(snapshot, **invalid)


def test_manual_and_scheduled_fingerprints_are_deterministic_and_cover_only_caller_intent() -> None:
    """Fingerprint 必须 deterministic，并对每个 caller-intent 漂移敏感。"""

    manual = _enqueue_request()
    baseline = build_manual_source_request_fingerprint(manual)
    assert baseline == build_manual_source_request_fingerprint(manual)
    assert len(baseline) == 64
    for drift in (
        {"expected_subscription_version": 7},
        {"trigger_id": UUID("00000000-0000-4000-8000-000000000014")},
        {"available_at": manual.available_at + timedelta(seconds=1)},
        {"deadline_at": manual.deadline_at + timedelta(seconds=1)},
    ):
        assert build_manual_source_request_fingerprint(replace(manual, **drift)) != baseline

    scheduled = _schedule_request()
    schedule_baseline = build_scheduled_source_request_fingerprint(scheduled, "source:daily:brk-b")
    assert schedule_baseline == build_scheduled_source_request_fingerprint(scheduled, "source:daily:brk-b")
    assert build_scheduled_source_request_fingerprint(scheduled, "source:daily:other") != schedule_baseline
    for drift in (
        {"cron_expression": "30 6 * * *"},
        {"timezone_name": "UTC"},
        {"misfire_grace_seconds": 121},
        {"job_deadline_seconds": 901},
    ):
        assert (
            build_scheduled_source_request_fingerprint(
                replace(scheduled, **drift),
                "source:daily:brk-b",
            )
            != schedule_baseline
        )
    with pytest.raises(ValueError):
        build_scheduled_source_request_fingerprint(scheduled, " ")


def test_payload_dtos_reject_cross_identity_version_and_hash_drift() -> None:
    """Payload DTO 构造期必须闭合 snapshot identity、version 与 hash。"""

    manual = _manual_payload()
    assert tuple(field.name for field in fields(manual)) == (
        "subscription_id",
        "expected_subscription_version",
        "trigger_id",
        "execution_snapshot",
        "request_fingerprint",
    )
    for invalid in (
        {"subscription_id": SourceSubscriptionId("00000000-0000-4000-8000-000000000015")},
        {"expected_subscription_version": 7},
        {"request_fingerprint": "A" * 64},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(manual, **invalid)

    scheduled = _scheduled_payload()
    assert tuple(field.name for field in fields(scheduled)) == (
        "subscription_id",
        "source_definition_id",
        "expected_subscription_version",
        "schedule_key",
        "source_request_fingerprint",
    )
    for invalid in (
        {"expected_subscription_version": 0},
        {"schedule_key": " daily"},
        {"source_request_fingerprint": "bad"},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(scheduled, **invalid)


def test_snapshot_manual_and_scheduled_documents_round_trip_exactly() -> None:
    """三个 canonical builder/parser 必须返回完整 strict DTO。"""

    snapshot = _snapshot()
    snapshot_document = build_source_execution_snapshot_document(snapshot)
    assert snapshot_document.schema_name == SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME
    assert parse_source_execution_snapshot_document(snapshot_document) == snapshot

    manual = _manual_payload()
    manual_document = build_manual_source_sync_payload_document(manual)
    assert manual_document.schema_name == SOURCE_SYNC_PAYLOAD_SCHEMA_NAME
    assert parse_source_sync_payload(manual_document) == manual

    scheduled = _scheduled_payload()
    scheduled_document = build_scheduled_source_sync_payload_document(scheduled)
    assert scheduled_document.schema_name == SOURCE_SYNC_PAYLOAD_SCHEMA_NAME
    assert parse_source_sync_payload(scheduled_document) == scheduled


def test_snapshot_manual_and_scheduled_builders_enforce_exact_and_one_over_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三个 durable builder 必须在返回前执行与 parser 对称的 size cap。"""

    snapshot = _snapshot()
    snapshot_document = build_source_execution_snapshot_document(snapshot)
    monkeypatch.setattr(
        source_payload_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(snapshot_document.canonical_bytes),
    )
    exact_snapshot = build_source_execution_snapshot_document(snapshot)
    assert parse_source_execution_snapshot_document(exact_snapshot) == snapshot
    monkeypatch.setattr(
        source_payload_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(snapshot_document.canonical_bytes) - 1,
    )
    with pytest.raises(ValueError):
        build_source_execution_snapshot_document(snapshot)

    manual = _manual_payload()
    monkeypatch.setattr(source_payload_module, "MAX_SOURCE_DOCUMENT_BYTES", MAX_SOURCE_DOCUMENT_BYTES)
    manual_document = build_manual_source_sync_payload_document(manual)
    monkeypatch.setattr(
        source_payload_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(manual_document.canonical_bytes),
    )
    exact_manual = build_manual_source_sync_payload_document(manual)
    assert parse_source_sync_payload(exact_manual) == manual
    monkeypatch.setattr(
        source_payload_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(manual_document.canonical_bytes) - 1,
    )
    with pytest.raises(ValueError):
        build_manual_source_sync_payload_document(manual)

    scheduled = _scheduled_payload()
    monkeypatch.setattr(source_payload_module, "MAX_SOURCE_DOCUMENT_BYTES", MAX_SOURCE_DOCUMENT_BYTES)
    scheduled_document = build_scheduled_source_sync_payload_document(scheduled)
    monkeypatch.setattr(
        source_payload_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(scheduled_document.canonical_bytes),
    )
    exact_scheduled = build_scheduled_source_sync_payload_document(scheduled)
    assert parse_source_sync_payload(exact_scheduled) == scheduled
    monkeypatch.setattr(
        source_payload_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(scheduled_document.canonical_bytes) - 1,
    )
    with pytest.raises(ValueError):
        build_scheduled_source_sync_payload_document(scheduled)


def test_snapshot_parser_rejects_unknown_missing_schema_enum_and_nested_shape_drift() -> None:
    """Snapshot parser 对 exact keys、版本、enum 与 nested binding 漂移 fail closed。"""

    value = _snapshot_value(_snapshot())
    unknown = dict(value)
    unknown["unknown"] = True
    missing = dict(value)
    missing.pop("canonical_ticker")
    wrong_version = dict(value)
    wrong_version["schema_version"] = 2
    bool_version = dict(value)
    bool_version["schema_version"] = True
    wrong_binding = dict(value)
    binding = _binding_value(_binding())
    binding["connector_key"] = "rss.v1"
    wrong_binding["binding"] = binding
    for invalid in (unknown, missing, wrong_version, bool_version, wrong_binding):
        document = build_canonical_document(
            invalid,
            schema_name=SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME,
            schema_version=1,
        )
        with pytest.raises(ValueError):
            parse_source_execution_snapshot_document(document)


def test_payload_parser_rejects_discriminant_key_type_and_nested_snapshot_drift() -> None:
    """Payload parser 必须按 origin exact 分流并拒绝 unknown/missing/type 漂移。"""

    manual = _manual_payload()
    manual_value: dict[str, JsonValue] = {
        "execution_snapshot": _snapshot_value(manual.execution_snapshot),
        "expected_subscription_version": manual.expected_subscription_version,
        "origin": "manual",
        "request_fingerprint": manual.request_fingerprint,
        "schema_version": 1,
        "subscription_id": str(manual.subscription_id),
        "trigger_id": str(manual.trigger_id),
    }
    scheduled = _scheduled_payload()
    scheduled_value: dict[str, JsonValue] = {
        "expected_subscription_version": scheduled.expected_subscription_version,
        "origin": "scheduled",
        "schedule_key": scheduled.schedule_key,
        "schema_version": 1,
        "source_definition_id": str(scheduled.source_definition_id),
        "source_request_fingerprint": scheduled.source_request_fingerprint,
        "subscription_id": str(scheduled.subscription_id),
    }

    cases: list[dict[str, JsonValue]] = []
    for base, key, value in (
        (manual_value, "unknown", True),
        (manual_value, "origin", "rss"),
        (manual_value, "schema_version", 2),
        (manual_value, "schema_version", True),
        (manual_value, "expected_subscription_version", True),
        (manual_value, "trigger_id", "not-a-uuid"),
        (manual_value, "request_fingerprint", "bad"),
        (scheduled_value, "unknown", True),
        (scheduled_value, "schedule_key", " "),
        (scheduled_value, "source_definition_id", "not-a-uuid"),
    ):
        invalid = dict(base)
        invalid[key] = value
        cases.append(invalid)
    missing_manual = dict(manual_value)
    missing_manual.pop("trigger_id")
    cases.append(missing_manual)
    missing_scheduled = dict(scheduled_value)
    missing_scheduled.pop("schedule_key")
    cases.append(missing_scheduled)
    nested_drift = dict(manual_value)
    snapshot_value = _snapshot_value(manual.execution_snapshot)
    snapshot_value["canonical_ticker"] = "AAPL"
    nested_drift["execution_snapshot"] = snapshot_value
    cases.append(nested_drift)

    for invalid in cases:
        with pytest.raises(ValueError):
            parse_source_sync_payload(_payload_document(invalid))
