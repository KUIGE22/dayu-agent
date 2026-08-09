# 投资平台恢复计划独立复审（MiMo Native — Re-review）

- **审查对象**：`docs/plans/2026-08-10-investment-platform-restoration.md`（修订后）
- **审查基线**：`d0ffe223d0f42521bb8a907152c1e8b4ade0125f`
- **审查分支**：`codex/investment-platform`
- **审查 gate**：Dual plan re-review（第二轮）
- **初审来源**：`docs/reviews/plan-review-20260810-072034-terra.md`（FAIL，6H/2M）、`docs/reviews/plan-review-20260810-072130-mimo-native.md`（PASS-WITH-RISKS，13 observations）
- **Controller 裁决**：`docs/reviews/plan-fix-20260810-072408-codex.md`
- **审查范围**：仅判断修订计划是否可安全交给 code-generation agent；逐项验证 Terra T01–T08 与 MiM M001–M013 闭合。未修改目标计划、生产代码、测试、README，也未执行 commit/push/PR。

## 审查结论

**PASS**。

修订计划正确接受了 Terra 6H/2M 与 MiM M003–M010、M012–M013 的 material findings，并以明确的 plan text 变更（§6.1–§6.5、Slice 0.1/1.1/1.3/1.5/2.1/2.2/5.3–5.5/6.1–6.2/7.1/8.4、§8.0 DAG）闭合。MiM M001/M002/M011 按事实拒绝，理由成立。Open H/M/L = 0。计划现在是 code-generation-ready。

## 逐项闭合验证

### Terra T01 — Workspace Migration 缺少可实施 slice

**状态：CLOSED**

- **Controller 修复**：新增 Slice 1.5（§8 Phase 1），Allowlist 显式包含 `dayu/cli/workspace_migrations/**`、`dayu/cli/commands/init.py`、CLI parser/dispatch。
- **修订计划证据**：Slice 1.5（第 371–376 行）定义 scope（只导入 company/security/source identity 和 research bundle locator/hash，不复制 Host/Fins bytes）、contract（显式 `--import-existing-workspace` 入口、migration id + source root fingerprint + schema version 唯一、stage/validate 后单事务发布、成功 marker 使重复执行为 no-op）及 tests（empty workspace、现有 fixture、partial/invalid bundle、interrupted rollback、rerun idempotency、marker/fingerprint drift、不搬运 Host/Fins bytes、跨 tenant target reject）。
- **判断**：可直接实施；implementation agent 有明确的文件范围、幂等语义和验收矩阵。

### Terra T02 — Composition Roots 被 allowlist 排除

**状态：CLOSED**

- **Controller 修复**：S3、worker、FastAPI、Streamlit slices 的 allowlist 与 completion condition 加入当前真实 composition root 文件。
- **修订计划证据**：
  - Slice 0.2（第 335–339 行）：Allowed 包含 `dayu/investment/composition.py`、`dayu/startup/platform.py`、`dayu/services/startup_preparation.py`；completion 明确"真实 startup composition 创建 platform settings、repositories 和 Service bundle；组合根只向 UI 暴露 Service Protocol，不暴露 repository/ORM"。
  - Slice 1.4（第 364–369 行）：Allowed 包含 `dayu/fins/service_runtime.py`、`dayu/services/startup_preparation.py`；tests 要求 `DefaultFinsRuntime.create()` 和 startup composition 选择正确 backend。
  - Slice 2.2（第 388–392 行）：Allowed 包含 `dayu/startup/platform.py`、`dayu/services/startup_preparation.py`。
  - Slice 7.2（第 523–527 行）：Allowed 包含 `dayu/web/fastapi_app.py`。
  - Slice 7.4（第 536–539 行）：Allowed 包含 `dayu/web/streamlit/pages/main_page.py`。
- **判断**：每个改变可运行能力的 slice 现在显式列出 composition root；black-box composition test 要求断言 production config 实际实例化 PG/S3/queue 与新增 route/page。

### Terra T03 — Tenant/RBAC Sequencing 与 RLS 契约

**状态：CLOSED**

- **Controller 修复**：TenantId/Principal/TenantScope 进入 Slice 0.1；organization/auth/RLS 进入首个 PG schema；所有私有 repository 显式 scope。
- **修订计划证据**：
  - Slice 0.1（第 327–333 行）：Types 显式包含 `TenantId/CompanyId/SecurityId/... newtypes`、`Principal/TenantScope`。
  - §6.2（第 163–167 行）：schema 明确 `TenantScope` 由已认证 Principal 产生；repository 每个 read/write/search 方法显式接收 scope；公共 reference 到私有 projection 只允许从私有表指向公共表，禁止反向 FK。
  - §6.2 RLS（第 167 行）：PostgreSQL RLS 对私有表 default-deny；连接事务必须 `SET LOCAL app.tenant_id`，repository 仍保留 tenant predicate，形成双层隔离。
  - Slice 1.1（第 343–349 行）：validation 包含"private table non-null tenant、RLS default deny、cross-tenant SQL reject"。
  - Slice 7.1（第 516–521 行）：RBAC foundation 有 Roles（viewer/analyst/portfolio_manager/trader/admin）、Tests 包含"cross-tenant route/repository/RLS 三层拒绝"。
- **判断**：Tenant isolation 从第一张私有表开始，不延后到 UI/RBAC 阶段；RLS + repository scope 双层隔离有明确 contract 和验收。

### Terra T04 — Fins Evidence Locator 缺少可解析身份

**状态：CLOSED**

- **Controller 修复**：§6.3 冻结强 EvidenceLocator；新增 Slice 1.3 给 Fins Service resolver/validator/citation projection ownership。
- **修订计划证据**：
  - §6.3（第 202–215 行）：EvidenceLocator 的 owner 是 `dayu.fins`；projection 精确字段为 `repository_id`、`ticker`、`document_id`、`source_kind`、`artifact_kind`、`document_version`、`source_fingerprint`、`primary_content_sha256`、`locator_kind`、`locator_payload`、`locator_content_sha256`。Fins Service Protocol 新增 `resolve_evidence_locator()`、`validate_evidence_locator()`、`read_citation_projection()`；FS/S3 两种 repository 必须产生相同 canonical projection。逻辑删除、重处理、hash drift、同 document id 不同 source kind、跨 ticker/tenant 均 fail closed。
  - Slice 1.3（第 357–362 行）：Allowed 包含 `dayu/fins/domain/evidence_locator.py`、`dayu/fins/service_runtime.py`、`dayu/services/protocols.py`；Tests 包含 source/processed/page/table/XBRL locator、FS canonical projection、hash/version/reprocess drift、wrong ticker/source kind、logical deletion、unknown locator、citation bytes；Stop condition 明确"不得在 investment domain 发明第二 locator"。
- **判断**：强类型、无路径、可序列化的 EvidenceLocator contract 已冻结；Fins 唯一 owner；investment domain 只持有 projection，不导入 Fins 实现或 handle。直接证据充分。

### Terra T05 — 订单/成交/审批/Kill-switch 状态机无恢复语义

**状态：CLOSED**

- **Controller 修复**：拆分 Decision、OrderIntent、BrokerOrder、Ledger/Reconciliation 四个独立 aggregate，补 CAS/fencing/query-before-retry/late fill/kill-switch 语义。
- **修订计划证据**：
  - §6.4（第 237–255 行）：
    - **Decision aggregate**：`candidate -> risk_checked -> awaiting_approval -> approved`；唯一键 `(tenant_id, portfolio_id, candidate_fingerprint)`。
    - **OrderIntent aggregate**：只由 approved decision transition 创建；唯一键 `(tenant_id, account_id, decision_version, intent_sequence)`；状态 `staged -> dispatching -> dispatched`，旁路 `blocked/cancelled/expired/dispatch_unknown`；每次 `dispatching` 取得 CAS version + fencing token。
    - **BrokerOrder aggregate**：以 `(tenant_id, broker_account_id, client_order_id)` 唯一；状态 `submission_unknown|acknowledged|partially_filled|filled|cancel_pending|cancelled|rejected|expired`；Broker event 以 `(broker_order_id, broker_event_id)` 去重；late fill 永远可在 cancelled 后进入 ledger。
    - **Ledger/reconciliation**：Fill 只追加且以 broker execution id 去重；同一 DB transaction 写 fill、cash ledger、position lot event 与 reconciliation watermark。
    - **提交语义**：query-before-retry；broker 接受但本地超时后进入 `submission_unknown`；新 attempt 先用 client order id 查询；找到则关联原单；明确不存在才在同一 idempotency key 下重试；禁止在不确定状态换 client order id。
    - **Kill switch**：scope global/tenant/account/strategy；PG append-only control event + current projection 是唯一真源；开启时取消未 dispatch intent 并阻止新 side effect；已 acknowledged/partially-filled 默认 `hold_and_reconcile`，不得自动 cancel；关闭需要双人/双角色审批并生成新 authorization version。
  - Slice 5.5（第 483–486 行）：Tests 包含 cross-company/portfolio reject、stale evidence、policy change、expired approval、duplicate candidate/intents、concurrent dispatch CAS、kill switch、mode transitions。
  - Slice 6.1（第 490–494 行）：Tests 包含 duplicate submit、accept-then-timeout/query-before-retry、submission_unknown、partial/late fill、out-of-order/duplicate event、cancel race、reject、fee/cash/position conservation、restart reconcile、client order id 不可换键重试。
  - Slice 6.2（第 497–500 行）：Tests 包含 every bypass path fail before broker call；authorization revocation immediate；global/tenant/account/strategy kill switch；dual-role disable approval；acknowledged/partial order 默认 hold_and_reconcile；Redis stale cache 不能绕过。
- **判断**：四个独立 aggregate 有明确的 owner、唯一键、CAS/fencing、idempotency、合法/非法转移和 terminal/repair path。直接证据充分，可直接实施。

### Terra T06 — 回测无 point-in-time 数据契约

**状态：CLOSED**

- **Controller 修复**：冻结 effective/published/ingested/available/revision 与 universe/corporate-action/FX/fill policy fingerprint，补反例矩阵。
- **修订计划证据**：
  - §6.5（第 264–274 行）：每条输入必须有 `effective_at`、`published_at`、`ingested_at`、`available_at`、`revision_id` 和 prior revision link；任何一步计算只允许 `available_at <= decision_at`；`MarketDataSnapshot` 绑定 universe membership/delisting、raw/adjusted price、corporate action version、FX market/timezone、trading calendar、halt/missing marker；`BacktestPolicy` 绑定信号形成时点、下单延迟、成交价规则、滑点/费用和缺价处理；完整 data watermark、revision set、universe、adjustment 和 fill policy 进入 fingerprint。
  - Slice 5.3（第 469–473 行）：Tests 包含"effective 但当时尚未 published/ingested/available 的输入拒绝、revision 重放稳定"。
  - Slice 5.4（第 476–480 行）：Contract 要求"run fingerprint 必须包含 universe membership、delisting、corporate action、FX、trading calendar、market close、fill/latency/slippage/cost policy 及所有 input revision"；Tests 包含"walk-forward split、announcement-after-close、late filing、revised fundamentals、look-ahead trap、delisting/missing price、split/dividend、FX staleness、cost sensitivity、input fingerprint"。
- **判断**：point-in-time contract 显式覆盖 effective/published/ingested/available/revision 五时点；fingerprint 绑定完整数据版本和 availability cut；反例矩阵覆盖晚发布 Fact、退市、复权、停牌、休市/FX 时区和缺价。直接证据充分。

### Terra T07 — Host/PG 无单一 owner 关联恢复契约

**状态：CLOSED**

- **Controller 修复**：明确 Host SQLite 与 PG 各自真源，以 immutable `AgentRunCorrelation` 关联并 query-before-retry，不做跨库事务/dual write。
- **修订计划证据**：
  - §6.1（第 144–151 行）：
    - Host SQLite **永久**拥有 conversation/session、Agent run、pending turn、reply outbox、permit、Agent cancellation 与恢复状态；不 dual-write、不迁移、不复制到 PostgreSQL。
    - PostgreSQL **永久**拥有投资业务、platform job definition/run/attempt/lease/event、source health、notification outbox 与交易状态；不覆盖 Host run 细节。
    - 纯业务 job 只有 PostgreSQL 状态；需要调用 Agent 的 job attempt 生成 immutable `AgentRunCorrelation(tenant_id, job_run_id, attempt_id, host_run_id, idempotency_key)`。
    - crash reconciliation 固定为 query-before-retry：Host terminal success 时只补 PG receipt；Host running/pending 时恢复或等待同一 run；Host terminal failure 时按 retry policy 创建新 attempt；找不到关联且没有外部 receipt 时才允许新建 run。禁止跨库事务和盲目重放 Agent side effect。
    - cancel 的外部真源是 PostgreSQL job cancel intent；worker 持续把它投射为 Host cancel intent。
  - Slice 2.1（第 380–386 行）：Tests 包含"two-worker race、expired lease、retry/backoff、cancel-before/while-run、crash recovery、Host success 补 PG receipt、Host pending 等待、Host failure 新 attempt、missing correlation 安全重建、禁止双重模型执行"。
- **判断**：Host SQLite 与 PostgreSQL 各有明确 owner、不 dual-write、不跨库事务；`AgentRunCorrelation` 提供 immutable 关联；query-before-retry 覆盖四个 crash 点。直接证据充分。

### Terra T08 — 36-slice 承诺与实际不一致

**状态：CLOSED**

- **Controller 修复**：实际35项经新增 Evidence Locator（Slice 1.3）与 workspace migration（Slice 1.5）后成为机械可数的37 slices；计划不再声称36。
- **修订计划证据**：
  - §8 第 296 行："本计划共 **37 个 slices**"。
  - Phase 0：0.1、0.2（2 slices）
  - Phase 1：1.1、1.2、1.3、1.4、1.5（5 slices）
  - Phase 2：2.1、2.2、2.3（3 slices）
  - Phase 3：3.1、3.2、3.3（3 slices）
  - Phase 4：4.1、4.2、4.3、4.4、4.5（5 slices）
  - Phase 5：5.1、5.2、5.3、5.4、5.5（5 slices）
  - Phase 6：6.1、6.2、6.3、6.4（4 slices）
  - Phase 7：7.1、7.2、7.3、7.4、7.5、7.6（6 slices）
  - Phase 8：8.1、8.2、8.3、8.4（4 slices）
  - 合计：2 + 5 + 3 + 3 + 5 + 5 + 4 + 6 + 4 = **37**。
- **判断**：数量一致；revision changelog 明确记录变更来源。

---

### MiM M001 — Greenfield 被误作已有骨架

**状态：REJECTED-WITH-REASON / CLOSED**（Controller 原裁决维持）

- **Controller 理由**：计划已经陈述 `dayu/investment/` 不存在；"skeleton" 是要创建的 slice 名称，不是假设已有代码。
- **修订计划证据**：§4.2（第 100 行）："`dayu/investment/` 完全不存在，因此本计划中的 investment domain 是明确的 greenfield package，不是对已有 investment skeleton 的增量补丁"。Slice 0.1（第 329 行）allowed files 全部不存在于当前仓库。
- **判断**：rejection 成立。"skeleton" 在此处是 Slice 名称（"Investment domain skeleton"），指的是创建空包结构，不是假设已有代码。plan text 已强化 greenfield 声明。

### MiM M002 — 依赖当前缺失

**状态：ACCEPTED-IN-PART / CLOSED**（Controller 原裁决维持）

- **Controller 理由**：当前缺失正是计划交付内容而非 plan defect；已按 owner slice 明确兼容与验证。
- **修订计划证据**：Slice 1.1（第 346 行）"锁定 SQLAlchemy 2.x、psycopg 3、Alembic 与 PostgreSQL 16 compatible ranges；新增依赖必须在 Python 3.11 min-compat lane 与当前 full suite 验证"；Slice 1.4（第 367 行）"只选一个 S3 client 并锁 Python 3.11 兼容版本"；Slice 2.2（第 390 行）"锁定 Redis client 兼容版本"；Slice 3.3（第 419 行）"锁定 pgvector client/extension compatibility"。
- **判断**：rejection 成立。依赖缺失是 implementation gap 而非 plan defect；每个依赖在 owner slice 中有明确的兼容性锁定和验证要求。

### MiM M003 — Fins 边界模糊

**状态：DUPLICATE T-04 / CLOSED**（Controller 原裁决维持）

- **Controller 理由**：采用 Fins-owned strong locator，不采用会暴露 object key 的弱 locator 建议。
- **判断**：与 Terra T04 同一 finding。§6.3 EvidenceLocator 已冻结强类型 contract，不暴露 bucket/path。

### MiM M004 — 缺乏 slice DAG

**状态：ACCEPTED / CLOSED**

- **Controller 修复**：新增 §8.0 DAG、predecessor commit 与 Phase integration 要求。
- **修订计划证据**：§8.0（第 298–318 行）显式 DAG 列出所有关键依赖路径；§8.0 第 320 行："没有 predecessor 的 slice 也只能在 0.1/0.2 architecture guard accepted 后开始"；每个 Phase 结束运行 `tests/integration/investment/` 中对应纵向 lane；Slice artifact 必须列出 predecessor accepted commit。
- **判断**：DAG 覆盖所有37 slices 的依赖关系；predecessor commit 和 Phase integration 要求提供机械可验证的完成定义。

### MiM M005 — Claim trust 模型缺乏验证边界

**状态：ACCEPTED / CLOSED**

- **Controller 修复**：confidence 不自动批准；expiry 转 review_required；material conflict 人工 resolve 前阻止下游。
- **修订计划证据**：§6.2（第 174 行）："confidence 只是信息，不自动批准 Claim；Claim approval 由明确 permission 的 reviewer 完成"；§6.2（第 175 行）："`valid_until` 到期自动转 `review_required` 并阻止新 forecast/decision 使用，不自动 supersede"；§6.2（第 176 行）："Material conflict 未 resolve 时下游 fail closed"；§6.3（第 215 行）："confidence_band 不构成批准阈值"。
- **判断**：trust boundary 明确；confidence/expiry/conflict 三条规则有直接 plan text 支撑。

### MiM M006 — Look-ahead 防护缺乏实现指导

**状态：DUPLICATE T-06 / CLOSED**（Controller 原裁决维持）

- **判断**：与 Terra T06 同一 finding。§6.5 point-in-time contract 已闭合。

### MiM M007 — Kill switch 双端检查缺乏细节

**状态：ACCEPTED / CLOSED**

- **Controller 修复**：PG control 真源、Redis 仅 invalidates、Service/adapter 双读、scope 与 dual-role 解除、partial fill 策略已冻结。
- **修订计划证据**：§6.4（第 253 行）："每次 broker side effect 前 Service 必须重新读取 PostgreSQL execution_controls、approval expiry、account/strategy authorization 与 risk limit；Broker adapter 的 submit/cancel 还必须接收不可伪造的 ExecutionAuthorizationSnapshot，并通过注入的 ExecutionControlReaderProtocol 再读 PostgreSQL version。Redis 只广播 invalidation，不是真源"；§6.4（第 255 行）："Kill switch scope 为 global/tenant/account/strategy，PostgreSQL append-only control event + current projection 是唯一真源"。
- **判断**：PG 为真源、Redis 为 invalidation hint、Service 与 adapter 双读 PostgreSQL；scope 和 dual-role 审批已冻结。

### MiM M008 — Tenant 隔离缺乏多租户考虑

**状态：ACCEPTED / CLOSED**

- **Controller 修复**：不延后；从第一张私有表开始 tenant-ready 并建立 default organization。
- **修订计划证据**：§6.2（第 164 行）："`organizations`、`users`、`roles`、`permissions`、`user_roles`、`api_tokens` 先于其它私有表建立"；§6.2（第 165–167 行）：tenant scope 和 RLS 契约；§2（第 61 行）："平台数据面按 organization/tenant 隔离"。
- **判断**：tenant isolation 从第一张业务表开始，不延后。

### MiM M009 — Redis 降级策略过于简略

**状态：ACCEPTED / CLOSED**

- **Controller 修复**：固定5秒 poll、30秒 health、3次阈值与 event_assisted/polling_degraded 转换及测试。
- **修订计划证据**：§6.1（第 152–156 行）："Redis wake-up/pub-sub 只是提示。worker 每次都从 PostgreSQL claim；丢消息不会丢任务"；"配置真源为 PlatformQueueSettings：默认 poll_interval_seconds=5、redis_health_interval_seconds=30、redis_failure_threshold=3，均必须为有限正数并进入启动快照"；"达到失败阈值后进入 polling_degraded，继续按 PostgreSQL poll；Redis 健康检查恢复后回到 event_assisted。模式切换写 audit/metrics"。
- **判断**：降级参数、触发条件、转换语义和可观测性均已冻结。

### MiM M010 — Live broker owner 和授权流程不清晰

**状态：ACCEPTED / CLOSED**

- **Controller 修复**：明确 user/admin/trader-compliance owners、secret 引用/轮换/撤销和 read-only→sandbox→Paper→minimal-live→policy_auto 顺序。
- **修订计划证据**：Slice 8.4（第 574–581 行）："External owners：用户选择 Broker/账户/市场并授权；platform admin 配置 credential source 与账户映射；trader/compliance operator 批准 supervised live 和后续 policy_auto"；Credential contract：credential 仅来自部署 secret manager 或明确环境变量名；DB/config/audit/log/对话只保存引用名与 version，不保存值；rotation/revocation 先禁用 account authorization，再验证 read-only 和 reconciliation 后恢复。Sequence：选择 vendor/account/market → 配置 secret 引用 → read-only account/positions → vendor sandbox → Paper submit/cancel/fill/reconcile → supervised minimal live → policy_auto 再次独立授权。
- **判断**：owner、credential lifecycle 和 authorization sequence 已冻结。

### MiM M011 — 36 slices 可能过度拆分

**状态：REJECTED-WITH-REASON / CLOSED**（Controller 原裁决维持）

- **Controller 理由**：Greenfield 投资域与资金安全边界需要窄 review；合并会放大 schema、租户和订单状态风险。
- **修订计划证据**：§8 第 296 行："数量来自真实 owner 与高风险边界，不以压缩提交数为目标：schema/tenant、Fins evidence、durable jobs、optimizer、execution、RBAC 和 recovery 必须独立 review，不能为了减少 slices 把多个真源揉成一个大改动"。
- **判断**：rejection 成立。37 slices 的拆分逻辑是 owner-driven（每个独立真源/高风险边界一个 slice），不是人为计数。合并 Phase 4 的 forecast/valuation/thesis/graph/report 会模糊 schema ownership 和 review boundary，增加集成风险。

### MiM M012 — Integration lane 缺乏定义

**状态：ACCEPTED / CLOSED**

- **Controller 修复**：固定 `tests/integration/investment/`、marker、PR 受影响 lane 和 nightly 全集。
- **修订计划证据**：§8.0（第 321 行）："每个 Phase 结束运行 `tests/integration/investment/` 中对应纵向 lane；测试统一标记 `integration`，默认 unit lane 排除，受影响 PR 必跑相关 integration，nightly 跑 PostgreSQL/Redis/MinIO/Compose 全集"；§9（第 598–607 行）："PostgreSQL slices 使用真实 PostgreSQL 16 integration lane"、"Object storage 使用 MinIO integration lane"、"Integration tests 统一位于 `tests/integration/investment/` 并使用 `integration` marker"。
- **判断**：integration lane 的目录结构、marker、PR 触发和 nightly 频率均已定义。

### MiM M013 — 投资域 README 缺乏定义

**状态：ACCEPTED / CLOSED**

- **Controller 修复**：固定 investment 开发手册、根用户手册、dayu 包导航、tests lane 文档职责。
- **修订计划证据**：§9（第 609 行）："文档职责也是 hard gate：`dayu/investment/README.md` 维护依赖方向、模块 owner、schema/migration、composition 与开发命令；根 `README.md` 维护用户安装、启动和 operator workflow；`dayu/README.md` 维护包级阅读顺序；`tests/README.md` 维护 unit/integration/nightly/acceptance lane"。
- **判断**：各 README 的固定职责与 AGENTS.md §文档职责一致。

---

## 额外验证：用户指定的关键项

### 37 Slices — 已验证

§8 第 296 行明示总数；逐 Phase 机械计数 2+5+3+3+5+5+4+6+4 = 37，与 plan text 一致。

### DAG — 已验证

§8.0（第 298–318 行）显式 DAG 覆盖所有关键依赖路径；§8.0 第 320 行约束无 predecessor slice 必须在 architecture guard 后开始。DAG 中每条边对应 slice 间的 schema/协议/composition 依赖，不是人为排期。

### 真实 Composition Roots — 已验证

每个改变可运行能力的 slice（0.2、1.4、2.2、7.2、7.4）的 Allowlist 或 Completion condition 显式列出当前唯一 composition root 文件；black-box composition test 要求断言 production config 实际实例化。

### Tenant/RLS — 已验证

TenantId 在 Slice 0.1；organization/auth tables 在 Slice 1.1；RLS default-deny + `SET LOCAL app.tenant_id` + repository scope 三层隔离；所有私有表 non-null tenant_id；public→private FK only。直接证据在 §6.2（第 163–167 行）和 Slice 1.1（第 349 行）。

### Fins Locator — 已验证

§6.3 冻结强 EvidenceLocator（无路径、可序列化 projection、11 字段）；Slice 1.3 给 Fins Service Protocol ownership；investment domain 只持有 projection，不导入 Fins 实现。直接证据在 §6.3（第 202–215 行）。

### Host/PG 恢复 — 已验证

§6.1（第 144–151 行）明确 dual owner、immutable `AgentRunCorrelation`、query-before-retry 四种 crash 点、禁止跨库事务。直接证据充分。

### Point-in-Time — 已验证

§6.5（第 264–274 行）冻结 effective/published/ingested/available/revision 五时点 + `available_at <= decision_at` 硬约束；MarketDataSnapshot/BacktestPolicy/fingerprint 绑定完整数据版本。反例矩阵覆盖晚发布/退市/复权/停牌/休市/FX 时区/缺价。

### 订单幂等/Kill Switch — 已验证

§6.4 定义四个独立 aggregate（Decision/OrderIntent/BrokerOrder/Ledger）；OrderIntent 唯一键 + CAS version + fencing token；BrokerOrder 去重键；query-before-retry 语义；kill switch 四级 scope + PG 真源 + Redis invalidation + 双读 + dual-role 审批。直接证据充分。

### Integration — 已验证

`tests/integration/investment/` + `integration` marker + PR 受影响 lane + nightly 全集。§8.0 和 §9 有明确约定。

### Live Gate — 已验证

Slice 8.4 定义五步 sequence（read-only → sandbox → Paper → minimal live → policy_auto）；每个 gate 有独立 owner、credential lifecycle、fail-closed 和 stop condition。

## Assumptions Tested

1. **Terra T01–T08 全部闭合**：通过。8 项均有 plan text 变更直接证据。
2. **MiM M001–M013 全部闭合（ACCEPTED 项已修复，REJECTED 项理由成立）**：通过。13 项均有 plan text 或 controller 裁决直接证据。
3. **37 slices、DAG、composition roots、tenant/RLS、Fins locator、Host/PG、point-in-time、订单幂等/kill switch、integration、live gate 均有直接 plan text 支撑**：通过。每项在 plan 中有明确的 section、slice、schema、state machine 或 test definition。
4. **Open H/M/L = 0**：通过。无遗留的 accepted-candidate 或 needs-evidence findings。

## Residual Risks

| 风险 | 当前状态 | 建议 destination |
| --- | --- | --- |
| 供应商/交易所格式变化 | 计划 §12 已列入 residual | Source connector strict parser + adapter-specific review |
| pgvector 相似度误导 | 计划 §12 已列入 residual | Evidence Service exact locator gate；向量只作候选 |
| 优化过拟合/数据偏差 | 计划 §12 已列入 residual | Backtest walk-forward + Paper admission + operator review |
| 模型幻觉 | 计划 §12 已列入 residual | Candidate staging + evidence closure + independent audit |
| Broker 事件乱序/重复 | 计划 §12 已列入 residual | Execution reconciliation + idempotency + append-only event |
| 自动策略失控 | 计划 §12 已列入 residual | account/strategy authorization + dual kill switch + limits + alerts |
| Redis/通知不可用 | 计划 §12 已列入 residual | PostgreSQL truth + retry/outbox；通知失败不丢业务事件 |
| 对象存储或 DB 灾难 | 计划 §12 已列入 residual | checksummed backup/restore + restore drill |
| 用户权限误配 | 计划 §12 已列入 residual | explicit permission matrix + audit + default deny |
| 实际收益未达预期 | 计划 §12 已列入 residual | 不做收益承诺；用风险调整指标、归因和策略版本决定停用/修订 |

所有 residual 在 §12 有 owner 和 destination；计划要求"所有 residual 必须在相应 slice artifact 中再次分类"。这些是 implementation 风险而非 plan defect，不阻塞 PASS。

## Open Questions

无。所有初审 open questions 已在修订计划中收敛或合理推迟到 Slice 8.4（live broker 授权）。

## Final Verdict

**PASS**。

修订计划正确闭合了 Terra 6H/2M 与 MiM 13 observations 中所有 material findings。37 个 slices 有显式 DAG、production composition roots、tenant/RLS 双层隔离、Fins EvidenceLocator 强类型 contract、Host/PG dual-owner 关联恢复、point-in-time 数据契约、四 aggregate 订单状态机与 kill switch、integration lanes 及 live admission gate。Open H/M/L = 0。计划现在是 code-generation-ready，可以推进到 implementation。
