# Controller Final3 Re-review Adjudication：Slice 2.1 durable job queue

- **Gate**：final3 corrective dual plan re-review adjudication
- **Branch / baseline**：`codex/investment-platform` / `61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Target**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Source reviews**：
  - `docs/reviews/plan-final3-corrective-rereview-20260811-slice-2.1-mim.md`
  - `docs/reviews/plan-final3-corrective-rereview-20260811-slice-2.1-flash.md`
- **Controller conclusion**：`PLAN FIX REQUIRED / OPEN H/M/L = 0/1/1`
- **Scope**：只裁决当前计划文本与 code-generation readiness；不授权 production、tests、README、Docker、PostgreSQL、implementation、commit、push、PR、deploy、live 或 paid action。

## 1. 已关闭项

`S21-CTRL-FINAL2-001..007` 与 `S21-CTRL-FINAL3-001..005` 的核心契约均已闭合：owner/DAG、descriptor-only registry、Host reserved identity、correlation-by-ID lookup、deadline、versioned lease、UNSETTLED、generic receipt、recovery result、correlation-safe targeted recovery、complete tiebreak、reserved ID validator、ready-deadline observation 与 master Slice 2.1 五行同步均无回归。

MiM 的 `PASS / open 0/0/0` 可作为上述闭合项的支持证据，但不能作为本 gate 的最终通过结论：它没有识别下述直接文本冲突，也没有识别 Flash 已证明的实施测试 owner 缺口。

## 2. Accepted finding：S21-CTRL-FINAL4-001（Medium）

### 证据

目标 §3.2 已把 public `JobService.recover(scope)` 锁定为：

1. 枚举全部 expired committed correlations；
2. 对每条执行 correlation lookup → Host read → strict mapping → reconciliation；
3. 只对 `NO_HOST_RUN` decision 调 targeted `recover_agent_run_after_no_host`；
4. 全部 correlation 处理完后，恰好一次调用 generic `job_store.recover(scope)`，后者以 SQL `NOT EXISTS agent_run_correlations` 只收敛无 committed correlation 的 attempt。

但 §7D 仍保留旧句：`generic recover only after NO_HOST_RUN, never ... after HOST_ACTIVE_WAIT`。在同一批次同时存在 active correlation 与无-correlation expired attempt 时，该句可要求完全跳过 generic recover；这与 §3.2 的固定 public algorithm、§4.2.7 的 `NOT EXISTS` 隔离及 `test_targeted_no_host_recovery_isolated_from_active_and_no_correlation_attempts` 的混合场景冲突。

### 裁决

**ACCEPTED / Medium / OPEN**。

### 唯一最小修复

只修 target §7D 的 recovery branch 文本，使其逐字等于 §3.2：

- sorted expired committed correlations → 每条 terminal-only reconciliation；
- 仅 `NO_HOST_RUN` decision 进入 targeted recovery；
- active/terminal/stale/invariant decision 不进入 targeted 或以自身作为 generic 输入；
- correlation enumeration 完成后，始终且仅调用一次 generic recover，后者只处理 `NOT EXISTS correlation` 的 attempts；
- mixed active + NO_HOST_RUN + no-correlation batch 仍返回 targeted results 后接 generic results 的稳定顺序。

不得改变 public signature、状态机、owner、Slice 2.2/2.3 边界或 residual。

## 3. Accepted finding：S21-CTRL-FINAL4-002（Low）

### 证据

Flash 证明 §8 completion matrix 中 16 个 mandatory named tests 只在最终 gate 出现，未被 §7A-E 任一 implementation slice 认领。计划又明确禁止以相邻测试替代，因此按 §7 小批实施可能漏写，直到最终门禁才暴露。

### 裁决

**ACCEPTED / Low / OPEN**。

### 唯一最小修复

只把现有测试名补入 §7 对应 slice 的 `Tests` 清单，不改测试名、算法或 gate：

- **A**：`test_ensure_reserved_run_rejects_invalid_32_hex_before_sqlite_write`。
- **B**：`test_disabled_definition_rejects_enqueue`、`test_postgres_jobs_cross_tenant_reads_are_not_found_and_writes_denied`、`test_postgres_jobs_rls_setting_does_not_leak_between_transactions`、`test_0003_grant_matrix_exact`、`test_0003_upgrade_downgrade_upgrade_and_external_dependency_refusal`。
- **C**：`test_claim_empty_returns_none`、`test_ready_deadline_sets_exact_safe_failure_and_single_event_without_attempt`、`test_complete_cancel_intent_precedes_deadline_and_success`。
- **D**：`test_reserved_missing_replay_has_no_duplicate_event`、`test_host_failed_or_unsettled_terminalizes_with_retry_policy`、`test_host_cancelled_terminalizes_cancel_receipt`、`test_correlation_identity_or_state_mismatch_is_invariant_failure`、`test_job_service_recover_returns_targeted_then_generic_results_in_stable_order`、`test_targeted_no_host_recovery_isolated_from_active_and_no_correlation_attempts`、`test_targeted_no_host_recovery_changed_observation_state_or_fence_is_zero_mutation`。

## 4. Review-source disposition

- **MiM**：结论 `PASS / 0/0/0`；其 FINAL2/FINAL3、master、DAG、signature、状态机和 residual 核验保留为有效支持证据，但“无 open finding”被 Controller 上述直接证据覆盖。
- **Flash**：结论 `FAIL / 0/0/1`；L-01 全部接受并映射为 `S21-CTRL-FINAL4-002`。其 FINAL2/FINAL3 closure 与其余 non-finding 结论保留。
- **Controller observation**：§7D 与 §3.2 的 mixed-batch recovery 冲突映射为 `S21-CTRL-FINAL4-001`；该 finding 不改变 Final3 核心修复，只消除实施步骤中的旧措辞。

## 5. 下一 gate

Terra 只可修改：

1. `docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`；
2. `docs/reviews/plan-fix-20260811-slice-2.1-final-codegen-closure-terra.md`。

修复后状态应为 `FINAL REVIEW OBSERVATIONS FIXED / AWAITING FINAL CLOSURE RE-REVIEW`，并在 fix artifact 映射 `S21-CTRL-FINAL4-001..002`。master 五行、production、tests、README、source reviews 与其它 artifacts 全部冻结。随后必须由独立 MiM + Flash 做 closure-only re-review；open H/M/L 未归零前不得接受计划、进入 implementation 或 commit。
