"""旧 workspace 显式导入的 PostgreSQL 16 真实 integration 测试。

本文件在真实官方 ``postgres:16.14-bookworm`` 容器上验证 S15-CTRL-09/12
的 repository 单事务契约与 vertical CLI 流程：

- publish_import 单事务发布后 company/security/source/locator/marker
  rows exact；public existing exact reuse；business-key/id/content
  conflict fail closed；
- exact rerun no_op 且时间/版本不变；fingerprint/schema/payload/count/
  row drift 抛稳定 drift；
- advisory xact lock key 算法 exact；两进程 race 恰一 imported 一
  no-op；winner 中途终止后 loser 完整发布；
- 临时 trigger fault injection：company/security/source/locator/marker
  各阶段抛错整次 rollback 零行；
- RLS：unset/cross tenant 不可见不可写；schema 不存在冗余
  ``company_id``；
- vertical：真实 ``dayu-cli init --import-existing-workspace`` 经注入
  PostgreSQL fixture 使用真实 stage/Service/repository，随后用独立
  audit/read 模型证明 locator/hash 可解析回原 bundle 且 legacy bytes
  未改。

禁止 SQLite/fake PostgreSQL 替代 transaction/RLS/concurrency truth。
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection

from dayu.cli.commands._research_template_materialize import materialize_research_template_bundle
from dayu.cli.commands.init import run_init_command
from dayu.investment.domain.identifiers import Principal, TenantId, TenantScope
from dayu.investment.domain.source import SecurityType, SourceKind
from dayu.investment.domain.workspace_import import (
    LEGACY_FINS_FILING_SOURCE_KEY,
    LEGACY_REPOSITORY_KEY,
    WORKSPACE_IMPORT_MIGRATION_ID,
    WorkspaceImportDriftError,
    WorkspaceImportRepositoryFailureError,
    WorkspaceImportRequest,
    WorkspaceImportSchemaUnavailableError,
    LegacyBundleReference,
    build_verified_bundle_locator,
    build_verified_company,
    build_verified_source_definition,
    build_workspace_import_request,
)
from dayu.investment.storage import (
    DEFAULT_ORGANIZATION_ID,
    PLATFORM_APP_ROLE,
    PLATFORM_AUDIT_ROLE,
    PLATFORM_SCHEMA_NAME,
    create_platform_engine,
    create_platform_session_factory,
)
from dayu.investment.storage.postgres_workspace_import import PostgresWorkspaceImportRepository

from tests.integration.investment.conftest import (
    PlatformCluster,
    TemporaryLogin,
    create_temporary_login,
    drop_temporary_login,
    query_all,
    run_alembic_downgrade,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.integration

_TENANT_A = DEFAULT_ORGANIZATION_ID
_TENANT_B = "00000000-0000-0000-0000-000000000002"

DatabaseFactory = Callable[[], str]

_BOOTSTRAP_COMPANY_ID = "11111111-1111-4111-8111-111111111111"
_BOOTSTRAP_SECURITY_ID = "22222222-2222-4222-8222-222222222222"
_BOOTSTRAP_MARKER_ID = "33333333-3333-4333-8333-333333333333"
_BOOTSTRAP_LOCATOR_ID = "44444444-4444-4444-8444-444444444444"


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


def _connect(dsn: str) -> Engine:
    """创建测试 engine（调用方负责 dispose）。

    Args:
        dsn: PostgreSQL DSN。

    Returns:
        关闭回显的 engine。

    Raises:
        无。
    """

    return create_engine(dsn, echo=False)


def _default_scope() -> TenantScope:
    """构造固定 default bootstrap scope。

    Args:
        无。

    Returns:
        default tenant scope。

    Raises:
        无。
    """

    return Principal(
        TenantId(DEFAULT_ORGANIZATION_ID),
        "workspace-import-bootstrap",
    ).to_scope()


def _build_request(
    tenant_id: TenantId,
    *,
    bundle_sha256: str = "a" * 64,
) -> WorkspaceImportRequest:
    """构造真实 import 请求（AAPL US + filing source + 1 locator）。

    Args:
        tenant_id: 目标租户。
        bundle_sha256: bundle 摘要（drift 场景覆盖用）。

    Returns:
        纯 import 请求。

    Raises:
        无。
    """

    company = build_verified_company(
        legacy_company_id="AAPL_US",
        company_name="Apple Inc.",
        company_meta_market="US",
        lei=None,
        country_code="US",
        ticker="AAPL",
        exchange_mic="XNAS",
        security_type=SecurityType.EQUITY,
        currency="USD",
        isin=None,
        is_active=True,
        bundles=(
            LegacyBundleReference(
                template_name="technology",
                relative_locator="assets/research_templates/technology.bundle.json",
            ),
        ),
    )
    locator = build_verified_bundle_locator(
        tenant_id=tenant_id,
        exchange_mic="XNAS",
        ticker="AAPL",
        template_name="technology",
        relative_locator="assets/research_templates/technology.bundle.json",
        bundle_sha256=bundle_sha256,
        artifact_manifest_sha256="b" * 64,
    )
    source_definition = build_verified_source_definition(
        source_key=LEGACY_FINS_FILING_SOURCE_KEY,
        source_kind=SourceKind.FILING,
        display_name="Legacy Fins Filing",
        enabled_by_default=False,
    )
    return build_workspace_import_request(
        migration_id=WORKSPACE_IMPORT_MIGRATION_ID,
        companies=(company,),
        source_definitions=(source_definition,),
        locators=(locator,),
        company_projections=(),
        source_root_presence=(),
        bundle_closures=(),
    )


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


def _make_repository(
    cluster: PlatformCluster,
    database: str,
) -> tuple[PostgresWorkspaceImportRepository, Engine, TemporaryLogin]:
    """构造 app 身份的 workspace import repository。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。

    Returns:
        (repository, engine, login) 三元组（engine 与 login 由调用方
        dispose/释放）。

    Raises:
        无。
    """

    login = _make_app_login(cluster, database)
    engine = create_platform_engine(login.dsn)
    repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
    return repository, engine, login


def _set_tenant(conn: Connection, tenant_id: str) -> None:
    """在测试连接上设置 RLS 租户上下文（set_config, local）。

    Args:
        conn: 打开的连接。
        tenant_id: 租户 UUID。

    Returns:
        无。

    Raises:
        无。
    """

    conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})


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


def _query_marker_rows(engine: Engine) -> list[tuple]:
    """以 app 身份（SET LOCAL 默认租户）读取全部 marker 行。

    Args:
        engine: app engine。

    Returns:
        marker 行元组列表。

    Raises:
        无。
    """

    with engine.connect() as conn:
        _set_tenant(conn, _TENANT_A)
        rows = conn.execute(
            text(
                f"SELECT migration_id, source_schema_version, source_root_fingerprint, "
                "staged_payload_sha256, company_count, security_count, "
                "source_definition_count, bundle_count, created_at "
                f"FROM {PLATFORM_SCHEMA_NAME}.workspace_import_markers"
            )
        ).fetchall()
        return [tuple(row) for row in rows]


def _query_locator_rows(engine: Engine) -> list[tuple]:
    """以 app 身份（SET LOCAL 默认租户）读取全部 locator 行。

    Args:
        engine: app engine。

    Returns:
        locator 行元组列表。

    Raises:
        无。
    """

    with engine.connect() as conn:
        _set_tenant(conn, _TENANT_A)
        rows = conn.execute(
            text(
                f"SELECT security_id, template_name, repository_key, relative_locator, "
                "bundle_sha256, artifact_manifest_sha256 "
                f"FROM {PLATFORM_SCHEMA_NAME}.research_bundle_locators"
            )
        ).fetchall()
        return [tuple(row) for row in rows]


class TestWorkspaceImportRepository:
    """workspace import repository 单事务契约。"""

    @pytest.mark.integration
    def test_publish_commits_and_rows_exact(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """publish 后 company/security/source/locator/marker rows exact。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        repository, engine, login = _make_repository(platform_cluster, database)
        request = _build_request(TenantId(_TENANT_A))
        receipt = repository.publish_import(_default_scope(), request)
        assert receipt.status == "committed"
        assert receipt.company_count == 1
        assert receipt.security_count == 1
        assert receipt.source_definition_count == 1
        assert receipt.bundle_count == 1

        marker_rows = _query_marker_rows(engine)
        assert len(marker_rows) == 1
        marker = marker_rows[0]
        assert marker[0] == WORKSPACE_IMPORT_MIGRATION_ID
        assert marker[1] == 1
        assert marker[2] == request.source_root_fingerprint
        assert marker[3] == request.staged_payload_sha256
        assert marker[4] == 1 and marker[5] == 1 and marker[6] == 1 and marker[7] == 1

        locator_rows = _query_locator_rows(engine)
        assert len(locator_rows) == 1
        locator = locator_rows[0]
        assert locator[1] == "technology"
        assert locator[2] == LEGACY_REPOSITORY_KEY
        assert locator[4] == request.locators[0].bundle_sha256

        with engine.connect() as conn:
            company_rows = list(
                conn.execute(
                    text(
                        f"SELECT id, legal_name, lei, country_code FROM {PLATFORM_SCHEMA_NAME}.companies "
                        "WHERE id = :id"
                    ),
                    {"id": request.companies[0].company_id.value},
                ).fetchall()
            )
            assert len(company_rows) == 1
            assert company_rows[0][1] == "Apple Inc."
            security_rows = list(
                conn.execute(
                    text(
                        f"SELECT id, company_id, ticker, exchange_mic, security_type, currency "
                        f"FROM {PLATFORM_SCHEMA_NAME}.securities WHERE id = :id"
                    ),
                    {"id": request.companies[0].security.security_id.value},
                ).fetchall()
            )
            assert len(security_rows) == 1
            assert str(security_rows[0][1]) == request.companies[0].company_id.value
            assert security_rows[0][2] == "AAPL"
            assert security_rows[0][3] == "XNAS"
            source_rows = list(
                conn.execute(
                    text(
                        f"SELECT source_key, source_kind, enabled_by_default "
                        f"FROM {PLATFORM_SCHEMA_NAME}.source_definitions WHERE id = :id"
                    ),
                    {"id": request.source_definitions[0].source_definition_id.value},
                ).fetchall()
            )
            assert len(source_rows) == 1
            assert source_rows[0][0] == LEGACY_FINS_FILING_SOURCE_KEY
            assert source_rows[0][1] == "filing"
            assert source_rows[0][2] is False
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_exact_rerun_is_no_op_and_unchanged(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """exact rerun no_op，marker 时间/字节不变。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        first = repository.publish_import(_default_scope(), request)
        assert first.status == "committed"
        marker_before = _query_marker_rows(engine)
        second = repository.publish_import(_default_scope(), request)
        assert second.status == "no_op"
        marker_after = _query_marker_rows(engine)
        assert marker_after == marker_before
        assert len(_query_locator_rows(engine)) == 1
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_fingerprint_drift_raises_stable_error(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """marker fingerprint 不同时抛稳定 drift。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        first = repository.publish_import(_default_scope(), _build_request(TenantId(_TENANT_A)))
        assert first.status == "committed"
        drifted = _build_request(TenantId(_TENANT_A), bundle_sha256="c" * 64)
        with pytest.raises(WorkspaceImportDriftError):
            repository.publish_import(_default_scope(), drifted)
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_row_drift_after_external_tamper_raises_stable_error(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """marker exact 但 company row 被篡改时抛稳定 drift。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        repository.publish_import(_default_scope(), request)
        conn = _connect(_bootstrap_dsn(platform_cluster, database)).connect()
        try:
            conn = _autocommit(conn)
            conn.execute(
                text(
                    f"UPDATE {PLATFORM_SCHEMA_NAME}.companies "
                    "SET legal_name = 'Tampered Inc.' WHERE id = :id"
                ),
                {"id": request.companies[0].company_id.value},
            )
        finally:
            conn.close()
        with pytest.raises(WorkspaceImportDriftError):
            repository.publish_import(_default_scope(), request)
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_business_key_conflict_fails_closed(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """相同业务键映射到不同 ID 时 fail closed。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        conn = _connect(_bootstrap_dsn(platform_cluster, database)).connect()
        try:
            conn = _autocommit(conn)
            conn.execute(
                text(
                    f"INSERT INTO {PLATFORM_SCHEMA_NAME}.companies "
                    "(id, legal_name, lei, country_code) VALUES (:id, 'Apple Inc.', NULL, 'US')"
                ),
                {"id": request.companies[0].company_id.value},
            )
            conn.execute(
                text(
                    f"INSERT INTO {PLATFORM_SCHEMA_NAME}.securities "
                    "(id, company_id, ticker, exchange_mic, security_type, currency, isin, is_active) "
                    "VALUES (:id, :company_id, 'AAPL', 'XNAS', 'equity', 'USD', NULL, true)"
                ),
                {
                    "id": "99999999-9999-4999-8999-999999999999",
                    "company_id": request.companies[0].company_id.value,
                },
            )
        finally:
            conn.close()
        with pytest.raises(WorkspaceImportDriftError):
            repository.publish_import(_default_scope(), request)
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_public_existing_exact_reuse_commits(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """public rows 已 exact 存在时发布复用并完成 marker。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        company = request.companies[0]
        security = company.security
        source_definition = request.source_definitions[0]
        conn = _connect(_bootstrap_dsn(platform_cluster, database)).connect()
        try:
            conn = _autocommit(conn)
            conn.execute(
                text(
                    f"INSERT INTO {PLATFORM_SCHEMA_NAME}.companies "
                    "(id, legal_name, lei, country_code) VALUES (:id, :name, :lei, :cc)"
                ),
                {
                    "id": company.company_id.value,
                    "name": company.company_name,
                    "lei": None,
                    "cc": company.country_code,
                },
            )
            conn.execute(
                text(
                    f"INSERT INTO {PLATFORM_SCHEMA_NAME}.securities "
                    "(id, company_id, ticker, exchange_mic, security_type, currency, isin, is_active) "
                    "VALUES (:id, :company_id, :ticker, :mic, :st, :cur, :isin, :active)"
                ),
                {
                    "id": security.security_id.value,
                    "company_id": security.company_id.value,
                    "ticker": security.ticker,
                    "mic": security.exchange_mic,
                    "st": security.security_type.value,
                    "cur": security.currency,
                    "isin": None,
                    "active": True,
                },
            )
            conn.execute(
                text(
                    f"INSERT INTO {PLATFORM_SCHEMA_NAME}.source_definitions "
                    "(id, source_key, source_kind, display_name, enabled_by_default) "
                    "VALUES (:id, :key, :kind, :name, :enabled)"
                ),
                {
                    "id": source_definition.source_definition_id.value,
                    "key": source_definition.source_key,
                    "kind": source_definition.source_kind.value,
                    "name": source_definition.display_name,
                    "enabled": False,
                },
            )
        finally:
            conn.close()
        receipt = repository.publish_import(_default_scope(), request)
        assert receipt.status == "committed"
        assert len(_query_marker_rows(engine)) == 1
        assert len(_query_locator_rows(engine)) == 1
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_missing_0002_schema_raises_schema_unavailable(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """0002 schema 未应用时抛 schema_unavailable。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        from alembic import command
        from alembic.config import Config

        from tests.integration.investment.conftest import _ALEMBIC_INI, _MIGRATIONS_DIR

        cfg = Config(str(_ALEMBIC_INI))
        cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
        import os

        previous = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
        os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = _bootstrap_dsn(platform_cluster, database)
        try:
            command.downgrade(cfg, "0001_platform_foundation")
        finally:
            if previous is None:
                os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
            else:
                os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = previous
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        with pytest.raises(WorkspaceImportSchemaUnavailableError):
            repository.publish_import(_default_scope(), _build_request(TenantId(_TENANT_A)))
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_trigger_fault_rollback_zero_rows(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """company/source/locator/marker 各阶段 fault 整次 rollback 零行。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        for table_name in (
            "companies",
            "source_definitions",
            "research_bundle_locators",
            "workspace_import_markers",
        ):
            _install_failing_trigger(platform_cluster, database, table_name)
            with pytest.raises(WorkspaceImportRepositoryFailureError):
                repository.publish_import(_default_scope(), request)
            _drop_failing_trigger(platform_cluster, database, table_name)
            with engine.connect() as conn:
                _set_tenant(conn, _TENANT_A)
                marker_count = conn.execute(
                    text(
                        f"SELECT count(*) FROM {PLATFORM_SCHEMA_NAME}.workspace_import_markers"
                    )
                ).scalar()
                locator_count = conn.execute(
                    text(
                        f"SELECT count(*) FROM {PLATFORM_SCHEMA_NAME}.research_bundle_locators"
                    )
                ).scalar()
            assert marker_count == 0
            assert locator_count == 0
        receipt = repository.publish_import(_default_scope(), request)
        assert receipt.status == "committed"
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_two_thread_race_one_committed_one_noop(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """同 marker 两线程 race：恰一 imported 一 no_op。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        barrier = threading.Barrier(2)
        statuses: list[str] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def _publish() -> None:
            """并发发布同一 request（race 用）。

            Args:
                无。

            Returns:
                无。

            Raises:
                BaseException: repository 异常记录到 errors。
            """

            barrier.wait()
            try:
                receipt = repository.publish_import(_default_scope(), request)
                with lock:
                    statuses.append(receipt.status)
            except BaseException as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=_publish) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        assert sorted(statuses) == ["committed", "no_op"]
        assert len(_query_marker_rows(engine)) == 1
        assert len(_query_locator_rows(engine)) == 1
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_winner_rollback_then_loser_fully_imports(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """winner 在 locator 阶段终止后，下一进程完整发布。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        _install_failing_trigger(platform_cluster, database, "research_bundle_locators")
        with pytest.raises(WorkspaceImportRepositoryFailureError):
            repository.publish_import(_default_scope(), request)
        _drop_failing_trigger(platform_cluster, database, "research_bundle_locators")
        receipt = repository.publish_import(_default_scope(), request)
        assert receipt.status == "committed"
        assert len(_query_marker_rows(engine)) == 1
        assert len(_query_locator_rows(engine)) == 1
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_advisory_lock_blocks_until_released(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """repository 使用精确 advisory key（外部持锁会阻塞发布）。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        tenant_value = _TENANT_A
        digest = hashlib.sha256(f"{tenant_value}\0{WORKSPACE_IMPORT_MIGRATION_ID}".encode()).digest()
        expected_key = int.from_bytes(digest[:8], byteorder="big", signed=True)

        holder = _connect(_bootstrap_dsn(platform_cluster, database)).connect()

        results: list[str] = []
        errors: list[BaseException] = []

        def _publish() -> None:
            """在外部 advisory lock 下尝试发布（应被阻塞）。

            Args:
                无。

            Returns:
                无。

            Raises:
                BaseException: repository 异常记录到 errors。
            """

            try:
                receipt = repository.publish_import(_default_scope(), request)
                results.append(receipt.status)
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=_publish)
        with holder.begin():
            holder.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": expected_key})
            worker.start()
            worker.join(timeout=2.0)
            assert worker.is_alive(), "publish 应被 advisory lock 阻塞"
        holder.close()
        worker.join(timeout=30.0)
        assert not worker.is_alive()
        assert errors == []
        assert results == ["committed"]
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_locator_resolves_company_only_via_security(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """locator 无冗余 company_id，公司只经 security_id 解析。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        repository.publish_import(_default_scope(), request)
        with engine.connect() as conn:
            columns = query_all(
                conn,
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_schema = '{PLATFORM_SCHEMA_NAME}' "
                "AND table_name = 'research_bundle_locators'",
            )
            assert "company_id" not in {row[0] for row in columns}
            _set_tenant(conn, _TENANT_A)
            resolved = conn.execute(
                text(
                    f"SELECT c.legal_name FROM {PLATFORM_SCHEMA_NAME}.research_bundle_locators l "
                    f"JOIN {PLATFORM_SCHEMA_NAME}.securities s ON s.id = l.security_id "
                    f"JOIN {PLATFORM_SCHEMA_NAME}.companies c ON c.id = s.company_id "
                    "WHERE l.template_name = 'technology'"
                )
            ).fetchone()
        assert resolved is not None
        assert resolved[0] == "Apple Inc."
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))

    @pytest.mark.integration
    def test_rls_hides_cross_tenant_rows(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
    ) -> None:
        """unset/cross-tenant RLS：marker/locator 不可见不可写。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = _make_app_login(platform_cluster, database)
        engine = create_platform_engine(login.dsn)
        repository = PostgresWorkspaceImportRepository(create_platform_session_factory(engine))
        request = _build_request(TenantId(_TENANT_A))
        repository.publish_import(_default_scope(), request)

        with engine.connect() as conn:
            visible = conn.execute(
                text(
                    f"SELECT count(*) FROM {PLATFORM_SCHEMA_NAME}.workspace_import_markers"
                )
            ).scalar()
            assert visible == 0
            _set_tenant(conn, _TENANT_B)
            cross_tenant = conn.execute(
                text(
                    f"SELECT count(*) FROM {PLATFORM_SCHEMA_NAME}.workspace_import_markers"
                )
            ).scalar()
            assert cross_tenant == 0
            with pytest.raises(Exception):
                conn.execute(
                    text(
                        f"INSERT INTO {PLATFORM_SCHEMA_NAME}.workspace_import_markers "
                        "(id, tenant_id, migration_id, source_schema_version, source_root_fingerprint, "
                        "staged_payload_sha256, company_count, security_count, "
                        "source_definition_count, bundle_count) VALUES "
                        "('55555555-5555-4555-8555-555555555555', :t, 'other', 1, "
                        "'" + "a" * 64 + "', '" + "b" * 64 + "', 0, 0, 0, 0)"
                    ),
                    {"t": _TENANT_A},
                )
            conn.rollback()
        engine.dispose()
        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))


def _install_failing_trigger(cluster: PlatformCluster, database: str, table_name: str) -> None:
    """在指定表上安装临时 RAISE 触发器。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。
        table_name: 目标表名。

    Returns:
        无。

    Raises:
        无。
    """

    conn = _connect(_bootstrap_dsn(cluster, database)).connect()
    try:
        conn = _autocommit(conn)
        conn.execute(
            text(
                "CREATE OR REPLACE FUNCTION dayu_slice15_fail() RETURNS trigger AS $$ "
                "BEGIN RAISE EXCEPTION 'slice15 injected failure'; END $$ LANGUAGE plpgsql"
            )
        )
        conn.execute(
            text(
                f"DROP TRIGGER IF EXISTS trg_slice15_fail ON {PLATFORM_SCHEMA_NAME}.{table_name}"
            )
        )
        conn.execute(
            text(
                f"CREATE TRIGGER trg_slice15_fail BEFORE INSERT ON "
                f"{PLATFORM_SCHEMA_NAME}.{table_name} "
                "FOR EACH ROW EXECUTE FUNCTION dayu_slice15_fail()"
            )
        )
    finally:
        conn.close()


def _drop_failing_trigger(cluster: PlatformCluster, database: str, table_name: str) -> None:
    """删除临时 RAISE 触发器与函数。

    Args:
        cluster: 共享临时 cluster。
        database: 目标数据库。
        table_name: 目标表名。

    Returns:
        无。

    Raises:
        无。
    """

    conn = _connect(_bootstrap_dsn(cluster, database)).connect()
    try:
        conn = _autocommit(conn)
        conn.execute(
            text(
                f"DROP TRIGGER IF EXISTS trg_slice15_fail ON {PLATFORM_SCHEMA_NAME}.{table_name}"
            )
        )
        conn.execute(text("DROP FUNCTION IF EXISTS dayu_slice15_fail()"))
    finally:
        conn.close()


class TestWorkspaceImportVerticalCli:
    """真实 dayu-cli import 流程（注入 PostgreSQL fixture）。"""

    @pytest.mark.integration
    def test_vertical_cli_import_commits_and_bytes_unchanged(
        self,
        platform_cluster: PlatformCluster,
        lifecycle_database: DatabaseFactory,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """vertical CLI：真实 stage/Service/repository 发布，legacy bytes 未改。"""

        database = lifecycle_database()
        run_alembic_upgrade(_bootstrap_dsn(platform_cluster, database))
        login = create_temporary_login(platform_cluster, database, member_of=PLATFORM_APP_ROLE)

        workspace_root = tmp_path / "workspace"
        portfolio_dir = workspace_root / "portfolio"
        ticker_dir = portfolio_dir / "AAPL"
        ticker_dir.mkdir(parents=True)
        meta = {
            "company_id": "AAPL_US",
            "company_name": "Apple Inc.",
            "ticker": "AAPL",
            "ticker_aliases": ["AAPL"],
            "market": "US",
            "resolver_version": "test",
            "updated_at": "2026-08-11T00:00:00.000000Z",
        }
        (ticker_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (ticker_dir / "filings").mkdir()
        materialized = materialize_research_template_bundle(
            "technology",
            workspace_root=workspace_root,
            ticker="AAPL",
            company="Apple Inc.",
            overwrite=True,
        )
        bundle_file = Path(str(materialized["bundle_file"]))
        manifest = {
            "schema_version": 1,
            "migration_id": "legacy-workspace-import-v1",
            "companies": [
                {
                    "legacy_company_id": "AAPL_US",
                    "country_code": "US",
                    "lei": None,
                    "security": {
                        "ticker": "AAPL",
                        "exchange_mic": "XNAS",
                        "security_type": "equity",
                        "currency": "USD",
                        "isin": None,
                        "is_active": True,
                    },
                    "bundles": [
                        {
                            "template_name": "technology",
                            "relative_locator": "assets/research_templates/technology.bundle.json",
                        }
                    ],
                }
            ],
        }
        manifest_path = workspace_root / "operator.manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        tree_before = _tree_snapshot(workspace_root)
        from dayu.investment.config import (
            DAYU_PLATFORM_AUTH_KEY_ENV,
            DAYU_PLATFORM_ENABLED_ENV,
            DAYU_PLATFORM_OBJECT_STORAGE_ENV,
            DAYU_PLATFORM_POSTGRES_DSN_ENV,
            DAYU_PLATFORM_PROFILE_ENV,
            DAYU_PLATFORM_REDIS_ENV,
        )

        monkeypatch.setenv(DAYU_PLATFORM_ENABLED_ENV, "1")
        monkeypatch.setenv(DAYU_PLATFORM_PROFILE_ENV, "production")
        monkeypatch.setenv(DAYU_PLATFORM_POSTGRES_DSN_ENV, login.dsn)
        monkeypatch.setenv(DAYU_PLATFORM_OBJECT_STORAGE_ENV, "DAYU_PLATFORM_OBJECT_STORAGE")
        monkeypatch.setenv(DAYU_PLATFORM_REDIS_ENV, "DAYU_PLATFORM_REDIS_URL")
        monkeypatch.setenv(DAYU_PLATFORM_AUTH_KEY_ENV, "DAYU_PLATFORM_AUTH_KEY")

        from argparse import Namespace

        args = Namespace(
            base=str(workspace_root),
            import_existing_workspace=True,
            import_existing_workspace_seen=1,
            import_existing_workspace_repeated=False,
            import_manifest=str(manifest_path),
            target_tenant_id=DEFAULT_ORGANIZATION_ID,
            reset=False,
            overwrite=False,
        )
        exit_code = run_init_command(args)
        assert exit_code == 0, capsys.readouterr().out
        captured = capsys.readouterr().out
        assert "workspace import committed" in captured

        assert _tree_snapshot(workspace_root) == tree_before

        audit_login = create_temporary_login(platform_cluster, database, member_of=PLATFORM_AUDIT_ROLE)
        audit_engine = create_platform_engine(audit_login.dsn)
        with audit_engine.connect() as conn:
            conn.execute(text(f"SET ROLE {PLATFORM_AUDIT_ROLE}"))
            rows = list(
                conn.execute(
                    text(
                        f"SELECT s.ticker, l.relative_locator, l.bundle_sha256, "
                        "l.artifact_manifest_sha256 "
                        f"FROM {PLATFORM_SCHEMA_NAME}.research_bundle_locators l "
                        f"JOIN {PLATFORM_SCHEMA_NAME}.securities s ON s.id = l.security_id"
                    )
                ).fetchall()
            )
        assert len(rows) == 1
        assert rows[0][0] == "AAPL"
        assert rows[0][1] == "assets/research_templates/technology.bundle.json"
        expected_descriptor_sha256 = hashlib.sha256(bundle_file.read_bytes()).hexdigest()
        assert rows[0][2] == expected_descriptor_sha256
        audit_engine.dispose()
        drop_temporary_login(platform_cluster, audit_login)

        marker_engine = create_platform_engine(login.dsn)
        with marker_engine.connect() as conn:
            _set_tenant(conn, _TENANT_A)
            marker = conn.execute(
                text(
                    f"SELECT migration_id, company_count, bundle_count "
                    f"FROM {PLATFORM_SCHEMA_NAME}.workspace_import_markers"
                )
            ).fetchone()
        marker_engine.dispose()
        assert marker is not None
        assert marker[0] == WORKSPACE_IMPORT_MIGRATION_ID
        assert marker[1] == 1
        assert marker[2] == 1

        drop_temporary_login(platform_cluster, login)
        run_alembic_downgrade(_bootstrap_dsn(platform_cluster, database))


def _tree_snapshot(root: Path) -> dict[str, tuple[str, int, int]]:
    """收集目录下全部 entry 的 (类型, size, mtime_ns) 快照。

    Args:
        root: 待快照的目录。

    Returns:
        相对路径 -> (类型, size, mtime_ns) 映射。

    Raises:
        OSError: 遍历失败时抛出。
    """

    import stat as stat_module

    snapshot: dict[str, tuple[str, int, int]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        try:
            entry_stat = path.lstat()
        except OSError:
            continue
        if stat_module.S_ISDIR(entry_stat.st_mode):
            entry_type = "dir"
        elif stat_module.S_ISLNK(entry_stat.st_mode):
            entry_type = "symlink"
        else:
            entry_type = "file"
        snapshot[relative] = (entry_type, entry_stat.st_size, entry_stat.st_mtime_ns)
    return snapshot
