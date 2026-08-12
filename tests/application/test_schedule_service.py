"""ScheduleService 的 PG-clock、DST、due 与 materialization 单元测试。

测试只使用 pure DTO 与两个最小 recording fake：Store fake 保留九方法精确
surface，Job gateway fake 只暴露 availability 与 committed enqueue。测试不注入
本机 clock、SQLAlchemy session、callback、Redis 或 Host concrete type。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from dayu.host.scheduler import SchedulerGatewayProtocol
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
    ScheduleActivationRequest,
    ScheduleDefinition,
    ScheduleDueCursor,
    ScheduleDueEntry,
    ScheduleDuePage,
    ScheduleExecutionUnavailableError,
    ScheduleInputError,
    ScheduleInvariantError,
    ScheduleMarkEnqueuedAction,
    ScheduleMarkEnqueuedResult,
    ScheduleMaterializationAction,
    ScheduleMaterializationAdmission,
    ScheduleMaterializationDecision,
    ScheduleMaterializationResultAction,
    ScheduleMisfirePolicy,
    ScheduleObservation,
    ScheduleOccurrence,
    ScheduleOccurrenceState,
    ScheduleRegistrationRequest,
    ScheduleReplayCursor,
    ScheduleReplayPage,
    ScheduleReservationBatch,
    ScheduleReservationResult,
    ScheduleReserveAction,
    ScheduleSkipReason,
    ScheduleState,
    ScheduleStateTransitionAction,
    ScheduleStateTransitionResult,
    ScheduleVersionConflictError,
)
from dayu.services.schedule_service import (
    DURABLE_SCHEDULES_SERVICE_NAME,
    ScheduleJobGatewayProtocol,
    ScheduleService,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
"""稳定测试 PG clock。"""


def _scope(seed: int = 1) -> TenantScope:
    """构造一个 canonical tenant scope。

    Args:
        seed: tenant UUID 的末尾整数。

    Returns:
        测试 ``TenantScope``。

    Raises:
        无。
    """

    return Principal(
        tenant_id=TenantId(f"00000000-0000-0000-0000-{seed:012d}"),
        user_id=f"user-{seed}",
    ).to_scope()


def _descriptor(job_type: str = "test.schedule") -> JobHandlerDescriptor:
    """构造完整测试 descriptor。

    Args:
        job_type: descriptor job type。

    Returns:
        七字段 ``JobHandlerDescriptor``。

    Raises:
        无。
    """

    return JobHandlerDescriptor(
        job_type=job_type,
        payload_schema_name="test.schedule.payload",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=60,
    )


def _payload() -> CanonicalJobDocument:
    """构造 canonical schedule payload。

    Args:
        无。

    Returns:
        canonical document。

    Raises:
        无。
    """

    return build_canonical_document(
        {"kind": "schedule-test"},
        schema_name="test.schedule.payload",
        schema_version=1,
    )


def _registration(
    *,
    cron_expression: str = "* * * * *",
    timezone_name: str = "UTC",
) -> ScheduleRegistrationRequest:
    """构造 schedule registration request。

    Args:
        cron_expression: 五字段 cron。
        timezone_name: IANA timezone。

    Returns:
        disabled draft registration request。

    Raises:
        无。
    """

    return ScheduleRegistrationRequest(
        schedule_key="schedule-test",
        descriptor=_descriptor(),
        payload=_payload(),
        cron_expression=cron_expression,
        timezone_name=timezone_name,
        misfire_policy=ScheduleMisfirePolicy.COALESCE_ONE,
        misfire_grace_seconds=120,
        job_deadline_seconds=600,
    )


def _definition(
    *,
    schedule_id: UUID | None = None,
    scope: TenantScope | None = None,
    descriptor: JobHandlerDescriptor | None = None,
    state: ScheduleState = ScheduleState.ACTIVE,
    next_fire_at: datetime | None = NOW,
    version: int = 4,
    cron_expression: str = "* * * * *",
    timezone_name: str = "UTC",
    grace_seconds: int = 120,
    deadline_seconds: int = 600,
) -> ScheduleDefinition:
    """构造 active/disabled schedule definition。

    Args:
        schedule_id: 可空固定 schedule UUID。
        scope: 可空 tenant scope。
        descriptor: 可空 descriptor。
        state: schedule state。
        next_fire_at: 可空 persisted cursor。
        version: optimistic version。
        cron_expression: 五字段 cron。
        timezone_name: IANA timezone。
        grace_seconds: misfire grace 秒数。
        deadline_seconds: job deadline 秒数。

    Returns:
        合法 ``ScheduleDefinition``。

    Raises:
        无。
    """

    selected_scope = scope if scope is not None else _scope()
    return ScheduleDefinition(
        id=schedule_id if schedule_id is not None else uuid4(),
        tenant_id=selected_scope.tenant_id,
        schedule_key="schedule-test",
        descriptor=descriptor if descriptor is not None else _descriptor(),
        payload=_payload(),
        cron_expression=cron_expression,
        timezone_name=timezone_name,
        misfire_policy=ScheduleMisfirePolicy.COALESCE_ONE,
        misfire_grace_seconds=grace_seconds,
        job_deadline_seconds=deadline_seconds,
        state=state,
        next_fire_at=next_fire_at,
        version=version,
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=1),
    )


def _observation(
    definition: ScheduleDefinition,
    database_now: datetime = NOW,
) -> ScheduleObservation:
    """构造同事务 PG-clock observation。

    Args:
        definition: schedule definition。
        database_now: aware UTC PG clock。

    Returns:
        ``ScheduleObservation``。

    Raises:
        无。
    """

    return ScheduleObservation(definition=definition, database_now=database_now)


def _idempotency_key(definition: ScheduleDefinition, scheduled_for: datetime) -> str:
    """按 production 固定公式独立构造 expected idempotency key。

    Args:
        definition: schedule revision。
        scheduled_for: occurrence fire。

    Returns:
        逐字 expected key。

    Raises:
        无。
    """

    return f"schedule:{definition.id}:{definition.version}:{scheduled_for.isoformat(timespec='microseconds')}"


def _snapshot(
    definition: ScheduleDefinition,
    scheduled_for: datetime,
) -> CanonicalScheduleEnqueueSnapshot:
    """构造与 production 公式逐字段相同的 snapshot fixture。

    Args:
        definition: schedule revision。
        scheduled_for: occurrence fire。

    Returns:
        canonical enqueue snapshot。

    Raises:
        无。
    """

    key = _idempotency_key(definition, scheduled_for)
    deadline_at = scheduled_for + timedelta(seconds=definition.job_deadline_seconds)
    request = JobEnqueueRequest(
        descriptor=definition.descriptor,
        idempotency_key=key,
        payload=definition.payload,
        available_at=scheduled_for,
        deadline_at=deadline_at,
    )
    return CanonicalScheduleEnqueueSnapshot(
        descriptor=definition.descriptor,
        payload=definition.payload,
        idempotency_key=key,
        available_at=scheduled_for,
        deadline_at=deadline_at,
        request_fingerprint=job_enqueue_request_fingerprint(request),
    )


def _occurrence(
    definition: ScheduleDefinition,
    *,
    occurrence_id: UUID | None = None,
    state: ScheduleOccurrenceState = ScheduleOccurrenceState.PENDING,
    scheduled_for: datetime = NOW,
    job_id: UUID | None = None,
    skip_reason: ScheduleSkipReason | None = None,
) -> ScheduleOccurrence:
    """构造一条合法 occurrence projection。

    Args:
        definition: parent schedule revision。
        occurrence_id: 可空固定 UUID。
        state: occurrence state。
        scheduled_for: fire 时间。
        job_id: 可空 bound job UUID。
        skip_reason: 可空 skip reason。

    Returns:
        合法 ``ScheduleOccurrence``。

    Raises:
        无。
    """

    keeps_snapshot = state is not ScheduleOccurrenceState.SKIPPED or (
        skip_reason is ScheduleSkipReason.SCHEDULE_DISABLED
    )
    return ScheduleOccurrence(
        id=occurrence_id if occurrence_id is not None else uuid4(),
        tenant_id=definition.tenant_id,
        schedule_id=definition.id,
        schedule_version=definition.version,
        scheduled_for=scheduled_for,
        state=state,
        snapshot=_snapshot(definition, scheduled_for) if keeps_snapshot else None,
        job_id=job_id,
        coalesced_count=(
            0
            if state is not ScheduleOccurrenceState.SKIPPED
            or skip_reason
            in (
                ScheduleSkipReason.MISFIRE_EXPIRED,
                ScheduleSkipReason.SCHEDULE_DISABLED,
            )
            else None
        ),
        skip_reason=skip_reason,
        created_at=NOW,
        updated_at=NOW,
    )


def _receipt(scope: TenantScope, job_id: UUID | None = None) -> JobEnqueueReceipt:
    """构造 ready enqueue receipt。

    Args:
        scope: tenant scope。
        job_id: 可空固定 job UUID。

    Returns:
        ``JobEnqueueReceipt``。

    Raises:
        无。
    """

    return JobEnqueueReceipt(
        tenant_id=scope.tenant_id,
        definition_id=uuid4(),
        job_id=job_id if job_id is not None else uuid4(),
        state=JobState.READY,
        idempotency_reused=False,
    )


def _due_page(
    *observations: ScheduleObservation,
) -> ScheduleDuePage:
    """把 observations 转成 exact cursor due page。

    Args:
        observations: active due observations。

    Returns:
        ``ScheduleDuePage``。

    Raises:
        无。
    """

    entries = tuple(
        ScheduleDueEntry(
            observation=observation,
            cursor_after=ScheduleDueCursor(
                next_fire_at=observation.definition.next_fire_at,
                schedule_id=observation.definition.id,
            ),
        )
        for observation in observations
        if observation.definition.next_fire_at is not None
    )
    return ScheduleDuePage(
        entries=entries,
        next_cursor=entries[-1].cursor_after if entries else None,
    )


def _applied_activation(
    request: ScheduleActivationRequest,
    previous: ScheduleDefinition,
    candidate: datetime,
    database_now: datetime,
) -> ScheduleStateTransitionResult:
    """构造合法 applied ACTIVE transition。

    Args:
        request: activation request。
        previous: disabled definition。
        candidate: strictly future candidate。
        database_now: conditional DML PG clock。

    Returns:
        applied transition result。

    Raises:
        无。
    """

    current = replace(
        previous,
        state=ScheduleState.ACTIVE,
        next_fire_at=candidate,
        version=previous.version + 1,
        updated_at=database_now,
    )
    return ScheduleStateTransitionResult(
        action=ScheduleStateTransitionAction.APPLIED,
        request=request,
        previous_definition=previous,
        observation=_observation(current, database_now),
        activation_next_fire_at=candidate,
    )


def _clock_stale(
    request: ScheduleActivationRequest,
    previous: ScheduleDefinition,
    candidate: datetime,
    database_now: datetime,
) -> ScheduleStateTransitionResult:
    """构造合法 clock-stale zero-mutation transition。

    Args:
        request: 原始 activation request。
        previous: disabled definition。
        candidate: 已不晚于 fresh PG clock 的 candidate。
        database_now: fresh PG clock。

    Returns:
        clock-stale transition result。

    Raises:
        无。
    """

    return ScheduleStateTransitionResult(
        action=ScheduleStateTransitionAction.CLOCK_STALE,
        request=request,
        previous_definition=previous,
        observation=_observation(previous, database_now),
        activation_next_fire_at=candidate,
    )


class _FakeScheduleStore:
    """九方法 exact surface 的 programmable recording fake。"""

    def __init__(self) -> None:
        """初始化安全默认值与 call logs。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.register_result: ScheduleDefinition | None = None
        self.get_result: ScheduleObservation | None = None
        self.occurrence_result: ScheduleOccurrence | None = None
        self.transition_results: list[ScheduleStateTransitionResult] = []
        self.due_page = ScheduleDuePage(entries=(), next_cursor=None)
        self.reservation_result = ScheduleReservationResult(
            action=ScheduleReserveAction.LOST_RACE,
            occurrences=(),
        )
        self.replay_page = ScheduleReplayPage(
            occurrences=(),
            next_pending_cursor=None,
        )
        self.begin_result: ScheduleMaterializationDecision | None = None
        self.mark_result: ScheduleMarkEnqueuedResult | None = None
        self.register_calls: list[tuple[TenantScope, ScheduleRegistrationRequest]] = []
        self.get_calls: list[tuple[TenantScope, UUID]] = []
        self.occurrence_calls: list[tuple[TenantScope, UUID]] = []
        self.state_calls: list[tuple[TenantScope, ScheduleActivationRequest, datetime | None]] = []
        self.due_calls: list[tuple[TenantScope, ScheduleDueCursor | None, int]] = []
        self.reserve_calls: list[tuple[TenantScope, ScheduleReservationBatch]] = []
        self.replay_calls: list[tuple[TenantScope, ScheduleReplayCursor | None, int]] = []
        self.begin_calls: list[tuple[TenantScope, UUID, ScheduleMaterializationAdmission]] = []
        self.mark_calls: list[tuple[TenantScope, UUID, str, UUID]] = []

    def register(
        self,
        scope: TenantScope,
        request: ScheduleRegistrationRequest,
    ) -> ScheduleDefinition:
        """记录 register 并返回配置结果。

        Args:
            scope: tenant scope。
            request: registration request。

        Returns:
            配置的 definition。

        Raises:
            AssertionError: 测试未配置结果时抛出。
        """

        self.register_calls.append((scope, request))
        result = self.register_result
        if result is None:
            raise AssertionError("register_result 未配置")
        return result

    def get(
        self,
        scope: TenantScope,
        schedule_id: UUID,
    ) -> ScheduleObservation | None:
        """记录 schedule point read。

        Args:
            scope: tenant scope。
            schedule_id: schedule UUID。

        Returns:
            配置 observation 或 ``None``。

        Raises:
            无。
        """

        self.get_calls.append((scope, schedule_id))
        return self.get_result

    def get_occurrence(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
    ) -> ScheduleOccurrence | None:
        """记录 occurrence point read。

        Args:
            scope: tenant scope。
            occurrence_id: occurrence UUID。

        Returns:
            配置 occurrence 或 ``None``。

        Raises:
            无。
        """

        self.occurrence_calls.append((scope, occurrence_id))
        return self.occurrence_result

    def set_state(
        self,
        scope: TenantScope,
        request: ScheduleActivationRequest,
        *,
        activation_next_fire_at: datetime | None,
    ) -> ScheduleStateTransitionResult:
        """记录 state CAS 并依序返回结果。

        Args:
            scope: tenant scope。
            request: activation request。
            activation_next_fire_at: candidate 或 ``None``。

        Returns:
            队头 transition result。

        Raises:
            AssertionError: 测试未配置结果时抛出。
        """

        self.state_calls.append((scope, request, activation_next_fire_at))
        if not self.transition_results:
            raise AssertionError("transition_results 未配置")
        return self.transition_results.pop(0)

    def list_due(
        self,
        scope: TenantScope,
        cursor: ScheduleDueCursor | None,
        *,
        limit: int,
    ) -> ScheduleDuePage:
        """记录 due page read。

        Args:
            scope: tenant scope。
            cursor: due cursor。
            limit: page 上限。

        Returns:
            配置 due page。

        Raises:
            无。
        """

        self.due_calls.append((scope, cursor, limit))
        return self.due_page

    def reserve_occurrences(
        self,
        scope: TenantScope,
        batch: ScheduleReservationBatch,
    ) -> ScheduleReservationResult:
        """记录 reservation batch。

        Args:
            scope: tenant scope。
            batch: Service 计算的 batch。

        Returns:
            配置 reservation result。

        Raises:
            无。
        """

        self.reserve_calls.append((scope, batch))
        return self.reservation_result

    def list_replayable(
        self,
        scope: TenantScope,
        cursor: ScheduleReplayCursor | None,
        *,
        limit: int,
    ) -> ScheduleReplayPage:
        """记录 replay page read。

        Args:
            scope: tenant scope。
            cursor: pending replay cursor。
            limit: page 上限。

        Returns:
            配置 replay page。

        Raises:
            无。
        """

        self.replay_calls.append((scope, cursor, limit))
        return self.replay_page

    def begin_materialization(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
        *,
        admission: ScheduleMaterializationAdmission,
    ) -> ScheduleMaterializationDecision:
        """记录 begin admission 并返回配置 decision。

        Args:
            scope: tenant scope。
            occurrence_id: occurrence UUID。
            admission: closed admission。

        Returns:
            配置 materialization decision。

        Raises:
            AssertionError: 测试未配置结果时抛出。
        """

        self.begin_calls.append((scope, occurrence_id, admission))
        result = self.begin_result
        if result is None:
            raise AssertionError("begin_result 未配置")
        return result

    def mark_enqueued(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
        expected_snapshot_fingerprint: str,
        job_id: UUID,
    ) -> ScheduleMarkEnqueuedResult:
        """记录 mark 并返回配置结果。

        Args:
            scope: tenant scope。
            occurrence_id: occurrence UUID。
            expected_snapshot_fingerprint: snapshot fingerprint。
            job_id: committed job UUID。

        Returns:
            配置 mark result。

        Raises:
            AssertionError: 测试未配置结果时抛出。
        """

        self.mark_calls.append((scope, occurrence_id, expected_snapshot_fingerprint, job_id))
        result = self.mark_result
        if result is None:
            raise AssertionError("mark_result 未配置")
        return result


class _FakeScheduleJobGateway:
    """availability + committed enqueue 的最小 recording fake。"""

    def __init__(self) -> None:
        """初始化 availability 与 enqueue 状态。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.default_available = True
        self.availability: dict[str, bool] = {}
        self.enqueue_result: JobEnqueueReceipt | None = None
        self.availability_calls: list[JobHandlerDescriptor] = []
        self.enqueue_calls: list[tuple[TenantScope, ScheduleMaterializationDecision]] = []

    def is_execution_available(self, descriptor: JobHandlerDescriptor) -> bool:
        """返回按 job type 配置的 process-local availability。

        Args:
            descriptor: 完整 descriptor。

        Returns:
            配置 availability，缺省使用 ``default_available``。

        Raises:
            无。
        """

        self.availability_calls.append(descriptor)
        return self.availability.get(descriptor.job_type, self.default_available)

    def enqueue_committed_schedule_occurrence(
        self,
        scope: TenantScope,
        decision: ScheduleMaterializationDecision,
    ) -> JobEnqueueReceipt:
        """记录 committed enqueue 并返回配置 receipt。

        Args:
            scope: tenant scope。
            decision: persisted materializing decision。

        Returns:
            配置 enqueue receipt。

        Raises:
            AssertionError: 测试未配置 receipt 时抛出。
        """

        self.enqueue_calls.append((scope, decision))
        result = self.enqueue_result
        if result is None:
            raise AssertionError("enqueue_result 未配置")
        return result


def _service(
    store: _FakeScheduleStore,
    gateway: _FakeScheduleJobGateway,
    *,
    lookback_seconds: int = 600,
    scan_limit: int = 100,
) -> ScheduleService:
    """构造注入最小 fakes 的 ScheduleService。

    Args:
        store: recording Store。
        gateway: recording Job gateway。
        lookback_seconds: bounded lookback。
        scan_limit: raw candidate limit。

    Returns:
        ``ScheduleService``。

    Raises:
        无。
    """

    return ScheduleService(
        schedule_store=store,
        job_gateway=gateway,
        schedule_max_lookback_seconds=lookback_seconds,
        schedule_candidate_scan_limit=scan_limit,
    )


@pytest.mark.unit
def test_schedule_service_registers_valid_draft_and_rejects_croniter_invalid_before_store() -> None:
    """register 允许 unavailable draft，但 semantic invalid cron 零 Store 调用。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    store = _FakeScheduleStore()
    gateway = _FakeScheduleJobGateway()
    draft = _definition(state=ScheduleState.DISABLED, next_fire_at=None)
    store.register_result = draft
    service = _service(store, gateway)
    request = _registration()
    assert service.platform_service_name == DURABLE_SCHEDULES_SERVICE_NAME
    assert service.register(scope, request) is draft
    assert store.register_calls == [(scope, request)]
    assert gateway.availability_calls == []

    with pytest.raises(ScheduleInputError, match="cron_expression_invalid"):
        service.register(scope, _registration(cron_expression="61 * * * *"))
    assert store.register_calls == [(scope, request)]


@pytest.mark.unit
def test_croniter_valid_but_candidate_empty_is_rejected_before_store() -> None:
    """固定 seed probe 在 Store 前拒绝 croniter-valid 无候选表达式。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    store = _FakeScheduleStore()
    service = _service(store, _FakeScheduleJobGateway())
    with pytest.raises(ScheduleInputError) as error:
        service.register(
            scope,
            _registration(cron_expression="0 0 31 2 *"),
        )
    assert str(error.value) == "schedule_cron_has_no_candidate"
    assert store.register_calls == []


@pytest.mark.unit
def test_activate_uses_pg_observation_and_persists_first_strictly_future_cursor() -> None:
    """activation 只以 PG clock 计算并提交首个严格 future cursor。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    database_now = datetime(2026, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
    previous = _definition(
        state=ScheduleState.DISABLED,
        next_fire_at=None,
        cron_expression="0 9 * * *",
        timezone_name="Asia/Shanghai",
    )
    request = ScheduleActivationRequest(
        schedule_id=previous.id,
        expected_version=previous.version,
        target_state=ScheduleState.ACTIVE,
    )
    candidate = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
    store = _FakeScheduleStore()
    store.get_result = _observation(previous, database_now)
    store.transition_results = [_applied_activation(request, previous, candidate, database_now)]
    gateway = _FakeScheduleJobGateway()
    result = _service(store, gateway).set_state(scope, request)
    assert result.action is ScheduleStateTransitionAction.APPLIED
    assert store.state_calls == [(scope, request, candidate)]
    assert gateway.availability_calls == [previous.descriptor]


@pytest.mark.unit
def test_activate_clock_stale_uses_three_total_cas_attempts_including_first_without_version_rebase() -> None:
    """三次 stale 使用 fresh PG clock 重算且始终保留原 expected version。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    previous = _definition(
        state=ScheduleState.DISABLED,
        next_fire_at=None,
        cron_expression="* * * * *",
    )
    request = ScheduleActivationRequest(
        schedule_id=previous.id,
        expected_version=previous.version,
        target_state=ScheduleState.ACTIVE,
    )
    initial_now = datetime(2026, 1, 1, 0, 0, 59, 900000, tzinfo=timezone.utc)
    candidates = [
        datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc),
    ]
    stale_clocks = candidates
    store = _FakeScheduleStore()
    store.get_result = _observation(previous, initial_now)
    store.transition_results = [
        _clock_stale(request, previous, candidate, stale_clock)
        for candidate, stale_clock in zip(candidates, stale_clocks, strict=True)
    ]
    gateway = _FakeScheduleJobGateway()
    result = _service(store, gateway).set_state(scope, request)
    assert result.action is ScheduleStateTransitionAction.CLOCK_STALE
    assert [call[1] for call in store.state_calls] == [request, request, request]
    assert [call[2] for call in store.state_calls] == candidates
    assert gateway.availability_calls == [previous.descriptor]


@pytest.mark.unit
def test_activation_cron_iteration_exhaustion_reads_only_and_never_calls_set_state() -> None:
    """持久化无候选 cron 的 activation 只读 observation 后 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    previous = _definition(
        state=ScheduleState.DISABLED,
        next_fire_at=None,
        cron_expression="0 0 31 2 *",
    )
    request = ScheduleActivationRequest(
        schedule_id=previous.id,
        expected_version=previous.version,
        target_state=ScheduleState.ACTIVE,
    )
    store = _FakeScheduleStore()
    store.get_result = _observation(previous)
    with pytest.raises(ScheduleInvariantError) as error:
        _service(store, _FakeScheduleJobGateway()).set_state(scope, request)
    assert str(error.value) == "schedule_cron_iteration_exhausted"
    assert store.get_calls == [(scope, previous.id)]
    assert store.state_calls == []


@pytest.mark.unit
def test_activation_unavailable_keeps_disabled_row_byte_exact_and_never_calls_store_transition() -> None:
    """disabled->active unavailable 在 Store transition 前 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    previous = _definition(state=ScheduleState.DISABLED, next_fire_at=None)
    request = ScheduleActivationRequest(
        schedule_id=previous.id,
        expected_version=previous.version,
        target_state=ScheduleState.ACTIVE,
    )
    store = _FakeScheduleStore()
    store.get_result = _observation(previous)
    gateway = _FakeScheduleJobGateway()
    gateway.default_available = False
    with pytest.raises(
        ScheduleExecutionUnavailableError,
        match="schedule_execution_unavailable",
    ):
        _service(store, gateway).set_state(scope, request)
    assert store.state_calls == []
    assert store.get_result == _observation(previous)


@pytest.mark.unit
def test_active_exact_version_activation_is_unchanged_without_availability_gate() -> None:
    """已 active request 直接由 Store 返回 unchanged，不查 local capability。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    active = _definition(next_fire_at=NOW + timedelta(minutes=1))
    request = ScheduleActivationRequest(
        schedule_id=active.id,
        expected_version=active.version,
        target_state=ScheduleState.ACTIVE,
    )
    unchanged = ScheduleStateTransitionResult(
        action=ScheduleStateTransitionAction.UNCHANGED,
        request=request,
        previous_definition=active,
        observation=_observation(active),
        activation_next_fire_at=None,
    )
    store = _FakeScheduleStore()
    store.get_result = _observation(active)
    store.transition_results = [unchanged]
    gateway = _FakeScheduleJobGateway()
    assert _service(store, gateway).set_state(scope, request) is unchanged
    assert store.state_calls == [(scope, request, None)]
    assert gateway.availability_calls == []


@pytest.mark.unit
def test_activation_missing_or_stale_version_fails_before_availability_and_cas() -> None:
    """missing/stale observation 统一返回 fixed version conflict。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    definition = _definition(state=ScheduleState.DISABLED, next_fire_at=None)
    request = ScheduleActivationRequest(
        schedule_id=definition.id,
        expected_version=definition.version + 1,
        target_state=ScheduleState.ACTIVE,
    )
    gateway = _FakeScheduleJobGateway()
    for observation in (None, _observation(definition)):
        store = _FakeScheduleStore()
        store.get_result = observation
        with pytest.raises(
            ScheduleVersionConflictError,
            match="schedule_version_conflict",
        ):
            _service(store, gateway).set_state(scope, request)
        assert store.state_calls == []
    assert gateway.availability_calls == []


@pytest.mark.unit
def test_persisted_cron_iteration_exhaustion_stops_without_schedule_mutation() -> None:
    """持久化无候选表达式产生固定 invariant 且所有 mutation gateway 为零。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    previous = _definition(
        state=ScheduleState.DISABLED,
        next_fire_at=None,
        cron_expression="0 0 31 2 *",
    )
    request = ScheduleActivationRequest(
        schedule_id=previous.id,
        expected_version=previous.version,
        target_state=ScheduleState.ACTIVE,
    )
    store = _FakeScheduleStore()
    store.get_result = _observation(previous)
    with pytest.raises(ScheduleInvariantError) as error:
        _service(store, _FakeScheduleJobGateway()).set_state(scope, request)
    assert str(error.value) == "schedule_cron_iteration_exhausted"
    assert store.register_calls == []
    assert store.state_calls == []
    assert store.reserve_calls == []
    assert store.begin_calls == []
    assert store.mark_calls == []


@pytest.mark.unit
def test_due_cron_iteration_exhaustion_reads_only_and_never_calls_reserve_occurrences() -> None:
    """due 路径只读取 persisted page，cron 耗尽前不提交 reservation。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    definition = _definition(
        next_fire_at=NOW,
        cron_expression="0 0 31 2 *",
    )
    store = _FakeScheduleStore()
    store.due_page = _due_page(_observation(definition))
    with pytest.raises(ScheduleInvariantError) as error:
        _service(store, _FakeScheduleJobGateway()).reserve_due_occurrences(
            scope,
            None,
            limit=1,
        )
    assert str(error.value) == "schedule_cron_iteration_exhausted"
    assert store.due_calls == [(scope, None, 1)]
    assert store.reserve_calls == []


@pytest.mark.unit
def test_scheduler_dst_nonexistent_time_policy_is_exact() -> None:
    """New York spring-gap 02:30 被跳过而不是平移到 03:30。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    database_now = datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc)
    previous = _definition(
        state=ScheduleState.DISABLED,
        next_fire_at=None,
        cron_expression="30 2 * * *",
        timezone_name="America/New_York",
    )
    request = ScheduleActivationRequest(
        schedule_id=previous.id,
        expected_version=previous.version,
        target_state=ScheduleState.ACTIVE,
    )
    expected = datetime(2026, 3, 9, 6, 30, tzinfo=timezone.utc)
    store = _FakeScheduleStore()
    store.get_result = _observation(previous, database_now)
    store.transition_results = [_applied_activation(request, previous, expected, database_now)]
    _service(store, _FakeScheduleJobGateway()).set_state(scope, request)
    assert store.state_calls[0][2] == expected


@pytest.mark.unit
def test_scheduler_dst_ambiguous_fold_enqueues_exactly_once() -> None:
    """New York fall-fold 01:30 固定 fold=0 的唯一 UTC candidate。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    database_now = datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc)
    previous = _definition(
        state=ScheduleState.DISABLED,
        next_fire_at=None,
        cron_expression="30 1 * * *",
        timezone_name="America/New_York",
    )
    request = ScheduleActivationRequest(
        schedule_id=previous.id,
        expected_version=previous.version,
        target_state=ScheduleState.ACTIVE,
    )
    fold_zero = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
    store = _FakeScheduleStore()
    store.get_result = _observation(previous, database_now)
    store.transition_results = [_applied_activation(request, previous, fold_zero, database_now)]
    _service(store, _FakeScheduleJobGateway()).set_state(scope, request)
    assert [call[2] for call in store.state_calls] == [fold_zero]


def _reserved_batch(
    definition: ScheduleDefinition,
    database_now: datetime,
    *,
    lookback_seconds: int = 600,
    scan_limit: int = 100,
) -> ScheduleReservationBatch:
    """通过 public due gateway 取得一次计算后的 batch。

    Args:
        definition: active due definition。
        database_now: due page PG clock。
        lookback_seconds: bounded lookback。
        scan_limit: raw candidate limit。

    Returns:
        fake Store 捕获的唯一 reservation batch。

    Raises:
        AssertionError: Service 未恰好 reserve 一次时抛出。
    """

    store = _FakeScheduleStore()
    store.due_page = _due_page(_observation(definition, database_now))
    gateway = _FakeScheduleJobGateway()
    result = _service(
        store,
        gateway,
        lookback_seconds=lookback_seconds,
        scan_limit=scan_limit,
    ).reserve_due_occurrences(_scope(), None, limit=1)
    assert result.inspected_count == 1
    assert len(store.reserve_calls) == 1
    return store.reserve_calls[0][1]


@pytest.mark.unit
def test_scheduler_coalesces_misfire_with_bounded_lookback() -> None:
    """grace 内多个 due fire coalesce 为最新一条 pending snapshot。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    database_now = NOW
    definition = _definition(
        next_fire_at=database_now - timedelta(minutes=2),
        grace_seconds=180,
    )
    batch = _reserved_batch(definition, database_now)
    assert batch.resulting_state is ScheduleState.ACTIVE
    assert batch.resulting_next_fire_at == database_now + timedelta(minutes=1)
    assert len(batch.reservations) == 1
    pending = batch.reservations[0]
    assert pending.state is ScheduleOccurrenceState.PENDING
    assert pending.scheduled_for == database_now
    assert pending.coalesced_count == 2
    assert pending.snapshot is not None
    assert pending.snapshot.idempotency_key == _idempotency_key(
        definition,
        database_now,
    )
    assert pending.snapshot.available_at == database_now
    assert pending.snapshot.deadline_at == database_now + timedelta(seconds=600)


@pytest.mark.unit
def test_scheduler_skips_misfire_past_grace_before_lookback_and_advances_cursor() -> None:
    """lookback 内 grace 外 fire 收敛为 exact expired group。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition(
        next_fire_at=NOW - timedelta(minutes=5),
        grace_seconds=120,
    )
    batch = _reserved_batch(definition, NOW)
    expired, eligible = batch.reservations
    assert expired.skip_reason is ScheduleSkipReason.MISFIRE_EXPIRED
    assert expired.scheduled_for == NOW - timedelta(minutes=3)
    assert expired.coalesced_count == 2
    assert eligible.state is ScheduleOccurrenceState.PENDING
    assert eligible.scheduled_for == NOW
    assert eligible.coalesced_count == 2
    assert batch.resulting_next_fire_at == NOW + timedelta(minutes=1)


@pytest.mark.unit
def test_scheduler_misfire_boundary_is_inclusive_and_dst_cursor_is_monotonic() -> None:
    """``now-candidate == grace`` 属于 eligible，future cursor 严格增加。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition(
        next_fire_at=NOW - timedelta(minutes=2),
        grace_seconds=120,
    )
    batch = _reserved_batch(definition, NOW)
    assert [item.skip_reason for item in batch.reservations] == [None]
    assert batch.reservations[0].coalesced_count == 2
    assert batch.resulting_next_fire_at > NOW


@pytest.mark.unit
def test_scheduler_lookback_relocation_includes_fire_exactly_equal_to_boundary() -> None:
    """L-1 minute seed 保留 ``C == L``，不被 lookback audit 吞掉。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition(
        next_fire_at=NOW - timedelta(minutes=11),
        grace_seconds=600,
        deadline_seconds=1200,
    )
    batch = _reserved_batch(definition, NOW, lookback_seconds=600)
    lookback, pending = batch.reservations
    assert lookback.skip_reason is ScheduleSkipReason.LOOKBACK_EXCEEDED
    assert lookback.scheduled_for == NOW - timedelta(minutes=11)
    assert lookback.coalesced_count is None
    assert pending.state is ScheduleOccurrenceState.PENDING
    assert pending.scheduled_for == NOW
    assert pending.coalesced_count == 10


@pytest.mark.unit
def test_candidate_scan_limit_counts_raw_nonexistent_dst_candidates_before_classification() -> None:
    """spring-gap raw candidate 消耗唯一 slot并触发 closed scan-limit disable。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    persisted = datetime(2026, 3, 7, 7, 30, tzinfo=timezone.utc)
    database_now = datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc)
    definition = _definition(
        next_fire_at=persisted,
        cron_expression="30 2 * * *",
        timezone_name="America/New_York",
        grace_seconds=86400,
        deadline_seconds=90000,
    )
    batch = _reserved_batch(
        definition,
        database_now,
        lookback_seconds=172800,
        scan_limit=1,
    )
    assert batch.resulting_state is ScheduleState.DISABLED
    assert batch.resulting_next_fire_at == persisted
    assert len(batch.reservations) == 1
    audit = batch.reservations[0]
    assert audit.skip_reason is ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED
    assert audit.scheduled_for == persisted
    assert audit.coalesced_count is None


@pytest.mark.unit
def test_scan_limit_before_distinct_relocation_candidate_coalesces_colliding_audits_to_one_scan_limit_row() -> None:
    """relocation 未取得 distinct candidate 时由 scan-limit audit 支配同键。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    persisted = datetime(2026, 3, 7, 7, 30, tzinfo=timezone.utc)
    database_now = datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc)
    definition = _definition(
        next_fire_at=persisted,
        cron_expression="30 2 * * *",
        timezone_name="America/New_York",
        grace_seconds=3600,
        deadline_seconds=7200,
    )
    batch = _reserved_batch(
        definition,
        database_now,
        lookback_seconds=3600,
        scan_limit=1,
    )
    assert batch.resulting_state is ScheduleState.DISABLED
    assert batch.resulting_next_fire_at == persisted
    assert len(batch.reservations) == 1
    assert batch.reservations[0].scheduled_for == persisted
    assert batch.reservations[0].skip_reason is ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED


@pytest.mark.unit
def test_scan_limit_after_distinct_relocation_candidate_persists_two_distinct_audits() -> None:
    """relocation 取得 distinct candidate 后保留两个不同自然键的审计。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    persisted = NOW - timedelta(minutes=11)
    lower_bound = NOW - timedelta(minutes=10)
    definition = _definition(
        next_fire_at=persisted,
        cron_expression="* * * * *",
        grace_seconds=600,
        deadline_seconds=1200,
    )
    batch = _reserved_batch(
        definition,
        NOW,
        lookback_seconds=600,
        scan_limit=2,
    )
    assert batch.resulting_state is ScheduleState.DISABLED
    assert batch.resulting_next_fire_at == persisted
    assert [item.scheduled_for for item in batch.reservations] == [
        persisted,
        lower_bound,
    ]
    assert [item.skip_reason for item in batch.reservations] == [
        ScheduleSkipReason.LOOKBACK_EXCEEDED,
        ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED,
    ]


@pytest.mark.unit
def test_scheduler_candidate_scan_limit_disables_with_one_closed_audit() -> None:
    """scan limit 丢弃已扫描 provisional eligible group，只提交唯一 audit。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition(
        next_fire_at=NOW,
        cron_expression="* * * * *",
        grace_seconds=60,
    )
    batch = _reserved_batch(definition, NOW, scan_limit=0 + 1)
    assert batch.resulting_state is ScheduleState.ACTIVE
    assert batch.resulting_next_fire_at == NOW + timedelta(minutes=1)
    assert batch.reservations[0].state is ScheduleOccurrenceState.PENDING

    gap_definition = _definition(
        next_fire_at=datetime(2026, 3, 7, 7, 30, tzinfo=timezone.utc),
        cron_expression="30 2 * * *",
        timezone_name="America/New_York",
        grace_seconds=86400,
        deadline_seconds=90000,
    )
    limited = _reserved_batch(
        gap_definition,
        datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc),
        lookback_seconds=172800,
        scan_limit=1,
    )
    assert [item.state for item in limited.reservations] == [ScheduleOccurrenceState.SKIPPED]


@pytest.mark.unit
def test_due_cursor_rotates_past_unavailable_prefix_at_least_page_limit_to_later_available_schedule() -> None:
    """due scan 跳过 unavailable 前缀并只 reserve 首个 available entry。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    first = _definition(descriptor=_descriptor("unavailable-1"))
    second = _definition(descriptor=_descriptor("unavailable-2"))
    third = _definition(descriptor=_descriptor("available"))
    store = _FakeScheduleStore()
    store.due_page = _due_page(
        _observation(first),
        _observation(second),
        _observation(third),
    )
    gateway = _FakeScheduleJobGateway()
    gateway.availability = {
        "unavailable-1": False,
        "unavailable-2": False,
        "available": True,
    }
    result = _service(store, gateway).reserve_due_occurrences(
        scope,
        None,
        limit=3,
    )
    assert result.inspected_count == 3
    assert result.next_due_cursor == store.due_page.entries[2].cursor_after
    assert result.reservation is store.reservation_result
    assert len(store.reserve_calls) == 1
    assert store.reserve_calls[0][1].schedule_id == third.id


@pytest.mark.unit
def test_due_scan_empty_or_all_unavailable_is_bounded_and_zero_mutation() -> None:
    """空页与全 unavailable 页返回 typed cursor/count 且不 reserve。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    store = _FakeScheduleStore()
    gateway = _FakeScheduleJobGateway()
    service = _service(store, gateway)
    empty = service.reserve_due_occurrences(scope, None, limit=2)
    assert empty.reservation is None
    assert empty.next_due_cursor is None
    assert empty.inspected_count == 0

    first = _definition(descriptor=_descriptor("unavailable-1"))
    second = _definition(descriptor=_descriptor("unavailable-2"))
    store.due_page = _due_page(_observation(first), _observation(second))
    gateway.default_available = False
    unavailable = service.reserve_due_occurrences(scope, None, limit=2)
    assert unavailable.reservation is None
    assert unavailable.inspected_count == 2
    assert unavailable.next_due_cursor == store.due_page.entries[-1].cursor_after
    assert store.reserve_calls == []


@pytest.mark.unit
def test_list_replayable_occurrences_preserves_typed_cursor_and_keyword_limit() -> None:
    """replay gateway 逐字传递 typed cursor 与 keyword-only limit。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    cursor = ScheduleReplayCursor(scheduled_for=NOW, occurrence_id=uuid4())
    store = _FakeScheduleStore()
    store.replay_page = ScheduleReplayPage(
        occurrences=(),
        next_pending_cursor=cursor,
    )
    service = _service(store, _FakeScheduleJobGateway())
    assert service.list_replayable_occurrences(scope, cursor, limit=7) is store.replay_page
    assert store.replay_calls == [(scope, cursor, 7)]


def _configure_materialization(
    observed: ScheduleOccurrence,
    decision: ScheduleMaterializationDecision,
    *,
    mark_action: ScheduleMarkEnqueuedAction = ScheduleMarkEnqueuedAction.MARKED,
) -> tuple[
    ScheduleService,
    _FakeScheduleStore,
    _FakeScheduleJobGateway,
    JobEnqueueReceipt,
]:
    """构造一个可执行 materialization 的 fake harness。

    Args:
        observed: point-read occurrence。
        decision: begin 返回 decision。
        mark_action: enqueue 路径的 mark action。

    Returns:
        ``(service, store, gateway, receipt)``。

    Raises:
        无。
    """

    scope = _scope()
    store = _FakeScheduleStore()
    store.occurrence_result = observed
    store.begin_result = decision
    gateway = _FakeScheduleJobGateway()
    receipt = _receipt(scope)
    gateway.enqueue_result = receipt
    if decision.action is ScheduleMaterializationAction.ENQUEUE:
        enqueued = replace(
            decision.occurrence,
            state=ScheduleOccurrenceState.ENQUEUED,
            job_id=receipt.job_id,
            updated_at=NOW + timedelta(seconds=1),
        )
        store.mark_result = ScheduleMarkEnqueuedResult(
            action=mark_action,
            occurrence=enqueued,
        )
    return _service(store, gateway), store, gateway, receipt


@pytest.mark.unit
def test_schedule_activation_and_materialization_reject_unregistered_descriptor_without_job() -> None:
    """本进程缺 handler 时 activation 与 PENDING 均不会创建 job。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    scope = _scope()
    disabled = _definition(state=ScheduleState.DISABLED, next_fire_at=None)
    activation = ScheduleActivationRequest(
        schedule_id=disabled.id,
        expected_version=disabled.version,
        target_state=ScheduleState.ACTIVE,
    )
    activation_store = _FakeScheduleStore()
    activation_store.get_result = _observation(disabled)
    unavailable_gateway = _FakeScheduleJobGateway()
    unavailable_gateway.default_available = False
    with pytest.raises(
        ScheduleExecutionUnavailableError,
        match="schedule_execution_unavailable",
    ):
        _service(activation_store, unavailable_gateway).set_state(scope, activation)
    assert activation_store.state_calls == []
    assert unavailable_gateway.enqueue_calls == []

    pending = _occurrence(_definition())
    unavailable = ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.UNAVAILABLE,
        occurrence=pending,
    )
    service, materialization_store, materialization_gateway, _ = (
        _configure_materialization(pending, unavailable)
    )
    materialization_gateway.default_available = False
    result = service.materialize_occurrence(scope, pending.id)
    assert result.action is ScheduleMaterializationResultAction.UNAVAILABLE
    assert materialization_store.mark_calls == []
    assert materialization_gateway.enqueue_calls == []


@pytest.mark.unit
def test_pending_unavailable_admission_returns_no_work_without_schedule_or_occurrence_mutation() -> None:
    """PENDING unavailable 返回原 PENDING，零 committed enqueue/mark。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition()
    pending = _occurrence(definition)
    decision = ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.UNAVAILABLE,
        occurrence=pending,
    )
    service, store, gateway, _ = _configure_materialization(pending, decision)
    gateway.default_available = False
    result = service.materialize_occurrence(_scope(), pending.id)
    assert result.action is ScheduleMaterializationResultAction.UNAVAILABLE
    assert result.occurrence is pending
    assert result.enqueue_receipt is None
    assert store.begin_calls == [(_scope(), pending.id, ScheduleMaterializationAdmission.PENDING_UNAVAILABLE)]
    assert gateway.enqueue_calls == []
    assert store.mark_calls == []


@pytest.mark.unit
def test_stale_unavailable_admission_losing_to_begin_keeps_materializing_commitment() -> None:
    """stale negative proof 不得撤销并发赢家的 MATERIALIZING commitment。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition()
    pending = _occurrence(definition)
    materializing = replace(
        pending,
        state=ScheduleOccurrenceState.MATERIALIZING,
    )
    decision = ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.ENQUEUE,
        occurrence=materializing,
    )
    service, store, gateway, receipt = _configure_materialization(pending, decision)
    gateway.default_available = False
    result = service.materialize_occurrence(_scope(), pending.id)
    assert result.action is ScheduleMaterializationResultAction.ENQUEUED
    assert result.enqueue_receipt is receipt
    assert store.begin_calls[0][2] is ScheduleMaterializationAdmission.PENDING_UNAVAILABLE
    assert gateway.enqueue_calls == [(_scope(), decision)]
    assert len(store.mark_calls) == 1


@pytest.mark.unit
def test_materializing_replay_does_not_call_execution_availability_gateway() -> None:
    """初始 MATERIALIZING 使用 committed replay 且 availability 调用数为零。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition()
    materializing = _occurrence(
        definition,
        state=ScheduleOccurrenceState.MATERIALIZING,
    )
    decision = ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.ENQUEUE,
        occurrence=materializing,
    )
    service, store, gateway, _ = _configure_materialization(
        materializing,
        decision,
    )
    service.materialize_occurrence(_scope(), materializing.id)
    assert gateway.availability_calls == []
    assert store.begin_calls[0][2] is ScheduleMaterializationAdmission.COMMITTED_REPLAY


@pytest.mark.unit
def test_materializing_replay_uses_committed_enqueue_entry_and_never_ordinary_enqueue() -> None:
    """MATERIALIZING 只把 typed decision 送进 committed gateway 后 mark。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition()
    materializing = _occurrence(
        definition,
        state=ScheduleOccurrenceState.MATERIALIZING,
    )
    decision = ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.ENQUEUE,
        occurrence=materializing,
    )
    service, store, gateway, receipt = _configure_materialization(
        materializing,
        decision,
    )
    result = service.materialize_occurrence(_scope(), materializing.id)
    assert gateway.enqueue_calls == [(_scope(), decision)]
    snapshot = materializing.snapshot
    assert snapshot is not None
    assert store.mark_calls == [(_scope(), materializing.id, snapshot.request_fingerprint, receipt.job_id)]
    assert result.action is ScheduleMaterializationResultAction.ENQUEUED


@pytest.mark.unit
def test_materialization_replay_builds_byte_identical_enqueue_request() -> None:
    """crash replay 透传同一 frozen snapshot、fingerprint 与 natural key。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition(version=11)
    scheduled_for = NOW - timedelta(minutes=1)
    materializing = _occurrence(
        definition,
        state=ScheduleOccurrenceState.MATERIALIZING,
        scheduled_for=scheduled_for,
    )
    decision = ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.ENQUEUE,
        occurrence=materializing,
    )
    service, store, gateway, receipt = _configure_materialization(
        materializing,
        decision,
    )
    service.materialize_occurrence(_scope(), materializing.id)
    captured = gateway.enqueue_calls[0][1].occurrence.snapshot
    assert captured is materializing.snapshot
    assert captured is not None
    assert captured.idempotency_key == (
        f"schedule:{definition.id}:11:{scheduled_for.isoformat(timespec='microseconds')}"
    )
    assert store.mark_calls[0][2] == captured.request_fingerprint
    assert store.mark_calls[0][3] == receipt.job_id


@pytest.mark.unit
def test_materialize_occurrence_losing_terminal_race_returns_already_enqueued_without_fabricated_receipt() -> None:
    """begin terminal 输家返回 persisted ENQUEUED 且零 enqueue/mark/receipt。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition()
    pending = _occurrence(definition)
    enqueued = replace(
        pending,
        state=ScheduleOccurrenceState.ENQUEUED,
        job_id=uuid4(),
    )
    decision = ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.ALREADY_ENQUEUED,
        occurrence=enqueued,
    )
    service, store, gateway, _ = _configure_materialization(pending, decision)
    result = service.materialize_occurrence(_scope(), pending.id)
    assert result.action is ScheduleMaterializationResultAction.ALREADY_ENQUEUED
    assert result.enqueue_receipt is None
    assert result.occurrence is enqueued
    assert gateway.enqueue_calls == []
    assert store.mark_calls == []


@pytest.mark.unit
def test_skipped_occurrence_returns_closed_no_work_without_availability_or_enqueue() -> None:
    """SKIPPED point-read 走 committed replay 并返回 typed skipped。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition()
    skipped = _occurrence(
        definition,
        state=ScheduleOccurrenceState.SKIPPED,
        skip_reason=ScheduleSkipReason.MISFIRE_EXPIRED,
    )
    decision = ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.SKIPPED,
        occurrence=skipped,
    )
    service, store, gateway, _ = _configure_materialization(skipped, decision)
    result = service.materialize_occurrence(_scope(), skipped.id)
    assert result.action is ScheduleMaterializationResultAction.SKIPPED
    assert gateway.availability_calls == []
    assert gateway.enqueue_calls == []
    assert store.mark_calls == []


@pytest.mark.unit
def test_mark_enqueued_skipped_conflict_is_closed_and_stops_scheduler() -> None:
    """job 已提交后 mark 遇 SKIPPED 必须抛 fixed runtime invariant。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    definition = _definition()
    materializing = _occurrence(
        definition,
        state=ScheduleOccurrenceState.MATERIALIZING,
    )
    decision = ScheduleMaterializationDecision(
        action=ScheduleMaterializationAction.ENQUEUE,
        occurrence=materializing,
    )
    service, store, _, _ = _configure_materialization(materializing, decision)
    skipped = replace(
        materializing,
        state=ScheduleOccurrenceState.SKIPPED,
        snapshot=None,
        coalesced_count=None,
        skip_reason=ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED,
    )
    store.mark_result = ScheduleMarkEnqueuedResult(
        action=ScheduleMarkEnqueuedAction.SKIPPED_CONFLICT,
        occurrence=skipped,
    )
    with pytest.raises(
        ScheduleInvariantError,
        match="schedule_mark_skipped_conflict",
    ):
        service.materialize_occurrence(_scope(), materializing.id)


@pytest.mark.unit
def test_materialize_missing_occurrence_uses_fixed_safe_invariant_code() -> None:
    """tenant-scoped point read missing 时抛 fixed safe invariant。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    store = _FakeScheduleStore()
    gateway = _FakeScheduleJobGateway()
    with pytest.raises(
        ScheduleInvariantError,
        match="schedule_occurrence_missing",
    ):
        _service(store, gateway).materialize_occurrence(_scope(), uuid4())
    assert store.begin_calls == []
    assert gateway.availability_calls == []


@pytest.mark.unit
def test_schedule_service_structurally_satisfies_scheduler_gateway_without_importing_host() -> None:
    """Service 满足 Host-local port，且 production 模块不 import Host。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    store = _FakeScheduleStore()
    gateway = _FakeScheduleJobGateway()
    service = _service(store, gateway)
    scheduler_gateway: SchedulerGatewayProtocol = service
    import dayu.services.schedule_service as service_module

    assert service_module.__file__ is not None
    source = Path(service_module.__file__).read_text(encoding="utf-8")
    assert isinstance(gateway, ScheduleJobGatewayProtocol)
    assert isinstance(scheduler_gateway, SchedulerGatewayProtocol)
    assert "from dayu.host" not in source
    assert "import dayu.host" not in source
