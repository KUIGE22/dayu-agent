"""Slice 3.1 证据闭合的六张 PostgreSQL ORM 表。

表结构与 0007 迁移保持同名约束。所有私有表由迁移启用 FORCE RLS；
本模块只声明 metadata，不创建表，也不把结构性 Fins locator 当作实时验证。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dayu.investment.storage.db import PlatformBase

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


_HEX64 = "'^[0-9a-f]{64}$'"
_LOCATOR_TICKER = (
    "((jsonb_typeof(locator_json->'ticker') = 'string') AND "
    "(locator_ticker = locator_json->>'ticker')) IS TRUE"
)
_LINK_TARGET = (
    "((fact_id IS NOT NULL AND security_id IS NULL AND locator_ticker IS NULL "
    "AND locator_json IS NULL AND locator_index_digest IS NULL) OR "
    "(fact_id IS NULL AND security_id IS NOT NULL AND locator_ticker IS NOT NULL "
    "AND locator_json IS NOT NULL AND locator_index_digest IS NOT NULL "
    "AND octet_length(locator_index_digest) = 32 "
    "AND jsonb_typeof(locator_json->'ticker') = 'string' "
    "AND locator_ticker = locator_json->>'ticker')) IS TRUE"
)


class FactRow(PlatformBase):
    """不可变 Fact revision；经济时点由 caller 显式给出。"""

    __tablename__ = "facts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    locator_ticker: Mapped[str] = mapped_column(Text, nullable=False)
    locator_json: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    fact_series_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    prior_fact_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    fact_key: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    value_kind: Mapped[str] = mapped_column(Text, nullable=False)
    value_decimal: Mapped[Decimal | None] = mapped_column(Numeric(asdecimal=True), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    unit_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(CHAR(3), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    verification_status: Mapped[str] = mapped_column(Text, nullable=False)
    verifier_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    operation_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_facts_tenant_company_id"),
        UniqueConstraint("tenant_id", "company_id", "fact_series_id", "revision_no", name="uq_facts_series_revision"),
        UniqueConstraint("tenant_id", "operation_id", name="uq_facts_tenant_operation"),
        ForeignKeyConstraint(["company_id", "security_id", "locator_ticker"], ["securities.company_id", "securities.id", "securities.ticker"], name="fk_facts_security_ticker", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "company_id", "prior_fact_id"], ["facts.tenant_id", "facts.company_id", "facts.id"], name="fk_facts_prior", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "verifier_user_id"], ["users.tenant_id", "users.id"], name="fk_facts_verifier", ondelete="RESTRICT"),
        CheckConstraint("revision_no > 0 AND ((revision_no = 1 AND prior_fact_id IS NULL) OR (revision_no > 1 AND prior_fact_id IS NOT NULL))", name="revision_shape"),
        CheckConstraint("fact_key <> '' AND fact_key = btrim(fact_key)", name="fact_key_nonblank"),
        CheckConstraint("metric <> '' AND metric = btrim(metric)", name="metric_nonblank"),
        CheckConstraint("extractor_version <> '' AND extractor_version = btrim(extractor_version)", name="extractor_nonblank"),
        CheckConstraint("(period_start IS NULL AND period_end IS NULL) OR (period_start IS NOT NULL AND period_end IS NOT NULL AND period_start <= period_end)", name="period_shape"),
        CheckConstraint("published_at <= ingested_at AND ingested_at <= available_at", name="time_order"),
        CheckConstraint("verification_status IN ('unverified','verified','invalidated')", name="verification_status"),
        CheckConstraint("(verification_status = 'unverified' AND verifier_user_id IS NULL AND verified_at IS NULL) OR (verification_status <> 'unverified' AND verifier_user_id IS NOT NULL AND verified_at IS NOT NULL)", name="verification_witness"),
        CheckConstraint("dayu_platform.evidence_locator_valid(locator_json) IS TRUE", name="locator"),
        CheckConstraint(_LOCATOR_TICKER, name="locator_ticker"),
        CheckConstraint("dayu_platform.evidence_decimal_valid(value_decimal) IS TRUE OR value_kind <> 'decimal'", name="decimal_bound"),
        CheckConstraint("((value_kind = 'decimal' AND value_decimal IS NOT NULL AND value_text IS NULL AND value_date IS NULL AND value_boolean IS NULL) OR (value_kind = 'text' AND value_decimal IS NULL AND value_text IS NOT NULL AND value_text <> '' AND value_date IS NULL AND value_boolean IS NULL) OR (value_kind = 'date' AND value_decimal IS NULL AND value_text IS NULL AND value_date IS NOT NULL AND value_boolean IS NULL) OR (value_kind = 'boolean' AND value_decimal IS NULL AND value_text IS NULL AND value_date IS NULL AND value_boolean IS NOT NULL)) IS TRUE", name="value_shape"),
        CheckConstraint("((value_kind = 'decimal' AND unit_code IS NOT NULL AND unit_code <> '' AND unit_code = btrim(unit_code) AND ((unit_code = 'currency' AND currency ~ '^[A-Z]{3}$') OR (unit_code <> 'currency' AND currency IS NULL))) OR (value_kind <> 'decimal' AND unit_code IS NULL AND currency IS NULL)) IS TRUE", name="unit_shape"),
        CheckConstraint(f"operation_fingerprint ~ {_HEX64}", name="operation_fingerprint"),
        Index("ix_facts_scope_series", "tenant_id", "company_id", "fact_series_id", "revision_no"),
    )


class ClaimRow(PlatformBase):
    """Claim lineage 的可变 CAS shell。"""

    __tablename__ = "claims"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_claims_tenant_company_id"),
        CheckConstraint("version > 0", name="version_positive"),
    )


class ClaimVersionRow(PlatformBase):
    """Claim 的不可变版本，记录 copy source 与动作授权见证。"""

    __tablename__ = "claim_versions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    claim_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    transition_kind: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_mode: Mapped[str] = mapped_column(Text, nullable=False)
    copy_source_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    operation_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_band: Mapped[str] = mapped_column(Text, nullable=False)
    probability: Mapped[Decimal | None] = mapped_column(Numeric(asdecimal=True), nullable=True)
    impact_horizon: Mapped[str] = mapped_column(Text, nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    invalidation_rule: Mapped[str] = mapped_column(Text, nullable=False)
    transition_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    author_auth_token_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    author_auth_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    author_auth_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reviewer_token_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reviewer_user_role_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reviewer_role_permission_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reviewer_permission_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reviewer_permission_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_claim_versions_tenant_company_id"),
        UniqueConstraint("tenant_id", "company_id", "claim_id", "id", name="uq_claim_versions_claim_id"),
        UniqueConstraint("tenant_id", "claim_id", "version_no", name="uq_claim_versions_claim_version"),
        UniqueConstraint("tenant_id", "operation_id", name="uq_claim_versions_operation"),
        ForeignKeyConstraint(["tenant_id", "company_id", "claim_id"], ["claims.tenant_id", "claims.company_id", "claims.id"], name="fk_claim_versions_claim", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "company_id", "claim_id", "copy_source_version_id"], ["claim_versions.tenant_id", "claim_versions.company_id", "claim_versions.claim_id", "claim_versions.id"], name="fk_claim_versions_copy_source", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "author_user_id"], ["users.tenant_id", "users.id"], name="fk_claim_versions_author", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "author_auth_token_id"], ["api_tokens.tenant_id", "api_tokens.id"], name="fk_claim_versions_author_token", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "reviewer_user_id"], ["users.tenant_id", "users.id"], name="fk_claim_versions_reviewer", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "reviewer_token_id"], ["api_tokens.tenant_id", "api_tokens.id"], name="fk_claim_versions_reviewer_token", ondelete="RESTRICT"),
        CheckConstraint("version_no > 0", name="version_positive"),
        CheckConstraint("(((version_no = 1 AND transition_kind = 'claim_create' AND evidence_mode = 'replace_all' AND status = 'draft') OR (version_no > 1 AND transition_kind <> 'claim_create')) IS TRUE)", name="first_version"),
        CheckConstraint("((evidence_mode = 'replace_all' AND copy_source_version_id IS NULL) OR (evidence_mode = 'copy_previous' AND copy_source_version_id IS NOT NULL)) IS TRUE", name="evidence_mode"),
        CheckConstraint("statement <> '' AND statement = btrim(statement)", name="statement_nonblank"),
        CheckConstraint("invalidation_rule <> '' AND invalidation_rule = btrim(invalidation_rule)", name="invalidation_rule"),
        CheckConstraint("confidence_band IN ('low','medium','high')", name="confidence_band"),
        CheckConstraint("impact_horizon IN ('short','medium','long')", name="impact_horizon"),
        CheckConstraint("probability IS NULL OR (probability >= 0 AND probability <= 1)", name="probability"),
        CheckConstraint("status IN ('draft','in_review','approved','rejected','invalidated','review_required','superseded')", name="status"),
        CheckConstraint("transition_kind IN ('claim_create','content_revision','submit_review','begin_revision','review_decision','expiry','conflict_resolution')", name="transition_kind"),
        CheckConstraint("transition_reason IS NULL OR (transition_reason <> '' AND transition_reason = btrim(transition_reason))", name="transition_reason"),
        CheckConstraint("((transition_kind = 'begin_revision' AND status = 'draft' AND author_user_id IS NOT NULL AND transition_reason IS NOT NULL AND author_auth_token_id IS NOT NULL AND author_auth_checked_at IS NOT NULL AND author_auth_policy IS NOT NULL AND author_auth_policy <> '' AND reviewer_user_id IS NULL AND reviewer_token_id IS NULL AND reviewer_user_role_id IS NULL AND reviewer_role_permission_id IS NULL AND reviewer_permission_id IS NULL AND reviewer_permission_key IS NULL AND reviewer_checked_at IS NULL AND reviewer_policy IS NULL AND reviewer_reason IS NULL) OR (transition_kind IN ('review_decision','conflict_resolution') AND author_auth_token_id IS NULL AND author_auth_checked_at IS NULL AND author_auth_policy IS NULL AND reviewer_user_id IS NOT NULL AND reviewer_token_id IS NOT NULL AND reviewer_user_role_id IS NOT NULL AND reviewer_role_permission_id IS NOT NULL AND reviewer_permission_id IS NOT NULL AND reviewer_permission_key = 'investment.claim.review' AND reviewer_checked_at IS NOT NULL AND reviewer_policy IS NOT NULL AND reviewer_policy <> '' AND reviewer_reason IS NOT NULL AND reviewer_reason <> '') OR (transition_kind IN ('claim_create','content_revision','submit_review','expiry') AND author_auth_token_id IS NULL AND author_auth_checked_at IS NULL AND author_auth_policy IS NULL AND reviewer_user_id IS NULL AND reviewer_token_id IS NULL AND reviewer_user_role_id IS NULL AND reviewer_role_permission_id IS NULL AND reviewer_permission_id IS NULL AND reviewer_permission_key IS NULL AND reviewer_checked_at IS NULL AND reviewer_policy IS NULL AND reviewer_reason IS NULL AND (transition_kind <> 'expiry' OR (status = 'review_required' AND transition_reason IS NOT NULL)))) IS TRUE", name="action_witness"),
        CheckConstraint(f"operation_fingerprint ~ {_HEX64}", name="operation_fingerprint"),
        Index("ix_claim_versions_current", "tenant_id", "company_id", "claim_id", "version_no"),
    )


class EvidenceLinkRow(PlatformBase):
    """ClaimVersion 的不可变完整证据集合成员。"""

    __tablename__ = "evidence_links"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    claim_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    fact_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    security_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    locator_ticker: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator_json: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB, nullable=True)
    locator_index_digest: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_evidence_links_tenant_company_id"),
        UniqueConstraint("tenant_id", "company_id", "claim_version_id", "id", name="uq_evidence_links_version_id"),
        ForeignKeyConstraint(["tenant_id", "company_id", "claim_version_id"], ["claim_versions.tenant_id", "claim_versions.company_id", "claim_versions.id"], name="fk_evidence_links_version", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "company_id", "fact_id"], ["facts.tenant_id", "facts.company_id", "facts.id"], name="fk_evidence_links_fact", ondelete="RESTRICT"),
        ForeignKeyConstraint(["company_id", "security_id", "locator_ticker"], ["securities.company_id", "securities.id", "securities.ticker"], name="fk_evidence_links_security_ticker", ondelete="RESTRICT"),
        CheckConstraint("relation IN ('supports','contradicts','context')", name="relation"),
        CheckConstraint(_LINK_TARGET, name="target_arm"),
        CheckConstraint("locator_json IS NULL OR dayu_platform.evidence_locator_valid(locator_json) IS TRUE", name="locator"),
        Index("uq_evidence_links_fact_target", "tenant_id", "claim_version_id", "relation", "fact_id", unique=True, postgresql_where=text("fact_id IS NOT NULL")),
        Index("uq_evidence_links_direct_digest", "tenant_id", "claim_version_id", "relation", "security_id", "locator_index_digest", unique=True, postgresql_where=text("fact_id IS NULL")),
    )


class ClaimConflictRow(PlatformBase):
    """两个版本间的有向规范化冲突及其受控解决见证。"""

    __tablename__ = "claim_conflicts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    left_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    right_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    material: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    operation_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    resolution_operation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_operation_fingerprint: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    resolution_new_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_new_link_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_reviewer_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_reviewer_token_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_user_role_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_role_permission_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_permission_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolution_permission_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_claim_conflicts_tenant_company_id"),
        UniqueConstraint("tenant_id", "company_id", "left_version_id", "right_version_id", name="uq_claim_conflicts_pair"),
        UniqueConstraint("tenant_id", "operation_id", name="uq_claim_conflicts_operation"),
        ForeignKeyConstraint(["tenant_id", "company_id", "left_version_id"], ["claim_versions.tenant_id", "claim_versions.company_id", "claim_versions.id"], name="fk_claim_conflicts_left", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "company_id", "right_version_id"], ["claim_versions.tenant_id", "claim_versions.company_id", "claim_versions.id"], name="fk_claim_conflicts_right", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "company_id", "resolution_new_version_id", "resolution_new_link_id"], ["evidence_links.tenant_id", "evidence_links.company_id", "evidence_links.claim_version_id", "evidence_links.id"], name="fk_claim_conflicts_resolution_link", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "resolution_reviewer_user_id"], ["users.tenant_id", "users.id"], name="fk_claim_conflicts_reviewer", ondelete="RESTRICT"),
        ForeignKeyConstraint(["tenant_id", "resolution_reviewer_token_id"], ["api_tokens.tenant_id", "api_tokens.id"], name="fk_claim_conflicts_reviewer_token", ondelete="RESTRICT"),
        CheckConstraint("left_version_id < right_version_id", name="endpoint_order"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("reason <> '' AND reason = btrim(reason)", name="reason_nonblank"),
        CheckConstraint("status IN ('open','resolved')", name="status"),
        CheckConstraint("((status = 'open' AND resolution_operation_id IS NULL AND resolution_operation_fingerprint IS NULL AND resolution_new_version_id IS NULL AND resolution_new_link_id IS NULL AND resolution_reviewer_user_id IS NULL AND resolution_reviewer_token_id IS NULL AND resolution_user_role_id IS NULL AND resolution_role_permission_id IS NULL AND resolution_permission_id IS NULL AND resolution_permission_key IS NULL AND resolution_checked_at IS NULL AND resolution_policy IS NULL AND resolution_reason IS NULL AND resolved_at IS NULL) OR (status = 'resolved' AND resolution_operation_id IS NOT NULL AND resolution_operation_fingerprint IS NOT NULL AND resolution_new_version_id IS NOT NULL AND resolution_new_link_id IS NOT NULL AND resolution_reviewer_user_id IS NOT NULL AND resolution_reviewer_token_id IS NOT NULL AND resolution_user_role_id IS NOT NULL AND resolution_role_permission_id IS NOT NULL AND resolution_permission_id IS NOT NULL AND resolution_permission_key = 'investment.claim.review' AND resolution_checked_at IS NOT NULL AND resolution_policy IS NOT NULL AND resolution_reason IS NOT NULL AND resolution_reason <> '' AND resolved_at IS NOT NULL)) IS TRUE", name="resolution_witness"),
        CheckConstraint(f"operation_fingerprint ~ {_HEX64}", name="operation_fingerprint"),
        CheckConstraint(f"resolution_operation_fingerprint IS NULL OR resolution_operation_fingerprint ~ {_HEX64}", name="resolution_fingerprint"),
        Index("uq_claim_conflicts_resolution_operation", "tenant_id", "resolution_operation_id", unique=True, postgresql_where=text("resolution_operation_id IS NOT NULL")),
    )


class ResearchCandidateRow(PlatformBase):
    """不可变候选 payload 与独立可变 staging 状态。"""

    __tablename__ = "research_candidates"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_payload_json: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    operation_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_research_candidates_tenant_company_id"),
        UniqueConstraint("tenant_id", "operation_id", name="uq_research_candidates_operation"),
        CheckConstraint("origin IN ('agent','human')", name="origin"),
        CheckConstraint("state IN ('proposed','validated','accepted','rejected')", name="state"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("jsonb_typeof(canonical_payload_json) = 'object'", name="payload_object"),
        CheckConstraint(f"sha256 ~ {_HEX64}", name="sha256"),
        CheckConstraint(f"operation_fingerprint ~ {_HEX64}", name="operation_fingerprint"),
        CheckConstraint("(state = 'rejected' AND rejection_code IS NOT NULL AND rejection_code <> '') OR (state <> 'rejected' AND rejection_code IS NULL)", name="rejection_shape"),
    )


__all__ = ["FactRow", "ClaimRow", "ClaimVersionRow", "EvidenceLinkRow", "ClaimConflictRow", "ResearchCandidateRow"]
