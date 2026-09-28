"""建立私有 immutable intake receipt，不改变0007证据或guard。

Revision ID: 0008_candidate_intake
Revises: 0007_strict_evidence

只由bootstrap superuser在精确33表baseline新建；回退仅允许精确own
catalog、空receipt、无外部权限/依赖和NOWAIT独占锁，失败整体回滚。
"""

from __future__ import annotations

import hashlib

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from dayu.investment.storage.db import (
    PLATFORM_APP_ROLE,
    PLATFORM_AUDIT_ROLE,
    PLATFORM_SCHEMA_NAME,
    PlatformMigrationAdmissionError,
)

revision = "0008_candidate_intake"
down_revision = "0007_strict_evidence"
branch_labels = None
depends_on = None

_SCHEMA = PLATFORM_SCHEMA_NAME
_TABLE = "candidate_intake_receipts"
_TRIGGER = "candidate_intake_receipts_append_only_trigger"
_GUARD_BODY = "\nBEGIN\n    RAISE EXCEPTION 'immutable evidence row mutation rejected' USING ERRCODE = 'check_violation';\nEND\n"
_OWN_NAMES: tuple[str, ...] = (
    _TABLE, "pk_candidate_intake_receipts", "uq_candidate_intake_receipts_tenant_candidate",
    "fk_candidate_intake_receipts_candidate", "fk_candidate_intake_receipts_security",
    "fk_candidate_intake_receipts_tenant_id_organizations", "fk_candidate_intake_receipts_company_id_companies",
    "ck_candidate_intake_receipts_origin", "ck_candidate_intake_receipts_schema_version",
    "ck_candidate_intake_receipts_extractor_nonblank", "ck_candidate_intake_receipts_raw_bytes",
    "ck_candidate_intake_receipts_raw_sha256", "ck_candidate_intake_receipts_request_fingerprint",
    "ck_candidate_intake_receipts_payload_sha256", "ck_candidate_intake_receipts_locator_sha256",
    "ck_candidate_intake_receipts_citation_sha256", "ck_candidate_intake_receipts_outcome_shape",
)
_BASELINE_TABLES = frozenset({
    "organizations", "companies", "securities", "source_definitions", "users", "roles",
    "permissions", "user_roles", "role_permissions", "api_tokens", "source_subscriptions",
    "source_sync_runs", "source_health_snapshots", "source_sync_operations", "source_health_states",
    "source_health_alert_outbox", "workspace_import_markers", "research_bundle_locators",
    "job_definitions", "job_runs", "job_attempts", "job_leases", "job_attempt_receipts",
    "job_events", "agent_run_correlations", "job_schedules", "job_schedule_occurrences",
    "facts", "claims", "claim_versions", "evidence_links", "claim_conflicts", "research_candidates",
})
_PUBLIC_TABLES = frozenset({"companies", "securities", "source_definitions"})

_TABLE_DDL = """CREATE TABLE dayu_platform.candidate_intake_receipts (
 tenant_id UUID NOT NULL,
 operation_id UUID NOT NULL,
 company_id UUID NOT NULL,
 security_id UUID NOT NULL,
 security_ticker TEXT NOT NULL,
 candidate_id UUID NOT NULL,
 origin TEXT NOT NULL,
 extractor_version TEXT NOT NULL,
 schema_version TEXT NOT NULL,
 raw_sha256 CHAR(64) NOT NULL,
 raw_bytes BIGINT NOT NULL,
 request_fingerprint CHAR(64) NOT NULL,
 payload_sha256 CHAR(64) NOT NULL,
 outcome TEXT NOT NULL,
 rejection_code TEXT,
 locator_sha256 CHAR(64),
 citation_sha256 CHAR(64),
 fins_checked_at TIMESTAMP WITH TIME ZONE,
 created_at TIMESTAMP WITH TIME ZONE DEFAULT statement_timestamp() NOT NULL,
 CONSTRAINT pk_candidate_intake_receipts PRIMARY KEY (tenant_id, operation_id),
 CONSTRAINT uq_candidate_intake_receipts_tenant_candidate UNIQUE (tenant_id, candidate_id),
 CONSTRAINT fk_candidate_intake_receipts_candidate FOREIGN KEY(tenant_id, company_id, candidate_id) REFERENCES dayu_platform.research_candidates (tenant_id, company_id, id) ON DELETE RESTRICT,
 CONSTRAINT fk_candidate_intake_receipts_security FOREIGN KEY(company_id, security_id, security_ticker) REFERENCES dayu_platform.securities (company_id, id, ticker) ON DELETE RESTRICT,
 CONSTRAINT ck_candidate_intake_receipts_origin CHECK (origin IN ('agent','human')),
 CONSTRAINT ck_candidate_intake_receipts_schema_version CHECK (schema_version = 'candidate_intake.v1'),
 CONSTRAINT ck_candidate_intake_receipts_extractor_nonblank CHECK (extractor_version <> '' AND extractor_version = btrim(extractor_version)),
 CONSTRAINT ck_candidate_intake_receipts_raw_bytes CHECK (raw_bytes >= 0),
 CONSTRAINT ck_candidate_intake_receipts_raw_sha256 CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
 CONSTRAINT ck_candidate_intake_receipts_request_fingerprint CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
 CONSTRAINT ck_candidate_intake_receipts_payload_sha256 CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
 CONSTRAINT ck_candidate_intake_receipts_locator_sha256 CHECK (locator_sha256 IS NULL OR locator_sha256 ~ '^[0-9a-f]{64}$'),
 CONSTRAINT ck_candidate_intake_receipts_citation_sha256 CHECK (citation_sha256 IS NULL OR citation_sha256 ~ '^[0-9a-f]{64}$'),
 CONSTRAINT ck_candidate_intake_receipts_outcome_shape CHECK (((outcome = 'proposed' AND rejection_code IS NULL AND locator_sha256 IS NOT NULL AND citation_sha256 IS NOT NULL AND fins_checked_at IS NOT NULL) OR (outcome = 'rejected' AND rejection_code IN ('candidate_payload_too_large','candidate_json_invalid','candidate_schema_invalid','unsupported_material_claim','evidence_missing','evidence_cross_ticker','evidence_unavailable','evidence_ambiguous_owner','evidence_stale','evidence_fragment_unresolved','evidence_readback_mismatch') AND locator_sha256 IS NULL AND citation_sha256 IS NULL AND fins_checked_at IS NULL)) IS TRUE),
 CONSTRAINT fk_candidate_intake_receipts_tenant_id_organizations FOREIGN KEY(tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
 CONSTRAINT fk_candidate_intake_receipts_company_id_companies FOREIGN KEY(company_id) REFERENCES dayu_platform.companies (id) ON DELETE RESTRICT
)"""

# 固定PG16 catalog投影包括精确列/keys/checks/index/policy/trigger/ACL。
# 在独占 PG16.14 fresh DB 逐六投影测量后冻结；往返测试独立复核。
_EXPECTED_CATALOG_SHA256 = "06a30f5fbef25ae3c438cbb897eeacb5a75c07723daa49e6358528ef939327bc"
_CATALOG_QUERIES: tuple[str, ...] = (
    "SELECT coalesce(json_agg(row_to_json(x)), '[]')::text FROM (SELECT a.attname, "
    "format_type(a.atttypid,a.atttypmod) AS type, a.attnotnull, "
    "pg_get_expr(d.adbin,d.adrelid) AS column_default, a.attidentity,a.attgenerated,a.attacl::text "
    "FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
    "WHERE a.attrelid='dayu_platform.candidate_intake_receipts'::regclass "
    "AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum) x",
    "SELECT coalesce(json_agg(row_to_json(x)), '[]')::text FROM (SELECT conname,contype, "
    "pg_get_constraintdef(oid,true) AS definition,convalidated,condeferrable,condeferred "
    "FROM pg_constraint WHERE conrelid='dayu_platform.candidate_intake_receipts'::regclass ORDER BY conname) x",
    "SELECT coalesce(json_agg(row_to_json(x)), '[]')::text FROM (SELECT indexname,indexdef "
    "FROM pg_indexes WHERE schemaname='dayu_platform' AND tablename='candidate_intake_receipts' ORDER BY indexname) x",
    "SELECT coalesce(json_agg(row_to_json(x)), '[]')::text FROM (SELECT polname,polcmd,polpermissive, "
    "ARRAY(SELECT rolname FROM pg_roles WHERE oid=ANY(polroles) ORDER BY rolname) AS roles, "
    "pg_get_expr(polqual,polrelid) AS qual,pg_get_expr(polwithcheck,polrelid) AS withcheck "
    "FROM pg_policy WHERE polrelid='dayu_platform.candidate_intake_receipts'::regclass ORDER BY polname) x",
    "SELECT coalesce(json_agg(row_to_json(x)), '[]')::text FROM (SELECT t.tgname,t.tgenabled, "
    "pg_get_triggerdef(t.oid,true) AS definition,n.nspname,p.proname,p.prosecdef,p.proconfig,p.prosrc, "
    "p.proowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) AS owned "
    "FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace n ON n.oid=p.pronamespace "
    "WHERE t.tgrelid='dayu_platform.candidate_intake_receipts'::regclass AND NOT t.tgisinternal ORDER BY tgname) x",
    "SELECT coalesce(json_agg(row_to_json(x)), '[]')::text FROM (SELECT gr.rolname, acl.privilege_type, "
    "acl.is_grantable, acl.grantor=c.relowner AS owner_grant FROM pg_class c "
    "CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) acl "
    "LEFT JOIN pg_roles gr ON gr.oid=acl.grantee WHERE c.oid='dayu_platform.candidate_intake_receipts'::regclass "
    "AND acl.grantee<>c.relowner ORDER BY gr.rolname,acl.privilege_type) x",
)


def _fail(reason: str) -> None:
    """以固定safe原因拒绝迁移。

    Args:
        reason: 已分类原因。
    Returns:
        不返回。
    Raises:
        PlatformMigrationAdmissionError: 总是拒绝。
    """
    raise PlatformMigrationAdmissionError("0008 candidate intake admission: " + reason)


def _baseline(connection: Connection, *, reverting: bool) -> None:
    """验证bootstrap owner、roles、head、精确表/RLS和旧guard。

    Args:
        connection: Alembic当前事务。
        reverting: 当前为0008回退或0007升迁。
    Returns:
        无。
    Raises:
        PlatformMigrationAdmissionError: baseline不匹配。
    """
    admission = connection.execute(text(
        "SELECT r.rolsuper,n.nspowner=r.oid FROM pg_roles r JOIN pg_namespace n "
        "ON n.nspname=:schema WHERE r.rolname=current_user"
    ), {"schema": _SCHEMA}).first()
    if admission != (True, True):
        _fail("bootstrap_owner_required")
    if connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all() != [revision if reverting else down_revision]:
        _fail("head_mismatch")
    roles = connection.execute(text("SELECT rolname,rolsuper,rolcanlogin,rolbypassrls FROM pg_roles "
        "WHERE rolname IN (:app,:audit) ORDER BY rolname"), {"app": PLATFORM_APP_ROLE, "audit": PLATFORM_AUDIT_ROLE}).all()
    if roles != [(PLATFORM_APP_ROLE, False, False, False), (PLATFORM_AUDIT_ROLE, False, False, True)]:
        _fail("role_baseline_mismatch")
    tables = connection.execute(text("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND c.relkind='r'"), {"schema": _SCHEMA}).all()
    wanted = _BASELINE_TABLES | ({_TABLE} if reverting else set())
    if {r[0] for r in tables} != wanted:
        _fail("tables_mismatch")
    if any((enabled, forced) != (name not in _PUBLIC_TABLES, name not in _PUBLIC_TABLES) for name, enabled, forced in tables):
        _fail("rls_baseline_mismatch")
    guard = connection.execute(text("SELECT p.proowner=r.oid,p.prosecdef,p.proconfig,p.prorettype='trigger'::regtype,p.prosrc "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.rolname=current_user "
        "WHERE n.nspname=:schema AND p.proname='guard_evidence_append_only' AND p.pronargs=0"), {"schema": _SCHEMA}).all()
    if guard != [(True, False, None, True, _GUARD_BODY)]:
        _fail("guard_baseline_mismatch")


def _catalog_digest(connection: Connection) -> str:
    """独立编码PG16机械catalog投影，不混入OID、凭据或宿主时间。

    Args:
        connection: 已锁定目标的事务。
    Returns:
        全六类own对象规范投影摘要。
    Raises:
        PlatformMigrationAdmissionError: 结果不是文本。
    """
    digest = hashlib.sha256()
    for query in _CATALOG_QUERIES:
        result = connection.execute(text(query)).scalar_one()
        if type(result) is not str:
            _fail("catalog_projection_invalid")
        raw = result.encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def upgrade() -> None:
    """由精确0007建立一个私有table及guard/RLS/最小权限。

    Args:
        无。
    Returns:
        无。
    Raises:
        PlatformMigrationAdmissionError: baseline或命名空间被占用。
        DBAPIError: DDL失败整体rollback。
    """
    connection = op.get_bind()
    _baseline(connection, reverting=False)
    # 不借IF NOT EXISTS接管任何外部relation/constraint/trigger。
    collision_query = text(
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=:schema AND c.relname IN :names "
        "UNION ALL SELECT 1 FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace "
        "WHERE n.nspname=:schema AND c.conname IN :names "
        "UNION ALL SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=:schema AND t.tgname=:trigger LIMIT 1"
    ).bindparams(bindparam("names", expanding=True))
    collision = connection.execute(collision_query,
        {"schema": _SCHEMA, "names": _OWN_NAMES, "trigger": _TRIGGER}).first()
    if collision is not None:
        _fail("object_name_collision")
    op.execute(_TABLE_DDL)
    op.execute(f"CREATE TRIGGER {_TRIGGER} BEFORE UPDATE OR DELETE ON {_SCHEMA}.{_TABLE} FOR EACH ROW EXECUTE FUNCTION {_SCHEMA}.guard_evidence_append_only()")
    op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.{_TABLE} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON TABLE {_SCHEMA}.{_TABLE} TO {PLATFORM_APP_ROLE}")
    op.execute(f"GRANT SELECT ON TABLE {_SCHEMA}.{_TABLE} TO {PLATFORM_AUDIT_ROLE}")
    op.execute(f"ALTER TABLE {_SCHEMA}.{_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_SCHEMA}.{_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {_SCHEMA}.{_TABLE} FOR ALL TO {PLATFORM_APP_ROLE} USING (nullif(current_setting('app.tenant_id', true), '')::uuid = tenant_id) WITH CHECK (nullif(current_setting('app.tenant_id', true), '')::uuid = tenant_id)")
    if _catalog_digest(connection) != _EXPECTED_CATALOG_SHA256:
        _fail("own_manifest_mismatch")


def downgrade() -> None:
    """只删除精确空0008own对象，原guard与六表不改。

    Args:
        无。
    Returns:
        无。
    Raises:
        PlatformMigrationAdmissionError: own catalog、业务行或依赖拒绝。
        DBAPIError: NOWAIT锁/RESTRICT外部依赖失败整体rollback。
    """
    connection = op.get_bind()
    _baseline(connection, reverting=True)
    op.execute(f"LOCK TABLE {_SCHEMA}.{_TABLE} IN ACCESS EXCLUSIVE MODE NOWAIT")
    table_owner = connection.execute(text("SELECT c.relowner=r.oid,c.relkind,c.relpersistence "
        "FROM pg_class c JOIN pg_roles r ON r.rolname=current_user WHERE c.oid='dayu_platform.candidate_intake_receipts'::regclass")).first()
    if table_owner != (True, "r", "p") or _catalog_digest(connection) != _EXPECTED_CATALOG_SHA256:
        _fail("own_manifest_mismatch")
    if connection.execute(text(f"SELECT EXISTS(SELECT 1 FROM {_SCHEMA}.{_TABLE})")).scalar_one():
        _fail("business_rows_present")
    # DROP RESTRICT作为最终依赖门；任何view/FK/其它依赖失败同事务保留全部对象/revision。
    op.execute(f"DROP TRIGGER {_TRIGGER} ON {_SCHEMA}.{_TABLE}")
    op.execute(f"DROP POLICY tenant_isolation ON {_SCHEMA}.{_TABLE}")
    op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.{_TABLE} FROM {PLATFORM_APP_ROLE}, {PLATFORM_AUDIT_ROLE}")
    op.execute(f"DROP TABLE {_SCHEMA}.{_TABLE} RESTRICT")
