# Final Round-3 Closure Plan Re-review — Slice 2.2 Scheduler / Worker / Redis

## Scope

- **Mode**: final round-3 closure-only re-review
- **Target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`（707 行最终版）
- **Target SHA256**: `d71eced3e4e58f6e3ffa875a2699a425a700b7ba2552267072c10ed7113eaa87`（verified）
- **Controller fix**: `docs/reviews/plan-fix-20260812-slice-2.2-scheduler-worker-redis-codex.md`（128 行）
- **Controller fix SHA256**: `b913591e8b4f3fcec13e8bedd382036f6fb2fe25f1d751c5465b22c3d4b0cab9`（verified）
- **Baseline**: `38ddad4`
- **Output file**: `docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-final3-mim.md`
- **Excluded**: 不修改任何文件；不运行长测试/live/model/broker

## Conclusion

**PASS / open H/M/L = 0/0/0**

四项指定验证区域全部闭合，此前所有 closure 无回归，未发现 blocking 新 finding。Plan 707 行，Controller fix 25 项收口全部 accepted。

---

## 区域验证

### 1. Intake Gate（§7.5 L449-453 + §10 L625-627 + §12 L689-690）

**核心设计**：
- `ProcessIntakeGate` + frozen `IntakeEpoch(value)`：`capture()` / `request_stop()` / `is_current(epoch)` / `is_open`
- 第一次 signal 调用 `request_stop`：RUNNING epoch 递增一次并永久关闭 gate；重复 soft signal 不重新开放
- 每个可能返回新 work 的 `asyncio.to_thread`/`await` 在**派发前 capture**，返回后且在启动 handler/heartbeat/claim/materialization 前必须同时验证 `is_open` 与 `is_current(captured)`

**Gate 语义**：
- "gate 前已发出但 gate 后才返回的 PG claim **不得启动 handler 或 heartbeat**、不得写 complete/fail/假 terminal"——正确
- "gate 后才返回的 replay/list/reservation **不得启动 materialize_occurrence**"——正确
- "只有 gate 关闭前已经派发的一个 Service-owned `materialize_occurrence` 算'当前 occurrence'，它即使在 gate 后返回也必须完成整个 begin/enqueue/mark 收口，返回后不得开始下一项"——正确

**Owner & allowlist**：§3 L124 `dayu/host/process_intake.py`（新）、`tests/application/test_platform_process_intake.py`（新）

**命名测试**（§10 L625-627）：
- `test_claim_returning_after_drain_gate_never_starts_handler_or_heartbeat`
- `test_scheduler_replay_or_reserve_returning_after_drain_gate_starts_no_materialization`
- `test_materialization_admitted_before_drain_gate_only_finishes_current_occurrence`

**STOP condition**（§12 L689-690）：
- "首信号关闭 intake gate 后，先前发出的 claim/list/reserve 返回仍可启动 handler、heartbeat 或新 materialization；或把已派发 materialization 中途拆断形成新崩溃窗口"

**结论**: 闭合。gate 的 epoch-based 线性化点精确、allowlist 明确、测试覆盖三个关键窗口。

### 2. Redis Runtime/Settings（§7.2 L400-412 + §4.1 L180 + §12 L691）

**核心设计**：
- `PlatformQueueMode`（deployment config）与 `RedisRuntimeState`（Worker-owned mutable state）分离
- `RedisRuntimeState = {event_assisted, polling_degraded}` 只由 REDIS admission 构造
- POSTGRES_ONLY：`redis_runtime_state=None`、publisher/subscriber/client 全 None、永不 construct/ping/subscribe/resubscribe/health-recover Redis
- 转换条件从 settings 读取：`consecutive_failures >= settings.redis_failure_threshold`（默认 3）、`settings.redis_health_interval_seconds`（默认 30）到期后 ping+resubscribe 成功
- "运行逻辑必须读取 settings 而非硬编码；非默认合法值必须真实改变转换时机"

**命名测试**（§10 L632-633）：
- `test_nondefault_redis_failure_threshold_and_health_interval_drive_runtime_transitions`——非默认值必须真实改变转换时机
- `test_postgres_only_worker_never_constructs_pings_subscribes_or_recovers_redis`——POSTGRES_ONLY 零 Redis 构造

**STOP condition**（§12 L691）：
- "REDIS runtime 硬编码 3/30 而不消费 settings 阈值/间隔；或 deployment mode 与 runtime degraded state 混为一个可变真源"

**结论**: 闭合。deployment mode 与 runtime state 严格分离、settings 驱动转换、POSTGRES_ONLY 零 Redis 有明确测试。

### 3. Host-local Port Signatures（§3 L124-126 + §6.1 L293-357 + §15 L349-350）

**核心设计**：
- `WorkerJobGatewayProtocol` 声明在 `dayu/host/worker.py`（§6.1 L293-325）
- `SchedulerGatewayProtocol` 声明在 `dayu/host/scheduler.py`（§6.1 L327-341）
- "Host worker/scheduler 不得 import `dayu.services`"（§3 L159）
- "Host 作为下层只在自身模块声明调用所需的最小 structural gateway ports"（§3 L159）
- "startup 从上层注入结构兼容的 JobService/ScheduleService，保持 `UI -> Service -> Host -> Agent` 无反向依赖"（§3 DAG L151-152）

**Port 设计**：
- WorkerJobGatewayProtocol：recover / claim / execute_claim(async) / heartbeat / complete / fail / govern_agent_runs——全部 sync 除 execute_claim
- SchedulerGatewayProtocol：next_replayable_occurrence / reserve_due_occurrences / materialize_occurrence——全部 sync
- "返回值和异常只允许 pure jobs/schedules closed types，绝不透出 Store、SQLAlchemy row、Host RunRecord、Redis exception 或 Service concrete type"（§6.1 L347-348）

**命名测试**（§10 L550-552）：
- `test_layers_do_not_import_forbidden_modules`
- `test_job_service_structurally_satisfies_worker_gateway_without_importing_host`
- `test_schedule_service_structurally_satisfies_scheduler_gateway_without_importing_host`

**STOP condition**（§12 L689）：
- "Host-local gateway 需要 import Service/Store/concrete Host 类型才能实现，或 Schedule gateway 把 Store 级 begin/mark 接口泄漏给 Host"

**结论**: 闭合。反向依赖通过 Protocol structural typing + import guard + 测试三重封锁。

### 4. Materialization already_enqueued 三态（§5.1 L214/216/233-235 + §5.3 L269-270 + §12 L681）

**核心设计**：

| 路径 | ScheduleMaterializationAction | ScheduleMaterializationResult.action | receipt | JobService call |
| --- | --- | --- | --- | --- |
| 正常 begin → enqueue → mark | `enqueue` | `enqueued` | 非空，job_id 一致 | enqueue + mark |
| 并发输家 begin 时看到 ENQUEUED | `already_enqueued` | `already_enqueued` | **必须 None** | **零调用** |
| disabled/miss 跳过 | `skipped` | `skipped` | None | 零调用 |

**§5.1 L235 精确文本**：
> "enqueued 只表示本调用完成 enqueue+mark，receipt 必非空且 job_id 逐字段一致；already_enqueued 表示并发输家在 begin 时看到持久 ENQUEUED，receipt 必须 None、job_id 必非空且本调用零 JobService/Redis/mark；skipped 时 receipt 为 None 且 occurrence 为 SKIPPED。禁止从 occurrence 字段伪造缺少 definition/idempotency 事实的 receipt。"

**§5.3 L270 精确文本**：
> "materialize_occurrence 收到 begin_materialization(already_enqueued) 必须直接返回 ScheduleMaterializationResult(already_enqueued, occurrence, None)；这是并发 terminal race 的正常 closed 结果，不得再次 enqueue/publish/mark，也不得新增按 job_id 查询或伪造 JobEnqueueReceipt。"

**命名测试**（§10 L567）：
- `test_materialize_occurrence_losing_terminal_race_returns_already_enqueued_without_fabricated_receipt`

**STOP condition**（§12 L681）：
- "并发 materialization 输家看到 ENQUEUED 后伪造 receipt、重复调用 JobService/Redis/mark，或为此新增按 job_id 读取 receipt 的第二真源"

**结论**: 闭合。三态 action/result/receipt 映射精确，already_enqueued 路径零 side effect 有明确 STOP。

---

## Prior Closure Regression Check

逐项扫描 707 行 plan 与 128 行 Controller fix，所有 prior closures 无回归：

| Area | Closure Count | Regression Check |
| --- | --- | --- |
| MiM M-001..003 / L-001..002 + Open Q | 6 items | 全部在最新 plan 中保持（§5.2/§5.1/§6.1/§4.1/§8/§6.2） |
| Terra S22-001..009 | 9 items | materializing/snapshot/governance/drain/startup/CI 全保持 |
| Controller 25 收口 | 25 items | §5.1 content immutability、§5.2 replay timestamps、§5.3 skipped_conflict/intake gate/Redis state/governance pages/lock order/scan limit/lookback/MISSING_HOST_WAIT/already_enqueued 全保持 |
| Round-1 closure (5 items) | 5 items | lookback C>=L/explicit-provider Redis/lock order/PENDING availability/MATERIALIZING typed decision 全保持 |
| Round-2 closure (3 items) | 3 items | generic recover READ COMMITTED/MISSING_HOST_WAIT/scan limit raw count 全保持 |

---

## Blocking-Only New Finding Scan

扫描 707 行 plan + 128 行 Controller fix 全文，仅检查 blocking（H/M/L）新 finding：

- **Intake gate**: epoch-based 线性化 + capture/is_open 双验 + 3 个命名测试 + STOP。无 open。
- **Redis runtime/state**: deployment mode 与 runtime state 分离 + settings 驱动 + POSTGRES_ONLY 零 Redis + 2 个命名测试 + STOP。无 open。
- **Host-local ports**: Protocol 声明在 Host module + structural typing + import guard + 3 个命名测试 + STOP。无 open。
- **Materialization 三态**: already_enqueued 零 side effect + receipt=None + 1 个命名测试 + STOP。无 open。
- **Schema/DLL**: §5.3 DDL exact CHECK、FK/RLS/grants/downgrade + 0004 migration owner 明确。无 open。
- **State machines**: §7.3 Worker 7 状态 + §7.4 Scheduler 4 状态 + §6.2 Governance 10 action（含 MISSING_HOST_WAIT）。无 open。
- **Lock ordering**: §6.2 L389 8 入口统一锁序 + READ COMMITTED 双 statement。无 open。
- **Drain**: §7.5 gate + epoch + drain_abandon_requested + WAITING_FOR_INNER_WORK + os._exit(1)。无 open。
- **CI**: §10 五条独立 pytest + workflow ignore + PG16/Redis digest。无 open。
- **Tests**: 98 个命名测试覆盖 config/schedule/worker/Redis/CLI/intake/port。无 open。
- **STOP conditions**: §12 18 条 STOP 与 plan 全文对齐。无 open。
- **Residual**: §13 7 项 residual 合理。无 open。

**未发现新 H/M/L finding。**

---

## Artifact Metadata

| Field | Value |
| --- | --- |
| Target SHA256 | `d71eced3e4e58f6e3ffa875a2699a425a700b7ba2552267072c10ed7113eaa87` |
| Fix SHA256 | `b913591e8b4f3fcec13e8bedd382036f6fb2fe25f1d751c5465b22c3d4b0cab9` |
| Baseline | `38ddad4` |
| Plan lines | 707 |
| Fix lines | 128 |
| Named tests | 98 |
| STOP conditions | 18 |
| Prior closures | 51 items (all no regression) |
| New H/M/L | 0/0/0 |
