# Final Round-2 Closure Plan Re-review — Slice 2.2 Scheduler / Worker / Redis

## Scope

- **Mode**: final round-2 closure-only re-review
- **Target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`（613 行最终版，SHA256 `1b4f46746aa24d64f9e4251de0e6c3e8c46137dc7b284e6732f9d1c3aae89829`）
- **Baseline**: `38ddad4`
- **Output file**: `docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-final2-mim.md`
- **Excluded**: 不修改任何文件；不运行长测试/live/model/broker

## Conclusion

**PASS / open H/M/L = 0/0/0**

三项新增区域全部闭合，此前所有 closure 无回归，未发现 blocking 新 finding。

---

## 新增区域验证

### 1. generic recover 纳入统一锁序 + READ COMMITTED 双 statement refreshed-snapshot late correlation re-read

**位置**: §6.2 L315

**新增文本**：
> "所有会读取或修改同一 Agent correlation 的 PG 入口统一使用且只使用以下锁序：`job_runs -> job_attempts -> job_leases（存在时） -> agent_run_correlations`。精确覆盖 `reserve_agent_run_correlation`、`authorize_agent_run_start`、`heartbeat`、`complete`、`fail`、generic `recover(scope)`、`recover_agent_run_after_no_host` 与 `reconcile_agent_run_terminal`；禁止任何入口先 FOR UPDATE correlation 再回锁 job/attempt。"
>
> "generic recover 即使候选 SQL 含 `NOT EXISTS correlation` 也只能把它当无锁候选过滤：必须在同一 READ COMMITTED 事务中先用第一条 statement 取得父行锁，再用**第二条独立 statement** 取得刷新后的 statement snapshot 并 late lock/re-read correlation，不能把候选、锁父行、NOT EXISTS 复核和 terminal UPDATE 压成一个旧 snapshot statement；有任一已提交 correlation 即跳过且零 mutation。"

**验证**：
- 8 个入口全部列出，generic `recover(scope)` 已被纳入统一锁序——正确。
- READ COMMITTED 双 statement 模式明确：第一条 statement 锁父行，第二条 statement 用刷新后的 snapshot late re-read correlation——正确。
- "不能把候选、锁父行、NOT EXISTS 复核和 terminal UPDATE 压成一个旧 snapshot statement"——明确禁止单 statement 旧 snapshot 语义——正确。
- "有任一已提交 correlation 即跳过且零 mutation"——safe fail-closed——正确。
- §10 L523 新增 `test_generic_recover_racing_correlation_reservation_late_rechecks_and_skips`——覆盖此竞态。

**结论**: 闭合。

### 2. valid-lease missing Host 的 MISSING_HOST_WAIT 停止续租并以 persisted expiry 收敛

**位置**: §6.2 L309 + §7.3 L347 + §6.2 L313

**新增文本**（L309）：
> "Host missing 但 lease 仍有效返回 `MISSING_HOST_WAIT`：零 recover、零新 attempt，Worker 按 reobserve interval 继续读取同一 reserved id，但从第一次 missing observation 起**停止该 attempt 后续 heartbeat/续租**并保留 PG 中已提交的 `lease_expires_at` 作为唯一等待上界；Host 若在 expiry 前出现则转 `ACTIVE_WAIT` 并恢复同一 lease heartbeat，若到 expiry 仍 missing 则先重新读取 PG+Host、再走 targeted recover。"

**新增文本**（L347）：
> "Host missing -> MISSING_HOST_WAIT + stop renewal until persisted expiry/recovery"

**新增文本**（L313）：
> "Host missing 时进入 `MISSING_HOST_WAIT` 子态并按上段停止续租、等待 persisted expiry/targeted recovery"

**验证**：
- `MISSING_HOST_WAIT` 是新增的 `AgentRunGovernanceAction` closed value（§6.2 L305）——正确。
- "停止该 attempt 后续 heartbeat/续租"——不再无限续租——正确。
- "保留 PG 中已提交的 `lease_expires_at` 作为唯一等待上界"——以 persisted expiry 收敛——正确。
- "Host 若在 expiry 前出现则转 `ACTIVE_WAIT` 并恢复同一 lease heartbeat"——可恢复——正确。
- "若到 expiry 仍 missing 则先重新读取 PG+Host、再走 targeted recover"——expiry 后走 targeted recover——正确。
- §10 L531-533 三个命名测试覆盖：
  - `test_valid_lease_missing_host_waits_without_targeted_or_generic_recovery`
  - `test_valid_lease_missing_host_stops_renewal_then_expiry_allows_targeted_recovery`
  - `test_expired_lease_missing_host_alone_allows_targeted_recovery`
- §12 STOP condition L593："missing Host 也绝不能被当前 owner 无限续租"。

**结论**: 闭合。

### 3. scan limit 按 DST 分类前 raw candidate 计数且下限 ceil(lookback/60)+2882

**位置**: §4.1 L174 + §5.2 step 3 L241

**新增文本**（§4.1 L174）：
> "scan limit 的计数单位固定为**croniter 每次产出的 raw naive-local candidate，发生在 ZoneInfo/DST 分类前**，从而同时约束 CPU 与 invalid/nonexistent candidate；下限固定为 `ceil(lookback_seconds / 60) + 2882`，其中 2880 覆盖 Python timezone offset 两端严格小于 24 小时所允许的最坏 naive-local 跨度差，另 2 覆盖 boundary/future candidate。默认 7 日 lookback 的最小值 12962，默认 20000 合法；改变 lookback 导致下限不满足时 settings fail-fast。"

**新增文本**（§5.2 step 3 L241）：
> "每次 croniter 产出 raw naive-local candidate 时先把 scan count 加 1，再做 ZoneInfo round-trip、nonexistent/ambiguous 分类，因此 invalid candidate 同样消耗 limit；只有分类后的有效 UTC cursor 要求严格增加。raw count 不得超过 `schedule_candidate_scan_limit`。"

**验证**：
- 计数单位明确为 raw naive-local candidate，在 DST 分类前——正确。
- invalid/nonexistent candidate 同样消耗 limit——正确。
- 下限公式 `ceil(lookback_seconds / 60) + 2882`：2880 覆盖最坏 naive-local 跨度差，2 覆盖 boundary/future——数学上正确（24h offset 两端 < 48h naive span，2880 = 48*60）。
- 默认 7 日 lookback：`ceil(604800/60) + 2882 = 10080 + 2882 = 12962`；默认 20000 > 12962——合法。
- 改变 lookback 时 fail-fast——正确。
- §10 L457 新增 `test_queue_settings_scan_limit_lower_bound_includes_timezone_offset_margin`——覆盖下限校验。
- §10 L495 新增 `test_candidate_scan_limit_counts_raw_nonexistent_dst_candidates_before_classification`——覆盖 raw 计数语义。

**结论**: 闭合。

---

## Prior Closure Regression Check

逐项扫描 613 行 plan 与 prior closures：

| Area | Prior Status | Regression Check | Result |
| --- | --- | --- | --- |
| MiM M-001 croniter DST | CLOSED | §5.2 empirical gate 保持，§9 Slice A pre-edit gate 保持 | 无回归 |
| MiM M-002 CAS return type | CLOSED | §5.1 ScheduleReserveAction 保持，§5.3 lost_race 零 mutation | 无回归 |
| MiM M-003 worker_id reason | CLOSED | §6.1 security rationale 保持，§10 named test 保持 | 无回归 |
| MiM L-001 INTEGRATION rejection | CLOSED | §4.1/§8 ordinary wrapper rejection 保持 | 无回归 |
| MiM L-002 CLI file scope | CLOSED | §3/§8 per-file constraints 保持 | 无回归 |
| MiM Open Question Protocol | CLOSED | §6.2 runtime-checkable Protocol 保持 | 无回归 |
| Terra S22-001..009 | ALL CLOSED | materializing/snapshot/governance/drain/startup/CI 全保持 | 无回归 |
| Controller 5 收口 | ALL CLOSED | content immutability/replay timestamps/skipped_conflict/fixture/empty registry 全保持 | 无回归 |
| Round-1 closure (lookback C>=L) | CLOSED | §5.2 step 2 C>=L 保持 | 无回归 |
| Round-1 closure (explicit-provider Redis) | CLOSED | §8 L104/L411 Redis admission 强制保持 | 无回归 |
| Round-1 closure (lock order/late re-read) | CLOSED | §6.2 L315 unified lock order 保持 | 无回归 |
| Round-1 closure (PENDING availability) | CLOSED | §6.1 L297 availability gate + §10 3 named tests 保持 | 无回归 |
| Round-1 closure (MATERIALIZING typed decision) | CLOSED | §6.1 L299 enqueue_committed_schedule_occurrence 保持 | 无回归 |

---

## Blocking-Only New Finding Scan

扫描 613 行 plan 全文，仅检查 blocking（H/M/L）新 finding：

- **Schema/DLL**: §5.3 DDL exact CHECK、FK/RLS/grants/downgrade 完整。无 open。
- **State machine**: §7.3 Worker 7 状态 + §7.4 Scheduler 4 状态 + §6.2 Governance 9 action + §5.1 12 DTO/8 enum 全闭合。无 open。
- **Lock ordering**: §6.2 L315 8 个入口统一锁序 + generic recover READ COMMITTED 双 statement。无 open。
- **Concurrency**: §5.3 concurrent enqueue conflict re-read、§7.4 concurrent materializing replay、§6.2 reserve racing finalize。无 open。
- **Startup**: §8 two wrapper → one private root + typed admission + Redis-first。无 open。
- **Drain**: §7.5 two-signal + drain_abandon_requested + WAITING_FOR_INNER_WORK + os._exit(1)。无 open。
- **CI**: §10 五条独立 pytest + workflow ignore + PG16/Redis digest。无 open。
- **Tests**: 88 个命名测试覆盖 config/schedule/worker/Redis/CLI。无 open。
- **STOP conditions**: §12 16 条 STOP 与 plan 全文对齐。无 open。
- **Residual**: §13 7 项 residual 合理。无 open。

**未发现新 H/M/L finding。**
