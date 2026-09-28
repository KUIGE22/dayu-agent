"""0008 私有 candidate intake receipt 的19列不可变映射。

DDL/RLS/ACL/append-only 真源是迁移；ORM 不创建数据库对象。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from dayu.investment.domain.candidate_intake import CandidateIntakeRejectionCode
from dayu.investment.storage.db import PlatformBase

_HEX64 = "'^[0-9a-f]{64}$'"
_CODES = ",".join(f"'{code.value}'" for code in CandidateIntakeRejectionCode)


class CandidateIntakeReceiptRow(PlatformBase):
    """tenant+operation 的首提交结果，候选后续CAS不修改本表。"""

    __tablename__ = "candidate_intake_receipts"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_ticker: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    raw_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    raw_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator_sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    citation_sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    fins_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("statement_timestamp()"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "candidate_id", name="uq_candidate_intake_receipts_tenant_candidate"),
        ForeignKeyConstraint(["tenant_id", "company_id", "candidate_id"],
                             ["research_candidates.tenant_id", "research_candidates.company_id", "research_candidates.id"],
                             name="fk_candidate_intake_receipts_candidate", ondelete="RESTRICT"),
        ForeignKeyConstraint(["company_id", "security_id", "security_ticker"],
                             ["securities.company_id", "securities.id", "securities.ticker"],
                             name="fk_candidate_intake_receipts_security", ondelete="RESTRICT"),
        CheckConstraint("origin IN ('agent','human')", name="origin"),
        CheckConstraint("schema_version = 'candidate_intake.v1'", name="schema_version"),
        CheckConstraint("extractor_version <> '' AND extractor_version = btrim(extractor_version)", name="extractor_nonblank"),
        CheckConstraint("raw_bytes >= 0", name="raw_bytes"),
        CheckConstraint(f"raw_sha256 ~ {_HEX64}", name="raw_sha256"),
        CheckConstraint(f"request_fingerprint ~ {_HEX64}", name="request_fingerprint"),
        CheckConstraint(f"payload_sha256 ~ {_HEX64}", name="payload_sha256"),
        CheckConstraint(f"locator_sha256 IS NULL OR locator_sha256 ~ {_HEX64}", name="locator_sha256"),
        CheckConstraint(f"citation_sha256 IS NULL OR citation_sha256 ~ {_HEX64}", name="citation_sha256"),
        CheckConstraint(
            "((outcome = 'proposed' AND rejection_code IS NULL AND locator_sha256 IS NOT NULL "
            "AND citation_sha256 IS NOT NULL AND fins_checked_at IS NOT NULL) OR "
            f"(outcome = 'rejected' AND rejection_code IN ({_CODES}) AND locator_sha256 IS NULL "
            "AND citation_sha256 IS NULL AND fins_checked_at IS NULL)) IS TRUE", name="outcome_shape"),
    )
