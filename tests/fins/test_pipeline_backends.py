"""Download-only ingestion wrapper ownership tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from typing import Any

import pytest

from dayu.contracts.cancellation import CancelledError
from dayu.fins.ingestion.pipeline_backends import PipelineIngestionBackend
from dayu.fins.ingestion.process_events import ProcessEvent, ProcessEventType
from dayu.fins.ingestion.service import FinsIngestionService
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType

pytestmark = pytest.mark.unit


class _TrackedStream(AsyncGenerator[DownloadEvent, None]):
    def __init__(self, *, error: BaseException | None = None, count: int = 1) -> None:
        self.remaining = count
        self.error = error
        self.error_raised = False
        self.aclose_calls = 0

    def __aiter__(self) -> _TrackedStream:
        return self

    async def __anext__(self) -> DownloadEvent:
        if self.remaining:
            self.remaining -= 1
            return DownloadEvent(event_type=DownloadEventType.PIPELINE_STARTED, ticker="AAPL")
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


class _Pipeline:
    def __init__(self, stream: _TrackedStream) -> None:
        self.stream = stream

    def download_stream_impl(
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
        del ticker, form_type, start_date, end_date, overwrite, rebuild, ticker_aliases, cancel_checker
        return self.stream

    async def process_stream_impl(
        self,
        ticker: str,
        overwrite: bool = False,
        ci: bool = False,
        document_ids: list[str] | None = None,
        *,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        del overwrite, ci, document_ids, cancel_checker
        if False:
            yield ProcessEvent(event_type=ProcessEventType.PIPELINE_STARTED, ticker=ticker)


class _Backend:
    def __init__(self, stream: _TrackedStream) -> None:
        self.stream = stream

    def download_stream(
        self,
        ticker: str,
        form_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        overwrite: bool = False,
        rebuild: bool = False,
        ticker_aliases: list[str] | None = None,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AsyncGenerator[DownloadEvent, None]:
        del ticker, form_type, start_date, end_date, overwrite, rebuild, ticker_aliases, cancel_checker
        return self.stream

    async def process_stream(
        self,
        ticker: str,
        overwrite: bool = False,
        ci: bool = False,
        document_ids: list[str] | None = None,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        del overwrite, ci, document_ids, cancel_checker
        if False:
            yield ProcessEvent(event_type=ProcessEventType.PIPELINE_STARTED, ticker=ticker)


async def _consume(stream: AsyncGenerator[DownloadEvent, None]) -> None:
    async for _ in stream:
        pass


@pytest.mark.asyncio
async def test_pipeline_backend_closes_impl_download_stream_once_on_success_error_cancel_and_outer_aclose() -> None:
    cases: tuple[BaseException | None, ...] = (None, RuntimeError("boom"), CancelledError("cancel"), asyncio.CancelledError())
    for error in cases:
        inner = _TrackedStream(error=error)
        outer = PipelineIngestionBackend(_Pipeline(inner)).download_stream(ticker="AAPL")
        if error is None:
            await _consume(outer)
        else:
            with pytest.raises(type(error)):
                await _consume(outer)
        assert inner.aclose_calls == 1
    inner = _TrackedStream(count=2)
    outer = PipelineIngestionBackend(_Pipeline(inner)).download_stream(ticker="AAPL")
    await anext(outer)
    await outer.aclose()
    assert inner.aclose_calls == 1


@pytest.mark.asyncio
async def test_ingestion_service_closes_backend_download_stream_once_on_success_error_cancel_and_outer_aclose() -> None:
    cases: tuple[BaseException | None, ...] = (None, RuntimeError("boom"), CancelledError("cancel"), asyncio.CancelledError())
    for error in cases:
        inner = _TrackedStream(error=error)
        outer = FinsIngestionService(backend=_Backend(inner)).download_stream(ticker="AAPL")
        if error is None:
            await _consume(outer)
        else:
            with pytest.raises(type(error)):
                await _consume(outer)
        assert inner.aclose_calls == 1
    inner = _TrackedStream(count=2)
    outer = FinsIngestionService(backend=_Backend(inner)).download_stream(ticker="AAPL")
    await anext(outer)
    await outer.aclose()
    assert inner.aclose_calls == 1
