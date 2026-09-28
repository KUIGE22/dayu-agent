"""严格解析一项 Fact proposal；不抽取自由文本或产生权威 Fact。

JSON 边界拒绝 nested duplicate/float/constants/非法 Unicode，业务阶段使用
固定拒绝码；所有 parse exception 均不附带 raw、字段值或原异常链。
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import NoReturn

from dayu.investment.domain.candidate_intake import (
    MAX_CANDIDATE_BYTES,
    CandidateIntakeRejectionCode,
)
from dayu.investment.domain.evidence import (
    EvidenceLocatorSnapshot,
    FactCandidatePayload,
    FactValue,
    FactValueKind,
    JsonValue,
)

_ROOT_KEYS = frozenset({"schema_version", "candidate_type", "fact_key", "metric", "value",
                        "period_start", "period_end", "effective_at", "locator"})
_VALUE_KEYS = frozenset({"kind", "value"})
_DECIMAL_KEYS = _VALUE_KEYS | {"unit_code", "currency"}
_DECIMAL_TEXT = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?\Z")
_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_UTC_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z\Z")


class CandidateParseError(ValueError):
    """只携带闭合拒绝码，不泄漏 Agent 原内容。"""

    def __init__(self, code: CandidateIntakeRejectionCode) -> None:
        """构造固定码异常。

        Args:
            code: parser 的闭合原因。
        Returns:
            无。
        Raises:
            无。
        """
        super().__init__(code.value)
        self.code = code


def _reject_json(_: str) -> NoReturn:
    """拒绝 JSON float 或非标准常量。

    Args:
        _: JSON 原数值文本，不存储或返回。
    Returns:
        不返回。
    Raises:
        CandidateParseError: 固定 JSON_INVALID。
    """
    raise CandidateParseError(CandidateIntakeRejectionCode.JSON_INVALID)


def _unique_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """拒绝每一层 JSON 对象的重复键。

    Args:
        pairs: 原始键值对。
    Returns:
        唯一键对象。
    Raises:
        CandidateParseError: 任一重复键。
    """
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateParseError(CandidateIntakeRejectionCode.JSON_INVALID)
        result[key] = value
    return result


def _validate_strings(root: JsonValue) -> None:
    """迭代核验所有键/值 Unicode，避免额外递归与 JSONB NUL 故障。

    Args:
        root: 解码后的有限 JSON 树。
    Returns:
        无。
    Raises:
        CandidateParseError: NUL 或孤立 surrogate。
    """
    pending: list[JsonValue] = [root]
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            if "\x00" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
                raise CandidateParseError(CandidateIntakeRejectionCode.JSON_INVALID)
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def _string(value: JsonValue) -> str:
    """读取真实字符串，禁止隐式转换。

    Args:
        value: JSON 字段。
    Returns:
        原字符串。
    Raises:
        ValueError: 不是字符串。
    """
    if type(value) is not str:
        raise ValueError("candidate_schema_invalid")
    return value


def _date(value: JsonValue) -> date:
    """解析严格 YYYY-MM-DD。

    Args:
        value: 日期字段。
    Returns:
        原日期。
    Raises:
        ValueError: 类型、形态或真实日期非法。
    """
    text = _string(value)
    if _DATE_TEXT.fullmatch(text) is None:
        raise ValueError("candidate_schema_invalid")
    return date.fromisoformat(text)


def _time(value: JsonValue) -> datetime:
    """只允许带 Z 的严格 UTC RFC3339。

    Args:
        value: proposal 有效时刻。
    Returns:
        aware UTC datetime。
    Raises:
        ValueError: 文本形态或时间非法。
    """
    text = _string(value)
    if _UTC_TEXT.fullmatch(text) is None:
        raise ValueError("candidate_schema_invalid")
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _fact_value(value: JsonValue) -> FactValue:
    """解析四个精确 arm，并复用 FactValue 未舍入校验。

    Args:
        value: 值对象。
    Returns:
        一个不可变 FactValue。
    Raises:
        ValueError: arm、类型或精度非法。
    """
    if type(value) is not dict:
        raise ValueError("candidate_schema_invalid")
    kind = FactValueKind(_string(value.get("kind")))
    if set(value) != (_DECIMAL_KEYS if kind is FactValueKind.DECIMAL else _VALUE_KEYS):
        raise ValueError("candidate_schema_invalid")
    if kind is FactValueKind.DECIMAL:
        decimal = _string(value["value"])
        if _DECIMAL_TEXT.fullmatch(decimal) is None:
            raise ValueError("candidate_schema_invalid")
        currency = value["currency"]
        return FactValue(kind, value_decimal=Decimal(decimal), unit_code=_string(value["unit_code"]),
                         currency=None if currency is None else _string(currency))
    if kind is FactValueKind.TEXT:
        return FactValue(kind, value_text=_string(value["value"]))
    if kind is FactValueKind.DATE:
        return FactValue(kind, value_date=_date(value["value"]))
    boolean = value["value"]
    if type(boolean) is not bool:
        raise ValueError("candidate_schema_invalid")
    return FactValue(kind, value_boolean=boolean)


def parse_fact_candidate(raw: bytes) -> FactCandidatePayload:
    """按固定阶段顺序解析唯一九键 Fact proposal。

    Args:
        raw: 可信 caller 传入的 Agent 输出 bytes。
    Returns:
        完整 typed payload，无 ID/witness/PIT。
    Raises:
        TypeError: caller 没有传 bytes。
        CandidateParseError: 固定业务拒绝码，不附原内容或异常链。
    """
    if type(raw) is not bytes:
        raise TypeError("research_input_invalid")
    if len(raw) > MAX_CANDIDATE_BYTES:
        raise CandidateParseError(CandidateIntakeRejectionCode.PAYLOAD_TOO_LARGE)
    try:
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("BOM")
        value: JsonValue = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                                      parse_float=_reject_json, parse_constant=_reject_json)
        _validate_strings(value)
    except (ValueError, UnicodeError, RecursionError):
        raise CandidateParseError(CandidateIntakeRejectionCode.JSON_INVALID) from None
    if type(value) is not dict:
        raise CandidateParseError(CandidateIntakeRejectionCode.JSON_INVALID)
    if value.get("candidate_type") == "claim":
        raise CandidateParseError(CandidateIntakeRejectionCode.MATERIAL_CLAIM_UNSUPPORTED)
    if (set(value) not in (_ROOT_KEYS, _ROOT_KEYS - {"locator"})
            or value.get("schema_version") != "fact_candidate.v1"
            or value.get("candidate_type") != "fact"):
        raise CandidateParseError(CandidateIntakeRejectionCode.SCHEMA_INVALID)
    if value.get("locator") is None:
        raise CandidateParseError(CandidateIntakeRejectionCode.EVIDENCE_MISSING)
    try:
        # 固定字段顺序：labels、value、period、effective_at、locator。
        fact_key = _string(value["fact_key"])
        metric = _string(value["metric"])
        fact_value = _fact_value(value["value"])
        start = None if value["period_start"] is None else _date(value["period_start"])
        end = None if value["period_end"] is None else _date(value["period_end"])
        payload = FactCandidatePayload(fact_key, metric, fact_value, start, end,
                                       _time(value["effective_at"]),
                                       EvidenceLocatorSnapshot.from_dict(value["locator"]))
        encoded = payload.canonical_bytes()
    except (ValueError, TypeError, OverflowError):
        raise CandidateParseError(CandidateIntakeRejectionCode.SCHEMA_INVALID) from None
    if len(encoded) > MAX_CANDIDATE_BYTES:
        raise CandidateParseError(CandidateIntakeRejectionCode.PAYLOAD_TOO_LARGE)
    return payload
