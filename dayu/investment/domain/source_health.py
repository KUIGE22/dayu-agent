"""Source Sync 健康状态、快照与 semantic alert 纯领域契约。

本模块唯一拥有 health/alert enum、projection/cursor/page、线性化 transition
以及 deterministic alert outbox builder。它只消费 foundation closed outcome/error
与既有强标识/canonical document，不依赖 payload、evidence、operation、Fins、
Service 或存储实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from uuid import NAMESPACE_URL, UUID, uuid5

from dayu.investment.domain.identifiers import TenantId
from dayu.investment.domain.jobs import CanonicalJobDocument, JsonValue, build_canonical_document
from dayu.investment.domain.source import SourceSubscriptionId
from dayu.investment.domain.source_sync import (
    FinsDisclosureSubscriptionConfig,
    SourceSyncErrorCode,
    SourceSyncOutcome,
    _decode_source_document,
    _require_aware_utc,
    _require_canonical_document_size,
    _require_exact_type,
    _require_json_schema_version,
    _require_nonnegative_int,
    _require_positive_int,
    _require_sha256,
)

SOURCE_HEALTH_ALERT_SCHEMA_NAME = "investment.source-health-alert"
"""Semantic health alert 的 canonical schema 名。"""

MAX_SOURCE_ALERT_EVENT_BYTES = 1_048_576
"""Semantic alert canonical bytes 上限。"""

HEALTH_ERRORS = frozenset(
    {
        SourceSyncErrorCode.PARTIAL_BATCH,
        SourceSyncErrorCode.UNSUPPORTED_MARKET,
        SourceSyncErrorCode.UNSUPPORTED_FORM,
        SourceSyncErrorCode.STALE_DATA,
        SourceSyncErrorCode.PROVIDER_RATE_LIMITED,
        SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        SourceSyncErrorCode.FINS_INVARIANT,
    }
)
"""会推进 health 的 closed safe error 集。"""


class SourceHealthStatus(str, Enum):
    """Subscription health head 的闭合状态。"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    DISABLED = "disabled"


class SourceAlertKind(str, Enum):
    """Semantic health alert 的闭合种类。"""

    DEGRADED = "degraded"
    FAILING = "failing"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class SourceHealthReenableRequest:
    """Operator re-enable health 的 CAS 请求。"""

    subscription_id: SourceSubscriptionId
    expected_health_version: int

    def __post_init__(self) -> None:
        """校验订阅标识与预期 health 版本。

        Raises:
            TypeError: 标识类型非法时抛出。
            ValueError: 版本非正时抛出。
        """

        if not isinstance(self.subscription_id, SourceSubscriptionId):
            raise TypeError("subscription_id 必须是 SourceSubscriptionId")
        _require_positive_int(self.expected_health_version, "expected_health_version")


@dataclass(frozen=True, slots=True)
class SourceHealthProjection:
    """Subscription 当前 health head 或 virtual healthy projection。"""

    tenant_id: TenantId
    subscription_id: SourceSubscriptionId
    status: SourceHealthStatus
    consecutive_failures: int
    safe_error_code: SourceSyncErrorCode | None
    version: int
    last_source_sync_run_id: UUID | None
    observed_at: datetime | None

    def __post_init__(self) -> None:
        """校验 virtual/persisted head presence 与状态矩阵。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: version、presence 或状态矩阵非法时抛出。
        """

        _validate_health_identity(self.tenant_id, self.subscription_id)
        if not isinstance(self.status, SourceHealthStatus):
            raise TypeError("status 必须是 SourceHealthStatus")
        _require_nonnegative_int(self.consecutive_failures, "consecutive_failures")
        _require_nonnegative_int(self.version, "version")
        _validate_health_status_shape(self.status, self.consecutive_failures, self.safe_error_code)
        if self.version == 0:
            if (
                self.status is not SourceHealthStatus.HEALTHY
                or self.consecutive_failures != 0
                or self.safe_error_code is not None
                or self.last_source_sync_run_id is not None
                or self.observed_at is not None
            ):
                raise ValueError("virtual health head shape 非法")
            return
        if self.last_source_sync_run_id is None or self.observed_at is None:
            raise ValueError("persisted health head 必须有 run 与 observed_at")
        _require_exact_type(self.last_source_sync_run_id, UUID, "last_source_sync_run_id")
        _require_aware_utc(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class SourceHealthSnapshotProjection:
    """Provider、operator 或 legacy health snapshot projection。"""

    snapshot_id: UUID
    tenant_id: TenantId
    subscription_id: SourceSubscriptionId
    source_sync_run_id: UUID | None
    health_state_version: int | None
    status: SourceHealthStatus
    consecutive_failures: int
    latency_ms: int | None
    safe_error_code: SourceSyncErrorCode | None
    observed_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        """校验 snapshot identity、version、lineage 与时间矩阵。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: provider/operator/legacy shape 非法时抛出。
        """

        _require_exact_type(self.snapshot_id, UUID, "snapshot_id")
        _validate_health_identity(self.tenant_id, self.subscription_id)
        if not isinstance(self.status, SourceHealthStatus):
            raise TypeError("status 必须是 SourceHealthStatus")
        _require_nonnegative_int(self.consecutive_failures, "consecutive_failures")
        _validate_health_status_shape(self.status, self.consecutive_failures, self.safe_error_code)
        _require_aware_utc(self.observed_at, "observed_at")
        _require_aware_utc(self.created_at, "created_at")
        if self.health_state_version is None:
            if self.source_sync_run_id is not None:
                _require_exact_type(self.source_sync_run_id, UUID, "source_sync_run_id")
            if self.latency_ms is not None:
                _require_nonnegative_int(self.latency_ms, "latency_ms")
            return
        _require_positive_int(self.health_state_version, "health_state_version")
        if self.created_at != self.observed_at:
            raise ValueError("v2 snapshot created_at 必须等于 observed_at")
        if self.source_sync_run_id is None:
            if (
                self.latency_ms is not None
                or self.status is not SourceHealthStatus.HEALTHY
                or self.consecutive_failures != 0
                or self.safe_error_code is not None
            ):
                raise ValueError("operator snapshot shape 非法")
            return
        _require_exact_type(self.source_sync_run_id, UUID, "source_sync_run_id")
        if self.latency_ms is None:
            raise ValueError("provider snapshot 必须携带 latency_ms")
        _require_nonnegative_int(self.latency_ms, "latency_ms")


@dataclass(frozen=True, slots=True)
class SourceHealthSnapshotCursor:
    """健康快照的 keyset cursor。"""

    observed_at: datetime
    snapshot_id: UUID

    def __post_init__(self) -> None:
        """校验 cursor 时间与 UUID。

        Raises:
            TypeError: UUID 类型非法时抛出。
            ValueError: 时间不是 aware UTC 时抛出。
        """

        _require_aware_utc(self.observed_at, "observed_at")
        _require_exact_type(self.snapshot_id, UUID, "snapshot_id")


@dataclass(frozen=True, slots=True)
class SourceHealthSnapshotPage:
    """按 ``observed_at DESC, snapshot_id DESC`` 排序的 snapshot 页。"""

    snapshots: tuple[SourceHealthSnapshotProjection, ...]
    next_cursor: SourceHealthSnapshotCursor | None

    def __post_init__(self) -> None:
        """防御性复制并校验排序与 cursor identity。

        Raises:
            TypeError: item 或 cursor 类型非法时抛出。
            ValueError: 排序或 cursor 位置非法时抛出。
        """

        snapshots = tuple(self.snapshots)
        object.__setattr__(self, "snapshots", snapshots)
        for snapshot in snapshots:
            if not isinstance(snapshot, SourceHealthSnapshotProjection):
                raise TypeError("snapshots item 必须是 SourceHealthSnapshotProjection")
        keys = [(item.observed_at, item.snapshot_id.int) for item in snapshots]
        if keys != sorted(keys, reverse=True) or len(set(keys)) != len(keys):
            raise ValueError("snapshots 必须严格 descending 排序")
        if self.next_cursor is None:
            return
        if not isinstance(self.next_cursor, SourceHealthSnapshotCursor):
            raise TypeError("next_cursor 类型非法")
        if not snapshots:
            raise ValueError("空页不得携带 next_cursor")
        last = snapshots[-1]
        if (self.next_cursor.observed_at, self.next_cursor.snapshot_id) != (last.observed_at, last.snapshot_id):
            raise ValueError("next_cursor 必须等于页尾 snapshot identity")


@dataclass(frozen=True, slots=True)
class SourceAlertOutboxEvent:
    """确定性的 semantic health alert outbox event。"""

    event_id: UUID
    tenant_id: TenantId
    subscription_id: SourceSubscriptionId
    source_sync_run_id: UUID
    health_snapshot_id: UUID
    health_state_version: int
    alert_kind: SourceAlertKind
    target_status: SourceHealthStatus
    safe_error_code: SourceSyncErrorCode
    dedupe_key: str
    created_at: datetime
    event: CanonicalJobDocument

    def __post_init__(self) -> None:
        """重算 dedupe、event UUID/body/hash 并闭合 lineage。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: lineage、dedupe、时间或 canonical body 漂移时抛出。
        """

        _require_exact_type(self.event_id, UUID, "event_id")
        _validate_health_identity(self.tenant_id, self.subscription_id)
        _require_exact_type(self.source_sync_run_id, UUID, "source_sync_run_id")
        _require_exact_type(self.health_snapshot_id, UUID, "health_snapshot_id")
        _require_positive_int(self.health_state_version, "health_state_version")
        if not isinstance(self.alert_kind, SourceAlertKind):
            raise TypeError("alert_kind 必须是 SourceAlertKind")
        if not isinstance(self.target_status, SourceHealthStatus):
            raise TypeError("target_status 必须是 SourceHealthStatus")
        if self.alert_kind.value != self.target_status.value:
            raise ValueError("alert kind 与 target status 必须一一对应")
        if self.safe_error_code not in HEALTH_ERRORS:
            raise ValueError("alert safe_error_code 不属于 HEALTH_ERRORS")
        _require_sha256(self.dedupe_key, "dedupe_key")
        _require_aware_utc(self.created_at, "created_at")
        expected_dedupe = _build_alert_dedupe_key(
            tenant_id=self.tenant_id,
            subscription_id=self.subscription_id,
            source_sync_run_id=self.source_sync_run_id,
            health_snapshot_id=self.health_snapshot_id,
            health_state_version=self.health_state_version,
            alert_kind=self.alert_kind,
            target_status=self.target_status,
            safe_error_code=self.safe_error_code,
        )
        if self.dedupe_key != expected_dedupe:
            raise ValueError("alert dedupe_key 漂移")
        expected_id = uuid5(NAMESPACE_URL, f"investment-source-health-alert:v1:{self.dedupe_key}")
        if self.event_id != expected_id:
            raise ValueError("alert event_id 漂移")
        raw = _decode_source_document(
            self.event,
            schema_name=SOURCE_HEALTH_ALERT_SCHEMA_NAME,
            schema_version=1,
            max_bytes=MAX_SOURCE_ALERT_EVENT_BYTES,
        )
        _require_json_schema_version(raw.get("schema_version"), "alert schema_version")
        if raw != _source_alert_event_value(self):
            raise ValueError("alert canonical event 与 outer fields 不一致")


def _validate_health_identity(tenant_id: TenantId, subscription_id: SourceSubscriptionId) -> None:
    """校验 health projection 的强标识类型。

    Args:
        tenant_id: 租户标识。
        subscription_id: Source subscription 标识。

    Raises:
        TypeError: 任一强标识类型非法时抛出。
    """

    if not isinstance(tenant_id, TenantId):
        raise TypeError("tenant_id 必须是 TenantId")
    if not isinstance(subscription_id, SourceSubscriptionId):
        raise TypeError("subscription_id 必须是 SourceSubscriptionId")


def _validate_health_status_shape(
    status: SourceHealthStatus,
    consecutive_failures: int,
    safe_error_code: SourceSyncErrorCode | None,
) -> None:
    """校验 health status/failure/error 的闭合形状。

    Args:
        status: Health 状态。
        consecutive_failures: 连续失败次数。
        safe_error_code: 可空安全错误。

    Raises:
        TypeError: error 类型非法时抛出。
        ValueError: 状态矩阵非法时抛出。
    """

    if safe_error_code is not None and not isinstance(safe_error_code, SourceSyncErrorCode):
        raise TypeError("safe_error_code 类型非法")
    if status is SourceHealthStatus.HEALTHY:
        if consecutive_failures != 0 or safe_error_code is not None:
            raise ValueError("healthy health shape 非法")
    elif consecutive_failures <= 0 or safe_error_code not in HEALTH_ERRORS:
        raise ValueError("non-healthy health shape 非法")


def is_source_observation_stale(
    *,
    outcome: SourceSyncOutcome,
    latest_source_observed_date: date | None,
    authoritative_utc_date: date,
    freshness_max_age_days: int,
) -> bool:
    """按 authoritative PG UTC date 判断有文档 observation 是否 stale。

    Args:
        outcome: Provider observation outcome。
        latest_source_observed_date: Verified documents 最新 calendar date。
        authoritative_utc_date: Terminal transaction 派生的 UTC date。
        freshness_max_age_days: 允许最大 calendar day age。

    Returns:
        超过最大 age 时返回 ``True``；空 no-change 恒为 ``False``。

    Raises:
        TypeError: outcome/date 类型非法时抛出。
        ValueError: freshness 范围或 outcome/date 组合非法时抛出。
    """

    if not isinstance(outcome, SourceSyncOutcome):
        raise TypeError("outcome 必须是 SourceSyncOutcome")
    if type(authoritative_utc_date) is not date:
        raise TypeError("authoritative_utc_date 必须是 date")
    _require_positive_int(freshness_max_age_days, "freshness_max_age_days")
    if freshness_max_age_days > 3660:
        raise ValueError("freshness_max_age_days 不得超过 3660")
    if outcome is SourceSyncOutcome.NO_CHANGE:
        if latest_source_observed_date is not None:
            raise ValueError("no_change 不得携带 source date")
        return False
    if latest_source_observed_date is None:
        raise ValueError("非 no_change observation 必须携带 source date")
    if type(latest_source_observed_date) is not date:
        raise TypeError("latest_source_observed_date 必须是 date")
    return (authoritative_utc_date - latest_source_observed_date).days > freshness_max_age_days


def build_source_health_transition(
    *,
    current: SourceHealthProjection,
    outcome: SourceSyncOutcome,
    safe_error_code: SourceSyncErrorCode | None,
    config: FinsDisclosureSubscriptionConfig,
    source_sync_run_id: UUID,
    observed_at: datetime,
) -> tuple[SourceHealthProjection, SourceAlertKind | None]:
    """按 provider observation 线性推进 health head。

    Args:
        current: 锁定的 current 或 virtual health head。
        outcome: Source observation outcome。
        safe_error_code: Outcome 对应 closed error。
        config: Subscription health 阈值。
        source_sync_run_id: 本次 provider run UUID。
        observed_at: Authoritative terminal 时刻。

    Returns:
        ``(health_after, optional_alert_kind)``；no-op 返回原 projection。

    Raises:
        TypeError: 字段类型非法时抛出。
        ValueError: outcome/error matrix 非法时抛出。
    """

    if not isinstance(current, SourceHealthProjection):
        raise TypeError("current 必须是 SourceHealthProjection")
    if not isinstance(outcome, SourceSyncOutcome):
        raise TypeError("outcome 必须是 SourceSyncOutcome")
    if not isinstance(config, FinsDisclosureSubscriptionConfig):
        raise TypeError("config 必须是 FinsDisclosureSubscriptionConfig")
    _require_exact_type(source_sync_run_id, UUID, "source_sync_run_id")
    _require_aware_utc(observed_at, "observed_at")
    if outcome is SourceSyncOutcome.SKIPPED_DISABLED:
        if safe_error_code is not None:
            raise ValueError("skipped_disabled error 必须为空")
        return current, None
    if outcome is SourceSyncOutcome.STALE_SUBSCRIPTION:
        if safe_error_code is not SourceSyncErrorCode.STALE_SUBSCRIPTION:
            raise ValueError("stale_subscription error 不匹配")
        return current, None
    _validate_provider_outcome_error(outcome, safe_error_code)
    if current.status is SourceHealthStatus.DISABLED:
        return current, None
    if outcome in {SourceSyncOutcome.SUCCEEDED, SourceSyncOutcome.NO_CHANGE}:
        status = SourceHealthStatus.HEALTHY
        failures = 0
        error = None
    else:
        failures = current.consecutive_failures + 1
        error = safe_error_code
        if failures >= config.disable_after:
            status = SourceHealthStatus.DISABLED
        elif failures >= config.failing_after:
            status = SourceHealthStatus.FAILING
        else:
            status = SourceHealthStatus.DEGRADED
        if current.status is SourceHealthStatus.FAILING and status is SourceHealthStatus.DEGRADED:
            status = SourceHealthStatus.FAILING
    after = SourceHealthProjection(
        tenant_id=current.tenant_id,
        subscription_id=current.subscription_id,
        status=status,
        consecutive_failures=failures,
        safe_error_code=error,
        version=current.version + 1,
        last_source_sync_run_id=source_sync_run_id,
        observed_at=observed_at,
    )
    return after, _derive_alert_kind(current, after)


def _validate_provider_outcome_error(
    outcome: SourceSyncOutcome,
    safe_error_code: SourceSyncErrorCode | None,
) -> None:
    """校验会推进 health 的 provider outcome/error 组合。

    Args:
        outcome: Source observation outcome。
        safe_error_code: 可空 safe error。

    Raises:
        ValueError: 组合不在 closed matrix 时抛出。
    """

    if outcome in {SourceSyncOutcome.SUCCEEDED, SourceSyncOutcome.NO_CHANGE}:
        if safe_error_code is not None:
            raise ValueError("success/no_change error 必须为空")
        return
    if outcome is SourceSyncOutcome.PARTIAL:
        if safe_error_code is not SourceSyncErrorCode.PARTIAL_BATCH:
            raise ValueError("partial error 必须为 partial_batch")
        return
    if outcome is SourceSyncOutcome.FAILED and safe_error_code in HEALTH_ERRORS - {SourceSyncErrorCode.PARTIAL_BATCH}:
        return
    raise ValueError("provider outcome/error 不在 health closed matrix")


def _derive_alert_kind(
    current: SourceHealthProjection,
    after: SourceHealthProjection,
) -> SourceAlertKind | None:
    """从 semantic transition 派生可选 alert kind。

    Args:
        current: Transition 前 health。
        after: Transition 后 health。

    Returns:
        进入/升级/同状态错误变化时的 alert kind，否则 ``None``。

    Raises:
        无。
    """

    if after.status is SourceHealthStatus.HEALTHY:
        return None
    if after.status is current.status:
        if after.safe_error_code is current.safe_error_code:
            return None
        return SourceAlertKind(after.status.value)
    if current.status is SourceHealthStatus.HEALTHY:
        return SourceAlertKind(after.status.value)
    if current.status is SourceHealthStatus.DEGRADED and after.status in {
        SourceHealthStatus.FAILING,
        SourceHealthStatus.DISABLED,
    }:
        return SourceAlertKind(after.status.value)
    if current.status is SourceHealthStatus.FAILING and after.status is SourceHealthStatus.DISABLED:
        return SourceAlertKind(after.status.value)
    return None


def _build_alert_dedupe_key(
    *,
    tenant_id: TenantId,
    subscription_id: SourceSubscriptionId,
    source_sync_run_id: UUID,
    health_snapshot_id: UUID,
    health_state_version: int,
    alert_kind: SourceAlertKind,
    target_status: SourceHealthStatus,
    safe_error_code: SourceSyncErrorCode,
) -> str:
    """按固定八字段 transition object 生成 dedupe SHA-256。

    Args:
        tenant_id: 租户标识。
        subscription_id: Subscription 标识。
        source_sync_run_id: Source run UUID。
        health_snapshot_id: Health snapshot UUID。
        health_state_version: Health head version。
        alert_kind: Alert kind。
        target_status: Target health status。
        safe_error_code: Closed health error。

    Returns:
        Lowercase SHA-256 dedupe key。

    Raises:
        无。
    """

    document = build_canonical_document(
        {
            "alert_kind": alert_kind.value,
            "health_snapshot_id": str(health_snapshot_id),
            "health_state_version": health_state_version,
            "safe_error_code": safe_error_code.value,
            "source_sync_run_id": str(source_sync_run_id),
            "subscription_id": str(subscription_id),
            "target_status": target_status.value,
            "tenant_id": str(tenant_id),
        },
        schema_name="investment.source-health-transition",
        schema_version=1,
    )
    return document.sha256


def _source_alert_event_value(event: SourceAlertOutboxEvent) -> dict[str, JsonValue]:
    """把 alert DTO 投影为 canonical event body。

    Args:
        event: Strict alert event DTO。

    Returns:
        Closed alert JSON body。

    Raises:
        无。
    """

    return {
        "alert_kind": event.alert_kind.value,
        "created_at": event.created_at.isoformat(),
        "dedupe_key": event.dedupe_key,
        "event_id": str(event.event_id),
        "health_snapshot_id": str(event.health_snapshot_id),
        "health_state_version": event.health_state_version,
        "safe_error_code": event.safe_error_code.value,
        "schema_version": 1,
        "source_sync_run_id": str(event.source_sync_run_id),
        "subscription_id": str(event.subscription_id),
        "target_status": event.target_status.value,
        "tenant_id": str(event.tenant_id),
    }


def build_source_alert_outbox_event(
    *,
    health_snapshot: SourceHealthSnapshotProjection,
    alert_kind: SourceAlertKind,
) -> SourceAlertOutboxEvent:
    """从 provider health snapshot 唯一构建 deterministic alert event。

    Args:
        health_snapshot: 与 alert 绑定的 provider snapshot。
        alert_kind: Transition builder 派生的 alert kind。

    Returns:
        Immutable canonical outbox event。

    Raises:
        TypeError: 参数类型非法时抛出。
        ValueError: snapshot lineage/status/error 不可形成 alert 时抛出。
    """

    if not isinstance(health_snapshot, SourceHealthSnapshotProjection):
        raise TypeError("health_snapshot 必须是 SourceHealthSnapshotProjection")
    if not isinstance(alert_kind, SourceAlertKind):
        raise TypeError("alert_kind 必须是 SourceAlertKind")
    if (
        health_snapshot.source_sync_run_id is None
        or health_snapshot.health_state_version is None
        or health_snapshot.safe_error_code is None
    ):
        raise ValueError("alert 必须绑定 provider snapshot 的完整 lineage")
    if health_snapshot.status.value != alert_kind.value:
        raise ValueError("alert_kind 与 snapshot status 不匹配")
    dedupe_key = _build_alert_dedupe_key(
        tenant_id=health_snapshot.tenant_id,
        subscription_id=health_snapshot.subscription_id,
        source_sync_run_id=health_snapshot.source_sync_run_id,
        health_snapshot_id=health_snapshot.snapshot_id,
        health_state_version=health_snapshot.health_state_version,
        alert_kind=alert_kind,
        target_status=health_snapshot.status,
        safe_error_code=health_snapshot.safe_error_code,
    )
    event_id = uuid5(NAMESPACE_URL, f"investment-source-health-alert:v1:{dedupe_key}")
    value: dict[str, JsonValue] = {
        "alert_kind": alert_kind.value,
        "created_at": health_snapshot.observed_at.isoformat(),
        "dedupe_key": dedupe_key,
        "event_id": str(event_id),
        "health_snapshot_id": str(health_snapshot.snapshot_id),
        "health_state_version": health_snapshot.health_state_version,
        "safe_error_code": health_snapshot.safe_error_code.value,
        "schema_version": 1,
        "source_sync_run_id": str(health_snapshot.source_sync_run_id),
        "subscription_id": str(health_snapshot.subscription_id),
        "target_status": health_snapshot.status.value,
        "tenant_id": str(health_snapshot.tenant_id),
    }
    document = build_canonical_document(
        value,
        schema_name=SOURCE_HEALTH_ALERT_SCHEMA_NAME,
        schema_version=1,
    )
    _require_canonical_document_size(document, max_bytes=MAX_SOURCE_ALERT_EVENT_BYTES)
    return SourceAlertOutboxEvent(
        event_id=event_id,
        tenant_id=health_snapshot.tenant_id,
        subscription_id=health_snapshot.subscription_id,
        source_sync_run_id=health_snapshot.source_sync_run_id,
        health_snapshot_id=health_snapshot.snapshot_id,
        health_state_version=health_snapshot.health_state_version,
        alert_kind=alert_kind,
        target_status=health_snapshot.status,
        safe_error_code=health_snapshot.safe_error_code,
        dedupe_key=dedupe_key,
        created_at=health_snapshot.observed_at,
        event=document,
    )


__all__ = [
    "HEALTH_ERRORS",
    "MAX_SOURCE_ALERT_EVENT_BYTES",
    "SOURCE_HEALTH_ALERT_SCHEMA_NAME",
    "SourceAlertKind",
    "SourceAlertOutboxEvent",
    "SourceHealthProjection",
    "SourceHealthReenableRequest",
    "SourceHealthSnapshotCursor",
    "SourceHealthSnapshotPage",
    "SourceHealthSnapshotProjection",
    "SourceHealthStatus",
    "build_source_alert_outbox_event",
    "build_source_health_transition",
    "is_source_observation_stale",
]
