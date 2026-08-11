# Slice 2.2 Scheduler / Worker / Redis — MiMo Corrective Plan Re-Review

- **Status**: PASS / open H/M/L=0/0/0
- **Reviewer**: MiMo (corrective re-review)
- **Target plan**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`（REVIEW FIX APPLIED）
- **Baseline**: `38ddad4`
- **Method**: 全量审读更新后 plan + Controller plan-fix + 原 MiMo review + AGENTS.md + baseline code

## 0. Verdict

**PASS.** 原 4M+2L 全部 CLOSED；新增 materializing 状态机、frozen snapshot、candidate scan limit、五独立 integration process、inner-future ownership 等修订正确闭合所有攻击面，无新增 finding。

## 1. 原 Finding Closure

- **M-001 (Integration profile)**: CLOSED. §6.5 明确 "必须且只允许PostgreSQL DSN；object storage、Redis、auth任一非空都fail-fast，绝不静默忽略"。§6.5 同时明确 ordinary startup 在任何 side effect 前拒绝 INTEGRATION。
- **M-002 (skip_reason enum)**: CLOSED. §5.1 新增 `ScheduleSkipReason` 精确 4 值：`misfire_expired/lookback_exceeded/schedule_disabled/candidate_scan_limit_exceeded`。coalesced 只由 count 表示。
- **M-003 (Redis-first startup)**: CLOSED. §6.7/§8 固定 `_prepare_queue_admission` → `_prepare_host_runtime_after_queue_admission`，两个 public wrapper 共用一个 typed private composition root，无 callback/bool bypass。
- **M-004 (Redis client/server)**: CLOSED. §4.2 明确 "固定client 8.1.x + server 8.4组合只使用向后兼容RESP2"，不兼容时 "立即STOP并plan-fix/re-review，不得静默改client窗口或digest"。
- **L-001 (heartbeat no-jitter)**: CLOSED AS RESIDUAL. §7.3 补充 "不加jitter是为了保持lease安全上界可证明"，§13 记录 "同相多worker可能形成PG瞬时峰值，部署方应错开启动"。
- **L-002 (disable/materializing race)**: CLOSED. §7.4 明确 "disable与begin都按schedule->occurrence锁序线性化；disable先赢则pending->skipped，begin先赢则materializing成为不可撤销入队承诺"。§5.3 `set_state(disabled)` 只改 PENDING。

## 2. 新攻击面验证

### 2.1 Materializing 状态机正确性

- `PENDING → MATERIALIZING`：`begin_materialization` 原子转换，返回 `enqueue`。
- `MATERIALIZING 重放`：同 snapshot 返回 `enqueue`，使用同 idempotency key 复用同一 PG job。
- `MATERIALIZING → ENQUEUED`：`mark_enqueued` 绑定 job_run_id。
- `MATERIALIZING → SKIPPED`：**不可能**。disable 只改 PENDING，schedule row lock 保证线性化。
- `skipped_conflict`：仅当 invariant 已破坏时出现，scheduler 必须 nonzero 停止。**正确。**

### 2.2 Frozen Snapshot Immutable Replay

- §5.1 `CanonicalScheduleEnqueueSnapshot` 冻结 descriptor 七字段 + payload + idempotency_key + available_at/deadline_at。
- `available_at = occurrence.scheduled_for`，`deadline_at = scheduled_for + job_deadline_seconds`。
- replay 重建 byte-identical `JobEnqueueRequest`，不读当前时钟。
- `request_fingerprint` 逐字段覆盖与 `PostgresJobStore.enqueue` 相同的 identity。
- **正确。** crash replay 必须产生相同 fingerprint 才能复用同一 job。

### 2.3 Correlated Deadline Governance

- §6.2 `list_governable_agent_runs` 覆盖 lease 有效 + 过期的全部未终结 correlation。
- correlated heartbeat 遇 deadline 续 lease + 返回 governance-required，不走 generic terminalization。
- Host cancel 只走 `cancel_run`（写 intent），不走 `cancel_run_and_settle`。
- `job_cancel_requested_at`（PG）与 Host `cancel_requested_at` 分离，不混用。
- **正确。** generic 无 correlation deadline 保持 Slice 2.1 语义不变。

### 2.4 Shutdown / Inner-Future Ownership

- §7.5 首信号 cooperative grace：停止 intake，handler/heartbeat/inner future 在 grace 内收敛。
- grace 到期：请求 handler cancellation 但继续 heartbeat 直到 inner future 真实结束。
- 第二信号：hard stop，不写假 terminal，lease expiry/recovery 接管。
- §7.3 每个 sync store/Redis 调用有唯一 async owner，同类至多一个 in-flight，outer cancel 不等于 inner cancel。
- **正确。** 不同时承诺 "首信号硬时限" 与 "非协作 handler 零 late side effect"。

### 2.5 CI Isolation

- §10 五个 integration 文件逐个独立 pytest process，独立 session PG16 cluster/container。
- workflow aggregate 以五个 `--ignore=<exact path>` 排除。
- `test_platform_migrations.py` 是无 PG 静态 DDL gate，不伪装 integration。
- **正确。** 与 Slice 2.1 accepted PG16 lane isolation 规则一致。

### 2.6 Concurrent Enqueue Idempotency

- §5.3/§6.1 `PostgresJobStore.enqueue` 使用数据库原子 `INSERT ... ON CONFLICT DO NOTHING` + conflict re-read。
- 同 fingerprint 返回同一 `JobEnqueueReceipt(idempotency_reused=True)`。
- 不同 fingerprint 返回 closed `JobIdempotencyConflictError`。
- 不泄漏裸 `IntegrityError`。
- **正确。** 与 Slice 2.1 的 enqueue idempotency 对齐。

## 3. Named Test Completeness

Plan §10 含 70+ 命名测试，覆盖：
- Config/profile/queue settings（6 tests）
- Schedule domain/PG（21 tests，含 DST/misfire/crash/disable race/concurrent replay）
- Worker/execution/governance（18 tests，含 heartbeat/inner-future/signal drain）
- Redis/CLI/real process（13 tests，含 disconnect/restart/RESP2 interop/subprocess signal）

新增关键测试：
- `test_materialization_replay_builds_byte_identical_enqueue_request`
- `test_disable_before_materialization_linearization_skips_without_job`
- `test_concurrent_pending_replay_reuses_one_job_and_marks_one_occurrence`
- `test_mark_enqueued_skipped_conflict_is_closed_and_stops_scheduler`
- `test_worker_grace_expiry_with_noncooperative_handler_keeps_lease_and_no_false_terminal`
- `test_worker_second_signal_hard_stops_without_false_terminal_then_lease_recovers`

## 4. Residual Risks (Non-Blocking)

1. heartbeat 无 jitter 同相峰值 — plan 已文档化，部署方错开启动。
2. 非协作 handler grace 后仍运行 — 第二信号 hard stop，lease recovery 接管。
3. Redis hint 天然可丢 — PG poll 兜底，延迟 ≤ poll_interval_seconds。

## 5. Final Verdict

**PASS / open H/M/L=0/0/0.** 全部原 finding CLOSED，无新增缺陷。Plan 可进入 accepted baseline commit。
