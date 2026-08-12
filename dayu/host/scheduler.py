"""Durable schedule 的 Host 异步运行循环。

本模块只声明 Host 本地 ``SchedulerGatewayProtocol`` 并编排两个
process-local keyset cursor。所有持久化与 cron 语义均由注入的 Service
gateway 负责；Host 不 import Service、storage、PostgreSQL、Redis 或业务模块。

同步 gateway 调用统一提交到 ``asyncio.to_thread``，并由唯一 inner task owner
收口。soft stop 只关闭 ``ProcessIntakeGate``，不会把线程池调用的 outer task
取消伪装成底层调用终止。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol, runtime_checkable
from uuid import UUID

from dayu.host.process_intake import IntakeEpoch, ProcessIntakeGate
from dayu.investment.config import PlatformQueueSettings
from dayu.investment.domain.identifiers import TenantScope
from dayu.investment.domain.schedules import (
    ScheduleDueCursor,
    ScheduleDueScanResult,
    ScheduleInvariantError,
    ScheduleMaterializationResult,
    ScheduleReplayCursor,
    ScheduleReplayPage,
)

_SCHEDULER_RUNTIME_ERROR_EXIT = 1
_SCHEDULER_GRACEFUL_EXIT = 0


@runtime_checkable
class SchedulerGatewayProtocol(Protocol):
    """Scheduler 可调用的三条 Service-owned 高层入口。"""

    def list_replayable_occurrences(
        self,
        scope: TenantScope,
        cursor: ScheduleReplayCursor | None,
        *,
        limit: int,
    ) -> ScheduleReplayPage:
        """读取 bounded MATERIALIZING-first/PENDING replay page。

        Args:
            scope: 已授权租户范围。
            cursor: PENDING process-local keyset cursor。
            limit: 本页最大 occurrence 数量。

        Returns:
            严格 ``ScheduleReplayPage``。

        Raises:
            ScheduleInvariantError: Service 检测到持久状态不变量破坏时抛出。
        """

        ...

    def reserve_due_occurrences(
        self,
        scope: TenantScope,
        cursor: ScheduleDueCursor | None,
        *,
        limit: int,
    ) -> ScheduleDueScanResult:
        """检查 bounded due page 并至多 reserve 一个 schedule batch。

        Args:
            scope: 已授权租户范围。
            cursor: active due process-local keyset cursor。
            limit: 本次最大检查 schedule 数量。

        Returns:
            严格 ``ScheduleDueScanResult``。

        Raises:
            ScheduleInvariantError: cron 或持久状态不变量破坏时抛出。
        """

        ...

    def materialize_occurrence(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
    ) -> ScheduleMaterializationResult:
        """经 Service 高层入口收口一个 occurrence。

        Args:
            scope: 已授权租户范围。
            occurrence_id: 待收口 occurrence UUID。

        Returns:
            严格 ``ScheduleMaterializationResult``。

        Raises:
            ScheduleInvariantError: materialization 不变量破坏时抛出。
        """

        ...


_SchedulerGatewayResult = ScheduleReplayPage | ScheduleDueScanResult | ScheduleMaterializationResult


class _OwnedSchedulerGateway:
    """串行持有 Scheduler 的真实同步 gateway inner task。"""

    def __init__(self, gateway: SchedulerGatewayProtocol) -> None:
        """保存结构化 gateway。

        Args:
            gateway: 满足 ``SchedulerGatewayProtocol`` 的 Service 实例。

        Returns:
            无。

        Raises:
            无。
        """

        self._gateway = gateway
        self._active: asyncio.Task[_SchedulerGatewayResult] | None = None

    async def list_replayable(
        self,
        scope: TenantScope,
        cursor: ScheduleReplayCursor | None,
        *,
        limit: int,
    ) -> ScheduleReplayPage:
        """在线程池读取 replay page 并严格收窄返回类型。

        Args:
            scope: 已授权租户范围。
            cursor: 当前 replay cursor。
            limit: bounded page 大小。

        Returns:
            ``ScheduleReplayPage``。

        Raises:
            ScheduleInvariantError: 同时存在另一个 inner call 或返回类型非法时抛出。
            BaseException: gateway inner call 的异常原样传播。
        """

        result = await self._call(
            lambda: self._gateway.list_replayable_occurrences(
                scope,
                cursor,
                limit=limit,
            )
        )
        if not isinstance(result, ScheduleReplayPage):
            raise ScheduleInvariantError("scheduler_replay_result_type")
        return result

    async def reserve_due(
        self,
        scope: TenantScope,
        cursor: ScheduleDueCursor | None,
        *,
        limit: int,
    ) -> ScheduleDueScanResult:
        """在线程池执行 due scan 并严格收窄返回类型。

        Args:
            scope: 已授权租户范围。
            cursor: 当前 due cursor。
            limit: bounded scan 大小。

        Returns:
            ``ScheduleDueScanResult``。

        Raises:
            ScheduleInvariantError: 同时存在另一个 inner call 或返回类型非法时抛出。
            BaseException: gateway inner call 的异常原样传播。
        """

        result = await self._call(
            lambda: self._gateway.reserve_due_occurrences(
                scope,
                cursor,
                limit=limit,
            )
        )
        if not isinstance(result, ScheduleDueScanResult):
            raise ScheduleInvariantError("scheduler_due_result_type")
        return result

    async def materialize(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
    ) -> ScheduleMaterializationResult:
        """在线程池执行一次 Service-owned materialization。

        Args:
            scope: 已授权租户范围。
            occurrence_id: 待收口 occurrence UUID。

        Returns:
            ``ScheduleMaterializationResult``。

        Raises:
            ScheduleInvariantError: 同时存在另一个 inner call 或返回类型非法时抛出。
            BaseException: gateway inner call 的异常原样传播。
        """

        result = await self._call(lambda: self._gateway.materialize_occurrence(scope, occurrence_id))
        if not isinstance(result, ScheduleMaterializationResult):
            raise ScheduleInvariantError("scheduler_materialization_result_type")
        return result

    async def _call(
        self,
        operation: Callable[[], _SchedulerGatewayResult],
    ) -> _SchedulerGatewayResult:
        """提交并收口唯一真实 inner thread call。

        外层取消仅被记录；inner task 完成后优先传播 inner 异常，其次重抛
        第一份 ``CancelledError``，避免把 outer cancellation 误当作同步调用
        已停止。

        Args:
            operation: 无参数、返回 closed scheduler DTO 的同步调用。

        Returns:
            inner call 的 closed DTO。

        Raises:
            ScheduleInvariantError: 已有另一个 inner call 尚未收口时抛出。
            BaseException: inner call 的异常优先传播。
            asyncio.CancelledError: inner 成功后重抛第一份 outer cancellation。
        """

        if self._active is not None:
            raise ScheduleInvariantError("scheduler_inner_call_already_active")
        task = asyncio.create_task(asyncio.to_thread(operation))
        self._active = task
        pending_cancelled: asyncio.CancelledError | None = None
        try:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError as exc:
                    if pending_cancelled is None:
                        pending_cancelled = exc
            inner_error = task.exception()
            if inner_error is not None:
                raise inner_error
            result = task.result()
            if pending_cancelled is not None:
                raise pending_cancelled
            return result
        finally:
            if task.done():
                self._active = None


class PlatformScheduler:
    """PG-authoritative durable schedule 的单租户 Host loop。"""

    def __init__(
        self,
        *,
        gateway: SchedulerGatewayProtocol,
        scope: TenantScope,
        settings: PlatformQueueSettings,
        intake_gate: ProcessIntakeGate,
    ) -> None:
        """构造 scheduler runtime。

        Args:
            gateway: 仅暴露三条 Service-owned 高层入口的结构化 gateway。
            scope: 外部 operator 已授权的单租户范围。
            settings: 严格 queue/scheduler runtime settings。
            intake_gate: event-loop-owned process intake gate。

        Returns:
            无。

        Raises:
            TypeError: scope、settings 或 intake_gate 类型非法时抛出。
        """

        if not isinstance(scope, TenantScope):
            raise TypeError("scope 必须是 TenantScope")
        if not isinstance(settings, PlatformQueueSettings):
            raise TypeError("settings 必须是 PlatformQueueSettings")
        if not isinstance(intake_gate, ProcessIntakeGate):
            raise TypeError("intake_gate 必须是 ProcessIntakeGate")
        self._scope = scope
        self._settings = settings
        self._intake_gate = intake_gate
        self._gateway = _OwnedSchedulerGateway(gateway)
        self._replay_cursor: ScheduleReplayCursor | None = None
        self._due_cursor: ScheduleDueCursor | None = None
        self._stop_event = asyncio.Event()
        self._running = False

    def request_stop(self) -> None:
        """关闭 intake gate 并唤醒 tick 间等待。

        本方法必须由 runtime 所属 event loop 调用；signal handler 通过
        ``loop.call_soon`` 进入该线性化点。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._intake_gate.request_stop()
        self._stop_event.set()

    async def run(self) -> int:
        """运行 bounded replay/due ticks 直到 graceful drain 或 invariant。

        Args:
            无。

        Returns:
            graceful drain 返回 0；closed scheduler runtime invariant 返回 1。

        Raises:
            RuntimeError: 同一实例被并发运行时抛出。
            BaseException: 非 closed scheduler invariant 的未知异常原样传播。
        """

        if self._running:
            raise RuntimeError("platform scheduler 已在运行")
        self._running = True
        try:
            while self._intake_gate.is_open:
                await self._run_tick()
                if self._intake_gate.is_open:
                    await self._wait_for_next_tick()
            return _SCHEDULER_GRACEFUL_EXIT
        except ScheduleInvariantError:
            self.request_stop()
            return _SCHEDULER_RUNTIME_ERROR_EXIT
        finally:
            self._running = False

    async def _run_tick(self) -> None:
        """执行一个 bounded replay page 与至多一次 due scan。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInvariantError: gateway page/result 违反 bounded 或 identity
                契约时抛出。
            BaseException: gateway 的其它异常原样传播。
        """

        limit = self._settings.schedule_tick_batch_size
        replay_epoch = self._intake_gate.capture()
        page = await self._gateway.list_replayable(
            self._scope,
            self._replay_cursor,
            limit=limit,
        )
        self._replay_cursor = page.next_pending_cursor
        if len(page.occurrences) > limit:
            raise ScheduleInvariantError("scheduler_replay_page_exceeds_limit")
        if not self._admission_is_current(replay_epoch):
            return

        for occurrence in page.occurrences:
            materialize_epoch = self._intake_gate.capture()
            if not self._admission_is_current(materialize_epoch):
                return
            result = await self._gateway.materialize(self._scope, occurrence.id)
            if result.occurrence.id != occurrence.id:
                raise ScheduleInvariantError("scheduler_materialization_identity")
            if not self._admission_is_current(materialize_epoch):
                return

        due_epoch = self._intake_gate.capture()
        if not self._admission_is_current(due_epoch):
            return
        due = await self._gateway.reserve_due(
            self._scope,
            self._due_cursor,
            limit=limit,
        )
        self._due_cursor = due.next_due_cursor
        if due.inspected_count > limit:
            raise ScheduleInvariantError("scheduler_due_scan_exceeds_limit")
        if not self._admission_is_current(due_epoch):
            return

    def _admission_is_current(self, epoch: IntakeEpoch) -> bool:
        """检查 gateway 派发 epoch 在返回后仍可启动后续工作。

        Args:
            epoch: ``ProcessIntakeGate.capture`` 返回的 ``IntakeEpoch``。

        Returns:
            gate 开放且 epoch 仍为当前值时为 ``True``。

        Raises:
            无。
        """

        return self._intake_gate.is_open and self._intake_gate.is_current(epoch)

    async def _wait_for_next_tick(self) -> None:
        """等待下个 poll tick，soft stop 可立即唤醒。

        Args:
            无。

        Returns:
            timeout 或 stop event 均正常返回。

        Raises:
            asyncio.CancelledError: 非 soft-stop 的外层取消原样传播。
        """

        if self._stop_event.is_set():
            return
        stop_waiter = asyncio.create_task(self._stop_event.wait())
        timer = asyncio.create_task(asyncio.sleep(self._settings.poll_interval_seconds))
        try:
            await asyncio.wait(
                (stop_waiter, timer),
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (stop_waiter, timer):
                if not task.done():
                    task.cancel()
            await asyncio.gather(stop_waiter, timer, return_exceptions=True)


__all__ = ["PlatformScheduler", "SchedulerGatewayProtocol"]
