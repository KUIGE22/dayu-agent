"""Fins 到 Investment 的数据源连接器与闭合注册表。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from dayu.fins.domain.evidence_locator import sha256_hex
from dayu.fins.domain.source_sync import (
    FinsWorkerSourceDocument,
    FinsWorkerSyncOutcome,
    FinsWorkerSyncRequest,
    FinsWorkerSyncResult,
)
from dayu.investment.domain.jobs import JobCancellationSignalProtocol
from dayu.investment.domain.source_evidence import (
    SourceConnectorSyncAction,
    SourceConnectorSyncDecision,
    SourceConnectorSyncRequest,
    SourceDocumentEvidence,
    SourceFinsTerminalCandidate,
    build_source_evidence_locator_document,
    validate_evidence_against_snapshot,
)
from dayu.investment.domain.source_sync import SourceConnectorKey, SourceSyncErrorCode, SourceSyncOutcome


class FinsWorkerGatewayProtocol(Protocol):
    """由 FinsService 结构满足的窄异步网关。"""

    async def sync_worker_source(
        self,
        request: FinsWorkerSyncRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> FinsWorkerSyncResult:
        """执行一次 worker 数据源同步。"""

        ...


class SourceConnectorProtocol(Protocol):
    """Investment 持有的数据源连接器契约。"""

    @property
    def connector_key(self) -> SourceConnectorKey:
        """返回闭合连接器键。"""

        ...

    async def sync(
        self,
        request: SourceConnectorSyncRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> SourceConnectorSyncDecision:
        """执行一次连接器同步并返回领域决策。"""

        ...


def _failed_candidate(error: SourceSyncErrorCode) -> SourceFinsTerminalCandidate:
    """构造全空的闭合失败候选。"""

    return SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.FAILED,
        proposed_safe_error_code=error,
        documents=(),
        records_discovered=0,
        records_downloaded=0,
        records_reused=0,
        records_ignored=0,
        records_failed=0,
        latest_source_observed_date=None,
    )


def _convert_document(
    document: FinsWorkerSourceDocument,
    request: SourceConnectorSyncRequest,
) -> SourceDocumentEvidence:
    """把 Fins 无路径投影二次封装成 Investment evidence。"""

    locator = document.locator
    if document.locator_sha256 != sha256_hex(locator.to_json()):
        raise ValueError("Fins locator projection hash drift")
    wrapper = build_source_evidence_locator_document(
        repository_id=locator.repository_id,
        ticker=locator.ticker,
        document_id=locator.document_id,
        source_kind=locator.source_kind.value,
        artifact_kind=locator.artifact_kind.value,
        document_version=locator.document_version,
        source_fingerprint=locator.source_fingerprint,
        primary_content_sha256=locator.primary_content_sha256,
        locator_kind=locator.locator_kind.value,
        locator_content_sha256=locator.locator_content_sha256,
    )
    evidence = SourceDocumentEvidence(
        document_id=document.document_id,
        form_type=document.form_type,
        source_observed_date=document.source_observed_date,
        locator=wrapper,
        locator_sha256=wrapper.document.sha256,
    )
    validate_evidence_against_snapshot(evidence, request.execution_snapshot)
    return evidence


def _convert_result(
    result: FinsWorkerSyncResult,
    request: SourceConnectorSyncRequest,
) -> SourceFinsTerminalCandidate:
    """把闭合 Fins result 映射成唯一 Source terminal candidate。"""

    documents = tuple(_convert_document(document, request) for document in result.documents)
    common = {
        "documents": documents,
        "records_discovered": result.discovered_count,
        "records_downloaded": result.downloaded_count,
        "records_reused": result.reused_count,
        "records_ignored": result.ignored_count,
        "records_failed": result.failed_count,
        "latest_source_observed_date": result.latest_source_observed_date,
    }
    if result.outcome is FinsWorkerSyncOutcome.COMPLETE:
        return SourceFinsTerminalCandidate(
            proposed_outcome=SourceSyncOutcome.SUCCEEDED if documents else SourceSyncOutcome.NO_CHANGE,
            proposed_safe_error_code=None,
            **common,
        )
    if result.outcome is FinsWorkerSyncOutcome.PARTIAL:
        return SourceFinsTerminalCandidate(
            proposed_outcome=SourceSyncOutcome.PARTIAL,
            proposed_safe_error_code=SourceSyncErrorCode.PARTIAL_BATCH,
            **common,
        )
    if result.outcome is FinsWorkerSyncOutcome.UNAVAILABLE:
        return SourceFinsTerminalCandidate(
            proposed_outcome=SourceSyncOutcome.FAILED,
            proposed_safe_error_code=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
            **common,
        )
    error = {
        FinsWorkerSyncOutcome.RATE_LIMITED: SourceSyncErrorCode.PROVIDER_RATE_LIMITED,
        FinsWorkerSyncOutcome.UNSUPPORTED_MARKET: SourceSyncErrorCode.UNSUPPORTED_MARKET,
        FinsWorkerSyncOutcome.UNSUPPORTED_FORM: SourceSyncErrorCode.UNSUPPORTED_FORM,
        FinsWorkerSyncOutcome.INVARIANT_FAILED: SourceSyncErrorCode.FINS_INVARIANT,
    }.get(result.outcome)
    if error is None:
        raise ValueError("unsupported Fins worker outcome")
    return _failed_candidate(error)


@dataclass(frozen=True, slots=True)
class FinsSourceConnector(SourceConnectorProtocol):
    """从 Investment 请求到 Fins worker 网关的单次委托适配器。"""

    fins_gateway: FinsWorkerGatewayProtocol = field(repr=False, compare=False)

    @property
    def connector_key(self) -> SourceConnectorKey:
        """返回唯一生产连接器键。"""

        return SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1

    async def sync(
        self,
        request: SourceConnectorSyncRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> SourceConnectorSyncDecision:
        """派生精确 worker 请求并把结果收窄为领域决策。"""

        snapshot = request.execution_snapshot
        config = snapshot.binding.config
        worker_request = FinsWorkerSyncRequest(
            ticker=snapshot.canonical_ticker,
            exchange_mic=snapshot.binding.exchange_mic,
            forms=tuple(sorted(config.forms)),
            start_date=snapshot.query_start_date,
            end_date=snapshot.query_end_date,
            max_documents=config.max_documents_per_sync,
            max_events=16_064,
        )
        result = await self.fins_gateway.sync_worker_source(worker_request, cancellation)
        try:
            if type(result) is not FinsWorkerSyncResult:
                raise TypeError("Fins gateway returned an invalid result type")
            result.__post_init__()
        except (TypeError, ValueError):
            return SourceConnectorSyncDecision(
                action=SourceConnectorSyncAction.COMPLETED,
                candidate=_failed_candidate(SourceSyncErrorCode.FINS_INVARIANT),
            )
        if result.outcome is FinsWorkerSyncOutcome.CANCELLED:
            return SourceConnectorSyncDecision(
                action=SourceConnectorSyncAction.CANCELLED,
                candidate=None,
            )
        try:
            candidate = _convert_result(result, request)
        except (TypeError, ValueError):
            candidate = _failed_candidate(SourceSyncErrorCode.FINS_INVARIANT)
        return SourceConnectorSyncDecision(
            action=SourceConnectorSyncAction.COMPLETED,
            candidate=candidate,
        )


class SourceConnectorRegistry:
    """拒绝重复键且不暴露修改 API 的连接器注册表。"""

    __slots__ = ("_connectors", "_by_key")

    def __init__(self, connectors: tuple[SourceConnectorProtocol, ...]) -> None:
        """防御性快照连接器并拒绝重复键。"""

        snapshot = tuple(connectors)
        by_key: dict[SourceConnectorKey, SourceConnectorProtocol] = {}
        for connector in snapshot:
            if connector.connector_key in by_key:
                raise ValueError(f"duplicate source connector key: {connector.connector_key.value}")
            by_key[connector.connector_key] = connector
        self._connectors = snapshot
        self._by_key = by_key

    def get(self, connector_key: SourceConnectorKey) -> SourceConnectorProtocol | None:
        """返回指定键对应的只读连接器。"""

        return self._by_key.get(connector_key)


__all__ = [
    "FinsSourceConnector",
    "FinsWorkerGatewayProtocol",
    "SourceConnectorProtocol",
    "SourceConnectorRegistry",
]
