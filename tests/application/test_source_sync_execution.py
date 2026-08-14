"""Source Sync 私有 execution Service 与 handler 的 application 测试。"""

from __future__ import annotations

import ast
import asyncio
import inspect
import threading
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TypeAlias, get_type_hints
from uuid import UUID

import pytest

import dayu.services as services_package
import dayu.services.source_sync_execution as execution_module
from dayu.investment.connectors.source import (
    SourceConnectorProtocol,
    SourceConnectorRegistry,
)
from dayu.investment.domain.identifiers import (
    CompanyId,
    Principal,
    SecurityId,
    TenantId,
    TenantScope,
)
from dayu.investment.domain.jobs import (
    JobCancellationSignalProtocol,
    JobCompletion,
    JobExecutionRequest,
    JobFailure,
    SafeJobErrorCode,
    build_canonical_document,
)
from dayu.investment.domain.source import (
    SourceDefinitionId,
    SourceKind,
    SourceSubscriptionId,
    SubscriptionStatus,
)
from dayu.investment.domain.source_evidence import (
    SourceConnectorSyncAction,
    SourceConnectorSyncDecision,
    SourceConnectorSyncRequest,
    SourceFinsTerminalCandidate,
    SourceSyncAttemptReceipt,
    build_source_sync_attempt_receipt,
    build_source_sync_result,
)
from dayu.investment.domain.source_health import (
    SourceHealthProjection,
    SourceHealthReenableRequest,
    SourceHealthSnapshotCursor,
    SourceHealthSnapshotPage,
    SourceHealthSnapshotProjection,
    SourceHealthStatus,
)
from dayu.investment.domain.source_operation import (
    SourceOperationAcquireAction,
    SourceOperationAcquireDecision,
    SourceOperationAcquireRequest,
    SourceOperationEffectiveState,
    SourceTerminalRecordAction,
    SourceTerminalRecordDecision,
    SourceTerminalRecordRequest,
)
from dayu.investment.domain.source_payload import (
    ManualSourceSyncPayload,
    SourceExecutionBinding,
    SourceExecutionSnapshot,
    build_manual_source_sync_payload_document,
    build_source_execution_snapshot_document,
)
from dayu.investment.domain.source_sync import (
    FINS_SOURCE_DEFINITION_KEY,
    SOURCE_SYNC_JOB_DESCRIPTOR,
    SOURCE_SYNC_JOB_TYPE,
    FinsDisclosureSubscriptionConfig,
    SourceBindingDisposition,
    SourceConnectorKey,
    SourceSyncExecutionRejected,
    SourceSyncExecutionRejectionCode,
    SourceSyncOutcome,
    SourceSyncRepositoryFailure,
    SourceSyncRepositoryFailureCode,
    SourceSyncRequestRejected,
    SourceSyncRequestRejectionCode,
)
from dayu.services.job_service import JobExecutionHandlerProtocol
from dayu.services.source_sync_execution import (
    SourceSyncExecutionHandler,
    SourceSyncExecutionService,
    SourceSyncExecutionServiceProtocol,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_NOW = datetime(2026, 8, 14, 9, 30, tzinfo=_UTC)
_OPERATION_ID = UUID("00000000-0000-4000-8000-000000000401")
_RUN_ID = UUID("00000000-0000-4000-8000-000000000402")
_SNAPSHOT_ID = UUID("00000000-0000-4000-8000-000000000403")

ExecutionRaised: TypeAlias = (
    SourceSyncRequestRejected | SourceSyncExecutionRejected | SourceSyncRepositoryFailure | RuntimeError
)


class _CancellationSignal:
    """可显式置位并记录同步读取次数的领域取消信号。"""

    def __init__(self) -> None:
        """初始化未取消状态。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.requested = False
        self.read_calls = 0
        self._event = asyncio.Event()

    def request(self) -> None:
        """置位领域取消。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.requested = True
        self._event.set()

    def is_cancel_requested(self) -> bool:
        """返回并记录当前取消状态。

        Args:
            无。

        Returns:
            当前是否已请求取消。

        Raises:
            无。
        """

        self.read_calls += 1
        return self.requested

    async def wait_cancel_requested(self) -> None:
        """等待领域取消置位。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        await self._event.wait()


class _RecordingExecutionService:
    """记录 handler raw delegation 的 execution protocol fake。"""

    def __init__(self, result: JobCompletion | JobFailure) -> None:
        """保存固定结果。

        Args:
            result: 每次调用原样返回的闭合结果。

        Returns:
            无。

        Raises:
            无。
        """

        self.result = result
        self.calls: list[tuple[TenantScope, JobExecutionRequest, JobCancellationSignalProtocol]] = []

    async def execute_source_sync(
        self,
        scope: TenantScope,
        request: JobExecutionRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """记录三个参数的对象 identity 并返回固定结果。

        Args:
            scope: 可信租户范围。
            request: Execution request。
            cancellation: 领域取消信号。

        Returns:
            构造时保存的同一个结果对象。

        Raises:
            无。
        """

        self.calls.append((scope, request, cancellation))
        return self.result


class _Connector(SourceConnectorProtocol):
    """返回闭合 decision、可置位取消或抛 closed error 的 connector。"""

    def __init__(
        self,
        decision: SourceConnectorSyncDecision,
        *,
        error: ExecutionRaised | None = None,
        cancellation_to_request: _CancellationSignal | None = None,
    ) -> None:
        """保存 connector 行为。

        Args:
            decision: 正常调用返回的闭合 decision。
            error: 可空 closed/hostile runtime error。
            cancellation_to_request: 返回前可置位的领域取消信号。

        Returns:
            无。

        Raises:
            无。
        """

        self.decision = decision
        self.error = error
        self.cancellation_to_request = cancellation_to_request
        self.calls: list[tuple[SourceConnectorSyncRequest, JobCancellationSignalProtocol]] = []

    @property
    def connector_key(self) -> SourceConnectorKey:
        """返回唯一可执行 Fins connector key。

        Args:
            无。

        Returns:
            Fins market disclosure connector key。

        Raises:
            无。
        """

        return SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1

    async def sync(
        self,
        request: SourceConnectorSyncRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> SourceConnectorSyncDecision:
        """记录调用，按配置置位取消、抛错或返回 decision。

        Args:
            request: Frozen connector execution request。
            cancellation: 同一领域取消信号。

        Returns:
            配置的 closed connector decision。

        Raises:
            SourceSyncRequestRejected: 配置该 closed error 时抛出。
            SourceSyncExecutionRejected: 配置该 closed error 时抛出。
            SourceSyncRepositoryFailure: 配置该 closed error 时抛出。
            RuntimeError: 配置未列出的 hostile error 时原样抛出。
        """

        self.calls.append((request, cancellation))
        if self.cancellation_to_request is not None:
            self.cancellation_to_request.request()
        if self.error is not None:
            raise self.error
        return self.decision


class _ExecutionRepository:
    """同步 repository fake，提供线程 barrier 与 closed failure seams。"""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        acquire_decision: SourceOperationAcquireDecision,
        terminal_decision: SourceTerminalRecordDecision,
        acquire_error: ExecutionRaised | None = None,
        terminal_error: ExecutionRaised | None = None,
        block_acquire: bool = False,
        block_terminal: bool = False,
    ) -> None:
        """保存决策、错误与可控线程 barrier。

        Args:
            loop: 当前 event loop，用于线程安全通知测试协程。
            acquire_decision: 正常 acquire 返回值。
            terminal_decision: 正常 terminal 返回值。
            acquire_error: 可空 acquire failure。
            terminal_error: 可空 terminal failure。
            block_acquire: 是否等待 acquire release event。
            block_terminal: 是否等待 terminal release event。

        Returns:
            无。

        Raises:
            无。
        """

        self._loop = loop
        self.acquire_decision = acquire_decision
        self.terminal_decision = terminal_decision
        self.acquire_error = acquire_error
        self.terminal_error = terminal_error
        self.block_acquire = block_acquire
        self.block_terminal = block_terminal
        self.acquire_entered = asyncio.Event()
        self.acquire_finished = asyncio.Event()
        self.terminal_entered = asyncio.Event()
        self.terminal_finished = asyncio.Event()
        self.acquire_release = threading.Event()
        self.terminal_release = threading.Event()
        self.acquire_calls: list[tuple[TenantScope, SourceOperationAcquireRequest]] = []
        self.terminal_calls: list[tuple[TenantScope, SourceTerminalRecordRequest]] = []
        self.terminal_mutations = 0

    def _notify(self, event: asyncio.Event) -> None:
        """从 repository thread 通知 event loop。

        Args:
            event: 待置位的 asyncio event。

        Returns:
            无。

        Raises:
            无。
        """

        self._loop.call_soon_threadsafe(event.set)

    def acquire_operation(
        self,
        scope: TenantScope,
        request: SourceOperationAcquireRequest,
    ) -> SourceOperationAcquireDecision:
        """记录 acquire，在 barrier 后返回或抛配置结果。

        Args:
            scope: 可信租户范围。
            request: Strict acquire request。

        Returns:
            配置的 acquire decision。

        Raises:
            SourceSyncRequestRejected: 配置该 closed error 时抛出。
            SourceSyncExecutionRejected: 配置该 closed error 时抛出。
            SourceSyncRepositoryFailure: 配置该 closed error 时抛出。
            RuntimeError: barrier 超时或配置 hostile error 时抛出。
        """

        self.acquire_calls.append((scope, request))
        self._notify(self.acquire_entered)
        try:
            if self.block_acquire and not self.acquire_release.wait(timeout=5.0):
                raise RuntimeError("acquire barrier timeout")
            if self.acquire_error is not None:
                raise self.acquire_error
            return self.acquire_decision
        finally:
            self._notify(self.acquire_finished)

    def record_terminal(
        self,
        scope: TenantScope,
        request: SourceTerminalRecordRequest,
    ) -> SourceTerminalRecordDecision:
        """记录 terminal，在 barrier 后原子模拟 mutation 或抛错。

        Args:
            scope: 可信租户范围。
            request: Closed terminal request。

        Returns:
            配置的 terminal decision。

        Raises:
            SourceSyncRequestRejected: 配置该 closed error 时抛出。
            SourceSyncExecutionRejected: 配置该 hostile closed error 时抛出。
            SourceSyncRepositoryFailure: 配置该 closed error 时抛出。
            RuntimeError: barrier 超时或配置 hostile error 时抛出。
        """

        self.terminal_calls.append((scope, request))
        self._notify(self.terminal_entered)
        try:
            if self.block_terminal and not self.terminal_release.wait(timeout=5.0):
                raise RuntimeError("terminal barrier timeout")
            if self.terminal_error is not None:
                raise self.terminal_error
            self.terminal_mutations += 1
            return self.terminal_decision
        finally:
            self._notify(self.terminal_finished)

    def get_executable_binding(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceExecutionBinding:
        """拒绝 execution Service 不应发起的独立 binding read。

        Args:
            scope: 可信租户范围。
            subscription_id: Subscription identity。

        Returns:
            本拒绝 seam 不返回。

        Raises:
            AssertionError: 本 execution 路径调用该方法时抛出。
        """

        raise AssertionError("execution service 不得独立读取 binding")

    def get_source_receipt(
        self,
        scope: TenantScope,
        source_sync_run_id: UUID,
    ) -> SourceSyncAttemptReceipt | None:
        """拒绝 execution Service 不应发起的 receipt read。

        Args:
            scope: 可信租户范围。
            source_sync_run_id: Source run identity。

        Returns:
            本拒绝 seam 不返回。

        Raises:
            AssertionError: 本 execution 路径调用该方法时抛出。
        """

        raise AssertionError("execution service 不得独立读取 receipt")

    def get_health(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceHealthProjection:
        """拒绝 execution Service 不应发起的 health read。

        Args:
            scope: 可信租户范围。
            subscription_id: Subscription identity。

        Returns:
            本拒绝 seam 不返回。

        Raises:
            AssertionError: 本 execution 路径调用该方法时抛出。
        """

        raise AssertionError("execution service 不得独立读取 health")

    def list_health_snapshots(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
        cursor: SourceHealthSnapshotCursor | None,
        *,
        limit: int,
    ) -> SourceHealthSnapshotPage:
        """拒绝 execution Service 不应发起的 snapshot list。

        Args:
            scope: 可信租户范围。
            subscription_id: Subscription identity。
            cursor: Keyset cursor。
            limit: Page size。

        Returns:
            本拒绝 seam 不返回。

        Raises:
            AssertionError: 本 execution 路径调用该方法时抛出。
        """

        raise AssertionError("execution service 不得列出 health snapshots")

    def reenable_health(
        self,
        scope: TenantScope,
        request: SourceHealthReenableRequest,
    ) -> SourceHealthProjection:
        """拒绝 execution Service 不应发起的 health mutation。

        Args:
            scope: 可信租户范围。
            request: Health re-enable request。

        Returns:
            本拒绝 seam 不返回。

        Raises:
            AssertionError: 本 execution 路径调用该方法时抛出。
        """

        raise AssertionError("execution service 不得 re-enable health")


def _scope() -> TenantScope:
    """返回固定 trusted scope。

    Args:
        无。

    Returns:
        Test tenant scope。

    Raises:
        无。
    """

    return Principal(
        tenant_id=TenantId("00000000-0000-0000-0000-000000000401"),
        user_id="source-execution-user",
    ).to_scope()


def _snapshot(scope: TenantScope) -> SourceExecutionSnapshot:
    """返回可执行的单日 frozen snapshot。

    Args:
        scope: 提供 tenant identity 的 trusted scope。

    Returns:
        Strict Source execution snapshot。

    Raises:
        无。
    """

    return SourceExecutionSnapshot(
        binding=SourceExecutionBinding(
            tenant_id=scope.tenant_id,
            source_definition_id=SourceDefinitionId("00000000-0000-4000-8000-000000000404"),
            source_definition_version=1,
            source_key=FINS_SOURCE_DEFINITION_KEY,
            source_kind=SourceKind.FILING,
            subscription_id=SourceSubscriptionId("00000000-0000-4000-8000-000000000405"),
            subscription_version=2,
            subscription_status=SubscriptionStatus.ENABLED,
            security_company_id=CompanyId("source-execution-company"),
            security_id=SecurityId("source-execution-security"),
            security_version=3,
            security_ticker="AAPL",
            exchange_mic="XNAS",
            security_is_active=True,
            connector_key=SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1,
            config=FinsDisclosureSubscriptionConfig(
                forms=("10-K",),
                lookback_days=1,
                freshness_max_age_days=2,
                failing_after=2,
                disable_after=4,
            ),
        ),
        canonical_ticker="AAPL",
        query_start_date=date(2026, 8, 14),
        query_end_date=date(2026, 8, 14),
    )


def _request(scope: TenantScope) -> JobExecutionRequest:
    """返回 strict manual Source Sync execution request。

    Args:
        scope: 提供 tenant identity 的 trusted scope。

    Returns:
        Canonical Job execution request。

    Raises:
        无。
    """

    snapshot = _snapshot(scope)
    payload = build_manual_source_sync_payload_document(
        ManualSourceSyncPayload(
            subscription_id=snapshot.binding.subscription_id,
            expected_subscription_version=snapshot.binding.subscription_version,
            trigger_id=UUID("00000000-0000-4000-8000-000000000406"),
            execution_snapshot=snapshot,
            request_fingerprint="a" * 64,
        )
    )
    return JobExecutionRequest(
        tenant_id=scope.tenant_id,
        definition_id=UUID("00000000-0000-4000-8000-000000000407"),
        job_id=UUID("00000000-0000-4000-8000-000000000408"),
        attempt_id=UUID("00000000-0000-4000-8000-000000000409"),
        attempt_number=1,
        descriptor=SOURCE_SYNC_JOB_DESCRIPTOR,
        payload=payload,
        deadline_at=_NOW + timedelta(minutes=15),
    )


def _candidate() -> SourceFinsTerminalCandidate:
    """返回合法 no-change provider candidate。

    Args:
        无。

    Returns:
        Closed Fins terminal candidate。

    Raises:
        无。
    """

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


def _connector_decision(*, cancelled: bool = False) -> SourceConnectorSyncDecision:
    """返回 completed 或 cancelled connector decision。

    Args:
        cancelled: 是否返回 cancelled action。

    Returns:
        Closed connector decision。

    Raises:
        无。
    """

    if cancelled:
        return SourceConnectorSyncDecision(action=SourceConnectorSyncAction.CANCELLED, candidate=None)
    return SourceConnectorSyncDecision(action=SourceConnectorSyncAction.COMPLETED, candidate=_candidate())


def _acquire_decision(
    scope: TenantScope,
    *,
    disposition: SourceBindingDisposition = SourceBindingDisposition.READY,
) -> SourceOperationAcquireDecision:
    """返回 acquired/live decision。

    Args:
        scope: Snapshot tenant scope。
        disposition: Repository 冻结的 binding disposition。

    Returns:
        Valid acquired decision。

    Raises:
        无。
    """

    snapshot = _snapshot(scope)
    snapshot_sha256 = build_source_execution_snapshot_document(snapshot).sha256
    return SourceOperationAcquireDecision(
        action=SourceOperationAcquireAction.ACQUIRED,
        effective_state=SourceOperationEffectiveState.LIVE,
        operation_id=_OPERATION_ID,
        generation=1,
        execution_snapshot=snapshot,
        execution_snapshot_sha256=snapshot_sha256,
        binding_disposition=disposition,
        terminal_result=None,
        terminal_receipt=None,
    )


def _busy_decision() -> SourceOperationAcquireDecision:
    """返回 busy/live decision。

    Args:
        无。

    Returns:
        Valid busy decision。

    Raises:
        无。
    """

    return SourceOperationAcquireDecision(
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


def _terminal_decision(scope: TenantScope, request: JobExecutionRequest) -> SourceTerminalRecordDecision:
    """返回带 canonical result 的 recorded terminal decision。

    Args:
        scope: Receipt tenant scope。
        request: Receipt Job lineage。

    Returns:
        Valid recorded terminal decision。

    Raises:
        无。
    """

    snapshot_sha256 = build_source_execution_snapshot_document(_snapshot(scope)).sha256
    finished_at = _NOW + timedelta(milliseconds=50)
    receipt = build_source_sync_attempt_receipt(
        tenant_id=scope.tenant_id,
        source_sync_run_id=_RUN_ID,
        subscription_id=_snapshot(scope).binding.subscription_id,
        job_id=request.job_id,
        producer_attempt_id=request.attempt_id,
        payload_sha256=request.payload.sha256,
        execution_snapshot_sha256=snapshot_sha256,
        outcome=SourceSyncOutcome.NO_CHANGE,
        retry_recommended=False,
        documents=(),
        records_discovered=0,
        records_ingested=0,
        records_downloaded=0,
        records_reused=0,
        records_ignored=0,
        records_failed=0,
        latest_source_observed_date=None,
        safe_error_code=None,
        started_at=_NOW,
        finished_at=finished_at,
        latency_ms=50,
    )
    health = SourceHealthProjection(
        tenant_id=scope.tenant_id,
        subscription_id=receipt.subscription_id,
        status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
        safe_error_code=None,
        version=1,
        last_source_sync_run_id=_RUN_ID,
        observed_at=finished_at,
    )
    health_snapshot = SourceHealthSnapshotProjection(
        snapshot_id=_SNAPSHOT_ID,
        tenant_id=scope.tenant_id,
        subscription_id=receipt.subscription_id,
        source_sync_run_id=_RUN_ID,
        health_state_version=1,
        status=SourceHealthStatus.HEALTHY,
        consecutive_failures=0,
        latency_ms=50,
        safe_error_code=None,
        observed_at=finished_at,
        created_at=finished_at,
    )
    return SourceTerminalRecordDecision(
        action=SourceTerminalRecordAction.RECORDED,
        result=build_source_sync_result(receipt),
        receipt=receipt,
        health_after=health,
        health_snapshot=health_snapshot,
        alert_event=None,
    )


def _live_loss_decision(action: SourceTerminalRecordAction) -> SourceTerminalRecordDecision:
    """返回 lease_lost 或 job_not_live 空结果 decision。

    Args:
        action: Live-loss terminal action。

    Returns:
        Valid empty terminal decision。

    Raises:
        ValueError: action 不是 live-loss closed member 时抛出。
    """

    return SourceTerminalRecordDecision(
        action=action,
        result=None,
        receipt=None,
        health_after=None,
        health_snapshot=None,
        alert_event=None,
    )


def _replay_decision(scope: TenantScope, request: JobExecutionRequest) -> SourceOperationAcquireDecision:
    """返回 byte-identical terminal replay decision。

    Args:
        scope: Receipt tenant scope。
        request: Receipt Job lineage。

    Returns:
        Valid terminal replay decision。

    Raises:
        AssertionError: Recorded fixture 缺少 required result/receipt 时抛出。
    """

    terminal = _terminal_decision(scope, request)
    if terminal.result is None or terminal.receipt is None:
        raise AssertionError("recorded fixture 必须有 result/receipt")
    return SourceOperationAcquireDecision(
        action=SourceOperationAcquireAction.TERMINAL_REPLAY,
        effective_state=SourceOperationEffectiveState.TERMINAL,
        operation_id=_OPERATION_ID,
        generation=None,
        execution_snapshot=None,
        execution_snapshot_sha256=None,
        binding_disposition=None,
        terminal_result=terminal.result,
        terminal_receipt=terminal.receipt,
    )


def _service(repository: _ExecutionRepository, connector: _Connector) -> SourceSyncExecutionService:
    """构造仅含一个 connector 的 execution Service。

    Args:
        repository: 同步 Source repository fake。
        connector: 唯一 connector fake。

    Returns:
        Production execution Service。

    Raises:
        ValueError: Connector registry identity 重复时抛出。
    """

    return SourceSyncExecutionService(
        repository=repository,
        connector_registry=SourceConnectorRegistry((connector,)),
    )


async def _run_handler(
    repository: _ExecutionRepository,
    connector: _Connector,
    scope: TenantScope,
    request: JobExecutionRequest,
    cancellation: _CancellationSignal,
) -> JobCompletion | JobFailure:
    """经 production handler 运行一次真实 execution Service。

    Args:
        repository: 同步 Source repository fake。
        connector: Connector fake。
        scope: 可信租户范围。
        request: Job execution request。
        cancellation: 领域取消信号。

    Returns:
        Handler 原样返回的 closed result。

    Raises:
        asyncio.CancelledError: Pre-PONR outer cancellation 时传播。
        RuntimeError: 未列出的 hostile execution error 原样传播。
    """

    handler = SourceSyncExecutionHandler(execution_service=_service(repository, connector))
    return await handler.execute(scope, request, cancellation)


async def _checkpoint() -> None:
    """通过 FIFO call-soon barrier 让已排队的 task 恢复一次。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    reached = asyncio.Event()
    asyncio.get_running_loop().call_soon(reached.set)
    await reached.wait()


def _assert_failure(
    result: JobCompletion | JobFailure,
    code: SafeJobErrorCode,
    *,
    retryable: bool,
) -> None:
    """断言 execution 返回 exact safe failure。

    Args:
        result: 待核对的 closed result。
        code: 期望 safe code。
        retryable: 期望 retryability。

    Returns:
        无。

    Raises:
        AssertionError: Result 的类型、code 或 retryability 不符时抛出。
    """

    assert isinstance(result, JobFailure)
    assert result.safe_error_code is code
    assert result.retryable is retryable


@pytest.mark.asyncio
async def test_source_sync_execution_protocol_handler_constructor_and_one_call_delegation_are_exact() -> None:
    """Protocol、handler constructor、fixed job type 与一次 raw delegation 必须精确。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 签名、类型、identity 或调用次数漂移时抛出。
    """

    protocol_signature = inspect.signature(SourceSyncExecutionServiceProtocol.execute_source_sync)
    assert tuple(protocol_signature.parameters) == ("self", "scope", "request", "cancellation")
    assert all(
        parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and parameter.default is inspect.Parameter.empty
        for parameter in protocol_signature.parameters.values()
    )
    protocol_hints = get_type_hints(SourceSyncExecutionServiceProtocol.execute_source_sync)
    assert protocol_hints == {
        "scope": TenantScope,
        "request": JobExecutionRequest,
        "cancellation": JobCancellationSignalProtocol,
        "return": JobCompletion | JobFailure,
    }

    constructor = inspect.signature(SourceSyncExecutionHandler.__init__)
    assert tuple(constructor.parameters) == ("self", "execution_service")
    assert constructor.parameters["execution_service"].kind is inspect.Parameter.KEYWORD_ONLY
    assert constructor.parameters["execution_service"].default is inspect.Parameter.empty
    assert (
        get_type_hints(SourceSyncExecutionHandler.__init__)["execution_service"] is SourceSyncExecutionServiceProtocol
    )

    scope = _scope()
    request = _request(scope)
    cancellation = _CancellationSignal()
    expected = JobFailure(safe_error_code=SafeJobErrorCode.SOURCE_OPERATION_BUSY, retryable=True)
    execution_service = _RecordingExecutionService(expected)
    handler = SourceSyncExecutionHandler(execution_service=execution_service)
    assert isinstance(handler, JobExecutionHandlerProtocol)
    assert handler.job_type == SOURCE_SYNC_JOB_TYPE
    result = await handler.execute(scope, request, cancellation)
    assert result is expected
    assert len(execution_service.calls) == 1
    delegated_scope, delegated_request, delegated_cancellation = execution_service.calls[0]
    assert delegated_scope is scope
    assert delegated_request is request
    assert delegated_cancellation is cancellation


def test_source_sync_execution_owner_does_not_import_facade_fins_concrete_session_host_or_agent() -> None:
    """Execution owner 依赖方向、offload helper 与 private export 必须闭合。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Import、export、offload 或 delegation contract 漂移时抛出。
    """

    repository_root = Path(__file__).parents[2]
    production_path = repository_root / "dayu/services/source_sync_execution.py"
    facade_path = repository_root / "dayu/services/investment_sources.py"
    production_tree = ast.parse(production_path.read_text(encoding="utf-8"))
    facade_tree = ast.parse(facade_path.read_text(encoding="utf-8"))

    imported_modules = {
        node.module
        for node in ast.walk(production_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name for node in ast.walk(production_tree) if isinstance(node, ast.Import) for alias in node.names
    )
    assert "dayu.services.investment_sources" not in imported_modules
    assert not any(module.startswith("dayu.fins") for module in imported_modules)
    assert not any(module.startswith("sqlalchemy") for module in imported_modules)
    assert not any("host" in module.lower() or "agent" in module.lower() for module in imported_modules)

    imported_symbols = {
        alias.name for node in ast.walk(production_tree) if isinstance(node, ast.ImportFrom) for alias in node.names
    }
    assert imported_symbols.isdisjoint(
        {
            "FinsSourceConnector",
            "FinsService",
            "Session",
            "Engine",
            "Host",
            "Agent",
            "InvestmentSourcesService",
        }
    )
    assert not {
        "getattr",
        "hasattr",
        "cast",
    }.intersection(node.id for node in ast.walk(production_tree) if isinstance(node, ast.Name))

    facade_imports = {
        node.module for node in ast.walk(facade_tree) if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    facade_imports.update(
        alias.name for node in ast.walk(facade_tree) if isinstance(node, ast.Import) for alias in node.names
    )
    assert "dayu.services.source_sync_execution" not in facade_imports
    assert "SourceSyncExecutionService" not in vars(services_package)
    assert "SourceSyncExecutionHandler" not in vars(services_package)
    assert "SourceSyncExecutionServiceProtocol" not in vars(services_package)

    functions = {
        node.name: node for node in production_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for helper_name in (
        "_await_acquire_operation",
        "_await_record_terminal_after_point_of_no_return",
    ):
        helper = functions[helper_name]
        assert (
            sum(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create_task"
                for node in ast.walk(helper)
            )
            == 1
        )
        assert (
            sum(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "to_thread"
                for node in ast.walk(helper)
            )
            == 1
        )

    handler_class = next(
        node
        for node in production_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SourceSyncExecutionHandler"
    )
    handler_execute = next(
        node for node in handler_class.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute"
    )
    delegation_calls = [
        node
        for node in ast.walk(handler_execute)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute_source_sync"
    ]
    assert len(delegation_calls) == 1


@pytest.mark.asyncio
async def test_pre_terminal_owned_thread_reaps_blocking_acquire_then_propagates_first_of_repeated_outer_cancellations_without_fins() -> (
    None
):
    """Pre-PONR repeated cancel 必须先回收 acquire thread，再传播第一份且零 Fins。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Cancel precedence、thread ownership 或零副作用证据漂移时抛出。
    """

    loop = asyncio.get_running_loop()
    scope = _scope()
    request = _request(scope)
    typed_request_error = SourceSyncRequestRejected(SourceSyncRequestRejectionCode.SNAPSHOT_MISMATCH)
    typed_execution_error = SourceSyncExecutionRejected(SourceSyncExecutionRejectionCode.LEASE_LOST)
    typed_repository_error = SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED)
    hostile_error = RuntimeError("hostile acquire exception")
    for error in (
        None,
        typed_request_error,
        typed_execution_error,
        typed_repository_error,
        hostile_error,
    ):
        repository = _ExecutionRepository(
            loop=loop,
            acquire_decision=_acquire_decision(scope),
            terminal_decision=_terminal_decision(scope, request),
            acquire_error=error,
            block_acquire=True,
        )
        connector = _Connector(_connector_decision())
        cancellation = _CancellationSignal()
        task = asyncio.create_task(_run_handler(repository, connector, scope, request, cancellation))

        await asyncio.wait_for(repository.acquire_entered.wait(), timeout=1.0)
        error_name = type(error).__name__ if error is not None else "success"
        first_marker = f"first-pre-ponr-{error_name}"
        second_marker = f"second-pre-ponr-{error_name}"
        assert task.cancel(first_marker)
        await _checkpoint()
        assert task.cancel(second_marker)
        await _checkpoint()
        repository.acquire_release.set()
        with pytest.raises(asyncio.CancelledError) as raised:
            await task

        assert raised.value.args == (first_marker,)
        assert raised.value.args[0] is first_marker
        assert repository.acquire_finished.is_set()
        assert len(repository.acquire_calls) == 1
        assert repository.terminal_calls == []
        assert repository.terminal_mutations == 0
        assert connector.calls == []
        assert cancellation.read_calls == 0


@pytest.mark.asyncio
async def test_terminal_point_of_no_return_repeated_outer_cancellation_returns_durable_completion_after_owned_thread_commit() -> (
    None
):
    """Terminal PONR 后 repeated cancel 不得覆盖 durable completion 或遗留线程。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Durable result、mutation 或 thread reap 证据漂移时抛出。
    """

    loop = asyncio.get_running_loop()
    scope = _scope()
    request = _request(scope)
    terminal = _terminal_decision(scope, request)
    typed_terminal_error = SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.PERSISTED_INVARIANT)
    typed_terminal_error.args = ("misleading outer cancellation",)
    for error in (None, typed_terminal_error):
        repository = _ExecutionRepository(
            loop=loop,
            acquire_decision=_acquire_decision(scope),
            terminal_decision=terminal,
            terminal_error=error,
            block_terminal=True,
        )
        connector = _Connector(_connector_decision())
        cancellation = _CancellationSignal()
        task = asyncio.create_task(_run_handler(repository, connector, scope, request, cancellation))

        await asyncio.wait_for(repository.terminal_entered.wait(), timeout=1.0)
        assert task.cancel("first-post-ponr")
        await _checkpoint()
        assert task.cancel("second-post-ponr")
        await _checkpoint()
        repository.terminal_release.set()
        result = await task

        if error is None:
            assert isinstance(result, JobCompletion)
            assert terminal.result is not None
            assert result.result is terminal.result.result
            assert repository.terminal_mutations == 1
        else:
            _assert_failure(result, SafeJobErrorCode.REPOSITORY_FAILURE, retryable=True)
            assert repository.terminal_mutations == 0
        assert repository.terminal_finished.is_set()
        assert len(repository.acquire_calls) == 1
        assert len(repository.terminal_calls) == 1
        assert len(connector.calls) == 1
        assert cancellation.read_calls == 1


@pytest.mark.asyncio
async def test_terminal_final_domain_cancel_check_before_thread_schedule_returns_interrupted_with_zero_source_mutation() -> (
    None
):
    """Provider 后最后 domain cancel 为真时必须在线程创建前 interrupted、零 mutation。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Final check 顺序、safe failure 或零 mutation 证据漂移时抛出。
    """

    loop = asyncio.get_running_loop()
    scope = _scope()
    request = _request(scope)
    repository = _ExecutionRepository(
        loop=loop,
        acquire_decision=_acquire_decision(scope),
        terminal_decision=_terminal_decision(scope, request),
    )
    cancellation = _CancellationSignal()
    connector = _Connector(
        _connector_decision(),
        cancellation_to_request=cancellation,
    )

    result = await _run_handler(repository, connector, scope, request, cancellation)

    _assert_failure(result, SafeJobErrorCode.SOURCE_INTERRUPTED, retryable=True)
    assert len(repository.acquire_calls) == 1
    assert len(connector.calls) == 1
    assert cancellation.read_calls == 1
    assert repository.terminal_calls == []
    assert repository.terminal_mutations == 0
    assert not repository.terminal_entered.is_set()


@pytest.mark.asyncio
async def test_source_handler_maps_closed_request_execution_and_repository_errors_without_message_guessing() -> None:
    """Handler 只透传 Service 的 closed type mapping，不按 message/shape 猜分支。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Closed mapping、retryability、zero side effect 或 passthrough 漂移时抛出。
    """

    loop = asyncio.get_running_loop()
    scope = _scope()
    request = _request(scope)
    terminal = _terminal_decision(scope, request)
    completed_connector = _connector_decision()

    malformed_payload = build_canonical_document(
        {"schema_version": 1},
        schema_name="investment.not-source-sync",
        schema_version=1,
    )
    malformed_repository = _ExecutionRepository(
        loop=loop,
        acquire_decision=_acquire_decision(scope),
        terminal_decision=terminal,
    )
    malformed_result = await _run_handler(
        malformed_repository,
        _Connector(completed_connector),
        scope,
        replace(request, payload=malformed_payload),
        _CancellationSignal(),
    )
    _assert_failure(malformed_result, SafeJobErrorCode.SOURCE_INVALID, retryable=False)
    assert malformed_repository.acquire_calls == []

    wrong_descriptor_repository = _ExecutionRepository(
        loop=loop,
        acquire_decision=_acquire_decision(scope),
        terminal_decision=terminal,
    )
    wrong_descriptor_result = await _run_handler(
        wrong_descriptor_repository,
        _Connector(completed_connector),
        scope,
        replace(
            request,
            descriptor=replace(SOURCE_SYNC_JOB_DESCRIPTOR, job_type="investment.other-source.v1"),
        ),
        _CancellationSignal(),
    )
    _assert_failure(wrong_descriptor_result, SafeJobErrorCode.SOURCE_INVALID, retryable=False)
    assert wrong_descriptor_repository.acquire_calls == []

    for code in SourceSyncRequestRejectionCode:
        error = SourceSyncRequestRejected(code)
        error.args = ("misleading repository timeout",)
        repository = _ExecutionRepository(
            loop=loop,
            acquire_decision=_acquire_decision(scope),
            terminal_decision=terminal,
            acquire_error=error,
        )
        result = await _run_handler(
            repository,
            _Connector(completed_connector),
            scope,
            request,
            _CancellationSignal(),
        )
        _assert_failure(result, SafeJobErrorCode.SOURCE_INVALID, retryable=False)
        assert repository.terminal_calls == []

    for code in SourceSyncExecutionRejectionCode:
        error = SourceSyncExecutionRejected(code)
        error.args = ("misleading invalid payload",)
        repository = _ExecutionRepository(
            loop=loop,
            acquire_decision=_acquire_decision(scope),
            terminal_decision=terminal,
            acquire_error=error,
        )
        result = await _run_handler(
            repository,
            _Connector(completed_connector),
            scope,
            request,
            _CancellationSignal(),
        )
        _assert_failure(result, SafeJobErrorCode.SOURCE_INTERRUPTED, retryable=True)

    for code in SourceSyncRepositoryFailureCode:
        error = SourceSyncRepositoryFailure(code)
        error.args = ("misleading binding conflict",)
        repository = _ExecutionRepository(
            loop=loop,
            acquire_decision=_acquire_decision(scope),
            terminal_decision=terminal,
            acquire_error=error,
        )
        result = await _run_handler(
            repository,
            _Connector(completed_connector),
            scope,
            request,
            _CancellationSignal(),
        )
        _assert_failure(result, SafeJobErrorCode.REPOSITORY_FAILURE, retryable=True)

    for error, expected_code, retryable in (
        (
            SourceSyncRequestRejected(SourceSyncRequestRejectionCode.SNAPSHOT_MISMATCH),
            SafeJobErrorCode.SOURCE_INVALID,
            False,
        ),
        (
            SourceSyncExecutionRejected(SourceSyncExecutionRejectionCode.LEASE_LOST),
            SafeJobErrorCode.SOURCE_INTERRUPTED,
            True,
        ),
        (
            SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.TRANSACTION_ABORTED),
            SafeJobErrorCode.REPOSITORY_FAILURE,
            True,
        ),
    ):
        error.args = ("misleading terminal outcome",)
        repository = _ExecutionRepository(
            loop=loop,
            acquire_decision=_acquire_decision(scope),
            terminal_decision=terminal,
            terminal_error=error,
        )
        result = await _run_handler(
            repository,
            _Connector(completed_connector),
            scope,
            request,
            _CancellationSignal(),
        )
        _assert_failure(result, expected_code, retryable=retryable)
        assert repository.terminal_mutations == 0

    for error, expected_code, retryable in (
        (
            SourceSyncRequestRejected(SourceSyncRequestRejectionCode.INVALID_INPUT),
            SafeJobErrorCode.SOURCE_INVALID,
            False,
        ),
        (
            SourceSyncExecutionRejected(SourceSyncExecutionRejectionCode.JOB_NOT_LIVE),
            SafeJobErrorCode.SOURCE_INTERRUPTED,
            True,
        ),
        (
            SourceSyncRepositoryFailure(SourceSyncRepositoryFailureCode.UNAVAILABLE),
            SafeJobErrorCode.REPOSITORY_FAILURE,
            True,
        ),
    ):
        error.args = ("misleading connector response",)
        repository = _ExecutionRepository(
            loop=loop,
            acquire_decision=_acquire_decision(scope),
            terminal_decision=terminal,
        )
        result = await _run_handler(
            repository,
            _Connector(completed_connector, error=error),
            scope,
            request,
            _CancellationSignal(),
        )
        _assert_failure(result, expected_code, retryable=retryable)
        assert repository.terminal_calls == []

    busy_repository = _ExecutionRepository(
        loop=loop,
        acquire_decision=_busy_decision(),
        terminal_decision=terminal,
    )
    busy_result = await _run_handler(
        busy_repository,
        _Connector(completed_connector),
        scope,
        request,
        _CancellationSignal(),
    )
    _assert_failure(busy_result, SafeJobErrorCode.SOURCE_OPERATION_BUSY, retryable=True)

    cancelled_repository = _ExecutionRepository(
        loop=loop,
        acquire_decision=_acquire_decision(scope),
        terminal_decision=terminal,
    )
    cancelled_result = await _run_handler(
        cancelled_repository,
        _Connector(_connector_decision(cancelled=True)),
        scope,
        request,
        _CancellationSignal(),
    )
    _assert_failure(cancelled_result, SafeJobErrorCode.SOURCE_INTERRUPTED, retryable=True)
    assert cancelled_repository.terminal_calls == []

    for action in (SourceTerminalRecordAction.LEASE_LOST, SourceTerminalRecordAction.JOB_NOT_LIVE):
        live_loss_repository = _ExecutionRepository(
            loop=loop,
            acquire_decision=_acquire_decision(scope),
            terminal_decision=_live_loss_decision(action),
        )
        live_loss_result = await _run_handler(
            live_loss_repository,
            _Connector(completed_connector),
            scope,
            request,
            _CancellationSignal(),
        )
        _assert_failure(live_loss_result, SafeJobErrorCode.SOURCE_INTERRUPTED, retryable=True)

    replay = _replay_decision(scope, request)
    replay_repository = _ExecutionRepository(
        loop=loop,
        acquire_decision=replay,
        terminal_decision=terminal,
    )
    replay_result = await _run_handler(
        replay_repository,
        _Connector(completed_connector),
        scope,
        request,
        _CancellationSignal(),
    )
    assert isinstance(replay_result, JobCompletion)
    assert replay.terminal_result is not None
    assert replay_result.result is replay.terminal_result.result

    for disposition in (SourceBindingDisposition.DISABLED, SourceBindingDisposition.STALE):
        no_provider_repository = _ExecutionRepository(
            loop=loop,
            acquire_decision=_acquire_decision(scope, disposition=disposition),
            terminal_decision=_live_loss_decision(SourceTerminalRecordAction.JOB_NOT_LIVE),
        )
        no_provider_connector = _Connector(completed_connector)
        no_provider_result = await _run_handler(
            no_provider_repository,
            no_provider_connector,
            scope,
            request,
            _CancellationSignal(),
        )
        _assert_failure(no_provider_result, SafeJobErrorCode.SOURCE_INTERRUPTED, retryable=True)
        assert no_provider_connector.calls == []
        assert len(no_provider_repository.terminal_calls) == 1

    hostile_error = RuntimeError("hostile unlisted failure")
    hostile_repository = _ExecutionRepository(
        loop=loop,
        acquire_decision=_acquire_decision(scope),
        terminal_decision=terminal,
        acquire_error=hostile_error,
    )
    with pytest.raises(RuntimeError) as raised:
        await _run_handler(
            hostile_repository,
            _Connector(completed_connector),
            scope,
            request,
            _CancellationSignal(),
        )
    assert raised.value is hostile_error


assert execution_module.SourceSyncExecutionServiceProtocol.__module__ == "dayu.services.source_sync_execution"
