"""S31-A 六表 schema 与 S31-B repository 的真实 PostgreSQL 16 验证。"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import partial
from threading import Barrier
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from alembic import command
from psycopg import Error as PsycopgError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from dayu.fins.domain.evidence_locator import (
    EvidenceLocatorError,
    parse_evidence_locator_projection,
)
from dayu.investment.domain.evidence import (
    CandidateOrigin,
    ClaimConflictOpenRequest,
    ClaimConflictResolveRequest,
    ClaimContent,
    ClaimCreateRequest,
    ClaimReviewRequest,
    ClaimRevisionBeginRequest,
    ClaimStatus,
    ClaimVersionAppendRequest,
    ConfidenceBand,
    EvidenceLinkRequest,
    EvidenceLocatorSnapshot,
    EvidenceRelation,
    EvidenceSelection,
    FactCreateRequest,
    FactPitTimes,
    FactValue,
    FactValueKind,
    ImpactHorizon,
    ResearchCandidateCreateRequest,
    VerificationStatus,
    copied_link_id,
)
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.storage import (
    DEFAULT_ORGANIZATION_ID,
    PLATFORM_APP_ROLE,
    PLATFORM_SCHEMA_NAME,
    PlatformMigrationAdmissionError,
)
from dayu.investment.storage import postgres_evidence as evidence_repository_module
from dayu.investment.storage.db import create_platform_engine, create_platform_session_factory
from dayu.investment.storage.evidence_protocols import (
    EvidenceConflictError,
    EvidenceDigestCollisionError,
    EvidenceDuplicateTargetError,
    EvidenceInputError,
    EvidenceMaterializationNeededError,
    EvidenceOptimisticConflictError,
    EvidenceRepositoryError,
    EvidenceUnauthorizedError,
)
from dayu.investment.storage.models_evidence import EvidenceLinkRow
from dayu.investment.storage.postgres_evidence import PostgresEvidenceRepository
from tests.integration.investment.conftest import (
    PlatformCluster,
    TemporaryLogin,
    _alembic_config,
    create_temporary_login,
    drop_temporary_login,
    run_alembic_downgrade,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration

_TENANT = UUID(DEFAULT_ORGANIZATION_ID)
_WHEN = datetime(2025, 1, 2, tzinfo=timezone.utc)
_HEX = "a" * 64


@dataclass(frozen=True, slots=True, repr=False)
class _RepositoryDatabase:
    """独占 PG16 测试库与合成身份。"""

    repository: PostgresEvidenceRepository
    sessions: sessionmaker[Session]
    admin: Engine
    scope: TenantScope
    company: UUID
    security_a: UUID
    security_b: UUID
    user: UUID
    token: UUID
    role_permission: UUID
    bearer: bytes


@pytest.fixture()
def repository_database(platform_cluster: PlatformCluster, lifecycle_database) -> Iterator[_RepositoryDatabase]:
    """迁移随机库并创建 app-role、双 MIC 证券和 reviewer grant。

    Args:
        platform_cluster: fixture 独占 PG16。
        lifecycle_database: 随机数据库工厂。
    Yields:
        合成仓储测试句柄。
    Raises:
        数据库配置错误原样传给 pytest。
    """

    database = lifecycle_database()
    dsn = platform_cluster.dsn_for_database(database, "postgres")
    login: TemporaryLogin | None = None
    admin: Engine | None = None
    app: Engine | None = None
    upgraded = False
    company, security_a, security_b, user, token = (uuid4() for _ in range(5))
    role, permission, user_role, role_permission = (uuid4() for _ in range(4))
    bearer = secrets.token_urlsafe(32).encode("ascii")
    try:
        run_alembic_upgrade(dsn)
        upgraded = True
        login = create_temporary_login(platform_cluster, database, member_of=PLATFORM_APP_ROLE)
        admin = create_platform_engine(dsn)
        app = create_platform_engine(login.dsn)
        with admin.begin() as connection:
            connection.execute(text(
                "INSERT INTO dayu_platform.companies(id,legal_name) VALUES (:id,'Evidence Co')"
            ), {"id": company})
            connection.execute(text(
                "INSERT INTO dayu_platform.securities(id,company_id,ticker,exchange_mic,security_type,currency) VALUES "
                "(:a,:company,'ABC','XNAS','equity','USD'),"
                "(:b,:company,'ABC','XNYS','equity','USD')"
            ), {"a": security_a, "b": security_b, "company": company})
            connection.execute(text(
                "INSERT INTO dayu_platform.users(id,tenant_id,subject,display_name,status) "
                "VALUES (:id,:tenant,'evidence-repo-user','Evidence User','active')"
            ), {"id": user, "tenant": _TENANT})
            connection.execute(text(
                "INSERT INTO dayu_platform.api_tokens(id,tenant_id,user_id,name,token_hash,status,expires_at) "
                "VALUES (:id,:tenant,:user,'synthetic',:hash,'active',statement_timestamp()+interval '1 hour')"
            ), {"id": token, "tenant": _TENANT, "user": user,
                "hash": hashlib.sha256(bearer).hexdigest()})
            connection.execute(text(
                "INSERT INTO dayu_platform.roles(id,tenant_id,name) VALUES (:id,:tenant,'evidence-reviewer')"
            ), {"id": role, "tenant": _TENANT})
            connection.execute(text(
                "INSERT INTO dayu_platform.permissions(id,tenant_id,permission_key) "
                "VALUES (:id,:tenant,'investment.claim.review')"
            ), {"id": permission, "tenant": _TENANT})
            connection.execute(text(
                "INSERT INTO dayu_platform.user_roles(id,tenant_id,user_id,role_id) "
                "VALUES (:id,:tenant,:user,:role)"
            ), {"id": user_role, "tenant": _TENANT, "user": user, "role": role})
            connection.execute(text(
                "INSERT INTO dayu_platform.role_permissions(id,tenant_id,role_id,permission_id) "
                "VALUES (:id,:tenant,:role,:permission)"
            ), {"id": role_permission, "tenant": _TENANT, "role": role,
                "permission": permission})
        scope = Principal(TenantId(str(_TENANT)), "hint-only").to_scope()
        sessions = create_platform_session_factory(app)
        yield _RepositoryDatabase(PostgresEvidenceRepository(sessions), sessions, admin,
                                  scope, company, security_a, security_b, user,
                                  token, role_permission, bearer)
    finally:
        if app is not None:
            app.dispose()
        try:
            if upgraded:
                cleanup_admin = admin if admin is not None else create_platform_engine(dsn)
                try:
                    # 独占随机库六表同批 TRUNCATE；append-only guard 只防 UPDATE/DELETE。
                    with cleanup_admin.begin() as connection:
                        connection.exec_driver_sql(
                            "TRUNCATE dayu_platform.claim_conflicts, dayu_platform.evidence_links, "
                            "dayu_platform.claim_versions, dayu_platform.claims, "
                            "dayu_platform.facts, dayu_platform.research_candidates"
                        )
                finally:
                    cleanup_admin.dispose()
        finally:
            if admin is not None and not upgraded:
                admin.dispose()
            try:
                if login is not None:
                    drop_temporary_login(platform_cluster, login)
            finally:
                # Alembic 即使在 upgrade 中途失败，也尝试回退随机库已落地的 revision。
                run_alembic_downgrade(dsn)


def _repo_locator(*, long: bool = False) -> EvidenceLocatorSnapshot:
    """生成完整合法 Fins v1 结构镜像。

    Args:
        long: 为真时给 document_version 数千字节高熵值。
    Returns:
        document locator。
    Raises:
        结构错误原样传播。
    """

    raw = json.loads(_locator("ABC"))
    if long:
        raw["document_version"] = "v" + secrets.token_hex(3000)
    return EvidenceLocatorSnapshot.from_json_bytes(json.dumps(raw).encode("utf-8"))


def _content(status: ClaimStatus, *, statement: str = "Revenue grows",
             valid_until: datetime | None = None) -> ClaimContent:
    """构造状态矩阵测试的完整 Claim 内容。

    Args:
        status: 目标状态。
        statement: 论断文本。
        valid_until: 可选期限。
    Returns:
        ClaimContent。
    Raises:
        DTO 校验错误原样传播。
    """

    return ClaimContent(statement, ConfidenceBand.MEDIUM, None,
                        ImpactHorizon.LONG, valid_until, status, "revise")


def _claim_db_state(db: _RepositoryDatabase, claim_id: UUID) -> tuple[str, str, str]:
    """在独占随机库比较 Claim head、不可变版本与 link 持久行。

    Args:
        db: 随机 PG16 句柄。
        claim_id: 目标 Claim ID。
    Returns:
        head、有序版本行及 link 行的完整 JSONB 文本快照。
    Raises:
        数据库查询失败原样传播。
    """

    with db.admin.connect() as connection:
        head = connection.execute(text(
            "SELECT to_jsonb(c)::text FROM dayu_platform.claims c WHERE c.id=:id"
        ), {"id": claim_id}).scalar_one()
        versions = connection.execute(text(
            "SELECT COALESCE(jsonb_agg(to_jsonb(v) ORDER BY v.version_no)::text,'[]') "
            "FROM dayu_platform.claim_versions v WHERE v.claim_id=:id"
        ), {"id": claim_id}).scalar_one()
        links = connection.execute(text(
            "SELECT COALESCE(jsonb_agg(to_jsonb(l) ORDER BY v.version_no,l.id)::text,'[]') "
            "FROM dayu_platform.evidence_links l JOIN dayu_platform.claim_versions v "
            "ON v.id=l.claim_version_id AND v.tenant_id=l.tenant_id AND v.company_id=l.company_id "
            "WHERE v.claim_id=:id"
        ), {"id": claim_id}).scalar_one()
    return head, versions, links


def _conflict_db_state(db: _RepositoryDatabase, conflict_id: UUID) -> str:
    """读取目标 Conflict 的完整持久 JSONB 快照。

    Args:
        db: 独占随机 PG16 句柄。
        conflict_id: 已持久化冲突 ID。
    Returns:
        完整行的 JSONB 文本。
    Raises:
        数据库查询失败原样传播。
    """

    with db.admin.connect() as connection:
        return connection.execute(text(
            "SELECT to_jsonb(c)::text FROM dayu_platform.claim_conflicts c WHERE c.id=:id"
        ), {"id": conflict_id}).scalar_one()


def _different_reviewer_bearer(db: _RepositoryDatabase) -> bytes:
    """为同租户另一个主体建立真实 active bearer 与现有 reviewer grant。

    Args:
        db: 已有 reviewer role 的独占随机 PG16 句柄。
    Returns:
        仅交给仓储认证入口的合成 bearer。
    Raises:
        数据库插入失败原样传播。
    """

    user_id, token_id, user_role_id = (uuid4() for _ in range(3))
    bearer = secrets.token_urlsafe(32).encode("ascii")
    with db.admin.begin() as connection:
        connection.execute(text(
            "INSERT INTO dayu_platform.users(id,tenant_id,subject,display_name,status) "
            "VALUES (:id,:tenant,:subject,'Other Reviewer','active')"
        ), {"id": user_id, "tenant": _TENANT, "subject": "reviewer-" + user_id.hex})
        connection.execute(text(
            "INSERT INTO dayu_platform.api_tokens(id,tenant_id,user_id,name,token_hash,status,expires_at) "
            "VALUES (:id,:tenant,:user,'synthetic-other',:hash,'active',statement_timestamp()+interval '1 hour')"
        ), {"id": token_id, "tenant": _TENANT, "user": user_id,
            "hash": hashlib.sha256(bearer).hexdigest()})
        connection.execute(text(
            "INSERT INTO dayu_platform.user_roles(id,tenant_id,user_id,role_id) "
            "SELECT :id,:tenant,:user,role_id FROM dayu_platform.user_roles "
            "WHERE tenant_id=:tenant AND user_id=:original"
        ), {"id": user_role_id, "tenant": _TENANT, "user": user_id, "original": db.user})
    return bearer


def test_repository_fact_claim_copy_retry_and_candidate(repository_database: _RepositoryDatabase) -> None:
    """真 PG 验 Fact revision、双证券 direct links、历史重试及候选 hash。

    Args:
        repository_database: 随机 app-role PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 事务或投影契约漂移。
    """

    db = repository_database
    repo = db.repository
    locator = _repo_locator(long=True)
    fact_id, series = uuid4(), uuid4()
    fact_request = FactCreateRequest(
        fact_id, db.company, db.security_a, series, 1, None, "revenue", "revenue",
        locator, FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("12.25"),
                           unit_code="currency", currency="USD"),
        FactPitTimes(None, None, _WHEN, _WHEN, _WHEN, _WHEN),
        "extractor-v1", VerificationStatus.UNVERIFIED, None, None, uuid4(),
    )
    first = repo.create_fact(db.scope, fact_request)
    assert repo.create_fact(db.scope, fact_request) == first
    assert repo.get_fact(db.scope, fact_id) == first
    second_request = FactCreateRequest(
        uuid4(), db.company, db.security_a, series, 2, fact_id, "revenue", "revenue",
        locator, FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("12.5"),
                           unit_code="currency", currency="USD"),
        FactPitTimes(None, None, _WHEN, _WHEN, _WHEN, _WHEN),
        "extractor-v2", VerificationStatus.UNVERIFIED, None, None, uuid4(),
    )
    second = repo.create_fact(db.scope, second_request)
    assert repo.list_fact_revisions(db.scope, db.company, series) == (first, second)
    links = (EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                 security_id=db.security_a, locator=locator),
             EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                 security_id=db.security_b, locator=locator))
    claim_id, version_id = uuid4(), uuid4()
    create = ClaimCreateRequest(claim_id, db.company, version_id, _content(ClaimStatus.DRAFT),
                                EvidenceSelection(links, False), db.user, uuid4())
    v1 = repo.create_claim(db.scope, create)
    assert v1.version == 1 and len(v1.links) == 2
    assert {link.request.security_id for link in v1.links} == {db.security_a, db.security_b}
    append = ClaimVersionAppendRequest(
        claim_id, 1, uuid4(), _content(ClaimStatus.IN_REVIEW),
        EvidenceSelection(None, True), db.user, uuid4(),
    )
    v2 = repo.append_claim_version(db.scope, append)
    assert v2.version == 2 and len(v2.links) == 2
    assert repo.append_claim_version(db.scope, append) == v2
    assert repo.create_claim(db.scope, create) == v1
    assert repo.create_claim(db.scope, replace(
        create, evidence=EvidenceSelection(tuple(reversed(links)), False))) == v1
    assert repo.get_claim(db.scope, claim_id) == v2
    payload = b'{"origin":"synthetic","score":1}'
    candidate = ResearchCandidateCreateRequest(uuid4(), db.company, CandidateOrigin.AGENT,
                                               payload, uuid4())
    proposed = repo.create_proposed_candidate(db.scope, candidate)
    assert proposed.request.canonical_payload_json == payload
    assert repo.get_candidate(db.scope, candidate.id) == proposed


def test_repository_fact_series_is_company_scoped(repository_database: _RepositoryDatabase) -> None:
    """同租户两公司复用系列 UUID，各自独立追加、读取和拒绝串链。

    Args:
        repository_database: 随机 app-role PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 公司维度或修订链不闭合。
    """

    db = repository_database
    other_company, other_security, series = uuid4(), uuid4(), uuid4()
    with db.admin.begin() as connection:
        connection.execute(text(
            "INSERT INTO dayu_platform.companies(id,legal_name) VALUES (:id,'Other Evidence Co')"
        ), {"id": other_company})
        connection.execute(text(
            "INSERT INTO dayu_platform.securities(id,company_id,ticker,exchange_mic,security_type,currency) "
            "VALUES (:id,:company,'XYZ','XNAS','equity','USD')"
        ), {"id": other_security, "company": other_company})
    locator = _repo_locator()
    other_locator = EvidenceLocatorSnapshot.from_json_bytes(_locator("XYZ").encode("utf-8"))
    base = FactCreateRequest(
        uuid4(), db.company, db.security_a, series, 1, None, "revenue", "revenue",
        locator, FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("5"),
                           unit_code="currency", currency="USD"),
        FactPitTimes(None, None, _WHEN, _WHEN, _WHEN, _WHEN),
        "extractor-v1", VerificationStatus.UNVERIFIED, None, None, uuid4(),
    )
    a1 = db.repository.create_fact(db.scope, base)
    b1_request = replace(base, id=uuid4(), company_id=other_company,
                         security_id=other_security, locator=other_locator,
                         operation_id=uuid4())
    b1 = db.repository.create_fact(db.scope, b1_request)
    a2 = db.repository.create_fact(db.scope, replace(
        base, id=uuid4(), revision_no=2, prior_fact_id=a1.id,
        extractor_version="extractor-v2", operation_id=uuid4()))
    b2 = db.repository.create_fact(db.scope, replace(
        b1_request, id=uuid4(), revision_no=2, prior_fact_id=b1.id,
        extractor_version="extractor-v2", operation_id=uuid4()))
    assert db.repository.list_fact_revisions(db.scope, db.company, series) == (a1, a2)
    assert db.repository.list_fact_revisions(db.scope, other_company, series) == (b1, b2)
    assert db.repository.list_fact_revisions(db.scope, uuid4(), series) == ()
    assert db.repository.list_fact_revisions(db.scope, db.company, uuid4()) == ()
    with pytest.raises(EvidenceInputError):
        db.repository.list_fact_revisions(db.scope, UUID(int=0), series)
    wrong_scope = Principal(TenantId(str(uuid4())), "other-tenant").to_scope()
    assert db.repository.list_fact_revisions(wrong_scope, db.company, series) == ()
    with pytest.raises(EvidenceInputError):
        db.repository.create_fact(db.scope, replace(
            b1_request, id=uuid4(), revision_no=3, prior_fact_id=a2.id,
            extractor_version="extractor-v3", operation_id=uuid4()))
    assert db.repository.list_fact_revisions(db.scope, other_company, series) == (b1, b2)


def test_repository_append_copy_retry_after_head_moves(repository_database: _RepositoryDatabase) -> None:
    """普通 append 复制操作在 head 前进后仍按原 source 幂等重试。

    Args:
        repository_database: 随机 app-role PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 历史 copy、CAS 或全量 link 身份漂移。
    """

    db = repository_database
    locator = _repo_locator()
    claim_id = uuid4()
    link = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                               security_id=db.security_a, locator=locator)
    db.repository.create_claim(db.scope, ClaimCreateRequest(
        claim_id, db.company, uuid4(), _content(ClaimStatus.DRAFT),
        EvidenceSelection((link,), False), db.user, uuid4()))
    copy = ClaimVersionAppendRequest(
        claim_id, 1, uuid4(), _content(ClaimStatus.DRAFT, statement="Revised estimate"),
        EvidenceSelection(None, True), db.user, uuid4())
    copied = db.repository.append_claim_version(db.scope, copy)
    assert len(copied.links) == 1
    assert copied.links[0].request.id == copied_link_id(copy.new_version_id, link.id)
    advanced = db.repository.append_claim_version(db.scope, ClaimVersionAppendRequest(
        claim_id, 2, uuid4(), _content(ClaimStatus.DRAFT, statement="Later estimate"),
        EvidenceSelection(None, True), db.user, uuid4()))
    before = _claim_db_state(db, claim_id)
    assert db.repository.append_claim_version(db.scope, copy) == copied
    assert db.repository.get_claim(db.scope, claim_id) == advanced
    with pytest.raises(EvidenceOptimisticConflictError):
        db.repository.append_claim_version(db.scope, replace(
            copy, new_version_id=uuid4(), operation_id=uuid4()))
    with pytest.raises(EvidenceConflictError):
        db.repository.append_claim_version(db.scope, replace(
            copy, content=_content(ClaimStatus.DRAFT, statement="Different estimate")))
    with pytest.raises(EvidenceConflictError):
        db.repository.append_claim_version(db.scope, replace(
            copy, evidence=EvidenceSelection((EvidenceLinkRequest(
                copied_link_id(copy.new_version_id, link.id), EvidenceRelation.SUPPORTS,
                security_id=db.security_a, locator=locator),), False)))
    assert _claim_db_state(db, claim_id) == before


def test_repository_review_begin_and_conflict_copy_retry(repository_database: _RepositoryDatabase) -> None:
    """真 PG 验 reviewer witness、同 lineage 重开及 conflict copy 丢响应重试。

    Args:
        repository_database: 随机 app-role PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 审核或冲突状态矩阵漂移。
    """

    db, locator = repository_database, _repo_locator()
    repo = db.repository
    a_id, a_v1, b_id, b_v1 = (uuid4() for _ in range(4))
    a_link = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                 security_id=db.security_a, locator=locator)
    b_link = EvidenceLinkRequest(uuid4(), EvidenceRelation.CONTRADICTS,
                                 security_id=db.security_b, locator=locator)
    a = repo.create_claim(db.scope, ClaimCreateRequest(
        a_id, db.company, a_v1, _content(ClaimStatus.DRAFT),
        EvidenceSelection((a_link,), False), db.user, uuid4()))
    b = repo.create_claim(db.scope, ClaimCreateRequest(
        b_id, db.company, b_v1, _content(ClaimStatus.DRAFT),
        EvidenceSelection((b_link,), False), db.user, uuid4()))
    assert a.current.content.status is ClaimStatus.DRAFT
    assert b.current.content.status is ClaimStatus.DRAFT
    review_submit = ClaimVersionAppendRequest(
        a_id, 1, uuid4(), _content(ClaimStatus.IN_REVIEW),
        EvidenceSelection(None, True), db.user, uuid4())
    in_review = repo.append_claim_version(db.scope, review_submit)
    rejected_request = ClaimReviewRequest(
        a_id, 2, uuid4(), _content(ClaimStatus.REJECTED),
        EvidenceSelection(None, True), "contradictory filing", uuid4())
    rejected = repo.record_claim_review(db.scope, db.bearer, rejected_request)
    assert rejected.current.reviewer is not None
    assert rejected.current.reviewer.reviewer_user_id == db.user
    assert repo.record_claim_review(db.scope, db.bearer, rejected_request) == rejected
    begin = ClaimRevisionBeginRequest(
        a_id, 3, uuid4(), _content(ClaimStatus.DRAFT, statement="Revenue revised"),
        EvidenceSelection(None, True), "new filing", uuid4())
    reopened = repo.begin_claim_revision(db.scope, db.bearer, begin)
    assert reopened.current.author_user_id == db.user
    assert reopened.current.author_auth is not None
    assert repo.begin_claim_revision(db.scope, db.bearer, begin) == reopened
    assert repo.record_claim_review(db.scope, db.bearer, rejected_request) == rejected
    assert in_review.version == 2 and reopened.version == 4

    # 两个 V1 端点仍不可变；A 的当前 head 增加端点外的新 Fact 身份。
    fact_id = uuid4()
    repo.create_fact(db.scope, FactCreateRequest(
        fact_id, db.company, db.security_a, uuid4(), 1, None, "margin", "margin",
        locator, FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("8.5"),
                           unit_code="percent"),
        FactPitTimes(None, None, _WHEN, _WHEN, _WHEN, _WHEN),
        "extractor-v1", VerificationStatus.UNVERIFIED, None, None, uuid4(),
    ))
    new_fact_link = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS, fact_id=fact_id)
    replacement_a_link = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                             security_id=db.security_a, locator=locator)
    revised = repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
        a_id, 4, uuid4(), _content(ClaimStatus.DRAFT, statement="Revenue with margin"),
        EvidenceSelection((replacement_a_link, new_fact_link), False), db.user, uuid4()))
    assert revised.version == 5
    assert repo.begin_claim_revision(db.scope, db.bearer, begin) == reopened
    left_v1, right_v1 = sorted((a_v1, b_v1))
    conflict = repo.open_conflict(db.scope, ClaimConflictOpenRequest(
        uuid4(), db.company, left_v1, right_v1, True, "filings disagree", uuid4()))
    assert conflict.status.value == "open"
    resolve_version = uuid4()
    resolve = ClaimConflictResolveRequest(
        conflict.id, a_id, 5, 1, 1, resolve_version,
        copied_link_id(resolve_version, new_fact_link.id),
        _content(ClaimStatus.DRAFT, statement="Revenue with margin"),
        EvidenceSelection(None, True), "new margin evidence", uuid4())
    resolved = repo.resolve_conflict_with_review(db.scope, db.bearer, resolve)
    assert resolved.status.value == "resolved"
    assert resolved.reviewer is not None and resolved.reviewer.reviewer_user_id == db.user
    assert repo.resolve_conflict_with_review(db.scope, db.bearer, resolve) == resolved
    resolved_head = repo.get_claim(db.scope, a_id)
    assert resolved_head is not None and resolved_head.version == 6
    repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
        a_id, 6, uuid4(), _content(ClaimStatus.DRAFT, statement="After resolution"),
        EvidenceSelection(None, True), db.user, uuid4()))
    assert repo.resolve_conflict_with_review(db.scope, db.bearer, resolve) == resolved
    assert repo.record_claim_review(db.scope, db.bearer, rejected_request) == rejected
    wrong_hint = Principal(TenantId(str(uuid4())), "spoofed").to_scope()
    with pytest.raises(EvidenceUnauthorizedError):
        repo.record_claim_review(wrong_hint, db.bearer, rejected_request)
    with pytest.raises(EvidenceUnauthorizedError):
        repo.resolve_conflict_with_review(wrong_hint, db.bearer, resolve)
    new_bearer, new_token = secrets.token_urlsafe(32).encode("ascii"), uuid4()
    with db.admin.begin() as connection:
        connection.execute(text(
            "UPDATE dayu_platform.api_tokens SET status='revoked' WHERE id=:id"
        ), {"id": db.token})
        connection.execute(text(
            "INSERT INTO dayu_platform.api_tokens(id,tenant_id,user_id,name,token_hash,status,expires_at) "
            "VALUES (:id,:tenant,:user,'replacement',:hash,'active',statement_timestamp()+interval '1 hour')"
        ), {"id": new_token, "tenant": _TENANT, "user": db.user,
            "hash": hashlib.sha256(new_bearer).hexdigest()})
    with pytest.raises(EvidenceUnauthorizedError):
        repo.record_claim_review(db.scope, db.bearer, rejected_request)
    with pytest.raises(EvidenceUnauthorizedError):
        repo.resolve_conflict_with_review(db.scope, db.bearer, resolve)
    assert repo.record_claim_review(db.scope, new_bearer, rejected_request) == rejected
    assert repo.resolve_conflict_with_review(db.scope, new_bearer, resolve) == resolved
    with pytest.raises(EvidenceConflictError):
        repo.record_claim_review(db.scope, new_bearer,
                                 replace(rejected_request, review_reason="different"))

    # 完全相同的历史记录下，调用者变化必须是业务冲突，不是存储损坏。
    before = (_claim_db_state(db, a_id), _claim_db_state(db, b_id),
              _conflict_db_state(db, conflict.id))
    other_bearer = _different_reviewer_bearer(db)
    with pytest.raises(EvidenceConflictError) as actor_conflict:
        repo.resolve_conflict_with_review(db.scope, other_bearer, resolve)
    assert actor_conflict.value.code.value == "evidence_conflict"
    changed_requests = (
        replace(resolve, selected_claim_id=b_id),
        replace(resolve, expected_selected_version=resolve.expected_selected_version + 1),
        replace(resolve, expected_conflict_version=resolve.expected_conflict_version + 1),
        replace(resolve, expected_other_version=resolve.expected_other_version + 1),
        replace(resolve, content=replace(resolve.content, status=ClaimStatus.IN_REVIEW)),
        replace(resolve, content=replace(resolve.content, statement="Different resolution")),
        replace(resolve, resolution_reason="different resolution reason"),
        replace(resolve, evidence=EvidenceSelection((new_fact_link,), False)),
    )
    for changed_request in changed_requests:
        with pytest.raises(EvidenceConflictError) as request_conflict:
            repo.resolve_conflict_with_review(db.scope, new_bearer, changed_request)
        assert request_conflict.value.code.value == "evidence_conflict"
        assert (_claim_db_state(db, a_id), _claim_db_state(db, b_id),
                _conflict_db_state(db, conflict.id)) == before
    assert repo.resolve_conflict_with_review(db.scope, new_bearer, resolve) == resolved
    assert (_claim_db_state(db, a_id), _claim_db_state(db, b_id),
            _conflict_db_state(db, conflict.id)) == before

    # 三个通用 copy 入口的原 operation 也先按指纹拒绝 changed expected。
    with pytest.raises(EvidenceConflictError) as append_expected_conflict:
        repo.append_claim_version(db.scope, replace(
            review_submit, expected_version=review_submit.expected_version + 1))
    assert append_expected_conflict.value.code.value == "evidence_conflict"
    with pytest.raises(EvidenceConflictError) as begin_expected_conflict:
        repo.begin_claim_revision(db.scope, new_bearer, replace(
            begin, expected_version=begin.expected_version + 1))
    assert begin_expected_conflict.value.code.value == "evidence_conflict"
    with pytest.raises(EvidenceConflictError) as review_expected_conflict:
        repo.record_claim_review(db.scope, new_bearer, replace(
            rejected_request, expected_version=rejected_request.expected_version + 1))
    assert review_expected_conflict.value.code.value == "evidence_conflict"
    assert (_claim_db_state(db, a_id), _claim_db_state(db, b_id),
            _conflict_db_state(db, conflict.id)) == before
    assert repo.append_claim_version(db.scope, review_submit) == in_review
    assert repo.begin_claim_revision(db.scope, new_bearer, begin) == reopened
    assert repo.record_claim_review(db.scope, new_bearer, rejected_request) == rejected

    # 两份持久指纹彼此漂移也属于历史损坏，不能误报本次请求变化。
    with db.admin.begin() as connection:
        connection.execute(text(
            "UPDATE dayu_platform.claim_conflicts SET resolution_operation_fingerprint=:sha WHERE id=:id"
        ), {"sha": "0" * 64, "id": conflict.id})
    with pytest.raises(EvidenceRepositoryError) as fingerprint_drift:
        repo.resolve_conflict_with_review(db.scope, new_bearer, resolve)
    assert type(fingerprint_drift.value) is EvidenceRepositoryError
    assert fingerprint_drift.value.code.value == "evidence_storage_failure"
    assert (_claim_db_state(db, a_id), _claim_db_state(db, b_id)) == before[:2]
    with db.admin.begin() as connection:
        connection.execute(text(
            "UPDATE dayu_platform.claim_conflicts c SET resolution_operation_fingerprint=v.operation_fingerprint "
            "FROM dayu_platform.claim_versions v WHERE c.id=:id AND v.id=c.resolution_new_version_id "
            "AND v.tenant_id=c.tenant_id AND v.company_id=c.company_id"
        ), {"id": conflict.id})
    assert (_claim_db_state(db, a_id), _claim_db_state(db, b_id),
            _conflict_db_state(db, conflict.id)) == before
    assert repo.resolve_conflict_with_review(db.scope, new_bearer, resolve) == resolved

    with db.admin.begin() as connection:
        connection.execute(text(
            "UPDATE dayu_platform.claim_conflicts SET resolution_policy='drift' WHERE id=:id"
        ), {"id": conflict.id})
    with pytest.raises(EvidenceRepositoryError) as stored_drift:
        repo.resolve_conflict_with_review(db.scope, new_bearer, resolve)
    assert type(stored_drift.value) is EvidenceRepositoryError
    assert stored_drift.value.code.value == "evidence_storage_failure"
    assert (_claim_db_state(db, a_id), _claim_db_state(db, b_id)) == before[:2]


def test_repository_terminal_review_and_bearer_reopen_edges(
    repository_database: _RepositoryDatabase,
) -> None:
    """PG reviewer 到终态后由 bearer 重开，普通 append 不能越过终态门。

    Args:
        repository_database: 随机 app-role PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 状态边或失败事务持久行漂移。
    """

    db = repository_database
    repo = db.repository
    locator = _repo_locator()
    for terminal in (ClaimStatus.REJECTED, ClaimStatus.INVALIDATED,
                     ClaimStatus.SUPERSEDED):
        claim_id = uuid4()
        link = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                   security_id=db.security_a, locator=locator)
        draft = repo.create_claim(db.scope, ClaimCreateRequest(
            claim_id, db.company, uuid4(), _content(ClaimStatus.DRAFT),
            EvidenceSelection((link,), False), db.user, uuid4()))
        if terminal is ClaimStatus.REJECTED:
            before_draft_failure = _claim_db_state(db, claim_id)
            ordinary_review_required = ClaimVersionAppendRequest(
                claim_id, 1, uuid4(), _content(ClaimStatus.REVIEW_REQUIRED),
                EvidenceSelection(None, True), db.user, uuid4())
            with pytest.raises(EvidenceInputError):
                repo.append_claim_version(db.scope, ordinary_review_required)
            assert _claim_db_state(db, claim_id) == before_draft_failure
            assert repo.get_claim(db.scope, claim_id) == draft
        in_review = repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
            claim_id, 1, uuid4(), _content(ClaimStatus.IN_REVIEW),
            EvidenceSelection(None, True), db.user, uuid4()))
        if terminal is ClaimStatus.REJECTED:
            reached = repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
                claim_id, 2, uuid4(), _content(ClaimStatus.REJECTED),
                EvidenceSelection(None, True), "rejected evidence", uuid4()))
        else:
            approved = repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
                claim_id, 2, uuid4(), _content(
                    ClaimStatus.APPROVED,
                    valid_until=datetime.now(timezone.utc) + timedelta(minutes=5)),
                EvidenceSelection(None, True), "approved evidence", uuid4()))
            if terminal is ClaimStatus.INVALIDATED:
                reached = repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
                    claim_id, 3, uuid4(), _content(ClaimStatus.INVALIDATED),
                    EvidenceSelection(None, True), "source invalidated", uuid4()))
            else:
                review_required = repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
                    claim_id, 3, uuid4(), _content(ClaimStatus.REVIEW_REQUIRED),
                    EvidenceSelection(None, True), "follow-up required", uuid4()))
                reached = repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
                    claim_id, 4, uuid4(), _content(ClaimStatus.SUPERSEDED),
                    EvidenceSelection(None, True), "superseding disclosure", uuid4()))
                assert review_required.current.content.status is ClaimStatus.REVIEW_REQUIRED
            assert approved.current.content.status is ClaimStatus.APPROVED
        assert in_review.version == 2
        assert reached.current.content.status is terminal
        assert reached.current.reviewer is not None
        before_failure = _claim_db_state(db, claim_id)
        with pytest.raises(EvidenceInputError):
            repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
                claim_id, reached.version, uuid4(),
                _content(ClaimStatus.DRAFT, statement="Ordinary terminal bypass"),
                EvidenceSelection(None, True), db.user, uuid4()))
        assert _claim_db_state(db, claim_id) == before_failure
        assert repo.get_claim(db.scope, claim_id) == reached
        if terminal in (ClaimStatus.INVALIDATED, ClaimStatus.SUPERSEDED):
            reopened = repo.begin_claim_revision(db.scope, db.bearer, ClaimRevisionBeginRequest(
                claim_id, reached.version, uuid4(),
                _content(ClaimStatus.DRAFT, statement="New disclosure"),
                EvidenceSelection(None, True), "new disclosure", uuid4()))
            assert reopened.version == reached.version + 1
            assert reopened.current.content.status is ClaimStatus.DRAFT
            assert reopened.current.author_auth is not None
            assert reopened.current.author_user_id == db.user
            assert repo.get_claim(db.scope, claim_id) == reopened


def test_repository_approval_local_eligibility_and_expiry(repository_database: _RepositoryDatabase) -> None:
    """真 PG 验 approved 只局部 ready，过期首次读取追加系统版本。

    Args:
        repository_database: 随机 app-role PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 时间 gate 或 Fins 边界漂移。
    """

    db, locator = repository_database, _repo_locator()
    repo = db.repository
    claim_id = uuid4()
    direct = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                 security_id=db.security_a, locator=locator)
    repo.create_claim(db.scope, ClaimCreateRequest(
        claim_id, db.company, uuid4(), _content(ClaimStatus.DRAFT),
        EvidenceSelection((direct,), False), db.user, uuid4()))
    repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
        claim_id, 1, uuid4(), _content(ClaimStatus.IN_REVIEW),
        EvidenceSelection(None, True), db.user, uuid4()))
    approved = repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
        claim_id, 2, uuid4(), _content(ClaimStatus.APPROVED,
                                     valid_until=datetime.now(timezone.utc) + timedelta(seconds=2)),
        EvidenceSelection(None, True), "evidence checked", uuid4()))
    assert approved.current.content.status is ClaimStatus.APPROVED
    assert repo.local_claim_eligibility(db.scope, claim_id).reason.value == "locally_ready_requires_fins_validation"
    sleep(2.1)
    with pytest.raises(EvidenceMaterializationNeededError):
        repo.begin_claim_revision(db.scope, db.bearer, ClaimRevisionBeginRequest(
            claim_id, 3, uuid4(), _content(ClaimStatus.DRAFT),
            EvidenceSelection(None, True), "expired source", uuid4()))
    expired = repo.local_claim_eligibility(db.scope, claim_id)
    assert expired.reason.value == "expired"
    materialized = repo.get_claim(db.scope, claim_id)
    assert materialized is not None
    assert materialized.version == 4
    assert materialized.current.content.status is ClaimStatus.REVIEW_REQUIRED
    assert repo.get_claim(db.scope, claim_id) == materialized
    with pytest.raises(EvidenceOptimisticConflictError):
        repo.begin_claim_revision(db.scope, db.bearer, ClaimRevisionBeginRequest(
            claim_id, 3, uuid4(), _content(ClaimStatus.DRAFT),
            EvidenceSelection(None, True), "stale approved", uuid4()))


@pytest.mark.parametrize("target_on_left", (True, False))
def test_repository_local_eligibility_matches_historical_conflict_endpoints(
    repository_database: _RepositoryDatabase, target_on_left: bool,
) -> None:
    """局部资格匹配两侧历史端点，并忽略无关及 nonmaterial 冲突。

    Args:
        repository_database: 独占随机 PG16 句柄。
        target_on_left: 为真时目标历史版本是规范排序后的左端点。
    Returns:
        无。
    Raises:
        AssertionError: 历史范围、冲突过滤、优先级或只读语义漂移。
    """

    db, repo, locator = repository_database, repository_database.repository, _repo_locator()
    target, peer, unrelated_a, unrelated_b = (uuid4() for _ in range(4))
    first, second = sorted((uuid4(), uuid4()))
    target_v1, peer_v1 = (first, second) if target_on_left else (second, first)
    unrelated_a_v1, unrelated_b_v1 = uuid4(), uuid4()
    for claim_id, version_id in ((target, target_v1), (peer, peer_v1),
                                  (unrelated_a, unrelated_a_v1),
                                  (unrelated_b, unrelated_b_v1)):
        repo.create_claim(db.scope, ClaimCreateRequest(
            claim_id, db.company, version_id, _content(ClaimStatus.DRAFT),
            EvidenceSelection((EvidenceLinkRequest(
                uuid4(), EvidenceRelation.SUPPORTS,
                security_id=db.security_a, locator=locator),), False), db.user, uuid4()))
    for expected_version in (1, 2):
        repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
            target, expected_version, uuid4(),
            _content(ClaimStatus.DRAFT, statement=f"Revenue revision {expected_version}"),
            EvidenceSelection(None, True), db.user, uuid4()))
    repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
        target, 3, uuid4(), _content(ClaimStatus.IN_REVIEW),
        EvidenceSelection(None, True), db.user, uuid4()))
    approved = repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
        target, 4, uuid4(), _content(ClaimStatus.APPROVED,
                                  valid_until=datetime.now(timezone.utc) + timedelta(minutes=5)),
        EvidenceSelection(None, True), "approved", uuid4()))
    unrelated_left, unrelated_right = sorted((unrelated_a_v1, unrelated_b_v1))
    repo.open_conflict(db.scope, ClaimConflictOpenRequest(
        uuid4(), db.company, unrelated_left, unrelated_right, True, "unrelated", uuid4()))
    nonmaterial_left, nonmaterial_right = sorted((approved.current.id, peer_v1))
    repo.open_conflict(db.scope, ClaimConflictOpenRequest(
        uuid4(), db.company, nonmaterial_left, nonmaterial_right, False, "nonmaterial", uuid4()))
    before = _claim_db_state(db, target)
    assert repo.local_claim_eligibility(db.scope, target).reason.value == "locally_ready_requires_fins_validation"
    assert _claim_db_state(db, target) == before
    historical = repo.open_conflict(db.scope, ClaimConflictOpenRequest(
        uuid4(), db.company, first, second, True, "historical material", uuid4()))
    assert (historical.left_version_id if target_on_left else historical.right_version_id) == target_v1
    assert target_v1 != approved.current.id
    assert repo.local_claim_eligibility(db.scope, target).reason.value == "material_conflict"
    assert repo.local_claim_eligibility(db.scope, peer).reason.value == "material_conflict"
    assert _claim_db_state(db, target) == before


def test_repository_auth_revocation_and_same_actor_retry(repository_database: _RepositoryDatabase) -> None:
    """真 PG 验无 grant 可 begin、旧 token 撤销拒绝和新 token 同主体重试。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: bearer/RBAC/幂等边界漂移。
    """

    db, repo, locator = repository_database, repository_database.repository, _repo_locator()
    claim_id = uuid4()
    link = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                               security_id=db.security_a, locator=locator)
    repo.create_claim(db.scope, ClaimCreateRequest(
        claim_id, db.company, uuid4(), _content(ClaimStatus.DRAFT),
        EvidenceSelection((link,), False), db.user, uuid4()))
    repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
        claim_id, 1, uuid4(), _content(ClaimStatus.IN_REVIEW),
        EvidenceSelection(None, True), db.user, uuid4()))
    repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
        claim_id, 2, uuid4(), _content(ClaimStatus.REJECTED),
        EvidenceSelection(None, True), "review rejected", uuid4()))
    with db.admin.begin() as connection:
        connection.execute(text("DELETE FROM dayu_platform.role_permissions WHERE id=:id"),
                           {"id": db.role_permission})
    with pytest.raises(EvidenceUnauthorizedError):
        repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
            claim_id, 3, uuid4(), _content(ClaimStatus.REVIEW_REQUIRED),
            EvidenceSelection(None, True), "grant absent", uuid4()))
    begin = ClaimRevisionBeginRequest(
        claim_id, 3, uuid4(), _content(ClaimStatus.DRAFT, statement="New disclosure"),
        EvidenceSelection(None, True), "new disclosure", uuid4())
    reopened = repo.begin_claim_revision(db.scope, db.bearer, begin)
    assert reopened.current.author_user_id == db.user
    wrong_hint = Principal(TenantId(str(uuid4())), "spoofed").to_scope()
    with pytest.raises(EvidenceUnauthorizedError):
        repo.begin_claim_revision(wrong_hint, db.bearer, begin)
    with db.admin.begin() as connection:
        connection.execute(text(
            "UPDATE dayu_platform.api_tokens SET status='revoked' WHERE id=:id"
        ), {"id": db.token})
    with pytest.raises(EvidenceUnauthorizedError):
        repo.begin_claim_revision(db.scope, db.bearer, begin)
    new_bearer, new_token = secrets.token_urlsafe(32).encode("ascii"), uuid4()
    with db.admin.begin() as connection:
        connection.execute(text(
            "INSERT INTO dayu_platform.api_tokens(id,tenant_id,user_id,name,token_hash,status,expires_at) "
            "VALUES (:id,:tenant,:user,'replacement',:hash,'active',statement_timestamp()+interval '1 hour')"
        ), {"id": new_token, "tenant": _TENANT, "user": db.user,
            "hash": hashlib.sha256(new_bearer).hexdigest()})
    assert repo.begin_claim_revision(db.scope, new_bearer, begin) == reopened
    with pytest.raises(EvidenceConflictError):
        repo.begin_claim_revision(db.scope, new_bearer,
                                  replace(begin, revision_reason="different reason"))


def test_repository_expired_approved_conflict_requires_materialization(
    repository_database: _RepositoryDatabase,
) -> None:
    """过期 physical approved 不得在 conflict resolve 中跳过系统 expiry 版。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 过期/冲突状态入口漂移。
    """

    db, locator = repository_database, _repo_locator()
    repo = db.repository
    fact_id = uuid4()
    repo.create_fact(db.scope, FactCreateRequest(
        fact_id, db.company, db.security_a, uuid4(), 1, None, "margin", "margin",
        locator, FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("4"),
                           unit_code="percent"),
        FactPitTimes(None, None, _WHEN, _WHEN, _WHEN, _WHEN),
        "extractor-v1", VerificationStatus.UNVERIFIED, None, None, uuid4()))
    a_id, b_id, a_v1, b_v1 = (uuid4() for _ in range(4))
    direct_a = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                   security_id=db.security_a, locator=locator)
    direct_b = EvidenceLinkRequest(uuid4(), EvidenceRelation.CONTRADICTS,
                                   security_id=db.security_b, locator=locator)
    repo.create_claim(db.scope, ClaimCreateRequest(
        a_id, db.company, a_v1, _content(ClaimStatus.DRAFT),
        EvidenceSelection((direct_a,), False), db.user, uuid4()))
    repo.create_claim(db.scope, ClaimCreateRequest(
        b_id, db.company, b_v1, _content(ClaimStatus.DRAFT),
        EvidenceSelection((direct_b,), False), db.user, uuid4()))
    repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
        a_id, 1, uuid4(), _content(ClaimStatus.IN_REVIEW),
        EvidenceSelection(None, True), db.user, uuid4()))
    approved = repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
        a_id, 2, uuid4(), _content(ClaimStatus.APPROVED,
                                   valid_until=datetime.now(timezone.utc) + timedelta(seconds=2)),
        EvidenceSelection(None, True), "approved", uuid4()))
    left, right = sorted((approved.current.id, b_v1))
    conflict = repo.open_conflict(db.scope, ClaimConflictOpenRequest(
        uuid4(), db.company, left, right, True, "material", uuid4()))
    new_fact_link = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS, fact_id=fact_id)
    replacement = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                      security_id=db.security_a, locator=locator)
    resolve = ClaimConflictResolveRequest(
        conflict.id, a_id, 3, 1, 1, uuid4(), new_fact_link.id,
        _content(ClaimStatus.REVIEW_REQUIRED),
        EvidenceSelection((replacement, new_fact_link), False),
        "new fact", uuid4())
    sleep(2.1)
    with pytest.raises(EvidenceMaterializationNeededError):
        repo.resolve_conflict_with_review(db.scope, db.bearer, resolve)
    materialized = repo.get_claim(db.scope, a_id)
    assert materialized is not None and materialized.version == 4
    with pytest.raises(EvidenceOptimisticConflictError):
        repo.resolve_conflict_with_review(db.scope, db.bearer, resolve)


def test_repository_same_lineage_conflict_checks_both_tokens(
    repository_database: _RepositoryDatabase,
) -> None:
    """同 lineage 两个 conflict endpoint 的两个 expected token 都核当前 head。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 同 lineage 双 CAS 被绕过。
    """

    db, locator = repository_database, _repo_locator()
    claim_id, v1 = uuid4(), uuid4()
    db.repository.create_claim(db.scope, ClaimCreateRequest(
        claim_id, db.company, v1, _content(ClaimStatus.DRAFT),
        EvidenceSelection((EvidenceLinkRequest(
            uuid4(), EvidenceRelation.SUPPORTS,
            security_id=db.security_a, locator=locator),), False), db.user, uuid4()))
    v2 = db.repository.append_claim_version(db.scope, ClaimVersionAppendRequest(
        claim_id, 1, uuid4(), _content(ClaimStatus.DRAFT, statement="Revised"),
        EvidenceSelection(None, True), db.user, uuid4()))
    left, right = sorted((v1, v2.current.id))
    conflict = db.repository.open_conflict(db.scope, ClaimConflictOpenRequest(
        uuid4(), db.company, left, right, True, "same lineage", uuid4()))
    assert db.repository.local_claim_eligibility(db.scope, claim_id).reason.value == "material_conflict"
    with pytest.raises(EvidenceOptimisticConflictError):
        db.repository.resolve_conflict_with_review(db.scope, db.bearer,
            ClaimConflictResolveRequest(
                conflict.id, claim_id, 2, 1, 1, uuid4(), uuid4(),
                _content(ClaimStatus.DRAFT, statement="Revised"),
                EvidenceSelection(None, True), "new target pending", uuid4()))
    assert db.repository.get_claim(db.scope, claim_id) == v2


def test_repository_approved_conflict_resolves_to_review_required(
    repository_database: _RepositoryDatabase,
) -> None:
    """有效 approved 经 reviewer conflict successor 仅进入 review_required。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: conflict 状态边或新目标身份漂移。
    """

    db, locator = repository_database, _repo_locator()
    repo = db.repository
    a_id, b_id, a_v1, b_v1 = (uuid4() for _ in range(4))
    repo.create_claim(db.scope, ClaimCreateRequest(
        a_id, db.company, a_v1, _content(ClaimStatus.DRAFT),
        EvidenceSelection((EvidenceLinkRequest(
            uuid4(), EvidenceRelation.SUPPORTS,
            security_id=db.security_a, locator=locator),), False), db.user, uuid4()))
    repo.create_claim(db.scope, ClaimCreateRequest(
        b_id, db.company, b_v1, _content(ClaimStatus.DRAFT),
        EvidenceSelection((EvidenceLinkRequest(
            uuid4(), EvidenceRelation.CONTRADICTS,
            security_id=db.security_a, locator=locator),), False), db.user, uuid4()))
    repo.append_claim_version(db.scope, ClaimVersionAppendRequest(
        a_id, 1, uuid4(), _content(ClaimStatus.IN_REVIEW),
        EvidenceSelection(None, True), db.user, uuid4()))
    approved = repo.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
        a_id, 2, uuid4(), _content(ClaimStatus.APPROVED,
                                   valid_until=datetime.now(timezone.utc) + timedelta(minutes=5)),
        EvidenceSelection(None, True), "approved", uuid4()))
    left, right = sorted((approved.current.id, b_v1))
    conflict = repo.open_conflict(db.scope, ClaimConflictOpenRequest(
        uuid4(), db.company, left, right, True, "material", uuid4()))
    new_target = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                     security_id=db.security_b, locator=locator)
    old_target = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                     security_id=db.security_a, locator=locator)
    resolved = repo.resolve_conflict_with_review(db.scope, db.bearer,
        ClaimConflictResolveRequest(
            conflict.id, a_id, 3, 1, 1, uuid4(), new_target.id,
            _content(ClaimStatus.REVIEW_REQUIRED),
            EvidenceSelection((old_target, new_target), False), "new MIC", uuid4()))
    assert resolved.status.value == "resolved"
    current = repo.get_claim(db.scope, a_id)
    assert current is not None and current.version == 4
    assert current.current.content.status is ClaimStatus.REVIEW_REQUIRED
    assert {link.request.security_id for link in current.links} == {db.security_a, db.security_b}
    assert repo.local_claim_eligibility(db.scope, a_id).reason.value == "not_approved"


def _race_get_claim(db: _RepositoryDatabase, claim_id: UUID, barrier: Barrier) -> int:
    """屏障后独立连接读取并物化同一已过期 Claim。

    Args:
        db: 随机 PG16 句柄。
        claim_id: 已批准 Claim。
        barrier: 双连接启动屏障。
    Returns:
        受控读取的 current 版号。
    Raises:
        EvidenceRepositoryError: current 不存在或漂移。
    """

    barrier.wait(timeout=10)
    snapshot = db.repository.get_claim(db.scope, claim_id)
    if snapshot is None:
        raise EvidenceRepositoryError()
    return snapshot.version


def test_repository_expiry_concurrent_one_materialization(
    repository_database: _RepositoryDatabase,
) -> None:
    """两连接同时访问过期 approved，仅追加一次系统 review_required 版。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: CAS/锁或系统 operation 去重漂移。
    """

    db, locator = repository_database, _repo_locator()
    claim_id = uuid4()
    db.repository.create_claim(db.scope, ClaimCreateRequest(
        claim_id, db.company, uuid4(), _content(ClaimStatus.DRAFT),
        EvidenceSelection((EvidenceLinkRequest(
            uuid4(), EvidenceRelation.SUPPORTS,
            security_id=db.security_a, locator=locator),), False), db.user, uuid4()))
    db.repository.append_claim_version(db.scope, ClaimVersionAppendRequest(
        claim_id, 1, uuid4(), _content(ClaimStatus.IN_REVIEW),
        EvidenceSelection(None, True), db.user, uuid4()))
    db.repository.record_claim_review(db.scope, db.bearer, ClaimReviewRequest(
        claim_id, 2, uuid4(), _content(ClaimStatus.APPROVED,
                                      valid_until=datetime.now(timezone.utc) + timedelta(seconds=2)),
        EvidenceSelection(None, True), "approved", uuid4()))
    sleep(2.1)
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(_race_get_claim, db, claim_id, barrier) for _ in range(2)]
        assert [result.result(timeout=20) for result in results] == [4, 4]
    with db.sessions() as session, session.begin():
        session.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                        {"tenant": str(_TENANT)})
        count = session.execute(text(
            "SELECT count(*) FROM dayu_platform.claim_versions WHERE claim_id=:id"
        ), {"id": claim_id}).scalar_one()
    assert count == 4


def test_repository_named_direct_duplicate_savepoint(repository_database: _RepositoryDatabase) -> None:
    """真 PG 命名 digest unique 冲突经 savepoint 后比完整 JSONB。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 冲突分类或整事务回滚漂移。
    """

    db, repo, locator = repository_database, repository_database.repository, _repo_locator()
    first_link = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                     security_id=db.security_a, locator=locator)
    version_id = uuid4()
    repo.create_claim(db.scope, ClaimCreateRequest(
        uuid4(), db.company, version_id, _content(ClaimStatus.DRAFT),
        EvidenceSelection((first_link,), False), db.user, uuid4()))
    duplicate = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                    security_id=db.security_a, locator=locator)
    with pytest.raises(EvidenceDuplicateTargetError):
        with db.sessions() as session, session.begin():
            session.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                            {"tenant": str(_TENANT)})
            evidence_repository_module._insert_links(
                session, _TENANT, db.company, version_id, (duplicate,))
    with db.sessions() as session, session.begin():
        session.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                        {"tenant": str(_TENANT)})
        count = session.execute(text(
            "SELECT count(*) FROM dayu_platform.evidence_links WHERE claim_version_id=:id"
        ), {"id": version_id}).scalar_one()
    assert count == 1
    # 同批第一条尚未提交，第二条 savepoint 失败后仍须在外层新语句可见。
    empty_version = uuid4()
    repo.create_claim(db.scope, ClaimCreateRequest(
        uuid4(), db.company, empty_version, _content(ClaimStatus.DRAFT),
        EvidenceSelection((), False), db.user, uuid4()))
    batch_first = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                      security_id=db.security_a, locator=locator)
    batch_second = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                       security_id=db.security_a, locator=locator)
    with pytest.raises(EvidenceDuplicateTargetError):
        with db.sessions() as session, session.begin():
            session.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                            {"tenant": str(_TENANT)})
            evidence_repository_module._insert_links(
                session, _TENANT, db.company, empty_version,
                (batch_first, batch_second))
    with db.sessions() as session, session.begin():
        session.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                        {"tenant": str(_TENANT)})
        count = session.execute(text(
            "SELECT count(*) FROM dayu_platform.evidence_links WHERE claim_version_id=:id"
        ), {"id": empty_version}).scalar_one()
    assert count == 0


def test_repository_digest_collision_fault_injection(
    repository_database: _RepositoryDatabase, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实命名 23505 加 digest 故障注入，异完整 JSONB 必 fail closed。

    Args:
        repository_database: 随机 PG16 句柄。
        monkeypatch: 仅替换候选 digest 计算输出的测试 seam。
    Returns:
        无。
    Raises:
        AssertionError: collision 分类或事务保护漂移。
    """

    db, locator = repository_database, _repo_locator()
    version_id = uuid4()
    db.repository.create_claim(db.scope, ClaimCreateRequest(
        uuid4(), db.company, version_id, _content(ClaimStatus.DRAFT),
        EvidenceSelection((EvidenceLinkRequest(
            uuid4(), EvidenceRelation.SUPPORTS,
            security_id=db.security_a, locator=locator),), False), db.user, uuid4()))
    changed = locator.to_dict()
    changed["document_version"] = "v2"
    other_locator = EvidenceLocatorSnapshot.from_dict(changed)
    other_link = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                     security_id=db.security_a, locator=other_locator)
    with db.sessions() as session, session.begin():
        session.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                        {"tenant": str(_TENANT)})
        digest = session.execute(text(
            "SELECT locator_index_digest FROM dayu_platform.evidence_links "
            "WHERE claim_version_id=:id"
        ), {"id": version_id}).scalar_one()
        assert type(digest) is bytes and len(digest) == 32
        with pytest.raises(IntegrityError) as caught:
            with session.begin_nested():
                session.add(EvidenceLinkRow(
                    id=uuid4(), tenant_id=_TENANT, company_id=db.company,
                    claim_version_id=version_id, relation=EvidenceRelation.SUPPORTS.value,
                    security_id=db.security_a, locator_ticker=locator.ticker,
                    locator_json=locator.to_dict(),
                ))
                session.flush()
        monkeypatch.setattr(evidence_repository_module, "_digest_for_locator",
                            partial(_forced_digest, digest))
        with pytest.raises(EvidenceDigestCollisionError):
            evidence_repository_module._raise_integrity(
                session, caught.value, _TENANT, db.company, version_id, other_link)


def test_repository_candidate_hash_drift_and_scope(repository_database: _RepositoryDatabase) -> None:
    """JSONB canonical 读回核 hash，跨租户读取为空。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: 候选 payload 完整性或 RLS 漂移。
    """

    db = repository_database
    request = ResearchCandidateCreateRequest(
        uuid4(), db.company, CandidateOrigin.HUMAN,
        b'{"nested":{"score":2},"source":"synthetic"}', uuid4())
    db.repository.create_proposed_candidate(db.scope, request)
    with pytest.raises(EvidenceConflictError):
        db.repository.create_proposed_candidate(
            db.scope, replace(request, canonical_payload_json=b'{"nested":{"score":3},"source":"synthetic"}'))
    wrong_scope = Principal(TenantId(str(uuid4())), "other").to_scope()
    assert db.repository.get_candidate(wrong_scope, request.id) is None
    with db.admin.begin() as connection:
        connection.execute(text(
            "UPDATE dayu_platform.research_candidates SET sha256=:sha WHERE id=:id"
        ), {"sha": "0" * 64, "id": request.id})
    with pytest.raises(EvidenceRepositoryError):
        db.repository.get_candidate(db.scope, request.id)


def test_repository_cross_tenant_company_target_rollback(
    repository_database: _RepositoryDatabase,
) -> None:
    """复合 FK 拒绝跨租户 Fact link 与跨公司 security，失败零中间行。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: closure 或整体回滚漂移。
    """

    db, repo, locator = repository_database, repository_database.repository, _repo_locator()
    other_tenant, other_company, other_security = uuid4(), uuid4(), uuid4()
    with db.admin.begin() as connection:
        connection.execute(text(
            "INSERT INTO dayu_platform.organizations(id,slug,display_name,status) "
            "VALUES (:id,:slug,'Other tenant','active')"
        ), {"id": other_tenant, "slug": "other-" + other_tenant.hex})
        connection.execute(text(
            "INSERT INTO dayu_platform.companies(id,legal_name) VALUES (:id,'Other company')"
        ), {"id": other_company})
        connection.execute(text(
            "INSERT INTO dayu_platform.securities(id,company_id,ticker,exchange_mic,security_type,currency) "
            "VALUES (:id,:company,'ABC','XHKG','equity','USD')"
        ), {"id": other_security, "company": other_company})
    other_scope = Principal(TenantId(str(other_tenant)), "other").to_scope()
    fact_other_tenant = FactCreateRequest(
        uuid4(), db.company, db.security_a, uuid4(), 1, None, "margin", "margin",
        locator, FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("1"),
                           unit_code="percent"),
        FactPitTimes(None, None, _WHEN, _WHEN, _WHEN, _WHEN),
        "extractor-v1", VerificationStatus.UNVERIFIED, None, None, uuid4())
    repo.create_fact(other_scope, fact_other_tenant)
    assert repo.get_fact(db.scope, fact_other_tenant.id) is None
    claim_id = uuid4()
    with pytest.raises(EvidenceConflictError):
        repo.create_claim(db.scope, ClaimCreateRequest(
            claim_id, db.company, uuid4(), _content(ClaimStatus.DRAFT),
            EvidenceSelection((EvidenceLinkRequest(
                uuid4(), EvidenceRelation.SUPPORTS, fact_id=fact_other_tenant.id),), False),
            db.user, uuid4()))
    assert repo.get_claim(db.scope, claim_id) is None
    wrong_company_fact = replace(fact_other_tenant, id=uuid4(), security_id=other_security,
                                 operation_id=uuid4())
    with pytest.raises(EvidenceConflictError):
        repo.create_fact(db.scope, wrong_company_fact)
    assert repo.get_fact(db.scope, wrong_company_fact.id) is None
    wrong_direct_claim = uuid4()
    with pytest.raises(EvidenceConflictError):
        repo.create_claim(db.scope, ClaimCreateRequest(
            wrong_direct_claim, db.company, uuid4(), _content(ClaimStatus.DRAFT),
            EvidenceSelection((EvidenceLinkRequest(
                uuid4(), EvidenceRelation.SUPPORTS,
                security_id=other_security, locator=locator),), False),
            db.user, uuid4()))
    assert repo.get_claim(db.scope, wrong_direct_claim) is None


def _race_direct_link(db: _RepositoryDatabase, version_id: UUID,
                      link: EvidenceLinkRequest, barrier: Barrier) -> str:
    """并发测试中在独立 app Session 插入一条 direct link。

    Args:
        db: 随机 PG16 句柄。
        version_id: 空链接版本。
        link: 本连接待插入的 direct link。
        barrier: 双连接启动屏障。
    Returns:
        created 或 duplicate。
    Raises:
        其它持久故障原样传给主测试。
    """

    try:
        with db.sessions() as session, session.begin():
            session.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                            {"tenant": str(_TENANT)})
            barrier.wait(timeout=10)
            evidence_repository_module._insert_links(
                session, _TENANT, db.company, version_id, (link,))
        return "created"
    except EvidenceDuplicateTargetError:
        return "duplicate"


def _forced_digest(digest: bytes, _session: Session,
                   _locator: EvidenceLocatorSnapshot) -> bytes:
    """仅模拟候选 SHA 碰撞，不更改 PG trigger/constraint。

    Args:
        digest: 已持久化 L1 的 digest。
        _session: 未使用的当前事务。
        _locator: 未使用的候选 locator。
    Returns:
        注入的 32-byte digest。
    Raises:
        无。
    """

    return digest


def test_repository_direct_digest_concurrent_same_and_different_security(
    repository_database: _RepositoryDatabase,
) -> None:
    """两连接证实同证券 duplicate 单胜、不同证券同 locator 双胜。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: unique scope 或并发分类漂移。
    """

    db, locator = repository_database, _repo_locator()
    for same_security in (True, False):
        version_id = uuid4()
        db.repository.create_claim(db.scope, ClaimCreateRequest(
            uuid4(), db.company, version_id, _content(ClaimStatus.DRAFT),
            EvidenceSelection((), False), db.user, uuid4()))
        left = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                   security_id=db.security_a, locator=locator)
        right = EvidenceLinkRequest(uuid4(), EvidenceRelation.SUPPORTS,
                                    security_id=db.security_a if same_security else db.security_b,
                                    locator=locator)
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(_race_direct_link, db, version_id, left, barrier)
            second = pool.submit(_race_direct_link, db, version_id, right, barrier)
            outcomes = sorted((first.result(timeout=20), second.result(timeout=20)))
        assert outcomes == (["created", "duplicate"] if same_security else ["created", "created"])


def _race_fact_revision(db: _RepositoryDatabase,
                        request: FactCreateRequest, barrier: Barrier) -> str:
    """并发测试中用公有 repository 追加同系列同版号。

    Args:
        db: 随机 PG16 句柄。
        request: rev2 请求。
        barrier: 双连接启动屏障。
    Returns:
        created 或 conflict。
    Raises:
        其它持久故障原样传给主测试。
    """

    barrier.wait(timeout=10)
    try:
        db.repository.create_fact(db.scope, request)
        return "created"
    except EvidenceConflictError:
        return "conflict"


def test_repository_fact_revision_concurrent_cas(repository_database: _RepositoryDatabase) -> None:
    """同 series 的两连接 rev2 只一胜，链按版号闭合。

    Args:
        repository_database: 随机 PG16 句柄。
    Returns:
        无。
    Raises:
        AssertionError: advisory series lock 或 unique 裁决漂移。
    """

    db, locator = repository_database, _repo_locator()
    series, first_id = uuid4(), uuid4()
    value = FactValue(FactValueKind.DECIMAL, value_decimal=Decimal("7.25"),
                      unit_code="currency", currency="USD")
    first = FactCreateRequest(first_id, db.company, db.security_a, series, 1, None,
                              "revenue", "revenue", locator, value,
                              FactPitTimes(None, None, _WHEN, _WHEN, _WHEN, _WHEN),
                              "extractor-v1", VerificationStatus.UNVERIFIED,
                              None, None, uuid4())
    db.repository.create_fact(db.scope, first)
    requests = tuple(FactCreateRequest(
        uuid4(), db.company, db.security_a, series, 2, first_id,
        "revenue", "revenue", locator, value,
        FactPitTimes(None, None, _WHEN, _WHEN, _WHEN, _WHEN),
        "extractor-v2", VerificationStatus.UNVERIFIED, None, None, uuid4(),
    ) for _ in range(2))
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(_race_fact_revision, db, request, barrier) for request in requests]
        outcomes = sorted(result.result(timeout=20) for result in results)
    assert outcomes == ["conflict", "created"]
    revisions = db.repository.list_fact_revisions(db.scope, db.company, series)
    assert len(revisions) == 2
    shared = FactCreateRequest(
        uuid4(), db.company, db.security_a, series, 3, revisions[1].id,
        "revenue", "revenue", locator, value,
        FactPitTimes(None, None, _WHEN, _WHEN, _WHEN, _WHEN),
        "extractor-v3", VerificationStatus.UNVERIFIED, None, None, uuid4(),
    )
    retry_barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(_race_fact_revision, db, shared, retry_barrier) for _ in range(2)]
        outcomes = sorted(result.result(timeout=20) for result in results)
    assert outcomes == ["created", "created"]
    assert len(db.repository.list_fact_revisions(db.scope, db.company, series)) == 3


@contextmanager
def _migration_dsn(dsn: str) -> Iterator[None]:
    """在单次 Alembic 命令期间设置 bootstrap DSN 并恢复原值。

    Args:
        dsn: 随机测试库的 bootstrap DSN，不写入文件。

    Yields:
        供 Alembic 执行命令的环境窗口。

    Raises:
        无；被包裹命令的异常原样传播。
    """

    old = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = dsn
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = old


def test_0007_empty_upgrade_downgrade_upgrade(
    platform_cluster: PlatformCluster, lifecycle_database,
) -> None:
    """真实空库升级、回退一个 revision、再升级，核 33/30/3。

    Args:
        platform_cluster: 临时 PG16 cluster。
        lifecycle_database: 独立随机数据库工厂。

    Returns:
        无。

    Raises:
        AssertionError: 往返、外部依赖拒绝或 catalog 不符。
    """

    database = lifecycle_database()
    dsn = platform_cluster.dsn_for_database(database, "postgres")
    upgraded = False
    try:
        run_alembic_upgrade(dsn)
        upgraded = True
        engine = create_engine(dsn)
        try:
            with engine.connect() as connection:
                rows = connection.execute(text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=:schema AND c.relkind='r'"
                ), {"schema": PLATFORM_SCHEMA_NAME}).all()
                assert len(rows) == 33
                assert sum(bool(row[1]) and bool(row[2]) for row in rows) == 30
                assert connection.execute(text(
                    "SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid='dayu_platform.facts'::regclass "
                    "AND attname='value_decimal'"
                )).scalar_one() == -1
                index = connection.execute(text(
                    "SELECT pg_get_indexdef('dayu_platform.uq_evidence_links_direct_digest'::regclass)"
                )).scalar_one()
                assert "(tenant_id, claim_version_id, relation, security_id, locator_index_digest)" in index
                assert "WHERE (fact_id IS NULL)" in index
        finally:
            engine.dispose()
        engine = create_engine(dsn)
        try:
            bounded_dsn = dsn + "?options=-c%20lock_timeout%3D5s"
            for locked_table in ("facts", "securities"):
                with engine.begin() as blocker:
                    blocker.exec_driver_sql(
                        f"LOCK TABLE dayu_platform.{locked_table} IN ACCESS SHARE MODE"
                    )
                    started = monotonic()
                    with _migration_dsn(bounded_dsn), pytest.raises(DBAPIError) as caught:
                        command.downgrade(_alembic_config(), "-1")
                    assert isinstance(caught.value.orig, PsycopgError)
                    assert caught.value.orig.sqlstate == "55P03"
                    assert monotonic() - started < 3.0
                    assert blocker.execute(text(
                        "SELECT version_num FROM public.alembic_version"
                    )).scalar_one() == "0007_strict_evidence"
                    assert blocker.execute(text(
                        "SELECT to_regclass('dayu_platform.facts')"
                    )).scalar_one() is not None
                    assert blocker.execute(text(
                        "SELECT count(*) FROM pg_constraint WHERE conname = "
                        "'uq_securities_company_id_id_ticker' "
                        "AND conrelid='dayu_platform.securities'::regclass"
                    )).scalar_one() == 1
            for grant, revoke in (
                (
                    "GRANT SELECT ON TABLE dayu_platform.facts TO PUBLIC",
                    "REVOKE SELECT ON TABLE dayu_platform.facts FROM PUBLIC",
                ),
                (
                    "GRANT SELECT (id) ON TABLE dayu_platform.facts TO PUBLIC",
                    "REVOKE SELECT (id) ON TABLE dayu_platform.facts FROM PUBLIC",
                ),
                (
                    "GRANT EXECUTE ON FUNCTION dayu_platform.evidence_locator_valid(jsonb) TO PUBLIC",
                    "REVOKE EXECUTE ON FUNCTION dayu_platform.evidence_locator_valid(jsonb) FROM PUBLIC",
                ),
            ):
                with engine.begin() as connection:
                    connection.exec_driver_sql(grant)
                with _migration_dsn(dsn), pytest.raises(
                    PlatformMigrationAdmissionError, match="external_role_dependency"
                ):
                    command.downgrade(_alembic_config(), "-1")
                with engine.begin() as connection:
                    assert connection.execute(text(
                        "SELECT version_num FROM public.alembic_version"
                    )).scalar_one() == "0007_strict_evidence"
                    assert connection.execute(text(
                        "SELECT to_regclass('dayu_platform.facts')"
                    )).scalar_one() is not None
                    connection.exec_driver_sql(revoke)
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE VIEW dayu_platform.evidence_external_probe "
                    "AS SELECT id FROM dayu_platform.facts"
                )
            with _migration_dsn(dsn), pytest.raises(DBAPIError):
                command.downgrade(_alembic_config(), "-1")
            with engine.begin() as connection:
                assert connection.execute(text(
                    "SELECT version_num FROM public.alembic_version"
                )).scalar_one() == "0007_strict_evidence"
                assert connection.execute(text(
                    "SELECT to_regclass('dayu_platform.facts')"
                )).scalar_one() is not None
                connection.exec_driver_sql("DROP VIEW dayu_platform.evidence_external_probe")
        finally:
            engine.dispose()
        with _migration_dsn(dsn):
            command.downgrade(_alembic_config(), "-1")
        engine = create_engine(dsn)
        try:
            with engine.connect() as connection:
                assert connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one() == "0006_job_request_identity"
                assert connection.execute(text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=:schema AND c.relkind='r'"
                ), {"schema": PLATFORM_SCHEMA_NAME}).scalar_one() == 27
                assert connection.execute(text(
                    "SELECT to_regclass('dayu_platform.uq_securities_company_id_id_ticker')"
                )).scalar_one() is None
        finally:
            engine.dispose()
        run_alembic_upgrade(dsn)
    finally:
        if upgraded:
            run_alembic_downgrade(dsn)


def _locator(ticker: str, kind: str = "document", payload: Mapping[str, str | int] | None = None) -> str:
    """生成无需 Fins runtime 的合法 v1 projection JSON。

    Args:
        ticker: 原样 canonical ticker。
        kind: 五类 locator kind 之一。
        payload: 对应 kind 的完整 payload。

    Returns:
        Fins v1 projection JSON 文本。

    Raises:
        TypeError: 输入不可 JSON 序列化时传播。
    """

    return json.dumps({
        "repository_id": "dayu.fins.public.v1",
        "ticker": ticker,
        "document_id": "doc_1",
        "source_kind": "filing",
        "artifact_kind": "source" if kind == "document" else "processed",
        "document_version": "v1",
        "source_fingerprint": _HEX,
        "primary_content_sha256": _HEX,
        "locator_kind": kind,
        "locator_payload": {} if payload is None else payload,
        "locator_content_sha256": _HEX,
    }, sort_keys=True)


def _reject(connection: Connection, statement: str, values: dict[str, str | bytes | int | UUID | datetime | None], sqlstate: str, constraint: str | None = None) -> None:
    """在 savepoint 内证实原始 SQL 由 PG 约束拒绝。

    Args:
        connection: 已设置本地租户上下文的 app 连接。
        statement: 参数化原始 SQL。
        values: 不含真实凭据的绑定值。
        sqlstate: 预期 PostgreSQL SQLSTATE。
        constraint: 可选的精确命名约束。

    Returns:
        无。

    Raises:
        AssertionError: PG 未按预期拒绝或命中错误约束。
    """

    savepoint = connection.begin_nested()
    try:
        with pytest.raises(DBAPIError) as caught:
            connection.execute(text(statement), values)
        assert isinstance(caught.value.orig, PsycopgError)
        assert caught.value.orig.sqlstate == sqlstate
        if constraint is not None:
            assert caught.value.orig.diag.constraint_name == constraint
    finally:
        savepoint.rollback()


def test_0007_app_role_raw_sql_rejections_and_dual_mic(
    platform_cluster: PlatformCluster, lifecycle_database,
) -> None:
    """app role 原始 INSERT 覆盖三值 NULL、ticker、decimal 与双 MIC。

    Args:
        platform_cluster: 临时 PG16 cluster。
        lifecycle_database: 独立随机数据库工厂。

    Returns:
        无。

    Raises:
        AssertionError: PG 原始 SQL 约束、权限或回退 admission 漂移。
    """

    database = lifecycle_database()
    dsn = platform_cluster.dsn_for_database(database, "postgres")
    company, other_company = uuid4(), uuid4()
    security_a, security_b, security_other = uuid4(), uuid4(), uuid4()
    actor, claim, version, fact = uuid4(), uuid4(), uuid4(), uuid4()
    run_alembic_upgrade(dsn)
    login = None
    try:
        bootstrap = create_engine(dsn)
        try:
            with bootstrap.begin() as connection:
                connection.execute(text("INSERT INTO dayu_platform.companies(id, legal_name) VALUES (:id, 'A'), (:other, 'B')"), {"id": company, "other": other_company})
                connection.execute(text(
                    "INSERT INTO dayu_platform.securities(id,company_id,ticker,exchange_mic,security_type,currency) VALUES "
                    "(:a,:company,'ABC','XNAS','equity','USD'),"
                    "(:b,:company,'ABC','XNYS','equity','USD'),"
                    "(:c,:other,'XYZ','XNAS','equity','USD')"
                ), {"a": security_a, "b": security_b, "c": security_other, "company": company, "other": other_company})
                connection.execute(text(
                    "INSERT INTO dayu_platform.users(id,tenant_id,subject,display_name,status) "
                    "VALUES (:id,:tenant,'evidence-author','Author','active')"
                ), {"id": actor, "tenant": _TENANT})
                connection.execute(text(
                    "INSERT INTO dayu_platform.claims(id,tenant_id,company_id) VALUES (:id,:tenant,:company)"
                ), {"id": claim, "tenant": _TENANT, "company": company})
                connection.execute(text(
                    "INSERT INTO dayu_platform.claim_versions "
                    "(id,tenant_id,company_id,claim_id,version_no,transition_kind,evidence_mode,operation_id,operation_fingerprint,statement,confidence_band,impact_horizon,status,invalidation_rule,author_user_id) "
                    "VALUES (:id,:tenant,:company,:claim,1,'claim_create','replace_all',:op,:fingerprint,'Revenue grows','medium','long','draft','revise',:actor)"
                ), {"id": version, "tenant": _TENANT, "company": company, "claim": claim, "op": uuid4(), "fingerprint": _HEX, "actor": actor})
        finally:
            bootstrap.dispose()
        login = create_temporary_login(platform_cluster, database, member_of=PLATFORM_APP_ROLE)
        engine = create_engine(login.dsn)
        try:
            with engine.connect() as connection:
                assert connection.execute(text("SELECT count(*) FROM dayu_platform.facts")).scalar_one() == 0
            fact_sql = (
                "INSERT INTO dayu_platform.facts "
                "(id,tenant_id,company_id,security_id,locator_ticker,locator_json,fact_series_id,revision_no,fact_key,metric,value_kind,value_decimal,unit_code,currency,effective_at,published_at,ingested_at,available_at,extractor_version,verification_status,operation_id,operation_fingerprint) "
                "VALUES (:id,:tenant,:company,:security,:ticker,CAST(:locator AS jsonb),:series,1,'revenue','revenue','decimal',CAST(:value AS numeric),:unit,:currency,:at,:at,:at,:at,'extractor-v1','unverified',:op,:fingerprint)"
            )
            with engine.begin() as connection:
                connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(_TENANT)})
                valid_locators: list[str] = []
                for kind, payload in (
                    ("document", {}),
                    ("page", {"page_no": 1}),
                    ("section", {"section_ref": "sec_1"}),
                    ("table_cell", {"table_ref": "table_1", "row_index": 0, "column": "Revenue"}),
                    ("xbrl_fact", {"concept": "us-gaap:Revenue", "fact_sha256": _HEX}),
                ):
                    locator = _locator("ABC", kind, payload)
                    parse_evidence_locator_projection(json.loads(locator))
                    valid_locators.append(locator)
                    assert connection.execute(text(
                        "SELECT dayu_platform.evidence_locator_valid(CAST(:locator AS jsonb))"
                    ), {"locator": locator}).scalar_one() is True
                assert connection.execute(text(
                    "SELECT dayu_platform.evidence_locator_valid(CAST(:locator AS jsonb))"
                ), {"locator": _locator("ABC", "page", {"page_no": -1})}).scalar_one() is False
                for kind, payload, key, padding in (
                    ("document", {}, "document_version", "\t"),
                    ("section", {"section_ref": "sec_1"}, "section_ref", "\u00a0"),
                    ("table_cell", {"table_ref": "table_1", "row_index": 0, "column": "Revenue"}, "table_ref", "\u2003"),
                    ("table_cell", {"table_ref": "table_1", "row_index": 0, "column": "Revenue"}, "column", "\t"),
                    ("xbrl_fact", {"concept": "us-gaap:Revenue", "fact_sha256": _HEX}, "concept", "\u00a0"),
                ):
                    invalid_locator = json.loads(_locator("ABC", kind, payload))
                    target = invalid_locator if key == "document_version" else invalid_locator["locator_payload"]
                    target[key] = padding + target[key]
                    with pytest.raises(EvidenceLocatorError):
                        parse_evidence_locator_projection(invalid_locator)
                    assert connection.execute(text(
                        "SELECT dayu_platform.evidence_locator_valid(CAST(:locator AS jsonb))"
                    ), {"locator": json.dumps(invalid_locator)}).scalar_one() is False
                base: dict[str, str | bytes | UUID | datetime | None] = {
                    "id": fact, "tenant": _TENANT, "company": company,
                    "security": security_a, "ticker": "ABC", "locator": _locator("ABC"),
                    "series": uuid4(), "value": "99999999999999999999999999.999999999999",
                    "unit": "currency", "currency": "USD",
                    "at": _WHEN, "op": uuid4(), "fingerprint": _HEX,
                }
                connection.execute(text(fact_sql), base)
                long_locator = _locator("ABC", "section", {
                    "section_ref": "".join(uuid4().hex for _ in range(250)),
                })
                parse_evidence_locator_projection(json.loads(long_locator))
                assert len(long_locator.encode()) > 8000
                for locator in (*valid_locators, long_locator):
                    fact_id = uuid4()
                    connection.execute(text(fact_sql), {
                        **base, "id": fact_id, "series": uuid4(), "op": uuid4(),
                        "locator": locator,
                    })
                    stored = connection.execute(text(
                        "SELECT locator_json::text FROM dayu_platform.facts WHERE id=:id"
                    ), {"id": fact_id}).scalar_one()
                    assert json.loads(stored) == json.loads(locator)
                roundtrip = connection.execute(text(
                    "SELECT value_decimal::text FROM dayu_platform.facts WHERE id=:id"
                ), {"id": fact}).scalar_one()
                assert roundtrip == base["value"]
                negative_id = uuid4()
                connection.execute(text(fact_sql), {
                    **base, "id": negative_id, "series": uuid4(), "op": uuid4(),
                    "value": "-" + str(base["value"]),
                })
                assert connection.execute(text(
                    "SELECT value_decimal::text FROM dayu_platform.facts WHERE id=:id"
                ), {"id": negative_id}).scalar_one() == "-" + str(base["value"])
                for changes, state, name in (
                    ({"security": None}, "23502", None),
                    ({"ticker": None}, "23502", None),
                    ({"locator": None}, "23502", None),
                    ({"locator": _locator("XYZ")}, "23514", "ck_facts_locator_ticker"),
                    ({"unit": None}, "23514", "ck_facts_unit_shape"),
                    ({"currency": None}, "23514", "ck_facts_unit_shape"),
                    ({"currency": "usd"}, "23514", "ck_facts_unit_shape"),
                    ({"value": "1.0000000000001"}, "23514", "ck_facts_decimal_bound"),
                    ({"value": "9" * 39}, "23514", "ck_facts_decimal_bound"),
                    ({"value": "NaN"}, "23514", "ck_facts_decimal_bound"),
                    ({"value": "Infinity"}, "23514", "ck_facts_decimal_bound"),
                    ({"value": "-Infinity"}, "23514", "ck_facts_decimal_bound"),
                ):
                    candidate = {**base, **changes, "id": uuid4(), "series": uuid4(), "op": uuid4()}
                    _reject(connection, fact_sql, candidate, state, name)
                invalid_fact_locator = json.loads(_locator("ABC"))
                invalid_fact_locator["document_version"] = "\t" + invalid_fact_locator["document_version"]
                _reject(connection, fact_sql, {
                    **base, "id": uuid4(), "series": uuid4(), "op": uuid4(),
                    "locator": json.dumps(invalid_fact_locator),
                }, "23514", "ck_facts_locator")
                link_sql = (
                    "INSERT INTO dayu_platform.evidence_links "
                    "(id,tenant_id,company_id,claim_version_id,relation,fact_id,security_id,locator_ticker,locator_json,locator_index_digest) "
                    "VALUES (:id,:tenant,:company,:version,:relation,:fact,:security,:ticker,CAST(:locator AS jsonb),:digest)"
                )
                link_base: dict[str, str | bytes | UUID | datetime | None] = {
                    "id": uuid4(), "tenant": _TENANT, "company": company,
                    "version": version, "relation": "supports", "fact": None, "security": security_a,
                    "ticker": "ABC", "locator": _locator("ABC"), "digest": b"caller-wrong",
                }
                connection.execute(text(link_sql), link_base)
                connection.execute(text(link_sql), {**link_base, "id": uuid4(), "security": security_b})
                digests = connection.execute(text(
                    "SELECT security_id, locator_index_digest, "
                    "sha256(convert_to(locator_json::text,'UTF8')) "
                    "FROM dayu_platform.evidence_links WHERE claim_version_id=:version "
                    "AND fact_id IS NULL ORDER BY security_id"
                ), {"version": version}).all()
                assert len(digests) == 2
                assert digests[0][1] == digests[1][1]
                assert all(len(row[1]) == 32 and row[1] == row[2] for row in digests)
                for locator in (*valid_locators, long_locator):
                    link_id = uuid4()
                    connection.execute(text(link_sql), {
                        **link_base, "id": link_id, "relation": "context",
                        "locator": locator,
                    })
                    stored = connection.execute(text(
                        "SELECT locator_json::text FROM dayu_platform.evidence_links WHERE id=:id"
                    ), {"id": link_id}).scalar_one()
                    assert json.loads(stored) == json.loads(locator)
                _reject(connection, link_sql, {**link_base, "id": uuid4()}, "23505", "uq_evidence_links_direct_digest")
                for changes, state, name in (
                    ({"fact": fact, "security": security_b, "ticker": "ABC", "locator": None}, "23514", "ck_evidence_links_target_arm"),
                    ({"fact": fact, "security": None, "ticker": "ABC", "locator": None}, "23514", "ck_evidence_links_target_arm"),
                    ({"ticker": None}, "23514", "ck_evidence_links_target_arm"),
                    ({"ticker": "ABC", "locator": _locator("XYZ")}, "23514", "ck_evidence_links_target_arm"),
                    ({"company": other_company, "relation": "contradicts"}, "23503", "fk_evidence_links_version"),
                    ({"security": security_other, "ticker": "XYZ", "locator": _locator("XYZ"), "relation": "contradicts"}, "23503", "fk_evidence_links_security_ticker"),
                ):
                    _reject(connection, link_sql, {**link_base, **changes, "id": uuid4()}, state, name)
                invalid_link_locator = json.loads(_locator("ABC", "section", {"section_ref": "sec_1"}))
                invalid_link_locator["locator_payload"]["section_ref"] += "\u00a0"
                _reject(connection, link_sql, {
                    **link_base, "id": uuid4(), "relation": "context",
                    "locator": json.dumps(invalid_link_locator),
                }, "23514", "ck_evidence_links_locator")
                connection.execute(text(link_sql), {
                    **link_base, "id": uuid4(), "fact": fact, "security": None,
                    "ticker": None, "locator": None, "digest": b"wrong",
                })
                assert connection.execute(text(
                    "SELECT count(*) FROM dayu_platform.evidence_links "
                    "WHERE claim_version_id=:version AND fact_id=:fact "
                    "AND locator_index_digest IS NULL AND security_id IS NULL "
                    "AND locator_ticker IS NULL AND locator_json IS NULL"
                ), {"version": version, "fact": fact}).scalar_one() == 1
                assert connection.execute(text(
                    "SELECT count(*) FROM dayu_platform.evidence_links WHERE claim_version_id=:version"
                ), {"version": version}).scalar_one() == 9
                version_sql = (
                    "INSERT INTO dayu_platform.claim_versions "
                    "(id,tenant_id,company_id,claim_id,version_no,transition_kind,evidence_mode,copy_source_version_id,operation_id,operation_fingerprint,statement,confidence_band,impact_horizon,status,invalidation_rule,transition_reason,author_user_id) "
                    "VALUES (:id,:tenant,:company,:claim,:number,:action,:mode,:source,:op,:fingerprint,'Revenue grows','medium','long',:status,'revise',:reason,:author)"
                )
                ordinary: dict[str, str | bytes | int | UUID | datetime | None] = {
                    "id": uuid4(), "tenant": _TENANT, "company": company,
                    "claim": claim, "number": 2, "action": "content_revision",
                    "mode": "replace_all", "source": None, "op": uuid4(),
                    "fingerprint": _HEX, "status": "draft", "reason": None,
                    "author": None,
                }
                connection.execute(text(version_sql), ordinary)
                for changes, state, name in (
                    ({"action": "claim_create"}, "23514", "ck_claim_versions_first_version"),
                    ({"action": "begin_revision", "reason": "revise"}, "23514", "ck_claim_versions_action_witness"),
                    ({"action": "expiry", "status": "review_required"}, "23514", "ck_claim_versions_action_witness"),
                    ({"action": "review_decision", "status": "approved"}, "23514", "ck_claim_versions_action_witness"),
                    ({"mode": "copy_previous"}, "23514", "ck_claim_versions_evidence_mode"),
                    ({"mode": "copy_previous", "source": uuid4()}, "23503", "fk_claim_versions_copy_source"),
                ):
                    _reject(connection, version_sql, {
                        **ordinary, **changes, "id": uuid4(), "number": 3, "op": uuid4(),
                    }, state, name)
                first_claim = uuid4()
                connection.execute(text(
                    "INSERT INTO dayu_platform.claims(id,tenant_id,company_id) "
                    "VALUES (:id,:tenant,:company)"
                ), {"id": first_claim, "tenant": _TENANT, "company": company})
                _reject(connection, version_sql, {
                    **ordinary, "id": uuid4(), "claim": first_claim, "number": 1,
                    "action": "claim_create", "status": "approved", "op": uuid4(),
                }, "23514", "ck_claim_versions_first_version")
        finally:
            engine.dispose()
        bootstrap_guard = create_engine(dsn)
        try:
            with bootstrap_guard.begin() as connection:
                for table, row_id in (
                    ("facts", fact), ("claim_versions", version),
                ):
                    _reject(connection,
                            f"UPDATE dayu_platform.{table} SET created_at=created_at WHERE id=:id",
                            {"id": row_id}, "23514")
                _reject(connection,
                        "DELETE FROM dayu_platform.evidence_links WHERE claim_version_id=:id",
                        {"id": version}, "23514")
        finally:
            bootstrap_guard.dispose()
        with _migration_dsn(dsn), pytest.raises(
            PlatformMigrationAdmissionError, match="business_rows_present"
        ):
            command.downgrade(_alembic_config(), "-1")
        unchanged = create_engine(dsn)
        try:
            with unchanged.connect() as connection:
                assert connection.execute(text(
                    "SELECT version_num FROM public.alembic_version"
                )).scalar_one() == "0007_strict_evidence"
                assert connection.execute(text(
                    "SELECT count(*) FROM dayu_platform.evidence_links"
                )).scalar_one() == 9
        finally:
            unchanged.dispose()
    finally:
        if login is not None:
            drop_temporary_login(platform_cluster, login)
        cleanup = create_engine(dsn)
        try:
            with cleanup.begin() as connection:
                connection.exec_driver_sql(
                    "TRUNCATE TABLE dayu_platform.claim_conflicts, dayu_platform.evidence_links, "
                    "dayu_platform.claim_versions, dayu_platform.claims, dayu_platform.facts, "
                    "dayu_platform.research_candidates"
                )
                connection.execute(text("DELETE FROM dayu_platform.users WHERE id=:id"), {"id": actor})
                connection.execute(text("DELETE FROM dayu_platform.securities WHERE id IN (:a,:b,:c)"), {"a": security_a, "b": security_b, "c": security_other})
                connection.execute(text("DELETE FROM dayu_platform.companies WHERE id IN (:a,:b)"), {"a": company, "b": other_company})
        finally:
            cleanup.dispose()
        run_alembic_downgrade(dsn)
