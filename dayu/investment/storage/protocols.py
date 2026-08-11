"""投资平台 repository 协议与稳定错误。

本模块是 Slice 1.2 的 repository 契约真源（S12-CTRL-01/05），定义：

- 五类稳定错误层级：``RepositoryError`` 及其
  ``RepositoryInputError`` / ``RepositoryNotFoundError`` /
  ``RepositoryConflictError`` / ``RepositoryOptimisticConflictError``；
- ``IdentityRepositoryProtocol``：公司+证券原子注册、按 id 读取与
  ``(exchange_mic, ticker)`` 查找；
- ``SourceRepositoryProtocol``：数据源定义注册/读取/查找与订阅
  创建/读取/CAS 更新；
- ``WorkspaceImportRepositoryProtocol``（S15-CTRL-09）：workspace
  import 唯一单事务发布（advisory xact lock + marker + public
  reconcile + locator + completed marker）。

设计约束：

- 本模块位于 ``storage``（SQL implementation 层），只依赖 pure domain
  与标准库；每个公开方法首参显式为 ``TenantScope``；
- 稳定错误消息是固定 safe code，不含 DSN/SQL/候选值；
- 协议不暴露 ORM row、SQLAlchemy 类型或 ``Any``/``object``。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from dayu.investment.domain.identifiers import CompanyId, SecurityId, TenantScope
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
from dayu.investment.domain.workspace_import import (
    WorkspaceImportReceipt,
    WorkspaceImportRequest,
)


class RepositoryError(RuntimeError):
    """repository 操作失败的稳定基类。

    消息只含固定 safe code，绝不包含 DSN、SQL、候选值或 credential。
    """


class RepositoryInputError(RepositoryError):
    """repository 输入非法时抛出的错误。

    在创建/checkout Session 前由 DTO/repository boundary 校验触发；
    不得执行 SQL，也不得传播 psycopg/SQLAlchemy 的类型转换错误。
    """


class RepositoryNotFoundError(RepositoryError):
    """目标租户内 row 不存在时抛出的错误。

    跨租户访问同样表现为 not-found，不泄漏目标存在性。
    """


class RepositoryConflictError(RepositoryError):
    """唯一键或业务键冲突时抛出的错误。"""


class RepositoryOptimisticConflictError(RepositoryConflictError):
    """CAS 更新时 ``expected_version`` 与当前版本不一致抛出的错误。"""


@runtime_checkable
class IdentityRepositoryProtocol(Protocol):
    """identity（公司/证券）repository 契约。"""

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
            RepositoryInputError: 输入非法时抛出。
            RepositoryConflictError: 唯一键冲突时抛出。
        """
        ...

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
        """
        ...

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
        """
        ...

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
        """
        ...


@runtime_checkable
class SourceRepositoryProtocol(Protocol):
    """source（数据源定义/订阅）repository 契约。"""

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
        ...

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
        """
        ...

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
        """
        ...

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
        ...

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
        """
        ...

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
        ...


@runtime_checkable
class WorkspaceImportRepositoryProtocol(Protocol):
    """旧 workspace 显式导入 repository 契约（S15-CTRL-09）。

    ``publish_import`` 是唯一 DB transaction owner：每次调用只建一个
    session，``SET LOCAL app.tenant_id`` 后在同一 transaction 内完成
    advisory xact lock、marker read、public reference reconcile、
    source definition reconcile、locator inserts 与 completed marker。
    已有 marker 且全部 intended rows exact 时返回 ``no_op``；任何字段
    或 row drift 抛稳定 drift 错误。
    """

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
            WorkspaceImportSchemaUnavailableError: 0002 schema 不可用时
                抛出。
            WorkspaceImportDriftError: marker/row 与 intended projection
                不一致时抛出。
            WorkspaceImportRepositoryFailureError: 数据库失败时抛出。
        """
        ...


__all__ = [
    "IdentityRepositoryProtocol",
    "RepositoryConflictError",
    "RepositoryError",
    "RepositoryInputError",
    "RepositoryNotFoundError",
    "RepositoryOptimisticConflictError",
    "SourceRepositoryProtocol",
    "WorkspaceImportRepositoryProtocol",
]
