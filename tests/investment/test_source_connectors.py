"""Fins source connector and immutable registry tests."""

from __future__ import annotations

import json
from datetime import date

import pytest

from dayu.fins.domain.enums import SourceKind as FinsSourceKind
from dayu.fins.domain.evidence_locator import (
    REPOSITORY_ID,
    ArtifactKind,
    DocumentLocatorPayload,
    EvidenceLocatorProjection,
    LocatorKind,
    sha256_hex,
)
from dayu.fins.domain.source_sync import (
    FinsWorkerSourceDocument,
    FinsWorkerSyncOutcome,
    FinsWorkerSyncRequest,
    FinsWorkerSyncResult,
)
from dayu.investment.connectors.source import FinsSourceConnector, SourceConnectorRegistry
from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantId
from dayu.investment.domain.jobs import JobCancellationSignalProtocol
from dayu.investment.domain.source import (
    SourceDefinitionId,
    SourceKind,
    SourceSubscriptionId,
    SubscriptionStatus,
)
from dayu.investment.domain.source_evidence import (
    SourceConnectorSyncAction,
    SourceConnectorSyncRequest,
)
from dayu.investment.domain.source_payload import (
    SourceExecutionBinding,
    SourceExecutionSnapshot,
    build_source_execution_snapshot_document,
)
from dayu.investment.domain.source_sync import (
    FINS_SOURCE_DEFINITION_KEY,
    FinsDisclosureSubscriptionConfig,
    SourceConnectorKey,
    SourceSyncErrorCode,
    SourceSyncOutcome,
)

pytestmark = pytest.mark.unit


class _Cancellation:
    def is_cancel_requested(self) -> bool:
        return False

    async def wait_cancel_requested(self) -> None:
        return None


class _Gateway:
    def __init__(self, result: FinsWorkerSyncResult) -> None:
        self.result = result
        self.calls: list[tuple[FinsWorkerSyncRequest, JobCancellationSignalProtocol]] = []

    async def sync_worker_source(
        self,
        request: FinsWorkerSyncRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> FinsWorkerSyncResult:
        self.calls.append((request, cancellation))
        return self.result


def _snapshot() -> SourceExecutionSnapshot:
    return SourceExecutionSnapshot(
        binding=SourceExecutionBinding(
            tenant_id=TenantId("tenant-connector"),
            source_definition_id=SourceDefinitionId("00000000-0000-4000-8000-000000000101"),
            source_definition_version=1,
            source_key=FINS_SOURCE_DEFINITION_KEY,
            source_kind=SourceKind.FILING,
            subscription_id=SourceSubscriptionId("00000000-0000-4000-8000-000000000102"),
            subscription_version=3,
            subscription_status=SubscriptionStatus.ENABLED,
            security_company_id=CompanyId("company-connector"),
            security_id=SecurityId("security-connector"),
            security_version=2,
            security_ticker="AAPL",
            exchange_mic="XNAS",
            security_is_active=True,
            connector_key=SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1,
            config=FinsDisclosureSubscriptionConfig(
                forms=("10-Q", "10-K"),
                lookback_days=3,
                freshness_max_age_days=7,
                failing_after=2,
                disable_after=4,
                max_documents_per_sync=17,
            ),
        ),
        canonical_ticker="AAPL",
        query_start_date=date(2026, 8, 10),
        query_end_date=date(2026, 8, 12),
    )


def _request() -> SourceConnectorSyncRequest:
    from uuid import UUID

    snapshot = _snapshot()
    document = build_source_execution_snapshot_document(snapshot)
    return SourceConnectorSyncRequest(
        operation_id=UUID("00000000-0000-4000-8000-000000000103"),
        execution_snapshot=snapshot,
        execution_snapshot_sha256=document.sha256,
    )


def _locator() -> EvidenceLocatorProjection:
    return EvidenceLocatorProjection(
        repository_id=REPOSITORY_ID,
        ticker="AAPL",
        document_id="fil_1",
        source_kind=FinsSourceKind.FILING,
        artifact_kind=ArtifactKind.SOURCE,
        document_version="v1",
        source_fingerprint="a" * 64,
        primary_content_sha256="b" * 64,
        locator_kind=LocatorKind.DOCUMENT,
        locator_payload=DocumentLocatorPayload(),
        locator_content_sha256="b" * 64,
    )


def _result(outcome: FinsWorkerSyncOutcome = FinsWorkerSyncOutcome.COMPLETE) -> FinsWorkerSyncResult:
    if outcome is FinsWorkerSyncOutcome.COMPLETE:
        locator = _locator()
        document = FinsWorkerSourceDocument(
            document_id="fil_1",
            form_type="10-K",
            source_observed_date=date(2026, 8, 11),
            locator=locator,
            locator_sha256=sha256_hex(locator.to_json()),
        )
        return FinsWorkerSyncResult(
            outcome=outcome,
            documents=(document,),
            latest_source_observed_date=document.source_observed_date,
            discovered_count=1,
            downloaded_count=1,
            reused_count=0,
            ignored_count=0,
            failed_count=0,
        )
    return FinsWorkerSyncResult(
        outcome=outcome,
        documents=(),
        latest_source_observed_date=None,
        discovered_count=0,
        downloaded_count=0,
        reused_count=0,
        ignored_count=0,
        failed_count=0,
    )


@pytest.mark.asyncio
async def test_fins_source_connector_derives_exact_worker_request_from_snapshot_and_config() -> None:
    gateway = _Gateway(_result())
    connector = FinsSourceConnector(gateway)
    cancellation = _Cancellation()
    decision = await connector.sync(_request(), cancellation)
    assert gateway.calls == [
        (
            FinsWorkerSyncRequest(
                ticker="AAPL",
                exchange_mic="XNAS",
                forms=("10-K", "10-Q"),
                start_date=date(2026, 8, 10),
                end_date=date(2026, 8, 12),
                max_documents=17,
                max_events=16_064,
            ),
            cancellation,
        )
    ]
    assert decision.action is SourceConnectorSyncAction.COMPLETED
    assert decision.candidate is not None
    assert decision.candidate.proposed_outcome is SourceSyncOutcome.SUCCEEDED


@pytest.mark.asyncio
async def test_fins_projection_hash_and_investment_wrapper_hash_are_distinct_and_fields_match() -> None:
    fins_document = _result().documents[0]
    decision = await FinsSourceConnector(_Gateway(_result())).sync(_request(), _Cancellation())
    assert decision.candidate is not None
    investment_document = decision.candidate.documents[0]
    assert fins_document.locator_sha256 != investment_document.locator_sha256
    raw = json.loads(investment_document.locator.document.canonical_bytes)
    assert raw["ticker"] == fins_document.locator.ticker
    assert raw["document_id"] == fins_document.locator.document_id
    assert raw["schema_version"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "error"),
    [
        (FinsWorkerSyncOutcome.RATE_LIMITED, SourceSyncErrorCode.PROVIDER_RATE_LIMITED),
        (FinsWorkerSyncOutcome.UNAVAILABLE, SourceSyncErrorCode.PROVIDER_UNAVAILABLE),
        (FinsWorkerSyncOutcome.UNSUPPORTED_MARKET, SourceSyncErrorCode.UNSUPPORTED_MARKET),
        (FinsWorkerSyncOutcome.UNSUPPORTED_FORM, SourceSyncErrorCode.UNSUPPORTED_FORM),
        (FinsWorkerSyncOutcome.INVARIANT_FAILED, SourceSyncErrorCode.FINS_INVARIANT),
    ],
)
async def test_fins_source_connector_maps_closed_worker_failures(
    outcome: FinsWorkerSyncOutcome,
    error: SourceSyncErrorCode,
) -> None:
    decision = await FinsSourceConnector(_Gateway(_result(outcome))).sync(_request(), _Cancellation())
    assert decision.candidate is not None
    assert decision.candidate.proposed_outcome is SourceSyncOutcome.FAILED
    assert decision.candidate.proposed_safe_error_code is error


@pytest.mark.asyncio
async def test_fins_source_connector_cancelled_returns_no_terminal_candidate() -> None:
    decision = await FinsSourceConnector(_Gateway(_result(FinsWorkerSyncOutcome.CANCELLED))).sync(
        _request(),
        _Cancellation(),
    )
    assert decision.action is SourceConnectorSyncAction.CANCELLED
    assert decision.candidate is None


@pytest.mark.asyncio
async def test_fins_source_connector_maps_every_nonclosed_worker_result_to_fins_invariant() -> None:
    malformed_results = (_result(FinsWorkerSyncOutcome.CANCELLED), _result(), _result())
    object.__setattr__(malformed_results[0], "failed_count", 1)
    object.__setattr__(malformed_results[1], "documents", ("not-a-document",))
    object.__setattr__(malformed_results[2].documents[0], "locator_sha256", "0" * 64)

    for result in malformed_results:
        decision = await FinsSourceConnector(_Gateway(result)).sync(_request(), _Cancellation())
        assert decision.action is SourceConnectorSyncAction.COMPLETED
        assert decision.candidate is not None
        assert decision.candidate.proposed_outcome is SourceSyncOutcome.FAILED
        assert decision.candidate.proposed_safe_error_code is SourceSyncErrorCode.FINS_INVARIANT


def test_source_connector_registry_is_defensive_unique_and_read_only() -> None:
    connector = FinsSourceConnector(_Gateway(_result()))
    mutable = [connector]
    registry = SourceConnectorRegistry(tuple(mutable))
    mutable.clear()
    assert registry.get(SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1) is connector
    assert registry.get(SourceConnectorKey.RSS_V1) is None
    with pytest.raises(ValueError, match="duplicate"):
        SourceConnectorRegistry((connector, connector))
    assert not hasattr(registry, "register")
