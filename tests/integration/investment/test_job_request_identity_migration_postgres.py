"""0006 immutable Job request identity 的独立 PostgreSQL 16 owner。

本文件只覆盖linear 0005->0006 migration：exact catalog/security、
proof-only backfill、fail-closed admission、NOWAIT锁与empty-only downgrade。
所有数据库独立创建，任何失败候选都验证0005无partial DDL。
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from psycopg.errors import LockNotAvailable
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError

from dayu.investment.domain.jobs import (
    CanonicalJobDocument,
    JobEnqueueRequest,
    JobHandlerDescriptor,
    job_enqueue_request_fingerprint,
)
from dayu.investment.storage import (
    PLATFORM_APP_ROLE,
    PLATFORM_SCHEMA_NAME,
)
from tests.integration.investment.conftest import (
    _ALEMBIC_INI,
    _MIGRATIONS_DIR,
    PlatformCluster,
    _exec_admin_sql,
    create_temporary_login,
    drop_temporary_login,
    run_alembic_downgrade,
)

pytestmark = pytest.mark.integration

DatabaseFactory = Callable[[], str]
_SCHEMA = PLATFORM_SCHEMA_NAME
_REVISION_0005 = "0005_source_connectors_health"
_REVISION_0006 = "0006_job_request_identity"
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
_FUNCTION_BODY = (
    " BEGIN IF (OLD.original_available_at IS DISTINCT FROM NEW.original_available_at "
    "OR OLD.request_payload_schema_name IS DISTINCT FROM NEW.request_payload_schema_name "
    "OR OLD.request_payload_schema_version IS DISTINCT FROM "
    "NEW.request_payload_schema_version) THEN RAISE EXCEPTION "
    "'immutable job request identity update rejected'; END IF; RETURN NEW; END; "
)
_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
_DEFINITION_ID = UUID("60000000-0000-4000-8000-000000000001")
_JOB_ID = UUID("60000000-0000-4000-8000-000000000002")
_AVAILABLE_AT = datetime(2026, 8, 14, 1, 2, 3, 456789, tzinfo=timezone.utc)
_DEADLINE_AT = _AVAILABLE_AT + timedelta(hours=2, microseconds=7)
_DESCRIPTOR = JobHandlerDescriptor(
    job_type="test.0006.legacy",
    payload_schema_name="test.definition.payload",
    payload_schema_version=3,
    max_attempts=4,
    retry_base_seconds=7,
    retry_max_seconds=61,
    lease_duration_seconds=43,
)


def _migration_config() -> Config:
    """构造只指向本仓迁移目录的Alembic配置。

    Returns:
        Alembic配置。

    Raises:
        无。
    """

    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return config


def _run_migration(dsn: str, *, revision: str, downgrade: bool = False) -> None:
    """运行精确revision并恢复进程环境。

    Args:
        dsn: 目标bootstrap DSN。
        revision: Alembic目标revision。
        downgrade: True时执行downgrade，否则upgrade。

    Returns:
        无。

    Raises:
        RuntimeError: migration admission拒绝时原样传播。
        DBAPIError: DDL或锁的数据库失败时原样传播。
    """

    previous = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = dsn
    try:
        if downgrade:
            command.downgrade(_migration_config(), revision)
        else:
            command.upgrade(_migration_config(), revision)
    finally:
        if previous is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = previous


@pytest.fixture()
def identity_database(
    platform_cluster: PlatformCluster,
    lifecycle_database: DatabaseFactory,
) -> Iterator[tuple[str, Engine]]:
    """创建owned数据库并保证Job清空、最终downgrade base。

    Args:
        platform_cluster: pinned PostgreSQL 16临时cluster。
        lifecycle_database: 独立数据库factory。

    Yields:
        bootstrap DSN与engine。

    Raises:
        RuntimeError: migration admission拒绝清理时传播。
        DBAPIError: 清理DML或DDL失败时传播。
    """

    database = lifecycle_database()
    dsn = platform_cluster.dsn_for_database(database, "postgres")
    engine = create_engine(dsn)
    try:
        yield dsn, engine
    finally:
        with engine.begin() as connection:
            schema_exists = connection.execute(
                text("SELECT 1 FROM pg_namespace WHERE nspname=:schema"),
                {"schema": _SCHEMA},
            ).scalar()
            if schema_exists == 1:
                connection.exec_driver_sql(
                    f"TRUNCATE TABLE {_SCHEMA}.source_health_alert_outbox, "
                    f"{_SCHEMA}.source_health_states, {_SCHEMA}.source_sync_operations, "
                    f"{_SCHEMA}.source_health_snapshots, {_SCHEMA}.source_sync_runs, "
                    f"{_SCHEMA}.job_schedule_occurrences, {_SCHEMA}.agent_run_correlations, "
                    f"{_SCHEMA}.job_events, {_SCHEMA}.job_attempt_receipts, "
                    f"{_SCHEMA}.job_leases, {_SCHEMA}.job_attempts, {_SCHEMA}.job_runs CASCADE"
                )
        engine.dispose()
        run_alembic_downgrade(dsn)


def _revision(connection: Connection) -> str:
    """读取唯一Alembic revision。

    Args:
        connection: bootstrap连接。

    Returns:
        当前revision字符串。

    Raises:
        AssertionError: revision不是字符串时抛出。
    """

    value = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert type(value) is str
    return value


def _assert_exact_0005(connection: Connection) -> None:
    """断言0006对象全无且0005关键目录保持exact。

    Args:
        connection: bootstrap连接。

    Returns:
        无。

    Raises:
        AssertionError: head、表数或任一0006对象残留时抛出。
    """

    assert _revision(connection) == _REVISION_0005
    assert connection.execute(
        text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema=:schema"
        ),
        {"schema": _SCHEMA},
    ).scalar_one() == 27
    assert connection.execute(
        text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema=:schema AND table_name='job_runs' "
            "AND column_name=ANY(:columns)"
        ),
        {"schema": _SCHEMA, "columns": list(_IDENTITY_COLUMNS)},
    ).scalar_one() == 0
    assert connection.execute(
        text(
            "SELECT (SELECT count(*) FROM pg_constraint constraint_owner "
            "JOIN pg_namespace namespace ON namespace.oid=constraint_owner.connamespace "
            "WHERE namespace.nspname=:schema AND constraint_owner.conname=ANY(:checks)) + "
            "(SELECT count(*) FROM pg_proc function_owner JOIN pg_namespace namespace "
            "ON namespace.oid=function_owner.pronamespace WHERE namespace.nspname=:schema "
            "AND function_owner.proname=:function_name) + "
            "(SELECT count(*) FROM pg_trigger WHERE tgname=:trigger_name)"
        ),
        {
            "schema": _SCHEMA,
            "checks": list(_CHECK_NAMES),
            "function_name": _FUNCTION_NAME,
            "trigger_name": _TRIGGER_NAME,
        },
    ).scalar_one() == 0
    job_indexes = {
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname=:schema "
                "AND tablename='job_runs'"
            ),
            {"schema": _SCHEMA},
        ).fetchall()
    }
    assert (
        "ix_job_runs_claim_ready",
        "CREATE INDEX ix_job_runs_claim_ready ON dayu_platform.job_runs USING btree "
        "(tenant_id, available_at, id) WHERE (state = 'ready'::text)",
    ) in job_indexes


def _assert_exact_0006(
    connection: Connection,
    *,
    external_execute_role: str | None = None,
) -> None:
    """独立断言0006三列、五对象、安全身份与head。

    Args:
        connection: bootstrap连接。
        external_execute_role: hostile role case中必须保留的额外EXECUTE grantee。

    Returns:
        无。

    Raises:
        AssertionError: 任一catalog/security事实漂移时抛出。
    """

    assert _revision(connection) == _REVISION_0006
    columns = {
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT column_name,data_type,is_nullable,column_default "
                "FROM information_schema.columns WHERE table_schema=:schema "
                "AND table_name='job_runs' AND column_name=ANY(:columns)"
            ),
            {"schema": _SCHEMA, "columns": list(_IDENTITY_COLUMNS)},
        ).fetchall()
    }
    assert columns == {
        ("original_available_at", "timestamp with time zone", "NO", None),
        ("request_payload_schema_name", "text", "NO", None),
        ("request_payload_schema_version", "integer", "NO", None),
    }
    checks = {
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT constraint_owner.conname,pg_get_expr(constraint_owner.conbin, "
                "constraint_owner.conrelid),constraint_owner.convalidated "
                "FROM pg_constraint constraint_owner JOIN pg_class relation "
                "ON relation.oid=constraint_owner.conrelid JOIN pg_namespace namespace "
                "ON namespace.oid=relation.relnamespace WHERE namespace.nspname=:schema "
                "AND relation.relname='job_runs' AND constraint_owner.conname=ANY(:checks)"
            ),
            {"schema": _SCHEMA, "checks": list(_CHECK_NAMES)},
        ).fetchall()
    }
    assert checks == {
        ("ck_job_runs_original_deadline_after_available", "(deadline_at > original_available_at)", True),
        (
            "ck_job_runs_request_payload_schema_name_nonempty",
            "((request_payload_schema_name <> ''::text) AND "
            "(request_payload_schema_name = TRIM(BOTH FROM request_payload_schema_name)))",
            True,
        ),
        ("ck_job_runs_request_payload_schema_version_positive", "(request_payload_schema_version > 0)", True),
    }
    function = connection.execute(
        text(
            "SELECT pg_get_function_arguments(function_owner.oid),"
            "pg_get_function_result(function_owner.oid),language.lanname,"
            "function_owner.provolatile,function_owner.prosecdef,"
            "function_owner.proleakproof,function_owner.proisstrict,"
            "function_owner.proparallel,function_owner.proretset,function_owner.pronargs,"
            "function_owner.proargtypes::text,function_owner.procost,function_owner.prorows,"
            "function_owner.prosupport::regproc::text,function_owner.prokind,"
            "function_owner.proconfig,function_owner.prosrc,owner_role.rolname "
            "FROM pg_proc function_owner JOIN pg_namespace namespace "
            "ON namespace.oid=function_owner.pronamespace JOIN pg_language language "
            "ON language.oid=function_owner.prolang JOIN pg_roles owner_role "
            "ON owner_role.oid=function_owner.proowner WHERE namespace.nspname=:schema "
            "AND function_owner.proname=:name"
        ),
        {"schema": _SCHEMA, "name": _FUNCTION_NAME},
    ).one()
    owner_name = str(function[17])
    assert tuple(function[:17]) == (
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
    )
    function_acl = {
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT CASE WHEN acl.grantee=0 THEN 'PUBLIC' ELSE role.rolname END, "
                "acl.privilege_type FROM pg_proc function_owner "
                "JOIN pg_namespace namespace ON namespace.oid=function_owner.pronamespace "
                "CROSS JOIN LATERAL aclexplode(function_owner.proacl) acl "
                "LEFT JOIN pg_roles role ON role.oid=acl.grantee "
                "WHERE namespace.nspname=:schema AND function_owner.proname=:name"
            ),
            {"schema": _SCHEMA, "name": _FUNCTION_NAME},
        ).fetchall()
    }
    expected_function_acl = {(owner_name, "EXECUTE")}
    if external_execute_role is not None:
        expected_function_acl.add((external_execute_role, "EXECUTE"))
    assert function_acl == expected_function_acl
    trigger = connection.execute(
        text(
            "SELECT trigger_owner.tgtype,trigger_owner.tgenabled,trigger_owner.tgisinternal,"
            "trigger_owner.tgattr::text,trigger_owner.tgqual,trigger_owner.tgdeferrable,"
            "trigger_owner.tginitdeferred,trigger_owner.tgoldtable,trigger_owner.tgnewtable,"
            "trigger_owner.tgnargs,function_owner.proname,function_namespace.nspname,"
            "pg_get_triggerdef(trigger_owner.oid,true) "
            "FROM pg_trigger trigger_owner JOIN pg_class relation "
            "ON relation.oid=trigger_owner.tgrelid JOIN pg_namespace namespace "
            "ON namespace.oid=relation.relnamespace JOIN pg_proc function_owner "
            "ON function_owner.oid=trigger_owner.tgfoid JOIN pg_namespace function_namespace "
            "ON function_namespace.oid=function_owner.pronamespace "
            "WHERE namespace.nspname=:schema "
            "AND relation.relname='job_runs' AND trigger_owner.tgname=:name"
        ),
        {"schema": _SCHEMA, "name": _TRIGGER_NAME},
    ).one()
    assert tuple(trigger) == (
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
        f"CREATE TRIGGER {_TRIGGER_NAME} BEFORE UPDATE ON {_SCHEMA}.job_runs "
        f"FOR EACH ROW EXECUTE FUNCTION {_SCHEMA}.{_FUNCTION_NAME}()",
    )
    new_update_grants = connection.execute(
        text(
            "SELECT count(*) FROM pg_class relation JOIN pg_namespace namespace "
            "ON namespace.oid=relation.relnamespace JOIN pg_attribute attribute "
            "ON attribute.attrelid=relation.oid CROSS JOIN LATERAL "
            "aclexplode(attribute.attacl) acl JOIN pg_roles role ON role.oid=acl.grantee "
            "WHERE namespace.nspname=:schema AND relation.relname='job_runs' "
            "AND attribute.attname=ANY(:columns) AND role.rolname=:app_role "
            "AND acl.privilege_type='UPDATE'"
        ),
        {
            "schema": _SCHEMA,
            "columns": list(_IDENTITY_COLUMNS),
            "app_role": PLATFORM_APP_ROLE,
        },
    ).scalar_one()
    assert new_update_grants == 0
    rls = connection.execute(
        text(
            "SELECT relrowsecurity,relforcerowsecurity FROM pg_class relation "
            "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
            "WHERE namespace.nspname=:schema AND relation.relname='job_runs'"
        ),
        {"schema": _SCHEMA},
    ).one()
    assert tuple(rls) == (True, True)
    policy = connection.execute(
        text(
            "SELECT policyname,permissive,cmd,roles::text,qual,with_check "
            "FROM pg_policies WHERE schemaname=:schema AND tablename='job_runs'"
        ),
        {"schema": _SCHEMA},
    ).one()
    tenant_expression = (
        "((NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid = tenant_id)"
    )
    assert tuple(policy) == (
        "tenant_isolation",
        "PERMISSIVE",
        "ALL",
        f"{{{PLATFORM_APP_ROLE}}}",
        tenant_expression,
        tenant_expression,
    )


def _seed_legacy_job(
    connection: Connection,
    *,
    raw_bytes: bytes,
    stored_sha256: str,
    request_schema_name: str,
    request_schema_version: int,
    available_at: datetime = _AVAILABLE_AT,
    current_attempt_number: int = 0,
) -> None:
    """在0005写入一条可控legacy definition/job。

    Args:
        connection: 0005 bootstrap connection。
        raw_bytes: legacy payload BYTEA。
        stored_sha256: legacy payload SHA列。
        request_schema_name: 用于生成stored fingerprint的原请求schema名。
        request_schema_version: 用于生成stored fingerprint的原请求schema版本。
        available_at: stored current available时间。
        current_attempt_number: legacy Job已推进的attempt计数。

    Returns:
        无。

    Raises:
        RuntimeError: DTO fingerprint admission失败时传播。
        DBAPIError: legacy DML失败时传播。
    """

    payload = CanonicalJobDocument(
        schema_name=request_schema_name,
        schema_version=request_schema_version,
        canonical_bytes=raw_bytes,
        sha256=stored_sha256,
    )
    fingerprint = job_enqueue_request_fingerprint(
        JobEnqueueRequest(
            descriptor=_DESCRIPTOR,
            idempotency_key="legacy-key",
            payload=payload,
            available_at=_AVAILABLE_AT,
            deadline_at=_DEADLINE_AT,
        )
    )
    connection.execute(
        text(
            f"INSERT INTO {_SCHEMA}.job_definitions "
            "(id,tenant_id,job_type,payload_schema_name,payload_schema_version,max_attempts,"
            "retry_base_seconds,retry_max_seconds,lease_duration_seconds,status) VALUES "
            "(:id,:tenant_id,:job_type,:schema_name,:schema_version,:max_attempts,"
            ":retry_base,:retry_max,:lease_duration,'active')"
        ),
        {
            "id": _DEFINITION_ID,
            "tenant_id": _TENANT_ID,
            "job_type": _DESCRIPTOR.job_type,
            "schema_name": _DESCRIPTOR.payload_schema_name,
            "schema_version": _DESCRIPTOR.payload_schema_version,
            "max_attempts": _DESCRIPTOR.max_attempts,
            "retry_base": _DESCRIPTOR.retry_base_seconds,
            "retry_max": _DESCRIPTOR.retry_max_seconds,
            "lease_duration": _DESCRIPTOR.lease_duration_seconds,
        },
    )
    connection.execute(
        text(
            f"INSERT INTO {_SCHEMA}.job_runs "
            "(id,tenant_id,definition_id,idempotency_key,request_fingerprint,payload_bytes,"
            "payload_sha256,state,available_at,deadline_at,current_attempt_number) VALUES "
            "(:id,:tenant_id,:definition_id,'legacy-key',:fingerprint,:payload_bytes,"
            ":payload_sha256,'ready',:available_at,:deadline_at,:current_attempt_number)"
        ),
        {
            "id": _JOB_ID,
            "tenant_id": _TENANT_ID,
            "definition_id": _DEFINITION_ID,
            "fingerprint": fingerprint,
            "payload_bytes": raw_bytes,
            "payload_sha256": stored_sha256,
            "available_at": available_at,
            "deadline_at": _DEADLINE_AT,
            "current_attempt_number": current_attempt_number,
        },
    )


def test_0006_exact_job_request_identity_columns_checks_trigger_acl_rls_and_head_catalog(
    identity_database: tuple[str, Engine],
    platform_cluster: PlatformCluster,
) -> None:
    """升级产生exact目录，并行为证明三列owner/app均不可改写。

    Args:
        identity_database: owned DSN/engine。
        platform_cluster: 创建窄app login所需的临时cluster。

    Returns:
        无。

    Raises:
        AssertionError: 任一目录事实漂移时抛出。
    """

    dsn, engine = identity_database
    raw = b'{"value":1}'
    _run_migration(dsn, revision=_REVISION_0005)
    with engine.begin() as connection:
        _seed_legacy_job(
            connection,
            raw_bytes=raw,
            stored_sha256=hashlib.sha256(raw).hexdigest(),
            request_schema_name=_DESCRIPTOR.payload_schema_name,
            request_schema_version=_DESCRIPTOR.payload_schema_version,
        )
    _run_migration(dsn, revision=_REVISION_0006)
    with engine.connect() as connection:
        _assert_exact_0006(connection)
        connection.rollback()
    mutations = (
        "original_available_at = original_available_at + interval '1 second'",
        "request_payload_schema_name = 'test.changed.payload'",
        "request_payload_schema_version = 99",
    )
    for assignment in mutations:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with pytest.raises(DBAPIError):
                    connection.exec_driver_sql(
                        f"UPDATE {_SCHEMA}.job_runs SET {assignment} WHERE id='{_JOB_ID}'"
                    )
            finally:
                transaction.rollback()
    database_name = engine.url.database
    assert type(database_name) is str
    app_login = create_temporary_login(
        platform_cluster,
        database_name,
        member_of=PLATFORM_APP_ROLE,
    )
    app_engine = create_engine(app_login.dsn)
    try:
        for assignment in mutations:
            with app_engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(
                        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                        {"tenant_id": str(_TENANT_ID)},
                    )
                    with pytest.raises(DBAPIError):
                        connection.exec_driver_sql(
                            f"UPDATE {_SCHEMA}.job_runs SET {assignment} "
                            f"WHERE id='{_JOB_ID}'"
                        )
                finally:
                    transaction.rollback()
    finally:
        app_engine.dispose()
        drop_temporary_login(platform_cluster, app_login)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                f"SELECT original_available_at,request_payload_schema_name,"
                f"request_payload_schema_version FROM {_SCHEMA}.job_runs WHERE id=:id"
            ),
            {"id": _JOB_ID},
        ).one()
        assert tuple(row) == (
            _AVAILABLE_AT,
            _DESCRIPTOR.payload_schema_name,
            _DESCRIPTOR.payload_schema_version,
        )
        connection.rollback()


@pytest.mark.parametrize(
    (
        "case_name",
        "raw_bytes",
        "stored_sha256",
        "current_attempt_number",
        "expect_success",
    ),
    (
        ("canonical", b'{"value":1}', hashlib.sha256(b'{"value":1}').hexdigest(), 0, True),
        (
            "canonical_progressed",
            b'{"value":1}',
            hashlib.sha256(b'{"value":1}').hexdigest(),
            2,
            True,
        ),
        ("root_null", b"null", hashlib.sha256(b"null").hexdigest(), 0, True),
        (
            "root_array",
            '[null,false,0,"中",{}]'.encode(),
            hashlib.sha256('[null,false,0,"中",{}]'.encode()).hexdigest(),
            0,
            True,
        ),
        ("finite_float", b"1.0", hashlib.sha256(b"1.0").hexdigest(), 0, False),
        ("nonfinite_nan", b"NaN", hashlib.sha256(b"NaN").hexdigest(), 0, False),
        ("invalid_utf8", b"\xff", hashlib.sha256(b"\xff").hexdigest(), 0, False),
        ("sha_drift", b'{"value":1}', "0" * 64, 0, False),
        (
            "noncanonical_order",
            b'{"z":1,"a":2}',
            hashlib.sha256(b'{"z":1,"a":2}').hexdigest(),
            0,
            False,
        ),
        (
            "duplicate",
            b'{"a":1,"a":2}',
            hashlib.sha256(b'{"a":1,"a":2}').hexdigest(),
            0,
            False,
        ),
        (
            "bom",
            b'\xef\xbb\xbf{"a":1}',
            hashlib.sha256(b'\xef\xbb\xbf{"a":1}').hexdigest(),
            0,
            False,
        ),
        (
            "trailing",
            b'{"a":1} ',
            hashlib.sha256(b'{"a":1} ').hexdigest(),
            0,
            False,
        ),
        (
            "token",
            b'{"token":"x"}',
            hashlib.sha256(b'{"token":"x"}').hexdigest(),
            0,
            False,
        ),
        (
            "mixed_token",
            b'{"a":{"ToKeN":"x"}}',
            hashlib.sha256(b'{"a":{"ToKeN":"x"}}').hexdigest(),
            0,
            False,
        ),
    ),
)
def test_0006_proven_backfill_persists_original_available_and_request_payload_schema_identity(
    identity_database: tuple[str, Engine],
    case_name: str,
    raw_bytes: bytes,
    stored_sha256: str,
    current_attempt_number: int,
    expect_success: bool,
) -> None:
    """backfill只接受全链可证明canonical row且负例零partial DDL。

    Args:
        identity_database: owned DSN/engine。
        case_name: 参数case标签。
        raw_bytes: legacy payload bytes。
        stored_sha256: legacy stored SHA。
        current_attempt_number: legacy已推进的attempt计数。
        expect_success: 是否应成功backfill。

    Returns:
        无。

    Raises:
        AssertionError: admission或持久化结果漂移时抛出。
    """

    del case_name
    dsn, engine = identity_database
    _run_migration(dsn, revision=_REVISION_0005)
    with engine.begin() as connection:
        _seed_legacy_job(
            connection,
            raw_bytes=raw_bytes,
            stored_sha256=stored_sha256,
            request_schema_name=_DESCRIPTOR.payload_schema_name,
            request_schema_version=_DESCRIPTOR.payload_schema_version,
            current_attempt_number=current_attempt_number,
        )
    with engine.connect() as connection:
        before = _catalog_snapshot(connection)
        connection.rollback()
    if expect_success:
        _run_migration(dsn, revision=_REVISION_0006)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    f"SELECT original_available_at,request_payload_schema_name,"
                    f"request_payload_schema_version,current_attempt_number "
                    f"FROM {_SCHEMA}.job_runs WHERE id=:id"
                ),
                {"id": _JOB_ID},
            ).one()
            assert tuple(row) == (
                _AVAILABLE_AT,
                _DESCRIPTOR.payload_schema_name,
                _DESCRIPTOR.payload_schema_version,
                current_attempt_number,
            )
            connection.rollback()
    else:
        with pytest.raises(RuntimeError):
            _run_migration(dsn, revision=_REVISION_0006)
        with engine.connect() as connection:
            _assert_exact_0005(connection)
            assert _catalog_snapshot(connection) == before
            connection.rollback()


def test_0006_upgrade_rejects_retry_mutated_available_at_without_partial_ddl(
    identity_database: tuple[str, Engine],
) -> None:
    """legacy retry改写current available后升级拒绝且0005原样。

    Args:
        identity_database: owned DSN/engine。

    Returns:
        无。

    Raises:
        AssertionError: upgrade接受猜测事实或留下partial DDL时抛出。
    """

    dsn, engine = identity_database
    _run_migration(dsn, revision=_REVISION_0005)
    raw = b'{"value":1}'
    with engine.begin() as connection:
        _seed_legacy_job(
            connection,
            raw_bytes=raw,
            stored_sha256=hashlib.sha256(raw).hexdigest(),
            request_schema_name=_DESCRIPTOR.payload_schema_name,
            request_schema_version=_DESCRIPTOR.payload_schema_version,
            available_at=_AVAILABLE_AT + timedelta(minutes=5),
        )
    with engine.connect() as connection:
        before = _catalog_snapshot(connection)
        connection.rollback()
    with pytest.raises(RuntimeError):
        _run_migration(dsn, revision=_REVISION_0006)
    with engine.connect() as connection:
        _assert_exact_0005(connection)
        assert _catalog_snapshot(connection) == before
        connection.rollback()


def test_0006_upgrade_rejects_legacy_payload_schema_mismatch_without_partial_ddl(
    identity_database: tuple[str, Engine],
) -> None:
    """历史合法request/definition schema mismatch无法证明时拒绝。

    Args:
        identity_database: owned DSN/engine。

    Returns:
        无。

    Raises:
        AssertionError: migration猜测definition schema或partial DDL时抛出。
    """

    dsn, engine = identity_database
    _run_migration(dsn, revision=_REVISION_0005)
    raw = b'{"value":1}'
    with engine.begin() as connection:
        _seed_legacy_job(
            connection,
            raw_bytes=raw,
            stored_sha256=hashlib.sha256(raw).hexdigest(),
            request_schema_name="test.request.payload",
            request_schema_version=19,
        )
    with engine.connect() as connection:
        before = _catalog_snapshot(connection)
        connection.rollback()
    with pytest.raises(RuntimeError):
        _run_migration(dsn, revision=_REVISION_0006)
    with engine.connect() as connection:
        _assert_exact_0005(connection)
        assert _catalog_snapshot(connection) == before
        connection.rollback()


@pytest.mark.parametrize("dependency_kind", ("row", "view", "role", "extension"))
def test_0006_downgrade_rejects_rows_or_external_dependencies_without_cascade(
    identity_database: tuple[str, Engine],
    platform_cluster: PlatformCluster,
    dependency_kind: str,
) -> None:
    """dirty row、view、role grant与extension membership均在破坏前拒绝。

    Args:
        identity_database: owned DSN/engine。
        platform_cluster: cluster admin DSN用于外部role case。
        dependency_kind: row/view/role/extension hostile case。

    Returns:
        无。

    Raises:
        AssertionError: downgrade发生partial DDL或CASCADE时抛出。
    """

    dsn, engine = identity_database
    role_name = f"dayu_0006_external_{uuid4().hex}"
    _run_migration(dsn, revision=_REVISION_0005)
    if dependency_kind == "row":
        raw = b'{"value":1}'
        with engine.begin() as connection:
            _seed_legacy_job(
                connection,
                raw_bytes=raw,
                stored_sha256=hashlib.sha256(raw).hexdigest(),
                request_schema_name=_DESCRIPTOR.payload_schema_name,
                request_schema_version=_DESCRIPTOR.payload_schema_version,
            )
    _run_migration(dsn, revision=_REVISION_0006)
    try:
        if dependency_kind == "view":
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    f"CREATE VIEW external_0006_identity_view AS SELECT "
                    f"original_available_at FROM {_SCHEMA}.job_runs"
                )
        elif dependency_kind == "role":
            _exec_admin_sql(platform_cluster.bootstrap_dsn, f'CREATE ROLE "{role_name}"')
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    f'GRANT EXECUTE ON FUNCTION {_SCHEMA}.{_FUNCTION_NAME}() TO "{role_name}"'
                )
        elif dependency_kind == "extension":
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    f"ALTER EXTENSION plpgsql ADD FUNCTION {_SCHEMA}.{_FUNCTION_NAME}()"
                )
        with pytest.raises(RuntimeError):
            _run_migration(dsn, revision=_REVISION_0005, downgrade=True)
        with engine.connect() as connection:
            _assert_exact_0006(
                connection,
                external_execute_role=(
                    role_name if dependency_kind == "role" else None
                ),
            )
            connection.rollback()
    finally:
        with engine.begin() as connection:
            if dependency_kind == "view":
                connection.exec_driver_sql("DROP VIEW IF EXISTS external_0006_identity_view")
            elif dependency_kind == "role":
                connection.exec_driver_sql(
                    f'REVOKE ALL ON FUNCTION {_SCHEMA}.{_FUNCTION_NAME}() FROM "{role_name}"'
                )
            elif dependency_kind == "extension":
                connection.exec_driver_sql(
                    f"ALTER EXTENSION plpgsql DROP FUNCTION {_SCHEMA}.{_FUNCTION_NAME}()"
                )
            connection.execute(text(f"DELETE FROM {_SCHEMA}.job_runs"))
            connection.execute(text(f"DELETE FROM {_SCHEMA}.job_definitions"))
        if dependency_kind == "role":
            _exec_admin_sql(platform_cluster.bootstrap_dsn, f'DROP ROLE IF EXISTS "{role_name}"')


@pytest.mark.parametrize("locked_table", ("job_runs", "job_definitions"))
def test_0006_nowait_lock_conflict_fails_closed_without_partial_ddl(
    identity_database: tuple[str, Engine],
    locked_table: str,
) -> None:
    """第二连接持锁时NOWAIT立即失败且0005不变。

    Args:
        identity_database: owned DSN/engine。
        locked_table: 持有ACCESS SHARE锁的精确目标表。

    Returns:
        无。

    Raises:
        AssertionError: upgrade等待、成功或留下partial DDL时抛出。
    """

    dsn, engine = identity_database
    _run_migration(dsn, revision=_REVISION_0005)
    with engine.connect() as connection:
        before = _catalog_snapshot(connection)
        connection.rollback()
    blocker = engine.connect()
    transaction = blocker.begin()
    try:
        blocker.exec_driver_sql(
            f"LOCK TABLE {_SCHEMA}.{locked_table} IN ACCESS SHARE MODE"
        )
        with pytest.raises(OperationalError) as raised:
            _run_migration(dsn, revision=_REVISION_0006)
        assert isinstance(raised.value.orig, LockNotAvailable)
    finally:
        transaction.rollback()
        blocker.close()
    with engine.connect() as connection:
        _assert_exact_0005(connection)
        assert _catalog_snapshot(connection) == before
        connection.rollback()


def _catalog_snapshot(connection: Connection) -> tuple[tuple[str, ...], ...]:
    """读取稳定排序的0005 affected目录快照。

    Args:
        connection: bootstrap连接。

    Returns:
        列、constraint、index、guard、relation、policy与ACL的字符串tuple。

    Raises:
        无。
    """

    statements = (
        "SELECT table_name||':'||column_name||':'||data_type||':'||is_nullable||':'||"
        "COALESCE(column_default,'') FROM information_schema.columns "
        f"WHERE table_schema='{_SCHEMA}' AND table_name IN ('job_definitions','job_runs') "
        "ORDER BY 1",
        "SELECT relation.relname||':'||constraint_owner.conname||':'||"
        "pg_get_constraintdef(constraint_owner.oid) FROM pg_constraint constraint_owner "
        "JOIN pg_class relation ON relation.oid=constraint_owner.conrelid "
        "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
        f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
        "('job_definitions','job_runs') ORDER BY 1",
        f"SELECT tablename||':'||indexname||':'||indexdef FROM pg_indexes WHERE schemaname='{_SCHEMA}' "
        "AND tablename IN ('job_definitions','job_runs') ORDER BY 1",
        f"SELECT tablename||':'||policyname||':'||permissive||':'||cmd||':'||"
        f"roles::text||':'||qual||':'||with_check "
        f"FROM pg_policies WHERE schemaname='{_SCHEMA}' AND tablename IN "
        "('job_definitions','job_runs') ORDER BY 1",
        "SELECT relation.relname||':'||owner_role.rolname||':'||relation.relkind::text||':'||"
        "relation.relpersistence::text||':'||relation.relispartition::text||':'||"
        "relation.relrowsecurity::text||':'||relation.relforcerowsecurity::text "
        "FROM pg_class relation JOIN pg_namespace namespace "
        "ON namespace.oid=relation.relnamespace JOIN pg_roles owner_role "
        "ON owner_role.oid=relation.relowner "
        f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
        "('job_definitions','job_runs') ORDER BY 1",
        "SELECT function_owner.proname||':'||pg_get_function_arguments(function_owner.oid)||':'||"
        "pg_get_function_result(function_owner.oid)||':'||language.lanname||':'||"
        "function_owner.provolatile::text||':'||function_owner.prosecdef::text||':'||"
        "function_owner.proisstrict::text||':'||function_owner.proparallel::text||':'||"
        "function_owner.prosrc||':'||owner_role.rolname||':'||"
        "COALESCE(function_owner.proacl::text,'') FROM pg_proc function_owner "
        "JOIN pg_namespace namespace ON namespace.oid=function_owner.pronamespace "
        "JOIN pg_language language ON language.oid=function_owner.prolang "
        "JOIN pg_roles owner_role ON owner_role.oid=function_owner.proowner "
        f"WHERE namespace.nspname='{_SCHEMA}' AND function_owner.proname IN "
        "('guard_job_definitions_immutable_columns','guard_job_runs_immutable_columns') "
        "ORDER BY 1",
        "SELECT relation.relname||':'||trigger_owner.tgname||':'||"
        "trigger_owner.tgtype::text||':'||trigger_owner.tgenabled::text||':'||"
        "trigger_owner.tgdeferrable::text||':'||trigger_owner.tginitdeferred::text||':'||"
        "pg_get_triggerdef(trigger_owner.oid,true) FROM pg_trigger trigger_owner "
        "JOIN pg_class relation ON relation.oid=trigger_owner.tgrelid "
        "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
        f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
        "('job_definitions','job_runs') AND NOT trigger_owner.tgisinternal ORDER BY 1",
        "SELECT relation.relname||':'||CASE WHEN acl.grantee=0 THEN 'PUBLIC' ELSE role.rolname END||':'||"
        "acl.privilege_type||':'||acl.is_grantable::text FROM pg_class relation "
        "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
        "CROSS JOIN LATERAL aclexplode(relation.relacl) acl "
        "LEFT JOIN pg_roles role ON role.oid=acl.grantee "
        f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
        "('job_definitions','job_runs') ORDER BY 1",
        "SELECT relation.relname||':'||attribute.attname||':'||role.rolname||':'||"
        "acl.privilege_type||':'||acl.is_grantable::text FROM pg_class relation "
        "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
        "JOIN pg_attribute attribute ON attribute.attrelid=relation.oid "
        "AND attribute.attnum>0 AND NOT attribute.attisdropped "
        "CROSS JOIN LATERAL aclexplode(attribute.attacl) acl "
        "JOIN pg_roles role ON role.oid=acl.grantee "
        f"WHERE namespace.nspname='{_SCHEMA}' AND relation.relname IN "
        "('job_definitions','job_runs') ORDER BY 1",
    )
    return tuple(
        tuple(str(row[0]) for row in connection.execute(text(statement)).fetchall())
        for statement in statements
    )


def test_0006_clean_upgrade_downgrade_upgrade_cycle_preserves_exact_0005_catalog(
    identity_database: tuple[str, Engine],
) -> None:
    """空库0005->0006->0005->0006循环精确保留baseline。

    Args:
        identity_database: owned DSN/engine。

    Returns:
        无。

    Raises:
        AssertionError: 任一cycle目录或head漂移时抛出。
    """

    dsn, engine = identity_database
    _run_migration(dsn, revision=_REVISION_0005)
    with engine.connect() as connection:
        before = _catalog_snapshot(connection)
        _assert_exact_0005(connection)
        connection.rollback()
    _run_migration(dsn, revision=_REVISION_0006)
    with engine.connect() as connection:
        _assert_exact_0006(connection)
        connection.rollback()
    _run_migration(dsn, revision=_REVISION_0005, downgrade=True)
    with engine.connect() as connection:
        _assert_exact_0005(connection)
        assert _catalog_snapshot(connection) == before
        connection.rollback()
    _run_migration(dsn, revision=_REVISION_0006)
    with engine.connect() as connection:
        _assert_exact_0006(connection)
        connection.rollback()
