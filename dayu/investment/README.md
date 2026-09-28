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
| `dayu/investment/domain/evidence.py` | S31-A 纯域 Fact/ClaimVersion/EvidenceLink/Conflict/Candidate DTO、五类 Fins locator 结构镜像、PIT 与局部状态规则；不验证 Fins 当前 owner/freshness |
| `dayu/investment/domain/workspace_import.py` | 旧 workspace 显式导入（S15-CTRL-06）的 strict DTO / canonical / fingerprint owner：七类稳定错误、UUIDv5 算法、HK/CN/US market consistency gate、fingerprint 计算 |
| `dayu/investment/domain/jobs.py` | durable job/attempt/lease/receipt/correlation 与 Worker governance 的纯域契约、canonical document 编码/解析与稳定错误；只依赖标准库与 `identifiers` |
| `dayu/investment/domain/schedules.py` | durable schedule/occurrence 纯域 owner：frozen DTO、closed 状态/动作/错误与 snapshot 不变量 |
| `dayu/investment/config.py` | `PlatformSettings`、`PlatformQueueSettings`、deployment profile→queue mode/admission 严格映射与安全启动快照 |
| `dayu/investment/composition.py` | `PlatformServiceProtocol`、`PlatformCompositionProviderProtocol`、`PlatformIdentityServiceProtocol`、`PlatformWorkspaceImportServiceProtocol` 窄服务契约、`PlatformOwnedLifecycleProtocol`、`PlatformComposition` 组合根、`PlatformCompositionContractError` |
| `dayu/investment/storage/db.py` | 隐藏 SQL bind 参数的 engine/session factory、确定性 naming convention、schema/role/tenant 常量、`PlatformMigrationAdmissionError` |
| `dayu/investment/storage/protocols.py` | identity/source/workspace import、`JobStoreProtocol` 与 `ScheduleStoreProtocol` 的存储契约及稳定错误 |
| `dayu/investment/storage/evidence_protocols.py` | S31-B 十三个严格证据仓储入口的窄协议与固定脱敏错误；认证入口只收租户提示、bearer 和请求 |
| `dayu/investment/storage/postgres_evidence.py` | `PostgresEvidenceRepository`：单事务证据写入、版本 CAS、审查见证、冲突解决、到期物化与局部就绪；不判定 Fins 实时有效性 |
| `dayu/investment/storage/postgres_identity.py` | transaction-scoped PostgreSQL identity/source repository（SET LOCAL、CAS、atomic registration） |
| `dayu/investment/storage/postgres_jobs.py` | `PostgresJobStore`：durable job/attempt/lease/receipt/event/correlation 的唯一 PostgreSQL 实现（单事务 SET LOCAL、SKIP LOCKED、fence+token 校验、PG clock 权威） |
| `dayu/investment/storage/postgres_schedules.py` | `PostgresScheduleStore`：schedule definition/cursor/occurrence outbox 的 tenant-scoped PostgreSQL 真源 |
| `dayu/investment/storage/_evidence_review_auth.py` | S31-Auth 私有辅助：在调用者的 PG READ COMMITTED 事务内验证已有 bearer 的 active actor 或显式 reviewer grant，并返回 token 派生见证 |
| `dayu/investment/storage/models_identity.py` | identity/tenant/source 域 8 张 ORM 表 |
| `dayu/investment/storage/models_auth.py` | RBAC/auth 域 5 张 ORM 表 |
| `dayu/investment/storage/models_evidence.py` | S31-A 六张证据/研究 ORM 表的 metadata；`0007` 是物理 DDL 真源 |
| `dayu/investment/storage/models_workspace_import.py` | 0002 两张 tenant-scoped append-only 表 ORM（marker / locator） |
| `dayu/investment/storage/postgres_workspace_import.py` | 唯一单事务 workspace import repository（advisory xact lock、marker、exact no-op/drift、RLS SET LOCAL） |
| `dayu/investment/storage/migrations/**` | Alembic migration 真源（transactional upgrade/downgrade） |
| `dayu/services/investment_identity.py` | `InvestmentIdentityService` 窄 Service 实现（编排两 repository，TenantScope 传入，幂等 close） |
| `dayu/services/workspace_import.py` | `WorkspaceImportService` 窄 Service 实现（只接受 default tenant scope，delegate repository，幂等 close） |
| `dayu/services/job_service.py` | durable job execution registry/gateway、post-commit wake-up publisher 与 Host correlation governance owner |
| `dayu/services/schedule_service.py` | cron/timezone/misfire 计算、schedule 状态编排与 occurrence materialization owner |

### 2.1 标识与租户范围

- 五个标识均为 frozen slots 运行时值对象；直接构造与 `make_*` 工厂
  执行同样的严格校验，空值、仅空白或首尾空白一律拒绝。
- `Principal` 是操作主体（租户 + 用户），当前为公开构造器；私有
  S31-Auth 辅助只返回 token 派生见证，不生成 `Principal`。`TenantScope`
  禁止公开直接构造，只能由 `Principal.to_scope()` 派生；模块私有
  哨兵仅是公开 API misuse guard，不是认证能力。
- `TenantScope` 是租户边界契约的载体，禁止从全局状态或业务字段
  推断租户。
- S31-Auth 将传入的 `TenantScope` 仅用作不可信 RLS 查询提示；在同一
  READ COMMITTED 事务中 `SET LOCAL` 并读回后，以已有 token 行推导
  tenant、user 与 token ID。作者路径只检查 active token/user/organization，
  审查路径还要求 `investment.claim.review` 显式 grant；两条路径各用一条
  授权 SELECT，以该语句快照为授权时点。辅助模块只接受
  `hide_parameters=True` 的事务连接，不签发 token、不提交事务。

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
- integration profile 只供测试/本地 durable integration：必须且只允许
  `DAYU_PLATFORM_POSTGRES_DSN`，object storage、Redis、auth 任一非空都 fail-fast。
  它固定派生 `POSTGRES_POLLING` / `POSTGRES_ONLY`；production 固定派生
  `EVENT_ASSISTED` / `REDIS`。
- `PlatformQueueSettings` 持有 poll、Redis health/failure threshold、shutdown grace、
  schedule lookback/scan/tick 与 governance page/failure threshold 的严格数值契约。
  profile 唯一决定 mode/admission，不接受用户自由 mode 字符串。
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

- 0001–0006 的 `dayu_platform` schema 精确包含 27 张表：3 张公共 reference
  （`companies` / `securities` / `source_definitions`，不启用 RLS）、
  0001 的 10 张 tenant 私有表（`organizations` / `users` / `roles` /
  `permissions` / `user_roles` / `role_permissions` / `api_tokens` /
  `source_subscriptions` / `source_sync_runs` / `source_health_snapshots`）、
  0002 新增 2 张私有表
  （`workspace_import_markers` / `research_bundle_locators`）与 0003
  新增 7 张 durable job 私有表（`job_definitions` / `job_runs` /
  `job_attempts` / `job_leases` / `job_attempt_receipts` / `job_events` /
  `agent_run_correlations`），以及 0004 新增 2 张 durable schedule 私有表
  （`job_schedules` / `job_schedule_occurrences`）与 0005 新增 3 张 source
  health 私有表（`source_sync_operations` / `source_health_states` /
  `source_health_alert_outbox`）；合计 `3 + 10 + 2 + 7 + 2 + 3 = 27`，
  所有 tenant 私有表都 `ENABLE + FORCE ROW LEVEL SECURITY`。
- linear `0006_job_request_identity` 在 `job_runs` 增加最终 NOT NULL 的
  `original_available_at`、`request_payload_schema_name` 与
  `request_payload_schema_version`；首次 enqueue 在同一 INSERT 写入三列，
  app role 不获得 UPDATE 权限，immutable trigger 拒绝任何后续改写。
  `available_at` 继续只表示 mutable retry eligibility；claim/recovery/Source
  provenance 从持久化 original identity 重建，合法 request schema 可与
  definition descriptor schema 不同。
- 0006 非空库 backfill 先在锁内验证 raw SHA、严格 UTF-8 canonical JSON
  （duplicate/BOM/trailing/float/NaN/sensitive key 全拒绝）与逐字节重编码，
  再用当前 available+definition schema 重算既有 fingerprint；只有全表
  proof exact 才两阶段写入。downgrade 使用相同 NOWAIT 锁序，存在 Job row
  或三列/三CHECK/function/trigger的外部依赖时 fail closed，禁止 CASCADE。
- linear `0007_strict_evidence` 在 `securities` 加 `(company_id,id,ticker)`
  UNIQUE，并新增六张 tenant 私有表：`facts`、`claims`、`claim_versions`、
  `evidence_links`、`claim_conflicts`、`research_candidates`；总计 33 张
  physical 表、24 张 ORM mapped 表（显式 0007）。当前 head 0008 有 34 张
  physical 表、25 张 mapped 表，其中 31 张私有表、3 张公开表。Fact 原值为无 typmod `NUMERIC`，
  DB CHECK 限制未舍入的 38 位/12 scale；Fact 与 direct link 的
  security/ticker/locator 由复合 FK、JSONB ticker 等值和全列互斥 CHECK
  闭合。direct link digest 仅作固定宽查重键，完整 JSONB 是目标身份。
  六表启用 FORCE RLS；Fact/ClaimVersion/EvidenceLink append-only。
  S31-B 仓储以 `(tenant_id,company_id,fact_series_id)` 列出各公司的
  不可变 Fact 修订链，并提供证据版本写入、候选 proposed 持久化与局部就绪；Fins
  owner/readback/freshness 和最终 forecast/decision readiness 留给后续 Service。
  已提交 conflict resolution 的重试先核原持久指纹配对、witness/source，再核完整请求
  指纹；异 reviewer 或请求返回 `evidence_conflict`，原历史损坏返回
  `evidence_storage_failure`，不会改写已提交的版本、链接或冲突记录。
  append/begin/review 的 copy 重试也核 source 与持久 successor 的邻接，
  相同 operation 改变 caller expected version 返回稳定冲突。
  局部就绪以全部历史版本 ID 的集合匹配 open material conflict 的两侧端点，
  保留旧版本上的冲突并忽略同公司无关、nonmaterial 和 resolved 冲突。
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

### 2.8 Durable job queue 与 governance

- `dayu.investment.domain.jobs` 是 job/execution/heartbeat/governance DTO、closed 状态枚举、
  稳定错误与 canonical document / generic / Host-origin receipt
  builder 的唯一 import 路径；只依赖标准库与 `identifiers`，禁止
  import Host / contracts / storage。
- `JobStoreProtocol`（`storage/protocols.py`）与 `PostgresJobStore`
  （`storage/postgres_jobs.py`）是 queue 仓储契约/实现真源：每个方法
  独立 tenant-scoped 单事务（`SET LOCAL app.tenant_id` 后取 PG
  `transaction_timestamp()`/`clock_timestamp()` 为唯一权威时钟）。
  `PostgresJobStore` constructor 只接收 `session_factory`，绝不接收
  Host reader / registry；storage 永不 import `dayu.host` /
  `dayu.contracts`。lease 校验按
  tenant/job/attempt/fence/token-hash/current-attempt 全关联执行，
  wrong-tenant / 跨 job 拼接 / wrong attempt / wrong fence / wrong
  token 一律 `JobLeaseLostError`（authorize 入口返回闭合
  `LEASE_LOST` decision），零业务状态变更。
- `PostgresJobStore.enqueue()` 是新请求唯一 canonical admission owner：在
  session factory、fingerprint、SQL 与 wakeup publish 前 strict decode/
  public parse/re-encode，并要求bytes/SHA exact一致；成功后持久化上述三列。
- `0003_durable_jobs` 新增七张 tenant-scoped 私有表：versioned
  mutable 行带 `updated_at/version`，append-only 行只有 `created_at`；
  `job_leases` 的 release 是 versioned CAS + single-release trigger；
  `job_attempt_receipts` 每 attempt 至多一条 immutable receipt；
  event sequence 取自锁定 `job_runs` 行后原子递增的
  `next_event_sequence`，禁止裸 `MAX+1`。app role 权限最小化：receipts
  / events 只 `SELECT/INSERT`，其余表 `SELECT/INSERT` + 精确列级
  UPDATE（identity/payload/fingerprint/fence/token/acquire 不可更新，
  以列级 GRANT 与 DB trigger 双重拒绝）；audit 只 `SELECT`；PUBLIC 全
  revoke。
- 0003 downgrade 在任何破坏性 DDL 前先查询 `pg_depend`：发现七表
  owner 之外的外部 view/rule 或其它表 FK 依赖时**整次 fail closed 并
  回滚**，运维必须先移除该外部依赖后再重试，**禁止 CASCADE**；随后按
  `job_attempt_receipts -> job_events -> agent_run_correlations ->
  job_leases -> job_attempts -> job_runs -> job_definitions` 顺序删除，
  保留 0001/0002 对象、roles、default org 与 Alembic version table。
- `dayu.services.job_service` 分离 immutable descriptor registry 与 execution registry；
  `JobService.execute_claim()` 是 Worker 唯一 handler invocation gateway，handler 不会收到
  lease/fence/raw token/worker id。Host correlation 的 deadline/cancel 来自 PG projection，
  需要取消 active Host run 时只写入协作式 `cancel_run()` intent。
- production descriptor/execution registry 注册并封存 exact-one Source Sync handler，不注册
  research/Agent/Broker handler；其它未注册 handler 仍以稳定的 non-retryable failure 收敛，不调用 Host、模型或 provider。
- `dayu-cli init` 经 `dayu.cli.workspace_migrations.platform_jobs`
  在平台启用且 production 时以既有 bootstrap DSN 环境变量幂等执行
  `upgrade head`；平台禁用 / development / DSN 缺失均 fail closed，
  不读写 workspace 业务文件。

### 2.9 Durable schedules 与 Redis hint

- `job_schedules` 保存 immutable schedule definition 和 current cursor；
  `job_schedule_occurrences` 是 cursor 与 job enqueue 之间的 durable outbox。cursor 推进与
  PENDING occurrence 在同一 PG 事务，`MATERIALIZING` 则是不可撤销的入队承诺。
- `ScheduleService` 拥有 croniter/timezone/DST/misfire 计算；storage 只拥有 PG 状态机。
  崩溃重放使用 occurrence 中冻结的 enqueue snapshot、fingerprint 和 idempotency key，
  不使用新时钟重建请求。
- PostgreSQL 是 job/schedule 全部 durable truth。Redis 只发布 tenant-scoped wake-up
  hint，不承载 payload、queue、lease、fence、cancel、dedupe、cursor、occurrence 或 receipt。
  production 启动需先通过 Redis admission；integration 的 `POSTGRES_ONLY` 路径不构造任何
  Redis 对象。

## 3. 测试与验证

```bash
source .venv/bin/activate
python -m pytest tests/investment -q
python -m pytest tests/investment --cov=dayu.investment --cov-report=term-missing
pytest tests/integration/investment/test_platform_migrations_postgres.py -q -m integration --timeout=120
pytest tests/integration/investment/test_job_request_identity_migration_postgres.py -q -m integration --timeout=120
pytest tests/integration/investment/test_postgres_jobs.py -q -m integration --timeout=120
pytest tests/integration/investment/test_postgres_sources.py -q -m integration --timeout=120
pytest tests/integration/investment/test_postgres_evidence_auth.py -q -m integration --timeout=120
pytest tests/investment/test_evidence_domain.py tests/investment/test_evidence_storage_contract.py -q
pytest tests/integration/investment/test_postgres_evidence.py -q -m integration --timeout=120
pyright dayu/investment tests/investment tests/integration/investment
ruff check --select E4,E7,E9,F,I dayu/investment tests/investment tests/integration/investment
```

S31-Auth 的 PG16 用例运行于当前 head（0008）schema，但只验证认证语义；S31-A 的 PG16 用例
验证 0007 迁移往返、RLS/ACL、原始参数化 SQL 负例、双 MIC 与五类 locator，
均不改变已建立的九个有状态 integration owner lane。本地固定 PostgreSQL/Redis 镜像的显式
pull 前置、digest 与“fixture 不隐式 pull”契约见
[`tests/README.md`](../../tests/README.md)。

`tests/investment/test_architecture_boundaries.py` 以 AST 按相对路径
分组守护 `dayu.investment` 生产代码的依赖方向、逃逸模式
（`Any/object/cast/type: ignore/getattr/hasattr`，含对 frozen+slots
dataclass `__post_init__` 内精确 `object.__setattr__` 的豁免）与中文
docstring 完整性；
`tests/investment/test_evidence_review_auth.py` 覆盖 S31-Auth bearer/hint
校验、固定脱敏错误、两条 SQL 形态及不可序列化见证；
`tests/investment/test_evidence_domain.py` 与
`tests/investment/test_evidence_storage_contract.py` 覆盖 S31-A 结构镜像、
Decimal/PIT、状态/链接、六表 metadata/迁移静态契约，以及 S31-B 证据仓储
协议的十三个签名（含必填公司 ID 的 Fact series 列表）与固定错误码；
`tests/integration/investment/test_postgres_evidence_auth.py` 在当前 head（0008）
上验证 active actor/reviewer grant、RLS/ACL、撤销快照、INFO 参数日志
隐藏、非隐藏 Engine 拒绝与故障回滚；
`tests/integration/investment/test_postgres_evidence.py` 同时验证 0007 物理约束
与 S31-B 仓储的跨公司同 series、head 前进后历史 copy 重试、reviewer
terminal 转换与重开、普通 append 状态门、版本、冲突、到期、digest 和事务回滚行为；
冲突解决重试还比较异主体/请求的固定冲突码及完整历史 JSONB 快照，保留 witness
或持久指纹配对损坏的存储失败与同主体更换 token 的成功重试；append/begin/review
同 operation 改变 expected version 时也核固定冲突码和完整 head/Version/Link 快照；
`tests/investment/test_platform_config.py` 覆盖平台
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

### 候选接入边界

`InvestmentResearchService.ingest_candidate(scope, context, raw_output)` 通过显式
identity、intake repository、Fins 协议和 UTC clock 注入处理候选；`scope` 从
`Principal.to_scope()` 获得，context 明确 candidate/operation/company/security
UUID、origin 和 extractor version。`parse_fact_candidate` 只接受九键
`fact_candidate.v1`，保留 Decimal 的定点精度、scale 和负零；拒绝重复 JSON
key、float、非法 Unicode 与超过 1 MiB 的 raw/canonical payload。

Service 先查历史 intake receipt，再调用公共 Fins validate 和 citation readback
逐字段与实际内容 SHA 核验。业务拒绝只保存 raw SHA、字节数和固定 rejection code
组成的四键安全 envelope；依赖失败返回固定错误并保持零 candidate/receipt 写入。
候选接入不产生 Fact/Claim 晋升；首结果和后续 candidate head 分别持有历史与可变状态。

`PostgresCandidateIntakeRepository` 在 READ COMMITTED 单事务的一个 SAVEPOINT 内
写 candidate 与 `candidate_intake_receipts`。五个精确命名 23505 键都先回滚
SAVEPOINT，再按 requested tenant+operation 用新 SELECT 回读完整历史；请求身份
相同才恢复首结果，损坏历史为固定 storage failure。receipt 的 outcome/version1
不随 candidate 后续状态改变。0008 的19列 receipt 具有 tenant/security/candidate
FK、闭合 outcome CHECK、FORCE RLS 和 append-only guard；app 仅 SELECT/INSERT，
audit 仅 SELECT。回退必须通过精确 own catalog、空表、NOWAIT 锁和 DROP RESTRICT。

`tests/integration/investment/test_postgres_candidate_intake.py` 使用真实 PG16 的
Service/identity/intake 组合，覆盖首结果恢复、并发/跨租户身份冲突、同 SAVEPOINT
故障回滚和0008回退拒绝。Fins 使用公共协议本地替身；观察 witness 不承诺提交时
或未来消费时的 source freshness。所有迁移验证针对测试独占随机库。
