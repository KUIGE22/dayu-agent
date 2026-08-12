"""投资数据源同步的纯领域契约与 canonical 文档。

本模块是 Source Sync 执行 foundation 的唯一 owner。它只依赖 source、
durable jobs 与 schedules 的纯契约，集中拥有共享 enum、closed error、
config、public manual/schedule input 与跨 owner 使用的严格 typed helper。

所有公开 DTO 均为 frozen slots；时间必须为 aware UTC，日期必须是精确
``date``，tuple 在构造期防御性复制。模块不依赖 Fins、Service 或存储实现。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from uuid import UUID

from dayu.investment.domain.jobs import (
    CanonicalJobDocument,
    JobHandlerDescriptor,
    JsonValue,
    parse_canonical_document,
)
from dayu.investment.domain.schedules import ScheduleMisfirePolicy
from dayu.investment.domain.source import SourceSubscriptionId

SOURCE_SYNC_JOB_TYPE = "investment.source-sync.v1"
"""Source Sync durable Job 的固定类型。"""

SOURCE_SYNC_PAYLOAD_SCHEMA_NAME = "investment.source-sync"
"""Source Sync payload 的 canonical schema 名。"""

SOURCE_SYNC_PAYLOAD_SCHEMA_VERSION = 1
"""Source Sync payload 的 canonical schema 版本。"""

SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME = "investment.source-execution-snapshot"
"""执行快照的 canonical schema 名。"""

SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME = "investment.fins-evidence-locator"
"""Investment-owned pathless locator wrapper 的 schema 名。"""

SOURCE_SYNC_RECEIPT_SCHEMA_NAME = "investment.source-sync-receipt"
"""Source Sync receipt 的 canonical schema 名。"""

SOURCE_SYNC_RESULT_SCHEMA_NAME = "investment.source-sync-result"
"""Source Sync Job result 的 canonical schema 名。"""

SOURCE_SYNC_JOB_DESCRIPTOR = JobHandlerDescriptor(
    job_type=SOURCE_SYNC_JOB_TYPE,
    payload_schema_name=SOURCE_SYNC_PAYLOAD_SCHEMA_NAME,
    payload_schema_version=SOURCE_SYNC_PAYLOAD_SCHEMA_VERSION,
    max_attempts=3,
    retry_base_seconds=30,
    retry_max_seconds=300,
    lease_duration_seconds=900,
)
"""Slice 2.3 固定 Source Sync handler descriptor。"""

FINS_SOURCE_DEFINITION_KEY = "fins.market-disclosure.v1"
"""本 Slice 唯一可执行的数据源定义 key。"""

MAX_SOURCE_DOCUMENTS = 500
"""单次同步可持久化的最大文档数。"""

MAX_SOURCE_DOCUMENT_BYTES = 8_388_608
"""Source receipt/result canonical bytes 的统一上限。"""

_LOWER_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_FORM = re.compile(r"^[A-Z0-9][A-Z0-9./\-]*(?: [A-Z0-9][A-Z0-9./\-]*)*$")
_CANONICAL_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]*$")


class SourceConnectorKey(str, Enum):
    """数据源 connector 的闭合集合。"""

    FINS_MARKET_DISCLOSURE_V1 = "fins.market-disclosure.v1"
    RSS_V1 = "rss.v1"
    INDUSTRY_METRIC_V1 = "industry-metric.v1"
    MANUAL_V1 = "manual.v1"


class SourceSyncOrigin(str, Enum):
    """Source Sync 请求来源。"""

    MANUAL = "manual"
    SCHEDULED = "scheduled"


class SourceBindingDisposition(str, Enum):
    """operation acquire 时冻结的 binding 处置。"""

    READY = "ready"
    DISABLED = "disabled"
    STALE = "stale"


class SourceSyncOutcome(str, Enum):
    """Source observation 的闭合结果。"""

    SUCCEEDED = "succeeded"
    NO_CHANGE = "no_change"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED_DISABLED = "skipped_disabled"
    STALE_SUBSCRIPTION = "stale_subscription"


class SourceSyncErrorCode(str, Enum):
    """Source observation 的安全错误码。"""

    UNSUPPORTED_MARKET = "unsupported_market"
    UNSUPPORTED_FORM = "unsupported_form"
    STALE_DATA = "stale_data"
    PARTIAL_BATCH = "partial_batch"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    FINS_INVARIANT = "fins_invariant"
    STALE_SUBSCRIPTION = "stale_subscription"


class SourceSyncRequestRejectionCode(str, Enum):
    """请求或持久化 identity 的闭合拒绝码。"""

    TENANT_IDENTITY_MISMATCH = "tenant_identity_mismatch"
    JOB_LINEAGE_MISMATCH = "job_lineage_mismatch"
    PAYLOAD_HASH_MISMATCH = "payload_hash_mismatch"
    BINDING_NON_EXECUTABLE = "binding_non_executable"
    SNAPSHOT_MISMATCH = "snapshot_mismatch"
    INVALID_INPUT = "invalid_input"
    SUBSCRIPTION_NOT_FOUND = "subscription_not_found"
    SUBSCRIPTION_VERSION_CONFLICT = "subscription_version_conflict"
    SUBSCRIPTION_STATE_CONFLICT = "subscription_state_conflict"
    HEALTH_VERSION_CONFLICT = "health_version_conflict"
    HEALTH_STATE_CONFLICT = "health_state_conflict"


class SourceSyncExecutionRejectionCode(str, Enum):
    """锁后 execution live truth 的闭合拒绝码。"""

    JOB_NOT_LIVE = "job_not_live"
    LEASE_LOST = "lease_lost"


class SourceSyncRepositoryFailureCode(str, Enum):
    """Source repository 的闭合基础设施错误码。"""

    UNAVAILABLE = "unavailable"
    TRANSACTION_ABORTED = "transaction_aborted"
    PERSISTED_INVARIANT = "persisted_invariant"


class SourceSyncRequestRejected(Exception):
    """Source repository 的 closed request rejection。"""

    def __init__(self, code: SourceSyncRequestRejectionCode) -> None:
        """保存闭合错误码，不接收自由错误正文。

        Args:
            code: 请求拒绝码。
        """

        if not isinstance(code, SourceSyncRequestRejectionCode):
            raise TypeError("code 必须是 SourceSyncRequestRejectionCode")
        super().__init__(code.value)
        self.code = code


class SourceSyncExecutionRejected(Exception):
    """Source repository 的 closed execution rejection。"""

    def __init__(self, code: SourceSyncExecutionRejectionCode) -> None:
        """保存闭合错误码，不接收自由错误正文。

        Args:
            code: execution 拒绝码。
        """

        if not isinstance(code, SourceSyncExecutionRejectionCode):
            raise TypeError("code 必须是 SourceSyncExecutionRejectionCode")
        super().__init__(code.value)
        self.code = code


class SourceSyncRepositoryFailure(Exception):
    """Source repository 的 closed failure。"""

    def __init__(self, code: SourceSyncRepositoryFailureCode) -> None:
        """保存闭合错误码，不泄漏 driver 或 SQL 正文。

        Args:
            code: repository failure 码。
        """

        if not isinstance(code, SourceSyncRepositoryFailureCode):
            raise TypeError("code 必须是 SourceSyncRepositoryFailureCode")
        super().__init__(code.value)
        self.code = code


class SourceServiceInputError(Exception):
    """Source public Service 的闭合输入错误。"""

    def __init__(self, code: SourceSyncRequestRejectionCode) -> None:
        """保存原 request rejection code。

        Args:
            code: 输入错误码。
        """

        if not isinstance(code, SourceSyncRequestRejectionCode):
            raise TypeError("code 必须是 SourceSyncRequestRejectionCode")
        super().__init__(code.value)
        self.code = code


class SourceServiceUnavailableError(Exception):
    """Source public Service 的闭合不可用错误。"""

    def __init__(self, code: SourceSyncRepositoryFailureCode) -> None:
        """保存原 repository failure code。

        Args:
            code: 不可用错误码。
        """

        if not isinstance(code, SourceSyncRepositoryFailureCode):
            raise TypeError("code 必须是 SourceSyncRepositoryFailureCode")
        super().__init__(code.value)
        self.code = code


def _require_exact_type(value: UUID, expected_type: type[UUID], label: str) -> None:
    """校验 UUID 运行时类型。

    Args:
        value: 待校验 UUID。
        expected_type: 目标 UUID 类型。
        label: 字段名。

    Raises:
        TypeError: 类型不符时抛出。
    """

    if not isinstance(value, expected_type):
        raise TypeError(f"{label} 类型非法")


def _require_positive_int(value: int, label: str) -> None:
    """校验精确正整数并拒绝 bool。

    Args:
        value: 待校验整数。
        label: 字段名。

    Raises:
        TypeError: 不是精确整数时抛出。
        ValueError: 非正数时抛出。
    """

    if type(value) is not int:
        raise TypeError(f"{label} 必须是 int")
    if value <= 0:
        raise ValueError(f"{label} 必须为正整数")


def _require_nonnegative_int(value: int, label: str) -> None:
    """校验精确非负整数。

    Args:
        value: 待校验整数。
        label: 字段名。

    Raises:
        TypeError: 不是精确整数时抛出。
        ValueError: 为负数时抛出。
    """

    if type(value) is not int:
        raise TypeError(f"{label} 必须是 int")
    if value < 0:
        raise ValueError(f"{label} 不得为负数")


def _require_nonblank(value: str, label: str) -> None:
    """校验非空且无首尾空白文本。

    Args:
        value: 待校验文本。
        label: 字段名。

    Raises:
        TypeError: 不是文本时抛出。
        ValueError: 空白形态非法时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{label} 必须是 str")
    if not value or value != value.strip():
        raise ValueError(f"{label} 必须非空且无首尾空白")


def _require_sha256(value: str, label: str) -> None:
    """校验小写 64-hex SHA-256。

    Args:
        value: 待校验 hash。
        label: 字段名。

    Raises:
        ValueError: hash 形态非法时抛出。
    """

    if not isinstance(value, str) or _LOWER_HEX_64.fullmatch(value) is None:
        raise ValueError(f"{label} 必须是小写 64-hex SHA-256")


def _require_aware_utc(value: datetime, label: str) -> None:
    """校验 datetime 为 aware UTC。

    Args:
        value: 待校验时刻。
        label: 字段名。

    Raises:
        TypeError: 不是 datetime 时抛出。
        ValueError: 不是 UTC aware 时抛出。
    """

    if not isinstance(value, datetime):
        raise TypeError(f"{label} 必须是 datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} 必须是 aware UTC datetime")


def _require_date(value: date, label: str) -> None:
    """校验值是精确 calendar date。

    Args:
        value: 待校验日期。
        label: 字段名。

    Raises:
        TypeError: datetime 或其它类型时抛出。
    """

    if type(value) is not date:
        raise TypeError(f"{label} 必须是 date")


def _decode_source_document(
    document: CanonicalJobDocument,
    *,
    schema_name: str,
    schema_version: int,
    max_bytes: int,
) -> dict[str, JsonValue]:
    """按显式 schema identity 与 byte cap 解码 Source document。

    Args:
        document: 待解析文档。
        schema_name: 期望 schema 名。
        schema_version: 期望 schema 版本。
        max_bytes: 调用方责任对应的 canonical bytes 上限。

    Returns:
        严格 JSON 根对象。

    Raises:
        TypeError: 参数类型非法时抛出。
        ValueError: schema、bytes、hash、cap 或根类型漂移时抛出。
    """

    if not isinstance(document, CanonicalJobDocument):
        raise TypeError("document 必须是 CanonicalJobDocument")
    _require_nonblank(schema_name, "schema_name")
    _require_positive_int(schema_version, "schema_version")
    _require_positive_int(max_bytes, "max_bytes")
    if document.schema_name != schema_name or document.schema_version != schema_version:
        raise ValueError("canonical document schema identity 漂移")
    if len(document.canonical_bytes) > max_bytes:
        raise ValueError("canonical document 超过大小上限")
    try:
        text = document.canonical_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("canonical document 必须是 UTF-8") from None
    parsed = parse_canonical_document(
        text,
        schema_name=schema_name,
        schema_version=schema_version,
    )
    if parsed.sha256 != document.sha256:
        raise ValueError("canonical document hash 漂移")
    raw: JsonValue = json.loads(text)
    if type(raw) is not dict:
        raise ValueError("canonical document 根必须是 JSON object")
    return raw


def _require_canonical_document_size(
    document: CanonicalJobDocument,
    *,
    max_bytes: int,
) -> None:
    """校验 canonical document 未超过调用方声明的字节上限。

    Args:
        document: 已构造的 canonical document。
        max_bytes: 调用方职责对应的精确字节上限。

    Raises:
        TypeError: document 类型非法时抛出。
        ValueError: 上限非法或 canonical bytes 超限时抛出。
    """

    if not isinstance(document, CanonicalJobDocument):
        raise TypeError("document 必须是 CanonicalJobDocument")
    _require_positive_int(max_bytes, "max_bytes")
    if len(document.canonical_bytes) > max_bytes:
        raise ValueError("canonical document 超过大小上限")


def _require_json_object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    """把 JSON union 收窄为对象。

    Args:
        value: JSON 值。
        label: 字段名。

    Returns:
        JSON 对象。

    Raises:
        ValueError: 值不是对象时抛出。
    """

    if type(value) is not dict:
        raise ValueError(f"{label} 必须是 JSON object")
    return value


def _require_exact_keys(value: dict[str, JsonValue], expected: frozenset[str], label: str) -> None:
    """校验 JSON 对象恰含固定 key。

    Args:
        value: JSON 对象。
        expected: 固定 key 集。
        label: 字段名。

    Raises:
        ValueError: missing 或 unknown key 存在时抛出。
    """

    if frozenset(value) != expected:
        raise ValueError(f"{label} key 集不闭合")


def _require_json_text(value: JsonValue, label: str) -> str:
    """把 JSON 值收窄为非空文本。

    Args:
        value: JSON 值。
        label: 字段名。

    Returns:
        严格文本。

    Raises:
        ValueError: 文本形态非法时抛出。
    """

    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} 必须是非空无首尾空白文本")
    return value


def _require_json_positive_int(value: JsonValue, label: str) -> int:
    """把 JSON 值收窄为正整数。

    Args:
        value: JSON 值。
        label: 字段名。

    Returns:
        正整数。

    Raises:
        ValueError: 类型或范围非法时抛出。
    """

    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} 必须为正整数")
    return value


def _require_json_nonnegative_int(value: JsonValue, label: str) -> int:
    """把 JSON 值收窄为非负整数。

    Args:
        value: JSON 值。
        label: 字段名。

    Returns:
        非负整数。

    Raises:
        ValueError: 类型或范围非法时抛出。
    """

    if type(value) is not int or value < 0:
        raise ValueError(f"{label} 必须为非负整数")
    return value


def _require_json_schema_version(value: JsonValue, label: str) -> None:
    """校验 JSON schema version 精确为整数 ``1``。

    Args:
        value: JSON schema version 值。
        label: 字段名。

    Raises:
        ValueError: 值不是精确整数 ``1``，包括 bool 冒充时抛出。
    """

    if type(value) is not int or value != 1:
        raise ValueError(f"{label} 必须是整数 1")


def _parse_uuid_text(value: JsonValue, label: str) -> UUID:
    """把 canonical UUID 文本解析为 UUID。

    Args:
        value: JSON 值。
        label: 字段名。

    Returns:
        UUID 值。

    Raises:
        ValueError: UUID 文本不规范时抛出。
    """

    text = _require_json_text(value, label)
    try:
        parsed = UUID(text)
    except ValueError:
        raise ValueError(f"{label} 必须是 UUID") from None
    if str(parsed) != text:
        raise ValueError(f"{label} 必须是 canonical UUID")
    return parsed


def _parse_date_text(value: JsonValue, label: str) -> date:
    """解析 canonical ISO calendar date。

    Args:
        value: JSON 值。
        label: 字段名。

    Returns:
        Calendar date。

    Raises:
        ValueError: 日期文本非法或非 canonical 时抛出。
    """

    text = _require_json_text(value, label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{label} 必须是 ISO date") from None
    if parsed.isoformat() != text:
        raise ValueError(f"{label} 必须是 canonical ISO date")
    return parsed


def _parse_datetime_text(value: JsonValue, label: str) -> datetime:
    """解析 canonical aware UTC datetime。

    Args:
        value: JSON 值。
        label: 字段名。

    Returns:
        Aware UTC datetime。

    Raises:
        ValueError: 时间非法或非 canonical 时抛出。
    """

    text = _require_json_text(value, label)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{label} 必须是 ISO datetime") from None
    _require_aware_utc(parsed, label)
    if parsed.isoformat() != text:
        raise ValueError(f"{label} 必须是 canonical ISO datetime")
    return parsed


@dataclass(frozen=True, slots=True)
class FinsDisclosureSubscriptionConfig:
    """Fins 市场披露订阅的严格配置。"""

    forms: tuple[str, ...]
    lookback_days: int
    freshness_max_age_days: int
    failing_after: int
    disable_after: int
    max_documents_per_sync: int = MAX_SOURCE_DOCUMENTS

    def __post_init__(self) -> None:
        """校验 forms、阈值与文档上限。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: 范围或 canonical 形态非法时抛出。
        """

        if type(self.forms) is not tuple:
            raise TypeError("forms 必须是精确 tuple")
        forms = tuple(self.forms)
        object.__setattr__(self, "forms", forms)
        if not 1 <= len(forms) <= 16:
            raise ValueError("forms 数量必须为 1..16")
        for form in forms:
            if type(form) is not str or _CANONICAL_FORM.fullmatch(form) is None:
                raise ValueError("form 必须是 canonical uppercase form")
        if len(set(forms)) != len(forms):
            raise ValueError("forms 必须唯一")
        _require_positive_int(self.lookback_days, "lookback_days")
        _require_positive_int(self.freshness_max_age_days, "freshness_max_age_days")
        _require_positive_int(self.failing_after, "failing_after")
        _require_positive_int(self.disable_after, "disable_after")
        _require_positive_int(self.max_documents_per_sync, "max_documents_per_sync")
        if self.lookback_days > 3660 or self.freshness_max_age_days > 3660:
            raise ValueError("lookback/freshness 天数不得超过 3660")
        if self.failing_after >= self.disable_after:
            raise ValueError("failing_after 必须小于 disable_after")
        if self.max_documents_per_sync > MAX_SOURCE_DOCUMENTS:
            raise ValueError("max_documents_per_sync 不得超过 500")


@dataclass(frozen=True, slots=True)
class SourceSyncEnqueueRequest:
    """手工 Source Sync 入队调用意图。"""

    subscription_id: SourceSubscriptionId
    expected_subscription_version: int
    trigger_id: UUID
    available_at: datetime
    deadline_at: datetime

    def __post_init__(self) -> None:
        """校验标识、版本和时间窗口。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: 版本或时间关系非法时抛出。
        """

        if not isinstance(self.subscription_id, SourceSubscriptionId):
            raise TypeError("subscription_id 必须是 SourceSubscriptionId")
        _require_positive_int(self.expected_subscription_version, "expected_subscription_version")
        _require_exact_type(self.trigger_id, UUID, "trigger_id")
        _require_aware_utc(self.available_at, "available_at")
        _require_aware_utc(self.deadline_at, "deadline_at")
        if self.deadline_at <= self.available_at:
            raise ValueError("deadline_at 必须晚于 available_at")


@dataclass(frozen=True, slots=True)
class SourcePollingScheduleRequest:
    """Source polling schedule draft 的调用意图。"""

    subscription_id: SourceSubscriptionId
    expected_subscription_version: int
    cron_expression: str
    timezone_name: str
    misfire_policy: ScheduleMisfirePolicy
    misfire_grace_seconds: int
    job_deadline_seconds: int
    schedule_key: str | None = None

    def __post_init__(self) -> None:
        """校验 schedule shape，不读取 mutable source state。

        Raises:
            TypeError: 字段类型非法时抛出。
            ValueError: 文本或整数非法时抛出。
        """

        if not isinstance(self.subscription_id, SourceSubscriptionId):
            raise TypeError("subscription_id 必须是 SourceSubscriptionId")
        _require_positive_int(self.expected_subscription_version, "expected_subscription_version")
        _require_nonblank(self.cron_expression, "cron_expression")
        _require_nonblank(self.timezone_name, "timezone_name")
        if not isinstance(self.misfire_policy, ScheduleMisfirePolicy):
            raise TypeError("misfire_policy 必须是 ScheduleMisfirePolicy")
        _require_positive_int(self.misfire_grace_seconds, "misfire_grace_seconds")
        _require_positive_int(self.job_deadline_seconds, "job_deadline_seconds")
        if self.schedule_key is not None:
            _require_nonblank(self.schedule_key, "schedule_key")


def parse_fins_disclosure_subscription_config(value: JsonValue) -> FinsDisclosureSubscriptionConfig:
    """严格解析 Fins subscription config 的 closed JSON shape。

    Args:
        value: SourceDefinition 中的 JSON 配置。

    Returns:
        Strict Fins config DTO。

    Raises:
        ValueError: missing/unknown key 或字段非法时抛出。
    """

    raw = _require_json_object(value, "config")
    required_keys = frozenset(
        {
            "forms",
            "lookback_days",
            "freshness_max_age_days",
            "failing_after",
            "disable_after",
        }
    )
    keys = frozenset(raw)
    if keys not in {required_keys, required_keys | {"max_documents_per_sync"}}:
        raise ValueError("config key 集不闭合")
    raw_forms = raw["forms"]
    if type(raw_forms) is not list:
        raise ValueError("forms 必须是 JSON array")
    forms: list[str] = []
    for raw_form in raw_forms:
        forms.append(_require_json_text(raw_form, "form"))
    max_documents_per_sync = MAX_SOURCE_DOCUMENTS
    if "max_documents_per_sync" in raw:
        max_documents_per_sync = _require_json_positive_int(
            raw["max_documents_per_sync"],
            "max_documents_per_sync",
        )
    return FinsDisclosureSubscriptionConfig(
        forms=tuple(forms),
        lookback_days=_require_json_positive_int(raw["lookback_days"], "lookback_days"),
        freshness_max_age_days=_require_json_positive_int(
            raw["freshness_max_age_days"],
            "freshness_max_age_days",
        ),
        failing_after=_require_json_positive_int(raw["failing_after"], "failing_after"),
        disable_after=_require_json_positive_int(raw["disable_after"], "disable_after"),
        max_documents_per_sync=max_documents_per_sync,
    )


__all__ = [
    "FINS_SOURCE_DEFINITION_KEY",
    "MAX_SOURCE_DOCUMENTS",
    "MAX_SOURCE_DOCUMENT_BYTES",
    "SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME",
    "SOURCE_EXECUTION_SNAPSHOT_SCHEMA_NAME",
    "SOURCE_SYNC_JOB_DESCRIPTOR",
    "SOURCE_SYNC_JOB_TYPE",
    "SOURCE_SYNC_PAYLOAD_SCHEMA_NAME",
    "SOURCE_SYNC_PAYLOAD_SCHEMA_VERSION",
    "SOURCE_SYNC_RECEIPT_SCHEMA_NAME",
    "SOURCE_SYNC_RESULT_SCHEMA_NAME",
    "FinsDisclosureSubscriptionConfig",
    "SourceBindingDisposition",
    "SourceConnectorKey",
    "SourcePollingScheduleRequest",
    "SourceServiceInputError",
    "SourceServiceUnavailableError",
    "SourceSyncEnqueueRequest",
    "SourceSyncErrorCode",
    "SourceSyncExecutionRejected",
    "SourceSyncExecutionRejectionCode",
    "SourceSyncOrigin",
    "SourceSyncOutcome",
    "SourceSyncRepositoryFailure",
    "SourceSyncRepositoryFailureCode",
    "SourceSyncRequestRejected",
    "SourceSyncRequestRejectionCode",
    "parse_fins_disclosure_subscription_config",
]
