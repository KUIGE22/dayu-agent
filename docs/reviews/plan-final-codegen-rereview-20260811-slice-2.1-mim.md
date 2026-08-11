# Final Codegen Re-review：Slice 2.1 durable job queue

- **Gate**：final dual plan re-review
- **Branch / baseline**：`codex/investment-platform` / `61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Target**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Scope**：逐项裁决 S21-CTRL-FINAL2-001..007、Controller follow-up、adversarial code-generation-readiness 检查
- **Valid prior reviews**：
  - `docs/reviews/plan-controller-final-corrective-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`（Controller，OPEN H/M/L = 3/2/2）
  - `docs/reviews/plan-fix-20260811-slice-2.1-final-codegen-closure-terra.md`（Terra fix，all CLOSED）
- **External actions**：未执行 commit、push、PR、deploy、live、paid、Docker 或 PostgreSQL action。

## 1. Review-integrity record

本 review 独立于 Terra fix，未读取任何本 gate 另一 reviewer 新产物（MiM/DeepSeek 的 new review）。仅读取：
1. AGENTS.md（项目约束）
2. Master plan Phase2/Slice2.1 边界（`docs/plans/2026-08-10-investment-platform-restoration.md:3750-3758`）
3. Target plan（`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`，全文）
4. Controller final corrective adjudication（`docs/reviews/plan-controller-final-corrective-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`）
5. Terra fix（`docs/reviews/plan-fix-20260811-slice-2.1-final-codegen-closure-terra.md`）
6. Architecture guard source（`tests/investment/test_architecture_boundaries.py:80-195`）

## 2. Finding closure verdicts

### S21-CTRL-FINAL2-001 — job contract owner 与 storage import guard 冲突

**Verdict：CLOSED**

Terra fix 选择唯一正确分层：`dayu.investment.domain.jobs` 为 pure domain DTO/enum/error/receipt builder owner；`dayu.investment.storage.protocols.JobStoreProtocol` 为 repository contract owner；`dayu.services.job_service` 为 Service/registry/reader owner。`PostgresJobStore` 只依赖 pure domain，不 import `dayu.host` 或 `dayu.contracts`。现有 AST guard（`tests/investment/test_architecture_boundaries.py:80-97,193-195`）对 `storage/**` 应用 `_INFRA_FORBIDDEN_IMPORT_PREFIXES`（含 `dayu.host`、`dayu.contracts`），`TYPE_CHECKING` 也受检。计划 §2 允许表精确列出 Host reserved identity owner 的 `dayu/host/protocols.py` 改动仅限 §3.1 的四项 reserved identity contract。§9 STOP 条件明确禁止 `dayu.host.protocols` 承载 PG job DTO/Protocol/JobService。依赖 DAG（§2 图示）无反向边。无 lazy import、re-export、wrapper 或测试豁免。

**直接证据**：target plan §2 owner 表、§3.1 Host protocol owner、§3.2 Service/registry owner、§2 DAG、§9 STOP、`test_architecture_boundaries.py:80-97`。

### S21-CTRL-FINAL2-002 — terminal reconciliation 缺 correlation-by-id lookup

**Verdict：CLOSED**

计划 §3.2 精确声明 `get_agent_run_correlation(scope, correlation_id) -> AgentRunCorrelation`，包含 tenant-scoped not-found/invariant 语义（§3.2 第 245 行）。Service exact sequence（§4.3.2）：`get_agent_run_correlation` → `host_run_reader.get_run` → strict mapping → `reconcile_agent_run_terminal`。每次 direct/live/restart/replay 都重新读取，无 cache。§7D 测试名证明 direct/live/restart 三条路径各有独立 coverage。

**直接证据**：target plan §3.2 `get_agent_run_correlation` signature/语义、§4.3.2 Service exact sequence、§7D test names。

### S21-CTRL-FINAL2-003 — deadline 与 correlation-missing 分支未闭合

**Verdict：CLOSED**

heartbeat deadline 分支（§4.2.3）：`now >= deadline_at` 时同事务 attempt/job failed、release reason=deadline、generic receipt `(failed, "deadline", deadline_exceeded, null)`、event、抛 `JobDeadlineExceededError`；绝不返回 past-expiry claim。`correlation_missing` 唯一生产分支（§4.1、§4.3.1）：有效 lease 的 `authorize_agent_run_start` 找不到 committed correlation 时返回 `INVARIANT_FAILURE + correlation_missing`，零写入。§7C 测试名 `test_heartbeat_at_or_after_deadline_terminalizes_then_raises_deadline_error`、`test_correlation_missing_has_only_start_authorization_invariant_decision` 证明覆盖。

**直接证据**：target plan §4.2.3 heartbeat、§4.1 correlation_missing、§4.3.1 start authorization、§7C/§8 test names。

### S21-CTRL-FINAL2-004 — mutable lease schema 与总则冲突

**Verdict：CLOSED**

§5 `job_leases` DDL 明确包含 `updated_at DEFAULT transaction_timestamp()` 和 `version INTEGER NOT NULL DEFAULT 1`。§5 还声明 single-release CHECK、CAS `WHERE version=:expected_version`、release trigger 拒绝 release 后修改。grant 精确包含 `released_at, release_reason, updated_at, version`。§7B/§8 测试 `test_job_lease_single_release_versioned_cas_and_grant_matrix` 证明覆盖。

**直接证据**：target plan §5 `job_leases` DDL、migration grants/CAS/trigger、§7B/§8。

### S21-CTRL-FINAL2-005 — Host UNSETTLED 映射不唯一

**Verdict：CLOSED**

§3.2 `HostRunObservationState` 枚举包含 `unsettled`。§4.3.2 首次 terminalize 明确：Host UNSETTLED 唯一映射为 `CorrelationState.host_unsettled`、Host-origin receipt `outcome=failed`、`safe_error_code=host_run_unsettled`、action=`TERMINALIZED_FAILURE`。禁止降格写 `host_failed` 或 `host_run_failed`。§7D/§8 测试 `test_host_unsettled_maps_to_unsettled_state_code_and_failure_action` 证明覆盖。

**直接证据**：target plan §3.2 HostRunObservationState、§4.3.2 UNSETTLED mapping、§7D/§8。

### S21-CTRL-FINAL2-006 — generic attempt receipt canonical schema 缺失

**Verdict：CLOSED**

§3.2 固定 generic schema name/version 常量、8-key canonical object（按字典序：`attempt_id, job_id, outcome, reason, result, safe_error_code, schema_name, schema_version`）、result 仅 hash reference、所有 non-Host outcome builder（complete/fail/cancel/deadline/lease-expired/retry-exhausted）的 exact 参数来源、strict combinations、immutable replay bytes/hash。§5 receipt DDL 区分 generic 与 Host receipt schema/key set。§7B/§8 测试 `test_generic_attempt_receipt_golden_bytes_for_every_non_host_outcome`、`test_generic_attempt_receipt_strict_parse_rejects_wrong_key_set_or_combination`、`test_generic_attempt_receipt_db_roundtrip_preserves_bytes_and_hash` 证明覆盖。

**直接证据**：target plan §3.2 generic builder、§4.2.3-7 receipt paths、§5 DDL、§7B/§8。

### S21-CTRL-FINAL2-007 — recover 的 attempt state/receipt 互相矛盾

**Verdict：CLOSED**

§4.2.5-7 明确锁定每种路径的 attempt/job state、receipt outcome/safe code、next_available_at：
- handler fail retry：`failed/ready`，receipt `(failed, "failure", failure.safe_error_code, null)`
- lease-expiry retry：`abandoned/ready`，receipt `(failed, "lease_expired", lease_expired, null)`
- cancel-intent recover：`cancelled/cancelled`，receipt `(cancelled, "cancel_intent", cancelled, null)`
- deadline terminal：`failed/failed`，receipt `(failed, "deadline", deadline_exceeded, null)`
- retry-exhausted terminal：`failed/failed`，receipt `(failed, "failure", retry_exhausted, null)`

§3.2 `JobRecoveryResult` invariant 明确 attempt state 如实报告。§7C/§8 测试 `test_recovery_result_reports_actual_handler_fail_lease_expiry_cancel_and_terminal_states` 证明覆盖。

**直接证据**：target plan §4.2.5-7、§3.2 DTO invariants、§7C/§8。

## 3. Controller follow-up 检查

### Host protocols allowlist

计划 §2 允许表精确列出 Host reserved identity owner 的文件：`dayu/host/protocols.py`、`dayu/host/run_registry.py`、`dayu/host/host_execution.py`、`dayu/host/executor.py`、`dayu/host/host.py`。§3.1 明确 `dayu/host/protocols.py` 改动仅限 `ReservedRunEnsureResult`、`ReservedRunIdentityConflictError`、`ReservedAgentRunExistsError` 和 `ensure_reserved_run`。§9 STOP 禁止承载 PG job DTO/Protocol/JobService。**Verdict：CLOSED**

### 两个 error constructors/.record

§3.1 精确声明 `ReservedRunIdentityConflictError(record)` 和 `ReservedAgentRunExistsError(record)` 的 constructor：`self.record = record; super().__init__("reserved_run_identity_conflict")` / `super().__init__("reserved_agent_run_exists")`。两个 error 都把传入 `RunRecord` 赋给公开只读 `.record`；`RuntimeError.args` 只为固定 safe code。**Verdict：CLOSED**

### 安全 message

§3.1 明确异常文本不序列化 record；§3.2 `CanonicalJobDocument` 递归拒绝 closed 敏感键集合（password、secret、token、authorization、cookie、api_key）；§6 明确 no payload/result/receipt bytes、token、host metadata、prompt 或 stack trace 被 emit。**Verdict：CLOSED**

### 15 DTO 唯一 owner

§2 允许表明确 `dayu/investment/domain/jobs.py` 是 "15 个且仅 15 个 job DTO、closed enum、稳定错误、canonical document/parser 与 generic receipt builder 的唯一真源"。§3.2 逐一列出 15 个 DTO 的精确字段。§9 STOP 禁止第二 owner。**Verdict：CLOSED**

### Services-owned registry

§3.2 明确 `JobHandlerRegistryProtocol` 与唯一 concrete `JobHandlerRegistry` 都位于 `dayu.services.job_service`，而非 storage。Protocol 只声明 `register_descriptor` 和 `get_descriptor`。`JobHandlerRegistry` 使用私有 `dict[str, JobHandlerDescriptor]`。production composition 构造空实例。**Verdict：CLOSED**

### JobService-before-store enqueue

§3.2 明确 `JobService.enqueue` 唯一顺序：`descriptor_registry.get_descriptor` → None 或 mismatch 时抛 `JobInputError` 且**不得调用 store** → 完全相等时唯一调用 `job_store.enqueue`。§7B 测试 `test_job_service_enqueue_rejects_missing_or_mismatched_descriptor_before_store` 证明覆盖。**Verdict：CLOSED**

### Correlation lookup/order

§4.3.2 `reconcile_agent_run_terminal` 固定顺序：`job_store.get_agent_run_correlation(scope, correlation_id)` → `host_run_reader.get_run(correlation.reserved_host_run_id)` → strict mapping → `job_store.reconcile_agent_run_terminal(scope, correlation_id, observation)`。每次 restart/replay 都执行该四步。**Verdict：CLOSED**

### Heartbeat/deadline/correlation_missing

已在 §2 S21-CTRL-FINAL2-003 中验证。**Verdict：CLOSED**

### Lease version/CAS

已在 §2 S21-CTRL-FINAL2-004 中验证。**Verdict：CLOSED**

### UNSETTLED

已在 §2 S21-CTRL-FINAL2-005 中验证。**Verdict：CLOSED**

### Generic receipt schema

已在 §2 S21-CTRL-FINAL2-006 中验证。**Verdict：CLOSED**

### Real recovery state

§4.2.7 recover 算法明确：cancel-intent → attempt `cancelled`、job `cancelled`、receipt `(cancelled, "cancel_intent", cancelled, null)`；非取消 → attempt `abandoned`、receipt `(failed, "lease_expired", lease_expired, null)`、按 retry policy 使 job ready/failed。§3.2 `JobRecoveryResult` invariant 明确 attempt state 如实报告。§8 故障矩阵测试覆盖所有路径。**Verdict：CLOSED**

## 4. Adversarial code-generation-readiness 检查

### 4.1 Owner DAG

依赖 DAG（§2 图示）：`domain.jobs` → `storage.protocols` → `PostgresJobStore`；`domain.jobs` → `services.job_service`；`services.job_service` → `HostRunReaderProtocol.get_run` → Host。无反向边。storage 只依赖 pure domain；Service 是唯一可 import `RunRecord` 的位置；Host 只保留 reserved-run lifecycle。**Verdict：无问题**

### 4.2 Public signatures

§3.2 精确声明 `JobStoreProtocol` 全部 12 个方法的 exact sync signature（enqueue/claim/heartbeat/complete/fail/cancel/recover/reserve_agent_run_correlation/get_agent_run_correlation/list_expired_agent_run_correlations/authorize_agent_run_start/reconcile_agent_run_terminal）。`JobService` 公共签名与 store 签名一一对应（除 `reconcile_agent_run_terminal` 不接收 observation 参数）。`HostRunReaderProtocol.get_run(run_id: str) -> RunRecord | None`。所有 signature 无 `Any`、`object`、`cast`、`type: ignore`。**Verdict：无问题**

### 4.3 State/race/replay

§4.1 闭合转换表覆盖 Job/Attempt/Correlation 三类对象的所有合法转换。§4.2 各算法在唯一 PG transaction 内以数据库时钟为唯一权威。§4.3 两个显式事务（claim Transaction 1 + reserve Transaction 2）不声称共享 context。terminal replay/first terminalize/stale replay 的去重规则（§4.3.2）确保 immutable receipt 不被 rewrite、event 不重复追加。§8 故障矩阵覆盖 two-worker race、stale writes、clock skew、cancel race、crash recovery。**Verdict：无问题**

### 4.4 DDL/RLS/grants

§5 七表 DDL 精确声明每表的列、FK、CHECK、索引。RLS：所有七表启用并 force RLS，单一 `tenant_isolation` policy。Grant：revoke PUBLIC；audit SELECT only；app 精确列级 UPDATE grant（§5 grants 精确列表）；receipts/events 只 SELECT/INSERT。`job_leases` 受 single-release CHECK + CAS + release trigger 三重保护。Downgrade：查询 catalog dependencies、fail closed on external dependency、按依赖顺序 drop。**Verdict：无问题**

### 4.5 Composition/lifecycle

§6 两阶段 composition：`_prepare_production_platform_dependencies` 在 provider admission 位点运行（PG engine probe、identity service）；`_build_production_services_provider` 在 Host 构造后做内存装配（PostgresJobStore → JobService）。`InvestmentIdentityService` 是唯一 engine lifecycle owner；`PreparedHostRuntimeDependencies.close()` 是 sole exact-once owner。阶段 2 失败时 dispose engine 一次、Host 不被暴露。**Verdict：无问题**

### 4.6 Tests/stop/residual

§7 五个 implementation slices（A-E）各有完整测试名列表。§8 故障矩阵逐场景映射到命名测试。§9 STOP 条件覆盖所有已知 codegen-blocking 场景。§9 残余风险归属明确（Slice 2.2/2.3/future handler）。§9 明确 "双路 plan re-review 必须把 S21-CTRL-FINAL2-001..007 逐项裁决；任何未关闭高/中 finding 使本计划退出 candidate"。**Verdict：无问题**

## 5. Final conclusion

**PASS** — open H/M/L = 0/0/0

S21-CTRL-FINAL2-001..007 全部 CLOSED；Controller follow-up 全部验证通过；adversarial code-generation-readiness 检查未发现高/中缺口。Owner DAG、public signatures、state/race/replay、DDL/RLS/grants、composition/lifecycle、tests/stop/residual 均 code-generation-ready 且不与 master/源码冲突。计划可进入 implementation gate。
