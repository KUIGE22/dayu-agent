# Final Codegen Closure：Slice 2.1 durable job queue（Terra，Final3）

- **Gate**：final3 bounded corrective plan-fix；`FINAL REVIEW FINDINGS FIXED / AWAITING FINAL DUAL PLAN RE-REVIEW`
- **Branch / baseline**：`codex/investment-platform` / `61e4eb3b1995a5df43d805e4c5ffc67b2b7de27f`
- **Target**：`docs/plans/2026-08-11-slice-2.1-durable-job-queue.md`
- **Accepted source findings**：`S21-CTRL-FINAL3-001..005`，来源为
  `docs/reviews/plan-controller-final-codegen-adjudication-20260811-slice-2.1-durable-job-queue-codex.md`；
  `S21-CTRL-FINAL2-001..007` 持续 CLOSED-IN-PLAN。
- **Scope / non-goals**：本工件包含 Controller final3 的最小 allowlist closure；只改 target plan、master Slice 2.1 的 Allowed/API/Invariants/Completion/Tests 五行与本工件；未改 production、tests、README 或 source review artifact；未启动 Gateflow、implementation、tests、code review、commit、push、PR、deploy、Docker 或 PostgreSQL。

## 1. Root-cause decision 与唯一 owner DAG

根因不是 Host reader seam 本身，而是原计划让 `PostgresJobStore` 必须构造 Host-owned
DTO/实现 Host-owned Protocol，同时现有 `tests/investment/test_architecture_boundaries.py`
对 `storage/**` 的 AST guard 禁止 `dayu.host` 与 `dayu.contracts` import（`TYPE_CHECKING`
也受检）。这会使实现者没有合法 import path；不能用 re-export、wrapper、lazy import 或测试豁免解决。

Controller follow-up 又确认一处独立、同样阻断 codegen 的 allowlist 冲突：target 先禁止修改
`dayu/host/protocols.py`，却在 §3.1 要求在其真实 owner
`RunRegistryProtocol`（`dayu/host/protocols.py:557`）新增 reserved ensure contract。该协议变更
只能由该 owner 承载，不能移动到 PG job owner 或绕过 allowlist；已把该文件加入 Host reserved
identity allowlist，并明确其改动仅限 reserved DTO/error/method。

第二个 Controller follow-up 还确认两项直接冲突：其一，两个 reserved identity error 被调用方
依赖 `.record`，仅 class annotation 不会在 `RuntimeError(record)` 时赋值；其二，store constructor
被锁为 `session_factory`，不能执行原文的 registry lookup。二者现分别收敛为 Host protocol owner
的显式 safe constructor，以及 services-owned concrete registry 的 Service-before-store enqueue gate。

唯一选择如下：

```text
dayu.investment.domain.jobs
  ├─ 15 DTO / enum / stable errors / canonical document / generic receipt builder
  ├─> dayu.investment.storage.protocols.JobStoreProtocol
  │     └─> dayu.investment.storage.postgres_jobs.PostgresJobStore
  └─> dayu.services.job_service.JobService
        ├─ JobHandlerRegistryProtocol / concrete empty JobHandlerRegistry
        └─ HostRunReaderProtocol.get_run -> Host (read-only lifecycle observation)
```

因此 storage 只依赖 pure investment domain；Service 是唯一可 import `RunRecord` 并将其投影为
domain `HostRunObservationState` 的位置；Host 只保留 reserved-run/Agent 生命周期真源。该
选择保持 master 的 Host 强约束与 PG job 真源，不改变 master design，也不引入跨库事务或 dual-write。

## 2. Finding closure map

| Finding | 状态 | 精确计划落点 | 已闭合的决定与验证 |
| --- | --- | --- | --- |
| S21-CTRL-FINAL2-001 | **已修复** | §2 owner/allowlist/DAG/主计划边界说明；§3.1 Host protocol owner/errors；§3.2 service registry owner/enqueue；§4.2.1；§6；§7A/B；§8；§9 | `dayu.host.protocols` 只承载真实 owner 的 reserved ensure DTO、two-error constructor/method；两 error 均以固定 safe args 与精确 `.record` 字段表达。job DTO/enum 只在 `investment.domain.jobs`，`JobStoreProtocol` 只在 `investment.storage.protocols`，registry Protocol/concrete 与 Service 只在 `services.job_service`。Service 先 registry gate 后才 call store；`PostgresJobStore` 不得 import Host/contracts 或持 registry。现有 AST guard 保持，不加豁免；测试锁定 Host error payload、registry owner、empty production registry、Service-before-store 与 import guard。 |
| S21-CTRL-FINAL2-002 | **已修复** | §3.2 `get_agent_run_correlation` signature/语义；JobService exact sequence；§4.3.2；§7D/§8 | 增加 tenant-scoped `get_agent_run_correlation(scope, correlation_id) -> AgentRunCorrelation`。Service 每次 direct/live/restart/replay 都遵循 get correlation → Host get_run → strict mapping → store reconcile；not-found 与 invariant、cross-tenant、无 cache 均固定。 |
| S21-CTRL-FINAL2-003 | **已修复** | §4.1 `correlation_missing` 唯一分支；§4.2.3 heartbeat；§4.3.1；§7C/§8 | heartbeat 在 `now >= deadline` 时同事务 attempt/job failed、release、generic receipt/event 后抛 `JobDeadlineExceededError`，不会返回 past-expiry claim；`correlation_missing` 仅在有效 lease 但 start authorization 找不到 committed correlation 时返回 `INVARIANT_FAILURE`。 |
| S21-CTRL-FINAL2-004 | **已修复** | §5 `job_leases` DDL；migration grants/CAS/trigger；§7B/§8 | 选择 versioned mutable lease：补 `updated_at/version`，single-release pair CHECK、CAS 与 release trigger，grant 精确包含这两个并禁止 release 后修改。 |
| S21-CTRL-FINAL2-005 | **已修复** | §3.2 Host observation state；§4.3.2 first terminalize；§7D/§8 | `UNSETTLED → host_unsettled / failed / host_run_unsettled / TERMINALIZED_FAILURE` 唯一映射，随后与 Host failed 同一 retry policy；禁止降格写 `host_failed` 或 `host_run_failed`。 |
| S21-CTRL-FINAL2-006 | **已修复** | §3.2 generic builder exact schema/key/value table；§4.2.3–7；§5 receipt DDL；§7B/§8 | 固定 generic schema/version、8-key canonical object、result 仅 hash reference、所有 non-Host outcome builder、strict combinations、immutable replay bytes/hash；DDL 区分 generic 与 Host receipt schema/key set。 |
| S21-CTRL-FINAL2-007 | **已修复** | §3.2 `JobRecoveryResult` invariant；§4.2.5–7；§7C/§8 | handler fail retry=`failed/ready`；lease-expiry retry=`abandoned/ready`；cancel-intent recover=`cancelled/cancelled`；deadline/retry-exhausted=`failed/failed`。每种 receipt outcome/safe code/next_available_at 与持久 attempt/job state 同步。 |

## 3. Final3 closure map

| Finding | 状态 | 精确计划落点 | 已闭合的决定与验证 |
| --- | --- | --- | --- |
| S21-CTRL-FINAL3-001 | **已修复** | target §3.2 `JobStoreProtocol`/`JobService.recover`；§4.2.7–8；§4.3；§8；§9 | bulk `recover(scope)` 以 SQL `NOT EXISTS agent_run_correlations` 排除所有 attached attempt。新增仅 Store Protocol 的 exact `recover_agent_run_after_no_host(scope, correlation_id, observation_sha256)`；同一 PG transaction 锁 job/attempt/lease/correlation，仅 current reserved + persisted missing fingerprint matching + expired lease + no later fence/attempt 才 mutate，其他前提变化 `None` 且零 mutation。Service 固定为 sorted correlation enumerate → get/Host/strict-map/reconcile → 仅 `NO_HOST_RUN` targeted → 一次 generic；结果顺序固定，active/terminal/stale/invariant 不入 recover。PG two-engine barrier 锁 active/no-host/no-correlation 隔离与 fingerprint/state/fence no-op。 |
| S21-CTRL-FINAL3-002 | **已修复** | target §4.2.4、§4.2 matrix、§8 | `complete` 明定 `cancel intent → deadline → success`；同时命中必写 cancelled receipt/event，不写 deadline/success receipt/event；具名 PG test 锁定。 |
| S21-CTRL-FINAL3-003 | **已修复** | target §3.1、§8 | `RunRegistry.ensure_reserved_run` 是唯一 Host validator，在 SQLite transaction/写入前拒绝非 `run_` + 32 位小写 hex，固定 `ValueError("invalid_reserved_run_id")` 且零 Host side effect；executor/Host 仅委托；invalid matrix/no-write test 锁定。 |
| S21-CTRL-FINAL3-004 | **已修复** | target §4.2.2、§8 | ready deadline 固定 job=`failed`、`safe_failure_code=deadline_exceeded`、唯一 `job_deadline_exceeded` event、无 attempt/lease/receipt；重放不追加 event；具名 PG test 锁定。 |
| S21-CTRL-FINAL3-005 | **已修复** | master Slice 2.1 Allowed/API/Invariants/Completion/Tests 五行 | 五行现高层链接 target，并同步 investment pure domain + storage protocol/store + Service registry/reader + Host reserved identity、descriptor-only、execution protocol/handler 留给 Slice 2.2/2.3、missing correlation 不补建旧 attempt、correlation-safe Service recovery；Phase 1 history 与其它 Phase 2 slice 未改。 |

## 4. Internal-consistency audit

本轮只做了允许的只读/文档检查与三份允许文档的定向修订：

- 完整复读 master Phase 2/Slice 2.1、target、Controller final-codegen adjudication、source Flash re-review 与本工件；直接文本证据确认旧 generic recover 无 correlation 排除、master 五行仍有旧 owner/API/rebuild drift，故 Final3 动机成立。
- 搜索并人工核对 `recover_agent_run_after_no_host`、`NOT EXISTS`、`NO_HOST_RUN`、stable order、`cancel intent → deadline → success`、`invalid_reserved_run_id`、`job_deadline_exceeded`、`START_REQUIRED` TOCTOU、`distributed exactly-once` 与 target 链接；三份文档的 owner、API、状态机、测试、STOP 与 residual 一致。
- 审计 `S21-CTRL-FINAL2-001..007` 的原落点仍保留：Host reserved protocol/error `.record`、services descriptor-only registry/Service-before-store、strict correlation lookup/mapping、heartbeat deadline、versioned lease、UNSETTLED mapping、generic receipt 与 recovery result 均未回退；未引入 re-export、wrapper、第二 contract owner、Host storage import 或业务 handler。
- 三个允许文件的 diff 已检查为仅计划/closure 文本；路径、LF 行尾、尾随空白与 whitespace diff 均纳入本轮收尾审计。未运行 pytest、pyright、ruff、Docker 或 PG16 integration：本 gate 明确禁止 tests、实现和 PostgreSQL actions；这些仍是后续 implementation gate 的计划内验证，而非本工件的完成证据。

## 5. Open questions、residual risk 与 stop status

- **Blocking open questions**：无。Final3 五项均在用户指定的三文档 allowlist 内闭合；master 只改指定五行，未触发 Slice 2.2/2.3 或其它产品边界变更。
- **Slice 2.1 residual owner**：已取得 `START_REQUIRED` 后、Host ensure 前跨 lease 的跨 store TOCTOU 不可由本 slice 消除；只承诺同一 correlation 的 Host ensure at-most-once，绝不宣称 distributed exactly-once。Host/PG crash-window、receipt immutability、RLS/DDL、deadline/recovery 状态机由本 slice implementation + PG16 integration 验证负责。
- **Later-slice owner**：scheduler polling、Redis degradation、active Host re-observe/cancel delivery/governance 归 Slice 2.2；业务 payload schema/source health/notification 归 Slice 2.3；外部 provider/tool exactly-once 归未来 Agent handler/connector owner。
- **Next entry point**：仅可进入独立 final dual plan re-review；re-review 必逐项裁决 `S21-CTRL-FINAL2-001..007` 与 `S21-CTRL-FINAL3-001..005`，任一未关闭高/中 finding 均使计划退出 candidate。

## 6. Final4 corrective closure

| Finding | 状态 | 精确计划落点 | 已闭合的决定与验证 |
| --- | --- | --- | --- |
| S21-CTRL-FINAL4-001 | **FIXED-IN-PLAN / AWAITING CLOSURE-ONLY RE-REVIEW** | target §7D recovery branch；其规范文本逐字复用 §3.2 `JobService.recover(scope)` | §7D 已删除“仅在 `NO_HOST_RUN` 后 generic、不得在 `HOST_ACTIVE_WAIT` 后 generic”的批次级旧条件。排序 expired committed correlations 后逐条 terminal-only reconciliation；仅 `NO_HOST_RUN` 进入 targeted `recover_agent_run_after_no_host`；`HOST_ACTIVE_WAIT`、terminal、stale、invariant 不进入 targeted，也不作为 generic 的输入；全部 correlations 枚举完成后始终且仅调用一次 `job_store.recover(scope)`。该 generic 的 §4.2.7 SQL `NOT EXISTS agent_run_correlations` 仅收敛无 committed correlation 的 attempt；mixed active + `NO_HOST_RUN` + no-correlation batch 稳定返回 targeted results 后接 generic results。 |
| S21-CTRL-FINAL4-002 | **FIXED-IN-PLAN / AWAITING CLOSURE-ONLY RE-REVIEW** | target §7 A/B/C/D 的 `Tests` 清单 | Controller 指定的 16 个既有测试名已按 A/B/C/D = 1/5/3/7 补入各自 implementation slice：A reserved-ID validator；B disabled definition、RLS/grant/upgrade；C empty claim、ready deadline、complete tiebreak；D missing replay、Host failed/unsettled/cancelled、correlation invariant 与三个 correlation-safe recovery tests。未改 §8、算法、测试名或 completion gate。 |

## 7. Final4 review-source disposition、scope 与下一 gate

- **MiM disposition**：其 `PASS / 0/0/0` 对 FINAL2/FINAL3、master、DAG、signature、状态机与 residual 的核验持续作为有效支持证据；其“无 open finding”结论仅就本轮被 Controller 对 FINAL4-001/002 的直接文本证据覆盖。
- **Flash disposition**：其 `FAIL / 0/0/1` 的 L-01 全部接受并映射为 `S21-CTRL-FINAL4-002`；FINAL2/FINAL3 closure 与其余 non-finding 结论保持有效。
- **历史保留与本轮范围**：本工件第 1–5 节的 FINAL2/FINAL3 历史原样保留。本轮 write set 严格只有 target plan 与本工件；master 五行、production、tests、README、source reviews 与其它 artifacts 均冻结。未运行 pytest、pyright、Ruff、Docker 或 PostgreSQL，也未执行 implementation、commit、push、PR、live 或 paid action。
- **状态与下一 gate**：target 状态为 `FINAL REVIEW OBSERVATIONS FIXED / AWAITING FINAL CLOSURE RE-REVIEW`。下一步只能由独立 MiM + Flash 执行 closure-only re-review；open H/M/L 未归零前不得接受计划、进入 implementation 或 commit。
