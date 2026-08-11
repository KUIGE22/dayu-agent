# Final Round-4 Closure Plan Re-review — Slice 2.2 Scheduler / Worker / Redis

## Scope

- **Mode**: final round-4 closure-only re-review
- **Target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`（709 行）
- **Target SHA256**: `65357054b7c70ce36d664ca30ec8f71e2f89dec23223a58b0802ea3457082079`（verified）
- **Controller fix**: `docs/reviews/plan-fix-20260812-slice-2.2-scheduler-worker-redis-codex.md`（129 行）
- **Controller fix SHA256**: `46cb02de08000553e9f04468f2eb1f4841ecc708350099badd0aa1bd915d5217`（verified）
- **Baseline**: `38ddad4`
- **Output file**: `docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-final4-mim.md`
- **Scope**: 仅核对 TERRA-S22-FINAL3-001 修复 + 前轮四项无回归 + 新 finding 扫描

## Conclusion

**PASS / open H/M/L = 0/0/0**

TERRA-S22-FINAL3-001 闭合，前轮四项无回归，未发现 blocking 新 finding。

---

## TERRA-S22-FINAL3-001 验证

**Controller fix §5 #26**：
> "Worker 所有 poll/heartbeat 治理调用精确经 `asyncio.to_thread` 传入 keyword-only `limit=settings.governance_page_size`，并把返回 `AgentRunGovernancePage.next_cursor` 立即写回唯一 process-local cursor；尾页 None 让下一次从头开始。新增非默认 page-size/cursor 轮转命名测试与 STOP，禁止默认 limit、双 cursor 或 storage page 泄漏。"

**§6.2 L385 新增文本**：
> "Worker 只维护一个 process-local governance cursor；每个 poll 周期在 claim 前、每个 correlated heartbeat 前后都以精确同步 gateway 调用 `await asyncio.to_thread(gateway.govern_agent_runs, scope, cursor, limit=settings.governance_page_size)` 取得 `AgentRunGovernancePage`，随后立即把同一 cursor 更新为 `page.next_cursor`；为 None 时下一次调用从头开始。所有调用都必须显式传 keyword-only limit，不得加默认值、分别维护 poll/heartbeat cursor、丢弃 next_cursor 或复用 storage projection page。"

**§10 L610 新增命名测试**：
- `test_worker_governance_uses_configured_keyword_only_page_limit_and_rotates_cursor`——覆盖非默认 page-size + cursor 轮转
- `test_governance_keyset_rotation_prevents_long_active_wait_from_starving_later_rows`——覆盖长期 ACTIVE_WAIT 不饿死后续行

**§12 L691 新增 STOP**：
- "Worker 调用 governance gateway 遗漏 keyword-only settings limit、未消费 page.next_cursor、为 poll/heartbeat 维护不同 cursor 或把 storage projection page 泄漏进 Host"

**验证**：
- keyword-only limit：显式传 `limit=settings.governance_page_size`，禁止默认值——正确
- cursor 轮转：唯一 process-local cursor，`page.next_cursor` 立即写回，None 时从头——正确
- 禁止双 cursor：poll 和 heartbeat 用同一 cursor——正确
- 禁止 storage page 泄漏：返回 `AgentRunGovernancePage`，不暴露 `AgentRunGovernanceProjectionPage`——正确（§6.2 L379 两层 page 明确区分）

**结论**: 闭合。

---

## 前轮四项无回归检查

### Intake Gate（§7.5 L449-453）

§3 L124 `dayu/host/process_intake.py` owner 保持；§6.2 L385 governance 调用经 `asyncio.to_thread`；§7.4 L434 scheduler tick 循环在 gate open 后执行；§7.5 L449-453 intake gate epoch 线性化点保持；§10 L625-628 三个 intake gate 命名测试保持；§12 L692 STOP 保持。无回归。

### Redis Runtime/Settings（§7.2 L400-412）

§7.2 L409 `POSTGRES_ONLY admission -> redis_runtime_state=None -> pure PG polling` 保持；L412 "运行逻辑必须读取 settings 而非硬编码；非默认合法值必须真实改变转换时机" 保持；§10 L632-634 三个 Redis 命名测试保持；§12 L693 STOP 保持。无回归。

### Host-local Port Signatures（§3 L124-126 + §6.1 L293-357）

§3 L147-152 dependency DAG 中 Host-local ports 描述保持；§6.1 L293-357 WorkerJobGatewayProtocol/SchedulerGatewayProtocol 保持；§6.1 L343-350 import guard + structural typing 保持；§10 L550-553 三个 port/import 命名测试保持；§12 L690 STOP 保持。无回归。

### Materialization already_enqueued 三态（§5.1 L214/216/235 + §5.3 L269-271）

§5.1 L214 `ScheduleMaterializationAction: enqueue, already_enqueued, skipped` 保持；L235 already_enqueued receipt=None + 零 side effect 保持；§5.3 L270 "materialize_occurrence 收到 begin_materialization(already_enqueued) 必须直接返回 ScheduleMaterializationResult(already_enqueued, occurrence, None)" 保持；§10 L567 命名测试保持；§12 L682 STOP 保持。无回归。

---

## Blocking-Only New Finding Scan

扫描 709 行 plan + 129 行 Controller fix，仅检查 blocking 新 finding：

- **TERRA-S22-FINAL3-001**: keyword-only limit + cursor 轮转 + 命名测试 + STOP。无 open。
- **Intake gate**: epoch 线性化 + 3 个命名测试 + STOP。无 open。
- **Redis runtime/settings**: mode/state 分离 + settings 驱动 + POSTGRES_ONLY 零 Redis + 3 个命名测试 + STOP。无 open。
- **Host-local ports**: Protocol 声明在 Host module + structural typing + import guard + 3 个命名测试 + STOP。无 open。
- **Materialization 三态**: already_enqueued 零 side effect + receipt=None + 1 个命名测试 + STOP。无 open。
- **Schema/DLL**: §5.3 DDL exact CHECK + FK/RLS/grants + 0004 migration owner。无 open。
- **State machines**: §7.3 Worker 7 状态 + §7.4 Scheduler 4 状态 + §6.2 Governance 10 action。无 open。
- **Lock ordering**: §6.2 L389 8 入口统一锁序 + READ COMMITTED 双 statement。无 open。
- **Drain**: §7.5 gate + epoch + drain_abandon_requested + WAITING_FOR_INNER_WORK + os._exit(1)。无 open。
- **CI**: §10 五条独立 pytest + workflow ignore + PG16/Redis digest。无 open。
- **Tests**: 99 个命名测试。无 open。
- **STOP conditions**: §12 19 条 STOP 与 plan 全文对齐。无 open。
- **Residual**: §13 7 项 residual 合理。无 open。

**未发现新 H/M/L finding。**

---

## Artifact Metadata

| Field | Value |
| --- | --- |
| Target SHA256 | `65357054b7c70ce36d664ca30ec8f71e2f89dec23223a58b0802ea3457082079` |
| Fix SHA256 | `46cb02de08000553e9f04468f2eb1f4841ecc708350099badd0aa1bd915d5217` |
| Baseline | `38ddad4` |
| Plan lines | 709 |
| Fix lines | 129 |
| Named tests | 99 |
| STOP conditions | 19 |
| TERRA-S22-FINAL3-001 | CLOSED |
| Prior 4 items | ALL NO REGRESSION |
| New H/M/L | 0/0/0 |
