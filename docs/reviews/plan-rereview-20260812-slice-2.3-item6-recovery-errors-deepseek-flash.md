# Slice 2.3 Item 6 Recovery Errors / Receipt Owner — DeepSeek Flash Independent Plan Re-Review

- 日期：2026-08-12T23:16:13+0800（本机系统时钟）
- 角色：DeepSeek V4 Flash 独立 plan reviewer（只读，不实施、不修文档、不改 production/tests）
- Gate：Gateflow Item 6 corrective plan fresh same-SHA re-review（recovery-errors corrective）
- 分支：`codex/investment-platform`
- Reviewed target：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
  - 审查开始 SHA-256：`e589cc5e6c6ab7bfd6402977ffb32340739fdee519cd6d7b4e3ca12328fcda8c`
  - 审查结束 SHA-256：`e589cc5e6c6ab7bfd6402977ffb32340739fdee519cd6d7b4e3ca12328fcda8c`（一致）
- Reviewed master：`docs/plans/2026-08-10-investment-platform-restoration.md`
  - 开始/结束 SHA-256：`9f5ee84245070783aed0d7397e273241869fa883fd37e9af9e2ef5e2f80a70d1`（一致）
- Reviewed fix：`docs/reviews/plan-fix-20260812-slice-2.3-item6-recovery-errors-codex.md`
  - 开始/结束 SHA-256：`56bb7e98101ba0530ebf4d6de7d8cdb640f73962eefb672aee34815bdfe623c2`（一致）
- 真实 tracked contracts 核验对象：`dayu/investment/domain/jobs.py`、`dayu/investment/domain/schedules.py`、`dayu/services/job_service.py`（均只读）
- 未读取：MiMo 本轮 artifact（`plan-rereview-20260812-slice-2.3-item6-recovery-errors-mimo.md`）、Item 1 的 11 个 production/test WIP path、两份 code-review artifact
- 外部边界：未运行 network/provider/model/Broker/trading；未 stage、commit、push 或创建 PR；未编辑任何 frozen 文档

## 结论

**PASS / open H/M/L = 0/0/0**

本次 corrective candidate 无 material finding。审查范围严格限定为 Item 6 recovery-errors/receipt-owner corrective（三份 frozen docs 与真实 tracked contracts）；Item 1 的并行 architecture test diff 属冻结 WIP，不计入本 pass scope。

## 审查假设（逐项验证）

1. `JobRepositoryFailureError` 与 `ScheduleRepositoryError` 无稳定 typed code，计划穷尽映射 lookup/enqueue/ensure 的这两类下游异常为 `SourceServiceUnavailableError(unavailable)`，禁止 message/shape guessing。
2. Source 自有 typed `SourceSyncRepositoryFailure(persisted_invariant)` 保留且与 Job/Schedule 收窄边界无混淆。
3. `JobService.get_by_idempotency_key` 只返回 `JobIdempotencyRecord | None`；`InvestmentSourcesService` 在 strict 验证 source payload、caller intent、record lineage 后唯一构造 READY/idempotency_reused receipt；无 JobService 构造 receipt 的陈旧文字。
4. §3.4/§5/§9/§12/§13.1/§15/§16/§17 与 master 状态一致、code-generation-ready，无 scope/owner/cycle/response-loss/tenant 泄漏。
5. 158 个 named tests 唯一；勘误仅 docs 范围，未影响 Item 1 纯合同。

## Findings（findings-first）

### 无 material finding

- **开放计数：H=0 / M=0 / L=0**
- 无 blocker、无 needs-evidence、无 defer-candidate。逐项反例验证结果如下。

## 证据与逐项验证

### A1. Job/Schedule 无 typed code 异常的统一 unavailable 映射（Q1）

**代码事实（tracked，3f0de57 与工作树一致）**：
- `dayu/investment/domain/jobs.py:233-234`：`class JobRepositoryFailureError(RuntimeError)`，docstring「数据库/仓储内部失败时抛出的稳定错误（不携带 cause 细节）」，无 `code` 字段。
- `dayu/investment/domain/schedules.py:167-168`：`class ScheduleRepositoryError(RuntimeError)`，docstring「schedule 仓储内部失败时抛出的稳定错误（不携带 cause 细节）」，无 `code` 字段。

**计划文本**：
- target §9（L2229-2237 表格）：`JobRepositoryFailureError / ScheduleRepositoryError → SourceServiceUnavailableError(unavailable)`；且该表格行在 corrective pass 前后均为 `unavailable`（diff 仅新增说明段，未改行），符合 fix doc §3「表中既有 unavailable action 不改」。
- §9 L2224-2227 明确：「尤其 `JobRepositoryFailureError` 与 `ScheduleRepositoryError` 都没有 typed code；无论底层事实来自 infra failure 还是 persisted drift，都只能映射 `unavailable`。Source 自有 `SourceSyncRepositoryFailure(code)` 仍保留 `persisted_invariant` typed code，不受此收窄影响」。
- §3.4 L950-954、§5.1 L1400-1402、§5.2 L1440-1442 全部由 pre-edit 的 `persisted_invariant` 改为 `unavailable`（diff 逐 hunk 核实，共三处），并保留「绝不按 message/persisted shape 再分类或当 miss」「不得伪造 `persisted_invariant` 诊断」禁止句。
- §15 STOP（L2873-2875）：新增「为区分 Job/Schedule repository infra failure 与 persisted tamper 而检查异常 message、SQL/row shape、cause 或自由字符串，或在现有无 typed-code 异常上伪造 `persisted_invariant`」即 STOP。
- §16 residual 9（L2909-2911）：诚实记录「只能稳定暴露 unavailable，不能区分 infra failure 与 persisted drift」，后续归独立 typed repository-error contract work unit。

**边界无混淆**：表格中其余映射 `persisted_invariant` 的异常（`JobNotFoundError`/`JobStateConflictError`/`JobCorrelationInvariantError`/`JobGovernanceRequiredError`/`JobLeaseLostError`/`JobDeadlineExceededError`/`ScheduleInvariantError`/`ScheduleExecutionUnavailableError`，L2235-2237）各自是独立 typed class，class identity 即 typed discriminator，非 message guessing；且 L2235 注明「source fixed descriptor lookup/enqueue 不应观察到这些 durable drift」，L2236 注明「本调用集合不可达；若 callee 违约抛出」——属防御性闭合。`persisted_invariant` 在该表与 Source 自有 `SourceSyncRepositoryFailure(code)` 两个命名空间不混用。

**穷尽性**：Source facade 实际只调用四个方法（§3.3 两个 gateway protocol 共四方法 + constructor structural test 固定「Source facade 只调用上述四个方法」，L859-860）。jobs.py/schedules.py 的全部 14 个 stable exception class（9 + 5）均被表格覆盖。

### A2. get_by_idempotency_key 返回 record/None 且 facade 唯一构造 receipt（Q2）

- §3.4 L927-934：`JobService.get_by_idempotency_key` 只 read-only 委托 Store 一次并原样返回 `JobIdempotencyRecord | None`；「它不 strict parse Source payload、不比较 caller intent、不构造 `JobEnqueueReceipt`、不 publish 且不产生任何 mutation。只有 `InvestmentSourcesService` 在命中后完成 Source-owned strict payload parse、caller-intent compare 与 record identity 验证，才重建原 enqueue 语义的 `JobEnqueueReceipt(..., state=JobState.READY, idempotency_reused=True)`」。
- §5.1 step 1-2（L1392-1402）：lookup 发生在任何 current binding/status/version 读取之前；命中时 strict parse 与 intent 比较成功后唯一构造 receipt；caller intent drift → `JobIdempotencyConflictError`；tamper → 统一 `unavailable`。
- 陈旧文字检查：全 plan grep「JobService × receipt/重建/构造/READY」仅 L2553（§13.1 断言 JobService 不构造 receipt）与 L2266/2270（composition 构造顺序），无任何「JobService 重建 receipt」残留。
- 代码事实：`JobEnqueueReceipt.__post_init__`（jobs.py:1088）要求 `state is JobState.READY`，与重建语义一致；`JobService.enqueue`（job_service.py:519-544，fix doc 证据行号吻合）含 registry gate + Store enqueue + `_publish_hint_best_effort`，证明 lookup 不得复用 enqueue/publish 路径的动机成立。
- §13.1 新增 named test `test_job_service_idempotency_lookup_returns_record_without_receipt_reconstruction_or_publish`（L2521）与 prose（L2552-2556）锁定 delegation 无副作用；manual lost-response test 改名锁定「strict persisted intent 验证完成后只有 Source facade 构造 READY/reused receipt」。

### A3. 跨章节一致性、code-generation-ready、无泄漏（Q3）

- §3.4/§5.1/§5.2/§9/§12 Item6 文字（L2490-2491）/§13.1/§15/§16/§17 全部对齐（diff + grep 核实）。
- master：状态行、Slice 2.3 evidence index（L267-274）、revision changelog（L982-990）、Slice 2.3 章节（L4002-4011）与 target 状态一致，均标注 `IMPLEMENTATION FROZEN / ITEM 6 CORRECTIVE CANDIDATE AWAITING FRESH SAME-SHA DEEPSEEK FLASH + MIMO REVIEW`。
- Scope：§11 production/test allowlist 与 §11.1 coverage matrix 零改动；public surface 不扩张（`JobIdempotencyRecord` 与 lookup facade 在 round-3 已存在，本 pass 仅改 ownership/映射）。
- Owner/cycle：jobs domain 不 import Source schema（L924-925）；facade 拥有 Source parse；STOP 禁止 JobStore 读 source 表与 Source repository 跨读 Job idempotency。
- Response-loss：lookup 先于 current binding 读取；recovery 不要求 current Job READY / definition active / current binding 未漂移（L932-934、L1397-1399）。
- Tenant：lookup 用 tenant + exact descriptor + key，cross-tenant 等价 missing（L948-949）；miss 路径的 tenant-scoped read 不会泄漏目标存在性。
- 计数：§17（L2939）「由157项变为158项」与实测一致（见 A4）。

### A4. 158 named tests 唯一；勘误仅 docs 范围；Item 1 纯合同未受影响（Q4）

- 实测：§13.1–§13.4 的 `^- test_` bullet 共 **158 项**，`sort | uniq -d` 为空（唯一）。
- 计数构成：旧名 `test_manual_response_loss_recovers_same_ready_receipt_after_job_progress_definition_disable_and_source_drift_without_publish` 被替换（rename）为 strict-validation 新名，另新增 1 个 JobService delegation owner test，净 +1（157 → 158），与 fix doc §4 声称一致。
- 旧名残留检查：docs/ 与 dayu/、tests/ 均零引用。
- 勘误范围：`git diff 3f0de57` 下本 pass 只改两份 frozen docs（target +82/-、master +44/-），fix doc 为新文件；Item 1 的 11 个 WIP path（`test_architecture_boundaries.py` 等）与三份 code-review artifact 均未被本 pass 触碰。Item 1 architecture test 的并行 diff 不计入本 pass scope。
- Item 1 纯合同：corrective 不触碰 production/tests；§13.1 改动的命名测试是计划级（尚未实现）而非冻结 WIP 文件；§11 测试 allowlist 中 `test_job_service.py`、`test_investment_sources.py`、`test_postgres_jobs.py` 均为 writable 项，新测试归属合法。

## Open Questions

无。

## Residual Risks（承接 plan §16，非新 finding）

1. Job/Schedule repository failure 无 typed code，Source public facade 只能暴露 `unavailable`，无法区分 infra failure 与 persisted tamper（plan §16.9 已记录）；如需 operator observability 区分，归独立 typed repository-error contract work unit，本 Slice 禁止按 message 补诊断。
2. corrective candidate 尚未经 Controller acceptance；双路 fresh same-SHA review 均 PASS/open0 且 Controller acceptance 前，implementation 保持冻结。

## 结论

本 DeepSeek Flash 独立 plan re-review 对冻结 candidate（target `e589cc5e…`、master `9f5ee842…`、fix `56bb7e98…`）给出 **PASS / open H/M/L = 0/0/0**。Item 6 corrective 已闭合 Job/Schedule 无 typed-code 异常的统一 `unavailable` 映射与 manual receipt owner 归属，未引入 scope/owner/cycle/response-loss/tenant 泄漏；158 项 named tests 唯一；勘误严格 docs-only。

**Status: PASS**
**Summary: Item 6 recovery-errors corrective candidate 通过 DeepSeek Flash 独立 plan re-review，open H/M/L=0/0/0，三份 frozen docs SHA 全程一致。**
**Files touched: docs/reviews/plan-rereview-20260812-slice-2.3-item6-recovery-errors-deepseek-flash.md（唯一写入）**
**Findings worth promoting: 无（0/0/0）**
