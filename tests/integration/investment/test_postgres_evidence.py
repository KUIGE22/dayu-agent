"""S31-A 六表真实 PostgreSQL 16 schema 与 raw SQL 反例。"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from time import monotonic
from uuid import UUID, uuid4

import pytest
from alembic import command
from psycopg import Error as PsycopgError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from dayu.fins.domain.evidence_locator import (
    EvidenceLocatorError,
    parse_evidence_locator_projection,
)
from dayu.investment.storage import (
    DEFAULT_ORGANIZATION_ID,
    PLATFORM_APP_ROLE,
    PLATFORM_SCHEMA_NAME,
    PlatformMigrationAdmissionError,
)
from tests.integration.investment.conftest import (
    PlatformCluster,
    _alembic_config,
    create_temporary_login,
    drop_temporary_login,
    run_alembic_downgrade,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration

_TENANT = UUID(DEFAULT_ORGANIZATION_ID)
_WHEN = datetime(2025, 1, 2, tzinfo=timezone.utc)
_HEX = "a" * 64


@contextmanager
def _migration_dsn(dsn: str) -> Iterator[None]:
    """在单次 Alembic 命令期间设置 bootstrap DSN 并恢复原值。

    Args:
        dsn: 随机测试库的 bootstrap DSN，不写入文件。

    Yields:
        供 Alembic 执行命令的环境窗口。

    Raises:
        无；被包裹命令的异常原样传播。
    """

    old = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = dsn
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = old


def test_0007_empty_upgrade_downgrade_upgrade(
    platform_cluster: PlatformCluster, lifecycle_database,
) -> None:
    """真实空库升级、回退一个 revision、再升级，核 33/30/3。

    Args:
        platform_cluster: 临时 PG16 cluster。
        lifecycle_database: 独立随机数据库工厂。

    Returns:
        无。

    Raises:
        AssertionError: 往返、外部依赖拒绝或 catalog 不符。
    """

    database = lifecycle_database()
    dsn = platform_cluster.dsn_for_database(database, "postgres")
    upgraded = False
    try:
        run_alembic_upgrade(dsn)
        upgraded = True
        engine = create_engine(dsn)
        try:
            with engine.connect() as connection:
                rows = connection.execute(text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=:schema AND c.relkind='r'"
                ), {"schema": PLATFORM_SCHEMA_NAME}).all()
                assert len(rows) == 33
                assert sum(bool(row[1]) and bool(row[2]) for row in rows) == 30
                assert connection.execute(text(
                    "SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid='dayu_platform.facts'::regclass "
                    "AND attname='value_decimal'"
                )).scalar_one() == -1
                index = connection.execute(text(
                    "SELECT pg_get_indexdef('dayu_platform.uq_evidence_links_direct_digest'::regclass)"
                )).scalar_one()
                assert "(tenant_id, claim_version_id, relation, security_id, locator_index_digest)" in index
                assert "WHERE (fact_id IS NULL)" in index
        finally:
            engine.dispose()
        engine = create_engine(dsn)
        try:
            bounded_dsn = dsn + "?options=-c%20lock_timeout%3D5s"
            for locked_table in ("facts", "securities"):
                with engine.begin() as blocker:
                    blocker.exec_driver_sql(
                        f"LOCK TABLE dayu_platform.{locked_table} IN ACCESS SHARE MODE"
                    )
                    started = monotonic()
                    with _migration_dsn(bounded_dsn), pytest.raises(DBAPIError) as caught:
                        command.downgrade(_alembic_config(), "-1")
                    assert isinstance(caught.value.orig, PsycopgError)
                    assert caught.value.orig.sqlstate == "55P03"
                    assert monotonic() - started < 3.0
                    assert blocker.execute(text(
                        "SELECT version_num FROM public.alembic_version"
                    )).scalar_one() == "0007_strict_evidence"
                    assert blocker.execute(text(
                        "SELECT to_regclass('dayu_platform.facts')"
                    )).scalar_one() is not None
                    assert blocker.execute(text(
                        "SELECT count(*) FROM pg_constraint WHERE conname = "
                        "'uq_securities_company_id_id_ticker' "
                        "AND conrelid='dayu_platform.securities'::regclass"
                    )).scalar_one() == 1
            for grant, revoke in (
                (
                    "GRANT SELECT ON TABLE dayu_platform.facts TO PUBLIC",
                    "REVOKE SELECT ON TABLE dayu_platform.facts FROM PUBLIC",
                ),
                (
                    "GRANT SELECT (id) ON TABLE dayu_platform.facts TO PUBLIC",
                    "REVOKE SELECT (id) ON TABLE dayu_platform.facts FROM PUBLIC",
                ),
                (
                    "GRANT EXECUTE ON FUNCTION dayu_platform.evidence_locator_valid(jsonb) TO PUBLIC",
                    "REVOKE EXECUTE ON FUNCTION dayu_platform.evidence_locator_valid(jsonb) FROM PUBLIC",
                ),
            ):
                with engine.begin() as connection:
                    connection.exec_driver_sql(grant)
                with _migration_dsn(dsn), pytest.raises(
                    PlatformMigrationAdmissionError, match="external_role_dependency"
                ):
                    command.downgrade(_alembic_config(), "-1")
                with engine.begin() as connection:
                    assert connection.execute(text(
                        "SELECT version_num FROM public.alembic_version"
                    )).scalar_one() == "0007_strict_evidence"
                    assert connection.execute(text(
                        "SELECT to_regclass('dayu_platform.facts')"
                    )).scalar_one() is not None
                    connection.exec_driver_sql(revoke)
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE VIEW dayu_platform.evidence_external_probe "
                    "AS SELECT id FROM dayu_platform.facts"
                )
            with _migration_dsn(dsn), pytest.raises(DBAPIError):
                command.downgrade(_alembic_config(), "-1")
            with engine.begin() as connection:
                assert connection.execute(text(
                    "SELECT version_num FROM public.alembic_version"
                )).scalar_one() == "0007_strict_evidence"
                assert connection.execute(text(
                    "SELECT to_regclass('dayu_platform.facts')"
                )).scalar_one() is not None
                connection.exec_driver_sql("DROP VIEW dayu_platform.evidence_external_probe")
        finally:
            engine.dispose()
        with _migration_dsn(dsn):
            command.downgrade(_alembic_config(), "-1")
        engine = create_engine(dsn)
        try:
            with engine.connect() as connection:
                assert connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one() == "0006_job_request_identity"
                assert connection.execute(text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=:schema AND c.relkind='r'"
                ), {"schema": PLATFORM_SCHEMA_NAME}).scalar_one() == 27
                assert connection.execute(text(
                    "SELECT to_regclass('dayu_platform.uq_securities_company_id_id_ticker')"
                )).scalar_one() is None
        finally:
            engine.dispose()
        run_alembic_upgrade(dsn)
    finally:
        if upgraded:
            run_alembic_downgrade(dsn)


def _locator(ticker: str, kind: str = "document", payload: Mapping[str, str | int] | None = None) -> str:
    """生成无需 Fins runtime 的合法 v1 projection JSON。

    Args:
        ticker: 原样 canonical ticker。
        kind: 五类 locator kind 之一。
        payload: 对应 kind 的完整 payload。

    Returns:
        Fins v1 projection JSON 文本。

    Raises:
        TypeError: 输入不可 JSON 序列化时传播。
    """

    return json.dumps({
        "repository_id": "dayu.fins.public.v1",
        "ticker": ticker,
        "document_id": "doc_1",
        "source_kind": "filing",
        "artifact_kind": "source" if kind == "document" else "processed",
        "document_version": "v1",
        "source_fingerprint": _HEX,
        "primary_content_sha256": _HEX,
        "locator_kind": kind,
        "locator_payload": {} if payload is None else payload,
        "locator_content_sha256": _HEX,
    }, sort_keys=True)


def _reject(connection: Connection, statement: str, values: dict[str, str | bytes | int | UUID | datetime | None], sqlstate: str, constraint: str | None = None) -> None:
    """在 savepoint 内证实原始 SQL 由 PG 约束拒绝。

    Args:
        connection: 已设置本地租户上下文的 app 连接。
        statement: 参数化原始 SQL。
        values: 不含真实凭据的绑定值。
        sqlstate: 预期 PostgreSQL SQLSTATE。
        constraint: 可选的精确命名约束。

    Returns:
        无。

    Raises:
        AssertionError: PG 未按预期拒绝或命中错误约束。
    """

    savepoint = connection.begin_nested()
    try:
        with pytest.raises(DBAPIError) as caught:
            connection.execute(text(statement), values)
        assert isinstance(caught.value.orig, PsycopgError)
        assert caught.value.orig.sqlstate == sqlstate
        if constraint is not None:
            assert caught.value.orig.diag.constraint_name == constraint
    finally:
        savepoint.rollback()


def test_0007_app_role_raw_sql_rejections_and_dual_mic(
    platform_cluster: PlatformCluster, lifecycle_database,
) -> None:
    """app role 原始 INSERT 覆盖三值 NULL、ticker、decimal 与双 MIC。

    Args:
        platform_cluster: 临时 PG16 cluster。
        lifecycle_database: 独立随机数据库工厂。

    Returns:
        无。

    Raises:
        AssertionError: PG 原始 SQL 约束、权限或回退 admission 漂移。
    """

    database = lifecycle_database()
    dsn = platform_cluster.dsn_for_database(database, "postgres")
    company, other_company = uuid4(), uuid4()
    security_a, security_b, security_other = uuid4(), uuid4(), uuid4()
    actor, claim, version, fact = uuid4(), uuid4(), uuid4(), uuid4()
    run_alembic_upgrade(dsn)
    login = None
    try:
        bootstrap = create_engine(dsn)
        try:
            with bootstrap.begin() as connection:
                connection.execute(text("INSERT INTO dayu_platform.companies(id, legal_name) VALUES (:id, 'A'), (:other, 'B')"), {"id": company, "other": other_company})
                connection.execute(text(
                    "INSERT INTO dayu_platform.securities(id,company_id,ticker,exchange_mic,security_type,currency) VALUES "
                    "(:a,:company,'ABC','XNAS','equity','USD'),"
                    "(:b,:company,'ABC','XNYS','equity','USD'),"
                    "(:c,:other,'XYZ','XNAS','equity','USD')"
                ), {"a": security_a, "b": security_b, "c": security_other, "company": company, "other": other_company})
                connection.execute(text(
                    "INSERT INTO dayu_platform.users(id,tenant_id,subject,display_name,status) "
                    "VALUES (:id,:tenant,'evidence-author','Author','active')"
                ), {"id": actor, "tenant": _TENANT})
                connection.execute(text(
                    "INSERT INTO dayu_platform.claims(id,tenant_id,company_id) VALUES (:id,:tenant,:company)"
                ), {"id": claim, "tenant": _TENANT, "company": company})
                connection.execute(text(
                    "INSERT INTO dayu_platform.claim_versions "
                    "(id,tenant_id,company_id,claim_id,version_no,transition_kind,evidence_mode,operation_id,operation_fingerprint,statement,confidence_band,impact_horizon,status,invalidation_rule,author_user_id) "
                    "VALUES (:id,:tenant,:company,:claim,1,'claim_create','replace_all',:op,:fingerprint,'Revenue grows','medium','long','draft','revise',:actor)"
                ), {"id": version, "tenant": _TENANT, "company": company, "claim": claim, "op": uuid4(), "fingerprint": _HEX, "actor": actor})
        finally:
            bootstrap.dispose()
        login = create_temporary_login(platform_cluster, database, member_of=PLATFORM_APP_ROLE)
        engine = create_engine(login.dsn)
        try:
            with engine.connect() as connection:
                assert connection.execute(text("SELECT count(*) FROM dayu_platform.facts")).scalar_one() == 0
            fact_sql = (
                "INSERT INTO dayu_platform.facts "
                "(id,tenant_id,company_id,security_id,locator_ticker,locator_json,fact_series_id,revision_no,fact_key,metric,value_kind,value_decimal,unit_code,currency,effective_at,published_at,ingested_at,available_at,extractor_version,verification_status,operation_id,operation_fingerprint) "
                "VALUES (:id,:tenant,:company,:security,:ticker,CAST(:locator AS jsonb),:series,1,'revenue','revenue','decimal',CAST(:value AS numeric),:unit,:currency,:at,:at,:at,:at,'extractor-v1','unverified',:op,:fingerprint)"
            )
            with engine.begin() as connection:
                connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(_TENANT)})
                valid_locators: list[str] = []
                for kind, payload in (
                    ("document", {}),
                    ("page", {"page_no": 1}),
                    ("section", {"section_ref": "sec_1"}),
                    ("table_cell", {"table_ref": "table_1", "row_index": 0, "column": "Revenue"}),
                    ("xbrl_fact", {"concept": "us-gaap:Revenue", "fact_sha256": _HEX}),
                ):
                    locator = _locator("ABC", kind, payload)
                    parse_evidence_locator_projection(json.loads(locator))
                    valid_locators.append(locator)
                    assert connection.execute(text(
                        "SELECT dayu_platform.evidence_locator_valid(CAST(:locator AS jsonb))"
                    ), {"locator": locator}).scalar_one() is True
                assert connection.execute(text(
                    "SELECT dayu_platform.evidence_locator_valid(CAST(:locator AS jsonb))"
                ), {"locator": _locator("ABC", "page", {"page_no": -1})}).scalar_one() is False
                for kind, payload, key, padding in (
                    ("document", {}, "document_version", "\t"),
                    ("section", {"section_ref": "sec_1"}, "section_ref", "\u00a0"),
                    ("table_cell", {"table_ref": "table_1", "row_index": 0, "column": "Revenue"}, "table_ref", "\u2003"),
                    ("table_cell", {"table_ref": "table_1", "row_index": 0, "column": "Revenue"}, "column", "\t"),
                    ("xbrl_fact", {"concept": "us-gaap:Revenue", "fact_sha256": _HEX}, "concept", "\u00a0"),
                ):
                    invalid_locator = json.loads(_locator("ABC", kind, payload))
                    target = invalid_locator if key == "document_version" else invalid_locator["locator_payload"]
                    target[key] = padding + target[key]
                    with pytest.raises(EvidenceLocatorError):
                        parse_evidence_locator_projection(invalid_locator)
                    assert connection.execute(text(
                        "SELECT dayu_platform.evidence_locator_valid(CAST(:locator AS jsonb))"
                    ), {"locator": json.dumps(invalid_locator)}).scalar_one() is False
                base: dict[str, str | bytes | UUID | datetime | None] = {
                    "id": fact, "tenant": _TENANT, "company": company,
                    "security": security_a, "ticker": "ABC", "locator": _locator("ABC"),
                    "series": uuid4(), "value": "99999999999999999999999999.999999999999",
                    "unit": "currency", "currency": "USD",
                    "at": _WHEN, "op": uuid4(), "fingerprint": _HEX,
                }
                connection.execute(text(fact_sql), base)
                long_locator = _locator("ABC", "section", {
                    "section_ref": "".join(uuid4().hex for _ in range(250)),
                })
                parse_evidence_locator_projection(json.loads(long_locator))
                assert len(long_locator.encode()) > 8000
                for locator in (*valid_locators, long_locator):
                    fact_id = uuid4()
                    connection.execute(text(fact_sql), {
                        **base, "id": fact_id, "series": uuid4(), "op": uuid4(),
                        "locator": locator,
                    })
                    stored = connection.execute(text(
                        "SELECT locator_json::text FROM dayu_platform.facts WHERE id=:id"
                    ), {"id": fact_id}).scalar_one()
                    assert json.loads(stored) == json.loads(locator)
                roundtrip = connection.execute(text(
                    "SELECT value_decimal::text FROM dayu_platform.facts WHERE id=:id"
                ), {"id": fact}).scalar_one()
                assert roundtrip == base["value"]
                negative_id = uuid4()
                connection.execute(text(fact_sql), {
                    **base, "id": negative_id, "series": uuid4(), "op": uuid4(),
                    "value": "-" + str(base["value"]),
                })
                assert connection.execute(text(
                    "SELECT value_decimal::text FROM dayu_platform.facts WHERE id=:id"
                ), {"id": negative_id}).scalar_one() == "-" + str(base["value"])
                for changes, state, name in (
                    ({"security": None}, "23502", None),
                    ({"ticker": None}, "23502", None),
                    ({"locator": None}, "23502", None),
                    ({"locator": _locator("XYZ")}, "23514", "ck_facts_locator_ticker"),
                    ({"unit": None}, "23514", "ck_facts_unit_shape"),
                    ({"currency": None}, "23514", "ck_facts_unit_shape"),
                    ({"currency": "usd"}, "23514", "ck_facts_unit_shape"),
                    ({"value": "1.0000000000001"}, "23514", "ck_facts_decimal_bound"),
                    ({"value": "9" * 39}, "23514", "ck_facts_decimal_bound"),
                    ({"value": "NaN"}, "23514", "ck_facts_decimal_bound"),
                    ({"value": "Infinity"}, "23514", "ck_facts_decimal_bound"),
                    ({"value": "-Infinity"}, "23514", "ck_facts_decimal_bound"),
                ):
                    candidate = {**base, **changes, "id": uuid4(), "series": uuid4(), "op": uuid4()}
                    _reject(connection, fact_sql, candidate, state, name)
                invalid_fact_locator = json.loads(_locator("ABC"))
                invalid_fact_locator["document_version"] = "\t" + invalid_fact_locator["document_version"]
                _reject(connection, fact_sql, {
                    **base, "id": uuid4(), "series": uuid4(), "op": uuid4(),
                    "locator": json.dumps(invalid_fact_locator),
                }, "23514", "ck_facts_locator")
                link_sql = (
                    "INSERT INTO dayu_platform.evidence_links "
                    "(id,tenant_id,company_id,claim_version_id,relation,fact_id,security_id,locator_ticker,locator_json,locator_index_digest) "
                    "VALUES (:id,:tenant,:company,:version,:relation,:fact,:security,:ticker,CAST(:locator AS jsonb),:digest)"
                )
                link_base: dict[str, str | bytes | UUID | datetime | None] = {
                    "id": uuid4(), "tenant": _TENANT, "company": company,
                    "version": version, "relation": "supports", "fact": None, "security": security_a,
                    "ticker": "ABC", "locator": _locator("ABC"), "digest": b"caller-wrong",
                }
                connection.execute(text(link_sql), link_base)
                connection.execute(text(link_sql), {**link_base, "id": uuid4(), "security": security_b})
                digests = connection.execute(text(
                    "SELECT security_id, locator_index_digest, "
                    "sha256(convert_to(locator_json::text,'UTF8')) "
                    "FROM dayu_platform.evidence_links WHERE claim_version_id=:version "
                    "AND fact_id IS NULL ORDER BY security_id"
                ), {"version": version}).all()
                assert len(digests) == 2
                assert digests[0][1] == digests[1][1]
                assert all(len(row[1]) == 32 and row[1] == row[2] for row in digests)
                for locator in (*valid_locators, long_locator):
                    link_id = uuid4()
                    connection.execute(text(link_sql), {
                        **link_base, "id": link_id, "relation": "context",
                        "locator": locator,
                    })
                    stored = connection.execute(text(
                        "SELECT locator_json::text FROM dayu_platform.evidence_links WHERE id=:id"
                    ), {"id": link_id}).scalar_one()
                    assert json.loads(stored) == json.loads(locator)
                _reject(connection, link_sql, {**link_base, "id": uuid4()}, "23505", "uq_evidence_links_direct_digest")
                for changes, state, name in (
                    ({"fact": fact, "security": security_b, "ticker": "ABC", "locator": None}, "23514", "ck_evidence_links_target_arm"),
                    ({"fact": fact, "security": None, "ticker": "ABC", "locator": None}, "23514", "ck_evidence_links_target_arm"),
                    ({"ticker": None}, "23514", "ck_evidence_links_target_arm"),
                    ({"ticker": "ABC", "locator": _locator("XYZ")}, "23514", "ck_evidence_links_target_arm"),
                    ({"company": other_company, "relation": "contradicts"}, "23503", "fk_evidence_links_version"),
                    ({"security": security_other, "ticker": "XYZ", "locator": _locator("XYZ"), "relation": "contradicts"}, "23503", "fk_evidence_links_security_ticker"),
                ):
                    _reject(connection, link_sql, {**link_base, **changes, "id": uuid4()}, state, name)
                invalid_link_locator = json.loads(_locator("ABC", "section", {"section_ref": "sec_1"}))
                invalid_link_locator["locator_payload"]["section_ref"] += "\u00a0"
                _reject(connection, link_sql, {
                    **link_base, "id": uuid4(), "relation": "context",
                    "locator": json.dumps(invalid_link_locator),
                }, "23514", "ck_evidence_links_locator")
                connection.execute(text(link_sql), {
                    **link_base, "id": uuid4(), "fact": fact, "security": None,
                    "ticker": None, "locator": None, "digest": b"wrong",
                })
                assert connection.execute(text(
                    "SELECT count(*) FROM dayu_platform.evidence_links "
                    "WHERE claim_version_id=:version AND fact_id=:fact "
                    "AND locator_index_digest IS NULL AND security_id IS NULL "
                    "AND locator_ticker IS NULL AND locator_json IS NULL"
                ), {"version": version, "fact": fact}).scalar_one() == 1
                assert connection.execute(text(
                    "SELECT count(*) FROM dayu_platform.evidence_links WHERE claim_version_id=:version"
                ), {"version": version}).scalar_one() == 9
                version_sql = (
                    "INSERT INTO dayu_platform.claim_versions "
                    "(id,tenant_id,company_id,claim_id,version_no,transition_kind,evidence_mode,copy_source_version_id,operation_id,operation_fingerprint,statement,confidence_band,impact_horizon,status,invalidation_rule,transition_reason,author_user_id) "
                    "VALUES (:id,:tenant,:company,:claim,:number,:action,:mode,:source,:op,:fingerprint,'Revenue grows','medium','long',:status,'revise',:reason,:author)"
                )
                ordinary: dict[str, str | bytes | int | UUID | datetime | None] = {
                    "id": uuid4(), "tenant": _TENANT, "company": company,
                    "claim": claim, "number": 2, "action": "content_revision",
                    "mode": "replace_all", "source": None, "op": uuid4(),
                    "fingerprint": _HEX, "status": "draft", "reason": None,
                    "author": None,
                }
                connection.execute(text(version_sql), ordinary)
                for changes, state, name in (
                    ({"action": "claim_create"}, "23514", "ck_claim_versions_first_version"),
                    ({"action": "begin_revision", "reason": "revise"}, "23514", "ck_claim_versions_action_witness"),
                    ({"action": "expiry", "status": "review_required"}, "23514", "ck_claim_versions_action_witness"),
                    ({"action": "review_decision", "status": "approved"}, "23514", "ck_claim_versions_action_witness"),
                    ({"mode": "copy_previous"}, "23514", "ck_claim_versions_evidence_mode"),
                    ({"mode": "copy_previous", "source": uuid4()}, "23503", "fk_claim_versions_copy_source"),
                ):
                    _reject(connection, version_sql, {
                        **ordinary, **changes, "id": uuid4(), "number": 3, "op": uuid4(),
                    }, state, name)
                first_claim = uuid4()
                connection.execute(text(
                    "INSERT INTO dayu_platform.claims(id,tenant_id,company_id) "
                    "VALUES (:id,:tenant,:company)"
                ), {"id": first_claim, "tenant": _TENANT, "company": company})
                _reject(connection, version_sql, {
                    **ordinary, "id": uuid4(), "claim": first_claim, "number": 1,
                    "action": "claim_create", "status": "approved", "op": uuid4(),
                }, "23514", "ck_claim_versions_first_version")
        finally:
            engine.dispose()
        bootstrap_guard = create_engine(dsn)
        try:
            with bootstrap_guard.begin() as connection:
                for table, row_id in (
                    ("facts", fact), ("claim_versions", version),
                ):
                    _reject(connection,
                            f"UPDATE dayu_platform.{table} SET created_at=created_at WHERE id=:id",
                            {"id": row_id}, "23514")
                _reject(connection,
                        "DELETE FROM dayu_platform.evidence_links WHERE claim_version_id=:id",
                        {"id": version}, "23514")
        finally:
            bootstrap_guard.dispose()
        with _migration_dsn(dsn), pytest.raises(
            PlatformMigrationAdmissionError, match="business_rows_present"
        ):
            command.downgrade(_alembic_config(), "-1")
        unchanged = create_engine(dsn)
        try:
            with unchanged.connect() as connection:
                assert connection.execute(text(
                    "SELECT version_num FROM public.alembic_version"
                )).scalar_one() == "0007_strict_evidence"
                assert connection.execute(text(
                    "SELECT count(*) FROM dayu_platform.evidence_links"
                )).scalar_one() == 9
        finally:
            unchanged.dispose()
    finally:
        if login is not None:
            drop_temporary_login(platform_cluster, login)
        cleanup = create_engine(dsn)
        try:
            with cleanup.begin() as connection:
                connection.exec_driver_sql(
                    "TRUNCATE TABLE dayu_platform.claim_conflicts, dayu_platform.evidence_links, "
                    "dayu_platform.claim_versions, dayu_platform.claims, dayu_platform.facts, "
                    "dayu_platform.research_candidates"
                )
                connection.execute(text("DELETE FROM dayu_platform.users WHERE id=:id"), {"id": actor})
                connection.execute(text("DELETE FROM dayu_platform.securities WHERE id IN (:a,:b,:c)"), {"a": security_a, "b": security_b, "c": security_other})
                connection.execute(text("DELETE FROM dayu_platform.companies WHERE id IN (:a,:b)"), {"a": company, "b": other_company})
        finally:
            cleanup.dispose()
        run_alembic_downgrade(dsn)
