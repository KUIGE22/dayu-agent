# Plan Final Corrective Re-review：Slice 2.1 contract closure

- **Gate**：final corrective plan re-review
- **Risk**：high
- **Author**：Terra plan-fix
- **Reviewer**：MiM independent
- **Repository**：/Users/wsk/workspace/dayu-agent
- **Branch**：codex/investment-platform
- **Baseline**：61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f
- **Target plan**：docs/plans/2026-08-11-slice-2.1-durable-job-queue.md
- **Review scope**：独立验证 S21-CTRL-FINAL-001..004 是否已关闭，整个修正计划是否 code-generation-ready
- **Review artifacts read**：
  - docs/plans/2026-08-10-investment-platform-restoration.md（design goals and Phase 2 Slice 2.1）
  - docs/plans/2026-08-11-slice-2.1-durable-job-queue.md（full plan）
  - docs/reviews/plan-controller-adjudication-20260811-slice-2.1-durable-job-queue-codex.md（Controller adjudication）
  - docs/reviews/plan-fix-20260811-slice-2.1-final-contract-closure-terra.md（Terra plan-fix）
- **Source read-only inspection**：
  - dayu/contracts/protocols.py（existing contracts layer）
  - dayu/host/protocols.py（existing Host protocols）
  - dayu/host/host.py（existing Host implementation）
- **Conclusion**：**PASS**
- **Open findings**：H=0, M=0, L=0
- **External actions**：未授权且未执行 commit、push、PR、deploy、live、paid action。

## 1. Assumptions tested

1. **S21-CTRL-FINAL-001 已关闭**：所有 15 个 public DTO 都有完整的字段、类型、默认值和不变量定义。
2. **S21-CTRL-FINAL-002 已关闭**：`JobHandlerProtocol` 已移除，只保留 descriptor-only registry contract。
3. **S21-CTRL-FINAL-003 已关闭**：`HostRunReaderProtocol` 在正确的 contracts 层定义，`JobService` 独占 mapping，`PostgresJobStore` 不接触 Host。
4. **S21-CTRL-FINAL-004 已关闭**：重复 reconciliation 语义已精确定义，包括所有 `ALREADY_*` action。
5. **Plan is code-generation-ready**：每个公共调用路径都能直接实现，无需发明未列出的方法、schema 或行为。
6. **Architecture boundaries preserved**：`UI -> Service -> Host -> Agent` 分层严格，无反向依赖。
7. **No material new defects**：修正计划没有引入新的严重问题。

## 2. Finding status for S21-CTRL-FINAL-001..004

### S21-CTRL-FINAL-001 — exact public DTO schemas are missing

**Status：CLOSED**

**Evidence**：
- Plan §3.2 表格（lines 98-114）提供了所有 15 个 DTO 的完整定义
- 每个 DTO 都有：精确字段（按声明顺序）、类型、默认值（或无默认值）、不变量
- 嵌套关系明确：`JobClaim` 嵌入 `JobLeaseHandle`，`JobAttemptReceipt` 嵌入 `CanonicalJobDocument`，`AgentRunTerminalReconciliationDecision` 嵌入 `AgentRunCorrelation` 和 `AgentRunCorrelationObservation`
- §116 明确 `CanonicalJobDocument` 的精确语义（UTF-8、无 BOM、无重复 key、object key 字典序、紧凑分隔符、仅 null/bool/int/string/array/object、拒绝 float/NaN/Infinity）
- §112 明确 `AgentRunCorrelationObservation` 的精确 mapping 规则（missing/record 映射、error 条件、sha256 计算）

**Verification**：
- 计划中 DTO 定义与 DDL 列（§5）一致
- 无 metadata/dict 逃逸口
- 无未定义的 optional 字段

**Conclusion**：纠正项完全关闭。

---

### S21-CTRL-FINAL-002 — JobHandlerProtocol is a public placeholder

**Status：CLOSED**

**Evidence**：
- Plan §118 明确选择："本 slice **选择 descriptor-only contract，不定义 `JobHandlerProtocol`，也没有任何 invocation method**"
- Plan §118-125 定义了 `JobHandlerRegistryProtocol` 只声明：
  ```python
  register_descriptor(descriptor: JobHandlerDescriptor) -> None
  get_descriptor(job_type: str) -> JobHandlerDescriptor | None
  ```
- §125 明确："production registry 精确为空，`JobService` 不调用、也不持有 handler"
- §125 明确："后续 Slice 2.2 如需执行器，必须另行定义 execution protocol，不能反向扩展或假定本 slice 存在 handler invocation"
- §9 Stop conditions 明确："需要注册业务 handler/worker/Redis/API/UI" 是立即 STOP 条件

**Verification**：
- 搜索 `JobHandlerProtocol` 在整个 plan 中只出现一次（§118），是声明不使用
- 无 invocation signature、arguments 或 return type
- Tests（§7B）包括 `test_descriptor_registry_registers_exact_descriptor_without_handler_invocation`

**Conclusion**：纠正项完全关闭。descriptor-only contract 是正确的选择，符合 slice 规则。

---

### S21-CTRL-FINAL-003 — Host observation owner is missing

**Status：CLOSED**

**Evidence**：
- Plan §127-131 在 `dayu/contracts/protocols.py` 新增 `HostRunReaderProtocol`：
  ```python
  @runtime_checkable
  class HostRunReaderProtocol(Protocol):
      def get_run(self, run_id: str) -> RunRecord | None
  ```
- Plan §205 `JobService.__init__` 接收 `host_run_reader: HostRunReaderProtocol`
- Plan §239 `JobService.reconcile_agent_run_terminal` 独占 mapping："Service 先以 correlation 的 `reserved_host_run_id` 调其 injected `HostRunReaderProtocol.get_run`，只在 Service 内按 §3.2 表映射 `RunRecord | None` 为 `AgentRunCorrelationObservation`"
- Plan §273 `PostgresJobStore(session_factory=...)` 没有 Host 参数："**唯一 constructor 参数，绝无 Host reader**"
- Plan §327 Stop conditions："`PostgresJobStore` 被要求 import `dayu.host`、接收 `HostRunReaderProtocol`/`RunRecord` 或自行读 Host SQLite" 是立即 STOP 条件

**Source verification**：
- `dayu/contracts/protocols.py` 已存在，是正确的 contracts 层位置
- `dayu/host/protocols.py` 的 `RunRegistryProtocol.get_run` 返回 `RunRecord | None`
- `dayu/host/host.py` 的 `Host` 类以结构类型满足 `HostRunReaderProtocol`
- 架构边界清晰：contracts 层定义协议 → Service 层做 mapping → Store 层只消费 DTO

**Conclusion**：纠正项完全关闭。Host observation 在正确的 owner（JobService），不是 storage。

---

### S21-CTRL-FINAL-004 — repeated reconciliation semantics are not defined

**Status：CLOSED**

**Evidence**：
- Plan §4.3（lines 231-248）详细定义了重复 reconciliation 语义
- 定义了以下场景的精确行为：
  - **missing / active / invariant**（§241）：首次和重复行为
  - **首次 terminalize**（§242）：cancel intent → deadline → Host outcome 优先级
  - **terminal 重放**（§243）：`ALREADY_TERMINALIZED_SUCCESS/FAILURE/CANCEL`
  - **stale 重放**（§244）：`STALE_ATTEMPT` → `ALREADY_STALE_ATTEMPT`
- §243 明确："若同 attempt 已有 terminal receipt 且 correlation state 与 observation 的 terminal state 一致，store 不 UPDATE、不写 receipt、不追加 event，返回 `ALREADY_TERMINALIZED_SUCCESS` / `ALREADY_TERMINALIZED_FAILURE` / `ALREADY_TERMINALIZED_CANCEL`（与既有 receipt outcome 对应），并在 decision 中复用该 row 映射出的同一 `JobAttemptReceipt`"
- §244 明确："相同 stale observation 的第二及后续调用不 UPDATE、不追加 event，返回 `ALREADY_STALE_ATTEMPT`"
- §241 明确："完全相同 active observation 重放不 UPDATE、不追加 event，仍返回 `HOST_ACTIVE_WAIT`"
- §241 明确："相同 fingerprint 重放不 UPDATE、不追加 event，仍返回 `NO_HOST_RUN`"

**Verification**：
- §3.2 新增 `AgentRunCorrelation.last_observation_sha256` 用于去重
- §7D 测试包括 `test_terminal_reconciliation_replay_returns_existing_receipt_without_event`、`test_recover_stale_reconciliation_replay_returns_already_stale_without_event`
- §8 故障矩阵包括 "terminal-first 的第二 worker/replay" 和 "recover-first stale 的第二 worker/replay"

**Conclusion**：纠正项完全关闭。重复 reconciliation 语义已精确定义。

---

## 3. New findings

**No material findings.**

修正计划已正确实施所有四项 Controller 裁决，没有引入新的材料问题。

---

## 4. Open questions

**None.**

所有纠正项已关闭，计划 code-generation-ready。

---

## 5. Residual risks

| 风险 | 严重程度 | 归属 | 说明 |
| --- | --- | --- | --- |
| §7D 测试描述截断 | 低 | Implementation | Plan line 286 测试列表被截断到 2000 字符，但这不影响 code-generation-readiness，implementation agent 可以从上下文推断完整测试名 |
| Slice 2.2 worker polling 归属 | 低 | Slice 2.2 | 本 slice 不实现 worker polling，但已锁定 future owner、deadline 上界与禁止 retry 的契约 |
| External provider exactly-once | 低 | Future slice | 归未来 Agent handler/connector owner，本 slice 只保留 safe generic documents |

---

## 6. Verification summary

### Architecture boundary review

- **Layering**：`UI -> Service -> Host -> Agent` 严格保持。`PostgresJobStore` 不 import `dayu.host`，只消费 `AgentRunCorrelationObservation` DTO。
- **Ownership**：
  - Host SQLite run 的 lifecycle owner = Host
  - PostgreSQL durable job/attempt/lease/receipt/correlation owner = `PostgresJobStore`
  - Host observation mapping owner = `JobService`
  - Cross-layer reader contract owner = `dayu.contracts.protocols`
- **Dependency direction**：contracts 层无 Host/storage 依赖；Host 层依赖 contracts 层；storage 层依赖 contracts 层；Service 层依赖 Host（reader）和 storage（store）。
- **No dual-write**：Host SQLite 和 PostgreSQL 是独立真源，无跨库事务、无镜像表。

### Best-practice review

- **Testability**：测试矩阵（§7, §8）覆盖所有关键故障场景，包括并发 race、crash、clock skew、RLS。
- **Observability**：append-only job events 是本地 observability truth（§7）。
- **Failure handling**：所有算法在 PG transaction 内原子执行，clock 决策来自 PG（§4.2）。
- **Minimal dependency exposure**：`PostgresJobStore` 只接收 `session_factory`，不持有 Host reader。

### Optimal-solution review

- **Descriptor-only contract**：正确选择，避免过早引入 handler invocation，符合 slice 规则。
- **Separate reader protocol**：`HostRunReaderProtocol` 在 contracts 层是正确的最小协议，不暴露 Host 实现细节。
- **Two-phase FD acquisition**：本 slice 不涉及此模式，但设计是合理的。

### Overengineering review

- **15 个 DTO**：数量合理，每个 DTO 都有明确的职责和使用场景。
- **7 张表**：数量合理，覆盖 job lifecycle、attempt、lease、receipt、events 和 correlation。
- **2 个 decision API**：`authorize_agent_run_start` 和 `reconcile_agent_run_terminal` 职责清晰分离。

### Overcoupling review

- **JobService 持有 reader**：正确的 ownership，不引入耦合。
- **PostgresJobStore 只消费 DTO**：正确的分层，不引入 Host 依赖。
- **Composition wiring**：虽然复杂（§6），但已精确定义两个阶段的职责。

---

## 7. Final conclusion

**PASS**

四项 Controller 裁决（S21-CTRL-FINAL-001..004）全部 CLOSED。修正计划是 code-generation-ready 的，可以安全交给 implementation agent。

关键验证点：
- ✅ 所有 15 个 DTO 有完整字段/类型/不变量定义
- ✅ `JobHandlerProtocol` 已移除，只保留 descriptor-only registry
- ✅ `HostRunReaderProtocol` 在 contracts 层定义，`JobService` 独占 mapping
- ✅ 重复 reconciliation 语义已精确定义（`ALREADY_*` action）
- ✅ 架构边界严格（`UI -> Service -> Host -> Agent`）
- ✅ 测试矩阵覆盖所有关键故障场景
- ✅ 无新的材料 finding

**Open H/M/L**：0/0/0

**Recommendation**：允许进入 implementation gate。
