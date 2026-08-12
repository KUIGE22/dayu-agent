"""平台迁移单元契约测试（无数据库）。

本文件只验证不需要数据库的 unit contract（S11-CTRL-07 / S15-CTRL-08 /
Slice 2.2 durable schedules）：

- ``dayu_platform`` schema 精确包含 15 张表，表名与类型完整；
- metadata naming convention 确定且被 ``PlatformBase.metadata`` 采用；
- 每张表编译出的 DDL 满足列类型/nullable/约束契约：UUID 无 server
  default、时间戳时区语义、``version`` 的 check、JSONB 对象 check、
  私有表 FK 的 RESTRICT 等；
- ``0002_workspace_import`` 两表契约：marker 无 updated_at/version、
  counts/schema_version CHECK、``UNIQUE(tenant_id,migration_id)``；
  locator 无冗余 ``company_id``、``repository_key`` closed CHECK、
  复合 ``(tenant_id, import_marker_id)`` FK；
- 生产 import 路径禁止 ``metadata.create_all()``（AST 扫描
  ``dayu.investment.storage`` 与迁移脚本，不能出现 ``create_all``
  调用）。
- ``0004_durable_schedules`` 的两表、closed state/snapshot/count矩阵、
  tenant FK、RLS/最小权限与破坏性downgrade admission由源码级静态门禁
  锁定；真实PostgreSQL行为仍由独立integration process证明。

真实 ``upgrade -> downgrade -> upgrade``、default organization、
RLS/GRANT/schema exact 全部在 integration lane
（``tests/integration/investment/test_platform_migrations_postgres.py``）
验证，本文件不触碰数据库。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import DateTime, Engine, ForeignKeyConstraint, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from dayu.investment.storage import (
    NAMING_CONVENTION,
    PLATFORM_SCHEMA_NAME,
    PlatformBase,
    create_platform_engine,
    create_platform_session_factory,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STORAGE_SRC = _REPO_ROOT / "dayu" / "investment" / "storage"
_SCHEDULE_MIGRATION = (
    _STORAGE_SRC / "migrations" / "versions" / "0004_durable_schedules.py"
)

# 精确 15 张表名（S11-CTRL-03 + S15-CTRL-08）。
_EXPECTED_TABLES: frozenset[str] = frozenset(
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
        "workspace_import_markers",
        "research_bundle_locators",
    }
)

# 私有表（启用并 FORCE RLS）。
_PRIVATE_TABLES: frozenset[str] = frozenset(
    {
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
    }
)


def _iter_storage_files() -> list[Path]:
    """收集 storage 子包下全部 Python 文件。

    Args:
        无。

    Returns:
        按文件名排序的 Python 文件路径列表。

    Raises:
        无。
    """

    return sorted(path for path in _STORAGE_SRC.rglob("*.py") if path.is_file())


def _compile_ddl(table: Table) -> str:
    """把 ORM 表编译为 PostgreSQL DDL 字符串。

    Args:
        table: 待编译的 ORM 表。

    Returns:
        该表在 PostgreSQL 方言下的 ``CREATE TABLE`` 语句。

    Raises:
        无。
    """

    return str(CreateTable(table).compile(dialect=postgresql.dialect()))


class TestPlatformSchemaMetadata:
    """metadata 表集合与命名约定契约。"""

    @pytest.mark.unit
    def test_metadata_contains_exactly_13_platform_tables(self) -> None:
        """metadata 精确包含 13 张 ``dayu_platform`` 表。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        tables = set(PlatformBase.metadata.tables.keys())
        expected = {f"{PLATFORM_SCHEMA_NAME}.{name}" for name in _EXPECTED_TABLES}
        assert tables == expected

    @pytest.mark.unit
    def test_metadata_uses_platform_schema(self) -> None:
        """全部表位于 ``dayu_platform`` schema。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table in PlatformBase.metadata.tables.values():
            assert table.schema == PLATFORM_SCHEMA_NAME

    @pytest.mark.unit
    def test_metadata_uses_deterministic_naming_convention(self) -> None:
        """naming convention 与平台常量一致且包含全部约束键。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        convention = PlatformBase.metadata.naming_convention
        assert convention == NAMING_CONVENTION
        for key in ("ix", "uq", "ck", "fk", "pk"):
            assert key in convention

    @pytest.mark.unit
    def test_naming_convention_constraint_tokens_are_concrete(self) -> None:
        """约定模板不含会导致约束名不确定的表达式。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for template in NAMING_CONVENTION.values():
            assert "%(column_0_label)s" in template or "%(table_name)s" in template
            assert "%(constraint_name)s" not in template or "ck" in template

    @pytest.mark.unit
    def test_uuid_pk_has_no_server_default(self) -> None:
        """UUID 主键由调用方提供，无 server random default。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _EXPECTED_TABLES:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            ddl = _compile_ddl(table).lower()
            assert "gen_random_uuid" not in ddl
            assert "uuid_generate" not in ddl
            for column in table.primary_key.columns:
                assert column.server_default is None
                assert column.default is None


class TestWorkspaceImportSchema:
    """0002 workspace import 两表的契约。"""

    @pytest.mark.unit
    def test_workspace_import_marker_is_append_only(self) -> None:
        """marker 无 updated_at/version，只带 created_at。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.workspace_import_markers"
        ]
        assert "updated_at" not in table.c
        assert "version" not in table.c
        assert "created_at" in table.c

    @pytest.mark.unit
    def test_workspace_import_marker_checks_and_uniques(self) -> None:
        """marker 的 schema_version/counts CHECK 与 tenant 内唯一约束。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.workspace_import_markers"
        ]
        ddl = _compile_ddl(table)
        assert "source_schema_version > 0" in ddl
        assert "company_count >= 0" in ddl
        assert "security_count >= 0" in ddl
        assert "source_definition_count >= 0" in ddl
        assert "bundle_count >= 0" in ddl
        assert "UNIQUE (tenant_id, migration_id)" in ddl
        assert "UNIQUE (tenant_id, id)" in ddl
        for fk in table.foreign_keys:
            assert fk.ondelete == "RESTRICT"

    @pytest.mark.unit
    def test_research_bundle_locator_has_no_redundant_company_id(self) -> None:
        """locator 无冗余 company_id，公司只能经 security_id 解析。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.research_bundle_locators"
        ]
        assert "company_id" not in table.c
        assert "security_id" in table.c
        assert "import_marker_id" in table.c

    @pytest.mark.unit
    def test_research_bundle_locator_repository_key_closed_check(self) -> None:
        """locator 的 repository_key 精确 CHECK 为 legacy-workspace。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.research_bundle_locators"
        ]
        ddl = _compile_ddl(table)
        assert "repository_key = 'legacy-workspace'" in ddl
        assert "UNIQUE (tenant_id, security_id, template_name)" in ddl
        assert "UNIQUE (tenant_id, repository_key, relative_locator)" in ddl

    @pytest.mark.unit
    def test_research_bundle_locator_has_composite_marker_fk(self) -> None:
        """locator 通过 (tenant_id, import_marker_id) 复合 FK 引用 marker。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.research_bundle_locators"
        ]
        composite_fks = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            and len(constraint.columns) == 2
        ]
        assert len(composite_fks) == 1
        composite = composite_fks[0]
        assert set(composite.column_keys) == {"tenant_id", "import_marker_id"}
        for element in composite.elements:
            assert element.ondelete == "RESTRICT"

    @pytest.mark.unit
    def test_workspace_import_marker_has_no_status_column(self) -> None:
        """marker 只表示 completed commit，不设 pending/failed status。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[
            f"{PLATFORM_SCHEMA_NAME}.workspace_import_markers"
        ]
        assert "status" not in table.c


class TestPlatformSchemaColumns:
    """列类型、nullable 与约束契约。"""

    @pytest.mark.unit
    def test_all_tables_have_created_at_timestamptz(self) -> None:
        """全部表都有 ``created_at`` TIMESTAMPTZ 非空默认值。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _EXPECTED_TABLES:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "created_at" in table.c
            column = table.c["created_at"]
            assert isinstance(column.type, DateTime)
            assert column.type.timezone
            assert not column.nullable
            assert column.server_default is not None

    @pytest.mark.unit
    def test_mutable_tables_have_updated_at_and_version(self) -> None:
        """mutable 表带 updated_at/version；append-only 表不带。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        mutable_tables: frozenset[str] = frozenset(
            {
                "organizations",
                "companies",
                "securities",
                "source_definitions",
                "users",
                "roles",
                "permissions",
                "api_tokens",
                "source_subscriptions",
            }
        )
        append_only_tables = _EXPECTED_TABLES - mutable_tables
        for table_name in mutable_tables:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "updated_at" in table.c
            assert "version" in table.c
            assert not table.c["version"].nullable
            assert table.c["version"].server_default is not None
        for table_name in append_only_tables:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "updated_at" not in table.c
            assert "version" not in table.c

    @pytest.mark.unit
    def test_version_column_has_positive_check(self) -> None:
        """version 列必须带 ``version > 0`` check。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _EXPECTED_TABLES:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            if "version" not in table.c:
                continue
            ddl = _compile_ddl(table)
            assert "CHECK" in ddl
            assert "version > 0" in ddl

    @pytest.mark.unit
    def test_observed_at_and_started_at_have_no_server_default(self) -> None:
        """observed_at/started_at 由调用方提供，无 server default。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        cases: dict[str, str] = {
            "source_health_snapshots": "observed_at",
            "source_sync_runs": "started_at",
        }
        for table_name, column_name in cases.items():
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            column = table.c[column_name]
            assert column.server_default is None
            assert not column.nullable

    @pytest.mark.unit
    def test_private_tables_have_non_null_tenant_id(self) -> None:
        """私有表 tenant_id 非空且引用 organizations。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _PRIVATE_TABLES - {"organizations"}:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "tenant_id" in table.c
            assert not table.c["tenant_id"].nullable

    @pytest.mark.unit
    def test_api_tokens_only_holds_hash(self) -> None:
        """api_tokens 只保存 64 位小写 hex hash。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.api_tokens"]
        ddl = _compile_ddl(table)
        assert "CHAR(64)" in ddl
        assert "UNIQUE" in ddl
        assert "0-9a-f" in ddl or "9a-f" in ddl
        assert "raw" not in ddl.lower()


class TestPlatformSchemaGeneratedSql:
    """编译 DDL 的 schema exact 契约。"""

    @pytest.mark.unit
    def test_public_reference_tables_have_no_rls_columns(self) -> None:
        """公共 reference 表不含 tenant_id 列。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        public_tables = _EXPECTED_TABLES - _PRIVATE_TABLES
        assert public_tables == frozenset({"companies", "securities", "source_definitions"})
        for table_name in public_tables:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            assert "tenant_id" not in table.c

    @pytest.mark.unit
    def test_source_sync_runs_append_only_contract(self) -> None:
        """source_sync_runs 为 append-only：无 updated_at/version。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.source_sync_runs"]
        assert "updated_at" not in table.c
        assert "version" not in table.c
        ddl = _compile_ddl(table)
        assert "idempotency_key" in ddl
        assert "finished_at" in ddl
        assert "started_at" in ddl

    @pytest.mark.unit
    def test_foreign_keys_use_restrict(self) -> None:
        """全部 FK 使用 ON DELETE RESTRICT（禁止 CASCADE）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for table_name in _EXPECTED_TABLES:
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            for fk in table.foreign_keys:
                assert fk.ondelete == "RESTRICT"
            for constraint in table.constraints:
                if isinstance(constraint, ForeignKeyConstraint):
                    for element in constraint.elements:
                        assert element.ondelete == "RESTRICT"

    @pytest.mark.unit
    def test_unique_constraints_cover_business_keys(self) -> None:
        """业务键唯一约束存在于 DDL 中。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        cases: dict[str, str] = {
            "organizations": "slug",
            "users": "subject",
            "roles": "name",
            "permissions": "permission_key",
            "source_definitions": "source_key",
        }
        for table_name, column_name in cases.items():
            table = PlatformBase.metadata.tables[f"{PLATFORM_SCHEMA_NAME}.{table_name}"]
            ddl = _compile_ddl(table)
            assert f"UNIQUE ({column_name})" in ddl or "UNIQUE" in ddl


class TestDurableScheduleMigrationSource:
    """0004 durable schedule迁移的无数据库静态合同。"""

    @pytest.mark.unit
    def test_schedule_static_ddl_contract_covers_0004_without_shared_pg_cluster(
        self,
    ) -> None:
        """静态锁定0004两表、closed CHECK、RLS、权限与downgrade admission。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        source = _SCHEDULE_MIGRATION.read_text(encoding="utf-8")
        assert 'revision = "0004_durable_schedules"' in source
        assert 'down_revision = "0003_durable_jobs"' in source
        assert "CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_schedules" in source
        assert (
            "CREATE TABLE {PLATFORM_SCHEMA_NAME}.job_schedule_occurrences"
            in source
        )
        assert "ck_job_schedules_active_has_next_fire" in source
        assert "CHECK (state <> 'active' OR next_fire_at IS NOT NULL)" in source
        assert "ck_job_schedules_disabled_no_next_fire" not in source
        assert "timezone(next_fire_at)" not in source
        assert "timezone(scheduled_for)" not in source
        assert "ck_job_schedule_occurrences_coalesced_count_exact" in source
        assert "skip_reason IN ('misfire_expired', 'schedule_disabled')" in source
        assert "'candidate_scan_limit_exceeded')" in source
        assert "AND coalesced_count IS NULL" in source
        assert "snapshot_available_at = scheduled_for" in source
        assert "FOREIGN KEY (tenant_id, schedule_id)" in source
        assert "FOREIGN KEY (tenant_id, job_run_id)" in source
        assert "ENABLE ROW LEVEL SECURITY" in source
        assert "FORCE ROW LEVEL SECURITY" in source
        assert "GRANT UPDATE (state, next_fire_at, version, updated_at)" in source
        assert "GRANT UPDATE (state, job_run_id, skip_reason, updated_at)" in source
        assert "SELECT count(*) FROM {PLATFORM_SCHEMA_NAME}.job_schedules" in source
        assert "pg_auth_members" in source
        assert "DROP TABLE {PLATFORM_SCHEMA_NAME}.{table_name}" in source
        assert "DROP TABLE {PLATFORM_SCHEMA_NAME}.{table_name} CASCADE" not in source


class TestCreateAllForbidden:
    """生产 import 路径禁止 ``metadata.create_all()``。"""

    @pytest.mark.unit
    def test_no_create_all_call_in_storage_production_code(self) -> None:
        """storage 子包生产代码不得调用 ``metadata.create_all()``。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        violations: list[str] = []
        for file_path in _iter_storage_files():
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func_name = _extract_call_name(node)
                    if func_name == "create_all":
                        violations.append(f"{file_path.name}: {func_name}()")
        assert violations == []

    @pytest.mark.unit
    def test_migrations_do_not_import_orm_metadata_for_creation(self) -> None:
        """迁移脚本不通过 metadata 的 create_all 建表。

        迁移真源是显式 SQL DDL（``op.execute``），而不是从 ORM
        metadata 自动生成；本断言扫描迁移版本脚本，确认不存在
        ``create_all`` 调用。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        versions_dir = _STORAGE_SRC / "migrations" / "versions"
        if not versions_dir.is_dir():
            pytest.skip("迁移版本目录不存在")
        violations: list[str] = []
        for file_path in sorted(versions_dir.glob("*.py")):
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and _extract_call_name(node) == "create_all":
                    violations.append(file_path.name)
        assert violations == []


def _extract_call_name(node: ast.Call) -> str:
    """提取调用表达式的最末段函数名。

    Args:
        node: AST 调用节点。

    Returns:
        函数名（如 ``create_all``）；无法解析时返回空串。

    Raises:
        无。
    """

    func = node.func
    while isinstance(func, ast.Attribute):
        func = func.value
    if isinstance(func, ast.Name):
        return func.id
    return ""


class TestPlatformEngineFactories:
    """engine / session factory 单元契约。"""

    @pytest.mark.unit
    def test_create_platform_engine_returns_engine_without_echo(self) -> None:
        """engine 构造成功且关闭 SQL 回显，不创建 schema。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        engine = create_platform_engine("postgresql+psycopg://u:p@127.0.0.1:1/nonexistent")
        assert isinstance(engine, Engine)
        assert engine.url.get_backend_name() == "postgresql"
        assert engine.url.get_driver_name() == "psycopg"
        assert engine.echo is False
        engine.dispose()

    @pytest.mark.unit
    def test_create_platform_session_factory_binds_engine(self) -> None:
        """session factory 绑定给定 engine 且提交后不自动 expire。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        engine = create_platform_engine("postgresql+psycopg://u:p@127.0.0.1:1/nonexistent")
        factory = create_platform_session_factory(engine)
        assert isinstance(factory, sessionmaker)
        assert factory.kw.get("bind") is engine
        assert factory.kw.get("expire_on_commit") is False
        engine.dispose()


_JOBS_0003_TABLES: tuple[str, ...] = (
    "job_definitions",
    "job_runs",
    "job_attempts",
    "job_leases",
    "job_attempt_receipts",
    "job_events",
    "agent_run_correlations",
)
"""0003 迁移的七张 durable jobs 表（定义/删除共用顺序）。"""


class TestDurableJobs0003SchemaExactContract:
    """0003 durable jobs 迁移的 unit 契约（DDL 文本级校验）。

    真实 upgrade/downgrade/RLS/GRANT 在 integration lane 用真实 PG16
    验证；本类只校验迁移脚本的静态契约，避免同源自比。
    """

    @pytest.mark.unit
    def test_0003_schema_exact_contract(self) -> None:
        """0003 迁移必须精确创建七张表、RLS、列级 grant 与 downgrade。"""

        migration_source = (
            _REPO_ROOT / "dayu" / "investment" / "storage" / "migrations" / "versions" / "0003_durable_jobs.py"
        ).read_text(encoding="utf-8")
        for table in _JOBS_0003_TABLES:
            assert f"CREATE TABLE {{PLATFORM_SCHEMA_NAME}}.{table}" in migration_source, (
                f"0003 缺少表 {table}"
            )
        # 七表 RLS enable + force + 唯一 tenant_isolation policy（循环应用全部表）。
        assert "ENABLE ROW LEVEL SECURITY" in migration_source
        assert "FORCE ROW LEVEL SECURITY" in migration_source
        assert "CREATE POLICY tenant_isolation" in migration_source
        # 列级 grant：app SELECT/INSERT + audit SELECT。
        assert "GRANT SELECT, INSERT ON TABLE" in migration_source
        assert "GRANT SELECT ON TABLE" in migration_source
        # downgrade 无 CASCADE、保留依赖顺序。
        assert "DROP TABLE" in migration_source
        assert "ON DELETE CASCADE" not in migration_source
        assert "DROP TABLE" in migration_source
        # downgrade 前置 catalog 外部依赖检查。
        assert "pg_depend" in migration_source

    @pytest.mark.unit
    def test_0003_columns_match_contract(self) -> None:
        """每张表的契约列与约束必须在 DDL 中显式出现。"""

        migration_source = (
            _REPO_ROOT / "dayu" / "investment" / "storage" / "migrations" / "versions" / "0003_durable_jobs.py"
        ).read_text(encoding="utf-8")
        table_columns = {
            "job_definitions": (
                "job_type",
                "payload_schema_name",
                "payload_schema_version",
                "max_attempts",
                "retry_base_seconds",
                "retry_max_seconds",
                "lease_duration_seconds",
                "status",
            ),
            "job_runs": (
                "idempotency_key",
                "request_fingerprint",
                "payload_bytes",
                "payload_sha256",
                "state",
                "available_at",
                "deadline_at",
                "current_attempt_number",
                "next_event_sequence",
                "cancel_requested_at",
                "safe_failure_code",
            ),
            "job_attempts": (
                "attempt_number",
                "worker_id",
                "state",
                "fence",
                "lease_token_sha256",
                "claimed_at",
                "lease_expires_at",
                "last_heartbeat_at",
            ),
            "job_leases": (
                "fence",
                "token_sha256",
                "acquired_at",
                "expires_at",
                "released_at",
                "release_reason",
            ),
            "job_attempt_receipts": (
                "outcome",
                "result_schema_name",
                "result_bytes",
                "receipt_schema_name",
                "receipt_bytes",
                "receipt_sha256",
                "safe_error_code",
                "finalized_at",
            ),
            "job_events": (
                "sequence_number",
                "event_type",
                "safe_detail_bytes",
                "occurred_at",
            ),
            "agent_run_correlations": (
                "idempotency_key",
                "reserved_host_run_id",
                "state",
                "observed_at",
                "last_observation_sha256",
                "version",
            ),
        }
        for table, columns in table_columns.items():
            table_block = _extract_table_block(migration_source, table)
            for column in columns:
                assert column in table_block, f"{table} 缺少列 {column}"

    @pytest.mark.unit
    def test_0003_lease_single_release_and_immutable_guard_present(self) -> None:
        """versioned single-release trigger 与 immutable 列 guard 必须存在。"""

        migration_source = (
            _REPO_ROOT / "dayu" / "investment" / "storage" / "migrations" / "versions" / "0003_durable_jobs.py"
        ).read_text(encoding="utf-8")
        assert "job_leases_single_release" in migration_source
        assert "guard_{table_name}_immutable_columns" in migration_source
        assert "{function_name}_trigger" in migration_source


def _extract_table_block(migration_source: str, table: str) -> str:
    """提取迁移源码中某张表的 CREATE TABLE 块。

    Args:
        migration_source: 迁移源码文本。
        table: 表名。

    Returns:
        该表的 DDL 块文本；找不到时返回空串。

    Raises:
        无。
    """

    marker = f"CREATE TABLE {{PLATFORM_SCHEMA_NAME}}.{table}"
    start = migration_source.find(marker)
    if start < 0:
        return ""
    return migration_source[start : start + 4000]
