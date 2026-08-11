"""PostgreSQL workspace import repository 实现（S15-CTRL-09）。

本模块是 ``WorkspaceImportRepositoryProtocol.publish_import`` 的唯一
DB transaction owner：

- 每次调用只建一个 session，``SET LOCAL app.tenant_id`` 后在同一
  transaction 内完成：schema probe -> transaction-scoped advisory
  xact lock -> marker read -> public reference reconcile ->
  source definition reconcile -> marker insert -> locator inserts；
- advisory lock key 为 ``sha256(tenant_id + "\\0" + migration_id)``
  前 8 字节按 signed big-endian 解释的 ``int64``；相同 tenant/migration
  串行，hash 碰撞只会额外串行而不改变 correctness，commit/rollback
  自动释放；绝不使用"缺失 row 的 ``FOR UPDATE``"冒充互斥；
- 已有 marker 的 schema/root/payload/counts 全相同且 intended
  company/security/source/locator rows 仍 exact 时返回
  ``status=no_op``，数据库字节/版本/时间不变；marker 任一字段不同，
  或 marker exact 但 row missing/drift，抛稳定 drift error；
- company/security/source 公共 rows 只允许 insert 或 exact reuse；
  相同业务键映射到不同 ID、相同 ID projection 不一致、
  security-company 关系不一致均 fail closed，绝不
  update/merge/last-writer-wins；
- marker 与 locators 处于同一 transaction，任一
  insert/constraint/connection error rollback 全部
  identity/source/locator/marker；commit exception 不得返回成功；
- repository 返回 pure receipt，不泄漏 ORM row/session/DSN/absolute
  locator。

本模块被精确授权在该 transaction 内直接操作已有
``Company``/``Security``/``SourceDefinition`` ORM models 与两个新
owner models（经 SQLAlchemy ``Session`` 的 text SQL），不调用各自另开
transaction 的 ``IdentityRepositoryProtocol``/``SourceRepositoryProtocol``
方法；该特殊权限只属于 workspace import repository。
"""

from __future__ import annotations

import hashlib
from typing import NoReturn
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, sessionmaker

from dayu.investment.domain.identifiers import TenantId, TenantScope
from dayu.investment.domain.workspace_import import (
    LegacySecurityMapping,
    VerifiedLegacyCompany,
    VerifiedLegacySourceDefinition,
    VerifiedResearchBundleLocator,
    WorkspaceImportDriftError,
    WorkspaceImportError,
    WorkspaceImportReceipt,
    WorkspaceImportRepositoryFailureError,
    WorkspaceImportRequest,
    WorkspaceImportSchemaUnavailableError,
    WorkspaceImportUsageError,
    derive_workspace_import_marker_id,
)
from dayu.investment.storage.db import (
    PLATFORM_SCHEMA_NAME,
    TENANT_CONTEXT_SETTING,
)

_MARKER_COLS = (
    "id, tenant_id, migration_id, source_schema_version, source_root_fingerprint, "
    "staged_payload_sha256, company_count, security_count, source_definition_count, bundle_count"
)
_COMPANY_COLS = "legal_name, lei, country_code"
_SECURITY_COLS = "company_id, ticker, exchange_mic, security_type, currency, isin, is_active"
_SOURCE_DEFINITION_COLS = "source_key, source_kind, display_name, enabled_by_default"
_LOCATOR_COLS = (
    "id, tenant_id, import_marker_id, security_id, template_name, repository_key, "
    "relative_locator, bundle_sha256, artifact_manifest_sha256"
)


def _canonical_uuid(value: str, label: str) -> str:
    """校验并返回 canonical UUID 字符串。

    Args:
        value: 待校验的 UUID 字符串。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的小写连字符 UUID 字符串。

    Raises:
        WorkspaceImportUsageError: 值不是规范 UUID 时抛出。
    """

    if not isinstance(value, str):
        raise WorkspaceImportUsageError()
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise WorkspaceImportUsageError() from None
    if parsed.int == 0 or str(parsed) != value:
        raise WorkspaceImportUsageError()
    return value


def _validate_scope(scope: TenantScope) -> TenantId:
    """校验租户范围并返回租户标识。

    Args:
        scope: 待校验的租户范围。

    Returns:
        租户标识。

    Raises:
        WorkspaceImportUsageError: scope 非法时抛出。
    """

    if not isinstance(scope, TenantScope):
        raise WorkspaceImportUsageError()
    _canonical_uuid(scope.tenant_id.value, "租户标识")
    return scope.tenant_id


def _set_tenant_local(session: Session, tenant_id: TenantId) -> None:
    """以 bind parameter 设置租户上下文并读回确认。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。

    Returns:
        无。

    Raises:
        WorkspaceImportRepositoryFailureError: 读回确认不一致时抛出。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    result = session.execute(
        text(f"SELECT set_config('{TENANT_CONTEXT_SETTING}', :tenant_id, true)"),
        {"tenant_id": tenant_value},
    )
    if result.scalar() != tenant_value:
        raise WorkspaceImportRepositoryFailureError()


def _advisory_key(tenant_id: TenantId, migration_id: str) -> int:
    """计算 transaction-scoped advisory lock key。

    key = ``sha256(tenant_id + "\\0" + migration_id)`` 前 8 字节按
    signed big-endian 解释的 ``int64``。

    Args:
        tenant_id: 租户标识。
        migration_id: migration id。

    Returns:
        唯一 ``int64`` advisory key。

    Raises:
        无。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    digest = hashlib.sha256(f"{tenant_value}\0{migration_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _row_text(row: Row, index: int) -> str:
    """从查询行取字符串字段（接受 UUID 并转 canonical 字符串）。

    Args:
        row: SQLAlchemy 查询行。
        index: 列索引。

    Returns:
        字符串值。

    Raises:
        WorkspaceImportRepositoryFailureError: 值不是字符串或 UUID 时
            抛出。
    """

    value = row[index]
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        raise WorkspaceImportRepositoryFailureError()
    return value


def _row_text_optional(row: Row, index: int) -> str | None:
    """从查询行取可空字符串字段（接受 UUID）。

    Args:
        row: SQLAlchemy 查询行。
        index: 列索引。

    Returns:
        字符串值或 ``None``。

    Raises:
        WorkspaceImportRepositoryFailureError: 值类型非法时抛出。
    """

    value = row[index]
    if value is None:
        return None
    return _row_text(row, index)


def _row_int(row: Row, index: int) -> int:
    """从查询行取整数字段。

    Args:
        row: SQLAlchemy 查询行。
        index: 列索引。

    Returns:
        整数值。

    Raises:
        WorkspaceImportRepositoryFailureError: 值不是整数时抛出。
    """

    value = row[index]
    if not isinstance(value, int):
        raise WorkspaceImportRepositoryFailureError()
    return value


def _row_bool(row: Row, index: int) -> bool:
    """从查询行取布尔字段。

    Args:
        row: SQLAlchemy 查询行。
        index: 列索引。

    Returns:
        布尔值。

    Raises:
        WorkspaceImportRepositoryFailureError: 值不是布尔时抛出。
    """

    value = row[index]
    if not isinstance(value, bool):
        raise WorkspaceImportRepositoryFailureError()
    return value


def _raise_drift() -> NoReturn:
    """抛出稳定 drift 错误。

    Args:
        无。

    Returns:
        永不返回。

    Raises:
        WorkspaceImportDriftError: 恒抛。
    """

    raise WorkspaceImportDriftError()


def _raise_repository_failure(error: Exception) -> NoReturn:
    """把数据库异常映射为稳定 repository failure。

    保留原始异常作为 ``__cause__`` 便于运维定位，但稳定消息仍只含
    safe code，不含 DSN、SQL 或候选值。

    Args:
        error: 原始数据库异常。

    Returns:
        永不返回。

    Raises:
        WorkspaceImportRepositoryFailureError: 恒抛。
    """

    raise WorkspaceImportRepositoryFailureError() from error


class PostgresWorkspaceImportRepository:
    """transaction-scoped PostgreSQL workspace import repository。

    Args:
        session_factory: SQLAlchemy ``sessionmaker[Session]`` 工厂。
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """初始化 repository。

        Args:
            session_factory: SQLAlchemy ``sessionmaker[Session]`` 工厂。

        Returns:
            无。

        Raises:
            无。
        """

        self._session_factory = session_factory

    def publish_import(
        self,
        scope: TenantScope,
        request: WorkspaceImportRequest,
    ) -> WorkspaceImportReceipt:
        """以单事务发布一次 workspace import。

        Args:
            scope: 租户范围。
            request: 已 fingerprint 的纯 import 请求。

        Returns:
            纯结果收据（``committed`` 或 ``no_op``）。

        Raises:
            WorkspaceImportUsageError: scope/request 非法时抛出。
            WorkspaceImportSchemaUnavailableError: 0002 schema 不可用时
                抛出。
            WorkspaceImportDriftError: marker/row 与 intended projection
                不一致时抛出。
            WorkspaceImportRepositoryFailureError: 数据库失败时抛出。
        """

        tenant_id = _validate_scope(scope)
        if not isinstance(request, WorkspaceImportRequest):
            raise WorkspaceImportUsageError()
        company_count = len(request.companies)
        security_count = company_count
        source_definition_count = len(request.source_definitions)
        bundle_count = len(request.locators)
        marker_id = derive_workspace_import_marker_id(tenant_id, request.migration_id)

        session = self._session_factory()
        session.begin()
        try:
            _set_tenant_local(session, tenant_id)
            self._probe_schema(session)
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": _advisory_key(tenant_id, request.migration_id)},
            )
            marker_row = session.execute(
                text(
                    f"SELECT {_MARKER_COLS} FROM {PLATFORM_SCHEMA_NAME}.workspace_import_markers "
                    "WHERE tenant_id = :tenant_id AND migration_id = :migration_id"
                ),
                {"tenant_id": tenant_id.value, "migration_id": request.migration_id},
            ).first()
            if marker_row is None:
                self._publish_new(
                    session=session,
                    tenant_id=tenant_id,
                    request=request,
                    marker_id=marker_id,
                    company_count=company_count,
                    security_count=security_count,
                    source_definition_count=source_definition_count,
                    bundle_count=bundle_count,
                )
                status = "committed"
            else:
                self._verify_no_op(
                    session=session,
                    tenant_id=tenant_id,
                    request=request,
                    marker_row=marker_row,
                    marker_id=marker_id,
                    company_count=company_count,
                    security_count=security_count,
                    source_definition_count=source_definition_count,
                    bundle_count=bundle_count,
                )
                status = "no_op"
            session.commit()
        except WorkspaceImportError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_repository_failure(error)
        return WorkspaceImportReceipt(
            marker_id=marker_id,
            migration_id=request.migration_id,
            status=status,
            company_count=company_count,
            security_count=security_count,
            source_definition_count=source_definition_count,
            bundle_count=bundle_count,
            source_root_fingerprint=request.source_root_fingerprint,
            staged_payload_sha256=request.staged_payload_sha256,
        )

    def _probe_schema(self, session: Session) -> None:
        """探测 0002 两张表是否可用。

        Args:
            session: 当前事务 Session。

        Returns:
            无。

        Raises:
            WorkspaceImportSchemaUnavailableError: 任一表缺失时抛出。
        """

        for table_name in ("workspace_import_markers", "research_bundle_locators"):
            qualified = f"{PLATFORM_SCHEMA_NAME}.{table_name}"
            found = session.execute(
                text("SELECT to_regclass(:qualified)"),
                {"qualified": qualified},
            ).scalar()
            if found is None:
                raise WorkspaceImportSchemaUnavailableError()

    def _verify_no_op(
        self,
        *,
        session: Session,
        tenant_id: TenantId,
        request: WorkspaceImportRequest,
        marker_row: Row,
        marker_id: str,
        company_count: int,
        security_count: int,
        source_definition_count: int,
        bundle_count: int,
    ) -> None:
        """校验已有 marker 与 intended rows 是否 exact（no-op 或 drift）。

        Args:
            session: 当前事务 Session。
            tenant_id: 租户标识。
            request: import 请求。
            marker_row: 已读取的 marker 行。
            marker_id: 派生的 marker 标识。
            company_count: intended 公司数。
            security_count: intended 证券数。
            source_definition_count: intended 数据源定义数。
            bundle_count: intended locator 数。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: marker 任一字段或任一 intended
                row 与 projection 不一致时抛出。
            WorkspaceImportRepositoryFailureError: 数据库读取失败时
                抛出。
        """

        if _row_text(marker_row, 0) != marker_id:
            _raise_drift()
        if _row_text(marker_row, 1) != tenant_id.value:
            _raise_drift()
        if _row_text(marker_row, 2) != request.migration_id:
            _raise_drift()
        if _row_int(marker_row, 3) != request.schema_version:
            _raise_drift()
        if _row_text(marker_row, 4) != request.source_root_fingerprint:
            _raise_drift()
        if _row_text(marker_row, 5) != request.staged_payload_sha256:
            _raise_drift()
        if _row_int(marker_row, 6) != company_count:
            _raise_drift()
        if _row_int(marker_row, 7) != security_count:
            _raise_drift()
        if _row_int(marker_row, 8) != source_definition_count:
            _raise_drift()
        if _row_int(marker_row, 9) != bundle_count:
            _raise_drift()
        for company in request.companies:
            self._verify_company_exact(session, company)
        for security in (company.security for company in request.companies):
            self._verify_security_exact(session, security)
        for definition in request.source_definitions:
            self._verify_source_definition_exact(session, definition)
        for locator in request.locators:
            self._verify_locator_exact(session, tenant_id, marker_id, locator)

    def _publish_new(
        self,
        *,
        session: Session,
        tenant_id: TenantId,
        request: WorkspaceImportRequest,
        marker_id: str,
        company_count: int,
        security_count: int,
        source_definition_count: int,
        bundle_count: int,
    ) -> None:
        """发布新 import：reconcile 公共 rows、插入 marker 与 locators。

        顺序为 public reference reconcile -> source definition reconcile
        -> marker insert -> locator inserts；locator 的
        ``(tenant_id, import_marker_id)`` 复合 FK 引用 marker，因此
        marker 必须先于 locator 存在。

        Args:
            session: 当前事务 Session。
            tenant_id: 租户标识。
            request: import 请求。
            marker_id: 派生的 marker 标识。
            company_count: intended 公司数。
            security_count: intended 证券数。
            source_definition_count: intended 数据源定义数。
            bundle_count: intended locator 数。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: 公共 row 冲突/漂移时抛出。
            WorkspaceImportRepositoryFailureError: 数据库失败时抛出。
        """

        for company in request.companies:
            self._reconcile_company(session, company)
        for security in (company.security for company in request.companies):
            self._reconcile_security(session, security)
        for definition in request.source_definitions:
            self._reconcile_source_definition(session, definition)
        session.execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.workspace_import_markers "
                "(id, tenant_id, migration_id, source_schema_version, source_root_fingerprint, "
                "staged_payload_sha256, company_count, security_count, "
                "source_definition_count, bundle_count) "
                "VALUES (:id, :tenant_id, :migration_id, :source_schema_version, "
                ":source_root_fingerprint, :staged_payload_sha256, :company_count, "
                ":security_count, :source_definition_count, :bundle_count)"
            ),
            {
                "id": marker_id,
                "tenant_id": tenant_id.value,
                "migration_id": request.migration_id,
                "source_schema_version": request.schema_version,
                "source_root_fingerprint": request.source_root_fingerprint,
                "staged_payload_sha256": request.staged_payload_sha256,
                "company_count": company_count,
                "security_count": security_count,
                "source_definition_count": source_definition_count,
                "bundle_count": bundle_count,
            },
        )
        for locator in request.locators:
            self._insert_locator(session, tenant_id, marker_id, locator)

    def _reconcile_company(self, session: Session, company: VerifiedLegacyCompany) -> None:
        """插入或 exact reuse 公司公共 reference row。

        Args:
            session: 当前事务 Session。
            company: ``VerifiedLegacyCompany``。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: 相同 ID projection 不一致或
                相同业务键映射到不同 ID 时抛出。
            WorkspaceImportRepositoryFailureError: 数据库失败时抛出。
        """

        company_id = company.company_id.value
        row = session.execute(
            text(
                f"SELECT {_COMPANY_COLS} FROM {PLATFORM_SCHEMA_NAME}.companies WHERE id = :id"
            ),
            {"id": company_id},
        ).first()
        if row is not None:
            if (
                _row_text(row, 0) != company.company_name
                or _row_text_optional(row, 1) != company.lei
                or _row_text_optional(row, 2) != company.country_code
            ):
                _raise_drift()
            return
        if company.lei is not None:
            conflict = session.execute(
                text(
                    f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.companies "
                    "WHERE lei = :lei AND lei IS NOT NULL AND id <> :id"
                ),
                {"lei": company.lei, "id": company_id},
            ).first()
            if conflict is not None:
                _raise_drift()
        session.execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.companies "
                "(id, legal_name, lei, country_code) VALUES (:id, :legal_name, :lei, :country_code)"
            ),
            {
                "id": company_id,
                "legal_name": company.company_name,
                "lei": company.lei,
                "country_code": company.country_code,
            },
        )

    def _reconcile_security(self, session: Session, security: LegacySecurityMapping) -> None:
        """插入或 exact reuse 证券公共 reference row。

        Args:
            session: 当前事务 Session。
            security: ``LegacySecurityMapping``。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: 相同 ID projection 不一致、业务键
                冲突或 security-company 关系不一致时抛出。
            WorkspaceImportRepositoryFailureError: 数据库失败时抛出。
        """

        security_id = security.security_id.value
        row = session.execute(
            text(
                f"SELECT {_SECURITY_COLS} FROM {PLATFORM_SCHEMA_NAME}.securities WHERE id = :id"
            ),
            {"id": security_id},
        ).first()
        if row is not None:
            if (
                _row_text(row, 0) != security.company_id.value
                or _row_text(row, 1) != security.ticker
                or _row_text(row, 2) != security.exchange_mic
                or _row_text(row, 3) != security.security_type.value
                or _row_text(row, 4) != security.currency
                or _row_text_optional(row, 5) != security.isin
                or _row_bool(row, 6) != security.is_active
            ):
                _raise_drift()
            return
        conflict = session.execute(
            text(
                f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.securities "
                "WHERE exchange_mic = :exchange_mic AND ticker = :ticker AND id <> :id"
            ),
            {
                "exchange_mic": security.exchange_mic,
                "ticker": security.ticker,
                "id": security_id,
            },
        ).first()
        if conflict is not None:
            _raise_drift()
        if security.isin is not None:
            isin_conflict = session.execute(
                text(
                    f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.securities "
                    "WHERE isin = :isin AND isin IS NOT NULL AND id <> :id"
                ),
                {"isin": security.isin, "id": security_id},
            ).first()
            if isin_conflict is not None:
                _raise_drift()
        session.execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.securities "
                "(id, company_id, ticker, exchange_mic, security_type, currency, isin, is_active) "
                "VALUES (:id, :company_id, :ticker, :exchange_mic, :security_type, "
                ":currency, :isin, :is_active)"
            ),
            {
                "id": security_id,
                "company_id": security.company_id.value,
                "ticker": security.ticker,
                "exchange_mic": security.exchange_mic,
                "security_type": security.security_type.value,
                "currency": security.currency,
                "isin": security.isin,
                "is_active": security.is_active,
            },
        )

    def _reconcile_source_definition(
        self,
        session: Session,
        definition: VerifiedLegacySourceDefinition,
    ) -> None:
        """插入或 exact reuse 数据源定义公共 reference row。

        Args:
            session: 当前事务 Session。
            definition: ``VerifiedLegacySourceDefinition``。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: 相同 ID projection 不一致或
                source_key 映射到不同 ID 时抛出。
            WorkspaceImportRepositoryFailureError: 数据库失败时抛出。
        """

        definition_id = definition.source_definition_id.value
        row = session.execute(
            text(
                f"SELECT {_SOURCE_DEFINITION_COLS} FROM {PLATFORM_SCHEMA_NAME}.source_definitions "
                "WHERE id = :id"
            ),
            {"id": definition_id},
        ).first()
        if row is not None:
            if (
                _row_text(row, 0) != definition.source_key
                or _row_text(row, 1) != definition.source_kind.value
                or _row_text(row, 2) != definition.display_name
                or _row_bool(row, 3) != definition.enabled_by_default
            ):
                _raise_drift()
            return
        conflict = session.execute(
            text(
                f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.source_definitions "
                "WHERE source_key = :source_key AND id <> :id"
            ),
            {"source_key": definition.source_key, "id": definition_id},
        ).first()
        if conflict is not None:
            _raise_drift()
        session.execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.source_definitions "
                "(id, source_key, source_kind, display_name, enabled_by_default) "
                "VALUES (:id, :source_key, :source_kind, :display_name, :enabled_by_default)"
            ),
            {
                "id": definition_id,
                "source_key": definition.source_key,
                "source_kind": definition.source_kind.value,
                "display_name": definition.display_name,
                "enabled_by_default": definition.enabled_by_default,
            },
        )

    def _insert_locator(
        self,
        session: Session,
        tenant_id: TenantId,
        marker_id: str,
        locator: VerifiedResearchBundleLocator,
    ) -> None:
        """插入单个 research bundle locator row。

        Args:
            session: 当前事务 Session。
            tenant_id: 租户标识。
            marker_id: 已插入 marker 标识。
            locator: ``VerifiedResearchBundleLocator``。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: 业务键冲突时抛出。
            WorkspaceImportRepositoryFailureError: 数据库失败时抛出。
        """

        conflict = session.execute(
            text(
                f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.research_bundle_locators "
                "WHERE tenant_id = :tenant_id AND security_id = :security_id "
                "AND template_name = :template_name AND id <> :id"
            ),
            {
                "tenant_id": tenant_id.value,
                "security_id": locator.security_id.value,
                "template_name": locator.template_name,
                "id": locator.locator_id,
            },
        ).first()
        if conflict is not None:
            _raise_drift()
        locator_conflict = session.execute(
            text(
                f"SELECT id FROM {PLATFORM_SCHEMA_NAME}.research_bundle_locators "
                "WHERE tenant_id = :tenant_id AND repository_key = :repository_key "
                "AND relative_locator = :relative_locator AND id <> :id"
            ),
            {
                "tenant_id": tenant_id.value,
                "repository_key": locator.repository_key,
                "relative_locator": locator.relative_locator,
                "id": locator.locator_id,
            },
        ).first()
        if locator_conflict is not None:
            _raise_drift()
        session.execute(
            text(
                f"INSERT INTO {PLATFORM_SCHEMA_NAME}.research_bundle_locators "
                "(id, tenant_id, import_marker_id, security_id, template_name, repository_key, "
                "relative_locator, bundle_sha256, artifact_manifest_sha256) "
                "VALUES (:id, :tenant_id, :import_marker_id, :security_id, :template_name, "
                ":repository_key, :relative_locator, :bundle_sha256, :artifact_manifest_sha256)"
            ),
            {
                "id": locator.locator_id,
                "tenant_id": tenant_id.value,
                "import_marker_id": marker_id,
                "security_id": locator.security_id.value,
                "template_name": locator.template_name,
                "repository_key": locator.repository_key,
                "relative_locator": locator.relative_locator,
                "bundle_sha256": locator.bundle_sha256,
                "artifact_manifest_sha256": locator.artifact_manifest_sha256,
            },
        )

    def _verify_company_exact(self, session: Session, company: VerifiedLegacyCompany) -> None:
        """校验已有公司 row 与 intended projection exact。

        Args:
            session: 当前事务 Session。
            company: ``VerifiedLegacyCompany``。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: row missing 或字段不一致时抛出。
        """

        row = session.execute(
            text(
                f"SELECT {_COMPANY_COLS} FROM {PLATFORM_SCHEMA_NAME}.companies WHERE id = :id"
            ),
            {"id": company.company_id.value},
        ).first()
        if row is None:
            _raise_drift()
        if (
            _row_text(row, 0) != company.company_name
            or _row_text_optional(row, 1) != company.lei
            or _row_text_optional(row, 2) != company.country_code
        ):
            _raise_drift()

    def _verify_security_exact(self, session: Session, security: LegacySecurityMapping) -> None:
        """校验已有证券 row 与 intended projection exact。

        Args:
            session: 当前事务 Session。
            security: ``LegacySecurityMapping``。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: row missing 或字段不一致时抛出。
        """

        row = session.execute(
            text(
                f"SELECT {_SECURITY_COLS} FROM {PLATFORM_SCHEMA_NAME}.securities WHERE id = :id"
            ),
            {"id": security.security_id.value},
        ).first()
        if row is None:
            _raise_drift()
        if (
            _row_text(row, 0) != security.company_id.value
            or _row_text(row, 1) != security.ticker
            or _row_text(row, 2) != security.exchange_mic
            or _row_text(row, 3) != security.security_type.value
            or _row_text(row, 4) != security.currency
            or _row_text_optional(row, 5) != security.isin
            or _row_bool(row, 6) != security.is_active
        ):
            _raise_drift()

    def _verify_source_definition_exact(
        self,
        session: Session,
        definition: VerifiedLegacySourceDefinition,
    ) -> None:
        """校验已有数据源定义 row 与 intended projection exact。

        Args:
            session: 当前事务 Session。
            definition: ``VerifiedLegacySourceDefinition``。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: row missing 或字段不一致时抛出。
        """

        row = session.execute(
            text(
                f"SELECT {_SOURCE_DEFINITION_COLS} FROM {PLATFORM_SCHEMA_NAME}.source_definitions "
                "WHERE id = :id"
            ),
            {"id": definition.source_definition_id.value},
        ).first()
        if row is None:
            _raise_drift()
        if (
            _row_text(row, 0) != definition.source_key
            or _row_text(row, 1) != definition.source_kind.value
            or _row_text(row, 2) != definition.display_name
            or _row_bool(row, 3) != definition.enabled_by_default
        ):
            _raise_drift()

    def _verify_locator_exact(
        self,
        session: Session,
        tenant_id: TenantId,
        marker_id: str,
        locator: VerifiedResearchBundleLocator,
    ) -> None:
        """校验已有 locator row 与 intended projection exact。

        Args:
            session: 当前事务 Session。
            tenant_id: 租户标识。
            marker_id: 已提交 marker 标识。
            locator: ``VerifiedResearchBundleLocator``。

        Returns:
            无。

        Raises:
            WorkspaceImportDriftError: row missing 或字段不一致时抛出。
        """

        row = session.execute(
            text(
                f"SELECT {_LOCATOR_COLS} FROM {PLATFORM_SCHEMA_NAME}.research_bundle_locators "
                "WHERE id = :id"
            ),
            {"id": locator.locator_id},
        ).first()
        if row is None:
            _raise_drift()
        if (
            _row_text(row, 0) != locator.locator_id
            or _row_text(row, 1) != tenant_id.value
            or _row_text(row, 2) != marker_id
            or _row_text(row, 3) != locator.security_id.value
            or _row_text(row, 4) != locator.template_name
            or _row_text(row, 5) != locator.repository_key
            or _row_text(row, 6) != locator.relative_locator
            or _row_text(row, 7) != locator.bundle_sha256
            or _row_text(row, 8) != locator.artifact_manifest_sha256
        ):
            _raise_drift()


__all__ = [
    "PostgresWorkspaceImportRepository",
]
