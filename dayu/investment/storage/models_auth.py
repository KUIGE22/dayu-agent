"""投资平台 RBAC 与令牌域 ORM 模型。

本模块定义 ``dayu_platform`` schema 中 5 张 RBAC/auth 域表：

- ``roles`` / ``permissions``：租户内角色与权限；
- ``user_roles`` / ``role_permissions``：join 表，append-only，
  无 ``updated_at/version``；
- ``api_tokens``：只保存 token hash，禁止 raw token。

设计约束（与 ``dayu/investment/storage/migrations`` 真源保持一致）：

- UUID 全部由调用方提供，无 server random default；
- ``created_at/updated_at`` 为 ``TIMESTAMPTZ NOT NULL DEFAULT
  transaction_timestamp()``；
- 文本业务键必须非空且无首尾空白，``version`` 为
  ``INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)``；
- join 表通过复合 FK ``(tenant_id, user_id/role_id/permission_id)``
  约束同租户引用，禁止跨租户关联；
- 全部私有表由 migration 启用 ``FORCE ROW LEVEL SECURITY``。

CheckConstraint 只声明语义短名（如 ``status``），最终约束名由
naming convention 生成 ``ck_<table>_<short>``，与迁移 DDL 完全一致；
显式短名必须保持表内唯一，且最终名不超过 PostgreSQL 63 字符限制。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from dayu.investment.storage.db import PlatformBase


class Role(PlatformBase):
    """租户内角色模型。

    ``name`` 在租户内唯一；``is_system`` 标记系统预置角色。
    """

    __tablename__ = "roles"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey("organizations.id", name="fk_roles_tenant_id_organizations", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default=text("''"), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_roles_tenant_id_id"),
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_id_name"),
        CheckConstraint("name <> '' AND name = btrim(name)", name="name_nonblank"),
        CheckConstraint("version > 0", name="version_positive"),
    )


class Permission(PlatformBase):
    """租户内权限模型。

    ``permission_key`` 在租户内唯一；权限以显式 key 表达，不做
    role-name 分支。
    """

    __tablename__ = "permissions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey("organizations.id", name="fk_permissions_tenant_id_organizations", ondelete="RESTRICT"),
        nullable=False,
    )
    permission_key: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default=text("''"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_permissions_tenant_id_id"),
        UniqueConstraint("tenant_id", "permission_key", name="uq_permissions_tenant_id_permission_key"),
        CheckConstraint(
            "permission_key <> '' AND permission_key = btrim(permission_key)",
            name="permission_key_nonblank",
        ),
        CheckConstraint("version > 0", name="version_positive"),
    )


class UserRole(PlatformBase):
    """用户-角色 join 表 append-only 模型。

    复合 FK ``(tenant_id, user_id) -> users`` 与
    ``(tenant_id, role_id) -> roles`` 保证同租户关联；无
    ``updated_at/version``。
    """

    __tablename__ = "user_roles"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey("organizations.id", name="fk_user_roles_tenant_id_organizations", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    role_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_user_roles_tenant_id_id"),
        UniqueConstraint("tenant_id", "user_id", "role_id", name="uq_user_roles_tenant_id_user_id_role_id"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_user_roles_tenant_user_users",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name="fk_user_roles_tenant_role_roles",
            ondelete="RESTRICT",
        ),
    )


class RolePermission(PlatformBase):
    """角色-权限 join 表 append-only 模型。

    复合 FK ``(tenant_id, role_id) -> roles`` 与
    ``(tenant_id, permission_id) -> permissions`` 保证同租户关联；
    无 ``updated_at/version``。
    """

    __tablename__ = "role_permissions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey("organizations.id", name="fk_role_permissions_tenant_id_organizations", ondelete="RESTRICT"),
        nullable=False,
    )
    role_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    permission_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_role_permissions_tenant_id_id"),
        UniqueConstraint(
            "tenant_id", "role_id", "permission_id", name="uq_role_permissions_tenant_id_role_id_permission_id"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name="fk_role_permissions_tenant_role_roles",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "permission_id"],
            ["permissions.tenant_id", "permissions.id"],
            name="fk_role_permissions_tenant_permission_permissions",
            ondelete="RESTRICT",
        ),
    )


class ApiToken(PlatformBase):
    """API 令牌模型。

    只保存 ``token_hash``（64 位小写 hex），禁止保存 raw token；
    ``(tenant_id, user_id)`` 复合 FK 保证同租户用户。
    """

    __tablename__ = "api_tokens"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey("organizations.id", name="fk_api_tokens_tenant_id_organizations", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_api_tokens_tenant_id_id"),
        UniqueConstraint("token_hash", name="uq_api_tokens_token_hash"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_api_tokens_tenant_user_users",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked', 'expired')",
            name="status",
        ),
        CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name="token_hash_lowercase_hex",
        ),
        CheckConstraint("name <> '' AND name = btrim(name)", name="name_nonblank"),
        CheckConstraint("version > 0", name="version_positive"),
    )


__all__ = [
    "ApiToken",
    "Permission",
    "Role",
    "RolePermission",
    "UserRole",
]
