"""per-filing terminal 状态机单元测试（S14-CTRL-12，闭合 Terra S14-TERMINAL-02）。

验证 SEC ``run_download_stream_impl`` 与 CN ``run_cn_download_single_filing_stream``
的 per-filing terminal 语义：

- 恰好一个 FILING_COMPLETED（含 skip）且 pre-commit cancel fence 通过才
  commit；缺 terminal、重复/矛盾 terminal、FILING_FAILED、CancelledError、
  TimeoutError、其它 exception 均 rollback 同一 token（零 publish）；
- CN 阶段 A/B 失败零 begin（无 token、零 publish）；仅阶段 C 已 begin 才
  rollback 同一 token；
- 外部 event yield 顺序/内容与既有 continue/stop 语义不变。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import AsyncIterator, Callable

import pytest

from dayu.contracts.cancellation import CancelledError
from dayu.fins.domain.document_models import BatchToken, FileObjectMeta
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile,
    CnReportCandidate,
    CnReportQuery,
    DownloadedReportAsset,
)
from dayu.fins.pipelines.cn_download_pdf_gate import NoopCnDownloadPdfGate
from dayu.fins.pipelines.cn_download_protocols import CnPreparationGate
from dayu.fins.pipelines.cn_download_workflow import run_cn_download_single_filing_stream
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.sec_company_meta import (
    extract_sec_ticker_aliases,
    merge_ticker_aliases,
)
from dayu.fins.pipelines.sec_download_diagnostics import (
    warn_insufficient_filings,
    warn_xbrl_missing_filings,
)
from dayu.fins.pipelines.sec_download_event_mapping import build_download_filing_event_payload
from dayu.fins.pipelines.sec_download_state import (
    _load_rejection_registry as _sec_load_rejection_registry,
)
from dayu.fins.pipelines.sec_download_state import (
    _save_rejection_registry as _sec_save_rejection_registry,
)
from dayu.fins.pipelines.sec_download_workflow import run_download_stream_impl
from dayu.fins.pipelines.sec_form_utils import parse_date
from dayu.fins.pipelines.sec_sc13_filtering import should_warn_missing_sc13
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet
from dayu.fins.storage.fs_batching_repository import FsBatchingRepository
from tests.fins.storage_testkit import FsStorageTestContext, build_fs_storage_test_context

_PDF_BYTES = b"%PDF-1.7\n" + b"1" * 512
_DOCLING_BYTES = b'{"document": "ok"}'

_MODULE = "test_per_filing_terminal_state"


class _FakeStagedStore:
    """实现 StagedFileStoreProtocol 的记录型 fake（stat 真实、缺失抛异常）。"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.published: list[str] = []
        self.fail_stage: bool = False

    def stage_publish(self, *, operation_id: str, data: BytesIO) -> FileObjectMeta:
        """写入 staging（key 为 ``.dayu-staging/{operation_id}/{sha256}``）。"""

        if self.fail_stage:
            raise OSError("stage failed")
        content = data.read()
        digest = hashlib.sha256(content).hexdigest()
        key = f".dayu-staging/{operation_id}/{digest}"
        self.objects[key] = content
        return FileObjectMeta(
            uri=self.object_uri(key),
            sha256=digest,
            size=len(content),
        )

    def publish_staged(
        self,
        *,
        staging_key: str,
        final_key: str,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> None:
        """发布 final。"""

        del content_type, metadata
        self.objects[final_key] = self.objects[staging_key]
        self.published.append(final_key)

    def object_uri(self, key: str) -> str:
        """构造 URI。"""

        return f"s3://bucket/{key}"

    def key_from_uri(self, uri: str) -> str:
        """从 URI 提取 key。"""

        return uri.split("s3://bucket/", 1)[1]

    def delete_object_idempotent(self, key: str) -> None:
        """幂等删除。"""

        self.objects.pop(key, None)

    def stat_object(self, key: str) -> FileObjectMeta:
        """HEAD 返回真实 digest/size；缺失抛 FileNotFoundError。"""

        if key not in self.objects:
            raise FileNotFoundError(f"对象不存在: {key}")
        content = self.objects[key]
        return FileObjectMeta(
            uri=self.object_uri(key),
            sha256=hashlib.sha256(content).hexdigest(),
            size=len(content),
        )

    def list_objects(self, prefix: str) -> list[FileObjectMeta]:
        """列出对象。"""

        return [
            FileObjectMeta(uri=self.object_uri(key))
            for key in sorted(self.objects)
            if key.startswith(prefix)
        ]

    def get_object(self, key: str) -> BytesIO:
        """读取对象。"""

        if key not in self.objects:
            raise FileNotFoundError(f"对象不存在: {key}")
        return BytesIO(self.objects[key])


class _RecordingBatching:
    """记录 begin/commit/rollback 的 batching fake（转发同 core 真实现）。"""

    def __init__(self, real: FsBatchingRepository) -> None:
        self._real = real
        self.begin_calls: list[str] = []
        self.commit_calls: list[str] = []
        self.rollback_calls: list[str] = []

    def begin_batch(self, ticker: str) -> BatchToken:
        """记录并转发 begin。"""

        self.begin_calls.append(ticker)
        return self._real.begin_batch(ticker)

    def commit_batch(self, token: BatchToken) -> None:
        """记录并转发 commit。"""

        self.commit_calls.append(token.ticker)
        self._real.commit_batch(token)

    def rollback_batch(self, token: BatchToken) -> None:
        """记录并转发 rollback。"""

        self.rollback_calls.append(token.ticker)
        self._real.rollback_batch(token)

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """转发 recovery。"""

        return self._real.recover_orphan_batches(dry_run=dry_run)


# ========== SEC per-filing terminal ==========


@dataclass(frozen=True)
class _FakeFiling:
    """下载工作流所需的 filing 视图。"""

    accession_number: str
    form_type: str
    filing_date: str
    report_date: str


class _FakeSecDownloader:
    """满足 SEC 工作流下载器边界的最小 fake。"""

    def configure(self, user_agent: str | None, sleep_seconds: float, max_retries: int) -> None:
        """配置下载器（无操作）。"""

        del user_agent, sleep_seconds, max_retries

    def normalize_ticker(self, ticker: str) -> str:
        """标准化 ticker。"""

        return ticker

    def resolve_company(self, ticker: str) -> tuple[str, str, str]:
        """解析公司。"""

        del ticker
        return ("0000320193", "Apple Inc.", "0000320193")

    def fetch_submissions(self, cik10: str) -> dict[str, str]:
        """拉取 submissions（空）。"""

        del cik10
        return {}


class _FakeSecWorkflowHost:
    """实现 ``SecDownloadWorkflowHost`` 的最小测试宿主。"""

    def __init__(
        self,
        *,
        context: FsStorageTestContext,
        batching: BatchingRepositoryProtocol | None,
        single_filing_events: list[DownloadEvent],
    ) -> None:
        self.MODULE = _MODULE
        self._downloader = _FakeSecDownloader()
        self._user_agent: str | None = None
        self._sleep_seconds = 0.0
        self._max_retries = 0
        self._filing_maintenance_repository = context.filing_maintenance_repository
        self._source_repository = context.source_repository
        self._batching_repository = batching
        self._single_filing_events = single_filing_events
        self._filings = [
            _FakeFiling(
                accession_number="0000320193-24-000001",
                form_type="10-K",
                filing_date="2024-02-01",
                report_date="2024-02-01",
            )
        ]
        self._stream_override: Callable[[], AsyncIterator[DownloadEvent]] | None = None
        self.upsert_company_calls = 0
        self.logged_results: list[dict[str, str]] = []

    @property
    def batching_repository(self) -> BatchingRepositoryProtocol | None:
        """返回注入的 batch 仓储。"""

        return self._batching_repository

    def _rebuild_download_artifacts(
        self,
        *,
        ticker: str,
        form_type: str | None,
        start_date: str | None,
        end_date: str | None,
        overwrite: bool,
    ) -> dict[str, str]:
        """重建产物（未使用）。"""

        del ticker, form_type, start_date, end_date, overwrite
        return {}

    def _resolve_form_windows(
        self,
        form_type: str | None,
        start_date: str | None,
        end_date: dt.date,
    ) -> dict[str, dt.date]:
        """返回固定 form 窗口。"""

        del form_type, start_date
        return {"10-K": end_date}

    def _upsert_company_meta(
        self,
        ticker: str,
        company_id: str,
        company_name: str,
        ticker_aliases: list[str] | None,
    ) -> None:
        """记录公司 upsert。"""

        del ticker, company_id, company_name, ticker_aliases
        self.upsert_company_calls += 1

    def _build_result(self, action: str, **payload: str) -> dict[str, str]:
        """构建统一结果。"""

        del action, payload
        return {"status": "ok"}

    async def _download_single_filing_stream(
        self,
        *,
        ticker: str,
        cik: str,
        filing: _FakeFiling,
        overwrite: bool,
        rejection_registry: dict[str, dict[str, str]],
    ) -> AsyncIterator[DownloadEvent]:
        """按测试配置逐条产出单 filing 事件。"""

        del ticker, cik, filing, overwrite, rejection_registry
        override = self._stream_override
        if override is not None:
            async for event in override():
                yield event
            return
        for event in self._single_filing_events:
            yield event

    async def _filter_filings(
        self,
        *,
        ticker: str,
        submissions: dict[str, str],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: dict[str, bool | None] | None = None,
        rejection_registry: dict[str, dict[str, str]] | None = None,
        overwrite: bool = False,
    ) -> tuple[list[_FakeFiling], set[str]]:
        """返回固定 filing 列表。"""

        del ticker, submissions, form_windows, end_date, target_cik
        del sc13_direction_cache, rejection_registry, overwrite
        return self._filings, set()

    async def _extend_with_browse_edgar_sc13(
        self,
        *,
        ticker: str,
        filings: list[_FakeFiling],
        filenums: set[str],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: dict[str, bool | None] | None = None,
        rejection_registry: dict[str, dict[str, str]] | None = None,
        overwrite: bool = False,
    ) -> list[_FakeFiling]:
        """不扩展 SC13。"""

        del ticker, filenums, form_windows, end_date, target_cik
        del sc13_direction_cache, rejection_registry, overwrite
        return filings

    async def _retry_sc13_if_empty(
        self,
        *,
        ticker: str,
        filings: list[_FakeFiling],
        filenums: set[str],
        submissions: dict[str, str],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: dict[str, bool | None] | None = None,
        rejection_registry: dict[str, dict[str, str]] | None = None,
        overwrite: bool = False,
    ) -> list[_FakeFiling]:
        """不重试 SC13。"""

        del ticker, filenums, submissions, form_windows, end_date, target_cik
        del sc13_direction_cache, rejection_registry, overwrite
        return filings

    def _log_filing_download_result(self, ticker: str, filing_result: dict[str, str]) -> None:
        """记录 filing 结果。"""

        del ticker
        self.logged_results.append(filing_result)


def _terminal_event(
    event_type: DownloadEventType,
    *,
    document_id: str,
    status: str = "downloaded",
) -> DownloadEvent:
    """构造携带 ``filing_result`` 的 terminal 事件。"""

    return DownloadEvent(
        event_type=event_type,
        ticker="AAPL",
        document_id=document_id,
        payload={
            "filing_result": {
                "document_id": document_id,
                "status": status,
            },
            "status": status,
        },
    )


def _noop_cleanup_stale_filing_dirs(**kwargs: str) -> int:
    """stale cleanup 桩。"""

    del kwargs
    return 0


def _drive_sec_workflow(
    tmp_path: Path,
    *,
    single_filing_events: list[DownloadEvent],
    cancel_checker: Callable[[], bool] | None = None,
    provider_download_timeout_seconds: float = 60.0,
) -> tuple[list[DownloadEvent], _RecordingBatching, _FakeStagedStore]:
    """驱动 SEC per-filing 下载工作流，返回事件/批次记录/staged store。"""

    context = build_fs_storage_test_context(tmp_path)
    fake_store = _FakeStagedStore()
    context.core._file_store = fake_store
    batching = _RecordingBatching(
        FsBatchingRepository(
            tmp_path,
            repository_set=_FsRepositorySet(core=context.core),
        )
    )
    host = _FakeSecWorkflowHost(
        context=context,
        batching=batching,
        single_filing_events=single_filing_events,
    )
    events: list[DownloadEvent] = []

    async def collect() -> list[DownloadEvent]:
        async for event in run_download_stream_impl(
            host,
            ticker="AAPL",
            form_type="10-K",
            start_date="2024-01-01",
            end_date="2024-12-31",
            overwrite=False,
            rebuild=False,
            ticker_aliases=None,
            cancel_checker=cancel_checker,
            parse_date=parse_date,
            extract_sec_ticker_aliases=extract_sec_ticker_aliases,
            merge_ticker_aliases=merge_ticker_aliases,
            clear_filings_dir=lambda repo, ticker: repo.clear_filing_documents(ticker),
            load_rejection_registry=_sec_load_rejection_registry,
            save_rejection_registry=_sec_save_rejection_registry,
            should_warn_missing_sc13=should_warn_missing_sc13,
            warn_insufficient_filings=warn_insufficient_filings,
            warn_xbrl_missing_filings=warn_xbrl_missing_filings,
            cleanup_stale_filing_dirs=_noop_cleanup_stale_filing_dirs,
            build_download_filing_event_payload=build_download_filing_event_payload,
            provider_download_timeout_seconds=provider_download_timeout_seconds,
        ):
            events.append(event)
        return events

    return asyncio.run(collect()), batching, fake_store


def test_sec_exactly_one_completed_commits(tmp_path: Path) -> None:
    """恰好一个 FILING_COMPLETED 且 fence 通过 => 唯一 begin + commit。"""

    events, batching, fake_store = _drive_sec_workflow(
        tmp_path,
        single_filing_events=[
            _terminal_event(DownloadEventType.FILING_COMPLETED, document_id="fil_1"),
        ],
    )
    assert batching.begin_calls == ["AAPL"]
    assert batching.commit_calls == ["AAPL"]
    assert batching.rollback_calls == []
    terminal = [
        event
        for event in events
        if event.event_type in {
            DownloadEventType.FILING_COMPLETED,
            DownloadEventType.FILING_FAILED,
        }
    ]
    assert [event.event_type for event in terminal] == [DownloadEventType.FILING_COMPLETED]
    assert events[-1].event_type == DownloadEventType.PIPELINE_COMPLETED


def test_sec_filing_failed_normal_return_rolls_back(tmp_path: Path) -> None:
    """FILING_FAILED 正常 return => rollback 同一 token、零 publish。"""

    events, batching, fake_store = _drive_sec_workflow(
        tmp_path,
        single_filing_events=[
            _terminal_event(
                DownloadEventType.FILING_FAILED,
                document_id="fil_1",
                status="failed",
            ),
        ],
    )
    assert batching.begin_calls == ["AAPL"]
    assert batching.rollback_calls == ["AAPL"]
    assert batching.commit_calls == []
    assert fake_store.published == []
    assert events[-1].event_type == DownloadEventType.PIPELINE_COMPLETED


def test_sec_missing_terminal_rolls_back(tmp_path: Path) -> None:
    """stream 结束无 terminal event => rollback、零 publish。"""

    events, batching, fake_store = _drive_sec_workflow(
        tmp_path,
        single_filing_events=[
            DownloadEvent(
                event_type=DownloadEventType.FILE_DOWNLOADED,
                ticker="AAPL",
                document_id="fil_1",
                payload={"name": "a.pdf"},
            )
        ],
    )
    assert batching.begin_calls == ["AAPL"]
    assert batching.rollback_calls == ["AAPL"]
    assert batching.commit_calls == []
    assert fake_store.published == []


def test_sec_duplicate_completed_terminal_rolls_back(tmp_path: Path) -> None:
    """重复 FILING_COMPLETED => 非法终态 rollback（恰好一个才 commit）。"""

    _, batching, fake_store = _drive_sec_workflow(
        tmp_path,
        single_filing_events=[
            _terminal_event(DownloadEventType.FILING_COMPLETED, document_id="fil_1"),
            _terminal_event(DownloadEventType.FILING_COMPLETED, document_id="fil_1"),
        ],
    )
    assert batching.begin_calls == ["AAPL"]
    assert batching.rollback_calls == ["AAPL"]
    assert batching.commit_calls == []
    assert fake_store.published == []


def test_sec_conflicting_terminal_rolls_back(tmp_path: Path) -> None:
    """矛盾 terminal（COMPLETED 后 FAILED、FAILED 后 COMPLETED）=> rollback。"""

    _, batching, fake_store = _drive_sec_workflow(
        tmp_path,
        single_filing_events=[
            _terminal_event(DownloadEventType.FILING_COMPLETED, document_id="fil_1"),
            _terminal_event(
                DownloadEventType.FILING_FAILED,
                document_id="fil_1",
                status="failed",
            ),
        ],
    )
    assert batching.rollback_calls == ["AAPL"]
    assert batching.commit_calls == []
    assert fake_store.published == []

    _, batching_failed_then_completed, fake_store_reverse = _drive_sec_workflow(
        tmp_path,
        single_filing_events=[
            _terminal_event(
                DownloadEventType.FILING_FAILED,
                document_id="fil_1",
                status="failed",
            ),
            _terminal_event(DownloadEventType.FILING_COMPLETED, document_id="fil_1"),
        ],
    )
    assert batching_failed_then_completed.rollback_calls == ["AAPL"]
    assert batching_failed_then_completed.commit_calls == []
    assert fake_store_reverse.published == []


def test_sec_cancel_fence_prevents_commit(tmp_path: Path) -> None:
    """FILING_COMPLETED 但 commit 前 cancel fence 命中 => rollback。"""

    class _FlipCancelChecker:
        """第一次（循环顶部）返回 False，commit 前 fence 返回 True。"""

        def __init__(self) -> None:
            self.calls = 0

        def __call__(self) -> bool:
            self.calls += 1
            return self.calls > 1

    _, batching, fake_store = _drive_sec_workflow(
        tmp_path,
        single_filing_events=[
            _terminal_event(DownloadEventType.FILING_COMPLETED, document_id="fil_1"),
        ],
        cancel_checker=_FlipCancelChecker(),
    )
    assert batching.begin_calls == ["AAPL"]
    assert batching.rollback_calls == ["AAPL"]
    assert batching.commit_calls == []
    assert fake_store.published == []


def test_sec_stream_exception_rolls_back_same_token(tmp_path: Path) -> None:
    """单 filing 流抛其它 exception => rollback 同一 token 并传播。"""

    context = build_fs_storage_test_context(tmp_path)
    fake_store = _FakeStagedStore()
    context.core._file_store = fake_store
    batching = _RecordingBatching(
        FsBatchingRepository(
            tmp_path,
            repository_set=_FsRepositorySet(core=context.core),
        )
    )

    async def failing_stream() -> AsyncIterator[DownloadEvent]:
        """先产出 terminal 再抛异常。"""

        yield _terminal_event(DownloadEventType.FILING_COMPLETED, document_id="fil_1")
        raise RuntimeError("boom")

    host = _FakeSecWorkflowHost(
        context=context,
        batching=batching,
        single_filing_events=[],
    )
    host._stream_override = failing_stream

    async def collect() -> None:
        with pytest.raises(RuntimeError, match="boom"):
            async for _event in run_download_stream_impl(
                host,
                ticker="AAPL",
                form_type="10-K",
                start_date="2024-01-01",
                end_date="2024-12-31",
                overwrite=False,
                rebuild=False,
                ticker_aliases=None,
                cancel_checker=None,
                parse_date=parse_date,
                extract_sec_ticker_aliases=extract_sec_ticker_aliases,
                merge_ticker_aliases=merge_ticker_aliases,
                clear_filings_dir=lambda repo, ticker: repo.clear_filing_documents(ticker),
                load_rejection_registry=_sec_load_rejection_registry,
                save_rejection_registry=_sec_save_rejection_registry,
                should_warn_missing_sc13=should_warn_missing_sc13,
                warn_insufficient_filings=warn_insufficient_filings,
                warn_xbrl_missing_filings=warn_xbrl_missing_filings,
                cleanup_stale_filing_dirs=_noop_cleanup_stale_filing_dirs,
                build_download_filing_event_payload=build_download_filing_event_payload,
                provider_download_timeout_seconds=60.0,
            ):
                pass

    asyncio.run(collect())
    assert batching.rollback_calls == ["AAPL"]
    assert batching.commit_calls == []
    assert fake_store.published == []


def test_sec_cancelled_error_rolls_back_same_token(tmp_path: Path) -> None:
    """单 filing 流抛 CancelledError => rollback 同一 token 并传播。"""

    context = build_fs_storage_test_context(tmp_path)
    fake_store = _FakeStagedStore()
    context.core._file_store = fake_store
    batching = _RecordingBatching(
        FsBatchingRepository(
            tmp_path,
            repository_set=_FsRepositorySet(core=context.core),
        )
    )

    async def cancelled_stream() -> AsyncIterator[DownloadEvent]:
        """async generator：首个元素前抛 CancelledError。"""

        if True:
            raise CancelledError("cancelled")
        yield _terminal_event(DownloadEventType.FILING_COMPLETED, document_id="fil_1")

    host = _FakeSecWorkflowHost(
        context=context,
        batching=batching,
        single_filing_events=[],
    )
    host._stream_override = cancelled_stream

    async def collect() -> None:
        with pytest.raises(CancelledError):
            async for _event in run_download_stream_impl(
                host,
                ticker="AAPL",
                form_type="10-K",
                start_date="2024-01-01",
                end_date="2024-12-31",
                overwrite=False,
                rebuild=False,
                ticker_aliases=None,
                cancel_checker=None,
                parse_date=parse_date,
                extract_sec_ticker_aliases=extract_sec_ticker_aliases,
                merge_ticker_aliases=merge_ticker_aliases,
                clear_filings_dir=lambda repo, ticker: repo.clear_filing_documents(ticker),
                load_rejection_registry=_sec_load_rejection_registry,
                save_rejection_registry=_sec_save_rejection_registry,
                should_warn_missing_sc13=should_warn_missing_sc13,
                warn_insufficient_filings=warn_insufficient_filings,
                warn_xbrl_missing_filings=warn_xbrl_missing_filings,
                cleanup_stale_filing_dirs=_noop_cleanup_stale_filing_dirs,
                build_download_filing_event_payload=build_download_filing_event_payload,
                provider_download_timeout_seconds=60.0,
            ):
                pass

    asyncio.run(collect())
    assert batching.rollback_calls == ["AAPL"]
    assert batching.commit_calls == []
    assert fake_store.published == []


def test_sec_provider_timeout_rolls_back_same_token(tmp_path: Path) -> None:
    """阶段 A 超时（asyncio.TimeoutError）=> rollback 同一 token 并传播。"""

    context = build_fs_storage_test_context(tmp_path)
    fake_store = _FakeStagedStore()
    context.core._file_store = fake_store
    batching = _RecordingBatching(
        FsBatchingRepository(
            tmp_path,
            repository_set=_FsRepositorySet(core=context.core),
        )
    )

    async def hanging_stream() -> AsyncIterator[DownloadEvent]:
        """永远挂起，触发 provider timeout。"""

        await asyncio.sleep(3600)
        yield _terminal_event(DownloadEventType.FILING_COMPLETED, document_id="fil_1")

    host = _FakeSecWorkflowHost(
        context=context,
        batching=batching,
        single_filing_events=[],
    )
    host._stream_override = hanging_stream

    async def collect() -> None:
        with pytest.raises(TimeoutError):
            async for _event in run_download_stream_impl(
                host,
                ticker="AAPL",
                form_type="10-K",
                start_date="2024-01-01",
                end_date="2024-12-31",
                overwrite=False,
                rebuild=False,
                ticker_aliases=None,
                cancel_checker=None,
                parse_date=parse_date,
                extract_sec_ticker_aliases=extract_sec_ticker_aliases,
                merge_ticker_aliases=merge_ticker_aliases,
                clear_filings_dir=lambda repo, ticker: repo.clear_filing_documents(ticker),
                load_rejection_registry=_sec_load_rejection_registry,
                save_rejection_registry=_sec_save_rejection_registry,
                should_warn_missing_sc13=should_warn_missing_sc13,
                warn_insufficient_filings=warn_insufficient_filings,
                warn_xbrl_missing_filings=warn_xbrl_missing_filings,
                cleanup_stale_filing_dirs=_noop_cleanup_stale_filing_dirs,
                build_download_filing_event_payload=build_download_filing_event_payload,
                provider_download_timeout_seconds=0.05,
            ):
                pass

    asyncio.run(collect())
    assert batching.rollback_calls == ["AAPL"]
    assert batching.commit_calls == []
    assert fake_store.published == []


# ========== CN per-filing terminal ==========


class _FakeCnDiscovery:
    """CN 下载 discovery fake：写真实临时 PDF，支持失败注入。"""

    def __init__(self, *, temp_dir: Path, fail_download: bool = False) -> None:
        self.temp_dir = temp_dir
        self.fail_download = fail_download
        self.download_calls = 0

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
        """返回空候选（本 harness 直调阶段机，只走 download）。"""

        del query, profile
        return ()

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """写入临时 PDF 并返回资产。"""

        self.download_calls += 1
        if self.fail_download:
            raise RuntimeError("provider download failed")
        path = self.temp_dir / f"{candidate.source_id}_{self.download_calls}.pdf"
        path.write_bytes(_PDF_BYTES)
        return DownloadedReportAsset(
            candidate=candidate,
            pdf_path=path,
            sha256=hashlib.sha256(_PDF_BYTES).hexdigest(),
            content_length=len(_PDF_BYTES),
            downloaded_at="2026-04-01T00:00:00+00:00",
        )


class _FakeCnConverter:
    """CN Docling 转换 fake：返回固定字节。"""

    def __init__(self) -> None:
        self.calls = 0

    def convert(self, raw_data: bytes, stream_name: str) -> bytes:
        """转换。"""

        del raw_data, stream_name
        self.calls += 1
        return _DOCLING_BYTES


def _cn_candidate(*, source_id: str = "A1") -> CnReportCandidate:
    """构造 CN 候选。"""

    return CnReportCandidate(
        provider="cninfo",
        source_id=source_id,
        source_url=f"https://static.cninfo.test/{source_id}.pdf",
        title="贵州茅台：2024年年度报告",
        language="zh",
        filing_date="2025-04-01",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
        content_length=len(_PDF_BYTES),
        etag='"v1"',
        last_modified="Wed, 01 Apr 2026 00:00:00 GMT",
    )


def _cn_profile(ticker: str) -> CnCompanyProfile:
    """构造公司基础元数据。"""

    return CnCompanyProfile(
        provider="cninfo",
        company_id="CNINFO:9900000600",
        company_name="贵州茅台",
        ticker=ticker,
    )


def _build_cn_harness(
    tmp_path: Path,
) -> tuple[FsStorageTestContext, _FakeStagedStore, _RecordingBatching, CnPreparationGate]:
    """构造 CN 单 filing 测试装配。"""

    context = build_fs_storage_test_context(tmp_path)
    fake_store = _FakeStagedStore()
    context.core._file_store = fake_store
    batching = _RecordingBatching(
        FsBatchingRepository(
            tmp_path,
            repository_set=_FsRepositorySet(core=context.core),
        )
    )
    gate = CnPreparationGate(capacity=1)
    return context, fake_store, batching, gate


async def _collect_cn_events(
    *,
    context: FsStorageTestContext,
    batching: _RecordingBatching,
    gate: CnPreparationGate,
    discovery: _FakeCnDiscovery,
    converter: _FakeCnConverter,
    overwrite: bool = False,
) -> list[DownloadEvent]:
    """收集 CN 单 filing 事件流。"""

    events: list[DownloadEvent] = []
    async for event in run_cn_download_single_filing_stream(
        source_repository=context.source_repository,
        blob_repository=context.blob_repository,
        processed_repository=context.processed_repository,
        discovery_client=discovery,
        pdf_download_gate=NoopCnDownloadPdfGate(),
        convert_pdf_to_docling_json=converter.convert,
        ticker="600519",
        profile=_cn_profile("600519"),
        candidate=_cn_candidate(),
        overwrite=overwrite,
        cancel_checker=None,
        module=_MODULE,
        batching_repository=batching,
        preparation_gate=gate,
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_cn_exactly_one_completed_commits(tmp_path: Path) -> None:
    """CN 成功下载：恰好一个 FILING_COMPLETED、唯一 begin + commit、零 rollback。"""

    context, fake_store, batching, gate = _build_cn_harness(tmp_path)
    events = await _collect_cn_events(
        context=context,
        batching=batching,
        gate=gate,
        discovery=_FakeCnDiscovery(temp_dir=tmp_path),
        converter=_FakeCnConverter(),
    )
    terminal = [
        event
        for event in events
        if event.event_type in {
            DownloadEventType.FILING_COMPLETED,
            DownloadEventType.FILING_FAILED,
        }
    ]
    assert [event.event_type for event in terminal] == [DownloadEventType.FILING_COMPLETED]
    assert batching.begin_calls == ["600519"]
    assert batching.commit_calls == ["600519"]
    assert batching.rollback_calls == []
    assert fake_store.published
    assert all(key.startswith("600519/filings/") for key in fake_store.published)


@pytest.mark.asyncio
async def test_cn_stage_a_failure_zero_begin(tmp_path: Path) -> None:
    """CN 阶段 A provider 失败：FILING_FAILED、零 begin、零 publish。"""

    context, fake_store, batching, gate = _build_cn_harness(tmp_path)
    events = await _collect_cn_events(
        context=context,
        batching=batching,
        gate=gate,
        discovery=_FakeCnDiscovery(temp_dir=tmp_path, fail_download=True),
        converter=_FakeCnConverter(),
    )
    assert [event.event_type for event in events] == [DownloadEventType.FILING_FAILED]
    assert batching.begin_calls == []
    assert batching.commit_calls == []
    assert batching.rollback_calls == []
    assert fake_store.published == []


@pytest.mark.asyncio
async def test_cn_stage_c_failure_rolls_back_same_token(tmp_path: Path) -> None:
    """CN 阶段 C（已 begin）staging 写入失败：rollback 同一 token、零 publish。"""

    context, fake_store, batching, gate = _build_cn_harness(tmp_path)
    fake_store.fail_stage = True
    with pytest.raises(OSError, match="stage failed"):
        await _collect_cn_events(
            context=context,
            batching=batching,
            gate=gate,
            discovery=_FakeCnDiscovery(temp_dir=tmp_path),
            converter=_FakeCnConverter(),
        )
    assert batching.begin_calls == ["600519"]
    assert batching.rollback_calls == ["600519"]
    assert batching.commit_calls == []
    assert fake_store.published == []
