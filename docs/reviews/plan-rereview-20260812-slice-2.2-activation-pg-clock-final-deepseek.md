# Slice 2.2 activation / availability corrective plan FINAL closure re-review（DeepSeek）

- **复审时间**：2026-08-12 05:10:45 CST
- **结论**：`PASS`
- **Open H/M/L**：`0 / 0 / 0`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **目标计划 SHA-256（已核验）**：`cf952ce6a76384c0dc62c642403804a9328d0b80e58897b9003ed1f473a29a62`
- **Controller fix**：`docs/reviews/plan-fix-20260812-slice-2.2-activation-pg-clock-codex.md`
- **Controller fix SHA-256（已核验）**：`e5846a6d0c50abc949c6e581dbfea723155a86d65d87058acf8e5ffaeeba1a76`
- **首轮 Terra review**：`docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-terra.md`（`FAIL / 0 / 1 / 1`）
- **最终 Terra review**：`docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-final-terra.md`（`PASS / 0 / 0 / 0`）
- **复审边界**：完整重读根 `AGENTS.md`、`planreview` 技能、当前 target、Controller fix 与两份 Terra review；只做九项 corrective closure 与 blocking-only regression scan。以只读方式核对既有 baseline 符号（`JobHandlerDescriptor`、`JobEnqueueReceipt`、`Principal`/`TenantScope`、`RunRecord.cancel_requested_at`、`JobStoreProtocol.heartbeat`、Host `cancel_run` surface），未读取或评价冻结 WIP 的完成度，未运行实现、测试、live/network/provider/broker 或交易操作，未修改 target/fix/任何 Terra review/production/tests/deps/README，未启动子 agent。

## 1. 审核结论

九项 corrective 已在同一份 target（SHA `cf952c...a29a62`）中闭合为可生成、可验收的精确合同，且 DTO/Protocol、Service/Host ownership、状态机、命名测试与 STOP 条件之间交叉一致；首轮 Terra 的两项 finding（`TERRA-S22-APC-001` conditional DML 原子线性化、`TERRA-S22-APC-002` CAS 计数不一致）均已被真实消除而非改写结论文字。本次未发现新的阻断性 H/M/L 回归。

## 2. 九项 corrective closure

| corrective | 结论 | 直接证据 |
| --- | --- | --- |
| 1. conditional PG-clock DML | `CLOSED` | `S22-CTRL-008` 与 Store ACTIVE 规则一致锁定：row lock 后**一条** conditional DML，one-row materialized CTE 只读一次 `clock_timestamp()`，同一值同时进入 `:candidate > database_now` 谓词与返回的 `ScheduleObservation.database_now`，tenant/id/version/source-state CAS 同 statement；零行时仍持锁重读 row 与 fresh clock 并返回零 mutation `clock_stale`；明令禁止 `transaction_timestamp()`、锁前 clock 与 Python precheck 后无 guard UPDATE（target:116、347）。STOP 同步禁止同值 guard 缺失与 precheck（target:813）；命名测试 `test_activate_conditional_pg_clock_guard_rejects_candidate_expiring_at_update_boundary` 逐字存在（target:695）。future 的可证明点被收敛为 DML 线性化点，`TERRA-S22-APC-001` 消除。 |
| 2. public 总计三次 CAS 含首次 | `CLOSED` | target 两处（`S22-CTRL-008` target:116 与 Store ACTIVE 规则 target:348）统一为“每次 public activate/re-enable **总计三次** `set_state` CAS 尝试，**包含首次**；第三次仍 stale 直接返回第三个 closed result，原 `expected_version` 不变且不自动 rebase，不得用本机 clock/sleep/无限循环”；Controller fix 同步同一计数（fix:29、77）。命名测试精确写为 `test_activate_clock_stale_uses_three_total_cas_attempts_including_first_without_version_rebase`（target:694），STOP 禁止总 CAS 超过三次（target:813）。旧名 `retries_three` 与旧“重试三次”表述经 grep 确认零残留，`TERRA-S22-APC-002` 消除。 |
| 3. scan-limit batch 显式 resulting state/cursors | `CLOSED` | `ScheduleReservationBatch` 同时携带 `expected_next_fire_at`、`resulting_state`、`resulting_next_fire_at`；normal 与 scan-limit batch 的合法组合分别固定，禁止从 skip_reason 猜 target state（target:252）。scan-limit 路径同一事务插入唯一 audit + 显式 CAS 到 `disabled`/保留 expected persisted cursor + skip 既有 PENDING（target:281、284、352）。命名测试 `test_scheduler_candidate_scan_limit_disables_with_one_closed_audit`、`test_scan_limit_batch_explicitly_disables_and_preserves_expected_cursor_without_skip_reason_inference`（target:688、690），STOP 同步（target:812）。 |
| 4. transition before/after action matrix | `CLOSED` | `ScheduleStateTransitionAction` 精确封闭为 `applied/unchanged/clock_stale`，execution unavailable 是 Service 在调用 Store 前抛出的 closed error，不伪装成 Store transition（target:233、269）；`ScheduleStateTransitionResult(action, request, previous_definition, observation, activation_next_fire_at)` 携带 before/after、原 request 与本次 candidate，矩阵逐条锁定 version `+1`、state/cursor/零 mutation 约束，任何其它组合构造时抛 `ScheduleInvariantError`（target:245、263–269）。命名矩阵测试（target:696）与 STOP（target:813）齐备。 |
| 5. MATERIALIZING committed enqueue DAG | `CLOSED` | 依赖 DAG 固定为 ScheduleService → JobService `enqueue_committed_schedule_occurrence`（target:160、440）；Host `SchedulerGatewayProtocol` 只暴露三个 Service 高层入口，绝不泄漏 Store `begin/mark`（target:414–433）。MATERIALIZING replay 直接把 store 返回的 typed persisted `ScheduleMaterializationDecision` 传入窄 committed entry，不接受 ordinary enqueue、不重复 availability gate，随后 `mark_enqueued` 在锁内重验（target:463、477–479）；命名 trap 测试 `test_materializing_replay_uses_committed_enqueue_entry_and_never_ordinary_enqueue`、`test_materializing_replay_does_not_call_execution_availability_gateway`（target:713–714），STOP 同步（target:816）。 |
| 6. negative availability 零 mutation/不做全局 skip | `CLOSED` | activation unavailable 在 Store 前抛 closed `ScheduleExecutionUnavailableError` 并保持 disabled row 原字节（target:118、349、477）；PENDING `pending_unavailable` 返回 typed `unavailable`，schedule/occurrence 零 mutation 并继续页内下一项（target:117、354、357）；已持久 MATERIALIZING 的 durable commitment 优先于任何 stale admission（target:117、354）。availability 不写 PG/Redis/不做 process cache，registries 无 remove/replace（target:118、463）。命名测试覆盖 activation、pending、mixed-capability（target:702–704），STOP 禁止升级为 global disable/skip（target:814）。 |
| 7. MATERIALIZING-first replay + PENDING keyset 公平 | `CLOSED` | `ScheduleReplayPage` 规定全部 MATERIALIZING 严格排在 PENDING 前；PENDING 按独立 keyset cursor 读取并可在尾部无重复 wrap 到队头填充剩余 slot，MATERIALIZING 不受 pending cursor 影响（target:256、355）。`list_replayable` 无条件优先最老 MATERIALIZING，总数受 keyword-only limit 约束、页内不重复（target:355）。命名测试覆盖 priority、PENDING rotation、unavailable 不饿死 materializing commitment（target:705–707），STOP 禁止 head-of-line starvation 与重复 wrap（target:815）。 |
| 8. due cursor/page 跨页公平 | `CLOSED` | `ScheduleDueCursor/Page/ScanResult` 精确规定 active-only `(next_fire_at, schedule_id)` keyset、页内无重复 wrap、已检查前缀 cursor 与 bounded 单次 reservation（target:246–249、351、542）。Service 逐 entry 跳过本地 unavailable 且零 mutation，整页 unavailable 时返回该页最后 cursor 下一 tick 继续，任意长度 unavailable 前缀不能永久挡住 later available schedule（target:249、542）。命名测试 `test_due_cursor_rotates_past_unavailable_prefix_at_least_page_limit_to_later_available_schedule`、`test_due_page_wrap_has_no_duplicates_and_unavailable_rows_remain_byte_exact`（target:708–709），STOP 同步（target:815）。 |
| 9. 双 cursor 在首个后续 await 前赋值 | `CLOSED` | Scheduler 只维护 `ScheduleReplayCursor` 与 `ScheduleDueCursor` 两个 process-local cursor、不混用不持久化（target:540）；每个 gateway 返回后、任何 gate/epoch/materialize/result 处理 await **之前**立即把 typed cursor 赋为 `page.next_pending_cursor` / `result.next_due_cursor`（target:540）。Host 侧 gateway 签名全部使用 typed cursor + keyword-only limit（target:414–433）。命名测试 `test_scheduler_assigns_each_typed_cursor_before_first_followup_await_and_never_mixes_them`、`test_replay_page_limit_and_cursor_prevent_same_tick_busy_loop_or_duplicate_occurrence`（target:710–711），STOP 禁止 cursor 混用/未立即消费（target:815）。 |

## 3. Signature、边界与回归核对

- `ScheduleStoreProtocol` 九项 surface 精确：`register/get/get_occurrence/set_state/list_due/reserve_occurrences/list_replayable/begin_materialization/mark_enqueued`；`get` 返回 `ScheduleObservation`，`set_state` 的 candidate 为 keyword-only，due/replay page 均为 typed cursor + keyword-only limit（target:297–345）。无 callback、SQLAlchemy session/row、croniter 或第二时钟真源泄漏（target:345、116）。
- Host-local `WorkerJobGatewayProtocol`/`SchedulerGatewayProtocol` 只使用 pure jobs/schedules closed types；Service 以 pyright structural assignment 注入，Host 不 import `dayu.services`，Scheduler 不接触 Store 级 materialization/mark（target:380–463、174）。`ScheduleJobGatewayProtocol` 的 availability 与 committed-enqueue 责任分离，negative proof 不缓存/不落 PG/Redis（target:435–445、463、477–479）。
- 既有 baseline 符号交叉核对全部一致：`JobHandlerDescriptor` 七字段（job_type/payload_schema_name/payload_schema_version/max_attempts/retry_base_seconds/retry_max_seconds/lease_duration_seconds，`dayu/investment/domain/jobs.py:991–1010`）与 plan 的“descriptor 七字段”一致；`JobEnqueueReceipt` 含 `job_id`/`idempotency_reused`（jobs.py:1075–1091）支持 `idempotency_reused=True` 与 mark 同 job 语义；`Principal.to_scope()`/`TenantScope`（`dayu/investment/domain/identifiers.py:206,237,271`）；`RunRecord.cancel_requested_at`（`dayu/contracts/run.py:137`）；`JobStoreProtocol.heartbeat -> JobHeartbeatResult`（`dayu/investment/storage/protocols.py:347–369`）；Host `cancel_run(run_id) -> RunRecord`（`dayu/host/protocols.py:1438`、`dayu/host/host.py:839`）与 plan 定义的窄 `HostRunCancellationProtocol` 结构兼容，`cancel_run_and_settle` 仅由 process_lifecycle 使用、Worker 永不调用（target:68、21）。
- 状态机（target:544–554）与 §5.3 Store 矩阵、§6.1 gateway、§7.4 每 tick 预算、§7.5 drain 线性化点一致；`skipped_conflict` 后 scheduler 固定 nonzero 停止（target:358、554、817）；并发 terminal race 输家返回 `already_enqueued` 且零 JobService/Redis/mark、不伪造 receipt（target:356、818）。
- 新增 page/cursor/scan-limit/transition DTO 不产生第二 cursor、第二 registry 或第二 time truth；`clock_timestamp()`、PostgreSQL state/CAS 与 persisted snapshot 仍是唯一相应真源（target:116、244、248–259、351–358）。

## 4. Findings 与 open questions

无 material finding；无 open question。blocking-only regression scan 未发现 corrective 与既有 schedule/outbox、Service/Host port、named-test 或 STOP 合同间的矛盾；首轮 Terra 两项 finding 的修复点在 target 内可逐字定位且无残留旧表述。

## 5. 残余风险与后续门禁

- 这是计划 closure，不是实现验收；冻结 WIP（fix §5 记录的 13 条路径）尚未恢复，不能据此声称 production/test 行为已达标。恢复实施后的第一动作按 target §12 要求删除/修正 WIP 中间态（ACTIVE invariant、`if False` 占位、disabled 清 cursor 等）并先跑 focused/static/真实 PG 门禁。
- conditional DML 的“时间谓词零行 vs version/state CAS 零行”判别在计划内由 closed error 契约（`ScheduleVersionConflictError` vs `clock_stale`）与 action 矩阵（`clock_stale` 要求 previous 与 observation 逐字段相等）共同闭合，未单独写成一条 SQL 分支说明；实现时须按该契约区分，否则会误报 conflict。该点已由 `test_activate_conditional_pg_clock_guard_...` 与并发赢家测试覆盖，作为低风险实现注意事项，不构成 finding。
- 恢复实施后仍必须执行 target §11 的真实 PG16/Redis、subprocess signal、pyright、coverage、allowlist 与双路 code-review 门禁；尤其 conditional DML 分钟边界、真实 keyset wrap 与 committed replay 不得由 fake-only 代替。
- 按 target 当前状态，仍需 Controller 接受本轮最终复审后才可解除 implementation pause；这不是本 artifact 的修改授权。

## 6. 最终计划复审结论

`PASS`。目标 SHA-256 已核验为 `cf952ce6a76384c0dc62c642403804a9328d0b80e58897b9003ed1f473a29a62`；九项 corrective 全部 `CLOSED`，open H/M/L 为 `0 / 0 / 0`，未发现 blocking regression。
