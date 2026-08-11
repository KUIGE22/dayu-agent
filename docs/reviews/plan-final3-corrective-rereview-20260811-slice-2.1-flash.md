# Plan Final3 Corrective Re-Review：Slice 2.1 durable job queue（DeepSeek Flash）

- **Gate**：final corrective plan re-review（FINAL3 / 独立 reviewer）
- **目标计划**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **基线**：`61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`（branch `codex/investment-platform`）
- **裁决输入**：`S21-CTRL-FINAL2-001..007`（`plan-controller-final-corrective-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`）与 `S21-CTRL-FINAL3-001..005`（`plan-controller-final-codegen-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`）
- **修复输入**：`docs/reviews/plan-fix-20260811-slice-2.1-final-contract-closure-terra.md`、`docs/reviews/plan-fix-20260811-slice-2.1-final-codegen-closure-terra.md`
- **结论**：**FAIL / OPEN H/M/L = 0/0/1**
- **本次写入**：仅本 artifact。未运行 pytest/pyright/Ruff/Docker/PG；未 commit/push/PR/live；未读本轮另一 reviewer（MiM）artifact；未读任何 production/test/README 之外的改动。

## 1. 方法与范围

逐项独立裁决 `S21-CTRL-FINAL2-001..007` 与 `S21-CTRL-FINAL3-001..005` 的修复落点，并对计划做
code-generation-readiness 复核。全部结论基于当前分支只读源码与目标计划全文：

- `tests/investment/test_architecture_boundaries.py:60-100,192-195`（`_PURE_FORBIDDEN_IMPORT_PREFIXES`
  与 `_INFRA_FORBIDDEN_IMPORT_PREFIXES`：`storage/**` 仍禁 `dayu.host` / `dayu.contracts` /
  `dayu.services` / `dayu.fins` 等，仅豁免 `sqlalchemy`/`psycopg`/`alembic`）
- `dayu/investment/storage/protocols.py:1-50`（现仅 import `dayu.investment.domain.*` 与标准库）
- `dayu/host/protocols.py:557`（`RunRegistryProtocol`，与计划 §3.1 引用的行号一致）
- `dayu/host/host.py:1075`（`get_run -> RunRecord | None`）；`dayu/host/host.py:792,816`（`cancel_run`/
  `cancel_run_and_settle`）；`dayu/host/executor.py:521,694,924,944`（四个 Agent entry 均 async）
- `dayu/contracts/run.py:23-77`（`RunState` 含 `UNSETTLED`，七个 terminal/active 状态齐全）；
  `dayu/contracts/run.py:102-143`（`RunRecord`：`run_id/session_id/service_type/scene_name/completed_at/
  metadata`）
- `dayu/contracts/agent_execution.py:167,188,282,329,388,448`（§7D fixture 五个类全部存在）
- master 计划 `docs/plans/2026-08-10-investment-platform-restoration.md:3752-3758`（Slice 2.1 五行）与
  `:3760-3765`（Slice 2.2 五行）；`git diff` 确认 master 五行已由旧
  `dayu/host/job_contracts.py`/`JobHandlerProtocol` 版本替换为新 owner 版本

## 2. S21-CTRL-FINAL2-001..007 逐项裁决（全部 CLOSED，无回归）

| Finding | 状态 | 独立证据 |
| --- | --- | --- |
| 001（High，owner 冲突） | **CLOSED** | §2 owner 表与 §3.2 把全部 job DTO/`JobStoreProtocol` 归 `dayu/investment/domain/jobs.py` + `dayu/investment/storage/protocols.py`，`JobService`/registry/reader 归 `dayu/services/job_service.py`；`storage/protocols.py` 现仅 import pure domain（源码 1-50 行），`postgres_jobs.py` 只依赖 domain+protocols；`_INFRA_FORBIDDEN_IMPORT_PREFIXES`（测试 93-95 行）继续拒绝 storage 对 `dayu.host`/`dayu.contracts` 的全部 import，无需窄豁免；§9 STOP 同步。 |
| 002（High，reconcile 缺 correlation lookup） | **CLOSED** | §3.2 `JobStoreProtocol` 新增精确 `get_agent_run_correlation(scope, correlation_id) -> AgentRunCorrelation`（:238,248）；`JobService.reconcile_agent_run_terminal(scope, correlation_id)` 固定四步：`get_agent_run_correlation` → `host_run_reader.get_run(reserved_host_run_id)` → Service 内 strict mapping → `store.reconcile_agent_run_terminal(scope, correlation_id, observation)`（:292）；每次 live/restart/replay 重读，无 cache。 |
| 003（Medium，deadline/correlation_missing 分支） | **CLOSED** | §4.2.3 heartbeat：`now >= deadline_at`（lease 仍有效）在同一事务把 attempt/job 收敛 `failed`、lease release reason=`deadline`、generic receipt `(failed,"deadline",deadline_exceeded,null)` + 一个 deadline event，然后抛 `JobDeadlineExceededError`，绝不返回 `JobClaim`；`now < deadline_at` 才 clamp 到 `min(now+lease, deadline)`，且要求严格晚于 now（§4.2.3）。`correlation_missing` 唯一生产返回点钉死为 `authorize_agent_run_start` → `INVARIANT_FAILURE + correlation_missing` + deduped event，其它 correlation 缺失一律 tenant-scoped `JobNotFoundError`（§4.1）。 |
| 004（Low，lease schema） | **CLOSED** | §5 `job_leases` 明定为 versioned mutable row：`created_at, updated_at DEFAULT transaction_timestamp(), version INTEGER NOT NULL DEFAULT 1`，`UNIQUE(tenant_id,attempt_id,fence)`，release 仅可从 `released_at/release_reason NULL` 以 CAS `version` 更新、不可改写；grant 列级 UPDATE 含 `updated_at, version`；`test_job_lease_single_release_versioned_cas_and_grant_matrix`（§7.2、§8:429）。 |
| 005（Low，UNSETTLED 映射） | **CLOSED** | §4.3.2 唯一映射：`HostRunObservationState.unsettled → CorrelationState.host_unsettled`、Host-origin receipt `outcome=failed`、`safe_error_code=host_run_unsettled`、action=`TERMINALIZED_FAILURE`，随后走与 Host failed 相同 retry policy；禁止写 `host_failed`/`host_run_failed`；`test_host_unsettled_maps_to_unsettled_state_code_and_failure_action`（§7.4、§8:421）。 |
| 006（High，generic receipt schema） | **CLOSED** | §3.2 定义 `GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME="dayu.job.generic-attempt-receipt"`/`VERSION=1`，exact canonical key 集合（按字典序 8 键），`result` 只可为 null 或含 `schema_name/schema_version/sha256` 的引用对象；builder 参数来源逐路径固定（complete/fail/cancel/deadline/lease-expired/retry-exhausted）；同 attempt 重放读既有 immutable row，绝不重建；§7.2 golden bytes/strict parse/DB roundtrip/duplicate-finalization 四个具名测试。 |
| 007（Medium，recover attempt state） | **CLOSED** | §3.2 `JobRecoveryResult` 不变量与 §4.2.7 对齐：handler `fail` retry → attempt=`failed`、receipt 非空、job=`ready`、next 非空；非取消 lease-expiry → attempt=`abandoned`、receipt 非空、job=`ready`；cancel-intent recover → attempt=`cancelled`、job=`cancelled`、next=None；deadline/耗尽 → job=`failed`、next=None，结果如实报告真实持久 attempt state（§3.2 行 173）；状态矩阵表（§4.2）同步。 |

## 3. S21-CTRL-FINAL3-001..005 逐项裁决（全部 CLOSED，无回归）

| Finding | 状态 | 独立证据 |
| --- | --- | --- |
| 001（Medium，broad recover 表达力） | **CLOSED** | §4.2.7 generic `recover` 的 SQL 以 `NOT EXISTS (SELECT 1 FROM agent_run_correlations ...)` 排除一切 correlation-attached attempt；新增 Store-only `recover_agent_run_after_no_host(scope, correlation_id, observation_sha256)`（§3.2:234-236、§4.2.8），同一 job-row serialization point、仅 current reserved + 持久 missing fingerprint 相等 + lease 过期 + 无更高 attempt/fence 才 mutate，其余 `None` 零 mutation；`JobService.recover` 固定 correlation-safe 顺序：sorted enumerate → 四步 reconcile → 仅 `NO_HOST_RUN` 走 targeted → 最后恰一次 generic；active/terminal/stale/invariant 不入 recover primitives（§3.2:292）；`test_future_recovery_reconciles_existing_correlation_before_generic_recover` 等 PG16 two-engine 测试锁定。 |
| 002（Low，complete cancel/deadline 顺序） | **CLOSED** | §4.2.4 固定判定顺序 `cancel intent → deadline → success`；cancel+deadline 同时成立必写 `(cancelled,"cancel_intent",cancelled,null)` receipt/event，不写 deadline/success；`test_complete_cancel_intent_precedes_deadline_and_success`（§8:412）。 |
| 003（Low，reserved ID validator owner） | **CLOSED** | §3.1 `RunRegistry.ensure_reserved_run` 是唯一 Host 侧格式校验 owner：在任何 `write_transaction()`/SQLite 写入前以 `run_` + 32 位小写 hex 严格校验，不合法即 `ValueError("invalid_reserved_run_id")` 零 side effect；executor/Host 只委托；`test_ensure_reserved_run_rejects_invalid_32_hex_before_sqlite_write`（§8:406）。 |
| 004（Low，ready deadline observation） | **CLOSED** | §4.2.2 claim 事务先把 deadline 已到的 ready job 置 job=`failed`、`safe_failure_code=deadline_exceeded`、仅一个 `job_deadline_exceeded` event、无 attempt/lease/receipt；非 ready 重放不追加 event；`test_ready_deadline_sets_exact_safe_failure_and_single_event_without_attempt`（§8:412）。 |
| 005（High，master 五行 drift） | **CLOSED** | `git diff` 证实 master Slice 2.1 五行（:3754-3758）已替换为 investment pure domain + storage protocol/store + services registry/reader + Host reserved identity 的高层链接，并链接到 target plan 取精确 allowlist/owner；`JobHandlerProtocol`、`dayu/host/job_contracts.py`、`dayu/host/job_service.py` 全文不再出现；master 五行与 target §2 五行（plan :51-57）语义一致。 |

## 4. 本轮专项核验

### 4.1 deadline 闭合（无 finding）

- enqueue：`deadline_at > available_at`（§3.2）；claim 仅选 `deadline_at > database_now` 的 ready job（§4.2.2）。
- claim 前 ready-deadline sweep：job=`failed`/`deadline_exceeded`/单 event/无 attempt（§4.2.2，FINAL3-004）。
- heartbeat：`now >= deadline_at` 即 terminalize + 抛 `JobDeadlineExceededError`；clamp `min(now+lease, deadline)` 且要求严格晚于 now，杜绝“expiry 已过去仍返回成功 claim”（§4.2.3）。
- complete：cancel→deadline→success 固定序（§4.2.4）。
- fail：retry 要求 `next_available_at < deadline_at`，否则终态 `failed`（§4.2.5）。
- recover：deadline 已到 → job=`failed`/`deadline_exceeded`；已耗尽 → `retry_exhausted`；receipt 终态 code 覆盖 `lease_expired` 时 reason 仍为 `lease_expired`（§4.2.7）。
- `authorize_agent_run_start` 要求 `clock_timestamp() < deadline_at` 才 `START_REQUIRED`（§4.3.1）；terminal reconcile 固定 cancel→deadline→Host outcome（§4.3.2）；HOST_ACTIVE_WAIT loop 以持久 `deadline_at` 为硬上界（§4.3, :348）。
- 状态矩阵表（§4.2）deadline 行与上述算法逐字一致；`JobLeaseHandle.expires_at > acquired_at` 不变量成立。
- 结论：FINAL2-003 与 FINAL3-002/004 的 deadline 语义在算法、矩阵、DTO 不变量与具名测试四层一致，无残余矛盾。

### 4.2 master 五行与 target 一致（无 finding）

- Allowed：master「investment pure domain（`dayu/investment/domain/jobs.py`）、storage protocol/store、
  `dayu/services/job_service.py` 的 registry/Host reader、Host reserved identity、migration/composition/
  init/tests 与对应文档；精确 allowlist 与 owner 见 target plan」——与 target §2 owner 表逐项对应，且 master
  明确链接 target 取精确性。
- API：master「enqueue/claim/heartbeat/complete/fail/cancel/recover；descriptor-only Service registry；
  Host reserved identity 与 `AgentRunCorrelation`；不定义 execution invocation protocol 或注册 handler」——
  与 target JobService 公共 11 方法（§3.2:252-268）、descriptor-only registry、无 handler 一致。
- Invariants：master「`FOR UPDATE SKIP LOCKED`、lease token fencing、attempt receipt、idempotency key；
  不 dual-write；缺 correlation 不补建；generic recover 仅处理 `NOT EXISTS correlation`；public Service
  recovery 以 correlation-safe query-before-retry orchestration 收敛」——与 target §4.1/§4.2.7/§3.2:292 逐字对应。
- Completion：master「PG job store 与 Service registry/Host reader 加入既有 platform provider；不启动
  scheduler/worker、不注册 handler；保持 Host 对 reserved Agent lifecycle 真源」——与 target §6 一致。
- Tests：master 列出的 two-worker race/expired lease/retry-backoff/cancel-before-while-run 与
  cancel→deadline→success/crash recovery/Host success-active-no-host reconciliation/correlation-safe
  targeted recover PG race/missing correlation 不补建/禁止双重模型执行/startup provider——与 §8 矩阵逐项对应。
- 结论：五行与 target 一致，无残余旧 owner/旧术语。

### 4.3 START_REQUIRED 跨 lease TOCTOU residual 与 Slice 2.2 owner（无 finding，1 条 observation）

- Residual 诚实披露：§4.3(:350) 与 §9(:438) 明确「已取得 `START_REQUIRED` 但在 Host `ensure_reserved_run`
  前长期暂停并跨过 lease expiry 时，存在跨 PG/Host store 的 read-to-entry TOCTOU；后续 safe recovery 可使
  job 前进，原 caller 仍可能进入其已授权 correlation」；slice 只保证「同一 correlation 的 Host ensure
  at-most-once」，绝不声称 distributed exactly-once。
- Owner 明确：§4.3(:348) 把 `HOST_ACTIVE_WAIT` 的 future owner 钉为 Slice 2.2 worker，要求显式正数
  `host_active_reobserve_interval_seconds` 重观测、以持久 `deadline_at` 为硬上界、到点停止 normal
  recovery/claim、向既有 Host lifecycle 发幂等 `cancel_run(reserved_host_run_id)`，并继续只重观测至
  Host terminal/unsettled；Host cancel 的发送去重/重试/治理 = Slice 2.2 worker/Host 明确 owner；Slice 2.1
  不注册该 worker、不投射 Host cancel。master Slice 2.2 Allowed（master :3762）含 `dayu/host/worker.py`，
  与该 owner 落点兼容，无矛盾。
- Observation（非阻塞）：master Slice 2.2 五行（:3760-3765）目前只覆盖 scheduler/worker/Redis 的
  schedule→enqueue→claim→handler→receipt 路径与其测试，尚未把「active re-observe loop / deadline 上界 /
  cancel delivery」写进 master Slice 2.2 的 Tests 五行；该契约目前只存在于 target §4.3 前向锁定段
  （:348,438）。由于 target 明示「本段只锁定其未来 owner、deadline 上界与禁止 retry 的契约」且不在本 slice
  实现，不构成 Slice 2.1 阻塞；建议在编写 Slice 2.2 target plan 时同步 master Slice 2.2 五行。

## 5. 本轮新 finding

### L-01（Low）§8 completion-gate 具名测试中有 16 个未登记进 §7 任一 slice 测试清单

**证据（直接行号）**：§8 矩阵（plan :404,405,406,412,418,421,425,426,427,428）要求以下具名测试存在，
但 §7.1-§7.5 的 slice 测试清单（plan :385-389）均未枚举它们（逐名 `rg` 全文件仅命中 §8 单行）：

- `test_disabled_definition_rejects_enqueue`（:404）→ 应归 §7.2(B)
- `test_claim_empty_returns_none`（:405）→ 应归 §7.3(C)
- `test_ensure_reserved_run_rejects_invalid_32_hex_before_sqlite_write`（:406）→ 应归 §7.1(A)
- `test_ready_deadline_sets_exact_safe_failure_and_single_event_without_attempt`（:412）→ 应归 §7.3(C)
- `test_complete_cancel_intent_precedes_deadline_and_success`（:412）→ 应归 §7.3(C)
- `test_reserved_missing_replay_has_no_duplicate_event`（:418）→ 应归 §7.4(D)
- `test_host_failed_or_unsettled_terminalizes_with_retry_policy`（:421）→ 应归 §7.4(D)
- `test_host_cancelled_terminalizes_cancel_receipt`（:421）→ 应归 §7.4(D)
- `test_correlation_identity_or_state_mismatch_is_invariant_failure`（:425）→ 应归 §7.4(D)
- `test_job_service_recover_returns_targeted_then_generic_results_in_stable_order`（:426）→ 应归 §7.4(D)
- `test_targeted_no_host_recovery_isolated_from_active_and_no_correlation_attempts`（:426）→ 应归 §7.4(D)
- `test_targeted_no_host_recovery_changed_observation_state_or_fence_is_zero_mutation`（:426）→ 应归 §7.4(D)
- `test_postgres_jobs_cross_tenant_reads_are_not_found_and_writes_denied`（:427,429）→ 应归 §7.3(C) 或 §7.5(E)
- `test_postgres_jobs_rls_setting_does_not_leak_between_transactions`（:427）→ 应归 §7.3(C) 或 §7.5(E)
- `test_0003_grant_matrix_exact`（:428）→ 应归 §7.2(B)
- `test_0003_upgrade_downgrade_upgrade_and_external_dependency_refusal`（:428）→ 应归 §7.2(B)

**为何是 finding 而非照抄即可**：§8 头（:395）明示「每个测试断言最终 job/attempt/correlation state、唯一
receipt、精确 event sequence、无 raw secret 和 Agent construction/model entry 次数。不得以「已由相邻测试
覆盖」替代任一条目」——即这些测试必须存在；但 §7 的 slice 清单是实施者逐 slice 的测试真源，16 个 gate 测试
没有任何 slice 认领，实施者按 slice 推进时会漏写，直到最终 gate 才暴露。属于计划内部测试清单不一致。

**最小修复**：把上述 16 个测试名分别补进对应 §7 slice 的 `Tests:` 清单（按上面「→ 应归」映射），不改任何
算法/契约/owner/状态机文本。

## 6. 其它 codegen-readiness 核验（无 finding）

- owner/DAG：§2 allowlist 与 §33「不修改 `dayu/investment/composition.py`、`dayu/startup/platform.py`、
  `dayu/contracts/protocols.py` 和架构守护」一致；`HostRunReaderProtocol` 定义于 `dayu/services/job_service.py`
  （§3.2:208）而非 contracts，storage 永不 import 它；DAG A→B→C→D→E→F 的依赖方向与
  `_INFRA_FORBIDDEN_IMPORT_PREFIXES` 兼容。
- public signatures：`JobStoreProtocol` 13 方法（§3.2:226-246）与文字枚举（:214）逐名一致；`JobService` 公共
  11 方法（:252-268）不含 `get_agent_run_correlation`/`recover_agent_run_after_no_host`，符合「不得暴露
  targeted method 为 public API」；`PostgresJobStore(session_factory=...)` 唯一构造参数（§6）。
- 状态机：§4.1 闭合转换与 §4.3.2 missing/active/first-terminalize/terminal-replay/stale-replay 分支一致；
  11 值 `AgentRunTerminalReconciliationAction` 与分支一一对应；`ALREADY_*`/`STALE_ATTEMPT` 重放语义闭合。
- PG16 named tests：§8 其余矩阵行均有 §7 对应具名测试；SQLite thread/process/reopen seam（:393）与 §7.1/§7.4
  的 crash 测试对应（`test_crash_after_claim_before_reserve_*`、
  `test_crash_after_reserve_before_future_host_call_*`、`test_crash_after_host_reserved_insert_before_model_*`）。
- stop conditions：§9 覆盖 reserved identity 塞 metadata、host protocols 承载 PG job DTO、error message/args
  泄漏 record、store 持有 registry、enqueue 绕过 gate、PG correlation commit 前调 Host、同步 reconcile 构造
  ExecutionContract、storage import host/contracts、cross-store transaction、correlation-attached attempt 进
  generic recover、targeted recovery 暴露 public、blind replay、RLS 用 fake、双 engine lifecycle owner、注册
  业务 handler 等全部红线。
- DTO/DDL：15 个 DTO 与 7 表 DDL 逐列对齐；`job_leases` versioned + CAS 单 release；receipts/events
  append-only；`agent_run_correlations` `UNIQUE(tenant_id,attempt_id)` + `UNIQUE(reserved_host_run_id)`；
  downgrade 先 catalog 查外部依赖 fail closed。

## 7. 结论

**FAIL（OPEN H/M/L = 0/0/1）**。

`S21-CTRL-FINAL2-001..007` 与 `S21-CTRL-FINAL3-001..005` 全部 CLOSED，无回归；deadline 四层一致、
master 五行与 target 一致、START_REQUIRED 跨 lease TOCTOU residual 诚实披露且 Slice 2.2 owner 明确；
其余 owner/DAG/signatures/状态机/stop/codegen 项均通过。唯一 open 项为 Low：§8 completion gate 的 16 个
具名测试未登记进 §7 任一 slice 测试清单（L-01）。按本计划 §9 与 Controller adjudication 的「open 必须归零
才能 accepted」，本计划需一次 bounded plan fix（仅补 §7 slice 测试清单），修复后可达 PASS。
