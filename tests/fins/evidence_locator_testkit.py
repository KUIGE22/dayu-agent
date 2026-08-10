"""Evidence Locator 测试用 fake 仓储与处理器 testkit。

该模块只服务于测试代码，提供：

- ``MemorySource``：内存 Source 实现。
- ``EvidenceSourceRepository`` / ``EvidenceProcessedRepository`` /
  ``EvidenceCompanyRepository``：source/processed/company 窄仓储 fake。
- ``FakeEvidenceProcessor`` / ``EvidenceProcessorRegistry``：可注入数据的
  处理器与注册表 fake。

所有 fake 都完整实现对应协议，供 runtime / service 测试以类型安全方式装配
``DefaultFinsRuntime``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Callable, Optional

from dayu.engine.processors.base import (
    DocumentProcessor,
    PageContentResult,
    SearchHit,
    SectionContent,
    SectionSummary,
    TableContent,
    TableSummary,
)
from dayu.engine.processors.processor_registry import ProcessorRegistry
from dayu.engine.processors.source import Source
from dayu.fins.domain.document_models import (
    CompanyMeta,
    CompanyMetaInventoryEntry,
    DocumentEntry,
    DocumentHandle,
    DocumentMeta,
    DocumentQuery,
    DocumentSummary,
    FileObjectMeta,
    ProcessedCreateRequest,
    ProcessedDeleteRequest,
    ProcessedHandle,
    ProcessedUpdateRequest,
    RejectedFilingArtifact,
    RejectedFilingArtifactUpsertRequest,
    SourceDocumentStateChangeRequest,
    SourceDocumentUpsertRequest,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.evidence_locator import JsonValue


class StubBlobRepository:
    """blob 仓储测试桩。"""

    def list_entries(self, handle: SourceHandle | ProcessedHandle) -> list[DocumentEntry]:
        """返回空条目列表。

        Args:
            handle: 文档句柄。

        Returns:
            空列表。

        Raises:
            无。
        """

        del handle
        return []

    def read_file_bytes(self, handle: SourceHandle | ProcessedHandle, name: str) -> bytes:
        """测试桩不支持字节读取。

        Args:
            handle: 文档句柄。
            name: 文件名。

        Returns:
            无。

        Raises:
            NotImplementedError: 测试桩不支持该能力。
        """

        del handle, name
        raise NotImplementedError("StubBlobRepository 不支持字节读取")

    def delete_entry(self, handle: SourceHandle | ProcessedHandle, name: str) -> None:
        """测试桩不支持删除。

        Args:
            handle: 文档句柄。
            name: 文件名。

        Returns:
            无。

        Raises:
            NotImplementedError: 测试桩不支持该能力。
        """

        del handle, name
        raise NotImplementedError("StubBlobRepository 不支持删除")

    def store_file(
        self,
        handle: SourceHandle | ProcessedHandle,
        filename: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """测试桩不支持写入。

        Args:
            handle: 文档句柄。
            filename: 文件名。
            data: 数据流。
            content_type: 内容类型。
            metadata: 元数据。

        Returns:
            无。

        Raises:
            NotImplementedError: 测试桩不支持该能力。
        """

        del handle, filename, data, content_type, metadata
        raise NotImplementedError("StubBlobRepository 不支持写入")

    def list_files(self, handle: SourceHandle | ProcessedHandle) -> list[FileObjectMeta]:
        """返回空文件列表。

        Args:
            handle: 文档句柄。

        Returns:
            空列表。

        Raises:
            无。
        """

        del handle
        return []


class StubFilingMaintenanceRepository:
    """filing 维护仓储测试桩。"""

    def clear_filing_documents(self, ticker: str) -> None:
        """测试桩不支持清理。

        Args:
            ticker: 股票代码。

        Returns:
            无。

        Raises:
            NotImplementedError: 测试桩不支持该能力。
        """

        del ticker
        raise NotImplementedError("StubFilingMaintenanceRepository 不支持清理")

    def load_download_rejection_registry(self, ticker: str) -> dict[str, dict[str, str]]:
        """返回空拒绝注册表。

        Args:
            ticker: 股票代码。

        Returns:
            空字典。

        Raises:
            无。
        """

        del ticker
        return {}

    def save_download_rejection_registry(
        self,
        ticker: str,
        registry: dict[str, dict[str, str]],
    ) -> None:
        """测试桩不支持写入。

        Args:
            ticker: 股票代码。
            registry: 拒绝注册表。

        Returns:
            无。

        Raises:
            NotImplementedError: 测试桩不支持该能力。
        """

        del ticker, registry
        raise NotImplementedError("StubFilingMaintenanceRepository 不支持写入")

    def store_rejected_filing_file(
        self,
        ticker: str,
        document_id: str,
        filename: str,
        data: BinaryIO,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """测试桩不支持写入。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            filename: 文件名。
            data: 数据流。
            content_type: 内容类型。
            metadata: 元数据。

        Returns:
            无。

        Raises:
            NotImplementedError: 测试桩不支持该能力。
        """

        del ticker, document_id, filename, data, content_type, metadata
        raise NotImplementedError("StubFilingMaintenanceRepository 不支持写入")

    def upsert_rejected_filing_artifact(
        self,
        req: RejectedFilingArtifactUpsertRequest,
    ) -> RejectedFilingArtifact:
        """测试桩不支持写入。

        Args:
            req: 请求对象。

        Returns:
            无。

        Raises:
            NotImplementedError: 测试桩不支持该能力。
        """

        del req
        raise NotImplementedError("StubFilingMaintenanceRepository 不支持写入")

    def get_rejected_filing_artifact(
        self,
        ticker: str,
        document_id: str,
    ) -> RejectedFilingArtifact:
        """测试桩不支持读取。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            无。

        Raises:
            NotImplementedError: 测试桩不支持该能力。
        """

        del ticker, document_id
        raise NotImplementedError("StubFilingMaintenanceRepository 不支持读取")

    def list_rejected_filing_artifacts(self, ticker: str) -> list[RejectedFilingArtifact]:
        """返回空列表。

        Args:
            ticker: 股票代码。

        Returns:
            空列表。

        Raises:
            无。
        """

        del ticker
        return []

    def read_rejected_filing_file_bytes(
        self,
        ticker: str,
        document_id: str,
        filename: str,
    ) -> bytes:
        """测试桩不支持读取。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            filename: 文件名。

        Returns:
            无。

        Raises:
            NotImplementedError: 测试桩不支持该能力。
        """

        del ticker, document_id, filename
        raise NotImplementedError("StubFilingMaintenanceRepository 不支持读取")

    def cleanup_stale_filing_documents(
        self,
        ticker: str,
        *,
        active_form_types: set[str],
        valid_document_ids: set[str],
    ) -> int:
        """返回 0。

        Args:
            ticker: 股票代码。
            active_form_types: 活跃表单类型。
            valid_document_ids: 有效文档 ID。

        Returns:
            固定返回 0。

        Raises:
            无。
        """

        del ticker, active_form_types, valid_document_ids
        return 0


class MemorySource:
    """内存 Source 实现。"""

    def __init__(self, uri: str, content: bytes, media_type: Optional[str] = None) -> None:
        """初始化内存 Source。

        Args:
            uri: 资源 URI。
            content: 文件 bytes。
            media_type: 媒体类型。

        Returns:
            无。

        Raises:
            无。
        """

        self.uri = uri
        self.content = content
        self.media_type = media_type
        self.content_length = len(content)
        self.etag = None

    def open(self) -> BinaryIO:
        """打开只读内存流。

        Args:
            无。

        Returns:
            二进制只读流。

        Raises:
            无。
        """

        from io import BytesIO

        return BytesIO(self.content)

    def materialize(self, suffix: Optional[str] = None) -> Path:
        """物化路径（测试桩不支持）。

        Args:
            suffix: 可选后缀。

        Returns:
            无。

        Raises:
            OSError: 测试桩不提供物化能力。
        """

        del suffix
        raise OSError("memory source 不支持 materialize")


@dataclass
class SeededSource:
    """source 种子数据。

    Attributes:
        meta: source meta 字典。
        primary_bytes: 主文件 bytes。
        primary_sha: 可选 meta sha256；``None`` 表示不提供。
        primary_file_missing: 模拟 ``get_primary_file`` 抛 ``FileNotFoundError``。
    """

    meta: dict[str, JsonValue]
    primary_bytes: bytes
    primary_sha: Optional[str] = None
    primary_file_missing: bool = False


@dataclass(frozen=True)
class EvidenceDocumentData:
    """单个文档的处理器注入数据。

    Attributes:
        sections: 章节摘要列表。
        section_by_ref: ref 到章节正文的映射。
        tables: 表格摘要列表。
        table_by_ref: table_ref 到表格内容的映射。
        page: 页面内容结果。
        xbrl_facts: XBRL fact 列表。
    """

    sections: list[SectionSummary] = field(default_factory=list)
    section_by_ref: dict[str, SectionContent] = field(default_factory=dict)
    tables: list[TableSummary] = field(default_factory=list)
    table_by_ref: dict[str, TableContent] = field(default_factory=dict)
    page: PageContentResult | None = None
    xbrl_facts: list[dict[str, JsonValue]] = field(default_factory=list)


class EvidenceSourceRepository:
    """source 文档仓储 fake。"""

    def __init__(self) -> None:
        """初始化空仓储。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._entries: dict[tuple[str, str, SourceKind], SeededSource] = {}

    def seed(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        *,
        meta: dict[str, JsonValue],
        primary_bytes: bytes,
        primary_sha: Optional[str] = None,
        primary_file_missing: bool = False,
    ) -> None:
        """写入 source 种子数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            meta: source meta。
            primary_bytes: 主文件 bytes。
            primary_sha: 可选 meta sha256。
            primary_file_missing: 是否模拟主文件元数据缺失。

        Returns:
            无。

        Raises:
            无。
        """

        self._entries[(ticker, document_id, source_kind)] = SeededSource(
            meta=meta,
            primary_bytes=primary_bytes,
            primary_sha=primary_sha,
            primary_file_missing=primary_file_missing,
        )

    def mutate_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        **changes: JsonValue,
    ) -> None:
        """原地修改 source meta（测试辅助，用于 race 模拟）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            changes: 需要覆盖的 meta 字段。

        Returns:
            无。

        Raises:
            KeyError: 目标 source 不存在时抛出。
        """

        entry = self._entries[(ticker, document_id, source_kind)]
        entry.meta.update(changes)

    def replace_primary_bytes(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        primary_bytes: bytes,
    ) -> None:
        """替换主文件 bytes（测试辅助，用于 race 模拟）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            primary_bytes: 新的主文件 bytes。

        Returns:
            无。

        Raises:
            KeyError: 目标 source 不存在时抛出。
        """

        entry = self._entries[(ticker, document_id, source_kind)]
        entry.primary_bytes = primary_bytes

    def _lookup(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> SeededSource | None:
        """按身份查找种子数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            种子数据；不存在时返回 ``None``。

        Raises:
            无。
        """

        return self._entries.get((ticker, document_id, source_kind))

    def get_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> DocumentMeta:
        """读取源文档 meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            source meta 字典副本。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
        """

        entry = self._lookup(ticker, document_id, source_kind)
        if entry is None:
            raise FileNotFoundError(document_id)
        return dict(entry.meta)

    def get_source_handle(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> SourceHandle:
        """构造源文档句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            源文档句柄。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
        """

        entry = self._lookup(ticker, document_id, source_kind)
        if entry is None:
            raise FileNotFoundError(document_id)
        return SourceHandle(
            ticker=ticker,
            document_id=document_id,
            source_kind=source_kind.value,
        )

    def get_primary_source(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> Source:
        """读取源文档主文件 source。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            ``MemorySource`` 主文件。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
        """

        entry = self._lookup(ticker, document_id, source_kind)
        if entry is None:
            raise FileNotFoundError(document_id)
        return MemorySource(
            uri=f"memory://{source_kind.value}/{document_id}",
            content=entry.primary_bytes,
            media_type="text/html",
        )

    def get_primary_file(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> FileObjectMeta:
        """读取源文档主文件对象元数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            主文件元数据。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
        """

        entry = self._lookup(ticker, document_id, source_kind)
        if entry is None:
            raise FileNotFoundError(document_id)
        if entry.primary_file_missing:
            raise FileNotFoundError(f"primary file missing: {document_id}")
        return FileObjectMeta(
            uri=f"memory://{source_kind.value}/{document_id}",
            sha256=entry.primary_sha,
        )

    def list_source_document_ids(self, ticker: str, source_kind: SourceKind) -> list[str]:
        """按来源列出源文档 ID。

        Args:
            ticker: 股票代码。
            source_kind: 来源类型。

        Returns:
            文档 ID 列表。

        Raises:
            无。
        """

        return [
            document_id
            for (entry_ticker, document_id, entry_kind) in self._entries
            if entry_ticker == ticker and entry_kind is source_kind
        ]

    def has_source_storage_root(self, ticker: str, source_kind: SourceKind) -> bool:
        """判断某类源文档根目录是否存在。

        Args:
            ticker: 股票代码。
            source_kind: 来源类型。

        Returns:
            是否已有对应种子数据。

        Raises:
            无。
        """

        return bool(self.list_source_document_ids(ticker, source_kind))

    def has_filing_xbrl_instance(self, ticker: str, document_id: str) -> bool:
        """判断 filing 是否已落盘 XBRL instance。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            固定返回 ``False``。

        Raises:
            无。
        """

        del ticker, document_id
        return False

    def create_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
    ) -> DocumentHandle:
        """测试 fake 不负责写路径。

        Args:
            req: 写入请求。
            source_kind: 来源类型。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del req, source_kind
        raise NotImplementedError("EvidenceSourceRepository 不实现写路径")

    def update_source_document(
        self,
        req: SourceDocumentUpsertRequest,
        source_kind: SourceKind,
    ) -> DocumentHandle:
        """测试 fake 不负责写路径。

        Args:
            req: 写入请求。
            source_kind: 来源类型。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del req, source_kind
        raise NotImplementedError("EvidenceSourceRepository 不实现写路径")

    def delete_source_document(self, req: SourceDocumentStateChangeRequest) -> None:
        """测试 fake 不负责写路径。

        Args:
            req: 删除请求。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del req
        raise NotImplementedError("EvidenceSourceRepository 不实现写路径")

    def reset_source_document(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> None:
        """测试 fake 不负责重置写路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del ticker, document_id, source_kind
        raise NotImplementedError("EvidenceSourceRepository 不实现写路径")

    def restore_source_document(self, req: SourceDocumentStateChangeRequest) -> DocumentHandle:
        """测试 fake 不负责写路径。

        Args:
            req: 恢复请求。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del req
        raise NotImplementedError("EvidenceSourceRepository 不实现写路径")

    def replace_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        meta: DocumentMeta,
    ) -> None:
        """测试 fake 不负责写路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            meta: 新 meta。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del ticker, document_id, source_kind, meta
        raise NotImplementedError("EvidenceSourceRepository 不实现写路径")

    def get_source(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        filename: str,
    ) -> Source:
        """测试 fake 只提供主文件 source。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            filename: 目标文件名。

        Returns:
            主文件 source。

        Raises:
            NotImplementedError: fake 不支持按文件名读取。
        """

        del ticker, document_id, source_kind, filename
        raise NotImplementedError("EvidenceSourceRepository 不实现按文件名读取")


class EvidenceProcessedRepository:
    """processed 文档仓储 fake。"""

    def __init__(self) -> None:
        """初始化空仓储。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._meta: dict[tuple[str, str], dict[str, JsonValue]] = {}

    def seed(self, ticker: str, document_id: str, meta: dict[str, JsonValue]) -> None:
        """写入 processed meta 种子数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            meta: processed meta。

        Returns:
            无。

        Raises:
            无。
        """

        self._meta[(ticker, document_id)] = meta

    def get_processed_meta(self, ticker: str, document_id: str) -> DocumentMeta:
        """读取 processed meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            processed meta 字典副本。

        Raises:
            FileNotFoundError: processed 不存在时抛出。
        """

        entry = self._meta.get((ticker, document_id))
        if entry is None:
            raise FileNotFoundError(document_id)
        return dict(entry)

    def create_processed(self, req: ProcessedCreateRequest) -> DocumentHandle:
        """测试 fake 不负责写路径。

        Args:
            req: 创建请求。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del req
        raise NotImplementedError("EvidenceProcessedRepository 不实现写路径")

    def update_processed(self, req: ProcessedUpdateRequest) -> DocumentHandle:
        """测试 fake 不负责写路径。

        Args:
            req: 更新请求。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del req
        raise NotImplementedError("EvidenceProcessedRepository 不实现写路径")

    def delete_processed(self, req: ProcessedDeleteRequest) -> None:
        """测试 fake 不负责写路径。

        Args:
            req: 删除请求。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del req
        raise NotImplementedError("EvidenceProcessedRepository 不实现写路径")

    def get_processed_handle(self, ticker: str, document_id: str) -> ProcessedHandle:
        """构造 processed 句柄。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            processed 句柄。

        Raises:
            无。
        """

        return ProcessedHandle(ticker=ticker, document_id=document_id)

    def list_processed_documents(self, ticker: str, query: DocumentQuery) -> list[DocumentSummary]:
        """测试 fake 不提供列表查询。

        Args:
            ticker: 股票代码。
            query: 查询条件。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持列表查询。
        """

        del ticker, query
        raise NotImplementedError("EvidenceProcessedRepository 不实现列表查询")

    def clear_processed_documents(self, ticker: str) -> None:
        """测试 fake 不负责写路径。

        Args:
            ticker: 股票代码。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del ticker
        raise NotImplementedError("EvidenceProcessedRepository 不实现写路径")

    def mark_processed_reprocess_required(
        self,
        ticker: str,
        document_id: str,
        required: bool,
    ) -> None:
        """测试 fake 不负责写路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            required: 是否需要重处理。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del ticker, document_id, required
        raise NotImplementedError("EvidenceProcessedRepository 不实现写路径")


class EvidenceCompanyRepository:
    """公司元数据仓储 fake。"""

    def get_company_meta(self, ticker: str) -> CompanyMeta:
        """读取公司元数据。

        Args:
            ticker: 股票代码。

        Returns:
            固定测试公司元数据。

        Raises:
            无。
        """

        return CompanyMeta(
            company_id="1",
            company_name="Test Co",
            ticker=ticker,
            market="US",
            resolver_version="test",
            updated_at="2026-01-01T00:00:00+00:00",
        )

    def scan_company_meta_inventory(self) -> list[CompanyMetaInventoryEntry]:
        """返回空盘点。

        Args:
            无。

        Returns:
            空列表。

        Raises:
            无。
        """

        return []

    def upsert_company_meta(self, meta: CompanyMeta) -> None:
        """测试 fake 不负责写路径。

        Args:
            meta: 公司元数据。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持写路径。
        """

        del meta
        raise NotImplementedError("EvidenceCompanyRepository 不实现写路径")

    def resolve_existing_ticker(self, ticker_candidates: list[str]) -> Optional[str]:
        """解析已存在 ticker。

        Args:
            ticker_candidates: 候选 ticker。

        Returns:
            首个候选 ticker。

        Raises:
            无。
        """

        return ticker_candidates[0] if ticker_candidates else None


class FakeEvidenceProcessor:
    """可注入数据的文档处理器 fake。

    完整实现 ``DocumentProcessor`` 协议，并附带 ``get_page_content`` /
    ``query_xbrl_facts`` / ``get_financial_statement`` 能力方法。
    """

    def __init__(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> None:
        """初始化处理器。

        Args:
            source: 文档来源。
            form_type: 文档类型。
            media_type: 媒体类型。

        Returns:
            无。

        Raises:
            无。
        """

        self.source = source
        self.form_type = form_type
        self.media_type = media_type
        self.data = EvidenceDocumentData()

    @classmethod
    def get_parser_version(cls) -> str:
        """返回 parser version。

        Args:
            无。

        Returns:
            parser version。

        Raises:
            无。
        """

        return "test"

    @classmethod
    def supports(
        cls,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> bool:
        """判断是否支持该文件。

        Args:
            source: 文档来源。
            form_type: 文档类型。
            media_type: 媒体类型。

        Returns:
            固定返回 ``True``。

        Raises:
            无。
        """

        del source, form_type, media_type
        return True

    def list_sections(self) -> list[SectionSummary]:
        """读取章节列表。

        Args:
            无。

        Returns:
            注入的章节摘要列表。

        Raises:
            无。
        """

        return self.data.sections

    def list_tables(self) -> list[TableSummary]:
        """读取表格列表。

        Args:
            无。

        Returns:
            注入的表格摘要列表。

        Raises:
            无。
        """

        return self.data.tables

    def read_section(self, ref: str) -> SectionContent:
        """按 ref 读取章节内容。

        Args:
            ref: 章节引用。

        Returns:
            注入的章节内容。

        Raises:
            KeyError: 章节不存在时抛出。
        """

        if ref not in self.data.section_by_ref:
            raise KeyError(ref)
        return self.data.section_by_ref[ref]

    def read_table(self, table_ref: str) -> TableContent:
        """按 table_ref 读取表格内容。

        Args:
            table_ref: 表格引用。

        Returns:
            注入的表格内容。

        Raises:
            KeyError: 表格不存在时抛出。
        """

        if table_ref not in self.data.table_by_ref:
            raise KeyError(table_ref)
        return self.data.table_by_ref[table_ref]

    def get_section_title(self, ref: str) -> Optional[str]:
        """根据 section ref 获取章节标题。

        Args:
            ref: 章节引用。

        Returns:
            章节标题；不存在时返回 ``None``。

        Raises:
            无。
        """

        for section in self.data.sections:
            if section.get("ref") == ref:
                return section.get("title")
        return None

    def search(
        self,
        query: str,
        within_ref: Optional[str] = None,
    ) -> list[SearchHit]:
        """测试 fake 不提供搜索。

        Args:
            query: 搜索词。
            within_ref: 可选章节范围。

        Returns:
            空列表。

        Raises:
            无。
        """

        del query, within_ref
        return []

    def get_full_text(self) -> str:
        """返回空全文。

        Args:
            无。

        Returns:
            空字符串。

        Raises:
            无。
        """

        return ""

    def get_full_text_with_table_markers(self) -> str:
        """返回空全文。

        Args:
            无。

        Returns:
            空字符串。

        Raises:
            无。
        """

        return ""

    def get_page_content(self, page_no: int) -> PageContentResult:
        """读取页面内容。

        Args:
            page_no: 页码。

        Returns:
            注入的页面内容（页码覆盖为入参）。

        Raises:
            ValueError: 未注入页面数据时抛出。
        """

        if self.data.page is None:
            raise ValueError("未注入 page 数据")
        return PageContentResult(
            page_no=page_no,
            sections=self.data.page.get("sections", []),
            tables=self.data.page.get("tables", []),
            text_preview=str(self.data.page.get("text_preview", "")),
            has_content=bool(self.data.page.get("has_content", False)),
            total_items=int(self.data.page.get("total_items", 0)),
            supported=bool(self.data.page.get("supported", True)),
        )

    def query_xbrl_facts(
        self,
        concepts: list[str],
        statement_type: Optional[str] = None,
        period_end: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        fiscal_period: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> dict[str, JsonValue]:
        """查询 XBRL facts。

        Args:
            concepts: 概念列表。
            statement_type: 报表类型。
            period_end: 期末日期。
            fiscal_year: 财年。
            fiscal_period: 财期。
            min_value: 最小值。
            max_value: 最大值。

        Returns:
            注入的 facts 载荷。

        Raises:
            无。
        """

        del statement_type, period_end, fiscal_year, fiscal_period, min_value, max_value
        return {
            "facts": self.data.xbrl_facts,
            "query_params": {"concepts": concepts},
        }

    def get_financial_statement(self, statement_type: str) -> dict[str, JsonValue]:
        """测试 fake 不提供财务报表。

        Args:
            statement_type: 报表类型。

        Returns:
            无。

        Raises:
            NotImplementedError: fake 不支持财务报表。
        """

        del statement_type
        raise NotImplementedError("FakeEvidenceProcessor 不提供财务报表")


class EvidenceProcessorRegistry(ProcessorRegistry):
    """按文档注入数据的处理器注册表 fake。"""

    def __init__(self, data: dict[str, EvidenceDocumentData]) -> None:
        """初始化注册表。

        Args:
            data: document_id 到注入数据的映射。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self.create_call_count = 0
        self.create_hook: Callable[[], None] | None = None
        self._data = data

    def create(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> FakeEvidenceProcessor:
        """创建处理器实例。

        Args:
            source: 文档来源。
            form_type: 文档类型。
            media_type: 媒体类型。

        Returns:
            处理器实例。

        Raises:
            无。
        """

        if self.create_hook is not None:
            self.create_hook()
        self.create_call_count += 1
        processor = FakeEvidenceProcessor(
            source,
            form_type=form_type,
            media_type=media_type,
        )
        document_id = str(source.uri).split("/")[-1].split(".")[0]
        processor.data = self._data.get(document_id, EvidenceDocumentData())
        return processor

    def create_with_fallback(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
        on_fallback: Optional[Callable[[type[DocumentProcessor], Exception, int, int], None]] = None,
    ) -> FakeEvidenceProcessor:
        """兼容统一回退接口并复用 create。

        Args:
            source: 文档来源。
            form_type: 文档类型。
            media_type: 媒体类型。
            on_fallback: 回退回调（本桩不触发）。

        Returns:
            处理器实例。

        Raises:
            无。
        """

        del on_fallback
        return self.create(source, form_type=form_type, media_type=media_type)


@dataclass(frozen=True)
class EvidenceRuntimeContext:
    """runtime 测试装配上下文。

    Attributes:
        source_repository: source 仓储 fake。
        processed_repository: processed 仓储 fake。
        company_repository: 公司仓储 fake。
        processor_registry: 处理器注册表 fake。
        blob_repository: blob 仓储桩。
        filing_maintenance_repository: filing 维护仓储桩。
    """

    source_repository: EvidenceSourceRepository
    processed_repository: EvidenceProcessedRepository
    company_repository: EvidenceCompanyRepository
    processor_registry: EvidenceProcessorRegistry
    blob_repository: StubBlobRepository
    filing_maintenance_repository: StubFilingMaintenanceRepository


def build_evidence_runtime_context(
    data: dict[str, EvidenceDocumentData],
) -> EvidenceRuntimeContext:
    """构建共享同一底层 fake 的 runtime 上下文。

    Args:
        data: document_id 到处理器注入数据的映射。

    Returns:
        runtime 测试装配上下文。

    Raises:
        无。
    """

    return EvidenceRuntimeContext(
        source_repository=EvidenceSourceRepository(),
        processed_repository=EvidenceProcessedRepository(),
        company_repository=EvidenceCompanyRepository(),
        processor_registry=EvidenceProcessorRegistry(data),
        blob_repository=StubBlobRepository(),
        filing_maintenance_repository=StubFilingMaintenanceRepository(),
    )
