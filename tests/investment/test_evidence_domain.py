"""S31-A 投资证据纯领域结构、PIT 与状态边单元测试。"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest

from dayu.fins.domain.evidence_locator import parse_evidence_locator_projection
from dayu.investment.domain.evidence import (
    CandidateOrigin,
    CandidateStatus,
    ClaimConflict,
    ClaimConflictOpenRequest,
    ClaimConflictResolveRequest,
    ClaimContent,
    ClaimCreateRequest,
    ClaimReviewRequest,
    ClaimRevisionBeginRequest,
    ClaimSnapshot,
    ClaimStatus,
    ClaimTransitionKind,
    ClaimVersion,
    ClaimVersionAppendRequest,
    ConfidenceBand,
    ConflictStatus,
    EvidenceLink,
    EvidenceLinkRequest,
    EvidenceLocatorSnapshot,
    EvidenceMode,
    EvidenceRelation,
    EvidenceSelection,
    Fact,
    FactCreateRequest,
    FactPitTimes,
    FactValue,
    FactValueKind,
    ImpactHorizon,
    JsonValue,
    LocalEligibilityReason,
    ResearchCandidate,
    ResearchCandidateCreateRequest,
    ReviewWitness,
    VerificationStatus,
    canonical_json_document,
    canonical_sha256,
    copied_link_id,
    evidence_fingerprint_frame,
    local_eligibility_reason,
    ordered_link_identities,
    validate_append_transition,
    validate_begin_transition,
    validate_conflict_resolution_transition,
    validate_review_transition,
)

_NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
_HASH = "a" * 64


def _locator_dict(kind: str = "document", payload: dict[str, JsonValue] | None = None) -> dict[str, JsonValue]:
    """生成与 Fins v1 projection 同形的合法十一键对象。

    Args:
        kind: locator kind。
        payload: 该 kind 的 exact payload。

    Returns:
        投资域输入字典。

    Raises:
        无。
    """

    return {
        "repository_id": "dayu.fins.public.v1",
        "ticker": "AAPL",
        "document_id": "fil_0001",
        "source_kind": "filing",
        "artifact_kind": "processed",
        "document_version": "v1",
        "source_fingerprint": _HASH,
        "primary_content_sha256": "b" * 64,
        "locator_kind": kind,
        "locator_payload": {} if payload is None else payload,
        "locator_content_sha256": "c" * 64,
    }


def _locator() -> EvidenceLocatorSnapshot:
    """生成已验证的 document locator。

    Args:
        无。

    Returns:
        不可变 locator。

    Raises:
        无。
    """

    return EvidenceLocatorSnapshot.from_dict(_locator_dict())


def _content(status: ClaimStatus = ClaimStatus.DRAFT) -> ClaimContent:
    """生成合法 Claim 内容。

    Args:
        status: 版本状态。

    Returns:
        不可变内容。

    Raises:
        无。
    """

    return ClaimContent(
        statement="Revenue grew", confidence_band=ConfidenceBand.HIGH,
        probability=Decimal("0.8"), impact_horizon=ImpactHorizon.SHORT,
        valid_until=_NOW + timedelta(days=30), status=status,
        invalidation_rule="Revenue falls below prior year",
    )


def _replace_links() -> EvidenceSelection:
    """构造一个 supports Fact link 的完整替换选择。

    Args:
        无。

    Returns:
        replace_all 选择。

    Raises:
        无。
    """

    return EvidenceSelection(
        links=(EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS, fact_id=uuid4()),),
        copy_previous_links=False,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("document", {}),
        ("page", {"page_no": 1}),
        ("section", {"section_ref": "s_001"}),
        ("table_cell", {"table_ref": "t_001", "row_index": 0, "column": "Revenue"}),
        ("xbrl_fact", {"concept": "us-gaap:Revenues", "fact_sha256": _HASH}),
    ],
)
def test_five_locator_payload_shapes_roundtrip(kind: str, payload: dict[str, JsonValue]) -> None:
    """五种 Fins v1 结构镜像均按 canonical bytes 往返。

    Args:
        kind: 预期 kind。
        payload: 该 kind 的 payload。

    Returns:
        无。

    Raises:
        AssertionError: 结构或序列化错误。
    """

    locator = EvidenceLocatorSnapshot.from_dict(_locator_dict(kind, payload))
    assert locator.to_dict()["locator_payload"] == payload
    assert parse_evidence_locator_projection(locator.to_dict()).to_dict() == locator.to_dict()
    assert EvidenceLocatorSnapshot.from_json_bytes(locator.canonical_bytes()) == locator
    assert locator.canonical_bytes() == json.dumps(
        _locator_dict(kind, payload), ensure_ascii=True, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation",
    [
        {"repository_id": "unknown"},
        {"ticker": " AAPL"},
        {"document_id": "bad/path"},
        {"source_fingerprint": "A" * 64},
        {"source_kind": "other"},
        {"locator_kind": "unknown"},
        {"schema_version": "fins-evidence-locator-v2"},
    ],
)
def test_locator_rejects_unknown_or_noncanonical_fields(mutation: dict[str, str]) -> None:
    """拒绝未知 schema、namespace、枚举和路径形态。

    Args:
        mutation: 对合法输入的修改。

    Returns:
        无。

    Raises:
        AssertionError: 非法输入被接受。
    """

    raw = _locator_dict()
    raw.update(mutation)
    with pytest.raises((ValueError, TypeError)):
        EvidenceLocatorSnapshot.from_dict(raw)


@pytest.mark.unit
def test_locator_rejects_source_nondocument_and_payload_ambiguity() -> None:
    """source 只能 document，payload 必须与 kind 精确配对。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非法组合被接受。
    """

    source_page = _locator_dict("page", {"page_no": 2})
    source_page["artifact_kind"] = "source"
    with pytest.raises(ValueError):
        EvidenceLocatorSnapshot.from_dict(source_page)
    with pytest.raises(ValueError):
        EvidenceLocatorSnapshot.from_dict(_locator_dict("page", {"page_no": 2, "uri": "x"}))
    with pytest.raises(TypeError):
        EvidenceLocatorSnapshot.from_dict(_locator_dict("page", {"page_no": True}))


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        b"\xef\xbb\xbf{}",
        b'{"ticker":"A","ticker":"B"}',
        b"{} {}",
        b'{"x":NaN}',
    ],
)
def test_locator_json_ingress_rejects_bom_duplicate_trailing_and_nonfinite(raw: bytes) -> None:
    """在 JSONB 归一化前拒绝原始 bytes 的歧义。

    Args:
        raw: 非法 JSON bytes。

    Returns:
        无。

    Raises:
        AssertionError: 非法输入被接受。
    """

    with pytest.raises(ValueError):
        EvidenceLocatorSnapshot.from_json_bytes(raw)


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    [Decimal("1.0000000000001"), Decimal("9" * 39), Decimal("NaN"),
     Decimal("Infinity"), Decimal("-Infinity"), 1.2, True],
)
def test_decimal_rejects_precision_nonfinite_and_float(value: Decimal | float | bool) -> None:
    """数值按原值拒绝越界且不允许 float/bool。

    Args:
        value: 非法值。

    Returns:
        无。

    Raises:
        AssertionError: 非法值被接受。
    """

    with pytest.raises((TypeError, ValueError)):
        FactValue(FactValueKind.DECIMAL, value_decimal=cast(Decimal, value), unit_code="shares")


@pytest.mark.unit
def test_decimal_accepts_38_12_without_rounding_and_currency_closure() -> None:
    """边界合法数值原样保存，单位与货币严格配对。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 原值发生舍入或非法单位被接受。
    """

    boundary = Decimal("9" * 26 + "." + "9" * 12)
    result = FactValue(FactValueKind.DECIMAL, value_decimal=boundary, unit_code="currency", currency="USD")
    assert result.value_decimal == boundary
    assert isinstance(result.value_decimal, Decimal)
    assert result.value_decimal.as_tuple() == boundary.as_tuple()
    assert FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("0E+10"), unit_code="shares")
    with pytest.raises(ValueError):
        FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("1"), unit_code="currency")
    with pytest.raises(ValueError):
        FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("1"), unit_code="shares", currency="USD")
    with pytest.raises(ValueError):
        FactValue(FactValueKind.TEXT, value_text="value", unit_code="shares")
    with pytest.raises(TypeError):
        FactValue(FactValueKind.BOOLEAN, value_boolean=cast(bool, 1))


@pytest.mark.unit
def test_pit_times_keep_effective_at_independent_and_reject_bad_clock() -> None:
    """forward guidance 可晚于 published；资料到达时钟仍须有序。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非 UTC 或倒置时间被接受。
    """

    pit = FactPitTimes(
        period_start=date(2026, 1, 1), period_end=date(2026, 3, 31),
        effective_at=_NOW + timedelta(days=90), published_at=_NOW,
        ingested_at=_NOW + timedelta(seconds=1), available_at=_NOW + timedelta(seconds=2),
    )
    assert pit.effective_at > pit.published_at
    assert replace(pit, period_start=None, period_end=None).period_end is None
    with pytest.raises(ValueError):
        replace(pit, available_at=_NOW)
    with pytest.raises(ValueError):
        replace(pit, period_start=date(2026, 4, 1))
    with pytest.raises(ValueError):
        replace(pit, period_start=None)
    with pytest.raises(ValueError):
        replace(pit, period_end=None)
    with pytest.raises(ValueError):
        replace(pit, published_at=datetime(2026, 9, 27, 12))


@pytest.mark.unit
def test_fact_revision_and_verifier_witness() -> None:
    """Fact revision 链与验证快照在构造时闭合。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 缺 prior 或 verifier witness 被接受。
    """

    pit = FactPitTimes(None, None, _NOW, _NOW, _NOW, _NOW)
    request = FactCreateRequest(
        id=uuid4(), company_id=uuid4(), security_id=uuid4(),
        fact_series_id=uuid4(), revision_no=1, prior_fact_id=None,
        fact_key="Revenue", metric="revenue", locator=_locator(),
        value=FactValue(FactValueKind.DATE, value_date=date(2026, 3, 31)),
        pit=pit, extractor_version="v1", verification_status=VerificationStatus.UNVERIFIED,
        verifier_user_id=None, verified_at=None, operation_id=uuid4(),
    )
    assert request.locator_ticker == "AAPL"
    with pytest.raises(ValueError):
        replace(request, revision_no=2)
    with pytest.raises(ValueError):
        replace(request, verification_status=VerificationStatus.VERIFIED)
    assert replace(request, revision_no=2, prior_fact_id=uuid4(),
                   verification_status=VerificationStatus.VERIFIED,
                   verifier_user_id=uuid4(), verified_at=_NOW)


@pytest.mark.unit
def test_evidence_selection_preserves_distinct_securities_and_copy_identity() -> None:
    """同 ticker/locator 的两只证券仍是两个 direct target。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: target 被合并或 ID 不稳定。
    """

    locator = _locator()
    a = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS, security_id=uuid4(), locator=locator)
    b = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS, security_id=uuid4(), locator=locator)
    assert a.target_identity() != b.target_identity()
    assert a.locator_ticker == b.locator_ticker == "AAPL"
    assert ordered_link_identities((a, b)) == ordered_link_identities((b, a))
    assert EvidenceSelection((a, b), False).links == (a, b)
    new_version = uuid4()
    assert copied_link_id(new_version, a.id) == copied_link_id(new_version, a.id)
    assert copied_link_id(new_version, a.id) != copied_link_id(new_version, b.id)
    with pytest.raises(ValueError):
        EvidenceSelection((a, a), False)
    with pytest.raises(ValueError):
        EvidenceSelection((a,), True)
    with pytest.raises(ValueError):
        EvidenceSelection(None, False)
    assert EvidenceSelection(None, True).links is None


@pytest.mark.unit
def test_replace_and_copy_fingerprint_frames_bind_full_source_snapshot() -> None:
    """复制指纹绑定 immutable 来源及新旧 ID，且不依赖输入顺序。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 两模式或两证券身份被合并。
    """

    locator = _locator()
    a = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                            security_id=uuid4(), locator=locator)
    b = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                            security_id=uuid4(), locator=locator)
    new_version_id, source_version_id = uuid4(), uuid4()
    replace_frame = evidence_fingerprint_frame(
        EvidenceSelection((b, a), False), new_version_id=new_version_id,
    )
    copy_frame = evidence_fingerprint_frame(
        EvidenceSelection(None, True), new_version_id=new_version_id,
        copy_source_version_id=source_version_id, copy_source_version_no=3,
        copy_source_links=(a, b),
    )
    reordered_copy = evidence_fingerprint_frame(
        EvidenceSelection(None, True), new_version_id=new_version_id,
        copy_source_version_id=source_version_id, copy_source_version_no=3,
        copy_source_links=(b, a),
    )
    assert canonical_sha256(copy_frame) == canonical_sha256(reordered_copy)
    assert canonical_sha256(copy_frame) != canonical_sha256(replace_frame)
    assert copy_frame["source_version_id"] == str(source_version_id)
    assert len(cast(list[JsonValue], copy_frame["links"])) == 2
    assert b"security_id" in json.dumps(copy_frame).encode("utf-8")
    assert b"locator" in json.dumps(copy_frame).encode("utf-8")
    with pytest.raises(ValueError):
        evidence_fingerprint_frame(EvidenceSelection(None, True), new_version_id=new_version_id)
    with pytest.raises(ValueError):
        evidence_fingerprint_frame(EvidenceSelection((a,), False), new_version_id=new_version_id,
                                   copy_source_version_id=source_version_id)


@pytest.mark.unit
def test_fact_link_carries_no_direct_identity() -> None:
    """Fact arm 不携任何 direct-only 字段。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 残余字段被接受。
    """

    fact_link = EvidenceLinkRequest(uuid4(), EvidenceRelation.CONTEXT, fact_id=uuid4())
    assert fact_link.locator_ticker is None
    assert fact_link.target_identity()[0] == "fact"
    with pytest.raises(ValueError):
        replace(fact_link, security_id=uuid4(), locator=_locator())
    with pytest.raises(ValueError):
        EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS, security_id=uuid4())


@pytest.mark.unit
def test_claim_requests_restrict_status_and_derive_actor_outside_request() -> None:
    """V1、普通 append、begin、review 有独立状态入口。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: reviewer-only 状态进入普通 append。
    """

    selection = _replace_links()
    create = ClaimCreateRequest(uuid4(), uuid4(), uuid4(), _content(), selection, None, uuid4())
    assert create.content.status is ClaimStatus.DRAFT
    with pytest.raises(ValueError):
        replace(create, evidence=EvidenceSelection(None, True))
    with pytest.raises(ValueError):
        ClaimVersionAppendRequest(uuid4(), 1, uuid4(), _content(ClaimStatus.APPROVED), selection, None, uuid4())
    begin = ClaimRevisionBeginRequest(uuid4(), 1, uuid4(), _content(), selection, "new information", uuid4())
    assert not hasattr(begin, "author_user_id")
    with pytest.raises(ValueError):
        replace(begin, content=_content(ClaimStatus.IN_REVIEW))
    review = ClaimReviewRequest(uuid4(), 1, uuid4(), _content(ClaimStatus.APPROVED), selection, "checked", uuid4())
    assert not hasattr(review, "reviewer_user_id")


@pytest.mark.unit
def test_claim_state_matrix_and_local_eligibility_order() -> None:
    """通用、审查、重开、冲突入口与局部 reason 顺序闭合。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 禁止的状态边被允许。
    """

    assert validate_append_transition(ClaimStatus.DRAFT, ClaimStatus.IN_REVIEW,
                                      materially_changed=False).value == "submit_review"
    assert validate_append_transition(ClaimStatus.IN_REVIEW, ClaimStatus.IN_REVIEW,
                                      materially_changed=True).value == "content_revision"
    with pytest.raises(ValueError):
        validate_append_transition(ClaimStatus.REJECTED, ClaimStatus.DRAFT, materially_changed=True)
    with pytest.raises(ValueError):
        validate_append_transition(ClaimStatus.DRAFT, ClaimStatus.DRAFT, materially_changed=False)
    validate_begin_transition(ClaimStatus.REJECTED, ClaimStatus.DRAFT)
    validate_begin_transition(ClaimStatus.REVIEW_REQUIRED, ClaimStatus.DRAFT)
    with pytest.raises(ValueError):
        validate_begin_transition(ClaimStatus.APPROVED, ClaimStatus.DRAFT)
    validate_review_transition(ClaimStatus.IN_REVIEW, ClaimStatus.APPROVED,
                               supports_count=1, valid_until=_NOW + timedelta(days=1), statement_clock=_NOW)
    with pytest.raises(ValueError):
        validate_review_transition(ClaimStatus.IN_REVIEW, ClaimStatus.APPROVED,
                                   supports_count=0, valid_until=_NOW + timedelta(days=1), statement_clock=_NOW)
    with pytest.raises(ValueError):
        validate_review_transition(ClaimStatus.DRAFT, ClaimStatus.APPROVED,
                                   supports_count=1, valid_until=_NOW + timedelta(days=1), statement_clock=_NOW)
    validate_conflict_resolution_transition(ClaimStatus.APPROVED, ClaimStatus.REVIEW_REQUIRED)
    with pytest.raises(ValueError):
        validate_conflict_resolution_transition(ClaimStatus.REJECTED, ClaimStatus.DRAFT)
    assert local_eligibility_reason(
        ClaimStatus.APPROVED, valid_until=_NOW, statement_clock=_NOW,
        has_open_material_conflict=True, supports_count=0,
    ) is LocalEligibilityReason.EXPIRED
    assert local_eligibility_reason(
        ClaimStatus.APPROVED, valid_until=None, statement_clock=_NOW,
        has_open_material_conflict=False, supports_count=1,
    ) is LocalEligibilityReason.EXPIRED
    assert local_eligibility_reason(
        ClaimStatus.APPROVED, valid_until=_NOW + timedelta(days=1), statement_clock=_NOW,
        has_open_material_conflict=True, supports_count=0,
    ) is LocalEligibilityReason.MATERIAL_CONFLICT
    assert local_eligibility_reason(
        ClaimStatus.APPROVED, valid_until=_NOW + timedelta(days=1), statement_clock=_NOW,
        has_open_material_conflict=False, supports_count=1,
    ) is LocalEligibilityReason.LOCALLY_READY_REQUIRES_FINS_VALIDATION


@pytest.mark.unit
def test_candidate_payload_is_bounded_canonical_and_finite() -> None:
    """候选 ingress 拒绝重复键、BOM、非有限与非 canonical 输入。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非法 payload 被接受。
    """

    canonical = canonical_json_document(b'{"b":2,"a":1}')
    assert canonical == b'{"a":1,"b":2}'
    request = ResearchCandidateCreateRequest(uuid4(), uuid4(), CandidateOrigin.AGENT,
                                             canonical, uuid4())
    assert len(request.sha256) == 64
    with pytest.raises(ValueError):
        replace(request, canonical_payload_json=b'{"b":2,"a":1}')
    with pytest.raises(ValueError):
        canonical_json_document(b'{"x":1,"x":2}')
    with pytest.raises(ValueError):
        canonical_json_document(b'{"x":1e999}')
    with pytest.raises(ValueError):
        canonical_json_document(b'{"x":1}' + b" " * 100, max_bytes=50)


@pytest.mark.unit
def test_dtos_are_frozen_slots_and_nil_uuid_rejected() -> None:
    """公开 DTO 不可变且 caller ID 不能使用 nil UUID。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: DTO 可修改或 nil ID 被接受。
    """

    locator = _locator()
    with pytest.raises(FrozenInstanceError):
        locator.ticker = "MSFT"  # type: ignore[misc]
    assert hasattr(locator, "__slots__")
    with pytest.raises(ValueError):
        EvidenceLinkRequest(UUID(int=0), EvidenceRelation.SUPPORTS, fact_id=uuid4())


@pytest.mark.unit
def test_claim_version_snapshot_and_link_projection_closure() -> None:
    """持久化投影要求 shell/current/link 同 tenant、company、version。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 投影身份漂移被接受。
    """

    tenant_id, company_id, claim_id, version_id = uuid4(), uuid4(), uuid4(), uuid4()
    request = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS, fact_id=uuid4())
    link = EvidenceLink(tenant_id, company_id, version_id, request, None, _NOW)
    version = ClaimVersion(
        id=version_id, tenant_id=tenant_id, company_id=company_id, claim_id=claim_id,
        version_no=1, transition_kind=ClaimTransitionKind.CLAIM_CREATE,
        evidence_mode=EvidenceMode.REPLACE_ALL, copy_source_version_id=None,
        operation_id=uuid4(), operation_fingerprint=_HASH, content=_content(),
        author_user_id=None, author_auth=None, reviewer=None, created_at=_NOW,
    )
    snapshot = ClaimSnapshot(claim_id, tenant_id, company_id, 1, _NOW, _NOW,
                             version, (link,))
    assert snapshot.current == version
    with pytest.raises(ValueError):
        replace(snapshot, version=2)
    with pytest.raises(ValueError):
        replace(snapshot, links=(link, link))
    with pytest.raises(ValueError):
        replace(link, locator_index_digest=b"x" * 32)
    direct = EvidenceLinkRequest(uuid4(), EvidenceRelation.CONTEXT,
                                 security_id=uuid4(), locator=_locator())
    assert EvidenceLink(tenant_id, company_id, version_id, direct, b"x" * 32, _NOW)
    with pytest.raises(ValueError):
        EvidenceLink(tenant_id, company_id, version_id, direct, None, _NOW)
    with pytest.raises(ValueError):
        replace(version, evidence_mode=EvidenceMode.COPY_PREVIOUS)
    with pytest.raises(ValueError):
        replace(version, transition_kind=ClaimTransitionKind.REVIEW_DECISION)


@pytest.mark.unit
def test_reviewer_witness_and_review_version_are_not_bearer_inputs() -> None:
    """review 投影持完整认证 witness，结构上不保存 raw bearer。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: reviewer witness 缺失或权限键错误被接受。
    """

    witness = ReviewWitness(
        reviewer_user_id=uuid4(), reviewer_token_id=uuid4(),
        user_role_id=uuid4(), role_permission_id=uuid4(), permission_id=uuid4(),
        permission_key="investment.claim.review", checked_at=_NOW,
        policy_version="v1", reason="checked",
    )
    version = ClaimVersion(
        id=uuid4(), tenant_id=uuid4(), company_id=uuid4(), claim_id=uuid4(),
        version_no=2, transition_kind=ClaimTransitionKind.REVIEW_DECISION,
        evidence_mode=EvidenceMode.COPY_PREVIOUS, copy_source_version_id=uuid4(),
        operation_id=uuid4(), operation_fingerprint=_HASH,
        content=_content(ClaimStatus.APPROVED), author_user_id=None,
        author_auth=None, reviewer=witness, created_at=_NOW,
    )
    assert version.reviewer == witness
    assert not hasattr(version, "raw_token")
    assert not hasattr(witness, "role_id")
    with pytest.raises(ValueError):
        replace(witness, user_role_id=UUID(int=0))
    with pytest.raises(ValueError):
        replace(witness, role_permission_id=UUID(int=0))
    with pytest.raises(ValueError):
        replace(witness, permission_key="investment.claim.write")
    with pytest.raises(ValueError):
        replace(version, reviewer=None)


@pytest.mark.unit
def test_conflict_open_resolve_request_and_projection() -> None:
    """冲突端点排序、resolution successor 与 witness 完整性闭合。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非法冲突结构被接受。
    """

    low, high = sorted((uuid4(), uuid4()), key=lambda value: value.int)
    opened = ClaimConflictOpenRequest(uuid4(), uuid4(), low, high, True,
                                      "material contradiction", uuid4())
    with pytest.raises(ValueError):
        replace(opened, left_version_id=high, right_version_id=low)
    resolved_request = ClaimConflictResolveRequest(
        conflict_id=opened.id, selected_claim_id=uuid4(), expected_selected_version=2,
        expected_other_version=1, expected_conflict_version=1,
        new_version_id=uuid4(), new_link_id=uuid4(),
        content=_content(ClaimStatus.DRAFT), evidence=_replace_links(),
        resolution_reason="new evidence", operation_id=uuid4(),
    )
    assert resolved_request.content.status is ClaimStatus.DRAFT
    with pytest.raises(ValueError):
        replace(resolved_request, content=_content(ClaimStatus.APPROVED))
    conflict = ClaimConflict(
        id=opened.id, tenant_id=uuid4(), company_id=opened.company_id,
        left_version_id=low, right_version_id=high, material=True,
        status=ConflictStatus.OPEN, reason=opened.reason, version=1,
        created_at=_NOW, updated_at=_NOW, operation_id=opened.operation_id,
        operation_fingerprint=_HASH, resolution_new_version_id=None,
        resolution_new_link_id=None, resolution_operation_id=None, reviewer=None,
    )
    assert conflict.status is ConflictStatus.OPEN
    with pytest.raises(ValueError):
        replace(conflict, status=ConflictStatus.RESOLVED)
    witness = ReviewWitness(
        reviewer_user_id=uuid4(), reviewer_token_id=uuid4(),
        user_role_id=uuid4(), role_permission_id=uuid4(), permission_id=uuid4(),
        permission_key="investment.claim.review", checked_at=_NOW,
        policy_version="v1", reason="resolved",
    )
    assert replace(
        conflict, status=ConflictStatus.RESOLVED, version=2,
        resolution_new_version_id=resolved_request.new_version_id,
        resolution_new_link_id=resolved_request.new_link_id,
        resolution_operation_id=resolved_request.operation_id,
        reviewer=witness,
    )


@pytest.mark.unit
def test_fact_candidate_projection_and_remaining_local_reasons() -> None:
    """Fact PIT revision identity、candidate staging 和局部原因完整输出。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 投影身份或状态错误。
    """

    pit = FactPitTimes(None, None, _NOW, _NOW, _NOW, _NOW)
    request = FactCreateRequest(
        id=uuid4(), company_id=uuid4(), security_id=uuid4(),
        fact_series_id=uuid4(), revision_no=2, prior_fact_id=uuid4(),
        fact_key="Revenue", metric="revenue", locator=_locator(),
        value=FactValue(FactValueKind.TEXT, value_text="reported"), pit=pit,
        extractor_version="v1", verification_status=VerificationStatus.UNVERIFIED,
        verifier_user_id=None, verified_at=None, operation_id=uuid4(),
    )
    fact = Fact(request.id, uuid4(), request, _HASH, _NOW)
    assert fact.revision_id == request.id
    assert fact.prior_revision_id == request.prior_fact_id
    assert fact.to_pit_projection().effective_at == pit.effective_at
    assert fact.to_pit_projection().revision_id == request.id
    with pytest.raises(ValueError):
        replace(fact, id=uuid4())
    candidate_request = ResearchCandidateCreateRequest(
        uuid4(), request.company_id, CandidateOrigin.HUMAN,
        b'{"metric":"revenue"}', uuid4(),
    )
    candidate = ResearchCandidate(uuid4(), candidate_request, CandidateStatus.PROPOSED,
                                  1, _HASH, _NOW, _NOW, None)
    assert candidate.request.sha256 == canonical_sha256({"metric": "revenue"})
    with pytest.raises(ValueError):
        replace(candidate, rejection_code="bad")
    assert replace(candidate, state=CandidateStatus.REJECTED, rejection_code="bad")
    assert local_eligibility_reason(
        ClaimStatus.DRAFT, valid_until=None, statement_clock=_NOW,
        has_open_material_conflict=False, supports_count=0,
    ) is LocalEligibilityReason.NOT_APPROVED
    assert local_eligibility_reason(
        ClaimStatus.APPROVED, valid_until=_NOW + timedelta(days=1), statement_clock=_NOW,
        has_open_material_conflict=False, supports_count=0,
    ) is LocalEligibilityReason.MISSING_SUPPORT
