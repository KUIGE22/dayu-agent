"""数据源同步 operation、health 与 semantic alert schema 迁移。

Revision ID: 0005_source_connectors_health
Revises: 0004_durable_schedules
Create Date: 2026-08-13

本迁移在单一 Alembic 事务中把平台 schema 从 24 表推进到 27 表：

- 为 ``source_sync_runs`` 增加 durable Job lineage、closed receipt/result
  与精确 outcome/count 约束；
- 为 ``source_health_snapshots`` 增加 health version 与强三列 run lineage；
- 新增 ``source_sync_operations``、``source_health_states`` 与
  ``source_health_alert_outbox``；
- 以数据库 CHECK、owner-proof trigger、RLS 与最小列级 UPDATE grant
  闭合 insert、transition、immutable 与 tenant isolation 契约。

upgrade 先验证 0004 baseline catalog 与 legacy 数据，再按 parent-key ->
child-FK DAG 创建对象；downgrade 先验证 0005 catalog并拒绝业务数据、
恢复旧 partial unique 时的冲突与外部依赖，再无 CASCADE 精确逆序回滚。
"""

from __future__ import annotations

from collections.abc import Iterable

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection

from dayu.investment.storage.db import (
    PLATFORM_APP_ROLE,
    PLATFORM_AUDIT_ROLE,
    PLATFORM_SCHEMA_NAME,
)

revision = "0005_source_connectors_health"
down_revision = "0004_durable_schedules"
branch_labels = None
depends_on = None

_SCHEMA = PLATFORM_SCHEMA_NAME
_TENANT_EXPRESSION = "nullif(current_setting('app.tenant_id', true), '')::uuid"
_HEX64 = "'^[0-9a-f]{64}$'"

_NEW_TABLES: tuple[str, ...] = (
    "source_sync_operations",
    "source_health_states",
    "source_health_alert_outbox",
)
_AFFECTED_TABLES: tuple[str, ...] = (
    "source_sync_runs",
    "source_health_snapshots",
    *_NEW_TABLES,
)
_BASELINE_PRIVATE_TABLES: tuple[str, ...] = (
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
_BASELINE_PUBLIC_TABLES: tuple[str, ...] = (
    "companies",
    "securities",
    "source_definitions",
)
_BASELINE_TABLES: tuple[str, ...] = _BASELINE_PRIVATE_TABLES + _BASELINE_PUBLIC_TABLES
_DOWNGRADE_LOCK_TABLES: tuple[str, ...] = (
    "source_health_alert_outbox",
    "source_health_states",
    "source_sync_operations",
    "source_health_snapshots",
    "source_sync_runs",
    "source_subscriptions",
    "job_attempts",
)
_REPLACED_BASELINE_INDEX_NAMES: tuple[str, ...] = (
    "uq_source_subscriptions_tenant_wide",
    "uq_source_subscriptions_company",
    "uq_source_subscriptions_security",
)
_RUN_COLUMNS: tuple[str, ...] = (
    "job_run_id",
    "job_attempt_id",
    "payload_sha256",
    "outcome",
    "retry_recommended",
    "records_downloaded",
    "records_reused",
    "records_ignored",
    "records_failed",
    "latest_source_observed_date",
    "receipt_json",
    "receipt_sha256",
    "result_json",
    "result_sha256",
)
_RUN_CORE_COLUMNS: tuple[str, ...] = tuple(
    column for column in _RUN_COLUMNS if column != "latest_source_observed_date"
)
_HEALTH_ERRORS: tuple[str, ...] = (
    "partial_batch",
    "unsupported_market",
    "unsupported_form",
    "stale_data",
    "provider_rate_limited",
    "provider_unavailable",
    "fins_invariant",
)
_HEALTH_ERROR_SQL = ", ".join(f"'{value}'" for value in _HEALTH_ERRORS)

_BASELINE_POLICY_EXPRESSION_TENANT = (
    "((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid = tenant_id)"
)
_BASELINE_POLICY_EXPRESSION_ORGANIZATION = (
    "((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid = id)"
)
_BASELINE_POLICY_MANIFEST: frozenset[tuple[str, str, str, str, str, str]] = frozenset(
    (
        table_name,
        "tenant_isolation",
        "ALL",
        f"{{{PLATFORM_APP_ROLE}}}",
        (
            _BASELINE_POLICY_EXPRESSION_ORGANIZATION
            if table_name == "organizations"
            else _BASELINE_POLICY_EXPRESSION_TENANT
        ),
        (
            _BASELINE_POLICY_EXPRESSION_ORGANIZATION
            if table_name == "organizations"
            else _BASELINE_POLICY_EXPRESSION_TENANT
        ),
    )
    for table_name in _BASELINE_PRIVATE_TABLES
)
_BASELINE_APP_BROAD_UPDATE_TABLES: tuple[str, ...] = (
    *_BASELINE_PUBLIC_TABLES,
    "organizations",
    "users",
    "roles",
    "permissions",
    "api_tokens",
    "source_subscriptions",
)
_BASELINE_APP_JOIN_TABLES: tuple[str, ...] = ("user_roles", "role_permissions")
_BASELINE_APP_APPEND_TABLES: tuple[str, ...] = (
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
_BASELINE_APP_TABLE_ACL_MANIFEST: frozenset[tuple[str, str, bool]] = frozenset(
    {
        (table_name, privilege, False)
        for table_name in _BASELINE_APP_BROAD_UPDATE_TABLES
        for privilege in ("INSERT", "SELECT", "UPDATE")
    }
    | {
        (table_name, privilege, False)
        for table_name in _BASELINE_APP_JOIN_TABLES
        for privilege in ("DELETE", "INSERT", "SELECT")
    }
    | {
        (table_name, privilege, False)
        for table_name in _BASELINE_APP_APPEND_TABLES
        for privilege in ("INSERT", "SELECT")
    }
)
_BASELINE_APP_COLUMN_UPDATE_MANIFEST: frozenset[tuple[str, str, str, bool]] = frozenset(
    {
        ("job_definitions", column, "UPDATE", False)
        for column in ("status", "updated_at", "version")
    }
    | {
        ("job_runs", column, "UPDATE", False)
        for column in (
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
        )
    }
    | {
        ("job_attempts", column, "UPDATE", False)
        for column in (
            "state",
            "lease_expires_at",
            "last_heartbeat_at",
            "finished_at",
            "safe_failure_code",
            "updated_at",
            "version",
        )
    }
    | {
        ("job_leases", column, "UPDATE", False)
        for column in ("released_at", "release_reason", "updated_at", "version")
    }
    | {
        ("agent_run_correlations", column, "UPDATE", False)
        for column in (
            "state",
            "observed_at",
            "last_observation_sha256",
            "updated_at",
            "version",
        )
    }
    | {
        ("job_schedules", column, "UPDATE", False)
        for column in ("state", "next_fire_at", "version", "updated_at")
    }
    | {
        ("job_schedule_occurrences", column, "UPDATE", False)
        for column in ("state", "job_run_id", "skip_reason", "updated_at")
    }
)
_NEW_TABLE_OWNER_PRIVILEGES: tuple[str, ...] = (
    "DELETE",
    "INSERT",
    "REFERENCES",
    "SELECT",
    "TRIGGER",
    "TRUNCATE",
    "UPDATE",
)
_NEW_TABLE_APP_COLUMN_UPDATE_MANIFEST: frozenset[tuple[str, str, str, bool]] = frozenset(
    {
        ("source_sync_operations", column, "UPDATE", False)
        for column in (
            "owner_attempt_id",
            "generation",
            "acquired_at",
            "owner_binding_disposition",
            "state",
            "terminal_source_sync_run_id",
            "updated_at",
        )
    }
    | {
        ("source_health_states", column, "UPDATE", False)
        for column in (
            "status",
            "consecutive_failures",
            "safe_error_code",
            "version",
            "observed_at",
            "last_source_sync_run_id",
            "updated_at",
        )
    }
)

_UNIQUE_MANIFEST: tuple[str, ...] = (
    "uq_job_attempts_tenant_job_run_id_v2",
    "uq_source_sync_runs_tenant_subscription_id_v2",
    "uq_source_sync_runs_tenant_subscription_job_id_v2",
    "uq_source_sync_runs_tenant_sub_job_attempt_id_v2",
    "uq_source_health_snapshots_tenant_subscription_id_v2",
    "uq_source_health_snapshots_tenant_sub_run_version_id_v2",
    "uq_source_sync_operations_tenant_id",
    "uq_source_sync_operations_tenant_job_run",
    "uq_source_health_states_tenant_id",
    "uq_source_health_states_tenant_subscription",
    "uq_source_health_alert_outbox_tenant_id",
    "uq_source_health_alert_outbox_tenant_dedupe",
)
_PARTIAL_UNIQUE_INDEX_MANIFEST: tuple[str, ...] = (
    "uq_source_sync_runs_tenant_job_run_v2",
    "uq_source_sync_runs_tenant_job_attempt_v2",
    "uq_source_health_snapshots_tenant_subscription_version_v2",
)
_INDEX_MANIFEST: tuple[str, ...] = (
    "ix_source_sync_operations_tenant_state_updated",
    "ix_source_health_states_tenant_status_observed",
    "ix_source_health_alert_outbox_tenant_created",
    "ix_source_health_alert_outbox_tenant_sub_created",
)
_FK_MANIFEST: tuple[str, ...] = (
    "fk_source_sync_runs_tenant_job_attempt_v2",
    "fk_source_health_snapshots_tenant_subscription_run_v2",
    "fk_source_sync_operations_tenant_id_organizations",
    "fk_source_sync_operations_tenant_job_attempt",
    "fk_source_sync_operations_tenant_subscription",
    "fk_source_sync_operations_terminal_run",
    "fk_source_health_states_tenant_id_organizations",
    "fk_source_health_states_last_run",
    "fk_source_health_alert_outbox_tenant_id_organizations",
    "fk_source_health_alert_outbox_run",
    "fk_source_health_alert_outbox_snapshot",
)
_CHECK_SOURCE_SYNC_RUNS_V1_CORE_PRESENCE = (
    f"(({' AND '.join(f'{column} IS NULL' for column in _RUN_CORE_COLUMNS)}) OR "
    f"({' AND '.join(f'{column} IS NOT NULL' for column in _RUN_CORE_COLUMNS)}))"
)
_CHECK_SOURCE_SYNC_RUNS_V1_COUNTS = (
    "job_run_id IS NULL OR (records_downloaded >= 0 AND records_reused >= 0 "
    "AND records_ignored >= 0 AND records_failed >= 0 "
    "AND records_discovered = records_downloaded + records_reused + records_ignored + records_failed "
    "AND records_ingested = records_downloaded + records_reused "
    "AND ((records_ingested > 0) = (latest_source_observed_date IS NOT NULL)))"
)
_CHECK_SOURCE_SYNC_RUNS_V1_OUTCOME_SHAPE = (
    "job_run_id IS NULL OR (status IN ('succeeded', 'failed') AND finished_at IS NOT NULL "
    "AND jsonb_typeof(receipt_json) = 'object' AND jsonb_typeof(result_json) = 'object' "
    f"AND payload_sha256 ~ {_HEX64} AND receipt_sha256 ~ {_HEX64} "
    f"AND result_sha256 ~ {_HEX64} "
    "AND ((outcome = 'succeeded' AND status = 'succeeded' AND safe_error_code IS NULL "
    "AND retry_recommended = false AND records_ingested > 0 AND records_failed = 0) "
    "OR (outcome = 'no_change' AND status = 'succeeded' AND safe_error_code IS NULL "
    "AND retry_recommended = false AND records_ingested = 0 AND records_failed = 0) "
    "OR (outcome = 'partial' AND status = 'succeeded' "
    "AND safe_error_code = 'partial_batch' AND retry_recommended = true "
    "AND records_ingested > 0 AND records_failed > 0) "
    "OR (outcome = 'skipped_disabled' AND status = 'succeeded' "
    "AND safe_error_code IS NULL AND retry_recommended = false "
    "AND records_downloaded = 0 AND records_reused = 0 "
    "AND records_ignored = 0 AND records_failed = 0) "
    "OR (outcome = 'stale_subscription' AND status = 'failed' "
    "AND safe_error_code = 'stale_subscription' AND retry_recommended = false "
    "AND records_downloaded = 0 AND records_reused = 0 "
    "AND records_ignored = 0 AND records_failed = 0) "
    "OR (outcome = 'failed' AND status = 'failed' AND safe_error_code IS NOT NULL "
    "AND safe_error_code IN ('unsupported_market', 'unsupported_form', 'stale_data', "
    "'provider_rate_limited', 'provider_unavailable', 'fins_invariant') "
    "AND retry_recommended = (safe_error_code IN "
    "('provider_rate_limited', 'provider_unavailable')) "
    "AND ((safe_error_code = 'stale_data' AND records_ingested > 0) "
    "OR (safe_error_code = 'provider_unavailable' AND records_downloaded = 0 "
    "AND records_reused = 0) OR (safe_error_code IN ('unsupported_market', "
    "'unsupported_form', 'provider_rate_limited', 'fins_invariant') "
    "AND records_downloaded = 0 AND records_reused = 0 "
    "AND records_ignored = 0 AND records_failed = 0)))))"
)
_CHECK_SOURCE_HEALTH_SNAPSHOTS_V2_SHAPE = (
    "((status = 'healthy' AND consecutive_failures = 0 AND safe_error_code IS NULL) "
    "OR (status IN ('degraded', 'failing', 'disabled') AND consecutive_failures > 0 "
    f"AND safe_error_code IS NOT NULL AND safe_error_code IN ({_HEALTH_ERROR_SQL}))) "
    "AND (health_state_version IS NULL OR (health_state_version > 0 AND "
    "((sync_run_id IS NOT NULL AND latency_ms IS NOT NULL AND latency_ms >= 0) "
    "OR (sync_run_id IS NULL AND latency_ms IS NULL AND status = 'healthy' "
    "AND consecutive_failures = 0 AND safe_error_code IS NULL))))"
)
_CHECK_SOURCE_SYNC_OPERATIONS_STATE_SHAPE = (
    "generation > 0 AND owner_binding_disposition IN ('ready', 'disabled', 'stale') "
    "AND ((state = 'active' AND terminal_source_sync_run_id IS NULL) "
    "OR (state = 'terminal' AND terminal_source_sync_run_id IS NOT NULL))"
)
_CHECK_SOURCE_SYNC_OPERATIONS_HASHES = (
    f"payload_sha256 ~ {_HEX64} AND execution_snapshot_sha256 ~ {_HEX64}"
)
_CHECK_SOURCE_SYNC_OPERATIONS_SNAPSHOT_OBJECT = (
    "jsonb_typeof(execution_snapshot_json) = 'object'"
)
_CHECK_SOURCE_HEALTH_STATES_SHAPE = (
    "version > 0 AND consecutive_failures >= 0 "
    "AND ((status = 'healthy' AND consecutive_failures = 0 AND safe_error_code IS NULL) "
    "OR (status IN ('degraded', 'failing', 'disabled') "
    "AND consecutive_failures > 0 AND safe_error_code IS NOT NULL "
    f"AND safe_error_code IN ({_HEALTH_ERROR_SQL})))"
)
_CHECK_SOURCE_HEALTH_ALERT_OUTBOX_SHAPE = (
    "health_state_version > 0 AND alert_kind IN ('degraded', 'failing', 'disabled') "
    "AND alert_kind = target_status AND safe_error_code IS NOT NULL "
    f"AND safe_error_code IN ({_HEALTH_ERROR_SQL}) "
    f"AND dedupe_key ~ {_HEX64} AND event_sha256 ~ {_HEX64} "
    "AND jsonb_typeof(event_json) = 'object'"
)
_CHECK_DEFINITION_MANIFEST: tuple[tuple[str, str, str], ...] = (
    (
        "source_sync_runs",
        "ck_source_sync_runs_v1_core_presence",
        _CHECK_SOURCE_SYNC_RUNS_V1_CORE_PRESENCE,
    ),
    (
        "source_sync_runs",
        "ck_source_sync_runs_v1_counts",
        _CHECK_SOURCE_SYNC_RUNS_V1_COUNTS,
    ),
    (
        "source_sync_runs",
        "ck_source_sync_runs_v1_outcome_shape",
        _CHECK_SOURCE_SYNC_RUNS_V1_OUTCOME_SHAPE,
    ),
    (
        "source_health_snapshots",
        "ck_source_health_snapshots_v2_shape",
        _CHECK_SOURCE_HEALTH_SNAPSHOTS_V2_SHAPE,
    ),
    (
        "source_sync_operations",
        "ck_source_sync_operations_state_shape",
        _CHECK_SOURCE_SYNC_OPERATIONS_STATE_SHAPE,
    ),
    (
        "source_sync_operations",
        "ck_source_sync_operations_hashes",
        _CHECK_SOURCE_SYNC_OPERATIONS_HASHES,
    ),
    (
        "source_sync_operations",
        "ck_source_sync_operations_snapshot_object",
        _CHECK_SOURCE_SYNC_OPERATIONS_SNAPSHOT_OBJECT,
    ),
    (
        "source_health_states",
        "ck_source_health_states_shape",
        _CHECK_SOURCE_HEALTH_STATES_SHAPE,
    ),
    (
        "source_health_alert_outbox",
        "ck_source_health_alert_outbox_shape",
        _CHECK_SOURCE_HEALTH_ALERT_OUTBOX_SHAPE,
    ),
)
_CHECK_MANIFEST: tuple[str, ...] = tuple(
    constraint_name
    for _table_name, constraint_name, _definition in _CHECK_DEFINITION_MANIFEST
)
_INSERT_GUARDS: tuple[tuple[str, str], ...] = (
    ("source_sync_runs_require_v1_insert", "source_sync_runs"),
    ("source_health_snapshots_require_v2_insert", "source_health_snapshots"),
    ("source_sync_operations_require_initial_insert", "source_sync_operations"),
    ("source_health_states_require_initial_insert", "source_health_states"),
)
_APPEND_ONLY_GUARDS: tuple[tuple[str, str], ...] = (
    ("guard_source_sync_runs_append_only", "source_sync_runs"),
    ("guard_source_health_snapshots_append_only", "source_health_snapshots"),
    ("guard_source_health_alert_outbox_append_only", "source_health_alert_outbox"),
)
_TRANSITION_GUARDS: tuple[tuple[str, str], ...] = (
    ("guard_source_sync_operations_transition", "source_sync_operations"),
    ("guard_source_health_states_transition", "source_health_states"),
)
_DELETE_GUARDS: tuple[tuple[str, str], ...] = (
    ("guard_source_sync_operations_delete", "source_sync_operations"),
    ("guard_source_health_states_delete", "source_health_states"),
)
_FUNCTION_MANIFEST: tuple[str, ...] = tuple(
    function_name
    for function_name, _ in (
        _INSERT_GUARDS
        + _APPEND_ONLY_GUARDS
        + _TRANSITION_GUARDS
        + _DELETE_GUARDS
    )
)
_TRIGGER_MANIFEST: tuple[tuple[str, str], ...] = tuple(
    (f"{function_name}_trigger", table_name)
    for function_name, table_name in (
        _INSERT_GUARDS
        + _APPEND_ONLY_GUARDS
        + _TRANSITION_GUARDS
        + _DELETE_GUARDS
    )
)
_NEW_0005_OBJECT_NAMES: tuple[str, ...] = (
    "pk_source_sync_operations",
    "pk_source_health_states",
    "pk_source_health_alert_outbox",
    *_UNIQUE_MANIFEST,
    *_PARTIAL_UNIQUE_INDEX_MANIFEST,
    *_INDEX_MANIFEST,
    *_FK_MANIFEST,
    *_CHECK_MANIFEST,
    *_FUNCTION_MANIFEST,
    *(trigger_name for trigger_name, _ in _TRIGGER_MANIFEST),
)

_UNIQUE_SHAPES: tuple[tuple[str, str, str], ...] = (
    ("uq_job_attempts_tenant_job_run_id_v2", "job_attempts", "tenant_id,job_run_id,id"),
    (
        "uq_source_sync_runs_tenant_subscription_id_v2",
        "source_sync_runs",
        "tenant_id,subscription_id,id",
    ),
    (
        "uq_source_sync_runs_tenant_subscription_job_id_v2",
        "source_sync_runs",
        "tenant_id,subscription_id,job_run_id,id",
    ),
    (
        "uq_source_sync_runs_tenant_sub_job_attempt_id_v2",
        "source_sync_runs",
        "tenant_id,subscription_id,job_run_id,job_attempt_id,id",
    ),
    (
        "uq_source_health_snapshots_tenant_subscription_id_v2",
        "source_health_snapshots",
        "tenant_id,subscription_id,id",
    ),
    (
        "uq_source_health_snapshots_tenant_sub_run_version_id_v2",
        "source_health_snapshots",
        "tenant_id,subscription_id,sync_run_id,health_state_version,id",
    ),
    (
        "uq_source_sync_operations_tenant_id",
        "source_sync_operations",
        "tenant_id,id",
    ),
    (
        "uq_source_sync_operations_tenant_job_run",
        "source_sync_operations",
        "tenant_id,job_run_id",
    ),
    ("uq_source_health_states_tenant_id", "source_health_states", "tenant_id,id"),
    (
        "uq_source_health_states_tenant_subscription",
        "source_health_states",
        "tenant_id,subscription_id",
    ),
    (
        "uq_source_health_alert_outbox_tenant_id",
        "source_health_alert_outbox",
        "tenant_id,id",
    ),
    (
        "uq_source_health_alert_outbox_tenant_dedupe",
        "source_health_alert_outbox",
        "tenant_id,dedupe_key",
    ),
)

_FK_SHAPES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "fk_source_sync_runs_tenant_job_attempt_v2",
        "source_sync_runs",
        "tenant_id,job_run_id,job_attempt_id",
        "job_attempts",
        "tenant_id,job_run_id,id",
    ),
    (
        "fk_source_health_snapshots_tenant_subscription_run_v2",
        "source_health_snapshots",
        "tenant_id,subscription_id,sync_run_id",
        "source_sync_runs",
        "tenant_id,subscription_id,id",
    ),
    (
        "fk_source_sync_operations_tenant_id_organizations",
        "source_sync_operations",
        "tenant_id",
        "organizations",
        "id",
    ),
    (
        "fk_source_sync_operations_tenant_job_attempt",
        "source_sync_operations",
        "tenant_id,job_run_id,owner_attempt_id",
        "job_attempts",
        "tenant_id,job_run_id,id",
    ),
    (
        "fk_source_sync_operations_tenant_subscription",
        "source_sync_operations",
        "tenant_id,subscription_id",
        "source_subscriptions",
        "tenant_id,id",
    ),
    (
        "fk_source_sync_operations_terminal_run",
        "source_sync_operations",
        "tenant_id,subscription_id,job_run_id,owner_attempt_id,terminal_source_sync_run_id",
        "source_sync_runs",
        "tenant_id,subscription_id,job_run_id,job_attempt_id,id",
    ),
    (
        "fk_source_health_states_tenant_id_organizations",
        "source_health_states",
        "tenant_id",
        "organizations",
        "id",
    ),
    (
        "fk_source_health_states_last_run",
        "source_health_states",
        "tenant_id,subscription_id,last_source_sync_run_id",
        "source_sync_runs",
        "tenant_id,subscription_id,id",
    ),
    (
        "fk_source_health_alert_outbox_tenant_id_organizations",
        "source_health_alert_outbox",
        "tenant_id",
        "organizations",
        "id",
    ),
    (
        "fk_source_health_alert_outbox_run",
        "source_health_alert_outbox",
        "tenant_id,subscription_id,source_sync_run_id",
        "source_sync_runs",
        "tenant_id,subscription_id,id",
    ),
    (
        "fk_source_health_alert_outbox_snapshot",
        "source_health_alert_outbox",
        "tenant_id,subscription_id,source_sync_run_id,health_state_version,health_snapshot_id",
        "source_health_snapshots",
        "tenant_id,subscription_id,sync_run_id,health_state_version,id",
    ),
)

_AFFECTED_BASELINE_CONSTRAINT_IDENTITIES: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("source_sync_runs", "pk_source_sync_runs", "p"),
        ("source_sync_runs", "uq_source_sync_runs_tenant_id_id", "u"),
        (
            "source_sync_runs",
            "uq_source_sync_runs_tenant_id_idempotency_key",
            "u",
        ),
        (
            "source_sync_runs",
            "fk_source_sync_runs_tenant_id_organizations",
            "f",
        ),
        (
            "source_sync_runs",
            "fk_source_sync_runs_tenant_subscription_source_subscriptions",
            "f",
        ),
        ("source_sync_runs", "ck_source_sync_runs_status", "c"),
        (
            "source_sync_runs",
            "ck_source_sync_runs_records_discovered_nonnegative",
            "c",
        ),
        (
            "source_sync_runs",
            "ck_source_sync_runs_records_ingested_nonnegative",
            "c",
        ),
        (
            "source_sync_runs",
            "ck_source_sync_runs_finished_at_after_started_at",
            "c",
        ),
        (
            "source_sync_runs",
            "ck_source_sync_runs_idempotency_key_nonblank",
            "c",
        ),
        ("source_health_snapshots", "pk_source_health_snapshots", "p"),
        (
            "source_health_snapshots",
            "uq_source_health_snapshots_tenant_id_id",
            "u",
        ),
        (
            "source_health_snapshots",
            "fk_source_health_snapshots_tenant_id_organizations",
            "f",
        ),
        (
            "source_health_snapshots",
            "fk_source_health_snapshots_tenant_subscription",
            "f",
        ),
        ("source_health_snapshots", "ck_source_health_snapshots_status", "c"),
        (
            "source_health_snapshots",
            "ck_source_health_snapshots_consecutive_failures_nonnegative",
            "c",
        ),
        (
            "source_health_snapshots",
            "ck_source_health_snapshots_latency_nonnegative",
            "c",
        ),
    }
)
_AFFECTED_CONSTRAINT_IDENTITY_MANIFEST: frozenset[tuple[str, str, str]] = frozenset(
    _AFFECTED_BASELINE_CONSTRAINT_IDENTITIES
    | {
        (table_name, constraint_name, "u")
        for constraint_name, table_name, _columns in _UNIQUE_SHAPES
        if table_name in _AFFECTED_TABLES
    }
    | {
        (table_name, constraint_name, "f")
        for constraint_name, table_name, _columns, _ref_table, _ref_columns in _FK_SHAPES
    }
    | {
        (table_name, constraint_name, "c")
        for table_name, constraint_name, _definition in _CHECK_DEFINITION_MANIFEST
    }
    | {
        ("source_sync_operations", "pk_source_sync_operations", "p"),
        ("source_health_states", "pk_source_health_states", "p"),
        ("source_health_alert_outbox", "pk_source_health_alert_outbox", "p"),
    }
)

_INDEX_DEFINITION_MANIFEST: tuple[tuple[str, str], ...] = (
    (
        "uq_source_sync_runs_tenant_job_run_v2",
        "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_job_run_v2 ON "
        "dayu_platform.source_sync_runs USING btree (tenant_id, job_run_id) "
        "WHERE (job_run_id IS NOT NULL)",
    ),
    (
        "uq_source_sync_runs_tenant_job_attempt_v2",
        "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_job_attempt_v2 ON "
        "dayu_platform.source_sync_runs USING btree (tenant_id, job_attempt_id) "
        "WHERE (job_attempt_id IS NOT NULL)",
    ),
    (
        "uq_source_health_snapshots_tenant_subscription_version_v2",
        "CREATE UNIQUE INDEX uq_source_health_snapshots_tenant_subscription_version_v2 ON "
        "dayu_platform.source_health_snapshots USING btree "
        "(tenant_id, subscription_id, health_state_version) "
        "WHERE (health_state_version IS NOT NULL)",
    ),
    (
        "uq_source_subscriptions_tenant_wide",
        "CREATE UNIQUE INDEX uq_source_subscriptions_tenant_wide ON "
        "dayu_platform.source_subscriptions USING btree (tenant_id, source_definition_id) "
        "WHERE ((company_id IS NULL) AND (security_id IS NULL))",
    ),
    (
        "uq_source_subscriptions_company",
        "CREATE UNIQUE INDEX uq_source_subscriptions_company ON "
        "dayu_platform.source_subscriptions USING btree "
        "(tenant_id, source_definition_id, company_id) WHERE (company_id IS NOT NULL)",
    ),
    (
        "uq_source_subscriptions_security",
        "CREATE UNIQUE INDEX uq_source_subscriptions_security ON "
        "dayu_platform.source_subscriptions USING btree "
        "(tenant_id, source_definition_id, security_id) WHERE (security_id IS NOT NULL)",
    ),
    (
        "ix_source_sync_operations_tenant_state_updated",
        "CREATE INDEX ix_source_sync_operations_tenant_state_updated ON "
        "dayu_platform.source_sync_operations USING btree (tenant_id, state, updated_at, id)",
    ),
    (
        "ix_source_health_states_tenant_status_observed",
        "CREATE INDEX ix_source_health_states_tenant_status_observed ON "
        "dayu_platform.source_health_states USING btree (tenant_id, status, observed_at, id)",
    ),
    (
        "ix_source_health_alert_outbox_tenant_created",
        "CREATE INDEX ix_source_health_alert_outbox_tenant_created ON "
        "dayu_platform.source_health_alert_outbox USING btree (tenant_id, created_at, id)",
    ),
    (
        "ix_source_health_alert_outbox_tenant_sub_created",
        "CREATE INDEX ix_source_health_alert_outbox_tenant_sub_created ON "
        "dayu_platform.source_health_alert_outbox USING btree "
        "(tenant_id, subscription_id, created_at, id)",
    ),
)

_AFFECTED_INDEX_DEFINITION_MANIFEST: frozenset[tuple[str, str, str]] = frozenset(
    {
        (
            "source_sync_runs",
            "ix_source_sync_runs_tenant_subscription_started",
            "CREATE INDEX ix_source_sync_runs_tenant_subscription_started ON "
            "dayu_platform.source_sync_runs USING btree "
            "(tenant_id, subscription_id, started_at DESC)",
        ),
        (
            "source_sync_runs",
            "pk_source_sync_runs",
            "CREATE UNIQUE INDEX pk_source_sync_runs ON "
            "dayu_platform.source_sync_runs USING btree (id)",
        ),
        (
            "source_sync_runs",
            "uq_source_sync_runs_tenant_id_id",
            "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_id_id ON "
            "dayu_platform.source_sync_runs USING btree (tenant_id, id)",
        ),
        (
            "source_sync_runs",
            "uq_source_sync_runs_tenant_id_idempotency_key",
            "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_id_idempotency_key ON "
            "dayu_platform.source_sync_runs USING btree (tenant_id, idempotency_key)",
        ),
        (
            "source_sync_runs",
            "uq_source_sync_runs_tenant_job_attempt_v2",
            "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_job_attempt_v2 ON "
            "dayu_platform.source_sync_runs USING btree (tenant_id, job_attempt_id) "
            "WHERE (job_attempt_id IS NOT NULL)",
        ),
        (
            "source_sync_runs",
            "uq_source_sync_runs_tenant_job_run_v2",
            "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_job_run_v2 ON "
            "dayu_platform.source_sync_runs USING btree (tenant_id, job_run_id) "
            "WHERE (job_run_id IS NOT NULL)",
        ),
        (
            "source_sync_runs",
            "uq_source_sync_runs_tenant_sub_job_attempt_id_v2",
            "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_sub_job_attempt_id_v2 ON "
            "dayu_platform.source_sync_runs USING btree "
            "(tenant_id, subscription_id, job_run_id, job_attempt_id, id)",
        ),
        (
            "source_sync_runs",
            "uq_source_sync_runs_tenant_subscription_id_v2",
            "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_subscription_id_v2 ON "
            "dayu_platform.source_sync_runs USING btree (tenant_id, subscription_id, id)",
        ),
        (
            "source_sync_runs",
            "uq_source_sync_runs_tenant_subscription_job_id_v2",
            "CREATE UNIQUE INDEX uq_source_sync_runs_tenant_subscription_job_id_v2 ON "
            "dayu_platform.source_sync_runs USING btree "
            "(tenant_id, subscription_id, job_run_id, id)",
        ),
        (
            "source_health_snapshots",
            "ix_source_health_snapshots_tenant_subscription_observed",
            "CREATE INDEX ix_source_health_snapshots_tenant_subscription_observed ON "
            "dayu_platform.source_health_snapshots USING btree "
            "(tenant_id, subscription_id, observed_at DESC)",
        ),
        (
            "source_health_snapshots",
            "pk_source_health_snapshots",
            "CREATE UNIQUE INDEX pk_source_health_snapshots ON "
            "dayu_platform.source_health_snapshots USING btree (id)",
        ),
        (
            "source_health_snapshots",
            "uq_source_health_snapshots_tenant_id_id",
            "CREATE UNIQUE INDEX uq_source_health_snapshots_tenant_id_id ON "
            "dayu_platform.source_health_snapshots USING btree (tenant_id, id)",
        ),
        (
            "source_health_snapshots",
            "uq_source_health_snapshots_tenant_sub_run_version_id_v2",
            "CREATE UNIQUE INDEX uq_source_health_snapshots_tenant_sub_run_version_id_v2 ON "
            "dayu_platform.source_health_snapshots USING btree "
            "(tenant_id, subscription_id, sync_run_id, health_state_version, id)",
        ),
        (
            "source_health_snapshots",
            "uq_source_health_snapshots_tenant_subscription_id_v2",
            "CREATE UNIQUE INDEX uq_source_health_snapshots_tenant_subscription_id_v2 ON "
            "dayu_platform.source_health_snapshots USING btree "
            "(tenant_id, subscription_id, id)",
        ),
        (
            "source_health_snapshots",
            "uq_source_health_snapshots_tenant_subscription_version_v2",
            "CREATE UNIQUE INDEX "
            "uq_source_health_snapshots_tenant_subscription_version_v2 ON "
            "dayu_platform.source_health_snapshots USING btree "
            "(tenant_id, subscription_id, health_state_version) "
            "WHERE (health_state_version IS NOT NULL)",
        ),
        (
            "source_sync_operations",
            "ix_source_sync_operations_tenant_state_updated",
            "CREATE INDEX ix_source_sync_operations_tenant_state_updated ON "
            "dayu_platform.source_sync_operations USING btree "
            "(tenant_id, state, updated_at, id)",
        ),
        (
            "source_sync_operations",
            "pk_source_sync_operations",
            "CREATE UNIQUE INDEX pk_source_sync_operations ON "
            "dayu_platform.source_sync_operations USING btree (id)",
        ),
        (
            "source_sync_operations",
            "uq_source_sync_operations_tenant_id",
            "CREATE UNIQUE INDEX uq_source_sync_operations_tenant_id ON "
            "dayu_platform.source_sync_operations USING btree (tenant_id, id)",
        ),
        (
            "source_sync_operations",
            "uq_source_sync_operations_tenant_job_run",
            "CREATE UNIQUE INDEX uq_source_sync_operations_tenant_job_run ON "
            "dayu_platform.source_sync_operations USING btree (tenant_id, job_run_id)",
        ),
        (
            "source_health_states",
            "ix_source_health_states_tenant_status_observed",
            "CREATE INDEX ix_source_health_states_tenant_status_observed ON "
            "dayu_platform.source_health_states USING btree "
            "(tenant_id, status, observed_at, id)",
        ),
        (
            "source_health_states",
            "pk_source_health_states",
            "CREATE UNIQUE INDEX pk_source_health_states ON "
            "dayu_platform.source_health_states USING btree (id)",
        ),
        (
            "source_health_states",
            "uq_source_health_states_tenant_id",
            "CREATE UNIQUE INDEX uq_source_health_states_tenant_id ON "
            "dayu_platform.source_health_states USING btree (tenant_id, id)",
        ),
        (
            "source_health_states",
            "uq_source_health_states_tenant_subscription",
            "CREATE UNIQUE INDEX uq_source_health_states_tenant_subscription ON "
            "dayu_platform.source_health_states USING btree (tenant_id, subscription_id)",
        ),
        (
            "source_health_alert_outbox",
            "ix_source_health_alert_outbox_tenant_created",
            "CREATE INDEX ix_source_health_alert_outbox_tenant_created ON "
            "dayu_platform.source_health_alert_outbox USING btree "
            "(tenant_id, created_at, id)",
        ),
        (
            "source_health_alert_outbox",
            "ix_source_health_alert_outbox_tenant_sub_created",
            "CREATE INDEX ix_source_health_alert_outbox_tenant_sub_created ON "
            "dayu_platform.source_health_alert_outbox USING btree "
            "(tenant_id, subscription_id, created_at, id)",
        ),
        (
            "source_health_alert_outbox",
            "pk_source_health_alert_outbox",
            "CREATE UNIQUE INDEX pk_source_health_alert_outbox ON "
            "dayu_platform.source_health_alert_outbox USING btree (id)",
        ),
        (
            "source_health_alert_outbox",
            "uq_source_health_alert_outbox_tenant_dedupe",
            "CREATE UNIQUE INDEX uq_source_health_alert_outbox_tenant_dedupe ON "
            "dayu_platform.source_health_alert_outbox USING btree (tenant_id, dedupe_key)",
        ),
        (
            "source_health_alert_outbox",
            "uq_source_health_alert_outbox_tenant_id",
            "CREATE UNIQUE INDEX uq_source_health_alert_outbox_tenant_id ON "
            "dayu_platform.source_health_alert_outbox USING btree (tenant_id, id)",
        ),
    }
)


def _qualified_literals(values: Iterable[str]) -> str:
    """把闭合集合转换为只含受控 manifest 名的 SQL literal 列表。

    Args:
        values: 受控 object-name manifest。

    Returns:
        可放入 ``IN (...)`` 的单引号列表。

    Raises:
        无。
    """

    return ", ".join(f"'{value}'" for value in values)


def _fetch_scalar_int(bind: Connection, statement: str) -> int:
    """执行 catalog 标量查询并返回整数。

    Args:
        bind: 当前 Alembic 连接。
        statement: 不含外部输入的只读 catalog SQL。

    Returns:
        查询整数结果；数据库返回 NULL 时为零。

    Raises:
        RuntimeError: 返回值无法转换为整数时抛出。
    """

    value = bind.execute(text(statement)).scalar()
    return 0 if value is None else int(value)


def _assert_count(actual: int, expected: int, message: str) -> None:
    """断言 catalog 数量精确匹配。

    Args:
        actual: 实际数量。
        expected: 期望数量。
        message: fail-closed 稳定错误消息。

    Returns:
        无。

    Raises:
        RuntimeError: 数量不匹配时抛出。
    """

    if actual != expected:
        raise RuntimeError(message)


def _baseline_subscription_indexes_are_exact(bind: Connection) -> bool:
    """检查三个 0001 subscription partial unique index 的 exact shape。

    Args:
        bind: 当前 Alembic 连接。

    Returns:
        三个 index 全部处于 0001 exact shape 时为 ``True``。

    Raises:
        无。
    """

    rows = bind.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes "
            f"WHERE schemaname = '{_SCHEMA}' AND indexname IN "
            f"({_qualified_literals(_REPLACED_BASELINE_INDEX_NAMES)}) "
            "ORDER BY indexname"
        )
    ).fetchall()
    expected = {
        "uq_source_subscriptions_tenant_wide": (
            "CREATE UNIQUE INDEX uq_source_subscriptions_tenant_wide ON "
            "dayu_platform.source_subscriptions USING btree (tenant_id) "
            "WHERE ((company_id IS NULL) AND (security_id IS NULL))"
        ),
        "uq_source_subscriptions_company": (
            "CREATE UNIQUE INDEX uq_source_subscriptions_company ON "
            "dayu_platform.source_subscriptions USING btree (tenant_id, company_id) "
            "WHERE (company_id IS NOT NULL)"
        ),
        "uq_source_subscriptions_security": (
            "CREATE UNIQUE INDEX uq_source_subscriptions_security ON "
            "dayu_platform.source_subscriptions USING btree (tenant_id, security_id) "
            "WHERE (security_id IS NOT NULL)"
        ),
    }
    return {str(row[0]): str(row[1]) for row in rows} == expected


def _expected_check_catalog(bind: Connection) -> set[tuple[str, str, str, str]]:
    """用 PostgreSQL 自身 deparser 生成九个 CHECK 的 exact expected catalog。

    临时表只承载 single production manifest 的原始表达式；返回值补回每个
    constraint 的真实 owner table，因此 self-check 同时锁定 table、name、
    ``contype`` 与 ``pg_get_constraintdef``，且不猜测 PostgreSQL 括号和 cast。

    Args:
        bind: 当前 Alembic 连接。

    Returns:
        九个 ``(table, name, contype, definition)`` exact tuples。

    Raises:
        SQLAlchemyError: 临时 oracle DDL 或 catalog 查询失败时向外传播。
        RuntimeError: 临时 oracle 未生成 exact 九个 CHECK 时抛出。
    """

    oracle_table = "_0005_expected_check_oracle"
    oracle_prefix = "oracle_"
    constraint_sql = ", ".join(
        f"CONSTRAINT {oracle_prefix}{constraint_name} CHECK ({definition})"
        for _table_name, constraint_name, definition in _CHECK_DEFINITION_MANIFEST
    )
    bind.execute(
        text(
            f"CREATE TEMP TABLE {oracle_table} ("
            "job_run_id UUID, job_attempt_id UUID, payload_sha256 TEXT, outcome TEXT, "
            "retry_recommended BOOLEAN, records_downloaded INTEGER, records_reused INTEGER, "
            "records_ignored INTEGER, records_failed INTEGER, records_discovered INTEGER, "
            "records_ingested INTEGER, latest_source_observed_date DATE, receipt_json JSONB, "
            "receipt_sha256 TEXT, result_json JSONB, result_sha256 TEXT, status TEXT, "
            "finished_at TIMESTAMPTZ, safe_error_code TEXT, consecutive_failures INTEGER, "
            "health_state_version INTEGER, sync_run_id UUID, latency_ms INTEGER, generation INTEGER, "
            "owner_binding_disposition TEXT, state TEXT, terminal_source_sync_run_id UUID, "
            "execution_snapshot_sha256 TEXT, execution_snapshot_json JSONB, version INTEGER, "
            "alert_kind TEXT, target_status TEXT, dedupe_key TEXT, event_sha256 TEXT, "
            f"event_json JSONB, {constraint_sql}) ON COMMIT DROP"
        )
    )
    rows = bind.execute(
        text(
            "SELECT con.conname, con.contype, pg_get_constraintdef(con.oid) "
            "FROM pg_constraint con "
            f"WHERE con.conrelid = 'pg_temp.{oracle_table}'::regclass"
        )
    ).fetchall()
    bind.execute(text(f"DROP TABLE pg_temp.{oracle_table}"))
    table_by_name = {
        constraint_name: table_name
        for table_name, constraint_name, _definition in _CHECK_DEFINITION_MANIFEST
    }
    expected = {
        (
            table_by_name[str(row[0]).removeprefix(oracle_prefix)],
            str(row[0]).removeprefix(oracle_prefix),
            str(row[1]),
            str(row[2]),
        )
        for row in rows
    }
    if len(expected) != len(_CHECK_DEFINITION_MANIFEST):
        raise RuntimeError("0005 catalog self-check：CHECK expected oracle 漂移")
    return expected


def _assert_baseline_security_exact(bind: Connection) -> None:
    """逐对象验证 0004 baseline 的 RLS、policy 与 ACL 身份集合。

    Args:
        bind: 当前 Alembic 连接。

    Returns:
        无。

    Raises:
        RuntimeError: 任一 RLS flag、policy expression 或权限元组漂移时抛出。
    """

    rls_rows = bind.execute(
        text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN "
            f"({_qualified_literals(_BASELINE_TABLES)}) AND c.relkind = 'r'"
        )
    ).fetchall()
    actual_rls = {
        (str(row[0]), bool(row[1]), bool(row[2]))
        for row in rls_rows
    }
    expected_rls = {
        (table_name, table_name in _BASELINE_PRIVATE_TABLES, table_name in _BASELINE_PRIVATE_TABLES)
        for table_name in _BASELINE_TABLES
    }
    if actual_rls != expected_rls:
        raise RuntimeError("0005 upgrade 拒绝：baseline RLS/FORCE identity 漂移")

    policy_rows = bind.execute(
        text(
            "SELECT tablename, policyname, cmd, roles::text, qual, with_check "
            "FROM pg_policies "
            f"WHERE schemaname = '{_SCHEMA}' AND tablename IN "
            f"({_qualified_literals(_BASELINE_TABLES)})"
        )
    ).fetchall()
    actual_policies = {
        tuple(str(value) for value in row)
        for row in policy_rows
    }
    if actual_policies != _BASELINE_POLICY_MANIFEST:
        raise RuntimeError("0005 upgrade 拒绝：baseline tenant policy exact manifest 漂移")

    table_acl_rows = bind.execute(
        text(
            "SELECT c.relname, CASE WHEN acl.grantee = 0 THEN 'PUBLIC' "
            "ELSE grantee_role.rolname END, acl.privilege_type, acl.is_grantable "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "CROSS JOIN LATERAL aclexplode(c.relacl) acl "
            "LEFT JOIN pg_roles grantee_role ON grantee_role.oid = acl.grantee "
            f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN "
            f"({_qualified_literals(_BASELINE_TABLES)})"
        )
    ).fetchall()
    actual_table_acl = {
        (str(row[0]), str(row[1]), str(row[2]), bool(row[3]))
        for row in table_acl_rows
    }
    owner_name = str(bind.execute(text("SELECT current_user")).scalar_one())
    expected_table_acl = {
        (table_name, PLATFORM_APP_ROLE, privilege, grantable)
        for table_name, privilege, grantable in _BASELINE_APP_TABLE_ACL_MANIFEST
    } | {
        (table_name, PLATFORM_AUDIT_ROLE, "SELECT", False)
        for table_name in _BASELINE_TABLES
    } | {
        (table_name, owner_name, privilege, False)
        for table_name in _BASELINE_TABLES
        for privilege in (
            "DELETE",
            "INSERT",
            "REFERENCES",
            "SELECT",
            "TRIGGER",
            "TRUNCATE",
            "UPDATE",
        )
    }
    if actual_table_acl != expected_table_acl:
        raise RuntimeError("0005 upgrade 拒绝：baseline app table ACL exact manifest 漂移")

    column_acl_rows = bind.execute(
        text(
            "SELECT c.relname, a.attname, CASE WHEN acl.grantee = 0 THEN 'PUBLIC' "
            "ELSE grantee_role.rolname END, acl.privilege_type, acl.is_grantable "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
            "CROSS JOIN LATERAL aclexplode(a.attacl) acl "
            "LEFT JOIN pg_roles grantee_role ON grantee_role.oid = acl.grantee "
            f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN "
            f"({_qualified_literals(_BASELINE_TABLES)})"
        )
    ).fetchall()
    actual_column_acl = {
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]), bool(row[4]))
        for row in column_acl_rows
    }
    # ``attacl``只存显式 column grant；table owner 的隐式权限不会逐列展开。
    # 因此 exact set 只包含0003/0004显式授予 app 的37个 UPDATE tuple。
    expected_column_acl = {
        (table_name, column_name, PLATFORM_APP_ROLE, privilege, grantable)
        for table_name, column_name, privilege, grantable
        in _BASELINE_APP_COLUMN_UPDATE_MANIFEST
    }
    if actual_column_acl != expected_column_acl:
        raise RuntimeError("0005 upgrade 拒绝：baseline column ACL exact manifest 漂移")


def _preflight_upgrade() -> None:
    """在任何 0005 DDL 前验证 0004 baseline、对象缺席与 legacy 数据。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: baseline/object/data 形状漂移时 fail closed。
    """

    bind = op.get_bind()
    op.execute(
        f"LOCK TABLE {_SCHEMA}.job_attempts, {_SCHEMA}.source_subscriptions, "
        f"{_SCHEMA}.source_sync_runs, {_SCHEMA}.source_health_snapshots "
        "IN ACCESS EXCLUSIVE MODE"
    )
    table_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema = '{_SCHEMA}'",
    )
    _assert_count(table_count, 24, "0005 upgrade 拒绝：baseline table count 不是 24")
    revision_value = bind.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if revision_value != down_revision:
        raise RuntimeError("0005 upgrade 拒绝：Alembic baseline 不是 0004_durable_schedules")
    present = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema = '{_SCHEMA}' AND table_name IN "
        f"({_qualified_literals(_BASELINE_TABLES)})",
    )
    _assert_count(present, 24, "0005 upgrade 拒绝：baseline owner table 集合漂移")
    new_table_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema = '{_SCHEMA}' AND table_name IN "
        f"({_qualified_literals(_NEW_TABLES)})",
    )
    _assert_count(new_table_count, 0, "0005 upgrade 拒绝：new table 已存在")
    if not _baseline_subscription_indexes_are_exact(bind):
        raise RuntimeError("0005 upgrade 拒绝：三个 baseline subscription index 不是 0001 exact shape")

    object_names = _qualified_literals(_NEW_0005_OBJECT_NAMES)
    collision_count = _fetch_scalar_int(
        bind,
        "SELECT (SELECT count(*) FROM pg_constraint con JOIN pg_namespace n "
        "ON n.oid = con.connamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND con.conname IN ({object_names})) "
        "+ (SELECT count(*) FROM pg_class c JOIN pg_namespace n "
        "ON n.oid = c.relnamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN ({object_names})) "
        "+ (SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
        "ON n.oid = p.pronamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND p.proname IN ({object_names})) "
        "+ (SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND NOT t.tgisinternal "
        f"AND t.tgname IN ({object_names}))",
    )
    _assert_count(collision_count, 0, "0005 upgrade 拒绝：new object name 已存在")

    unexpected_columns = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM information_schema.columns "
        f"WHERE table_schema = '{_SCHEMA}' AND "
        f"((table_name = 'source_sync_runs' AND column_name IN "
        f"({_qualified_literals(_RUN_COLUMNS)})) OR "
        "(table_name = 'source_health_snapshots' AND "
        "column_name = 'health_state_version'))",
    )
    _assert_count(unexpected_columns, 0, "0005 upgrade 拒绝：target column 已存在")
    weak_fk_shape = bind.execute(
        text(
            "SELECT con.contype, rel.relname, ref.relname, con.confdeltype, "
            "array_to_string(ARRAY(SELECT a.attname FROM unnest(con.conkey) "
            "WITH ORDINALITY AS k(attnum, ord) JOIN pg_attribute a "
            "ON a.attrelid = con.conrelid AND a.attnum = k.attnum ORDER BY k.ord), ','), "
            "array_to_string(ARRAY(SELECT a.attname FROM unnest(con.confkey) "
            "WITH ORDINALITY AS k(attnum, ord) JOIN pg_attribute a "
            "ON a.attrelid = con.confrelid AND a.attnum = k.attnum ORDER BY k.ord), ',') "
            "FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_class ref ON ref.oid = con.confrelid "
            "JOIN pg_namespace n ON n.oid = con.connamespace "
            f"WHERE n.nspname = '{_SCHEMA}' AND "
            "con.conname = 'fk_source_health_snapshots_tenant_sync_run'"
        )
    ).fetchall()
    if weak_fk_shape != [
        ("f", "source_health_snapshots", "source_sync_runs", "r", "tenant_id,sync_run_id", "tenant_id,id")
    ]:
        raise RuntimeError("0005 upgrade 拒绝：baseline weak snapshot FK shape 漂移")

    owner_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_roles owner_role ON owner_role.oid = c.relowner "
        f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN "
        f"({_qualified_literals(_BASELINE_TABLES)}) "
        "AND owner_role.rolname = current_user",
    )
    _assert_count(owner_count, 24, "0005 upgrade 拒绝：baseline table owner 漂移")
    _assert_baseline_security_exact(bind)

    dependency_count = _fetch_scalar_int(
        bind,
        "WITH targets AS ("
        "SELECT c.oid, 'pg_class'::regclass AS classid FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN "
        f"({_qualified_literals(_REPLACED_BASELINE_INDEX_NAMES)}) "
        "UNION ALL SELECT con.oid, 'pg_constraint'::regclass FROM pg_constraint con "
        "JOIN pg_namespace n ON n.oid = con.connamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND "
        "con.conname = 'fk_source_health_snapshots_tenant_sync_run') "
        "SELECT count(*) FROM pg_depend d JOIN targets t "
        "ON d.refclassid = t.classid AND d.refobjid = t.oid WHERE d.deptype = 'n'",
    )
    _assert_count(dependency_count, 0, "0005 upgrade 拒绝：target object 存在外部 dependency")

    mismatch_count = _fetch_scalar_int(
        bind,
        f"SELECT count(*) FROM {_SCHEMA}.source_health_snapshots s "
        f"JOIN {_SCHEMA}.source_sync_runs r ON r.tenant_id = s.tenant_id "
        "AND r.id = s.sync_run_id "
        "WHERE s.sync_run_id IS NOT NULL AND s.subscription_id <> r.subscription_id",
    )
    _assert_count(mismatch_count, 0, "0005 upgrade 拒绝：legacy snapshot/run subscription lineage 漂移")
    invalid_health_count = _fetch_scalar_int(
        bind,
        f"SELECT count(*) FROM {_SCHEMA}.source_health_snapshots "
        "WHERE NOT ((status = 'healthy' AND consecutive_failures = 0 "
        "AND safe_error_code IS NULL) OR "
        "(status IN ('degraded', 'failing', 'disabled') "
        "AND consecutive_failures > 0 AND safe_error_code IS NOT NULL "
        f"AND safe_error_code IN ({_HEALTH_ERROR_SQL})))",
    )
    _assert_count(invalid_health_count, 0, "0005 upgrade 拒绝：legacy health shape 不在 closed contract")


def _add_parent_attempt_unique() -> None:
    """先创建 run/operation child FK 共同依赖的 attempts parent key。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 数据库拒绝创建 parent unique constraint 时向外传播。
    """

    op.execute(
        f"ALTER TABLE {_SCHEMA}.job_attempts ADD CONSTRAINT "
        "uq_job_attempts_tenant_job_run_id_v2 UNIQUE (tenant_id, job_run_id, id)"
    )


def _extend_source_sync_runs() -> None:
    """扩展 source run durable columns、checks、indexes 与 FK parent keys。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 任一列、约束、索引或 FK DDL 失败时向外传播。
    """

    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_sync_runs "
        "ADD COLUMN job_run_id UUID, "
        "ADD COLUMN job_attempt_id UUID, "
        "ADD COLUMN payload_sha256 TEXT, "
        "ADD COLUMN outcome TEXT, "
        "ADD COLUMN retry_recommended BOOLEAN, "
        "ADD COLUMN records_downloaded INTEGER, "
        "ADD COLUMN records_reused INTEGER, "
        "ADD COLUMN records_ignored INTEGER, "
        "ADD COLUMN records_failed INTEGER, "
        "ADD COLUMN latest_source_observed_date DATE, "
        "ADD COLUMN receipt_json JSONB, "
        "ADD COLUMN receipt_sha256 TEXT, "
        "ADD COLUMN result_json JSONB, "
        "ADD COLUMN result_sha256 TEXT"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_sync_runs ADD CONSTRAINT "
        "ck_source_sync_runs_v1_core_presence "
        f"CHECK ({_CHECK_SOURCE_SYNC_RUNS_V1_CORE_PRESENCE})"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_sync_runs ADD CONSTRAINT "
        f"ck_source_sync_runs_v1_counts CHECK ({_CHECK_SOURCE_SYNC_RUNS_V1_COUNTS})"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_sync_runs ADD CONSTRAINT "
        "ck_source_sync_runs_v1_outcome_shape "
        f"CHECK ({_CHECK_SOURCE_SYNC_RUNS_V1_OUTCOME_SHAPE})"
    )
    op.execute(
        f"CREATE UNIQUE INDEX uq_source_sync_runs_tenant_job_run_v2 ON {_SCHEMA}.source_sync_runs "
        "(tenant_id, job_run_id) WHERE job_run_id IS NOT NULL"
    )
    op.execute(
        f"CREATE UNIQUE INDEX uq_source_sync_runs_tenant_job_attempt_v2 ON {_SCHEMA}.source_sync_runs "
        "(tenant_id, job_attempt_id) WHERE job_attempt_id IS NOT NULL"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_sync_runs ADD CONSTRAINT "
        "uq_source_sync_runs_tenant_subscription_id_v2 UNIQUE (tenant_id, subscription_id, id), "
        "ADD CONSTRAINT uq_source_sync_runs_tenant_subscription_job_id_v2 "
        "UNIQUE (tenant_id, subscription_id, job_run_id, id), "
        "ADD CONSTRAINT uq_source_sync_runs_tenant_sub_job_attempt_id_v2 "
        "UNIQUE (tenant_id, subscription_id, job_run_id, job_attempt_id, id)"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_sync_runs ADD CONSTRAINT "
        "fk_source_sync_runs_tenant_job_attempt_v2 "
        f"FOREIGN KEY (tenant_id, job_run_id, job_attempt_id) REFERENCES {_SCHEMA}.job_attempts "
        "(tenant_id, job_run_id, id) ON DELETE RESTRICT NOT VALID"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_sync_runs VALIDATE CONSTRAINT "
        "fk_source_sync_runs_tenant_job_attempt_v2"
    )


def _extend_source_health_snapshots() -> None:
    """扩展 snapshot version，并无保护空窗地替换 strong run FK。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 任一 snapshot DDL 或 FK validation 失败时向外传播。
    """

    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_health_snapshots "
        "ADD COLUMN health_state_version INTEGER"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_health_snapshots ADD CONSTRAINT "
        "uq_source_health_snapshots_tenant_subscription_id_v2 "
        "UNIQUE (tenant_id, subscription_id, id), "
        "ADD CONSTRAINT uq_source_health_snapshots_tenant_sub_run_version_id_v2 "
        "UNIQUE (tenant_id, subscription_id, sync_run_id, health_state_version, id), "
        "ADD CONSTRAINT ck_source_health_snapshots_v2_shape "
        f"CHECK ({_CHECK_SOURCE_HEALTH_SNAPSHOTS_V2_SHAPE})"
    )
    op.execute(
        f"CREATE UNIQUE INDEX uq_source_health_snapshots_tenant_subscription_version_v2 "
        f"ON {_SCHEMA}.source_health_snapshots "
        "(tenant_id, subscription_id, health_state_version) "
        "WHERE health_state_version IS NOT NULL"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_health_snapshots ADD CONSTRAINT "
        "fk_source_health_snapshots_tenant_subscription_run_v2 "
        f"FOREIGN KEY (tenant_id, subscription_id, sync_run_id) REFERENCES {_SCHEMA}.source_sync_runs "
        "(tenant_id, subscription_id, id) ON DELETE RESTRICT NOT VALID"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_health_snapshots VALIDATE CONSTRAINT "
        "fk_source_health_snapshots_tenant_subscription_run_v2"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_health_snapshots DROP CONSTRAINT "
        "fk_source_health_snapshots_tenant_sync_run"
    )


def _replace_subscription_indexes_for_upgrade() -> None:
    """把三个 target unique identity 扩为 source-definition scoped。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 删除或创建 subscription index 失败时向外传播。
    """

    for index_name in _REPLACED_BASELINE_INDEX_NAMES:
        op.execute(f"DROP INDEX {_SCHEMA}.{index_name}")
    op.execute(
        f"CREATE UNIQUE INDEX uq_source_subscriptions_tenant_wide ON {_SCHEMA}.source_subscriptions "
        "(tenant_id, source_definition_id) WHERE company_id IS NULL AND security_id IS NULL"
    )
    op.execute(
        f"CREATE UNIQUE INDEX uq_source_subscriptions_company ON {_SCHEMA}.source_subscriptions "
        "(tenant_id, source_definition_id, company_id) WHERE company_id IS NOT NULL"
    )
    op.execute(
        f"CREATE UNIQUE INDEX uq_source_subscriptions_security ON {_SCHEMA}.source_subscriptions "
        "(tenant_id, source_definition_id, security_id) WHERE security_id IS NOT NULL"
    )


def _create_source_sync_operations() -> None:
    """创建 operation owner/generation fence 表与 exact lineage。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 创建 operation 表、约束或索引失败时向外传播。
    """

    op.execute(
        f"""
        CREATE TABLE {_SCHEMA}.source_sync_operations (
            id UUID CONSTRAINT pk_source_sync_operations PRIMARY KEY,
            tenant_id UUID NOT NULL,
            job_run_id UUID NOT NULL,
            subscription_id UUID NOT NULL,
            owner_attempt_id UUID NOT NULL,
            state TEXT NOT NULL,
            generation INTEGER NOT NULL,
            owner_binding_disposition TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            execution_snapshot_sha256 TEXT NOT NULL,
            execution_snapshot_json JSONB NOT NULL,
            acquired_at TIMESTAMPTZ NOT NULL,
            terminal_source_sync_run_id UUID NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT uq_source_sync_operations_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_source_sync_operations_tenant_job_run UNIQUE (tenant_id, job_run_id),
            CONSTRAINT fk_source_sync_operations_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES {_SCHEMA}.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_sync_operations_tenant_job_attempt
                FOREIGN KEY (tenant_id, job_run_id, owner_attempt_id)
                REFERENCES {_SCHEMA}.job_attempts (tenant_id, job_run_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_sync_operations_tenant_subscription
                FOREIGN KEY (tenant_id, subscription_id)
                REFERENCES {_SCHEMA}.source_subscriptions (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_sync_operations_terminal_run
                FOREIGN KEY (tenant_id, subscription_id, job_run_id,
                             owner_attempt_id, terminal_source_sync_run_id)
                REFERENCES {_SCHEMA}.source_sync_runs
                    (tenant_id, subscription_id, job_run_id, job_attempt_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_source_sync_operations_state_shape CHECK (
                {_CHECK_SOURCE_SYNC_OPERATIONS_STATE_SHAPE}
            ),
            CONSTRAINT ck_source_sync_operations_hashes CHECK (
                {_CHECK_SOURCE_SYNC_OPERATIONS_HASHES}
            ),
            CONSTRAINT ck_source_sync_operations_snapshot_object CHECK (
                {_CHECK_SOURCE_SYNC_OPERATIONS_SNAPSHOT_OBJECT}
            )
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_source_sync_operations_tenant_state_updated ON {_SCHEMA}.source_sync_operations "
        "(tenant_id, state, updated_at, id)"
    )


def _create_source_health_states() -> None:
    """创建每订阅唯一 mutable health head 表。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 创建 health state 表、约束或索引失败时向外传播。
    """

    op.execute(
        f"""
        CREATE TABLE {_SCHEMA}.source_health_states (
            id UUID CONSTRAINT pk_source_health_states PRIMARY KEY,
            tenant_id UUID NOT NULL,
            subscription_id UUID NOT NULL,
            last_source_sync_run_id UUID NOT NULL,
            status TEXT NOT NULL,
            consecutive_failures INTEGER NOT NULL,
            safe_error_code TEXT NULL,
            version INTEGER NOT NULL,
            observed_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT uq_source_health_states_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_source_health_states_tenant_subscription UNIQUE (tenant_id, subscription_id),
            CONSTRAINT fk_source_health_states_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES {_SCHEMA}.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_health_states_last_run
                FOREIGN KEY (tenant_id, subscription_id, last_source_sync_run_id)
                REFERENCES {_SCHEMA}.source_sync_runs (tenant_id, subscription_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_source_health_states_shape CHECK (
                {_CHECK_SOURCE_HEALTH_STATES_SHAPE}
            )
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_source_health_states_tenant_status_observed ON {_SCHEMA}.source_health_states "
        "(tenant_id, status, observed_at, id)"
    )


def _create_source_health_alert_outbox() -> None:
    """创建 append-only semantic alert outbox 及强 snapshot lineage。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 创建 outbox 表、约束或索引失败时向外传播。
    """

    op.execute(
        f"""
        CREATE TABLE {_SCHEMA}.source_health_alert_outbox (
            id UUID CONSTRAINT pk_source_health_alert_outbox PRIMARY KEY,
            tenant_id UUID NOT NULL,
            subscription_id UUID NOT NULL,
            source_sync_run_id UUID NOT NULL,
            health_snapshot_id UUID NOT NULL,
            health_state_version INTEGER NOT NULL,
            alert_kind TEXT NOT NULL,
            target_status TEXT NOT NULL,
            safe_error_code TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            event_json JSONB NOT NULL,
            event_sha256 TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_source_health_alert_outbox_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_source_health_alert_outbox_tenant_dedupe UNIQUE (tenant_id, dedupe_key),
            CONSTRAINT fk_source_health_alert_outbox_tenant_id_organizations
                FOREIGN KEY (tenant_id) REFERENCES {_SCHEMA}.organizations (id) ON DELETE RESTRICT,
            CONSTRAINT fk_source_health_alert_outbox_run
                FOREIGN KEY (tenant_id, subscription_id, source_sync_run_id)
                REFERENCES {_SCHEMA}.source_sync_runs (tenant_id, subscription_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_source_health_alert_outbox_snapshot
                FOREIGN KEY (tenant_id, subscription_id, source_sync_run_id,
                             health_state_version, health_snapshot_id)
                REFERENCES {_SCHEMA}.source_health_snapshots
                    (tenant_id, subscription_id, sync_run_id, health_state_version, id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_source_health_alert_outbox_shape CHECK (
                {_CHECK_SOURCE_HEALTH_ALERT_OUTBOX_SHAPE}
            )
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_source_health_alert_outbox_tenant_created "
        f"ON {_SCHEMA}.source_health_alert_outbox (tenant_id, created_at, id)"
    )
    op.execute(
        f"CREATE INDEX ix_source_health_alert_outbox_tenant_sub_created "
        f"ON {_SCHEMA}.source_health_alert_outbox "
        "(tenant_id, subscription_id, created_at, id)"
    )


def _create_guard_functions() -> None:
    """以 single manifest 创建 exact 11 个 owner-proof guard functions。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 任一 PL/pgSQL function 创建失败时向外传播。
    """

    present_core = " AND ".join(f"NEW.{column} IS NOT NULL" for column in _RUN_CORE_COLUMNS)
    op.execute(
        f"""
        CREATE FUNCTION {_SCHEMA}.source_sync_runs_require_v1_insert()
        RETURNS trigger AS $$
        BEGIN
            IF NOT ({present_core}) THEN
                RAISE EXCEPTION 'source_sync_runs requires v1 core on insert';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_SCHEMA}.source_health_snapshots_require_v2_insert()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.health_state_version IS NULL THEN
                RAISE EXCEPTION 'source_health_snapshots requires v2 version on insert';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_SCHEMA}.source_sync_operations_require_initial_insert()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.state <> 'active' OR NEW.generation <> 1
               OR NEW.terminal_source_sync_run_id IS NOT NULL
               OR NEW.owner_attempt_id IS NULL OR NEW.owner_binding_disposition IS NULL
               OR NEW.payload_sha256 IS NULL OR NEW.execution_snapshot_sha256 IS NULL
               OR NEW.execution_snapshot_json IS NULL OR NEW.acquired_at IS NULL
               OR NEW.tenant_id IS NULL OR NEW.job_run_id IS NULL
               OR NEW.subscription_id IS NULL THEN
                RAISE EXCEPTION 'source_sync_operations initial insert invalid';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_SCHEMA}.source_health_states_require_initial_insert()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.version <> 1 OR NEW.last_source_sync_run_id IS NULL
               OR NEW.observed_at IS NULL THEN
                RAISE EXCEPTION 'source_health_states initial insert invalid';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for function_name, table_name in _APPEND_ONLY_GUARDS:
        op.execute(
            f"""
            CREATE FUNCTION {_SCHEMA}.{function_name}()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '{table_name} is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    op.execute(
        f"""
        CREATE FUNCTION {_SCHEMA}.guard_source_sync_operations_transition()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.state = 'terminal' THEN
                RAISE EXCEPTION 'terminal source operation is immutable';
            END IF;
            IF OLD.id IS DISTINCT FROM NEW.id
               OR OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
               OR OLD.job_run_id IS DISTINCT FROM NEW.job_run_id
               OR OLD.subscription_id IS DISTINCT FROM NEW.subscription_id
               OR OLD.payload_sha256 IS DISTINCT FROM NEW.payload_sha256
               OR OLD.execution_snapshot_sha256 IS DISTINCT FROM NEW.execution_snapshot_sha256
               OR OLD.execution_snapshot_json IS DISTINCT FROM NEW.execution_snapshot_json
               OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
                RAISE EXCEPTION 'source operation immutable identity drift';
            END IF;
            IF NEW.state = 'active' THEN
                IF OLD.state <> 'active'
                   OR NEW.owner_attempt_id IS NOT DISTINCT FROM OLD.owner_attempt_id
                   OR NEW.generation <> OLD.generation + 1
                   OR NEW.owner_binding_disposition NOT IN ('ready', 'disabled', 'stale')
                   OR NEW.acquired_at <> NEW.updated_at
                   OR NEW.acquired_at <= OLD.acquired_at
                   OR NEW.terminal_source_sync_run_id IS NOT NULL THEN
                    RAISE EXCEPTION 'source operation takeover transition invalid';
                END IF;
            ELSIF NEW.state = 'terminal' THEN
                IF OLD.state <> 'active' OR NEW.terminal_source_sync_run_id IS NULL
                   OR NEW.owner_attempt_id IS DISTINCT FROM OLD.owner_attempt_id
                   OR NEW.generation IS DISTINCT FROM OLD.generation
                   OR NEW.owner_binding_disposition IS DISTINCT FROM OLD.owner_binding_disposition
                   OR NEW.acquired_at IS DISTINCT FROM OLD.acquired_at
                   OR NEW.updated_at < OLD.updated_at THEN
                    RAISE EXCEPTION 'source operation terminal transition invalid';
                END IF;
            ELSE
                RAISE EXCEPTION 'source operation state invalid';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {_SCHEMA}.guard_source_health_states_transition()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.id IS DISTINCT FROM NEW.id
               OR OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
               OR OLD.subscription_id IS DISTINCT FROM NEW.subscription_id
               OR OLD.created_at IS DISTINCT FROM NEW.created_at
               OR NEW.version <> OLD.version + 1
               OR NEW.observed_at IS DISTINCT FROM NEW.updated_at THEN
                RAISE EXCEPTION 'source health identity/version transition invalid';
            END IF;
            IF OLD.status = 'disabled' THEN
                IF NEW.status <> 'healthy' OR NEW.consecutive_failures <> 0
                   OR NEW.safe_error_code IS NOT NULL
                   OR NEW.last_source_sync_run_id IS DISTINCT FROM OLD.last_source_sync_run_id
                   OR NEW.observed_at <= OLD.observed_at THEN
                    RAISE EXCEPTION 'source health re-enable transition invalid';
                END IF;
            ELSIF NEW.last_source_sync_run_id IS NOT DISTINCT FROM OLD.last_source_sync_run_id
               OR NEW.observed_at < OLD.observed_at THEN
                RAISE EXCEPTION 'source health observation transition invalid';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for function_name, table_name in _DELETE_GUARDS:
        op.execute(
            f"""
            CREATE FUNCTION {_SCHEMA}.{function_name}()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '{table_name} delete rejected';
            END;
            $$ LANGUAGE plpgsql
            """
        )


def _create_guard_triggers() -> None:
    """按 exact manifest 把 11 个 function 绑定到唯一 table/timing。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 任一 trigger binding 创建失败时向外传播。
    """

    for function_name, table_name in _INSERT_GUARDS:
        op.execute(
            f"CREATE TRIGGER {function_name}_trigger BEFORE INSERT ON {_SCHEMA}.{table_name} "
            f"FOR EACH ROW EXECUTE FUNCTION {_SCHEMA}.{function_name}()"
        )
    for function_name, table_name in _APPEND_ONLY_GUARDS:
        op.execute(
            f"CREATE TRIGGER {function_name}_trigger BEFORE UPDATE OR DELETE ON "
            f"{_SCHEMA}.{table_name} FOR EACH ROW EXECUTE FUNCTION {_SCHEMA}.{function_name}()"
        )
    for function_name, table_name in _TRANSITION_GUARDS:
        op.execute(
            f"CREATE TRIGGER {function_name}_trigger BEFORE UPDATE ON {_SCHEMA}.{table_name} "
            f"FOR EACH ROW EXECUTE FUNCTION {_SCHEMA}.{function_name}()"
        )
    for function_name, table_name in _DELETE_GUARDS:
        op.execute(
            f"CREATE TRIGGER {function_name}_trigger BEFORE DELETE ON {_SCHEMA}.{table_name} "
            f"FOR EACH ROW EXECUTE FUNCTION {_SCHEMA}.{function_name}()"
        )


def _grant_and_enable_rls() -> None:
    """为三新表安装最小权限与 exact tenant policy。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 任一 revoke、grant、RLS 或 policy DDL 失败时向外传播。
    """

    for table_name in _NEW_TABLES:
        op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.{table_name} FROM PUBLIC")
        op.execute(
            f"GRANT SELECT, INSERT ON TABLE {_SCHEMA}.{table_name} TO {PLATFORM_APP_ROLE}"
        )
        op.execute(
            f"GRANT SELECT ON TABLE {_SCHEMA}.{table_name} TO {PLATFORM_AUDIT_ROLE}"
        )
    op.execute(
        f"GRANT UPDATE (owner_attempt_id, generation, acquired_at, owner_binding_disposition, "
        f"state, terminal_source_sync_run_id, updated_at) ON TABLE "
        f"{_SCHEMA}.source_sync_operations TO {PLATFORM_APP_ROLE}"
    )
    op.execute(
        f"GRANT UPDATE (status, consecutive_failures, safe_error_code, version, observed_at, "
        f"last_source_sync_run_id, updated_at) ON TABLE {_SCHEMA}.source_health_states "
        f"TO {PLATFORM_APP_ROLE}"
    )
    for table_name in _NEW_TABLES:
        op.execute(f"ALTER TABLE {_SCHEMA}.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {_SCHEMA}.{table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {_SCHEMA}.{table_name} "
            f"FOR ALL TO {PLATFORM_APP_ROLE} USING ({_TENANT_EXPRESSION} = tenant_id) "
            f"WITH CHECK ({_TENANT_EXPRESSION} = tenant_id)"
        )


def _assert_0005_catalog() -> None:
    """从 single manifest 做 upgrade/downgrade 共用的 catalog self-check。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 任一 catalog、security 或 guard manifest 漂移时抛出。
        SQLAlchemyError: catalog 查询失败时向外传播。
    """

    bind = op.get_bind()
    table_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema = '{_SCHEMA}'",
    )
    _assert_count(table_count, 27, "0005 catalog self-check：table count 不是 27")
    new_table_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema = '{_SCHEMA}' AND table_name IN "
        f"({_qualified_literals(_NEW_TABLES)})",
    )
    _assert_count(new_table_count, 3, "0005 catalog self-check：三新表缺失")
    constraint_names = _UNIQUE_MANIFEST + _FK_MANIFEST + _CHECK_MANIFEST + (
        "pk_source_sync_operations",
        "pk_source_health_states",
        "pk_source_health_alert_outbox",
    )
    constraint_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_constraint con JOIN pg_namespace n "
        "ON n.oid = con.connamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND con.conname IN "
        f"({_qualified_literals(constraint_names)})",
    )
    _assert_count(
        constraint_count,
        len(constraint_names),
        "0005 catalog self-check：named constraint manifest 漂移",
    )
    new_table_constraint_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_constraint con JOIN pg_class rel "
        "ON rel.oid = con.conrelid JOIN pg_namespace n ON n.oid = rel.relnamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND rel.relname IN "
        f"({_qualified_literals(_NEW_TABLES)})",
    )
    _assert_count(
        new_table_constraint_count,
        23,
        "0005 catalog self-check：新表存在额外或缺失 constraint",
    )
    affected_constraint_rows = bind.execute(
        text(
            "SELECT rel.relname, con.conname, con.contype "
            "FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = rel.relnamespace "
            f"WHERE n.nspname = '{_SCHEMA}' AND rel.relname IN "
            f"({_qualified_literals(_AFFECTED_TABLES)})"
        )
    ).fetchall()
    actual_affected_constraints = {
        (str(row[0]), str(row[1]), str(row[2]))
        for row in affected_constraint_rows
    }
    if actual_affected_constraints != _AFFECTED_CONSTRAINT_IDENTITY_MANIFEST:
        raise RuntimeError(
            "0005 catalog self-check：affected-table constraint exact manifest 漂移"
        )
    check_rows = bind.execute(
        text(
            "SELECT rel.relname, con.conname, con.contype, "
            "pg_get_constraintdef(con.oid) "
            "FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = con.connamespace "
            f"WHERE n.nspname = '{_SCHEMA}' AND con.conname IN "
            f"({_qualified_literals(_CHECK_MANIFEST)})"
        )
    ).fetchall()
    actual_checks = {
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
        for row in check_rows
    }
    if actual_checks != _expected_check_catalog(bind):
        raise RuntimeError("0005 catalog self-check：CHECK table/kind/definition manifest 漂移")
    unique_rows = bind.execute(
        text(
            "SELECT con.conname, rel.relname, "
            "array_to_string(ARRAY(SELECT a.attname FROM unnest(con.conkey) "
            "WITH ORDINALITY AS k(attnum, ord) JOIN pg_attribute a "
            "ON a.attrelid = con.conrelid AND a.attnum = k.attnum ORDER BY k.ord), ',') "
            "FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = con.connamespace "
            f"WHERE n.nspname = '{_SCHEMA}' AND con.contype = 'u' "
            f"AND con.conname IN ({_qualified_literals(_UNIQUE_MANIFEST)})"
        )
    ).fetchall()
    actual_unique_shapes = {
        (str(row[0]), str(row[1]), str(row[2])) for row in unique_rows
    }
    if actual_unique_shapes != set(_UNIQUE_SHAPES):
        raise RuntimeError("0005 catalog self-check：UNIQUE ordered-column manifest 漂移")
    pk_rows = bind.execute(
        text(
            "SELECT con.conname, rel.relname, "
            "array_to_string(ARRAY(SELECT a.attname FROM unnest(con.conkey) "
            "WITH ORDINALITY AS k(attnum, ord) JOIN pg_attribute a "
            "ON a.attrelid = con.conrelid AND a.attnum = k.attnum ORDER BY k.ord), ',') "
            "FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = con.connamespace "
            f"WHERE n.nspname = '{_SCHEMA}' AND con.contype = 'p' "
            "AND con.conname IN ('pk_source_sync_operations', "
            "'pk_source_health_states', 'pk_source_health_alert_outbox')"
        )
    ).fetchall()
    actual_pk_shapes = {(str(row[0]), str(row[1]), str(row[2])) for row in pk_rows}
    expected_pk_shapes = {
        ("pk_source_sync_operations", "source_sync_operations", "id"),
        ("pk_source_health_states", "source_health_states", "id"),
        ("pk_source_health_alert_outbox", "source_health_alert_outbox", "id"),
    }
    if actual_pk_shapes != expected_pk_shapes:
        raise RuntimeError("0005 catalog self-check：PK manifest 漂移")
    fk_rows = bind.execute(
        text(
            "SELECT con.conname, rel.relname, "
            "array_to_string(ARRAY(SELECT a.attname FROM unnest(con.conkey) "
            "WITH ORDINALITY AS k(attnum, ord) JOIN pg_attribute a "
            "ON a.attrelid = con.conrelid AND a.attnum = k.attnum ORDER BY k.ord), ','), "
            "ref.relname, array_to_string(ARRAY(SELECT a.attname FROM unnest(con.confkey) "
            "WITH ORDINALITY AS k(attnum, ord) JOIN pg_attribute a "
            "ON a.attrelid = con.confrelid AND a.attnum = k.attnum ORDER BY k.ord), ',') "
            "FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_class ref ON ref.oid = con.confrelid "
            "JOIN pg_namespace n ON n.oid = con.connamespace "
            f"WHERE n.nspname = '{_SCHEMA}' AND con.contype = 'f' "
            f"AND con.conname IN ({_qualified_literals(_FK_MANIFEST)})"
        )
    ).fetchall()
    actual_fk_shapes = {
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]))
        for row in fk_rows
    }
    if actual_fk_shapes != set(_FK_SHAPES):
        raise RuntimeError("0005 catalog self-check：FK ordered lineage manifest 漂移")
    index_names = _PARTIAL_UNIQUE_INDEX_MANIFEST + _INDEX_MANIFEST + _REPLACED_BASELINE_INDEX_NAMES
    index_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_indexes "
        f"WHERE schemaname = '{_SCHEMA}' AND indexname IN "
        f"({_qualified_literals(index_names)})",
    )
    _assert_count(index_count, len(index_names), "0005 catalog self-check：index manifest 漂移")
    index_rows = bind.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes "
            f"WHERE schemaname = '{_SCHEMA}' AND indexname IN "
            f"({_qualified_literals(index_names)})"
        )
    ).fetchall()
    actual_index_definitions = {(str(row[0]), str(row[1])) for row in index_rows}
    if actual_index_definitions != set(_INDEX_DEFINITION_MANIFEST):
        raise RuntimeError("0005 catalog self-check：index definition/predicate manifest 漂移")
    affected_index_rows = bind.execute(
        text(
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            f"WHERE schemaname = '{_SCHEMA}' AND tablename IN "
            f"({_qualified_literals(_AFFECTED_TABLES)})"
        )
    ).fetchall()
    actual_affected_indexes = {
        (str(row[0]), str(row[1]), str(row[2])) for row in affected_index_rows
    }
    if actual_affected_indexes != _AFFECTED_INDEX_DEFINITION_MANIFEST:
        raise RuntimeError(
            "0005 catalog self-check：affected-table index exact manifest 漂移"
        )
    function_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND p.proname IN "
        f"({_qualified_literals(_FUNCTION_MANIFEST)})",
    )
    _assert_count(function_count, 11, "0005 catalog self-check：guard function manifest 漂移")
    trigger_rows = bind.execute(
        text(
            "SELECT t.tgname, c.relname, fn.nspname, p.proname, t.tgtype, t.tgenabled "
            "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_proc p ON p.oid = t.tgfoid "
            "JOIN pg_namespace fn ON fn.oid = p.pronamespace "
            f"WHERE n.nspname = '{_SCHEMA}' AND NOT t.tgisinternal AND c.relname IN "
            "('source_sync_runs', 'source_health_snapshots', 'source_sync_operations', "
            "'source_health_states', 'source_health_alert_outbox')"
        )
    ).fetchall()
    actual_triggers = {
        (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            int(row[4]),
            str(row[5]),
        )
        for row in trigger_rows
    }
    expected_triggers = {
        (f"{name}_trigger", table_name, _SCHEMA, name, 7, "O")
        for name, table_name in _INSERT_GUARDS
    } | {
        (f"{name}_trigger", table_name, _SCHEMA, name, 27, "O")
        for name, table_name in _APPEND_ONLY_GUARDS
    } | {
        (f"{name}_trigger", table_name, _SCHEMA, name, 19, "O")
        for name, table_name in _TRANSITION_GUARDS
    } | {
        (f"{name}_trigger", table_name, _SCHEMA, name, 11, "O")
        for name, table_name in _DELETE_GUARDS
    }
    if actual_triggers != expected_triggers:
        raise RuntimeError("0005 catalog self-check：trigger event/function/enabled manifest 漂移")
    policy_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_policies "
        f"WHERE schemaname = '{_SCHEMA}' AND tablename IN "
        f"({_qualified_literals(_NEW_TABLES)}) AND policyname = 'tenant_isolation'",
    )
    _assert_count(policy_count, 3, "0005 catalog self-check：new-table policy manifest 漂移")
    policy_rows = bind.execute(
        text(
            "SELECT tablename, policyname, cmd, roles::text, qual, with_check "
            "FROM pg_policies "
            f"WHERE schemaname = '{_SCHEMA}' AND tablename IN "
            f"({_qualified_literals(_NEW_TABLES)})"
        )
    ).fetchall()
    policy_expression = (
        "((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid = tenant_id)"
    )
    actual_policies = {
        tuple(str(value) for value in row) for row in policy_rows
    }
    expected_policies = {
        (
            table_name,
            "tenant_isolation",
            "ALL",
            f"{{{PLATFORM_APP_ROLE}}}",
            policy_expression,
            policy_expression,
        )
        for table_name in _NEW_TABLES
    }
    if actual_policies != expected_policies:
        raise RuntimeError("0005 catalog self-check：policy role/qual/check manifest 漂移")
    rls_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN "
        f"({_qualified_literals(_NEW_TABLES)}) AND c.relrowsecurity AND c.relforcerowsecurity",
    )
    _assert_count(rls_count, 3, "0005 catalog self-check：new-table RLS 未 enable+force")
    invalid_fk = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_constraint con JOIN pg_namespace n "
        "ON n.oid = con.connamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND con.conname IN "
        f"({_qualified_literals(_FK_MANIFEST)}) AND (con.contype <> 'f' OR con.confdeltype <> 'r' "
        "OR NOT con.convalidated)",
    )
    _assert_count(invalid_fk, 0, "0005 catalog self-check：FK action/validation 漂移")
    weak_fk_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_constraint con JOIN pg_namespace n "
        "ON n.oid = con.connamespace "
        f"WHERE n.nspname = '{_SCHEMA}' AND "
        "con.conname = 'fk_source_health_snapshots_tenant_sync_run'",
    )
    _assert_count(weak_fk_count, 0, "0005 catalog self-check：legacy weak snapshot FK 未移除")
    table_acl_rows = bind.execute(
        text(
            "SELECT c.relname, CASE WHEN acl.grantee = 0 THEN 'PUBLIC' "
            "ELSE grantee_role.rolname END, acl.privilege_type, acl.is_grantable "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "CROSS JOIN LATERAL aclexplode(c.relacl) acl "
            "LEFT JOIN pg_roles grantee_role ON grantee_role.oid = acl.grantee "
            f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN "
            f"({_qualified_literals(_NEW_TABLES)}) AND c.relkind = 'r'"
        )
    ).fetchall()
    actual_table_acl = {
        (str(row[0]), str(row[1]), str(row[2]), bool(row[3]))
        for row in table_acl_rows
    }
    owner_name = str(bind.execute(text("SELECT current_user")).scalar_one())
    expected_table_acl = {
        (table_name, owner_name, privilege, False)
        for table_name in _NEW_TABLES
        for privilege in _NEW_TABLE_OWNER_PRIVILEGES
    } | {
        (table_name, PLATFORM_APP_ROLE, privilege, False)
        for table_name in _NEW_TABLES
        for privilege in ("INSERT", "SELECT")
    } | {
        (table_name, PLATFORM_AUDIT_ROLE, "SELECT", False)
        for table_name in _NEW_TABLES
    }
    if actual_table_acl != expected_table_acl:
        raise RuntimeError("0005 catalog self-check：new-table table ACL manifest 漂移")
    column_acl_rows = bind.execute(
        text(
            "SELECT c.relname, a.attname, CASE WHEN acl.grantee = 0 THEN 'PUBLIC' "
            "ELSE grantee_role.rolname END, acl.privilege_type, acl.is_grantable "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
            "CROSS JOIN LATERAL aclexplode(a.attacl) acl "
            "LEFT JOIN pg_roles grantee_role ON grantee_role.oid = acl.grantee "
            f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN "
            f"({_qualified_literals(_NEW_TABLES)}) AND c.relkind = 'r'"
        )
    ).fetchall()
    actual_column_acl = {
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]), bool(row[4]))
        for row in column_acl_rows
    }
    # ``attacl``只存显式 column grant；owner 的隐式 table 权限不会逐列展开。
    # 因此终态 exact set 只包含显式授予 app 的十四个 UPDATE tuple。
    expected_column_acl = {
        (table_name, column_name, PLATFORM_APP_ROLE, privilege, grantable)
        for table_name, column_name, privilege, grantable
        in _NEW_TABLE_APP_COLUMN_UPDATE_MANIFEST
    }
    if actual_column_acl != expected_column_acl:
        raise RuntimeError("0005 catalog self-check：new-table column ACL manifest 漂移")
    if any(len(name.encode("utf-8")) > 63 for name in _NEW_0005_OBJECT_NAMES):
        raise RuntimeError("0005 catalog self-check：identifier 超过 PostgreSQL 63-byte 上限")


def _0005_table_oids(bind: Connection) -> list[str]:
    """返回三个新表的 catalog OID 字符串列表。

    Args:
        bind: 当前 Alembic 连接。

    Returns:
        三个新表当前存在的 OID 字符串列表。

    Raises:
        SQLAlchemyError: catalog 查询失败时向外传播。
    """

    rows = bind.execute(
        text(
            "SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE n.nspname = '{_SCHEMA}' AND c.relname IN "
            f"({_qualified_literals(_NEW_TABLES)})"
        )
    ).fetchall()
    return [str(row[0]) for row in rows]


def _old_subscription_identity_conflicts(bind: Connection) -> int:
    """返回恢复 0001 三条 target-only unique index 会产生的冲突数。

    Args:
        bind: 当前 Alembic 连接。

    Returns:
        三类旧 target identity 中重复分组的总数。

    Raises:
        RuntimeError: catalog 标量无法转换为整数时抛出。
        SQLAlchemyError: 数据查询失败时向外传播。
    """

    statement = (
        f"SELECT (SELECT count(*) FROM (SELECT tenant_id FROM {_SCHEMA}.source_subscriptions "
        "WHERE company_id IS NULL AND security_id IS NULL GROUP BY tenant_id HAVING count(*) > 1) q) "
        f"+ (SELECT count(*) FROM (SELECT tenant_id, company_id FROM {_SCHEMA}.source_subscriptions "
        "WHERE company_id IS NOT NULL GROUP BY tenant_id, company_id HAVING count(*) > 1) q) "
        f"+ (SELECT count(*) FROM (SELECT tenant_id, security_id FROM {_SCHEMA}.source_subscriptions "
        "WHERE security_id IS NOT NULL GROUP BY tenant_id, security_id HAVING count(*) > 1) q)"
    )
    return _fetch_scalar_int(bind, statement)


def _lock_downgrade_targets() -> None:
    """在任何 downgrade admission 读取前锁定全部 destructive targets。

    锁按 child 到 parent 的固定顺序以单条 ``NOWAIT`` 请求取得；任一
    runtime DML 已持锁时立即 fail closed，避免加入 repository parent-first
    row lock 或 direct-DML child-first FK lock 的等待图。全部锁取得后由
    Alembic migration transaction 持有到逆向 DDL 与 revision 更新完成，
    形成 admission 的线性化点。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 当前 migration transaction 不是 READ COMMITTED 时抛出。
        SQLAlchemyError: 任一目标不存在、正被占用或数据库拒绝锁时向外传播。
    """

    qualified_tables = ", ".join(
        f"{_SCHEMA}.{table_name}" for table_name in _DOWNGRADE_LOCK_TABLES
    )
    op.execute(f"LOCK TABLE {qualified_tables} IN ACCESS EXCLUSIVE MODE NOWAIT")
    isolation = str(
        op.get_bind().execute(text("SHOW transaction_isolation")).scalar_one()
    )
    if isolation != "read committed":
        raise RuntimeError("0005 downgrade 拒绝：transaction isolation 必须为 read committed")


def _downgrade_admission() -> None:
    """在线性化锁内拒绝业务数据、旧索引冲突与外部依赖。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: catalog、业务数据、旧索引或外部依赖不满足时抛出。
        SQLAlchemyError: 目标锁或 catalog 查询被数据库拒绝时向外传播。
    """

    _lock_downgrade_targets()
    _assert_0005_catalog()
    bind = op.get_bind()
    business_rows = _fetch_scalar_int(
        bind,
        f"SELECT (SELECT count(*) FROM {_SCHEMA}.source_health_alert_outbox) "
        f"+ (SELECT count(*) FROM {_SCHEMA}.source_health_states) "
        f"+ (SELECT count(*) FROM {_SCHEMA}.source_sync_operations)",
    )
    _assert_count(business_rows, 0, "0005 downgrade 拒绝：三新表仍存在业务行")
    any_run_value = " OR ".join(f"{column} IS NOT NULL" for column in _RUN_COLUMNS)
    migrated_run_rows = _fetch_scalar_int(
        bind,
        f"SELECT count(*) FROM {_SCHEMA}.source_sync_runs WHERE {any_run_value}",
    )
    _assert_count(migrated_run_rows, 0, "0005 downgrade 拒绝：source run 存在 0005 durable 字段")
    snapshot_rows = _fetch_scalar_int(
        bind,
        f"SELECT count(*) FROM {_SCHEMA}.source_health_snapshots "
        "WHERE health_state_version IS NOT NULL",
    )
    _assert_count(snapshot_rows, 0, "0005 downgrade 拒绝：snapshot 存在 health_state_version")
    _assert_count(
        _old_subscription_identity_conflicts(bind),
        0,
        "0005 downgrade 拒绝：恢复 0001 subscription unique 会冲突",
    )
    table_oids = _0005_table_oids(bind)
    if table_oids:
        oid_list = ", ".join(table_oids)
        external_dependencies = _fetch_scalar_int(
            bind,
            "SELECT count(*) FROM pg_depend d WHERE d.refclassid = 'pg_class'::regclass "
            f"AND d.refobjid IN ({oid_list}) AND (d.classid = 'pg_rewrite'::regclass "
            "OR (d.classid = 'pg_constraint'::regclass AND d.objid NOT IN "
            f"(SELECT con.oid FROM pg_constraint con WHERE con.conrelid IN ({oid_list}))))",
        )
        _assert_count(external_dependencies, 0, "0005 downgrade 拒绝：存在外部 view/FK dependency")
    role_dependencies = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM pg_auth_members m JOIN pg_roles gr ON gr.oid = m.roleid "
        f"WHERE gr.rolname IN ('{PLATFORM_APP_ROLE}', '{PLATFORM_AUDIT_ROLE}')",
    )
    _assert_count(role_dependencies, 0, "0005 downgrade 拒绝：platform role 存在外部 member")


def _revoke_drop_guard_and_new_tables() -> None:
    """逆序撤销三新表 grants/RLS，并删除 exact guards、functions 与 tables。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 任一 revoke 或 destructive DDL 失败时向外传播。
    """

    for table_name in _NEW_TABLES:
        op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.{table_name} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.{table_name} FROM {PLATFORM_APP_ROLE}")
        op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.{table_name} FROM {PLATFORM_AUDIT_ROLE}")
    for trigger_name, table_name in reversed(_TRIGGER_MANIFEST):
        op.execute(f"DROP TRIGGER {trigger_name} ON {_SCHEMA}.{table_name}")
    for function_name in reversed(_FUNCTION_MANIFEST):
        op.execute(f"DROP FUNCTION {_SCHEMA}.{function_name}()")
    for table_name in _NEW_TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {_SCHEMA}.{table_name}")
        op.execute(f"ALTER TABLE {_SCHEMA}.{table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {_SCHEMA}.{table_name} DISABLE ROW LEVEL SECURITY")
    for table_name in reversed(_NEW_TABLES):
        op.execute(f"DROP TABLE {_SCHEMA}.{table_name}")


def _restore_snapshot_baseline() -> None:
    """先恢复并验证弱 FK，再显式移除所有 version 依赖后删除列。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: FK validation 或任一逆向 DDL 失败时向外传播。
    """

    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_health_snapshots ADD CONSTRAINT "
        "fk_source_health_snapshots_tenant_sync_run FOREIGN KEY (tenant_id, sync_run_id) "
        f"REFERENCES {_SCHEMA}.source_sync_runs (tenant_id, id) ON DELETE RESTRICT NOT VALID"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_health_snapshots VALIDATE CONSTRAINT "
        "fk_source_health_snapshots_tenant_sync_run"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_health_snapshots DROP CONSTRAINT "
        "fk_source_health_snapshots_tenant_subscription_run_v2"
    )
    op.execute(
        f"DROP INDEX {_SCHEMA}.uq_source_health_snapshots_tenant_subscription_version_v2"
    )
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_health_snapshots "
        "DROP CONSTRAINT uq_source_health_snapshots_tenant_subscription_id_v2, "
        "DROP CONSTRAINT uq_source_health_snapshots_tenant_sub_run_version_id_v2, "
        "DROP CONSTRAINT ck_source_health_snapshots_v2_shape, "
        "DROP COLUMN health_state_version"
    )


def _restore_source_runs_baseline() -> None:
    """逆序移除 run child FK、index、parent、check 与 14 列。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 任一 source run 逆向 DDL 失败时向外传播。
    """

    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_sync_runs DROP CONSTRAINT "
        "fk_source_sync_runs_tenant_job_attempt_v2"
    )
    op.execute(f"DROP INDEX {_SCHEMA}.uq_source_sync_runs_tenant_job_run_v2")
    op.execute(f"DROP INDEX {_SCHEMA}.uq_source_sync_runs_tenant_job_attempt_v2")
    op.execute(
        f"ALTER TABLE {_SCHEMA}.source_sync_runs "
        "DROP CONSTRAINT uq_source_sync_runs_tenant_subscription_id_v2, "
        "DROP CONSTRAINT uq_source_sync_runs_tenant_subscription_job_id_v2, "
        "DROP CONSTRAINT uq_source_sync_runs_tenant_sub_job_attempt_id_v2, "
        "DROP CONSTRAINT ck_source_sync_runs_v1_core_presence, "
        "DROP CONSTRAINT ck_source_sync_runs_v1_counts, "
        "DROP CONSTRAINT ck_source_sync_runs_v1_outcome_shape, "
        + ", ".join(f"DROP COLUMN {column}" for column in _RUN_COLUMNS)
    )


def _restore_subscription_indexes_for_downgrade() -> None:
    """恢复 exact 0001 target-only partial unique indexes。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 删除 0005 index 或恢复 0001 index 失败时向外传播。
    """

    for index_name in _REPLACED_BASELINE_INDEX_NAMES:
        op.execute(f"DROP INDEX {_SCHEMA}.{index_name}")
    op.execute(
        f"CREATE UNIQUE INDEX uq_source_subscriptions_tenant_wide ON {_SCHEMA}.source_subscriptions "
        "(tenant_id) WHERE company_id IS NULL AND security_id IS NULL"
    )
    op.execute(
        f"CREATE UNIQUE INDEX uq_source_subscriptions_company ON {_SCHEMA}.source_subscriptions "
        "(tenant_id, company_id) WHERE company_id IS NOT NULL"
    )
    op.execute(
        f"CREATE UNIQUE INDEX uq_source_subscriptions_security ON {_SCHEMA}.source_subscriptions "
        "(tenant_id, security_id) WHERE security_id IS NOT NULL"
    )


def _assert_0004_catalog_after_downgrade() -> None:
    """确认 0005 owner 全消失且 24-table baseline 恢复。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 任一 0005 owner 残留或 baseline 漂移时抛出。
        SQLAlchemyError: catalog 查询失败时向外传播。
    """

    bind = op.get_bind()
    table_count = _fetch_scalar_int(
        bind,
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema = '{_SCHEMA}'",
    )
    _assert_count(table_count, 24, "0005 downgrade self-check：table count 不是 24")
    if not _baseline_subscription_indexes_are_exact(bind):
        raise RuntimeError("0005 downgrade self-check：subscription index 未恢复 0001 shape")
    lingering = _fetch_scalar_int(
        bind,
        "SELECT (SELECT count(*) FROM pg_constraint WHERE conname IN "
        f"({_qualified_literals(_UNIQUE_MANIFEST + _FK_MANIFEST + _CHECK_MANIFEST)}) "
        ") + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        f"WHERE n.nspname='{_SCHEMA}' AND p.proname IN "
        f"({_qualified_literals(_FUNCTION_MANIFEST)}))",
    )
    _assert_count(lingering, 0, "0005 downgrade self-check：0005 owner 未完全清除")


def upgrade() -> None:
    """按 exact dependency DAG 安装 0005 source sync/health schema。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: preflight 或最终 catalog self-check 失败时抛出。
        SQLAlchemyError: 任一 transactional DDL 失败时向外传播。
    """

    _preflight_upgrade()
    _add_parent_attempt_unique()
    _extend_source_sync_runs()
    _extend_source_health_snapshots()
    _replace_subscription_indexes_for_upgrade()
    _create_source_sync_operations()
    _create_source_health_states()
    _create_source_health_alert_outbox()
    _create_guard_functions()
    _create_guard_triggers()
    _grant_and_enable_rls()
    _assert_0005_catalog()


def downgrade() -> None:
    """经 fail-closed admission 后无 CASCADE 精确回滚 0005 owner。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: admission 或恢复后的 catalog self-check 失败时抛出。
        SQLAlchemyError: 目标锁或任一 transactional DDL 失败时向外传播。
    """

    _downgrade_admission()
    _revoke_drop_guard_and_new_tables()
    _restore_snapshot_baseline()
    _restore_source_runs_baseline()
    _restore_subscription_indexes_for_downgrade()
    op.execute(
        f"ALTER TABLE {_SCHEMA}.job_attempts DROP CONSTRAINT "
        "uq_job_attempts_tenant_job_run_id_v2"
    )
    _assert_0004_catalog_after_downgrade()
