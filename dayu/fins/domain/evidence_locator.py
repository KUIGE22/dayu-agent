"""Fins 证据定位器 DTO、严格解析与 canonical bytes。

本模块是 Evidence Locator 的 DTO、strict parser 与 canonical byte helper 唯一 owner，
包含：

- 五类严格 locator payload（document / page / section / table_cell / xbrl_fact），
  全部为 ``frozen=True, slots=True`` dataclass；
- 请求与投影 DTO（``EvidenceLocatorRequest`` / ``EvidenceLocatorProjection``）与
  只读 citation 结果（``CitationProjection``）；
- closed 枚举（``ArtifactKind`` / ``LocatorKind``，source kind 复用 ``SourceKind``）；
- 严格双向 parser：拒绝 missing/unknown 字段、bool-as-int、空字符串、
  非 canonical ticker/document id、非小写 64-hex SHA 与未知 schema version；
- canonical JSON bytes（UTF-8、sorted keys、compact separators、``allow_nan=False``）
  与 SHA-256 helper。

设计约束：

- 本模块不接触任何存储、路径、URI、bucket 或 handle；投影字段全部为无路径标量。
- ``to_json()`` 只序列化 owner 允许的精确字段集，hash 输入只能是 canonical JSON bytes。
- 未知 repository id 由本模块 fail closed：``repository_id`` 必须精确等于
  ``REPOSITORY_ID``。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias, Union

from dayu.fins.domain.enums import SourceKind

REPOSITORY_ID = "dayu.fins.public.v1"
"""逻辑公共仓储 namespace，与 backend/path/tenant 无关。"""

SCHEMA_VERSION = "fins-evidence-locator-v1"
"""本模块当前严格 schema 版本。"""

_LOWER_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_TICKER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*$")
_CANONICAL_DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")

JsonScalar: TypeAlias = str | int | float | bool | None
"""JSON 标量类型别名。"""

JsonValue: TypeAlias = JsonScalar | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
"""递归 JSON 值类型别名。

使用协变容器 ``Sequence`` / ``Mapping`` 表达 JSON 数组与对象，避免 mutable
``list`` / ``dict`` 的类型参数不变性阻碍嵌套 JSON 数据的赋值；具体序列化仍
接受 ``dict`` / ``list`` 实例。
"""

JsonObject: TypeAlias = Mapping[str, JsonValue]
"""JSON 对象类型别名。"""


class ArtifactKind(str, Enum):
    """证据产物类型枚举。

    仅允许 ``source``（原始文档）与 ``processed``（解析产物）。
    """

    SOURCE = "source"
    PROCESSED = "processed"


class LocatorKind(str, Enum):
    """定位器类型枚举。

    仅允许 document / page / section / table_cell / xbrl_fact 五种。
    """

    DOCUMENT = "document"
    PAGE = "page"
    SECTION = "section"
    TABLE_CELL = "table_cell"
    XBRL_FACT = "xbrl_fact"


class EvidenceLocatorError(Exception):
    """证据定位器错误。

    用于定位器请求解析、source/processed identity closure、primary/locator SHA
    校验、dual-kind 碰撞与 pre/post race 的所有 fail-closed 拒绝路径。

    Attributes:
        code: 稳定错误码。
        message: 人类可读的错误说明。
    """

    def __init__(self, code: str, message: str) -> None:
        """初始化定位器错误。

        Args:
            code: 稳定错误码。
            message: 错误说明。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class DocumentLocatorPayload:
    """document 定位器严格 payload。

    document 定位器不携带任何字段，artifact 类型由 ``artifact_kind`` 区分。
    """

    def to_dict(self) -> dict[str, JsonValue]:
        """序列化为无字段字典。

        Args:
            无。

        Returns:
            空字典。

        Raises:
            无。
        """

        return {}


@dataclass(frozen=True, slots=True)
class PageLocatorPayload:
    """page 定位器严格 payload。

    Attributes:
        page_no: 目标页码，必须为正整数。
    """

    page_no: int

    def to_dict(self) -> dict[str, JsonValue]:
        """序列化为字典。

        Args:
            无。

        Returns:
            包含 ``page_no`` 的字典。

        Raises:
            无。
        """

        return {"page_no": self.page_no}


@dataclass(frozen=True, slots=True)
class SectionLocatorPayload:
    """section 定位器严格 payload。

    Attributes:
        section_ref: 章节引用，必须为非空字符串。
    """

    section_ref: str

    def to_dict(self) -> dict[str, JsonValue]:
        """序列化为字典。

        Args:
            无。

        Returns:
            包含 ``section_ref`` 的字典。

        Raises:
            无。
        """

        return {"section_ref": self.section_ref}


@dataclass(frozen=True, slots=True)
class TableCellLocatorPayload:
    """table_cell 定位器严格 payload。

    Attributes:
        table_ref: 表格引用，必须为非空字符串。
        row_index: 目标行下标，必须为非负整数。
        column: 目标列名，必须为非空字符串。
    """

    table_ref: str
    row_index: int
    column: str

    def to_dict(self) -> dict[str, JsonValue]:
        """序列化为字典。

        Args:
            无。

        Returns:
            包含 ``table_ref`` / ``row_index`` / ``column`` 的字典。

        Raises:
            无。
        """

        return {
            "table_ref": self.table_ref,
            "row_index": self.row_index,
            "column": self.column,
        }


@dataclass(frozen=True, slots=True)
class XbrlFactLocatorPayload:
    """xbrl_fact 定位器严格 payload。

    Attributes:
        concept: XBRL 概念，必须为非空字符串。
        fact_sha256: canonical fact row 的小写 64-hex SHA-256。
    """

    concept: str
    fact_sha256: str

    def to_dict(self) -> dict[str, JsonValue]:
        """序列化为字典。

        Args:
            无。

        Returns:
            包含 ``concept`` / ``fact_sha256`` 的字典。

        Raises:
            无。
        """

        return {"concept": self.concept, "fact_sha256": self.fact_sha256}


LocatorPayload = Union[
    DocumentLocatorPayload,
    PageLocatorPayload,
    SectionLocatorPayload,
    TableCellLocatorPayload,
    XbrlFactLocatorPayload,
]
"""五类 locator payload 联合类型。"""


@dataclass(frozen=True, slots=True)
class EvidenceLocatorRequest:
    """证据定位器请求。

    由调用方提交，包含全部 identity 字段与期望的 content hashes；runtime
    resolve 会按当前 owner 状态重算并逐项比较，任何漂移 fail closed。

    Attributes:
        schema_version: 请求 schema 版本，必须为 ``SCHEMA_VERSION``。
        repository_id: 逻辑仓储 namespace，必须为 ``REPOSITORY_ID``。
        ticker: 股票代码。
        document_id: 文档 ID。
        source_kind: 来源类型（filing / material）。
        artifact_kind: 产物类型（source / processed）。
        document_version: source 文档版本。
        source_fingerprint: source 主文件指纹（小写 64-hex）。
        primary_content_sha256: source 主文件 exact bytes 的 SHA-256（小写 64-hex）。
        locator_kind: 定位器类型。
        locator_payload: 对应定位器严格 payload。
        locator_content_sha256: canonical fragment bytes 的 SHA-256（小写 64-hex）。
    """

    schema_version: str
    repository_id: str
    ticker: str
    document_id: str
    source_kind: SourceKind
    artifact_kind: ArtifactKind
    document_version: str
    source_fingerprint: str
    primary_content_sha256: str
    locator_kind: LocatorKind
    locator_payload: LocatorPayload
    locator_content_sha256: str


@dataclass(frozen=True, slots=True)
class EvidenceLocatorProjection:
    """证据定位器投影。

    无路径、可序列化的持久化投影；``to_json()`` 产生 canonical JSON bytes，
    ``sha256(content_bytes)`` 必须等于 ``locator_content_sha256``。

    Attributes:
        repository_id: 逻辑仓储 namespace（``dayu.fins.public.v1``）。
        ticker: 股票代码。
        document_id: 文档 ID。
        source_kind: 来源类型。
        artifact_kind: 产物类型。
        document_version: source 文档版本。
        source_fingerprint: source 主文件指纹。
        primary_content_sha256: source 主文件 exact bytes 的 SHA-256。
        locator_kind: 定位器类型。
        locator_payload: 对应定位器严格 payload。
        locator_content_sha256: canonical fragment bytes 的 SHA-256。
    """

    repository_id: str
    ticker: str
    document_id: str
    source_kind: SourceKind
    artifact_kind: ArtifactKind
    document_version: str
    source_fingerprint: str
    primary_content_sha256: str
    locator_kind: LocatorKind
    locator_payload: LocatorPayload
    locator_content_sha256: str

    def to_dict(self) -> dict[str, JsonValue]:
        """序列化为无路径投影字典。

        Args:
            无。

        Returns:
            精确字段集字典（不含任何路径 / URI / handle）。

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

    def to_json(self) -> bytes:
        """生成 canonical JSON bytes。

        输出为 UTF-8、sorted keys、compact separators 且 ``allow_nan=False``
        的 canonical JSON；该 bytes 可直接作为 hash 输入。

        Args:
            无。

        Returns:
            canonical JSON bytes。

        Raises:
            ValueError: 投影含 NaN/Infinity 等不可序列化值时抛出。
        """

        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True, slots=True)
class CitationProjection:
    """runtime 返回的只读 citation 结果。

    精确包含 ``locator``、``content_type`` 与 ``content_bytes``；它本身不写入
    locator JSON。``sha256(content_bytes)`` 必须等于
    ``locator.locator_content_sha256``。

    Attributes:
        locator: 已验证的证据定位器投影。
        content_type: 内容 MIME 类型。
        content_bytes: canonical evidence fragment bytes。
    """

    locator: EvidenceLocatorProjection
    content_type: str
    content_bytes: bytes


def canonical_json_bytes(value: JsonValue) -> bytes:
    """将任意 JSON 值编码为 canonical JSON bytes。

    规则固定为 UTF-8、``sort_keys=True``、compact separators 且
    ``allow_nan=False``，保证 FS/S3 等不同 backend 对同一结构产生相同 bytes。

    Args:
        value: 待编码的 JSON 值。

    Returns:
        canonical JSON bytes。

    Raises:
        ValueError: 值含 NaN/Infinity 或不可序列化对象时抛出。
        TypeError: 值不可序列化时抛出。
    """

    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """计算小写 64-hex SHA-256。

    Args:
        data: 待哈希的 bytes。

    Returns:
        小写 64-hex SHA-256。

    Raises:
        无。
    """

    return hashlib.sha256(data).hexdigest()


def is_lower_hex_sha256(value: str) -> bool:
    """判断字符串是否为小写 64-hex SHA-256。

    Args:
        value: 待判断的字符串。

    Returns:
        是小写 64-hex SHA-256 时返回 ``True``，否则返回 ``False``。

    Raises:
        无。
    """

    return _LOWER_HEX_64_RE.fullmatch(value) is not None


def validate_evidence_locator_request(request: EvidenceLocatorRequest) -> None:
    """严格校验已构造的证据定位器请求 DTO。

    本校验器是 DTO 级 invariant 唯一真源：即使调用方不经 parser 直接构造
    dataclass，也强制拒绝 unknown schema/repository、非 canonical
    ticker/document id、非小写 64-hex SHA、非真实枚举类型、locator
    kind/payload 配对错误以及 source artifact 非 document 组合。

    Args:
        request: 已构造的请求 DTO。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: 任一 invariant 不满足时抛出。
    """

    _validate_dto(
        schema_version=request.schema_version,
        repository_id=request.repository_id,
        ticker=request.ticker,
        document_id=request.document_id,
        source_kind=request.source_kind,
        artifact_kind=request.artifact_kind,
        document_version=request.document_version,
        source_fingerprint=request.source_fingerprint,
        primary_content_sha256=request.primary_content_sha256,
        locator_kind=request.locator_kind,
        locator_payload=request.locator_payload,
        locator_content_sha256=request.locator_content_sha256,
    )


def validate_evidence_locator_projection(locator: EvidenceLocatorProjection) -> None:
    """严格校验已构造的证据定位器投影 DTO。

    与 ``validate_evidence_locator_request`` 相同语义，拒绝未知 repository id、
    非 canonical 标识、非法 hash、非真实枚举类型与 kind/payload 配对错误；
    投影不携带 schema_version。

    Args:
        locator: 已构造的投影 DTO。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: 任一 invariant 不满足时抛出。
    """

    _validate_dto(
        schema_version=None,
        repository_id=locator.repository_id,
        ticker=locator.ticker,
        document_id=locator.document_id,
        source_kind=locator.source_kind,
        artifact_kind=locator.artifact_kind,
        document_version=locator.document_version,
        source_fingerprint=locator.source_fingerprint,
        primary_content_sha256=locator.primary_content_sha256,
        locator_kind=locator.locator_kind,
        locator_payload=locator.locator_payload,
        locator_content_sha256=locator.locator_content_sha256,
    )


def _validate_dto(
    *,
    schema_version: str | None,
    repository_id: str,
    ticker: str,
    document_id: str,
    source_kind: SourceKind | str,
    artifact_kind: ArtifactKind | str,
    document_version: str,
    source_fingerprint: str,
    primary_content_sha256: str,
    locator_kind: LocatorKind | str,
    locator_payload: LocatorPayload,
    locator_content_sha256: str,
) -> None:
    """执行 DTO 级公共 invariant 校验。

    Args:
        schema_version: 请求 schema 版本；投影为 ``None``。
        repository_id: 逻辑仓储 namespace。
        ticker: 股票代码。
        document_id: 文档 ID。
        source_kind: 来源类型（真实枚举或原始字符串）。
        artifact_kind: 产物类型（真实枚举或原始字符串）。
        document_version: source 文档版本。
        source_fingerprint: source 主文件指纹。
        primary_content_sha256: source 主文件 SHA-256。
        locator_kind: 定位器类型（真实枚举或原始字符串）。
        locator_payload: 定位器严格 payload。
        locator_content_sha256: canonical fragment SHA-256。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: 任一 invariant 不满足时抛出。
    """

    if schema_version is not None:
        _check_schema_version(schema_version)
    _check_repository_id(repository_id)
    _check_canonical_ticker(ticker)
    _check_canonical_document_id(document_id)
    _check_text(document_version, "document_version")
    _check_lower_hex64(source_fingerprint, "source_fingerprint")
    _check_lower_hex64(primary_content_sha256, "primary_content_sha256")
    _check_lower_hex64(locator_content_sha256, "locator_content_sha256")
    _check_source_kind(source_kind)
    artifact_kind_value = _check_artifact_kind(artifact_kind)
    locator_kind_value = _check_locator_kind(locator_kind)
    _check_payload_pairing(locator_kind_value, locator_payload)
    _check_artifact_combo(artifact_kind_value, locator_kind_value, locator_payload)


def _check_schema_version(value: str) -> None:
    """校验 schema version 等于当前严格版本。

    Args:
        value: schema 版本字符串。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: 版本与 ``SCHEMA_VERSION`` 不一致时抛出。
    """

    if value != SCHEMA_VERSION:
        raise EvidenceLocatorError(
            "unsupported_schema_version",
            f"不支持的 schema version: {value!r}",
        )


def _check_repository_id(value: str) -> None:
    """校验 repository id 等于固定逻辑 namespace。

    Args:
        value: repository id 字符串。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: 值与 ``REPOSITORY_ID`` 不一致时抛出。
    """

    if value != REPOSITORY_ID:
        raise EvidenceLocatorError(
            "unsupported_repository_id",
            f"不支持的 repository id: {value!r}",
        )


def _check_text(value: str, label: str) -> None:
    """校验字符串非空且无首尾空白。

    Args:
        value: 待校验字符串。
        label: 用于错误消息的名称。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: 值为空、非字符串或含首尾空白时抛出。
    """

    if not isinstance(value, str) or value != value.strip() or not value:
        raise EvidenceLocatorError("invalid_format", f"{label} 不能为空或含首尾空白")


def _check_canonical_ticker(value: str) -> None:
    """校验 ticker 满足 canonical 格式。

    Args:
        value: 待校验 ticker。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: ticker 不满足 canonical 格式时抛出。
    """

    if _CANONICAL_TICKER_RE.fullmatch(value) is None:
        raise EvidenceLocatorError(
            "invalid_ticker",
            f"ticker 不是 canonical 格式: {value!r}",
        )


def _check_canonical_document_id(value: str) -> None:
    """校验 document id 满足 canonical 格式。

    Args:
        value: 待校验 document id。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: document id 不满足 canonical 格式时抛出。
    """

    if _CANONICAL_DOCUMENT_ID_RE.fullmatch(value) is None:
        raise EvidenceLocatorError(
            "invalid_document_id",
            f"document_id 不是 canonical 格式: {value!r}",
        )


def _check_lower_hex64(value: str, label: str) -> None:
    """校验字符串为小写 64-hex SHA-256。

    Args:
        value: 待校验字符串。
        label: 用于错误消息的名称。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: 值不是小写 64-hex 时抛出。
    """

    if not isinstance(value, str) or _LOWER_HEX_64_RE.fullmatch(value) is None:
        raise EvidenceLocatorError(
            "invalid_sha256",
            f"{label} 不是小写 64-hex SHA-256: {value!r}",
        )


def _check_source_kind(value: SourceKind | str) -> SourceKind:
    """校验并收窄 source kind 为真实枚举。

    Args:
        value: 待校验值（真实枚举或原始字符串）。

    Returns:
        ``SourceKind`` 枚举值。

    Raises:
        EvidenceLocatorError: 值不是 ``SourceKind`` 枚举时抛出。
    """

    if not isinstance(value, SourceKind):
        raise EvidenceLocatorError(
            "invalid_enum_type",
            f"source_kind 必须是 SourceKind 枚举，实际类型 {type(value).__name__}",
        )
    return value


def _check_artifact_kind(value: ArtifactKind | str) -> ArtifactKind:
    """校验并收窄 artifact kind 为真实枚举。

    Args:
        value: 待校验值（真实枚举或原始字符串）。

    Returns:
        ``ArtifactKind`` 枚举值。

    Raises:
        EvidenceLocatorError: 值不是 ``ArtifactKind`` 枚举时抛出。
    """

    if not isinstance(value, ArtifactKind):
        raise EvidenceLocatorError(
            "invalid_enum_type",
            f"artifact_kind 必须是 ArtifactKind 枚举，实际类型 {type(value).__name__}",
        )
    return value


def _check_locator_kind(value: LocatorKind | str) -> LocatorKind:
    """校验并收窄 locator kind 为真实枚举。

    Args:
        value: 待校验值（真实枚举或原始字符串）。

    Returns:
        ``LocatorKind`` 枚举值。

    Raises:
        EvidenceLocatorError: 值不是 ``LocatorKind`` 枚举时抛出。
    """

    if not isinstance(value, LocatorKind):
        raise EvidenceLocatorError(
            "invalid_enum_type",
            f"locator_kind 必须是 LocatorKind 枚举，实际类型 {type(value).__name__}",
        )
    return value


def _require_real_int(value: JsonScalar, key: str) -> int:
    """校验并返回真实 int（拒绝 bool 与非 int 标量）。

    该 helper 是 int 型 locator 字段 invariant 的单一真源：parser 的
    ``_require_int`` 与 DTO validator 的 ``_check_payload_pairing`` 共同复用，
    保证 JSON number 语义下 ``True``/``False``、字符串与浮点都不被当作整数接受。

    Args:
        value: 待校验的标量值。
        key: 用于错误消息的字段名。

    Returns:
        真实 int 值（不含 bool）。

    Raises:
        EvidenceLocatorError: 值不是真实 int（含 bool/str/float）时抛出。
    """

    if not isinstance(value, int) or isinstance(value, bool):
        raise EvidenceLocatorError(
            "invalid_type",
            f"{key} 必须是整数，不能是布尔值",
        )
    return value


def _check_payload_pairing(locator_kind: LocatorKind, locator_payload: LocatorPayload) -> None:
    """校验 locator kind 与 payload 类型及值约束配对。

    Args:
        locator_kind: 定位器类型。
        locator_payload: 定位器严格 payload。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: payload 类型不匹配或值约束不满足时抛出。
    """

    if locator_kind is LocatorKind.DOCUMENT:
        if not isinstance(locator_payload, DocumentLocatorPayload):
            raise EvidenceLocatorError(
                "invalid_locator_payload",
                "document 定位器 payload 类型不匹配",
            )
        return
    if locator_kind is LocatorKind.PAGE:
        if not isinstance(locator_payload, PageLocatorPayload):
            raise EvidenceLocatorError(
                "invalid_locator_payload",
                "page 定位器 payload 类型不匹配",
            )
        page_no = _require_real_int(locator_payload.page_no, "page_no")
        if page_no <= 0:
            raise EvidenceLocatorError("invalid_format", "page_no 必须是正整数")
        return
    if locator_kind is LocatorKind.SECTION:
        if not isinstance(locator_payload, SectionLocatorPayload):
            raise EvidenceLocatorError(
                "invalid_locator_payload",
                "section 定位器 payload 类型不匹配",
            )
        _check_text(locator_payload.section_ref, "section_ref")
        return
    if locator_kind is LocatorKind.TABLE_CELL:
        if not isinstance(locator_payload, TableCellLocatorPayload):
            raise EvidenceLocatorError(
                "invalid_locator_payload",
                "table_cell 定位器 payload 类型不匹配",
            )
        _check_text(locator_payload.table_ref, "table_ref")
        _check_text(locator_payload.column, "column")
        row_index = _require_real_int(locator_payload.row_index, "row_index")
        if row_index < 0:
            raise EvidenceLocatorError("invalid_format", "row_index 必须是非负整数")
        return
    if locator_kind is LocatorKind.XBRL_FACT:
        if not isinstance(locator_payload, XbrlFactLocatorPayload):
            raise EvidenceLocatorError(
                "invalid_locator_payload",
                "xbrl_fact 定位器 payload 类型不匹配",
            )
        _check_text(locator_payload.concept, "concept")
        _check_lower_hex64(locator_payload.fact_sha256, "fact_sha256")
        return
    raise EvidenceLocatorError(
        "unsupported_locator_kind",
        f"不支持的 locator_kind: {locator_kind.value}",
    )


def _check_artifact_combo(
    artifact_kind: ArtifactKind,
    locator_kind: LocatorKind,
    locator_payload: LocatorPayload,
) -> None:
    """校验 artifact kind 与 locator 组合。

    source artifact 只允许 document 定位器且 payload 为
    ``DocumentLocatorPayload``；processed 允许全部五种。

    Args:
        artifact_kind: 产物类型。
        locator_kind: 定位器类型。
        locator_payload: 定位器严格 payload。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: source artifact 组合不合法时抛出。
    """

    if artifact_kind is ArtifactKind.SOURCE:
        if locator_kind is not LocatorKind.DOCUMENT or not isinstance(
            locator_payload,
            DocumentLocatorPayload,
        ):
            raise EvidenceLocatorError(
                "artifact_kind_not_supported",
                "source artifact 只允许 document 定位器",
            )


def parse_evidence_locator_request(raw: JsonValue) -> EvidenceLocatorRequest:
    """严格解析证据定位器请求。

    双向拒绝 missing/unknown 字段、bool-as-int、空字符串、非 canonical
    ticker/document id、非小写 64-hex SHA、未知 schema version 与未知
    repository id。

    Args:
        raw: 原始请求对象。

    Returns:
        严格校验后的 ``EvidenceLocatorRequest``。

    Raises:
        EvidenceLocatorError: 请求形状或任一字段非法时抛出。
    """

    payload = _require_mapping(raw, "request")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "repository_id",
            "ticker",
            "document_id",
            "source_kind",
            "artifact_kind",
            "document_version",
            "source_fingerprint",
            "primary_content_sha256",
            "locator_kind",
            "locator_payload",
            "locator_content_sha256",
        },
    )
    schema_version = _require_text(payload, "schema_version", "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise EvidenceLocatorError(
            "unsupported_schema_version",
            f"不支持的 schema version: {schema_version!r}",
        )
    repository_id = _require_text(payload, "repository_id", "repository_id")
    if repository_id != REPOSITORY_ID:
        raise EvidenceLocatorError(
            "unsupported_repository_id",
            f"不支持的 repository id: {repository_id!r}",
        )
    ticker = _require_canonical_ticker(payload)
    document_id = _require_canonical_document_id(payload)
    source_kind = _parse_source_kind(payload)
    artifact_kind = _parse_artifact_kind(payload)
    document_version = _require_text(payload, "document_version", "document_version")
    source_fingerprint = _require_lower_hex64(payload, "source_fingerprint")
    primary_content_sha256 = _require_lower_hex64(payload, "primary_content_sha256")
    locator_kind = _parse_locator_kind(payload)
    locator_payload = _parse_locator_payload(payload, locator_kind)
    locator_content_sha256 = _require_lower_hex64(payload, "locator_content_sha256")
    request = EvidenceLocatorRequest(
        schema_version=schema_version,
        repository_id=repository_id,
        ticker=ticker,
        document_id=document_id,
        source_kind=source_kind,
        artifact_kind=artifact_kind,
        document_version=document_version,
        source_fingerprint=source_fingerprint,
        primary_content_sha256=primary_content_sha256,
        locator_kind=locator_kind,
        locator_payload=locator_payload,
        locator_content_sha256=locator_content_sha256,
    )
    validate_evidence_locator_request(request)
    return request


def parse_evidence_locator_projection(raw: JsonValue) -> EvidenceLocatorProjection:
    """严格解析证据定位器投影。

    从 canonical projection 字典重建投影，拒绝 missing/unknown 字段与任何
    非法标量；可用于持久化后的 round-trip 重放。

    Args:
        raw: 原始投影对象。

    Returns:
        严格校验后的 ``EvidenceLocatorProjection``。

    Raises:
        EvidenceLocatorError: 投影形状或任一字段非法时抛出。
    """

    payload = _require_mapping(raw, "projection")
    _require_exact_keys(
        payload,
        {
            "repository_id",
            "ticker",
            "document_id",
            "source_kind",
            "artifact_kind",
            "document_version",
            "source_fingerprint",
            "primary_content_sha256",
            "locator_kind",
            "locator_payload",
            "locator_content_sha256",
        },
    )
    repository_id = _require_text(payload, "repository_id", "repository_id")
    if repository_id != REPOSITORY_ID:
        raise EvidenceLocatorError(
            "unsupported_repository_id",
            f"不支持的 repository id: {repository_id!r}",
        )
    ticker = _require_canonical_ticker(payload)
    document_id = _require_canonical_document_id(payload)
    source_kind = _parse_source_kind(payload)
    artifact_kind = _parse_artifact_kind(payload)
    document_version = _require_text(payload, "document_version", "document_version")
    source_fingerprint = _require_lower_hex64(payload, "source_fingerprint")
    primary_content_sha256 = _require_lower_hex64(payload, "primary_content_sha256")
    locator_kind = _parse_locator_kind(payload)
    locator_payload = _parse_locator_payload(payload, locator_kind)
    locator_content_sha256 = _require_lower_hex64(payload, "locator_content_sha256")
    locator = EvidenceLocatorProjection(
        repository_id=repository_id,
        ticker=ticker,
        document_id=document_id,
        source_kind=source_kind,
        artifact_kind=artifact_kind,
        document_version=document_version,
        source_fingerprint=source_fingerprint,
        primary_content_sha256=primary_content_sha256,
        locator_kind=locator_kind,
        locator_payload=locator_payload,
        locator_content_sha256=locator_content_sha256,
    )
    validate_evidence_locator_projection(locator)
    return locator


def _require_mapping(raw: JsonValue, label: str) -> JsonObject:
    """把原始值收窄为 JSON 对象。

    Args:
        raw: 原始值。
        label: 用于错误消息的名称。

    Returns:
        JSON 对象。

    Raises:
        EvidenceLocatorError: 值不是字典时抛出。
    """

    if not isinstance(raw, dict):
        raise EvidenceLocatorError(
            "invalid_shape",
            f"{label} 必须是 JSON 对象",
        )
    return raw


def _require_exact_keys(payload: Mapping[str, JsonValue], allowed: set[str]) -> None:
    """校验字典字段集合精确等于允许集合。

    Args:
        payload: 目标字典。
        allowed: 允许的字段集合。

    Returns:
        无。

    Raises:
        EvidenceLocatorError: 存在 missing 或 unknown 字段时抛出。
    """

    actual = set(payload.keys())
    missing = sorted(allowed - actual)
    unknown = sorted(actual - allowed)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing={missing}")
        if unknown:
            details.append(f"unknown={unknown}")
        raise EvidenceLocatorError(
            "invalid_fields",
            "字段集合非法: " + ", ".join(details),
        )


def _require_text(payload: Mapping[str, JsonValue], key: str, label: str) -> str:
    """读取并校验非空字符串字段。

    Args:
        payload: 目标字典。
        key: 字段名。
        label: 用于错误消息的名称。

    Returns:
        去首尾空白后仍非空的字符串。

    Raises:
        EvidenceLocatorError: 字段缺失、非字符串、空或含首尾空白时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, str):
        raise EvidenceLocatorError("invalid_type", f"{label} 必须是字符串")
    if value != value.strip():
        raise EvidenceLocatorError("invalid_format", f"{label} 不能包含首尾空白")
    if not value:
        raise EvidenceLocatorError("invalid_format", f"{label} 不能为空")
    return value


def _require_canonical_ticker(payload: Mapping[str, JsonValue]) -> str:
    """读取并校验 canonical ticker。

    Args:
        payload: 目标字典。

    Returns:
        满足 canonical 格式的 ticker。

    Raises:
        EvidenceLocatorError: ticker 缺失、非字符串或不满足 canonical 格式时抛出。
    """

    ticker = _require_text(payload, "ticker", "ticker")
    if _CANONICAL_TICKER_RE.fullmatch(ticker) is None:
        raise EvidenceLocatorError(
            "invalid_ticker",
            f"ticker 不是 canonical 格式: {ticker!r}",
        )
    return ticker


def _require_canonical_document_id(payload: Mapping[str, JsonValue]) -> str:
    """读取并校验 canonical document id。

    Args:
        payload: 目标字典。

    Returns:
        满足 canonical 格式的 document id。

    Raises:
        EvidenceLocatorError: document id 缺失、非字符串或不满足 canonical
        格式时抛出。
    """

    document_id = _require_text(payload, "document_id", "document_id")
    if _CANONICAL_DOCUMENT_ID_RE.fullmatch(document_id) is None:
        raise EvidenceLocatorError(
            "invalid_document_id",
            f"document_id 不是 canonical 格式: {document_id!r}",
        )
    return document_id


def _require_lower_hex64(payload: Mapping[str, JsonValue], key: str) -> str:
    """读取并校验小写 64-hex SHA 字段。

    Args:
        payload: 目标字典。
        key: 字段名。

    Returns:
        小写 64-hex 字符串。

    Raises:
        EvidenceLocatorError: 字段缺失、非字符串或不满足小写 64-hex 时抛出。
    """

    value = _require_text(payload, key, key)
    if _LOWER_HEX_64_RE.fullmatch(value) is None:
        raise EvidenceLocatorError(
            "invalid_sha256",
            f"{key} 不是小写 64-hex SHA-256: {value!r}",
        )
    return value


def _parse_source_kind(payload: Mapping[str, JsonValue]) -> SourceKind:
    """解析 source kind 枚举。

    Args:
        payload: 目标字典。

    Returns:
        ``SourceKind`` 枚举值。

    Raises:
        EvidenceLocatorError: 字段缺失、非字符串或不在 ``filing|material``
        时抛出。
    """

    value = _require_text(payload, "source_kind", "source_kind")
    try:
        return SourceKind(value)
    except ValueError as exc:
        raise EvidenceLocatorError(
            "unsupported_source_kind",
            f"不支持的 source_kind: {value!r}",
        ) from exc


def _parse_artifact_kind(payload: Mapping[str, JsonValue]) -> ArtifactKind:
    """解析 artifact kind 枚举。

    Args:
        payload: 目标字典。

    Returns:
        ``ArtifactKind`` 枚举值。

    Raises:
        EvidenceLocatorError: 字段缺失、非字符串或不在 ``source|processed``
        时抛出。
    """

    value = _require_text(payload, "artifact_kind", "artifact_kind")
    try:
        return ArtifactKind(value)
    except ValueError as exc:
        raise EvidenceLocatorError(
            "unsupported_artifact_kind",
            f"不支持的 artifact_kind: {value!r}",
        ) from exc


def _parse_locator_kind(payload: Mapping[str, JsonValue]) -> LocatorKind:
    """解析 locator kind 枚举。

    Args:
        payload: 目标字典。

    Returns:
        ``LocatorKind`` 枚举值。

    Raises:
        EvidenceLocatorError: 字段缺失、非字符串或不在五种允许值时抛出。
    """

    value = _require_text(payload, "locator_kind", "locator_kind")
    try:
        return LocatorKind(value)
    except ValueError as exc:
        raise EvidenceLocatorError(
            "unsupported_locator_kind",
            f"不支持的 locator_kind: {value!r}",
        ) from exc


def _parse_locator_payload(
    payload: Mapping[str, JsonValue],
    locator_kind: LocatorKind,
) -> LocatorPayload:
    """按 locator kind 解析严格 payload。

    Args:
        payload: 目标字典。
        locator_kind: 定位器类型。

    Returns:
        对应类型的严格 payload。

    Raises:
        EvidenceLocatorError: payload 缺失、字段集合或字段值非法时抛出。
    """

    raw_payload = payload.get("locator_payload")
    if not isinstance(raw_payload, dict):
        raise EvidenceLocatorError(
            "invalid_payload",
            "locator_payload 必须是 JSON 对象",
        )
    if locator_kind is LocatorKind.DOCUMENT:
        if raw_payload:
            raise EvidenceLocatorError(
                "invalid_payload",
                "document 定位器不允许携带任何 payload 字段",
            )
        return DocumentLocatorPayload()
    if locator_kind is LocatorKind.PAGE:
        _require_exact_keys(raw_payload, {"page_no"})
        return PageLocatorPayload(page_no=_require_positive_int(raw_payload, "page_no"))
    if locator_kind is LocatorKind.SECTION:
        _require_exact_keys(raw_payload, {"section_ref"})
        return SectionLocatorPayload(
            section_ref=_require_text(raw_payload, "section_ref", "section_ref"),
        )
    if locator_kind is LocatorKind.TABLE_CELL:
        _require_exact_keys(raw_payload, {"table_ref", "row_index", "column"})
        return TableCellLocatorPayload(
            table_ref=_require_text(raw_payload, "table_ref", "table_ref"),
            row_index=_require_non_negative_int(raw_payload, "row_index"),
            column=_require_text(raw_payload, "column", "column"),
        )
    if locator_kind is LocatorKind.XBRL_FACT:
        _require_exact_keys(raw_payload, {"concept", "fact_sha256"})
        return XbrlFactLocatorPayload(
            concept=_require_text(raw_payload, "concept", "concept"),
            fact_sha256=_require_payload_hex64(raw_payload, "fact_sha256"),
        )
    raise EvidenceLocatorError(
        "unsupported_locator_kind",
        f"不支持的 locator_kind: {locator_kind.value!r}",
    )


def _require_positive_int(payload: Mapping[str, JsonValue], key: str) -> int:
    """读取并校验正整数字段。

    Args:
        payload: 目标字典。
        key: 字段名。

    Returns:
        正整数。

    Raises:
        EvidenceLocatorError: 字段缺失、非整数或不是正整数时抛出。
    """

    value = _require_int(payload, key)
    if value <= 0:
        raise EvidenceLocatorError(
            "invalid_format",
            f"{key} 必须是正整数",
        )
    return value


def _require_non_negative_int(payload: Mapping[str, JsonValue], key: str) -> int:
    """读取并校验非负整数字段。

    Args:
        payload: 目标字典。
        key: 字段名。

    Returns:
        非负整数。

    Raises:
        EvidenceLocatorError: 字段缺失、非整数或负数时抛出。
    """

    value = _require_int(payload, key)
    if value < 0:
        raise EvidenceLocatorError(
            "invalid_format",
            f"{key} 必须是非负整数",
        )
    return value


def _require_int(payload: Mapping[str, JsonValue], key: str) -> int:
    """读取并校验整数字段（拒绝 bool-as-int）。

    与 DTO validator 共用 ``_require_real_int`` 作为真实 int invariant 单一真源。

    Args:
        payload: 目标字典。
        key: 字段名。

    Returns:
        真实整数值。

    Raises:
        EvidenceLocatorError: 字段缺失、非整数或为 bool 时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, int):
        raise EvidenceLocatorError(
            "invalid_type",
            f"{key} 必须是整数",
        )
    return _require_real_int(value, key)


def _require_payload_hex64(payload: Mapping[str, JsonValue], key: str) -> str:
    """读取并校验 payload 内的小写 64-hex 字段。

    Args:
        payload: 目标字典。
        key: 字段名。

    Returns:
        小写 64-hex 字符串。

    Raises:
        EvidenceLocatorError: 字段缺失、非字符串或不满足小写 64-hex 时抛出。
    """

    value = payload.get(key)
    if not isinstance(value, str) or _LOWER_HEX_64_RE.fullmatch(value) is None:
        raise EvidenceLocatorError(
            "invalid_sha256",
            f"{key} 不是小写 64-hex SHA-256: {value!r}",
        )
    return value
