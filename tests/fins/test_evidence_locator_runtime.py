"""Evidence Locator runtime resolve/validate/read 测试。

覆盖 S13-CTRL-07 要求的五 kind / 允许组合、source/processed closure、
dual-kind 碰撞、shared-cache 不复用、pre/post race、processed 各字段闭合、
canonical citation bytes 与递归泄漏扫描。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pytest

from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.evidence_locator import (
    ArtifactKind,
    CitationProjection,
    DocumentLocatorPayload,
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
    sha256_hex,
)
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.service import FinsToolService
from tests.fins.evidence_locator_testkit import (
    EvidenceDocumentData,
    EvidenceRuntimeContext,
    build_evidence_runtime_context,
)

_PRIMARY_BYTES = b"<source primary bytes>"
_FINGERPRINT = "f" * 64


def _make_runtime(ctx: EvidenceRuntimeContext) -> DefaultFinsRuntime:
    """构建测试用 runtime。"""

    return DefaultFinsRuntime(
        workspace_root=Path("/tmp/evidence-test"),
        company_repository=ctx.company_repository,
        source_repository=ctx.source_repository,
        processed_repository=ctx.processed_repository,
        blob_repository=ctx.blob_repository,
        filing_maintenance_repository=ctx.filing_maintenance_repository,
        processor_registry=ctx.processor_registry,
    )


def _seed_source(
    ctx: EvidenceRuntimeContext,
    document_id: str,
    *,
    source_kind: SourceKind = SourceKind.FILING,
    version: str = "v1",
    fingerprint: str = _FINGERPRINT,
    is_deleted: bool = False,
    ingest_complete: bool = True,
    primary_bytes: bytes = _PRIMARY_BYTES,
    primary_sha: str | None = None,
    primary_file_missing: bool = False,
    meta_extra: dict[str, JsonValue] | None = None,
) -> None:
    """写入 source 种子数据。"""

    meta: dict[str, JsonValue] = {
        "document_id": document_id,
        "form_type": None,
        "is_deleted": is_deleted,
        "ingest_complete": ingest_complete,
        "document_version": version,
        "source_fingerprint": fingerprint,
    }
    if meta_extra:
        meta.update(meta_extra)
    ctx.source_repository.seed(
        "AAPL",
        document_id,
        source_kind,
        meta=meta,
        primary_bytes=primary_bytes,
        primary_sha=primary_sha,
        primary_file_missing=primary_file_missing,
    )


def _seed_processed(
    ctx: EvidenceRuntimeContext,
    document_id: str,
    *,
    source_kind: str = "filing",
    version: str = "v1",
    fingerprint: str = _FINGERPRINT,
    is_deleted: bool = False,
    reprocess_required: bool = False,
    extra: dict[str, JsonValue] | None = None,
) -> None:
    """写入 processed meta 种子数据。"""

    meta: dict[str, JsonValue] = {
        "document_id": document_id,
        "source_kind": source_kind,
        "source_document_version": version,
        "source_fingerprint": fingerprint,
        "is_deleted": is_deleted,
        "reprocess_required": reprocess_required,
    }
    if extra:
        meta.update(extra)
    ctx.processed_repository.seed("AAPL", document_id, meta)


def _build_request(
    *,
    ticker: str = "AAPL",
    document_id: str = "doc_1",
    source_kind: SourceKind = SourceKind.FILING,
    artifact_kind: ArtifactKind = ArtifactKind.PROCESSED,
    document_version: str = "v1",
    source_fingerprint: str = _FINGERPRINT,
    primary_content_sha256: str = "0" * 64,
    locator_kind: LocatorKind = LocatorKind.DOCUMENT,
    locator_payload: LocatorPayload = DocumentLocatorPayload(),
    locator_content_sha256: str = "0" * 64,
) -> EvidenceLocatorRequest:
    """构造证据定位器请求。"""

    return EvidenceLocatorRequest(
        schema_version="fins-evidence-locator-v1",
        repository_id="dayu.fins.public.v1",
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


def _build_tool(ctx: EvidenceRuntimeContext) -> FinsToolService:
    """构建 request-scoped 同构 FinsToolService 探针。"""

    return FinsToolService(
        company_repository=ctx.company_repository,
        source_repository=ctx.source_repository,
        processed_repository=ctx.processed_repository,
        processor_registry=ctx.processor_registry,
        processor_cache_max_entries=8,
    )


def _probe_fragment_bytes(
    ctx: EvidenceRuntimeContext,
    *,
    ticker: str,
    document_id: str,
    artifact_kind: ArtifactKind,
    locator_kind: LocatorKind,
    locator_payload: LocatorPayload,
    primary_bytes: bytes,
) -> bytes:
    """测试探针：按 runtime 相同语义复现 canonical fragment bytes。"""

    if artifact_kind is ArtifactKind.SOURCE:
        return primary_bytes
    tool = _build_tool(ctx)
    if locator_kind is LocatorKind.DOCUMENT:
        sections_result = tool.get_document_sections(ticker=ticker, document_id=document_id)
        tables_result = tool.list_tables(ticker=ticker, document_id=document_id)
        return canonical_json_bytes(
            {
                "sections": sections_result["sections"],
                "tables": tables_result["tables"],
            }
        )
    if locator_kind is LocatorKind.PAGE:
        assert isinstance(locator_payload, PageLocatorPayload)
        result = tool.get_page_content(
            ticker=ticker,
            document_id=document_id,
            page_no=locator_payload.page_no,
        )
        return canonical_json_bytes(
            {
                "page_no": result.get("page_no"),
                "sections": result.get("sections"),
                "tables": result.get("tables"),
                "text_preview": result.get("text_preview"),
                "has_content": result.get("has_content"),
                "total_items": result.get("total_items"),
                "supported": result.get("supported"),
            }
        )
    if locator_kind is LocatorKind.SECTION:
        assert isinstance(locator_payload, SectionLocatorPayload)
        result = tool.read_section(
            ticker=ticker,
            document_id=document_id,
            ref=locator_payload.section_ref,
        )
        return canonical_json_bytes(
            {
                "ref": result.get("ref"),
                "title": result.get("title"),
                "item": result.get("item"),
                "topic": result.get("topic"),
                "content": result.get("content"),
                "children": result.get("children"),
                "page_range": result.get("page_range"),
                "content_word_count": result.get("content_word_count"),
            }
        )
    if locator_kind is LocatorKind.TABLE_CELL:
        assert isinstance(locator_payload, TableCellLocatorPayload)
        result = tool.get_table(
            ticker=ticker,
            document_id=document_id,
            table_ref=locator_payload.table_ref,
        )
        rows = result["data"]["rows"]
        row = rows[locator_payload.row_index]
        return canonical_json_bytes(
            {
                "column": locator_payload.column,
                "row_index": locator_payload.row_index,
                "table_ref": locator_payload.table_ref,
                "value": row[locator_payload.column],
            }
        )
    if locator_kind is LocatorKind.XBRL_FACT:
        assert isinstance(locator_payload, XbrlFactLocatorPayload)
        result = tool.query_xbrl_facts(
            ticker=ticker,
            document_id=document_id,
            concepts=[locator_payload.concept],
        )
        matched: list[bytes] = []
        for fact in result.get("facts", []):
            if not isinstance(fact, dict):
                continue
            if str(fact.get("concept") or "") != locator_payload.concept:
                continue
            row = {key: fact.get(key) for key in (
                "concept", "label", "numeric_value", "text_value", "content_type",
                "unit", "decimals", "period_type", "period_start", "period_end",
                "fiscal_year", "fiscal_period", "statement_type",
            )}
            row_bytes = canonical_json_bytes(row)
            if sha256_hex(row_bytes) == locator_payload.fact_sha256:
                matched.append(row_bytes)
        assert len(matched) == 1, f"探针匹配 {len(matched)} 条"
        return matched[0]
    raise AssertionError(f"未支持的 locator_kind: {locator_kind}")


_FORBIDDEN_PATTERNS = (
    "file://",
    "http://",
    "https://",
    "s3://",
    "gs://",
    "bucket",
    "workspace/portfolio",
    "local://",
    "uri=",
    "handle=",
    ".dayu",
    "/Users/",
    "C:\\",
)


def _assert_no_leak(value: JsonValue | bytes, path: str) -> None:
    """递归扫描输出，确保不含路径/URI/bucket/handle 信号。"""

    if isinstance(value, str):
        lowered = value.lower()
        for pattern in _FORBIDDEN_PATTERNS:
            assert pattern not in lowered, f"{path} 泄漏 {pattern!r}: {value!r}"
        return
    if isinstance(value, bytes):
        _assert_no_leak(value.decode("utf-8", errors="ignore"), path)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_no_leak(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_no_leak(item, f"{path}[{index}]")
        return


@pytest.fixture()
def ctx() -> EvidenceRuntimeContext:
    """构建空 runtime 上下文。"""

    return build_evidence_runtime_context({})


def _happy_document_processed(
    ctx: EvidenceRuntimeContext,
) -> EvidenceLocatorProjection:
    """构建 document+processed happy 场景并返回 resolved projection。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[
            {"ref": "s_1", "title": "Overview", "level": 1, "parent_ref": None, "preview": "p"}
        ],
        tables=[
            {
                "table_ref": "t_1",
                "caption": None,
                "context_before": "",
                "row_count": 1,
                "col_count": 1,
                "table_type": "financial",
                "headers": ["A"],
                "section_ref": None,
            }
        ],
    )
    fragment = _probe_fragment_bytes(
        ctx,
        ticker="AAPL",
        document_id="doc_1",
        artifact_kind=ArtifactKind.PROCESSED,
        locator_kind=LocatorKind.DOCUMENT,
        locator_payload=DocumentLocatorPayload(),
        primary_bytes=_PRIMARY_BYTES,
    )
    runtime = _make_runtime(ctx)
    projection = runtime.resolve_evidence_locator(
        _build_request(
            primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
            locator_content_sha256=sha256_hex(fragment),
        )
    )
    return projection


@pytest.mark.unit
def test_resolve_document_source_happy(ctx: EvidenceRuntimeContext) -> None:
    """验证 document+source：fragment 为主文件 exact bytes。"""

    _seed_source(ctx, "doc_1", source_kind=SourceKind.FILING, primary_sha=sha256_hex(_PRIMARY_BYTES))
    runtime = _make_runtime(ctx)
    projection = runtime.resolve_evidence_locator(
        _build_request(
            artifact_kind=ArtifactKind.SOURCE,
            primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
            locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
        )
    )
    assert projection.artifact_kind is ArtifactKind.SOURCE
    assert projection.primary_content_sha256 == sha256_hex(_PRIMARY_BYTES)
    assert projection.locator_content_sha256 == sha256_hex(_PRIMARY_BYTES)
    citation = runtime.read_citation_projection(projection)
    assert citation.content_bytes == _PRIMARY_BYTES
    assert citation.content_type == "text/html"


@pytest.mark.unit
def test_resolve_document_processed_happy(ctx: EvidenceRuntimeContext) -> None:
    """验证 document+processed：fragment 只编码 sections/tables。"""

    projection = _happy_document_processed(ctx)
    assert projection.artifact_kind is ArtifactKind.PROCESSED
    assert projection.locator_kind is LocatorKind.DOCUMENT
    assert projection.repository_id == "dayu.fins.public.v1"
    assert projection.ticker == "AAPL"
    assert projection.document_id == "doc_1"
    assert projection.source_kind is SourceKind.FILING
    assert projection.document_version == "v1"
    assert projection.source_fingerprint == _FINGERPRINT
    assert projection.primary_content_sha256 == sha256_hex(_PRIMARY_BYTES)


@pytest.mark.unit
def test_resolve_page_happy(ctx: EvidenceRuntimeContext) -> None:
    """验证 page 定位器 happy path。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        page={
            "page_no": 1,
            "sections": [],
            "tables": [],
            "text_preview": "page text",
            "has_content": True,
            "total_items": 2,
            "supported": True,
        }
    )
    payload = PageLocatorPayload(page_no=1)
    fragment = _probe_fragment_bytes(
        ctx,
        ticker="AAPL",
        document_id="doc_1",
        artifact_kind=ArtifactKind.PROCESSED,
        locator_kind=LocatorKind.PAGE,
        locator_payload=payload,
        primary_bytes=_PRIMARY_BYTES,
    )
    runtime = _make_runtime(ctx)
    projection = runtime.resolve_evidence_locator(
        _build_request(
            primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
            locator_kind=LocatorKind.PAGE,
            locator_payload=payload,
            locator_content_sha256=sha256_hex(fragment),
        )
    )
    assert projection.locator_kind is LocatorKind.PAGE
    citation = runtime.read_citation_projection(projection)
    assert citation.content_bytes == fragment
    assert citation.content_type == "application/json"


@pytest.mark.unit
def test_resolve_page_unsupported_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 page 定位器 supported=false 拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        page={
            "page_no": 1,
            "sections": [],
            "tables": [],
            "text_preview": "",
            "has_content": False,
            "total_items": 0,
            "supported": False,
        }
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.PAGE,
                locator_payload=PageLocatorPayload(page_no=1),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "page_not_supported"


@pytest.mark.unit
def test_resolve_section_happy(ctx: EvidenceRuntimeContext) -> None:
    """验证 section 定位器 happy path。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[
            {"ref": "s_1", "title": "Overview", "level": 1, "parent_ref": None, "preview": "p"}
        ],
        section_by_ref={
            "s_1": {
                "ref": "s_1",
                "title": "Overview",
                "content": "section body",
                "tables": [],
                "word_count": 2,
                "contains_full_text": False,
            }
        },
    )
    payload = SectionLocatorPayload(section_ref="s_1")
    fragment = _probe_fragment_bytes(
        ctx,
        ticker="AAPL",
        document_id="doc_1",
        artifact_kind=ArtifactKind.PROCESSED,
        locator_kind=LocatorKind.SECTION,
        locator_payload=payload,
        primary_bytes=_PRIMARY_BYTES,
    )
    runtime = _make_runtime(ctx)
    projection = runtime.resolve_evidence_locator(
        _build_request(
            primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
            locator_kind=LocatorKind.SECTION,
            locator_payload=payload,
            locator_content_sha256=sha256_hex(fragment),
        )
    )
    assert projection.locator_kind is LocatorKind.SECTION


@pytest.mark.unit
def test_resolve_table_cell_happy(ctx: EvidenceRuntimeContext) -> None:
    """验证 table_cell records happy path。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        tables=[
            {
                "table_ref": "t_1",
                "caption": None,
                "context_before": "",
                "row_count": 1,
                "col_count": 1,
                "table_type": "financial",
                "headers": ["Revenue"],
                "section_ref": None,
            }
        ],
        table_by_ref={
            "t_1": {
                "table_ref": "t_1",
                "caption": None,
                "data_format": "records",
                "data": [{"Revenue": 100}],
                "columns": ["Revenue"],
                "row_count": 1,
                "col_count": 1,
                "section_ref": None,
                "table_type": "financial",
            }
        },
    )
    payload = TableCellLocatorPayload(table_ref="t_1", row_index=0, column="Revenue")
    fragment = _probe_fragment_bytes(
        ctx,
        ticker="AAPL",
        document_id="doc_1",
        artifact_kind=ArtifactKind.PROCESSED,
        locator_kind=LocatorKind.TABLE_CELL,
        locator_payload=payload,
        primary_bytes=_PRIMARY_BYTES,
    )
    runtime = _make_runtime(ctx)
    projection = runtime.resolve_evidence_locator(
        _build_request(
            primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
            locator_kind=LocatorKind.TABLE_CELL,
            locator_payload=payload,
            locator_content_sha256=sha256_hex(fragment),
        )
    )
    assert projection.locator_kind is LocatorKind.TABLE_CELL


@pytest.mark.unit
def test_resolve_table_cell_markdown_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 table_cell 对 markdown 表格拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        tables=[
            {
                "table_ref": "t_md",
                "caption": None,
                "context_before": "",
                "row_count": 1,
                "col_count": 1,
                "table_type": "text",
                "headers": None,
                "section_ref": None,
            }
        ],
        table_by_ref={
            "t_md": {
                "table_ref": "t_md",
                "caption": None,
                "data_format": "markdown",
                "data": "| A |\n|---|\n| 1 |",
                "columns": None,
                "row_count": 1,
                "col_count": 1,
                "section_ref": None,
                "table_type": "text",
            }
        },
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.TABLE_CELL,
                locator_payload=TableCellLocatorPayload(table_ref="t_md", row_index=0, column="A"),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "table_not_records"


@pytest.mark.unit
def test_resolve_table_cell_row_out_of_range(ctx: EvidenceRuntimeContext) -> None:
    """验证 table_cell 行越界拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        tables=[
            {
                "table_ref": "t_1",
                "caption": None,
                "context_before": "",
                "row_count": 1,
                "col_count": 1,
                "table_type": "financial",
                "headers": ["Revenue"],
                "section_ref": None,
            }
        ],
        table_by_ref={
            "t_1": {
                "table_ref": "t_1",
                "caption": None,
                "data_format": "records",
                "data": [{"Revenue": 100}],
                "columns": ["Revenue"],
                "row_count": 1,
                "col_count": 1,
                "section_ref": None,
                "table_type": "financial",
            }
        },
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.TABLE_CELL,
                locator_payload=TableCellLocatorPayload(table_ref="t_1", row_index=5, column="Revenue"),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "table_row_out_of_range"


@pytest.mark.unit
def test_resolve_table_cell_column_missing(ctx: EvidenceRuntimeContext) -> None:
    """验证 table_cell 缺列拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        tables=[
            {
                "table_ref": "t_1",
                "caption": None,
                "context_before": "",
                "row_count": 1,
                "col_count": 1,
                "table_type": "financial",
                "headers": ["Revenue"],
                "section_ref": None,
            }
        ],
        table_by_ref={
            "t_1": {
                "table_ref": "t_1",
                "caption": None,
                "data_format": "records",
                "data": [{"Revenue": 100}],
                "columns": ["Revenue"],
                "row_count": 1,
                "col_count": 1,
                "section_ref": None,
                "table_type": "financial",
            }
        },
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.TABLE_CELL,
                locator_payload=TableCellLocatorPayload(table_ref="t_1", row_index=0, column="Missing"),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "table_column_missing"


def _xbrl_fact(concept: str = "Revenue", **overrides: JsonValue) -> dict[str, JsonValue]:
    """构造规范化友好的 XBRL fact。"""

    fact: dict[str, JsonValue] = {
        "concept": concept,
        "label": "Revenue",
        "numeric_value": 123.0,
        "value": 123.0,
        "unit": "USD",
        "decimals": 0,
        "period_type": "duration",
        "period_start": "2024-01-01",
        "period_end": "2024-12-31",
        "fiscal_year": 2024,
        "fiscal_period": "FY",
        "statement_type": "income",
    }
    fact.update(overrides)
    return fact


def _xbrl_canonical_row_sha(fact: dict[str, JsonValue]) -> str:
    """计算单条 fact 的 canonical row SHA。"""

    row = {key: fact.get(key) for key in (
        "concept", "label", "numeric_value", "text_value", "content_type",
        "unit", "decimals", "period_type", "period_start", "period_end",
        "fiscal_year", "fiscal_period", "statement_type",
    )}
    return sha256_hex(canonical_json_bytes(row))


@pytest.mark.unit
def test_resolve_xbrl_fact_happy(ctx: EvidenceRuntimeContext) -> None:
    """验证 xbrl_fact 恰好一条 canonical row 匹配。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    fact = _xbrl_fact()
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        xbrl_facts=[fact],
    )
    payload = XbrlFactLocatorPayload(concept="Revenue", fact_sha256=_xbrl_canonical_row_sha(fact))
    fragment = _probe_fragment_bytes(
        ctx,
        ticker="AAPL",
        document_id="doc_1",
        artifact_kind=ArtifactKind.PROCESSED,
        locator_kind=LocatorKind.XBRL_FACT,
        locator_payload=payload,
        primary_bytes=_PRIMARY_BYTES,
    )
    runtime = _make_runtime(ctx)
    projection = runtime.resolve_evidence_locator(
        _build_request(
            primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
            locator_kind=LocatorKind.XBRL_FACT,
            locator_payload=payload,
            locator_content_sha256=sha256_hex(fragment),
        )
    )
    assert projection.locator_kind is LocatorKind.XBRL_FACT
    citation = runtime.read_citation_projection(projection)
    assert citation.content_bytes == fragment


@pytest.mark.unit
def test_resolve_xbrl_fact_zero_match(ctx: EvidenceRuntimeContext) -> None:
    """验证 xbrl_fact 0 条匹配拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    fact = _xbrl_fact()
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(xbrl_facts=[fact])
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.XBRL_FACT,
                locator_payload=XbrlFactLocatorPayload(concept="Revenue", fact_sha256="e" * 64),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "xbrl_fact_not_unique"


@pytest.mark.unit
def test_resolve_xbrl_fact_duplicate_match(ctx: EvidenceRuntimeContext) -> None:
    """验证 xbrl_fact 重复 canonical row 匹配拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    fact = _xbrl_fact()
    duplicate = _xbrl_fact(segment="a")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        xbrl_facts=[fact, duplicate],
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.XBRL_FACT,
                locator_payload=XbrlFactLocatorPayload(concept="Revenue", fact_sha256=_xbrl_canonical_row_sha(fact)),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "xbrl_fact_not_unique"


@pytest.mark.unit
def test_validate_and_read_happy(ctx: EvidenceRuntimeContext) -> None:
    """验证 validate/read 对一致 projection 通过且 citation SHA 闭合。"""

    projection = _happy_document_processed(ctx)
    runtime = _make_runtime(ctx)
    runtime.validate_evidence_locator(projection)
    citation = runtime.read_citation_projection(projection)
    assert isinstance(citation, CitationProjection)
    assert citation.locator == projection
    assert citation.content_type == "application/json"
    assert sha256_hex(citation.content_bytes) == projection.locator_content_sha256


@pytest.mark.unit
def test_resolve_rejects_mismatched_payload_type(ctx: EvidenceRuntimeContext) -> None:
    """验证 locator kind 与 payload 类型不匹配拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[{"ref": "s_1", "title": "T", "level": 1, "parent_ref": None, "preview": "p"}]
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.PAGE,
                locator_payload=SectionLocatorPayload(section_ref="s_1"),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "invalid_locator_payload"


@pytest.mark.unit
def test_resolve_section_missing_ref_wraps_read_failure(ctx: EvidenceRuntimeContext) -> None:
    """验证 tool 读取失败包装为 evidence_read_failed。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[{"ref": "s_1", "title": "T", "level": 1, "parent_ref": None, "preview": "p"}]
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.SECTION,
                locator_payload=SectionLocatorPayload(section_ref="s_missing"),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "evidence_read_failed"


@pytest.mark.unit
def test_processed_source_kind_key_missing_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 processed meta 完全缺失 source_kind 键拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processed_repository._meta[("AAPL", "doc_1")].pop("source_kind")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "processed_source_kind_mismatch"


@pytest.mark.unit
def test_validate_rejects_document_version_drift(ctx: EvidenceRuntimeContext) -> None:
    """验证 document_version 漂移拒绝。"""

    projection = _happy_document_processed(ctx)
    drifted = EvidenceLocatorProjection(
        repository_id=projection.repository_id,
        ticker=projection.ticker,
        document_id=projection.document_id,
        source_kind=projection.source_kind,
        artifact_kind=projection.artifact_kind,
        document_version="v2",
        source_fingerprint=projection.source_fingerprint,
        primary_content_sha256=projection.primary_content_sha256,
        locator_kind=projection.locator_kind,
        locator_payload=projection.locator_payload,
        locator_content_sha256=projection.locator_content_sha256,
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.validate_evidence_locator(drifted)
    assert excinfo.value.code == "document_version_mismatch"


@pytest.mark.unit
def test_validate_rejects_source_fingerprint_drift(ctx: EvidenceRuntimeContext) -> None:
    """验证 source_fingerprint 漂移拒绝。"""

    projection = _happy_document_processed(ctx)
    drifted = EvidenceLocatorProjection(
        repository_id=projection.repository_id,
        ticker=projection.ticker,
        document_id=projection.document_id,
        source_kind=projection.source_kind,
        artifact_kind=projection.artifact_kind,
        document_version=projection.document_version,
        source_fingerprint="d" * 64,
        primary_content_sha256=projection.primary_content_sha256,
        locator_kind=projection.locator_kind,
        locator_payload=projection.locator_payload,
        locator_content_sha256=projection.locator_content_sha256,
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.validate_evidence_locator(drifted)
    assert excinfo.value.code == "source_fingerprint_mismatch"


@pytest.mark.unit
def test_resolve_rejects_primary_sha_drift(ctx: EvidenceRuntimeContext) -> None:
    """验证 primary_content_sha256 与实算不一致拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256="d" * 64,
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "primary_content_sha256_mismatch"


@pytest.mark.unit
def test_resolve_rejects_locator_sha_drift(ctx: EvidenceRuntimeContext) -> None:
    """验证 locator_content_sha256 与实算 fragment 不一致拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[{"ref": "s_1", "title": "T", "level": 1, "parent_ref": None, "preview": "p"}]
    )
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="d" * 64,
            )
        )
    assert excinfo.value.code == "locator_content_sha256_mismatch"


@pytest.mark.unit
def test_meta_sha_optional_and_mismatch(ctx: EvidenceRuntimeContext) -> None:
    """验证 primary meta SHA 可选匹配与不匹配拒绝。"""

    _seed_source(ctx, "doc_1", primary_sha=None)
    runtime = _make_runtime(ctx)
    projection = runtime.resolve_evidence_locator(
        _build_request(
            artifact_kind=ArtifactKind.SOURCE,
            primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
            locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
        )
    )
    assert projection.primary_content_sha256 == sha256_hex(_PRIMARY_BYTES)

    _seed_source(ctx, "doc_2", primary_sha="d" * 64)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                document_id="doc_2",
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "primary_sha_mismatch"


@pytest.mark.unit
def test_source_deleted_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 source 逻辑删除拒绝。"""

    _seed_source(ctx, "doc_1", is_deleted=True)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "source_deleted"


@pytest.mark.unit
def test_source_not_ingested_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 source 未完成摄入拒绝。"""

    _seed_source(ctx, "doc_1", ingest_complete=False)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "source_not_ingested"


@pytest.mark.unit
def test_source_invalid_fingerprint_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 source 指纹非 lower-64-hex 拒绝。"""

    _seed_source(ctx, "doc_1", fingerprint="not-a-hash")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "invalid_source_fingerprint"


@pytest.mark.unit
def test_source_missing_version_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 source 缺失 document_version 拒绝。"""

    _seed_source(ctx, "doc_1", version="")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "invalid_document_version"


@pytest.mark.unit
def test_wrong_identity_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证不存在/错误身份拒绝。"""

    _seed_source(ctx, "doc_1")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                ticker="MSFT",
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "source_identity_not_found"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                document_id="missing",
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "source_identity_not_found"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                source_kind=SourceKind.MATERIAL,
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "source_identity_not_found"


@pytest.mark.unit
def test_dual_kind_collision_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证同 ticker/document_id 双 source kind 碰撞 fail closed。"""

    _seed_source(ctx, "doc_1", source_kind=SourceKind.FILING)
    _seed_source(ctx, "doc_1", source_kind=SourceKind.MATERIAL)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "ambiguous_source_identity"


@pytest.mark.unit
def test_shared_cache_stale_processor_not_used(ctx: EvidenceRuntimeContext) -> None:
    """验证 evidence 读取不复用共享 tool cache 的 stale processor。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[{"ref": "s_old", "title": "Old", "level": 1, "parent_ref": None, "preview": "p"}]
    )
    runtime = _make_runtime(ctx)
    shared = runtime.get_tool_service()
    shared.get_document_sections(ticker="AAPL", document_id="doc_1")
    calls_before = ctx.processor_registry.create_call_count
    assert calls_before == 1

    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[{"ref": "s_new", "title": "New", "level": 1, "parent_ref": None, "preview": "p"}]
    )
    fragment = _probe_fragment_bytes(
        ctx,
        ticker="AAPL",
        document_id="doc_1",
        artifact_kind=ArtifactKind.PROCESSED,
        locator_kind=LocatorKind.DOCUMENT,
        locator_payload=DocumentLocatorPayload(),
        primary_bytes=_PRIMARY_BYTES,
    )
    runtime.resolve_evidence_locator(
        _build_request(
            primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
            locator_content_sha256=sha256_hex(fragment),
        )
    )
    # 探针（1 次）与 request-scoped resolve（1 次）各新建 processor，共享 cache 不复用。
    assert ctx.processor_registry.create_call_count == calls_before + 2
    assert b"s_new" in fragment


@pytest.mark.unit
def test_pre_post_race_meta_change_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证读取期间 source meta 漂移（pre/post race）拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[{"ref": "s_1", "title": "T", "level": 1, "parent_ref": None, "preview": "p"}]
    )
    fragment = _probe_fragment_bytes(
        ctx,
        ticker="AAPL",
        document_id="doc_1",
        artifact_kind=ArtifactKind.PROCESSED,
        locator_kind=LocatorKind.DOCUMENT,
        locator_payload=DocumentLocatorPayload(),
        primary_bytes=_PRIMARY_BYTES,
    )

    def _mutate_on_create() -> None:
        ctx.source_repository.mutate_meta("AAPL", "doc_1", SourceKind.FILING, document_version="v2")

    ctx.processor_registry.create_hook = _mutate_on_create
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(fragment),
            )
        )
    assert excinfo.value.code == "source_identity_changed"


@pytest.mark.unit
def test_pre_post_race_primary_bytes_change_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证读取期间 primary bytes 漂移（pre/post race）拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[{"ref": "s_1", "title": "T", "level": 1, "parent_ref": None, "preview": "p"}]
    )
    fragment = _probe_fragment_bytes(
        ctx,
        ticker="AAPL",
        document_id="doc_1",
        artifact_kind=ArtifactKind.PROCESSED,
        locator_kind=LocatorKind.DOCUMENT,
        locator_payload=DocumentLocatorPayload(),
        primary_bytes=_PRIMARY_BYTES,
    )

    def _mutate_on_create() -> None:
        ctx.source_repository.replace_primary_bytes("AAPL", "doc_1", SourceKind.FILING, b"<changed>")

    ctx.processor_registry.create_hook = _mutate_on_create
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(fragment),
            )
        )
    assert excinfo.value.code == "primary_content_changed"


@pytest.mark.unit
def test_processed_missing_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 processed 缺失拒绝。"""

    _seed_source(ctx, "doc_1")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "processed_not_found"


@pytest.mark.unit
def test_processed_deleted_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 processed 逻辑删除拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1", is_deleted=True)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "processed_deleted"


@pytest.mark.unit
def test_processed_reprocess_required_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 processed 需要重处理拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1", reprocess_required=True)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "processed_reprocess_required"


@pytest.mark.unit
def test_processed_version_mismatch_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 processed source_document_version 与 source 不一致拒绝。"""

    _seed_source(ctx, "doc_1", version="v1")
    _seed_processed(ctx, "doc_1", version="v2")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "processed_version_mismatch"


@pytest.mark.unit
def test_processed_fingerprint_mismatch_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 processed source_fingerprint 与 source 不一致拒绝。"""

    _seed_source(ctx, "doc_1", fingerprint=_FINGERPRINT)
    _seed_processed(ctx, "doc_1", fingerprint="d" * 64)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "processed_fingerprint_mismatch"


@pytest.mark.unit
def test_processed_source_kind_mismatch_and_missing_rejected(ctx: EvidenceRuntimeContext) -> None:
    """验证 processed source_kind 不匹配与缺失拒绝。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1", source_kind="material")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "processed_source_kind_mismatch"

    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[{"ref": "s_1", "title": "T", "level": 1, "parent_ref": None, "preview": "p"}]
    )
    _seed_processed(ctx, "doc_2", source_kind="")
    _seed_source(ctx, "doc_2")
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                document_id="doc_2",
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "processed_source_kind_mismatch"


@pytest.mark.unit
def test_read_citation_output_no_path_leak(ctx: EvidenceRuntimeContext) -> None:
    """验证 resolve/read 输出递归不含路径/URI/bucket/handle。"""

    projection = _happy_document_processed(ctx)
    runtime = _make_runtime(ctx)
    citation = runtime.read_citation_projection(projection)
    _assert_no_leak(projection.to_json(), "projection.to_json")
    _assert_no_leak(citation.content_bytes, "citation.content_bytes")
    _assert_no_leak(
        {
            "content_type": citation.content_type,
            "locator_json": projection.to_json(),
        },
        "citation",
    )


@pytest.mark.unit
def test_resolve_rejects_direct_dto_unknown_schema_and_repository(ctx: EvidenceRuntimeContext) -> None:
    """验证 runtime resolve 对 direct-DTO 的 unknown schema/repository fail closed。"""

    _seed_source(ctx, "doc_1", source_kind=SourceKind.FILING)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            replace(
                _build_request(artifact_kind=ArtifactKind.SOURCE),
                schema_version="fins-evidence-locator-v2",
            )
        )
    assert excinfo.value.code == "unsupported_schema_version"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            replace(
                _build_request(artifact_kind=ArtifactKind.SOURCE),
                repository_id="untrusted.repo",
            )
        )
    assert excinfo.value.code == "unsupported_repository_id"


@pytest.mark.unit
def test_validate_and_read_reject_direct_dto_unknown_repository(ctx: EvidenceRuntimeContext) -> None:
    """验证 runtime validate/read 对 direct-DTO 的 unknown repository fail closed。"""

    _seed_source(ctx, "doc_1", source_kind=SourceKind.FILING)
    runtime = _make_runtime(ctx)
    projection = runtime.resolve_evidence_locator(
        _build_request(
            artifact_kind=ArtifactKind.SOURCE,
            primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
            locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
        )
    )
    drifted = replace(projection, repository_id="untrusted.repo")
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.validate_evidence_locator(drifted)
    assert excinfo.value.code == "unsupported_repository_id"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.read_citation_projection(drifted)
    assert excinfo.value.code == "unsupported_repository_id"


@pytest.mark.unit
def test_resolve_rejects_direct_dto_wrong_payload_type(ctx: EvidenceRuntimeContext) -> None:
    """验证 runtime resolve 对 direct-DTO 的 kind/payload 错配 fail closed。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            replace(
                _build_request(),
                locator_kind=LocatorKind.PAGE,
                locator_payload=SectionLocatorPayload(section_ref="s_1"),
            )
        )
    assert excinfo.value.code == "invalid_locator_payload"


def _build_projection_for(
    *,
    ticker: str = "AAPL",
    document_id: str = "doc_1",
    source_kind: SourceKind = SourceKind.FILING,
    artifact_kind: ArtifactKind = ArtifactKind.PROCESSED,
    locator_kind: LocatorKind = LocatorKind.DOCUMENT,
    locator_payload: LocatorPayload = DocumentLocatorPayload(),
) -> EvidenceLocatorProjection:
    """构造身份合法、hash 占位的投影。"""

    return EvidenceLocatorProjection(
        repository_id="dayu.fins.public.v1",
        ticker=ticker,
        document_id=document_id,
        source_kind=source_kind,
        artifact_kind=artifact_kind,
        document_version="v1",
        source_fingerprint=_FINGERPRINT,
        primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
        locator_kind=locator_kind,
        locator_payload=locator_payload,
        locator_content_sha256="0" * 64,
    )


@pytest.mark.parametrize(
    "source_kind,locator_kind,payload",
    [
        (SourceKind.MATERIAL, LocatorKind.DOCUMENT, DocumentLocatorPayload()),
        (SourceKind.MATERIAL, LocatorKind.PAGE, PageLocatorPayload(page_no=1)),
        (SourceKind.MATERIAL, LocatorKind.SECTION, SectionLocatorPayload(section_ref="s_1")),
        (
            SourceKind.MATERIAL,
            LocatorKind.TABLE_CELL,
            TableCellLocatorPayload(table_ref="t_1", row_index=0, column="A"),
        ),
        (
            SourceKind.MATERIAL,
            LocatorKind.XBRL_FACT,
            XbrlFactLocatorPayload(concept="Revenue", fact_sha256="d" * 64),
        ),
    ],
)
def test_deleted_filing_counterpart_ambiguous_all_kinds(
    ctx: EvidenceRuntimeContext,
    source_kind: SourceKind,
    locator_kind: LocatorKind,
    payload: LocatorPayload,
) -> None:
    """验证 deleted filing + active material 时五种 processed 投影全部歧义且不建 processor。"""

    _seed_source(ctx, "doc_1", source_kind=SourceKind.MATERIAL)
    _seed_source(ctx, "doc_1", source_kind=SourceKind.FILING, is_deleted=True)
    _seed_processed(ctx, "doc_1", source_kind="material")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.validate_evidence_locator(
            _build_projection_for(
                source_kind=source_kind,
                locator_kind=locator_kind,
                locator_payload=payload,
            )
        )
    assert excinfo.value.code == "ambiguous_source_identity"
    assert ctx.processor_registry.create_call_count == 0


@pytest.mark.parametrize(
    "source_kind,locator_kind,payload",
    [
        (SourceKind.FILING, LocatorKind.DOCUMENT, DocumentLocatorPayload()),
        (SourceKind.FILING, LocatorKind.PAGE, PageLocatorPayload(page_no=1)),
        (SourceKind.FILING, LocatorKind.SECTION, SectionLocatorPayload(section_ref="s_1")),
        (
            SourceKind.FILING,
            LocatorKind.TABLE_CELL,
            TableCellLocatorPayload(table_ref="t_1", row_index=0, column="A"),
        ),
        (
            SourceKind.FILING,
            LocatorKind.XBRL_FACT,
            XbrlFactLocatorPayload(concept="Revenue", fact_sha256="d" * 64),
        ),
    ],
)
def test_deleted_material_counterpart_ambiguous_all_kinds(
    ctx: EvidenceRuntimeContext,
    source_kind: SourceKind,
    locator_kind: LocatorKind,
    payload: LocatorPayload,
) -> None:
    """验证 deleted material + active filing 时五种 processed 投影全部歧义且不建 processor。"""

    _seed_source(ctx, "doc_1", source_kind=SourceKind.FILING)
    _seed_source(ctx, "doc_1", source_kind=SourceKind.MATERIAL, is_deleted=True)
    _seed_processed(ctx, "doc_1", source_kind="filing")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.read_citation_projection(
            _build_projection_for(
                source_kind=source_kind,
                locator_kind=locator_kind,
                locator_payload=payload,
            )
        )
    assert excinfo.value.code == "ambiguous_source_identity"
    assert ctx.processor_registry.create_call_count == 0


@pytest.mark.unit
def test_deleted_counterpart_ambiguous_on_resolve_and_read(ctx: EvidenceRuntimeContext) -> None:
    """验证 deleted counterpart 对 resolve 与 read 均歧义。"""

    _seed_source(ctx, "doc_1", source_kind=SourceKind.MATERIAL)
    _seed_source(ctx, "doc_1", source_kind=SourceKind.FILING, is_deleted=True)
    _seed_processed(ctx, "doc_1", source_kind="material")
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            replace(
                _build_request(source_kind=SourceKind.MATERIAL),
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code == "ambiguous_source_identity"
    assert ctx.processor_registry.create_call_count == 0
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.read_citation_projection(
            _build_projection_for(source_kind=SourceKind.MATERIAL)
        )
    assert excinfo.value.code == "ambiguous_source_identity"
    assert ctx.processor_registry.create_call_count == 0


@pytest.mark.unit
def test_primary_read_failed_when_primary_file_missing(ctx: EvidenceRuntimeContext) -> None:
    """验证 get_primary_file 的 FileNotFoundError 统一包装为 primary_read_failed。"""

    _seed_source(ctx, "doc_1", source_kind=SourceKind.FILING, primary_file_missing=True)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                artifact_kind=ArtifactKind.SOURCE,
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_content_sha256=sha256_hex(_PRIMARY_BYTES),
            )
        )
    assert excinfo.value.code == "primary_read_failed"


def _seed_processed_document(ctx: EvidenceRuntimeContext) -> None:
    """写入 document+processed 完整场景。"""

    _seed_source(ctx, "doc_1")
    _seed_processed(ctx, "doc_1")
    ctx.processor_registry._data["doc_1"] = EvidenceDocumentData(
        sections=[{"ref": "s_1", "title": "T", "level": 1, "parent_ref": None, "preview": "p"}],
        page={
            "page_no": 1,
            "sections": [],
            "tables": [],
            "text_preview": "text",
            "has_content": True,
            "total_items": 1,
            "supported": True,
        },
        tables=[
            {
                "table_ref": "t_1",
                "caption": None,
                "context_before": "",
                "row_count": 1,
                "col_count": 1,
                "table_type": "financial",
                "headers": ["A"],
                "section_ref": None,
            }
        ],
        table_by_ref={
            "t_1": {
                "table_ref": "t_1",
                "caption": None,
                "data_format": "records",
                "data": [{"A": 1}],
                "columns": ["A"],
                "row_count": 1,
                "col_count": 1,
                "section_ref": None,
                "table_type": "financial",
            }
        },
    )


@pytest.mark.parametrize("page_no", [True, 0, -1])
def test_resolve_rejects_bad_page_no(
    ctx: EvidenceRuntimeContext,
    page_no: int,
) -> None:
    """验证 bool/0/负 page_no 的 resolve 全部 fail closed 且不建 processor。"""

    _seed_processed_document(ctx)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.PAGE,
                locator_payload=PageLocatorPayload(page_no=page_no),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code in ("invalid_type", "invalid_format")
    assert ctx.processor_registry.create_call_count == 0


@pytest.mark.parametrize("row_index", [True, -1])
def test_resolve_rejects_bad_row_index(
    ctx: EvidenceRuntimeContext,
    row_index: int,
) -> None:
    """验证 bool/负 row_index 的 resolve 全部 fail closed 且不建 processor。"""

    _seed_processed_document(ctx)
    runtime = _make_runtime(ctx)
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.resolve_evidence_locator(
            _build_request(
                primary_content_sha256=sha256_hex(_PRIMARY_BYTES),
                locator_kind=LocatorKind.TABLE_CELL,
                locator_payload=TableCellLocatorPayload(table_ref="t_1", row_index=row_index, column="A"),
                locator_content_sha256="0" * 64,
            )
        )
    assert excinfo.value.code in ("invalid_type", "invalid_format")
    assert ctx.processor_registry.create_call_count == 0


@pytest.mark.unit
def test_validate_and_read_reject_bool_page_no(
    ctx: EvidenceRuntimeContext,
) -> None:
    """验证 validate/read 对 bool page_no 的 direct-DTO 投影 fail closed。"""

    _seed_processed_document(ctx)
    runtime = _make_runtime(ctx)
    projection = _build_projection_for(
        locator_kind=LocatorKind.PAGE,
        locator_payload=PageLocatorPayload(page_no=True),
    )
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.validate_evidence_locator(projection)
    assert excinfo.value.code == "invalid_type"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        runtime.read_citation_projection(projection)
    assert excinfo.value.code == "invalid_type"
    assert ctx.processor_registry.create_call_count == 0
