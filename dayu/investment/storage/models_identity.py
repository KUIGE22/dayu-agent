"""投资平台身份、租户与数据源域 ORM 模型。

本模块定义 ``dayu_platform`` schema 中 8 张 identity/tenant/source 域表：

- ``organizations``：tenant root，以 ``id`` 自身作 RLS tenant；
- ``companies`` / ``securities``：公共 reference，不启用 RLS；
- ``users``：租户内用户，subject/email 唯一；
- ``source_definitions``：公共 reference 数据源定义；
- ``source_subscriptions``：租户对数据源的订阅；
- ``source_sync_runs`` / ``source_health_snapshots``：append-only
  同步运行与健康快照。

设计约束（与 ``dayu/investment/storage/migrations`` 真源保持一致）：

- UUID 全部由调用方提供，无 server random default；
- ``created_at/updated_at`` 为 ``TIMESTAMPTZ NOT NULL DEFAULT
  transaction_timestamp()``，``started_at/observed_at`` 由调用方提供，
  ``finished_at`` 可空；
- 文本业务键必须非空且无首尾空白，``version`` 为
  ``INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)``；
- mutable 表带 ``updated_at/version``，append-only 表不带；
- 私有表（除公共 reference 外全部）由 migration 启用 ``FORCE ROW
  LEVEL SECURITY``，本模块不声明 RLS（policy 属于迁移 DDL）。

CheckConstraint 只声明语义短名（如 ``status``），最终约束名由
naming convention 生成 ``ck_<table>_<short>``，与迁移 DDL 完全一致；
显式短名必须保持表内唯一，且最终名不超过 PostgreSQL 63 字符限制。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
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
"""递归 JSON 值类型：config_json 等 JSONB 列的 Python 侧类型。"""


class Organization(PlatformBase):
    """组织（tenant root）模型。

    以 ``id`` 自身作为 RLS tenant 比较列；``slug`` 为唯一业务键，
    迁移以幂等固定值创建 ``default`` 组织。
    """

    __tablename__ = "organizations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
        CheckConstraint("slug <> '' AND slug = btrim(slug)", name="slug_nonblank"),
        CheckConstraint("version > 0", name="version_positive"),
    )


class Company(PlatformBase):
    """被研究公司公共 reference 模型。

    公共 reference 不启用 RLS；``lei`` 为可空唯一外部标识。
    """

    __tablename__ = "companies"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    lei: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("lei", name="uq_companies_lei"),
        CheckConstraint(
            "country_code IS NULL OR (upper(country_code) = country_code AND length(country_code) = 2)",
            name="country_code_upper_2",
        ),
        CheckConstraint("lei IS NULL OR (lei <> '' AND lei = btrim(lei))", name="lei_nonblank"),
        CheckConstraint("version > 0", name="version_positive"),
    )


class Security(PlatformBase):
    """证券公共 reference 模型。

    以 ``(exchange_mic, ticker)`` 唯一；``company_id`` 引用公共
    ``companies``（RESTRICT）；``isin`` 为可空唯一外部标识。
    """

    __tablename__ = "securities"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    company_id: Mapped[Uuid] = mapped_column(
        ForeignKey("companies.id", name="fk_securities_company_id_companies", ondelete="RESTRICT"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_mic: Mapped[str] = mapped_column(String(4), nullable=False)
    security_type: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    isin: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("exchange_mic", "ticker", name="uq_securities_exchange_mic_ticker"),
        UniqueConstraint("isin", name="uq_securities_isin"),
        Index("ix_securities_company_id", "company_id"),
        CheckConstraint(
            "exchange_mic = upper(exchange_mic) AND length(exchange_mic) = 4",
            name="exchange_mic_upper_4",
        ),
        CheckConstraint(
            "security_type IN ('equity', 'adr', 'etf', 'fund', 'bond', 'other')",
            name="security_type",
        ),
        CheckConstraint("currency = upper(currency)", name="currency_upper"),
        CheckConstraint("ticker <> '' AND ticker = btrim(ticker)", name="ticker_nonblank"),
        CheckConstraint("isin IS NULL OR (isin <> '' AND isin = btrim(isin))", name="isin_nonblank"),
        CheckConstraint("version > 0", name="version_positive"),
    )


class User(PlatformBase):
    """租户内用户模型。

    ``subject`` 为租户内唯一登录标识；``email`` 非空时按小写唯一；
    ``tenant_id`` 引用 ``organizations``（RESTRICT）。
    """

    __tablename__ = "users"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey("organizations.id", name="fk_users_tenant_id_organizations", ondelete="RESTRICT"),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
        UniqueConstraint("tenant_id", "subject", name="uq_users_tenant_id_subject"),
        Index(
            "uq_users_tenant_email_lower",
            "tenant_id",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        CheckConstraint(
            "status IN ('active', 'disabled', 'locked')",
            name="status",
        ),
        CheckConstraint("subject <> '' AND subject = btrim(subject)", name="subject_nonblank"),
        CheckConstraint(
            "email IS NULL OR (email = btrim(email))",
            name="email_nonblank",
        ),
        CheckConstraint("version > 0", name="version_positive"),
    )


class SourceDefinition(PlatformBase):
    """数据源公共 reference 定义模型。

    ``source_key`` 全局唯一；公共 reference 不启用 RLS。
    """

    __tablename__ = "source_definitions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled_by_default: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("source_key", name="uq_source_definitions_source_key"),
        CheckConstraint(
            "source_kind IN ('filing', 'announcement', 'industry_metric', "
            "'research_material', 'market_price', 'fx')",
            name="source_kind",
        ),
        CheckConstraint(
            "source_key <> '' AND source_key = btrim(source_key)",
            name="source_key_nonblank",
        ),
        CheckConstraint("version > 0", name="version_positive"),
    )


class SourceSubscription(PlatformBase):
    """租户数据源订阅模型。

    ``company_id`` 与 ``security_id`` 至多一个非空
    （``num_nonnulls(...) <= 1``）；三条 partial unique index 分别约束
    tenant-wide / company / security 三种订阅目标互斥唯一。
    """

    __tablename__ = "source_subscriptions"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey("organizations.id", name="fk_source_subscriptions_tenant_id_organizations", ondelete="RESTRICT"),
        nullable=False,
    )
    source_definition_id: Mapped[Uuid] = mapped_column(
        ForeignKey(
            "source_definitions.id",
            name="fk_source_subscriptions_source_definition_id_source_definitions",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    company_id: Mapped[Uuid | None] = mapped_column(
        ForeignKey("companies.id", name="fk_source_subscriptions_company_id_companies", ondelete="RESTRICT"),
        nullable=True,
    )
    security_id: Mapped[Uuid | None] = mapped_column(
        ForeignKey("securities.id", name="fk_source_subscriptions_security_id_securities", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_source_subscriptions_tenant_id_id"),
        Index(
            "uq_source_subscriptions_tenant_wide",
            "tenant_id",
            unique=True,
            postgresql_where=text("company_id IS NULL AND security_id IS NULL"),
        ),
        Index(
            "uq_source_subscriptions_company",
            "tenant_id",
            "company_id",
            unique=True,
            postgresql_where=text("company_id IS NOT NULL"),
        ),
        Index(
            "uq_source_subscriptions_security",
            "tenant_id",
            "security_id",
            unique=True,
            postgresql_where=text("security_id IS NOT NULL"),
        ),
        CheckConstraint(
            "status IN ('enabled', 'disabled')",
            name="status",
        ),
        CheckConstraint(
            "num_nonnulls(company_id, security_id) <= 1",
            name="target_exclusive",
        ),
        CheckConstraint(
            "jsonb_typeof(config_json) = 'object'",
            name="config_json_object",
        ),
        CheckConstraint("version > 0", name="version_positive"),
    )


class SourceSyncRun(PlatformBase):
    """数据源同步运行 append-only 模型。

    ``idempotency_key`` 在租户内唯一；``started_at`` 由调用方提供，
    ``finished_at`` 可空且不得早于 ``started_at``；无
    ``updated_at/version``。
    """

    __tablename__ = "source_sync_runs"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey("organizations.id", name="fk_source_sync_runs_tenant_id_organizations", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_discovered: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    records_ingested: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    safe_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_source_sync_runs_tenant_id_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_source_sync_runs_tenant_id_idempotency_key"),
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"],
            ["source_subscriptions.tenant_id", "source_subscriptions.id"],
            name="fk_source_sync_runs_tenant_subscription_source_subscriptions",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_source_sync_runs_tenant_subscription_started",
            "tenant_id",
            "subscription_id",
            text("started_at DESC"),
        ),
        CheckConstraint(
            "status IN ('planned', 'running', 'succeeded', 'failed', 'cancelled')",
            name="status",
        ),
        CheckConstraint("records_discovered >= 0", name="records_discovered_nonnegative"),
        CheckConstraint("records_ingested >= 0", name="records_ingested_nonnegative"),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="finished_at_after_started_at",
        ),
        CheckConstraint(
            "idempotency_key <> '' AND idempotency_key = btrim(idempotency_key)",
            name="idempotency_key_nonblank",
        ),
    )


class SourceHealthSnapshot(PlatformBase):
    """数据源健康快照 append-only 模型。

    ``observed_at`` 由调用方提供；``sync_run_id`` 可空并引用同租户
    ``source_sync_runs``；无 ``updated_at/version``。
    """

    __tablename__ = "source_health_snapshots"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(
        ForeignKey(
            "organizations.id",
            name="fk_source_health_snapshots_tenant_id_organizations",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    subscription_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    sync_run_id: Mapped[Uuid | None] = mapped_column(Uuid, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    safe_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_source_health_snapshots_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"],
            ["source_subscriptions.tenant_id", "source_subscriptions.id"],
            name="fk_source_health_snapshots_tenant_subscription",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sync_run_id"],
            ["source_sync_runs.tenant_id", "source_sync_runs.id"],
            name="fk_source_health_snapshots_tenant_sync_run",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_source_health_snapshots_tenant_subscription_observed",
            "tenant_id",
            "subscription_id",
            text("observed_at DESC"),
        ),
        CheckConstraint(
            "status IN ('healthy', 'degraded', 'failing', 'disabled')",
            name="status",
        ),
        CheckConstraint(
            "consecutive_failures >= 0",
            name="consecutive_failures_nonnegative",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_nonnegative"),
    )


__all__ = [
    "Company",
    "JsonValue",
    "Organization",
    "Security",
    "SourceDefinition",
    "SourceHealthSnapshot",
    "SourceSubscription",
    "SourceSyncRun",
    "User",
]
