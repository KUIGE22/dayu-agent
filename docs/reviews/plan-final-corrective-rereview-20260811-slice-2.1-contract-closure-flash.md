# Plan Final Corrective Re-Review：Slice 2.1 contract closure（DeepSeek Flash）

- **Gate**：final corrective plan re-review（独立 fallback reviewer）
- **Role**：reviewer-only；未实现、未修改任何 production/test/README/master-plan 文件
- **目标计划**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **基线**：`61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **裁决输入**：`docs/reviews/plan-controller-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`
- **修复输入**：`docs/reviews/plan-fix-20260811-slice-2.1-final-contract-closure-terra.md`
- **结论**：**FAIL / OPEN H/M/L = 2/1/2**
- **本次写入**：仅本 artifact。未执行 commit/push/PR/deploy/live/network/paid/Docker/PG；未读任何 `plan-final-corrective-rereview`、`plan-final-rereview-20260811-...-mimo` 或 Codex Spark mechanical audit artifact。

## 1. 方法与范围

逐项独立验证 S21-CTRL-FINAL-001..004 的修复落点，并对全计划做 code-generation-readiness 审计。所有结论基于当前分支 `codex/investment-platform` 只读源码：

- `tests/investment/test_architecture_boundaries.py:838-866`（`test_investment_never_imports_forbidden_modules`，AST 扫描全部 `dayu.investment` 文件）
- `tests/investment/test_architecture_boundaries.py:91-97`（infra forbidden set：`storage/**` 仍禁 `dayu.host` / `dayu.contracts` / `dayu.services` 等，仅豁免 SQLAlchemy/psycopg/alembic）
- `tests/investment/test_architecture_boundaries.py:193-195`（`storage/**` 命中 `_INFRA_FORBIDDEN_IMPORT_PREFIXES`）
- `dayu/investment/storage/protocols.py:1-45`（storage 协议真源只 import pure domain 与 stdlib；不在本 slice allowlist）
- `dayu/contracts/protocols.py`（跨层协议文件；本 slice 仅允许加 `HostRunReaderProtocol`）
- `dayu/contracts/run.py:23-46,101-143`（`RunState` / `RunRecord`；terminal/active 集合、`completed_at` 语义）
- `dayu/host/host_execution.py:24-100`（`HostExecutorProtocol`，四个 Agent entry）
- `dayu/host/executor.py:521,924,944,1429`（`DefaultHostExecutor.run_agent_stream`/`run_agent_and_wait*` 均为 async；`_start_run`）
- `dayu/host/host.py:195,611,647,683,705,1075`（`Host` 及四个委托 entry、`get_run -> RunRecord | None`）
- `dayu/host/run_registry.py:169-250`（`register_run`：`run_` + 12 hex；`write_transaction`）
- `dayu/host/host_store.py:44-61`（`runs` DDL：`run_id TEXT PRIMARY KEY`，无长度 CHECK）
- `dayu/services/startup_preparation.py:671-833`（provider admission → `build_platform_composition` → Host → recovery 的既有顺序）
- `dayu/startup/platform.py:39-73`、`dayu/investment/composition.py:59-120,273-392`（composition/provider/lifecycle 契约）
- `dayu/investment/domain/identifiers.py:270-322`（`TenantScope`，`tenant_id: TenantId`）
- `dayu/contracts/agent_execution.py:167,188,282,329,388,448`（D-fixture 五个类及字段，全部可照 plan §7D 逐字构造）
- `dayu/investment/storage/migrations/versions/0001_platform_foundation.py:37-38,154-165`、`0002_workspace_import.py:42-43`（rev 链 `None→0001→0002`，`organizations` 表存在）
- `dayu/cli/workspace_migrations/runner.py:38-80`、`platform_import.py`（init hook 形态）

## 2. S21-CTRL-FINAL-001..004 状态

| Finding | 状态 | 独立证据 |
| --- | --- | --- |
| 001（exact DTO schema） | **CLOSED** | §3.2 现给出 15 个 DTO 的逐字段/类型/默认值/不变量/嵌套表，两个 decision DTO 有完整代码块；§5 补齐 `worker_id`、receipt schema/version、`last_observation_sha256`；§7B/§8 命名测试 `test_all_fifteen_public_job_dtos_have_exact_fields_defaults_and_nesting`。15 个 DTO 计数与实际表一致；`AgentRunCorrelationObservation.sha256` 四业务值 fingerprint 与 §4.3.2 fingerprint 去重逻辑一致。 |
| 002（JobHandlerProtocol 占位） | **CLOSED** | §1/§3.2/§7B/§9 全部改为 descriptor-only；`JobHandlerProtocol` 全文不再出现（grep 确认），registry 仅 `register_descriptor`/`get_descriptor`，production registry 精确为空，非目标与 STOP 同步更新。 |
| 003（Host observation owner） | **CLOSED（reader seam）；新 seam 见 F-01/F-02** | `HostRunReaderProtocol` 落 `dayu/contracts/protocols.py`（改，已在 allowlist），只 import `RunRecord`；`JobService` 独占 mapping；`PostgresJobStore(session_factory=...)` 无 Host 参数（§6）；真实 `Host.get_run`（host.py:1075）结构满足协议。reader 注入方向无反向依赖问题。但本 finding 未覆盖「store 自身必须消费的 job DTO/协议住在哪一层」与「Service 如何取得 correlation 的 reserved_host_run_id」——见新 F-01、F-02。 |
| 004（重复 reconciliation 语义） | **CLOSED（重放语义）；调用 seam 见 F-02** | `last_observation_sha256` + 四类 `ALREADY_*` action + Terra closure 表（首次/第二结果、receipt/event 行为）+ PG16 two-engine/process-barrier 命名测试（terminal-first、recover-first stale、active repeat、observation transition）均已逐项规定；`job_events` 以 job-row counter 分配 sequence 防重复 event。 |

四项裁决均已在计划内闭合。下述新 finding 不属于 001..004 的直接覆盖范围，但同属「实现者不得自行选择跨层 ownership / DTO 位置 / 调用 seam」的 Controller 红线。

## 3. 新 material findings

### F-01（High）job DTO 与 JobStoreProtocol 的家无法被 `PostgresJobStore` 合法引用

计划把 15 个 job DTO、`JobStoreProtocol` 与 `JobHandlerRegistryProtocol` 全部放在 `dayu/host/job_contracts.py`（新）与 `dayu/host/protocols.py`（改）（§2 owner 表、§3.2）。但：

- 存储实现 `dayu/investment/storage/postgres_jobs.py`（§2，新）实现 `JobStoreProtocol` 且必须构造/返回 `JobEnqueueReceipt`/`JobClaim`/`AgentRunCorrelation` 等 DTO，运行时必然 `import dayu.host.job_contracts` / `dayu.host.protocols`；
- 既有架构守护 `tests/investment/test_architecture_boundaries.py:838-866` 对 `storage/**` 应用 `_INFRA_FORBIDDEN_IMPORT_PREFIXES`（:93-97，含 `dayu.host`、`dayu.contracts`），AST 层 `_collect_forbidden_imports`（:214-243）连 `if TYPE_CHECKING:` 内的 import 一并命中；该测试文件**不在** slice 2.1 allowlist，worker 不得修改；
- 计划自身 §9 STOP 明确「`PostgresJobStore` 被要求 import `dayu.host` … 立即 STOP」；§3.2 只声明「storage 不 import 该协议」——但该句仅指 `HostRunReaderProtocol`，不能覆盖 store 对 job DTO/协议的必需引用；
- 其余候选家（`dayu/investment/storage/protocols.py`、`dayu/investment/domain/` 新模块、`dayu/contracts/` 新文件）全部不在 allowlist，任何迁移都触发「未列文件须停报」；且 `storage/**` 同样禁 import `dayu.contracts`，contracts 也不是可行家。

结论：计划文本同时要求「DTO 住 dayu.host」与「store 不得 import dayu.host」，且每条合法解法都需要 allowlist 之外的改动或直接违反既有守护。实现者无法不发明依赖位置而开工。这是 S21-CTRL-FINAL-003 同类（storage 不得拥有/引用 Host 访问）在「store 自身类型消费」面上的复现，未被修复文本覆盖。

### F-02（High）`JobService.reconcile_agent_run_terminal(scope, correlation_id)` 无法取得 correlation 的 `reserved_host_run_id`

§4.3.2 规定 Service「先以 correlation 的 `reserved_host_run_id` 调 injected `HostRunReaderProtocol.get_run`」，但公共 Service 签名只接收 `(scope, correlation_id)`（§3.2），且 `JobStoreProtocol` 的精确 10 方法清单（§3.2/§4.3）没有任何「按 correlation_id 取 correlation」的方法：

- `list_expired_agent_run_correlations` 只返回已过期且仍 leased/cancel_requested 的 correlation（§4.3）；
- `reserve_agent_run_correlation` / `authorize_agent_run_start` 都要求 lease token；
- `recover` 是 generic 路径，不返回 correlation；
- `JobService` 被定位为无状态 delegate（「持有 reader，执行 get_run 和上表唯一 mapping 后调用 store terminal signature」），无 cache；
- `reserved_host_run_id = run_{attempt_id.hex}` 依赖 attempt_id，Service 仅有 correlation_id（UUID），无法推导。

结论：§4.3.2 的调用流程无法在给定签名 + 给定 store 协议下执行。实现者必须发明一个未列 store 方法（如 `get_agent_run_correlation(scope, correlation_id)`）或改写已固定 Service 签名——两者都属于计划未裁决的公共契约选择。`test_future_recovery_reconciles_existing_correlation_before_generic_recover` 正走这条断链。

### F-03（Medium）两个已列稳定错误/安全码没有定义抛出或返回点

- `JobDeadlineExceededError`（§6 稳定错误清单）全文无抛出点：§4.2.3 heartbeat 的 0-row 分支只规定 `JobLeaseLostError`/`JobStateConflictError`；§4.2.4 complete 对 deadline 是「收敛 failed receipt」而非抛错。且 §4.2.3「延长不得越过 deadline」在 `now >= deadline_at`（lease 仍有效）时的 UPDATE clamp 语义未定义——若按 `LEAST(now+lease, deadline)` 执行会把 expiry 钳到过去时间再返回「成功」。
- `correlation_missing`（`SafeJobErrorCode`，§3.2）没有返回点：§4.1 定义了 missing-correlation 窗口并禁止据此重建，但未把任何 decision action / safe code 钉到该场景（`authorize_agent_run_start` 遇缺 correlation 行、reconcile 前提不满足时分别返回什么，未规定）。

### F-04（Low）§5 表级规则与 `job_leases` 列清单自相矛盾

§5 总则「mutable row 有 `updated_at DEFAULT transaction_timestamp()` 与正 `version`；append-only row 只有 `created_at`」，但 `job_leases` 含可变列 `released_at`/`release_reason`（grant 清单也允许 app 列级 UPDATE 这两列）却没有 `updated_at`/`version`。按「未列字段不得发明」，列清单应胜出，但总则句文本错误，worker 必须自行判断取舍。

### F-05（Low）Host UNSETTLED 终态化的 correlation state / safe code 未钉死

§4.3.2 首次 terminalize：「Host failed/unsettled 以既有 retry algorithm 写 failed receipt、state/event」，未规定 correlation state 写 `host_unsettled` 还是 `host_failed`，也未规定 receipt/decision 的 safe code 用 `host_run_unsettled` 还是 `host_run_failed`（§4.1 转换表两者都存在）。`AgentRunCorrelationObservation` 映射对 UNSETTLED 的处理也未在 §3.2 表中明确。

## 4. 已验证为 code-generation-ready 的部分（无 finding）

- **reserved identity**：`RunRegistryProtocol.ensure_reserved_run` 增补、SQLite 单 `write_transaction` + `INSERT OR IGNORE`→`SELECT`→identity compare 路径与现有 `write_transaction`（`dayu/host/run_registry.py:201`）/`runs` DDL 兼容；`runs.run_id` 无长度 CHECK（host_store.py:44-61），32-hex 与 12-hex 共存无需改 schema；`run_agent_stream`/`run_agent_and_wait*` 确为 async（executor.py:521/924/944），同步 JobService 无法调用；Host 四委托入口齐备（host.py:611/647/683/705）。
- **canonical document**：UTF-8/无 BOM/字典序/拒 float/敏感键递归拒绝/64-hex sha 的规则完整；§3.2 与 `test_canonical_document_rejects_each_known_sensitive_key` 对应。
- **DTO/DDL/action/state 一致性**：15 DTO 与 7 表 DDL 逐列对齐；`JobRecoveryResult.next_available_at ↔ job_runs.available_at`、attempt/fence 正、`UNIQUE(tenant_id,attempt_id)`、`UNIQUE(reserved_host_run_id)`、event sequence 用 locked-row counter（§4.2 与 §5）均一致；`AgentRunTerminalReconciliationAction` 11 值与 §4.3.2 分支一一对应。
- **PG clock 权威**：全部 lease/deadline/backoff/event/observation 由 `transaction_timestamp()`/`clock_timestamp()` 取，caller 时间全部删除；unit fake clock 只模拟 store DB clock。
- **RLS/grants/downgrade**：7 表单 RLS policy、列级 UPDATE 精确清单、`job_definitions` identity 等不可 UPDATE、无 DELETE/TRUNCATE/DDL、downgrade 先 catalog 查外部依赖 fail closed、`platform_jobs` 只经既有 bootstrap admission 调 Alembic `upgrade head`——与既有 `0001/0002` 风格及 `runner.py` hook 形态兼容。
- **composition/lifecycle**：两阶段拆分与 `PreparedHostRuntimeDependencies.close()`/`_OwnedLifecycleRegistration` exact-once 语义兼容；`PlatformServiceProtocol.platform_service_name`（composition.py:69-72）与 provider mapping `{"investment_identity", "durable_jobs"}` 契约一致；`PostgresJobStore` 唯一构造参数 `session_factory`。
- **D-fixture 可构造**：§7D 五个符号（agent_execution.py:167/188/282/329/388/448）与字段（`session_key`/`resumable`/`user_message`/`model_name`）逐字可构造。
- **allowlist 完整性**：新增/修改文件均在下表；未发现 future-slice import、handler 注册或 `dayu/investment/composition.py`/`dayu/startup/platform.py` 修改要求。

## 5. Observations（非阻塞）

- §6 把 `build_platform_composition` 从「Host/Fins 副作用之前」移到「Host 构造后、startup recovery 前」，与 `dayu/services/startup_preparation.py` 模块 docstring 既有契约「组合提供者自身抛出的异常原样传播，且必发生在任何 Host / Fins 副作用之前」相悖；计划 §6 已明确新语义（Host 已构造但不暴露、不做 recovery、不额外 close SQLite state），属有意的 bounded 变更，worker 需同步该 docstring（文件在 allowlist 内）。
- `JobHandlerRegistry` 具体类（§6 构造）的声明文件未点名，但按 §3.2 语境可推导为 `job_contracts.py`，不构成发明。
- `ensure_reserved_run` 的 INSERT 必须补齐 `runs` 表 NOT NULL 列（`created_at`/`state`/`owner_pid`，host_store.py:44-61），计划未枚举，但可由既有 `register_run`（run_registry.py:188-198）直接推导，不构成发明。

## 6. 结论

FAIL。S21-CTRL-FINAL-001..004 均已闭合，但新发现两个 High（F-01：job DTO/协议家在 dayu.host，与既有架构守护及计划自身 STOP 直接冲突；F-02：terminal-only reconciliation 的 Service 入口无法取得 `reserved_host_run_id`，给定 store 协议无取回方法）、一个 Medium（F-03：`JobDeadlineExceededError`/`correlation_missing` 无抛出/返回点，heartbeat-deadline 边缘未定义）与两个 Low（F-04、F-05）。按「pass 要求 open 0」，本计划不满足 implementation gate，需 Controller 裁决并做 bounded plan fix（涉及 DTO/协议家与 reconciliation 调用 seam 两个公共契约选择）。
