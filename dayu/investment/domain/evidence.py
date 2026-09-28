"""投资研究证据的纯领域 DTO、严格 locator 结构和状态规则。

本模块只验证可持久化的局部结构。Fins 片段当前是否存在，以及审查人
是否持有效权限，均由各自的运行时 owner 在数据库事务中验证。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid5

_REPOSITORY_ID = "dayu.fins.public.v1"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_TICKER = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]*\Z")
_DOCUMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]*\Z")
_BOUNDED_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]{0,127}\Z")
_CURRENCY = re.compile(r"[A-Z]{3}\Z")
_LOCATOR_KEYS = frozenset({
    "repository_id", "ticker", "document_id", "source_kind", "artifact_kind",
    "document_version", "source_fingerprint", "primary_content_sha256",
    "locator_kind", "locator_payload", "locator_content_sha256",
})
_COPY_NAMESPACE = "dayu:evidence-link-copy:v1:"
_DECIMAL_MAX_SCALE = 12
_DECIMAL_MAX_DIGITS = 38

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _require_uuid(value: UUID, label: str) -> None:
    """校验 caller 提供的非 nil UUID。

    Args:
        value: 待校验的 UUID。
        label: 字段名称。

    Returns:
        无。

    Raises:
        TypeError: 值不是 UUID。
        ValueError: 值为 nil UUID。
    """

    if not isinstance(value, UUID):
        raise TypeError(f"{label} 必须是 UUID")
    if value.int == 0:
        raise ValueError(f"{label} 不得为 nil UUID")


def _require_optional_uuid(value: UUID | None, label: str) -> None:
    """校验可空 UUID。

    Args:
        value: 可空 UUID。
        label: 字段名称。

    Returns:
        无。

    Raises:
        TypeError: 非空值不是 UUID。
        ValueError: 非空值为 nil UUID。
    """

    if value is not None:
        _require_uuid(value, label)


def _require_int(value: int, label: str, *, minimum: int = 0) -> None:
    """校验真实整数及下界，拒绝 bool 冒充 int。

    Args:
        value: 待校验整数。
        label: 字段名称。
        minimum: 允许的最小值。

    Returns:
        无。

    Raises:
        TypeError: 值不是真实 int。
        ValueError: 值低于下界。
    """

    if type(value) is not int:
        raise TypeError(f"{label} 必须是整数")
    if value < minimum:
        raise ValueError(f"{label} 低于最小值")


def _require_text(value: str, label: str) -> None:
    """校验非空、无首尾空白的文本。

    Args:
        value: 待校验文本。
        label: 字段名称。

    Returns:
        无。

    Raises:
        TypeError: 值不是字符串。
        ValueError: 值为空或有首尾空白。
    """

    if type(value) is not str:
        raise TypeError(f"{label} 必须是字符串")
    if not value or value != value.strip():
        raise ValueError(f"{label} 不能为空或含首尾空白")


def _require_pattern(value: str, label: str, pattern: re.Pattern[str]) -> None:
    """校验文本匹配明确的 canonical 形态。

    Args:
        value: 待校验文本。
        label: 字段名称。
        pattern: 全串匹配正则。

    Returns:
        无。

    Raises:
        TypeError: 值不是文本。
        ValueError: 文本不匹配形态。
    """

    _require_text(value, label)
    if pattern.fullmatch(value) is None:
        raise ValueError(f"{label} 不是 canonical 形态")


def _require_utc(value: datetime, label: str) -> None:
    """校验时间为明确的 aware UTC。

    Args:
        value: 待校验时间。
        label: 字段名称。

    Returns:
        无。

    Raises:
        TypeError: 值不是 datetime。
        ValueError: 值没有 UTC 时区。
    """

    if type(value) is not datetime:
        raise TypeError(f"{label} 必须是 datetime")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} 必须是 aware UTC")


def _require_date(value: date, label: str) -> None:
    """校验真实 date，拒绝 datetime 冒充。

    Args:
        value: 待校验日期。
        label: 字段名称。

    Returns:
        无。

    Raises:
        TypeError: 值不是真实 date。
    """

    if type(value) is not date:
        raise TypeError(f"{label} 必须是 date")


def _require_enum(value: Enum, enum_type: type[Enum], label: str) -> None:
    """校验 closed enum 使用真实成员，而非同值字符串。

    Args:
        value: 待校验成员。
        enum_type: 允许的枚举类。
        label: 字段名称。

    Returns:
        无。

    Raises:
        TypeError: 值不是指定枚举成员。
    """

    if type(value) is not enum_type:
        raise TypeError(f"{label} 必须是 {enum_type.__name__} 成员")


def _require_hex64(value: str, label: str) -> None:
    """校验小写 SHA-256 十六进制形态。

    Args:
        value: 待校验文本。
        label: 字段名称。

    Returns:
        无。

    Raises:
        TypeError: 值不是文本。
        ValueError: 值不是小写 64 位十六进制。
    """

    _require_pattern(value, label, _HEX64)


def _require_decimal(value: Decimal, label: str) -> None:
    """按未舍入值校验 PostgreSQL NUMERIC 38/12 契约。

    Args:
        value: 原始 Decimal。
        label: 字段名称。

    Returns:
        无。

    Raises:
        TypeError: 值不是 Decimal。
        ValueError: 非有限、scale 或总位数越界。
    """

    if type(value) is not Decimal:
        raise TypeError(f"{label} 必须是 Decimal，禁止 float")
    if not value.is_finite():
        raise ValueError(f"{label} 必须是有限数值")
    _, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError(f"{label} 必须是有限数值")
    scale = max(0, -exponent)
    if scale > _DECIMAL_MAX_SCALE:
        raise ValueError(f"{label} scale 超过 12")
    integer_digits = 0 if value.copy_abs() < 1 else max(0, len(digits) + exponent)
    if max(1, integer_digits + scale) > _DECIMAL_MAX_DIGITS:
        raise ValueError(f"{label} 总位数超过 38")


class FactValueKind(str, Enum):
    """事实值的闭合类型。"""

    DECIMAL = "decimal"
    TEXT = "text"
    DATE = "date"
    BOOLEAN = "boolean"


class VerificationStatus(str, Enum):
    """事实修订的核验快照状态。"""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    INVALIDATED = "invalidated"


class ClaimStatus(str, Enum):
    """ClaimVersion 的闭合状态。"""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"
    REVIEW_REQUIRED = "review_required"
    SUPERSEDED = "superseded"


class ConfidenceBand(str, Enum):
    """信息置信度，不构成审核授权。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ImpactHorizon(str, Enum):
    """影响时域的闭合分类。"""

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class EvidenceRelation(str, Enum):
    """链接与论断的关系。"""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"


class EvidenceMode(str, Enum):
    """新版本完整证据集合的生成方式。"""

    REPLACE_ALL = "replace_all"
    COPY_PREVIOUS = "copy_previous"


class ClaimTransitionKind(str, Enum):
    """ClaimVersion 的闭合动作来源。"""

    CLAIM_CREATE = "claim_create"
    CONTENT_REVISION = "content_revision"
    SUBMIT_REVIEW = "submit_review"
    BEGIN_REVISION = "begin_revision"
    REVIEW_DECISION = "review_decision"
    EXPIRY = "expiry"
    CONFLICT_RESOLUTION = "conflict_resolution"


class ConflictStatus(str, Enum):
    """冲突行的闭合状态。"""

    OPEN = "open"
    RESOLVED = "resolved"


class CandidateOrigin(str, Enum):
    """候选内容来源。"""

    AGENT = "agent"
    HUMAN = "human"


class CandidateStatus(str, Enum):
    """候选晋升阶段。"""

    PROPOSED = "proposed"
    VALIDATED = "validated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class LocalEligibilityReason(str, Enum):
    """局部筛选结果；不表示最终 Fins 可用性。"""

    EXPIRED = "expired"
    MATERIAL_CONFLICT = "material_conflict"
    NOT_APPROVED = "not_approved"
    MISSING_SUPPORT = "missing_support"
    LOCALLY_READY_REQUIRES_FINS_VALIDATION = "locally_ready_requires_fins_validation"


class LocatorSourceKind(str, Enum):
    """Fins v1 projection 镜像中的来源分类。"""

    FILING = "filing"
    MATERIAL = "material"


class LocatorArtifactKind(str, Enum):
    """Fins v1 projection 镜像中的产物分类。"""

    SOURCE = "source"
    PROCESSED = "processed"


class LocatorKind(str, Enum):
    """Fins v1 projection 镜像中的五种定位形状。"""

    DOCUMENT = "document"
    PAGE = "page"
    SECTION = "section"
    TABLE_CELL = "table_cell"
    XBRL_FACT = "xbrl_fact"


@dataclass(frozen=True, slots=True)
class DocumentLocatorPayload:
    """document 定位没有额外字段。"""

    def to_dict(self) -> dict[str, JsonValue]:
        """生成空 payload。

        Args:
            无。

        Returns:
            空对象。

        Raises:
            无。
        """

        return {}


@dataclass(frozen=True, slots=True)
class PageLocatorPayload:
    """page 定位的正整数页码。"""

    page_no: int

    def __post_init__(self) -> None:
        """校验页码。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 页码不是整数。
            ValueError: 页码非正。
        """

        _require_int(self.page_no, "page_no", minimum=1)

    def to_dict(self) -> dict[str, JsonValue]:
        """生成 page payload。

        Args:
            无。

        Returns:
            仅有页码的对象。

        Raises:
            无。
        """

        return {"page_no": self.page_no}


@dataclass(frozen=True, slots=True)
class SectionLocatorPayload:
    """section 定位的引用。"""

    section_ref: str

    def __post_init__(self) -> None:
        """校验章节引用。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 引用不是文本。
            ValueError: 引用为空或含首尾空白。
        """

        _require_text(self.section_ref, "section_ref")

    def to_dict(self) -> dict[str, JsonValue]:
        """生成 section payload。

        Args:
            无。

        Returns:
            仅有章节引用的对象。

        Raises:
            无。
        """

        return {"section_ref": self.section_ref}


@dataclass(frozen=True, slots=True)
class TableCellLocatorPayload:
    """table_cell 定位的表格、行号和列名。"""

    table_ref: str
    row_index: int
    column: str

    def __post_init__(self) -> None:
        """校验表格单元格坐标。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: 文本为空或行号为负。
        """

        _require_text(self.table_ref, "table_ref")
        _require_int(self.row_index, "row_index")
        _require_text(self.column, "column")

    def to_dict(self) -> dict[str, JsonValue]:
        """生成 table_cell payload。

        Args:
            无。

        Returns:
            精确三字段对象。

        Raises:
            无。
        """

        return {"table_ref": self.table_ref, "row_index": self.row_index, "column": self.column}


@dataclass(frozen=True, slots=True)
class XbrlFactLocatorPayload:
    """xbrl_fact 定位的 concept 与事实 hash。"""

    concept: str
    fact_sha256: str

    def __post_init__(self) -> None:
        """校验 XBRL 事实定位。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段不是文本。
            ValueError: concept 或 hash 形态错误。
        """

        _require_text(self.concept, "concept")
        _require_hex64(self.fact_sha256, "fact_sha256")

    def to_dict(self) -> dict[str, JsonValue]:
        """生成 xbrl_fact payload。

        Args:
            无。

        Returns:
            精确二字段对象。

        Raises:
            无。
        """

        return {"concept": self.concept, "fact_sha256": self.fact_sha256}


LocatorPayload: TypeAlias = (
    DocumentLocatorPayload | PageLocatorPayload | SectionLocatorPayload
    | TableCellLocatorPayload | XbrlFactLocatorPayload
)


def _parse_payload(kind: LocatorKind, raw: JsonValue) -> LocatorPayload:
    """按 locator kind 构造严格 payload。

    Args:
        kind: 定位器类型。
        raw: 解码的 JSON 值。

    Returns:
        对应的不可变 payload。

    Raises:
        TypeError: payload 不是 JSON 对象。
        ValueError: 键集或字段值错误。
    """

    if type(raw) is not dict:
        raise TypeError("locator_payload 必须是对象")
    if kind is LocatorKind.DOCUMENT:
        if raw:
            raise ValueError("document payload 必须为空")
        return DocumentLocatorPayload()
    if kind is LocatorKind.PAGE:
        if set(raw) != {"page_no"}:
            raise ValueError("page payload 键集错误")
        page_no = raw["page_no"]
        if type(page_no) is not int:
            raise TypeError("page_no 必须是整数")
        return PageLocatorPayload(page_no)
    if kind is LocatorKind.SECTION:
        if set(raw) != {"section_ref"}:
            raise ValueError("section payload 键集错误")
        section_ref = raw["section_ref"]
        if type(section_ref) is not str:
            raise TypeError("section_ref 必须是文本")
        return SectionLocatorPayload(section_ref)
    if kind is LocatorKind.TABLE_CELL:
        if set(raw) != {"table_ref", "row_index", "column"}:
            raise ValueError("table_cell payload 键集错误")
        table_ref, row_index, column = raw["table_ref"], raw["row_index"], raw["column"]
        if type(table_ref) is not str or type(row_index) is not int or type(column) is not str:
            raise TypeError("table_cell payload 字段类型错误")
        return TableCellLocatorPayload(table_ref, row_index, column)
    if kind is LocatorKind.XBRL_FACT:
        if set(raw) != {"concept", "fact_sha256"}:
            raise ValueError("xbrl_fact payload 键集错误")
        concept, fact_sha256 = raw["concept"], raw["fact_sha256"]
        if type(concept) is not str or type(fact_sha256) is not str:
            raise TypeError("xbrl_fact payload 字段类型错误")
        return XbrlFactLocatorPayload(concept, fact_sha256)
    raise ValueError("未知 locator kind")


def _read_locator_text(raw: dict[str, JsonValue], key: str) -> str:
    """读取 locator 文本字段并为静态类型检查收窄。

    Args:
        raw: 已校验根键集的 JSON 对象。
        key: 必须存在的文本键。

    Returns:
        原样文本。

    Raises:
        TypeError: 字段不是字符串。
    """

    value = raw[key]
    if type(value) is not str:
        raise TypeError(f"{key} 必须是文本")
    return value


@dataclass(frozen=True, slots=True)
class EvidenceLocatorSnapshot:
    """Fins v1 无路径 projection 的投资域结构镜像。"""

    repository_id: str
    ticker: str
    document_id: str
    source_kind: LocatorSourceKind
    artifact_kind: LocatorArtifactKind
    document_version: str
    source_fingerprint: str
    primary_content_sha256: str
    locator_kind: LocatorKind
    locator_payload: LocatorPayload
    locator_content_sha256: str

    def __post_init__(self) -> None:
        """校验十一字段及 source/locator 配对。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 枚举或 payload 类型错误。
            ValueError: 身份、hash 或配对错误。
        """

        if self.repository_id != _REPOSITORY_ID:
            raise ValueError("未知 repository_id")
        _require_pattern(self.ticker, "ticker", _TICKER)
        _require_pattern(self.document_id, "document_id", _DOCUMENT_ID)
        _require_enum(self.source_kind, LocatorSourceKind, "source_kind")
        _require_enum(self.artifact_kind, LocatorArtifactKind, "artifact_kind")
        _require_text(self.document_version, "document_version")
        _require_hex64(self.source_fingerprint, "source_fingerprint")
        _require_hex64(self.primary_content_sha256, "primary_content_sha256")
        _require_enum(self.locator_kind, LocatorKind, "locator_kind")
        _require_hex64(self.locator_content_sha256, "locator_content_sha256")
        if self.locator_kind is LocatorKind.DOCUMENT:
            expected = DocumentLocatorPayload
        elif self.locator_kind is LocatorKind.PAGE:
            expected = PageLocatorPayload
        elif self.locator_kind is LocatorKind.SECTION:
            expected = SectionLocatorPayload
        elif self.locator_kind is LocatorKind.TABLE_CELL:
            expected = TableCellLocatorPayload
        else:
            expected = XbrlFactLocatorPayload
        if type(self.locator_payload) is not expected:
            raise TypeError("locator_kind 与 payload 类型不配对")
        if self.artifact_kind is LocatorArtifactKind.SOURCE and self.locator_kind is not LocatorKind.DOCUMENT:
            raise ValueError("source artifact 只允许 document locator")

    def to_dict(self) -> dict[str, JsonValue]:
        """生成精确十一键的无路径字典。

        Args:
            无。

        Returns:
            新建的 JSON 对象。

        Raises:
            无。
        """

        return {
            "repository_id": self.repository_id,
            "ticker": self.ticker,
            "document_id": self.document_id,
            "source_kind": self.source_kind.value,
            "artifact_kind": self.artifact_kind.value,
            "document_version": self.document_version,
            "source_fingerprint": self.source_fingerprint,
            "primary_content_sha256": self.primary_content_sha256,
            "locator_kind": self.locator_kind.value,
            "locator_payload": self.locator_payload.to_dict(),
            "locator_content_sha256": self.locator_content_sha256,
        }

    def canonical_bytes(self) -> bytes:
        """生成 sorted/compact/UTF-8 canonical JSON bytes。

        Args:
            无。

        Returns:
            可持久化与指纹计算的 bytes。

        Raises:
            ValueError: 数据不可 JSON 序列化。
        """

        return json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")

    @classmethod
    def from_dict(cls, raw: JsonValue) -> EvidenceLocatorSnapshot:
        """从 JSONB 读回值严格重建结构镜像。

        Args:
            raw: 解码后的 projection 对象。

        Returns:
            已验证的不可变 locator。

        Raises:
            TypeError: 根或字段类型非法。
            ValueError: 键集、枚举或值非法。
        """

        if type(raw) is not dict:
            raise TypeError("locator 必须是 JSON 对象")
        if set(raw) != _LOCATOR_KEYS:
            raise ValueError("locator 十一键集合错误")
        source_kind = LocatorSourceKind(_read_locator_text(raw, "source_kind"))
        artifact_kind = LocatorArtifactKind(_read_locator_text(raw, "artifact_kind"))
        locator_kind = LocatorKind(_read_locator_text(raw, "locator_kind"))
        payload = _parse_payload(locator_kind, raw["locator_payload"])
        return cls(
            repository_id=_read_locator_text(raw, "repository_id"),
            ticker=_read_locator_text(raw, "ticker"),
            document_id=_read_locator_text(raw, "document_id"), source_kind=source_kind,
            artifact_kind=artifact_kind,
            document_version=_read_locator_text(raw, "document_version"),
            source_fingerprint=_read_locator_text(raw, "source_fingerprint"),
            primary_content_sha256=_read_locator_text(raw, "primary_content_sha256"),
            locator_kind=locator_kind, locator_payload=payload,
            locator_content_sha256=_read_locator_text(raw, "locator_content_sha256"),
        )

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> EvidenceLocatorSnapshot:
        """解析 ingress JSON bytes，拒绝 BOM、重复键与尾随数据。

        Args:
            raw: UTF-8 JSON bytes。

        Returns:
            已验证的不可变 locator。

        Raises:
            TypeError: 输入不是 bytes。
            ValueError: 编码、JSON 或结构非法。
        """

        if type(raw) is not bytes:
            raise TypeError("locator JSON 必须是 bytes")
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("locator JSON 不允许 BOM")
        try:
            decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                                 parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("locator JSON 非法") from exc
        return cls.from_dict(decoded)


def _unique_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """在 JSON 解析阶段拒绝重复字段。

    Args:
        pairs: 一个对象中的原始键值对序列。

    Returns:
        无重复键的 JSON 对象。

    Raises:
        ValueError: 对象包含重复键。
    """

    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("locator JSON 包含重复键")
        result[key] = value
    return result


def _reject_constant(value: str) -> JsonValue:
    """拒绝 JSON 标准之外的 NaN 与 Infinity 常量。

    Args:
        value: 非标准常量名称。

    Returns:
        永不返回。

    Raises:
        ValueError: 总是拒绝非标准常量。
    """

    raise ValueError(f"locator JSON 非法常量 {value}")


@dataclass(frozen=True, slots=True)
class FactValue:
    """恰有一种 payload 的事实值，单位约束随值类型验证。"""

    kind: FactValueKind
    value_decimal: Decimal | None = None
    value_text: str | None = None
    value_date: date | None = None
    value_boolean: bool | None = None
    unit_code: str | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        """校验 tagged union、未舍入数值和单位闭合。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 值或枚举类型错误。
            ValueError: payload 数量、数值精度或单位错误。
        """

        _require_enum(self.kind, FactValueKind, "kind")
        present = sum(value is not None for value in (
            self.value_decimal, self.value_text, self.value_date, self.value_boolean,
        ))
        if present != 1:
            raise ValueError("FactValue 必须恰有一种 payload")
        if self.kind is FactValueKind.DECIMAL:
            if self.value_decimal is None:
                raise ValueError("decimal payload 缺失")
            _require_decimal(self.value_decimal, "value_decimal")
            if self.unit_code is None:
                raise ValueError("decimal 值必须提供 unit_code")
            _require_pattern(self.unit_code, "unit_code", _BOUNDED_CODE)
            if self.unit_code == "currency":
                if self.currency is None:
                    raise ValueError("currency unit 必须提供 currency")
                _require_pattern(self.currency, "currency", _CURRENCY)
            elif self.currency is not None:
                raise ValueError("非 currency unit 不得携带 currency")
        elif self.kind is FactValueKind.TEXT:
            if self.value_text is None:
                raise ValueError("text payload 缺失")
            _require_text(self.value_text, "value_text")
        elif self.kind is FactValueKind.DATE:
            if self.value_date is None:
                raise ValueError("date payload 缺失")
            _require_date(self.value_date, "value_date")
        elif self.kind is FactValueKind.BOOLEAN:
            if type(self.value_boolean) is not bool:
                raise TypeError("value_boolean 必须是真实 bool")
        if self.kind is not FactValueKind.DECIMAL and (self.unit_code is not None or self.currency is not None):
            raise ValueError("非 numeric 值不得携带单位或货币")
        if self.kind is not FactValueKind.DECIMAL and self.value_decimal is not None:
            raise ValueError("非 decimal 类型不得携带数值")
        if self.kind is not FactValueKind.TEXT and self.value_text is not None:
            raise ValueError("非 text 类型不得携带文本")
        if self.kind is not FactValueKind.DATE and self.value_date is not None:
            raise ValueError("非 date 类型不得携带日期")
        if self.kind is not FactValueKind.BOOLEAN and self.value_boolean is not None:
            raise ValueError("非 boolean 类型不得携带布尔值")


@dataclass(frozen=True, slots=True)
class FactPitTimes:
    """Fact 的四个原样 PIT 时间与可选观测区间。"""

    period_start: date | None
    period_end: date | None
    effective_at: datetime
    published_at: datetime
    ingested_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        """验证日期区间与三个资料到达时刻的先后。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 日期或时间类型错误。
            ValueError: 区间倒置、时间非 UTC 或资料时间倒置。
        """

        if self.period_start is not None:
            _require_date(self.period_start, "period_start")
        if self.period_end is not None:
            _require_date(self.period_end, "period_end")
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("period_start 与 period_end 必须同时为空或同时提供")
        if self.period_start is not None and self.period_end is not None and self.period_start > self.period_end:
            raise ValueError("period_start 不得晚于 period_end")
        _require_utc(self.effective_at, "effective_at")
        _require_utc(self.published_at, "published_at")
        _require_utc(self.ingested_at, "ingested_at")
        _require_utc(self.available_at, "available_at")
        if self.ingested_at < self.published_at or self.available_at < self.ingested_at:
            raise ValueError("必须满足 available_at >= ingested_at >= published_at")


@dataclass(frozen=True, slots=True)
class FactPitProjection:
    """供后续 PIT 消费者读取的原样 revision 与四时间字段。"""

    revision_id: UUID
    prior_revision_id: UUID | None
    effective_at: datetime
    published_at: datetime
    ingested_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        """校验 PIT identity 与 UTC/可用时间顺序。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ID 或时间类型非法。
            ValueError: nil ID、非 UTC 或资料时序倒置。
        """

        _require_uuid(self.revision_id, "revision_id")
        _require_optional_uuid(self.prior_revision_id, "prior_revision_id")
        _require_utc(self.effective_at, "effective_at")
        _require_utc(self.published_at, "published_at")
        _require_utc(self.ingested_at, "ingested_at")
        _require_utc(self.available_at, "available_at")
        if self.ingested_at < self.published_at or self.available_at < self.ingested_at:
            raise ValueError("PIT 时间倒置")


@dataclass(frozen=True, slots=True)
class FactCreateRequest:
    """caller 供应 ID 的新 Fact revision 请求。"""

    id: UUID
    company_id: UUID
    security_id: UUID
    fact_series_id: UUID
    revision_no: int
    prior_fact_id: UUID | None
    fact_key: str
    metric: str
    locator: EvidenceLocatorSnapshot
    value: FactValue
    pit: FactPitTimes
    extractor_version: str
    verification_status: VerificationStatus
    verifier_user_id: UUID | None
    verified_at: datetime | None
    operation_id: UUID

    def __post_init__(self) -> None:
        """校验 revision 身份与原始 locator/value/PIT。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: 版本链或核验字段错误。
        """

        for label, value in (("id", self.id), ("company_id", self.company_id),
                             ("security_id", self.security_id),
                             ("fact_series_id", self.fact_series_id),
                             ("operation_id", self.operation_id)):
            _require_uuid(value, label)
        _require_optional_uuid(self.prior_fact_id, "prior_fact_id")
        _require_int(self.revision_no, "revision_no", minimum=1)
        if (self.revision_no == 1) != (self.prior_fact_id is None):
            raise ValueError("首版必须无 prior_fact_id；修订版必须提供 prior_fact_id")
        _require_pattern(self.fact_key, "fact_key", _BOUNDED_CODE)
        _require_pattern(self.metric, "metric", _BOUNDED_CODE)
        if type(self.locator) is not EvidenceLocatorSnapshot:
            raise TypeError("locator 必须是 EvidenceLocatorSnapshot")
        if type(self.value) is not FactValue:
            raise TypeError("value 必须是 FactValue")
        if type(self.pit) is not FactPitTimes:
            raise TypeError("pit 必须是 FactPitTimes")
        _require_text(self.extractor_version, "extractor_version")
        _require_enum(self.verification_status, VerificationStatus, "verification_status")
        _require_optional_uuid(self.verifier_user_id, "verifier_user_id")
        if self.verified_at is not None:
            _require_utc(self.verified_at, "verified_at")
        if self.verification_status is VerificationStatus.UNVERIFIED:
            if self.verifier_user_id is not None or self.verified_at is not None:
                raise ValueError("unverified 不得携带 verifier witness")
        elif self.verifier_user_id is None or self.verified_at is None:
            raise ValueError("核验状态必须携带 verifier witness")

    @property
    def locator_ticker(self) -> str:
        """从同一 locator 中取显式 DB ticker 列值。

        Args:
            无。

        Returns:
            原样 ticker。

        Raises:
            无。
        """

        return self.locator.ticker


@dataclass(frozen=True, slots=True)
class Fact:
    """已持久化的不可变 Fact revision 投影。"""

    id: UUID
    tenant_id: UUID
    request: FactCreateRequest
    operation_fingerprint: str
    created_at: datetime

    def __post_init__(self) -> None:
        """验证持久化身份、指纹和创建时间。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 请求类型错误。
            ValueError: 身份、指纹或时间错误。
        """

        _require_uuid(self.id, "id")
        _require_uuid(self.tenant_id, "tenant_id")
        if type(self.request) is not FactCreateRequest:
            raise TypeError("request 必须是 FactCreateRequest")
        if self.id != self.request.id:
            raise ValueError("Fact ID 与 request 不一致")
        _require_hex64(self.operation_fingerprint, "operation_fingerprint")
        _require_utc(self.created_at, "created_at")

    @property
    def revision_id(self) -> UUID:
        """将 Fact ID 原样映射为 PIT revision_id。

        Args:
            无。

        Returns:
            当前 Fact ID。

        Raises:
            无。
        """

        return self.id

    @property
    def prior_revision_id(self) -> UUID | None:
        """将 prior_fact_id 原样映射为 PIT prior_revision_id。

        Args:
            无。

        Returns:
            上一 revision ID 或空。

        Raises:
            无。
        """

        return self.request.prior_fact_id

    def to_pit_projection(self) -> FactPitProjection:
        """原样映射 Fact revision ID 与四个时间字段。

        Args:
            无。

        Returns:
            不授予最终 PIT 使用许可的只读投影。

        Raises:
            无。
        """

        pit = self.request.pit
        return FactPitProjection(
            revision_id=self.id, prior_revision_id=self.request.prior_fact_id,
            effective_at=pit.effective_at, published_at=pit.published_at,
            ingested_at=pit.ingested_at, available_at=pit.available_at,
        )


@dataclass(frozen=True, slots=True)
class EvidenceLinkRequest:
    """新 ClaimVersion 的一条显式证据链接请求。"""

    id: UUID
    relation: EvidenceRelation
    fact_id: UUID | None = None
    security_id: UUID | None = None
    locator: EvidenceLocatorSnapshot | None = None

    def __post_init__(self) -> None:
        """校验 Fact/direct 两 target arm 恰取一种。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ID、枚举或 locator 类型错误。
            ValueError: target arm 不闭合。
        """

        _require_uuid(self.id, "id")
        _require_enum(self.relation, EvidenceRelation, "relation")
        _require_optional_uuid(self.fact_id, "fact_id")
        _require_optional_uuid(self.security_id, "security_id")
        if self.fact_id is not None:
            if self.security_id is not None or self.locator is not None:
                raise ValueError("Fact arm 不得携带 direct-only 字段")
        else:
            if self.security_id is None or type(self.locator) is not EvidenceLocatorSnapshot:
                raise ValueError("direct arm 必须有 security_id 和 locator")

    @property
    def locator_ticker(self) -> str | None:
        """从 direct locator 派生显式 ticker 列。

        Args:
            无。

        Returns:
            direct ticker；Fact arm 返回空。

        Raises:
            无。
        """

        return self.locator.ticker if self.locator is not None else None

    def target_identity(self) -> tuple[str, str, str]:
        """生成包含完整 locator 的目标身份。

        Args:
            无。

        Returns:
            ``(target_kind, security_or_fact_id, canonical_locator_json)``。

        Raises:
            无。
        """

        if self.fact_id is not None:
            return ("fact", str(self.fact_id), "")
        assert self.security_id is not None and self.locator is not None
        return ("direct", str(self.security_id), self.locator.canonical_bytes().decode("utf-8"))


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    """持久化在一个不可变 ClaimVersion 下的完整链接。"""

    tenant_id: UUID
    company_id: UUID
    claim_version_id: UUID
    request: EvidenceLinkRequest
    locator_index_digest: bytes | None
    created_at: datetime

    def __post_init__(self) -> None:
        """验证投影与 DB 生成 digest 的 arm 闭合。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: digest、arm 或时间错误。
        """

        _require_uuid(self.tenant_id, "tenant_id")
        _require_uuid(self.company_id, "company_id")
        _require_uuid(self.claim_version_id, "claim_version_id")
        if type(self.request) is not EvidenceLinkRequest:
            raise TypeError("request 必须是 EvidenceLinkRequest")
        if self.request.fact_id is not None:
            if self.locator_index_digest is not None:
                raise ValueError("Fact arm 不得携带 direct digest")
        elif type(self.locator_index_digest) is not bytes or len(self.locator_index_digest) != 32:
            raise ValueError("direct arm 必须携带 DB 生成的 32-byte digest")
        _require_utc(self.created_at, "created_at")


def copied_link_id(new_version_id: UUID, old_link_id: UUID) -> UUID:
    """为 immutable source link 确定性生成 successor link ID。

    Args:
        new_version_id: 新 ClaimVersion ID。
        old_link_id: 原不可变 Link ID。

    Returns:
        URL namespace UUID5。

    Raises:
        TypeError: ID 不是 UUID。
        ValueError: ID 为 nil。
    """

    _require_uuid(new_version_id, "new_version_id")
    _require_uuid(old_link_id, "old_link_id")
    return uuid5(NAMESPACE_URL, _COPY_NAMESPACE + str(new_version_id) + ":" + str(old_link_id))


def ordered_link_identities(links: tuple[EvidenceLinkRequest, ...]) -> tuple[tuple[str, str, str, str, str], ...]:
    """按关系、完整目标身份和 link ID 排序指纹输入。

    Args:
        links: 已验证的完整链接集合。

    Returns:
        与输入顺序无关的 identity tuple。

    Raises:
        TypeError: 集合或成员类型错误。
    """

    if type(links) is not tuple:
        raise TypeError("links 必须是 tuple")
    rows: list[tuple[str, str, str, str, str]] = []
    for link in links:
        if type(link) is not EvidenceLinkRequest:
            raise TypeError("links 成员必须是 EvidenceLinkRequest")
        target_kind, target_id, locator_json = link.target_identity()
        rows.append((link.relation.value, target_kind, target_id, locator_json, str(link.id)))
    return tuple(sorted(rows))


def _link_fingerprint_row(link: EvidenceLinkRequest) -> dict[str, JsonValue]:
    """将一个链接转换为不含 digest 的完整 target frame。

    Args:
        link: 已验证的链接请求。

    Returns:
        包含 relation、Fact ID 或 security ID 加完整 locator 的 JSON 对象。

    Raises:
        TypeError: 输入不是链接请求。
    """

    if type(link) is not EvidenceLinkRequest:
        raise TypeError("link 必须是 EvidenceLinkRequest")
    if link.fact_id is not None:
        return {"relation": link.relation.value, "target_kind": "fact", "fact_id": str(link.fact_id)}
    assert link.security_id is not None and link.locator is not None
    return {
        "relation": link.relation.value, "target_kind": "direct",
        "security_id": str(link.security_id), "locator": link.locator.to_dict(),
    }


def evidence_fingerprint_frame(
    selection: EvidenceSelection, *, new_version_id: UUID,
    copy_source_version_id: UUID | None = None,
    copy_source_version_no: int | None = None,
    copy_source_links: tuple[EvidenceLinkRequest, ...] | None = None,
) -> dict[str, JsonValue]:
    """构造 replace/copy 互斥且顺序归一的证据指纹 frame。

    copy 来源必须是首次 expected_version 的 immutable Version+Links，
    repository 在调用前核 tenant/company/claim、version_no 与完整性。

    Args:
        selection: 请求指定的证据集合模式。
        new_version_id: caller 提供的新版本 ID。
        copy_source_version_id: copy 时原不可变版本 ID。
        copy_source_version_no: copy 时原不可变版本号。
        copy_source_links: copy 时原版本的完整链接集合。

    Returns:
        不含 bearer、hash、grant 或 digest 的 canonicalizable frame。

    Raises:
        TypeError: 参数类型错误。
        ValueError: replace 携 source 或 copy 缺 source。
    """

    if type(selection) is not EvidenceSelection:
        raise TypeError("selection 必须是 EvidenceSelection")
    _require_uuid(new_version_id, "new_version_id")
    if selection.mode is EvidenceMode.REPLACE_ALL:
        if (copy_source_version_id is not None or copy_source_version_no is not None
                or copy_source_links is not None):
            raise ValueError("replace_all 不得携带 copy source")
        assert selection.links is not None
        rows: list[JsonValue] = []
        for link in sorted(selection.links, key=lambda item: (
            item.relation.value, *item.target_identity(), str(item.id),
        )):
            row = _link_fingerprint_row(link)
            row["link_id"] = str(link.id)
            rows.append(row)
        return {"mode": EvidenceMode.REPLACE_ALL.value, "links": rows}
    if copy_source_version_id is None or copy_source_version_no is None or copy_source_links is None:
        raise ValueError("copy_previous 必须提供完整 immutable source")
    _require_uuid(copy_source_version_id, "copy_source_version_id")
    _require_int(copy_source_version_no, "copy_source_version_no", minimum=1)
    # 来源已由 repository 做 scoped read；这里仍拒绝漂移后的重复集合。
    EvidenceSelection(copy_source_links, False)
    rows = []
    for old_link in sorted(copy_source_links, key=lambda item: (
        item.relation.value, *item.target_identity(), str(item.id),
    )):
        row = _link_fingerprint_row(old_link)
        row["old_link_id"] = str(old_link.id)
        row["new_link_id"] = str(copied_link_id(new_version_id, old_link.id))
        rows.append(row)
    return {
        "mode": EvidenceMode.COPY_PREVIOUS.value,
        "source_version_id": str(copy_source_version_id),
        "source_version_no": copy_source_version_no,
        "links": rows,
    }


@dataclass(frozen=True, slots=True)
class EvidenceSelection:
    """完整替换与从 expected_version 复制的互斥选择。"""

    links: tuple[EvidenceLinkRequest, ...] | None
    copy_previous_links: bool

    def __post_init__(self) -> None:
        """拒绝同时 copy/replace 和重复 target。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: copy 标志或 links 类型错误。
            ValueError: 模式不互斥、link ID 或 target 重复。
        """

        if type(self.copy_previous_links) is not bool:
            raise TypeError("copy_previous_links 必须是 bool")
        if self.copy_previous_links == (self.links is not None):
            raise ValueError("必须恰取 copy_previous 或显式 replace_all")
        if self.links is None:
            return
        identities = ordered_link_identities(self.links)
        ids = [row[4] for row in identities]
        targets = [row[:4] for row in identities]
        if len(ids) != len(set(ids)) or len(targets) != len(set(targets)):
            raise ValueError("link ID 或 relation+target identity 重复")

    @property
    def mode(self) -> EvidenceMode:
        """返回明确的持久化 evidence_mode。

        Args:
            无。

        Returns:
            replace_all 或 copy_previous。

        Raises:
            无。
        """

        return EvidenceMode.COPY_PREVIOUS if self.copy_previous_links else EvidenceMode.REPLACE_ALL


@dataclass(frozen=True, slots=True)
class ClaimContent:
    """ClaimVersion 的内容与非授权性置信信息。"""

    statement: str
    confidence_band: ConfidenceBand
    probability: Decimal | None
    impact_horizon: ImpactHorizon
    valid_until: datetime | None
    status: ClaimStatus
    invalidation_rule: str

    def __post_init__(self) -> None:
        """校验内容、closed enum 与概率精度。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: 空文本、概率越界或时间非 UTC。
        """

        _require_text(self.statement, "statement")
        _require_enum(self.confidence_band, ConfidenceBand, "confidence_band")
        if self.probability is not None:
            _require_decimal(self.probability, "probability")
            if not 0 <= self.probability <= 1:
                raise ValueError("probability 必须在 [0,1] 内")
        _require_enum(self.impact_horizon, ImpactHorizon, "impact_horizon")
        if self.valid_until is not None:
            _require_utc(self.valid_until, "valid_until")
        _require_enum(self.status, ClaimStatus, "status")
        _require_text(self.invalidation_rule, "invalidation_rule")


@dataclass(frozen=True, slots=True)
class ClaimCreateRequest:
    """创建同事务 shell、V1 draft 和完整 links 的请求。"""

    id: UUID
    company_id: UUID
    version_id: UUID
    content: ClaimContent
    evidence: EvidenceSelection
    author_user_id: UUID | None
    operation_id: UUID

    def __post_init__(self) -> None:
        """要求 caller ID、draft 与 replace_all。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: V1 状态或证据模式错误。
        """

        for label, value in (("id", self.id), ("company_id", self.company_id),
                             ("version_id", self.version_id), ("operation_id", self.operation_id)):
            _require_uuid(value, label)
        if type(self.content) is not ClaimContent or type(self.evidence) is not EvidenceSelection:
            raise TypeError("content/evidence 类型错误")
        if self.content.status is not ClaimStatus.DRAFT:
            raise ValueError("V1 必须为 draft")
        if self.evidence.mode is not EvidenceMode.REPLACE_ALL:
            raise ValueError("V1 只能 replace_all")
        _require_optional_uuid(self.author_user_id, "author_user_id")


@dataclass(frozen=True, slots=True)
class ClaimVersionAppendRequest:
    """普通内容修订或 draft 提交审核的请求。"""

    claim_id: UUID
    expected_version: int
    new_version_id: UUID
    content: ClaimContent
    evidence: EvidenceSelection
    author_user_id: UUID | None
    operation_id: UUID

    def __post_init__(self) -> None:
        """拒绝普通 append 直接进入 reviewer-only 状态。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: 版本或目标状态非法。
        """

        _require_uuid(self.claim_id, "claim_id")
        _require_int(self.expected_version, "expected_version", minimum=1)
        _require_uuid(self.new_version_id, "new_version_id")
        _require_uuid(self.operation_id, "operation_id")
        if type(self.content) is not ClaimContent or type(self.evidence) is not EvidenceSelection:
            raise TypeError("content/evidence 类型错误")
        if self.content.status not in (ClaimStatus.DRAFT, ClaimStatus.IN_REVIEW, ClaimStatus.REVIEW_REQUIRED):
            raise ValueError("append 不得进入 reviewer-only 状态")
        _require_optional_uuid(self.author_user_id, "author_user_id")


@dataclass(frozen=True, slots=True)
class ClaimRevisionBeginRequest:
    """持 active bearer 重开同 lineage draft 的请求；actor 由 token 推导。"""

    claim_id: UUID
    expected_version: int
    new_version_id: UUID
    content: ClaimContent
    evidence: EvidenceSelection
    revision_reason: str
    operation_id: UUID

    def __post_init__(self) -> None:
        """校验重开请求没有自由 author/reviewer 字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: 非 draft 或空 reason。
        """

        _require_uuid(self.claim_id, "claim_id")
        _require_int(self.expected_version, "expected_version", minimum=1)
        _require_uuid(self.new_version_id, "new_version_id")
        _require_uuid(self.operation_id, "operation_id")
        if type(self.content) is not ClaimContent or type(self.evidence) is not EvidenceSelection:
            raise TypeError("content/evidence 类型错误")
        if self.content.status is not ClaimStatus.DRAFT:
            raise ValueError("begin_revision 只能进入 draft")
        _require_text(self.revision_reason, "revision_reason")


@dataclass(frozen=True, slots=True)
class ClaimReviewRequest:
    """审查决定请求；不接受 caller 自报 reviewer 身份或 grant。"""

    claim_id: UUID
    expected_version: int
    new_version_id: UUID
    content: ClaimContent
    evidence: EvidenceSelection
    review_reason: str
    operation_id: UUID

    def __post_init__(self) -> None:
        """校验审查动作的结构和目标状态集合。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: 状态或原因非法。
        """

        _require_uuid(self.claim_id, "claim_id")
        _require_int(self.expected_version, "expected_version", minimum=1)
        _require_uuid(self.new_version_id, "new_version_id")
        _require_uuid(self.operation_id, "operation_id")
        if type(self.content) is not ClaimContent or type(self.evidence) is not EvidenceSelection:
            raise TypeError("content/evidence 类型错误")
        if self.content.status not in (ClaimStatus.APPROVED, ClaimStatus.REJECTED,
                                       ClaimStatus.INVALIDATED, ClaimStatus.REVIEW_REQUIRED,
                                       ClaimStatus.SUPERSEDED):
            raise ValueError("review 目标状态非法")
        _require_text(self.review_reason, "review_reason")


@dataclass(frozen=True, slots=True)
class AuthorAuthWitness:
    """begin_revision 从已核 active token 派生的不可变 witness。"""

    token_id: UUID
    checked_at: datetime
    policy_version: str

    def __post_init__(self) -> None:
        """校验 token witness 的局部结构。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ID 或时间类型错误。
            ValueError: nil ID、非 UTC 或空 policy。
        """

        _require_uuid(self.token_id, "token_id")
        _require_utc(self.checked_at, "checked_at")
        _require_text(self.policy_version, "policy_version")


@dataclass(frozen=True, slots=True)
class ReviewWitness:
    """可从不可变行重建的 token/grant reviewer 事实快照。"""

    reviewer_user_id: UUID
    reviewer_token_id: UUID
    user_role_id: UUID
    role_permission_id: UUID
    permission_id: UUID
    permission_key: str
    checked_at: datetime
    policy_version: str
    reason: str

    def __post_init__(self) -> None:
        """校验完整审查 witness，禁止空字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ID 或时间类型错误。
            ValueError: 关键字段为空或权限键错误。
        """

        for label, value in (("reviewer_user_id", self.reviewer_user_id),
                             ("reviewer_token_id", self.reviewer_token_id),
                             ("user_role_id", self.user_role_id),
                             ("role_permission_id", self.role_permission_id),
                             ("permission_id", self.permission_id)):
            _require_uuid(value, label)
        if self.permission_key != "investment.claim.review":
            raise ValueError("reviewer permission key 错误")
        _require_utc(self.checked_at, "checked_at")
        _require_text(self.policy_version, "policy_version")
        _require_text(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class ClaimVersion:
    """持久化的不可变 Claim 内容、动作和证据来源投影。"""

    id: UUID
    tenant_id: UUID
    company_id: UUID
    claim_id: UUID
    version_no: int
    transition_kind: ClaimTransitionKind
    evidence_mode: EvidenceMode
    copy_source_version_id: UUID | None
    operation_id: UUID
    operation_fingerprint: str
    content: ClaimContent
    author_user_id: UUID | None
    author_auth: AuthorAuthWitness | None
    reviewer: ReviewWitness | None
    created_at: datetime

    def __post_init__(self) -> None:
        """校验 mode/source 互斥与动作 witness 形状。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ID、枚举或嵌套 DTO 类型错误。
            ValueError: version、mode、状态或 witness 不闭合。
        """

        for label, value in (("id", self.id), ("tenant_id", self.tenant_id),
                             ("company_id", self.company_id), ("claim_id", self.claim_id),
                             ("operation_id", self.operation_id)):
            _require_uuid(value, label)
        _require_int(self.version_no, "version_no", minimum=1)
        _require_enum(self.transition_kind, ClaimTransitionKind, "transition_kind")
        _require_enum(self.evidence_mode, EvidenceMode, "evidence_mode")
        _require_optional_uuid(self.copy_source_version_id, "copy_source_version_id")
        if (self.evidence_mode is EvidenceMode.COPY_PREVIOUS) != (self.copy_source_version_id is not None):
            raise ValueError("copy_previous iff copy_source_version_id 非空")
        if self.version_no == 1 and (self.transition_kind is not ClaimTransitionKind.CLAIM_CREATE
                                     or self.evidence_mode is not EvidenceMode.REPLACE_ALL):
            raise ValueError("V1 必须 claim_create + replace_all")
        if self.version_no != 1 and self.transition_kind is ClaimTransitionKind.CLAIM_CREATE:
            raise ValueError("claim_create 只能产生 V1")
        _require_hex64(self.operation_fingerprint, "operation_fingerprint")
        if type(self.content) is not ClaimContent:
            raise TypeError("content 必须是 ClaimContent")
        _require_optional_uuid(self.author_user_id, "author_user_id")
        if self.author_auth is not None and type(self.author_auth) is not AuthorAuthWitness:
            raise TypeError("author_auth 类型错误")
        if self.reviewer is not None and type(self.reviewer) is not ReviewWitness:
            raise TypeError("reviewer 类型错误")
        if self.transition_kind is ClaimTransitionKind.BEGIN_REVISION:
            if (self.author_user_id is None or self.author_auth is None or self.reviewer is not None
                    or self.content.status is not ClaimStatus.DRAFT):
                raise ValueError("begin_revision 必须有 token-derived author witness 且目标为 draft")
        elif self.transition_kind in (ClaimTransitionKind.REVIEW_DECISION,
                                      ClaimTransitionKind.CONFLICT_RESOLUTION):
            if self.reviewer is None or self.author_auth is not None:
                raise ValueError("review 动作必须有完整 reviewer witness")
        elif self.author_auth is not None or self.reviewer is not None:
            raise ValueError("普通/系统版本不得携带认证 witness")
        if self.transition_kind is ClaimTransitionKind.CLAIM_CREATE and self.content.status is not ClaimStatus.DRAFT:
            raise ValueError("claim_create 必须为 draft")
        if self.transition_kind is ClaimTransitionKind.EXPIRY and self.content.status is not ClaimStatus.REVIEW_REQUIRED:
            raise ValueError("expiry 只能进入 review_required")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class ClaimSnapshot:
    """Claim shell、唯一 current version 和完整当前链接投影。"""

    id: UUID
    tenant_id: UUID
    company_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime
    current: ClaimVersion
    links: tuple[EvidenceLink, ...]

    def __post_init__(self) -> None:
        """核 shell/version/link 的 tenant、company 和 version 闭合。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: current 或链接身份漂移。
        """

        for label, value in (("id", self.id), ("tenant_id", self.tenant_id),
                             ("company_id", self.company_id)):
            _require_uuid(value, label)
        _require_int(self.version, "version", minimum=1)
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at 早于 created_at")
        if type(self.current) is not ClaimVersion or type(self.links) is not tuple:
            raise TypeError("current/links 类型错误")
        if (self.current.claim_id != self.id or self.current.tenant_id != self.tenant_id
                or self.current.company_id != self.company_id or self.current.version_no != self.version):
            raise ValueError("current version 与 shell 漂移")
        identities: set[tuple[str, str, str, str]] = set()
        for link in self.links:
            if type(link) is not EvidenceLink:
                raise TypeError("links 成员类型错误")
            if (link.tenant_id != self.tenant_id or link.company_id != self.company_id
                    or link.claim_version_id != self.current.id):
                raise ValueError("link tenant/company/version 漂移")
            identity = (link.request.relation.value, *link.request.target_identity())
            if identity in identities:
                raise ValueError("current links 包含重复 relation+target")
            identities.add(identity)


@dataclass(frozen=True, slots=True)
class ClaimConflictOpenRequest:
    """创建同公司两个 immutable version 间的 material conflict。"""

    id: UUID
    company_id: UUID
    left_version_id: UUID
    right_version_id: UUID
    material: bool
    reason: str
    operation_id: UUID

    def __post_init__(self) -> None:
        """校验冲突端点排序、非同一 ID 和 material 类型。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ID 或 material 类型错误。
            ValueError: 端点排序或 reason 错误。
        """

        for label, value in (("id", self.id), ("company_id", self.company_id),
                             ("left_version_id", self.left_version_id),
                             ("right_version_id", self.right_version_id),
                             ("operation_id", self.operation_id)):
            _require_uuid(value, label)
        if self.left_version_id.int >= self.right_version_id.int:
            raise ValueError("冲突端点必须按 UUID 升序且不同")
        if type(self.material) is not bool:
            raise TypeError("material 必须是 bool")
        _require_text(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class ClaimConflictResolveRequest:
    """reviewer 在同事务新增 successor 并关闭冲突的请求。"""

    conflict_id: UUID
    selected_claim_id: UUID
    expected_selected_version: int
    expected_other_version: int
    expected_conflict_version: int
    new_version_id: UUID
    new_link_id: UUID
    content: ClaimContent
    evidence: EvidenceSelection
    resolution_reason: str
    operation_id: UUID

    def __post_init__(self) -> None:
        """校验 CAS tokens、successor ID 和非空原因。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: 版本或原因非法。
        """

        for label, value in (("conflict_id", self.conflict_id),
                             ("selected_claim_id", self.selected_claim_id),
                             ("new_version_id", self.new_version_id),
                             ("new_link_id", self.new_link_id),
                             ("operation_id", self.operation_id)):
            _require_uuid(value, label)
        for label, value in (("expected_selected_version", self.expected_selected_version),
                             ("expected_other_version", self.expected_other_version),
                             ("expected_conflict_version", self.expected_conflict_version)):
            _require_int(value, label, minimum=1)
        if type(self.content) is not ClaimContent or type(self.evidence) is not EvidenceSelection:
            raise TypeError("content/evidence 类型错误")
        if self.content.status not in (ClaimStatus.DRAFT, ClaimStatus.IN_REVIEW,
                                       ClaimStatus.REVIEW_REQUIRED):
            raise ValueError("conflict resolution 不得直接 approve 或终结")
        _require_text(self.resolution_reason, "resolution_reason")


@dataclass(frozen=True, slots=True)
class ClaimConflict:
    """冲突开立或解决后的 tenant 私有投影。"""

    id: UUID
    tenant_id: UUID
    company_id: UUID
    left_version_id: UUID
    right_version_id: UUID
    material: bool
    status: ConflictStatus
    reason: str
    version: int
    created_at: datetime
    updated_at: datetime
    operation_id: UUID
    operation_fingerprint: str
    resolution_new_version_id: UUID | None
    resolution_new_link_id: UUID | None
    resolution_operation_id: UUID | None
    reviewer: ReviewWitness | None

    def __post_init__(self) -> None:
        """校验状态与 resolution witness 全有或全无。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: 端点排序、状态或 witness 不闭合。
        """

        for label, value in (("id", self.id), ("tenant_id", self.tenant_id),
                             ("company_id", self.company_id),
                             ("left_version_id", self.left_version_id),
                             ("right_version_id", self.right_version_id),
                             ("operation_id", self.operation_id)):
            _require_uuid(value, label)
        if self.left_version_id.int >= self.right_version_id.int:
            raise ValueError("冲突端点必须按 UUID 升序")
        if type(self.material) is not bool:
            raise TypeError("material 必须是 bool")
        _require_enum(self.status, ConflictStatus, "status")
        _require_text(self.reason, "reason")
        _require_int(self.version, "version", minimum=1)
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at 早于 created_at")
        _require_hex64(self.operation_fingerprint, "operation_fingerprint")
        _require_optional_uuid(self.resolution_new_version_id, "resolution_new_version_id")
        _require_optional_uuid(self.resolution_new_link_id, "resolution_new_link_id")
        _require_optional_uuid(self.resolution_operation_id, "resolution_operation_id")
        if self.reviewer is not None and type(self.reviewer) is not ReviewWitness:
            raise TypeError("reviewer 类型错误")
        resolved = self.status is ConflictStatus.RESOLVED
        fields_present = all(value is not None for value in (
            self.resolution_new_version_id, self.resolution_new_link_id,
            self.resolution_operation_id, self.reviewer,
        ))
        fields_absent = all(value is None for value in (
            self.resolution_new_version_id, self.resolution_new_link_id,
            self.resolution_operation_id, self.reviewer,
        ))
        if (resolved and not fields_present) or (not resolved and not fields_absent):
            raise ValueError("冲突状态与 resolution witness 不闭合")


_MAX_CANDIDATE_JSON_BYTES = 1_048_576


def canonical_json_bytes(value: JsonValue) -> bytes:
    """将严格有限 JSON 值编码为稳定 canonical bytes。

    Args:
        value: JSON 值；调用方必须避免包含凭据。

    Returns:
        UTF-8、sorted keys、compact separators 编码。

    Raises:
        TypeError: 值不可序列化。
        ValueError: 值含 NaN 或 Infinity。
    """

    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_json_document(raw: bytes, *, max_bytes: int = _MAX_CANDIDATE_JSON_BYTES) -> bytes:
    """严格读取 JSON 对象并返回 canonical bytes。

    Args:
        raw: UTF-8 JSON bytes。
        max_bytes: 输入和输出共同适用的边界。

    Returns:
        无重复键、无 BOM 的 canonical JSON bytes。

    Raises:
        TypeError: 输入或上限类型非法。
        ValueError: 超限、重复键、BOM、尾随数据或非有限值。
    """

    if type(raw) is not bytes:
        raise TypeError("JSON document 必须是 bytes")
    _require_int(max_bytes, "max_bytes", minimum=1)
    if len(raw) > max_bytes or raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("JSON document 超限或含 BOM")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON document 非法") from exc
    if type(value) is not dict:
        raise ValueError("JSON document 根必须是对象")
    canonical = canonical_json_bytes(value)
    if len(canonical) > max_bytes:
        raise ValueError("canonical JSON document 超限")
    return canonical


def canonical_sha256(value: JsonValue) -> str:
    """为不含凭据的 canonical JSON frame 计算 SHA-256。

    Args:
        value: 严格 JSON frame。

    Returns:
        小写 64-hex 指纹。

    Raises:
        TypeError: frame 不可序列化。
        ValueError: frame 含非有限值。
    """

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class ResearchCandidateCreateRequest:
    """仅创建 proposed staging 候选的请求。"""

    id: UUID
    company_id: UUID
    origin: CandidateOrigin
    canonical_payload_json: bytes
    operation_id: UUID

    def __post_init__(self) -> None:
        """校验 bounded canonical payload 和 caller ID。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: payload 非 canonical、非有限或超限。
        """

        _require_uuid(self.id, "id")
        _require_uuid(self.company_id, "company_id")
        _require_enum(self.origin, CandidateOrigin, "origin")
        _require_uuid(self.operation_id, "operation_id")
        canonical = canonical_json_document(self.canonical_payload_json)
        if canonical != self.canonical_payload_json:
            raise ValueError("canonical_payload_json 必须已 canonical 化")

    @property
    def sha256(self) -> str:
        """返回候选 canonical payload 的 SHA-256。

        Args:
            无。

        Returns:
            小写 64-hex hash。

        Raises:
            无。
        """

        return hashlib.sha256(self.canonical_payload_json).hexdigest()


@dataclass(frozen=True, slots=True)
class ResearchCandidate:
    """租户私有候选 staging 投影；接受并不等于 Claim 已批准。"""

    tenant_id: UUID
    request: ResearchCandidateCreateRequest
    state: CandidateStatus
    version: int
    operation_fingerprint: str
    created_at: datetime
    updated_at: datetime
    rejection_code: str | None

    def __post_init__(self) -> None:
        """校验 staging 状态与 rejection_code 配对。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: DTO 或枚举类型错误。
            ValueError: 版本、时间或拒绝原因错误。
        """

        _require_uuid(self.tenant_id, "tenant_id")
        if type(self.request) is not ResearchCandidateCreateRequest:
            raise TypeError("request 类型错误")
        _require_enum(self.state, CandidateStatus, "state")
        _require_int(self.version, "version", minimum=1)
        _require_hex64(self.operation_fingerprint, "operation_fingerprint")
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at 早于 created_at")
        if self.state is CandidateStatus.REJECTED:
            if self.rejection_code is None:
                raise ValueError("rejected 必须提供 rejection_code")
            _require_pattern(self.rejection_code, "rejection_code", _BOUNDED_CODE)
        elif self.rejection_code is not None:
            raise ValueError("非 rejected 不得携带 rejection_code")


@dataclass(frozen=True, slots=True)
class ClaimLocalEligibility:
    """局部候选可用性判定；ready 仍需 Fins owner 验证。"""

    claim_id: UUID
    reason: LocalEligibilityReason
    checked_at: datetime

    def __post_init__(self) -> None:
        """校验判定身份与 PG statement clock 投影。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 字段类型错误。
            ValueError: nil ID 或非 UTC 时间。
        """

        _require_uuid(self.claim_id, "claim_id")
        _require_enum(self.reason, LocalEligibilityReason, "reason")
        _require_utc(self.checked_at, "checked_at")


def validate_append_transition(
    current: ClaimStatus, desired: ClaimStatus, *, materially_changed: bool,
) -> ClaimTransitionKind:
    """校验普通 append 的唯一状态入口。

    Args:
        current: 当前持久状态。
        desired: 新版本状态。
        materially_changed: 忽略新 link ID 后内容或 target 是否实质改变。

    Returns:
        content_revision 或 submit_review。

    Raises:
        TypeError: 状态或标志类型错误。
        ValueError: 禁止的状态边或空操作。
    """

    _require_enum(current, ClaimStatus, "current")
    _require_enum(desired, ClaimStatus, "desired")
    if type(materially_changed) is not bool:
        raise TypeError("materially_changed 必须是 bool")
    if current is ClaimStatus.DRAFT and desired is ClaimStatus.IN_REVIEW:
        return ClaimTransitionKind.SUBMIT_REVIEW
    if current in (ClaimStatus.DRAFT, ClaimStatus.IN_REVIEW,
                   ClaimStatus.REVIEW_REQUIRED) and desired is current and materially_changed:
        return ClaimTransitionKind.CONTENT_REVISION
    raise ValueError("append 状态边或空修订非法")


def validate_begin_transition(current: ClaimStatus, desired: ClaimStatus) -> None:
    """校验 token-derived begin_revision 的同 lineage 状态边。

    Args:
        current: 当前持久状态。
        desired: 请求目标状态。

    Returns:
        无。

    Raises:
        TypeError: 状态不是 closed enum。
        ValueError: 目标非 draft 或来源不可重开。
    """

    _require_enum(current, ClaimStatus, "current")
    _require_enum(desired, ClaimStatus, "desired")
    if current not in (ClaimStatus.REJECTED, ClaimStatus.INVALIDATED,
                       ClaimStatus.SUPERSEDED, ClaimStatus.REVIEW_REQUIRED) or desired is not ClaimStatus.DRAFT:
        raise ValueError("begin_revision 状态边非法")


def validate_review_transition(
    current: ClaimStatus, desired: ClaimStatus, *, supports_count: int,
    valid_until: datetime | None, statement_clock: datetime,
) -> None:
    """校验 reviewer-only 状态边和 approved 的最低证据时效条件。

    Args:
        current: 当前持久状态。
        desired: 审查目标状态。
        supports_count: 新版本完整 links 中 supports 数量。
        valid_until: 新版本有效期。
        statement_clock: 同事务 PostgreSQL statement_timestamp。

    Returns:
        无。

    Raises:
        TypeError: 状态、计数或时间类型错误。
        ValueError: 状态边、证据或有效期非法。
    """

    _require_enum(current, ClaimStatus, "current")
    _require_enum(desired, ClaimStatus, "desired")
    _require_int(supports_count, "supports_count")
    _require_utc(statement_clock, "statement_clock")
    if valid_until is not None:
        _require_utc(valid_until, "valid_until")
    allowed = (
        (current is ClaimStatus.IN_REVIEW and desired in (ClaimStatus.APPROVED, ClaimStatus.REJECTED))
        or (current is ClaimStatus.APPROVED and desired in (ClaimStatus.INVALIDATED, ClaimStatus.REVIEW_REQUIRED))
        or (current is ClaimStatus.REVIEW_REQUIRED and desired is ClaimStatus.SUPERSEDED)
    )
    if not allowed:
        raise ValueError("review 状态边非法")
    if desired is ClaimStatus.APPROVED and (
        supports_count < 1 or valid_until is None or valid_until <= statement_clock
    ):
        raise ValueError("approved 必须有 supports 且 valid_until 晚于 PG 时钟")


def validate_conflict_resolution_transition(current: ClaimStatus, desired: ClaimStatus) -> None:
    """校验 conflict resolution 不隐式重开或批准。

    Args:
        current: 当前持久状态。
        desired: 新版本状态。

    Returns:
        无。

    Raises:
        TypeError: 状态类型错误。
        ValueError: 不允许的状态边。
    """

    _require_enum(current, ClaimStatus, "current")
    _require_enum(desired, ClaimStatus, "desired")
    if current in (ClaimStatus.DRAFT, ClaimStatus.IN_REVIEW,
                   ClaimStatus.REVIEW_REQUIRED) and desired is current:
        return
    if current is ClaimStatus.APPROVED and desired is ClaimStatus.REVIEW_REQUIRED:
        return
    raise ValueError("conflict resolution 状态边非法")


def local_eligibility_reason(
    status: ClaimStatus, *, valid_until: datetime | None, statement_clock: datetime,
    has_open_material_conflict: bool, supports_count: int,
) -> LocalEligibilityReason:
    """按 PG 时间、material conflict、状态、supports 顺序局部筛选。

    Args:
        status: 持久 current 状态。
        valid_until: 持久有效期。
        statement_clock: 同事务 PostgreSQL statement_timestamp。
        has_open_material_conflict: 当前 lineage 是否有 open material conflict。
        supports_count: 当前完整 links 中 supports 数量。

    Returns:
        五种 closed reason 之一；局部 ready 仍须 Fins 验证。

    Raises:
        TypeError: 状态、布尔标志或计数类型错误。
        ValueError: 时间非 UTC。
    """

    _require_enum(status, ClaimStatus, "status")
    _require_utc(statement_clock, "statement_clock")
    if valid_until is not None:
        _require_utc(valid_until, "valid_until")
    if type(has_open_material_conflict) is not bool:
        raise TypeError("has_open_material_conflict 必须是 bool")
    _require_int(supports_count, "supports_count")
    if status is ClaimStatus.APPROVED and (valid_until is None or valid_until <= statement_clock):
        return LocalEligibilityReason.EXPIRED
    if has_open_material_conflict:
        return LocalEligibilityReason.MATERIAL_CONFLICT
    if status is not ClaimStatus.APPROVED:
        return LocalEligibilityReason.NOT_APPROVED
    if supports_count == 0:
        return LocalEligibilityReason.MISSING_SUPPORT
    return LocalEligibilityReason.LOCALLY_READY_REQUIRES_FINS_VALIDATION
