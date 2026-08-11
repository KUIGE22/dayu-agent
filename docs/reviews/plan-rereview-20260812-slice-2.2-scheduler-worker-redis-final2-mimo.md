# Slice 2.2 Scheduler / Worker / Redis — MiMo Final Round-2 Closure Plan Re-Review

- **Status**: PASS / open H/M/L=0/0/0
- **Reviewer**: MiMo (final round-2 closure)
- **Target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md` (SHA256 `1b4f467...e89829`)
- **Prior**: `plan-rereview-...-final-mimo.md`（PASS/0）
- **Scope**: 三项新增 + prior closure 回归扫描 + blocking-only 新 finding 扫描

## 0. Verdict

**PASS.** 三项新增全部正确闭合，prior closure 无回归，无 blocking 新 finding。

## 1. Generic Recover 纳入统一锁序 + READ COMMITTED 双 Statement Late Re-Read

§6.2 line 315："精确覆盖...generic `recover(scope)`、`recover_agent_run_after_no_host`与`reconcile_agent_run_terminal`"。

§6.2 明确 READ COMMITTED 语义："generic recover即使候选SQL含`NOT EXISTS correlation`也只能把它当无锁候选过滤：必须在同一READ COMMITTED事务中先用第一条statement取得父行锁，再用**第二条独立statement**取得刷新后的statement snapshot并late lock/re-read correlation，不能把候选、锁父行、NOT EXISTS复核和terminal UPDATE压成一个旧snapshot statement；有任一已提交correlation即跳过且零mutation"。

**正确性论证**：READ COMMITTED 中每个 statement 看到该 statement 开始时已提交的快照。单 statement 路径中 NOT EXISTS 用旧 snapshot，锁父行后 correlation 可能已被另一事务 commit，但 UPDATE 仍用旧 snapshot 判定 NOT EXISTS=true → 错误 terminalize。双 statement 路径中第二条 statement 刷新 snapshot，看到已提交 correlation → skip + 零 mutation。

**证据**: `test_generic_recover_racing_correlation_reservation_late_rechecks_and_skips`（§10 line 523）。STOP conditions（line 593）未列此项为 STOP，因为它已正确闭合在 §6.2 中。

## 2. Valid-Lease Missing Host：MISSING_HOST_WAIT 停止续租 + Persisted Expiry 收敛

§6.2 line 309："Host missing但lease仍有效返回`MISSING_HOST_WAIT`：零recover、零新attempt，Worker按reobserve interval继续读取同一reserved id，但从第一次missing observation起**停止该attempt后续heartbeat/续租**并保留PG中已提交的`lease_expires_at`作为唯一等待上界；Host若在expiry前出现则转`ACTIVE_WAIT`并恢复同一lease heartbeat，若到expiry仍missing则先重新读取PG+Host、再走targeted recover"。

§6.2 line 313："Host missing时进入`MISSING_HOST_WAIT`子态并按上段停止续租、等待persisted expiry/targeted recovery"。

§7.3 line 347："Host missing -> MISSING_HOST_WAIT + stop renewal until persisted expiry/recovery"。

**正确性论证**：停止续租防止 owner 无限续租 missing Host 的 lease（§12 STOP："missing Host也绝不能被当前owner无限续租"）。persisted `lease_expires_at` 是 PG 权威上界，不依赖 worker wall clock。Host 在 expiry 前出现 → 恢复 ACTIVE_WAIT + heartbeat；expiry 仍 missing → PG+Host re-read → targeted recover。无无限等待、无伪造 terminal。

**证据**: `test_valid_lease_missing_host_waits_without_targeted_or_generic_recovery`（line 531）；`test_expired_lease_missing_host_alone_allows_targeted_recovery`（line 532）。

## 3. Scan Limit：DST 分类前 Raw Candidate 计数 + 下限 ceil(lookback/60)+2882

§4.1 line 174："scan limit的计数单位固定为**croniter每次产出的raw naive-local candidate，发生在ZoneInfo/DST分类前**，从而同时约束CPU与invalid/nonexistent candidate；下限固定为`ceil(lookback_seconds / 60) + 2882`，其中2880覆盖Python timezone offset两端严格小于24小时所允许的最坏naive-local跨度差，另2覆盖boundary/future candidate。默认7日lookback的最小值12962，默认20000合法；改变lookback导致下限不满足时settings fail-fast"。

§5.2 step 3 line 241："每次croniter产出raw naive-local candidate时先把scan count加1，再做ZoneInfo round-trip、nonexistent/ambiguous分类，因此invalid candidate同样消耗limit；只有分类后的有效UTC cursor要求严格增加"。

**下限验证**：7日 = 604800s。`ceil(604800/60) + 2882 = 10080 + 2882 = 12962`。Plan 声明 "默认7日lookback的最小值12962" ✓。2880 = 24h × 60min × 2（offset 两端），+2 = boundary + future。默认 20000 > 12962 ✓。

**正确性论证**：nonexistent local time（DST gap）不产生有效 UTC candidate 但仍消耗 scan count → 防止 croniter 在 gap 中无限循环。raw count 在 DST 分类前递增 → CPU 开销有确定上界。下限保证 worst-case timezone offset 不会因 limit 过低而无法找到 future candidate。

**证据**: `test_queue_settings_scan_limit_lower_bound_includes_timezone_offset_margin`（line 457）；`test_candidate_scan_limit_counts_raw_nonexistent_dst_candidates_before_classification`（line 495）。

## 4. Prior Closure 回归扫描

全部 6 原 finding（M-001..M-004, L-001..L-002）+ 3 residual 不变。materializing 状态机、frozen snapshot、五独立 integration process、inner-future ownership、drain_abandon、typed `ScheduleMaterializationDecision`、PENDING availability gate、correlation 统一锁序、heartbeat `governance_required`、`complete`/`fail` 遇 correlation 抛 `JobGovernanceRequiredError`、cursor 分页防饿死——全部仍在最新 target 中正确存在。

## 5. Blocking 新 Finding 扫描

无 blocking 新 finding。三项新增均有精确 plan 文本、正确性论证和 named test 覆盖。

## 6. Final Verdict

**PASS / open H/M/L=0/0/0.** Plan 可进入 accepted baseline commit。
