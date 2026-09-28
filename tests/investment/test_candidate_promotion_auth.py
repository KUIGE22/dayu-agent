"""固定 Fact 授权的单元契约；真实权限、RLS 和撤销由 PG16 lane 验证。"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import pickle
import secrets
from dataclasses import fields
from datetime import datetime, timezone
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

import dayu.investment.storage._evidence_review_auth as auth
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope

_TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_SQL_SOURCE_SHA = {
    "_ACTOR_SQL": "3a0910d1dad8082a926359a2051597a34eaea5f97950ff72f6603f5a60839d7c",
    "_REVIEWER_SQL": "d521a37d60aec0a7e54911ef34fa7065e319529e5380b8ee9b9acb4d4e410352",
}


def _scope(value: str = _TENANT) -> TenantScope:
    """构造只作定位、不证明认证的公开主体提示。

    Args:
        value: 候选 tenant 文本。
    Returns:
        公开 Principal 派生的提示。
    Raises:
        ValueError: 域标识本身非法时传播。
    """
    return Principal(tenant_id=TenantId(value), user_id="forged-caller").to_scope()


def test_frozen_sql_signature_and_fixed_action_boundaries() -> None:
    """保护已接受的 SQL 原字节、旧故障 seam 和闭合动作入口。

    Args:
        无。
    Returns:
        无。
    Raises:
        无。
    """
    source = inspect.getsource(auth)
    found: dict[str, str] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in _SQL_SOURCE_SHA:
                segment = ast.get_source_segment(source, node)
                assert segment is not None
                found[name] = hashlib.sha256(segment.encode()).hexdigest()
    assert found == _SQL_SOURCE_SHA
    signature = inspect.signature(auth._auth_row)
    assert list(signature.parameters) == ["connection", "tenant_id", "token_hash", "reviewer"]
    assert signature.parameters["reviewer"].kind is inspect.Parameter.KEYWORD_ONLY
    assert list(inspect.signature(auth.authorize_fact_promoter).parameters) == [
        "session", "scope_hint", "raw_token"
    ]
    assert auth.FACT_PROMOTION_PERMISSION_KEY == "investment.fact.promote"
    assert auth.FACT_PROMOTION_PERMISSION_KEY != auth.REVIEW_PERMISSION_KEY
    assert auth.FactPromoterAuthWitness.__bases__ == (auth.ActorAuthWitness,)
    assert "FOR UPDATE" not in auth._REVIEWER_SQL.upper()
    assert "FOR SHARE" not in auth._REVIEWER_SQL.upper()


@pytest.mark.parametrize("purpose", ["", "investment.fact.promote.extra", "investment.claim.author", "investment.fact.promote "])
def test_unsupported_private_purpose_rejected_before_connection_use(purpose: str) -> None:
    """无效目的在使用连接前拒绝，不把 unit 边界当真实权限证据。

    Args:
        purpose: 闭合双目的之外的输入。
    Returns:
        无。
    Raises:
        无。
    """
    # 未初始化的真实 Connection 只用于证明 guard 不访问连接；不模拟授权行。
    connection = Connection.__new__(Connection)
    with pytest.raises(auth.EvidenceReviewUsageError, match="^认证事务无效$"):
        auth._granted_auth_row(connection, _TENANT, "unused", purpose)


def test_private_purpose_requires_actual_string() -> None:
    """不可信类型 cast 仅刻画 runtime 边界，连接必须零调用。

    Args:
        无。
    Returns:
        无。
    Raises:
        无。
    """
    connection = Connection.__new__(Connection)
    with pytest.raises(auth.EvidenceReviewUsageError):
        auth._granted_auth_row(connection, _TENANT, "unused", cast(str, 1))


@pytest.mark.parametrize("invalid", [b"", b"a" * 42, b"a" * 44, b"+" * 43, b"a" * 42 + b"=", b"A" * 42 + b"B"])
def test_fact_entry_rejects_invalid_token_before_transaction(invalid: bytes) -> None:
    """坏 bearer 先统一拒绝，不泄露输入或 decoder context。

    Args:
        invalid: 非 canonical bearer。
    Returns:
        无。
    Raises:
        无。
    """
    with Session() as session:
        with pytest.raises(auth.EvidenceReviewUnauthorizedError, match="^认证或授权失败$") as error:
            auth.authorize_fact_promoter(session, _scope(), invalid)
    assert error.value.__cause__ is None and error.value.__context__ is None


@pytest.mark.parametrize("invalid", [_TENANT.upper(), str(UUID(int=0)), "not-a-uuid"])
def test_fact_entry_rejects_invalid_hint_before_transaction(invalid: str) -> None:
    """坏租户提示的优先级先于事务检查。

    Args:
        invalid: 非 canonical 非零 UUID 提示。
    Returns:
        无。
    Raises:
        无。
    """
    with Session() as session:
        with pytest.raises(auth.EvidenceReviewUnauthorizedError):
            auth.authorize_fact_promoter(session, _scope(invalid), secrets.token_urlsafe(32).encode())


def test_fact_entry_requires_existing_transaction_and_bytes() -> None:
    """合法形态事务外 Usage，错误 bytes 类型 Unauthorized。

    Args:
        无。
    Returns:
        无。
    Raises:
        无。
    """
    raw = secrets.token_urlsafe(32).encode()
    with Session() as session:
        with pytest.raises(auth.EvidenceReviewUsageError, match="^认证事务无效$"):
            auth.authorize_fact_promoter(session, _scope(), raw)
        with pytest.raises(auth.EvidenceReviewUnauthorizedError):
            auth.authorize_fact_promoter(session, _scope(), cast(bytes, raw.decode()))


def test_fact_witness_is_opaque_sibling_but_constructor_is_not_provenance() -> None:
    """只验证标准 serializer/repr，公开 constructor 不代表认证来源。

    Args:
        无。
    Returns:
        无。
    Raises:
        无。
    """
    witness = auth.FactPromoterAuthWitness(
        UUID(_TENANT), UUID(int=1), UUID(int=2), datetime.now(timezone.utc),
        auth.FACT_PROMOTION_PERMISSION_KEY, UUID(int=3), UUID(int=4), UUID(int=5), UUID(int=6),
    )
    assert isinstance(witness, auth.ActorAuthWitness)
    assert not isinstance(witness, auth.ReviewerAuthWitness)
    assert {f.name for f in fields(witness)} == {
        "tenant_id", "user_id", "token_id", "checked_at", "policy_key",
        "user_role_id", "role_id", "role_permission_id", "permission_id"
    }
    assert str(witness.user_id) not in repr(witness)
    assert auth.FACT_PROMOTION_PERMISSION_KEY not in repr(witness)
    with pytest.raises(TypeError, match="不可序列化"):
        pickle.dumps(witness)
    with pytest.raises(TypeError):
        json.dumps(witness)
