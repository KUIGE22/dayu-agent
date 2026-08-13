"""CN download workflow 单元测试。

覆盖 A4 的核心语义：主流程事件序列、完成态 fast skip、远端 fingerprint 变化但
PDF SHA 相同的只读 skip、PDF 中间态恢复，以及 overwrite ticker 级清理。
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO, Optional, TypeAlias

import pytest

from dayu.contracts.cancellation import CancelledError
from dayu.engine.processors.processor_registry import ProcessorRegistry
from dayu.fins.domain.document_models import (
    BatchToken,
    FileObjectMeta,
    FilingUpdateRequest,
    RejectedFilingArtifact,
    RejectedFilingArtifactUpsertRequest,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.source_sync import FinsWorkerSyncOutcome, FinsWorkerSyncRequest
from dayu.fins.pipelines.cn_download_models import (
    CN_PIPELINE_DOWNLOAD_VERSION,
    CnCompanyProfile,
    CnFiscalPeriod,
    CnReportCandidate,
    CnReportQuery,
    CnSourceProvider,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_download_pdf_gate import CnDownloadPdfGateProtocol, NoopCnDownloadPdfGate
from dayu.fins.pipelines.cn_download_protocols import CnPreparationGate
from dayu.fins.pipelines.cn_download_workflow import run_cn_download_stream_impl
from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.pipelines.docling_upload_service import build_cn_filing_ids
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.source_sync_runtime import (
    DefaultFinsWorkerSourceSyncRuntime,
    FinsSourceSyncDownloadPipelineProtocol,
)
from dayu.fins.storage import BatchingRepositoryProtocol, FilingMaintenanceRepositoryProtocol
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet
from dayu.fins.storage.fs_batching_repository import FsBatchingRepository
from tests.fins.storage_testkit import FsStorageTestContext, build_fs_storage_test_context

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_PDF_BYTES = b"%PDF-1.7\n" + b"0" * 2048
_DOCLING_BYTES = b'{"document": "ok"}'


@dataclass
class _FakeDiscoveryClient:
    """CN discovery fake。"""

    temp_dir: Path
    candidates: tuple[CnReportCandidate, ...]
    pdf_bytes: bytes = _PDF_BYTES
    download_calls: int = 0
    failed_source_ids: set[str] = field(default_factory=set)
    list_error: RuntimeError | None = None
    delete_pdf_before_return: bool = False

    def resolve_company(self, query: CnReportQuery) -> CnCompanyProfile:
        """返回固定公司元数据。"""

        return CnCompanyProfile(
            provider="cninfo",
            company_id="CNINFO:9900000600",
            company_name="贵州茅台",
            ticker=query.normalized_ticker,
        )

    def list_report_candidates(
        self,
        query: CnReportQuery,
        profile: CnCompanyProfile,
    ) -> tuple[CnReportCandidate, ...]:
        """返回测试候选。"""

        del query, profile
        if self.list_error is not None:
            raise self.list_error
        return self.candidates

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """写入临时 PDF 并返回下载资产。"""

        self.download_calls += 1
        if candidate.source_id in self.failed_source_ids:
            raise RuntimeError(f"download failed: {candidate.source_id}")
        path = self.temp_dir / f"{candidate.source_id}_{self.download_calls}.pdf"
        path.write_bytes(self.pdf_bytes)
        if self.delete_pdf_before_return:
            path.unlink()
        return DownloadedReportAsset(
            candidate=candidate,
            pdf_path=path,
            sha256=hashlib.sha256(self.pdf_bytes).hexdigest(),
            content_length=len(self.pdf_bytes),
            downloaded_at="2026-05-02T00:00:00+00:00",
        )


@dataclass
class _FakeConverter:
    """Docling 转换 fake。"""

    fail_once: bool = False
    calls: int = 0

    def __call__(self, raw_data: bytes, stream_name: str) -> bytes:
        """返回固定 Docling JSON。"""

        del raw_data, stream_name
        self.calls += 1
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("docling failed")
        return _DOCLING_BYTES


@dataclass
class _RecordingPdfGate(CnDownloadPdfGateProtocol):
    """记录 PDF 下载 gate 持有状态。"""

    active: bool = False
    enter_count: int = 0
    exit_count: int = 0

    def lease_for_provider(
        self,
        provider: CnSourceProvider,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AbstractContextManager[None]:
        """返回记录型 lease。"""

        del cancel_checker
        assert provider in {"cninfo", "hkexnews"}
        return _RecordingPdfGateLease(self)


@dataclass
class _RecordingPdfGateLease:
    """测试用 PDF gate lease。"""

    gate: _RecordingPdfGate

    def __enter__(self) -> None:
        """标记 gate 已进入。"""

        self.gate.active = True
        self.gate.enter_count += 1
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """标记 gate 已退出。"""

        del exc_type, exc, traceback
        self.gate.active = False
        self.gate.exit_count += 1


@dataclass
class _GateAwareConverter(_FakeConverter):
    """验证 Docling 转换不在 PDF 下载 gate 内执行。"""

    gate: _RecordingPdfGate = field(default_factory=_RecordingPdfGate)

    def __call__(self, raw_data: bytes, stream_name: str) -> bytes:
        """断言转换阶段没有持有 PDF 下载 gate。"""

        assert self.gate.active is False
        return super().__call__(raw_data, stream_name)


@dataclass
class _CountingMaintenanceRepository:
    """记录 clear 调用并委托真实维护仓储。"""

    delegate: FilingMaintenanceRepositoryProtocol
    cleared_tickers: list[str] = field(default_factory=list)

    def clear_filing_documents(self, ticker: str) -> None:
        """记录 ticker 级清理。"""

        self.cleared_tickers.append(ticker)
        self.delegate.clear_filing_documents(ticker)

    def load_download_rejection_registry(self, ticker: str) -> dict[str, dict[str, str]]:
        """委托读取下载拒绝注册表。"""

        return self.delegate.load_download_rejection_registry(ticker)

    def save_download_rejection_registry(
        self,
        ticker: str,
        registry: dict[str, dict[str, str]],
    ) -> None:
        """委托保存下载拒绝注册表。"""

        self.delegate.save_download_rejection_registry(ticker, registry)

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
        """委托写入 rejected filing 文件。"""

        return self.delegate.store_rejected_filing_file(
            ticker,
            document_id,
            filename,
            data,
            content_type=content_type,
            metadata=metadata,
        )

    def upsert_rejected_filing_artifact(
        self,
        req: RejectedFilingArtifactUpsertRequest,
    ) -> RejectedFilingArtifact:
        """委托写入 rejected filing artifact。"""

        return self.delegate.upsert_rejected_filing_artifact(req)

    def get_rejected_filing_artifact(
        self,
        ticker: str,
        document_id: str,
    ) -> RejectedFilingArtifact:
        """委托读取 rejected filing artifact。"""

        return self.delegate.get_rejected_filing_artifact(ticker, document_id)

    def list_rejected_filing_artifacts(self, ticker: str) -> list[RejectedFilingArtifact]:
        """委托列出 rejected filing artifacts。"""

        return self.delegate.list_rejected_filing_artifacts(ticker)

    def read_rejected_filing_file_bytes(
        self,
        ticker: str,
        document_id: str,
        filename: str,
    ) -> bytes:
        """委托读取 rejected filing 文件。"""

        return self.delegate.read_rejected_filing_file_bytes(ticker, document_id, filename)

    def cleanup_stale_filing_documents(
        self,
        ticker: str,
        *,
        active_form_types: set[str],
        valid_document_ids: set[str],
    ) -> int:
        """委托清理 stale filing。"""

        return self.delegate.cleanup_stale_filing_documents(
            ticker,
            active_form_types=active_form_types,
            valid_document_ids=valid_document_ids,
        )


def _candidate(
    *,
    source_id: str = "A1",
    etag: str = '"v1"',
    fiscal_year: int = 2024,
    fiscal_period: CnFiscalPeriod = "FY",
    filing_date: str | None = None,
) -> CnReportCandidate:
    """构造 CN 候选。"""

    return CnReportCandidate(
        provider="cninfo",
        source_id=source_id,
        source_url=f"https://static.cninfo.test/{source_id}.pdf",
        title=f"贵州茅台：{fiscal_year}年{fiscal_period}报告",
        language="zh",
        filing_date=filing_date or f"{fiscal_year + 1}-04-01",
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        amended=False,
        content_length=len(_PDF_BYTES),
        etag=etag,
        last_modified="Wed, 01 Apr 2026 00:00:00 GMT",
    )


def _build_pipeline(
    *,
    tmp_path: Path,
    discovery: _FakeDiscoveryClient,
    converter: _FakeConverter,
    maintenance: FilingMaintenanceRepositoryProtocol | None = None,
    pdf_download_gate: CnDownloadPdfGateProtocol | None = None,
    batching_repository: BatchingRepositoryProtocol | None = None,
    preparation_gate: CnPreparationGate | None = None,
    context: FsStorageTestContext | None = None,
) -> CnPipeline:
    """构造注入 fake downloader / converter 的 CnPipeline。

    Args:
        tmp_path: workspace 根目录。
        discovery: fake discovery。
        converter: fake converter。
        maintenance: 可选 maintenance 仓储。
        pdf_download_gate: 可选 PDF 下载 gate。
        batching_repository: 可选同-core batch 仓储。
        preparation_gate: 可选共享 preparation gate。
        context: 可选测试仓储上下文；传入时复用其仓储（同 core），避免
            与 batching_repository 的 core 冲突。
    """

    if context is None:
        context = build_fs_storage_test_context(tmp_path)
    return CnPipeline(
        workspace_root=tmp_path,
        processor_registry=ProcessorRegistry(),
        company_repository=context.company_repository,
        source_repository=context.source_repository,
        processed_repository=context.processed_repository,
        blob_repository=context.blob_repository,
        filing_maintenance_repository=maintenance or context.filing_maintenance_repository,
        cn_discovery_client=discovery,
        pdf_download_gate=pdf_download_gate or NoopCnDownloadPdfGate(),
        convert_pdf_to_docling_json=converter,
        batching_repository=batching_repository,
        preparation_gate=preparation_gate,
    )


def _seed_staged_cn_download_state(
    *,
    tmp_path: Path,
    discovery: _FakeDiscoveryClient,
    candidate: CnReportCandidate,
    pdf_bytes: bytes = _PDF_BYTES,
    docling_bytes: bytes | None = None,
) -> str:
    """模拟阶段 C 中途 crash 的 staging state（S14-CTRL-12 crash-mid-stage-C）。

    Args:
        tmp_path: workspace 根目录。
        discovery: fake discovery（用于远端 fingerprint）。
        candidate: 当前候选。
        pdf_bytes: 已落盘 PDF 字节。
        docling_bytes: 已落盘 Docling JSON 字节（可选）。

    Returns:
        构造的 document_id。
    """

    from dayu.fins.domain.document_models import FilingCreateRequest
    from dayu.fins.pipelines.cn_download_source_upsert import build_remote_fingerprint

    context = build_fs_storage_test_context(tmp_path)
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type=candidate.fiscal_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.fiscal_period,
        amended=candidate.amended,
    )[0]
    remote_fingerprint = build_remote_fingerprint(candidate)
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    context.source_repository.create_source_document(
        FilingCreateRequest(
            ticker="600519",
            document_id=document_id,
            internal_document_id=f"cn_seed_{document_id}",
            form_type=candidate.fiscal_period,
            primary_document=f"{document_id}.pdf",
            file_entries=[],
            meta={
                "ingest_complete": False,
                "staging_remote_fingerprint": remote_fingerprint,
                "staging_pdf_sha256": pdf_sha256,
                "remote_fingerprint": remote_fingerprint,
            },
        ),
        source_kind=SourceKind.FILING,
    )
    handle = context.source_repository.get_source_handle("600519", document_id, SourceKind.FILING)
    pdf_meta = context.blob_repository.store_file(
        handle,
        f"{document_id}.pdf",
        BytesIO(pdf_bytes),
        content_type="application/pdf",
        metadata={"source": "original"},
    )
    entries: list[dict[str, str | int | None]] = [
        {
            "name": f"{document_id}.pdf",
            "uri": pdf_meta.uri,
            "etag": pdf_meta.etag,
            "last_modified": pdf_meta.last_modified,
            "size": pdf_meta.size,
            "content_type": pdf_meta.content_type,
            "sha256": pdf_meta.sha256,
            "source": "original",
        }
    ]
    if docling_bytes is not None:
        docling_meta = context.blob_repository.store_file(
            handle,
            f"{document_id}_docling.json",
            BytesIO(docling_bytes),
            content_type="application/json",
            metadata={"source": "docling", "pdf_sha256": pdf_sha256},
        )
        entries.append(
            {
                "name": f"{document_id}_docling.json",
                "uri": docling_meta.uri,
                "etag": docling_meta.etag,
                "last_modified": docling_meta.last_modified,
                "size": docling_meta.size,
                "content_type": docling_meta.content_type,
                "sha256": docling_meta.sha256,
                "source": "docling",
            }
        )
    context.source_repository.update_source_document(
        FilingUpdateRequest(
            ticker="600519",
            document_id=document_id,
            internal_document_id=f"cn_seed_{document_id}",
            form_type=candidate.fiscal_period,
            primary_document=f"{document_id}.pdf",
            file_entries=entries,
            meta={
                "ingest_complete": False,
                "staging_remote_fingerprint": remote_fingerprint,
                "staging_pdf_sha256": pdf_sha256,
                "remote_fingerprint": remote_fingerprint,
            },
        ),
        source_kind=SourceKind.FILING,
    )
    return document_id


def _collect_events(
    pipeline: CnPipeline,
    *,
    overwrite: bool = False,
    form_type: str = "FY",
    cancel_checker: Callable[[], bool] | None = None,
) -> list[DownloadEvent]:
    """同步收集 download_stream 事件。"""

    async def collect() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []
        async for event in pipeline.download_stream(
            ticker="600519",
            form_type=form_type,
            start_date="2024",
            end_date="2026",
            overwrite=overwrite,
            cancel_checker=cancel_checker,
        ):
            events.append(event)
        return events

    return asyncio.run(collect())


def _final_result(events: list[DownloadEvent]) -> JsonObject:
    """读取最终 pipeline result。"""

    payload = events[-1].payload.get("result")
    assert isinstance(payload, dict)
    return {str(key): value for key, value in payload.items()}


class _TrackedCnFilingStream(AsyncGenerator[DownloadEvent, None]):
    def __init__(self, events: list[DownloadEvent], *, error: BaseException | None = None) -> None:
        self.events = iter(events)
        self.error = error
        self.error_raised = False
        self.aclose_calls = 0

    def __aiter__(self) -> _TrackedCnFilingStream:
        return self

    async def __anext__(self) -> DownloadEvent:
        try:
            return next(self.events)
        except StopIteration:
            if self.error is not None and not self.error_raised:
                self.error_raised = True
                raise self.error
            raise StopAsyncIteration

    async def asend(self, value: None) -> DownloadEvent:
        return await self.__anext__()

    async def athrow(self, *args: Any) -> DownloadEvent:
        raise StopAsyncIteration

    async def aclose(self) -> None:
        self.aclose_calls += 1


class _RecordingCnBatching:
    """记录调用并委托同 core 真实 FS batching repository。"""

    def __init__(self, real: FsBatchingRepository) -> None:
        """保存真实 repository 并初始化调用记录。

        Args:
            real: 同 core 真实 FS batching repository。

        Returns:
            无。

        Raises:
            无。
        """

        self.real = real
        self.begin_calls: list[str] = []
        self.commit_calls: list[str] = []
        self.rollback_calls: list[str] = []

    def begin_batch(self, ticker: str) -> BatchToken:
        """记录并委托 batch 开启。

        Args:
            ticker: 规范股票代码。

        Returns:
            真实 batch token。

        Raises:
            Exception: 真实 repository 开启失败时原样抛出。
        """

        self.begin_calls.append(ticker)
        return self.real.begin_batch(ticker)

    def commit_batch(self, token: BatchToken) -> None:
        """记录并委托 batch 提交。

        Args:
            token: 当前真实 batch token。

        Returns:
            无。

        Raises:
            Exception: 真实 repository 提交失败时原样抛出。
        """

        self.commit_calls.append(token.ticker)
        self.real.commit_batch(token)

    def rollback_batch(self, token: BatchToken) -> None:
        """记录并委托 batch 回滚。

        Args:
            token: 当前真实 batch token。

        Returns:
            无。

        Raises:
            Exception: 真实 repository 回滚失败时原样抛出。
        """

        self.rollback_calls.append(token.ticker)
        self.real.rollback_batch(token)

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """委托孤儿 batch 恢复。

        Args:
            dry_run: 是否只预览恢复动作。

        Returns:
            真实 repository 的恢复摘要。

        Raises:
            Exception: 真实 repository 恢复失败时原样抛出。
        """

        return self.real.recover_orphan_batches(dry_run=dry_run)


class _DirectCnFilingOwnerSpy(AsyncGenerator[DownloadEvent, None]):
    """包装真实 filing stream 并记录 market owner 的直接关闭次数。"""

    def __init__(self, inner: AsyncGenerator[DownloadEvent, None]) -> None:
        """保存真实 inner stream。

        Args:
            inner: 真实 CN filing stream。

        Returns:
            无。

        Raises:
            无。
        """

        self.inner = inner
        self.aclose_calls = 0

    def __aiter__(self) -> _DirectCnFilingOwnerSpy:
        """返回自身异步迭代器。

        Args:
            无。

        Returns:
            当前 spy。

        Raises:
            无。
        """

        return self

    async def __anext__(self) -> DownloadEvent:
        """委托取得下一真实事件。

        Args:
            无。

        Returns:
            下一真实下载事件。

        Raises:
            BaseException: inner 迭代结果原样传播。
        """

        return await self.inner.__anext__()

    async def asend(self, value: None) -> DownloadEvent:
        """委托向真实 inner 发送空值。

        Args:
            value: async-generator 协议空值。

        Returns:
            下一真实下载事件。

        Raises:
            BaseException: inner 结果原样传播。
        """

        return await self.inner.asend(value)

    async def athrow(self, *args: Any) -> DownloadEvent:
        """委托向真实 inner 注入异常。

        Args:
            args: async-generator ``athrow`` 参数。

        Returns:
            inner 恢复后产生的下载事件。

        Raises:
            BaseException: inner 结果原样传播。
        """

        return await self.inner.athrow(*args)

    async def aclose(self) -> None:
        """记录并直接关闭真实 inner 恰好一次。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: inner 关闭失败时原样传播。
        """

        self.aclose_calls += 1
        await self.inner.aclose()


class _CnReplayPipeline:
    """把真实 CN producer 事件原序重放给 source-sync consumer。"""

    def __init__(self, events: list[DownloadEvent]) -> None:
        """保存待重放事件。

        Args:
            events: 真实 producer 产生的事件序列。

        Returns:
            无。

        Raises:
            无。
        """

        self.events = events

    def download_stream(
        self,
        ticker: str,
        form_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        overwrite: bool = False,
        rebuild: bool = False,
        ticker_aliases: list[str] | None = None,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AsyncGenerator[DownloadEvent, None]:
        """返回真实事件序列的可关闭重放流。

        Args:
            ticker: consumer 请求 ticker。
            form_type: consumer 请求 form。
            start_date: consumer 请求窗口起点。
            end_date: consumer 请求窗口终点。
            overwrite: consumer 覆盖标记。
            rebuild: consumer rebuild 标记。
            ticker_aliases: consumer ticker aliases。
            cancel_checker: consumer 取消检查器。

        Yields:
            原序真实下载事件。

        Raises:
            无。
        """

        del ticker, form_type, start_date, end_date, overwrite, rebuild, ticker_aliases, cancel_checker

        async def replay() -> AsyncGenerator[DownloadEvent, None]:
            """逐项重放真实 producer 事件。

            Args:
                无。

            Yields:
                原序真实下载事件。

            Raises:
                无。
            """

            for event in self.events:
                yield event

        return replay()


class _CnReplayFactory:
    """始终返回同一 CN 重放 pipeline 的测试工厂。"""

    def __init__(self, pipeline: _CnReplayPipeline) -> None:
        """保存重放 pipeline。

        Args:
            pipeline: 待返回重放 pipeline。

        Returns:
            无。

        Raises:
            无。
        """

        self.pipeline = pipeline

    def build_source_sync_pipeline(self, ticker: str) -> FinsSourceSyncDownloadPipelineProtocol:
        """返回已保存 pipeline。

        Args:
            ticker: consumer 请求 ticker。

        Returns:
            已保存重放 pipeline。

        Raises:
            无。
        """

        del ticker
        return self.pipeline


def _cn_market_stream(pipeline: CnPipeline) -> AsyncGenerator[DownloadEvent, None]:
    return run_cn_download_stream_impl(
        pipeline,
        ticker="600519",
        form_type="FY",
        start_date="2024",
        end_date="2026",
        overwrite=False,
        rebuild=False,
        ticker_aliases=None,
        cancel_checker=None,
        module="TEST.CN.CLOSE",
        pipeline_name="cn",
    )


@pytest.mark.asyncio
async def test_cn_market_workflow_closes_per_filing_stream_once_on_cancel_error_and_outer_aclose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dayu.fins.pipelines import cn_download_workflow as module

    cases: tuple[BaseException | None, ...] = (
        None,
        RuntimeError("boom"),
        CancelledError("cancel"),
        asyncio.CancelledError(),
    )
    for index, error in enumerate(cases):
        root = tmp_path / f"case-{index}"
        pipeline = _build_pipeline(
            tmp_path=root,
            discovery=_FakeDiscoveryClient(temp_dir=root, candidates=(_candidate(),)),
            converter=_FakeConverter(),
        )
        terminal = DownloadEvent(
            event_type=DownloadEventType.FILING_COMPLETED,
            ticker="600519",
            document_id="fil_cn_1",
            payload={"filing_result": {"document_id": "fil_cn_1", "status": "downloaded"}},
        )
        tracked = _TrackedCnFilingStream([] if error is not None else [terminal], error=error)
        monkeypatch.setattr(module, "run_cn_download_single_filing_stream", lambda **kwargs: tracked)
        if isinstance(error, asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):
                async for _ in _cn_market_stream(pipeline):
                    pass
        else:
            async for _ in _cn_market_stream(pipeline):
                pass
        assert tracked.aclose_calls == 1

    root = tmp_path / "outer-close"
    pipeline = _build_pipeline(
        tmp_path=root,
        discovery=_FakeDiscoveryClient(temp_dir=root, candidates=(_candidate(),)),
        converter=_FakeConverter(),
    )
    file_event = DownloadEvent(
        event_type=DownloadEventType.FILE_DOWNLOADED,
        ticker="600519",
        document_id="fil_cn_1",
    )
    tracked = _TrackedCnFilingStream([file_event])
    monkeypatch.setattr(module, "run_cn_download_single_filing_stream", lambda **kwargs: tracked)
    outer = _cn_market_stream(pipeline)
    while (await anext(outer)).event_type is not DownloadEventType.FILE_DOWNLOADED:
        pass
    await outer.aclose()
    assert tracked.aclose_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("task_cancel", (False, True))
async def test_cn_market_outer_close_and_task_cancel_release_real_fs_batch_and_direct_inner_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    task_cancel: bool,
) -> None:
    """CN market owner 关闭真实 filing inner 后不遗留 token、staging 或发布。"""

    from dayu.fins.pipelines import cn_download_workflow as module

    context = build_fs_storage_test_context(tmp_path)
    real_batching = FsBatchingRepository(
        tmp_path,
        repository_set=_FsRepositorySet(core=context.core),
    )
    batching = _RecordingCnBatching(real_batching)
    candidate = _candidate(source_id="CNINFO-A1")
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=(candidate,)),
        converter=_FakeConverter(),
        batching_repository=batching,
        preparation_gate=CnPreparationGate(capacity=1),
        context=context,
    )
    real_filing_stream = module.run_cn_download_single_filing_stream
    owned: list[_DirectCnFilingOwnerSpy] = []

    def build_owned_stream(**kwargs: Any) -> AsyncGenerator[DownloadEvent, None]:
        """包装真实 filing stream 并暴露 direct-close 计数。

        Args:
            kwargs: 原生产函数关键字参数。

        Returns:
            direct-close 记录型真实 filing stream。

        Raises:
            无。
        """

        spy = _DirectCnFilingOwnerSpy(real_filing_stream(**kwargs))
        owned.append(spy)
        return spy

    monkeypatch.setattr(module, "run_cn_download_single_filing_stream", build_owned_stream)
    outer = _cn_market_stream(pipeline)
    if task_cancel:
        ready = asyncio.Event()

        async def consume() -> None:
            """消费到 batch 内事件后等待 task 取消并关闭直接 owned outer。

            Args:
                无。

            Returns:
                无。

            Raises:
                asyncio.CancelledError: 测试 task 被取消时原样抛出。
            """

            try:
                async for event in outer:
                    if event.event_type is DownloadEventType.FILE_DOWNLOADED:
                        ready.set()
                        await asyncio.Event().wait()
            finally:
                await outer.aclose()

        task = asyncio.create_task(consume())
        await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        while (await anext(outer)).event_type is not DownloadEventType.FILE_DOWNLOADED:
            pass
        await outer.aclose()

    assert len(owned) == 1 and owned[0].aclose_calls == 1
    assert batching.begin_calls == ["600519"]
    assert batching.rollback_calls == ["600519"]
    assert batching.commit_calls == []
    assert context.core._active_batches == {}
    assert not context.core.batch_root.exists() or list(context.core.batch_root.iterdir()) == []
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )[0]
    with pytest.raises(FileNotFoundError):
        context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    recovery = real_batching.begin_batch("600519")
    real_batching.rollback_batch(recovery)


def test_cn_download_workflow_commits_pdf_and_docling(tmp_path: Path) -> None:
    """主流程应按事件序列完成 PDF + Docling + ingest_complete commit。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    events = _collect_events(pipeline)

    assert [event.event_type for event in events] == [
        DownloadEventType.PIPELINE_STARTED,
        DownloadEventType.COMPANY_RESOLVED,
        DownloadEventType.FILING_STARTED,
        DownloadEventType.FILE_DOWNLOADED,
        DownloadEventType.FILING_COMPLETED,
        DownloadEventType.PIPELINE_COMPLETED,
    ]
    result = _final_result(events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["downloaded"] == 1
    assert summary["converted"] == 1
    assert discovery.download_calls == 1
    assert converter.calls == 1
    started = [event for event in events if event.event_type == DownloadEventType.FILING_STARTED]
    completed = [event for event in events if event.event_type == DownloadEventType.FILING_COMPLETED]
    company_info = result["company_info"]
    assert isinstance(company_info, dict)
    assert company_info["company_id"] == "600519_SSE"
    assert company_info["provider_company_id"] == "CNINFO:9900000600"
    company_meta = pipeline._company_repository.get_company_meta("600519")  # type: ignore[attr-defined]
    assert company_meta.company_id == "600519_SSE"
    document_id, _ = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    source_meta = pipeline._source_repository.get_source_meta("600519", document_id, SourceKind.FILING)  # type: ignore[attr-defined]
    assert started[-1].document_id == document_id
    assert completed[-1].document_id == document_id
    assert source_meta["company_id"] == "600519_SSE"
    assert source_meta["provider_company_id"] == "CNINFO:9900000600"
    assert source_meta["document_version"] == "v1"


def test_real_cn_producer_source_id_flows_through_source_sync_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 CN producer 的 fiscal/source identity 可由 runtime 完整关联。"""

    candidate = _candidate(source_id="CNINFO-A1")
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=(candidate,)),
        converter=_FakeConverter(),
    )
    events = _collect_events(pipeline)
    started = next(event for event in events if event.event_type is DownloadEventType.FILING_STARTED)
    terminal = next(event for event in events if event.event_type is DownloadEventType.FILING_COMPLETED)
    terminal_filing = terminal.payload["filing_result"]
    result_filings = _final_result(events)["filings"]
    assert isinstance(terminal_filing, dict)
    assert isinstance(result_filings, list) and result_filings
    result_filing = result_filings[0]
    assert isinstance(result_filing, dict)
    for field_name in ("fiscal_year", "fiscal_period", "source_id"):
        assert terminal.payload[field_name] == started.payload[field_name]
        assert terminal_filing[field_name] == started.payload[field_name]
        assert result_filing[field_name] == started.payload[field_name]

    locator_owner = DefaultFinsRuntime.create(workspace_root=tmp_path)
    runtime = DefaultFinsWorkerSourceSyncRuntime(
        pipeline_factory=_CnReplayFactory(_CnReplayPipeline(events)),
        source_repository=locator_owner.source_repository,
        evidence_locator_owner=locator_owner,
    )
    sync_result = asyncio.run(
        runtime.sync_worker_source(
            FinsWorkerSyncRequest(
                ticker="600519",
                exchange_mic="XSHG",
                forms=("FY",),
                start_date=date(2024, 1, 1),
                end_date=date(2026, 12, 31),
                max_documents=5,
                max_events=50,
            ),
            cancel_checker=lambda: False,
        )
    )
    assert sync_result.outcome is FinsWorkerSyncOutcome.COMPLETE
    assert sync_result.downloaded_count == 1

    fast_skip_events = _collect_events(pipeline)
    fast_skip_terminal = next(
        event for event in fast_skip_events if event.event_type is DownloadEventType.FILING_COMPLETED
    )
    fast_skip_nested = fast_skip_terminal.payload["filing_result"]
    fast_skip_filings = _final_result(fast_skip_events)["filings"]
    assert isinstance(fast_skip_nested, dict)
    assert isinstance(fast_skip_filings, list) and fast_skip_filings == [fast_skip_nested]
    assert fast_skip_nested["reason_code"] == "remote_fingerprint_matched"
    assert fast_skip_nested["source_id"] == candidate.source_id
    fast_skip_result = asyncio.run(
        DefaultFinsWorkerSourceSyncRuntime(
            pipeline_factory=_CnReplayFactory(_CnReplayPipeline(fast_skip_events)),
            source_repository=locator_owner.source_repository,
            evidence_locator_owner=locator_owner,
        ).sync_worker_source(
            FinsWorkerSyncRequest(
                ticker="600519",
                exchange_mic="XSHG",
                forms=("FY",),
                start_date=date(2024, 1, 1),
                end_date=date(2026, 12, 31),
                max_documents=5,
                max_events=50,
            ),
            cancel_checker=lambda: False,
        )
    )
    assert fast_skip_result.outcome is FinsWorkerSyncOutcome.COMPLETE
    assert fast_skip_result.reused_count == 1

    missing_root = tmp_path / "missing"
    missing_pipeline = _build_pipeline(
        tmp_path=missing_root,
        discovery=_FakeDiscoveryClient(temp_dir=missing_root, candidates=()),
        converter=_FakeConverter(),
    )
    missing_events = _collect_events(missing_pipeline)
    missing_terminal = next(
        event for event in missing_events if event.event_type is DownloadEventType.FILING_COMPLETED
    )
    assert missing_terminal.payload["reason_code"] == "candidate_not_found"
    missing_locator_owner = DefaultFinsRuntime.create(workspace_root=missing_root)
    missing_result = asyncio.run(
        DefaultFinsWorkerSourceSyncRuntime(
            pipeline_factory=_CnReplayFactory(_CnReplayPipeline(missing_events)),
            source_repository=missing_locator_owner.source_repository,
            evidence_locator_owner=missing_locator_owner,
        ).sync_worker_source(
            FinsWorkerSyncRequest(
                ticker="600519",
                exchange_mic="XSHG",
                forms=("FY",),
                start_date=date(2024, 1, 1),
                end_date=date(2026, 12, 31),
                max_documents=5,
                max_events=50,
            ),
            cancel_checker=lambda: False,
        )
    )
    assert missing_result.outcome is FinsWorkerSyncOutcome.COMPLETE
    assert missing_result.ignored_count == 1

    from dayu.fins.pipelines import cn_download_workflow as workflow_module

    async def failing_filing_stream() -> AsyncGenerator[DownloadEvent, None]:
        """在真实 market owner 内触发 outer candidate-failure builder。

        Args:
            无。

        Yields:
            不产生事件。

        Raises:
            RuntimeError: 每次迭代均抛出固定 provider 错误。
        """

        if False:
            yield DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="600519")
        raise RuntimeError("outer candidate failure")

    monkeypatch.setattr(
        workflow_module,
        "run_cn_download_single_filing_stream",
        lambda **kwargs: failing_filing_stream(),
    )
    failed_root = tmp_path / "failed"
    failed_pipeline = _build_pipeline(
        tmp_path=failed_root,
        discovery=_FakeDiscoveryClient(temp_dir=failed_root, candidates=(candidate,)),
        converter=_FakeConverter(),
    )
    failed_events = _collect_events(failed_pipeline)
    failed_terminal = next(
        event for event in failed_events if event.event_type is DownloadEventType.FILING_FAILED
    )
    failed_nested = failed_terminal.payload["filing_result"]
    failed_filings = _final_result(failed_events)["filings"]
    assert isinstance(failed_nested, dict)
    assert isinstance(failed_filings, list) and failed_filings == [failed_nested]
    assert failed_nested["source_id"] == candidate.source_id
    failed_locator_owner = DefaultFinsRuntime.create(workspace_root=failed_root)
    failed_result = asyncio.run(
        DefaultFinsWorkerSourceSyncRuntime(
            pipeline_factory=_CnReplayFactory(_CnReplayPipeline(failed_events)),
            source_repository=failed_locator_owner.source_repository,
            evidence_locator_owner=failed_locator_owner,
        ).sync_worker_source(
            FinsWorkerSyncRequest(
                ticker="600519",
                exchange_mic="XSHG",
                forms=("FY",),
                start_date=date(2024, 1, 1),
                end_date=date(2026, 12, 31),
                max_documents=5,
                max_events=50,
            ),
            cancel_checker=lambda: False,
        )
    )
    assert failed_result.outcome is FinsWorkerSyncOutcome.UNAVAILABLE
    assert failed_result.failed_count == 1


def test_cn_download_pdf_gate_does_not_cover_docling_convert(tmp_path: Path) -> None:
    """PDF 下载 gate 只应覆盖远端 PDF 下载，不应覆盖 Docling 转换。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    gate = _RecordingPdfGate()
    converter = _GateAwareConverter(gate=gate)
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=discovery,
        converter=converter,
        pdf_download_gate=gate,
    )

    result = _final_result(_collect_events(pipeline))

    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["downloaded"] == 1
    assert summary["converted"] == 1
    assert gate.enter_count == 1
    assert gate.exit_count == 1
    assert gate.active is False
    assert converter.calls == 1


def test_cn_download_logs_match_sec_download_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CN download 应输出与 SEC download 对齐的入口和 filing 终态日志。"""

    info_logs: list[str] = []

    def capture_info(message: str, *, module: str) -> None:
        """捕获 ``Log.info`` 消息。"""

        info_logs.append(f"{module} {message}")

    monkeypatch.setattr(
        "dayu.fins.pipelines.cn_download_workflow.Log.info",
        capture_info,
    )
    monkeypatch.setattr(
        "dayu.fins.pipelines.cn_download_filing_workflow.Log.info",
        capture_info,
    )
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    _collect_events(pipeline)

    assert any("FINS.CN_PIPELINE 进入CN/HK下载流程: ticker=600519" in item for item in info_logs)
    assert any(
        "FINS.CN_PIPELINE filing 下载完成: ticker=600519 "
        "document_id=fil_cn_" in item
        and "status=downloaded form=FY" in item
        and "downloaded_files=2 skipped_files=0 failed_files=0" in item
        for item in info_logs
    )
    assert any(
        "FINS.CN_PIPELINE 开始 Docling 转换: ticker=600519 document_id=fil_cn_" in item
        and "form=FY filing_date=2025-04-01" in item
        and "source_file=fil_cn_" in item
        for item in info_logs
    )
    assert any(
        "FINS.CN_PIPELINE CN/HK 下载完成: ticker=600519 total=1 downloaded=1 skipped=0 failed=0 elapsed_ms="
        in item
        for item in info_logs
    )


def test_cn_download_fast_skip_uses_remote_fingerprint(tmp_path: Path) -> None:
    """完成态版本与 remote_fingerprint 命中时不下载 PDF。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    _collect_events(pipeline)

    events = _collect_events(pipeline)

    completed = [event for event in events if event.event_type == DownloadEventType.FILING_COMPLETED]
    assert completed[-1].payload["reason_code"] == "remote_fingerprint_matched"
    assert completed[-1].payload["fiscal_year"] == 2024
    assert completed[-1].payload["fiscal_period"] == "FY"
    assert completed[-1].payload["source_id"] == "A1"
    assert discovery.download_calls == 1
    assert converter.calls == 1


def test_cn_download_pdf_sha_skip_commits_remote_meta_for_next_fast_skip(tmp_path: Path) -> None:
    """PDF 内容一致时跳过 Docling，但推进远端 meta 让下次 fast skip。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(etag='"v1"'),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    _collect_events(pipeline)
    discovery.candidates = (_candidate(source_id="A2", etag='"v2"'),)
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )[0]
    context = build_fs_storage_test_context(tmp_path)
    before_meta = context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)

    events = _collect_events(pipeline)

    completed = [event for event in events if event.event_type == DownloadEventType.FILING_COMPLETED]
    assert completed[-1].payload["reason_code"] == "pdf_sha256_matched"
    assert completed[-1].payload["fiscal_year"] == 2024
    assert completed[-1].payload["fiscal_period"] == "FY"
    assert completed[-1].payload["source_id"] == "A2"
    assert discovery.download_calls == 2
    assert converter.calls == 1
    after_meta = context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    assert after_meta["source_id"] == "A2"
    assert after_meta["remote_fingerprint"] != before_meta["remote_fingerprint"]
    assert after_meta["source_fingerprint"] == before_meta["source_fingerprint"]
    assert after_meta["document_version"] == before_meta["document_version"]

    third_events = _collect_events(pipeline)

    third_completed = [event for event in third_events if event.event_type == DownloadEventType.FILING_COMPLETED]
    assert third_completed[-1].payload["reason_code"] == "remote_fingerprint_matched"
    assert third_completed[-1].payload["source_id"] == "A2"
    assert discovery.download_calls == 2
    assert converter.calls == 1


def test_cn_download_candidate_failure_does_not_fail_pipeline(tmp_path: Path) -> None:
    """单个 candidate PDF 下载失败时应继续处理后续候选。"""

    discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(
            _candidate(source_id="A1", fiscal_year=2024),
            _candidate(source_id="A2", fiscal_year=2023),
        ),
        failed_source_ids={"A1"},
    )
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    events = _collect_events(pipeline)

    result = _final_result(events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert result["status"] == "ok"
    assert summary["failed"] == 1
    assert summary["downloaded"] == 1
    assert [event.event_type for event in events].count(DownloadEventType.FILING_FAILED) == 1
    assert [event.event_type for event in events].count(DownloadEventType.FILING_COMPLETED) == 1
    failed_event = next(event for event in events if event.event_type is DownloadEventType.FILING_FAILED)
    assert failed_event.payload["fiscal_year"] == 2024
    assert failed_event.payload["fiscal_period"] == "FY"
    assert failed_event.payload["source_id"] == "A1"
    assert discovery.download_calls == 2


def test_cn_download_workflow_keeps_multi_year_periodic_candidates(tmp_path: Path) -> None:
    """workflow 不应再次截断 downloader 返回的跨年 H1/季度候选。"""

    discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(
            _candidate(source_id="H1-2024", fiscal_year=2024, fiscal_period="H1"),
            _candidate(source_id="H1-2023", fiscal_year=2023, fiscal_period="H1"),
        ),
    )
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    events = _collect_events(pipeline, form_type="H1")

    started = [event for event in events if event.event_type == DownloadEventType.FILING_STARTED]
    result = _final_result(events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert [event.payload["fiscal_year"] for event in started] == [2024, 2023]
    assert summary["downloaded"] == 2
    assert discovery.download_calls == 2
    assert converter.calls == 2


def test_cn_download_workflow_marks_missing_independent_quarters_skipped(tmp_path: Path) -> None:
    """请求 Q2/Q4 但主源无独立报告时应 skipped，不应 failed 或用 H1/FY 冒充。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    events = _collect_events(pipeline, form_type="Q2 Q4")

    completed = [event for event in events if event.event_type == DownloadEventType.FILING_COMPLETED]
    result = _final_result(events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert [(event.payload["form_type"], event.payload["status"]) for event in completed] == [
        ("Q2", "skipped"),
        ("Q4", "skipped"),
    ]
    assert result["status"] == "ok"
    assert summary["skipped"] == 2
    assert summary["failed"] == 0
    assert discovery.download_calls == 0
    assert converter.calls == 0


def test_cn_download_default_window_limits_interim_to_two_years(tmp_path: Path) -> None:
    """默认窗口下半年报/季报只保留 end 年和上一 fiscal_year 候选。"""

    discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(
            _candidate(
                source_id="H1-2026",
                fiscal_year=2026,
                fiscal_period="H1",
                filing_date="2026-08-30",
            ),
            _candidate(
                source_id="H1-2025",
                fiscal_year=2025,
                fiscal_period="H1",
                filing_date="2025-08-30",
            ),
            _candidate(
                source_id="H1-2024",
                fiscal_year=2024,
                fiscal_period="H1",
                filing_date="2024-08-30",
            ),
        ),
    )
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    async def collect() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []
        async for event in pipeline.download_stream(
            ticker="600519",
            form_type="H1",
            start_date=None,
            end_date="2026-12-31",
            overwrite=False,
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())

    started = [event for event in events if event.event_type == DownloadEventType.FILING_STARTED]
    result = _final_result(events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert [event.payload["fiscal_year"] for event in started] == [2026, 2025]
    assert summary["downloaded"] == 2
    assert discovery.download_calls == 2
    assert converter.calls == 2


def test_cn_download_default_window_limits_annual_to_five_reports(tmp_path: Path) -> None:
    """默认窗口下 FY 只保留最近 5 份年报候选。"""

    discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=tuple(
            _candidate(source_id=f"FY-{year}", fiscal_year=year, fiscal_period="FY")
            for year in (2025, 2024, 2023, 2022, 2021, 2020)
        ),
    )
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    async def collect() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []
        async for event in pipeline.download_stream(
            ticker="600519",
            form_type="FY",
            start_date=None,
            end_date="2026-05-01",
            overwrite=False,
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())

    started = [event for event in events if event.event_type == DownloadEventType.FILING_STARTED]
    result = _final_result(events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert [event.payload["fiscal_year"] for event in started] == [2025, 2024, 2023, 2022, 2021]
    assert summary["downloaded"] == 5
    assert discovery.download_calls == 5
    assert converter.calls == 5


def test_cn_download_version_mismatch_redownloads(tmp_path: Path) -> None:
    """完成态 download_version 不一致时禁止 fast skip 和 PDF skip。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    _collect_events(pipeline)
    context = build_fs_storage_test_context(tmp_path)
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )[0]
    meta = context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    meta["download_version"] = "cn_pipeline_download_v0.0.0"
    meta["first_ingested_at"] = "2020-01-01T00:00:00+00:00"
    meta["created_at"] = "2020-01-01T00:00:01+00:00"
    context.source_repository.replace_source_meta("600519", document_id, SourceKind.FILING, meta)

    events = _collect_events(pipeline)

    completed = [event for event in events if event.event_type == DownloadEventType.FILING_COMPLETED]
    assert completed[-1].payload["status"] == "downloaded"
    assert discovery.download_calls == 2
    assert converter.calls == 2
    updated_meta = context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    assert updated_meta["first_ingested_at"] == "2020-01-01T00:00:00+00:00"
    assert updated_meta["created_at"] == "2020-01-01T00:00:01+00:00"


def test_cn_download_docling_failure_leaves_no_staged_state(tmp_path: Path) -> None:
    """阶段 B（Docling）失败 => 零 begin/零 publish：不落任何 staging state。

    S14-CTRL-12 三段边界：阶段 A/B 失败/取消 => 零 begin（无 token、零
    publish）；第二次运行必须重新下载与转换，不得复用任何 staged 中间态。
    """

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter(fail_once=True)
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    first_events = _collect_events(pipeline)
    assert any(event.event_type == DownloadEventType.FILING_FAILED for event in first_events)

    context = build_fs_storage_test_context(tmp_path)
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )[0]
    with pytest.raises(FileNotFoundError):
        context.source_repository.get_source_handle("600519", document_id, SourceKind.FILING)

    second_events = _collect_events(pipeline)

    completed = [event for event in second_events if event.event_type == DownloadEventType.FILING_COMPLETED]
    assert completed[-1].payload["status"] == "downloaded"
    assert completed[-1].payload["reused_pdf"] is False
    assert discovery.download_calls == 2
    assert converter.calls == 2


def test_cn_download_stage_cancel_returns_cancelled_not_failed(tmp_path: Path) -> None:
    """阶段内取消应返回 cancelled，不应记作 failed。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    calls = {"count": 0}

    def cancel_checker() -> bool:
        calls["count"] += 1
        return calls["count"] >= 3

    events = _collect_events(pipeline, cancel_checker=cancel_checker)

    result = _final_result(events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert result["status"] == "cancelled"
    assert summary["failed"] == 0
    assert any(event.event_type == DownloadEventType.FILE_DOWNLOADED for event in events)
    assert not any(event.event_type == DownloadEventType.FILING_FAILED for event in events)


def test_cn_download_cancel_after_docling_convert_prevents_commit(tmp_path: Path) -> None:
    """Docling 转换后收到取消信号时不得继续提交完成态 source meta。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    def cancel_checker() -> bool:
        """转换完成后返回取消。"""

        return converter.calls > 0

    events = _collect_events(pipeline, cancel_checker=cancel_checker)

    result = _final_result(events)
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )[0]
    source_meta = pipeline._source_repository.get_source_meta("600519", document_id, SourceKind.FILING)  # type: ignore[attr-defined]
    assert result["status"] == "cancelled"
    assert source_meta["ingest_complete"] is False


def test_cn_download_commits_when_pdf_and_docling_are_staged(tmp_path: Path) -> None:
    """PDF 与 Docling JSON 都已落盘但 ingest_complete=False 时应直接 commit。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    _seed_staged_cn_download_state(
        tmp_path=tmp_path,
        discovery=discovery,
        candidate=_candidate(),
        docling_bytes=_DOCLING_BYTES,
    )

    events = _collect_events(pipeline)

    completed = [event for event in events if event.event_type == DownloadEventType.FILING_COMPLETED]
    assert completed[-1].payload["status"] == "downloaded"
    assert completed[-1].payload["reused_docling"] is True
    assert discovery.download_calls == 0
    assert converter.calls == 0


def test_cn_download_reuses_unlisted_docling_blob_after_crash(tmp_path: Path) -> None:
    """Docling blob 已落盘但 meta 未列出时，下次应复用 blob 并 commit。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    _seed_staged_cn_download_state(
        tmp_path=tmp_path,
        discovery=discovery,
        candidate=_candidate(),
        docling_bytes=_DOCLING_BYTES,
    )
    context = build_fs_storage_test_context(tmp_path)
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )[0]
    staged_meta = context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    existing_files = staged_meta.get("files")
    assert isinstance(existing_files, list)
    context.source_repository.update_source_document(
        FilingUpdateRequest(
            ticker="600519",
            document_id=document_id,
            internal_document_id=str(staged_meta["internal_document_id"]),
            form_type="FY",
            primary_document=f"{document_id}.pdf",
            file_entries=[item for item in existing_files if isinstance(item, dict) and item.get("name") != f"{document_id}_docling.json"],
            meta={"ingest_complete": False},
        ),
        source_kind=SourceKind.FILING,
    )

    events = _collect_events(pipeline)

    completed = [event for event in events if event.event_type == DownloadEventType.FILING_COMPLETED]
    assert completed[-1].payload["status"] == "downloaded"
    assert completed[-1].payload["reused_docling"] is True
    assert discovery.download_calls == 0
    assert converter.calls == 0


def test_cn_download_unlisted_docling_staged_store_atomic_recovery(tmp_path: Path) -> None:
    """staged-store 下 unlisted Docling blob：同批重存 + commit 原子。

    阶段 C 显式 batch 内复用已读 docling bytes 重存（``_find_file_meta`` 仅
    在条目存在时使用），provider/converter 零调用；commit 后 blob 与 meta
    条目一致。
    """

    from dayu.fins.pipelines.cn_download_source_upsert import build_remote_fingerprint
    from dayu.fins.storage import (
        FsBatchingRepository,
        FsCompanyMetaRepository,
        FsDocumentBlobRepository,
        FsFilingMaintenanceRepository,
        FsProcessedDocumentRepository,
        FsSourceDocumentRepository,
    )
    from dayu.fins.storage._fs_repository_factory import build_fs_repository_set

    repository_set: _FsRepositorySet = build_fs_repository_set(workspace_root=tmp_path)
    company_repository = FsCompanyMetaRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    maintenance_repository = FsFilingMaintenanceRepository(tmp_path, repository_set=repository_set)
    batching = FsBatchingRepository(tmp_path, repository_set=repository_set)

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    gate = CnPreparationGate(capacity=1)
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        processor_registry=ProcessorRegistry(),
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        blob_repository=blob_repository,
        filing_maintenance_repository=maintenance_repository,
        cn_discovery_client=discovery,
        pdf_download_gate=NoopCnDownloadPdfGate(),
        convert_pdf_to_docling_json=converter,
        batching_repository=batching,
        preparation_gate=gate,
    )

    candidate = _candidate()
    remote_fingerprint = build_remote_fingerprint(candidate)
    pdf_sha256 = hashlib.sha256(_PDF_BYTES).hexdigest()
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type=candidate.fiscal_period,
        fiscal_year=candidate.fiscal_year,
        fiscal_period=candidate.fiscal_period,
        amended=candidate.amended,
    )[0]
    from dayu.fins.domain.document_models import FilingCreateRequest

    source_repository.create_source_document(
        FilingCreateRequest(
            ticker="600519",
            document_id=document_id,
            internal_document_id=f"cn_seed_{document_id}",
            form_type=candidate.fiscal_period,
            primary_document=f"{document_id}.pdf",
            file_entries=[],
            meta={
                "ingest_complete": False,
                "staging_remote_fingerprint": remote_fingerprint,
                "staging_pdf_sha256": pdf_sha256,
                "remote_fingerprint": remote_fingerprint,
            },
        ),
        source_kind=SourceKind.FILING,
    )
    handle = source_repository.get_source_handle("600519", document_id, SourceKind.FILING)
    pdf_meta = blob_repository.store_file(
        handle,
        f"{document_id}.pdf",
        BytesIO(_PDF_BYTES),
        content_type="application/pdf",
        metadata={"source": "original"},
    )
    blob_repository.store_file(
        handle,
        f"{document_id}_docling.json",
        BytesIO(_DOCLING_BYTES),
        content_type="application/json",
        metadata={"source": "docling", "pdf_sha256": pdf_sha256},
    )

    def _entry(name: str, meta: FileObjectMeta) -> dict[str, str | int | None]:
        """构造 meta.files 条目。"""

        return {
            "name": name,
            "uri": meta.uri,
            "etag": meta.etag,
            "last_modified": meta.last_modified,
            "size": meta.size,
            "content_type": meta.content_type,
            "sha256": meta.sha256,
            "source": "original" if name.endswith(".pdf") else "docling",
        }

    # 故意把 docling 从 meta.files 移除（unlisted）。
    source_repository.update_source_document(
        FilingUpdateRequest(
            ticker="600519",
            document_id=document_id,
            internal_document_id=f"cn_seed_{document_id}",
            form_type=candidate.fiscal_period,
            primary_document=f"{document_id}.pdf",
            file_entries=[
                _entry(f"{document_id}.pdf", pdf_meta),
            ],
            meta={
                "ingest_complete": False,
                "staging_remote_fingerprint": remote_fingerprint,
                "staging_pdf_sha256": pdf_sha256,
                "remote_fingerprint": remote_fingerprint,
            },
        ),
        source_kind=SourceKind.FILING,
    )

    events = _collect_events(pipeline)

    completed = [event for event in events if event.event_type == DownloadEventType.FILING_COMPLETED]
    assert completed[-1].payload["status"] == "downloaded"
    assert completed[-1].payload["reused_docling"] is True
    assert discovery.download_calls == 0
    assert converter.calls == 0
    final_meta = source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    final_files = final_meta.get("files")
    assert isinstance(final_files, list)
    assert any(
        isinstance(item, dict) and item.get("name") == f"{document_id}_docling.json"
        for item in final_files
    )
    assert final_meta.get("ingest_complete") is True


def test_cn_download_does_not_reuse_docling_when_staged_pdf_sha_differs(tmp_path: Path) -> None:
    """当前 PDF SHA 与 staged meta 不一致时，旧 Docling JSON 不能复用。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    _seed_staged_cn_download_state(
        tmp_path=tmp_path,
        discovery=discovery,
        candidate=_candidate(),
        docling_bytes=b'{"document": "old"}',
    )
    context = build_fs_storage_test_context(tmp_path)
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )[0]
    staged_meta = context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    staged_meta["staging_pdf_sha256"] = "0" * 64
    context.source_repository.replace_source_meta("600519", document_id, SourceKind.FILING, staged_meta)

    events = _collect_events(pipeline)

    completed = [event for event in events if event.event_type == DownloadEventType.FILING_COMPLETED]
    assert completed[-1].payload["status"] == "downloaded"
    assert completed[-1].payload["reused_docling"] is False
    assert discovery.download_calls == 1
    assert converter.calls == 1


def test_cn_download_overwrite_clears_ticker_and_redownloads(tmp_path: Path) -> None:
    """overwrite=True 应触发 ticker 级 clear，并禁止复用完成态。"""

    context = build_fs_storage_test_context(tmp_path)
    maintenance = _CountingMaintenanceRepository(context.filing_maintenance_repository)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        processor_registry=ProcessorRegistry(),
        company_repository=context.company_repository,
        source_repository=context.source_repository,
        processed_repository=context.processed_repository,
        blob_repository=context.blob_repository,
        filing_maintenance_repository=maintenance,
        cn_discovery_client=discovery,
        convert_pdf_to_docling_json=converter,
    )
    _collect_events(pipeline)

    _collect_events(pipeline, overwrite=True)

    assert maintenance.cleared_tickers == ["600519"]
    assert discovery.download_calls == 2
    meta = context.source_repository.get_source_meta(
        ticker="600519",
        document_id=build_cn_filing_ids(
            ticker="600519",
            form_type="FY",
            fiscal_year=2024,
            fiscal_period="FY",
            amended=False,
        )[0],
        source_kind=SourceKind.FILING,
    )
    assert meta["ingest_complete"] is True
    assert meta["download_version"] == CN_PIPELINE_DOWNLOAD_VERSION
    assert str(meta["primary_document"]).endswith("_docling.json")


def test_cn_download_overwrite_does_not_clear_when_discovery_fails(tmp_path: Path) -> None:
    """overwrite=True 遇到候选发现失败时不得先清空本地已完成 filing。"""

    context = build_fs_storage_test_context(tmp_path)
    maintenance = _CountingMaintenanceRepository(context.filing_maintenance_repository)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = CnPipeline(
        workspace_root=tmp_path,
        processor_registry=ProcessorRegistry(),
        company_repository=context.company_repository,
        source_repository=context.source_repository,
        processed_repository=context.processed_repository,
        blob_repository=context.blob_repository,
        filing_maintenance_repository=maintenance,
        cn_discovery_client=discovery,
        convert_pdf_to_docling_json=converter,
    )
    _collect_events(pipeline)
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )[0]
    assert context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)

    discovery.list_error = RuntimeError("remote discovery unavailable")
    events = _collect_events(pipeline, overwrite=True)

    result = _final_result(events)
    assert result["status"] == "failed"
    assert maintenance.cleared_tickers == []
    assert context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)


def test_cn_download_pdf_temp_file_read_failure_is_filing_failed(tmp_path: Path) -> None:
    """PDF 下载后临时文件不可读时应产出 filing failed，而不是未处理异常。"""

    discovery = _FakeDiscoveryClient(
        temp_dir=tmp_path,
        candidates=(_candidate(),),
        delete_pdf_before_return=True,
    )
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    events = _collect_events(pipeline)

    failed_events = [event for event in events if event.event_type == DownloadEventType.FILING_FAILED]
    result = _final_result(events)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert failed_events[-1].payload["reason_code"] == "pdf_read_failed"
    assert summary["failed"] == 1


def test_cn_download_unsupported_ticker_raises_value_error(tmp_path: Path) -> None:
    """非 CN/HK ticker 应与 SEC 一样作为请求级错误直接抛出。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    async def collect() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []
        async for event in pipeline.download_stream(ticker="AAPL", form_type="FY"):
            events.append(event)
        return events

    with pytest.raises(ValueError, match="不支持"):
        asyncio.run(collect())


def test_cn_download_rebuild_local_meta_manifest_without_redownload(tmp_path: Path) -> None:
    """CN/HK `download --rebuild` 应基于本地完成态重建且不访问远端下载。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    _collect_events(pipeline)
    context = build_fs_storage_test_context(tmp_path)
    document_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )[0]
    meta = context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    meta["download_version"] = "legacy_download_version"
    meta["staging_remote_fingerprint"] = "legacy_stage"
    meta["staging_pdf_sha256"] = "legacy_pdf"
    context.source_repository.replace_source_meta("600519", document_id, SourceKind.FILING, meta)

    async def collect() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []
        async for event in pipeline.download_stream(
            ticker="600519",
            form_type="FY",
            start_date="2024",
            end_date="2026",
            overwrite=False,
            rebuild=True,
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())

    result = _final_result(events)
    filters = result["filters"]
    summary = result["summary"]
    assert isinstance(filters, dict)
    assert isinstance(summary, dict)
    rebuilt_meta = context.source_repository.get_source_meta("600519", document_id, SourceKind.FILING)
    assert [event.event_type for event in events] == [
        DownloadEventType.PIPELINE_STARTED,
        DownloadEventType.FILING_COMPLETED,
        DownloadEventType.PIPELINE_COMPLETED,
    ]
    assert result["status"] == "ok"
    assert filters["rebuild"] is True
    assert summary["downloaded"] == 1
    assert discovery.download_calls == 1
    assert converter.calls == 1
    assert rebuilt_meta["download_version"] == CN_PIPELINE_DOWNLOAD_VERSION
    assert rebuilt_meta["staging_remote_fingerprint"] is None
    assert rebuilt_meta["staging_pdf_sha256"] is None


def test_cn_download_rebuild_honors_cancel_checker(tmp_path: Path) -> None:
    """rebuild 遍历本地 filing 时应响应取消并返回 cancelled。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(_candidate(),))
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)
    _collect_events(pipeline)

    async def collect() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []
        async for event in pipeline.download_stream(
            ticker="600519",
            form_type="FY",
            start_date="2024",
            end_date="2026",
            overwrite=False,
            rebuild=True,
            cancel_checker=lambda: True,
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())

    result = _final_result(events)
    assert [event.event_type for event in events] == [
        DownloadEventType.PIPELINE_STARTED,
        DownloadEventType.PIPELINE_COMPLETED,
    ]
    assert result["status"] == "cancelled"


def test_cn_download_post_loop_cancel_checker_error_yields_failed_result(tmp_path: Path) -> None:
    """最终状态检查时 cancel_checker 失败也必须产出 PIPELINE_COMPLETED。"""

    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=())
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, converter=converter)

    async def collect() -> list[DownloadEvent]:
        events: list[DownloadEvent] = []

        def cancel_checker() -> bool:
            """模拟取消通道关闭。"""

            raise RuntimeError("cancel channel closed")

        async for event in pipeline.download_stream(
            ticker="600519",
            form_type="FY",
            start_date="2024",
            end_date="2026",
            cancel_checker=cancel_checker,
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())

    result = _final_result(events)
    assert events[-1].event_type == DownloadEventType.PIPELINE_COMPLETED
    assert result["status"] == "failed"
    assert result["reason_code"] == "cn_download_failed"
