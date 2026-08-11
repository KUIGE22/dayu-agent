"""投资平台存储子包。

``dayu.investment.storage`` 承载投资平台 PostgreSQL 存储实现：

- ``db.py``：engine / session factory、确定性 metadata naming
  convention、平台 schema/role/tenant 常量与迁移 admission 错误；
- ``models_identity.py`` / ``models_auth.py`` / ``models_workspace_import.py``：
  ``dayu_platform`` schema 15 张表的 SQLAlchemy ORM 声明；
- ``migrations/``：Alembic 迁移真源（transactional upgrade/downgrade、
  RBAC group role、RLS policy、最小权限 GRANT、default organization
  seed）。

本子包属于 SQL storage implementation 层：允许依赖 SQLAlchemy /
psycopg / Alembic 与 pure domain，禁止依赖 Web、Service、Host、Agent、
CLI、Broker SDK 或未来 slice。schema 的唯一创建真源是 Alembic
migration，任何 import 路径都不得调用 ``metadata.create_all()``。
"""

from dayu.investment.storage.db import (
    DEFAULT_ORGANIZATION_ID,
    DEFAULT_ORGANIZATION_SLUG,
    NAMING_CONVENTION,
    PLATFORM_APP_ROLE,
    PLATFORM_AUDIT_ROLE,
    PLATFORM_SCHEMA_NAME,
    PlatformBase,
    PlatformMigrationAdmissionError,
    TENANT_CONTEXT_SETTING,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage.models_auth import ApiToken, Permission, Role, RolePermission, UserRole
from dayu.investment.storage.models_identity import (
    Company,
    Organization,
    Security,
    SourceDefinition,
    SourceHealthSnapshot,
    SourceSubscription,
    SourceSyncRun,
    User,
)
from dayu.investment.storage.models_workspace_import import (
    ResearchBundleLocator,
    WorkspaceImportMarker,
)

__all__ = [
    "ApiToken",
    "Company",
    "DEFAULT_ORGANIZATION_ID",
    "DEFAULT_ORGANIZATION_SLUG",
    "NAMING_CONVENTION",
    "Organization",
    "Permission",
    "PLATFORM_APP_ROLE",
    "PLATFORM_AUDIT_ROLE",
    "PLATFORM_SCHEMA_NAME",
    "PlatformBase",
    "PlatformMigrationAdmissionError",
    "ResearchBundleLocator",
    "Role",
    "RolePermission",
    "Security",
    "SourceDefinition",
    "SourceHealthSnapshot",
    "SourceSubscription",
    "SourceSyncRun",
    "TENANT_CONTEXT_SETTING",
    "User",
    "UserRole",
    "WorkspaceImportMarker",
    "create_platform_engine",
    "create_platform_session_factory",
]
