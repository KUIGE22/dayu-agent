# Investment 投资域开发手册

`dayu.investment` 是投资平台（公司研究、组合、决策与执行）的落地包。
本文档只写当前实现：依赖方向、模块 owner 与开发命令。

## 1. 依赖方向

投资包是 `UI -> Service -> Host -> Agent` 分层之外的纯领域包，位于依赖
方向的底部：

```text
dayu.investment.domain         纯 domain 契约（Slice 0.1）
dayu.investment.config         平台严格设置（只记录环境变量名称）
dayu.investment.composition    平台组合契约（只承载 Service 协议实例的组合根）
```

硬约束：

- `dayu.investment` 全部模块不依赖 Web、Service、Host、Agent、
  SQLAlchemy、pydantic 或任何 Broker SDK。
- `dayu.investment.config` 只做环境变量名称的存在性检查，绝不记录或
  回显 secret 值；非法 env-name 异常只报告字段与固定规则。
- `dayu.investment.composition` 定义 `PlatformServiceProtocol` /
  `PlatformCompositionProviderProtocol` 与组合根
  `PlatformComposition`；组合根构造期校验注册键 / 名称 / 值并把
  内部注册防御性快照为只读映射。
- 投资域不读取 `workspace/portfolio/...` 私有文件；财报与研究材料存取
  只能经 `dayu.fins.storage` 协议（既有 owner）。
- 依赖方向由 `tests/investment/test_architecture_boundaries.py` 的
  AST guard 守护：它只枚举 `dayu.investment` 包内的 Python 文件，
  断言这些文件不导入上层包；它不扫描 `dayu.investment` 以外的模块，
  因此不构成对跨包反向 import 的检查。

## 2. 模块 owner

当前实现包含纯 domain 骨架、平台严格设置与平台组合契约：

| 模块 | 职责 |
| --- | --- |
| `dayu/investment/__init__.py` | 包导出层，转发 domain 公开符号 |
| `dayu/investment/domain/__init__.py` | domain 子包导出层 |
| `dayu/investment/domain/identifiers.py` | `TenantId/CompanyId/SecurityId/PortfolioId/AccountId` 强标识、`Principal`、`TenantScope` |
| `dayu/investment/domain/money.py` | `Money`、`Quantity` 值对象与 UTC 时间工具 |
| `dayu/investment/config.py` | `PlatformSettings` 严格设置、`PlatformDeploymentProfile`、`load_platform_settings()`、`PlatformSettingsError` |
| `dayu/investment/composition.py` | `PlatformServiceProtocol`、`PlatformCompositionProviderProtocol`、`PlatformComposition` 组合根、`PlatformCompositionContractError` |

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

### 2.4 平台严格设置

- 环境变量开关与名称是固定契约，由 `config.py` 常量声明：
  `DAYU_PLATFORM_ENABLED`、`DAYU_PLATFORM_PROFILE`、
  `DAYU_PLATFORM_USE_IN_MEMORY`、`DAYU_PLATFORM_POSTGRES_DSN`、
  `DAYU_PLATFORM_OBJECT_STORAGE`、`DAYU_PLATFORM_REDIS_URL`、
  `DAYU_PLATFORM_AUTH_KEY`。
- `PlatformSettings` 只记录"环境变量名称已配置"这一事实，任何情况下
  都不持有/回显 secret 值；`load_platform_settings()` 只做存在性
  检查，绝不读取并保留取值。
- production 部署启用平台时必须提供全部四个基础设施环境变量名称且
  禁止 in-memory adapters；development 部署启用时必须显式选择
  in-memory adapters 且禁止混用 production 基础设施环境变量；平台
  禁用时不要求任何基础设施，但仍校验已配置名称的 env-name 形态。
- 非法 env-name、非法布尔开关、未知 profile 一律 fail closed；异常
  消息只报告字段与固定规则，不格式化候选值。

### 2.5 平台组合契约

- `PlatformServiceProtocol` 是平台可对外暴露 Service 的非空稳定契约，
  携带只读 `platform_service_name`，支持运行时结构检查。
- `PlatformCompositionProviderProtocol` 声明
  `provide_services() -> Mapping[str, PlatformServiceProtocol]`；
  真源在纯层，`dayu.services.protocols` 只做稳定 re-export。
- `PlatformComposition` 组合根构造期校验：注册键必须是非空且无首尾
  空白字符串、值必须满足 `PlatformServiceProtocol`、值的
  `platform_service_name` 必须合法且与注册键一致、禁用组合不得携带
  任何注册；内部注册防御性快照为只读 `MappingProxyType`，外部后续
  修改原映射不影响组合根。任意 str / dict / 无协议值、空 / 仅空白 /
  键名不匹配一律 fail closed。
- 启动装配入口在 `dayu.startup.platform.build_platform_composition()`：
  平台启用但未注入提供者、提供者不满足协议或产出注册违反契约时
  fail-fast；提供者自身异常原样传播。该入口只依赖纯层契约，可冷启动
  直接导入。

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
完整性；`tests/investment/test_platform_config.py` 覆盖平台设置
校验矩阵、组合根协议边界与 secret-shape 异常 redaction。测试文件自身
同样遵守根 `AGENTS.md` 的同类约束。
