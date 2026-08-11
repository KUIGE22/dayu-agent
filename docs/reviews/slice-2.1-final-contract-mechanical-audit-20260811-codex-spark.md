# ADVISORY SNAPSHOT / SUPERSEDED / NOT GATE EVIDENCE
# 本文件仅保留历史机械审计记录，不可作为实现依据。
# 目标实现已由以下 acceptance 目标覆盖，请以其为准；冲突处一律不执行本文件结论：
# - [accepted target plan](docs/plans/2026-08-11-slice-2.1-durable-job-queue.md)
# - [accepted target acceptance](docs/reviews/plan-acceptance-20260811-slice-2.1-durable-job-queue-codex.md)

# Slice 2.1 Durable Job Queue
## 机械证据审计（Codex Spark）

> 约束重置：当前是 pre-implementation plan gate，baseline 不存在不算缺口；只审计目标计划内部是否闭合。
> 缺口仅在计划文本本身要求实现者自行发明未列出方法、schema、数据源或状态语义时判定。

### 1. 审计对象与证据集
- 目标计划：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- Controller/plan-fix 修正上下文：`docs/reviews/plan-controller-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`、`docs/reviews/plan-fix-20260811-slice-2.1-final-contract-closure-terra.md`
- 变更 owner/allowlist 依据源码：
  - `dayu/host/protocols.py:557`（`RunRegistryProtocol` 当前现有方法集合）
  - `dayu/host/host_execution.py:40-100`（`HostExecutorProtocol` 当前现有方法集合）
  - `dayu/services/startup_preparation.py:300-365`（当前仅返回 `{"investment_identity": service}`）
  - `dayu/investment/composition.py:60`（`PlatformServiceProtocol` 的最小 property 约束）

### 2. Public 公共方法闭环审计（Service / Store）

#### 2.1 JobService 公共方法

| Service method（public） | 输入参数来源与 canonical 来源定义 | Service→Store 边界 | Store 输出/receipt/event 归因 | 重启后 correlation / Host run 恢复边 | Plan 命名测试/DDL | plan 状态 |
|---|---|---|---|---|---|---|
| `enqueue(scope: TenantScope, request: JobEnqueueRequest) -> JobEnqueueReceipt` | `scope` 为上游 Service 调用者 tenant 上下文，`request` 为 DTO：`JobEnqueueRequest` 字段在 plan 102 与 DDL 结合定义；`tenant_id` 源于 `TenantScope`。同 key 同 fingerprint 幂等边界定义为 `(tenant_id, job_type, idempotency_key)` 且 fingerprint 覆盖 descriptor 全字段 + payload schema/name/version/sha256 + available/deadline（§4.2 step1）。 | 直接委托到 `JobStoreProtocol.enqueue`（plan 133-136）。 | 产出 `JobEnqueueReceipt`（字段 103）并持久化 `job_runs` / `job_definitions` + `job_events`。`job_runs` DDL 明确 identity/index/fingerprint 列（§5）。 | 重启时不涉及 correlation；重试以 job-level 幂等和已持久化 fingerprint 判定（同 key 不同 fingerprint -> 冲突错误）。 | `test_enqueue_same_scope_key_same_fingerprint_is_idempotent`、`test_enqueue_same_key_different_fingerprint_conflicts`、`test_0003_schema_exact_contract`（§7-B/§8） | closed（计划完整） |
| `claim(scope, worker_id) -> JobClaim | None` | `worker_id` 输入明文由调用者提供；`scope` 来自 tenant 上下文（§4.2 claim）。 | 直接委托 `JobStoreProtocol.claim`。 | 返回 `JobClaim`（表 105）包含 `JobLeaseHandle`；持久化 `job_runs/job_attempts/job_leases/job_events`（§5）。 | 再次 claim 后恢复由 stored lease 与 attempt state 控制；claim 之后故障但未 reserve 时属于预期 incomplete window，由 `recover` 处理。 | `test_claim_two_workers_only_one_receives_job`、`test_two_writers_allocate_distinct_per_job_event_sequences`（§7-C/§8） | closed（计划完整） |
| `heartbeat(scope, lease) -> JobClaim` | `lease` 全部字段来自前序 claim；token 校验与 host-like clock 来源计划明确：不接受 caller wall-clock，PG 为权威（§4.2 heartbeat）。 | 直接委托 `JobStoreProtocol.heartbeat`。 | 仅更新租约状态与 heartbeat；`job_events` 用 `job_runs.next_event_sequence` 分配序列。 | 无 correlation 回退；若 lease 失效则抛 `JobLeaseLostError`，避免误续约，重启后不恢复 stale lease。 | `test_stale_heartbeat_complete_and_fence...`（§7-C） | closed |
| `complete(scope, lease, completion) -> JobAttemptReceipt` | `completion` = `JobCompletion` DTO（plan DTO 表明字段，含 result/receipt schema）；`lease` 作为授权条件；`scope` 为 tenant；`clock` 与 `deadline` 由 PG。 | 直接委托 `JobStoreProtocol.complete`。 | 产出 `JobAttemptReceipt`（109）；写 `job_attempt_receipts` + transition events（`job_events`）并更新 job/attempt/correlation 状态。 | `complete` 不直接读 Host；重启情况下若调用失败可由重试策略/`recover` + 冲突约束控制是否允许进入。 | `test_missing_expired_or_wrong_lease_never_authorizes_start`、`test_completion_deadline_precedes_success`（§7-C/§8） | closed |
| `fail(scope, lease, failure) -> JobRecoveryResult` | `failure` 由 DTO `JobFailure`（107）定义；`lease` 为当前 attempt 授权；`scope` tenant。 | 直接委托 `JobStoreProtocol.fail`。 | 产出 `JobFailure` 驱动 retry/cancel_outcome；persist 到 `job_runs` `job_attempts` `job_leases` `job_attempt_receipts`（§4.2 fail；§5）。 | 若 attempt 过期/fence 变更，不可重写；失败重试生成新 attempt/fence，失败后可触发 stale recovery。 | `test_recover_expired_lease_never_revives_attempt`、`test_stale_heartbeat_complete_and_fail_are_fenced`（§7-C） | closed |
| `cancel(scope, request) -> JobRecoveryResult` | `request` 源 `JobCancellationRequest`（108）；`scope` tenant；`reason` 规范化为非空脱敏文本。 | 直接委托 `JobStoreProtocol.cancel`。 | no-attempt 分支写无 receipt（`job_runs` 直接 terminal + event）；有 attempt 分支可产生 attempt receipt（plan 6）。 | 无 correlation 时走本地 job recovery，不触发 Host ；这与 `NO_HOST_RUN` 场景分离。 | `test_ready_cancel_writes_no_attempt_receipt`、`test_cancel_while_leased_blocks_success`（§7-C） | closed |
| `recover(scope) -> tuple[JobRecoveryResult, ...]` | `scope` 为 tenant；recover 调度仅对无 correlation 或 `NO_HOST_RUN` 的过期 lease 入口；调用顺序由 §4.3 给定。 | 直接委托 `JobStoreProtocol.recover`。 | 根据 `job_runs/job_attempts` 及 lease 过期写入 `job_events`；无 Host 读路径。 | 只对无 correlation 或 `NO_HOST_RUN` 的 correlation 进行 recover；Plan 明确“`future recovery` 先 terminal reconcile 后再 generic recover”。 | `test_terminal_reconcile_wins_before_recover`、`test_recover_wins_terminal_reconcile_is_stale...`（§7-D/§8） | closed |
| `reserve_agent_run_correlation(scope, lease) -> AgentRunCorrelation` | `lease` 来自 claim；`scope` tenant；reserved ID 推导 `run_{attempt_id.hex}`（§3.1）。 | 与 `JobStoreProtocol.reserve_agent_run_correlation` 对接。 | 持久化 `agent_run_correlations`，插入 `(tenant_id,attempt_id,reserved_host_run_id,idempotency_key,state)`；同 attempt 逐字段 immutability compare，冲突为 invariant。 | 重启时 correlation 持久行与 attempt/job fence 共同决定 stale/replay。 | `test_correlation_is_committed_before_start_authorization`、`test_crash_after_claim_before_reserve_recovers_without_host_side_effect`（§7-D） | closed |
| `list_expired_agent_run_correlations(scope) -> tuple[AgentRunCorrelation, ...]` | `scope` tenant；筛选条件计划为仍 leased/cancel_requested 且 lease 过期的 correlation（§4.3）。 | 与 `JobStoreProtocol.list_expired_agent_run_correlations` 对接。 | 不直接写状态；返回 correlation 列表供外部 recovery loop。 | 恢复时为 recovery orchestrator 输入点；后续每条只读映射+terminal reconcile。 | `test_future_recovery_reconciles_existing_correlation_before_generic_recover`（§7-D） | closed |
| `authorize_agent_run_start(scope, lease, correlation_id) -> AgentRunStartAuthorizationDecision` | 输入来自 claim/recovery state：`lease`（当前 lease hash/fence）、`correlation_id`（reserved row）。 | 调用 `JobStoreProtocol.authorize_agent_run_start`，不读 Host。 | 决策仅为 `START_REQUIRED/WAIT/...` 与 `safe_error_code`；不产生命令级 receipt。 | 决策前提要求 correlation 仍绑定当前 attempt，且 token/fence/deadline 正常；返回 `START_REQUIRED` 前提是 Host entry 仍可继续走 reserved path。 | `test_start_required_requires_current_raw_lease`（§7-D） | closed |
| `reconcile_agent_run_terminal(scope, correlation_id) -> AgentRunTerminalReconciliationDecision` | 输入仅 `scope+correlation_id`；Service 必须通过注入的 `HostRunReaderProtocol.get_run(correlation.reserved_host_run_id)` 先拉取 `RunRecord | None`，映射为 `AgentRunCorrelationObservation`（§3.2、§4.3）。 | 映射后调用 `JobStoreProtocol.reconcile_agent_run_terminal(scope, correlation_id, observation)`；不会把 reader/RunRecord 传入 store。 | Store 在 pg tx 内产生命令化 `JobAttemptReceipt`/`JobRecoveryResult`（同 action）、`job_events`，并承诺 terminal replay 与 stale replay 的零 rewrite / 零重复 event。 | 重启与重放规则在 §4.3 明确：`NO_HOST_RUN`/`HOST_ACTIVE_WAIT`/`STALE_ATTEMPT`/`ALREADY_*` 决定的 idempotent 重放；`future recovery` 以此入口优先于 generic recover。 | `test_terminal_reconciliation_replay_returns_existing_receipt_without_event`、`test_recover_stale_reconciliation_replay_returns_already_stale_without_event`、`test_host_transition_between_reconciliation_observations_terminalizes_once`（§7-D/§8） | closed |

#### 2.2 JobStoreProtocol 公共方法

| Store method（public） | 输入来源 | 输出/receipt/event 定义 | 持久化列/表 | 重启/观测关系（Host） | Plan DDL/测试闭合 | plan 状态 |
|---|---|---|---|---|---|---|
| `enqueue(scope, request)` | 来自 Service 层，`request` 已通过 DTO/descriptor 校验（§3.2/§4.2） | `JobEnqueueReceipt`（tenant_id/definition_id/job_id/state/idempotency_reused）；`state=ready`；`idempotency_reused` 标记重放 | `job_runs`（`definition_id`/`idempotency_key`/`payload_*`/`state`）、`job_definitions`（descriptor 行）、`job_events`（初始事件） | 无 Host 依赖 | `test_0003_schema_exact_contract`、`test_enqueue_same_scope_key_same_fingerprint_is_idempotent`（§7-B） | closed |
| `claim(scope, worker_id)` | 来自 caller；`scope` tenant；`clock` 用 PG transaction/clock timestamp（§4.2） | `JobClaim`（含 lease） | `job_runs` / `job_attempts` / `job_leases` / `job_events`（行锁+序列化计数） | Host 无关 | `test_claim_empty_returns_none`、`test_claim_two_workers_only_one_receives_job`（§8） | closed |
| `heartbeat(scope, lease)` | 仅接受 `JobLeaseHandle` | `JobClaim` 重签结果 | `job_attempts.job_lease_expires_at` / `last_heartbeat_at` / `job_events` | Host 无关 | `test_stale_heartbeat_complete_and_fail_are_fenced`（§7-C） | closed |
| `complete(scope, lease, completion)` | 由 lease + completion | `JobAttemptReceipt`，failed/cancelled/succeeded 分支；result/receipt hash 校验 | `job_attempt_receipts`（UNIQUE tenant,attempt） + `job_attempts` + `job_events` | Host 无关；Host 成功由 terminal reconcile 负责 | `test_completion_deadline_precedes_success`（§8） | closed |
| `fail(scope, lease, failure)` | 由 lease + failure（safe code） | `JobRecoveryResult`；可继续 ready/retry 或 terminal | 同 complete + attempt/job 状态退化字段 + event counter | Host 无关；`Host failed` 分支仅在 reconcile 路径 | `test_retry_backoff_and_deadline_are_closed`（§8） | closed |
| `cancel(scope, request)` | 由 request：`job_id` + reason（脱敏） | `JobRecoveryResult`；可无 attempt receipt 分支 | `job_runs` state/event；有 attempt 时写 receipt | Host 无关，`reconcile` 决定 host_cancel 归因 | `test_ready_cancel_writes_no_attempt_receipt`、`test_cancel_while_leased_blocks_success`（§8） | closed |
| `recover(scope)` | scope tenant；筛选过期 attempt/window | `tuple[JobRecoveryResult, ...]` | `job_runs` / `job_attempts` / `job_leases` / `job_events` | 仅处理非 correlation 的过期 attempt；correlation 已有则先进行 terminal reconcile | `test_recover_expired_lease_never_revives_attempt`（§8） | closed |
| `reserve_agent_run_correlation(scope, lease)` | lease→attempt/job/fence+token；idempotency key 和 reserved run id 来自 lease/attempt | `AgentRunCorrelation`（含 `reserved_host_run_id`） | `agent_run_correlations`（`UNIQUE(reserved_host_run_id)`，`UNIQUE(tenant_id, attempt_id)`）+ event | Host run 不在此 txn 读取；与 transaction 2 commit 确保 restart-safe pre-host gap | `test_crash_after_reserve_before_future_host_call_reuses_same_reserved_id`（§7-D） | closed |
| `list_expired_agent_run_correlations(scope)` | tenant tenant 的过期 lease+active correlation 条件查询 | tuple of `AgentRunCorrelation` | `agent_run_correlations` + `job_attempts`（校验 lease/j状态） | 为 recovery orchestrator 输出供 terminal reconcile | `test_future_recovery_reconciles_existing_correlation_before_generic_recover`（§7-D） | closed |
| `authorize_agent_run_start(scope, lease, correlation_id)` | lease+correlation_id；PG authoritative state 做匹配 | `AgentRunStartAuthorizationDecision`（action 不含 raw token） | `job_runs/job_attempts/job_leases/agent_run_correlations`（状态锁） | 与 Host 先隔离：此 API 仅本地授权，Host reserved path 在 service层决定是否 entry | `test_missing_expired_or_wrong_lease_never_authorizes_start`（§8） | closed |
| `reconcile_agent_run_terminal(scope, correlation_id, observation)` | scope+correlation_id+`AgentRunCorrelationObservation`（来自 Service 映射） | `AgentRunTerminalReconciliationDecision`（含 terminal/stale/action、receipt 可复用） | `job_runs`, `job_attempts`, `agent_run_correlations`, `job_attempt_receipts`, `job_events` | Host 观测通过 Service 已标准化；Store 只消费 observation，不读 Host，保证隔离 | `test_terminal_reconciliation_replay_returns_existing_receipt_without_event`、`test_recover_stale_reconciliation_replay_returns_already_stale_without_event`（§8） | closed |

#### 2.3 Host reserved API 与调用协作（与 JobService/Store 的交界）

| 公共边/方法 | 计划证据 | 输入数据源 | 观察/receipt 归属 | 重启重放 | 计划闭环 | 缺口判定 |
|---|---|---|---|---|---|---|
| `RunRegistryProtocol.ensure_reserved_run`（`ReservedRunEnsureResult`） | §3.1；`ReservedRunEnsureResult` 与 `ReservedAgentRunExistsError` 定义；`run_id` 同步规则 32 hex | `reserved_run_id` 由 `attempt_id.hex` 组成；`session_id`、`service_type`、`scene_name`、`metadata` 来自调用侧（ExecutionContract） | 成功返回新 run 的 `RunRecord`；失败返回 `created=False` + record | 写入成功与否是 `reconcile` 前提；`created=False` 不允许再次建模 | `test_ensure_reserved_run_concurrent_same_identity_returns_one_created`、`test_reserved_agent_run_existing_never_builds_agent`（§7-A） | closed |
| HostExecutor reserved entry（`run_agent_stream` / `run_prepared_turn_stream` / `run_agent_and_wait` / `run_agent_and_wait_replayable` + keyword-only `reserved_run_id`） | §3.1 明确 patch 目标与行为（created=True 才启动）；`replay_agent_and_wait` 不扩展 | reserved_id 由 `reserve_agent_run_correlation` 产物注入 | `ReservedAgentRunExistsError` 防止 duplicate model entry；仅 created 时 start | 重启/重复调用由 store decision + reserved run ID 判重保障；`created=False` 即恢复/查询 | `test_reserved_agent_run_existing_outcome_carries_record`（§7-A） | closed |
| `HostRunReaderProtocol.get_run -> AgentRunCorrelationObservation` 映射 | §3.2 引入、fix §1 强制 Service mapping | source: Host `RunRecord | None` by `reserved_host_run_id` 查询 | mapping 在 Service 内生成 observation 的 canonical SHA256 与缺失/terminal规则 | 重启后 recovery/reconcile 每次重新 get_run，再映射 observation，靠 `last_observation_sha256` 做 dedupe/replay 语义 | `test_job_service_maps_host_run_or_missing_to_exact_observation`（§7-D/§8） | closed |

### 3. 重复调用/去重与 restart-safety 交叉闭环

#### 3.1 重放语义（plan-internal 已闭合）

| 场景 | 计划内规则 | named tests | plan 状态 |
|---|---|---|---|
| 首次 terminal，重复同 observation | 返回 `ALREADY_TERMINALIZED_*`；复用同一 immutable receipt；零 UPDATE、零新 event（fix §1） | `test_terminal_reconciliation_replay_returns_existing_receipt_without_event` | closed |
| stale replay 重复 | 首次 `STALE_ATTEMPT`，后续 `ALREADY_STALE_ATTEMPT`；零 UPDATE、零新 event；只记录 observation | `test_newer_attempt_stale_correlation_only_records_safe_observation`、`test_recover_stale...already_stale` | closed |
| active 重复 | `HOST_ACTIVE_WAIT` 并可 dedupe 相同 fingerprint；状态与 attempt 不变 | `test_active_reconciliation_repeat_has_no_event_until_host_transition` | closed |
| missing 重复 | `NO_HOST_RUN` 重放不 UPDATE、不重放 event | `test_reserved_missing_replay_has_no_duplicate_event`（§8） | closed |
| invariant 重复 | `INVARIANT_FAILURE` 重复时不重放 event | `test_observed_host_disappearance_is_invariant_failure`、`test_correlation_identity_or_state_mismatch_is_invariant_failure` | closed |

#### 3.2 restart-safe correlation/Host run 回收路径

| 复原目标 | 计划依据 | 数据边界 | 结论 |
|---|---|---|---|
| Claim 成功、reserve 前崩溃 | §4.3（claim 与 reserve 分离、不同 txn）+ §4.1 correlation_missing 定义 | 无 correlation；只恢复未提交 attempt，不能读 Host | 规则闭合：`recover` 处理无 correlation 的过期 attempt | closed |
| Reserve 成功、Host call 前崩溃 | §4.3 + §7-D crash tests | 已持久化 correlation，Host run 缺失时 `NO_HOST_RUN` 并可重用 reserved id | closed |
| Host inserted 但模型未执行完 | §4.2 + §4.3 + stop list | Host 行已存在且 `reconcile` 使用 observation map 决策；只允许一次 model entry + 再入场需 created=False 处理 | closed |
| Future recovery 顺序 | §4.3 明确：`list_expired... -> terminal reconcile -> NO_HOST_RUN 才 generic recover` | 分层顺序决定，不直接调用 recover before terminal | closed |

### 4. 计划内部剩余缺口（仅真正缺口）

- 无：在计划文本与其纠偏后（`plan-fix`）中，所有 public JobService/JobStore/Host reserved/public APIs、DTO/observation 映射、状态机动作、重放语义、DDL 与 named tests 已闭合，未见计划要求实现者自行发明的新方法、schema 或状态语义。

### 5. 计划与源码 owner/allowlist 可行性（只作可行性审计）

- 计划允许在 `dayu/host` 新增 `job_contracts.py` 与 `job_service.py`、在 `dayu/contracts/protocols.py` 新增 `HostRunReaderProtocol`（计划 §2，fix §1）。
- 当前源码确认 `PlatformServiceProtocol` 仅要求 `platform_service_name`，适配 `durable_jobs` 注入不冲突（`dayu/investment/composition.py:60`）。
- 当前源码 `startup_preparation` 现阶段仅返回 `investment_identity`（`dayu/services/startup_preparation.py:352-361`），与计划 §6. 依赖顺序不同，但这是 pre-implementation 与实现偏差，不作为 plan-internal 缺口；对 allowlist 可行性提示为“当前待扩展”。
- 当前源码 `RunRegistryProtocol`/`HostExecutorProtocol` 尚未出现新增 reserved APIs（`dayu/host/protocols.py:557`、`dayu/host/host_execution.py:40`），属于计划待实现工作面，不作为当前任务缺口。
