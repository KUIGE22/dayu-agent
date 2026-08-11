# Slice 2.2 activation / availability corrective plan FINAL closure re-review（MiMo）

- **复审时间**：2026-08-12 05:14:42 CST
- **结论**：`PASS`
- **Open H/M/L**：`0 / 0 / 0`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **目标计划 SHA-256（已核验）**：`cf952ce6a76384c0dc62c642403804a9328d0b80e58897b9003ed1f473a29a62`
- **Controller fix**：`docs/reviews/plan-fix-20260812-slice-2.2-activation-pg-clock-codex.md`
- **Controller fix SHA-256（已核验）**：`e5846a6d0c50abc949c6e581dbfea723155a86d65d87058acf8e5ffaeeba1a76`
- **首轮 Terra review**：`docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-terra.md`（`FAIL / 0 / 1 / 1`）
- **最终 Terra review**：`docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-terra.md`（`PASS / 0 / 0 / 0`）
- **DeepSeek final review**：`docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-deepseek.md`（`PASS / 0 / 0 / 0`）
- **复审边界**：完整重读根 `AGENTS.md`、`planreview` 技能、当前 target、Controller fix、首轮 Terra review、最终 Terra review 与 DeepSeek final review；只做九项 corrective closure 与 blocking-only regression scan。以只读方式核对既有 baseline 符号，未读取或评价冻结 WIP 的完成度，未运行实现、测试、live/network/provider/broker 或交易操作，未修改 target/fix/既 review/production/tests/deps/README，未启动子 agent。

## 1. 审核结论

九项 corrective 均已在同一份 target 中闭合为可生成、可验收的精确合同。DTO/Protocol 可生成性充分、Service/Host ownership 边界清晰、状态机与 action matrix 完备、命名测试与 STOP 条件交叉一致。本轮独立验证未发现新的阻断性 H/M/L 回归；首轮 Terra 的两项 finding（`TERRA-S22-APC-001` conditional DML 线性化、`TERRA-S22-APC-002` CAS 计数不一致）在 target 内已被真实消除。

## 2. 九项 corrective closure

### 2.1 conditional PG-clock DML — `CLOSED`

**合同文本**：`S22-CTRL-008` 第 2 点（target:116）与 Store ACTIVE 规则（target:347）均锁定：row lock 后**一条** conditional DML，one-row materialized CTE 只读一次 `clock_timestamp()`，同一值同时进入 `:candidate > database_now` 谓词与返回的 `ScheduleObservation.database_now`，tenant/id/version/source-state CAS 同 statement。零行时仍持锁重读 row 与 fresh clock 并返回零 mutation `clock_stale`。

**DTO 可生成性**：`ScheduleActivationRequest(schedule_id, expected_version, target_state)` 提供输入；`ScheduleStateTransitionResult(action, request, previous_definition, observation, activation_next_fire_at)` 携带完整 before/after；`ScheduleObservation(definition, database_now)` 提供 PG-clock 消费端。Store 签名 `set_state(scope, request, *, activation_next_fire_at)` 的 keyword-only candidate 由 Service 计算后传入。DTO 可直接生成。

**命名测试**：`test_activate_conditional_pg_clock_guard_rejects_candidate_expiring_at_update_boundary`（target:695）逐字存在，断言时间 guard 与 CAS 在同一写 statement、零 version/cursor mutation、返回 fresh observation。

**STOP 同步**：target:813 明令禁止 `transaction_timestamp()`、锁前 clock、Python precheck 后无 guard UPDATE。

**首轮 Terra finding 消除**：`TERRA-S22-APC-001` 的反例——Python 比较后发无时间谓词 UPDATE 导致写入已过期 cursor——已被同一 statement conditional DML 线性化消除。`clock_stale` 由 zero-row 分支返回，不是独立 SQL 分支；action matrix（target:263-269）与 `ScheduleVersionConflictError` 共同区分时间谓词零行与 version/state CAS 零行。

### 2.2 public 总计三次 CAS 含首次 — `CLOSED`

**合同文本**：target:116 与 target:348 统一为"每次 public activate/re-enable **总计三次** `set_state` CAS 尝试，**包含首次**；第三次仍 stale 直接返回第三个 closed result，原 `expected_version` 不变且不自动 rebase，不得用本机 clock/sleep/无限循环"。

**命名测试**：`test_activate_clock_stale_uses_three_total_cas_attempts_including_first_without_version_rebase`（target:694）精确断言三次调用、三次均 `clock_stale`、原 expected version 不变。

**STOP 同步**：target:813 禁止总 CAS 超过三次。

**首轮 Terra finding 消除**：`TERRA-S22-APC-002` 的计数歧义（"重试三次"vs"最多三次"）已被三处文字统一收敛为"总计三次 CAS，包含首次"消除。Controller fix（fix:29、77）同步同一计数。

### 2.3 scan-limit batch 显式 resulting state/cursors — `CLOSED`

**合同文本**：`ScheduleReservationBatch`（target:252）同时携带 `expected_next_fire_at`、`resulting_state`、`resulting_next_fire_at`；normal 与 scan-limit batch 的 state/cursor 合法组合分别固定，禁止从 skip reason 猜 target state。scan-limit 路径同一事务插入唯一 audit + 显式 CAS 到 `disabled`/保留 expected persisted cursor + skip 既有 PENDING（target:281、284、352）。

**DTO 可生成性**：`ScheduleReservationResult(action, occurrences)` 中 `lost_race` 时 tuple 空，`reserved` 时 tuple 非空；`ScheduleOccurrenceReservation` 精确携带 `scheduled_for`、state、snapshot、coalesced_count、skip_reason。DTO 语义完备。

**命名测试**：`test_scheduler_candidate_scan_limit_disables_with_one_closed_audit`（target:688）、`test_scan_limit_batch_explicitly_disables_and_preserves_expected_cursor_without_skip_reason_inference`（target:690）。

**STOP 同步**：target:812。

### 2.4 transition before/after action matrix — `CLOSED`

**合同文本**：`ScheduleStateTransitionAction` 精确封闭为 `applied/unchanged/clock_stale`（target:233）；execution unavailable 是 Service 在调用 Store 前抛出的 closed error，不伪装成 Store transition（target:269）。`ScheduleStateTransitionResult(action, request, previous_definition, observation, activation_next_fire_at)` 携带完整 before/after（target:245）。矩阵逐条锁定 version `+1`、state/cursor/zero-mutation 约束（target:263-269），任何其它组合构造时抛 `ScheduleInvariantError`。

**DTO 可生成性**：三个 action 各有精确前置条件和后置断言；`applied` 要求 request expected version == previous version、version 恰好 `+1`、state == target、ACTIVE 要求 candidate aware UTC 且 `> database_now`；`unchanged` 要求逐字段相等、version 不变、state 已等于 target、candidate=None；`clock_stale` 要求 previous=disabled、candidate 非 None 且 `<= database_now`。可直接生成。

**命名测试**：`test_schedule_state_transition_result_action_matrix_closes_before_after_version_cursor_and_candidate`（target:696）。

**STOP 同步**：target:813 明确禁止违反矩阵的组合构造。

### 2.5 MATERIALIZING committed enqueue DAG — `CLOSED`

**合同文本**：依赖 DAG 固定为 ScheduleService → JobService `enqueue_committed_schedule_occurrence`（target:160、440）；Host `SchedulerGatewayProtocol` 只暴露三个 Service 高层入口（target:414-433），不泄漏 Store `begin_materialization` 或 `mark_enqueued`。MATERIALIZING replay 直接把 store 返回的 typed persisted `ScheduleMaterializationDecision` 传入窄 committed entry（target:463、477-479）。

**Protocol 可生成性**：`ScheduleJobGatewayProtocol` 定义 `is_execution_available(descriptor) -> bool` 和 `enqueue_committed_schedule_occurrence(scope, decision) -> JobEnqueueReceipt`（target:435-445）；`SchedulerGatewayProtocol` 定义三个入口（target:414-433）。两个 Protocol 签名完整、类型明确。

**命名测试**：`test_materializing_replay_uses_committed_enqueue_entry_and_never_ordinary_enqueue`（target:714）、`test_materializing_replay_does_not_call_execution_availability_gateway`（target:713）。

**STOP 同步**：target:816 明确禁止 MATERIALIZING replay 走普通 `JobService.enqueue`/availability 路径。

### 2.6 negative availability 零 mutation — `CLOSED`

**合同文本**：activation unavailable 在 Store 前抛 closed `ScheduleExecutionUnavailableError` 并保持 disabled row 原字节（target:118、349、477）；PENDING `pending_unavailable` 返回 typed `unavailable`，schedule/occurrence 零 mutation 并继续页内下一项（target:117、354、357）；已持久 MATERIALIZING 的 durable commitment 优先于任何 stale admission（target:117、354）。availability 不写 PG/Redis/不做 process cache，registries 无 remove/replace（target:118、463）。

**不可变性链路**：`ScheduleJobGatewayProtocol.is_execution_available` 返回 bool，不返回 registry 对象、不缓存、不持久化（target:463）；positive proof 在单进程生命周期内单调（append-only + exact-idempotent），negative proof 只是瞬时能力判断。

**命名测试**：`test_activation_unavailable_keeps_disabled_row_byte_exact_and_never_calls_store_transition`（target:702）、`test_pending_unavailable_admission_returns_no_work_without_schedule_or_occurrence_mutation`（target:703）、`test_mixed_capability_scheduler_cannot_skip_fire_available_to_another_process`（target:704）。

**STOP 同步**：target:814 明确禁止把 negative availability 升级为 global disable/skip。

### 2.7 MATERIALIZING-first replay + PENDING keyset 公平 — `CLOSED`

**合同文本**：`ScheduleReplayPage`（target:256）规定全部 MATERIALIZING 严格排在 PENDING 前；PENDING 按独立 keyset cursor 读取并可在尾部无重复 wrap 到队头填充剩余 slot，MATERIALIZING 不受 pending cursor 影响。`list_replayable` 无条件优先最老 MATERIALIZING，总数受 keyword-only limit 约束（target:355）。

**关键属性**：
- MATERIALIZING-first 保证已提交 commitment 不会被 PENDING starvation 延后；
- PENDING keyset cursor 跨 tick 轮转，确保 unavailable PENDING 不永久阻挡 later available；
- wrap 无重复，防止 busy-loop。

**命名测试**：`test_unavailable_oldest_pending_does_not_starve_later_materializing_commitment`（target:705）、`test_pending_keyset_cursor_rotates_past_unavailable_without_starving_later_available_pending`（target:706）、`test_materializing_is_always_selected_before_pending_regardless_of_pending_cursor`（target:707）。

**STOP 同步**：target:815 禁止 head-of-line starvation 与重复 wrap。

### 2.8 due cursor/page 跨页公平 — `CLOSED`

**合同文本**：`ScheduleDueCursor/Page/ScanResult`（target:246-249）精确规定 active-only `(next_fire_at, schedule_id)` keyset、页内无重复 wrap、已检查前缀 cursor 与 bounded 单次 reservation。`list_due` 只列 `state=active AND next_fire_at <= database_now`（target:351）。整页 unavailable 时返回该页最后 cursor，下一 tick 从边界后继续；到尾后 Store 无重复 wrap。

**关键属性**：
- Service 逐 entry 跳过本地 unavailable 且零 mutation；
- 任意长度 unavailable 前缀不能永久挡住 later available schedule；
- 每 tick 至多一次 bounded reservation，不会创建更多本进程无法处理的 PENDING。

**命名测试**：`test_due_cursor_rotates_past_unavailable_prefix_at_least_page_limit_to_later_available_schedule`（target:708）、`test_due_page_wrap_has_no_duplicates_and_unavailable_rows_remain_byte_exact`（target:709）。

**STOP 同步**：target:815 禁止 page wrap 重复与 unavailable 永久饿死。

### 2.9 双 cursor 在首个后续 await 前赋值 — `CLOSED`

**合同文本**：Scheduler 维护两个且仅两个 process-local cursor：`ScheduleReplayCursor | None` 与 `ScheduleDueCursor | None`（target:540）；不混用、不持久化。每个 gateway 返回后、**任何 gate/epoch/materialize/result 处理 await 之前**立即把 typed cursor 赋为 `page.next_pending_cursor` / `result.next_due_cursor`（target:540）。

**赋值时序保证**：cursor 赋值在同步赋值语句中完成，无 await 可插入；命名测试精确锁定每步调用顺序。

**Host port 签名**：`SchedulerGatewayProtocol` 的 `list_replayable_occurrences` 返回 `ScheduleReplayPage`（含 `next_pending_cursor`），`reserve_due_occurrences` 返回 `ScheduleDueScanResult`（含 `next_due_cursor`），均 keyword-only limit（target:414-433）。

**命名测试**：`test_scheduler_assigns_each_typed_cursor_before_first_followup_await_and_never_mixes_them`（target:710）、`test_replay_page_limit_and_cursor_prevent_same_tick_busy_loop_or_duplicate_occurrence`（target:711）。

**STOP 同步**：target:815 禁止 cursor 混用与未立即消费。

## 3. Signature、边界与回归核对

### 3.1 DTO/Protocol 可生成性总结

| DTO/Protocol | 可生成性 | 证据 |
|---|---|---|
| `ScheduleStoreProtocol` 九项 | OK | target:297-345，签名完整，纯 domain DTO |
| `ScheduleStateTransitionResult` action matrix | OK | target:233-269，三个 action 的 before/after/candidate 约束完备 |
| `ScheduleReservationBatch` + scan-limit | OK | target:252，expected/resulting state/cursor 锁定 |
| `ScheduleJobGatewayProtocol` | OK | target:435-445，availability + committed enqueue 责任分离 |
| `SchedulerGatewayProtocol` 三入口 | OK | target:414-433，typed cursor + keyword-only limit |
| `WorkerJobGatewayProtocol` 七方法 | OK | target:380-412，含 governance cursor/page |
| `ScheduleReplayPage` MATERIALIZING-first | OK | target:256，PENDING keyset wrap 规则完备 |
| `ScheduleDuePage` + `ScheduleDueScanResult` | OK | target:246-249，checked prefix cursor + bounded reservation |
| `ScheduleMaterializationAdmission` closed | OK | target:234，三态精确：pending_available / pending_unavailable / committed_replay |
| `ScheduleOccurrenceReservation` | OK | target:251，snapshot/count/skip_reason 互斥规则完备 |

所有 DTO/Protocol 具有完整类型标注，无 callback/session/croniter/clock 泄漏，可直接生成 Python dataclass 与 Protocol 定义。

### 3.2 Ownership 与 DAG

- Store 不 import `dayu.host`、`dayu.services`、`dayu.contracts` 或 Redis（target:174）。
- Host worker/scheduler 不 import `dayu.services`、concrete PostgreSQL store、business source/research/Broker modules（target:174）。
- `ScheduleService` 拥有 availability orchestration，`JobService` 拥有 execution registry/gateway（target:160、364-445）。
- Startup 以 pyright structural assignment 注入，不使用 cast/getattr/Any/object（target:453-454）。
- 只有两处固定 lazy import：`main.py` 的 platform dispatch 和 `_prepare_queue_admission` 的 Redis import（target:174）。

DAG 无反向依赖、无 callback、无跨层 session、无 registry truth 泄漏。

### 3.3 既有 baseline 符号核对

与 DeepSeek final review 交叉验证一致：
- `JobHandlerDescriptor` 七字段（`dayu/investment/domain/jobs.py:991-1010`）
- `JobEnqueueReceipt` 含 `job_id`/`idempotency_reused`（jobs.py:1075-1091）
- `Principal.to_scope()`/`TenantScope`（`dayu/investment/domain/identifiers.py:206,237,271`）
- `RunRecord.cancel_requested_at`（`dayu/contracts/run.py:137`）
- `JobStoreProtocol.heartbeat -> JobHeartbeatResult`（`dayu/investment/storage/protocols.py:347-369`）
- Host `cancel_run(run_id) -> RunRecord`（`dayu/host/protocols.py:1438`、`dayu/host/host.py:839`）

所有既有符号与 plan 定义的窄 protocol 结构兼容，无 mismatch。

### 3.4 状态机一致性

- Schedule occurrence 状态机（target:554）：PENDING → MATERIALIZING → ENQUEUED；PENDING → SKIPPED；MATERIALIZING 不可逆（stale admission 不撤销）；ENQUEUED/SKIPPED terminal。
- Worker 状态机（target:522-534）：RUNNING → govern → PG claim → HANDLING + HEARTBEATING → complete/fail → governance-required → WAITING_FOR_CORRELATION。
- Redis mode 状态机（target:507-518）：EVENT_ASSISTED ↔ POLLING_DEGRADED；POSTGRES_ONLY 独立。
- Process drain（target:556-562）：gate close → DRAINING → grace → drain_abandon → WAITING_FOR_INNER_WORK → second signal → `os._exit(1)`。

四个状态机在 plan 内交叉一致，无矛盾。

### 3.5 AGENTS.md 约束核对

- **架构硬约束**：`UI -> Service -> Host -> Agent`；Host 只声明 gateway ports，不 import Service（满足）。
- **编码硬约束**：禁止 `Any`/`object`/`cast`/`type: ignore`/`getattr`/`hasattr`（plan STOP 同步禁止）。
- **schema 变更**：`0004_durable_schedules` 按全新 schema 起库，无旧库兼容读取。
- **测试与验证**：命名测试完整覆盖 happy path + failure paths + state machine；STOP 禁止 fake-only 代替真实 lane。
- **目录约束**：`dayu/host/redis_wakeup.py`、`dayu/host/worker.py`、`dayu/host/scheduler.py`、`dayu/host/process_intake.py` 均在 `dayu/host/` 下，符合架构归属。

## 4. Findings

无 material finding。

## 5. Open questions

无。

## 6. Blocking-only regression scan

逐项扫描首轮 Terra finding 与 nine corrective 之间、corrective 与既 review 之间、corrective 与 STOP 合同之间的一致性：

| 扫描维度 | 结论 |
|---|---|
| conditional DML 与 action matrix 一致性 | OK；zero-row → clock_stale（matrix 闭环），CAS 成功 → applied（matrix 闭环），version/state 冲突 → closed error（matrix 外） |
| 三次 CAS 与 STOP 一致性 | OK；STOP 禁止超过三次，测试断言三次 |
| scan-limit resulting state 与 disable 语义一致性 | OK；显式 resulting_state=disabled + expected persisted cursor，不从 skip_reason 推断 |
| committed enqueue DAG 与 Schedule gateway 隔离 | OK；Host Scheduler 不接触 Store begin/mark，只经 Service 高层入口 |
| negative availability 与 durable commitment 优先级 | OK；MATERIALIZING durable commitment 优先于任何 stale admission |
| replay MATERIALIZING-first 与 due fairness 独立性 | OK；两个 keyset cursor 独立、不混用、不持久化 |
| cursor assignment-before-await 与 drain gate 一致性 | OK；drain gate 关闭后已返回的 page 仍消费 cursor 但不启动新 materialization |
| 双路 prior review 结论与本轮独立验证一致性 | OK；Terra PASS（0/0/0）、DeepSeek PASS（0/0/0）与本轮结论一致 |

未发现 blocking regression。

## 7. 残余风险与后续门禁

- 这是计划 closure，不是实现验收；冻结 WIP 尚未恢复，不能据此声称 production/test 行为已达标。
- 恢复实施后的第一动作按 target §12 要求删除/修正 WIP 中间态（ACTIVE invariant、`if False` 占位、disabled 清 cursor 等）并先跑 focused/static/真实 PG 门禁。
- conditional DML 的"时间谓词零行 vs version/state CAS 零行"判别在计划内由 closed error 契约与 action matrix 共同闭合，未单独写成一条 SQL 分支说明；实现时须按该契约区分，否则会误报 conflict。该点已由命名测试覆盖，作为低风险实现注意事项。
- 恢复实施后仍必须执行 target §11 的真实 PG16/Redis、subprocess signal、pyright、coverage、allowlist 与双路 code-review 门禁。
- 按 target 当前状态，仍需 Controller 接受本轮最终复审后才可解除 implementation pause；这不是本 artifact 的修改授权。

## 8. 最终计划复审结论

`PASS`。目标 SHA-256 已核验为 `cf952ce6a76384c0dc62c642403804a9328d0b80e58897b9003ed1f473a29a62`；九项 corrective 全部 `CLOSED`，open H/M/L 为 `0 / 0 / 0`，未发现 blocking regression。
