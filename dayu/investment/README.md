# Investment 投资域开发手册

`dayu.investment` 是投资平台（公司研究、组合、决策与执行）的落地包。
本文档只写当前实现：依赖方向、模块 owner、schema/migration 真源与
开发命令。

## 1. 依赖方向

投资包位于 `UI -> Service -> Host -> Agent` 分层之外的领域/存储层，
位于依赖方向的底部：

```text
dayu.investment.domain         纯 domain 契约（Slice 0.1）
dayu.investment.config         平台严格设置（只记录环境变量名称）
dayu.investment.composition    平台组合契约（只承载 Service 协议实例的组合根）
dayu.investment.storage        PostgreSQL 存储实现（ORM + Alembic migration）
```

硬约束（按 owner 分组，由 architecture AST guard 守护）：

- pure 集合精确为根 `__init__.py`、`domain/**`、`config.py`、
  `composition.py`：不依赖 Web、Service、Host、Agent、SQLAlchemy、
  psycopg、Alembic、pydantic 或任何 Broker SDK。
- infra 集合精确为 `storage/**`：可以依赖 SQLAlchemy / psycopg /
  Alembic 与 pure domain，仍禁止依赖 Web、Service、Host、Agent、CLI、
  Broker SDK 或未来 slice。
- `dayu.investment.config` 只做环境变量名称的存在性检查，绝不记录或
  回显 secret 值；非法 env-name 异常只报告字段与固定规则。
- `dayu.investment.composition` 定义 `PlatformServiceProtocol` /
  `PlatformCompositionProviderProtocol` 与组合根
  `PlatformComposition`；组合根构造期校验注册键 / 名称 / 值并把
  内部注册防御性快照为只读映射。
- 投资域不读取 `workspace/portfolio/...` 私有文件；财报与研究材料存取
  只能经 `dayu.fins.storage` 协议（既有 owner）。
- 依赖方向由 `tests/investment/test_architecture_boundaries.py` 的
  AST guard 按相对路径分组守护：pure 集合使用完整 forbidden set，
  infra 集合只移除 ORM/驱动依赖；未知新增路径默认按 pure 规则拒绝。
  它只枚举 `dayu.investment` 包内的 Python 文件，不扫描包外模块，
  因此不构成对跨包反向 import 的检查。

## 2. 模块 owner

当前实现包含纯 domain 骨架、平台严格设置、平台组合契约与 PostgreSQL
存储层：

| 模块 | 职责 |
| --- | --- |
| `dayu/investment/__init__.py` | 包导出层，转发 domain 公开符号（不 re-export storage/ORM） |
| `dayu/investment/domain/__init__.py` | domain 子包导出层 |
| `dayu/investment/domain/identifiers.py` | `TenantId/CompanyId/SecurityId/PortfolioId/AccountId` 强标识、`Principal`、`TenantScope` |
| `dayu/investment/domain/money.py` | `Money`、`Quantity` 值对象与 UTC 时间工具 |
| `dayu/investment/domain/source.py` | identity/source 边界 frozen DTO、closed enums、canonical UUID 强标识（S12-CTRL-01/05） |
| `dayu/investment/domain/workspace_import.py` | 旧 workspace 显式导入（S15-CTRL-06）的 strict DTO / canonical / fingerprint owner：七类稳定错误、UUIDv5 算法、HK/CN/US market consistency gate、fingerprint 计算 |
| `dayu/investment/config.py` | `PlatformSettings` 严格设置、`PlatformDeploymentProfile`、`load_platform_settings()`、`PlatformSettingsError` |
| `dayu/investment/composition.py` | `PlatformServiceProtocol`、`PlatformCompositionProviderProtocol`、`PlatformIdentityServiceProtocol`、`PlatformWorkspaceImportServiceProtocol` 窄服务契约、`PlatformOwnedLifecycleProtocol`、`PlatformComposition` 组合根、`PlatformCompositionContractError` |
| `dayu/investment/storage/db.py` | engine/session factory、确定性 naming convention、schema/role/tenant 常量、`PlatformMigrationAdmissionError` |
| `dayu/investment/storage/protocols.py` | `IdentityRepositoryProtocol` / `SourceRepositoryProtocol` / `WorkspaceImportRepositoryProtocol` 与五类稳定错误（S12-CTRL-01 / S15-CTRL-09） |
| `dayu/investment/storage/postgres_identity.py` | transaction-scoped PostgreSQL identity/source repository（SET LOCAL、CAS、atomic registration） |
| `dayu/investment/storage/models_identity.py` | identity/tenant/source 域 8 张 ORM 表 |
| `dayu/investment/storage/models_auth.py` | RBAC/auth 域 5 张 ORM 表 |
| `dayu/investment/storage/models_workspace_import.py` | 0002 两张 tenant-scoped append-only 表 ORM（marker / locator） |
| `dayu/investment/storage/postgres_workspace_import.py` | 唯一单事务 workspace import repository（advisory xact lock、marker、exact no-op/drift、RLS SET LOCAL） |
| `dayu/investment/storage/migrations/**` | Alembic migration 真源（transactional upgrade/downgrade） |
| `dayu/services/investment_identity.py` | `InvestmentIdentityService` 窄 Service 实现（编排两 repository，TenantScope 传入，幂等 close） |
| `dayu/services/workspace_import.py` | `WorkspaceImportService` 窄 Service 实现（只接受 default tenant scope，delegate repository，幂等 close） |

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

### 2.6 PostgreSQL 存储层

- `dayu_platform` schema 精确包含 15 张表：3 张公共 reference
  （`companies` / `securities` / `source_definitions`，不启用 RLS）、
  10 张既有私有表（`organizations` 及 `users` 到
  `source_health_snapshots`）与 0002 新增 2 张私有表
  （`workspace_import_markers` / `research_bundle_locators`，全部
  `ENABLE + FORCE ROW LEVEL SECURITY`）。
- UUID 全部由调用方提供，无 server random default；`created_at/
  updated_at` 为 `TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp()`；
  `observed_at/started_at` 由调用方提供；`finished_at` 可空；
  `version` 为 `INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)`；
  mutable 表带 `updated_at/version`，append-only 表不带。
- 私有表每张建立唯一 `tenant_isolation` policy
  （`FOR ALL TO dayu_platform_app`），tenant 表达式为
  `nullif(current_setting('app.tenant_id', true), '')::uuid`，
  `organizations` 比较 `id`，其它私有表比较 `tenant_id`；未设置 / 空 /
  错误 tenant default deny。
- RBAC group role 精确为 `dayu_platform_app`（NOLOGIN NOBYPASSRLS
  无 DDL）与 `dayu_platform_audit`（NOLOGIN BYPASSRLS 只读）；
  app/audit 对象权限矩阵在迁移内显式授予，不向 future objects
  blanket grant；bootstrap superuser 独占 schema/DDL/role/policy
  ownership。受审计 operator LOGIN 自身 NOBYPASSRLS，只能经 audit
  group membership + 显式 `SET ROLE dayu_platform_audit` 获得受控
  bypass，不能把高权限直接扩散到 operator。
- `alembic.ini` 不保存 DSN；Alembic env 只从
  `DAYU_PLATFORM_POSTGRES_DSN` 读取 bootstrap DSN、关闭 SQL/secret
  回显，并在任何 DDL 前以 `pg_roles` 完成 `rolsuper IS TRUE` 准入
  预检（`PlatformMigrationAdmissionError`，事务中零 side effect）。
- downgrade 在任何破坏性 DDL 前执行显式 admission：存在 app/audit
  外部 member、非当前活跃 session 或 `dayu_platform` schema 之外的
  外部依赖时整次 fail closed；通过后按 policy -> 表 -> schema
  `RESTRICT` -> group role 精确回滚，禁止 CASCADE。
- 生产/导入路径禁止 `metadata.create_all()`，schema 唯一创建真源是
  Alembic migration。

### 2.7 旧 workspace 显式导入（S15-CTRL-06/08/09）

- `dayu.investment.domain.workspace_import` 是唯一 strict
  DTO/canonical/fingerprint owner：七类稳定错误
  （`workspace_import_usage` 到 `workspace_import_repository_failure`）、
  UUIDv5 ID 算法（`NAMESPACE_URL` + 固定 name 前缀）、HK/CN/US
  market consistency gate（HK 必须 `XHKG/HKD/HK`，CN SSE/SZSE 分别
  `XSHG`/`XSHE` 且 `CNY/CN`，US 只做形状验证、不猜 MIC）、
  `source_root_fingerprint` / `staged_payload_sha256` canonical
  SHA-256；该模块只依赖标准库与 pure identifiers，禁止 import
  `dayu.fins.*` / CLI / Service / ORM。
- `0002_workspace_import` migration 新增且只新增两表：
  `workspace_import_markers`（marker 只表示 completed commit，无
  pending/failed status；`UNIQUE(tenant_id, migration_id)`）与
  `research_bundle_locators`（无冗余 `company_id`，公司只能经
  `security_id -> securities.company_id` 解析；`repository_key`
  closed 值 `legacy-workspace`；复合 `(tenant_id, import_marker_id)`
  FK）。两表 `ENABLE + FORCE RLS`，唯一 `tenant_isolation` policy
  （`app.tenant_id`），app 仅 `SELECT/INSERT`，audit `SELECT`，
  PUBLIC 全 revoke；downgrade 先拒绝外部依赖（外部 view/rule 或其它
  表 FK），再按 locator -> marker 删除，无 CASCADE。
- `PostgresWorkspaceImportRepository.publish_import` 是唯一 DB
  transaction owner：每次调用只建一个 session，`SET LOCAL
  app.tenant_id` 后在同一 transaction 内完成 schema probe ->
  `pg_advisory_xact_lock(sha256(tenant + "\0" + migration) 前 8 字节
  signed big-endian)` -> marker read -> public reference reconcile ->
  marker insert -> locator inserts；已有 marker 且 intended rows exact
  返回 `no_op`，任一字段/row drift 抛稳定 drift，commit/rollback
  自动释放锁。company/security/source 公共行只允许 insert 或 exact
  reuse，相同业务键映射到不同 ID、同 ID projection 不一致、
  security-company 关系不一致均 fail closed。

## 3. 测试与验证

```bash
source .venv/bin/activate
python -m pytest tests/investment -q
python -m pytest tests/investment --cov=dayu.investment --cov-report=term-missing
python -m pytest tests/integration/investment -q            # 需本地 pinned PG16 镜像
pyright dayu/investment tests/investment tests/integration/investment
ruff check --select E4,E7,E9,F,I dayu/investment tests/investment tests/integration/investment
```

`tests/investment/test_architecture_boundaries.py` 以 AST 按相对路径
分组守护 `dayu.investment` 生产代码的依赖方向、逃逸模式
（`Any/object/cast/type: ignore/getattr/hasattr`，含对 frozen+slots
dataclass `__post_init__` 内精确 `object.__setattr__` 的豁免）与中文
docstring 完整性；`tests/investment/test_platform_config.py` 覆盖平台
设置校验矩阵、组合根协议边界与 secret-shape 异常 redaction；
`tests/investment/test_platform_migrations.py` 覆盖 metadata /
naming convention / 编译 DDL / 禁止 `create_all` 等无数据库 unit
contract；`tests/investment/test_identity_repositories.py` 覆盖
domain/source DTO、repository 协议签名、窄 Service 契约与深冻结
JSON（无 DB）；`tests/integration/investment/test_platform_migrations_postgres.py`
在真实官方 `postgres:16.14-bookworm` 容器上验证
`upgrade/downgrade/upgrade`、default organization、RLS default
deny/same-tenant/cross-tenant、audit bypass、GRANT matrix、downgrade
三类 fail-closed 与 schema exact；
`tests/integration/investment/test_identity_repositories_postgres.py`
在真实 PG16 上验证 unique/CAS/atomic rollback/cross-tenant/tenant
setting 不泄漏、read-path schema fault 稳定映射与 production startup
black-box；
`tests/integration/investment/test_workspace_migration.py` 在真实 PG16
上验证 workspace import 单事务发布 rows exact、exact rerun no_op、
fingerprint/row/business-key drift、advisory lock key 与两进程 race、
trigger fault 整次 rollback 零行、RLS/cross-tenant、vertical
`dayu-cli init --import-existing-workspace`（真实 stage/Service/
repository + 独立 audit 回读且 legacy bytes 未改）；
`tests/cli/test_workspace_migrations.py` 覆盖 domain/staging/CLI
import mode 的 unit 矩阵。测试文件自身同样遵守根 `AGENTS.md` 的同类约束。
