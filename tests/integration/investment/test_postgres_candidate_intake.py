"""S32-A 真PG16 candidate+receipt原子性、不可变重试与0008安全门。

真实Service、identity和intake仓储组合；Fins只使用公共protocol替身，不替代SQL。
独占随机库沿用head fixture，同批七表清理，不停RLS/约束/append-only trigger。
"""

from __future__ import annotations

import hashlib
import importlib
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Barrier, Lock, get_ident
from typing import TypeAlias
from uuid import UUID, uuid4

import pytest
from alembic import command
from psycopg import Error as PsycopgError
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, ExceptionContext
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from dayu.fins.domain.evidence_locator import EvidenceLocatorError
from dayu.investment.domain.candidate_intake import (
    CandidateFinsValidationWitness,
    CandidateIntakeContext,
    CandidateIntakeReceipt,
    CandidateIntakeRecordRequest,
    CandidateIntakeRejectionCode,
    intake_request_fingerprint,
)
from dayu.investment.domain.candidate_parsing import parse_fact_candidate
from dayu.investment.domain.evidence import CandidateOrigin, CandidateStatus, canonical_json_bytes
from dayu.investment.domain.identifiers import Principal, TenantId
from dayu.investment.storage import postgres_candidate_intake as intake_module
from dayu.investment.storage.db import PLATFORM_APP_ROLE, PLATFORM_AUDIT_ROLE, PlatformMigrationAdmissionError
from dayu.investment.storage.evidence_protocols import (
    EvidenceConflictError,
    EvidenceInputError,
    EvidenceRepositoryError,
)
from dayu.investment.storage.models_candidate_intake import CandidateIntakeReceiptRow
from dayu.investment.storage.postgres_candidate_intake import PostgresCandidateIntakeRepository
from dayu.investment.storage.postgres_identity import PostgresIdentityRepository
from dayu.services.investment_research import InvestmentResearchService, ResearchContextError, ResearchDependencyError
from tests.integration.investment.conftest import PlatformCluster, _alembic_config
from tests.integration.investment.test_postgres_evidence import _RepositoryDatabase
from tests.integration.investment.test_postgres_evidence import repository_database as repository_database
from tests.investment.test_candidate_intake_service import _Fins
from tests.investment.test_candidate_parsing import proposal

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)
_TABLE = "dayu_platform.candidate_intake_receipts"
_OWN_TABLES = (
    "candidate_intake_receipts",
    "research_candidates",
    "facts",
    "claims",
    "claim_versions",
    "evidence_links",
    "claim_conflicts",
)
_ReceiptReader = Callable[[Session, UUID, UUID], CandidateIntakeReceiptRow | None]


def _context(db: _RepositoryDatabase) -> CandidateIntakeContext:
    """生成fixture内有效caller身份。

    Args:
        db: 独占库句柄。
    Returns:
        非nil完整context。
    Raises:
        无。
    """
    return CandidateIntakeContext(uuid4(), uuid4(), db.company, db.security_a, CandidateOrigin.AGENT, "pg.v1")


def _raw(fins: _Fins, *, ticker: str = "ABC") -> bytes:
    """绑定公共Fins返回内容的真实SHA，不发网络请求。

    Args:
        fins: 公共protocol替身。
        ticker: 明确证券ticker。
    Returns:
        合法九键proposal bytes。
    Raises:
        无。
    """
    value = proposal()
    locator = value["locator"]
    assert isinstance(locator, dict)
    locator.update(ticker=ticker, locator_content_sha256=hashlib.sha256(fins.content).hexdigest())
    return canonical_json_bytes(value)


def _request(context: CandidateIntakeContext, raw: bytes) -> CandidateIntakeRecordRequest:
    """生成已经过观察的typed仓储请求。

    Args:
        context: 明确caller身份。
        raw: 完整合法proposal。
    Returns:
        proposal和SHA绑定witness。
    Raises:
        CandidateParseError: 测试输入非法。
    """
    payload = parse_fact_candidate(raw)
    witness = CandidateFinsValidationWitness(
        hashlib.sha256(payload.locator.canonical_bytes()).hexdigest(), payload.locator.locator_content_sha256, _NOW
    )
    return CandidateIntakeRecordRequest(
        context, payload.locator.ticker, hashlib.sha256(raw).hexdigest(), len(raw), payload, witness, None
    )


def _snapshot(db: _RepositoryDatabase) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """回读全部相关表完整JSON行，验证故障前后没有隐藏副作用。

    Args:
        db: 独占admin连接工厂。
    Returns:
        七表完整稳定排序快照。
    Raises:
        DBAPIError: 真SQL失败。
    """
    with db.admin.connect() as connection:
        return tuple(
            (
                name,
                tuple(
                    connection.execute(
                        text(f"SELECT row_to_json(r)::text FROM dayu_platform.{name} r ORDER BY row_to_json(r)::text")
                    ).scalars()
                ),
            )
            for name in _OWN_TABLES
        )


def _counts(db: _RepositoryDatabase) -> tuple[int, ...]:
    """读取七表精确行数。

    Args:
        db: 独占库。
    Returns:
        receipt/candidate/五权威表的计数。
    Raises:
        DBAPIError: 真SQL失败。
    """
    return tuple(len(rows) for _, rows in _snapshot(db))


def _service(db: _RepositoryDatabase, fins: _Fins) -> InvestmentResearchService:
    """装配真实Service/identity/intake仓储与明确公共Fins依赖。

    Args:
        db: 真PG fixture。
        fins: 公共owner替身。
    Returns:
        当前生产Service。
    Raises:
        无。
    """
    return InvestmentResearchService(
        PostgresIdentityRepository(db.sessions), PostgresCandidateIntakeRepository(db.sessions), fins, lambda: _NOW
    )


def _revision(db: _RepositoryDatabase, cluster: PlatformCluster, target: str, *, upgrade: bool) -> None:
    """只在owned随机库执行显式revision，不泄漏合成DSN。

    Args:
        db: 独占随机库。
        cluster: owner cluster。
        target: 精确revision。
        upgrade: 升迁或回退。
    Returns:
        无。
    Raises:
        PlatformMigrationAdmissionError: 保留迁移拒绝。
        DBAPIError: 保留真SQL失败。
    """
    database = db.admin.url.database
    assert type(database) is str
    previous = os.environ.get("DAYU_PLATFORM_POSTGRES_DSN")
    os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = cluster.dsn_for_database(database, "postgres")
    try:
        if upgrade:
            command.upgrade(_alembic_config(), target)
        else:
            command.downgrade(_alembic_config(), target)
    finally:
        if previous is None:
            os.environ.pop("DAYU_PLATFORM_POSTGRES_DSN", None)
        else:
            os.environ["DAYU_PLATFORM_POSTGRES_DSN"] = previous


def _head(db: _RepositoryDatabase) -> str:
    """读取实际revision。

    Args:
        db: 独占库。
    Returns:
        版本名。
    Raises:
        DBAPIError: 真SQL失败。
    """
    with db.admin.connect() as connection:
        value = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one()
        assert type(value) is str
        return value


def test_real_service_pg_success_and_historical_retry(repository_database: _RepositoryDatabase) -> None:
    """成功、响应丢失、source漂移和mutable head变化仍恢复首receipt。

    Args:
        repository_database: 真PG fixture。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    fins = _Fins()
    context, raw = _context(db), _raw(fins)
    service = _service(db, fins)
    receipt = service.ingest_candidate(db.scope, context, raw)
    assert receipt.outcome is CandidateStatus.PROPOSED and receipt.candidate_version == 1
    assert receipt.witness is not None and receipt.witness.checked_at == _NOW
    assert _counts(db) == (1, 1, 0, 0, 0, 0, 0)
    with db.admin.connect() as connection:
        candidate = connection.execute(
            text(
                "SELECT canonical_payload_json,sha256,version,state FROM dayu_platform.research_candidates WHERE id=:id"
            ),
            {"id": context.candidate_id},
        ).one()
        assert canonical_json_bytes(candidate[0]) == parse_fact_candidate(raw).canonical_bytes()
        assert candidate[1:] == (receipt.payload_sha256, 1, "proposed")
    with db.admin.begin() as connection:
        connection.execute(
            text("UPDATE dayu_platform.research_candidates SET state='validated',version=2 WHERE id=:id"),
            {"id": context.candidate_id},
        )
    snapshot = _snapshot(db)
    fins.error = OSError("private path must never escape")
    assert service.ingest_candidate(db.scope, context, raw) == receipt
    assert (fins.validated, fins.reads) == (1, 1)
    assert _snapshot(db) == snapshot


@pytest.mark.parametrize(
    "raw,code",
    [
        (b'{"secret":"caller-secret"', "candidate_json_invalid"),
        (b'{"candidate_type":"claim"}', "unsupported_material_claim"),
        (b"{}", "candidate_schema_invalid"),
    ],
)
def test_real_pg_parser_rejection_is_safe_one_pair(
    repository_database: _RepositoryDatabase, raw: bytes, code: str
) -> None:
    """业务拒绝仅写安全四键，raw/异常message不持久化。

    Args:
        repository_database: 真PG fixture。
        raw: 非法输入。
        code: 固定拒绝码。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    fins = _Fins()
    receipt = _service(db, fins).ingest_candidate(db.scope, _context(db), raw)
    assert receipt.outcome is CandidateStatus.REJECTED and receipt.rejection_code is not None
    assert receipt.rejection_code.value == code and receipt.witness is None
    assert _counts(db) == (1, 1, 0, 0, 0, 0, 0)
    assert (fins.validated, fins.reads) == (0, 0)
    with db.admin.connect() as connection:
        payload = connection.execute(
            text("SELECT canonical_payload_json FROM dayu_platform.research_candidates")
        ).scalar_one()
        assert payload == {
            "schema_version": "rejected_intake.v1",
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_bytes": len(raw),
            "rejection_code": code,
        }
        assert b"caller-secret" not in canonical_json_bytes(payload)


@pytest.mark.parametrize(
    "code,expected",
    [
        ("source_identity_not_found", "evidence_unavailable"),
        ("source_deleted", "evidence_unavailable"),
        ("source_not_ingested", "evidence_unavailable"),
        ("processed_not_found", "evidence_unavailable"),
        ("processed_deleted", "evidence_unavailable"),
        ("processed_reprocess_required", "evidence_unavailable"),
        ("ambiguous_source_identity", "evidence_ambiguous_owner"),
        ("document_version_mismatch", "evidence_stale"),
        ("source_fingerprint_mismatch", "evidence_stale"),
        ("processed_source_kind_mismatch", "evidence_stale"),
        ("processed_version_mismatch", "evidence_stale"),
        ("processed_fingerprint_mismatch", "evidence_stale"),
        ("source_identity_changed", "evidence_stale"),
        ("primary_content_changed", "evidence_stale"),
        ("primary_sha_mismatch", "evidence_stale"),
        ("primary_content_sha256_mismatch", "evidence_stale"),
        ("locator_content_sha256_mismatch", "evidence_stale"),
        ("table_row_out_of_range", "evidence_fragment_unresolved"),
        ("table_column_missing", "evidence_fragment_unresolved"),
        ("page_not_supported", "evidence_fragment_unresolved"),
        ("xbrl_fact_not_unique", "evidence_fragment_unresolved"),
    ],
)
def test_each_fins_business_code_writes_only_one_rejected_pair(
    repository_database: _RepositoryDatabase,
    code: str,
    expected: str,
) -> None:
    """每个公共owner业务码通过真实Service+PG边界保存安全拒绝。

    Args:
        repository_database: 真PG fixture。
        code: closed公共错误码。
        expected: 固定接入拒绝码。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    fins = _Fins()
    fins.read_error = EvidenceLocatorError(code, "bounded test fault")
    receipt = _service(db, fins).ingest_candidate(db.scope, _context(db), _raw(fins))
    assert receipt.rejection_code is not None and receipt.rejection_code.value == expected
    assert _counts(db) == (1, 1, 0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "code",
    [
        "table_not_records",
        "xbrl_facts_unavailable",
        "invalid_locator_payload",
        "artifact_kind_not_supported",
        "meta_invalid",
        "read_failed",
        "unknown_code",
    ],
)
def test_fins_infrastructure_has_zero_pg_writes(repository_database: _RepositoryDatabase, code: str) -> None:
    """owner基础设施错误不能冒充业务拒绝结果。

    Args:
        repository_database: 真PG fixture。
        code: 非业务错误码。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    fins = _Fins()
    fins.error = EvidenceLocatorError(code, "bounded test fault")
    before = _snapshot(db)
    with pytest.raises(ResearchDependencyError, match="^research_dependency_unavailable$"):
        _service(db, fins).ingest_candidate(db.scope, _context(db), _raw(fins))
    assert _snapshot(db) == before


@pytest.mark.parametrize("kind", ["missing_security", "wrong_company", "cross_ticker", "readback"])
def test_context_cross_ticker_and_readback_boundaries(repository_database: _RepositoryDatabase, kind: str) -> None:
    """错误context零行，业务ticker/readback拒绝各一对。

    Args:
        repository_database: 真PG fixture。
        kind: 精确边界。
    Returns:
        无。
    Raises:
        无。
    """
    db, fins = repository_database, _Fins()
    context = _context(db)
    before = _snapshot(db)
    if kind == "missing_security":
        context = replace(context, security_id=uuid4())
    elif kind == "wrong_company":
        context = replace(context, company_id=uuid4())
    if kind in {"missing_security", "wrong_company"}:
        with pytest.raises(ResearchContextError):
            _service(db, fins).ingest_candidate(db.scope, context, _raw(fins))
        assert _snapshot(db) == before
        return
    if kind == "readback":
        fins.changed_locator = True
    receipt = _service(db, fins).ingest_candidate(
        db.scope, context, _raw(fins, ticker="OTHER" if kind == "cross_ticker" else "ABC")
    )
    assert receipt.rejection_code is (
        CandidateIntakeRejectionCode.CROSS_TICKER
        if kind == "cross_ticker"
        else CandidateIntakeRejectionCode.READBACK_MISMATCH
    )
    assert _counts(db) == (1, 1, 0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "change", ["raw", "candidate_id", "security_id", "origin", "extractor_version", "operation_id"]
)
def test_operation_identity_conflict_preserves_full_snapshot(
    repository_database: _RepositoryDatabase, change: str
) -> None:
    """不同不可变请求不能盲目复用原operation/candidate。

    Args:
        repository_database: 真PG fixture。
        change: 被更改字段。
    Returns:
        无。
    Raises:
        无。
    """
    db, fins = repository_database, _Fins()
    context, raw = _context(db), _raw(fins)
    service = _service(db, fins)
    service.ingest_candidate(db.scope, context, raw)
    before = _snapshot(db)
    if change == "raw":
        raw += b" "
    elif change == "candidate_id":
        context = replace(context, candidate_id=uuid4())
    elif change == "security_id":
        context = replace(context, security_id=db.security_b)
    elif change == "origin":
        context = replace(context, origin=CandidateOrigin.HUMAN)
    elif change == "extractor_version":
        context = replace(context, extractor_version="pg.v2")
    else:
        context = replace(context, operation_id=uuid4())
    with pytest.raises(EvidenceConflictError):
        service.ingest_candidate(db.scope, context, raw)
    assert _snapshot(db) == before


class _ReadBarrier:
    """只阻挡每个线程的首次requested receipt SELECT，允许恢复查询执行。"""

    def __init__(self, original: _ReceiptReader) -> None:
        """建立两连接同步点。

        Args:
            original: 当前实际SQL reader。
        Returns:
            无。
        Raises:
            无。
        """
        self.original = original
        self.barrier = Barrier(2)
        self.lock = Lock()
        self.seen: set[int] = set()

    def read(self, session: Session, tenant: UUID, operation: UUID) -> CandidateIntakeReceiptRow | None:
        """先真实SELECT再同步，使两事务都尝试首次INSERT。

        Args:
            session: 当前真PG Session。
            tenant: 请求租户。
            operation: 请求operation。
        Returns:
            原SQL行。
        Raises:
            BrokenBarrierError: 并发没有到达同步点。
        """
        result = self.original(session, tenant, operation)
        thread = get_ident()
        with self.lock:
            first = thread not in self.seen
            self.seen.add(thread)
        if first:
            self.barrier.wait(timeout=10)
        return result


class _ErrorKeys:
    """仅记录真实psycopg23505 constraint name，不存SQL/参数/message。"""

    def __init__(self) -> None:
        """建立观察列表。

        Args:
            无。
        Returns:
            无。
        Raises:
            无。
        """
        self.keys: list[str] = []

    def observe(self, context: ExceptionContext) -> None:
        """观察真PG错误边界。

        Args:
            context: SQLAlchemy真实错误事件。
        Returns:
            无。
        Raises:
            无。
        """
        error = context.original_exception
        if isinstance(error, PsycopgError) and error.sqlstate == "23505" and error.diag.constraint_name is not None:
            self.keys.append(error.diag.constraint_name)


def test_two_connections_same_request_returns_one_committed_receipt(
    repository_database: _RepositoryDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实唯一冲突回滚SAVEPOINT后新RC SELECT恢复首结果。

    Args:
        repository_database: 真PG fixture。
        monkeypatch: 只同步实际read，未模拟SQL结果。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    request = _request(_context(db), _raw(_Fins()))
    repository = PostgresCandidateIntakeRepository(db.sessions)
    gate = _ReadBarrier(intake_module._receipt_row)
    monkeypatch.setattr(intake_module, "_receipt_row", gate.read)
    keys = _ErrorKeys()
    with db.sessions() as session:
        engine = session.get_bind()
    event.listen(engine, "handle_error", keys.observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(repository.record_intake, db.scope, request) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
    finally:
        event.remove(engine, "handle_error", keys.observe)
    assert results[0] == results[1]
    assert len(keys.keys) == 1 and keys.keys[0] in {
        "pk_research_candidates",
        "uq_research_candidates_tenant_company_id",
        "uq_research_candidates_operation",
    }
    assert _counts(db) == (1, 1, 0, 0, 0, 0, 0)


def _race_result(
    repository: PostgresCandidateIntakeRepository, db: _RepositoryDatabase, request: CandidateIntakeRecordRequest
) -> CandidateIntakeReceipt | str:
    """将并发业务conflict转换为固定测试观察值。

    Args:
        repository: 真仓储。
        db: 真PG fixture。
        request: 完整request。
    Returns:
        receipt或固定conflict。
    Raises:
        其它异常保留。
    """
    try:
        return repository.record_intake(db.scope, request)
    except EvidenceConflictError:
        return "conflict"


@pytest.mark.parametrize("change", ["same_op_other_id", "same_id_other_op", "same_op_other_raw"])
def test_two_connections_conflicting_requests_do_not_reuse(
    repository_database: _RepositoryDatabase,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    """真实并发不同request仅一对胜出，失败方没有partial行。

    Args:
        repository_database: 真PG fixture。
        monkeypatch: 首次SELECT同步。
        change: 对立身份形状。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    request = _request(_context(db), _raw(_Fins()))
    if change == "same_op_other_id":
        other = replace(request, context=replace(request.context, candidate_id=uuid4()))
    elif change == "same_id_other_op":
        other = replace(request, context=replace(request.context, operation_id=uuid4()))
    else:
        other = replace(request, raw_sha256="f" * 64)
    gate = _ReadBarrier(intake_module._receipt_row)
    monkeypatch.setattr(intake_module, "_receipt_row", gate.read)
    repository = PostgresCandidateIntakeRepository(db.sessions)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_race_result, repository, db, item) for item in (request, other)]
        results = [future.result(timeout=15) for future in futures]
    assert sum(isinstance(result, CandidateIntakeReceipt) for result in results) == 1
    assert results.count("conflict") == 1 and _counts(db) == (1, 1, 0, 0, 0, 0, 0)


class _FirstMiss:
    """仅复现初始read尚未看见已提交历史；后续恢复必须走真SQL。"""

    def __init__(self, original: _ReceiptReader) -> None:
        """绑定真SQL reader。

        Args:
            original: 当前实际reader。
        Returns:
            无。
        Raises:
            无。
        """
        self.original, self.first = original, True

    def read(self, session: Session, tenant: UUID, operation: UUID) -> CandidateIntakeReceiptRow | None:
        """只让第一次read返回None，分类故障后完整回读SQL。

        Args:
            session: 真事务。
            tenant: requested tenant。
            operation: requested op。
        Returns:
            首次None或真实完整row。
        Raises:
            SQLAlchemyError: 保留实际SQL错误。
        """
        if self.first:
            self.first = False
            return None
        return self.original(session, tenant, operation)


@pytest.mark.parametrize(
    "key",
    [
        "pk_research_candidates",
        "uq_research_candidates_tenant_company_id",
        "uq_research_candidates_operation",
        "pk_candidate_intake_receipts",
        "uq_candidate_intake_receipts_tenant_candidate",
        "unexpected_unique_key",
    ],
)
def test_all_named_23505_classifications_use_real_psycopg_error(
    repository_database: _RepositoryDatabase,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
) -> None:
    """PG trigger发出精确named23505；不声称所有键自然竞争时首先命中。

    Args:
        repository_database: 真PG fixture。
        monkeypatch: 只复现首次miss，恢复为真SQL。
        key: 注入的exact constraint name。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    request = _request(_context(db), _raw(_Fins()))
    repository = PostgresCandidateIntakeRepository(db.sessions)
    first = repository.record_intake(db.scope, request)
    before = _snapshot(db)
    with db.admin.begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION dayu_platform.s32_named_fault() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN RAISE unique_violation USING CONSTRAINT = '{key}', MESSAGE = 'injected owned test fault'; END $$"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER s32_named_fault BEFORE INSERT ON dayu_platform.research_candidates "
            "FOR EACH ROW EXECUTE FUNCTION dayu_platform.s32_named_fault()"
        )
    miss = _FirstMiss(intake_module._receipt_row)
    monkeypatch.setattr(intake_module, "_receipt_row", miss.read)
    try:
        if key == "unexpected_unique_key":
            with pytest.raises(EvidenceConflictError):
                repository.record_intake(db.scope, request)
        else:
            assert repository.record_intake(db.scope, request) == first
        assert _snapshot(db) == before
    finally:
        with db.admin.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER s32_named_fault ON dayu_platform.research_candidates")
            connection.exec_driver_sql("DROP FUNCTION dayu_platform.s32_named_fault() RESTRICT")


def test_receipt_insert_failure_rolls_back_candidate(repository_database: _RepositoryDatabase) -> None:
    """candidate已flush后receipt真SQL故障仍整对零行。

    Args:
        repository_database: 真PG fixture。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    before = _snapshot(db)
    with db.admin.begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION dayu_platform.s32_receipt_fault() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE check_violation USING MESSAGE = 'secret path fault must be hidden'; END $$"
        )
        connection.exec_driver_sql(
            f"CREATE TRIGGER s32_receipt_fault BEFORE INSERT ON {_TABLE} "
            "FOR EACH ROW EXECUTE FUNCTION dayu_platform.s32_receipt_fault()"
        )
    try:
        with pytest.raises(EvidenceRepositoryError) as caught:
            PostgresCandidateIntakeRepository(db.sessions).record_intake(
                db.scope, _request(_context(db), _raw(_Fins()))
            )
        assert str(caught.value) == "evidence_storage_failure"
        assert caught.value.__suppress_context__ and _snapshot(db) == before
    finally:
        with db.admin.begin() as connection:
            connection.exec_driver_sql(f"DROP TRIGGER s32_receipt_fault ON {_TABLE}")
            connection.exec_driver_sql("DROP FUNCTION dayu_platform.s32_receipt_fault() RESTRICT")


@pytest.mark.parametrize("change", ["payload", "origin", "operation_fingerprint", "deep_json"])
def test_corrupt_candidate_history_is_storage_failure_before_request_conflict(
    repository_database: _RepositoryDatabase,
    change: str,
) -> None:
    """不修改append-only receipt，admin损坏候选可观测自闭合失败。

    Args:
        repository_database: 真PG fixture。
        change: 损坏的候选字段。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    request = _request(_context(db), _raw(_Fins()))
    repository = PostgresCandidateIntakeRepository(db.sessions)
    repository.record_intake(db.scope, request)
    assignment = {
        "payload": "canonical_payload_json='{}'::jsonb",
        "origin": "origin='human'",
        "operation_fingerprint": "operation_fingerprint=repeat('f',64)",
        "deep_json": "canonical_payload_json=('{\"a\":'||repeat('[',1500)||'0'||repeat(']',1500)||'}')::jsonb",
    }[change]
    with db.admin.begin() as connection:
        connection.execute(
            text(f"UPDATE dayu_platform.research_candidates SET {assignment} WHERE id=:id"),
            {"id": request.context.candidate_id},
        )
    before = _snapshot(db)
    with pytest.raises(EvidenceRepositoryError, match="^evidence_storage_failure$"):
        repository.find_intake_receipt(db.scope, request.context.operation_id, "f" * 64)
    assert _snapshot(db) == before


def test_cross_tenant_public_evidence_and_global_pk_collision(repository_database: _RepositoryDatabase) -> None:
    """同public locator两tenant各自成功；同candidate全球PK不泄漏复用。

    Args:
        repository_database: 真PG fixture。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    tenant_b = uuid4()
    scope_b = Principal(TenantId(str(tenant_b)), "test-b").to_scope()
    with db.admin.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO dayu_platform.organizations(id,slug,display_name,status) VALUES (:id,:slug,'Tenant B','active')"
            ),
            {"id": tenant_b, "slug": "tenant-" + tenant_b.hex},
        )
    request = _request(_context(db), _raw(_Fins()))
    repository = PostgresCandidateIntakeRepository(db.sessions)
    first = repository.record_intake(db.scope, request)
    assert repository.find_intake_receipt(scope_b, request.context.operation_id, first.request_fingerprint) is None
    snapshot = _snapshot(db)
    with pytest.raises(EvidenceConflictError):
        repository.record_intake(scope_b, request)
    assert _snapshot(db) == snapshot
    other = replace(request, context=replace(request.context, candidate_id=uuid4()))
    second = repository.record_intake(scope_b, other)
    assert second.tenant_id == tenant_b and first.tenant_id != second.tenant_id
    assert _counts(db) == (2, 2, 0, 0, 0, 0, 0)
    with db.sessions() as session, session.begin():
        assert session.execute(text(f"SELECT count(*) FROM {_TABLE}")).scalar_one() == 0
        session.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"), {"tenant": str(tenant_b)})
        assert session.execute(text(f"SELECT count(*) FROM {_TABLE}")).scalar_one() == 1
        with pytest.raises(DBAPIError), session.begin_nested():
            session.execute(
                text(
                    f"INSERT INTO {_TABLE} SELECT :wrong_tenant,gen_random_uuid(),company_id,"
                    "security_id,security_ticker,candidate_id,origin,extractor_version,schema_version,raw_sha256,"
                    "raw_bytes,request_fingerprint,payload_sha256,outcome,rejection_code,locator_sha256,"
                    f"citation_sha256,fins_checked_at,created_at FROM {_TABLE}"
                ),
                {"wrong_tenant": first.tenant_id},
            )


def test_0008_catalog_empty_roundtrip(
    repository_database: _RepositoryDatabase, platform_cluster: PlatformCluster
) -> None:
    """34/31/3、精确19列及最小权限；空回退保留0007六表后重升一致。

    Args:
        repository_database: 真PG fixture。
        platform_cluster: owner cluster。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    migration = importlib.import_module("dayu.investment.storage.migrations.versions.0008_candidate_intake")
    with db.admin.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='dayu_platform' AND c.relkind='r'"
            )
        ).all()
        assert len(rows) == 34 and sum(bool(r[1]) and bool(r[2]) for r in rows) == 31
        columns = connection.execute(
            text(
                "SELECT column_name,data_type,is_nullable,column_default "
                "FROM information_schema.columns WHERE table_schema='dayu_platform' AND table_name='candidate_intake_receipts' "
                "ORDER BY ordinal_position"
            )
        ).all()
        assert [r[0] for r in columns] == [
            "tenant_id",
            "operation_id",
            "company_id",
            "security_id",
            "security_ticker",
            "candidate_id",
            "origin",
            "extractor_version",
            "schema_version",
            "raw_sha256",
            "raw_bytes",
            "request_fingerprint",
            "payload_sha256",
            "outcome",
            "rejection_code",
            "locator_sha256",
            "citation_sha256",
            "fins_checked_at",
            "created_at",
        ]
        assert [r[0] for r in columns if r[2] == "YES"] == [
            "rejection_code",
            "locator_sha256",
            "citation_sha256",
            "fins_checked_at",
        ]
        assert columns[-1][1:] == ("timestamp with time zone", "NO", "statement_timestamp()")
        digest = migration._catalog_digest(connection)
        assert digest == "06a30f5fbef25ae3c438cbb897eeacb5a75c07723daa49e6358528ef939327bc"
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE conrelid='dayu_platform.candidate_intake_receipts'::regclass"
                )
            ).scalar_one()
            == 16
        )
        for role, allowed in ((PLATFORM_APP_ROLE, {"SELECT", "INSERT"}), (PLATFORM_AUDIT_ROLE, {"SELECT"})):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
                result = connection.execute(
                    text("SELECT has_table_privilege(:role,:table,:privilege)"),
                    {"role": role, "table": _TABLE, "privilege": privilege},
                ).scalar_one()
                assert result is (privilege in allowed)
    _revision(db, platform_cluster, "0007_strict_evidence", upgrade=False)
    assert _head(db) == "0007_strict_evidence"
    with db.admin.connect() as connection:
        assert (
            connection.execute(text("SELECT to_regclass('dayu_platform.candidate_intake_receipts')")).scalar_one()
            is None
        )
        assert all(
            connection.execute(text("SELECT to_regclass(:name)"), {"name": "dayu_platform." + name}).scalar_one()
            is not None
            for name in _OWN_TABLES[1:]
        )
    _revision(db, platform_cluster, "head", upgrade=True)
    assert _head(db) == "0008_candidate_intake"
    with db.admin.connect() as connection:
        assert migration._catalog_digest(connection) == digest


@pytest.mark.parametrize(
    "dependency", ["view", "foreign_key", "role_acl", "column_acl", "nowait_lock", "business_rows"]
)
def test_0008_downgrade_refuses_and_rolls_back_exactly(
    repository_database: _RepositoryDatabase,
    platform_cluster: PlatformCluster,
    dependency: str,
) -> None:
    """外部ACL/view/FK、两连接锁和业务行均拒绝，revision/完整行不变。

    Args:
        repository_database: 真PG fixture。
        platform_cluster: owner cluster。
        dependency: 精确回退拒绝原因。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    if dependency == "business_rows":
        PostgresCandidateIntakeRepository(db.sessions).record_intake(db.scope, _request(_context(db), _raw(_Fins())))
    with db.admin.begin() as connection:
        if dependency == "view":
            connection.exec_driver_sql(f"CREATE VIEW public.s32_external_view AS SELECT * FROM {_TABLE}")
        elif dependency == "foreign_key":
            connection.exec_driver_sql(
                f"CREATE TABLE public.s32_external_fk(tenant UUID,operation UUID, "
                f"FOREIGN KEY(tenant,operation) REFERENCES {_TABLE}(tenant_id,operation_id))"
            )
        elif dependency == "role_acl":
            connection.exec_driver_sql(f"GRANT SELECT ON {_TABLE} TO PUBLIC")
        elif dependency == "column_acl":
            connection.exec_driver_sql(f"GRANT SELECT(raw_sha256) ON {_TABLE} TO PUBLIC")
    before = _snapshot(db)
    lock_connection = db.admin.connect() if dependency == "nowait_lock" else None
    try:
        if lock_connection is not None:
            lock_connection.execute(text(f"LOCK TABLE {_TABLE} IN ACCESS SHARE MODE"))
        with pytest.raises((PlatformMigrationAdmissionError, DBAPIError)):
            _revision(db, platform_cluster, "0007_strict_evidence", upgrade=False)
        assert _head(db) == "0008_candidate_intake" and _snapshot(db) == before
        with db.admin.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_trigger WHERE tgrelid='dayu_platform.candidate_intake_receipts'::regclass "
                        "AND tgname='candidate_intake_receipts_append_only_trigger'"
                    )
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_policy WHERE polrelid='dayu_platform.candidate_intake_receipts'::regclass"
                    )
                ).scalar_one()
                == 1
            )
    finally:
        if lock_connection is not None:
            lock_connection.rollback()
            lock_connection.close()
        with db.admin.begin() as connection:
            if dependency == "view":
                connection.exec_driver_sql("DROP VIEW public.s32_external_view")
            elif dependency == "foreign_key":
                connection.exec_driver_sql("DROP TABLE public.s32_external_fk")
            elif dependency == "role_acl":
                connection.exec_driver_sql(f"REVOKE SELECT ON {_TABLE} FROM PUBLIC")
            elif dependency == "column_acl":
                connection.exec_driver_sql(f"REVOKE SELECT(raw_sha256) ON {_TABLE} FROM PUBLIC")


@pytest.mark.parametrize(
    "tenant_text", ["not-a-uuid", "00000000-0000-0000-0000-000000000000", "ABCDEFAB-0000-4000-8000-000000000001"]
)
def test_repository_invalid_tenant_has_zero_writes(repository_database: _RepositoryDatabase, tenant_text: str) -> None:
    """opaque TenantId仍需仓储canonical非nilUUID校验，失败尚未SQL。

    Args:
        repository_database: 真PG fixture。
        tenant_text: 非canonical租户文本。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    scope = Principal(TenantId(tenant_text), "test-invalid").to_scope()
    repository = PostgresCandidateIntakeRepository(db.sessions)
    before = _snapshot(db)
    with pytest.raises(EvidenceInputError):
        repository.record_intake(scope, _request(_context(db), _raw(_Fins())))
    assert _snapshot(db) == before


@pytest.mark.parametrize("invalid", ["nil_operation", "fingerprint"])
def test_repository_invalid_receipt_lookup_has_zero_writes(
    repository_database: _RepositoryDatabase, invalid: str
) -> None:
    """直接read契约对nil operation/非hex指纹拒绝。

    Args:
        repository_database: 真PG fixture。
        invalid: 非法字段。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    repository = PostgresCandidateIntakeRepository(db.sessions)
    before = _snapshot(db)
    with pytest.raises(EvidenceInputError):
        repository.find_intake_receipt(
            db.scope,
            UUID(int=0) if invalid == "nil_operation" else uuid4(),
            "z" * 64 if invalid == "fingerprint" else "a" * 64,
        )
    assert _snapshot(db) == before


@pytest.mark.parametrize("unsafe", ["visible_parameters", "repeatable_read"])
def test_repository_enforces_hidden_parameters_and_read_committed(
    repository_database: _RepositoryDatabase, unsafe: str
) -> None:
    """实际不安全engine/隔离配置被固定storage错误拒绝并保持零行。

    Args:
        repository_database: 真PG fixture。
        unsafe: 真实engine配置故障。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    before = _snapshot(db)
    if unsafe == "visible_parameters":
        engine = create_engine(db.admin.url, echo=False, hide_parameters=False)
    else:
        with db.sessions() as session:
            bind = session.get_bind()
            assert isinstance(bind, Engine)
        engine = bind.execution_options(isolation_level="REPEATABLE READ")
    try:
        repository = PostgresCandidateIntakeRepository(sessionmaker(bind=engine, class_=Session))
        with pytest.raises(EvidenceRepositoryError, match="^evidence_storage_failure$"):
            repository.record_intake(db.scope, _request(_context(db), _raw(_Fins())))
        assert _snapshot(db) == before
    finally:
        engine.dispose()


def test_two_connections_cross_tenant_global_candidate_pk_cannot_be_reused(
    repository_database: _RepositoryDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两租户同时插相同全球candidate ID，仅胜方有自己的receipt。

    Args:
        repository_database: 真PG fixture。
        monkeypatch: 首次真实SELECT同步。
    Returns:
        无。
    Raises:
        无。
    """
    db = repository_database
    tenant_b = uuid4()
    scope_b = Principal(TenantId(str(tenant_b)), "race-b").to_scope()
    with db.admin.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO dayu_platform.organizations(id,slug,display_name,status) "
                "VALUES (:id,:slug,'Tenant B','active')"
            ),
            {"id": tenant_b, "slug": "tenant-" + tenant_b.hex},
        )
    request = _request(_context(db), _raw(_Fins()))
    repository = PostgresCandidateIntakeRepository(db.sessions)
    gate = _ReadBarrier(intake_module._receipt_row)
    monkeypatch.setattr(intake_module, "_receipt_row", gate.read)
    results: list[CandidateIntakeReceipt | str] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(repository.record_intake, scope, request) for scope in (db.scope, scope_b)]
        for future in futures:
            try:
                results.append(future.result(timeout=15))
            except EvidenceConflictError:
                results.append("conflict")
    assert sum(isinstance(value, CandidateIntakeReceipt) for value in results) == 1
    assert results.count("conflict") == 1 and _counts(db) == (1, 1, 0, 0, 0, 0, 0)
    monkeypatch.setattr(intake_module, "_receipt_row", gate.original)
    # 全部后续读取仍是实际SQL；失败tenant没有operation receipt可盲复用。
    for scope in (db.scope, scope_b):
        fp = intake_request_fingerprint(scope, request.context, "ABC", request.raw_sha256, request.raw_bytes)
        receipt = repository.find_intake_receipt(scope, request.context.operation_id, fp)
        assert (receipt is not None) is any(
            isinstance(value, CandidateIntakeReceipt) and value.tenant_id == UUID(scope.tenant_id.value)
            for value in results
        )


_S32SqlValue: TypeAlias = UUID | str | int | datetime | None
_S32_RECEIPT_COLUMNS = (
    "tenant_id",
    "operation_id",
    "company_id",
    "security_id",
    "security_ticker",
    "candidate_id",
    "origin",
    "extractor_version",
    "schema_version",
    "raw_sha256",
    "raw_bytes",
    "request_fingerprint",
    "payload_sha256",
    "outcome",
    "rejection_code",
    "locator_sha256",
    "citation_sha256",
    "fins_checked_at",
    "created_at",
)
_S32_RECEIPT_INSERT = (
    "INSERT INTO dayu_platform.candidate_intake_receipts ("
    + ",".join(_S32_RECEIPT_COLUMNS)
    + ") VALUES ("
    + ",".join(":" + name for name in _S32_RECEIPT_COLUMNS)
    + ")"
)
_S32_NULLABLE_COLUMNS = frozenset({"rejection_code", "locator_sha256", "citation_sha256", "fins_checked_at"})
_S32_REQUIRED_COLUMNS = tuple(name for name in _S32_RECEIPT_COLUMNS if name not in _S32_NULLABLE_COLUMNS)
_S32_HASH_COLUMNS = ("raw_sha256", "request_fingerprint", "payload_sha256", "locator_sha256", "citation_sha256")


def _s32_receipt_sql_values(
    db: _RepositoryDatabase,
    *,
    outcome: CandidateStatus = CandidateStatus.PROPOSED,
    isolated_parents: bool = False,
) -> dict[str, _S32SqlValue]:
    """创建有真实 payload 的新 staging 行，返回尚未 INSERT receipt 的完整十九键。

    Args:
        db: 独占随机库及合成身份。
        outcome: proposed 或 rejected 正例 arm。
        isolated_parents: 创建仅供本测试使用的新组织、公司和证券。
    Returns:
        新 candidate/op 对应的全列参数；不会复用已有 receipt 的唯一键。
    Raises:
        AssertionError: seed 投影、克隆行或参数集合不闭合。
        DBAPIError: 创建明确父数据或 staging 行失败。
    """
    assert outcome in (CandidateStatus.PROPOSED, CandidateStatus.REJECTED)
    request = _request(_context(db), _raw(_Fins()))
    if outcome is CandidateStatus.REJECTED:
        request = replace(request, payload=None, witness=None, rejection_code=CandidateIntakeRejectionCode.JSON_INVALID)
    seed = PostgresCandidateIntakeRepository(db.sessions).record_intake(db.scope, request)
    tenant, company, security = seed.tenant_id, db.company, db.security_a
    if isolated_parents:
        tenant, company, security = uuid4(), uuid4(), uuid4()
        with db.admin.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO dayu_platform.organizations(id,slug,display_name,status) "
                    "VALUES (:id,:slug,'SQL isolated tenant','active')"
                ),
                {"id": tenant, "slug": "sql-" + tenant.hex},
            )
            connection.execute(
                text("INSERT INTO dayu_platform.companies(id,legal_name) VALUES (:id,'SQL isolated company')"),
                {"id": company},
            )
            connection.execute(
                text(
                    "INSERT INTO dayu_platform.securities "
                    "(id,company_id,ticker,exchange_mic,security_type,currency) "
                    "VALUES (:id,:company,'ABC','XPAR','equity','USD')"
                ),
                {"id": security, "company": company},
            )
    context = replace(
        request.context, candidate_id=uuid4(), operation_id=uuid4(), company_id=company, security_id=security
    )
    scope = Principal(TenantId(str(tenant)), "sql-contract").to_scope()
    fingerprint = intake_request_fingerprint(scope, context, "ABC", request.raw_sha256, request.raw_bytes)
    with db.admin.begin() as connection:
        inserted = connection.execute(
            text(
                "INSERT INTO dayu_platform.research_candidates "
                "(id,tenant_id,company_id,origin,canonical_payload_json,sha256,operation_id,"
                "operation_fingerprint,state,rejection_code,version) "
                "SELECT :id,:tenant,:company,origin,canonical_payload_json,sha256,:operation,"
                ":fingerprint,state,rejection_code,1 FROM dayu_platform.research_candidates "
                "WHERE id=:source RETURNING id,sha256"
            ),
            {
                "id": context.candidate_id,
                "tenant": tenant,
                "company": company,
                "operation": context.operation_id,
                "fingerprint": fingerprint,
                "source": seed.context.candidate_id,
            },
        ).one()
        assert tuple(inserted) == (context.candidate_id, seed.payload_sha256)
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM dayu_platform.candidate_intake_receipts "
                    "WHERE tenant_id=:tenant AND candidate_id=:candidate"
                ),
                {"tenant": tenant, "candidate": context.candidate_id},
            ).scalar_one()
            == 0
        )
    witness = seed.witness
    values: dict[str, _S32SqlValue] = {
        "tenant_id": tenant,
        "operation_id": context.operation_id,
        "company_id": company,
        "security_id": security,
        "security_ticker": "ABC",
        "candidate_id": context.candidate_id,
        "origin": context.origin.value,
        "extractor_version": context.extractor_version,
        "schema_version": "candidate_intake.v1",
        "raw_sha256": request.raw_sha256,
        "raw_bytes": request.raw_bytes,
        "request_fingerprint": fingerprint,
        "payload_sha256": seed.payload_sha256,
        "outcome": outcome.value,
        "rejection_code": seed.rejection_code.value if seed.rejection_code is not None else None,
        "locator_sha256": witness.locator_sha256 if witness is not None else None,
        "citation_sha256": witness.citation_sha256 if witness is not None else None,
        "fins_checked_at": witness.checked_at if witness is not None else None,
        "created_at": _NOW,
    }
    assert tuple(values) == _S32_RECEIPT_COLUMNS
    return values


def _s32_insert_receipt_sql(db: _RepositoryDatabase, values: dict[str, _S32SqlValue]) -> None:
    """使用 app role、正确租户和显式全列参数写 raw SQL 正例。

    Args:
        db: 随机库 admin 连接工厂；只用于切换既有 app role。
        values: 已有新 staging 行、无 receipt 的完整参数。
    Returns:
        无。
    Raises:
        AssertionError: 租户不是 UUID 或 readback 不精确。
        DBAPIError: 真 SQL 失败。
    """
    tenant = values["tenant_id"]
    assert isinstance(tenant, UUID)
    with db.admin.begin() as connection:
        connection.exec_driver_sql(f"SET LOCAL ROLE {PLATFORM_APP_ROLE}")
        connection.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"), {"tenant": str(tenant)})
        connection.execute(text(_S32_RECEIPT_INSERT), values)
        row = connection.execute(
            text(
                "SELECT "
                + ",".join(_S32_RECEIPT_COLUMNS)
                + " FROM "
                + _TABLE
                + " WHERE tenant_id=:tenant_id AND operation_id=:operation_id"
            ),
            values,
        ).one()
        assert tuple(row) == tuple(values[name] for name in _S32_RECEIPT_COLUMNS)


def _s32_reject_sql(
    db: _RepositoryDatabase,
    statement: str,
    values: dict[str, _S32SqlValue],
    *,
    sqlstate: str,
    constraint: str | None,
    role: str | None = None,
    tenant: UUID | None = None,
    column: str | None = None,
) -> None:
    """核真实 psycopg 错误、SAVEPOINT 恢复和七表完整快照不变。

    Args:
        db: 独占随机库。
        statement: 本片段固定 SQL；数据全部参数化。
        values: 仅合成 UUID、文本、数字、UTC 时间或 NULL。
        sqlstate: 必需的精确错误码。
        constraint: 精确命名约束；ACL、NOT NULL 与 guard 预期为 NULL。
        role: 既有 app/audit role，或保持 admin。
        tenant: 可选的 SET LOCAL 租户；NULL 保持未设置。
        column: NOT NULL 错误的精确列；其它错误为 NULL。
    Returns:
        无。
    Raises:
        AssertionError: SQL 未拒绝、错误来源错误或持久行变化。
        DBAPIError: 错误之外的数据库操作失败。
    """
    assert role in (None, PLATFORM_APP_ROLE, PLATFORM_AUDIT_ROLE)
    before = _snapshot(db)
    with db.admin.begin() as connection:
        if role is not None:
            connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
        if tenant is not None:
            connection.execute(text("SELECT set_config('app.tenant_id',:tenant,true)"), {"tenant": str(tenant)})
        savepoint = connection.begin_nested()
        try:
            with pytest.raises(DBAPIError) as caught:
                connection.execute(text(statement), values)
            error = caught.value.orig
            assert isinstance(error, PsycopgError)
            assert error.sqlstate == sqlstate
            assert error.diag.constraint_name == constraint
            assert error.diag.column_name == column
        finally:
            savepoint.rollback()
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
    assert _snapshot(db) == before


def test_0008_sql_exact_column_types_and_four_restrict_fk_catalog(repository_database: _RepositoryDatabase) -> None:
    """独立列举十九列全类型/default/nullability及四 FK 的列序、目标和 RESTRICT。

    Args:
        repository_database: 真实 head 随机库。
    Returns:
        无。
    Raises:
        AssertionError: 未知列、类型、默认值或 FK 漂移。
        DBAPIError: catalog 查询失败。
    """
    with repository_database.admin.connect() as connection:
        columns = connection.execute(
            text(
                "SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid) "
                "FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                "WHERE a.attrelid='dayu_platform.candidate_intake_receipts'::regclass "
                "AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum"
            )
        ).all()
        assert [tuple(row) for row in columns] == [
            ("tenant_id", "uuid", True, None),
            ("operation_id", "uuid", True, None),
            ("company_id", "uuid", True, None),
            ("security_id", "uuid", True, None),
            ("security_ticker", "text", True, None),
            ("candidate_id", "uuid", True, None),
            ("origin", "text", True, None),
            ("extractor_version", "text", True, None),
            ("schema_version", "text", True, None),
            ("raw_sha256", "character(64)", True, None),
            ("raw_bytes", "bigint", True, None),
            ("request_fingerprint", "character(64)", True, None),
            ("payload_sha256", "character(64)", True, None),
            ("outcome", "text", True, None),
            ("rejection_code", "text", False, None),
            ("locator_sha256", "character(64)", False, None),
            ("citation_sha256", "character(64)", False, None),
            ("fins_checked_at", "timestamp with time zone", False, None),
            ("created_at", "timestamp with time zone", True, "statement_timestamp()"),
        ]
        foreign_keys = connection.execute(
            text(
                "SELECT co.conname,"
                "array_to_string(ARRAY(SELECT a.attname FROM unnest(co.conkey) WITH ORDINALITY k(attnum,ord) "
                "JOIN pg_attribute a ON a.attrelid=co.conrelid AND a.attnum=k.attnum ORDER BY k.ord),','),"
                "n.nspname||'.'||parent.relname,"
                "array_to_string(ARRAY(SELECT a.attname FROM unnest(co.confkey) WITH ORDINALITY k(attnum,ord) "
                "JOIN pg_attribute a ON a.attrelid=co.confrelid AND a.attnum=k.attnum ORDER BY k.ord),','),"
                "co.confdeltype::text,co.confupdtype::text,co.convalidated,co.condeferrable,co.condeferred "
                "FROM pg_constraint co JOIN pg_class parent ON parent.oid=co.confrelid "
                "JOIN pg_namespace n ON n.oid=parent.relnamespace "
                "WHERE co.conrelid='dayu_platform.candidate_intake_receipts'::regclass AND co.contype='f' "
                "ORDER BY co.conname"
            )
        ).all()
        assert [tuple(row) for row in foreign_keys] == [
            (
                "fk_candidate_intake_receipts_candidate",
                "tenant_id,company_id,candidate_id",
                "dayu_platform.research_candidates",
                "tenant_id,company_id,id",
                "r",
                "a",
                True,
                False,
                False,
            ),
            (
                "fk_candidate_intake_receipts_company_id_companies",
                "company_id",
                "dayu_platform.companies",
                "id",
                "r",
                "a",
                True,
                False,
                False,
            ),
            (
                "fk_candidate_intake_receipts_security",
                "company_id,security_id,security_ticker",
                "dayu_platform.securities",
                "company_id,id,ticker",
                "r",
                "a",
                True,
                False,
                False,
            ),
            (
                "fk_candidate_intake_receipts_tenant_id_organizations",
                "tenant_id",
                "dayu_platform.organizations",
                "id",
                "r",
                "a",
                True,
                False,
                False,
            ),
        ]


@pytest.mark.parametrize("outcome", [CandidateStatus.PROPOSED, CandidateStatus.REJECTED])
def test_0008_raw_sql_both_valid_outcome_arms(
    repository_database: _RepositoryDatabase,
    outcome: CandidateStatus,
) -> None:
    """两个合法 arm 真 INSERT/readback；新 candidate/op 不先命中唯一键。

    Args:
        repository_database: 独占随机库。
        outcome: 完整 proposed/rejected arm。
    Returns:
        无。
    Raises:
        AssertionError: 全列回读或新增行数不符。
        DBAPIError: 真 SQL 失败。
    """
    db = repository_database
    values = _s32_receipt_sql_values(db, outcome=outcome)
    assert _counts(db) == (1, 2, 0, 0, 0, 0, 0)
    _s32_insert_receipt_sql(db, values)
    assert _counts(db) == (2, 2, 0, 0, 0, 0, 0)


@pytest.mark.parametrize("column", _S32_REQUIRED_COLUMNS)
def test_0008_raw_sql_required_columns_reject_null(
    repository_database: _RepositoryDatabase,
    column: str,
) -> None:
    """十五个 NOT NULL 列逐一由真 PG 拒绝，不依赖 DTO 校验。

    Args:
        repository_database: 独占随机库。
        column: 十九列中的必需列。
    Returns:
        无。
    Raises:
        AssertionError: SQLSTATE/列身份或快照不符。
        DBAPIError: seed 操作失败。
    """
    values = _s32_receipt_sql_values(repository_database)
    values[column] = None
    _s32_reject_sql(repository_database, _S32_RECEIPT_INSERT, values, sqlstate="23502", constraint=None, column=column)


@pytest.mark.parametrize("column", _S32_HASH_COLUMNS)
@pytest.mark.parametrize("invalid_hash", ["A" * 64, "g" * 64, "a" * 63])
def test_0008_raw_sql_hash_checks_are_named_and_exact(
    repository_database: _RepositoryDatabase,
    column: str,
    invalid_hash: str,
) -> None:
    """五个摘要分别拒绝大写、非 hex 与短值；精确核命名 CHECK。

    Args:
        repository_database: 独占随机库。
        column: 五个摘要列。
        invalid_hash: 合成坏摘要，不含任何凭据。
    Returns:
        无。
    Raises:
        AssertionError: SQLSTATE、命名 CHECK 或快照不符。
        DBAPIError: seed 操作失败。
    """
    values = _s32_receipt_sql_values(repository_database)
    values[column] = invalid_hash
    _s32_reject_sql(
        repository_database,
        _S32_RECEIPT_INSERT,
        values,
        sqlstate="23514",
        constraint="ck_candidate_intake_receipts_" + column,
    )


@pytest.mark.parametrize(
    "column,value,check",
    [
        ("origin", "tool", "origin"),
        ("schema_version", "candidate_intake.v2", "schema_version"),
        ("extractor_version", "", "extractor_nonblank"),
        ("extractor_version", " pg.v1 ", "extractor_nonblank"),
        ("raw_bytes", -1, "raw_bytes"),
    ],
)
def test_0008_raw_sql_scalar_checks_reject_invalid_values(
    repository_database: _RepositoryDatabase,
    column: str,
    value: _S32SqlValue,
    check: str,
) -> None:
    """origin/schema/extractor/count 各自命中固定 CHECK，不碰已有唯一键。

    Args:
        repository_database: 独占随机库。
        column: 明确的被测列。
        value: 合成非法值。
        check: 该列固定 CHECK 后缀。
    Returns:
        无。
    Raises:
        AssertionError: CHECK 身份或七表快照不符。
        DBAPIError: seed 操作失败。
    """
    values = _s32_receipt_sql_values(repository_database)
    values[column] = value
    _s32_reject_sql(
        repository_database,
        _S32_RECEIPT_INSERT,
        values,
        sqlstate="23514",
        constraint="ck_candidate_intake_receipts_" + check,
    )


@pytest.mark.parametrize(
    "outcome,column,value",
    [
        (CandidateStatus.PROPOSED, "locator_sha256", None),
        (CandidateStatus.PROPOSED, "citation_sha256", None),
        (CandidateStatus.PROPOSED, "fins_checked_at", None),
        (CandidateStatus.PROPOSED, "rejection_code", "candidate_json_invalid"),
        (CandidateStatus.PROPOSED, "outcome", "accepted"),
        (CandidateStatus.REJECTED, "rejection_code", None),
        (CandidateStatus.REJECTED, "rejection_code", "arbitrary_message"),
        (CandidateStatus.REJECTED, "locator_sha256", "a" * 64),
        (CandidateStatus.REJECTED, "citation_sha256", "a" * 64),
        (CandidateStatus.REJECTED, "fins_checked_at", _NOW),
    ],
)
def test_0008_raw_sql_outcome_null_closure_is_true(
    repository_database: _RepositoryDatabase,
    outcome: CandidateStatus,
    column: str,
    value: _S32SqlValue,
) -> None:
    """逐个 nullable arm 坏值核外层 IS TRUE，NULL 不能绕过 outcome CHECK。

    Args:
        repository_database: 独占随机库。
        outcome: 原完整正例 arm。
        column: 改为非法值的 arm 列。
        value: NULL、无关 witness 或未知拒绝码。
    Returns:
        无。
    Raises:
        AssertionError: 命名 outcome CHECK 或七表快照不符。
        DBAPIError: seed 操作失败。
    """
    values = _s32_receipt_sql_values(repository_database, outcome=outcome)
    values[column] = value
    _s32_reject_sql(
        repository_database,
        _S32_RECEIPT_INSERT,
        values,
        sqlstate="23514",
        constraint="ck_candidate_intake_receipts_outcome_shape",
    )


@pytest.mark.parametrize(
    "kind", ["missing_candidate", "foreign_candidate", "missing_security", "foreign_security", "ticker"]
)
def test_0008_raw_sql_composite_fk_rejects_wrong_tuple(
    repository_database: _RepositoryDatabase,
    kind: str,
) -> None:
    """明确创建另一组父数据；只声称实际命中的 candidate/security 复合 FK。

    Args:
        repository_database: 独占随机库。
        kind: 缺失 ID、真实外部 tuple 或 ticker 串联。
    Returns:
        无。
    Raises:
        AssertionError: 命名 FK 或完整七表快照不符。
        DBAPIError: 父数据/staging 创建失败。
    """
    db = repository_database
    values = _s32_receipt_sql_values(db)
    if kind in ("foreign_candidate", "foreign_security"):
        other = _s32_receipt_sql_values(db, isolated_parents=True)
        values["candidate_id" if kind == "foreign_candidate" else "security_id"] = other[
            "candidate_id" if kind == "foreign_candidate" else "security_id"
        ]
    elif kind == "ticker":
        values["security_ticker"] = "XYZ"
    else:
        values["candidate_id" if kind == "missing_candidate" else "security_id"] = uuid4()
    constraint = "fk_candidate_intake_receipts_" + ("candidate" if "candidate" in kind else "security")
    _s32_reject_sql(db, _S32_RECEIPT_INSERT, values, sqlstate="23503", constraint=constraint)


@pytest.mark.parametrize(
    "table,column,constraint",
    [
        ("research_candidates", "candidate_id", "fk_candidate_intake_receipts_candidate"),
        ("securities", "security_id", "fk_candidate_intake_receipts_security"),
        ("companies", "company_id", "fk_securities_company_id_companies"),
        ("organizations", "tenant_id", "fk_research_candidates_tenant_id_organizations"),
    ],
)
def test_0008_raw_sql_parent_delete_restrict_preserves_rows(
    repository_database: _RepositoryDatabase,
    table: str,
    column: str,
    constraint: str,
) -> None:
    """四类真实父行 DELETE 被 RESTRICT 拒绝，记录实际先命中的旧/新 FK。

    Args:
        repository_database: 独占随机库。
        table: 固定的四个父表之一。
        column: 完整 receipt 中的父 ID 列。
        constraint: 当前 PG 首个约束；org/company 不冒充新冗余 FK 命中。
    Returns:
        无。
    Raises:
        AssertionError: 实际约束或七表/父行内容变化。
        DBAPIError: 父数据创建、INSERT 或 readback 失败。
    """
    db = repository_database
    values = _s32_receipt_sql_values(db, isolated_parents=True)
    _s32_insert_receipt_sql(db, values)
    parameters: dict[str, _S32SqlValue] = {"id": values[column]}
    with db.admin.connect() as connection:
        before_parent = connection.execute(
            text(f"SELECT row_to_json(p)::text FROM dayu_platform.{table} p WHERE id=:id"),
            parameters,
        ).scalar_one()
    _s32_reject_sql(
        db, f"DELETE FROM dayu_platform.{table} WHERE id=:id", parameters, sqlstate="23503", constraint=constraint
    )
    with db.admin.connect() as connection:
        assert (
            connection.execute(
                text(f"SELECT row_to_json(p)::text FROM dayu_platform.{table} p WHERE id=:id"),
                parameters,
            ).scalar_one()
            == before_parent
        )


@pytest.mark.parametrize("mutation", ["UPDATE", "DELETE", "TRUNCATE"])
@pytest.mark.parametrize("role", [PLATFORM_APP_ROLE, PLATFORM_AUDIT_ROLE])
def test_0008_raw_sql_app_and_audit_mutation_acl(
    repository_database: _RepositoryDatabase,
    mutation: str,
    role: str,
) -> None:
    """app/audit 真 UPDATE、DELETE、TRUNCATE 全被权限拒绝，表行保持。

    Args:
        repository_database: 独占随机库。
        mutation: 三个固定 mutation。
        role: 既有 app 或 audit role。
    Returns:
        无。
    Raises:
        AssertionError: 权限码或七表快照不符。
        DBAPIError: 正例准备失败。
    """
    db = repository_database
    values = _s32_receipt_sql_values(db)
    _s32_insert_receipt_sql(db, values)
    tenant = values["tenant_id"]
    assert isinstance(tenant, UUID)
    statement = {
        "UPDATE": f"UPDATE {_TABLE} SET created_at=created_at WHERE tenant_id=:tenant_id AND operation_id=:operation_id",
        "DELETE": f"DELETE FROM {_TABLE} WHERE tenant_id=:tenant_id AND operation_id=:operation_id",
        "TRUNCATE": f"TRUNCATE TABLE {_TABLE}",
    }[mutation]
    _s32_reject_sql(db, statement, values, sqlstate="42501", constraint=None, role=role, tenant=tenant)


@pytest.mark.parametrize("mutation", ["UPDATE", "DELETE"])
def test_0008_raw_sql_admin_append_only_guard(repository_database: _RepositoryDatabase, mutation: str) -> None:
    """admin 绕不过既有 guard，真实 UPDATE/DELETE 均 check_violation。

    Args:
        repository_database: 独占随机库。
        mutation: UPDATE 或 DELETE；不停止 RLS/trigger。
    Returns:
        无。
    Raises:
        AssertionError: guard 函数、错误码或七表快照不符。
        DBAPIError: 正例/catalog 操作失败。
    """
    db = repository_database
    values = _s32_receipt_sql_values(db)
    _s32_insert_receipt_sql(db, values)
    with db.admin.connect() as connection:
        assert connection.execute(
            text(
                "SELECT t.tgname,t.tgenabled,n.nspname,p.proname,p.prosecdef,p.proconfig "
                "FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE t.tgrelid='dayu_platform.candidate_intake_receipts'::regclass AND NOT t.tgisinternal"
            )
        ).all() == [
            (
                "candidate_intake_receipts_append_only_trigger",
                "O",
                "dayu_platform",
                "guard_evidence_append_only",
                False,
                None,
            )
        ]
    statement = (
        f"UPDATE {_TABLE} SET created_at=created_at WHERE tenant_id=:tenant_id AND operation_id=:operation_id"
        if mutation == "UPDATE"
        else f"DELETE FROM {_TABLE} WHERE tenant_id=:tenant_id AND operation_id=:operation_id"
    )
    _s32_reject_sql(db, statement, values, sqlstate="23514", constraint=None)


def test_0008_raw_sql_audit_read_only_insert_denied(repository_database: _RepositoryDatabase) -> None:
    """audit 可 SELECT 已有 receipt，却不能 INSERT 尚无唯一键冲突的新 receipt。

    Args:
        repository_database: 独占随机库。
    Returns:
        无。
    Raises:
        AssertionError: audit 读取、错误码或七表快照不符。
        DBAPIError: 正例准备失败。
    """
    db = repository_database
    values = _s32_receipt_sql_values(db)
    before = _snapshot(db)
    with db.admin.begin() as connection:
        connection.exec_driver_sql(f"SET LOCAL ROLE {PLATFORM_AUDIT_ROLE}")
        assert connection.execute(text(f"SELECT count(*) FROM {_TABLE}")).scalar_one() == 1
    assert _snapshot(db) == before
    _s32_reject_sql(db, _S32_RECEIPT_INSERT, values, sqlstate="42501", constraint=None, role=PLATFORM_AUDIT_ROLE)


@pytest.mark.parametrize("context", ["unset", "wrong"])
def test_0008_raw_sql_app_insert_requires_exact_tenant_context(
    repository_database: _RepositoryDatabase,
    context: str,
) -> None:
    """unset/wrong tenant 的 app INSERT 由 RLS 拒绝，不用跨库或真实凭据。

    Args:
        repository_database: 独占随机库。
        context: 未设置或明确错误的合成租户。
    Returns:
        无。
    Raises:
        AssertionError: RLS 错误码或七表快照不符。
        DBAPIError: staging 准备失败。
    """
    db = repository_database
    values = _s32_receipt_sql_values(db)
    _s32_reject_sql(
        db,
        _S32_RECEIPT_INSERT,
        values,
        sqlstate="42501",
        constraint=None,
        role=PLATFORM_APP_ROLE,
        tenant=uuid4() if context == "wrong" else None,
    )
