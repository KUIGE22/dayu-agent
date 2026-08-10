"""投资平台包。

``dayu.investment`` 是投资域（公司研究、组合、决策与执行）的落地包，
遵循 ``UI -> Service -> Host -> Agent`` 分层中的独立纯域定位：

- ``dayu.investment.domain`` 是纯领域层，不依赖 Web、Service、Host、
  Agent、SQLAlchemy 或任何 Broker SDK。

当前版本（Slice 0.1）只包含 domain 骨架：强标识、主体与租户范围、
金额/数量值对象与 UTC 时间工具。
"""

from .domain import (
    AccountId,
    CompanyId,
    Money,
    PortfolioId,
    Principal,
    Quantity,
    SecurityId,
    TenantId,
    TenantScope,
    make_account_id,
    make_company_id,
    make_portfolio_id,
    make_security_id,
    make_tenant_id,
    parse_utc,
    to_utc_iso,
    utc_now,
)

__all__ = [
    "AccountId",
    "CompanyId",
    "Money",
    "PortfolioId",
    "Principal",
    "Quantity",
    "SecurityId",
    "TenantId",
    "TenantScope",
    "make_account_id",
    "make_company_id",
    "make_portfolio_id",
    "make_security_id",
    "make_tenant_id",
    "parse_utc",
    "to_utc_iso",
    "utc_now",
]
