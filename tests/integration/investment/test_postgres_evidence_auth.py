"""S31-Auth 在平台当前 head schema 上的真实 PostgreSQL 16 契约。

只使用 fixture 独占的 pinned PG16 与合成 256-bit bearer，证明 tenant
RLS、active actor、显式 reviewer grant 和 READ COMMITTED 授权快照。
本文件不操作 evidence 表、不发令牌；迁移随平台 head 执行。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import traceback
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.storage import _evidence_review_auth as auth_module
from dayu.investment.storage._evidence_review_auth import (
    ACTIVE_ACTOR_POLICY_KEY,
    REVIEW_PERMISSION_KEY,
    EvidenceReviewStorageError,
    EvidenceReviewUnauthorizedError,
    ReviewerAuthWitness,
    authorize_active_actor,
    authorize_reviewer,
)
from dayu.investment.storage.db import create_platform_engine, create_platform_session_factory
from tests.integration.investment.conftest import (
    PlatformCluster,
    create_temporary_login,
    drop_temporary_login,
    run_alembic_downgrade,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration
DatabaseFactory = Callable[[], str]
RevocationKind = Literal["token", "user", "organization", "grant"]


@dataclass(frozen=True, slots=True, repr=False)
class AuthDatabase:
    """一次测试私有数据库和合成令牌的无 repr 句柄。"""

    admin: Engine
    app: Engine
    sessions: sessionmaker[Session]
    tenant_a: UUID
    tenant_b: UUID
    user_a: UUID
    token_a: UUID
    raw_a: bytes
    raw_b: bytes
    role: UUID
    permission: UUID
    user_role: UUID
    role_permission: UUID


def _scope(tenant_id: UUID, claimed_user: str = "caller-hint-only") -> TenantScope:
    """构造只承载租户定位的调用者提示。

    Args:
        tenant_id: 待设置 RLS 上下文的租户。
        claimed_user: 不可信且不参与授权的 caller 用户文本。

    Returns:
        公开主体构造器派生的租户范围。

    Raises:
        无。
    """

    return Principal(tenant_id=TenantId(str(tenant_id)), user_id=claimed_user).to_scope()


def _seed(admin: Engine, app: Engine) -> AuthDatabase:
    """仅在独占随机库中放入两租户的合成 auth fixture。

    Args:
        admin: 测试库 bootstrap engine。
        app: 继承最小 app group role 的 engine。

    Returns:
        租户 A 初始无 grant 的测试句柄。

    Raises:
        SQLAlchemyError: 临时测试库 seed 失败时传播。
    """

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    token_a, token_b = uuid.uuid4(), uuid.uuid4()
    role, permission = uuid.uuid4(), uuid.uuid4()
    user_role, role_permission = uuid.uuid4(), uuid.uuid4()
    raw_a = secrets.token_urlsafe(32).encode("ascii")
    raw_b = secrets.token_urlsafe(32).encode("ascii")
    with admin.begin() as connection:
        for tenant, slug in ((tenant_a, "auth-a"), (tenant_b, "auth-b")):
            connection.execute(
                text("INSERT INTO dayu_platform.organizations (id, slug, display_name, status) "
                     "VALUES (:id, :slug, :display_name, 'active')"),
                {"id": tenant, "slug": slug, "display_name": slug},
            )
        for tenant, user, subject in ((tenant_a, user_a, "auth-a"), (tenant_b, user_b, "auth-b")):
            connection.execute(
                text("INSERT INTO dayu_platform.users (id, tenant_id, subject, display_name, status) "
                     "VALUES (:id, :tenant_id, :subject, :display_name, 'active')"),
                {"id": user, "tenant_id": tenant, "subject": subject, "display_name": subject},
            )
        for tenant, user, token, raw in (
            (tenant_a, user_a, token_a, raw_a),
            (tenant_b, user_b, token_b, raw_b),
        ):
            connection.execute(
                text("INSERT INTO dayu_platform.api_tokens "
                     "(id, tenant_id, user_id, name, token_hash, status, expires_at) "
                     "VALUES (:id, :tenant_id, :user_id, :name, :token_hash, 'active', "
                     "statement_timestamp() + interval '1 hour')"),
                {"id": token, "tenant_id": tenant, "user_id": user,
                 "name": "synthetic", "token_hash": hashlib.sha256(raw).hexdigest()},
            )
        connection.execute(
            text("INSERT INTO dayu_platform.roles (id, tenant_id, name) "
                 "VALUES (:id, :tenant_id, :name)"),
            {"id": role, "tenant_id": tenant_a, "name": "synthetic-reviewer"},
        )
        connection.execute(
            text("INSERT INTO dayu_platform.permissions (id, tenant_id, permission_key) "
                 "VALUES (:id, :tenant_id, :permission_key)"),
            {"id": permission, "tenant_id": tenant_a, "permission_key": REVIEW_PERMISSION_KEY},
        )
    return AuthDatabase(
        admin, app, create_platform_session_factory(app), tenant_a, tenant_b,
        user_a, token_a, raw_a, raw_b, role, permission, user_role, role_permission,
    )


@pytest.fixture()
def auth_database(
    platform_cluster: PlatformCluster,
    lifecycle_database: DatabaseFactory,
) -> Iterator[AuthDatabase]:
    """创建并在测试后回退随机 PG16 数据库与 app login。

    Args:
        platform_cluster: 带 owner label 的临时 PG16 cluster。
        lifecycle_database: 独立随机库工厂。

    Returns:
        已 seed 的认证测试句柄。

    Raises:
        SQLAlchemyError: 临时库 seed 或连接故障时传播。
    """

    database = lifecycle_database()
    run_alembic_upgrade(platform_cluster.dsn_for_database(database, "postgres"))
    login = create_temporary_login(platform_cluster, database, member_of="dayu_platform_app")
    admin = create_platform_engine(platform_cluster.dsn_for_database(database, "postgres"))
    app = create_platform_engine(login.dsn)
    try:
        yield _seed(admin, app)
    finally:
        app.dispose()
        admin.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(platform_cluster.dsn_for_database(database, "postgres"))


def _grant(database: AuthDatabase) -> None:
    """给合成用户增加唯一明确的 reviewer grant。

    Args:
        database: 随机测试库句柄。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 临时库写入故障时传播。
    """

    with database.admin.begin() as connection:
        connection.execute(
            text("INSERT INTO dayu_platform.user_roles (id, tenant_id, user_id, role_id) "
                 "VALUES (:id, :tenant_id, :user_id, :role_id)"),
            {"id": database.user_role, "tenant_id": database.tenant_a,
             "user_id": database.user_a, "role_id": database.role},
        )
        connection.execute(
            text("INSERT INTO dayu_platform.role_permissions "
                 "(id, tenant_id, role_id, permission_id) "
                 "VALUES (:id, :tenant_id, :role_id, :permission_id)"),
            {"id": database.role_permission, "tenant_id": database.tenant_a,
             "role_id": database.role, "permission_id": database.permission},
        )


def _revoke(database: AuthDatabase, kind: RevocationKind, *, revoked: bool) -> None:
    """在第二个连接提交撤销或恢复，供快照顺序测试。

    Args:
        database: 随机测试库句柄。
        kind: 待变更的 token/user/org/grant。
        revoked: 为真时撤销，否则恢复。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 临时库变更故障时传播。
    """

    with database.admin.begin() as connection:
        if kind == "token":
            connection.execute(
                text("UPDATE dayu_platform.api_tokens SET status = :status "
                     "WHERE id = :id"),
                {"status": "revoked" if revoked else "active", "id": database.token_a},
            )
        elif kind == "user":
            connection.execute(
                text("UPDATE dayu_platform.users SET status = :status WHERE id = :id"),
                {"status": "disabled" if revoked else "active", "id": database.user_a},
            )
        elif kind == "organization":
            connection.execute(
                text("UPDATE dayu_platform.organizations SET status = :status WHERE id = :id"),
                {"status": "disabled" if revoked else "active", "id": database.tenant_a},
            )
        else:
            if revoked:
                connection.execute(
                    text("DELETE FROM dayu_platform.role_permissions WHERE id = :id"),
                    {"id": database.role_permission},
                )
            else:
                connection.execute(
                    text("INSERT INTO dayu_platform.role_permissions "
                         "(id, tenant_id, role_id, permission_id) "
                         "VALUES (:id, :tenant_id, :role_id, :permission_id)"),
                    {"id": database.role_permission, "tenant_id": database.tenant_a,
                     "role_id": database.role, "permission_id": database.permission},
                )


def _assert_reviewer_denied_but_actor_allowed(database: AuthDatabase) -> None:
    """证明 grant 缺失只拒 reviewer，不拒 active bearer 作者。

    Args:
        database: 随机测试库句柄。

    Returns:
        无。

    Raises:
        无。
    """

    with database.sessions() as session, session.begin():
        with pytest.raises(EvidenceReviewUnauthorizedError, match="^认证或授权失败$"):
            authorize_reviewer(session, _scope(database.tenant_a), database.raw_a)
        actor = authorize_active_actor(session, _scope(database.tenant_a), database.raw_a)
        assert actor.user_id == database.user_a


def _check_actor_and_reviewer_grant(auth_database: AuthDatabase) -> None:
    """无 grant 的 active bearer 可作作者，但不能作 reviewer。

    Args:
        auth_database: 真实 PG16 随机库句柄。

    Returns:
        无。

    Raises:
        无。
    """

    db = auth_database
    with db.sessions() as session, session.begin():
        actor = authorize_active_actor(session, _scope(db.tenant_a, "forged-user"), db.raw_a)
        assert actor.tenant_id == db.tenant_a
        assert actor.user_id == db.user_a
        assert actor.token_id == db.token_a
        assert actor.policy_key == ACTIVE_ACTOR_POLICY_KEY
        assert actor.checked_at.tzinfo is not None
        with pytest.raises(EvidenceReviewUnauthorizedError, match="^认证或授权失败$"):
            authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
    _grant(db)
    with db.sessions() as session, session.begin():
        reviewer = authorize_reviewer(session, _scope(db.tenant_a, "forged-user"), db.raw_a)
        assert isinstance(reviewer, ReviewerAuthWitness)
        assert reviewer.user_id == db.user_a
        assert reviewer.token_id == db.token_a
        assert reviewer.user_role_id == db.user_role
        assert reviewer.role_permission_id == db.role_permission
        assert reviewer.permission_id == db.permission
        assert reviewer.policy_key == REVIEW_PERMISSION_KEY
        assert reviewer.checked_at.tzinfo is not None
    with db.app.connect() as connection:
        assert connection.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar() in (None, "")
        acl = connection.execute(
            text("SELECT has_table_privilege(current_user, 'dayu_platform.user_roles', 'SELECT'), "
                 "has_table_privilege(current_user, 'dayu_platform.user_roles', 'UPDATE'), "
                 "has_table_privilege(current_user, 'dayu_platform.role_permissions', 'SELECT'), "
                 "has_table_privilege(current_user, 'dayu_platform.role_permissions', 'UPDATE')")
        ).one()
        assert tuple(acl) == (True, False, True, False)


def _check_info_logging_boundary(
    auth_database: AuthDatabase, caplog: pytest.LogCaptureFixture
) -> None:
    """真 PG16 INFO 日志隐藏 hash，外部非隐藏连接在 SQL 前被拒。

    Args:
        auth_database: 已有显式 reviewer grant 的随机库。
        caplog: SQLAlchemy Engine INFO 日志捕获夹具。

    Returns:
        无。

    Raises:
        无。
    """

    db = auth_database
    synthetic_hash = hashlib.sha256(db.raw_a).hexdigest()
    engine_logger = logging.getLogger("sqlalchemy.engine.Engine")
    original_disabled = engine_logger.disabled
    original_propagate = engine_logger.propagate
    engine_logger.disabled = False
    engine_logger.propagate = True
    try:
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="sqlalchemy.engine.Engine"):
            with db.sessions() as session, session.begin():
                actor = authorize_active_actor(session, _scope(db.tenant_a), db.raw_a)
                reviewer = authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
        assert actor.user_id == db.user_a
        assert reviewer.user_id == db.user_a
        assert "api_tokens AS t" in caplog.text
        assert db.raw_a.decode("ascii") not in caplog.text
        assert synthetic_hash not in caplog.text

        external_engine = create_engine(db.app.url, echo=False, hide_parameters=False)
        external_sessions = create_platform_session_factory(external_engine)
        try:
            assert external_engine.hide_parameters is False
            for authorize in (authorize_active_actor, authorize_reviewer):
                caplog.clear()
                with caplog.at_level(logging.INFO, logger="sqlalchemy.engine.Engine"):
                    with external_sessions() as session:
                        with pytest.raises(EvidenceReviewStorageError, match="^认证存储失败$") as denied:
                            with session.begin():
                                authorize(session, _scope(db.tenant_a), db.raw_a)
                        assert not session.in_transaction()
                        assert session.execute(text("SELECT 1")).scalar_one() == 1
                assert denied.value.__context__ is None
                assert denied.value.__cause__ is None
                rendered = "".join(traceback.format_exception(denied.value))
                assert db.raw_a.decode("ascii") not in rendered
                assert synthetic_hash not in rendered
                assert "api_tokens AS t" not in caplog.text
                assert synthetic_hash not in caplog.text
        finally:
            external_engine.dispose()
    finally:
        engine_logger.disabled = original_disabled
        engine_logger.propagate = original_propagate


def _check_missing_grant_links(auth_database: AuthDatabase) -> None:
    """逐一移除 user_role、role_permission、permission 后拒绝审查。

    Args:
        auth_database: 已授予 reviewer grant 的随机库。

    Returns:
        无。

    Raises:
        无。
    """

    db = auth_database
    with db.admin.begin() as connection:
        connection.execute(
            text("DELETE FROM dayu_platform.user_roles WHERE id = :id"),
            {"id": db.user_role},
        )
    _assert_reviewer_denied_but_actor_allowed(db)
    with db.admin.begin() as connection:
        connection.execute(
            text("INSERT INTO dayu_platform.user_roles "
                 "(id, tenant_id, user_id, role_id) "
                 "VALUES (:id, :tenant_id, :user_id, :role_id)"),
            {"id": db.user_role, "tenant_id": db.tenant_a,
             "user_id": db.user_a, "role_id": db.role},
        )
    _revoke(db, "grant", revoked=True)
    _assert_reviewer_denied_but_actor_allowed(db)
    with db.admin.begin() as connection:
        connection.execute(
            text("DELETE FROM dayu_platform.permissions WHERE id = :id"),
            {"id": db.permission},
        )
    _assert_reviewer_denied_but_actor_allowed(db)
    with db.admin.begin() as connection:
        connection.execute(
            text("INSERT INTO dayu_platform.permissions "
                 "(id, tenant_id, permission_key) "
                 "VALUES (:id, :tenant_id, :permission_key)"),
            {"id": db.permission, "tenant_id": db.tenant_a,
             "permission_key": REVIEW_PERMISSION_KEY},
        )
    _revoke(db, "grant", revoked=False)


def _check_multiple_grants_deterministic(auth_database: AuthDatabase) -> None:
    """多条有效 grant 以 user_role/role_permission ID 顺序稳定选一。

    Args:
        auth_database: 已有第一条 reviewer grant 的随机库。

    Returns:
        无。

    Raises:
        无。
    """

    db = auth_database
    role_b, user_role_b, role_permission_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with db.admin.begin() as connection:
        connection.execute(
            text("INSERT INTO dayu_platform.roles (id, tenant_id, name) "
                 "VALUES (:id, :tenant_id, :name)"),
            {"id": role_b, "tenant_id": db.tenant_a, "name": "synthetic-reviewer-b"},
        )
        connection.execute(
            text("INSERT INTO dayu_platform.user_roles "
                 "(id, tenant_id, user_id, role_id) "
                 "VALUES (:id, :tenant_id, :user_id, :role_id)"),
            {"id": user_role_b, "tenant_id": db.tenant_a,
             "user_id": db.user_a, "role_id": role_b},
        )
        connection.execute(
            text("INSERT INTO dayu_platform.role_permissions "
                 "(id, tenant_id, role_id, permission_id) "
                 "VALUES (:id, :tenant_id, :role_id, :permission_id)"),
            {"id": role_permission_b, "tenant_id": db.tenant_a,
             "role_id": role_b, "permission_id": db.permission},
        )
    expected_ur = min(db.user_role, user_role_b)
    expected_rp = db.role_permission if expected_ur == db.user_role else role_permission_b
    with db.sessions() as session, session.begin():
        witness = authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
        assert witness.user_role_id == expected_ur
        assert witness.role_permission_id == expected_rp
    with db.admin.begin() as connection:
        connection.execute(
            text("DELETE FROM dayu_platform.role_permissions WHERE id = :id"),
            {"id": role_permission_b},
        )
        connection.execute(
            text("DELETE FROM dayu_platform.user_roles WHERE id = :id"),
            {"id": user_role_b},
        )
        connection.execute(
            text("DELETE FROM dayu_platform.roles WHERE id = :id"),
            {"id": role_b},
        )


def _check_hint_expiry_and_active_status(auth_database: AuthDatabase) -> None:
    """错误租户提示及 token/user/org 状态在 DB 查询处统一拒绝。

    Args:
        auth_database: 真实 PG16 随机库句柄。

    Returns:
        无。

    Raises:
        无。
    """

    db = auth_database
    for scope, token in ((_scope(db.tenant_b), db.raw_a), (_scope(db.tenant_a), db.raw_b)):
        with db.sessions() as session, session.begin():
            with pytest.raises(EvidenceReviewUnauthorizedError, match="^认证或授权失败$"):
                authorize_active_actor(session, scope, token)
            with pytest.raises(EvidenceReviewUnauthorizedError, match="^认证或授权失败$"):
                authorize_reviewer(session, scope, token)
    with db.admin.begin() as connection:
        connection.execute(
            text("UPDATE dayu_platform.api_tokens SET expires_at = NULL WHERE id = :id"),
            {"id": db.token_a},
        )
    with db.sessions() as session, session.begin():
        with pytest.raises(EvidenceReviewUnauthorizedError):
            authorize_active_actor(session, _scope(db.tenant_a), db.raw_a)
        with pytest.raises(EvidenceReviewUnauthorizedError):
            authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
    with db.admin.begin() as connection:
        connection.execute(
            text("UPDATE dayu_platform.api_tokens "
                 "SET expires_at = statement_timestamp() - interval '1 second' WHERE id = :id"),
            {"id": db.token_a},
        )
    with db.sessions() as session, session.begin():
        with pytest.raises(EvidenceReviewUnauthorizedError):
            authorize_active_actor(session, _scope(db.tenant_a), db.raw_a)
        with pytest.raises(EvidenceReviewUnauthorizedError):
            authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
    with db.admin.begin() as connection:
        connection.execute(
            text("UPDATE dayu_platform.api_tokens "
                 "SET expires_at = statement_timestamp() + interval '1 hour' WHERE id = :id"),
            {"id": db.token_a},
        )
    for kind in ("token", "user", "organization"):
        _revoke(db, kind, revoked=True)
        with db.sessions() as session, session.begin():
            with pytest.raises(EvidenceReviewUnauthorizedError):
                authorize_active_actor(session, _scope(db.tenant_a), db.raw_a)
            with pytest.raises(EvidenceReviewUnauthorizedError):
                authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
        _revoke(db, kind, revoked=False)
    with db.admin.begin() as connection:
        connection.execute(
            text("UPDATE dayu_platform.users SET status = 'locked' WHERE id = :id"),
            {"id": db.user_a},
        )
    with db.sessions() as session, session.begin():
        with pytest.raises(EvidenceReviewUnauthorizedError):
            authorize_active_actor(session, _scope(db.tenant_a), db.raw_a)
        with pytest.raises(EvidenceReviewUnauthorizedError):
            authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
    with db.admin.begin() as connection:
        connection.execute(
            text("UPDATE dayu_platform.users SET status = 'active' WHERE id = :id"),
            {"id": db.user_a},
        )


def _check_read_committed_revocation_linearization(auth_database: AuthDatabase) -> None:
    """撤销在授权语句前拒绝，语句后提交不追溯历史见证。

    Args:
        auth_database: 真实 PG16 随机库句柄。

    Returns:
        无。

    Raises:
        无。
    """

    db = auth_database
    for kind in ("token", "user", "organization", "grant"):
        with db.sessions() as session, session.begin():
            session.execute(text("SELECT 1"))
            _revoke(db, kind, revoked=True)
            with pytest.raises(EvidenceReviewUnauthorizedError):
                authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
            if kind == "grant":
                actor = authorize_active_actor(session, _scope(db.tenant_a), db.raw_a)
                assert actor.user_id == db.user_a
        _revoke(db, kind, revoked=False)
        with db.sessions() as session, session.begin():
            witness = authorize_reviewer(session, _scope(db.tenant_a), db.raw_a)
            assert witness.user_id == db.user_a
            _revoke(db, kind, revoked=True)
            assert session.in_transaction()
        assert witness.checked_at <= datetime.now(timezone.utc)
        _revoke(db, kind, revoked=False)


def _check_repeatable_read_is_rejected(auth_database: AuthDatabase) -> None:
    """调用者事务不是 READ COMMITTED 时 helper fail closed。

    Args:
        auth_database: 真实 PG16 随机库句柄。

    Returns:
        无。

    Raises:
        无。
    """

    repeatable_engine = auth_database.app.execution_options(isolation_level="REPEATABLE READ")
    sessions = create_platform_session_factory(repeatable_engine)
    with sessions() as session, session.begin():
        with pytest.raises(EvidenceReviewStorageError, match="^认证存储失败$"):
            authorize_active_actor(session, _scope(auth_database.tenant_a), auth_database.raw_a)


def _check_sql_failure_is_redacted_and_rolled_back(
    auth_database: AuthDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """参数化授权 SQL 故障只暴露固定错误并回滚调用者事务。

    Args:
        auth_database: 真实 PG16 随机库句柄。
        monkeypatch: 仅在本测试内注入不存在的 auth 表。

    Returns:
        无。

    Raises:
        无。
    """

    monkeypatch.setattr(
        auth_module,
        "_ACTOR_SQL",
        "SELECT id FROM dayu_platform.absent_auth_table WHERE token_hash = :token_hash",
    )
    with auth_database.sessions() as session:
        with pytest.raises(EvidenceReviewStorageError, match="^认证存储失败$") as captured:
            with session.begin():
                authorize_active_actor(session, _scope(auth_database.tenant_a), auth_database.raw_a)
        assert not session.in_transaction()
        assert session.execute(text("SELECT 1")).scalar_one() == 1
    assert captured.value.__context__ is None
    assert captured.value.__cause__ is None
    rendered = "".join(traceback.format_exception(captured.value))
    assert auth_database.raw_a.decode("ascii") not in rendered
    assert hashlib.sha256(auth_database.raw_a).hexdigest() not in rendered
    monkeypatch.setattr(
        auth_module,
        "_REVIEWER_SQL",
        "SELECT id FROM dayu_platform.absent_review_table WHERE token_hash = :token_hash",
    )
    with auth_database.sessions() as session:
        with pytest.raises(EvidenceReviewStorageError, match="^认证存储失败$") as review_error:
            with session.begin():
                authorize_reviewer(session, _scope(auth_database.tenant_a), auth_database.raw_a)
        assert not session.in_transaction()
    assert review_error.value.__context__ is None
    assert review_error.value.__cause__ is None
    review_traceback = "".join(traceback.format_exception(review_error.value))
    assert auth_database.raw_a.decode("ascii") not in review_traceback
    assert hashlib.sha256(auth_database.raw_a).hexdigest() not in review_traceback


def test_s31_auth_pg16_on_current_head(
    auth_database: AuthDatabase,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """同一随机库串行覆盖认证、撤销快照与隔离负例。

    0001 的 app/audit group role 是 cluster-global；fixture 回退到 base
    并清理临时登录角色，使下一随机库可重新执行 0001。

    Args:
        auth_database: 真实 PG16 随机库句柄。
        monkeypatch: SQL 故障分支的临时测试注入器。
        caplog: SQLAlchemy Engine INFO 日志夹具。

    Returns:
        无。

    Raises:
        无。
    """

    _check_actor_and_reviewer_grant(auth_database)
    _check_info_logging_boundary(auth_database, caplog)
    _check_missing_grant_links(auth_database)
    _check_multiple_grants_deterministic(auth_database)
    _check_hint_expiry_and_active_status(auth_database)
    _check_read_committed_revocation_linearization(auth_database)
    _check_repeatable_read_is_rejected(auth_database)
    _check_sql_failure_is_redacted_and_rolled_back(auth_database, monkeypatch)
