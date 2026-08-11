# Slice 2.2 activation / availability corrective plan FINAL closure re-review（Terra）

- **复审时间**：2026-08-12 05:00:58 CST
- **结论**：`PASS`
- **Open H/M/L**：`0 / 0 / 0`
- **目标计划**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`
- **目标计划 SHA-256（已核验）**：`cf952ce6a76384c0dc62c642403804a9328d0b80e58897b9003ed1f473a29a62`
- **Controller fix**：`docs/reviews/plan-fix-20260812-slice-2.2-activation-pg-clock-codex.md`
- **Controller fix SHA-256（已核验）**：`e5846a6d0c50abc949c6e581dbfea723155a86d65d87058acf8e5ffaeeba1a76`
- **首轮 Terra review**：`docs/reviews/plan-rereview-20260812-slice-2.2-activation-pg-clock-terra.md`（`FAIL / 0 / 1 / 1`）
- **复审边界**：完整重读根 `AGENTS.md`、`planreview` 技能、当前 target、Controller fix 与首轮 Terra review；仅做九项 corrective closure 和 blocking-only regression scan。未读取或评价冻结 WIP 的完成度，未运行实现、测试、live/network/provider/broker 或交易操作，未修改 target/fix/首轮 review/production/tests/deps/README。

## 1. 审核结论

九项 corrective 均已在同一份 target 中闭合到可生成、可验收的精确合同，并在 DTO/Protocol、Service/Host ownership、状态机、命名测试和 STOP 条件之间保持一致。本次未发现新的阻断性 H/M/L 回归；首轮 `TERRA-S22-APC-001` 和 `TERRA-S22-APC-002` 均已真实消除，而非仅改写结论文字。

## 2. 九项 corrective closure

| corrective | 结论 | 直接证据 |
| --- | --- | --- |
| 1. conditional PG-clock DML | `CLOSED` | `S22-CTRL-008` 与 Store ACTIVE 规则均锁定：row lock 后单条 conditional DML、one-row materialized CTE 的同一 `clock_timestamp()` 同时进入时间 guard 和 returned observation，CAS 同 statement；零行后仍持锁重读并返回零 mutation `clock_stale`（target:116、347）。`test_activate_conditional_pg_clock_guard_rejects_candidate_expiring_at_update_boundary` 与对应 STOP 禁止 precheck/no-guard UPDATE（target:695、813）。这把 future 的可证明点收敛为 DML 线性化点。 |
| 2. 三次总 CAS | `CLOSED` | target 明定每次 public activate/re-enable 总计三次 `set_state` CAS、包含首次、第三次 stale 返回且绝不 rebase（target:116、348）；Controller fix 同步该计数（fix:29、77），命名测试精确写为 `three_total_cas_attempts_including_first`（target:694），STOP 禁止超过三次（target:813）。 |
| 3. scan-limit explicit resulting state/cursors | `CLOSED` | `ScheduleReservationBatch` 同时拥有 `expected_next_fire_at`、`resulting_state`、`resulting_next_fire_at`；normal 与 scan-limit batch 的 state/cursor 合法组合分别固定，禁止从 skip reason 推断（target:252）。scan-limit 要求同事务 audit + disable + 保留 expected persisted cursor + skip PENDING（target:281、284、352）；命名测试与 STOP 均覆盖（target:688–690、812）。 |
| 4. transition before/after matrix | `CLOSED` | `ScheduleStateTransitionResult` 以 request、previous definition、observation、candidate 自证；`applied`、`unchanged`、`clock_stale` 的 version/state/cursor/zero-mutation 矩阵精确封闭，execution unavailable 只能是 Service closed error（target:245、263–269、349）。命名矩阵测试和 ACTIVE DML STOP 同步存在（target:696、813）。 |
| 5. committed enqueue DAG | `CLOSED` | DAG 固定为 ScheduleService 到 JobService 的 `enqueue_committed_schedule_occurrence`（target:160）；Host `SchedulerGatewayProtocol` 只暴露三个高层 Service entry，不泄漏 Store `begin/mark`（target:414–461）。MATERIALIZING 直接携带 persisted decision 进入窄 committed entry，不做 availability 或普通 enqueue，随后 Store 重验 mark（target:463、477–479）；命名 trap 测试和 STOP 禁令齐备（target:713–714、816）。 |
| 6. negative availability 零 mutation | `CLOSED` | activation unavailable 在 Store 前抛 closed error 并保持 disabled；PENDING `pending_unavailable` 返回 typed `unavailable`，schedule/occurrence 原字节不变，实际已 MATERIALIZING 的 durable commitment 优先（target:117–118、269、349、354、357）。命名测试覆盖 activation、pending 和 mixed-capability process，STOP 禁止升级为 global disable/skip（target:702–704、814）。 |
| 7. MATERIALIZING-first replay + PENDING fairness | `CLOSED` | `ScheduleReplayPage` 将所有 MATERIALIZING 固定排在 PENDING 前；PENDING 以独立 keyset cursor 无重复 wrap，unavailable 不结束 page，MATERIALIZING 不受 pending cursor 影响（target:255–259、355、540–554）。相应 priority、pending rotation 和 stale-admission/committed-replay tests 均已命名（target:705–707、712–714），STOP 明确禁止 head-of-line starvation（target:815）。 |
| 8. due cursor/page fairness | `CLOSED` | `ScheduleDueCursor/Page/ScanResult` 精确规定 active-only `(next_fire_at, schedule_id)` keyset、无重复 wrap、已检查前缀 cursor 和 bounded single reservation（target:246–249、351、542）。无可用项时继续跨 tick 轮转，不把 local unavailable 写入 durable truth；至少 page-limit 穿越 unavailable prefix 和 no-duplicate tests 已锁定（target:708–709）。 |
| 9. 双 cursor assignment-before-await | `CLOSED` | Scheduler 只维护 `ScheduleReplayCursor` 和 `ScheduleDueCursor` 两个 process-local cursor；每个 gateway 返回后，在任一 gate/epoch/materialize/result 处理 await 前立即赋值，且不混用（target:540）。精确 Host port 签名均使用 typed cursor 与 keyword-only limit（target:414–433），命名调用顺序/busy-loop tests 和 STOP 同步覆盖（target:710–711、815）。 |

## 3. Signature、边界与回归核对

- `ScheduleStoreProtocol` 的九项 surface 保持纯 domain DTO：`get` 返回 `ScheduleObservation`，`set_state` 的 candidate 是 keyword-only，due/replay page 均以 typed cursor + keyword-only limit 表达（target:297–345）。没有 callback、SQLAlchemy session/row 或 croniter 泄漏。
- Host-local `WorkerJobGatewayProtocol`/`SchedulerGatewayProtocol` 只使用 pure jobs/schedules closed types；Service 以 structural assignment 注入，Host 不 import `dayu.services`，Scheduler 不接触 Store-level materialization/mark（target:380–463、174）。这维持既定依赖倒置，没有由 corrective 引入反向 concrete dependency。
- `ScheduleJobGatewayProtocol` 的 availability 与 committed-enqueue 责任边界分离；negative proof 不缓存、不落 PG/Redis、不触发全局状态转换（target:435–445、463、477–479）。
- 新增的 page/cursor、scan-limit 与 transition DTO 不产生第二 cursor、第二 registry 或第二 time truth；`clock_timestamp()`、PostgreSQL state/CAS 和 persisted snapshot 仍是唯一相应真源（target:116、244、248–259、351–358）。

## 4. Findings 与 open questions

无 material finding；无 open question。blocking-only regression scan 未发现 corrective 与既有 schedule/outbox、Service/Host port、named-test 或 STOP 合同间的矛盾。

## 5. 残余风险与后续门禁

- 这是计划 closure，不是实现验收；冻结 WIP 尚未恢复，不能据此声称 production/test 行为已达标。
- 恢复实施后仍必须执行 target §11 的真实 PG16/Redis、subprocess signal、pyright、coverage、allowlist 与双路 code-review 门禁；尤其 conditional DML 的分钟边界、真实 keyset wrap 与 committed replay 不得由 fake-only 代替。
- 按 target 当前状态，仍需 Controller 接受本轮双路 final review 后才可解除 implementation pause；这不是本 artifact 的修改授权。

## 6. 最终计划复审结论

`PASS`。目标 SHA-256 已核验为 `cf952ce6a76384c0dc62c642403804a9328d0b80e58897b9003ed1f473a29a62`；九项 corrective 全部 `CLOSED`，open H/M/L 为 `0 / 0 / 0`，未发现 blocking regression。
