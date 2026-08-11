# Slice 2.1 Durable Job Queue — Plan Handoff Blocker

- **状态**：`CANDIDATE / AWAITING DUAL PLAN REVIEW`
- **原定状态**：`STOP / BLOCKED BEFORE CANDIDATE`（已由 Controller 裁决解除）
- **基线**：`61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`（Phase 1 accepted）
- **结论**：原 blocker 已由 Controller 接受并以窄的 Host external-run identity contract 关闭；已生成对应 candidate plan。该契约只保证同一 correlation 在本地 Host 不会重复进入模型，不承诺外部模型供应商或工具副作用的 exactly-once。

## 已读取的真源与库存裁决

本 handoff 在写入前已完整读取 `AGENTS.md`、master restoration plan 的全局架构、状态机、Phase 1、Slice 2.1、validation 和 stop 条款、Phase 1 acceptance、当前 `dayu.host` / `dayu.investment` / `dayu.startup` 源码与相关测试，以及 Spark inventory `docs/reviews/slice-2.1-architecture-inventory-20260811-codex-spark.md`。

| Spark inventory 部分 | 裁决 | 对本 STOP 的影响 |
| --- | --- | --- |
| §2 Host run / session / pending / outbox / lane / recovery | 接受其 SQLite owner、取消、lease 与启动恢复边界；更正一个非决定性描述：现有 `RunRegistry` 没有 `upsert_run` 或 `cancel_run`，公开创建入口是 `register_run()`。 | 证明 Host 是独立真源，不能把 PG attempt 当作 Host run 的替身。 |
| §3 transaction owner | 接受 owner 三元组和 stale-owner 约束。 | 不提供跨 SQLite/PG 的统一 correlation identity。 |
| §4 PG composition / migration | 接受严格 schema、显式 `TenantScope`、RLS 和 Alembic 真源。 | 不能用 PG transaction 覆盖 Host SQLite 注册。 |
| §5 startup / close | 接受 provider 生命周期必须 exact-once。 | 不是本 blocker 的修复点；不能借 startup best-effort 把运行时重复执行降级。 |
| §6 tests | 接受既有并发、lease、idempotency、recovery 测试可作模式参考。 | 当前没有覆盖跨 store 的“Host 已创建、关联未写”故障窗口。 |
| §7 call graph / 文件盘点 | 接受 queue、PG repository、composition/startup 是预期 owner。 | 盘点未包含使 Host 接受预分配 run identity 所必需的 `run_registry.py`、`executor.py`、`host_execution.py` 等 owner。 |
| §8 correlation gap | **接受并升级为 blocker**。其中“可用 run_id 回查”的前提只在调用方已经持有该 ID 时成立。 | 当前调用方在 Host 创建前没有可持久化且可重放的 Host run ID。 |
| §9 must-stop | 接受禁止 dual-write、compat wrapper、无 owner lease 和反向依赖。 | 推荐修复不使用跨库事务或兼容层。 |

## 阻塞 finding

### S21-STOP-001-未修复-[严重]-Host run identity 无法在跨库崩溃前持久化

- **位置**：master §6.1 的 Host/PG owner 与 Agent crash reconciliation（第 960–964 行），Slice 2.1 API/invariants/tests（第 3754–3758 行）；当前 `dayu.host.run_registry.SQLiteRunRegistry.register_run()`（第 169–222 行）与 `dayu.host.executor.DefaultHostExecutor`。
- **问题类型**：状态机漏洞 / 并发恢复风险 / 不可直接实施。
- **主纲要要求**：Agent attempt 必须保存 immutable `AgentRunCorrelation(tenant_id, job_run_id, attempt_id, host_run_id, idempotency_key)`；恢复必须 query-before-retry；missing correlation 可安全重建；并且不得 PG+Host dual-write、不得双重模型执行。
- **直接证据**：
  - `SQLiteRunRegistry.register_run()` 无 caller-supplied identity 参数，在 SQLite transaction 内生成 `run_{uuid}`（`dayu/host/run_registry.py:169-222`）。
  - `HostExecutorProtocol` 的各 Agent/direct-operation 入口未接收预分配 run ID（`dayu/host/host_execution.py:28-90`）；默认 executor 随后自行调用 `register_run()`（`dayu/host/executor.py:437-446`、`1031-1039`）。
  - 当前 Service 可见查询仅以已经知道的 `run_id` 读取，或以 session/state/service_type 枚举（`dayu/host/protocols.py:1332-1360`）；没有按 durable correlation/idempotency key 精确查找的稳定 Host 协议。将业务 correlation 塞入 Host metadata 既违反“显式参数不得进 extra payload”，也没有唯一约束或可验证的 idempotent create 语义。
- **可复现失败时序**：
  1. PG worker 已 `claim` attempt A，持有 lease/fencing token。
  2. Agent handler 调 Host；Host 在 SQLite 成功注册并开始 Host run H（可能已经产生模型侧副作用），但 H 的随机 ID 只存在于该进程。
  3. 进程在 handler 将 H 插入 PG `AgentRunCorrelation` 前崩溃。
  4. PG recovery 只看见 attempt A 缺少 correlation。它既不知道 H 的 ID，也不能从 Host 侧精确检索 H；若依主纲要“missing correlation 且无 external receipt 可新建 run”，会创建 H2，导致模型执行两次。若拒绝重建，则 attempt 永远无法判定，违背 durable recovery。
- **影响**：任何 SQL schema、`SKIP LOCKED`、lease fencing、attempt receipt 或测试 fake 都无法弥合该跨 store 的 identity loss。实施者只能在“盲目重放”与“永久卡死”之间二选一，违反 master 的明示不变量；这满足 master §11 “schema 无法表达真实 owner 状态/需要发明第二真源”的 stop 条件。
- **禁止的伪修复**：
  - PG 与 Host SQLite 的分布式事务、双写或把 Host run 复制到 PG；
  - 通过扫描 `list_runs()`、时间窗、session、service type 或日志猜测 H；这些都不能证明唯一性；
  - 把 correlation/idempotency key 藏入 metadata/extra payload、用 `getattr`/兼容 wrapper 绕过现有契约；
  - 把“模型调用通常幂等”作为证明。现有 Agent 调用没有该外部副作用幂等保证。

## 已裁决的解除方案（Controller decision）

Controller 已授权把下列 **Host external-run identity contract** 纳入 Slice 2.1 allowlist，并新增 `dayu/host/run_registry.py`、`dayu/host/executor.py`、`dayu/host/host.py` 与 application tests。它是本 slice 的第一实施子片，不是兼容层或跨库事务。

1. Host 在 Service→Host 稳定边界显式接收一个预分配、严格校验的 `host_run_id`（或等价 `external_run_key`），禁止经 metadata 传递；相应扩展 `HostedRunSpec`、`HostExecutorProtocol`、`RunRegistryProtocol`、`DefaultHostExecutor` 和 `SQLiteRunRegistry`。这需要把上述 owner 文件与其测试加入 allowed set。
2. `register_run` 对相同外部 identity 只允许“完全同一 immutable run specification”的幂等返回；任何字段不一致 fail closed。Host run ID 必须是 PG correlation 先持久化的 UUID/确定性值，而不是 Host 内部随机生成值。
3. Agent attempt 固定顺序改为：PG transaction 创建 attempt A 与 immutable correlation（含预分配 H）→ 提交 → 调 Host 以 H 注册/执行 → PG 仅补 receipt。该顺序没有跨库事务：PG 崩溃前无 Host 副作用；PG 提交后、Host 调用前可按 H 安全重试；Host 成功注册后、PG receipt 前可按 H query-before-retry。
4. Host 必须新增精确查询与取消能力，只按此显式 identity 返回一个 run；`succeeded` 只允许补 PG receipt，`created/queued/running` 只等待或投射 cancel，`failed/cancelled/unsettled` 才由 PG retry policy 决定新 attempt。原 attempt 的 H 永不替换。
5. 该 predecessor 的真实 SQLite fault-injection tests 必须在四个 cut point kill/reopen 进程：PG correlation commit 前、commit 后 Host 调用前、Host SQLite register commit 后但 PG receipt 前、Host terminal 后但 PG receipt 前；逐一断言一个 correlation identity 最多创建一个 Host run，且没有第二次模型调用。通过后，Slice 2.1 再补真实 PG16 的 lease/claim/retry/RLS 并发测试。

## 已关闭 finding 与残余归属

| 已关闭项 / 残余风险 | 归属 |
| --- | --- |
| Controller 已裁决 external-run identity，candidate plan 将公开契约、allowed files、故障注入与验收证据写死。 | Controller / master plan owner |
| Host predecessor 在 Slice 2.1 首片以真实 SQLite crash-window tests 验收；不可用 fake 或时序猜测替代。 | Host owner |
| 外部 provider / 工具不具 exactly-once 语义；本 slice 只保证单个 correlation 不会二次进入本地 Host 模型执行。任何将来外部 side effect 必须自带 provider idempotency key。 | 后续 Agent handler / connector owner |
| PG 是 job 真源、Host SQLite 是 run 真源；无 dual-write、无 Redis/API/UI/业务 handler 仍是 hard boundary。 | Controller / architecture owner |

S21-STOP-001 已从 blocker 转为已裁决风险。后续双路 plan review 必须验证候选计划是否确实把 PG-first correlation、reserved ensure 与所有 crash cut point 连成闭环。
