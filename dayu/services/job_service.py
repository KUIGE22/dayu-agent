"""durable job 应用 Service 与 descriptor-only registry。

本模块是 Slice 2.1 的 application 层唯一 owner：

- ``JobHandlerRegistryProtocol`` / 唯一 concrete ``JobHandlerRegistry``：
  descriptor-only registry，无 invoke/handler/payload API；同 ``job_type``
  的七字段完全一致才幂等，任一不同抛 ``JobInputError``；
- ``HostRunReaderProtocol``：只声明 ``get_run(run_id) -> RunRecord | None``，
  仅 import ``dayu.contracts.run.RunRecord``；现有 ``Host`` 与
  ``RunRegistryProtocol`` 以结构类型满足它；
- ``JobService``：public orchestration 唯一实现，持有
  ``job_store`` / ``descriptor_registry`` / ``host_run_reader``；
  ``enqueue`` 的唯一顺序是 registry gate 早于 store；``recover`` 是唯一
  public recovery orchestration；terminal-only reconciliation 固定四步
  （correlation lookup -> Host reader -> strict mapping -> store
  reconciliation），绝不构造 ``ExecutionContract``、不调用 async Agent
  entry、不用 cache。

本模块依赖存储协议与 pure domain，storage 永不反向 import 本模块。
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Protocol, runtime_checkable
from uuid import UUID

from dayu.contracts.run import RunRecord, RunState
from dayu.investment.composition import PlatformServiceProtocol
from dayu.investment.domain.identifiers import TenantScope
from dayu.investment.domain.jobs import (
    AgentRunCorrelation,
    AgentRunCorrelationObservation,
    AgentRunStartAuthorizationDecision,
    AgentRunTerminalReconciliationAction,
    AgentRunTerminalReconciliationDecision,
    HostRunObservationState,
    JobAttemptReceipt,
    JobCancellationRequest,
    JobClaim,
    JobCompletion,
    JobCorrelationInvariantError,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobFailure,
    JobHandlerDescriptor,
    JobInputError,
    JobLeaseHandle,
    JobRecoveryResult,
)
from dayu.investment.storage.protocols import JobStoreProtocol

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
    """

    def __init__(
        self,
        *,
        job_store: JobStoreProtocol,
        descriptor_registry: JobHandlerRegistryProtocol,
        host_run_reader: HostRunReaderProtocol,
    ) -> None:
        """初始化 Service。

        Args:
            job_store: 仓储实现。
            descriptor_registry: descriptor-only registry。
            host_run_reader: Host run 只读查询源。

        Returns:
            无。

        Raises:
            无。
        """

        self._job_store = job_store
        self._descriptor_registry = descriptor_registry
        self._host_run_reader = host_run_reader

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
        return self._job_store.enqueue(scope, request)

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
    ) -> JobClaim:
        """续约有效 lease。

        Args:
            scope: 租户范围。
            lease: 当前持有的 lease。

        Returns:
            续约后的 ``JobClaim``。
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
    "HostRunReaderProtocol",
    "JobHandlerRegistry",
    "JobHandlerRegistryProtocol",
    "JobService",
]
