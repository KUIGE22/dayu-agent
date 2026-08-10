"""平台基础 schema 迁移。

Revision ID: 0001_platform_foundation
Revises: (none)
Create Date: 2026-08-10

本迁移以 bootstrap superuser 在单次事务中创建 ``dayu_platform``
schema 的全部 owner 对象：

- 两个 group role：``dayu_platform_app``（NOLOGIN/NOBYPASSRLS/无DDL）
  与 ``dayu_platform_audit``（NOLOGIN/BYPASSRLS/只读）；
- 13 张表（3 张公共 reference + 10 张私有表）及全部
  列/FK/unique/check/index 契约；
- default organization 种子（固定 UUID，幂等）；
- PUBLIC 权限清理、app/audit 最小权限矩阵、schema default privileges
  仅 revoke PUBLIC；
- 私有表 ``ENABLE + FORCE ROW LEVEL SECURITY`` 与唯一
  ``tenant_isolation`` policy（``app.tenant_id`` 上下文）。

downgrade 按 owner 顺序精确回滚：policy -> 13 张表 -> schema
``RESTRICT`` -> 两个 group role；禁止 CASCADE，存在外部 member/
session/dependency 时整次失败回滚。Alembic version table 保留在
bootstrap-owned 默认 schema，不在本迁移删除范围内。
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

from dayu.investment.storage.db import (
    PLATFORM_APP_ROLE,
    PLATFORM_AUDIT_ROLE,
    PLATFORM_SCHEMA_NAME,
)

revision = "0001_platform_foundation"
down_revision = None
branch_labels = None
depends_on = None

# 私有表（启用 RLS）：organizations 以 id 比较，其余以 tenant_id 比较。
_PRIVATE_TABLES: tuple[str, ...] = (
    "organizations",
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "api_tokens",
    "source_subscriptions",
    "source_sync_runs",
    "source_health_snapshots",
)

# 公共 reference（不启用 RLS）。
_PUBLIC_TABLES: tuple[str, ...] = ("companies", "securities", "source_definitions")

# app 可 DML 的私有表权限分类（按计划权限矩阵）。
_APP_UPDATE_TABLES: tuple[str, ...] = (
    "organizations",
    "users",
    "roles",
    "permissions",
    "api_tokens",
    "source_subscriptions",
)
_APP_JOIN_TABLES: tuple[str, ...] = ("user_roles", "role_permissions")
_APP_APPEND_TABLES: tuple[str, ...] = ("source_sync_runs", "source_health_snapshots")

_TENANT_EXPRESSION = "nullif(current_setting('app.tenant_id', true), '')::uuid"
"""RLS tenant policy 使用的租户上下文表达式。"""


def _create_group_roles() -> None:
    """创建 app/audit group role（fail closed on 已存在）。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 同名 role 已存在时抛出，禁止接管未知 owner。
    """

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dayu_platform_app') THEN
                RAISE EXCEPTION 'role dayu_platform_app already exists';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dayu_platform_audit') THEN
                RAISE EXCEPTION 'role dayu_platform_audit already exists';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        "CREATE ROLE dayu_platform_app "
        "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )
    op.execute(
        "CREATE ROLE dayu_platform_audit "
        "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS"
    )


def _create_schema() -> None:
    """创建 ``dayu_platform`` schema（fail closed on 已存在）。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 同名 schema 已存在时抛出，禁止接管未知 owner。
    """

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'dayu_platform') THEN
                RAISE EXCEPTION 'schema dayu_platform already exists';
            END IF;
        END
        $$;
        """
    )
    op.execute("CREATE SCHEMA dayu_platform")


def _create_tables() -> None:
    """创建 13 张表及其全部约束与索引。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        """
        CREATE TABLE dayu_platform.organizations (
            id UUID CONSTRAINT pk_organizations PRIMARY KEY,
            slug TEXT NOT NULL,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT uq_organizations_slug UNIQUE (slug),
            CONSTRAINT ck_organizations_status CHECK (status IN ('active', 'disabled')),
            CONSTRAINT ck_organizations_slug_nonblank CHECK (slug <> '' AND slug = btrim(slug)),
            CONSTRAINT ck_organizations_version_positive CHECK (version > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.companies (
            id UUID CONSTRAINT pk_companies PRIMARY KEY,
            legal_name TEXT NOT NULL,
            lei TEXT,
            country_code VARCHAR(2),
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT uq_companies_lei UNIQUE (lei),
            CONSTRAINT ck_companies_country_code_upper_2 CHECK (
                country_code IS NULL OR (upper(country_code) = country_code AND length(country_code) = 2)
            ),
            CONSTRAINT ck_companies_lei_nonblank CHECK (lei IS NULL OR (lei <> '' AND lei = btrim(lei))),
            CONSTRAINT ck_companies_version_positive CHECK (version > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.securities (
            id UUID CONSTRAINT pk_securities PRIMARY KEY,
            company_id UUID NOT NULL,
            ticker TEXT NOT NULL,
            exchange_mic VARCHAR(4) NOT NULL,
            security_type TEXT NOT NULL,
            currency CHAR(3) NOT NULL,
            isin TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_securities_company_id_companies
                FOREIGN KEY (company_id) REFERENCES dayu_platform.companies (id) ON DELETE RESTRICT,
            CONSTRAINT uq_securities_exchange_mic_ticker UNIQUE (exchange_mic, ticker),
            CONSTRAINT uq_securities_isin UNIQUE (isin),
            CONSTRAINT ck_securities_exchange_mic_upper_4 CHECK (
                exchange_mic = upper(exchange_mic) AND length(exchange_mic) = 4
            ),
            CONSTRAINT ck_securities_security_type CHECK (
                security_type IN ('equity', 'adr', 'etf', 'fund', 'bond', 'other')
            ),
            CONSTRAINT ck_securities_currency_upper CHECK (currency = upper(currency)),
            CONSTRAINT ck_securities_ticker_nonblank CHECK (ticker <> '' AND ticker = btrim(ticker)),
            CONSTRAINT ck_securities_isin_nonblank CHECK (isin IS NULL OR (isin <> '' AND isin = btrim(isin))),
            CONSTRAINT ck_securities_version_positive CHECK (version > 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_securities_company_id ON dayu_platform.securities (company_id)")
    op.execute(
        """
        CREATE TABLE dayu_platform.source_definitions (
            id UUID CONSTRAINT pk_source_definitions PRIMARY KEY,
            source_key TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            display_name TEXT NOT NULL,
            enabled_by_default BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT uq_source_definitions_source_key UNIQUE (source_key),
            CONSTRAINT ck_source_definitions_source_kind CHECK (
                source_kind IN ('filing', 'announcement', 'industry_metric',
                                'research_material', 'market_price', 'fx')
            ),
            CONSTRAINT ck_source_definitions_source_key_nonblank CHECK (
                source_key <> '' AND source_key = btrim(source_key)
            ),
            CONSTRAINT ck_source_definitions_version_positive CHECK (version > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.users (
            id UUID CONSTRAINT pk_users PRIMARY KEY,
            tenant_id UUID NOT NULL,
            subject TEXT NOT NULL,
            email TEXT,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_users_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT uq_users_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_users_tenant_id_subject UNIQUE (tenant_id, subject),
            CONSTRAINT ck_users_status CHECK (status IN ('active', 'disabled', 'locked')),
            CONSTRAINT ck_users_subject_nonblank CHECK (subject <> '' AND subject = btrim(subject)),
            CONSTRAINT ck_users_email_nonblank CHECK (email IS NULL OR email = btrim(email)),
            CONSTRAINT ck_users_version_positive CHECK (version > 0)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_users_tenant_email_lower
            ON dayu_platform.users (tenant_id, lower(email)) WHERE email IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.roles (
            id UUID CONSTRAINT pk_roles PRIMARY KEY,
            tenant_id UUID NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_system BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_roles_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT uq_roles_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_roles_tenant_id_name UNIQUE (tenant_id, name),
            CONSTRAINT ck_roles_name_nonblank CHECK (name <> '' AND name = btrim(name)),
            CONSTRAINT ck_roles_version_positive CHECK (version > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.permissions (
            id UUID CONSTRAINT pk_permissions PRIMARY KEY,
            tenant_id UUID NOT NULL,
            permission_key TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_permissions_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT uq_permissions_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_permissions_tenant_id_permission_key UNIQUE (tenant_id, permission_key),
            CONSTRAINT ck_permissions_permission_key_nonblank CHECK (
                permission_key <> '' AND permission_key = btrim(permission_key)
            ),
            CONSTRAINT ck_permissions_version_positive CHECK (version > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.user_roles (
            id UUID CONSTRAINT pk_user_roles PRIMARY KEY,
            tenant_id UUID NOT NULL,
            user_id UUID NOT NULL,
            role_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_user_roles_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_user_roles_tenant_user_users
                FOREIGN KEY (tenant_id, user_id) REFERENCES dayu_platform.users (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_user_roles_tenant_role_roles
                FOREIGN KEY (tenant_id, role_id) REFERENCES dayu_platform.roles (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_user_roles_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_user_roles_tenant_id_user_id_role_id UNIQUE (tenant_id, user_id, role_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.role_permissions (
            id UUID CONSTRAINT pk_role_permissions PRIMARY KEY,
            tenant_id UUID NOT NULL,
            role_id UUID NOT NULL,
            permission_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_role_permissions_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_role_permissions_tenant_role_roles
                FOREIGN KEY (tenant_id, role_id) REFERENCES dayu_platform.roles (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_role_permissions_tenant_permission_permissions
                FOREIGN KEY (tenant_id, permission_id)
                REFERENCES dayu_platform.permissions (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_role_permissions_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_role_permissions_tenant_id_role_id_permission_id
                UNIQUE (tenant_id, role_id, permission_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.api_tokens (
            id UUID CONSTRAINT pk_api_tokens PRIMARY KEY,
            tenant_id UUID NOT NULL,
            user_id UUID NOT NULL,
            name TEXT NOT NULL,
            token_hash CHAR(64) NOT NULL,
            status TEXT NOT NULL,
            expires_at TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_api_tokens_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_api_tokens_tenant_user_users
                FOREIGN KEY (tenant_id, user_id) REFERENCES dayu_platform.users (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_api_tokens_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_api_tokens_token_hash UNIQUE (token_hash),
            CONSTRAINT ck_api_tokens_status CHECK (status IN ('active', 'revoked', 'expired')),
            CONSTRAINT ck_api_tokens_token_hash_lowercase_hex CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_api_tokens_name_nonblank CHECK (name <> '' AND name = btrim(name)),
            CONSTRAINT ck_api_tokens_version_positive CHECK (version > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.source_subscriptions (
            id UUID CONSTRAINT pk_source_subscriptions PRIMARY KEY,
            tenant_id UUID NOT NULL,
            source_definition_id UUID NOT NULL,
            company_id UUID,
            security_id UUID,
            status TEXT NOT NULL,
            config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_source_subscriptions_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_subscriptions_source_definition_id_source_definitions
                FOREIGN KEY (source_definition_id)
                REFERENCES dayu_platform.source_definitions (id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_subscriptions_company_id_companies
                FOREIGN KEY (company_id) REFERENCES dayu_platform.companies (id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_subscriptions_security_id_securities
                FOREIGN KEY (security_id) REFERENCES dayu_platform.securities (id) ON DELETE RESTRICT,
            CONSTRAINT uq_source_subscriptions_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT ck_source_subscriptions_status CHECK (status IN ('enabled', 'disabled')),
            CONSTRAINT ck_source_subscriptions_target_exclusive CHECK (num_nonnulls(company_id, security_id) <= 1),
            CONSTRAINT ck_source_subscriptions_config_json_object CHECK (jsonb_typeof(config_json) = 'object'),
            CONSTRAINT ck_source_subscriptions_version_positive CHECK (version > 0)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_source_subscriptions_tenant_wide
            ON dayu_platform.source_subscriptions (tenant_id)
            WHERE company_id IS NULL AND security_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_source_subscriptions_company
            ON dayu_platform.source_subscriptions (tenant_id, company_id)
            WHERE company_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_source_subscriptions_security
            ON dayu_platform.source_subscriptions (tenant_id, security_id)
            WHERE security_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.source_sync_runs (
            id UUID CONSTRAINT pk_source_sync_runs PRIMARY KEY,
            tenant_id UUID NOT NULL,
            subscription_id UUID NOT NULL,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            records_discovered INTEGER NOT NULL DEFAULT 0,
            records_ingested INTEGER NOT NULL DEFAULT 0,
            safe_error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_source_sync_runs_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_sync_runs_tenant_subscription_source_subscriptions
                FOREIGN KEY (tenant_id, subscription_id)
                REFERENCES dayu_platform.source_subscriptions (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_source_sync_runs_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_source_sync_runs_tenant_id_idempotency_key UNIQUE (tenant_id, idempotency_key),
            CONSTRAINT ck_source_sync_runs_status CHECK (
                status IN ('planned', 'running', 'succeeded', 'failed', 'cancelled')
            ),
            CONSTRAINT ck_source_sync_runs_records_discovered_nonnegative CHECK (records_discovered >= 0),
            CONSTRAINT ck_source_sync_runs_records_ingested_nonnegative CHECK (records_ingested >= 0),
            CONSTRAINT ck_source_sync_runs_finished_at_after_started_at CHECK (
                finished_at IS NULL OR finished_at >= started_at
            ),
            CONSTRAINT ck_source_sync_runs_idempotency_key_nonblank CHECK (
                idempotency_key <> '' AND idempotency_key = btrim(idempotency_key)
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_source_sync_runs_tenant_subscription_started
            ON dayu_platform.source_sync_runs (tenant_id, subscription_id, started_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE dayu_platform.source_health_snapshots (
            id UUID CONSTRAINT pk_source_health_snapshots PRIMARY KEY,
            tenant_id UUID NOT NULL,
            subscription_id UUID NOT NULL,
            sync_run_id UUID,
            observed_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER,
            safe_error_code TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_source_health_snapshots_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_health_snapshots_tenant_subscription
                FOREIGN KEY (tenant_id, subscription_id)
                REFERENCES dayu_platform.source_subscriptions (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_health_snapshots_tenant_sync_run
                FOREIGN KEY (tenant_id, sync_run_id)
                REFERENCES dayu_platform.source_sync_runs (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_source_health_snapshots_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT ck_source_health_snapshots_status CHECK (
                status IN ('healthy', 'degraded', 'failing', 'disabled')
            ),
            CONSTRAINT ck_source_health_snapshots_consecutive_failures_nonnegative CHECK (consecutive_failures >= 0),
            CONSTRAINT ck_source_health_snapshots_latency_nonnegative CHECK (latency_ms IS NULL OR latency_ms >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_source_health_snapshots_tenant_subscription_observed
            ON dayu_platform.source_health_snapshots (tenant_id, subscription_id, observed_at DESC)
        """
    )


def _seed_default_organization() -> None:
    """以幂等固定值创建 default organization。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        """
        INSERT INTO dayu_platform.organizations (id, slug, display_name, status, version)
        VALUES (
            '00000000-0000-0000-0000-000000000001',
            'default',
            'default',
            'active',
            1
        )
        """
    )


def _grant_matrix() -> None:
    """清理 PUBLIC 权限并按最小权限矩阵授予 app/audit。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute("REVOKE ALL ON SCHEMA dayu_platform FROM PUBLIC")
    for table_name in _PRIVATE_TABLES + _PUBLIC_TABLES:
        op.execute(f"REVOKE ALL ON TABLE dayu_platform.{table_name} FROM PUBLIC")

    op.execute("GRANT USAGE ON SCHEMA dayu_platform TO dayu_platform_app")
    op.execute("GRANT USAGE ON SCHEMA dayu_platform TO dayu_platform_audit")

    for table_name in _PUBLIC_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE dayu_platform.{table_name} TO dayu_platform_app")
    for table_name in _APP_UPDATE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE dayu_platform.{table_name} TO dayu_platform_app")
    for table_name in _APP_JOIN_TABLES:
        op.execute(f"GRANT SELECT, INSERT, DELETE ON TABLE dayu_platform.{table_name} TO dayu_platform_app")
    for table_name in _APP_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON TABLE dayu_platform.{table_name} TO dayu_platform_app")

    for table_name in _PRIVATE_TABLES + _PUBLIC_TABLES:
        op.execute(f"GRANT SELECT ON TABLE dayu_platform.{table_name} TO dayu_platform_audit")

    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA dayu_platform REVOKE ALL ON TABLES FROM PUBLIC"
    )


def _enable_rls() -> None:
    """为私有表启用并强制 RLS，创建唯一 tenant_isolation policy。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _PRIVATE_TABLES:
        op.execute(f"ALTER TABLE dayu_platform.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE dayu_platform.{table_name} FORCE ROW LEVEL SECURITY")
    for table_name in _PRIVATE_TABLES:
        compare_column = "id" if table_name == "organizations" else "tenant_id"
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON dayu_platform.{table_name}
            FOR ALL TO dayu_platform_app
            USING ({_TENANT_EXPRESSION} = {compare_column})
            WITH CHECK ({_TENANT_EXPRESSION} = {compare_column})
            """
        )


def _drop_policies() -> None:
    """删除全部私有表的 tenant_isolation policy。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _PRIVATE_TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON dayu_platform.{table_name}")


def _drop_tables() -> None:
    """按依赖顺序删除 13 张表（含 default organization 行）。

    顺序为子表在前、被引用表在后，保证无 CASCADE 即可完成删除。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    drop_order: tuple[str, ...] = (
        "source_health_snapshots",
        "source_sync_runs",
        "source_subscriptions",
        "api_tokens",
        "role_permissions",
        "user_roles",
        "permissions",
        "roles",
        "users",
        "securities",
        "companies",
        "source_definitions",
        "organizations",
    )
    for table_name in drop_order:
        op.execute(f"DROP TABLE dayu_platform.{table_name}")


def _downgrade_admission() -> None:
    """downgrade 破坏性 DDL 前的显式 admission 检查。

    不依赖 ``DROP ROLE`` 默认的依赖报错语义，而是在任何 destructive
    downgrade DDL（删除 policy/表/schema/group role）之前，显式查询：

    - ``pg_auth_members``：app/audit group role 存在任何外部 member；
    - ``pg_stat_activity``：存在使用 app/audit 或其 member 身份的非
      当前连接 active session；
    - ``pg_shdepend``：app/audit group role 存在 ``dayu_platform``
      schema 之外的外部对象依赖。

    任一检查命中即抛稳定异常，整次 downgrade 在事务中回滚，schema、
    表、group role、default organization 全部原样保留，绝不发布半
    schema，也不接管未知 owner 或依赖。错误消息不包含 DSN/credential。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 存在外部 member / active session / 外部依赖时
            抛出，消息只描述违规类别。
    """

    bind = op.get_bind()
    group_roles = (PLATFORM_APP_ROLE, PLATFORM_AUDIT_ROLE)
    group_placeholders = ", ".join(f"'{name}'" for name in group_roles)

    member_count = bind.execute(
        text(
            "SELECT count(*) FROM pg_auth_members m "
            "JOIN pg_roles gr ON gr.oid = m.roleid "
            f"WHERE gr.rolname IN ({group_placeholders})"
        )
    ).scalar()
    if member_count and int(member_count) > 0:
        raise RuntimeError(
            "downgrade 拒绝：dayu_platform_app / dayu_platform_audit 仍存在外部 member，"
            "请先移除成员关系"
        )

    session_count = bind.execute(
        text(
            "SELECT count(*) FROM pg_stat_activity a "
            "WHERE a.pid <> pg_backend_pid() AND a.usename IN ("
            "SELECT m.member::regrole::text FROM pg_auth_members m "
            "JOIN pg_roles gr ON gr.oid = m.roleid "
            f"WHERE gr.rolname IN ({group_placeholders})"
            f" UNION SELECT '{PLATFORM_APP_ROLE}' UNION SELECT '{PLATFORM_AUDIT_ROLE}'"
            ")"
        )
    ).scalar()
    if session_count and int(session_count) > 0:
        raise RuntimeError(
            "downgrade 拒绝：存在使用 dayu_platform_app / dayu_platform_audit "
            "或其 member 身份的活跃连接，请先断开"
        )

    external_dependency_count = bind.execute(
        text(
            "SELECT count(*) FROM pg_shdepend d "
            "JOIN pg_roles gr ON gr.oid = d.refobjid "
            f"WHERE gr.rolname IN ({group_placeholders}) "
            "AND NOT ("
            "  (d.classid = 'pg_namespace'::regclass "
            f"    AND d.objid = (SELECT oid FROM pg_namespace WHERE nspname = '{PLATFORM_SCHEMA_NAME}')) "
            "  OR (d.classid = 'pg_class'::regclass AND d.objid IN ("
            "        SELECT c.oid FROM pg_class c "
            "        JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"        WHERE n.nspname = '{PLATFORM_SCHEMA_NAME}')) "
            "  OR (d.classid = 'pg_policy'::regclass AND d.objid IN ("
            "        SELECT p.oid FROM pg_policy p "
            "        JOIN pg_class c ON c.oid = p.polrelid "
            "        JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"        WHERE n.nspname = '{PLATFORM_SCHEMA_NAME}'))"
            ")"
        )
    ).scalar()
    if external_dependency_count and int(external_dependency_count) > 0:
        raise RuntimeError(
            "downgrade 拒绝：dayu_platform_app / dayu_platform_audit "
            "存在 dayu_platform schema 之外的外部对象依赖，请先清理"
        )


def upgrade() -> None:
    """创建 platform 基础 schema、roles、RLS 与 default organization。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 同名 role/schema 已存在时抛出。
    """

    _create_group_roles()
    _create_schema()
    _create_tables()
    _seed_default_organization()
    _grant_matrix()
    _enable_rls()


def downgrade() -> None:
    """精确回滚本迁移创建的 schema、表与 group role。

    在任何破坏性 DDL 前先执行 ``_downgrade_admission``：存在外部
    member / active session / 外部 dependency 时整次 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 存在外部 member / active session / 外部依赖，
            或 schema 非空、group role 无法删除时抛出，整次回滚。
    """

    _downgrade_admission()
    _drop_policies()
    _drop_tables()
    op.execute("DROP SCHEMA dayu_platform RESTRICT")
    op.execute(f"DROP ROLE {PLATFORM_APP_ROLE}")
    op.execute(f"DROP ROLE {PLATFORM_AUDIT_ROLE}")
