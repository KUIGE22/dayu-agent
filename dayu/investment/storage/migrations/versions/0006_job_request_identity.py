"""为 durable Job 增加不可变的原始请求身份。

Revision ID: 0006_job_request_identity
Revises: 0005_source_connectors_health
Create Date: 2026-08-14

本迁移保持 ``available_at`` 作为可变的重试 eligibility，同时把首次
enqueue 的时间与 payload schema 身份保存为不可变事实。非空库升级只
接受能够由现有 request fingerprint 逐字段证明的行；无法证明时整次
事务 fail closed。downgrade 只允许空 ``job_runs`` 且不存在外部依赖。
"""

from __future__ import annotations

import hashlib
import importlib
import json
from datetime import datetime, timedelta
from typing import NamedTuple, NoReturn, TypeAlias
from uuid import UUID

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection, Row

from dayu.investment.storage.db import (
    PLATFORM_APP_ROLE,
    PLATFORM_AUDIT_ROLE,
    PLATFORM_SCHEMA_NAME,
)

revision = "0006_job_request_identity"
down_revision = "0005_source_connectors_health"
branch_labels = None
depends_on = None

_SCHEMA = PLATFORM_SCHEMA_NAME
_JOB_TABLE = f"{_SCHEMA}.job_runs"
_DEFINITION_TABLE = f"{_SCHEMA}.job_definitions"
_HEX64 = frozenset("0123456789abcdef")

_IDENTITY_COLUMNS: tuple[str, ...] = (
    "original_available_at",
    "request_payload_schema_name",
    "request_payload_schema_version",
)
_CHECK_NAMES: tuple[str, ...] = (
    "ck_job_runs_original_deadline_after_available",
    "ck_job_runs_request_payload_schema_name_nonempty",
    "ck_job_runs_request_payload_schema_version_positive",
)
_FUNCTION_NAME = "guard_job_runs_request_identity_immutable"
_TRIGGER_NAME = "guard_job_runs_request_identity_immutable_trigger"
_OBJECT_NAMES: tuple[str, ...] = (*_CHECK_NAMES, _FUNCTION_NAME, _TRIGGER_NAME)
_EXPECTED_0005_TABLES: frozenset[str] = frozenset(
    {
        "organizations",
        "companies",
        "securities",
        "source_definitions",
        "users",
        "roles",
        "permissions",
        "user_roles",
        "role_permissions",
        "api_tokens",
        "source_subscriptions",
        "source_sync_runs",
        "source_health_snapshots",
        "source_sync_operations",
        "source_health_states",
        "source_health_alert_outbox",
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
)
_CHECK_EXPRESSIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (
            "ck_job_runs_original_deadline_after_available",
            "(deadline_at > original_available_at)",
        ),
        (
            "ck_job_runs_request_payload_schema_name_nonempty",
            "((request_payload_schema_name <> ''::text) AND "
            "(request_payload_schema_name = TRIM(BOTH FROM request_payload_schema_name)))",
        ),
        (
            "ck_job_runs_request_payload_schema_version_positive",
            "(request_payload_schema_version > 0)",
        ),
    }
)
_FUNCTION_BODY = (
    " BEGIN IF (OLD.original_available_at IS DISTINCT FROM NEW.original_available_at "
    "OR OLD.request_payload_schema_name IS DISTINCT FROM NEW.request_payload_schema_name "
    "OR OLD.request_payload_schema_version IS DISTINCT FROM NEW.request_payload_schema_version) "
    "THEN RAISE EXCEPTION 'immutable job request identity update rejected'; END IF; "
    "RETURN NEW; END; "
)
_BASELINE_COLUMNS: frozenset[tuple[str, str, str, str, str | None, str, str]] = frozenset(
    {
        *( ("job_definitions", name, data_type, nullable, default, "NO", "NEVER") for name, data_type, nullable, default in (
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
        )),
        *( ("job_runs", name, data_type, nullable, default, "NO", "NEVER") for name, data_type, nullable, default in (
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
        )),
    }
)
_BASELINE_CONSTRAINTS: frozenset[tuple[str, str, str, str]] = frozenset(
    {
        ("job_definitions", "pk_job_definitions", "p", "PRIMARY KEY (id)"),
        ("job_definitions", "uq_job_definitions_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("job_definitions", "uq_job_definitions_tenant_id_job_type", "u", "UNIQUE (tenant_id, job_type)"),
        ("job_definitions", "fk_job_definitions_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("job_definitions", "ck_job_definitions_job_type_nonempty", "c", "CHECK (((job_type <> ''::text) AND (job_type = TRIM(BOTH FROM job_type))))"),
        ("job_definitions", "ck_job_definitions_payload_schema_name_nonempty", "c", "CHECK (((payload_schema_name <> ''::text) AND (payload_schema_name = TRIM(BOTH FROM payload_schema_name))))"),
        ("job_definitions", "ck_job_definitions_payload_schema_version_positive", "c", "CHECK ((payload_schema_version > 0))"),
        ("job_definitions", "ck_job_definitions_max_attempts_positive", "c", "CHECK ((max_attempts > 0))"),
        ("job_definitions", "ck_job_definitions_retry_base_seconds_positive", "c", "CHECK ((retry_base_seconds > 0))"),
        ("job_definitions", "ck_job_definitions_retry_max_seconds_positive", "c", "CHECK ((retry_max_seconds > 0))"),
        ("job_definitions", "ck_job_definitions_retry_max_ge_base", "c", "CHECK ((retry_max_seconds >= retry_base_seconds))"),
        ("job_definitions", "ck_job_definitions_lease_duration_seconds_positive", "c", "CHECK ((lease_duration_seconds > 0))"),
        ("job_definitions", "ck_job_definitions_status_closed", "c", "CHECK ((status = ANY (ARRAY['active'::text, 'disabled'::text])))"),
        ("job_definitions", "ck_job_definitions_version_positive", "c", "CHECK ((version > 0))"),
        ("job_runs", "pk_job_runs", "p", "PRIMARY KEY (id)"),
        ("job_runs", "uq_job_runs_tenant_id_id", "u", "UNIQUE (tenant_id, id)"),
        ("job_runs", "uq_job_runs_tenant_definition_idempotency_key", "u", "UNIQUE (tenant_id, definition_id, idempotency_key)"),
        ("job_runs", "fk_job_runs_tenant_id_organizations", "f", "FOREIGN KEY (tenant_id) REFERENCES dayu_platform.organizations(id) ON DELETE RESTRICT"),
        ("job_runs", "fk_job_runs_tenant_definition_definitions", "f", "FOREIGN KEY (tenant_id, definition_id) REFERENCES dayu_platform.job_definitions(tenant_id, id) ON DELETE RESTRICT"),
        ("job_runs", "ck_job_runs_idempotency_key_nonempty", "c", "CHECK (((idempotency_key <> ''::text) AND (idempotency_key = TRIM(BOTH FROM idempotency_key))))"),
        ("job_runs", "ck_job_runs_request_fingerprint_hex64", "c", "CHECK ((request_fingerprint ~ '^[0-9a-f]{64}$'::text))"),
        ("job_runs", "ck_job_runs_payload_sha256_hex64", "c", "CHECK ((payload_sha256 ~ '^[0-9a-f]{64}$'::text))"),
        ("job_runs", "ck_job_runs_state_closed", "c", "CHECK ((state = ANY (ARRAY['ready'::text, 'leased'::text, 'cancel_requested'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text])))"),
        ("job_runs", "ck_job_runs_deadline_after_available", "c", "CHECK ((deadline_at > available_at))"),
        ("job_runs", "ck_job_runs_current_attempt_number_nonnegative", "c", "CHECK ((current_attempt_number >= 0))"),
        ("job_runs", "ck_job_runs_next_event_sequence_positive", "c", "CHECK ((next_event_sequence > 0))"),
        ("job_runs", "ck_job_runs_version_positive", "c", "CHECK ((version > 0))"),
    }
)
_BASELINE_INDEXES: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("job_definitions", "pk_job_definitions", "CREATE UNIQUE INDEX pk_job_definitions ON dayu_platform.job_definitions USING btree (id)"),
        ("job_definitions", "uq_job_definitions_tenant_id_id", "CREATE UNIQUE INDEX uq_job_definitions_tenant_id_id ON dayu_platform.job_definitions USING btree (tenant_id, id)"),
        ("job_definitions", "uq_job_definitions_tenant_id_job_type", "CREATE UNIQUE INDEX uq_job_definitions_tenant_id_job_type ON dayu_platform.job_definitions USING btree (tenant_id, job_type)"),
        ("job_runs", "ix_job_runs_cancel_recover", "CREATE INDEX ix_job_runs_cancel_recover ON dayu_platform.job_runs USING btree (tenant_id, state, deadline_at)"),
        ("job_runs", "ix_job_runs_claim_ready", "CREATE INDEX ix_job_runs_claim_ready ON dayu_platform.job_runs USING btree (tenant_id, available_at, id) WHERE (state = 'ready'::text)"),
        ("job_runs", "pk_job_runs", "CREATE UNIQUE INDEX pk_job_runs ON dayu_platform.job_runs USING btree (id)"),
        ("job_runs", "uq_job_runs_tenant_definition_idempotency_key", "CREATE UNIQUE INDEX uq_job_runs_tenant_definition_idempotency_key ON dayu_platform.job_runs USING btree (tenant_id, definition_id, idempotency_key)"),
        ("job_runs", "uq_job_runs_tenant_id_id", "CREATE UNIQUE INDEX uq_job_runs_tenant_id_id ON dayu_platform.job_runs USING btree (tenant_id, id)"),
    }
)
_BASELINE_GUARD_COLUMNS: dict[str, tuple[str, ...]] = {
    "job_definitions": (
        "id", "tenant_id", "job_type", "payload_schema_name", "payload_schema_version",
        "max_attempts", "retry_base_seconds", "retry_max_seconds", "lease_duration_seconds",
        "created_at",
    ),
    "job_runs": (
        "id", "tenant_id", "definition_id", "idempotency_key", "request_fingerprint",
        "payload_bytes", "payload_sha256", "deadline_at", "created_at",
    ),
}
_APP_JOB_RUN_UPDATE_COLUMNS: frozenset[str] = frozenset(
    {
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
    }
)
_APP_UPDATE_COLUMNS_BY_TABLE: dict[str, frozenset[str]] = {
    "job_definitions": frozenset({"status", "updated_at", "version"}),
    "job_runs": _APP_JOB_RUN_UPDATE_COLUMNS,
}
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {"password", "secret", "token", "authorization", "cookie", "api_key"}
)

JsonScalar: TypeAlias = None | bool | int | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
_RowValue: TypeAlias = str | int | datetime | bytes | memoryview | UUID | None
_MigrationRow: TypeAlias = Row[tuple[_RowValue, ...]]


class _CanonicalInvalid(ValueError):
    """迁移本地 canonical admission 的闭合失败类型。"""


class _CanonicalAdmission(NamedTuple):
    """迁移本地已验证的 canonical document 身份。"""

    schema_name: str
    schema_version: int
    canonical_bytes: bytes
    sha256: str


class _BackfillCandidate(NamedTuple):
    """Phase A 完整证明后才允许由 Phase B 写入的候选事实。"""

    tenant_id: UUID
    job_id: UUID
    original_available_at: datetime
    request_payload_schema_name: str
    request_payload_schema_version: int


def _invalid() -> NoReturn:
    """抛出不含业务值的 canonical admission 失败。

    Args:
        无。

    Returns:
        永不返回。

    Raises:
        _CanonicalInvalid: 恒抛。
    """

    raise _CanonicalInvalid("canonical payload invalid")


def _reject_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """拒绝重复 JSON object key。

    Args:
        pairs: ``json.loads`` 提供的有序键值对。

    Returns:
        无重复 key 的字典。

    Raises:
        _CanonicalInvalid: 发现重复 key 时抛出。
    """

    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _reject_nonfinite(_token: str) -> NoReturn:
    """拒绝 JSON ``NaN``/``Infinity`` 常量。

    Args:
        _token: parser 发现的非有限常量；其值不得进入错误消息。

    Returns:
        永不返回。

    Raises:
        _CanonicalInvalid: 恒抛。
    """

    _invalid()


def _validate_json_value(value: JsonValue) -> JsonValue:
    """递归验证 closed JSON primitive tree 与敏感键。

    Args:
        value: ``json.loads`` 结果。

    Returns:
        经过闭合集合验证的同值树。

    Raises:
        _CanonicalInvalid: 出现 float、未知容器、非字符串键或敏感键时抛出。
    """

    if value is None or type(value) is bool:
        return value
    if type(value) is int or type(value) is str:
        return value
    if type(value) is list:
        return [_validate_json_value(item) for item in value]
    if type(value) is dict:
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if type(key) is not str or key.lower() in _SENSITIVE_KEYS:
                _invalid()
            result[key] = _validate_json_value(item)
        return result
    _invalid()


def _parse_canonical_text(raw_bytes: bytes) -> bytes:
    """严格解析并重新编码 canonical JSON bytes。

    Args:
        raw_bytes: 数据库保存的原始 payload bytes。

    Returns:
        与输入逐字节相同的 canonical UTF-8 bytes。

    Raises:
        _CanonicalInvalid: UTF-8、JSON、闭合类型或 canonical identity 非法时抛出。
    """

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _invalid()
    try:
        parsed: JsonValue = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, _CanonicalInvalid, ValueError):
        _invalid()
    validated = _validate_json_value(parsed)
    canonical = json.dumps(
        validated,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if canonical != raw_bytes:
        _invalid()
    return canonical


def _admit_canonical_payload(
    raw_bytes: bytes,
    supplied_sha256: str,
    *,
    schema_name: str,
    schema_version: int,
) -> _CanonicalAdmission:
    """先验证 raw SHA，再执行迁移本地 canonical admission。

    Args:
        raw_bytes: 原始 payload bytes。
        supplied_sha256: 数据库保存的 payload SHA-256。
        schema_name: 候选 request payload schema 名。
        schema_version: 候选 request payload schema 版本。

    Returns:
        完整 canonical identity。

    Raises:
        _CanonicalInvalid: SHA、schema 或 canonical bytes 任一非法时抛出。
    """

    if (
        type(raw_bytes) is not bytes
        or type(supplied_sha256) is not str
        or len(supplied_sha256) != 64
        or any(character not in _HEX64 for character in supplied_sha256)
        or hashlib.sha256(raw_bytes).hexdigest() != supplied_sha256
        or type(schema_name) is not str
        or not schema_name
        or schema_name != schema_name.strip()
        or type(schema_version) is not int
        or schema_version <= 0
    ):
        _invalid()
    canonical = _parse_canonical_text(raw_bytes)
    return _CanonicalAdmission(
        schema_name=schema_name,
        schema_version=schema_version,
        canonical_bytes=canonical,
        sha256=supplied_sha256,
    )


def _require_aware_utc(value: datetime) -> datetime:
    """验证并返回 aware UTC datetime。

    Args:
        value: PostgreSQL TIMESTAMPTZ 值。

    Returns:
        原 datetime。

    Raises:
        RuntimeError: 值不是 aware UTC 时抛出。
    """

    if type(value) is not datetime or value.utcoffset() != timedelta(0):
        raise RuntimeError("0006 request identity 拒绝：timestamp 不是 aware UTC")
    return value


def _job_request_fingerprint(
    *,
    job_type: str,
    payload_schema_name: str,
    payload_schema_version: int,
    max_attempts: int,
    retry_base_seconds: int,
    retry_max_seconds: int,
    lease_duration_seconds: int,
    request_payload_schema_name: str,
    request_payload_schema_version: int,
    request_payload_sha256: str,
    available_at: datetime,
    deadline_at: datetime,
) -> str:
    """按 domain 真源逐 key 重算 enqueue request fingerprint。

    Args:
        job_type: Job 类型。
        payload_schema_name: Descriptor payload schema 名。
        payload_schema_version: Descriptor payload schema 版本。
        max_attempts: 最大 attempt 数。
        retry_base_seconds: 基础退避秒数。
        retry_max_seconds: 最大退避秒数。
        lease_duration_seconds: Lease 秒数。
        request_payload_schema_name: 原请求 payload schema 名。
        request_payload_schema_version: 原请求 payload schema 版本。
        request_payload_sha256: 原请求 payload SHA-256。
        available_at: 原请求可用时间。
        deadline_at: 原请求截止时间。

    Returns:
        小写 64-hex SHA-256；幂等键明确不参与。

    Raises:
        RuntimeError: 时间不是 aware UTC 时抛出。
    """

    original_available = _require_aware_utc(available_at)
    deadline = _require_aware_utc(deadline_at)
    canonical = json.dumps(
        {
            "available_at": original_available.isoformat(),
            "deadline_at": deadline.isoformat(),
            "job_type": job_type,
            "lease_duration_seconds": lease_duration_seconds,
            "max_attempts": max_attempts,
            "payload_schema_name": payload_schema_name,
            "payload_schema_version": payload_schema_version,
            "request_payload_schema_name": request_payload_schema_name,
            "request_payload_schema_version": request_payload_schema_version,
            "request_payload_sha256": request_payload_sha256,
            "retry_base_seconds": retry_base_seconds,
            "retry_max_seconds": retry_max_seconds,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scalar_int(bind: Connection, statement: str) -> int:
    """执行无外部输入的 catalog 标量查询。

    Args:
        bind: 当前 Alembic connection。
        statement: 受控 SQL。

    Returns:
        查询整数；NULL 归零。

    Raises:
        RuntimeError: 值不能转换为整数时抛出。
    """

    value = bind.execute(text(statement)).scalar()
    return 0 if value is None else int(value)


def _row_value(row: _MigrationRow, key: str) -> _RowValue:
    """读取 migration row 的闭合标量。

    Args:
        row: SQLAlchemy row。
        key: 列名。

    Returns:
        闭合集合内的 PostgreSQL 标量。

    Raises:
        RuntimeError: 列值类型超出闭合集合时抛出。
    """

    value = row._mapping[key]
    if value is None or isinstance(value, (str, int, datetime, bytes, memoryview, UUID)):
        return value
    raise RuntimeError("0006 request identity 拒绝：持久化行类型非法")


def _row_text(row: _MigrationRow, key: str) -> str:
    """读取严格文本列。

    Args:
        row: SQLAlchemy row。
        key: 列名。

    Returns:
        文本值。

    Raises:
        RuntimeError: 值不是字符串时抛出。
    """

    value = _row_value(row, key)
    if type(value) is not str:
        raise RuntimeError("0006 request identity 拒绝：持久化文本非法")
    return value


def _row_int(row: _MigrationRow, key: str) -> int:
    """读取严格整数列。

    Args:
        row: SQLAlchemy row。
        key: 列名。

    Returns:
        整数值。

    Raises:
        RuntimeError: 值不是严格整数时抛出。
    """

    value = _row_value(row, key)
    if type(value) is not int:
        raise RuntimeError("0006 request identity 拒绝：持久化整数非法")
    return value


def _row_uuid(row: _MigrationRow, key: str) -> UUID:
    """读取 UUID 列。

    Args:
        row: SQLAlchemy row。
        key: 列名。

    Returns:
        UUID 值。

    Raises:
        RuntimeError: 值不能安全规范为 UUID 时抛出。
    """

    value = _row_value(row, key)
    try:
        return value if type(value) is UUID else UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise RuntimeError("0006 request identity 拒绝：持久化 UUID 非法") from None


def _row_datetime(row: _MigrationRow, key: str) -> datetime:
    """读取 aware UTC datetime 列。

    Args:
        row: SQLAlchemy row。
        key: 列名。

    Returns:
        aware UTC datetime。

    Raises:
        RuntimeError: 值不是 aware UTC datetime 时抛出。
    """

    value = _row_value(row, key)
    if type(value) is not datetime:
        raise RuntimeError("0006 request identity 拒绝：持久化 timestamp 非法")
    return _require_aware_utc(value)


def _row_bytes(row: _MigrationRow, key: str) -> bytes:
    """读取 BYTEA 并规范为不可变 bytes。

    Args:
        row: SQLAlchemy row。
        key: 列名。

    Returns:
        不可变 bytes。

    Raises:
        RuntimeError: 值不是 bytes/memoryview 时抛出。
    """

    value = _row_value(row, key)
    if type(value) is bytes:
        return value
    if type(value) is memoryview:
        return value.tobytes()
    raise RuntimeError("0006 request identity 拒绝：payload bytes 非法")


def _assert_security_exact(bind: Connection) -> None:
    """验证两个0006 affected Job表的owner/RLS/policy/ACL exact manifest。

    Args:
        bind: 当前 Alembic connection。

    Returns:
        无。

    Raises:
        RuntimeError: 任一安全身份漂移时抛出。
    """

    current_user = str(bind.execute(text("SELECT current_user")).scalar_one())
    relation_rows = {
        (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            bool(row[3]),
            bool(row[4]),
            str(row[5]),
            bool(row[6]),
        )
        for row in bind.execute(
            text(
                "SELECT relation.relname, owner_role.rolname, relation.relkind, "
                "relation.relrowsecurity, relation.relforcerowsecurity, "
                "relation.relpersistence, relation.relispartition FROM pg_class relation "
                "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
                "JOIN pg_roles owner_role ON owner_role.oid=relation.relowner "
                f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
                "('job_definitions','job_runs') AND relation.relkind='r'"
            )
        ).fetchall()
    }
    if relation_rows != {
        (table_name, current_user, "r", True, True, "p", False)
        for table_name in _APP_UPDATE_COLUMNS_BY_TABLE
    }:
        raise RuntimeError("0006 catalog 拒绝：affected Job table owner/RLS 漂移")
    tenant_expression = (
        "((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid = tenant_id)"
    )
    policies = {
        tuple(str(value) for value in row)
        for row in bind.execute(
            text(
                "SELECT tablename, policyname, permissive, cmd, roles::text, qual, with_check "
                "FROM pg_policies "
                f"WHERE schemaname='{_SCHEMA}' AND tablename IN "
                "('job_definitions','job_runs')"
            )
        ).fetchall()
    }
    expected_policies = {
        (
            table_name,
            "tenant_isolation",
            "PERMISSIVE",
            "ALL",
            f"{{{PLATFORM_APP_ROLE}}}",
            tenant_expression,
            tenant_expression,
        )
        for table_name in _APP_UPDATE_COLUMNS_BY_TABLE
    }
    if policies != expected_policies:
        raise RuntimeError("0006 catalog 拒绝：affected Job tenant policy 漂移")
    table_acl = {
        (str(row[0]), str(row[1]), str(row[2]), bool(row[3]))
        for row in bind.execute(
            text(
                "SELECT relation.relname, CASE WHEN acl.grantee=0 THEN 'PUBLIC' "
                "ELSE role.rolname END, "
                "acl.privilege_type, acl.is_grantable FROM pg_class relation "
                "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
                "CROSS JOIN LATERAL aclexplode(relation.relacl) acl "
                "LEFT JOIN pg_roles role ON role.oid=acl.grantee "
                f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
                "('job_definitions','job_runs')"
            )
        ).fetchall()
    }
    owner_privileges = {"DELETE", "INSERT", "REFERENCES", "SELECT", "TRIGGER", "TRUNCATE", "UPDATE"}
    expected_table_acl = {
        (table_name, current_user, privilege, False)
        for table_name in _APP_UPDATE_COLUMNS_BY_TABLE
        for privilege in owner_privileges
    } | {
        (table_name, role_name, privilege, False)
        for table_name in _APP_UPDATE_COLUMNS_BY_TABLE
        for role_name, privilege in (
            (PLATFORM_APP_ROLE, "INSERT"),
            (PLATFORM_APP_ROLE, "SELECT"),
            (PLATFORM_AUDIT_ROLE, "SELECT"),
        )
    }
    if table_acl != expected_table_acl:
        raise RuntimeError("0006 catalog 拒绝：affected Job table ACL 漂移")
    column_acl = {
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]), bool(row[4]))
        for row in bind.execute(
            text(
                "SELECT relation.relname, attribute.attname, role.rolname, "
                "acl.privilege_type, acl.is_grantable "
                "FROM pg_class relation JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
                "JOIN pg_attribute attribute ON attribute.attrelid=relation.oid "
                "AND attribute.attnum>0 AND NOT attribute.attisdropped "
                "CROSS JOIN LATERAL aclexplode(attribute.attacl) acl "
                "JOIN pg_roles role ON role.oid=acl.grantee "
                f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
                "('job_definitions','job_runs')"
            )
        ).fetchall()
    }
    expected_column_acl = {
        (table_name, column, PLATFORM_APP_ROLE, "UPDATE", False)
        for table_name, columns in _APP_UPDATE_COLUMNS_BY_TABLE.items()
        for column in columns
    }
    if column_acl != expected_column_acl:
        raise RuntimeError("0006 catalog 拒绝：affected Job column ACL 漂移")


def _assert_baseline_job_catalog_exact(bind: Connection) -> None:
    """精确验证0006受影响的0003 Job definition/run物理目录。

    Args:
        bind: 当前 Alembic connection。

    Returns:
        无。

    Raises:
        RuntimeError: 任一列、constraint、index或既有guard漂移时抛出。
    """

    columns = {
        tuple(row)
        for row in bind.execute(
            text(
                "SELECT relation.relname, attribute.attname, "
                "pg_catalog.format_type(attribute.atttypid, attribute.atttypmod), "
                "CASE WHEN attribute.attnotnull THEN 'NO' ELSE 'YES' END, "
                "pg_catalog.pg_get_expr(default_value.adbin, default_value.adrelid), "
                "CASE WHEN attribute.attidentity='' THEN 'NO' ELSE 'YES' END, "
                "CASE WHEN attribute.attgenerated='' THEN 'NEVER' ELSE 'ALWAYS' END "
                "FROM pg_attribute attribute JOIN pg_class relation "
                "ON relation.oid=attribute.attrelid JOIN pg_namespace namespace "
                "ON namespace.oid=relation.relnamespace LEFT JOIN pg_attrdef default_value "
                "ON default_value.adrelid=attribute.attrelid "
                "AND default_value.adnum=attribute.attnum "
                f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
                "('job_definitions','job_runs') AND relation.relkind='r' "
                "AND attribute.attnum>0 AND NOT attribute.attisdropped"
            )
        ).fetchall()
    }
    if columns != _BASELINE_COLUMNS:
        raise RuntimeError("0006 拒绝：affected Job column exact manifest 漂移")
    constraints = {
        tuple(row)
        for row in bind.execute(
            text(
                "SELECT relation.relname, constraint_owner.conname, "
                "constraint_owner.contype, pg_get_constraintdef(constraint_owner.oid) "
                "FROM pg_constraint constraint_owner JOIN pg_class relation "
                "ON relation.oid=constraint_owner.conrelid JOIN pg_namespace namespace "
                "ON namespace.oid=relation.relnamespace "
                f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
                "('job_definitions','job_runs')"
            )
        ).fetchall()
    }
    if constraints != _BASELINE_CONSTRAINTS:
        raise RuntimeError("0006 拒绝：affected Job constraint exact manifest 漂移")
    invalid_foreign_keys = {
        (str(row[0]), str(row[1]))
        for row in bind.execute(
            text(
                "SELECT relation.relname, constraint_owner.conname "
                "FROM pg_constraint constraint_owner JOIN pg_class relation "
                "ON relation.oid=constraint_owner.conrelid JOIN pg_namespace namespace "
                "ON namespace.oid=relation.relnamespace "
                f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
                "('job_definitions','job_runs') AND constraint_owner.contype='f' "
                "AND (constraint_owner.confdeltype<>'r' OR NOT constraint_owner.convalidated "
                "OR constraint_owner.condeferrable OR constraint_owner.condeferred)"
            )
        ).fetchall()
    }
    if invalid_foreign_keys:
        raise RuntimeError("0006 拒绝：affected Job FK action/validation 漂移")
    indexes = {
        tuple(row)
        for row in bind.execute(
            text(
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                f"WHERE schemaname='{_SCHEMA}' AND tablename IN "
                "('job_definitions','job_runs')"
            )
        ).fetchall()
    }
    if indexes != _BASELINE_INDEXES:
        raise RuntimeError("0006 拒绝：affected Job index exact manifest 漂移")
    owner_name = str(bind.execute(text("SELECT current_user")).scalar_one())
    function_rows = bind.execute(
        text(
            "SELECT function_owner.proname, pg_get_function_arguments(function_owner.oid), "
            "pg_get_function_result(function_owner.oid), language.lanname, "
            "function_owner.provolatile, function_owner.prosecdef, function_owner.proleakproof, "
            "function_owner.proisstrict, function_owner.proparallel, function_owner.proretset, "
            "function_owner.pronargs, function_owner.proargtypes::text, function_owner.procost, "
            "function_owner.prorows, function_owner.prosupport::regproc::text, "
            "function_owner.prokind, function_owner.proconfig, function_owner.prosrc, "
            "owner_role.rolname FROM pg_proc function_owner JOIN pg_namespace namespace "
            "ON namespace.oid=function_owner.pronamespace JOIN pg_language language "
            "ON language.oid=function_owner.prolang JOIN pg_roles owner_role "
            "ON owner_role.oid=function_owner.proowner "
            f"WHERE namespace.nspname='{_SCHEMA}' AND function_owner.proname IN "
            "('guard_job_definitions_immutable_columns','guard_job_runs_immutable_columns')"
        )
    ).fetchall()
    if len(function_rows) != len(_BASELINE_GUARD_COLUMNS):
        raise RuntimeError("0006 拒绝：affected Job guard function count 漂移")
    for row in function_rows:
        function_name = str(row[0])
        table_name = function_name.removeprefix("guard_").removesuffix(
            "_immutable_columns"
        )
        immutable_columns = _BASELINE_GUARD_COLUMNS.get(table_name)
        if immutable_columns is None:
            raise RuntimeError("0006 拒绝：affected Job guard function identity 漂移")
        comparisons = " OR ".join(
            f"OLD.{column} IS DISTINCT FROM NEW.{column}"
            for column in immutable_columns
        )
        expected_body = (
            f"BEGIN IF ({comparisons}) THEN RAISE EXCEPTION "
            f"'immutable column update rejected on {table_name}'; END IF; "
            "RETURN NEW; END;"
        )
        actual_body = " ".join(str(row[17]).split())
        if tuple(row[1:17]) != (
            "",
            "trigger",
            "plpgsql",
            "v",
            False,
            False,
            False,
            "u",
            False,
            0,
            "",
            100.0,
            0.0,
            "-",
            "f",
            None,
        ):
            raise RuntimeError("0006 拒绝：affected Job guard function shape 漂移")
        if actual_body != expected_body or str(row[18]) != owner_name:
            raise RuntimeError("0006 拒绝：affected Job guard function body/owner 漂移")
    function_acl = {
        (str(row[0]), str(row[1]), str(row[2]), bool(row[3]))
        for row in bind.execute(
            text(
                "SELECT function_owner.proname, CASE WHEN acl.grantee=0 THEN 'PUBLIC' "
                "ELSE role.rolname END, acl.privilege_type, acl.is_grantable "
                "FROM pg_proc function_owner JOIN pg_namespace namespace "
                "ON namespace.oid=function_owner.pronamespace "
                "CROSS JOIN LATERAL aclexplode(COALESCE(function_owner.proacl, "
                "acldefault('f', function_owner.proowner))) acl "
                "LEFT JOIN pg_roles role ON role.oid=acl.grantee "
                f"WHERE namespace.nspname='{_SCHEMA}' AND function_owner.proname IN "
                "('guard_job_definitions_immutable_columns','guard_job_runs_immutable_columns')"
            )
        ).fetchall()
    }
    expected_function_acl = {
        (f"guard_{table_name}_immutable_columns", role_name, "EXECUTE", False)
        for table_name in _BASELINE_GUARD_COLUMNS
        for role_name in ("PUBLIC", owner_name)
    }
    if function_acl != expected_function_acl:
        raise RuntimeError("0006 拒绝：affected Job guard function ACL 漂移")
    trigger_rows = {
        tuple(row)
        for row in bind.execute(
            text(
                "SELECT relation.relname, trigger_owner.tgname, trigger_owner.tgtype, "
                "trigger_owner.tgenabled, trigger_owner.tgisinternal, "
                "trigger_owner.tgdeferrable, trigger_owner.tginitdeferred, "
                "function_owner.proname, function_namespace.nspname, "
                "pg_get_triggerdef(trigger_owner.oid, true) FROM pg_trigger trigger_owner "
                "JOIN pg_class relation ON relation.oid=trigger_owner.tgrelid "
                "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
                "JOIN pg_proc function_owner ON function_owner.oid=trigger_owner.tgfoid "
                "JOIN pg_namespace function_namespace "
                "ON function_namespace.oid=function_owner.pronamespace "
                f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
                "('job_definitions','job_runs') AND NOT trigger_owner.tgisinternal"
            )
        ).fetchall()
    }
    expected_triggers = {
        (
            table_name,
            f"guard_{table_name}_immutable_columns_trigger",
            19,
            "O",
            False,
            False,
            False,
            f"guard_{table_name}_immutable_columns",
            _SCHEMA,
            f"CREATE TRIGGER guard_{table_name}_immutable_columns_trigger "
            f"BEFORE UPDATE ON {_SCHEMA}.{table_name} FOR EACH ROW EXECUTE FUNCTION "
            f"{_SCHEMA}.guard_{table_name}_immutable_columns()",
        )
        for table_name in _BASELINE_GUARD_COLUMNS
    }
    if trigger_rows != expected_triggers:
        raise RuntimeError("0006 拒绝：affected Job guard trigger exact manifest 漂移")


def _assert_0005_catalog(
    *,
    require_identity_absent: bool,
    require_revision_0005: bool = True,
) -> None:
    """验证受0006影响的exact 0005 catalog 与当前revision。

    Args:
        require_identity_absent: 是否要求三列/五对象全部不存在。
        require_revision_0005: 是否要求 Alembic 尚处于0005；downgrade
            函数返回前 version table 仍为0006，终态catalog检查须关闭此项。

    Returns:
        无。

    Raises:
        RuntimeError: revision、27-table baseline 或受影响对象漂移时抛出。
    """

    bind = op.get_bind()
    revision_value = bind.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if require_revision_0005 and revision_value != down_revision:
        raise RuntimeError("0006 拒绝：Alembic baseline 不是 0005_source_connectors_health")
    table_names = {
        str(row[0])
        for row in bind.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema='{_SCHEMA}'"
            )
        ).fetchall()
    }
    if table_names != _EXPECTED_0005_TABLES:
        raise RuntimeError("0006 拒绝：exact 0005 table manifest 漂移")
    source_health_migration = importlib.import_module(
        "dayu.investment.storage.migrations.versions.0005_source_connectors_health"
    )
    source_health_migration._assert_0005_catalog()
    _assert_baseline_job_catalog_exact(bind)
    if _scalar_int(
        bind,
        "SELECT count(*) FROM pg_constraint constraint_owner "
        "JOIN pg_namespace namespace ON namespace.oid=constraint_owner.connamespace "
        f"WHERE namespace.nspname='{_SCHEMA}' AND constraint_owner.conname="
        "'uq_job_attempts_tenant_job_run_id_v2' AND constraint_owner.contype='u'",
    ) != 1:
        raise RuntimeError("0006 拒绝：0005 parent unique 漂移")
    _assert_security_exact(bind)
    if not require_identity_absent:
        return
    column_literals = ",".join(repr(name) for name in _IDENTITY_COLUMNS)
    if _scalar_int(
        bind,
        "SELECT count(*) FROM information_schema.columns "
        f"WHERE table_schema='{_SCHEMA}' AND table_name='job_runs' "
        f"AND column_name IN ({column_literals})",
    ) != 0:
        raise RuntimeError("0006 拒绝：request identity 列已存在")
    object_literals = ",".join(repr(name) for name in _OBJECT_NAMES)
    collision_count = _scalar_int(
        bind,
        "SELECT (SELECT count(*) FROM pg_constraint constraint_owner "
        "JOIN pg_namespace namespace ON namespace.oid=constraint_owner.connamespace "
        f"WHERE namespace.nspname='{_SCHEMA}' AND constraint_owner.conname IN ({object_literals})) + "
        "(SELECT count(*) FROM pg_proc function_owner JOIN pg_namespace namespace "
        "ON namespace.oid=function_owner.pronamespace "
        f"WHERE namespace.nspname='{_SCHEMA}' AND function_owner.proname IN ({object_literals})) + "
        "(SELECT count(*) FROM pg_trigger trigger_owner JOIN pg_class relation "
        "ON relation.oid=trigger_owner.tgrelid JOIN pg_namespace namespace "
        "ON namespace.oid=relation.relnamespace "
        f"WHERE namespace.nspname='{_SCHEMA}' AND NOT trigger_owner.tgisinternal "
        f"AND trigger_owner.tgname IN ({object_literals}))",
    )
    if collision_count != 0:
        raise RuntimeError("0006 拒绝：request identity object 已存在")


def _lock_identity_tables() -> None:
    """按 job_runs -> job_definitions 顺序取得 NOWAIT exclusive locks。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 任一锁不可用时立即向外传播。
    """

    op.execute(f"LOCK TABLE {_JOB_TABLE} IN ACCESS EXCLUSIVE MODE NOWAIT")
    op.execute(f"LOCK TABLE {_DEFINITION_TABLE} IN ACCESS EXCLUSIVE MODE NOWAIT")


def _backfill_rows() -> None:
    """以 proof-only 两阶段算法 backfill 三个request identity列。

    Phase A验证全表并只在内存形成候选；任何行失败前绝不UPDATE。Phase B
    才写候选，随后再次逐行复核，避免partial proof。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: 行缺失definition、canonical或fingerprint无法证明时抛出。
    """

    bind = op.get_bind()
    rows = bind.execute(
        text(
            f"SELECT job.tenant_id, job.id AS job_id, job.request_fingerprint, "
            "job.payload_bytes, job.payload_sha256, job.available_at, job.deadline_at, "
            "definition.job_type, definition.payload_schema_name, "
            "definition.payload_schema_version, definition.max_attempts, "
            "definition.retry_base_seconds, definition.retry_max_seconds, "
            "definition.lease_duration_seconds, definition.id AS matched_definition_id "
            f"FROM {_JOB_TABLE} job LEFT JOIN {_DEFINITION_TABLE} definition "
            "ON definition.tenant_id=job.tenant_id AND definition.id=job.definition_id "
            "ORDER BY job.tenant_id, job.id"
        )
    ).fetchall()
    if len(rows) != _scalar_int(bind, f"SELECT count(*) FROM {_JOB_TABLE}"):
        raise RuntimeError("0006 backfill 拒绝：Job全表读取计数漂移")
    candidates: list[_BackfillCandidate] = []
    for raw_row in rows:
        row: _MigrationRow = raw_row
        if _row_value(row, "matched_definition_id") is None:
            raise RuntimeError("0006 backfill 拒绝：Job definition lineage 缺失")
        raw_bytes = _row_bytes(row, "payload_bytes")
        payload_sha = _row_text(row, "payload_sha256")
        schema_name = _row_text(row, "payload_schema_name")
        schema_version = _row_int(row, "payload_schema_version")
        try:
            admission = _admit_canonical_payload(
                raw_bytes,
                payload_sha,
                schema_name=schema_name,
                schema_version=schema_version,
            )
        except _CanonicalInvalid:
            raise RuntimeError("0006 backfill 拒绝：payload canonical identity 无法证明") from None
        available_at = _row_datetime(row, "available_at")
        deadline_at = _row_datetime(row, "deadline_at")
        reproduced = _job_request_fingerprint(
            job_type=_row_text(row, "job_type"),
            payload_schema_name=schema_name,
            payload_schema_version=schema_version,
            max_attempts=_row_int(row, "max_attempts"),
            retry_base_seconds=_row_int(row, "retry_base_seconds"),
            retry_max_seconds=_row_int(row, "retry_max_seconds"),
            lease_duration_seconds=_row_int(row, "lease_duration_seconds"),
            request_payload_schema_name=admission.schema_name,
            request_payload_schema_version=admission.schema_version,
            request_payload_sha256=admission.sha256,
            available_at=available_at,
            deadline_at=deadline_at,
        )
        if reproduced != _row_text(row, "request_fingerprint"):
            raise RuntimeError("0006 backfill 拒绝：原请求身份无法由fingerprint证明")
        candidates.append(
            _BackfillCandidate(
                tenant_id=_row_uuid(row, "tenant_id"),
                job_id=_row_uuid(row, "job_id"),
                original_available_at=available_at,
                request_payload_schema_name=admission.schema_name,
                request_payload_schema_version=admission.schema_version,
            )
        )
    for candidate in candidates:
        result = bind.execute(
            text(
                f"UPDATE {_JOB_TABLE} SET original_available_at=:original_available_at, "
                "request_payload_schema_name=:request_payload_schema_name, "
                "request_payload_schema_version=:request_payload_schema_version "
                "WHERE tenant_id=:tenant_id AND id=:job_id "
                "AND original_available_at IS NULL "
                "AND request_payload_schema_name IS NULL "
                "AND request_payload_schema_version IS NULL"
            ),
            {
                "tenant_id": candidate.tenant_id,
                "job_id": candidate.job_id,
                "original_available_at": candidate.original_available_at,
                "request_payload_schema_name": candidate.request_payload_schema_name,
                "request_payload_schema_version": candidate.request_payload_schema_version,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError("0006 backfill 拒绝：identity write cardinality 漂移")
    verified = bind.execute(
        text(
            f"SELECT job.tenant_id, job.id AS job_id, job.request_fingerprint, "
            "job.payload_bytes, job.payload_sha256, job.original_available_at AS available_at, "
            "job.deadline_at, job.request_payload_schema_name, job.request_payload_schema_version, "
            "definition.job_type, definition.payload_schema_name, definition.payload_schema_version, "
            "definition.max_attempts, definition.retry_base_seconds, definition.retry_max_seconds, "
            f"definition.lease_duration_seconds FROM {_JOB_TABLE} job "
            f"JOIN {_DEFINITION_TABLE} definition ON definition.tenant_id=job.tenant_id "
            "AND definition.id=job.definition_id ORDER BY job.tenant_id, job.id"
        )
    ).fetchall()
    if len(verified) != len(candidates):
        raise RuntimeError("0006 backfill 拒绝：post-write row count 漂移")
    for raw_row in verified:
        row: _MigrationRow = raw_row
        request_schema_name = _row_text(row, "request_payload_schema_name")
        request_schema_version = _row_int(row, "request_payload_schema_version")
        try:
            admission = _admit_canonical_payload(
                _row_bytes(row, "payload_bytes"),
                _row_text(row, "payload_sha256"),
                schema_name=request_schema_name,
                schema_version=request_schema_version,
            )
        except _CanonicalInvalid:
            raise RuntimeError("0006 backfill 拒绝：post-write canonical identity 漂移") from None
        reproduced = _job_request_fingerprint(
            job_type=_row_text(row, "job_type"),
            payload_schema_name=_row_text(row, "payload_schema_name"),
            payload_schema_version=_row_int(row, "payload_schema_version"),
            max_attempts=_row_int(row, "max_attempts"),
            retry_base_seconds=_row_int(row, "retry_base_seconds"),
            retry_max_seconds=_row_int(row, "retry_max_seconds"),
            lease_duration_seconds=_row_int(row, "lease_duration_seconds"),
            request_payload_schema_name=admission.schema_name,
            request_payload_schema_version=admission.schema_version,
            request_payload_sha256=admission.sha256,
            available_at=_row_datetime(row, "available_at"),
            deadline_at=_row_datetime(row, "deadline_at"),
        )
        if reproduced != _row_text(row, "request_fingerprint"):
            raise RuntimeError("0006 backfill 拒绝：post-write fingerprint 漂移")


def _install_identity_contract() -> None:
    """安装NOT NULL、三个CHECK与独立immutable guard。

    Args:
        无。

    Returns:
        无。

    Raises:
        SQLAlchemyError: 任一DDL失败时向外传播。
    """

    op.execute(
        f"ALTER TABLE {_JOB_TABLE} "
        "ALTER COLUMN original_available_at SET NOT NULL, "
        "ALTER COLUMN request_payload_schema_name SET NOT NULL, "
        "ALTER COLUMN request_payload_schema_version SET NOT NULL, "
        "ADD CONSTRAINT ck_job_runs_original_deadline_after_available "
        "CHECK (deadline_at > original_available_at), "
        "ADD CONSTRAINT ck_job_runs_request_payload_schema_name_nonempty "
        "CHECK (request_payload_schema_name <> '' AND "
        "request_payload_schema_name = trim(request_payload_schema_name)), "
        "ADD CONSTRAINT ck_job_runs_request_payload_schema_version_positive "
        "CHECK (request_payload_schema_version > 0)"
    )
    op.execute(
        f"CREATE FUNCTION {_SCHEMA}.{_FUNCTION_NAME}() RETURNS trigger AS $${_FUNCTION_BODY}$$ "
        "LANGUAGE plpgsql"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_SCHEMA}.{_FUNCTION_NAME}() FROM PUBLIC")
    op.execute(
        f"CREATE TRIGGER {_TRIGGER_NAME} BEFORE UPDATE ON {_JOB_TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION {_SCHEMA}.{_FUNCTION_NAME}()"
    )


def _assert_0006_catalog(*, expected_revision: str) -> None:
    """验证0006三列、五对象与安全身份exact终态。

    Args:
        expected_revision: Alembic在当前migration函数内应仍持有的revision。

    Returns:
        无。

    Raises:
        RuntimeError: 任一catalog、ACL或RLS事实漂移时抛出。
    """

    bind = op.get_bind()
    revision_value = bind.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if revision_value != expected_revision:
        raise RuntimeError("0006 catalog self-check：Alembic revision 漂移")
    columns = {
        (str(row[0]), str(row[1]), str(row[2]), row[3])
        for row in bind.execute(
            text(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                f"WHERE table_schema='{_SCHEMA}' AND table_name='job_runs' "
                "AND column_name IN ('original_available_at', 'request_payload_schema_name', "
                "'request_payload_schema_version')"
            )
        ).fetchall()
    }
    if columns != {
        ("original_available_at", "timestamp with time zone", "NO", None),
        ("request_payload_schema_name", "text", "NO", None),
        ("request_payload_schema_version", "integer", "NO", None),
    }:
        raise RuntimeError("0006 catalog self-check：identity column shape 漂移")
    checks = {
        tuple(row)
        for row in bind.execute(
            text(
                "SELECT constraint_owner.conname, constraint_owner.contype, "
                "pg_get_expr(constraint_owner.conbin, constraint_owner.conrelid), "
                "constraint_owner.convalidated, constraint_owner.connoinherit, "
                "constraint_owner.condeferrable, constraint_owner.condeferred "
                "FROM pg_constraint constraint_owner JOIN pg_class relation "
                "ON relation.oid=constraint_owner.conrelid JOIN pg_namespace namespace "
                "ON namespace.oid=relation.relnamespace "
                f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname='job_runs' "
                "AND constraint_owner.conname IN ('ck_job_runs_original_deadline_after_available', "
                "'ck_job_runs_request_payload_schema_name_nonempty', "
                "'ck_job_runs_request_payload_schema_version_positive')"
            )
        ).fetchall()
    }
    if checks != {
        (name, "c", expression, True, False, False, False)
        for name, expression in _CHECK_EXPRESSIONS
    }:
        raise RuntimeError("0006 catalog self-check：CHECK manifest 漂移")
    owner_name = str(bind.execute(text("SELECT current_user")).scalar_one())
    function_rows = {
        tuple(row)
        for row in bind.execute(
            text(
                "SELECT pg_get_function_arguments(function_owner.oid), "
                "pg_get_function_result(function_owner.oid), language.lanname, "
                "function_owner.provolatile, function_owner.prosecdef, function_owner.proleakproof, "
                "function_owner.proisstrict, function_owner.proparallel, function_owner.proretset, "
                "function_owner.pronargs, function_owner.proargtypes::text, function_owner.procost, "
                "function_owner.prorows, function_owner.prosupport::regproc::text, "
                "function_owner.prokind, function_owner.proconfig, function_owner.prosrc, "
                "owner_role.rolname FROM pg_proc function_owner "
                "JOIN pg_namespace namespace ON namespace.oid=function_owner.pronamespace "
                "JOIN pg_language language ON language.oid=function_owner.prolang "
                "JOIN pg_roles owner_role ON owner_role.oid=function_owner.proowner "
                f"WHERE namespace.nspname='{_SCHEMA}' AND function_owner.proname='{_FUNCTION_NAME}'"
            )
        ).fetchall()
    }
    if function_rows != {
        (
            "",
            "trigger",
            "plpgsql",
            "v",
            False,
            False,
            False,
            "u",
            False,
            0,
            "",
            100.0,
            0.0,
            "-",
            "f",
            None,
            _FUNCTION_BODY,
            owner_name,
        )
    }:
        raise RuntimeError("0006 catalog self-check：function definition/owner 漂移")
    function_acl = {
        (str(row[0]), str(row[1]), bool(row[2]))
        for row in bind.execute(
            text(
                "SELECT CASE WHEN acl.grantee=0 THEN 'PUBLIC' ELSE role.rolname END, "
                "acl.privilege_type, acl.is_grantable FROM pg_proc function_owner "
                "JOIN pg_namespace namespace ON namespace.oid=function_owner.pronamespace "
                "CROSS JOIN LATERAL aclexplode(COALESCE(function_owner.proacl, "
                "acldefault('f', function_owner.proowner))) acl "
                "LEFT JOIN pg_roles role ON role.oid=acl.grantee "
                f"WHERE namespace.nspname='{_SCHEMA}' AND function_owner.proname='{_FUNCTION_NAME}'"
            )
        ).fetchall()
    }
    if function_acl != {(owner_name, "EXECUTE", False)}:
        raise RuntimeError("0006 catalog self-check：function ACL/PUBLIC revoke 漂移")
    trigger_rows = {
        tuple(row)
        for row in bind.execute(
            text(
                "SELECT trigger_owner.tgtype, trigger_owner.tgenabled, trigger_owner.tgisinternal, "
                "trigger_owner.tgattr::text, trigger_owner.tgqual, trigger_owner.tgdeferrable, "
                "trigger_owner.tginitdeferred, trigger_owner.tgoldtable, trigger_owner.tgnewtable, "
                "trigger_owner.tgnargs, function_owner.proname, function_namespace.nspname, "
                "owner_role.rolname, pg_get_triggerdef(trigger_owner.oid, true) "
                "FROM pg_trigger trigger_owner JOIN pg_class relation "
                "ON relation.oid=trigger_owner.tgrelid JOIN pg_namespace namespace "
                "ON namespace.oid=relation.relnamespace JOIN pg_roles owner_role "
                "ON owner_role.oid=relation.relowner JOIN pg_proc function_owner "
                "ON function_owner.oid=trigger_owner.tgfoid JOIN pg_namespace function_namespace "
                "ON function_namespace.oid=function_owner.pronamespace "
                f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname='job_runs' "
                f"AND trigger_owner.tgname='{_TRIGGER_NAME}'"
            )
        ).fetchall()
    }
    expected_trigger_definition = (
        f"CREATE TRIGGER {_TRIGGER_NAME} BEFORE UPDATE ON {_JOB_TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION {_SCHEMA}.{_FUNCTION_NAME}()"
    )
    if trigger_rows != {
        (
            19,
            "O",
            False,
            "",
            None,
            False,
            False,
            None,
            None,
            0,
            _FUNCTION_NAME,
            _SCHEMA,
            owner_name,
            expected_trigger_definition,
        )
    }:
        raise RuntimeError("0006 catalog self-check：function/trigger manifest 漂移")
    if any(len(name.encode("utf-8")) > 63 for name in _OBJECT_NAMES):
        raise RuntimeError("0006 catalog self-check：identifier超过63-byte")
    _assert_security_exact(bind)


def _external_dependency_count(bind: Connection) -> int:
    """统计0006三列/三CHECK/function/trigger的owner外依赖。

    Args:
        bind: 当前 Alembic connection。

    Returns:
        外部view/rule/constraint/function/trigger/role依赖数量。

    Raises:
        SQLAlchemyError: catalog查询失败时向外传播。
    """

    relation_oid = str(
        bind.execute(text(f"SELECT '{_JOB_TABLE}'::regclass::oid")).scalar_one()
    )
    attribute_rows = {
        (str(row[0]), int(row[1]))
        for row in bind.execute(
            text(
                "SELECT attname, attnum FROM pg_attribute "
                f"WHERE attrelid={relation_oid}::oid AND attname IN "
                "('original_available_at','request_payload_schema_name',"
                "'request_payload_schema_version') AND NOT attisdropped"
            )
        ).fetchall()
    }
    if {name for name, _attnum in attribute_rows} != set(_IDENTITY_COLUMNS):
        raise RuntimeError("0006 downgrade 拒绝：identity column catalog 漂移")
    attnums = ",".join(str(attnum) for _name, attnum in sorted(attribute_rows))
    check_rows = {
        (str(row[0]), int(row[1]))
        for row in bind.execute(
            text(
                "SELECT constraint_owner.conname, constraint_owner.oid "
                "FROM pg_constraint constraint_owner "
                f"WHERE constraint_owner.conrelid={relation_oid}::oid "
                "AND constraint_owner.conname IN "
                "('ck_job_runs_original_deadline_after_available',"
                "'ck_job_runs_request_payload_schema_name_nonempty',"
                "'ck_job_runs_request_payload_schema_version_positive')"
            )
        ).fetchall()
    }
    if {name for name, _oid in check_rows} != set(_CHECK_NAMES):
        raise RuntimeError("0006 downgrade 拒绝：identity CHECK catalog 漂移")
    check_oids = ",".join(str(oid) for _name, oid in sorted(check_rows))
    function_oid = str(
        bind.execute(
            text(f"SELECT '{_SCHEMA}.{_FUNCTION_NAME}()'::regprocedure::oid")
        ).scalar_one()
    )
    trigger_oid = str(
        bind.execute(
            text(
                "SELECT trigger_owner.oid FROM pg_trigger trigger_owner "
                f"WHERE trigger_owner.tgrelid={relation_oid}::oid "
                f"AND trigger_owner.tgname='{_TRIGGER_NAME}' "
                "AND NOT trigger_owner.tgisinternal"
            )
        ).scalar_one()
    )
    target_rows = [
        f"('pg_class'::regclass,{relation_oid}::oid,{attnum})"
        for _name, attnum in sorted(attribute_rows)
    ] + [
        f"('pg_constraint'::regclass,{oid}::oid,0)"
        for _name, oid in sorted(check_rows)
    ] + [
        f"('pg_proc'::regclass,{function_oid}::oid,0)",
        f"('pg_trigger'::regclass,{trigger_oid}::oid,0)",
    ]
    target_values = ",".join(target_rows)
    external_dependencies = _scalar_int(
        bind,
        "WITH targets(classid,objid,objsubid) AS (VALUES "
        f"{target_values}) SELECT count(*) FROM pg_depend dependency JOIN targets target "
        "ON dependency.refclassid=target.classid AND dependency.refobjid=target.objid "
        "AND dependency.refobjsubid=target.objsubid WHERE NOT ("
        "(target.classid='pg_class'::regclass AND dependency.classid='pg_constraint'::regclass "
        f"AND dependency.objid IN ({check_oids})) OR "
        "(target.classid='pg_proc'::regclass AND dependency.classid='pg_trigger'::regclass "
        f"AND dependency.objid={trigger_oid}::oid))",
    )
    outbound_extension_dependencies = _scalar_int(
        bind,
        "WITH targets(classid,objid,objsubid) AS (VALUES "
        f"{target_values}) SELECT count(*) FROM pg_depend dependency JOIN targets target "
        "ON dependency.classid=target.classid AND dependency.objid=target.objid "
        "AND dependency.objsubid=target.objsubid "
        "WHERE dependency.refclassid='pg_extension'::regclass "
        "AND dependency.deptype IN ('e','x')",
    )
    column_acl_dependencies = _scalar_int(
        bind,
        "SELECT count(*) FROM pg_attribute attribute "
        "CROSS JOIN LATERAL aclexplode(attribute.attacl) acl "
        f"WHERE attribute.attrelid={relation_oid}::oid AND attribute.attnum IN ({attnums})",
    )
    function_acl_dependencies = _scalar_int(
        bind,
        "SELECT count(*) FROM pg_proc function_owner "
        "CROSS JOIN LATERAL aclexplode(function_owner.proacl) acl "
        f"WHERE function_owner.oid={function_oid}::oid "
        "AND acl.grantee<>function_owner.proowner",
    )
    shared_role_dependencies = _scalar_int(
        bind,
        "WITH targets(classid,objid,objsubid) AS (VALUES "
        f"{target_values}) SELECT count(*) FROM pg_shdepend dependency JOIN targets target "
        "ON dependency.classid=target.classid AND dependency.objid=target.objid "
        "AND dependency.objsubid=target.objsubid "
        "WHERE dependency.dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) "
        "AND dependency.deptype<>'o'",
    )
    return (
        external_dependencies
        + outbound_extension_dependencies
        + column_acl_dependencies
        + function_acl_dependencies
        + shared_role_dependencies
    )


def upgrade() -> None:
    """安全安装0006 immutable Job request identity。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: baseline、backfill proof或终态catalog不闭合时抛出。
        SQLAlchemyError: NOWAIT lock或任一transactional DDL失败时传播。
    """

    op.execute("SET LOCAL TIME ZONE 'UTC'")
    _assert_0005_catalog(require_identity_absent=True)
    _lock_identity_tables()
    _assert_0005_catalog(require_identity_absent=True)
    op.execute(
        f"ALTER TABLE {_JOB_TABLE} ADD COLUMN original_available_at TIMESTAMPTZ, "
        "ADD COLUMN request_payload_schema_name TEXT, "
        "ADD COLUMN request_payload_schema_version INTEGER"
    )
    _backfill_rows()
    _install_identity_contract()
    _assert_0006_catalog(expected_revision=down_revision)


def downgrade() -> None:
    """仅在空Job表且无外部依赖时精确回滚0006。

    Args:
        无。

    Returns:
        无。

    Raises:
        RuntimeError: catalog、dependency或空表admission失败时抛出。
        SQLAlchemyError: NOWAIT lock或任一transactional DDL失败时传播。
    """

    op.execute("SET LOCAL TIME ZONE 'UTC'")
    _lock_identity_tables()
    _assert_0006_catalog(expected_revision=revision)
    bind = op.get_bind()
    if _external_dependency_count(bind) != 0:
        raise RuntimeError("0006 downgrade 拒绝：request identity存在外部依赖")
    if _scalar_int(bind, f"SELECT count(*) FROM {_JOB_TABLE}") != 0:
        raise RuntimeError("0006 downgrade 拒绝：job_runs不是空表")
    op.execute(f"DROP TRIGGER {_TRIGGER_NAME} ON {_JOB_TABLE}")
    op.execute(f"DROP FUNCTION {_SCHEMA}.{_FUNCTION_NAME}()")
    op.execute(
        f"ALTER TABLE {_JOB_TABLE} "
        "DROP CONSTRAINT ck_job_runs_request_payload_schema_version_positive, "
        "DROP CONSTRAINT ck_job_runs_request_payload_schema_name_nonempty, "
        "DROP CONSTRAINT ck_job_runs_original_deadline_after_available, "
        "DROP COLUMN request_payload_schema_version, "
        "DROP COLUMN request_payload_schema_name, "
        "DROP COLUMN original_available_at"
    )
    _assert_0005_catalog(
        require_identity_absent=True,
        require_revision_0005=False,
    )
