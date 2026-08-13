"""Source Sync 仓储的纯协议边界。

本模块只声明七个同步仓储方法及其纯领域 DTO。PostgreSQL、SQLAlchemy、
Session、Row、Fins 与 Service 均由协议边界之外的具体实现拥有。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from dayu.investment.domain.identifiers import TenantScope
from dayu.investment.domain.source import SourceSubscriptionId
from dayu.investment.domain.source_evidence import SourceSyncAttemptReceipt
from dayu.investment.domain.source_health import (
    SourceHealthProjection,
    SourceHealthReenableRequest,
    SourceHealthSnapshotCursor,
    SourceHealthSnapshotPage,
)
from dayu.investment.domain.source_operation import (
    SourceOperationAcquireDecision,
    SourceOperationAcquireRequest,
    SourceTerminalRecordDecision,
    SourceTerminalRecordRequest,
)
from dayu.investment.domain.source_payload import SourceExecutionBinding


@runtime_checkable
class SourceSyncRepositoryProtocol(Protocol):
    """Source operation、receipt 与 health 的同步持久化协议。"""

    def get_executable_binding(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceExecutionBinding:
        """读取租户内可供 Source Sync 使用的 binding。

        Args:
            scope: 可信租户范围。
            subscription_id: Source subscription 标识。

        Returns:
            严格、纯领域的执行 binding。

        Raises:
            SourceSyncRequestRejected: 输入、缺失或不可执行时抛出。
            SourceSyncRepositoryFailure: 数据库或持久化不变量失败时抛出。
        """
        ...

    def acquire_operation(
        self,
        scope: TenantScope,
        request: SourceOperationAcquireRequest,
    ) -> SourceOperationAcquireDecision:
        """取得、复用或重放一个 Source operation。

        Args:
            scope: 可信租户范围。
            request: Acquire 请求。

        Returns:
            Acquired、busy 或 terminal replay 决策。

        Raises:
            SourceSyncRequestRejected: 请求或持久化 lineage 不匹配时抛出。
            SourceSyncExecutionRejected: Job/lease 已不可执行时抛出。
            SourceSyncRepositoryFailure: 数据库或持久化不变量失败时抛出。
        """
        ...

    def record_terminal(
        self,
        scope: TenantScope,
        request: SourceTerminalRecordRequest,
    ) -> SourceTerminalRecordDecision:
        """原子记录 Source run、health、alert 与 operation terminal。

        Args:
            scope: 可信租户范围。
            request: Terminal candidate 请求。

        Returns:
            Recorded、stale 或 live-loss 决策。

        Raises:
            SourceSyncRequestRejected: 请求 lineage 或 snapshot 不匹配时抛出。
            SourceSyncRepositoryFailure: 数据库或持久化不变量失败时抛出。
        """
        ...

    def get_source_receipt(
        self,
        scope: TenantScope,
        source_sync_run_id: UUID,
    ) -> SourceSyncAttemptReceipt | None:
        """读取 v1 Source receipt；missing 与合法 legacy row 返回空。

        Args:
            scope: 可信租户范围。
            source_sync_run_id: Source run UUID。

        Returns:
            严格 receipt；missing、跨租户或合法 legacy row 返回 ``None``。

        Raises:
            SourceSyncRequestRejected: 输入非法时抛出。
            SourceSyncRepositoryFailure: 数据库或持久化不变量失败时抛出。
        """
        ...

    def get_health(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
    ) -> SourceHealthProjection:
        """读取 subscription health head。

        Args:
            scope: 可信租户范围。
            subscription_id: Source subscription 标识。

        Returns:
            持久化 head，或无 head 时的 virtual healthy projection。

        Raises:
            SourceSyncRequestRejected: 输入非法或 subscription 不存在时抛出。
            SourceSyncRepositoryFailure: 数据库或持久化不变量失败时抛出。
        """
        ...

    def list_health_snapshots(
        self,
        scope: TenantScope,
        subscription_id: SourceSubscriptionId,
        cursor: SourceHealthSnapshotCursor | None,
        *,
        limit: int,
    ) -> SourceHealthSnapshotPage:
        """按稳定 descending keyset 列出 health snapshots。

        Args:
            scope: 可信租户范围。
            subscription_id: Source subscription 标识。
            cursor: 可空 keyset cursor。
            limit: 每页数量，范围 1..200。

        Returns:
            Snapshot page。

        Raises:
            SourceSyncRequestRejected: 输入非法或 subscription 不存在时抛出。
            SourceSyncRepositoryFailure: 数据库或持久化不变量失败时抛出。
        """
        ...

    def reenable_health(
        self,
        scope: TenantScope,
        request: SourceHealthReenableRequest,
    ) -> SourceHealthProjection:
        """以 CAS 将 disabled health head 恢复为 healthy。

        Args:
            scope: 可信租户范围。
            request: Re-enable 请求。

        Returns:
            更新后的 health head。

        Raises:
            SourceSyncRequestRejected: 输入、状态或版本冲突时抛出。
            SourceSyncRepositoryFailure: 数据库或持久化不变量失败时抛出。
        """
        ...


__all__ = ["SourceSyncRepositoryProtocol"]
