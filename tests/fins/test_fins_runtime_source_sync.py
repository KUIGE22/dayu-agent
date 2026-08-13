"""Default Fins facade delegation tests for the dedicated source-sync owner."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import get_type_hints

import pytest

from dayu.fins.domain.source_sync import FinsWorkerSyncOutcome, FinsWorkerSyncRequest, FinsWorkerSyncResult
from dayu.fins.service_runtime import DefaultFinsRuntime, FinsRuntimeProtocol
from dayu.fins.source_sync_runtime import DefaultFinsWorkerSourceSyncRuntime
from tests.fins.evidence_locator_testkit import build_evidence_runtime_context

pytestmark = pytest.mark.unit


def _request() -> FinsWorkerSyncRequest:
    return FinsWorkerSyncRequest(
        ticker="AAPL",
        exchange_mic="XNAS",
        forms=("10-K",),
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 12),
        max_documents=5,
        max_events=50,
    )


def _result() -> FinsWorkerSyncResult:
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


def _runtime() -> DefaultFinsRuntime:
    ctx = build_evidence_runtime_context({})
    return DefaultFinsRuntime(
        workspace_root=Path("/tmp/fins-source-sync-runtime"),
        company_repository=ctx.company_repository,
        source_repository=ctx.source_repository,
        processed_repository=ctx.processed_repository,
        blob_repository=ctx.blob_repository,
        filing_maintenance_repository=ctx.filing_maintenance_repository,
        processor_registry=ctx.processor_registry,
    )


class _Component:
    def __init__(self) -> None:
        self.calls: list[tuple[FinsWorkerSyncRequest, Callable[[], bool]]] = []

    async def sync_worker_source(
        self,
        request: FinsWorkerSyncRequest,
        *,
        cancel_checker: Callable[[], bool],
    ) -> FinsWorkerSyncResult:
        self.calls.append((request, cancel_checker))
        return _result()


@pytest.mark.asyncio
async def test_default_fins_runtime_eagerly_delegates_source_sync_to_direct_owned_component_without_duplicate_state_machine() -> None:
    runtime = _runtime()
    eager = runtime._source_sync_runtime
    assert isinstance(eager, DefaultFinsWorkerSourceSyncRuntime)
    assert eager.pipeline_factory is runtime
    assert eager.source_repository is runtime.source_repository
    assert eager.evidence_locator_owner is runtime
    component = _Component()
    object.__setattr__(runtime, "_source_sync_runtime", component)
    def checker() -> bool:
        return False

    request = _request()
    assert await runtime.sync_worker_source(request, cancel_checker=checker) == _result()
    assert component.calls == [(request, checker)]


def test_default_fins_runtime_create_eagerly_constructs_source_sync_component(tmp_path: Path) -> None:
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    assert runtime._source_sync_runtime.pipeline_factory is runtime
    assert runtime._source_sync_runtime.source_repository is runtime.source_repository
    assert runtime._source_sync_runtime.evidence_locator_owner is runtime


def test_source_sync_component_fins_runtime_protocol_and_default_runtime_signatures_are_identical_required_keyword_only() -> None:
    methods = (
        DefaultFinsWorkerSourceSyncRuntime.sync_worker_source,
        FinsRuntimeProtocol.sync_worker_source,
        DefaultFinsRuntime.sync_worker_source,
    )
    signatures = [inspect.signature(method) for method in methods]
    assert signatures[0] == signatures[1] == signatures[2]
    for method, signature in zip(methods, signatures, strict=True):
        checker = signature.parameters["cancel_checker"]
        assert checker.kind is inspect.Parameter.KEYWORD_ONLY
        assert checker.default is inspect.Parameter.empty
        hints = get_type_hints(method)
        assert hints["request"] is FinsWorkerSyncRequest
        assert hints["return"] is FinsWorkerSyncResult


def test_default_fins_runtime_build_source_sync_pipeline_delegates_existing_market_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    sentinel = object()
    calls: list[str] = []

    def _build(ticker: str) -> object:
        calls.append(ticker)
        return sentinel

    monkeypatch.setattr(runtime, "_build_pipeline_for_ticker", _build)
    assert runtime.build_source_sync_pipeline("AAPL") is sentinel
    assert calls == ["AAPL"]
