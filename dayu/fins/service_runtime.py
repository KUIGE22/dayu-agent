"""Fins 运行时适配器。"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, AsyncIterator, Callable, Mapping, Optional, Protocol, TypeVar, runtime_checkable

from dayu.contracts.fins import (
    DownloadCommandPayload,
    DownloadCompanyInfo,
    DownloadFailedFile,
    DownloadFilingResultItem,
    DownloadFilingResultStatus,
    DownloadFilters,
    DownloadFilterWindow,
    DownloadProgressPayload,
    DownloadResultData,
    DownloadSummary,
    FinsCommand,
    FinsCommandName,
    FinsCommandPayload,
    FinsEvent,
    FinsEventType,
    FinsProgressEventName,
    FinsResult,
    FinsResultData,
    ProcessCommandPayload,
    ProcessDocumentResultItem,
    ProcessFilingCommandPayload,
    ProcessMaterialCommandPayload,
    ProcessProgressPayload,
    ProcessResultData,
    ProcessSingleResultData,
    ProcessSummary,
    UploadFileResultItem,
    UploadFilingCommandPayload,
    UploadFilingProgressPayload,
    UploadFilingResultData,
    UploadFilingsFromCommandPayload,
    UploadFilingsFromMaterialItem,
    UploadFilingsFromRecognizedItem,
    UploadFilingsFromResultData,
    UploadFilingsFromSkippedItem,
    UploadMaterialCommandPayload,
    UploadMaterialProgressPayload,
    UploadMaterialResultData,
)
from dayu.engine.processors.processor_registry import ProcessorRegistry
from dayu.fins._converters import int_or_zero, optional_int
from dayu.fins.cli_support import (
    _coerce_document_ids_input as coerce_document_ids_input,
)
from dayu.fins.cli_support import (
    _coerce_forms_input as coerce_forms_input,
)
from dayu.fins.cli_support import (
    _generate_upload_filings_script as generate_upload_filings_script,
)
from dayu.fins.cli_support import (
    _prepare_cli_args as prepare_cli_args,
)
from dayu.fins.cli_support import (
    _validate_upload_filing_args as validate_upload_filing_args,
)
from dayu.fins.cli_support import (
    _validate_upload_material_args as validate_upload_material_args,
)
from dayu.fins.domain.document_models import BatchToken, CompanyMeta, FilingSummary
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.evidence_locator import (
    REPOSITORY_ID,
    ArtifactKind,
    CitationProjection,
    EvidenceLocatorError,
    EvidenceLocatorProjection,
    EvidenceLocatorRequest,
    JsonValue,
    LocatorKind,
    LocatorPayload,
    PageLocatorPayload,
    SectionLocatorPayload,
    TableCellLocatorPayload,
    XbrlFactLocatorPayload,
    canonical_json_bytes,
    is_lower_hex_sha256,
    sha256_hex,
    validate_evidence_locator_projection,
    validate_evidence_locator_request,
)
from dayu.fins.domain.source_sync import FinsWorkerSyncRequest, FinsWorkerSyncResult
from dayu.fins.ingestion.factory import (
    IngestionServiceFactory,
    build_ingestion_manager_key,
    build_ingestion_service_factory,
)
from dayu.fins.ingestion.process_events import ProcessEvent
from dayu.fins.pipelines import PipelineProtocol, get_pipeline_from_normalized_ticker
from dayu.fins.pipelines.cn_download_pdf_gate import (
    CnDownloadPdfGateProtocol,
    NoopCnDownloadPdfGate,
)
from dayu.fins.pipelines.cn_download_protocols import CnPreparationGate
from dayu.fins.pipelines.download_events import DownloadEvent
from dayu.fins.pipelines.upload_filing_events import UploadFilingEvent
from dayu.fins.pipelines.upload_material_events import UploadMaterialEvent
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.source_sync_runtime import (
    DefaultFinsWorkerSourceSyncRuntime,
    FinsSourceSyncDownloadPipelineProtocol,
)
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    CompanyMetaRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    FilingMaintenanceRepositoryProtocol,
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import (
    _FsRepositorySet,
    build_fs_repository_set,
)
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.fins.tools.result_types import TableDetailResult
from dayu.fins.tools.service import FinsToolService
from dayu.log import Log

_LOG_MODULE = "FINS.RUNTIME"

_EVIDENCE_TOOL_CACHE_MAX_ENTRIES = 8
"""request-scoped FinsToolService 的 processor 缓存容量上限。

evidence 读取必须每次从空 cache 构建当前 processor，容量只需容纳单次读取
涉及的少量文档，避免与共享 tool service 共享任何状态。
"""

_XBRL_CANONICAL_FIELDS: tuple[str, ...] = (
    "concept",
    "label",
    "numeric_value",
    "text_value",
    "content_type",
    "unit",
    "decimals",
    "period_type",
    "period_start",
    "period_end",
    "fiscal_year",
    "fiscal_period",
    "statement_type",
)
"""XBRL canonical fact row 的精确 13 字段清单（缺值为 JSON null）。"""


@dataclass(frozen=True)
class _EvidenceIdentity:
    """证据定位器 identity 内部载体。

    由 ``EvidenceLocatorRequest`` 或 ``EvidenceLocatorProjection`` 投影为同一
    结构，供 resolve/validate/read 复用同一验证核心。

    Attributes:
        ticker: 股票代码。
        document_id: 文档 ID。
        source_kind: 来源类型。
        artifact_kind: 产物类型。
        document_version: source 文档版本。
        source_fingerprint: source 主文件指纹。
        primary_content_sha256: 期望的 source 主文件 SHA-256。
        locator_kind: 定位器类型。
        locator_payload: 定位器严格 payload。
        locator_content_sha256: 期望的 canonical fragment SHA-256。
    """

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


@dataclass(frozen=True)
class _ProcessedIdentityState:
    """processed meta 的 identity 相关状态快照。

    Attributes:
        exists: processed 文档是否存在。
        is_deleted: 是否逻辑删除。
        reprocess_required: 是否需要重新处理。
        source_kind: processed meta 中的 source kind 字段。
        source_document_version: processed meta 中的 source 文档版本字段。
        source_fingerprint: processed meta 中的 source 指纹字段。
    """

    exists: bool
    is_deleted: bool
    reprocess_required: bool
    source_kind: str | None
    source_document_version: str | None
    source_fingerprint: str | None


@dataclass(frozen=True)
class _SourceIdentityState:
    """source/processed identity preflight 状态快照。

    供 postflight double-read 逐字段比较；任一字段漂移均 fail closed。

    Attributes:
        ticker: 股票代码。
        document_id: 文档 ID。
        source_kind: 来源类型。
        artifact_kind: 产物类型。
        document_version: 当前 source meta 的文档版本。
        source_fingerprint: 当前 source meta 的指纹。
        counterpart_visible: 相反 source kind 是否仍可被工具发现
            （含逻辑删除）。
        processed: processed identity 状态；source artifact 时为 ``None``。
    """

    ticker: str
    document_id: str
    source_kind: SourceKind
    artifact_kind: ArtifactKind
    document_version: str
    source_fingerprint: str
    counterpart_visible: bool
    processed: _ProcessedIdentityState | None


@dataclass(frozen=True)
class _PrimarySource:
    """source 主文件读取结果。

    Attributes:
        content: 主文件 exact bytes（唯一来源为 ``get_primary_source().open()``）。
        sha256: 实算 SHA-256（小写 64-hex）。
        media_type: 主文件 MIME 类型。
    """

    content: bytes
    sha256: str
    media_type: str


@dataclass(frozen=True)
class _VerifiedEvidence:
    """已验证的 evidence 读取结果。

    Attributes:
        primary_sha256: 实算的 source 主文件 SHA-256。
        media_type: source 主文件 MIME 类型。
        fragment_bytes: canonical evidence fragment bytes。
    """

    primary_sha256: str
    media_type: str
    fragment_bytes: bytes


def _to_evidence_identity(request: EvidenceLocatorRequest) -> _EvidenceIdentity:
    """把请求投影为 identity 载体。

    Args:
        request: 证据定位器请求。

    Returns:
        identity 载体。

    Raises:
        无。
    """

    return _EvidenceIdentity(
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


def _locator_to_evidence_identity(locator: EvidenceLocatorProjection) -> _EvidenceIdentity:
    """把投影投影为 identity 载体。

    Args:
        locator: 证据定位器投影。

    Returns:
        identity 载体。

    Raises:
        无。
    """

    return _EvidenceIdentity(
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


def _as_optional_text(value: JsonValue) -> str | None:
    """把任意值标准化为可选字符串。

    Args:
        value: 原始值。

    Returns:
        去首尾空白后的字符串；为空时返回 ``None``。

    Raises:
        无。
    """

    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _require_meta_text(
    meta: Mapping[str, JsonValue],
    key: str,
    *,
    error_code: str,
    message: str,
) -> str:
    """读取并校验 meta 中的非空字符串字段。

    Args:
        meta: meta 字典。
        key: 字段名。
        error_code: 校验失败时的错误码。
        message: 校验失败时的错误说明。

    Returns:
        非空且无首尾空白的字符串。

    Raises:
        EvidenceLocatorError: 字段缺失、非字符串、为空或含首尾空白时抛出。
    """

    value = meta.get(key)
    if not isinstance(value, str) or value != value.strip() or not value:
        raise EvidenceLocatorError(error_code, message)
    return value


def _require_meta_fingerprint(
    meta: Mapping[str, JsonValue],
    *,
    error_code: str,
    message: str,
) -> str:
    """读取并校验 meta 中的 source fingerprint 字段。

    Args:
        meta: meta 字典。
        error_code: 校验失败时的错误码。
        message: 校验失败时的错误说明。

    Returns:
        小写 64-hex 指纹。

    Raises:
        EvidenceLocatorError: 字段缺失、非字符串或不是小写 64-hex 时抛出。
    """

    value = meta.get("source_fingerprint")
    if not isinstance(value, str) or not is_lower_hex_sha256(value):
        raise EvidenceLocatorError(error_code, message)
    return value


def _canonical_xbrl_row(fact: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """构建 XBRL canonical fact row。

    精确提取 13 个字段，所有键总是存在、缺值为 JSON null；排除派生的
    ``scale`` 等非 canonical 字段。

    Args:
        fact: 单条 fact 字典。

    Returns:
        canonical fact row。

    Raises:
        无。
    """

    return {field_name: fact.get(field_name) for field_name in _XBRL_CANONICAL_FIELDS}


PayloadT = TypeVar(
    "PayloadT",
    PageLocatorPayload,
    SectionLocatorPayload,
    TableCellLocatorPayload,
    XbrlFactLocatorPayload,
)
"""locator payload 类型变量。"""


def _require_payload_type(
    payload: LocatorPayload,
    expected: type[PayloadT],
    label: str,
) -> PayloadT:
    """把联合 payload 收窄为期望类型。

    Args:
        payload: 联合 payload。
        expected: 期望的 payload 类型。
        label: 用于错误消息的定位器名称。

    Returns:
        收窄后的 payload。

    Raises:
        EvidenceLocatorError: payload 与期望类型不一致时抛出。
    """

    if not isinstance(payload, expected):
        raise EvidenceLocatorError(
            "invalid_locator_payload",
            f"{label} 定位器 payload 类型不匹配",
        )
    return payload


def _build_table_cell_fragment(
    result: TableDetailResult,
    payload: TableCellLocatorPayload,
) -> bytes:
    """从 ``get_table`` 结果构建 table_cell canonical fragment。

    Args:
        result: ``get_table`` 返回结果。
        payload: table_cell 定位器 payload。

    Returns:
        canonical JSON bytes（``column`` / ``row_index`` / ``table_ref`` /
        ``value`` 精确字段）。

    Raises:
        EvidenceLocatorError: 表格不是 records 数据、行越界或列缺失时抛出。
    """

    data = result.get("data")
    if not isinstance(data, dict) or data.get("kind") != "records":
        raise EvidenceLocatorError(
            "table_not_records",
            f"table={payload.table_ref} 不是 records 数据，无法定位单元格",
        )
    rows = data.get("rows")
    if not isinstance(rows, list) or payload.row_index >= len(rows):
        raise EvidenceLocatorError(
            "table_row_out_of_range",
            f"table={payload.table_ref} 行越界: row_index={payload.row_index}",
        )
    row = rows[payload.row_index]
    if not isinstance(row, dict) or payload.column not in row:
        raise EvidenceLocatorError(
            "table_column_missing",
            f"table={payload.table_ref} 缺少列: column={payload.column!r}",
        )
    fragment = {
        "column": payload.column,
        "row_index": payload.row_index,
        "table_ref": payload.table_ref,
        "value": row[payload.column],
    }
    return canonical_json_bytes(fragment)


def _build_xbrl_fact_fragment(
    tool_service: FinsToolService,
    *,
    ticker: str,
    document_id: str,
    payload: XbrlFactLocatorPayload,
) -> bytes:
    """从 ``query_xbrl_facts`` 结果构建 xbrl_fact canonical fragment。

    exact concept 查询后，对返回的每条 fact 构建 canonical 13 字段 row 并
    逐 row 求 SHA；必须恰好一条匹配 ``fact_sha256``，0 条或重复匹配拒绝。

    Args:
        tool_service: request-scoped FinsToolService。
        ticker: 股票代码。
        document_id: 文档 ID。
        payload: xbrl_fact 定位器 payload。

    Returns:
        canonical fact row 的 canonical JSON bytes。

    Raises:
        EvidenceLocatorError: fact 列表缺失、concept 不匹配或 SHA 匹配数
            不为 1 时抛出。
    """

    result = tool_service.query_xbrl_facts(
        ticker=ticker,
        document_id=document_id,
        concepts=[payload.concept],
    )
    facts = result.get("facts")
    if not isinstance(facts, list):
        raise EvidenceLocatorError(
            "xbrl_facts_unavailable",
            f"concept={payload.concept} 未返回 facts 列表",
        )
    matched_rows: list[dict[str, JsonValue]] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        if str(fact.get("concept") or "") != payload.concept:
            continue
        row = _canonical_xbrl_row(fact)
        if sha256_hex(canonical_json_bytes(row)) == payload.fact_sha256:
            matched_rows.append(row)
    if len(matched_rows) != 1:
        raise EvidenceLocatorError(
            "xbrl_fact_not_unique",
            f"concept={payload.concept} 的 canonical row SHA 匹配 {len(matched_rows)} 条",
        )
    return canonical_json_bytes(matched_rows[0])


def _resolve_fragment_bytes(
    tool_service: FinsToolService,
    *,
    ticker: str,
    document_id: str,
    artifact_kind: ArtifactKind,
    locator_kind: LocatorKind,
    locator_payload: LocatorPayload,
    primary_bytes: bytes,
) -> bytes:
    """解析 evidence canonical fragment bytes。

    source artifact 只允许 document 定位器并返回主文件 exact bytes；processed
    artifact 按定位器类型从 tool public API 结果构建严格字段集，剥离一切
    tool wrapper / citation / 路径信息。

    Args:
        tool_service: request-scoped FinsToolService。
        ticker: 股票代码。
        document_id: 文档 ID。
        artifact_kind: 产物类型。
        locator_kind: 定位器类型。
        locator_payload: 定位器严格 payload。
        primary_bytes: source 主文件 exact bytes。

    Returns:
        canonical fragment bytes。

    Raises:
        EvidenceLocatorError: artifact/locator 组合非法、page 不支持、
            table/XBRL 规则不满足或 tool 读取失败时抛出。
    """

    if artifact_kind is ArtifactKind.SOURCE:
        if locator_kind is not LocatorKind.DOCUMENT:
            raise EvidenceLocatorError(
                "artifact_kind_not_supported",
                f"source artifact 只支持 document 定位器，收到 {locator_kind.value}",
            )
        return primary_bytes
    if locator_kind is LocatorKind.DOCUMENT:
        sections_result = tool_service.get_document_sections(ticker=ticker, document_id=document_id)
        tables_result = tool_service.list_tables(ticker=ticker, document_id=document_id)
        document_fragment: dict[str, JsonValue] = {
            "sections": sections_result.get("sections"),
            "tables": tables_result.get("tables"),
        }
        return canonical_json_bytes(document_fragment)
    if locator_kind is LocatorKind.PAGE:
        page_payload = _require_payload_type(locator_payload, PageLocatorPayload, "page")
        page_result = tool_service.get_page_content(
            ticker=ticker,
            document_id=document_id,
            page_no=page_payload.page_no,
        )
        if not bool(page_result.get("supported", False)):
            raise EvidenceLocatorError(
                "page_not_supported",
                f"page={page_payload.page_no} 不支持页面内容",
            )
        fragment: dict[str, JsonValue] = {
            "page_no": page_result.get("page_no"),
            "sections": page_result.get("sections"),
            "tables": page_result.get("tables"),
            "text_preview": page_result.get("text_preview"),
            "has_content": page_result.get("has_content"),
            "total_items": page_result.get("total_items"),
            "supported": page_result.get("supported"),
        }
        return canonical_json_bytes(fragment)
    if locator_kind is LocatorKind.SECTION:
        section_payload = _require_payload_type(locator_payload, SectionLocatorPayload, "section")
        section_result = tool_service.read_section(
            ticker=ticker,
            document_id=document_id,
            ref=section_payload.section_ref,
        )
        section_fragment: dict[str, JsonValue] = {
            "ref": section_result.get("ref"),
            "title": section_result.get("title"),
            "item": section_result.get("item"),
            "topic": section_result.get("topic"),
            "content": section_result.get("content"),
            "children": section_result.get("children"),
            "page_range": section_result.get("page_range"),
            "content_word_count": section_result.get("content_word_count"),
        }
        return canonical_json_bytes(section_fragment)
    if locator_kind is LocatorKind.TABLE_CELL:
        cell_payload = _require_payload_type(locator_payload, TableCellLocatorPayload, "table_cell")
        table_result = tool_service.get_table(
            ticker=ticker,
            document_id=document_id,
            table_ref=cell_payload.table_ref,
        )
        return _build_table_cell_fragment(table_result, cell_payload)
    if locator_kind is LocatorKind.XBRL_FACT:
        xbrl_payload = _require_payload_type(locator_payload, XbrlFactLocatorPayload, "xbrl_fact")
        return _build_xbrl_fact_fragment(
            tool_service,
            ticker=ticker,
            document_id=document_id,
            payload=xbrl_payload,
        )
    raise EvidenceLocatorError(
        "unsupported_locator_kind",
        f"不支持的 locator_kind: {locator_kind.value}",
    )


@runtime_checkable
class CompanyMetaProviderProtocol(Protocol):
    """提供公司名称与公司元信息摘要的窄协议。"""

    def get_company_name(self, ticker: str) -> str:
        """返回公司名称。"""

        ...

    def get_company_meta_summary(self, ticker: str) -> dict[str, str]:
        """返回公司基础 meta 摘要。"""

        ...


@runtime_checkable
class FinsRuntimeProtocol(CompanyMetaProviderProtocol, Protocol):
    """Fins 运行时协议。"""

    def validate_command(self, command: FinsCommand) -> None:
        """在执行前同步校验命令是否可被受理。"""

        ...

    async def sync_worker_source(
        self,
        request: FinsWorkerSyncRequest,
        *,
        cancel_checker: Callable[[], bool],
    ) -> FinsWorkerSyncResult:
        """Synchronize one bounded worker source request."""

        ...

    def execute(
        self,
        command: FinsCommand,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> FinsResult | AsyncIterator[FinsEvent]:
        """执行财报命令。"""

        ...

    def get_processor_registry(self) -> ProcessorRegistry:
        """返回处理器注册表。"""

        ...

    def get_tool_service(self, *, processor_cache_max_entries: int = 128) -> FinsToolService:
        """返回共享的 FinsToolService 实例。

        首次调用时按指定参数创建并缓存，后续调用返回已有实例。

        Args:
            processor_cache_max_entries: Processor 缓存最大条目数（仅首次创建时生效）。

        Returns:
            共享的 FinsToolService 实例。
        """

        ...

    def resolve_evidence_locator(self, request: EvidenceLocatorRequest) -> EvidenceLocatorProjection:
        """解析并验证证据定位器请求，返回当前 projection。

        Args:
            request: 证据定位器请求。

        Returns:
            与当前 owner 状态一致的证据定位器投影。

        Raises:
            EvidenceLocatorError: source/processed identity closure、content hash、
                dual-kind 碰撞或读取中状态漂移不满足时抛出。
        """

        ...

    def validate_evidence_locator(self, locator: EvidenceLocatorProjection) -> None:
        """重算并逐字段验证持久化的证据定位器投影。

        Args:
            locator: 待验证的证据定位器投影。

        Returns:
            无。

        Raises:
            EvidenceLocatorError: 投影任一 identity/content 字段与当前 owner 状态
                不一致或读取中状态漂移时抛出。
        """

        ...

    def read_citation_projection(self, locator: EvidenceLocatorProjection) -> CitationProjection:
        """验证定位器并读取 canonical citation 结果。

        Args:
            locator: 已验证的证据定位器投影。

        Returns:
            只读 citation 结果；``sha256(content_bytes)`` 必须等于
            ``locator.locator_content_sha256``。

        Raises:
            EvidenceLocatorError: 投影验证失败或读取中状态漂移时抛出。
        """

        ...

    def build_ingestion_service_factory(self) -> IngestionServiceFactory:
        """构建按 ticker 路由的长事务服务工厂。"""

        ...

    def get_ingestion_manager_key(self) -> str:
        """返回长事务 job 管理器 key。"""

        ...

    def list_source_filings(self, ticker: str) -> list[FilingSummary]:
        """列出指定股票的已下载财报源文件摘要。

        Args:
            ticker: 股票代码。

        Returns:
            财报源文件摘要列表。
        """

        ...

def _default_batching_repository_factory() -> BatchingRepositoryProtocol:
    """构造未显式注入时的默认 batching repository。

    仅用于直接构造 ``DefaultFinsRuntime`` 且未显式传入
    ``batching_repository`` 的退化路径；``create()`` 总是显式传入。此处返回
    一个未绑定 workspace 的空实现并在首次使用时失败，防止静默持有错误状态。

    Args:
        无。

    Returns:
        未绑定的 batching repository 占位。

    Raises:
        无。
    """

    return _UnboundBatchingRepository()


class _UnboundBatchingRepository:
    """未绑定 workspace 的 batching repository 占位。

    直接构造 ``DefaultFinsRuntime`` 且未显式传 ``batching_repository`` 时，
    runtime 会持有本占位；任何 batch 调用都会失败，提示应经 ``create()``
    装配。
    """

    def begin_batch(self, ticker: str) -> BatchToken:
        """开启批处理事务（未绑定，禁止调用）。

        Args:
            ticker: 股票代码。

        Returns:
            无返回值（总是抛出）。

        Raises:
            RuntimeError: 未绑定 workspace 时抛出。
        """

        raise RuntimeError("DefaultFinsRuntime 未装配 batching repository，请使用 create()")

    def commit_batch(self, token: BatchToken) -> None:
        """提交批处理事务（未绑定，禁止调用）。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            RuntimeError: 未绑定 workspace 时抛出。
        """

        raise RuntimeError("DefaultFinsRuntime 未装配 batching repository，请使用 create()")

    def rollback_batch(self, token: BatchToken) -> None:
        """回滚批处理事务（未绑定，禁止调用）。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            RuntimeError: 未绑定 workspace 时抛出。
        """

        raise RuntimeError("DefaultFinsRuntime 未装配 batching repository，请使用 create()")

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """恢复孤儿 batch（未绑定，禁止调用）。

        Args:
            dry_run: 是否仅返回动作。

        Returns:
            无返回值（总是抛出）。

        Raises:
            RuntimeError: 未绑定 workspace 时抛出。
        """

        raise RuntimeError("DefaultFinsRuntime 未装配 batching repository，请使用 create()")


def _coerce_forms_input(value: Any) -> Optional[str]:
    """标准化 `forms` 参数。"""

    if value is None:
        return None
    return coerce_forms_input(value)


def _coerce_document_ids_input(value: Any) -> Optional[list[str]]:
    """标准化 `document_ids` 参数。"""

    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return None
    return coerce_document_ids_input(value)


def _build_pipeline(
    *,
    ticker: str,
    workspace_root: Path,
    company_repository: CompanyMetaRepositoryProtocol,
    source_repository: SourceDocumentRepositoryProtocol,
    processed_repository: ProcessedDocumentRepositoryProtocol,
    blob_repository: DocumentBlobRepositoryProtocol,
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol,
    processor_registry: ProcessorRegistry,
    cn_download_pdf_gate: CnDownloadPdfGateProtocol,
    batching_repository: BatchingRepositoryProtocol,
    preparation_gate: CnPreparationGate,
) -> PipelineProtocol:
    """按 ticker 构建 pipeline。"""

    normalized_ticker = normalize_ticker(ticker)
    return get_pipeline_from_normalized_ticker(
        normalized_ticker=normalized_ticker,
        workspace_root=workspace_root,
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        blob_repository=blob_repository,
        filing_maintenance_repository=filing_maintenance_repository,
        processor_registry=processor_registry,
        cn_download_pdf_gate=cn_download_pdf_gate,
        batching_repository=batching_repository,
        preparation_gate=preparation_gate,
    )


@dataclass(frozen=True)
class _PreparedDownloadArgs:
    """下载命令的运行时准备参数。"""

    ticker: str
    form_type: str | list[str] | None
    start_date: str | None
    end_date: str | None
    overwrite: bool
    rebuild: bool
    ticker_aliases: list[str] | None


@dataclass(frozen=True)
class _PreparedProcessArgs:
    """处理命令的运行时准备参数。"""

    ticker: str
    document_ids: list[str] | None
    overwrite: bool
    ci: bool


@dataclass(frozen=True)
class _PreparedUploadFilingArgs:
    """上传财报命令的运行时准备参数。"""

    ticker: str
    action: str | None
    fiscal_year: int
    fiscal_period: str
    amended: bool
    filing_date: str | None
    report_date: str | None
    company_id: str | None
    company_name: str | None
    ticker_aliases: list[str] | None
    overwrite: bool


@dataclass(frozen=True)
class _PreparedUploadMaterialArgs:
    """上传材料命令的运行时准备参数。"""

    ticker: str
    action: str | None
    form_type: str
    material_name: str
    document_id: str | None
    internal_document_id: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    filing_date: str | None
    report_date: str | None
    company_id: str | None
    company_name: str | None
    ticker_aliases: list[str] | None
    overwrite: bool


@dataclass(frozen=True)
class _PreparedUploadFilingsFromArgs:
    """批量上传脚本生成命令的运行时准备参数。"""

    ticker: str
    original_ticker: str
    base: str
    source_dir: str
    action: str | None
    output_script: str | None
    recursive: bool
    amended: bool
    filing_date: str | None
    report_date: str | None
    company_id: str | None
    company_name: str | None
    original_company_name: str | None
    infer: bool
    overwrite: bool
    material_forms: str | None
    verbose: bool
    debug: bool
    info: bool
    quiet: bool
    log_level: str | None
    ticker_aliases: list[str] | None
    generated_ticker_csv: str


def _optional_string_list(value: object) -> list[str] | None:
    """把 Namespace 中的可选字符串序列收窄为 `list[str] | None`。

    Args:
        value: 原始属性值。

    Returns:
        规范化后的字符串列表；空值时返回 `None`。

    Raises:
        无。
    """

    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        normalized = [str(item).strip() for item in value if str(item).strip()]
        return normalized or None
    normalized_value = str(value).strip()
    return [normalized_value] if normalized_value else None


def _build_upload_filing_args(
    payload: UploadFilingCommandPayload,
    workspace_root: Path,
) -> _PreparedUploadFilingArgs:
    """为上传财报命令构建强类型准备参数。"""

    namespace = _build_upload_filing_namespace(payload, workspace_root)
    validate_upload_filing_args(namespace)
    return _PreparedUploadFilingArgs(
        ticker=str(namespace.ticker),
        action=str(namespace.action).strip() or None if namespace.action is not None else None,
        fiscal_year=int(namespace.fiscal_year),
        fiscal_period=str(namespace.fiscal_period),
        amended=bool(namespace.amended),
        filing_date=str(namespace.filing_date).strip() or None if namespace.filing_date is not None else None,
        report_date=str(namespace.report_date).strip() or None if namespace.report_date is not None else None,
        company_id=str(namespace.company_id).strip() or None if namespace.company_id is not None else None,
        company_name=str(namespace.company_name).strip() or None if namespace.company_name is not None else None,
        ticker_aliases=_optional_string_list(getattr(namespace, "ticker_aliases", None)),
        overwrite=bool(namespace.overwrite),
    )


def _build_download_args(
    payload: DownloadCommandPayload,
    workspace_root: Path,
) -> _PreparedDownloadArgs:
    """为下载命令构建强类型准备参数。"""

    namespace = _build_download_namespace(payload, workspace_root)
    return _PreparedDownloadArgs(
        ticker=str(namespace.ticker),
        form_type=namespace.form_type,
        start_date=str(namespace.start_date).strip() or None if namespace.start_date is not None else None,
        end_date=str(namespace.end_date).strip() or None if namespace.end_date is not None else None,
        overwrite=bool(namespace.overwrite),
        rebuild=bool(namespace.rebuild),
        ticker_aliases=_optional_string_list(getattr(namespace, "ticker_aliases", None)),
    )


def _build_process_args(
    payload: ProcessCommandPayload,
    workspace_root: Path,
) -> _PreparedProcessArgs:
    """为处理命令构建强类型准备参数。"""

    namespace = _build_process_namespace(payload, workspace_root)
    return _PreparedProcessArgs(
        ticker=str(namespace.ticker),
        document_ids=_optional_string_list(namespace.document_ids),
        overwrite=bool(namespace.overwrite),
        ci=bool(namespace.ci),
    )


def _build_upload_material_args(
    payload: UploadMaterialCommandPayload,
    workspace_root: Path,
) -> _PreparedUploadMaterialArgs:
    """为上传材料命令构建强类型准备参数。"""

    namespace = _build_upload_material_namespace(payload, workspace_root)
    validate_upload_material_args(namespace)
    return _PreparedUploadMaterialArgs(
        ticker=str(namespace.ticker),
        action=str(namespace.action).strip() or None if namespace.action is not None else None,
        form_type=str(namespace.form_type),
        material_name=str(namespace.material_name),
        document_id=str(namespace.document_id).strip() or None if namespace.document_id is not None else None,
        internal_document_id=(
            str(namespace.internal_document_id).strip() or None
            if namespace.internal_document_id is not None
            else None
        ),
        fiscal_year=int(namespace.fiscal_year) if namespace.fiscal_year is not None else None,
        fiscal_period=str(namespace.fiscal_period).strip() or None if namespace.fiscal_period is not None else None,
        filing_date=str(namespace.filing_date).strip() or None if namespace.filing_date is not None else None,
        report_date=str(namespace.report_date).strip() or None if namespace.report_date is not None else None,
        company_id=str(namespace.company_id).strip() or None if namespace.company_id is not None else None,
        company_name=str(namespace.company_name).strip() or None if namespace.company_name is not None else None,
        ticker_aliases=_optional_string_list(getattr(namespace, "ticker_aliases", None)),
        overwrite=bool(namespace.overwrite),
    )


def _build_upload_filings_from_args(
    payload: UploadFilingsFromCommandPayload,
    workspace_root: Path,
) -> _PreparedUploadFilingsFromArgs:
    """为批量上传脚本命令构建强类型准备参数。"""

    namespace = _build_upload_filings_from_namespace(payload, workspace_root)
    generated_ticker_csv = str(getattr(namespace, "generated_ticker_csv", "")).strip()
    if not generated_ticker_csv:
        raise ValueError("upload_filings_from 缺少 generated_ticker_csv")
    return _PreparedUploadFilingsFromArgs(
        ticker=str(namespace.ticker),
        original_ticker=str(getattr(namespace, "original_ticker", namespace.ticker)),
        base=str(namespace.base),
        source_dir=str(namespace.source_dir),
        action=str(namespace.action).strip() or None if namespace.action is not None else None,
        output_script=str(namespace.output_script).strip() or None if namespace.output_script is not None else None,
        recursive=bool(namespace.recursive),
        amended=bool(namespace.amended),
        filing_date=str(namespace.filing_date).strip() or None if namespace.filing_date is not None else None,
        report_date=str(namespace.report_date).strip() or None if namespace.report_date is not None else None,
        company_id=str(namespace.company_id).strip() or None if namespace.company_id is not None else None,
        company_name=str(namespace.company_name).strip() or None if namespace.company_name is not None else None,
        original_company_name=(
            str(getattr(namespace, "original_company_name", None)).strip() or None
            if getattr(namespace, "original_company_name", None) is not None
            else None
        ),
        infer=bool(namespace.infer),
        overwrite=bool(namespace.overwrite),
        material_forms=str(namespace.material_forms).strip() or None if namespace.material_forms is not None else None,
        verbose=bool(namespace.verbose),
        debug=bool(namespace.debug),
        info=bool(namespace.info),
        quiet=bool(namespace.quiet),
        log_level=str(namespace.log_level).strip() or None if namespace.log_level is not None else None,
        ticker_aliases=_optional_string_list(getattr(namespace, "ticker_aliases", None)),
        generated_ticker_csv=generated_ticker_csv,
    )


def _load_company_meta_best_effort(
    repository: CompanyMetaRepositoryProtocol,
    *,
    ticker: str,
) -> CompanyMeta | None:
    """以 best-effort 方式读取公司元数据。

    Args:
        repository: 公司元数据仓储。
        ticker: 股票代码。

    Returns:
        公司元数据；不存在或底层读取失败时返回 `None`。

    Raises:
        无。
    """

    try:
        return repository.get_company_meta(ticker)
    except (FileNotFoundError, ValueError, OSError):
        return None


def _build_upload_filing_namespace(payload: UploadFilingCommandPayload, workspace_root: Path) -> Namespace:
    """为上传财报校验构建命名空间。"""

    namespace = Namespace(
        command="upload_filing",
        ticker=payload.ticker,
        base=str(workspace_root),
        action=payload.action,
        files=[str(path) for path in payload.files],
        fiscal_year=payload.fiscal_year,
        fiscal_period=payload.fiscal_period,
        amended=payload.amended,
        filing_date=payload.filing_date,
        report_date=payload.report_date,
        company_id=payload.company_id,
        company_name=payload.company_name,
        infer=payload.infer,
        ticker_aliases=list(payload.ticker_aliases),
        overwrite=payload.overwrite,
    )
    prepare_cli_args(namespace)
    return namespace


def _build_download_namespace(payload: DownloadCommandPayload, workspace_root: Path) -> Namespace:
    """为下载命令构建并规范化命名空间。"""

    namespace = Namespace(
        command="download",
        ticker=payload.ticker,
        base=str(workspace_root),
        form_type=list(payload.form_type) if payload.form_type else None,
        start_date=payload.start_date,
        end_date=payload.end_date,
        overwrite=payload.overwrite,
        rebuild=payload.rebuild,
        infer=payload.infer,
        ticker_aliases=list(payload.ticker_aliases),
    )
    prepare_cli_args(namespace)
    return namespace


def _build_process_namespace(payload: ProcessCommandPayload, workspace_root: Path) -> Namespace:
    """为处理命令构建并规范化命名空间。"""

    namespace = Namespace(
        command="process",
        ticker=payload.ticker,
        base=str(workspace_root),
        document_ids=list(payload.document_ids) if payload.document_ids else None,
        overwrite=payload.overwrite,
        ci=payload.ci,
    )
    prepare_cli_args(namespace)
    return namespace


def _build_upload_material_namespace(payload: UploadMaterialCommandPayload, workspace_root: Path) -> Namespace:
    """为上传材料校验构建命名空间。"""

    namespace = Namespace(
        command="upload_material",
        ticker=payload.ticker,
        base=str(workspace_root),
        action=payload.action,
        form_type=payload.form_type,
        material_name=payload.material_name,
        files=[str(path) for path in payload.files],
        document_id=payload.document_id,
        internal_document_id=payload.internal_document_id,
        fiscal_year=payload.fiscal_year,
        fiscal_period=payload.fiscal_period,
        filing_date=payload.filing_date,
        report_date=payload.report_date,
        company_id=payload.company_id,
        company_name=payload.company_name,
        infer=payload.infer,
        ticker_aliases=list(payload.ticker_aliases),
        overwrite=payload.overwrite,
    )
    prepare_cli_args(namespace)
    return namespace


def _build_upload_filings_from_namespace(
    payload: UploadFilingsFromCommandPayload,
    workspace_root: Path,
) -> Namespace:
    """为批量上传脚本生成构建命名空间。"""

    namespace = Namespace(
        command="upload_filings_from",
        ticker=payload.ticker,
        base=str(workspace_root),
        source_dir=str(payload.source_dir),
        action=payload.action,
        output_script=str(payload.output_script) if payload.output_script is not None else None,
        recursive=payload.recursive,
        amended=payload.amended,
        filing_date=payload.filing_date,
        report_date=payload.report_date,
        company_id=payload.company_id,
        company_name=payload.company_name,
        infer=payload.infer,
        overwrite=payload.overwrite,
        material_forms=list(payload.material_forms),
        verbose=payload.verbose,
        debug=payload.debug,
        info=payload.info,
        quiet=payload.quiet,
        log_level=payload.log_level,
    )
    prepare_cli_args(namespace)
    return namespace


def _build_upload_file_items(values: object) -> tuple[UploadFileResultItem, ...]:
    """把结果中的文件列表规范化为强类型条目。"""

    if not isinstance(values, list):
        return ()
    items: list[UploadFileResultItem] = []
    for value in values:
        normalized = str(value).strip()
        if normalized:
            items.append(UploadFileResultItem(path=normalized))
    return tuple(items)


def _build_download_failed_files(values: object) -> tuple[DownloadFailedFile, ...]:
    """规范化失败下载文件列表。"""

    if not isinstance(values, list):
        return ()
    items: list[DownloadFailedFile] = []
    for value in values:
        if isinstance(value, dict):
            items.append(
                DownloadFailedFile(
                    file_name=_optional_text(value.get("name")) or _optional_text(value.get("file_name")),
                    source=_optional_text(value.get("source")),
                    reason_code=_optional_text(value.get("reason_code")),
                    reason_message=(
                        _optional_text(value.get("reason_message"))
                        or _optional_text(value.get("message"))
                        or _optional_text(value.get("error"))
                    ),
                )
            )
            continue
        normalized = str(value).strip()
        if normalized:
            items.append(DownloadFailedFile(file_name=normalized))
    return tuple(items)


def _optional_text(value: object) -> str | None:
    """提取可选字符串。"""

    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _require_download_payload(payload: FinsCommandPayload) -> DownloadCommandPayload:
    """收窄 download 命令载荷类型。

    Args:
        payload: 宽命令载荷。

    Returns:
        ``DownloadCommandPayload`` 强类型载荷。

    Raises:
        TypeError: 当载荷类型与 ``download`` 命令不匹配时抛出。
    """

    if not isinstance(payload, DownloadCommandPayload):
        raise TypeError("download 命令必须使用 DownloadCommandPayload")
    return payload


def _require_upload_filing_payload(payload: FinsCommandPayload) -> UploadFilingCommandPayload:
    """收窄 upload_filing 命令载荷类型。

    Args:
        payload: 宽命令载荷。

    Returns:
        ``UploadFilingCommandPayload`` 强类型载荷。

    Raises:
        TypeError: 当载荷类型与 ``upload_filing`` 命令不匹配时抛出。
    """

    if not isinstance(payload, UploadFilingCommandPayload):
        raise TypeError("upload_filing 命令必须使用 UploadFilingCommandPayload")
    return payload


def _require_upload_filings_from_payload(payload: FinsCommandPayload) -> UploadFilingsFromCommandPayload:
    """收窄 upload_filings_from 命令载荷类型。

    Args:
        payload: 宽命令载荷。

    Returns:
        ``UploadFilingsFromCommandPayload`` 强类型载荷。

    Raises:
        TypeError: 当载荷类型与 ``upload_filings_from`` 命令不匹配时抛出。
    """

    if not isinstance(payload, UploadFilingsFromCommandPayload):
        raise TypeError("upload_filings_from 命令必须使用 UploadFilingsFromCommandPayload")
    return payload


def _require_upload_material_payload(payload: FinsCommandPayload) -> UploadMaterialCommandPayload:
    """收窄 upload_material 命令载荷类型。

    Args:
        payload: 宽命令载荷。

    Returns:
        ``UploadMaterialCommandPayload`` 强类型载荷。

    Raises:
        TypeError: 当载荷类型与 ``upload_material`` 命令不匹配时抛出。
    """

    if not isinstance(payload, UploadMaterialCommandPayload):
        raise TypeError("upload_material 命令必须使用 UploadMaterialCommandPayload")
    return payload


def _require_process_payload(payload: FinsCommandPayload) -> ProcessCommandPayload:
    """收窄 process 命令载荷类型。

    Args:
        payload: 宽命令载荷。

    Returns:
        ``ProcessCommandPayload`` 强类型载荷。

    Raises:
        TypeError: 当载荷类型与 ``process`` 命令不匹配时抛出。
    """

    if not isinstance(payload, ProcessCommandPayload):
        raise TypeError("process 命令必须使用 ProcessCommandPayload")
    return payload


def _require_process_filing_payload(payload: FinsCommandPayload) -> ProcessFilingCommandPayload:
    """收窄 process_filing 命令载荷类型。

    Args:
        payload: 宽命令载荷。

    Returns:
        ``ProcessFilingCommandPayload`` 强类型载荷。

    Raises:
        TypeError: 当载荷类型与 ``process_filing`` 命令不匹配时抛出。
    """

    if not isinstance(payload, ProcessFilingCommandPayload):
        raise TypeError("process_filing 命令必须使用 ProcessFilingCommandPayload")
    return payload


def _require_process_material_payload(payload: FinsCommandPayload) -> ProcessMaterialCommandPayload:
    """收窄 process_material 命令载荷类型。

    Args:
        payload: 宽命令载荷。

    Returns:
        ``ProcessMaterialCommandPayload`` 强类型载荷。

    Raises:
        TypeError: 当载荷类型与 ``process_material`` 命令不匹配时抛出。
    """

    if not isinstance(payload, ProcessMaterialCommandPayload):
        raise TypeError("process_material 命令必须使用 ProcessMaterialCommandPayload")
    return payload


def _require_download_event(
    event: DownloadEvent | ProcessEvent | UploadFilingEvent | UploadMaterialEvent,
) -> DownloadEvent:
    """收窄 download 流事件类型。

    Args:
        event: 宽事件对象。

    Returns:
        ``DownloadEvent`` 强类型事件。

    Raises:
        TypeError: 当事件类型与 ``download`` 流不匹配时抛出。
    """

    if not isinstance(event, DownloadEvent):
        raise TypeError("download 事件流必须产出 DownloadEvent")
    return event


def _require_process_event(
    event: DownloadEvent | ProcessEvent | UploadFilingEvent | UploadMaterialEvent,
) -> ProcessEvent:
    """收窄 process 流事件类型。

    Args:
        event: 宽事件对象。

    Returns:
        ``ProcessEvent`` 强类型事件。

    Raises:
        TypeError: 当事件类型与 ``process`` 流不匹配时抛出。
    """

    if not isinstance(event, ProcessEvent):
        raise TypeError("process 事件流必须产出 ProcessEvent")
    return event


def _require_upload_filing_event(
    event: DownloadEvent | ProcessEvent | UploadFilingEvent | UploadMaterialEvent,
) -> UploadFilingEvent:
    """收窄 upload_filing 流事件类型。

    Args:
        event: 宽事件对象。

    Returns:
        ``UploadFilingEvent`` 强类型事件。

    Raises:
        TypeError: 当事件类型与 ``upload_filing`` 流不匹配时抛出。
    """

    if not isinstance(event, UploadFilingEvent):
        raise TypeError("upload_filing 事件流必须产出 UploadFilingEvent")
    return event


def _require_upload_material_event(
    event: DownloadEvent | ProcessEvent | UploadFilingEvent | UploadMaterialEvent,
) -> UploadMaterialEvent:
    """收窄 upload_material 流事件类型。

    Args:
        event: 宽事件对象。

    Returns:
        ``UploadMaterialEvent`` 强类型事件。

    Raises:
        TypeError: 当事件类型与 ``upload_material`` 流不匹配时抛出。
    """

    if not isinstance(event, UploadMaterialEvent):
        raise TypeError("upload_material 事件流必须产出 UploadMaterialEvent")
    return event


def _build_download_filing_result_item(payload: dict[str, Any]) -> DownloadFilingResultItem:
    """构建单个 filing 下载结果。"""

    return DownloadFilingResultItem(
        document_id=str(payload.get("document_id", "")).strip(),
        status=DownloadFilingResultStatus.from_raw(str(payload.get("status", ""))),
        form_type=_optional_text(payload.get("form_type")),
        filing_date=_optional_text(payload.get("filing_date")),
        report_date=_optional_text(payload.get("report_date")),
        downloaded_files=int_or_zero(payload.get("downloaded_files")),
        skipped_files=int_or_zero(payload.get("skipped_files")),
        failed_files=_build_download_failed_files(payload.get("failed_files")),
        has_xbrl=payload.get("has_xbrl") if isinstance(payload.get("has_xbrl"), bool) else None,
        reason_code=(
            _optional_text(payload.get("reason_code"))
            or _optional_text(payload.get("skip_reason"))
            or _optional_text(payload.get("reason"))
        ),
        reason_message=(
            _optional_text(payload.get("reason_message"))
            or _optional_text(payload.get("message"))
            or _optional_text(payload.get("error"))
        ),
        skip_reason=_optional_text(payload.get("skip_reason")),
        filter_category=_optional_text(payload.get("filter_category")),
    )


def _build_download_result_data(result: dict[str, Any]) -> DownloadResultData:
    """把 pipeline download 结果规范化为公共契约。"""

    company_info_payload = result.get("company_info")
    company_info = DownloadCompanyInfo()
    if isinstance(company_info_payload, dict):
        company_info = DownloadCompanyInfo(
            company_id=_optional_text(company_info_payload.get("company_id")),
            company_name=_optional_text(company_info_payload.get("company_name")),
            market=_optional_text(company_info_payload.get("market")),
        )
    filters_payload = result.get("filters")
    filters = DownloadFilters()
    if isinstance(filters_payload, dict):
        forms_raw = filters_payload.get("forms")
        start_dates_raw = filters_payload.get("start_dates")
        start_dates: list[DownloadFilterWindow] = []
        if isinstance(start_dates_raw, dict):
            for form_type, start_date in sorted(start_dates_raw.items()):
                normalized_form = str(form_type).strip()
                normalized_start = str(start_date).strip()
                if normalized_form and normalized_start:
                    start_dates.append(DownloadFilterWindow(form_type=normalized_form, start_date=normalized_start))
        filters = DownloadFilters(
            forms=(
                tuple(str(item).strip() for item in forms_raw if str(item).strip())
                if isinstance(forms_raw, list)
                else ()
            ),
            start_dates=tuple(start_dates),
            end_date=_optional_text(filters_payload.get("end_date")),
            overwrite=bool(filters_payload.get("overwrite", False)),
        )
    warnings_raw = result.get("warnings")
    filings_raw = result.get("filings")
    summary_raw = result.get("summary")
    filings = tuple(
        _build_download_filing_result_item(item)
        for item in filings_raw
        if isinstance(item, dict)
    ) if isinstance(filings_raw, list) else ()
    summary = DownloadSummary(0, 0, 0, 0, 0, 0, 0)
    if isinstance(summary_raw, dict):
        summary = DownloadSummary(
            total=int_or_zero(summary_raw.get("total")),
            downloaded=int_or_zero(summary_raw.get("downloaded")),
            skipped=int_or_zero(summary_raw.get("skipped")),
            failed=int_or_zero(summary_raw.get("failed")),
            elapsed_ms=int_or_zero(summary_raw.get("elapsed_ms")),
            reused_downloads=int_or_zero(summary_raw.get("reused_downloads")),
            converted=int_or_zero(summary_raw.get("converted")),
        )
    return DownloadResultData(
        pipeline=str(result.get("pipeline", "")).strip(),
        status=str(result.get("status", "")).strip(),
        ticker=str(result.get("ticker", "")).strip(),
        company_info=company_info,
        filters=filters,
        warnings=(
            tuple(str(item).strip() for item in warnings_raw if str(item).strip())
            if isinstance(warnings_raw, list)
            else ()
        ),
        filings=filings,
        summary=summary,
    )


def _build_upload_filing_result_data(result: dict[str, Any]) -> UploadFilingResultData:
    """把 upload_filing 结果规范化为公共契约。"""

    return UploadFilingResultData(
        pipeline=str(result.get("pipeline", "")).strip(),
        status=str(result.get("status", "")).strip(),
        ticker=str(result.get("ticker", "")).strip(),
        filing_action=str(result.get("filing_action", "")).strip(),
        files=_build_upload_file_items(result.get("files")),
        form_type=_optional_text(result.get("form_type")),
        fiscal_year=optional_int(result.get("fiscal_year")),
        fiscal_period=_optional_text(result.get("fiscal_period")),
        amended=result.get("amended") if isinstance(result.get("amended"), bool) else None,
        company_id=_optional_text(result.get("company_id")),
        company_name=_optional_text(result.get("company_name")),
        document_id=_optional_text(result.get("document_id")),
        primary_document=_optional_text(result.get("primary_document")),
        uploaded_files=optional_int(result.get("uploaded_files")),
        document_version=_optional_text(result.get("document_version")),
        source_fingerprint=_optional_text(result.get("source_fingerprint")),
        filing_date=_optional_text(result.get("filing_date")),
        report_date=_optional_text(result.get("report_date")),
        overwrite=result.get("overwrite") if isinstance(result.get("overwrite"), bool) else None,
        skip_reason=_optional_text(result.get("skip_reason")),
        message=_optional_text(result.get("message")),
    )


def _build_upload_material_result_data(result: dict[str, Any]) -> UploadMaterialResultData:
    """把 upload_material 结果规范化为公共契约。"""

    return UploadMaterialResultData(
        pipeline=str(result.get("pipeline", "")).strip(),
        status=str(result.get("status", "")).strip(),
        ticker=str(result.get("ticker", "")).strip(),
        material_action=str(result.get("material_action", "")).strip(),
        files=_build_upload_file_items(result.get("files")),
        form_type=_optional_text(result.get("form_type")),
        material_name=_optional_text(result.get("material_name")),
        fiscal_year=optional_int(result.get("fiscal_year")),
        fiscal_period=_optional_text(result.get("fiscal_period")),
        company_id=_optional_text(result.get("company_id")),
        company_name=_optional_text(result.get("company_name")),
        document_id=_optional_text(result.get("document_id")),
        internal_document_id=_optional_text(result.get("internal_document_id")),
        primary_document=_optional_text(result.get("primary_document")),
        uploaded_files=optional_int(result.get("uploaded_files")),
        document_version=_optional_text(result.get("document_version")),
        source_fingerprint=_optional_text(result.get("source_fingerprint")),
        filing_date=_optional_text(result.get("filing_date")),
        report_date=_optional_text(result.get("report_date")),
        overwrite=result.get("overwrite") if isinstance(result.get("overwrite"), bool) else None,
        skip_reason=_optional_text(result.get("skip_reason")),
        message=_optional_text(result.get("message")),
    )


def _build_upload_filings_from_result_data(result: dict[str, Any]) -> UploadFilingsFromResultData:
    """把 upload_filings_from 结果规范化为公共契约。"""

    recognized_raw = result.get("recognized")
    material_raw = result.get("material")
    skipped_raw = result.get("skipped")
    recognized = tuple(
        UploadFilingsFromRecognizedItem(
            file=str(item.get("file", "")).strip(),
            fiscal_year=optional_int(item.get("fiscal_year")),
            fiscal_period=_optional_text(item.get("fiscal_period")),
        )
        for item in recognized_raw
        if isinstance(item, dict)
    ) if isinstance(recognized_raw, list) else ()
    material = tuple(
        UploadFilingsFromMaterialItem(
            file=str(item.get("file", "")).strip(),
            material_name=_optional_text(item.get("material_name")),
        )
        for item in material_raw
        if isinstance(item, dict)
    ) if isinstance(material_raw, list) else ()
    skipped = tuple(
        UploadFilingsFromSkippedItem(
            file=str(item.get("file", "")).strip(),
            reason=_optional_text(item.get("reason")),
        )
        for item in skipped_raw
        if isinstance(item, dict)
    ) if isinstance(skipped_raw, list) else ()
    return UploadFilingsFromResultData(
        script_path=str(result.get("script_path", "")).strip(),
        script_platform=str(result.get("script_platform", "")).strip(),
        ticker=str(result.get("ticker", "")).strip(),
        source_dir=str(result.get("source_dir", "")).strip(),
        total_files=int_or_zero(result.get("total_files")),
        recognized_count=int_or_zero(result.get("recognized_count")),
        material_count=int_or_zero(result.get("material_count")),
        skipped_count=int_or_zero(result.get("skipped_count")),
        recognized=recognized,
        material=material,
        skipped=skipped,
    )


def _build_process_summary(payload: object) -> ProcessSummary:
    """构建 process 汇总。"""

    if not isinstance(payload, dict):
        return ProcessSummary(0, 0, 0, 0, False)
    return ProcessSummary(
        total=int_or_zero(payload.get("total")),
        processed=int_or_zero(payload.get("processed")),
        skipped=int_or_zero(payload.get("skipped")),
        failed=int_or_zero(payload.get("failed")),
        todo=bool(payload.get("todo", False)),
    )


def _build_process_document_result_item(payload: dict[str, Any]) -> ProcessDocumentResultItem:
    """构建单个 process 文档结果。"""

    return ProcessDocumentResultItem(
        document_id=str(payload.get("document_id", "")).strip(),
        status=str(payload.get("status", "")).strip(),
        reason=_optional_text(payload.get("reason")),
        form_type=_optional_text(payload.get("form_type")),
        fiscal_year=optional_int(payload.get("fiscal_year")),
        quality=_optional_text(payload.get("quality")),
        has_xbrl=payload.get("has_xbrl") if isinstance(payload.get("has_xbrl"), bool) else None,
        section_count=optional_int(payload.get("section_count")),
        table_count=optional_int(payload.get("table_count")),
        skip_reason=_optional_text(payload.get("skip_reason")),
        source_kind=_optional_text(payload.get("source_kind")),
    )


def _build_process_result_data(result: dict[str, Any]) -> ProcessResultData:
    """把 process 结果规范化为公共契约。"""

    filings_raw = result.get("filings")
    materials_raw = result.get("materials")
    filings = tuple(
        _build_process_document_result_item(item)
        for item in filings_raw
        if isinstance(item, dict)
    ) if isinstance(filings_raw, list) else ()
    materials = tuple(
        _build_process_document_result_item(item)
        for item in materials_raw
        if isinstance(item, dict)
    ) if isinstance(materials_raw, list) else ()
    return ProcessResultData(
        pipeline=str(result.get("pipeline", "")).strip(),
        status=str(result.get("status", "")).strip(),
        ticker=str(result.get("ticker", "")).strip(),
        overwrite=bool(result.get("overwrite", False)),
        ci=bool(result.get("ci", False)),
        filings=filings,
        filing_summary=_build_process_summary(result.get("filing_summary")),
        materials=materials,
        material_summary=_build_process_summary(result.get("material_summary")),
    )


def _build_process_single_result_data(result: dict[str, Any]) -> ProcessSingleResultData:
    """把 process_filing/process_material 结果规范化为公共契约。"""

    return ProcessSingleResultData(
        pipeline=str(result.get("pipeline", "")).strip(),
        action=str(result.get("action", "")).strip(),
        status=str(result.get("status", "")).strip(),
        ticker=str(result.get("ticker", "")).strip(),
        document_id=str(result.get("document_id", "")).strip(),
        overwrite=bool(result.get("overwrite", False)),
        ci=bool(result.get("ci", False)),
        reason=_optional_text(result.get("reason")),
        form_type=_optional_text(result.get("form_type")),
        fiscal_year=optional_int(result.get("fiscal_year")),
        quality=_optional_text(result.get("quality")),
        has_xbrl=result.get("has_xbrl") if isinstance(result.get("has_xbrl"), bool) else None,
        section_count=optional_int(result.get("section_count")),
        table_count=optional_int(result.get("table_count")),
        skip_reason=_optional_text(result.get("skip_reason")),
        message=_optional_text(result.get("message")),
    )


def _build_result_data(command_name: FinsCommandName, result: dict[str, Any]) -> FinsResultData:
    """按命令名把结果字典规范化为强类型结果。"""

    if command_name == FinsCommandName.DOWNLOAD:
        return _build_download_result_data(result)
    if command_name == FinsCommandName.UPLOAD_FILING:
        return _build_upload_filing_result_data(result)
    if command_name == FinsCommandName.UPLOAD_FILINGS_FROM:
        return _build_upload_filings_from_result_data(result)
    if command_name == FinsCommandName.UPLOAD_MATERIAL:
        return _build_upload_material_result_data(result)
    if command_name == FinsCommandName.PROCESS:
        return _build_process_result_data(result)
    return _build_process_single_result_data(result)


def _extract_result_data_from_event(
    *,
    command_name: FinsCommandName,
    event_payload: dict[str, Any],
) -> FinsResultData | None:
    """从内部 pipeline 事件中提取最终强类型结果。"""

    result = event_payload.get("result")
    if not isinstance(result, dict):
        return None
    return _build_result_data(command_name, result)


def _build_download_progress_payload(event: DownloadEvent) -> DownloadProgressPayload:
    """把下载 pipeline 事件映射为跨层 progress 负载。"""

    payload = event.payload if isinstance(event.payload, dict) else {}
    filing_result_payload = payload.get("filing_result")
    return DownloadProgressPayload(
        event_type=FinsProgressEventName(str(event.event_type)),
        ticker=event.ticker,
        document_id=event.document_id,
        action=_optional_text(payload.get("action")),
        name=_optional_text(payload.get("name")),
        form_type=_optional_text(payload.get("form_type")),
        file_count=optional_int(payload.get("file_count")),
        size=optional_int(payload.get("size")),
        message=_optional_text(payload.get("message")),
        reason=_optional_text(payload.get("reason")) or _optional_text(payload.get("skip_reason")),
        filing_result=(
            _build_download_filing_result_item(filing_result_payload)
            if isinstance(filing_result_payload, dict)
            else None
        ),
    )


def _build_process_progress_payload(event: ProcessEvent) -> ProcessProgressPayload:
    """把 process pipeline 事件映射为跨层 progress 负载。"""

    payload = event.payload if isinstance(event.payload, dict) else {}
    summary_payload = payload.get("result_summary")
    return ProcessProgressPayload(
        event_type=FinsProgressEventName(str(event.event_type)),
        ticker=event.ticker,
        document_id=event.document_id,
        source_kind=_optional_text(payload.get("source_kind")),
        total_documents=optional_int(payload.get("total_documents")),
        overwrite=payload.get("overwrite") if isinstance(payload.get("overwrite"), bool) else None,
        ci=payload.get("ci") if isinstance(payload.get("ci"), bool) else None,
        reason=_optional_text(payload.get("reason")),
        result_summary=(
            _build_process_document_result_item(summary_payload)
            if isinstance(summary_payload, dict)
            else None
        ),
    )


def _build_upload_filing_progress_payload(event: UploadFilingEvent) -> UploadFilingProgressPayload:
    """把上传财报事件映射为跨层 progress 负载。"""

    payload = event.payload if isinstance(event.payload, dict) else {}
    return UploadFilingProgressPayload(
        event_type=FinsProgressEventName(str(event.event_type)),
        ticker=event.ticker,
        document_id=event.document_id,
        action=_optional_text(payload.get("action")),
        name=_optional_text(payload.get("name")),
        file_count=optional_int(payload.get("file_count")),
        size=optional_int(payload.get("size")),
        message=_optional_text(payload.get("message")),
        error=_optional_text(payload.get("error")),
    )


def _build_upload_material_progress_payload(event: UploadMaterialEvent) -> UploadMaterialProgressPayload:
    """把上传材料事件映射为跨层 progress 负载。"""

    payload = event.payload if isinstance(event.payload, dict) else {}
    return UploadMaterialProgressPayload(
        event_type=FinsProgressEventName(str(event.event_type)),
        ticker=event.ticker,
        document_id=event.document_id,
        action=_optional_text(payload.get("action")),
        name=_optional_text(payload.get("name")),
        file_count=optional_int(payload.get("file_count")),
        size=optional_int(payload.get("size")),
        message=_optional_text(payload.get("message")),
        error=_optional_text(payload.get("error")),
    )


@dataclass
class DefaultFinsRuntime(FinsRuntimeProtocol):
    """默认 Fins 运行时实现。"""

    workspace_root: Path
    company_repository: CompanyMetaRepositoryProtocol
    source_repository: SourceDocumentRepositoryProtocol
    processed_repository: ProcessedDocumentRepositoryProtocol
    blob_repository: DocumentBlobRepositoryProtocol
    filing_maintenance_repository: FilingMaintenanceRepositoryProtocol
    processor_registry: ProcessorRegistry
    cn_download_pdf_gate: CnDownloadPdfGateProtocol = field(
        default_factory=NoopCnDownloadPdfGate
    )
    batching_repository: BatchingRepositoryProtocol = field(
        default_factory=_default_batching_repository_factory
    )
    _preparation_gate: CnPreparationGate = field(
        default_factory=CnPreparationGate,
        repr=False,
        compare=False,
    )
    _tool_service: Optional[FinsToolService] = field(init=False, default=None, repr=False)
    _tool_service_lock: Lock = field(init=False, repr=False)
    _source_sync_runtime: DefaultFinsWorkerSourceSyncRuntime = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        """初始化内部状态。"""

        # 复杂逻辑说明：_tool_service 使用懒创建 + 锁保证线程安全，
        # 所有 scene agent 共享同一个 FinsToolService 实例及其 processor cache。
        self._tool_service_lock = Lock()
        self._source_sync_runtime = DefaultFinsWorkerSourceSyncRuntime(
            pipeline_factory=self,
            source_repository=self.source_repository,
            evidence_locator_owner=self,
        )

    def _build_pipeline_for_ticker(self, ticker: str) -> PipelineProtocol:
        """按 ticker 构建 direct operation 所需 pipeline。"""

        return _build_pipeline(
            ticker=ticker,
            workspace_root=self.workspace_root,
            company_repository=self.company_repository,
            source_repository=self.source_repository,
            processed_repository=self.processed_repository,
            blob_repository=self.blob_repository,
            filing_maintenance_repository=self.filing_maintenance_repository,
            processor_registry=self.processor_registry,
            cn_download_pdf_gate=self.cn_download_pdf_gate,
            batching_repository=self.batching_repository,
            preparation_gate=self._preparation_gate,
        )

    def build_source_sync_pipeline(self, ticker: str) -> FinsSourceSyncDownloadPipelineProtocol:
        """Delegate source-sync pipeline construction to the existing factory."""

        return self._build_pipeline_for_ticker(ticker)

    async def sync_worker_source(
        self,
        request: FinsWorkerSyncRequest,
        *,
        cancel_checker: Callable[[], bool],
    ) -> FinsWorkerSyncResult:
        """Admit and delegate one worker source synchronization."""

        if type(request) is not FinsWorkerSyncRequest:
            raise TypeError("request must be FinsWorkerSyncRequest")
        return await self._source_sync_runtime.sync_worker_source(
            request,
            cancel_checker=cancel_checker,
        )

    @classmethod
    def create(
        cls,
        *,
        workspace_root: Path,
        repository_set: _FsRepositorySet | None = None,
        cn_download_pdf_gate: CnDownloadPdfGateProtocol | None = None,
    ) -> "DefaultFinsRuntime":
        """创建默认 Fins 运行时。

        只接受可选 ``repository_set``，不接受 ``file_store`` 参数（S14-CTRL-05）。
        非 ``None`` 时直接复用该 set 构造 5 个窄仓储与唯一
        ``FsBatchingRepository``（同一 core、同一 ``_active_batches`` token
        空间）；为 ``None`` 时精确保留当前 FS 行为（内部
        ``build_fs_repository_set(workspace_root=...)``）。``create`` 内部不再
        重复触发 batch recovery。

        Args:
            workspace_root: 工作区根目录。
            repository_set: 可选共享仓储 core 集合。
            cn_download_pdf_gate: 可选 CN/HK PDF 下载段 gate。

        Returns:
            默认 Fins 运行时。

        Raises:
            无。
        """

        if repository_set is None:
            repository_set = build_fs_repository_set(workspace_root=workspace_root)
        runtime = cls(
            workspace_root=workspace_root,
            company_repository=FsCompanyMetaRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            source_repository=FsSourceDocumentRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            processed_repository=FsProcessedDocumentRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            blob_repository=FsDocumentBlobRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            filing_maintenance_repository=FsFilingMaintenanceRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            processor_registry=build_fins_processor_registry(),
            cn_download_pdf_gate=cn_download_pdf_gate or NoopCnDownloadPdfGate(),
            batching_repository=FsBatchingRepository(
                workspace_root,
                repository_set=repository_set,
            ),
            _preparation_gate=CnPreparationGate(),
        )
        return runtime

    def get_processor_registry(self) -> ProcessorRegistry:
        """返回处理器注册表。"""

        return self.processor_registry

    def get_tool_service(self, *, processor_cache_max_entries: int = 128) -> FinsToolService:
        """返回共享的 FinsToolService 实例。

        首次调用时按指定参数创建并缓存，后续调用返回已有实例。
        同一进程内所有 scene agent 共享同一个实例及其 processor cache。

        Args:
            processor_cache_max_entries: Processor 缓存最大条目数（仅首次创建时生效）。

        Returns:
            共享的 FinsToolService 实例。

        Raises:
            无。
        """

        if self._tool_service is not None:
            return self._tool_service
        with self._tool_service_lock:
            if self._tool_service is not None:
                return self._tool_service
            service = FinsToolService(
                company_repository=self.company_repository,
                source_repository=self.source_repository,
                processed_repository=self.processed_repository,
                processor_registry=self.processor_registry,
                processor_cache_max_entries=processor_cache_max_entries,
            )
            self._tool_service = service
            return service

    def _build_request_scoped_tool_service(self) -> FinsToolService:
        """构建 request-scoped FinsToolService。

        每次 evidence 读取都必须使用同一 repositories/registry 新建实例，
        绝不复用 ``get_tool_service()`` 的共享 cache，避免跨请求 processor
        污染。

        Args:
            无。

        Returns:
            空的 request-scoped FinsToolService。

        Raises:
            无。
        """

        return FinsToolService(
            company_repository=self.company_repository,
            source_repository=self.source_repository,
            processed_repository=self.processed_repository,
            processor_registry=self.processor_registry,
            processor_cache_max_entries=_EVIDENCE_TOOL_CACHE_MAX_ENTRIES,
        )

    def _read_processed_identity_state(
        self,
        *,
        ticker: str,
        document_id: str,
    ) -> _ProcessedIdentityState:
        """读取 processed meta 的 identity 状态快照。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            processed identity 状态；不存在时 ``exists=False``。

        Raises:
            无。
        """

        try:
            meta = self.processed_repository.get_processed_meta(ticker, document_id)
        except FileNotFoundError:
            return _ProcessedIdentityState(
                exists=False,
                is_deleted=False,
                reprocess_required=False,
                source_kind=None,
                source_document_version=None,
                source_fingerprint=None,
            )
        return _ProcessedIdentityState(
            exists=True,
            is_deleted=bool(meta.get("is_deleted", False)),
            reprocess_required=bool(meta.get("reprocess_required", False)),
            source_kind=_as_optional_text(meta.get("source_kind")),
            source_document_version=_as_optional_text(meta.get("source_document_version")),
            source_fingerprint=_as_optional_text(meta.get("source_fingerprint")),
        )

    def _counterpart_source_visible(
        self,
        *,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> bool:
        """探测相反 source kind 是否仍可被工具发现。

        现有 ``FinsToolService`` 的 source kind 解析只检查 counterpart
        ``get_source_handle()`` 是否存在（meta 文件存在即视为可发现），不区分
        逻辑删除状态。因此只要 counterpart 的 handle/source meta 对工具仍可
        发现（包括 ``is_deleted=true``），就视为歧义，避免 filing-first
        fallback 把错误 source kind 的 processed bytes 归属给请求 locator。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 请求的来源类型。

        Returns:
            相反 source kind 可被工具发现时返回 ``True``。

        Raises:
            无。
        """

        counterpart = SourceKind.MATERIAL if source_kind is SourceKind.FILING else SourceKind.FILING
        try:
            self.source_repository.get_source_handle(ticker, document_id, counterpart)
        except FileNotFoundError:
            return False
        return True

    def _preflight_source_identity(
        self,
        *,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        artifact_kind: ArtifactKind,
    ) -> _SourceIdentityState:
        """执行 exact/counterpart source 与 processed identity preflight。

        以 ``ticker + document_id + exact source_kind`` 读取 source meta；
        不存在、逻辑删除、未完成摄入、非法版本/指纹、双 source kind 碰撞或
        processed closure 不满足时一律 fail closed，绝不 fallback 纠正 caller。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 请求的来源类型。
            artifact_kind: 请求的产物类型。

        Returns:
            identity preflight 快照。

        Raises:
            EvidenceLocatorError: 任一 identity 约束不满足时抛出。
        """

        try:
            source_meta = self.source_repository.get_source_meta(ticker, document_id, source_kind)
        except FileNotFoundError as exc:
            raise EvidenceLocatorError(
                "source_identity_not_found",
                f"source 不存在: ticker={ticker}, document_id={document_id}, kind={source_kind.value}",
            ) from exc
        if bool(source_meta.get("is_deleted", False)):
            raise EvidenceLocatorError(
                "source_deleted",
                f"source 已逻辑删除: ticker={ticker}, document_id={document_id}, kind={source_kind.value}",
            )
        if not bool(source_meta.get("ingest_complete", True)):
            raise EvidenceLocatorError(
                "source_not_ingested",
                f"source 未完成摄入: ticker={ticker}, document_id={document_id}",
            )
        document_version = _require_meta_text(
            source_meta,
            "document_version",
            error_code="invalid_document_version",
            message=f"source 缺少合法 document_version: ticker={ticker}, document_id={document_id}",
        )
        source_fingerprint = _require_meta_fingerprint(
            source_meta,
            error_code="invalid_source_fingerprint",
            message=f"source 缺少合法 source_fingerprint: ticker={ticker}, document_id={document_id}",
        )
        counterpart_visible = self._counterpart_source_visible(
            ticker=ticker,
            document_id=document_id,
            source_kind=source_kind,
        )
        if counterpart_visible:
            raise EvidenceLocatorError(
                "ambiguous_source_identity",
                f"ticker={ticker}, document_id={document_id} 同时存在 filing 与 material",
            )
        processed: _ProcessedIdentityState | None = None
        if artifact_kind is ArtifactKind.PROCESSED:
            processed = self._read_processed_identity_state(ticker=ticker, document_id=document_id)
            if not processed.exists:
                raise EvidenceLocatorError(
                    "processed_not_found",
                    f"processed 不存在: ticker={ticker}, document_id={document_id}",
                )
            if processed.is_deleted:
                raise EvidenceLocatorError(
                    "processed_deleted",
                    f"processed 已逻辑删除: ticker={ticker}, document_id={document_id}",
                )
            if processed.reprocess_required:
                raise EvidenceLocatorError(
                    "processed_reprocess_required",
                    f"processed 需要重新处理: ticker={ticker}, document_id={document_id}",
                )
            if processed.source_kind != source_kind.value:
                raise EvidenceLocatorError(
                    "processed_source_kind_mismatch",
                    f"processed source_kind 与请求不一致: ticker={ticker}, document_id={document_id}",
                )
            if processed.source_document_version != document_version:
                raise EvidenceLocatorError(
                    "processed_version_mismatch",
                    f"processed source_document_version 与 source 不一致: ticker={ticker}, document_id={document_id}",
                )
            if processed.source_fingerprint != source_fingerprint:
                raise EvidenceLocatorError(
                    "processed_fingerprint_mismatch",
                    f"processed source_fingerprint 与 source 不一致: ticker={ticker}, document_id={document_id}",
                )
        return _SourceIdentityState(
            ticker=ticker,
            document_id=document_id,
            source_kind=source_kind,
            artifact_kind=artifact_kind,
            document_version=document_version,
            source_fingerprint=source_fingerprint,
            counterpart_visible=counterpart_visible,
            processed=processed,
        )

    def _read_primary_source(
        self,
        *,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> _PrimarySource:
        """读取 source 主文件 exact bytes 并实算 SHA。

        source bytes 唯一来源是 ``get_primary_source(...).open()``；可选
        ``get_primary_file(...).sha256`` 若存在必须与实算值相等，不存在也
        不能跳过实算。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            主文件 bytes、实算 SHA 与 MIME 类型。

        Raises:
            EvidenceLocatorError: 主文件无法读取或 meta SHA 与实算值不一致时抛出。
        """

        source = self.source_repository.get_primary_source(ticker, document_id, source_kind)
        try:
            with source.open() as stream:
                content = stream.read()
            content_sha = sha256_hex(content)
            primary_file = self.source_repository.get_primary_file(ticker, document_id, source_kind)
        except OSError as exc:
            raise EvidenceLocatorError(
                "primary_read_failed",
                f"读取 source 主文件失败: ticker={ticker}, document_id={document_id}",
            ) from exc
        meta_sha = primary_file.sha256
        if meta_sha is not None and str(meta_sha).strip().lower() != content_sha:
            raise EvidenceLocatorError(
                "primary_sha_mismatch",
                f"source 主文件 meta SHA 与实算值不一致: ticker={ticker}, document_id={document_id}",
            )
        media_type = _as_optional_text(source.media_type) or "application/octet-stream"
        return _PrimarySource(
            content=content,
            sha256=content_sha,
            media_type=media_type,
        )

    def _postflight_identity(
        self,
        *,
        preflight: _SourceIdentityState,
        primary_sha256: str,
    ) -> None:
        """读取后重读 owner 状态并比较 preflight identity。

        每次 fragment 读取后再次读取 exact/counterpart source meta、processed
        meta 与 primary bytes 并与 preflight 快照逐字段比较；中途新增/删除/
        变更一律拒绝，避免 TOCTOU 发布混合 projection。

        Args:
            preflight: preflight 阶段保存的 identity 快照。
            primary_sha256: preflight 阶段实算的主文件 SHA-256。

        Returns:
            无。

        Raises:
            EvidenceLocatorError: owner 状态或主文件 bytes 在读取期间漂移时抛出。
        """

        try:
            current_meta = self.source_repository.get_source_meta(
                preflight.ticker,
                preflight.document_id,
                preflight.source_kind,
            )
        except FileNotFoundError as exc:
            raise EvidenceLocatorError(
                "source_identity_changed",
                f"source 在读取期间被删除: ticker={preflight.ticker}, document_id={preflight.document_id}",
            ) from exc
        current_version = _require_meta_text(
            current_meta,
            "document_version",
            error_code="source_identity_changed",
            message=f"source 版本在读取期间失效: ticker={preflight.ticker}, document_id={preflight.document_id}",
        )
        current_fingerprint = _require_meta_fingerprint(
            current_meta,
            error_code="source_identity_changed",
            message=f"source 指纹在读取期间失效: ticker={preflight.ticker}, document_id={preflight.document_id}",
        )
        current_counterpart = self._counterpart_source_visible(
            ticker=preflight.ticker,
            document_id=preflight.document_id,
            source_kind=preflight.source_kind,
        )
        if (
            current_version != preflight.document_version
            or current_fingerprint != preflight.source_fingerprint
            or current_counterpart != preflight.counterpart_visible
            or bool(current_meta.get("is_deleted", False))
            or not bool(current_meta.get("ingest_complete", True))
        ):
            raise EvidenceLocatorError(
                "source_identity_changed",
                f"source identity 在读取期间发生变更: ticker={preflight.ticker}, document_id={preflight.document_id}",
            )
        if preflight.artifact_kind is ArtifactKind.PROCESSED:
            current_processed = self._read_processed_identity_state(
                ticker=preflight.ticker,
                document_id=preflight.document_id,
            )
            if current_processed != preflight.processed:
                raise EvidenceLocatorError(
                    "source_identity_changed",
                    "processed identity 在读取期间发生变更: "
                    f"ticker={preflight.ticker}, document_id={preflight.document_id}",
                )
        primary = self._read_primary_source(
            ticker=preflight.ticker,
            document_id=preflight.document_id,
            source_kind=preflight.source_kind,
        )
        if primary.sha256 != primary_sha256:
            raise EvidenceLocatorError(
                "primary_content_changed",
                f"source 主文件在读取期间发生变更: ticker={preflight.ticker}, document_id={preflight.document_id}",
            )

    def _verify_evidence_identity(
        self,
        identity: _EvidenceIdentity,
    ) -> _VerifiedEvidence:
        """验证 identity 并读取 canonical fragment。

        依次执行 exact/counterpart preflight、identity 字段逐项比较、primary
        SHA 实算、request-scoped tool 读取与 postflight double-read；任何漂移
        均 fail closed。

        Args:
            identity: 证据定位器 identity 载体。

        Returns:
            已验证的 evidence 读取结果。

        Raises:
            EvidenceLocatorError: 任一验证步骤不满足时抛出。
        """

        preflight = self._preflight_source_identity(
            ticker=identity.ticker,
            document_id=identity.document_id,
            source_kind=identity.source_kind,
            artifact_kind=identity.artifact_kind,
        )
        if identity.document_version != preflight.document_version:
            raise EvidenceLocatorError(
                "document_version_mismatch",
                f"document_version 与当前 source 不一致: ticker={identity.ticker}, document_id={identity.document_id}",
            )
        if identity.source_fingerprint != preflight.source_fingerprint:
            raise EvidenceLocatorError(
                "source_fingerprint_mismatch",
                "source_fingerprint 与当前 source 不一致: "
                f"ticker={identity.ticker}, document_id={identity.document_id}",
            )
        primary = self._read_primary_source(
            ticker=identity.ticker,
            document_id=identity.document_id,
            source_kind=identity.source_kind,
        )
        if identity.primary_content_sha256 != primary.sha256:
            raise EvidenceLocatorError(
                "primary_content_sha256_mismatch",
                f"primary_content_sha256 与实算值不一致: ticker={identity.ticker}, document_id={identity.document_id}",
            )
        tool_service = self._build_request_scoped_tool_service()
        try:
            fragment_bytes = _resolve_fragment_bytes(
                tool_service,
                ticker=identity.ticker,
                document_id=identity.document_id,
                artifact_kind=identity.artifact_kind,
                locator_kind=identity.locator_kind,
                locator_payload=identity.locator_payload,
                primary_bytes=primary.content,
            )
        except EvidenceLocatorError:
            raise
        except Exception as exc:
            raise EvidenceLocatorError(
                "evidence_read_failed",
                f"读取 evidence fragment 失败: ticker={identity.ticker}, document_id={identity.document_id}",
            ) from exc
        if identity.locator_content_sha256 != sha256_hex(fragment_bytes):
            raise EvidenceLocatorError(
                "locator_content_sha256_mismatch",
                "locator_content_sha256 与实算 fragment 不一致: "
                f"ticker={identity.ticker}, document_id={identity.document_id}",
            )
        self._postflight_identity(
            preflight=preflight,
            primary_sha256=primary.sha256,
        )
        return _VerifiedEvidence(
            primary_sha256=primary.sha256,
            media_type=primary.media_type,
            fragment_bytes=fragment_bytes,
        )

    def _build_current_projection(
        self,
        *,
        identity: _EvidenceIdentity,
        primary_sha256: str,
        fragment_bytes: bytes,
    ) -> EvidenceLocatorProjection:
        """构建与当前 owner 状态一致的 projection。

        Args:
            identity: 已验证的 identity 载体。
            primary_sha256: 实算的 source 主文件 SHA-256。
            fragment_bytes: canonical fragment bytes。

        Returns:
            当前 projection（无路径字段）。

        Raises:
            无。
        """

        return EvidenceLocatorProjection(
            repository_id=REPOSITORY_ID,
            ticker=identity.ticker,
            document_id=identity.document_id,
            source_kind=identity.source_kind,
            artifact_kind=identity.artifact_kind,
            document_version=identity.document_version,
            source_fingerprint=identity.source_fingerprint,
            primary_content_sha256=primary_sha256,
            locator_kind=identity.locator_kind,
            locator_payload=identity.locator_payload,
            locator_content_sha256=sha256_hex(fragment_bytes),
        )

    def resolve_evidence_locator(self, request: EvidenceLocatorRequest) -> EvidenceLocatorProjection:
        """解析并验证证据定位器请求，返回当前 projection。

        Args:
            request: 证据定位器请求。

        Returns:
            与当前 owner 状态一致的证据定位器投影。

        Raises:
            EvidenceLocatorError: DTO invariant、source/processed identity closure、
                content hash、dual-kind 碰撞或读取中状态漂移不满足时抛出。
        """

        validate_evidence_locator_request(request)
        identity = _to_evidence_identity(request)
        verified = self._verify_evidence_identity(identity)
        return self._build_current_projection(
            identity=identity,
            primary_sha256=verified.primary_sha256,
            fragment_bytes=verified.fragment_bytes,
        )

    def validate_evidence_locator(self, locator: EvidenceLocatorProjection) -> None:
        """重算并逐字段验证持久化的证据定位器投影。

        Args:
            locator: 待验证的证据定位器投影。

        Returns:
            无。

        Raises:
            EvidenceLocatorError: DTO invariant 不满足，或投影任一 identity/content
                字段与当前 owner 状态不一致时抛出。
        """

        validate_evidence_locator_projection(locator)
        identity = _locator_to_evidence_identity(locator)
        self._verify_evidence_identity(identity)

    def read_citation_projection(self, locator: EvidenceLocatorProjection) -> CitationProjection:
        """验证定位器并读取 canonical citation 结果。

        Args:
            locator: 已验证的证据定位器投影。

        Returns:
            只读 citation 结果；``sha256(content_bytes)`` 必须等于
            ``locator.locator_content_sha256``。

        Raises:
            EvidenceLocatorError: DTO invariant 不满足、投影验证失败或读取中
                状态漂移时抛出。
        """

        validate_evidence_locator_projection(locator)
        identity = _locator_to_evidence_identity(locator)
        verified = self._verify_evidence_identity(identity)
        content_type = (
            verified.media_type
            if identity.artifact_kind is ArtifactKind.SOURCE
            else "application/json"
        )
        return CitationProjection(
            locator=locator,
            content_type=content_type,
            content_bytes=verified.fragment_bytes,
        )

    def build_ingestion_service_factory(self) -> IngestionServiceFactory:
        """构建按 ticker 路由的长事务服务工厂。"""

        return build_ingestion_service_factory(
            workspace_root=self.workspace_root,
            company_repository=self.company_repository,
            source_repository=self.source_repository,
            processed_repository=self.processed_repository,
            blob_repository=self.blob_repository,
            filing_maintenance_repository=self.filing_maintenance_repository,
            processor_registry=self.processor_registry,
            batching_repository=self.batching_repository,
            preparation_gate=self._preparation_gate,
        )

    def get_ingestion_manager_key(self) -> str:
        """返回长事务 job 管理器 key。"""

        return build_ingestion_manager_key(workspace_root=self.workspace_root)

    def list_source_filings(self, ticker: str) -> list[FilingSummary]:
        """列出指定股票的已下载财报源文件摘要。

        Args:
            ticker: 股票代码。

        Returns:
            财报源文件摘要列表。

        Raises:
            OSError: 列举源文档 ID 或读取单文档数据时底层存储异常。
            ValueError: 存储数据损坏或格式不合法时抛出。
        """

        result: list[FilingSummary] = []
        try:
            document_ids = self.source_repository.list_source_document_ids(ticker, SourceKind.FILING)
        except (OSError, ValueError):
            Log.error(
                f"列出财报源文档 ID 失败: ticker={ticker}",
                exc_info=True,
                module=_LOG_MODULE,
            )
            raise

        skipped_document_count = 0
        for doc_id in document_ids:
            try:
                meta = self.source_repository.get_source_meta(ticker, doc_id, SourceKind.FILING)
                fiscal_year_raw = meta.get("fiscal_year")
                primary_file_name: Optional[str] = None
                primary_file_path: Optional[str] = None
                try:
                    primary_source = self.source_repository.get_primary_source(
                        ticker, doc_id, SourceKind.FILING
                    )
                    materialized_path = primary_source.materialize().resolve()
                    primary_file_name = materialized_path.name or None
                    primary_file_path = str(materialized_path)
                except (OSError, ValueError):
                    Log.warning(
                        f"读取财报主文件失败，降级返回元信息: ticker={ticker}, document_id={doc_id}",
                        module=_LOG_MODULE,
                    )

                result.append(FilingSummary(
                    document_id=doc_id,
                    form_type=meta.get("form_type"),
                    filing_date=meta.get("filing_date"),
                    report_date=meta.get("report_date"),
                    fiscal_year=fiscal_year_raw if isinstance(fiscal_year_raw, int) else None,
                    fiscal_period=meta.get("fiscal_period"),
                    is_deleted=bool(meta.get("is_deleted", False)),
                    primary_file_name=primary_file_name,
                    primary_file_path=primary_file_path,
                ))
            except (OSError, ValueError):
                skipped_document_count += 1
                Log.warning(
                    f"读取单条财报元信息失败，已跳过: ticker={ticker}, document_id={doc_id}",
                    module=_LOG_MODULE,
                )
                continue

        if skipped_document_count > 0:
            Log.warning(
                "财报列表存在降级结果: "
                f"ticker={ticker}, total={len(document_ids)}, skipped={skipped_document_count}",
                module=_LOG_MODULE,
            )
        result.sort(key=lambda x: x.filing_date or "", reverse=True)
        return result

    def get_company_name(self, ticker: str) -> str:
        """返回公司名称。"""

        meta = _load_company_meta_best_effort(self.company_repository, ticker=ticker)
        if meta is None:
            return ""
        return str(getattr(meta, "company_name", "")).strip()

    def get_company_meta_summary(self, ticker: str) -> dict[str, str]:
        """返回公司基础 meta 摘要。

        Args:
            ticker: 股票代码。

        Returns:
            仅包含当前写作链路需要的基础 meta 字段。

        Raises:
            无。
        """

        meta = _load_company_meta_best_effort(self.company_repository, ticker=ticker)
        if meta is None:
            return {"ticker": ticker}
        return {
            "ticker": str(getattr(meta, "ticker", "") or ticker).strip(),
            "company_name": str(getattr(meta, "company_name", "") or "").strip(),
            "market": str(getattr(meta, "market", "") or "").strip(),
            "company_id": str(getattr(meta, "company_id", "") or "").strip(),
        }

    def validate_command(self, command: FinsCommand) -> None:
        """在创建 Host run 前同步校验命令是否可被受理。

        对每个命令执行参数规范化和业务规则校验，确保请求级错误在返回
        执行句柄前被同步拒绝。

        Args:
            command: 待校验的财报命令。

        Returns:
            无。

        Raises:
            ValueError: 命令参数非法或不支持流式执行时抛出。
        """

        # 流式兼容性检查：仅 download/process/upload_filing/upload_material 支持流式
        if command.stream and command.name not in {
            FinsCommandName.DOWNLOAD,
            FinsCommandName.PROCESS,
            FinsCommandName.UPLOAD_FILING,
            FinsCommandName.UPLOAD_MATERIAL,
        }:
            raise ValueError(f"不支持流式执行的命令: {command.name}")

        if command.name == FinsCommandName.DOWNLOAD:
            typed_payload = _require_download_payload(command.payload)
            self._prepare_download_execution(typed_payload)
            return
        if command.name == FinsCommandName.PROCESS:
            typed_payload = _require_process_payload(command.payload)
            self._prepare_process_execution(typed_payload)
            return
        if command.name == FinsCommandName.UPLOAD_FILING:
            typed_payload = _require_upload_filing_payload(command.payload)
            self._prepare_upload_filing_execution(typed_payload)
            return
        if command.name == FinsCommandName.UPLOAD_MATERIAL:
            typed_payload = _require_upload_material_payload(command.payload)
            self._prepare_upload_material_execution(typed_payload)
            return
        if command.name == FinsCommandName.UPLOAD_FILINGS_FROM:
            typed_payload = _require_upload_filings_from_payload(command.payload)
            prepared_args = _build_upload_filings_from_args(typed_payload, self.workspace_root)
            # namespace 构建仅做 ticker / CLI 规范化；source_dir 存在性在
            # generate_upload_filings_script 内才检查，必须在 preflight 提前卡住
            source_dir = Path(prepared_args.source_dir).expanduser().resolve()
            if not source_dir.exists() or not source_dir.is_dir():
                raise FileNotFoundError(f"source_dir 不存在或不是目录: {source_dir}")
            return
        if command.name == FinsCommandName.PROCESS_FILING:
            typed_payload = _require_process_filing_payload(command.payload)
            if not typed_payload.document_id.strip():
                raise ValueError("process_filing 的 document_id 不能为空")
            self._build_pipeline_for_ticker(typed_payload.ticker)
            return
        if command.name == FinsCommandName.PROCESS_MATERIAL:
            typed_payload = _require_process_material_payload(command.payload)
            if not typed_payload.document_id.strip():
                raise ValueError("process_material 的 document_id 不能为空")
            self._build_pipeline_for_ticker(typed_payload.ticker)
            return

    def _prepare_download_execution(
        self,
        payload: DownloadCommandPayload,
    ) -> tuple[_PreparedDownloadArgs, PipelineProtocol]:
        """准备 download 命令的已校验参数与 pipeline。"""

        prepared_args = _build_download_args(payload, self.workspace_root)
        pipeline = self._build_pipeline_for_ticker(prepared_args.ticker)
        return prepared_args, pipeline

    def _prepare_process_execution(
        self,
        payload: ProcessCommandPayload,
    ) -> tuple[_PreparedProcessArgs, PipelineProtocol]:
        """准备 process 命令的已校验参数与 pipeline。"""

        prepared_args = _build_process_args(payload, self.workspace_root)
        pipeline = self._build_pipeline_for_ticker(prepared_args.ticker)
        return prepared_args, pipeline

    def _prepare_upload_filing_execution(
        self,
        payload: UploadFilingCommandPayload,
    ) -> tuple[_PreparedUploadFilingArgs, PipelineProtocol]:
        """准备 upload_filing 命令的已校验参数与 pipeline。

        Args:
            payload: 上传财报命令载荷。

        Returns:
            校验通过的命名空间与 pipeline。

        Raises:
            ValueError: 参数非法时抛出。
        """

        prepared_args = _build_upload_filing_args(payload, self.workspace_root)
        pipeline = self._build_pipeline_for_ticker(prepared_args.ticker)
        return prepared_args, pipeline

    def _prepare_upload_material_execution(
        self,
        payload: UploadMaterialCommandPayload,
    ) -> tuple[_PreparedUploadMaterialArgs, PipelineProtocol]:
        """准备 upload_material 命令的已校验参数与 pipeline。

        Args:
            payload: 上传材料命令载荷。

        Returns:
            校验通过的命名空间与 pipeline。

        Raises:
            ValueError: 参数非法时抛出。
        """

        prepared_args = _build_upload_material_args(payload, self.workspace_root)
        pipeline = self._build_pipeline_for_ticker(prepared_args.ticker)
        return prepared_args, pipeline

    def execute(
        self,
        command: FinsCommand,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> FinsResult | AsyncIterator[FinsEvent]:
        """执行财报命令。"""

        if command.stream:
            return self._execute_stream(command, cancel_checker=cancel_checker)
        result = self._execute_sync(command, cancel_checker=cancel_checker)
        return FinsResult(command=command.name, data=result)

    def _execute_sync(
        self,
        command: FinsCommand,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> FinsResultData:
        """执行同步命令。"""

        name = command.name
        payload = command.payload
        if name == FinsCommandName.UPLOAD_FILINGS_FROM:
            typed_payload = _require_upload_filings_from_payload(payload)
            prepared_args = _build_upload_filings_from_args(typed_payload, self.workspace_root)
            return _build_upload_filings_from_result_data(generate_upload_filings_script(prepared_args))

        if name == FinsCommandName.DOWNLOAD:
            typed_payload = _require_download_payload(payload)
            prepared_args, pipeline = self._prepare_download_execution(typed_payload)
            raw_result = pipeline.download(
                ticker=prepared_args.ticker,
                form_type=_coerce_forms_input(prepared_args.form_type),
                start_date=prepared_args.start_date,
                end_date=prepared_args.end_date,
                overwrite=prepared_args.overwrite,
                rebuild=prepared_args.rebuild,
                ticker_aliases=prepared_args.ticker_aliases,
                cancel_checker=cancel_checker,
            )
            return _build_download_result_data(raw_result)
        if name == FinsCommandName.UPLOAD_FILING:
            typed_payload = _require_upload_filing_payload(payload)
            prepared_args, pipeline = self._prepare_upload_filing_execution(typed_payload)
            raw_result = pipeline.upload_filing(
                ticker=prepared_args.ticker,
                action=prepared_args.action,
                files=list(typed_payload.files),
                fiscal_year=prepared_args.fiscal_year,
                fiscal_period=prepared_args.fiscal_period,
                amended=prepared_args.amended,
                filing_date=prepared_args.filing_date,
                report_date=prepared_args.report_date,
                company_id=prepared_args.company_id,
                company_name=prepared_args.company_name,
                ticker_aliases=prepared_args.ticker_aliases,
                overwrite=prepared_args.overwrite,
            )
            return _build_upload_filing_result_data(raw_result)
        if name == FinsCommandName.UPLOAD_MATERIAL:
            typed_payload = _require_upload_material_payload(payload)
            prepared_args, pipeline = self._prepare_upload_material_execution(typed_payload)
            raw_result = pipeline.upload_material(
                ticker=prepared_args.ticker,
                action=prepared_args.action,
                form_type=prepared_args.form_type,
                material_name=prepared_args.material_name,
                files=list(typed_payload.files),
                document_id=prepared_args.document_id,
                internal_document_id=prepared_args.internal_document_id,
                fiscal_year=prepared_args.fiscal_year,
                fiscal_period=prepared_args.fiscal_period,
                filing_date=prepared_args.filing_date,
                report_date=prepared_args.report_date,
                company_id=prepared_args.company_id,
                company_name=prepared_args.company_name,
                ticker_aliases=prepared_args.ticker_aliases,
                overwrite=prepared_args.overwrite,
            )
            return _build_upload_material_result_data(raw_result)
        if name == FinsCommandName.PROCESS:
            typed_payload = _require_process_payload(payload)
            prepared_args, pipeline = self._prepare_process_execution(typed_payload)
            raw_result = pipeline.process(
                ticker=prepared_args.ticker,
                overwrite=prepared_args.overwrite,
                ci=prepared_args.ci,
                document_ids=_coerce_document_ids_input(prepared_args.document_ids),
            )
            return _build_process_result_data(raw_result)
        if name == FinsCommandName.PROCESS_FILING:
            typed_payload = _require_process_filing_payload(payload)
            pipeline = self._build_pipeline_for_ticker(typed_payload.ticker)
            raw_result = pipeline.process_filing(
                ticker=typed_payload.ticker,
                document_id=typed_payload.document_id,
                overwrite=typed_payload.overwrite,
                ci=typed_payload.ci,
                cancel_checker=cancel_checker,
            )
            return _build_process_single_result_data(raw_result)
        if name == FinsCommandName.PROCESS_MATERIAL:
            typed_payload = _require_process_material_payload(payload)
            pipeline = self._build_pipeline_for_ticker(typed_payload.ticker)
            raw_result = pipeline.process_material(
                ticker=typed_payload.ticker,
                document_id=typed_payload.document_id,
                overwrite=typed_payload.overwrite,
                ci=typed_payload.ci,
                cancel_checker=cancel_checker,
            )
            return _build_process_single_result_data(raw_result)
        raise ValueError(f"不支持的命令: {name}")

    async def _execute_stream(
        self,
        command: FinsCommand,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AsyncIterator[FinsEvent]:
        """执行流式命令。

        Args:
            command: 财报命令。
            cancel_checker: 可选取消检查函数；当前仅在已支持的长事务流式链路中继续下传。

        Yields:
            统一的财报事件。

        Raises:
            ValueError: 命令不支持流式执行时抛出。
            RuntimeError: 流式事件缺少最终结果时抛出。
        """

        name = command.name
        payload = command.payload

        if name == FinsCommandName.DOWNLOAD:
            typed_payload = _require_download_payload(payload)
            prepared_args, pipeline = self._prepare_download_execution(typed_payload)
            stream = pipeline.download_stream(
                ticker=prepared_args.ticker,
                form_type=_coerce_forms_input(prepared_args.form_type),
                start_date=prepared_args.start_date,
                end_date=prepared_args.end_date,
                overwrite=prepared_args.overwrite,
                rebuild=prepared_args.rebuild,
                ticker_aliases=prepared_args.ticker_aliases,
                cancel_checker=cancel_checker,
            )
            async for event in self._iter_stream_events(
                command_name=name,
                stream=stream,
                final_event_types={"pipeline_completed"},
            ):
                yield event
            return

        if name == FinsCommandName.PROCESS:
            typed_payload = _require_process_payload(payload)
            prepared_args, pipeline = self._prepare_process_execution(typed_payload)
            stream = pipeline.process_stream(
                ticker=prepared_args.ticker,
                overwrite=prepared_args.overwrite,
                ci=prepared_args.ci,
                document_ids=_coerce_document_ids_input(prepared_args.document_ids),
                cancel_checker=cancel_checker,
            )
            async for event in self._iter_stream_events(
                command_name=name,
                stream=stream,
                final_event_types={"pipeline_completed"},
            ):
                yield event
            return

        if name == FinsCommandName.UPLOAD_FILING:
            typed_payload = _require_upload_filing_payload(payload)
            prepared_args, pipeline = self._prepare_upload_filing_execution(typed_payload)
            stream = pipeline.upload_filing_stream(
                ticker=prepared_args.ticker,
                action=prepared_args.action,
                files=list(typed_payload.files),
                fiscal_year=prepared_args.fiscal_year,
                fiscal_period=prepared_args.fiscal_period,
                amended=prepared_args.amended,
                filing_date=prepared_args.filing_date,
                report_date=prepared_args.report_date,
                company_id=prepared_args.company_id,
                company_name=prepared_args.company_name,
                ticker_aliases=prepared_args.ticker_aliases,
                overwrite=prepared_args.overwrite,
            )
            async for event in self._iter_stream_events(
                command_name=name,
                stream=stream,
                final_event_types={"upload_completed", "upload_failed"},
            ):
                yield event
            return

        if name == FinsCommandName.UPLOAD_MATERIAL:
            typed_payload = _require_upload_material_payload(payload)
            prepared_args, pipeline = self._prepare_upload_material_execution(typed_payload)
            stream = pipeline.upload_material_stream(
                ticker=prepared_args.ticker,
                action=prepared_args.action,
                form_type=prepared_args.form_type,
                material_name=prepared_args.material_name,
                files=list(typed_payload.files),
                document_id=prepared_args.document_id,
                internal_document_id=prepared_args.internal_document_id,
                fiscal_year=prepared_args.fiscal_year,
                fiscal_period=prepared_args.fiscal_period,
                filing_date=prepared_args.filing_date,
                report_date=prepared_args.report_date,
                company_id=prepared_args.company_id,
                company_name=prepared_args.company_name,
                ticker_aliases=prepared_args.ticker_aliases,
                overwrite=prepared_args.overwrite,
            )
            async for event in self._iter_stream_events(
                command_name=name,
                stream=stream,
                final_event_types={"upload_completed", "upload_failed"},
            ):
                yield event
            return

        raise ValueError(f"不支持流式执行的命令: {name}")

    async def _iter_stream_events(
        self,
        *,
        command_name: FinsCommandName,
        stream: AsyncIterator[DownloadEvent | ProcessEvent | UploadFilingEvent | UploadMaterialEvent],
        final_event_types: set[str],
    ) -> AsyncIterator[FinsEvent]:
        """将 pipeline 事件流转换为统一 FinsEvent 流。"""

        final_result: FinsResultData | None = None
        async for event in stream:
            if command_name == FinsCommandName.DOWNLOAD:
                progress_payload = _build_download_progress_payload(_require_download_event(event))
            elif command_name == FinsCommandName.PROCESS:
                progress_payload = _build_process_progress_payload(_require_process_event(event))
            elif command_name == FinsCommandName.UPLOAD_FILING:
                progress_payload = _build_upload_filing_progress_payload(_require_upload_filing_event(event))
            else:
                progress_payload = _build_upload_material_progress_payload(_require_upload_material_event(event))
            yield FinsEvent(
                type=FinsEventType.PROGRESS,
                command=command_name,
                payload=progress_payload,
            )
            if event.event_type in final_event_types:
                extracted = _extract_result_data_from_event(command_name=command_name, event_payload=event.payload)
                if extracted is not None:
                    final_result = extracted

        if final_result is None:
            raise RuntimeError(f"{command_name} 事件流未返回最终结果")

        yield FinsEvent(
            type=FinsEventType.RESULT,
            command=command_name,
            payload=final_result,
        )


__all__ = [
    "CompanyMetaProviderProtocol",
    "DefaultFinsRuntime",
    "FinsRuntimeProtocol",
]
