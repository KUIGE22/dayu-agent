"""Source Sync 私有异步执行 Service 与 Job handler。

本模块唯一拥有 Source Sync provider state machine、同步 repository 的线程
offload，以及 terminal point-of-no-return 的取消收敛。它不进入 public
Service package export，也不依赖 facade、Fins concrete、Session、Host 或 Agent。
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from dayu.investment.connectors.source import SourceConnectorRegistry
from dayu.investment.domain.identifiers import TenantScope
from dayu.investment.domain.jobs import (
    JobCancellationSignalProtocol,
    JobCompletion,
    JobExecutionRequest,
    JobFailure,
    SafeJobErrorCode,
)
from dayu.investment.domain.source_evidence import (
    SourceConnectorSyncAction,
    SourceConnectorSyncRequest,
    SourceNoProviderReason,
    SourceNoProviderTerminalCandidate,
    SourceTerminalCandidate,
)
from dayu.investment.domain.source_operation import (
    SourceOperationAcquireAction,
    SourceOperationAcquireDecision,
    SourceOperationAcquireRequest,
    SourceTerminalRecordAction,
    SourceTerminalRecordDecision,
    SourceTerminalRecordRequest,
)
from dayu.investment.domain.source_payload import (
    ManualSourceSyncPayload,
    parse_source_sync_payload,
)
from dayu.investment.domain.source_sync import (
    SOURCE_SYNC_JOB_TYPE,
    SourceBindingDisposition,
    SourceSyncExecutionRejected,
    SourceSyncOrigin,
    SourceSyncRepositoryFailure,
    SourceSyncRequestRejected,
)
from dayu.investment.storage.source_sync_protocols import SourceSyncRepositoryProtocol


@runtime_checkable
class SourceSyncExecutionServiceProtocol(Protocol):
    """Source Sync Job handler 使用的私有异步执行协议。"""

    async def execute_source_sync(
        self,
        scope: TenantScope,
        request: JobExecutionRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """执行一次 Source Sync durable Job。

        Args:
            scope: JobService 已验证的可信租户范围。
            request: 不含 lease/token/worker identity 的执行请求。
            cancellation: 协作式领域取消信号。

        Returns:
            闭合 Job completion 或 safe failure。

        Raises:
            asyncio.CancelledError: terminal PONR 前的外层任务取消在同步
                acquire thread 被完整回收后原样传播。
        """

        ...


async def _await_acquire_operation(
    repository: SourceSyncRepositoryProtocol,
    scope: TenantScope,
    request: SourceOperationAcquireRequest,
) -> SourceOperationAcquireDecision:
    """在线程中唯一调用同步 acquire，并完整回收 pre-PONR inner task。

    Args:
        repository: 同步 Source repository。
        scope: 可信租户范围。
        request: Strict acquire request。

    Returns:
        Repository 的 acquire decision。

    Raises:
        asyncio.CancelledError: 任一外层取消发生时，在 inner task 真正结束
            后原样传播第一份取消。
        SourceSyncRequestRejected: Repository 的 closed request rejection。
        SourceSyncExecutionRejected: Repository 的 closed live rejection。
        SourceSyncRepositoryFailure: Repository 的 closed failure。
    """

    inner_task = asyncio.create_task(asyncio.to_thread(repository.acquire_operation, scope, request))
    first_cancellation: asyncio.CancelledError | None = None
    while not inner_task.done():
        try:
            await asyncio.shield(inner_task)
        except asyncio.CancelledError as cancelled:
            if first_cancellation is None:
                first_cancellation = cancelled
        except Exception:
            if first_cancellation is None:
                raise
    if first_cancellation is not None:
        inner_task.exception()
        raise first_cancellation
    return inner_task.result()


async def _await_record_terminal_after_point_of_no_return(
    repository: SourceSyncRepositoryProtocol,
    scope: TenantScope,
    request: SourceTerminalRecordRequest,
) -> SourceTerminalRecordDecision:
    """跨越 PONR 后在线程中记录 terminal，并让 durable outcome 优先。

    Args:
        repository: 同步 Source repository。
        scope: 可信租户范围。
        request: Closed terminal request。

    Returns:
        Repository 已收敛的 authoritative terminal decision。

    Raises:
        SourceSyncRequestRejected: Repository 的 closed request rejection。
        SourceSyncRepositoryFailure: Repository 的 closed failure。

    Notes:
        等待期间的任意外层 ``CancelledError`` 都只触发继续 shield/reap；
        inner repository outcome 是 PONR 后唯一权威结果。
    """

    inner_task = asyncio.create_task(asyncio.to_thread(repository.record_terminal, scope, request))
    while not inner_task.done():
        try:
            await asyncio.shield(inner_task)
        except asyncio.CancelledError:
            continue
    return inner_task.result()


def _source_failure(code: SafeJobErrorCode) -> JobFailure:
    """按 Source safe code 构造唯一合法 retryability。

    Args:
        code: Source execution 使用的闭合 Job safe code。

    Returns:
        与该 code 精确匹配 retryability 的 Job failure。

    Raises:
        ValueError: 收到本 state machine 不拥有的 safe code 时抛出。
    """

    if code is SafeJobErrorCode.SOURCE_INVALID:
        return JobFailure(safe_error_code=code, retryable=False)
    if code in {
        SafeJobErrorCode.SOURCE_OPERATION_BUSY,
        SafeJobErrorCode.SOURCE_INTERRUPTED,
        SafeJobErrorCode.REPOSITORY_FAILURE,
    }:
        return JobFailure(safe_error_code=code, retryable=True)
    raise ValueError("Source execution 不拥有该 safe error code")


class SourceSyncExecutionService(SourceSyncExecutionServiceProtocol):
    """Source repository 与 connector registry 之上的私有异步 state machine。"""

    def __init__(
        self,
        *,
        repository: SourceSyncRepositoryProtocol,
        connector_registry: SourceConnectorRegistry,
    ) -> None:
        """保存 execution 唯一两项依赖。

        Args:
            repository: 同步 Source repository。
            connector_registry: 构造后只读的 Investment connector registry。

        Returns:
            无。

        Raises:
            无。
        """

        self._repository = repository
        self._connector_registry = connector_registry

    async def execute_source_sync(
        self,
        scope: TenantScope,
        request: JobExecutionRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """按 strict parse、acquire、provider、terminal 顺序执行 Source Sync。

        Args:
            scope: JobService 已验证的可信租户范围。
            request: Source Sync Job execution request。
            cancellation: 协作式领域取消信号。

        Returns:
            Persisted Source result 对应的 completion，或闭合 safe failure。

        Raises:
            asyncio.CancelledError: terminal PONR 前的外层取消在同步 thread
                完整回收后原样传播。
            RuntimeError: 构造期已闭合的 registry/decision contract 在运行时
                发生不可能的漂移时抛出。
        """

        try:
            try:
                payload = parse_source_sync_payload(request.payload)
                origin = (
                    SourceSyncOrigin.MANUAL
                    if isinstance(payload, ManualSourceSyncPayload)
                    else SourceSyncOrigin.SCHEDULED
                )
                candidate_snapshot = (
                    payload.execution_snapshot if isinstance(payload, ManualSourceSyncPayload) else None
                )
                acquire_request = SourceOperationAcquireRequest(
                    origin=origin,
                    definition_id=request.definition_id,
                    descriptor=request.descriptor,
                    job_id=request.job_id,
                    attempt_id=request.attempt_id,
                    attempt_number=request.attempt_number,
                    payload_sha256=request.payload.sha256,
                    candidate_execution_snapshot=candidate_snapshot,
                )
            except (TypeError, ValueError):
                return _source_failure(SafeJobErrorCode.SOURCE_INVALID)
            acquired = await _await_acquire_operation(self._repository, scope, acquire_request)
            return await self._continue_after_acquire(scope, request, cancellation, acquired)
        except SourceSyncRequestRejected:
            return _source_failure(SafeJobErrorCode.SOURCE_INVALID)
        except SourceSyncExecutionRejected:
            return _source_failure(SafeJobErrorCode.SOURCE_INTERRUPTED)
        except SourceSyncRepositoryFailure:
            return _source_failure(SafeJobErrorCode.REPOSITORY_FAILURE)

    async def _continue_after_acquire(
        self,
        scope: TenantScope,
        request: JobExecutionRequest,
        cancellation: JobCancellationSignalProtocol,
        acquired: SourceOperationAcquireDecision,
    ) -> JobCompletion | JobFailure:
        """消费 authoritative acquire decision 并在需要时跨越 terminal PONR。

        Args:
            scope: 可信租户范围。
            request: 原始 Job execution request。
            cancellation: 协作式领域取消信号。
            acquired: Repository 的 acquire decision。

        Returns:
            Replay/provider terminal completion 或闭合 safe failure。

        Raises:
            asyncio.CancelledError: provider 或 terminal PONR 前的外层取消。
            SourceSyncRequestRejected: Terminal repository request 拒绝。
            SourceSyncRepositoryFailure: Terminal repository failure。
            RuntimeError: Decision presence 或 registry contract 漂移。
        """

        if acquired.action is SourceOperationAcquireAction.TERMINAL_REPLAY:
            if acquired.terminal_result is None:
                raise RuntimeError("terminal replay 缺少 persisted result")
            return JobCompletion(result=acquired.terminal_result.result)
        if acquired.action is SourceOperationAcquireAction.BUSY:
            return _source_failure(SafeJobErrorCode.SOURCE_OPERATION_BUSY)

        generation = acquired.generation
        snapshot = acquired.execution_snapshot
        snapshot_sha256 = acquired.execution_snapshot_sha256
        disposition = acquired.binding_disposition
        if generation is None or snapshot is None or snapshot_sha256 is None or disposition is None:
            raise RuntimeError("acquired decision presence matrix 漂移")

        candidate: SourceTerminalCandidate
        if disposition is SourceBindingDisposition.STALE:
            candidate = SourceNoProviderTerminalCandidate(reason=SourceNoProviderReason.BINDING_DRIFT)
        elif disposition is SourceBindingDisposition.DISABLED:
            candidate = SourceNoProviderTerminalCandidate(reason=SourceNoProviderReason.DISABLED)
        else:
            connector = self._connector_registry.get(snapshot.binding.connector_key)
            if connector is None:
                raise RuntimeError("executable binding connector 未注册")
            connector_decision = await connector.sync(
                SourceConnectorSyncRequest(
                    operation_id=acquired.operation_id,
                    execution_snapshot=snapshot,
                    execution_snapshot_sha256=snapshot_sha256,
                ),
                cancellation,
            )
            if connector_decision.action is SourceConnectorSyncAction.CANCELLED:
                return _source_failure(SafeJobErrorCode.SOURCE_INTERRUPTED)
            if connector_decision.candidate is None:
                raise RuntimeError("completed connector decision 缺少 candidate")
            candidate = connector_decision.candidate

        terminal_request = SourceTerminalRecordRequest(
            operation_id=acquired.operation_id,
            job_id=request.job_id,
            attempt_id=request.attempt_id,
            attempt_number=request.attempt_number,
            expected_generation=generation,
            expected_execution_snapshot_sha256=snapshot_sha256,
            candidate=candidate,
        )
        if cancellation.is_cancel_requested():
            return _source_failure(SafeJobErrorCode.SOURCE_INTERRUPTED)
        terminal = await _await_record_terminal_after_point_of_no_return(
            self._repository,
            scope,
            terminal_request,
        )
        if terminal.action in {
            SourceTerminalRecordAction.LEASE_LOST,
            SourceTerminalRecordAction.JOB_NOT_LIVE,
        }:
            return _source_failure(SafeJobErrorCode.SOURCE_INTERRUPTED)
        if terminal.result is None:
            raise RuntimeError("terminal decision 缺少 persisted result")
        return JobCompletion(result=terminal.result.result)


class SourceSyncExecutionHandler:
    """只做一次 raw delegation 的 fixed Source Sync Job handler。"""

    def __init__(self, *, execution_service: SourceSyncExecutionServiceProtocol) -> None:
        """保存唯一 execution service 依赖。

        Args:
            execution_service: 私有 Source Sync execution protocol。

        Returns:
            无。

        Raises:
            无。
        """

        self._execution_service = execution_service

    @property
    def job_type(self) -> str:
        """返回 fixed Source Sync durable Job type。

        Args:
            无。

        Returns:
            ``investment.source-sync.v1``。

        Raises:
            无。
        """

        return SOURCE_SYNC_JOB_TYPE

    async def execute(
        self,
        scope: TenantScope,
        request: JobExecutionRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> JobCompletion | JobFailure:
        """把可信 scope、request 与 cancellation 原样委托一次。

        Args:
            scope: JobService 已验证的可信租户范围。
            request: Source Sync execution request。
            cancellation: 协作式领域取消信号。

        Returns:
            Execution service 原样返回的 completion 或 failure。

        Raises:
            asyncio.CancelledError: Execution service 的 pre-PONR 取消原样传播。
        """

        return await self._execution_service.execute_source_sync(scope, request, cancellation)


__all__ = [
    "SourceSyncExecutionHandler",
    "SourceSyncExecutionService",
    "SourceSyncExecutionServiceProtocol",
]
