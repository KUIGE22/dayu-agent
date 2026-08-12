"""投资平台 PostgreSQL 16 真实 integration lane 测试。

本文件在真实官方 ``postgres:16.14-bookworm`` 容器上验证 Slice 1.1
迁移契约（S11-CTRL-06/07）：

- empty database ``upgrade -> downgrade -> upgrade``；
- default organization 固定种子；
- 私有表 non-null tenant、公共 reference 无 tenant；
- RLS：unset/default deny、same-tenant allow、cross-tenant reject、
  audit bounded bypass、``SET LOCAL`` 不泄漏；
- transactional 语义：同名 role 已存在时迁移 fail-closed 且零对象；
- role/GRANT/policy/schema exact：``information_schema`` /
  ``pg_constraint`` / ``pg_indexes`` / ``pg_policies`` /
  ``pg_auth_members``；
- bootstrap admission：非 superuser ``CREATEROLE NOBYPASSRLS`` 在首个
  DDL 前拒绝且零对象；官方容器初始 superuser 正向 upgrade；
- 测试只经 Alembic upgrade 建 schema，禁止 ``create_all()``。

所有测试统一 ``integration`` marker；共享一个 session cluster，但每个
migration lifecycle 使用独立随机 database。group role 是 cluster 级
对象，因此每个 lifecycle 测试结束时必须 downgrade 移除 group role，
否则下个测试的 upgrade 会因同名 role fail-closed。fixture 不自动设置
tenant，每个 application transaction 必须显式 ``SET LOCAL
app.tenant_id``。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from dayu.investment.storage import (
    DEFAULT_ORGANIZATION_ID,
    DEFAULT_ORGANIZATION_SLUG,
    PLATFORM_APP_ROLE,
    PLATFORM_AUDIT_ROLE,
    PLATFORM_SCHEMA_NAME,
    PlatformMigrationAdmissionError,
)
from tests.integration.investment.conftest import (
    PlatformCluster,
    TemporaryLogin,
    _collect_redacted_logs,
    create_temporary_login,
    drop_temporary_login,
    query_all,
    run_alembic_downgrade,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration

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
    "workspace_import_markers",
    "research_bundle_locators",
    "job_definitions",
    "job_runs",
    "job_attempts",
    "job_leases",
    "job_attempt_receipts",
    "job_events",
    "agent_run_correlations",
    "job_schedules",
    "job_schedule_occurrences",
)

_PUBLIC_TABLES: tuple[str, ...] = ("companies", "securities", "source_definitions")

_ALL_TABLES: tuple[str, ...] = _PRIVATE_TABLES + _PUBLIC_TABLES

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

_TENANT_A = DEFAULT_ORGANIZATION_ID
_TENANT_B = "00000000-0000-0000-0000-000000000002"
_TENANT_C = "00000000-0000-0000-0000-000000000003"

DatabaseFactory = Callable[[], str]

# =============================================================================
# 独立 expected catalog（TERRA-002）
#
# 以下期望值硬编码自 accepted plan S11-CTRL-03/04 契约与实测 PG16 catalog
# 输出，不读取 ORM metadata、不读取迁移脚本，避免与实现同源自比。任一
# migration/ORM 漂移都会让真实 PG16 catalog 查询与这些期望不一致。
# =============================================================================

# 表名 -> 有序列契约：(列名, data_type, 是否可空 "YES"/"NO", 默认值或 None)
_EXPECTED_COLUMNS: dict[str, list[tuple[str, str, str, str | None]]] = {
    "organizations": [
        ("id", "uuid", "NO", None),
        ("slug", "text", "NO", None),
        ("display_name", "text", "NO", None),
        ("status", "text", "NO", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "companies": [
        ("id", "uuid", "NO", None),
        ("legal_name", "text", "NO", None),
        ("lei", "text", "YES", None),
        ("country_code", "character varying(2)", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "securities": [
        ("id", "uuid", "NO", None),
        ("company_id", "uuid", "NO", None),
        ("ticker", "text", "NO", None),
        ("exchange_mic", "character varying(4)", "NO", None),
        ("security_type", "text", "NO", None),
        ("currency", "character(3)", "NO", None),
        ("isin", "text", "YES", None),
        ("is_active", "boolean", "NO", "true"),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "source_definitions": [
        ("id", "uuid", "NO", None),
        ("source_key", "text", "NO", None),
        ("source_kind", "text", "NO", None),
        ("display_name", "text", "NO", None),
        ("enabled_by_default", "boolean", "NO", "true"),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "users": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("subject", "text", "NO", None),
        ("email", "text", "YES", None),
        ("display_name", "text", "NO", None),
        ("status", "text", "NO", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "roles": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("name", "text", "NO", None),
        ("description", "text", "NO", "''::text"),
        ("is_system", "boolean", "NO", "false"),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "permissions": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("permission_key", "text", "NO", None),
        ("description", "text", "NO", "''::text"),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "user_roles": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("user_id", "uuid", "NO", None),
        ("role_id", "uuid", "NO", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
    "role_permissions": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("role_id", "uuid", "NO", None),
        ("permission_id", "uuid", "NO", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
    "api_tokens": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("user_id", "uuid", "NO", None),
        ("name", "text", "NO", None),
        ("token_hash", "character(64)", "NO", None),
        ("status", "text", "NO", None),
        ("expires_at", "timestamp with time zone", "YES", None),
        ("last_used_at", "timestamp with time zone", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "source_subscriptions": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("source_definition_id", "uuid", "NO", None),
        ("company_id", "uuid", "YES", None),
        ("security_id", "uuid", "YES", None),
        ("status", "text", "NO", None),
        ("config_json", "jsonb", "NO", "'{}'::jsonb"),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "source_sync_runs": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("subscription_id", "uuid", "NO", None),
        ("idempotency_key", "text", "NO", None),
        ("status", "text", "NO", None),
        ("started_at", "timestamp with time zone", "NO", None),
        ("finished_at", "timestamp with time zone", "YES", None),
        ("records_discovered", "integer", "NO", "0"),
        ("records_ingested", "integer", "NO", "0"),
        ("safe_error_code", "text", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
    "source_health_snapshots": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("subscription_id", "uuid", "NO", None),
        ("sync_run_id", "uuid", "YES", None),
        ("observed_at", "timestamp with time zone", "NO", None),
        ("status", "text", "NO", None),
        ("consecutive_failures", "integer", "NO", "0"),
        ("latency_ms", "integer", "YES", None),
        ("safe_error_code", "text", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
    "workspace_import_markers": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("migration_id", "text", "NO", None),
        ("source_schema_version", "integer", "NO", None),
        ("source_root_fingerprint", "character(64)", "NO", None),
        ("staged_payload_sha256", "character(64)", "NO", None),
        ("company_count", "integer", "NO", None),
        ("security_count", "integer", "NO", None),
        ("source_definition_count", "integer", "NO", None),
        ("bundle_count", "integer", "NO", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
    "research_bundle_locators": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("import_marker_id", "uuid", "NO", None),
        ("security_id", "uuid", "NO", None),
        ("template_name", "text", "NO", None),
        ("repository_key", "text", "NO", None),
        ("relative_locator", "text", "NO", None),
        ("bundle_sha256", "character(64)", "NO", None),
        ("artifact_manifest_sha256", "character(64)", "NO", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
    "job_definitions": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("job_type", "text", "NO", None),
        ("payload_schema_name", "text", "NO", None),
        ("payload_schema_version", "integer", "NO", None),
        ("max_attempts", "integer", "NO", None),
        ("retry_base_seconds", "integer", "NO", None),
        ("retry_max_seconds", "integer", "NO", None),
        ("lease_duration_seconds", "integer", "NO", None),
        ("status", "text", "NO", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "job_runs": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("definition_id", "uuid", "NO", None),
        ("idempotency_key", "text", "NO", None),
        ("request_fingerprint", "character(64)", "NO", None),
        ("payload_bytes", "bytea", "NO", None),
        ("payload_sha256", "character(64)", "NO", None),
        ("state", "text", "NO", None),
        ("available_at", "timestamp with time zone", "NO", None),
        ("deadline_at", "timestamp with time zone", "NO", None),
        ("current_attempt_number", "integer", "NO", "0"),
        ("next_event_sequence", "bigint", "NO", "1"),
        ("cancel_requested_at", "timestamp with time zone", "YES", None),
        ("cancel_reason", "text", "YES", None),
        ("completed_at", "timestamp with time zone", "YES", None),
        ("safe_failure_code", "text", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "job_attempts": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("job_run_id", "uuid", "NO", None),
        ("attempt_number", "integer", "NO", None),
        ("worker_id", "text", "NO", None),
        ("state", "text", "NO", None),
        ("fence", "bigint", "NO", None),
        ("lease_token_sha256", "character(64)", "NO", None),
        ("claimed_at", "timestamp with time zone", "NO", None),
        ("lease_expires_at", "timestamp with time zone", "NO", None),
        ("last_heartbeat_at", "timestamp with time zone", "YES", None),
        ("finished_at", "timestamp with time zone", "YES", None),
        ("safe_failure_code", "text", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "job_leases": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("job_run_id", "uuid", "NO", None),
        ("attempt_id", "uuid", "NO", None),
        ("fence", "bigint", "NO", None),
        ("token_sha256", "character(64)", "NO", None),
        ("acquired_at", "timestamp with time zone", "NO", None),
        ("expires_at", "timestamp with time zone", "NO", None),
        ("released_at", "timestamp with time zone", "YES", None),
        ("release_reason", "text", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "job_attempt_receipts": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("job_run_id", "uuid", "NO", None),
        ("attempt_id", "uuid", "NO", None),
        ("outcome", "text", "NO", None),
        ("result_schema_name", "text", "YES", None),
        ("result_schema_version", "integer", "YES", None),
        ("result_bytes", "bytea", "YES", None),
        ("result_sha256", "character(64)", "YES", None),
        ("receipt_schema_name", "text", "NO", None),
        ("receipt_schema_version", "integer", "NO", None),
        ("receipt_bytes", "bytea", "NO", None),
        ("receipt_sha256", "character(64)", "NO", None),
        ("safe_error_code", "text", "YES", None),
        ("finalized_at", "timestamp with time zone", "NO", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
    "job_events": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("job_run_id", "uuid", "NO", None),
        ("attempt_id", "uuid", "YES", None),
        ("sequence_number", "bigint", "NO", None),
        ("event_type", "text", "NO", None),
        ("safe_detail_bytes", "bytea", "YES", None),
        ("safe_detail_sha256", "character(64)", "YES", None),
        ("occurred_at", "timestamp with time zone", "NO", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
    "agent_run_correlations": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("job_run_id", "uuid", "NO", None),
        ("attempt_id", "uuid", "NO", None),
        ("idempotency_key", "text", "NO", None),
        ("reserved_host_run_id", "text", "NO", None),
        ("state", "text", "NO", None),
        ("observed_at", "timestamp with time zone", "YES", None),
        ("last_observation_sha256", "character(64)", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("version", "integer", "NO", "1"),
    ],
    "job_schedules": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("schedule_key", "text", "NO", None),
        ("descriptor_job_type", "text", "NO", None),
        ("descriptor_payload_schema_name", "text", "NO", None),
        ("descriptor_payload_schema_version", "integer", "NO", None),
        ("descriptor_max_attempts", "integer", "NO", None),
        ("descriptor_retry_base_seconds", "integer", "NO", None),
        ("descriptor_retry_max_seconds", "integer", "NO", None),
        ("descriptor_lease_duration_seconds", "integer", "NO", None),
        ("payload_schema_name", "text", "NO", None),
        ("payload_schema_version", "integer", "NO", None),
        ("payload_bytes", "bytea", "NO", None),
        ("payload_sha256", "character(64)", "NO", None),
        ("cron_expression", "text", "NO", None),
        ("timezone_name", "text", "NO", None),
        ("misfire_policy", "text", "NO", None),
        ("misfire_grace_seconds", "integer", "NO", None),
        ("job_deadline_seconds", "integer", "NO", None),
        ("state", "text", "NO", None),
        ("next_fire_at", "timestamp with time zone", "YES", None),
        ("version", "integer", "NO", "1"),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
    "job_schedule_occurrences": [
        ("id", "uuid", "NO", None),
        ("tenant_id", "uuid", "NO", None),
        ("schedule_id", "uuid", "NO", None),
        ("schedule_version", "integer", "NO", None),
        ("scheduled_for", "timestamp with time zone", "NO", None),
        ("state", "text", "NO", None),
        ("snapshot_descriptor_job_type", "text", "YES", None),
        ("snapshot_descriptor_payload_schema_name", "text", "YES", None),
        ("snapshot_descriptor_payload_schema_version", "integer", "YES", None),
        ("snapshot_descriptor_max_attempts", "integer", "YES", None),
        ("snapshot_descriptor_retry_base_seconds", "integer", "YES", None),
        ("snapshot_descriptor_retry_max_seconds", "integer", "YES", None),
        ("snapshot_descriptor_lease_duration_seconds", "integer", "YES", None),
        ("snapshot_payload_schema_name", "text", "YES", None),
        ("snapshot_payload_schema_version", "integer", "YES", None),
        ("snapshot_payload_bytes", "bytea", "YES", None),
        ("snapshot_payload_sha256", "character(64)", "YES", None),
        ("snapshot_idempotency_key", "text", "YES", None),
        ("snapshot_available_at", "timestamp with time zone", "YES", None),
        ("snapshot_deadline_at", "timestamp with time zone", "YES", None),
        ("snapshot_request_fingerprint", "character(64)", "YES", None),
        ("job_run_id", "uuid", "YES", None),
        ("coalesced_count", "integer", "YES", None),
        ("skip_reason", "text", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
        ("updated_at", "timestamp with time zone", "NO", "transaction_timestamp()"),
    ],
}

# 表名 -> 有序 named constraint 契约：(conname, contype, pg_get_constraintdef)
_EXPECTED_CONSTRAINTS: dict[str, list[tuple[str, str, str]]] = {
    "organizations": [
        ("pk_organizations", "p", "PRIMARY KEY (id)"),
        ("uq_organizations_slug", "u", "UNIQUE (slug)"),
        ("ck_organizations_status", "c", "CHECK ((status = ANY (ARRAY['active'::text, 'disabled'::text])))"),
        ("ck_organizations_slug_nonblank", "c", "CHECK (((slug <> ''::text) AND (slug = btrim(slug))))"),
        ("ck_organizations_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "companies": [
        ("pk_companies", "p", "PRIMARY KEY (id)"),
        ("uq_companies_lei", "u", "UNIQUE (lei)"),
        ("ck_companies_country_code_upper_2", "c", "CHECK (((country_code IS NULL) OR ((upper((country_code)::text) = (country_code)::text) AND (length((country_code)::text) = 2))))"),
        ("ck_companies_lei_nonblank", "c", "CHECK (((lei IS NULL) OR ((lei <> ''::text) AND (lei = btrim(lei)))))"),
        ("ck_companies_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "securities": [
        ("pk_securities", "p", "PRIMARY KEY (id)"),
        ("uq_securities_exchange_mic_ticker", "u", "UNIQUE (exchange_mic, ticker)"),
        ("uq_securities_isin", "u", "UNIQUE (isin)"),
        ("fk_securities_company_id_companies", "f", "FOREIGN KEY (company_id) REFERENCES dayu_platform.companies(id) ON DELETE RESTRICT"),
        ("ck_securities_exchange_mic_upper_4", "c", "CHECK ((((exchange_mic)::text = upper((exchange_mic)::text)) AND (length((exchange_mic)::text) = 4)))"),
        ("ck_securities_security_type", "c", "CHECK ((security_type = ANY (ARRAY['equity'::text, 'adr'::text, 'etf'::text, 'fund'::text, 'bond'::text, 'other'::text])))"),
        ("ck_securities_currency_upper", "c", "CHECK (((currency)::text = upper((currency)::text)))"),
        ("ck_securities_ticker_nonblank", "c", "CHECK (((ticker <> ''::text) AND (ticker = btrim(ticker))))"),
        ("ck_securities_isin_nonblank", "c", "CHECK (((isin IS NULL) OR ((isin <> ''::text) AND (isin = btrim(isin)))))"),
        ("ck_securities_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "source_definitions": [
        ("pk_source_definitions", "p", "PRIMARY KEY (id)"),
        ("uq_source_definitions_source_key", "u", "UNIQUE (source_key)"),
        ("ck_source_definitions_source_kind", "c", "CHECK ((source_kind = ANY (ARRAY['filing'::text, 'announcement'::text, 'industry_metric'::text, 'research_material'::text, 'market_price'::text, 'fx'::text])))"),
        ("ck_source_definitions_source_key_nonblank", "c", "CHECK (((source_key <> ''::text) AND (source_key = btrim(source_key))))"),
        ("ck_source_definitions_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "users": [
        ("pk_users", "p", "PRIMARY KEY (id)"),
        ("uq_users_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_users_tenant_id_subject", "u", "UNIQUE (tenant_id, subject)"),
        ("fk_users_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("ck_users_status", "c", "CHECK ((status = ANY (ARRAY['active'::text, 'disabled'::text, 'locked'::text])))"),
        ("ck_users_subject_nonblank", "c", "CHECK (((subject <> ''::text) AND (subject = btrim(subject))))"),
        ("ck_users_email_nonblank", "c", "CHECK (((email IS NULL) OR (email = btrim(email))))"),
        ("ck_users_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "roles": [
        ("pk_roles", "p", "PRIMARY KEY (id)"),
        ("uq_roles_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_roles_tenant_id_name", "u", "UNIQUE (tenant_id, name)"),
        ("fk_roles_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("ck_roles_name_nonblank", "c", "CHECK (((name <> ''::text) AND (name = btrim(name))))"),
        ("ck_roles_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "permissions": [
        ("pk_permissions", "p", "PRIMARY KEY (id)"),
        ("uq_permissions_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_permissions_tenant_id_permission_key", "u", "UNIQUE (tenant_id, permission_key)"),
        ("fk_permissions_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("ck_permissions_permission_key_nonblank", "c", "CHECK (((permission_key <> ''::text) AND (permission_key = btrim(permission_key))))"),
        ("ck_permissions_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "user_roles": [
        ("pk_user_roles", "p", "PRIMARY KEY (id)"),
        ("uq_user_roles_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_user_roles_tenant_id_user_id_role_id", "u", "UNIQUE (tenant_id, user_id, role_id)"),
        ("fk_user_roles_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_user_roles_tenant_user_users", "f", "FOREIGN KEY (tenant_id, user_id) REFERENCES dayu_platform.users(tenant_id, id) ON DELETE RESTRICT"),
        ("fk_user_roles_tenant_role_roles", "f", "FOREIGN KEY (tenant_id, role_id) REFERENCES dayu_platform.roles(tenant_id, id) ON DELETE RESTRICT"),
    ],
    "role_permissions": [
        ("pk_role_permissions", "p", "PRIMARY KEY (id)"),
        ("uq_role_permissions_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_role_permissions_tenant_id_role_id_permission_id", "u", "UNIQUE (tenant_id, role_id, permission_id)"),
        ("fk_role_permissions_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_role_permissions_tenant_role_roles", "f", "FOREIGN KEY (tenant_id, role_id) REFERENCES dayu_platform.roles(tenant_id, id) ON DELETE RESTRICT"),
        ("fk_role_permissions_tenant_permission_permissions", "f", "FOREIGN KEY (tenant_id, permission_id) REFERENCES dayu_platform.permissions(tenant_id, id) ON DELETE RESTRICT"),
    ],
    "api_tokens": [
        ("pk_api_tokens", "p", "PRIMARY KEY (id)"),
        ("uq_api_tokens_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_api_tokens_token_hash", "u", "UNIQUE (token_hash)"),
        ("fk_api_tokens_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_api_tokens_tenant_user_users", "f", "FOREIGN KEY (tenant_id, user_id) REFERENCES dayu_platform.users(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_api_tokens_status", "c", "CHECK ((status = ANY (ARRAY['active'::text, 'revoked'::text, 'expired'::text])))"),
        ("ck_api_tokens_token_hash_lowercase_hex", "c", "CHECK ((token_hash ~ '^[0-9a-f]{64}$'::text))"),
        ("ck_api_tokens_name_nonblank", "c", "CHECK (((name <> ''::text) AND (name = btrim(name))))"),
        ("ck_api_tokens_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "source_subscriptions": [
        ("pk_source_subscriptions", "p", "PRIMARY KEY (id)"),
        ("uq_source_subscriptions_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("fk_source_subscriptions_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_source_subscriptions_source_definition_id_source_definitions", "f", "FOREIGN KEY (source_definition_id) REFERENCES dayu_platform.source_definitions(id) ON DELETE RESTRICT"),
        ("fk_source_subscriptions_company_id_companies", "f", "FOREIGN KEY (company_id) REFERENCES dayu_platform.companies(id) ON DELETE RESTRICT"),
        ("fk_source_subscriptions_security_id_securities", "f", "FOREIGN KEY (security_id) REFERENCES dayu_platform.securities(id) ON DELETE RESTRICT"),
        ("ck_source_subscriptions_status", "c", "CHECK ((status = ANY (ARRAY['enabled'::text, 'disabled'::text])))"),
        ("ck_source_subscriptions_target_exclusive", "c", "CHECK ((num_nonnulls(company_id, security_id) <= 1))"),
        ("ck_source_subscriptions_config_json_object", "c", "CHECK ((jsonb_typeof(config_json) = 'object'::text))"),
        ("ck_source_subscriptions_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "source_sync_runs": [
        ("pk_source_sync_runs", "p", "PRIMARY KEY (id)"),
        ("uq_source_sync_runs_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_source_sync_runs_tenant_id_idempotency_key", "u", "UNIQUE (tenant_id, idempotency_key)"),
        ("fk_source_sync_runs_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_source_sync_runs_tenant_subscription_source_subscriptions", "f", "FOREIGN KEY (tenant_id, subscription_id) REFERENCES dayu_platform.source_subscriptions(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_source_sync_runs_status", "c", "CHECK ((status = ANY (ARRAY['planned'::text, 'running'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text])))"),
        ("ck_source_sync_runs_records_discovered_nonnegative", "c", "CHECK ((records_discovered >= 0))"),
        ("ck_source_sync_runs_records_ingested_nonnegative", "c", "CHECK ((records_ingested >= 0))"),
        ("ck_source_sync_runs_finished_at_after_started_at", "c", "CHECK (((finished_at IS NULL) OR (finished_at >= started_at)))"),
        ("ck_source_sync_runs_idempotency_key_nonblank", "c", "CHECK (((idempotency_key <> ''::text) AND (idempotency_key = btrim(idempotency_key))))"),
    ],
    "source_health_snapshots": [
        ("pk_source_health_snapshots", "p", "PRIMARY KEY (id)"),
        ("uq_source_health_snapshots_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("fk_source_health_snapshots_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_source_health_snapshots_tenant_subscription", "f", "FOREIGN KEY (tenant_id, subscription_id) REFERENCES dayu_platform.source_subscriptions(tenant_id, id) ON DELETE RESTRICT"),
        ("fk_source_health_snapshots_tenant_sync_run", "f", "FOREIGN KEY (tenant_id, sync_run_id) REFERENCES dayu_platform.source_sync_runs(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_source_health_snapshots_status", "c", "CHECK ((status = ANY (ARRAY['healthy'::text, 'degraded'::text, 'failing'::text, 'disabled'::text])))"),
        ("ck_source_health_snapshots_consecutive_failures_nonnegative", "c", "CHECK ((consecutive_failures >= 0))"),
        ("ck_source_health_snapshots_latency_nonnegative", "c", "CHECK (((latency_ms IS NULL) OR (latency_ms >= 0)))"),
    ],
    "workspace_import_markers": [
        ("pk_workspace_import_markers", "p", "PRIMARY KEY (id)"),
        ("uq_workspace_import_markers_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_workspace_import_markers_tenant_id_migration_id", "u", "UNIQUE (tenant_id, migration_id)"),
        ("fk_workspace_import_markers_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("ck_workspace_import_markers_source_schema_version_positive", "c", "CHECK ((source_schema_version > 0))"),
        ("ck_workspace_import_markers_company_count_nonnegative", "c", "CHECK ((company_count >= 0))"),
        ("ck_workspace_import_markers_security_count_nonnegative", "c", "CHECK ((security_count >= 0))"),
        ("ck_workspace_import_markers_source_definition_count_nonnegative", "c", "CHECK ((source_definition_count >= 0))"),
        ("ck_workspace_import_markers_bundle_count_nonnegative", "c", "CHECK ((bundle_count >= 0))"),
    ],
    "research_bundle_locators": [
        ("pk_research_bundle_locators", "p", "PRIMARY KEY (id)"),
        ("uq_research_bundle_locators_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_research_bundle_locators_tenant_security_template", "u", "UNIQUE (tenant_id, security_id, template_name)"),
        ("uq_research_bundle_locators_tenant_repository_locator", "u", "UNIQUE (tenant_id, repository_key, relative_locator)"),
        ("fk_research_bundle_locators_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_research_bundle_locators_security_id_securities", "f", "FOREIGN KEY (security_id) REFERENCES dayu_platform.securities(id) ON DELETE RESTRICT"),
        ("fk_research_bundle_locators_tenant_marker_markers", "f", "FOREIGN KEY (tenant_id, import_marker_id) REFERENCES dayu_platform.workspace_import_markers(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_research_bundle_locators_repository_key_legacy_workspace", "c", "CHECK ((repository_key = 'legacy-workspace'::text))"),
    ],
    "job_definitions": [
        ("pk_job_definitions", "p", "PRIMARY KEY (id)"),
        ("uq_job_definitions_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_job_definitions_tenant_id_job_type", "u", "UNIQUE (tenant_id, job_type)"),
        ("fk_job_definitions_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("ck_job_definitions_job_type_nonempty", "c", "CHECK (((job_type <> ''::text) AND (job_type = TRIM(BOTH FROM job_type))))"),
        ("ck_job_definitions_payload_schema_name_nonempty", "c", "CHECK (((payload_schema_name <> ''::text) AND (payload_schema_name = TRIM(BOTH FROM payload_schema_name))))"),
        ("ck_job_definitions_payload_schema_version_positive", "c", "CHECK ((payload_schema_version > 0))"),
        ("ck_job_definitions_max_attempts_positive", "c", "CHECK ((max_attempts > 0))"),
        ("ck_job_definitions_retry_base_seconds_positive", "c", "CHECK ((retry_base_seconds > 0))"),
        ("ck_job_definitions_retry_max_seconds_positive", "c", "CHECK ((retry_max_seconds > 0))"),
        ("ck_job_definitions_retry_max_ge_base", "c", "CHECK ((retry_max_seconds >= retry_base_seconds))"),
        ("ck_job_definitions_lease_duration_seconds_positive", "c", "CHECK ((lease_duration_seconds > 0))"),
        ("ck_job_definitions_status_closed", "c", "CHECK ((status = ANY (ARRAY['active'::text, 'disabled'::text])))"),
        ("ck_job_definitions_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "job_runs": [
        ("pk_job_runs", "p", "PRIMARY KEY (id)"),
        ("uq_job_runs_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_job_runs_tenant_definition_idempotency_key", "u", "UNIQUE (tenant_id, definition_id, idempotency_key)"),
        ("fk_job_runs_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_job_runs_tenant_definition_definitions", "f", "FOREIGN KEY (tenant_id, definition_id) REFERENCES dayu_platform.job_definitions(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_job_runs_idempotency_key_nonempty", "c", "CHECK (((idempotency_key <> ''::text) AND (idempotency_key = TRIM(BOTH FROM idempotency_key))))"),
        ("ck_job_runs_request_fingerprint_hex64", "c", "CHECK ((request_fingerprint ~ '^[0-9a-f]{64}$'::text))"),
        ("ck_job_runs_payload_sha256_hex64", "c", "CHECK ((payload_sha256 ~ '^[0-9a-f]{64}$'::text))"),
        ("ck_job_runs_state_closed", "c", "CHECK ((state = ANY (ARRAY['ready'::text, 'leased'::text, 'cancel_requested'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text])))"),
        ("ck_job_runs_deadline_after_available", "c", "CHECK ((deadline_at > available_at))"),
        ("ck_job_runs_current_attempt_number_nonnegative", "c", "CHECK ((current_attempt_number >= 0))"),
        ("ck_job_runs_next_event_sequence_positive", "c", "CHECK ((next_event_sequence > 0))"),
        ("ck_job_runs_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "job_attempts": [
        ("pk_job_attempts", "p", "PRIMARY KEY (id)"),
        ("uq_job_attempts_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_job_attempts_tenant_job_run_attempt_number", "u", "UNIQUE (tenant_id, job_run_id, attempt_number)"),
        ("uq_job_attempts_tenant_job_run_fence", "u", "UNIQUE (tenant_id, job_run_id, fence)"),
        ("fk_job_attempts_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_job_attempts_tenant_job_run_job_runs", "f", "FOREIGN KEY (tenant_id, job_run_id) REFERENCES dayu_platform.job_runs(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_job_attempts_worker_id_nonempty", "c", "CHECK (((worker_id <> ''::text) AND (worker_id = TRIM(BOTH FROM worker_id))))"),
        ("ck_job_attempts_attempt_number_positive", "c", "CHECK ((attempt_number > 0))"),
        ("ck_job_attempts_fence_positive", "c", "CHECK ((fence > 0))"),
        ("ck_job_attempts_lease_token_sha256_hex64", "c", "CHECK ((lease_token_sha256 ~ '^[0-9a-f]{64}$'::text))"),
        ("ck_job_attempts_state_closed", "c", "CHECK ((state = ANY (ARRAY['leased'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text, 'abandoned'::text])))"),
        ("ck_job_attempts_lease_expires_after_claimed", "c", "CHECK ((lease_expires_at > claimed_at))"),
        ("ck_job_attempts_heartbeat_after_claimed", "c", "CHECK (((last_heartbeat_at IS NULL) OR (last_heartbeat_at >= claimed_at)))"),
        ("ck_job_attempts_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "job_leases": [
        ("pk_job_leases", "p", "PRIMARY KEY (id)"),
        ("uq_job_leases_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_job_leases_tenant_attempt_fence", "u", "UNIQUE (tenant_id, attempt_id, fence)"),
        ("fk_job_leases_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_job_leases_tenant_job_run_job_runs", "f", "FOREIGN KEY (tenant_id, job_run_id) REFERENCES dayu_platform.job_runs(tenant_id, id) ON DELETE RESTRICT"),
        ("fk_job_leases_tenant_attempt_job_attempts", "f", "FOREIGN KEY (tenant_id, attempt_id) REFERENCES dayu_platform.job_attempts(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_job_leases_fence_positive", "c", "CHECK ((fence > 0))"),
        ("ck_job_leases_token_sha256_hex64", "c", "CHECK ((token_sha256 ~ '^[0-9a-f]{64}$'::text))"),
        ("ck_job_leases_expires_after_acquired", "c", "CHECK ((expires_at > acquired_at))"),
        ("ck_job_leases_release_reason_closed", "c", "CHECK (((release_reason IS NULL) OR (release_reason = ANY (ARRAY['completion'::text, 'failure'::text, 'cancel_intent'::text, 'deadline'::text, 'lease_expired'::text]))))"),
        ("ck_job_leases_release_pair_present", "c", "CHECK (((released_at IS NULL) = (release_reason IS NULL)))"),
        ("ck_job_leases_released_at_after_acquired", "c", "CHECK (((released_at IS NULL) OR (released_at >= acquired_at)))"),
        ("ck_job_leases_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "job_attempt_receipts": [
        ("pk_job_attempt_receipts", "p", "PRIMARY KEY (id)"),
        ("uq_job_attempt_receipts_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_job_attempt_receipts_tenant_attempt", "u", "UNIQUE (tenant_id, attempt_id)"),
        ("fk_job_attempt_receipts_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_job_attempt_receipts_tenant_job_run_job_runs", "f", "FOREIGN KEY (tenant_id, job_run_id) REFERENCES dayu_platform.job_runs(tenant_id, id) ON DELETE RESTRICT"),
        ("fk_job_attempt_receipts_tenant_attempt_job_attempts", "f", "FOREIGN KEY (tenant_id, attempt_id) REFERENCES dayu_platform.job_attempts(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_job_attempt_receipts_outcome_closed", "c", "CHECK ((outcome = ANY (ARRAY['succeeded'::text, 'failed'::text, 'cancelled'::text])))"),
        ("ck_job_attempt_receipts_result_pair_all_or_none", "c", "CHECK ((((result_schema_name IS NULL) AND (result_schema_version IS NULL) AND (result_bytes IS NULL) AND (result_sha256 IS NULL)) OR ((result_schema_name IS NOT NULL) AND (result_schema_version IS NOT NULL) AND (result_bytes IS NOT NULL) AND (result_sha256 IS NOT NULL))))"),
        ("ck_job_attempt_receipts_result_only_on_success", "c", "CHECK ((((result_schema_name IS NULL) AND (result_schema_version IS NULL) AND (result_bytes IS NULL) AND (result_sha256 IS NULL)) OR ((outcome = 'succeeded'::text) AND (result_bytes IS NOT NULL) AND (result_schema_name IS NOT NULL) AND (result_schema_version IS NOT NULL) AND (result_sha256 IS NOT NULL))))"),
        ("ck_job_attempt_receipts_result_sha256_hex64", "c", "CHECK (((result_sha256 IS NULL) OR (result_sha256 ~ '^[0-9a-f]{64}$'::text)))"),
        ("ck_job_attempt_receipts_receipt_schema_constants", "c", "CHECK (((receipt_schema_name = ANY (ARRAY['dayu.job.generic-attempt-receipt'::text, 'dayu.job.agent-run-terminal-receipt'::text])) AND (receipt_schema_version = 1)))"),
        ("ck_job_attempt_receipts_receipt_sha256_hex64", "c", "CHECK ((receipt_sha256 ~ '^[0-9a-f]{64}$'::text))"),
        ("ck_job_attempt_receipts_safe_error_code_nullability", "c", "CHECK ((((outcome = 'succeeded'::text) AND (safe_error_code IS NULL)) OR ((outcome = ANY (ARRAY['failed'::text, 'cancelled'::text])) AND (safe_error_code IS NOT NULL))))"),
    ],
    "job_events": [
        ("pk_job_events", "p", "PRIMARY KEY (id)"),
        ("uq_job_events_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_job_events_tenant_job_run_sequence", "u", "UNIQUE (tenant_id, job_run_id, sequence_number)"),
        ("fk_job_events_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_job_events_tenant_job_run_job_runs", "f", "FOREIGN KEY (tenant_id, job_run_id) REFERENCES dayu_platform.job_runs(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_job_events_sequence_number_positive", "c", "CHECK ((sequence_number > 0))"),
        ("ck_job_events_event_type_nonempty", "c", "CHECK (((event_type <> ''::text) AND (event_type = TRIM(BOTH FROM event_type))))"),
        ("ck_job_events_safe_detail_pair_all_or_none", "c", "CHECK (((safe_detail_bytes IS NULL) = (safe_detail_sha256 IS NULL)))"),
        ("ck_job_events_safe_detail_sha256_hex64", "c", "CHECK (((safe_detail_sha256 IS NULL) OR (safe_detail_sha256 ~ '^[0-9a-f]{64}$'::text)))"),
    ],
    "agent_run_correlations": [
        ("pk_agent_run_correlations", "p", "PRIMARY KEY (id)"),
        ("uq_agent_run_correlations_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_agent_run_correlations_tenant_attempt", "u", "UNIQUE (tenant_id, attempt_id)"),
        ("uq_agent_run_correlations_reserved_host_run_id", "u", "UNIQUE (reserved_host_run_id)"),
        ("fk_agent_run_correlations_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_agent_run_correlations_tenant_job_run_job_runs", "f", "FOREIGN KEY (tenant_id, job_run_id) REFERENCES dayu_platform.job_runs(tenant_id, id) ON DELETE RESTRICT"),
        ("fk_agent_run_correlations_tenant_attempt_job_attempts", "f", "FOREIGN KEY (tenant_id, attempt_id) REFERENCES dayu_platform.job_attempts(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_agent_run_correlations_idempotency_key_nonempty", "c", "CHECK (((idempotency_key <> ''::text) AND (idempotency_key = TRIM(BOTH FROM idempotency_key))))"),
        ("ck_agent_run_correlations_reserved_host_run_id_format", "c", "CHECK ((reserved_host_run_id ~ '^run_[0-9a-f]{32}$'::text))"),
        ("ck_agent_run_correlations_state_closed", "c", "CHECK ((state = ANY (ARRAY['reserved'::text, 'host_created'::text, 'host_running'::text, 'host_succeeded'::text, 'host_failed'::text, 'host_cancelled'::text, 'host_unsettled'::text])))"),
        ("ck_agent_run_correlations_observed_pair_all_or_none", "c", "CHECK (((observed_at IS NULL) = (last_observation_sha256 IS NULL)))"),
        ("ck_agent_run_correlations_last_observation_sha256_hex64", "c", "CHECK (((last_observation_sha256 IS NULL) OR (last_observation_sha256 ~ '^[0-9a-f]{64}$'::text)))"),
        ("ck_agent_run_correlations_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "job_schedules": [
        ("pk_job_schedules", "p", "PRIMARY KEY (id)"),
        ("uq_job_schedules_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_job_schedules_tenant_id_schedule_key", "u", "UNIQUE (tenant_id, schedule_key)"),
        ("fk_job_schedules_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("ck_job_schedules_active_has_next_fire", "c", "CHECK (((state <> 'active'::text) OR (next_fire_at IS NOT NULL)))"),
        ("ck_job_schedules_cron_expression_nonempty", "c", "CHECK (((cron_expression <> ''::text) AND (cron_expression = TRIM(BOTH FROM cron_expression))))"),
        ("ck_job_schedules_deadline_greater_than_grace", "c", "CHECK ((job_deadline_seconds > misfire_grace_seconds))"),
        ("ck_job_schedules_descriptor_job_type_nonempty", "c", "CHECK (((descriptor_job_type <> ''::text) AND (descriptor_job_type = TRIM(BOTH FROM descriptor_job_type))))"),
        ("ck_job_schedules_descriptor_lease_duration_seconds_positive", "c", "CHECK ((descriptor_lease_duration_seconds > 0))"),
        ("ck_job_schedules_descriptor_max_attempts_positive", "c", "CHECK ((descriptor_max_attempts > 0))"),
        ("ck_job_schedules_descriptor_payload_schema_name_nonempty", "c", "CHECK (((descriptor_payload_schema_name <> ''::text) AND (descriptor_payload_schema_name = TRIM(BOTH FROM descriptor_payload_schema_name))))"),
        ("ck_job_schedules_descriptor_payload_schema_version_positive", "c", "CHECK ((descriptor_payload_schema_version > 0))"),
        ("ck_job_schedules_descriptor_retry_base_seconds_positive", "c", "CHECK ((descriptor_retry_base_seconds > 0))"),
        ("ck_job_schedules_descriptor_retry_max_ge_base", "c", "CHECK ((descriptor_retry_max_seconds >= descriptor_retry_base_seconds))"),
        ("ck_job_schedules_descriptor_retry_max_seconds_positive", "c", "CHECK ((descriptor_retry_max_seconds > 0))"),
        ("ck_job_schedules_job_deadline_seconds_positive", "c", "CHECK ((job_deadline_seconds > 0))"),
        ("ck_job_schedules_misfire_grace_seconds_positive", "c", "CHECK ((misfire_grace_seconds > 0))"),
        ("ck_job_schedules_misfire_policy_closed", "c", "CHECK ((misfire_policy = 'coalesce_one'::text))"),
        ("ck_job_schedules_payload_schema_name_nonempty", "c", "CHECK (((payload_schema_name <> ''::text) AND (payload_schema_name = TRIM(BOTH FROM payload_schema_name))))"),
        ("ck_job_schedules_payload_schema_version_positive", "c", "CHECK ((payload_schema_version > 0))"),
        ("ck_job_schedules_payload_sha256_hex64", "c", "CHECK ((payload_sha256 ~ '^[0-9a-f]{64}$'::text))"),
        ("ck_job_schedules_schedule_key_nonempty", "c", "CHECK (((schedule_key <> ''::text) AND (schedule_key = TRIM(BOTH FROM schedule_key))))"),
        ("ck_job_schedules_state_closed", "c", "CHECK ((state = ANY (ARRAY['active'::text, 'disabled'::text])))"),
        ("ck_job_schedules_timezone_name_nonempty", "c", "CHECK (((timezone_name <> ''::text) AND (timezone_name = TRIM(BOTH FROM timezone_name))))"),
        ("ck_job_schedules_version_positive", "c", "CHECK ((version > 0))"),
    ],
    "job_schedule_occurrences": [
        ("pk_job_schedule_occurrences", "p", "PRIMARY KEY (id)"),
        ("uq_job_schedule_occurrences_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("uq_job_schedule_occurrences_tenant_schedule_fire", "u", "UNIQUE (tenant_id, schedule_id, schedule_version, scheduled_for)"),
        ("fk_job_schedule_occurrences_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("fk_job_schedule_occurrences_tenant_job_run_job_runs", "f", "FOREIGN KEY (tenant_id, job_run_id) REFERENCES dayu_platform.job_runs(tenant_id, id) ON DELETE RESTRICT"),
        ("fk_job_schedule_occurrences_tenant_schedule_job_schedules", "f", "FOREIGN KEY (tenant_id, schedule_id) REFERENCES dayu_platform.job_schedules(tenant_id, id) ON DELETE RESTRICT"),
        ("ck_job_schedule_occurrences_coalesced_count_exact", "c", "CHECK ((((state = ANY (ARRAY['pending'::text, 'materializing'::text, 'enqueued'::text])) AND (coalesced_count IS NOT NULL)) OR ((state = 'skipped'::text) AND (skip_reason = ANY (ARRAY['misfire_expired'::text, 'schedule_disabled'::text])) AND (coalesced_count IS NOT NULL)) OR ((state = 'skipped'::text) AND (skip_reason = ANY (ARRAY['lookback_exceeded'::text, 'candidate_scan_limit_exceeded'::text])) AND (coalesced_count IS NULL))))"),
        ("ck_job_schedule_occurrences_coalesced_count_nonnegative", "c", "CHECK (((coalesced_count IS NULL) OR (coalesced_count >= 0)))"),
        ("ck_job_schedule_occurrences_enqueued_bound", "c", "CHECK (((state <> 'enqueued'::text) OR ((job_run_id IS NOT NULL) AND (skip_reason IS NULL) AND ((snapshot_descriptor_job_type IS NOT NULL) AND (snapshot_descriptor_payload_schema_name IS NOT NULL) AND (snapshot_descriptor_payload_schema_version IS NOT NULL) AND (snapshot_descriptor_max_attempts IS NOT NULL) AND (snapshot_descriptor_retry_base_seconds IS NOT NULL) AND (snapshot_descriptor_retry_max_seconds IS NOT NULL) AND (snapshot_descriptor_lease_duration_seconds IS NOT NULL) AND (snapshot_payload_schema_name IS NOT NULL) AND (snapshot_payload_schema_version IS NOT NULL) AND (snapshot_payload_bytes IS NOT NULL) AND (snapshot_payload_sha256 IS NOT NULL) AND (snapshot_idempotency_key IS NOT NULL) AND (snapshot_available_at IS NOT NULL) AND (snapshot_deadline_at IS NOT NULL) AND (snapshot_request_fingerprint IS NOT NULL)))))"),
        ("ck_job_schedule_occurrences_pending_materializing_clean", "c", "CHECK (((state <> ALL (ARRAY['pending'::text, 'materializing'::text])) OR ((job_run_id IS NULL) AND (skip_reason IS NULL) AND ((snapshot_descriptor_job_type IS NOT NULL) AND (snapshot_descriptor_payload_schema_name IS NOT NULL) AND (snapshot_descriptor_payload_schema_version IS NOT NULL) AND (snapshot_descriptor_max_attempts IS NOT NULL) AND (snapshot_descriptor_retry_base_seconds IS NOT NULL) AND (snapshot_descriptor_retry_max_seconds IS NOT NULL) AND (snapshot_descriptor_lease_duration_seconds IS NOT NULL) AND (snapshot_payload_schema_name IS NOT NULL) AND (snapshot_payload_schema_version IS NOT NULL) AND (snapshot_payload_bytes IS NOT NULL) AND (snapshot_payload_sha256 IS NOT NULL) AND (snapshot_idempotency_key IS NOT NULL) AND (snapshot_available_at IS NOT NULL) AND (snapshot_deadline_at IS NOT NULL) AND (snapshot_request_fingerprint IS NOT NULL)))))"),
        ("ck_job_schedule_occurrences_schedule_version_positive", "c", "CHECK ((schedule_version > 0))"),
        ("ck_job_schedule_occurrences_skip_reason_closed", "c", "CHECK (((skip_reason IS NULL) OR (skip_reason = ANY (ARRAY['misfire_expired'::text, 'lookback_exceeded'::text, 'schedule_disabled'::text, 'candidate_scan_limit_exceeded'::text]))))"),
        ("ck_job_schedule_occurrences_skipped_audit_drops_snapshot", "c", "CHECK (((state <> 'skipped'::text) OR (skip_reason = 'schedule_disabled'::text) OR ((snapshot_descriptor_job_type IS NULL) AND (snapshot_descriptor_payload_schema_name IS NULL) AND (snapshot_descriptor_payload_schema_version IS NULL) AND (snapshot_descriptor_max_attempts IS NULL) AND (snapshot_descriptor_retry_base_seconds IS NULL) AND (snapshot_descriptor_retry_max_seconds IS NULL) AND (snapshot_descriptor_lease_duration_seconds IS NULL) AND (snapshot_payload_schema_name IS NULL) AND (snapshot_payload_schema_version IS NULL) AND (snapshot_payload_bytes IS NULL) AND (snapshot_payload_sha256 IS NULL) AND (snapshot_idempotency_key IS NULL) AND (snapshot_available_at IS NULL) AND (snapshot_deadline_at IS NULL) AND (snapshot_request_fingerprint IS NULL))))"),
        ("ck_job_schedule_occurrences_skipped_clean", "c", "CHECK (((state <> 'skipped'::text) OR ((job_run_id IS NULL) AND (skip_reason IS NOT NULL))))"),
        ("ck_job_schedule_occurrences_skipped_disabled_keeps_snapshot", "c", "CHECK (((state <> 'skipped'::text) OR (skip_reason <> 'schedule_disabled'::text) OR ((snapshot_descriptor_job_type IS NOT NULL) AND (snapshot_descriptor_payload_schema_name IS NOT NULL) AND (snapshot_descriptor_payload_schema_version IS NOT NULL) AND (snapshot_descriptor_max_attempts IS NOT NULL) AND (snapshot_descriptor_retry_base_seconds IS NOT NULL) AND (snapshot_descriptor_retry_max_seconds IS NOT NULL) AND (snapshot_descriptor_lease_duration_seconds IS NOT NULL) AND (snapshot_payload_schema_name IS NOT NULL) AND (snapshot_payload_schema_version IS NOT NULL) AND (snapshot_payload_bytes IS NOT NULL) AND (snapshot_payload_sha256 IS NOT NULL) AND (snapshot_idempotency_key IS NOT NULL) AND (snapshot_available_at IS NOT NULL) AND (snapshot_deadline_at IS NOT NULL) AND (snapshot_request_fingerprint IS NOT NULL))))"),
        ("ck_job_schedule_occurrences_snapshot_available_matches_fire", "c", "CHECK (((snapshot_available_at IS NULL) OR (snapshot_available_at = scheduled_for)))"),
        ("ck_job_schedule_occurrences_snapshot_deadline_after_available", "c", "CHECK (((snapshot_available_at IS NULL) OR ((snapshot_deadline_at IS NOT NULL) AND (snapshot_deadline_at > snapshot_available_at))))"),
        ("ck_job_schedule_occurrences_snapshot_fingerprint_hex64", "c", "CHECK (((snapshot_request_fingerprint IS NULL) OR (snapshot_request_fingerprint ~ '^[0-9a-f]{64}$'::text)))"),
        ("ck_job_schedule_occurrences_snapshot_payload_sha256_hex64", "c", "CHECK (((snapshot_payload_sha256 IS NULL) OR (snapshot_payload_sha256 ~ '^[0-9a-f]{64}$'::text)))"),
        ("ck_job_schedule_occurrences_snapshot_present_or_null", "c", "CHECK ((((snapshot_descriptor_job_type IS NOT NULL) AND (snapshot_descriptor_payload_schema_name IS NOT NULL) AND (snapshot_descriptor_payload_schema_version IS NOT NULL) AND (snapshot_descriptor_max_attempts IS NOT NULL) AND (snapshot_descriptor_retry_base_seconds IS NOT NULL) AND (snapshot_descriptor_retry_max_seconds IS NOT NULL) AND (snapshot_descriptor_lease_duration_seconds IS NOT NULL) AND (snapshot_payload_schema_name IS NOT NULL) AND (snapshot_payload_schema_version IS NOT NULL) AND (snapshot_payload_bytes IS NOT NULL) AND (snapshot_payload_sha256 IS NOT NULL) AND (snapshot_idempotency_key IS NOT NULL) AND (snapshot_available_at IS NOT NULL) AND (snapshot_deadline_at IS NOT NULL) AND (snapshot_request_fingerprint IS NOT NULL)) OR ((snapshot_descriptor_job_type IS NULL) AND (snapshot_descriptor_payload_schema_name IS NULL) AND (snapshot_descriptor_payload_schema_version IS NULL) AND (snapshot_descriptor_max_attempts IS NULL) AND (snapshot_descriptor_retry_base_seconds IS NULL) AND (snapshot_descriptor_retry_max_seconds IS NULL) AND (snapshot_descriptor_lease_duration_seconds IS NULL) AND (snapshot_payload_schema_name IS NULL) AND (snapshot_payload_schema_version IS NULL) AND (snapshot_payload_bytes IS NULL) AND (snapshot_payload_sha256 IS NULL) AND (snapshot_idempotency_key IS NULL) AND (snapshot_available_at IS NULL) AND (snapshot_deadline_at IS NULL) AND (snapshot_request_fingerprint IS NULL))))"),
        ("ck_job_schedule_occurrences_state_closed", "c", "CHECK ((state = ANY (ARRAY['pending'::text, 'materializing'::text, 'enqueued'::text, 'skipped'::text])))"),
    ],
}

# 表名 -> 全部 physical index 契约：(indexname, indexdef)
# 覆盖每张表 pg_indexes 的全部行（PK/unique backing、普通、partial），
# 不做名称/constraint 过滤；indexdef 精确含 unique/primary 标记与
# WHERE predicate。
_EXPECTED_INDEXES: dict[str, list[tuple[str, str]]] = {
    "organizations": [
        ("pk_organizations", "CREATE UNIQUE INDEX pk_organizations ON dayu_platform.organizations USING btree (id)"),
        ("uq_organizations_slug", "CREATE UNIQUE INDEX uq_organizations_slug ON dayu_platform.organizations USING btree (slug)"),
    ],
    "companies": [
        ("pk_companies", "CREATE UNIQUE INDEX pk_companies ON dayu_platform.companies USING btree (id)"),
        ("uq_companies_lei", "CREATE UNIQUE INDEX uq_companies_lei ON dayu_platform.companies USING btree (lei)"),
    ],
    "securities": [
        ("ix_securities_company_id", "CREATE INDEX ix_securities_company_id ON dayu_platform.securities USING btree (company_id)"),
        ("pk_securities", "CREATE UNIQUE INDEX pk_securities ON dayu_platform.securities USING btree (id)"),
        ("uq_securities_exchange_mic_ticker", "CREATE UNIQUE INDEX uq_securities_exchange_mic_ticker ON dayu_platform.securities USING btree (exchange_mic, ticker)"),
        ("uq_securities_isin", "CREATE UNIQUE INDEX uq_securities_isin ON dayu_platform.securities USING btree (isin)"),
    ],
    "source_definitions": [
        ("pk_source_definitions", "CREATE UNIQUE INDEX pk_source_definitions ON dayu_platform.source_definitions USING btree (id)"),
        ("uq_source_definitions_source_key", "CREATE UNIQUE INDEX uq_source_definitions_source_key ON dayu_platform.source_definitions USING btree (source_key)"),
    ],
    "users": [
        ("pk_users", "CREATE UNIQUE INDEX pk_users ON dayu_platform.users USING btree (id)"),
        ("uq_users_tenant_email_lower", "CREATE UNIQUE INDEX uq_users_tenant_email_lower ON dayu_platform.users USING btree (tenant_id, lower(email)) WHERE (email IS NOT NULL)"),
        ("uq_users_tenant_id_id", "CREATE UNIQUE INDEX uq_users_tenant_id_id ON dayu_platform.users USING btree (tenant_id, id)"),
        ("uq_users_tenant_id_subject", "CREATE UNIQUE INDEX uq_users_tenant_id_subject ON dayu_platform.users USING btree (tenant_id, subject)"),
    ],
    "roles": [
        ("pk_roles", "CREATE UNIQUE INDEX pk_roles ON dayu_platform.roles USING btree (id)"),
        ("uq_roles_tenant_id_id", "CREATE UNIQUE INDEX uq_roles_tenant_id_id ON dayu_platform.roles USING btree (tenant_id, id)"),
        ("uq_roles_tenant_id_name", "CREATE UNIQUE INDEX uq_roles_tenant_id_name ON dayu_platform.roles USING btree (tenant_id, name)"),
    ],
    "permissions": [
        ("pk_permissions", "CREATE UNIQUE INDEX pk_permissions ON dayu_platform.permissions USING btree (id)"),
        ("uq_permissions_tenant_id_id", "CREATE UNIQUE INDEX uq_permissions_tenant_id_id ON dayu_platform.permissions USING btree (tenant_id, id)"),
        ("uq_permissions_tenant_id_permission_key", "CREATE UNIQUE INDEX uq_permissions_tenant_id_permission_key ON dayu_platform.permissions USING btree (tenant_id, permission_key)"),
    ],
    "user_roles": [
        ("pk_user_roles", "CREATE UNIQUE INDEX pk_user_roles ON dayu_platform.user_roles USING btree (id)"),
        ("uq_user_roles_tenant_id_id", "CREATE UNIQUE INDEX uq_user_roles_tenant_id_id ON dayu_platform.user_roles USING btree (tenant_id, id)"),
        ("uq_user_roles_tenant_id_user_id_role_id", "CREATE UNIQUE INDEX uq_user_roles_tenant_id_user_id_role_id ON dayu_platform.user_roles USING btree (tenant_id, user_id, role_id)"),
    ],
    "role_permissions": [
        ("pk_role_permissions", "CREATE UNIQUE INDEX pk_role_permissions ON dayu_platform.role_permissions USING btree (id)"),
        ("uq_role_permissions_tenant_id_id", "CREATE UNIQUE INDEX uq_role_permissions_tenant_id_id ON dayu_platform.role_permissions USING btree (tenant_id, id)"),
        ("uq_role_permissions_tenant_id_role_id_permission_id", "CREATE UNIQUE INDEX uq_role_permissions_tenant_id_role_id_permission_id ON dayu_platform.role_permissions USING btree (tenant_id, role_id, permission_id)"),
    ],
    "api_tokens": [
        ("pk_api_tokens", "CREATE UNIQUE INDEX pk_api_tokens ON dayu_platform.api_tokens USING btree (id)"),
        ("uq_api_tokens_tenant_id_id", "CREATE UNIQUE INDEX uq_api_tokens_tenant_id_id ON dayu_platform.api_tokens USING btree (tenant_id, id)"),
        ("uq_api_tokens_token_hash", "CREATE UNIQUE INDEX uq_api_tokens_token_hash ON dayu_platform.api_tokens USING btree (token_hash)"),
    ],
    "source_subscriptions": [
        ("pk_source_subscriptions", "CREATE UNIQUE INDEX pk_source_subscriptions ON dayu_platform.source_subscriptions USING btree (id)"),
        ("uq_source_subscriptions_company", "CREATE UNIQUE INDEX uq_source_subscriptions_company ON dayu_platform.source_subscriptions USING btree (tenant_id, company_id) WHERE (company_id IS NOT NULL)"),
        ("uq_source_subscriptions_security", "CREATE UNIQUE INDEX uq_source_subscriptions_security ON dayu_platform.source_subscriptions USING btree (tenant_id, security_id) WHERE (security_id IS NOT NULL)"),
        ("uq_source_subscriptions_tenant_id_id", "CREATE UNIQUE INDEX uq_source_subscriptions_tenant_id_id ON dayu_platform.source_subscriptions USING btree (tenant_id, id)"),
        ("uq_source_subscriptions_tenant_wide", "CREATE UNIQUE INDEX uq_source_subscriptions_tenant_wide ON dayu_platform.source_subscriptions USING btree (tenant_id) WHERE ((company_id IS NULL) AND (security_id IS NULL))"),
    ],
    "source_sync_runs": [
        ("ix_source_sync_runs_tenant_subscription_started", "CREATE INDEX ix_source_sync_runs_tenant_subscription_started ON dayu_platform.source_sync_runs USING btree (tenant_id, subscription_id, started_at DESC)"),
        ("pk_source_sync_runs", "CREATE UNIQUE INDEX pk_source_sync_runs ON dayu_platform.source_sync_runs USING btree (id)"),
        ("uq_source_sync_runs_tenant_id_id", "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_id_id ON dayu_platform.source_sync_runs USING btree (tenant_id, id)"),
        ("uq_source_sync_runs_tenant_id_idempotency_key", "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_id_idempotency_key ON dayu_platform.source_sync_runs USING btree (tenant_id, idempotency_key)"),
    ],
    "source_health_snapshots": [
        ("ix_source_health_snapshots_tenant_subscription_observed", "CREATE INDEX ix_source_health_snapshots_tenant_subscription_observed ON dayu_platform.source_health_snapshots USING btree (tenant_id, subscription_id, observed_at DESC)"),
        ("pk_source_health_snapshots", "CREATE UNIQUE INDEX pk_source_health_snapshots ON dayu_platform.source_health_snapshots USING btree (id)"),
        ("uq_source_health_snapshots_tenant_id_id", "CREATE UNIQUE INDEX uq_source_health_snapshots_tenant_id_id ON dayu_platform.source_health_snapshots USING btree (tenant_id, id)"),
    ],
    "workspace_import_markers": [
        ("pk_workspace_import_markers", "CREATE UNIQUE INDEX pk_workspace_import_markers ON dayu_platform.workspace_import_markers USING btree (id)"),
        ("uq_workspace_import_markers_tenant_id_id", "CREATE UNIQUE INDEX uq_workspace_import_markers_tenant_id_id ON dayu_platform.workspace_import_markers USING btree (tenant_id, id)"),
        ("uq_workspace_import_markers_tenant_id_migration_id", "CREATE UNIQUE INDEX uq_workspace_import_markers_tenant_id_migration_id ON dayu_platform.workspace_import_markers USING btree (tenant_id, migration_id)"),
    ],
    "research_bundle_locators": [
        ("pk_research_bundle_locators", "CREATE UNIQUE INDEX pk_research_bundle_locators ON dayu_platform.research_bundle_locators USING btree (id)"),
        ("uq_research_bundle_locators_tenant_id_id", "CREATE UNIQUE INDEX uq_research_bundle_locators_tenant_id_id ON dayu_platform.research_bundle_locators USING btree (tenant_id, id)"),
        ("uq_research_bundle_locators_tenant_repository_locator", "CREATE UNIQUE INDEX uq_research_bundle_locators_tenant_repository_locator ON dayu_platform.research_bundle_locators USING btree (tenant_id, repository_key, relative_locator)"),
        ("uq_research_bundle_locators_tenant_security_template", "CREATE UNIQUE INDEX uq_research_bundle_locators_tenant_security_template ON dayu_platform.research_bundle_locators USING btree (tenant_id, security_id, template_name)"),
    ],
    "job_definitions": [
        ("pk_job_definitions", "CREATE UNIQUE INDEX pk_job_definitions ON dayu_platform.job_definitions USING btree (id)"),
        ("uq_job_definitions_tenant_id_id", "CREATE UNIQUE INDEX uq_job_definitions_tenant_id_id ON dayu_platform.job_definitions USING btree (tenant_id, id)"),
        ("uq_job_definitions_tenant_id_job_type", "CREATE UNIQUE INDEX uq_job_definitions_tenant_id_job_type ON dayu_platform.job_definitions USING btree (tenant_id, job_type)"),
    ],
    "job_runs": [
        ("ix_job_runs_cancel_recover", "CREATE INDEX ix_job_runs_cancel_recover ON dayu_platform.job_runs USING btree (tenant_id, state, deadline_at)"),
        ("ix_job_runs_claim_ready", "CREATE INDEX ix_job_runs_claim_ready ON dayu_platform.job_runs USING btree (tenant_id, available_at, id) WHERE (state = 'ready'::text)"),
        ("pk_job_runs", "CREATE UNIQUE INDEX pk_job_runs ON dayu_platform.job_runs USING btree (id)"),
        ("uq_job_runs_tenant_definition_idempotency_key", "CREATE UNIQUE INDEX uq_job_runs_tenant_definition_idempotency_key ON dayu_platform.job_runs USING btree (tenant_id, definition_id, idempotency_key)"),
        ("uq_job_runs_tenant_id_id", "CREATE UNIQUE INDEX uq_job_runs_tenant_id_id ON dayu_platform.job_runs USING btree (tenant_id, id)"),
    ],
    "job_attempts": [
        ("ix_job_attempts_recover", "CREATE INDEX ix_job_attempts_recover ON dayu_platform.job_attempts USING btree (tenant_id, state, lease_expires_at)"),
        ("pk_job_attempts", "CREATE UNIQUE INDEX pk_job_attempts ON dayu_platform.job_attempts USING btree (id)"),
        ("uq_job_attempts_tenant_id_id", "CREATE UNIQUE INDEX uq_job_attempts_tenant_id_id ON dayu_platform.job_attempts USING btree (tenant_id, id)"),
        ("uq_job_attempts_tenant_job_run_attempt_number", "CREATE UNIQUE INDEX uq_job_attempts_tenant_job_run_attempt_number ON dayu_platform.job_attempts USING btree (tenant_id, job_run_id, attempt_number)"),
        ("uq_job_attempts_tenant_job_run_fence", "CREATE UNIQUE INDEX uq_job_attempts_tenant_job_run_fence ON dayu_platform.job_attempts USING btree (tenant_id, job_run_id, fence)"),
    ],
    "job_leases": [
        ("ix_job_leases_attempt_history", "CREATE INDEX ix_job_leases_attempt_history ON dayu_platform.job_leases USING btree (tenant_id, attempt_id, expires_at DESC)"),
        ("pk_job_leases", "CREATE UNIQUE INDEX pk_job_leases ON dayu_platform.job_leases USING btree (id)"),
        ("uq_job_leases_tenant_attempt_fence", "CREATE UNIQUE INDEX uq_job_leases_tenant_attempt_fence ON dayu_platform.job_leases USING btree (tenant_id, attempt_id, fence)"),
        ("uq_job_leases_tenant_id_id", "CREATE UNIQUE INDEX uq_job_leases_tenant_id_id ON dayu_platform.job_leases USING btree (tenant_id, id)"),
    ],
    "job_attempt_receipts": [
        ("pk_job_attempt_receipts", "CREATE UNIQUE INDEX pk_job_attempt_receipts ON dayu_platform.job_attempt_receipts USING btree (id)"),
        ("uq_job_attempt_receipts_tenant_attempt", "CREATE UNIQUE INDEX uq_job_attempt_receipts_tenant_attempt ON dayu_platform.job_attempt_receipts USING btree (tenant_id, attempt_id)"),
        ("uq_job_attempt_receipts_tenant_id_id", "CREATE UNIQUE INDEX uq_job_attempt_receipts_tenant_id_id ON dayu_platform.job_attempt_receipts USING btree (tenant_id, id)"),
    ],
    "job_events": [
        ("ix_job_events_append", "CREATE INDEX ix_job_events_append ON dayu_platform.job_events USING btree (tenant_id, job_run_id, sequence_number)"),
        ("pk_job_events", "CREATE UNIQUE INDEX pk_job_events ON dayu_platform.job_events USING btree (id)"),
        ("uq_job_events_tenant_id_id", "CREATE UNIQUE INDEX uq_job_events_tenant_id_id ON dayu_platform.job_events USING btree (tenant_id, id)"),
        ("uq_job_events_tenant_job_run_sequence", "CREATE UNIQUE INDEX uq_job_events_tenant_job_run_sequence ON dayu_platform.job_events USING btree (tenant_id, job_run_id, sequence_number)"),
    ],
    "agent_run_correlations": [
        ("ix_agent_run_correlations_expired", "CREATE INDEX ix_agent_run_correlations_expired ON dayu_platform.agent_run_correlations USING btree (tenant_id, state, updated_at)"),
        ("pk_agent_run_correlations", "CREATE UNIQUE INDEX pk_agent_run_correlations ON dayu_platform.agent_run_correlations USING btree (id)"),
        ("uq_agent_run_correlations_reserved_host_run_id", "CREATE UNIQUE INDEX uq_agent_run_correlations_reserved_host_run_id ON dayu_platform.agent_run_correlations USING btree (reserved_host_run_id)"),
        ("uq_agent_run_correlations_tenant_attempt", "CREATE UNIQUE INDEX uq_agent_run_correlations_tenant_attempt ON dayu_platform.agent_run_correlations USING btree (tenant_id, attempt_id)"),
        ("uq_agent_run_correlations_tenant_id_id", "CREATE UNIQUE INDEX uq_agent_run_correlations_tenant_id_id ON dayu_platform.agent_run_correlations USING btree (tenant_id, id)"),
    ],
    "job_schedules": [
        ("ix_job_schedules_due", "CREATE INDEX ix_job_schedules_due ON dayu_platform.job_schedules USING btree (tenant_id, next_fire_at, id) WHERE (state = 'active'::text)"),
        ("pk_job_schedules", "CREATE UNIQUE INDEX pk_job_schedules ON dayu_platform.job_schedules USING btree (id)"),
        ("uq_job_schedules_tenant_id_id", "CREATE UNIQUE INDEX uq_job_schedules_tenant_id_id ON dayu_platform.job_schedules USING btree (tenant_id, id)"),
        ("uq_job_schedules_tenant_id_schedule_key", "CREATE UNIQUE INDEX uq_job_schedules_tenant_id_schedule_key ON dayu_platform.job_schedules USING btree (tenant_id, schedule_key)"),
    ],
    "job_schedule_occurrences": [
        ("ix_job_schedule_occurrences_replayable", "CREATE INDEX ix_job_schedule_occurrences_replayable ON dayu_platform.job_schedule_occurrences USING btree (tenant_id, state, scheduled_for, id)"),
        ("pk_job_schedule_occurrences", "CREATE UNIQUE INDEX pk_job_schedule_occurrences ON dayu_platform.job_schedule_occurrences USING btree (id)"),
        ("uq_job_schedule_occurrences_tenant_id_id", "CREATE UNIQUE INDEX uq_job_schedule_occurrences_tenant_id_id ON dayu_platform.job_schedule_occurrences USING btree (tenant_id, id)"),
        ("uq_job_schedule_occurrences_tenant_idempotency_key", "CREATE UNIQUE INDEX uq_job_schedule_occurrences_tenant_idempotency_key ON dayu_platform.job_schedule_occurrences USING btree (tenant_id, snapshot_idempotency_key) WHERE (snapshot_idempotency_key IS NOT NULL)"),
        ("uq_job_schedule_occurrences_tenant_schedule_fire", "CREATE UNIQUE INDEX uq_job_schedule_occurrences_tenant_schedule_fire ON dayu_platform.job_schedule_occurrences USING btree (tenant_id, schedule_id, schedule_version, scheduled_for)"),
    ],
}

# 私有表 -> RLS policy 契约：(policyname, cmd, roles, USING, WITH CHECK)
_POLICY_USING = "((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid = tenant_id)"
_POLICY_USING_ORG = "((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid = id)"
_EXPECTED_POLICIES: dict[str, tuple[str, str, str, str, str]] = {
    table_name: (
        "tenant_isolation",
        "ALL",
        "{dayu_platform_app}",
        _POLICY_USING_ORG if table_name == "organizations" else _POLICY_USING,
        _POLICY_USING_ORG if table_name == "organizations" else _POLICY_USING,
    )
    for table_name in _PRIVATE_TABLES
}


def _bootstrap_dsn(cluster: PlatformCluster, database: str) -> str:
    """构造指向指定数据库的 bootstrap DSN。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库名。

    Returns:
        bootstrap superuser DSN。

    Raises:
        无。
    """

    return cluster.dsn_for_database(database, "postgres")


def _migrate_up(cluster: PlatformCluster, database: str) -> None:
    """对该数据库运行 empty upgrade。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库名。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: admission 失败时抛出。
    """

    run_alembic_upgrade(_bootstrap_dsn(cluster, database))


def _migrate_down(cluster: PlatformCluster, database: str) -> None:
    """对该数据库运行完整 downgrade。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库名。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: admission 失败时抛出。
    """

    run_alembic_downgrade(_bootstrap_dsn(cluster, database))


def _connect(dsn: str) -> Connection:
    """创建测试连接。

    Args:
        dsn: PostgreSQL DSN。

    Returns:
        打开的 ``Connection``。

    Raises:
        无。
    """

    engine = create_engine(dsn, echo=False)
    return engine.connect()


def _autocommit(conn: Connection) -> Connection:
    """返回带 AUTOCOMMIT 隔离级别的连接。

    Args:
        conn: 打开的连接。

    Returns:
        带 AUTOCOMMIT 的执行选项连接。

    Raises:
        无。
    """

    return conn.execution_options(isolation_level="AUTOCOMMIT")


def _insert_tenant_b(cluster: PlatformCluster, database: str) -> None:
    """以 bootstrap 插入第二 tenant。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        无。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        _autocommit(conn).execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.organizations "
                "(id, slug, display_name, status) VALUES "
                f"('{_TENANT_B}', 'tenant-b', 'tenant-b', 'active')"
            )
        )
    finally:
        conn.close()


def _make_app_login(cluster: PlatformCluster, database: str) -> TemporaryLogin:
    """创建临时 app LOGIN 角色。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        临时 app 登录句柄。

    Raises:
        无。
    """

    return create_temporary_login(cluster, database, member_of=PLATFORM_APP_ROLE)


def _make_audit_operator_login(cluster: PlatformCluster, database: str) -> TemporaryLogin:
    """创建临时 audit-operator LOGIN 角色。

    operator 自身 ``NOBYPASSRLS``（``create_temporary_login`` 默认），
    仅持有 ``dayu_platform_audit`` group membership；跨租户只读必须经
    显式 ``SET ROLE dayu_platform_audit`` 获得 group 的 BYPASSRLS，
    不能把 bypass 权限直接扩散到 operator LOGIN。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        临时 audit-operator 登录句柄。

    Raises:
        无。
    """

    return create_temporary_login(cluster, database, member_of=PLATFORM_AUDIT_ROLE)


class TestUpgradeDowngradeCycle:
    """empty upgrade -> downgrade -> upgrade 生命周期。"""

    @pytest.mark.integration
    def test_empty_upgrade_downgrade_upgrade(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """empty 库可完整 upgrade/downgrade/upgrade。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        _assert_schema_present(platform_cluster, database)
        _migrate_down(platform_cluster, database)
        _assert_schema_absent(platform_cluster, database)
        _migrate_up(platform_cluster, database)
        _assert_schema_present(platform_cluster, database)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_default_organization_seed(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """default organization 以固定 UUID/幂等值创建。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            rows = query_all(
                conn,
                f"SELECT id, slug, display_name, status, version FROM {PLATFORM_SCHEMA_NAME}.organizations",
            )
        finally:
            conn.close()
        assert rows == [(UUID(_TENANT_A), DEFAULT_ORGANIZATION_SLUG, "default", "active", 1)]
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_upgrade_fails_closed_when_role_pre_exists(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """同名 role 已存在时迁移 fail-closed 且零对象。

        预先创建同名 ``dayu_platform_app`` group role，再执行 upgrade：
        迁移必须整体失败回滚，schema/表/audit role/default organization
        全部不存在，证明迁移不接管未知 owner 且不发布半 schema。
        预创建的 app role 属于本测试夹具，无论断言结果都必须清理，
        避免污染 cluster 级共享资源。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            _autocommit(conn).execute(text(f"CREATE ROLE {PLATFORM_APP_ROLE} NOLOGIN"))
        finally:
            conn.close()
        try:
            with pytest.raises(SQLAlchemyError):
                _migrate_up(platform_cluster, database)
            _assert_no_platform_objects(platform_cluster, database)
            conn = _connect(_bootstrap_dsn(platform_cluster, database))
            try:
                rows = query_all(
                    conn,
                    "SELECT count(*) FROM pg_roles WHERE rolname = '" + PLATFORM_AUDIT_ROLE + "'",
                )
                assert rows == [(0,)]
            finally:
                conn.close()
        finally:
            conn = _connect(_bootstrap_dsn(platform_cluster, database))
            try:
                _autocommit(conn).execute(text(f"DROP ROLE IF EXISTS {PLATFORM_APP_ROLE}"))
            finally:
                conn.close()

    @pytest.mark.integration
    def test_downgrade_fails_closed_on_external_member(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """downgrade 遇外部 member 时整次回滚，24 表/roles/seed 原样。

        upgrade 后创建 app LOGIN 并加入 ``dayu_platform_app`` 成为
        外部 member，然后 downgrade：显式 admission 必须拒绝且整次
        回滚；随后移除 fixture-owned login membership 再正常 downgrade
        成功且全部消失。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            with pytest.raises(RuntimeError):
                _migrate_down(platform_cluster, database)
            _assert_schema_intact(platform_cluster, database)
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)
        _assert_schema_absent(platform_cluster, database)

    @pytest.mark.integration
    def test_downgrade_fails_closed_on_active_session(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """downgrade 遇活跃 session 时整次回滚，24 表/roles/seed 原样。

        upgrade 后创建 app LOGIN（加入 ``dayu_platform_app``）并保持
        一个以该 LOGIN 连接的活动 session，然后 downgrade：显式
        admission 必须检测到非当前活跃连接并拒绝；关闭连接并移除
        fixture-owned login 后再正常 downgrade 成功。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        session_conn = _connect(login.dsn)
        try:
            session_conn.execute(text("SELECT 1"))
            with pytest.raises(RuntimeError):
                _migrate_down(platform_cluster, database)
            _assert_schema_intact(platform_cluster, database)
        finally:
            session_conn.close()
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)
        _assert_schema_absent(platform_cluster, database)

    @pytest.mark.integration
    def test_downgrade_fails_closed_on_external_dependency(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """downgrade 遇外部依赖时整次回滚，24 表/roles/seed 原样。

        upgrade 后在 ``dayu_platform`` schema 之外创建一张表并授予
        ``dayu_platform_app`` 权限，形成外部对象依赖，然后 downgrade：
        显式 admission 必须检测到外部依赖并拒绝；清理外部对象后再正常
        downgrade 成功。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            _autocommit(conn).execute(
                text(
                    "CREATE TABLE external_dep (id uuid); "
                    f"GRANT SELECT ON TABLE external_dep TO {PLATFORM_APP_ROLE}"
                )
            )
        finally:
            conn.close()
        try:
            with pytest.raises(RuntimeError):
                _migrate_down(platform_cluster, database)
            _assert_schema_intact(platform_cluster, database)
        finally:
            conn = _connect(_bootstrap_dsn(platform_cluster, database))
            try:
                _autocommit(conn).execute(text("DROP TABLE IF EXISTS external_dep"))
            finally:
                conn.close()
        _migrate_down(platform_cluster, database)
        _assert_schema_absent(platform_cluster, database)

    @pytest.mark.integration
    def test_fixture_redacted_logs_do_not_leak_secrets(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """redacted logs 收集不泄漏 raw password / DSN password。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        logs = _collect_redacted_logs(platform_cluster)
        assert isinstance(logs, str)
        assert platform_cluster.admin_password not in logs
        encoded_password = platform_cluster.admin_password
        import urllib.parse

        assert urllib.parse.quote(encoded_password, safe="") not in logs
        assert "postgresql+psycopg://" not in logs
        assert len(logs) <= 4000
        lifecycle_database()

    @pytest.mark.integration
    def test_bootstrap_superuser_admission_rejects_non_superuser(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """非 superuser bootstrap 在首个 DDL 前拒绝且零对象。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        login = create_temporary_login(
            platform_cluster,
            database,
            member_of="",
            createrole=True,
        )
        try:
            with pytest.raises(PlatformMigrationAdmissionError):
                run_alembic_upgrade(login.dsn)
        finally:
            drop_temporary_login(platform_cluster, login)
        _assert_schema_absent(platform_cluster, database)


class TestSchemaExact:
    """schema/role/policy exact 断言。"""

    @pytest.mark.integration
    def test_exact_24_tables(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """schema 精确包含 24 张表，无额外表。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            rows = query_all(
                conn,
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}'",
            )
        finally:
            conn.close()
        table_names = {row[0] for row in rows}
        assert table_names == set(_ALL_TABLES)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_private_tables_have_non_null_tenant_id(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """私有表 tenant_id 非空；公共 reference 无 tenant_id。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            for table_name in frozenset(_PRIVATE_TABLES) - {"organizations"}:
                rows = query_all(
                    conn,
                    "SELECT is_nullable FROM information_schema.columns "
                    f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}' AND table_name = '{table_name}' "
                    "AND column_name = 'tenant_id'",
                )
                assert rows == [("NO",)], table_name
            for table_name in _PUBLIC_TABLES:
                rows = query_all(
                    conn,
                    "SELECT column_name FROM information_schema.columns "
                    f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}' AND table_name = '{table_name}' "
                    "AND column_name = 'tenant_id'",
                )
                assert rows == [], table_name
        finally:
            conn.close()
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_exact_group_roles(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """group role 存在且属性精确（audit 带 BYPASSRLS）。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            rows = query_all(
                conn,
                "SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, "
                "rolcanlogin, rolreplication, rolbypassrls "
                "FROM pg_roles WHERE rolname IN "
                f"('{PLATFORM_APP_ROLE}', '{PLATFORM_AUDIT_ROLE}') ORDER BY rolname",
            )
        finally:
            conn.close()
        by_name = {row[0]: row[1:] for row in rows}
        assert set(by_name) == {PLATFORM_APP_ROLE, PLATFORM_AUDIT_ROLE}
        assert by_name[PLATFORM_APP_ROLE] == (False, True, False, False, False, False, False)
        assert by_name[PLATFORM_AUDIT_ROLE] == (False, True, False, False, False, False, True)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_rls_enabled_and_forced_on_private_tables(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """私有表启用并 FORCE RLS；公共表不启用。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            rows = query_all(
                conn,
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE n.nspname = '{PLATFORM_SCHEMA_NAME}' AND c.relkind = 'r' ORDER BY c.relname",
            )
        finally:
            conn.close()
        by_name = {row[0]: (row[1], row[2]) for row in rows}
        for table_name in _PRIVATE_TABLES:
            assert by_name[table_name] == (True, True), table_name
        for table_name in _PUBLIC_TABLES:
            assert by_name[table_name] == (False, False), table_name
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_tenant_isolation_policy_on_each_private_table(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """每张私有表存在唯一 tenant_isolation policy。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            rows = query_all(
                conn,
                "SELECT tablename, policyname FROM pg_policies "
                f"WHERE schemaname = '{PLATFORM_SCHEMA_NAME}' ORDER BY tablename",
            )
        finally:
            conn.close()
        by_table: dict[str, list[str]] = {}
        for table_name, policy_name in rows:
            by_table.setdefault(str(table_name), []).append(str(policy_name))
        for table_name in _PRIVATE_TABLES:
            assert by_table.get(table_name) == ["tenant_isolation"], table_name
        for table_name in _PUBLIC_TABLES:
            assert table_name not in by_table, table_name
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_foreign_keys_use_restrict(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """全部 FK 使用 ON DELETE RESTRICT。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            rows = query_all(
                conn,
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conrelid IN (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE n.nspname = '{PLATFORM_SCHEMA_NAME}') AND contype = 'f'",
            )
        finally:
            conn.close()
        assert rows
        assert all(row[0] == "r" for row in rows)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_schema_exact_columns(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """24 表全量列/类型/nullable/default 独立 catalog 精确断言。

        期望值来自独立 expected catalog（TERRA-002），不读取 ORM/metadata
        或迁移脚本，避免同源自比。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            columns = query_all(
                conn,
                "SELECT c.relname AS table_name, a.attname AS column_name, "
                "pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type, "
                "CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS is_nullable, "
                "COALESCE(pg_catalog.pg_get_expr(ad.adbin, ad.adrelid), '') "
                "FROM pg_catalog.pg_attribute a "
                "JOIN pg_catalog.pg_class c ON c.oid = a.attrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "LEFT JOIN pg_catalog.pg_attrdef ad "
                "ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum "
                f"WHERE n.nspname = '{PLATFORM_SCHEMA_NAME}' AND c.relkind = 'r' "
                "AND a.attnum > 0 AND NOT a.attisdropped "
                "ORDER BY c.relname, a.attnum",
            )
        finally:
            conn.close()
        by_table: dict[str, list[tuple[str, str, str, str]]] = {}
        for table_name, column_name, data_type, is_nullable, column_default in columns:
            by_table.setdefault(str(table_name), []).append(
                (
                    str(column_name),
                    str(data_type),
                    "YES" if str(is_nullable) == "YES" else "NO",
                    str(column_default),
                )
            )
        assert set(by_table) == set(_ALL_TABLES)
        for table_name, expected in _EXPECTED_COLUMNS.items():
            actual = [
                (name, data_type, nullable, column_default if column_default else None)
                for name, data_type, nullable, column_default in by_table[table_name]
            ]
            assert actual == expected, table_name
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_schema_exact_named_constraints(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """24 表 named PK/FK/unique/check 与定义的独立 catalog 精确断言。

        期望值来自独立 expected catalog，逐表比较 ``pg_constraint`` 的
        ``conname`` / ``contype`` / ``pg_get_constraintdef``。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            rows = query_all(
                conn,
                "SELECT c.relname AS table_name, con.conname, con.contype, "
                "pg_get_constraintdef(con.oid) AS def "
                "FROM pg_constraint con "
                "JOIN pg_class c ON c.oid = con.conrelid "
                "JOIN pg_namespace n ON n.oid = con.connamespace "
                f"WHERE n.nspname = '{PLATFORM_SCHEMA_NAME}' ORDER BY c.relname, con.conname",
            )
        finally:
            conn.close()
        by_table: dict[str, list[tuple[str, str, str]]] = {}
        for table_name, conname, contype, definition in rows:
            by_table.setdefault(str(table_name), []).append(
                (str(conname), str(contype), str(definition))
            )
        assert set(by_table) == set(_ALL_TABLES)
        for table_name, expected in _EXPECTED_CONSTRAINTS.items():
            assert by_table[table_name] == sorted(expected, key=lambda item: item[0]), table_name
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_schema_exact_indexes_with_predicates(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """24 表全部 physical indexes 的独立 catalog 双向精确断言。

        ``pg_indexes`` 的 ``indexdef`` 覆盖 PK/unique backing、普通与
        partial index（含 unique 标记与 WHERE predicate）；期望值来自
       独立 expected catalog，且**不做任何名称/constraint 过滤**——表集合
       与实际集合双向 exact，任何多建/漏建/漂移的 physical index 都会
       失败（含 ``pk_`` 伪装 index）。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            rows = query_all(
                conn,
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                f"WHERE schemaname = '{PLATFORM_SCHEMA_NAME}' "
                "ORDER BY tablename, indexname",
            )
        finally:
            conn.close()
        by_table: dict[str, list[tuple[str, str]]] = {}
        for table_name, index_name, index_def in rows:
            by_table.setdefault(str(table_name), []).append(
                (str(index_name), str(index_def))
            )
        assert set(by_table) == set(_EXPECTED_INDEXES)
        for table_name in _EXPECTED_INDEXES:
            assert by_table[table_name] == _EXPECTED_INDEXES[table_name], table_name
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_schema_exact_rejects_extra_pk_prefixed_index(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """额外 ``pk_`` 伪装 index 会被完整 catalog 比较拒绝。

        在已 upgrade 的库上手工创建 ``pk_unchecked`` 普通 index，证明
        完整 ``pg_indexes`` 双向比较不会因名称前缀被过滤而假绿；随后
        移除该 index，再次比较必须恢复 exact 一致。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        engine = create_engine(_bootstrap_dsn(platform_cluster, database), echo=False)
        conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(
                text(f"CREATE INDEX pk_unchecked ON {PLATFORM_SCHEMA_NAME}.companies (legal_name)")
            )
            rows = query_all(
                conn,
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                f"WHERE schemaname = '{PLATFORM_SCHEMA_NAME}' "
                "ORDER BY tablename, indexname",
            )
            by_table: dict[str, list[tuple[str, str]]] = {}
            for table_name, index_name, index_def in rows:
                by_table.setdefault(str(table_name), []).append(
                    (str(index_name), str(index_def))
                )
            assert set(by_table) == set(_EXPECTED_INDEXES)
            assert by_table["companies"] != _EXPECTED_INDEXES["companies"]
        finally:
            conn.execute(
                text(f"DROP INDEX IF EXISTS {PLATFORM_SCHEMA_NAME}.pk_unchecked")
            )
            conn.close()
            engine.dispose()
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_schema_exact_policies(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """RLS policy command/roles/USING/WITH CHECK 独立 catalog 精确断言。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            rows = query_all(
                conn,
                "SELECT tablename, policyname, cmd, roles::text, qual, with_check "
                "FROM pg_policies "
                f"WHERE schemaname = '{PLATFORM_SCHEMA_NAME}' ORDER BY tablename",
            )
        finally:
            conn.close()
        by_table: dict[str, tuple[str, str, str, str, str]] = {}
        for table_name, policy_name, cmd, roles, qual, with_check in rows:
            by_table[str(table_name)] = (
                str(policy_name),
                str(cmd),
                str(roles),
                str(qual),
                str(with_check),
            )
        assert set(by_table) == set(_PRIVATE_TABLES)
        for table_name, expected in _EXPECTED_POLICIES.items():
            assert by_table[table_name] == expected, table_name
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_public_and_default_acl_exact(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """PUBLIC 与 default ACL 独立断言：PUBLIC 无表/schema 权限、无 app/audit default grant。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            public_table_grants = query_all(
                conn,
                "SELECT count(*) FROM information_schema.role_table_grants "
                f"WHERE grantee = 'PUBLIC' AND table_schema = '{PLATFORM_SCHEMA_NAME}'",
            )
            assert public_table_grants == [(0,)]
            public_schema_usage = query_all(
                conn,
                "SELECT has_schema_privilege('public', "
                f"'{PLATFORM_SCHEMA_NAME}', 'USAGE')",
            )
            assert public_schema_usage == [(False,)]
            # pg_default_acl 为空：migration 未向 future objects blanket grant。
            default_acl_rows = query_all(
                conn,
                "SELECT count(*) FROM pg_default_acl",
            )
            assert default_acl_rows == [(0,)]
        finally:
            conn.close()
        _migrate_down(platform_cluster, database)


class TestRlsBehavior:
    """RLS 行为：default deny、同租户允许、跨租户拒绝与 audit 受控绕过。"""

    @pytest.mark.integration
    def test_app_unset_tenant_default_deny(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """app 未设置 tenant 时 SELECT 私有表默认 deny（0 行）。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                rows = query_all(conn, f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.organizations")
                assert rows == []
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_app_same_tenant_allow_after_set_local(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """app 显式 SET LOCAL tenant 后可读该租户行，提交后不泄漏。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                conn.execute(text("BEGIN"))
                conn.execute(text("SET LOCAL app.tenant_id = '" + _TENANT_A + "'"))
                rows = query_all(conn, f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.organizations")
                assert rows == [(UUID(_TENANT_A),)]
                conn.execute(text("COMMIT"))
                after_rows = query_all(conn, f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.organizations")
                assert after_rows == []
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_app_cross_tenant_reject(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """app 以 tenant A 身份看不到 tenant B 的行。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        _insert_tenant_b(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                conn.execute(text("BEGIN"))
                conn.execute(text("SET LOCAL app.tenant_id = '" + _TENANT_A + "'"))
                rows = query_all(conn, f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.organizations")
                assert rows == [(UUID(_TENANT_A),)]
                conn.execute(text("COMMIT"))
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_audit_operator_requires_set_role_for_cross_tenant(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """audit-operator NOBYPASSRLS：未 SET ROLE 不能跨租户，SET ROLE 后可只读。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        _insert_tenant_b(platform_cluster, database)
        login = _make_audit_operator_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                # operator 自身 NOBYPASSRLS：未 SET ROLE 时 RLS 生效，
                # tenant 未设置 => default deny，跨租户行不可见。
                rows = query_all(conn, f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.organizations")
                assert rows == []
                # 显式 SET ROLE 到 audit group 后获得 BYPASSRLS：
                # 跨租户只读可见，但全部 DML 仍被权限拒绝。
                conn.execute(text(f"SET ROLE {PLATFORM_AUDIT_ROLE}"))
                bypass_rows = query_all(
                    conn, f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.organizations ORDER BY id"
                )
                assert bypass_rows == [(UUID(_TENANT_A),), (UUID(_TENANT_B),)]
                with pytest.raises(Exception):
                    conn.execute(
                        text(
                            f"INSERT INTO {PLATFORM_SCHEMA_NAME}.organizations "
                            "(id, slug, display_name, status) VALUES "
                            f"('{_TENANT_C}', 'c', 'c', 'active')"
                        )
                    )
                conn.rollback()
                with pytest.raises(Exception):
                    conn.execute(
                        text(
                            f"UPDATE {PLATFORM_SCHEMA_NAME}.organizations "
                            f"SET display_name = 'x' WHERE id = '{_TENANT_A}'"
                        )
                    )
                conn.rollback()
                with pytest.raises(Exception):
                    conn.execute(text(f"DROP TABLE {PLATFORM_SCHEMA_NAME}.companies"))
                conn.rollback()
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_audit_operator_membership_options_exact(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """audit-operator membership 的 INHERIT/SET/ADMIN options 精确。

        PostgreSQL 16 ``pg_auth_members`` 对每条 membership row 记录三个
        独立字段：``inherit_option``、``set_option``、``admin_option``。
        fixture 显式以 ``GRANT group TO login WITH INHERIT TRUE, SET TRUE,
        ADMIN FALSE`` 建立 membership；本测试精确断言三字段
        （true/true/false），并单独把 ``pg_roles.rolinherit`` 作为 LOGIN
        role 属性断言，绝不把 role 属性当作 membership option。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        audit_login = _make_audit_operator_login(platform_cluster, database)
        app_login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(_bootstrap_dsn(platform_cluster, database))
            try:
                rows = query_all(
                    conn,
                    "SELECT m.member::regrole::text, m.roleid::regrole::text, "
                    "m.inherit_option, m.set_option, m.admin_option "
                    "FROM pg_auth_members m "
                    "JOIN pg_roles gr ON gr.oid = m.roleid "
                    "WHERE gr.rolname IN "
                    f"('{PLATFORM_APP_ROLE}', '{PLATFORM_AUDIT_ROLE}') "
                    "ORDER BY gr.rolname, m.member::regrole::text",
                )
                login_attrs = query_all(
                    conn,
                    "SELECT rolname, rolinherit FROM pg_roles "
                    f"WHERE rolname IN ('{audit_login.role}', '{app_login.role}') "
                    "ORDER BY rolname",
                )
            finally:
                conn.close()
            by_member = {
                (str(row[0]), str(row[1])): (bool(row[2]), bool(row[3]), bool(row[4]))
                for row in rows
            }
            assert (audit_login.role, PLATFORM_AUDIT_ROLE) in by_member
            assert (app_login.role, PLATFORM_APP_ROLE) in by_member
            assert (audit_login.role, PLATFORM_APP_ROLE) not in by_member
            assert (app_login.role, PLATFORM_AUDIT_ROLE) not in by_member
            for options in by_member.values():
                assert options == (True, True, False)
            # rolinherit 是 LOGIN role 属性，单独断言，不替代 membership 字段。
            by_role = {str(row[0]): bool(row[1]) for row in login_attrs}
            assert by_role[audit_login.role] is True
            assert by_role[app_login.role] is True
        finally:
            drop_temporary_login(platform_cluster, audit_login)
            drop_temporary_login(platform_cluster, app_login)
        _migrate_down(platform_cluster, database)


class TestGrantMatrix:
    """app/audit 最小权限矩阵。"""

    @pytest.mark.integration
    def test_app_privileges_exact(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """app 对 schema/tables 的权限矩阵精确。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                schema_usage = query_all(
                    conn,
                    "SELECT has_schema_privilege(current_user, "
                    f"'{PLATFORM_SCHEMA_NAME}', 'USAGE')",
                )
                schema_create = query_all(
                    conn,
                    "SELECT has_schema_privilege(current_user, "
                    f"'{PLATFORM_SCHEMA_NAME}', 'CREATE')",
                )
                assert schema_usage == [(True,)]
                assert schema_create == [(False,)]
                for table_name in _PUBLIC_TABLES + _APP_UPDATE_TABLES:
                    grants = query_all(
                        conn,
                        "SELECT has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'SELECT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'INSERT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'UPDATE'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'DELETE'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'TRUNCATE')",
                    )
                    assert grants == [(True, True, True, False, False)], table_name
                for table_name in _APP_JOIN_TABLES:
                    grants = query_all(
                        conn,
                        "SELECT has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'SELECT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'INSERT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'UPDATE'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'DELETE')",
                    )
                    assert grants == [(True, True, False, True)], table_name
                for table_name in _APP_APPEND_TABLES:
                    grants = query_all(
                        conn,
                        "SELECT has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'SELECT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'INSERT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'UPDATE'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'DELETE')",
                    )
                    assert grants == [(True, True, False, False)], table_name
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_app_cannot_set_role_audit(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """app 不是 audit member，SET ROLE audit 被拒。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                with pytest.raises(Exception):
                    conn.execute(text(f"SET ROLE {PLATFORM_AUDIT_ROLE}"))
                conn.rollback()
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_audit_select_only_all_tables(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """audit-operator SET ROLE 后对全部 24 表只有 SELECT。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_audit_operator_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                conn.execute(text(f"SET ROLE {PLATFORM_AUDIT_ROLE}"))
                for table_name in _ALL_TABLES:
                    grants = query_all(
                        conn,
                        "SELECT has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'SELECT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'INSERT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'UPDATE'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'DELETE')",
                    )
                    assert grants == [(True, False, False, False)], table_name
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_app_cannot_create_objects_in_schema(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """app 在 schema 内无 CREATE 权限，DDL 被拒。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                with pytest.raises(Exception):
                    conn.execute(text(f"CREATE TABLE {PLATFORM_SCHEMA_NAME}.hacked (id uuid)"))
                conn.rollback()
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)


def _migrate_down_to_0001(cluster: PlatformCluster, database: str) -> None:
    """把数据库降级到 ``0001_platform_foundation``。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        无。
    """

    from alembic import command
    from alembic.config import Config

    from tests.integration.investment.conftest import _ALEMBIC_INI, _MIGRATIONS_DIR

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    previous = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = _bootstrap_dsn(cluster, database)
    try:
        command.downgrade(cfg, "0001_platform_foundation")
    finally:
        if previous is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = previous


class TestWorkspaceImportMigrationCycle:
    """0002 workspace import 迁移循环/降级/权限契约。"""

    @pytest.mark.integration
    def test_upgrade_downgrade_0001_upgrade_cycle(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """0001 -> 0002 -> 0001 -> 0002 可重复且 0002 owner 精确消失。"""

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        _assert_0002_present(platform_cluster, database)
        _migrate_down_to_0001(platform_cluster, database)
        _assert_0002_absent(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            remaining = query_all(
                conn,
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}'",
            )
        finally:
            conn.close()
        assert {row[0] for row in remaining} == set(_ALL_TABLES) - {
            "workspace_import_markers",
            "research_bundle_locators",
            "job_definitions",
            "job_runs",
            "job_attempts",
            "job_leases",
            "job_attempt_receipts",
            "job_events",
            "agent_run_correlations",
            "job_schedules",
            "job_schedule_occurrences",
        }
        _migrate_up(platform_cluster, database)
        _assert_0002_present(platform_cluster, database)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_downgrade_0002_with_internal_rows_succeeds(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """0002 表有内部 rows 仍可降级（rows 随 owner table 删除）。"""

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        _seed_0002_rows(platform_cluster, database)
        _migrate_down_to_0001(platform_cluster, database)
        _assert_0002_absent(platform_cluster, database)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_downgrade_0002_rejects_external_dependent_view(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """0002 表存在外部 dependent view 时整次降级失败并回滚。"""

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            _autocommit(conn).execute(
                text(
                    "CREATE VIEW external_marker_view AS "
                    f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.workspace_import_markers"
                )
            )
        finally:
            conn.close()
        try:
            with pytest.raises(RuntimeError):
                _migrate_down_to_0001(platform_cluster, database)
            _assert_0002_present(platform_cluster, database)
        finally:
            conn = _connect(_bootstrap_dsn(platform_cluster, database))
            try:
                _autocommit(conn).execute(text("DROP VIEW IF EXISTS external_marker_view"))
            finally:
                conn.close()
        _migrate_down_to_0001(platform_cluster, database)
        _assert_0002_absent(platform_cluster, database)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_app_update_delete_0002_tables_denied(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """app 对 marker/locator 只有 SELECT/INSERT，禁止 UPDATE/DELETE。"""

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        _seed_0002_rows(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                for table_name in ("workspace_import_markers", "research_bundle_locators"):
                    grants = query_all(
                        conn,
                        "SELECT has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'SELECT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'INSERT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'UPDATE'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'DELETE')",
                    )
                    assert grants == [(True, True, False, False)], table_name
                with pytest.raises(Exception):
                    conn.execute(
                        text(
                            f"UPDATE {PLATFORM_SCHEMA_NAME}.workspace_import_markers "
                            "SET company_count = 9"
                        )
                    )
                conn.rollback()
                with pytest.raises(Exception):
                    conn.execute(
                        text(
                            f"DELETE FROM {PLATFORM_SCHEMA_NAME}.research_bundle_locators"
                        )
                    )
                conn.rollback()
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)


def _assert_0002_present(cluster: PlatformCluster, database: str) -> None:
    """断言 0002 两张表存在。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 表缺失时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        rows = query_all(
            conn,
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}'",
        )
    finally:
        conn.close()
    table_names = {row[0] for row in rows}
    assert {"workspace_import_markers", "research_bundle_locators"}.issubset(table_names)


def _assert_0002_absent(cluster: PlatformCluster, database: str) -> None:
    """断言 0002 两张表已消失。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 表仍存在时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        rows = query_all(
            conn,
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}'",
        )
    finally:
        conn.close()
    table_names = {row[0] for row in rows}
    assert "workspace_import_markers" not in table_names
    assert "research_bundle_locators" not in table_names


def _seed_0002_rows(cluster: PlatformCluster, database: str) -> None:
    """以 bootstrap 插入 marker/locator 内部行。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        无。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        conn = _autocommit(conn)
        conn.execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.companies "
                "(id, legal_name, lei, country_code) VALUES "
                "('11111111-1111-4111-8111-111111111111', 'Seed Co', NULL, 'US')"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.securities "
                "(id, company_id, ticker, exchange_mic, security_type, currency, isin, is_active) "
                "VALUES ('22222222-2222-4222-8222-222222222222', "
                "'11111111-1111-4111-8111-111111111111', 'SEED', 'XNAS', 'equity', 'USD', NULL, true)"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.workspace_import_markers "
                "(id, tenant_id, migration_id, source_schema_version, source_root_fingerprint, "
                "staged_payload_sha256, company_count, security_count, "
                "source_definition_count, bundle_count) VALUES "
                "('33333333-3333-4333-8333-333333333333', "
                f"'{_TENANT_A}', 'legacy-workspace-import-v1', 1, "
                "'" + "a" * 64 + "', '" + "b" * 64 + "', 0, 0, 0, 0)"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.research_bundle_locators "
                "(id, tenant_id, import_marker_id, security_id, template_name, repository_key, "
                "relative_locator, bundle_sha256, artifact_manifest_sha256) VALUES "
                "('44444444-4444-4444-8444-444444444444', "
                f"'{_TENANT_A}', '33333333-3333-4333-8333-333333333333', "
                "'22222222-2222-4222-8222-222222222222', 'technology', 'legacy-workspace', "
                "'assets/research_templates/technology.bundle.json', "
                "'" + "c" * 64 + "', '" + "d" * 64 + "')"
            )
        )
    finally:
        conn.close()


def _assert_schema_present(cluster: PlatformCluster, database: str) -> None:
    """断言 schema/表/group role 已存在。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 存在性断言失败时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        schema = query_all(conn, "SELECT 1 FROM pg_namespace WHERE nspname = '" + PLATFORM_SCHEMA_NAME + "'")
        assert schema == [(1,)]
        table_count = query_all(
            conn,
            "SELECT count(*) FROM information_schema.tables "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}'",
        )
        assert table_count[0][0] == 24
        roles = query_all(
            conn,
            "SELECT count(*) FROM pg_roles WHERE rolname IN "
            f"('{PLATFORM_APP_ROLE}', '{PLATFORM_AUDIT_ROLE}')",
        )
        assert roles == [(2,)]
    finally:
        conn.close()


def _assert_schema_intact(cluster: PlatformCluster, database: str) -> None:
    """断言 downgrade 失败后 schema/24 表/roles/default seed 全部原样。

    用于验证 fail-closed 场景：迁移拒绝后不得发布任何部分状态，
    对象集合与升级完成态完全一致。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 任一对象缺失或 seed 漂移时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        schema = query_all(conn, "SELECT 1 FROM pg_namespace WHERE nspname = '" + PLATFORM_SCHEMA_NAME + "'")
        assert schema == [(1,)]
        table_names = {
            row[0]
            for row in query_all(
                conn,
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}'",
            )
        }
        assert table_names == set(_ALL_TABLES)
        roles = query_all(
            conn,
            "SELECT rolname FROM pg_roles WHERE rolname IN "
            f"('{PLATFORM_APP_ROLE}', '{PLATFORM_AUDIT_ROLE}') ORDER BY rolname",
        )
        assert [row[0] for row in roles] == [PLATFORM_APP_ROLE, PLATFORM_AUDIT_ROLE]
        seed = query_all(
            conn,
            f"SELECT id, slug, status, version FROM {PLATFORM_SCHEMA_NAME}.organizations",
        )
        assert seed == [(UUID(_TENANT_A), DEFAULT_ORGANIZATION_SLUG, "active", 1)]
    finally:
        conn.close()


def _assert_schema_absent(cluster: PlatformCluster, database: str) -> None:
    """断言 schema/group role/seed 全部消失。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 消失性断言失败时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        schema = query_all(conn, "SELECT 1 FROM pg_namespace WHERE nspname = '" + PLATFORM_SCHEMA_NAME + "'")
        assert schema == []
        roles = query_all(
            conn,
            "SELECT count(*) FROM pg_roles WHERE rolname IN "
            f"('{PLATFORM_APP_ROLE}', '{PLATFORM_AUDIT_ROLE}')",
        )
        assert roles == [(0,)]
    finally:
        conn.close()


def _assert_no_platform_objects(cluster: PlatformCluster, database: str) -> None:
    """断言迁移未发布任何平台对象（schema/表/seed 全部不存在）。

    与 ``_assert_schema_absent`` 不同，本断言不断言 group role：
    fail-closed 场景中夹具可能预创建同名 app role，迁移不得接管或
    删除该未知 owner。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 存在迁移发布的对象时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        schema = query_all(conn, "SELECT 1 FROM pg_namespace WHERE nspname = '" + PLATFORM_SCHEMA_NAME + "'")
        assert schema == []
        tables = query_all(
            conn,
            "SELECT count(*) FROM information_schema.tables "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}'",
        )
        assert tables == [(0,)]
        # schema 已不存在，default organization seed 必然不存在。
        seed_rows = query_all(
            conn,
            "SELECT count(*) FROM information_schema.tables "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}' AND table_name = 'organizations'",
        )
        assert seed_rows == [(0,)]
    finally:
        conn.close()


_JOBS_0003_TABLES: tuple[str, ...] = (
    "job_definitions",
    "job_runs",
    "job_attempts",
    "job_leases",
    "job_attempt_receipts",
    "job_events",
    "agent_run_correlations",
)
"""0003 durable jobs 的七张表。"""


def _migrate_down_to_0002(cluster: PlatformCluster, database: str) -> None:
    """把数据库降级到 ``0002_workspace_import``。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        无。
    """

    from alembic import command
    from alembic.config import Config

    from tests.integration.investment.conftest import _ALEMBIC_INI, _MIGRATIONS_DIR

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    previous = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = _bootstrap_dsn(cluster, database)
    try:
        command.downgrade(cfg, "0002_workspace_import")
    finally:
        if previous is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = previous


def _assert_0003_present(cluster: PlatformCluster, database: str) -> None:
    """断言 0003 七张表存在。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 表缺失时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        rows = query_all(
            conn,
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}'",
        )
    finally:
        conn.close()
    table_names = {row[0] for row in rows}
    assert set(_JOBS_0003_TABLES).issubset(table_names)


def _assert_0003_absent(cluster: PlatformCluster, database: str) -> None:
    """断言 0003 七张表已消失。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 表仍存在时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        rows = query_all(
            conn,
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}'",
        )
    finally:
        conn.close()
    table_names = {row[0] for row in rows}
    assert not set(_JOBS_0003_TABLES).intersection(table_names)


class TestDurableJobs0003MigrationCycle:
    """0003 durable jobs 迁移循环/降级/权限契约。"""

    @pytest.mark.integration
    def test_0003_upgrade_downgrade_upgrade_and_external_dependency_refusal(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """0003 up -> down -> up 可重复；外部 dependent view 使降级 fail closed。"""

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        _assert_0003_present(platform_cluster, database)
        # 外部 dependent view 阻止降级。
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            _autocommit(conn).execute(
                text(
                    "CREATE VIEW external_correlation_view AS "
                    f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.agent_run_correlations"
                )
            )
        finally:
            conn.close()
        try:
            with pytest.raises(RuntimeError):
                _migrate_down_to_0002(platform_cluster, database)
            _assert_0003_present(platform_cluster, database)
        finally:
            conn = _connect(_bootstrap_dsn(platform_cluster, database))
            try:
                _autocommit(conn).execute(
                    text("DROP VIEW IF EXISTS external_correlation_view")
                )
            finally:
                conn.close()
        # 清理后降级 -> 再升级。
        _migrate_down_to_0002(platform_cluster, database)
        _assert_0003_absent(platform_cluster, database)
        _migrate_up(platform_cluster, database)
        _assert_0003_present(platform_cluster, database)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_0003_grant_matrix_exact(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """app/audit 权限矩阵精确：SELECT/INSERT、列级 UPDATE、无 DELETE/TRUNCATE。"""

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                for table_name in _JOBS_0003_TABLES:
                    grants = query_all(
                        conn,
                        "SELECT has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'SELECT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'INSERT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'DELETE'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'TRUNCATE')",
                    )
                    assert grants == [(True, True, False, False)], table_name
                # append-only 表无 UPDATE。
                for table_name in ("job_attempt_receipts", "job_events"):
                    update_grant = query_all(
                        conn,
                        "SELECT has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'UPDATE')",
                    )
                    assert update_grant == [(False,)], table_name
                # 列级 UPDATE 精确集合。
                _assert_app_column_updates(conn)
                # identity/immutable 列不可由 app 更新。
                with pytest.raises(Exception):
                    conn.execute(
                        text(
                            f"UPDATE {PLATFORM_SCHEMA_NAME}.job_runs "
                            "SET definition_id = gen_random_uuid()"
                        )
                    )
                conn.rollback()
                with pytest.raises(Exception):
                    conn.execute(
                        text(
                            f"UPDATE {PLATFORM_SCHEMA_NAME}.job_attempts "
                            "SET lease_token_sha256 = '0' * 64"
                        )
                    )
                conn.rollback()
                with pytest.raises(Exception):
                    conn.execute(
                        text(
                            f"UPDATE {PLATFORM_SCHEMA_NAME}.agent_run_correlations "
                            "SET reserved_host_run_id = 'run_' || repeat('0', 32)"
                        )
                    )
                conn.rollback()
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_app_role_rejects_direct_identity_payload_fingerprint_and_fence_token_mutation(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """app 直改 identity/payload/fingerprint/fence/token 列被双重拒绝。"""

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            conn = _connect(login.dsn)
            try:
                attempts = (
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.job_definitions SET job_type = 'x'",
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.job_definitions SET max_attempts = 9",
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.job_runs SET payload_bytes = decode('00', 'hex')",
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.job_runs SET request_fingerprint = repeat('0', 64)",
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.job_runs SET deadline_at = now()",
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.job_attempts SET fence = 9",
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.job_attempts SET lease_token_sha256 = repeat('f', 64)",
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.job_leases SET token_sha256 = repeat('f', 64)",
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.job_leases SET acquired_at = now()",
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.agent_run_correlations SET idempotency_key = 'x'",
                )
                for statement in attempts:
                    with pytest.raises(Exception):
                        conn.execute(text(statement))
                    conn.rollback()
            finally:
                conn.close()
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down(platform_cluster, database)


def _assert_app_column_updates(conn) -> None:
    """断言 app role 的列级 UPDATE 权限精确匹配契约。

    Args:
        conn: app 连接。

    Returns:
        无。

    Raises:
        AssertionError: 权限集合不匹配时抛出。
    """

    expected_columns = {
        "job_definitions": {"status", "updated_at", "version"},
        "job_runs": {
            "state",
            "available_at",
            "current_attempt_number",
            "next_event_sequence",
            "cancel_requested_at",
            "cancel_reason",
            "completed_at",
            "safe_failure_code",
            "updated_at",
            "version",
        },
        "job_attempts": {
            "state",
            "lease_expires_at",
            "last_heartbeat_at",
            "finished_at",
            "safe_failure_code",
            "updated_at",
            "version",
        },
        "job_leases": {"released_at", "release_reason", "updated_at", "version"},
        "agent_run_correlations": {
            "state",
            "observed_at",
            "last_observation_sha256",
            "updated_at",
            "version",
        },
    }
    for table_name, expected in expected_columns.items():
        actual: set[str] = set()
        for column in expected:
            granted = query_all(
                conn,
                "SELECT has_column_privilege(current_user, "
                f"'{PLATFORM_SCHEMA_NAME}.{table_name}', '{column}', 'UPDATE')",
            )
            if granted == [(True,)]:
                actual.add(column)
        # 断言已授权列恰为 expected；再补查未预期列无权限。
        assert actual == expected, table_name
        columns = query_all(
            conn,
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}' "
            f"AND table_name = '{table_name}'",
        )
        for column_row in columns:
            column = str(column_row[0])
            if column in expected:
                continue
            granted = query_all(
                conn,
                "SELECT has_column_privilege(current_user, "
                f"'{PLATFORM_SCHEMA_NAME}.{table_name}', '{column}', 'UPDATE')",
            )
            assert granted == [(False,)], f"{table_name}.{column}"
    for table_name in ("job_attempt_receipts", "job_events"):
        columns = query_all(
            conn,
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}' "
            f"AND table_name = '{table_name}'",
        )
        for column_row in columns:
            granted = query_all(
                conn,
                "SELECT has_column_privilege(current_user, "
                f"'{PLATFORM_SCHEMA_NAME}.{table_name}', "
                f"'{column_row[0]}', 'UPDATE')",
            )
            assert granted == [(False,)], f"{table_name}.{column_row[0]}"


_SCHEDULES_0004_TABLES: tuple[str, ...] = (
    "job_schedules",
    "job_schedule_occurrences",
)
"""0004 durable schedules 的两张 owner 表。"""

_SCHEDULE_A_ID = "40000000-0000-4000-8000-000000000001"
_SCHEDULE_B_ID = "40000000-0000-4000-8000-000000000002"
_SCHEDULE_DISABLED_ID = "40000000-0000-4000-8000-000000000003"
_SCHEDULE_DISABLED_HISTORY_ID = "40000000-0000-4000-8000-000000000004"


def _migrate_down_to_0003(cluster: PlatformCluster, database: str) -> None:
    """把数据库降级到 ``0003_durable_jobs``。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        RuntimeError: 0004 downgrade admission 拒绝时抛出。
    """

    from alembic import command
    from alembic.config import Config

    from tests.integration.investment.conftest import _ALEMBIC_INI, _MIGRATIONS_DIR

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    previous = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = _bootstrap_dsn(cluster, database)
    try:
        command.downgrade(cfg, "0003_durable_jobs")
    finally:
        if previous is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = previous


def _assert_0004_present(cluster: PlatformCluster, database: str) -> None:
    """断言 0004 两张表存在且 Alembic revision 未回退。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 表或 revision 缺失时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        rows = query_all(
            conn,
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}' "
            "AND table_name IN ('job_schedules', 'job_schedule_occurrences') "
            "ORDER BY table_name",
        )
        revision = query_all(conn, "SELECT version_num FROM alembic_version")
    finally:
        conn.close()
    assert [row[0] for row in rows] == [
        "job_schedule_occurrences",
        "job_schedules",
    ]
    assert revision == [("0004_durable_schedules",)]


def _assert_0004_absent(cluster: PlatformCluster, database: str) -> None:
    """断言 0004 表消失且 0003 durable jobs 完整保留。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        AssertionError: 0004 表仍存在或 0003 revision 漂移时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        rows = query_all(
            conn,
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}' "
            "AND table_name IN ('job_schedules', 'job_schedule_occurrences')",
        )
        revision = query_all(conn, "SELECT version_num FROM alembic_version")
    finally:
        conn.close()
    assert rows == []
    assert revision == [("0003_durable_jobs",)]
    _assert_0003_present(cluster, database)


def _schedule_insert_sql(
    *,
    schedule_id: str,
    tenant_id: str,
    schedule_key: str,
    state: str,
    next_fire_sql: str,
) -> str:
    """构造一条固定测试 schedule INSERT。

    Args:
        schedule_id: schedule UUID literal。
        tenant_id: tenant UUID literal。
        schedule_key: 唯一 schedule key。
        state: ``active`` 或 ``disabled``。
        next_fire_sql: cursor 的受控 SQL literal。

    Returns:
        可直接交给 SQLAlchemy ``text`` 的 INSERT 字符串。

    Raises:
        无。
    """

    return (
        f"INSERT INTO {PLATFORM_SCHEMA_NAME}.job_schedules ("
        "id, tenant_id, schedule_key, descriptor_job_type, "
        "descriptor_payload_schema_name, descriptor_payload_schema_version, "
        "descriptor_max_attempts, descriptor_retry_base_seconds, "
        "descriptor_retry_max_seconds, descriptor_lease_duration_seconds, "
        "payload_schema_name, payload_schema_version, payload_bytes, "
        "payload_sha256, cron_expression, timezone_name, misfire_policy, "
        "misfire_grace_seconds, job_deadline_seconds, state, next_fire_at) VALUES ("
        f"'{schedule_id}', '{tenant_id}', '{schedule_key}', 'agent_run', "
        "'dayu.job.payload', 1, 3, 1, 10, 60, 'dayu.job.payload', 1, "
        "decode('7b7d', 'hex'), repeat('a', 64), '* * * * *', 'UTC', "
        f"'coalesce_one', 60, 120, '{state}', {next_fire_sql})"
    )


def _snapshot_values_sql(
    *,
    idempotency_key: str,
    available_at_sql: str,
) -> str:
    """构造 occurrence 的完整冻结 enqueue snapshot values。

    Args:
        idempotency_key: tenant 内唯一幂等键。
        available_at_sql: 受控 ``TIMESTAMPTZ`` SQL literal。

    Returns:
        与 15 个 snapshot 列顺序一致的 SQL values 片段。

    Raises:
        无。
    """

    return (
        "'agent_run', 'dayu.job.payload', 1, 3, 1, 10, 60, "
        "'dayu.job.payload', 1, decode('7b7d', 'hex'), repeat('a', 64), "
        f"'{idempotency_key}', {available_at_sql}, "
        f"{available_at_sql} + interval '120 seconds', repeat('b', 64)"
    )


def _null_snapshot_values_sql() -> str:
    """返回 15 个全 NULL snapshot values。

    Args:
        无。

    Returns:
        与 15 个 snapshot 列顺序一致的全 NULL SQL 片段。

    Raises:
        无。
    """

    return ", ".join("NULL" for _ in range(15))


def _occurrence_insert_sql(
    *,
    occurrence_id: str,
    tenant_id: str,
    schedule_id: str,
    scheduled_for_sql: str,
    state: str,
    snapshot_values_sql: str,
    job_run_id_sql: str,
    coalesced_count_sql: str,
    skip_reason_sql: str,
) -> str:
    """构造一条固定测试 occurrence INSERT。

    Args:
        occurrence_id: occurrence UUID literal。
        tenant_id: tenant UUID literal。
        schedule_id: 所属 schedule UUID literal。
        scheduled_for_sql: 受控 ``TIMESTAMPTZ`` SQL literal。
        state: closed occurrence state。
        snapshot_values_sql: 完整或全 NULL snapshot values。
        job_run_id_sql: job UUID 或 NULL SQL literal。
        coalesced_count_sql: exact count 或 NULL SQL literal。
        skip_reason_sql: closed skip reason 或 NULL SQL literal。

    Returns:
        可直接交给 SQLAlchemy ``text`` 的 INSERT 字符串。

    Raises:
        无。
    """

    return (
        f"INSERT INTO {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences ("
        "id, tenant_id, schedule_id, schedule_version, scheduled_for, state, "
        "snapshot_descriptor_job_type, snapshot_descriptor_payload_schema_name, "
        "snapshot_descriptor_payload_schema_version, snapshot_descriptor_max_attempts, "
        "snapshot_descriptor_retry_base_seconds, snapshot_descriptor_retry_max_seconds, "
        "snapshot_descriptor_lease_duration_seconds, snapshot_payload_schema_name, "
        "snapshot_payload_schema_version, snapshot_payload_bytes, snapshot_payload_sha256, "
        "snapshot_idempotency_key, snapshot_available_at, snapshot_deadline_at, "
        "snapshot_request_fingerprint, job_run_id, coalesced_count, skip_reason) VALUES ("
        f"'{occurrence_id}', '{tenant_id}', '{schedule_id}', 1, "
        f"{scheduled_for_sql}, '{state}', {snapshot_values_sql}, {job_run_id_sql}, "
        f"{coalesced_count_sql}, {skip_reason_sql})"
    )


def _delete_0004_rows(cluster: PlatformCluster, database: str) -> None:
    """按 FK 逆序删除本测试创建的 0004 业务行。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 删除失败时抛出。
    """

    conn = _connect(_bootstrap_dsn(cluster, database))
    try:
        autocommit = _autocommit(conn)
        autocommit.execute(
            text(f"DELETE FROM {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences")
        )
        autocommit.execute(text(f"DELETE FROM {PLATFORM_SCHEMA_NAME}.job_schedules"))
    finally:
        conn.close()


class TestDurableSchedules0004Migration:
    """0004 durable schedules 的真实 PostgreSQL 16 契约。"""

    @pytest.mark.integration
    def test_schedule_tables_enforce_rls_grants_and_tenant_scoped_foreign_keys_on_postgres16(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """两表强制 RLS、最小 grant、immutable guard 与 tenant FK 均生效。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        _insert_tenant_b(platform_cluster, database)
        bootstrap = _connect(_bootstrap_dsn(platform_cluster, database))
        login: TemporaryLogin | None = None
        try:
            autocommit = _autocommit(bootstrap)
            autocommit.execute(
                text(
                    _schedule_insert_sql(
                        schedule_id=_SCHEDULE_A_ID,
                        tenant_id=_TENANT_A,
                        schedule_key="tenant-a-active",
                        state="active",
                        next_fire_sql="'2026-08-13 00:00:00+00'::timestamptz",
                    )
                )
            )
            autocommit.execute(
                text(
                    _schedule_insert_sql(
                        schedule_id=_SCHEDULE_B_ID,
                        tenant_id=_TENANT_B,
                        schedule_key="tenant-b-active",
                        state="active",
                        next_fire_sql="'2026-08-13 00:00:00+00'::timestamptz",
                    )
                )
            )
            relations = query_all(
                bootstrap,
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE n.nspname = '{PLATFORM_SCHEMA_NAME}' "
                "AND c.relname IN ('job_schedules', 'job_schedule_occurrences') "
                "ORDER BY c.relname",
            )
            assert relations == [
                ("job_schedule_occurrences", True, True),
                ("job_schedules", True, True),
            ]
            for table_name in _SCHEDULES_0004_TABLES:
                audit_grants = query_all(
                    bootstrap,
                    "SELECT has_table_privilege('dayu_platform_audit', "
                    f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'SELECT'), "
                    "has_table_privilege('dayu_platform_audit', "
                    f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'INSERT'), "
                    "has_table_privilege('dayu_platform_audit', "
                    f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'UPDATE'), "
                    "has_table_privilege('dayu_platform_audit', "
                    f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'DELETE')",
                )
                assert audit_grants == [(True, False, False, False)], table_name

            cross_tenant_occurrence = _occurrence_insert_sql(
                occurrence_id="41000000-0000-4000-8000-000000000001",
                tenant_id=_TENANT_A,
                schedule_id=_SCHEDULE_B_ID,
                scheduled_for_sql="'2026-08-12 00:00:00+00'::timestamptz",
                state="pending",
                snapshot_values_sql=_snapshot_values_sql(
                    idempotency_key="cross-tenant-fk",
                    available_at_sql="'2026-08-12 00:00:00+00'::timestamptz",
                ),
                job_run_id_sql="NULL",
                coalesced_count_sql="0",
                skip_reason_sql="NULL",
            )
            with pytest.raises(SQLAlchemyError):
                autocommit.execute(text(cross_tenant_occurrence))

            login = _make_app_login(platform_cluster, database)
            app = _connect(login.dsn)
            try:
                for table_name, expected_updates in {
                    "job_schedules": {
                        "state",
                        "next_fire_at",
                        "version",
                        "updated_at",
                    },
                    "job_schedule_occurrences": {
                        "state",
                        "job_run_id",
                        "skip_reason",
                        "updated_at",
                    },
                }.items():
                    table_grants = query_all(
                        app,
                        "SELECT has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'SELECT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'INSERT'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'UPDATE'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'DELETE'), "
                        "has_table_privilege(current_user, "
                        f"'{PLATFORM_SCHEMA_NAME}.{table_name}', 'TRUNCATE')",
                    )
                    assert table_grants == [(True, True, False, False, False)]
                    columns = query_all(
                        app,
                        "SELECT column_name FROM information_schema.columns "
                        f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}' "
                        f"AND table_name = '{table_name}'",
                    )
                    actual_updates = {
                        str(column[0])
                        for column in columns
                        if query_all(
                            app,
                            "SELECT has_column_privilege(current_user, "
                            f"'{PLATFORM_SCHEMA_NAME}.{table_name}', "
                            f"'{column[0]}', 'UPDATE')",
                        )
                        == [(True,)]
                    }
                    assert actual_updates == expected_updates, table_name

                unseen = query_all(
                    app,
                    f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.job_schedules",
                )
                assert unseen == []
                app.execute(text(f"SET LOCAL app.tenant_id = '{_TENANT_A}'"))
                tenant_a = query_all(
                    app,
                    f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.job_schedules",
                )
                assert tenant_a == [(UUID(_SCHEDULE_A_ID),)]
                with pytest.raises(SQLAlchemyError):
                    app.execute(
                        text(
                            _schedule_insert_sql(
                                schedule_id="40000000-0000-4000-8000-000000000099",
                                tenant_id=_TENANT_B,
                                schedule_key="rls-cross-tenant",
                                state="disabled",
                                next_fire_sql="NULL",
                            )
                        )
                    )
                app.rollback()
                app.execute(text(f"SET LOCAL app.tenant_id = '{_TENANT_A}'"))
                with pytest.raises(SQLAlchemyError):
                    app.execute(
                        text(
                            f"UPDATE {PLATFORM_SCHEMA_NAME}.job_schedules "
                            "SET schedule_key = 'mutated' "
                            f"WHERE id = '{_SCHEDULE_A_ID}'"
                        )
                    )
                app.rollback()
            finally:
                app.close()
        finally:
            bootstrap.close()
            if login is not None:
                drop_temporary_login(platform_cluster, login)
            _delete_0004_rows(platform_cluster, database)
            _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_disabled_draft_allows_null_cursor_but_active_requires_nonnull_on_postgres16(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """active 必有 cursor；disabled 可为 NULL 或保留历史 cursor。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            autocommit = _autocommit(conn)
            with pytest.raises(SQLAlchemyError):
                autocommit.execute(
                    text(
                        _schedule_insert_sql(
                            schedule_id="40000000-0000-4000-8000-000000000090",
                            tenant_id=_TENANT_A,
                            schedule_key="invalid-active-null",
                            state="active",
                            next_fire_sql="NULL",
                        )
                    )
                )
            autocommit.execute(
                text(
                    _schedule_insert_sql(
                        schedule_id=_SCHEDULE_DISABLED_ID,
                        tenant_id=_TENANT_A,
                        schedule_key="disabled-draft",
                        state="disabled",
                        next_fire_sql="NULL",
                    )
                )
            )
            autocommit.execute(
                text(
                    _schedule_insert_sql(
                        schedule_id=_SCHEDULE_DISABLED_HISTORY_ID,
                        tenant_id=_TENANT_A,
                        schedule_key="disabled-history",
                        state="disabled",
                        next_fire_sql="'2026-08-13 00:00:00+00'::timestamptz",
                    )
                )
            )
            rows = query_all(
                conn,
                f"SELECT schedule_key, next_fire_at IS NULL FROM {PLATFORM_SCHEMA_NAME}.job_schedules "
                "ORDER BY schedule_key",
            )
            assert rows == [
                ("disabled-draft", True),
                ("disabled-history", False),
            ]
        finally:
            conn.close()
            _delete_0004_rows(platform_cluster, database)
            _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_schedule_occurrence_state_snapshot_job_and_skip_reason_checks_are_exact(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """snapshot/available/count/skip reason 的 closed 矩阵由 PG16 直接拒绝漂移。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        fire = "'2026-08-12 00:00:00+00'::timestamptz"
        try:
            autocommit = _autocommit(conn)
            autocommit.execute(
                text(
                    _schedule_insert_sql(
                        schedule_id=_SCHEDULE_DISABLED_ID,
                        tenant_id=_TENANT_A,
                        schedule_key="occurrence-matrix",
                        state="disabled",
                        next_fire_sql="NULL",
                    )
                )
            )
            valid_statements = (
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000001",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql=fire,
                    state="pending",
                    snapshot_values_sql=_snapshot_values_sql(
                        idempotency_key="valid-pending",
                        available_at_sql=fire,
                    ),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="0",
                    skip_reason_sql="NULL",
                ),
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000002",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql="'2026-08-12 00:01:00+00'::timestamptz",
                    state="skipped",
                    snapshot_values_sql=_null_snapshot_values_sql(),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="0",
                    skip_reason_sql="'misfire_expired'",
                ),
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000003",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql="'2026-08-12 00:02:00+00'::timestamptz",
                    state="skipped",
                    snapshot_values_sql=_null_snapshot_values_sql(),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="NULL",
                    skip_reason_sql="'lookback_exceeded'",
                ),
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000004",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql="'2026-08-12 00:03:00+00'::timestamptz",
                    state="skipped",
                    snapshot_values_sql=_null_snapshot_values_sql(),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="NULL",
                    skip_reason_sql="'candidate_scan_limit_exceeded'",
                ),
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000005",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql="'2026-08-12 00:04:00+00'::timestamptz",
                    state="skipped",
                    snapshot_values_sql=_snapshot_values_sql(
                        idempotency_key="valid-disabled-snapshot",
                        available_at_sql="'2026-08-12 00:04:00+00'::timestamptz",
                    ),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="2",
                    skip_reason_sql="'schedule_disabled'",
                ),
            )
            for statement in valid_statements:
                autocommit.execute(text(statement))

            invalid_statements = (
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000011",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql="'2026-08-12 00:11:00+00'::timestamptz",
                    state="pending",
                    snapshot_values_sql=_snapshot_values_sql(
                        idempotency_key="invalid-null-count",
                        available_at_sql="'2026-08-12 00:11:00+00'::timestamptz",
                    ),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="NULL",
                    skip_reason_sql="NULL",
                ),
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000012",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql="'2026-08-12 00:12:00+00'::timestamptz",
                    state="pending",
                    snapshot_values_sql=_snapshot_values_sql(
                        idempotency_key="invalid-available",
                        available_at_sql="'2026-08-12 00:13:00+00'::timestamptz",
                    ),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="0",
                    skip_reason_sql="NULL",
                ),
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000013",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql="'2026-08-12 00:13:00+00'::timestamptz",
                    state="skipped",
                    snapshot_values_sql=_null_snapshot_values_sql(),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="0",
                    skip_reason_sql="'candidate_scan_limit_exceeded'",
                ),
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000014",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql="'2026-08-12 00:14:00+00'::timestamptz",
                    state="skipped",
                    snapshot_values_sql=_null_snapshot_values_sql(),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="NULL",
                    skip_reason_sql="'schedule_disabled'",
                ),
                _occurrence_insert_sql(
                    occurrence_id="42000000-0000-4000-8000-000000000015",
                    tenant_id=_TENANT_A,
                    schedule_id=_SCHEDULE_DISABLED_ID,
                    scheduled_for_sql="'2026-08-12 00:15:00+00'::timestamptz",
                    state="skipped",
                    snapshot_values_sql=_null_snapshot_values_sql(),
                    job_run_id_sql="NULL",
                    coalesced_count_sql="-1",
                    skip_reason_sql="'misfire_expired'",
                ),
            )
            for statement in invalid_statements:
                with pytest.raises(SQLAlchemyError):
                    autocommit.execute(text(statement))
            persisted = query_all(
                conn,
                f"SELECT count(*) FROM {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences",
            )
            assert persisted == [(5,)]
        finally:
            conn.close()
            _delete_0004_rows(platform_cluster, database)
            _migrate_down(platform_cluster, database)

    @pytest.mark.integration
    def test_schedule_migration_upgrade_downgrade_and_dirty_database_admission(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """0004 可 clean 循环，并对业务行、外部依赖、role member fail closed。

        Args:
            platform_cluster: 共享临时 cluster。
            lifecycle_database: 随机独立数据库工厂。

        Returns:
            无。

        Raises:
            无。
        """

        database = lifecycle_database()
        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            _autocommit(conn).execute(
                text(
                    _schedule_insert_sql(
                        schedule_id=_SCHEDULE_DISABLED_ID,
                        tenant_id=_TENANT_A,
                        schedule_key="dirty-downgrade",
                        state="disabled",
                        next_fire_sql="NULL",
                    )
                )
            )
        finally:
            conn.close()
        with pytest.raises(RuntimeError, match="仍存在业务行"):
            _migrate_down_to_0003(platform_cluster, database)
        _assert_0004_present(platform_cluster, database)
        _delete_0004_rows(platform_cluster, database)
        _migrate_down_to_0003(platform_cluster, database)
        _assert_0004_absent(platform_cluster, database)

        _migrate_up(platform_cluster, database)
        conn = _connect(_bootstrap_dsn(platform_cluster, database))
        try:
            _autocommit(conn).execute(
                text(
                    "CREATE VIEW external_schedule_view AS "
                    f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.job_schedules"
                )
            )
        finally:
            conn.close()
        try:
            with pytest.raises(RuntimeError, match="外部依赖"):
                _migrate_down_to_0003(platform_cluster, database)
            _assert_0004_present(platform_cluster, database)
        finally:
            conn = _connect(_bootstrap_dsn(platform_cluster, database))
            try:
                _autocommit(conn).execute(
                    text("DROP VIEW IF EXISTS external_schedule_view")
                )
            finally:
                conn.close()
        _migrate_down_to_0003(platform_cluster, database)
        _assert_0004_absent(platform_cluster, database)

        _migrate_up(platform_cluster, database)
        login = _make_app_login(platform_cluster, database)
        try:
            with pytest.raises(RuntimeError, match="外部 member"):
                _migrate_down_to_0003(platform_cluster, database)
            _assert_0004_present(platform_cluster, database)
        finally:
            drop_temporary_login(platform_cluster, login)
        _migrate_down_to_0003(platform_cluster, database)
        _assert_0004_absent(platform_cluster, database)
        _migrate_down(platform_cluster, database)
