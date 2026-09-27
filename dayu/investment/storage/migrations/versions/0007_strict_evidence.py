"""建立 Slice 3.1 严格证据六表及 PostgreSQL 闭合约束。

Revision ID: 0007_strict_evidence
Revises: 0006_job_request_identity

本迁移只接受精确 0006 baseline；0007 的 DDL 在 Alembic 单事务执行。
downgrade 只接受空六表和无外部依赖，拒绝时事务保留原版本。
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection

from dayu.investment.storage.db import (
    PLATFORM_APP_ROLE,
    PLATFORM_AUDIT_ROLE,
    PLATFORM_SCHEMA_NAME,
    PlatformMigrationAdmissionError,
)

revision = "0007_strict_evidence"
down_revision = "0006_job_request_identity"
branch_labels = None
depends_on = None

_SCHEMA = PLATFORM_SCHEMA_NAME
_TABLES: tuple[str, ...] = (
    "facts", "claims", "claim_versions", "evidence_links",
    "claim_conflicts", "research_candidates",
)
_DROP_TABLES: tuple[str, ...] = (
    "claim_conflicts", "evidence_links", "claim_versions",
    "claims", "facts", "research_candidates",
)
_BASELINE_TABLES: frozenset[str] = frozenset({
    "organizations", "companies", "securities", "source_definitions", "users",
    "roles", "permissions", "user_roles", "role_permissions", "api_tokens",
    "source_subscriptions", "source_sync_runs", "source_health_snapshots",
    "source_sync_operations", "source_health_states", "source_health_alert_outbox",
    "workspace_import_markers", "research_bundle_locators", "job_definitions",
    "job_runs", "job_attempts", "job_leases", "job_attempt_receipts",
    "job_events", "agent_run_correlations", "job_schedules",
    "job_schedule_occurrences",
})
_BASELINE_PUBLIC_TABLES: frozenset[str] = frozenset({
    "companies", "securities", "source_definitions",
})
_FUNCTIONS: tuple[str, ...] = (
    "evidence_decimal_valid", "evidence_locator_valid",
    "evidence_link_digest_insert", "guard_evidence_append_only",
)
_TRIGGERS: tuple[str, ...] = (
    "evidence_links_digest_insert_trigger",
    "facts_append_only_trigger", "claim_versions_append_only_trigger",
    "evidence_links_append_only_trigger",
)

# 编译后的静态 ORM DDL 在实现时冻结于本迁移，不在运行时导入 ORM。
_TABLE_DDL: tuple[str, ...] = (
    """CREATE TABLE dayu_platform.facts (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	company_id UUID NOT NULL,
	security_id UUID NOT NULL,
	locator_ticker TEXT NOT NULL,
	locator_json JSONB NOT NULL,
	fact_series_id UUID NOT NULL,
	revision_no INTEGER NOT NULL,
	prior_fact_id UUID,
	fact_key TEXT NOT NULL,
	metric TEXT NOT NULL,
	value_kind TEXT NOT NULL,
	value_decimal NUMERIC,
	value_text TEXT,
	value_date DATE,
	value_boolean BOOLEAN,
	unit_code TEXT,
	currency CHAR(3),
	period_start DATE,
	period_end DATE,
	effective_at TIMESTAMP WITH TIME ZONE NOT NULL,
	published_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ingested_at TIMESTAMP WITH TIME ZONE NOT NULL,
	available_at TIMESTAMP WITH TIME ZONE NOT NULL,
	extractor_version TEXT NOT NULL,
	verification_status TEXT NOT NULL,
	verifier_user_id UUID,
	verified_at TIMESTAMP WITH TIME ZONE,
	operation_id UUID NOT NULL,
	operation_fingerprint CHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL,
	CONSTRAINT pk_facts PRIMARY KEY (id),
	CONSTRAINT uq_facts_tenant_company_id UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_facts_series_revision UNIQUE (tenant_id, company_id, fact_series_id, revision_no),
	CONSTRAINT uq_facts_tenant_operation UNIQUE (tenant_id, operation_id),
	CONSTRAINT fk_facts_security_ticker FOREIGN KEY(company_id, security_id, locator_ticker) REFERENCES dayu_platform.securities (company_id, id, ticker) ON DELETE RESTRICT,
	CONSTRAINT fk_facts_prior FOREIGN KEY(tenant_id, company_id, prior_fact_id) REFERENCES dayu_platform.facts (tenant_id, company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_facts_verifier FOREIGN KEY(tenant_id, verifier_user_id) REFERENCES dayu_platform.users (tenant_id, id) ON DELETE RESTRICT,
	CONSTRAINT ck_facts_revision_shape CHECK (revision_no > 0 AND ((revision_no = 1 AND prior_fact_id IS NULL) OR (revision_no > 1 AND prior_fact_id IS NOT NULL))),
	CONSTRAINT ck_facts_fact_key_nonblank CHECK (fact_key <> '' AND fact_key = btrim(fact_key)),
	CONSTRAINT ck_facts_metric_nonblank CHECK (metric <> '' AND metric = btrim(metric)),
	CONSTRAINT ck_facts_extractor_nonblank CHECK (extractor_version <> '' AND extractor_version = btrim(extractor_version)),
	CONSTRAINT ck_facts_period_shape CHECK ((period_start IS NULL AND period_end IS NULL) OR (period_start IS NOT NULL AND period_end IS NOT NULL AND period_start <= period_end)),
	CONSTRAINT ck_facts_time_order CHECK (published_at <= ingested_at AND ingested_at <= available_at),
	CONSTRAINT ck_facts_verification_status CHECK (verification_status IN ('unverified','verified','invalidated')),
	CONSTRAINT ck_facts_verification_witness CHECK ((verification_status = 'unverified' AND verifier_user_id IS NULL AND verified_at IS NULL) OR (verification_status <> 'unverified' AND verifier_user_id IS NOT NULL AND verified_at IS NOT NULL)),
	CONSTRAINT ck_facts_locator CHECK (dayu_platform.evidence_locator_valid(locator_json) IS TRUE),
	CONSTRAINT ck_facts_locator_ticker CHECK (((jsonb_typeof(locator_json->'ticker') = 'string') AND (locator_ticker = locator_json->>'ticker')) IS TRUE),
	CONSTRAINT ck_facts_decimal_bound CHECK (dayu_platform.evidence_decimal_valid(value_decimal) IS TRUE OR value_kind <> 'decimal'),
	CONSTRAINT ck_facts_value_shape CHECK (((value_kind = 'decimal' AND value_decimal IS NOT NULL AND value_text IS NULL AND value_date IS NULL AND value_boolean IS NULL) OR (value_kind = 'text' AND value_decimal IS NULL AND value_text IS NOT NULL AND value_text <> '' AND value_date IS NULL AND value_boolean IS NULL) OR (value_kind = 'date' AND value_decimal IS NULL AND value_text IS NULL AND value_date IS NOT NULL AND value_boolean IS NULL) OR (value_kind = 'boolean' AND value_decimal IS NULL AND value_text IS NULL AND value_date IS NULL AND value_boolean IS NOT NULL)) IS TRUE),
	CONSTRAINT ck_facts_unit_shape CHECK (((value_kind = 'decimal' AND unit_code IS NOT NULL AND unit_code <> '' AND unit_code = btrim(unit_code) AND ((unit_code = 'currency' AND currency ~ '^[A-Z]{3}$') OR (unit_code <> 'currency' AND currency IS NULL))) OR (value_kind <> 'decimal' AND unit_code IS NULL AND currency IS NULL)) IS TRUE),
	CONSTRAINT ck_facts_operation_fingerprint CHECK (operation_fingerprint ~ '^[0-9a-f]{64}$'),
	CONSTRAINT fk_facts_tenant_id_organizations FOREIGN KEY(tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_facts_company_id_companies FOREIGN KEY(company_id) REFERENCES dayu_platform.companies (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE dayu_platform.claims (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	company_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL,
	version INTEGER DEFAULT 1 NOT NULL,
	CONSTRAINT pk_claims PRIMARY KEY (id),
	CONSTRAINT uq_claims_tenant_company_id UNIQUE (tenant_id, company_id, id),
	CONSTRAINT ck_claims_version_positive CHECK (version > 0),
	CONSTRAINT fk_claims_tenant_id_organizations FOREIGN KEY(tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_claims_company_id_companies FOREIGN KEY(company_id) REFERENCES dayu_platform.companies (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE dayu_platform.claim_versions (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	company_id UUID NOT NULL,
	claim_id UUID NOT NULL,
	version_no INTEGER NOT NULL,
	transition_kind TEXT NOT NULL,
	evidence_mode TEXT NOT NULL,
	copy_source_version_id UUID,
	operation_id UUID NOT NULL,
	operation_fingerprint CHAR(64) NOT NULL,
	statement TEXT NOT NULL,
	confidence_band TEXT NOT NULL,
	probability NUMERIC,
	impact_horizon TEXT NOT NULL,
	valid_until TIMESTAMP WITH TIME ZONE,
	status TEXT NOT NULL,
	invalidation_rule TEXT NOT NULL,
	transition_reason TEXT,
	author_user_id UUID,
	author_auth_token_id UUID,
	author_auth_checked_at TIMESTAMP WITH TIME ZONE,
	author_auth_policy TEXT,
	reviewer_user_id UUID,
	reviewer_token_id UUID,
	reviewer_user_role_id UUID,
	reviewer_role_permission_id UUID,
	reviewer_permission_id UUID,
	reviewer_permission_key TEXT,
	reviewer_checked_at TIMESTAMP WITH TIME ZONE,
	reviewer_policy TEXT,
	reviewer_reason TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL,
	CONSTRAINT pk_claim_versions PRIMARY KEY (id),
	CONSTRAINT uq_claim_versions_tenant_company_id UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_claim_versions_claim_id UNIQUE (tenant_id, company_id, claim_id, id),
	CONSTRAINT uq_claim_versions_claim_version UNIQUE (tenant_id, claim_id, version_no),
	CONSTRAINT uq_claim_versions_operation UNIQUE (tenant_id, operation_id),
	CONSTRAINT fk_claim_versions_claim FOREIGN KEY(tenant_id, company_id, claim_id) REFERENCES dayu_platform.claims (tenant_id, company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_versions_copy_source FOREIGN KEY(tenant_id, company_id, claim_id, copy_source_version_id) REFERENCES dayu_platform.claim_versions (tenant_id, company_id, claim_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_versions_author FOREIGN KEY(tenant_id, author_user_id) REFERENCES dayu_platform.users (tenant_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_versions_author_token FOREIGN KEY(tenant_id, author_auth_token_id) REFERENCES dayu_platform.api_tokens (tenant_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_versions_reviewer FOREIGN KEY(tenant_id, reviewer_user_id) REFERENCES dayu_platform.users (tenant_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_versions_reviewer_token FOREIGN KEY(tenant_id, reviewer_token_id) REFERENCES dayu_platform.api_tokens (tenant_id, id) ON DELETE RESTRICT,
	CONSTRAINT ck_claim_versions_version_positive CHECK (version_no > 0),
	CONSTRAINT ck_claim_versions_first_version CHECK ((((version_no = 1 AND transition_kind = 'claim_create' AND evidence_mode = 'replace_all' AND status = 'draft') OR (version_no > 1 AND transition_kind <> 'claim_create')) IS TRUE)),
	CONSTRAINT ck_claim_versions_evidence_mode CHECK (((evidence_mode = 'replace_all' AND copy_source_version_id IS NULL) OR (evidence_mode = 'copy_previous' AND copy_source_version_id IS NOT NULL)) IS TRUE),
	CONSTRAINT ck_claim_versions_statement_nonblank CHECK (statement <> '' AND statement = btrim(statement)),
	CONSTRAINT ck_claim_versions_invalidation_rule CHECK (invalidation_rule <> '' AND invalidation_rule = btrim(invalidation_rule)),
	CONSTRAINT ck_claim_versions_confidence_band CHECK (confidence_band IN ('low','medium','high')),
	CONSTRAINT ck_claim_versions_impact_horizon CHECK (impact_horizon IN ('short','medium','long')),
	CONSTRAINT ck_claim_versions_probability CHECK (probability IS NULL OR (probability >= 0 AND probability <= 1)),
	CONSTRAINT ck_claim_versions_status CHECK (status IN ('draft','in_review','approved','rejected','invalidated','review_required','superseded')),
	CONSTRAINT ck_claim_versions_transition_kind CHECK (transition_kind IN ('claim_create','content_revision','submit_review','begin_revision','review_decision','expiry','conflict_resolution')),
	CONSTRAINT ck_claim_versions_transition_reason CHECK (transition_reason IS NULL OR (transition_reason <> '' AND transition_reason = btrim(transition_reason))),
	CONSTRAINT ck_claim_versions_action_witness CHECK (((transition_kind = 'begin_revision' AND status = 'draft' AND author_user_id IS NOT NULL AND transition_reason IS NOT NULL AND author_auth_token_id IS NOT NULL AND author_auth_checked_at IS NOT NULL AND author_auth_policy IS NOT NULL AND author_auth_policy <> '' AND reviewer_user_id IS NULL AND reviewer_token_id IS NULL AND reviewer_user_role_id IS NULL AND reviewer_role_permission_id IS NULL AND reviewer_permission_id IS NULL AND reviewer_permission_key IS NULL AND reviewer_checked_at IS NULL AND reviewer_policy IS NULL AND reviewer_reason IS NULL) OR (transition_kind IN ('review_decision','conflict_resolution') AND author_auth_token_id IS NULL AND author_auth_checked_at IS NULL AND author_auth_policy IS NULL AND reviewer_user_id IS NOT NULL AND reviewer_token_id IS NOT NULL AND reviewer_user_role_id IS NOT NULL AND reviewer_role_permission_id IS NOT NULL AND reviewer_permission_id IS NOT NULL AND reviewer_permission_key = 'investment.claim.review' AND reviewer_checked_at IS NOT NULL AND reviewer_policy IS NOT NULL AND reviewer_policy <> '' AND reviewer_reason IS NOT NULL AND reviewer_reason <> '') OR (transition_kind IN ('claim_create','content_revision','submit_review','expiry') AND author_auth_token_id IS NULL AND author_auth_checked_at IS NULL AND author_auth_policy IS NULL AND reviewer_user_id IS NULL AND reviewer_token_id IS NULL AND reviewer_user_role_id IS NULL AND reviewer_role_permission_id IS NULL AND reviewer_permission_id IS NULL AND reviewer_permission_key IS NULL AND reviewer_checked_at IS NULL AND reviewer_policy IS NULL AND reviewer_reason IS NULL AND (transition_kind <> 'expiry' OR (status = 'review_required' AND transition_reason IS NOT NULL)))) IS TRUE),
	CONSTRAINT ck_claim_versions_operation_fingerprint CHECK (operation_fingerprint ~ '^[0-9a-f]{64}$'),
	CONSTRAINT fk_claim_versions_tenant_id_organizations FOREIGN KEY(tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_versions_company_id_companies FOREIGN KEY(company_id) REFERENCES dayu_platform.companies (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE dayu_platform.evidence_links (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	company_id UUID NOT NULL,
	claim_version_id UUID NOT NULL,
	relation TEXT NOT NULL,
	fact_id UUID,
	security_id UUID,
	locator_ticker TEXT,
	locator_json JSONB,
	locator_index_digest BYTEA,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL,
	CONSTRAINT pk_evidence_links PRIMARY KEY (id),
	CONSTRAINT uq_evidence_links_tenant_company_id UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_evidence_links_version_id UNIQUE (tenant_id, company_id, claim_version_id, id),
	CONSTRAINT fk_evidence_links_version FOREIGN KEY(tenant_id, company_id, claim_version_id) REFERENCES dayu_platform.claim_versions (tenant_id, company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_evidence_links_fact FOREIGN KEY(tenant_id, company_id, fact_id) REFERENCES dayu_platform.facts (tenant_id, company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_evidence_links_security_ticker FOREIGN KEY(company_id, security_id, locator_ticker) REFERENCES dayu_platform.securities (company_id, id, ticker) ON DELETE RESTRICT,
	CONSTRAINT ck_evidence_links_relation CHECK (relation IN ('supports','contradicts','context')),
	CONSTRAINT ck_evidence_links_target_arm CHECK (((fact_id IS NOT NULL AND security_id IS NULL AND locator_ticker IS NULL AND locator_json IS NULL AND locator_index_digest IS NULL) OR (fact_id IS NULL AND security_id IS NOT NULL AND locator_ticker IS NOT NULL AND locator_json IS NOT NULL AND locator_index_digest IS NOT NULL AND octet_length(locator_index_digest) = 32 AND jsonb_typeof(locator_json->'ticker') = 'string' AND locator_ticker = locator_json->>'ticker')) IS TRUE),
	CONSTRAINT ck_evidence_links_locator CHECK (locator_json IS NULL OR dayu_platform.evidence_locator_valid(locator_json) IS TRUE),
	CONSTRAINT fk_evidence_links_tenant_id_organizations FOREIGN KEY(tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_evidence_links_company_id_companies FOREIGN KEY(company_id) REFERENCES dayu_platform.companies (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE dayu_platform.claim_conflicts (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	company_id UUID NOT NULL,
	left_version_id UUID NOT NULL,
	right_version_id UUID NOT NULL,
	material BOOLEAN NOT NULL,
	status TEXT NOT NULL,
	reason TEXT NOT NULL,
	operation_id UUID NOT NULL,
	operation_fingerprint CHAR(64) NOT NULL,
	resolution_operation_id UUID,
	resolution_operation_fingerprint CHAR(64),
	resolution_new_version_id UUID,
	resolution_new_link_id UUID,
	resolution_reviewer_user_id UUID,
	resolution_reviewer_token_id UUID,
	resolution_user_role_id UUID,
	resolution_role_permission_id UUID,
	resolution_permission_id UUID,
	resolution_permission_key TEXT,
	resolution_checked_at TIMESTAMP WITH TIME ZONE,
	resolution_policy TEXT,
	resolution_reason TEXT,
	resolved_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL,
	version INTEGER DEFAULT 1 NOT NULL,
	CONSTRAINT pk_claim_conflicts PRIMARY KEY (id),
	CONSTRAINT uq_claim_conflicts_tenant_company_id UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_claim_conflicts_pair UNIQUE (tenant_id, company_id, left_version_id, right_version_id),
	CONSTRAINT uq_claim_conflicts_operation UNIQUE (tenant_id, operation_id),
	CONSTRAINT fk_claim_conflicts_left FOREIGN KEY(tenant_id, company_id, left_version_id) REFERENCES dayu_platform.claim_versions (tenant_id, company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_conflicts_right FOREIGN KEY(tenant_id, company_id, right_version_id) REFERENCES dayu_platform.claim_versions (tenant_id, company_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_conflicts_resolution_link FOREIGN KEY(tenant_id, company_id, resolution_new_version_id, resolution_new_link_id) REFERENCES dayu_platform.evidence_links (tenant_id, company_id, claim_version_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_conflicts_reviewer FOREIGN KEY(tenant_id, resolution_reviewer_user_id) REFERENCES dayu_platform.users (tenant_id, id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_conflicts_reviewer_token FOREIGN KEY(tenant_id, resolution_reviewer_token_id) REFERENCES dayu_platform.api_tokens (tenant_id, id) ON DELETE RESTRICT,
	CONSTRAINT ck_claim_conflicts_endpoint_order CHECK (left_version_id < right_version_id),
	CONSTRAINT ck_claim_conflicts_version_positive CHECK (version > 0),
	CONSTRAINT ck_claim_conflicts_reason_nonblank CHECK (reason <> '' AND reason = btrim(reason)),
	CONSTRAINT ck_claim_conflicts_status CHECK (status IN ('open','resolved')),
	CONSTRAINT ck_claim_conflicts_resolution_witness CHECK (((status = 'open' AND resolution_operation_id IS NULL AND resolution_operation_fingerprint IS NULL AND resolution_new_version_id IS NULL AND resolution_new_link_id IS NULL AND resolution_reviewer_user_id IS NULL AND resolution_reviewer_token_id IS NULL AND resolution_user_role_id IS NULL AND resolution_role_permission_id IS NULL AND resolution_permission_id IS NULL AND resolution_permission_key IS NULL AND resolution_checked_at IS NULL AND resolution_policy IS NULL AND resolution_reason IS NULL AND resolved_at IS NULL) OR (status = 'resolved' AND resolution_operation_id IS NOT NULL AND resolution_operation_fingerprint IS NOT NULL AND resolution_new_version_id IS NOT NULL AND resolution_new_link_id IS NOT NULL AND resolution_reviewer_user_id IS NOT NULL AND resolution_reviewer_token_id IS NOT NULL AND resolution_user_role_id IS NOT NULL AND resolution_role_permission_id IS NOT NULL AND resolution_permission_id IS NOT NULL AND resolution_permission_key = 'investment.claim.review' AND resolution_checked_at IS NOT NULL AND resolution_policy IS NOT NULL AND resolution_reason IS NOT NULL AND resolution_reason <> '' AND resolved_at IS NOT NULL)) IS TRUE),
	CONSTRAINT ck_claim_conflicts_operation_fingerprint CHECK (operation_fingerprint ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_claim_conflicts_resolution_fingerprint CHECK (resolution_operation_fingerprint IS NULL OR resolution_operation_fingerprint ~ '^[0-9a-f]{64}$'),
	CONSTRAINT fk_claim_conflicts_tenant_id_organizations FOREIGN KEY(tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_claim_conflicts_company_id_companies FOREIGN KEY(company_id) REFERENCES dayu_platform.companies (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE dayu_platform.research_candidates (
	id UUID NOT NULL,
	tenant_id UUID NOT NULL,
	company_id UUID NOT NULL,
	origin TEXT NOT NULL,
	canonical_payload_json JSONB NOT NULL,
	sha256 CHAR(64) NOT NULL,
	operation_id UUID NOT NULL,
	operation_fingerprint CHAR(64) NOT NULL,
	state TEXT NOT NULL,
	rejection_code TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT transaction_timestamp() NOT NULL,
	version INTEGER DEFAULT 1 NOT NULL,
	CONSTRAINT pk_research_candidates PRIMARY KEY (id),
	CONSTRAINT uq_research_candidates_tenant_company_id UNIQUE (tenant_id, company_id, id),
	CONSTRAINT uq_research_candidates_operation UNIQUE (tenant_id, operation_id),
	CONSTRAINT ck_research_candidates_origin CHECK (origin IN ('agent','human')),
	CONSTRAINT ck_research_candidates_state CHECK (state IN ('proposed','validated','accepted','rejected')),
	CONSTRAINT ck_research_candidates_version_positive CHECK (version > 0),
	CONSTRAINT ck_research_candidates_payload_object CHECK (jsonb_typeof(canonical_payload_json) = 'object'),
	CONSTRAINT ck_research_candidates_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_research_candidates_operation_fingerprint CHECK (operation_fingerprint ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_research_candidates_rejection_shape CHECK ((state = 'rejected' AND rejection_code IS NOT NULL AND rejection_code <> '') OR (state <> 'rejected' AND rejection_code IS NULL)),
	CONSTRAINT fk_research_candidates_tenant_id_organizations FOREIGN KEY(tenant_id) REFERENCES dayu_platform.organizations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_research_candidates_company_id_companies FOREIGN KEY(company_id) REFERENCES dayu_platform.companies (id) ON DELETE RESTRICT
)""",
)
_INDEX_DDL: tuple[str, ...] = (
    """CREATE INDEX ix_facts_scope_series ON dayu_platform.facts (tenant_id, company_id, fact_series_id, revision_no)""",
    """CREATE INDEX ix_claim_versions_current ON dayu_platform.claim_versions (tenant_id, company_id, claim_id, version_no)""",
    """CREATE UNIQUE INDEX uq_evidence_links_direct_digest ON dayu_platform.evidence_links (tenant_id, claim_version_id, relation, security_id, locator_index_digest) WHERE fact_id IS NULL""",
    """CREATE UNIQUE INDEX uq_evidence_links_fact_target ON dayu_platform.evidence_links (tenant_id, claim_version_id, relation, fact_id) WHERE fact_id IS NOT NULL""",
    """CREATE UNIQUE INDEX uq_claim_conflicts_resolution_operation ON dayu_platform.claim_conflicts (tenant_id, resolution_operation_id) WHERE resolution_operation_id IS NOT NULL""",
)
_NEW_CONSTRAINTS: tuple[str, ...] = ('ck_claim_conflicts_endpoint_order', 'ck_claim_conflicts_operation_fingerprint', 'ck_claim_conflicts_reason_nonblank', 'ck_claim_conflicts_resolution_fingerprint', 'ck_claim_conflicts_resolution_witness', 'ck_claim_conflicts_status', 'ck_claim_conflicts_version_positive', 'ck_claim_versions_action_witness', 'ck_claim_versions_confidence_band', 'ck_claim_versions_evidence_mode', 'ck_claim_versions_first_version', 'ck_claim_versions_impact_horizon', 'ck_claim_versions_invalidation_rule', 'ck_claim_versions_operation_fingerprint', 'ck_claim_versions_probability', 'ck_claim_versions_statement_nonblank', 'ck_claim_versions_status', 'ck_claim_versions_transition_kind', 'ck_claim_versions_transition_reason', 'ck_claim_versions_version_positive', 'ck_claims_version_positive', 'ck_evidence_links_locator', 'ck_evidence_links_relation', 'ck_evidence_links_target_arm', 'ck_facts_decimal_bound', 'ck_facts_extractor_nonblank', 'ck_facts_fact_key_nonblank', 'ck_facts_locator', 'ck_facts_locator_ticker', 'ck_facts_metric_nonblank', 'ck_facts_operation_fingerprint', 'ck_facts_period_shape', 'ck_facts_revision_shape', 'ck_facts_time_order', 'ck_facts_unit_shape', 'ck_facts_value_shape', 'ck_facts_verification_status', 'ck_facts_verification_witness', 'ck_research_candidates_operation_fingerprint', 'ck_research_candidates_origin', 'ck_research_candidates_payload_object', 'ck_research_candidates_rejection_shape', 'ck_research_candidates_sha256', 'ck_research_candidates_state', 'ck_research_candidates_version_positive', 'fk_claim_conflicts_company_id_companies', 'fk_claim_conflicts_left', 'fk_claim_conflicts_resolution_link', 'fk_claim_conflicts_reviewer', 'fk_claim_conflicts_reviewer_token', 'fk_claim_conflicts_right', 'fk_claim_conflicts_tenant_id_organizations', 'fk_claim_versions_author', 'fk_claim_versions_author_token', 'fk_claim_versions_claim', 'fk_claim_versions_company_id_companies', 'fk_claim_versions_copy_source', 'fk_claim_versions_reviewer', 'fk_claim_versions_reviewer_token', 'fk_claim_versions_tenant_id_organizations', 'fk_claims_company_id_companies', 'fk_claims_tenant_id_organizations', 'fk_evidence_links_company_id_companies', 'fk_evidence_links_fact', 'fk_evidence_links_security_ticker', 'fk_evidence_links_tenant_id_organizations', 'fk_evidence_links_version', 'fk_facts_company_id_companies', 'fk_facts_prior', 'fk_facts_security_ticker', 'fk_facts_tenant_id_organizations', 'fk_facts_verifier', 'fk_research_candidates_company_id_companies', 'fk_research_candidates_tenant_id_organizations', 'pk_claim_conflicts', 'pk_claim_versions', 'pk_claims', 'pk_evidence_links', 'pk_facts', 'pk_research_candidates', 'uq_claim_conflicts_operation', 'uq_claim_conflicts_pair', 'uq_claim_conflicts_tenant_company_id', 'uq_claim_versions_claim_id', 'uq_claim_versions_claim_version', 'uq_claim_versions_operation', 'uq_claim_versions_tenant_company_id', 'uq_claims_tenant_company_id', 'uq_evidence_links_tenant_company_id', 'uq_evidence_links_version_id', 'uq_facts_series_revision', 'uq_facts_tenant_company_id', 'uq_facts_tenant_operation', 'uq_research_candidates_operation', 'uq_research_candidates_tenant_company_id')
_NEW_INDEXES: tuple[str, ...] = ('ix_claim_versions_current', 'ix_facts_scope_series', 'uq_claim_conflicts_resolution_operation', 'uq_evidence_links_direct_digest', 'uq_evidence_links_fact_target')

_DECIMAL_FUNCTION = """
CREATE FUNCTION dayu_platform.evidence_decimal_valid(v NUMERIC)
RETURNS BOOLEAN LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT CASE WHEN v::text IN ('NaN', 'Infinity', '-Infinity') THEN FALSE
    ELSE scale(v) BETWEEN 0 AND 12
         AND greatest(1, (CASE WHEN abs(v) < 1 THEN 0
                              ELSE length(trunc(abs(v))::text) END) + scale(v)) <= 38
    END
$$
"""

# Python 3.11 str.strip() 的 29 个 Unicode 空白码点；Fins 与投资域的
# locator 文本解析均使用该规则。U& 转义避免 SQL 文件中的控制字符。
_PYTHON_STRIP_CHARS_SQL = (
    r"U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020"
    r"\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006"
    r"\2007\2008\2009\200A\2028\2029\202F\205F\3000'"
)

_LOCATOR_FUNCTION = """
CREATE FUNCTION dayu_platform.evidence_locator_valid(v JSONB)
RETURNS BOOLEAN LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT (
        jsonb_typeof(v) = 'object'
        AND v = jsonb_build_object(
            'repository_id', v->'repository_id',
            'ticker', v->'ticker',
            'document_id', v->'document_id',
            'source_kind', v->'source_kind',
            'artifact_kind', v->'artifact_kind',
            'document_version', v->'document_version',
            'source_fingerprint', v->'source_fingerprint',
            'primary_content_sha256', v->'primary_content_sha256',
            'locator_kind', v->'locator_kind',
            'locator_payload', v->'locator_payload',
            'locator_content_sha256', v->'locator_content_sha256')
        AND v->>'repository_id' = 'dayu.fins.public.v1'
        AND jsonb_typeof(v->'ticker') = 'string'
        AND (v->>'ticker') ~ '^[A-Za-z0-9][A-Za-z0-9.\\-]*$'
        AND jsonb_typeof(v->'document_id') = 'string'
        AND (v->>'document_id') ~ '^[A-Za-z0-9][A-Za-z0-9_\\-]*$'
        AND jsonb_typeof(v->'source_kind') = 'string'
        AND v->>'source_kind' IN ('filing', 'material')
        AND jsonb_typeof(v->'artifact_kind') = 'string'
        AND v->>'artifact_kind' IN ('source', 'processed')
        AND jsonb_typeof(v->'document_version') = 'string'
        AND v->>'document_version' <> ''
        AND v->>'document_version' = btrim(v->>'document_version', @PYTHON_STRIP_CHARS@)
        AND jsonb_typeof(v->'source_fingerprint') = 'string'
        AND (v->>'source_fingerprint') ~ '^[0-9a-f]{64}$'
        AND jsonb_typeof(v->'primary_content_sha256') = 'string'
        AND (v->>'primary_content_sha256') ~ '^[0-9a-f]{64}$'
        AND jsonb_typeof(v->'locator_kind') = 'string'
        AND v->>'locator_kind' IN ('document','page','section','table_cell','xbrl_fact')
        AND jsonb_typeof(v->'locator_content_sha256') = 'string'
        AND (v->>'locator_content_sha256') ~ '^[0-9a-f]{64}$'
        AND jsonb_typeof(v->'locator_payload') = 'object'
        AND (v->>'artifact_kind' <> 'source' OR v->>'locator_kind' = 'document')
        AND CASE v->>'locator_kind'
            WHEN 'document' THEN v->'locator_payload' = '{}'::jsonb
            WHEN 'page' THEN
                v->'locator_payload' = jsonb_build_object('page_no', v#>'{locator_payload,page_no}')
                AND jsonb_typeof(v#>'{locator_payload,page_no}') = 'number'
                AND (v#>>'{locator_payload,page_no}') ~ '^[0-9]+$'
                AND (v#>>'{locator_payload,page_no}')::numeric > 0
            WHEN 'section' THEN
                v->'locator_payload' = jsonb_build_object('section_ref', v#>'{locator_payload,section_ref}')
                AND jsonb_typeof(v#>'{locator_payload,section_ref}') = 'string'
                AND v#>>'{locator_payload,section_ref}' <> ''
                AND v#>>'{locator_payload,section_ref}' = btrim(v#>>'{locator_payload,section_ref}', @PYTHON_STRIP_CHARS@)
            WHEN 'table_cell' THEN
                v->'locator_payload' = jsonb_build_object(
                    'table_ref', v#>'{locator_payload,table_ref}',
                    'row_index', v#>'{locator_payload,row_index}',
                    'column', v#>'{locator_payload,column}')
                AND jsonb_typeof(v#>'{locator_payload,table_ref}') = 'string'
                AND v#>>'{locator_payload,table_ref}' <> ''
                AND v#>>'{locator_payload,table_ref}' = btrim(v#>>'{locator_payload,table_ref}', @PYTHON_STRIP_CHARS@)
                AND jsonb_typeof(v#>'{locator_payload,row_index}') = 'number'
                AND (v#>>'{locator_payload,row_index}') ~ '^[0-9]+$'
                AND jsonb_typeof(v#>'{locator_payload,column}') = 'string'
                AND v#>>'{locator_payload,column}' <> ''
                AND v#>>'{locator_payload,column}' = btrim(v#>>'{locator_payload,column}', @PYTHON_STRIP_CHARS@)
            WHEN 'xbrl_fact' THEN
                v->'locator_payload' = jsonb_build_object(
                    'concept', v#>'{locator_payload,concept}',
                    'fact_sha256', v#>'{locator_payload,fact_sha256}')
                AND jsonb_typeof(v#>'{locator_payload,concept}') = 'string'
                AND v#>>'{locator_payload,concept}' <> ''
                AND v#>>'{locator_payload,concept}' = btrim(v#>>'{locator_payload,concept}', @PYTHON_STRIP_CHARS@)
                AND jsonb_typeof(v#>'{locator_payload,fact_sha256}') = 'string'
                AND (v#>>'{locator_payload,fact_sha256}') ~ '^[0-9a-f]{64}$'
            ELSE FALSE END
    ) IS TRUE
$$
""".replace("@PYTHON_STRIP_CHARS@", _PYTHON_STRIP_CHARS_SQL)

_DIGEST_FUNCTION = """
CREATE FUNCTION dayu_platform.evidence_link_digest_insert()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.fact_id IS NULL THEN
        NEW.locator_index_digest := sha256(convert_to(NEW.locator_json::text, 'UTF8'));
    ELSE
        NEW.locator_index_digest := NULL;
    END IF;
    RETURN NEW;
END
$$
"""

_APPEND_GUARD_FUNCTION = """
CREATE FUNCTION dayu_platform.guard_evidence_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'immutable evidence row mutation rejected' USING ERRCODE = 'check_violation';
END
$$
"""


def _fail(reason: str) -> None:
    """以无凭据信息的稳定原因拒绝迁移。

    Args:
        reason: 已分类的 catalog 准入原因。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: 总是抛出。
    """

    raise PlatformMigrationAdmissionError(f"0007 strict evidence admission: {reason}")


def _head_is(connection: Connection, wanted: str) -> bool:
    """读取 Alembic 当前单 head 是否符合预期。

    Args:
        connection: 当前 Alembic 事务连接。
        wanted: 预期 revision ID。

    Returns:
        只有唯一 head 等于预期时为真。

    Raises:
        SQLAlchemyError: catalog 查询失败时传播。
    """

    rows = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
    return rows == [wanted]


def _table_names(connection: Connection) -> frozenset[str]:
    """读取平台 schema 内普通表的精确名称集合。

    Args:
        connection: 当前 Alembic 事务连接。

    Returns:
        平台 schema 中的普通表名集合。

    Raises:
        SQLAlchemyError: catalog 查询失败时传播。
    """

    return frozenset(connection.execute(text(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=:schema AND c.relkind='r'"
    ), {"schema": _SCHEMA}).scalars().all())


def _preflight_upgrade(connection: Connection) -> None:
    """确认 0006 head、表、角色、RLS 与全部新增命名空间空闲。

    Args:
        connection: 当前 Alembic 事务连接。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: 任一 baseline 或命名碰撞不符。
    """

    if not _head_is(connection, down_revision):
        _fail("head_mismatch")
    if _table_names(connection) != _BASELINE_TABLES:
        _fail("baseline_tables_mismatch")
    roles = connection.execute(text(
        "SELECT rolname, rolsuper, rolcanlogin, rolbypassrls FROM pg_roles "
        "WHERE rolname IN (:app, :audit) ORDER BY rolname"
    ), {"app": PLATFORM_APP_ROLE, "audit": PLATFORM_AUDIT_ROLE}).all()
    if roles != [
        (PLATFORM_APP_ROLE, False, False, False),
        (PLATFORM_AUDIT_ROLE, False, False, True),
    ]:
        _fail("role_baseline_mismatch")
    columns = connection.execute(text(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema=:schema AND table_name='securities' "
        "AND column_name IN ('company_id','id','ticker') ORDER BY column_name"
    ), {"schema": _SCHEMA}).all()
    if columns != [("company_id", "uuid", "NO"), ("id", "uuid", "NO"), ("ticker", "text", "NO")]:
        _fail("security_columns_mismatch")
    key_count = connection.execute(text(
        "SELECT count(*) FROM pg_constraint WHERE conrelid='dayu_platform.securities'::regclass "
        "AND conname IN ('pk_securities','uq_securities_exchange_mic_ticker')"
    )).scalar_one()
    if key_count != 2:
        _fail("security_keys_mismatch")
    rls = connection.execute(text(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=:schema AND c.relkind='r'"
    ), {"schema": _SCHEMA}).all()
    for table_name, enabled, forced in rls:
        expected_private = table_name not in _BASELINE_PUBLIC_TABLES
        if (enabled, forced) != (expected_private, expected_private):
            _fail("rls_baseline_mismatch")
    names = (*_TABLES, "uq_securities_company_id_id_ticker", *_NEW_CONSTRAINTS, *_NEW_INDEXES)
    occupied = connection.execute(text(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=:schema AND c.relname = ANY(:names)"
    ), {"schema": _SCHEMA, "names": list(names)}).first()
    if occupied is not None:
        _fail("relation_name_collision")
    occupied_constraint = connection.execute(text(
        "SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace "
        "WHERE n.nspname=:schema AND conname = ANY(:names)"
    ), {"schema": _SCHEMA, "names": list((*_NEW_CONSTRAINTS, "uq_securities_company_id_id_ticker"))}).first()
    if occupied_constraint is not None:
        _fail("constraint_name_collision")
    occupied_function = connection.execute(text(
        "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname=:schema AND p.proname = ANY(:names)"
    ), {"schema": _SCHEMA, "names": list(_FUNCTIONS)}).first()
    if occupied_function is not None:
        _fail("function_name_collision")
    occupied_trigger = connection.execute(text(
        "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema "
        "AND NOT t.tgisinternal AND t.tgname = ANY(:names)"
    ), {"schema": _SCHEMA, "names": list(_TRIGGERS)}).first()
    if occupied_trigger is not None:
        _fail("trigger_name_collision")


def _preflight_downgrade(connection: Connection) -> None:
    """在 NOWAIT 锁后拒绝有业务行或外部角色授权的回滚。

    Args:
        connection: 当前 Alembic 事务连接。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: 当前状态不可安全回退。
        DBAPIError: NOWAIT 锁竞争时由 PostgreSQL 传播。
    """

    if not _head_is(connection, revision):
        _fail("head_mismatch")
    if _table_names(connection) != _BASELINE_TABLES | frozenset(_TABLES):
        _fail("current_tables_mismatch")
    for table_name in (*_DROP_TABLES, "securities"):
        connection.exec_driver_sql(f"LOCK TABLE {_SCHEMA}.{table_name} IN ACCESS EXCLUSIVE MODE NOWAIT")
    for table_name in _TABLES:
        if connection.exec_driver_sql(f"SELECT EXISTS (SELECT 1 FROM {_SCHEMA}.{table_name})").scalar_one():
            _fail("business_rows_present")
    external_grants = connection.execute(text(
        "SELECT 1 FROM ("
        "SELECT acl.grantee, acl.grantor, c.relowner AS owner_oid "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) acl "
        "WHERE n.nspname=:schema AND c.relname = ANY(:tables) "
        "UNION ALL "
        "SELECT acl.grantee, acl.grantor, c.relowner AS owner_oid "
        "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(a.attacl) acl "
        "WHERE n.nspname=:schema AND c.relname = ANY(:tables) "
        "AND a.attnum > 0 AND NOT a.attisdropped "
        "UNION ALL "
        "SELECT acl.grantee, acl.grantor, p.proowner AS owner_oid "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl "
        "WHERE n.nspname=:schema AND p.proname = ANY(:functions)"
        ") grants WHERE grants.grantee = 0 "
        "OR (grants.grantee <> grants.owner_oid AND grants.grantee NOT IN "
        "(SELECT oid FROM pg_roles WHERE rolname IN (:app,:audit))) "
        "OR grants.grantor <> grants.owner_oid LIMIT 1"
    ), {
        "schema": _SCHEMA, "tables": list(_TABLES), "functions": list(_FUNCTIONS),
        "app": PLATFORM_APP_ROLE, "audit": PLATFORM_AUDIT_ROLE,
    }).first()
    if external_grants is not None:
        _fail("external_role_dependency")


def upgrade() -> None:
    """从精确 0006 baseline 原子建立六表与权限。

    Args:
        无。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: 0006 admission 不通过。
        DBAPIError: DDL 失败并由 Alembic 事务回滚。
    """

    connection = op.get_bind()
    _preflight_upgrade(connection)
    op.execute("LOCK TABLE dayu_platform.securities IN ACCESS EXCLUSIVE MODE")
    op.execute("ALTER TABLE dayu_platform.securities ADD CONSTRAINT uq_securities_company_id_id_ticker UNIQUE (company_id, id, ticker)")
    op.execute(_DECIMAL_FUNCTION)
    op.execute(_LOCATOR_FUNCTION)
    for ddl in _TABLE_DDL:
        op.execute(ddl)
    for ddl in _INDEX_DDL:
        op.execute(ddl)
    op.execute(_DIGEST_FUNCTION)
    op.execute(_APPEND_GUARD_FUNCTION)
    op.execute("CREATE TRIGGER evidence_links_digest_insert_trigger BEFORE INSERT ON dayu_platform.evidence_links FOR EACH ROW EXECUTE FUNCTION dayu_platform.evidence_link_digest_insert()")
    for table_name in ("facts", "claim_versions", "evidence_links"):
        op.execute(f"CREATE TRIGGER {table_name}_append_only_trigger BEFORE UPDATE OR DELETE ON {_SCHEMA}.{table_name} FOR EACH ROW EXECUTE FUNCTION dayu_platform.guard_evidence_append_only()")
    for table_name in _TABLES:
        op.execute(f"REVOKE ALL ON TABLE {_SCHEMA}.{table_name} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON TABLE {_SCHEMA}.{table_name} TO {PLATFORM_APP_ROLE}")
        op.execute(f"GRANT SELECT ON TABLE {_SCHEMA}.{table_name} TO {PLATFORM_AUDIT_ROLE}")
        op.execute(f"ALTER TABLE {_SCHEMA}.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {_SCHEMA}.{table_name} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {_SCHEMA}.{table_name} FOR ALL TO {PLATFORM_APP_ROLE} USING (nullif(current_setting('app.tenant_id', true), '')::uuid = tenant_id) WITH CHECK (nullif(current_setting('app.tenant_id', true), '')::uuid = tenant_id)")
    op.execute(f"GRANT UPDATE (version, updated_at) ON TABLE {_SCHEMA}.claims TO {PLATFORM_APP_ROLE}")
    op.execute(f"GRANT UPDATE (status, version, updated_at, resolution_operation_id, resolution_operation_fingerprint, resolution_new_version_id, resolution_new_link_id, resolution_reviewer_user_id, resolution_reviewer_token_id, resolution_user_role_id, resolution_role_permission_id, resolution_permission_id, resolution_permission_key, resolution_checked_at, resolution_policy, resolution_reason, resolved_at) ON TABLE {_SCHEMA}.claim_conflicts TO {PLATFORM_APP_ROLE}")
    op.execute(f"GRANT UPDATE (state, version, updated_at, rejection_code) ON TABLE {_SCHEMA}.research_candidates TO {PLATFORM_APP_ROLE}")
    for function_name, arguments in (("evidence_decimal_valid", "numeric"), ("evidence_locator_valid", "jsonb"), ("evidence_link_digest_insert", ""), ("guard_evidence_append_only", "")):
        op.execute(f"REVOKE ALL ON FUNCTION {_SCHEMA}.{function_name}({arguments}) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_SCHEMA}.evidence_decimal_valid(numeric), {_SCHEMA}.evidence_locator_valid(jsonb) TO {PLATFORM_APP_ROLE}")


def downgrade() -> None:
    """仅在空六表且无外部依赖时原子撤销 0007。

    Args:
        无。

    Returns:
        无。

    Raises:
        PlatformMigrationAdmissionError: 六表含业务行或对象不匹配。
        DBAPIError: 锁竞争或外部依赖阻止无 CASCADE 回退。
    """

    connection = op.get_bind()
    _preflight_downgrade(connection)
    for table_name in _DROP_TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {_SCHEMA}.{table_name}")
    op.execute("DROP TRIGGER evidence_links_digest_insert_trigger ON dayu_platform.evidence_links")
    for table_name in ("evidence_links", "claim_versions", "facts"):
        op.execute(f"DROP TRIGGER {table_name}_append_only_trigger ON {_SCHEMA}.{table_name}")
    for table_name in _DROP_TABLES:
        op.execute(f"DROP TABLE {_SCHEMA}.{table_name} RESTRICT")
    op.execute("DROP FUNCTION dayu_platform.evidence_link_digest_insert() RESTRICT")
    op.execute("DROP FUNCTION dayu_platform.guard_evidence_append_only() RESTRICT")
    op.execute("DROP FUNCTION dayu_platform.evidence_locator_valid(jsonb) RESTRICT")
    op.execute("DROP FUNCTION dayu_platform.evidence_decimal_valid(numeric) RESTRICT")
    op.execute("ALTER TABLE dayu_platform.securities DROP CONSTRAINT uq_securities_company_id_id_ticker RESTRICT")
