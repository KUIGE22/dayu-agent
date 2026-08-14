"""durable schedule 的应用 Service 与 cron/misfire 编排。

本模块是 Slice 2.2 schedule application orchestration 的唯一 owner：

- ``croniter`` 只在本模块导入，并且只接收/返回 naive local datetime；
- PostgreSQL ``ScheduleObservation.database_now`` 是唯一时钟真源；
- schedule cursor 推进与 occurrence reservation 由 Store 单事务提交；
- PENDING occurrence 在本进程 availability 为真时才线性化为
  MATERIALIZING，已提交的 MATERIALIZING 重放永不再次经过可否决 gate；
- Host 只看三个高层 scheduler gateway 方法，绝不取得 Store 的
  ``begin_materialization`` / ``mark_enqueued`` 接口。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID
from zoneinfo import ZoneInfo

from croniter import CroniterBadDateError, CroniterError, croniter

from dayu.investment.composition import PlatformServiceProtocol
from dayu.investment.domain.jobs import (
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobHandlerDescriptor,
    job_enqueue_request_fingerprint,
)
from dayu.investment.domain.schedules import (
    CanonicalScheduleEnqueueSnapshot,
    ScheduleActivationRequest,
    ScheduleDefinition,
    ScheduleDueCursor,
    ScheduleDueScanResult,
    ScheduleExecutionUnavailableError,
    ScheduleInputError,
    ScheduleInvariantError,
    ScheduleMarkEnqueuedAction,
    ScheduleMaterializationAction,
    ScheduleMaterializationAdmission,
    ScheduleMaterializationDecision,
    ScheduleMaterializationResult,
    ScheduleMaterializationResultAction,
    ScheduleOccurrenceReservation,
    ScheduleOccurrenceState,
    ScheduleRegistrationRequest,
    ScheduleReplayCursor,
    ScheduleReplayPage,
    ScheduleReservationBatch,
    ScheduleSkipReason,
    ScheduleState,
    ScheduleStateTransitionAction,
    ScheduleStateTransitionResult,
    ScheduleVersionConflictError,
)

if TYPE_CHECKING:
    from dayu.investment.domain.identifiers import TenantScope
    from dayu.investment.domain.schedules import ScheduleOccurrence
    from dayu.investment.storage.protocols import ScheduleStoreProtocol

DURABLE_SCHEDULES_SERVICE_NAME = "durable_schedules"
"""durable schedule Service 的稳定 production mapping 名称。"""

_ACTIVATION_CAS_ATTEMPTS = 3
"""一次 public activate/re-enable 允许的总 CAS 次数（包含首次）。"""

_SCHEDULE_IDEMPOTENCY_KEY_PREFIX = "schedule"
"""schedule occurrence job 幂等键的稳定 namespace。"""

_REGISTRATION_CRON_PROBE_SEED = datetime(2000, 1, 1)
"""registration candidate probe 使用的固定 naive seed。"""


class _ScheduleScanOrigin(str, Enum):
    """candidate scan 的 closed process-local origin 状态。"""

    PERSISTED_CURSOR = "persisted_cursor"
    DISTINCT_RELOCATED_CURSOR = "distinct_relocated_cursor"


@dataclass(frozen=True, slots=True)
class _CandidateScanBounds:
    """单次 cron candidate 读取的闭合边界。

    Args:
        scan_limit: raw candidate 总上限。
        minimum_utc: 可空 inclusive UTC 下界。
        strictly_after_utc: 可空 strict UTC 单调下界。

    Returns:
        不适用；该类是不可变扫描边界值对象。

    Raises:
        无。
    """

    scan_limit: int
    minimum_utc: datetime | None
    strictly_after_utc: datetime | None


@runtime_checkable
class ScheduleJobGatewayProtocol(Protocol):
    """ScheduleService 消费的 JobService 窄结构协议。"""

    def is_execution_available(self, descriptor: JobHandlerDescriptor) -> bool:
        """检查本进程是否可执行完整 descriptor。

        Args:
            descriptor: occurrence/schedule 冻结的完整 descriptor。

        Returns:
            descriptor 与 execution handler 均精确注册时返回 ``True``。

        Raises:
            无。
        """

        ...

    def enqueue_committed_schedule_occurrence(
        self,
        scope: TenantScope,
        decision: ScheduleMaterializationDecision,
    ) -> JobEnqueueReceipt:
        """入队已经持久化为 MATERIALIZING 的 occurrence commitment。

        Args:
            scope: 租户范围。
            decision: Store 返回的 typed persisted enqueue decision。

        Returns:
            PostgreSQL job enqueue receipt。

        Raises:
            无额外协议约束；实现只可抛 closed jobs errors。
        """

        ...


def _require_positive_int(value: int, label: str) -> None:
    """校验 exact positive int，拒绝 ``bool`` 冒充。

    Args:
        value: 待校验整数。
        label: 稳定字段名称。

    Returns:
        无。

    Raises:
        ScheduleInputError: 值不是精确正整数时抛出。
    """

    if type(value) is not int or value <= 0:
        raise ScheduleInputError(f"{label}_invalid")


def _validate_croniter_expression(expression: str) -> None:
    """用 pinned croniter 补足 domain 的语义有效性校验。

    Args:
        expression: 已通过五字段结构校验的 cron 表达式。

    Returns:
        无。

    Raises:
        ScheduleInputError: croniter 判定表达式非法或固定 seed 无候选时
            抛出。
    """

    try:
        valid = croniter.is_valid(expression)
    except (CroniterError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ScheduleInputError("cron_expression_invalid")
    try:
        candidate: datetime = croniter(
            expression,
            _REGISTRATION_CRON_PROBE_SEED,
        ).get_next(datetime)
    except CroniterBadDateError:
        raise ScheduleInputError("schedule_cron_has_no_candidate") from None
    except (CroniterError, TypeError, ValueError):
        raise ScheduleInputError("cron_expression_invalid") from None
    if not isinstance(candidate, datetime):
        raise ScheduleInputError("schedule_cron_has_no_candidate")


def _local_naive(value: datetime, zone: ZoneInfo) -> datetime:
    """把 aware UTC 时间转换为 croniter 使用的 naive local 时间。

    Args:
        value: aware UTC 时间。
        zone: schedule IANA timezone。

    Returns:
        去除 ``tzinfo`` 的 local wall datetime。

    Raises:
        无。
    """

    return value.astimezone(zone).replace(tzinfo=None)


def _classify_local_candidate(raw_candidate: datetime, zone: ZoneInfo) -> datetime | None:
    """以 ZoneInfo fold=0 round-trip 分类一个 naive local candidate。

    nonexistent local time 的 UTC round-trip 不等于原 wall time，返回
    ``None``；normal/ambiguous candidate 均使用 fold=0 对应的唯一 UTC
    fire，因而 fall-fold 只产生一次 occurrence。

    Args:
        raw_candidate: croniter 返回的 naive local datetime。
        zone: schedule IANA timezone。

    Returns:
        有效时返回 aware UTC candidate；nonexistent 时返回 ``None``。

    Raises:
        ScheduleInvariantError: croniter 返回非 naive datetime 时抛出。
    """

    if not isinstance(raw_candidate, datetime) or raw_candidate.tzinfo is not None:
        raise ScheduleInvariantError("schedule_cron_candidate_not_naive")
    fold_zero = raw_candidate.replace(tzinfo=zone, fold=0)
    candidate_utc = fold_zero.astimezone(timezone.utc)
    round_trip = candidate_utc.astimezone(zone).replace(tzinfo=None)
    if round_trip != raw_candidate:
        return None
    return candidate_utc


def _next_valid_utc_candidate(
    iterator: croniter,
    zone: ZoneInfo,
    *,
    raw_count: int,
    bounds: _CandidateScanBounds,
) -> tuple[datetime | None, int]:
    """从同一个 croniter iterator 读取下一个可接受 UTC candidate。

    每次 raw ``get_next`` 在 DST 分类前先计数。invalid/nonexistent、早于
    lookback 边界或不满足 UTC 严格单调的 candidate 仍消耗 scan slot。

    Args:
        iterator: 已以 naive local seed 创建的 croniter iterator。
        zone: schedule IANA timezone。
        raw_count: 本次 reservation scan 已消耗的 raw candidate 数。
        bounds: raw candidate 总上限与 UTC 接受边界。

    Returns:
        ``(candidate_or_none, updated_raw_count)``；达到 exact limit 仍未
        找到 candidate 时返回 ``None``。

    Raises:
        ScheduleInvariantError: croniter 已耗尽、运行失败或返回非法类型时
            抛出。
    """

    count = raw_count
    while count < bounds.scan_limit:
        try:
            raw_candidate: datetime = iterator.get_next(datetime)
        except CroniterBadDateError:
            raise ScheduleInvariantError("schedule_cron_iteration_exhausted") from None
        except (CroniterError, TypeError, ValueError):
            raise ScheduleInvariantError("schedule_cron_iteration_failed") from None
        count += 1
        candidate_utc = _classify_local_candidate(raw_candidate, zone)
        if candidate_utc is None:
            continue
        if bounds.minimum_utc is not None and candidate_utc < bounds.minimum_utc:
            continue
        if bounds.strictly_after_utc is not None and candidate_utc <= bounds.strictly_after_utc:
            continue
        return candidate_utc, count
    return None, count


def _new_iterator(expression: str, seed: datetime) -> croniter:
    """创建一个只消费 naive local datetime 的 croniter iterator。

    Args:
        expression: 已验证的五字段 cron 表达式。
        seed: naive local datetime。

    Returns:
        croniter iterator。

    Raises:
        ScheduleInvariantError: 持久化 cron 已耗尽或无法创建 iterator 时
            抛出。
    """

    if seed.tzinfo is not None:
        raise ScheduleInvariantError("schedule_cron_seed_not_naive")
    try:
        return croniter(expression, seed)
    except CroniterBadDateError:
        raise ScheduleInvariantError("schedule_cron_iteration_exhausted") from None
    except (CroniterError, TypeError, ValueError):
        raise ScheduleInvariantError("schedule_cron_invalid") from None


def _first_strictly_future_candidate(
    definition: ScheduleDefinition,
    database_now: datetime,
    *,
    scan_limit: int,
) -> datetime:
    """按 PG observation 计算首个严格 future 的有效 UTC fire。

    Args:
        definition: disabled schedule immutable definition。
        database_now: Store observation 的 aware UTC PG clock。
        scan_limit: raw cron candidate 上限。

    Returns:
        严格晚于 ``database_now`` 的首个有效 UTC candidate。

    Raises:
        ScheduleInvariantError: cron 迭代失败或达到 scan limit 时抛出。
    """

    zone = ZoneInfo(definition.timezone_name)
    iterator = _new_iterator(
        definition.cron_expression,
        _local_naive(database_now, zone),
    )
    candidate, _ = _next_valid_utc_candidate(
        iterator,
        zone,
        raw_count=0,
        bounds=_CandidateScanBounds(
            scan_limit=scan_limit,
            minimum_utc=None,
            strictly_after_utc=database_now,
        ),
    )
    if candidate is None:
        raise ScheduleInvariantError("schedule_candidate_scan_limit_exceeded")
    return candidate


def _schedule_idempotency_key(
    schedule_id: UUID,
    schedule_version: int,
    scheduled_for: datetime,
) -> str:
    """由 occurrence natural identity 构造稳定 job idempotency key。

    公式逐字固定为
    ``schedule:{schedule_id}:{schedule_version}:{scheduled_for.isoformat(timespec='microseconds')}``。
    tenant 已由 JobStore 的 composite uniqueness 隔离，不进入 key。

    Args:
        schedule_id: schedule UUID。
        schedule_version: reservation 使用的 schedule version。
        scheduled_for: occurrence aware UTC fire。

    Returns:
        稳定非空 idempotency key。

    Raises:
        无。
    """

    timestamp = scheduled_for.isoformat(timespec="microseconds")
    return f"{_SCHEDULE_IDEMPOTENCY_KEY_PREFIX}:{schedule_id}:{schedule_version}:{timestamp}"


def _build_snapshot(
    definition: ScheduleDefinition,
    scheduled_for: datetime,
) -> CanonicalScheduleEnqueueSnapshot:
    """从 immutable schedule revision 与 fire 构造冻结 enqueue snapshot。

    Args:
        definition: reservation CAS 对应的 schedule revision。
        scheduled_for: eligible group 的最新 fire。

    Returns:
        完整 canonical enqueue snapshot。

    Raises:
        ScheduleInputError: nested jobs/schedule DTO 不变量不闭合时抛出。
    """

    deadline_at = scheduled_for + timedelta(seconds=definition.job_deadline_seconds)
    idempotency_key = _schedule_idempotency_key(
        definition.id,
        definition.version,
        scheduled_for,
    )
    request = JobEnqueueRequest(
        descriptor=definition.descriptor,
        idempotency_key=idempotency_key,
        payload=definition.payload,
        available_at=scheduled_for,
        deadline_at=deadline_at,
    )
    return CanonicalScheduleEnqueueSnapshot(
        descriptor=definition.descriptor,
        payload=definition.payload,
        idempotency_key=idempotency_key,
        available_at=scheduled_for,
        deadline_at=deadline_at,
        request_fingerprint=job_enqueue_request_fingerprint(request),
    )


def _lookback_audit(scheduled_for: datetime) -> ScheduleOccurrenceReservation:
    """构造一条 closed lookback-exceeded audit reservation。

    Args:
        scheduled_for: 进入事务时的 persisted cursor。

    Returns:
        无 snapshot/count 的 skipped audit。

    Raises:
        ScheduleInputError: DTO 不变量不闭合时抛出。
    """

    return ScheduleOccurrenceReservation(
        scheduled_for=scheduled_for,
        state=ScheduleOccurrenceState.SKIPPED,
        snapshot=None,
        coalesced_count=None,
        skip_reason=ScheduleSkipReason.LOOKBACK_EXCEEDED,
    )


def _scan_limit_audit(scheduled_for: datetime) -> ScheduleOccurrenceReservation:
    """构造一条 closed candidate-scan-limit audit reservation。

    Args:
        scheduled_for: 进入 bounded scan 前的 working cursor/boundary。

    Returns:
        无 snapshot/count 的 skipped audit。

    Raises:
        ScheduleInputError: DTO 不变量不闭合时抛出。
    """

    return ScheduleOccurrenceReservation(
        scheduled_for=scheduled_for,
        state=ScheduleOccurrenceState.SKIPPED,
        snapshot=None,
        coalesced_count=None,
        skip_reason=ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED,
    )


def _scan_limit_batch(
    definition: ScheduleDefinition,
    *,
    lookback_audit: ScheduleOccurrenceReservation | None,
    scan_origin: _ScheduleScanOrigin,
    scan_limit_anchor: datetime,
) -> ScheduleReservationBatch:
    """丢弃 provisional groups 并构造显式 disable scan-limit batch。

    Args:
        definition: due schedule revision。
        lookback_audit: 可空 lookback audit（唯一允许保留的 provisional）。
        scan_origin: persisted 或 distinct-relocated 的 closed origin 状态。
        scan_limit_anchor: scan-limit audit 使用的自然键时间。

    Returns:
        显式 disabled、保留 persisted cursor 的 reservation batch。

    Raises:
        ScheduleInvariantError: active definition 缺少 persisted cursor，或
            origin/anchor 组合不闭合时抛出。
        ScheduleInputError: batch DTO 不变量不闭合时抛出。
    """

    expected_cursor = definition.next_fire_at
    if expected_cursor is None:
        raise ScheduleInvariantError("schedule_active_cursor_missing")
    if scan_origin is _ScheduleScanOrigin.PERSISTED_CURSOR:
        if scan_limit_anchor != expected_cursor:
            raise ScheduleInvariantError("schedule_scan_origin_anchor_invalid")
        reservations = (_scan_limit_audit(expected_cursor),)
    else:
        if lookback_audit is None or scan_limit_anchor == expected_cursor:
            raise ScheduleInvariantError("schedule_scan_origin_anchor_invalid")
        reservations = (
            lookback_audit,
            _scan_limit_audit(scan_limit_anchor),
        )
    return ScheduleReservationBatch(
        schedule_id=definition.id,
        expected_version=definition.version,
        expected_next_fire_at=expected_cursor,
        resulting_state=ScheduleState.DISABLED,
        resulting_next_fire_at=expected_cursor,
        reservations=reservations,
    )


@dataclass(frozen=True, slots=True)
class _PreparedDueScan:
    """due candidate 扫描的已定位起点与审计上下文。

    Args:
        iterator: 从已定位 wall-clock seed 继续读取的 cron iterator。
        working_cursor: 首个待分类的 UTC candidate。
        raw_count: 定位阶段已消费的 raw candidate 数。
        lookback_audit: 可空 lookback audit。
        scan_origin: persisted 或 distinct-relocated origin。
        scan_limit_anchor: scan-limit audit 的自然键时间。

    Returns:
        不适用；该类是不可变扫描上下文。

    Raises:
        无。
    """

    iterator: croniter
    working_cursor: datetime
    raw_count: int
    lookback_audit: ScheduleOccurrenceReservation | None
    scan_origin: _ScheduleScanOrigin
    scan_limit_anchor: datetime


@dataclass(frozen=True, slots=True)
class _DueCandidateGroups:
    """截至 PG clock 的 expired/eligible candidate 聚合。

    Args:
        resulting_cursor: 首个严格晚于 PG clock 的 cursor。
        expired_count: 过期 candidate 数量。
        expired_latest: 可空最后一条过期 candidate。
        eligible_count: grace 内 candidate 数量。
        eligible_latest: 可空最后一条 grace 内 candidate。

    Returns:
        不适用；该类是不可变 candidate 聚合。

    Raises:
        无。
    """

    resulting_cursor: datetime
    expired_count: int
    expired_latest: datetime | None
    eligible_count: int
    eligible_latest: datetime | None


def _prepare_due_scan(
    definition: ScheduleDefinition,
    lower_bound: datetime,
    zone: ZoneInfo,
    candidate_scan_limit: int,
) -> _PreparedDueScan | ScheduleReservationBatch:
    """从 persisted cursor 或 bounded lookback 位置准备 due scan。

    Args:
        definition: active due schedule definition。
        lower_bound: PG clock 推导的 inclusive lookback 下界。
        zone: schedule IANA timezone。
        candidate_scan_limit: raw cron candidate 总上限。

    Returns:
        可继续扫描的上下文；定位已耗尽上限时返回 disabled batch。

    Raises:
        ScheduleInvariantError: active definition 缺 cursor 或 cron 迭代失败时抛出。
        ScheduleInputError: disabled batch DTO 不变量不闭合时抛出。
    """

    expected_cursor = definition.next_fire_at
    if expected_cursor is None:
        raise ScheduleInvariantError("schedule_active_cursor_missing")
    if expected_cursor >= lower_bound:
        return _PreparedDueScan(
            iterator=_new_iterator(
                definition.cron_expression,
                _local_naive(expected_cursor, zone),
            ),
            working_cursor=expected_cursor,
            raw_count=0,
            lookback_audit=None,
            scan_origin=_ScheduleScanOrigin.PERSISTED_CURSOR,
            scan_limit_anchor=expected_cursor,
        )

    lookback = _lookback_audit(expected_cursor)
    iterator = _new_iterator(
        definition.cron_expression,
        _local_naive(lower_bound - timedelta(minutes=1), zone),
    )
    working_cursor, raw_count = _next_valid_utc_candidate(
        iterator,
        zone,
        raw_count=0,
        bounds=_CandidateScanBounds(
            scan_limit=candidate_scan_limit,
            minimum_utc=lower_bound,
            strictly_after_utc=expected_cursor,
        ),
    )
    if working_cursor is None:
        return _scan_limit_batch(
            definition,
            lookback_audit=lookback,
            scan_origin=_ScheduleScanOrigin.PERSISTED_CURSOR,
            scan_limit_anchor=expected_cursor,
        )
    return _PreparedDueScan(
        iterator=iterator,
        working_cursor=working_cursor,
        raw_count=raw_count,
        lookback_audit=lookback,
        scan_origin=_ScheduleScanOrigin.DISTINCT_RELOCATED_CURSOR,
        scan_limit_anchor=working_cursor,
    )


def _scan_due_candidates(
    definition: ScheduleDefinition,
    database_now: datetime,
    prepared: _PreparedDueScan,
    candidate_scan_limit: int,
) -> _DueCandidateGroups | None:
    """把截至 PG clock 的 candidate 分成 expired 与 eligible 两组。

    Args:
        definition: active due schedule definition。
        database_now: 同事务 PG clock。
        prepared: 已定位的 candidate 扫描上下文。
        candidate_scan_limit: raw cron candidate 总上限。

    Returns:
        完整聚合；scan limit 先耗尽时返回 ``None``。

    Raises:
        ScheduleInvariantError: cron 迭代失败或非单调时抛出。
    """

    expired_count = 0
    expired_latest: datetime | None = None
    eligible_count = 0
    eligible_latest: datetime | None = None
    candidate = prepared.working_cursor
    raw_count = prepared.raw_count
    grace = timedelta(seconds=definition.misfire_grace_seconds)
    while candidate <= database_now:
        if database_now - candidate <= grace:
            eligible_count += 1
            eligible_latest = candidate
        else:
            expired_count += 1
            expired_latest = candidate
        next_candidate, raw_count = _next_valid_utc_candidate(
            prepared.iterator,
            ZoneInfo(definition.timezone_name),
            raw_count=raw_count,
            bounds=_CandidateScanBounds(
                scan_limit=candidate_scan_limit,
                minimum_utc=None,
                strictly_after_utc=candidate,
            ),
        )
        if next_candidate is None:
            return None
        candidate = next_candidate
    return _DueCandidateGroups(
        resulting_cursor=candidate,
        expired_count=expired_count,
        expired_latest=expired_latest,
        eligible_count=eligible_count,
        eligible_latest=eligible_latest,
    )


def _build_grouped_reservations(
    definition: ScheduleDefinition,
    lookback: ScheduleOccurrenceReservation | None,
    groups: _DueCandidateGroups,
) -> tuple[ScheduleOccurrenceReservation, ...]:
    """把 lookback/expired/eligible 聚合构造成闭合 reservation tuple。

    Args:
        definition: active due schedule definition。
        lookback: 可空 lookback audit。
        groups: 完整 candidate 聚合。

    Returns:
        按 lookback、expired、eligible 排序的非空 reservation tuple。

    Raises:
        ScheduleInvariantError: 聚合无法产生 reservation 时抛出。
        ScheduleInputError: reservation DTO 不变量不闭合时抛出。
    """

    reservations: list[ScheduleOccurrenceReservation] = []
    if lookback is not None:
        reservations.append(lookback)
    if groups.expired_latest is not None:
        reservations.append(
            ScheduleOccurrenceReservation(
                scheduled_for=groups.expired_latest,
                state=ScheduleOccurrenceState.SKIPPED,
                snapshot=None,
                coalesced_count=groups.expired_count - 1,
                skip_reason=ScheduleSkipReason.MISFIRE_EXPIRED,
            )
        )
    if groups.eligible_latest is not None:
        reservations.append(
            ScheduleOccurrenceReservation(
                scheduled_for=groups.eligible_latest,
                state=ScheduleOccurrenceState.PENDING,
                snapshot=_build_snapshot(definition, groups.eligible_latest),
                coalesced_count=groups.eligible_count - 1,
                skip_reason=None,
            )
        )
    if not reservations:
        raise ScheduleInvariantError("schedule_due_reservations_empty")
    return tuple(reservations)


def _build_due_batch(
    definition: ScheduleDefinition,
    database_now: datetime,
    *,
    max_lookback_seconds: int,
    candidate_scan_limit: int,
) -> ScheduleReservationBatch:
    """按 PG clock、DST/misfire规则构造一次完整 reservation batch。

    Args:
        definition: active due schedule definition。
        database_now: 与 due page 同事务的 aware UTC PG clock。
        max_lookback_seconds: bounded lookback 秒数。
        candidate_scan_limit: raw cron candidate 总上限。

    Returns:
        normal active cursor-advance batch，或显式 disabled scan-limit batch。

    Raises:
        ScheduleInvariantError: definition 非 active/due、cron 迭代失败或
            internal monotonic invariant 破坏时抛出。
        ScheduleInputError: reservation DTO 不变量不闭合时抛出。
    """

    expected_cursor = definition.next_fire_at
    if definition.state is not ScheduleState.ACTIVE or expected_cursor is None or expected_cursor > database_now:
        raise ScheduleInvariantError("schedule_due_observation_invalid")

    lower_bound = database_now - timedelta(seconds=max_lookback_seconds)
    prepared = _prepare_due_scan(
        definition,
        lower_bound,
        ZoneInfo(definition.timezone_name),
        candidate_scan_limit,
    )
    if isinstance(prepared, ScheduleReservationBatch):
        return prepared
    groups = _scan_due_candidates(
        definition,
        database_now,
        prepared,
        candidate_scan_limit,
    )
    if groups is None:
        return _scan_limit_batch(
            definition,
            lookback_audit=prepared.lookback_audit,
            scan_origin=prepared.scan_origin,
            scan_limit_anchor=prepared.scan_limit_anchor,
        )
    return ScheduleReservationBatch(
        schedule_id=definition.id,
        expected_version=definition.version,
        expected_next_fire_at=expected_cursor,
        resulting_state=ScheduleState.ACTIVE,
        resulting_next_fire_at=groups.resulting_cursor,
        reservations=_build_grouped_reservations(
            definition,
            prepared.lookback_audit,
            groups,
        ),
    )


class ScheduleService(PlatformServiceProtocol):
    """durable schedule 的 application Service。

    Args:
        schedule_store: tenant-scoped schedule/occurrence Store。
        job_gateway: availability 与 committed enqueue 的 JobService 窄入口。
        schedule_max_lookback_seconds: misfire bounded lookback 秒数。
        schedule_candidate_scan_limit: 每轮 raw cron candidate 上限。
    """

    def __init__(
        self,
        *,
        schedule_store: ScheduleStoreProtocol,
        job_gateway: ScheduleJobGatewayProtocol,
        schedule_max_lookback_seconds: int,
        schedule_candidate_scan_limit: int,
    ) -> None:
        """初始化 ScheduleService。

        Args:
            schedule_store: tenant-scoped schedule/occurrence Store。
            job_gateway: availability 与 committed enqueue gateway。
            schedule_max_lookback_seconds: misfire bounded lookback 秒数。
            schedule_candidate_scan_limit: raw cron candidate 上限。

        Returns:
            无。

        Raises:
            ScheduleInputError: 数值设置不是 exact positive int 时抛出。
        """

        _require_positive_int(
            schedule_max_lookback_seconds,
            "schedule_max_lookback_seconds",
        )
        _require_positive_int(
            schedule_candidate_scan_limit,
            "schedule_candidate_scan_limit",
        )
        self._schedule_store = schedule_store
        self._job_gateway = job_gateway
        self._schedule_max_lookback_seconds = schedule_max_lookback_seconds
        self._schedule_candidate_scan_limit = schedule_candidate_scan_limit

    @property
    def platform_service_name(self) -> str:
        """返回稳定 production service mapping 名称。

        Args:
            无。

        Returns:
            精确 ``durable_schedules``。

        Raises:
            无。
        """

        return DURABLE_SCHEDULES_SERVICE_NAME

    def validate_cron_expression(self, expression: str) -> None:
        """复用 Schedule owner 的 croniter 语义校验且不读取 Store。

        Args:
            expression: 待校验的五字段 cron 表达式。

        Returns:
            无。

        Raises:
            ScheduleInputError: croniter 判定表达式非法或无候选时抛出。
        """

        _validate_croniter_expression(expression)

    def get_by_key(
        self,
        scope: TenantScope,
        *,
        schedule_key: str,
    ) -> ScheduleDefinition | None:
        """只委托 Store 按租户与 schedule key 读取当前 definition。

        Args:
            scope: 租户范围。
            schedule_key: 稳定 schedule key。

        Returns:
            Store 返回的当前 definition 或 ``None``。

        Raises:
            ScheduleInputError: schedule key 非法时抛出。
            ScheduleRepositoryError: Store 读取失败或持久 row 非法时原样
                传播。
        """

        return self._schedule_store.get_by_key(
            scope,
            schedule_key=schedule_key,
        )

    def ensure_registered(
        self,
        scope: TenantScope,
        request: ScheduleRegistrationRequest,
    ) -> ScheduleDefinition:
        """校验 cron 后创建或重读 immutable intent 相同的 schedule。

        Args:
            scope: 租户范围。
            request: immutable schedule registration request。

        Returns:
            Store 返回的首次 disabled draft 或既存当前 definition。

        Raises:
            ScheduleInputError: 请求类型或 croniter 语义非法时抛出。
            ScheduleVersionConflictError: 同 key 的 immutable intent 不同时
                抛出。
            ScheduleRepositoryError: Store 写入、重读或持久 row 非法时
                原样传播。
        """

        if not isinstance(request, ScheduleRegistrationRequest):
            raise ScheduleInputError("schedule_registration_request_invalid")
        _validate_croniter_expression(request.cron_expression)
        return self._schedule_store.ensure_registered(scope, request)

    def register(
        self,
        scope: TenantScope,
        request: ScheduleRegistrationRequest,
    ) -> ScheduleDefinition:
        """注册一个 croniter-valid 的 disabled draft schedule。

        registration 不要求当前进程具备 execution handler；availability
        只在 disabled->active 时检查。

        Args:
            scope: 租户范围。
            request: immutable schedule registration request。

        Returns:
            Store 持久化的 disabled definition。

        Raises:
            ScheduleInputError: 请求类型或 croniter 语义非法时抛出。
            ScheduleVersionConflictError: schedule key 冲突时抛出。
        """

        if not isinstance(request, ScheduleRegistrationRequest):
            raise ScheduleInputError("schedule_registration_request_invalid")
        _validate_croniter_expression(request.cron_expression)
        return self._schedule_store.register(scope, request)

    def set_state(
        self,
        scope: TenantScope,
        request: ScheduleActivationRequest,
    ) -> ScheduleStateTransitionResult:
        """以 PG-clock observation 与最多三次 CAS 切换 schedule state。

        Args:
            scope: 租户范围。
            request: 含原始 expected version 的 state transition 请求。

        Returns:
            applied/unchanged，或第三次仍过期的 clock_stale closed result。

        Raises:
            ScheduleInputError: request 类型非法时抛出。
            ScheduleVersionConflictError: schedule 不存在或版本失配时抛出。
            ScheduleExecutionUnavailableError: disabled->active 时本进程没有
                exact execution capability；Store 保持零调用/零 mutation。
            ScheduleInvariantError: cron candidate 无法安全计算时抛出。
        """

        if not isinstance(request, ScheduleActivationRequest):
            raise ScheduleInputError("schedule_activation_request_invalid")
        if request.target_state is ScheduleState.DISABLED:
            return self._schedule_store.set_state(
                scope,
                request,
                activation_next_fire_at=None,
            )

        observation = self._schedule_store.get(scope, request.schedule_id)
        if observation is None or observation.definition.version != request.expected_version:
            raise ScheduleVersionConflictError("schedule_version_conflict")
        if observation.definition.state is ScheduleState.ACTIVE:
            return self._schedule_store.set_state(
                scope,
                request,
                activation_next_fire_at=None,
            )
        if not self._job_gateway.is_execution_available(observation.definition.descriptor):
            raise ScheduleExecutionUnavailableError("schedule_execution_unavailable")

        current_observation = observation
        for attempt in range(_ACTIVATION_CAS_ATTEMPTS):
            candidate = _first_strictly_future_candidate(
                current_observation.definition,
                current_observation.database_now,
                scan_limit=self._schedule_candidate_scan_limit,
            )
            result = self._schedule_store.set_state(
                scope,
                request,
                activation_next_fire_at=candidate,
            )
            if result.action is not ScheduleStateTransitionAction.CLOCK_STALE:
                return result
            if attempt == _ACTIVATION_CAS_ATTEMPTS - 1:
                return result
            current_observation = result.observation
        raise ScheduleInvariantError("schedule_activation_attempts_unreachable")

    def list_replayable_occurrences(
        self,
        scope: TenantScope,
        cursor: ScheduleReplayCursor | None,
        *,
        limit: int,
    ) -> ScheduleReplayPage:
        """返回 MATERIALIZING-first、PENDING-keyset 的 bounded page。

        Args:
            scope: 租户范围。
            cursor: process-local PENDING replay cursor。
            limit: keyword-only page 上限。

        Returns:
            Store 返回的 typed replay page。

        Raises:
            ScheduleInputError: limit 非法时抛出。
            ScheduleInvariantError: Store 返回超过请求上限的 page 时抛出。
        """

        _require_positive_int(limit, "limit")
        page = self._schedule_store.list_replayable(
            scope,
            cursor,
            limit=limit,
        )
        if len(page.occurrences) > limit:
            raise ScheduleInvariantError("schedule_replay_page_limit_exceeded")
        return page

    def reserve_due_occurrences(
        self,
        scope: TenantScope,
        cursor: ScheduleDueCursor | None,
        *,
        limit: int,
    ) -> ScheduleDueScanResult:
        """公平扫描 bounded due page 并至多 reserve 一个 schedule batch。

        unavailable schedule 只消耗本页一个 scan slot并继续；返回 cursor
        永远等于最后一条实际检查的 entry，而不是未检查的 page 尾部。

        Args:
            scope: 租户范围。
            cursor: process-local active due cursor。
            limit: keyword-only due page 上限。

        Returns:
            reservation/next cursor/inspected count 的闭合扫描结果。

        Raises:
            ScheduleInputError: limit 非法时抛出。
            ScheduleInvariantError: Store page 超界、tenant identity 漂移，
                或持久化 cron/candidate invariant 无法闭合时抛出。
        """

        _require_positive_int(limit, "limit")
        page = self._schedule_store.list_due(scope, cursor, limit=limit)
        if len(page.entries) > limit:
            raise ScheduleInvariantError("schedule_due_page_limit_exceeded")
        inspected_count = 0
        next_due_cursor: ScheduleDueCursor | None = None
        for entry in page.entries:
            inspected_count += 1
            next_due_cursor = entry.cursor_after
            definition = entry.observation.definition
            if definition.tenant_id != scope.tenant_id:
                raise ScheduleInvariantError("schedule_due_tenant_mismatch")
            if not self._job_gateway.is_execution_available(definition.descriptor):
                continue
            batch = _build_due_batch(
                definition,
                entry.observation.database_now,
                max_lookback_seconds=self._schedule_max_lookback_seconds,
                candidate_scan_limit=self._schedule_candidate_scan_limit,
            )
            reservation = self._schedule_store.reserve_occurrences(scope, batch)
            return ScheduleDueScanResult(
                reservation=reservation,
                next_due_cursor=next_due_cursor,
                inspected_count=inspected_count,
            )
        return ScheduleDueScanResult(
            reservation=None,
            next_due_cursor=next_due_cursor,
            inspected_count=inspected_count,
        )

    def materialize_occurrence(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
    ) -> ScheduleMaterializationResult:
        """线性化并完整收口一个 occurrence 的 durable materialization。

        Args:
            scope: 租户范围。
            occurrence_id: 目标 occurrence UUID。

        Returns:
            enqueued/already_enqueued/unavailable/skipped 的闭合结果。

        Raises:
            ScheduleInputError: occurrence ID 非法时抛出。
            ScheduleInvariantError: occurrence 缺失、tenant 漂移、enqueue
                receipt 漂移或 mark 出现 skipped conflict 时抛出。
        """

        if not isinstance(occurrence_id, UUID):
            raise ScheduleInputError("schedule_occurrence_id_invalid")
        observed = self._schedule_store.get_occurrence(scope, occurrence_id)
        if observed is None:
            raise ScheduleInvariantError("schedule_occurrence_missing")
        if observed.tenant_id != scope.tenant_id:
            raise ScheduleInvariantError("schedule_occurrence_tenant_mismatch")

        decision = self._schedule_store.begin_materialization(
            scope,
            occurrence_id,
            admission=self._materialization_admission(observed),
        )
        terminal_result = self._terminal_materialization_result(decision)
        if terminal_result is not None:
            return terminal_result
        return self._enqueue_materialization(scope, occurrence_id, decision)

    def _materialization_admission(
        self,
        occurrence: ScheduleOccurrence,
    ) -> ScheduleMaterializationAdmission:
        """按已观察 occurrence 状态计算 PENDING availability admission。

        Args:
            occurrence: Store 返回的当前 occurrence。

        Returns:
            PENDING availability 或 durable committed replay admission。

        Raises:
            ScheduleInvariantError: PENDING occurrence 缺少 snapshot 时抛出。
        """

        if occurrence.state is not ScheduleOccurrenceState.PENDING:
            return ScheduleMaterializationAdmission.COMMITTED_REPLAY
        if occurrence.snapshot is None:
            raise ScheduleInvariantError("schedule_pending_snapshot_missing")
        if self._job_gateway.is_execution_available(occurrence.snapshot.descriptor):
            return ScheduleMaterializationAdmission.PENDING_AVAILABLE
        return ScheduleMaterializationAdmission.PENDING_UNAVAILABLE

    @staticmethod
    def _terminal_materialization_result(
        decision: ScheduleMaterializationDecision,
    ) -> ScheduleMaterializationResult | None:
        """把非 ENQUEUE Store decision 映射为闭合 Service result。

        Args:
            decision: Store 线性化后的 materialization decision。

        Returns:
            非 ENQUEUE 的闭合 result；ENQUEUE 返回 ``None`` 继续入队。

        Raises:
            ScheduleInvariantError: decision action 不属于闭合集合时抛出。
        """

        if decision.action is ScheduleMaterializationAction.ENQUEUE:
            return None
        result_actions = {
            ScheduleMaterializationAction.UNAVAILABLE: ScheduleMaterializationResultAction.UNAVAILABLE,
            ScheduleMaterializationAction.ALREADY_ENQUEUED: ScheduleMaterializationResultAction.ALREADY_ENQUEUED,
            ScheduleMaterializationAction.SKIPPED: ScheduleMaterializationResultAction.SKIPPED,
        }
        result_action = result_actions.get(decision.action)
        if result_action is None:
            raise ScheduleInvariantError("schedule_materialization_action_invalid")
        return ScheduleMaterializationResult(
            action=result_action,
            occurrence=decision.occurrence,
            enqueue_receipt=None,
        )

    def _enqueue_materialization(
        self,
        scope: TenantScope,
        occurrence_id: UUID,
        decision: ScheduleMaterializationDecision,
    ) -> ScheduleMaterializationResult:
        """执行已持久化 MATERIALIZING commitment 并标记 ENQUEUED。

        Args:
            scope: 租户范围。
            occurrence_id: 目标 occurrence UUID。
            decision: Store 返回的 ENQUEUE decision。

        Returns:
            携带 job enqueue receipt 的 ENQUEUED result。

        Raises:
            ScheduleInvariantError: snapshot、tenant receipt 或 mark 结果漂移时抛出。
        """

        snapshot = decision.occurrence.snapshot
        if snapshot is None:
            raise ScheduleInvariantError("schedule_materializing_snapshot_missing")
        receipt = self._job_gateway.enqueue_committed_schedule_occurrence(
            scope,
            decision,
        )
        if receipt.tenant_id != scope.tenant_id:
            raise ScheduleInvariantError("schedule_enqueue_receipt_tenant_mismatch")
        mark = self._schedule_store.mark_enqueued(
            scope,
            occurrence_id,
            snapshot.request_fingerprint,
            receipt.job_id,
        )
        if mark.action is ScheduleMarkEnqueuedAction.SKIPPED_CONFLICT:
            raise ScheduleInvariantError("schedule_mark_skipped_conflict")
        return ScheduleMaterializationResult(
            action=ScheduleMaterializationResultAction.ENQUEUED,
            occurrence=mark.occurrence,
            enqueue_receipt=receipt,
        )


__all__ = [
    "DURABLE_SCHEDULES_SERVICE_NAME",
    "ScheduleJobGatewayProtocol",
    "ScheduleService",
]
