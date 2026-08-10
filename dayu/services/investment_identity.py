"""投资平台 identity/source 窄 Service 实现。

本模块是 ``PlatformIdentityServiceProtocol`` 的窄具体实现 owner
（S12-CTRL-02）：

- 只编排 ``IdentityRepositoryProtocol`` 与 ``SourceRepositoryProtocol``，
  原样要求调用方传入 ``TenantScope``；
- 不 import ORM model、engine/session，不生成或猜测 tenant；
- ``close()`` 线程安全且幂等，只释放自持 engine（auto-created 场景），
  不删除/修改业务数据。

设计约束：

- Service 层位于 ``dayu.services``，依赖 storage 协议与 domain，
  不反向依赖 Web/Host/Agent；
- 稳定注册名只读且精确为 ``investment_identity``。
"""

from __future__ import annotations

import threading

from sqlalchemy.engine import Engine

from dayu.investment.composition import (
    PlatformIdentityServiceProtocol,
    PlatformOwnedLifecycleProtocol,
)
from dayu.investment.domain.identifiers import (
    CompanyId,
    SecurityId,
    TenantScope,
)
from dayu.investment.domain.source import (
    CompanyProjection,
    CompanySecurityRegistration,
    RegisteredCompanySecurity,
    SecurityProjection,
    SourceDefinitionCreateRequest,
    SourceDefinitionId,
    SourceDefinitionProjection,
    SourceSubscriptionCreateRequest,
    SourceSubscriptionId,
    SourceSubscriptionProjection,
    SourceSubscriptionUpdateRequest,
)
from dayu.investment.storage.protocols import (
    IdentityRepositoryProtocol,
    SourceRepositoryProtocol,
)

_INVESTMENT_IDENTITY_SERVICE_NAME = "investment_identity"
"""窄 identity/source Service 的稳定注册名。"""


class InvestmentIdentityService(PlatformIdentityServiceProtocol, PlatformOwnedLifecycleProtocol):
    """投资平台 identity/source 窄 Service 实现。

    只编排两个 repository protocol；``close()`` 线程安全且幂等，只释放
    自持 engine（auto-created provider 场景），显式注入的 repository
    engine 由调用方持有、不关闭。

    Args:
        identity_repository: identity repository 实现。
        source_repository: source repository 实现。
        owned_engine: 自持 engine（auto-created 场景）；由调用方传入
            的 engine 不应传给本参数。
    """

    def __init__(
        self,
        identity_repository: IdentityRepositoryProtocol,
        source_repository: SourceRepositoryProtocol,
        owned_engine: Engine | None = None,
    ) -> None:
        """初始化窄 Service。

        Args:
            identity_repository: identity repository 实现。
            source_repository: source repository 实现。
            owned_engine: 自持 engine；为 ``None`` 表示 engine 由调用方
                own（显式 provider 场景），``close()`` 不触碰。

        Returns:
            无。

        Raises:
            无。
        """

        self._identity_repository = identity_repository
        self._source_repository = source_repository
        self._owned_engine = owned_engine
        self._close_lock = threading.Lock()
        self._closed = False

    @property
    def platform_service_name(self) -> str:
        """返回稳定注册名。

        Args:
            无。

        Returns:
            精确为 ``investment_identity``。

        Raises:
            无。
        """

        return _INVESTMENT_IDENTITY_SERVICE_NAME

    def register_company_security(
        self,
        scope: TenantScope,
        request: CompanySecurityRegistration,
    ) -> RegisteredCompanySecurity:
        """原子注册公司+证券。

        Args:
            scope: 租户范围。
            request: 公司+证券注册请求。

        Returns:
            注册结果投影。

        Raises:
            RepositoryError: 稳定错误层级。
        """

        return self._identity_repository.register_company_security(scope, request)

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
            RepositoryError: 稳定错误层级。
        """

        return self._identity_repository.get_company(scope, company_id)

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
            RepositoryError: 稳定错误层级。
        """

        return self._identity_repository.get_security(scope, security_id)

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
            RepositoryError: 稳定错误层级。
        """

        return self._identity_repository.find_security(scope, exchange_mic, ticker)

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
            RepositoryError: 稳定错误层级。
        """

        return self._source_repository.register_source_definition(scope, request)

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
            RepositoryError: 稳定错误层级。
        """

        return self._source_repository.get_source_definition(scope, source_definition_id)

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
            RepositoryError: 稳定错误层级。
        """

        return self._source_repository.find_source_definition(scope, source_key)

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
            RepositoryError: 稳定错误层级。
        """

        return self._source_repository.create_source_subscription(scope, request)

    def get_source_subscription(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceSubscriptionProjection | None:
        """按 id 读取订阅。

        Args:
            scope: 租户范围。
            subscription_id: 订阅标识。

        Returns:
            订阅投影或 ``None``。

        Raises:
            RepositoryError: 稳定错误层级。
        """

        return self._source_repository.get_source_subscription(scope, subscription_id)

    def update_source_subscription(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
        expected_version: int,
        request: SourceSubscriptionUpdateRequest,
    ) -> SourceSubscriptionProjection:
        """CAS 更新订阅。

        Args:
            scope: 租户范围。
            subscription_id: 订阅标识。
            expected_version: 期望版本（正整数）。
            request: 订阅更新请求。

        Returns:
            更新后的订阅投影。

        Raises:
            RepositoryError: 稳定错误层级。
        """

        return self._source_repository.update_source_subscription(
            scope,
            subscription_id,
            expected_version,
            request,
        )

    def close(self) -> None:
        """释放自持 engine（线程安全且幂等）。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            if self._owned_engine is not None:
                self._owned_engine.dispose()


__all__ = [
    "InvestmentIdentityService",
]
