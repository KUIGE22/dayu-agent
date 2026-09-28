"""候选接入的纯上下文、闭合拒绝原因与不可变首结果契约。

本模块不决定 Fins 当前有效性、晋升权威或 SQL 事务，只验证一次接入的
完整请求身份与 proposed/rejected 结果是否闭合。原始输出只保留 hash/count。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

from dayu.investment.domain.evidence import (
    CandidateOrigin,
    CandidateStatus,
    FactCandidatePayload,
    JsonValue,
    canonical_json_bytes,
)
from dayu.investment.domain.identifiers import TenantScope

CANDIDATE_INTAKE_SCHEMA = "candidate_intake.v1"
MAX_CANDIDATE_BYTES = 1_048_576
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_TICKER = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]*\Z")


class CandidateIntakeRejectionCode(str, Enum):
    """业务拒绝的完整闭合集合；不保存依赖异常 message。"""

    PAYLOAD_TOO_LARGE = "candidate_payload_too_large"
    JSON_INVALID = "candidate_json_invalid"
    SCHEMA_INVALID = "candidate_schema_invalid"
    MATERIAL_CLAIM_UNSUPPORTED = "unsupported_material_claim"
    EVIDENCE_MISSING = "evidence_missing"
    CROSS_TICKER = "evidence_cross_ticker"
    UNAVAILABLE = "evidence_unavailable"
    AMBIGUOUS_OWNER = "evidence_ambiguous_owner"
    STALE = "evidence_stale"
    FRAGMENT_UNRESOLVED = "evidence_fragment_unresolved"
    READBACK_MISMATCH = "evidence_readback_mismatch"


def _uuid(value: UUID) -> None:
    """校验非 nil UUID。

    Args:
        value: 明确身份。
    Returns:
        无。
    Raises:
        ValueError: 身份类型或值非法。
    """
    if type(value) is not UUID or value.int == 0:
        raise ValueError("candidate_context_invalid")


def _text(value: str) -> None:
    """校验能安全写入 PostgreSQL 的非空文本。

    Args:
        value: 明确上下文字段。
    Returns:
        无。
    Raises:
        ValueError: 字段类型、空白或 Unicode 非法。
    """
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("candidate_context_invalid")
    if "\x00" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("candidate_context_invalid")


def _hash(value: str) -> None:
    """校验 lowercase SHA-256。

    Args:
        value: digest。
    Returns:
        无。
    Raises:
        ValueError: 非法 digest。
    """
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise ValueError("candidate_hash_invalid")


def _utc(value: datetime) -> None:
    """校验明确 UTC 时刻。

    Args:
        value: 观察或数据库时刻。
    Returns:
        无。
    Raises:
        ValueError: 类型或时区非法。
    """
    if type(value) is not datetime or value.utcoffset() != timedelta(0):
        raise ValueError("candidate_clock_invalid")


@dataclass(frozen=True, slots=True)
class CandidateIntakeContext:
    """可信 caller 的身份，Agent 无权供应这些字段。"""

    candidate_id: UUID
    operation_id: UUID
    company_id: UUID
    security_id: UUID
    origin: CandidateOrigin
    extractor_version: str

    def __post_init__(self) -> None:
        """校验完整上下文。

        Args:
            无。
        Returns:
            无。
        Raises:
            ValueError: UUID、origin 或版本文本非法。
        """
        for value in (self.candidate_id, self.operation_id, self.company_id, self.security_id):
            _uuid(value)
        if type(self.origin) is not CandidateOrigin:
            raise ValueError("candidate_context_invalid")
        _text(self.extractor_version)


@dataclass(frozen=True, slots=True)
class CandidateFinsValidationWitness:
    """一次 locator/citation 观察；不提供数据库授权或永久 source freshness。"""

    locator_sha256: str
    citation_sha256: str
    checked_at: datetime

    def __post_init__(self) -> None:
        """校验两个 digest 与 UTC 时刻。

        Args:
            无。
        Returns:
            无。
        Raises:
            ValueError: digest/clock 非法。
        """
        _hash(self.locator_sha256)
        _hash(self.citation_sha256)
        _utc(self.checked_at)


def _identity_fingerprint(
    tenant_id: UUID, context: CandidateIntakeContext, security_ticker: str,
    raw_sha256: str, raw_bytes: int,
) -> str:
    """承诺请求身份，排除 Fins 动态结果与所有观察/提交时刻。

    Args:
        tenant_id: 已校验的租户 UUID。
        context: 完整上下文。
        security_ticker: 明确证券原样 ticker。
        raw_sha256: 原始输出实算 digest。
        raw_bytes: 原始输出长度。
    Returns:
        candidate_intake.v1 canonical SHA-256。
    Raises:
        ValueError: 身份、ticker 或原始元数据非法。
    """
    _uuid(tenant_id)
    if type(context) is not CandidateIntakeContext:
        raise ValueError("candidate_context_invalid")
    _text(security_ticker)
    if _TICKER.fullmatch(security_ticker) is None:
        raise ValueError("candidate_context_invalid")
    _hash(raw_sha256)
    if type(raw_bytes) is not int or raw_bytes < 0:
        raise ValueError("candidate_raw_identity_invalid")
    frame: dict[str, JsonValue] = {
        "schema_version": CANDIDATE_INTAKE_SCHEMA, "tenant_id": str(tenant_id),
        "candidate_id": str(context.candidate_id), "operation_id": str(context.operation_id),
        "company_id": str(context.company_id), "security_id": str(context.security_id),
        "security_ticker": security_ticker, "origin": context.origin.value,
        "extractor_version": context.extractor_version, "raw_sha256": raw_sha256,
        "raw_bytes": raw_bytes,
    }
    return hashlib.sha256(canonical_json_bytes(frame)).hexdigest()


def intake_request_fingerprint(
    scope: TenantScope, context: CandidateIntakeContext, security_ticker: str,
    raw_sha256: str, raw_bytes: int,
) -> str:
    """从合法 TenantScope 派生请求指纹；不创造新的 scope 权威。

    Args:
        scope: Principal 派生的可信租户。
        context: 完整 caller 上下文。
        security_ticker: 显式证券 ticker。
        raw_sha256: 原输出 digest。
        raw_bytes: 原输出长度。
    Returns:
        canonical 请求指纹。
    Raises:
        ValueError: scope 身份或请求字段非法。
    """
    if type(scope) is not TenantScope:
        raise ValueError("candidate_context_invalid")
    tenant_id = UUID(scope.tenant_id.value)
    if str(tenant_id) != scope.tenant_id.value:
        raise ValueError("candidate_context_invalid")
    return _identity_fingerprint(tenant_id, context, security_ticker, raw_sha256, raw_bytes)


@dataclass(frozen=True, slots=True)
class CandidateIntakeRecordRequest:
    """一个成功 payload+witness 或一个固定拒绝码，不能携带原 raw。"""

    context: CandidateIntakeContext
    security_ticker: str
    raw_sha256: str
    raw_bytes: int
    payload: FactCandidatePayload | None
    witness: CandidateFinsValidationWitness | None
    rejection_code: CandidateIntakeRejectionCode | None

    def __post_init__(self) -> None:
        """验证二选一结果和证据 digest 自闭合。

        Args:
            无。
        Returns:
            无。
        Raises:
            ValueError: 上下文、结果 arm 或 witness 不闭合。
        """
        if type(self.context) is not CandidateIntakeContext:
            raise ValueError("candidate_context_invalid")
        _text(self.security_ticker)
        if _TICKER.fullmatch(self.security_ticker) is None:
            raise ValueError("candidate_context_invalid")
        _hash(self.raw_sha256)
        if type(self.raw_bytes) is not int or self.raw_bytes < 0:
            raise ValueError("candidate_raw_identity_invalid")
        if self.rejection_code is None:
            if type(self.payload) is not FactCandidatePayload or type(self.witness) is not CandidateFinsValidationWitness:
                raise ValueError("candidate_outcome_invalid")
            if self.payload.locator.ticker != self.security_ticker:
                raise ValueError("candidate_outcome_invalid")
            if (self.witness.locator_sha256 != hashlib.sha256(self.payload.locator.canonical_bytes()).hexdigest()
                    or self.witness.citation_sha256 != self.payload.locator.locator_content_sha256):
                raise ValueError("candidate_witness_invalid")
        elif (type(self.rejection_code) is not CandidateIntakeRejectionCode
              or self.payload is not None or self.witness is not None):
            raise ValueError("candidate_outcome_invalid")
        if len(self.payload_bytes()) > MAX_CANDIDATE_BYTES:
            raise ValueError("candidate_payload_too_large")

    def payload_bytes(self) -> bytes:
        """编码 proposed 九键或 rejected 四键 safe envelope。

        Args:
            无。
        Returns:
            实际 candidate payload canonical bytes。
        Raises:
            ValueError: 结果 arm 不闭合。
        """
        if self.payload is not None:
            return self.payload.canonical_bytes()
        if self.rejection_code is None:
            raise ValueError("candidate_outcome_invalid")
        return canonical_json_bytes({
            "schema_version": "rejected_intake.v1", "raw_sha256": self.raw_sha256,
            "raw_bytes": self.raw_bytes, "rejection_code": self.rejection_code.value,
        })


@dataclass(frozen=True, slots=True)
class CandidateIntakeReceipt:
    """不可变的第一次提交结果；candidate 当前状态不改变历史 outcome。"""

    tenant_id: UUID
    context: CandidateIntakeContext
    security_ticker: str
    raw_sha256: str
    raw_bytes: int
    request_fingerprint: str
    payload_sha256: str
    outcome: CandidateStatus
    rejection_code: CandidateIntakeRejectionCode | None
    witness: CandidateFinsValidationWitness | None
    created_at: datetime
    candidate_version: int = 1

    def __post_init__(self) -> None:
        """验证历史请求指纹与原始 outcome arm。

        Args:
            无。
        Returns:
            无。
        Raises:
            ValueError: 历史字段或 digest 不闭合。
        """
        _uuid(self.tenant_id)
        expected = _identity_fingerprint(self.tenant_id, self.context,
                                        self.security_ticker, self.raw_sha256, self.raw_bytes)
        if self.request_fingerprint != expected:
            raise ValueError("candidate_receipt_invalid")
        _hash(self.payload_sha256)
        _utc(self.created_at)
        if type(self.candidate_version) is not int or self.candidate_version != 1:
            raise ValueError("candidate_receipt_invalid")
        if self.outcome is CandidateStatus.PROPOSED:
            if self.rejection_code is not None or type(self.witness) is not CandidateFinsValidationWitness:
                raise ValueError("candidate_receipt_invalid")
        elif self.outcome is CandidateStatus.REJECTED:
            if type(self.rejection_code) is not CandidateIntakeRejectionCode or self.witness is not None:
                raise ValueError("candidate_receipt_invalid")
        else:
            raise ValueError("candidate_receipt_invalid")
