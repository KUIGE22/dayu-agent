# Slice 2.2 Scheduler / Worker / Redis — MiMo Final Closure Plan Re-Review

- **Status**: PASS / open H/M/L=0/0/0
- **Reviewer**: MiMo (final closure)
- **Target plan**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`（REVIEW FIX APPLIED）
- **Baseline**: `38ddad4`
- **Prior**: `plan-rereview-20260812-...-mimo.md`（PASS/0）
- **Method**: 重读最新 target + Controller fix + prior PASS；聚焦 lookback C>=L、explicit-provider Redis admission、correlation 锁序/late re-read/valid-lease missing、PENDING availability + MATERIALIZING typed decision

## 0. Verdict

**PASS.** 四项新增/修订攻击面全部正确闭合，无新增 finding。Prior PASS 的 6 CLOSED + 3 residual 不变。

## 1. Lookback C>=L 等号算法

§5.2 step 2 精确规定：
- working cursor 重定位为最早有效 UTC candidate `C` 且 `C >= L`（`L = database_now - schedule_max_lookback_seconds`）。
- 不用严格 `get_next(L)`（会跳过 `C == L`）。
- 实现规则：以 `L - 1 minute` 转换出的 naive local minute作为croniter seed，逐个做ZoneInfo round-trip并丢弃 `candidate_utc < L`，首个 `>= L` 者进入 expired/eligible。
- `C == L` 必须按 grace 进入 expired 或 eligible，绝不能被 lookback audit 吞掉。
- 重定位候选计入 candidate scan limit。

**证据**: `test_scheduler_lookback_relocation_includes_fire_exactly_equal_to_boundary`（§10）；`test_scheduler_misfire_boundary_is_inclusive_and_dst_cursor_is_monotonic`。

**裁决**: 正确。`C >= L` 等号边界闭合，croniter seed 用 `L - 1 min` 避免跳过 `C == L`，scan limit 覆盖重定位候选。

## 2. Production Explicit-Provider Redis Admission

§8 明确：
- "ordinary production显式provider仍必须持有REDIS admission"。
- "但因custom composition不承诺暴露durable Job/Schedule Service，direct refs允许None且admission资源仍由prepared runtime exact-once关闭；其publisher不自动注入外部provider"。
- `_PreparedQueueAdmission` 不变量：NOT_REQUIRED 全 None；POSTGRES_ONLY settings非None+Redis字段None；REDIS settings mode=event_assisted+Redis三项全非None。platform wrapper 只接受 POSTGRES_ONLY/REDIS，拒 NOT_REQUIRED。

**证据**: `test_production_explicit_provider_cannot_bypass_redis_admission`；`test_production_explicit_provider_keeps_custom_composition_after_redis_admission`。

**裁决**: 正确。explicit provider 仍需 Redis admission（PRODUCTION mode），但 custom composition 的 Job/Schedule Service refs 允许 None。admission 资源由 prepared runtime exact-once 关闭，不泄漏。

## 3. Correlation 统一 PG 锁序 / Late Re-Read / Valid-Lease Missing Host Wait

### 3.1 统一锁序

§6.2: "所有会读取或修改同一Agent correlation的PG入口统一使用且只使用以下锁序：`job_runs -> job_attempts -> job_leases（存在时） -> agent_run_correlations`"。精确覆盖 reserve/authorize/heartbeat/complete/fail/recover/reconcile 七个入口。禁止先锁 correlation 再回锁 job/attempt。

**证据**: `test_correlation_mutations_share_job_attempt_lease_correlation_lock_order_without_deadlock`。

### 3.2 Late Re-Read

§6.2: "reconcile/recover允许先做一次不加锁的correlation locator读取以取得job/attempt identity，但该读取不是授权真源；随后必须按统一顺序加锁全部父行，最后锁定并逐字段重读correlation，若缺失/漂移则返回closed invariant且零mutation"。

"heartbeat/complete/fail必须在锁定job/attempt/lease后再做同事务late correlation re-read，不能用锁前未发现缓存；reserve同样在父行锁内重验attempt/lease/job状态后才插入"。

**证据**: `test_reserve_racing_heartbeat_complete_or_fail_has_one_late_rechecked_linearized_outcome`。

### 3.3 Valid-Lease Missing Host Wait

§6.2: "Host missing且`lease_expires_at <= database_now`才允许既有NO_HOST targeted recover，Host missing但lease仍有效必须返回`ACTIVE_WAIT`并在同一correlation继续heartbeat/reobserve，零recover、零新attempt"。

**证据**: `test_valid_lease_missing_host_waits_without_targeted_or_generic_recovery`；`test_expired_lease_missing_host_alone_allows_targeted_recovery`。

**裁决**: 正确。valid-lease missing Host 不进入 recover，继续 heartbeat/reobserve；expired lease missing Host 才允许 targeted recover。与 Slice 2.1 的 `NO_HOST_RUN` 语义一致但增加了 lease 有效性前置条件。

## 4. PENDING Availability + MATERIALIZING Committed Replay

### 4.1 PENDING availability gate

§6.1: "activate以及PENDING occurrence的`begin_materialization`之前必须经JobService窄availability方法证明：既有descriptor registry含同job_type逐字段相等descriptor，且execution registry含与该descriptor绑定的handler；缺失/漂移时零enqueue、同事务disable schedule并把仍为PENDING的occurrence按`schedule_disabled`收敛"。

**证据**: `test_schedule_activation_and_materialization_reject_unregistered_descriptor_without_job`；`test_pending_availability_failure_disables_and_skips_before_materializing`。

### 4.2 MATERIALIZING committed replay bypasses availability

§6.1: "证明成功后即使registry随后漂移，MATERIALIZING的durable commitment也不能撤销"。

"MATERIALIZING replay不再重复执行可否决的handler availability gate，而是由ScheduleService把store刚返回的typed persisted `ScheduleMaterializationDecision`传给JobService窄`enqueue_committed_schedule_occurrence(scope, decision)`入口"。

"decision是ScheduleService内部trusted boundary，不是跨事务仍持有数据库锁的假承诺；真实state/identity由随后`mark_enqueued(scope, occurrence_id, expected_snapshot_fingerprint, job_id)`再次在ScheduleStore锁内重验"。

**证据**: `test_materializing_replay_ignores_later_registry_drift_and_converges_to_one_job`。

**裁决**: 正确。PENDING 有 availability gate（descriptor + execution registry）；MATERIALIZING 是 durable commitment，replay 用 typed `ScheduleMaterializationDecision` 绕过 availability gate，但 `mark_enqueued` 仍在 ScheduleStore 锁内重验 snapshot fingerprint。registry 漂移不影响已 materializing 的 occurrence。

## 5. Additional New Tests Verified

- `test_correlated_heartbeat_renews_past_business_deadline_with_governance_required_action`：correlated heartbeat 遇 deadline 只续 lease + governance-required，不走 generic terminalization。
- `test_correlated_complete_and_fail_are_rejected_until_host_terminal_reconciliation`：`complete`/`fail` 遇未终结 correlation 抛 `JobGovernanceRequiredError`，进入 `WAITING_FOR_CORRELATION`。
- `test_handler_return_with_active_correlation_waits_and_heartbeats_without_new_claim`：handler 返回后 correlation 仍活跃 → 继续 heartbeat，不 claim 新 attempt。
- `test_handler_result_after_drain_abandon_is_ignored_without_receipt`：drain_abandon 后 handler return/error 全忽略，不写 receipt。
- `test_governance_keyset_rotation_prevents_long_active_wait_from_starving_later_rows`：cursor 分页防止 ACTIVE_WAIT 饿死后续行。

## 6. Residual (不变)

1. heartbeat 无 jitter 同相峰值 — 部署方错开启动。
2. 非协作 handler grace 后仍运行 — 第二信号 hard stop，lease recovery 接管。
3. Redis hint 天然可丢 — PG poll 兜底。

## 7. Final Verdict

**PASS / open H/M/L=0/0/0.** lookback C>=L、explicit-provider Redis admission、correlation 锁序/late re-read/valid-lease missing、PENDING availability + MATERIALIZING typed decision 全部正确闭合。无新增 finding。Plan 可进入 accepted baseline commit。
