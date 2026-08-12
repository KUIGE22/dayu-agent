"""durable job 应用 Service、执行 registry 与 Agent governance。

本模块是 Slice 2.1 的 application 层唯一 owner：

- ``JobHandlerRegistryProtocol`` / 唯一 concrete ``JobHandlerRegistry``：
  descriptor-only registry，无 invoke/handler/payload API；同 ``job_type``
  的七字段完全一致才幂等，任一不同抛 ``JobInputError``；
- ``HostRunReaderProtocol``：只声明 ``get_run(run_id) -> RunRecord | None``，
  仅 import ``dayu.contracts.run.RunRecord``；现有 ``Host`` 与
  ``RunRegistryProtocol`` 以结构类型满足它；
- ``JobExecutionRegistry``：Service-owned、append-only 的 async handler
  registry；descriptor registry、注册 descriptor 与 handler identity 必须
  逐字段闭合；
- ``JobService``：Worker/Scheduler 唯一高层 gateway，负责 execution request
  收窄、PG commit 后 best-effort wakeup、committed schedule enqueue 与 Agent
  governance。Host/Redis/SQLAlchemy concrete type 不得穿过本模块边界。

本模块依赖存储协议与 pure domain，storage 永不反向 import 本模块。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import UUID

from dayu.contracts.run import RunRecord, RunState
from dayu.investment.composition import PlatformServiceProtocol
from dayu.investment.domain.identifiers import TenantScope
from dayu.investment.domain.jobs import (
    AgentRunCorrelation,
    AgentRunCorrelationObservation,
    AgentRunGovernanceAction,
    AgentRunGovernanceCursor,
    AgentRunGovernancePage,
    AgentRunGovernanceProjection,
    AgentRunGovernanceResult,
    AgentRunStartAuthorizationDecision,
    AgentRunTerminalReconciliationAction,
    AgentRunTerminalReconciliationDecision,
    HostRunObservationState,
    JobAttemptReceipt,
    JobCancellationRequest,
    JobCancellationSignalProtocol,
    JobClaim,
    JobCompletion,
    JobCorrelationInvariantError,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobExecutionRequest,
    JobFailure,
    JobHandlerDescriptor,
    JobHeartbeatResult,
    JobInputError,
    JobLeaseHandle,
    JobRecoveryResult,
    JobRepositoryFailureError,
    SafeJobErrorCode,
    job_enqueue_request_fingerprint,
)
from dayu.investment.domain.schedules import (
    ScheduleMaterializationAction,
    ScheduleMaterializationDecision,
    ScheduleOccurrenceState,
)
from dayu.investment.storage.protocols import JobStoreProtocol

_LOGGER = logging.getLogger(__name__)

DURABLE_JOBS_SERVICE_NAME = "durable_jobs"
"""durable job Service 的稳定注册名。"""

_TERMINAL_HOST_OBSERVATION_STATES: frozenset[HostRunObservationState] = frozenset(
    {
        HostRunObservationState.SUCCEEDED,
        HostRunObservationState.FAILED,
        HostRunObservationState.CANCELLED,
        HostRunObservationState.UNSETTLED,
    }
)
"""observation 的 Host terminal 状态集合。"""

_TERMINAL_RECONCILIATION_ACTIONS: frozenset[
    AgentRunTerminalReconciliationAction
] = frozenset(
    {
        AgentRunTerminalReconciliationAction.TERMINALIZED_SUCCESS,
        AgentRunTerminalReconciliationAction.TERMINALIZED_FAILURE,
        AgentRunTerminalReconciliationAction.TERMINALIZED_CANCEL,
        AgentRunTerminalReconciliationAction.ALREADY_TERMINALIZED_SUCCESS,
        AgentRunTerminalReconciliationAction.ALREADY_TERMINALIZED_FAILURE,
        AgentRunTerminalReconciliationAction.ALREADY_TERMINALIZED_CANCEL,
    }
)
"""可安全映射为 ``TERMINAL_RECONCILED`` 的 store actions。"""

_STALE_RECONCILIATION_ACTIONS: frozenset[
    AgentRunTerminalReconciliationAction
] = frozenset(
    {
        AgentRunTerminalReconciliationAction.STALE_ATTEMPT,
        AgentRunTerminalReconciliationAction.ALREADY_STALE_ATTEMPT,
    }
)
"""可安全映射为 ``STALE`` 的 store actions。"""


class _MissingHostBehavior(Enum):
    """声明 reconciliation 对 missing Host run 的闭合处理方式。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    REJECT = "reject"
    WAIT = "wait"
    RECOVER_IF_EXPIRED = "recover_if_expired"


@runtime_checkable
class JobExecutionHandlerProtocol(Protocol):
    """Service-owned async job handler 窄协议。"""

    @property
    def job_type(self) -> str:
        """返回 handler 唯一 job type。

        Args:
            无。

        Returns:
            非空 job type。

        Raises:
            无。
        """
        ...

    async def execute(
        self,
        request: JobExecutionRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """执行一个已收窄的 job request。

        Args:
            request: 不含 lease/token/worker identity 的执行请求。
            cancellation: 协作式业务取消信号。

        Returns:
            闭合完成或失败结果。

        Raises:
            asyncio.CancelledError: 外层 Worker 取消 handler task 时传播。
        """
        ...


@runtime_checkable
class HostRunCancellationProtocol(Protocol):
    """Host 协作式取消的 Service 侧窄协议。"""

    def cancel_run(self, run_id: str) -> RunRecord:
        """幂等写入 Host run cancel intent。

        Args:
            run_id: correlation 绑定的 reserved Host run ID。

        Returns:
            写入后的 Host ``RunRecord``。

        Raises:
            KeyError: run 与调用并发消失时抛出。
        """
        ...


@runtime_checkable
class JobWakeupPublisherProtocol(Protocol):
    """PG commit 后发送 best-effort wakeup hint 的窄协议。"""

    def publish_hint(self, scope: TenantScope, job_id: UUID) -> bool:
        """发送不含 payload/lease/token 的 wakeup hint。

        Args:
            scope: 租户范围。
            job_id: 已提交 job UUID。

        Returns:
            成功发送时为 ``True``；可安全降级到 PG polling 时为 ``False``。

        Raises:
            Exception: adapter 必须把 Redis 可用性故障收窄为
                ``False``；未收窄的程序错误原样传播。
        """
        ...


@dataclass(frozen=True, slots=True)
class JobServiceRuntimeAdapters:
    """持有 JobService 的可选外部运行时 adapter。

    Args:
        host_run_canceller: 可空 Host 协作式取消入口。
        wakeup_publisher: 可空 PG commit 后 wakeup publisher。

    Returns:
        无。

    Raises:
        无。
    """

    host_run_canceller: HostRunCancellationProtocol | None = None
    wakeup_publisher: JobWakeupPublisherProtocol | None = None


@runtime_checkable
class JobHandlerRegistryProtocol(Protocol):
    """descriptor-only job handler registry 契约。

    本协议只声明注册与查询，没有 invoke/handler/payload API。
    """

    def register_descriptor(self, descriptor: JobHandlerDescriptor) -> None:
        """注册一个 immutable descriptor。

        Args:
            descriptor: 待注册的 descriptor。

        Returns:
            无。

        Raises:
            JobInputError: 同 ``job_type`` 的既有 descriptor 任一字段
                不同时抛出。
        """
        ...

    def get_descriptor(self, job_type: str) -> JobHandlerDescriptor | None:
        """查询 descriptor。

        Args:
            job_type: job 类型。

        Returns:
            已注册的 immutable descriptor；不存在时返回 ``None``。
        """
        ...


class JobHandlerRegistry(JobHandlerRegistryProtocol):
    """descriptor-only registry 的唯一 concrete 实现。

    使用私有 ``dict[str, JobHandlerDescriptor]``，不对外暴露；生产
    composition 只构造一次空实例并注入 ``JobService``。
    """

    def __init__(self) -> None:
        """初始化空 registry。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._descriptors: dict[str, JobHandlerDescriptor] = {}

    def register_descriptor(self, descriptor: JobHandlerDescriptor) -> None:
        """注册一个 immutable descriptor。

        Args:
            descriptor: 待注册的 descriptor。

        Returns:
            无。

        Raises:
            JobInputError: 同 ``job_type`` 的既有 descriptor 任一字段
                不同时抛出。
        """

        existing = self._descriptors.get(descriptor.job_type)
        if existing is not None and existing != descriptor:
            raise JobInputError("同 job_type 的 descriptor 必须逐字段相同")
        self._descriptors[descriptor.job_type] = descriptor

    def get_descriptor(self, job_type: str) -> JobHandlerDescriptor | None:
        """查询 descriptor。

        Args:
            job_type: job 类型。

        Returns:
            已注册的 immutable descriptor；不存在时返回 ``None``。
        """

        return self._descriptors.get(job_type)


class JobExecutionRegistry:
    """append-only、exact-idempotent 的 async execution registry。

    首次注册前，descriptor 必须已在 descriptor-only registry 中以七字段
    精确注册，且 ``handler.job_type`` 必须相同。同一 descriptor 与同一
    handler 对象重复注册幂等；不同对象或任一 descriptor 漂移均 fail
    closed。registry 不提供 remove/replace API。

    Args:
        descriptor_registry: descriptor 唯一真源。
    """

    def __init__(self, descriptor_registry: JobHandlerRegistryProtocol) -> None:
        """初始化空 execution registry。

        Args:
            descriptor_registry: descriptor 唯一真源。

        Returns:
            无。

        Raises:
            无。
        """

        self._descriptor_registry = descriptor_registry
        self._handlers: dict[
            str,
            tuple[JobHandlerDescriptor, JobExecutionHandlerProtocol],
        ] = {}

    def register_handler(
        self,
        descriptor: JobHandlerDescriptor,
        handler: JobExecutionHandlerProtocol,
    ) -> None:
        """注册一个 descriptor-closed async handler。

        Args:
            descriptor: handler 对应的 immutable descriptor。
            handler: async execution handler。

        Returns:
            无。

        Raises:
            JobInputError: descriptor 未注册/漂移、handler job type 不同，
                或同 job type 试图替换 descriptor/handler identity 时抛出。
        """

        if not isinstance(descriptor, JobHandlerDescriptor):
            raise JobInputError("descriptor 必须是 JobHandlerDescriptor")
        try:
            registered = self._descriptor_registry.get_descriptor(descriptor.job_type)
        except Exception:
            raise JobInputError("execution descriptor registry 查询失败") from None
        if registered is None or registered != descriptor:
            raise JobInputError("execution descriptor 必须与 descriptor registry 逐字段一致")
        try:
            handler_matches_protocol = isinstance(
                handler,
                JobExecutionHandlerProtocol,
            )
            handler_job_type = handler.job_type if handler_matches_protocol else None
        except Exception:
            raise JobInputError("handler.job_type 查询失败") from None
        if not handler_matches_protocol:
            raise JobInputError("handler 必须满足 JobExecutionHandlerProtocol")
        if handler_job_type != descriptor.job_type:
            raise JobInputError("handler.job_type 必须等于 descriptor.job_type")
        existing = self._handlers.get(descriptor.job_type)
        if existing is not None:
            existing_descriptor, existing_handler = existing
            if existing_descriptor != descriptor or existing_handler is not handler:
                raise JobInputError("同 job_type 不得替换 execution descriptor 或 handler")
            return
        self._handlers[descriptor.job_type] = (descriptor, handler)

    def get_handler(
        self,
        descriptor: JobHandlerDescriptor,
    ) -> JobExecutionHandlerProtocol | None:
        """按完整 descriptor 解析 handler。

        Args:
            descriptor: 调用点持有的完整 descriptor。

        Returns:
            两个 registry 与 handler live job type 都精确一致时返回 handler；
            不存在或任一字段漂移时返回 ``None``。

        Raises:
            无。
        """

        if not isinstance(descriptor, JobHandlerDescriptor):
            return None
        try:
            registered = self._descriptor_registry.get_descriptor(descriptor.job_type)
            entry = self._handlers.get(descriptor.job_type)
            if registered != descriptor or entry is None:
                return None
            entry_descriptor, handler = entry
            if (
                entry_descriptor != descriptor
                or handler.job_type != descriptor.job_type
            ):
                return None
        except Exception:
            return None
        return handler


@runtime_checkable
class HostRunReaderProtocol(Protocol):
    """Host run 的只读查询协议（Service 侧窄视图）。

    现有 ``Host`` 与 ``RunRegistryProtocol`` 都以结构类型满足本协议；
    storage 永不 import 本协议、不接收 reader。
    """

    def get_run(self, run_id: str) -> RunRecord | None:
        """查询单个 Host run。

        Args:
            run_id: Host run ID。

        Returns:
            ``RunRecord``；不存在时返回 ``None``。
        """
        ...


class JobService(PlatformServiceProtocol):
    """durable job 应用 Service。

    Args:
        job_store: 仓储实现。
        descriptor_registry: descriptor-only registry。
        host_run_reader: Host run 只读查询源。
        execution_registry: 可空 execution registry；省略时构造空 registry。
        runtime_adapters: 可选 Host cancel 与 wakeup publisher adapter。
    """

    def __init__(
        self,
        *,
        job_store: JobStoreProtocol,
        descriptor_registry: JobHandlerRegistryProtocol,
        host_run_reader: HostRunReaderProtocol,
        execution_registry: JobExecutionRegistry | None = None,
        runtime_adapters: JobServiceRuntimeAdapters | None = None,
    ) -> None:
        """初始化 Service。

        Args:
            job_store: 仓储实现。
            descriptor_registry: descriptor-only registry。
            host_run_reader: Host run 只读查询源。
            execution_registry: 可空 execution registry；省略时构造空 registry。
            runtime_adapters: 可选 Host cancel 与 wakeup publisher adapter。

        Returns:
            无。

        Raises:
            无。
        """

        self._job_store = job_store
        self._descriptor_registry = descriptor_registry
        self._host_run_reader = host_run_reader
        self._execution_registry = (
            execution_registry
            if execution_registry is not None
            else JobExecutionRegistry(descriptor_registry)
        )
        adapters = (
            runtime_adapters
            if runtime_adapters is not None
            else JobServiceRuntimeAdapters()
        )
        self._host_run_canceller = adapters.host_run_canceller
        self._wakeup_publisher = adapters.wakeup_publisher

    @property
    def platform_service_name(self) -> str:
        """返回稳定注册名。

        Args:
            无。

        Returns:
            精确为 ``durable_jobs``。

        Raises:
            无。
        """

        return DURABLE_JOBS_SERVICE_NAME

    def enqueue(
        self,
        scope: TenantScope,
        request: JobEnqueueRequest,
    ) -> JobEnqueueReceipt:
        """入队一个 job（registry gate 先于 store）。

        Args:
            scope: 租户范围。
            request: 入队请求。

        Returns:
            入队收据。

        Raises:
            JobInputError: descriptor 未注册或与 registry 不一致时抛出，
                且不调用 store、不开始 PG transaction。
        """

        registered = self._descriptor_registry.get_descriptor(
            request.descriptor.job_type
        )
        if registered is None or registered != request.descriptor:
            raise JobInputError("descriptor 未注册或与 registry 不一致")
        receipt = self._job_store.enqueue(scope, request)
        self._publish_hint_best_effort(scope, receipt.job_id)
        return receipt

    def is_execution_available(self, descriptor: JobHandlerDescriptor) -> bool:
        """检查本进程是否能执行完整 descriptor。

        两个 append-only registries 与 handler live ``job_type`` 必须同时
        精确匹配；negative 只代表当前进程本地不可用，不产生持久化副作用。

        Args:
            descriptor: 待检查的完整 handler descriptor。

        Returns:
            当前进程可安全执行时返回 ``True``。

        Raises:
            无。
        """

        if not isinstance(descriptor, JobHandlerDescriptor):
            return False
        try:
            registered = self._descriptor_registry.get_descriptor(
                descriptor.job_type
            )
        except Exception:
            return False
        return (
            registered == descriptor
            and self._execution_registry.get_handler(descriptor) is not None
        )

    async def execute_claim(
        self,
        scope: TenantScope,
        claim: JobClaim,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """通过 Service-owned gateway 调用一个已领取 job 的 handler。

        handler 只收到八字段 ``JobExecutionRequest`` 与 pure cancellation
        signal；lease/fence/raw token/worker id 永不进入 handler。unknown、
        registry 漂移、handler 异常或非法返回统一映射为 non-retryable
        ``HANDLER_REJECTED``。``asyncio.CancelledError`` 属于 Worker drain
        边界，必须原样传播。

        Args:
            scope: 租户范围。
            claim: 已领取 job 快照。
            cancellation: 协作式业务取消信号。

        Returns:
            handler 的闭合结果，或稳定 ``HANDLER_REJECTED``。

        Raises:
            asyncio.CancelledError: 外层任务取消时原样传播。
        """

        rejected = _handler_rejected_failure()
        if not isinstance(claim, JobClaim):
            return rejected
        if claim.tenant_id != scope.tenant_id:
            return rejected
        try:
            registered = self._descriptor_registry.get_descriptor(
                claim.descriptor.job_type
            )
        except Exception:
            return rejected
        if registered != claim.descriptor:
            return rejected
        handler = self._execution_registry.get_handler(claim.descriptor)
        if handler is None:
            return rejected
        request = JobExecutionRequest(
            tenant_id=claim.tenant_id,
            definition_id=claim.definition_id,
            job_id=claim.job_id,
            attempt_id=claim.attempt_id,
            attempt_number=claim.attempt_number,
            descriptor=claim.descriptor,
            payload=claim.payload,
            deadline_at=claim.deadline_at,
        )
        try:
            result = await handler.execute(request, cancellation)
            cancel_requested = cancellation.is_cancel_requested()
        except asyncio.CancelledError:
            raise
        except Exception:
            return rejected
        if not isinstance(result, (JobCompletion, JobFailure)):
            return rejected
        if isinstance(result, JobCompletion) and cancel_requested:
            return rejected
        return result

    def enqueue_committed_schedule_occurrence(
        self,
        scope: TenantScope,
        decision: ScheduleMaterializationDecision,
    ) -> JobEnqueueReceipt:
        """入队一个已提交 MATERIALIZING occurrence commitment。

        本入口只消费 Store 返回的 closed commitment；它重建完整
        ``JobEnqueueRequest`` 并重算唯一 fingerprint，但刻意不执行普通
        registry availability gate，避免 process-local drift 撤销 durable
        commitment。

        Args:
            scope: 租户范围。
            decision: ``action=ENQUEUE`` 且 occurrence=MATERIALIZING 的决策。

        Returns:
            已提交 job 的 enqueue receipt。

        Raises:
            JobInputError: decision/action/state/tenant/snapshot/fingerprint
                任一不闭合时抛出，且不调用 store/publisher。
        """

        if not isinstance(decision, ScheduleMaterializationDecision):
            raise JobInputError("decision 必须是 ScheduleMaterializationDecision")
        occurrence = decision.occurrence
        if (
            decision.action is not ScheduleMaterializationAction.ENQUEUE
            or occurrence.state is not ScheduleOccurrenceState.MATERIALIZING
            or occurrence.tenant_id != scope.tenant_id
            or occurrence.snapshot is None
        ):
            raise JobInputError("只接受本租户已提交的 MATERIALIZING enqueue decision")
        snapshot = occurrence.snapshot
        request = JobEnqueueRequest(
            descriptor=snapshot.descriptor,
            idempotency_key=snapshot.idempotency_key,
            payload=snapshot.payload,
            available_at=snapshot.available_at,
            deadline_at=snapshot.deadline_at,
        )
        if job_enqueue_request_fingerprint(request) != snapshot.request_fingerprint:
            raise JobInputError("schedule snapshot fingerprint 与重建请求不一致")
        receipt = self._job_store.enqueue(scope, request)
        self._publish_hint_best_effort(scope, receipt.job_id)
        return receipt

    def claim(
        self,
        scope: TenantScope,
        worker_id: str,
    ) -> JobClaim | None:
        """领取一个 ready job。

        Args:
            scope: 租户范围。
            worker_id: worker 标识。

        Returns:
            ``JobClaim``；无可用 job 时返回 ``None``。
        """

        return self._job_store.claim(scope, worker_id)

    def heartbeat(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
    ) -> JobHeartbeatResult:
        """续约有效 lease 并返回闭合 heartbeat 结果。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。

        Returns:
            续约后的 ``JobHeartbeatResult``。

        Raises:
            JobLeaseLostError: lease/fence/token 已失效时由 Store 抛出。
            JobStateConflictError: generic job 已有 cancel intent 时由 Store 抛出。
            JobDeadlineExceededError: generic job deadline 已到时由 Store 抛出。
        """

        return self._job_store.heartbeat(scope, lease)

    def complete(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        completion: JobCompletion,
    ) -> JobAttemptReceipt:
        """以有效 lease 正常完成 job。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。
            completion: 完成结果。

        Returns:
            immutable attempt receipt。

        Raises:
            JobLeaseLostError: lease 已失效时由 Store 抛出。
            JobDeadlineExceededError: generic job 已到 deadline 时由 Store 抛出。
            JobGovernanceRequiredError: 存在未终结 correlation 时零
                mutation 抛出，Worker 必须转 governance。
        """

        return self._job_store.complete(scope, lease, completion)

    def fail(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        failure: JobFailure,
    ) -> JobRecoveryResult:
        """以有效 lease 声明安全失败。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。
            failure: 安全失败声明。

        Returns:
            收敛后的 recovery 结果。

        Raises:
            JobLeaseLostError: lease 已失效时由 Store 抛出。
            JobGovernanceRequiredError: 存在未终结 correlation 时零
                mutation 抛出，Worker 必须转 governance。
        """

        return self._job_store.fail(scope, lease, failure)

    def cancel(
        self,
        scope: TenantScope,
        request: JobCancellationRequest,
    ) -> JobRecoveryResult:
        """请求取消一个 job。

        Args:
            scope: 租户范围。
            request: 取消请求。

        Returns:
            收敛后的 recovery 结果。
        """

        return self._job_store.cancel(scope, request)

    def govern_agent_runs(
        self,
        scope: TenantScope,
        cursor: AgentRunGovernanceCursor | None,
        *,
        limit: int,
    ) -> AgentRunGovernancePage:
        """治理一页未终结 Agent run correlations。

        固定顺序为 PG projection -> Host observe -> 必要时 cancel/reobserve
        -> Store reconcile/targeted recover。Host cancel 发送失败保持 PG 零
        mutation 并返回 ``SEND_RETRY``；每个 projection 精确产生一个 closed
        result，storage cursor 原样轮转到 Service page。

        Args:
            scope: 租户范围。
            cursor: process-local keyset cursor；从头开始时为 ``None``。
            limit: keyword-only page limit。

        Returns:
            governance closed results 与下一页 cursor。

        Raises:
            JobInputError: cursor/limit 非法或 projection/result page
                cardinality、identity、顺序、唯一性违反合同时抛出。
            JobRepositoryFailureError: governance PG 查询、reconcile 或
                targeted recovery 发生闭合仓储失败时原样抛出。
        """

        page = self._job_store.list_governable_agent_runs(
            scope,
            cursor,
            limit=limit,
        )
        _require_unique_governance_projection_identities(page.projections)
        results = tuple(
            self._govern_projection(scope, projection)
            for projection in page.projections
        )
        return _build_validated_governance_page(
            projections=page.projections,
            results=results,
            next_cursor=page.next_cursor,
        )

    def _govern_projection(
        self,
        scope: TenantScope,
        projection: AgentRunGovernanceProjection,
    ) -> AgentRunGovernanceResult:
        """治理一个已闭合 PG projection。

        Args:
            scope: 租户范围。
            projection: Store 返回的单条 governance projection。

        Returns:
            单条 closed governance result。

        Raises:
            JobRepositoryFailureError: reconcile/targeted recovery 发生闭合
                仓储失败时原样抛出。Host observation/cancellation 的非取消
                异常仍收窄为 closed result。
        """

        correlation = projection.correlation
        try:
            record = self._host_run_reader.get_run(
                correlation.reserved_host_run_id
            )
        except Exception:
            return _governance_send_retry(projection)
        try:
            observation = _map_run_record_to_observation(
                correlation_id=correlation.id,
                reserved_host_run_id=correlation.reserved_host_run_id,
                record=record,
            )
        except Exception:
            return _governance_invariant_failure(projection)

        if observation.host_state in _TERMINAL_HOST_OBSERVATION_STATES:
            return self._reconcile_governance_observation(
                scope,
                projection,
                observation,
                active_action=AgentRunGovernanceAction.ACTIVE_WAIT,
                missing_host_behavior=_MissingHostBehavior.RECOVER_IF_EXPIRED,
            )
        if observation.host_state is HostRunObservationState.MISSING:
            return self._reconcile_governance_observation(
                scope,
                projection,
                observation,
                active_action=AgentRunGovernanceAction.ACTIVE_WAIT,
                missing_host_behavior=_MissingHostBehavior.RECOVER_IF_EXPIRED,
            )

        initial_result = self._reconcile_governance_observation(
            scope,
            projection,
            observation,
            active_action=AgentRunGovernanceAction.ACTIVE_WAIT,
            missing_host_behavior=_MissingHostBehavior.REJECT,
        )
        if initial_result.action is not AgentRunGovernanceAction.ACTIVE_WAIT:
            return initial_result
        governance_required = (
            projection.job_cancel_requested_at is not None
            or projection.deadline_reached
        )
        if not governance_required:
            return initial_result

        return self._cancel_and_reobserve_projection(scope, projection, record)

    def _cancel_and_reobserve_projection(
        self,
        scope: TenantScope,
        projection: AgentRunGovernanceProjection,
        record: RunRecord | None,
    ) -> AgentRunGovernanceResult:
        """发送必要的 Host cancel，并按同一 correlation 重新观察一次。

        Args:
            scope: 租户范围。
            projection: 已确认需要治理的 PG projection。
            record: 首次 Host observation 使用的 record。

        Returns:
            cancel/reobserve/reconcile 后的 closed governance result。

        Raises:
            JobRepositoryFailureError: 二次 reconciliation 的闭合仓储失败
                原样抛出；Host observation/cancellation 异常收窄为 closed
                ``SEND_RETRY``。
        """

        cancel_sent = False
        if record is None:
            return _governance_invariant_failure(projection)
        correlation = projection.correlation
        if record.cancel_requested_at is None:
            if self._host_run_canceller is None:
                return _governance_send_retry(projection)
            try:
                self._host_run_canceller.cancel_run(
                    correlation.reserved_host_run_id
                )
                cancel_sent = True
            except KeyError:
                # observe/cancel race：KeyError 不是失败结论，必须重新读取
                # 同一 reserved run 后按真实状态收敛。
                cancel_sent = False
            except Exception:
                return _governance_send_retry(projection)

        try:
            reobserved_record = self._host_run_reader.get_run(
                correlation.reserved_host_run_id
            )
        except Exception:
            return _governance_send_retry(projection)
        try:
            reobserved = _map_run_record_to_observation(
                correlation_id=correlation.id,
                reserved_host_run_id=correlation.reserved_host_run_id,
                record=reobserved_record,
            )
        except Exception:
            return _governance_invariant_failure(projection)
        active_action = (
            AgentRunGovernanceAction.CANCEL_REQUESTED
            if cancel_sent
            else AgentRunGovernanceAction.CANCEL_ALREADY_REQUESTED
        )
        reobserved_result = self._reconcile_governance_observation(
            scope,
            projection,
            reobserved,
            active_action=active_action,
            missing_host_behavior=_MissingHostBehavior.REJECT,
        )
        if (
            reobserved_result.action
            in (
                AgentRunGovernanceAction.CANCEL_REQUESTED,
                AgentRunGovernanceAction.CANCEL_ALREADY_REQUESTED,
            )
            and reobserved_record is not None
            and reobserved_record.cancel_requested_at is None
        ):
            return _governance_send_retry(projection)
        return reobserved_result

    def _reconcile_governance_observation(
        self,
        scope: TenantScope,
        projection: AgentRunGovernanceProjection,
        observation: AgentRunCorrelationObservation,
        *,
        active_action: AgentRunGovernanceAction,
        missing_host_behavior: _MissingHostBehavior,
    ) -> AgentRunGovernanceResult:
        """把一次 Host observation 经 Store 决策映射为 governance result。

        Args:
            scope: 租户范围。
            projection: 本页 PG projection。
            observation: strict Host observation。
            active_action: Store 返回 ``HOST_ACTIVE_WAIT`` 时应报告的 action。
            missing_host_behavior: missing observation 的闭合处理方式。

        Returns:
            单条 closed governance result。

        Raises:
            JobRepositoryFailureError: Store reconcile/targeted recovery 的
                闭合仓储失败原样抛出；其它 identity/action 漂移收窄为
                invariant result。
        """

        correlation = projection.correlation
        try:
            decision = self._job_store.reconcile_agent_run_terminal(
                scope,
                correlation.id,
                observation,
            )
        except JobRepositoryFailureError:
            raise
        except Exception:
            return _governance_invariant_failure(projection)
        if (
            decision.correlation.id != correlation.id
            or decision.correlation.job_id != correlation.job_id
            or decision.correlation.attempt_id != correlation.attempt_id
            or decision.observation != observation
        ):
            return _governance_invariant_failure(projection)

        if decision.action in _TERMINAL_RECONCILIATION_ACTIONS:
            return _terminal_reconciliation_result(projection, decision)
        if decision.action in _STALE_RECONCILIATION_ACTIONS:
            return _governance_result_from_projection(
                projection,
                action=AgentRunGovernanceAction.STALE,
                safe_error_code=SafeJobErrorCode.CORRELATION_STALE_ATTEMPT,
            )
        if (
            decision.action
            is AgentRunTerminalReconciliationAction.INVARIANT_FAILURE
        ):
            return _governance_invariant_failure(projection)
        if (
            decision.action
            is AgentRunTerminalReconciliationAction.HOST_ACTIVE_WAIT
        ):
            if observation.host_state not in (
                HostRunObservationState.CREATED,
                HostRunObservationState.QUEUED,
                HostRunObservationState.RUNNING,
            ):
                return _governance_invariant_failure(projection)
            return _governance_result_from_projection(
                projection,
                action=active_action,
                safe_error_code=None,
            )
        if decision.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN:
            return self._resolve_missing_host_reconciliation(
                scope,
                projection,
                observation,
                missing_host_behavior,
            )
        return _governance_invariant_failure(projection)

    def _resolve_missing_host_reconciliation(
        self,
        scope: TenantScope,
        projection: AgentRunGovernanceProjection,
        observation: AgentRunCorrelationObservation,
        behavior: _MissingHostBehavior,
    ) -> AgentRunGovernanceResult:
        """按闭合策略处理 Store 返回的 ``NO_HOST_RUN``。

        Args:
            scope: 租户范围。
            projection: 本页 PG projection。
            observation: strict missing Host observation。
            behavior: missing Host run 的闭合处理方式。

        Returns:
            invariant、等待、targeted recovery 或 race reobserve 结果。

        Raises:
            JobRepositoryFailureError: targeted recovery 的闭合仓储失败原样
                抛出；其它仓储异常收窄为 invariant result。
        """

        if (
            behavior is _MissingHostBehavior.REJECT
            or observation.host_state is not HostRunObservationState.MISSING
        ):
            return _governance_invariant_failure(projection)
        if (
            projection.lease_expires_at > projection.database_now
            or behavior is _MissingHostBehavior.WAIT
        ):
            return _governance_result_from_projection(
                projection,
                action=AgentRunGovernanceAction.MISSING_HOST_WAIT,
                safe_error_code=None,
            )
        if behavior is not _MissingHostBehavior.RECOVER_IF_EXPIRED:
            return _governance_invariant_failure(projection)
        correlation = projection.correlation
        try:
            recovered = self._job_store.recover_agent_run_after_no_host(
                scope,
                correlation.id,
                observation.sha256,
            )
        except JobRepositoryFailureError:
            raise
        except Exception:
            return _governance_invariant_failure(projection)
        if recovered is None:
            return self._reobserve_after_targeted_race(
                scope,
                projection,
            )
        if (
            recovered.job_id != correlation.job_id
            or recovered.attempt_id != correlation.attempt_id
            or recovered.safe_error_code not in (
                SafeJobErrorCode.CANCELLED,
                SafeJobErrorCode.DEADLINE_EXCEEDED,
                SafeJobErrorCode.LEASE_EXPIRED,
                SafeJobErrorCode.RETRY_EXHAUSTED,
            )
        ):
            return _governance_invariant_failure(projection)
        return _governance_result_from_projection(
            projection,
            action=AgentRunGovernanceAction.NO_HOST_RECOVERED,
            safe_error_code=recovered.safe_error_code,
        )

    def _reobserve_after_targeted_race(
        self,
        scope: TenantScope,
        projection: AgentRunGovernanceProjection,
    ) -> AgentRunGovernanceResult:
        """targeted recover 失去前提后只 reobserve/reconcile 一次。

        Args:
            scope: 租户范围。
            projection: 触发 targeted recovery 的原 PG projection。

        Returns:
            reobserve 后的 closed result；仍 missing 时返回等待，不在同一
            调用再次 recover。

        Raises:
            JobRepositoryFailureError: reobserve 后的 Store reconcile 发生
                闭合仓储失败时原样抛出。
        """

        correlation = projection.correlation
        try:
            record = self._host_run_reader.get_run(
                correlation.reserved_host_run_id
            )
        except Exception:
            return _governance_send_retry(projection)
        try:
            observation = _map_run_record_to_observation(
                correlation_id=correlation.id,
                reserved_host_run_id=correlation.reserved_host_run_id,
                record=record,
            )
        except Exception:
            return _governance_invariant_failure(projection)
        return self._reconcile_governance_observation(
            scope,
            projection,
            observation,
            active_action=AgentRunGovernanceAction.ACTIVE_WAIT,
            missing_host_behavior=_MissingHostBehavior.WAIT,
        )

    def _publish_hint_best_effort(
        self,
        scope: TenantScope,
        job_id: UUID,
    ) -> None:
        """在 PG commit 后 best-effort 发布 wakeup hint。

        Args:
            scope: 租户范围。
            job_id: 已提交 job UUID。

        Returns:
            无。

        Raises:
            TypeError: publisher 未返回精确 ``bool`` 时抛出。
            Exception: publisher 未收窄的程序错误原样传播。
        """

        if self._wakeup_publisher is None:
            return
        published = self._wakeup_publisher.publish_hint(scope, job_id)
        if type(published) is not bool:
            raise TypeError("publish_hint 必须返回 bool")
        if not published:
            # Adapter 已把 Redis 可用性故障收窄为 False；此事件只记
            # 固定名称，不携 tenant/job/URL/异常正文。
            _LOGGER.warning("platform_job_wakeup_publish_degraded")

    def reserve_agent_run_correlation(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
    ) -> AgentRunCorrelation:
        """在独立 PG 事务中保留一个 agent run correlation。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。

        Returns:
            已持久化的 ``AgentRunCorrelation``。
        """

        return self._job_store.reserve_agent_run_correlation(scope, lease)

    def list_expired_agent_run_correlations(
        self,
        scope: TenantScope,
    ) -> tuple[AgentRunCorrelation, ...]:
        """列出已提交且绑定 attempt lease 已过期的 correlation。

        Args:
            scope: 租户范围。

        Returns:
            按 ``(created_at ASC, id ASC)`` 排序的 correlation tuple。
        """

        return self._job_store.list_expired_agent_run_correlations(scope)

    def authorize_agent_run_start(
        self,
        scope: TenantScope,
        lease: JobLeaseHandle,
        correlation_id: UUID,
    ) -> AgentRunStartAuthorizationDecision:
        """在单个 PG 事务内产生 live start authorization 决策。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。
            correlation_id: 目标 correlation UUID。

        Returns:
            闭合决策。
        """

        return self._job_store.authorize_agent_run_start(
            scope, lease, correlation_id
        )

    def reconcile_agent_run_terminal(
        self,
        scope: TenantScope,
        correlation_id: UUID,
    ) -> AgentRunTerminalReconciliationDecision:
        """执行 tokenless terminal-only reconciliation。

        重启安全固定顺序：correlation lookup -> Host reader -> strict
        mapping -> store reconciliation；每次 live/restart/replay 都执行
        这四步，绝不用 cache、绝不由 correlation UUID 推导 attempt/
        reserved ID。

        Args:
            scope: 租户范围。
            correlation_id: 目标 correlation UUID。

        Returns:
            闭合决策。
        """

        correlation = self._job_store.get_agent_run_correlation(
            scope, correlation_id
        )
        record = self._host_run_reader.get_run(
            correlation.reserved_host_run_id
        )
        observation = _map_run_record_to_observation(
            correlation_id=correlation.id,
            reserved_host_run_id=correlation.reserved_host_run_id,
            record=record,
        )
        return self._job_store.reconcile_agent_run_terminal(
            scope, correlation_id, observation
        )

    def recover(self, scope: TenantScope) -> tuple[JobRecoveryResult, ...]:
        """执行唯一 public recovery orchestration。

        固定顺序：先 ``list_expired_agent_run_correlations(scope)``
        （结果按 ``created_at ASC, id ASC``）逐条执行四步 reconciliation，
        只对 ``NO_HOST_RUN`` decision 以该 observation 的 ``sha256`` 调
        targeted recovery；``HOST_ACTIVE_WAIT``、任一 terminal、stale 或
        invariant decision 均不得进入任一 recover primitive；最后且仅
        最后调用一次 generic ``recover(scope)`` 收敛无 committed
        correlation 的 attempt。返回 tuple 只含本调用实际产生的非
        ``None`` 结果：先按已排序 correlation 的 targeted 成功结果，
        后接 generic 结果。

        Args:
            scope: 租户范围。

        Returns:
            按上文顺序排列的 ``JobRecoveryResult`` tuple。
        """

        correlations = self.list_expired_agent_run_correlations(scope)
        targeted_results: list[JobRecoveryResult] = []
        for correlation in correlations:
            decision = self.reconcile_agent_run_terminal(scope, correlation.id)
            if (
                decision.action is AgentRunTerminalReconciliationAction.NO_HOST_RUN
            ):
                result = self._job_store.recover_agent_run_after_no_host(
                    scope,
                    correlation.id,
                    decision.observation.sha256,
                )
                if result is not None:
                    targeted_results.append(result)
        generic_results = self._job_store.recover(scope)
        return tuple([*targeted_results, *generic_results])


def _handler_rejected_failure() -> JobFailure:
    """构造统一的 non-retryable handler rejection。

    Args:
        无。

    Returns:
        稳定 ``HANDLER_REJECTED`` failure。

    Raises:
        无。
    """

    return JobFailure(
        safe_error_code=SafeJobErrorCode.HANDLER_REJECTED,
        retryable=False,
    )


def _governance_result_from_projection(
    projection: AgentRunGovernanceProjection,
    *,
    action: AgentRunGovernanceAction,
    safe_error_code: SafeJobErrorCode | None,
) -> AgentRunGovernanceResult:
    """从同一 governance projection 集中构造一个闭合结果。

    Args:
        projection: 结果 identity 的唯一来源。
        action: 闭合治理 action。
        safe_error_code: 与 action 矩阵匹配的安全错误码。

    Returns:
        逐字段复制 correlation/job/attempt identity 的治理结果。

    Raises:
        JobInputError: projection identity 或 action/code 组合非法时抛出。
    """

    correlation = projection.correlation
    return AgentRunGovernanceResult(
        correlation_id=correlation.id,
        job_id=correlation.job_id,
        attempt_id=correlation.attempt_id,
        action=action,
        safe_error_code=safe_error_code,
    )


def _build_validated_governance_page(
    *,
    projections: tuple[AgentRunGovernanceProjection, ...],
    results: tuple[AgentRunGovernanceResult, ...],
    next_cursor: AgentRunGovernanceCursor | None,
) -> AgentRunGovernancePage:
    """验证 projection/result 一一对应后构造 Service page。

    Args:
        projections: Store 返回且已按 keyset 排序的 projection tuple。
        results: Service 按相同顺序生成的 result tuple。
        next_cursor: Store page 的下一页 cursor。

    Returns:
        cardinality、identity、顺序和页内唯一性全部闭合的 Service page。

    Raises:
        JobInputError: 数量不等、逐项 identity/顺序漂移，或同页重复
            correlation/attempt identity 时抛出。
    """

    _require_unique_governance_projection_identities(projections)
    if len(results) != len(projections):
        raise JobInputError("governance result/projection cardinality 必须相等")
    for projection, result in zip(projections, results, strict=True):
        correlation = projection.correlation
        if (
            result.correlation_id != correlation.id
            or result.job_id != correlation.job_id
            or result.attempt_id != correlation.attempt_id
        ):
            raise JobInputError("governance result identity/order 必须逐项匹配 projection")
    return AgentRunGovernancePage(results=results, next_cursor=next_cursor)


def _require_unique_governance_projection_identities(
    projections: tuple[AgentRunGovernanceProjection, ...],
) -> None:
    """在任何 Host/PG 治理副作用前拒绝页内重复 identity。

    Args:
        projections: Store 返回的 governance projection tuple。

    Returns:
        无。

    Raises:
        JobInputError: 同页 correlation 或 attempt identity 重复时抛出。
    """

    seen_correlation_ids: set[UUID] = set()
    seen_attempt_ids: set[UUID] = set()
    for projection in projections:
        correlation = projection.correlation
        if correlation.id in seen_correlation_ids:
            raise JobInputError("governance page 不得重复 correlation identity")
        if correlation.attempt_id in seen_attempt_ids:
            raise JobInputError("governance page 不得重复 attempt identity")
        seen_correlation_ids.add(correlation.id)
        seen_attempt_ids.add(correlation.attempt_id)


def _governance_invariant_failure(
    projection: AgentRunGovernanceProjection,
) -> AgentRunGovernanceResult:
    """构造统一的 governance invariant result。

    Args:
        projection: identity 的原始 PG projection。

    Returns:
        ``INVARIANT_FAILURE / CORRELATION_INVARIANT``。

    Raises:
        无。
    """

    return _governance_result_from_projection(
        projection,
        action=AgentRunGovernanceAction.INVARIANT_FAILURE,
        safe_error_code=SafeJobErrorCode.CORRELATION_INVARIANT,
    )


def _governance_send_retry(
    projection: AgentRunGovernanceProjection,
) -> AgentRunGovernanceResult:
    """构造 Host interaction 可重试结果。

    Args:
        projection: identity 的原始 PG projection。

    Returns:
        ``SEND_RETRY / None``。

    Raises:
        无。
    """

    return _governance_result_from_projection(
        projection,
        action=AgentRunGovernanceAction.SEND_RETRY,
        safe_error_code=None,
    )


def _terminal_reconciliation_result(
    projection: AgentRunGovernanceProjection,
    decision: AgentRunTerminalReconciliationDecision,
) -> AgentRunGovernanceResult:
    """把 terminal reconciliation decision 收窄为 governance result。

    Args:
        projection: identity 的原始 PG projection。
        decision: Store 返回的 terminal decision。

    Returns:
        identity/receipt/code 闭合时返回 ``TERMINAL_RECONCILED``；否则
        返回 invariant result。

    Raises:
        无。
    """

    receipt = decision.receipt
    if receipt is None:
        return _governance_invariant_failure(projection)
    correlation = decision.correlation
    if (
        receipt.tenant_id != correlation.tenant_id
        or receipt.job_id != correlation.job_id
        or receipt.attempt_id != correlation.attempt_id
    ):
        return _governance_invariant_failure(projection)
    code = receipt.safe_error_code
    if code in (
        SafeJobErrorCode.HOST_RUN_FAILED,
        SafeJobErrorCode.HOST_RUN_CANCELLED,
        SafeJobErrorCode.HOST_RUN_UNSETTLED,
    ):
        safe_code = code
    elif code in (
        None,
        SafeJobErrorCode.CANCELLED,
        SafeJobErrorCode.DEADLINE_EXCEEDED,
    ):
        safe_code = None
    else:
        return _governance_invariant_failure(projection)
    return _governance_result_from_projection(
        projection,
        action=AgentRunGovernanceAction.TERMINAL_RECONCILED,
        safe_error_code=safe_code,
    )


def _map_run_record_to_observation(
    *,
    correlation_id: UUID,
    reserved_host_run_id: str,
    record: RunRecord | None,
) -> AgentRunCorrelationObservation:
    """把 Host ``RunRecord | None`` strict mapping 为 observation。

    Args:
        correlation_id: correlation UUID。
        reserved_host_run_id: correlation 绑定的 reserved Host run ID。
        record: Host run 记录或 ``None``。

    Returns:
        ``AgentRunCorrelationObservation``。

    Raises:
        JobCorrelationInvariantError: run_id 不等于 reserved ID、terminal
            时间缺失/非 aware UTC，或非 terminal 时间非空时抛出。
    """

    if record is None:
        return AgentRunCorrelationObservation(
            correlation_id=correlation_id,
            host_run_id=reserved_host_run_id,
            host_state=HostRunObservationState.MISSING,
            host_completed_at=None,
            sha256=_observation_sha256(
                correlation_id=correlation_id,
                host_run_id=reserved_host_run_id,
                host_state=HostRunObservationState.MISSING.value,
                host_completed_at=None,
            ),
        )
    if record.run_id != reserved_host_run_id:
        raise JobCorrelationInvariantError()
    host_state = _run_state_to_observation_state(record.state)
    completed_at = record.completed_at
    if host_state in _TERMINAL_HOST_OBSERVATION_STATES:
        if completed_at is None:
            raise JobCorrelationInvariantError()
        if completed_at.tzinfo is None or completed_at.utcoffset() != timedelta(0):
            raise JobCorrelationInvariantError()
    elif completed_at is not None:
        raise JobCorrelationInvariantError()
    return AgentRunCorrelationObservation(
        correlation_id=correlation_id,
        host_run_id=reserved_host_run_id,
        host_state=host_state,
        host_completed_at=completed_at,
        sha256=_observation_sha256(
            correlation_id=correlation_id,
            host_run_id=reserved_host_run_id,
            host_state=host_state.value,
            host_completed_at=(
                completed_at.isoformat() if completed_at is not None else None
            ),
        ),
    )


def _run_state_to_observation_state(
    run_state: RunState,
) -> HostRunObservationState:
    """把 Host ``RunState`` 一一映射为 observation state。

    Args:
        run_state: Host run 状态。

    Returns:
        同名 lowercase ``HostRunObservationState``。

    Raises:
        JobCorrelationInvariantError: 未知状态时抛出。
    """

    mapping = {
        RunState.CREATED: HostRunObservationState.CREATED,
        RunState.QUEUED: HostRunObservationState.QUEUED,
        RunState.RUNNING: HostRunObservationState.RUNNING,
        RunState.SUCCEEDED: HostRunObservationState.SUCCEEDED,
        RunState.FAILED: HostRunObservationState.FAILED,
        RunState.CANCELLED: HostRunObservationState.CANCELLED,
        RunState.UNSETTLED: HostRunObservationState.UNSETTLED,
    }
    mapped = mapping.get(run_state)
    if mapped is None:
        raise JobCorrelationInvariantError()
    return mapped


def _observation_sha256(
    *,
    correlation_id: UUID,
    host_run_id: str,
    host_state: str,
    host_completed_at: str | None,
) -> str:
    """计算 observation 的 canonical-safe JSON fingerprint。

    Args:
        correlation_id: correlation UUID。
        host_run_id: Host run ID。
        host_state: observation state 字符串。
        host_completed_at: 可空 ISO 时间字符串。

    Returns:
        小写 64-hex SHA-256。

    Raises:
        无。
    """

    canonical = json.dumps(
        {
            "correlation_id": str(correlation_id),
            "host_run_id": host_run_id,
            "host_state": host_state,
            "host_completed_at": host_completed_at,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "DURABLE_JOBS_SERVICE_NAME",
    "HostRunCancellationProtocol",
    "HostRunReaderProtocol",
    "JobExecutionHandlerProtocol",
    "JobExecutionRegistry",
    "JobHandlerRegistry",
    "JobHandlerRegistryProtocol",
    "JobService",
    "JobServiceRuntimeAdapters",
    "JobWakeupPublisherProtocol",
]
