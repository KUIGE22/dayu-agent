"""投资平台 workspace import 两表 ORM 模型（S15-CTRL-08）。

本模块定义 ``dayu_platform`` schema 中 0002 迁移新增的两张
tenant-scoped append-only 表：

- ``workspace_import_markers``：import marker，只表示 completed commit，
  不设 pending/failed status；
- ``research_bundle_locators``：research bundle locator，公司只能经
  ``security_id -> securities.company_id`` 唯一解析，无冗余
  ``company_id`` 列。

设计约束（与迁移 DDL 真源保持一致，且逐列符合 S15-CTRL-08）：

- UUID 全部由调用方提供，无 server random default；
- ``created_at`` 为 ``TIMESTAMPTZ NOT NULL DEFAULT
  transaction_timestamp()``，无 ``updated_at/version``（append-only）；
- ``source_schema_version`` 必须 ``> 0``，四个 count 必须 ``>= 0``，
  ``repository_key`` 必须精确等于 ``legacy-workspace``（closed enum）；
- 两表均为私有 tenant 表，由 migration 启用 ``FORCE ROW LEVEL
  SECURITY`` 与唯一 ``tenant_isolation`` policy（``app.tenant_id``）；
  application 只允许 SELECT/INSERT，禁止 UPDATE/DELETE。

CheckConstraint 只声明语义短名，最终约束名由 naming convention 生成
``ck_<table>_<short>``，与迁移 DDL 完全一致。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
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


class WorkspaceImportMarker(PlatformBase):
    """import marker 模型（append-only，只表示 completed commit）。

    ``(tenant_id, migration_id)`` 租户内唯一；``created_at`` 由数据库
    ``transaction_timestamp()`` 生成，无 ``updated_at/version``。
    """

    __tablename__ = "workspace_import_markers"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey(
            "organizations.id",
            name="fk_workspace_import_markers_tenant_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    migration_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_root_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    staged_payload_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    company_count: Mapped[int] = mapped_column(Integer, nullable=False)
    security_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_definition_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bundle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_workspace_import_markers_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "migration_id",
            name="uq_workspace_import_markers_tenant_id_migration_id",
        ),
        CheckConstraint("source_schema_version > 0", name="source_schema_version_positive"),
        CheckConstraint("company_count >= 0", name="company_count_nonnegative"),
        CheckConstraint("security_count >= 0", name="security_count_nonnegative"),
        CheckConstraint("source_definition_count >= 0", name="source_definition_count_nonnegative"),
        CheckConstraint("bundle_count >= 0", name="bundle_count_nonnegative"),
    )


class ResearchBundleLocator(PlatformBase):
    """research bundle locator 模型（append-only）。

    公司只能经 ``security_id -> securities.company_id`` 唯一解析，
    schema 中不存在冗余 ``company_id`` 列；``(tenant_id,
    import_marker_id)`` 复合 FK 引用 marker 的 ``(tenant_id, id)``。
    """

    __tablename__ = "research_bundle_locators"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey(
            "organizations.id",
            name="fk_research_bundle_locators_tenant_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    import_marker_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[Uuid] = mapped_column(
        ForeignKey(
            "securities.id",
            name="fk_research_bundle_locators_security_id_securities",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    template_name: Mapped[str] = mapped_column(Text, nullable=False)
    repository_key: Mapped[str] = mapped_column(Text, nullable=False)
    relative_locator: Mapped[str] = mapped_column(Text, nullable=False)
    bundle_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    artifact_manifest_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_research_bundle_locators_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "security_id",
            "template_name",
            name="uq_research_bundle_locators_tenant_security_template",
        ),
        UniqueConstraint(
            "tenant_id",
            "repository_key",
            "relative_locator",
            name="uq_research_bundle_locators_tenant_repository_locator",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "import_marker_id"],
            ["workspace_import_markers.tenant_id", "workspace_import_markers.id"],
            name="fk_research_bundle_locators_tenant_marker_markers",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "repository_key = 'legacy-workspace'",
            name="repository_key_legacy_workspace",
        ),
    )


__all__ = [
    "ResearchBundleLocator",
    "WorkspaceImportMarker",
]
