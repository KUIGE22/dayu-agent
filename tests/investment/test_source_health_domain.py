"""Source Sync health、snapshot 与 alert owner 的直接测试。"""

from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

import dayu.investment.domain.source_health as source_health_module
from dayu.investment.domain.identifiers import TenantId
from dayu.investment.domain.jobs import build_canonical_document
from dayu.investment.domain.source import SourceSubscriptionId
from dayu.investment.domain.source_health import (
    HEALTH_ERRORS,
    MAX_SOURCE_ALERT_EVENT_BYTES,
    SOURCE_HEALTH_ALERT_SCHEMA_NAME,
    SourceAlertKind,
    SourceAlertOutboxEvent,
    SourceHealthProjection,
    SourceHealthReenableRequest,
    SourceHealthSnapshotCursor,
    SourceHealthSnapshotPage,
    SourceHealthSnapshotProjection,
    SourceHealthStatus,
    build_source_alert_outbox_event,
    build_source_health_transition,
    is_source_observation_stale,
)
from dayu.investment.domain.source_sync import (
    FinsDisclosureSubscriptionConfig,
    SourceSyncErrorCode,
    SourceSyncOutcome,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_NOW = datetime(2026, 8, 12, 9, 30, tzinfo=_UTC)
_TENANT_ID = TenantId("tenant-source-health")
_SUBSCRIPTION_ID = SourceSubscriptionId("00000000-0000-4000-8000-000000000031")
_RUN_ID = UUID("00000000-0000-4000-8000-000000000032")


def _config(*, failing_after: int = 2, disable_after: int = 4) -> FinsDisclosureSubscriptionConfig:
    """返回 health transition 使用的 strict 配置。"""

    return FinsDisclosureSubscriptionConfig(
        forms=("10-K",),
        lookback_days=30,
        freshness_max_age_days=7,
        failing_after=failing_after,
        disable_after=disable_after,
    )


def _virtual_health() -> SourceHealthProjection:
    """返回无持久 row 的 virtual healthy head。"""

    return SourceHealthProjection(
        tenant_id=_TENANT_ID,
        subscription_id=_SUBSCRIPTION_ID,
        status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
        safe_error_code=None,
        version=0,
        last_source_sync_run_id=None,
        observed_at=None,
    )


def _health(
    *,
    status: SourceHealthStatus = SourceHealthStatus.DEGRADED,
    failures: int = 1,
    error: SourceSyncErrorCode | None = SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
    version: int = 1,
    run_id: UUID = _RUN_ID,
    observed_at: datetime = _NOW,
) -> SourceHealthProjection:
    """返回合法 persisted health head。"""

    return SourceHealthProjection(
        tenant_id=_TENANT_ID,
        subscription_id=_SUBSCRIPTION_ID,
        status=status,
        consecutive_failures=failures,
        safe_error_code=error,
        version=version,
        last_source_sync_run_id=run_id,
        observed_at=observed_at,
    )


def _provider_snapshot(
    *,
    status: SourceHealthStatus = SourceHealthStatus.DEGRADED,
    failures: int = 1,
    error: SourceSyncErrorCode = SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
    snapshot_id: UUID = UUID("00000000-0000-4000-8000-000000000033"),
    version: int = 1,
    observed_at: datetime = _NOW,
) -> SourceHealthSnapshotProjection:
    """返回 alert 可引用的 provider snapshot。"""

    return SourceHealthSnapshotProjection(
        snapshot_id=snapshot_id,
        tenant_id=_TENANT_ID,
        subscription_id=_SUBSCRIPTION_ID,
        source_sync_run_id=_RUN_ID,
        health_state_version=version,
        status=status,
        consecutive_failures=failures,
        latency_ms=125,
        safe_error_code=error,
        observed_at=observed_at,
        created_at=observed_at,
    )


def test_health_constants_enums_and_reenable_request_are_exact() -> None:
    """Health 常量、closed enum 与 re-enable request 字段必须精确。"""

    assert SOURCE_HEALTH_ALERT_SCHEMA_NAME == "investment.source-health-alert"
    assert MAX_SOURCE_ALERT_EVENT_BYTES == 1_048_576
    assert HEALTH_ERRORS == {
        SourceSyncErrorCode.PARTIAL_BATCH,
        SourceSyncErrorCode.UNSUPPORTED_MARKET,
        SourceSyncErrorCode.UNSUPPORTED_FORM,
        SourceSyncErrorCode.STALE_DATA,
        SourceSyncErrorCode.PROVIDER_RATE_LIMITED,
        SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        SourceSyncErrorCode.FINS_INVARIANT,
    }
    assert {member.value for member in SourceHealthStatus} == {"healthy", "degraded", "failing", "disabled"}
    assert {member.value for member in SourceAlertKind} == {"degraded", "failing", "disabled"}
    request = SourceHealthReenableRequest(_SUBSCRIPTION_ID, 3)
    assert tuple(field.name for field in fields(request)) == ("subscription_id", "expected_health_version")
    with pytest.raises((TypeError, ValueError)):
        SourceHealthReenableRequest(_SUBSCRIPTION_ID, 0)


def test_health_projection_closes_virtual_persisted_status_and_presence_matrices() -> None:
    """Health head 必须区分唯一 virtual shape 与 persisted closed status shape。"""

    virtual = _virtual_health()
    assert tuple(field.name for field in fields(virtual)) == (
        "tenant_id",
        "subscription_id",
        "status",
        "consecutive_failures",
        "safe_error_code",
        "version",
        "last_source_sync_run_id",
        "observed_at",
    )
    healthy = _health(status=SourceHealthStatus.HEALTHY, failures=0, error=None)
    assert healthy.version == 1
    with pytest.raises(FrozenInstanceError):
        setattr(healthy, "version", 2)
    invalid = (
        {"status": SourceHealthStatus.DEGRADED, "consecutive_failures": 1, "safe_error_code": None},
        {"status": SourceHealthStatus.HEALTHY, "consecutive_failures": 1},
        {"status": SourceHealthStatus.HEALTHY, "safe_error_code": SourceSyncErrorCode.PARTIAL_BATCH},
        {"safe_error_code": SourceSyncErrorCode.STALE_SUBSCRIPTION},
        {"version": 0},
        {"last_source_sync_run_id": None},
        {"observed_at": None},
        {"observed_at": _NOW.replace(tzinfo=None)},
    )
    for drift in invalid:
        with pytest.raises((TypeError, ValueError)):
            replace(_health(), **drift)
    with pytest.raises(ValueError):
        replace(virtual, last_source_sync_run_id=_RUN_ID)


def test_health_snapshot_accepts_provider_operator_and_legacy_shapes() -> None:
    """Snapshot 接受 provider、operator re-enable 与 legacy 三种计划形态。"""

    provider = _provider_snapshot()
    operator = SourceHealthSnapshotProjection(
        snapshot_id=UUID("00000000-0000-4000-8000-000000000034"),
        tenant_id=_TENANT_ID,
        subscription_id=_SUBSCRIPTION_ID,
        source_sync_run_id=None,
        health_state_version=2,
        status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
        latency_ms=None,
        safe_error_code=None,
        observed_at=_NOW + timedelta(seconds=1),
        created_at=_NOW + timedelta(seconds=1),
    )
    legacy = replace(
        provider,
        health_state_version=None,
        created_at=provider.observed_at + timedelta(days=1),
    )
    assert provider.health_state_version == 1
    assert operator.source_sync_run_id is None
    assert legacy.health_state_version is None
    assert legacy.created_at != legacy.observed_at
    for invalid in (
        {"created_at": _NOW + timedelta(microseconds=1)},
        {"health_state_version": 0},
        {"latency_ms": None},
        {"latency_ms": -1},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(provider, **invalid)
    for invalid in (
        {"latency_ms": 0},
        {
            "status": SourceHealthStatus.DEGRADED,
            "consecutive_failures": 1,
            "safe_error_code": SourceSyncErrorCode.PARTIAL_BATCH,
        },
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(operator, **invalid)
    with pytest.raises(ValueError):
        replace(legacy, observed_at=legacy.observed_at.replace(tzinfo=None))
    with pytest.raises(ValueError):
        replace(legacy, created_at=legacy.created_at.replace(tzinfo=None))


def test_snapshot_page_enforces_descending_unique_order_and_tail_cursor() -> None:
    """Snapshot page 必须按 observed_at/snapshot_id descending 且 cursor 指向页尾。"""

    first = _provider_snapshot(
        snapshot_id=UUID("00000000-0000-4000-8000-000000000035"),
        observed_at=_NOW + timedelta(seconds=1),
    )
    second = _provider_snapshot(snapshot_id=UUID("00000000-0000-4000-8000-000000000034"))
    cursor = SourceHealthSnapshotCursor(observed_at=second.observed_at, snapshot_id=second.snapshot_id)
    page = SourceHealthSnapshotPage(snapshots=(first, second), next_cursor=cursor)
    assert page.snapshots == (first, second)
    with pytest.raises(ValueError):
        SourceHealthSnapshotPage(snapshots=(second, first), next_cursor=None)
    with pytest.raises(ValueError):
        SourceHealthSnapshotPage(snapshots=(first, first), next_cursor=None)
    with pytest.raises(ValueError):
        SourceHealthSnapshotPage(snapshots=(), next_cursor=cursor)
    with pytest.raises(ValueError):
        SourceHealthSnapshotPage(
            snapshots=(first, second),
            next_cursor=SourceHealthSnapshotCursor(first.observed_at, first.snapshot_id),
        )
    with pytest.raises(ValueError):
        SourceHealthSnapshotCursor(_NOW.replace(tzinfo=None), first.snapshot_id)


def test_freshness_uses_calendar_days_accepts_exact_max_and_exempts_empty_no_change() -> None:
    """Freshness 使用 authoritative calendar date，exact max 接受且空 no-change 豁免。"""

    assert not is_source_observation_stale(
        outcome=SourceSyncOutcome.NO_CHANGE,
        latest_source_observed_date=None,
        authoritative_utc_date=date(2026, 8, 12),
        freshness_max_age_days=7,
    )
    assert not is_source_observation_stale(
        outcome=SourceSyncOutcome.SUCCEEDED,
        latest_source_observed_date=date(2026, 8, 5),
        authoritative_utc_date=date(2026, 8, 12),
        freshness_max_age_days=7,
    )
    assert is_source_observation_stale(
        outcome=SourceSyncOutcome.PARTIAL,
        latest_source_observed_date=date(2026, 8, 4),
        authoritative_utc_date=date(2026, 8, 12),
        freshness_max_age_days=7,
    )
    invalid_calls = (
        lambda: is_source_observation_stale(
            outcome=SourceSyncOutcome.NO_CHANGE,
            latest_source_observed_date=date(2026, 8, 12),
            authoritative_utc_date=date(2026, 8, 12),
            freshness_max_age_days=7,
        ),
        lambda: is_source_observation_stale(
            outcome=SourceSyncOutcome.SUCCEEDED,
            latest_source_observed_date=None,
            authoritative_utc_date=date(2026, 8, 12),
            freshness_max_age_days=7,
        ),
        lambda: is_source_observation_stale(
            outcome=SourceSyncOutcome.SUCCEEDED,
            latest_source_observed_date=date(2026, 8, 12),
            authoritative_utc_date=_NOW,
            freshness_max_age_days=7,
        ),
        lambda: is_source_observation_stale(
            outcome=SourceSyncOutcome.SUCCEEDED,
            latest_source_observed_date=date(2026, 8, 12),
            authoritative_utc_date=date(2026, 8, 12),
            freshness_max_age_days=3661,
        ),
    )
    for invalid_call in invalid_calls:
        with pytest.raises((TypeError, ValueError)):
            invalid_call()


def test_health_transition_covers_success_degraded_failing_disabled_and_sticky_disabled() -> None:
    """Transition 必须按阈值推进并使 disabled 对晚到 observation sticky。"""

    healthy, healthy_alert = build_source_health_transition(
        current=_virtual_health(),
        outcome=SourceSyncOutcome.SUCCEEDED,
        safe_error_code=None,
        config=_config(),
        source_sync_run_id=_RUN_ID,
        observed_at=_NOW,
    )
    assert healthy.status is SourceHealthStatus.HEALTHY
    assert healthy.version == 1
    assert healthy_alert is None

    degraded, degraded_alert = build_source_health_transition(
        current=healthy,
        outcome=SourceSyncOutcome.FAILED,
        safe_error_code=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        config=_config(),
        source_sync_run_id=UUID("00000000-0000-4000-8000-000000000036"),
        observed_at=_NOW + timedelta(seconds=1),
    )
    assert (degraded.status, degraded.consecutive_failures, degraded_alert) == (
        SourceHealthStatus.DEGRADED,
        1,
        SourceAlertKind.DEGRADED,
    )
    failing, failing_alert = build_source_health_transition(
        current=degraded,
        outcome=SourceSyncOutcome.PARTIAL,
        safe_error_code=SourceSyncErrorCode.PARTIAL_BATCH,
        config=_config(),
        source_sync_run_id=UUID("00000000-0000-4000-8000-000000000037"),
        observed_at=_NOW + timedelta(seconds=2),
    )
    assert (failing.status, failing.consecutive_failures, failing_alert) == (
        SourceHealthStatus.FAILING,
        2,
        SourceAlertKind.FAILING,
    )
    almost_disabled = replace(failing, consecutive_failures=3, version=3)
    disabled, disabled_alert = build_source_health_transition(
        current=almost_disabled,
        outcome=SourceSyncOutcome.FAILED,
        safe_error_code=SourceSyncErrorCode.FINS_INVARIANT,
        config=_config(),
        source_sync_run_id=UUID("00000000-0000-4000-8000-000000000038"),
        observed_at=_NOW + timedelta(seconds=3),
    )
    assert (disabled.status, disabled.consecutive_failures, disabled_alert) == (
        SourceHealthStatus.DISABLED,
        4,
        SourceAlertKind.DISABLED,
    )
    sticky, sticky_alert = build_source_health_transition(
        current=disabled,
        outcome=SourceSyncOutcome.SUCCEEDED,
        safe_error_code=None,
        config=_config(),
        source_sync_run_id=UUID("00000000-0000-4000-8000-000000000039"),
        observed_at=_NOW + timedelta(seconds=4),
    )
    assert sticky is disabled
    assert sticky_alert is None


def test_health_transition_noops_and_semantic_same_status_alert_rules_are_exact() -> None:
    """Skipped/stale 不推进；同状态同 error 不告警，error 变化才告警。"""

    current = _health()
    skipped = build_source_health_transition(
        current=current,
        outcome=SourceSyncOutcome.SKIPPED_DISABLED,
        safe_error_code=None,
        config=_config(),
        source_sync_run_id=_RUN_ID,
        observed_at=_NOW,
    )
    stale = build_source_health_transition(
        current=current,
        outcome=SourceSyncOutcome.STALE_SUBSCRIPTION,
        safe_error_code=SourceSyncErrorCode.STALE_SUBSCRIPTION,
        config=_config(),
        source_sync_run_id=_RUN_ID,
        observed_at=_NOW,
    )
    assert skipped == (current, None)
    assert stale == (current, None)

    same, same_alert = build_source_health_transition(
        current=current,
        outcome=SourceSyncOutcome.FAILED,
        safe_error_code=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        config=_config(failing_after=5, disable_after=8),
        source_sync_run_id=UUID("00000000-0000-4000-8000-000000000040"),
        observed_at=_NOW + timedelta(seconds=1),
    )
    changed, changed_alert = build_source_health_transition(
        current=current,
        outcome=SourceSyncOutcome.FAILED,
        safe_error_code=SourceSyncErrorCode.PROVIDER_RATE_LIMITED,
        config=_config(failing_after=5, disable_after=8),
        source_sync_run_id=UUID("00000000-0000-4000-8000-000000000041"),
        observed_at=_NOW + timedelta(seconds=1),
    )
    assert same.status is SourceHealthStatus.DEGRADED
    assert same_alert is None
    assert changed.status is SourceHealthStatus.DEGRADED
    assert changed_alert is SourceAlertKind.DEGRADED


@pytest.mark.parametrize(
    ("config", "error", "expected_status", "expected_alert"),
    [
        (
            _config(failing_after=5, disable_after=8),
            SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
            SourceHealthStatus.FAILING,
            None,
        ),
        (
            _config(failing_after=5, disable_after=8),
            SourceSyncErrorCode.PROVIDER_RATE_LIMITED,
            SourceHealthStatus.FAILING,
            SourceAlertKind.FAILING,
        ),
        (
            _config(failing_after=1, disable_after=3),
            SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
            SourceHealthStatus.DISABLED,
            SourceAlertKind.DISABLED,
        ),
        (
            _config(failing_after=1, disable_after=3),
            SourceSyncErrorCode.PROVIDER_RATE_LIMITED,
            SourceHealthStatus.DISABLED,
            SourceAlertKind.DISABLED,
        ),
    ],
)
def test_continuing_failure_never_downgrades_severity_when_thresholds_drift(
    config: FinsDisclosureSubscriptionConfig,
    error: SourceSyncErrorCode,
    expected_status: SourceHealthStatus,
    expected_alert: SourceAlertKind | None,
) -> None:
    """持续失败在阈值升降与 error 变化下只能保持或升级 severity。"""

    current = _health(
        status=SourceHealthStatus.FAILING,
        failures=2,
        error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
    )
    after, alert = build_source_health_transition(
        current=current,
        outcome=SourceSyncOutcome.FAILED,
        safe_error_code=error,
        config=config,
        source_sync_run_id=UUID("00000000-0000-4000-8000-000000000044"),
        observed_at=_NOW + timedelta(seconds=1),
    )
    assert after.status is expected_status
    assert after.consecutive_failures == 3
    assert after.version == current.version + 1
    assert alert is expected_alert


@pytest.mark.parametrize(
    ("outcome", "error"),
    [
        (SourceSyncOutcome.SUCCEEDED, SourceSyncErrorCode.PROVIDER_UNAVAILABLE),
        (SourceSyncOutcome.NO_CHANGE, SourceSyncErrorCode.PARTIAL_BATCH),
        (SourceSyncOutcome.PARTIAL, None),
        (SourceSyncOutcome.PARTIAL, SourceSyncErrorCode.PROVIDER_UNAVAILABLE),
        (SourceSyncOutcome.FAILED, None),
        (SourceSyncOutcome.FAILED, SourceSyncErrorCode.STALE_SUBSCRIPTION),
        (SourceSyncOutcome.SKIPPED_DISABLED, SourceSyncErrorCode.PARTIAL_BATCH),
        (SourceSyncOutcome.STALE_SUBSCRIPTION, None),
    ],
)
def test_health_transition_rejects_outcome_error_matrix_drift(
    outcome: SourceSyncOutcome,
    error: SourceSyncErrorCode | None,
) -> None:
    """Transition 不得猜测非法 outcome/error 组合。"""

    with pytest.raises(ValueError):
        build_source_health_transition(
            current=_virtual_health(),
            outcome=outcome,
            safe_error_code=error,
            config=_config(),
            source_sync_run_id=_RUN_ID,
            observed_at=_NOW,
        )


def test_alert_builder_is_deterministic_exact_and_bound_to_snapshot_time() -> None:
    """Alert event ID、dedupe、body/hash 必须由同一 snapshot transition 唯一派生。"""

    snapshot = _provider_snapshot()
    first = build_source_alert_outbox_event(
        health_snapshot=snapshot,
        alert_kind=SourceAlertKind.DEGRADED,
    )
    second = build_source_alert_outbox_event(
        health_snapshot=snapshot,
        alert_kind=SourceAlertKind.DEGRADED,
    )
    assert first == second
    assert first.created_at == snapshot.observed_at
    assert first.event.schema_name == SOURCE_HEALTH_ALERT_SCHEMA_NAME
    assert first.event.sha256 == second.event.sha256
    assert len(first.dedupe_key) == 64
    raw = json.loads(first.event.canonical_bytes)
    assert set(raw) == {
        "alert_kind",
        "created_at",
        "dedupe_key",
        "event_id",
        "health_snapshot_id",
        "health_state_version",
        "safe_error_code",
        "schema_version",
        "source_sync_run_id",
        "subscription_id",
        "target_status",
        "tenant_id",
    }
    different = build_source_alert_outbox_event(
        health_snapshot=replace(
            snapshot,
            snapshot_id=UUID("00000000-0000-4000-8000-000000000042"),
        ),
        alert_kind=SourceAlertKind.DEGRADED,
    )
    assert different.event_id != first.event_id
    assert different.dedupe_key != first.dedupe_key


def test_alert_builder_enforces_exact_and_one_over_event_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alert durable builder 必须在返回前执行 1 MiB family cap。"""

    snapshot = _provider_snapshot()
    event = build_source_alert_outbox_event(
        health_snapshot=snapshot,
        alert_kind=SourceAlertKind.DEGRADED,
    )
    monkeypatch.setattr(
        source_health_module,
        "MAX_SOURCE_ALERT_EVENT_BYTES",
        len(event.event.canonical_bytes),
    )
    assert (
        build_source_alert_outbox_event(
            health_snapshot=snapshot,
            alert_kind=SourceAlertKind.DEGRADED,
        )
        == event
    )
    monkeypatch.setattr(
        source_health_module,
        "MAX_SOURCE_ALERT_EVENT_BYTES",
        len(event.event.canonical_bytes) - 1,
    )
    with pytest.raises(ValueError):
        build_source_alert_outbox_event(
            health_snapshot=snapshot,
            alert_kind=SourceAlertKind.DEGRADED,
        )


def test_alert_builder_and_event_reject_operator_kind_status_error_time_and_body_drift() -> None:
    """Alert 只能绑定完整 provider snapshot，并拒绝 kind/status/error/time/body 漂移。"""

    provider = _provider_snapshot()
    alert = build_source_alert_outbox_event(
        health_snapshot=provider,
        alert_kind=SourceAlertKind.DEGRADED,
    )
    operator = replace(
        provider,
        source_sync_run_id=None,
        latency_ms=None,
        status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
        safe_error_code=None,
    )
    with pytest.raises(ValueError):
        build_source_alert_outbox_event(
            health_snapshot=operator,
            alert_kind=SourceAlertKind.DEGRADED,
        )
    with pytest.raises(ValueError):
        build_source_alert_outbox_event(
            health_snapshot=provider,
            alert_kind=SourceAlertKind.FAILING,
        )
    for invalid in (
        {"target_status": SourceHealthStatus.FAILING},
        {"safe_error_code": SourceSyncErrorCode.STALE_SUBSCRIPTION},
        {"dedupe_key": "f" * 64},
        {"event_id": UUID("00000000-0000-4000-8000-000000000043")},
        {"created_at": _NOW + timedelta(seconds=1)},
        {"event": replace(alert.event, sha256="f" * 64)},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(alert, **invalid)
    event_value = json.loads(alert.event.canonical_bytes)
    event_value["schema_version"] = True
    with pytest.raises(ValueError):
        replace(
            alert,
            event=build_canonical_document(
                event_value,
                schema_name=SOURCE_HEALTH_ALERT_SCHEMA_NAME,
                schema_version=1,
            ),
        )
    assert tuple(field.name for field in fields(SourceAlertOutboxEvent)) == (
        "event_id",
        "tenant_id",
        "subscription_id",
        "source_sync_run_id",
        "health_snapshot_id",
        "health_state_version",
        "alert_kind",
        "target_status",
        "safe_error_code",
        "dedupe_key",
        "created_at",
        "event",
    )


def test_freshness_helper_uses_pg_utc_date_accepts_exact_max_age_and_exempts_empty_no_change() -> None:
    """Freshness 只用 PG UTC date，exact max 接受且空 no-change 豁免。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Calendar-day 边界或 hostile type/value admission 漂移时抛出。
    """

    pg_utc_date = date(2026, 8, 14)
    assert not is_source_observation_stale(
        outcome=SourceSyncOutcome.NO_CHANGE,
        latest_source_observed_date=None,
        authoritative_utc_date=pg_utc_date,
        freshness_max_age_days=7,
    )
    assert not is_source_observation_stale(
        outcome=SourceSyncOutcome.SUCCEEDED,
        latest_source_observed_date=date(2026, 8, 7),
        authoritative_utc_date=pg_utc_date,
        freshness_max_age_days=7,
    )
    assert is_source_observation_stale(
        outcome=SourceSyncOutcome.PARTIAL,
        latest_source_observed_date=date(2026, 8, 6),
        authoritative_utc_date=pg_utc_date,
        freshness_max_age_days=7,
    )
    invalid_calls = (
        (SourceSyncOutcome.NO_CHANGE, pg_utc_date, pg_utc_date, 7),
        (SourceSyncOutcome.SUCCEEDED, None, pg_utc_date, 7),
        (SourceSyncOutcome.SUCCEEDED, _NOW, pg_utc_date, 7),
        (SourceSyncOutcome.SUCCEEDED, pg_utc_date, _NOW, 7),
        (SourceSyncOutcome.SUCCEEDED, pg_utc_date, pg_utc_date, True),
        (SourceSyncOutcome.SUCCEEDED, pg_utc_date, pg_utc_date, 0),
        (SourceSyncOutcome.SUCCEEDED, pg_utc_date, pg_utc_date, 3661),
    )
    for outcome, latest, authoritative, max_age in invalid_calls:
        with pytest.raises((TypeError, ValueError)):
            is_source_observation_stale(
                outcome=outcome,
                latest_source_observed_date=latest,
                authoritative_utc_date=authoritative,
                freshness_max_age_days=max_age,
            )


def test_alert_event_ignores_external_builder_clock_and_rejects_created_at_not_equal_to_snapshot_observed_at() -> (
    None
):
    """Alert builder 无外部 clock seam，event 全部时间绑定 snapshot observed_at。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Builder surface、确定性或 outer/canonical time lineage 漂移时抛出。
    """

    signature = inspect.signature(build_source_alert_outbox_event)
    assert tuple(signature.parameters) == ("health_snapshot", "alert_kind")
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())
    assert "clock" not in signature.parameters

    snapshot = _provider_snapshot()
    first = build_source_alert_outbox_event(
        health_snapshot=snapshot,
        alert_kind=SourceAlertKind.DEGRADED,
    )
    external_builder_clock = snapshot.observed_at + timedelta(days=1)
    second = build_source_alert_outbox_event(
        health_snapshot=snapshot,
        alert_kind=SourceAlertKind.DEGRADED,
    )
    assert first == second
    assert first.event_id == second.event_id
    assert first.dedupe_key == second.dedupe_key
    assert first.event.canonical_bytes == second.event.canonical_bytes
    assert first.created_at == snapshot.observed_at
    assert first.created_at != external_builder_clock
    body = json.loads(first.event.canonical_bytes)
    assert body["created_at"] == snapshot.observed_at.isoformat()

    with pytest.raises(ValueError):
        replace(first, created_at=external_builder_clock)
    body["created_at"] = external_builder_clock.isoformat()
    with pytest.raises(ValueError):
        replace(
            first,
            event=build_canonical_document(
                body,
                schema_name=SOURCE_HEALTH_ALERT_SCHEMA_NAME,
                schema_version=1,
            ),
        )
