"""Source Sync operation acquire/terminal owner 的直接测试。"""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

import dayu.investment.domain.source_operation as source_operation_module
from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantId
from dayu.investment.domain.source import (
    SourceDefinitionId,
    SourceKind,
    SourceSubscriptionId,
    SubscriptionStatus,
)
from dayu.investment.domain.source_evidence import (
    SourceDocumentEvidence,
    SourceFinsTerminalCandidate,
    SourceNoProviderReason,
    SourceNoProviderTerminalCandidate,
    SourceSyncAttemptReceipt,
    build_source_evidence_locator_document,
    build_source_sync_attempt_receipt,
    build_source_sync_result,
)
from dayu.investment.domain.source_health import (
    SourceAlertKind,
    SourceHealthProjection,
    SourceHealthSnapshotProjection,
    SourceHealthStatus,
    build_source_alert_outbox_event,
)
from dayu.investment.domain.source_operation import (
    SourceOperationAcquireAction,
    SourceOperationAcquireDecision,
    SourceOperationAcquireRequest,
    SourceOperationEffectiveState,
    SourceOperationState,
    SourceTerminalRecordAction,
    SourceTerminalRecordDecision,
    SourceTerminalRecordRequest,
)
from dayu.investment.domain.source_payload import (
    SourceExecutionBinding,
    SourceExecutionSnapshot,
    build_source_execution_snapshot_document,
)
from dayu.investment.domain.source_sync import (
    FINS_SOURCE_DEFINITION_KEY,
    SOURCE_SYNC_JOB_DESCRIPTOR,
    FinsDisclosureSubscriptionConfig,
    SourceBindingDisposition,
    SourceConnectorKey,
    SourceSyncErrorCode,
    SourceSyncOrigin,
    SourceSyncOutcome,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_NOW = datetime(2026, 8, 12, 9, 30, tzinfo=_UTC)
_TENANT_ID = TenantId("tenant-source-operation")
_SUBSCRIPTION_ID = SourceSubscriptionId("00000000-0000-4000-8000-000000000051")
_DEFINITION_ID = UUID("00000000-0000-4000-8000-000000000052")
_JOB_ID = UUID("00000000-0000-4000-8000-000000000053")
_ATTEMPT_ID = UUID("00000000-0000-4000-8000-000000000054")
_OPERATION_ID = UUID("00000000-0000-4000-8000-000000000055")
_RUN_ID = UUID("00000000-0000-4000-8000-000000000056")


def _snapshot() -> SourceExecutionSnapshot:
    """返回 acquire 使用的 frozen snapshot。"""

    binding = SourceExecutionBinding(
        tenant_id=_TENANT_ID,
        source_definition_id=SourceDefinitionId("00000000-0000-4000-8000-000000000057"),
        source_definition_version=1,
        source_key=FINS_SOURCE_DEFINITION_KEY,
        source_kind=SourceKind.FILING,
        subscription_id=_SUBSCRIPTION_ID,
        subscription_version=1,
        subscription_status=SubscriptionStatus.ENABLED,
        security_company_id=CompanyId("company-source-operation"),
        security_id=SecurityId("security-source-operation"),
        security_version=1,
        security_ticker="AAPL",
        exchange_mic="XNAS",
        security_is_active=True,
        connector_key=SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1,
        config=FinsDisclosureSubscriptionConfig(
            forms=("10-K",),
            lookback_days=1,
            freshness_max_age_days=7,
            failing_after=2,
            disable_after=4,
        ),
    )
    return SourceExecutionSnapshot(
        binding=binding,
        canonical_ticker="AAPL",
        query_start_date=date(2026, 8, 12),
        query_end_date=date(2026, 8, 12),
    )


def _document_evidence() -> SourceDocumentEvidence:
    """返回 succeeded/partial receipt 使用的 pathless evidence。"""

    locator = build_source_evidence_locator_document(
        repository_id="dayu.fins.public.v1",
        ticker="AAPL",
        document_id="operation-doc-1",
        source_kind="filing",
        artifact_kind="source",
        document_version="v1",
        source_fingerprint="b" * 64,
        primary_content_sha256="c" * 64,
        locator_kind="document",
        locator_content_sha256="d" * 64,
    )
    return SourceDocumentEvidence(
        document_id="operation-doc-1",
        form_type="10-K",
        source_observed_date=date(2026, 8, 12),
        locator=locator,
        locator_sha256=locator.document.sha256,
    )


def _receipt(
    *,
    outcome: SourceSyncOutcome = SourceSyncOutcome.NO_CHANGE,
    error: SourceSyncErrorCode | None = None,
    retry: bool = False,
    run_id: UUID = _RUN_ID,
) -> SourceSyncAttemptReceipt:
    """返回 operation lineage 使用的 closed canonical receipt。"""

    documents: tuple[SourceDocumentEvidence, ...] = ()
    downloaded = 0
    failed = 0
    if outcome in {SourceSyncOutcome.SUCCEEDED, SourceSyncOutcome.PARTIAL}:
        documents = (_document_evidence(),)
        downloaded = 1
    if outcome is SourceSyncOutcome.PARTIAL or (
        outcome is SourceSyncOutcome.FAILED and error is SourceSyncErrorCode.PROVIDER_UNAVAILABLE
    ):
        failed = 1
    latest_source_observed_date = documents[0].source_observed_date if documents else None
    return build_source_sync_attempt_receipt(
        tenant_id=_TENANT_ID,
        source_sync_run_id=run_id,
        subscription_id=_SUBSCRIPTION_ID,
        job_id=_JOB_ID,
        producer_attempt_id=_ATTEMPT_ID,
        payload_sha256="a" * 64,
        execution_snapshot_sha256=build_source_execution_snapshot_document(_snapshot()).sha256,
        outcome=outcome,
        retry_recommended=retry,
        documents=documents,
        records_discovered=downloaded + failed,
        records_ingested=downloaded,
        records_downloaded=downloaded,
        records_reused=0,
        records_ignored=0,
        records_failed=failed,
        latest_source_observed_date=latest_source_observed_date,
        safe_error_code=error,
        started_at=_NOW,
        finished_at=_NOW + timedelta(milliseconds=50),
        latency_ms=50,
    )


def _health(
    *,
    status: SourceHealthStatus = SourceHealthStatus.HEALTHY,
    failures: int = 0,
    error: SourceSyncErrorCode | None = None,
    version: int = 1,
    run_id: UUID = _RUN_ID,
) -> SourceHealthProjection:
    """返回 terminal decision 使用的 persisted health head。"""

    return SourceHealthProjection(
        tenant_id=_TENANT_ID,
        subscription_id=_SUBSCRIPTION_ID,
        status=status,
        consecutive_failures=failures,
        safe_error_code=error,
        version=version,
        last_source_sync_run_id=run_id,
        observed_at=_NOW + timedelta(milliseconds=50),
    )


def _snapshot_projection(
    *,
    status: SourceHealthStatus = SourceHealthStatus.HEALTHY,
    failures: int = 0,
    error: SourceSyncErrorCode | None = None,
    version: int = 1,
    run_id: UUID = _RUN_ID,
    snapshot_id: UUID = UUID("00000000-0000-4000-8000-000000000058"),
) -> SourceHealthSnapshotProjection:
    """返回与 receipt/head 同 lineage 的 provider snapshot。"""

    return SourceHealthSnapshotProjection(
        snapshot_id=snapshot_id,
        tenant_id=_TENANT_ID,
        subscription_id=_SUBSCRIPTION_ID,
        source_sync_run_id=run_id,
        health_state_version=version,
        status=status,
        consecutive_failures=failures,
        latency_ms=50,
        safe_error_code=error,
        observed_at=_NOW + timedelta(milliseconds=50),
        created_at=_NOW + timedelta(milliseconds=50),
    )


def _no_change_candidate() -> SourceFinsTerminalCandidate:
    """返回合法无变化 Fins candidate。"""

    return SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.NO_CHANGE,
        proposed_safe_error_code=None,
        documents=(),
        records_discovered=0,
        records_downloaded=0,
        records_reused=0,
        records_ignored=0,
        records_failed=0,
        latest_source_observed_date=None,
    )


def test_operation_closed_enums_and_exact_dto_fields_are_stable() -> None:
    """Operation closed enums 与四个 DTO 精确字段必须稳定。"""

    assert {member.value for member in SourceOperationState} == {"active", "terminal"}
    assert {member.value for member in SourceOperationEffectiveState} == {"live", "terminal"}
    assert {member.value for member in SourceOperationAcquireAction} == {"acquired", "busy", "terminal_replay"}
    assert {member.value for member in SourceTerminalRecordAction} == {
        "recorded",
        "lease_lost",
        "job_not_live",
        "stale_subscription",
    }
    assert tuple(field.name for field in fields(SourceOperationAcquireRequest)) == (
        "origin",
        "definition_id",
        "descriptor",
        "job_id",
        "attempt_id",
        "attempt_number",
        "payload_sha256",
        "candidate_execution_snapshot",
    )
    assert tuple(field.name for field in fields(SourceOperationAcquireDecision)) == (
        "action",
        "effective_state",
        "operation_id",
        "generation",
        "execution_snapshot",
        "execution_snapshot_sha256",
        "binding_disposition",
        "terminal_result",
        "terminal_receipt",
    )
    assert tuple(field.name for field in fields(SourceTerminalRecordRequest)) == (
        "operation_id",
        "job_id",
        "attempt_id",
        "attempt_number",
        "expected_generation",
        "expected_execution_snapshot_sha256",
        "candidate",
    )
    assert tuple(field.name for field in fields(SourceTerminalRecordDecision)) == (
        "action",
        "result",
        "receipt",
        "health_after",
        "health_snapshot",
        "alert_event",
    )


def test_acquire_request_enforces_descriptor_lineage_hash_and_origin_snapshot_matrix() -> None:
    """Acquire request 必须携带 fixed descriptor 并闭合 manual/scheduled snapshot matrix。"""

    snapshot = _snapshot()
    manual = SourceOperationAcquireRequest(
        origin=SourceSyncOrigin.MANUAL,
        definition_id=_DEFINITION_ID,
        descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
        job_id=_JOB_ID,
        attempt_id=_ATTEMPT_ID,
        attempt_number=1,
        payload_sha256="a" * 64,
        candidate_execution_snapshot=snapshot,
    )
    scheduled = replace(
        manual,
        origin=SourceSyncOrigin.SCHEDULED,
        candidate_execution_snapshot=None,
    )
    assert manual.candidate_execution_snapshot is snapshot
    assert scheduled.candidate_execution_snapshot is None
    for invalid in (
        {"origin": SourceSyncOrigin.MANUAL, "candidate_execution_snapshot": None},
        {"origin": SourceSyncOrigin.SCHEDULED, "candidate_execution_snapshot": snapshot},
        {"attempt_number": 0},
        {"attempt_number": True},
        {"payload_sha256": "A" * 64},
        {"descriptor": replace(SOURCE_SYNC_JOB_DESCRIPTOR, max_attempts=4)},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(manual, **invalid)


def test_acquire_decision_accepts_acquired_busy_and_terminal_replay_exact_matrices() -> None:
    """Acquire decision 三个 action 的 required/None 矩阵必须精确。"""

    snapshot = _snapshot()
    snapshot_sha = build_source_execution_snapshot_document(snapshot).sha256
    acquired = SourceOperationAcquireDecision(
        action=SourceOperationAcquireAction.ACQUIRED,
        effective_state=SourceOperationEffectiveState.LIVE,
        operation_id=_OPERATION_ID,
        generation=1,
        execution_snapshot=snapshot,
        execution_snapshot_sha256=snapshot_sha,
        binding_disposition=SourceBindingDisposition.READY,
        terminal_result=None,
        terminal_receipt=None,
    )
    busy = SourceOperationAcquireDecision(
        action=SourceOperationAcquireAction.BUSY,
        effective_state=SourceOperationEffectiveState.LIVE,
        operation_id=_OPERATION_ID,
        generation=None,
        execution_snapshot=None,
        execution_snapshot_sha256=None,
        binding_disposition=None,
        terminal_result=None,
        terminal_receipt=None,
    )
    receipt = _receipt()
    result = build_source_sync_result(receipt)
    replay = SourceOperationAcquireDecision(
        action=SourceOperationAcquireAction.TERMINAL_REPLAY,
        effective_state=SourceOperationEffectiveState.TERMINAL,
        operation_id=_OPERATION_ID,
        generation=None,
        execution_snapshot=None,
        execution_snapshot_sha256=None,
        binding_disposition=None,
        terminal_result=result,
        terminal_receipt=receipt,
    )
    assert acquired.generation == 1
    assert busy.operation_id == _OPERATION_ID
    assert replay.terminal_result == result


def test_acquire_decision_rejects_presence_state_hash_and_replay_lineage_drift() -> None:
    """Acquire decision 对 state/presence/hash 与 replay lineage 漂移 fail closed。"""

    snapshot = _snapshot()
    snapshot_sha = build_source_execution_snapshot_document(snapshot).sha256
    acquired = SourceOperationAcquireDecision(
        SourceOperationAcquireAction.ACQUIRED,
        SourceOperationEffectiveState.LIVE,
        _OPERATION_ID,
        1,
        snapshot,
        snapshot_sha,
        SourceBindingDisposition.READY,
        None,
        None,
    )
    for invalid in (
        {"effective_state": SourceOperationEffectiveState.TERMINAL},
        {"generation": None},
        {"generation": 0},
        {"execution_snapshot": None},
        {"execution_snapshot_sha256": "f" * 64},
        {"binding_disposition": None},
        {"terminal_result": build_source_sync_result(_receipt())},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(acquired, **invalid)

    busy = replace(
        acquired,
        action=SourceOperationAcquireAction.BUSY,
        generation=None,
        execution_snapshot=None,
        execution_snapshot_sha256=None,
        binding_disposition=None,
    )
    with pytest.raises(ValueError):
        replace(busy, generation=1)
    receipt = _receipt()
    replay = SourceOperationAcquireDecision(
        SourceOperationAcquireAction.TERMINAL_REPLAY,
        SourceOperationEffectiveState.TERMINAL,
        _OPERATION_ID,
        None,
        None,
        None,
        None,
        build_source_sync_result(receipt),
        receipt,
    )
    other_receipt = _receipt(run_id=UUID("00000000-0000-4000-8000-000000000059"))
    with pytest.raises(ValueError):
        replace(replay, terminal_result=build_source_sync_result(other_receipt))
    with pytest.raises(ValueError):
        replace(replay, generation=1)


def test_terminal_request_accepts_only_closed_candidate_union_and_strict_lineage() -> None:
    """Terminal request 只接 Fins/no-provider union，不接最终 receipt/result。"""

    request = SourceTerminalRecordRequest(
        operation_id=_OPERATION_ID,
        job_id=_JOB_ID,
        attempt_id=_ATTEMPT_ID,
        attempt_number=1,
        expected_generation=1,
        expected_execution_snapshot_sha256=build_source_execution_snapshot_document(_snapshot()).sha256,
        candidate=_no_change_candidate(),
    )
    no_provider = replace(
        request,
        candidate=SourceNoProviderTerminalCandidate(SourceNoProviderReason.DISABLED),
    )
    assert isinstance(no_provider.candidate, SourceNoProviderTerminalCandidate)
    for invalid in (
        {"attempt_number": 0},
        {"expected_generation": True},
        {"expected_execution_snapshot_sha256": "bad"},
        {"candidate": _receipt()},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(request, **invalid)


def test_terminal_live_loss_decisions_require_every_result_field_none() -> None:
    """lease_lost/job_not_live 必须是完全空结果 decision。"""

    for action in (SourceTerminalRecordAction.LEASE_LOST, SourceTerminalRecordAction.JOB_NOT_LIVE):
        decision = SourceTerminalRecordDecision(action, None, None, None, None, None)
        assert decision.result is None
        with pytest.raises(ValueError):
            replace(decision, health_after=_health())


def test_recorded_terminal_decision_closes_result_receipt_health_snapshot_and_alert_lineage() -> None:
    """Recorded decision 必须逐值闭合 receipt/result/head/snapshot/alert lineage。"""

    receipt = _receipt(
        outcome=SourceSyncOutcome.FAILED,
        error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        retry=True,
    )
    result = build_source_sync_result(receipt)
    health = _health(
        status=SourceHealthStatus.DEGRADED,
        failures=1,
        error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
    )
    snapshot = _snapshot_projection(
        status=SourceHealthStatus.DEGRADED,
        failures=1,
        error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
    )
    alert = build_source_alert_outbox_event(
        health_snapshot=snapshot,
        alert_kind=SourceAlertKind.DEGRADED,
    )
    decision = SourceTerminalRecordDecision(
        SourceTerminalRecordAction.RECORDED,
        result,
        receipt,
        health,
        snapshot,
        alert,
    )
    assert decision.alert_event == alert
    with pytest.raises(ValueError):
        replace(decision, result=build_source_sync_result(_receipt()))
    with pytest.raises(ValueError):
        replace(decision, health_after=replace(health, version=2))
    with pytest.raises(ValueError):
        replace(decision, health_after=replace(health, observed_at=_NOW))
    with pytest.raises(ValueError):
        replace(
            decision,
            health_after=replace(
                health,
                last_source_sync_run_id=UUID("00000000-0000-4000-8000-000000000061"),
            ),
        )
    with pytest.raises(ValueError):
        replace(decision, health_snapshot=replace(snapshot, health_state_version=2))
    with pytest.raises(ValueError):
        replace(decision, health_snapshot=replace(snapshot, latency_ms=51))
    with pytest.raises(ValueError):
        replace(decision, health_snapshot=None)
    other_snapshot = replace(
        snapshot,
        snapshot_id=UUID("00000000-0000-4000-8000-000000000060"),
    )
    other_alert = build_source_alert_outbox_event(
        health_snapshot=other_snapshot,
        alert_kind=SourceAlertKind.DEGRADED,
    )
    with pytest.raises(ValueError):
        replace(decision, alert_event=other_alert)


def test_recorded_terminal_decision_snapshot_presence_tracks_health_advance_exactly() -> None:
    """Recorded 仅在本 receipt 推进 health 时强制 snapshot，no-op 禁止伪造证据。"""

    receipt = _receipt()
    result = build_source_sync_result(receipt)
    advanced_health = _health()
    advanced_snapshot = _snapshot_projection()
    advanced = SourceTerminalRecordDecision(
        SourceTerminalRecordAction.RECORDED,
        result,
        receipt,
        advanced_health,
        advanced_snapshot,
        None,
    )
    assert advanced.health_snapshot == advanced_snapshot
    with pytest.raises(ValueError):
        replace(advanced, health_snapshot=None)

    old_health = _health(
        status=SourceHealthStatus.DISABLED,
        failures=4,
        error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        run_id=UUID("00000000-0000-4000-8000-000000000062"),
    )
    old_health = replace(old_health, observed_at=_NOW)
    no_op = SourceTerminalRecordDecision(
        SourceTerminalRecordAction.RECORDED,
        result,
        receipt,
        old_health,
        None,
        None,
    )
    assert no_op.health_snapshot is None
    for drift in (
        {"health_snapshot": advanced_snapshot},
        {
            "alert_event": build_source_alert_outbox_event(
                health_snapshot=replace(
                    advanced_snapshot,
                    status=SourceHealthStatus.DEGRADED,
                    consecutive_failures=1,
                    safe_error_code=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
                ),
                alert_kind=SourceAlertKind.DEGRADED,
            )
        },
    ):
        with pytest.raises(ValueError):
            replace(no_op, **drift)


@pytest.mark.parametrize(
    (
        "outcome",
        "receipt_error",
        "retry",
        "health_status",
        "health_failures",
        "health_error",
        "alert_kind",
    ),
    [
        (
            SourceSyncOutcome.SKIPPED_DISABLED,
            None,
            False,
            SourceHealthStatus.HEALTHY,
            0,
            None,
            None,
        ),
        (
            SourceSyncOutcome.FAILED,
            SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
            True,
            SourceHealthStatus.HEALTHY,
            0,
            None,
            None,
        ),
        (
            SourceSyncOutcome.NO_CHANGE,
            None,
            False,
            SourceHealthStatus.DEGRADED,
            1,
            SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
            SourceAlertKind.DEGRADED,
        ),
    ],
)
def test_recorded_health_advance_rejects_outcome_status_and_error_contradictions(
    outcome: SourceSyncOutcome,
    receipt_error: SourceSyncErrorCode | None,
    retry: bool,
    health_status: SourceHealthStatus,
    health_failures: int,
    health_error: SourceSyncErrorCode | None,
    alert_kind: SourceAlertKind | None,
) -> None:
    """Recorded 必须拒绝 review 实证的三种 receipt/health 矛盾证据链。"""

    receipt = _receipt(outcome=outcome, error=receipt_error, retry=retry)
    health = _health(
        status=health_status,
        failures=health_failures,
        error=health_error,
    )
    snapshot = _snapshot_projection(
        status=health_status,
        failures=health_failures,
        error=health_error,
    )
    alert = (
        build_source_alert_outbox_event(
            health_snapshot=snapshot,
            alert_kind=alert_kind,
        )
        if alert_kind is not None
        else None
    )
    with pytest.raises(ValueError):
        SourceTerminalRecordDecision(
            SourceTerminalRecordAction.RECORDED,
            build_source_sync_result(receipt),
            receipt,
            health,
            snapshot,
            alert,
        )


@pytest.mark.parametrize(
    ("outcome", "error", "retry"),
    [
        (SourceSyncOutcome.SUCCEEDED, None, False),
        (SourceSyncOutcome.NO_CHANGE, None, False),
        (SourceSyncOutcome.PARTIAL, SourceSyncErrorCode.PARTIAL_BATCH, True),
        (SourceSyncOutcome.FAILED, SourceSyncErrorCode.PROVIDER_UNAVAILABLE, True),
    ],
)
def test_recorded_provider_outcomes_allow_late_disabled_health_noop(
    outcome: SourceSyncOutcome,
    error: SourceSyncErrorCode | None,
    retry: bool,
) -> None:
    """并发 disabled 的旧 head 对所有 provider outcome 保持 sticky no-op。"""

    receipt = _receipt(outcome=outcome, error=error, retry=retry)
    disabled = _health(
        status=SourceHealthStatus.DISABLED,
        failures=4,
        error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        run_id=UUID("00000000-0000-4000-8000-000000000064"),
    )
    decision = SourceTerminalRecordDecision(
        SourceTerminalRecordAction.RECORDED,
        build_source_sync_result(receipt),
        receipt,
        disabled,
        None,
        None,
    )
    assert decision.health_after is disabled
    assert decision.health_snapshot is None
    assert decision.alert_event is None
    old_healthy = _health(
        status=SourceHealthStatus.HEALTHY,
        failures=0,
        error=None,
        run_id=UUID("00000000-0000-4000-8000-000000000066"),
    )
    with pytest.raises(ValueError):
        replace(decision, health_after=old_healthy)


def test_stale_terminal_decision_requires_stale_receipt_and_never_snapshot_or_alert() -> None:
    """Stale decision 必须绑定 stale receipt、保留 health 且不推进 snapshot/alert。"""

    receipt = _receipt(
        outcome=SourceSyncOutcome.STALE_SUBSCRIPTION,
        error=SourceSyncErrorCode.STALE_SUBSCRIPTION,
    )
    prior_health = replace(
        _health(run_id=UUID("00000000-0000-4000-8000-000000000065")),
        observed_at=_NOW,
    )
    stale = SourceTerminalRecordDecision(
        SourceTerminalRecordAction.STALE_SUBSCRIPTION,
        build_source_sync_result(receipt),
        receipt,
        prior_health,
        None,
        None,
    )
    assert stale.receipt == receipt
    with pytest.raises(ValueError):
        replace(stale, receipt=_receipt(), result=build_source_sync_result(_receipt()))
    with pytest.raises(ValueError):
        replace(stale, health_snapshot=_snapshot_projection())
    with pytest.raises(ValueError):
        replace(stale, health_after=_health())
    ordinary = SourceTerminalRecordDecision(
        SourceTerminalRecordAction.RECORDED,
        build_source_sync_result(_receipt()),
        _receipt(),
        _health(
            status=SourceHealthStatus.DISABLED,
            failures=4,
            error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
            run_id=UUID("00000000-0000-4000-8000-000000000063"),
        ),
        None,
        None,
    )
    with pytest.raises(ValueError):
        replace(ordinary, receipt=receipt, result=build_source_sync_result(receipt))


def test_source_operation_effective_state_is_closed_to_live_and_terminal_and_residual_active_has_no_public_projection() -> (
    None
):
    """Effective state 只公开 live/terminal，物理 residual ACTIVE 没有公共投影。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Enum、公开符号或 decision 字段扩张时抛出。
    """

    assert tuple(member.value for member in SourceOperationEffectiveState) == ("live", "terminal")
    assert "ACTIVE" not in SourceOperationEffectiveState.__members__
    assert SourceOperationState.ACTIVE.value == "active"
    assert tuple(field.name for field in fields(SourceOperationAcquireDecision)) == (
        "action",
        "effective_state",
        "operation_id",
        "generation",
        "execution_snapshot",
        "execution_snapshot_sha256",
        "binding_disposition",
        "terminal_result",
        "terminal_receipt",
    )
    public_symbols = vars(source_operation_module)
    assert {
        "SourceOperationResidualState",
        "SourceOperationRetryPending",
        "SourceOperationAbandoned",
        "SourceOperationInvariantFailure",
    }.isdisjoint(public_symbols)
    assert "active" not in {member.value for member in SourceOperationEffectiveState}


def test_acquire_decision_presence_matrix_is_exact_for_acquired_busy_and_terminal_replay() -> None:
    """Acquired、busy、replay 的 state 与逐字段 presence matrix 必须精确。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一 required/forbidden 字段或 state 组合被错误接受时抛出。
    """

    snapshot = _snapshot()
    snapshot_sha = build_source_execution_snapshot_document(snapshot).sha256
    receipt = _receipt()
    result = build_source_sync_result(receipt)
    acquired = SourceOperationAcquireDecision(
        SourceOperationAcquireAction.ACQUIRED,
        SourceOperationEffectiveState.LIVE,
        _OPERATION_ID,
        1,
        snapshot,
        snapshot_sha,
        SourceBindingDisposition.READY,
        None,
        None,
    )
    busy = SourceOperationAcquireDecision(
        SourceOperationAcquireAction.BUSY,
        SourceOperationEffectiveState.LIVE,
        _OPERATION_ID,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    replay = SourceOperationAcquireDecision(
        SourceOperationAcquireAction.TERMINAL_REPLAY,
        SourceOperationEffectiveState.TERMINAL,
        _OPERATION_ID,
        None,
        None,
        None,
        None,
        result,
        receipt,
    )

    for drift in (
        {"operation_id": None},
        {"effective_state": SourceOperationEffectiveState.TERMINAL},
        {"generation": None},
        {"execution_snapshot": None},
        {"execution_snapshot_sha256": None},
        {"binding_disposition": None},
        {"terminal_result": result},
        {"terminal_receipt": receipt},
        {"action": SourceOperationAcquireAction.BUSY},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(acquired, **drift)
    for drift in (
        {"operation_id": None},
        {"effective_state": SourceOperationEffectiveState.TERMINAL},
        {"generation": 1},
        {"execution_snapshot": snapshot},
        {"execution_snapshot_sha256": snapshot_sha},
        {"binding_disposition": SourceBindingDisposition.READY},
        {"terminal_result": result},
        {"terminal_receipt": receipt},
        {"action": SourceOperationAcquireAction.ACQUIRED},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(busy, **drift)
    for drift in (
        {"operation_id": None},
        {"effective_state": SourceOperationEffectiveState.LIVE},
        {"generation": 1},
        {"execution_snapshot": snapshot},
        {"execution_snapshot_sha256": snapshot_sha},
        {"binding_disposition": SourceBindingDisposition.READY},
        {"terminal_result": None},
        {"terminal_receipt": None},
        {"action": SourceOperationAcquireAction.BUSY},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(replay, **drift)


def test_acquire_request_requires_manual_snapshot_and_forbids_scheduled_candidate_snapshot() -> None:
    """Manual acquire 必须携带 snapshot，scheduled 必须明确不携带 candidate。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Origin/snapshot presence 的任一反向组合被接受时抛出。
    """

    snapshot = _snapshot()
    manual = SourceOperationAcquireRequest(
        SourceSyncOrigin.MANUAL,
        _DEFINITION_ID,
        SOURCE_SYNC_JOB_DESCRIPTOR,
        _JOB_ID,
        _ATTEMPT_ID,
        1,
        "a" * 64,
        snapshot,
    )
    scheduled = SourceOperationAcquireRequest(
        SourceSyncOrigin.SCHEDULED,
        _DEFINITION_ID,
        SOURCE_SYNC_JOB_DESCRIPTOR,
        _JOB_ID,
        _ATTEMPT_ID,
        1,
        "a" * 64,
        None,
    )
    assert manual.candidate_execution_snapshot is snapshot
    assert scheduled.candidate_execution_snapshot is None
    with pytest.raises(ValueError):
        replace(manual, candidate_execution_snapshot=None)
    with pytest.raises(ValueError):
        replace(scheduled, candidate_execution_snapshot=snapshot)


def test_acquire_request_origin_definition_descriptor_and_snapshot_matrix_rejects_every_cross_combination() -> None:
    """Origin、definition type、fixed descriptor 与 snapshot 的全组合只接受两种。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 16 项矩阵不是精确两项合法，或跨命名空间 UUID 被比较时抛出。
    """

    snapshot = _snapshot()
    coincident_job_definition_uuid = UUID(str(snapshot.binding.source_definition_id))
    baseline = SourceOperationAcquireRequest(
        SourceSyncOrigin.MANUAL,
        coincident_job_definition_uuid,
        SOURCE_SYNC_JOB_DESCRIPTOR,
        _JOB_ID,
        _ATTEMPT_ID,
        1,
        "a" * 64,
        snapshot,
    )
    drifted_descriptor = replace(SOURCE_SYNC_JOB_DESCRIPTOR, lease_duration_seconds=901)
    accepted: list[SourceOperationAcquireRequest] = []
    for origin in (SourceSyncOrigin.MANUAL, SourceSyncOrigin.SCHEDULED):
        for candidate_snapshot in (snapshot, None):
            for descriptor in (SOURCE_SYNC_JOB_DESCRIPTOR, drifted_descriptor):
                for definition_id in (
                    coincident_job_definition_uuid,
                    snapshot.binding.source_definition_id,
                ):
                    should_accept = (
                        descriptor == SOURCE_SYNC_JOB_DESCRIPTOR
                        and isinstance(definition_id, UUID)
                        and (
                            (origin is SourceSyncOrigin.MANUAL and candidate_snapshot is snapshot)
                            or (origin is SourceSyncOrigin.SCHEDULED and candidate_snapshot is None)
                        )
                    )
                    if should_accept:
                        accepted.append(
                            replace(
                                baseline,
                                origin=origin,
                                definition_id=definition_id,
                                descriptor=descriptor,
                                candidate_execution_snapshot=candidate_snapshot,
                            )
                        )
                    else:
                        with pytest.raises((TypeError, ValueError)):
                            replace(
                                baseline,
                                origin=origin,
                                definition_id=definition_id,
                                descriptor=descriptor,
                                candidate_execution_snapshot=candidate_snapshot,
                            )
    assert len(accepted) == 2
    assert {request.origin for request in accepted} == {
        SourceSyncOrigin.MANUAL,
        SourceSyncOrigin.SCHEDULED,
    }
    assert all(request.definition_id == coincident_job_definition_uuid for request in accepted)


def test_terminal_request_cannot_supply_final_ids_clock_receipt_result_health_or_alert() -> None:
    """Terminal request 只接 caller candidate/lineage，禁止最终事实与外部 clock。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 字段 surface 扩张或任一 final DTO 被当作 candidate 接受时抛出。
    """

    request = SourceTerminalRecordRequest(
        _OPERATION_ID,
        _JOB_ID,
        _ATTEMPT_ID,
        1,
        1,
        build_source_execution_snapshot_document(_snapshot()).sha256,
        _no_change_candidate(),
    )
    assert tuple(field.name for field in fields(SourceTerminalRecordRequest)) == (
        "operation_id",
        "job_id",
        "attempt_id",
        "attempt_number",
        "expected_generation",
        "expected_execution_snapshot_sha256",
        "candidate",
    )
    assert {
        "source_sync_run_id",
        "finished_at",
        "clock",
        "receipt",
        "result",
        "health_after",
        "health_snapshot",
        "alert_event",
    }.isdisjoint(field.name for field in fields(SourceTerminalRecordRequest))

    receipt = _receipt(
        outcome=SourceSyncOutcome.FAILED,
        error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        retry=True,
    )
    result = build_source_sync_result(receipt)
    health = _health(
        status=SourceHealthStatus.DEGRADED,
        failures=1,
        error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
    )
    health_snapshot = _snapshot_projection(
        status=SourceHealthStatus.DEGRADED,
        failures=1,
        error=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
    )
    alert = build_source_alert_outbox_event(
        health_snapshot=health_snapshot,
        alert_kind=SourceAlertKind.DEGRADED,
    )
    for forbidden_candidate in (
        _RUN_ID,
        _NOW,
        receipt,
        result,
        health,
        health_snapshot,
        alert,
    ):
        with pytest.raises(TypeError):
            replace(request, candidate=forbidden_candidate)
