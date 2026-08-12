"""Durable platform Worker 与 Worker-owned Redis 纯端口。

本模块位于 Host 层，只依赖投资平台纯配置、纯领域类型与进程入口闸门。
它声明上层 Service 必须结构化满足的最小 gateway，并实现一次只持有一个
attempt 的异步 Worker 状态机。Redis 在这里仅表现为无第三方依赖的提示端口；
具体 redis-py adapter 只能单向依赖本模块，Worker 永不导入它。

所有同步 gateway 与 Redis 调用都由唯一 async owner 通过
``asyncio.to_thread`` 执行。外层取消不会被当成线程已经停止：owner 会先
等待真实 inner work 收口，再传播取消。PostgreSQL 始终是 claim、lease、
fence、governance 与 terminal receipt 的唯一真源。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import partial
from typing import ParamSpec, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from dayu.host.process_intake import IntakeEpoch, ProcessIntakeGate
from dayu.investment.config import PlatformQueueMode, PlatformQueueSettings
from dayu.investment.domain.identifiers import TenantScope
from dayu.investment.domain.jobs import (
    AgentRunGovernanceAction,
    AgentRunGovernanceCursor,
    AgentRunGovernancePage,
    JobAttemptReceipt,
    JobCancellationSignalProtocol,
    JobClaim,
    JobCompletion,
    JobDeadlineExceededError,
    JobFailure,
    JobGovernanceRequiredError,
    JobHeartbeatAction,
    JobHeartbeatResult,
    JobLeaseHandle,
    JobLeaseLostError,
    JobRecoveryResult,
    JobRepositoryFailureError,
    JobStateConflictError,
)

_LOGGER = logging.getLogger(__name__)

_REDIS_READ_TIMEOUT_MAX_SECONDS = 1.0
_DRAIN_OBSERVATION_INTERVAL_SECONDS = 0.05
_DRAIN_OBSERVATION_SLICE_COUNT = 10

_P = ParamSpec("_P")
_R = TypeVar("_R")


class RedisWakeupReadAction(Enum):
    """一次 bounded Redis PubSub 读取的闭合结果。"""

    WAKEUP = "wakeup"
    NO_MESSAGE = "no_message"
    INVALID_MESSAGE = "invalid_message"
    CONNECTION_FAILURE = "connection_failure"


class RedisRuntimeState(Enum):
    """event-assisted deployment 的进程内 Redis 运行状态。"""

    EVENT_ASSISTED = "event_assisted"
    POLLING_DEGRADED = "polling_degraded"


@dataclass(frozen=True, slots=True)
class RedisWakeupHint:
    """通过严格 wire 校验的 tenant/job 提示。

    Args:
        tenant_id: canonical tenant UUID。
        job_id: canonical job UUID。

    Raises:
        TypeError: 任一字段不是 ``UUID`` 时抛出。
    """

    tenant_id: UUID
    job_id: UUID

    def __post_init__(self) -> None:
        """校验提示 identity。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 任一字段不是 ``UUID`` 时抛出。
        """

        if not isinstance(self.tenant_id, UUID):
            raise TypeError("tenant_id 必须是 UUID")
        if not isinstance(self.job_id, UUID):
            raise TypeError("job_id 必须是 UUID")


@dataclass(frozen=True, slots=True)
class RedisWakeupRead:
    """bounded PubSub 读取结果。

    Args:
        action: closed read action。
        hint: 仅 ``WAKEUP`` 时存在的严格提示。

    Raises:
        TypeError: action 或 hint 类型错误时抛出。
        ValueError: action/hint 联合矩阵不闭合时抛出。
    """

    action: RedisWakeupReadAction
    hint: RedisWakeupHint | None

    def __post_init__(self) -> None:
        """校验 action/hint 联合矩阵。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: action 或 hint 类型错误时抛出。
            ValueError: action/hint 联合矩阵不闭合时抛出。
        """

        if not isinstance(self.action, RedisWakeupReadAction):
            raise TypeError("action 必须是 RedisWakeupReadAction")
        if self.hint is not None and not isinstance(self.hint, RedisWakeupHint):
            raise TypeError("hint 必须是 RedisWakeupHint 或 None")
        if (self.action is RedisWakeupReadAction.WAKEUP) != (self.hint is not None):
            raise ValueError("仅 WAKEUP action 允许携带 hint")


@runtime_checkable
class RedisWakeupSubscriberProtocol(Protocol):
    """Worker 使用的同步、bounded Redis subscriber 窄协议。"""

    def resubscribe(self) -> bool:
        """订阅或重订阅固定 tenant channel。

        Args:
            无。

        Returns:
            成功时为 ``True``；连接失败时为 ``False``。

        Raises:
            TypeError: adapter 发生程序类型错误时传播。
            ValueError: adapter 发生程序值错误时传播。
        """

        ...

    def get_message(self, *, timeout_seconds: float) -> RedisWakeupRead:
        """执行一次 bounded PubSub read。

        Args:
            timeout_seconds: 正有限秒数。

        Returns:
            closed ``RedisWakeupRead``。

        Raises:
            TypeError: adapter 发生程序类型错误时传播。
            ValueError: timeout 或 adapter 状态非法时传播。
        """

        ...

    def close(self) -> None:
        """幂等关闭 PubSub。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: adapter 发生程序类型错误时传播。
            ValueError: adapter 发生程序值错误时传播。
        """

        ...


@runtime_checkable
class RedisWakeupSubscriberFactoryProtocol(Protocol):
    """按 tenant 创建 subscriber 的同步窄协议。"""

    def create_subscriber(
        self,
        scope: TenantScope,
    ) -> RedisWakeupSubscriberProtocol:
        """创建尚未订阅的 tenant subscriber。

        Args:
            scope: 显式 tenant scope。

        Returns:
            新 subscriber。

        Raises:
            RuntimeError: 已收窄的 Redis runtime construction failure。
            TypeError: adapter 发生程序类型错误时传播。
            ValueError: scope 或 adapter 状态非法时传播。
        """

        ...


@runtime_checkable
class RedisWakeupClientProtocol(Protocol):
    """Worker health 使用的同步 Redis client 窄协议。"""

    def ping(self) -> bool:
        """执行有界 Redis ping。

        Args:
            无。

        Returns:
            健康时为 ``True``；连接失败时为 ``False``。

        Raises:
            TypeError: adapter 发生程序类型错误时传播。
            ValueError: adapter 发生程序值错误时传播。
        """

        ...

    def close(self) -> None:
        """幂等关闭底层 client。

        Redis client 由 prepared runtime 而不是 Worker 持有；本方法只
        构成 startup lifecycle 的结构化端口，Worker 不调用它。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: adapter 发生程序类型错误时传播。
            ValueError: adapter 发生程序值错误时传播。
        """

        ...


@runtime_checkable
class WorkerJobGatewayProtocol(Protocol):
    """Host Worker 调用上层 Job Service 的最小结构化端口。"""

    def recover(self, scope: TenantScope) -> tuple[JobRecoveryResult, ...]:
        """恢复本 tenant 可安全恢复的 generic attempts。

        Args:
            scope: 显式 tenant scope。

        Returns:
            closed recovery results。

        Raises:
            RuntimeError: gateway 的 closed repository/domain failure。
        """

        ...

    def claim(self, scope: TenantScope, worker_id: str) -> JobClaim | None:
        """从 PostgreSQL claim 一个可执行 job。

        Args:
            scope: 显式 tenant scope。
            worker_id: 当前 Worker identity。

        Returns:
            成功 claim；没有工作时为 ``None``。

        Raises:
            RuntimeError: gateway 的 closed repository/domain failure。
        """

        ...

    async def execute_claim(
        self,
        scope: TenantScope,
        claim: JobClaim,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """只经 Service-owned registry 执行 claim。

        Args:
            scope: 显式 tenant scope。
            claim: PostgreSQL claim 快照。
            cancellation: 协作式取消信号。

        Returns:
            closed completion 或 failure。

        Raises:
            asyncio.CancelledError: Worker 请求 task cancellation 时传播。
        """

        ...

    def heartbeat(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
    ) -> JobHeartbeatResult:
        """续约当前 attempt lease。

        Args:
            scope: 显式 tenant scope。
            lease: 当前 lease。

        Returns:
            closed heartbeat result。

        Raises:
            RuntimeError: lease/domain/repository closed failure。
        """

        ...

    def complete(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        completion: JobCompletion,
    ) -> JobAttemptReceipt:
        """完成 generic attempt。

        Args:
            scope: 显式 tenant scope。
            lease: 当前 lease。
            completion: safe completion。

        Returns:
            immutable terminal receipt。

        Raises:
            RuntimeError: lease/domain/repository closed failure。
        """

        ...

    def fail(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        failure: JobFailure,
    ) -> JobRecoveryResult:
        """以 safe failure 收敛 generic attempt。

        Args:
            scope: 显式 tenant scope。
            lease: 当前 lease。
            failure: safe failure。

        Returns:
            closed recovery result。

        Raises:
            RuntimeError: lease/domain/repository closed failure。
        """

        ...

    def govern_agent_runs(
        self,
        scope: TenantScope,
        cursor: AgentRunGovernanceCursor | None,
        *,
        limit: int,
    ) -> AgentRunGovernancePage:
        """治理一页未终结 Agent correlations。

        Args:
            scope: 显式 tenant scope。
            cursor: 唯一 process-local keyset cursor。
            limit: settings 提供的 keyword-only page limit。

        Returns:
            Service 层 closed governance page。

        Raises:
            JobRepositoryFailureError: 可按严格阈值重试的仓储失败。
            RuntimeError: 其它 closed domain failure。
        """

        ...


class _WorkerCancellationSignal(JobCancellationSignalProtocol):
    """event-loop-owned 的协作式 handler cancellation signal。"""

    def __init__(self) -> None:
        """构造未请求取消的 signal。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._event = asyncio.Event()

    def request_cancel(self) -> None:
        """幂等设置取消意图。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._event.set()

    def is_cancel_requested(self) -> bool:
        """返回取消意图是否已置位。

        Args:
            无。

        Returns:
            已请求时为 ``True``。

        Raises:
            无。
        """

        return self._event.is_set()

    async def wait_cancel_requested(self) -> None:
        """等待取消意图置位。

        Args:
            无。

        Returns:
            无。

        Raises:
            asyncio.CancelledError: 调用 task 被取消时传播。
        """

        await self._event.wait()


class _AttemptControl:
    """event-loop-owned 的单 attempt 协调状态。"""

    def __init__(self, claim: JobClaim) -> None:
        """从 claim 初始化 lease 与治理状态。

        Args:
            claim: 当前 PostgreSQL claim。

        Returns:
            无。

        Raises:
            TypeError: claim 类型非法时抛出。
        """

        if not isinstance(claim, JobClaim):
            raise TypeError("claim 必须是 JobClaim")
        self.job_id = claim.job_id
        self.attempt_id = claim.attempt_id
        self.worker_id = claim.worker_id
        self.lease = claim.lease
        self.cancellation = _WorkerCancellationSignal()
        self.heartbeat_enabled = True
        self.stop_attempt = False
        self.runtime_failed = False
        self.drain_abandon_requested = False
        self.heartbeat_stop = asyncio.Event()


@dataclass(eq=False, repr=False, slots=True, kw_only=True)
class PlatformWorker:
    """单 tenant、单 in-flight attempt 的 durable platform Worker。"""

    gateway: WorkerJobGatewayProtocol
    scope: TenantScope
    worker_id: str
    settings: PlatformQueueSettings
    intake_gate: ProcessIntakeGate
    redis_subscriber_factory: RedisWakeupSubscriberFactoryProtocol | None = None
    redis_client: RedisWakeupClientProtocol | None = None
    _redis_state: RedisRuntimeState | None = field(init=False)
    _redis_subscriber: RedisWakeupSubscriberProtocol | None = field(
        init=False,
        default=None,
    )
    _redis_subscribed: bool = field(init=False, default=False)
    _redis_subscriber_closed: bool = field(init=False, default=False)
    _redis_failures: int = field(init=False, default=0)
    _redis_degraded_transitions: int = field(init=False, default=0)
    _redis_recovered_transitions: int = field(init=False, default=0)
    _invalid_redis_hint_count: int = field(init=False, default=0)
    _next_redis_health_at: float | None = field(init=False, default=None)
    _governance_cursor: AgentRunGovernanceCursor | None = field(
        init=False,
        default=None,
    )
    _governance_failures: int = field(init=False, default=0)
    _runtime_failed: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        """校验注入边界并构造尚未运行的 Worker。

        Args:
            gateway: 上层 Job Service 结构化端口。
            scope: 唯一显式 tenant scope。
            worker_id: 当前进程的安全 Worker label。
            settings: durable queue settings。
            intake_gate: CLI signal callback 与 Worker 共享的入口闸门。
            redis_subscriber_factory: event-assisted 模式的 subscriber factory。
            redis_client: event-assisted 模式的 health client。

        Returns:
            无。

        Raises:
            TypeError: 任一依赖类型不满足闭合协议时抛出。
            ValueError: worker id 或 queue-mode/Redis 联合矩阵非法时抛出。
        """

        if not isinstance(self.gateway, WorkerJobGatewayProtocol):
            raise TypeError("gateway 必须满足 WorkerJobGatewayProtocol")
        if not isinstance(self.scope, TenantScope):
            raise TypeError("scope 必须是 TenantScope")
        if type(self.worker_id) is not str or not self.worker_id or self.worker_id != self.worker_id.strip():
            raise ValueError("worker_id 必须是非空无首尾空白字符串")
        if not isinstance(self.settings, PlatformQueueSettings):
            raise TypeError("settings 必须是 PlatformQueueSettings")
        if not isinstance(self.intake_gate, ProcessIntakeGate):
            raise TypeError("intake_gate 必须是 ProcessIntakeGate")

        if self.settings.mode is PlatformQueueMode.POSTGRES_POLLING:
            if self.redis_subscriber_factory is not None or self.redis_client is not None:
                raise ValueError("POSTGRES_POLLING 不得注入 Redis 引用")
            redis_state: RedisRuntimeState | None = None
        elif self.settings.mode is PlatformQueueMode.EVENT_ASSISTED:
            if not isinstance(
                self.redis_subscriber_factory,
                RedisWakeupSubscriberFactoryProtocol,
            ) or not isinstance(self.redis_client, RedisWakeupClientProtocol):
                raise ValueError("EVENT_ASSISTED 必须注入完整 Redis 引用")
            redis_state = RedisRuntimeState.EVENT_ASSISTED
        else:
            raise ValueError("queue mode 不受 Worker 支持")

        self._redis_state = redis_state

    @property
    def redis_runtime_state(self) -> RedisRuntimeState | None:
        """返回当前进程内 Redis runtime state。

        Args:
            无。

        Returns:
            event-assisted/degraded 状态；POSTGRES_ONLY 为 ``None``。

        Raises:
            无。
        """

        return self._redis_state

    @property
    def redis_degraded_transition_count(self) -> int:
        """返回进入 polling-degraded 的次数。

        Args:
            无。

        Returns:
            非负 transition count。

        Raises:
            无。
        """

        return self._redis_degraded_transitions

    @property
    def redis_recovered_transition_count(self) -> int:
        """返回恢复 event-assisted 的次数。

        Args:
            无。

        Returns:
            非负 transition count。

        Raises:
            无。
        """

        return self._redis_recovered_transitions

    @property
    def invalid_redis_hint_count(self) -> int:
        """返回被协议边界拒绝的 Redis hint 数量。

        Args:
            无。

        Returns:
            非负 safe metric count。

        Raises:
            无。
        """

        return self._invalid_redis_hint_count

    def request_stop(self) -> None:
        """关闭共享 intake gate，进入 cooperative drain。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.intake_gate.request_stop()

    async def run(self) -> int:
        """运行 Worker 直到 cooperative drain 或 runtime failure。

        Args:
            无。

        Returns:
            graceful drain 为 ``0``；runtime invariant、治理阈值耗尽或
            drain-abandon 收口为 ``1``。

        Raises:
            asyncio.CancelledError: 外层 task 被取消时，在 reap 当前
                Worker-owned inner work 后传播。
        """

        exit_code = 0
        try:
            try:
                exit_code = await self._run_loop()
            except asyncio.CancelledError:
                raise
            except Exception:
                exit_code = 1
        finally:
            try:
                await self._close_subscriber()
            except asyncio.CancelledError:
                raise
            except Exception:
                exit_code = 1
        return exit_code

    async def _run_loop(self) -> int:
        """执行 startup recovery、govern、claim 与 wait 主循环。

        Args:
            无。

        Returns:
            closed process exit code。

        Raises:
            Exception: 未分类 gateway/Redis/contract 错误向 ``run`` 传播。
        """

        if not await self._prepare_run():
            return 0

        while self.intake_gate.is_open and not self._runtime_failed:
            governance_succeeded = await self._govern_agent_runs(None)
            if self._runtime_failed:
                return 1
            if not self.intake_gate.is_open:
                break
            if not governance_succeeded:
                await self._wait_for_next_poll()
                continue

            claim_epoch = self.intake_gate.capture()
            claim = await _await_owned_thread_call(
                self.gateway.claim,
                self.scope,
                self.worker_id,
            )
            if not self._is_admitted(claim_epoch):
                break
            if claim is None:
                await self._wait_for_next_poll()
                continue
            self._validate_claim(claim)
            attempt_exit = await self._run_attempt(claim)
            if attempt_exit != 0:
                return attempt_exit

        return 1 if self._runtime_failed else 0

    async def _prepare_run(self) -> bool:
        """在 intake epoch 内执行启动恢复并准备 Redis subscriber。

        Args:
            无。

        Returns:
            恢复后仍允许进入主循环时为 ``True``。

        Raises:
            TypeError: recovery result 不满足闭合契约时抛出。
            Exception: gateway 或 Redis 未分类错误传播给 ``run``。
        """

        recovery_epoch = self.intake_gate.capture()
        recovery_results = await _await_owned_thread_call(
            self.gateway.recover,
            self.scope,
        )
        if not isinstance(recovery_results, tuple) or any(
            not isinstance(result, JobRecoveryResult) for result in recovery_results
        ):
            raise TypeError("recover 必须返回 JobRecoveryResult tuple")
        if not self._is_admitted(recovery_epoch):
            return False
        if self._redis_state is RedisRuntimeState.EVENT_ASSISTED:
            await self._ensure_subscription()
        return True

    def _is_admitted(self, epoch: IntakeEpoch) -> bool:
        """检查一次阻塞调用返回后是否仍可启动新工作。

        Args:
            epoch: 派发前取得的 intake epoch。

        Returns:
            gate 仍开放且 epoch 仍 current 时为 ``True``。

        Raises:
            无。
        """

        return self.intake_gate.is_open and self.intake_gate.is_current(epoch)

    def _validate_claim(self, claim: JobClaim) -> None:
        """校验 gateway claim 未跨 tenant/worker 漂移。

        Args:
            claim: gateway 返回的 claim。

        Returns:
            无。

        Raises:
            TypeError: 返回值不是 ``JobClaim`` 时抛出。
            ValueError: tenant 或 worker identity 漂移时抛出。
        """

        if not isinstance(claim, JobClaim):
            raise TypeError("claim 必须是 JobClaim 或 None")
        if claim.tenant_id != self.scope.tenant_id:
            raise ValueError("claim tenant 与 Worker scope 不一致")
        if claim.worker_id != self.worker_id:
            raise ValueError("claim worker_id 与当前 Worker 不一致")

    async def _run_attempt(self, claim: JobClaim) -> int:
        """执行、续租并收敛一个已 admission 的 attempt。

        Args:
            claim: gate 关闭前取得并验证的 claim。

        Returns:
            attempt 可继续主循环为 ``0``；runtime/drain-abandon 为 ``1``。

        Raises:
            Exception: 未分类 gateway/contract 错误向主循环传播。
        """

        control = _AttemptControl(claim)
        handler_task = asyncio.create_task(
            self.gateway.execute_claim(
                self.scope,
                claim,
                control.cancellation,
            )
        )
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(control, claim))
        drain_deadline: float | None = None

        try:
            while not handler_task.done():
                if heartbeat_task.done():
                    return await self._settle_stopped_heartbeat(
                        control,
                        handler_task,
                        heartbeat_task,
                    )
                abandoned, drain_deadline = await self._wait_for_attempt_progress(
                    control,
                    handler_task,
                    heartbeat_task,
                    drain_deadline,
                )
                if abandoned:
                    return 1

            return await self._settle_completed_handler(control, claim, handler_task, heartbeat_task)
        except asyncio.CancelledError:
            cleanup_task = asyncio.create_task(
                self._cleanup_cancelled_attempt(
                    control,
                    handler_task,
                    heartbeat_task,
                )
            )
            await _await_cleanup_task(cleanup_task)
            raise

    async def _cleanup_cancelled_attempt(
        self,
        control: _AttemptControl,
        handler_task: asyncio.Task[JobCompletion | JobFailure],
        heartbeat_task: asyncio.Task[None],
    ) -> None:
        """在独立 task 中完整回收被取消 attempt 的两个 owner。

        Args:
            control: 当前 attempt 协调状态。
            handler_task: 唯一 handler owner。
            heartbeat_task: 唯一 heartbeat owner。

        Returns:
            无。

        Raises:
            asyncio.CancelledError: cleanup task 自身被外部错误取消时传播。
        """

        await self._cancel_handler_without_terminal(handler_task, control)
        await _reap_task(heartbeat_task)

    async def _settle_stopped_heartbeat(
        self,
        control: _AttemptControl,
        handler_task: asyncio.Task[JobCompletion | JobFailure],
        heartbeat_task: asyncio.Task[None],
    ) -> int:
        """在 heartbeat owner 提前停止后取消 handler 并选择退出码。

        Args:
            control: 当前 attempt 协调状态。
            handler_task: 尚未完成的唯一 handler owner。
            heartbeat_task: 已完成的唯一 heartbeat owner。

        Returns:
            terminal governance 正常停止为 ``0``；其它停止为 ``1``。

        Raises:
            asyncio.CancelledError: 当前 Worker owner 被取消时传播。
        """

        if _task_exception(heartbeat_task) is not None:
            control.runtime_failed = True
        await self._cancel_handler_without_terminal(handler_task, control)
        if control.runtime_failed or self._runtime_failed:
            return 1
        return 0 if control.stop_attempt else 1

    async def _wait_for_attempt_progress(
        self,
        control: _AttemptControl,
        handler_task: asyncio.Task[JobCompletion | JobFailure],
        heartbeat_task: asyncio.Task[None],
        drain_deadline: float | None,
    ) -> tuple[bool, float | None]:
        """等待 attempt task 前进，并在 drain grace 耗尽时完整 reap。

        Args:
            control: 当前 attempt 协调状态。
            handler_task: 唯一 handler owner。
            heartbeat_task: 唯一 heartbeat owner。
            drain_deadline: 可空 cooperative drain deadline。

        Returns:
            ``(是否 abandon, 当前 deadline)``。

        Raises:
            asyncio.CancelledError: 当前 Worker owner 被取消时传播。
        """

        loop = asyncio.get_running_loop()
        if not self.intake_gate.is_open and drain_deadline is None:
            drain_deadline = loop.time() + self.settings.shutdown_grace_seconds
        wait_seconds = min(
            _DRAIN_OBSERVATION_INTERVAL_SECONDS,
            self.settings.shutdown_grace_seconds / _DRAIN_OBSERVATION_SLICE_COUNT,
        )
        if drain_deadline is not None:
            remaining = drain_deadline - loop.time()
            if remaining <= 0:
                await self._abandon_attempt(control, handler_task, heartbeat_task)
                return True, drain_deadline
            wait_seconds = min(_DRAIN_OBSERVATION_INTERVAL_SECONDS, remaining)
        await asyncio.wait(
            (handler_task, heartbeat_task),
            timeout=wait_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        return False, drain_deadline

    async def _abandon_attempt(
        self,
        control: _AttemptControl,
        handler_task: asyncio.Task[JobCompletion | JobFailure],
        heartbeat_task: asyncio.Task[None],
    ) -> None:
        """在 drain grace 耗尽后取消 handler 并等待两个 owner 收口。

        Args:
            control: 当前 attempt 协调状态。
            handler_task: 唯一 handler owner。
            heartbeat_task: 唯一 heartbeat owner。

        Returns:
            无。

        Raises:
            asyncio.CancelledError: 当前 Worker owner 被取消时传播。
        """

        control.drain_abandon_requested = True
        control.cancellation.request_cancel()
        handler_task.cancel()
        await _reap_cancelled_handler(handler_task)
        control.heartbeat_stop.set()
        await _reap_task(heartbeat_task)

    async def _settle_completed_handler(
        self,
        control: _AttemptControl,
        claim: JobClaim,
        handler_task: asyncio.Task[JobCompletion | JobFailure],
        heartbeat_task: asyncio.Task[None],
    ) -> int:
        """停止 heartbeat 并收敛已完成 handler 的闭合结果。

        Args:
            control: 当前 attempt 协调状态。
            claim: 当前 claim identity。
            handler_task: 已完成的 handler owner。
            heartbeat_task: 待停止的 heartbeat owner。

        Returns:
            可继续主循环为 ``0``；runtime failure 为 ``1``。

        Raises:
            Exception: handler 或 gateway 未分类异常传播给主循环。
        """

        control.heartbeat_stop.set()
        await _reap_task(heartbeat_task)
        heartbeat_error = _task_exception(heartbeat_task)
        handler_result = _handler_result(handler_task)
        if heartbeat_error is not None:
            control.runtime_failed = True
        if control.drain_abandon_requested or control.runtime_failed or self._runtime_failed:
            return 1
        if control.stop_attempt:
            return 0
        if not isinstance(handler_result, (JobCompletion, JobFailure)):
            return 1
        return await self._finalize_handler_result(control, claim, handler_result)

    async def _heartbeat_loop(
        self,
        control: _AttemptControl,
        original_claim: JobClaim,
    ) -> None:
        """以唯一 owner 周期性 governance 与 heartbeat 当前 lease。

        Args:
            control: 当前 attempt 的 event-loop-owned 状态。
            original_claim: 初始 claim，用于闭合续约 identity。

        Returns:
            stop、lease lost、terminal governance 或 runtime failure 后返回。

        Raises:
            Exception: 未分类 gateway/contract 错误传播给 attempt owner。
        """

        heartbeat_interval = min(
            self.settings.poll_interval_seconds,
            original_claim.descriptor.lease_duration_seconds / 3.0,
        )
        if heartbeat_interval <= 0:
            raise ValueError("heartbeat interval 必须为正")

        while not control.heartbeat_stop.is_set():
            if await _wait_until_set(control.heartbeat_stop, heartbeat_interval):
                return
            if await self._run_heartbeat_cycle(control):
                return

    async def _run_heartbeat_cycle(self, control: _AttemptControl) -> bool:
        """执行一次 govern-heartbeat-govern 闭合周期。

        Args:
            control: 当前 attempt 的 event-loop-owned 状态。

        Returns:
            heartbeat owner 应停止时为 ``True``。

        Raises:
            Exception: 未分类 gateway/contract 错误传播给 attempt owner。
        """

        await self._govern_agent_runs(control)
        if self._attempt_should_stop(control):
            return True
        if not control.heartbeat_enabled:
            return False
        heartbeat = await self._renew_attempt_lease(control)
        if heartbeat is None:
            return True
        self._apply_heartbeat(control, heartbeat)
        if heartbeat.action is JobHeartbeatAction.GOVERNANCE_REQUIRED:
            control.cancellation.request_cancel()
        await self._govern_agent_runs(control)
        return self._attempt_should_stop(control)

    async def _renew_attempt_lease(
        self,
        control: _AttemptControl,
    ) -> JobHeartbeatResult | None:
        """续约当前 lease，并把 expected lease conflicts 收窄为 attempt stop。

        Args:
            control: 当前 attempt 的 event-loop-owned 状态。

        Returns:
            成功 heartbeat result；lease 已失效时为 ``None``。

        Raises:
            Exception: 未分类 gateway/contract 错误传播给 attempt owner。
        """

        try:
            return await _await_owned_thread_call(
                self.gateway.heartbeat,
                self.scope,
                control.lease,
            )
        except (JobLeaseLostError, JobStateConflictError, JobDeadlineExceededError):
            control.cancellation.request_cancel()
            control.stop_attempt = True
            return None

    def _attempt_should_stop(self, control: _AttemptControl) -> bool:
        """把 Worker runtime failure 投影到 attempt 并判断是否停止。

        Args:
            control: 当前 attempt 的 event-loop-owned 状态。

        Returns:
            runtime failure 或 terminal governance 已发生时为 ``True``。

        Raises:
            无。
        """

        if self._runtime_failed:
            control.runtime_failed = True
        return control.runtime_failed or control.stop_attempt

    def _apply_heartbeat(
        self,
        control: _AttemptControl,
        heartbeat: JobHeartbeatResult,
    ) -> None:
        """校验同 attempt/same-fence renewal 并替换当前 lease。

        Args:
            control: 当前 attempt state。
            heartbeat: gateway heartbeat result。

        Returns:
            无。

        Raises:
            TypeError: heartbeat 类型非法时抛出。
            ValueError: identity、worker、fence 或 token 漂移时抛出。
        """

        if not isinstance(heartbeat, JobHeartbeatResult):
            raise TypeError("heartbeat 必须返回 JobHeartbeatResult")
        renewed = heartbeat.claim
        previous = control.lease
        if renewed.job_id != control.job_id or renewed.attempt_id != control.attempt_id:
            raise ValueError("heartbeat claim identity 漂移")
        if renewed.worker_id != control.worker_id:
            raise ValueError("heartbeat worker identity 漂移")
        if renewed.lease.fence != previous.fence:
            raise ValueError("heartbeat fence 不得变化")
        if renewed.lease.raw_token != previous.raw_token:
            raise ValueError("heartbeat raw token 不得变化")
        control.lease = renewed.lease

    async def _finalize_handler_result(
        self,
        control: _AttemptControl,
        claim: JobClaim,
        result: JobCompletion | JobFailure,
    ) -> int:
        """通过 gateway 完成 generic terminal 或转 correlation wait。

        Args:
            control: 当前 attempt state。
            claim: 初始 claim identity。
            result: handler closed result。

        Returns:
            正常收敛为 ``0``；runtime failure 为 ``1``。

        Raises:
            Exception: 未分类 gateway/contract 错误传播给 ``run``。
        """

        try:
            if isinstance(result, JobCompletion):
                receipt = await _await_owned_thread_call(
                    self.gateway.complete,
                    self.scope,
                    control.lease,
                    result,
                )
                if not isinstance(receipt, JobAttemptReceipt):
                    raise TypeError("complete 必须返回 JobAttemptReceipt")
                if receipt.job_id != claim.job_id or receipt.attempt_id != claim.attempt_id:
                    raise ValueError("complete receipt identity 漂移")
            else:
                recovery = await _await_owned_thread_call(
                    self.gateway.fail,
                    self.scope,
                    control.lease,
                    result,
                )
                if not isinstance(recovery, JobRecoveryResult):
                    raise TypeError("fail 必须返回 JobRecoveryResult")
                if recovery.job_id != claim.job_id or recovery.attempt_id != claim.attempt_id:
                    raise ValueError("fail recovery identity 漂移")
        except JobGovernanceRequiredError:
            control.heartbeat_stop.clear()
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(control, claim))
            return await self._wait_for_correlation(control, heartbeat_task)
        except (JobLeaseLostError, JobStateConflictError, JobDeadlineExceededError):
            return 0
        return 0

    async def _wait_for_correlation(
        self,
        control: _AttemptControl,
        heartbeat_task: asyncio.Task[None],
    ) -> int:
        """handler 已返回后持续 heartbeat/govern 直到 correlation 收敛。

        Args:
            control: 当前 attempt state。
            heartbeat_task: 唯一 heartbeat owner。

        Returns:
            terminal/recovered/stale/lease lost 为 ``0``；runtime failure
            为 ``1``。首次停机仅关闭 intake，不终止已进入治理等待的
            correlation。

        Raises:
            asyncio.CancelledError: 外层取消时传播。
        """

        try:
            while not heartbeat_task.done():
                await asyncio.wait(
                    (heartbeat_task,),
                    timeout=_DRAIN_OBSERVATION_INTERVAL_SECONDS,
                    return_when=asyncio.FIRST_COMPLETED,
                )
        except asyncio.CancelledError:
            cleanup_task = asyncio.create_task(_stop_and_reap_heartbeat(control, heartbeat_task))
            await _await_cleanup_task(cleanup_task)
            raise

        heartbeat_error = _task_exception(heartbeat_task)
        if heartbeat_error is not None:
            return 1
        if control.runtime_failed or self._runtime_failed:
            return 1
        return 0 if control.stop_attempt else 1

    async def _govern_agent_runs(self, control: _AttemptControl | None) -> bool:
        """读取一页治理结果并按 identity/action 矩阵更新 attempt。

        只有 closed ``JobRepositoryFailureError`` 参与 settings 阈值；任一
        其它异常传播为 runtime failure。cursor 在 page 返回后、消费结果前
        立即更新，poll 与 heartbeat 共用同一字段。

        Args:
            control: 当前 attempt；poll-before-claim 时为 ``None``。

        Returns:
            成功取得并验证 page 时为 ``True``；低于阈值的 repository
            failure 为 ``False``。

        Raises:
            Exception: 非 repository failure 原样传播。
        """

        try:
            page = await _await_owned_thread_call(
                self.gateway.govern_agent_runs,
                self.scope,
                self._governance_cursor,
                limit=self.settings.governance_page_size,
            )
        except JobRepositoryFailureError:
            self._governance_failures += 1
            _LOGGER.warning("platform_worker_governance_repository_failure")
            if self._governance_failures >= self.settings.governance_failure_threshold:
                self._runtime_failed = True
            return False

        if not isinstance(page, AgentRunGovernancePage):
            raise TypeError("govern_agent_runs 必须返回 AgentRunGovernancePage")
        self._governance_cursor = page.next_cursor
        self._governance_failures = 0

        for result in page.results:
            _LOGGER.debug(
                "platform_worker_governance_result correlation_id=%s action=%s",
                result.correlation_id,
                result.action.value,
            )
            if result.action is AgentRunGovernanceAction.INVARIANT_FAILURE:
                self._runtime_failed = True
                if control is not None:
                    control.runtime_failed = True
                continue
            if control is None:
                continue
            if result.job_id != control.job_id or result.attempt_id != control.attempt_id:
                continue
            self._apply_matching_governance_action(control, result.action)
        return True

    def _apply_matching_governance_action(
        self,
        control: _AttemptControl,
        action: AgentRunGovernanceAction,
    ) -> None:
        """应用完整 matching governance action 矩阵。

        Args:
            control: 当前 attempt state。
            action: identity 已同时匹配 job/attempt 的 closed action。

        Returns:
            无。

        Raises:
            ValueError: action 不属于 closed enum 时抛出。
        """

        if action is AgentRunGovernanceAction.MISSING_HOST_WAIT:
            control.heartbeat_enabled = False
            return
        if action in (
            AgentRunGovernanceAction.ACTIVE_WAIT,
            AgentRunGovernanceAction.CANCEL_REQUESTED,
            AgentRunGovernanceAction.CANCEL_ALREADY_REQUESTED,
            AgentRunGovernanceAction.SEND_RETRY,
        ):
            control.heartbeat_enabled = True
            if action in (
                AgentRunGovernanceAction.CANCEL_REQUESTED,
                AgentRunGovernanceAction.CANCEL_ALREADY_REQUESTED,
            ):
                control.cancellation.request_cancel()
            return
        if action in (
            AgentRunGovernanceAction.TERMINAL_RECONCILED,
            AgentRunGovernanceAction.NO_HOST_RECOVERED,
            AgentRunGovernanceAction.STALE,
        ):
            control.heartbeat_enabled = False
            control.stop_attempt = True
            control.cancellation.request_cancel()
            return
        if action is AgentRunGovernanceAction.INVARIANT_FAILURE:
            control.runtime_failed = True
            return
        raise ValueError("未知 governance action")

    async def _wait_for_next_poll(self) -> None:
        """按 deployment/runtime mode 等待下一次 PostgreSQL claim。

        Args:
            无。

        Returns:
            poll timeout、Redis hint、协议拒绝、连接状态变化或 gate 关闭后返回。

        Raises:
            Exception: Redis 运行期程序错误传播给 ``run``。
        """

        if self._redis_state is None:
            await _sleep_while_open(
                self.intake_gate,
                self.settings.poll_interval_seconds,
            )
            return
        if self._redis_state is RedisRuntimeState.POLLING_DEGRADED:
            await self._wait_polling_degraded()
            return
        await self._wait_event_assisted_poll()

    async def _wait_event_assisted_poll(self) -> None:
        """在 event-assisted 状态等待 hint 或 PostgreSQL poll deadline。

        Args:
            无。

        Returns:
            hint、deadline、连接状态变化或 gate 关闭后返回。

        Raises:
            Exception: Redis 运行期程序错误传播给 ``run``。
        """

        if not await self._ensure_subscription():
            await _sleep_while_open(
                self.intake_gate,
                self.settings.poll_interval_seconds,
            )
            return

        subscriber = self._redis_subscriber
        if subscriber is None:
            raise RuntimeError("event-assisted subscriber 缺失")
        deadline = asyncio.get_running_loop().time() + self.settings.poll_interval_seconds
        await self._read_redis_until_deadline(subscriber, deadline)

    async def _read_redis_until_deadline(
        self,
        subscriber: RedisWakeupSubscriberProtocol,
        deadline: float,
    ) -> None:
        """以 bounded reads 消费 Redis，直到 hint 或 poll deadline。

        Args:
            subscriber: 已成功订阅的 tenant subscriber。
            deadline: 当前 event loop 的绝对 poll deadline。

        Returns:
            hint、deadline、连接状态变化或 gate 关闭后返回。

        Raises:
            TypeError: adapter 返回值不满足闭合契约时抛出。
            Exception: Redis 运行期程序错误传播给 ``run``。
        """

        while self.intake_gate.is_open:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            timeout = min(remaining, _REDIS_READ_TIMEOUT_MAX_SECONDS)
            read = await _await_owned_thread_call(
                subscriber.get_message,
                timeout_seconds=timeout,
            )
            if self._consume_redis_read(read):
                return

    def _consume_redis_read(self, read: RedisWakeupRead) -> bool:
        """校验并消费一次 closed Redis read。

        Args:
            read: subscriber 返回的 closed read。

        Returns:
            当前 wait 应结束时为 ``True``；NO_MESSAGE 时为 ``False``。

        Raises:
            TypeError: read 不满足闭合契约时抛出。
        """

        if not isinstance(read, RedisWakeupRead):
            raise TypeError("subscriber 必须返回 RedisWakeupRead")
        if read.action is RedisWakeupReadAction.CONNECTION_FAILURE:
            self._record_redis_failure()
            return True
        self._record_redis_success()
        if read.action is RedisWakeupReadAction.NO_MESSAGE:
            return False
        if read.action is RedisWakeupReadAction.INVALID_MESSAGE:
            self._invalid_redis_hint_count += 1
            return True
        hint = read.hint
        if hint is not None and str(hint.tenant_id) != self.scope.tenant_id.value:
            self._invalid_redis_hint_count += 1
        return True

    async def _ensure_subscription(self) -> bool:
        """确保存在已成功订阅当前 tenant 的 subscriber。

        Args:
            无。

        Returns:
            subscribe 成功为 ``True``；已收窄 Redis failure 为 ``False``。

        Raises:
            TypeError: factory/adapter 程序类型错误时传播。
            ValueError: factory/adapter 程序值错误时传播。
        """

        factory = self.redis_subscriber_factory
        if factory is None:
            raise RuntimeError("Redis subscriber factory 缺失")
        if not self.intake_gate.is_open:
            return False
        if self._redis_subscriber is None:
            creation_epoch = self.intake_gate.capture()
            try:
                await self._create_and_own_subscriber(factory)
            except RuntimeError:
                self._record_redis_failure()
                return False
            if not self._is_admitted(creation_epoch):
                return False
        if self._redis_subscribed:
            return True
        subscriber = self._redis_subscriber
        if subscriber is None:
            raise RuntimeError("event-assisted subscriber 缺失")
        subscribe_epoch = self.intake_gate.capture()
        subscribed = await _await_owned_thread_call(
            subscriber.resubscribe,
        )
        if not self._is_admitted(subscribe_epoch):
            return False
        if subscribed is not True:
            self._record_redis_failure()
            return False
        self._redis_subscribed = True
        self._record_redis_success()
        return True

    async def _create_and_own_subscriber(
        self,
        factory: RedisWakeupSubscriberFactoryProtocol,
    ) -> None:
        """创建 subscriber，并在传播重复 owner cancel 前接管资源。

        Args:
            factory: 已验证的同步 subscriber factory。

        Returns:
            无。

        Raises:
            asyncio.CancelledError: 资源已登记后传播首份 owner cancellation。
            RuntimeError: adapter 的 closed construction failure。
            TypeError: factory 返回值不满足 subscriber protocol。
            ValueError: adapter 的程序值错误。
        """

        call = partial(factory.create_subscriber, self.scope)
        inner_task = asyncio.create_task(asyncio.to_thread(call))
        pending_cancelled: asyncio.CancelledError | None = None
        while not inner_task.done():
            try:
                await asyncio.shield(inner_task)
            except asyncio.CancelledError as exc:
                if pending_cancelled is None:
                    pending_cancelled = exc
            except Exception:
                if pending_cancelled is None:
                    raise
                try:
                    inner_task.result()
                except Exception:
                    pass
                raise pending_cancelled

        subscriber = inner_task.result()
        if not isinstance(subscriber, RedisWakeupSubscriberProtocol):
            raise TypeError("factory 必须返回 Redis subscriber protocol")
        self._redis_subscriber = subscriber
        if pending_cancelled is not None:
            raise pending_cancelled

    async def _wait_polling_degraded(self) -> None:
        """在 PG polling 中按 health interval 尝试 ping+resubscribe。

        Args:
            无。

        Returns:
            poll/health deadline 或 gate 关闭后返回。

        Raises:
            TypeError: Redis adapter 程序类型错误时传播。
            ValueError: Redis adapter 程序值错误时传播。
        """

        loop = asyncio.get_running_loop()
        health_at = self._next_redis_health_at
        if health_at is None:
            health_at = loop.time() + self.settings.redis_health_interval_seconds
            self._next_redis_health_at = health_at
        if loop.time() >= health_at:
            await self._probe_redis_health()
            return
        wait_seconds = min(
            self.settings.poll_interval_seconds,
            max(health_at - loop.time(), _DRAIN_OBSERVATION_INTERVAL_SECONDS),
        )
        await _sleep_while_open(self.intake_gate, wait_seconds)

    async def _probe_redis_health(self) -> None:
        """执行一次严格 ping+resubscribe health probe。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: Redis adapter 程序类型错误时传播。
            ValueError: Redis adapter 程序值错误时传播。
        """

        client = self.redis_client
        if client is None:
            raise RuntimeError("Redis health client 缺失")
        healthy = await _await_owned_thread_call(client.ping)
        if healthy is not True:
            self._record_redis_failure()
            self._schedule_next_redis_health()
            return
        if await self._ensure_subscription():
            return
        self._schedule_next_redis_health()

    def _record_redis_failure(self) -> None:
        """记录一次连接失败并在精确阈值切换 degraded。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._redis_subscribed = False
        self._redis_failures += 1
        if (
            self._redis_state is RedisRuntimeState.EVENT_ASSISTED
            and self._redis_failures >= self.settings.redis_failure_threshold
        ):
            self._redis_state = RedisRuntimeState.POLLING_DEGRADED
            self._redis_degraded_transitions += 1
            self._schedule_next_redis_health()
            _LOGGER.warning("platform_worker_redis_polling_degraded")

    def _record_redis_success(self) -> None:
        """重置连续失败，并在完整 health success 后恢复 event-assisted。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._redis_failures = 0
        if self._redis_state is RedisRuntimeState.POLLING_DEGRADED:
            self._redis_state = RedisRuntimeState.EVENT_ASSISTED
            self._redis_recovered_transitions += 1
            self._next_redis_health_at = None
            _LOGGER.info("platform_worker_redis_event_assisted")

    def _schedule_next_redis_health(self) -> None:
        """用 settings 健康间隔设置下次 process-local probe deadline。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._next_redis_health_at = asyncio.get_running_loop().time() + self.settings.redis_health_interval_seconds

    async def _cancel_handler_without_terminal(
        self,
        handler_task: asyncio.Task[JobCompletion | JobFailure],
        control: _AttemptControl,
    ) -> None:
        """取消并 reap handler，明确不调用 complete/fail。

        Args:
            handler_task: 唯一 handler owner。
            control: 当前 attempt state。

        Returns:
            无。

        Raises:
            asyncio.CancelledError: 当前 Worker task 被取消时传播。
        """

        control.cancellation.request_cancel()
        if not handler_task.done():
            handler_task.cancel()
        await _reap_cancelled_handler(handler_task)
        control.heartbeat_stop.set()

    async def _close_subscriber(self) -> None:
        """在全部 Worker-owned Redis calls 收口后 exact-once 关闭 PubSub。

        Args:
            无。

        Returns:
            无。

        Raises:
            Exception: adapter 的非 Redis 程序错误传播给 ``run``。
        """

        subscriber = self._redis_subscriber
        if subscriber is None or self._redis_subscriber_closed:
            return
        self._redis_subscriber_closed = True
        self._redis_subscribed = False
        await _await_owned_thread_call(subscriber.close)


async def _await_owned_thread_call(
    function: Callable[_P, _R],
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _R:
    """在唯一 task 中运行 sync call，外层取消后仍 reap inner thread。

    Args:
        function: 同步 callable。
        *args: callable positional arguments。
        **kwargs: callable keyword arguments。

    Returns:
        callable 返回值。

    Raises:
        asyncio.CancelledError: inner thread 收口后重新传播外层取消。
        Exception: callable 的未分类异常原样传播。
    """

    call = partial(function, *args, **kwargs)
    inner_task = asyncio.create_task(asyncio.to_thread(call))
    pending_cancelled: asyncio.CancelledError | None = None
    while not inner_task.done():
        try:
            await asyncio.shield(inner_task)
        except asyncio.CancelledError as exc:
            if pending_cancelled is None:
                pending_cancelled = exc
        except Exception:
            if pending_cancelled is None:
                raise
            break
    if pending_cancelled is not None:
        try:
            inner_task.result()
        except Exception:
            pass
        raise pending_cancelled
    return inner_task.result()


async def _await_cleanup_task(task: asyncio.Task[None]) -> None:
    """抵抗 owner 重复取消并等待独立 cleanup task 真实结束。

    调用方已持有第一份 ``CancelledError`` 并会在本函数返回后 bare
    re-raise；这里仅吞掉等待期间新到达的重复取消请求，不取消 cleanup。

    Args:
        task: 唯一独立 cleanup owner。

    Returns:
        无。

    Raises:
        Exception: cleanup task 的程序错误在真实结束后传播。
    """

    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    task.result()


async def _stop_and_reap_heartbeat(
    control: _AttemptControl,
    heartbeat_task: asyncio.Task[None],
) -> None:
    """停止并完整回收 correlation wait 的局部 heartbeat owner。

    Args:
        control: 当前 attempt 协调状态。
        heartbeat_task: correlation wait 创建的第二 heartbeat owner。

    Returns:
        无。

    Raises:
        asyncio.CancelledError: cleanup task 自身被外部错误取消时传播。
    """

    control.heartbeat_stop.set()
    await _reap_task(heartbeat_task)


async def _wait_until_set(event: asyncio.Event, timeout_seconds: float) -> bool:
    """bounded 等待 event，避免取消真实 sync inner work。

    Args:
        event: event-loop-owned signal。
        timeout_seconds: 正 timeout。

    Returns:
        timeout 前置位为 ``True``；超时为 ``False``。

    Raises:
        asyncio.CancelledError: 当前 task 被取消时传播。
    """

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
    except TimeoutError:
        return False
    return True


async def _sleep_while_open(
    gate: ProcessIntakeGate,
    seconds: float,
) -> None:
    """以短片段等待，使 cooperative stop 不受长配置间隔阻塞。

    Args:
        gate: shared intake gate。
        seconds: 总等待上界。

    Returns:
        deadline 或 gate 关闭后返回。

    Raises:
        asyncio.CancelledError: 当前 task 被取消时传播。
    """

    deadline = asyncio.get_running_loop().time() + seconds
    while gate.is_open:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return
        await asyncio.sleep(min(remaining, _DRAIN_OBSERVATION_INTERVAL_SECONDS))


def _handler_result(
    task: asyncio.Task[JobCompletion | JobFailure],
) -> JobCompletion | JobFailure | None:
    """读取 handler task 结果并把取消收窄为空结果。

    Args:
        task: 已完成 handler task。

    Returns:
        closed handler 结果；task 被取消时为 ``None``。

    Raises:
        Exception: handler gateway 未分类异常原样传播。
    """

    try:
        return task.result()
    except asyncio.CancelledError:
        return None


def _task_exception(task: asyncio.Task[None]) -> BaseException | None:
    """读取已完成辅助 task 的异常而不丢失 owner。

    Args:
        task: 已完成 heartbeat task。

    Returns:
        可空异常；task 被取消时返回 ``CancelledError`` instance。

    Raises:
        无。
    """

    if task.cancelled():
        return asyncio.CancelledError()
    return task.exception()


async def _reap_task(task: asyncio.Task[None]) -> None:
    """等待 heartbeat owner 完成并保留异常供调用方检查。

    Args:
        task: heartbeat task。

    Returns:
        无。

    Raises:
        asyncio.CancelledError: 当前 owner 被取消时传播。
    """

    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        if task.cancelled():
            return
        raise
    except Exception:
        return


async def _reap_cancelled_handler(
    task: asyncio.Task[JobCompletion | JobFailure],
) -> None:
    """等待已请求取消的 handler 真实结束并忽略其业务结果。

    Args:
        task: 唯一 handler task。

    Returns:
        无。

    Raises:
        asyncio.CancelledError: 当前 Worker owner 被再次取消时传播。
    """

    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        if task.cancelled():
            return
        raise
    except Exception:
        return


__all__ = [
    "PlatformWorker",
    "RedisRuntimeState",
    "RedisWakeupClientProtocol",
    "RedisWakeupHint",
    "RedisWakeupRead",
    "RedisWakeupReadAction",
    "RedisWakeupSubscriberFactoryProtocol",
    "RedisWakeupSubscriberProtocol",
    "WorkerJobGatewayProtocol",
]
