"""S31-Auth 私有令牌入口的无数据库单元契约。

本文件只验证 canonical bearer、脱敏错误与 SQL 形状；RLS、ACL、授权
语句快照和撤销竞态必须由真实 PostgreSQL 16 integration lane 证明。
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import secrets
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.storage._evidence_review_auth import (
    _ACTOR_SQL,
    _REVIEWER_SQL,
    ACTIVE_ACTOR_POLICY_KEY,
    REVIEW_PERMISSION_KEY,
    ActorAuthWitness,
    EvidenceReviewUnauthorizedError,
    ReviewerAuthWitness,
    _tenant_hint,
    _token_hash,
)
from dayu.investment.storage.db import create_platform_engine

_ALPHABET = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _scope(value: str) -> TenantScope:
    """以测试主体构造一个不可信租户提示。

    Args:
        value: 候选租户标识文本。

    Returns:
        由公开主体构造器派生的 scope hint。

    Raises:
        ValueError: 标识本身为空时传播域校验错误。
    """

    return Principal(tenant_id=TenantId(value), user_id="test-user").to_scope()


def test_token_hash_accepts_only_canonical_32_byte_bearer() -> None:
    """合法合成令牌只在函数内形成 hash，非 canonical 编码拒绝。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    raw = secrets.token_urlsafe(32).encode("ascii")
    assert len(raw) == 43
    assert _token_hash(raw) == hashlib.sha256(raw).hexdigest()
    last_index = _ALPHABET.index(raw[-1])
    assert last_index % 4 == 0
    noncanonical = raw[:-1] + bytes((_ALPHABET[last_index + 1],))
    for candidate in (b"", raw + b"=", raw[:-1], raw[:-1] + b"+", noncanonical):
        with pytest.raises(EvidenceReviewUnauthorizedError, match="^认证或授权失败$") as exc:
            _token_hash(candidate)
        assert exc.value.__cause__ is None
        assert exc.value.__context__ is None
        assert raw.decode("ascii") not in str(exc.value)
        assert hashlib.sha256(raw).hexdigest() not in str(exc.value)


def test_tenant_hint_is_canonical_only_and_never_an_actor() -> None:
    """租户提示仅提供 canonical UUID，不携带 caller 声称的 actor。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    assert _tenant_hint(_scope(_TENANT)) == _TENANT
    for value in (_TENANT.upper(), "00000000-0000-0000-0000-000000000000", "not-a-uuid"):
        with pytest.raises(EvidenceReviewUnauthorizedError, match="^认证或授权失败$") as exc:
            _tenant_hint(_scope(value))
        assert exc.value.__cause__ is None
        assert exc.value.__context__ is None
    uninitialized = TenantScope.__new__(TenantScope)
    with pytest.raises(EvidenceReviewUnauthorizedError, match="^认证或授权失败$") as exc:
        _tenant_hint(uninitialized)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


def test_actor_and_reviewer_use_separate_single_select_shapes() -> None:
    """作者查询不要求 grant；审查查询单语句闭合租户 RBAC 链。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    assert _ACTOR_SQL.upper().count("SELECT ") == 1
    assert _REVIEWER_SQL.upper().count("SELECT ") == 1
    for statement in (_ACTOR_SQL, _REVIEWER_SQL):
        assert "api_tokens AS t" in statement
        assert "u.tenant_id = t.tenant_id" in statement
        assert "o.id = t.tenant_id" in statement
        assert "t.expires_at > statement_timestamp()" in statement
        assert "statement_timestamp() AS checked_at" in statement
        assert "t.token_hash = :token_hash" in statement
        assert "FOR UPDATE" not in statement.upper()
        assert "FOR SHARE" not in statement.upper()
    assert "user_roles" not in _ACTOR_SQL
    assert "role_permissions" not in _ACTOR_SQL
    for join in ("ur.tenant_id = t.tenant_id", "r.tenant_id = t.tenant_id", "rp.tenant_id = t.tenant_id", "p.tenant_id = t.tenant_id"):
        assert join in _REVIEWER_SQL
    assert "p.permission_key = :permission_key" in _REVIEWER_SQL
    assert "ORDER BY ur.id, rp.id, p.id" in _REVIEWER_SQL
    assert ACTIVE_ACTOR_POLICY_KEY != REVIEW_PERMISSION_KEY


def test_witness_has_no_bearer_and_refuses_standard_serializers() -> None:
    """不可变见证只含数据库身份/时刻，不进 JSON 或 pickle。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    tenant = UUID(_TENANT)
    now = datetime(2026, 9, 27, tzinfo=timezone.utc)
    actor = ActorAuthWitness(tenant, UUID(int=1), UUID(int=2), now, ACTIVE_ACTOR_POLICY_KEY)
    reviewer = ReviewerAuthWitness(
        tenant, UUID(int=1), UUID(int=2), now, REVIEW_PERMISSION_KEY,
        UUID(int=3), UUID(int=4), UUID(int=5), UUID(int=6),
    )
    for witness in (actor, reviewer):
        assert "token_hash" not in repr(witness)
        assert "raw_token" not in repr(witness)
        with pytest.raises(TypeError, match="不可序列化"):
            pickle.dumps(witness)
        with pytest.raises(TypeError):
            json.dumps(witness)


def test_platform_engine_hides_synthetic_bound_hash_in_info_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """INFO 日志对照证明平台 Engine 隐藏 SQL bind 参数。

    Args:
        caplog: 捕获 SQLAlchemy Engine 日志的测试夹具。

    Returns:
        无。

    Raises:
        无。
    """

    synthetic_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    plain = create_engine("sqlite+pysqlite:///:memory:", echo=False, hide_parameters=False)
    hidden = create_platform_engine("sqlite+pysqlite:///:memory:")
    try:
        assert hidden.echo is False
        assert hidden.hide_parameters is True
        with caplog.at_level(logging.INFO, logger="sqlalchemy.engine.Engine"):
            with plain.connect() as connection:
                connection.execute(text("SELECT :token_hash"), {"token_hash": synthetic_hash})
        assert synthetic_hash in caplog.text
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="sqlalchemy.engine.Engine"):
            with hidden.connect() as connection:
                connection.execute(text("SELECT :token_hash"), {"token_hash": synthetic_hash})
                with pytest.raises(SQLAlchemyError) as database_error:
                    connection.execute(
                        text("SELECT :token_hash FROM absent_auth_table"),
                        {"token_hash": synthetic_hash},
                    )
        assert "SELECT" in caplog.text
        assert synthetic_hash not in caplog.text
        assert synthetic_hash not in str(database_error.value)
    finally:
        hidden.dispose()
        plain.dispose()
