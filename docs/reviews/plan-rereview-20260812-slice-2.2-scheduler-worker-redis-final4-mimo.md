# Slice 2.2 Scheduler / Worker / Redis — MiMo Final4 Closure Plan Re-Review

- **Status**: PASS / open H/M/L=0/0/0
- **Reviewer**: MiMo (final4 closure)
- **Target**: `docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md` (SHA256 `65357054...2079`)
- **Fix**: `docs/reviews/plan-fix-20260812-...-codex.md` (SHA256 `46cb02de...5217`)
- **Scope**: TERRA-S22-FINAL3-001 fix verification + prior四轮无回归确认

## 0. Verdict

**PASS.** TERRA-S22-FINAL3-001 正确闭合，prior 四轮（intake/Redis/ports/materialization）无回归，无 blocking 新 finding。

## 1. TERRA-S22-FINAL3-001 Fix Verification

### 1.1 Keyword-only settings limit

§6.2 line 385: Worker 以精确同步 gateway 调用 `await asyncio.to_thread(gateway.govern_agent_runs, scope, cursor, limit=settings.governance_page_size)`。`limit` 为 keyword-only，值来自 `settings.governance_page_size`（§4.1 默认 100）。

"所有调用都必须显式传keyword-only limit，不得加默认值、分别维护poll/heartbeat cursor、丢弃next_cursor或复用storage projection page"。

**闭合**: `limit` 是 keyword-only 参数，无默认值，值来自 frozen settings。禁止默认 limit。

### 1.2 唯一 cursor 消费 next_cursor/None 轮转

§6.2 line 385: "Worker只维护一个process-local governance cursor；每个poll周期在claim前、每个correlated heartbeat前后...立即把同一cursor更新为`page.next_cursor`；为None时下一次调用从头开始"。

§6.2 line 381: "Worker每poll处理一页并保存process-local cursor，到尾部`next_cursor=None`后从头开始；长期ACTIVE_WAIT不能把后续deadline/terminal饿死，重启从头只是重复观察而不改变PG"。

§6.2 line 379: storage 返回 `AgentRunGovernanceProjectionPage(projections, next_cursor)`，JobService 返回 `AgentRunGovernancePage(results, next_cursor)`，两层 page 不得混用。

**闭合**: 唯一 process-local cursor，poll/heartbeat 共享同一 cursor，next_cursor=None 时从头开始，两层 page 类型分离。

### 1.3 Tests

- `test_worker_governance_uses_configured_keyword_only_page_limit_and_rotates_cursor`（line 610）：验证 keyword-only limit + cursor 轮转。
- `test_governance_keyset_rotation_prevents_long_active_wait_from_starving_later_rows`（line 609）：验证 keyset 分页防止 ACTIVE_WAIT 饿死后续行。

### 1.4 STOP

line 691: "Worker调用governance gateway遗漏keyword-only settings limit、未消费page.next_cursor、为poll/heartbeat维护不同cursor或把storage projection page泄漏进Host"。

**闭合**: STOP 精确覆盖四种违规：遗漏 limit、未消费 next_cursor、双 cursor、storage page 泄漏。

## 2. Prior Rounds Regression

- **Intake gate**: §7.5 `ProcessIntakeGate` epoch 递增线性化，gate 后返回的 to_thread 因 `is_current(captured)` 失败。不变。
- **Redis runtime/settings**: `PlatformQueueMode` vs `RedisRuntimeState` 分离，POSTGRES_ONLY 不构造 Redis 对象，REDIS 读取 settings。不变。
- **Host-local ports**: `WorkerJobGatewayProtocol`/`SchedulerGatewayProtocol` 在 Host 模块声明，返回值只有 pure closed types，Host 不知道 `dayu.services`。不变。
- **Materialization already_enqueued 三态**: `ScheduleMaterializationAction` 与 `ScheduleMaterializationResultAction` 分离，`already_enqueued` receipt=None 零 JobService/Redis/mark。不变。

新增命名测试 `test_valid_lease_missing_host_stops_renewal_then_expiry_allows_targeted_recovery`（line 618）补充 MISSING_HOST_WAIT 停止续租→expiry→targeted recovery 全路径。与 prior round 一致。

## 3. Blocking 新 Finding 扫描

无 blocking 新 finding。TERRA-S22-FINAL3-001 的 keyword-only limit、唯一 cursor 轮转、两层 page 分离、STOP 覆盖均已完整闭合。

## 4. Final Verdict

**PASS / open H/M/L=0/0/0.** Plan 可进入 accepted baseline commit。
