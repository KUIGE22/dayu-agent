# Corrective Plan Re-review — Slice 2.2 Scheduler / Worker / Redis

## Scope

- **Mode**: corrective plan re-review（仅复核 MiM M-001..003/L-001..002 + Terra 9 项 + Controller 收口 + 新 finding 扫描）
- **Target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`（REVIEW FIX APPLIED 版）
- **Baseline**: `38ddad4`（Slice 2.1 accepted commit）
- **Output file**: `docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-mim.md`
- **Review sources**: MiM original `plan-review-20260812-slice-2.2-scheduler-worker-redis-mim.md`、Controller fix `plan-fix-20260812-slice-2.2-scheduler-worker-redis-codex.md`、updated plan
- **Excluded**: 不修改 production/tests/README/dependency/CI/plan；不运行长测试/live/model/broker

## Conclusion

**PASS / open H/M/L = 0/0/0**

MiM 原五项 finding 全部 CLOSED；Terra 九项（含 Controller 三项收口）全部 CLOSED/ACCEPTED-IN-PLAN。Plan 从初版 439 行扩展至 572 行，新增 materializing state、frozen snapshot、correlated heartbeat precedence、two-signal drain、private composition root、empirical croniter gate、candidate scan limit 等关键设计。未发现新 finding。

---

## MiM Finding Closure

### M-001 — CLOSED

**原 finding**: DST/misfire 算法对 croniter 行为的假设需要 empirical 验证。

**修订验证**: plan §5.2 新增 "实施前先在 pinned croniter 上运行 pure empirical gate，固定 America/New_York spring-gap 02:30、fall-fold 01:30 与 Asia/Shanghai 无 DST 样本"；§9 Slice A 明确 "在任何 production scheduler 编辑前先运行 pinned croniter naive New York spring/fall + Shanghai empirical gate；不满足 §5.2 即 STOP/plan-fix"。§10 新增命名测试 `test_croniter_naive_candidate_empirical_gate_is_exact_for_new_york_and_shanghai`。

**结论**: 与 Terra-S22-002 同簇。croniter 行为不再被隐式假设，而是被显式 empirical gate 验证。CLOSED。

### M-002 — CLOSED

**原 finding**: `reserve_occurrence` CAS conflict 的返回类型未指定。

**修订验证**: plan §5.1 新增 `ScheduleReserveAction: reserved, lost_race` 与 `ScheduleReservationBatch`/`ScheduleReservationResult` DTO。§5.3 明确 "state/version/cursor 已变化返回 `ScheduleReservationResult(lost_race, ())` 且零 mutation，不抛裸 IntegrityError"。§10 新增 `test_mark_enqueued_skipped_conflict_is_closed_and_stops_scheduler`。

**结论**: 与 Terra-S22-001 同簇。CAS conflict 有明确 closed return type。CLOSED。

### M-003 — CLOSED

**原 finding**: Execution request 排除 worker_id 缺少明确安全理由。

**修订验证**: plan §6.1 新增 "worker identity 只属于 PG attempt 审计、process 日志与 metrics；禁止业务 handler 按短生命周期 worker 身份分支 side effect 或构造幂等键，因此不进入 execution request。测试必须反射/typed fake 双重证明 lease/fence/raw token/worker_id 均不可见。" §10 `test_execution_handler_never_receives_lease_fence_raw_token_or_worker_id` 保持。

**结论**: 安全理由明确。CLOSED。

### L-001 — CLOSED

**原 finding**: INTEGRATION profile 的 ordinary startup 拒绝机制未指定精确实现路径。

**修订验证**: plan §4.1 明确 "load_platform_settings 接受并严格验证该 profile；普通 prepare_host_runtime_dependencies 在任何路径/Redis/PG/S3/Host/workspace 副作用前拒绝，只有 platform worker|scheduler 专用 preparation 可接收"。§8 细化为两个 public wrapper 共用一个 private composition root，ordinary wrapper 在 `load/validate settings` 阶段即拒绝 INTEGRATION。§10 新增 `test_integration_profile_requires_only_postgres_and_rejects_redis_object_and_auth_env` 与 `test_ordinary_startup_rejects_integration_before_any_side_effect`。

**结论**: 与 MiMo M-001 重叠。拒绝路径精确到 ordinary wrapper 的 settings validation 阶段。CLOSED。

### L-002 — CLOSED

**原 finding**: CLI 共享文件修改范围未指定。

**修订验证**: plan §3 CLI owner 明确 "arg_parsing.py 只增加 platform nested subparser 注册；arguments.py 只增加 typed fields；command_names.py 只增加轻量命令集合/`__all__`；main.py 只增加 lazy import/dispatch。所有 runtime/admission/signal/exit/cleanup 在 commands/platform.py"。§8 同步。

**结论**: 每个共享文件的修改范围精确到 mechanical-only。CLOSED。

### Open Question — CLOSED

**原 question**: `HostRunCancellationProtocol` 的实现形式。

**修订验证**: plan §6.2 明确 "JobService 在本模块定义并注入 `@runtime_checkable HostRunCancellationProtocol.cancel_run(run_id) -> RunRecord`；既有 Host 以结构类型同时满足 reader/canceller"。Controller fix §3 确认 "HostRunCancellationProtocol 明确在 job_service.py 新增为 runtime-checkable 结构协议"。

**结论**: Protocol 定义位置、形式和注入方式全部明确。CLOSED。

---

## Terra Finding Closure

### TERRA-S22-001 — CLOSED

occurrence 从 pending 直接 enqueue 改为 `pending -> materializing -> enqueued`。materializing 是 durable commitment，不是进程锁。immutable snapshot + atomic job idempotency 使任意并发 replay 安全收敛。disable 与 begin 按 schedule→occurrence 同一锁序线性化。§10 新增 10+ 个 named tests 覆盖 crash/replay/disable race/concurrent enqueue。

### TERRA-S22-002 — CLOSED

新增 misfire_expired/lookback_exceeded/candidate_scan_limit_exceeded closed reasons；grace 等号边界、lookback 跳转 audit、最多三项 reservation batch、exact count/None 语义、strict UTC cursor、candidate scan limit、activate/re-enable 首个 future fire 均明确。

### TERRA-S22-003 — CLOSED

新增覆盖有效 lease 的 `list_governable_agent_runs`；projection 拆分 `job_cancel_requested_at` 与 Host cancel intent；correlated heartbeat 在 deadline/cancel 时续 lease 并返回 governance-required，不再走 generic terminalization。

### TERRA-S22-004 — CLOSED

每个 handler/heartbeat/PG/Redis future 唯一 owner、同类至多一个 in-flight、有界 PubSub wait、outer cancel 不代表 inner cancel、close 前真实 reap。首信号 grace 只承诺 cooperative drain；非协作 inner work 继续 heartbeat/保留 runtime，第二信号才 hard-stop 且不写假 terminal。

### TERRA-S22-005 — CLOSED

五个 integration 文件逐个独立 pytest process 与独立 session cluster/container；workflow aggregate 命令必须逐一 `--ignore`；真实 exit 不得由 `-k`、order、skip 或 masked shell status 替代。

### TERRA-S22-006 — CLOSED

0004 明确 organizations FK、schedule/job composite tenant FK、ON DELETE RESTRICT、state/snapshot/job/skip exact CHECK、RLS、最小列级 UPDATE、无 DELETE 及真实 cross-tenant/invalid-state 写入测试。

### TERRA-S22-007 — CLOSED

startup 固定 `_PreparedQueueAdmission`、`PreparedPlatformQueueRuntime`、`_prepare_queue_admission`、`_prepare_host_runtime_after_queue_admission` 及一个 platform public wrapper。ordinary/platform wrapper 共用同一 private root；无 callback/bool bypass、无 special→ordinary 二次调用。

### TERRA-S22-008 — CLOSED

从 allowlist/交付/验证删除 ignored 且 untracked 的 `uv.lock`。唯一安装真源为 `pyproject.toml` 窗口和 tracked pip constraints。

### TERRA-S22-009 — CLOSED (DEFERRED AUTH OWNER)

canonical tenant selector 不是认证。target/master/handoff 声明外部已授权 operator/process-manager 与 credential 分发是启动前置条件；不能证明则 STOP。service account、tenant roster、RBAC 归 Slice 7.1/8.2。

---

## Controller 收口 Closure

1. **Schedule content immutability**: §5.1 ScheduleRegistrationRequest 明确 "descriptor/payload/cron/timezone/policy/grace/deadline 注册后不可原地修改；改变内容必须新建不同 schedule_key"。CLOSED。
2. **Replay exact timestamps**: §5.1 CanonicalScheduleEnqueueSnapshot 明确 "available_at = occurrence.scheduled_for, deadline_at = occurrence.scheduled_for + schedule.job_deadline_seconds"；§5.2 "crash replay 必须重建 byte-identical JobEnqueueRequest, 不得重新读取 current time 或可变 schedule 内容"。CLOSED。
3. **skipped_conflict invariant**: §5.3 "SKIPPED 返回 skipped_conflict 且 scheduler 必须以 runtime invariant 停止，不能静默继续"；§7.4 "skipped_conflict 表示实现/数据库不变量已破坏，scheduler 固定 nonzero 停止并保留现场"。CLOSED。
4. **Redis image fixture**: §10 "本地缺固定 image 必须 STOP 并给出显式 pull 命令，不能把 skip 计作 PASS；fixture 不 implicit pull"。CLOSED。
5. **Production execution registry empty**: §8 "execution registry 为空"；§6.1 "Slice 2.2 production registry 精确为空"。CLOSED。

---

## New Finding Scan

逐项检查 plan 572 行 + Controller fix 108 行，未发现新 H/M/L finding：

- **Closed DTO**: §5.1 列出 12 个 frozen DTO + 8 个 closed enum/error，每个都有精确字段定义。无 open。
- **Exact owners**: §3 逐文件 owner 表 + dependency DAG 完整。CLI 共享文件修改范围在 §3/§8 双重锁定。无 open。
- **Startup call graph**: §8 两个 public wrapper → 一个 private root 的结构在 Controller fix 中固定。Redis admission 在 path/S3/PG/Host/workspace 之前。无 open。
- **Materializing replay**: §5.3 `begin_materialization`/`list_replayable`/`mark_enqueued` 三步状态机在 §7.4 Scheduler occurrence 中完整描述。snapshot freeze 在 §5.1 CanonicalScheduleEnqueueSnapshot 中明确。无 open。
- **Misfire**: §5.2 算法 6 步 + empirical gate + candidate scan limit + 具体 skip reasons 闭合。无 open。
- **Correlated heartbeat**: §6.2 新增 correlated 分支，heartbeat 在 deadline/cancel 时续 lease 返回 governance-required，不走 generic terminalization。§10 有 `test_correlated_deadline_does_not_follow_generic_heartbeat_terminalization`。无 open。
- **Drain**: §7.5 two-signal model 明确：首信号 cooperative drain + WAITING_FOR_INNER_WORK；第二信号 hard-stop。§10 有 5 个 drain 命名测试。无 open。
- **CI lanes**: §11 门禁 5 固定五条独立命令 + workflow ignore 合同。无 open。
- **DAG/layering**: §3 DAG 与 §12 STOP conditions 对齐。Storage 不 import Host/Service/Redis；Host 不 import concrete PG store。无 open。
- **Type safety**: plan 禁止 `Any`/`object`/`cast`/`type: ignore`/`getattr`/`hasattr`。§11 门禁 2 pyright 0 errors。无 open。
- **Docstrings**: §11 门禁 4 要求完整中文 Args/Returns/Raises。无 open。
