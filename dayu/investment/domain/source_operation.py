"""Source Sync operation acquire 与 terminal 纯领域契约。

本模块唯一拥有 operation 状态/action、acquire request/decision 与 terminal
request/decision。它只组合 foundation、payload、evidence、health 与 durable
Job descriptor 的纯 DTO，不保存 lease/token/fence、PG clock 或 caller 预构造的
terminal IDs/document。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from dayu.investment.domain.jobs import JobHandlerDescriptor
from dayu.investment.domain.source_evidence import (
    SourceFinsTerminalCandidate,
    SourceNoProviderTerminalCandidate,
    SourceSyncAttemptReceipt,
    SourceSyncResult,
    SourceTerminalCandidate,
)
from dayu.investment.domain.source_health import (
    SourceAlertOutboxEvent,
    SourceHealthProjection,
    SourceHealthSnapshotProjection,
    SourceHealthStatus,
)
from dayu.investment.domain.source_payload import (
    SourceExecutionSnapshot,
    build_source_execution_snapshot_document,
)
from dayu.investment.domain.source_sync import (
    SOURCE_SYNC_JOB_DESCRIPTOR,
    SourceBindingDisposition,
    SourceSyncOrigin,
    SourceSyncOutcome,
    _require_exact_type,
    _require_positive_int,
    _require_sha256,
)


class SourceOperationState(str, Enum):
    """持久化 source operation 的闭合状态。"""

    ACTIVE = "active"
    TERMINAL = "terminal"


class SourceOperationEffectiveState(str, Enum):
    """Acquire decision 可公开的闭合 effective state。"""

    LIVE = "live"
    TERMINAL = "terminal"


class SourceOperationAcquireAction(str, Enum):
    """Acquire operation 的闭合 action。"""

    ACQUIRED = "acquired"
    BUSY = "busy"
    TERMINAL_REPLAY = "terminal_replay"


class SourceTerminalRecordAction(str, Enum):
    """Record terminal 的闭合 action。"""

    RECORDED = "recorded"
    LEASE_LOST = "lease_lost"
    JOB_NOT_LIVE = "job_not_live"
    STALE_SUBSCRIPTION = "stale_subscription"


@dataclass(frozen=True, slots=True)
class SourceOperationAcquireRequest:
    """Repository acquire operation 的 strict request。"""

    origin: SourceSyncOrigin
    definition_id: UUID
    descriptor: JobHandlerDescriptor
    job_id: UUID
    attempt_id: UUID
    attempt_number: int
    payload_sha256: str
    candidate_execution_snapshot: SourceExecutionSnapshot | None

    def __post_init__(self) -> None:
        """校验 Job lineage、descriptor、hash 与 origin/snapshot matrix。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: descriptor 或 origin/snapshot 组合非法时抛出。
        """

        if not isinstance(self.origin, SourceSyncOrigin):
            raise TypeError("origin 必须是 SourceSyncOrigin")
        _require_exact_type(self.definition_id, UUID, "definition_id")
        if not isinstance(self.descriptor, JobHandlerDescriptor):
            raise TypeError("descriptor 必须是 JobHandlerDescriptor")
        if self.descriptor != SOURCE_SYNC_JOB_DESCRIPTOR:
            raise ValueError("descriptor 必须精确等于 Source Sync descriptor")
        _require_exact_type(self.job_id, UUID, "job_id")
        _require_exact_type(self.attempt_id, UUID, "attempt_id")
        _require_positive_int(self.attempt_number, "attempt_number")
        _require_sha256(self.payload_sha256, "payload_sha256")
        if self.origin is SourceSyncOrigin.MANUAL:
            if not isinstance(self.candidate_execution_snapshot, SourceExecutionSnapshot):
                raise ValueError("manual acquire 必须携带 candidate snapshot")
        elif self.candidate_execution_snapshot is not None:
            raise ValueError("scheduled acquire 不得携带 candidate snapshot")


@dataclass(frozen=True, slots=True)
class SourceOperationAcquireDecision:
    """Acquire operation 的 acquired/busy/replay closed decision。"""

    action: SourceOperationAcquireAction
    effective_state: SourceOperationEffectiveState
    operation_id: UUID
    generation: int | None
    execution_snapshot: SourceExecutionSnapshot | None
    execution_snapshot_sha256: str | None
    binding_disposition: SourceBindingDisposition | None
    terminal_result: SourceSyncResult | None
    terminal_receipt: SourceSyncAttemptReceipt | None

    def __post_init__(self) -> None:
        """校验三个 action 的 exact presence matrix 与 replay lineage。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: action/effective-state/presence matrix 非法时抛出。
        """

        if not isinstance(self.action, SourceOperationAcquireAction):
            raise TypeError("action 必须是 SourceOperationAcquireAction")
        if not isinstance(self.effective_state, SourceOperationEffectiveState):
            raise TypeError("effective_state 必须是 SourceOperationEffectiveState")
        _require_exact_type(self.operation_id, UUID, "operation_id")
        if self.action is SourceOperationAcquireAction.ACQUIRED:
            self._validate_acquired()
        elif self.action is SourceOperationAcquireAction.BUSY:
            self._validate_busy()
        else:
            self._validate_terminal_replay()

    def _validate_acquired(self) -> None:
        """校验 acquired/live presence matrix。

        Raises:
            ValueError: 任一 required/forbidden 字段不符时抛出。
        """

        if self.effective_state is not SourceOperationEffectiveState.LIVE:
            raise ValueError("acquired effective_state 必须为 live")
        if self.generation is None:
            raise ValueError("acquired 必须携带 generation")
        _require_positive_int(self.generation, "generation")
        if self.execution_snapshot is None:
            raise ValueError("acquired 必须携带 execution_snapshot")
        if not isinstance(self.execution_snapshot, SourceExecutionSnapshot):
            raise TypeError("execution_snapshot 类型非法")
        if self.execution_snapshot_sha256 is None:
            raise ValueError("acquired 必须携带 snapshot SHA")
        _require_sha256(self.execution_snapshot_sha256, "execution_snapshot_sha256")
        expected_snapshot_sha256 = build_source_execution_snapshot_document(self.execution_snapshot).sha256
        if self.execution_snapshot_sha256 != expected_snapshot_sha256:
            raise ValueError("acquired snapshot SHA 与 snapshot bytes 不一致")
        if self.binding_disposition is None:
            raise ValueError("acquired 必须携带 binding_disposition")
        if not isinstance(self.binding_disposition, SourceBindingDisposition):
            raise TypeError("binding_disposition 类型非法")
        if self.terminal_result is not None or self.terminal_receipt is not None:
            raise ValueError("acquired 不得携带 terminal replay")

    def _validate_busy(self) -> None:
        """校验 busy/live presence matrix。

        Raises:
            ValueError: 任一 extra 字段非空时抛出。
        """

        if self.effective_state is not SourceOperationEffectiveState.LIVE:
            raise ValueError("busy effective_state 必须为 live")
        if any(
            value is not None
            for value in (
                self.generation,
                self.execution_snapshot,
                self.execution_snapshot_sha256,
                self.binding_disposition,
                self.terminal_result,
                self.terminal_receipt,
            )
        ):
            raise ValueError("busy 只能携带 operation identity")

    def _validate_terminal_replay(self) -> None:
        """校验 terminal replay presence 与 canonical lineage。

        Raises:
            ValueError: presence、state 或 receipt/result lineage 非法时抛出。
        """

        if self.effective_state is not SourceOperationEffectiveState.TERMINAL:
            raise ValueError("terminal replay effective_state 必须为 terminal")
        if any(
            value is not None
            for value in (
                self.generation,
                self.execution_snapshot,
                self.execution_snapshot_sha256,
                self.binding_disposition,
            )
        ):
            raise ValueError("terminal replay 不得携带 live fields")
        if self.terminal_result is None or self.terminal_receipt is None:
            raise ValueError("terminal replay 必须携带 result 与 receipt")
        if not isinstance(self.terminal_result, SourceSyncResult):
            raise TypeError("terminal_result 类型非法")
        if not isinstance(self.terminal_receipt, SourceSyncAttemptReceipt):
            raise TypeError("terminal_receipt 类型非法")
        _validate_result_receipt_lineage(self.terminal_result, self.terminal_receipt)


@dataclass(frozen=True, slots=True)
class SourceTerminalRecordRequest:
    """Repository record_terminal 的 closed candidate request。"""

    operation_id: UUID
    job_id: UUID
    attempt_id: UUID
    attempt_number: int
    expected_generation: int
    expected_execution_snapshot_sha256: str
    candidate: SourceTerminalCandidate

    def __post_init__(self) -> None:
        """校验 operation/attempt identity、generation、hash 与 candidate union。

        Raises:
            TypeError: 字段或 candidate 类型非法时抛出。
            ValueError: 数值或 hash 非法时抛出。
        """

        _require_exact_type(self.operation_id, UUID, "operation_id")
        _require_exact_type(self.job_id, UUID, "job_id")
        _require_exact_type(self.attempt_id, UUID, "attempt_id")
        _require_positive_int(self.attempt_number, "attempt_number")
        _require_positive_int(self.expected_generation, "expected_generation")
        _require_sha256(self.expected_execution_snapshot_sha256, "expected_execution_snapshot_sha256")
        if not isinstance(
            self.candidate,
            (SourceFinsTerminalCandidate, SourceNoProviderTerminalCandidate),
        ):
            raise TypeError("candidate 必须是 SourceTerminalCandidate closed union")


@dataclass(frozen=True, slots=True)
class SourceTerminalRecordDecision:
    """Repository terminal record 的 closed decision。"""

    action: SourceTerminalRecordAction
    result: SourceSyncResult | None
    receipt: SourceSyncAttemptReceipt | None
    health_after: SourceHealthProjection | None
    health_snapshot: SourceHealthSnapshotProjection | None
    alert_event: SourceAlertOutboxEvent | None

    def __post_init__(self) -> None:
        """校验 action-specific presence、outcome 与 cross-DTO lineage。

        Raises:
            TypeError: action 类型非法时抛出。
            ValueError: presence 或 lineage matrix 非法时抛出。
        """

        if not isinstance(self.action, SourceTerminalRecordAction):
            raise TypeError("action 必须是 SourceTerminalRecordAction")
        if self.action in {SourceTerminalRecordAction.LEASE_LOST, SourceTerminalRecordAction.JOB_NOT_LIVE}:
            if any(
                value is not None
                for value in (
                    self.result,
                    self.receipt,
                    self.health_after,
                    self.health_snapshot,
                    self.alert_event,
                )
            ):
                raise ValueError("live loss decision 的所有 result fields 必须为空")
            return
        if self.result is None or self.receipt is None:
            raise ValueError("terminal decision 必须携带 result 与 receipt")
        if not isinstance(self.result, SourceSyncResult):
            raise TypeError("result 类型非法")
        if not isinstance(self.receipt, SourceSyncAttemptReceipt):
            raise TypeError("receipt 类型非法")
        if self.health_after is None:
            raise ValueError("terminal decision 必须携带 health_after")
        if not isinstance(self.health_after, SourceHealthProjection):
            raise TypeError("health_after 类型非法")
        _validate_result_receipt_lineage(self.result, self.receipt)
        if self.health_after.tenant_id != self.receipt.tenant_id:
            raise ValueError("health 与 receipt tenant lineage 不一致")
        if self.health_after.subscription_id != self.receipt.subscription_id:
            raise ValueError("health 与 receipt subscription lineage 不一致")
        if self.action is SourceTerminalRecordAction.STALE_SUBSCRIPTION:
            if self.receipt.outcome is not SourceSyncOutcome.STALE_SUBSCRIPTION:
                raise ValueError("stale decision 必须绑定 stale_subscription receipt")
            if self.health_snapshot is not None or self.alert_event is not None:
                raise ValueError("stale decision 不得推进 snapshot/alert")
            if self.health_after.last_source_sync_run_id == self.receipt.source_sync_run_id:
                raise ValueError("stale_subscription 不得推进 health head")
            return
        if self.receipt.outcome is SourceSyncOutcome.STALE_SUBSCRIPTION:
            raise ValueError("recorded action 不得伪装 stale_subscription")
        health_advanced = self.health_after.last_source_sync_run_id == self.receipt.source_sync_run_id
        if health_advanced:
            if self.receipt.outcome is SourceSyncOutcome.SKIPPED_DISABLED:
                raise ValueError("skipped_disabled 不得推进 health")
            if self.receipt.outcome in {SourceSyncOutcome.SUCCEEDED, SourceSyncOutcome.NO_CHANGE}:
                if (
                    self.health_after.status is not SourceHealthStatus.HEALTHY
                    or self.health_after.consecutive_failures != 0
                    or self.health_after.safe_error_code is not None
                ):
                    raise ValueError("success/no_change health 必须恢复为 healthy")
            elif self.receipt.outcome in {SourceSyncOutcome.PARTIAL, SourceSyncOutcome.FAILED} and (
                self.health_after.status is SourceHealthStatus.HEALTHY
                or self.health_after.consecutive_failures <= 0
                or self.health_after.safe_error_code is not self.receipt.safe_error_code
            ):
                raise ValueError("partial/failed health 必须绑定 receipt error")
            if self.health_after.observed_at != self.receipt.finished_at:
                raise ValueError("推进后的 health head 时间必须绑定 terminal receipt")
            if self.health_snapshot is None:
                raise ValueError("health 推进时必须携带 snapshot")
        else:
            if (
                self.receipt.outcome
                in {
                    SourceSyncOutcome.SUCCEEDED,
                    SourceSyncOutcome.NO_CHANGE,
                    SourceSyncOutcome.PARTIAL,
                    SourceSyncOutcome.FAILED,
                }
                and self.health_after.status is not SourceHealthStatus.DISABLED
            ):
                raise ValueError("provider health no-op 只允许 sticky disabled head")
            if self.health_snapshot is not None or self.alert_event is not None:
                raise ValueError("health no-op 时不得携带 snapshot/alert")
        if self.health_snapshot is not None:
            if not isinstance(self.health_snapshot, SourceHealthSnapshotProjection):
                raise TypeError("health_snapshot 类型非法")
            _validate_snapshot_lineage(self.receipt, self.health_after, self.health_snapshot)
        if self.alert_event is not None:
            if not isinstance(self.alert_event, SourceAlertOutboxEvent):
                raise TypeError("alert_event 类型非法")
            if self.health_snapshot is None:
                raise ValueError("alert_event 必须绑定 health_snapshot")
            _validate_alert_lineage(self.health_snapshot, self.alert_event)


def _validate_result_receipt_lineage(result: SourceSyncResult, receipt: SourceSyncAttemptReceipt) -> None:
    """校验 result 精确引用同一 canonical receipt。

    Args:
        result: Source Job result。
        receipt: Source attempt receipt。

    Raises:
        ValueError: outcome/run/attempt/hash/retry 任一不一致时抛出。
    """

    if (
        result.outcome is not receipt.outcome
        or result.source_sync_run_id != receipt.source_sync_run_id
        or result.producer_attempt_id != receipt.producer_attempt_id
        or result.source_receipt_sha256 != receipt.receipt.sha256
        or result.retry_recommended != receipt.retry_recommended
    ):
        raise ValueError("result 与 receipt canonical lineage 不一致")


def _validate_snapshot_lineage(
    receipt: SourceSyncAttemptReceipt,
    health_after: SourceHealthProjection,
    snapshot: SourceHealthSnapshotProjection,
) -> None:
    """校验 provider health snapshot 与 receipt/head lineage。

    Args:
        receipt: Source receipt。
        health_after: Transition 后 head。
        snapshot: 同 transaction snapshot。

    Raises:
        ValueError: tenant/subscription/run/version/status/error 任一漂移时抛出。
    """

    if (
        snapshot.tenant_id != receipt.tenant_id
        or snapshot.subscription_id != receipt.subscription_id
        or snapshot.source_sync_run_id != receipt.source_sync_run_id
        or snapshot.health_state_version != health_after.version
        or snapshot.status is not health_after.status
        or snapshot.consecutive_failures != health_after.consecutive_failures
        or snapshot.safe_error_code is not health_after.safe_error_code
        or snapshot.latency_ms != receipt.latency_ms
        or snapshot.observed_at != receipt.finished_at
        or health_after.last_source_sync_run_id != receipt.source_sync_run_id
        or health_after.observed_at != receipt.finished_at
    ):
        raise ValueError("health snapshot lineage 与 terminal observation 不一致")


def _validate_alert_lineage(
    snapshot: SourceHealthSnapshotProjection,
    alert: SourceAlertOutboxEvent,
) -> None:
    """校验 alert 与 bound health snapshot 的 exact lineage。

    Args:
        snapshot: Bound provider snapshot。
        alert: Semantic outbox event。

    Raises:
        ValueError: identity/version/status/error/time 任一漂移时抛出。
    """

    if (
        alert.tenant_id != snapshot.tenant_id
        or alert.subscription_id != snapshot.subscription_id
        or alert.source_sync_run_id != snapshot.source_sync_run_id
        or alert.health_snapshot_id != snapshot.snapshot_id
        or alert.health_state_version != snapshot.health_state_version
        or alert.target_status is not snapshot.status
        or alert.safe_error_code is not snapshot.safe_error_code
        or alert.created_at != snapshot.observed_at
    ):
        raise ValueError("alert lineage 与 health snapshot 不一致")


__all__ = [
    "SourceOperationAcquireAction",
    "SourceOperationAcquireDecision",
    "SourceOperationAcquireRequest",
    "SourceOperationEffectiveState",
    "SourceOperationState",
    "SourceTerminalRecordAction",
    "SourceTerminalRecordDecision",
    "SourceTerminalRecordRequest",
]
