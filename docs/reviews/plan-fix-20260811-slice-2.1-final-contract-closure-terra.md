# Plan Fix：Slice 2.1 final contract closure（Terra）

- **Gate**：corrective plan-fix
- **目标计划**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **基线**：`61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **裁决输入**：`docs/reviews/plan-controller-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`
- **状态**：`S21-CTRL-FINAL-001..004 FIXED / AWAITING CORRECTIVE DUAL PLAN RE-REVIEW`
- **本次写入**：仅目标计划与本 artifact；production、tests、README、master plan、既有 artifacts 均未改动。

## 动机复核与架构结论

四项 Medium finding 均成立。原计划把 DTO shape、handler invocation、Host observation
owner 和重复 reconciliation 的公共返回语义留给实现者推导；DDL、行锁或 UNIQUE 约束只能
限制部分存储结果，不能替代跨层公开契约。

直接源码证据为：`RunRecord`/`RunState` 已由 `dayu.contracts.run` 持有；跨层 protocol 的
既有 owner 是 `dayu.contracts.protocols`；`Host.get_run()` 与
`RunRegistryProtocol.get_run()` 都已返回 `RunRecord | None`；当前
`dayu.investment.storage` 不依赖 `dayu.host`；`Host` 在
`prepare_host_runtime_dependencies()` 内于 platform provider admission 后构造。

修复保持 Host SQLite run 的生命周期真源与 PostgreSQL durable job 真源分离：Host reader
仅注入 `JobService`，由它映射 observation；`PostgresJobStore` 仅消费已脱敏、强类型的
observation，绝不 import/read Host。为保持 Phase 1 的 fail-fast admission，唯一 engine
probe 仍在 Host/Fins 构造前；新增 durable-job service 的纯内存 wiring 在 Host 构造后、
startup recovery 前完成。这是 Slice 2.1 allowlist 内的 bounded composition addition，未改变
Phase 1 identity service、engine lifecycle 或 Host/PG owner 边界。

## Accepted finding closure

| Finding | 修复落点 | 精确 closure |
| --- | --- | --- |
| `S21-CTRL-FINAL-001` | plan §3.2、§5、§7B、§8 | 明确 15 个（原文误称 14）public DTO 的字段顺序、类型、无默认值规则、可空性、嵌套关系与不变量；并补 `worker_id`、receipt schema/version 和 observation fingerprint 对应 DDL。 |
| `S21-CTRL-FINAL-002` | plan §1、§3.2、§7B、§9 | 选择 descriptor-only：无 `JobHandlerProtocol`、无 invocation signature。registry 仅有精确的 `register_descriptor` / `get_descriptor`；production registry 为空，后续 execution protocol 归 Slice 2.2。 |
| `S21-CTRL-FINAL-003` | plan §2、§3.2、§4.3、§6–§8 | 在 `dayu/contracts/protocols.py` 增 `HostRunReaderProtocol.get_run`；`JobService` constructor 注入 reader 并独占 `RunRecord | None → AgentRunCorrelationObservation` mapping；store terminal signature 强制接收 observation。`PostgresJobStore(session_factory=...)` 没有 Host 参数；真实 `Host` 在 bounded composition stage 注入 JobService。 |
| `S21-CTRL-FINAL-004` | plan §3.2、§4.3、§5、§7D、§8 | 增加 `last_observation_sha256` 和四类 `ALREADY_*` action；首次 terminal/stale/active/missing 观察与同 fingerprint replay 的 receipt、event、state、return action 全部精确规定。terminal replay 返回已提交 immutable receipt；stale replay 返回 `ALREADY_STALE_ATTEMPT`；active repeat 返回 `HOST_ACTIVE_WAIT` 且不写 event。 |

## 关键 contract

`AgentRunCorrelationObservation` 不带 caller clock、raw Host error 或 metadata。missing 精确映射为
reserved run ID + `host_state=None`；存在 run 必须 ID 一致，terminal `completed_at` 必须是
aware UTC。其 canonical-safe SHA-256 是 PostgreSQL 去重 observation transition/event 的唯一
比较键，PG 的 `clock_timestamp()` 仍是持久化 `observed_at` 的权威。

重复 terminal reconcile 的 public action 已闭合：

| 第一结果 | 同 observation 的第二结果 | receipt/event |
| --- | --- | --- |
| `TERMINALIZED_SUCCESS/FAILURE/CANCEL` | 对应 `ALREADY_TERMINALIZED_*` | 复用同一 immutable receipt；零 UPDATE、零新 event |
| `STALE_ATTEMPT` | `ALREADY_STALE_ATTEMPT` | 无 receipt；零 UPDATE、零新 event |
| `HOST_ACTIVE_WAIT` | `HOST_ACTIVE_WAIT` | 无 receipt；零 UPDATE、零新 event；Host state 改变才写一次 transition |
| `NO_HOST_RUN` | `NO_HOST_RUN` | 无 receipt；零 UPDATE、零新 event |
| `INVARIANT_FAILURE` | `INVARIANT_FAILURE` | 无 receipt；相同 fingerprint 零新 event |

新增的 PG16 two-engine/process-barrier tests 精确锁定 terminal-first replay、recover-first
stale replay、active repeat 与 active→terminal observation transition；均断言 receipt bytes/hash
复用和 event sequence 未递增。

## 验证与范围审计

未运行 pytest、pyright、coverage、Ruff、PG16/Docker 或任何生产动作（本 gate 仅允许文档检查）。
已完成：当前源码 path/owner/signature read-only 核对、目标计划与 artifact path allowlist 核对、
工作树范围核对、`git diff --check`、目标文本中旧 handler/store-reader/test-name 交叉检索。

## Open questions 与 residual owner

没有阻塞性 open question。后续仍由 Slice 2.2 拥有 worker polling、active-host reobserve、
deadline bounded Host cancel delivery、Redis degradation 及任何 execution protocol；Slice 2.3
拥有业务 payload schema、source health、notification；未来 Agent handler/connector owner
拥有外部 provider/tool exactly-once。双路 corrective re-review 与 Controller adjudication 仍是
implementation 前唯一放行条件。
