"""投资平台 workspace import 窄 Service 实现（S15-CTRL-10）。

本模块是 ``PlatformWorkspaceImportServiceProtocol`` 的窄具体实现
owner：

- 只编排 ``WorkspaceImportRepositoryProtocol``，原样要求调用方传入
  ``TenantScope``，并再次校验 ``scope.tenant_id`` 精确等于
  ``DEFAULT_ORGANIZATION_ID``；
- 不 import ORM model、engine/session，不生成或猜测 tenant；
- ``close()`` 线程安全且幂等，只释放自持 engine（one-shot import
  mode 场景），不删除/修改业务数据。

设计约束：

- Service 层位于 ``dayu.services``，依赖 storage 协议与 domain，
  不反向依赖 Web/Host/Agent；
- 稳定注册名只读且精确为 ``workspace_import``；
- 这是 Slice 7 auth 之前的 bootstrap maintenance boundary，不是认证：
  CLI 只用固定 default scope，marker 不宣称用户身份。
"""

from __future__ import annotations

import threading

from sqlalchemy.engine import Engine

from dayu.investment.composition import (
    PlatformOwnedLifecycleProtocol,
    PlatformWorkspaceImportServiceProtocol,
)
from dayu.investment.domain.identifiers import TenantId, TenantScope
from dayu.investment.domain.workspace_import import (
    WorkspaceImportReceipt,
    WorkspaceImportRequest,
    WorkspaceImportUsageError,
)
from dayu.investment.storage.db import DEFAULT_ORGANIZATION_ID
from dayu.investment.storage.protocols import WorkspaceImportRepositoryProtocol

_WORKSPACE_IMPORT_SERVICE_NAME = "workspace_import"
"""workspace import 窄 Service 的稳定注册名。"""


class WorkspaceImportService(PlatformWorkspaceImportServiceProtocol, PlatformOwnedLifecycleProtocol):
    """投资平台 workspace import 窄 Service 实现。

    只编排 workspace import repository；``close()`` 线程安全且幂等，
    只释放自持 engine（one-shot import 场景），显式注入的 repository
    engine 由调用方持有、不关闭。

    Args:
        import_repository: workspace import repository 实现。
        owned_engine: 自持 engine（one-shot 场景）；由调用方传入的
            engine 不应传给本参数。
    """

    def __init__(
        self,
        import_repository: WorkspaceImportRepositoryProtocol,
        owned_engine: Engine | None = None,
    ) -> None:
        """初始化窄 Service。

        Args:
            import_repository: workspace import repository 实现。
            owned_engine: 自持 engine；为 ``None`` 表示 engine 由调用方
                own，``close()`` 不触碰。

        Returns:
            无。

        Raises:
            无。
        """

        self._import_repository = import_repository
        self._owned_engine = owned_engine
        self._close_lock = threading.Lock()
        self._closed = False

    @property
    def platform_service_name(self) -> str:
        """返回稳定注册名。

        Args:
            无。

        Returns:
            精确为 ``workspace_import``。

        Raises:
            无。
        """

        return _WORKSPACE_IMPORT_SERVICE_NAME

    def import_workspace(
        self,
        scope: TenantScope,
        request: WorkspaceImportRequest,
    ) -> WorkspaceImportReceipt:
        """以固定 default scope 发布一次 workspace import。

        Args:
            scope: 租户范围。
            request: 已 fingerprint 的纯 import 请求。

        Returns:
            纯结果收据。

        Raises:
            WorkspaceImportUsageError: 租户不是 default organization 时
                抛出。
            WorkspaceImportError: 稳定错误层级。
        """

        if scope.tenant_id != TenantId(DEFAULT_ORGANIZATION_ID):
            raise WorkspaceImportUsageError()
        return self._import_repository.publish_import(scope, request)

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
    "WorkspaceImportService",
]
