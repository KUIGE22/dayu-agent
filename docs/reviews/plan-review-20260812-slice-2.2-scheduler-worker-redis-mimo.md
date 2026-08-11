# Slice 2.2 Scheduler / Worker / Redis — MiMo Adversarial Plan Review

- **Status**: FAIL / open H/M/L=0/4/2
- **Reviewer**: MiMo (adversarial, independent of MiM and Terra)
- **Target plan**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **Baseline**: `38ddad4` (Slice 2.1 accepted commit)
- **Method**: 全量审读 plan + handoff + AGENTS.md + baseline code（config/startup/host/composition/protocols/CLI/CI/constraints）

## 0. Verdict

**FAIL.** 4 Medium + 2 Low open findings。Plan 整体架构设计扎实，七个 Controller blocking contract 已闭合关键缺口，但存在 integration profile 安全边界、skip_reason 枚举缺失、startup call graph Redis-first 可实现性、以及 Redis client/server 版本对齐等需修复项。

## 1. M-001 — Integration profile 安全边界未约束 production env 共存

**Severity**: Medium
**Location**: §4.1, §6.5

Plan 定义 `PlatformDeploymentProfile.INTEGRATION`："必须配置 PostgreSQL DSN 环境变量、禁止 object storage/Redis/auth 环境变量"。但 §6.5 又说 "production 缺 Redis package/URL 或首次 ping 失败必须在 PG engine/Host/Fins/workspace 创建前 fail-fast"。

**Gap**: 如果 operator 在 integration profile 下同时设置了 `DAYU_PLATFORM_REDIS_URL`，plan 未明确是否应 reject。当前 `PlatformSettings.validate()` 只处理 DEVELOPMENT/PRODUCTION 两个 profile（`config.py:34-39`）。新增 INTEGRATION 需要自己的 validation path，但如果该 path 不显式拒斥 Redis env，operator 可能误以为 Redis 已被使用而实际被忽略。

**Fix**: §4.1 或 §6.5 必须明确：integration profile 下 Redis env 非空时 fail-fast（与 development 禁止 production infra 的契约对齐），或显式记录为 ignored 且 startup snapshot 标记。

## 2. M-002 — ScheduleOccurrenceReservation.skip_reason 缺 closed 枚举

**Severity**: Medium
**Location**: §5.1 DTO 表

Plan 说 skip_reason "仅固定 closed 值或 None"，但未列出精确枚举值。从 §5.2 算法可推断至少有 `lookback_exceeded`、`schedule_disabled`（§7.4）、`misfire_grace_exceeded`、`coalesced`；但这些值散落在不同段落，未像 `ScheduleState`/`ScheduleOccurrenceState` 那样定义 closed enum。

**Risk**: 实现者可能自行发明 skip reason 字符串，或遗漏某个值导致 occurrence 无法被审计分类。§5.3 occurrence 表有 `closed skip reason` CHECK 约束，需要精确值列表。

**Fix**: §5.1 新增 `ScheduleSkipReason` closed enum，精确列出所有合法值，与 §5.2/§7.4 算法一一对应。

## 3. M-003 — Redis-first startup admission 在现有 call graph 中的可实现性

**Severity**: Medium
**Location**: §6.7, §8, startup_preparation.py

Plan §6.7 要求 "Redis import/client/ping admission 必须早于 `_read_postgres_dsn`、engine、S3、Host 路径创建和 workspace 写"。但当前 `startup_preparation.py` 的 `_build_production_services_provider`（line 381-416）在 Host 构造后才装配 JobService；`_default_provider_or_fail`（line 468+）在 production 路径调用 `_prepare_production_platform_dependencies`（读 DSN → 创建 engine → probe）。

**Gap**: Plan §8 说 "仅实际需要时改 startup/platform；不得建立第二 composition root"，但未提供具体的 call graph 修改点。Worker/scheduler CLI 需要在调用现有 `build_prepared_host_runtime`（或等价入口）之前完成 Redis admission。如果该入口内部先读 DSN、创建 engine，Redis admission 就不是 truly first。

**Fix**: Plan §8 应明确：(a) worker/scheduler CLI 使用独立 preparation path（如 `_prepare_queue_runtime`）在调用现有 startup 前完成 Redis admission，或 (b) 现有 startup 入口接受可选的 pre-admission callback。Option (a) 更安全但需要更多新代码；Option (b) 更轻量但侵入现有 call graph。Plan 必须选一并描述具体修改点。

## 4. M-004 — Redis client 8.1.x 与 server 8.4.0 的版本对齐声明

**Severity**: Medium
**Location**: §4.2

Plan 固定 `redis>=8.1.0,<8.2.0`（client）与 `redis:8.4.0-bookworm`（server image）。redis-py 8.1.x 支持 RESP2/RESP3，Redis server 8.4 是当前最新。虽然 RESP 协议向后兼容，但 redis-py 8.1.x 的 release notes 未声明对 Redis 8.4 server 的官方验证。

**Risk**: 如果 redis-py 8.1.x 与 Redis 8.4 存在未文档化的协议不兼容（如新的 server push 消息类型干扰 PubSub），integration tests 可能因版本组合失败而需紧急调整。

**Fix**: §4.2 应记录选择依据（如 "redis-py 8.1.x 通过 RESP2 protocol=2 连接 Redis 8.4，忽略 RESP3 特性"），并明确若 integration test 发现不兼容时的 fallback 策略（升级 client 上界或降级 server digest）。

## 5. L-001 — heartbeat interval 无 jitter 的 thundering herd 风险

**Severity**: Low
**Location**: §7.3

Plan 固定 heartbeat interval = `min(poll_interval_seconds, lease_duration_seconds / 3)` 且 "不加 jitter"。一进程一 tenant 模型下，同一 tenant 只有一个 worker，故同一时刻不会有多个 heartbeat。但如果 operator 为同一 tenant 启动多个 worker（违反 plan 但无 enforced guard），或多个 tenant 的 heartbeat 恰好同步，会产生 PG 连接峰值。

**Risk**: Low——plan 明确 "一个 worker process 同时最多处理一个 attempt"，且 §13 说 "一进程一tenant是当前明确的安全收缩"。Thundering herd 只在 operator 误配置时出现。

**Fix**: 可接受为 residual。建议 §7.3 补充一句 "不加 jitter 是因为一进程一 tenant 保证同一时刻最多一个 heartbeat；多 tenant 部署由进程管理器错开启动时间"。

## 6. L-002 — Scheduler pending replay 与 disable 事务的竞态窗口

**Severity**: Low
**Location**: §7.4

Plan §7.4 说 "disable transaction 同时把尚未 enqueue 的 pending occurrence 标为 skipped `schedule_disabled`"。但 §7.4 又说 "每 tick 顺序：replay pending（最老优先）-> list due -> reserve -> materialize -> wait"。

**Gap**: 如果 scheduler A 正在 replay pending（已读取但未 mark），同时 scheduler B disable 了该 schedule 并把 pending 标为 skipped，scheduler A 的 `mark_enqueued` 会尝试 mark 一个已被 skipped 的 occurrence。Plan 未明确 `mark_enqueued` 对 skipped occurrence 的行为。

**Fix**: §5.3 `mark_enqueued` 应明确：若 occurrence 已被标记为 `skipped`，`mark_enqueued` 返回 closed conflict（不抛异常、不改状态），scheduler 跳过该 occurrence 继续。或 `reserve_occurrence` 的 FOR UPDATE 锁已覆盖此窗口（disable 事务也要锁 schedule row）。Plan 应明确锁粒度。

## 7. Closed Observations (Non-Blocking)

1. **Occurrence outbox crash windows**: Plan §6.1 的 cursor+pending 同事务 → enqueue → mark 三步正确闭合两个窗口。Window 1（cursor commit 后 enqueue 前崩溃）：pending occurrence 可重放。Window 2（enqueue 后 mark 前崩溃）：同一 idempotency key 复用同一 PG job。Redis hint 在 commit 后发送，不影响 PG truth。**Closed.**
2. **croniter DST**: §5.2 的 nonexistent-skip + ambiguous-fold=0 + round-trip 规则是业界标准做法。croniter 的 `croniter.get_next()` 返回 naive datetime，实现者需自行用 ZoneInfo 做 UTC round-trip。Plan 已明确此要求。**Closed.**
3. **Execution request 不含 lease/token**: §6.1 明确 `JobExecutionRequest` 不含 `JobLeaseHandle`、fence、raw token 或 worker id。Worker 不得调用 handler 方法绕开 Service。**Closed.**
4. **Agent governance PG projection**: §6.2 使用 PG join projection 计算 deadline_reached，不依赖 worker wall clock。Host cancel 只走 `cancel_run`（`host.py:839`），不走 `cancel_run_and_settle`（`host.py:863`）。**Closed.**
5. **Grace drain 不写假 terminal**: §7.5 grace 超时 "不调用 fail/complete/cancel_run、不改 PG terminal，等待 lease expiry/recovery"。正确。**Closed.**

## 8. Required Fix Scope

Plan-only 修改（不涉及 production/tests）：
- §4.1: integration profile 对 Redis env 的显式拒斥或 ignored 声明
- §5.1: 新增 `ScheduleSkipReason` closed enum
- §8: Redis-first admission 的具体 call graph 修改点选择
- §4.2: Redis client/server 版本对齐声明
- §7.3: heartbeat no-jitter 的设计理由补充（可选）
- §5.3: `mark_enqueued` 对 skipped occurrence 的行为 + disable 事务锁粒度

## 9. Final Verdict

**FAIL / open H/M/L=0/4/2.** M-001 至 M-004 需 Controller 裁决或 plan fix 后方可 implementation；L-001/L-002 可接受为 residual 或在 fix 中顺带澄清。
