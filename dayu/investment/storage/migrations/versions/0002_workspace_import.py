"""旧 workspace 显式导入 schema 迁移（S15-CTRL-08）。

Revision ID: 0002_workspace_import
Revises: 0001_platform_foundation
Create Date: 2026-08-11

本迁移以 bootstrap superuser 在单次事务中新增且只新增两张
tenant-scoped append-only 私有表：

- ``workspace_import_markers``：import marker，只表示 completed
  commit，不设 pending/failed status；
- ``research_bundle_locators``：research bundle locator，公司只能经
  ``security_id -> securities.company_id`` 唯一解析，无冗余
  ``company_id`` 列。

两表为 private tenant tables，必须 ``ENABLE + FORCE ROW LEVEL
SECURITY``，唯一 policy 复用现有 ``app.tenant_id`` expression；app
仅 marker/locator ``SELECT/INSERT``，audit ``SELECT``，PUBLIC 全
revoke，default privileges 维持；禁止 application UPDATE/DELETE。
``repository_key='legacy-workspace'`` 是当前 closed enum，新 repository
必须另做 migration，不在本迁移放宽 CHECK。

downgrade 先用 PostgreSQL catalog 拒绝 0002 tables/policies 之外的
外部依赖（表内 locator/marker rows 不构成外部依赖），再按
locator -> marker 顺序删除 0002 policy/grants/tables；保留 0001 的
13 表/roles/schema/default org；禁止 CASCADE。Alembic version table
保留在 bootstrap-owned 默认 schema，不在本迁移删除范围内。
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection

from dayu.investment.storage.db import (
    PLATFORM_APP_ROLE,
    PLATFORM_AUDIT_ROLE,
    PLATFORM_SCHEMA_NAME,
)

revision = "0002_workspace_import"
down_revision = "0001_platform_foundation"
branch_labels = None
depends_on = None

_TENANT_EXPRESSION = "nullif(current_setting('app.tenant_id', true), '')::uuid"
"""RLS tenant policy 使用的租户上下文表达式（与 0001 一致）。"""

_MARKER_TABLE = "workspace_import_markers"
_LOCATOR_TABLE = "research_bundle_locators"


def _create_tables() -> None:
    """创建 0002 两张表及其全部约束与索引。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.workspace_import_markers (
            id UUID CONSTRAINT pk_workspace_import_markers PRIMARY KEY,
            tenant_id UUID NOT NULL,
            migration_id TEXT NOT NULL,
            source_schema_version INTEGER NOT NULL,
            source_root_fingerprint CHAR(64) NOT NULL,
            staged_payload_sha256 CHAR(64) NOT NULL,
            company_count INTEGER NOT NULL,
            security_count INTEGER NOT NULL,
            source_definition_count INTEGER NOT NULL,
            bundle_count INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_workspace_import_markers_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_workspace_import_markers_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_workspace_import_markers_tenant_id_migration_id
                UNIQUE (tenant_id, migration_id),
            CONSTRAINT ck_workspace_import_markers_source_schema_version_positive
                CHECK (source_schema_version > 0),
            CONSTRAINT ck_workspace_import_markers_company_count_nonnegative
                CHECK (company_count >= 0),
            CONSTRAINT ck_workspace_import_markers_security_count_nonnegative
                CHECK (security_count >= 0),
            CONSTRAINT ck_workspace_import_markers_source_definition_count_nonnegative
                CHECK (source_definition_count >= 0),
            CONSTRAINT ck_workspace_import_markers_bundle_count_nonnegative
                CHECK (bundle_count >= 0)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.research_bundle_locators (
            id UUID CONSTRAINT pk_research_bundle_locators PRIMARY KEY,
            tenant_id UUID NOT NULL,
            import_marker_id UUID NOT NULL,
            security_id UUID NOT NULL,
            template_name TEXT NOT NULL,
            repository_key TEXT NOT NULL,
            relative_locator TEXT NOT NULL,
            bundle_sha256 CHAR(64) NOT NULL,
            artifact_manifest_sha256 CHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_research_bundle_locators_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_research_bundle_locators_security_id_securities
                FOREIGN KEY (security_id) REFERENCES {PLATFORM_SCHEMA_NAME}.securities (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_research_bundle_locators_tenant_marker_markers
                FOREIGN KEY (tenant_id, import_marker_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.workspace_import_markers (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_research_bundle_locators_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_research_bundle_locators_tenant_security_template
                UNIQUE (tenant_id, security_id, template_name),
            CONSTRAINT uq_research_bundle_locators_tenant_repository_locator
                UNIQUE (tenant_id, repository_key, relative_locator),
            CONSTRAINT ck_research_bundle_locators_repository_key_legacy_workspace
                CHECK (repository_key = 'legacy-workspace')
        )
        """
    )


def _grant_matrix() -> None:
    """清理 PUBLIC 权限并按最小权限矩阵授予 app/audit。

    0001 已设置 schema 级 default privileges 仅 revoke PUBLIC；本迁移
    继续维持该不变式，并只授予 marker/locator 的 SELECT/INSERT。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in (_MARKER_TABLE, _LOCATOR_TABLE):
        op.execute(
            f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM PUBLIC"
        )
    op.execute(
        f"GRANT SELECT, INSERT ON TABLE {PLATFORM_SCHEMA_NAME}.{_MARKER_TABLE} TO {PLATFORM_APP_ROLE}"
    )
    op.execute(
        f"GRANT SELECT, INSERT ON TABLE {PLATFORM_SCHEMA_NAME}.{_LOCATOR_TABLE} TO {PLATFORM_APP_ROLE}"
    )
    for table_name in (_MARKER_TABLE, _LOCATOR_TABLE):
        op.execute(
            f"GRANT SELECT ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} TO {PLATFORM_AUDIT_ROLE}"
        )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA "
        f"{PLATFORM_SCHEMA_NAME} REVOKE ALL ON TABLES FROM PUBLIC"
    )


def _enable_rls() -> None:
    """为两张私有表启用并强制 RLS，创建唯一 tenant_isolation policy。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in (_MARKER_TABLE, _LOCATOR_TABLE):
        op.execute(
            f"ALTER TABLE {PLATFORM_SCHEMA_NAME}.{table_name} ENABLE ROW LEVEL SECURITY"
        )
        op.execute(
            f"ALTER TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {PLATFORM_SCHEMA_NAME}.{table_name}
            FOR ALL TO {PLATFORM_APP_ROLE}
            USING ({_TENANT_EXPRESSION} = tenant_id)
            WITH CHECK ({_TENANT_EXPRESSION} = tenant_id)
            """
        )


def _drop_policies() -> None:
    """删除两张 0002 表的 tenant_isolation policy。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in (_MARKER_TABLE, _LOCATOR_TABLE):
        op.execute(
            f"DROP POLICY tenant_isolation ON {PLATFORM_SCHEMA_NAME}.{table_name}"
        )


def _revoke_grants() -> None:
    """撤销 0002 表的 app/audit grants 并清理 PUBLIC。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in (_MARKER_TABLE, _LOCATOR_TABLE):
        op.execute(
            f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM PUBLIC"
        )
        op.execute(
            f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM {PLATFORM_APP_ROLE}"
        )
        op.execute(
            f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM {PLATFORM_AUDIT_ROLE}"
        )


def _0002_table_oids(bind: Connection) -> list[str]:
    """返回 0002 两张表在 ``dayu_platform`` schema 中的 OID 列表。

    Args:
        bind: Alembic 连接绑定。

    Returns:
        0002 两张表的 ``pg_class.oid`` 字符串列表。

    Raises:
        无。
    """

    rows = bind.execute(
        text(
            "SELECT c.oid FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE n.nspname = '{PLATFORM_SCHEMA_NAME}' "
            f"AND c.relname IN ('{_MARKER_TABLE}', '{_LOCATOR_TABLE}')"
        )
    ).fetchall()
    return [str(row[0]) for row in rows]


def _downgrade_admission() -> None:
    """downgrade 破坏性 DDL 前的显式外部依赖 preflight。

    在删除 0002 policy/grants/tables 之前，先查询 ``pg_depend``：存在
    任何非 0002 owner 的对象（外部 view/rule，或其它表的 FK 引用
    0002 表）时，整次 downgrade fail closed 并回滚。0002 表自身的
    row type / toast 表 / attrdef / index / constraint / policy /
    trigger 与表内 locator/marker rows 均不构成外部依赖，也不会阻止
    无 CASCADE 的 ``DROP TABLE``。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 存在 0002 owner 之外的外部依赖时抛出，消息只
            描述违规类别，不包含 DSN/credential。
    """

    bind = op.get_bind()
    table_oids = _0002_table_oids(bind)
    if not table_oids:
        return
    oid_list = ", ".join(table_oids)
    external_dependency_count = bind.execute(
        text(
            "SELECT count(*) FROM pg_depend d "
            "WHERE d.refclassid = 'pg_class'::regclass "
            f"AND d.refobjid IN ({oid_list}) "
            "AND ("
            "  d.classid = 'pg_rewrite'::regclass "
            "  OR (d.classid = 'pg_constraint'::regclass AND d.objid NOT IN ("
            "        SELECT con.oid FROM pg_constraint con WHERE con.conrelid IN "
            f"        ({oid_list})))"
            ")"
        )
    ).scalar()
    if external_dependency_count and int(external_dependency_count) > 0:
        raise RuntimeError(
            "downgrade 拒绝：workspace_import_markers / research_bundle_locators "
            "存在 0002 owner 之外的外部依赖（外部 view/rule 或其它表的 FK），请先清理"
        )


def _drop_tables() -> None:
    """按引用顺序删除 0002 两张表（locator -> marker，无 CASCADE）。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"DROP TABLE {PLATFORM_SCHEMA_NAME}.{_LOCATOR_TABLE}"
    )
    op.execute(
        f"DROP TABLE {PLATFORM_SCHEMA_NAME}.{_MARKER_TABLE}"
    )


def upgrade() -> None:
    """新增 0002 两张表、RLS policy 与最小权限 grants。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    _create_tables()
    _grant_matrix()
    _enable_rls()


def downgrade() -> None:
    """精确回滚 0002 的 policy/grants/tables。

    在任何破坏性 DDL 前先执行 ``_downgrade_admission``：存在 0002
    owner 之外的外部依赖时整次 fail closed 并回滚，保留 0001 的
    13 表/roles/schema/default org。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 存在外部依赖时抛出，整次回滚。
    """

    _downgrade_admission()
    _drop_policies()
    _revoke_grants()
    _drop_tables()
