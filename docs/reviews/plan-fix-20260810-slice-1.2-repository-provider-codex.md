# Slice 1.2 repository/provider plan-gap fix

- **Work unit**：Investment Platform Restoration / Slice 1.2
- **Controller**：Codex
- **状态**：**CLOSED / DUAL PLAN RE-REVIEW PASS**
- **Baseline**：`acd64d8`
- **Implementation state**：pre-edit STOP，repository/service 文件零编辑
- **External actions**：无

## Stop evidence

DeepSeek Flash 在 pre-edit owner/signature/call-graph 审计中确认四项 plan gap：

1. Slice 1.2 要求真实 PostgreSQL 行为，却没有允许
   `tests/integration/investment/` 下的测试文件；unit 路径也无法消费该目录的 owner-
   labeled PG16 fixture。
2. 窄 Service protocol 的真源只能在纯层 `investment.composition`，而稳定 Service
   protocol 汇聚点 `dayu/services/protocols.py` 不在 allowlist。
3. Completion 要求 production provider 暴露真实窄 Service，但没有允许任何具体
   Service owner；把它塞进 storage 会混层，把它塞进 startup 会形成反向依赖。
4. 新 repository/provider 与 integration lane 会改变 package/test 阅读真源，但
   `dayu/investment/README.md`、`tests/README.md` 不在 allowlist。

现有 13 表已足以实现 identity/source repository，`TenantScope` + transaction-local
tenant setting 能闭合 RLS；不需要 schema/migration 变更。

## Controller decision

四项均 **ACCEPTED / PLAN GAP**。S12-CTRL-01..04 锁定：

- source DTO / repository API 与严格 transaction-local tenant boundary；
- `PlatformIdentityServiceProtocol` 的 pure-layer 真源、Service-layer re-export 与
  `InvestmentIdentityService` 具体 owner；
- production default provider 只装配 PostgreSQL identity/source，不预注册 future
  owner；development 仍要求显式 provider；
- 真实 PG16 integration 与两份 README completion。

本勘误只扩大 Slice 1.2 的 owner/test/docs allowlist并补齐可执行契约，不改 13 表、
Slice DAG、后续能力、live/data/model/broker gate。Terra + MiM Native 任一路 open
H/M/L 非零时，Slice 1.2 implementation 继续冻结。

## Plan-review adjudication and fix

- Terra `plan-review-20260810-slice-1.2-repository-provider-terra.md`：FAIL，
  open H/M/L=`0/2/0`；TERRA-S12-001/002 均 **ACCEPTED / FIXED**。
- MiM Native `plan-review-20260810-slice-1.2-repository-provider-mimo-native.md`：
  文本称 PASS，但列出两项 Low 且结论计数误写 `0/2/0`；001/002 均
  **ACCEPTED / FIXED**，不能以“非 blocker”跳过 open finding。

S12-CTRL-05 冻结 exact DTO/UUID/API/errors、single-transaction rollback 与 CAS；
S12-CTRL-06 冻结 production 无注入 public startup black-box、secret-safe errors 与
auto-created engine ownership。Slice 1.2 继续冻结，直至 Terra + MiM Native corrective
plan re-review 均 PASS、open H/M/L=`0/0/0`。

首轮 corrective final review 中 MiM Native PASS/open0；Terra 接受前述 closure，但新增
`TERRA-S12-FINAL-001` Medium：成功态 engine 缺 public typed shutdown owner。Controller
已接受并由 S12-CTRL-07 修复；最终 dual re-review 前 implementation 继续冻结。

## Final closure

Terra 与 MiM Native final closure 均 PASS、open H/M/L=`0/0/0`。本 artifact 的四项
plan gap、TERRA-S12-001/002、MiM-001/002 与 TERRA-S12-FINAL-001 全部 CLOSED；
Slice 1.2 可按 accepted S12-CTRL-01..07 恢复实现。
