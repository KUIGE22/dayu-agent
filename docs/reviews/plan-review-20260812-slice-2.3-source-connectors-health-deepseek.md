# Slice 2.3 独立 plan review（DeepSeek）

- Reviewer：DeepSeek（独立 reviewer，未参考任何其它 reviewer 结论）
- 日期：2026-08-12（生成 timestamp 20260812-123010）
- 目标计划：`docs/plans/2026-08-12-slice-2.3-source-connectors-health.md`
- 设计/控制真源：`docs/plans/2026-08-10-investment-platform-restoration.md`
- Handoff：`docs/reviews/plan-handoff-20260812-slice-2.3-source-connectors-health-codex-terra.md`
- 基线：`0db6c7b63608a15cd157f842a5be772799fdacd9`（已核对 `git rev-parse HEAD` 一致）
- 只读 review：未修改目标计划、master、handoff、代码、测试或 Git 状态；未联网/live/provider/Broker。

## 1. Reviewed target & scope

审阅了目标计划全部 11 节、handoff、master Phase 2（Slice 2.1/2.2/2.3 与 §6.2/§6.3/§8 DAG）、以及以下直接代码事实：

- `dayu/investment/domain/jobs.py`（JobExecutionRequest 八字段、JobFailure 矩阵、generic receipt 闭合矩阵、SafeJobErrorCode 现有 13 码、JobExecutionRegistry 无 seal/count）；
- `dayu/services/job_service.py`（JobHandlerRegistry/JobExecutionRegistry/execute_claim/is_execution_available/JobCancellationSignalProtocol）；
- `dayu/host/worker.py`（heartbeat 周期、finalize 收敛、取消信号来源、drain abandon 竞态）；
- `dayu/investment/storage/postgres_jobs.py`（fail/complete/cancel/recover、retryable 判定、cancel-intent 收敛、receipt 构造）；
- `dayu/investment/storage/migrations/versions/0001/0003/0004`（source_sync_runs 约束与 grants、job_attempts 约束、0003 downgrade admission、0004 head/down_revision）；
- `dayu/investment/storage/models_identity.py`、`dayu/investment/domain/source.py`、`dayu/investment/storage/protocols.py`；
- `dayu/fins/service_runtime.py`、`dayu/fins/domain/evidence_locator.py`、`dayu/services/fins_service.py`、`dayu/services/protocols.py`；
- `dayu/services/startup_preparation.py`（阶段 1/2、_build_production_services_provider、PreparedHostRuntimeDependencies）、`dayu/startup/platform.py`、`dayu/investment/composition.py`；
- `dayu/investment/domain/schedules.py`（静态 snapshot/payload/idempotency_key，无 per-occurrence UUID）、`dayu/cli/workspace_migrations/platform_jobs.py`。

## 2. Assumptions tested（结论摘要）

| 假设 | 结论 |
|---|---|
| JobExecutionRequest 无 lease/fence/token，不能扩充 | **成立**（jobs.py:1191-1244，handler 走 execute_claim 收窄） |
| 0001 source_sync_runs/source_health_snapshots append-only、app 仅 SELECT/INSERT | **成立**（0001 `_APP_APPEND_TABLES`，models_identity 无 updated/version） |
| FinsService.submit() 入 Host，Worker 不得嵌套 | **成立**（fins_service.py 薄委托 runtime；新增 sync_worker_source 可行） |
| verified locator 只能由 Fins runtime/storage 产出 | **成立**（S13 已有 resolve/validate + source meta：document_version/source_fingerprint/ingest_complete；SEC pipeline 有 provider 侧 filing_date 可供 source-observed time） |
| 2.2 ScheduleService 只持久化静态 payload/idempotency snapshot | **成立**（schedules.py CanonicalScheduleEnqueueSnapshot，request_fingerprint 静态） |
| 0005 down_revision="0004_durable_schedules"、0003/0004 downgrade admission 先例 | **成立**（0004 down_revision 已核；0003 有 pg_depend 外部依赖 preflight） |
| 生产 startup 顺序/唯一 Host+Fins runtime 可扩展 investment_sources | **成立**（_build_production_services_provider 需新增 fins_runtime 参数，startup_preparation.py 在 allowlist 内；platform.py 不校验 service 名） |
| **retryable failure 与 operation head terminal 收敛** | **不成立**（F1） |
| **每 attempt 终态行与 0001 idempotency_key UNIQUE 闭合** | **不成立**（F2） |
| **operation lease 与 job attempt lease 长期镜像** | **不成立**（F3） |
| **deferred connector 的执行路径自洽** | **不成立**（F4） |

## 3. Findings

### DS23-001-未修复-[高]-retryable failure 把 operation head 标 terminal，导致 source sync 的 retry 在第一次 attempt 后彻底失效（Fins 永不重试）

- **位置**: 目标计划 §6.2「terminal head 返回其 receipt 的 reusable decision」「B 读 terminal head/receipt 并重放，不调用 Fins」；§6.3「先 find_attempt_receipt(job, attempt)，再查 operation head/reusable receipt；随后 acquire operation」「每分支经 record_terminal_attempt 后再返回 JobCompletion/JobFailure」；§7.3「mark operation terminal」；§8「rate/unavailable/stale/… -> retryable 或 nonretryable failure」「rate retry 使用 descriptor backoff」。
- **问题类型**: 状态机漏洞 / 并发恢复风险
- **当前写法**: handler 对 rate/unavailable 返回 retryable failure，且「每分支」都先走 record_terminal_attempt；record_terminal_attempt 无条件「mark operation terminal」。下一次 attempt 的 handler 流程在 acquire 之前先查 operation head，terminal head 一律返回 reusable decision 重放。
- **反例/失败场景**: attempt 1 被 rate_limited → record_terminal_attempt（head 置 terminal、source run/health 落库）→ 返回 `JobFailure(SOURCE_RATE_LIMITED, retryable=True)` → store `fail()` 进入 retry_wait（postgres_jobs.py:1621-1624 按 `failure.retryable` 计算重试）→ attempt 2 被 claim → handler 先查 head：terminal → **重放同一 retryable receipt，零 Fins 调用** → 再次 `fail()` → attempt 3 同样重放 → `RETRY_EXHAUSTED`。**即便零崩溃、零竞态**，一次 rate limit 就会耗尽全部 3 次 attempt，且此后永远不再触碰 Fins；§8 声称的「rate retry 使用 descriptor backoff」落空。§6.2 的「A/B overlap」只描述了 completion 的崩溃重放，没有为「terminal head 持 retryable-failure receipt」定义任何重新执行路径（terminal head 不可 re-acquire）。
- **为什么有问题**: 与计划自身核心承诺（bounded at-least-once read、max_attempts=3 有界重试、retryable failure 收敛）直接矛盾；实现者按字面实现将产出「重试形同虚设」的生产 handler，且 S23-B/S23-C 的 retry 相关 fault 测试若按计划文字构造会掩盖该行为。
- **直接证据**: 计划 §6.2/§6.3/§7.3/§8 原文；代码事实 postgres_jobs.py:1621-1624（retryable 判定只依赖 failure.retryable，不感知 operation head）、worker.py:1164-1193（finalize 只做 complete/fail）。
- **影响**: 生成错误代码（retry 失效）/ 源同步在首个限流后必然失败 / 健康被错误累积 failures。
- **建议改法和验证点**: (a) record_terminal_attempt 对 **retryable-failure outcome 不得把 head 置 terminal**（保留 active/expired，供下一 attempt 以 generation+1 重新 acquire 并重跑 Fins）；仅 completion 与 non-retryable failure 置 terminal 供崩溃重放；(b) 明确「terminal head 的 reusable decision 只对 completion/non-retryable receipt 生效」；(c) 验证点：PG16 fault 测试断言「attempt 1 retryable → attempt 2 必须再次调用 Fins 且 Fins 调用计数 >=2」；崩溃重放测试仅对 completion receipt 断言「B 不调 Fins」。
- **修复风险（低）**: 需要同时处理 F2 的 idempotency_key 约束（见 DS23-002），否则 per-attempt 多行会撞 UNIQUE。
- **严重程度（高）**:

### DS23-002-未修复-[高]-source_sync_runs 的 0001 `UNIQUE(tenant_id, idempotency_key)` 与每 attempt 一条终态行冲突，0005 未处理

- **位置**: 目标计划 §7.1（新增 job_run_id/job_attempt_id/…/partial unique `(tenant_id, job_attempt_id)`、「新 attempt row 必须 complete terminal status…」「2.3 永远 INSERT 一次终态 row」）；§4.1「Job idempotency key 固定 `source-sync:v1:<request_fingerprint>`」；0001 DDL `0001_platform_foundation.py:451` `CONSTRAINT uq_source_sync_runs_tenant_id_idempotency_key UNIQUE (tenant_id, idempotency_key)`。
- **问题类型**: 契约缺失 / schema 变更漏洞
- **当前写法**: 0005 只新增列与 partial unique `(tenant_id, job_attempt_id)`，未 drop/替换 0001 的 `UNIQUE(tenant_id, idempotency_key)`；新行的 idempotency_key 取值未定义。同一 job 的 payload 在各 attempt 间逐字节相同，Job 级 idempotency key 恒定。
- **反例/失败场景**: 任何「两个 attempt 都成功 record_terminal_attempt」的路径——最直接的是实施 DS23-001 修复后：attempt 1（rate_limited）落一行、attempt 2（重跑成功）落第二行，两行 idempotency_key 相同 → 第二次 INSERT 违反 `uq_source_sync_runs_tenant_id_idempotency_key` → RepositoryError → 按 §6.3「repository error 才映射 REPOSITORY_FAILURE」→ job 非重试失败，且 record_terminal_attempt 事务整体回滚（health/snapshot/outbox 全丢）。计划 §7.1 的 partial unique 恰恰暗示「per-attempt 行」是设计意图，与 §4.1 恒定 key 自相矛盾。
- **为什么有问题**: 0005 没有给出与「per-attempt 终态行」兼容的 idempotency 语义；实现者必须在实现期自行发明（改 key 或删约束），属于计划未收敛的 schema 决策，违反「code-generation-ready」要求。
- **直接证据**: 0001_platform_foundation.py:451；计划 §7.1/§4.1 原文；0003 job_attempts 的 `UNIQUE(tenant_id, job_run_id, attempt_number)` 与 `UNIQUE(tenant_id, id)` 均不能约束 source_sync_runs 行。
- **影响**: 生成错误代码（运行时唯一约束崩溃）/ 状态不一致 / 后续返工。
- **建议改法和验证点**: 0005 显式二选一并写明：(a) source_sync_runs 的 idempotency_key 改为 per-attempt（如 `source-sync:v1:<request_fingerprint>:<attempt_id>`），保留 0001 UNIQUE；或 (b) 0005 drop `uq_source_sync_runs_tenant_id_idempotency_key`，由 `UNIQUE(tenant_id, job_attempt_id)` 承担每 attempt 唯一。验证点：真实 PG 测试「同一 job 两个 attempt 各成功 record 后两行并存且查询闭合」。
- **修复风险（低）**:
- **严重程度（高）**:

### DS23-003-未修复-[中]-operation head lease 冻结在 acquire 时刻，不被 worker heartbeat 续约；WAIT 分支在镜像设计下不可达；SourceOperationLeaseLost 的 handler 行为未定义

- **位置**: 目标计划 §6.2「lease 精确镜像该 job attempt expiry」「另一 attempt 的 active、未过期 head 返回 WAIT…SOURCE_OPERATION_BUSY」「record_terminal_attempt 必须以 (owner_attempt_id, generation, lease_expires_at > database now()) 条件更新 head；0 rows 就是 SourceOperationLeaseLost，A 不得写 source run/health/outbox，也不得报告 completion」；§6.1/§11 STOP「若 Fins operation 无法在 descriptor deadline/lease 内安全运行」。
- **问题类型**: 并发恢复风险 / 状态机漏洞 / 契约缺失
- **当前写法**: 计划只规定 acquire 时 lease 镜像 attempt expiry，未规定 heartbeat 续约 operation head，也未规定 handler 收到 SourceOperationLeaseLost 时返回什么。
- **反例/失败场景**: (a) Fins 同步耗时 > lease_duration(900s) 但 < job deadline（worker 心跳持续有效续约 job lease，worker.py:1027-1038 heartbeat 周期、postgres_jobs.py:1263 heartbeat 续约）→ operation head 到期而 job attempt 仍 leased → B 无法 claim → A 完成 Fins 后 record 条件 `lease_expires_at > database now()` 为假 → SourceOperationLeaseLost → 计划未定义返回：若抛异常冒泡 → `execute_claim` 映射 `HANDLER_REJECTED`（非重试）→ job 直接失败；若返回 retryable，下一 attempt 重新 acquire（新 generation、新 900s）后同一慢源再次超头 → 3 attempts 内永不收敛，且每次 Fins 工作被丢弃重做；(b) 「WAIT」分支在镜像设计下几乎不可达：B 能 claim 意味着 A 的 job attempt lease 已过期，而 head 到期不晚于 attempt 到期（head 不随心跳延长）→ active+未过期 head 无法被观察到，「A/B acquire-WAIT」测试只能靠直接注入 head 状态构造。
- **为什么有问题**: 计划自称「A/B overlap 时序」是必查收敛点（handoff §3），但 lease 生命周期不对称（job lease 可心跳延长、operation head 不可）使「精确镜像」随时间失效，且最关键的分支结果（SourceOperationLeaseLost 之后 handler 怎么办）无契约，实现者必须重新设计。
- **直接证据**: worker.py:1027-1038（heartbeat 周期与续约）、postgres_jobs.py:1263（heartbeat 续约 job lease）；计划 §6.2 无任何 operation head 续约机制；§6.3 无 SourceOperationLeaseLost 分支。
- **影响**: 慢而有效的同步丢失结果 / 非重试误杀 / WAIT 语义死代码 / 实现者自行设计。
- **建议改法和验证点**: (a) 规定 operation head lease 与 job attempt lease 同步续约（同一 heartbeat 事务内更新，或 head 有效期直接绑定 job deadline 且 B 的抢占以 job attempt lease 过期为准）；(b) 明确规定 SourceOperationLeaseLost → handler 返回 retryable `JobFailure(SOURCE_OPERATION_BUSY)`（与 WAIT 分支一致），绝不向 execute_claim 冒泡为 HANDLER_REJECTED；(c) PG16 fault 测试覆盖「Fins 时长超过 operation lease 但未超 job deadline」的确定性收敛（通过 fixture 直接改写 head lease 而非 sleep）。
- **修复风险（中）**: 需要协调 heartbeat 事务与 operation head 的写入归属（仍须避免跨层耦合，heartbeat 只能在 Job store 内完成，operation head 续约需由 Job store 或注入的窄回调完成）。
- **严重程度（中）**:

### DS23-004-未修复-[中]-deferred connector（RSS/industry/manual）的 handler 执行路径与 enqueue 的 executable 门禁自相矛盾

- **位置**: 目标计划 §4.3「RSS/industry/manual 只生成无 bytes 的 DeferredExternalIngestionRequest，2.3 handler 以 non-retryable terminal receipt 收敛，绝不联网/上传/写 Fact」；S23-A「unknown/deferred no Fins」；§6.3「enqueue_sync…验证 enabled/version/executable source」（2.3 仅 fins.market-disclosure.v1 executable）。
- **问题类型**: 范围漂移 / 契约缺失 / 不可直接实施
- **当前写法**: 一边说 handler 会对 deferred connector 收敛出 terminal receipt（意味着存在可执行的 deferred job），一边说 enqueue 拒绝非 executable source（意味着 deferred job 永远不会被创建）。`DeferredExternalIngestionRequest` 也未列入 §4.1 的类型表，无字段定义。
- **反例/失败场景**: 若实现者遵守 enqueue 的 executable 门禁，则 rss/industry/manual 的 job 无法入队，handler 的 deferred 分支与 S23-A 的「deferred no Fins」测试只能靠手工构造 payload 到达——测试与生产路径脱节；若放行非 executable，则 deferred job 走 record_terminal_attempt → §8 矩阵「零 locator → failures+1」→ 健康被降级、发 alert，而计划未定义 deferred 的 outcome/code/health 语义（deferred 不在 SourceSyncOutcome 内）。
- **为什么有问题**: 同一计划的两个章节对「deferred 是否可执行」给出相反约束，实现者必须自行裁决，属于未收敛的 scope 决策。
- **直接证据**: 计划 §4.3 / S23-A / §6.3 / §8 原文；`SourceSyncOutcome` closed 集合无 deferred（§4.1）。
- **影响**: 实现跑偏 / 测试与生产脱节 / 健康状态误报。
- **建议改法和验证点**: 明确二选一：(a) deferred 仅存在于 connector registry/plan() 契约层（registry 闭合测试覆盖），enqueue 对非 executable 恒定拒绝，S23-A 的 deferred 断言改为 registry/plan 层（不产生 job）；或 (b) 若允许显式 trigger 入队 deferred，则规定其 receipt outcome/code（如 failed+SOURCE_INVALID）与健康行为（不触发 degraded 或独立 code）。验证点：对应命名测试显式断言所选语义。
- **修复风险（低）**:
- **严重程度（中）**:

### DS23-005-未修复-[低]-outbox 去重的冲突语义未指定（裸 INSERT 会把 run/health/snapshot 一起回滚）

- **位置**: 目标计划 §7.2「`UNIQUE(tenant_id,dedupe_key)`」「INSERT deduped outbox」；§7.3「若有 transition INSERT deduped outbox…任何失败全回滚」；§8 dedupe key 定义。
- **问题类型**: 契约缺失 / 并发恢复风险
- **当前写法**: 只给 UNIQUE 约束与 dedupe key 公式，未规定冲突时的处理（ON CONFLICT DO NOTHING / SELECT-then-INSERT / 报错）。
- **反例/失败场景**: 同一 episode 内两次 record 命中同一 dedupe key（operator re-enable 竞态、崩溃重放后的重复 transition、7.6 未来 delivery 重放）时，裸 INSERT 抛 UNIQUE 冲突 → 整个 record_terminal_attempt 事务回滚（terminal run + health head + snapshot 全部丢失）→ REPOSITORY_FAILURE。当前 §8 矩阵多数重复不发 event，但 crash/replay 与后续 slice 使该约束承重。
- **为什么有问题**: 去重是「语义事件 best-effort」，不该成为业务写入的失败源；机制缺失会让实现者自由选择，错选即静默丢数据。
- **直接证据**: 计划 §7.2/§7.3/§8；`source_health_alert_outbox` 为 append-only 且无 delivery state（7.6 才消费）。
- **影响**: 数据丢失 / 非重试失败 / 后续返工。
- **建议改法和验证点**: 明确 outbox 使用 `INSERT … ON CONFLICT (tenant_id, dedupe_key) DO NOTHING`，dedupe 冲突绝不影响 run/snapshot 提交；验证点：PG 测试「同 episode 重复 transition 提交 run+snapshot 且 outbox 仅一行」。
- **修复风险（低）**:
- **严重程度（低）**:

### DS23-006-未修复-[低]-`cancelled -> JobFailure(CANCELLED)` 映射未限定 PG cancel intent 前置，无 intent 时 store fail() 抛 JobInputError

- **位置**: 目标计划 §6.3「cancelled -> CANCELLED non-retryable」；代码事实：jobs.py:882-888（`_validate_receipt_combination` 对 reason=failure 拒绝 CANCELLED 码）、postgres_jobs.py:1583-1600（仅当 `cancel_requested_at` 非空才 `_converge_cancel_intent` 收敛为 cancelled；否则 1676-1700 走 terminal_code=CANCELLED → `build_generic_attempt_receipt(failure, CANCELLED)` → JobInputError）、worker.py:946-971（drain abandon 的 request_cancel 竞态窗口）。
- **问题类型**: 契约缺失 / 状态机漏洞
- **当前写法**: 计划把 Fins cancelled 直接映射为 `JobFailure(CANCELLED)`，未说明该返回仅在 PG cancel intent 存在时合法。
- **反例/失败场景**: handler 观察到取消信号（worker shutdown drain 竞态）且 PG 无 cancel intent、未到 deadline → 返回 JobFailure(CANCELLED) → store fail() 构造 failure+CANCELLED receipt 触发闭合矩阵拒绝 → JobInputError 冒泡 → worker 以 runtime failure 退出（退出码 1），而非干净收敛。正常路径（cancel intent/deadline）会被 store 先行收敛，故该洞仅在 drain 竞态窗口触发，但实现者按字面映射必然踩中。
- **为什么有问题**: 2.1 的 generic 不变量是「cancelled 只能由 cancel-intent 收敛产生」，§6.3 的映射表破坏了该不变量且未加前置条件。
- **直接证据**: jobs.py:882-888、postgres_jobs.py:1583-1600/1676-1700、worker.py:946-971。
- **影响**: worker 非预期退出 / 取消语义失真。
- **建议改法和验证点**: §6.3 明确：handler 返回 CANCELLED 仅当取消信号对应 PG cancel intent（或由 store 的 cancel-intent 分支自动收敛，handler 对 Fins-cancelled 一律返回 retryable SOURCE_OPERATION_BUSY / 非重试 SOURCE_*）；验证点：单元测试证明「无 cancel intent 时 handler 不产生 CANCELLED 返回」。
- **修复风险（低）**:
- **严重程度（低）**:

### DS23-007-未修复-[低]-coverage 命令未覆盖全部新增/修改 production module

- **位置**: 目标计划 §10 命令清单（`--cov=dayu.services.investment_sources --cov=dayu.investment.connectors.source --cov=dayu.fins.service_runtime`）与 §9 修改文件清单（另含 `dayu/services/job_service.py`、`dayu/services/fins_service.py`、`dayu/services/startup_preparation.py`、`dayu/investment/domain/source.py`、`dayu/investment/domain/jobs.py`、`dayu/investment/storage/postgres_sources.py` 等）。
- **问题类型**: 测试缺口
- **当前写法**: §10 文字 gate 声明「每个新增/修改 production module branch coverage >=80%」，但给出的 cov 命令只测 3 个 module。
- **反例/失败场景**: 实现者按 §10 命令跑完即以为 coverage gate 闭合，实际 registry seal（job_service.py）、startup 装配（startup_preparation.py）、domain 校验（source.py/jobs.py）等修改模块未纳入测量。
- **为什么有问题**: 命令与 gate 声明不一致，验收可被无意识绕过。
- **直接证据**: 计划 §9 与 §10 对照。
- **影响**: 验收失真 / 覆盖漏洞后移。
- **建议改法和验证点**: cov 命令显式追加全部新增/修改 module（或给出「按 §9 文件清单逐模块 cov」的显式说明）。
- **修复风险（低）**:
- **严重程度（低）**:

### DS23-008-未修复-[低]-S23-C 的 MinIO（S3）locator readback 测试未命名测试文件/断言

- **位置**: 目标计划 S23-C「Relevant S3 storage fixture follows existing MinIO lane」与 §9 允许测试文件清单（`tests/fins/test_fins_runtime_source_sync.py` 等，无 MinIO 变体）。
- **问题类型**: 测试缺口
- **当前写法**: 只写「follows existing MinIO lane」，未命名承载 S3 backend 下 `sync_worker_source` verified locator readback 的具体测试文件或标记。
- **反例/失败场景**: 生产 S3 模式（Slice 1.4 已接受）下 locator readback 的字节真源差异（FS vs S3）无测试覆盖，实现者会以 FS fixture 冒充闭合。
- **为什么有问题**: 「Fins 自身 runtime/storage 返回 verified locator」是硬边界，S3 是已接受的生产路径，缺命名测试即缺可验收证据。
- **直接证据**: 计划 S23-C 与 §9 allowlist；1.4 已接受 S3 blob repository。
- **影响**: 验收缺口 / 回归风险后移。
- **建议改法和验证点**: 在 `tests/fins/test_fins_runtime_source_sync.py`（或 allowlist 内新文件）明确命名 MinIO 变体用例与集成标记，复用既有 MinIO fixture。
- **修复风险（低）**:
- **严重程度（低）**:

### DS23-009-未修复-[低]-registry seal 使「所有未来 handler 必须在 seal 前注册」成为承重契约，计划未登记该扩展点

- **位置**: 目标计划 §6.1（seal 后所有 register 抛 JobInputError；startup 精确顺序；断言两个 registry 均仅该 job type）、§11（完成报告含 sealed job types/count）。
- **问题类型**: 最佳实践偏离 / 过度耦合（轻微）
- **当前写法**: seal 位于生产注册序列末尾，但计划未说明未来 handler（5.4 backtest、6.3 watch 等）如何扩展（只能在 seal 前追加注册），也未要求在 README/完成报告登记该契约。
- **反例/失败场景**: 后续 slice 实现者不清楚 seal 存在，在 composition 其它位点注册 handler → 运行时 JobInputError；或为绕过 seal 引入兼容入口，破坏「sealed exact-one」。
- **为什么有问题**: seal 将生产装配顺序变成全局承重点，扩展契约不写清即埋坑。
- **直接证据**: 计划 §6.1/§11；job_service.py JobExecutionRegistry 现状（无 seal）。
- **影响**: 后续返工 / 契约漂移。
- **建议改法和验证点**: 在 §10 README 说明与 §11 完成报告中显式登记「production 全部 handler 必须在 seal 之前注册，seal 后注册恒 JobInputError」；seal 顺序测试断言「seal 后 register 抛 JobInputError（含同 object）」。
- **修复风险（低）**:
- **严重程度（低）**:

## 4. 已验证无问题的重点区域

- **hard scope / 自动采集目标 owner**：Fins market-disclosure 同步由 Fins connector（SourceConnectorRegistry/FinsMarketDisclosureConnector）、Fins runtime（sync_worker_source）、InvestmentSourcesService、PostgresSourceSyncRepository、handler 明确分权；RSS/industry/manual 无 bytes、不联网、不写 Fact；循环 schedule 不注册、提供显式 trigger_id enqueue API，STOP 条件明确。owner 清晰。
- **Fins 非嵌套 Host 边界**：`FinsServiceProtocol/FinsService/FinsRuntimeProtocol/DefaultFinsRuntime` 新增 `sync_worker_source` 只走 Service→runtime，不调用 submit()/execute()/ServiceSessionCoordinator/host.run_operation_*；取消经 `JobCancellationSignalProtocol.is_cancel_requested` 注入；verified locator owner 为 Fins runtime 内部 validate_evidence_locator + source meta（document_version/source_fingerprint），代码事实支持可行性。
- **attempt state / generation fencing 主体**：`acquire_source_operation` 单事务锁 operation head + job_attempts row、generation+1、条件 terminal 更新（owner_attempt_id, generation, lease 未过期）设计正确，方向与 2.1 的 fence 语义一致；A 失 lease 后条件写 0 rows 即 SourceOperationLeaseLost 的思路正确（缺口见 DS23-003 的返回语义）。
- **partial/health/alert 原子性**：record_terminal_attempt 单事务覆盖 run+health head+snapshot+outbox+head terminal、任何失败全回滚、Fins 调用期间不持 PG 事务——设计正确（dedupe 冲突语义见 DS23-005）。
- **0005 schema/RLS/grants/downgrade 历史兼容**：旧 row（job_attempt_id NULL）合法、新列可空、terminal CHECK 只约束新行、RLS FORCE + 唯一 tenant policy + PUBLIC revoke + app SELECT/INSERT + head 最小列级 UPDATE + guard trigger、downgrade 按 0003/0004 先例做外部依赖 preflight 且对修改既有表增加业务行 fail-closed——方向正确；job_attempts 增 `UNIQUE(tenant_id, job_run_id, id)` 支撑 composite FK 可行。
- **allowlist / 实施切片 / 命名测试 / STOP / residual**：文件清单与 master 2.3 allowlist 一致（更严格，platform.py 以 type-contract 例外覆盖）；S23-A/B/C 顺序合理、命名测试覆盖两个 crash cut point、fault 测试禁 sleep/真实 provider；STOP 与 residual owner（provider at-least-once read、schedule template、outbox 7.6、RBAC 7.1、RSS/industry/manual bytes、Fact extraction）完整诚实。

## 5. Open questions

- O1（folding 进 DS23-003 的修复）：operation head 续约若绑定 heartbeat 事务，归属谁实现——Job store（postgres_jobs.py）还是注入窄回调？这影响分层边界，需 Controller 裁决后写入计划。
- O2（folding 进 DS23-004）：deferred connector 在 2.3 到底是「registry 契约层存在、enqueue 恒拒」还是「显式 trigger 可入队」，需二选一。
- O3：`source_sync_runs` 每 attempt 一行时，`UNIQUE(tenant_id, idempotency_key)` 的处置（drop vs per-attempt key）需与 DS23-001/002 一并裁决。

## 6. Residual risks / 建议去向

- 慢源（Fins 时长接近 lease_duration）的收敛只依赖 STOP 兜底；建议在修复 DS23-003 后把「operation head 续约」作为明确契约而非 STOP 例外。
- 健康矩阵对「零 locator」与 deferred 的边界语义（DS23-004 二选一后）需同步到 §8 表。
- `source_health_alert_outbox` 无 delivery state 属 7.6；本 slice 内 outbox 仅事实，已诚实标注。
- `SourceSyncAttemptReceipt` 的 locator 项只存 canonical mapping+SHA 无路径——与 S13 无路径约束一致，无需额外跟踪。
- 建议把 DS23-001/002/003/004 的修复唯一化进计划后重审（dual review），再解除 implementation freeze。

## 7. Final plan review conclusion

**FAIL**（open H/M/L = **2/2/5**）

DS23-001/002 直接破坏计划的核心承诺（retryable failure 重试收敛、per-attempt 终态 receipt 的 schema 闭合），DS23-003/004 存在必须由实现者自行裁决的契约缺口；在四项修复唯一化进计划并通过 dual re-review 前，Slice 2.3 不应进入 implementation gate。
