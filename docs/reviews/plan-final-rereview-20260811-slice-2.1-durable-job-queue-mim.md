# Final Corrective Independent Plan Re-Review: Slice 2.1 Durable Job Contract 与 PostgreSQL Queue

- **审查目标**: `docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **审查类型**: Final corrective independent plan re-review
- **本机时间**: 2026-08-11 14:47:07 CST
- **对照真源**:
  - Fix artifact: `docs/reviews/plan-fix-20260811-144217-slice-2.1-crash-recovery.md`
  - Prior false-pass review: `docs/reviews/plan-review-20260811-141746-slice-2.1-durable-job-queue.md`（含两个 false assumptions）
  - Prior review: `docs/reviews/plan-review-20260811-142059.md`
  - 代码证据: `dayu/host/host_execution.py`, `dayu/host/protocols.py`, `dayu/host/executor.py`, `dayu/host/run_registry.py`, `dayu/host/host.py`, `dayu/services/startup_preparation.py`, `dayu/investment/composition.py`, `dayu/contracts/agent_execution.py`, `tests/application/test_host_executor.py`

---

## 1. 先前 False Assumptions 纠正验证

Prior review 141746 做了两个 false assumptions：

1. **"claim 与 reserve 可共享一个 PG transaction"** — 修正后：`JobService.claim(scope, worker_id)` 与 `JobService.reserve_agent_run_correlation(scope, lease)` 是独立 public signatures（plan §4.2.2, §4.3）。Plan §4.3 现在明确写道 "两个独立公开调用、两个明确的 PostgreSQL transaction，绝不声称共享 transaction context"。Fix artifact Controller A 裁决确认这一点。✅ 已修正。

2. **"tokenless terminal backfill 在无 exact current-attempt/job-row predicate 时不安全"** — 修正后：`reconcile_agent_run_terminal(scope, correlation_id)` 是无 token 的 terminal-only reconciliation API（plan §4.3.2），它不接受 lease，只读 Host terminal evidence；在同 job-row FOR UPDATE lock 下检查 current attempt、no newer fence/no recover abandonment，按 cancel→deadline→Host terminal outcome 执行；返回 `STALE_ATTEMPT` 而非覆写。Fix artifact Controller B/D/E 裁决确认。✅ 已修正。

---

## 2. Eight Adversarial Focus Areas 独立验证

### Focus 1: Two-transaction claim then reserve semantics and crash before reserve

**Plan 实际写法（§4.2.2, §4.3）:**

Transaction 1（claim）：单 PG transaction → SET LOCAL tenant → SKIP LOCKED ready jobs → 创建 attempt/lease → commit → 返回 raw token。不创建 correlation。

Transaction 2（reserve）：独立 public method，自己的 PG transaction → SET LOCAL tenant → clock_timestamp() → 锁 job row FOR UPDATE → 锁 attempt/lease/correlation slot → 仅当 raw token SHA-256 + tenant/job/attempt/fence + attempt=leased + job=leased + lease expiry + no cancel intent + deadline 未到全部匹配 → 插入 immutable correlation + event → commit。

**Crash window 分析（plan §4.1）:**

| Crash 时机 | 已提交状态 | 收敛路径 |
|-----------|-----------|---------|
| claim commit 前 | 无 | 可重试 claim |
| claim commit 后、reserve commit 前 | attempt=leased, job=leased, 无 correlation | lease expiry → recover abandon → retry；这是预期 incomplete-operation window，不是 corruption |
| reserve commit 后、Host entry 前 | correlation=reserved, 无 Host row | reconcile → NO_HOST_RUN → generic recover abandon → retry |

**代码证据:** `executor.py:47-55` 确认 `run_agent_stream` 是 async，同步 JobService 不能凭空构造 ExecutionContract 或调 async entry。Plan §3.1 "attempt UUID 生成 run_{attempt_id.hex}" 保证每次 attempt 有确定性唯一 reserved ID。

**判定:** ✅ 无 blocker。两事务分离正确描述，crash window 每种场景有明确收敛路径，claim-reserve crash test 已命名（`test_crash_after_claim_before_reserve_recovers_without_host_side_effect`）。

---

### Focus 2: live START_REQUIRED requires valid current raw lease

**Plan 实际写法（§4.3.1）:**

`authorize_agent_run_start(scope, lease, correlation_id)` — 持 token 的 live authorization。单 PG transaction 内以 job row FOR UPDATE 串行化，锁 correlation + attempt，重新计算 raw token hash；只有 correlation 的 tenant/job/attempt/id、attempt number/fence、lease token hash、lease expiry、job current attempt、job=leased、attempt=leased、无 cancel intent、PG clock_timestamp() < deadline 全部匹配，且 Host observation 是 missing/correlation 仍 reserved → 返回 `START_REQUIRED`。

**关键约束:** 缺 lease、过期 token、wrong tenant/job/attempt/fence/token、非 current attempt、cancel intent 或 deadline 一律不能返回 `START_REQUIRED`，分别给 `LEASE_LOST`、`CANCEL`、`DEADLINE_EXCEEDED` 或 `INVARIANT_FAILURE`。

**No-token observer 无法获得 START_REQUIRED 的验证:** `authorize_agent_run_start` 签名要求 `lease: JobLeaseHandle`（非 Optional），无 lease 参数无法调用此 API。`reconcile_agent_run_terminal` 签名是 `(scope, correlation_id)` 且"不接受 lease、不得 start Host"。两个 API 签名互斥，无法混淆。

**代码证据:** `host_execution.py:47-55` 确认 `run_agent_stream` 是 async entry；`executor.py:521` 附近确认 executor 方法的 async 性质。同步 JobService 不得调用。

**判定:** ✅ 无 blocker。START_REQUIRED 的 token-based fencing 完整闭合。

---

### Focus 3: terminal-only reconciliation vs recover — two lock orders, newer attempt/fence, immutable receipts, event sequence

**Plan 实际写法（§4.3.2）:**

Terminal reconciliation: 接受已提交 correlation ID → 读 Host terminal evidence → **另开 PG transaction** → 同一 job row FOR UPDATE serialization → 锁 attempt + correlation → 检查 current attempt + no newer fence + no recover abandonment → 按 **cancel intent → deadline → Host terminal outcome** 顺序写 receipt/event/state → 返回 terminalized。

若 recover 先取得 job lock：recover 将旧 attempt abandoned + job ready/terminal → terminal reconciliation 只能更新 correlation 为 terminal observation + 追加 `correlation_stale_attempt` event → 返回 `STALE_ATTEMPT` + `correlation_stale_attempt` → **不得**回写旧 attempt receipt 或 current job state。

**Race matrix:**

| 场景 | 获胜方 | 结果 |
|------|-------|------|
| terminal reconcile 先锁 job | terminalize | 正确 receipt + event |
| recover 先锁 job | recover | 旧 attempt abandoned; stale terminal 只记 safe observation |
| newer attempt/fence | stale terminal | STALE_ATTEMPT；safe error 必为 correlation_stale_attempt |

**Event sequence 安全:** §4.2 明确 "每次写 event 前先锁定该 job_runs 行…原子递增 next_event_sequence…禁止裸 MAX(sequence_number)+1"。§5 DDL: `next_event_sequence BIGINT NOT NULL DEFAULT 1`。

**Immutable receipts:** §5 DDL `job_attempt_receipts` 是 append-only，无 UPDATE grant；`UNIQUE(tenant_id, attempt_id)` 保证每个 attempt 一条 receipt。§4.3.2 "所有 receipt 仍为每 attempt 一条 immutable row"。

**判定:** ✅ 无 blocker。Terminal vs recover 的 race 完全由 job-row serialization 点闭合；newer attempt stale 路径正确；receipt/event 完整性有 DDL+grant 保护。

---

### Focus 4: distinct NO_HOST_RUN vs HOST_ACTIVE_WAIT; active Host must never generic-recover/claim new attempt/enter model twice

**Plan 实际写法（§4.3.2 + fix artifact Active Host correction）:**

互斥结果：
1. `reserved` + Host missing → `NO_HOST_RUN` → **仅此分支可 generic recover**
2. Host `CREATED/QUEUED/RUNNING` → `HOST_ACTIVE_WAIT` → 保持 current attempt/correlation → **不 recover、不 retry、不 second entry**
3. Host terminal → terminalize 或 stale 路径
4. 已观察 Host 后 row 反向消失 → `INVARIANT_FAILURE`

**HOST_ACTIVE_WAIT 未来 owner（§4.3.2 + §9）:** Slice 2.2 worker 以正数 `host_active_reobserve_interval_seconds` 重观测 → PG `deadline_at` 为 active-wait 上界 → 到期后向 Host lifecycle 发幂等 cancel_run → 只重观测至 Host terminal/unsettled → **绝不** generic recover 或 claim 新 attempt。Slice 2.1 不注册或实现该 worker，也不投射 Host cancel。

**测试覆盖:**
- `test_reserved_missing_host_returns_no_host_run_then_recovers` — reserved + Host missing → recover
- `test_active_host_returns_wait_never_recovers_or_creates_new_attempt` — CREATED/QUEUED/RUNNING → WAIT
- `test_active_host_wait_never_enters_model_twice` — active Host 不得造成第二次 Agent entry
- `test_terminal_reconciliation_never_calls_async_agent_entry` — reconcile 不调 async entry

**判定:** ✅ 无 blocker。NO_HOST_RUN vs HOST_ACTIVE_WAIT 互斥正确；active Host 行为有测试锁定；future Slice 2.2 owner 精确指定。

---

### Focus 5: correlation state transition, Host row disappearance, cancel/deadline priority, Host failed/unsettled retry, stale correlation behavior

**Correlation 状态机（§4.1）:**

| 对象 | 合法转换 | 触发者 |
|------|---------|-------|
| Correlation | reserved→host_created/host_running/terminal | query-before-retry observation |
| | host_created→host_running/terminal | |
| | host_running→terminal | |
| | terminal 吸收 | |

**Host row 消失后行为（§4.3.2）:**
- committed correlation 后 Host row 反向消失（曾 observed host_created/host_running/terminal 后 row 消失）→ `correlation_invariant` + `INVARIANT_FAILURE`
- correlation=reserved + Host missing → `NO_HOST_RUN`（不是 invariant failure，是预期窗口）

**Cancel/Deadline priority（§4.3.2）:** terminalize 按严格顺序执行：**cancel intent → deadline → Host terminal outcome**。cancel intent 先写 attempt/job cancelled + cancel receipt；否则 clock_timestamp() >= deadline_at 先写 attempt/job failed + deadline receipt；仅其后才写 Host success/failure/cancel。

**Host failed/unsettled retry（§4.3.2）:** Host failed/unsettled → 按既有 retry algorithm 写 failed/ready 或 failed terminal。如果 attempt 仍是 current attempt、no newer fence、recover 未 abandon → 正常写 receipt/event + retry；否则 → STALE_ATTEMPT。

**Stale correlation（§4.3.2）:** recover 先赢 job lock → abandon + ready/terminal → terminal reconciliation 只能追加 `correlation_stale_attempt` event → 返回 `STALE_ATTEMPT` → future worker 记录 safe stale observation，不执行。

**判定:** ✅ 无 blocker。Correlation 状态机完整；Host row 消失有 invariant 分支；cancel/deadline/host outcome 优先级闭合；failed/unsettled retry 和 stale correlation 路径正确。

---

### Focus 6: exact public DTO fields/signatures, DDL/grants/RLS, allowlist, ExecutionContract test fixture, named fault matrix, shared engine lifecycle

**Public DTO 验证:**
- 14 个 frozen+slots dataclass DTO（§3.2），全部 UTC aware、UUID caller-generated、no Any/object
- 9 个 JobService 方法签名（§3.2）与 §4.2 算法一一对应
- `JobStoreProtocol` 精确声明 11 个方法（§3.2）

**DDL/Grants/RLS 验证:**
- 7 张表完整 DDL（§5），逐表列级 UPDATE grants 精确覆盖可变列
- immutable 字段（identity/payload/fence/token/idempotency key/correlation identity）不可 app role UPDATE
- append-only 表（receipts/events）无 UPDATE grant
- 7 张表均 ENABLE+FORCE RLS，tenant_isolation policy 与既有 0001 模式一致

**代码证据:** `composition.py:59-71` 确认 `PlatformServiceProtocol` 要求 `platform_service_name` property；`run_registry.py:188` 确认现有 `run_` + 12 hex 格式；`host_store.py:341-392` 确认 `write_transaction` 使用 `BEGIN IMMEDIATE`。

**Allowlist 验证:** §2 完整文件表（29 files），每个有 owner 和责任。

**ExecutionContract test fixture:** Fix artifact Controller J + §7 slice D 现在精确指定：
```python
from dayu.contracts.agent_execution import (
    AcceptedExecutionSpec, AcceptedModelSpec,
    ExecutionContract, ExecutionHostPolicy,
    ExecutionMessageInputs, ScenePreparationSpec,
)
ExecutionContract(
    service_name="durable_job_test",
    scene_name="durable_job_test",
    host_policy=ExecutionHostPolicy(session_key="durable-job-session", resumable=False),
    preparation_spec=ScenePreparationSpec(),
    message_inputs=ExecutionMessageInputs(user_message="durable job fixture"),
    accepted_execution_spec=AcceptedExecutionSpec(model=AcceptedModelSpec(model_name="test-model")),
)
```
代码证据: `tests/application/test_host_executor.py:58-61` 确认 `_minimal_accepted_execution_spec()` 的 exact 构造方式。

**Named fault matrix:** §8 列出 34+ 故障场景，每个有显式命名测试和 lane（unit/PG16 integration/SQLite integration/CLI/application），不允许以"已由相邻测试覆盖"替代。

**Shared engine lifecycle:** §6 重命名 `_build_production_identity_provider` → `_build_production_services_provider`，注入同一 session factory 到 `PostgresIdentityRepository` 与 `PostgresJobStore`；`InvestmentIdentityService` 仍是唯一 engine lifecycle owner；`PreparedHostRuntimeDependencies.close()` 经既有 lifecycle registration 仍是 sole exact-once owner。

**代码证据:** `startup_preparation.py:304-369` 确认现有 provider 构造、engine probe、atexit 协调器模式。

**判定:** ✅ 无 blocker。所有 DTO/signature/DDL/grants/RLS/allowlist/fixture/matrix/lifecycle 完整且一致。

---

### Focus 7: current Slice 2.1 no production worker/handler while Slice 2.2 future ownership remains implementable

**Plan 非目标（§1）:**
"不启动 scheduler、worker、Redis、CLI queue 命令、API、UI、业务 handler、Agent handler、source connector 或任何 Broker；不注册 production handler。"

**JobHandlerProtocol + JobHandlerRegistry（§3.2）:**
"本 slice 定义 JobHandlerProtocol（仅 descriptor 与 typed handle signature）和 JobHandlerRegistry（以 job_type 唯一注册并验证 descriptor exactness），作为 Master Slice 2.1 要求的稳定 API；production registry 保持为空，JobService 不调用 handler。"

**代码证据:** `executor.py:47-55` 确认 `run_agent_stream` 是 async；`host_execution.py:24-113` 确认 `HostExecutorProtocol` 8 methods（无 reserved_run_id，那是 plan 待新增的 keyword-only 参数）。同步 JobService 不能构造 ExecutionContract 或调 async entry — 这是架构硬约束。

**Slice 2.2 future ownership 明确指定:**
- §4.3.2: "future worker 的唯一 recovery 顺序是 list_expired → reconcile → only NO_HOST_RUN → recover"
- §4.3.2: "HOST_ACTIVE_WAIT 的 future owner 是 Slice 2.2 worker：以 host_active_reobserve_interval_seconds 重观测，deadline_at 为上界，到期 cancel_run，绝不 generic recover"
- §9: "scheduler polling/Redis degradation 和 backoff jitter 归 Slice 2.2"

**判定:** ✅ 无 blocker。Slice 2.1 不注册 handler/worker，Slice 2.2 owner 契约明确。

---

### Focus 8: plan is code-generation-ready for Flash without inventing state, transaction or test decisions

**Code-generation readiness 逐项验证:**

| 维度 | Plan 覆盖 | 可生成 |
|------|----------|-------|
| DTO 定义 | §3.2 精确字段+类型 | ✅ |
| Protocol 定义 | §3.1 RunRegistryProtocol, §3.2 JobStoreProtocol | ✅ |
| Public method signatures | §3.2 9 methods + §4.3 2 methods | ✅ |
| DDL | §5 7 tables + CHECK/FK/index | ✅ |
| Grants/RLS | §5 精确列级 | ✅ |
| Migration | §5 downgrade + fail closed | ✅ |
| State machines | §4.1 closed transitions | ✅ |
| Algorithms | §4.2 enqueue/claim/heartbeat/complete/fail/cancel/recover | ✅ |
| Correlation semantics | §4.3 两事务+两 decision | ✅ |
| Test fixture | §7 slice D ExecutionContract 精确字段 | ✅ |
| Named tests | §7 slice A-E 28+ tests | ✅ |
| Fault matrix | §8 34+ scenarios | ✅ |
| File allowlist | §2 29 files | ✅ |
| Composition | §6 renamed provider + shared factory | ✅ |

**未发明的决策:**
- 未发明新 state 或 transaction 模式（使用已有 PG transaction + SKIP LOCKED + FOR UPDATE 模式）
- 未发明新 test approach（使用已有的 fake future caller + real RunRegistry + real DefaultHostExecutor，同 `tests/application/test_host_executor.py` 模式）
- 未发明新 schema 增量（使用 `0003_durable_jobs.py` 迁移）
- 未发明新 composition 模式（使用已有 `PlatformComposition` + `PlatformServiceProtocol`）

**判定:** ✅ 无 blocker。Plan 足够具体，implementation agent 可直接生成代码。

---

## 3. Findings

**无 High 或 Medium findings。**

Plan 在 fix artifact 修正后，所有先前 false assumptions 已纠正，所有 8 个 adversarial focus areas 均经独立源码证据验证闭合。

---

## 4. Open Questions

无 material open questions。先前 review 的 open questions 均已在 fix artifact 中闭合：

- **Recover→Reconcile 生产调用时机**: §4.2.7 明确 "recover 本身不触发 reconcile；reconciliation 由 future worker recovery 路径负责"；§4.3.2 精确指定 "future worker 先 list expired correlations → terminal reconcile → only NO_HOST_RUN → generic recover"。归属 Slice 2.2 worker owner。✅ 已闭合。
- **CanonicalJobDocument 检查时机**: §7 slice B 的 `test_canonical_document_rejects_each_known_sensitive_key` 暗示构造期检查。§3.2 描述 canonical 格式约束。Implementation agent 可从测试和 DTO 定义推断。✅ 已闭合。
- **Host row 消失后 recover 路径**: §4.3.2 明确 "已记录 host_created/terminal 后 Host row 反向消失 → correlation_invariant + INVARIANT_FAILURE"。recover 不调 reconcile，Host row 消失由 reconcile 路径处理。✅ 已闭合。

---

## 5. Residual Risks

| 风险 | 归属 | 跟踪建议 |
|------|------|---------|
| External provider/tool exactly-once | Agent handler/connector owner | Slice 2.3+ |
| Scheduler polling/Redis degradation + backoff jitter | Scheduler owner | Slice 2.2 |
| Business payload schema/source health/notification | Business service owner | Slice 2.3 |
| HOST_ACTIVE_WAIT reobserve interval + deadline cancel delivery | Slice 2.2 worker owner | Slice 2.2 plan |

---

## 6. Final Plan Review Conclusion

**PASS**

Plan 在 fix artifact 修正后达到 code-generation-ready 标准。A–L closure 全部 verified（fix artifact 的 11 accepted + 3 rejected-with-reason 与 plan 文本一致）。8 个 adversarial focus areas 全部经独立源码证据验证闭合：

1. **Two-transaction claim then reserve**: 独立 public signatures，crash window 每种场景有明确收敛路径。
2. **live START_REQUIRED requires raw lease**: token-based fencing 完整，no-token observer 无法获得 START_REQUIRED。
3. **Terminal-only reconciliation vs recover**: job-row serialization 点闭合 race；newer attempt stale 路径正确；immutable receipt/event 有 DDL+grant 保护。
4. **NO_HOST_RUN vs HOST_ACTIVE_WAIT**: 互斥正确；active Host 行为有测试锁定；Slice 2.2 owner 精确指定。
5. **Correlation state transition**: 完整 closed state machine；cancel/deadline/host outcome priority 闭合。
6. **DTO/DDL/grants/RLS/allowlist/fixture/matrix/lifecycle**: 全部完整且一致。
7. **No production worker/handler**: 非目标明确；Slice 2.2 owner 契约完整。
8. **Code-generation-ready**: 足够具体，无需 invent new state/transaction/test decisions。

Open items: **0H / 0M / 0L**。计划可以进入实施。
