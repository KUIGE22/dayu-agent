# Final4 Closure Re-review：Slice 2.1 durable job queue

- **Gate**：final4 closure-only re-review
- **Branch / baseline**：`codex/investment-platform` / `61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Target**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Scope**：逐项确认 FINAL4-001 和 FINAL4-002；bounded regression check 确保 FINAL2/3/master/residual/public contracts 未回退
- **Valid prior reviews**：
  - `docs/reviews/plan-controller-final3-rereview-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`（Controller，FINAL4-001 M / FINAL4-002 L）
  - `docs/reviews/plan-fix-20260811-slice-2.1-final-codegen-closure-terra.md`（Terra fix，FINAL4 全部 FIXED-IN-PLAN）
  - `docs/reviews/plan-final3-corrective-rereview-20260811-slice-2.1-mim.md`（MiM prior，PASS open 0/0/0）
- **Review-integrity**：本 review 独立于 Terra fix 与任何另一 reviewer 的本轮新产物。仅读取：AGENTS.md、master plan Phase2/Slice2.1、target plan（全文）、Controller final3 re-review adjudication、Terra fix、MiM prior review。不读取 Flash 本轮 artifact。
- **External actions**：未执行 commit、push、PR、deploy、live、paid、Docker、PostgreSQL、tests、pyright、ruff 或任何实现动作。

## 1. FINAL4-001 逐项确认

### 1.1 §7D 与 §3.2 一致性

**目标**：验证 §7D 的 `JobService.recover` 描述与 §3.2 完全一致。

**证据**：
- §3.2（第292行）："`JobService.recover` 是唯一 public recovery orchestration：先调用 `list_expired_agent_run_correlations(scope)`，其结果固定按 `created_at ASC, id ASC`；逐条执行上述四步 reconciliation，只对 `NO_HOST_RUN` decision 以该 decision observation 的 `sha256` 调 `recover_agent_run_after_no_host`，`HOST_ACTIVE_WAIT`、任一 terminal、stale 或 invariant decision 均不得进入任一 recover primitive；最后且仅最后调用一次 `job_store.recover(scope)` 收敛无 committed correlation 的 attempt。返回 tuple 仅包含本调用实际产生的非 `None` `JobRecoveryResult`，先按已排序 correlation 的 targeted 成功结果，后接 generic result 按 `(job_id ASC, attempt_id ASC NULLS FIRST)`；不得暴露 targeted method 为 JobService public API。"
- §7D（第388行）：完全相同的文本。

**Verdict**：**MATCH**。§7D 已删除旧句"generic recover only after NO_HOST_RUN, never ... after HOST_ACTIVE_WAIT"，现逐字复用 §3.2 描述。

### 1.2 NO_HOST_RUN 只进 targeted

**目标**：验证 `NO_HOST_RUN` decision 只进入 targeted `recover_agent_run_after_no_host`，不进入 generic recover。

**证据**：
- §3.2："只对 `NO_HOST_RUN` decision 以该 decision observation 的 `sha256` 调 `recover_agent_run_after_no_host`"
- §7D：相同描述。
- §4.2.8（第318行）：`recover_agent_run_after_no_host` 的精确语义：只供 `JobService.recover` 在同一轮刚得到 `NO_HOST_RUN` 后调用。

**Verdict**：**CONFIRMED**。`NO_HOST_RUN` 只进 targeted method。

### 1.3 全部 correlations 后恰一次 generic 且仅 NOT EXISTS correlation

**目标**：验证 correlation enumeration 完成后，始终且仅调用一次 generic recover，后者只处理 `NOT EXISTS correlation` 的 attempt。

**证据**：
- §3.2："最后且仅最后调用一次 `job_store.recover(scope)` 收敛无 committed correlation 的 attempt。"
- §4.2.7（第316行）："SQL 必须以 `NOT EXISTS (SELECT 1 FROM agent_run_correlations correlation WHERE correlation.tenant_id = attempt.tenant_id AND correlation.attempt_id = attempt.id)` 证明该 attempt **从未提交 correlation**；不得触碰任何 correlation-attached attempt。"
- §7D：相同描述。

**Verdict**：**CONFIRMED**。恰一次 generic，且仅 NOT EXISTS correlation。

### 1.4 mixed active + NO_HOST_RUN + no-correlation 稳定顺序

**目标**：验证 mixed batch 稳定返回 targeted results 后接 generic results。

**证据**：
- §3.2："返回 tuple 仅包含本调用实际产生的非 `None` `JobRecoveryResult`，先按已排序 correlation 的 targeted 成功结果，后接 generic result 按 `(job_id ASC, attempt_id ASC NULLS FIRST)`"
- §7D：相同描述。
- §8 测试：`test_job_service_recover_returns_targeted_then_generic_results_in_stable_order`、`test_targeted_no_host_recovery_isolated_from_active_and_no_correlation_attempts`

**Verdict**：**CONFIRMED**。稳定顺序已锁定，且有具名测试覆盖。

### 1.5 FINAL4-001 总结

**S21-CTRL-FINAL4-001 (Medium)**：**CLOSED**。§7D 已与 §3.2 逐字一致，NO_HOST_RUN 只进 targeted，generic 恰一次且仅 NOT EXISTS，mixed batch 稳定顺序已锁定。

## 2. FINAL4-002 逐项确认

### 2.1 16 个测试在 §7 A/B/C/D 按 1/5/3/7 各出现一次

**目标**：验证 Controller 指定的 16 个测试已按 A=1, B=5, C=3, D=7 补入 §7 对应 slice。

**证据**：

**A (1 test)**：
- `test_ensure_reserved_run_rejects_invalid_32_hex_before_sqlite_write` — §7A 第385行 ✓

**B (5 tests)**：
- `test_disabled_definition_rejects_enqueue` — §7B 第386行 ✓
- `test_postgres_jobs_cross_tenant_reads_are_not_found_and_writes_denied` — §7B 第386行 ✓
- `test_postgres_jobs_rls_setting_does_not_leak_between_transactions` — §7B 第386行 ✓
- `test_0003_grant_matrix_exact` — §7B 第386行 ✓
- `test_0003_upgrade_downgrade_upgrade_and_external_dependency_refusal` — §7B 第386行 ✓

**C (3 tests)**：
- `test_claim_empty_returns_none` — §7C 第387行 ✓
- `test_ready_deadline_sets_exact_safe_failure_and_single_event_without_attempt` — §7C 第387行 ✓
- `test_complete_cancel_intent_precedes_deadline_and_success` — §7C 第387行 ✓

**D (7 tests)**：
- `test_reserved_missing_replay_has_no_duplicate_event` — §7D 第388行 ✓
- `test_host_failed_or_unsettled_terminalizes_with_retry_policy` — §7D 第388行 ✓
- `test_host_cancelled_terminalizes_cancel_receipt` — §7D 第388行 ✓
- `test_correlation_identity_or_state_mismatch_is_invariant_failure` — §7D 第388行 ✓
- `test_job_service_recover_returns_targeted_then_generic_results_in_stable_order` — §7D 第388行 ✓
- `test_targeted_no_host_recovery_isolated_from_active_and_no_correlation_attempts` — §7D 第388行 ✓
- `test_targeted_no_host_recovery_changed_observation_state_or_fence_is_zero_mutation` — §7D 第388行 ✓

**Verdict**：**ALL 16 TESTS PRESENT**。1/5/3/7 分布正确。

### 2.2 §8 未改

**目标**：验证 §8 故障矩阵未被修改。

**证据**：
- §8（第391-431行）：完整故障矩阵表格，逐场景映射到命名测试。
- 与 Terra fix 前版本比较：表格结构、场景描述、测试名、lane 标注均未变化。
- Controller 裁决明确要求"不改 §8、算法、测试名或 completion gate"。

**Verdict**：**UNMODIFIED**。§8 未被修改。

### 2.3 FINAL4-002 总结

**S21-CTRL-FINAL4-002 (Low)**：**CLOSED**。16 个测试已按 1/5/3/7 补入 §7 A/B/C/D，§8 未改。

## 3. Bounded Regression Check

### 3.1 FINAL2-001..007 无回归

**目标**：验证 FINAL2 七项核心修复未回退。

**证据**（逐项）：
- **FINAL2-001**（job contract owner / storage import guard）：§2 owner 表、§3.1 Host protocol owner、§3.2 Service/registry owner 均保持原定位。AST guard 不变。**NO REGRESSION**。
- **FINAL2-002**（correlation-by-id lookup）：§3.2 精确声明 `get_agent_run_correlation`，§4.3.2 Service exact sequence 保持四步。**NO REGRESSION**。
- **FINAL2-003**（deadline / correlation-missing 分支）：heartbeat deadline（§4.2.3）、`correlation_missing` 唯一分支（§4.1、§4.3.1）均不变。**NO REGRESSION**。
- **FINAL2-004**（mutable lease schema）：§5 `job_leases` DDL 含 `updated_at/version`、single-release CHECK、CAS、release trigger。**NO REGRESSION**。
- **FINAL2-005**（Host UNSETTLED 映射）：§3.2 `HostRunObservationState` 含 `unsettled`，§4.3.2 唯一映射不变。**NO REGRESSION**。
- **FINAL2-006**（generic attempt receipt canonical schema）：§3.2 固定 generic schema/version、8-key canonical object 不变。**NO REGRESSION**。
- **FINAL2-007**（recover attempt state/receipt）：§4.2.5-7 每种路径的 attempt/job state、receipt outcome/safe code、next_available_at 不变。**NO REGRESSION**。

### 3.2 FINAL3-001..005 无回归

**目标**：验证 FINAL3 五项修复未回退。

**证据**（逐项）：
- **FINAL3-001**（correlation-safe recovery）：§4.2.7 SQL `NOT EXISTS`、§3.2 `recover_agent_run_after_no_host` signature、§3.2 `JobService.recover` fixed sequence 均不变。**NO REGRESSION**。
- **FINAL3-002**（complete cancel/deadline 顺序）：§4.2.4 固定 `cancel intent → deadline → success` 不变。**NO REGRESSION**。
- **FINAL3-003**（reserved run ID Host enforcement）：§3.1 `RunRegistry.ensure_reserved_run` 格式校验唯一 owner 不变。**NO REGRESSION**。
- **FINAL3-004**（ready deadline terminal state）：§4.2.2 固定 job=`failed`、`safe_failure_code=deadline_exceeded`、单一 event 不变。**NO REGRESSION**。
- **FINAL3-005**（master Slice 2.1 五行同步）：§1 逐字比较确认七个维度全部 MATCH（从 MiM prior review 证据）。**NO REGRESSION**。

### 3.3 Master 五行

**目标**：验证 master Slice 2.1 Allowed/API/Invariants/Completion/Tests 五行与 target 一致。

**证据**：从 MiM prior review §1 的七个维度逐字比较，全部 MATCH。master 状态与 Phase 1 history 未改写。

**Verdict**：**NO REGRESSION**。

### 3.4 Residual Risk

**目标**：验证残余风险描述未变化。

**证据**：§9（第434-438行）残余风险归属与之前一致：TOCTOU residual、Slice 2.2/2.3 owner、external provider exactly-once、backoff jitter、business payload schema 均不变。

**Verdict**：**NO REGRESSION**。

### 3.5 Public Contracts

**目标**：验证公共契约（signature、DTO、Protocol）未变化。

**证据**：
- §3.2 公共 `JobService` 签名（11 个方法）不变。
- §3.2 `JobStoreProtocol` 签名（13 个方法）不变。
- §3.2 15 个 public DTO 字段、类型、默认值不变。
- §3.2 `HostRunReaderProtocol.get_run` signature 不变。
- §3.1 `RunRegistryProtocol.ensure_reserved_run` signature 不变。

**Verdict**：**NO REGRESSION**。

## 4. Adversarial Spot-check

### 4.1 §7D recovery branch 文本冲突

**目标**：确认旧句"generic recover only after NO_HOST_RUN, never ... after HOST_ACTIVE_WAIT"已完全删除。

**证据**：grep 搜索该旧句在 target plan 中无匹配。§7D 现为与 §3.2 逐字一致的描述。

**Verdict**：**CLEAN**。旧句已删除。

### 4.2 16 个测试完整性

**目标**：确认 Controller 指定的 16 个测试全部在 §7 中出现。

**证据**：§2.1 已逐项核验，16/16 全部 present。

**Verdict**：**COMPLETE**。

### 4.3 §8 与 §7 测试名一致性

**目标**：确认 §8 故障矩阵中的测试名与 §7 Tests 清单一致。

**证据**：§8 表格中每个测试名均可在 §7 A-E 的 Tests 清单中找到对应条目。无孤立项。

**Verdict**：**CONSISTENT**。

## 5. Final conclusion

**PASS** — open H/M/L = 0/0/0

S21-CTRL-FINAL4-001 (Medium) 已 CLOSED：§7D 与 §3.2 逐字一致，NO_HOST_RUN 只进 targeted，generic 恰一次且仅 NOT EXISTS，mixed batch 稳定顺序已锁定。

S21-CTRL-FINAL4-002 (Low) 已 CLOSED：16 个测试已按 1/5/3/7 补入 §7 A/B/C/D，§8 未改。

FINAL2-001..007、FINAL3-001..005 全部保持 CLOSED，无回归。Master 五行、residual risk、public contracts 均未回退。计划可进入 implementation gate。

---

**Output file**: `docs/reviews/plan-final4-closure-rereview-20260811-slice-2.1-mim.md`
**Timestamp**: 20260811-171627
