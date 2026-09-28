"""纯 intake 请求、指纹/观察排除与历史结果闭合测试。"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

import pytest

from dayu.investment.domain.candidate_intake import (
    CandidateFinsValidationWitness,
    CandidateIntakeContext,
    CandidateIntakeReceipt,
    CandidateIntakeRecordRequest,
    CandidateIntakeRejectionCode,
    intake_request_fingerprint,
)
from dayu.investment.domain.candidate_parsing import parse_fact_candidate
from dayu.investment.domain.evidence import CandidateOrigin, CandidateStatus, canonical_json_bytes
from dayu.investment.domain.identifiers import Principal, TenantId
from tests.investment.test_candidate_parsing import proposal

_NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)


def test_rejected_envelope_fingerprint_and_historical_version_are_closed() -> None:
    """请求与结果digest分离，rejected不保存原内容。

    Args:
        无。
    Returns:
        无。
    Raises:
        无。
    """
    scope = Principal(TenantId(str(uuid4())), "test").to_scope()
    context = CandidateIntakeContext(uuid4(), uuid4(), uuid4(), uuid4(), CandidateOrigin.AGENT, "extractor.v1")
    raw = b"secret malformed output"
    request = CandidateIntakeRecordRequest(
        context,
        "AAPL",
        hashlib.sha256(raw).hexdigest(),
        len(raw),
        None,
        None,
        CandidateIntakeRejectionCode.JSON_INVALID,
    )
    frame = request.payload_bytes()
    assert b"secret" not in frame
    assert frame == canonical_json_bytes(
        {
            "schema_version": "rejected_intake.v1",
            "raw_sha256": request.raw_sha256,
            "raw_bytes": len(raw),
            "rejection_code": "candidate_json_invalid",
        }
    )
    fp = intake_request_fingerprint(scope, context, "AAPL", request.raw_sha256, len(raw))
    receipt = CandidateIntakeReceipt(
        UUID(scope.tenant_id.value),
        context,
        "AAPL",
        request.raw_sha256,
        len(raw),
        fp,
        hashlib.sha256(frame).hexdigest(),
        CandidateStatus.REJECTED,
        request.rejection_code,
        None,
        _NOW,
    )
    assert receipt.candidate_version == 1
    for changed in (
        replace(context, candidate_id=uuid4()),
        replace(context, operation_id=uuid4()),
        replace(context, company_id=uuid4()),
        replace(context, security_id=uuid4()),
        replace(context, origin=CandidateOrigin.HUMAN),
        replace(context, extractor_version="v2"),
    ):
        assert intake_request_fingerprint(scope, changed, "AAPL", request.raw_sha256, len(raw)) != fp
    assert intake_request_fingerprint(scope, context, "aapl", request.raw_sha256, len(raw)) != fp
    assert intake_request_fingerprint(scope, context, "AAPL", "f" * 64, len(raw)) != fp
    assert intake_request_fingerprint(scope, context, "AAPL", request.raw_sha256, len(raw) + 1) != fp
    for change in (
        {"request_fingerprint": "f" * 64},
        {"candidate_version": 2},
        {"candidate_version": True},
        {"outcome": CandidateStatus.VALIDATED},
        {"rejection_code": None},
        {"payload_sha256": "bad"},
        {"created_at": _NOW.replace(tzinfo=None)},
    ):
        with pytest.raises(ValueError):
            replace(receipt, **change)


def test_proposed_witness_and_outcome_cannot_be_forged_as_rejected() -> None:
    """成功hash与locator绑定，动态观察时刻不进入请求指纹。

    Args:
        无。
    Returns:
        无。
    Raises:
        无。
    """
    scope = Principal(TenantId(str(uuid4())), "test").to_scope()
    context = CandidateIntakeContext(uuid4(), uuid4(), uuid4(), uuid4(), CandidateOrigin.HUMAN, "v1")
    payload = parse_fact_candidate(canonical_json_bytes(proposal()))
    witness = CandidateFinsValidationWitness(
        hashlib.sha256(payload.locator.canonical_bytes()).hexdigest(), payload.locator.locator_content_sha256, _NOW
    )
    request = CandidateIntakeRecordRequest(context, "AAPL", "a" * 64, 100, payload, witness, None)
    assert request.payload_bytes() == payload.canonical_bytes()
    fp = intake_request_fingerprint(scope, context, "AAPL", "a" * 64, 100)
    later = replace(request, witness=replace(witness, checked_at=_NOW.replace(year=2027)))
    assert (
        intake_request_fingerprint(scope, later.context, later.security_ticker, later.raw_sha256, later.raw_bytes) == fp
    )
    receipt = CandidateIntakeReceipt(
        UUID(scope.tenant_id.value),
        context,
        "AAPL",
        "a" * 64,
        100,
        fp,
        hashlib.sha256(request.payload_bytes()).hexdigest(),
        CandidateStatus.PROPOSED,
        None,
        witness,
        _NOW,
    )
    for change in ({"witness": None}, {"rejection_code": CandidateIntakeRejectionCode.STALE}):
        with pytest.raises(ValueError):
            replace(receipt, **change)
    for change in (
        {"payload": None},
        {"witness": None},
        {"security_ticker": "MSFT"},
        {"raw_bytes": -1},
        {"raw_sha256": "bad"},
        {"witness": replace(witness, citation_sha256="f" * 64)},
        {"witness": replace(witness, locator_sha256="f" * 64)},
        {"rejection_code": CandidateIntakeRejectionCode.STALE},
    ):
        with pytest.raises(ValueError):
            replace(request, **change)
    with pytest.raises(ValueError):
        CandidateIntakeRecordRequest(
            context, "AAPL", "a" * 64, 1, None, None, cast(CandidateIntakeRejectionCode, "evidence_stale")
        )


@pytest.mark.parametrize("field", ["candidate_id", "operation_id", "company_id", "security_id"])
def test_context_rejects_nil_uuid(field: str) -> None:
    """所有caller UUID必须非nil。

    Args:
        field: 上下文字段。
    Returns:
        无。
    Raises:
        无。
    """
    context = CandidateIntakeContext(uuid4(), uuid4(), uuid4(), uuid4(), CandidateOrigin.AGENT, "v1")
    with pytest.raises(ValueError):
        replace(context, **{field: UUID(int=0)})


@pytest.mark.parametrize("version", ["", " v1", "v1 ", "v\x00", "\ud800"])
def test_context_text_cannot_produce_jsonb_infrastructure_failure(version: str) -> None:
    """可信元数据仍不能包含NUL/surrogate/空白。

    Args:
        version: 错误文本。
    Returns:
        无。
    Raises:
        无。
    """
    with pytest.raises(ValueError):
        CandidateIntakeContext(uuid4(), uuid4(), uuid4(), uuid4(), CandidateOrigin.AGENT, version)
