"""PlatformScheduler 的 cursor、drain barrier 与 runtime exit 测试。"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import UUID, uuid4

import pytest

from dayu.host.process_intake import ProcessIntakeGate
from dayu.host.scheduler import PlatformScheduler, SchedulerGatewayProtocol
from dayu.investment.config import PlatformQueueMode, PlatformQueueSettings
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.domain.jobs import (
    CanonicalJobDocument,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobHandlerDescriptor,
    JobState,
    build_canonical_document,
    job_enqueue_request_fingerprint,
)
from dayu.investment.domain.schedules import (
    CanonicalScheduleEnqueueSnapshot,
    ScheduleDueCursor,
    ScheduleDueScanResult,
    ScheduleInvariantError,
    ScheduleMaterializationResult,
    ScheduleMaterializationResultAction,
    ScheduleOccurrence,
    ScheduleOccurrenceState,
    ScheduleReplayCursor,
    ScheduleReplayPage,
    ScheduleReservationResult,
    ScheduleReserveAction,
)

_NOW = datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc)


def _scope() -> TenantScope:
    """构造稳定测试租户范围。

    Args:
        无。

    Returns:
        经 ``Principal`` 派生的 ``TenantScope``。

    Raises:
        无。
    """

    return Principal(
        tenant_id=TenantId("00000000-0000-0000-0000-000000000501"),
        user_id="scheduler-test",
    ).to_scope()


def _settings(*, batch_size: int = 2, poll_seconds: float = 3600.0) -> PlatformQueueSettings:
    """构造不接触 Redis 的 integration queue settings。

    Args:
        batch_size: scheduler bounded batch 大小。
        poll_seconds: tick 间等待秒数。

    Returns:
        严格 ``PlatformQueueSettings``。

    Raises:
        无。
    """

    return PlatformQueueSettings(
        mode=PlatformQueueMode.POSTGRES_POLLING,
        poll_interval_seconds=poll_seconds,
        schedule_tick_batch_size=batch_size,
    )


def _descriptor() -> JobHandlerDescriptor:
    """构造 scheduler 测试 descriptor。

    Args:
        无。

    Returns:
        完整 ``JobHandlerDescriptor``。

    Raises:
        无。
    """

    return JobHandlerDescriptor(
        job_type="test.scheduler",
        payload_schema_name="test.scheduler.payload",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=60,
    )


def _payload() -> CanonicalJobDocument:
    """构造 canonical scheduler payload。

    Args:
        无。

    Returns:
        canonical payload document。

    Raises:
        无。
    """

    return build_canonical_document(
        {"kind": "scheduler-test"},
        schema_name="test.scheduler.payload",
        schema_version=1,
    )


def _snapshot(scheduled_for: datetime) -> CanonicalScheduleEnqueueSnapshot:
    """构造与 fire 时间绑定的 immutable enqueue snapshot。

    Args:
        scheduled_for: occurrence fire 时间。

    Returns:
        完整 canonical snapshot。

    Raises:
        无。
    """

    descriptor = _descriptor()
    payload = _payload()
    request = JobEnqueueRequest(
        descriptor=descriptor,
        idempotency_key=f"schedule-test:{scheduled_for.isoformat()}",
        payload=payload,
        available_at=scheduled_for,
        deadline_at=scheduled_for + timedelta(minutes=10),
    )
    return CanonicalScheduleEnqueueSnapshot(
        descriptor=descriptor,
        payload=payload,
        idempotency_key=request.idempotency_key,
        available_at=request.available_at,
        deadline_at=request.deadline_at,
        request_fingerprint=job_enqueue_request_fingerprint(request),
    )


def _occurrence(
    *,
    occurrence_id: UUID | None = None,
    state: ScheduleOccurrenceState = ScheduleOccurrenceState.PENDING,
    job_id: UUID | None = None,
) -> ScheduleOccurrence:
    """构造 pending/materializing/enqueued occurrence。

    Args:
        occurrence_id: 可空固定 occurrence UUID。
        state: 非 skipped occurrence 状态。
        job_id: enqueued 状态绑定的 job UUID。

    Returns:
        合法 ``ScheduleOccurrence``。

    Raises:
        无。
    """

    return ScheduleOccurrence(
        id=occurrence_id if occurrence_id is not None else uuid4(),
        tenant_id=_scope().tenant_id,
        schedule_id=uuid4(),
        schedule_version=2,
        scheduled_for=_NOW,
        state=state,
        snapshot=_snapshot(_NOW),
        job_id=job_id,
        coalesced_count=0,
        skip_reason=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _unavailable_result(occurrence: ScheduleOccurrence) -> ScheduleMaterializationResult:
    """构造 pending unavailable materialization 结果。

    Args:
        occurrence: pending occurrence。

    Returns:
        closed unavailable result。

    Raises:
        无。
    """

    return ScheduleMaterializationResult(
        action=ScheduleMaterializationResultAction.UNAVAILABLE,
        occurrence=occurrence,
        enqueue_receipt=None,
    )


def _enqueued_result(occurrence: ScheduleOccurrence) -> ScheduleMaterializationResult:
    """把 occurrence identity 收口为 enqueued 结果。

    Args:
        occurrence: 待保留 identity 的 replay occurrence。

    Returns:
        携带真实 enqueue receipt 的 closed result。

    Raises:
        无。
    """

    job_id = uuid4()
    enqueued = ScheduleOccurrence(
        id=occurrence.id,
        tenant_id=occurrence.tenant_id,
        schedule_id=occurrence.schedule_id,
        schedule_version=occurrence.schedule_version,
        scheduled_for=occurrence.scheduled_for,
        state=ScheduleOccurrenceState.ENQUEUED,
        snapshot=occurrence.snapshot,
        job_id=job_id,
        coalesced_count=occurrence.coalesced_count,
        skip_reason=None,
        created_at=occurrence.created_at,
        updated_at=occurrence.updated_at,
    )
    receipt = JobEnqueueReceipt(
        tenant_id=occurrence.tenant_id,
        definition_id=uuid4(),
        job_id=job_id,
        state=JobState.READY,
        idempotency_reused=False,
    )
    return ScheduleMaterializationResult(
        action=ScheduleMaterializationResultAction.ENQUEUED,
        occurrence=enqueued,
        enqueue_receipt=receipt,
    )


def _page(*occurrences: ScheduleOccurrence) -> ScheduleReplayPage:
    """构造带最后 pending key 的 replay page。

    Args:
        occurrences: MATERIALIZING-first/PENDING occurrence 序列。

    Returns:
        严格 replay page。

    Raises:
        无。
    """

    pending = tuple(occurrence for occurrence in occurrences if occurrence.state is ScheduleOccurrenceState.PENDING)
    cursor = (
        ScheduleReplayCursor(
            scheduled_for=pending[-1].scheduled_for,
            occurrence_id=pending[-1].id,
        )
        if pending
        else None
    )
    return ScheduleReplayPage(
        occurrences=tuple(occurrences),
        next_pending_cursor=cursor,
    )


class _RecordingSchedulerGateway:
    """可阻塞、可编程的 strict Scheduler gateway fake。"""

    def __init__(
        self,
        *,
        replay_pages: tuple[ScheduleReplayPage, ...] = (),
        due_results: tuple[ScheduleDueScanResult, ...] = (),
        materialization_results: tuple[ScheduleMaterializationResult, ...] = (),
    ) -> None:
        """保存闭合返回序列与同步 barrier。

        Args:
            replay_pages: 按调用顺序返回的 replay pages。
            due_results: 按调用顺序返回的 due scan results。
            materialization_results: 按调用顺序返回的 materialization results。

        Returns:
            无。

        Raises:
            无。
        """

        self.replay_pages = deque(replay_pages)
        self.due_results = deque(due_results)
        self.materialization_results = deque(materialization_results)
        self.replay_calls: list[ScheduleReplayCursor | None] = []
        self.due_calls: list[ScheduleDueCursor | None] = []
        self.materialize_calls: list[UUID] = []
        self.call_order: list[str] = []
        self.block_replay = False
        self.block_due = False
        self.block_materialize = False
        self.replay_entered = Event()
        self.replay_release = Event()
        self.due_entered = Event()
        self.due_release = Event()
        self.materialize_entered = Event()
        self.materialize_release = Event()
        self.due_error: ScheduleInvariantError | None = None
        self.on_materialize: Callable[[UUID], None] | None = None

    def list_replayable_occurrences(
        self,
        scope: TenantScope,
        cursor: ScheduleReplayCursor | None,
        *,
        limit: int,
    ) -> ScheduleReplayPage:
        """记录 replay cursor 并返回下一页。

        Args:
            scope: 调用租户范围。
            cursor: 当前 replay cursor。
            limit: bounded page 大小。

        Returns:
            下一条编程 page 或空页。

        Raises:
            ScheduleInvariantError: 测试 barrier 超时时抛出。
        """

        assert scope == _scope()
        assert limit > 0
        self.replay_calls.append(cursor)
        self.call_order.append("replay")
        self.replay_entered.set()
        self._wait_if_blocked(self.block_replay, self.replay_release, "replay")
        if self.replay_pages:
            return self.replay_pages.popleft()
        return ScheduleReplayPage(occurrences=(), next_pending_cursor=None)

    def reserve_due_occurrences(
        self,
        scope: TenantScope,
        cursor: ScheduleDueCursor | None,
        *,
        limit: int,
    ) -> ScheduleDueScanResult:
        """记录 due cursor 并返回下一条 scan result。

        Args:
            scope: 调用租户范围。
            cursor: 当前 due cursor。
            limit: bounded scan 大小。

        Returns:
            下一条编程 result 或 empty result。

        Raises:
            ScheduleInvariantError: 编程 error 或 barrier timeout 时抛出。
        """

        assert scope == _scope()
        assert limit > 0
        self.due_calls.append(cursor)
        self.call_order.append("due")
        self.due_entered.set()
        self._wait_if_blocked(self.block_due, self.due_release, "due")
        if self.due_error is not None:
            raise self.due_error
        if self.due_results:
            return self.due_results.popleft()
        return ScheduleDueScanResult(
            reservation=None,
            next_due_cursor=None,
            inspected_count=0,
        )

    def materialize_occurrence(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
    ) -> ScheduleMaterializationResult:
        """记录 materialization identity 并返回下一结果。

        Args:
            scope: 调用租户范围。
            occurrence_id: occurrence UUID。

        Returns:
            下一条编程 materialization result。

        Raises:
            ScheduleInvariantError: 未提供结果或 barrier timeout 时抛出。
        """

        assert scope == _scope()
        self.materialize_calls.append(occurrence_id)
        self.call_order.append("materialize")
        self.materialize_entered.set()
        if self.on_materialize is not None:
            self.on_materialize(occurrence_id)
        self._wait_if_blocked(
            self.block_materialize,
            self.materialize_release,
            "materialize",
        )
        if not self.materialization_results:
            raise ScheduleInvariantError("test_materialization_result_missing")
        return self.materialization_results.popleft()

    @staticmethod
    def _wait_if_blocked(blocked: bool, release: Event, label: str) -> None:
        """在测试启用时等待同步 release barrier。

        Args:
            blocked: 是否需要阻塞。
            release: 由 event loop 测试释放的 threading event。
            label: timeout safe code 后缀。

        Returns:
            无。

        Raises:
            ScheduleInvariantError: 三十秒内未释放时抛出。
        """

        if blocked and not release.wait(30.0):
            raise ScheduleInvariantError(f"test_{label}_barrier_timeout")


def _scheduler(gateway: SchedulerGatewayProtocol, gate: ProcessIntakeGate) -> PlatformScheduler:
    """构造测试 scheduler。

    Args:
        gateway: recording gateway。
        gate: shared intake gate。

    Returns:
        ``PlatformScheduler``。

    Raises:
        无。
    """

    return PlatformScheduler(
        gateway=gateway,
        scope=_scope(),
        settings=_settings(),
        intake_gate=gate,
    )


def test_schedule_gateway_fake_structurally_satisfies_host_protocol() -> None:
    """Fake 精确满足 Host-local protocol 且不需要继承 Service 类型。"""

    gateway: SchedulerGatewayProtocol = _RecordingSchedulerGateway()

    assert isinstance(gateway, SchedulerGatewayProtocol)


@pytest.mark.asyncio
async def test_scheduler_materializes_due_fire_through_durable_materializing_occurrence() -> None:
    """due tick 只 reserve，下一 tick 才从 durable replay 完成 materialization。"""

    pending = _occurrence()
    due_cursor = ScheduleDueCursor(next_fire_at=_NOW, schedule_id=pending.schedule_id)
    due = ScheduleDueScanResult(
        reservation=ScheduleReservationResult(
            action=ScheduleReserveAction.RESERVED,
            occurrences=(pending,),
        ),
        next_due_cursor=due_cursor,
        inspected_count=1,
    )
    gateway = _RecordingSchedulerGateway(
        replay_pages=(
            ScheduleReplayPage(occurrences=(), next_pending_cursor=None),
            _page(pending),
        ),
        due_results=(due,),
        materialization_results=(_enqueued_result(pending),),
    )
    gate = ProcessIntakeGate()
    scheduler = PlatformScheduler(
        gateway=gateway,
        scope=_scope(),
        settings=_settings(poll_seconds=0.01),
        intake_gate=gate,
    )
    loop = asyncio.get_running_loop()

    def _stop_after_materialization(_occurrence_id: UUID) -> None:
        """在线程调用返回前把 stop callback 安全投递到 event loop。

        Args:
            _occurrence_id: 已完成 materialization 的 occurrence UUID。

        Returns:
            无。

        Raises:
            无。
        """

        loop.call_soon_threadsafe(scheduler.request_stop)

    gateway.on_materialize = _stop_after_materialization

    exit_code = await scheduler.run()

    assert exit_code == 0
    assert gateway.call_order == ["replay", "due", "replay", "materialize"]
    assert gateway.materialize_calls == [pending.id]
    assert gateway.due_calls == [None]


@pytest.mark.asyncio
async def test_scheduler_assigns_each_typed_cursor_before_first_followup_await_and_never_mixes_them() -> None:
    """replay cursor 在 materialize 前可见，due cursor 在下一 tick 独立回传。"""

    pending = _occurrence()
    replay_page = _page(pending)
    replay_cursor = replay_page.next_pending_cursor
    assert replay_cursor is not None
    due_cursor = ScheduleDueCursor(next_fire_at=_NOW, schedule_id=uuid4())
    due_result = ScheduleDueScanResult(
        reservation=None,
        next_due_cursor=due_cursor,
        inspected_count=1,
    )
    gateway = _RecordingSchedulerGateway(
        replay_pages=(replay_page, ScheduleReplayPage(occurrences=(), next_pending_cursor=None)),
        due_results=(due_result, ScheduleDueScanResult(None, None, 0)),
        materialization_results=(_unavailable_result(pending),),
    )
    gate = ProcessIntakeGate()
    scheduler = PlatformScheduler(
        gateway=gateway,
        scope=_scope(),
        settings=_settings(poll_seconds=0.01),
        intake_gate=gate,
    )
    replay_seen_before_materialize: list[ScheduleReplayCursor | None] = []

    def _observe_replay_cursor(_occurrence_id: UUID) -> None:
        """记录 materialize inner call 启动时 Host 已提交的 replay cursor。

        Args:
            _occurrence_id: 当前 occurrence UUID（identity 由外层另断言）。

        Returns:
            无。

        Raises:
            无。
        """

        replay_seen_before_materialize.append(scheduler._replay_cursor)

    gateway.on_materialize = _observe_replay_cursor
    task = asyncio.create_task(scheduler.run())
    while len(gateway.due_calls) < 2:
        await asyncio.sleep(0.001)
    scheduler.request_stop()

    assert await task == 0
    assert replay_seen_before_materialize == [replay_cursor]
    assert gateway.replay_calls == [None, replay_cursor]
    assert gateway.due_calls == [None, due_cursor]


@pytest.mark.parametrize("blocked_call", ["replay", "due"])
@pytest.mark.asyncio
async def test_scheduler_replay_or_reserve_returning_after_drain_gate_starts_no_materialization(
    blocked_call: str,
) -> None:
    """gate 后返回的 replay/due 结果只保留 PG work，不启动 materialize。

    Args:
        blocked_call: 本 case 阻塞 replay 或 due gateway。
    """

    pending = _occurrence()
    gateway = _RecordingSchedulerGateway(
        replay_pages=(_page(pending),),
        materialization_results=(_unavailable_result(pending),),
    )
    if blocked_call == "replay":
        gateway.block_replay = True
        entered = gateway.replay_entered
        release = gateway.replay_release
    else:
        gateway.replay_pages = deque((ScheduleReplayPage(occurrences=(), next_pending_cursor=None),))
        gateway.block_due = True
        entered = gateway.due_entered
        release = gateway.due_release
    scheduler = _scheduler(gateway, ProcessIntakeGate())
    task = asyncio.create_task(scheduler.run())
    assert await asyncio.to_thread(entered.wait, 2.0)

    scheduler.request_stop()
    release.set()

    assert await task == 0
    assert gateway.materialize_calls == []


@pytest.mark.asyncio
async def test_materialization_admitted_before_drain_gate_only_finishes_current_occurrence() -> None:
    """gate 前已派发的 materialization 收口，后续 item 与 due 不再启动。"""

    first = _occurrence()
    second = _occurrence()
    gateway = _RecordingSchedulerGateway(
        replay_pages=(_page(first, second),),
        materialization_results=(
            _unavailable_result(first),
            _unavailable_result(second),
        ),
    )
    gateway.block_materialize = True
    scheduler = _scheduler(gateway, ProcessIntakeGate())
    task = asyncio.create_task(scheduler.run())
    assert await asyncio.to_thread(gateway.materialize_entered.wait, 2.0)

    scheduler.request_stop()
    gateway.materialize_release.set()

    assert await task == 0
    assert gateway.materialize_calls == [first.id]
    assert gateway.due_calls == []


@pytest.mark.asyncio
async def test_scheduler_cron_iteration_exhaustion_returns_exit_one_without_mutation() -> None:
    """Service closed cron exhaustion 让 scheduler 返回 1 且不 materialize。"""

    gateway = _RecordingSchedulerGateway(replay_pages=(ScheduleReplayPage(occurrences=(), next_pending_cursor=None),))
    gateway.due_error = ScheduleInvariantError("schedule_cron_iteration_exhausted")
    gate = ProcessIntakeGate()
    scheduler = _scheduler(gateway, gate)

    assert await scheduler.run() == 1
    assert not gate.is_open
    assert gateway.materialize_calls == []


@pytest.mark.asyncio
async def test_scheduler_rejects_cross_occurrence_materialization_result() -> None:
    """Gateway 返回另一 occurrence identity 时 scheduler fail closed。"""

    requested = _occurrence()
    other = _occurrence()
    gateway = _RecordingSchedulerGateway(
        replay_pages=(_page(requested),),
        materialization_results=(_unavailable_result(other),),
    )
    scheduler = _scheduler(gateway, ProcessIntakeGate())

    assert await scheduler.run() == 1
    assert gateway.materialize_calls == [requested.id]


@pytest.mark.asyncio
async def test_scheduler_request_stop_wakes_long_poll_without_second_tick() -> None:
    """soft stop 立即唤醒长 poll，且不启动第二个 replay tick。"""

    gateway = _RecordingSchedulerGateway()
    scheduler = _scheduler(gateway, ProcessIntakeGate())
    task = asyncio.create_task(scheduler.run())
    assert await asyncio.to_thread(gateway.due_entered.wait, 2.0)
    await asyncio.sleep(0)

    scheduler.request_stop()

    assert await asyncio.wait_for(task, timeout=1.0) == 0
    assert gateway.replay_calls == [None]
    assert gateway.due_calls == [None]


@pytest.mark.asyncio
async def test_scheduler_outer_cancellation_reaps_real_inner_call_before_propagating() -> None:
    """outer cancellation 等待阻塞 replay inner 真结束后才传播。"""

    gateway = _RecordingSchedulerGateway()
    gateway.block_replay = True
    scheduler = _scheduler(gateway, ProcessIntakeGate())
    task = asyncio.create_task(scheduler.run())
    assert await asyncio.to_thread(gateway.replay_entered.wait, 2.0)

    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    gateway.replay_release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
