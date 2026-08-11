# Final Codegen Re-Review：Slice 2.1 durable job queue（DeepSeek Flash，独立 reviewer-only）

- **Gate**：final corrective plan re-review（S21-CTRL-FINAL2-001..007 逐项裁决 + adversarial owner/contract/at-most-once/recovery/bytes/DDL/composition/fault-matrix/stop 复核）
- **Branch / baseline**：`codex/investment-platform` / `61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Target plan**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Source findings**：`docs/reviews/plan-controller-final-corrective-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`（S21-CTRL-FINAL2-001..007）
- **Plan fix**：`docs/reviews/plan-fix-20260811-slice-2.1-final-codegen-closure-terra.md`
- **Master**：`docs/plans/2026-08-10-investment-platform-restoration.md`（Phase 2 / Slice 2.1，行 3750-3758）
- **Conclusion**：**FAIL — open H/M/L = 0/1/3**

## 1. Review-integrity record

本 reviewer 未参与 Slice 2.1 计划编写或任一修复，本轮严格 reviewer-only；只读取了本任务明确授权的五类输入（AGENTS.md、master Phase2/Slice2.1、target plan 全文 433 行、Controller final corrective adjudication、Terra final codegen-closure fix）以及必要的直接源码/架构守护。未读取本 gate 的另一 reviewer 新产物（`plan-final-corrective-rereview-20260811-slice-2.1-contract-closure-flash.md` / `...-mim.md`），未依赖任何过去的 review 结论。未运行 pytest、pyright、ruff、Docker 或 PG16；未做任何 commit/push/PR/live/paid 动作。本 gate 明确禁止这些验证，它们是后续 implementation gate 的计划内动作。

## 2. S21-CTRL-FINAL2-001..007 逐项裁决（全部 CLOSED-IN-PLAN）

### S21-CTRL-FINAL2-001 — CLOSED — job contract owner 与 storage import guard 冲突

直接证据（源码守护）：`tests/investment/test_architecture_boundaries.py:91-97` 的 `_INFRA_FORBIDDEN_IMPORT_PREFIXES` 从完整 forbidden set 只移除 `sqlalchemy/psycopg/alembic`，仍含 `dayu.host` 与 `dayu.contracts`；`:193-195` 把 `storage/` 前缀映射到该集合；`:214-243` 的 `_collect_forbidden_imports` 对 `ast.Import`/`ast.ImportFrom` 全树扫描（含 `TYPE_CHECKING` 分支），`:866` 断言零违规。owner DAG 修复落点：

- `dayu/investment/domain/jobs.py`（纯域，15 DTO/enums/errors/canonical/receipt builder）：target §2 owner 表行 1、§2 依赖顺序 B；guard 对 `domain/` 前缀按 pure 集合（`:188-192`），`dayu.host`/`dayu.contracts` 仍禁。
- `dayu/investment/storage/protocols.py`（JobStoreProtocol 真源）：target §3.2；现文件 `dayu/investment/storage/protocols.py:28-45` 已按同模式只 import `dayu.investment.domain.*`，storage 不再需要 `dayu.host`/`dayu.contracts`，guard 无需豁免（target §2 line 33 明示）。
- `dayu/services/job_service.py`（JobService + JobHandlerRegistryProtocol/concrete + HostRunReaderProtocol）：target §2 owner 表行 3、§3.2；位于 `dayu.services`，不在 guard 扫描范围，是唯一可 import `dayu.contracts.run.RunRecord` 并投影为 `HostRunObservationState` 的位置，符合 `UI -> Service -> Host -> Agent` 分层。
- `dayu/host/protocols.py` 只承载 §3.1 四项 reserved identity contract（target §2 line 33）；`RunRegistryProtocol` 确在 `dayu/host/protocols.py:557`，`ensure_reserved_run` 使用已 import 的 `ExecutionDeliveryContext`（`:15`）。
- 无 re-export/wrapper/lazy import/测试豁免；`test_investment_storage_import_guard_still_rejects_host_and_contracts`（§7B）与 `test_job_domain_storage_protocol_and_service_registry_are_the_only_contract_owners`（§7B/§8）锁定。

### S21-CTRL-FINAL2-002 — CLOSED — terminal reconciliation 缺 correlation-by-id lookup

`get_agent_run_correlation(scope, correlation_id) -> AgentRunCorrelation` 已加入 JobStoreProtocol exact signature 表（target §3.2 line 235）与 JobService signature 表（line 258）；语义固定：单 tenant transaction 内 `SET LOCAL app.tenant_id`、`(tenant_id, id)` 精确读取、不存在/跨租户 `JobNotFoundError`、identity/invariant 违反 `JobCorrelationInvariantError`、无 cache（line 245）。Service 四步顺序 `get correlation → host_run_reader.get_run → strict mapping → store reconcile` 固定于 §3.2 line 289 与 §4.3.2 line 336。测试：`test_get_agent_run_correlation_is_tenant_scoped_not_found_and_invariant_checked`、`test_direct_live_restart_reconciliation_always_reads_correlation_then_host_then_store`（§7D、§8 matrix line 412）。

### S21-CTRL-FINAL2-003 — CLOSED — deadline 与 correlation-missing 分支未闭合

heartbeat：`now >= deadline_at` 同事务 attempt/job failed、lease release reason=deadline、generic receipt `(failed, "deadline", deadline_exceeded, null)` + deadline event，随后抛 `JobDeadlineExceededError`，绝不返回过去/等于 now 的 expiry 成功 claim；`now < deadline_at` 才 clamp 为 `min(now+lease_duration, deadline_at)`（§4.2.3 line 309）。`correlation_missing` 唯一生产返回点：`authorize_agent_run_start` 有效 lease 但无 committed correlation → `INVARIANT_FAILURE + correlation_missing` + deduped event，零状态变更（§4.1 line 301、§4.3.1 line 334）；其它 correlation 缺失读取一律 `JobNotFoundError`。测试：`test_heartbeat_at_or_after_deadline_terminalizes_then_raises_deadline_error`、`test_heartbeat_before_deadline_clamps_expiry_without_past_success_claim`、`test_correlation_missing_has_only_start_authorization_invariant_decision`（§7C/§8）。

### S21-CTRL-FINAL2-004 — CLOSED — mutable lease schema 与总则冲突

选择 versioned mutable lease：`job_leases` 增加 `updated_at DEFAULT transaction_timestamp(), version INTEGER NOT NULL DEFAULT 1`（§5 line 356）；single-release 由 CHECK（`released_at>=acquired_at`、release_reason closed values）+ `WHERE version=:expected_version` CAS + release trigger（拒绝 release 后任何再次更新及不成对字段）双重约束（line 356、line 361）；grant 精确包含 `job_leases(released_at, release_reason, updated_at, version)`（line 361）。测试：`test_job_lease_single_release_versioned_cas_and_grant_matrix`（§7B/§8）。

### S21-CTRL-FINAL2-005 — CLOSED — Host UNSETTLED 映射不唯一

唯一映射固定：`UNSETTLED → HostRunObservationState.unsettled → CorrelationState.host_unsettled → Host-origin receipt (failed, host_run_unsettled) → TERMINALIZED_FAILURE`，随后与 Host failed 同一 retry policy；禁止写 `host_failed`/`host_run_failed`/其它 outcome/code（§4.3.2 line 339）。测试：`test_host_unsettled_maps_to_unsettled_state_code_and_failure_action`（§7D/§8）。

### S21-CTRL-FINAL2-006 — CLOSED — generic attempt receipt canonical schema 缺失

固定 `GENERIC_ATTEMPT_RECEIPT_SCHEMA_NAME="dayu.job.generic-attempt-receipt"` / `VERSION=1`，canonical object 按字典序恰含 8 key：`attempt_id, job_id, outcome, reason, result, safe_error_code, schema_name, schema_version`；`result` 只可为 null 或 `{schema_name, schema_version, sha256}` 引用对象，绝不重复 `result_bytes`；每个 non-Host outcome 的 builder 参数来源逐项固定（complete/fail/cancel 收敛/heartbeat deadline/lease-expiry/retry-exhausted），同 attempt 重放必须读取既存 immutable row、绝不重建（§3.2 line 182-197）。DDL `job_attempt_receipts` 区分 generic 与 Host schema 常量/key set 约束（§5 line 357）。测试：`test_generic_attempt_receipt_golden_bytes_for_every_non_host_outcome`、`test_generic_attempt_receipt_strict_parse_rejects_wrong_key_set_or_combination`、`test_generic_attempt_receipt_db_roundtrip_preserves_bytes_and_hash`、`test_duplicate_non_host_finalization_reuses_existing_receipt_bytes_and_hash`（§7B/§8）。

### S21-CTRL-FINAL2-007 — CLOSED — recover 的 attempt state/receipt 互相矛盾

`JobRecoveryResult` invariant 逐分支唯一化（§3.2 line 173）：handler fail retry=`failed/ready`；非取消 lease-expiry retry=`abandoned/ready`；cancel-intent recover=`cancelled/cancelled`；deadline/retry-exhausted terminal=`failed/failed`；"结果必须报告真实持久 attempt state，绝不以 DTO 伪装为 failed"。§4.2.5/4.2.7 与 §4.3 状态矩阵（line 317-326）同步；"若终态 code 覆盖 lease_expired，receipt 的 safe_error_code 必同步为该终态 code、reason 仍为 lease_expired"（line 313）。测试：`test_recovery_result_reports_actual_handler_fail_lease_expiry_cancel_and_terminal_states`（§7C/§8，参数化）。

## 3. Adversarial pass（按指定检查项逐项）

**owner DAG**：B 只依赖纯域、C 只依赖 B、D 依赖 B/C/A 且 C 不依赖 Host/contracts、E 只装配 C/D/A（§2 line 49）；`dayu.investment.composition.PlatformServiceProtocol`（composition.py:60-72）与 `PlatformComposition`（:272-346）现成承载 `durable_jobs`，`dayu/contracts/protocols.py` 未改动；`dayu/startup/platform.py` 与 architecture guard 未改动（§2 line 33）。✓

**exact public contract**：JobStoreProtocol 12 方法与 JobService 11 方法（后者无 `get_agent_run_correlation`，内部四步使用）签名逐字固定（§3.2 line 214-265）；decision DTO 字段/不变量表（line 267-287）；`TenantId`/`TenantScope` 来自 `dayu/investment/domain/identifiers.py:91-95,270-322`。✓

**Host reserved at-most-once**：`write_transaction` 确为 `BEGIN IMMEDIATE`（`dayu/host/host_store.py:373`）；`register_run` 用 `run_{uuid.uuid4().hex[:12]}`（`dayu/host/run_registry.py:188`），与 32-hex reserved 永久共存且 `runs` 表不加长度 CHECK（§3.1 line 133）；executor 四个 Agent entry 全为 async（`dayu/host/executor.py:521,694,924,944`，`HostExecutorProtocol` 位于 `dayu/host/host_execution.py:47-87`），`replay_agent_and_wait`（executor.py:979）不扩展；Host 同名委托入口在 `dayu/host/host.py:611,647,683,705`；`created=False` 绝不构造 Agent/调用模型，抛 `ReservedAgentRunExistsError(record)`（§3.1 line 137）。crash-window SQLite seam 测试齐全（§8 line 388、matrix line 410）。✓

**PG clock/fence/lease/recovery/correlation replay**：所有时钟决策来自 `transaction_timestamp()`/`clock_timestamp()`（§3.2 line 289、§4.2 line 305），caller time 一律拒绝；claim SKIP LOCKED + `(tenant_id, available_at, id) WHERE state='ready'` partial index（§5 line 354）；event sequence 用行锁下 `next_event_sequence` 递增，禁裸 MAX+1（line 305、line 358）；stale complete/fail/heartbeat 由 fence+token+expiry predicate 拒绝（§4.2.7 line 313）。replay 去重由 `last_observation_sha256` fingerprint 控制（§3.2 line 174-175、§4.3.2 line 338-341），terminal replay 复用同一 immutable receipt（line 340）。✓（recover 与 correlation 交互的缺口见 §4 M1。）

**generic/Host receipt canonical bytes**：generic 8-key 字典序（已核对排序正确）、result 仅引用；Host receipt 固定 schema/version/key set（§4.3.2 line 339）；DDL 区分两种 schema 约束（§5 line 357）；`CanonicalJobDocument` 严格 canonical（无 float/NaN/Infinity、key 字典序、byte-exact、敏感键递归拒绝）（§3.2 line 179）。✓

**DDL/RLS/grants**：七表 schema/FK/CHECK/index 与总则（tenant_id FK organizations(id) RESTRICT、UNIQUE(tenant_id,id)、TIMESTAMPTZ、versioned/append-only）一致（§5 line 349-361，与 0001 migration `0001_platform_foundation.py:152-508` 惯例对齐）；RLS 表达式复用 `nullif(current_setting('app.tenant_id', true), '')::uuid`（line 361，与 0001:71 一致）；列级 UPDATE grant 精确枚举、identity 列禁改、无 DELETE/TRUNCATE/DDL；downgrade catalog fail-closed + 依赖顺序无 CASCADE（line 363）。✓

**composition/lifecycle**：两阶段拆分——阶段 1 保留 pre-Host PG admission（probe `pg_has_role`/非 superuser/非 BYPASSRLS，`startup_preparation.py:259-302`），阶段 2 纯内存装配 `PostgresJobStore(session_factory)` + `JobService(job_store, JobHandlerRegistry(), host_run_reader=host)`，`Host.get_run` 确在 `dayu/host/host.py:1075` 结构满足 reader；唯一 engine lifecycle owner 仍是 `InvestmentIdentityService`（`PreparedHostRuntimeDependencies.close()` 经既有 `_OwnedLifecycleRegistration`），阶段 2 不连接 PG/不启 thread/atexit；失败路径恰好 dispose 一次（§6 line 369-372，与 `startup_preparation.py:824-833` except 路径一致）。✓

**real PG16 fault matrix**：two-engine/process barrier、SKIP LOCKED race、event sequence two-writer、tenant A/B RLS、app role immutable-column UPDATE、clock skew、upgrade→downgrade→upgrade、external dependency refusal、init hook 均落到具名测试（§8 line 388-425）；每项断言最终 state/唯一 receipt/精确 event/无 raw secret/Agent 构造与模型入口次数（line 390）。✓（其中 recover 相关两条存在语义张力，见 §4 M1。）

**stop/residual**：§9 STOP 覆盖 metadata 塞 reserved identity、host/protocols 越权承载、error 携带 record/token/payload、store 持 registry、绕过 registry gate、correlation commit 前调 Host、同步构造 ExecutionContract、storage import Host/contracts、第二 owner、双写、existing reserved run 重建 Agent、replay 无法去重、fake-only RLS、双 lifecycle、注册 handler/worker。✓

## 4. 新 finding

### M1 — NEW — Medium — `recover(scope)` 与 committed correlation 的 store-side 交互未定义；active-Host 保护只靠调用方纪律，job-level 双执行残余未记录

**证据**：

1. §4.2.7（target line 313）对 store 方法 `recover` 的行为描述为"锁定过期 leased/cancel_requested attempt，并 release lease"，**无任何 correlation 排除规则**；`JobStoreProtocol.recover(scope: TenantScope) -> tuple[JobRecoveryResult, ...]` 是批量、无 attempt/correlation 参数的公开 API（line 233），`JobService.recover` 同名委托（line 256）。
2. §4.3（line 343）把保护完全交给 future worker 纪律："仅对 NO_HOST_RUN 的对应 attempt 以及所有无 correlation 的 expired attempt 调 generic recover(scope)……期间绝不调用 generic recover 或 claim 新 attempt"——这是调用方契约，不是 store 契约；任何未遵守纪律的调用方（§8 两 engine/process barrier 中的第二 engine、未来 2.2 worker 竞态、运维直连）一次 `recover(scope)` 即可 abandon 仍持有活跃 Host run（correlation=`host_created`/`host_running`）的 attempt → job 回 `ready` → 新 attempt → 新 correlation → 同 job 第二次模型入口。
3. §8 matrix（line 414）的 `test_active_host_returns_wait_never_recovers_or_creates_new_attempt`（PG16 two-engine/process barrier）以机制级断言命名（"never recovers"），但该保证只能靠两 engine 都遵守 §7D fake-caller 纪律实现；matrix 同时要求 `test_recover_wins_terminal_reconcile_is_stale_without_receipt_or_job_mutation`（line 418）——recover 必须能处理 correlation-attached attempt 才能赢得该竞态。两条测试在 store 层面互相排斥（store 无法区分"host_created/host_running 的 correlation"，因为 Host 行状态 store 不可见），唯一自洽解是"recover 无排除 + 调用方纪律 + STALE_ATTEMPT 兜底"，但计划从未显式写下这一 store 语义组合，实现者无法从计划文本推导出唯一行为。
4. TOCTOU 未闭环：§4.3 顺序"reconcile → NO_HOST_RUN → recover"与并发 `START_REQUIRED` handler 创建 Host run 之间存在窗口——reconcile 观测 missing 时 Host 尚未创建（correlation 仍 `reserved`，reconcile 不改 state，line 338），recover 随即 abandon 该 attempt，此后同一 handler 以同一 `reserved_host_run_id` ensure（created=True）仍进入模型（§4.1 line 301 "Host ensure 仍是唯一的本地模型 at-most-once 栅栏"）。计划以 per-correlation 范围隐式接受"同 job 跨两个 correlation 双执行"，但该残余未写入 §9，matrix 也无对应测试。

**结论**：Slice 2.1 生产侧不注册 worker/handler，运行时无直接暴露面，故不判 High；但 §8 两条具名测试与 §4.2.7 的 store 语义之间缺少唯一可实施规则，且 job-level 双执行残余未在 §9 登记，属于 codegen-readiness 级 Medium 缺口。

**修复方向（供 Controller/plan-fix 选择，本 reviewer 不实现）**：(a) 在 §4.2.7/§4.3 明确 `recover(scope)` 锁定范围内的 correlation-attached attempt 处理规则（如：跳过 correlation state ∈ {host_created, host_running} 的 attempt，并相应改写 `test_recover_wins_...` 的场景前提，使其与 active 保护自洽）；或 (b) 在 §9 显式登记"active-Host 保护依赖 Slice 2.2 worker 纪律、NO_HOST_RUN→recover 与并发 Host entry 的 TOCTOU 可能造成同 job 跨 correlation 二次模型执行（per-correlation at-most-once 保持）"为 accepted residual，并在 §8 补对应测试。

### L2 — NEW — Low — `complete` 在 cancel intent 与 deadline 同时成立时的顺序未固定

§4.2.4（line 310）写"cancel intent 或 deadline 优先"，两者同时成立时未固定 tiebreak；而 heartbeat（§4.2.3 line 309，cancel_requested 先于 deadline 判）、fail（§4.2.5 line 311，cancel 直接优先）、recover（§4.2.7 line 313，cancel 优先）、terminal reconcile（§4.3.2 line 339，cancel → deadline → Host outcome）均为 cancel 优先。§8 矩阵未列"complete 遇 cancel+deadline 同时"行。建议与其余操作对齐为 cancel 优先。

### L3 — NEW — Low — `reserved_run_id` 格式校验的 enforcement owner 未固定

§3.1（line 133）规定 `reserved_run_id` 只接受 `run_` + 32 位小写 hex，但未说明 Host 侧（`ensure_reserved_run`/executor）在何处校验；PG 侧 DDL 有 "reserved ID format check"（§5 line 359）。两份 store 无跨库事务，若损坏 ID 先写入 Host SQLite，需到 PG 侧才被拒绝。当前唯一生成者是 JobService（attempt UUID hex 恰 32 位），风险低，但建议固定 Host 侧校验位点。

### L4 — NEW — Low — claim 对 deadline 已到的 ready job 标记 failed 时的 safe code/event detail 未固定

§4.2.2（line 308）"先把 deadline 已到的 ready job 标记 failed/event"，未固定写入 `job_runs.safe_failure_code`（DDL line 354）的值与 event `safe_detail_bytes` 内容；ready 无 attempt、无 receipt 是明确的（§4.2.6 line 312 类比），但观察面字段建议固定为 `deadline_exceeded`。

## 5. 结论与下一步

- **FAIL（open H/M/L = 0/1/3）**：S21-CTRL-FINAL2-001..007 全部 CLOSED-IN-PLAN（证据见 §2）；M1 为阻断 codegen 的 Medium——`recover(scope)` 与 committed correlation 的 store-side 语义未定义，§8 两条 recover 竞态测试无法从计划推导出唯一可实施行为，active-Host at-most-once 保护完全依赖未来 worker 纪律，job-level 双执行残余未登记。
- 依据 Terra plan-fix §4 的 gate 约定："re-review 必逐项裁决 S21-CTRL-FINAL2-001..007，任一未关闭高/中 finding 均使计划退出 candidate"，M1 使计划退出 candidate，需 Controller 裁决后进入下一轮 bounded corrective plan-fix（只改 target plan 与本轮 artifact），随后仍需独立双路 re-review 归零。
- 本 reviewer 未执行任何 tests/Docker/PG16/commit/push/PR/live/paid 动作。

## 6. 验证方式与本工件自身约束

- 本工件仅写入 `docs/reviews/plan-final-codegen-rereview-20260811-slice-2.1-flash.md`，未修改 target/master/source/tests/README 或任何既有 review artifact，未启动 Gateflow。
- 本工件以 LF 行尾书写，行尾无尾随空白。
