"""单 READ COMMITTED 事务持久化 candidate 与不可变 intake 首结果。

五个精确命名23505键都先回滚整个SAVEPOINT，再按requested tenant+op读取
完整历史。SQL异常不包含参数；candidate状态变化不重写receipt原outcome。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID

from psycopg import Error as PsycopgError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from dayu.investment.domain.candidate_intake import (
    CANDIDATE_INTAKE_SCHEMA,
    CandidateFinsValidationWitness,
    CandidateIntakeContext,
    CandidateIntakeReceipt,
    CandidateIntakeRecordRequest,
    CandidateIntakeRejectionCode,
    intake_request_fingerprint,
)
from dayu.investment.domain.candidate_parsing import parse_fact_candidate
from dayu.investment.domain.evidence import CandidateOrigin, CandidateStatus, JsonValue, canonical_json_bytes
from dayu.investment.domain.identifiers import TenantId, TenantScope
from dayu.investment.storage.db import TENANT_CONTEXT_SETTING
from dayu.investment.storage.evidence_protocols import (
    EvidenceConflictError,
    EvidenceInputError,
    EvidenceRepositoryError,
)
from dayu.investment.storage.models_candidate_intake import CandidateIntakeReceiptRow
from dayu.investment.storage.models_evidence import ResearchCandidateRow

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_RETRY_KEYS = frozenset({
    "pk_research_candidates", "uq_research_candidates_tenant_company_id",
    "uq_research_candidates_operation", "pk_candidate_intake_receipts",
    "uq_candidate_intake_receipts_tenant_candidate",
})


def _tenant(scope: TenantScope) -> UUID:
    """核可信scope的canonical非nilUUID。

    Args:
        scope: Principal派生scope。
    Returns:
        明确租户UUID。
    Raises:
        EvidenceInputError: 类型/文本非法，尚未SQL。
    """
    if type(scope) is not TenantScope or type(scope.tenant_id) is not TenantId:
        raise EvidenceInputError()
    try:
        tenant = UUID(scope.tenant_id.value)
    except (TypeError, ValueError):
        raise EvidenceInputError() from None
    if tenant.int == 0 or str(tenant) != scope.tenant_id.value:
        raise EvidenceInputError()
    return tenant


def _time(value: datetime) -> datetime:
    """读取PG aware时刻并转UTC，不与宿主排序。

    Args:
        value: 数据库时刻。
    Returns:
        UTC datetime。
    Raises:
        EvidenceRepositoryError: 存储时刻无时区。
    """
    if type(value) is not datetime or value.utcoffset() is None:
        raise EvidenceRepositoryError()
    return value.astimezone(timezone.utc)


@contextmanager
def _transaction(factory: sessionmaker[Session], tenant: UUID) -> Iterator[Session]:
    """提供参数隐藏、租户readback和RC隔离的独占事务。

    Args:
        factory: hide_parameters Session工厂。
        tenant: 已核租户。
    Yields:
        当前事务Session。
    Raises:
        EvidenceRepositoryError: 参数隐藏/隔离/readback/SQL失败。
    """
    try:
        with factory() as session, session.begin():
            connection = session.connection()
            if connection.engine.hide_parameters is not True:
                raise EvidenceRepositoryError()
            assigned = session.execute(text(f"SELECT set_config('{TENANT_CONTEXT_SETTING}', :tenant, true)"),
                                       {"tenant": str(tenant)}).scalar_one()
            stored, isolation = session.execute(text(
                f"SELECT current_setting('{TENANT_CONTEXT_SETTING}', true), current_setting('transaction_isolation')"
            )).one()
            if assigned != str(tenant) or stored != str(tenant) or isolation != "read committed":
                raise EvidenceRepositoryError()
            yield session
    except EvidenceRepositoryError:
        raise
    except SQLAlchemyError:
        raise EvidenceRepositoryError() from None


def _receipt_row(session: Session, tenant: UUID, operation: UUID) -> CandidateIntakeReceiptRow | None:
    """每次用新RC SELECT按requested tenant+operation查询。

    Args:
        session: 非aborted事务。
        tenant: 请求租户。
        operation: 请求operation。
    Returns:
        完整receipt行或None。
    Raises:
        SQLAlchemyError: 由外层固定收束。
    """
    return session.scalar(select(CandidateIntakeReceiptRow).where(
        CandidateIntakeReceiptRow.tenant_id == tenant,
        CandidateIntakeReceiptRow.operation_id == operation,
    ))


def _project(session: Session, row: CandidateIntakeReceiptRow) -> CandidateIntakeReceipt:
    """先重核历史自闭合，不把损坏历史误归请求conflict。

    Args:
        session: 当前租户事务。
        row: 完整receipt行。
    Returns:
        历史immutable DTO。
    Raises:
        EvidenceRepositoryError: 身份/payload/schema/witness/digest损坏。
    """
    try:
        if row.schema_version != CANDIDATE_INTAKE_SCHEMA:
            raise EvidenceRepositoryError()
        context = CandidateIntakeContext(row.candidate_id, row.operation_id, row.company_id,
                                         row.security_id, CandidateOrigin(row.origin), row.extractor_version)
        witness: CandidateFinsValidationWitness | None = None
        if row.locator_sha256 is not None and row.citation_sha256 is not None and row.fins_checked_at is not None:
            witness = CandidateFinsValidationWitness(row.locator_sha256, row.citation_sha256, _time(row.fins_checked_at))
        elif any(v is not None for v in (row.locator_sha256, row.citation_sha256, row.fins_checked_at)):
            raise EvidenceRepositoryError()
        rejection = CandidateIntakeRejectionCode(row.rejection_code) if row.rejection_code is not None else None
        receipt = CandidateIntakeReceipt(row.tenant_id, context, row.security_ticker, row.raw_sha256,
            row.raw_bytes, row.request_fingerprint, row.payload_sha256, CandidateStatus(row.outcome),
            rejection, witness, _time(row.created_at))
        candidate = session.scalar(select(ResearchCandidateRow).where(
            ResearchCandidateRow.tenant_id == row.tenant_id,
            ResearchCandidateRow.company_id == row.company_id,
            ResearchCandidateRow.id == row.candidate_id,
        ))
        if candidate is None:
            raise EvidenceRepositoryError()
        if (candidate.operation_id != row.operation_id or candidate.origin != row.origin
                or candidate.operation_fingerprint != row.request_fingerprint):
            raise EvidenceRepositoryError()
        raw = canonical_json_bytes(candidate.canonical_payload_json)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row.payload_sha256 or digest != candidate.sha256:
            raise EvidenceRepositoryError()
        if rejection is None:
            payload = parse_fact_candidate(raw)
            if (witness is None or payload.canonical_bytes() != raw
                    or payload.locator.ticker != row.security_ticker
                    or hashlib.sha256(payload.locator.canonical_bytes()).hexdigest() != witness.locator_sha256
                    or payload.locator.locator_content_sha256 != witness.citation_sha256):
                raise EvidenceRepositoryError()
        elif raw != canonical_json_bytes({
            "schema_version": "rejected_intake.v1", "raw_sha256": row.raw_sha256,
            "raw_bytes": row.raw_bytes, "rejection_code": rejection.value,
        }):
            raise EvidenceRepositoryError()
        # state/version是可变head，不参与immutable初始outcome重建。
        return receipt
    except (TypeError, ValueError, OverflowError, RecursionError):
        # PG合法的损坏JSONB也可能在driver解码阶段超过Python递归界限。
        raise EvidenceRepositoryError() from None


def _same_request(prior: CandidateIntakeReceipt, request: CandidateIntakeRecordRequest, fingerprint: str) -> None:
    """比较完整不可变request字段，排除本次动态结果。

    Args:
        prior: 已自闭合的历史结果。
        request: 本次请求。
        fingerprint: 本次完整请求指纹。
    Returns:
        无。
    Raises:
        EvidenceConflictError: 完整请求身份不同。
    """
    if (prior.request_fingerprint != fingerprint or prior.context != request.context
            or prior.security_ticker != request.security_ticker or prior.raw_sha256 != request.raw_sha256
            or prior.raw_bytes != request.raw_bytes):
        raise EvidenceConflictError()


class PostgresCandidateIntakeRepository:
    """窄candidate+receipt仓储，不拥有Fins或authoritative证据写入。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """接收既有平台Session工厂。

        Args:
            session_factory: 明确app-role/hide_parameters工厂。
        Returns:
            无。
        Raises:
            无。
        """
        self._factory = session_factory

    def find_intake_receipt(
        self, scope: TenantScope, operation_id: UUID, request_fingerprint: str,
    ) -> CandidateIntakeReceipt | None:
        """恢复历史首结果；不重新访问Fins。

        Args:
            scope: 可信租户。
            operation_id: 请求operation。
            request_fingerprint: 完整request digest。
        Returns:
            历史receipt或None。
        Raises:
            EvidenceInputError: 输入非法。
            EvidenceConflictError: 同op异请求。
            EvidenceRepositoryError: SQL/历史不变量损坏。
        """
        tenant = _tenant(scope)
        if (type(operation_id) is not UUID or operation_id.int == 0
                or type(request_fingerprint) is not str or _HEX64.fullmatch(request_fingerprint) is None):
            raise EvidenceInputError()
        with _transaction(self._factory, tenant) as session:
            row = _receipt_row(session, tenant, operation_id)
            if row is None:
                return None
            receipt = _project(session, row)
            if receipt.request_fingerprint != request_fingerprint:
                raise EvidenceConflictError()
            return receipt

    def record_intake(self, scope: TenantScope, request: CandidateIntakeRecordRequest) -> CandidateIntakeReceipt:
        """一个SAVEPOINT内写两个结果，任何失败不留半个candidate。

        Args:
            scope: 可信租户。
            request: 完整typed结果。
        Returns:
            首次提交immutable结果。
        Raises:
            EvidenceInputError: 输入非法。
            EvidenceConflictError: 合法业务冲突。
            EvidenceRepositoryError: SQL/历史损坏。
        """
        tenant = _tenant(scope)
        if type(request) is not CandidateIntakeRecordRequest:
            raise EvidenceInputError()
        try:
            request.__post_init__()
            fingerprint = intake_request_fingerprint(scope, request.context, request.security_ticker,
                                                     request.raw_sha256, request.raw_bytes)
            raw = request.payload_bytes()
            payload: dict[str, JsonValue] = json.loads(raw)
        except (TypeError, ValueError, OverflowError):
            raise EvidenceInputError() from None
        with _transaction(self._factory, tenant) as session:
            prior_row = _receipt_row(session, tenant, request.context.operation_id)
            if prior_row is not None:
                prior = _project(session, prior_row)
                _same_request(prior, request, fingerprint)
                return prior
            witness = request.witness
            rejection = request.rejection_code
            outcome = CandidateStatus.PROPOSED if rejection is None else CandidateStatus.REJECTED
            try:
                with session.begin_nested():
                    candidate = ResearchCandidateRow(
                        id=request.context.candidate_id, tenant_id=tenant, company_id=request.context.company_id,
                        origin=request.context.origin.value, canonical_payload_json=payload,
                        sha256=hashlib.sha256(raw).hexdigest(), operation_id=request.context.operation_id,
                        operation_fingerprint=fingerprint, state=outcome.value, version=1,
                        rejection_code=rejection.value if rejection is not None else None,
                    )
                    session.add(candidate)
                    # 顺序明确：candidate先flush，receipt故障仍在同一个SAVEPOINT内回滚。
                    session.flush()
                    row = CandidateIntakeReceiptRow(
                        tenant_id=tenant, operation_id=request.context.operation_id,
                        company_id=request.context.company_id, security_id=request.context.security_id,
                        security_ticker=request.security_ticker, candidate_id=request.context.candidate_id,
                        origin=request.context.origin.value, extractor_version=request.context.extractor_version,
                        schema_version=CANDIDATE_INTAKE_SCHEMA, raw_sha256=request.raw_sha256,
                        raw_bytes=request.raw_bytes, request_fingerprint=fingerprint,
                        payload_sha256=candidate.sha256, outcome=outcome.value,
                        rejection_code=rejection.value if rejection is not None else None,
                        locator_sha256=witness.locator_sha256 if witness is not None else None,
                        citation_sha256=witness.citation_sha256 if witness is not None else None,
                        fins_checked_at=witness.checked_at if witness is not None else None,
                    )
                    session.add(row)
                    session.flush()
                    session.refresh(row)
                    session.refresh(candidate)
                    receipt = _project(session, row)
                    if canonical_json_bytes(candidate.canonical_payload_json) != raw:
                        raise EvidenceRepositoryError()
                    _same_request(receipt, request, fingerprint)
                    return receipt
            except IntegrityError as exc:
                origin = exc.orig
                if not isinstance(origin, PsycopgError) or origin.sqlstate != "23505":
                    raise EvidenceRepositoryError() from None
                if origin.diag.constraint_name not in _RETRY_KEYS:
                    raise EvidenceConflictError() from None
                # nested上下文已完整rollback；新的RC语句看首个committed receipt。
                recovered_row = _receipt_row(session, tenant, request.context.operation_id)
                if recovered_row is None:
                    raise EvidenceConflictError() from None
                recovered = _project(session, recovered_row)
                _same_request(recovered, request, fingerprint)
                return recovered
