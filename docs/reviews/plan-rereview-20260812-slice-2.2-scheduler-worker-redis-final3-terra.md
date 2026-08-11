# Slice 2.2 Scheduler / Worker / Redis — Terra final3 closure-only 独立复审

- **复审时间**：2026-08-12 02:56:38 CST。
- **结论**：**FAIL**。
- **开放 finding**：`H/M/L = 0/1/0`。
- **代码基线**：`38ddad489f4f9cfa1ae2a4373d69a628e49578bf`。
- **锁定 target**：`docs/plans/2026-08-12-slice-2.2-scheduler-worker-redis.md`，SHA-256 `d71eced3e4e58f6e3ffa875a2699a425a700b7ba2552267072c10ed7113eaa87`（已实测一致）。
- **锁定 Controller fix**：`docs/reviews/plan-fix-20260812-slice-2.2-scheduler-worker-redis-codex.md`，SHA-256 `b913591e8b4f3fcec13e8bedd382036f6fb2fe25f1d751c5465b22c3d4b0cab9`（已实测一致）。
- **此前 Terra final review**：`docs/reviews/plan-rereview-20260812-slice-2.2-scheduler-worker-redis-final-terra.md`，SHA-256 `9185e36fbd6294407adff98453d27e56439de62b539f2ce626a46cb80cda9d10`（已完整重读）。
- **审阅边界**：完整重读根 `AGENTS.md`、上述三份 artifact/计划及与分层约束直接相关的当前 Host、架构守卫和 Job receipt 基线。只读；未修改 target、master、fix、source、tests、README、依赖或 CI；未运行 pytest、pyright、Ruff、Docker、PostgreSQL、Redis、broker、模型或 live action；未 commit、push 或启动 Gateflow。

## 1. 结论先行

`TERRA-S22-FINAL-001`、`TERRA-S22-FINAL-002`、Host-local gateway 的**分层与签名定义**、以及 `M-NEW-001` 的 materialization terminal-race 三态均已在计划合同中闭合。此前 final review 的两个 M 不再开放。

但本轮 blocking-only 扫描发现 `WorkerJobGatewayProtocol.govern_agent_runs` 的精确签名与 Worker 调用文本直接矛盾：协议要求必填 keyword-only `limit`，调用却没有传入，且没有把返回页的 cursor 写回。该矛盾会使计划自身的 strict typing 合同不可实现，并会让 `governance_page_size` / keyset rotation 的真源被实现者猜测。因此维持 **FAIL / IMPLEMENTATION FROZEN**，直至该唯一 M 以最小 plan erratum 闭合。

## 2. 指定 closure 逐项复证

| 项目 | 结论 | 直接证据 |
| --- | --- | --- |
| `TERRA-S22-FINAL-001` intake epoch | **CLOSED** | Controller fix `114` 已接受该修正。target `449–451` 将 `ProcessIntakeGate` / `IntakeEpoch` 固定为 event-loop-owned closed surface；所有可能返回新 work 的 await/to_thread 都在派发前 capture、返回后且启动下一工作前同时重验 `is_open` 与 `is_current`。gate 后返回的 claim 不启动 handler/heartbeat/terminal，replay/list/reservation 不启动 materialization；仅 gate 前已派发的一个 Service-owned materialization 可完整收口。`625–627` 列出三个 barrier 命名测试，`690` 将回归列为 STOP。 |
| `TERRA-S22-FINAL-002` Redis runtime / settings / `POSTGRES_ONLY` | **CLOSED** | target `165–194` 固定 `PlatformQueueSettings`、正值校验与默认 `3/30`；`401–412` 将 profile-derived `PlatformQueueMode` 与 Worker-owned 两态 `RedisRuntimeState` 分离，转换逐字读取 settings。`POSTGRES_ONLY` 的 state、publisher、subscriber、client 全为 `None`，且禁止 construct/ping/subscribe/resubscribe/recover。`488–494` 固定 typed admission 和 exact-once close，`631–635` 与 `691` 锁定非默认参数、PG-only 零 Redis 和 STOP。 |
| Host-local gateway exact signatures / 分层 | **CLOSED（定义与分层）** | target `293–350` 给出 Worker/Scheduler ports 的逐方法类型、唯一 async 边界、pure-domain 返回值和 structural assignment；`352–357` 明确 Scheduler 只见 Service-owned 高层 replay/reserve/materialize，不能取得 Store facade。`159` 禁止 Host worker/scheduler import Service、concrete PostgreSQL store 或业务模块；现有架构守卫 `tests/architecture/test_dependency_boundaries.py:97–123` 已禁止 Host import `dayu.services`，而 allowlist `131` 允许在新的 worker/scheduler unit tests 固化其余 AST 边界。当前发现的**调用点签名矛盾**另列为本次唯一 M，不改变该分层 closure 判断。 |
| `M-NEW-001` materialization terminal-race 三态 | **CLOSED** | target `211–216` 定义 occurrence、decision 和 result 的 closed action；`233–235` 规定 terminal loser 的 `already_enqueued` 必须 `receipt=None`、持久 job id 非空且零 JobService/Redis/mark。`269–273` 禁止 terminal read-back、伪造 receipt 和裸 unique violation；`371–373` 令 PENDING availability 只在 materializing 前可否决，committed replay 用 typed persisted decision、immutable snapshot、同一 PG idempotency 真源和 mark 时再次锁内重验。`567` 是专门 race 测试，`681` 是 STOP。 |

## 3. 开放 finding

### TERRA-S22-FINAL3-001 — governance gateway 调用违背自身 exact Protocol，page limit/cursor 消费未闭合（中）

**直接证据**：

1. target `319–325` 将 `WorkerJobGatewayProtocol.govern_agent_runs` 精确定义为 `govern_agent_runs(scope, cursor, *, limit: int) -> AgentRunGovernancePage`；`limit` 是必填 keyword-only 参数。
2. target `381` 要求 limit 精确来自 `settings.governance_page_size`，Worker 每 poll 处理一页、保存 process-local cursor，并在 `next_cursor=None` 后从头轮转，以避免长期 `ACTIVE_WAIT` 饿死后续行。
3. target `385` 却只写 Worker 调用 `govern_agent_runs(scope, cursor)`。这按同一计划的 Protocol 不能通过类型检查；文本也没有要求接收 `AgentRunGovernancePage.next_cursor` 并写回 Worker cursor。

**影响**：实现者若按 `385` 落地会立即违反 exact signature；若自行补默认 limit 或自行猜测 cursor 归零时机，则 `governance_page_size` 不再是配置真源，keyset rotation 也没有可验证的调用级合同。它直接触及 active/cancel/deadline governance 的分页公平性，属于 implementation-blocking M，而非文案瑕疵。

**最小计划修复**：

1. 在 target §6.2 `385` 明确所有该调用均为同步 gateway 经 `asyncio.to_thread` 的精确调用：`await asyncio.to_thread(gateway.govern_agent_runs, scope, cursor, limit=settings.governance_page_size)`。
2. 明确 Worker 接收返回的 `AgentRunGovernancePage` 后立即将 process-local cursor 更新为 `page.next_cursor`；为 `None` 时按 `381` 的既有规则在下一次调用从头开始。该规则必须同时适用于 poll claim 前和 correlated heartbeat 前后调用，不能各自维护 cursor 或复用 storage page。
3. 在已允许的 `tests/application/test_platform_worker.py` 增加命名测试，例如 `test_worker_governance_uses_configured_keyword_only_page_limit_and_rotates_cursor`：使用非默认 page size，断言 keyword-only `limit`、page `next_cursor` 轮转与尾页归零；保留现有 `test_governance_keyset_rotation_prevents_long_active_wait_from_starving_later_rows` 的跨页公平性验证。

## 4. blocking-only 扫描与残余风险

- 除 `TERRA-S22-FINAL3-001` 外，未发现新的 H、M 或 L。特别是 materializing 不引入 lease 并非缺口：immutable snapshot、atomic idempotent enqueue、mark 同 job 重放和 terminal loser 的无 receipt 结果已形成单一真源闭环。
- 现有通用 architecture guard 尚未逐一枚举 concrete store/business module 前缀，但这不构成 allowlist 阻断：target 已允许新增 `tests/application/test_platform_worker.py` 与 `test_platform_scheduler.py` 来为 `159` 的更窄边界写静态断言；无需修改 allowlist 外文件。
- 本 artifact 只证明计划合同；不会替代后续 implementation、pyright、真实 PG16/Redis/SIGTERM lanes 或 code review。Redis hint 的丢失/重复/乱序仍由既定 PG claim/fence 真源吸收，代价是 poll 延迟。

## 5. Gate 决定

在 `TERRA-S22-FINAL3-001` 完成最小 plan erratum、重新锁定 target/fix，并取得新的独立 re-review `PASS / open H/M/L=0/0/0` 前：

- 保持 `IMPLEMENTATION FROZEN`；
- 不得启动 Flash implementation、修改 production/tests/README/dependency/CI，或将此前 closure 视为实现验收；
- 不得 commit、push、开 PR 或启动 Gateflow review。
