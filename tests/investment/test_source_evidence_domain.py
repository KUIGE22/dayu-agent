"""Source Sync evidence、candidate、receipt/result owner 的直接测试。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

import dayu.investment.domain.source_evidence as source_evidence_module
from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantId
from dayu.investment.domain.jobs import CanonicalJobDocument, JsonValue, build_canonical_document
from dayu.investment.domain.source import (
    SourceDefinitionId,
    SourceKind,
    SourceSubscriptionId,
    SubscriptionStatus,
)
from dayu.investment.domain.source_evidence import (
    SourceConnectorSyncAction,
    SourceConnectorSyncDecision,
    SourceConnectorSyncRequest,
    SourceDocumentEvidence,
    SourceEvidenceLocatorDocument,
    SourceFinsTerminalCandidate,
    SourceNoProviderReason,
    SourceNoProviderTerminalCandidate,
    SourceSyncAttemptReceipt,
    _evidence_value,
    _source_sync_attempt_receipt_value,
    _source_sync_result_value,
    build_source_evidence_locator_document,
    build_source_sync_attempt_receipt,
    build_source_sync_result,
    parse_source_sync_attempt_receipt,
    parse_source_sync_result,
    validate_evidence_against_snapshot,
)
from dayu.investment.domain.source_payload import (
    SourceExecutionBinding,
    SourceExecutionSnapshot,
    build_source_execution_snapshot_document,
)
from dayu.investment.domain.source_sync import (
    FINS_SOURCE_DEFINITION_KEY,
    MAX_SOURCE_DOCUMENT_BYTES,
    SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME,
    SOURCE_SYNC_RECEIPT_SCHEMA_NAME,
    SOURCE_SYNC_RESULT_SCHEMA_NAME,
    FinsDisclosureSubscriptionConfig,
    SourceConnectorKey,
    SourceSyncErrorCode,
    SourceSyncOutcome,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_NOW = datetime(2026, 8, 12, 9, 30, tzinfo=_UTC)
_TENANT_ID = TenantId("tenant-source-evidence")
_SUBSCRIPTION_ID = SourceSubscriptionId("00000000-0000-4000-8000-000000000021")
_RUN_ID = UUID("00000000-0000-4000-8000-000000000022")
_JOB_ID = UUID("00000000-0000-4000-8000-000000000023")
_ATTEMPT_ID = UUID("00000000-0000-4000-8000-000000000024")
_PAYLOAD_SHA = "a" * 64
_SNAPSHOT_SHA = "b" * 64


def _binding() -> SourceExecutionBinding:
    """返回 evidence identity 验证使用的 binding。"""

    return SourceExecutionBinding(
        tenant_id=_TENANT_ID,
        source_definition_id=SourceDefinitionId("00000000-0000-4000-8000-000000000025"),
        source_definition_version=1,
        source_key=FINS_SOURCE_DEFINITION_KEY,
        source_kind=SourceKind.FILING,
        subscription_id=_SUBSCRIPTION_ID,
        subscription_version=1,
        subscription_status=SubscriptionStatus.ENABLED,
        security_company_id=CompanyId("company-source-evidence"),
        security_id=SecurityId("security-source-evidence"),
        security_version=1,
        security_ticker="AAPL",
        exchange_mic="XNAS",
        security_is_active=True,
        connector_key=SourceConnectorKey.FINS_MARKET_DISCLOSURE_V1,
        config=FinsDisclosureSubscriptionConfig(
            forms=("10-K", "10-Q"),
            lookback_days=3,
            freshness_max_age_days=7,
            failing_after=2,
            disable_after=4,
        ),
    )


def _snapshot() -> SourceExecutionSnapshot:
    """返回固定三日 query window。"""

    return SourceExecutionSnapshot(
        binding=_binding(),
        canonical_ticker="AAPL",
        query_start_date=date(2026, 8, 10),
        query_end_date=date(2026, 8, 12),
    )


def _locator(*, ticker: str = "AAPL", document_id: str = "doc-1") -> SourceEvidenceLocatorDocument:
    """返回 canonical pathless locator。"""

    return build_source_evidence_locator_document(
        repository_id="dayu.fins.public.v1",
        ticker=ticker,
        document_id=document_id,
        source_kind="filing",
        artifact_kind="source",
        document_version="v1",
        source_fingerprint="c" * 64,
        primary_content_sha256="d" * 64,
        locator_kind="document",
        locator_content_sha256="e" * 64,
    )


def _evidence(
    *,
    document_id: str = "doc-1",
    ticker: str = "AAPL",
    form_type: str = "10-K",
    observed_date: date = date(2026, 8, 11),
) -> SourceDocumentEvidence:
    """返回与 snapshot 匹配的单文档 evidence。"""

    locator = _locator(ticker=ticker, document_id=document_id)
    return SourceDocumentEvidence(
        document_id=document_id,
        form_type=form_type,
        source_observed_date=observed_date,
        locator=locator,
        locator_sha256=locator.document.sha256,
    )


def _succeeded_candidate() -> SourceFinsTerminalCandidate:
    """返回单文档 succeeded terminal candidate。"""

    evidence = _evidence()
    return SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.SUCCEEDED,
        proposed_safe_error_code=None,
        documents=(evidence,),
        records_discovered=1,
        records_downloaded=1,
        records_reused=0,
        records_ignored=0,
        records_failed=0,
        latest_source_observed_date=evidence.source_observed_date,
    )


def _receipt(
    *,
    outcome: SourceSyncOutcome = SourceSyncOutcome.SUCCEEDED,
    safe_error_code: SourceSyncErrorCode | None = None,
    retry_recommended: bool = False,
    documents: tuple[SourceDocumentEvidence, ...] | None = None,
    records_discovered: int | None = None,
    records_downloaded: int | None = None,
    records_reused: int = 0,
    records_ignored: int = 0,
    records_failed: int = 0,
) -> SourceSyncAttemptReceipt:
    """按给定 outcome 构建完整 canonical receipt。"""

    selected = (_evidence(),) if documents is None else documents
    downloaded = len(selected) if records_downloaded is None else records_downloaded
    discovered = downloaded + records_reused + records_ignored + records_failed
    if records_discovered is not None:
        discovered = records_discovered
    return build_source_sync_attempt_receipt(
        tenant_id=_TENANT_ID,
        source_sync_run_id=_RUN_ID,
        subscription_id=_SUBSCRIPTION_ID,
        job_id=_JOB_ID,
        producer_attempt_id=_ATTEMPT_ID,
        payload_sha256=_PAYLOAD_SHA,
        execution_snapshot_sha256=_SNAPSHOT_SHA,
        outcome=outcome,
        retry_recommended=retry_recommended,
        documents=selected,
        records_discovered=discovered,
        records_ingested=downloaded + records_reused,
        records_downloaded=downloaded,
        records_reused=records_reused,
        records_ignored=records_ignored,
        records_failed=records_failed,
        latest_source_observed_date=max((item.source_observed_date for item in selected), default=None),
        safe_error_code=safe_error_code,
        started_at=_NOW,
        finished_at=_NOW + timedelta(milliseconds=125),
        latency_ms=125,
    )


def _manual_document(value: JsonValue, *, schema_name: str) -> CanonicalJobDocument:
    """把 closed JSON 值编码为指定 schema 的 canonical document。"""

    return build_canonical_document(value, schema_name=schema_name, schema_version=1)


def test_locator_wrapper_has_exact_field_and_canonical_pathless_body() -> None:
    """Locator wrapper 只持有 canonical document，body 固定为 pathless schema。"""

    locator = _locator()
    assert tuple(field.name for field in fields(locator)) == ("document",)
    assert locator.document.schema_name == SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME
    raw = json.loads(locator.document.canonical_bytes)
    assert set(raw) == {
        "artifact_kind",
        "document_id",
        "document_version",
        "locator_content_sha256",
        "locator_kind",
        "locator_payload",
        "primary_content_sha256",
        "repository_id",
        "schema_version",
        "source_fingerprint",
        "source_kind",
        "ticker",
    }
    assert raw["locator_payload"] == {}
    assert not {"path", "url", "bucket", "key"}.intersection(raw)
    with pytest.raises(FrozenInstanceError):
        setattr(locator, "document", locator.document)


def test_locator_receipt_and_result_builders_enforce_exact_and_one_over_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence family 的三个 durable builder 必须在返回前闭合 size cap。"""

    locator = _locator()
    monkeypatch.setattr(
        source_evidence_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(locator.document.canonical_bytes),
    )
    assert _locator() == locator
    monkeypatch.setattr(
        source_evidence_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(locator.document.canonical_bytes) - 1,
    )
    with pytest.raises(ValueError):
        _locator()

    monkeypatch.setattr(source_evidence_module, "MAX_SOURCE_DOCUMENT_BYTES", MAX_SOURCE_DOCUMENT_BYTES)
    receipt = _receipt()
    monkeypatch.setattr(
        source_evidence_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(receipt.receipt.canonical_bytes),
    )
    exact_receipt = _receipt()
    assert parse_source_sync_attempt_receipt(tenant_id=_TENANT_ID, receipt=exact_receipt.receipt) == exact_receipt
    monkeypatch.setattr(
        source_evidence_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(receipt.receipt.canonical_bytes) - 1,
    )
    with pytest.raises(ValueError):
        _receipt()

    monkeypatch.setattr(source_evidence_module, "MAX_SOURCE_DOCUMENT_BYTES", MAX_SOURCE_DOCUMENT_BYTES)
    result = build_source_sync_result(receipt)
    monkeypatch.setattr(
        source_evidence_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(result.result.canonical_bytes),
    )
    exact_result = build_source_sync_result(receipt)
    assert parse_source_sync_result(exact_result.result) == exact_result
    monkeypatch.setattr(
        source_evidence_module,
        "MAX_SOURCE_DOCUMENT_BYTES",
        len(result.result.canonical_bytes) - 1,
    )
    with pytest.raises(ValueError):
        build_source_sync_result(receipt)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository_id", "other.repository"),
        ("ticker", "aapl"),
        ("ticker", " AAPL"),
        ("document_id", ""),
        ("source_kind", "announcement"),
        ("artifact_kind", "processed"),
        ("document_version", " version"),
        ("source_fingerprint", "C" * 64),
        ("primary_content_sha256", "bad"),
        ("locator_kind", "file"),
        ("locator_content_sha256", "E" * 64),
    ],
)
def test_locator_builder_rejects_fixed_identity_text_and_hash_drift(field: str, value: str) -> None:
    """Locator 构造期必须逐字段验证 fixed identity、文本与 hash。"""

    values = {
        "repository_id": "dayu.fins.public.v1",
        "ticker": "AAPL",
        "document_id": "doc-1",
        "source_kind": "filing",
        "artifact_kind": "source",
        "document_version": "v1",
        "source_fingerprint": "c" * 64,
        "primary_content_sha256": "d" * 64,
        "locator_kind": "document",
        "locator_content_sha256": "e" * 64,
    }
    values[field] = value
    with pytest.raises(ValueError):
        build_source_evidence_locator_document(**values)


def test_locator_rejects_unknown_nonempty_payload_sensitive_and_hash_drift() -> None:
    """Locator parser 拒绝 unknown key、非空 payload、敏感 key 与 wrapper hash 漂移。"""

    valid_value = json.loads(_locator().document.canonical_bytes)
    unknown = dict(valid_value)
    unknown["unknown"] = True
    nonempty = dict(valid_value)
    nonempty["locator_payload"] = {"opaque": "value"}
    bool_version = dict(valid_value)
    bool_version["schema_version"] = True
    for invalid in (unknown, nonempty, bool_version):
        with pytest.raises(ValueError):
            SourceEvidenceLocatorDocument(
                document=_manual_document(invalid, schema_name=SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME)
            )

    sensitive = dict(valid_value)
    sensitive["locator_payload"] = {"URI": "storage://private"}
    sensitive_bytes = json.dumps(sensitive, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    sensitive_document = CanonicalJobDocument(
        schema_name=SOURCE_EVIDENCE_LOCATOR_SCHEMA_NAME,
        schema_version=1,
        canonical_bytes=sensitive_bytes,
        sha256=hashlib.sha256(sensitive_bytes).hexdigest(),
    )
    with pytest.raises(ValueError):
        SourceEvidenceLocatorDocument(document=sensitive_document)
    with pytest.raises(ValueError):
        SourceEvidenceLocatorDocument(document=replace(_locator().document, sha256="a" * 64))


def test_evidence_closes_locator_identity_hash_form_date_and_snapshot_identity() -> None:
    """Evidence 必须闭合 locator hash/identity，并逐值对照 snapshot ticker/form/date。"""

    evidence = _evidence()
    validate_evidence_against_snapshot(evidence, _snapshot())
    assert tuple(field.name for field in fields(evidence)) == (
        "document_id",
        "form_type",
        "source_observed_date",
        "locator",
        "locator_sha256",
    )
    for invalid in (
        {"document_id": "other"},
        {"form_type": "10-k"},
        {"source_observed_date": _NOW},
        {"locator_sha256": "a" * 64},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(evidence, **invalid)
    for mismatch in (
        _evidence(ticker="MSFT"),
        _evidence(form_type="8-K"),
        _evidence(observed_date=date(2026, 8, 9)),
        _evidence(observed_date=date(2026, 8, 13)),
    ):
        with pytest.raises(ValueError):
            validate_evidence_against_snapshot(mismatch, _snapshot())


def test_fins_candidate_accepts_every_closed_outcome_matrix() -> None:
    """Fins candidate 接受 succeeded/no-change/partial/failed 的全部合法矩阵。"""

    evidence = _evidence()
    succeeded = _succeeded_candidate()
    no_change = SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.NO_CHANGE,
        proposed_safe_error_code=None,
        documents=(),
        records_discovered=2,
        records_downloaded=0,
        records_reused=0,
        records_ignored=2,
        records_failed=0,
        latest_source_observed_date=None,
    )
    partial = SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.PARTIAL,
        proposed_safe_error_code=SourceSyncErrorCode.PARTIAL_BATCH,
        documents=(evidence,),
        records_discovered=2,
        records_downloaded=1,
        records_reused=0,
        records_ignored=0,
        records_failed=1,
        latest_source_observed_date=evidence.source_observed_date,
    )
    unsupported = SourceFinsTerminalCandidate(
        proposed_outcome=SourceSyncOutcome.FAILED,
        proposed_safe_error_code=SourceSyncErrorCode.UNSUPPORTED_MARKET,
        documents=(),
        records_discovered=0,
        records_downloaded=0,
        records_reused=0,
        records_ignored=0,
        records_failed=0,
        latest_source_observed_date=None,
    )
    unavailable = replace(
        unsupported,
        proposed_safe_error_code=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        records_discovered=2,
        records_ignored=1,
        records_failed=1,
    )
    assert succeeded.documents == (evidence,)
    assert no_change.records_ignored == 2
    assert partial.records_failed == 1
    assert unsupported.records_discovered == 0
    assert unavailable.records_discovered == 2


@pytest.mark.parametrize(
    "invalid",
    [
        {"documents": (), "records_discovered": 0, "records_downloaded": 0, "latest_source_observed_date": None},
        {"proposed_safe_error_code": SourceSyncErrorCode.PARTIAL_BATCH},
        {"records_failed": 1, "records_discovered": 2},
        {"records_discovered": 2},
        {"records_reused": 1},
        {"latest_source_observed_date": date(2026, 8, 10)},
        {"proposed_outcome": SourceSyncOutcome.STALE_SUBSCRIPTION},
        {"proposed_outcome": SourceSyncOutcome.SKIPPED_DISABLED},
        {"proposed_outcome": SourceSyncOutcome.FAILED},
    ],
)
def test_fins_candidate_rejects_count_document_latest_and_outcome_drift(invalid: dict[str, JsonValue]) -> None:
    """Candidate 不得修补 count/docs/latest 或 caller-proposed stale/disabled。"""

    with pytest.raises((TypeError, ValueError)):
        replace(_succeeded_candidate(), **invalid)


def test_candidate_document_tuple_must_be_sorted_unique_and_capped() -> None:
    """Candidate documents 必须严格排序、document_id 唯一且不超过 cap。"""

    first = _evidence(document_id="doc-1")
    second = _evidence(document_id="doc-2", observed_date=date(2026, 8, 12))
    valid = replace(
        _succeeded_candidate(),
        documents=(first, second),
        records_discovered=2,
        records_downloaded=2,
        latest_source_observed_date=date(2026, 8, 12),
    )
    assert valid.documents == (first, second)
    with pytest.raises(ValueError):
        replace(valid, documents=(second, first))
    duplicate_id = _evidence(document_id="doc-1", observed_date=date(2026, 8, 12))
    with pytest.raises(ValueError):
        replace(valid, documents=(first, duplicate_id))
    with pytest.raises(ValueError):
        replace(
            valid,
            documents=tuple(first for _ in range(501)),
            records_discovered=501,
            records_downloaded=501,
        )


def test_no_provider_and_connector_decision_presence_matrices_are_exact() -> None:
    """No-provider reason 与 connector completed/cancelled presence 矩阵必须闭合。"""

    assert SourceNoProviderTerminalCandidate(SourceNoProviderReason.DISABLED).reason is SourceNoProviderReason.DISABLED
    assert (
        SourceNoProviderTerminalCandidate(SourceNoProviderReason.BINDING_DRIFT).reason
        is SourceNoProviderReason.BINDING_DRIFT
    )
    completed = SourceConnectorSyncDecision(SourceConnectorSyncAction.COMPLETED, _succeeded_candidate())
    cancelled = SourceConnectorSyncDecision(SourceConnectorSyncAction.CANCELLED, None)
    assert completed.candidate is not None
    assert cancelled.candidate is None
    with pytest.raises(ValueError):
        SourceConnectorSyncDecision(SourceConnectorSyncAction.COMPLETED, None)
    with pytest.raises(ValueError):
        SourceConnectorSyncDecision(SourceConnectorSyncAction.CANCELLED, _succeeded_candidate())


def test_connector_request_recomputes_snapshot_hash() -> None:
    """Connector request 必须重算 frozen snapshot canonical SHA。"""

    snapshot = _snapshot()
    snapshot_sha = build_source_execution_snapshot_document(snapshot).sha256
    request = SourceConnectorSyncRequest(
        operation_id=UUID("00000000-0000-4000-8000-000000000026"),
        execution_snapshot=snapshot,
        execution_snapshot_sha256=snapshot_sha,
    )
    assert request.execution_snapshot_sha256 == snapshot_sha
    with pytest.raises(ValueError):
        replace(request, execution_snapshot_sha256="f" * 64)


def test_receipt_and_result_builders_round_trip_without_replay_marker() -> None:
    """Receipt/result canonical builder/parser 必须完整 round-trip 且无 replay 字段。"""

    receipt = _receipt()
    assert tuple(field.name for field in fields(receipt))[-1] == "receipt"
    assert receipt.receipt.schema_name == SOURCE_SYNC_RECEIPT_SCHEMA_NAME
    assert parse_source_sync_attempt_receipt(tenant_id=_TENANT_ID, receipt=receipt.receipt) == receipt
    raw_receipt = json.loads(receipt.receipt.canonical_bytes)
    assert "tenant_id" not in raw_receipt
    assert "replay" not in raw_receipt
    assert raw_receipt["documents"] == [_evidence_value(_evidence())]

    result = build_source_sync_result(receipt)
    assert result.result.schema_name == SOURCE_SYNC_RESULT_SCHEMA_NAME
    assert parse_source_sync_result(result.result) == result
    raw_result = json.loads(result.result.canonical_bytes)
    assert set(raw_result) == {
        "outcome",
        "producer_attempt_id",
        "retry_recommended",
        "schema_version",
        "source_receipt_sha256",
        "source_sync_run_id",
    }
    assert "replay" not in raw_result


def test_receipt_accepts_all_closed_terminal_outcome_shapes() -> None:
    """Receipt 接受 success/no-change/partial/disabled/stale/failed 的 exact 矩阵。"""

    empty: tuple[SourceDocumentEvidence, ...] = ()
    no_change = _receipt(
        outcome=SourceSyncOutcome.NO_CHANGE,
        documents=empty,
        records_downloaded=0,
        records_ignored=2,
    )
    partial = _receipt(
        outcome=SourceSyncOutcome.PARTIAL,
        safe_error_code=SourceSyncErrorCode.PARTIAL_BATCH,
        retry_recommended=True,
        records_failed=1,
    )
    skipped = _receipt(
        outcome=SourceSyncOutcome.SKIPPED_DISABLED,
        documents=empty,
        records_downloaded=0,
    )
    stale = _receipt(
        outcome=SourceSyncOutcome.STALE_SUBSCRIPTION,
        safe_error_code=SourceSyncErrorCode.STALE_SUBSCRIPTION,
        documents=empty,
        records_downloaded=0,
    )
    unavailable = _receipt(
        outcome=SourceSyncOutcome.FAILED,
        safe_error_code=SourceSyncErrorCode.PROVIDER_UNAVAILABLE,
        retry_recommended=True,
        documents=empty,
        records_downloaded=0,
        records_failed=1,
    )
    stale_data = _receipt(
        outcome=SourceSyncOutcome.FAILED,
        safe_error_code=SourceSyncErrorCode.STALE_DATA,
    )
    assert no_change.records_ingested == 0
    assert partial.retry_recommended
    assert skipped.safe_error_code is None
    assert stale.safe_error_code is SourceSyncErrorCode.STALE_SUBSCRIPTION
    assert unavailable.records_failed == 1
    assert stale_data.records_ingested == 1


def test_receipt_rejects_count_time_latest_and_outcome_matrix_drift() -> None:
    """Receipt builder 对 count/time/latest 与 outcome/error/retry 漂移 fail closed。"""

    evidence = _evidence()
    invalid_arguments = (
        {"records_discovered": 2},
        {"records_ingested": 0},
        {"records_downloaded": 0},
        {"latest_source_observed_date": None},
        {"retry_recommended": True},
        {"safe_error_code": SourceSyncErrorCode.PARTIAL_BATCH},
        {"finished_at": _NOW - timedelta(seconds=1), "latency_ms": 0},
        {"finished_at": _NOW + timedelta(milliseconds=125), "latency_ms": 124},
    )
    base = {
        "tenant_id": _TENANT_ID,
        "source_sync_run_id": _RUN_ID,
        "subscription_id": _SUBSCRIPTION_ID,
        "job_id": _JOB_ID,
        "producer_attempt_id": _ATTEMPT_ID,
        "payload_sha256": _PAYLOAD_SHA,
        "execution_snapshot_sha256": _SNAPSHOT_SHA,
        "outcome": SourceSyncOutcome.SUCCEEDED,
        "retry_recommended": False,
        "documents": (evidence,),
        "records_discovered": 1,
        "records_ingested": 1,
        "records_downloaded": 1,
        "records_reused": 0,
        "records_ignored": 0,
        "records_failed": 0,
        "latest_source_observed_date": evidence.source_observed_date,
        "safe_error_code": None,
        "started_at": _NOW,
        "finished_at": _NOW + timedelta(milliseconds=125),
        "latency_ms": 125,
    }
    for drift in invalid_arguments:
        arguments = dict(base)
        arguments.update(drift)
        with pytest.raises((TypeError, ValueError)):
            build_source_sync_attempt_receipt(**arguments)


def test_receipt_and_result_dtos_reject_outer_canonical_and_parser_drift() -> None:
    """Outer fields、canonical body、exact keys 与 parser enum/bool 全部必须一致。"""

    receipt = _receipt()
    with pytest.raises(ValueError):
        replace(receipt, payload_sha256="f" * 64)
    with pytest.raises(ValueError):
        parse_source_sync_attempt_receipt(
            tenant_id=_TENANT_ID,
            receipt=replace(receipt.receipt, sha256="f" * 64),
        )
    receipt_value = _source_sync_attempt_receipt_value(receipt)
    receipt_value["unknown"] = True
    with pytest.raises(ValueError):
        parse_source_sync_attempt_receipt(
            tenant_id=_TENANT_ID,
            receipt=_manual_document(receipt_value, schema_name=SOURCE_SYNC_RECEIPT_SCHEMA_NAME),
        )
    receipt_value = _source_sync_attempt_receipt_value(receipt)
    receipt_value["retry_recommended"] = 1
    with pytest.raises(ValueError):
        parse_source_sync_attempt_receipt(
            tenant_id=_TENANT_ID,
            receipt=_manual_document(receipt_value, schema_name=SOURCE_SYNC_RECEIPT_SCHEMA_NAME),
        )
    receipt_value = _source_sync_attempt_receipt_value(receipt)
    receipt_value["schema_version"] = True
    with pytest.raises(ValueError):
        parse_source_sync_attempt_receipt(
            tenant_id=_TENANT_ID,
            receipt=_manual_document(receipt_value, schema_name=SOURCE_SYNC_RECEIPT_SCHEMA_NAME),
        )

    result = build_source_sync_result(receipt)
    with pytest.raises(ValueError):
        replace(result, source_receipt_sha256="f" * 64)
    result_value = _source_sync_result_value(result)
    result_value["outcome"] = "unknown"
    with pytest.raises(ValueError):
        parse_source_sync_result(_manual_document(result_value, schema_name=SOURCE_SYNC_RESULT_SCHEMA_NAME))
    result_value = _source_sync_result_value(result)
    result_value["retry_recommended"] = 1
    with pytest.raises(ValueError):
        parse_source_sync_result(_manual_document(result_value, schema_name=SOURCE_SYNC_RESULT_SCHEMA_NAME))
    result_value = _source_sync_result_value(result)
    result_value["schema_version"] = True
    with pytest.raises(ValueError):
        parse_source_sync_result(_manual_document(result_value, schema_name=SOURCE_SYNC_RESULT_SCHEMA_NAME))


def test_result_builder_rejects_non_receipt_and_result_has_exact_fields() -> None:
    """Result builder 只接完整 receipt，DTO 字段必须精确六项。"""

    result = build_source_sync_result(_receipt())
    assert tuple(field.name for field in fields(result)) == (
        "outcome",
        "source_sync_run_id",
        "producer_attempt_id",
        "source_receipt_sha256",
        "retry_recommended",
        "result",
    )
