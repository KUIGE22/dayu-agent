"""Evidence Locator domain DTO / parser / canonical bytes 测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from typing import Mapping

import pytest

from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.evidence_locator import (
    REPOSITORY_ID,
    SCHEMA_VERSION,
    ArtifactKind,
    CitationProjection,
    DocumentLocatorPayload,
    EvidenceLocatorError,
    EvidenceLocatorProjection,
    JsonValue,
    LocatorKind,
    PageLocatorPayload,
    SectionLocatorPayload,
    TableCellLocatorPayload,
    XbrlFactLocatorPayload,
    _validate_dto,
    canonical_json_bytes,
    is_lower_hex_sha256,
    parse_evidence_locator_projection,
    parse_evidence_locator_request,
    sha256_hex,
    validate_evidence_locator_projection,
    validate_evidence_locator_request,
)

_FORBIDDEN_PATTERNS = (
    "file://",
    "http://",
    "https://",
    "s3://",
    "gs://",
    "bucket",
    "workspace/portfolio",
    "local://",
    "uri=",
    "handle=",
    ".dayu",
    "/Users/",
    "C:\\",
)


def _build_request_dict(**overrides: JsonValue) -> dict[str, JsonValue]:
    """构造合法 request 字典。"""

    payload: dict[str, JsonValue] = {
        "schema_version": SCHEMA_VERSION,
        "repository_id": REPOSITORY_ID,
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
    }
    payload.update(overrides)
    return payload


def _assert_no_leak(value: JsonValue | bytes, path: str) -> None:
    """递归扫描输出，确保不含路径/URI/bucket/handle 信号。"""

    if isinstance(value, str):
        lowered = value.lower()
        for pattern in _FORBIDDEN_PATTERNS:
            assert pattern not in lowered, f"{path} 泄漏 forbidden pattern {pattern!r}: {value!r}"
        return
    if isinstance(value, bytes):
        _assert_no_leak(value.decode("utf-8", errors="ignore"), path)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_no_leak(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_no_leak(item, f"{path}[{index}]")
        return


@pytest.mark.unit
def test_payload_dataclasses_are_frozen_and_slots() -> None:
    """验证 payload DTO 均为 frozen + slots。"""

    assert PageLocatorPayload.__slots__ == ("page_no",)
    payload = PageLocatorPayload(page_no=1)
    with pytest.raises(FrozenInstanceError):
        setattr(payload, "page_no", 2)


@pytest.mark.unit
def test_canonical_json_bytes_sorted_compact_utf8() -> None:
    """验证 canonical JSON：sorted keys、compact separators、UTF-8。"""

    data = {"b": 1, "a": {"d": 2, "c": 3}}
    encoded = canonical_json_bytes(data)
    assert encoded == b'{"a":{"c":3,"d":2},"b":1}'
    assert isinstance(encoded, bytes)


@pytest.mark.unit
def test_canonical_json_bytes_rejects_nan() -> None:
    """验证 canonical JSON 拒绝 NaN/Infinity。"""

    with pytest.raises(ValueError):
        canonical_json_bytes({"value": float("nan")})
    with pytest.raises(ValueError):
        canonical_json_bytes({"value": float("inf")})


@pytest.mark.unit
def test_sha256_hex_and_is_lower_hex_sha256() -> None:
    """验证 SHA helper 与格式校验。"""

    digest = sha256_hex(b"hello")
    assert len(digest) == 64
    assert digest == digest.lower()
    assert is_lower_hex_sha256(digest)
    assert not is_lower_hex_sha256(digest.upper())
    assert not is_lower_hex_sha256("abc")
    assert not is_lower_hex_sha256("")


@pytest.mark.unit
def test_parse_request_document_payload() -> None:
    """验证 document 定位器请求解析。"""

    request = parse_evidence_locator_request(_build_request_dict())
    assert request.repository_id == REPOSITORY_ID
    assert request.schema_version == SCHEMA_VERSION
    assert request.ticker == "AAPL"
    assert request.document_id == "fil_0001"
    assert request.source_kind is SourceKind.FILING
    assert request.artifact_kind is ArtifactKind.PROCESSED
    assert request.locator_kind is LocatorKind.DOCUMENT
    assert isinstance(request.locator_payload, DocumentLocatorPayload)
    assert request.locator_payload.to_dict() == {}


@pytest.mark.unit
def test_parse_request_page_payload() -> None:
    """验证 page 定位器请求解析。"""

    request = parse_evidence_locator_request(
        _build_request_dict(locator_kind="page", locator_payload={"page_no": 7})
    )
    assert request.locator_kind is LocatorKind.PAGE
    assert isinstance(request.locator_payload, PageLocatorPayload)
    assert request.locator_payload.page_no == 7


@pytest.mark.unit
def test_parse_request_section_payload() -> None:
    """验证 section 定位器请求解析。"""

    request = parse_evidence_locator_request(
        _build_request_dict(locator_kind="section", locator_payload={"section_ref": "s_0001"})
    )
    assert request.locator_kind is LocatorKind.SECTION
    assert isinstance(request.locator_payload, SectionLocatorPayload)
    assert request.locator_payload.section_ref == "s_0001"


@pytest.mark.unit
def test_parse_request_table_cell_payload() -> None:
    """验证 table_cell 定位器请求解析。"""

    request = parse_evidence_locator_request(
        _build_request_dict(
            locator_kind="table_cell",
            locator_payload={"table_ref": "t_0001", "row_index": 3, "column": "Revenue"},
        )
    )
    assert request.locator_kind is LocatorKind.TABLE_CELL
    assert isinstance(request.locator_payload, TableCellLocatorPayload)
    assert request.locator_payload.table_ref == "t_0001"
    assert request.locator_payload.row_index == 3
    assert request.locator_payload.column == "Revenue"


@pytest.mark.unit
def test_parse_request_xbrl_fact_payload() -> None:
    """验证 xbrl_fact 定位器请求解析。"""

    request = parse_evidence_locator_request(
        _build_request_dict(
            locator_kind="xbrl_fact",
            locator_payload={"concept": "Revenue", "fact_sha256": "d" * 64},
        )
    )
    assert request.locator_kind is LocatorKind.XBRL_FACT
    assert isinstance(request.locator_payload, XbrlFactLocatorPayload)
    assert request.locator_payload.concept == "Revenue"
    assert request.locator_payload.fact_sha256 == "d" * 64


@pytest.mark.unit
def test_parse_request_rejects_missing_fields() -> None:
    """验证 missing 字段拒绝。"""

    raw = _build_request_dict()
    del raw["ticker"]
    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(raw)
    assert excinfo.value.code == "invalid_fields"


@pytest.mark.unit
def test_parse_request_rejects_unknown_fields() -> None:
    """验证 unknown 字段拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(extra_field="x"))
    assert excinfo.value.code == "invalid_fields"


@pytest.mark.unit
def test_parse_request_rejects_bool_as_int() -> None:
    """验证 bool-as-int 拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(
            _build_request_dict(
                locator_kind="table_cell",
                locator_payload={"table_ref": "t_0001", "row_index": True, "column": "A"},
            )
        )
    assert excinfo.value.code == "invalid_type"


@pytest.mark.unit
def test_parse_request_rejects_page_non_positive() -> None:
    """验证 page 定位器非正整数拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(
            _build_request_dict(locator_kind="page", locator_payload={"page_no": 0})
        )
    assert excinfo.value.code == "invalid_format"


@pytest.mark.unit
def test_parse_request_rejects_empty_string() -> None:
    """验证空字符串拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(ticker=""))
    assert excinfo.value.code == "invalid_format"


@pytest.mark.unit
def test_parse_request_rejects_non_canonical_ticker() -> None:
    """验证非 canonical ticker 拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(ticker="AAPL OTC"))
    assert excinfo.value.code == "invalid_ticker"


@pytest.mark.unit
def test_parse_request_rejects_non_canonical_document_id() -> None:
    """验证非 canonical document id 拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(document_id="bad id"))
    assert excinfo.value.code == "invalid_document_id"


@pytest.mark.unit
def test_parse_request_rejects_non_lower_hex() -> None:
    """验证非小写 64-hex SHA 拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(source_fingerprint="ABC"))
    assert excinfo.value.code == "invalid_sha256"


@pytest.mark.unit
def test_parse_request_rejects_unknown_schema_version() -> None:
    """验证未知 schema version 拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(schema_version="fins-evidence-locator-v2"))
    assert excinfo.value.code == "unsupported_schema_version"


@pytest.mark.unit
def test_parse_request_rejects_unknown_repository_id() -> None:
    """验证未知 repository id 拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(repository_id="com.example.other"))
    assert excinfo.value.code == "unsupported_repository_id"


@pytest.mark.unit
def test_parse_request_rejects_unknown_enum_values() -> None:
    """验证未知枚举值拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(source_kind="website"))
    assert excinfo.value.code == "unsupported_source_kind"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(artifact_kind="raw"))
    assert excinfo.value.code == "unsupported_artifact_kind"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(_build_request_dict(locator_kind="table"))
    assert excinfo.value.code == "unsupported_locator_kind"


@pytest.mark.unit
def test_parse_request_rejects_document_payload_with_fields() -> None:
    """验证 document 定位器不允许携带字段。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(
            _build_request_dict(locator_kind="document", locator_payload={"page_no": 1})
        )
    assert excinfo.value.code == "invalid_payload"


@pytest.mark.unit
def test_parse_projection_round_trip() -> None:
    """验证 projection to_json -> parse round-trip 一致。"""

    import json

    request = parse_evidence_locator_request(
        _build_request_dict(
            locator_kind="table_cell",
            locator_payload={"table_ref": "t_1", "row_index": 0, "column": "A"},
        )
    )
    projection = EvidenceLocatorProjection(
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
    json_bytes = projection.to_json()
    parsed = parse_evidence_locator_projection(json.loads(json_bytes.decode("utf-8")))
    assert parsed == projection


@pytest.mark.unit
def test_parse_projection_accepts_json_text() -> None:
    """验证 projection parse 接受 canonical JSON 文本。"""

    import json

    projection = parse_evidence_locator_projection(
        json.loads(json.dumps(_build_projection_dict()))
    )
    assert projection.ticker == "AAPL"


def _build_projection_dict() -> dict[str, JsonValue]:
    """构造合法 projection 字典。"""

    return {
        "repository_id": REPOSITORY_ID,
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
    }


@pytest.mark.unit
def test_parse_projection_rejects_unknown_fields() -> None:
    """验证 projection parse 拒绝 unknown 字段。"""

    raw = _build_projection_dict()
    raw["tenant_id"] = "tenant-a"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_projection(raw)
    assert excinfo.value.code == "invalid_fields"


@pytest.mark.unit
def test_projection_to_json_has_no_path_leak() -> None:
    """验证 projection 输出递归不含路径/URI/bucket/handle。"""

    projection = parse_evidence_locator_projection(_build_projection_dict())
    _assert_no_leak(projection.to_json(), "projection.to_json")


@pytest.mark.unit
def test_citation_projection_is_frozen_slots() -> None:
    """验证 CitationProjection 为 frozen + slots。"""

    assert "__slots__" in CitationProjection.__dict__
    projection = parse_evidence_locator_projection(_build_projection_dict())
    citation = CitationProjection(
        locator=projection,
        content_type="application/json",
        content_bytes=b"{}",
    )
    assert citation.content_bytes == b"{}"


@pytest.mark.unit
def test_evidence_locator_error_has_code() -> None:
    """验证 EvidenceLocatorError 携带稳定错误码。"""

    error = EvidenceLocatorError("test_code", "message")
    assert error.code == "test_code"
    assert error.message == "message"


@pytest.mark.parametrize(
    "locator_kind,payload",
    [
        ("page", {"page_no": 1, "extra": "x"}),
        ("section", {"section_ref": "s_1", "extra": "x"}),
        ("table_cell", {"table_ref": "t_1", "row_index": 0, "column": "A", "extra": "x"}),
        ("xbrl_fact", {"concept": "Revenue", "fact_sha256": "d" * 64, "extra": "x"}),
    ],
)
def test_parse_request_rejects_nested_payload_extra(
    locator_kind: str,
    payload: dict[str, JsonValue],
) -> None:
    """验证四种 non-document payload 的 nested-extra 字段拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(
            _build_request_dict(locator_kind=locator_kind, locator_payload=payload)
        )
    assert excinfo.value.code == "invalid_fields"


@pytest.mark.parametrize(
    "locator_kind,payload",
    [
        ("page", {"page_no": 1, "extra": "x"}),
        ("section", {"section_ref": "s_1", "extra": "x"}),
        ("table_cell", {"table_ref": "t_1", "row_index": 0, "column": "A", "extra": "x"}),
        ("xbrl_fact", {"concept": "Revenue", "fact_sha256": "d" * 64, "extra": "x"}),
    ],
)
def test_parse_projection_rejects_nested_payload_extra(
    locator_kind: str,
    payload: dict[str, JsonValue],
) -> None:
    """验证 projection parser 对四种 nested-extra 字段拒绝。"""

    raw = _build_projection_dict()
    raw["locator_kind"] = locator_kind
    raw["locator_payload"] = payload
    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_projection(raw)
    assert excinfo.value.code == "invalid_fields"


@pytest.mark.parametrize(
    "locator_kind,payload",
    [
        ("page", {}),
        ("section", {}),
        ("table_cell", {"table_ref": "t_1"}),
        ("xbrl_fact", {"concept": "Revenue"}),
    ],
)
def test_parse_request_rejects_nested_payload_missing(
    locator_kind: str,
    payload: dict[str, JsonValue],
) -> None:
    """验证四种 non-document payload 的 nested-missing 字段拒绝。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        parse_evidence_locator_request(
            _build_request_dict(locator_kind=locator_kind, locator_payload=payload)
        )
    assert excinfo.value.code == "invalid_fields"


@pytest.mark.unit
def test_validate_request_rejects_unknown_schema_and_repository() -> None:
    """验证 direct-DTO validator 拒绝 unknown schema/repository。"""

    request = parse_evidence_locator_request(_build_request_dict())
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(replace(request, schema_version="fins-evidence-locator-v2"))
    assert excinfo.value.code == "unsupported_schema_version"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(replace(request, repository_id="untrusted.repo"))
    assert excinfo.value.code == "unsupported_repository_id"


@pytest.mark.unit
def test_validate_request_rejects_wrong_payload_type() -> None:
    """验证 direct-DTO validator 拒绝 locator kind/payload 配对错误。"""

    request = parse_evidence_locator_request(_build_request_dict())
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(
            replace(
                request,
                locator_kind=LocatorKind.PAGE,
                locator_payload=SectionLocatorPayload(section_ref="s_1"),
            )
        )
    assert excinfo.value.code == "invalid_locator_payload"


@pytest.mark.unit
def test_validate_request_rejects_source_wrong_payload() -> None:
    """验证 direct-DTO validator 拒绝 source artifact 非 document 组合。"""

    request = parse_evidence_locator_request(_build_request_dict())
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(
            replace(
                request,
                artifact_kind=ArtifactKind.SOURCE,
                locator_kind=LocatorKind.PAGE,
                locator_payload=PageLocatorPayload(page_no=1),
            )
        )
    assert excinfo.value.code == "artifact_kind_not_supported"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(
            replace(
                request,
                artifact_kind=ArtifactKind.SOURCE,
                locator_kind=LocatorKind.SECTION,
                locator_payload=SectionLocatorPayload(section_ref="s_1"),
            )
        )
    assert excinfo.value.code == "artifact_kind_not_supported"


@pytest.mark.unit
def test_validate_request_rejects_bad_canonical_or_hash() -> None:
    """验证 direct-DTO validator 拒绝非 canonical 标识与非法 hash。"""

    request = parse_evidence_locator_request(_build_request_dict())
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(replace(request, ticker="AAPL OTC"))
    assert excinfo.value.code == "invalid_ticker"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(replace(request, document_id="bad id"))
    assert excinfo.value.code == "invalid_document_id"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(replace(request, source_fingerprint="XYZ"))
    assert excinfo.value.code == "invalid_sha256"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(replace(request, locator_content_sha256=""))
    assert excinfo.value.code == "invalid_sha256"


@pytest.mark.unit
def test_validate_dto_rejects_raw_string_enum() -> None:
    """验证 DTO 核心校验拒绝字符串冒充枚举。"""

    with pytest.raises(EvidenceLocatorError) as excinfo:
        _validate_dto(
            schema_version=None,
            repository_id=REPOSITORY_ID,
            ticker="AAPL",
            document_id="fil_0001",
            source_kind="filing",
            artifact_kind=ArtifactKind.PROCESSED,
            document_version="v1",
            source_fingerprint="f" * 64,
            primary_content_sha256="b" * 64,
            locator_kind=LocatorKind.DOCUMENT,
            locator_payload=DocumentLocatorPayload(),
            locator_content_sha256="c" * 64,
        )
    assert excinfo.value.code == "invalid_enum_type"
    with pytest.raises(EvidenceLocatorError) as excinfo:
        _validate_dto(
            schema_version=None,
            repository_id=REPOSITORY_ID,
            ticker="AAPL",
            document_id="fil_0001",
            source_kind=SourceKind.FILING,
            artifact_kind="processed",
            document_version="v1",
            source_fingerprint="f" * 64,
            primary_content_sha256="b" * 64,
            locator_kind=LocatorKind.DOCUMENT,
            locator_payload=DocumentLocatorPayload(),
            locator_content_sha256="c" * 64,
        )
    assert excinfo.value.code == "invalid_enum_type"


@pytest.mark.unit
def test_validate_projection_rejects_unknown_repository() -> None:
    """验证 direct-DTO projection validator 拒绝 unknown repository。"""

    projection = parse_evidence_locator_projection(_build_projection_dict())
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_projection(replace(projection, repository_id="untrusted.repo"))
    assert excinfo.value.code == "unsupported_repository_id"


@pytest.mark.unit
def test_validate_request_rejects_bool_page_no() -> None:
    """验证 direct-DTO 的 bool page_no fail closed。"""

    request = parse_evidence_locator_request(_build_request_dict())
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(
            replace(
                request,
                locator_kind=LocatorKind.PAGE,
                locator_payload=PageLocatorPayload(page_no=True),
            )
        )
    assert excinfo.value.code == "invalid_type"


@pytest.mark.unit
def test_validate_request_rejects_bool_row_index() -> None:
    """验证 direct-DTO 的 bool row_index fail closed。"""

    request = parse_evidence_locator_request(_build_request_dict())
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(
            replace(
                request,
                locator_kind=LocatorKind.TABLE_CELL,
                locator_payload=TableCellLocatorPayload(table_ref="t_1", row_index=True, column="A"),
            )
        )
    assert excinfo.value.code == "invalid_type"


@pytest.mark.unit
def test_validate_request_rejects_non_positive_page_no() -> None:
    """验证 direct-DTO 的 0/负 page_no fail closed。"""

    request = parse_evidence_locator_request(_build_request_dict())
    for page_no in (0, -1):
        with pytest.raises(EvidenceLocatorError) as excinfo:
            validate_evidence_locator_request(
                replace(
                    request,
                    locator_kind=LocatorKind.PAGE,
                    locator_payload=PageLocatorPayload(page_no=page_no),
                )
            )
        assert excinfo.value.code == "invalid_format"


@pytest.mark.unit
def test_validate_request_rejects_negative_row_index() -> None:
    """验证 direct-DTO 的负 row_index fail closed。"""

    request = parse_evidence_locator_request(_build_request_dict())
    with pytest.raises(EvidenceLocatorError) as excinfo:
        validate_evidence_locator_request(
            replace(
                request,
                locator_kind=LocatorKind.TABLE_CELL,
                locator_payload=TableCellLocatorPayload(table_ref="t_1", row_index=-1, column="A"),
            )
        )
    assert excinfo.value.code == "invalid_format"


@pytest.mark.unit
def test_require_real_int_rejects_non_int_and_bool() -> None:
    """验证真实 int 单一 helper 拒绝 bool/str/float/None 并接受 int。"""

    from dayu.fins.domain.evidence_locator import _require_real_int

    assert _require_real_int(7, "page_no") == 7
    for bad in (True, False, "1", 1.5, None):
        with pytest.raises(EvidenceLocatorError) as excinfo:
            _require_real_int(bad, "page_no")
        assert excinfo.value.code == "invalid_type"
