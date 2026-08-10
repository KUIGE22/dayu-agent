# Investment 投资域开发手册

`dayu.investment` 是投资平台（公司研究、组合、决策与执行）的落地包。
本文档只写当前实现：依赖方向、模块 owner 与开发命令。

## 1. 依赖方向

投资包是 `UI -> Service -> Host -> Agent` 分层之外的纯领域包，位于依赖
方向的底部：

```text
dayu.investment.domain   纯 domain 契约（当前）
```

硬约束：

- `dayu.investment.domain` 不依赖 Web、Service、Host、Agent、
  SQLAlchemy、pydantic 或任何 Broker SDK。
- 投资域不读取 `workspace/portfolio/...` 私有文件；财报与研究材料存取
  只能经 `dayu.fins.storage` 协议（既有 owner）。
- 依赖方向由 `tests/investment/test_architecture_boundaries.py` 的
  AST guard 守护：它只枚举 `dayu.investment` 包内的 Python 文件，
  断言这些文件不导入上层包；它不扫描 `dayu.investment` 以外的模块，
  因此不构成对跨包反向 import 的检查。

## 2. 模块 owner

当前（Slice 0.1）只存在纯 domain 骨架，不实现业务行为：

| 模块 | 职责 |
| --- | --- |
| `dayu/investment/__init__.py` | 包导出层，转发 domain 公开符号 |
| `dayu/investment/domain/__init__.py` | domain 子包导出层 |
| `dayu/investment/domain/identifiers.py` | `TenantId/CompanyId/SecurityId/PortfolioId/AccountId` 强标识、`Principal`、`TenantScope` |
| `dayu/investment/domain/money.py` | `Money`、`Quantity` 值对象与 UTC 时间工具 |

### 2.1 标识与租户范围

- 五个标识均为 frozen slots 运行时值对象；直接构造与 `make_*` 工厂
  执行同样的严格校验，空值、仅空白或首尾空白一律拒绝。
- `Principal` 是操作主体（租户 + 用户），当前为公开构造器；认证层
  作为 `Principal` 的唯一 producer 属于后续授权 slice。`TenantScope`
  禁止公开直接构造，只能由 `Principal.to_scope()` 派生；模块私有
  哨兵仅是公开 API misuse guard，不是认证能力。
- `TenantScope` 是租户边界契约的载体，禁止从全局状态或业务字段
  推断租户。

### 2.2 金额与数量

- `Money` 由有限非负 `Decimal` 与三位大写货币代码组成；`Quantity` 由
  有限非负 `Decimal` 组成，禁止 `float`。
- `NaN` / `Infinity` / 负数、`float` / `bool` / `int` 输入一律 fail
  closed（`TypeError` / `ValueError`）。
- 金额加减与比较要求两侧货币相同，否则 fail closed。
- 本模块只提供值对象语义；当前模块不实现账本分录或费用分摊规则。

### 2.3 UTC 时间工具

`utc_now()` / `parse_utc()` / `to_utc_iso()` 统一走 UTC 时区；输入必须
携带有效 UTC 偏移（`tzinfo` 与 `utcoffset()` 均非 `None`），否则拒绝。

## 3. 测试与验证

```bash
source .venv/bin/activate
python -m pytest tests/investment -q
python -m pytest tests/investment --cov=dayu.investment --cov-report=term-missing
pyright dayu/investment tests/investment
ruff check --select E4,E7,E9,F,I dayu/investment tests/investment
```

`tests/investment/test_architecture_boundaries.py` 以 AST 守护
`dayu.investment` 生产代码的依赖方向、逃逸模式
（`Any/object/cast/type: ignore/getattr/hasattr`）与中文 docstring
完整性；测试文件自身同样遵守根 `AGENTS.md` 的同类约束。
