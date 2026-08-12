# Slice 2.3 Corrective Plan Review（MiMo independent）

- **Reviewer**: MiMo (independent corrective plan review)
- **日期**: 2026-08-12 13:48:36 UTC
- **Gate**: Slice 2.3 PLAN CORRECTIVE / high risk
- **基线**: `0db6c7b63608a15cd157f842a5be772799fdacd9`
- **目标计划**: `docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- **SHA-256**: `281f0a753423df5142d76a9cf2597b143e8c32bea5f8d4c70a3e2c691b7f8e23`
- **设计真源**: `docs/plans/2026-08-10-investment-platform-restoration.md`
- **初审**: `docs/reviews/plan-review-20260812-122255-slice-2.3-source-connectors-health-mimo.md`（PASS-WITH-RISKS，H0/M1/L2）
- **Controller纠偏**: `docs/reviews/plan-fix-20260812-slice-2.3-source-connectors-health-codex.md`
- **性质**: 独立只读 adversarial plan review；不参考 DeepSeek corrective 结论；不修改 target/master/code/tests。

## Assumptions Tested

1. `JobExecutionHandlerProtocol.execute` 当前签名只传 `(request, cancellation)`，不含 `TenantScope`（代码验证：`job_service.py:151-168`，精确2参数）
2. `JobService.execute_claim` 已有 `scope: TenantScope` 参数并验证 `claim.tenant_id == scope.tenant_id`（代码验证：`job_service.py:576-639`，line 605）
3. `JobHandlerRegistryProtocol` 当前无 `seal()`/`is_sealed` 方法（代码验证：`job_service.py:230-262`，仅 `register_descriptor` + `get_descriptor`）
4. `JobExecutionRegistry` 当前无 `seal()` 方法（代码验证：`job_service.py:318-343`，无 seal 相关）
5. `ScheduleStoreProtocol` 当前无 `ensure_registered` 方法（代码验证：`protocols.py:614-713`，仅有 `register`）
6. `ScheduleService` 当前无 `ensure_registered` 方法（代码验证：`schedule_service.py:866-891`，仅有 `register`）
7. `FinsService.submit()` 通过 Host 执行（代码验证：`fins_service.py:39-72`，调用 `host.run_operation_sync/stream`）
8. `DefaultFinsRuntime` 已有 `cancel_checker` 参数（代码验证：`service_runtime.py:690`，`execute` 方法签名）
9. `FinsIngestionService.download_stream` 是 plain async generator，无显式 aclose（代码验证：`ingestion/service.py:74-115`，`async for event in self._backend.download_stream(...): yield event`）
10. `_iter_stream_events` 是 plain async generator，无显式 aclose（代码验证：`service_runtime.py:3101-3137`，`async for event in stream: ... yield`）
11. 0001 `source_sync_runs` 有 11 列，0005 新增列 nullable（代码验证：`models_identity.py:332-388`）
12. 0001 `source_health_snapshots` 有弱二列 FK `(tenant_id, sync_run_id)`（代码验证：`models_identity.py:420-449`）
13. `source_subscriptions` 三个 partial unique index 均不含 `source_definition_id`（代码验证：`models_identity.py:294-329`）
14. ORM metadata 当前 15 个 table（代码验证：15个 PlatformBase subclass: Organization, Company, Security, User, SourceDefinition, SourceSubscription, SourceSyncRun, SourceHealthSnapshot, WorkspaceImportMarker, ResearchBundleLocator, Role, Permission, UserRole, RolePermission, ApiToken）
15. `job_runs` 表有 `current_attempt_number` 而非 `current_attempt_id`（代码验证：`0003_durable_jobs.py:191`）
16. `SafeJobErrorCode` 当前无 `SOURCE_INVALID`/`SOURCE_OPERATION_BUSY`/`SOURCE_INTERRUPTED`（代码验证：`jobs.py:148-162`，现有12个值）

## Findings

### CORR-001-未修复-[高]-§6.1 terminal transaction lock order 未指定，存在 deadlock 风险

- **位置**: §6.1 handler 顺序；§6.2 步骤 6-7
- **问题类型**: 并发恢复风险
- **当前写法**: §6.1 描述"每次 acquire/terminal commit 都以相同锁序读取 live Job lease：job_run -> job_attempt -> job_lease -> source_operation -> subscription -> health_state。"§6.2 步骤 6 说"收到 Fins result 后开启 terminal transaction，重新验证 live attempt lease、generation、subscription/version/status 与 frozen snapshot。"
- **反例/失败场景**: Handler 在 Fins 调用期间不持 PG transaction（§6.2 步骤 5）。收到 Fins result 后开启 terminal transaction 并重新验证。但 terminal transaction 的 lock order 未明确。如果两个并发 handler（attempt A 和 attempt B）同时为同一 subscription 的不同 job 提交 terminal，且 lock order 不一致（一个先锁 operation 再锁 subscription，另一个反过来），会导致死锁。更具体：Handler A 持有 operation lock 等待 subscription lock；Handler B 持有 subscription lock 等待 operation lock。
- **为什么有问题**: §6.1 声称"相同锁序"但未指定 terminal transaction 内的具体 lock acquisition order。实现者可能按不同顺序获取锁，导致真实 deadlock。这是并发测试无法覆盖的 liveness 问题——即使测试通过，生产并发仍可能死锁。
- **直接证据**: §6.1（"每次 acquire/terminal commit 都以相同锁序"）；§6.2 步骤 6（"开启 terminal transaction，重新验证"）；无具体 SQL lock order 或 `FOR UPDATE` 指定。
- **影响**: 生产并发 handler 死锁；PG 回滚事务；source terminal 未提交但 operation 保留 ACTIVE；后续 attempt 无法 acquire。
- **建议改法和验证点**: §6.1 显式列出 terminal transaction 的 lock order，例如：`LOCK source_sync_operations ROW EXCLUSIVE` → `LOCK source_subscriptions ROW EXCLUSIVE` → `LOCK source_health_states ROW EXCLUSIVE`（或等价的 `SELECT ... FOR UPDATE` 序列）。同时要求 §6.2 步骤 6 明确：terminal transaction 必须先锁 operation，再锁 subscription，最后锁 health_state，且在同一事务内完成所有 DML。测试验证：两个并发 handler 同时提交 terminal 不死锁。
- **修复风险**: 低
- **严重程度**: 高

### CORR-002-未修复-[高]-§8.2 operation FK 依赖 job_attempts 新 UNIQUE 约束但 migration ordering 未指定

- **位置**: §8.2 job_attempts 扩展；§8.3 operation composite FK
- **问题类型**: 迁移 hazard
- **当前写法**: §8.2 说"job_attempts 新增 UNIQUE(tenant_id, job_run_id, id)"。§8.3 说"operation (tenant,job_run,owner_attempt) -> job_attempts(tenant,job_run,id)"。
- **反例/失败场景**: 0005 migration 必须先创建 `UNIQUE(tenant_id, job_run_id, id)` 约束，然后才能创建 FK `(tenant_id, job_run_id, owner_attempt_id) -> job_attempts(tenant_id, job_run_id, id)`。如果 migration 脚本先创建 FK 再创建 UNIQUE，PostgreSQL 会拒绝 FK 创建（因为 parent key 不存在）。此外，`job_attempts.id` 是主键（UUID），`(tenant_id, job_run_id, id)` 作为 UNIQUE 是冗余的（因为 `id` 已唯一），但 PostgreSQL 要求 FK parent 必须是 UNIQUE 或 PRIMARY KEY。当前 `job_attempts` 的唯一约束是 `UNIQUE(tenant_id, job_run_id, attempt_number)`，不包含 `id` 列。
- **为什么有问题**: plan 没有指定 DDL 操作顺序。实现者可能按任意顺序创建约束，导致 migration 失败。这是一个 code-generation-ready plan 的必备细节。
- **直接证据**: §8.2（"job_attempts 新增 UNIQUE(tenant_id, job_run_id, id)"）；§8.3（"operation (tenant,job_run,owner_attempt) -> job_attempts(tenant,job_run,id)"）；`0003_durable_jobs.py:191`（现有 `current_attempt_number` 但无 `(tenant_id, job_run_id, id)` UNIQUE）。
- **影响**: Migration 脚本在有数据的数据库上失败；实现者需要调试 DDL ordering。
- **建议改法和验证点**: §8.2 显式声明："0005 migration 必须先 `ALTER TABLE job_attempts ADD CONSTRAINT uq_job_attempts_tenant_run_id UNIQUE (tenant_id, job_run_id, id)`，然后才能创建 operation 的 FK。" 同时声明该 UNIQUE 约束是冗余的（因为 `id` 已是 PK），但为 FK parent 而创建。验证：`alembic upgrade head` 在有 job_attempts 数据的数据库上成功。
- **修复风险**: 低
- **严重程度**: 高

### CORR-003-未修复-[中]-§4.4 aclose chain 缺少 FinsIngestionService 的 finally aclose 规格

- **位置**: §4.4 Cancellation 与嵌套 stream owner
- **问题类型**: 架构边界 / 最佳实践偏离
- **当前写法**: §4.4 说"同时修改 dayu/fins/service_runtime.py、dayu/fins/ingestion/service.py、dayu/fins/ingestion/pipeline_backends.py。每层把 inner stream 保存为唯一局部 owner，并在 finally await inner.aclose()；禁止依赖 GC。"
- **反例/失败场景**: 当前 `FinsIngestionService.download_stream`（`ingestion/service.py:74-115`）是 plain async generator：`async for event in self._backend.download_stream(...): yield event`。如果外层 generator 被关闭（CancelledError），`async for` 循环退出，但 `self._backend.download_stream()` 返回的 async generator 不会被显式 aclose。同样，`_iter_stream_events`（`service_runtime.py:3101-3137`）也是 plain async generator：`async for event in stream: ... yield`。外层关闭时 `stream` 不会被显式 aclose。Plan 列出了3个文件但没有指定每个文件的具体 aclose 模式。实现者可能只在 `_execute_stream` 层加 aclose，而忽略 ingestion service 层。
- **为什么有问题**: 嵌套 async generator 的 aclose 语义是 Python 的已知陷阱。外层 generator 的 `async for` 退出不会自动关闭内层 async generator（取决于 Python 版本和实现）。plan 需要明确每个层的 aclose 模式，否则实现者可能遗漏中间层。
- **直接证据**: `ingestion/service.py:105-115`（plain async for，无 try/finally aclose）；`service_runtime.py:3111`（plain async for，无 try/finally aclose）；§4.4（列出3个文件但无具体 aclose 模式）。
- **影响**: 资源泄漏（文件句柄、网络连接）；测试可能通过但生产出现 resource warning 或 fd exhaustion。
- **建议改法和验证点**: §4.4 补充每个层的 aclose 模式。例如：
  - `DefaultFinsRuntime._execute_stream`：`stream = pipeline.download_stream(...); try: async for event in stream: yield event; finally: await stream.aclose()`
  - `FinsIngestionService.download_stream`：`backend_stream = self._backend.download_stream(...); try: async for event in backend_stream: yield event; finally: await backend_stream.aclose()`
  - `_iter_stream_events`：`try: async for event in stream: ...; finally: await stream.aclose()`
  测试验证：CancelledError 路径下所有层的 aclose 被调用 exactly once。
- **修复风险**: 低
- **严重程度**: 中

### CORR-004-未修复-[中]-§8.2 source_sync_runs CHECK 约束实现路径不明确

- **位置**: §8.2 source_sync_runs 扩展列约束
- **问题类型**: 不可直接实施
- **当前写法**: §8.2 描述了 source_sync_runs 新 row 的复杂 CHECK 条件："succeeded：status=succeeded、safe_error NULL、retry=false、ingested>0、failed=0"；"partial：status=succeeded、safe_error=partial_batch、retry=true、ingested>0、failed>0"；"no_change：status=succeeded、safe_error NULL、retry=false、ingested=0、failed=0" 等。但没有说明这些是 CHECK constraint、trigger 还是 application-level validation。
- **反例/失败场景**: PostgreSQL CHECK constraint 无法表达"status=X AND safe_error IS NULL AND retry=false AND ingested>0 AND failed=0"这种跨列条件组合（需要单个 CHECK 表达式或多个 CHECK）。如果用单个 CHECK，表达式会非常复杂。如果用 trigger，DDL 更复杂但更灵活。plan 没有指定实现路径，实现者需要自行决定。
- **为什么有问题**: plan 声称是 code-generation-ready，但 CHECK 约束的实现路径是 migration 的核心细节。不同的实现路径（CHECK vs trigger）对 DDL 复杂度、错误消息质量和维护成本影响很大。
- **直接证据**: §8.2（逐项列出每种 outcome 的 CHECK 条件）；无 CHECK/trigger/application 分层指定。
- **影响**: 实现者可能选择过简的 CHECK（遗漏边界条件）或过复杂的 trigger（难以维护）。
- **建议改法和验证点**: §8.2 显式声明实现路径。推荐：(a) 用多个 CHECK constraint 分别约束简单条件（如 `records_discovered >= 0`、`records_ingested >= 0`）；(b) 用一个 CHECK constraint 约束 outcome 级别的条件组合（如 `CASE WHEN job_attempt_id IS NOT NULL THEN status IN ('succeeded', 'failed') ELSE TRUE END`）；(c) 复杂的跨列不变量（如 `records_discovered = downloaded + reused + ignored + failed`）用 application-level validation 或 deferred trigger。验证：DDL 中每个 CHECK constraint 有明确的 name 和表达式。
- **修复风险**: 低
- **严重程度**: 中

### CORR-005-未修复-[中]-§5.2 ScheduleService.ensure_registered 的 cron validation 语义未指定

- **位置**: §5.2 ensure_registered
- **问题类型**: 契约缺失
- **当前写法**: §5.2 说"ScheduleService.ensure_registered 只做既有 cron semantic validation 后委托 Store。"§5.2 还说"ensure_registered 使用 INSERT ... ON CONFLICT DO NOTHING，再按 tenant + schedule_key 重读；既有 definition 的 descriptor、payload、cron、timezone、misfire policy/grace/deadline 与请求逐字段相同则返回同 row（无论当前 active/disabled、version/cursor 已推进）；比较明确排除 id/state/next_fire_at/version/created_at/updated_at；任一 immutable 漂移抛 ScheduleVersionConflictError。"
- **反例/失败场景**: `ScheduleService.register`（`schedule_service.py:866-891`）调用 `_validate_croniter_expression(request.cron_expression)` 做 cron validation。`ensure_registered` 也需要同样的 cron validation，但 plan 没有说明：(a) ensure_registered 是否复用 register 的 cron validation 逻辑；(b) 如果 INSERT 成功（首次创建），是否返回 disabled draft；(c) 如果 INSERT 冲突（已存在），重读后的比较是否包括 cron expression 本身（应该是，因为 cron 是 immutable）。
- **为什么有问题**: 实现者需要知道 ensure_registered 的精确语义：首次创建返回什么状态、重读比较哪些字段、cron validation 是否复用。plan 描述了 Store 层行为但 Service 层行为不完整。
- **直接证据**: §5.2（"ScheduleService.ensure_registered 只做既有 cron semantic validation 后委托 Store"）；`schedule_service.py:866-891`（register 的 cron validation 模式）；无 ensure_registered 的 Service 层完整签名和行为。
- **影响**: 实现者可能遗漏 cron validation 或错误处理首次创建 vs 重读的返回值。
- **建议改法和验证点**: §5.2 补充 Service 层 ensure_registered 的完整行为：(a) 签名：`ensure_registered(scope, request) -> ScheduleDefinition`；(b) 先做 `_validate_croniter_expression(request.cron_expression)`；(c) 委托 `self._schedule_store.ensure_registered(scope, request)`；(d) 返回 Store 的结果（首次创建的 disabled draft 或已存在的 definition）。验证：测试 `ensure_registered` 对已存在 schedule 返回相同 definition、对 immutable drift 抛 ScheduleVersionConflictError。
- **修复风险**: 低
- **严重程度**: 中

### CORR-006-未修复-[中]-§2.2 handler 不得返回 CANCELLED 的约束未在 handler protocol 中体现

- **位置**: §2.2 Job 完成的精确定义；§3.1 handler protocol
- **问题类型**: 契约缺失
- **当前写法**: §2.2 说"不得从 handler 返回 SafeJobErrorCode.CANCELLED。PG cancel intent、deadline、max attempts 的唯一真源仍是 PostgresJobStore。asyncio.CancelledError 原样传播；不得持久化 source observation。"§3.1 的 `JobExecutionHandlerProtocol` 签名是 `execute(request, cancellation) -> JobCompletion | JobFailure`。
- **反例/失败场景**: `SafeJobErrorCode.CANCELLED`（`jobs.py:151`）是 `JobFailure` 的合法 `safe_error_code`。如果 handler 返回 `JobFailure(safe_error_code=SafeJobErrorCode.CANCELLED)`，`JobService.execute_claim` 会接受它（line 635-636 只检查 `isinstance(result, (JobCompletion, JobFailure))`）。但 plan 说 handler 不得返回 CANCELLED。这个约束只在 plan 文本中，不在 Protocol 或代码中。
- **为什么有问题**: plan 声称是 code-generation-ready，但 handler 的 CANCELLED 约束只在 plan 文本中。实现者可能忽略这个约束，让 handler 返回 CANCELLED。虽然 JobService 可以在 execute_claim 中拦截 CANCELLED，但 plan 没有指定这个拦截。
- **直接证据**: §2.2（"不得从 handler 返回 SafeJobErrorCode.CANCELLED"）；`job_service.py:628-639`（execute_claim 不检查 safe_error_code）；`jobs.py:151`（CANCELLED 是合法枚举值）。
- **影响**: 实现者可能让 handler 返回 CANCELLED，导致 JobStore 以 CANCELLED 收敛而非保留 source truth。
- **建议改法和验证点**: 两个选项：(a) 在 `JobService.execute_claim` 中新增检查：如果 `isinstance(result, JobFailure) and result.safe_error_code is SafeJobErrorCode.CANCELLED`，返回 `rejected`；(b) 在 plan §2.2 显式声明："handler 返回 CANCELLED 时，execute_claim 映射为 HANDLER_REJECTED"。推荐 (a)，因为它在代码层面强制约束。验证：测试 handler 返回 CANCELLED 时 execute_claim 返回 HANDLER_REJECTED。
- **修复风险**: 低
- **严重程度**: 中

### CORR-007-未修复-[低]-§11 allowlist 未列入 dayu/fins/ingestion/service.py 的 aclose 改动范围

- **位置**: §11 Exact implementation allowlist
- **问题类型**: 范围漂移
- **当前写法**: §11 allowlist 列出 `dayu/fins/ingestion/service.py`（line 736），但 §4.4 要求修改该文件添加 aclose。同时 §4.4 列出3个文件（service_runtime.py、ingestion/service.py、pipeline_backends.py），但 pipeline_backends.py 的 aclose 模式未指定。
- **反例/失败场景**: `dayu/fins/ingestion/service.py` 在 allowlist 中，可以修改。但 `dayu/fins/ingestion/pipeline_backends.py` 不在 allowlist 中（line 734 只列了 `dayu/fins/ingestion/service.py`）。如果 pipeline_backends.py 需要 aclose 修改，实现者必须 STOP 回 Controller。
- **为什么有问题**: §4.4 明确列出3个文件需要 aclose 修改，但 §11 allowlist 只包含其中2个（service_runtime.py 和 ingestion/service.py）。pipeline_backends.py 不在 allowlist 中。
- **直接证据**: §4.4（"同时修改 dayu/fins/service_runtime.py、dayu/fins/ingestion/service.py、dayu/fins/ingestion/pipeline_backends.py"）；§11 allowlist（无 `dayu/fins/ingestion/pipeline_backends.py`）。
- **影响**: 实现者发现 pipeline_backends.py 需要修改但不在 allowlist 中，必须 STOP 回 Controller，浪费时间。
- **建议改法和验证点**: §11 allowlist 新增 `dayu/fins/ingestion/pipeline_backends.py`。或者，如果 pipeline_backends.py 不需要 aclose 修改（因为 aclose 在 ingestion service 层处理），§4.4 应从文件列表中移除它。验证：allowlist 与 §4.4 的文件列表一致。
- **修复风险**: 低
- **严重程度**: 低

### CORR-008-未修复-[低]-§10 validation gates 的 "focused tests per module" 定义模糊

- **位置**: §10 Validation gates 第1项
- **问题类型**: 不可直接实施
- **当前写法**: §10 gate 1："每个新增/修改 production module 单独运行对应 focused tests，coverage >= 80%；不能用聚合覆盖掩盖低文件。"
- **反例/失败场景**: "focused tests" 的定义不明确。对于 `dayu/services/job_service.py`（修改量大），"focused tests" 是 `tests/application/test_job_service.py` 吗？还是所有 import job_service 的测试？对于 `dayu/investment/storage/postgres_sources.py`（新增），"focused tests" 是 `tests/integration/investment/test_postgres_sources.py` 吗？实现者可能选择过窄的 test suite 导致 coverage 虚高。
- **为什么有问题**: plan 声称是 code-generation-ready，但 validation gate 的执行路径不明确。实现者需要知道每个 production module 对应哪个 test file。
- **直接证据**: §10 gate 1（"每个新增/修改 production module 单独运行对应 focused tests"）；§11 test allowlist（列出所有测试文件但未映射到 production module）。
- **影响**: 实现者可能选择错误的 test suite，导致 coverage 计算不准确。
- **建议改法和验证点**: §10 gate 1 补充 mapping table：每个 production module → 对应的 focused test file。例如：`dayu/services/job_service.py` → `tests/application/test_job_service.py`；`dayu/investment/storage/postgres_sources.py` → `tests/integration/investment/test_postgres_sources.py`。或者声明"focused tests = §11 allowlist 中以该 module 名为前缀的测试文件"。验证：每个 production module 至少有一个 focused test file。
- **修复风险**: 低
- **严重程度**: 低

## Open Questions

None. All critical design decisions are resolved in the corrective plan.

## Residual Risks

| Risk | Owner | Tracking |
|---|---|---|
| provider at-least-once read（Fins connector owner，最大 3 attempts） | Fins connector | 后续 slice |
| 循环 schedule template（Schedule owner） | Schedule owner | 后续 slice |
| outbox delivery | 7.6 | 后续 slice |
| operator auth/RBAC | 7.1 | 后续 slice |
| RSS/industry/manual bytes（后续 connector） | Future connector | 后续 slice |
| Fact extraction/review | Future evidence slice | 后续 slice |
| source terminal 与 Job terminal 跨事务不同步（§2.3 明确接受的 residual） | Controller | §16 residual 2 |
| Fins date-only 元数据只能做 calendar-day freshness（§16 residual 7） | Fins connector | 后续 slice |

## Plan Review Conclusion

**PASS-WITH-RISKS**

Open findings: **H=2, M=4, L=2**

Corrective plan 整体质量显著高于初稿。Controller 的纠偏准确地识别并修复了初稿的核心缺口：trusted TenantScope 传递、source terminal/Job terminal 跨事务 honest boundary、DownloadEvent identification、schedule ensure_registered、composite FK 闭合、health/alert 同事务原子性、三新表列/guard/grant 精确冻结。

两个 High finding 均为 migration/concurrency 的 code-generation-ready 细节缺口：
- CORR-001（terminal transaction lock order）是并发安全的必要条件，不指定则实现者可能引入 deadlock。
- CORR-002（job_attempts 新 UNIQUE 约束的 DDL ordering）是 migration 成功的必要条件，不指定则 migration 脚本可能失败。

四个 Medium finding 是契约/实现路径的细化，不阻塞 plan 整体正确性但需要 implementation agent 做额外判断。

两个 Low finding 是 allowlist 一致性和 validation gate 定义的 minor gap。

建议：Controller 修复 CORR-001 和 CORR-002 后，plan 可进入 implementation gate。CORR-003-008 可由 implementation agent 在实现时自行处理，或在 code review 阶段闭合。
