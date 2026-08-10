"""投资域子包导出。

本包集中导出投资域的纯领域基元：

- 强标识与主体/租户范围（``identifiers`` 模块）
- 金额、数量与 UTC 时间工具（``money`` 模块）

对外只暴露本包自身的稳定符号，禁止把上层包（Web/Service/Host/Agent）
或 ORM 类型泄漏到 domain 之外。
"""

from .identifiers import (
    AccountId,
    CompanyId,
    PortfolioId,
    Principal,
    SecurityId,
    TenantId,
    TenantScope,
    make_account_id,
    make_company_id,
    make_portfolio_id,
    make_security_id,
    make_tenant_id,
)
from .money import Money, Quantity, parse_utc, to_utc_iso, utc_now

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
