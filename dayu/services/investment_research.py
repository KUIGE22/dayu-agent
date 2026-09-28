"""可信候选接入 Service：严格 proposal → Fins 观察 → 原子 intake。

没有模型/Host 调度或晋升动作。Fins 公共接口是唯一 owner 校验入口；
旧 receipt 是耐久历史，不提供当前 source 就绪或权威批准。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import cast

from dayu.fins.domain.evidence_locator import (
    CitationProjection,
    EvidenceLocatorError,
    EvidenceLocatorProjection,
    parse_evidence_locator_projection,
)
from dayu.investment.domain.candidate_intake import (
    CandidateFinsValidationWitness,
    CandidateIntakeContext,
    CandidateIntakeReceipt,
    CandidateIntakeRecordRequest,
    CandidateIntakeRejectionCode,
    intake_request_fingerprint,
)
from dayu.investment.domain.candidate_parsing import CandidateParseError, parse_fact_candidate
from dayu.investment.domain.evidence import EvidenceLocatorSnapshot, FactCandidatePayload, JsonValue
from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantScope
from dayu.investment.domain.source import CompanyProjection, SecurityProjection
from dayu.investment.storage.candidate_intake_protocols import CandidateIntakeRepositoryProtocol
from dayu.investment.storage.protocols import IdentityRepositoryProtocol
from dayu.services.protocols import FinsServiceProtocol

_BUSINESS_CODES = {
    **dict.fromkeys(("source_identity_not_found", "source_deleted", "source_not_ingested",
                     "processed_not_found", "processed_deleted", "processed_reprocess_required"),
                    CandidateIntakeRejectionCode.UNAVAILABLE),
    "ambiguous_source_identity": CandidateIntakeRejectionCode.AMBIGUOUS_OWNER,
    **dict.fromkeys(("document_version_mismatch", "source_fingerprint_mismatch",
                     "processed_source_kind_mismatch", "processed_version_mismatch",
                     "processed_fingerprint_mismatch", "source_identity_changed",
                     "primary_content_changed", "primary_sha_mismatch",
                     "primary_content_sha256_mismatch", "locator_content_sha256_mismatch"),
                    CandidateIntakeRejectionCode.STALE),
    **dict.fromkeys(("table_row_out_of_range", "table_column_missing", "page_not_supported",
                     "xbrl_fact_not_unique"), CandidateIntakeRejectionCode.FRAGMENT_UNRESOLVED),
}


class ResearchContextError(ValueError):
    """可信 caller 的 scope/context/raw 输入非法，零候选写入。"""

    def __init__(self) -> None:
        """初始化固定 context error。

        Args:
            无。
        Returns:
            无。
        Raises:
            无。
        """
        super().__init__("research_context_invalid")


class ResearchDependencyError(RuntimeError):
    """依赖或 owner 契约不可用，零 candidate/receipt，可重试。"""

    def __init__(self) -> None:
        """初始化固定依赖 error。

        Args:
            无。
        Returns:
            无。
        Raises:
            无。
        """
        super().__init__("research_dependency_unavailable")


def _utc_now() -> datetime:
    """取默认 UTC 观察时刻，不与数据库时钟比较排序。

    Args:
        无。
    Returns:
        aware UTC datetime。
    Raises:
        无。
    """
    return datetime.now(timezone.utc)


class InvestmentResearchService:
    """通过显式 protocol 注入提供一个可运行的候选接入行为。"""

    def __init__(
        self, identity_repository: IdentityRepositoryProtocol,
        intake_repository: CandidateIntakeRepositoryProtocol,
        fins: FinsServiceProtocol, clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """保存明确依赖，不取得 Fins storage 或 SQL session。

        Args:
            identity_repository: 明确 company/security 读取 owner。
            intake_repository: candidate+receipt 原子 owner。
            fins: 公共 Fins validate/citation owner。
            clock: UTC 观察时钟。
        Returns:
            无。
        Raises:
            无。
        """
        self._identity = identity_repository
        self._intake = intake_repository
        self._fins = fins
        self._clock = clock

    def _ticker(self, scope: TenantScope, context: CandidateIntakeContext) -> str:
        """按明确 ID 核 company/security 配对，禁止猜 ticker 映射。

        Args:
            scope: caller scope。
            context: 完整上下文。
        Returns:
            证券原样 ticker。
        Raises:
            ResearchContextError: 目标缺失或不配对。
            ResearchDependencyError: owner 返回或存储失败。
        """
        company_id = CompanyId(str(context.company_id))
        security_id = SecurityId(str(context.security_id))
        try:
            company = self._identity.get_company(scope, company_id)
            security = self._identity.get_security(scope, security_id)
        except Exception:
            raise ResearchDependencyError() from None
        if company is None or security is None:
            raise ResearchContextError()
        if type(company) is not CompanyProjection or type(security) is not SecurityProjection:
            raise ResearchDependencyError()
        if (company.company_id != company_id or security.security_id != security_id
                or security.company_id != company_id):
            raise ResearchContextError()
        return security.ticker

    def _observe(
        self, payload: FactCandidatePayload,
    ) -> CandidateFinsValidationWitness | CandidateIntakeRejectionCode:
        """核完整 locator 与 citation raw bytes，返回观察或闭合业务码。

        Args:
            payload: 已严格解析的 proposal。
        Returns:
            一次 Fins witness 或业务拒绝码。
        Raises:
            ResearchDependencyError: owner/clock 契约或基础设施不可用。
        """
        try:
            locator = parse_evidence_locator_projection(payload.locator.to_dict())
            result = self._fins.validate_evidence_locator(locator)
            if result is not None:
                raise ResearchDependencyError()
            citation = self._fins.read_citation_projection(locator)
            if (type(citation) is not CitationProjection
                    or type(citation.locator) is not EvidenceLocatorProjection
                    or type(citation.content_bytes) is not bytes
                    or type(citation.content_type) is not str or not citation.content_type):
                raise ResearchDependencyError()
            readback = EvidenceLocatorSnapshot.from_dict(cast(JsonValue, citation.locator.to_dict()))
            content_sha = hashlib.sha256(citation.content_bytes).hexdigest()
            if (readback.canonical_bytes() != payload.locator.canonical_bytes()
                    or content_sha != payload.locator.locator_content_sha256):
                return CandidateIntakeRejectionCode.READBACK_MISMATCH
            return CandidateFinsValidationWitness(
                hashlib.sha256(payload.locator.canonical_bytes()).hexdigest(), content_sha, self._clock(),
            )
        except EvidenceLocatorError as exc:
            code = _BUSINESS_CODES.get(exc.code)
            if code is not None:
                return code
            raise ResearchDependencyError() from None
        except Exception:
            raise ResearchDependencyError() from None

    def ingest_candidate(
        self, scope: TenantScope, context: CandidateIntakeContext, raw_output: bytes,
    ) -> CandidateIntakeReceipt:
        """接入一次 proposal，历史首结果在任何 parser/Fins 调用前恢复。

        Args:
            scope: Principal 派生的可信租户。
            context: immutable caller 身份。
            raw_output: 原始 Agent bytes，不持久化。
        Returns:
            首次提交的不可变 receipt。
        Raises:
            ResearchContextError: scope/context/raw 非法或公司证券不存在。
            ResearchDependencyError: identity/Fins/clock 不可用，零写入。
            EvidenceRepositoryError: 原子持久化或 operation 冲突的安全错误。
        """
        if (type(scope) is not TenantScope or type(context) is not CandidateIntakeContext
                or type(raw_output) is not bytes):
            raise ResearchContextError()
        ticker = self._ticker(scope, context)
        raw_sha = hashlib.sha256(raw_output).hexdigest()
        try:
            fingerprint = intake_request_fingerprint(scope, context, ticker, raw_sha, len(raw_output))
        except (ValueError, TypeError):
            raise ResearchContextError() from None
        prior = self._intake.find_intake_receipt(scope, context.operation_id, fingerprint)
        if prior is not None:
            return prior
        payload: FactCandidatePayload | None = None
        witness: CandidateFinsValidationWitness | None = None
        rejection: CandidateIntakeRejectionCode | None = None
        try:
            payload = parse_fact_candidate(raw_output)
        except CandidateParseError as exc:
            rejection = exc.code
        if payload is not None:
            if payload.locator.ticker != ticker:
                rejection = CandidateIntakeRejectionCode.CROSS_TICKER
            else:
                observation = self._observe(payload)
                if isinstance(observation, CandidateIntakeRejectionCode):
                    rejection = observation
                else:
                    witness = observation
        return self._intake.record_intake(scope, CandidateIntakeRecordRequest(
            context, ticker, raw_sha, len(raw_output),
            payload if rejection is None else None, witness, rejection,
        ))
