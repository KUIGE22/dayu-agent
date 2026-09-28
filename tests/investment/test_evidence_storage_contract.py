"""当前 head metadata、S31 evidence ORM 与冻结 0007 静态契约。"""

from __future__ import annotations

import ast
import importlib.util
import inspect
from pathlib import Path
from typing import get_type_hints
from uuid import UUID

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Numeric
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from dayu.investment.domain.evidence import (
    ClaimConflict,
    ClaimConflictOpenRequest,
    ClaimConflictResolveRequest,
    ClaimCreateRequest,
    ClaimLocalEligibility,
    ClaimReviewRequest,
    ClaimRevisionBeginRequest,
    ClaimSnapshot,
    ClaimVersionAppendRequest,
    Fact,
    FactCreateRequest,
    ResearchCandidate,
    ResearchCandidateCreateRequest,
)
from dayu.investment.domain.identifiers import TenantScope
from dayu.investment.storage import PLATFORM_SCHEMA_NAME, PlatformBase
from dayu.investment.storage.evidence_protocols import (
    EvidenceConflictError,
    EvidenceDigestCollisionError,
    EvidenceDuplicateTargetError,
    EvidenceErrorCode,
    EvidenceInputError,
    EvidenceMaterializationNeededError,
    EvidenceNotFoundError,
    EvidenceOptimisticConflictError,
    EvidenceRepositoryError,
    EvidenceRepositoryProtocol,
    EvidenceUnauthorizedError,
)

pytestmark = pytest.mark.unit

_TABLES = frozenset({
    "facts", "claims", "claim_versions", "evidence_links",
    "claim_conflicts", "research_candidates",
})
_MIGRATION = Path(__file__).resolve().parents[2] / "dayu/investment/storage/migrations/versions/0007_strict_evidence.py"
_PROTOCOL = Path(__file__).resolve().parents[2] / "dayu/investment/storage/evidence_protocols.py"
_METHODS = (
    "create_fact", "get_fact", "list_fact_revisions", "create_claim", "get_claim",
    "append_claim_version", "begin_claim_revision", "record_claim_review",
    "open_conflict", "resolve_conflict_with_review", "local_claim_eligibility",
    "create_proposed_candidate", "get_candidate",
)


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
    """当前 head 注册 25 表，冻结 evidence 六表与无舍入 decimal 契约。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 映射表集合、列或 numeric typmod 漂移。
    """

    metadata = PlatformBase.metadata
    assert len(metadata.tables) == 25
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


def test_evidence_protocol_has_exact_pure_signatures_and_no_free_reviewer_identity() -> None:
    """十三入口只传纯领域类型，自认证入口没有自由身份参数。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 方法、参数顺序或类型边界漂移。
    """

    declared = tuple(
        name for name, value in EvidenceRepositoryProtocol.__dict__.items()
        if not name.startswith("_") and inspect.isfunction(value)
    )
    assert declared == _METHODS
    expected = {
        "create_fact": (("self", "scope", "request"), FactCreateRequest, Fact),
        "get_fact": (("self", "scope", "fact_id"), UUID, Fact | None),
        "list_fact_revisions": (("self", "scope", "company_id", "fact_series_id"), UUID, tuple[Fact, ...]),
        "create_claim": (("self", "scope", "request"), ClaimCreateRequest, ClaimSnapshot),
        "get_claim": (("self", "scope", "claim_id"), UUID, ClaimSnapshot | None),
        "append_claim_version": (("self", "scope", "request"), ClaimVersionAppendRequest, ClaimSnapshot),
        "begin_claim_revision": (
            ("self", "scope_hint", "raw_token", "request"), ClaimRevisionBeginRequest, ClaimSnapshot,
        ),
        "record_claim_review": (("self", "scope_hint", "raw_token", "request"), ClaimReviewRequest, ClaimSnapshot),
        "open_conflict": (("self", "scope", "request"), ClaimConflictOpenRequest, ClaimConflict),
        "resolve_conflict_with_review": (
            ("self", "scope_hint", "raw_token", "request"), ClaimConflictResolveRequest, ClaimConflict,
        ),
        "local_claim_eligibility": (("self", "scope", "claim_id"), UUID, ClaimLocalEligibility),
        "create_proposed_candidate": (
            ("self", "scope", "request"), ResearchCandidateCreateRequest, ResearchCandidate,
        ),
        "get_candidate": (("self", "scope", "candidate_id"), UUID, ResearchCandidate | None),
    }
    for name, (parameters, last_type, return_type) in expected.items():
        method = EvidenceRepositoryProtocol.__dict__[name]
        assert inspect.isfunction(method) and not inspect.iscoroutinefunction(method)
        signature = inspect.signature(method)
        assert tuple(signature.parameters) == parameters
        assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())
        hints = get_type_hints(method)
        scope_name = "scope_hint" if "scope_hint" in parameters else "scope"
        assert hints[scope_name] is TenantScope
        if name == "list_fact_revisions":
            assert hints["company_id"] is UUID
        assert hints[parameters[-1]] == last_type
        assert hints["return"] == return_type
        if "raw_token" in parameters:
            assert hints["raw_token"] is bytes
            assert not {"author_user_id", "reviewer_user_id", "permission_id", "checked_at"} & set(parameters)


def test_evidence_protocol_imports_only_domain_and_standard_library() -> None:
    """协议源文件不得依赖 SQL、认证实现或外部资料模块。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 协议越过纯领域边界。
    """

    tree = ast.parse(_PROTOCOL.read_text(encoding="utf-8"))
    imported = {node.module for node in tree.body if isinstance(node, ast.ImportFrom)}
    assert imported == {
        "__future__", "enum", "typing", "uuid",
        "dayu.investment.domain.evidence", "dayu.investment.domain.identifiers",
    }
    assert not any(isinstance(node, ast.Import) for node in tree.body)


def test_evidence_protocol_errors_have_closed_fixed_safe_codes() -> None:
    """调用方可按稳定错误类型分支，异常文本不接收候选输入。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 错误层级或固定消息漂移。
    """

    cases = (
        (EvidenceRepositoryError, EvidenceErrorCode.STORAGE_FAILURE),
        (EvidenceInputError, EvidenceErrorCode.INVALID_INPUT),
        (EvidenceNotFoundError, EvidenceErrorCode.NOT_FOUND),
        (EvidenceConflictError, EvidenceErrorCode.CONFLICT),
        (EvidenceOptimisticConflictError, EvidenceErrorCode.OPTIMISTIC_CONFLICT),
        (EvidenceDuplicateTargetError, EvidenceErrorCode.DUPLICATE_TARGET),
        (EvidenceDigestCollisionError, EvidenceErrorCode.DIGEST_COLLISION),
        (EvidenceMaterializationNeededError, EvidenceErrorCode.REVIEW_REQUIRED_MATERIALIZATION_NEEDED),
        (EvidenceUnauthorizedError, EvidenceErrorCode.UNAUTHORIZED),
    )
    for error_type, code in cases:
        error = error_type()
        assert isinstance(error, EvidenceRepositoryError)
        assert error.code is code
        assert str(error) == code.value
        assert tuple(inspect.signature(error_type.__init__).parameters) == ("self",)
    assert issubclass(EvidenceOptimisticConflictError, EvidenceConflictError)
    assert issubclass(EvidenceDigestCollisionError, EvidenceConflictError)
