"""schedule 纯领域模型测试（Slice 2.2）。

本文件覆盖 ``dayu.investment.domain.schedules`` 的三类契约：

1. pinned croniter naive-local empirical gate：固定 ``America/New_York``
   spring-gap 02:30、fall-fold 01:30 与 ``Asia/Shanghai`` 无 DST 样本，
   锁定 croniter 只接收/返回 naive local datetime、``get_next`` 严格
   大于 seed、ZoneInfo round-trip 是唯一 DST classifier；
2. cron/timezone 结构校验（5 字段 POSIX 形态、拒昵称/随机/hash 扩展、
   拒固定 UTC offset 字符串）；
3. 19 个公开 DTO 的字段/默认值/嵌套不变量与 closed 组合校验。

本测试文件遵守根 ``AGENTS.md`` 约束，不使用 ``object`` / ``Any`` /
``cast`` / ``type: ignore`` / ``getattr`` / ``hasattr``。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from croniter import croniter

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
    ScheduleDueScanResult,
    ScheduleInputError,
    ScheduleInvariantError,
    ScheduleMarkEnqueuedAction,
    ScheduleMarkEnqueuedResult,
    ScheduleMaterializationAction,
    ScheduleMaterializationAdmission,
    ScheduleMaterializationDecision,
    ScheduleMaterializationResult,
    ScheduleMaterializationResultAction,
    ScheduleMisfirePolicy,
    ScheduleObservation,
    ScheduleOccurrence,
    ScheduleOccurrenceReservation,
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
    validate_cron_expression,
    validate_timezone_name,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
"""测试固定时刻（aware UTC）。"""

_NY = "America/New_York"
_SH = "Asia/Shanghai"


def _tenant_scope() -> TenantScope:
    """构造测试租户范围。

    Args:
        无。

    Returns:
        ``TenantScope``。
    """

    return Principal(
        tenant_id=TenantId("00000000-0000-0000-0000-000000000001"),
        user_id="u-1",
    ).to_scope()


def _descriptor(*, job_type: str = "test.schedule.job") -> JobHandlerDescriptor:
    """构造测试 descriptor。

    Args:
        job_type: job 类型。

    Returns:
        ``JobHandlerDescriptor``。
    """

    return JobHandlerDescriptor(
        job_type=job_type,
        payload_schema_name="test.payload",
        payload_schema_version=1,
        max_attempts=3,
        retry_base_seconds=1,
        retry_max_seconds=10,
        lease_duration_seconds=60,
    )


def _payload() -> CanonicalJobDocument:
    """构造 canonical payload document。

    Args:
        无。

    Returns:
        ``CanonicalJobDocument``。
    """

    return build_canonical_document({"kind": "test"}, schema_name="test.payload", schema_version=1)


def _snapshot(*, scheduled_for: datetime = NOW) -> CanonicalScheduleEnqueueSnapshot:
    """构造合法 enqueue snapshot。

    Args:
        scheduled_for: 计划 fire 时间。

    Returns:
        ``CanonicalScheduleEnqueueSnapshot``。
    """

    descriptor = _descriptor()
    available_at = scheduled_for
    deadline_at = scheduled_for + timedelta(seconds=300)
    request_fingerprint = job_enqueue_request_fingerprint(
        JobEnqueueRequest(
            descriptor=descriptor,
            idempotency_key="occ-1",
            payload=_payload(),
            available_at=available_at,
            deadline_at=deadline_at,
        )
    )
    return CanonicalScheduleEnqueueSnapshot(
        descriptor=descriptor,
        payload=_payload(),
        idempotency_key="occ-1",
        available_at=available_at,
        deadline_at=deadline_at,
        request_fingerprint=request_fingerprint,
    )


def _registration() -> ScheduleRegistrationRequest:
    """构造合法注册请求。

    Args:
        无。

    Returns:
        ``ScheduleRegistrationRequest``。
    """

    return ScheduleRegistrationRequest(
        schedule_key="daily-close",
        descriptor=_descriptor(),
        payload=_payload(),
        cron_expression="30 2 * * *",
        timezone_name=_NY,
        misfire_policy=ScheduleMisfirePolicy.COALESCE_ONE,
        misfire_grace_seconds=60,
        job_deadline_seconds=300,
    )


def _definition() -> ScheduleDefinition:
    """构造合法 schedule definition（active）。

    Args:
        无。

    Returns:
        ``ScheduleDefinition``。
    """

    return ScheduleDefinition(
        id=uuid4(),
        tenant_id=_tenant_scope().tenant_id,
        schedule_key="daily-close",
        descriptor=_descriptor(),
        payload=_payload(),
        cron_expression="30 2 * * *",
        timezone_name=_NY,
        misfire_policy=ScheduleMisfirePolicy.COALESCE_ONE,
        misfire_grace_seconds=60,
        job_deadline_seconds=300,
        state=ScheduleState.ACTIVE,
        next_fire_at=NOW + timedelta(hours=1),
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def _disabled_definition(*, preserve_cursor: bool = False) -> ScheduleDefinition:
    """构造 disabled draft 或保留历史 cursor 的 definition。

    Args:
        preserve_cursor: 是否保留 active definition 的历史 cursor。

    Returns:
        合法 disabled definition。
    """

    active = _definition()
    return replace(
        active,
        state=ScheduleState.DISABLED,
        next_fire_at=active.next_fire_at if preserve_cursor else None,
    )


def _occurrence(
    *,
    occurrence_id: UUID | None = None,
    state: ScheduleOccurrenceState = ScheduleOccurrenceState.PENDING,
    snapshot: CanonicalScheduleEnqueueSnapshot | None = None,
    job_id: UUID | None = None,
    coalesced_count: int | None = 0,
    skip_reason: ScheduleSkipReason | None = None,
    scheduled_for: datetime = NOW,
) -> ScheduleOccurrence:
    """构造合法 occurrence。

    Args:
        occurrence_id: 可选固定 occurrence UUID。
        state: occurrence 状态。
        snapshot: 可空 snapshot。
        job_id: 可空绑定 job UUID。
        coalesced_count: 可空 coalesced 计数。
        skip_reason: 可空跳过原因。
        scheduled_for: 计划 fire 时间。

    Returns:
        ``ScheduleOccurrence``。
    """

    snap = snapshot if snapshot is not None else _snapshot(scheduled_for=scheduled_for)
    return ScheduleOccurrence(
        id=occurrence_id if occurrence_id is not None else uuid4(),
        tenant_id=_tenant_scope().tenant_id,
        schedule_id=uuid4(),
        schedule_version=1,
        scheduled_for=scheduled_for,
        state=state,
        snapshot=snap
        if state
        in (
            ScheduleOccurrenceState.PENDING,
            ScheduleOccurrenceState.MATERIALIZING,
            ScheduleOccurrenceState.ENQUEUED,
        )
        or skip_reason is ScheduleSkipReason.SCHEDULE_DISABLED
        else None,
        job_id=job_id,
        coalesced_count=coalesced_count,
        skip_reason=skip_reason,
        created_at=NOW,
        updated_at=NOW,
    )


class TestCroniterEmpiricalGate:
    """pinned croniter naive-local candidate 的 empirical gate（§5.2/§9.A）。"""

    @pytest.mark.unit
    def test_croniter_naive_candidate_empirical_gate_is_exact_for_new_york_and_shanghai(self) -> None:
        """croniter 只产 naive-local candidate，ZoneInfo round-trip 是唯一 DST classifier。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        # New York spring-gap：02:30 在 2026-03-08 不存在（02:00 -> 03:00）。
        spring_seed = datetime(2026, 3, 7, 12, 0)
        spring_gap = croniter("30 2 * * *", spring_seed).get_next(datetime)
        assert spring_gap == datetime(2026, 3, 8, 2, 30)
        assert spring_gap.tzinfo is None
        ny = ZoneInfo(_NY)
        # fold=0 与 fold=1 的 offset 不同 -> 非 normal；round-trip 到
        # UTC 再转回本地不等于原 naive -> nonexistent（gap）。
        fold0_aware = spring_gap.replace(tzinfo=ny, fold=0)
        roundtrip = fold0_aware.astimezone(timezone.utc).astimezone(ny).replace(tzinfo=None)
        assert roundtrip != spring_gap

        # New York fall-fold：01:30 在 2026-11-01 ambiguous（fold=0/1 两个时刻）。
        fall_seed = datetime(2026, 10, 31, 12, 0)
        fall_fold = croniter("30 1 * * *", fall_seed).get_next(datetime)
        assert fall_fold == datetime(2026, 11, 1, 1, 30)
        assert fall_fold.tzinfo is None
        fold0 = fall_fold.replace(tzinfo=ny, fold=0)
        fold1 = fall_fold.replace(tzinfo=ny, fold=1)
        assert fold0.astimezone(timezone.utc) != fold1.astimezone(timezone.utc)
        # fold=0 是真实时刻：round-trip 保持原 naive。
        roundtrip_fold = fold0.astimezone(timezone.utc).astimezone(ny).replace(tzinfo=None)
        assert roundtrip_fold == fall_fold

        # Asia/Shanghai 无 DST：offset 恒定 +08:00。
        sh = ZoneInfo(_SH)
        shanghai = croniter("30 2 * * *", datetime(2026, 3, 1, 0, 0)).get_next(datetime)
        assert shanghai == datetime(2026, 3, 1, 2, 30)
        assert sh.utcoffset(shanghai) == timedelta(hours=8)

        # get_next 严格大于 seed（seed 恰为 candidate 时刻也返回下一个）。
        exact_seed = datetime(2026, 3, 9, 2, 30)
        assert croniter("30 2 * * *", exact_seed).get_next(datetime) == datetime(2026, 3, 10, 2, 30)
        # 每日候选按 naive-local 枚举，随后由 round-trip 分类为有效 UTC。
        candidates = [
            croniter("30 2 * * *", spring_seed).get_next(datetime),
            croniter("30 2 * * *", datetime(2026, 3, 9, 2, 30)).get_next(datetime),
        ]
        assert candidates[0] == datetime(2026, 3, 8, 2, 30)
        assert candidates[1] == datetime(2026, 3, 10, 2, 30)


class TestCronAndTimezoneValidation:
    """cron/timezone 结构校验测试。"""

    @pytest.mark.unit
    def test_cron_expression_accepts_five_field_posix_forms(self) -> None:
        """5 字段 minute-resolution POSIX 表达式全部接受。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for expression in (
            "30 2 * * *",
            "*/5 * * * *",
            "0 9 * * 1-5",
            "15,45 8,20 * * *",
            "0 12 * JAN-JUN *",
        ):
            validate_cron_expression(expression)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "expression",
        [
            "30 2 * * * *",
            "@daily",
            "30 2 * *",
            "H 2 * * *",
            "30 2 * * * ",
            " 30 2 * * *",
            "30 2 * * ?",
            "H/5 * * * *",
            "0 R/5 * * *",
            "0 0 15W * *",
            "0 0 L * *",
        ],
    )
    def test_cron_expression_rejects_non_canonical_forms(self, expression: str) -> None:
        """秒字段/昵称/随机扩展/空白漂移/非法字符一律拒绝。

        Args:
            expression: 非法 cron 表达式。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ScheduleInputError):
            validate_cron_expression(expression)
        with pytest.raises(ScheduleInputError):
            replace(_registration(), cron_expression=expression)

    @pytest.mark.unit
    def test_timezone_name_accepts_iana_and_rejects_fixed_offset(self) -> None:
        """IANA 名称接受，固定 UTC offset 形态与不可加载名称拒绝。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        validate_timezone_name("Asia/Shanghai")
        validate_timezone_name("America/New_York")
        validate_timezone_name("UTC")
        for name in ("UTC+8", "GMT+08:00", "Etc/GMT-5", "Asia/Shanghai+8", "Not/AZone"):
            with pytest.raises(ScheduleInputError):
                validate_timezone_name(name)
        with pytest.raises(ScheduleInputError):
            replace(_registration(), timezone_name="UTC+8")


class TestScheduleRegistrationAndDefinition:
    """注册请求与 definition 的构造不变量。"""

    @pytest.mark.unit
    def test_registration_request_requires_deadline_greater_than_grace(self) -> None:
        """deadline 必须大于 grace，防 misfire 一入队即过期。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        valid = _registration()
        assert valid.job_deadline_seconds > valid.misfire_grace_seconds
        with pytest.raises(ScheduleInputError):
            replace(valid, job_deadline_seconds=valid.misfire_grace_seconds)
        with pytest.raises(ScheduleInputError):
            replace(valid, misfire_policy="coalesce_one")
        with pytest.raises(ScheduleInputError):
            replace(valid, descriptor="descriptor")
        with pytest.raises(ScheduleInputError):
            replace(valid, schedule_key="  spaced  ")

    @pytest.mark.unit
    def test_definition_active_requires_cursor_and_disabled_preserves_history(self) -> None:
        """active 必须有 cursor；disabled draft 与历史 cursor 都合法。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        valid = _definition()
        assert valid.state is ScheduleState.ACTIVE
        disabled_draft = replace(valid, state=ScheduleState.DISABLED, next_fire_at=None)
        assert disabled_draft.next_fire_at is None
        disabled_historical = replace(valid, state=ScheduleState.DISABLED)
        assert disabled_historical.next_fire_at == valid.next_fire_at
        with pytest.raises(ScheduleInputError):
            replace(valid, next_fire_at=None)
        with pytest.raises(ScheduleInputError):
            replace(valid, tenant_id="tenant")
        with pytest.raises(ScheduleInputError):
            replace(valid, version=0)
        with pytest.raises(ScheduleInputError):
            replace(valid, id="schedule-id")

    @pytest.mark.unit
    def test_activation_request_requires_positive_version_and_closed_state(self) -> None:
        """activation CAS 请求必须携带 positive version 与枚举 state。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        request = ScheduleActivationRequest(
            schedule_id=uuid4(),
            expected_version=1,
            target_state=ScheduleState.ACTIVE,
        )
        assert request.target_state is ScheduleState.ACTIVE
        with pytest.raises(ScheduleInputError):
            replace(request, expected_version=0)
        with pytest.raises(ScheduleInputError):
            replace(request, target_state="active")

    @pytest.mark.unit
    def test_schedule_observation_requires_aware_utc_clock(self) -> None:
        """database_now 必须 aware UTC、definition 必须嵌套。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        observation = ScheduleObservation(definition=_definition(), database_now=NOW)
        assert observation.database_now == NOW
        with pytest.raises(ScheduleInputError):
            replace(observation, database_now=datetime(2026, 1, 1))
        with pytest.raises(ScheduleInputError):
            replace(observation, definition="definition")


class TestScheduleStateTransitionResult:
    """activation/disable CAS result 的严格 action 矩阵。"""

    @pytest.mark.unit
    def test_schedule_state_transition_result_action_matrix_closes_before_after_version_cursor_and_candidate(
        self,
    ) -> None:
        """三种 action 闭合 before/after version、cursor 与 candidate。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        previous = _disabled_definition()
        candidate = NOW + timedelta(minutes=1)
        request = ScheduleActivationRequest(
            schedule_id=previous.id,
            expected_version=previous.version,
            target_state=ScheduleState.ACTIVE,
        )
        current = replace(
            previous,
            state=ScheduleState.ACTIVE,
            next_fire_at=candidate,
            version=previous.version + 1,
            updated_at=NOW + timedelta(seconds=1),
        )
        applied = ScheduleStateTransitionResult(
            action=ScheduleStateTransitionAction.APPLIED,
            request=request,
            previous_definition=previous,
            observation=ScheduleObservation(definition=current, database_now=NOW),
            activation_next_fire_at=candidate,
        )
        assert applied.observation.definition.next_fire_at == candidate
        with pytest.raises(ScheduleInvariantError):
            replace(
                applied,
                observation=ScheduleObservation(
                    definition=replace(current, version=current.version + 1),
                    database_now=NOW,
                ),
            )

        active = _definition()
        disabled = replace(
            active,
            state=ScheduleState.DISABLED,
            version=active.version + 1,
            updated_at=NOW + timedelta(seconds=1),
        )
        disabled_result = ScheduleStateTransitionResult(
            action=ScheduleStateTransitionAction.APPLIED,
            request=ScheduleActivationRequest(
                schedule_id=active.id,
                expected_version=active.version,
                target_state=ScheduleState.DISABLED,
            ),
            previous_definition=active,
            observation=ScheduleObservation(definition=disabled, database_now=NOW),
            activation_next_fire_at=None,
        )
        assert disabled_result.observation.definition.next_fire_at == active.next_fire_at

        unchanged = ScheduleStateTransitionResult(
            action=ScheduleStateTransitionAction.UNCHANGED,
            request=ScheduleActivationRequest(
                schedule_id=active.id,
                expected_version=active.version,
                target_state=ScheduleState.ACTIVE,
            ),
            previous_definition=active,
            observation=ScheduleObservation(definition=active, database_now=NOW),
            activation_next_fire_at=None,
        )
        assert unchanged.previous_definition == unchanged.observation.definition

        preserved = _disabled_definition(preserve_cursor=True)
        stale = ScheduleStateTransitionResult(
            action=ScheduleStateTransitionAction.CLOCK_STALE,
            request=ScheduleActivationRequest(
                schedule_id=preserved.id,
                expected_version=preserved.version,
                target_state=ScheduleState.ACTIVE,
            ),
            previous_definition=preserved,
            observation=ScheduleObservation(definition=preserved, database_now=NOW),
            activation_next_fire_at=NOW,
        )
        assert stale.previous_definition == stale.observation.definition
        assert stale.activation_next_fire_at == stale.observation.database_now

    @pytest.mark.unit
    def test_unchanged_and_clock_stale_require_zero_mutation(self) -> None:
        """unchanged/clock_stale 必须返回逐字段相等的 definition。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        active = _definition()
        unchanged = ScheduleStateTransitionResult(
            action=ScheduleStateTransitionAction.UNCHANGED,
            request=ScheduleActivationRequest(
                schedule_id=active.id,
                expected_version=active.version,
                target_state=ScheduleState.ACTIVE,
            ),
            previous_definition=active,
            observation=ScheduleObservation(definition=active, database_now=NOW),
            activation_next_fire_at=None,
        )
        assert unchanged.previous_definition == unchanged.observation.definition

        previous = _disabled_definition(preserve_cursor=True)
        stale = ScheduleStateTransitionResult(
            action=ScheduleStateTransitionAction.CLOCK_STALE,
            request=ScheduleActivationRequest(
                schedule_id=previous.id,
                expected_version=previous.version,
                target_state=ScheduleState.ACTIVE,
            ),
            previous_definition=previous,
            observation=ScheduleObservation(definition=previous, database_now=NOW),
            activation_next_fire_at=NOW,
        )
        assert stale.activation_next_fire_at == stale.observation.database_now
        with pytest.raises(ScheduleInvariantError):
            replace(stale, activation_next_fire_at=NOW + timedelta(seconds=1))


class TestScheduleDueDtos:
    """due cursor/entry/page 的 closed 容器不变量。"""

    @pytest.mark.unit
    def test_due_entry_page_and_scan_cursor_matrix(self) -> None:
        """entry cursor 精确绑定 definition，page/scan 空非空矩阵闭合。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        definition = replace(_definition(), next_fire_at=NOW)
        cursor = ScheduleDueCursor(next_fire_at=NOW, schedule_id=definition.id)
        entry = ScheduleDueEntry(
            observation=ScheduleObservation(definition=definition, database_now=NOW),
            cursor_after=cursor,
        )
        page = ScheduleDuePage(entries=(entry,), next_cursor=cursor)
        assert page.next_cursor == entry.cursor_after
        assert ScheduleDuePage(entries=(), next_cursor=None).entries == ()
        with pytest.raises(ScheduleInputError):
            replace(entry, cursor_after=replace(cursor, schedule_id=uuid4()))
        with pytest.raises(ScheduleInputError):
            ScheduleDuePage(entries=(entry, entry), next_cursor=cursor)

        scan = ScheduleDueScanResult(
            reservation=None,
            next_due_cursor=cursor,
            inspected_count=1,
        )
        assert scan.inspected_count == 1
        with pytest.raises(ScheduleInputError):
            replace(scan, inspected_count=0)


class TestCanonicalEnqueueSnapshot:
    """enqueue snapshot 的 fingerprint 单真源闭合测试。"""

    @pytest.mark.unit
    def test_snapshot_fingerprint_must_equal_rebuilt_enqueue_request(self) -> None:
        """fingerprint 必须等于重建 JobEnqueueRequest 的算法真源输出。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        snapshot = _snapshot()
        rebuilt = JobEnqueueRequest(
            descriptor=snapshot.descriptor,
            idempotency_key=snapshot.idempotency_key,
            payload=snapshot.payload,
            available_at=snapshot.available_at,
            deadline_at=snapshot.deadline_at,
        )
        assert snapshot.request_fingerprint == job_enqueue_request_fingerprint(rebuilt)
        assert snapshot.available_at == snapshot.available_at
        assert snapshot.deadline_at > snapshot.available_at
        with pytest.raises(ScheduleInputError):
            replace(snapshot, request_fingerprint="f" * 64)
        with pytest.raises(ScheduleInputError):
            replace(snapshot, available_at=datetime(2026, 1, 1))

    @pytest.mark.unit
    def test_snapshot_available_at_is_scheduled_for_and_deadline_is_scheduled_plus_seconds(self) -> None:
        """available_at 固定为 scheduled_for，deadline 固定加 job_deadline_seconds。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        scheduled_for = NOW + timedelta(hours=2)
        snapshot = _snapshot(scheduled_for=scheduled_for)
        assert snapshot.available_at == scheduled_for
        assert snapshot.deadline_at == scheduled_for + timedelta(seconds=300)


class TestOccurrenceStateMachine:
    """occurrence 状态/snapshot/job/reason 的 closed 组合。"""

    @pytest.mark.unit
    def test_occurrence_state_snapshot_job_and_skip_reason_checks_are_exact(self) -> None:
        """四种 occurrence state 精确闭合 snapshot、job 与 reason。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        pending = _occurrence()
        assert pending.state is ScheduleOccurrenceState.PENDING
        materializing = _occurrence(state=ScheduleOccurrenceState.MATERIALIZING)
        assert materializing.snapshot is not None
        with pytest.raises(ScheduleInputError):
            replace(pending, snapshot=None)
        with pytest.raises(ScheduleInputError):
            replace(pending, job_id=uuid4())
        with pytest.raises(ScheduleInputError):
            replace(pending, skip_reason=ScheduleSkipReason.MISFIRE_EXPIRED)
        enqueued = _occurrence(
            state=ScheduleOccurrenceState.ENQUEUED,
            job_id=uuid4(),
        )
        assert enqueued.snapshot is not None
        assert enqueued.job_id is not None
        assert enqueued.skip_reason is None
        skipped = _occurrence(
            state=ScheduleOccurrenceState.SKIPPED,
            skip_reason=ScheduleSkipReason.MISFIRE_EXPIRED,
            coalesced_count=0,
        )
        assert skipped.snapshot is None
        assert skipped.job_id is None
        assert skipped.skip_reason is ScheduleSkipReason.MISFIRE_EXPIRED

    @pytest.mark.unit
    def test_enqueued_requires_job_id_and_snapshot(self) -> None:
        """enqueued 必须 job_id + 完整 snapshot 且无 skip_reason。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        enqueued = _occurrence(state=ScheduleOccurrenceState.ENQUEUED, job_id=uuid4())
        assert enqueued.job_id is not None
        with pytest.raises(ScheduleInputError):
            replace(enqueued, job_id=None)
        with pytest.raises(ScheduleInputError):
            replace(enqueued, snapshot=None)
        with pytest.raises(ScheduleInputError):
            replace(enqueued, skip_reason=ScheduleSkipReason.SCHEDULE_DISABLED)

    @pytest.mark.unit
    def test_skipped_disabled_keeps_snapshot_but_other_reasons_do_not(self) -> None:
        """schedule_disabled 保留 snapshot，其它 skip reason 必须全 NULL。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        disabled = _occurrence(
            state=ScheduleOccurrenceState.SKIPPED,
            snapshot=_snapshot(),
            skip_reason=ScheduleSkipReason.SCHEDULE_DISABLED,
            coalesced_count=0,
        )
        assert disabled.snapshot is not None
        assert disabled.coalesced_count == 0
        with pytest.raises(ScheduleInputError):
            replace(disabled, coalesced_count=None)
        misfire = _occurrence(
            state=ScheduleOccurrenceState.SKIPPED,
            skip_reason=ScheduleSkipReason.MISFIRE_EXPIRED,
            coalesced_count=2,
        )
        assert misfire.snapshot is None
        lookback = _occurrence(
            state=ScheduleOccurrenceState.SKIPPED,
            skip_reason=ScheduleSkipReason.LOOKBACK_EXCEEDED,
            coalesced_count=None,
        )
        assert lookback.coalesced_count is None
        with pytest.raises(ScheduleInputError):
            replace(lookback, snapshot=_snapshot())
        with pytest.raises(ScheduleInputError):
            replace(lookback, coalesced_count=1)
        with pytest.raises(ScheduleInputError):
            replace(misfire, coalesced_count=None)
        with pytest.raises(ScheduleInputError):
            replace(lookback, skip_reason="lookback_exceeded")

    @pytest.mark.unit
    def test_coalesced_count_is_exact_nonnegative(self) -> None:
        """coalesced_count 必须 exact nonnegative int。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ScheduleInputError):
            replace(_occurrence(), coalesced_count=-1)
        with pytest.raises(ScheduleInputError):
            replace(_occurrence(), coalesced_count=True)
        with pytest.raises(ScheduleInputError):
            _occurrence(snapshot=_snapshot(scheduled_for=NOW + timedelta(minutes=1)))


class TestScheduleReplayDtos:
    """replay cursor/page 的 MATERIALIZING-first 与 PENDING cursor 不变量。"""

    @pytest.mark.unit
    def test_replay_page_orders_commitments_and_tracks_last_pending(self) -> None:
        """MATERIALIZING 必须在前，cursor 精确等于最后 PENDING key。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        materializing = _occurrence(
            state=ScheduleOccurrenceState.MATERIALIZING,
            scheduled_for=NOW,
        )
        pending = _occurrence(scheduled_for=NOW + timedelta(minutes=1))
        cursor = ScheduleReplayCursor(
            scheduled_for=pending.scheduled_for,
            occurrence_id=pending.id,
        )
        page = ScheduleReplayPage(
            occurrences=(materializing, pending),
            next_pending_cursor=cursor,
        )
        assert page.next_pending_cursor == cursor
        with pytest.raises(ScheduleInputError):
            replace(page, occurrences=(pending, materializing))
        with pytest.raises(ScheduleInputError):
            replace(page, occurrences=(materializing, pending, pending))
        with pytest.raises(ScheduleInputError):
            replace(page, next_pending_cursor=replace(cursor, occurrence_id=uuid4()))


class TestReservationDtos:
    """reservation batch/result 的 closed 组合。"""

    @pytest.mark.unit
    def test_reservation_batch_requires_one_to_three_reservations(self) -> None:
        """batch 必须 1-3 条 reservation、positive version 与 aware cursor。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        pending = ScheduleOccurrenceReservation(
            scheduled_for=NOW,
            state=ScheduleOccurrenceState.PENDING,
            snapshot=_snapshot(),
            coalesced_count=0,
            skip_reason=None,
        )
        batch = ScheduleReservationBatch(
            schedule_id=uuid4(),
            expected_version=1,
            expected_next_fire_at=NOW,
            resulting_state=ScheduleState.ACTIVE,
            resulting_next_fire_at=NOW + timedelta(hours=1),
            reservations=(pending,),
        )
        assert len(batch.reservations) == 1
        with pytest.raises(ScheduleInputError):
            replace(batch, reservations=())
        with pytest.raises(ScheduleInputError):
            replace(batch, reservations=(pending, pending, pending, pending))
        with pytest.raises(ScheduleInputError):
            replace(batch, reservations=[pending])
        with pytest.raises(ScheduleInputError):
            replace(batch, resulting_next_fire_at=datetime(2026, 1, 1))
        with pytest.raises(ScheduleInputError):
            replace(batch, resulting_next_fire_at=NOW)

    @pytest.mark.unit
    def test_scan_limit_batch_explicitly_disables_and_preserves_expected_cursor(self) -> None:
        """scan-limit batch 显式 disabled，保留 cursor 且含唯一 audit。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        scan_limit = ScheduleOccurrenceReservation(
            scheduled_for=NOW,
            state=ScheduleOccurrenceState.SKIPPED,
            snapshot=None,
            coalesced_count=None,
            skip_reason=ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED,
        )
        batch = ScheduleReservationBatch(
            schedule_id=uuid4(),
            expected_version=1,
            expected_next_fire_at=NOW,
            resulting_state=ScheduleState.DISABLED,
            resulting_next_fire_at=NOW,
            reservations=(scan_limit,),
        )
        assert batch.resulting_state is ScheduleState.DISABLED
        assert batch.resulting_next_fire_at == batch.expected_next_fire_at
        with pytest.raises(ScheduleInputError):
            replace(batch, resulting_next_fire_at=NOW + timedelta(minutes=1))
        with pytest.raises(
            ScheduleInvariantError,
            match="schedule_batch_duplicate_scheduled_for",
        ):
            replace(batch, reservations=(scan_limit, scan_limit))
        with pytest.raises(ScheduleInputError):
            replace(batch, reservations=(replace(scan_limit, skip_reason=ScheduleSkipReason.LOOKBACK_EXCEEDED),))

    @pytest.mark.unit
    def test_schedule_reservation_batch_rejects_duplicate_scheduled_for_before_postgres(
        self,
    ) -> None:
        """pure batch 在 PostgreSQL 前拒绝重复 occurrence 自然键。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        lookback = ScheduleOccurrenceReservation(
            scheduled_for=NOW,
            state=ScheduleOccurrenceState.SKIPPED,
            snapshot=None,
            coalesced_count=None,
            skip_reason=ScheduleSkipReason.LOOKBACK_EXCEEDED,
        )
        scan_limit = replace(
            lookback,
            skip_reason=ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED,
        )
        with pytest.raises(ScheduleInvariantError) as error:
            ScheduleReservationBatch(
                schedule_id=uuid4(),
                expected_version=1,
                expected_next_fire_at=NOW,
                resulting_state=ScheduleState.DISABLED,
                resulting_next_fire_at=NOW,
                reservations=(lookback, scan_limit),
            )
        assert str(error.value) == "schedule_batch_duplicate_scheduled_for"

    @pytest.mark.unit
    def test_reservation_result_actions_are_closed(self) -> None:
        """reserved 必须非空 occurrences，lost_race 必须空。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        occurrence = _occurrence()
        reserved = ScheduleReservationResult(
            action=ScheduleReserveAction.RESERVED,
            occurrences=(occurrence,),
        )
        assert reserved.action is ScheduleReserveAction.RESERVED
        lost = ScheduleReservationResult(action=ScheduleReserveAction.LOST_RACE, occurrences=())
        assert lost.occurrences == ()
        with pytest.raises(ScheduleInputError):
            replace(reserved, occurrences=())
        with pytest.raises(ScheduleInputError):
            replace(lost, occurrences=(occurrence,))
        with pytest.raises(ScheduleInputError):
            replace(reserved, action="reserved")


class TestMaterializationDtos:
    """begin/mark/materialize 决策的 closed 组合。"""

    @pytest.mark.unit
    def test_materialization_decision_requires_enum_action_and_nested_occurrence(self) -> None:
        """decision 的 action 必须枚举、occurrence 必须嵌套。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        decision = ScheduleMaterializationDecision(
            action=ScheduleMaterializationAction.ENQUEUE,
            occurrence=_occurrence(state=ScheduleOccurrenceState.MATERIALIZING),
        )
        assert decision.action is ScheduleMaterializationAction.ENQUEUE
        unavailable = ScheduleMaterializationDecision(
            action=ScheduleMaterializationAction.UNAVAILABLE,
            occurrence=_occurrence(),
        )
        assert unavailable.occurrence.state is ScheduleOccurrenceState.PENDING
        assert ScheduleMaterializationAdmission.PENDING_UNAVAILABLE.value == "pending_unavailable"
        with pytest.raises(ValueError):
            ScheduleMaterializationAdmission("unavailable")
        with pytest.raises(ScheduleInputError):
            replace(decision, action="enqueue")
        with pytest.raises(ScheduleInputError):
            replace(decision, occurrence="occurrence")
        with pytest.raises(ScheduleInputError):
            replace(decision, occurrence=_occurrence())

    @pytest.mark.unit
    def test_mark_enqueued_result_actions_are_closed(self) -> None:
        """mark 结果 action 必须枚举。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        result = ScheduleMarkEnqueuedResult(
            action=ScheduleMarkEnqueuedAction.MARKED,
            occurrence=_occurrence(
                state=ScheduleOccurrenceState.ENQUEUED,
                job_id=uuid4(),
            ),
        )
        assert result.action is ScheduleMarkEnqueuedAction.MARKED
        with pytest.raises(ScheduleInputError):
            replace(result, action="marked")
        with pytest.raises(ScheduleInputError):
            replace(
                result,
                occurrence=_occurrence(state=ScheduleOccurrenceState.MATERIALIZING),
            )

    @pytest.mark.unit
    def test_materialization_result_four_state_invariants(self) -> None:
        """materialization 四态严格绑定 occurrence state 与 receipt。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        enqueued_occurrence = _occurrence(
            state=ScheduleOccurrenceState.ENQUEUED,
            job_id=uuid4(),
        )
        bound_job_id = enqueued_occurrence.job_id
        assert bound_job_id is not None
        receipt = JobEnqueueReceipt(
            tenant_id=_tenant_scope().tenant_id,
            definition_id=uuid4(),
            job_id=bound_job_id,
            state=JobState.READY,
            idempotency_reused=False,
        )
        result = ScheduleMaterializationResult(
            action=ScheduleMaterializationResultAction.ENQUEUED,
            occurrence=enqueued_occurrence,
            enqueue_receipt=receipt,
        )
        enqueued_receipt = result.enqueue_receipt
        assert enqueued_receipt is not None
        assert enqueued_receipt.job_id == bound_job_id
        with pytest.raises(ScheduleInputError):
            replace(result, enqueue_receipt=None)
        with pytest.raises(ScheduleInputError):
            replace(result, enqueue_receipt=replace(receipt, job_id=uuid4()))

        already = ScheduleMaterializationResult(
            action=ScheduleMaterializationResultAction.ALREADY_ENQUEUED,
            occurrence=enqueued_occurrence,
            enqueue_receipt=None,
        )
        assert already.enqueue_receipt is None
        with pytest.raises(ScheduleInputError):
            replace(already, enqueue_receipt=receipt)
        with pytest.raises(ScheduleInputError):
            replace(already, occurrence=_occurrence())

        unavailable = ScheduleMaterializationResult(
            action=ScheduleMaterializationResultAction.UNAVAILABLE,
            occurrence=_occurrence(),
            enqueue_receipt=None,
        )
        assert unavailable.occurrence.state is ScheduleOccurrenceState.PENDING
        with pytest.raises(ScheduleInputError):
            replace(unavailable, occurrence=enqueued_occurrence)

        skipped_occurrence = _occurrence(
            state=ScheduleOccurrenceState.SKIPPED,
            skip_reason=ScheduleSkipReason.SCHEDULE_DISABLED,
            snapshot=_snapshot(),
            coalesced_count=0,
        )
        skipped = ScheduleMaterializationResult(
            action=ScheduleMaterializationResultAction.SKIPPED,
            occurrence=skipped_occurrence,
            enqueue_receipt=None,
        )
        assert skipped.enqueue_receipt is None
        with pytest.raises(ScheduleInputError):
            replace(
                skipped,
                occurrence=_occurrence(state=ScheduleOccurrenceState.PENDING),
            )
