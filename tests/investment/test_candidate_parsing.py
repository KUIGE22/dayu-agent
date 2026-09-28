"""S32-A parser 精确形状、未舍入精度与拒绝优先级测试。"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from dayu.fins.domain.evidence_locator import parse_evidence_locator_projection
from dayu.investment.domain.candidate_intake import MAX_CANDIDATE_BYTES, CandidateIntakeRejectionCode
from dayu.investment.domain.candidate_parsing import CandidateParseError, parse_fact_candidate
from dayu.investment.domain.evidence import JsonValue


def proposal() -> dict[str, JsonValue]:
    """生成独立的九键 proposal 输入。

    Args:
        无。
    Returns:
        新 JSON 对象。
    Raises:
        无。
    """
    return {
        "schema_version": "fact_candidate.v1",
        "candidate_type": "fact",
        "fact_key": "Revenue",
        "metric": "Revenue",
        "value": {"kind": "decimal", "value": "-0.0000", "unit_code": "currency", "currency": "USD"},
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "effective_at": "2026-09-28T00:00:00.123Z",
        "locator": {
            "repository_id": "dayu.fins.public.v1",
            "ticker": "AAPL",
            "document_id": "fil_0001",
            "source_kind": "filing",
            "artifact_kind": "processed",
            "document_version": "v1",
            "source_fingerprint": "a" * 64,
            "primary_content_sha256": "b" * 64,
            "locator_kind": "document",
            "locator_payload": {},
            "locator_content_sha256": "c" * 64,
        },
    }


def _raw(value: dict[str, JsonValue]) -> bytes:
    """保留真实 UTF-8 编码以验证 canonical 扩张。

    Args:
        value: 输入树。
    Returns:
        输入 bytes。
    Raises:
        无。
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("document", {}),
        ("page", {"page_no": 1}),
        ("section", {"section_ref": "income"}),
        ("table_cell", {"table_ref": "income", "row_index": 0, "column": "Revenue"}),
        ("xbrl_fact", {"concept": "Revenue", "fact_sha256": "d" * 64}),
    ],
)
def test_five_locator_arms_equal_public_fins(kind: str, payload: dict[str, JsonValue]) -> None:
    """五 arm 都逐字段与公共 Fins parser 同形。

    Args:
        kind: locator kind。
        payload: exact arm。
    Returns:
        无。
    Raises:
        无。
    """
    value = proposal()
    locator = cast(dict[str, JsonValue], value["locator"])
    locator.update(locator_kind=kind, locator_payload=payload)
    parsed = parse_fact_candidate(_raw(value))
    assert parsed.locator.to_dict() == parse_evidence_locator_projection(locator).to_dict()
    assert len(parsed.to_dict()) == 9
    assert parsed.period_start == date(2026, 1, 1)
    assert parsed.effective_at.microsecond == 123000
    assert parsed.value.value_decimal == Decimal("-0.0000")
    assert cast(dict[str, JsonValue], parsed.to_dict()["value"])["value"] == "-0.0000"
    assert parse_fact_candidate(parsed.canonical_bytes()) == parsed


@pytest.mark.parametrize(
    "value,expected",
    [
        (
            {"kind": "decimal", "value": "9" * 26 + "." + "9" * 12, "unit_code": "count", "currency": None},
            "9" * 26 + "." + "9" * 12,
        ),
        ({"kind": "decimal", "value": "0.000000000001", "unit_code": "ratio", "currency": None}, "0.000000000001"),
        ({"kind": "text", "value": "exact text"}, "exact text"),
        ({"kind": "date", "value": "2024-02-29"}, "2024-02-29"),
        ({"kind": "boolean", "value": False}, False),
    ],
)
def test_value_arms_preserve_original_value(value: dict[str, JsonValue], expected: JsonValue) -> None:
    """四值 arm 和38/12边界保留原值，不舍入。

    Args:
        value: 合法值 arm。
        expected: serialized原值。
    Returns:
        无。
    Raises:
        无。
    """
    raw = proposal()
    raw["value"] = value
    raw["period_start"] = raw["period_end"] = None
    parsed = parse_fact_candidate(_raw(raw))
    assert cast(dict[str, JsonValue], parsed.to_dict()["value"])["value"] == expected
    assert parsed.period_start is parsed.period_end is None


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[]",
        b"{} {}",
        b"\xef\xbb\xbf{}",
        b"\xff",
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1.0}',
        b'{"x":1e2}',
        b'{"x":1,"x":2}',
        b'{"x":{"a":1,"a":2}}',
        b'{"x":"\\ud800"}',
        b'{"x":"\\u0000"}',
        b'{"\\u0000":1}',
        b"[" * 2000 + b"0" + b"]" * 2000,
    ],
)
def test_json_boundary_rejects_without_original_context(raw: bytes) -> None:
    """JSON结构/编码/重复键/浮点/Unicode都返回固定码。

    Args:
        raw: 无效输出。
    Returns:
        无。
    Raises:
        无。
    """
    with pytest.raises(CandidateParseError) as exc:
        parse_fact_candidate(raw)
    assert exc.value.code is CandidateIntakeRejectionCode.JSON_INVALID
    assert str(exc.value) == "candidate_json_invalid"
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None or exc.value.__suppress_context__


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "decimal", "value": "1e2", "unit_code": "count", "currency": None},
        {"kind": "decimal", "value": "+1", "unit_code": "count", "currency": None},
        {"kind": "decimal", "value": "01", "unit_code": "count", "currency": None},
        {"kind": "decimal", "value": "-00", "unit_code": "count", "currency": None},
        {"kind": "decimal", "value": "NaN", "unit_code": "count", "currency": None},
        {"kind": "decimal", "value": "0.0000000000000", "unit_code": "count", "currency": None},
        {"kind": "decimal", "value": "9" * 27 + "." + "9" * 12, "unit_code": "count", "currency": None},
        {"kind": "decimal", "value": 1, "unit_code": "count", "currency": None},
        {"kind": "decimal", "value": "1", "unit_code": "currency", "currency": None},
        {"kind": "decimal", "value": "1", "unit_code": "count", "currency": "USD"},
        {"kind": "decimal", "value": "1", "unit_code": "count"},
        {"kind": "text", "value": " x"},
        {"kind": "text", "value": ""},
        {"kind": "text", "value": "x", "unit_code": "count"},
        {"kind": "date", "value": "2026-02-29"},
        {"kind": "date", "value": "20260928"},
        {"kind": "boolean", "value": 1},
        {"kind": "unknown", "value": True},
        [],
    ],
)
def test_bad_value_arms_are_schema_rejections(value: JsonValue) -> None:
    """精度与类型失败不会降级为宽松兼容 arm。

    Args:
        value: 无效值。
    Returns:
        无。
    Raises:
        无。
    """
    raw = proposal()
    raw["value"] = value
    with pytest.raises(CandidateParseError, match="^candidate_schema_invalid$"):
        parse_fact_candidate(_raw(raw))


@pytest.mark.parametrize(
    "key,value",
    [
        ("effective_at", "2026-09-28T00:00:00+00:00"),
        ("effective_at", "2026-09-28 00:00:00Z"),
        ("effective_at", "2026-09-28T00:00:00.1234567Z"),
        ("effective_at", "2026-09-28T00:00:60Z"),
        ("period_start", None),
        ("period_start", "2026-12-01"),
        ("period_end", "2026-06-31"),
        ("fact_key", "with spaces"),
        ("metric", 1),
        ("schema_version", "fact_candidate.v2"),
        ("candidate_type", "unknown"),
        ("unknown", True),
    ],
)
def test_root_shape_dates_and_utc_are_strict(key: str, value: JsonValue) -> None:
    """九键、严格日期与Z时间逐阶段收束。

    Args:
        key: 修改字段。
        value: 错误值。
    Returns:
        无。
    Raises:
        无。
    """
    raw = proposal()
    raw[key] = value
    with pytest.raises(CandidateParseError, match="^candidate_schema_invalid$"):
        parse_fact_candidate(_raw(raw))


def test_missing_locator_claim_and_size_have_distinct_safe_codes() -> None:
    """缺证据、Claim和两种大小限制都保持特定阶段原因。

    Args:
        无。
    Returns:
        无。
    Raises:
        无。
    """
    raw = proposal()
    del raw["locator"]
    with pytest.raises(CandidateParseError, match="^evidence_missing$"):
        parse_fact_candidate(_raw(raw))
    raw["locator"] = None
    with pytest.raises(CandidateParseError, match="^evidence_missing$"):
        parse_fact_candidate(_raw(raw))
    raw["candidate_type"] = "claim"
    with pytest.raises(CandidateParseError, match="^unsupported_material_claim$"):
        parse_fact_candidate(_raw(raw))
    with pytest.raises(CandidateParseError, match="^candidate_payload_too_large$"):
        parse_fact_candidate(b" " * (MAX_CANDIDATE_BYTES + 1))
    raw = proposal()
    raw["value"] = {"kind": "text", "value": "汉" * 200000}
    encoded = _raw(raw)
    assert len(encoded) < MAX_CANDIDATE_BYTES
    with pytest.raises(CandidateParseError, match="^candidate_payload_too_large$"):
        parse_fact_candidate(encoded)
    with pytest.raises(TypeError, match="^research_input_invalid$"):
        parse_fact_candidate(cast(bytes, "{}"))
