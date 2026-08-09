# 公司投研与交易平台恢复计划

- **Work unit**：Investment Platform Restoration
- **分支**：`codex/investment-platform`
- **基线**：`d0ffe223d0f42521bb8a907152c1e8b4ade0125f`
- **状态**：**ACCEPTED / DUAL PLAN RE-REVIEW PASS**
- **目标运行时**：Python 3.11
- **Initial plan reviews**：`docs/reviews/plan-review-20260810-072034-terra.md`（FAIL，6H/2M）、`docs/reviews/plan-review-20260810-072130-mimo-native.md`（PASS-WITH-RISKS，13 observations）
- **Controller fix**：`docs/reviews/plan-fix-20260810-072408-codex.md`
- **Final plan reviews**：`docs/reviews/plan-final-rereview-20260810-074150-terra.md`（PASS，open 0/0/0）、`docs/reviews/plan-final-rereview-20260810-074150-mimo-native.md`（PASS，open 0/0/0）
- **Acceptance**：`docs/reviews/plan-acceptance-20260810-074424-codex.md`

### Revision changelog

- 2026-08-10 initial candidate：恢复完整公司投研与交易平台，定义 9 个 Phase、研究/组合/交易/运营闭环以及 Paper-to-Live gate。
- 2026-08-10 plan-review fix：接受 Terra 1–8 与 MiMo 003–010、012–013 的 material findings；补全 workspace migration、production composition roots、tenant scope、Fins evidence locator、Host/PG 单一状态 owner、point-in-time 数据、订单恢复/kill-switch、slice DAG、集成测试和 live authorization。MiMo 001 的“skeleton 暗示已有实现”、002 的“依赖当前不存在即缺陷”以及 011 的“安全切片过多即过度设计”按事实拒绝，但吸收其可执行性说明；计划现在明确为 greenfield investment domain、37 个独立 slices。
- 2026-08-10 re-review observation fix：接受 Terra复审唯一M-01；0.2收窄为纯settings/composition contract，1.2负责首次PG repository/service实际装配，2.1负责job store装配，2.3显式依赖1.2/1.3/1.4/2.2并负责source handler注册。修正DAG后不存在future-slice import或占位adapter。
- 2026-08-10 accepted closure：Terra与MiM final closure re-review均PASS，open H/M/L=0/0/0；37-slice master plan进入implementation gate，Slice 8.4仍保留独立live authorization。

## 1. 目标与动机

当前仓库已经是一套有严格 Host 治理、财报仓储和双模型研究能力的 Agent，但还不是用户最早规划的完整公司投研与交易平台。本 work unit 的目标不是重写 Dayu，而是把已有研究引擎装入完整的业务闭环：

```text
自动采集事实
-> 严格 Fact / Claim / Evidence
-> 预测、估值、反方与失效条件
-> 组合优化与风险检查
-> 决策候选与审批
-> Paper / Broker 执行
-> 持仓、现金、成交与归因
-> 监控、复盘和再次优化
```

平台的产品目标是提高信息跟踪及时性、研究可追溯性、组合纪律和风险调整后的决策质量。平台不得承诺盈利或保证收益；策略有效性只能用冻结数据集上的 out-of-sample 回测、Paper Trading、风险约束命中率、执行正确性和长期实盘归因来验证。

### 1.1 成功信号

1. 十一组用户硬需求逐项有真实 owner、持久 schema、Service/Host 调用路径和自动测试。
2. 一条公司纵向链路能够从公告/财报/行业资料进入 Fact，经 Claim/Evidence、预测、估值、反方审核，最终形成可供决策的公司卡片和周报。
3. 一条组合纵向链路能够从批准的研究观点生成约束内目标权重、决策候选、审批记录、Paper 订单、成交、现金/持仓更新和月度归因。
4. 调度、队列、lease、retry、恢复、幂等、取消、告警、审计均有持久状态；进程重启不把进行中的任务误判成功。
5. Web、Telegram 和 Obsidian 消费同一 Service 输出，不直接读取 Host 或数据库实现。
6. LLM 永远不能直接调用 Broker；自动交易必须经过确定性 optimizer、risk policy、approval policy 和 execution service。
7. PostgreSQL、Redis、S3-compatible object storage、API、Worker、Scheduler 和 UI 能以生产 Compose 启动，并完成备份恢复与 smoke test。

## 2. 明确范围

以下十一组能力全部属于本 master plan 的硬范围，不能仅列为“未来愿景”：

1. 公告、财报、行业指标和研究资料自动采集。
2. `Fact -> Claim -> Evidence` 证据链。
3. 财务预测、估值情景、反方论证和逻辑失效条件。
4. 持久化调度、任务队列、断点恢复、数据源健康告警。
5. 公司知识图谱、事件影响归因、公司周报。
6. 投资组合、持仓、盈亏、集中度、行业和币种暴露。
7. `buy/add/hold/reduce/sell/avoid/watch` 决策日志。
8. 催化剂、风险、逻辑失效条件自动监控。
9. 压力测试、交易执行账本、月度复盘。
10. Web 控制台、Telegram 通知、Obsidian 导出。
11. 用户权限、审计、备份恢复和生产部署。

自动优化与交易闭环也属于硬范围：当前 work unit 必须实现版本化 optimizer/risk policy、回测、Paper Broker 和三种执行模式；真实券商 adapter 的代码必须服从同一协议和 live admission gate，不能让 Broker SDK 反向污染 domain/Service。

平台数据面按 organization/tenant 隔离。首次部署自动建立一个 default organization，但 schema、repository scope、worker、search、backup 和 audit 从第一张业务表开始都必须携带 `TenantId`；不能以“个人部署”名义把 tenant 条件推迟到 UI/RBAC 阶段。

## 3. Non-goals 与安全边界

- 不重写已有 Agent、Host、Fins、research-template、AAPL acceptance 或 Streamlit/FastAPI 框架。
- 不把共享聊天中声称的 v1.0/v1.0.1 当作已交付代码或迁移来源。
- 不引入 Next.js、Neo4j、Kafka 或其它当前需求没有证明必要性的第二套平台。
- 不让 UI 直连数据库、Host 实现或 Agent；稳定依赖仍为 `UI -> Service -> Host -> Agent`。
- 不让投资域读取 `workspace/portfolio/...` 私有文件；财报和研究材料存取只能经 `dayu.fins.storage` 协议。
- 不让向量检索结果自动成为证据；所有 Claim 必须最终指向可定位的 Document/Fact/Evidence locator。
- 不让 LLM 直接生成可提交订单、绕过 risk policy、修改 approved policy 或持久化 authoritative Fact/Claim。
- 不在没有账户级授权、kill switch、Paper 验收和外部 live gate 的情况下启用真实自动交易。
- 不承诺收益率；优化目标与指标必须版本化并可复现。

## 4. 当前仓库直接证据

### 4.1 可复用能力

- `dayu/web/fastapi_app.py` 与 `dayu/web/streamlit_app.py` 已提供 FastAPI/Streamlit UI 入口。
- `dayu/web/routes/` 已通过 Service Protocol 受理 chat、prompt、Fins、run、session 和 SSE。
- `dayu/services/` 已是 UI 与 Host 之间的应用服务层。
- `dayu/host/` 已有 session/run/pending-turn/reply-outbox、lease、取消、并发 lane、启动恢复和 SQLite 持久化。
- `dayu/fins/storage/` 已有 company/source/processed/blob/maintenance 窄仓储；这是材料存取唯一真源。
- `dayu/fins/` 已有多市场下载、解析、XBRL/Docling、source fingerprint 和 processing pipeline。
- `dayu/cli/commands/_research_template_*` 已有 workbook、bundle、portfolio materialization、dry-run monitoring plan、status snapshot 和 scheduler manifest。
- `dayu/services/write_service.py` 及内部流水线已有双模型研究、audit/confirm/repair、预算、usage 和可恢复产物。
- `utils/investment_agent_acceptance*.py` 已提供 AAPL 公司研究纵向验收，可作为平台质量 gate，而不是平台数据库真源。

### 4.2 已证实缺口

- Host 当前 authoritative store 是 SQLite；没有投资域 PostgreSQL schema、Alembic 迁移或 PostgreSQL durable job queue。
- 没有 Fact/Claim/Evidence、Forecast、Scenario、Graph、EventImpact 等正式投资域 owner。
- 没有真实 Portfolio/Account/Position/Cash/Order/Fill/Decision/Approval/RiskPolicy schema。
- 现有 research portfolio 是“研究目标清单”，不是资金/持仓组合。
- monitoring plan 固定 disabled/unbound/dry-run，没有生产数据绑定、触发、通知或交易风险联动。
- Streamlit 主要覆盖财报、聊天和报告；FastAPI `/write` 仍是骨架，缺公司 cockpit、组合、决策和监控 API。
- 没有 RBAC、append-only API audit、Telegram、Obsidian、备份恢复或完整生产 Compose。
- 没有 PostgreSQL/pgvector、Redis 或 S3-compatible object storage 依赖与组合根。

`dayu/investment/` 完全不存在，因此本计划中的 investment domain 是明确的 greenfield package，不是对已有 investment skeleton 的增量补丁。已有 Dayu/Fins/Host/Web 是可复用平台骨架；所有投资业务 schema、repository 和 Service 都从零建立。

## 5. 目标架构与依赖方向

```text
dayu.web / notification adapters / export adapters          (UI)
                    |
                    v
dayu.services.investment_* / portfolio_* / execution_*      (Service)
                    |
                    v
dayu.host generic durable jobs / leases / events / recovery  (Host)
                    |
                    v
dayu.engine / dayu.services.write / Agent model execution     (Agent)

dayu.investment.domain       pure domain contracts
dayu.investment.storage      repository protocols + PostgreSQL implementations
dayu.investment.connectors   source/broker adapter protocols and bounded adapters
dayu.fins.storage            original filing/material bytes and processed truth
```

硬依赖规则：

- `domain` 不依赖 Web、Service、Host、Agent、SQLAlchemy、Broker SDK。
- `storage protocols` 只依赖 domain；SQL 实现依赖协议和基础设施，不向上暴露 ORM row。
- Service 编排 domain、repositories、Host protocol 和 Fins Service Protocol，不直接打开 workspace 文件。
- Host 只认识通用 `JobSpec/JobRun/Lease/JobEvent`，不导入投资业务类型。
- Agent 只返回候选 payload；Service 通过 strict parser、来源闭合和审批规则后才持久化。
- UI、Telegram、Obsidian 只调用 Service Protocol。
- Redis 用于事件 fan-out、短期 cache 和 worker wake-up；PostgreSQL 是任务与业务状态真源，不把 Redis 当 durable truth。
- 对象存储的财报/材料实现仍放在 `dayu.fins.storage`；投资域只保存安全 locator、hash 和 repository id。

## 6. 技术与数据决策

### 6.1 数据面

- PostgreSQL 16 是投资域、用户权限、任务、审计、组合和订单账本真源。
- SQLAlchemy 2.x + psycopg 3 提供同步事务边界；FastAPI 通过现有 Service 调用约定运行短事务，长任务只入队。
- Alembic 管理全新 platform schema；旧 workspace 数据迁移必须作为 `dayu-cli init` 的 `workspace_migrations` 插件显式导入，不做隐式兼容读取。
- `pgvector` 只保存 embedding 和 document/fact id；Evidence 仍以 relational FK + exact locator 为权威。
- S3-compatible storage 默认 MinIO；新增的 Fins blob repository 实现遵循现有 `DocumentBlobRepositoryProtocol`。
- Redis 不保存不可恢复业务事实；Redis 不可用时 API 仍可入 PostgreSQL 队列，worker 通过轮询退化运行。

**Host SQLite 与 PostgreSQL 的唯一 owner**：

- 现有 Host SQLite 永久继续拥有 conversation/session、Agent run、pending turn、reply outbox、permit、Agent cancellation 与其恢复状态；本 work unit 不 dual-write、不迁移、不复制这些表到 PostgreSQL。
- PostgreSQL 永久拥有投资业务、platform job definition/run/attempt/lease/event、source health、notification outbox 与交易状态；它不覆盖 Host run 细节。
- 纯业务 job 只有 PostgreSQL 状态。需要调用 Agent 的 job attempt 生成 immutable `AgentRunCorrelation(tenant_id, job_run_id, attempt_id, host_run_id, idempotency_key)`；PostgreSQL job 是外层调度真源，Host SQLite run 是模型执行真源。
- Agent job 的 crash reconciliation 固定为 query-before-retry：已有 Host terminal success 时只补 PG receipt；Host running/pending 时恢复或等待同一 run；Host terminal failure 时按 retry policy 创建新 attempt；找不到关联且没有外部 receipt 时才允许新建 run。禁止跨库事务和盲目重放 Agent side effect。
- cancel 的外部真源是 PostgreSQL job cancel intent；worker 持续把它投射为 Host cancel intent。Host 的更早 terminal result仍可写回 job receipt，但不得把 cancel 后的新 side effect 标记成功。

**Redis degradation**：

- Redis wake-up/pub-sub 只是提示。worker 每次都从 PostgreSQL claim；丢消息不会丢任务。
- 配置真源为 `PlatformQueueSettings`：默认 `poll_interval_seconds=5`、`redis_health_interval_seconds=30`、`redis_failure_threshold=3`，均必须为有限正数并进入启动快照。
- 达到失败阈值后进入 `polling_degraded`，继续按 PostgreSQL poll；Redis 健康检查恢复后回到 `event_assisted`。模式切换写 audit/metrics，不改变 lease/fencing 语义。

### 6.2 核心 schema

所有表使用 UUID/稳定业务键、UTC 时间、乐观版本号和 append-only event/audit。金额使用 `Decimal` + currency，数量禁止 float。

**Identity / tenancy / source**

- `organizations`、`users`、`roles`、`permissions`、`user_roles`、`api_tokens` 先于其它私有表建立。
- `TenantScope` 由已认证 `Principal` 产生；repository 每个 read/write/search 方法都必须显式接收 scope，不能从全局变量或 ticker 推断 tenant。
- `companies`、`securities` 与原始 Fins document identity 可作为公共 reference；source subscription、Fact/Claim、forecast、graph projection、portfolio、job、decision/order、report、audit 全部带 non-null `tenant_id`。公共 reference 到私有 projection 只允许从 tenant 私有表指向公共表，禁止反向 FK。
- PostgreSQL RLS 对私有表 default-deny；连接事务必须 `SET LOCAL app.tenant_id`，repository 仍保留 tenant predicate，形成双层隔离。migration/admin task 使用单独、审计的 bypass role。
- `companies`、`securities`、`source_definitions`、`source_subscriptions`、`source_sync_runs`、`source_health_snapshots`。
- Source health：`healthy -> degraded -> failing -> disabled`；只有 operator 能从 disabled 重新启用。

**Evidence / research**

- `facts`：immutable observation，包含 tenant/company、强类型 evidence locator、fact type、value/unit/currency、effective period、published_at、ingested_at、available_at、revision lineage、extractor version、verification status。
- `claims` + `claim_versions`：statement、closed `confidence_band=low/medium/high`、可选已校准 probability、impact horizon、valid_until、status、invalidation rule、author/approver；版本不可覆盖。confidence 只是信息，不自动批准 Claim。
- `evidence_links`：`supports/contradicts/context`，绑定 ClaimVersion 到 Fact/Document exact locator。
- `claim_conflicts` 显式记录 material contradiction。矛盾 Claim 可以并存，但 unresolved material conflict 会阻止 forecast/decision promotion；只能由新 evidence + 人工 reviewer resolve，不能按时间或模型分数静默覆盖。
- `research_theses`、`counter_theses`、`thesis_changes`。
- Agent 输出先进入 `research_candidates`：`proposed -> validated -> accepted/rejected`；只有 Service 可以 promote。

**Forecast / valuation / event / graph**

- `forecast_models`、`forecast_versions`、`forecast_assumptions`、`forecast_metrics`。
- `valuation_scenarios`：bear/base/bull 或自定义场景，绑定 approved forecast version、price snapshot 和公式版本。
- `event_impacts`：方向、期限、影响变量、low/base/high 区间和 evidence links。
- `knowledge_nodes`、`knowledge_edges` 是从 authoritative ids 派生的 projection；重建不得改原 Fact/Claim。
- `company_reports` 保存 Markdown/object locator、covered ids 和 generator version。

**Portfolio / decision / execution**

- `portfolios`、`accounts`、`position_lots`、`position_snapshots`、`cash_ledger`、`price_snapshots`、`fx_snapshots`、`universe_memberships`、`corporate_actions`。所有 market/research input 含 `effective_at/published_at/ingested_at/available_at/revision_id`。
- `optimizer_policies`、`optimizer_runs`、`backtest_runs`：目标、约束、input fingerprint、output weights、turnover、risk metrics。
- `decision_candidates` action 固定为 `buy/add/hold/reduce/sell/avoid/watch`；必须绑定 thesis/forecast/scenario/evidence window 和 optimizer run。
- `decision_approvals` 保存 actor、role、policy version、scope、expiry 和 signature hash。
- `order_intents`、`broker_orders`、`fills`、`reconciliation_runs`；订单事实不可覆盖，只追加状态事件。
- `watch_conditions`、`watch_evaluations`、`risk_alerts`。

**Operations / security**

- `job_definitions`、`job_runs`、`job_attempts`、`job_events`、`job_leases`。
- `audit_events` 只追加 actor/action/resource/result/request-id/timing/safe metadata，不保存密码、token、prompt 或完整请求正文。

### 6.3 Fins Evidence Locator 与 Agent trust boundary

`EvidenceLocator` 的 owner 是 `dayu.fins`，investment domain 只能持有其无路径、可序列化 projection，禁止自行拼 bucket/workspace key。projection 精确字段为：

- `repository_id`：当前 Fins repository composition 的稳定 id；
- `ticker`、`document_id`、`source_kind`；
- `artifact_kind=source|processed`、`document_version`、`source_fingerprint`；
- `primary_content_sha256`；
- `locator_kind=page|table_cell|section|xbrl_fact|document` 以及对应的严格 locator payload；
- `locator_content_sha256`，验证 locator 指向的原始片段未漂移。

Fins Service Protocol 新增 `resolve_evidence_locator()`、`validate_evidence_locator()` 和 `read_citation_projection()`；FS/S3 两种 repository 必须产生相同 canonical projection。逻辑删除、重处理、hash drift、同 document id 不同 source kind、跨 ticker/tenant 均 fail closed。investment domain 不导入 `dayu.fins.storage` 实现或 handle。

Agent 输出只能写 `ResearchCandidate`。Promotion 同时要求：strict schema、tenant/company、Fins locator、Fact unit/period、evidence supports/contradicts、source freshness全部闭合。`confidence_band` 不构成批准阈值；Claim approval 由明确 permission 的 reviewer 完成。`valid_until` 到期自动转 `review_required` 并阻止新 forecast/decision 使用，不自动 supersede。Material conflict 未 resolve 时下游 fail closed。

### 6.4 状态机

**Job**

```text
scheduled -> queued -> leased -> running -> succeeded
                              \-> retry_wait -> queued
                              \-> failed | cancelled | timed_out
```

lease 过期只允许重新取得执行权，不能把未知副作用重复标为成功；每个 handler 必须有幂等键和 receipt。

**Claim version**

```text
draft -> in_review -> approved -> review_required -> superseded
                  \-> rejected
approved -> invalidated
```

**Decision / execution mode**

- `advisory`：止于候选，不创建 order intent。
- `approval_required`：risk pass 后等待具备权限的人批准。
- `policy_auto`：只有 account + strategy 的 auto authorization 有效、Paper gate 通过、kill switch 关闭时，确定性 policy 可以代替逐笔人工批准；LLM 仍无执行权限。

**Decision aggregate**：`candidate -> risk_checked -> awaiting_approval -> approved`，旁路为 `blocked/rejected/expired`。唯一键为 `(tenant_id, portfolio_id, candidate_fingerprint)`；approval 唯一绑定 decision version、risk snapshot、optimizer run、mode、actor/policy 和 expiry。

**OrderIntent aggregate**：只由 approved decision transition 创建，唯一键 `(tenant_id, account_id, decision_version, intent_sequence)`；状态 `staged -> dispatching -> dispatched`，旁路 `blocked/cancelled/expired/dispatch_unknown`。每次 `dispatching` 取得 CAS version + fencing token。

**BrokerOrder aggregate**：以 `(tenant_id, broker_account_id, client_order_id)` 唯一；状态 `submission_unknown|acknowledged|partially_filled|filled|cancel_pending|cancelled|rejected|expired`。Broker event 以 `(broker_order_id, broker_event_id)` 去重，late fill 永远可在 cancelled 后进入 ledger，不能丢弃或改写历史。

**Ledger / reconciliation aggregate**：Fill 只追加且以 broker execution id 去重；同一 DB transaction 写 fill、cash ledger、position lot event 与 reconciliation watermark。`reconciliation_required` 是控制状态，不替代 broker/ledger terminal；reconcile 只追加差异决议和修复 event。

提交语义固定为 query-before-retry：broker 接受但本地超时后进入 `submission_unknown`，新 attempt 先用 client order id 查询；找到则关联原单，明确不存在才在同一 idempotency key 下重试。禁止在不确定状态换 client order id。

每次 broker side effect 前 Service 必须重新读取 PostgreSQL `execution_controls`、approval expiry、account/strategy authorization 与 risk limit；Broker adapter 的 `submit/cancel` 还必须接收不可伪造的 `ExecutionAuthorizationSnapshot`，并通过注入的 `ExecutionControlReaderProtocol` 再读 PostgreSQL version。Redis 只广播 invalidation，不是真源。

Kill switch scope 为 global/tenant/account/strategy，PostgreSQL append-only control event + current projection 是唯一真源。开启时取消未 dispatch intent并阻止新 side effect；已 acknowledged/partially-filled 的订单默认 `hold_and_reconcile`，不得自动 cancel，因为 cancel 与 late fill本身有风险。具备 trader 权限的 operator 可在审计后单独发 cancel。关闭 kill switch 需要双人/双角色审批并生成新 authorization version。

**Watch**

```text
draft -> armed -> triggered -> acknowledged -> resolved
                 \-> disabled
```

### 6.5 Point-in-time 数据与自动优化

Backtest/optimizer 的每条输入必须有 `effective_at`（经济事实所属时点）、`published_at`（外部公开时点）、`ingested_at`、`available_at`（本平台可用时点）、`revision_id` 和 prior revision link。任何一步计算只允许 `available_at <= decision_at`；回测绝不能用 period end 代替公开时点。

`MarketDataSnapshot` 还绑定 universe membership/delisting、raw/adjusted price、corporate action version、FX market/timezone、trading calendar、halt/missing marker。`BacktestPolicy` 绑定信号形成时点、下单延迟、成交价规则、滑点/费用和缺价处理。完整 data watermark、revision set、universe、adjustment和 fill policy进入 fingerprint。

- Optimizer 只使用 approved forecast/scenario、可追溯 price/FX、持仓和版本化 policy；不得直接消费自由文本 LLM 输出。
- 默认目标为约束下的 risk-adjusted objective；输出必须包含预期收益输入、协方差/风险输入、target weights、turnover、成本估计和约束余量。
- 硬约束至少包括单证券/行业/币种上限、gross/net exposure、cash floor、最大 turnover、流动性/最小交易单位、价格 freshness、max drawdown/stop、禁止交易清单和 market-hours。
- backtest 必须使用 expanding/rolling walk-forward，训练/validation/test 时间窗不重叠；晚发布 Fact、事后更正、退市、拆股复权、停牌、休市/FX 时区和缺价均有 adversarial fixture；只报告，不自动启用策略。
- `policy_auto` admission 顺序固定：unit tests -> frozen backtest -> out-of-sample -> Paper Trading -> operator review -> account-scoped live authorization。

## 7. 十一组需求到 owner/证据映射

| 需求 | Authoritative owner | 最终验收证据 |
| --- | --- | --- |
| 自动采集 | Fins protocols + source services + durable jobs | 多源 fixture、幂等 sync、restart、health transition |
| Fact/Claim/Evidence | investment domain/storage/service | strict schema、locator closure、version/approval tests |
| 预测/估值/反方/失效 | forecast/thesis services | deterministic formulas、scenario diff、counter thesis gate |
| 调度/队列/恢复/健康 | Host job protocols + PostgreSQL store | crash/lease/retry/idempotency/health alert integration |
| 图谱/事件/周报 | projection/report services | rebuild stable ids、impact evidence、weekly report closure |
| 组合/持仓/暴露 | portfolio ledger/service | fill/cash/lot accounting、concentration/FX property tests |
| 决策日志 | decision service | seven actions、cross-company rejection、approval audit |
| 自动监控 | watch/risk service + scheduler | trigger/debounce/ack/resolve/notification tests |
| 压测/执行/复盘 | optimizer/execution/attribution services | scenario shock、Paper fills、idempotency、monthly attribution |
| Web/Telegram/Obsidian | UI adapters | API contract、Streamlit smoke、dedupe、safe export |
| 权限/审计/备份/部署 | auth/audit/ops | RBAC matrix、secret scan、restore roundtrip、Compose smoke |

## 8. Implementation phases 与 slices

每个 slice 都必须单独执行 implementation -> code review -> fix -> re-review -> accepted commit。Implementation agent 只能修改该 slice allowlist；发现 schema、ownership、反向依赖或外部协议 gap 必须停报。

本计划共 **37 个 slices**。数量来自真实 owner 与高风险边界，不以压缩提交数为目标：schema/tenant、Fins evidence、durable jobs、optimizer、execution、RBAC 和 recovery 必须独立 review，不能为了减少 slices 把多个真源揉成一个大改动。

### 8.0 Slice dependency DAG 与集成 lane

```text
0.1 -> 0.2 -> 1.1 -> 1.2
          \-> 1.3 -> 1.4
1.2 + 1.4 -> 1.5
0.2 + 1.1 -> 2.1 -> 2.2
1.2 + 1.3 + 1.4 + 2.2 -> 2.3
1.2 + 1.3 + 2.3 -> 3.1 -> 3.2 -> 3.3

3.1 -> 4.1 -> 4.2 -> 4.3 -> 4.4 -> 4.5
1.2 -> 5.1 -> 5.2 -> 5.3 -> 5.4 -> 5.5
5.5 -> 6.1 -> 6.2
4.3 + 5.2 + 2.2 -> 6.3
5.1 + 6.1 -> 6.4
1.1 -> 7.1
4.5 + 7.1 -> 7.2 -> 7.4
5.5 + 6.2 + 7.1 -> 7.3 -> 7.5
4.5 + 6.3 + 6.4 + 7.1 -> 7.6
1.4 + 2.2 + 7.1 -> 8.1 -> 8.2
all deterministic slices -> 8.3 -> 8.4 external gate
```

- 0.1 是唯一没有 predecessor 的 slice；其它每个 slice 必须列出的全部 predecessor accepted 后才能开始。
- 每个 Phase 结束运行 `tests/integration/investment/` 中对应纵向 lane；测试统一标记 `integration`，默认 unit lane排除，受影响 PR 必跑相关 integration，nightly 跑 PostgreSQL/Redis/MinIO/Compose 全集。
- Slice artifact 必须列出本 slice 的 predecessor accepted commit、production composition root、真实 integration command 和未运行的外部动作。

### Phase 0 — 架构护栏与数据组合根

#### Slice 0.1：Investment domain skeleton 与 dependency guard

- **Objective**：建立纯 domain 包和导入方向测试，不实现业务行为。
- **Allowed**：`dayu/investment/__init__.py`、`dayu/investment/domain/__init__.py`、`dayu/investment/domain/identifiers.py`、`dayu/investment/domain/money.py`、`dayu/investment/README.md`、`tests/investment/test_architecture_boundaries.py`、`dayu/README.md`、`tests/README.md`。
- **Types**：`TenantId/CompanyId/SecurityId/PortfolioId/AccountId` newtypes、`Principal/TenantScope`、`Money`、`Quantity`、UTC helpers。
- **Invariants**：无 SQLAlchemy/FastAPI/Host imports；Decimal finite/non-negative rules；中文 docstrings。
- **Tests**：dependency AST guard、Money/Quantity strict tests、pyright/Ruff、单文件 coverage >=80%。
- **Stop**：现有模块必须反向 import investment domain 才能闭合时停报。

#### Slice 0.2：Platform settings 与 composition contract

- **Allowed**：`dayu/investment/config.py`、`dayu/investment/composition.py`、`dayu/services/protocols.py`、`dayu/startup/platform.py`、`dayu/services/startup_preparation.py`、`tests/investment/test_platform_config.py`、`tests/application/test_service_startup_preparation.py`、`README.md`、`dayu/README.md`。
- **Decision**：配置只记录 env name，不回显 secret；production 缺 DSN/object/redis/auth key fail-fast；dev 可显式使用 in-memory adapters。
- **Completion**：只建立strict settings、`PlatformCompositionProviderProtocol`、空/禁用状态和startup注入点；本slice不导入或构造尚不存在的PG/Fins/job repository。启用platform但未注入provider时fail-fast；组合根只能接收/暴露Service Protocol。

### Phase 1 — PostgreSQL 与材料对象存储

#### Slice 1.1：ORM、tenant/auth foundation 与 Alembic fresh schema

- **Allowed**：`pyproject.toml`、`requirements*.txt`、`alembic.ini`、`dayu/investment/storage/db.py`、`dayu/investment/storage/models_identity.py`、`dayu/investment/storage/models_auth.py`、`dayu/investment/storage/migrations/**`、`tests/investment/test_platform_migrations.py`、`README.md`。
- **Dependencies**：锁定 SQLAlchemy 2.x、psycopg 3、Alembic 与 PostgreSQL 16 compatible ranges；新增依赖必须在 Python 3.11 min-compat lane 与当前 full suite验证。
- **Functions/types**：engine/session factory、metadata naming convention、organization/user/role/permission、identity/source tables、RLS policy和审计 bypass role。
- **Failure**：migration 中断 rollback；production 禁止自动 `create_all`。
- **Validation**：empty PostgreSQL upgrade/downgrade/upgrade、default organization、private table non-null tenant、RLS default deny、cross-tenant SQL reject、schema exact、pyright/Ruff。

#### Slice 1.2：Repository protocols 与 identity/source repositories

- **Allowed**：`dayu/investment/storage/protocols.py`、`dayu/investment/storage/postgres_identity.py`、`dayu/investment/domain/source.py`、`dayu/investment/composition.py`、`dayu/startup/platform.py`、`dayu/services/startup_preparation.py`、`tests/investment/test_identity_repositories.py`、`tests/application/test_service_startup_preparation.py`。
- **Call path**：Service -> protocol -> transaction-scoped repository；每个方法显式接收 `TenantScope`，事务同时 `SET LOCAL app.tenant_id`。
- **Completion**：首次production provider只装配本slice已经存在的identity/source repositories与窄Service Protocol；不得预注册jobs/evidence/portfolio等future-slice owner。
- **Tests**：unique ticker/security、source subscription、optimistic conflict、transaction rollback、tenant predicate/RLS 双层隔离、public reference/private projection、startup black-box确认真实PG provider且没有placeholder/future import。

#### Slice 1.3：Fins Evidence Locator 与 citation projection

- **Allowed**：`dayu/fins/domain/evidence_locator.py`、`dayu/fins/service_runtime.py`、`dayu/services/protocols.py`、相关 Fins domain/service tests、`dayu/fins/README.md`。
- **API**：`resolve_evidence_locator()`、`validate_evidence_locator()`、`read_citation_projection()`；projection 精确实现 §6.3，不暴露本地路径或 bucket key。
- **Tests**：source/processed/page/table/XBRL locator、FS canonical projection、hash/version/reprocess drift、wrong ticker/source kind、logical deletion、unknown locator、citation bytes。
- **Stop**：现有仓储 identity 不能稳定表达 repository/document/version/fingerprint/content hash 时停报，不得在 investment domain 发明第二 locator。

#### Slice 1.4：S3-compatible Fins blob repository

- **Allowed**：现有 `dayu/fins/storage` 中新增 S3 实现/装配文件、`dayu/fins/storage/__init__.py`、`dayu/fins/service_runtime.py`、`dayu/services/startup_preparation.py`、相关 Fins/runtime/startup tests、`dayu/fins/README.md`、依赖文件。
- **Dependencies**：只选一个 S3 client并锁Python 3.11兼容版本；MinIO用于integration环境但不成为domain依赖。
- **Invariant**：不改 protocol 语义；checksum/locator/atomic put；investment 不读 bucket path。
- **Tests**：真实 MinIO integration、hash mismatch、partial upload cleanup、FS/S3 evidence projection相同、`DefaultFinsRuntime.create()` 和 startup composition选择正确 backend、existing FS regression。

#### Slice 1.5：旧 workspace 显式导入迁移

- **Allowed**：`dayu/cli/workspace_migrations/**`、`dayu/cli/commands/init.py`、CLI parser/dispatch、`tests/cli/test_workspace_migrations.py`、`tests/integration/investment/test_workspace_migration.py`、`README.md`、`dayu/README.md`。
- **Scope**：只导入可验证的 company/security/source identity 和 research bundle locator/hash；Host SQLite conversation/run 与 Fins raw/processed bytes继续由原 owner保存，绝不复制进 platform tables。
- **Contract**：显式 `dayu-cli init --import-existing-workspace`；migration id + source root fingerprint + schema version唯一；先 stage/validate，再单事务发布；成功 marker使重复执行为 no-op。
- **Tests**：empty workspace、现有 fixture、partial/invalid bundle、interrupted import rollback、rerun idempotency、marker/fingerprint drift、不会搬运 Host/Fins bytes、跨 tenant target reject。

### Phase 2 — 自动采集、持久任务与健康

#### Slice 2.1：Generic durable Job contract 与 PostgreSQL queue

- **Allowed**：`dayu/host/job_contracts.py`、`dayu/host/job_service.py`、`dayu/host/protocols.py`、`dayu/investment/storage/postgres_jobs.py`、`dayu/investment/composition.py`、`dayu/startup/platform.py`、`dayu/services/startup_preparation.py`、migration、tests、`dayu/host/README.md`。
- **API**：enqueue/claim/heartbeat/complete/fail/cancel/recover；`JobHandlerProtocol`；Agent handler明确创建/读取 `AgentRunCorrelation`。
- **Invariants**：`FOR UPDATE SKIP LOCKED`、lease token fencing、attempt receipt、idempotency key；PG job与Host run不dual-write，cross-store recovery只走query-before-retry。
- **Completion**：把PG job store与job service加入既有platform provider；不启动scheduler/worker，也不注册业务handler。
- **Tests**：two-worker race、expired lease、retry/backoff、cancel-before/while-run、crash recovery、Host success补PG receipt、Host pending等待、Host failure新attempt、missing correlation安全重建、禁止双重模型执行、startup provider暴露真实job service。

#### Slice 2.2：Scheduler、worker process 与 Redis wake-up

- **Allowed**：`dayu/host/scheduler.py`、`dayu/host/worker.py`、`dayu/cli/commands/platform.py`、CLI parser/dispatch、`dayu/startup/platform.py`、`dayu/services/startup_preparation.py`、tests、README/host README。
- **Dependencies**：锁定Redis client兼容版本；没有Redis package或服务时production fail-fast，只有显式dev/test profile可纯PG polling。
- **Call path**：schedule tick -> enqueue -> worker claim -> Service handler -> receipt/event。
- **Tests**：timezone/DST、misfire、disabled schedule、restart、signal graceful stop、Redis丢消息仍由PG poll领取、连续3次失败转polling_degraded、恢复转event_assisted、两模式相同lease/fencing。

#### Slice 2.3：Source connectors、sync service 与 health state

- **Allowed**：`dayu/investment/domain/source.py`、`dayu/investment/connectors/source.py`、`dayu/services/investment_sources.py`、storage models/repository/migration、`dayu/investment/composition.py`、`dayu/startup/platform.py`、`dayu/services/startup_preparation.py`、worker registry、tests。
- **Adapters**：现有 Fins SEC/SSE/HKEX/其它已支持市场通过 Fins Service；RSS/industry/manual adapters只产 typed ingestion request，原文仍经 Fins storage。
- **Failure**：unknown form/source, stale data, partial batch, provider rate limit；不把媒体线索当 verified fact。
- **Completion**：source health transition 和 deduped alert event 持久化；handler在production composition registry注册，source sync receipt绑定Fins locator与PG job attempt。

### Phase 3 — Fact / Claim / Evidence 与检索

#### Slice 3.1：Strict evidence domain 与 repositories

- **Allowed**：`dayu/investment/domain/evidence.py`、`storage/models_evidence.py`、repository、migration、tests。
- **Types**：Fact, Claim, ClaimVersion, ClaimConflict, EvidenceLink, ResearchCandidate；closed enums。
- **Invariants**：immutable fact/version；evidence company/document/locator closure；cross-company link reject；confidence只表达证据强度不产生approval；expired Claim进入review_required；unresolved material conflict阻止forecast/decision。
- **Tests**：unknown/missing/NaN/date/unit/currency、version race、approve/reject/invalidate、confidence不能自动approve、valid_until到期、support/contradict conflict并存与人工resolve。

#### Slice 3.2：Candidate promotion Service 与 Agent boundary

- **Allowed**：`dayu/services/investment_research.py`、`dayu/services/protocols.py`、`dayu/investment/domain/candidate_parsing.py`、tests。
- **Call path**：Agent output -> strict candidate parser -> Fins locator validation -> candidate -> human/service promotion -> authoritative records。
- **Failure**：no evidence, stale source, unsupported material claim, cross-ticker evidence -> rejected candidate + audit, never authoritative Fact。

#### Slice 3.3：pgvector projection 与 evidence search

- **Allowed**：embedding domain/protocol、PostgreSQL vector repository/migration、search Service、tests、dependency files。
- **Dependencies**：锁定pgvector client/extension compatibility；migration显式检查extension availability，禁止静默退化为不兼容向量格式。
- **Invariant**：vector hit only returns candidates; query result always includes authoritative ids and score; no silent fallback to uncited prose.
- **Tests**：tenant/company isolation、dimension mismatch、stale embedding rebuild、exact locator retrieval。

### Phase 4 — Forecast、valuation、thesis、graph 与 company report

#### Slice 4.1：Forecast/Scenario versioned contracts

- **Allowed**：forecast domain/models/repository/migration/tests。
- **Types**：ForecastModel/Version/Assumption/Metric, ValuationScenario；formulas use Decimal and named units.
- **Tests**：version diff、bear/base/bull ordering not assumed、evidence binding、price/as-of freshness。

#### Slice 4.2：Deterministic valuation and event impact Service

- **Allowed**：`dayu/services/investment_forecast.py`、`investment_events.py`、protocols、tests。
- **Call path**：approved facts/assumptions -> formula engine -> scenario metrics -> event impact ranges。
- **Failure**：missing unit/period, circular formula, unapproved assumption, stale price fail closed。

#### Slice 4.3：Thesis/counter-thesis/invalidation Service

- **Allowed**：thesis domain/models/repository/service/tests/migration。
- **Invariant**：formal thesis requires supporting and contradicting evidence query, explicit falsifier and valid_until; change history append-only。

#### Slice 4.4：Knowledge graph projection

- **Allowed**：graph domain/models/repository/service/tests/migration。
- **Decision**：PostgreSQL edge projection, no Neo4j；stable node id from authoritative id；rebuild marks obsolete edges inactive。
- **Tests**：idempotent rebuild、cycle allowed but duplicate edge rejected、source deletion does not erase history。

#### Slice 4.5：Company cockpit read model 与 weekly report

- **Allowed**：company query/report service、report model/repository、tests。
- **Output**：thesis、counter-thesis、variables、forecast/valuation、catalysts、risks、invalidation、new facts、source health、changes。
- **Tests**：as-of snapshot、citation closure、no-evidence section fail、Markdown object hash。

### Phase 5 — Portfolio、optimizer、决策与风险

#### Slice 5.1：Portfolio/Cash/Position ledger

- **Allowed**：portfolio domain/models/repositories/migration/service/tests。
- **Events**：cash deposit/withdrawal/fee/dividend/fill；positions derived from ledger, not mutable counters。
- **Tests**：FIFO/average-cost policy explicit、multi-currency FX、partial sell、fees、corporate action placeholder stop、property-based conservation。

#### Slice 5.2：Exposure/PnL/risk snapshots

- **Allowed**：portfolio analytics service/domain/tests。
- **Metrics**：market value, cost, realized/unrealized PnL, gross/net, top1/top3, industry/currency, missing/stale prices。
- **Failure**：missing FX/price produces incomplete status, never zero value.

#### Slice 5.3：Optimizer policy 与 deterministic optimizer

- **Allowed**：optimizer domain/service/repository/migration/tests、numeric dependency if required。
- **Input**：approved expected return/risk/cost/liquidity + current ledger + policy version；所有数据都带 point-in-time availability envelope。
- **Output**：target weights, trade deltas, objective, constraints/slacks, fingerprint。
- **Tests**：determinism、infeasible policy、concentration/cash/turnover/liquidity/FX constraints、effective但当时尚未published/ingested/available的输入拒绝、revision重放稳定。

#### Slice 5.4：Backtest and Paper admission

- **Allowed**：backtest domain/service/repository/job handler/tests。
- **Metrics**：CAGR（仅历史描述）、volatility、Sharpe/Sortino、max drawdown、turnover、cost、benchmark delta；明确不代表未来收益。
- **Contract**：run fingerprint必须包含universe membership、delisting、corporate action、FX、trading calendar、market close、fill/latency/slippage/cost policy及所有input revision。
- **Tests**：walk-forward split、announcement-after-close、late filing、revised fundamentals、look-ahead trap、delisting/missing price、split/dividend、FX staleness、cost sensitivity、input fingerprint。

#### Slice 5.5：Decision candidate / risk / approval state machine

- **Allowed**：decision/risk/approval domain/models/repositories/migration/services/tests。
- **Rules**：seven actions；candidate binds optimizer + thesis + scenario + evidence window；risk checks deterministic；RBAC approval scoped/expiring；实现 §6.4 Decision 与 OrderIntent 两个独立 aggregate/unique key/CAS/fencing。
- **Tests**：cross-company/portfolio reject、stale evidence、policy change、expired approval、duplicate candidate/intents、concurrent dispatch CAS、kill switch、mode transitions。

### Phase 6 — 执行、监控、归因

#### Slice 6.1：Broker protocol 与 Paper Broker

- **Allowed**：`dayu/investment/connectors/broker.py`、paper adapter、execution domain/service/repository/migration/tests。
- **Protocol**：submit/cancel/get/list fills/reconcile；idempotency key required；adapter never accepts raw LLM payload；实现 §6.4 BrokerOrder、Fill/Ledger/Reconciliation aggregates。
- **Tests**：duplicate submit、accept-then-timeout/query-before-retry、submission_unknown、partial/late fill、out-of-order/duplicate event、cancel race、reject、fee/cash/position conservation、restart reconcile、client order id不可换键重试。

#### Slice 6.2：Execution modes 与 policy-auto admission

- **Allowed**：execution policy/control domain/service/repository/migration/tests。
- **Invariants**：advisory no order；approval_required exact approval；policy_auto requires valid account/strategy authorization + Paper admission + kill switch off；PostgreSQL execution control是真源，Service与adapter side effect前双读versioned authorization snapshot。
- **Tests**：every bypass path fail before broker call；authorization revocation immediate；global/tenant/account/strategy kill switch；dual-role disable approval；acknowledged/partial order默认hold_and_reconcile；Redis stale cache不能绕过；market-hours/liquidity/max loss/exposure gates。

#### Slice 6.3：Watch/risk monitoring engine

- **Allowed**：watch domain/models/repository/migration/service/job handler/tests。
- **Sources**：manual, approved Fact, industry metric, financial metric, position/exposure, source health。
- **Tests**：gt/gte/lt/lte/eq/neq/contains, debounce, stale observation, trigger/ack/resolve/disable, dedupe alert。

#### Slice 6.4：Stress tests 与 monthly attribution

- **Allowed**：risk scenario/attribution/report services、models/repository/tests。
- **Output**：price/FX/rate/earnings shock, position contribution, allocation/selection/currency/cost attribution, decision outcome review。
- **Tests**：shock composition、cash reconciliation、buy/sell direction、closed-position attribution、report evidence ids。

### Phase 7 — API、UI 与外部渠道

#### Slice 7.1：Auth/RBAC/audit foundation

- **Allowed**：基于 Slice 1.1 tenant/auth tables 的 auth service/repository、FastAPI dependency/middleware、`dayu/web/fastapi_app.py`、migration/tests、README/web README。
- **Roles**：viewer, analyst, portfolio_manager, trader, admin；permissions explicit, no role-name branching in routes。
- **Security**：Argon2 password, short JWT/access token, refresh rotation/revocation, production weak-secret guard, request-body exclusion from audit。
- **Tests**：route permission matrix、TenantScope注入、cross-tenant route/repository/RLS三层拒绝、disabled user、token rotation、audit success/failure、secret redaction。

#### Slice 7.2：Company research APIs

- **Allowed**：investment company/evidence/forecast/graph/report route modules、`dayu/web/fastapi_app.py`、schemas/tests/web README。
- **Endpoints**：companies, sources/health, facts, claims/versions/evidence, forecasts/scenarios, graph, events, weekly reports。
- **Tests**：OpenAPI schema、pagination/as-of、RBAC、Service-only dependency guard、404/conflict。

#### Slice 7.3：Portfolio/decision/execution APIs

- **Allowed**：portfolio/optimizer/decision/watch/execution routes/schemas/tests、`dayu/web/fastapi_app.py`。
- **Endpoints**：portfolios/accounts/positions/analytics, optimize/backtest, decisions/approve, orders/cancel/reconcile, watches/alerts, attribution。
- **Invariant**：API cannot create submitted order directly; only execution Service transition。

#### Slice 7.4：Streamlit company cockpit

- **Allowed**：new Streamlit investment pages/components、`dayu/web/streamlit/pages/main_page.py`、composition、UI tests、web README/root README。
- **Views**：company card, evidence center, thesis timeline, forecast/valuation, graph, events, source health, weekly report。
- **Tests**：Service fake rendering、empty/error/loading、no direct repo/Host import。

#### Slice 7.5：Streamlit portfolio and decision console

- **Allowed**：portfolio/decision/risk pages/components、`dayu/web/streamlit/pages/main_page.py`、tests/docs。
- **Views**：positions/PnL/exposure, optimizer proposal, approval queue, order/fill ledger, watches, stress, attribution, kill switch。
- **Safety**：destructive/submit actions require explicit confirmation and show policy/approval fingerprint。

#### Slice 7.6：Telegram notifications and Obsidian export

- **Allowed**：notification/export protocols、Telegram adapter、Obsidian exporter、services/job handlers/tests/dependencies/README。
- **Events**：source failure, material change, watch trigger, approval request, execution failure, weekly/monthly report。
- **Invariants**：dedupe key、retry receipt、no secrets/PII、Telegram command cannot bypass approval；Obsidian atomic export + manifest/hash。

### Phase 8 — Operations、production 与完整验收

#### Slice 8.1：Backup/restore and operational doctor

- **Allowed**：`dayu/ops/**`、CLI commands/parser、tests、README。
- **Backup**：pg_dump custom format, object manifest/hash, config inventory without secrets, audit receipt；restore to empty target only by default。
- **Tests**：roundtrip, corrupt archive, missing object, version mismatch, interrupted restore cleanup。

#### Slice 8.2：Production Compose and observability

- **Allowed**：Dockerfiles、compose files、Caddy/config、scripts、health/metrics modules、CI workflow、docs。
- **Services**：PostgreSQL, Redis, MinIO, migration, API, worker, scheduler, Streamlit, Caddy。
- **Order**：db/object/redis ready -> migration -> API/worker/scheduler -> UI/proxy。
- **Tests**：non-root/read-only fs, private data ports, liveness/readiness, heartbeat, log rotation, resource limits, Compose smoke。

#### Slice 8.3：Full deterministic platform acceptance

- **Allowed**：platform acceptance utility/tests/fixtures/docs/review artifact only。
- **Scenario**：fixture source sync -> Fact/Claim/Evidence -> forecast/valuation/counter -> graph/report -> portfolio optimizer -> approval -> Paper fills -> watch trigger -> monthly attribution -> notification/export -> backup/restore。
- **Hard gates**：all requirement rows proven, receipts/hashes stable, restart injection, secret scan, RBAC matrix, no live broker/network/model dependency。

#### Slice 8.4：Live broker adapter admission gate

- **External owners**：用户选择 Broker/账户/市场并授权；platform admin配置credential source与账户映射；trader/compliance operator批准supervised live和后续policy_auto。未选择供应商前不猜测SDK或credential字段。
- **Precondition**：Broker 官方 read-only/sandbox/paper API 可用；独立 plan review；单独外部授权；backup/restore、kill switch、reconciliation、Paper admission均已accepted。
- **Allowed**：仅新增具体 broker adapter/config/tests/docs，不改 domain/service contracts；若协议不足必须回 plan review。
- **Credential contract**：credential仅来自部署secret manager或明确环境变量名；DB/config/audit/log/对话只保存引用名与version，不保存值；rotation/revocation先禁用account authorization，再验证read-only和reconciliation后恢复。
- **Sequence**：选择 vendor/account/market -> 配置secret引用 -> read-only account/positions -> vendor sandbox -> Paper submit/cancel/fill/reconcile -> supervised最小live -> policy_auto再次独立授权。
- **Stop**：不得把 Paper PASS 当 live authorization；不得在 conversation secret 中接收/回显凭据；不得自动启用 policy_auto；read-only、sandbox、reconciliation或secret rotation任一失败立即保持disabled。

## 9. Validation matrix

每个 Python slice 至少运行：

```bash
source .venv/bin/activate
pytest <changed tests> -q
pyright <changed production and tests>
ruff check <changed python paths>
git diff --check -- <changed paths>
```

附加 gates：

- 单个新增/修改 production module statement coverage >=80%；utils 仅按 AGENTS 例外。
- PostgreSQL slices 使用真实 PostgreSQL 16 integration lane，不以 SQLite 替代 `FOR UPDATE/SKIP LOCKED/pgvector`。
- Object storage 使用 MinIO integration lane；测试必须验证 checksum/atomicity。
- Architecture test 扫描反向 imports、UI direct repository/Host imports、investment direct workspace access。
- Domain tests 拒 `Any/object/cast/ignore/getattr/hasattr` 逃逸和非中文 docstring。
- Optimizer/backtest tests 固定 seed/input fingerprint，防 look-ahead，输出可重复。
- Execution tests 使用 Paper adapter；任何 test 不得访问真实 Broker。
- RBAC、secret redaction、audit append-only 和 backup restore 是 release hard gates。
- Full repository Python 3.11 lane：`pytest -q --timeout=60 -m "not integration and not slow and not e2e"`。
- Integration tests统一位于 `tests/integration/investment/` 并使用 `integration` marker；默认unit lane排除。修改对应production owner的PR必须跑受影响integration，nightly跑PostgreSQL/Redis/MinIO/Compose全集。
- API OpenAPI snapshot、Streamlit smoke、Telegram fake、Obsidian golden manifest。

文档职责也是 hard gate：`dayu/investment/README.md` 维护依赖方向、模块 owner、schema/migration、composition与开发命令；根 `README.md` 维护用户安装、启动和operator workflow；`dayu/README.md` 维护包级阅读顺序；`tests/README.md` 维护unit/integration/nightly/acceptance lane。不得把实现契约只写在 plan/review artifact。

## 10. Review gates 与提交策略

1. 本计划先经 Terra + MiMo 独立 plan review；Controller 逐项 adjudicate。
2. 有 accepted finding 时只修改本计划并进入双路 re-review；open H/M/L 必须归零。
3. accepted plan commit 后按 Slice 0.1 开始；实现由 DeepSeek Flash/Codex implementation worker 按用户分工执行，Controller 不让 worker重启 Gateflow。
4. 每个 slice 都有 implementation artifact、双路 code review、fix/re-review 和 accepted local commit。
5. Phase 结束运行 phase integration review；所有 Phase 完成后对 `main...HEAD` 运行 aggregate `$deepreview --base main`。
6. aggregate accepted commit 后才到 `ready-to-open-draft-PR`；push/create PR 需要用户授权。
7. 真实 Broker、live data、付费模型、Telegram 外发和 production deployment 都是独立外部授权 gate。

## 11. Stop conditions

出现以下任一情况立即停止当前 slice并交回 Controller：

- 需要破坏 `UI -> Service -> Host -> Agent` 或 Fins storage 唯一存取边界；
- 计划指定 schema 无法表达真实 owner 状态，实施者需要发明第二真源/compat wrapper；
- 需要让 Agent/LLM 直接写 authoritative records、修改 policy 或调用 broker；
- PostgreSQL/pgvector/S3/Redis 行为只能靠 fake 证明但 slice 要求真实 integration；
- optimizer objective/约束、成本/price/FX 输入不完整或可能 look-ahead；
- 订单/成交/cash/position 对账不守恒，或幂等键不能证明；
- live broker vendor、账户、市场、权限或 credential source 未获明确授权；
- policy_auto admission、kill switch、max loss/exposure gate 未闭合；
- review finding、residual risk、测试失败或 dirty ownership 无法分类；
- 需要删除/覆盖用户 workspace、旧 receipts、raw filings 或审计历史。

## 12. Residual risks 与 owner

| 风险 | Owner / destination |
| --- | --- |
| 供应商/交易所格式变化 | Source connector strict parser + source health + adapter-specific review |
| pgvector 相似度误导 | Evidence Service exact locator gate；向量只作候选 |
| 优化过拟合/数据偏差 | Backtest walk-forward + Paper admission + operator review |
| 模型幻觉 | Candidate staging + evidence closure + independent audit |
| Broker 事件乱序/重复 | Execution reconciliation + idempotency + append-only event |
| 自动策略失控 | account/strategy authorization + dual kill switch + limits + alerts |
| Redis/通知不可用 | PostgreSQL truth + retry/outbox；通知失败不丢业务事件 |
| 对象存储或 DB 灾难 | checksummed backup/restore + restore drill |
| 用户权限误配 | explicit permission matrix + audit + default deny |
| 实际收益未达预期 | 不做收益承诺；用风险调整指标、归因和策略版本决定停用/修订 |

所有 residual 必须在相应 slice artifact 中再次分类；不能只引用本表关闭 finding。

## 13. 完成报告

最终报告必须逐项列出：

- 11 组硬需求对应的生产 owner、API/UI 入口和通过的验收命令；
- UI/Service/Host/Agent/Data 依赖审计结果；
- PostgreSQL schema/migration、pgvector、MinIO、Redis 和 durable job 证据；
- Fact/Claim/Evidence、forecast/valuation/thesis/graph/report 的真实纵向 receipt；
- portfolio/cash/position/PnL/exposure/optimizer/backtest/decision/approval/risk 的闭合证据；
- Paper order、partial fill、cancel、reconcile、fee/cash/position conservation；
- advisory/approval_required/policy_auto 三模式及全部 bypass negative tests；
- watch/alert、Telegram dedupe、Obsidian manifest；
- RBAC、audit、secret、backup/restore、Compose smoke；
- accepted plan/slice/phase/aggregate commit hashes和所有 review artifacts；
- 未执行的 live broker/生产外部动作及其明确授权状态；
- 任何剩余风险的 owner、destination 和下一入口。

只有 deterministic full acceptance、integration lanes、aggregate deepreview 和全部 accepted commits 完成，平台才可标记 `READY TO OPEN DRAFT PR`。这仍不代表真实券商自动交易已获授权。
