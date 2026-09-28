"""投资平台身份、租户与数据源域 ORM 模型。

本模块定义 ``dayu_platform`` schema 中 11 张 identity/tenant/source 域表：

- ``organizations``：tenant root，以 ``id`` 自身作 RLS tenant；
- ``companies`` / ``securities``：公共 reference，不启用 RLS；
- ``users``：租户内用户，subject/email 唯一；
- ``source_definitions``：公共 reference 数据源定义；
- ``source_subscriptions``：租户对数据源的订阅；
- ``source_sync_runs`` / ``source_health_snapshots``：append-only
  同步运行与健康快照；
- ``source_sync_operations``：同步操作 owner/generation fence；
- ``source_health_states``：每订阅唯一 mutable health head；
- ``source_health_alert_outbox``：append-only semantic alert outbox。

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

from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dayu.investment.storage.db import PLATFORM_SCHEMA_NAME, PlatformBase

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
"""递归 JSON 值类型：config_json 等 JSONB 列的 Python 侧类型。"""

_RAW_REFERENCE_METADATA = MetaData(schema=PLATFORM_SCHEMA_NAME)
"""仅供 ORM 复合 FK 编译的 raw-table metadata，不进入平台 metadata。"""

_RAW_JOB_ATTEMPTS = Table(
    "job_attempts",
    _RAW_REFERENCE_METADATA,
    Column("tenant_id", Uuid, nullable=False),
    Column("job_run_id", Uuid, nullable=False),
    Column("id", Uuid, nullable=False),
)
"""0003 raw SQL ``job_attempts`` 的最小只读引用形状。"""


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

    以 ``(exchange_mic, ticker)`` 唯一，另给 Fact/direct evidence 提供
    ``(company_id, id, ticker)`` 复合引用键；``company_id`` 引用公共
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
        UniqueConstraint("company_id", "id", "ticker", name="uq_securities_company_id_id_ticker"),
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
            "source_definition_id",
            unique=True,
            postgresql_where=text("company_id IS NULL AND security_id IS NULL"),
        ),
        Index(
            "uq_source_subscriptions_company",
            "tenant_id",
            "source_definition_id",
            "company_id",
            unique=True,
            postgresql_where=text("company_id IS NOT NULL"),
        ),
        Index(
            "uq_source_subscriptions_security",
            "tenant_id",
            "source_definition_id",
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
    job_run_id: Mapped[Uuid | None] = mapped_column(Uuid, nullable=True)
    job_attempt_id: Mapped[Uuid | None] = mapped_column(Uuid, nullable=True)
    payload_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_recommended: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    records_downloaded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_reused: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_ignored: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_source_observed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    receipt_json: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB, nullable=True)
    receipt_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB, nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_source_sync_runs_tenant_id_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_source_sync_runs_tenant_id_idempotency_key"),
        UniqueConstraint(
            "tenant_id",
            "subscription_id",
            "id",
            name="uq_source_sync_runs_tenant_subscription_id_v2",
        ),
        UniqueConstraint(
            "tenant_id",
            "subscription_id",
            "job_run_id",
            "id",
            name="uq_source_sync_runs_tenant_subscription_job_id_v2",
        ),
        UniqueConstraint(
            "tenant_id",
            "subscription_id",
            "job_run_id",
            "job_attempt_id",
            "id",
            name="uq_source_sync_runs_tenant_sub_job_attempt_id_v2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"],
            ["source_subscriptions.tenant_id", "source_subscriptions.id"],
            name="fk_source_sync_runs_tenant_subscription_source_subscriptions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "job_run_id", "job_attempt_id"],
            [
                _RAW_JOB_ATTEMPTS.c.tenant_id,
                _RAW_JOB_ATTEMPTS.c.job_run_id,
                _RAW_JOB_ATTEMPTS.c.id,
            ],
            name="fk_source_sync_runs_tenant_job_attempt_v2",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_source_sync_runs_tenant_subscription_started",
            "tenant_id",
            "subscription_id",
            text("started_at DESC"),
        ),
        Index(
            "uq_source_sync_runs_tenant_job_run_v2",
            "tenant_id",
            "job_run_id",
            unique=True,
            postgresql_where=text("job_run_id IS NOT NULL"),
        ),
        Index(
            "uq_source_sync_runs_tenant_job_attempt_v2",
            "tenant_id",
            "job_attempt_id",
            unique=True,
            postgresql_where=text("job_attempt_id IS NOT NULL"),
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
        CheckConstraint(
            "((job_run_id IS NULL AND job_attempt_id IS NULL AND payload_sha256 IS NULL "
            "AND outcome IS NULL AND retry_recommended IS NULL "
            "AND records_downloaded IS NULL AND records_reused IS NULL "
            "AND records_ignored IS NULL AND records_failed IS NULL "
            "AND receipt_json IS NULL AND receipt_sha256 IS NULL "
            "AND result_json IS NULL AND result_sha256 IS NULL) OR "
            "(job_run_id IS NOT NULL AND job_attempt_id IS NOT NULL "
            "AND payload_sha256 IS NOT NULL AND outcome IS NOT NULL "
            "AND retry_recommended IS NOT NULL AND records_downloaded IS NOT NULL "
            "AND records_reused IS NOT NULL AND records_ignored IS NOT NULL "
            "AND records_failed IS NOT NULL AND receipt_json IS NOT NULL "
            "AND receipt_sha256 IS NOT NULL AND result_json IS NOT NULL "
            "AND result_sha256 IS NOT NULL))",
            name="v1_core_presence",
        ),
        CheckConstraint(
            "job_run_id IS NULL OR (records_downloaded >= 0 AND records_reused >= 0 "
            "AND records_ignored >= 0 AND records_failed >= 0 "
            "AND records_discovered = records_downloaded + records_reused "
            "+ records_ignored + records_failed "
            "AND records_ingested = records_downloaded + records_reused "
            "AND ((records_ingested > 0) = (latest_source_observed_date IS NOT NULL)))",
            name="v1_counts",
        ),
        CheckConstraint(
            "job_run_id IS NULL OR (status IN ('succeeded', 'failed') "
            "AND finished_at IS NOT NULL "
            "AND jsonb_typeof(receipt_json) = 'object' "
            "AND jsonb_typeof(result_json) = 'object' "
            "AND payload_sha256 ~ '^[0-9a-f]{64}$' "
            "AND receipt_sha256 ~ '^[0-9a-f]{64}$' "
            "AND result_sha256 ~ '^[0-9a-f]{64}$' "
            "AND ((outcome = 'succeeded' AND status = 'succeeded' "
            "AND safe_error_code IS NULL AND retry_recommended = false "
            "AND records_ingested > 0 AND records_failed = 0) "
            "OR (outcome = 'no_change' AND status = 'succeeded' "
            "AND safe_error_code IS NULL AND retry_recommended = false "
            "AND records_ingested = 0 AND records_failed = 0) "
            "OR (outcome = 'partial' AND status = 'succeeded' "
            "AND safe_error_code = 'partial_batch' AND retry_recommended = true "
            "AND records_ingested > 0 AND records_failed > 0) "
            "OR (outcome = 'skipped_disabled' AND status = 'succeeded' "
            "AND safe_error_code IS NULL AND retry_recommended = false "
            "AND records_downloaded = 0 AND records_reused = 0 "
            "AND records_ignored = 0 AND records_failed = 0) "
            "OR (outcome = 'stale_subscription' AND status = 'failed' "
            "AND safe_error_code = 'stale_subscription' "
            "AND retry_recommended = false AND records_downloaded = 0 "
            "AND records_reused = 0 AND records_ignored = 0 AND records_failed = 0) "
            "OR (outcome = 'failed' AND status = 'failed' "
            "AND safe_error_code IS NOT NULL "
            "AND safe_error_code IN ('unsupported_market', 'unsupported_form', "
            "'stale_data', 'provider_rate_limited', 'provider_unavailable', "
            "'fins_invariant') "
            "AND retry_recommended = (safe_error_code IN "
            "('provider_rate_limited', 'provider_unavailable')) "
            "AND ((safe_error_code = 'stale_data' AND records_ingested > 0) "
            "OR (safe_error_code = 'provider_unavailable' "
            "AND records_downloaded = 0 AND records_reused = 0) "
            "OR (safe_error_code IN ('unsupported_market', 'unsupported_form', "
            "'provider_rate_limited', 'fins_invariant') "
            "AND records_downloaded = 0 AND records_reused = 0 "
            "AND records_ignored = 0 AND records_failed = 0))))))",
            name="v1_outcome_shape",
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
    health_state_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_source_health_snapshots_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "subscription_id",
            "id",
            name="uq_source_health_snapshots_tenant_subscription_id_v2",
        ),
        UniqueConstraint(
            "tenant_id",
            "subscription_id",
            "sync_run_id",
            "health_state_version",
            "id",
            name="uq_source_health_snapshots_tenant_sub_run_version_id_v2",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"],
            ["source_subscriptions.tenant_id", "source_subscriptions.id"],
            name="fk_source_health_snapshots_tenant_subscription",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id", "sync_run_id"],
            [
                "source_sync_runs.tenant_id",
                "source_sync_runs.subscription_id",
                "source_sync_runs.id",
            ],
            name="fk_source_health_snapshots_tenant_subscription_run_v2",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_source_health_snapshots_tenant_subscription_observed",
            "tenant_id",
            "subscription_id",
            text("observed_at DESC"),
        ),
        Index(
            "uq_source_health_snapshots_tenant_subscription_version_v2",
            "tenant_id",
            "subscription_id",
            "health_state_version",
            unique=True,
            postgresql_where=text("health_state_version IS NOT NULL"),
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
        CheckConstraint(
            "((status = 'healthy' AND consecutive_failures = 0 "
            "AND safe_error_code IS NULL) OR "
            "(status IN ('degraded', 'failing', 'disabled') "
            "AND consecutive_failures > 0 AND safe_error_code IS NOT NULL "
            "AND safe_error_code IN ('partial_batch', 'unsupported_market', "
            "'unsupported_form', 'stale_data', 'provider_rate_limited', "
            "'provider_unavailable', 'fins_invariant'))) "
            "AND (health_state_version IS NULL OR "
            "(health_state_version > 0 AND "
            "((sync_run_id IS NOT NULL AND latency_ms IS NOT NULL AND latency_ms >= 0) "
            "OR (sync_run_id IS NULL AND latency_ms IS NULL AND status = 'healthy' "
            "AND consecutive_failures = 0 AND safe_error_code IS NULL))))",
            name="v2_shape",
        ),
    )


class SourceSyncOperation(PlatformBase):
    """数据源同步 operation owner/generation fence 模型。"""

    __tablename__ = "source_sync_operations"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    job_run_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    subscription_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    owner_attempt_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_binding_disposition: Mapped[str] = mapped_column(Text, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    execution_snapshot_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    execution_snapshot_json: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    terminal_source_sync_run_id: Mapped[Uuid | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_source_sync_operations_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "job_run_id",
            name="uq_source_sync_operations_tenant_job_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_source_sync_operations_tenant_id_organizations",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "job_run_id", "owner_attempt_id"],
            [
                _RAW_JOB_ATTEMPTS.c.tenant_id,
                _RAW_JOB_ATTEMPTS.c.job_run_id,
                _RAW_JOB_ATTEMPTS.c.id,
            ],
            name="fk_source_sync_operations_tenant_job_attempt",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"],
            ["source_subscriptions.tenant_id", "source_subscriptions.id"],
            name="fk_source_sync_operations_tenant_subscription",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "subscription_id",
                "job_run_id",
                "owner_attempt_id",
                "terminal_source_sync_run_id",
            ],
            [
                "source_sync_runs.tenant_id",
                "source_sync_runs.subscription_id",
                "source_sync_runs.job_run_id",
                "source_sync_runs.job_attempt_id",
                "source_sync_runs.id",
            ],
            name="fk_source_sync_operations_terminal_run",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_source_sync_operations_tenant_state_updated",
            "tenant_id",
            "state",
            "updated_at",
            "id",
        ),
        CheckConstraint(
            "generation > 0 AND owner_binding_disposition IN ('ready', 'disabled', 'stale') "
            "AND ((state = 'active' AND terminal_source_sync_run_id IS NULL) "
            "OR (state = 'terminal' AND terminal_source_sync_run_id IS NOT NULL))",
            name="state_shape",
        ),
        CheckConstraint(
            "payload_sha256 ~ '^[0-9a-f]{64}$' "
            "AND execution_snapshot_sha256 ~ '^[0-9a-f]{64}$'",
            name="hashes",
        ),
        CheckConstraint(
            "jsonb_typeof(execution_snapshot_json) = 'object'",
            name="snapshot_object",
        ),
    )


class SourceHealthState(PlatformBase):
    """每订阅唯一 mutable source health head 模型。"""

    __tablename__ = "source_health_states"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    subscription_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    last_source_sync_run_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False)
    safe_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("transaction_timestamp()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_source_health_states_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "subscription_id",
            name="uq_source_health_states_tenant_subscription",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_source_health_states_tenant_id_organizations",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id", "last_source_sync_run_id"],
            [
                "source_sync_runs.tenant_id",
                "source_sync_runs.subscription_id",
                "source_sync_runs.id",
            ],
            name="fk_source_health_states_last_run",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_source_health_states_tenant_status_observed",
            "tenant_id",
            "status",
            "observed_at",
            "id",
        ),
        CheckConstraint(
            "version > 0 AND consecutive_failures >= 0 AND "
            "((status = 'healthy' AND consecutive_failures = 0 "
            "AND safe_error_code IS NULL) OR "
            "(status IN ('degraded', 'failing', 'disabled') "
            "AND consecutive_failures > 0 AND safe_error_code IS NOT NULL "
            "AND safe_error_code IN ('partial_batch', 'unsupported_market', "
            "'unsupported_form', 'stale_data', 'provider_rate_limited', "
            "'provider_unavailable', 'fins_invariant')))",
            name="shape",
        ),
    )


class SourceHealthAlertOutbox(PlatformBase):
    """append-only source health semantic alert outbox 模型。"""

    __tablename__ = "source_health_alert_outbox"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    subscription_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    source_sync_run_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    health_snapshot_id: Mapped[Uuid] = mapped_column(Uuid, nullable=False)
    health_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_status: Mapped[str] = mapped_column(Text, nullable=False)
    safe_error_code: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
    event_json: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False)
    event_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_source_health_alert_outbox_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "dedupe_key",
            name="uq_source_health_alert_outbox_tenant_dedupe",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_source_health_alert_outbox_tenant_id_organizations",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id", "source_sync_run_id"],
            [
                "source_sync_runs.tenant_id",
                "source_sync_runs.subscription_id",
                "source_sync_runs.id",
            ],
            name="fk_source_health_alert_outbox_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "subscription_id",
                "source_sync_run_id",
                "health_state_version",
                "health_snapshot_id",
            ],
            [
                "source_health_snapshots.tenant_id",
                "source_health_snapshots.subscription_id",
                "source_health_snapshots.sync_run_id",
                "source_health_snapshots.health_state_version",
                "source_health_snapshots.id",
            ],
            name="fk_source_health_alert_outbox_snapshot",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_source_health_alert_outbox_tenant_created",
            "tenant_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_source_health_alert_outbox_tenant_sub_created",
            "tenant_id",
            "subscription_id",
            "created_at",
            "id",
        ),
        CheckConstraint(
            "health_state_version > 0 "
            "AND alert_kind IN ('degraded', 'failing', 'disabled') "
            "AND alert_kind = target_status AND safe_error_code IS NOT NULL "
            "AND safe_error_code IN ('partial_batch', 'unsupported_market', "
            "'unsupported_form', 'stale_data', 'provider_rate_limited', "
            "'provider_unavailable', 'fins_invariant') "
            "AND dedupe_key ~ '^[0-9a-f]{64}$' "
            "AND event_sha256 ~ '^[0-9a-f]{64}$' "
            "AND jsonb_typeof(event_json) = 'object'",
            name="shape",
        ),
    )


__all__ = [
    "Company",
    "JsonValue",
    "Organization",
    "Security",
    "SourceDefinition",
    "SourceHealthAlertOutbox",
    "SourceHealthSnapshot",
    "SourceHealthState",
    "SourceSubscription",
    "SourceSyncOperation",
    "SourceSyncRun",
    "User",
]
