"""Direct tests for the bounded worker source-sync runtime owner."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Coroutine
from dataclasses import replace
from datetime import date, datetime
from io import BytesIO
from typing import Any, cast

import pytest

import dayu.fins.source_sync_runtime as source_sync_module
from dayu.contracts.cancellation import CancelledError
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.evidence_locator import (
    EvidenceLocatorProjection,
    EvidenceLocatorRequest,
)
from dayu.fins.domain.source_sync import (
    FinsWorkerSourceDocument,
    FinsWorkerSyncOutcome,
    FinsWorkerSyncRequest,
    FinsWorkerSyncResult,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.source_sync_runtime import (
    DefaultFinsWorkerSourceSyncRuntime,
    FinsDownloadPipelineFactoryProtocol,
    FinsEvidenceLocatorOwnerProtocol,
    FinsSourceSyncDownloadPipelineProtocol,
)
from dayu.fins.storage import SourceDocumentRepositoryProtocol

pytestmark = pytest.mark.unit

_FINGERPRINT = "a" * 64
_PRIMARY = b"verified source bytes"


class _Source:
    def open(self) -> BytesIO:
        return BytesIO(_PRIMARY)


class _Repository:
    def __init__(self, *, missing: bool = False, drift: bool = False) -> None:
        self.missing = missing
        self.drift = drift
        self.meta_calls: list[tuple[str, str, SourceKind]] = []
        self.primary_calls: list[tuple[str, str, SourceKind]] = []

    def get_source_meta(self, ticker: str, document_id: str, source_kind: SourceKind) -> dict[str, Any]:
        self.meta_calls.append((ticker, document_id, source_kind))
        if self.missing:
            raise FileNotFoundError(document_id)
        return {
            "ticker": ticker,
            "document_id": document_id,
            "form_type": "10-K" if not self.drift else "10-Q",
            "filing_date": "2026-08-11",
            "ingest_complete": True,
            "is_deleted": False,
            "document_version": "v1",
            "source_fingerprint": _FINGERPRINT,
        }

    def get_primary_source(self, ticker: str, document_id: str, source_kind: SourceKind) -> _Source:
        self.primary_calls.append((ticker, document_id, source_kind))
        return _Source()


class _LocatorOwner:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[EvidenceLocatorRequest] = []
        self.validated: list[EvidenceLocatorProjection] = []

    def resolve_evidence_locator(self, request: EvidenceLocatorRequest) -> EvidenceLocatorProjection:
        self.requests.append(request)
        if self.fail:
            raise ValueError("readback drift")
        return EvidenceLocatorProjection(
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

    def validate_evidence_locator(self, locator: EvidenceLocatorProjection) -> None:
        if self.fail:
            raise ValueError("readback drift")
        self.validated.append(locator)


class _TrackedStream(AsyncGenerator[DownloadEvent, None]):
    def __init__(
        self,
        events: list[DownloadEvent],
        *,
        error: BaseException | None = None,
        close_error: BaseException | None = None,
        block_iteration: bool = False,
        block_close: bool = False,
    ) -> None:
        self._events = iter(events)
        self._error = error
        self._close_error = close_error
        self._block_iteration = block_iteration
        self._block_close = block_close
        self._error_raised = False
        self.iteration_started = asyncio.Event()
        self.iteration_release = asyncio.Event()
        self.iteration_cancel: asyncio.CancelledError | None = None
        self.close_started = asyncio.Event()
        self.close_release = asyncio.Event()
        self.close_completed = False
        self.close_task: asyncio.Task[BaseException | None] | None = None
        self.aclose_calls = 0

    def __aiter__(self) -> _TrackedStream:
        return self

    async def __anext__(self) -> DownloadEvent:
        if self._block_iteration:
            self.iteration_started.set()
            try:
                await self.iteration_release.wait()
            except asyncio.CancelledError as exc:
                self.iteration_cancel = exc
                raise
        try:
            return next(self._events)
        except StopIteration:
            if self._error is not None and not self._error_raised:
                self._error_raised = True
                raise self._error
            raise StopAsyncIteration

    async def asend(self, value: None) -> DownloadEvent:
        return await self.__anext__()

    async def athrow(self, *args: Any) -> DownloadEvent:
        raise StopAsyncIteration

    async def aclose(self) -> None:
        self.aclose_calls += 1
        current_task = asyncio.current_task()
        assert current_task is not None
        self.close_task = cast(asyncio.Task[BaseException | None], current_task)
        self.close_started.set()
        if self._block_close:
            await self.close_release.wait()
        self.close_completed = True
        if self._close_error is not None:
            raise self._close_error


class _Pipeline:
    def __init__(self, stream: _TrackedStream) -> None:
        self.stream = stream
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append(
            {
                "ticker": ticker,
                "form_type": form_type,
                "start_date": start_date,
                "end_date": end_date,
                "overwrite": overwrite,
                "rebuild": rebuild,
                "ticker_aliases": ticker_aliases,
                "cancel_checker": cancel_checker,
            }
        )
        return self.stream


class _Factory:
    def __init__(self, pipeline: _Pipeline) -> None:
        self.pipeline = pipeline
        self.tickers: list[str] = []

    def build_source_sync_pipeline(self, ticker: str) -> FinsSourceSyncDownloadPipelineProtocol:
        self.tickers.append(ticker)
        return self.pipeline


def _request(*, max_documents: int = 5, max_events: int = 50) -> FinsWorkerSyncRequest:
    return FinsWorkerSyncRequest(
        ticker="AAPL",
        exchange_mic="XNAS",
        forms=("10-K",),
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 12),
        max_documents=max_documents,
        max_events=max_events,
    )


def _started(*, document_id: str = "fil_1") -> DownloadEvent:
    return DownloadEvent(
        event_type=DownloadEventType.FILING_STARTED,
        ticker="AAPL",
        document_id=document_id,
        payload={
            "form_type": "10-K",
            "filing_date": "2026-08-11",
            "report_date": "2026-06-30",
            "accession_number": document_id.removeprefix("fil_"),
            "total_filings": 1,
        },
    )


def _terminal(
    *,
    status: str = "downloaded",
    document_id: str = "fil_1",
    reason_code: str | None = None,
    mirror_drift: bool = False,
) -> DownloadEvent:
    nested: dict[str, Any] = {
        "document_id": document_id,
        "internal_document_id": document_id.removeprefix("fil_"),
        "status": status,
        "form_type": "10-K",
        "filing_date": "2026-08-11",
        "report_date": "2026-06-30",
        "downloaded_files": 1 if status == "downloaded" else 0,
        "skipped_files": 1 if status == "skipped" else 0,
        "has_xbrl": False,
    }
    if reason_code is not None:
        nested["reason_code"] = reason_code
        nested["skip_reason"] = reason_code
    payload = {"filing_result": dict(nested), **nested}
    if mirror_drift:
        payload["status"] = "failed"
    return DownloadEvent(
        event_type=(DownloadEventType.FILING_FAILED if status == "failed" else DownloadEventType.FILING_COMPLETED),
        ticker="AAPL",
        document_id=document_id,
        payload=payload,
    )


def _completed(terminals: list[DownloadEvent], *, status: str = "ok") -> DownloadEvent:
    filings = [dict(event.payload["filing_result"]) for event in terminals]
    counts = {
        "downloaded": sum(item["status"] == "downloaded" for item in filings),
        "skipped": sum(item["status"] == "skipped" for item in filings),
        "failed": sum(item["status"] == "failed" for item in filings),
    }
    result: dict[str, Any] = {
        "pipeline": "sec",
        "action": "download",
        "status": status,
        "ticker": "AAPL",
        "filters": {
            "forms": ["10-K"],
            "start_dates": {"10-K": "2026-08-10"},
            "end_date": "2026-08-12",
            "overwrite": False,
        },
        "filings": filings,
        "summary": {"total": len(filings), **counts},
    }
    return DownloadEvent(
        event_type=DownloadEventType.PIPELINE_COMPLETED,
        ticker="AAPL",
        payload={"result": result},
    )


def _events(*terminals: DownloadEvent, status: str = "ok") -> list[DownloadEvent]:
    return [
        DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="AAPL"),
        *sum(([_started(document_id=event.document_id or "fil_1"), event] for event in terminals), []),
        _completed(list(terminals), status=status),
    ]


def _runtime(
    events: list[DownloadEvent],
    *,
    repository: _Repository | None = None,
    locator_owner: _LocatorOwner | None = None,
    error: BaseException | None = None,
    close_error: BaseException | None = None,
    block_iteration: bool = False,
    block_close: bool = False,
) -> tuple[DefaultFinsWorkerSourceSyncRuntime, _Pipeline, _TrackedStream]:
    stream = _TrackedStream(
        events,
        error=error,
        close_error=close_error,
        block_iteration=block_iteration,
        block_close=block_close,
    )
    pipeline = _Pipeline(stream)
    runtime = DefaultFinsWorkerSourceSyncRuntime(
        pipeline_factory=cast(FinsDownloadPipelineFactoryProtocol, _Factory(pipeline)),
        source_repository=cast(SourceDocumentRepositoryProtocol, repository or _Repository()),
        evidence_locator_owner=cast(FinsEvidenceLocatorOwnerProtocol, locator_owner or _LocatorOwner()),
    )
    return runtime, pipeline, stream


def _assert_owned_close_reaped(
    stream: _TrackedStream,
    *,
    expected_error: BaseException | None = None,
) -> None:
    """断言 runtime 唯一 close task 已终止、取结果且无 orphan。

    Args:
        stream: 记录 direct-inner 关闭状态的受控流。
        expected_error: close 协程应作为值返回的原始异常。

    Returns:
        无。

    Raises:
        AssertionError: close 未完成、未 reap、重入或遗留 task 时抛出。
    """

    assert stream.aclose_calls == 1
    assert stream.close_completed is True
    close_task = stream.close_task
    assert close_task is not None
    assert close_task.get_name() == source_sync_module._SOURCE_SYNC_CLOSE_TASK_NAME
    assert close_task.done() and close_task.exception() is None
    assert close_task.result() is expected_error
    assert close_task not in asyncio.all_tasks()
    assert not any(
        task.get_name() == source_sync_module._SOURCE_SYNC_CLOSE_TASK_NAME
        for task in asyncio.all_tasks()
    )


def _cn_request() -> FinsWorkerSyncRequest:
    return FinsWorkerSyncRequest(
        ticker="600519",
        exchange_mic="XSHG",
        forms=("FY",),
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 12),
        max_documents=5,
        max_events=50,
    )


def _cn_terminal(*, candidate_not_found: bool = False) -> DownloadEvent:
    if candidate_not_found:
        nested: dict[str, Any] = {
            "document_id": "",
            "status": "skipped",
            "form_type": "FY",
            "filing_date": None,
            "report_date": None,
            "downloaded_files": 0,
            "skipped_files": 0,
            "failed_files": [],
            "has_xbrl": False,
            "reason_code": "candidate_not_found",
            "reason_message": "主源未返回对应财期报告",
            "skip_reason": "candidate_not_found",
        }
        document_id = None
    else:
        nested = {
            "document_id": "fil_cn_1",
            "status": "failed",
            "form_type": "FY",
            "filing_date": "2026-08-11",
            "report_date": None,
            "fiscal_year": 2026,
            "fiscal_period": "FY",
            "source_id": "source-cn-1",
            "downloaded_files": 0,
            "skipped_files": 0,
            "failed_files": [],
            "has_xbrl": False,
            "reason_code": "provider_failed",
            "reason_message": "provider failed",
        }
        document_id = "fil_cn_1"
    return DownloadEvent(
        event_type=(
            DownloadEventType.FILING_COMPLETED
            if candidate_not_found
            else DownloadEventType.FILING_FAILED
        ),
        ticker="600519",
        document_id=document_id,
        payload={"filing_result": dict(nested), **nested},
    )


def _cn_events(terminal: DownloadEvent) -> list[DownloadEvent]:
    events = [DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="600519")]
    if terminal.document_id is not None:
        events.append(
            DownloadEvent(
                event_type=DownloadEventType.FILING_STARTED,
                ticker="600519",
                document_id="fil_cn_1",
                payload={
                    "form_type": "FY",
                    "filing_date": "2026-08-11",
                    "fiscal_year": 2026,
                    "fiscal_period": "FY",
                    "source_id": "source-cn-1",
                },
            )
        )
    events.append(terminal)
    nested = dict(terminal.payload["filing_result"])
    counts = {
        "downloaded": int(nested["status"] == "downloaded"),
        "skipped": int(nested["status"] == "skipped"),
        "failed": int(nested["status"] == "failed"),
    }
    events.append(
        DownloadEvent(
            event_type=DownloadEventType.PIPELINE_COMPLETED,
            ticker="600519",
            payload={
                "result": {
                    "pipeline": "cn",
                    "action": "download",
                    "status": "ok",
                    "ticker": "600519",
                    "filters": {
                        "forms": ["FY"],
                        "start_dates": {"FY": "2026-08-10"},
                        "end_date": "2026-08-12",
                        "overwrite": False,
                    },
                    "filings": [nested],
                    "summary": {"total": 1, **counts},
                }
            },
        )
    )
    return events


def _asia_request(
    *,
    ticker: str,
    exchange_mic: str,
    forms: tuple[str, ...],
) -> FinsWorkerSyncRequest:
    """构造 CN/HK 共用的有界测试请求。

    Args:
        ticker: 规范 CN 或 HK 股票代码。
        exchange_mic: 与 ticker 一致的交易所 MIC。
        forms: 严格排序的目标财期集合。

    Returns:
        可供 public runtime 消费的规范请求。

    Raises:
        ValueError: ticker、MIC 或 forms 不符合 DTO 边界时抛出。
    """

    return FinsWorkerSyncRequest(
        ticker=ticker,
        exchange_mic=exchange_mic,
        forms=forms,
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 12),
        max_documents=5,
        max_events=50,
    )


def _asia_started(
    *,
    ticker: str,
    form_type: str,
    document_id: str,
    source_id: str,
) -> DownloadEvent:
    """构造带完整 provider identity 的 Asia ordinary started 事件。

    Args:
        ticker: 事件股票代码。
        form_type: 财期 form。
        document_id: ordinary filing 文档标识。
        source_id: provider candidate 标识。

    Returns:
        完整 ``FILING_STARTED`` 事件。

    Raises:
        无。
    """

    return DownloadEvent(
        event_type=DownloadEventType.FILING_STARTED,
        ticker=ticker,
        document_id=document_id,
        payload={
            "form_type": form_type,
            "filing_date": "2026-08-11",
            "fiscal_year": 2026,
            "fiscal_period": form_type,
            "source_id": source_id,
        },
    )


def _asia_failed_terminal(
    *,
    ticker: str,
    form_type: str,
    document_id: str,
    source_id: str,
) -> DownloadEvent:
    """构造与 started identity 完全一致的 Asia ordinary failed 终态。

    Args:
        ticker: 事件股票代码。
        form_type: 财期 form。
        document_id: ordinary filing 文档标识。
        source_id: provider candidate 标识。

    Returns:
        nested/flat mirror 精确一致的 ``FILING_FAILED`` 事件。

    Raises:
        无。
    """

    nested: dict[str, Any] = {
        "document_id": document_id,
        "status": "failed",
        "form_type": form_type,
        "filing_date": "2026-08-11",
        "report_date": None,
        "fiscal_year": 2026,
        "fiscal_period": form_type,
        "source_id": source_id,
        "downloaded_files": 0,
        "skipped_files": 0,
        "failed_files": [],
        "has_xbrl": False,
        "reason_code": "provider_failed",
        "reason_message": "provider failed",
    }
    return DownloadEvent(
        event_type=DownloadEventType.FILING_FAILED,
        ticker=ticker,
        document_id=document_id,
        payload={"filing_result": dict(nested), **nested},
    )


def _asia_candidate_not_found(*, ticker: str, form_type: str) -> DownloadEvent:
    """构造无 document identity 的 Asia ``candidate_not_found`` 终态。

    Args:
        ticker: 事件股票代码。
        form_type: 确认无 candidate 的财期 form。

    Returns:
        合法 synthetic filing terminal。

    Raises:
        无。
    """

    nested: dict[str, Any] = {
        "document_id": "",
        "status": "skipped",
        "form_type": form_type,
        "filing_date": None,
        "report_date": None,
        "downloaded_files": 0,
        "skipped_files": 0,
        "failed_files": [],
        "has_xbrl": False,
        "reason_code": "candidate_not_found",
        "reason_message": "provider returned no candidate",
        "skip_reason": "candidate_not_found",
    }
    return DownloadEvent(
        event_type=DownloadEventType.FILING_COMPLETED,
        ticker=ticker,
        document_id=None,
        payload={"filing_result": dict(nested), **nested},
    )


def _asia_events(
    *,
    ticker: str,
    forms: tuple[str, ...],
    body: list[DownloadEvent],
) -> list[DownloadEvent]:
    """用真实 terminal 发射顺序构造不能洗掉矛盾的 pipeline mirror。

    Args:
        ticker: 事件与 pipeline 共用的股票代码。
        forms: 请求的规范 form 集合。
        body: started 与 filing terminal 的实际发射序列。

    Returns:
        包含 pipeline started/body/completed 的完整事件流。

    Raises:
        KeyError: terminal 测试数据缺少 nested filing result 时抛出。
    """

    terminals = [
        event
        for event in body
        if event.event_type
        in {DownloadEventType.FILING_COMPLETED, DownloadEventType.FILING_FAILED}
    ]
    filings = [dict(event.payload["filing_result"]) for event in terminals]
    summary = {
        "total": len(filings),
        "downloaded": sum(item["status"] == "downloaded" for item in filings),
        "skipped": sum(item["status"] == "skipped" for item in filings),
        "failed": sum(item["status"] == "failed" for item in filings),
    }
    completed = DownloadEvent(
        event_type=DownloadEventType.PIPELINE_COMPLETED,
        ticker=ticker,
        payload={
            "result": {
                "pipeline": "cn",
                "action": "download",
                "status": "ok",
                "ticker": ticker,
                "filters": {
                    "forms": list(forms),
                    "start_dates": {form: "2026-08-10" for form in forms},
                    "end_date": "2026-08-12",
                    "overwrite": False,
                },
                "filings": filings,
                "summary": summary,
            }
        },
    )
    return [
        DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker=ticker),
        *body,
        completed,
    ]


def _replace_terminal_identity(
    events: list[DownloadEvent],
    *,
    field_name: str,
    value: Any,
    missing: bool,
) -> None:
    terminal = events[-2]
    nested = terminal.payload["filing_result"]
    if missing:
        nested.pop(field_name)
        terminal.payload.pop(field_name)
    else:
        nested[field_name] = value
        terminal.payload[field_name] = value
    events[-1].payload["result"]["filings"][0] = dict(nested)


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "error_type"),
    (
        ("ticker", 1, TypeError),
        ("ticker", "", ValueError),
        ("ticker", "A-", ValueError),
        ("ticker", "A--B", ValueError),
        ("ticker", "1234567", ValueError),
        ("ticker", "1A", ValueError),
        ("ticker", "aapl", ValueError),
        ("ticker", "AAPL.US", ValueError),
        ("exchange_mic", "xnas", ValueError),
        ("forms", [], ValueError),
        ("forms", (), ValueError),
        ("forms", (" 10-K",), ValueError),
        ("forms", ("10-Q", "10-K"), ValueError),
        ("start_date", datetime(2026, 8, 10), TypeError),
        ("end_date", datetime(2026, 8, 12), TypeError),
        ("start_date", date(2026, 8, 13), ValueError),
        ("max_documents", True, TypeError),
        ("max_documents", 0, ValueError),
        ("max_events", False, TypeError),
        ("max_events", 16_065, ValueError),
    ),
)
def test_fins_worker_sync_request_rejects_every_noncanonical_or_out_of_bounds_field(
    field_name: str,
    invalid_value: Any,
    error_type: type[Exception],
) -> None:
    request = _request()
    object.__setattr__(request, field_name, invalid_value)
    with pytest.raises(error_type):
        request.__post_init__()


@pytest.mark.parametrize("ticker", ("AAPL", "BRK-B", "0700", "600519", "000333"))
def test_fins_worker_sync_request_accepts_each_supported_canonical_ticker_shape(ticker: str) -> None:
    assert replace(_request(), ticker=ticker).ticker == ticker


@pytest.mark.asyncio
async def test_fins_worker_document_and_result_dtos_reject_every_closed_shape_drift() -> None:
    runtime, _, _ = _runtime(_events(_terminal()))
    valid = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    document = valid.documents[0]

    invalid_documents: tuple[tuple[str, Any, type[Exception]], ...] = (
        ("document_id", "", ValueError),
        ("form_type", " 10-K", ValueError),
        ("source_observed_date", datetime(2026, 8, 11), TypeError),
        ("locator_sha256", "x", ValueError),
        ("locator_sha256", "0" * 64, ValueError),
    )
    for field_name, invalid_value, error_type in invalid_documents:
        candidate = replace(document)
        object.__setattr__(candidate, field_name, invalid_value)
        with pytest.raises(error_type):
            candidate.__post_init__()

    drifted_locator = replace(document.locator, document_id="fil_2")
    locator_drift = replace(document)
    object.__setattr__(locator_drift, "locator", drifted_locator)
    object.__setattr__(locator_drift, "locator_sha256", source_sync_module.sha256_hex(drifted_locator.to_json()))
    with pytest.raises(ValueError, match="document_id"):
        locator_drift.__post_init__()

    second_locator = replace(document.locator, document_id="fil_2")
    second = FinsWorkerSourceDocument(
        document_id="fil_2",
        form_type=document.form_type,
        source_observed_date=document.source_observed_date,
        locator=second_locator,
        locator_sha256=source_sync_module.sha256_hex(second_locator.to_json()),
    )
    empty = _empty_sync_result()
    object.__setattr__(empty, "outcome", "complete")
    with pytest.raises(TypeError):
        empty.__post_init__()
    empty = _empty_sync_result()
    object.__setattr__(empty, "documents", [])
    with pytest.raises(TypeError):
        empty.__post_init__()

    invalid_results = (
        FinsWorkerSyncResult(
            outcome=FinsWorkerSyncOutcome.COMPLETE,
            documents=(document, second),
            latest_source_observed_date=document.source_observed_date,
            discovered_count=2,
            downloaded_count=2,
            reused_count=0,
            ignored_count=0,
            failed_count=0,
        ),
    )
    assert invalid_results[0].documents == (document, second)

    result = replace(invalid_results[0])
    object.__setattr__(result, "documents", (second, document))
    with pytest.raises(ValueError, match="sorted"):
        result.__post_init__()
    result = replace(invalid_results[0])
    object.__setattr__(result, "documents", (document, document))
    with pytest.raises(ValueError, match="unique"):
        result.__post_init__()

    invalid_shapes = (
        _empty_sync_result(),
        _empty_sync_result(),
        _empty_sync_result(),
        FinsWorkerSyncResult(
            outcome=FinsWorkerSyncOutcome.COMPLETE,
            documents=(document,),
            latest_source_observed_date=document.source_observed_date,
            discovered_count=1,
            downloaded_count=1,
            reused_count=0,
            ignored_count=0,
            failed_count=0,
        ),
    )
    count_drift, discovered_drift, document_count_drift, latest_drift = invalid_shapes
    object.__setattr__(count_drift, "failed_count", True)
    object.__setattr__(discovered_drift, "discovered_count", 1)
    object.__setattr__(document_count_drift, "documents", (document,))
    object.__setattr__(latest_drift, "latest_source_observed_date", None)
    for candidate in invalid_shapes:
        with pytest.raises(ValueError):
            candidate.__post_init__()

    complete_with_failure = _empty_sync_result()
    object.__setattr__(complete_with_failure, "discovered_count", 1)
    object.__setattr__(complete_with_failure, "failed_count", 1)
    partial_without_document = _empty_sync_result()
    object.__setattr__(partial_without_document, "outcome", FinsWorkerSyncOutcome.PARTIAL)
    object.__setattr__(partial_without_document, "discovered_count", 1)
    object.__setattr__(partial_without_document, "failed_count", 1)
    unavailable_with_document = replace(valid)
    object.__setattr__(unavailable_with_document, "outcome", FinsWorkerSyncOutcome.UNAVAILABLE)
    unavailable_without_failure = _empty_sync_result()
    object.__setattr__(unavailable_without_failure, "outcome", FinsWorkerSyncOutcome.UNAVAILABLE)
    object.__setattr__(unavailable_without_failure, "discovered_count", 1)
    object.__setattr__(unavailable_without_failure, "ignored_count", 1)
    rate_limited_with_counts = _empty_sync_result()
    object.__setattr__(rate_limited_with_counts, "outcome", FinsWorkerSyncOutcome.RATE_LIMITED)
    object.__setattr__(rate_limited_with_counts, "discovered_count", 1)
    object.__setattr__(rate_limited_with_counts, "ignored_count", 1)
    outcome_shapes = (
        complete_with_failure,
        partial_without_document,
        unavailable_with_document,
        unavailable_without_failure,
        rate_limited_with_counts,
    )
    for candidate in outcome_shapes:
        with pytest.raises(ValueError):
            candidate._validate_outcome_shape()


def _empty_sync_result() -> FinsWorkerSyncResult:
    return FinsWorkerSyncResult(
        outcome=FinsWorkerSyncOutcome.COMPLETE,
        documents=(),
        latest_source_observed_date=None,
        discovered_count=0,
        downloaded_count=0,
        reused_count=0,
        ignored_count=0,
        failed_count=0,
    )


def test_source_sync_private_ingress_strictly_copies_json_and_parses_market_specific_wire() -> None:
    assert source_sync_module._copy_json_value(1.25) == 1.25
    assert source_sync_module._copy_json_value([{"value": True}]) == [{"value": True}]
    with pytest.raises(source_sync_module._InvariantError, match="key"):
        source_sync_module._copy_json_value(cast(Any, {1: "value"}))
    with pytest.raises(source_sync_module._InvariantError, match="not JSON"):
        source_sync_module._copy_json_value(cast(Any, ("value",)))
    with pytest.raises(source_sync_module._InvariantError, match="object"):
        source_sync_module._copy_json_object(cast(Any, []))
    with pytest.raises(source_sync_module._InvariantError, match="canonical text"):
        source_sync_module._require_text(" value", "field")
    with pytest.raises(source_sync_module._InvariantError, match="integer"):
        source_sync_module._require_int(-1, "field")
    with pytest.raises(source_sync_module._InvariantError, match="ISO calendar"):
        source_sync_module._require_date("2026-02-30", "field")
    with pytest.raises(source_sync_module._InvariantError, match="canonical ISO"):
        source_sync_module._require_date("20260811", "field")

    cn_started_event = DownloadEvent(
        event_type=DownloadEventType.FILING_STARTED,
        ticker="000001",
        document_id="fil_cn_1",
        payload={
            "form_type": "FY",
            "filing_date": "2026-08-11",
            "report_date": None,
            "fiscal_year": 2026,
            "fiscal_period": "FY",
            "source_id": "source-cn-1",
        },
    )
    cn_started = source_sync_module._parse_started(cn_started_event, market="CN")
    assert (cn_started.fiscal_year, cn_started.fiscal_period, cn_started.source_id) == (
        2026,
        "FY",
        "source-cn-1",
    )

    without_nested = DownloadEvent(
        event_type=DownloadEventType.FILING_COMPLETED,
        ticker="AAPL",
        document_id="fil_1",
        payload={},
    )
    with pytest.raises(source_sync_module._InvariantError, match="filing_result"):
        source_sync_module._parse_terminal(without_nested)
    invalid_completed = _terminal(status="failed")
    object.__setattr__(invalid_completed, "event_type", DownloadEventType.FILING_COMPLETED)
    with pytest.raises(source_sync_module._InvariantError, match="filing_completed"):
        source_sync_module._parse_terminal(invalid_completed)
    invalid_failed = _terminal()
    object.__setattr__(invalid_failed, "event_type", DownloadEventType.FILING_FAILED)
    with pytest.raises(source_sync_module._InvariantError, match="filing_failed"):
        source_sync_module._parse_terminal(invalid_failed)

    candidate_payload: dict[str, Any] = {
        "document_id": "",
        "status": "skipped",
        "form_type": "FY",
        "filing_date": None,
        "report_date": None,
        "reason_code": "candidate_not_found",
        "skip_reason": "candidate_not_found",
    }
    candidate_event = DownloadEvent(
        event_type=DownloadEventType.FILING_COMPLETED,
        ticker="000001",
        document_id=None,
        payload={"filing_result": dict(candidate_payload), **candidate_payload},
    )
    candidate = source_sync_module._parse_terminal(candidate_event)
    candidate_request = _request()
    object.__setattr__(candidate_request, "ticker", "000001")
    object.__setattr__(candidate_request, "exchange_mic", "XSHE")
    object.__setattr__(candidate_request, "forms", ("FY",))
    state = source_sync_module._CollectionState()
    assert source_sync_module._correlate_terminal(
        candidate_event,
        candidate,
        state,
        candidate_request,
        market="CN",
    )
    with pytest.raises(source_sync_module._InvariantError, match="candidate_not_found"):
        source_sync_module._correlate_terminal(
            candidate_event,
            candidate,
            state,
            candidate_request,
            market="CN",
        )


@pytest.mark.asyncio
async def test_source_sync_runtime_rejects_malformed_event_order_and_maps_pre_stream_failures() -> None:
    malformed_streams = (
        [DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="MSFT")],
        [
            DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="AAPL"),
            DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="AAPL"),
        ],
        [DownloadEvent(event_type=DownloadEventType.COMPANY_RESOLVED, ticker="AAPL")],
        [
            DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="AAPL"),
            _started(),
            _started(),
        ],
        [
            DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="AAPL"),
            DownloadEvent(
                event_type=DownloadEventType.FILE_DOWNLOADED,
                ticker="AAPL",
                document_id="orphan",
            ),
        ],
        [DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="AAPL")],
        [
            DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="AAPL"),
            _started(),
            _completed([]),
        ],
    )
    for events in malformed_streams:
        runtime, _, _ = _runtime(events)
        result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
        assert result.outcome is FinsWorkerSyncOutcome.INVARIANT_FAILED

    runtime, _, _ = _runtime(_events())
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: True)).outcome is (
        FinsWorkerSyncOutcome.CANCELLED
    )
    cancelled_events = _events(status="cancelled")
    runtime, _, _ = _runtime(cancelled_events)
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.CANCELLED
    )

    valid_with_progress = _events()
    valid_with_progress.insert(1, DownloadEvent(event_type=DownloadEventType.COMPANY_RESOLVED, ticker="AAPL"))
    runtime, _, _ = _runtime(valid_with_progress)
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.COMPLETE
    )

    class _FailingFactory:
        def __init__(self, error: BaseException) -> None:
            self.error = error

        def build_source_sync_pipeline(self, ticker: str) -> FinsSourceSyncDownloadPipelineProtocol:
            del ticker
            raise self.error

    for error, expected in (
        (CancelledError("cancel"), FinsWorkerSyncOutcome.CANCELLED),
        (RuntimeError("provider unavailable"), FinsWorkerSyncOutcome.UNAVAILABLE),
    ):
        runtime = DefaultFinsWorkerSourceSyncRuntime(
            pipeline_factory=_FailingFactory(error),
            source_repository=cast(SourceDocumentRepositoryProtocol, _Repository()),
            evidence_locator_owner=cast(FinsEvidenceLocatorOwnerProtocol, _LocatorOwner()),
        )
        assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is expected

    runtime = DefaultFinsWorkerSourceSyncRuntime(
        pipeline_factory=_FailingFactory(asyncio.CancelledError()),
        source_repository=cast(SourceDocumentRepositoryProtocol, _Repository()),
        evidence_locator_owner=cast(FinsEvidenceLocatorOwnerProtocol, _LocatorOwner()),
    )
    with pytest.raises(asyncio.CancelledError):
        await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)


@pytest.mark.asyncio
async def test_fins_worker_sync_rejects_unknown_market_and_cross_market_form_before_stream_creation() -> None:
    runtime, pipeline, _ = _runtime([])
    unsupported_market = _request()
    object.__setattr__(unsupported_market, "exchange_mic", "XHKG")
    assert (await runtime.sync_worker_source(unsupported_market, cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.UNSUPPORTED_MARKET
    )
    unsupported_form = _request()
    object.__setattr__(unsupported_form, "forms", ("FY",))
    assert (await runtime.sync_worker_source(unsupported_form, cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.UNSUPPORTED_FORM
    )
    assert pipeline.calls == []


@pytest.mark.asyncio
async def test_fins_source_sync_runtime_maps_worker_request_to_exact_pipeline_call_arguments() -> None:
    runtime, pipeline, _ = _runtime(_events())
    await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert pipeline.calls == [
        {
            "ticker": "AAPL",
            "form_type": "10-K",
            "start_date": "2026-08-10",
            "end_date": "2026-08-12",
            "overwrite": False,
            "rebuild": False,
            "ticker_aliases": ["AAPL"],
            "cancel_checker": pipeline.calls[0]["cancel_checker"],
        }
    ]


@pytest.mark.asyncio
async def test_fins_worker_sync_correlates_each_filing_terminal_with_pipeline_terminal_exactly() -> None:
    terminal = _terminal()
    runtime, _, _ = _runtime(_events(terminal))
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.COMPLETE
    assert result.downloaded_count == 1
    assert result.documents[0].document_id == "fil_1"


@pytest.mark.parametrize(
    ("field_name", "mismatch"),
    (
        ("report_date", "2026-03-31"),
        ("internal_document_id", "wrong-accession"),
    ),
)
@pytest.mark.parametrize("missing", (True, False))
@pytest.mark.asyncio
async def test_sec_ordinary_terminal_requires_each_report_and_accession_identity_field(
    field_name: str,
    mismatch: Any,
    missing: bool,
) -> None:
    terminal = _terminal(status="failed")
    events = _events(terminal)
    _replace_terminal_identity(
        events,
        field_name=field_name,
        value=mismatch,
        missing=missing,
    )
    runtime, _, _ = _runtime(events)
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.INVARIANT_FAILED
    assert result.documents == ()
    assert result.discovered_count == 0


@pytest.mark.asyncio
async def test_sec_started_requires_report_date_key_and_optional_terminal_accession_must_match() -> None:
    events = _events(_terminal(status="failed"))
    events[1].payload.pop("report_date")
    runtime, _, _ = _runtime(events)
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.INVARIANT_FAILED
    )

    events = _events(_terminal(status="failed"))
    _replace_terminal_identity(
        events,
        field_name="accession_number",
        value="wrong-accession",
        missing=False,
    )
    runtime, _, _ = _runtime(events)
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.INVARIANT_FAILED
    )


@pytest.mark.parametrize(
    ("field_name", "mismatch"),
    (
        ("fiscal_year", 2025),
        ("fiscal_period", "H1"),
        ("source_id", "other-source"),
    ),
)
@pytest.mark.parametrize("missing", (True, False))
@pytest.mark.asyncio
async def test_cn_hk_ordinary_terminal_requires_each_provider_candidate_identity_field(
    field_name: str,
    mismatch: Any,
    missing: bool,
) -> None:
    events = _cn_events(_cn_terminal())
    _replace_terminal_identity(
        events,
        field_name=field_name,
        value=mismatch,
        missing=missing,
    )
    runtime, _, _ = _runtime(events)
    result = await runtime.sync_worker_source(_cn_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.INVARIANT_FAILED
    assert result.documents == ()
    assert result.discovered_count == 0


@pytest.mark.asyncio
async def test_cn_candidate_not_found_remains_the_only_terminal_identity_exception() -> None:
    events = _cn_events(_cn_terminal(candidate_not_found=True))
    runtime, _, _ = _runtime(events)
    result = await runtime.sync_worker_source(_cn_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.COMPLETE
    assert result.ignored_count == 1
    assert result.documents == ()


@pytest.mark.parametrize(
    ("ticker", "exchange_mic"),
    (("600519", "XSHG"), ("0700", "XHKG")),
)
@pytest.mark.parametrize(
    "event_order",
    ("candidate_started_terminal", "started_candidate_terminal", "started_terminal_candidate"),
)
@pytest.mark.asyncio
async def test_cn_hk_candidate_not_found_and_same_form_ordinary_are_mutually_exclusive_in_every_order(
    ticker: str,
    exchange_mic: str,
    event_order: str,
) -> None:
    """锁定 CN/HK 同 form synthetic 与 ordinary 事实在三种顺序下都互斥。

    Args:
        ticker: 当前市场的规范 ticker。
        exchange_mic: 与 ticker 一致的 MIC。
        event_order: synthetic/started/ordinary terminal 的相对顺序。

    Returns:
        无。

    Raises:
        AssertionError: 矛盾 wire 未 fail closed 或泄漏局部 counts 时抛出。
    """

    candidate = _asia_candidate_not_found(ticker=ticker, form_type="FY")
    started = _asia_started(
        ticker=ticker,
        form_type="FY",
        document_id="fil_asia_1",
        source_id="source-asia-1",
    )
    terminal = _asia_failed_terminal(
        ticker=ticker,
        form_type="FY",
        document_id="fil_asia_1",
        source_id="source-asia-1",
    )
    orders = {
        "candidate_started_terminal": [candidate, started, terminal],
        "started_candidate_terminal": [started, candidate, terminal],
        "started_terminal_candidate": [started, terminal, candidate],
    }
    runtime, _, stream = _runtime(
        _asia_events(ticker=ticker, forms=("FY",), body=orders[event_order])
    )
    result = await runtime.sync_worker_source(
        _asia_request(ticker=ticker, exchange_mic=exchange_mic, forms=("FY",)),
        cancel_checker=lambda: False,
    )

    assert result.outcome is FinsWorkerSyncOutcome.INVARIANT_FAILED
    assert result.documents == ()
    assert (
        result.discovered_count,
        result.downloaded_count,
        result.reused_count,
        result.ignored_count,
        result.failed_count,
    ) == (0, 0, 0, 0, 0)
    assert stream.aclose_calls == 1


@pytest.mark.parametrize(
    ("ticker", "exchange_mic"),
    (("600519", "XSHG"), ("0700", "XHKG")),
)
@pytest.mark.parametrize("candidate_first", (True, False))
@pytest.mark.asyncio
async def test_cn_hk_candidate_and_ordinary_on_different_forms_remain_legal(
    ticker: str,
    exchange_mic: str,
    candidate_first: bool,
) -> None:
    """证明互斥只限同 form，不同 form 的 synthetic/ordinary 在两种顺序均合法。

    Args:
        ticker: 当前市场的规范 ticker。
        exchange_mic: 与 ticker 一致的 MIC。
        candidate_first: synthetic terminal 是否先于 ordinary 组发射。

    Returns:
        无。

    Raises:
        AssertionError: 合法反例被过度收紧或 counts 不一致时抛出。
    """

    candidate = _asia_candidate_not_found(ticker=ticker, form_type="FY")
    ordinary = [
        _asia_started(
            ticker=ticker,
            form_type="H1",
            document_id="fil_asia_h1",
            source_id="source-asia-h1",
        ),
        _asia_failed_terminal(
            ticker=ticker,
            form_type="H1",
            document_id="fil_asia_h1",
            source_id="source-asia-h1",
        ),
    ]
    body = [candidate, *ordinary] if candidate_first else [*ordinary, candidate]
    runtime, _, stream = _runtime(
        _asia_events(ticker=ticker, forms=("FY", "H1"), body=body)
    )
    result = await runtime.sync_worker_source(
        _asia_request(
            ticker=ticker,
            exchange_mic=exchange_mic,
            forms=("FY", "H1"),
        ),
        cancel_checker=lambda: False,
    )

    assert result.outcome is FinsWorkerSyncOutcome.UNAVAILABLE
    assert result.documents == ()
    assert (result.discovered_count, result.ignored_count, result.failed_count) == (2, 1, 1)
    assert stream.aclose_calls == 1


@pytest.mark.asyncio
async def test_asia_same_form_multiple_ordinary_and_distinct_form_candidates_remain_legal_but_duplicate_candidate_fails() -> None:
    """锁定同 form 多 ordinary 与异 form synthetic 合法，同 form synthetic 重复仍失败。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 互斥边界过宽或过窄时抛出。
    """

    request = _asia_request(ticker="600519", exchange_mic="XSHG", forms=("FY",))
    ordinary_body: list[DownloadEvent] = []
    for suffix in ("1", "2"):
        ordinary_body.extend(
            (
                _asia_started(
                    ticker="600519",
                    form_type="FY",
                    document_id=f"fil_asia_{suffix}",
                    source_id=f"source-asia-{suffix}",
                ),
                _asia_failed_terminal(
                    ticker="600519",
                    form_type="FY",
                    document_id=f"fil_asia_{suffix}",
                    source_id=f"source-asia-{suffix}",
                ),
            )
        )
    runtime, _, _ = _runtime(
        _asia_events(ticker="600519", forms=("FY",), body=ordinary_body)
    )
    ordinary_result = await runtime.sync_worker_source(
        request,
        cancel_checker=lambda: False,
    )
    assert ordinary_result.outcome is FinsWorkerSyncOutcome.UNAVAILABLE
    assert (ordinary_result.discovered_count, ordinary_result.failed_count) == (2, 2)

    distinct_candidates = [
        _asia_candidate_not_found(ticker="600519", form_type="FY"),
        _asia_candidate_not_found(ticker="600519", form_type="H1"),
    ]
    runtime, _, _ = _runtime(
        _asia_events(
            ticker="600519",
            forms=("FY", "H1"),
            body=distinct_candidates,
        )
    )
    distinct_result = await runtime.sync_worker_source(
        _asia_request(
            ticker="600519",
            exchange_mic="XSHG",
            forms=("FY", "H1"),
        ),
        cancel_checker=lambda: False,
    )
    assert distinct_result.outcome is FinsWorkerSyncOutcome.COMPLETE
    assert (distinct_result.discovered_count, distinct_result.ignored_count) == (2, 2)

    duplicate = _asia_candidate_not_found(ticker="600519", form_type="FY")
    runtime, _, stream = _runtime(
        _asia_events(ticker="600519", forms=("FY",), body=[duplicate, duplicate])
    )
    duplicate_result = await runtime.sync_worker_source(
        request,
        cancel_checker=lambda: False,
    )
    assert duplicate_result.outcome is FinsWorkerSyncOutcome.INVARIANT_FAILED
    assert duplicate_result.discovered_count == 0
    assert stream.aclose_calls == 1


@pytest.mark.asyncio
async def test_filing_terminal_uses_nested_filing_result_and_rejects_flat_mirror_drift() -> None:
    terminal = _terminal(mirror_drift=True)
    runtime, _, _ = _runtime(_events(terminal))
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.INVARIANT_FAILED


@pytest.mark.asyncio
async def test_candidate_not_found_is_cn_hk_only_without_started_or_document_identity() -> None:
    candidate = {
        "document_id": "",
        "status": "skipped",
        "form_type": "FY",
        "filing_date": None,
        "report_date": None,
        "downloaded_files": 0,
        "skipped_files": 0,
        "failed_files": [],
        "has_xbrl": False,
        "reason_code": "candidate_not_found",
        "skip_reason": "candidate_not_found",
        "reason_message": "none",
    }
    event = DownloadEvent(
        event_type=DownloadEventType.FILING_COMPLETED,
        ticker="AAPL",
        payload={"filing_result": candidate, **candidate},
    )
    runtime, _, _ = _runtime(
        [DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="AAPL"), event, _completed([event])]
    )
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.INVARIANT_FAILED
    )


@pytest.mark.asyncio
async def test_pipeline_terminal_is_unique_last_cleanly_exhausted_and_summary_exact() -> None:
    runtime, _, _ = _runtime(_events() + [DownloadEvent(event_type=DownloadEventType.COMPANY_RESOLVED, ticker="AAPL")])
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.INVARIANT_FAILED
    )
    bad = _events()
    result = bad[-1].payload["result"]
    result["summary"]["total"] = 1
    runtime, _, _ = _runtime(bad)
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.INVARIANT_FAILED
    )


@pytest.mark.asyncio
async def test_pipeline_status_failed_after_prior_terminal_discards_buffers_without_success_summary_check() -> None:
    terminal = _terminal()
    events = _events(terminal, status="failed")
    events[-1].payload["result"]["filings"] = []
    events[-1].payload["result"]["summary"] = {"total": 0, "downloaded": 0, "skipped": 0, "failed": 0}
    runtime, _, _ = _runtime(events)
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.UNAVAILABLE
    assert result.documents == ()


@pytest.mark.asyncio
async def test_pipeline_status_ok_with_only_failed_filings_is_unavailable_with_correlated_counts() -> None:
    terminal = _terminal(status="failed")
    runtime, _, _ = _runtime(_events(terminal))
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.UNAVAILABLE
    assert (result.discovered_count, result.failed_count) == (1, 1)


@pytest.mark.asyncio
async def test_status_ok_mixed_downloaded_reused_and_failed_maps_partial_batch_retryable_with_verified_documents_preserved() -> None:
    downloaded = _terminal()
    failed = _terminal(status="failed", document_id="fil_2")
    runtime, _, _ = _runtime(_events(downloaded, failed))
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.PARTIAL
    assert (result.downloaded_count, result.failed_count, len(result.documents)) == (1, 1, 1)


@pytest.mark.asyncio
async def test_untyped_429_503_or_exception_text_never_infers_rate_limited() -> None:
    for error in (RuntimeError("HTTP 429"), RuntimeError("provider 503 rate limited")):
        runtime, _, _ = _runtime([], error=error)
        result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
        assert result.outcome is FinsWorkerSyncOutcome.UNAVAILABLE


@pytest.mark.asyncio
async def test_source_sync_does_not_recursive_validate_sec_file_event_payload_with_real_file_object_meta() -> None:
    terminal = _terminal()
    events = _events(terminal)
    events.insert(
        2,
        DownloadEvent(
            event_type=DownloadEventType.FILE_DOWNLOADED,
            ticker="AAPL",
            document_id="fil_1",
            payload={"legacy": BytesIO(b"not JSON")},
        ),
    )
    runtime, _, _ = _runtime(events)
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.COMPLETE
    )


@pytest.mark.asyncio
async def test_source_sync_rejects_non_json_or_nonfinite_owned_filing_and_pipeline_result_subtrees() -> None:
    terminal = _terminal()
    terminal.payload["filing_result"]["bad"] = float("nan")
    terminal.payload["bad"] = float("nan")
    runtime, _, _ = _runtime(_events(terminal))
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.INVARIANT_FAILED
    )


@pytest.mark.asyncio
async def test_source_sync_public_result_contains_no_download_event_mapping_or_raw_any() -> None:
    runtime, _, _ = _runtime(_events(_terminal()))
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert set(result.__slots__) == {
        "outcome",
        "documents",
        "latest_source_observed_date",
        "discovered_count",
        "downloaded_count",
        "reused_count",
        "ignored_count",
        "failed_count",
    }


@pytest.mark.asyncio
async def test_zero_total_or_all_ignored_is_healthy_no_change_with_zero_documents() -> None:
    runtime, _, _ = _runtime(_events())
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.COMPLETE
    assert result.documents == ()


@pytest.mark.asyncio
async def test_all_raw_skipped_with_verified_reused_document_is_succeeded_not_no_change() -> None:
    terminal = _terminal(status="skipped", reason_code="not_modified")
    runtime, _, _ = _runtime(_events(terminal))
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.COMPLETE
    assert result.reused_count == 1


@pytest.mark.asyncio
async def test_skipped_existing_complete_meta_returns_reused_verified_locator() -> None:
    terminal = _terminal(status="skipped", reason_code="already_downloaded_complete")
    locator = _LocatorOwner()
    runtime, _, _ = _runtime(_events(terminal), locator_owner=locator)
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.reused_count == 1
    assert len(locator.requests) == len(locator.validated) == 1


@pytest.mark.asyncio
async def test_skipped_missing_meta_with_closed_non_materialized_reason_is_ignored() -> None:
    terminal = _terminal(status="skipped", reason_code="6k_filtered")
    runtime, _, _ = _runtime(_events(terminal), repository=_Repository(missing=True))
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.COMPLETE
    assert result.ignored_count == 1


@pytest.mark.asyncio
async def test_unknown_skip_reason_or_meta_drift_is_invariant_failed() -> None:
    for repository, reason in ((_Repository(), "unknown"), (_Repository(drift=True), "not_modified")):
        runtime, _, _ = _runtime(_events(_terminal(status="skipped", reason_code=reason)), repository=repository)
        assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
            FinsWorkerSyncOutcome.INVARIANT_FAILED
        )


@pytest.mark.asyncio
async def test_locator_uses_exact_meta_primary_bytes_hash_and_passes_readback_validation() -> None:
    locator = _LocatorOwner()
    runtime, _, _ = _runtime(_events(_terminal()), locator_owner=locator)
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    request = locator.requests[0]
    from hashlib import sha256

    assert request.primary_content_sha256 == sha256(_PRIMARY).hexdigest()
    assert request.locator_content_sha256 == request.primary_content_sha256
    assert result.documents[0].locator in locator.validated


@pytest.mark.asyncio
async def test_locator_projection_recursively_contains_no_path_uri_bucket_or_key() -> None:
    runtime, _, _ = _runtime(_events(_terminal()))
    result = await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    raw = result.documents[0].locator.to_json().decode()
    assert all(token not in raw for token in ('"path"', '"uri"', '"bucket"', '"key"'))


@pytest.mark.asyncio
async def test_download_event_limit_and_document_limit_fail_closed_one_over_without_truncation() -> None:
    runtime, _, stream = _runtime(_events(_terminal()))
    result = await runtime.sync_worker_source(_request(max_events=3), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.INVARIANT_FAILED
    assert stream.aclose_calls == 1
    runtime, _, stream = _runtime(_events(_terminal(), _terminal(document_id="fil_2")))
    result = await runtime.sync_worker_source(_request(max_documents=1), cancel_checker=lambda: False)
    assert result.outcome is FinsWorkerSyncOutcome.INVARIANT_FAILED
    assert result.documents == ()
    assert stream.aclose_calls == 1


@pytest.mark.asyncio
async def test_asyncio_cancellation_re_raises_and_domain_cancellation_returns_typed_cancelled() -> None:
    runtime, _, stream = _runtime([], error=CancelledError("cancel"))
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.CANCELLED
    )
    assert stream.aclose_calls == 1


@pytest.mark.asyncio
async def test_stream_primary_outcome_wins_over_direct_inner_close_failure_exactly_once() -> None:
    asyncio_primary = asyncio.CancelledError("task cancelled")
    runtime, _, stream = _runtime(
        [],
        error=asyncio_primary,
        close_error=RuntimeError("close failed"),
    )
    with pytest.raises(asyncio.CancelledError) as raised:
        await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert raised.value is asyncio_primary
    assert stream.aclose_calls == 1

    runtime, _, stream = _runtime(
        [],
        error=CancelledError("domain cancel"),
        close_error=RuntimeError("close failed"),
    )
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.CANCELLED
    )
    assert stream.aclose_calls == 1

    runtime, _, stream = _runtime(
        [DownloadEvent(event_type=DownloadEventType.COMPANY_RESOLVED, ticker="AAPL")],
        close_error=RuntimeError("close failed"),
    )
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.INVARIANT_FAILED
    )
    assert stream.aclose_calls == 1

    runtime, _, stream = _runtime(
        [],
        error=RuntimeError("provider failed"),
        close_error=RuntimeError("close failed"),
    )
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.UNAVAILABLE
    )
    assert stream.aclose_calls == 1

    runtime, _, stream = _runtime(
        _events(),
        close_error=RuntimeError("close failed"),
    )
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is (
        FinsWorkerSyncOutcome.UNAVAILABLE
    )
    assert stream.aclose_calls == 1


@pytest.mark.parametrize("primary_kind", ("generic", "domain", "invariant"))
@pytest.mark.asyncio
async def test_cleanup_wait_cancellation_outranks_generic_domain_and_invariant_after_close_is_reaped(
    primary_kind: str,
) -> None:
    """关闭等待期真实 task cancel 必须高于已观察的业务终态。

    Args:
        primary_kind: cancel 前 body 已观察的异常类别。

    Returns:
        无。

    Raises:
        AssertionError: cleanup cancel 未获胜或 close task 未收敛时抛出。
    """

    if primary_kind == "generic":
        events: list[DownloadEvent] = []
        body_error: BaseException | None = RuntimeError("provider failed")
    elif primary_kind == "domain":
        events = []
        body_error = CancelledError("domain cancel")
    else:
        events = [DownloadEvent(event_type=DownloadEventType.COMPANY_RESOLVED, ticker="AAPL")]
        body_error = None
    runtime, _, stream = _runtime(
        events,
        error=body_error,
        block_close=True,
    )
    owner_task = asyncio.create_task(
        runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    )
    await stream.close_started.wait()
    assert owner_task.cancel(f"{primary_kind} cleanup cancel") is True
    await asyncio.sleep(0)
    stream.close_release.set()

    with pytest.raises(asyncio.CancelledError) as raised:
        await owner_task
    assert raised.value.args == (f"{primary_kind} cleanup cancel",)
    assert owner_task.cancelled() is True
    assert owner_task.cancelling() == 1
    assert any("secondary body error" in note for note in raised.value.__notes__)
    _assert_owned_close_reaped(stream)


@pytest.mark.asyncio
async def test_body_asyncio_cancel_identity_survives_multiple_cleanup_cancels_until_close_is_reaped() -> None:
    """第一份 body cancel 必须在多次 cleanup cancel 下保持身份且等待关闭完成。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: cancel identity/count 漂移或 close task 未收敛时抛出。
    """

    runtime, _, stream = _runtime(
        [],
        block_iteration=True,
        block_close=True,
    )
    owner_task = asyncio.create_task(
        runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    )
    await stream.iteration_started.wait()
    assert owner_task.cancel("body-first") is True
    await stream.close_started.wait()
    first_cancel = stream.iteration_cancel
    assert first_cancel is not None

    assert owner_task.cancel("cleanup-second") is True
    await asyncio.sleep(0)
    assert owner_task.cancel("cleanup-third") is True
    await asyncio.sleep(0)
    stream.close_release.set()

    with pytest.raises(asyncio.CancelledError) as raised:
        await owner_task
    assert raised.value is first_cancel
    assert owner_task.cancelled() is True
    assert owner_task.cancelling() == 3
    assert any("cleanup-second" in note for note in raised.value.__notes__)
    assert all("cleanup-third" not in note for note in raised.value.__notes__)
    _assert_owned_close_reaped(stream)


@pytest.mark.parametrize(
    "close_error",
    (
        asyncio.CancelledError("intrinsic close cancel"),
        KeyboardInterrupt("close interrupt"),
        SystemExit("close exit"),
    ),
)
@pytest.mark.asyncio
async def test_intrinsic_close_cancel_and_process_exit_propagate_only_after_owned_task_is_reaped(
    close_error: BaseException,
) -> None:
    """关闭自身的 asyncio/process-exit 必须作为值回收后再原样传播。

    Args:
        close_error: close 协程内生成的原始取消或进程级异常。

    Returns:
        无。

    Raises:
        AssertionError: 异常身份漂移或 close task 未收敛时抛出。
    """

    runtime, _, stream = _runtime(_events(), close_error=close_error)
    with pytest.raises(type(close_error)) as raised:
        await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert raised.value is close_error
    _assert_owned_close_reaped(stream, expected_error=close_error)


@pytest.mark.asyncio
async def test_close_failure_is_primary_only_without_stream_primary_and_never_converts_process_exit() -> None:
    close_cancel = asyncio.CancelledError("close cancelled")
    runtime, _, stream = _runtime(_events(), close_error=close_cancel)
    with pytest.raises(asyncio.CancelledError) as raised:
        await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert raised.value is close_cancel
    assert stream.aclose_calls == 1

    for primary in (KeyboardInterrupt("interrupt"), SystemExit("exit")):
        runtime, _, stream = _runtime(
            [],
            error=primary,
            close_error=RuntimeError("close failed"),
        )
        with pytest.raises(type(primary)) as raised_exit:
            await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
        assert raised_exit.value is primary
        assert stream.aclose_calls == 1
    runtime, _, stream = _runtime([], error=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    assert stream.aclose_calls == 1


@pytest.mark.asyncio
async def test_fins_source_sync_runtime_closes_pipeline_stream_once_on_success_error_domain_and_asyncio_cancel() -> None:
    cases: tuple[tuple[BaseException | None, FinsWorkerSyncOutcome | None], ...] = (
        (None, FinsWorkerSyncOutcome.COMPLETE),
        (RuntimeError("boom"), FinsWorkerSyncOutcome.UNAVAILABLE),
        (CancelledError("cancel"), FinsWorkerSyncOutcome.CANCELLED),
        (asyncio.CancelledError(), None),
    )
    for error, outcome in cases:
        runtime, _, stream = _runtime(_events() if error is None else [], error=error)
        if outcome is None:
            with pytest.raises(asyncio.CancelledError):
                await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
        else:
            assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)).outcome is outcome
        assert stream.aclose_calls == 1


@pytest.mark.asyncio
async def test_stream_outcome_priority_is_asyncio_then_external_cancel_then_proven_invariant_then_exception_then_clean_terminal() -> None:
    runtime, _, _ = _runtime([], error=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    runtime, _, _ = _runtime(_events(), error=RuntimeError("late"))
    checks = iter((False, True))
    assert (await runtime.sync_worker_source(_request(), cancel_checker=lambda: next(checks, True))).outcome is (
        FinsWorkerSyncOutcome.CANCELLED
    )
    runtime, _, _ = _runtime(_events())
    checks = iter((False, False, True))
    assert (
        await runtime.sync_worker_source(_request(max_events=1), cancel_checker=lambda: next(checks, True))
    ).outcome is FinsWorkerSyncOutcome.CANCELLED


def test_fins_source_sync_runtime_owner_has_narrow_factory_repository_locator_dependencies_and_no_default_runtime_cycle() -> None:
    assert tuple(DefaultFinsWorkerSourceSyncRuntime.__dataclass_fields__) == (
        "pipeline_factory",
        "source_repository",
        "evidence_locator_owner",
    )
    assert "DefaultFinsRuntime" not in __import__("dayu.fins.source_sync_runtime", fromlist=["x"]).__dict__


def test_pipeline_protocol_and_every_download_owner_return_typed_async_generator_with_aclose() -> None:
    import inspect
    from typing import get_origin, get_type_hints

    from dayu.fins.downloaders.sec_downloader import SecDownloader
    from dayu.fins.ingestion.pipeline_backends import PipelineIngestionBackend, PipelineIngestionSourceProtocol
    from dayu.fins.ingestion.service import FinsIngestionService, IngestionBackendProtocol
    from dayu.fins.pipelines.base import PipelineProtocol
    from dayu.fins.pipelines.cn_download_filing_workflow import run_cn_download_single_filing_stream
    from dayu.fins.pipelines.cn_download_workflow import run_cn_download_stream_impl
    from dayu.fins.pipelines.cn_pipeline import CnPipeline
    from dayu.fins.pipelines.sec_download_filing_workflow import run_download_single_filing_stream
    from dayu.fins.pipelines.sec_download_persistence import _RejectedArtifactDownloaderProtocol
    from dayu.fins.pipelines.sec_download_workflow import SecDownloadWorkflowHost, run_download_stream_impl
    from dayu.fins.pipelines.sec_pipeline import SecPipeline
    from dayu.fins.source_sync_runtime import FinsSourceSyncDownloadPipelineProtocol

    owners = (
        FinsSourceSyncDownloadPipelineProtocol.download_stream,
        PipelineProtocol.download_stream,
        IngestionBackendProtocol.download_stream,
        PipelineIngestionSourceProtocol.download_stream_impl,
        SecPipeline.download_stream,
        SecPipeline.download_stream_impl,
        SecPipeline._download_single_filing_stream,
        CnPipeline.download_stream,
        CnPipeline.download_stream_impl,
        FinsIngestionService.download_stream,
        PipelineIngestionBackend.download_stream,
        SecDownloadWorkflowHost._download_single_filing_stream,
        run_download_stream_impl,
        run_download_single_filing_stream,
        run_cn_download_stream_impl,
        run_cn_download_single_filing_stream,
        SecDownloader.download_files_stream,
        _RejectedArtifactDownloaderProtocol.download_files_stream,
    )
    assert len(owners) == 18
    assert all(get_origin(get_type_hints(owner)["return"]) is AsyncGenerator for owner in owners)
    assert inspect.isasyncgenfunction(DefaultFinsWorkerSourceSyncRuntime.sync_worker_source) is False


def test_source_sync_does_not_expose_coroutine_as_outer_aclose_target() -> None:
    runtime, _, _ = _runtime(_events())
    coroutine: Coroutine[Any, Any, Any] = runtime.sync_worker_source(_request(), cancel_checker=lambda: False)
    try:
        assert not hasattr(coroutine, "aclose")
    finally:
        coroutine.close()


def test_download_stream_owner_path_contains_no_getattr_hasattr_cast_ignore_or_legacy_download_files_fallback() -> None:
    import inspect

    from dayu.fins.pipelines.sec_download_filing_workflow import run_download_single_filing_stream
    from dayu.fins.pipelines.sec_download_persistence import persist_rejected_filing_artifact
    from dayu.fins.pipelines.sec_pipeline import SecPipeline

    sources = (
        inspect.getsource(SecPipeline._download_single_filing_stream),
        inspect.getsource(SecPipeline._persist_rejected_filing_artifact),
        inspect.getsource(run_download_single_filing_stream),
        inspect.getsource(persist_rejected_filing_artifact),
    )
    forbidden = ("getattr(", "hasattr(", "cast(", "# type: ignore", ".download_files(")
    assert all(token not in source for source in sources for token in forbidden)
