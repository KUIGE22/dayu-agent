"""严格证据的 PostgreSQL 仓储；每个入口独占 READ COMMITTED 事务。"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Iterator, NoReturn, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg import Error as PsycopgError
from sqlalchemy import null, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from dayu.investment.domain.evidence import (
    AuthorAuthWitness,
    CandidateOrigin,
    CandidateStatus,
    ClaimConflict,
    ClaimConflictOpenRequest,
    ClaimConflictResolveRequest,
    ClaimContent,
    ClaimCreateRequest,
    ClaimLocalEligibility,
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
    LocalEligibilityReason,
    ResearchCandidate,
    ResearchCandidateCreateRequest,
    ReviewWitness,
    VerificationStatus,
    canonical_json_bytes,
    canonical_json_document,
    canonical_sha256,
    copied_link_id,
    evidence_fingerprint_frame,
    local_eligibility_reason,
    validate_append_transition,
    validate_begin_transition,
    validate_conflict_resolution_transition,
    validate_review_transition,
)
from dayu.investment.domain.identifiers import TenantId, TenantScope
from dayu.investment.storage._evidence_review_auth import (
    REVIEW_PERMISSION_KEY,
    ActorAuthWitness,
    EvidenceReviewStorageError,
    EvidenceReviewUnauthorizedError,
    EvidenceReviewUsageError,
    ReviewerAuthWitness,
    authorize_active_actor,
    authorize_reviewer,
)
from dayu.investment.storage.db import TENANT_CONTEXT_SETTING
from dayu.investment.storage.evidence_protocols import (
    EvidenceConflictError,
    EvidenceDigestCollisionError,
    EvidenceDuplicateTargetError,
    EvidenceInputError,
    EvidenceMaterializationNeededError,
    EvidenceNotFoundError,
    EvidenceOptimisticConflictError,
    EvidenceRepositoryError,
    EvidenceUnauthorizedError,
)
from dayu.investment.storage.models_evidence import (
    ClaimConflictRow,
    ClaimRow,
    ClaimVersionRow,
    EvidenceLinkRow,
    FactRow,
    ResearchCandidateRow,
)

_JsonValue: TypeAlias = str | int | float | bool | None | list["_JsonValue"] | dict[str, "_JsonValue"]
_FrameInput: TypeAlias = (
    _JsonValue | UUID | Enum | Decimal | datetime | date | bytes |
    EvidenceLocatorSnapshot | FactCreateRequest | ClaimCreateRequest |
    ClaimVersionAppendRequest | ClaimRevisionBeginRequest | ClaimReviewRequest |
    ClaimConflictOpenRequest | ClaimConflictResolveRequest |
    ResearchCandidateCreateRequest
)
_EXPIRY_NAMESPACE = "dayu:claim-expiry:v1:"
_READ_COMMITTED = "read committed"
_DIRECT_DIGEST_INDEX = "uq_evidence_links_direct_digest"


def _tenant(scope: TenantScope) -> UUID:
    """读取规范租户提示。

    Args:
        scope: 进程内租户范围。
    Returns:
        非 nil 的规范 UUID。
    Raises:
        EvidenceInputError: 范围形态不符。
    """

    if type(scope) is not TenantScope or type(scope.tenant_id) is not TenantId:
        raise EvidenceInputError()
    raw = scope.tenant_id.value
    try:
        parsed = UUID(raw)
    except (TypeError, ValueError):
        raise EvidenceInputError() from None
    if parsed.int == 0 or str(parsed) != raw:
        raise EvidenceInputError()
    return parsed


def _id(value: UUID) -> UUID:
    """核 caller UUID。

    Args:
        value: 待核标识。
    Returns:
        非 nil UUID。
    Raises:
        EvidenceInputError: 标识无效。
    """

    if type(value) is not UUID or value.int == 0:
        raise EvidenceInputError()
    return value


def _utc(value: datetime) -> datetime:
    """将 PG aware 时刻归一为 UTC。

    Args:
        value: PG 时刻。
    Returns:
        UTC aware 时刻。
    Raises:
        EvidenceRepositoryError: 数据库时刻不闭合。
    """

    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceRepositoryError()
    return value.astimezone(timezone.utc)


def _required_uuid(value: UUID | None) -> UUID:
    """核可空 witness UUID 必须存在。

    Args:
        value: 可空 ORM 字段。
    Returns:
        非 nil UUID。
    Raises:
        EvidenceRepositoryError: 字段缺失。
    """

    if value is None or value.int == 0:
        raise EvidenceRepositoryError()
    return value


def _required_text(value: str | None) -> str:
    """核可空 witness 文本必须存在。

    Args:
        value: 可空 ORM 字段。
    Returns:
        非空文本。
    Raises:
        EvidenceRepositoryError: 字段缺失。
    """

    if value is None or not value:
        raise EvidenceRepositoryError()
    return value


def _required_time(value: datetime | None) -> datetime:
    """核可空 witness 时刻必须存在且为 UTC aware。

    Args:
        value: 可空 ORM 字段。
    Returns:
        UTC aware 时刻。
    Raises:
        EvidenceRepositoryError: 字段缺失或无时区。
    """

    if value is None:
        raise EvidenceRepositoryError()
    return _utc(value)


def _json(value: _FrameInput) -> _JsonValue:
    """把 DTO 字段递归归一为稳定 JSON 指纹字段。

    Args:
        value: 领域值。
    Returns:
        无 secret 的 JSON 值。
    Raises:
        EvidenceInputError: 输入不能安全编码。
    """

    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, EvidenceLocatorSnapshot):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_json(item) for item in value]
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return _json(asdict(value))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise EvidenceInputError()


def _fingerprint(kind: str, tenant_id: UUID, request: _FrameInput, *,
                 evidence: dict[str, _JsonValue] | None = None,
                 actor_id: UUID | None = None,
                 permission_key: str | None = None) -> str:
    """计算包含动作、租户和完整证据目标的指纹。

    Args:
        kind: 稳定动作名称。
        tenant_id: token 或 scope 派生的租户。
        request: 无凭据请求字段。
        evidence: 完整 replace/copy frame。
        actor_id: token 派生主体。
        permission_key: reviewer 动作所需的显式权限键。
    Returns:
        SHA-256 hex。
    Raises:
        EvidenceInputError: frame 不能 canonical 化。
    """

    request_json = _json(request)
    if evidence is not None:
        if not isinstance(request_json, dict):
            raise EvidenceInputError()
        # 完整证据只由排序后的 replace/copy frame 表示，caller tuple 顺序无语义。
        request_json.pop("evidence", None)
    frame: dict[str, _JsonValue] = {"kind": kind, "tenant_id": str(tenant_id),
                                    "request": request_json}
    if evidence is not None:
        frame["evidence"] = evidence
    if actor_id is not None:
        frame["actor_user_id"] = str(actor_id)
    if permission_key is not None:
        frame["permission_key"] = permission_key
    try:
        return canonical_sha256(frame)
    except (TypeError, ValueError):
        raise EvidenceInputError() from None


def _set_local(session: Session, tenant_id: UUID) -> None:
    """同一事务 SET LOCAL 并读回租户及隔离级别。

    Args:
        session: 已开启事务的 Session。
        tenant_id: 已核租户。
    Returns:
        无。
    Raises:
        EvidenceRepositoryError: 参数保护、readback 或隔离失败。
    """

    connection = session.connection()
    if connection.engine.hide_parameters is not True:
        raise EvidenceRepositoryError()
    assigned = connection.execute(text(f"SELECT set_config('{TENANT_CONTEXT_SETTING}', :tenant, true)"),
                                  {"tenant": str(tenant_id)}).scalar_one()
    tenant_read, isolation = connection.execute(text(
        f"SELECT current_setting('{TENANT_CONTEXT_SETTING}', true), "
        "current_setting('transaction_isolation')"
    )).one()
    if assigned != str(tenant_id) or tenant_read != str(tenant_id) or isolation != _READ_COMMITTED:
        raise EvidenceRepositoryError()


@contextmanager
def _session(factory: sessionmaker[Session], tenant_id: UUID, *, auth: bool = False) -> Iterator[Session]:
    """为一个 repository 方法提供独占事务和脱敏错误收束。

    Args:
        factory: hide_parameters 的 Session 工厂。
        tenant_id: 规范租户。
        auth: 认证入口自行完成 SET LOCAL。
    Yields:
        活跃 READ COMMITTED Session。
    Raises:
        EvidenceRepositoryError: 数据库故障。
    """

    try:
        with factory() as session, session.begin():
            if not auth:
                _set_local(session, tenant_id)
            yield session
    except EvidenceRepositoryError:
        raise
    except (EvidenceReviewUnauthorizedError,):
        raise EvidenceUnauthorizedError() from None
    except IntegrityError:
        raise
    except (EvidenceReviewStorageError, EvidenceReviewUsageError, SQLAlchemyError):
        raise EvidenceRepositoryError() from None


def _clock(session: Session) -> datetime:
    """取同事务 PG statement clock。

    Args:
        session: 当前 Session。
    Returns:
        UTC 时刻。
    Raises:
        EvidenceRepositoryError: 读回无效。
    """

    return _utc(session.execute(text("SELECT statement_timestamp()")).scalar_one())


def _locator(raw: dict[str, _JsonValue]) -> EvidenceLocatorSnapshot:
    """对 JSONB 中的完整 locator 重做领域 canonical 校验。

    Args:
        raw: PG JSONB 对象。
    Returns:
        结构镜像。
    Raises:
        EvidenceRepositoryError: 持久结构漂移。
    """

    try:
        return EvidenceLocatorSnapshot.from_json_bytes(canonical_json_bytes(raw))
    except (TypeError, ValueError):
        raise EvidenceRepositoryError() from None


def _fact(row: FactRow) -> Fact:
    """重建不可变 Fact DTO 并校验 locator 与值。

    Args:
        row: scoped ORM 行。
    Returns:
        已核 Fact。
    Raises:
        EvidenceRepositoryError: 行结构或指纹漂移。
    """

    try:
        locator = _locator(row.locator_json)
        if locator.ticker != row.locator_ticker:
            raise EvidenceRepositoryError()
        value = FactValue(kind=FactValueKind(row.value_kind), value_decimal=row.value_decimal,
                          value_text=row.value_text, value_date=row.value_date,
                          value_boolean=row.value_boolean, unit_code=row.unit_code,
                          currency=row.currency)
        request = FactCreateRequest(
            id=row.id, company_id=row.company_id, security_id=row.security_id,
            fact_series_id=row.fact_series_id, revision_no=row.revision_no,
            prior_fact_id=row.prior_fact_id, fact_key=row.fact_key, metric=row.metric,
            locator=locator, value=value,
            pit=FactPitTimes(row.period_start, row.period_end, _utc(row.effective_at),
                             _utc(row.published_at), _utc(row.ingested_at), _utc(row.available_at)),
            extractor_version=row.extractor_version,
            verification_status=VerificationStatus(row.verification_status),
            verifier_user_id=row.verifier_user_id,
            verified_at=_utc(row.verified_at) if row.verified_at is not None else None,
            operation_id=row.operation_id,
        )
        return Fact(row.id, row.tenant_id, request, row.operation_fingerprint, _utc(row.created_at))
    except (TypeError, ValueError):
        raise EvidenceRepositoryError() from None


def _fact_row(tenant_id: UUID, request: FactCreateRequest, fingerprint: str) -> FactRow:
    """构造一条不可变 Fact revision ORM 行。

    Args:
        tenant_id: scoped 租户。
        request: 已核请求。
        fingerprint: 完整操作指纹。
    Returns:
        待插入行。
    Raises:
        无。
    """

    value, pit = request.value, request.pit
    return FactRow(
        id=request.id, tenant_id=tenant_id, company_id=request.company_id,
        security_id=request.security_id, locator_ticker=request.locator_ticker,
        locator_json=request.locator.to_dict(), fact_series_id=request.fact_series_id,
        revision_no=request.revision_no, prior_fact_id=request.prior_fact_id,
        fact_key=request.fact_key, metric=request.metric, value_kind=value.kind.value,
        value_decimal=value.value_decimal, value_text=value.value_text,
        value_date=value.value_date, value_boolean=value.value_boolean,
        unit_code=value.unit_code, currency=value.currency,
        period_start=pit.period_start, period_end=pit.period_end,
        effective_at=pit.effective_at, published_at=pit.published_at,
        ingested_at=pit.ingested_at, available_at=pit.available_at,
        extractor_version=request.extractor_version,
        verification_status=request.verification_status.value,
        verifier_user_id=request.verifier_user_id, verified_at=request.verified_at,
        operation_id=request.operation_id, operation_fingerprint=fingerprint,
    )


def _version(row: ClaimVersionRow) -> ClaimVersion:
    """重建带作者或 reviewer witness 的 immutable 版本。

    Args:
        row: scoped 版本行。
    Returns:
        领域版本。
    Raises:
        EvidenceRepositoryError: 行字段不闭合。
    """

    try:
        author = None
        if row.author_auth_token_id is not None:
            author = AuthorAuthWitness(row.author_auth_token_id, _required_time(row.author_auth_checked_at),
                                       _required_text(row.author_auth_policy))
        reviewer = None
        if row.reviewer_user_id is not None:
            reviewer = ReviewWitness(
                row.reviewer_user_id, _required_uuid(row.reviewer_token_id),
                _required_uuid(row.reviewer_user_role_id),
                _required_uuid(row.reviewer_role_permission_id),
                _required_uuid(row.reviewer_permission_id),
                _required_text(row.reviewer_permission_key),
                _required_time(row.reviewer_checked_at),
                _required_text(row.reviewer_policy), _required_text(row.reviewer_reason),
            )
        return ClaimVersion(
            id=row.id, tenant_id=row.tenant_id, company_id=row.company_id,
            claim_id=row.claim_id, version_no=row.version_no,
            transition_kind=ClaimTransitionKind(row.transition_kind),
            evidence_mode=EvidenceMode(row.evidence_mode),
            copy_source_version_id=row.copy_source_version_id,
            operation_id=row.operation_id, operation_fingerprint=row.operation_fingerprint,
            content=ClaimContent(row.statement, ConfidenceBand(row.confidence_band),
                                 row.probability, ImpactHorizon(row.impact_horizon),
                                 _utc(row.valid_until) if row.valid_until is not None else None,
                                 ClaimStatus(row.status), row.invalidation_rule),
            author_user_id=row.author_user_id, author_auth=author, reviewer=reviewer,
            created_at=_utc(row.created_at),
        )
    except (TypeError, ValueError):
        raise EvidenceRepositoryError() from None


def _link(row: EvidenceLinkRow) -> EvidenceLink:
    """重建 link，核 full locator 与 digest arm。

    Args:
        row: scoped 链接行。
    Returns:
        领域链接。
    Raises:
        EvidenceRepositoryError: 链接 target 漂移。
    """

    try:
        locator = _locator(row.locator_json) if row.locator_json is not None else None
        if locator is not None and locator.ticker != row.locator_ticker:
            raise EvidenceRepositoryError()
        request = EvidenceLinkRequest(row.id, EvidenceRelation(row.relation), row.fact_id,
                                      row.security_id, locator)
        return EvidenceLink(row.tenant_id, row.company_id, row.claim_version_id,
                            request, row.locator_index_digest, _utc(row.created_at))
    except (TypeError, ValueError):
        raise EvidenceRepositoryError() from None


def _links(session: Session, tenant_id: UUID, company_id: UUID,
           version_id: UUID) -> tuple[EvidenceLink, ...]:
    """读取并校验 immutable 版本的完整 link 集合。

    Args:
        session: 当前事务。
        tenant_id: scoped 租户。
        company_id: scoped 公司。
        version_id: immutable 版本。
    Returns:
        按 ID 排序的全部链接。
    Raises:
        EvidenceRepositoryError: 持久链接不闭合。
    """

    rows = session.scalars(select(EvidenceLinkRow).where(
        EvidenceLinkRow.tenant_id == tenant_id,
        EvidenceLinkRow.company_id == company_id,
        EvidenceLinkRow.claim_version_id == version_id,
    ).order_by(EvidenceLinkRow.id)).all()
    return tuple(_link(row) for row in rows)


def _link_key(link: EvidenceLinkRequest) -> tuple[str, str, str, str, str]:
    """用完整 locator 与 link ID 比较不可哈希的链接 DTO。

    Args:
        link: 领域链接请求。
    Returns:
        relation、target kind、target ID、完整 locator、link ID。
    Raises:
        无。
    """

    return (link.relation.value, *link.target_identity(), str(link.id))


def _same_links(actual: tuple[EvidenceLink, ...],
                expected: tuple[EvidenceLinkRequest, ...]) -> bool:
    """按完整 target identity 和 link ID 核等价集合。

    Args:
        actual: 已持久化链接。
        expected: 本次重算链接。
    Returns:
        身份全集相同则真。
    Raises:
        无。
    """

    return tuple(sorted(_link_key(link.request) for link in actual)) == tuple(
        sorted(_link_key(link) for link in expected))


def _historical_snapshot(session: Session, shell: ClaimRow,
                         version: ClaimVersionRow) -> ClaimSnapshot:
    """返回已提交操作自己的 immutable 版本而不冒充新 head。

    Args:
        session: 当前事务。
        shell: lineage shell。
        version: 已提交 immutable 版本。
    Returns:
        该版本及其原完整链接投影。
    Raises:
        EvidenceRepositoryError: tenant/company/claim 漂移。
    """

    if (shell.tenant_id != version.tenant_id or shell.company_id != version.company_id
            or shell.id != version.claim_id):
        raise EvidenceRepositoryError()
    return ClaimSnapshot(shell.id, shell.tenant_id, shell.company_id,
                         version.version_no, _utc(shell.created_at),
                         _utc(version.created_at), _version(version),
                         _links(session, shell.tenant_id, shell.company_id, version.id))


def _snapshot(session: Session, row: ClaimRow) -> ClaimSnapshot:
    """以 shell 当前版号读取唯一 immutable head 和完整 links。

    Args:
        session: 当前事务。
        row: 已 scoped shell。
    Returns:
        闭合 Claim 快照。
    Raises:
        EvidenceRepositoryError: head 缺失或漂移。
    """

    versions = session.scalars(select(ClaimVersionRow).where(
        ClaimVersionRow.tenant_id == row.tenant_id,
        ClaimVersionRow.company_id == row.company_id,
        ClaimVersionRow.claim_id == row.id,
        ClaimVersionRow.version_no == row.version,
    )).all()
    if len(versions) != 1:
        raise EvidenceRepositoryError()
    version = _version(versions[0])
    return ClaimSnapshot(row.id, row.tenant_id, row.company_id, row.version,
                         _utc(row.created_at), _utc(row.updated_at), version,
                         _links(session, row.tenant_id, row.company_id, version.id))


def _claim(session: Session, tenant_id: UUID, claim_id: UUID, *, lock: bool) -> ClaimRow | None:
    """在 tenant predicate 下读取或锁定 Claim shell。

    Args:
        session: 当前事务。
        tenant_id: scoped 租户。
        claim_id: Claim ID。
        lock: 是否持有行锁到提交。
    Returns:
        shell 或空。
    Raises:
        无。
    """

    query = select(ClaimRow).where(ClaimRow.tenant_id == tenant_id, ClaimRow.id == claim_id)
    if lock:
        query = query.with_for_update()
    return session.scalar(query)


def _version_row(tenant_id: UUID, company_id: UUID, claim_id: UUID,
                 version_no: int, version_id: UUID, kind: ClaimTransitionKind,
                 content: ClaimContent, selection: EvidenceSelection,
                 source_id: UUID | None, operation_id: UUID, fingerprint: str,
                 author_user_id: UUID | None, reason: str | None,
                 actor: ActorAuthWitness | None,
                 reviewer: ReviewerAuthWitness | None) -> ClaimVersionRow:
    """映射动作、copy source 与 token 派生见证到版本列。

    Args:
        tenant_id: scoped 租户。
        company_id: scoped 公司。
        claim_id: lineage ID。
        version_no: successor 版号。
        version_id: successor ID。
        kind: 动作分类。
        content: 新内容。
        selection: 完整证据模式。
        source_id: copy 的首次 expected_version ID。
        operation_id: caller 操作 ID。
        fingerprint: canonical 指纹。
        author_user_id: 普通作者或 token-derived 作者。
        reason: 动作原因。
        actor: active bearer 见证。
        reviewer: reviewer grant 见证。
    Returns:
        待插入 immutable 行。
    Raises:
        无。
    """

    row = ClaimVersionRow(
        id=version_id, tenant_id=tenant_id, company_id=company_id,
        claim_id=claim_id, version_no=version_no, transition_kind=kind.value,
        evidence_mode=selection.mode.value, copy_source_version_id=source_id,
        operation_id=operation_id, operation_fingerprint=fingerprint,
        statement=content.statement, confidence_band=content.confidence_band.value,
        probability=content.probability, impact_horizon=content.impact_horizon.value,
        valid_until=content.valid_until, status=content.status.value,
        invalidation_rule=content.invalidation_rule, transition_reason=reason,
        author_user_id=author_user_id,
    )
    if actor is not None:
        row.author_auth_token_id = actor.token_id
        row.author_auth_checked_at = actor.checked_at
        row.author_auth_policy = actor.policy_key
    if reviewer is not None:
        row.reviewer_user_id = reviewer.user_id
        row.reviewer_token_id = reviewer.token_id
        row.reviewer_user_role_id = reviewer.user_role_id
        row.reviewer_role_permission_id = reviewer.role_permission_id
        row.reviewer_permission_id = reviewer.permission_id
        row.reviewer_permission_key = reviewer.policy_key
        row.reviewer_checked_at = reviewer.checked_at
        row.reviewer_policy = reviewer.policy_key
        row.reviewer_reason = reason
    return row


def _insert_links(session: Session, tenant_id: UUID, company_id: UUID,
                  version_id: UUID, links: tuple[EvidenceLinkRequest, ...]) -> None:
    """在版本创建事务内一次插入完整链接集合。

    Args:
        session: 当前事务。
        tenant_id: scoped 租户。
        company_id: scoped 公司。
        version_id: 新 immutable 版本。
        links: replace 或 deterministic copy 的全部链接。
    Returns:
        无。
    Raises:
        EvidenceRepositoryError: FK 或持久约束失败。
    """

    for link in links:
        row = EvidenceLinkRow(
            id=link.id, tenant_id=tenant_id, company_id=company_id,
            claim_version_id=version_id, relation=link.relation.value,
            fact_id=link.fact_id, security_id=link.security_id,
            locator_ticker=link.locator_ticker,
            locator_json=link.locator.to_dict() if link.locator is not None else null(),
        )
        try:
            # 每条 link 各有 savepoint；digest 冲突后保留同批前序 row 供新语句分类。
            with session.begin_nested():
                session.add(row)
                session.flush()
        except IntegrityError as error:
            _raise_integrity(session, error, tenant_id, company_id, version_id, link)


def _digest_for_locator(session: Session, locator: EvidenceLocatorSnapshot) -> bytes:
    """以 PostgreSQL JSONB 文本规则计算候选 direct locator digest。

    Args:
        session: 当前 READ COMMITTED 事务。
        locator: 已核结构镜像。
    Returns:
        32-byte PG digest。
    Raises:
        EvidenceRepositoryError: 数据库结果形态非法。
    """

    digest = session.execute(text(
        "SELECT sha256(convert_to(CAST(:locator AS jsonb)::text, 'UTF8'))"
    ), {"locator": locator.canonical_bytes().decode("utf-8")}).scalar_one()
    if type(digest) is not bytes or len(digest) != 32:
        raise EvidenceRepositoryError()
    return digest


def _raise_integrity(session: Session, error: IntegrityError,
                     tenant_id: UUID, company_id: UUID, version_id: UUID,
                     link: EvidenceLinkRequest) -> NoReturn:
    """仅对命名 direct digest unique 23505 做完整 JSONB 分类。

    当前 INSERT savepoint 已回滚；新 READ COMMITTED 语句可见同批前序 row。

    Args:
        session: 仍活跃的外层 READ COMMITTED 事务。
        error: 已回滚单条 INSERT 的 IntegrityError。
        tenant_id: scoped 租户。
        company_id: 链接公司。
        version_id: 新版本。
        link: 失败的 direct link。
    Returns:
        永不返回。
    Raises:
        EvidenceDuplicateTargetError: 同 security 且 full JSONB 相同。
        EvidenceDigestCollisionError: 同 security/digest 但 full JSONB 不同。
        EvidenceRepositoryError: 命名索引冲突却找不到 row。
        EvidenceConflictError: 其它完整性冲突。
    """

    origin = error.orig
    if (not isinstance(origin, PsycopgError) or origin.sqlstate != "23505" or
            origin.diag.constraint_name != _DIRECT_DIGEST_INDEX):
        raise EvidenceConflictError() from None
    if link.locator is None or link.security_id is None:
        raise EvidenceRepositoryError() from None
    digest = _digest_for_locator(session, link.locator)
    row = session.scalar(select(EvidenceLinkRow).where(
        EvidenceLinkRow.tenant_id == tenant_id,
        EvidenceLinkRow.company_id == company_id,
        EvidenceLinkRow.claim_version_id == version_id,
        EvidenceLinkRow.relation == link.relation.value,
        EvidenceLinkRow.security_id == link.security_id,
        EvidenceLinkRow.locator_index_digest == digest,
        EvidenceLinkRow.fact_id.is_(None),
    ))
    if row is not None:
        if row.locator_json == link.locator.to_dict():
            raise EvidenceDuplicateTargetError()
        raise EvidenceDigestCollisionError()
    raise EvidenceRepositoryError()


def _selection(session: Session, tenant_id: UUID, current: ClaimVersion,
               selection: EvidenceSelection, new_version_id: UUID) -> tuple[UUID | None, tuple[EvidenceLinkRequest, ...], dict[str, _JsonValue]]:
    """从首次 expected_version 的 immutable source 展开证据与指纹。

    Args:
        session: 当前事务。
        tenant_id: scoped 租户。
        current: 已核 expected_version。
        selection: replace 或 copy。
        new_version_id: successor ID。
    Returns:
        source ID、完整新 links、指纹 frame。
    Raises:
        EvidenceRepositoryError: source/link 不闭合。
    """

    if selection.mode is EvidenceMode.REPLACE_ALL:
        assert selection.links is not None
        return None, selection.links, evidence_fingerprint_frame(selection, new_version_id=new_version_id)
    source_links = _links(session, tenant_id, current.company_id, current.id)
    requests = tuple(link.request for link in source_links)
    try:
        frame = evidence_fingerprint_frame(
            selection, new_version_id=new_version_id,
            copy_source_version_id=current.id, copy_source_version_no=current.version_no,
            copy_source_links=requests,
        )
        copies = tuple(EvidenceLinkRequest(
            copied_link_id(new_version_id, link.id), link.relation,
            link.fact_id, link.security_id, link.locator,
        ) for link in requests)
        EvidenceSelection(copies, False)
        return current.id, copies, frame
    except (TypeError, ValueError):
        raise EvidenceRepositoryError() from None


def _current_source(session: Session, tenant_id: UUID, claim_id: UUID,
                    expected_version: int) -> tuple[ClaimRow, ClaimSnapshot]:
    """锁 shell 后核 current 与 caller CAS。

    Args:
        session: 当前事务。
        tenant_id: scoped 租户。
        claim_id: Claim ID。
        expected_version: caller CAS token。
    Returns:
        shell 与完整当前快照。
    Raises:
        EvidenceNotFoundError: shell 缺失。
        EvidenceOptimisticConflictError: CAS 版本已过期。
    """

    row = _claim(session, tenant_id, claim_id, lock=True)
    if row is None:
        raise EvidenceNotFoundError()
    if row.version != expected_version:
        raise EvidenceOptimisticConflictError()
    return row, _snapshot(session, row)


def _append(session: Session, row: ClaimRow, current: ClaimSnapshot,
            version_id: UUID, kind: ClaimTransitionKind, content: ClaimContent,
            selection: EvidenceSelection, operation_id: UUID, fingerprint: str,
            source_id: UUID | None, links: tuple[EvidenceLinkRequest, ...],
            author_id: UUID | None = None, reason: str | None = None,
            actor: ActorAuthWitness | None = None,
            reviewer: ReviewerAuthWitness | None = None) -> ClaimSnapshot:
    """在持锁 shell 上追加版本、全量 links 并 CAS 更新 head。

    Args:
        session: 当前事务。
        row: 持锁 shell。
        current: expected_version 快照。
        version_id: successor ID。
        kind: 动作。
        content: successor 内容。
        selection: 证据模式。
        operation_id: caller 操作 ID。
        fingerprint: canonical 指纹。
        source_id: copy source。
        links: 全量 successor links。
        author_id: 普通或 token-derived 作者。
        reason: 动作原因。
        actor: token-derived 作者认证。
        reviewer: reviewer 认证。
    Returns:
        新完整快照。
    Raises:
        EvidenceOptimisticConflictError: CAS 更新未命中。
        EvidenceRepositoryError: 持久行不闭合。
    """

    successor = _version_row(row.tenant_id, row.company_id, row.id,
                             current.version + 1, version_id, kind, content,
                             selection, source_id, operation_id, fingerprint,
                             author_id, reason, actor, reviewer)
    session.add(successor)
    session.flush()
    _insert_links(session, row.tenant_id, row.company_id, version_id, links)
    changed = session.connection().execute(update(ClaimRow).where(
        ClaimRow.tenant_id == row.tenant_id, ClaimRow.company_id == row.company_id,
        ClaimRow.id == row.id, ClaimRow.version == current.version,
    ).values(version=current.version + 1, updated_at=successor.created_at)).rowcount
    if changed != 1:
        raise EvidenceOptimisticConflictError()
    session.expire(row)
    return _snapshot(session, row)


class PostgresEvidenceRepository:
    """实现租户闭合的 13 个严格证据仓储入口。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """保存受控 Session 工厂。

        Args:
            session_factory: PG、hide_parameters 的工厂。
        Returns:
            无。
        Raises:
            TypeError: 工厂类型错误。
        """

        self._factory = session_factory

    def create_fact(self, scope: TenantScope, request: FactCreateRequest) -> Fact:
        """追加不可变 Fact revision，并核同系列前版。

        Args:
            scope: 租户范围。
            request: 完整 Fact 请求。
        Returns:
            已提交 Fact。
        Raises:
            EvidenceInputError: revision 链非法。
            EvidenceConflictError: operation 或系列版号冲突。
            EvidenceRepositoryError: DB 失败。
        """

        tenant_id = _tenant(scope)
        if type(request) is not FactCreateRequest:
            raise EvidenceInputError()
        fingerprint = _fingerprint("fact_create", tenant_id, request)
        try:
            with _session(self._factory, tenant_id) as session:
                existing = session.scalar(select(FactRow).where(
                    FactRow.tenant_id == tenant_id, FactRow.operation_id == request.operation_id))
                if existing is not None:
                    if existing.operation_fingerprint != fingerprint:
                        raise EvidenceConflictError()
                    return _fact(existing)
                # facts 无 UPDATE ACL；按 tenant/company/series 取事务 advisory lock，
                # 再读 prior，最终仍由 series/revision unique 抵御竞态。
                session.execute(text(
                    "SELECT pg_advisory_xact_lock(hashtextextended(:series_key, 0))"
                ), {"series_key": f"{tenant_id}:{request.company_id}:{request.fact_series_id}"})
                # 等待同系列 writer 后重查 operation，覆盖并发丢响应重试。
                existing = session.scalar(select(FactRow).where(
                    FactRow.tenant_id == tenant_id,
                    FactRow.operation_id == request.operation_id))
                if existing is not None:
                    if existing.operation_fingerprint != fingerprint:
                        raise EvidenceConflictError()
                    return _fact(existing)
                if request.prior_fact_id is not None:
                    prior = session.scalar(select(FactRow).where(
                        FactRow.tenant_id == tenant_id,
                        FactRow.company_id == request.company_id,
                        FactRow.id == request.prior_fact_id))
                    if (prior is None or prior.fact_series_id != request.fact_series_id
                            or prior.revision_no != request.revision_no - 1):
                        raise EvidenceInputError()
                row = _fact_row(tenant_id, request, fingerprint)
                session.add(row)
                session.flush()
                session.refresh(row)
                return _fact(row)
        except IntegrityError:
            raise EvidenceConflictError() from None

    def get_fact(self, scope: TenantScope, fact_id: UUID) -> Fact | None:
        """读取一个 scoped Fact。

        Args:
            scope: 租户范围。
            fact_id: Fact ID。
        Returns:
            Fact 或空。
        Raises:
            EvidenceInputError: ID 无效。
            EvidenceRepositoryError: 行漂移。
        """

        tenant_id = _tenant(scope)
        _id(fact_id)
        with _session(self._factory, tenant_id) as session:
            row = session.scalar(select(FactRow).where(
                FactRow.tenant_id == tenant_id, FactRow.id == fact_id))
            return _fact(row) if row is not None else None

    def list_fact_revisions(self, scope: TenantScope, company_id: UUID,
                            fact_series_id: UUID) -> tuple[Fact, ...]:
        """按版号读取同一系列的全部 scoped revision。

        Args:
            scope: 租户范围。
            company_id: 系列所属公司 ID。
            fact_series_id: 系列 ID。
        Returns:
            版号升序 Fact tuple。
        Raises:
            EvidenceInputError: ID 无效。
            EvidenceRepositoryError: 链断裂或漂移。
        """

        tenant_id = _tenant(scope)
        _id(company_id)
        _id(fact_series_id)
        with _session(self._factory, tenant_id) as session:
            rows = session.scalars(select(FactRow).where(
                FactRow.tenant_id == tenant_id,
                FactRow.company_id == company_id,
                FactRow.fact_series_id == fact_series_id,
            ).order_by(FactRow.revision_no)).all()
            facts = tuple(_fact(row) for row in rows)
            for index, fact in enumerate(facts, 1):
                if (fact.request.revision_no != index or
                        (index > 1 and fact.request.prior_fact_id != facts[index - 2].id) or
                        fact.tenant_id != tenant_id or
                        fact.request.company_id != company_id or
                        fact.request.fact_series_id != fact_series_id):
                    raise EvidenceRepositoryError()
            return facts

    def create_claim(self, scope: TenantScope, request: ClaimCreateRequest) -> ClaimSnapshot:
        """原子建立 shell、V1 draft 和完整 links。

        Args:
            scope: 租户范围。
            request: V1 请求。
        Returns:
            当前 Claim 快照。
        Raises:
            EvidenceInputError: 请求非法。
            EvidenceConflictError: ID 或 operation 冲突。
            EvidenceRepositoryError: DB 失败。
        """

        tenant_id = _tenant(scope)
        if type(request) is not ClaimCreateRequest:
            raise EvidenceInputError()
        assert request.evidence.links is not None
        frame = evidence_fingerprint_frame(request.evidence, new_version_id=request.version_id)
        fingerprint = _fingerprint("claim_create", tenant_id, request, evidence=frame)
        try:
            with _session(self._factory, tenant_id) as session:
                existing = session.scalar(select(ClaimVersionRow).where(
                    ClaimVersionRow.tenant_id == tenant_id,
                    ClaimVersionRow.operation_id == request.operation_id))
                if existing is not None:
                    if existing.operation_fingerprint != fingerprint or existing.id != request.version_id:
                        raise EvidenceConflictError()
                    shell = _claim(session, tenant_id, request.id, lock=False)
                    if shell is None:
                        raise EvidenceRepositoryError()
                    historical = _historical_snapshot(session, shell, existing)
                    if not _same_links(historical.links, request.evidence.links):
                        raise EvidenceRepositoryError()
                    return historical
                shell = ClaimRow(id=request.id, tenant_id=tenant_id,
                                 company_id=request.company_id, version=1)
                session.add(shell)
                session.flush()
                session.add(_version_row(
                    tenant_id, request.company_id, request.id, 1, request.version_id,
                    ClaimTransitionKind.CLAIM_CREATE, request.content, request.evidence,
                    None, request.operation_id, fingerprint, request.author_user_id,
                    None, None, None))
                session.flush()
                _insert_links(session, tenant_id, request.company_id,
                              request.version_id, request.evidence.links)
                session.refresh(shell)
                return _snapshot(session, shell)
        except IntegrityError:
            raise EvidenceConflictError() from None

    def get_claim(self, scope: TenantScope, claim_id: UUID) -> ClaimSnapshot | None:
        """受控读取 current，并物化已到期 approved。

        Args:
            scope: 租户范围。
            claim_id: Claim ID。
        Returns:
            当前快照或空。
        Raises:
            EvidenceInputError: ID 无效。
            EvidenceRepositoryError: head 漂移。
        """

        tenant_id = _tenant(scope)
        _id(claim_id)
        with _session(self._factory, tenant_id) as session:
            row = _claim(session, tenant_id, claim_id, lock=True)
            if row is None:
                return None
            return self._materialize_if_expired(session, row, _snapshot(session, row))

    def append_claim_version(self, scope: TenantScope,
                             request: ClaimVersionAppendRequest) -> ClaimSnapshot:
        """按状态矩阵追加普通修订或提交审核。

        Args:
            scope: 租户范围。
            request: expected_version、内容与证据。
        Returns:
            successor 快照。
        Raises:
            EvidenceInputError: 状态边非法。
            EvidenceOptimisticConflictError: CAS 冲突。
            EvidenceRepositoryError: DB 失败。
        """

        tenant_id = _tenant(scope)
        if type(request) is not ClaimVersionAppendRequest:
            raise EvidenceInputError()
        try:
            with _session(self._factory, tenant_id) as session:
                retry = self._retry_version(session, tenant_id, request.operation_id,
                                            request, "claim_append")
                if retry is not None:
                    return retry
                row, current = _current_source(session, tenant_id, request.claim_id,
                                               request.expected_version)
                source_id, links, frame = _selection(session, tenant_id, current.current,
                                                     request.evidence, request.new_version_id)
                changed = (current.current.content != request.content or
                           {(link.request.relation.value, *link.request.target_identity()) for link in current.links}
                           != {(link.relation.value, *link.target_identity()) for link in links})
                try:
                    kind = validate_append_transition(current.current.content.status,
                                                      request.content.status,
                                                      materially_changed=changed)
                except (TypeError, ValueError):
                    raise EvidenceInputError() from None
                fingerprint = _fingerprint("claim_append", tenant_id, request,
                                           evidence=frame)
                return _append(session, row, current, request.new_version_id, kind,
                               request.content, request.evidence, request.operation_id,
                               fingerprint, source_id, links, request.author_user_id)
        except IntegrityError:
            raise EvidenceConflictError() from None

    def _retry_version(self, session: Session, tenant_id: UUID, operation_id: UUID,
                       request: ClaimVersionAppendRequest | ClaimRevisionBeginRequest |
                       ClaimReviewRequest | ClaimConflictResolveRequest,
                       kind: str, actor_id: UUID | None = None) -> ClaimSnapshot | None:
        """以原 immutable source 重新计算已提交操作指纹。

        Args:
            session: 当前事务。
            tenant_id: scoped 租户。
            operation_id: caller 操作 ID。
            request: 同类重试请求。
            kind: 稳定动作名称。
            actor_id: token 派生 actor。
        Returns:
            相同操作的原结果或空。
        Raises:
            EvidenceConflictError: payload 或 actor 不同。
            EvidenceRepositoryError: 原 source/link 漂移。
        """

        persisted = session.scalar(select(ClaimVersionRow).where(
            ClaimVersionRow.tenant_id == tenant_id,
            ClaimVersionRow.operation_id == operation_id))
        if persisted is None:
            return None
        claim_id = request.claim_id if not isinstance(request, ClaimConflictResolveRequest) else request.selected_claim_id
        version_id = request.new_version_id
        if persisted.claim_id != claim_id or persisted.id != version_id:
            raise EvidenceConflictError()
        selection = request.evidence
        if persisted.evidence_mode != selection.mode.value:
            raise EvidenceConflictError()
        if selection.mode is EvidenceMode.COPY_PREVIOUS:
            source_id = persisted.copy_source_version_id
            if source_id is None:
                raise EvidenceRepositoryError()
            source = session.scalar(select(ClaimVersionRow).where(
                ClaimVersionRow.tenant_id == tenant_id,
                ClaimVersionRow.company_id == persisted.company_id,
                ClaimVersionRow.claim_id == claim_id,
                ClaimVersionRow.id == source_id))
            if source is None or source.version_no + 1 != persisted.version_no:
                raise EvidenceRepositoryError()
            _, expected_links, frame = _selection(session, tenant_id, _version(source),
                                                  selection, version_id)
        else:
            _, expected_links, frame = _selection(session, tenant_id, _version(persisted),
                                                  selection, version_id)
        fingerprint = _fingerprint(
            kind, tenant_id, request, evidence=frame, actor_id=actor_id,
            permission_key=REVIEW_PERMISSION_KEY if kind == "claim_review" else None,
        )
        if persisted.operation_fingerprint != fingerprint:
            raise EvidenceConflictError()
        actual = _links(session, tenant_id, persisted.company_id, persisted.id)
        if not _same_links(actual, expected_links):
            raise EvidenceRepositoryError()
        shell = _claim(session, tenant_id, claim_id, lock=False)
        if shell is None:
            raise EvidenceRepositoryError()
        return _historical_snapshot(session, shell, persisted)

    def _materialize_if_expired(self, session: Session, row: ClaimRow,
                                current: ClaimSnapshot) -> ClaimSnapshot:
        """首次受控访问将过期 approved CAS 为 review_required。

        Args:
            session: 当前持锁事务。
            row: Claim shell。
            current: 当前完整快照。
        Returns:
            原或新快照。
        Raises:
            EvidenceRepositoryError: 持久写入失败。
        """

        until = current.current.content.valid_until
        if current.current.content.status is not ClaimStatus.APPROVED or (until is not None and until > _clock(session)):
            return current
        version_id = uuid5(NAMESPACE_URL, _EXPIRY_NAMESPACE + str(current.current.id))
        operation_id = uuid5(NAMESPACE_URL, _EXPIRY_NAMESPACE + "operation:" + str(current.current.id))
        content = ClaimContent(current.current.content.statement,
                               current.current.content.confidence_band,
                               current.current.content.probability,
                               current.current.content.impact_horizon,
                               current.current.content.valid_until,
                               ClaimStatus.REVIEW_REQUIRED,
                               current.current.content.invalidation_rule)
        selection = EvidenceSelection(None, True)
        source_id, links, frame = _selection(session, row.tenant_id, current.current,
                                             selection, version_id)
        fingerprint = _fingerprint("claim_expiry", row.tenant_id,
                                   {"claim_id": str(row.id), "source_version_id": str(current.current.id)},
                                   evidence=frame)
        return _append(session, row, current, version_id, ClaimTransitionKind.EXPIRY,
                       content, selection, operation_id, fingerprint, source_id, links,
                       reason="valid_until_elapsed")

    def begin_claim_revision(self, scope_hint: TenantScope, raw_token: bytes,
                             request: ClaimRevisionBeginRequest) -> ClaimSnapshot:
        """用 active bearer 的主体在同 lineage 重开 draft。

        Args:
            scope_hint: 不可信租户定位提示。
            raw_token: 只传认证 helper 的 bearer。
            request: 无自由作者字段的重开请求。
        Returns:
            含 token-derived 作者的 successor。
        Raises:
            EvidenceUnauthorizedError: token 或 hint 无效。
            EvidenceMaterializationNeededError: 过期 head 尚未物化。
            EvidenceRepositoryError: 持久失败。
        """

        if type(request) is not ClaimRevisionBeginRequest:
            raise EvidenceInputError()
        try:
            tenant_id = _tenant(scope_hint)
        except EvidenceInputError:
            raise EvidenceUnauthorizedError() from None
        try:
            with _session(self._factory, tenant_id, auth=True) as session:
                auth = authorize_active_actor(session, scope_hint, raw_token)
                if auth.tenant_id != tenant_id:
                    raise EvidenceUnauthorizedError()
                retry = self._retry_version(session, tenant_id, request.operation_id,
                                            request, "claim_begin_revision", auth.user_id)
                if retry is not None:
                    return retry
                row, current = _current_source(session, tenant_id, request.claim_id,
                                               request.expected_version)
                until = current.current.content.valid_until
                if (current.current.content.status is ClaimStatus.APPROVED and
                        (until is None or until <= _clock(session))):
                    raise EvidenceMaterializationNeededError()
                try:
                    validate_begin_transition(current.current.content.status,
                                              request.content.status)
                except (TypeError, ValueError):
                    raise EvidenceInputError() from None
                source_id, links, frame = _selection(session, tenant_id, current.current,
                                                     request.evidence, request.new_version_id)
                fingerprint = _fingerprint("claim_begin_revision", tenant_id,
                                           request, evidence=frame, actor_id=auth.user_id)
                return _append(session, row, current, request.new_version_id,
                               ClaimTransitionKind.BEGIN_REVISION, request.content,
                               request.evidence, request.operation_id, fingerprint,
                               source_id, links, auth.user_id, request.revision_reason,
                               auth)
        except IntegrityError:
            raise EvidenceConflictError() from None

    def record_claim_review(self, scope_hint: TenantScope, raw_token: bytes,
                            request: ClaimReviewRequest) -> ClaimSnapshot:
        """以同事务 reviewer grant 追加审查决定。

        Args:
            scope_hint: 不可信租户定位提示。
            raw_token: 只供认证 helper 消费的 bearer。
            request: 无自由 reviewer 字段的审查请求。
        Returns:
            含完整 grant witness 的 successor。
        Raises:
            EvidenceUnauthorizedError: bearer 或 grant 无效。
            EvidenceInputError: 状态边/证据/期限非法。
            EvidenceRepositoryError: 持久失败。
        """

        if type(request) is not ClaimReviewRequest:
            raise EvidenceInputError()
        try:
            tenant_id = _tenant(scope_hint)
        except EvidenceInputError:
            raise EvidenceUnauthorizedError() from None
        try:
            with _session(self._factory, tenant_id, auth=True) as session:
                auth = authorize_reviewer(session, scope_hint, raw_token)
                if auth.tenant_id != tenant_id:
                    raise EvidenceUnauthorizedError()
                retry = self._retry_version(session, tenant_id, request.operation_id,
                                            request, "claim_review", auth.user_id)
                if retry is not None:
                    return retry
                row, current = _current_source(session, tenant_id, request.claim_id,
                                               request.expected_version)
                until = current.current.content.valid_until
                if (current.current.content.status is ClaimStatus.APPROVED and
                        (until is None or until <= _clock(session))):
                    raise EvidenceMaterializationNeededError()
                source_id, links, frame = _selection(session, tenant_id, current.current,
                                                     request.evidence, request.new_version_id)
                try:
                    validate_review_transition(
                        current.current.content.status, request.content.status,
                        supports_count=sum(link.relation is EvidenceRelation.SUPPORTS for link in links),
                        valid_until=request.content.valid_until,
                        statement_clock=_clock(session),
                    )
                except (TypeError, ValueError):
                    raise EvidenceInputError() from None
                fingerprint = _fingerprint("claim_review", tenant_id, request,
                                           evidence=frame, actor_id=auth.user_id,
                                           permission_key=auth.policy_key)
                return _append(session, row, current, request.new_version_id,
                               ClaimTransitionKind.REVIEW_DECISION, request.content,
                               request.evidence, request.operation_id, fingerprint,
                               source_id, links, reason=request.review_reason,
                               reviewer=auth)
        except IntegrityError:
            raise EvidenceConflictError() from None

    def open_conflict(self, scope: TenantScope,
                      request: ClaimConflictOpenRequest) -> ClaimConflict:
        """在同租户/公司两个 immutable 版本间建立 open conflict。

        Args:
            scope: 租户范围。
            request: 有序端点与原因。
        Returns:
            open conflict。
        Raises:
            EvidenceInputError: 端点范围非法。
            EvidenceConflictError: operation 或 pair 冲突。
            EvidenceRepositoryError: DB 失败。
        """

        tenant_id = _tenant(scope)
        if type(request) is not ClaimConflictOpenRequest:
            raise EvidenceInputError()
        fingerprint = _fingerprint("conflict_open", tenant_id, request)
        try:
            with _session(self._factory, tenant_id) as session:
                old = session.scalar(select(ClaimConflictRow).where(
                    ClaimConflictRow.tenant_id == tenant_id,
                    ClaimConflictRow.operation_id == request.operation_id))
                if old is not None:
                    if old.operation_fingerprint != fingerprint:
                        raise EvidenceConflictError()
                    return _conflict(old)
                endpoints = session.scalars(select(ClaimVersionRow).where(
                    ClaimVersionRow.tenant_id == tenant_id,
                    ClaimVersionRow.company_id == request.company_id,
                    ClaimVersionRow.id.in_((request.left_version_id,
                                            request.right_version_id)))).all()
                if len(endpoints) != 2:
                    raise EvidenceInputError()
                row = ClaimConflictRow(
                    id=request.id, tenant_id=tenant_id, company_id=request.company_id,
                    left_version_id=request.left_version_id,
                    right_version_id=request.right_version_id,
                    material=request.material, status=ConflictStatus.OPEN.value,
                    reason=request.reason, operation_id=request.operation_id,
                    operation_fingerprint=fingerprint, version=1,
                )
                session.add(row)
                session.flush()
                session.refresh(row)
                return _conflict(row)
        except IntegrityError:
            raise EvidenceConflictError() from None

    def resolve_conflict_with_review(self, scope_hint: TenantScope, raw_token: bytes,
                                     request: ClaimConflictResolveRequest) -> ClaimConflict:
        """reviewer 建完整 successor 后原子关闭一个 material conflict。

        Args:
            scope_hint: 不可信租户定位提示。
            raw_token: 只供认证 helper 消费的 bearer。
            request: 双 Claim 与 conflict CAS、完整链接和新增目标。
        Returns:
            resolved conflict。
        Raises:
            EvidenceUnauthorizedError: bearer/grant 无效。
            EvidenceInputError: 端点、新目标或状态边非法。
            EvidenceOptimisticConflictError: 任一 CAS 不匹配。
            EvidenceConflictError: 已提交 operation 的 actor 或请求不同。
            EvidenceRepositoryError: DB 失败。
        """

        if type(request) is not ClaimConflictResolveRequest:
            raise EvidenceInputError()
        try:
            tenant_id = _tenant(scope_hint)
        except EvidenceInputError:
            raise EvidenceUnauthorizedError() from None
        try:
            with _session(self._factory, tenant_id, auth=True) as session:
                auth = authorize_reviewer(session, scope_hint, raw_token)
                if auth.tenant_id != tenant_id:
                    raise EvidenceUnauthorizedError()
                prior = session.scalar(select(ClaimConflictRow).where(
                    ClaimConflictRow.tenant_id == tenant_id,
                    ClaimConflictRow.resolution_operation_id == request.operation_id))
                if prior is not None:
                    self._retry_resolution(session, tenant_id, prior, request, auth.user_id)
                    return _conflict(prior)
                conflict = session.scalar(select(ClaimConflictRow).where(
                    ClaimConflictRow.tenant_id == tenant_id,
                    ClaimConflictRow.id == request.conflict_id))
                if conflict is None:
                    raise EvidenceNotFoundError()
                endpoint_rows = session.scalars(select(ClaimVersionRow).where(
                    ClaimVersionRow.tenant_id == tenant_id,
                    ClaimVersionRow.company_id == conflict.company_id,
                    ClaimVersionRow.id.in_((conflict.left_version_id,
                                            conflict.right_version_id)))).all()
                if len(endpoint_rows) != 2:
                    raise EvidenceRepositoryError()
                claims = sorted({version.claim_id for version in endpoint_rows})
                if request.selected_claim_id not in claims:
                    raise EvidenceInputError()
                locked = session.scalars(select(ClaimRow).where(
                    ClaimRow.tenant_id == tenant_id,
                    ClaimRow.company_id == conflict.company_id,
                    ClaimRow.id.in_(claims)).order_by(ClaimRow.id).with_for_update()).all()
                if len(locked) != len(claims):
                    raise EvidenceRepositoryError()
                conflict = session.scalar(select(ClaimConflictRow).where(
                    ClaimConflictRow.tenant_id == tenant_id,
                    ClaimConflictRow.id == request.conflict_id).with_for_update())
                if conflict is None or conflict.status != ConflictStatus.OPEN.value:
                    raise EvidenceOptimisticConflictError()
                if conflict.version != request.expected_conflict_version:
                    raise EvidenceOptimisticConflictError()
                selected = next(row for row in locked if row.id == request.selected_claim_id)
                other = next((row for row in locked if row.id != selected.id), None)
                if (selected.version != request.expected_selected_version or
                        (other is not None and other.version != request.expected_other_version) or
                        (other is None and selected.version != request.expected_other_version)):
                    raise EvidenceOptimisticConflictError()
                current = _snapshot(session, selected)
                until = current.current.content.valid_until
                if (current.current.content.status is ClaimStatus.APPROVED and
                        (until is None or until <= _clock(session))):
                    raise EvidenceMaterializationNeededError()
                try:
                    validate_conflict_resolution_transition(current.current.content.status,
                                                            request.content.status)
                except (TypeError, ValueError):
                    raise EvidenceInputError() from None
                source_id, links, frame = _selection(session, tenant_id, current.current,
                                                     request.evidence, request.new_version_id)
                new_link = next((link for link in links if link.id == request.new_link_id), None)
                if new_link is None:
                    raise EvidenceInputError()
                old_targets: set[tuple[str, str, str]] = set()
                for endpoint in endpoint_rows:
                    old_targets.update(link.request.target_identity() for link in _links(
                        session, tenant_id, conflict.company_id, endpoint.id))
                if new_link.target_identity() in old_targets:
                    raise EvidenceInputError()
                fingerprint = _fingerprint("conflict_resolve", tenant_id, request,
                                           evidence=frame, actor_id=auth.user_id,
                                           permission_key=auth.policy_key)
                _append(session, selected, current, request.new_version_id,
                        ClaimTransitionKind.CONFLICT_RESOLUTION, request.content,
                        request.evidence, request.operation_id, fingerprint,
                        source_id, links, reason=request.resolution_reason,
                        reviewer=auth)
                changed = session.connection().execute(update(ClaimConflictRow).where(
                    ClaimConflictRow.tenant_id == tenant_id,
                    ClaimConflictRow.company_id == conflict.company_id,
                    ClaimConflictRow.id == conflict.id,
                    ClaimConflictRow.version == request.expected_conflict_version,
                    ClaimConflictRow.status == ConflictStatus.OPEN.value,
                ).values(
                    status=ConflictStatus.RESOLVED.value,
                    version=conflict.version + 1, updated_at=_clock(session),
                    resolution_operation_id=request.operation_id,
                    resolution_operation_fingerprint=fingerprint,
                    resolution_new_version_id=request.new_version_id,
                    resolution_new_link_id=request.new_link_id,
                    resolution_reviewer_user_id=auth.user_id,
                    resolution_reviewer_token_id=auth.token_id,
                    resolution_user_role_id=auth.user_role_id,
                    resolution_role_permission_id=auth.role_permission_id,
                    resolution_permission_id=auth.permission_id,
                    resolution_permission_key=auth.policy_key,
                    resolution_checked_at=auth.checked_at,
                    resolution_policy=auth.policy_key,
                    resolution_reason=request.resolution_reason,
                    resolved_at=_clock(session),
                )).rowcount
                if changed != 1:
                    raise EvidenceOptimisticConflictError()
                session.expire(conflict)
                return _conflict(conflict)
        except IntegrityError:
            raise EvidenceConflictError() from None

    def _retry_resolution(self, session: Session, tenant_id: UUID,
                          conflict: ClaimConflictRow,
                          request: ClaimConflictResolveRequest,
                          actor_id: UUID) -> None:
        """核丢响应重试的 conflict/version/link 双向一致性。

        Args:
            session: 当前事务。
            tenant_id: token 租户。
            conflict: 已按 operation 命中的解决记录。
            request: 本次重试输入。
            actor_id: 当前有效 token 主体。
        Returns:
            无。
        Raises:
            EvidenceConflictError: actor、request 或关联版本不同。
            EvidenceRepositoryError: 原 immutable source 漂移。
        """

        if (conflict.id != request.conflict_id or conflict.status != ConflictStatus.RESOLVED.value
                or conflict.resolution_new_version_id != request.new_version_id
                or conflict.resolution_new_link_id != request.new_link_id):
            raise EvidenceConflictError()
        version = session.scalar(select(ClaimVersionRow).where(
            ClaimVersionRow.tenant_id == tenant_id,
            ClaimVersionRow.company_id == conflict.company_id,
            ClaimVersionRow.id == conflict.resolution_new_version_id,
            ClaimVersionRow.operation_id == conflict.resolution_operation_id))
        if version is None:
            raise EvidenceRepositoryError()
        if version.transition_kind != ClaimTransitionKind.CONFLICT_RESOLUTION.value:
            raise EvidenceRepositoryError()
        version_witness = (
            version.reviewer_user_id, version.reviewer_token_id,
            version.reviewer_user_role_id, version.reviewer_role_permission_id,
            version.reviewer_permission_id, version.reviewer_permission_key,
            version.reviewer_checked_at, version.reviewer_policy,
            version.reviewer_reason,
        )
        conflict_witness = (
            conflict.resolution_reviewer_user_id, conflict.resolution_reviewer_token_id,
            conflict.resolution_user_role_id, conflict.resolution_role_permission_id,
            conflict.resolution_permission_id, conflict.resolution_permission_key,
            conflict.resolution_checked_at, conflict.resolution_policy,
            conflict.resolution_reason,
        )
        if (version.operation_fingerprint != conflict.resolution_operation_fingerprint or
                version_witness != conflict_witness or
                version.reviewer_permission_key != REVIEW_PERMISSION_KEY):
            raise EvidenceRepositoryError()
        if version.evidence_mode != request.evidence.mode.value:
            raise EvidenceConflictError()
        if request.evidence.mode is EvidenceMode.COPY_PREVIOUS:
            source = session.scalar(select(ClaimVersionRow).where(
                ClaimVersionRow.tenant_id == tenant_id,
                ClaimVersionRow.company_id == conflict.company_id,
                ClaimVersionRow.id == version.copy_source_version_id))
            if (source is None or source.claim_id != version.claim_id or
                    source.version_no + 1 != version.version_no):
                raise EvidenceRepositoryError()
            _, expected, frame = _selection(session, tenant_id, _version(source),
                                            request.evidence, request.new_version_id)
        else:
            _, expected, frame = _selection(session, tenant_id, _version(version),
                                            request.evidence, request.new_version_id)
        fingerprint = _fingerprint("conflict_resolve", tenant_id, request,
                                   evidence=frame, actor_id=actor_id,
                                   permission_key=REVIEW_PERMISSION_KEY)
        if (version.operation_fingerprint != fingerprint or
                conflict.resolution_operation_fingerprint != fingerprint):
            raise EvidenceConflictError()
        # 请求先以完整指纹分类；同指纹下的投影差异才是持久历史损坏。
        if (version.claim_id != request.selected_claim_id or
                version.version_no != request.expected_selected_version + 1 or
                conflict.version != request.expected_conflict_version + 1 or
                version.status != request.content.status.value or
                version.reviewer_user_id != actor_id or
                version.reviewer_reason != request.resolution_reason):
            raise EvidenceRepositoryError()
        actual = _links(session, tenant_id, conflict.company_id, version.id)
        if not _same_links(actual, expected):
            raise EvidenceRepositoryError()
        if request.new_link_id not in {link.request.id for link in actual}:
            raise EvidenceRepositoryError()

    def local_claim_eligibility(self, scope: TenantScope,
                                claim_id: UUID) -> ClaimLocalEligibility:
        """按 PG 时间、open material conflict、状态和 supports 局部筛选。

        Args:
            scope: 租户范围。
            claim_id: Claim ID。
        Returns:
            closed 局部原因；ready 仍需 Fins 验证。
        Raises:
            EvidenceNotFoundError: Claim 缺失。
            EvidenceRepositoryError: head 或链接漂移。
        """

        tenant_id = _tenant(scope)
        _id(claim_id)
        with _session(self._factory, tenant_id) as session:
            row = _claim(session, tenant_id, claim_id, lock=True)
            if row is None:
                raise EvidenceNotFoundError()
            before = _snapshot(session, row)
            now = _clock(session)
            expired = (before.current.content.status is ClaimStatus.APPROVED and
                       (before.current.content.valid_until is None or
                        before.current.content.valid_until <= now))
            current = self._materialize_if_expired(session, row, before)
            if expired:
                return ClaimLocalEligibility(claim_id, LocalEligibilityReason.EXPIRED, now)
            endpoint_ids = set(session.scalars(select(ClaimVersionRow.id).where(
                ClaimVersionRow.tenant_id == tenant_id,
                ClaimVersionRow.company_id == row.company_id,
                ClaimVersionRow.claim_id == claim_id)).all())
            conflicts = session.scalars(select(ClaimConflictRow).where(
                ClaimConflictRow.tenant_id == tenant_id,
                ClaimConflictRow.company_id == row.company_id,
                ClaimConflictRow.material.is_(True),
                ClaimConflictRow.status == ConflictStatus.OPEN.value)).all()
            has_conflict = any(conflict.left_version_id in endpoint_ids or
                               conflict.right_version_id in endpoint_ids
                               for conflict in conflicts)
            reason = local_eligibility_reason(
                current.current.content.status,
                valid_until=current.current.content.valid_until,
                statement_clock=now, has_open_material_conflict=has_conflict,
                supports_count=sum(link.request.relation is EvidenceRelation.SUPPORTS
                                   for link in current.links),
            )
            return ClaimLocalEligibility(claim_id, reason, now)

    def create_proposed_candidate(self, scope: TenantScope,
                                  request: ResearchCandidateCreateRequest) -> ResearchCandidate:
        """仅持久化 proposed JSONB 候选，不晋升 authoritative Fact。

        Args:
            scope: 租户范围。
            request: 已 canonical 的 bounded JSON bytes。
        Returns:
            proposed 候选。
        Raises:
            EvidenceInputError: payload 非 canonical。
            EvidenceConflictError: ID 或 operation 冲突。
            EvidenceRepositoryError: JSONB readback/hash 漂移。
        """

        tenant_id = _tenant(scope)
        if type(request) is not ResearchCandidateCreateRequest:
            raise EvidenceInputError()
        try:
            payload = json.loads(request.canonical_payload_json)
            if type(payload) is not dict:
                raise EvidenceInputError()
            fingerprint = _fingerprint("candidate_propose", tenant_id, request,
                                       evidence={"payload_sha256": request.sha256})
        except (TypeError, ValueError):
            raise EvidenceInputError() from None
        try:
            with _session(self._factory, tenant_id) as session:
                old = session.scalar(select(ResearchCandidateRow).where(
                    ResearchCandidateRow.tenant_id == tenant_id,
                    ResearchCandidateRow.operation_id == request.operation_id))
                if old is not None:
                    if old.operation_fingerprint != fingerprint:
                        raise EvidenceConflictError()
                    return _candidate(old)
                row = ResearchCandidateRow(
                    id=request.id, tenant_id=tenant_id, company_id=request.company_id,
                    origin=request.origin.value, canonical_payload_json=payload,
                    sha256=request.sha256, operation_id=request.operation_id,
                    operation_fingerprint=fingerprint,
                    state=CandidateStatus.PROPOSED.value, version=1,
                )
                session.add(row)
                session.flush()
                session.refresh(row)
                projected = _candidate(row)
                if projected.request.canonical_payload_json != request.canonical_payload_json:
                    raise EvidenceRepositoryError()
                return projected
        except IntegrityError:
            raise EvidenceConflictError() from None

    def get_candidate(self, scope: TenantScope,
                      candidate_id: UUID) -> ResearchCandidate | None:
        """按 tenant 读取候选并重新 canonical 化、核 SHA。

        Args:
            scope: 租户范围。
            candidate_id: 候选 ID。
        Returns:
            候选或空。
        Raises:
            EvidenceInputError: ID 无效。
            EvidenceRepositoryError: JSONB/hash 漂移。
        """

        tenant_id = _tenant(scope)
        _id(candidate_id)
        with _session(self._factory, tenant_id) as session:
            row = session.scalar(select(ResearchCandidateRow).where(
                ResearchCandidateRow.tenant_id == tenant_id,
                ResearchCandidateRow.id == candidate_id))
            return _candidate(row) if row is not None else None


def _conflict(row: ClaimConflictRow) -> ClaimConflict:
    """将冲突行及 reviewer witness 重建为领域投影。

    Args:
        row: scoped conflict 行。
    Returns:
        open 或 resolved conflict。
    Raises:
        EvidenceRepositoryError: witness/状态漂移。
    """

    try:
        reviewer = None
        if row.resolution_reviewer_user_id is not None:
            reviewer = ReviewWitness(
                row.resolution_reviewer_user_id,
                _required_uuid(row.resolution_reviewer_token_id),
                _required_uuid(row.resolution_user_role_id),
                _required_uuid(row.resolution_role_permission_id),
                _required_uuid(row.resolution_permission_id),
                _required_text(row.resolution_permission_key),
                _required_time(row.resolution_checked_at),
                _required_text(row.resolution_policy),
                _required_text(row.resolution_reason),
            )
        return ClaimConflict(
            row.id, row.tenant_id, row.company_id, row.left_version_id,
            row.right_version_id, row.material, ConflictStatus(row.status),
            row.reason, row.version, _utc(row.created_at), _utc(row.updated_at),
            row.operation_id, row.operation_fingerprint,
            row.resolution_new_version_id, row.resolution_new_link_id,
            row.resolution_operation_id, reviewer,
        )
    except (TypeError, ValueError):
        raise EvidenceRepositoryError() from None


def _candidate(row: ResearchCandidateRow) -> ResearchCandidate:
    """对 JSONB 读回重建 canonical bytes 并核 SHA。

    Args:
        row: scoped 候选行。
    Returns:
        有界、hash 一致的候选 DTO。
    Raises:
        EvidenceRepositoryError: payload/hash/状态漂移。
    """

    try:
        canonical = canonical_json_bytes(row.canonical_payload_json)
        canonical = canonical_json_document(canonical)
        if hashlib.sha256(canonical).hexdigest() != row.sha256:
            raise EvidenceRepositoryError()
        request = ResearchCandidateCreateRequest(
            row.id, row.company_id, CandidateOrigin(row.origin), canonical,
            row.operation_id,
        )
        return ResearchCandidate(
            row.tenant_id, request, CandidateStatus(row.state), row.version,
            row.operation_fingerprint, _utc(row.created_at), _utc(row.updated_at),
            row.rejection_code,
        )
    except (TypeError, ValueError):
        raise EvidenceRepositoryError() from None
