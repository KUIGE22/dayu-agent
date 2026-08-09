# 投资平台恢复计划独立审查（Terra）

- **审查对象**：`docs/plans/2026-08-10-investment-platform-restoration.md`
- **审查基线**：`d0ffe223d0f42521bb8a907152c1e8b4ade0125f`
- **审查分支**：`codex/investment-platform`
- **审查 gate**：plan review；独立 Terra reviewer
- **审查范围**：仅判断计划是否可安全交给 code-generation agent；未修改目标计划、生产代码、测试、README，也未执行 commit/push/PR。

## 审查结论

**fail**。

当前计划正确保留了 Paper 与独立 live admission gate，也正确识别了现有 UI -> Service -> Host -> Agent 与 Fins 仓储边界；但仍有 6 个高严重度未收敛项。这些项会让实施者在 schema、组合根、证据定位、租户隔离、回测与订单恢复上自行设计，违反计划的“发现 gap 必须停报”及 code-generation-ready 目标。

## 已测试的关键假设

1. **现有复用事实**：成立但边界比计划更具体。`dayu/web/fastapi_app.py:22-53` 由明确传入的窄 Service 装配并挂载路由；`dayu/web/streamlit/pages/main_page.py:55-98` 是现有 Streamlit tab 组合根。`dayu/services/startup_preparation.py:161-198` 同时硬编码构造 `HostStore`、`DefaultFinsRuntime` 与 `Host`。
2. **Host SQLite 可以保留而投资域改用 PostgreSQL**：可以，但必须明确两者的状态 owner 和关联方式。`dayu/host/host_store.py:31-122` 仍是 session/run/pending turn/reply outbox/permit 的 SQLite 真源；并非可由一个 PostgreSQL queue 自动替代的空壳。
3. **Fins 是材料唯一存取边界**：成立。现有 `SourceDocumentRepositoryProtocol` 以 `ticker + document_id + source_kind` 解析源文档（`dayu/fins/storage/repository_protocols.py:103-184`），blob 操作以 `SourceHandle | ProcessedHandle` 为输入（同文件:224-253）。
4. **S3 repository 会因实现而自动进入实际 Fins 链路**：不成立。默认运行时在 `DefaultFinsRuntime.create()` 固定创建五个 `Fs*Repository`（`dayu/fins/service_runtime.py:1291-1315`），启动组合根只调用该工厂（`dayu/services/startup_preparation.py:161-171`）。
5. **计划中的 live broker 没有被静默删除**：成立；Slice 8.4 明确要求具体 Broker、独立 plan review 与外部授权（计划:474-479）。本审查不把尚未获授权的真实下单本身列为缺陷。
6. **计划有 36 个可独立交付的 slices**：不成立。按 `^#### Slice ` 计数为 **35**（0.1-8.4），与 handoff 要求的 36 不一致。

## Findings

### 1-未修复-高-全新 schema 的旧工作区迁移被要求却没有可实施 slice
- **状态**: accepted-candidate
- **位置**: 计划 §6.1（第 128 行）、Slice 1.1（262-267 行）、所有 Slice allowlist；§10（509-515 行）。
- **问题类型**: 不可直接实施 / 契约缺失 / 切片过粗。
- **当前写法**: §6.1 要求“旧 workspace 数据迁移必须作为 `dayu-cli init` 的 `workspace_migrations` 插件显式导入”；Slice 1.1 只允许 Alembic fresh schema 与 migration tests，未允许 `dayu/cli/workspace_migrations/`、其 runner、`init` tests，后续 slice 也没有补充该迁移交付。
- **反例/失败场景**: 已有 workspace 同时存在 Host SQLite、Fins 文件材料与研究模板产物时，实施者只能选择：(a) 只启动空 PostgreSQL，令计划承诺的显式迁移缺失；或 (b) 在不属于任何 allowlist 的文件中临时接入迁移。两者都会使 migration source、幂等性、失败恢复和验收无 owner。
- **为什么有问题**: 项目约束对 schema 变更要求把旧库迁移动作接入 `dayu-cli init`；计划也作出同样承诺，却没有可执行切片。现有迁移机制要求新增模块并登记到统一 runner，而不是把逻辑写在 `init.py`（`dayu/cli/workspace_migrations/runner.py:1-13,38-80`；`dayu/README.md:352-369`）。
- **直接证据**: 计划 §6.1 第 128 行；Slice 1.1 第 264-267 行；现有 runner 第 20-35、54-80 行没有 platform migration；`dayu/README.md:352-369` 明确了迁移入口与登记规则。
- **影响**: 实施 Agent 跑偏 / 旧 workspace 无法受控迁移 / schema 变更违反项目硬约束 / review 不可验收。
- **建议改法和验证点**: 增设或明确一个独立 migration slice：给出哪些旧状态允许导入、哪些只保留只读、每类数据的 source-to-target mapping、幂等标记、失败后重跑语义、不可导入时的 fail-closed 报告；allowlist 必须包含新 migration 模块、runner 登记、`init` 测试及相关 README。以有 Fins/Host 历史数据、重复 init、半途失败重跑、空 workspace 为真实验收矩阵。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### 2-未修复-高-多个 slice 的 allowlist 排除了唯一实际组合根，交付物无法进入运行链路
- **状态**: accepted-candidate
- **位置**: Slice 0.2（254-258 行）、1.3（275-279 行）、2.1-2.2（283-294 行）、7.3（429-433 行）、7.5（441-445 行）。
- **问题类型**: 不可直接实施 / 架构边界 / 切片过粗。
- **当前写法**: 计划要求每个实施者只能修改该 slice allowlist；同时承诺 production 组合根只向 UI 暴露 Service Protocol、S3/PG/Redis 以 Compose 运行，并要求新增 API 与 Streamlit 控制台。
- **反例/失败场景**:
  1. Slice 1.3 只能改 `dayu/fins/storage/**`，不能改 `dayu/fins/service_runtime.py` 或 `dayu/services/startup_preparation.py`；因此 S3 repository 即使单测通过，默认 Fins runtime 仍创建 `FsDocumentBlobRepository`。
  2. Slice 7.3 未允许 `dayu/web/fastapi_app.py`，无法把新 portfolio/decision/execution router 挂到当前唯一 FastAPI app；Slice 7.5 未允许 `dayu/web/streamlit/pages/main_page.py`，无法把页面接进当前三-tab root。
  3. Slice 2.1/2.2 允许新增 job 文件，却没有明确谁修改现有启动期 Host/Service 装配来提供 queue、worker handler registry、Redis wake-up 与 shutdown 生命周期。
- **为什么有问题**: 这不是文档措辞问题，而是计划的“只能改 allowlist”规则会阻止生产路径接线。实施者若越界接线违反 plan，若不越界则只能提交孤立 adapter/router/page，无法满足 §1.1 的 production Compose 和 UI/API success signals。
- **直接证据**: `DefaultFinsRuntime.create()` 硬编码 FS 仓储（`dayu/fins/service_runtime.py:1291-1315`）；启动期只调用该 factory（`dayu/services/startup_preparation.py:161-171`）。FastAPI 组合根的全部 router 注册集中于 `dayu/web/fastapi_app.py:45-53`；Streamlit 内容组合集中于 `dayu/web/streamlit/pages/main_page.py:78-98`。对应计划 allowlist 分别见 1.3:277、7.3:431、7.5:443、2.1:285、2.2:292。
- **影响**: 生成错误代码 / S3、API、UI、worker 仅有测试桩没有 production path / 后续跨 slice 返工 / review 不可验收。
- **建议改法和验证点**: 在每个会改变可运行能力的 slice 中显式列出唯一 composition root，并把“注册方式、依赖注入接口、启动/关闭顺序、失败时 fail-fast 或降级”写为完成条件；或者新增仅负责 wiring 的窄 slice，但必须在消费它的功能 slice 前完成。每项做 black-box composition test，断言默认 production config 实际实例化 PG/S3/queue 与新增 route/page，而非只对实现类单测。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### 3-未修复-高-RBAC 被安排在持久化业务域之后，且 schema 没有租户真源与所有查询的隔离契约
- **状态**: accepted-candidate
- **位置**: §6.2 identity/security schema（137-171 行）、Slice 3.3（318-322 行）、Slice 5.1-5.5（357-386 行）、Slice 7.1（416-421 行）。
- **问题类型**: 架构边界 / 契约缺失 / 测试缺口。
- **当前写法**: schema 只列 `users/roles/permissions/user_roles/api_tokens`，业务表从 `companies` 到 `portfolios/accounts/orders` 均未声明 tenant/organization owner、跨 tenant FK、repository scope 参数或 PostgreSQL RLS；唯一出现 tenant 的地方是 Slice 3.3 的“tenant/company isolation”测试。RBAC foundation 被放在 Phase 7，晚于持久化研究、组合、订单和审批域。
- **反例/失败场景**: 两个 tenant 共享 ticker 或同一公共 Fins 文档时，服务按 `CompanyId`、`PortfolioId` 或 `document id` 查数据；没有 tenant key/作用域，就无法区分“共享公共材料可读”与“研究、组合、订单、approval 必须隔离”。后补 tenant 条件会迫使每个已有 repository/service/API 改签名，遗漏任一路径即泄漏别人的 decision/order 或用错 approval。
- **为什么有问题**: 用户要求包含 RBAC/tenant isolation，而计划声称所有表有 authoritative owner。现有 Host README 所称的“多租户”运行时能力是 Host session/run 治理，不提供投资数据 tenant ACL；不能把 Host session source 当投资域隔离真源（`dayu/host/README.md:9-17`，`dayu/host/host_store.py:31-63` 也没有 tenant 字段）。
- **直接证据**: 计划 schema:139-170 只列业务表和 users/roles 关系；Slice 3.3:322 要求 tenant isolation test；Slice 7.1:418-421 才建立 auth/RBAC。现有 Host SQLite `sessions/runs` schema 仅包含 `session_id/source/state` 与 run 元数据（`dayu/host/host_store.py:31-63`）。
- **影响**: 权限绕过 / 跨租户数据泄露或错误交易 / 后续返工 / RBAC matrix 无法证明真实隔离。
- **建议改法和验证点**: 在 Identity foundation（早于第一个可写业务 repository）定义 tenant/organization 边界：公共 Fins 材料与租户私有 projection 的 ownership model、每张私有表的 tenant FK、跨 tenant FK 禁止、repository 必带 scope、Service 从已认证 principal 建立 scope、是否使用 RLS 及其 connection contract。增加跨 tenant read/write/search/worker/retry/reconcile/backup restore 的负向集成测试；不是仅对 pgvector 搜索做一个过滤测试。
- **修复风险（低/中/高）**: 高。
- **严重程度（低/中/高/严重）**: 高。

### 4-未修复-高-Fact/Claim/Evidence 的“exact locator”缺少可解析的 Fins 文档身份，无法证明来源闭合
- **状态**: accepted-candidate
- **位置**: §5 硬依赖规则（115-120 行）、§6.2 Evidence schema（142-148 行）、Slice 3.1-3.2（305-316 行）。
- **问题类型**: 契约缺失 / 架构边界 / Agent trust boundary。
- **当前写法**: 计划要求投资域只保存“安全 locator、hash 和 repository id”，Fact 又只列“company、document id、locator、source hash”，Slice 3.2 声称 Service 做 Fins locator validation；但没有定义该 locator 的结构、canonical identity、版本/byte hash、source kind、processed/source variant、失效或删除语义，也没有给出 Fins read capability 的窄协议。
- **反例/失败场景**: Agent 返回旧 `document_id` 或同 ticker 的不同 source-kind 文档，或者 source document 被更新/重处理。Service 只持 company/document id/字符串 locator 时，无法无歧义地调用 Fins：现有 source repository 读取至少需要 `ticker, document_id, source_kind`，blob 仓储又需要 `SourceHandle | ProcessedHandle`。若放宽成直接拼 bucket/workspace path，会违反 Fins 唯一存取边界；若只相信字符串，则幻觉 candidate 可被误 promote。
- **为什么有问题**: 计划把 LLM 信任边界建立在“来源闭合”上，这是 authoritative Fact/Claim 的前置条件，不能留给 Slice 3.2 临时决定。当前 schema 与计划自身的 repository-id 承诺不一致，因而无法生成能稳定验证、展示 citation、重建 embedding 的实现。
- **直接证据**: 计划 §5:120 要 repository id；§6.2:144-146 没有该字段和 source kind；Slice 3.2:314-316 要 Fins validation。现有 `SourceDocumentRepositoryProtocol` 的 `get_source_meta/get_source/get_primary_source` 均要求 `source_kind`（`dayu/fins/storage/repository_protocols.py:148-184`），`DocumentBlobRepositoryProtocol` 只接收 Fins handles（同文件:224-253）。
- **影响**: LLM trust boundary 被绕过 / 错误或不可复核的 Fact 进入真源 / 证据链和公司隔离失效 / 无法安全迁移到 S3。
- **建议改法和验证点**: 在 Slice 3.1 前冻结一个由 Fins 定义、投资域只能不透明持有的强类型 `DocumentReference/Locator` 契约，至少包括 repository identity、canonical ticker/company、source/processed kind、document version/hash、精确 section/table/page locator 与可验证的 content hash；由 Fins Service Protocol 提供 validate/read/citation projection，投资域不触达 path/bucket。测试同 document id 跨 source-kind、重处理版本、hash mismatch、逻辑删除、跨 company/tenant、S3 和 FS 两个 adapter 的同一 locator 语义。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### 5-未修复-高-订单、成交、审批与 kill-switch 状态机不能定义可恢复的唯一提交语义
- **状态**: accepted-candidate
- **位置**: §6.2 Portfolio/decision/execution schema（158-165 行）、§6.3 Decision/execution state machine（195-204 行）、Slice 5.5（382-386 行）、Slice 6.1-6.2（390-400 行）。
- **问题类型**: 状态机漏洞 / 并发恢复风险 / 契约缺失。
- **当前写法**: 计划只有一个合并状态图：`candidate -> ... -> staged -> submitted -> acknowledged -> partially_filled -> filled`，并写“订单事实不可覆盖，只追加状态事件”；Broker protocol 只有 submit/cancel/get/list fills/reconcile，要求 idempotency key；kill switch 只规定不得提交新单。
- **反例/失败场景**: `submit()` 已被 broker 接收但本地网络超时，worker lease 过期后重试；或 cancel 与 late fill 并发；或 kill switch 在 `staged/submitted/partially_filled` 时触发。图没有定义 intent、broker order、fill、reconciliation run、approval、risk check、policy version 与 idempotency key 的基数/唯一键，也没有定义 uncertain-submit 如何从 broker 查询后归一、reconcile 后回到哪个业务状态、kill switch 是否 cancel open orders、谁有权恢复、何时更新账本。因此不同 implementation agent 可合法实现为重复下单、丢失 late fill 或把 `reconciled` 当终态而不更新 ledger。
- **为什么有问题**: 这条链路是用户要求的 Paper + 三模式 + 最终 live gate 的安全核心。现有 Host 对 pending turn/outbox 已采用 lease fence token 与显式 CAS，证明项目对“未知副作用后重试”要求强一致（`dayu/host/README.md:187-215,297-305`）；计划却未把同等的 ownership/fencing 语义落实到资金和订单域。
- **直接证据**: 计划:162-164 列表表名；:195-204 合并状态图；Slice 5.5:385-386 与 Slice 6.1:393-394；计划:221 仅覆盖“不得提交新单”。
- **影响**: 重复订单 / 账本不守恒 / kill switch 失效 / Paper 验收无法证明 live admission 所需的安全性 / 不可恢复。
- **建议改法和验证点**: 将状态拆为至少四个显式聚合：decision/approval、order intent、broker order lifecycle、ledger/fill/reconciliation；为每个给出 owner、事件表、CAS/fencing predicate、idempotency uniqueness、合法/非法转移和 terminal/repair path。明确 uncertain-submit 的 query-before-retry、late event de-dup key、reconcile 的差异决议、approval/policy/kill-switch 在每一次 broker side effect 前的 recheck，以及 kill switch 对已开订单的 cancel-or-hold 策略。以 crash-after-broker-accept、duplicate callback、cancel/late-fill、approval revoke、kill switch during partial-fill、restart reconcile 为黑箱 acceptance。
- **修复风险（低/中/高）**: 高。
- **严重程度（低/中/高/严重）**: 高。

### 6-未修复-高-回测与 policy-auto gate 没有 point-in-time 数据可用性契约，look-ahead 测试无法成为准入证明
- **状态**: accepted-candidate
- **位置**: §6.2 price/FX/optimizer/backtest schema（160-164 行）、§6.4（216-220 行）、Slice 5.3-5.4（369-380 行）、§9（500 行）。
- **问题类型**: 契约缺失 / 测试缺口 / 非最优方案。
- **当前写法**: 计划要求“防 look-ahead”、记录数据版本与训练/验证窗口，并列出 `price_snapshots/fx_snapshots`、input fingerprint、walk-forward 与 look-ahead trap 测试；但没有定义 observation timestamp、publication/availability timestamp、revision/as-of policy、universe membership/delisting source、corporate action adjustment、信号形成与下单/成交时点，也未要求 fingerprint 包含这些选择。
- **反例/失败场景**: Q2 财报在 8 月发布但 period end 为 6 月；回测按 period/as-of 或最新修订值在 6 月使用该 Fact，walk-forward split 仍可通过。类似地，当时尚未知的退市股票、拆股/复权、FX close 和次日开盘成交可被当作同日可用。结果能产生确定性 fingerprint 和“look-ahead trap”单测，却仍被错误提升至 Paper/policy_auto admission。
- **为什么有问题**: `policy_auto` 准入顺序把 frozen backtest/out-of-sample 作为外部 live authorization 的前序证据（计划:220）。没有 point-in-time contract，就不能从数据模型和测试判断“防 look-ahead”到底在验证什么，实施者会各自挑选时间语义，直接削弱自动优化硬目标。
- **直接证据**: 计划:160-164 仅列 price/FX/optimizer/backtest 表；:216-220 仅有原则；Slice 5.3:372-374、5.4:378-380、§9:500 均未给出上述时序字段或 acceptance cases。
- **影响**: 回测偏乐观 / 错误开放 policy_auto / 风险后移到 Paper 或 live / review 不可验收。
- **建议改法和验证点**: 在 optimizer/backtest 之前冻结 point-in-time market/research data contract：每条输入的 effective/published/ingested/available-at、revision lineage、universe membership、价格/FX/corporate action adjustment、decision timestamp、execution latency/fill rule 与 data watermark；fingerprint 必须绑定完整数据版本和 availability cut。加入“晚发布 Fact、后来更正、已退市、复权、市场休市/FX 时区、缺价停牌”反例，并断言任一未来可用数据都会 fail closed 或被排除。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### 7-未修复-中-PostgreSQL durable job 与既有 Host SQLite 生命周期之间没有单一 owner 或关联恢复契约
- **状态**: accepted-candidate
- **位置**: §4.1-4.2（73、82 行）、§5（99-119 行）、§6.2 Job tables（169 行）、Slice 2.1-2.2（283-294 行）。
- **问题类型**: 并发恢复风险 / 双真源 / 架构边界。
- **当前写法**: 计划把 PostgreSQL 定为任务与业务状态真源，同时把通用 job 放入 Host；但未定义 job 是否/何时产生 Host Run、`job_run_id <-> host_run_id` 是否一一对应、cancel/timeout/lease/recovery 的 authoritative owner、以及同步 Agent 工作的 receipt 怎样跨两套存储关联。
- **反例/失败场景**: worker 已在 PostgreSQL `leased/running`，其 handler 又触发 Host Agent run；进程在 Host run 成功与 PG receipt 提交之间崩溃。启动后 PG 可能重试并再次调用 Agent，而 SQLite 已记录成功；反向地，Host cancel intent 已落 SQLite 而 PG worker 不知情继续执行。两边各自状态机均可自洽，却没有系统级唯一结论。
- **为什么有问题**: 保留现有 Host SQLite 并不是问题；问题是计划没有给跨 store side effect 的 ownership/幂等关联设计。现有 Host 的 runs、pending turns、outbox 与 permits 都落在 SQLite（`dayu/host/host_store.py:31-122`），而计划明确将 `job_runs/job_attempts/job_events/job_leases` 放入 PostgreSQL（计划:169）。
- **直接证据**: 计划:73、82、99-119、126、169、283-294；`dayu/services/startup_preparation.py:161-192` 当前把 HostStore/Host 作为一个 SQLite 运行时装配，未出现 PG job adapter 或 mapping。
- **影响**: 重复 Agent side effect / 取消未生效 / restart recovery 误判成功或重复执行 / 第二真源。
- **建议改法和验证点**: 在 Slice 2.1 前确定两类 job：纯业务 job 与托管 Agent job 的关系；若后者存在，定义 immutable correlation id、PG job attempt receipt、Host run terminal receipt 的写入顺序与 crash reconciliation。选择一个状态为对外操作的唯一 truth，另一个只能是可重建 projection/receipt。测试四个 crash 点（claim 后、Host run 创建后、外部副作用后、receipt 前）及 SQLite/PG 相反终态。
- **修复风险（低/中/高）**: 高。
- **严重程度（低/中/高/严重）**: 中。

### 8-未修复-中-handoff 的 36-slice 承诺与计划实际 35 个 slice 不一致，缺失边界无法审查
- **状态**: accepted-candidate
- **位置**: 计划 §8（245-479 行）及 handoff 的“36 slices”要求。
- **问题类型**: 范围漂移 / 不可直接实施。
- **当前写法**: 计划没有明示总 slice 数；从 0.1 到 8.4 共列 35 个 `#### Slice` 标题。
- **反例/失败场景**: controller/implementation agent 按 handoff 排期、commit 与 review artifact 追踪 36 个交付单元，但计划只有 35 个，最后一个能力/迁移/wiring 可能被误认为已包含在相邻 slice，形成无 owner 的隐性 work。
- **为什么有问题**: 用户把 36 slices 作为当前计划是否可 code generation 的明确审查对象，同时 §8 规定每 slice 独立 accepted commit。数量不一致使完成定义不可机械验证；这也与 Finding 1 中尚无 owner 的 workspace migration 相吻合，但本 finding 只陈述可直接计数的范围不一致，不假定第 36 个具体应是什么。
- **直接证据**: `rg '^#### Slice ' docs/plans/2026-08-10-investment-platform-restoration.md | wc -l` 的结果为 35；标题范围为 Slice 0.1 至 8.4，计划:245-479。
- **影响**: 实施 Agent 跑偏 / 工作项漏交付 / aggregate review 无法判断完成。
- **建议改法和验证点**: 明确更正 handoff 或计划的总数，并提供 36 项的编号清单、每项唯一 completion predicate 与 dependency；若新增第 36 项，必须独立定义 allowlist/tests/docs，不能把它隐含塞入既有 slice。Controller 应在 re-review 前核对该清单。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

## Open questions

1. 目标是单租户个人平台、同组织多账户，还是多组织 SaaS？这决定 public Fins 材料与私有研究/交易数据的 tenant model，不能由 Slice 7.1 临时选择。
2. “旧 workspace 数据迁移”具体包含哪些 Fins 文档、Host SQLite records、research-template artifacts；哪些需要进入 PostgreSQL，哪些必须永久留在原 owner？需要 controller 明确可迁移集合与不可迁移集合。
3. 真实 Broker 的 vendor/account/market 选择仍是 Slice 8.4 的显式外部前置条件。它不应被合并进本 plan 的 deterministic acceptance；在用户选择前应保持 gated，而不是把 Paper 结果解释为 live readiness。

## Residual risks 与建议跟踪去向

| 风险 | 当前状态 | 建议 destination |
| --- | --- | --- |
| Redis 不可用时的轮询降级 | 计划已有原则，未发现需要单独阻止当前 review 的直接矛盾 | Slice 2.1/2.2：明确 poll cadence、wake-up 丢失恢复和 backlog observability 的验收 |
| S3 失败、partial upload 与 metadata/evidence 不一致 | 未被计划的 composition/locator/atomic boundary 闭合 | 先关闭 Finding 2 与 4，再在 Slice 1.3 增加 MinIO outage、cleanup、restart 与 evidence-read integration tests |
| live Broker 的具体安全与市场规则 | 合理地受独立授权限制，不能以 Paper 代替 | Slice 8.4 的独立 plan review；指定 vendor 后再做 adapter-specific threat model |
| 所有 open H/M/L | 未关闭，不能进入 implementation | Controller adjudication -> 更新 target plan -> Terra + MiMo re-review |

## Open 严重度汇总

- **H**：6（Finding 1-6）
- **M**：2（Finding 7-8）
- **L**：0

在 H/M/L 清零、36-slice 清单与所有缺失契约写入计划并完成双路 re-review 前，不应从 plan review 推进到 implementation。
