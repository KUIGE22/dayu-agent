"""durable schedule + occurrence outbox schema 迁移（Slice 2.2）。

Revision ID: 0004_durable_schedules
Revises: 0003_durable_jobs
Create Date: 2026-08-12

本迁移以 bootstrap superuser 在单次事务中新增两张 tenant-scoped 私有表
（``job_schedules`` / ``job_schedule_occurrences``）：

- ``job_schedules`` 是 immutable schedule definition/current cursor
  真源：descriptor 七字段、payload schema/version/bytes/hash、cron/
  timezone/misfire policy/grace/deadline 全部注册后不可原地修改；
  只有 state/next_fire/version/updated_at 可由 app role 更新；
- ``job_schedule_occurrences`` 是 cursor 与 job enqueue 之间的 durable
  outbox：冻结完整 enqueue snapshot（扁平 nullable 列）、occurrence
  state、可空 job 绑定与 closed skip reason；``(tenant_id,
  idempotency_key)`` 在 snapshot 非空时唯一；
- 两表均 ``ENABLE + FORCE ROW LEVEL SECURITY``，唯一 policy 复用既有
  ``app.tenant_id`` expression；occurrence 以 ``(tenant_id,
  schedule_id)`` composite FK 指向 schedule、可空 job 以 ``(tenant_id,
  job_run_id)`` composite FK 指向 ``job_runs``，均 ``ON DELETE
  RESTRICT``；
- app role 权限最小化：SELECT/INSERT + 精确列级 UPDATE（schedule 只
  允许 state/next_fire/version/updated_at；occurrence 只允许
  state/job_run_id/skip_reason/updated_at），无 DELETE，snapshot/
  identity/content 列由列级 GRANT 与 immutable guard trigger 双重拒绝；
- DDL exact CHECK：pending/materializing 必须 ``job_run_id IS NULL AND
  skip_reason IS NULL`` 且 snapshot 完整；enqueued 必须 ``job_run_id
  IS NOT NULL AND skip_reason IS NULL`` 且 snapshot 完整；skipped 必须
  ``job_run_id IS NULL AND skip_reason IS NOT NULL``，其中
  ``schedule_disabled`` 保留完整 snapshot、其它 skip reason 必须
  snapshot 全 NULL；lookback/scan-limit 仅允许 ``coalesced_count IS
  NULL``，其它状态/reason 要求 exact nonnegative count。

downgrade 先拒绝已有业务行、app/audit role member 风险与两张表 owner
之外的外部依赖，再删 policies/grants/triggers/tables；保留
0001/0002/0003 对象、roles、default org 与 Alembic version table；
禁止 CASCADE。
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

revision = "0004_durable_schedules"
down_revision = "0003_durable_jobs"
branch_labels = None
depends_on = None

_TENANT_EXPRESSION = "nullif(current_setting('app.tenant_id', true), '')::uuid"
"""RLS tenant policy 使用的租户上下文表达式（与 0001/0002/0003 一致）。"""

_HEX64 = "'^[0-9a-f]{64}$'"
"""小写 64-hex SHA-256 的 CHECK 正则。"""

_TABLES = ("job_schedules", "job_schedule_occurrences")
"""两张 0004 表的依赖顺序（定义/删除共用）。"""

_SNAPSHOT_COLUMNS = (
    "snapshot_descriptor_job_type",
    "snapshot_descriptor_payload_schema_name",
    "snapshot_descriptor_payload_schema_version",
    "snapshot_descriptor_max_attempts",
    "snapshot_descriptor_retry_base_seconds",
    "snapshot_descriptor_retry_max_seconds",
    "snapshot_descriptor_lease_duration_seconds",
    "snapshot_payload_schema_name",
    "snapshot_payload_schema_version",
    "snapshot_payload_bytes",
    "snapshot_payload_sha256",
    "snapshot_idempotency_key",
    "snapshot_available_at",
    "snapshot_deadline_at",
    "snapshot_request_fingerprint",
)
"""occurrence 冻结 enqueue snapshot 的扁平可空列集合。"""


def _create_job_schedules() -> None:
    """创建 ``job_schedules`` 表及其全部约束与索引。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_schedules (
            id UUID CONSTRAINT pk_job_schedules PRIMARY KEY,
            tenant_id UUID NOT NULL,
            schedule_key TEXT NOT NULL,
            descriptor_job_type TEXT NOT NULL,
            descriptor_payload_schema_name TEXT NOT NULL,
            descriptor_payload_schema_version INTEGER NOT NULL,
            descriptor_max_attempts INTEGER NOT NULL,
            descriptor_retry_base_seconds INTEGER NOT NULL,
            descriptor_retry_max_seconds INTEGER NOT NULL,
            descriptor_lease_duration_seconds INTEGER NOT NULL,
            payload_schema_name TEXT NOT NULL,
            payload_schema_version INTEGER NOT NULL,
            payload_bytes BYTEA NOT NULL,
            payload_sha256 CHAR(64) NOT NULL,
            cron_expression TEXT NOT NULL,
            timezone_name TEXT NOT NULL,
            misfire_policy TEXT NOT NULL,
            misfire_grace_seconds INTEGER NOT NULL,
            job_deadline_seconds INTEGER NOT NULL,
            state TEXT NOT NULL,
            next_fire_at TIMESTAMPTZ NULL,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_job_schedules_tenant_id_organizations
                FOREIGN KEY (tenant_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_job_schedules_tenant_id_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_job_schedules_tenant_id_schedule_key
                UNIQUE (tenant_id, schedule_key),
            CONSTRAINT ck_job_schedules_schedule_key_nonempty
                CHECK (schedule_key <> '' AND schedule_key = trim(schedule_key)),
            CONSTRAINT ck_job_schedules_descriptor_job_type_nonempty
                CHECK (descriptor_job_type <> '' AND descriptor_job_type = trim(descriptor_job_type)),
            CONSTRAINT ck_job_schedules_descriptor_payload_schema_name_nonempty
                CHECK (
                    descriptor_payload_schema_name <> ''
                    AND descriptor_payload_schema_name = trim(descriptor_payload_schema_name)
                ),
            CONSTRAINT ck_job_schedules_descriptor_payload_schema_version_positive
                CHECK (descriptor_payload_schema_version > 0),
            CONSTRAINT ck_job_schedules_descriptor_max_attempts_positive
                CHECK (descriptor_max_attempts > 0),
            CONSTRAINT ck_job_schedules_descriptor_retry_base_seconds_positive
                CHECK (descriptor_retry_base_seconds > 0),
            CONSTRAINT ck_job_schedules_descriptor_retry_max_seconds_positive
                CHECK (descriptor_retry_max_seconds > 0),
            CONSTRAINT ck_job_schedules_descriptor_retry_max_ge_base
                CHECK (descriptor_retry_max_seconds >= descriptor_retry_base_seconds),
            CONSTRAINT ck_job_schedules_descriptor_lease_duration_seconds_positive
                CHECK (descriptor_lease_duration_seconds > 0),
            CONSTRAINT ck_job_schedules_payload_schema_name_nonempty
                CHECK (payload_schema_name <> '' AND payload_schema_name = trim(payload_schema_name)),
            CONSTRAINT ck_job_schedules_payload_schema_version_positive
                CHECK (payload_schema_version > 0),
            CONSTRAINT ck_job_schedules_payload_sha256_hex64
                CHECK (payload_sha256 ~ {_HEX64}),
            CONSTRAINT ck_job_schedules_cron_expression_nonempty
                CHECK (cron_expression <> '' AND cron_expression = trim(cron_expression)),
            CONSTRAINT ck_job_schedules_timezone_name_nonempty
                CHECK (timezone_name <> '' AND timezone_name = trim(timezone_name)),
            CONSTRAINT ck_job_schedules_misfire_policy_closed
                CHECK (misfire_policy IN ('coalesce_one')),
            CONSTRAINT ck_job_schedules_misfire_grace_seconds_positive
                CHECK (misfire_grace_seconds > 0),
            CONSTRAINT ck_job_schedules_job_deadline_seconds_positive
                CHECK (job_deadline_seconds > 0),
            CONSTRAINT ck_job_schedules_deadline_greater_than_grace
                CHECK (job_deadline_seconds > misfire_grace_seconds),
            CONSTRAINT ck_job_schedules_state_closed
                CHECK (state IN ('active', 'disabled')),
            CONSTRAINT ck_job_schedules_active_has_next_fire
                CHECK (state <> 'active' OR next_fire_at IS NOT NULL),
            CONSTRAINT ck_job_schedules_version_positive
                CHECK (version > 0)
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_job_schedules_due
        ON {PLATFORM_SCHEMA_NAME}.job_schedules (tenant_id, next_fire_at, id)
        WHERE state = 'active'
        """
    )


def _create_job_schedule_occurrences() -> None:
    """创建 ``job_schedule_occurrences`` 表及其全部约束与索引。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    snapshot_nullability = " AND ".join(f"{column} IS NULL" for column in _SNAPSHOT_COLUMNS)
    snapshot_present = " AND ".join(f"{column} IS NOT NULL" for column in _SNAPSHOT_COLUMNS)
    op.execute(
        f"""
        CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences (
            id UUID CONSTRAINT pk_job_schedule_occurrences PRIMARY KEY,
            tenant_id UUID NOT NULL,
            schedule_id UUID NOT NULL,
            schedule_version INTEGER NOT NULL,
            scheduled_for TIMESTAMPTZ NOT NULL,
            state TEXT NOT NULL,
            snapshot_descriptor_job_type TEXT NULL,
            snapshot_descriptor_payload_schema_name TEXT NULL,
            snapshot_descriptor_payload_schema_version INTEGER NULL,
            snapshot_descriptor_max_attempts INTEGER NULL,
            snapshot_descriptor_retry_base_seconds INTEGER NULL,
            snapshot_descriptor_retry_max_seconds INTEGER NULL,
            snapshot_descriptor_lease_duration_seconds INTEGER NULL,
            snapshot_payload_schema_name TEXT NULL,
            snapshot_payload_schema_version INTEGER NULL,
            snapshot_payload_bytes BYTEA NULL,
            snapshot_payload_sha256 CHAR(64) NULL,
            snapshot_idempotency_key TEXT NULL,
            snapshot_available_at TIMESTAMPTZ NULL,
            snapshot_deadline_at TIMESTAMPTZ NULL,
            snapshot_request_fingerprint CHAR(64) NULL,
            job_run_id UUID NULL,
            coalesced_count INTEGER NULL,
            skip_reason TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
            CONSTRAINT fk_job_schedule_occurrences_tenant_id_organizations
                FOREIGN KEY (tenant_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.organizations (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_schedule_occurrences_tenant_schedule_job_schedules
                FOREIGN KEY (tenant_id, schedule_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_schedules (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_schedule_occurrences_tenant_job_run_job_runs
                FOREIGN KEY (tenant_id, job_run_id)
                REFERENCES {PLATFORM_SCHEMA_NAME}.job_runs (tenant_id, id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_job_schedule_occurrences_tenant_id_id
                UNIQUE (tenant_id, id),
            CONSTRAINT uq_job_schedule_occurrences_tenant_schedule_fire
                UNIQUE (tenant_id, schedule_id, schedule_version, scheduled_for),
            CONSTRAINT ck_job_schedule_occurrences_schedule_version_positive
                CHECK (schedule_version > 0),
            CONSTRAINT ck_job_schedule_occurrences_state_closed
                CHECK (state IN ('pending', 'materializing', 'enqueued', 'skipped')),
            CONSTRAINT ck_job_schedule_occurrences_snapshot_present_or_null
                CHECK (
                    ({snapshot_present})
                    OR
                    ({snapshot_nullability})
                ),
            CONSTRAINT ck_job_schedule_occurrences_pending_materializing_clean
                CHECK (
                    state NOT IN ('pending', 'materializing')
                    OR (job_run_id IS NULL AND skip_reason IS NULL AND ({snapshot_present}))
                ),
            CONSTRAINT ck_job_schedule_occurrences_enqueued_bound
                CHECK (
                    state <> 'enqueued'
                    OR (job_run_id IS NOT NULL AND skip_reason IS NULL AND ({snapshot_present}))
                ),
            CONSTRAINT ck_job_schedule_occurrences_skipped_clean
                CHECK (
                    state <> 'skipped'
                    OR (job_run_id IS NULL AND skip_reason IS NOT NULL)
                ),
            CONSTRAINT ck_job_schedule_occurrences_skipped_disabled_keeps_snapshot
                CHECK (
                    state <> 'skipped' OR skip_reason <> 'schedule_disabled'
                    OR ({snapshot_present})
                ),
            CONSTRAINT ck_job_schedule_occurrences_skipped_audit_drops_snapshot
                CHECK (
                    state <> 'skipped' OR skip_reason IN ('schedule_disabled')
                    OR ({snapshot_nullability})
                ),
            CONSTRAINT ck_job_schedule_occurrences_skip_reason_closed
                CHECK (
                    skip_reason IS NULL
                    OR skip_reason IN ('misfire_expired', 'lookback_exceeded',
                                       'schedule_disabled', 'candidate_scan_limit_exceeded')
                ),
            CONSTRAINT ck_job_schedule_occurrences_coalesced_count_exact
                CHECK (
                    (state IN ('pending', 'materializing', 'enqueued')
                     AND coalesced_count IS NOT NULL)
                    OR
                    (state = 'skipped'
                     AND skip_reason IN ('misfire_expired', 'schedule_disabled')
                     AND coalesced_count IS NOT NULL)
                    OR
                    (state = 'skipped'
                     AND skip_reason IN ('lookback_exceeded',
                                         'candidate_scan_limit_exceeded')
                     AND coalesced_count IS NULL)
                ),
            CONSTRAINT ck_job_schedule_occurrences_coalesced_count_nonnegative
                CHECK (coalesced_count IS NULL OR coalesced_count >= 0),
            CONSTRAINT ck_job_schedule_occurrences_snapshot_fingerprint_hex64
                CHECK (snapshot_request_fingerprint IS NULL OR snapshot_request_fingerprint ~ {_HEX64}),
            CONSTRAINT ck_job_schedule_occurrences_snapshot_payload_sha256_hex64
                CHECK (snapshot_payload_sha256 IS NULL OR snapshot_payload_sha256 ~ {_HEX64}),
            CONSTRAINT ck_job_schedule_occurrences_snapshot_deadline_after_available
                CHECK (
                    snapshot_available_at IS NULL
                    OR (snapshot_deadline_at IS NOT NULL
                        AND snapshot_deadline_at > snapshot_available_at)
                ),
            CONSTRAINT ck_job_schedule_occurrences_snapshot_available_matches_fire
                CHECK (
                    snapshot_available_at IS NULL
                    OR snapshot_available_at = scheduled_for
                )
        )
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_job_schedule_occurrences_tenant_idempotency_key
        ON {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences (tenant_id, snapshot_idempotency_key)
        WHERE snapshot_idempotency_key IS NOT NULL
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_job_schedule_occurrences_replayable
        ON {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences (tenant_id, state, scheduled_for, id)
        """
    )


def _create_tables() -> None:
    """创建两张 0004 表及其全部约束与索引。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    _create_job_schedules()
    _create_job_schedule_occurrences()


def _grant_matrix() -> None:
    """清理 PUBLIC 并按最小权限矩阵授予 app/audit。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _TABLES:
        op.execute(f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} TO {PLATFORM_APP_ROLE}")
    _grant_column_level_updates()
    for table_name in _TABLES:
        op.execute(f"GRANT SELECT ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} TO {PLATFORM_AUDIT_ROLE}")


def _grant_column_level_updates() -> None:
    """为 app role 授予精确的列级 UPDATE 权限。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    op.execute(
        f"GRANT UPDATE (state, next_fire_at, version, updated_at) "
        f"ON TABLE {PLATFORM_SCHEMA_NAME}.job_schedules TO {PLATFORM_APP_ROLE}"
    )
    op.execute(
        f"GRANT UPDATE (state, job_run_id, skip_reason, updated_at) "
        f"ON TABLE {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences TO {PLATFORM_APP_ROLE}"
    )


def _create_immutable_guard_triggers() -> None:
    """为不可由 app 更新的 identity/snapshot/content 列创建双重拒绝 trigger。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    _create_guard(
        "job_schedules",
        (
            "id",
            "tenant_id",
            "schedule_key",
            "descriptor_job_type",
            "descriptor_payload_schema_name",
            "descriptor_payload_schema_version",
            "descriptor_max_attempts",
            "descriptor_retry_base_seconds",
            "descriptor_retry_max_seconds",
            "descriptor_lease_duration_seconds",
            "payload_schema_name",
            "payload_schema_version",
            "payload_bytes",
            "payload_sha256",
            "cron_expression",
            "timezone_name",
            "misfire_policy",
            "misfire_grace_seconds",
            "job_deadline_seconds",
            "created_at",
        ),
    )
    _create_guard(
        "job_schedule_occurrences",
        (
            "id",
            "tenant_id",
            "schedule_id",
            "schedule_version",
            "scheduled_for",
            "snapshot_descriptor_job_type",
            "snapshot_descriptor_payload_schema_name",
            "snapshot_descriptor_payload_schema_version",
            "snapshot_descriptor_max_attempts",
            "snapshot_descriptor_retry_base_seconds",
            "snapshot_descriptor_retry_max_seconds",
            "snapshot_descriptor_lease_duration_seconds",
            "snapshot_payload_schema_name",
            "snapshot_payload_schema_version",
            "snapshot_payload_bytes",
            "snapshot_payload_sha256",
            "snapshot_idempotency_key",
            "snapshot_available_at",
            "snapshot_deadline_at",
            "snapshot_request_fingerprint",
            "created_at",
        ),
    )


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

    comparisons = " OR ".join(f"OLD.{column} IS DISTINCT FROM NEW.{column}" for column in immutable_columns)
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
    """为两张表启用并强制 RLS，创建唯一 tenant_isolation policy。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _TABLES:
        op.execute(f"ALTER TABLE {PLATFORM_SCHEMA_NAME}.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {PLATFORM_SCHEMA_NAME}.{table_name}
            FOR ALL TO {PLATFORM_APP_ROLE}
            USING ({_TENANT_EXPRESSION} = tenant_id)
            WITH CHECK ({_TENANT_EXPRESSION} = tenant_id)
            """
        )


def _drop_policies() -> None:
    """删除两张表的 tenant_isolation policy。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {PLATFORM_SCHEMA_NAME}.{table_name}")


def _revoke_grants() -> None:
    """撤销 0004 表的 app/audit grants 并清理 PUBLIC。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _TABLES:
        op.execute(f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM {PLATFORM_APP_ROLE}")
        op.execute(f"REVOKE ALL ON TABLE {PLATFORM_SCHEMA_NAME}.{table_name} FROM {PLATFORM_AUDIT_ROLE}")


def _drop_triggers_and_functions() -> None:
    """删除 0004 的 guard trigger 与函数。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    for table_name in _TABLES:
        op.execute(f"DROP TRIGGER guard_{table_name}_immutable_columns_trigger ON {PLATFORM_SCHEMA_NAME}.{table_name}")
        op.execute(f"DROP FUNCTION {PLATFORM_SCHEMA_NAME}.guard_{table_name}_immutable_columns()")


def _0004_table_oids(bind: Connection) -> list[str]:
    """返回两张 0004 表在 ``dayu_platform`` schema 中的 OID 列表。

    Args:
        bind: Alembic 连接绑定。

    Returns:
        两张表的 ``pg_class.oid`` 字符串列表。

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
    """downgrade 破坏性 DDL 前的显式数据与依赖 preflight。

    在删除 0004 policy/grants/tables 之前，依次拒绝已有 schedule /
    occurrence 业务行、app/audit group role 的外部 member，以及任何
    非 0004 owner 的对象依赖（外部 view/rule 或其它表 FK）。任一命中
    都让整次 downgrade fail closed 并回滚。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 存在业务行、role member 或 0004 owner 之外的
            外部依赖时抛出；消息只描述违规类别，不包含
            DSN/credential。
    """

    bind = op.get_bind()
    table_oids = _0004_table_oids(bind)
    if not table_oids:
        return
    business_row_count = bind.execute(
        text(
            f"SELECT (SELECT count(*) FROM {PLATFORM_SCHEMA_NAME}.job_schedules) "
            f"+ (SELECT count(*) FROM {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences)"
        )
    ).scalar()
    if business_row_count and int(business_row_count) > 0:
        raise RuntimeError("downgrade 拒绝：0004 durable schedules 仍存在业务行，请先显式迁移或清理")
    group_placeholders = ", ".join(f"'{name}'" for name in (PLATFORM_APP_ROLE, PLATFORM_AUDIT_ROLE))
    member_count = bind.execute(
        text(
            "SELECT count(*) FROM pg_auth_members m "
            "JOIN pg_roles gr ON gr.oid = m.roleid "
            f"WHERE gr.rolname IN ({group_placeholders})"
        )
    ).scalar()
    if member_count and int(member_count) > 0:
        raise RuntimeError("downgrade 拒绝：platform app/audit role 仍存在外部 member，请先移除成员关系")
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
            "downgrade 拒绝：0004 durable schedules 存在 owner 之外的外部依赖（外部 view/rule 或其它表的 FK），请先清理"
        )


def _drop_tables() -> None:
    """按依赖顺序删除两张 0004 表（无 CASCADE）。

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
    """新增两张 durable schedule 表、RLS policy、trigger 与最小权限 grants。

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
    """精确回滚 0004 的 policy/triggers/grants/tables。

    在任何破坏性 DDL 前先执行 ``_downgrade_admission``：存在业务行、
    app/audit role member 或 0004 owner 之外的外部依赖时整次 fail
    closed 并回滚，保留 0001/0002/0003 的对象、roles、default org 与
    Alembic version table。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 存在业务行、role member 或外部依赖时抛出，
            整次回滚。
    """

    _downgrade_admission()
    _drop_policies()
    _drop_triggers_and_functions()
    _revoke_grants()
    _drop_tables()
