"""Durable PlatformWorker、Host-local ports 与 Redis runtime 单元测试。"""

from __future__ import annotations

import ast
import asyncio
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event as ThreadEvent
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from dayu.host.process_intake import ProcessIntakeGate
from dayu.host.worker import (
    PlatformWorker,
    RedisRuntimeState,
    RedisWakeupHint,
    RedisWakeupRead,
    RedisWakeupReadAction,
    RedisWakeupSubscriberProtocol,
    WorkerJobGatewayProtocol,
)
from dayu.investment.config import PlatformQueueMode, PlatformQueueSettings
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.domain.jobs import (
    AgentRunGovernanceAction,
    AgentRunGovernanceCursor,
    AgentRunGovernancePage,
    AgentRunGovernanceResult,
    AttemptReceiptOutcome,
    AttemptState,
    CanonicalJobDocument,
    GenericAttemptReceiptReason,
    JobAttemptReceipt,
    JobCancellationSignalProtocol,
    JobClaim,
    JobCompletion,
    JobFailure,
    JobGovernanceRequiredError,
    JobHandlerDescriptor,
    JobHeartbeatAction,
    JobHeartbeatResult,
    JobLeaseHandle,
    JobRecoveryResult,
    JobRepositoryFailureError,
    JobState,
    SafeJobErrorCode,
    build_canonical_document,
    build_generic_attempt_receipt,
)

if TYPE_CHECKING:
    from dayu.services.job_service import JobService

    def _job_service_structurally_satisfies_worker_gateway(
        service: JobService,
    ) -> WorkerJobGatewayProtocol:
        """让 Pyright 证明 concrete JobService 精确满足 Host-local port。

        Args:
            service: concrete Job Service。

        Returns:
            同一实例的 Host-local structural view。

        Raises:
            无。
        """

        return service


TENANT_UUID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_TENANT_UUID = UUID("22222222-2222-4222-8222-222222222222")
JOB_UUID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ATTEMPT_UUID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
DEFINITION_UUID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
CORRELATION_UUID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
OTHER_JOB_UUID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
OTHER_ATTEMPT_UUID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
NOW = datetime(2026, 8, 12, 0, 0, tzinfo=UTC)
WORKER_ID = "worker-test"


def _scope() -> TenantScope:
    """构造 canonical tenant scope。

    Args:
        无。

    Returns:
        测试 tenant scope。

    Raises:
        无。
    """

    return Principal(
        tenant_id=TenantId(str(TENANT_UUID)),
        user_id="platform-worker-test",
    ).to_scope()


def _settings(
    mode: PlatformQueueMode = PlatformQueueMode.POSTGRES_POLLING,
    *,
    redis_failure_threshold: int = 3,
    redis_health_interval_seconds: float = 0.01,
    governance_failure_threshold: int = 3,
    shutdown_grace_seconds: float = 0.03,
) -> PlatformQueueSettings:
    """构造快速但完全合法的 queue settings。

    Args:
        mode: deployment queue mode。
        redis_failure_threshold: Redis 连续失败阈值。
        redis_health_interval_seconds: degraded health interval。
        governance_failure_threshold: governance repository failure 阈值。
        shutdown_grace_seconds: cooperative drain grace。

    Returns:
        严格 ``PlatformQueueSettings``。

    Raises:
        PlatformSettingsError: 参数违反配置不变量时抛出。
    """

    return PlatformQueueSettings(
        mode=mode,
        poll_interval_seconds=0.01,
        redis_health_interval_seconds=redis_health_interval_seconds,
        redis_failure_threshold=redis_failure_threshold,
        shutdown_grace_seconds=shutdown_grace_seconds,
        empty_poll_jitter_max_seconds=0.01,
        governance_page_size=2,
        governance_failure_threshold=governance_failure_threshold,
    )


def _document() -> CanonicalJobDocument:
    """构造安全 canonical document。

    Args:
        无。

    Returns:
        测试 document。

    Raises:
        无。
    """

    return build_canonical_document(
        {"status": "ok"},
        schema_name="test.worker-result",
        schema_version=1,
    )


def _descriptor() -> JobHandlerDescriptor:
    """构造短 heartbeat 周期 descriptor。

    Args:
        无。

    Returns:
        测试 descriptor。

    Raises:
        无。
    """

    return JobHandlerDescriptor(
        job_type="test.worker",
        payload_schema_name="test.worker-result",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=1,
    )


def _claim() -> JobClaim:
    """构造与 Worker identity 闭合的 claim。

    Args:
        无。

    Returns:
        测试 claim。

    Raises:
        无。
    """

    lease = JobLeaseHandle(
        tenant_id=TenantId(str(TENANT_UUID)),
        job_id=JOB_UUID,
        attempt_id=ATTEMPT_UUID,
        fence=1,
        raw_token="a" * 64,
        acquired_at=NOW,
        expires_at=NOW + timedelta(seconds=1),
    )
    return JobClaim(
        tenant_id=lease.tenant_id,
        definition_id=DEFINITION_UUID,
        job_id=lease.job_id,
        attempt_id=lease.attempt_id,
        attempt_number=1,
        worker_id=WORKER_ID,
        descriptor=_descriptor(),
        payload=_document(),
        lease=lease,
        deadline_at=NOW + timedelta(hours=1),
    )


def _receipt(claim: JobClaim) -> JobAttemptReceipt:
    """构造 successful terminal receipt。

    Args:
        claim: receipt identity 来源。

    Returns:
        immutable attempt receipt。

    Raises:
        无。
    """

    result = _document()
    return JobAttemptReceipt(
        tenant_id=claim.tenant_id,
        job_id=claim.job_id,
        attempt_id=claim.attempt_id,
        outcome=AttemptReceiptOutcome.SUCCEEDED,
        result=result,
        receipt=build_generic_attempt_receipt(
            job_id=claim.job_id,
            attempt_id=claim.attempt_id,
            outcome=AttemptReceiptOutcome.SUCCEEDED,
            reason=GenericAttemptReceiptReason.COMPLETION,
            safe_error_code=None,
            result_ref=result,
        ),
        safe_error_code=None,
        finalized_at=NOW + timedelta(minutes=1),
    )


def _recovery(claim: JobClaim) -> JobRecoveryResult:
    """构造 failed attempt recovery result。

    Args:
        claim: recovery identity 来源。

    Returns:
        closed recovery result。

    Raises:
        无。
    """

    return JobRecoveryResult(
        job_id=claim.job_id,
        attempt_id=claim.attempt_id,
        job_state=JobState.FAILED,
        attempt_state=AttemptState.FAILED,
        receipt=None,
        next_available_at=None,
        safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
    )


def _governance_result(
    action: AgentRunGovernanceAction,
    *,
    current: bool = True,
) -> AgentRunGovernanceResult:
    """构造 current 或 unrelated governance result。

    Args:
        action: closed governance action。
        current: 是否匹配当前 claim identity。

    Returns:
        governance result。

    Raises:
        无。
    """

    safe_error_code: SafeJobErrorCode | None = None
    if action is AgentRunGovernanceAction.STALE:
        safe_error_code = SafeJobErrorCode.CORRELATION_STALE_ATTEMPT
    elif action is AgentRunGovernanceAction.INVARIANT_FAILURE:
        safe_error_code = SafeJobErrorCode.CORRELATION_INVARIANT
    elif action is AgentRunGovernanceAction.NO_HOST_RECOVERED:
        safe_error_code = SafeJobErrorCode.LEASE_EXPIRED
    return AgentRunGovernanceResult(
        correlation_id=(CORRELATION_UUID if current else OTHER_JOB_UUID),
        job_id=(JOB_UUID if current else OTHER_JOB_UUID),
        attempt_id=(ATTEMPT_UUID if current else OTHER_ATTEMPT_UUID),
        action=action,
        safe_error_code=safe_error_code,
    )


def _page(
    *results: AgentRunGovernanceResult,
    cursor: AgentRunGovernanceCursor | None = None,
) -> AgentRunGovernancePage:
    """构造 Service governance page。

    Args:
        *results: ordered result tuple。
        cursor: 可空 next cursor。

    Returns:
        governance page。

    Raises:
        无。
    """

    return AgentRunGovernancePage(results=results, next_cursor=cursor)


class _FakeGateway:
    """可编程 Worker Job gateway fake。"""

    def __init__(self, *, gate: ProcessIntakeGate) -> None:
        """初始化调用记录与默认 closed 结果。

        Args:
            gate: terminal 后可关闭的 shared gate。

        Returns:
            无。

        Raises:
            无。
        """

        self.gate = gate
        self.claim_results: list[JobClaim | None] = []
        self.governance_outcomes: list[AgentRunGovernancePage | JobRepositoryFailureError | RuntimeError] = []
        self.default_governance_page = _page()
        self.handler_result: JobCompletion | JobFailure = JobCompletion(_document())
        self.handler_error: RuntimeError | None = None
        self.handler_started = asyncio.Event()
        self.handler_release = asyncio.Event()
        self.block_handler = False
        self.noncooperative_handler = False
        self.complete_requires_governance = False
        self.stop_after_complete = True
        self.stop_after_fail = True
        self.stop_during_governance = False
        self.recover_calls = 0
        self.claim_calls: list[tuple[TenantScope, str]] = []
        self.execute_calls: list[tuple[TenantScope, JobClaim, JobCancellationSignalProtocol]] = []
        self.heartbeat_calls: list[JobLeaseHandle] = []
        self.complete_calls: list[tuple[JobLeaseHandle, JobCompletion]] = []
        self.fail_calls: list[tuple[JobLeaseHandle, JobFailure]] = []
        self.governance_calls: list[tuple[AgentRunGovernanceCursor | None, int]] = []

    def recover(self, scope: TenantScope) -> tuple[JobRecoveryResult, ...]:
        """记录 startup recovery。

        Args:
            scope: tenant scope。

        Returns:
            空 recovery tuple。

        Raises:
            无。
        """

        del scope
        self.recover_calls += 1
        return ()

    def claim(self, scope: TenantScope, worker_id: str) -> JobClaim | None:
        """返回下一项可编程 claim。

        Args:
            scope: tenant scope。
            worker_id: Worker identity。

        Returns:
            下一 claim；queue 为空时关闭 gate 并返回 ``None``。

        Raises:
            无。
        """

        self.claim_calls.append((scope, worker_id))
        if self.claim_results:
            return self.claim_results.pop(0)
        self.gate.request_stop()
        return None

    async def execute_claim(
        self,
        scope: TenantScope,
        claim: JobClaim,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """记录唯一 Service execution gateway 调用。

        Args:
            scope: tenant scope。
            claim: current claim。
            cancellation: Worker cancellation signal。

        Returns:
            可编程 closed handler result。

        Raises:
            asyncio.CancelledError: cooperative 模式收到 task cancellation 时传播。
        """

        self.execute_calls.append((scope, claim, cancellation))
        cancellation.is_cancel_requested()
        self.handler_started.set()
        if self.block_handler:
            try:
                await self.handler_release.wait()
            except asyncio.CancelledError:
                if not self.noncooperative_handler:
                    raise
                await self.handler_release.wait()
        if self.handler_error is not None:
            raise self.handler_error
        return self.handler_result

    def heartbeat(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
    ) -> JobHeartbeatResult:
        """记录 heartbeat 并返回 same-fence renewal。

        Args:
            scope: tenant scope。
            lease: 当前 lease。

        Returns:
            renewed heartbeat result。

        Raises:
            无。
        """

        del scope
        self.heartbeat_calls.append(lease)
        claim = _claim()
        return JobHeartbeatResult(action=JobHeartbeatAction.RENEWED, claim=claim)

    def complete(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        completion: JobCompletion,
    ) -> JobAttemptReceipt:
        """记录 completion 或要求 correlation governance。

        Args:
            scope: tenant scope。
            lease: 当前 lease。
            completion: safe completion。

        Returns:
            terminal receipt。

        Raises:
            JobGovernanceRequiredError: 配置为 correlation wait 时抛出。
        """

        del scope
        self.complete_calls.append((lease, completion))
        if self.complete_requires_governance:
            raise JobGovernanceRequiredError()
        if self.stop_after_complete:
            self.gate.request_stop()
        return _receipt(_claim())

    def fail(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        failure: JobFailure,
    ) -> JobRecoveryResult:
        """记录 safe failure 并返回 closed recovery。

        Args:
            scope: tenant scope。
            lease: 当前 lease。
            failure: safe failure。

        Returns:
            recovery result。

        Raises:
            无。
        """

        del scope
        self.fail_calls.append((lease, failure))
        if self.stop_after_fail:
            self.gate.request_stop()
        return _recovery(_claim())

    def govern_agent_runs(
        self,
        scope: TenantScope,
        cursor: AgentRunGovernanceCursor | None,
        *,
        limit: int,
    ) -> AgentRunGovernancePage:
        """记录唯一 cursor/limit 并返回下一 outcome。

        Args:
            scope: tenant scope。
            cursor: process-local cursor。
            limit: keyword-only page size。

        Returns:
            governance page。

        Raises:
            JobRepositoryFailureError: 注入 closed repository failure 时抛出。
            RuntimeError: 注入未分类错误时抛出。
        """

        del scope
        self.governance_calls.append((cursor, limit))
        if self.stop_during_governance:
            self.gate.request_stop()
        if not self.governance_outcomes:
            return self.default_governance_page
        outcome = self.governance_outcomes.pop(0)
        if isinstance(outcome, JobRepositoryFailureError):
            raise outcome
        if isinstance(outcome, RuntimeError):
            raise outcome
        return outcome


class _BlockingClaimGateway(_FakeGateway):
    """在线程中阻塞 claim 的 intake barrier fake。"""

    def __init__(self, *, gate: ProcessIntakeGate) -> None:
        """初始化 thread barriers。

        Args:
            gate: shared intake gate。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(gate=gate)
        self.claim_entered = ThreadEvent()
        self.claim_release = ThreadEvent()

    def claim(self, scope: TenantScope, worker_id: str) -> JobClaim | None:
        """等待测试释放后返回一个 claim。

        Args:
            scope: tenant scope。
            worker_id: Worker identity。

        Returns:
            测试 claim。

        Raises:
            无。
        """

        self.claim_calls.append((scope, worker_id))
        self.claim_entered.set()
        self.claim_release.wait(timeout=2)
        return _claim()


class _CancelOrderingGateway(_FakeGateway):
    """记录 PG cancel governance 与后续 handler 的跨 gateway 顺序。"""

    def __init__(self, *, gate: ProcessIntakeGate) -> None:
        """初始化基础 fake 与调用序列。

        Args:
            gate: shared intake gate。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(gate=gate)
        self.call_order: list[str] = []

    def govern_agent_runs(
        self,
        scope: TenantScope,
        cursor: AgentRunGovernanceCursor | None,
        *,
        limit: int,
    ) -> AgentRunGovernancePage:
        """记录治理结果已由 Service 投射完成后才返回。

        Args:
            scope: tenant scope。
            cursor: process-local governance cursor。
            limit: keyword-only page size。

        Returns:
            基础 fake 的 closed governance page。

        Raises:
            JobRepositoryFailureError: 配置仓储失败时传播。
            RuntimeError: 配置程序错误时传播。
        """

        page = super().govern_agent_runs(scope, cursor, limit=limit)
        self.call_order.append("governance_projected")
        return page

    def claim(self, scope: TenantScope, worker_id: str) -> JobClaim | None:
        """记录治理完成后的 PostgreSQL claim。

        Args:
            scope: tenant scope。
            worker_id: Worker identity。

        Returns:
            基础 fake 的下一 claim。

        Raises:
            无。
        """

        self.call_order.append("claim")
        return super().claim(scope, worker_id)

    async def execute_claim(
        self,
        scope: TenantScope,
        claim: JobClaim,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """记录 handler side effect 边界。

        Args:
            scope: tenant scope。
            claim: 当前 claim。
            cancellation: 协作取消信号。

        Returns:
            基础 fake 的 closed handler result。

        Raises:
            asyncio.CancelledError: handler task 被取消时传播。
        """

        self.call_order.append("handler")
        return await super().execute_claim(scope, claim, cancellation)


class _BlockingHeartbeatGateway(_FakeGateway):
    """在线程中阻塞 heartbeat 的 inner-future ownership fake。"""

    def __init__(self, *, gate: ProcessIntakeGate) -> None:
        """初始化 heartbeat thread barriers。

        Args:
            gate: shared intake gate。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(gate=gate)
        self.heartbeat_entered = ThreadEvent()
        self.heartbeat_release = ThreadEvent()

    def heartbeat(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
    ) -> JobHeartbeatResult:
        """等待测试释放后返回 same-fence renewal。

        Args:
            scope: tenant scope。
            lease: 当前 lease。

        Returns:
            renewed heartbeat result。

        Raises:
            无。
        """

        del scope
        self.heartbeat_calls.append(lease)
        self.heartbeat_entered.set()
        self.heartbeat_release.wait(timeout=2)
        return JobHeartbeatResult(
            action=JobHeartbeatAction.RENEWED,
            claim=_claim(),
        )


class _FakeSubscriber:
    """可编程 Worker-owned Redis subscriber fake。"""

    def __init__(self) -> None:
        """初始化 read/subscribe/close 状态。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.reads: list[RedisWakeupRead] = []
        self.resubscribe_results: list[bool] = []
        self.read_calls = 0
        self.resubscribe_calls = 0
        self.close_calls = 0
        self.raise_type_error = False
        self.consume_pending_read_during_repeat_subscribe = False
        self.consumed_during_resubscribe = 0
        self.read_entered = ThreadEvent()
        self.read_release = ThreadEvent()
        self.block_read = False

    def resubscribe(self) -> bool:
        """返回下一 subscribe 结果。

        Args:
            无。

        Returns:
            配置结果；默认成功。

        Raises:
            TypeError: 配置程序错误时抛出。
        """

        self.resubscribe_calls += 1
        if self.raise_type_error:
            raise TypeError("program error")
        if self.consume_pending_read_during_repeat_subscribe and self.resubscribe_calls > 1 and self.reads:
            self.reads.pop(0)
            self.consumed_during_resubscribe += 1
            return False
        if self.resubscribe_results:
            return self.resubscribe_results.pop(0)
        return True

    def get_message(self, *, timeout_seconds: float) -> RedisWakeupRead:
        """返回下一 read；默认 no-message。

        Args:
            timeout_seconds: bounded timeout。

        Returns:
            closed Redis read。

        Raises:
            TypeError: 配置程序错误时抛出。
        """

        del timeout_seconds
        self.read_calls += 1
        if self.block_read:
            self.read_entered.set()
            self.read_release.wait(timeout=1)
        if self.raise_type_error:
            raise TypeError("program error")
        if self.reads:
            return self.reads.pop(0)
        return RedisWakeupRead(RedisWakeupReadAction.NO_MESSAGE, None)

    def close(self) -> None:
        """记录 close。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 配置程序错误时抛出。
        """

        self.close_calls += 1
        if self.raise_type_error:
            raise TypeError("program error")


class _FakeRedisRuntime:
    """同时满足 subscriber factory 与 health client 的 fake。"""

    def __init__(self, subscriber: _FakeSubscriber) -> None:
        """保存唯一 subscriber。

        Args:
            subscriber: 测试 subscriber。

        Returns:
            无。

        Raises:
            无。
        """

        self.subscriber = subscriber
        self.create_calls = 0
        self.ping_calls = 0
        self.ping_results: list[bool] = []
        self.close_calls = 0
        self.raise_value_error = False
        self.create_runtime_failures = 0
        self.block_create = False
        self.create_entered = ThreadEvent()
        self.create_release = ThreadEvent()

    def create_subscriber(self, scope: TenantScope) -> RedisWakeupSubscriberProtocol:
        """返回唯一 subscriber。

        Args:
            scope: tenant scope。

        Returns:
            fake subscriber。

        Raises:
            RuntimeError: 配置 closed construction failure 时抛出。
            ValueError: 配置程序错误时抛出。
        """

        del scope
        self.create_calls += 1
        if self.block_create:
            self.create_entered.set()
            self.create_release.wait(timeout=1)
        if self.create_runtime_failures > 0:
            self.create_runtime_failures -= 1
            raise RuntimeError("redis subscriber unavailable")
        if self.raise_value_error:
            raise ValueError("program error")
        return self.subscriber

    def ping(self) -> bool:
        """返回下一 health result。

        Args:
            无。

        Returns:
            配置结果；默认成功。

        Raises:
            ValueError: 配置程序错误时抛出。
        """

        self.ping_calls += 1
        if self.raise_value_error:
            raise ValueError("program error")
        if self.ping_results:
            return self.ping_results.pop(0)
        return True

    def close(self) -> None:
        """记录 prepared-runtime-owned client close。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 配置程序错误时抛出。
        """

        self.close_calls += 1
        if self.raise_value_error:
            raise ValueError("program error")


def _worker(
    gateway: WorkerJobGatewayProtocol,
    gate: ProcessIntakeGate,
    *,
    settings: PlatformQueueSettings | None = None,
    redis_runtime: _FakeRedisRuntime | None = None,
) -> PlatformWorker:
    """按 mode 构造 Worker。

    Args:
        gateway: fake Job gateway。
        gate: shared intake gate。
        settings: 可空 queue settings。
        redis_runtime: event-assisted Redis refs。

    Returns:
        ``PlatformWorker``。

    Raises:
        TypeError: gateway 不满足结构化端口时抛出。
        ValueError: mode/Redis 联合矩阵非法时抛出。
    """

    selected = settings or _settings()
    return PlatformWorker(
        gateway=gateway,
        scope=_scope(),
        worker_id=WORKER_ID,
        settings=selected,
        intake_gate=gate,
        redis_subscriber_factory=redis_runtime,
        redis_client=redis_runtime,
    )


async def _wait_until(predicate: Callable[[], bool], *, timeout: float = 1.0) -> None:
    """等待同步 predicate 成真。

    Args:
        predicate: 无参数布尔检查。
        timeout: 等待上界秒数。

    Returns:
        无。

    Raises:
        AssertionError: deadline 前仍未成真时抛出。
    """

    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("等待测试条件超时")
        await asyncio.sleep(0.001)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_invokes_handler_only_through_job_service_execution_gateway() -> None:
    """Worker 只调用 gateway execute/complete，不持有 handler/store seam。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(_claim())
    worker = _worker(gateway, gate)

    assert await worker.run() == 0
    assert gateway.recover_calls == 1
    assert len(gateway.execute_calls) == 1
    assert len(gateway.complete_calls) == 1
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pg_cancel_intent_is_projected_to_host_before_new_handler_side_effect() -> None:
    """poll governance 返回 cancel truth 后才允许 claim 与 handler side effect。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _CancelOrderingGateway(gate=gate)
    gateway.governance_outcomes.append(_page(_governance_result(AgentRunGovernanceAction.CANCEL_REQUESTED)))
    gateway.claim_results.append(_claim())

    assert await _worker(gateway, gate).run() == 0
    assert gateway.call_order[:3] == [
        "governance_projected",
        "claim",
        "handler",
    ]
    assert len(gateway.execute_calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_heartbeats_until_handler_returns_and_finalizes_once() -> None:
    """阻塞 handler 期间续租，返回后只写一次 terminal。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    worker = _worker(gateway, gate)
    task = asyncio.create_task(worker.run())

    await gateway.handler_started.wait()
    await _wait_until(lambda: len(gateway.heartbeat_calls) >= 2)
    gateway.handler_release.set()

    assert await task == 0
    assert len(gateway.complete_calls) == 1
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_program_error_reaps_blocked_heartbeat_before_closing_subscriber() -> None:
    """handler 程序错误先收口真实 heartbeat inner work 再关闭资源。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _BlockingHeartbeatGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    gateway.handler_error = RuntimeError("program error")
    subscriber = _FakeSubscriber()
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )
    task = asyncio.create_task(worker.run())

    await gateway.handler_started.wait()
    await asyncio.to_thread(gateway.heartbeat_entered.wait, 1)
    gateway.handler_release.set()
    await asyncio.sleep(0.01)

    assert not task.done()
    assert subscriber.close_calls == 0
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []

    gateway.heartbeat_release.set()
    assert await asyncio.wait_for(task, timeout=0.5) == 1
    assert subscriber.close_calls == 1
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_safe_failure_uses_gateway_fail_once() -> None:
    """closed handler failure 只经 gateway fail 收敛一次。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.handler_result = JobFailure(
        safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
        retryable=False,
    )
    worker = _worker(gateway, gate)

    assert await worker.run() == 0
    assert len(gateway.fail_calls) == 1
    assert gateway.complete_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_claims_only_from_postgres_after_redis_wakeup() -> None:
    """Redis hint 只提前结束等待，随后仍调用同一 PG claim gateway。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.extend((None, _claim()))
    subscriber = _FakeSubscriber()
    subscriber.reads.append(
        RedisWakeupRead(
            RedisWakeupReadAction.WAKEUP,
            RedisWakeupHint(TENANT_UUID, JOB_UUID),
        )
    )
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert len(gateway.claim_calls) == 2
    assert subscriber.read_calls == 1
    assert len(gateway.execute_calls) == 1
    assert subscriber.close_calls == 1
    assert redis_runtime.close_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repeated_event_assisted_poll_reuses_subscription_and_preserves_buffered_hints() -> None:
    """多轮正常 poll 不重订阅，也不把 queued hint 当作 ACK 消费。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.extend((None, None, _claim()))
    subscriber = _FakeSubscriber()
    subscriber.consume_pending_read_during_repeat_subscribe = True
    subscriber.reads.extend(
        (
            RedisWakeupRead(
                RedisWakeupReadAction.WAKEUP,
                RedisWakeupHint(TENANT_UUID, JOB_UUID),
            ),
            RedisWakeupRead(
                RedisWakeupReadAction.WAKEUP,
                RedisWakeupHint(TENANT_UUID, JOB_UUID),
            ),
        )
    )
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert len(gateway.claim_calls) == 3
    assert subscriber.resubscribe_calls == 1
    assert subscriber.consumed_during_resubscribe == 0
    assert subscriber.read_calls == 2
    assert worker.redis_degraded_transition_count == 0
    assert len(gateway.complete_calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_poll_claims_when_pubsub_message_is_lost() -> None:
    """PubSub 无消息时 poll deadline 后仍从 PostgreSQL claim。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.extend((None, _claim()))
    subscriber = _FakeSubscriber()
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert len(gateway.claim_calls) == 2
    assert subscriber.read_calls >= 1
    assert len(gateway.complete_calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_event_assisted_and_polling_degraded_use_identical_pg_claim_fencing() -> None:
    """event-assisted/degraded 都把同一 PG lease 交回 terminal gateway。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.extend((None, _claim()))
    subscriber = _FakeSubscriber()
    subscriber.resubscribe_results.extend((False, False))
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(
            PlatformQueueMode.EVENT_ASSISTED,
            redis_failure_threshold=1,
            redis_health_interval_seconds=1,
        ),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert worker.redis_degraded_transition_count == 1
    assert len(gateway.complete_calls) == 1
    terminal_lease = gateway.complete_calls[0][0]
    assert terminal_lease.job_id == JOB_UUID
    assert terminal_lease.attempt_id == ATTEMPT_UUID
    assert terminal_lease.fence == 1
    assert terminal_lease.raw_token == "a" * 64


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_governance_uses_configured_keyword_only_page_limit_and_rotates_cursor() -> None:
    """poll/heartbeat 共用一个 cursor 并显式传 settings page limit。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    cursor = AgentRunGovernanceCursor(
        deadline_at=NOW + timedelta(hours=1),
        correlation_id=CORRELATION_UUID,
    )
    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.governance_outcomes.extend((_page(cursor=cursor), _page()))
    gateway.claim_results.append(None)
    worker = _worker(gateway, gate)

    assert await worker.run() == 0
    assert gateway.governance_calls[0] == (None, 2)
    assert gateway.governance_calls[1] == (cursor, 2)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_matches_governance_identity_before_changing_current_attempt_heartbeat() -> None:
    """unrelated MISSING 不停当前续租，matching MISSING 才停止。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    gateway.governance_outcomes.extend(
        (
            _page(),
            _page(
                _governance_result(
                    AgentRunGovernanceAction.MISSING_HOST_WAIT,
                    current=False,
                )
            ),
            _page(),
            _page(_governance_result(AgentRunGovernanceAction.MISSING_HOST_WAIT)),
            _page(_governance_result(AgentRunGovernanceAction.NO_HOST_RECOVERED)),
        )
    )
    gateway.complete_requires_governance = True
    worker = _worker(gateway, gate)
    task = asyncio.create_task(worker.run())

    await gateway.handler_started.wait()
    await _wait_until(lambda: len(gateway.heartbeat_calls) >= 1)
    gateway.handler_release.set()

    assert await task == 0
    assert len(gateway.heartbeat_calls) >= 1
    assert len(gateway.complete_calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_return_with_active_correlation_waits_and_heartbeats_without_new_claim() -> None:
    """ACTIVE_WAIT 进入 drain 后超过 soft grace 仍保活同 lease。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    gateway.complete_requires_governance = True
    gateway.stop_after_complete = False
    gateway.governance_outcomes.append(_page())
    gateway.default_governance_page = _page(_governance_result(AgentRunGovernanceAction.ACTIVE_WAIT))
    worker = _worker(
        gateway,
        gate,
        settings=_settings(shutdown_grace_seconds=0.01),
    )
    task = asyncio.create_task(worker.run())

    await gateway.handler_started.wait()
    await _wait_until(lambda: len(gateway.heartbeat_calls) >= 1)
    gateway.handler_release.set()
    await _wait_until(lambda: len(gateway.complete_calls) == 1)
    await _wait_until(lambda: len(gateway.heartbeat_calls) >= 2)
    assert len(gateway.claim_calls) == 1
    assert len(gateway.execute_calls) == 1

    heartbeat_count = len(gateway.heartbeat_calls)
    worker.request_stop()
    await _wait_until(lambda: len(gateway.heartbeat_calls) > heartbeat_count)
    await asyncio.sleep(0.02)
    assert not task.done()
    assert len(gateway.heartbeat_calls) > heartbeat_count
    assert len(gateway.complete_calls) == 1
    assert gateway.fail_calls == []
    assert len(gateway.claim_calls) == 1

    gateway.default_governance_page = _page(
        _governance_result(AgentRunGovernanceAction.TERMINAL_RECONCILED)
    )
    assert await asyncio.wait_for(task, timeout=0.5) == 0
    assert len(gateway.claim_calls) == 1
    assert len(gateway.complete_calls) == 1
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_owner_cancel_reaps_correlation_wait_heartbeat_before_closing_subscriber() -> None:
    """correlation wait 的第二 heartbeat 收口后才传播 owner cancel。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _BlockingHeartbeatGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.complete_requires_governance = True
    gateway.default_governance_page = _page(_governance_result(AgentRunGovernanceAction.ACTIVE_WAIT))
    subscriber = _FakeSubscriber()
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )
    task = asyncio.create_task(worker.run())

    await _wait_until(lambda: len(gateway.complete_calls) == 1)
    await asyncio.to_thread(gateway.heartbeat_entered.wait, 1)
    task.cancel()
    await asyncio.sleep(0.01)

    assert not task.done()
    assert subscriber.close_calls == 0
    assert len(gateway.complete_calls) == 1
    assert gateway.fail_calls == []

    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()
    assert subscriber.close_calls == 0

    gateway.heartbeat_release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.5)
    assert subscriber.close_calls == 1
    assert len(gateway.complete_calls) == 1
    assert gateway.fail_calls == []
    assert gateway.execute_calls[0][2].is_cancel_requested()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "continuing_action",
    (
        AgentRunGovernanceAction.ACTIVE_WAIT,
        AgentRunGovernanceAction.CANCEL_REQUESTED,
        AgentRunGovernanceAction.CANCEL_ALREADY_REQUESTED,
        AgentRunGovernanceAction.SEND_RETRY,
    ),
)
async def test_governance_action_matrix_keeps_send_retry_stops_missing_or_terminal_and_ignores_unrelated_results(
    continuing_action: AgentRunGovernanceAction,
) -> None:
    """四个 continue action 保持 lease，terminal action 最终停止 attempt。

    Args:
        continuing_action: 本次验证的 continue action。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    gateway.governance_outcomes.extend(
        (
            _page(),
            _page(_governance_result(continuing_action)),
            _page(
                _governance_result(
                    AgentRunGovernanceAction.TERMINAL_RECONCILED,
                    current=False,
                )
            ),
            _page(_governance_result(AgentRunGovernanceAction.STALE)),
        )
    )
    worker = _worker(gateway, gate)

    assert await worker.run() == 0
    assert len(gateway.heartbeat_calls) >= 1
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_governance_invariant_failure_stops_runtime_regardless_of_current_attempt_identity() -> None:
    """unrelated INVARIANT_FAILURE 也让 tenant Worker 非零停机。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.governance_outcomes.append(
        _page(
            _governance_result(
                AgentRunGovernanceAction.INVARIANT_FAILURE,
                current=False,
            )
        )
    )
    worker = _worker(gateway, gate)

    assert await worker.run() == 1
    assert gateway.claim_calls == []
    assert gateway.complete_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_governance_repository_failure_retries_until_configured_threshold_then_stops_without_false_terminal() -> (
    None
):
    """只有 closed repository failure 计数，精确阈值返回 1。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.governance_outcomes.extend((JobRepositoryFailureError(), JobRepositoryFailureError()))
    worker = _worker(
        gateway,
        gate,
        settings=_settings(governance_failure_threshold=2),
    )

    assert await worker.run() == 1
    assert len(gateway.governance_calls) == 2
    assert gateway.claim_calls == []
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_governance_success_resets_consecutive_repository_failure_count() -> None:
    """成功 page 把失败计数清零，非连续失败不触发阈值。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.governance_outcomes.extend(
        (
            JobRepositoryFailureError(),
            _page(),
            JobRepositoryFailureError(),
            _page(),
        )
    )
    gateway.claim_results.extend((None, None))
    worker = _worker(
        gateway,
        gate,
        settings=_settings(governance_failure_threshold=2),
    )

    assert await worker.run() == 0
    assert len(gateway.governance_calls) >= 4
    assert len(gateway.claim_calls) >= 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unclassified_governance_exception_stops_runtime_without_false_terminal() -> None:
    """未分类 governance 错误不转 SEND_RETRY，直接保留现场退出 1。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.governance_outcomes.append(RuntimeError("program error"))
    worker = _worker(gateway, gate)

    assert await worker.run() == 1
    assert gateway.claim_calls == []
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_closed_gate_after_recovery_starts_no_governance_or_claim() -> None:
    """startup recovery 返回后若 epoch 已关闭，不启动任何新 work。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gate.request_stop()
    gateway = _FakeGateway(gate=gate)
    worker = _worker(gateway, gate)

    assert await worker.run() == 0
    assert gateway.recover_calls == 1
    assert gateway.governance_calls == []
    assert gateway.claim_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_gate_closed_by_governance_page_starts_no_claim() -> None:
    """governance 返回后 gate 已关闭时不跨线性化点 claim。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.stop_during_governance = True
    worker = _worker(gateway, gate)

    assert await worker.run() == 0
    assert len(gateway.governance_calls) == 1
    assert gateway.claim_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_signal_stops_new_claims_and_drains_with_heartbeat() -> None:
    """首个 stop 关闭 intake，但 admitted handler 继续 heartbeat 并正常收口。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    gateway.stop_after_complete = False
    worker = _worker(
        gateway,
        gate,
        settings=_settings(shutdown_grace_seconds=0.2),
    )
    task = asyncio.create_task(worker.run())

    await gateway.handler_started.wait()
    worker.request_stop()
    await _wait_until(lambda: len(gateway.heartbeat_calls) >= 1)
    gateway.handler_release.set()

    assert await task == 0
    assert len(gateway.claim_calls) == 1
    assert len(gateway.complete_calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_owner_cancel_reaps_noncooperative_handler_and_blocked_heartbeat_before_close() -> None:
    """owner cancel 等 handler 与真实 heartbeat inner work 收口后再关闭资源。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _BlockingHeartbeatGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    gateway.noncooperative_handler = True
    subscriber = _FakeSubscriber()
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )
    task = asyncio.create_task(worker.run())

    await gateway.handler_started.wait()
    await asyncio.to_thread(gateway.heartbeat_entered.wait, 1)
    task.cancel()
    await _wait_until(lambda: gateway.execute_calls[0][2].is_cancel_requested())

    assert not task.done()
    assert subscriber.close_calls == 0
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []

    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()
    assert subscriber.close_calls == 0

    gateway.handler_release.set()
    await asyncio.sleep(0.01)
    assert not task.done()
    assert subscriber.close_calls == 0

    gateway.heartbeat_release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.5)
    assert subscriber.close_calls == 1
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_claim_returning_after_drain_gate_never_starts_handler_or_heartbeat() -> None:
    """gate 前派发、gate 后返回的 claim 只留给 lease expiry/recovery。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _BlockingClaimGateway(gate=gate)
    worker = _worker(gateway, gate)
    task = asyncio.create_task(worker.run())

    await asyncio.to_thread(gateway.claim_entered.wait, 1)
    worker.request_stop()
    gateway.claim_release.set()

    assert await task == 0
    assert gateway.execute_calls == []
    assert gateway.heartbeat_calls == []
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_sigterm_while_pubsub_get_message_blocks_has_bounded_inner_wait() -> None:
    """stop 不把 outer cancellation 当线程结束，PubSub 返回后才 close。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(None)
    subscriber = _FakeSubscriber()
    subscriber.block_read = True
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )
    task = asyncio.create_task(worker.run())

    await asyncio.to_thread(subscriber.read_entered.wait, 1)
    worker.request_stop()
    await asyncio.sleep(0.01)
    assert not task.done()
    assert subscriber.close_calls == 0
    subscriber.read_release.set()

    assert await asyncio.wait_for(task, timeout=0.5) == 0
    assert subscriber.close_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repeated_owner_cancel_reaps_blocked_pubsub_thread_before_close() -> None:
    """重复 owner cancel 仍等待 PubSub thread 收口后才传播取消。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(None)
    subscriber = _FakeSubscriber()
    subscriber.block_read = True
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )
    task = asyncio.create_task(worker.run())

    await asyncio.to_thread(subscriber.read_entered.wait, 1)
    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()
    assert subscriber.close_calls == 0

    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()
    assert subscriber.close_calls == 0

    subscriber.read_release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.5)
    assert subscriber.close_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscriber_factory_returning_after_drain_starts_no_subscription_or_claim() -> None:
    """gate 前派发的 factory 在 gate 后返回时不得 subscribe 或 PG claim。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    subscriber = _FakeSubscriber()
    redis_runtime = _FakeRedisRuntime(subscriber)
    redis_runtime.block_create = True
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )
    task = asyncio.create_task(worker.run())

    await asyncio.to_thread(redis_runtime.create_entered.wait, 1)
    worker.request_stop()
    redis_runtime.create_release.set()

    assert await task == 0
    assert subscriber.resubscribe_calls == 0
    assert gateway.claim_calls == []
    assert subscriber.close_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_count", (1, 2))
async def test_owner_cancel_during_subscriber_creation_owns_and_closes_result(
    cancel_count: int,
) -> None:
    """创建中收到一次或重复取消仍接管并 exact-once 关闭 subscriber。

    Args:
        cancel_count: owner task 的取消请求次数。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    subscriber = _FakeSubscriber()
    redis_runtime = _FakeRedisRuntime(subscriber)
    redis_runtime.block_create = True
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )
    task = asyncio.create_task(worker.run())

    await asyncio.to_thread(redis_runtime.create_entered.wait, 1)
    for _ in range(cancel_count):
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        assert subscriber.close_calls == 0

    redis_runtime.create_release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.5)
    assert redis_runtime.create_calls == 1
    assert subscriber.resubscribe_calls == 0
    assert gateway.claim_calls == []
    assert subscriber.close_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_grace_expiry_with_blocked_heartbeat_does_not_close_under_inner_future() -> None:
    """grace 耗尽后仍 reap 阻塞 heartbeat，期间不关闭 PubSub。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _BlockingHeartbeatGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    subscriber = _FakeSubscriber()
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(
            PlatformQueueMode.EVENT_ASSISTED,
            shutdown_grace_seconds=0.01,
        ),
        redis_runtime=redis_runtime,
    )
    task = asyncio.create_task(worker.run())

    await gateway.handler_started.wait()
    await asyncio.to_thread(gateway.heartbeat_entered.wait, 1)
    worker.request_stop()
    await asyncio.sleep(0.03)
    assert not task.done()
    assert subscriber.close_calls == 0
    gateway.heartbeat_release.set()

    assert await asyncio.wait_for(task, timeout=0.5) == 1
    assert subscriber.close_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_worker_grace_expiry_with_noncooperative_handler_keeps_lease_and_no_false_terminal() -> None:
    """非协作 handler 在 grace 后仍被 reap；返回值被忽略且不写 terminal。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    gateway.noncooperative_handler = True
    gateway.stop_after_complete = False
    worker = _worker(
        gateway,
        gate,
        settings=_settings(shutdown_grace_seconds=0.02),
    )
    task = asyncio.create_task(worker.run())

    await gateway.handler_started.wait()
    worker.request_stop()
    await asyncio.sleep(0.04)
    assert not task.done()
    heartbeat_count = len(gateway.heartbeat_calls)
    await asyncio.sleep(0.02)
    assert len(gateway.heartbeat_calls) >= heartbeat_count
    gateway.handler_release.set()

    assert await task == 1
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handler_result_after_drain_abandon_is_ignored_without_receipt() -> None:
    """drain-abandon 线性化后 handler 即使成功返回也不写 receipt。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(_claim())
    gateway.block_handler = True
    gateway.noncooperative_handler = True
    worker = _worker(
        gateway,
        gate,
        settings=_settings(shutdown_grace_seconds=0.01),
    )
    task = asyncio.create_task(worker.run())

    await gateway.handler_started.wait()
    worker.request_stop()
    await asyncio.sleep(0.03)
    gateway.handler_release.set()

    assert await task == 1
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []


@pytest.mark.unit
def test_postgres_only_worker_never_constructs_pings_subscribes_or_recovers_redis() -> None:
    """POSTGRES_ONLY 构造期拒绝任一 Redis reference。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    redis_runtime = _FakeRedisRuntime(_FakeSubscriber())
    with pytest.raises(ValueError):
        _worker(gateway, gate, redis_runtime=redis_runtime)
    worker = _worker(gateway, gate)
    assert worker.redis_runtime_state is None
    assert redis_runtime.create_calls == 0
    assert redis_runtime.ping_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_three_consecutive_runtime_redis_failures_enter_polling_degraded_once() -> None:
    """默认三次连续 subscribe failure 精确进入 degraded 一次。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.extend((None, None, None))
    subscriber = _FakeSubscriber()
    subscriber.resubscribe_results.extend((False, False, False))
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(
            PlatformQueueMode.EVENT_ASSISTED,
            redis_health_interval_seconds=1,
        ),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert worker.redis_runtime_state is RedisRuntimeState.POLLING_DEGRADED
    assert worker.redis_degraded_transition_count == 1
    assert subscriber.resubscribe_calls == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_subscriber_construction_failure_uses_same_strict_redis_threshold() -> None:
    """factory 的 closed RuntimeError 只按配置阈值进入 degraded。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(None)
    subscriber = _FakeSubscriber()
    redis_runtime = _FakeRedisRuntime(subscriber)
    redis_runtime.create_runtime_failures = 2
    worker = _worker(
        gateway,
        gate,
        settings=_settings(
            PlatformQueueMode.EVENT_ASSISTED,
            redis_failure_threshold=2,
            redis_health_interval_seconds=1,
        ),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert worker.redis_runtime_state is RedisRuntimeState.POLLING_DEGRADED
    assert worker.redis_degraded_transition_count == 1
    assert redis_runtime.create_calls == 2
    assert subscriber.resubscribe_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_nondefault_redis_failure_threshold_and_health_interval_drive_runtime_transitions() -> None:
    """非默认 threshold=2 与短 health interval 驱动降级/恢复。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.extend((None, None, None, _claim()))
    subscriber = _FakeSubscriber()
    subscriber.resubscribe_results.extend((False, False, True))
    redis_runtime = _FakeRedisRuntime(subscriber)
    redis_runtime.ping_results.append(True)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(
            PlatformQueueMode.EVENT_ASSISTED,
            redis_failure_threshold=2,
            redis_health_interval_seconds=0.005,
        ),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert worker.redis_degraded_transition_count == 1
    assert worker.redis_recovered_transition_count == 1
    assert redis_runtime.ping_calls >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_success_before_threshold_resets_consecutive_failure_count() -> None:
    """一次 subscribe success 清零失败，使非连续失败不降级。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.extend((None, None, None))
    subscriber = _FakeSubscriber()
    subscriber.resubscribe_results.extend((False, True, False, True))
    subscriber.reads.extend(
        (
            RedisWakeupRead(RedisWakeupReadAction.CONNECTION_FAILURE, None),
            RedisWakeupRead(RedisWakeupReadAction.NO_MESSAGE, None),
        )
    )
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(
            PlatformQueueMode.EVENT_ASSISTED,
            redis_failure_threshold=3,
        ),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert worker.redis_runtime_state is RedisRuntimeState.EVENT_ASSISTED
    assert worker.redis_degraded_transition_count == 0
    assert subscriber.resubscribe_calls == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_probe_resubscribes_and_recovers_event_assisted_without_pg_mutation() -> None:
    """degraded health 只 ping/resubscribe，不因 Redis 写任何 PG terminal。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.extend((None, None, None))
    subscriber = _FakeSubscriber()
    subscriber.resubscribe_results.extend((False, True))
    redis_runtime = _FakeRedisRuntime(subscriber)
    redis_runtime.ping_results.append(True)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(
            PlatformQueueMode.EVENT_ASSISTED,
            redis_failure_threshold=1,
            redis_health_interval_seconds=0.005,
        ),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert worker.redis_recovered_transition_count == 1
    assert subscriber.resubscribe_calls == 2
    assert gateway.complete_calls == []
    assert gateway.fail_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lone_unicode_surrogate_hint_is_invalid_and_worker_continues_pg_polling() -> None:
    """adapter 的 INVALID surrogate 结果只唤醒 PG poll，不改变 PG state。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.extend((None, _claim()))
    subscriber = _FakeSubscriber()
    subscriber.reads.append(RedisWakeupRead(RedisWakeupReadAction.INVALID_MESSAGE, None))
    redis_runtime = _FakeRedisRuntime(subscriber)
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 0
    assert len(gateway.claim_calls) == 2
    assert len(gateway.complete_calls) == 1
    assert worker.invalid_redis_hint_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("location", ("subscriber", "client"))
async def test_runtime_redis_type_or_value_error_stops_worker_without_degraded_transition(
    location: str,
) -> None:
    """Redis runtime 程序错误返回 1，绝不计为连接降级。

    Args:
        location: 注入 subscriber TypeError 或 client ValueError。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    gateway.claim_results.append(None)
    subscriber = _FakeSubscriber()
    redis_runtime = _FakeRedisRuntime(subscriber)
    if location == "subscriber":
        subscriber.raise_type_error = True
    else:
        subscriber.resubscribe_results.append(False)
        redis_runtime.raise_value_error = True
    worker = _worker(
        gateway,
        gate,
        settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
        redis_runtime=redis_runtime,
    )

    assert await worker.run() == 1
    assert worker.redis_degraded_transition_count == 0


@pytest.mark.unit
def test_worker_pure_protocol_module_imports_without_redis_package() -> None:
    """Worker source 不 import adapter/redis-py，纯端口可安全提前 import。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    path = Path(__file__).parents[2] / "dayu" / "host" / "worker.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
    assert "redis" not in imported_modules
    assert "dayu.host.redis_wakeup" not in imported_modules
    assert not any(name.startswith("dayu.services") for name in imported_modules)
    assert not any("postgres" in name for name in imported_modules)
    script = """
import builtins
real_import = builtins.__import__
def deny_redis(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "redis" or name.startswith("redis."):
        raise ModuleNotFoundError("redis intentionally unavailable")
    return real_import(name, globals, locals, fromlist, level)
builtins.__import__ = deny_redis
import dayu.host.worker
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0


@pytest.mark.unit
def test_worker_constructor_closes_mode_and_dependency_matrix() -> None:
    """constructor 拒绝空 worker id、错误 Redis matrix 与非协议依赖。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    gate = ProcessIntakeGate()
    gateway = _FakeGateway(gate=gate)
    redis_runtime = _FakeRedisRuntime(_FakeSubscriber())
    with pytest.raises(ValueError):
        PlatformWorker(
            gateway=gateway,
            scope=_scope(),
            worker_id=" ",
            settings=_settings(),
            intake_gate=gate,
        )
    with pytest.raises(ValueError):
        PlatformWorker(
            gateway=gateway,
            scope=_scope(),
            worker_id=WORKER_ID,
            settings=_settings(PlatformQueueMode.EVENT_ASSISTED),
            intake_gate=gate,
        )
    with pytest.raises(ValueError):
        _worker(gateway, gate, redis_runtime=redis_runtime)
