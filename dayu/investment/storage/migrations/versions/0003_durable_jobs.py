"""durable job queue schema 迁移（Slice 2.1）。

Revision ID: 0003_durable_jobs
Revises: 0002_workspace_import
Create Date: 2026-08-11

本迁移以 bootstrap superuser 在单次事务中新增七张 tenant-scoped 私有表
（``job_definitions`` / ``job_runs`` / ``job_attempts`` / ``job_leases`` /
``job_attempt_receipts`` / ``job_events`` / ``agent_run_correlations``）：

- 全部表位于 ``dayu_platform``，UUID 无 server random default，私有表
  均 ``tenant_id UUID NOT NULL FK organizations(id) ON DELETE RESTRICT``
  与 ``UNIQUE(tenant_id, id)``；时间为 UTC ``TIMESTAMPTZ``；
- mutable row 有 ``updated_at DEFAULT transaction_timestamp()`` 与正
  ``version``；append-only row 只有 ``created_at``；
- 七表均 ``ENABLE + FORCE ROW LEVEL SECURITY``，唯一 policy 复用现有
  ``app.tenant_id`` expression；
- app role 权限最小化：receipts/events 只 SELECT/INSERT；其余表
  SELECT/INSERT + 精确列级 UPDATE；identity/payload/fingerprint/
  fence/token/acquire 等不可由 app 更新，以列级 GRANT 与 DB trigger
  双重拒绝；audit 只 SELECT；PUBLIC 全 revoke；
- ``job_leases`` 的 release 是 versioned CAS + single-release trigger：
  只能从 ``released_at/release_reason`` 均 NULL 一次更新到两者均
  non-null 且 ``released_at >= acquired_at``，同一 release 不得改写。

exact receipt key set 与 outcome/safe-code/result 组合由
``dayu.investment.domain.jobs`` 的 immutable builder/parser 单一强制
（reconstruction 到 SQL CHECK 会引入脆弱正则），DB 层强制 schema 常量、
version、outcome/safe-code/result nullability 与 canonical hash 形态。

downgrade 先以 catalog 查询拒绝七表 owner 之外的外部依赖，再删
policies/grants/tables；保留 0001/0002 对象、roles、default org 与
Alembic version table；禁止 CASCADE。
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

revision = "0003_durable_jobs"
down_revision = "0002_workspace_import"
branch_labels = None
depends_on = None

_TENANT_EXPRESSION = "nullif(current_setting('app.tenant_id', true), '')::uuid"
"""RLS tenant policy 使用的租户上下文表达式（与 0001/0002 一致）。"""

_HEX64 = "'^[0-9a-f]{64}$'"
"""小写 64-hex SHA-256 的 CHECK 正则。"""

_RESERVED_RUN_ID = "'^run_[0-9a-f]{32}$'"
"""reserved Host run ID 形态（``run_`` + 32 位小写 hex）的 CHECK 正则。"""

_TABLES = (
    "job_definitions",
    "job_runs",
    "job_attempts",
    "job_leases",
    "job_attempt_receipts",
    "job_events",
    "agent_run_correlations",
)
"""七张 0003 表的依赖顺序（定义/删除共用）。"""

_JOB_LEASE_RELEASE_REASONS = (
    "'completion'",
    "'failure'",
    "'cancel_intent'",
    "'deadline'",
    "'lease_expired'",
)


def _create_tables() -> None:
    """创建七张 0003 表及其全部约束与索引。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    _create_job_definitions()
    _create_job_runs()
    _create_job_attempts()
    _create_job_leases()
    _create_job_attempt_receipts()
    _create_job_events()
    _create_agent_run_correlations()


def _create_job_definitions() -> None:
    """创建 ``job_definitions`` 表。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_definitions (
            id UUID CONSTRAINT pk_job_definitions PRIMARY KEY,
            tenant_id UUID NOT NULL,
            job_type TEXT NOT NULL,
            payload_schema_name TEXT NOT NULL,
            payload_schema_version INTEGER NOT NULL,
            max_attempts INTEGER NOT NULL,
            retry_base_seconds INTEGER NOT NULL,
            retry_max_seconds INTEGER NOT NULL,
            lease_duration_seconds INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_job_definitions_tenant_id_organizations
                FOREIGN KEY (tenant_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_job_definitions_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_job_definitions_tenant_id_job_type
                UNIQUE (tenant_id, job_type),
            CONSTRAINT ck_job_definitions_job_type_nonempty
                CHECK (job_type <> '' AND job_type = trim(job_type)),
            CONSTRAINT ck_job_definitions_payload_schema_name_nonempty
                CHECK (payload_schema_name <> '' AND payload_schema_name = trim(payload_schema_name)),
            CONSTRAINT ck_job_definitions_payload_schema_version_positive
                CHECK (payload_schema_version > 0),
            CONSTRAINT ck_job_definitions_max_attempts_positive
                CHECK (max_attempts > 0),
            CONSTRAINT ck_job_definitions_retry_base_seconds_positive
                CHECK (retry_base_seconds > 0),
            CONSTRAINT ck_job_definitions_retry_max_seconds_positive
                CHECK (retry_max_seconds > 0),
            CONSTRAINT ck_job_definitions_retry_max_ge_base
                CHECK (retry_max_seconds >= retry_base_seconds),
            CONSTRAINT ck_job_definitions_lease_duration_seconds_positive
                CHECK (lease_duration_seconds > 0),
            CONSTRAINT ck_job_definitions_status_closed
                CHECK (status IN ('active', 'disabled')),
            CONSTRAINT ck_job_definitions_version_positive
                CHECK (version > 0)
        )
        """
    )


def _create_job_runs() -> None:
    """创建 ``job_runs`` 表。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_runs (
            id UUID CONSTRAINT pk_job_runs PRIMARY KEY,
            tenant_id UUID NOT NULL,
            definition_id UUID NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_fingerprint CHAR(64) NOT NULL,
            payload_bytes BYTEA NOT NULL,
            payload_sha256 CHAR(64) NOT NULL,
            state TEXT NOT NULL,
            available_at TIMESTAMPTZ NOT NULL,
            deadline_at TIMESTAMPTZ NOT NULL,
            current_attempt_number INTEGER NOT NULL DEFAULT 0,
            next_event_sequence BIGINT NOT NULL DEFAULT 1,
            cancel_requested_at TIMESTAMPTZ NULL,
            cancel_reason TEXT NULL,
            completed_at TIMESTAMPTZ NULL,
            safe_failure_code TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_job_runs_tenant_id_organizations
                FOREIGN KEY (tenant_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_runs_tenant_definition_definitions
                FOREIGN KEY (tenant_id, definition_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_definitions (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_job_runs_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_job_runs_tenant_definition_idempotency_key
                UNIQUE (tenant_id, definition_id, idempotency_key),
            CONSTRAINT ck_job_runs_idempotency_key_nonempty
                CHECK (idempotency_key <> '' AND idempotency_key = trim(idempotency_key)),
            CONSTRAINT ck_job_runs_request_fingerprint_hex64
                CHECK (request_fingerprint ~ {_HEX64}),
            CONSTRAINT ck_job_runs_payload_sha256_hex64
                CHECK (payload_sha256 ~ {_HEX64}),
            CONSTRAINT ck_job_runs_state_closed
                CHECK (state IN ('ready', 'leased', 'cancel_requested', 'succeeded', 'failed', 'cancelled')),
            CONSTRAINT ck_job_runs_deadline_after_available
                CHECK (deadline_at > available_at),
            CONSTRAINT ck_job_runs_current_attempt_number_nonnegative
                CHECK (current_attempt_number >= 0),
            CONSTRAINT ck_job_runs_next_event_sequence_positive
                CHECK (next_event_sequence > 0),
            CONSTRAINT ck_job_runs_version_positive
                CHECK (version > 0)
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_job_runs_claim_ready
        ON {PLATFORM_SCHEMA_NAME}.job_runs (tenant_id, available_at, id)
        WHERE state = 'ready'
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_job_runs_cancel_recover
        ON {PLATFORM_SCHEMA_NAME}.job_runs (tenant_id, state, deadline_at)
        """
    )


def _create_job_attempts() -> None:
    """创建 ``job_attempts`` 表。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_attempts (
            id UUID CONSTRAINT pk_job_attempts PRIMARY KEY,
            tenant_id UUID NOT NULL,
            job_run_id UUID NOT NULL,
            attempt_number INTEGER NOT NULL,
            worker_id TEXT NOT NULL,
            state TEXT NOT NULL,
            fence BIGINT NOT NULL,
            lease_token_sha256 CHAR(64) NOT NULL,
            claimed_at TIMESTAMPTZ NOT NULL,
            lease_expires_at TIMESTAMPTZ NOT NULL,
            last_heartbeat_at TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL,
            safe_failure_code TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_job_attempts_tenant_id_organizations
                FOREIGN KEY (tenant_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_attempts_tenant_job_run_job_runs
                FOREIGN KEY (tenant_id, job_run_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_runs (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_job_attempts_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_job_attempts_tenant_job_run_attempt_number
                UNIQUE (tenant_id, job_run_id, attempt_number),
            CONSTRAINT uq_job_attempts_tenant_job_run_fence
                UNIQUE (tenant_id, job_run_id, fence),
            CONSTRAINT ck_job_attempts_worker_id_nonempty
                CHECK (worker_id <> '' AND worker_id = trim(worker_id)),
            CONSTRAINT ck_job_attempts_attempt_number_positive
                CHECK (attempt_number > 0),
            CONSTRAINT ck_job_attempts_fence_positive
                CHECK (fence > 0),
            CONSTRAINT ck_job_attempts_lease_token_sha256_hex64
                CHECK (lease_token_sha256 ~ {_HEX64}),
            CONSTRAINT ck_job_attempts_state_closed
                CHECK (state IN ('leased', 'succeeded', 'failed', 'cancelled', 'abandoned')),
            CONSTRAINT ck_job_attempts_lease_expires_after_claimed
                CHECK (lease_expires_at > claimed_at),
            CONSTRAINT ck_job_attempts_heartbeat_after_claimed
                CHECK (last_heartbeat_at IS NULL OR last_heartbeat_at >= claimed_at),
            CONSTRAINT ck_job_attempts_version_positive
                CHECK (version > 0)
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_job_attempts_recover
        ON {PLATFORM_SCHEMA_NAME}.job_attempts (tenant_id, state, lease_expires_at)
        """
    )


def _create_job_leases() -> None:
    """创建 ``job_leases`` 表。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_leases (
            id UUID CONSTRAINT pk_job_leases PRIMARY KEY,
            tenant_id UUID NOT NULL,
            job_run_id UUID NOT NULL,
            attempt_id UUID NOT NULL,
            fence BIGINT NOT NULL,
            token_sha256 CHAR(64) NOT NULL,
            acquired_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            released_at TIMESTAMPTZ NULL,
            release_reason TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_job_leases_tenant_id_organizations
                FOREIGN KEY (tenant_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_leases_tenant_job_run_job_runs
                FOREIGN KEY (tenant_id, job_run_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_runs (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_leases_tenant_attempt_job_attempts
                FOREIGN KEY (tenant_id, attempt_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_attempts (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_job_leases_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_job_leases_tenant_attempt_fence
                UNIQUE (tenant_id, attempt_id, fence),
            CONSTRAINT ck_job_leases_fence_positive
                CHECK (fence > 0),
            CONSTRAINT ck_job_leases_token_sha256_hex64
                CHECK (token_sha256 ~ {_HEX64}),
            CONSTRAINT ck_job_leases_expires_after_acquired
                CHECK (expires_at > acquired_at),
            CONSTRAINT ck_job_leases_release_reason_closed
                CHECK (release_reason IS NULL OR release_reason IN ({', '.join(_JOB_LEASE_RELEASE_REASONS)})),
            CONSTRAINT ck_job_leases_release_pair_present
                CHECK ((released_at IS NULL) = (release_reason IS NULL)),
            CONSTRAINT ck_job_leases_released_at_after_acquired
                CHECK (released_at IS NULL OR released_at >= acquired_at),
            CONSTRAINT ck_job_leases_version_positive
                CHECK (version > 0)
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_job_leases_attempt_history
        ON {PLATFORM_SCHEMA_NAME}.job_leases (tenant_id, attempt_id, expires_at DESC)
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION {PLATFORM_SCHEMA_NAME}.job_leases_single_release()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.released_at IS NOT NULL THEN
                IF OLD.released_at IS NOT NULL THEN
                    RAISE EXCEPTION 'job lease already released';
                END IF;
                IF NEW.release_reason IS NULL OR NEW.released_at < OLD.acquired_at THEN
                    RAISE EXCEPTION 'job lease release fields invalid';
                END IF;
            ELSIF NEW.release_reason IS NOT NULL THEN
                RAISE EXCEPTION 'job lease release fields must be paired';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER job_leases_single_release_trigger
        BEFORE UPDATE ON {PLATFORM_SCHEMA_NAME}.job_leases
        FOR EACH ROW EXECUTE FUNCTION {PLATFORM_SCHEMA_NAME}.job_leases_single_release()
        """
    )


def _create_job_attempt_receipts() -> None:
    """创建 append-only ``job_attempt_receipts`` 表。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_attempt_receipts (
            id UUID CONSTRAINT pk_job_attempt_receipts PRIMARY KEY,
            tenant_id UUID NOT NULL,
            job_run_id UUID NOT NULL,
            attempt_id UUID NOT NULL,
            outcome TEXT NOT NULL,
            result_schema_name TEXT NULL,
            result_schema_version INTEGER NULL,
            result_bytes BYTEA NULL,
            result_sha256 CHAR(64) NULL,
            receipt_schema_name TEXT NOT NULL,
            receipt_schema_version INTEGER NOT NULL,
            receipt_bytes BYTEA NOT NULL,
            receipt_sha256 CHAR(64) NOT NULL,
            safe_error_code TEXT NULL,
            finalized_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_job_attempt_receipts_tenant_id_organizations
                FOREIGN KEY (tenant_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_attempt_receipts_tenant_job_run_job_runs
                FOREIGN KEY (tenant_id, job_run_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_runs (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_attempt_receipts_tenant_attempt_job_attempts
                FOREIGN KEY (tenant_id, attempt_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_attempts (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_job_attempt_receipts_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_job_attempt_receipts_tenant_attempt
                UNIQUE (tenant_id, attempt_id),
            CONSTRAINT ck_job_attempt_receipts_outcome_closed
                CHECK (outcome IN ('succeeded', 'failed', 'cancelled')),
            CONSTRAINT ck_job_attempt_receipts_result_pair_all_or_none
                CHECK (
                    (result_schema_name IS NULL AND result_schema_version IS NULL
                     AND result_bytes IS NULL AND result_sha256 IS NULL)
                    OR
                    (result_schema_name IS NOT NULL AND result_schema_version IS NOT NULL
                     AND result_bytes IS NOT NULL AND result_sha256 IS NOT NULL)
                ),
            CONSTRAINT ck_job_attempt_receipts_result_only_on_success
                CHECK (
                    (result_schema_name IS NULL AND result_schema_version IS NULL
                     AND result_bytes IS NULL AND result_sha256 IS NULL)
                    OR
                    (outcome = 'succeeded' AND result_bytes IS NOT NULL
                     AND result_schema_name IS NOT NULL AND result_schema_version IS NOT NULL
                     AND result_sha256 IS NOT NULL)
                ),
            CONSTRAINT ck_job_attempt_receipts_safe_error_code_nullability
                CHECK (
                    (outcome = 'succeeded' AND safe_error_code IS NULL)
                    OR
                    (outcome IN ('failed', 'cancelled') AND safe_error_code IS NOT NULL)
                ),
            CONSTRAINT ck_job_attempt_receipts_receipt_schema_constants
                CHECK (
                    receipt_schema_name IN (
                        'dayu.job.generic-attempt-receipt',
                        'dayu.job.agent-run-terminal-receipt'
                    )
                    AND receipt_schema_version = 1
                ),
            CONSTRAINT ck_job_attempt_receipts_receipt_sha256_hex64
                CHECK (receipt_sha256 ~ {_HEX64}),
            CONSTRAINT ck_job_attempt_receipts_result_sha256_hex64
                CHECK (result_sha256 IS NULL OR result_sha256 ~ {_HEX64})
        )
        """
    )


def _create_job_events() -> None:
    """创建 append-only ``job_events`` 表。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_events (
            id UUID CONSTRAINT pk_job_events PRIMARY KEY,
            tenant_id UUID NOT NULL,
            job_run_id UUID NOT NULL,
            attempt_id UUID NULL,
            sequence_number BIGINT NOT NULL,
            event_type TEXT NOT NULL,
            safe_detail_bytes BYTEA NULL,
            safe_detail_sha256 CHAR(64) NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_job_events_tenant_id_organizations
                FOREIGN KEY (tenant_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_events_tenant_job_run_job_runs
                FOREIGN KEY (tenant_id, job_run_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_runs (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_job_events_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_job_events_tenant_job_run_sequence
                UNIQUE (tenant_id, job_run_id, sequence_number),
            CONSTRAINT ck_job_events_sequence_number_positive
                CHECK (sequence_number > 0),
            CONSTRAINT ck_job_events_event_type_nonempty
                CHECK (event_type <> '' AND event_type = trim(event_type)),
            CONSTRAINT ck_job_events_safe_detail_pair_all_or_none
                CHECK ((safe_detail_bytes IS NULL) = (safe_detail_sha256 IS NULL)),
            CONSTRAINT ck_job_events_safe_detail_sha256_hex64
                CHECK (safe_detail_sha256 IS NULL OR safe_detail_sha256 ~ {_HEX64})
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_job_events_append
        ON {PLATFORM_SCHEMA_NAME}.job_events (tenant_id, job_run_id, sequence_number)
        """
    )


def _create_agent_run_correlations() -> None:
    """创建 ``agent_run_correlations`` 表。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.agent_run_correlations (
            id UUID CONSTRAINT pk_agent_run_correlations PRIMARY KEY,
            tenant_id UUID NOT NULL,
            job_run_id UUID NOT NULL,
            attempt_id UUID NOT NULL,
            idempotency_key TEXT NOT NULL,
            reserved_host_run_id TEXT NOT NULL,
            state TEXT NOT NULL,
            observed_at TIMESTAMPTZ NULL,
            last_observation_sha256 CHAR(64) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            version INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT fk_agent_run_correlations_tenant_id_organizations
                FOREIGN KEY (tenant_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_agent_run_correlations_tenant_job_run_job_runs
                FOREIGN KEY (tenant_id, job_run_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_runs (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_agent_run_correlations_tenant_attempt_job_attempts
                FOREIGN KEY (tenant_id, attempt_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_attempts (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_agent_run_correlations_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_agent_run_correlations_tenant_attempt
                UNIQUE (tenant_id, attempt_id),
            CONSTRAINT uq_agent_run_correlations_reserved_host_run_id
                UNIQUE (reserved_host_run_id),
            CONSTRAINT ck_agent_run_correlations_idempotency_key_nonempty
                CHECK (idempotency_key <> '' AND idempotency_key = trim(idempotency_key)),
            CONSTRAINT ck_agent_run_correlations_reserved_host_run_id_format
                CHECK (reserved_host_run_id ~ {_RESERVED_RUN_ID}),
            CONSTRAINT ck_agent_run_correlations_state_closed
                CHECK (state IN ('reserved', 'host_created', 'host_running',
                                 'host_succeeded', 'host_failed', 'host_cancelled',
                                 'host_unsettled')),
            CONSTRAINT ck_agent_run_correlations_observed_pair_all_or_none
                CHECK ((observed_at IS NULL) = (last_observation_sha256 IS NULL)),
            CONSTRAINT ck_agent_run_correlations_last_observation_sha256_hex64
                CHECK (last_observation_sha256 IS NULL OR last_observation_sha256 ~ {_HEX64}),
            CONSTRAINT ck_agent_run_correlations_version_positive
                CHECK (version > 0)
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_agent_run_correlations_expired
        ON {PLATFORM_SCHEMA_NAME}.agent_run_correlations (tenant_id, state, updated_at)
        """
    )


def _grant_matrix() -> None:
    """清理 PUBLIC 并按最小权限矩阵授予 app/audit。

    receipts/events 只授予 app SELECT/INSERT；其余表 SELECT/INSERT +
    精确列级 UPDATE；audit 只 SELECT。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _TABLES:
        op.execute(
            f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM PUBLIC"
        )
    for table_name in _TABLES:
        op.execute(
            f"GRANT SELECT, INSERT ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} TO {PLATFORM_APP_ROLE}"
        )
    _grant_column_level_updates()
    for table_name in _TABLES:
        op.execute(
            f"GRANT SELECT ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} TO {PLATFORM_AUDIT_ROLE}"
        )


def _grant_column_level_updates() -> None:
    """为 app role 授予精确的列级 UPDATE 权限。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    column_updates: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "job_definitions",
            ("status", "updated_at", "version"),
        ),
        (
            "job_runs",
            (
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
            ),
        ),
        (
            "job_attempts",
            (
                "state",
                "lease_expires_at",
                "last_heartbeat_at",
                "finished_at",
                "safe_failure_code",
                "updated_at",
                "version",
            ),
        ),
        (
            "job_leases",
            ("released_at", "release_reason", "updated_at", "version"),
        ),
        (
            "agent_run_correlations",
            (
                "state",
                "observed_at",
                "last_observation_sha256",
                "updated_at",
                "version",
            ),
        ),
    )
    for table_name, columns in column_updates:
        op.execute(
            f"GRANT UPDATE ({', '.join(columns)}) ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} TO {PLATFORM_APP_ROLE}"
        )


def _create_immutable_guard_triggers() -> None:
    """为不可由 app 更新的 identity 列创建双重拒绝 trigger。

    列级 GRANT 已阻止 app UPDATE；本 trigger 是第二道防线，拒绝任何
    对 identity/payload/fingerprint/fence/token/acquire 列的 UPDATE
    （含 superuser 直接改）。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    _create_guard("job_definitions", ("id", "tenant_id", "job_type", "payload_schema_name",
                                      "payload_schema_version", "max_attempts", "retry_base_seconds",
                                      "retry_max_seconds", "lease_duration_seconds", "created_at"))
    _create_guard("job_runs", ("id", "tenant_id", "definition_id", "idempotency_key",
                               "request_fingerprint", "payload_bytes", "payload_sha256",
                               "deadline_at", "created_at"))
    _create_guard("job_attempts", ("id", "tenant_id", "job_run_id", "attempt_number",
                                   "worker_id", "fence", "lease_token_sha256", "claimed_at",
                                   "created_at"))
    _create_guard("job_leases", ("id", "tenant_id", "job_run_id", "attempt_id", "fence",
                                 "token_sha256", "acquired_at", "created_at"))
    _create_guard("agent_run_correlations", ("id", "tenant_id", "job_run_id", "attempt_id",
                                             "idempotency_key", "reserved_host_run_id",
                                             "created_at"))


def _create_guard(table_name: str, immutable_columns: tuple[str, ...]) -> None:
    """为单张表创建 immutable 列 UPDATE 拒绝 trigger。

    Args:
        table_name: 目标表名。
        immutable_columns: 不可更新的列名集合。

    Returns:
        无。

    Raises:
        无。
    """

    comparisons = " OR ".join(
        f"OLD.{column} IS DISTINCT FROM NEW.{column}" for column in immutable_columns
    )
    function_name = f"guard_{table_name}_immutable_columns"
    op.execute(
        f"""
        CREATE FUNCTION {PLATFORM_SCHEMA_NAME}.{function_name}()
        RETURNS trigger AS $$
        BEGIN
            IF ({comparisons}) THEN
                RAISE EXCEPTION 'immutable column update rejected on {table_name}';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {function_name}_trigger
        BEFORE UPDATE ON {PLATFORM_SCHEMA_NAME}.{table_name}
        FOR EACH ROW EXECUTE FUNCTION {PLATFORM_SCHEMA_NAME}.{function_name}()
        """
    )


def _enable_rls() -> None:
    """为七张表启用并强制 RLS，创建唯一 tenant_isolation policy。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _TABLES:
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
    """删除七张表的 tenant_isolation policy。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _TABLES:
        op.execute(
            f"DROP POLICY tenant_isolation ON {PLATFORM_SCHEMA_NAME}.{table_name}"
        )


def _revoke_grants() -> None:
    """撤销 0003 表的 app/audit grants 并清理 PUBLIC。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _TABLES:
        op.execute(
            f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM PUBLIC"
        )
        op.execute(
            f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM {PLATFORM_APP_ROLE}"
        )
        op.execute(
            f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM {PLATFORM_AUDIT_ROLE}"
        )


def _drop_triggers_and_functions() -> None:
    """删除 0003 的 trigger 与 guard/single-release 函数。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"DROP TRIGGER job_leases_single_release_trigger ON {PLATFORM_SCHEMA_NAME}.job_leases"
    )
    op.execute(
        f"DROP FUNCTION {PLATFORM_SCHEMA_NAME}.job_leases_single_release()"
    )
    guarded_tables = (
        "job_definitions",
        "job_runs",
        "job_attempts",
        "job_leases",
        "agent_run_correlations",
    )
    for table_name in guarded_tables:
        op.execute(
            f"DROP TRIGGER guard_{table_name}_immutable_columns_trigger ON {PLATFORM_SCHEMA_NAME}.{table_name}"
        )
        op.execute(
            f"DROP FUNCTION {PLATFORM_SCHEMA_NAME}.guard_{table_name}_immutable_columns()"
        )


def _0003_table_oids(bind: Connection) -> list[str]:
    """返回七张 0003 表在 ``dayu_platform`` schema 中的 OID 列表。

    Args:
        bind: Alembic 连接绑定。

    Returns:
        七张表的 ``pg_class.oid`` 字符串列表。

    Raises:
        无。
    """

    table_list = ", ".join(f"'{name}'" for name in _TABLES)
    rows = bind.execute(
        text(
            "SELECT c.oid FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE n.nspname = '{PLATFORM_SCHEMA_NAME}' "
            f"AND c.relname IN ({table_list})"
        )
    ).fetchall()
    return [str(row[0]) for row in rows]


def _downgrade_admission() -> None:
    """downgrade 破坏性 DDL 前的显式外部依赖 preflight。

    在删除 0003 policy/grants/tables 之前，先查询 ``pg_depend``：存在
    任何非 0003 owner 的对象（外部 view/rule，或其它表的 FK 引用
    0003 表）时，整次 downgrade fail closed 并回滚。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 存在 0003 owner 之外的外部依赖时抛出，消息只
            描述违规类别，不包含 DSN/credential。
    """

    bind = op.get_bind()
    table_oids = _0003_table_oids(bind)
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
            "downgrade 拒绝：0003 durable jobs 存在 owner 之外的外部依赖"
            "（外部 view/rule 或其它表的 FK），请先清理"
        )


def _drop_tables() -> None:
    """按依赖顺序删除七张 0003 表（无 CASCADE）。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in reversed(_TABLES):
        op.execute(f"DROP TABLE {PLATFORM_SCHEMA_NAME}.{table_name}")


def upgrade() -> None:
    """新增七张 durable jobs 表、RLS policy、trigger 与最小权限 grants。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    _create_tables()
    _grant_matrix()
    _create_immutable_guard_triggers()
    _enable_rls()


def downgrade() -> None:
    """精确回滚 0003 的 policy/triggers/grants/tables。

    在任何破坏性 DDL 前先执行 ``_downgrade_admission``：存在 0003
    owner 之外的外部依赖时整次 fail closed 并回滚，保留 0001/0002 的
    对象、roles、default org 与 Alembic version table。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 存在外部依赖时抛出，整次回滚。
    """

    _downgrade_admission()
    _drop_policies()
    _drop_triggers_and_functions()
    _revoke_grants()
    _drop_tables()
