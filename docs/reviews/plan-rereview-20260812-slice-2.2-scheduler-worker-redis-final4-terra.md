# Slice 2.2 Scheduler / Worker / Redis — Terra final4 closure-only 独立复审

- **复审时间**：2026-08-12 03:00:06 CST。
- **结论**：**PASS**。
- **开放 finding**：`H/M/L = 0/0/0`。
- **代码基线**：`38ddad489f4f9cfa1ae2a4373d69a628e49578bf`。
- **锁定 target**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`，SHA-256 `65357054b7c70ce36d664ca30ec8f71e2f89dec23223a58b0802ea3457082079`（已实测一致）。
- **锁定 Controller fix**：`docs/reviews/plan-fix-20260812-slice-2.2-scheduler-worker-redis-codex.md`，SHA-256 `46cb02de08000553e9f04468f2eb1f4841ecc708350099badd0aa1bd915d5217`（已实测一致）。
- **上一轮 Terra artifact**：`docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-final3-terra.md`，SHA-256 `d4d088fb5dda071dcb0d7983e7e27f69f1a3a4dde26897dc52eb3dce343c6abd`（已完整重读）。
- **审阅边界**：只复核 `TERRA-S22-FINAL3-001` 的最小修复，以及 `TERRA-S22-FINAL-001`、`TERRA-S22-FINAL-002`、Host-local gateway 分层/签名、`M-NEW-001` 的无回归；不扩展历史审计。只读；未修改 target、master、fix、source、tests、README、依赖或 CI；未运行测试、类型检查、Docker、PostgreSQL、Redis、broker、模型或 live action；未启动子 agent、未 commit/push。

## 1. FINAL3-001 closure

**CLOSED**。此前的矛盾是 Protocol 要求 `limit`，Worker 调用文本却未传入，且没有锁定 cursor 消费。当前 target 已逐项消除该歧义：

1. `WorkerJobGatewayProtocol.govern_agent_runs` 仍保持精确闭合签名 `govern_agent_runs(scope, cursor, *, limit: int) -> AgentRunGovernancePage`（target `319–325`）。
2. Worker **只维护一个** process-local governance cursor；每个 poll 在 claim 前、每个 correlated heartbeat 前后，均精确经 `await asyncio.to_thread(gateway.govern_agent_runs, scope, cursor, limit=settings.governance_page_size)` 调用（target `385`）。因此所有调用均显式传入 keyword-only settings limit，而非猜测默认值。
3. 同一段要求取得 page 后立即将同一 cursor 更新为 `page.next_cursor`；尾页为 `None` 时下一次调用从头开始，并明确禁止 poll/heartbeat 双 cursor、丢弃 `next_cursor` 或把 storage projection page 泄漏到 Host（target `385`）。这与 keyset 轮转语义（target `381`）一致。
4. 命名测试同时覆盖跨页公平性和非默认 page-size / keyword-only / cursor rotation：`test_governance_keyset_rotation_prevents_long_active_wait_from_starving_later_rows` 与 `test_worker_governance_uses_configured_keyword_only_page_limit_and_rotates_cursor`（target `609–610`）。同类偏离被列为 STOP（target `691`）。
5. Controller fix `117` 与上述 target 一致，未引入第二个 gateway、默认 limit 或 storage-page 绕行。

## 2. 前轮四项无回归

| 项目 | 结论 | 当前直接证据 |
| --- | --- | --- |
| `TERRA-S22-FINAL-001` intake epoch | **无回归 / CLOSED** | target `449–451` 仍以 event-loop-owned `ProcessIntakeGate` / `IntakeEpoch` 为首信号线性化点，要求所有返回新 work 的 await/to_thread 双验 gate/epoch；gate 后 claim/list/reserve 不得启动新工作，只有已派发 materialization 完整收口。命名 barrier tests 保留于 `626–628`，STOP 保留于 `692`。 |
| `TERRA-S22-FINAL-002` Redis runtime / settings / `POSTGRES_ONLY` | **无回归 / CLOSED** | target `165–194` 继续固定 settings 与严格值域；`401–412` 保持 deployment mode 与 Worker-owned `RedisRuntimeState` 分离、阈值/health interval 从 settings 读取、`POSTGRES_ONLY` 全 Redis refs 为 `None` 且零 Redis 操作。非默认 settings / PG-only 命名测试与 STOP 分别保留于 `632–635`、`693`。 |
| Host-local gateway exact signatures / 分层 | **无回归 / CLOSED** | target `293–350` 保持逐方法 closed Protocol、sync/to_thread 边界、pure-domain 返回和 structural assignment；`352–357` 仍禁止 Scheduler 获取 Store facade。分层 STOP 保留于 `690`，相关结构/依赖命名测试保留于 `550–552`。FINAL3 的调用修复消费既有 Worker gateway，未引入 `dayu.services`、Store 或 concrete Host 依赖。 |
| `M-NEW-001` materialization terminal-race 三态 | **无回归 / CLOSED** | target `211–235` 仍定义 `enqueued/already_enqueued/skipped` closed result；terminal loser 必须 `receipt=None`、保留持久 job id 且零 JobService/Redis/mark。`269–273` 保持 immediate return、无 read-back/伪造 receipt 与 atomic enqueue 收敛；race test 和 STOP 分别保留于 `567`、`682`。 |

## 3. 开放问题与残余风险

- **开放问题**：无。本次 closure-only 范围内未发现新的 H/M/L。
- **残余风险**：本结论仅认证冻结计划的可实施合同，不替代后续实现、pyright、真实 PG16/Redis/SIGTERM lane 或 code review；这些既有验证义务未因本次 PASS 被豁免。

## 4. Gate 决定

本次 Terra final4 closure-only 复审为 **PASS / open H/M/L=0/0/0**。该 PASS 仅关闭所列计划问题；是否解除 `IMPLEMENTATION FROZEN` 仍须由 Controller 按 target 所列 dual re-review / 状态同步 gate 裁决。本 artifact 不授权实现、测试执行、commit、push、PR 或 Gateflow。
