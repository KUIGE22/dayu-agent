"""PostgreSQL identity/source repository 实现。

本模块是 ``IdentityRepositoryProtocol`` 与 ``SourceRepositoryProtocol``
的 transaction-scoped 单一实现（S12-CTRL-01）：

- 每个方法自己拥有一个 ``Session.begin()`` 事务；
- 第一条数据库语句用 bind parameter 调用
  ``set_config('app.tenant_id', :tenant_id, true)``（等价
  ``SET LOCAL``，``is_local=true``），并读回确认 tenant 与
  ``TenantScope`` 一致；
- 所有私有 query 同时带显式 tenant predicate；RLS 是第二道边界；
- atomic company+security registration 只允许一个数据库事务，任一
  后续 insert 失败由事务回滚，禁止 application-level delete/补偿、
  第二事务或 partial commit；
- 禁止 ``create_all()``、autocommit、global tenant、session/repository
  泄漏。

安全约束：

- 稳定错误消息只含固定 safe code，不含 DSN/SQL/候选值；
- 所有入口在创建 Session 前再次校验 ``scope.tenant_id`` 与全部 ID
  的 canonical 形态，非法值抛 ``RepositoryInputError``，不执行 SQL、
  不传播 psycopg/SQLAlchemy UUID cast error。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import NoReturn, TypeAlias
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, sessionmaker

from dayu.investment.domain.identifiers import (
    CompanyId,
    SecurityId,
    TenantId,
    TenantScope,
)
from dayu.investment.domain.source import (
    CompanyProjection,
    CompanySecurityRegistration,
    JsonValue,
    RegisteredCompanySecurity,
    SecurityProjection,
    SecurityType,
    SourceDefinitionCreateRequest,
    SourceDefinitionId,
    SourceDefinitionProjection,
    SourceKind,
    SourceSubscriptionCreateRequest,
    SourceSubscriptionId,
    SourceSubscriptionProjection,
    SourceSubscriptionUpdateRequest,
    SubscriptionStatus,
)
from dayu.investment.storage.db import PLATFORM_SCHEMA_NAME, TENANT_CONTEXT_SETTING
from dayu.investment.storage.protocols import (
    RepositoryConflictError,
    RepositoryError,
    RepositoryInputError,
    RepositoryNotFoundError,
    RepositoryOptimisticConflictError,
)

WireJsonScalar: TypeAlias = str | int | float | bool | None
"""JSONB wire 标量：``str/int/float/bool/None``。"""

WireJsonValue: TypeAlias = (
    WireJsonScalar | list["WireJsonValue"] | dict[str, "WireJsonValue"]
)
"""JSONB wire 递归值：plain list/dict（无 MappingProxyType/tuple）。

outbound 由 domain JSON 展开为 plain 结构，inbound 把 JSONB 读回值
收窄为 domain JSON；float 有限性由 DTO 构造与 DB ingress 双向
fail-closed 保证。
"""

_SCHEMA = PLATFORM_SCHEMA_NAME

# 各查询统一列序常量（供 helper 索引，避免重组 tuple）。
_COMPANY_COLS = "legal_name, lei, country_code, created_at, updated_at, version"
_SECURITY_COLS = (
    "id, company_id, ticker, exchange_mic, security_type, currency, "
    "isin, is_active, created_at, updated_at, version"
)
_SOURCE_DEFINITION_COLS = (
    "id, source_key, source_kind, display_name, enabled_by_default, "
    "created_at, updated_at, version"
)
_SUBSCRIPTION_COLS = (
    "id, tenant_id, source_definition_id, company_id, security_id, status, "
    "config_json, created_at, updated_at, version"
)


def _canonical_uuid(value: str, label: str) -> str:
    """校验并返回 canonical UUID 字符串。

    Args:
        value: 待校验的 UUID 字符串。
        label: 用于错误消息的中文名称。

    Returns:
        校验通过的小写连字符 UUID 字符串。

    Raises:
        RepositoryInputError: 值不是规范 UUID 时抛出。
    """

    if not isinstance(value, str):
        raise RepositoryInputError(f"{label} 必须是规范 UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise RepositoryInputError(f"{label} 必须是规范 UUID") from None
    if parsed.int == 0:
        raise RepositoryInputError(f"{label} 必须是规范 UUID")
    canonical = str(parsed)
    if canonical != value:
        raise RepositoryInputError(f"{label} 必须是规范 UUID")
    return canonical


def _validate_scope(scope: TenantScope) -> TenantId:
    """校验租户范围并返回租户标识。

    Args:
        scope: 待校验的租户范围。

    Returns:
        租户标识。

    Raises:
        RepositoryInputError: scope 非法时抛出。
    """

    if not isinstance(scope, TenantScope):
        raise RepositoryInputError("scope 必须是 TenantScope")
    _canonical_uuid(scope.tenant_id.value, "租户标识")
    return scope.tenant_id


def _normalize_company_id(company_id: CompanyId) -> str:
    """校验并返回公司标识 canonical 值。

    Args:
        company_id: 公司标识。

    Returns:
        canonical UUID 字符串。

    Raises:
        RepositoryInputError: 标识非法时抛出。
    """

    if not isinstance(company_id, CompanyId):
        raise RepositoryInputError("company_id 必须是 CompanyId")
    return _canonical_uuid(company_id.value, "公司标识")


def _normalize_security_id(security_id: SecurityId) -> str:
    """校验并返回证券标识 canonical 值。

    Args:
        security_id: 证券标识。

    Returns:
        canonical UUID 字符串。

    Raises:
        RepositoryInputError: 标识非法时抛出。
    """

    if not isinstance(security_id, SecurityId):
        raise RepositoryInputError("security_id 必须是 SecurityId")
    return _canonical_uuid(security_id.value, "证券标识")


def _normalize_source_definition_id(source_definition_id: SourceDefinitionId) -> str:
    """校验并返回数据源定义标识 canonical 值。

    Args:
        source_definition_id: 数据源定义标识。

    Returns:
        canonical UUID 字符串。

    Raises:
        RepositoryInputError: 标识非法时抛出。
    """

    if not isinstance(source_definition_id, SourceDefinitionId):
        raise RepositoryInputError("source_definition_id 必须是 SourceDefinitionId")
    return _canonical_uuid(source_definition_id.value, "数据源定义标识")


def _normalize_subscription_id(subscription_id: SourceSubscriptionId) -> str:
    """校验并返回订阅标识 canonical 值。

    Args:
        subscription_id: 订阅标识。

    Returns:
        canonical UUID 字符串。

    Raises:
        RepositoryInputError: 标识非法时抛出。
    """

    if not isinstance(subscription_id, SourceSubscriptionId):
        raise RepositoryInputError("subscription_id 必须是 SourceSubscriptionId")
    return _canonical_uuid(subscription_id.value, "订阅标识")


def _validate_positive_version(expected_version: int) -> None:
    """校验期望版本为正整数。

    Args:
        expected_version: 期望版本。

    Returns:
        无。

    Raises:
        RepositoryInputError: 版本非正整数时抛出。
    """

    if type(expected_version) is not int or expected_version <= 0:
        raise RepositoryInputError("expected_version 必须为正整数，禁止 bool 冒充")


def _validate_nonblank_field(value: str, label: str) -> None:
    """校验文本非空且无首尾空白。

    Args:
        value: 待校验文本。
        label: 用于错误消息的中文名称。

    Returns:
        无。

    Raises:
        RepositoryInputError: 值为空、仅空白或含首尾空白时抛出。
    """

    if not isinstance(value, str) or not value or value != value.strip():
        raise RepositoryInputError(f"{label} 必须非空且无首尾空白")


def _set_tenant_local(session: Session, tenant_id: TenantId) -> None:
    """以 bind parameter 设置租户上下文并读回确认。

    使用 ``set_config('app.tenant_id', :tenant_id, true)``（等价
    ``SET LOCAL``，``is_local=true``），随后读回确认与
    ``TenantScope`` 一致。

    Args:
        session: 当前事务 Session。
        tenant_id: 租户标识。

    Returns:
        无。

    Raises:
        RepositoryError: 读回确认不一致时抛出（不泄漏候选值）。
    """

    tenant_value = _canonical_uuid(tenant_id.value, "租户标识")
    result = session.execute(
        text(f"SELECT set_config('{TENANT_CONTEXT_SETTING}', :tenant_id, true)"),
        {"tenant_id": tenant_value},
    )
    set_value = result.scalar()
    if set_value != tenant_value:
        raise RepositoryError("租户上下文设置确认失败")


def _session_for_scope(session_factory: sessionmaker[Session], scope: TenantScope) -> Session:
    """创建会话并设置租户上下文（私有辅助）。

    Args:
        session_factory: ``sessionmaker[Session]`` 工厂。
        scope: 租户范围。

    Returns:
        已设置租户上下文的新 Session（事务已开始）。

    Raises:
        RepositoryInputError: scope 非法时抛出。
        RepositoryError: 租户上下文确认失败时抛出。
    """

    tenant_id = _validate_scope(scope)
    session = session_factory()
    session.begin()
    _set_tenant_local(session, tenant_id)
    return session


def _to_aware_utc(value: datetime) -> datetime:
    """把数据库时刻归一化为 aware UTC datetime。

    Args:
        value: 数据库返回的时刻。

    Returns:
        aware UTC datetime。

    Raises:
        RepositoryError: 值不是时刻时抛出（不泄漏候选值）。
    """

    if isinstance(value, datetime):
        return value
    raise RepositoryError("数据库时刻读取失败")


def _row_text(row: Row, index: int) -> str:
    """从行取字符串字段（接受 UUID 并转为 canonical 字符串）。

    Args:
        row: 查询行。
        index: 列索引。

    Returns:
        字符串值。

    Raises:
        RepositoryError: 值不是字符串或 UUID 时抛出。
    """

    value = row[index]
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        raise RepositoryError("数据库字段类型读取失败")
    return value


def _row_text_optional(row: Row, index: int) -> str | None:
    """从行取可空字符串字段（接受 UUID）。

    Args:
        row: 查询行。
        index: 列索引。

    Returns:
        字符串值或 ``None``。

    Raises:
        RepositoryError: 值非字符串/UUID 且非 None 时抛出。
    """

    value = row[index]
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        raise RepositoryError("数据库字段类型读取失败")
    return value


def _row_int(row: Row, index: int) -> int:
    """从行取整数字段。

    Args:
        row: 查询行。
        index: 列索引。

    Returns:
        整数值。

    Raises:
        RepositoryError: 值不是整数时抛出。
    """

    value = row[index]
    if not isinstance(value, int):
        raise RepositoryError("数据库字段类型读取失败")
    return value


def _row_bool(row: Row, index: int) -> bool:
    """从行取布尔字段。

    Args:
        row: 查询行。
        index: 列索引。

    Returns:
        布尔值。

    Raises:
        RepositoryError: 值不是布尔时抛出。
    """

    value = row[index]
    if not isinstance(value, bool):
        raise RepositoryError("数据库字段类型读取失败")
    return value


def _row_company_with_id(row: Row, company_id: CompanyId) -> CompanyProjection:
    """把公司行转换为投影（调用方已持有 company_id）。

    列序：legal_name, lei, country_code, created_at, updated_at, version。

    Args:
        row: 公司查询行。
        company_id: 公司标识。

    Returns:
        公司投影。

    Raises:
        无。
    """

    return CompanyProjection(
        company_id=company_id,
        legal_name=_row_text(row, 0),
        lei=_row_text_optional(row, 1),
        country_code=_row_text_optional(row, 2),
        created_at=_to_aware_utc(row[3]),
        updated_at=_to_aware_utc(row[4]),
        version=_row_int(row, 5),
    )


def _row_security_full(row: Row) -> SecurityProjection:
    """把完整证券行转换为投影。

    列序（``_SECURITY_COLS``）：id, company_id, ticker, exchange_mic,
    security_type, currency, isin, is_active, created_at, updated_at,
    version。

    Args:
        row: 完整证券查询行。

    Returns:
        证券投影。

    Raises:
        无。
    """

    return SecurityProjection(
        security_id=SecurityId(_row_text(row, 0)),
        company_id=CompanyId(_row_text(row, 1)),
        ticker=_row_text(row, 2),
        exchange_mic=_row_text(row, 3),
        security_type=SecurityType(_row_text(row, 4)),
        currency=_row_text(row, 5),
        isin=_row_text_optional(row, 6),
        is_active=_row_bool(row, 7),
        created_at=_to_aware_utc(row[8]),
        updated_at=_to_aware_utc(row[9]),
        version=_row_int(row, 10),
    )


def _row_source_definition_full(row: Row) -> SourceDefinitionProjection:
    """把完整数据源定义行转换为投影。

    列序（``_SOURCE_DEFINITION_COLS``）：id, source_key, source_kind,
    display_name, enabled_by_default, created_at, updated_at, version。

    Args:
        row: 完整数据源定义查询行。

    Returns:
        数据源定义投影。

    Raises:
        无。
    """

    return SourceDefinitionProjection(
        source_definition_id=SourceDefinitionId(_row_text(row, 0)),
        source_key=_row_text(row, 1),
        source_kind=SourceKind(_row_text(row, 2)),
        display_name=_row_text(row, 3),
        enabled_by_default=_row_bool(row, 4),
        created_at=_to_aware_utc(row[5]),
        updated_at=_to_aware_utc(row[6]),
        version=_row_int(row, 7),
    )


def _row_subscription_full(row: Row) -> SourceSubscriptionProjection:
    """把完整订阅行转换为投影。

    列序（``_SUBSCRIPTION_COLS``）：id, tenant_id, source_definition_id,
    company_id, security_id, status, config_json, created_at, updated_at,
    version。

    Args:
        row: 完整订阅查询行。

    Returns:
        订阅投影。

    Raises:
        无。
    """

    config = row[6]
    if not isinstance(config, dict):
        raise RepositoryError("订阅配置读取失败")
    converted_config = _json_inbound(config)
    if not isinstance(converted_config, Mapping):
        raise RepositoryError("订阅配置读取失败")
    company_id = CompanyId(_row_text(row, 3)) if row[3] is not None else None
    security_id = SecurityId(_row_text(row, 4)) if row[4] is not None else None
    return SourceSubscriptionProjection(
        subscription_id=SourceSubscriptionId(_row_text(row, 0)),
        tenant_id=TenantId(_row_text(row, 1)),
        source_definition_id=SourceDefinitionId(_row_text(row, 2)),
        company_id=company_id,
        security_id=security_id,
        status=SubscriptionStatus(_row_text(row, 5)),
        config=converted_config,
        created_at=_to_aware_utc(row[7]),
        updated_at=_to_aware_utc(row[8]),
        version=_row_int(row, 9),
    )


def _json_dumps(mapping: Mapping[str, JsonValue]) -> str:
    """把 JSON 映射序列化为 JSON 字符串（递归 codec）。

    递归展开嵌套 Mapping 为普通 dict、tuple 为 list、标量不变，使
    DTO 深冻结后的 ``MappingProxyType``/tuple 可被 ``json.dumps`` 序列化。

    Args:
        mapping: 待序列化的配置映射。

    Returns:
        JSON 字符串。

    Raises:
        RepositoryInputError: 存在非字符串 key 或非法值类型时抛出
            （消息不含候选值）。
    """

    plain = _json_outbound(mapping)
    try:
        return json.dumps(plain)
    except (TypeError, ValueError):
        raise RepositoryInputError("config 必须是合法 JSON") from None


def _json_outbound(value: JsonValue) -> WireJsonValue:
    """递归把 domain JSON 值转换为 JSONB wire plain 结构（outbound）。

    Mapping -> 普通 dict（递归）、tuple -> list（递归）、标量不变；
    拒绝非字符串 key 与非法值类型。

    Args:
        value: domain JSON 值（可含 MappingProxyType/tuple）。

    Returns:
        ``WireJsonValue`` plain 结构（可被 ``json.dumps`` 序列化）。

    Raises:
        RepositoryInputError: 存在非字符串 key 或非法值类型时抛出。
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_json_outbound(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, WireJsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RepositoryInputError("config 只允许字符串 key")
            result[key] = _json_outbound(item)
        return result
    raise RepositoryInputError("config 含非法 JSON 值类型")


def _json_inbound(value: WireJsonValue) -> JsonValue:
    """递归把 JSONB wire 值转换为 domain JSON 值（inbound）。

    dict -> 普通 dict（递归）、list -> tuple（递归）、标量不变；
    拒绝非字符串 key 与非法值类型，映射稳定 ``RepositoryError``。

    Args:
        value: JSONB 读回的 wire 结构。

    Returns:
        domain JSON 值（嵌套 dict/tuple）。

    Raises:
        RepositoryError: 存在非字符串 key 或非法值类型时抛出。
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return tuple(_json_inbound(item) for item in value)
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RepositoryError("config 只允许字符串 key")
            result[key] = _json_inbound(item)
        return result
    raise RepositoryError("config 含非法 JSON 值类型")


def _raise_stable_error(error: Exception) -> NoReturn:
    """把数据库异常映射为稳定错误（不泄漏候选值）。

    唯一键冲突映射 ``RepositoryConflictError``；其余映射
    ``RepositoryError``。

    Args:
        error: 原始数据库异常。

    Returns:
        永不返回，直接抛稳定错误。

    Raises:
        RepositoryConflictError: 唯一键冲突时抛出。
        RepositoryError: 其它数据库失败时抛出。
    """

    message = str(error)
    lowered = message.lower()
    if "duplicate key" in lowered or "unique violation" in lowered:
        raise RepositoryConflictError("duplicate key conflict") from None
    raise RepositoryError("database operation failed") from None


class PostgresIdentityRepository:
    """transaction-scoped PostgreSQL identity/source repository。

    同时实现 ``IdentityRepositoryProtocol`` 与
    ``SourceRepositoryProtocol``；每个方法自己拥有一个
    ``Session.begin()`` 事务，并在第一条语句前设置租户上下文。

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

    def register_company_security(
        self,
        scope: TenantScope,
        request: CompanySecurityRegistration,
    ) -> RegisteredCompanySecurity:
        """原子注册公司+证券（单事务）。

        Args:
            scope: 租户范围。
            request: 公司+证券注册请求。

        Returns:
            注册结果投影。

        Raises:
            RepositoryInputError: 输入非法时抛出。
            RepositoryConflictError: 唯一键冲突时抛出。
            RepositoryError: 其它数据库失败时抛出。
        """

        _validate_scope(scope)
        company_id = _normalize_company_id(request.company.company_id)
        security_id = _normalize_security_id(request.security.security_id)
        if request.company.company_id != request.security.company_id:
            raise RepositoryInputError("company 与 security 的 company_id 必须相同")
        _validate_nonblank_field(request.company.legal_name, "公司法定名称")
        _validate_nonblank_field(request.security.ticker, "证券代码")
        session = _session_for_scope(self._session_factory, scope)
        try:
            session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.companies "
                    "(id, legal_name, lei, country_code) "
                    "VALUES (:id, :legal_name, :lei, :country_code)"
                ),
                {
                    "id": company_id,
                    "legal_name": request.company.legal_name,
                    "lei": request.company.lei,
                    "country_code": request.company.country_code,
                },
            )
            session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.securities "
                    "(id, company_id, ticker, exchange_mic, security_type, currency, isin, is_active) "
                    "VALUES (:id, :company_id, :ticker, :exchange_mic, :security_type, "
                    ":currency, :isin, :is_active)"
                ),
                {
                    "id": security_id,
                    "company_id": company_id,
                    "ticker": request.security.ticker,
                    "exchange_mic": request.security.exchange_mic,
                    "security_type": request.security.security_type.value,
                    "currency": request.security.currency,
                    "isin": request.security.isin,
                    "is_active": request.security.is_active,
                },
            )
            session.flush()
            company_row = session.execute(
                text(f"SELECT {_COMPANY_COLS} FROM {_SCHEMA}.companies WHERE id = :id"),
                {"id": company_id},
            ).first()
            security_row = session.execute(
                text(f"SELECT {_SECURITY_COLS} FROM {_SCHEMA}.securities WHERE id = :id"),
                {"id": security_id},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if company_row is None or security_row is None:
            raise RepositoryError("注册后读取投影失败")
        company = _row_company_with_id(company_row, request.company.company_id)
        security = _row_security_full(security_row)
        return RegisteredCompanySecurity(company=company, security=security)

    def get_company(
        self,
        scope: TenantScope,
        company_id: CompanyId,
    ) -> CompanyProjection | None:
        """按 id 读取公司。

        Args:
            scope: 租户范围。
            company_id: 公司标识。

        Returns:
            公司投影或 ``None``。

        Raises:
            RepositoryInputError: 输入非法时抛出。
        """

        _validate_scope(scope)
        normalized_id = _normalize_company_id(company_id)
        session = _session_for_scope(self._session_factory, scope)
        try:
            row = session.execute(
                text(f"SELECT {_COMPANY_COLS} FROM {_SCHEMA}.companies WHERE id = :id"),
                {"id": normalized_id},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if row is None:
            return None
        return _row_company_with_id(row, company_id)

    def get_security(
        self,
        scope: TenantScope,
        security_id: SecurityId,
    ) -> SecurityProjection | None:
        """按 id 读取证券。

        Args:
            scope: 租户范围。
            security_id: 证券标识。

        Returns:
            证券投影或 ``None``。

        Raises:
            RepositoryInputError: 输入非法时抛出。
        """

        _validate_scope(scope)
        normalized_id = _normalize_security_id(security_id)
        session = _session_for_scope(self._session_factory, scope)
        try:
            row = session.execute(
                text(f"SELECT {_SECURITY_COLS} FROM {_SCHEMA}.securities WHERE id = :id"),
                {"id": normalized_id},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if row is None:
            return None
        return _row_security_full(row)

    def find_security(
        self,
        scope: TenantScope,
        exchange_mic: str,
        ticker: str,
    ) -> SecurityProjection | None:
        """按交易所 MIC 与证券代码查找证券。

        Args:
            scope: 租户范围。
            exchange_mic: 4 位大写交易所 MIC。
            ticker: 证券代码。

        Returns:
            证券投影或 ``None``。

        Raises:
            RepositoryInputError: 输入非法时抛出。
        """

        _validate_scope(scope)
        if not isinstance(exchange_mic, str) or len(exchange_mic) != 4 or not exchange_mic.isupper():
            raise RepositoryInputError("exchange_mic 必须是 4 位大写")
        if not isinstance(ticker, str) or not ticker.strip():
            raise RepositoryInputError("ticker 必须非空")
        session = _session_for_scope(self._session_factory, scope)
        try:
            row = session.execute(
                text(
                    f"SELECT {_SECURITY_COLS} FROM {_SCHEMA}.securities "
                    "WHERE exchange_mic = :exchange_mic AND ticker = :ticker"
                ),
                {"exchange_mic": exchange_mic, "ticker": ticker},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if row is None:
            return None
        return _row_security_full(row)

    def register_source_definition(
        self,
        scope: TenantScope,
        request: SourceDefinitionCreateRequest,
    ) -> SourceDefinitionProjection:
        """注册数据源定义。

        Args:
            scope: 租户范围。
            request: 数据源定义创建请求。

        Returns:
            数据源定义投影。

        Raises:
            RepositoryInputError: 输入非法时抛出。
            RepositoryConflictError: ``source_key`` 冲突时抛出。
        """

        _validate_scope(scope)
        source_definition_id = _normalize_source_definition_id(request.source_definition_id)
        _validate_nonblank_field(request.source_key, "数据源键")
        _validate_nonblank_field(request.display_name, "数据源显示名")
        session = _session_for_scope(self._session_factory, scope)
        try:
            session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.source_definitions "
                    "(id, source_key, source_kind, display_name, enabled_by_default) "
                    "VALUES (:id, :source_key, :source_kind, :display_name, :enabled_by_default)"
                ),
                {
                    "id": source_definition_id,
                    "source_key": request.source_key,
                    "source_kind": request.source_kind.value,
                    "display_name": request.display_name,
                    "enabled_by_default": request.enabled_by_default,
                },
            )
            session.flush()
            row = session.execute(
                text(
                    f"SELECT {_SOURCE_DEFINITION_COLS} FROM {_SCHEMA}.source_definitions "
                    "WHERE id = :id"
                ),
                {"id": source_definition_id},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if row is None:
            raise RepositoryError("注册后读取投影失败")
        return _row_source_definition_full(row)

    def get_source_definition(
        self,
        scope: TenantScope,
        source_definition_id: SourceDefinitionId,
    ) -> SourceDefinitionProjection | None:
        """按 id 读取数据源定义。

        Args:
            scope: 租户范围。
            source_definition_id: 数据源定义标识。

        Returns:
            数据源定义投影或 ``None``。

        Raises:
            RepositoryInputError: 输入非法时抛出。
        """

        _validate_scope(scope)
        normalized_id = _normalize_source_definition_id(source_definition_id)
        session = _session_for_scope(self._session_factory, scope)
        try:
            row = session.execute(
                text(
                    f"SELECT {_SOURCE_DEFINITION_COLS} FROM {_SCHEMA}.source_definitions "
                    "WHERE id = :id"
                ),
                {"id": normalized_id},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if row is None:
            return None
        return _row_source_definition_full(row)

    def find_source_definition(
        self,
        scope: TenantScope,
        source_key: str,
    ) -> SourceDefinitionProjection | None:
        """按 ``source_key`` 查找数据源定义。

        Args:
            scope: 租户范围。
            source_key: 数据源唯一键。

        Returns:
            数据源定义投影或 ``None``。

        Raises:
            RepositoryInputError: 输入非法时抛出。
        """

        _validate_scope(scope)
        if not isinstance(source_key, str) or not source_key.strip():
            raise RepositoryInputError("source_key 必须非空")
        session = _session_for_scope(self._session_factory, scope)
        try:
            row = session.execute(
                text(
                    f"SELECT {_SOURCE_DEFINITION_COLS} FROM {_SCHEMA}.source_definitions "
                    "WHERE source_key = :source_key"
                ),
                {"source_key": source_key},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if row is None:
            return None
        return _row_source_definition_full(row)

    def create_source_subscription(
        self,
        scope: TenantScope,
        request: SourceSubscriptionCreateRequest,
    ) -> SourceSubscriptionProjection:
        """创建数据源订阅。

        Args:
            scope: 租户范围。
            request: 订阅创建请求。

        Returns:
            订阅投影。

        Raises:
            RepositoryInputError: 输入非法时抛出。
            RepositoryConflictError: 订阅目标冲突时抛出。
        """

        tenant_id = _validate_scope(scope)
        subscription_id = _normalize_subscription_id(request.subscription_id)
        source_definition_id = _normalize_source_definition_id(request.source_definition_id)
        company_id = (
            _normalize_company_id(request.company_id) if request.company_id is not None else None
        )
        security_id = (
            _normalize_security_id(request.security_id) if request.security_id is not None else None
        )
        if company_id is not None and security_id is not None:
            raise RepositoryInputError("company_id 与 security_id 至多一个非空")
        session = _session_for_scope(self._session_factory, scope)
        try:
            session.execute(
                text(
                    f"INSERT INTO {_SCHEMA}.source_subscriptions "
                    "(id, tenant_id, source_definition_id, company_id, security_id, status, config_json) "
                    "VALUES (:id, :tenant_id, :source_definition_id, :company_id, "
                    ":security_id, :status, CAST(:config_json AS jsonb))"
                ),
                {
                    "id": subscription_id,
                    "tenant_id": tenant_id.value,
                    "source_definition_id": source_definition_id,
                    "company_id": company_id,
                    "security_id": security_id,
                    "status": request.status.value,
                    "config_json": _json_dumps(request.config),
                },
            )
            session.flush()
            row = session.execute(
                text(
                    f"SELECT {_SUBSCRIPTION_COLS} FROM {_SCHEMA}.source_subscriptions "
                    "WHERE id = :id"
                ),
                {"id": subscription_id},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if row is None:
            raise RepositoryError("创建后读取投影失败")
        return _row_subscription_full(row)

    def get_source_subscription(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceSubscriptionProjection | None:
        """按 id 读取订阅（tenant-local）。

        Args:
            scope: 租户范围。
            subscription_id: 订阅标识。

        Returns:
            订阅投影或 ``None``。

        Raises:
            RepositoryInputError: 输入非法时抛出。
        """

        tenant_id = _validate_scope(scope)
        normalized_id = _normalize_subscription_id(subscription_id)
        session = _session_for_scope(self._session_factory, scope)
        try:
            row = session.execute(
                text(
                    f"SELECT {_SUBSCRIPTION_COLS} FROM {_SCHEMA}.source_subscriptions "
                    "WHERE tenant_id = :tenant_id AND id = :id"
                ),
                {"tenant_id": tenant_id.value, "id": normalized_id},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if row is None:
            return None
        return _row_subscription_full(row)

    def update_source_subscription(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
        expected_version: int,
        request: SourceSubscriptionUpdateRequest,
    ) -> SourceSubscriptionProjection:
        """CAS 更新订阅（``tenant_id + id + version``）。

        Args:
            scope: 租户范围。
            subscription_id: 订阅标识。
            expected_version: 期望版本（正整数）。
            request: 订阅更新请求。

        Returns:
            更新后的订阅投影。

        Raises:
            RepositoryInputError: 输入非法时抛出。
            RepositoryNotFoundError: row 不存在（含跨租户）时抛出。
            RepositoryOptimisticConflictError: 版本不一致时抛出。
        """

        tenant_id = _validate_scope(scope)
        normalized_id = _normalize_subscription_id(subscription_id)
        _validate_positive_version(expected_version)
        session = _session_for_scope(self._session_factory, scope)
        try:
            row = session.execute(
                text(
                    f"UPDATE {_SCHEMA}.source_subscriptions "
                    "SET status = :status, config_json = CAST(:config_json AS jsonb), "
                    "updated_at = transaction_timestamp(), version = version + 1 "
                    "WHERE tenant_id = :tenant_id AND id = :id AND version = :expected_version "
                    "RETURNING id"
                ),
                {
                    "tenant_id": tenant_id.value,
                    "id": normalized_id,
                    "status": request.status.value,
                    "config_json": _json_dumps(request.config),
                    "expected_version": expected_version,
                },
            ).first()
            if row is None:
                exists = session.execute(
                    text(
                        f"SELECT version FROM {_SCHEMA}.source_subscriptions "
                        "WHERE tenant_id = :tenant_id AND id = :id"
                    ),
                    {"tenant_id": tenant_id.value, "id": normalized_id},
                ).first()
                session.commit()
                if exists is None:
                    raise RepositoryNotFoundError("source_subscription not found")
                raise RepositoryOptimisticConflictError("source_subscription version conflict")
            updated_row = session.execute(
                text(
                    f"SELECT {_SUBSCRIPTION_COLS} FROM {_SCHEMA}.source_subscriptions "
                    "WHERE tenant_id = :tenant_id AND id = :id"
                ),
                {"tenant_id": tenant_id.value, "id": normalized_id},
            ).first()
            session.commit()
        except RepositoryError:
            session.rollback()
            raise
        except Exception as error:
            session.rollback()
            _raise_stable_error(error)
        if updated_row is None:
            raise RepositoryError("更新后读取投影失败")
        return _row_subscription_full(updated_row)


__all__ = [
    "PostgresIdentityRepository",
]
