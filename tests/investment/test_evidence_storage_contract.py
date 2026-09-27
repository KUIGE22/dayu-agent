"""S31-A evidence ORM 与 0007 静态契约。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Numeric
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from dayu.investment.storage import PLATFORM_SCHEMA_NAME, PlatformBase

pytestmark = pytest.mark.unit

_TABLES = frozenset({
    "facts", "claims", "claim_versions", "evidence_links",
    "claim_conflicts", "research_candidates",
})
_MIGRATION = Path(__file__).resolve().parents[2] / "dayu/investment/storage/migrations/versions/0007_strict_evidence.py"


def _load_migration():
    """按文件路径加载 0007，避免数字前缀 import 语法。

    Args:
        无。

    Returns:
        已加载的 0007 迁移模块。

    Raises:
        AssertionError: 模块规格或 loader 缺失。
    """

    spec = importlib.util.spec_from_file_location("strict_evidence_0007_contract", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_six_private_mapped_tables_and_unrounded_decimal() -> None:
    """新增六表精确注册，Fact decimal 原值不经 typmod 舍入。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 映射表集合、列或 numeric typmod 漂移。
    """

    metadata = PlatformBase.metadata
    assert len(metadata.tables) == 24
    assert _TABLES <= {table.name for table in metadata.tables.values()}
    fact = metadata.tables[f"{PLATFORM_SCHEMA_NAME}.facts"]
    security = metadata.tables[f"{PLATFORM_SCHEMA_NAME}.securities"]
    assert any(c.name == "uq_securities_company_id_id_ticker" for c in security.constraints)
    assert isinstance(fact.c.value_decimal.type, Numeric)
    assert fact.c.value_decimal.type.precision is None
    assert fact.c.value_decimal.type.scale is None
    for name in ("security_id", "locator_ticker", "locator_json", "metric", "effective_at"):
        assert not fact.c[name].nullable
    ddl = str(CreateTable(fact).compile(dialect=postgresql.dialect()))
    assert "value_decimal NUMERIC" in ddl
    assert "value_decimal NUMERIC(" not in ddl
    assert "ck_facts_locator_ticker" in ddl
    assert "IS TRUE" in ddl
    assert "evidence_decimal_valid" in ddl


def test_fk_closure_and_link_arm_index() -> None:
    """租户、公司、证券与直接证据目标在 ORM 中闭合。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 复合 FK、目标 arm 或唯一键漂移。
    """

    metadata = PlatformBase.metadata
    fact = metadata.tables[f"{PLATFORM_SCHEMA_NAME}.facts"]
    link = metadata.tables[f"{PLATFORM_SCHEMA_NAME}.evidence_links"]
    version = metadata.tables[f"{PLATFORM_SCHEMA_NAME}.claim_versions"]
    conflict = metadata.tables[f"{PLATFORM_SCHEMA_NAME}.claim_conflicts"]
    assert {"security_id", "locator_ticker", "locator_json", "locator_index_digest"} <= set(link.c.keys())
    security_fks = [
        constraint for table in (fact, link) for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name in {"fk_facts_security_ticker", "fk_evidence_links_security_ticker"}
    ]
    assert len(security_fks) == 2
    assert all(tuple(fk.column_keys) == ("company_id", "security_id", "locator_ticker") for fk in security_fks)
    target = next(c for c in link.constraints if isinstance(c, CheckConstraint) and c.name == "ck_evidence_links_target_arm")
    expression = str(target.sqltext)
    assert all(f"{name} IS NULL" in expression for name in ("security_id", "locator_ticker", "locator_json", "locator_index_digest"))
    assert all(f"{name} IS NOT NULL" in expression for name in ("security_id", "locator_ticker", "locator_json", "locator_index_digest"))
    assert expression.endswith("IS TRUE")
    direct = next(i for i in link.indexes if i.name == "uq_evidence_links_direct_digest")
    assert direct.unique
    assert tuple(col.name for col in direct.columns) == (
        "tenant_id", "claim_version_id", "relation", "security_id", "locator_index_digest"
    )
    assert str(direct.dialect_options["postgresql"]["where"]) == "fact_id IS NULL"
    assert any(c.name == "fk_claim_versions_copy_source" for c in version.constraints)
    assert any(c.name == "fk_claim_conflicts_resolution_link" for c in conflict.constraints)


def test_frozen_migration_has_exact_six_tables_and_0006_parent() -> None:
    """0007 静态 DDL 不在迁移时导入可漂移的 ORM。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 静态 DDL 或迁移谱系漂移。
    """

    migration = _load_migration()
    assert migration.down_revision == "0006_job_request_identity"
    assert tuple(migration._TABLES) == (
        "facts", "claims", "claim_versions", "evidence_links",
        "claim_conflicts", "research_candidates",
    )
    assert len(migration._TABLE_DDL) == 6
    assert len(migration._INDEX_DDL) == 5
    assert "security_id, locator_index_digest" in " ".join(migration._INDEX_DDL)
    assert "sha256(convert_to(NEW.locator_json::text, 'UTF8'))" in migration._DIGEST_FUNCTION
    assert "RESTRICT" in _MIGRATION.read_text()
