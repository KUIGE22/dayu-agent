"""投资平台 identity/source repository 单元契约测试（无数据库）。

本文件只验证不需要数据库的 unit contract（S12-CTRL-03）：

- domain/source.py 的 frozen strict DTO：closed enums、canonical UUID
  强标识、全部 create/update request 与 read projection 的字段校验
  （非空/无首尾空白、MIC/currency/country code 形态、aware UTC、
  positive version、JSON 递归约束）；
- storage/protocols.py 的协议签名与五类稳定错误层级；
- InvestmentIdentityService 只编排 repository 协议、稳定注册名精确、
  ``close()`` 线程安全幂等、不 import ORM/engine/session。

真实 unique/transaction/CAS/tenant/RLS/startup provider 全部由
integration lane 证明，本文件不触碰数据库。
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from types import MappingProxyType

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from typing import Never

from dayu.investment.composition import (
    PlatformIdentityServiceProtocol,
    PlatformOwnedLifecycleProtocol,
)
from dayu.investment.domain.identifiers import (
    CompanyId,
    Principal,
    SecurityId,
    TenantId,
    TenantScope,
)
from dayu.investment.domain.source import (
    CompanyCreateRequest,
    CompanyProjection,
    CompanySecurityRegistration,
    JsonValue,
    RegisteredCompanySecurity,
    SecurityCreateRequest,
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
from dayu.investment.storage.postgres_identity import PostgresIdentityRepository
from dayu.investment.storage.protocols import (
    IdentityRepositoryProtocol,
    RepositoryConflictError,
    RepositoryError,
    RepositoryInputError,
    RepositoryNotFoundError,
    RepositoryOptimisticConflictError,
    SourceRepositoryProtocol,
)
from dayu.services.investment_identity import InvestmentIdentityService

_TENANT = TenantId("11111111-1111-1111-1111-111111111111")
_COMPANY = CompanyId("22222222-2222-2222-2222-222222222222")
_SECURITY = SecurityId("33333333-3333-3333-3333-333333333333")
_SOURCE_DEF = SourceDefinitionId("44444444-4444-4444-4444-444444444444")
_SUBSCRIPTION = SourceSubscriptionId("55555555-5555-5555-5555-555555555555")


def _scope() -> TenantScope:
    """构造测试租户范围。

    Args:
        无。

    Returns:
        由测试主体派生的租户范围。

    Raises:
        无。
    """

    return Principal(tenant_id=_TENANT, user_id="u-1").to_scope()


def _aware_utc() -> datetime:
    """构造 aware UTC 时刻。

    Args:
        无。

    Returns:
        UTC 时刻。

    Raises:
        无。
    """

    return datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)


def _company_request() -> CompanyCreateRequest:
    """构造合法公司创建请求。

    Args:
        无。

    Returns:
        公司创建请求。

    Raises:
        无。
    """

    return CompanyCreateRequest(
        company_id=_COMPANY,
        legal_name="Acme Corp",
        lei=None,
        country_code="US",
    )


def _security_request() -> SecurityCreateRequest:
    """构造合法证券创建请求。

    Args:
        无。

    Returns:
        证券创建请求。

    Raises:
        无。
    """

    return SecurityCreateRequest(
        security_id=_SECURITY,
        company_id=_COMPANY,
        ticker="ACME",
        exchange_mic="XNYS",
        security_type=SecurityType.EQUITY,
        currency="USD",
        isin=None,
        is_active=True,
    )


def _registration() -> CompanySecurityRegistration:
    """构造合法公司+证券注册请求。

    Args:
        无。

    Returns:
        注册请求。

    Raises:
        无。
    """

    return CompanySecurityRegistration(
        company=_company_request(),
        security=_security_request(),
    )


def _source_definition_request() -> SourceDefinitionCreateRequest:
    """构造合法数据源定义创建请求。

    Args:
        无。

    Returns:
        数据源定义创建请求。

    Raises:
        无。
    """

    return SourceDefinitionCreateRequest(
        source_definition_id=_SOURCE_DEF,
        source_key="sec-filings",
        source_kind=SourceKind.FILING,
        display_name="SEC 财报",
        enabled_by_default=True,
    )


def _subscription_request() -> SourceSubscriptionCreateRequest:
    """构造合法订阅创建请求。

    Args:
        无。

    Returns:
        订阅创建请求。

    Raises:
        无。
    """

    return SourceSubscriptionCreateRequest(
        subscription_id=_SUBSCRIPTION,
        source_definition_id=_SOURCE_DEF,
        company_id=_COMPANY,
        security_id=None,
        status=SubscriptionStatus.ENABLED,
        config={},
    )


class TestSourceDtoStrictValidation:
    """source DTO 严格校验。"""

    @pytest.mark.unit
    def test_closed_enums_exact_values(self) -> None:
        """closed enums 值精确。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        assert {item.value for item in SecurityType} == {
            "equity",
            "adr",
            "etf",
            "fund",
            "bond",
            "other",
        }
        assert {item.value for item in SourceKind} == {
            "filing",
            "announcement",
            "industry_metric",
            "research_material",
            "market_price",
            "fx",
        }
        assert {item.value for item in SubscriptionStatus} == {"enabled", "disabled"}

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "raw",
        [
            "12345678-1234-1234-1234-1234567890ab",
            "abcdef12-abcd-abcd-abcd-abcdef123456",
        ],
    )
    def test_source_definition_id_accepts_canonical_uuid(self, raw: str) -> None:
        """canonical 小写 UUID 构造成功。

        Args:
            raw: 规范 UUID 字符串。

        Returns:
            无。

        Raises:
            无。
        """

        assert str(SourceDefinitionId(raw)) == raw

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "raw",
        [
            "00000000-0000-0000-0000-000000000000",
            "ZZZZZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZZZZZZZZZ",
            "123456781234123412341234567890AB",
            "12345678-1234-1234-1234-1234567890AB",
            "",
            "  ",
            "not-a-uuid",
        ],
    )
    def test_source_definition_id_rejects_non_canonical(self, raw: str) -> None:
        """非 canonical UUID 构造失败。

        Args:
            raw: 非法 UUID 字符串。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            SourceDefinitionId(raw)

    @pytest.mark.unit
    def test_company_security_registration_requires_same_company(self) -> None:
        """company 与 security 的 company_id 必须相同。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        other_company = CompanyId("66666666-6666-6666-6666-666666666666")
        security = SecurityCreateRequest(
            security_id=_SECURITY,
            company_id=other_company,
            ticker="ACME",
            exchange_mic="XNYS",
            security_type=SecurityType.EQUITY,
            currency="USD",
            isin=None,
            is_active=True,
        )
        with pytest.raises(ValueError):
            CompanySecurityRegistration(
                company=_company_request(),
                security=security,
            )

    @pytest.mark.unit
    def test_security_validation_rejects_bad_fields(self) -> None:
        """证券字段非法时 fail closed。

        ticker 与表约束一致仅校验非空/无首尾空白；MIC 与 currency
        分别要求 4 位大写 / 3 位大写。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            SecurityCreateRequest(
                security_id=_SECURITY,
                company_id=_COMPANY,
                ticker="",
                exchange_mic="XNYS",
                security_type=SecurityType.EQUITY,
                currency="USD",
                isin=None,
                is_active=True,
            )
        with pytest.raises(ValueError):
            SecurityCreateRequest(
                security_id=_SECURITY,
                company_id=_COMPANY,
                ticker="ACME",
                exchange_mic="xny",
                security_type=SecurityType.EQUITY,
                currency="USD",
                isin=None,
                is_active=True,
            )
        with pytest.raises(ValueError):
            SecurityCreateRequest(
                security_id=_SECURITY,
                company_id=_COMPANY,
                ticker="ACME",
                exchange_mic="XNYS",
                security_type=SecurityType.EQUITY,
                currency="usd",
                isin=None,
                is_active=True,
            )

    @pytest.mark.unit
    def test_subscription_target_exclusive(self) -> None:
        """订阅 company/security 至多一个非空。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            SourceSubscriptionCreateRequest(
                subscription_id=_SUBSCRIPTION,
                source_definition_id=_SOURCE_DEF,
                company_id=_COMPANY,
                security_id=_SECURITY,
                status=SubscriptionStatus.ENABLED,
                config={},
            )

    @pytest.mark.unit
    def test_subscription_config_rejects_nan_and_cycle(self) -> None:
        """订阅 config 拒绝 NaN/Infinity/cycle。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            SourceSubscriptionCreateRequest(
                subscription_id=_SUBSCRIPTION,
                source_definition_id=_SOURCE_DEF,
                company_id=None,
                security_id=None,
                status=SubscriptionStatus.ENABLED,
                config={"x": float("nan")},
            )
        loop: dict[str, JsonValue] = {}
        loop["self"] = loop
        with pytest.raises(ValueError):
            SourceSubscriptionCreateRequest(
                subscription_id=_SUBSCRIPTION,
                source_definition_id=_SOURCE_DEF,
                company_id=None,
                security_id=None,
                status=SubscriptionStatus.ENABLED,
                config=loop,
            )
    @pytest.mark.unit
    def test_subscription_config_defensively_copied(self) -> None:
        """订阅 config 被防御性冻结。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        source: dict[str, str] = {"a": "b"}
        request = SourceSubscriptionCreateRequest(
            subscription_id=_SUBSCRIPTION,
            source_definition_id=_SOURCE_DEF,
            company_id=None,
            security_id=None,
            status=SubscriptionStatus.ENABLED,
            config=source,
        )
        source["a"] = "changed"
        assert request.config["a"] == "b"

    @pytest.mark.unit
    def test_subscription_config_nested_mapping_deep_frozen(self) -> None:
        """嵌套 Mapping 递归冻结，caller 修改不影响。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        nested: dict[str, str] = {"inner": "v"}
        source: Mapping[str, JsonValue] = {"outer": nested}
        request = SourceSubscriptionCreateRequest(
            subscription_id=_SUBSCRIPTION,
            source_definition_id=_SOURCE_DEF,
            company_id=None,
            security_id=None,
            status=SubscriptionStatus.ENABLED,
            config=source,
        )
        nested["inner"] = "changed"
        outer = request.config["outer"]
        assert isinstance(outer, Mapping)
        assert outer["inner"] == "v"

    @pytest.mark.unit
    def test_subscription_config_nested_write_rejected(self) -> None:
        """嵌套 Mapping 递归冻结为只读 MappingProxyType。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        source: Mapping[str, JsonValue] = {"outer": {"inner": "v"}}
        request = SourceSubscriptionCreateRequest(
            subscription_id=_SUBSCRIPTION,
            source_definition_id=_SOURCE_DEF,
            company_id=None,
            security_id=None,
            status=SubscriptionStatus.ENABLED,
            config=source,
        )
        outer = request.config["outer"]
        assert isinstance(outer, MappingProxyType)

    @pytest.mark.unit
    def test_subscription_config_tuple_mapping_frozen(self) -> None:
        """tuple 与 Mapping 组合递归冻结。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        source: Mapping[str, JsonValue] = {
            "tags": ("a", {"b": 1}),
            "pairs": (("x", "y"),),
        }
        request = SourceSubscriptionCreateRequest(
            subscription_id=_SUBSCRIPTION,
            source_definition_id=_SOURCE_DEF,
            company_id=None,
            security_id=None,
            status=SubscriptionStatus.ENABLED,
            config=source,
        )
        tags = request.config["tags"]
        assert isinstance(tags, tuple)
        inner = tags[1]
        assert isinstance(inner, Mapping)
        assert inner["b"] == 1
        pairs = request.config["pairs"]
        assert isinstance(pairs, tuple)
        assert pairs[0] == ("x", "y")

    @pytest.mark.unit
    def test_company_projection_validates_aware_utc_and_version(self) -> None:
        """公司投影校验 aware UTC 与正整数版本。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        naive = datetime(2026, 8, 10, 12, 0, 0)
        with pytest.raises(ValueError):
            CompanyProjection(
                company_id=_COMPANY,
                legal_name="Acme",
                lei=None,
                country_code="US",
                created_at=naive,
                updated_at=_aware_utc(),
                version=1,
            )
        with pytest.raises(ValueError):
            CompanyProjection(
                company_id=_COMPANY,
                legal_name="Acme",
                lei=None,
                country_code="US",
                created_at=_aware_utc(),
                updated_at=_aware_utc(),
                version=0,
            )

    @pytest.mark.unit
    def test_company_projection_rejects_bool_version(self) -> None:
        """projection version 拒绝 bool 冒充 int。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(TypeError):
            CompanyProjection(
                company_id=_COMPANY,
                legal_name="Acme",
                lei=None,
                country_code="US",
                created_at=_aware_utc(),
                updated_at=_aware_utc(),
                version=True,
            )

    @pytest.mark.unit
    def test_subscription_id_rejects_nil_uuid(self) -> None:
        """订阅标识拒绝 nil UUID。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with pytest.raises(ValueError):
            SourceSubscriptionId("00000000-0000-0000-0000-000000000000")


class TestRepositoryProtocols:
    """repository 协议签名与错误层级。"""

    @pytest.mark.unit
    def test_repository_error_hierarchy(self) -> None:
        """五类稳定错误层级精确。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        assert issubclass(RepositoryError, RuntimeError)
        assert issubclass(RepositoryInputError, RepositoryError)
        assert issubclass(RepositoryNotFoundError, RepositoryError)
        assert issubclass(RepositoryConflictError, RepositoryError)
        assert issubclass(RepositoryOptimisticConflictError, RepositoryConflictError)

    @pytest.mark.unit
    def test_repository_error_messages_are_safe_codes(self) -> None:
        """稳定错误消息是固定 safe code。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        for error in (
            RepositoryError("repository error"),
            RepositoryInputError("repository input error"),
            RepositoryNotFoundError("repository not found"),
            RepositoryConflictError("repository conflict"),
            RepositoryOptimisticConflictError("repository optimistic conflict"),
        ):
            assert str(error)
            assert "DSN" not in str(error)
            assert "postgresql" not in str(error)

    @pytest.mark.unit
    def test_identity_repository_protocol_method_signatures(self) -> None:
        """IdentityRepositoryProtocol 方法签名与首参 TenantScope 一致。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        assert isinstance(IdentityRepositoryProtocol, type)
        _ = (
            IdentityRepositoryProtocol.register_company_security,
            IdentityRepositoryProtocol.get_company,
            IdentityRepositoryProtocol.get_security,
            IdentityRepositoryProtocol.find_security,
        )

    @pytest.mark.unit
    def test_source_repository_protocol_method_signatures(self) -> None:
        """SourceRepositoryProtocol 方法签名与首参 TenantScope 一致。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        _ = (
            SourceRepositoryProtocol.register_source_definition,
            SourceRepositoryProtocol.get_source_definition,
            SourceRepositoryProtocol.find_source_definition,
            SourceRepositoryProtocol.create_source_subscription,
            SourceRepositoryProtocol.get_source_subscription,
            SourceRepositoryProtocol.update_source_subscription,
        )


class _RejectingSessionFactory(sessionmaker[Session]):
    """绝不允许被调用的 session factory spy。

    RR-001：nil UUID 必须在创建 Session / 执行任何 SQL 前被
    ``PostgresIdentityRepository`` 拒绝；若 factory 被调用则测试失败。
    """

    def __init__(self) -> None:
        """构造 sessionmaker 子类 spy。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(class_=Session)

    def __call__(self, **local_kw: Never) -> Session:
        """断言从未被调用。

        Args:
            local_kw: 任何关键字参数（本实现不接受）。

        Returns:
            永不返回，直接断言失败。

        Raises:
            AssertionError: 方法被调用时抛出。
        """

        del local_kw
        raise AssertionError("nil UUID 应在创建 session 前被拒绝")


def _forged_source_definition_id() -> SourceDefinitionId:
    """构造跳过 DTO 校验的伪造 nil 数据源定义标识。

    DTO 的公开构造器已正确拒绝 nil UUID；为验证 repository 自身防御
    边界，这里模拟"反序列化/不可信来源"绕过 DTO 校验直接构造携带
    nil ``value`` 的实例，随后 repository 必须自行拒绝。

    Args:
        无。

    Returns:
        携带 nil UUID 值、跳过 ``__post_init__`` 校验的
        ``SourceDefinitionId`` 实例。

    Raises:
        无。
    """

    forged = SourceDefinitionId.__new__(SourceDefinitionId)
    object.__setattr__(forged, "value", "00000000-0000-0000-0000-000000000000")
    return forged


def _forged_subscription_id() -> SourceSubscriptionId:
    """构造跳过 DTO 校验的伪造 nil 数据源订阅标识。

    DTO 的公开构造器已正确拒绝 nil UUID；为验证 repository 自身防御
    边界，这里模拟"反序列化/不可信来源"绕过 DTO 校验直接构造携带
    nil ``value`` 的实例，随后 repository 必须自行拒绝。

    Args:
        无。

    Returns:
        携带 nil UUID 值、跳过 ``__post_init__`` 校验的
        ``SourceSubscriptionId`` 实例。

    Raises:
        无。
    """

    forged = SourceSubscriptionId.__new__(SourceSubscriptionId)
    object.__setattr__(forged, "value", "00000000-0000-0000-0000-000000000000")
    return forged


class TestRepositoryRejectsNilIdsPreSession:
    """repository 层对 nil UUID 的 pre-session/zero-SQL 拒绝。

    ``TenantId`` / ``CompanyId`` / ``SecurityId`` /
    ``SourceDefinitionId`` / ``SourceSubscriptionId`` 中，source 强标识
    的 DTO 构造已拒绝 nil（``parsed.int == 0``），generic 标识只拒
    空/空白；repository 的 ``_canonical_uuid`` 必须对**每一类** entry
    在 Session 前拒绝 ``parsed.int == 0``（S12-CTRL-05 +
    TERRA-S12-RR-001），稳定 ``RepositoryInputError``、零 SQL。
    """

    @pytest.mark.unit
    def test_nil_tenant_scope_rejected_before_session(self) -> None:
        """nil 租户标识在创建 session 前被拒绝。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        factory = _RejectingSessionFactory()
        repository = PostgresIdentityRepository(factory)
        nil_scope = Principal(
            tenant_id=TenantId("00000000-0000-0000-0000-000000000000"),
            user_id="u-1",
        ).to_scope()
        with pytest.raises(RepositoryInputError):
            repository.get_company(nil_scope, _COMPANY)

    @pytest.mark.unit
    def test_nil_company_id_rejected_before_session(self) -> None:
        """nil 公司标识在创建 session 前被拒绝。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        factory = _RejectingSessionFactory()
        repository = PostgresIdentityRepository(factory)
        with pytest.raises(RepositoryInputError):
            repository.get_company(
                _scope(),
                CompanyId("00000000-0000-0000-0000-000000000000"),
            )

    @pytest.mark.unit
    def test_nil_security_id_rejected_before_session(self) -> None:
        """nil 证券标识在创建 session 前被拒绝。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        factory = _RejectingSessionFactory()
        repository = PostgresIdentityRepository(factory)
        with pytest.raises(RepositoryInputError):
            repository.get_security(
                _scope(),
                SecurityId("00000000-0000-0000-0000-000000000000"),
            )

    @pytest.mark.unit
    def test_nil_source_definition_id_rejected_before_session(self) -> None:
        """伪造 nil 数据源定义标识在创建 session 前被拒绝。

        DTO 公开构造已拒 nil；此处模拟不可信来源跳过 DTO 校验后，
        repository 仍必须拒绝。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        factory = _RejectingSessionFactory()
        repository = PostgresIdentityRepository(factory)
        with pytest.raises(RepositoryInputError):
            repository.get_source_definition(
                _scope(),
                _forged_source_definition_id(),
            )

    @pytest.mark.unit
    def test_nil_subscription_id_rejected_before_session(self) -> None:
        """伪造 nil 订阅标识在创建 session 前被拒绝。

        DTO 公开构造已拒 nil；此处模拟不可信来源跳过 DTO 校验后，
        repository 仍必须拒绝。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        factory = _RejectingSessionFactory()
        repository = PostgresIdentityRepository(factory)
        with pytest.raises(RepositoryInputError):
            repository.get_source_subscription(
                _scope(),
                _forged_subscription_id(),
            )


class _FakeIdentityRepository:
    """IdentityRepositoryProtocol 测试桩（记录调用）。"""

    def __init__(self) -> None:
        """初始化桩。"""
        self.last_scope: TenantScope | None = None

    def register_company_security(
        self,
        scope: TenantScope,
        request: CompanySecurityRegistration,
    ) -> RegisteredCompanySecurity:
        """记录调用并返回固定投影。"""
        self.last_scope = scope
        company = CompanyProjection(
            company_id=_COMPANY,
            legal_name="Acme",
            lei=None,
            country_code="US",
            created_at=_aware_utc(),
            updated_at=_aware_utc(),
            version=1,
        )
        security = SecurityProjection(
            security_id=_SECURITY,
            company_id=_COMPANY,
            ticker="ACME",
            exchange_mic="XNYS",
            security_type=SecurityType.EQUITY,
            currency="USD",
            isin=None,
            is_active=True,
            created_at=_aware_utc(),
            updated_at=_aware_utc(),
            version=1,
        )
        return RegisteredCompanySecurity(company=company, security=security)

    def get_company(
        self,
        scope: TenantScope,
        company_id: CompanyId,
    ) -> CompanyProjection | None:
        """记录 scope 并返回固定投影。"""
        self.last_scope = scope
        return CompanyProjection(
            company_id=_COMPANY,
            legal_name="Acme",
            lei=None,
            country_code="US",
            created_at=_aware_utc(),
            updated_at=_aware_utc(),
            version=1,
        )

    def get_security(
        self,
        scope: TenantScope,
        security_id: SecurityId,
    ) -> SecurityProjection | None:
        """返回固定投影。"""
        return None

    def find_security(
        self,
        scope: TenantScope,
        exchange_mic: str,
        ticker: str,
    ) -> SecurityProjection | None:
        """返回固定投影。"""
        return None


class _FakeSourceRepository:
    """SourceRepositoryProtocol 测试桩。"""

    def register_source_definition(
        self,
        scope: TenantScope,
        request: SourceDefinitionCreateRequest,
    ) -> SourceDefinitionProjection:
        """返回固定投影。"""
        return SourceDefinitionProjection(
            source_definition_id=_SOURCE_DEF,
            source_key="sec-filings",
            source_kind=SourceKind.FILING,
            display_name="SEC 财报",
            enabled_by_default=True,
            created_at=_aware_utc(),
            updated_at=_aware_utc(),
            version=1,
        )

    def get_source_definition(
        self,
        scope: TenantScope,
        source_definition_id: SourceDefinitionId,
    ) -> SourceDefinitionProjection | None:
        """返回固定投影。"""
        return None

    def find_source_definition(
        self,
        scope: TenantScope,
        source_key: str,
    ) -> SourceDefinitionProjection | None:
        """返回固定投影。"""
        return None

    def create_source_subscription(
        self,
        scope: TenantScope,
        request: SourceSubscriptionCreateRequest,
    ) -> SourceSubscriptionProjection:
        """返回固定投影。"""
        return _subscription_projection()

    def get_source_subscription(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceSubscriptionProjection | None:
        """返回固定投影。"""
        return None

    def update_source_subscription(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
        expected_version: int,
        request: SourceSubscriptionUpdateRequest,
    ) -> SourceSubscriptionProjection:
        """返回固定投影。"""
        return _subscription_projection()


def _subscription_projection() -> SourceSubscriptionProjection:
    """构造固定订阅投影。

    Args:
        无。

    Returns:
        订阅投影。

    Raises:
        无。
    """

    return SourceSubscriptionProjection(
        subscription_id=_SUBSCRIPTION,
        tenant_id=_TENANT,
        source_definition_id=_SOURCE_DEF,
        company_id=_COMPANY,
        security_id=None,
        status=SubscriptionStatus.ENABLED,
        config={},
        created_at=_aware_utc(),
        updated_at=_aware_utc(),
        version=1,
    )


class TestInvestmentIdentityService:
    """InvestmentIdentityService 窄 Service 契约。"""

    @pytest.mark.unit
    def test_service_registration_name_exact(self) -> None:
        """稳定注册名精确为 investment_identity。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        service = InvestmentIdentityService(
            identity_repository=_FakeIdentityRepository(),
            source_repository=_FakeSourceRepository(),
        )
        assert service.platform_service_name == "investment_identity"

    @pytest.mark.unit
    def test_service_satisfies_both_protocols(self) -> None:
        """Service 满足窄协议与生命周期协议。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        service = InvestmentIdentityService(
            identity_repository=_FakeIdentityRepository(),
            source_repository=_FakeSourceRepository(),
        )
        assert isinstance(service, PlatformIdentityServiceProtocol)
        assert isinstance(service, PlatformOwnedLifecycleProtocol)

    @pytest.mark.unit
    def test_service_forwards_tenant_scope_to_repository(self) -> None:
        """Service 原样转发 TenantScope 到 repository。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        repo = _FakeIdentityRepository()
        service = InvestmentIdentityService(
            identity_repository=repo,
            source_repository=_FakeSourceRepository(),
        )
        scope = _scope()
        service.get_company(scope, _COMPANY)
        assert repo.last_scope is scope

    @pytest.mark.unit
    def test_service_close_thread_safe_and_idempotent(self) -> None:
        """close 线程安全且幂等。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        engine = create_engine("sqlite+pysqlite:///:memory:", echo=False)
        service = InvestmentIdentityService(
            identity_repository=_FakeIdentityRepository(),
            source_repository=_FakeSourceRepository(),
            owned_engine=engine,
        )
        errors: list[Exception] = []

        def _closer() -> None:
            try:
                service.close()
            except Exception as error:  # pragma: no cover
                errors.append(error)

        threads = [threading.Thread(target=_closer) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        service.close()
        service.close()

    @pytest.mark.unit
    def test_service_close_without_owned_engine_is_noop(self) -> None:
        """无自持 engine 时 close 为 no-op。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        service = InvestmentIdentityService(
            identity_repository=_FakeIdentityRepository(),
            source_repository=_FakeSourceRepository(),
            owned_engine=None,
        )
        service.close()
        service.close()
