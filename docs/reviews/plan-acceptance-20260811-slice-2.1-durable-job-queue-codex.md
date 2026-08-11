# Plan Acceptance：Slice 2.1 durable job queue

- **Status**：`ACCEPTED / DUAL PLAN RE-REVIEW PASS / IMPLEMENTATION READY`
- **Controller**：Codex
- **Branch / baseline**：`codex/investment-platform` / `61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Accepted target**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Final independent reviews**：
  - `docs/reviews/plan-final4-closure-rereview-20260811-slice-2.1-mim.md` — `PASS / open H/M/L = 0/0/0`
  - `docs/reviews/plan-final4-closure-rereview-20260811-slice-2.1-flash.md` — `PASS / open H/M/L = 0/0/0`
- **External actions**：未运行 implementation、pytest、pyright、Ruff、Docker、PostgreSQL、network、live、paid、commit、push、PR 或 deploy。

## 1. Acceptance decision

Slice 2.1 计划已达到 code-generation-ready：全部 accepted plan findings 均 CLOSED，最终两路独立 closure-only re-review 均 PASS，Controller 复核 open H/M/L=`0/0/0`。target、master Slice 2.1 五行与下一 slice owner 边界一致，可以进入 implementation gate。

本 acceptance 只接受计划，不表示代码已实现、真实 PostgreSQL 16 fault matrix 已通过、Slice 2.1 已完成，亦不授权 scheduler、worker、Redis、业务 handler、broker、live、network 或 paid action。

## 2. Closed finding inventory

- `S21-CTRL-FINAL2-001..007`：owner/DAG 与 storage import guard、correlation-by-ID lookup、deadline/correlation-missing、versioned lease、UNSETTLED mapping、generic receipt canonical schema、真实 recovery result state 全部 CLOSED。
- `S21-CTRL-FINAL3-001..005`：correlation-safe generic/targeted recovery、complete 的 cancel→deadline→success、reserved ID validator owner、ready-deadline safe observation、master Slice 2.1 五行 drift 全部 CLOSED。
- `S21-CTRL-FINAL4-001..002`：§7D mixed-batch recovery 旧句与 16 个 mandatory test 的 implementation-slice owner 缺口全部 CLOSED。

Final4 的固定算法是：sorted expired committed correlations → 每条 correlation lookup / Host read / strict mapping / reconciliation → 仅 `NO_HOST_RUN` 进入 targeted recovery → 全部 correlation 后恰好一次 generic recovery；generic SQL 仅处理 `NOT EXISTS correlation` 的 attempts。mixed active + `NO_HOST_RUN` + no-correlation batch 的结果固定为 targeted successes 后接 generic results。

## 3. Accepted architecture boundary

- `dayu.investment.domain.jobs`：15 个 job DTO/enums/errors、canonical document 与 generic receipt builder 的 pure owner。
- `dayu.investment.storage.protocols` / `postgres_jobs`：`JobStoreProtocol` 与 PostgreSQL transaction/RLS/DDL owner；storage 不 import Host/contracts。
- `dayu.services.job_service`：descriptor-only registry、Host reader、strict Host observation mapping 与 public recovery orchestration owner。
- Host：reserved run identity、Agent lifecycle、cancel 与 Host SQLite run 的唯一 owner。
- PostgreSQL：durable job、attempt、lease、receipt、event 与 correlation 的唯一 owner。

本 slice 不定义 `JobHandlerProtocol`、不注册 handler、不启动 worker/scheduler/Redis、不引入跨 store transaction、dual-write 或 compatibility wrapper。missing correlation 的旧 attempt 不补建；generic recover 只处理从未提交 correlation 的 attempt。

## 4. Evidence integrity

有效最终证据：

- `docs/reviews/plan-controller-final-codegen-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`
- `docs/reviews/plan-controller-final3-rereview-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`
- `docs/reviews/plan-fix-20260811-slice-2.1-final-codegen-closure-terra.md`
- `docs/reviews/plan-final3-corrective-rereview-20260811-slice-2.1-mim.md`
- `docs/reviews/plan-final3-corrective-rereview-20260811-slice-2.1-flash.md`
- 两份 final4 closure-only PASS artifact。

`docs/reviews/plan-final-rereview-20260811-slice-2.1-durable-job-queue-mimo.md` 保留为历史 incident evidence，但因跨项目读取/覆盖风险已失效，不计入 dual review。`docs/reviews/slice-2.1-final-contract-mechanical-audit-20260811-codex-spark.md` 只作为 advisory inventory，不计作 plan PASS。MiM 前一轮 PASS 对 FINAL2/3 有效，但其 open0 被 Controller 的 Final4 直接证据覆盖；修复后的 final4 MiM PASS 才是最终 gate evidence。

## 5. Residual risks and owners

- `START_REQUIRED` 后、Host ensure 前跨 lease 的 PG/Host read-to-entry TOCTOU 不能由本 slice 的两套 store 消除；这里只承诺同一 correlation 的 Host ensure at-most-once，不宣称 distributed exactly-once。
- Slice 2.2 负责 immediate Host entry、worker heartbeat/governance、active Host re-observe/cancel delivery、scheduler 与 Redis degradation。
- Slice 2.3 负责业务 payload schema、source handler、source health 与 notification。
- 外部 provider/tool exactly-once 归未来 handler/connector idempotency protocol。

上述 residual 已明确 owner，不阻塞 Slice 2.1 的 durable queue contract 实现；若 implementation 要求移动这些边界、增加第二真源或改 public contract，必须 STOP 并返回 Controller。

## 6. Implementation gate

下一动作固定为：

1. DeepSeek Flash 按 accepted target 的 A→E 小 slice 顺序实施，且只能修改 exact allowlist。
2. 必须运行真实 PostgreSQL 16 两 engine/process barrier fault matrix；fake/SQLite 不能替代 PG race、RLS、grant、migration 与 recovery tests。
3. changed production modules coverage 均至少 80%，再运行 exact pyright、Ruff、相关 suites、Python 3.11 non-integration full lane 与 diff/secret/path hygiene。
4. 实现完成后由 MiM + Terra 做独立双路 code review；Flash 不自审。accepted findings 修复并双路 re-review open0 后，才允许本地 Slice 2.1 accepted code commit。

本 acceptance 允许本地 accepted plan commit；不授权 push、PR、deploy、live 或 paid action。
