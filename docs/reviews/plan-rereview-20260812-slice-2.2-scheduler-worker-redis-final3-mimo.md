# Slice 2.2 Scheduler / Worker / Redis — MiMo Final3 Closure Plan Re-Review

- **Status**: PASS / open H/M/L=0/0/0
- **Reviewer**: MiMo (final3 closure)
- **Target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md` (SHA256 `d71eced3...eaa87`)
- **Fix**: `docs/reviews/plan-fix-20260812-...-codex.md` (SHA256 `b913591e...cab9`)
- **Prior**: `plan-rereview-...-final2-mimo.md`（PASS/0）
- **Scope**: intake gate / Redis runtime+settings / Host-local port signatures / materialization already_enqueued 三态 / blocking-only 新 finding 扫描

## 0. Verdict

**PASS.** 四项复核全部正确闭合，prior closure 无回归，无 blocking 新 finding。

## 1. Intake Gate

§7.5 line 449: `ProcessIntakeGate` 暴露 `capture() -> IntakeEpoch`、`request_stop() -> None`、`is_current(epoch) -> bool`、`is_open: bool`。第一次 signal 递增 epoch 并永久关闭 gate。

每个可能返回新 work 的 `asyncio.to_thread`/await 在派发前 capture，返回后在启动 handler/heartbeat/claim/begin/materialization/tick/subscribe 前必须同时验证 `is_open` AND `is_current(captured)`。

§7.5 line 451 精确规定 gate 后行为：
- gate 前已发出但 gate 后返回的 PG claim → 不得启动 handler/heartbeat，已取得 lease 只由 persisted expiry/recovery 收敛。
- gate 后返回的 replay/list/reservation → 不得启动 `materialize_occurrence`。
- 只有 gate 前已派发的一个 Service-owned `materialize_occurrence` 算"当前 occurrence"，即使 gate 后返回也必须完成整个 begin/enqueue/mark 收口。

STOP conditions line 690: "首信号关闭intake gate后，先前发出的claim/list/reserve返回仍可启动handler、heartbeat或新materialization；或把已派发materialization中途拆断形成新崩溃窗口"。

**正确性论证**：`is_current(captured)` 利用 epoch 递增实现线性化——gate 关闭后 captured epoch 过期，任何后返回的 to_thread 结果无法通过检查。唯一的例外是已在 gate 前派发的 materialize_occurrence，它在 gate 后完成但不启动新 work。不存在"gate 后返回的 claim 启动 handler"的窗口。

## 2. Redis Runtime / Settings

§4.1 line 180: `PlatformQueueAdmissionKind` 三值 `not_required/postgres_only/redis`。§7.2 line 402: `RedisRuntimeState={event_assisted,polling_degraded}` 只由 Worker 持有且只在 REDIS admission 构造。

POSTGRES_ONLY runtime 的 state/publisher/subscriber/client 全部为 None，永不 construct/ping/subscribe/resubscribe/health-recover Redis。§7.2 line 412: "运行逻辑必须读取settings而非硬编码；非默认合法值必须真实改变转换时机"。

STOP conditions line 691: "POSTGRES_ONLY构造/调用任何Redis对象；REDIS runtime硬编码3/30而不消费settings阈值/间隔；或deployment mode与runtime degraded state混为一个可变真源"。

**正确性论证**：`PlatformQueueMode`（profile-derived 配置）与 `RedisRuntimeState`（Worker 运行时状态）是两个独立概念。mode 由 profile 唯一决定，runtime state 由实际 Redis 操作结果驱动。POSTGRES_ONLY 不构造 Redis 对象，REDIS 读取 settings 阈值/间隔。两者不混为一个可变真源。

## 3. Host-Local Port Signatures

§6.1 lines 293-350: `WorkerJobGatewayProtocol` 在 `dayu.host.worker` 声明，`SchedulerGatewayProtocol` 在 `dayu.host.scheduler` 声明。

- Worker gateway: `recover/claim/execute_claim(async)/heartbeat/complete/fail/govern_agent_runs` — 全部 sync 除 `execute_claim`。
- Scheduler gateway: `next_replayable_occurrence/reserve_due_occurrences/materialize_occurrence` — 全部 sync。三条 Service-owned 高层入口，不是 Store facade。

line 346-348: "Host loop必须只经 `asyncio.to_thread` 调用；返回值和异常只允许pure jobs/schedules closed types，绝不透出Store、SQLAlchemy row、Host RunRecord、Redis exception或Service concrete type"。

line 349-350: "`JobService`/`ScheduleService`不继承、不import Host protocol，但必须由pyright structural assignment证明精确满足；startup只做结构化注入"。

STOP condition line 689: "Host-local gateway需要import Service/Store/concrete Host类型才能实现，或Schedule gateway把Store级begin/mark接口泄漏给Host"。

**正确性论证**：Host 声明最小 structural gateway ports，Service 由 pyright 证明满足。Host 不知道 `dayu.services` 存在。Scheduler port 是三条 Service-owned 高层入口（next/reserve/materialize），不是 Store 的 begin/mark facade。返回值只有 pure closed types。

## 4. Materialization already_enqueued 三态

§5.1 line 214: `ScheduleMaterializationAction={enqueue, already_enqueued, skipped}`（store `begin_materialization` 返回）。
§5.1 line 216: `ScheduleMaterializationResultAction={enqueued, already_enqueued, skipped}`（高层 `materialize_occurrence` 返回）。

§5.3 line 270: "`materialize_occurrence`收到`begin_materialization(already_enqueued)`必须直接返回`ScheduleMaterializationResult(already_enqueued, occurrence, None)`；这是并发terminal race的正常closed结果，不得再次enqueue/publish/mark，也不得新增按job_id查询或伪造`JobEnqueueReceipt`"。

§5.1 line 235: "`already_enqueued`表示并发输家在begin时看到持久ENQUEUED，receipt必须None、job_id必非空且本调用零JobService/Redis/mark"。

STOP condition line 681: "并发materialization输家看到ENQUEUED后伪造receipt、重复调用JobService/Redis/mark，或为此新增按job_id读取receipt的第二真源"。

**正确性论证**：三态分离了 store 级 `begin_materialization` 的返回值（enqueue/already_enqueued/skipped）与 Service 级 `materialize_occurrence` 的最终结果（enqueued/already_enqueued/skipped）。`already_enqueued` 是并发 terminal race 的正常 closed 结果——输家在 `begin_materialization` 时发现 occurrence 已持久化为 ENQUEUED，直接返回 receipt=None，零 JobService/Redis/mark 调用。不新增按 job_id 查询 receipt 的第二真源。

## 5. Prior Closure 回归

全部历史 finding（MiMo M-001..M-004/L-001..L-002 + Terra TERRA-S22-001..009 + MiM M-001..L-002）均已在 target plan 和 Controller fix 中正确闭合。lookback C>=L、generic recover 双 statement late re-read、MISSING_HOST_WAIT 停止续租、scan limit raw candidate 计数+下限——全部仍在最新 target 中正确存在。无回归。

## 6. Blocking 新 Finding 扫描

无 blocking 新 finding。四项复核均有精确 plan 文本、STOP condition 覆盖和 named test 锁定。

## 7. Final Verdict

**PASS / open H/M/L=0/0/0.** Plan 可进入 accepted baseline commit。
