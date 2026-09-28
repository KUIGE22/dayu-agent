"""S32-B-Auth 真实 PG16 固定动作、撤销快照、零写与错误边界验证。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from typing import Literal, TypeAlias
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import Connection, ExecutionContext
from sqlalchemy.engine.interfaces import DBAPICursor
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

import dayu.investment.storage._evidence_review_auth as auth
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.storage.db import create_platform_engine, create_platform_session_factory
from tests.integration.investment.conftest import (
    PlatformCluster,
    create_temporary_login,
    drop_temporary_login,
    run_alembic_downgrade,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration
Revocation = Literal["token", "user", "organization", "user_role", "role_permission"]
SqlScalar: TypeAlias = str | int | bool | UUID | datetime | bytes | None
SqlParameters: TypeAlias = tuple[SqlScalar, ...] | dict[str, SqlScalar]
_AUTH_TABLES = ("api_tokens", "users", "organizations", "roles", "permissions", "user_roles", "role_permissions")
_LOCK_TIMEOUT = "1s"
_STATEMENT_TIMEOUT = "3s"


@dataclass(frozen=True, slots=True)
class Grant:
    """测试唯一 grant 链的四个非零 UUID；不含令牌。"""
    role: UUID
    user_role: UUID
    role_permission: UUID
    permission: UUID


@dataclass(frozen=True, slots=True, repr=False)
class FactDatabase:
    """owned 随机 PG16 数据库句柄；禁止 repr 泄露合成 bearer。"""
    admin: Engine
    app: Engine
    sessions: sessionmaker[Session]
    tenant_a: UUID
    tenant_b: UUID
    user_a: UUID
    user_b: UUID
    token_a: UUID
    token_b: UUID
    raw_a: bytes
    raw_b: bytes
    fact_a: Grant
    fact_b: Grant
    review_a: Grant


def _scope(tenant: UUID) -> TenantScope:
    """构造伪称用户的租户提示。Args: tenant为定位UUID。Returns: scope。Raises: 无。"""
    return Principal(tenant_id=TenantId(str(tenant)), user_id="forged-user").to_scope()


def _add_grant(connection: Connection, tenant: UUID, user: UUID, purpose: str, base: int) -> Grant:
    """只在 owned admin fixture seed grant。Args: 连接/租户/用户/目的/ID基数。Returns: grant。Raises: SQLAlchemyError。"""
    grant = Grant(*(UUID(int=base + offset) for offset in range(4)))
    connection.execute(text("INSERT INTO dayu_platform.roles (id,tenant_id,name) VALUES (:id,:tenant,:name)"),
                       {"id": grant.role, "tenant": tenant, "name": f"untrusted-role-name-{base}"})
    connection.execute(text("INSERT INTO dayu_platform.permissions (id,tenant_id,permission_key) VALUES (:id,:tenant,:purpose)"),
                       {"id": grant.permission, "tenant": tenant, "purpose": purpose})
    connection.execute(text("INSERT INTO dayu_platform.user_roles (id,tenant_id,user_id,role_id) VALUES (:id,:tenant,:user,:role)"),
                       {"id": grant.user_role, "tenant": tenant, "user": user, "role": grant.role})
    connection.execute(text("INSERT INTO dayu_platform.role_permissions (id,tenant_id,role_id,permission_id) VALUES (:id,:tenant,:role,:permission)"),
                       {"id": grant.role_permission, "tenant": tenant, "role": grant.role, "permission": grant.permission})
    return grant


def _seed(admin: Engine, app: Engine) -> FactDatabase:
    """seed两租户及两固定权限。Args: 随机库admin/app。Returns: 无repr句柄。Raises: SQLAlchemyError。"""
    ta, tb, ua, ub, toka, tokb = (uuid4() for _ in range(6))
    rawa, rawb = secrets.token_urlsafe(32).encode(), secrets.token_urlsafe(32).encode()
    with admin.begin() as connection:
        for tenant, user, token, raw, name in ((ta, ua, toka, rawa, "fact-a"), (tb, ub, tokb, rawb, "fact-b")):
            connection.execute(text("INSERT INTO dayu_platform.organizations(id,slug,display_name,status) VALUES (:tenant,:name,:name,'active')"),
                               {"tenant": tenant, "name": name})
            connection.execute(text("INSERT INTO dayu_platform.users(id,tenant_id,subject,display_name,status) VALUES (:user,:tenant,:name,:name,'active')"),
                               {"user": user, "tenant": tenant, "name": name})
            connection.execute(text("INSERT INTO dayu_platform.api_tokens(id,tenant_id,user_id,name,token_hash,status,expires_at) VALUES (:token,:tenant,:user,'synthetic',:hash,'active',statement_timestamp()+interval '1 hour')"),
                               {"token": token, "tenant": tenant, "user": user, "hash": hashlib.sha256(raw).hexdigest()})
        fa = _add_grant(connection, ta, ua, auth.FACT_PROMOTION_PERMISSION_KEY, 200)
        fb = _add_grant(connection, tb, ub, auth.FACT_PROMOTION_PERMISSION_KEY, 300)
        ra = _add_grant(connection, ta, ua, auth.REVIEW_PERMISSION_KEY, 400)
    return FactDatabase(admin, app, create_platform_session_factory(app), ta, tb, ua, ub, toka, tokb, rawa, rawb, fa, fb, ra)


@pytest.fixture()
def fact_database(platform_cluster: PlatformCluster, lifecycle_database: Callable[[], str]) -> Iterator[FactDatabase]:
    """复用owner harness创建/回退随机库。Args: cluster和随机库工厂。Returns: fixture。Raises: SQLAlchemyError。"""
    database = lifecycle_database()
    dsn = platform_cluster.dsn_for_database(database, "postgres")
    run_alembic_upgrade(dsn)
    login = create_temporary_login(platform_cluster, database, member_of="dayu_platform_app")
    admin, app = create_platform_engine(dsn), create_platform_engine(login.dsn)
    try:
        yield _seed(admin, app)
    finally:
        app.dispose()
        admin.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(dsn)


def _fact(session: Session, db: FactDatabase) -> auth.FactPromoterAuthWitness:
    """固定租户A动作调用。Args: caller Session/fixture。Returns: Fact见证。Raises: 认证固定错误。"""
    return auth.authorize_fact_promoter(session, _scope(db.tenant_a), db.raw_a)


def _deny(session: Session, db: FactDatabase) -> None:
    """断言真实query统一拒绝。Args: caller/fixture。Returns: 无。Raises: 无。"""
    with pytest.raises(auth.EvidenceReviewUnauthorizedError, match="^认证或授权失败$") as error:
        _fact(session, db)
    assert error.value.__context__ is None and error.value.__cause__ is None


def _assert_context_clean(db: FactDatabase) -> None:
    """核caller结束后连接池无SET LOCAL泄漏。Args: fixture。Returns: 无。Raises: SQLAlchemyError。"""
    with db.app.connect() as connection:
        assert connection.execute(text("SELECT current_setting('app.tenant_id',true)")).scalar_one() in (None, "")


def _snapshot(db: FactDatabase) -> dict[str, str]:
    """逐实际列快照auth七表并核所有业务counts。Args: fixture。Returns: 无敏感值的digest映射。Raises: SQLAlchemyError。"""
    result: dict[str, str] = {}
    with db.admin.connect() as connection:
        names = connection.execute(text("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='dayu_platform' AND c.relkind='r' ORDER BY c.relname")).scalars().all()
        for name in names:
            assert isinstance(name, str) and name.isidentifier()
            if name in _AUTH_TABLES:
                rows = connection.execute(text(f'SELECT row_to_json(t)::text FROM dayu_platform."{name}" t ORDER BY id')).scalars().all()
                assert all(isinstance(row, str) for row in rows)
                # 完整row JSON比较经长度分帧digest表示，pytest差异不打印token_hash列。
                framed = b"".join(len(row.encode()).to_bytes(8, "big") + row.encode() for row in rows)
                result[name] = hashlib.sha256(framed).hexdigest()
            else:
                result[name] = str(connection.execute(text(f'SELECT count(*) FROM dayu_platform."{name}"')).scalar_one())
    assert set(_AUTH_TABLES) <= result.keys()
    return result


@pytest.mark.parametrize("fact,review", [(False, False), (False, True), (True, False), (True, True)])
def test_fixed_grant_purposes(fact_database: FactDatabase, fact: bool, review: bool) -> None:
    """四组合验证purpose隔离与同链身份。Args: fixture/fact/review。Returns: 无。Raises: 无。"""
    db = fact_database
    with db.admin.begin() as connection:
        for allowed, grant in ((fact, db.fact_a), (review, db.review_a)):
            if not allowed:
                connection.execute(text("DELETE FROM dayu_platform.role_permissions WHERE id=:id"), {"id": grant.role_permission})
    with db.sessions() as session, session.begin():
        actor = auth.authorize_active_actor(session, _scope(db.tenant_a), db.raw_a)
        assert (actor.tenant_id, actor.user_id, actor.token_id) == (db.tenant_a, db.user_a, db.token_a)
        if fact:
            witness = _fact(session, db)
            assert type(witness) is auth.FactPromoterAuthWitness
            assert not isinstance(witness, auth.ReviewerAuthWitness)
            assert (witness.user_role_id, witness.role_id, witness.role_permission_id, witness.permission_id) == (db.fact_a.user_role, db.fact_a.role, db.fact_a.role_permission, db.fact_a.permission)
            assert witness.policy_key == auth.FACT_PROMOTION_PERMISSION_KEY
            assert witness.checked_at.tzinfo is timezone.utc
        else:
            _deny(session, db)
        if review:
            reviewer = auth.authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
            assert type(reviewer) is auth.ReviewerAuthWitness
            assert reviewer.permission_id == db.review_a.permission
            assert reviewer.policy_key == auth.REVIEW_PERMISSION_KEY
        else:
            with pytest.raises(auth.EvidenceReviewUnauthorizedError):
                auth.authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)


def test_tenant_rls_fk_and_multiple_chains(fact_database: FactDatabase) -> None:
    """两tenant/RLS/FK/确定整链选择。Args: fixture。Returns: 无。Raises: 无。"""
    db = fact_database
    with db.sessions() as session, session.begin():
        b = auth.authorize_fact_promoter(session, _scope(db.tenant_b), db.raw_b)
        assert (b.tenant_id, b.user_id, b.token_id, b.permission_id) == (db.tenant_b, db.user_b, db.token_b, db.fact_b.permission)
        with pytest.raises(auth.EvidenceReviewUnauthorizedError):
            auth.authorize_fact_promoter(session, _scope(db.tenant_b), db.raw_a)
        assert session.execute(text("SELECT id FROM dayu_platform.api_tokens")).scalars().all() == [db.token_b]
    with pytest.raises(IntegrityError), db.admin.begin() as connection:
        connection.execute(text("INSERT INTO dayu_platform.user_roles(id,tenant_id,user_id,role_id) VALUES (:id,:tenant,:user,:role)"),
                           {"id": uuid4(), "tenant": db.tenant_b, "user": db.user_a, "role": db.fact_b.role})
    with db.admin.begin() as connection:
        # 同purpose两条链共享permission，低UUID user_role应整链选中。
        low = Grant(UUID(int=100), UUID(int=101), UUID(int=102), db.fact_a.permission)
        connection.execute(text("INSERT INTO dayu_platform.roles(id,tenant_id,name) VALUES (:id,:tenant,'claim-review-name-does-not-authorize')"), {"id": low.role, "tenant": db.tenant_a})
        connection.execute(text("INSERT INTO dayu_platform.user_roles(id,tenant_id,user_id,role_id) VALUES (:id,:tenant,:user,:role)"), {"id": low.user_role, "tenant": db.tenant_a, "user": db.user_a, "role": low.role})
        connection.execute(text("INSERT INTO dayu_platform.role_permissions(id,tenant_id,role_id,permission_id) VALUES (:id,:tenant,:role,:permission)"), {"id": low.role_permission, "tenant": db.tenant_a, "role": low.role, "permission": low.permission})
    with db.sessions() as session, session.begin():
        w = _fact(session, db)
        assert (w.user_role_id, w.role_id, w.role_permission_id, w.permission_id) == (low.user_role, low.role, low.role_permission, low.permission)


def _revoke(db: FactDatabase, kind: Revocation, revoked: bool, caller_pid: int) -> None:
    """第二连接bounded撤销/恢复。Args: fixture/类别/方向/caller PID。Returns: 无。Raises: SQLAlchemyError。"""
    with db.admin.begin() as connection:
        assert connection.execute(text("SELECT pg_backend_pid()")).scalar_one() != caller_pid
        connection.execute(text("SELECT set_config('lock_timeout',:v,true)"), {"v": _LOCK_TIMEOUT})
        connection.execute(text("SELECT set_config('statement_timeout',:v,true)"), {"v": _STATEMENT_TIMEOUT})
        if kind in ("token", "user", "organization"):
            table, id_ = {"token": ("api_tokens", db.token_a), "user": ("users", db.user_a), "organization": ("organizations", db.tenant_a)}[kind]
            status = ("revoked" if kind == "token" else "disabled") if revoked else "active"
            connection.execute(text(f"UPDATE dayu_platform.{table} SET status=:status WHERE id=:id"), {"status": status, "id": id_})
        elif kind == "user_role":
            if revoked:
                connection.execute(text("DELETE FROM dayu_platform.user_roles WHERE id=:id"), {"id": db.fact_a.user_role})
            else:
                connection.execute(text("INSERT INTO dayu_platform.user_roles(id,tenant_id,user_id,role_id) VALUES (:id,:tenant,:user,:role)"), {"id": db.fact_a.user_role, "tenant": db.tenant_a, "user": db.user_a, "role": db.fact_a.role})
        elif revoked:
            connection.execute(text("DELETE FROM dayu_platform.role_permissions WHERE id=:id"), {"id": db.fact_a.role_permission})
        else:
            connection.execute(text("INSERT INTO dayu_platform.role_permissions(id,tenant_id,role_id,permission_id) VALUES (:id,:tenant,:role,:permission)"), {"id": db.fact_a.role_permission, "tenant": db.tenant_a, "role": db.fact_a.role, "permission": db.fact_a.permission})


@pytest.mark.parametrize("kind", ["token", "user", "organization", "user_role", "role_permission"])
def test_two_connection_fresh_snapshot_revocation(fact_database: FactDatabase, kind: Revocation) -> None:
    """五类各用新库证明前撤销/后撤销/同事务fresh拒绝且无锁。Args: fixture/类别。Returns: 无。Raises: 无。"""
    db = fact_database
    with db.sessions() as session, session.begin():
        pid = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert isinstance(pid, int)
        _revoke(db, kind, True, pid)
        _deny(session, db)
        _revoke(db, kind, False, pid)
    with db.sessions() as session, session.begin():
        before = session.execute(text("SELECT statement_timestamp()")).scalar_one()
        pid = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert isinstance(pid, int) and isinstance(before, datetime)
        witness = _fact(session, db)
        _revoke(db, kind, True, pid)
        after = session.execute(text("SELECT statement_timestamp()")).scalar_one()
        assert isinstance(after, datetime) and before <= witness.checked_at <= after
        assert session.in_transaction() and witness.user_id == db.user_a
        _deny(session, db)
    _assert_context_clean(db)


def test_expiry_status_and_permission_key(fact_database: FactDatabase) -> None:
    """严格expiry及现有status/permission变更真实拒绝。Args: fixture。Returns: 无。Raises: 无。"""
    db = fact_database
    assert "t.expires_at > statement_timestamp()" in auth._REVIEWER_SQL
    for expression in ("NULL", "statement_timestamp()", "statement_timestamp()-interval '1 second'"):
        with db.admin.begin() as connection:
            connection.execute(text(f"UPDATE dayu_platform.api_tokens SET expires_at={expression} WHERE id=:id"), {"id": db.token_a})
        with db.sessions() as session, session.begin():
            _deny(session, db)
    with db.admin.begin() as connection:
        connection.execute(text("UPDATE dayu_platform.api_tokens SET expires_at=statement_timestamp()+interval '1 hour' WHERE id=:id"), {"id": db.token_a})
    for table, id_, bad in (("api_tokens", db.token_a, "revoked"), ("users", db.user_a, "locked"), ("users", db.user_a, "disabled"), ("organizations", db.tenant_a, "disabled")):
        with db.admin.begin() as connection:
            connection.execute(text(f"UPDATE dayu_platform.{table} SET status=:status WHERE id=:id"), {"status": bad, "id": id_})
        with db.sessions() as session, session.begin():
            _deny(session, db)
        with db.admin.begin() as connection:
            connection.execute(text(f"UPDATE dayu_platform.{table} SET status='active' WHERE id=:id"), {"id": id_})
    with db.admin.begin() as connection:
        connection.execute(text("UPDATE dayu_platform.permissions SET permission_key='unrelated.permission' WHERE id=:id"), {"id": db.fact_a.permission})
    with db.sessions() as session, session.begin():
        _deny(session, db)


def test_catalog_acl_and_zero_writes(fact_database: FactDatabase) -> None:
    """当前head/RLS/旧ACL及auth全列和业务counts零写。Args: fixture。Returns: 无。Raises: 无。"""
    db = fact_database
    before = _snapshot(db)
    with db.sessions() as session, session.begin():
        for _ in range(2):
            _fact(session, db)
        acl = session.execute(text("SELECT has_table_privilege(current_user,'dayu_platform.user_roles','SELECT'),has_table_privilege(current_user,'dayu_platform.user_roles','DELETE'),has_table_privilege(current_user,'dayu_platform.user_roles','UPDATE'),has_table_privilege(current_user,'dayu_platform.role_permissions','SELECT'),has_table_privilege(current_user,'dayu_platform.role_permissions','DELETE'),has_table_privilege(current_user,'dayu_platform.role_permissions','UPDATE')")).one()
        assert tuple(acl) == (True, True, False, True, True, False)
        assert session.execute(text("SELECT last_used_at FROM dayu_platform.api_tokens WHERE id=:id"), {"id": db.token_a}).scalar_one() is None
    assert _snapshot(db) == before
    _assert_context_clean(db)
    with db.admin.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one() == "0008_candidate_intake"
        catalog = connection.execute(text("SELECT count(*),count(*) FILTER(WHERE c.relrowsecurity),count(*) FILTER(WHERE c.relforcerowsecurity) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='dayu_platform' AND c.relkind='r'")).one()
        assert tuple(catalog) == (34, 31, 31)


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
def test_non_read_committed_rejected(fact_database: FactDatabase, isolation: str) -> None:
    """拒绝非RC，不改变caller隔离。Args: fixture/隔离级别。Returns: 无。Raises: 无。"""
    sessions = create_platform_session_factory(fact_database.app.execution_options(isolation_level=isolation))
    with sessions() as session, session.begin():
        with pytest.raises(auth.EvidenceReviewStorageError):
            _fact(session, fact_database)


def _wrong_readback(connection: Connection, cursor: DBAPICursor, statement: str, parameters: SqlParameters, context: ExecutionContext, executemany: bool) -> tuple[str, SqlParameters]:
    """只注入owned readback结果。Args: SQLAlchemy真实cursor事件字段。Returns: SQL/原bind。Raises: 无。"""
    if statement.startswith("SELECT current_setting('app.tenant_id', true), "):
        return "SELECT 'wrong-tenant', 'read committed'", parameters
    return statement, parameters


def test_real_context_readback_failure(fact_database: FactDatabase) -> None:
    """真实连接readback失配收束Storage并caller回滚。Args: fixture。Returns: 无。Raises: 无。"""
    db = fact_database
    event.listen(db.app, "before_cursor_execute", _wrong_readback, retval=True)
    try:
        with db.sessions() as session:
            with pytest.raises(auth.EvidenceReviewStorageError), session.begin():
                _fact(session, db)
            assert not session.in_transaction()
    finally:
        event.remove(db.app, "before_cursor_execute", _wrong_readback)
    _assert_context_clean(db)


def test_projection_and_sql_error_redaction(fact_database: FactDatabase, monkeypatch: pytest.MonkeyPatch) -> None:
    """owned PG投影/SQL故障，不删FK不伪称认证成功。Args: fixture/patch。Returns: 无。Raises: 无。"""
    db = fact_database
    valid = [f"'{db.tenant_a}'::uuid", f"'{db.user_a}'::uuid", f"'{db.token_a}'::uuid", "statement_timestamp()", *[f"'{UUID(int=i)}'::uuid" for i in range(1, 5)]]
    projections = [valid[:3], valid + ["NULL"]]
    for index in (0, 1, 2, 4, 5, 6, 7):
        nil = valid.copy()
        nil[index] = f"'{UUID(int=0)}'::uuid"
        projections.append(nil)
    for bad in ("NULL::timestamptz", "statement_timestamp()::timestamp"):
        malformed = valid.copy()
        malformed[3] = bad
        projections.append(malformed)
    wrong_type = valid.copy()
    wrong_type[4] = "'wrong-uuid-type'::text"
    projections.append(wrong_type)
    for projection in projections:
        with monkeypatch.context() as patch:
            patch.setattr(auth, "_REVIEWER_SQL", "SELECT " + ",".join(projection))
            with db.sessions() as session:
                with pytest.raises(auth.EvidenceReviewStorageError), session.begin():
                    _fact(session, db)
                assert not session.in_transaction()
    with monkeypatch.context() as patch:
        patch.setattr(auth, "_REVIEWER_SQL", "SELECT id FROM dayu_platform.absent_fact_auth WHERE token_hash=:token_hash")
        with db.sessions() as session:
            with pytest.raises(auth.EvidenceReviewStorageError, match="^认证存储失败$") as error:
                with session.begin():
                    _fact(session, db)
            assert not session.in_transaction()
            assert session.execute(text("SELECT 1")).scalar_one() == 1
        assert error.value.__context__ is None and error.value.__cause__ is None
        rendered = "".join(traceback.format_exception(error.value))
        assert db.raw_a.decode() not in rendered and hashlib.sha256(db.raw_a).hexdigest() not in rendered


def test_hidden_bind_logging_and_external_engine(fact_database: FactDatabase, caplog: pytest.LogCaptureFixture) -> None:
    """真实PG INFO可见SQL但不可见raw/hash，非hidden engine先拒。Args: fixture/caplog。Returns: 无。Raises: 无。"""
    db = fact_database
    logger = logging.getLogger("sqlalchemy.engine.Engine")
    disabled, propagate = logger.disabled, logger.propagate
    logger.disabled, logger.propagate = False, True
    try:
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="sqlalchemy.engine.Engine"):
            with db.sessions() as session, session.begin():
                _fact(session, db)
        assert "api_tokens AS t" in caplog.text
        assert db.raw_a.decode() not in caplog.text and hashlib.sha256(db.raw_a).hexdigest() not in caplog.text
        engine = create_engine(db.app.url, hide_parameters=False)
        try:
            caplog.clear()
            with create_platform_session_factory(engine)() as session:
                with pytest.raises(auth.EvidenceReviewStorageError) as error, session.begin():
                    _fact(session, db)
                assert not session.in_transaction()
            assert error.value.__cause__ is None and error.value.__context__ is None
            assert db.raw_a.decode() not in str(error.value)
            assert "api_tokens AS t" not in caplog.text
        finally:
            engine.dispose()
    finally:
        logger.disabled, logger.propagate = disabled, propagate


def _raise_grant(connection: Connection, tenant_id: str, token_hash: str, permission_key: str, *, error_type: type[KeyboardInterrupt] | type[SystemExit]) -> auth._AuthRow:
    """owned故障边界抛BaseException。Args: 原grant字段及异常class。Returns: 不返回。Raises: KeyboardInterrupt/SystemExit。"""
    assert permission_key == auth.FACT_PROMOTION_PERMISSION_KEY
    raise error_type()


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_base_exception_propagates_and_rolls_back(fact_database: FactDatabase, monkeypatch: pytest.MonkeyPatch, error_type: type[KeyboardInterrupt] | type[SystemExit]) -> None:
    """helper内部BaseException不转deny，caller回滚零写。Args: fixture/patch/异常class。Returns: 无。Raises: 无。"""
    db = fact_database
    before = _snapshot(db)
    with monkeypatch.context() as patch:
        patch.setattr(auth, "_granted_auth_row", partial(_raise_grant, error_type=error_type))
        with db.sessions() as session:
            with pytest.raises(error_type), session.begin():
                _fact(session, db)
            assert not session.in_transaction()
    assert _snapshot(db) == before
    _assert_context_clean(db)


async def _cancel_caller(db: FactDatabase) -> None:
    """取消包围同步helper的caller task。Args: fixture。Returns: 不正常返回。Raises: asyncio.CancelledError。"""
    with db.sessions() as session, session.begin():
        _fact(session, db)
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        await asyncio.sleep(0)


def test_async_caller_cancellation_zero_writes(fact_database: FactDatabase) -> None:
    """证明caller取消传播，不声称同步driver异步取消。Args: fixture。Returns: 无。Raises: 无。"""
    db = fact_database
    before = _snapshot(db)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_cancel_caller(db))
    assert _snapshot(db) == before
    _assert_context_clean(db)
