# Final Closure Plan Re-review — Slice 2.2 Scheduler / Worker / Redis

## Scope

- **Mode**: closure-only re-review（仅验证指定新增区域 + 全局 new-finding scan）
- **Target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`（607 行最终版）
- **Baseline**: `38ddad4`
- **Output file**: `docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-final-mim.md`
- **Review sources**: MiM original PASS-WITH-RISKS、Controller fix（108 行）、MiM corrective PASS（0/0/0）
- **Excluded**: 不修改任何文件；不运行长测试/live/model/broker

## Conclusion

**PASS / open H/M/L = 0/0/0**

Plan 从 corrective PASS 版的 572 行进一步扩展至 607 行，新增 lookback C>=L 等号边界规则、production explicit-provider Redis admission 强制、correlation 统一 PG 锁序/late re-read/valid-lease missing-Host wait、PENDING availability gate + MATERIALIZING committed replay typed decision，以及 17 个新命名测试。所有指定验证区域均已闭合，未发现新 finding。

---

## 区域验证

### 1. Lookback C>=L 等号边界算法（§5.2 step 2）

**新增文本**（L240）：
> "working cursor 必须重定位为最早有效 UTC candidate C 且 `C >= L`，不能逐条展开边界外 fire，也不能用严格 `get_next(L)` 跳过 `C == L`。唯一实现规则是以 `L - 1 minute` 转换出的 naive local minute 作为 croniter seed，逐个做 ZoneInfo round-trip/DST 分类并丢弃 `candidate_utc < L`，首个 `>= L` 者进入第 4/5 步；这些重定位候选同样计入 candidate scan limit。`C == L` 必须按 grace 进入 expired 或 eligible，绝不能被 lookback audit 吞掉。"

**验证**：
- C==L 的候选被显式保留，不被 lookback audit 吞掉——正确。
- 实现规则以 `L - 1 minute` 为 croniter seed 做逐个 round-trip，明确且可编码。
- 重定位候选计入 scan limit——防止无限循环。
- 新命名测试 `test_scheduler_lookback_relocation_includes_fire_exactly_equal_to_boundary`（§10 L490）覆盖此边界。

**结论**: 闭合。

### 2. Production explicit-provider 仍需 Redis admission（§8 / §4.1）

**新增文本**（L104）：
> "production 即使显式注入 provider 也必须先取得 REDIS admission，显式 provider 只替换 composition 内容、绝不能成为 Redis 绕过路径"

**新增文本**（L411）：
> "ordinary production 显式 provider 仍必须持有 REDIS admission，但因 custom composition 不承诺暴露 durable Job/Schedule Service，direct refs 允许 None 且 admission 资源仍由 prepared runtime exact-once 关闭；其 publisher 不自动注入外部 provider。"

**新增命名测试**（§10 L463-464）：
- `test_production_explicit_provider_cannot_bypass_redis_admission`
- `test_production_explicit_provider_keeps_custom_composition_after_redis_admission`

**验证**：
- `_PreparedQueueAdmission.kind` 三值（`not_required`/`postgres_only`/`redis`）在 §4.1 明确；production 永远走 `redis`。
- ordinary wrapper 对 NOT_REQUIRED/POSTGRES_ONLY 的显式 provider 仍强制 Redis admission——绕不过。
- platform wrapper 只接受 POSTGRES_ONLY/REDIS，拒 NOT_REQUIRED——双重封锁。
- §12 STOP condition L591："production Redis 首次 admission 发生在 path/PG/S3/Host/workspace 副作用后"。
- §12 STOP condition L591："用 callback/bool 伪造 admission"。

**结论**: 闭合。

### 3. Correlation 统一 PG 锁序 / late re-read / valid-lease missing Host wait（§6.2）

**新增文本**（L315）：
> "所有会读取或修改同一 Agent correlation 的 PG 入口统一使用且只使用以下锁序：`job_runs -> job_attempts -> job_leases（存在时） -> agent_run_correlations`。精确覆盖 reserve_agent_run_correlation、authorize_agent_run_start、heartbeat、complete、fail、recover_agent_run_after_no_host 与 reconcile_agent_run_terminal；禁止任何入口先 FOR UPDATE correlation 再回锁 job/attempt。"

**新增文本**（L315）：
> "reconcile/recover 允许先做一次不加锁的 correlation locator 读取以取得 job/attempt identity，但该读取不是授权真源；随后必须按统一顺序加锁全部父行，最后锁定并逐字段重读 correlation，若缺失/漂移则返回 closed invariant 且零 mutation。heartbeat/complete/fail 必须在锁定 job/attempt/lease 后再做同事务 late correlation re-read，不能用锁前"未发现"缓存。"

**新增文本**（L309）：
> "Host missing 且 lease_expires_at <= database_now 才允许既有 NO_HOST targeted recover，Host missing 但 lease 仍有效必须返回 ACTIVE_WAIT 并在同一 correlation 继续 heartbeat/reobserve，零 recover、零新 attempt"

**新增命名测试**（§10 L517-527）：
- `test_correlation_mutations_share_job_attempt_lease_correlation_lock_order_without_deadlock`
- `test_reserve_racing_heartbeat_complete_or_fail_has_one_late_rechecked_linearized_outcome`
- `test_valid_lease_missing_host_waits_without_targeted_or_generic_recovery`
- `test_expired_lease_missing_host_alone_allows_targeted_recovery`

**验证**：
- 7 个入口全部列出，锁序固定为 `job_runs -> attempts -> leases -> correlations`——正确。
- late re-read 在父行锁内，不依赖锁前缓存——正确。
- valid-lease missing-Host 返回 ACTIVE_WAIT 而非 targeted recover——正确。
- expired-lease missing-Host 允许 targeted recover——正确。
- late re-read 后 correlation 缺失/漂移返回 closed invariant——正确。

**结论**: 闭合。

### 4. PENDING availability 与 MATERIALIZING committed replay typed decision（§6.1）

**新增文本**（L297）：
> "ScheduleService 可注册 disabled draft。activate 以及 PENDING occurrence 的 begin_materialization 之前必须经 JobService 窄 availability 方法证明：既有 descriptor registry 含同 job_type 逐字段相等 descriptor，且 execution registry 含与该 descriptor 绑定的 handler；缺失/漂移时零 enqueue、同事务 disable schedule 并把仍为 PENDING 的 occurrence 按 schedule_disabled 收敛。availability proof 与 begin_materialization 按 schedule 锁线性化；证明成功后即使 registry 随后漂移，MATERIALIZING 的 durable commitment 也不能撤销。"

**新增文本**（L299）：
> "MATERIALIZING replay 不再重复执行可否决的 handler availability gate，而是由 ScheduleService 把 store 刚返回的 typed persisted ScheduleMaterializationDecision 传给 JobService 窄 enqueue_committed_schedule_occurrence(scope, decision) 入口。该入口不持有或反向注入 ScheduleStore；它只接受 action=enqueue、occurrence.state=materializing、非空 snapshot，并重算 snapshot→JobEnqueueRequest 与 request fingerprint 逐字段闭合后调用同一 Postgres enqueue/idempotency 真源。"

**新增命名测试**（§10 L494-496）：
- `test_schedule_activation_and_materialization_reject_unregistered_descriptor_without_job`
- `test_pending_availability_failure_disables_and_skips_before_materializing`
- `test_materializing_replay_ignores_later_registry_drift_and_converges_to_one_job`

**验证**：
- PENDING availability gate：descriptor + execution registry 必须都匹配，缺失则 disable + skip——正确。
- MATERIALIZING replay：跳过 availability gate，使用 typed decision，不调用 handler——正确。
- `enqueue_committed_schedule_occurrence` 是窄入口，不持有 ScheduleStore——正确。
- `mark_enqueued` 在 ScheduleStore 锁内重验 snapshot fingerprint——正确。
- availability proof 与 begin_materialization 按 schedule 锁线性化——正确。
- durable commitment 不可撤销——正确。

**结论**: 闭合。

---

## 全局 New-Finding Scan

逐区域扫描 607 行 plan + 108 行 Controller fix，未发现新 H/M/L finding：

- **Closed DTO**（§5.1）：12 个 frozen DTO + 8 个 closed enum/error，字段全部精确。新增 `ScheduleReservationBatch`/`ScheduleReservationResult`、`ScheduleMaterializationDecision`/`ScheduleMarkEnqueuedResult` 有完整字段定义。无 open。
- **Exact owners**（§3）：28 行 owner 表 + dependency DAG 完整。CLI 共享文件修改范围在 §3/§8 双重锁定（"arg_parsing.py 只注册 nested parser" 等）。两处 lazy import 明确标注（§3 L154）。无 open。
- **Startup call graph**（§8）：两个 public wrapper → 一个 private root；`_PreparedQueueAdmission` 三态不变量（§8 L409）；ordinary production 显式 provider 强制 Redis admission（§8 L104/L411）；platform wrapper 拒 NOT_REQUIRED。无 open。
- **Materializing replay**（§6.1/§7.4）：typed decision → narrow enqueue entry → mark 重验；availability gate 只在 PENDING→MATERIALIZING 时执行一次；MATERIALIZING replay 跳过 gate。无 open。
- **Misfire**（§5.2）：grace 等号边界（`<=`）、lookback C>=L 重定位规则、candidate scan limit + disable、coalesce_one + expired 组。§10 有 7 个 misfire/lookback/scan 命名测试。无 open。
- **Correlated heartbeat**（§6.2）：`JobHeartbeatAction={renewed, governance_required}`；correlated deadline → 续 lease + governance-required；complete/fail 遇 correlation → `JobGovernanceRequiredError` → `WAITING_FOR_CORRELATION`。§10 有 4 个 correlated heartbeat 测试。无 open。
- **Drain**（§7.5）：首信号 cooperative + `drain_abandon_requested` 线性化点 + WAITING_FOR_INNER_WORK；第二信号 `os._exit(1)` hard-stop；§10 有 6 个 drain 命名测试。无 open。
- **CI lanes**（§10 §11）：五条独立 pytest 命令 + workflow ignore 合同 + PG16/Redis digest 显式 pull。无 open。
- **DAG/layering**（§3）：Storage 不 import Host/Service/Redis；Host 不 import concrete PG store。§12 STOP conditions 完整对齐。无 open。
- **Type safety**：§3 禁止 `Any`/`object`/`cast`/`type: ignore`/`getattr`/`hasattr`。§11 门禁 2 pyright 0 errors。无 open。
- **Docstrings**：§11 门禁 4 要求完整中文 Args/Returns/Raises。无 open。

---

## Prior Finding Closure Summary

| Finding | Status | Evidence |
| --- | --- | --- |
| MiM M-001 (croniter DST) | CLOSED | §5.2 empirical gate + §9 Slice A pre-edit gate + §10 named test |
| MiM M-002 (CAS return type) | CLOSED | §5.1 ScheduleReserveAction + §5.3 ScheduleReservationResult |
| MiM M-003 (worker_id reason) | CLOSED | §6.1 security rationale + test assertion |
| MiM L-001 (INTEGRATION rejection) | CLOSED | §4.1/§8 ordinary wrapper rejection + §10 2 named tests |
| MiM L-002 (CLI file scope) | CLOSED | §3/§8 per-file mechanical-only constraints |
| MiM Open Question (HostRunCancellationProtocol) | CLOSED | §6.2 runtime-checkable Protocol in job_service.py |
| Terra S22-001..009 | ALL CLOSED | §5.3 materializing + snapshot + §6.2 governance + §7.5 drain + §8 startup + §10 tests |
| Controller 5 收口 | ALL CLOSED | §5.1 content immutability + §5.2 replay timestamps + §5.3 skipped_conflict + §10 fixture rules + §6.1/§8 empty registry |
