"""严格证据写入的私有 PostgreSQL bearer 认证辅助。

本模块只在调用者已有的 READ COMMITTED Session 事务内验证现有
``api_tokens``、active user/organization 与固定 Claim/Fact 动作的显式 grant。
租户入参只是 RLS 查询提示；主体始终由 token 行给出。本模块不签发令牌、
不提交事务，也不保存或记录 raw bearer 与 token hash。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Never, SupportsIndex, TypeAlias
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from dayu.investment.domain.identifiers import TenantId, TenantScope
from dayu.investment.storage.db import PLATFORM_SCHEMA_NAME, TENANT_CONTEXT_SETTING

ACTIVE_ACTOR_POLICY_KEY = "investment.claim.author.active_bearer"
"""begin-revision 作者见证的稳定策略标识。"""

REVIEW_PERMISSION_KEY = "investment.claim.review"
"""审查及冲突解决要求的显式 RBAC 权限。"""

FACT_PROMOTION_PERMISSION_KEY = "investment.fact.promote"
"""Fact 晋升前件查询要求的固定 RBAC 权限，不执行晋升。"""

_ACTIVE_STATUS = "active"
_READ_COMMITTED = "read committed"
_TOKEN_LENGTH = 43
_TOKEN_BYTES = 32
_GRANTED_AUTH_ROW_COLUMNS = 8
_TOKEN_PATTERN = re.compile(rb"[A-Za-z0-9_-]{43}")
_DbScalar: TypeAlias = UUID | datetime | str | None
_AuthRow: TypeAlias = Row[tuple[_DbScalar, ...]]

_ACTOR_SQL = f"""
SELECT t.tenant_id, t.user_id, t.id, statement_timestamp() AS checked_at
FROM {PLATFORM_SCHEMA_NAME}.api_tokens AS t
JOIN {PLATFORM_SCHEMA_NAME}.users AS u
  ON u.tenant_id = t.tenant_id AND u.id = t.user_id
JOIN {PLATFORM_SCHEMA_NAME}.organizations AS o
  ON o.id = t.tenant_id
WHERE t.tenant_id = CAST(:tenant_id AS uuid)
  AND t.token_hash = :token_hash
  AND t.status = :active_status
  AND u.status = :active_status
  AND o.status = :active_status
  AND t.expires_at IS NOT NULL
  AND t.expires_at > statement_timestamp()
"""

_REVIEWER_SQL = f"""
SELECT t.tenant_id, t.user_id, t.id, statement_timestamp() AS checked_at,
       ur.id, r.id, rp.id, p.id
FROM {PLATFORM_SCHEMA_NAME}.api_tokens AS t
JOIN {PLATFORM_SCHEMA_NAME}.users AS u
  ON u.tenant_id = t.tenant_id AND u.id = t.user_id
JOIN {PLATFORM_SCHEMA_NAME}.organizations AS o
  ON o.id = t.tenant_id
JOIN {PLATFORM_SCHEMA_NAME}.user_roles AS ur
  ON ur.tenant_id = t.tenant_id AND ur.user_id = u.id
JOIN {PLATFORM_SCHEMA_NAME}.roles AS r
  ON r.tenant_id = t.tenant_id AND r.id = ur.role_id
JOIN {PLATFORM_SCHEMA_NAME}.role_permissions AS rp
  ON rp.tenant_id = t.tenant_id AND rp.role_id = r.id
JOIN {PLATFORM_SCHEMA_NAME}.permissions AS p
  ON p.tenant_id = t.tenant_id AND p.id = rp.permission_id
WHERE t.tenant_id = CAST(:tenant_id AS uuid)
  AND t.token_hash = :token_hash
  AND t.status = :active_status
  AND u.status = :active_status
  AND o.status = :active_status
  AND t.expires_at IS NOT NULL
  AND t.expires_at > statement_timestamp()
  AND p.permission_key = :permission_key
ORDER BY ur.id, rp.id, p.id
LIMIT 1
"""


class EvidenceReviewUnauthorizedError(RuntimeError):
    """令牌、租户提示或动作权限不匹配时的统一脱敏错误。"""

    def __init__(self) -> None:
        """设置固定错误文本。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__("认证或授权失败")


class EvidenceReviewStorageError(RuntimeError):
    """数据库上下文或持久行形态异常时的脱敏错误。"""

    def __init__(self) -> None:
        """设置固定错误文本。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__("认证存储失败")


class EvidenceReviewUsageError(RuntimeError):
    """调用者未提供现有事务时的固定错误。"""

    def __init__(self) -> None:
        """设置固定错误文本。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__("认证事务无效")


class _OpaqueWitness:
    """阻止令牌派生见证被 pickle 序列化的私有基类。"""

    __slots__ = ()

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        """拒绝 pickle 还原协议。

        Args:
            protocol: pickle 协议版本，不参与决策。

        Returns:
            永不返回。

        Raises:
            TypeError: 所有序列化请求均拒绝。
        """

        raise TypeError("认证见证不可序列化")


@dataclass(frozen=True, slots=True, repr=False)
class ActorAuthWitness(_OpaqueWitness):
    """从 active token 行导出的作者见证，不持有 bearer/hash。"""

    tenant_id: UUID
    user_id: UUID
    token_id: UUID
    checked_at: datetime
    policy_key: str


@dataclass(frozen=True, slots=True, repr=False)
class ReviewerAuthWitness(ActorAuthWitness):
    """从同一 SELECT 的有效 RBAC 链导出的审查见证。"""

    user_role_id: UUID
    role_id: UUID
    role_permission_id: UUID
    permission_id: UUID


@dataclass(frozen=True, slots=True, repr=False)
class FactPromoterAuthWitness(ActorAuthWitness):
    """同一 SELECT 导出的 Fact 固定动作见证，不是 caller 可传回的认证能力。"""

    user_role_id: UUID
    role_id: UUID
    role_permission_id: UUID
    permission_id: UUID


def _tenant_hint(scope_hint: TenantScope) -> str:
    """校验不可信租户提示的 canonical UUID 形态。

    Args:
        scope_hint: 只用于 RLS 定位的租户提示。

    Returns:
        小写连字符 UUID 文本。

    Raises:
        EvidenceReviewUnauthorizedError: 提示不是 canonical 非零 UUID。
    """

    if type(scope_hint) is not TenantScope:
        raise EvidenceReviewUnauthorizedError()
    try:
        tenant_id = scope_hint.tenant_id
        value = tenant_id.value if type(tenant_id) is TenantId else None
        parsed = UUID(value) if type(value) is str else None
    except (TypeError, ValueError, AttributeError):
        # 原解析异常可能携带候选 hint；离开异常上下文后统一拒绝。
        pass
    else:
        if parsed is not None and type(value) is str and parsed.int != 0 and str(parsed) == value:
            return value
    raise EvidenceReviewUnauthorizedError()


def _token_hash(raw_token: bytes) -> str:
    """校验 canonical 32-byte bearer 并只返回其 SHA-256 hex。

    Args:
        raw_token: 43 字符 unpadded base64url ASCII bearer。

    Returns:
        用于数据库等值查询的 64 位小写 hex hash。

    Raises:
        EvidenceReviewUnauthorizedError: bearer 形态非法。
    """

    if type(raw_token) is not bytes or len(raw_token) != _TOKEN_LENGTH:
        raise EvidenceReviewUnauthorizedError()
    if _TOKEN_PATTERN.fullmatch(raw_token) is None:
        raise EvidenceReviewUnauthorizedError()
    decoded: bytes | None = None
    try:
        decoded = base64.b64decode(raw_token + b"=", altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        # 原解码异常可能含输入片段；离开异常上下文后统一拒绝。
        pass
    if decoded is None or len(decoded) != _TOKEN_BYTES:
        raise EvidenceReviewUnauthorizedError()
    if base64.urlsafe_b64encode(decoded).rstrip(b"=") != raw_token:
        raise EvidenceReviewUnauthorizedError()
    return hashlib.sha256(raw_token).hexdigest()


def _checked_connection(session: Session) -> Connection:
    """取得调用者事务连接，并要求 Engine 隐藏 SQL bind 值。

    Args:
        session: 调用者已开启的 PostgreSQL Session。

    Returns:
        本次事务后续所有认证 SQL 共用的 Connection。

    Raises:
        EvidenceReviewUsageError: 调用者未开启事务。
        EvidenceReviewStorageError: 连接的 Engine 未隐藏 bind 参数。
        SQLAlchemyError: 连接故障交外层脱敏。
    """

    if not session.in_transaction():
        raise EvidenceReviewUsageError()
    connection = session.connection()
    if connection.engine.hide_parameters is not True:
        raise EvidenceReviewStorageError()
    return connection


def _set_tenant_context(connection: Connection, tenant_id: str) -> None:
    """在调用者事务中 SET LOCAL 并核 READ COMMITTED/readback。

    Args:
        connection: 已核隐藏参数、属调用者事务的 PostgreSQL Connection。
        tenant_id: 已校验的租户提示 UUID。

    Returns:
        无。

    Raises:
        EvidenceReviewStorageError: readback 或隔离级别不符合契约。
        SQLAlchemyError: SQL 故障交外层脱敏。
    """

    assigned = connection.execute(
        text(f"SELECT set_config('{TENANT_CONTEXT_SETTING}', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    ).scalar_one()
    row = connection.execute(
        text(
            f"SELECT current_setting('{TENANT_CONTEXT_SETTING}', true), "
            "current_setting('transaction_isolation')"
        )
    ).one()
    if assigned != tenant_id or row[0] != tenant_id or row[1] != _READ_COMMITTED:
        raise EvidenceReviewStorageError()


def _required_uuid(row: _AuthRow, index: int) -> UUID:
    """读取授权查询返回的非零 UUID。

    Args:
        row: 已命中的授权查询行。
        index: 固定 SQL 列序下标。

    Returns:
        非零 UUID。

    Raises:
        EvidenceReviewStorageError: 数据库结果类型或值非法。
    """

    value = row[index]
    if type(value) is UUID and value.int != 0:
        return value
    raise EvidenceReviewStorageError()


def _checked_at(row: _AuthRow) -> datetime:
    """读取并归一化同一授权 SELECT 的数据库语句时刻。

    Args:
        row: 已命中的授权查询行。

    Returns:
        UTC aware 授权检查时刻。

    Raises:
        EvidenceReviewStorageError: 数据库结果没有 aware 时刻。
    """

    value = row[3]
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceReviewStorageError()
    return value.astimezone(timezone.utc)


def _granted_auth_row(
    connection: Connection, tenant_id: str, token_hash: str, permission_key: str
) -> _AuthRow:
    """对两个固定动作执行同一条 tenant-private grant 查询。

    Args:
        connection: 已核隐藏参数及租户上下文的调用者事务连接。
        tenant_id: canonical 租户查询提示，不代表主体。
        token_hash: canonical bearer 的临时 SHA-256 hex bind。
        permission_key: 仅模块内 Claim review 或 Fact promote 固定常量。

    Returns:
        同一语句命中的 token、主体、时刻及完整 grant 行。

    Raises:
        EvidenceReviewUsageError: purpose 不是两个允许的真实字符串。
        EvidenceReviewUnauthorizedError: active bearer 或固定 grant 不匹配。
        SQLAlchemyError: 数据库故障交动作入口脱敏。
    """

    if type(permission_key) is not str or permission_key not in (
        REVIEW_PERMISSION_KEY, FACT_PROMOTION_PERMISSION_KEY
    ):
        raise EvidenceReviewUsageError()
    parameters = {
        "tenant_id": tenant_id,
        "token_hash": token_hash,
        "active_status": _ACTIVE_STATUS,
        "permission_key": permission_key,
    }
    row = connection.execute(text(_REVIEWER_SQL), parameters).first()
    if row is None:
        raise EvidenceReviewUnauthorizedError()
    return row


def _auth_row(connection: Connection, tenant_id: str, token_hash: str, *, reviewer: bool) -> _AuthRow:
    """按动作执行唯一一条令牌/RBAC 授权 SELECT。

    Args:
        connection: 已设置租户上下文、隐藏参数的调用者事务连接。
        tenant_id: 不可信租户提示，仅用于匹配与 RLS。
        token_hash: canonical bearer 的 SHA-256 hex，仅作 SQL bind。
        reviewer: 为真时同一 SELECT 加入完整 grant 链。

    Returns:
        命中的数据库行；actor 始终从 token 行推导。

    Raises:
        EvidenceReviewUnauthorizedError: 令牌或 reviewer grant 不匹配。
        SQLAlchemyError: SQL 故障交外层脱敏。
    """

    if reviewer:
        return _granted_auth_row(connection, tenant_id, token_hash, REVIEW_PERMISSION_KEY)
    parameters = {"tenant_id": tenant_id, "token_hash": token_hash, "active_status": _ACTIVE_STATUS}
    row = connection.execute(text(_ACTOR_SQL), parameters).first()
    if row is None:
        raise EvidenceReviewUnauthorizedError()
    return row


def authorize_active_actor(
    session: Session, scope_hint: TenantScope, raw_token: bytes
) -> ActorAuthWitness:
    """在同一 READ COMMITTED 事务中验证 active bearer 主体。

    供后续 ``begin_claim_revision`` 使用；此动作不要求 reviewer grant。
    调用者负责提交或回滚，必须在任何受保护写入前调用。

    Args:
        session: 调用者已开启的 PG Session 事务。
        scope_hint: 不可信租户 lookup hint。
        raw_token: 高熵 bearer 的 canonical ASCII bytes。

    Returns:
        仅含 token-derived tenant/user/token 与数据库时刻的见证。

    Raises:
        EvidenceReviewUnauthorizedError: 提示、令牌或 active 状态不符。
        EvidenceReviewUsageError: 没有调用者事务。
        EvidenceReviewStorageError: PG 上下文、隔离或持久结果故障。
    """

    tenant_id = _tenant_hint(scope_hint)
    token_hash = _token_hash(raw_token)
    try:
        connection = _checked_connection(session)
        _set_tenant_context(connection, tenant_id)
        row = _auth_row(connection, tenant_id, token_hash, reviewer=False)
        return ActorAuthWitness(
            tenant_id=_required_uuid(row, 0),
            user_id=_required_uuid(row, 1),
            token_id=_required_uuid(row, 2),
            checked_at=_checked_at(row),
            policy_key=ACTIVE_ACTOR_POLICY_KEY,
        )
    except SQLAlchemyError:
        # 离开 except 再抛固定错误，切断可能含 token hash 的 SQLAlchemy cause。
        pass
    raise EvidenceReviewStorageError()


def authorize_fact_promoter(
    session: Session, scope_hint: TenantScope, raw_token: bytes
) -> FactPromoterAuthWitness:
    """在调用者事务的一个语句快照内查询固定 Fact 晋升权限。

    本函数不执行晋升、不写 auth 或业务表，也不承诺后续提交时权限仍有效。
    返回见证不作为公共输入；未来受保护操作须在自己的事务内重新查询。

    Args:
        session: 调用者已经开启的 READ COMMITTED PostgreSQL Session。
        scope_hint: 仅用于 RLS 定位的不可信 canonical 租户提示。
        raw_token: canonical 32-byte bearer 的 unpadded ASCII bytes。

    Returns:
        token-derived 身份、语句开始时刻和同一 grant 链的 typed 见证。

    Raises:
        EvidenceReviewUnauthorizedError: bearer、active 状态或固定权限不符。
        EvidenceReviewUsageError: 没有调用者事务。
        EvidenceReviewStorageError: bind/context/isolation 或八列投影非法。
    """

    tenant_id = _tenant_hint(scope_hint)
    token_hash = _token_hash(raw_token)
    try:
        connection = _checked_connection(session)
        _set_tenant_context(connection, tenant_id)
        row = _granted_auth_row(connection, tenant_id, token_hash, FACT_PROMOTION_PERMISSION_KEY)
        if len(row) != _GRANTED_AUTH_ROW_COLUMNS:
            raise EvidenceReviewStorageError()
        return FactPromoterAuthWitness(
            tenant_id=_required_uuid(row, 0),
            user_id=_required_uuid(row, 1),
            token_id=_required_uuid(row, 2),
            checked_at=_checked_at(row),
            policy_key=FACT_PROMOTION_PERMISSION_KEY,
            user_role_id=_required_uuid(row, 4),
            role_id=_required_uuid(row, 5),
            role_permission_id=_required_uuid(row, 6),
            permission_id=_required_uuid(row, 7),
        )
    except SQLAlchemyError:
        # 退出 SQLAlchemy 异常上下文再抛固定错误，避免携带敏感 bind 或 cause。
        pass
    raise EvidenceReviewStorageError()


def authorize_reviewer(
    session: Session, scope_hint: TenantScope, raw_token: bytes
) -> ReviewerAuthWitness:
    """在同一 SELECT 中验证 active bearer 与显式 reviewer grant。

    供后续 ``record_claim_review``/``resolve_conflict_with_review`` 使用；
    不接受 caller reviewer ID、permission ID 或授权时刻。

    Args:
        session: 调用者已开启的 PG Session 事务。
        scope_hint: 不可信租户 lookup hint。
        raw_token: 高熵 bearer 的 canonical ASCII bytes。

    Returns:
        token-derived actor 与同一语句命中的 grant/permission 见证。

    Raises:
        EvidenceReviewUnauthorizedError: 提示、令牌或 grant 不符。
        EvidenceReviewUsageError: 没有调用者事务。
        EvidenceReviewStorageError: PG 上下文、隔离或持久结果故障。
    """

    tenant_id = _tenant_hint(scope_hint)
    token_hash = _token_hash(raw_token)
    try:
        connection = _checked_connection(session)
        _set_tenant_context(connection, tenant_id)
        row = _auth_row(connection, tenant_id, token_hash, reviewer=True)
        return ReviewerAuthWitness(
            tenant_id=_required_uuid(row, 0),
            user_id=_required_uuid(row, 1),
            token_id=_required_uuid(row, 2),
            checked_at=_checked_at(row),
            policy_key=REVIEW_PERMISSION_KEY,
            user_role_id=_required_uuid(row, 4),
            role_id=_required_uuid(row, 5),
            role_permission_id=_required_uuid(row, 6),
            permission_id=_required_uuid(row, 7),
        )
    except SQLAlchemyError:
        # 离开 except 再抛固定错误，切断可能含 token hash 的 SQLAlchemy cause。
        pass
    raise EvidenceReviewStorageError()
