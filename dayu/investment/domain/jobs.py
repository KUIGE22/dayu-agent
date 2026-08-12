"""durable job 纯领域模型。

本模块是 Slice 2.1 durable job queue 的 pure owner（唯一 import 路径），
只依赖标准库与既有 ``dayu.investment.domain.identifiers``，绝不 import
Host、contracts 或 storage：

- 11 个 closed 状态/决策枚举；
- 15 个公开 frozen slots DTO（字段、默认值与跨字段不变量唯一真源）；
- 8 个稳定错误（消息只含固定 safe code）；
- ``CanonicalJobDocument`` 的唯一 canonical 编码/解析与敏感键拒绝；
- generic / Host-origin attempt receipt builder 与 golden schema 常量。

安全约束：

- 所有时间为 aware UTC；所有 UUID 由调用方生成；
- 禁止 ``Any``/``object``/``cast``/``type: ignore``/``getattr``/
  ``hasattr``；无 metadata/dict 逃逸口；
- canonical document 拒绝 float/NaN/Infinity、重复 key、非紧凑分隔符
  与 closed 敏感键集合；日志/metrics 只写 ID、state、safe code、长度
  与 hash。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import NoReturn, Protocol, TypeAlias
from uuid import UUID

from dayu.investment.domain.identifiers import TenantId

JsonScalar: TypeAlias = str | int | bool | None
"""canonical JSON 标量（float/NaN/Infinity 一律拒绝）。"""

JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
"""canonical JSON 递归值（plain list/dict）。"""

_SENSITIVE_KEY_SET: frozenset[str] = frozenset({"password", "secret", "token", "authorization", "cookie", "api_key"})
"""canonical document 递归拒绝的 closed 敏感键集合。"""


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------


class JobState(str, Enum):
    """job 状态机状态。"""

    READY = "ready"
    LEASED = "leased"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptState(str, Enum):
    """attempt 状态机状态。"""

    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"


class CorrelationState(str, Enum):
    """agent run correlation 状态机状态。"""

    RESERVED = "reserved"
    HOST_CREATED = "host_created"
    HOST_RUNNING = "host_running"
    HOST_SUCCEEDED = "host_succeeded"
    HOST_FAILED = "host_failed"
    HOST_CANCELLED = "host_cancelled"
    HOST_UNSETTLED = "host_unsettled"


class JobDefinitionState(str, Enum):
    """job definition 状态。"""

    ACTIVE = "active"
    DISABLED = "disabled"


class JobHeartbeatAction(str, Enum):
    """heartbeat 的闭合决策 action（Slice 2.2）。

    ``renewed`` 表示 generic job 正常续约；``governance_required`` 表示
    同事务发现未终结 Agent correlation，续约同一 lease/fence 后必须由
    Worker 转 governance/reobserve，绝不再走 generic terminal 优先级。
    """

    RENEWED = "renewed"
    GOVERNANCE_REQUIRED = "governance_required"


class AttemptReceiptOutcome(str, Enum):
    """attempt receipt 的唯一业务 outcome。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenericAttemptReceiptReason(str, Enum):
    """generic attempt receipt 的 closed reason（只允许本集合值）。"""

    COMPLETION = "completion"
    FAILURE = "failure"
    CANCEL_INTENT = "cancel_intent"
    DEADLINE = "deadline"
    LEASE_EXPIRED = "lease_expired"


class LeaseReleaseReason(str, Enum):
    """lease 释放原因（``job_leases.release_reason`` 只允许本集合值）。"""

    COMPLETION = "completion"
    FAILURE = "failure"
    CANCEL_INTENT = "cancel_intent"
    DEADLINE = "deadline"
    LEASE_EXPIRED = "lease_expired"


class HostRunObservationState(str, Enum):
    """Host ``RunState`` 的闭合、安全投影（绝不 import ``RunState``）。

    映射规则（仅 Service 内 strict mapping）：Host record 不存在 ->
    ``missing``；``RunState.CREATED/QUEUED/RUNNING/SUCCEEDED/FAILED/
    CANCELLED/UNSETTLED`` 一一映射到同名 lowercase observation state。
    """

    MISSING = "missing"
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNSETTLED = "unsettled"


class SafeJobErrorCode(str, Enum):
    """job 失败的安全错误码（无 payload/exception/stack 逃逸）。"""

    CANCELLED = "cancelled"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    LEASE_EXPIRED = "lease_expired"
    RETRY_EXHAUSTED = "retry_exhausted"
    HANDLER_REJECTED = "handler_rejected"
    HOST_RUN_FAILED = "host_run_failed"
    HOST_RUN_CANCELLED = "host_run_cancelled"
    HOST_RUN_UNSETTLED = "host_run_unsettled"
    CORRELATION_MISSING = "correlation_missing"
    CORRELATION_INVARIANT = "correlation_invariant"
    CORRELATION_STALE_ATTEMPT = "correlation_stale_attempt"
    REPOSITORY_FAILURE = "repository_failure"
    SOURCE_INVALID = "source_invalid"
    SOURCE_OPERATION_BUSY = "source_operation_busy"
    SOURCE_INTERRUPTED = "source_interrupted"


class AgentRunStartAuthorizationAction(str, Enum):
    """live start authorization 的闭合决策 action。"""

    START_REQUIRED = "START_REQUIRED"
    WAIT = "WAIT"
    CANCEL = "CANCEL"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    LEASE_LOST = "LEASE_LOST"
    INVARIANT_FAILURE = "INVARIANT_FAILURE"


class AgentRunTerminalReconciliationAction(str, Enum):
    """tokenless terminal-only reconciliation 的闭合决策 action。"""

    TERMINALIZED_SUCCESS = "TERMINALIZED_SUCCESS"
    TERMINALIZED_FAILURE = "TERMINALIZED_FAILURE"
    TERMINALIZED_CANCEL = "TERMINALIZED_CANCEL"
    ALREADY_TERMINALIZED_SUCCESS = "ALREADY_TERMINALIZED_SUCCESS"
    ALREADY_TERMINALIZED_FAILURE = "ALREADY_TERMINALIZED_FAILURE"
    ALREADY_TERMINALIZED_CANCEL = "ALREADY_TERMINALIZED_CANCEL"
    NO_HOST_RUN = "NO_HOST_RUN"
    HOST_ACTIVE_WAIT = "HOST_ACTIVE_WAIT"
    STALE_ATTEMPT = "STALE_ATTEMPT"
    ALREADY_STALE_ATTEMPT = "ALREADY_STALE_ATTEMPT"
    INVARIANT_FAILURE = "INVARIANT_FAILURE"


# ---------------------------------------------------------------------------
# Stable errors
# ---------------------------------------------------------------------------


class JobInputError(ValueError):
    """job 输入非法时抛出的稳定错误。"""


class JobNotFoundError(RuntimeError):
    """目标租户内 job/correlation 不存在时抛出的稳定错误。

    跨租户访问同样表现为 not-found，不泄漏目标存在性。
    """


class JobIdempotencyConflictError(RuntimeError):
    """同 idempotency key 不同 fingerprint 时抛出的稳定错误。"""


class JobLeaseLostError(RuntimeError):
    """lease 已失效或 fence/token 不匹配时抛出的稳定错误。"""


class JobStateConflictError(RuntimeError):
    """job 状态与操作冲突（如 cancel intent 已立）时抛出的稳定错误。"""


class JobDeadlineExceededError(RuntimeError):
    """有效 lease 命中 deadline 且已收敛为 failed 时抛出的稳定错误。"""


class JobCorrelationInvariantError(RuntimeError):
    """correlation 不可变身份/observation 不变量破坏时抛出的稳定错误。"""


class JobGovernanceRequiredError(RuntimeError):
    """未终结 correlation 存在时，complete/fail 等 generic 终结入口
    必须零 mutation 拒绝并转 governance 的闭合错误。"""


class JobRepositoryFailureError(RuntimeError):
    """数据库/仓储内部失败时抛出的稳定错误（不携带 cause 细节）。"""


# ---------------------------------------------------------------------------
# Canonical document
# ---------------------------------------------------------------------------

GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME = "dayu.job.generic-attempt-receipt"
"""generic attempt receipt 的固定 schema 名。"""

GENERIC_ATTEMPT_RECEIPT_SCHEMA_VERSION = 1
"""generic attempt receipt 的固定 schema 版本。"""

AGENT_RUN_TERMINAL_RECEIPT_SCHEMA_NAME = "dayu.job.agent-run-terminal-receipt"
"""Host-origin terminal receipt 的固定 schema 名。"""

AGENT_RUN_TERMINAL_RECEIPT_SCHEMA_VERSION = 1
"""Host-origin terminal receipt 的固定 schema 版本。"""

_RESULT_REFERENCE_KEYS: frozenset[str] = frozenset({"schema_name", "schema_version", "sha256"})
"""receipt ``result`` 引用对象的精确 key 集合。"""

_GENERIC_RECEIPT_KEYS: frozenset[str] = frozenset(
    {
        "attempt_id",
        "job_id",
        "outcome",
        "reason",
        "result",
        "safe_error_code",
        "schema_name",
        "schema_version",
    }
)
"""generic receipt canonical object 的精确 key 集合（字典序）。"""


def _reject_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """``json.loads`` 的 ``object_pairs_hook``：拒绝重复 JSON key。

    Args:
        pairs: JSON 对象键值对序列。

    Returns:
        校验通过的字典。

    Raises:
        ValueError: 存在重复 key 时抛出。
    """

    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("canonical json duplicate key")
        result[key] = value
    return result


def _reject_nonfinite(_token: str) -> NoReturn:
    """``json.loads`` 的 ``parse_constant``：拒绝 NaN/Infinity。

    Args:
        _token: JSON 常量 token（不使用）。

    Returns:
        永不返回。

    Raises:
        ValueError: 恒抛。
    """

    raise ValueError("canonical json non-finite constant")


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


def _require_nonempty_text(value: str, label: str) -> None:
    """校验字符串非空且无首尾空白。

    Args:
        value: 待校验字符串。
        label: 错误消息中的中文名称。

    Returns:
        无。

    Raises:
        JobInputError: 值为空、仅空白或含首尾空白时抛出。
    """

    if not isinstance(value, str) or not value or value != value.strip():
        raise JobInputError(f"{label}必须是非空且无首尾空白的字符串")


def _require_positive_int(value: int, label: str) -> None:
    """校验值为精确正整数（拒绝 bool 冒充）。

    Args:
        value: 待校验整数。
        label: 错误消息中的中文名称。

    Returns:
        无。

    Raises:
        JobInputError: 值不是精确 ``int`` 或不大于 0 时抛出。
    """

    if type(value) is not int or value <= 0:
        raise JobInputError(f"{label}必须是正整数")


def _require_sha256(value: str, label: str) -> None:
    """校验字符串为小写 64 位 hex SHA-256。

    Args:
        value: 待校验 hash。
        label: 错误消息中的中文名称。

    Returns:
        无。

    Raises:
        JobInputError: 值不是小写 64-hex 时抛出。
    """

    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise JobInputError(f"{label}必须是小写 64 位 hex SHA-256")


def _require_aware_utc(value: datetime, label: str) -> None:
    """校验 datetime 为 aware UTC。

    Args:
        value: 待校验时间。
        label: 错误消息中的中文名称。

    Returns:
        无。

    Raises:
        JobInputError: 时间不是 aware UTC 时抛出。
    """

    if not isinstance(value, datetime) or not _is_aware_utc(value):
        raise JobInputError(f"{label}必须是 aware UTC datetime")


@dataclass(frozen=True, slots=True)
class CanonicalJobDocument:
    """canonical 业务 document（payload/result/receipt 的唯一表示）。

    Args:
        schema_name: 非空无首尾空白的 schema 名。
        schema_version: 正整数的 schema 版本。
        canonical_bytes: 唯一 canonical UTF-8 JSON 表示的 bytes。
        sha256: ``canonical_bytes`` 的小写 64-hex SHA-256。
    """

    schema_name: str
    schema_version: int
    canonical_bytes: bytes
    sha256: str

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 任一字段违反不变量时抛出。
        """

        if type(self.schema_name) is not str:
            raise JobInputError("schema_name 必须是 str")
        _require_nonempty_text(self.schema_name, "schema_name")
        _require_positive_int(self.schema_version, "schema_version")
        if type(self.canonical_bytes) is not bytes:
            raise JobInputError("canonical_bytes 必须是 bytes")
        if type(self.sha256) is not str:
            raise JobInputError("sha256 必须是 str")
        _require_sha256(self.sha256, "sha256")


class _JsonValueValidator:
    """canonical JSON 值的递归校验器（模块私有）。"""

    def validate(self, value: JsonValue) -> JsonValue:
        """递归校验并返回收窄后的 JSON 值。

        Args:
            value: 待校验的 JSON 值。

        Returns:
            收窄后的 ``JsonValue``。

        Raises:
            ValueError: 值含 float/bool 冒充 int/敏感键/非法容器时抛出。
        """

        return self._validate_value(value)

    def validate_object(self, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """校验并返回收窄后的 JSON 对象。

        Args:
            value: 待校验的原始 JSON 对象。

        Returns:
            收窄后的 ``dict[str, JsonValue]``。

        Raises:
            ValueError: 对象含敏感键或非法嵌套值时抛出。
        """

        return self._validate_object(value)

    def _validate_value(self, value: JsonValue) -> JsonValue:
        """递归校验单个 JSON 值并拒绝非 canonical 类型。

        Args:
            value: 待校验的 JSON 值。

        Returns:
            收窄后的 ``JsonValue``。

        Raises:
            ValueError: 值含 float/非法容器/敏感键时抛出。
        """

        if value is None or type(value) is bool:
            return value
        if type(value) is int:
            return value
        if type(value) is str:
            return value
        if type(value) is list:
            return [self._validate_value(item) for item in value]
        if type(value) is dict:
            return self._validate_object(value)
        raise ValueError("canonical json unsupported value type")

    def _validate_object(self, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """递归校验 JSON 对象并递归拒绝 closed 敏感键。

        Args:
            value: 待校验的 JSON 对象。

        Returns:
            收窄后的 ``dict[str, JsonValue]``。

        Raises:
            ValueError: 键非字符串或命中敏感键集合时抛出。
        """

        result: dict[str, JsonValue] = {}
        for raw_key, raw_value in value.items():
            if type(raw_key) is not str:
                raise ValueError("canonical json non-string key")
            key = raw_key
            if key.lower() in _SENSITIVE_KEY_SET:
                raise ValueError("canonical json sensitive key")
            result[key] = self._validate_value(raw_value)
        return result


def _encode_canonical(value: JsonValue) -> bytes:
    """把已校验 JSON 值编码为 canonical UTF-8 bytes。

    Args:
        value: 已通过递归校验的 JSON 值。

    Returns:
        紧凑分隔符、对象 key 字典序、UTF-8、无 BOM 的 bytes。

    Raises:
        无。
    """

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _hash_canonical(value: JsonValue) -> str:
    """计算 canonical JSON 值的小写 64-hex SHA-256。

    Args:
        value: 已通过递归校验的 JSON 值。

    Returns:
        小写 64-hex SHA-256。

    Raises:
        无。
    """

    return hashlib.sha256(_encode_canonical(value)).hexdigest()


def parse_canonical_document(
    text: str,
    *,
    schema_name: str,
    schema_version: int,
) -> CanonicalJobDocument:
    """严格解析 canonical 业务 document。

    输入文本必须本身就是 canonical 形态（UTF-8、无 BOM、无重复 key、
    对象 key 字典序、紧凑分隔符、仅 null/bool/int/string/array/object、
    拒绝 float/NaN/Infinity）；解析后重新编码的 bytes 必须与输入 bytes
    完全相同，否则拒绝。递归拒绝 closed 敏感键集合。

    Args:
        text: 原始 JSON 文本。
        schema_name: 非空无首尾空白的 schema 名。
        schema_version: 正整数的 schema 版本。

    Returns:
        ``CanonicalJobDocument``。

    Raises:
        JobInputError: 文本非法或 schema 字段违反不变量时抛出。
    """

    try:
        raw: JsonValue = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (ValueError, json.JSONDecodeError):
        raise JobInputError("payload 必须是严格 canonical JSON") from None
    validator = _JsonValueValidator()
    try:
        value = validator.validate(raw)
    except ValueError:
        raise JobInputError("payload 必须是严格 canonical JSON") from None
    canonical_bytes = _encode_canonical(value)
    if text.encode("utf-8") != canonical_bytes:
        raise JobInputError("payload 必须是严格 canonical JSON")
    return CanonicalJobDocument(
        schema_name=schema_name,
        schema_version=schema_version,
        canonical_bytes=canonical_bytes,
        sha256=hashlib.sha256(canonical_bytes).hexdigest(),
    )


def build_canonical_document(
    value: JsonValue,
    *,
    schema_name: str,
    schema_version: int,
) -> CanonicalJobDocument:
    """从已收窄 JSON 值构建 canonical 业务 document。

    构造期递归拒绝敏感键与非法类型；不要求调用方预先编码。

    Args:
        value: 待编码的 JSON 值。
        schema_name: 非空无首尾空白的 schema 名。
        schema_version: 正整数的 schema 版本。

    Returns:
        ``CanonicalJobDocument``。

    Raises:
        JobInputError: 值非法或 schema 字段违反不变量时抛出。
    """

    validator = _JsonValueValidator()
    try:
        validated = validator.validate(value)
    except ValueError:
        raise JobInputError("payload 必须是严格 canonical JSON") from None
    canonical_bytes = _encode_canonical(validated)
    return CanonicalJobDocument(
        schema_name=schema_name,
        schema_version=schema_version,
        canonical_bytes=canonical_bytes,
        sha256=hashlib.sha256(canonical_bytes).hexdigest(),
    )


def _build_receipt_document(
    *,
    schema_name: str,
    schema_version: int,
    value: dict[str, JsonValue],
) -> CanonicalJobDocument:
    """以已编码值构建带真实 SHA-256 的 receipt document（模块私有）。

    Args:
        schema_name: receipt schema 名。
        schema_version: receipt schema 版本。
        value: 已通过递归校验的 JSON 值。

    Returns:
        已编码且 hash 已填充的 ``CanonicalJobDocument``。

    Raises:
        JobInputError: 值含非法类型/敏感键时抛出。
    """

    validator = _JsonValueValidator()
    try:
        validated = validator.validate(dict(value))
    except ValueError:
        raise JobInputError("receipt 必须是严格 canonical JSON") from None
    canonical_bytes = _encode_canonical(validated)
    return CanonicalJobDocument(
        schema_name=schema_name,
        schema_version=schema_version,
        canonical_bytes=canonical_bytes,
        sha256=hashlib.sha256(canonical_bytes).hexdigest(),
    )


def build_generic_attempt_receipt(
    *,
    job_id: UUID,
    attempt_id: UUID,
    outcome: AttemptReceiptOutcome,
    reason: GenericAttemptReceiptReason,
    safe_error_code: SafeJobErrorCode | None,
    result_ref: CanonicalJobDocument | None,
) -> CanonicalJobDocument:
    """构建 generic attempt receipt 的唯一 canonical document。

    该 builder 是除 Host-origin terminal receipt 外每个有 attempt 的
    terminal 路径的唯一 receipt 构造入口；同一 attempt 的重放必须读取
    既存 immutable row，绝不重新 builder。``result`` 只可为 ``None`` 或
    恰含 ``schema_name/schema_version/sha256`` 的引用对象，绝不重复
    ``result_bytes``。

    Args:
        job_id: 关联 job UUID。
        attempt_id: 关联 attempt UUID。
        outcome: 唯一业务 outcome。
        reason: closed reason（``GenericAttemptReceiptReason``）。
        safe_error_code: 可空安全错误码。
        result_ref: 可空安全业务 result document 引用。

    Returns:
        已编码的 receipt ``CanonicalJobDocument``。

    Raises:
        JobInputError: outcome/safe-code/result-ref 组合不在闭合矩阵内
            时抛出。
    """

    _validate_receipt_combination(
        outcome=outcome,
        reason=reason,
        safe_error_code=safe_error_code,
        result_ref=result_ref,
    )
    result_value: JsonValue
    if result_ref is None:
        result_value = None
    else:
        result_value = {
            "schema_name": result_ref.schema_name,
            "schema_version": result_ref.schema_version,
            "sha256": result_ref.sha256,
        }
    return _build_receipt_document(
        schema_name=GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME,
        schema_version=GENERIC_ATTEMPT_RECEIPT_SCHEMA_VERSION,
        value={
            "attempt_id": str(attempt_id),
            "job_id": str(job_id),
            "outcome": outcome.value,
            "reason": reason.value,
            "result": result_value,
            "safe_error_code": (safe_error_code.value if safe_error_code is not None else None),
            "schema_name": GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME,
            "schema_version": GENERIC_ATTEMPT_RECEIPT_SCHEMA_VERSION,
        },
    )


def parse_generic_attempt_receipt(text: str) -> dict[str, JsonValue]:
    """严格解析并校验 generic attempt receipt。

    要求 canonical 形态、精确 key 集合、schema 常量与
    outcome/reason/safe-code/result 组合闭合；任一违反抛
    ``JobInputError``。本函数只做验证与取值，不创建新的公开 DTO。

    Args:
        text: 原始 receipt JSON 文本。

    Returns:
        已校验的收窄键值映射（key 精确为 generic receipt 集合）。

    Raises:
        JobInputError: canonical/key 集合/组合任一非法时抛出。
    """

    try:
        raw: JsonValue = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (ValueError, json.JSONDecodeError):
        raise JobInputError("receipt 必须是严格 canonical JSON") from None
    if type(raw) is not dict:
        raise JobInputError("receipt 必须是严格 canonical JSON")
    raw_mapping: dict[str, JsonValue] = raw
    if set(raw_mapping) != _GENERIC_RECEIPT_KEYS:
        raise JobInputError("receipt key 集合必须精确")
    validator = _JsonValueValidator()
    try:
        validated = validator.validate_object(raw_mapping)
    except ValueError:
        raise JobInputError("receipt 必须是严格 canonical JSON") from None
    try:
        canonical_bytes = _encode_canonical(validated)
        if text.encode("utf-8") != canonical_bytes:
            raise JobInputError("receipt 必须是严格 canonical JSON")
        schema_name = validated["schema_name"]
        schema_version = validated["schema_version"]
        if not isinstance(schema_name, str):
            raise JobInputError("receipt schema_name 类型非法")
        if type(schema_version) is not int:
            raise JobInputError("receipt schema_version 类型非法")
        if schema_name != GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME:
            raise JobInputError("receipt schema_name 非法")
        if schema_version != GENERIC_ATTEMPT_RECEIPT_SCHEMA_VERSION:
            raise JobInputError("receipt schema_version 非法")
        outcome_raw = validated["outcome"]
        reason_raw = validated["reason"]
        code_raw = validated["safe_error_code"]
        result_raw = validated["result"]
        if not isinstance(outcome_raw, str):
            raise JobInputError("receipt outcome 类型非法")
        if not isinstance(reason_raw, str):
            raise JobInputError("receipt reason 类型非法")
        outcome = AttemptReceiptOutcome(outcome_raw)
        reason = GenericAttemptReceiptReason(reason_raw)
        safe_error_code = SafeJobErrorCode(code_raw) if code_raw is not None else None
        result_ref: CanonicalJobDocument | None = None
        if result_raw is not None:
            if not isinstance(result_raw, dict):
                raise JobInputError("receipt result 类型非法")
            if set(result_raw) != _RESULT_REFERENCE_KEYS:
                raise JobInputError("receipt result 引用 key 集合必须精确")
            ref_schema_name = result_raw["schema_name"]
            ref_schema_version = result_raw["schema_version"]
            ref_sha256 = result_raw["sha256"]
            if not isinstance(ref_schema_name, str):
                raise JobInputError("receipt result schema_name 类型非法")
            if type(ref_schema_version) is not int:
                raise JobInputError("receipt result schema_version 类型非法")
            if not isinstance(ref_sha256, str):
                raise JobInputError("receipt result sha256 类型非法")
            _require_nonempty_text(ref_schema_name, "result schema_name")
            _require_positive_int(ref_schema_version, "result schema_version")
            _require_sha256(ref_sha256, "result sha256")
            result_ref = CanonicalJobDocument(
                schema_name=ref_schema_name,
                schema_version=ref_schema_version,
                canonical_bytes=b"",
                sha256=ref_sha256,
            )
        _validate_receipt_combination(
            outcome=outcome,
            reason=reason,
            safe_error_code=safe_error_code,
            result_ref=result_ref,
        )
    except (JobInputError, ValueError, TypeError, KeyError):
        raise JobInputError("receipt 违反严格组合不变量") from None
    return dict(validated)


def _validate_receipt_combination(
    *,
    outcome: AttemptReceiptOutcome,
    reason: GenericAttemptReceiptReason,
    safe_error_code: SafeJobErrorCode | None,
    result_ref: CanonicalJobDocument | None,
) -> None:
    """校验 generic receipt 的闭合 outcome/reason/code/result 矩阵。

    Args:
        outcome: 唯一业务 outcome。
        reason: closed reason。
        safe_error_code: 可空安全错误码。
        result_ref: 可空 result 引用。

    Returns:
        无。

    Raises:
        JobInputError: 组合不在闭合矩阵内时抛出。
    """

    if reason is GenericAttemptReceiptReason.COMPLETION:
        if outcome is not AttemptReceiptOutcome.SUCCEEDED or safe_error_code is not None:
            raise JobInputError("completion receipt 必须为 succeeded/None/result")
        if result_ref is None:
            raise JobInputError("completion receipt 必须携带 result 引用")
        return
    if result_ref is not None:
        raise JobInputError("非 completion receipt 不得携带 result 引用")
    if reason is GenericAttemptReceiptReason.CANCEL_INTENT:
        if outcome is not AttemptReceiptOutcome.CANCELLED or safe_error_code is not SafeJobErrorCode.CANCELLED:
            raise JobInputError("cancel_intent receipt 必须为 cancelled/cancelled")
        return
    if reason is GenericAttemptReceiptReason.DEADLINE:
        if outcome is not AttemptReceiptOutcome.FAILED or safe_error_code is not SafeJobErrorCode.DEADLINE_EXCEEDED:
            raise JobInputError("deadline receipt 必须为 failed/deadline_exceeded")
        return
    if reason is GenericAttemptReceiptReason.LEASE_EXPIRED:
        if outcome is not AttemptReceiptOutcome.FAILED or safe_error_code is None:
            raise JobInputError("lease_expired receipt 必须为 failed/非空 code")
        if safe_error_code not in (
            SafeJobErrorCode.LEASE_EXPIRED,
            SafeJobErrorCode.RETRY_EXHAUSTED,
            SafeJobErrorCode.DEADLINE_EXCEEDED,
        ):
            raise JobInputError("lease_expired receipt safe code 非法")
        return
    # reason == failure
    if outcome is not AttemptReceiptOutcome.FAILED or safe_error_code is None:
        raise JobInputError("failure receipt 必须为 failed/非空 code")
    if safe_error_code in (
        SafeJobErrorCode.CANCELLED,
        SafeJobErrorCode.DEADLINE_EXCEEDED,
        SafeJobErrorCode.CORRELATION_INVARIANT,
        SafeJobErrorCode.CORRELATION_STALE_ATTEMPT,
    ):
        raise JobInputError("failure receipt safe code 非法")


def build_agent_run_terminal_receipt(
    *,
    correlation_id: UUID,
    reserved_host_run_id: str,
    host_state: HostRunObservationState,
    host_completed_at: datetime | None,
    outcome: AttemptReceiptOutcome,
    safe_error_code: SafeJobErrorCode | None,
) -> CanonicalJobDocument:
    """构建 Host-origin terminal receipt 的唯一 canonical document。

    只用于 tokenless terminal reconciliation 的 Host terminal 收敛；
    canonical object 精确只含
    ``correlation_id/reserved_host_run_id/host_state/host_completed_at/
    outcome/safe_error_code``，无 result、raw Host error 或 metadata。

    Args:
        correlation_id: 关联 correlation UUID。
        reserved_host_run_id: correlation 绑定的 reserved Host run ID。
        host_state: Host observation state。
        host_completed_at: 可空 Host completed_at。
        outcome: 唯一业务 outcome。
        safe_error_code: 可空安全错误码。

    Returns:
        已编码的 receipt ``CanonicalJobDocument``。

    Raises:
        JobInputError: outcome/safe-code 组合非法，或 terminal observation
            与 completed_at 不变量冲突时抛出。
    """

    if host_state in (
        HostRunObservationState.SUCCEEDED,
        HostRunObservationState.FAILED,
        HostRunObservationState.CANCELLED,
        HostRunObservationState.UNSETTLED,
    ):
        if host_completed_at is None:
            raise JobInputError("terminal host observation 必须携带 completed_at")
    elif host_completed_at is not None:
        raise JobInputError("非 terminal host observation 不得携带 completed_at")
    if outcome is AttemptReceiptOutcome.SUCCEEDED:
        if safe_error_code is not None or host_state is not HostRunObservationState.SUCCEEDED:
            raise JobInputError("host success receipt 必须为 succeeded/None")
    elif outcome is AttemptReceiptOutcome.CANCELLED:
        if (
            safe_error_code is not SafeJobErrorCode.HOST_RUN_CANCELLED
            or host_state is not HostRunObservationState.CANCELLED
        ):
            raise JobInputError("host cancelled receipt 必须为 cancelled/host_run_cancelled")
    else:
        if safe_error_code not in (
            SafeJobErrorCode.HOST_RUN_FAILED,
            SafeJobErrorCode.HOST_RUN_UNSETTLED,
        ):
            raise JobInputError("host failure receipt safe code 非法")
        if host_state not in (
            HostRunObservationState.FAILED,
            HostRunObservationState.UNSETTLED,
        ):
            raise JobInputError("host failure receipt host_state 非法")
    return _build_receipt_document(
        schema_name=AGENT_RUN_TERMINAL_RECEIPT_SCHEMA_NAME,
        schema_version=AGENT_RUN_TERMINAL_RECEIPT_SCHEMA_VERSION,
        value={
            "correlation_id": str(correlation_id),
            "reserved_host_run_id": reserved_host_run_id,
            "host_state": host_state.value,
            "host_completed_at": (host_completed_at.isoformat() if host_completed_at is not None else None),
            "outcome": outcome.value,
            "safe_error_code": (safe_error_code.value if safe_error_code is not None else None),
        },
    )


# ---------------------------------------------------------------------------
# Job DTOs（15 个公开 DTO）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JobHandlerDescriptor:
    """job handler 的 descriptor-only 配置（immutable definition 映射）。

    Args:
        job_type: 非空无首尾空白的 job 类型。
        payload_schema_name: 非空无首尾空白的 payload schema 名。
        payload_schema_version: 正整数的 payload schema 版本。
        max_attempts: 正整数最大尝试次数。
        retry_base_seconds: 正整数基础退避秒数。
        retry_max_seconds: 正整数最大退避秒数（不低于 base）。
        lease_duration_seconds: 正整数 lease 时长秒数。
    """

    job_type: str
    payload_schema_name: str
    payload_schema_version: int
    max_attempts: int
    retry_base_seconds: int
    retry_max_seconds: int
    lease_duration_seconds: int

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段违反不变量时抛出。
        """

        _require_nonempty_text(self.job_type, "job_type")
        _require_nonempty_text(self.payload_schema_name, "payload_schema_name")
        _require_positive_int(self.payload_schema_version, "payload_schema_version")
        _require_positive_int(self.max_attempts, "max_attempts")
        _require_positive_int(self.retry_base_seconds, "retry_base_seconds")
        _require_positive_int(self.retry_max_seconds, "retry_max_seconds")
        _require_positive_int(self.lease_duration_seconds, "lease_duration_seconds")
        if self.retry_max_seconds < self.retry_base_seconds:
            raise JobInputError("retry_max_seconds 必须不小于 retry_base_seconds")


@dataclass(frozen=True, slots=True)
class JobEnqueueRequest:
    """job 入队请求。

    Args:
        descriptor: 与 registry 同 ``job_type`` 值逐字段相等的 descriptor。
        idempotency_key: 非空无首尾空白的幂等键。
        payload: canonical payload document。
        available_at: aware UTC 可用时间。
        deadline_at: aware UTC 截止时间（必须晚于 ``available_at``）。
    """

    descriptor: JobHandlerDescriptor
    idempotency_key: str
    payload: CanonicalJobDocument
    available_at: datetime
    deadline_at: datetime

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段违反不变量时抛出。
        """

        _require_nonempty_text(self.idempotency_key, "idempotency_key")
        _require_aware_utc(self.available_at, "available_at")
        _require_aware_utc(self.deadline_at, "deadline_at")
        if not self.deadline_at > self.available_at:
            raise JobInputError("deadline_at 必须晚于 available_at")


@dataclass(frozen=True, slots=True)
class JobEnqueueReceipt:
    """job 入队收据。

    Args:
        tenant_id: 租户标识。
        definition_id: definition UUID。
        job_id: job UUID。
        state: 必为 ``ready``。
        idempotency_reused: 同 fingerprint 重用时为 ``True``；绝不把不同
            fingerprint 伪装成重用。
    """

    tenant_id: TenantId
    definition_id: UUID
    job_id: UUID
    state: JobState
    idempotency_reused: bool

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: state 不是 ``ready`` 时抛出。
        """

        if self.state is not JobState.READY:
            raise JobInputError("enqueue receipt state 必须为 ready")


@dataclass(frozen=True, slots=True)
class JobLeaseHandle:
    """job attempt 的 lease 句柄。

    Args:
        tenant_id: 租户标识。
        job_id: job UUID。
        attempt_id: attempt UUID。
        fence: 当前 attempt 的 fence（正整数）。
        raw_token: 256-bit 随机值的小写 64-hex，仅在 claim 返回一次且
            绝不持久化明文。
        acquired_at: aware UTC 获取时间。
        expires_at: aware UTC 过期时间（晚于 ``acquired_at``）。
    """

    tenant_id: TenantId
    job_id: UUID
    attempt_id: UUID
    fence: int
    raw_token: str
    acquired_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段违反不变量时抛出。
        """

        _require_positive_int(self.fence, "fence")
        _require_sha256(self.raw_token, "raw_token")
        _require_aware_utc(self.acquired_at, "acquired_at")
        _require_aware_utc(self.expires_at, "expires_at")
        if not self.expires_at > self.acquired_at:
            raise JobInputError("expires_at 必须晚于 acquired_at")


@dataclass(frozen=True, slots=True)
class JobClaim:
    """一次成功 claim 返回的完整 job 负载。

    Args:
        tenant_id: 租户标识。
        definition_id: definition UUID。
        job_id: job UUID。
        attempt_id: attempt UUID。
        attempt_number: 正整数 attempt 序号。
        worker_id: 非空无首尾空白的 worker 标识。
        descriptor: 该 job definition 的 immutable descriptor。
        payload: canonical payload document。
        lease: 嵌入的 lease 句柄（tenant/job/attempt 与外层逐字段相等）。
        deadline_at: aware UTC 截止时间（晚于 lease acquired）。
    """

    tenant_id: TenantId
    definition_id: UUID
    job_id: UUID
    attempt_id: UUID
    attempt_number: int
    worker_id: str
    descriptor: JobHandlerDescriptor
    payload: CanonicalJobDocument
    lease: JobLeaseHandle
    deadline_at: datetime

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段违反不变量时抛出。
        """

        _require_positive_int(self.attempt_number, "attempt_number")
        _require_nonempty_text(self.worker_id, "worker_id")
        _require_aware_utc(self.deadline_at, "deadline_at")
        if self.lease.tenant_id != self.tenant_id:
            raise JobInputError("lease tenant 必须等于外层 tenant")
        if self.lease.job_id != self.job_id:
            raise JobInputError("lease job_id 必须等于外层 job_id")
        if self.lease.attempt_id != self.attempt_id:
            raise JobInputError("lease attempt_id 必须等于外层 attempt_id")
        if not self.deadline_at > self.lease.acquired_at:
            raise JobInputError("deadline_at 必须晚于 lease acquired_at")


@dataclass(frozen=True, slots=True)
class JobExecutionRequest:
    """worker 经 Service execution gateway 交到 handler 的收窄执行请求。

    不含 ``JobLeaseHandle``、fence、raw token 或 worker id：worker
    identity 只属于 PG attempt 审计、process 日志与 metrics，绝不进入
    handler 可见的执行请求。

    Args:
        tenant_id: 租户标识。
        definition_id: definition UUID。
        job_id: job UUID。
        attempt_id: attempt UUID。
        attempt_number: 正整数 attempt 序号。
        descriptor: 该 job definition 的 immutable descriptor。
        payload: canonical payload document。
        deadline_at: aware UTC 截止时间（晚于 lease acquired）。
    """

    tenant_id: TenantId
    definition_id: UUID
    job_id: UUID
    attempt_id: UUID
    attempt_number: int
    descriptor: JobHandlerDescriptor
    payload: CanonicalJobDocument
    deadline_at: datetime

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段违反不变量时抛出。
        """

        if not isinstance(self.tenant_id, TenantId):
            raise JobInputError("tenant_id 必须是 TenantId")
        if not isinstance(self.definition_id, UUID):
            raise JobInputError("definition_id 必须是 UUID")
        if not isinstance(self.job_id, UUID):
            raise JobInputError("job_id 必须是 UUID")
        if not isinstance(self.attempt_id, UUID):
            raise JobInputError("attempt_id 必须是 UUID")
        _require_positive_int(self.attempt_number, "attempt_number")
        if not isinstance(self.descriptor, JobHandlerDescriptor):
            raise JobInputError("descriptor 必须是 JobHandlerDescriptor")
        if not isinstance(self.payload, CanonicalJobDocument):
            raise JobInputError("payload 必须是 CanonicalJobDocument")
        _require_aware_utc(self.deadline_at, "deadline_at")


@dataclass(frozen=True, slots=True)
class JobHeartbeatResult:
    """heartbeat 的闭合返回结果（Slice 2.2）。

    Args:
        action: ``renewed`` 或 ``governance_required``。
        claim: 续约后的 ``JobClaim``（两种 action 都续约同一 lease/
            fence）。
    """

    action: JobHeartbeatAction
    claim: JobClaim

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: action 不是枚举或 claim 不是 ``JobClaim``
                时抛出。
        """

        if not isinstance(self.action, JobHeartbeatAction):
            raise JobInputError("action 必须是 JobHeartbeatAction")
        if not isinstance(self.claim, JobClaim):
            raise JobInputError("claim 必须是 JobClaim")


class JobCancellationSignalProtocol(Protocol):
    """handler 协作式取消信号协议（pure domain 唯一 owner）。

    handler 只能经本协议观察取消意图并协作退出；协议不携带 token、
    fence、Host run 或任何持久化事实。``wait_cancel_requested`` 是
    async 方法，由调用方在事件循环内等待。
    """

    def is_cancel_requested(self) -> bool:
        """返回取消意图是否已置位。

        Args:
            无。

        Returns:
            已请求取消时返回 ``True``。

        Raises:
            无。
        """
        ...

    async def wait_cancel_requested(self) -> None:
        """等待取消意图置位后返回。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """
        ...


@dataclass(frozen=True, slots=True)
class JobCompletion:
    """有效 lease 的正常业务完成结果。

    Args:
        result: 安全业务 result document（不得以空/原始异常代替）。
    """

    result: CanonicalJobDocument

    def __post_init__(self) -> None:
        """构造期校验 result owner。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: result 不是 CanonicalJobDocument 时抛出。
        """

        if type(self.result) is not CanonicalJobDocument:
            raise JobInputError("result 必须是 CanonicalJobDocument")


@dataclass(frozen=True, slots=True)
class JobFailure:
    """有效 lease 的安全失败声明。

    Args:
        safe_error_code: 安全错误码。
        retryable: 是否可重试（既有 closed code 规则保持不变；source
            invalid 不可重试，source busy/interrupted 与 repository
            failure 必须可重试）。
    """

    safe_error_code: SafeJobErrorCode
    retryable: bool

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段类型或错误码/retryable 组合非法时抛出。
        """

        if type(self.retryable) is not bool:
            raise JobInputError("retryable 必须是布尔值")
        if type(self.safe_error_code) is not SafeJobErrorCode:
            raise JobInputError("safe_error_code 必须是 SafeJobErrorCode")
        try:
            error_code_value = self.safe_error_code.value
        except AttributeError:
            raise JobInputError("safe_error_code 必须是已注册的 SafeJobErrorCode") from None
        if type(error_code_value) is not str:
            raise JobInputError("safe_error_code value 必须是 str")
        try:
            canonical_error_code = SafeJobErrorCode(error_code_value)
        except ValueError:
            raise JobInputError("safe_error_code 必须是已注册的 SafeJobErrorCode") from None
        if canonical_error_code is not self.safe_error_code:
            raise JobInputError("safe_error_code 必须是已注册的 SafeJobErrorCode")
        if self.retryable and self.safe_error_code in (
            SafeJobErrorCode.CANCELLED,
            SafeJobErrorCode.DEADLINE_EXCEEDED,
            SafeJobErrorCode.RETRY_EXHAUSTED,
            SafeJobErrorCode.CORRELATION_INVARIANT,
            SafeJobErrorCode.CORRELATION_STALE_ATTEMPT,
            SafeJobErrorCode.SOURCE_INVALID,
        ):
            raise JobInputError("该 safe_error_code 不可标记为 retryable")
        if not self.retryable and self.safe_error_code in (
            SafeJobErrorCode.REPOSITORY_FAILURE,
            SafeJobErrorCode.SOURCE_OPERATION_BUSY,
            SafeJobErrorCode.SOURCE_INTERRUPTED,
        ):
            raise JobInputError("该 safe_error_code 必须标记为 retryable")


@dataclass(frozen=True, slots=True)
class JobCancellationRequest:
    """job 取消请求。

    Args:
        job_id: 目标 job UUID。
        reason: 调用方已脱敏的稳定原因（非空、无首尾空白；不含 Host
            run、token 或自由错误正文）。
    """

    job_id: UUID
    reason: str

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: reason 为空或含首尾空白时抛出。
        """

        _require_nonempty_text(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class JobAttemptReceipt:
    """attempt 的 immutable terminal receipt。

    Args:
        tenant_id: 租户标识。
        job_id: job UUID。
        attempt_id: attempt UUID。
        outcome: 唯一业务 outcome。
        result: 仅 outcome=`succeeded` 时可非空的安全 result document。
        receipt: 始终存在的 canonical receipt document。
        safe_error_code: success 为 ``None``，failed/cancelled 必非空。
        finalized_at: aware UTC 收口时间。
    """

    tenant_id: TenantId
    job_id: UUID
    attempt_id: UUID
    outcome: AttemptReceiptOutcome
    result: CanonicalJobDocument | None
    receipt: CanonicalJobDocument
    safe_error_code: SafeJobErrorCode | None
    finalized_at: datetime

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段违反不变量时抛出。
        """

        _require_aware_utc(self.finalized_at, "finalized_at")
        if self.outcome is AttemptReceiptOutcome.SUCCEEDED:
            if self.safe_error_code is not None:
                raise JobInputError("success receipt safe_error_code 必须为 None")
        else:
            if self.safe_error_code is None:
                raise JobInputError("failed/cancelled receipt 必须携带 safe_error_code")
            if self.result is not None:
                raise JobInputError("failed/cancelled receipt result 必须为 None")


@dataclass(frozen=True, slots=True)
class JobRecoveryResult:
    """recovery 后返回的闭合状态结果。

    Args:
        job_id: job UUID。
        attempt_id: 可空 attempt UUID（无 attempt 的 ready cancel 为
            ``None``）。
        job_state: job 当前状态。
        attempt_state: 可空 attempt 当前状态（无 attempt 时为 ``None``）。
        receipt: 可空 attempt receipt（无 attempt 时为 ``None``）。
        next_available_at: 可空下次可用时间。
        safe_error_code: 可空安全错误码。
    """

    job_id: UUID
    attempt_id: UUID | None
    job_state: JobState
    attempt_state: AttemptState | None
    receipt: JobAttemptReceipt | None
    next_available_at: datetime | None
    safe_error_code: SafeJobErrorCode | None

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段违反不变量时抛出。
        """

        if self.attempt_id is None:
            if self.attempt_state is not None or self.receipt is not None:
                raise JobInputError("无 attempt 时不得携带 attempt_state/receipt")
        if self.next_available_at is not None:
            _require_aware_utc(self.next_available_at, "next_available_at")


@dataclass(frozen=True, slots=True)
class AgentRunCorrelation:
    """agent run correlation 的完整不可变投影。

    Args:
        id: correlation UUID。
        tenant_id: 租户标识。
        job_id: job UUID。
        attempt_id: attempt UUID。
        idempotency_key: 非空幂等键。
        reserved_host_run_id: 精确为 ``run_{attempt_id.hex}``。
        state: correlation 当前状态。
        observed_at: 可空 aware UTC observation 时间。
        last_observation_sha256: 可空小写 64-hex observation fingerprint。
        created_at: aware UTC 创建时间。
        updated_at: aware UTC 更新时间。
        version: 正整数乐观版本。
    """

    id: UUID
    tenant_id: TenantId
    job_id: UUID
    attempt_id: UUID
    idempotency_key: str
    reserved_host_run_id: str
    state: CorrelationState
    observed_at: datetime | None
    last_observation_sha256: str | None
    created_at: datetime
    updated_at: datetime
    version: int

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段违反不变量时抛出。
        """

        _require_nonempty_text(self.idempotency_key, "idempotency_key")
        expected_reserved = f"run_{self.attempt_id.hex}"
        if self.reserved_host_run_id != expected_reserved:
            raise JobInputError("reserved_host_run_id 必须等于 run_{attempt_id.hex}")
        _require_positive_int(self.version, "version")
        _require_aware_utc(self.created_at, "created_at")
        _require_aware_utc(self.updated_at, "updated_at")
        if self.observed_at is not None:
            _require_aware_utc(self.observed_at, "observed_at")
        if self.last_observation_sha256 is not None:
            _require_sha256(self.last_observation_sha256, "last_observation_sha256")
        if (self.observed_at is None) != (self.last_observation_sha256 is None):
            raise JobInputError("observed_at 与 last_observation_sha256 必须同时存在或同时为空")


@dataclass(frozen=True, slots=True)
class AgentRunCorrelationObservation:
    """Service 对 Host ``RunRecord`` 的闭合、安全 observation 投影。

    Args:
        correlation_id: 关联 correlation UUID。
        host_run_id: 必等于 correlation 的 reserved Host run ID。
        host_state: ``HostRunObservationState``。
        host_completed_at: terminal state 必为 aware UTC 非 None；非
            terminal 必为 ``None``。
        sha256: 上述四个业务值的 canonical-safe JSON fingerprint。
    """

    correlation_id: UUID
    host_run_id: str
    host_state: HostRunObservationState
    host_completed_at: datetime | None
    sha256: str

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 字段违反不变量时抛出。
        """

        _require_sha256(self.sha256, "sha256")
        if self.host_completed_at is not None:
            _require_aware_utc(self.host_completed_at, "host_completed_at")
        if self.host_state in (
            HostRunObservationState.SUCCEEDED,
            HostRunObservationState.FAILED,
            HostRunObservationState.CANCELLED,
            HostRunObservationState.UNSETTLED,
        ):
            if self.host_completed_at is None:
                raise JobInputError("terminal observation 必须携带 host_completed_at")
        elif self.host_completed_at is not None:
            raise JobInputError("非 terminal observation 不得携带 host_completed_at")


@dataclass(frozen=True, slots=True)
class AgentRunStartAuthorizationDecision:
    """live start authorization 的闭合决策。

    Args:
        correlation: 绑定 attempt 的 correlation。
        attempt_id: 必等于 correlation 绑定 attempt 的当前值。
        fence: 必等于 correlation 绑定 attempt 的当前 fence。
        action: 闭合决策 action。
        safe_error_code: ``START_REQUIRED``/``WAIT`` 时为 ``None``，其它
            action 按稳定 safe code 填充。
    """

    correlation: AgentRunCorrelation
    attempt_id: UUID
    fence: int
    action: AgentRunStartAuthorizationAction
    safe_error_code: SafeJobErrorCode | None

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: attempt/fence 与 correlation 绑定值不一致或
                error code 组合非法时抛出。
        """

        if self.attempt_id != self.correlation.attempt_id:
            raise JobInputError("attempt_id 必须等于 correlation 绑定 attempt")
        _require_positive_int(self.fence, "fence")
        if self.action in (
            AgentRunStartAuthorizationAction.START_REQUIRED,
            AgentRunStartAuthorizationAction.WAIT,
        ):
            if self.safe_error_code is not None:
                raise JobInputError("START_REQUIRED/WAIT 不得携带 safe_error_code")
        elif self.safe_error_code is None:
            raise JobInputError("非 START_REQUIRED/WAIT action 必须携带 safe_error_code")


@dataclass(frozen=True, slots=True)
class AgentRunTerminalReconciliationDecision:
    """tokenless terminal-only reconciliation 的闭合决策。

    Args:
        correlation: 绑定 attempt 的 correlation。
        observation: 本次 Host observation 投影（ID/host run ID 必匹配）。
        attempt_id: 必等于 correlation 绑定 attempt 的当前值。
        fence: 必等于 correlation 绑定 attempt 的当前 fence。
        action: 闭合决策 action。
        receipt: 可空 attempt receipt（terminal 路径有，其它为 ``None``）。
        safe_error_code: 可空安全错误码。
    """

    correlation: AgentRunCorrelation
    observation: AgentRunCorrelationObservation
    attempt_id: UUID
    fence: int
    action: AgentRunTerminalReconciliationAction
    receipt: JobAttemptReceipt | None
    safe_error_code: SafeJobErrorCode | None

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: ID/attempt/fence/receipt 不变量违反时抛出。
        """

        if self.correlation.id != self.observation.correlation_id:
            raise JobInputError("observation correlation_id 必须等于 correlation id")
        if self.observation.host_run_id != self.correlation.reserved_host_run_id:
            raise JobInputError("observation host_run_id 必须等于 reserved_host_run_id")
        if self.attempt_id != self.correlation.attempt_id:
            raise JobInputError("attempt_id 必须等于 correlation 绑定 attempt")
        _require_positive_int(self.fence, "fence")


@dataclass(frozen=True, slots=True)
class AgentRunGovernanceProjection:
    """PostgreSQL join projection 提供的 governance 快照（Slice 2.2）。

    deadline/cancel truth 只来自同一事务的 PG clock 与持久化列，绝不
    使用 worker wall clock、``correlation.updated_at``、Redis timestamp
    或进程启动时间推导。所有 identity 以 ``correlation`` 为唯一来源，
    其余标量必须与 correlation 绑定 job/attempt 逐字段闭合。

    Args:
        correlation: 未终结 correlation 的完整不可变投影。
        job_state: 绑定 job 的当前状态。
        attempt_state: 绑定 attempt 的当前状态。
        deadline_at: 绑定 job 的持久化 deadline。
        job_cancel_requested_at: 可空 PG cancel intent 时间。
        deadline_reached: 同一事务 PG clock 是否已达 deadline。
        lease_expires_at: 绑定 attempt 的持久化 lease 过期时间。
        database_now: 同一事务的 PG clock。
    """

    correlation: AgentRunCorrelation
    job_state: JobState
    attempt_state: AttemptState
    deadline_at: datetime
    job_cancel_requested_at: datetime | None
    deadline_reached: bool
    lease_expires_at: datetime
    database_now: datetime

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: correlation 类型、状态/时间字段或 PG 推导
                的 ``deadline_reached`` 一致性违反时抛出。
        """

        if not isinstance(self.correlation, AgentRunCorrelation):
            raise JobInputError("correlation 必须是 AgentRunCorrelation")
        if self.correlation.state not in (
            CorrelationState.RESERVED,
            CorrelationState.HOST_CREATED,
            CorrelationState.HOST_RUNNING,
        ):
            raise JobInputError("governance projection 只允许未终结 correlation")
        if not isinstance(self.job_state, JobState):
            raise JobInputError("job_state 必须是 JobState")
        if not isinstance(self.attempt_state, AttemptState):
            raise JobInputError("attempt_state 必须是 AttemptState")
        if type(self.deadline_reached) is not bool:
            raise JobInputError("deadline_reached 必须是布尔值")
        _require_aware_utc(self.deadline_at, "deadline_at")
        _require_aware_utc(self.lease_expires_at, "lease_expires_at")
        _require_aware_utc(self.database_now, "database_now")
        if self.job_cancel_requested_at is not None:
            _require_aware_utc(self.job_cancel_requested_at, "job_cancel_requested_at")
        if self.deadline_reached != (self.database_now >= self.deadline_at):
            raise JobInputError("deadline_reached 必须等于 PG 推导值 database_now >= deadline_at")


@dataclass(frozen=True, slots=True)
class AgentRunGovernanceCursor:
    """Worker governance 分页的 keyset cursor（``(deadline_at, id)``）。

    Args:
        deadline_at: 上一页末尾的 deadline（同 tuple keyset 排序键）。
        correlation_id: 上一页末尾的 correlation UUID。
    """

    deadline_at: datetime
    correlation_id: UUID

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: 时间不是 aware UTC 或 id 不是 UUID 时抛出。
        """

        _require_aware_utc(self.deadline_at, "deadline_at")
        if not isinstance(self.correlation_id, UUID):
            raise JobInputError("correlation_id 必须是 UUID")


@dataclass(frozen=True, slots=True)
class AgentRunGovernanceProjectionPage:
    """storage 层 governance 投影分页结果（绝不泄漏进 Host）。

    Args:
        projections: 本页投影 tuple（按 deadline ASC、correlation id
            ASC 排序）。
        next_cursor: 下一页 keyset cursor；已到尾部时为 ``None``。
    """

    projections: tuple[AgentRunGovernanceProjection, ...]
    next_cursor: AgentRunGovernanceCursor | None

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: projections 不是 tuple、元素类型非法或
                cursor 类型非法时抛出。
        """

        if not isinstance(self.projections, tuple):
            raise JobInputError("projections 必须是 tuple")
        previous_key: tuple[datetime, UUID] | None = None
        for projection in self.projections:
            if not isinstance(projection, AgentRunGovernanceProjection):
                raise JobInputError("projections 必须全部是 AgentRunGovernanceProjection")
            current_key = (
                projection.deadline_at,
                projection.correlation.id,
            )
            if previous_key is not None and current_key <= previous_key:
                raise JobInputError("projections 必须按 deadline_at/correlation_id 严格递增")
            previous_key = current_key
        if self.next_cursor is not None and not isinstance(self.next_cursor, AgentRunGovernanceCursor):
            raise JobInputError("next_cursor 必须是 AgentRunGovernanceCursor 或 None")
        if self.next_cursor is not None:
            if not self.projections:
                raise JobInputError("空 projections 的 next_cursor 必须是 None")
            last = self.projections[-1]
            expected_cursor = AgentRunGovernanceCursor(
                deadline_at=last.deadline_at,
                correlation_id=last.correlation.id,
            )
            if self.next_cursor != expected_cursor:
                raise JobInputError("next_cursor 必须等于本页末项 key")


class AgentRunGovernanceAction(str, Enum):
    """Worker governance 的闭合决策 action（Slice 2.2）。

    - ``ACTIVE_WAIT``：Host 活跃且无 cancel/deadline 治理条件，等待；
    - ``MISSING_HOST_WAIT``：Host missing 但 lease 仍有效，停止续租并
      等待持久化 expiry；
    - ``CANCEL_REQUESTED``：本调用向 Host 幂等写入协作式 cancel intent；
    - ``CANCEL_ALREADY_REQUESTED``：Host 已有 cancel intent，只 reobserve；
    - ``TERMINAL_RECONCILED``：Host terminal 已 reconcile；
    - ``NO_HOST_RECOVERED``：lease 已过期且 Host missing，targeted
      recover 已收敛；
    - ``SEND_RETRY``：Host cancel 发送失败，PG 零 mutation，下轮重试；
    - ``STALE``：reserved run 已漂移/过期，按真实终态收敛；
    - ``INVARIANT_FAILURE``：实现/数据库不变量破坏，fail closed。
    """

    ACTIVE_WAIT = "ACTIVE_WAIT"
    MISSING_HOST_WAIT = "MISSING_HOST_WAIT"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCEL_ALREADY_REQUESTED = "CANCEL_ALREADY_REQUESTED"
    TERMINAL_RECONCILED = "TERMINAL_RECONCILED"
    NO_HOST_RECOVERED = "NO_HOST_RECOVERED"
    SEND_RETRY = "SEND_RETRY"
    STALE = "STALE"
    INVARIANT_FAILURE = "INVARIANT_FAILURE"


def _require_governance_safe_error_combination(
    action: AgentRunGovernanceAction,
    safe_error_code: SafeJobErrorCode | None,
) -> None:
    """校验治理 action 与安全错误码的闭合组合。

    Args:
        action: 已验证的治理 action。
        safe_error_code: 已验证类型的可空安全错误码。

    Returns:
        无。

    Raises:
        JobInputError: action 与安全错误码不属于闭合矩阵时抛出。
    """

    no_error_actions = (
        AgentRunGovernanceAction.ACTIVE_WAIT,
        AgentRunGovernanceAction.MISSING_HOST_WAIT,
        AgentRunGovernanceAction.CANCEL_REQUESTED,
        AgentRunGovernanceAction.CANCEL_ALREADY_REQUESTED,
        AgentRunGovernanceAction.SEND_RETRY,
    )
    if action in no_error_actions and safe_error_code is not None:
        raise JobInputError(f"{action.value} 的 safe_error_code 必须是 None")
    if action is AgentRunGovernanceAction.STALE and safe_error_code is not SafeJobErrorCode.CORRELATION_STALE_ATTEMPT:
        raise JobInputError("STALE 的 safe_error_code 必须是 CORRELATION_STALE_ATTEMPT")
    if (
        action is AgentRunGovernanceAction.INVARIANT_FAILURE
        and safe_error_code is not SafeJobErrorCode.CORRELATION_INVARIANT
    ):
        raise JobInputError("INVARIANT_FAILURE 的 safe_error_code 必须是 CORRELATION_INVARIANT")
    if action is AgentRunGovernanceAction.TERMINAL_RECONCILED and (
        safe_error_code
        not in (
            None,
            SafeJobErrorCode.HOST_RUN_FAILED,
            SafeJobErrorCode.HOST_RUN_CANCELLED,
            SafeJobErrorCode.HOST_RUN_UNSETTLED,
        )
    ):
        raise JobInputError("TERMINAL_RECONCILED 的 safe_error_code 非法")
    if action is AgentRunGovernanceAction.NO_HOST_RECOVERED and (
        safe_error_code
        not in (
            SafeJobErrorCode.CANCELLED,
            SafeJobErrorCode.DEADLINE_EXCEEDED,
            SafeJobErrorCode.LEASE_EXPIRED,
            SafeJobErrorCode.RETRY_EXHAUSTED,
        )
    ):
        raise JobInputError("NO_HOST_RECOVERED 的 safe_error_code 非法")


@dataclass(frozen=True, slots=True)
class AgentRunGovernanceResult:
    """Worker governance 的闭合结果（携带完整 projection identity）。

    Args:
        correlation_id: 原 governance projection 的 correlation UUID。
        job_id: 原 governance projection 的 job UUID。
        attempt_id: 原 governance projection 的 attempt UUID。
        action: 闭合治理 action。
        safe_error_code: 可空安全错误码。
    """

    correlation_id: UUID
    job_id: UUID
    attempt_id: UUID
    action: AgentRunGovernanceAction
    safe_error_code: SafeJobErrorCode | None

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: identity/action 类型非法或 safe code 组合非法时
                抛出。
        """

        if not isinstance(self.correlation_id, UUID):
            raise JobInputError("correlation_id 必须是 UUID")
        if not isinstance(self.job_id, UUID):
            raise JobInputError("job_id 必须是 UUID")
        if not isinstance(self.attempt_id, UUID):
            raise JobInputError("attempt_id 必须是 UUID")
        if not isinstance(self.action, AgentRunGovernanceAction):
            raise JobInputError("action 必须是 AgentRunGovernanceAction")
        if self.safe_error_code is not None and not isinstance(self.safe_error_code, SafeJobErrorCode):
            raise JobInputError("safe_error_code 必须是 SafeJobErrorCode 或 None")
        _require_governance_safe_error_combination(self.action, self.safe_error_code)


@dataclass(frozen=True, slots=True)
class AgentRunGovernancePage:
    """Service 层 governance 分页结果（Worker 唯一消费方）。

    Args:
        results: 本页治理结果 tuple。
        next_cursor: 下一页 keyset cursor；已到尾部时为 ``None``。
    """

    results: tuple[AgentRunGovernanceResult, ...]
    next_cursor: AgentRunGovernanceCursor | None

    def __post_init__(self) -> None:
        """构造期校验字段不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            JobInputError: results 不是 tuple、元素类型非法或 cursor
                类型非法，或页内重复 correlation/attempt identity 时抛出。
        """

        if not isinstance(self.results, tuple):
            raise JobInputError("results 必须是 tuple")
        seen_correlation_ids: set[UUID] = set()
        seen_attempt_ids: set[UUID] = set()
        for result in self.results:
            if not isinstance(result, AgentRunGovernanceResult):
                raise JobInputError("results 必须全部是 AgentRunGovernanceResult")
            if result.correlation_id in seen_correlation_ids:
                raise JobInputError("governance page 不得重复 correlation identity")
            if result.attempt_id in seen_attempt_ids:
                raise JobInputError("governance page 不得重复 attempt identity")
            seen_correlation_ids.add(result.correlation_id)
            seen_attempt_ids.add(result.attempt_id)
        if self.next_cursor is not None and not isinstance(self.next_cursor, AgentRunGovernanceCursor):
            raise JobInputError("next_cursor 必须是 AgentRunGovernanceCursor 或 None")


def job_enqueue_request_fingerprint(request: JobEnqueueRequest) -> str:
    """计算 enqueue idempotency fingerprint（唯一算法真源）。

    覆盖 descriptor 全部七字段、payload schema/version/sha256 与
    available/deadline；``ScheduleService`` 与 ``PostgresJobStore`` 共同
    调用本函数，旧 storage 私有实现一律删除而非复制。crash replay 必须
    重建 byte-identical ``JobEnqueueRequest`` 后调用本函数。

    Args:
        request: 入队请求。

    Returns:
        小写 64-hex SHA-256。

    Raises:
        无。
    """

    descriptor = request.descriptor
    payload = request.payload
    fingerprint_input = {
        "job_type": descriptor.job_type,
        "payload_schema_name": descriptor.payload_schema_name,
        "payload_schema_version": descriptor.payload_schema_version,
        "max_attempts": descriptor.max_attempts,
        "retry_base_seconds": descriptor.retry_base_seconds,
        "retry_max_seconds": descriptor.retry_max_seconds,
        "lease_duration_seconds": descriptor.lease_duration_seconds,
        "request_payload_schema_name": payload.schema_name,
        "request_payload_schema_version": payload.schema_version,
        "request_payload_sha256": payload.sha256,
        "available_at": request.available_at.isoformat(),
        "deadline_at": request.deadline_at.isoformat(),
    }
    canonical = json.dumps(
        fingerprint_input,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "AGENT_RUN_TERMINAL_RECEIPT_SCHEMA_NAME",
    "AGENT_RUN_TERMINAL_RECEIPT_SCHEMA_VERSION",
    "AgentRunCorrelation",
    "AgentRunCorrelationObservation",
    "AgentRunGovernanceAction",
    "AgentRunGovernanceCursor",
    "AgentRunGovernancePage",
    "AgentRunGovernanceProjection",
    "AgentRunGovernanceProjectionPage",
    "AgentRunGovernanceResult",
    "AgentRunStartAuthorizationAction",
    "AgentRunStartAuthorizationDecision",
    "AgentRunTerminalReconciliationAction",
    "AgentRunTerminalReconciliationDecision",
    "AttemptReceiptOutcome",
    "AttemptState",
    "CanonicalJobDocument",
    "CorrelationState",
    "GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME",
    "GENERIC_ATTEMPT_RECEIPT_SCHEMA_VERSION",
    "GenericAttemptReceiptReason",
    "HostRunObservationState",
    "JobAttemptReceipt",
    "JobCancellationRequest",
    "JobCancellationSignalProtocol",
    "JobClaim",
    "JobCompletion",
    "JobCorrelationInvariantError",
    "JobDeadlineExceededError",
    "JobDefinitionState",
    "JobEnqueueReceipt",
    "JobEnqueueRequest",
    "JobExecutionRequest",
    "JobFailure",
    "JobGovernanceRequiredError",
    "JobHandlerDescriptor",
    "JobHeartbeatAction",
    "JobHeartbeatResult",
    "JobIdempotencyConflictError",
    "JobInputError",
    "JobLeaseHandle",
    "JobLeaseLostError",
    "JobNotFoundError",
    "JobRecoveryResult",
    "JobRepositoryFailureError",
    "JobState",
    "JobStateConflictError",
    "LeaseReleaseReason",
    "SafeJobErrorCode",
    "build_agent_run_terminal_receipt",
    "build_canonical_document",
    "build_generic_attempt_receipt",
    "job_enqueue_request_fingerprint",
    "parse_canonical_document",
    "parse_generic_attempt_receipt",
]
