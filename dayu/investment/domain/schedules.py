"""durable schedule 纯领域模型（Slice 2.2）。

本模块是 schedule/occurrence 的 pure owner（唯一 import 路径），只依赖
标准库、``dayu.investment.domain.identifiers`` 与
``dayu.investment.domain.jobs``，绝不 import Host、Service、Redis、
croniter 或 storage：

- 10 个 closed 状态/决策枚举（``ScheduleState`` / ``ScheduleMisfirePolicy`` /
  ``ScheduleOccurrenceState`` / ``ScheduleSkipReason`` / ``ScheduleReserveAction`` /
  ``ScheduleMaterializationAction`` / ``ScheduleMarkEnqueuedAction`` /
  ``ScheduleMaterializationResultAction`` / ``ScheduleStateTransitionAction`` /
  ``ScheduleMaterializationAdmission``）；
- 5 个稳定错误（消息只含固定 safe code，不携带 cron/payload/path/
  secret）；
- 19 个公开 frozen slots DTO（字段、默认值与跨字段不变量唯一真源）；
- cron 表达式只接受 5 字段 minute-resolution POSIX 形态：拒秒字段、
  昵称（``@``）、随机/hash 扩展与空白漂移；croniter-valid 的进一步
  校验由 ScheduleService cron calculator 承担（croniter 只在 Service
  层 import）；
- timezone 只接受 ``zoneinfo.ZoneInfo`` 可加载的 IANA 名称，禁止固定
  UTC offset 字符串。

安全约束：

- 所有时间为 aware UTC；所有 UUID 由调用方生成；
- 禁止 ``Any``/``object``/``cast``/``type: ignore``/``getattr``/
  ``hasattr``；
- ``CanonicalScheduleEnqueueSnapshot`` 的 ``request_fingerprint`` 只
  调用 ``domain.jobs.job_enqueue_request_fingerprint``，构造期重建
  ``JobEnqueueRequest`` 逐字段闭合验证。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dayu.investment.domain.identifiers import TenantId
from dayu.investment.domain.jobs import (
    CanonicalJobDocument,
    JobEnqueueReceipt,
    JobEnqueueRequest,
    JobHandlerDescriptor,
    job_enqueue_request_fingerprint,
)

_CRON_FIELD_PATTERN = re.compile(r"^[0-9A-Za-z*,/\-]+$")
"""cron 单字段的允许字符集（数字、月份/星期名、``*/-,``）。"""

_FIXED_OFFSET_TIMEZONE_PATTERN = re.compile(r"^(UTC|GMT|Etc/GMT)[+-]?\d|^[A-Za-z]+[+-]\d{1,2}(:\d{2})?$")
"""固定 UTC offset 形态的时间zone名（禁止）。"""

_SHA256_HEX_LENGTH = 64
"""SHA-256 小写十六进制文本的固定长度。"""

_CRON_FIELD_COUNT = 5
"""minute-resolution POSIX cron 的固定字段数。"""

_MAX_RESERVATIONS_PER_BATCH = 3
"""一次 cursor CAS 最多持久化的 occurrence reservation 数。"""


class ScheduleState(str, Enum):
    """schedule definition 状态机状态。"""

    ACTIVE = "active"
    DISABLED = "disabled"


class ScheduleMisfirePolicy(str, Enum):
    """misfire 收敛策略（closed 集合）。"""

    COALESCE_ONE = "coalesce_one"


class ScheduleOccurrenceState(str, Enum):
    """occurrence 状态机状态。"""

    PENDING = "pending"
    MATERIALIZING = "materializing"
    ENQUEUED = "enqueued"
    SKIPPED = "skipped"


class ScheduleSkipReason(str, Enum):
    """occurrence 跳过原因（closed 集合）。

    coalesced 只由 ``coalesced_count`` 表示，不是 skip reason。
    """

    MISFIRE_EXPIRED = "misfire_expired"
    LOOKBACK_EXCEEDED = "lookback_exceeded"
    SCHEDULE_DISABLED = "schedule_disabled"
    CANDIDATE_SCAN_LIMIT_EXCEEDED = "candidate_scan_limit_exceeded"


class ScheduleReserveAction(str, Enum):
    """occurrence reservation 的闭合决策 action。"""

    RESERVED = "reserved"
    LOST_RACE = "lost_race"


class ScheduleMaterializationAction(str, Enum):
    """``begin_materialization`` 的闭合决策 action。"""

    ENQUEUE = "enqueue"
    ALREADY_ENQUEUED = "already_enqueued"
    UNAVAILABLE = "unavailable"
    SKIPPED = "skipped"


class ScheduleMarkEnqueuedAction(str, Enum):
    """``mark_enqueued`` 的闭合决策 action。"""

    MARKED = "marked"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    SKIPPED_CONFLICT = "skipped_conflict"


class ScheduleMaterializationResultAction(str, Enum):
    """``materialize_occurrence`` 的闭合 result action。"""

    ENQUEUED = "enqueued"
    ALREADY_ENQUEUED = "already_enqueued"
    UNAVAILABLE = "unavailable"
    SKIPPED = "skipped"


class ScheduleStateTransitionAction(str, Enum):
    """schedule state CAS 的闭合结果 action。"""

    APPLIED = "applied"
    UNCHANGED = "unchanged"
    CLOCK_STALE = "clock_stale"


class ScheduleMaterializationAdmission(str, Enum):
    """PENDING/MATERIALIZING materialization 的闭合 admission。"""

    PENDING_AVAILABLE = "pending_available"
    PENDING_UNAVAILABLE = "pending_unavailable"
    COMMITTED_REPLAY = "committed_replay"


# ---------------------------------------------------------------------------
# Stable errors
# ---------------------------------------------------------------------------


class ScheduleInputError(ValueError):
    """schedule 输入非法时抛出的稳定错误。"""


class ScheduleVersionConflictError(RuntimeError):
    """schedule CAS 版本/状态/cursor 冲突时抛出的稳定错误。"""


class ScheduleInvariantError(RuntimeError):
    """schedule/occurrence 实现或数据库不变量破坏时抛出的稳定错误。"""


class ScheduleRepositoryError(RuntimeError):
    """schedule 仓储内部失败时抛出的稳定错误（不携带 cause 细节）。"""


class ScheduleExecutionUnavailableError(RuntimeError):
    """本进程无法执行 schedule descriptor 时抛出的稳定错误。"""


# ---------------------------------------------------------------------------
# 私有校验 helper
# ---------------------------------------------------------------------------


def _require_nonempty_text(value: str, label: str) -> None:
    """校验字符串非空且无首尾空白。

    Args:
        value: 待校验字符串。
        label: 错误消息中的中文名称。

    Returns:
        无。

    Raises:
        ScheduleInputError: 值为空、仅空白或含首尾空白时抛出。
    """

    if not isinstance(value, str) or not value or value != value.strip():
        raise ScheduleInputError(f"{label}必须是非空且无首尾空白的字符串")


def _require_positive_int(value: int, label: str) -> None:
    """校验值为精确正整数（拒绝 bool 冒充）。

    Args:
        value: 待校验整数。
        label: 错误消息中的中文名称。

    Returns:
        无。

    Raises:
        ScheduleInputError: 值不是精确 ``int`` 或不大于 0 时抛出。
    """

    if type(value) is not int or value <= 0:
        raise ScheduleInputError(f"{label}必须是正整数")


def _require_nonnegative_int(value: int, label: str) -> None:
    """校验值为精确非负整数（拒绝 bool 冒充）。

    Args:
        value: 待校验整数。
        label: 错误消息中的中文名称。

    Returns:
        无。

    Raises:
        ScheduleInputError: 值不是精确 ``int`` 或小于 0 时抛出。
    """

    if type(value) is not int or value < 0:
        raise ScheduleInputError(f"{label}必须是非负整数")


def _require_uuid(value: UUID, label: str) -> None:
    """校验值为 UUID。

    Args:
        value: 待校验 UUID。
        label: 错误消息中的字段名称。

    Returns:
        无。

    Raises:
        ScheduleInputError: 值不是 UUID 时抛出。
    """

    if not isinstance(value, UUID):
        raise ScheduleInputError(f"{label}必须是 UUID")


def _is_aware_utc(value: datetime) -> bool:
    """判断 datetime 是否为 aware UTC。

    Args:
        value: 待判断的 datetime。

    Returns:
        ``tzinfo`` 非空且 ``utcoffset`` 为 ``timedelta(0)`` 时返回
        ``True``。

    Raises:
        无。
    """

    offset = value.utcoffset()
    return offset is not None and offset == timedelta(0)


def _require_aware_utc(value: datetime, label: str) -> None:
    """校验 datetime 为 aware UTC。

    Args:
        value: 待校验时间。
        label: 错误消息中的中文名称。

    Returns:
        无。

    Raises:
        ScheduleInputError: 时间不是 aware UTC 时抛出。
    """

    if not isinstance(value, datetime) or not _is_aware_utc(value):
        raise ScheduleInputError(f"{label}必须是 aware UTC datetime")


def _require_sha256(value: str, label: str) -> None:
    """校验字符串为小写 64 位 hex SHA-256。

    Args:
        value: 待校验 hash。
        label: 错误消息中的中文名称。

    Returns:
        无。

    Raises:
        ScheduleInputError: 值不是小写 64-hex 时抛出。
    """

    if (
        not isinstance(value, str)
        or len(value) != _SHA256_HEX_LENGTH
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ScheduleInputError(f"{label}必须是小写 64 位 hex SHA-256")


def validate_cron_expression(value: str) -> None:
    """校验 5 字段 minute-resolution POSIX cron 表达式的结构形态。

    只做结构校验（字段数、字符集、无昵称/随机/hash 扩展、无空白漂移）；
    croniter-valid 的进一步校验由 ScheduleService 承担。月份/星期
    名称（JAN-DEC/SUN-SAT）由 croniter 解释，本函数不展开。

    Args:
        value: 待校验的 cron 表达式。

    Returns:
        无。

    Raises:
        ScheduleInputError: 表达式非 5 字段、含非法字符、昵称或
            随机/hash 扩展时抛出。
    """

    _require_nonempty_text(value, "cron_expression")
    if value.startswith("@"):
        raise ScheduleInputError("cron_expression 禁止使用昵称")
    fields = value.split()
    if len(fields) != _CRON_FIELD_COUNT:
        raise ScheduleInputError("cron_expression 必须精确为 5 个字段（分钟 小时 日 月 星期）")
    for field in fields:
        if _CRON_FIELD_PATTERN.fullmatch(field) is None:
            raise ScheduleInputError("cron_expression 含非法字符（禁止 ? L W # H R 与空白漂移）")
        if any(part.upper().startswith(("H", "R")) for part in field.split(",")):
            raise ScheduleInputError("cron_expression 禁止随机/hash 扩展")
    if any(character.isalpha() for character in fields[2]):
        raise ScheduleInputError("cron_expression 日期字段禁止 L/W 扩展")
    if "L" in fields[4].upper():
        raise ScheduleInputError("cron_expression 星期字段禁止 L 扩展")


def validate_timezone_name(value: str) -> None:
    """校验 timezone 为可加载的 IANA 名称（禁止固定 UTC offset 字符串）。

    Args:
        value: 待校验的 timezone 名称。

    Returns:
        无。

    Raises:
        ScheduleInputError: 名称无法加载或为固定 offset 形态时抛出。
    """

    _require_nonempty_text(value, "timezone_name")
    if _FIXED_OFFSET_TIMEZONE_PATTERN.match(value):
        raise ScheduleInputError("timezone_name 禁止使用固定 UTC offset 字符串")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ScheduleInputError("timezone_name 必须是 zoneinfo 可加载的 IANA 名称") from None


# ---------------------------------------------------------------------------
# frozen DTO（19 个公开 DTO）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScheduleRegistrationRequest:
    """新建 schedule definition 的注册请求（总是以 disabled 创建）。

    Args:
        schedule_key: 非空无首尾空白的 schedule 唯一键。
        descriptor: 与 registry 同 ``job_type`` 值逐字段相等的
            descriptor。
        payload: canonical payload document。
        cron_expression: 5 字段 minute-resolution POSIX cron 表达式。
        timezone_name: IANA timezone 名称。
        misfire_policy: misfire 收敛策略（closed 集合）。
        misfire_grace_seconds: 正整数 misfire 宽限秒数。
        job_deadline_seconds: 正整数 job 截止秒数（必须大于 grace）。
    """

    schedule_key: str
    descriptor: JobHandlerDescriptor
    payload: CanonicalJobDocument
    cron_expression: str
    timezone_name: str
    misfire_policy: ScheduleMisfirePolicy
    misfire_grace_seconds: int
    job_deadline_seconds: int

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 任一字段违反不变量时抛出。
        """

        _require_nonempty_text(self.schedule_key, "schedule_key")
        if not isinstance(self.descriptor, JobHandlerDescriptor):
            raise ScheduleInputError("descriptor 必须是 JobHandlerDescriptor")
        if not isinstance(self.payload, CanonicalJobDocument):
            raise ScheduleInputError("payload 必须是 CanonicalJobDocument")
        validate_cron_expression(self.cron_expression)
        validate_timezone_name(self.timezone_name)
        if not isinstance(self.misfire_policy, ScheduleMisfirePolicy):
            raise ScheduleInputError("misfire_policy 必须是 ScheduleMisfirePolicy")
        _require_positive_int(self.misfire_grace_seconds, "misfire_grace_seconds")
        _require_positive_int(self.job_deadline_seconds, "job_deadline_seconds")
        if self.job_deadline_seconds <= self.misfire_grace_seconds:
            raise ScheduleInputError("job_deadline_seconds 必须大于 misfire_grace_seconds")


@dataclass(frozen=True, slots=True)
class ScheduleDefinition:
    """schedule definition 的完整不可变投影。

    Args:
        id: schedule UUID。
        tenant_id: 租户标识。
        schedule_key: 非空唯一键。
        descriptor: 注册时冻结的 descriptor。
        payload: 注册时冻结的 canonical payload。
        cron_expression: 注册时冻结的 cron 表达式。
        timezone_name: 注册时冻结的 IANA timezone 名称。
        misfire_policy: 注册时冻结的 misfire 策略。
        misfire_grace_seconds: 注册时冻结的 grace 秒数。
        job_deadline_seconds: 注册时冻结的 deadline 秒数。
        state: 当前状态（新建总是 disabled）。
        next_fire_at: 可空下一个 fire 的 UTC 时间；新建 disabled draft
            为 ``None``，已运行后 disabled 可保留最后审计 cursor。
        version: 正整数乐观版本；只随 activate/disable/cursor CAS 增加。
        created_at: aware UTC 创建时间。
        updated_at: aware UTC 更新时间。
    """

    id: UUID
    tenant_id: TenantId
    schedule_key: str
    descriptor: JobHandlerDescriptor
    payload: CanonicalJobDocument
    cron_expression: str
    timezone_name: str
    misfire_policy: ScheduleMisfirePolicy
    misfire_grace_seconds: int
    job_deadline_seconds: int
    state: ScheduleState
    next_fire_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 任一字段违反不变量时抛出。
        """

        _require_uuid(self.id, "id")
        _require_nonempty_text(self.schedule_key, "schedule_key")
        if not isinstance(self.tenant_id, TenantId):
            raise ScheduleInputError("tenant_id 必须是 TenantId")
        if not isinstance(self.descriptor, JobHandlerDescriptor):
            raise ScheduleInputError("descriptor 必须是 JobHandlerDescriptor")
        if not isinstance(self.payload, CanonicalJobDocument):
            raise ScheduleInputError("payload 必须是 CanonicalJobDocument")
        validate_cron_expression(self.cron_expression)
        validate_timezone_name(self.timezone_name)
        if not isinstance(self.misfire_policy, ScheduleMisfirePolicy):
            raise ScheduleInputError("misfire_policy 必须是 ScheduleMisfirePolicy")
        _require_positive_int(self.misfire_grace_seconds, "misfire_grace_seconds")
        _require_positive_int(self.job_deadline_seconds, "job_deadline_seconds")
        if self.job_deadline_seconds <= self.misfire_grace_seconds:
            raise ScheduleInputError("job_deadline_seconds 必须大于 misfire_grace_seconds")
        if not isinstance(self.state, ScheduleState):
            raise ScheduleInputError("state 必须是 ScheduleState")
        if self.state is ScheduleState.ACTIVE and self.next_fire_at is None:
            raise ScheduleInputError("active schedule 必须携带 next_fire_at")
        if self.next_fire_at is not None:
            _require_aware_utc(self.next_fire_at, "next_fire_at")
        _require_positive_int(self.version, "version")
        _require_aware_utc(self.created_at, "created_at")
        _require_aware_utc(self.updated_at, "updated_at")


@dataclass(frozen=True, slots=True)
class ScheduleActivationRequest:
    """schedule activate/disable 的 CAS 请求。

    Args:
        schedule_id: 目标 schedule UUID。
        expected_version: 期望版本（CAS 前置）。
        target_state: 目标状态（active/disabled）。
    """

    schedule_id: UUID
    expected_version: int
    target_state: ScheduleState

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 版本/状态非法时抛出。
        """

        _require_uuid(self.schedule_id, "schedule_id")
        _require_positive_int(self.expected_version, "expected_version")
        if not isinstance(self.target_state, ScheduleState):
            raise ScheduleInputError("target_state 必须是 ScheduleState")


@dataclass(frozen=True, slots=True)
class ScheduleObservation:
    """schedule definition 与同一 tenant-scoped PG 事务时钟。

    Args:
        definition: 完整 schedule definition。
        database_now: 同一事务的 PG clock。
    """

    definition: ScheduleDefinition
    database_now: datetime

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 字段非法时抛出。
        """

        if not isinstance(self.definition, ScheduleDefinition):
            raise ScheduleInputError("definition 必须是 ScheduleDefinition")
        _require_aware_utc(self.database_now, "database_now")


def _same_definition_identity(
    previous: ScheduleDefinition,
    current: ScheduleDefinition,
) -> bool:
    """判断两份 definition 的 immutable identity/content 是否完全一致。

    Args:
        previous: 状态转换前 definition。
        current: 状态转换后 definition。

    Returns:
        除 state/cursor/version/updated_at 外字段逐项相等时返回 ``True``。

    Raises:
        无。
    """

    return (
        previous.id == current.id
        and previous.tenant_id == current.tenant_id
        and previous.schedule_key == current.schedule_key
        and previous.descriptor == current.descriptor
        and previous.payload == current.payload
        and previous.cron_expression == current.cron_expression
        and previous.timezone_name == current.timezone_name
        and previous.misfire_policy is current.misfire_policy
        and previous.misfire_grace_seconds == current.misfire_grace_seconds
        and previous.job_deadline_seconds == current.job_deadline_seconds
        and previous.created_at == current.created_at
    )


@dataclass(frozen=True, slots=True)
class ScheduleStateTransitionResult:
    """schedule activate/disable optimistic CAS 的闭合结果。

    Args:
        action: ``applied`` / ``unchanged`` / ``clock_stale``。
        request: 原始 activation 请求；clock stale 重试不得改写版本。
        previous_definition: 事务内锁定的转换前 definition。
        observation: 同一事务返回的转换后 definition 与 PG 时钟。
        activation_next_fire_at: ACTIVE 尝试使用的 candidate；其它动作按
            action 矩阵要求为空或保留该次 stale candidate。
    """

    action: ScheduleStateTransitionAction
    request: ScheduleActivationRequest
    previous_definition: ScheduleDefinition
    observation: ScheduleObservation
    activation_next_fire_at: datetime | None

    def __post_init__(self) -> None:
        """校验 applied/unchanged/clock_stale 的完整状态矩阵。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInvariantError: 任一 before/after/version/state/cursor/
                candidate 组合不符合闭合矩阵时抛出。
        """

        self._validate_fields()
        previous = self.previous_definition
        current = self.observation.definition
        candidate = self.activation_next_fire_at
        self._validate_identity(previous, current)
        if self.action is ScheduleStateTransitionAction.APPLIED:
            self._validate_applied(previous, current, candidate)
            return
        if self.action is ScheduleStateTransitionAction.UNCHANGED:
            self._validate_unchanged(previous, current, candidate)
            return
        self._validate_clock_stale(previous, current, candidate)

    def _validate_fields(self) -> None:
        """校验状态转换结果的字段类型与 candidate 时间。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInvariantError: 字段类型或 candidate 时间非法时抛出。
        """

        if not isinstance(self.action, ScheduleStateTransitionAction):
            raise ScheduleInvariantError("schedule_state_transition_action")
        if not isinstance(self.request, ScheduleActivationRequest):
            raise ScheduleInvariantError("schedule_state_transition_request")
        if not isinstance(self.previous_definition, ScheduleDefinition):
            raise ScheduleInvariantError("schedule_state_transition_previous")
        if not isinstance(self.observation, ScheduleObservation):
            raise ScheduleInvariantError("schedule_state_transition_observation")
        candidate = self.activation_next_fire_at
        if candidate is None:
            return
        try:
            _require_aware_utc(candidate, "activation_next_fire_at")
        except ScheduleInputError as error:
            raise ScheduleInvariantError("schedule_state_transition_candidate") from error

    def _validate_identity(
        self,
        previous: ScheduleDefinition,
        current: ScheduleDefinition,
    ) -> None:
        """校验转换请求与 before/after definition 的稳定身份。

        Args:
            previous: 转换前 definition。
            current: 转换后 definition。

        Returns:
            无。

        Raises:
            ScheduleInvariantError: 身份、版本或不可变字段漂移时抛出。
        """

        request = self.request
        if (
            request.schedule_id != previous.id
            or current.id != previous.id
            or request.expected_version != previous.version
            or not _same_definition_identity(previous, current)
        ):
            raise ScheduleInvariantError("schedule_state_transition_identity")

    def _validate_unchanged(
        self,
        previous: ScheduleDefinition,
        current: ScheduleDefinition,
        candidate: datetime | None,
    ) -> None:
        """校验 unchanged 动作不修改 definition 或 candidate。

        Args:
            previous: 转换前 definition。
            current: 转换后 definition。
            candidate: 必须为空的 activation candidate。

        Returns:
            无。

        Raises:
            ScheduleInvariantError: unchanged 矩阵非法时抛出。
        """

        if candidate is not None or previous != current or previous.state is not self.request.target_state:
            raise ScheduleInvariantError("schedule_state_transition_unchanged")

    def _validate_clock_stale(
        self,
        previous: ScheduleDefinition,
        current: ScheduleDefinition,
        candidate: datetime | None,
    ) -> None:
        """校验 clock-stale 动作只描述已落后 PG 时钟的激活候选。

        Args:
            previous: 转换前 definition。
            current: 未修改的转换后 definition。
            candidate: 已落后数据库时钟的 activation candidate。

        Returns:
            无。

        Raises:
            ScheduleInvariantError: clock-stale 矩阵非法时抛出。
        """

        if (
            self.request.target_state is not ScheduleState.ACTIVE
            or previous.state is not ScheduleState.DISABLED
            or candidate is None
            or candidate > self.observation.database_now
            or previous != current
        ):
            raise ScheduleInvariantError("schedule_state_transition_clock_stale")

    def _validate_applied(
        self,
        previous: ScheduleDefinition,
        current: ScheduleDefinition,
        candidate: datetime | None,
    ) -> None:
        """校验 applied 动作的严格状态转换。

        Args:
            previous: 转换前 definition。
            current: 转换后 definition。
            candidate: ACTIVE candidate 或 ``None``。

        Returns:
            无。

        Raises:
            ScheduleInvariantError: applied 矩阵非法时抛出。
        """

        target = self.request.target_state
        if current.version != previous.version + 1 or current.state is not target:
            raise ScheduleInvariantError("schedule_state_transition_applied_version")
        if target is ScheduleState.ACTIVE:
            if (
                previous.state is not ScheduleState.DISABLED
                or candidate is None
                or candidate <= self.observation.database_now
                or current.next_fire_at != candidate
            ):
                raise ScheduleInvariantError("schedule_state_transition_applied_active")
            return
        if (
            previous.state is not ScheduleState.ACTIVE
            or candidate is not None
            or current.next_fire_at != previous.next_fire_at
        ):
            raise ScheduleInvariantError("schedule_state_transition_applied_disabled")


@dataclass(frozen=True, slots=True)
class ScheduleDueCursor:
    """active due schedule 的 process-local keyset cursor。

    Args:
        next_fire_at: cursor 对应 schedule 的 aware UTC fire 时间。
        schedule_id: cursor 对应 schedule UUID。
    """

    next_fire_at: datetime
    schedule_id: UUID

    def __post_init__(self) -> None:
        """校验 cursor 字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 时间或 UUID 非法时抛出。
        """

        _require_aware_utc(self.next_fire_at, "next_fire_at")
        _require_uuid(self.schedule_id, "schedule_id")


@dataclass(frozen=True, slots=True)
class ScheduleDueEntry:
    """一条 due observation 及其精确 cursor。

    Args:
        observation: active due schedule 与同事务 PG 时钟。
        cursor_after: 必须逐字段等于 definition 的 cursor key。
    """

    observation: ScheduleObservation
    cursor_after: ScheduleDueCursor

    def __post_init__(self) -> None:
        """校验 observation 与 cursor 的逐字段关系。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: entry 不是 active due 或 cursor 不匹配时抛出。
        """

        if not isinstance(self.observation, ScheduleObservation):
            raise ScheduleInputError("observation 必须是 ScheduleObservation")
        if not isinstance(self.cursor_after, ScheduleDueCursor):
            raise ScheduleInputError("cursor_after 必须是 ScheduleDueCursor")
        definition = self.observation.definition
        if (
            definition.state is not ScheduleState.ACTIVE
            or definition.next_fire_at is None
            or definition.next_fire_at > self.observation.database_now
        ):
            raise ScheduleInputError("due entry 必须携带 active 且已到期的 definition")
        if self.cursor_after.next_fire_at != definition.next_fire_at or self.cursor_after.schedule_id != definition.id:
            raise ScheduleInputError("cursor_after 必须与 definition key 逐字段相等")


@dataclass(frozen=True, slots=True)
class ScheduleDuePage:
    """bounded due schedule page。

    Args:
        entries: 本页无重复 due entry tuple。
        next_cursor: 非空页必须等于最后 entry cursor；空页必须为 ``None``。
    """

    entries: tuple[ScheduleDueEntry, ...]
    next_cursor: ScheduleDueCursor | None

    def __post_init__(self) -> None:
        """校验 page 容器、重复项与尾 cursor。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: page 组合非法时抛出。
        """

        if not isinstance(self.entries, tuple):
            raise ScheduleInputError("entries 必须是 tuple")
        seen: set[UUID] = set()
        for entry in self.entries:
            if not isinstance(entry, ScheduleDueEntry):
                raise ScheduleInputError("entries 必须全部是 ScheduleDueEntry")
            schedule_id = entry.observation.definition.id
            if schedule_id in seen:
                raise ScheduleInputError("due page 内 schedule 不得重复")
            seen.add(schedule_id)
        if not self.entries:
            if self.next_cursor is not None:
                raise ScheduleInputError("空 due page 的 next_cursor 必须为 None")
            return
        if self.next_cursor != self.entries[-1].cursor_after:
            raise ScheduleInputError("next_cursor 必须等于最后 entry cursor")


@dataclass(frozen=True, slots=True)
class CanonicalScheduleEnqueueSnapshot:
    """occurrence 冻结的完整 enqueue snapshot。

    只由 persisted schedule + occurrence 构造，严禁 replay clock/jitter；
    ``available_at = scheduled_for``、``deadline_at = scheduled_for +
    job_deadline_seconds``；``request_fingerprint`` 只调用
    ``domain.jobs.job_enqueue_request_fingerprint``。

    Args:
        descriptor: 冻结的 descriptor。
        payload: 冻结的 canonical payload。
        idempotency_key: 非空幂等键。
        available_at: aware UTC 可用时间。
        deadline_at: aware UTC 截止时间（晚于 available）。
        request_fingerprint: 重建 ``JobEnqueueRequest`` 后由唯一算法
            真源计算的 SHA-256。
    """

    descriptor: JobHandlerDescriptor
    payload: CanonicalJobDocument
    idempotency_key: str
    available_at: datetime
    deadline_at: datetime
    request_fingerprint: str

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 任一字段违反不变量时抛出。
        """

        if not isinstance(self.descriptor, JobHandlerDescriptor):
            raise ScheduleInputError("descriptor 必须是 JobHandlerDescriptor")
        if not isinstance(self.payload, CanonicalJobDocument):
            raise ScheduleInputError("payload 必须是 CanonicalJobDocument")
        _require_nonempty_text(self.idempotency_key, "idempotency_key")
        _require_aware_utc(self.available_at, "available_at")
        _require_aware_utc(self.deadline_at, "deadline_at")
        if not self.deadline_at > self.available_at:
            raise ScheduleInputError("deadline_at 必须晚于 available_at")
        _require_sha256(self.request_fingerprint, "request_fingerprint")
        rebuilt = JobEnqueueRequest(
            descriptor=self.descriptor,
            idempotency_key=self.idempotency_key,
            payload=self.payload,
            available_at=self.available_at,
            deadline_at=self.deadline_at,
        )
        if job_enqueue_request_fingerprint(rebuilt) != self.request_fingerprint:
            raise ScheduleInputError("request_fingerprint 与重建的 enqueue 请求不一致")


@dataclass(frozen=True, slots=True)
class ScheduleOccurrenceReservation:
    """Service 计算出的单条 occurrence reservation。

    Args:
        scheduled_for: aware UTC 计划 fire 时间（candidate）。
        state: 初始状态（``pending`` 或 ``skipped``）。
        snapshot: pending 必为完整 snapshot；skipped audit 为 ``None``。
        coalesced_count: 可空 coalesced 组大小减一；lookback/scan-limit
            audit 为 ``None``，其余为 exact nonnegative int。
        skip_reason: pending 为 ``None``；skipped 必非空。
    """

    scheduled_for: datetime
    state: ScheduleOccurrenceState
    snapshot: CanonicalScheduleEnqueueSnapshot | None
    coalesced_count: int | None
    skip_reason: ScheduleSkipReason | None

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 状态/snapshot/count/reason 组合非法时
                抛出。
        """

        _require_aware_utc(self.scheduled_for, "scheduled_for")
        if not isinstance(self.state, ScheduleOccurrenceState):
            raise ScheduleInputError("state 必须是 ScheduleOccurrenceState")
        if self.snapshot is not None and not isinstance(
            self.snapshot,
            CanonicalScheduleEnqueueSnapshot,
        ):
            raise ScheduleInputError("snapshot 必须是 CanonicalScheduleEnqueueSnapshot 或 None")
        if self.skip_reason is not None and not isinstance(
            self.skip_reason,
            ScheduleSkipReason,
        ):
            raise ScheduleInputError("skip_reason 必须是 ScheduleSkipReason 或 None")
        if self.state is ScheduleOccurrenceState.PENDING:
            self._validate_pending()
            return
        if self.state is ScheduleOccurrenceState.SKIPPED:
            self._validate_skipped()
            return
        raise ScheduleInputError("reservation state 只允许 pending/skipped")

    def _validate_pending(self) -> None:
        """校验 PENDING reservation 的 snapshot 与 coalesced 字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: PENDING reservation 不变量非法时抛出。
        """

        if self.snapshot is None:
            raise ScheduleInputError("pending reservation 必须携带 snapshot")
        if self.skip_reason is not None:
            raise ScheduleInputError("pending reservation 不得携带 skip_reason")
        if self.coalesced_count is None:
            raise ScheduleInputError("pending reservation 必须携带 exact nonnegative coalesced_count")
        _require_nonnegative_int(self.coalesced_count, "coalesced_count")
        if self.snapshot.available_at != self.scheduled_for:
            raise ScheduleInputError("pending reservation 的 snapshot.available_at 必须等于 scheduled_for")

    def _validate_skipped(self) -> None:
        """校验 SKIPPED reservation 的 reason-specific 字段矩阵。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: SKIPPED reservation 不变量非法时抛出。
        """

        if self.skip_reason is None:
            raise ScheduleInputError("skipped reservation 必须携带 skip_reason")
        if self.skip_reason is ScheduleSkipReason.SCHEDULE_DISABLED:
            self._validate_schedule_disabled()
            return
        if self.snapshot is not None:
            raise ScheduleInputError("skipped audit reservation 不得携带 snapshot")
        if self.skip_reason is ScheduleSkipReason.MISFIRE_EXPIRED:
            if self.coalesced_count is None:
                raise ScheduleInputError("misfire_expired audit 必须携带 exact nonnegative coalesced_count")
            _require_nonnegative_int(self.coalesced_count, "coalesced_count")
            return
        if self.coalesced_count is not None:
            raise ScheduleInputError("lookback/scan-limit audit 的 coalesced_count 必须为 None")

    def _validate_schedule_disabled(self) -> None:
        """校验 schedule-disabled reservation 保留的完整 snapshot。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: snapshot 或 coalesced count 非法时抛出。
        """

        if self.snapshot is None:
            raise ScheduleInputError("schedule_disabled reservation 必须保留 snapshot")
        if self.snapshot.available_at != self.scheduled_for:
            raise ScheduleInputError("schedule_disabled snapshot.available_at 必须等于 scheduled_for")
        if self.coalesced_count is None:
            raise ScheduleInputError("schedule_disabled reservation 必须携带 exact nonnegative coalesced_count")
        _require_nonnegative_int(self.coalesced_count, "coalesced_count")


@dataclass(frozen=True, slots=True)
class ScheduleReservationBatch:
    """一次 reserve 事务内要插入的完整 occurrence batch。

    Args:
        schedule_id: 目标 schedule UUID。
        expected_version: reserve 时的 schedule CAS 版本。
        expected_next_fire_at: reserve 前持久化 cursor。
        resulting_state: 本次成功 CAS 后的显式 schedule state。
        resulting_next_fire_at: 本次成功 CAS 后的显式 cursor。
        reservations: 1 至 3 条 reservation（过期/eligible/skipped
            audit 组合）。
    """

    schedule_id: UUID
    expected_version: int
    expected_next_fire_at: datetime
    resulting_state: ScheduleState
    resulting_next_fire_at: datetime
    reservations: tuple[ScheduleOccurrenceReservation, ...]

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: batch 含 0 条或 4+ 条 reservation、版本
                或 cursor 非法时抛出。
            ScheduleInvariantError: reservations 的 ``scheduled_for``
                出现重复自然键时抛出。
        """

        _require_uuid(self.schedule_id, "schedule_id")
        _require_positive_int(self.expected_version, "expected_version")
        _require_aware_utc(self.expected_next_fire_at, "expected_next_fire_at")
        if not isinstance(self.resulting_state, ScheduleState):
            raise ScheduleInputError("resulting_state 必须是 ScheduleState")
        _require_aware_utc(self.resulting_next_fire_at, "resulting_next_fire_at")
        self._validate_reservations()
        if self.resulting_state is ScheduleState.ACTIVE:
            self._validate_active()
            return
        self._validate_disabled()

    def _validate_reservations(self) -> None:
        """校验 reservation 容器、元素类型与自然键唯一性。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 容器、数量或元素类型非法时抛出。
            ScheduleInvariantError: ``scheduled_for`` 自然键重复时抛出。
        """

        if not isinstance(self.reservations, tuple):
            raise ScheduleInputError("reservations 必须是 tuple")
        if not 1 <= len(self.reservations) <= _MAX_RESERVATIONS_PER_BATCH:
            raise ScheduleInputError("reservations 必须包含 1 至 3 条")
        for reservation in self.reservations:
            if not isinstance(reservation, ScheduleOccurrenceReservation):
                raise ScheduleInputError("reservations 必须全部是 ScheduleOccurrenceReservation")
        scheduled_for_values = tuple(reservation.scheduled_for for reservation in self.reservations)
        if len(set(scheduled_for_values)) != len(scheduled_for_values):
            raise ScheduleInvariantError("schedule_batch_duplicate_scheduled_for")

    def _validate_active(self) -> None:
        """校验 ACTIVE batch 严格推进 cursor 且不含 scan-limit audit。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: ACTIVE batch 状态矩阵非法时抛出。
        """

        if self.resulting_next_fire_at <= self.expected_next_fire_at:
            raise ScheduleInputError("active batch 必须严格推进 resulting cursor")
        if any(
            reservation.skip_reason is ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED
            for reservation in self.reservations
        ):
            raise ScheduleInputError("active batch 不得携带 scan-limit audit")

    def _validate_disabled(self) -> None:
        """校验 DISABLED scan-limit batch 的 cursor 与 audit 集合。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: DISABLED batch 状态矩阵非法时抛出。
        """

        if self.resulting_next_fire_at != self.expected_next_fire_at:
            raise ScheduleInputError("scan-limit batch 必须保留 expected cursor")
        scan_limit_count = sum(
            reservation.skip_reason is ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED
            for reservation in self.reservations
        )
        if scan_limit_count != 1:
            raise ScheduleInputError("disabled batch 必须含唯一 scan-limit audit")
        if any(
            reservation.state is not ScheduleOccurrenceState.SKIPPED
            or reservation.skip_reason
            not in (
                ScheduleSkipReason.LOOKBACK_EXCEEDED,
                ScheduleSkipReason.CANDIDATE_SCAN_LIMIT_EXCEEDED,
            )
            for reservation in self.reservations
        ):
            raise ScheduleInputError("scan-limit batch 只允许 lookback/scan-limit audit")


@dataclass(frozen=True, slots=True)
class ScheduleReservationResult:
    """``reserve_occurrences`` 的闭合结果。

    Args:
        action: ``reserved`` 或 ``lost_race``。
        occurrences: reserved 时非空（已持久化 occurrence）；lost_race
            时为空 tuple（零 mutation）。
    """

    action: ScheduleReserveAction
    occurrences: tuple[ScheduleOccurrence, ...]

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: action/occurrences 组合非法时抛出。
        """

        if not isinstance(self.action, ScheduleReserveAction):
            raise ScheduleInputError("action 必须是 ScheduleReserveAction")
        if not isinstance(self.occurrences, tuple):
            raise ScheduleInputError("occurrences 必须是 tuple")
        if self.action is ScheduleReserveAction.RESERVED and not self.occurrences:
            raise ScheduleInputError("reserved 结果必须携带非空 occurrences")
        if self.action is ScheduleReserveAction.LOST_RACE and self.occurrences:
            raise ScheduleInputError("lost_race 结果必须携带空 occurrences")
        for occurrence in self.occurrences:
            if not isinstance(occurrence, ScheduleOccurrence):
                raise ScheduleInputError("occurrences 必须全部是 ScheduleOccurrence")


@dataclass(frozen=True, slots=True)
class ScheduleDueScanResult:
    """ScheduleService 对 bounded due page 的闭合扫描结果。

    Args:
        reservation: 找到首个本进程可执行 schedule 后的单次 reservation
            结果；整页不可执行或空页时为 ``None``。
        next_due_cursor: 最后一条已检查 entry 的 cursor；空页为 ``None``。
        inspected_count: 实际检查的 page 前缀长度。
    """

    reservation: ScheduleReservationResult | None
    next_due_cursor: ScheduleDueCursor | None
    inspected_count: int

    def __post_init__(self) -> None:
        """校验扫描结果的空页与非空页矩阵。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: count/cursor/reservation 组合非法时抛出。
        """

        _require_nonnegative_int(self.inspected_count, "inspected_count")
        if self.reservation is not None and not isinstance(
            self.reservation,
            ScheduleReservationResult,
        ):
            raise ScheduleInputError("reservation 必须是 ScheduleReservationResult 或 None")
        if self.next_due_cursor is not None and not isinstance(
            self.next_due_cursor,
            ScheduleDueCursor,
        ):
            raise ScheduleInputError("next_due_cursor 必须是 ScheduleDueCursor 或 None")
        if self.inspected_count == 0:
            if self.reservation is not None or self.next_due_cursor is not None:
                raise ScheduleInputError("空 due scan 必须是零 count/无 cursor/无 reservation")
            return
        if self.next_due_cursor is None:
            raise ScheduleInputError("非空 due scan 必须携带 next_due_cursor")


@dataclass(frozen=True, slots=True)
class ScheduleOccurrence:
    """occurrence 的完整不可变投影。

    Args:
        id: occurrence UUID。
        tenant_id: 租户标识。
        schedule_id: 父 schedule UUID。
        schedule_version: 创建时的 schedule 版本。
        scheduled_for: aware UTC 计划 fire 时间。
        state: 当前状态。
        snapshot: pending/materializing/enqueued 及 schedule_disabled
            必为完整 snapshot；其它 skipped audit 为 ``None``。
        job_id: 可空绑定 job UUID（enqueued 必非空）。
        coalesced_count: 可空 coalesced 组大小减一。
        skip_reason: 可空跳过原因。
        created_at: aware UTC 创建时间。
        updated_at: aware UTC 更新时间。
    """

    id: UUID
    tenant_id: TenantId
    schedule_id: UUID
    schedule_version: int
    scheduled_for: datetime
    state: ScheduleOccurrenceState
    snapshot: CanonicalScheduleEnqueueSnapshot | None
    job_id: UUID | None
    coalesced_count: int | None
    skip_reason: ScheduleSkipReason | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 状态/snapshot/job/reason 组合非法时抛出。
        """

        self._validate_fields()
        if self.state in (
            ScheduleOccurrenceState.PENDING,
            ScheduleOccurrenceState.MATERIALIZING,
        ):
            self._validate_pending_or_materializing()
            return
        if self.state is ScheduleOccurrenceState.ENQUEUED:
            self._validate_enqueued()
            return
        if self.state is ScheduleOccurrenceState.SKIPPED:
            self._validate_skipped()
            return
        raise ScheduleInputError("occurrence state 非法")

    def _validate_fields(self) -> None:
        """校验 occurrence 的基础字段类型与时间。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 基础字段类型或时间非法时抛出。
        """

        _require_uuid(self.id, "id")
        if not isinstance(self.tenant_id, TenantId):
            raise ScheduleInputError("tenant_id 必须是 TenantId")
        _require_uuid(self.schedule_id, "schedule_id")
        if not isinstance(self.state, ScheduleOccurrenceState):
            raise ScheduleInputError("state 必须是 ScheduleOccurrenceState")
        if self.snapshot is not None and not isinstance(
            self.snapshot,
            CanonicalScheduleEnqueueSnapshot,
        ):
            raise ScheduleInputError("snapshot 必须是 CanonicalScheduleEnqueueSnapshot 或 None")
        if self.job_id is not None:
            _require_uuid(self.job_id, "job_id")
        if self.skip_reason is not None and not isinstance(
            self.skip_reason,
            ScheduleSkipReason,
        ):
            raise ScheduleInputError("skip_reason 必须是 ScheduleSkipReason 或 None")
        _require_positive_int(self.schedule_version, "schedule_version")
        _require_aware_utc(self.scheduled_for, "scheduled_for")
        _require_aware_utc(self.created_at, "created_at")
        _require_aware_utc(self.updated_at, "updated_at")

    def _validate_pending_or_materializing(self) -> None:
        """校验 PENDING/MATERIALIZING occurrence 的字段矩阵。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 状态字段组合非法时抛出。
        """

        if self.job_id is not None or self.skip_reason is not None:
            raise ScheduleInputError("pending/materializing occurrence 不得携带 job_id 或 skip_reason")
        if self.snapshot is None:
            raise ScheduleInputError("pending/materializing occurrence 必须携带完整 snapshot")
        self._validate_snapshot_schedule()
        self._validate_coalesced_count()

    def _validate_enqueued(self) -> None:
        """校验 ENQUEUED occurrence 的 job 与 snapshot 字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: ENQUEUED 字段组合非法时抛出。
        """

        if self.job_id is None or self.skip_reason is not None or self.snapshot is None:
            raise ScheduleInputError("enqueued occurrence 必须携带 job_id 与完整 snapshot 且无 skip_reason")
        self._validate_snapshot_schedule()
        self._validate_coalesced_count()

    def _validate_skipped(self) -> None:
        """校验 SKIPPED occurrence 的 reason-specific 字段矩阵。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: SKIPPED 字段组合非法时抛出。
        """

        if self.job_id is not None or self.skip_reason is None:
            raise ScheduleInputError("skipped occurrence 必须携带 skip_reason 且无 job_id")
        if self.skip_reason is ScheduleSkipReason.SCHEDULE_DISABLED:
            if self.snapshot is None:
                raise ScheduleInputError("schedule_disabled occurrence 必须保留完整 snapshot")
            self._validate_snapshot_schedule()
            self._validate_coalesced_count()
        elif self.snapshot is not None:
            raise ScheduleInputError("非 schedule_disabled 的 skipped occurrence 不得携带 snapshot")
        if self.skip_reason is ScheduleSkipReason.MISFIRE_EXPIRED:
            self._validate_coalesced_count()
        elif self.skip_reason is not ScheduleSkipReason.SCHEDULE_DISABLED and self.coalesced_count is not None:
            raise ScheduleInputError("lookback/scan-limit audit 的 coalesced_count 必须为 None")

    def _validate_coalesced_count(self) -> None:
        """校验 coalesced_count 为 exact nonnegative int。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: coalesced_count 非法时抛出。
        """

        if self.coalesced_count is None:
            raise ScheduleInputError("该状态必须携带 exact nonnegative coalesced_count")
        _require_nonnegative_int(self.coalesced_count, "coalesced_count")

    def _validate_snapshot_schedule(self) -> None:
        """校验冻结 snapshot 的 available_at 与 occurrence fire 相等。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: snapshot 缺失或时间不等时抛出。
        """

        if self.snapshot is None or self.snapshot.available_at != self.scheduled_for:
            raise ScheduleInputError("snapshot.available_at 必须等于 scheduled_for")


@dataclass(frozen=True, slots=True)
class ScheduleReplayCursor:
    """PENDING replay 的 process-local keyset cursor。

    Args:
        scheduled_for: cursor 对应 occurrence 的 aware UTC fire 时间。
        occurrence_id: cursor 对应 occurrence UUID。
    """

    scheduled_for: datetime
    occurrence_id: UUID

    def __post_init__(self) -> None:
        """校验 replay cursor 字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: 时间或 UUID 非法时抛出。
        """

        _require_aware_utc(self.scheduled_for, "scheduled_for")
        _require_uuid(self.occurrence_id, "occurrence_id")


@dataclass(frozen=True, slots=True)
class ScheduleReplayPage:
    """MATERIALIZING-first、PENDING-keyset 的 bounded replay page。

    Args:
        occurrences: 无重复 PENDING/MATERIALIZING occurrence tuple；全部
            MATERIALIZING 必须严格排在 PENDING 前。
        next_pending_cursor: 最后一条选中 PENDING 的 key；未选 PENDING 时
            可保持输入 cursor，确认全局无 PENDING 时为 ``None``。
    """

    occurrences: tuple[ScheduleOccurrence, ...]
    next_pending_cursor: ScheduleReplayCursor | None

    def __post_init__(self) -> None:
        """校验 replay page 的状态、顺序、重复项与 PENDING cursor。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: page 组合非法时抛出。
        """

        if not isinstance(self.occurrences, tuple):
            raise ScheduleInputError("occurrences 必须是 tuple")
        if self.next_pending_cursor is not None and not isinstance(
            self.next_pending_cursor,
            ScheduleReplayCursor,
        ):
            raise ScheduleInputError("next_pending_cursor 必须是 ScheduleReplayCursor 或 None")
        last_pending = self._validate_occurrences()
        if last_pending is not None:
            expected_cursor = ScheduleReplayCursor(
                scheduled_for=last_pending.scheduled_for,
                occurrence_id=last_pending.id,
            )
            if self.next_pending_cursor != expected_cursor:
                raise ScheduleInputError("next_pending_cursor 必须等于最后 PENDING occurrence key")

    def _validate_occurrences(self) -> ScheduleOccurrence | None:
        """校验 replay occurrence 的身份、状态及分段顺序。

        Args:
            无。

        Returns:
            最后一条 PENDING occurrence；页内无 PENDING 时返回 ``None``。

        Raises:
            ScheduleInputError: occurrence 重复、类型、状态或顺序非法时抛出。
        """

        seen: set[UUID] = set()
        pending_seen = False
        last_pending: ScheduleOccurrence | None = None
        for occurrence in self.occurrences:
            if not isinstance(occurrence, ScheduleOccurrence):
                raise ScheduleInputError("occurrences 必须全部是 ScheduleOccurrence")
            if occurrence.id in seen:
                raise ScheduleInputError("replay page 内 occurrence 不得重复")
            seen.add(occurrence.id)
            if occurrence.state is ScheduleOccurrenceState.PENDING:
                pending_seen = True
                last_pending = occurrence
            elif occurrence.state is ScheduleOccurrenceState.MATERIALIZING:
                if pending_seen:
                    raise ScheduleInputError("MATERIALIZING 必须严格排在 PENDING 前")
            else:
                raise ScheduleInputError("replay page 只允许 PENDING/MATERIALIZING")
        return last_pending


@dataclass(frozen=True, slots=True)
class ScheduleMaterializationDecision:
    """``begin_materialization`` 的闭合决策。

    Args:
        action: ``enqueue`` / ``already_enqueued`` / ``unavailable`` /
            ``skipped``。
        occurrence: 决策对应的 occurrence 快照。
    """

    action: ScheduleMaterializationAction
    occurrence: ScheduleOccurrence

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: action/occurrence 组合非法时抛出。
        """

        if not isinstance(self.action, ScheduleMaterializationAction):
            raise ScheduleInputError("action 必须是 ScheduleMaterializationAction")
        if not isinstance(self.occurrence, ScheduleOccurrence):
            raise ScheduleInputError("occurrence 必须是 ScheduleOccurrence")
        expected_state = {
            ScheduleMaterializationAction.ENQUEUE: ScheduleOccurrenceState.MATERIALIZING,
            ScheduleMaterializationAction.ALREADY_ENQUEUED: ScheduleOccurrenceState.ENQUEUED,
            ScheduleMaterializationAction.UNAVAILABLE: ScheduleOccurrenceState.PENDING,
            ScheduleMaterializationAction.SKIPPED: ScheduleOccurrenceState.SKIPPED,
        }[self.action]
        if self.occurrence.state is not expected_state:
            raise ScheduleInputError("materialization decision action/state 组合非法")


@dataclass(frozen=True, slots=True)
class ScheduleMarkEnqueuedResult:
    """``mark_enqueued`` 的闭合结果。

    Args:
        action: ``marked`` / ``idempotent_replay`` / ``skipped_conflict``。
        occurrence: 结果对应的 occurrence。
    """

    action: ScheduleMarkEnqueuedAction
    occurrence: ScheduleOccurrence

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: action/occurrence 组合非法时抛出。
        """

        if not isinstance(self.action, ScheduleMarkEnqueuedAction):
            raise ScheduleInputError("action 必须是 ScheduleMarkEnqueuedAction")
        if not isinstance(self.occurrence, ScheduleOccurrence):
            raise ScheduleInputError("occurrence 必须是 ScheduleOccurrence")
        if self.action in (
            ScheduleMarkEnqueuedAction.MARKED,
            ScheduleMarkEnqueuedAction.IDEMPOTENT_REPLAY,
        ):
            if self.occurrence.state is not ScheduleOccurrenceState.ENQUEUED:
                raise ScheduleInputError("marked/idempotent_replay 必须返回 ENQUEUED")
            return
        if self.occurrence.state is not ScheduleOccurrenceState.SKIPPED:
            raise ScheduleInputError("skipped_conflict 必须返回 SKIPPED")


@dataclass(frozen=True, slots=True)
class ScheduleMaterializationResult:
    """``materialize_occurrence`` 的闭合结果。

    Args:
        action: ``enqueued`` / ``already_enqueued`` / ``unavailable`` /
            ``skipped``。
        occurrence: 结果对应的 occurrence。
        enqueue_receipt: ``enqueued`` 必非空且 job_id 与 occurrence
            逐字段一致；其它 action 必为 ``None``。
    """

    action: ScheduleMaterializationResultAction
    occurrence: ScheduleOccurrence
    enqueue_receipt: JobEnqueueReceipt | None

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: action/receipt/occurrence 组合非法时抛出。
        """

        if not isinstance(self.action, ScheduleMaterializationResultAction):
            raise ScheduleInputError("action 必须是 ScheduleMaterializationResultAction")
        if not isinstance(self.occurrence, ScheduleOccurrence):
            raise ScheduleInputError("occurrence 必须是 ScheduleOccurrence")
        if self.enqueue_receipt is not None and not isinstance(
            self.enqueue_receipt,
            JobEnqueueReceipt,
        ):
            raise ScheduleInputError("enqueue_receipt 必须是 JobEnqueueReceipt 或 None")
        if self.action is ScheduleMaterializationResultAction.ENQUEUED:
            self._validate_enqueued()
            return
        self._validate_non_enqueued()

    def _validate_enqueued(self) -> None:
        """校验 ENQUEUED result 的 receipt 与 occurrence 绑定。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: receipt 缺失或 job ID 漂移时抛出。
        """

        if self.enqueue_receipt is None:
            raise ScheduleInputError("enqueued 结果必须携带 enqueue_receipt")
        if self.occurrence.job_id != self.enqueue_receipt.job_id:
            raise ScheduleInputError("enqueued 结果的 receipt job_id 必须与 occurrence 一致")

    def _validate_non_enqueued(self) -> None:
        """校验非 ENQUEUED result 的空 receipt 与目标状态。

        Args:
            无。

        Returns:
            无。

        Raises:
            ScheduleInputError: receipt 或 action/state 组合非法时抛出。
        """

        if self.enqueue_receipt is not None:
            raise ScheduleInputError("非 enqueued 结果不得携带 enqueue_receipt")
        if self.action is ScheduleMaterializationResultAction.ALREADY_ENQUEUED:
            if self.occurrence.state is not ScheduleOccurrenceState.ENQUEUED:
                raise ScheduleInputError("already_enqueued 结果的 occurrence 必须为 ENQUEUED")
        elif self.action is ScheduleMaterializationResultAction.UNAVAILABLE:
            if self.occurrence.state is not ScheduleOccurrenceState.PENDING:
                raise ScheduleInputError("unavailable 结果的 occurrence 必须为 PENDING")
        elif self.occurrence.state is not ScheduleOccurrenceState.SKIPPED:
            raise ScheduleInputError("skipped 结果的 occurrence 必须为 SKIPPED")


__all__ = [
    "CanonicalScheduleEnqueueSnapshot",
    "ScheduleActivationRequest",
    "ScheduleDefinition",
    "ScheduleDueCursor",
    "ScheduleDueEntry",
    "ScheduleDuePage",
    "ScheduleDueScanResult",
    "ScheduleExecutionUnavailableError",
    "ScheduleInputError",
    "ScheduleInvariantError",
    "ScheduleMarkEnqueuedAction",
    "ScheduleMarkEnqueuedResult",
    "ScheduleMaterializationAction",
    "ScheduleMaterializationAdmission",
    "ScheduleMaterializationDecision",
    "ScheduleMaterializationResult",
    "ScheduleMaterializationResultAction",
    "ScheduleMisfirePolicy",
    "ScheduleObservation",
    "ScheduleOccurrence",
    "ScheduleOccurrenceReservation",
    "ScheduleOccurrenceState",
    "ScheduleRegistrationRequest",
    "ScheduleReplayCursor",
    "ScheduleReplayPage",
    "ScheduleRepositoryError",
    "ScheduleReservationBatch",
    "ScheduleReservationResult",
    "ScheduleReserveAction",
    "ScheduleSkipReason",
    "ScheduleState",
    "ScheduleStateTransitionAction",
    "ScheduleStateTransitionResult",
    "ScheduleVersionConflictError",
    "validate_cron_expression",
    "validate_timezone_name",
]
