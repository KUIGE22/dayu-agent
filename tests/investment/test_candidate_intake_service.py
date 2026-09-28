"""S32-A Service 的观察、固定码、历史重试与零写入边界。"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

import pytest

from dayu.fins.domain.document_models import FilingSummary
from dayu.fins.domain.evidence_locator import (
    CitationProjection,
    EvidenceLocatorError,
    EvidenceLocatorProjection,
    EvidenceLocatorRequest,
)
from dayu.fins.domain.source_sync import FinsWorkerSyncRequest, FinsWorkerSyncResult
from dayu.investment.domain.candidate_intake import (
    CandidateIntakeContext,
    CandidateIntakeReceipt,
    CandidateIntakeRecordRequest,
    CandidateIntakeRejectionCode,
    intake_request_fingerprint,
)
from dayu.investment.domain.evidence import CandidateOrigin, CandidateStatus, JsonValue, canonical_json_bytes
from dayu.investment.domain.identifiers import CompanyId, Principal, SecurityId, TenantId, TenantScope
from dayu.investment.domain.jobs import JobCancellationSignalProtocol
from dayu.investment.domain.source import (
    CompanyProjection,
    CompanySecurityRegistration,
    RegisteredCompanySecurity,
    SecurityProjection,
    SecurityType,
)
from dayu.investment.storage.candidate_intake_protocols import CandidateIntakeRepositoryProtocol
from dayu.investment.storage.evidence_protocols import EvidenceConflictError
from dayu.investment.storage.protocols import IdentityRepositoryProtocol
from dayu.services.contracts import FinsSubmission, FinsSubmitRequest
from dayu.services.investment_research import InvestmentResearchService, ResearchContextError, ResearchDependencyError
from dayu.services.protocols import FinsServiceProtocol
from tests.investment.test_candidate_parsing import proposal

_NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)
_CONTENT = b"canonical fragment"


class _Identity(IdentityRepositoryProtocol):
    """测试只提供明确 company/security 读取，不模拟真实数据库写入。"""

    def __init__(self, context: CandidateIntakeContext) -> None:
        """构造可控身份。

        Args:
            context: caller上下文。
        Returns:
            无。
        Raises:
            无。
        """
        self.company: CompanyProjection | None = CompanyProjection(
            CompanyId(str(context.company_id)), "Apple", None, "US", _NOW, _NOW, 1
        )
        self.security: SecurityProjection | None = SecurityProjection(
            SecurityId(str(context.security_id)),
            CompanyId(str(context.company_id)),
            "AAPL",
            "XNAS",
            SecurityType.EQUITY,
            "USD",
            None,
            True,
            _NOW,
            _NOW,
            1,
        )
        self.error: Exception | None = None

    def get_company(self, scope: TenantScope, company_id: CompanyId) -> CompanyProjection | None:
        """读取测试公司。

        Args:
            scope: 租户。
            company_id: 明确ID。
        Returns:
            测试投影。
        Raises:
            Exception: 注入错误。
        """
        if self.error is not None:
            raise self.error
        assert self.company is None or company_id == self.company.company_id
        return self.company

    def get_security(self, scope: TenantScope, security_id: SecurityId) -> SecurityProjection | None:
        """读取测试证券。

        Args:
            scope: 租户。
            security_id: 明确ID。
        Returns:
            测试投影。
        Raises:
            无。
        """
        assert self.security is None or security_id == self.security.security_id
        return self.security

    def register_company_security(
        self,
        scope: TenantScope,
        request: CompanySecurityRegistration,
    ) -> RegisteredCompanySecurity:
        """禁止接入Service擅自注册身份。

        Args:
            scope: 租户。
            request: 注册请求。
        Returns:
            不返回。
        Raises:
            AssertionError: 此测试链路不可调用。
        """
        raise AssertionError("intake cannot register identities")

    def find_security(self, scope: TenantScope, exchange_mic: str, ticker: str) -> SecurityProjection | None:
        """禁止接入Service猜ticker映射。

        Args:
            scope: 租户。
            exchange_mic: 交易所。
            ticker: 代码。
        Returns:
            不返回。
        Raises:
            AssertionError: 此测试链路不可调用。
        """
        raise AssertionError("intake requires explicit security id")


class _Intake(CandidateIntakeRepositoryProtocol):
    """只证明Service边界；原子/并发/FK/RLS由真PG integration负责。"""

    def __init__(self) -> None:
        """初始化测试历史。

        Args:
            无。
        Returns:
            无。
        Raises:
            无。
        """
        self.history: dict[UUID, CandidateIntakeReceipt] = {}
        self.records: list[CandidateIntakeRecordRequest] = []

    def find_intake_receipt(
        self, scope: TenantScope, operation_id: UUID, request_fingerprint: str
    ) -> CandidateIntakeReceipt | None:
        """模拟首结果lookup。

        Args:
            scope: 租户。
            operation_id: 请求op。
            request_fingerprint: 完整请求digest。
        Returns:
            原结果或None。
        Raises:
            EvidenceConflictError: 同op异请求。
        """
        prior = self.history.get(operation_id)
        if prior is not None and prior.request_fingerprint != request_fingerprint:
            raise EvidenceConflictError()
        return prior

    def record_intake(self, scope: TenantScope, request: CandidateIntakeRecordRequest) -> CandidateIntakeReceipt:
        """保存单元测试观察结果。

        Args:
            scope: 租户。
            request: typed请求。
        Returns:
            immutable测试receipt。
        Raises:
            无。
        """
        self.records.append(request)
        receipt = CandidateIntakeReceipt(
            UUID(scope.tenant_id.value),
            request.context,
            request.security_ticker,
            request.raw_sha256,
            request.raw_bytes,
            intake_request_fingerprint(
                scope, request.context, request.security_ticker, request.raw_sha256, request.raw_bytes
            ),
            hashlib.sha256(request.payload_bytes()).hexdigest(),
            CandidateStatus.PROPOSED if request.rejection_code is None else CandidateStatus.REJECTED,
            request.rejection_code,
            request.witness,
            _NOW,
        )
        self.history[request.context.operation_id] = receipt
        return receipt


class _Fins(FinsServiceProtocol):
    """当前公共validate/readback的可控替身，不读取私有owner。"""

    def __init__(self) -> None:
        """初始化观察计数。

        Args:
            无。
        Returns:
            无。
        Raises:
            无。
        """
        self.validated = 0
        self.reads = 0
        self.error: BaseException | None = None
        self.read_error: BaseException | None = None
        self.content = _CONTENT
        self.changed_locator = False
        self.invalid_result = False

    def submit(self, request: FinsSubmitRequest) -> FinsSubmission:
        """禁止接入行为调度Agent命令。

        Args:
            request: Fins命令。
        Returns:
            不返回。
        Raises:
            AssertionError: 此链路不可调用。
        """
        raise AssertionError("intake cannot submit fins jobs")

    async def sync_worker_source(
        self,
        request: FinsWorkerSyncRequest,
        cancellation: JobCancellationSignalProtocol,
    ) -> FinsWorkerSyncResult:
        """禁止接入行为同步外部source。

        Args:
            request: source请求。
            cancellation: 取消信号。
        Returns:
            不返回。
        Raises:
            AssertionError: 此链路不可调用。
        """
        raise AssertionError("intake cannot sync sources")

    def list_filings(self, ticker: str) -> list[FilingSummary]:
        """禁止接入行为搜索source。

        Args:
            ticker: 代码。
        Returns:
            不返回。
        Raises:
            AssertionError: 此链路不可调用。
        """
        raise AssertionError("intake cannot discover sources")

    def resolve_evidence_locator(self, request: EvidenceLocatorRequest) -> EvidenceLocatorProjection:
        """禁止接入行为补locator身份或片段。

        Args:
            request: locator请求。
        Returns:
            不返回。
        Raises:
            AssertionError: 此链路不可调用。
        """
        raise AssertionError("intake requires a complete locator")

    def validate_evidence_locator(self, locator: EvidenceLocatorProjection) -> None:
        """模拟validation及固定码错误。

        Args:
            locator: 完整locator。
        Returns:
            无。
        Raises:
            BaseException: 注入错误/取消。
        """
        self.validated += 1
        if self.error is not None:
            raise self.error

    def read_citation_projection(self, locator: EvidenceLocatorProjection) -> CitationProjection:
        """返回完整citation或注入readback漂移。

        Args:
            locator: 完整locator。
        Returns:
            可控citation。
        Raises:
            BaseException: 注入读错误。
        """
        self.reads += 1
        if self.read_error is not None:
            raise self.read_error
        if self.invalid_result:
            return cast(CitationProjection, None)
        if self.changed_locator:
            locator = replace(locator, document_version="v2")
        return CitationProjection(locator, "text/plain", self.content)


def _context() -> CandidateIntakeContext:
    """生成完整caller上下文。

    Args:
        无。
    Returns:
        新上下文。
    Raises:
        无。
    """
    return CandidateIntakeContext(uuid4(), uuid4(), uuid4(), uuid4(), CandidateOrigin.AGENT, "v1")


def _raw(ticker: str = "AAPL") -> bytes:
    """生成与canonical fragment匹配的输入。

    Args:
        ticker: 显式locator ticker。
    Returns:
        九键JSON。
    Raises:
        无。
    """
    value = proposal()
    locator = cast(dict[str, JsonValue], value["locator"])
    locator["locator_content_sha256"] = hashlib.sha256(_CONTENT).hexdigest()
    locator["ticker"] = ticker
    return canonical_json_bytes(value)


def test_success_and_retry_recover_original_before_fins() -> None:
    """source随后不可用、时钟随后不同仍恢复历史首结果。

    Args:
        无。
    Returns:
        无。
    Raises:
        无。
    """
    context = _context()
    scope = Principal(TenantId(str(uuid4())), "caller").to_scope()
    intake = _Intake()
    fins = _Fins()
    service = InvestmentResearchService(_Identity(context), intake, fins, lambda: _NOW)
    first = service.ingest_candidate(scope, context, _raw())
    assert first.outcome is CandidateStatus.PROPOSED and first.witness is not None
    assert first.witness.citation_sha256 == hashlib.sha256(_CONTENT).hexdigest()
    assert first.witness.checked_at == _NOW
    assert first.payload_sha256 == hashlib.sha256(intake.records[0].payload_bytes()).hexdigest()
    fins.error = OSError("sensitive source path")
    assert service.ingest_candidate(scope, context, _raw()) is first
    assert len(intake.records) == 1 and fins.validated == fins.reads == 1
    for changed in (
        replace(context, candidate_id=uuid4()),
        replace(context, origin=CandidateOrigin.HUMAN),
        replace(context, extractor_version="v2"),
    ):
        with pytest.raises(EvidenceConflictError):
            service.ingest_candidate(scope, changed, _raw())
    with pytest.raises(EvidenceConflictError):
        service.ingest_candidate(scope, context, b"different raw")
    assert len(intake.records) == 1


@pytest.mark.parametrize(
    "raw,code",
    [
        (b"sensitive malformed", CandidateIntakeRejectionCode.JSON_INVALID),
        (b'{"candidate_type":"claim"}', CandidateIntakeRejectionCode.MATERIAL_CLAIM_UNSUPPORTED),
        (_raw("MSFT"), CandidateIntakeRejectionCode.CROSS_TICKER),
        (canonical_json_bytes({**proposal(), "locator": None}), CandidateIntakeRejectionCode.EVIDENCE_MISSING),
    ],
)
def test_business_parser_reject_is_single_safe_record_without_fins(
    raw: bytes, code: CandidateIntakeRejectionCode
) -> None:
    """业务拒绝用四键envelope且不调用Fins。

    Args:
        raw: 原始输出。
        code: 预期原因。
    Returns:
        无。
    Raises:
        无。
    """
    context = _context()
    scope = Principal(TenantId(str(uuid4())), "caller").to_scope()
    intake = _Intake()
    fins = _Fins()
    service = InvestmentResearchService(_Identity(context), intake, fins)
    result = service.ingest_candidate(scope, context, raw)
    assert result.outcome is CandidateStatus.REJECTED and result.rejection_code is code and result.witness is None
    assert len(intake.records) == 1 and fins.validated == fins.reads == 0
    assert b"sensitive" not in intake.records[0].payload_bytes()
    assert service.ingest_candidate(scope, context, raw) is result and len(intake.records) == 1


@pytest.mark.parametrize(
    "code,expected",
    [
        *(
            (c, CandidateIntakeRejectionCode.UNAVAILABLE)
            for c in (
                "source_identity_not_found",
                "source_deleted",
                "source_not_ingested",
                "processed_not_found",
                "processed_deleted",
                "processed_reprocess_required",
            )
        ),
        ("ambiguous_source_identity", CandidateIntakeRejectionCode.AMBIGUOUS_OWNER),
        *(
            (c, CandidateIntakeRejectionCode.STALE)
            for c in (
                "document_version_mismatch",
                "source_fingerprint_mismatch",
                "processed_source_kind_mismatch",
                "processed_version_mismatch",
                "processed_fingerprint_mismatch",
                "source_identity_changed",
                "primary_content_changed",
                "primary_sha_mismatch",
                "primary_content_sha256_mismatch",
                "locator_content_sha256_mismatch",
            )
        ),
        *(
            (c, CandidateIntakeRejectionCode.FRAGMENT_UNRESOLVED)
            for c in ("table_row_out_of_range", "table_column_missing", "page_not_supported", "xbrl_fact_not_unique")
        ),
    ],
)
@pytest.mark.parametrize("phase", ["validate", "read"])
def test_each_fins_business_code_is_closed_at_both_phases(
    code: str, expected: CandidateIntakeRejectionCode, phase: str
) -> None:
    """每个code都直接参数化，不从message猜匹配数或归因。

    Args:
        code: 当前Fins固定码。
        expected: 业务原因。
        phase: validation/readback。
    Returns:
        无。
    Raises:
        无。
    """
    context = _context()
    scope = Principal(TenantId(str(uuid4())), "caller").to_scope()
    intake = _Intake()
    fins = _Fins()
    failure = EvidenceLocatorError(code, "sensitive owner/path payload")
    if phase == "validate":
        fins.error = failure
    else:
        fins.read_error = failure
    result = InvestmentResearchService(_Identity(context), intake, fins).ingest_candidate(scope, context, _raw())
    assert result.outcome is CandidateStatus.REJECTED and result.rejection_code is expected
    assert len(intake.records) == 1 and b"sensitive" not in intake.records[0].payload_bytes()


@pytest.mark.parametrize(
    "code",
    [
        "table_not_records",
        "xbrl_facts_unavailable",
        "invalid_locator_payload",
        "artifact_kind_not_supported",
        "primary_read_failed",
        "evidence_read_failed",
        "invalid_document_version",
        "invalid_source_fingerprint",
        "unknown_future_code",
    ],
)
@pytest.mark.parametrize("phase", ["validate", "read"])
def test_owner_infrastructure_codes_have_zero_records(code: str, phase: str) -> None:
    """owner数据/版本/unknown不可用不写业务拒绝。

    Args:
        code: Fins错误码。
        phase: 抛出阶段。
    Returns:
        无。
    Raises:
        无。
    """
    context = _context()
    scope = Principal(TenantId(str(uuid4())), "caller").to_scope()
    intake = _Intake()
    fins = _Fins()
    failure = EvidenceLocatorError(code, "secret")
    if phase == "validate":
        fins.error = failure
    else:
        fins.read_error = failure
    with pytest.raises(ResearchDependencyError, match="^research_dependency_unavailable$") as exc:
        InvestmentResearchService(_Identity(context), intake, fins).ingest_candidate(scope, context, _raw())
    assert intake.records == [] and exc.value.__cause__ is None


@pytest.mark.parametrize("change", ["bytes", "locator", "invalid_return", "naive_clock", "identity", "io", "timeout"])
def test_readback_and_dependency_failures_do_not_forge_witness(change: str) -> None:
    """完整locator/bytes漂移为业务拒绝，invalidreturn/clock/IO为零写。

    Args:
        change: 故障种类。
    Returns:
        无。
    Raises:
        无。
    """
    context = _context()
    scope = Principal(TenantId(str(uuid4())), "caller").to_scope()
    identity = _Identity(context)
    intake = _Intake()
    fins = _Fins()
    if change == "bytes":
        fins.content = b"changed"
    elif change == "locator":
        fins.changed_locator = True
    elif change == "invalid_return":
        fins.invalid_result = True
    elif change == "identity":
        identity.error = RuntimeError("sensitive storage")
    elif change == "io":
        fins.error = OSError("secret")
    elif change == "timeout":
        fins.read_error = TimeoutError("secret")
    clock = (lambda: _NOW.replace(tzinfo=None)) if change == "naive_clock" else (lambda: _NOW)
    service = InvestmentResearchService(identity, intake, fins, clock)
    if change in ("bytes", "locator"):
        result = service.ingest_candidate(scope, context, _raw())
        assert result.rejection_code is CandidateIntakeRejectionCode.READBACK_MISMATCH and result.witness is None
    else:
        with pytest.raises(ResearchDependencyError):
            service.ingest_candidate(scope, context, _raw())
        assert intake.records == []


def test_invalid_context_and_cancel_never_persist() -> None:
    """context非法与BaseException取消均无候选；取消保持原语义。

    Args:
        无。
    Returns:
        无。
    Raises:
        无。
    """
    context = _context()
    scope = Principal(TenantId(str(uuid4())), "caller").to_scope()
    identity = _Identity(context)
    intake = _Intake()
    fins = _Fins()
    service = InvestmentResearchService(identity, intake, fins)
    identity.company = None
    with pytest.raises(ResearchContextError):
        service.ingest_candidate(scope, context, _raw())
    identity = _Identity(context)
    assert identity.security is not None
    identity.security = replace(identity.security, company_id=CompanyId(str(uuid4())))
    with pytest.raises(ResearchContextError):
        InvestmentResearchService(identity, intake, fins).ingest_candidate(scope, context, _raw())
    for raw in (cast(bytes, "{}"), cast(bytes, bytearray(b"{}"))):
        with pytest.raises(ResearchContextError):
            service.ingest_candidate(scope, context, raw)
    fins.error = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        InvestmentResearchService(_Identity(context), intake, fins).ingest_candidate(scope, context, _raw())
    assert intake.records == []
