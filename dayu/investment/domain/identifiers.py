"""投资域身份标识、主体与租户范围。

本模块集中定义投资域的身份基元：

- 五个强类型标识：``TenantId`` / ``CompanyId`` / ``SecurityId`` /
  ``PortfolioId`` / ``AccountId``，均为 frozen slots 运行时值对象，
  直接构造与 ``make_*`` 工厂执行同样的严格校验；
- 主体 ``Principal`` 与由它派生的租户范围 ``TenantScope``。

设计约束：

- 所有标识在构造时拒绝空值、仅空白或首尾空白，fail closed；
- 租户范围 ``TenantScope`` 禁止公开直接构造，只能经
  ``Principal.to_scope()`` 派生，禁止调用链自行猜测租户；
- ``TenantScope`` 的模块私有哨兵仅是公开 API misuse guard，不是
  认证能力；真正的 ``Principal`` 唯一 producer 与 repository/RLS
  的租户边界实施属于对应后续授权 slice；
- 本模块不依赖任何上层包、ORM 或 Web 框架。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


def _validate_identifier(value: str, label: str) -> str:
    """校验标识字符串非空且无首尾空白。

    Args:
        value: 待校验的标识原始字符串。
        label: 用于错误消息的中文标识名称。

    Returns:
        校验通过的原始字符串（不修改输入）。

    Raises:
        ValueError: ``value`` 为空、仅空白或含首尾空白时抛出。
    """

    if not value:
        raise ValueError(f"{label}不能为空")
    if value != value.strip():
        raise ValueError(f"{label}不能包含首尾空白")
    return value


@dataclass(frozen=True, slots=True)
class _Identifier:
    """强标识的公共不可变基类。

    承载唯一 ``value`` 槽位与构造期严格校验；五个公开标识
    （``TenantId`` 等）只需声明各自的 ``_label`` 名称。
    """

    _label: ClassVar[str] = "标识"
    value: str

    def __post_init__(self) -> None:
        """构造期校验标识字符串。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 标识为空、仅空白或含首尾空白时抛出。
        """

        _validate_identifier(self.value, self._label)

    def __str__(self) -> str:
        """返回标识的原始字符串。

        Args:
            无。

        Returns:
            标识原始字符串（不带类型前缀）。

        Raises:
            无。
        """

        return self.value


@dataclass(frozen=True, slots=True)
class TenantId(_Identifier):
    """租户标识：标识一个组织/租户的业务边界。"""

    _label: ClassVar[str] = "租户标识"


@dataclass(frozen=True, slots=True)
class CompanyId(_Identifier):
    """公司标识：标识一家被研究公司。"""

    _label: ClassVar[str] = "公司标识"


@dataclass(frozen=True, slots=True)
class SecurityId(_Identifier):
    """证券标识：标识一只可交易的证券。"""

    _label: ClassVar[str] = "证券标识"


@dataclass(frozen=True, slots=True)
class PortfolioId(_Identifier):
    """组合标识：标识一个投资组合。"""

    _label: ClassVar[str] = "组合标识"


@dataclass(frozen=True, slots=True)
class AccountId(_Identifier):
    """账户标识：标识一个资金/交易账户。"""

    _label: ClassVar[str] = "账户标识"


def make_tenant_id(value: str) -> TenantId:
    """构造租户标识。

    Args:
        value: 租户标识原始字符串。

    Returns:
        校验通过的 ``TenantId``。

    Raises:
        ValueError: 输入为空、仅空白或含首尾空白时抛出。
    """

    return TenantId(value)


def make_company_id(value: str) -> CompanyId:
    """构造公司标识。

    Args:
        value: 公司标识原始字符串。

    Returns:
        校验通过的 ``CompanyId``。

    Raises:
        ValueError: 输入为空、仅空白或含首尾空白时抛出。
    """

    return CompanyId(value)


def make_security_id(value: str) -> SecurityId:
    """构造证券标识。

    Args:
        value: 证券标识原始字符串。

    Returns:
        校验通过的 ``SecurityId``。

    Raises:
        ValueError: 输入为空、仅空白或含首尾空白时抛出。
    """

    return SecurityId(value)


def make_portfolio_id(value: str) -> PortfolioId:
    """构造组合标识。

    Args:
        value: 组合标识原始字符串。

    Returns:
        校验通过的 ``PortfolioId``。

    Raises:
        ValueError: 输入为空、仅空白或含首尾空白时抛出。
    """

    return PortfolioId(value)


def make_account_id(value: str) -> AccountId:
    """构造账户标识。

    Args:
        value: 账户标识原始字符串。

    Returns:
        校验通过的 ``AccountId``。

    Raises:
        ValueError: 输入为空、仅空白或含首尾空白时抛出。
    """

    return AccountId(value)


@dataclass(frozen=True, slots=True)
class Principal:
    """操作主体。

    代表一次操作的主体，持有其所属租户与用户标识；租户范围通过
    :meth:`to_scope` 派生，禁止在调用链中自行猜测租户。

    本模块不实现认证：``Principal`` 当前是公开构造器，认证层作为
    ``Principal`` 的唯一 producer 属于后续授权 slice。
    """

    tenant_id: TenantId
    user_id: str

    def __post_init__(self) -> None:
        """构造期校验主体字段。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: ``tenant_id`` 不是 ``TenantId`` 实例时抛出。
            ValueError: 用户标识为空、仅空白或含首尾空白时抛出。
        """

        if not isinstance(self.tenant_id, TenantId):
            raise TypeError("租户标识必须是 TenantId 实例，禁止使用原始字符串")
        _validate_identifier(self.user_id, "用户标识")

    def to_scope(self) -> TenantScope:
        """从主体派生本次请求的租户范围。

        Args:
            无。

        Returns:
            与主体租户一致的 ``TenantScope``。

        Raises:
            无。
        """

        return _make_tenant_scope(self.tenant_id)


class _TenantScopeToken:
    """租户范围构造哨兵类型（模块私有）。

    仅模块私有单例 ``_TENANT_SCOPE_TOKEN`` 能通过 ``TenantScope``
    受控 ``__init__`` 的身份校验；本哨兵仅是公开 API misuse guard，
    不是认证能力。同一进程内的调用方仍可解析并传入该单例，因此它
    不能证明唯一生产者或认证 provenance；``Principal`` 的唯一
    producer 与 repository/RLS 的租户边界实施属于后续授权 slice。
    """

    __slots__ = ()


_TENANT_SCOPE_TOKEN = _TenantScopeToken()
"""租户范围构造哨兵单例（模块私有，仅 ``_make_tenant_scope`` 使用）。"""


@dataclass(frozen=True, slots=True, init=False)
class TenantScope:
    """租户范围。

    标识一次请求/操作所属的租户边界；公开直接构造一律失败，只能经
    :meth:`Principal.to_scope` 派生；创建后禁止任何属性改写（frozen
    dataclass 只读 ``__setattr__``）。仓储的每个读、写、搜索方法都
    必须显式接收本类型，禁止从全局状态或业务字段推断租户。
    """

    tenant_id: TenantId

    def __init__(self, tenant_id: TenantId, _token: _TenantScopeToken | None = None) -> None:
        """受控构造租户范围。

        以对象身份（``is``）校验模块私有单例哨兵
        ``_TENANT_SCOPE_TOKEN``，未携带即拒绝；即使携带真实单例，
        ``tenant_id`` 仍必须是 ``TenantId`` 实例，原始字符串一律
        fail closed。哨兵仅是公开 API misuse guard，不是认证能力。

        Args:
            tenant_id: 主体对应的租户标识，必须是 ``TenantId`` 实例。
            _token: 模块私有单例哨兵；为 ``None`` 或不是单例时拒绝构造。

        Returns:
            无（构造结果通过实例返回）。

        Raises:
            TypeError: 未携带模块私有单例哨兵时抛出。
            TypeError: ``tenant_id`` 不是 ``TenantId`` 实例时抛出。
        """

        if _token is not _TENANT_SCOPE_TOKEN:
            raise TypeError("TenantScope 禁止公开构造，只能通过 Principal.to_scope() 创建")
        if not isinstance(tenant_id, TenantId):
            raise TypeError("租户标识必须是 TenantId 实例，禁止使用原始字符串")
        super(TenantScope, self).__setattr__("tenant_id", tenant_id)


def _make_tenant_scope(tenant_id: TenantId) -> TenantScope:
    """创建租户范围（模块私有，仅 ``Principal.to_scope`` 调用）。

    Args:
        tenant_id: 主体对应的租户标识，必须是 ``TenantId`` 实例。

    Returns:
        持有该租户标识的不可变 ``TenantScope``。

    Raises:
        无。
    """

    return TenantScope(tenant_id=tenant_id, _token=_TENANT_SCOPE_TOKEN)


__all__ = [
    "AccountId",
    "CompanyId",
    "PortfolioId",
    "Principal",
    "SecurityId",
    "TenantId",
    "TenantScope",
    "make_account_id",
    "make_company_id",
    "make_portfolio_id",
    "make_security_id",
    "make_tenant_id",
]
