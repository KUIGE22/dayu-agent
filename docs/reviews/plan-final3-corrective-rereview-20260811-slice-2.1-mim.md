# Final3 Corrective Re-review：Slice 2.1 durable job queue

- **Gate**：final3 corrective dual plan re-review
- **Branch / baseline**：`codex/investment-platform` / `61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Target**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Scope**：独立 adversarial 核验 FINAL2-001..007 无回归，逐项核验 FINAL3-001..005，逐字比较 master Slice2.1 五行与 target
- **Valid prior reviews**：
  - `docs/reviews/plan-controller-final-codegen-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`（Controller，OPEN H/M/L = 1/1/3）
  - `docs/reviews/plan-fix-20260811-slice-2.1-final-codegen-closure-terra.md`（Terra fix，FINAL3 全部 CLOSED）
  - `docs/reviews/plan-final-codegen-rereview-20260811-slice-2.1-mim.md`（MiM prior，PASS open 0/0/0）
- **Review-integrity**：本 review 独立于 Terra fix 与任何另一 reviewer 的本轮新产物。仅读取：AGENTS.md、master plan Phase2/Slice2.1（`:3750-3758`）、target plan（全文）、Controller final codegen adjudication、Terra fix、MiM prior review、architecture guard source。
- **External actions**：未执行 commit、push、PR、deploy、live、paid、Docker、PostgreSQL、tests、pyright、ruff 或任何实现动作。

## 1. Master vs Target 逐字比较

Controller 要求本轮必须逐字比较 master Slice2.1 五行与 target 的七个维度。以下逐行核验：

### 1.1 owner

- **Master :3754**："investment pure domain（`dayu/investment/domain/jobs.py`）、storage protocol/store、`dayu/services/job_service.py` 的 registry/Host reader、Host reserved identity"
- **Target §2 owner 表**：`dayu/investment/domain/jobs.py`（pure domain）、`dayu/investment/storage/protocols.py`（storage protocol）、`dayu/services/job_service.py`（Service/registry/reader）、`dayu/host/protocols.py` 等（Host reserved identity）
- **Verdict**：**MATCH**。master 正确反映 target 的四层 owner 结构，旧 master 的 `dayu/host/job_contracts.py`、`dayu/host/job_service.py`、`dayu/investment/composition.py`、`dayu/startup/platform.py` 已移除。

### 1.2 allowlist

- **Master :3754**："精确 allowlist 与 owner 见 [Slice 2.1 target plan](2026-08-11-slice-2.1-durable-job-queue.md)，不改 Slice 2.2/2.3 owner"
- **Target §2**：完整11行 allowlist 表
- **Verdict**：**MATCH**。master 正确 defer 到 target 的详细 allowlist，并明确不改 Slice 2.2/2.3 owner。

### 1.3 descriptor-only

- **Master :3755**："descriptor-only Service registry"
- **Target §3.2**："本 slice 选择 descriptor-only contract，不定义 `JobHandlerProtocol`，也没有任何 invocation method"
- **Verdict**：**MATCH**

### 1.4 无 JobHandlerProtocol

- **Master :3755**："本 slice 不定义 execution invocation protocol 或注册 handler，后者归 Slice 2.2/2.3"
- **Target §3.2**："不定义 `JobHandlerProtocol`，也没有任何 invocation method"；§9 STOP 禁止注册 business handler
- **Verdict**：**MATCH**

### 1.5 missing correlation 不补建

- **Master :3756**："缺 correlation 的旧 attempt 不补建"
- **Target §4.1**："该 attempt 只能等待 lease expiry 后由 generic `recover` abandon 并按 retry policy 重试；任何 caller 均不得据此创建 Host run，也不得为旧 attempt 补建 correlation"
- **Verdict**：**MATCH**

### 1.6 correlation-safe recover

- **Master :3756**："generic recover 仅处理 `NOT EXISTS correlation`，public Service recovery 以 correlation-safe query-before-retry orchestration 收敛"
- **Target §4.2.7**：SQL `NOT EXISTS (SELECT 1 FROM agent_run_correlations ...)` 排除所有 attached attempt
- **Target §3.2**：`recover_agent_run_after_no_host` targeted method + `JobService.recover` fixed sequence
- **Verdict**：**MATCH**

### 1.7 Slice 2.2/2.3 边界

- **Master :3755**："后者归 Slice 2.2/2.3"
- **Master :3754**："不改 Slice 2.2/2.3 owner"
- **Target §9**："scheduler polling/Redis degradation、backoff jitter 归 Slice 2.2"；"业务 payload schema、source health 与 notification 归 Slice 2.3"
- **Verdict**：**MATCH**

### 1.8 master 状态与 Phase 1 history

- **Master :6**：`**PHASE 1 ACCEPTED / VERTICAL INTEGRATION 74/74 PASS**` — 未改写
- **Verdict**：**未改写**，符合 Controller 约束

## 2. FINAL2-001..007 无回归核验

### S21-CTRL-FINAL2-001 — job contract owner 与 storage import guard

**Verdict：NO REGRESSION**

§2 owner 表、§3.1 Host protocol owner、§3.2 Service/registry owner 均保持原定位。`dayu.host.protocols` 仅承载 §3.1 四项 reserved identity contract（`ReservedRunEnsureResult`、`ReservedRunIdentityConflictError`、`ReservedAgentRunExistsError`、`ensure_reserved_run`）。§9 STOP 禁止承载 PG job DTO/Protocol/JobService。AST guard `tests/investment/test_architecture_boundaries.py:80-97` 对 `storage/**` 应用 `_INFRA_FORBIDDEN_IMPORT_PREFIXES`，`TYPE_CHECKING` 也受检。无 re-export、wrapper、lazy import 或测试豁免。

### S21-CTRL-FINAL2-002 — terminal reconciliation 缺 correlation-by-id lookup

**Verdict：NO REGRESSION**

§3.2 精确声明 `get_agent_run_correlation(scope, correlation_id) -> AgentRunCorrelation`，含 tenant-scoped not-found/invariant 语义。§4.3.2 Service exact sequence 保持四步：get correlation → Host get_run → strict mapping → store reconcile。§7D 测试名证明 direct/live/restart 三条路径各有独立 coverage。

### S21-CTRL-FINAL2-003 — deadline 与 correlation-missing 分支

**Verdict：NO REGRESSION**

heartbeat deadline（§4.2.3）：`now >= deadline_at` 时同事务 attempt/job failed、release reason=deadline、generic receipt、event、抛 `JobDeadlineExceededError`。`correlation_missing` 唯一生产分支（§4.1、§4.3.1）：有效 lease 的 `authorize_agent_run_start` 找不到 committed correlation 时返回 `INVARIANT_FAILURE + correlation_missing`。§7C/§8 测试覆盖。

### S21-CTRL-FINAL2-004 — mutable lease schema

**Verdict：NO REGRESSION**

§5 `job_leases` DDL 包含 `updated_at DEFAULT transaction_timestamp()` 和 `version INTEGER NOT NULL DEFAULT 1`。single-release CHECK、CAS `WHERE version=:expected_version`、release trigger 三重保护。grant 精确包含 `released_at, release_reason, updated_at, version`。

### S21-CTRL-FINAL2-005 — Host UNSETTLED 映射

**Verdict：NO REGRESSION**

§3.2 `HostRunObservationState` 包含 `unsettled`。§4.3.2 唯一映射：`host_unsettled` / `outcome=failed` / `safe_error_code=host_run_unsettled` / `TERMINALIZED_FAILURE`。禁止降格写 `host_failed` 或 `host_run_failed`。

### S21-CTRL-FINAL2-006 — generic attempt receipt canonical schema

**Verdict：NO REGRESSION**

§3.2 固定 generic schema/version 常量、8-key canonical object、result 仅 hash reference、所有 non-Host outcome builder 的 exact 参数来源、strict combinations、immutable replay bytes/hash。

### S21-CTRL-FINAL2-007 — recover attempt state/receipt

**Verdict：NO REGRESSION**

§4.2.5-7 明确锁定每种路径的 attempt/job state、receipt outcome/safe code、next_available_at。§3.2 `JobRecoveryResult` invariant 明确 attempt state 如实报告。

## 3. FINAL3-001..005 逐项核验

### S21-CTRL-FINAL3-001 — broad recover 不能表达 correlation-safe recovery

**Verdict：FIXED — no regression**

Controller 要求：
1. `PostgresJobStore.recover(scope)` 只恢复 `NOT EXISTS agent_run_correlations` 的 attempt — **§4.2.7 已实现**："SQL 必须以 `NOT EXISTS (SELECT 1 FROM agent_run_correlations correlation WHERE correlation.tenant_id = attempt.tenant_id AND correlation.attempt_id = attempt.id)` 证明该 attempt **从未提交 correlation**；不得触碰任何 correlation-attached attempt。"
2. `recover_agent_run_after_no_host` targeted method — **§3.2 已实现**：精确 signature `recover_agent_run_after_no_host(scope: TenantScope, correlation_id: UUID, observation_sha256: str) -> JobRecoveryResult | None`
3. `JobService.recover` fixed sequence — **§3.2 已实现**：sorted correlation enumerate → get/Host/strict-map/reconcile → only NO_HOST_RUN targeted → one generic; result order fixed
4. PG two-engine barrier — **§8 测试已实现**：`test_targeted_no_host_recovery_isolated_from_active_and_no_correlation_attempts`、`test_targeted_no_host_recovery_changed_observation_state_or_fence_is_zero_mutation`
5. TOCTOU residual — **§4.3、§9 已记录**："已取得 `START_REQUIRED` 但在 Host ensure 前跨 lease 的 read-to-entry TOCTOU 不能在两套 store 间消除；本 slice 只保证同一 correlation 的 Host ensure at-most-once，绝不声称 distributed exactly-once"

### S21-CTRL-FINAL3-002 — complete 的 cancel/deadline 同时成立顺序未锁定

**Verdict：FIXED — no regression**

Controller 要求：固定 complete 同时命中时 `cancel intent → deadline → success`

§4.2.4 已实现："固定判定顺序为 **cancel intent → deadline → success**。有 cancel intent 时无论是否同时到 deadline，attempt/job 均收敛 cancelled、release lease、写唯一 `(cancelled, "cancel_intent", cancelled, null)` receipt/event 并返回该 immutable receipt；不得写 deadline 或 success receipt/event。"

§8 测试：`test_complete_cancel_intent_precedes_deadline_and_success`

### S21-CTRL-FINAL3-003 — reserved run ID 的 Host enforcement owner 未锁定

**Verdict：FIXED — no regression**

Controller 要求：`RunRegistry.ensure_reserved_run` 是格式校验唯一 owner；必须在开启 write transaction/写 SQLite 前拒绝非 `run_` + 32 位小写 hex

§3.1 已实现："RunRegistry.ensure_reserved_run 是 Host 侧 reserved ID 格式校验的唯一 owner：必须在开启 `write_transaction()` / SQLite `BEGIN IMMEDIATE` 或任何 SQLite 写入前，以 `run_` + 32 位小写 hex 严格校验；不合法即抛 `ValueError("invalid_reserved_run_id")`，零 SQLite/Host side effect。executor 与 Host 只委托、不得复制第二 validator；PG DTO/DDL 仍独立执行同一格式不变量。"

§8 测试：`test_ensure_reserved_run_rejects_invalid_32_hex_before_sqlite_write`

### S21-CTRL-FINAL3-004 — ready deadline terminal state 的 safe observation 未固定

**Verdict：FIXED — no regression**

Controller 要求：固定为 job=`failed`、`safe_failure_code=deadline_exceeded`、单一 `job_deadline_exceeded` event、无 attempt/lease/receipt

§4.2.2 已实现："先把 deadline 已到的 ready job 标记为 job=`failed`、`safe_failure_code=deadline_exceeded`，并只写一个 `job_deadline_exceeded` event；该路径不创建 attempt、lease 或 receipt，job 已非 ready 的重放不追加 event。"

§8 测试：`test_ready_deadline_sets_exact_safe_failure_and_single_event_without_attempt`

### S21-CTRL-FINAL3-005 — master Slice 2.1 与 target 已发生显式 contract drift

**Verdict：FIXED — no regression**

Controller 要求：只修订 master Slice 2.1 `Allowed/API/Invariants/Completion/Tests` 五行

§1 已逐字比较确认七个维度（owner、allowlist、descriptor-only、无 JobHandlerProtocol、missing correlation 不补建、correlation-safe recover、Slice2.2/2.3 边界）全部 MATCH。master 状态与 Phase 1 history 未改写。

## 4. Adversarial code-generation-readiness 核验

### 4.1 Public signatures

§3.2 精确声明 `JobStoreProtocol` 13 个方法的 exact sync signature（含 `recover_agent_run_after_no_host`）。`JobService` 11 个公共签名与 store 签名一一对应（`reconcile_agent_run_terminal` 不接收 observation 参数，`recover_agent_run_after_no_host` 和 `get_agent_run_correlation` 不暴露为 public API）。`HostRunReaderProtocol.get_run(run_id: str) -> RunRecord | None`。所有 signature 无 `Any`、`object`、`cast`、`type: ignore`。

**Verdict：无问题**

### 4.2 Owner DAG

依赖 DAG（§2 图示）：`domain.jobs` → `storage.protocols` → `PostgresJobStore`；`domain.jobs` → `services.job_service`；`services.job_service` → `HostRunReaderProtocol.get_run` → Host。无反向边。storage 只依赖 pure domain；Service 是唯一可 import `RunRecord` 的位置；Host 只保留 reserved-run lifecycle。

**Verdict：无问题**

### 4.3 状态机

§4.1 闭合转换表覆盖 Job/Attempt/Correlation 三类对象的所有合法转换。§4.2 各算法在唯一 PG transaction 内以数据库时钟为唯一权威。§4.3 两个显式事务（claim Transaction 1 + reserve Transaction 2）不声称共享 context。terminal replay/first terminalize/stale replay 的去重规则确保 immutable receipt 不被 rewrite、event 不重复追加。

**Verdict：无问题**

### 4.4 PG16 named tests

§7 五个 implementation slices（A-E）各有完整测试名列表。§8 故障矩阵逐场景映射到命名测试，包括：
- two-worker race: `test_claim_two_workers_only_one_receives_job`
- PG clock skew: `test_worker_clock_skew_does_not_change_lease_deadline_backoff_or_event_time`
- two-engine/process barrier: `test_terminal_reconcile_wins_before_recover`、`test_recover_wins_terminal_reconcile_is_stale_without_receipt_or_job_mutation`
- correlation-safe recover: `test_job_service_recover_returns_targeted_then_generic_results_in_stable_order`、`test_targeted_no_host_recovery_isolated_from_active_and_no_correlation_attempts`
- RLS: `test_postgres_jobs_cross_tenant_reads_are_not_found_and_writes_denied`
- grant matrix: `test_0003_grant_matrix_exact`
- upgrade/downgrade: `test_0003_upgrade_downgrade_upgrade_and_external_dependency_refusal`

**Verdict：无问题**

### 4.5 Stop 条件

§9 STOP 覆盖所有已知 codegen-blocking 场景（18 项），包括：reserved identity 塞入 metadata、Host protocol 承载 PG job contract、reserved error 泄漏 record、PostgresJobStore 持有 registry、JobService 绕过 registry gate、Agent path before correlation commit、sync Service 构造 ExecutionContract、storage import Host/contracts、moving Host lifecycle truth、existing reserved run re-construct Agent、cross-store transaction/dual-write、correlation-attached attempt in generic recover、targeted recovery as public/bulk、Host row disappearance blind replay、missing fingerprint replay、RLS with fake、shared engine two lifecycle owners、registering business handler/worker/Redis/API/UI。

**Verdict：无问题**

### 4.6 TOCTOU residual

§4.3 和 §9 明确记录：已取得 `START_REQUIRED` 但在 Host ensure 前跨 lease 的 read-to-entry TOCTOU 不能在两套 store 间消除；本 slice 只保证同一 correlation 的 Host ensure at-most-once，绝不声称 distributed exactly-once；Slice 2.2 负责 immediate Host entry、heartbeat/governance、re-observe/cancel delivery。

**Verdict：诚实记录，归属正确**

## 5. Final conclusion

**PASS** — open H/M/L = 0/0/0

S21-CTRL-FINAL2-001..007 全部保持 CLOSED，无回归。S21-CTRL-FINAL3-001..005 全部 FIXED，逐项核验通过。master Slice2.1 五行与 target 的七个维度逐字比较全部 MATCH。Public signatures、owner DAG、state machine、PG16 named tests、stop conditions、TOCTOU residual 均 code-generation-ready。计划可进入 implementation gate。
